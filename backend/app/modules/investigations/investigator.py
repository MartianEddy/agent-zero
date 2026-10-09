"""Single-call structured model tasks; application code controls research progression."""

import asyncio
import base64
import logging
from dataclasses import dataclass
from typing import Literal

from agents import Agent, ModelSettings, Runner, set_tracing_disabled
from pydantic import BaseModel, Field, model_validator

from app.core.config import get_settings
from app.modules.investigations.provider_errors import (
    FailureCategory,
    classify_provider_error,
    is_retryable,
    retry_after_seconds,
)
from app.modules.investigations.triage import ClaimType
from app.modules.investigations.usage import (
    ModelCallBudget,
    ModelCallBudgetExceeded,
    complete_model_call,
    fail_model_call,
)

logger = logging.getLogger(__name__)


class PlannedClaim(BaseModel):
    text: str = Field(min_length=5, max_length=2000)
    normalized_text: str = Field(min_length=5, max_length=2000)
    claim_type: ClaimType
    needs_deep_investigation: bool

    @model_validator(mode="after")
    def enforce_investigation_depth(self) -> "PlannedClaim":
        self.needs_deep_investigation = self.claim_type != "SETTLED_FACT"
        return self


class PlannedQuery(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    freshness: Literal["CURRENT", "HISTORICAL", "BALANCED"] = "BALANCED"
    claim_index: int = Field(default=0, ge=0, le=2)
    topic: str = Field(default="general", min_length=1, max_length=80)
    jurisdiction: list[str] = Field(default_factory=list, max_length=5)
    source_lane: Literal["PRIMARY", "REFERENCE_REPORTING", "FACT_CHECK", "SOCIAL"] = "PRIMARY"
    widening_reason: str = Field(default="", max_length=240)


class ResearchPlan(BaseModel):
    claims: list[PlannedClaim] = Field(default_factory=list, max_length=3)
    queries: list[PlannedQuery | str] = Field(default_factory=list, max_length=5)
    clarification_question: str | None = Field(default=None, max_length=300)


class EvidenceAssessment(BaseModel):
    evidence_id: str
    relationship: Literal["SUPPORTS", "CONTRADICTS", "CONTEXTUALIZES", "MENTIONS", "UNKNOWN"]


class ExplanationSentence(BaseModel):
    sentence: str = Field(min_length=1, max_length=700)
    evidence_ids: list[str] = Field(min_length=1, max_length=10)


class ReasonedFinding(BaseModel):
    claim_id: str
    status: Literal[
        "SUPPORTED",
        "CONTRADICTED",
        "PARTLY_TRUE",
        "INSUFFICIENT_EVIDENCE",
        "NOT_VERIFIABLE",
    ]
    statement: str = Field(min_length=1, max_length=700)
    evidence_confidence: Literal["HIGH", "MEDIUM", "LOW"]
    confidence_rationale: str = Field(min_length=1, max_length=400)
    explanation: list[ExplanationSentence] = Field(default_factory=list, max_length=12)
    evidence: list[EvidenceAssessment] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=10)
    next_steps: list[str] = Field(default_factory=list, max_length=5)


class EvidenceReasoning(BaseModel):
    findings: list[ReasonedFinding] = Field(default_factory=list, max_length=3)


class ImageQuestionAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=700)


class VisualObservation(BaseModel):
    observation: str = Field(min_length=1, max_length=300)
    confidence: Literal["LOW", "MODERATE", "HIGH"]
    relevance: str = Field(min_length=1, max_length=200)
    limitations: list[str] = Field(default_factory=list, max_length=5)


class VisualAnalysis(BaseModel):
    observations: list[VisualObservation] = Field(default_factory=list, max_length=12)


class ModelInvocationFailed(RuntimeError):
    def __init__(self, *, provider: str, model: str, category: FailureCategory) -> None:
        self.provider = provider
        self.model = model
        self.category = category
        super().__init__(category.value)


