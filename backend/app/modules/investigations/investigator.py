"""Single-call structured model tasks; application code controls research progression."""

import asyncio
import base64
import logging
from dataclasses import dataclass
from typing import Literal

from agents import Agent, ModelSettings, Runner, set_tracing_disabled
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.modules.investigations.provider_errors import (
    FailureCategory,
    classify_provider_error,
    is_retryable,
    retry_after_seconds,
)
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
    claim_type: str = Field(default="GENERAL", max_length=40)


class PlannedQuery(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    freshness: Literal["CURRENT", "HISTORICAL", "BALANCED"] = "BALANCED"


class ResearchPlan(BaseModel):
    claims: list[PlannedClaim] = Field(default_factory=list, max_length=3)
    queries: list[PlannedQuery | str] = Field(default_factory=list, max_length=5)


class EvidenceAssessment(BaseModel):
    evidence_id: str
    relationship: Literal["SUPPORTS", "CONTRADICTS", "CONTEXTUALIZES", "MENTIONS", "UNKNOWN"]


class ReasonedFinding(BaseModel):
    claim_id: str
    status: Literal["SUPPORTED", "CONTRADICTED", "UNVERIFIED", "INCONCLUSIVE"]
    statement: str = Field(min_length=1, max_length=700)
    evidence_confidence: Literal["UNASSESSED", "LOW", "MODERATE", "HIGH"] = "UNASSESSED"
    confidence_rationale: str = Field(
        default="The reasoning model did not provide a confidence assessment.", max_length=400
    )
    evidence: list[EvidenceAssessment] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=10)
    next_steps: list[str] = Field(default_factory=list, max_length=5)


class EvidenceReasoning(BaseModel):
    findings: list[ReasonedFinding] = Field(default_factory=list, max_length=3)


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
            "Extract at most three independently verifiable factual claims from this submission. "
            "Return concise claims and at most five focused search-query objects, each with text "
            "and freshness. Classify each query as CURRENT when the claim is time-sensitive, "
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
            "Do not assess truth or invent details. "
            "If the submission contains no factual claim, return empty arrays."
        )
        return asyncio.run(
            self._structured_call(
                purpose="CLAIM_EXTRACTION",
                instructions=instructions,
                prompt=text[: self.settings.max_model_input_chars],
                images=[],
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
    ) -> ModelRun:
        instructions = (
            "Assess each supplied claim using only the supplied packet. Distinguish retrieved "
            "evidence excerpts from source-candidate and retrieval context; only eligible cited "
            "evidence may support or contradict a claim. Return one finding per claim. Cite "
            "packet evidence IDs and assign a relationship to each. "
            "SUPPORTED requires supporting evidence; CONTRADICTED requires contradicting evidence. "
            "Use UNVERIFIED when the packet has no retrieved, claim-linked evidence or has only "
            "unreviewed source candidates. Use INCONCLUSIVE when retrieved evidence materially "
            "conflicts or cannot be reconciled. Preserve disagreement and limitations. "
            "For each finding, draft a direct, plain-language answer for the person who asked: "
            "state what the evidence does and does not establish, and name the most relevant "
            "finding or source detail when the packet supports it. This statement is user-facing. "
            "Also assess evidence_confidence as LOW, MODERATE, or HIGH for the strength and "
            "coverage of the evidence packet, not the probability that the claim is true. LOW "
            "means sparse, indirect, conflicting, or weakly matched evidence; MODERATE means "
            "relevant traceable evidence but material gaps or limited corroboration; HIGH requires "
            "multiple relevant, independent, authoritative sources with no material conflict. "
            "Provide a short confidence_rationale grounded in source quality, independence, "
            "relevance, and disagreement. When evidence is absent, still give a useful, specific "
            "answer: say what the search and retrieval found, what could not be assessed, "
            "and the most useful next step. Do not turn source candidates or search-result titles "
            "into evidence. Never use HIGH when the claim is UNVERIFIED or "
            "INCONCLUSIVE. This is a qualitative, uncalibrated evidence-strength judgment, not a "
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
            )
        )

    def analyze_visual_content(
        self, *, image: tuple[str, bytes], claim_text: str, session, investigation_id
    ) -> ModelRun:
        instructions = (
            "Describe only visible, claim-relevant observations in this image. This is not AI, "
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
                images=[image],
                output_type=VisualAnalysis,
                max_tokens=min(700, self.settings.max_model_output_tokens_research),
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
            timeout=self.settings.model_request_timeout_seconds,
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
                    if (
                        not is_retryable(category)
                        or retry_count >= self.settings.max_provider_retries
                    ):
                        raise ModelInvocationFailed(
                            provider=provider,
                            model=model_name,
                            category=category,
                        ) from error
                    if category == FailureCategory.RATE_LIMITED:
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
