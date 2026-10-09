"use client";

import Image from "next/image";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { WorkspaceHeader } from "@/components/WorkspaceHeader";
import { WHATSAPP_CONTACT_URL } from "@/lib/contact";
import {
  aiDeclarationCopy,
  findingEvidenceReferences,
  inferInputType,
  imageOriginAnswer,
  presentedLimitations,
  publicationDateLabel,
  provenancePresentation,
  progressStepForStage,
  recommendedNextSteps,
  relativeDateBasis,
  relationshipPresentation,
  safeEvidenceText,
  stagePresentation,
  sourceResearchLane,
  statusPresentation,
  technicalMetadata,
  unknownsFromResults,
  uploadErrorMessage,
  visualAnalysisNotice,
  visualObservations,
} from "./presentation.mjs";
import type { ClaimType, Evidence, Finding, Investigation, Results, Source, TriageClaim, TriagePreview } from "./types";
import styles from "./page.module.css";

type EvidenceFilter = "ALL" | "SUPPORTS" | "CONTRADICTS" | "CONTEXT";

const ACTIVE = new Set([
  "RECEIVED",
  "PROCESSING",
  "ANALYZING",
  "RESEARCHING",
  "CORROBORATING",
  "GENERATING_BRIEF",
]);

const EXAMPLES: { text: string; label: string }[] = [
  { text: "Nairobi is the capital of Kenya.", label: "Likely true" },
  { text: "The Great Wall of China is visible from the Moon with the naked eye.", label: "Likely false" },
  { text: "The COVID-19 pandemic began with a laboratory accident.", label: "Contested" },
];
const CLAIM_TYPES: ClaimType[] = ["SETTLED_FACT", "CHECKABLE_EVENT", "STATISTICAL", "MEDIA_CLAIM", "CONTESTED", "OPINION_OR_PREDICTION"];
const REVIEW_STEPS = ["Understand the question", "Search for sources", "Compare retrieved pages", "Prepare the result"];

async function readError(response: Response) {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body) {
      const detail = body.detail;
      return uploadErrorMessage(detail);
    }
    return "The request could not be completed. Try again.";
  } catch {
    return "The request could not be completed. Try again.";
  }
}