@dataclass(frozen=True)
class ModelRun:
    output: ResearchPlan | EvidenceReasoning | VisualAnalysis
    provider: str
    model: str


class ModelGateway:
    """Thin OpenAI gateway for explicit, bounded model tasks."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def extract_claims_and_queries(
        self,
        *,
        text: str,
        images: list[tuple[str, bytes]],
        session,
        investigation_id,
    ) -> ModelRun:
        instructions = (
            "Triage the user's request into at most three atomic claim records. Every claim must "
            "include claim_type from SETTLED_FACT, CHECKABLE_EVENT, STATISTICAL, MEDIA_CLAIM, "
            "CONTESTED, or OPINION_OR_PREDICTION, and needs_deep_investigation. Use "
            "OPINION_OR_PREDICTION for opinions and predictions; never invent a factual verdict "
            "for them. SETTLED_FACT is limited to common knowledge, definitions, or stable facts "
            "that can be checked with a relevant authoritative reference. Other factual claims "
            "require deep investigation. Normalize each claim to one proposition. "
            "Turn the user's request into at most three independently verifiable factual claims. "
            "A clear factual question is a request to check its underlying proposition: rewrite it "
            "as a short declarative claim while preserving the named people or institutions, "
            "action, place, and time. Example: 'Did the ministry announce X yesterday?' becomes "
            "'The ministry announced X on [the normalized date]'. Do not return the question itself "
            "as a claim. Split compound requests only when each proposition can be checked alone. "
            "If a necessary subject, event, place, or time is missing or ambiguous, do not guess: "
            "return no claims and provide one concise clarification_question naming the missing "
            "detail. Retain opinions/predictions as OPINION_OR_PREDICTION claims and do not plan "
            "searches for them; explain why they cannot be verified and suggest a factual "
            "reformulation when useful. If no proposition can be assessed, return no claims and "
            "ask for clarification. "
            "When image or video frames are attached, use visible text or context only to form a "
            "narrowly scoped checkable claim; do not infer event truth, identity, origin, or "
            "manipulation from appearance. "
            "The prompt may include an application-supplied receipt timestamp and deterministic "
            "relative-date normalization; treat those lines as temporal context, not submitted claims. "
            "Return concise claims and at most five focused search-query objects. Do not create "
            "queries for OPINION_OR_PREDICTION claims. Each query "
            "must include text, claim_index (zero-based index into the claims array), freshness, "
            "topic, jurisdiction, source_lane, and widening_reason. "
            "Use topic and jurisdiction labels, not invented trusted-domain lists. Route lanes are "
            "PRIMARY for original records and topic-authoritative institutions, "
            "REFERENCE_REPORTING for established references and independent reporting, "
            "FACT_CHECK only for prior published fact-check discovery, and SOCIAL only when the "
            "claim is about a social post/account, circulation, or a firsthand social report. "
            "Start with PRIMARY. Widen to REFERENCE_REPORTING only to corroborate or fill a "
            "specific primary-source gap; use FACT_CHECK as context and follow it back to its "
            "sources. Do not plan SOCIAL for ordinary factual claims. Explain the gap/trigger in "
            "widening_reason. Classify each query as CURRENT when the claim is time-sensitive, "
            "ongoing, asks about latest/current/recent state, or refers to a recent event whose "
            "status should be checked against current reporting. Use HISTORICAL only when the "
            "request is confined to a past period or settled historical record. Use BALANCED when "
            "both the original period and later/current context matter. For CURRENT queries, seek "
            "the latest available reports and updates; for HISTORICAL queries, preserve the "
            "requested period and seek original records; for BALANCED, seek both. Search queries "
            "should seek "
            "primary/official records first, then original sources, independent reporting, "
            "established fact-checks, and public records. When input marks a SUBMITTED SOURCE, "
            "extract what it claims but do not treat that article as independent proof. "
            "Anchor relative dates such as today, yesterday, and last week to the supplied "
            "investigation receipt timestamp (UTC). Normalize the date in the claim/query and "
            "carry that date into the user-facing answer. The submitter's timezone is unknown; "
            "when local-time ambiguity could change the date or conclusion, state that limitation "
            "and ask for the intended timezone instead of guessing. For current-event claims, "
            "plan separate CURRENT coverage and HISTORICAL context queries when the budget allows. "
            "Do not treat old coverage as evidence of current status. Do not assess truth or invent details. "
            "Each returned claim must be specific enough that a source passage could support or "
            "contradict it. If no such claim can be responsibly stated, return empty claims and "
            "queries plus a useful clarification_question."
        )
        return asyncio.run(
            self._structured_call(
                purpose="CLAIM_EXTRACTION",
                instructions=instructions,
                prompt=text[: self.settings.max_model_input_chars],
                images=images,
                output_type=ResearchPlan,
                max_tokens=self.settings.max_model_output_tokens_research,
                session=session,
                investigation_id=investigation_id,
            )
        )

    def reason_about_evidence(
        self,
        *,
        evidence_packet: str,
        session,
        investigation_id,
        timeout_seconds: float | None = None,
    ) -> ModelRun:
        instructions = (
            "Assess each supplied claim using only the supplied packet. Return exactly one verdict "
            "from SUPPORTED, CONTRADICTED, PARTLY_TRUE, INSUFFICIENT_EVIDENCE, or "
            "NOT_VERIFIABLE; keep verdict separate from HIGH, MEDIUM, or LOW evidence confidence. "
            "Provide one confidence sentence tied to source count, quality, independence, and recency. "
            "Distinguish retrieved "
            "evidence excerpts from source-candidate and retrieval context; only eligible cited "
            "evidence may support or contradict a claim. Return one finding per claim. Cite "
            "packet evidence IDs and assign a relationship to each. "
            "SUPPORTED requires relevant support from at least two independent eligible sources, "
            "or one primary/authoritative source for SETTLED_FACT. CONTRADICTED requires the same "
            "threshold of contradicting evidence. PARTLY_TRUE requires material mixed evidence or "
            "distinct senses with different answers; state each sense plainly. Use "
            "For example, for 'a tomato is a vegetable/fruit', distinguish botanical fruit "
            "classification from culinary vegetable usage and return PARTLY_TRUE when the "
            "packet supports both meanings. "
            "INSUFFICIENT_EVIDENCE when evidence does not meet the threshold. Use NOT_VERIFIABLE "
            "for opinions/predictions or propositions not checkable as framed. Preserve conflicts. "
            "For each finding, draft a direct, plain-language answer for the person who asked as "
            "an explanation array of sentences, each with one or more evidence_ids from the packet. "
            "Every factual sentence must cite evidence that directly supports that sentence. Do not "
            "put uncited assertions in the explanation. "
            "Do not use any candidate ID or any evidence ID not supplied in the packet. "
            "For each finding, draft a direct, plain-language answer for the person who asked: "
            "state what the evidence does and does not establish, and name the most relevant "
            "finding or source detail when the packet supports it. This statement is user-facing. "
            "When a claim contains a relative date, use the packet's investigation receipt time "
            "and temporal policy to state its normalized calendar date; disclose the unknown "
            "submitter timezone if it could change the interpretation. Never say there is no "
            "reference date when the packet supplies the receipt time. "
            "Also assess evidence_confidence as LOW, MEDIUM, or HIGH for the strength and "
            "coverage of the evidence packet, not the probability that the claim is true. LOW "
            "means sparse, indirect, conflicting, or weakly matched evidence; MEDIUM means "
            "relevant traceable evidence but material gaps or limited corroboration; HIGH requires "
            "multiple relevant, independent, authoritative sources with no material conflict. "
            "Provide a short confidence_rationale grounded in source quality, independence, "
            "relevance, and disagreement. When evidence is absent, still give a useful, specific "
            "answer: say what the search and retrieval found, what could not be assessed, "
            "and the most useful next step. Do not turn source candidates or search-result titles "
            "into evidence. Never use HIGH when the claim is INSUFFICIENT_EVIDENCE or "
            "NOT_VERIFIABLE. This is a qualitative, uncalibrated evidence-strength judgment, not a "
            "numeric score or probability. Do not assert specifics absent from the packet. "
            "Treat SUBMITTED sources as context, not proof. Consider source type, claim-specific "
            "authority scope, and recorded CITES/DUPLICATES relationships; do not count duplicate "
            "or derivative publications as independent corroboration. Absence of a located "
            "official source does not prove a claim false. "
            "Media rules: metadata is editable and cannot establish origin, event time, or "
            "manipulation. C2PA VALID means local credentials validated, not that depicted events "
            "are true; NOT_PRESENT does not imply AI generation. AI statements must say the "
            "credentials declare AI involvement. Visual descriptions are fallible observations, "
            "not forensic proof; appearance alone cannot establish manipulation or "
            "synthetic origin. "
            "Use concise statements and short next steps. Do not invent sources, evidence, or IDs."
        )
        return asyncio.run(
            self._structured_call(
                purpose="EVIDENCE_REASONING",
                instructions=instructions,
                prompt=evidence_packet[: self.settings.max_total_evidence_chars + 8_000],
                images=[],
                output_type=EvidenceReasoning,
                max_tokens=self.settings.max_model_output_tokens_synthesis,
                session=session,
                investigation_id=investigation_id,
                timeout_seconds=timeout_seconds,
            )
        )

    def analyze_visual_content(
        self, *, images: list[tuple[str, bytes]], claim_text: str, session, investigation_id
    ) -> ModelRun:
        instructions = (
            "Describe only visible, claim-relevant observations in this image or sampled video frame. This is not AI, "
            "deepfake, authenticity, truth, or forensic detection. Do not identify people. "
            "Return at most twelve structured observations with uncertainty and limitations. "
            "Do not infer image origin, event truth, manipulation, or synthetic generation "
            "from appearance."
        )

        return asyncio.run(
            self._structured_call(
                purpose="MEDIA_VISUAL_ANALYSIS",
                instructions=instructions,
                prompt=(
                    "Submitted claim: "
                    + claim_text[:2000]
                    + "\nReport visible text, objects, scene, signage, dates, layout, or apparent "
                    "anomalies only where relevant."
                ),
                images=images[:4],
                output_type=VisualAnalysis,
                max_tokens=min(700, self.settings.max_model_output_tokens_research),
                session=session,
                investigation_id=investigation_id,
            )
        )

    def answer_image_origin_question(self, *, question: str, signals: str, session, investigation_id) -> ModelRun:
        instructions = (
            "Answer the user's image-origin question using only the supplied recorded checks. "
            "Be direct, plain-language, and specific to the actual results. Do not infer AI "
            "generation, authenticity, manipulation, or event truth from appearance or metadata. "
            "A C2PA declaration can be reported as an attached declaration, not independent proof. "
            "Distinguish unavailable/failed checks from checks that found no credentials. State "
            "when the result cannot determine origin and give one useful next step. Do not invent "
            "checks or sources."
        )
        return asyncio.run(
            self._structured_call(
                purpose="IMAGE_ORIGIN_RESPONSE",
                instructions=instructions,
                prompt=f"User question: {question[:1000]}\nRecorded image checks:\n{signals[:4000]}",
                images=[],
                output_type=ImageQuestionAnswer,
                max_tokens=min(450, self.settings.max_model_output_tokens_synthesis),
                session=session,
                investigation_id=investigation_id,
            )
        )

    async def _structured_call(
        self,
        *,
        purpose: str,
        instructions: str,
        prompt: str,
        images: list[tuple[str, bytes]],
        output_type: type[BaseModel],
        max_tokens: int,
        session,
        investigation_id,
        timeout_seconds: float | None = None,
    ) -> ModelRun:
        provider = "openai"
        api_key = (
            self.settings.openai_api_key.get_secret_value().strip()
            if self.settings.openai_api_key
            else ""
        )
        model_name = self.settings.openai_model
        if not api_key:
            raise ModelInvocationFailed(
                provider=provider,
                model=model_name,
                category=FailureCategory.AUTHENTICATION_FAILED,
            )
        from agents import OpenAIResponsesModel
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=api_key,
            max_retries=0,
            timeout=min(
                self.settings.model_request_timeout_seconds,
                max(0.1, timeout_seconds) if timeout_seconds is not None else self.settings.model_request_timeout_seconds,
            ),
        )
        content: list[dict[str, object]] = [{"type": "input_text", "text": prompt}]
        for mime_type, data in images:
            encoded = base64.b64encode(data).decode("ascii")
            content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:{mime_type};base64,{encoded}",
                    "detail": "low",
                }
            )
        model = OpenAIResponsesModel(
            model=model_name,
            openai_client=client,
        )
        agent = Agent(
            name=f"Agent 0 {purpose.replace('_', ' ').title()}",
            model=model,
            instructions=instructions,
            output_type=output_type,
            model_settings=ModelSettings(
                max_tokens=max_tokens,
                reasoning={"effort": self.settings.openai_reasoning_effort},
            ),
        )
        set_tracing_disabled(True)
        retry_count = 0
        schema_retry_count = 0
        budget = ModelCallBudget(session, investigation_id)
        try:
            while True:
                record = budget.begin(provider=provider, model=model_name, purpose=purpose)
                try:
                    result = await Runner.run(
                        agent,
                        [{"role": "user", "content": content}],
                        max_turns=1,
                    )
                    if not isinstance(result.final_output, output_type):
                        raise ModelInvocationFailed(
                            provider=provider,
                            model=model_name,
                            category=FailureCategory.INVALID_MODEL_OUTPUT,
                        )
                    complete_model_call(session, record, list(result.raw_responses or []))
                    return ModelRun(output=result.final_output, provider=provider, model=model_name)
                except ModelCallBudgetExceeded:
                    raise
                except Exception as error:
                    category = (
                        error.category
                        if isinstance(error, ModelInvocationFailed)
                        else classify_provider_error(error)
                    )
                    status_code = getattr(error, "status_code", None)
                    request_id = getattr(error, "request_id", None)
                    fail_model_call(
                        session,
                        record,
                        category.value,
                        http_status=status_code if isinstance(status_code, int) else None,
                        request_id=request_id if isinstance(request_id, str) else None,
                        retryable=is_retryable(category),
                        raw_responses=[getattr(error, "response", None)]
                        if getattr(error, "response", None) is not None
                        else None,
                    )
                    logger.warning(
                        "Model invocation failed provider=%s model=%s purpose=%s "
                        "category=%s status=%s request_id=%s",
                        provider,
                        model_name,
                        purpose,
                        category.value,
                        getattr(error, "status_code", None),
                        getattr(error, "request_id", None),
                    )
                    schema_retry = category == FailureCategory.INVALID_MODEL_OUTPUT and schema_retry_count < 1
                    if not schema_retry and (
                        not is_retryable(category)
                        or retry_count >= self.settings.max_provider_retries
                    ):
                        raise ModelInvocationFailed(
                            provider=provider,
                            model=model_name,
                            category=category,
                        ) from error
                    if schema_retry:
                        schema_retry_count += 1
                        delay = 0
                    elif category == FailureCategory.RATE_LIMITED:
                        delay = retry_after_seconds(error)
                        if delay is None or delay > self.settings.max_retry_after_seconds:
                            raise ModelInvocationFailed(
                                provider=provider,
                                model=model_name,
                                category=category,
                            ) from error
                    else:
                        delay = min(0.5 * (2**retry_count), self.settings.max_retry_after_seconds)
                    retry_count += 1
                    if delay:
                        await asyncio.sleep(delay)
        finally:
            await client.close()
