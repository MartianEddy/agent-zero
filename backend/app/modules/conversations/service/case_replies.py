"""Replies about saved cases: results, status, history, retries and quick answers."""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.investigation import Channel, InvestigationStatus
from app.modules.conversations import messages as copy
from app.modules.conversations.service import common, ports
from app.modules.investigations.evidence_ledger import owner_key
from app.modules.investigations.models import (
    Claim,
    Evidence,
    Finding,
    FindingEvidence,
    Investigation,
    InvestigationUsage,
    ProcessingJob,
    Source,
    Submission,
    VerificationBrief,
)
from app.modules.investigations.service import (
    InvestigationRetryUnavailable,
    is_retryable_failure_code,
)
from app.modules.investigations.usage import ModelCallBudgetExceeded
from app.modules.sources.registry import SUFFIX_ENTRIES, lookup_source


def _retrieved_sources(session: Session, *, investigation_id: UUID, limit: int = 3) -> list[Source]:
    return list(
        session.scalars(
            select(Source)
            .where(
                Source.investigation_id == investigation_id,
                Source.retrieval_status == "RETRIEVED",
            )
            .order_by(Source.retrieved_at.desc().nullslast(), Source.id)
            .limit(limit)
        )
    )


def _source_pairs(sources: list[Source]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for source in sources:
        label = (source.title or source.publisher or source.domain or "Retrieved source").strip()
        label = " ".join(label.split())[:100]
        url = source.canonical_url or source.url
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            continue
        safe_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if len(safe_url) <= 350:
            pairs.append((label, safe_url))
    return pairs


def _source_bullets(sources: list[Source]) -> str:
    return "\n".join(f"• {label}: {url}" for label, url in _source_pairs(sources))


_TRACKING_PARAMS = re.compile(r"^(utm_|c_correlation_id|c_tenant_id|fbclid|gclid|mc_|ref$|ref_src)")
_INLINE_LINK = re.compile(r"\s*\(?\[[^\]]{1,120}\]\(https?://[^)\s]+\)\)?")


def _clean_url(url: str) -> str:
    """Drop tracking parameters such as utm_source from a citation link."""
    parts = urlsplit(url)
    query = "&".join(
        pair for pair in parts.query.split("&")
        if pair and not _TRACKING_PARAMS.match(pair.split("=", 1)[0])
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def _factual_answer_message(answer: str, citations: tuple[dict[str, str], ...]) -> str:
    clean_citations: list[tuple[str, str]] = []
    seen: set[str] = set()
    for citation in citations:
        url = citation.get("url", "").strip()
        title = " ".join(citation.get("title", "").split())[:100]
        try:
            parsed = urlsplit(url)
        except ValueError:
            continue
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or url in seen
        ):
            continue
        url = _clean_url(url)
        if url in seen:
            continue
        seen.add(url)
        clean_citations.append((title or parsed.hostname, url))
        if len(clean_citations) >= 3:
            break

    # Sources are listed separately, so drop inline markdown links the model may add.
    text = _INLINE_LINK.sub("", " ".join(answer.split())).strip()[:1400]
    if not text or not clean_citations:
        return (
            "I couldn’t find a source for a reliable quick answer, so I won’t guess. "
            "Reply *CHECK* and I’ll run a full check instead."
        )
    header = "Quick answer from a fresh web search (not a full investigation):\n\n"
    source_header = "\n\nSources:\n"
    footer = "\n\nReply *CHECK* for a full check that compares sources."
    source_lines: list[str] = []
    for title, url in clean_citations:
        line = f"• {title}: {url}"
        candidate = header + text + source_header + "\n".join([*source_lines, line]) + footer
        if len(candidate) <= 3900:
            source_lines.append(line)
    if not source_lines:
        return (
            "I couldn’t fit a source into a reliable quick answer, so I won’t guess. "
            "Reply *CHECK* and I’ll run a full check instead."
        )
    return header + text + source_header + "\n".join(source_lines) + footer


def _with_reference(message: str, reference: str) -> str:
    suffix = f"\n\nReference: {reference}"
    return message[: 3900 - len(suffix)].rstrip() + suffix


def _retry_available(session: Session, investigation: Investigation) -> bool:
    job = session.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.investigation_id == investigation.id)
        .order_by(ProcessingJob.created_at.desc())
    )
    if (
        investigation.status not in {InvestigationStatus.NEEDS_REVIEW, InvestigationStatus.FAILED}
        or job is None
        or job.status in {"QUEUED", "RUNNING"}
        or not is_retryable_failure_code(job.error_code)
    ):
        return False
    usage = session.scalar(
        select(InvestigationUsage).where(InvestigationUsage.investigation_id == investigation.id)
    )
    return (
        usage is None or usage.model_calls < ports.get_settings().max_model_calls_per_investigation
    )