function formatBytes(value: number) {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function citationLabel(evidence: Evidence | undefined, fallback: number) {
  if (!evidence?.source?.url) return fallback;
  try {
    return new URL(evidence.source.url).hostname;
  } catch {
    return fallback;
  }
}

function sourceRoleLabel(role: string) {
  const labels: Record<string, string> = {
    PRIMARY: "Official or original source",
    AUTHORITATIVE: "Authoritative source",
    INDEPENDENT: "Independent reporting",
    DERIVATIVE: "Based on another source",
    SECONDARY: "Secondary source",
  };
  return labels[role] ?? "Source";
}

function findingRelationship(finding: Finding, evidence: Evidence[]) {
  const links = findingEvidenceReferences(finding, evidence);
  const byId = new Map(links.map((item) => [item.id, item]));
  return finding.evidence_ids.flatMap((id) => {
    const item = byId.get(id);
    if (!item) return [];
    const relationship = item.claim_links.find((link) => link.claim_id === finding.claim_id)?.relationship;
    return [{ item, relationship: relationship ?? "UNKNOWN" }];
  });
}

function EvidenceCard({ item, relationship, showSourceAction = true }: { item: Evidence; relationship?: string; showSourceAction?: boolean }) {
  const isMetadata = item.method === "MEDIA_TECHNICAL_METADATA" || item.method === "MEDIA_METADATA";
  const safeMetadata = isMetadata
    ? technicalMetadata(item.content)
    : [];
  const observations = item.method === "MEDIA_VISUAL_OBSERVATION"
    ? visualObservations(item.content)
    : [];
  const provenanceCopy = item.method === "MEDIA_PROVENANCE"
    ? provenancePresentation(item.provenance?.status)
    : null;
  return (
    <article className={styles.evidenceCard} id={`evidence-${item.id}`}>
      <div className={styles.evidenceCardHeader}>
        <span className={styles.evidenceFamily}>{item.source ? "Source evidence" : item.method === "MEDIA_PROVENANCE" ? "Origin & history" : item.method.includes("METADATA") ? "File details" : item.method === "MEDIA_VISUAL_OBSERVATION" ? "What Agent 0 can see" : "Evidence reviewed"}</span>
        {relationship && <span className={styles.relationship}>{relationshipPresentation(relationship)}</span>}
      </div>
      {isMetadata ? safeMetadata.length > 0 ? <dl className={styles.metadataList}>{safeMetadata.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl> : <p>No useful file details were available.</p>
        : item.method === "MEDIA_VISUAL_OBSERVATION" ? observations.length > 0 ? observations.map((observation, index) => <p key={`${observation.observation}-${index}`}>{observation.observation}</p>) : <p>No visual notes were recorded.</p>
          : provenanceCopy ? <p>{provenanceCopy.explanation}{aiDeclarationCopy(item.provenance?.ai_disclosures ?? []) && ` ${aiDeclarationCopy(item.provenance?.ai_disclosures ?? [])}`}</p>
            : <p>{safeEvidenceText(item.content)}</p>}
      {item.source && <dl className={styles.ledgerMeta} aria-label="Evidence ledger details">
        <div><dt>Tier</dt><dd>{(item.source_tier || "UNKNOWN").replaceAll("_", " ")}</dd></div>
        <div><dt>Stance</dt><dd>{relationshipPresentation(item.stance || relationship || "UNKNOWN")}</dd></div>
        <div><dt>Published</dt><dd>{item.published_date ? publicationDateLabel(item.published_date) || item.published_date : "Date unavailable"}{item.is_stale === true ? " · may be outdated" : ""}</dd></div>
        <div><dt>Source group</dt><dd>{item.independence_group_id || "unknown"}</dd></div>
        <div><dt>Excerpt</dt><dd>{item.excerpt_validated ? `Validated at characters ${item.excerpt_location?.start ?? "?"}–${item.excerpt_location?.end ?? "?"}` : "Quote validation unavailable"}</dd></div>
      </dl>}
      {item.limitations && <small className={styles.muted}>{safeEvidenceText(item.limitations)}</small>}
      {showSourceAction && item.source && <a className={styles.textLink} href={item.source.url} target="_blank" rel="noreferrer">Open source ↗</a>}
    </article>
  );
}

function SourceCard({ source, evidence, relationships, sources, lane }: {
  source: Source;
  evidence: Evidence[];
  relationships: Results["source_relationships"];
  sources: Source[];
  lane: "RECENT" | "HISTORICAL" | "OTHER";
}) {
  const excerpts = evidence.filter((item) => item.source?.id === source.id);
  const related = relationships.filter((item) => item.source_id === source.id || item.related_source_id === source.id);
  const retrievalStyle = source.retrieval_status === "RETRIEVED"
    ? styles.sourceRETRIEVED
    : source.retrieval_status === "FAILED" ? styles.sourceFAILED : styles.sourceCANDIDATE;
  return (
    <article className={`${styles.sourceCard} ${retrievalStyle}`}>
      <div className={styles.sourceHeading}>
        <div>
          <p className={styles.sourcePublisher}>{safeEvidenceText(source.publisher || source.domain || source.source_type)}</p>
          <h4>{safeEvidenceText(source.title || source.url)}</h4>
        </div>
        <div className={styles.sourceBadges}>
          {lane !== "OTHER" && <span className={`${styles.sourceLane} ${lane === "RECENT" ? styles.laneRecent : styles.laneHistorical}`}>{lane === "RECENT" ? "Recent coverage" : "Historical context"}</span>}
          <span className={styles.role}>{sourceRoleLabel(source.source_role)}</span>
        </div>
      </div>
      <p className={`${styles.sourceState} ${source.retrieval_status === "RETRIEVED" ? styles.sourceStateRetrieved : source.retrieval_status === "FAILED" ? styles.sourceStateFailed : styles.sourceStateCandidate}`}>
        {source.retrieval_status === "FAILED" ? "Retrieval failed" : source.retrieval_status === "RETRIEVED" ? "Page retrieved" : "Candidate only · not retrieved"}
      </p>
      <p className={styles.sourceMeta}>
        {source.published_at ? `Published ${publicationDateLabel(source.published_at) ?? "date unavailable"}` : "Publication date unavailable"}
        {source.author ? ` · ${safeEvidenceText(source.author)}` : ""}
      </p>
      {source.discovery_method === "SUBMITTED_URL" && <p className={styles.contextNote}>Submitted page. Its claims are context, not independent evidence.</p>}
      {source.discovery_method === "MODEL_PROPOSED" && <p className={styles.contextNote}>Suggested during investigation; Agent 0 could not confirm it in the recorded search results.</p>}
      {source.retrieval_status === "FAILED" && <p className={styles.contextNote}>Agent 0 could not independently retrieve this page.</p>}
      {source.authoritative_for.length > 0 && <p className={styles.scope}>Relevant to: {safeEvidenceText(source.authoritative_for.join("; "))}</p>}
      {related.length > 0 && <ul className={styles.relationshipList} aria-label="Source relationships">
        {related.map((relation, index) => {
          const otherId = relation.source_id === source.id ? relation.related_source_id : relation.source_id;
          const other = sources.find((item) => item.id === otherId);
          return <li key={`${relation.relationship}-${index}`}>{relationshipPresentation(relation.relationship)} {other ? `· ${safeEvidenceText(other.title || other.domain || "related source")}` : "· related source"}</li>;
        })}
      </ul>}
      {excerpts.length > 0 ? excerpts.map((item) => <EvidenceCard key={item.id} item={item} showSourceAction={false} />) : <p className={styles.muted}>No relevant excerpt from this source is available.</p>}
      <a className={styles.textLink} href={source.url} target="_blank" rel="noreferrer">Examine source ↗</a>
    </article>
  );
}

export default function InvestigatePage() {
  const [content, setContent] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const previewUrlRef = useRef<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [previewUnavailable, setPreviewUnavailable] = useState(false);
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [results, setResults] = useState<Results | null>(null);
  const [lastChecked, setLastChecked] = useState("");
  const [busy, setBusy] = useState(false);
  const [retryBusy, setRetryBusy] = useState(false);
  const [error, setError] = useState("");
  const [evidenceFilter, setEvidenceFilter] = useState<EvidenceFilter>("ALL");
  const [triage, setTriage] = useState<TriagePreview | null>(null);
  const [triageClaims, setTriageClaims] = useState<TriageClaim[]>([]);

  function selectFile(file: File | null) {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    const safeFile = file && ["image/jpeg", "image/png", "image/webp", "video/mp4", "video/webm"].includes(file.type) ? file : null;
    previewUrlRef.current = safeFile ? URL.createObjectURL(safeFile) : null;
    setPreviewUrl(previewUrlRef.current ?? "");
    setSelectedFile(safeFile);
    setPreviewUnavailable(false);
    if (safeFile) setError("");
    if (file && !safeFile) setError("Choose a JPEG, PNG or WebP image, or an MP4 or WebM video.");
  }

  useEffect(() => () => {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
  }, []);

  const refresh = useCallback(async (id: string) => {
    const [statusResponse, resultsResponse] = await Promise.all([
      fetch(`/api/investigations/${id}`, { cache: "no-store" }),
      fetch(`/api/investigations/${id}/results`, { cache: "no-store" }),
    ]);
    if (!statusResponse.ok) throw new Error(await readError(statusResponse));
    const current = (await statusResponse.json()) as Investigation;
    setInvestigation(current);
    setLastChecked(new Date().toISOString());
    if (resultsResponse.ok) setResults((await resultsResponse.json()) as Results);
    return current;
  }, []);

  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("investigation");
    if (!id) return;
    const timer = window.setTimeout(() => {
      void refresh(id).catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "Could not reopen this investigation.");
      });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  useEffect(() => {
    if (!investigation?.id || !ACTIVE.has(investigation.status)) return;
    let stopped = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const current = await refresh(investigation.id);
        if (!ACTIVE.has(current.status)) return;
      } catch (reason: unknown) {
        setError(reason instanceof Error ? reason.message : "Could not refresh this investigation.");
      }
      if (!stopped) timer = window.setTimeout(() => void poll(), 5000);
    };
    timer = window.setTimeout(() => void poll(), 5000);
    return () => {
      stopped = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [investigation?.id, investigation?.status, refresh]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setResults(null);
    setInvestigation(null);
    setPreviewUnavailable(false);
    try {
      if (selectedFile) {
        if (!content.trim()) throw new Error("Add the factual claim or question shown by the media before triage.");
      }
      const inputType = selectedFile ? "TEXT" : inferInputType(content);
      const response = await fetch("/api/investigations/triage", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ input_type: inputType, content: content.trim() }),
      });
      if (!response.ok) throw new Error(await readError(response));
      const preview = (await response.json()) as TriagePreview;
      if (!preview.draft_id) {
        setError(preview.clarification_question || "Please add one specific factual claim before continuing.");
        return;
      }
      setTriage(preview);
      setTriageClaims(preview.claims);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start this investigation.");
    } finally {
      setBusy(false);
    }
  }

  async function continueTriage() {
    if (!triage?.draft_id || triageClaims.length === 0) return;
    setBusy(true);
    setError("");
    try {
      let response: Response;
      if (selectedFile) {
        const form = new FormData();
        form.set("file", selectedFile);
        form.set("prompt", content.trim());
        form.set("triage_id", triage.draft_id);
        form.set("claims_json", JSON.stringify(triageClaims));
        response = await fetch("/api/investigations/media", { method: "POST", body: form });
      } else {
        response = await fetch(`/api/investigations/${triage.draft_id}/continue`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ claims: triageClaims }),
        });
      }
      if (!response.ok) throw new Error(await readError(response));
      const created = (await response.json()) as Investigation;
      setTriage(null);
      setInvestigation(created);
      await refresh(created.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not continue this investigation.");
    } finally {
      setBusy(false);
    }
  }

  async function retryInvestigation() {
    if (!investigation) return;
    setRetryBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/investigations/${investigation.id}`, { method: "POST" });
      if (!response.ok) throw new Error(await readError(response));
      const retried = (await response.json()) as Investigation;
      setInvestigation(retried);
      setResults(null);
      await refresh(retried.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not retry this investigation.");
    } finally {
      setRetryBusy(false);
    }
  }

  const finished = investigation !== null && !ACTIVE.has(investigation.status);
  const completed = investigation?.status === "COMPLETE";
  const activeProgressStep = investigation ? progressStepForStage(investigation.current_stage) : 0;
  const claims = results?.claims ?? [];
  const evidence = (results?.evidence ?? []).filter((item) => item.method !== "MEDIA_FINGERPRINT");
  const mediaEvidence = evidence.filter((item) => Boolean(item.media_asset));
  const mediaAssets = results?.media_assets ?? mediaEvidence.flatMap((item) => item.media_asset ? [item.media_asset] : []);
  const originalMedia = mediaAssets.find((asset) => asset.media_type === "IMAGE" && asset.role.toUpperCase() === "ORIGINAL");
  const originalVideo = mediaAssets.find((asset) => asset.media_type === "VIDEO" && asset.role.toUpperCase() === "ORIGINAL");
  const provenanceEvidence = mediaEvidence.find((item) => item.provenance);
  const provenance = provenanceEvidence?.provenance;
  const imageAnswerFallback = originalMedia && content.trim()
    ? imageOriginAnswer(content.trim(), provenance?.status, provenance?.ai_disclosures ?? [])
    : null;
  const imageAnswer = imageAnswerFallback && results?.brief?.summary
    ? safeEvidenceText(results.brief.summary)
    : imageAnswerFallback;
  const conciseMediaLimitations = imageAnswerFallback
    ? ["Appearance and file metadata cannot establish whether an image was AI-generated.", "Reverse-image search was not performed."]
    : results ? presentedLimitations(results) : [];
  const visualEvidence = mediaEvidence.filter((item) => item.method === "MEDIA_VISUAL_OBSERVATION");
  const videoLimitations = results?.usage_summary?.limitations.filter((item) => /video/i.test(item)) ?? [];
  const metadataEvidence = mediaEvidence.filter((item) => item.method === "MEDIA_TECHNICAL_METADATA" || item.method === "MEDIA_METADATA");
  const unknowns = useMemo(() => results ? unknownsFromResults(results, finished) : [], [results, finished]);
  const nextSteps = useMemo(() => results ? recommendedNextSteps(results, finished) : [], [results, finished]);
  const mediaNotice = results ? visualAnalysisNotice(results) : null;
  const dateReferenceText = [content, ...(results?.claims ?? []).map((claim) => claim.text)].join(" ");
  const dateBasis = investigation ? relativeDateBasis(dateReferenceText, investigation.created_at) : null;
  const retrievalDisabled = Boolean(results?.usage_summary?.limitations.some((item) => item.includes("Source retrieval is disabled")));
  const readerFailureReason = results?.sources.find((source) => source.retrieval_failure_reason)?.retrieval_failure_reason;
  const readerFailureCopy = readerFailureReason === "JINA_RATE_LIMITED"
    ? "Jina Reader rate limit reached. Source pages were not retrieved; search candidates remain unchecked. Add or refresh JINA_API_KEY, then retry when the key can make Reader requests."
    : readerFailureReason === "JINA_QUOTA_EXHAUSTED"
      ? "Jina Reader reports that its token quota is exhausted. Source pages were not retrieved; search candidates remain unchecked. Configure a Jina key with available Reader quota, then retry."
      : readerFailureReason === "JINA_AUTHENTICATION_FAILED"
        ? "Jina Reader rejected its API key. Source pages were not retrieved; search candidates remain unchecked. Check JINA_API_KEY, then retry."
        : null;
  const failedSearchProviders = [...new Set((results?.search_traces ?? [])
    .filter((trace) => ["unavailable", "error", "budget_exceeded"].includes(trace.action))
    .map((trace) => trace.provider.replaceAll("_", " ").toLowerCase()))];
  const searchedProviders = [...new Set((results?.search_traces ?? [])
    .filter((trace) => ["search", "empty"].includes(trace.action))
    .map((trace) => trace.provider.replaceAll("_", " ").toLowerCase()))];
  const attemptedRouteLanes = [...new Set((results?.search_traces ?? [])
    .filter((trace) => ["search", "empty"].includes(trace.action))
    .map((trace) => trace.route?.source_lane)
    .filter((lane): lane is "PRIMARY" | "REFERENCE_REPORTING" | "FACT_CHECK" | "SOCIAL" => Boolean(lane)))];
  const routeLaneNames = attemptedRouteLanes.map((lane) => ({
    PRIMARY: "primary records",
    REFERENCE_REPORTING: "independent references and reporting",
    FACT_CHECK: "published fact-check context",
    SOCIAL: "social sources",
  })[lane]);
  const searchUnavailable = failedSearchProviders.length > 0 && searchedProviders.length === 0;
  const searchReturnedNoResults = Boolean(results?.search_traces.length && results.search_traces.every((trace) => trace.action === "empty"));
  const unretrievedSourceCount = results?.sources.filter((source) => source.retrieval_status !== "RETRIEVED").length ?? 0;
  const filteringEvidence = evidence.filter((item) => {
    if (evidenceFilter === "ALL") return true;
    const links = item.claim_links.map((link) => link.relationship);
    if (evidenceFilter === "SUPPORTS") return links.includes("SUPPORTS");
    if (evidenceFilter === "CONTRADICTS") return links.includes("CONTRADICTS");
    return links.some((value) => ["CONTEXTUALIZES", "MENTIONS", "UNKNOWN"].includes(value));
  });
  const filteredSourceEvidence = filteringEvidence.filter((item) => Boolean(item.source));
  const otherEvidence = evidence.filter((item) => !item.source && !item.media_asset);
  const otherFilteredEvidence = filteringEvidence.filter((item) => !item.source && !item.media_asset);
  const sourceGroups = results ? ([
    { lane: "RECENT" as const, title: "Recent coverage", sources: results.sources.filter((source) => sourceResearchLane(source, results.search_traces) === "RECENT") },
    { lane: "HISTORICAL" as const, title: "Historical context", sources: results.sources.filter((source) => sourceResearchLane(source, results.search_traces) === "HISTORICAL") },
    { lane: "OTHER" as const, title: "Other sources found", sources: results.sources.filter((source) => sourceResearchLane(source, results.search_traces) === "OTHER") },
  ].filter((group) => group.sources.length > 0)) : [];

  return (
    <main className={styles.page}>
      <WorkspaceHeader activeHref="/investigate" />

      <div className={styles.workspace}>
        <p className={styles.processingNote}>Shared demo: investigation history is visible to other visitors. Use public, non-sensitive claims only.</p>
        <section className={styles.startGrid}>
          <div className={styles.intakeMain}>
        <section className={styles.intro}>
          <p className="eyebrow">A clear place to start</p>
          <h1>What do you want to check?</h1>
          <p>Ask about a specific factual claim, paste a public source, or add an image or short video. Agent 0 will identify what can be checked, review available evidence, and explain what remains uncertain.</p>
        </section>

        <form className={styles.form} onSubmit={submit} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); const file = event.dataTransfer.files?.[0]; if (file) selectFile(file); }} onPaste={(event) => { const file = Array.from(event.clipboardData.items).find((item) => item.type.startsWith("image/") || item.type.startsWith("video/"))?.getAsFile(); if (file) { event.preventDefault(); selectFile(file); } }}>
          <label htmlFor="investigation-input">Question, claim, or public source</label>
          <textarea id="investigation-input" maxLength={20000} rows={5} placeholder="Paste a claim or link…" value={content} onChange={(event) => setContent(event.target.value)} aria-describedby="input-help" />
          <p id="input-help" className={styles.helper}>You can also add an image or a short video.</p>
          <input ref={fileInputRef} id="image-upload" className={styles.fileInput} type="file" accept="image/jpeg,image/png,image/webp,video/mp4,video/webm,.jpg,.jpeg,.png,.webp,.mp4,.webm" aria-label="Choose an image or video" onChange={(event) => selectFile(event.target.files?.[0] ?? null)} />
          {selectedFile && <div className={styles.uploadPreview}>
            {previewUrl && (selectedFile.type.startsWith("video/")
              ? <video src={previewUrl} controls aria-label="Preview of the selected video" />
              : <Image src={previewUrl} alt="Preview of the selected image" width={720} height={480} unoptimized />)}
            <div><strong>{selectedFile.name || (selectedFile.type.startsWith("video/") ? "Selected video" : "Selected image")}</strong><span>{selectedFile.type || "Media file"} · {formatBytes(selectedFile.size)}</span></div>
            <button type="button" className={styles.removeFile} onClick={() => { selectFile(null); if (fileInputRef.current) fileInputRef.current.value = ""; }}>Remove file</button>
          </div>}

          <div className={styles.formFooter}>
            <div className={styles.inputActions}><button type="button" className={styles.uploadButton} onClick={() => fileInputRef.current?.click()}>＋ Add image or video</button><p>Video audio is not transcribed in this version. Use public information only.</p></div>
            <button className="button button-primary" disabled={busy || (!selectedFile && !content.trim())}>
              {busy ? "Starting…" : "Investigate"}<span aria-hidden="true">→</span>
            </button>
          </div>
          {error && <p className={styles.error} role="alert">{error}</p>}
        </form>

        {!investigation && !triage && <section className={styles.examples} aria-label="Examples">
          <p>Try a demo claim</p>{EXAMPLES.map((example) => <button type="button" key={example.text} onClick={() => { setContent(example.text); selectFile(null); if (fileInputRef.current) fileInputRef.current.value = ""; }}>{example.label}: {example.text}</button>)}
        </section>}
          </div>
          {!investigation && <aside className={styles.startAside}>
            <p className={styles.sectionKicker}>A careful first step</p>
            <h2>Make the claim easy to check.</h2>
            <p>Include who, what, where and when. A focused statement helps Agent 0 look for evidence that directly addresses it.</p>
            <ol><li><span>01</span>We identify and split checkable claims.</li><li><span>02</span>You review the claims before research starts.</li><li><span>03</span>You inspect findings and their source material.</li></ol>
          </aside>}
        </section>

        {triage && <section className={styles.stagePanel} aria-labelledby="triage-title">
          <p className="eyebrow">Before investigation</p>
          <h2 id="triage-title">Review the claims Agent 0 identified</h2>
          <p>Edit a claim or split a compound statement into separate claims. Research starts after you confirm.</p>
          {triageClaims.map((claim, index) => <div className={styles.form} key={`${index}-${claim.text}`}>
            <label htmlFor={`triage-claim-${index}`}>Claim {index + 1}</label>
            <textarea id={`triage-claim-${index}`} rows={2} value={claim.text} onChange={(event) => setTriageClaims((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, text: event.target.value } : item))} />
            <label htmlFor={`triage-type-${index}`}>Claim type</label>
            <select id={`triage-type-${index}`} value={claim.claim_type} onChange={(event) => { const claim_type = event.target.value as ClaimType; setTriageClaims((items) => items.map((item, itemIndex) => itemIndex === index ? { ...item, claim_type, needs_deep_investigation: claim_type !== "SETTLED_FACT" } : item)); }}>
              {CLAIM_TYPES.map((type) => <option key={type} value={type}>{type.replaceAll("_", " ")}</option>)}
            </select>
            {triageClaims.length > 1 && <button type="button" className={styles.removeFile} onClick={() => setTriageClaims((items) => items.filter((_, itemIndex) => itemIndex !== index))}>Remove claim</button>}
          </div>)}
          <button type="button" className="button button-secondary" disabled={triageClaims.length >= 3} onClick={() => setTriageClaims((items) => [...items, { text: "", claim_type: "CHECKABLE_EVENT", needs_deep_investigation: true }])}>＋ Split into another claim</button>
          <div className={styles.formFooter}><button type="button" className="button button-secondary" onClick={() => setTriage(null)}>Cancel</button><button type="button" className="button button-primary" disabled={busy || triageClaims.some((claim) => claim.text.trim().length < 5)} onClick={() => void continueTriage()}>{busy ? "Starting…" : "Confirm and investigate →"}</button></div>
          {error && <p className={styles.error} role="alert">{error}</p>}
        </section>}

        {investigation && <section className={styles.results} aria-labelledby="result-title">
          <div className={styles.resultHeader}>
            <div><p className="eyebrow">Investigation {investigation.reference}</p><h2 id="result-title">{completed ? "What Agent 0 found" : investigation.status === "FAILED" || investigation.status === "NEEDS_REVIEW" ? "Investigation paused" : investigation.status === "CANCELLED" ? "Investigation cancelled" : "Investigating…"}</h2></div>
            <div className={styles.resultTools}><a className={styles.whatsappLink} href={WHATSAPP_CONTACT_URL} target="_blank" rel="noopener noreferrer">WhatsApp help <span aria-hidden="true">↗</span></a><div className={styles.checked}>Last checked <time dateTime={lastChecked}>{lastChecked ? new Date(lastChecked).toLocaleTimeString() : "just now"}</time></div></div>
          </div>

          <div className={styles.stagePanel}>
            <span className={`${styles.stageMark}${finished ? "" : ` ${styles.stageActive}`}`} aria-hidden="true">{finished ? "✓" : "…"}</span>
            <div><strong>{stagePresentation(investigation.current_stage, results)}</strong><span role="status" aria-live="polite">{investigation.status === "NEEDS_REVIEW" ? "Review needed" : investigation.status === "FAILED" ? "Couldn’t complete" : investigation.status === "CANCELLED" ? "Cancelled" : completed ? "Processing finished" : "In progress"}</span></div>
            {!finished && <p className={styles.processingNote}>This can take a little while. You can stay here while Agent 0 checks the available evidence.</p>}
            {completed && <p className={styles.progressHint}>Processing completed. This does not mean the claim was verified; see the finding status and evidence below.</p>}
            {!finished && <div className={styles.progressDetails}>
              <ol className={styles.progressSteps} aria-label="Investigation checkpoints">
                {REVIEW_STEPS.map((step, index) => <li key={step} data-state={index < activeProgressStep ? "complete" : index === activeProgressStep ? "active" : "upcoming"} aria-current={index === activeProgressStep ? "step" : undefined}>
                  <span className={styles.progressMarker} aria-hidden="true">{index < activeProgressStep ? "✓" : index + 1}</span><span>{step}</span>
                </li>)}
              </ol>
              <div className={styles.progressTrack} role="progressbar" aria-label="Investigation progress" aria-valuemin={0} aria-valuemax={100} aria-valuetext={stagePresentation(investigation.current_stage, results)}><span /></div>
              <p className={styles.progressHint}>Checkpoints update as the review advances. This indicator does not estimate completion time.</p>
            </div>}
          </div>
          {investigation.failure_reason && <div className={styles.failure} role="alert"><strong>Agent 0 stopped before completing the review</strong><p>{safeEvidenceText(investigation.failure_reason)} Review any evidence already collected before drawing a conclusion.</p></div>}
          {results?.retry_allowed && <button type="button" className="button button-secondary" disabled={retryBusy} onClick={() => void retryInvestigation()}>{retryBusy ? "Retrying…" : "Retry investigation"}</button>}
          {error && <p className={styles.error} role="alert">{error}</p>}

          {results && <>
            <nav className={styles.sectionNav} aria-label="Investigation sections">
              <a href="#overview">Overview</a>
              <a href="#evidence">Evidence</a>
              {(originalMedia || originalVideo) && <a href="#media">Media</a>}
              {finished && results.brief && <a href="#brief">Brief</a>}
              <a className={styles.whatsappSectionLink} href={WHATSAPP_CONTACT_URL} target="_blank" rel="noopener noreferrer">WhatsApp help ↗</a>
            </nav>

            <section id="overview" className={styles.overview}>
              <div className={styles.overviewMain}>
                <p className={styles.sectionKicker}>{originalMedia && !content.trim() ? "Image submitted" : originalVideo && !content.trim() ? "Video submitted" : claims.length ? "Checkable claim" : "What we are investigating"}</p>
                {claims.length > 0 ? <div className={styles.claimList}>{claims.map((claim) => {
                  const finding = results.findings.find((item) => item.claim_id === claim.id);
                  const presentation = finding ? statusPresentation(finding.status) : null;
                  const cited = finding ? findingRelationship(finding, evidence) : [];
                  return <article className={styles.finding} key={claim.id}>
                      <h3>{safeEvidenceText(claim.text)}</h3>
                      <p className={styles.sectionKicker}>Triage · {claim.type.replaceAll("_", " ").toLowerCase()} · {claim.needs_deep_investigation === false ? "deep investigation not flagged" : "deep investigation flagged"}</p>
                      {dateBasis && <p className={styles.dateBasis}>{safeEvidenceText(dateBasis)}</p>}
                {finding && <>
                      <div className={`${styles.findingStatus} ${styles[`tone${finding.status}`] ?? ""}`}>
                        <span aria-hidden="true">{presentation?.icon}</span><strong>{presentation?.label}</strong>
                        <p>{presentation?.explanation}</p>
                      </div>
                      {finding.explanation?.length ? <div className={styles.findingStatement}>
                        {finding.explanation.map((item, index) => <span key={`${finding.id}-${index}`}>
                          {safeEvidenceText(item.sentence)} {item.evidence_ids.map((id, citationIndex) => <a key={id} href={`#evidence-${id}`} aria-label="View cited evidence">[{citationLabel(evidence.find((entry) => entry.id === id), citationIndex + 1)}]</a>)}{" "}
                        </span>)}
                      </div> : <p className={styles.findingStatement}>{safeEvidenceText(finding.statement)}</p>}
                      {finding.unsupported_statements_removed && <p className={styles.resultCaveat} role="status">Unsupported statements removed after citation checks.</p>}
                      {finding.evidence_confidence && <p className={styles.findingConfidence}><strong>Evidence confidence: {finding.evidence_confidence.toLowerCase()}</strong> <span>(qualitative, not a probability)</span>{finding.confidence_rationale && <> · {safeEvidenceText(finding.confidence_rationale)}</>}</p>}
                      {finding.limitations && <p className={styles.findingLimitation}>{safeEvidenceText(finding.limitations)}</p>}
                      <div className={styles.citationLinks}>
                        {cited.map(({ item, relationship }) => <a key={item.id} href={`#evidence-${item.id}`}>
                          {relationshipPresentation(relationship)} · View evidence
                        </a>)}
                      {cited.length === 0 && <span>No retrieved evidence excerpt supports this finding. Source candidates are listed below as leads only.</span>}
                      </div>
                    </>}
                  </article>;
                })}</div> : <article className={styles.finding}>
                  <p className={styles.sectionKicker}>Submitted question</p>
                  {content.trim() && <h3>{safeEvidenceText(content.trim())}</h3>}
                  <p className={styles.empty}>{!finished ? "Agent 0 is examining the submission and identifying a checkable claim." : imageAnswer ?? results?.brief?.summary ?? (originalVideo ? "The video was examined using a small set of visual frames. Audio was not transcribed, so spoken claims were not checked." : originalMedia ? "The available image checks do not establish where or when the depicted event happened. Share the original post or a source page to investigate its context." : "I couldn’t identify a specific claim to check. Add the exact statement and any relevant person, place, or date; it hasn’t been assessed as true or false.")}</p>
                </article>}
              </div>
              {claims.length > 0 && unretrievedSourceCount > 0 && <p className={styles.resultCaveat}>{retrievalDisabled && results.evidence_coverage.sources_retrieved === 0 ? "Search found candidates, but page retrieval is disabled for this run. No source text was reviewed; headlines cannot support a finding." : results.evidence_coverage.sources_retrieved === 0 ? "No source page was retrieved for this run. Search-result titles are leads only; source-based verification could not be completed." : `${unretrievedSourceCount} source candidate${unretrievedSourceCount === 1 ? " was" : "s were"} not retrieved. Only retrieved page content can support a source-based finding.`}</p>}
            </section>

            {claims.length > 0 && <section className={styles.keyEvidence} aria-labelledby="key-evidence-title">
              <div className={styles.sectionHeading}><div><p className={styles.sectionKicker}>The clearest signals</p><h3 id="key-evidence-title">Why Agent 0 reached this result</h3></div><a className={styles.textLink} href="#evidence">View all evidence ↓</a></div>
              {claims.flatMap((claim) => {
                const finding = results.findings.find((item) => item.claim_id === claim.id);
                return finding ? findingRelationship(finding, evidence).slice(0, 4) : [];
              }).slice(0, 4).length > 0 ? <div className={styles.keyEvidenceList}>
                {claims.flatMap((claim) => {
                  const finding = results.findings.find((item) => item.claim_id === claim.id);
                  return finding ? findingRelationship(finding, evidence).slice(0, 4) : [];
                }).slice(0, 4).map(({ item, relationship }) => <article className={styles.keyEvidenceItem} key={item.id}>
                  <p className={styles.evidenceFamily}>{item.source ? safeEvidenceText(results.sources.find((source) => source.id === item.source?.id)?.publisher || "Source evidence") : "Image evidence"}</p>
                  <p>{safeEvidenceText(item.content).slice(0, 360)}{item.content.length > 360 ? "…" : ""}</p><a className={styles.textLink} href={`#evidence-${item.id}`}>{relationshipPresentation(relationship)} · See details</a>
                </article>)}
              </div> : <p className={styles.empty}>{finished ? "No retrieved evidence excerpt was linked to a finding. The result explains what could not be assessed; source candidates remain leads until their contents are reviewed." : "Agent 0 is gathering and reviewing available evidence. Findings will appear here when the review is complete."}</p>}
            </section>}

            {claims.length > 0 && <section className={styles.unknowns} aria-labelledby="unknowns-title">
              <div><p className={styles.sectionKicker}>Open questions</p><h3 id="unknowns-title">What we still don’t know</h3></div>
              {unknowns.length ? <ul>{unknowns.map((item) => <li key={item}>{safeEvidenceText(item)}</li>)}</ul> : <p>{finished ? "No additional unknowns were recorded." : "Open questions will be summarized when the evidence review is complete."}</p>}
            </section>}

            {(claims.length > 0 || !imageAnswerFallback) && <section className={styles.nextSteps} aria-labelledby="next-steps-title">
              <div><p className={styles.sectionKicker}>Continue the reporting</p><h3 id="next-steps-title">What you can do next</h3></div>
              {nextSteps.length ? <ol>{nextSteps.map((item) => <li key={item}>{item}</li>)}</ol> : <p>{finished ? "Review the cited evidence with an editor before publication." : "Recommended next steps will appear when the evidence review is complete."}</p>}
            </section>}

            <section id="evidence" className={styles.contentSection}>
              <div className={styles.sectionHeading}><div><p className={styles.sectionKicker}>Inspect the trail</p><h3>Evidence</h3></div>
                <div className={styles.filters} role="group" aria-label="Filter evidence">
                  {(["ALL", "SUPPORTS", "CONTRADICTS", "CONTEXT"] as const).map((filter) => <button type="button" key={filter} aria-pressed={evidenceFilter === filter} onClick={() => setEvidenceFilter(filter)}>{filter === "ALL" ? "All" : filter === "CONTEXT" ? "Context" : relationshipPresentation(filter)}</button>)}
                </div>
              </div>
              <p className={styles.searchScopeNote}>{searchedProviders.length ? `Search providers used: ${searchedProviders.join(" and ")}.` : "Search providers have not returned results yet."} Route: {routeLaneNames.length ? routeLaneNames.join(" → ") : "primary records first"}. Secondary lanes run only when an earlier pass finds fewer than two distinct retrieved source domains for a claim. Search results remain candidates until their pages are retrieved. Agent 0 does not search logged-in pages or direct social-platform feeds.</p>
              {readerFailureCopy && <p className={styles.partialNotice} role="status">{readerFailureCopy}</p>}
              {failedSearchProviders.length > 0 && results.sources.length > 0 && <p className={styles.partialNotice}>Could not search {failedSearchProviders.join(" and ")}; results from {searchedProviders.join(" and ") || "the available providers"} may be incomplete.</p>}
              {results.sources.length > 0 ? <div className={styles.sourceList}>
                <h4>{results.sources.every((source) => source.retrieval_status === "RETRIEVED") ? "Sources reviewed" : "Sources found"}</h4>
                {!retrievalDisabled && results.sources.some((source) => source.retrieval_status !== "RETRIEVED") && <p className={styles.partialNotice}>{results.evidence_coverage.sources_retrieved === 0 ? "No source pages were retrieved in this investigation. These are search candidates only; titles and publication dates are leads, not evidence." : "Some results are source candidates only. Their titles and publication dates are leads, not reviewed evidence, until page content is retrieved."}</p>}
                {retrievalDisabled && <p className={styles.partialNotice}>Public web search returned candidates, but page retrieval is disabled for this run. Candidate titles are not evidence.</p>}
                {sourceGroups.map((group) => <div className={styles.sourceLaneGroup} key={group.lane}>
                  <h5>{group.title}</h5>
                  {group.sources.map((source) => <SourceCard key={source.id} source={source} evidence={filteredSourceEvidence} relationships={results.source_relationships} sources={results.sources} lane={group.lane} />)}
                </div>)}
              </div> : <p className={styles.empty}>{!finished ? "Source checks are still in progress. Results will appear here when available." : searchUnavailable ? `Search could not be completed by ${failedSearchProviders.join(" and ")}. No external source material was assessed; this does not tell us whether the claim is true or false.` : failedSearchProviders.length > 0 && searchedProviders.length > 0 ? `Search returned no source candidates. ${failedSearchProviders.join(" and ")} could not be searched, so coverage may be incomplete. This does not tell us whether the claim is true or false.` : searchReturnedNoResults ? "Search returned no source candidates. That alone does not tell us whether the claim is true or false." : "No external sources were collected for this investigation."}</p>}
              {otherEvidence.length > 0 && <div className={styles.otherEvidence}>
                <h4>Other evidence checked</h4>
                {otherFilteredEvidence.length ? otherFilteredEvidence.map((item) => <EvidenceCard key={item.id} item={item} relationship={item.claim_links[0]?.relationship} />) : <p className={styles.empty}>{finished ? "No additional evidence matches this filter." : "Evidence will appear here as Agent 0 reviews the submission and available sources."}</p>}
              </div>}
            </section>

            {originalMedia && <section id="media" className={styles.contentSection}>
              <div className={styles.sectionHeading}><div><p className={styles.sectionKicker}>Image submitted</p><h3>Image details</h3></div><span className={styles.mediaState}>{mediaEvidence.length ? "Review available" : "Review pending"}</span></div>
              <div className={styles.mediaCard}>
                <div className={styles.previewFrame}>
                  {!finished
                    ? <p className={styles.muted}>Preparing a safe image preview…</p>
                    : previewUnavailable
                    ? <p className={styles.muted}>A safe preview will appear after media preparation.</p>
                    : <Image src={`/api/investigations/${investigation.id}/media-preview`} alt="Metadata-stripped preview of the submitted image" width={960} height={640} unoptimized onError={() => setPreviewUnavailable(true)} />}
                </div>
                <div className={styles.mediaDetails}><span>{originalMedia.mime_type}</span><span>{formatBytes(originalMedia.size_bytes)}</span><p>The uploaded image is part of this investigation. The preview uses a normalized copy.</p></div>
              </div>
              {mediaNotice && <p className={styles.partialNotice}>{mediaNotice}</p>}

              <details className={styles.mediaChecksDetails}>
                <summary>View image checks and technical details</summary>
                <div className={styles.mediaEvidenceGrid}>
                <section className={styles.mediaGroup} aria-labelledby="provenance-title">
                  <p className={styles.sectionKicker}>Image origin</p><h4 id="provenance-title">Origin &amp; history</h4>
                  {provenance ? <>
                    <div className={styles.provenanceStatus}><span aria-hidden="true">{provenance.status === "VALID" ? "✓" : provenance.status === "NOT_PRESENT" ? "○" : "?"}</span><strong>{provenancePresentation(provenance.status).label}</strong></div>
                    {!imageAnswerFallback && <p>{provenancePresentation(provenance.status).explanation}</p>}
                    {aiDeclarationCopy(provenance.ai_disclosures) && <p className={styles.aiDeclaration}>{aiDeclarationCopy(provenance.ai_disclosures)}</p>}
                    {!imageAnswerFallback && <p className={styles.caution}>{provenancePresentation(provenance.status).limitation}</p>}
                    <details className={styles.offlineDetails}><summary>What does this mean?</summary><p>Content credentials can provide information about where an image came from or how it was edited. Their presence does not prove the event shown is true, and their absence does not mean an image is fake.</p><p>Technical details: credentials were checked on the uploaded file. Online certificate checks were not performed.</p></details>
                    {!imageAnswerFallback && provenance.limitations.map((item) => <small className={styles.muted} key={item}>{safeEvidenceText(item)}</small>)}
                  </> : <p className={styles.muted}>{finished ? "No image origin information is available." : "Checking available origin information…"}</p>}
                </section>

                <section className={styles.mediaGroup} aria-labelledby="metadata-title">
                  <p className={styles.sectionKicker}>File information</p><h4 id="metadata-title">File details</h4>
                  {metadataEvidence.length ? metadataEvidence.map((item) => {
                    const fields = technicalMetadata(item.content);
                    return <div key={item.id}>{fields.length ? <dl className={styles.metadataList}>{fields.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl> : <p>Allowlisted technical metadata was examined.</p>}{item.limitations && !imageAnswerFallback && <p className={styles.caution}>{safeEvidenceText(item.limitations)}</p>}</div>;
                  }) : <p className={styles.muted}>{finished ? "No useful file details are available." : "Reviewing file details…"}</p>}
                </section>

                <section className={styles.mediaGroup} aria-labelledby="visual-title">
                  <p className={styles.sectionKicker}>Visual review</p><h4 id="visual-title">What Agent 0 can see</h4>
                  {visualEvidence.length ? visualEvidence.flatMap((item): { observation: string; relevance: string; limitations: string[] }[] => visualObservations(item.content)).map((item, index) => <article className={styles.observation} key={`${item.observation}-${index}`}><span>OBSERVATION</span><p>{item.observation}</p>{item.relevance && <small>Relevance: {item.relevance}</small>}{item.limitations.map((limitation) => <small className={styles.caution} key={limitation}>{limitation}</small>)}</article>) : <p className={styles.muted}>{mediaNotice ? "Visual interpretation did not complete." : finished ? "No visual observations were recorded." : "Visual review is still in progress…"}</p>}
                  {!imageAnswerFallback && <p className={styles.caution}>Visual interpretation may be incomplete or mistaken; it is not forensic proof.</p>}
                </section>
                </div>
              </details>
            </section>}

            {originalVideo && <section id="media" className={styles.contentSection}>
              <div className={styles.sectionHeading}><div><p className={styles.sectionKicker}>Video submitted</p><h3>Video review</h3></div><span className={styles.mediaState}>{visualEvidence.length ? "Frame observations available" : finished ? "No frame observations recorded" : "Analysis in progress"}</span></div>
              <div className={styles.mediaCard}>
                <div className={styles.previewFrame}><p className={styles.muted}>Agent 0 samples up to four frames from videos under 90 seconds to identify visible, checkable details. The original video is not played in the results view.</p></div>
                <div className={styles.mediaDetails}><span>{originalVideo.mime_type}</span><span>{formatBytes(originalVideo.size_bytes)}</span><p>Audio was not transcribed or analyzed.</p>{videoLimitations.map((item) => <p key={item}>{safeEvidenceText(item)}</p>)}</div>
              </div>
              {mediaEvidence.length ? mediaEvidence.map((item) => <EvidenceCard key={item.id} item={item} relationship={item.claim_links[0]?.relationship} />) : <p className={styles.muted}>{finished ? "No video observations were recorded." : "Video observations are still being prepared."}</p>}
            </section>}

            <details className={styles.limitations}>
              <summary>Additional limitations and review notes</summary>
              <ul>
                {conciseMediaLimitations.map((item) => <li key={item}>{item}</li>)}
                {!results.brief?.limitations.length && !evidence.some((item) => item.limitations) && <li>{finished ? "Evidence collection is limited to the sources and media available in this investigation." : "Limitations will be summarized after the evidence review."}</li>}
                {originalMedia && !imageAnswerFallback && <li>Reverse-image search was not performed.</li>}
              </ul>
            </details>

            <section id="brief" className={styles.brief} aria-labelledby="brief-title">
              <div className={styles.sectionHeading}><div><p className={styles.sectionKicker}>A newsroom-ready summary</p><h3 id="brief-title">Verification brief</h3></div></div>
              {results.brief && finished ? <>
                {claims.map((claim) => {
                  const finding = results.findings.find((item) => item.claim_id === claim.id);
                  const view = finding ? statusPresentation(finding.status) : null;
                  return <article className={styles.briefClaim} key={claim.id}><h4>Claim</h4><p>{safeEvidenceText(claim.text)}</p>{finding && <><h4>Status</h4><p>{view?.label} — {safeEvidenceText(finding.statement)}</p>{finding.evidence_confidence && <><h4>Evidence confidence <small>(qualitative, not a probability)</small></h4><p>{finding.evidence_confidence.toLowerCase()}{finding.confidence_rationale ? ` — ${safeEvidenceText(finding.confidence_rationale)}` : ""}</p></>}<h4>Key evidence</h4>{findingRelationship(finding, evidence).map(({ item, relationship }) => <a key={item.id} href={`#evidence-${item.id}`}>{relationshipPresentation(relationship)} · View cited evidence</a>)}</>}</article>;
                })}
                {claims.length === 0 && <article className={styles.briefClaim}><h4>{originalMedia ? "Image review" : originalVideo ? "Video review" : "Your request"}</h4>{content.trim() && <p>{safeEvidenceText(content.trim())}</p>}<p>{imageAnswer ?? results.brief.summary}</p></article>}
                {originalMedia && claims.length > 0 && <><h4>Image origin &amp; history</h4><p>{provenance ? `${provenancePresentation(provenance.status).label}. ${provenancePresentation(provenance.status).limitation}` : "An image was submitted; no origin information is available."}</p></>}
                {claims.length > 0 && <><h4>Assessment summary</h4><p className={styles.briefSummary}>{safeEvidenceText(results.brief.summary)}</p>
                <h4>Unknowns</h4><ul>{unknowns.map((item) => <li key={item}>{item}</li>)}</ul>
                <h4>Recommended next steps</h4><ul>{nextSteps.length ? nextSteps.map((item) => <li key={item}>{item}</li>) : <li>Review all cited material with an editor.</li>}</ul>
                <h4>Limitations</h4><ul>{presentedLimitations(results).map((item) => <li key={item}>{item}</li>)}</ul></>}
              </> : <p className={styles.muted}>{finished ? "A verification brief is not available for this investigation." : "The brief will appear when evidence review is complete."}</p>}
            </section>
          </>}
        </section>}
      </div>
    </main>
  );
}