def _model_unavailable_reply(error: Exception) -> str:
    if isinstance(error, ModelCallBudgetExceeded):
        if error.reset_at is not None:
            local_reset = error.reset_at.astimezone(ZoneInfo("Africa/Nairobi"))
            reset_label = local_reset.strftime("%-I:%M %p EAT on %a, %b %-d")
            return (
                "I’ve hit my chat limit for now. I’ll be back at "
                f"{reset_label}. I got your message, but nothing was started."
            )
        return (
            "I’ve hit my chat limit for now. I got your message, but nothing was started. "
            "Please try again later."
        )
    return (
        "Sorry, I’m having trouble right now and couldn’t answer. Nothing was started. "
        "Please try again in a few minutes."
    )


def _find_case(
    session: Session,
    *,
    settings,
    sender_ref: str,
    reference: str | None,
    conversation_id: UUID | None = None,
) -> Investigation | None:
    """The sender's case with this reference, or their latest case; never anyone else's."""
    reference = reference.upper() if reference else None
    statement = (
        select(Investigation)
        .join(Submission, Submission.investigation_id == Investigation.id)
        .where(
            Investigation.owner_id == common._owner_id(settings),
            Investigation.channel == Channel.WHATSAPP,
            Submission.channel == Channel.WHATSAPP,
            Submission.source_metadata["sender_ref"].as_string() == sender_ref,
        )
    )
    if reference is not None:
        statement = statement.where(Investigation.reference == reference)
    else:
        statement = statement.order_by(Investigation.created_at.desc()).limit(1)
    investigation = session.scalar(statement)
    if investigation is None and conversation_id is not None:
        # A persisted case is also bound to the conversation that approved it.
        # Use that durable relation if legacy or malformed submission metadata
        # omitted the sender HMAC; keep owner, channel, and exact reference scope.
        conversation_statement = (
            select(Investigation)
            .join(Submission, Submission.investigation_id == Investigation.id)
            .where(
                Investigation.owner_id == common._owner_id(settings),
                Investigation.channel == Channel.WHATSAPP,
                Submission.channel == Channel.WHATSAPP,
                Submission.source_metadata["conversation_id"].as_string() == str(conversation_id),
            )
        )
        if reference is not None:
            conversation_statement = conversation_statement.where(
                Investigation.reference == reference
            )
        else:
            conversation_statement = conversation_statement.order_by(
                Investigation.created_at.desc()
            ).limit(1)
        investigation = session.scalar(conversation_statement)
    return investigation


def _result_message(
    session: Session,
    *,
    settings,
    sender_ref: str,
    reference: str | None,
    conversation_id: UUID | None = None,
) -> str:
    investigation = _find_case(
        session,
        settings=settings,
        sender_ref=sender_ref,
        reference=reference,
        conversation_id=conversation_id,
    )
    if investigation is None:
        return copy.no_check_found()

    brief = session.scalar(
        select(VerificationBrief).where(VerificationBrief.investigation_id == investigation.id)
    )
    if brief is None:
        job = session.scalar(
            select(ProcessingJob)
            .where(ProcessingJob.investigation_id == investigation.id)
            .order_by(ProcessingJob.created_at.desc())
        )
        in_progress = investigation.status not in {
            InvestigationStatus.FAILED,
            InvestigationStatus.CANCELLED,
            InvestigationStatus.NEEDS_REVIEW,
            InvestigationStatus.COMPLETE,
        }
        if in_progress:
            return copy.status_message(
                getattr(investigation, "current_stage", None),
                investigation.status.value,
                investigation.reference,
                queued_retry=False,
            )
        if investigation.status == InvestigationStatus.CANCELLED:
            return copy.fit("*This check was cancelled.*", investigation.reference)
        if investigation.status == InvestigationStatus.COMPLETE:
            return copy.fit(
                "*This check finished without a saved summary.* No conclusion is "
                "available. Please try again or contact support.",
                investigation.reference,
            )
        claims = list(
            session.scalars(
                select(Claim)
                .where(Claim.investigation_id == investigation.id)
                .order_by(Claim.created_at)
                .limit(3)
            )
        )
        category = job.error_code if job is not None else None
        retrieved = _retrieved_sources(session, investigation_id=investigation.id)
        if _retry_available(session, investigation):
            retry_line = (
                "To try again without resending the claim, reply "
                f"*RETRY {investigation.reference}*."
            )
        else:
            retry_line = (
                "A retry isn’t available right now. Keep the reference below if you "
                "contact support."
            )
        return copy.fit(
            copy.failed_without_summary(
                claims=[claim.text for claim in claims],
                reason=copy.failure_reason(category),
                sources=_source_bullets(retrieved),
                retry_line=retry_line,
            ),
            investigation.reference,
        )

    findings = list(
        session.scalars(
            select(Finding)
            .where(Finding.investigation_id == investigation.id)
            .order_by(Finding.created_at)
            .limit(5)
        )
    )
    stopped_early = investigation.status in {
        InvestigationStatus.NEEDS_REVIEW,
        InvestigationStatus.FAILED,
    }
    stopped_reason = None
    retry_hint = None
    if stopped_early:
        latest_job = session.scalar(
            select(ProcessingJob)
            .where(ProcessingJob.investigation_id == investigation.id)
            .order_by(ProcessingJob.created_at.desc())
        )
        stopped_reason = copy.failure_reason(latest_job.error_code if latest_job else None)
        if _retry_available(session, investigation):
            retry_hint = f"Reply *RETRY {investigation.reference}* to try again."
    claims_by_id = {
        claim.id: claim.text
        for claim in session.scalars(
            select(Claim).where(Claim.investigation_id == investigation.id)
        )
    }
    return copy.result_message(
        [
            copy.FindingView(
                status=item.status,
                claim=claims_by_id.get(item.claim_id, ""),
                headline=_plain_why(item),
                confidence=item.evidence_confidence,
                confidence_reason=item.confidence_rationale or "",
            )
            for item in findings
        ],
        source_names=[name for name, _source, _passage in _decisive_sources(session, findings)],
        reference=investigation.reference,
        stopped_early=stopped_early,
        stopped_reason=stopped_reason,
        retry_hint=retry_hint,
    )


# Words from the verdict rules that mean nothing to someone reading a result.
_INTERNAL_WORDING = re.compile(
    r"threshold|source group|independen\w* group|corroboration requirement|eligible|"
    r"finding|verdict|excerpt|retrieved evidence|sufficiency",
    re.IGNORECASE,
)


def _plain_why(finding: Finding) -> str:
    """One or two plain sentences on what the sources say, from the cited explanation."""
    sentences = [
        str(item.get("sentence") or "").strip()
        for item in (finding.explanation_json or [])
        if isinstance(item, dict)
    ]
    plain = [sentence for sentence in sentences if sentence and not _INTERNAL_WORDING.search(sentence)]
    why = " ".join(plain[:2])
    fallback = copy.PLAIN_REASONS.get(finding.status, "")
    if finding.status == "INSUFFICIENT_EVIDENCE":
        return f"{why} {fallback}".strip() if why else fallback
    return why or fallback


def _source_name(source: Source) -> str:
    domain = (source.domain or "").removeprefix("www.")
    entry = lookup_source(domain) if domain else None
    if entry is not None and entry.domain not in SUFFIX_ENTRIES:
        return entry.name
    if (source.publisher or "") in {"Wikipedia", "Wikidata"}:
        return source.publisher
    return domain or "Source"


def _decisive_sources(
    session: Session, findings: list[Finding], *, limit: int = 3
) -> list[tuple[str, Source, str]]:
    """Distinct retrieved sources behind the findings: deciding passages first."""
    if not findings:
        return []
    rows = session.execute(
        select(Evidence, Source)
        .join(FindingEvidence, FindingEvidence.evidence_id == Evidence.id)
        .join(Source, Source.id == Evidence.source_id)
        .where(
            FindingEvidence.finding_id.in_([item.id for item in findings]),
            Source.retrieval_status == "RETRIEVED",
        )
    ).all()
    decided = {"SUPPORTS": 0, "CONTRADICTS": 0}
    rows.sort(key=lambda row: (decided.get(row[0].stance or "", 1), str(row[1].id)))
    picked: list[tuple[str, Source, str]] = []
    seen: set[str] = set()
    for evidence, source in rows:
        owner = owner_key(source.domain) or str(source.id)
        if owner in seen:
            continue
        seen.add(owner)
        picked.append((_source_name(source), source, evidence.content or ""))
        if len(picked) >= limit:
            break
    return picked


def _completed_case(
    session: Session, *, settings, sender_ref: str, reference: str | None
) -> tuple[Investigation, list[Finding]] | None:
    investigation = _find_case(
        session, settings=settings, sender_ref=sender_ref, reference=reference
    )
    if investigation is None:
        return None
    findings = list(
        session.scalars(
            select(Finding)
            .where(Finding.investigation_id == investigation.id)
            .order_by(Finding.created_at)
            .limit(5)
        )
    )
    return (investigation, findings) if findings else None


def _sources_message(session: Session, *, settings, sender_ref: str, reference: str | None) -> str:
    case = _completed_case(session, settings=settings, sender_ref=sender_ref, reference=reference)
    if case is None:
        return copy.no_result_yet()
    investigation, findings = case
    entries = []
    for name, source, passage in _decisive_sources(session, findings, limit=5):
        pairs = _source_pairs([source])
        if pairs:
            entries.append((name, pairs[0][1], passage))
    return copy.sources_message(entries, reference=investigation.reference)


def _share_message(session: Session, *, settings, sender_ref: str, reference: str | None) -> str:
    case = _completed_case(session, settings=settings, sender_ref=sender_ref, reference=reference)
    if case is None:
        return copy.no_result_yet()
    investigation, findings = case
    claims = {
        claim.id: claim.text
        for claim in session.scalars(
            select(Claim).where(Claim.investigation_id == investigation.id)
        )
    }
    return copy.share_card(
        [(claims.get(item.claim_id, ""), item.status, _plain_why(item)) for item in findings],
        source_names=[name for name, _source, _passage in _decisive_sources(session, findings)],
        reference=investigation.reference,
        whatsapp_number=getattr(settings, "whatsapp_public_number", None),
        site_url=str(settings.public_site_url) if getattr(settings, "public_site_url", None) else None,
    )


def _result_buttons(
    session: Session, *, settings, sender_ref: str, reference: str | None
) -> list[tuple[str, str]] | None:
    """Sources, Share and Check another, for a result with saved findings."""
    case = _completed_case(session, settings=settings, sender_ref=sender_ref, reference=reference)
    if case is None:
        return None
    return copy.result_buttons(case[0].reference)


def _retry_message(
    session: Session,
    *,
    settings,
    sender_ref: str,
    reference: str | None,
) -> str:
    reference = reference.upper() if reference else None
    if reference is None:
        return "To avoid retrying the wrong check, send RETRY followed by its case reference."
    statement = (
        select(Investigation)
        .join(Submission, Submission.investigation_id == Investigation.id)
        .where(
            Investigation.owner_id == common._owner_id(settings),
            Investigation.channel == Channel.WHATSAPP,
            Submission.channel == Channel.WHATSAPP,
            Submission.source_metadata["sender_ref"].as_string() == sender_ref,
        )
    )
    statement = statement.where(Investigation.reference == reference)
    investigation = session.scalar(statement.with_for_update())
    if investigation is None:
        return copy.no_check_found()

    latest_job = session.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.investigation_id == investigation.id)
        .order_by(ProcessingJob.created_at.desc())
    )
    if latest_job is not None and not is_retryable_failure_code(latest_job.error_code):
        return copy.fit(
            "This kind of problem can’t be fixed by trying again. "
            "Send the claim again as a new check, or contact support.",
            investigation.reference,
        )

    try:
        ports.queue_investigation_retry(
            session,
            investigation=investigation,
            actor="whatsapp-user",
            max_model_calls=settings.max_model_calls_per_investigation,
        )
    except InvestigationRetryUnavailable as exc:
        messages = {
            "not_retryable": (
                "This check can’t be retried from here. Please send the claim again as a "
                "new check, or contact support."
            ),
            "job_missing": ("I couldn’t find a saved run to retry. Please send the claim again."),
            "already_running": ("A retry is already on its way. No need to send it again."),
            "budget_exhausted": (
                "This check has used up its allowance, so it can’t be retried right now."
            ),
        }
        return copy.fit(messages[exc.reason], investigation.reference)

    return copy.fit(
        "*I’m trying again with your saved claim.* No need to resend it.\n"
        "Reply *STATUS* to see how it’s going.",
        investigation.reference,
    )


def _latest_case(session: Session, *, settings, sender_ref: str) -> Investigation | None:
    return session.scalar(
        select(Investigation)
        .join(Submission, Submission.investigation_id == Investigation.id)
        .where(
            Investigation.owner_id == common._owner_id(settings),
            Investigation.channel == Channel.WHATSAPP,
            Submission.channel == Channel.WHATSAPP,
            Submission.source_metadata["sender_ref"].as_string() == sender_ref,
        )
        .order_by(Investigation.created_at.desc())
        .limit(1)
    )


def _status_message(session: Session, *, settings, sender_ref: str, reference: str | None) -> str:
    reference = reference.upper() if reference else None
    investigation = _latest_case(session, settings=settings, sender_ref=sender_ref)
    if reference:
        investigation = session.scalar(
            select(Investigation)
            .join(Submission, Submission.investigation_id == Investigation.id)
            .where(
                Investigation.owner_id == common._owner_id(settings),
                Investigation.channel == Channel.WHATSAPP,
                Investigation.reference == reference,
                Submission.channel == Channel.WHATSAPP,
                Submission.source_metadata["sender_ref"].as_string() == sender_ref,
            )
        )
    if investigation is None:
        return copy.no_check_found()
    latest_job = session.scalar(
        select(ProcessingJob)
        .where(ProcessingJob.investigation_id == investigation.id)
        .order_by(ProcessingJob.created_at.desc())
    )
    retry_hint = None
    if investigation.status in {InvestigationStatus.NEEDS_REVIEW, InvestigationStatus.FAILED}:
        if _retry_available(session, investigation):
            retry_hint = f"Reply *RETRY {investigation.reference}* to try again."
        else:
            retry_hint = "A retry isn’t available right now."
    return copy.status_message(
        getattr(investigation, "current_stage", None),
        investigation.status.value,
        investigation.reference,
        queued_retry=latest_job is not None
        and latest_job.status == "QUEUED"
        and investigation.status in {InvestigationStatus.NEEDS_REVIEW, InvestigationStatus.FAILED},
        retry_hint=retry_hint,
    )


def _case_list_message(session: Session, *, settings, sender_ref: str, page: int = 1) -> str:
    cases = list(
        session.scalars(
            select(Investigation)
            .join(Submission, Submission.investigation_id == Investigation.id)
            .where(
                Investigation.owner_id == common._owner_id(settings),
                Investigation.channel == Channel.WHATSAPP,
                Submission.channel == Channel.WHATSAPP,
                Submission.source_metadata["sender_ref"].as_string() == sender_ref,
            )
            .order_by(Investigation.created_at.desc(), Investigation.id.desc())
            .offset((page - 1) * 10)
            .limit(10)
        )
    )
    if not cases:
        if page > 1:
            return "There are no older checks. Reply *HISTORY* to see your newest ones."
        return "You haven’t asked me to check anything yet. Send me a claim or a link to start."
    rows = []
    for case in cases:
        claim = session.scalar(
            select(Claim.text)
            .where(Claim.investigation_id == case.id)
            .order_by(Claim.created_at)
            .limit(1)
        )
        rows.append((case.reference, copy.case_status_label(case.status.value), claim or ""))
    return copy.history_message(rows, page=page)
