"use client";

import Image from "next/image";
import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AgentMark } from "@/components/AgentMark";
import { WHATSAPP_CONTACT_URL } from "@/lib/contact";
import {
  aiDeclarationCopy,
  findingEvidenceReferences,
  inferInputType,
  presentedLimitations,
  provenancePresentation,
  progressStepForStage,
  recommendedNextSteps,
  relationshipPresentation,
  safeEvidenceText,
  stagePresentation,
  statusPresentation,
  technicalMetadata,
  unknownsFromResults,
  uploadErrorMessage,
  visualAnalysisNotice,
  visualObservations,
} from "./presentation.mjs";
import type { Evidence, Finding, Investigation, Results, Source } from "./types";
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

const EXAMPLES = [
  "Did the government announce this?",
  "Is this image from today’s event?",
  "Has this claim been reported elsewhere?",
  "Where did this information come from?",
];
const REVIEW_STEPS = ["Understand the claim", "Find sources", "Compare evidence", "Prepare the brief"];

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
      {item.limitations && <small className={styles.muted}>{safeEvidenceText(item.limitations)}</small>}
      {showSourceAction && item.source && <a className={styles.textLink} href={item.source.url} target="_blank" rel="noreferrer">Open source ↗</a>}
    </article>
  );
}

function SourceCard({ source, evidence, relationships, sources }: {
  source: Source;
  evidence: Evidence[];
  relationships: Results["source_relationships"];
  sources: Source[];
}) {
  const excerpts = evidence.filter((item) => item.source?.id === source.id);
  const related = relationships.filter((item) => item.source_id === source.id || item.related_source_id === source.id);
  return (
    <article className={styles.sourceCard}>
      <div className={styles.sourceHeading}>
        <div>
          <p className={styles.sourcePublisher}>{safeEvidenceText(source.publisher || source.domain || source.source_type)}</p>
          <h4>{safeEvidenceText(source.title || source.url)}</h4>
        </div>
        <span className={styles.role}>{sourceRoleLabel(source.source_role)}</span>
      </div>
      <p className={styles.sourceMeta}>
        {source.retrieval_status === "FAILED" ? "Couldn’t retrieve this page" : source.retrieval_status === "RETRIEVED" ? "Page reviewed" : "Source identified"}
        {source.published_at ? ` · Published ${new Date(source.published_at).toLocaleDateString()}` : ""}
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

  function selectFile(file: File | null) {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    const safeFile = file && ["image/jpeg", "image/png", "image/webp"].includes(file.type) ? file : null;
    previewUrlRef.current = safeFile ? URL.createObjectURL(safeFile) : null;
    setPreviewUrl(previewUrlRef.current ?? "");
    setSelectedFile(safeFile);
    setPreviewUnavailable(false);
    if (safeFile) setError("");
    if (file && !safeFile) setError("Choose a JPEG, PNG or WebP image.");
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
      let response: Response;
      if (selectedFile) {
        const form = new FormData();
        form.set("file", selectedFile);
        form.set("prompt", content.trim());
        response = await fetch("/api/investigations/media", { method: "POST", body: form });
      } else {
        const inputType = inferInputType(content);
        response = await fetch("/api/investigations", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ input_type: inputType, content: content.trim() }),
        });
      }
      if (!response.ok) throw new Error(await readError(response));
      const created = (await response.json()) as Investigation;
      setInvestigation(created);
      await refresh(created.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not start this investigation.");
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
  const provenanceEvidence = mediaEvidence.find((item) => item.provenance);
  const provenance = provenanceEvidence?.provenance;
  const visualEvidence = mediaEvidence.filter((item) => item.method === "MEDIA_VISUAL_OBSERVATION");
  const metadataEvidence = mediaEvidence.filter((item) => item.method === "MEDIA_TECHNICAL_METADATA" || item.method === "MEDIA_METADATA");
  const unknowns = useMemo(() => results ? unknownsFromResults(results, finished) : [], [results, finished]);
  const nextSteps = useMemo(() => results ? recommendedNextSteps(results, finished) : [], [results, finished]);
  const mediaNotice = results ? visualAnalysisNotice(results) : null;
  const filteringEvidence = evidence.filter((item) => {
    if (evidenceFilter === "ALL") return true;
    const links = item.claim_links.map((link) => link.relationship);
    if (evidenceFilter === "SUPPORTS") return links.includes("SUPPORTS");
    if (evidenceFilter === "CONTRADICTS") return links.includes("CONTRADICTS");
    return links.some((value) => ["CONTEXTUALIZES", "MENTIONS", "UNKNOWN"].includes(value));
  });
  const filteredSourceEvidence = filteringEvidence.filter((item) => Boolean(item.source));
  const otherEvidence = evidence.filter((item) => !item.source);
  const otherFilteredEvidence = filteringEvidence.filter((item) => !item.source);

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link href="/" aria-label="Agent 0 home"><AgentMark /></Link>
        <nav className={styles.workspaceNav} aria-label="Main navigation"><Link href="/investigate" aria-current="page">Investigate</Link><Link href="/investigations">Investigations</Link><Link href="/how-it-works">How it works</Link></nav>
      </header>

      <div className={styles.workspace}>
        <p className={styles.processingNote}>Public demo: use public information only. Do not submit private or sensitive details.</p>
        <section className={styles.intro}>
          <p className="eyebrow">A clear place to start</p>
          <h1>What do you want to check?</h1>
          <p>Paste a claim, link, or image. Agent 0 will examine the available evidence and show you what it can — and can’t — establish.</p>
        </section>

        <form className={styles.form} onSubmit={submit} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); const file = event.dataTransfer.files?.[0]; if (file) selectFile(file); }} onPaste={(event) => { const file = Array.from(event.clipboardData.items).find((item) => item.type.startsWith("image/"))?.getAsFile(); if (file) { event.preventDefault(); selectFile(file); } }}>
          <label htmlFor="investigation-input">Claim, link, or context</label>
          <textarea id="investigation-input" maxLength={20000} rows={5} placeholder="Paste a claim or link…" value={content} onChange={(event) => setContent(event.target.value)} aria-describedby="input-help" />
          <p id="input-help" className={styles.helper}>You can also add an image or drop one here.</p>
          <input ref={fileInputRef} id="image-upload" className={styles.fileInput} type="file" accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp" aria-label="Choose an image" onChange={(event) => selectFile(event.target.files?.[0] ?? null)} />
          {selectedFile && <div className={styles.uploadPreview}>
            {previewUrl && <Image src={previewUrl} alt="Preview of the selected image" width={720} height={480} unoptimized />}
            <div><strong>{selectedFile.name || "Selected image"}</strong><span>{selectedFile.type || "Image file"} · {formatBytes(selectedFile.size)}</span></div>
            <button type="button" className={styles.removeFile} onClick={() => { selectFile(null); if (fileInputRef.current) fileInputRef.current.value = ""; }}>Remove image</button>
          </div>}

          <div className={styles.formFooter}>
            <div className={styles.inputActions}><button type="button" className={styles.uploadButton} onClick={() => fileInputRef.current?.click()}>＋ Add image</button><p>Use public information only. Avoid private or credential-bearing details.</p></div>
            <button className="button button-primary" disabled={busy || (!selectedFile && !content.trim())}>
              {busy ? "Starting…" : "Investigate"}<span aria-hidden="true">→</span>
            </button>
          </div>
          {error && <p className={styles.error} role="alert">{error}</p>}
        </form>

        {!investigation && <section className={styles.examples} aria-label="Examples">
          <p>Try asking</p>{EXAMPLES.map((example) => <button type="button" key={example} onClick={() => { setContent(example); selectFile(null); if (fileInputRef.current) fileInputRef.current.value = ""; }}>{example}</button>)}
        </section>}

        {investigation && <section className={styles.results} aria-labelledby="result-title">
          <div className={styles.resultHeader}>
            <div><p className="eyebrow">Investigation {investigation.reference}</p><h2 id="result-title">{completed ? "What Agent 0 found" : investigation.status === "FAILED" || investigation.status === "NEEDS_REVIEW" ? "Investigation paused" : investigation.status === "CANCELLED" ? "Investigation cancelled" : "Investigating…"}</h2></div>
            <div className={styles.resultTools}><a className={styles.whatsappLink} href={WHATSAPP_CONTACT_URL} target="_blank" rel="noopener noreferrer">WhatsApp help <span aria-hidden="true">↗</span></a><div className={styles.checked}>Last checked <time dateTime={lastChecked}>{lastChecked ? new Date(lastChecked).toLocaleTimeString() : "just now"}</time></div></div>
          </div>

          <div className={styles.stagePanel}>
            <span className={`${styles.stageMark}${finished ? "" : ` ${styles.stageActive}`}`} aria-hidden="true">{finished ? "✓" : "…"}</span>
            <div><strong>{stagePresentation(investigation.current_stage)}</strong><span role="status" aria-live="polite">{investigation.status === "NEEDS_REVIEW" ? "Review needed" : investigation.status === "FAILED" ? "Couldn’t complete" : investigation.status === "CANCELLED" ? "Cancelled" : completed ? "Complete" : "In progress"}</span></div>
            {!finished && <p className={styles.processingNote}>This can take a little while. You can stay here while Agent 0 checks the available evidence.</p>}
            {!finished && <div className={styles.progressDetails}>
              <ol className={styles.progressSteps} aria-label="Investigation checkpoints">
                {REVIEW_STEPS.map((step, index) => <li key={step} data-state={index < activeProgressStep ? "complete" : index === activeProgressStep ? "active" : "upcoming"} aria-current={index === activeProgressStep ? "step" : undefined}>
                  <span className={styles.progressMarker} aria-hidden="true">{index < activeProgressStep ? "✓" : index + 1}</span><span>{step}</span>
                </li>)}
              </ol>
              <div className={styles.progressTrack} role="progressbar" aria-label="Investigation progress" aria-valuemin={0} aria-valuemax={100} aria-valuetext={stagePresentation(investigation.current_stage)}><span /></div>
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
              {originalMedia && <a href="#media">Media</a>}
              {finished && results.brief && <a href="#brief">Brief</a>}
              <a className={styles.whatsappSectionLink} href={WHATSAPP_CONTACT_URL} target="_blank" rel="noopener noreferrer">WhatsApp help ↗</a>
            </nav>

            <section id="overview" className={styles.overview}>
              <div className={styles.overviewMain}>
                <p className={styles.sectionKicker}>{originalMedia && !content.trim() ? "Image submitted" : "What we are investigating"}</p>
                {claims.length > 0 ? <div className={styles.claimList}>{claims.map((claim) => {
                  const finding = results.findings.find((item) => item.claim_id === claim.id);
                  const presentation = finding ? statusPresentation(finding.status) : null;
                  const cited = finding ? findingRelationship(finding, evidence) : [];
                  return <article className={styles.finding} key={claim.id}>
                    <h3>{safeEvidenceText(claim.text)}</h3>
                {finding && <>
                      <div className={`${styles.findingStatus} ${styles[`tone${finding.status}`] ?? ""}`}>
                        <span aria-hidden="true">{presentation?.icon}</span><strong>{presentation?.label}</strong>
                        <p>{presentation?.explanation}</p>
                      </div>
                      <p className={styles.findingStatement}>{safeEvidenceText(finding.statement)}</p>
                      {finding.limitations && <p className={styles.findingLimitation}>{safeEvidenceText(finding.limitations)}</p>}
                      <div className={styles.citationLinks}>
                        {cited.map(({ item, relationship }) => <a key={item.id} href={`#evidence-${item.id}`}>
                          {relationshipPresentation(relationship)} · View evidence
                        </a>)}
                      {cited.length === 0 && <span>No evidence was linked to this finding.</span>}
                      </div>
                    </>}
                  </article>;
                })}</div> : <article className={styles.finding}>
                  <p className={styles.sectionKicker}>Submitted question</p>
                  {content.trim() && <h3>{safeEvidenceText(content.trim())}</h3>}
                  <p className={styles.empty}>{!finished ? "Agent 0 is examining the submission. Any claim or image observations will appear here when this step is complete." : originalMedia && !content.trim() ? "No claim or context is available for this image review. Available file and origin signals do not establish where or when the depicted event occurred." : "No verifiable claim was extracted from this request. The question is shown as submitted, not treated as a finding."}</p>
                </article>}
              </div>
            </section>

            <section className={styles.keyEvidence} aria-labelledby="key-evidence-title">
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
              </div> : <p className={styles.empty}>{finished ? "No reliable evidence was linked to a finding. Review the available sources and what remains unknown below." : "Agent 0 is gathering and reviewing available evidence. Findings will appear here when the review is complete."}</p>}
            </section>

            <section className={styles.unknowns} aria-labelledby="unknowns-title">
              <div><p className={styles.sectionKicker}>Open questions</p><h3 id="unknowns-title">What we still don’t know</h3></div>
              {unknowns.length ? <ul>{unknowns.map((item) => <li key={item}>{safeEvidenceText(item)}</li>)}</ul> : <p>{finished ? "No additional unknowns were recorded." : "Open questions will be summarized when the evidence review is complete."}</p>}
            </section>

            <section className={styles.nextSteps} aria-labelledby="next-steps-title">
              <div><p className={styles.sectionKicker}>Continue the reporting</p><h3 id="next-steps-title">What you can do next</h3></div>
              {nextSteps.length ? <ol>{nextSteps.map((item) => <li key={item}>{item}</li>)}</ol> : <p>{finished ? "Review the cited evidence with an editor before publication." : "Recommended next steps will appear when the evidence review is complete."}</p>}
            </section>

            <section id="evidence" className={styles.contentSection}>
              <div className={styles.sectionHeading}><div><p className={styles.sectionKicker}>Inspect the trail</p><h3>Evidence</h3></div>
                <div className={styles.filters} role="group" aria-label="Filter evidence">
                  {(["ALL", "SUPPORTS", "CONTRADICTS", "CONTEXT"] as const).map((filter) => <button type="button" key={filter} aria-pressed={evidenceFilter === filter} onClick={() => setEvidenceFilter(filter)}>{filter === "ALL" ? "All" : filter === "CONTEXT" ? "Context" : relationshipPresentation(filter)}</button>)}
                </div>
              </div>
              {results.sources.length > 0 ? <div className={styles.sourceList}>
                <h4>Sources reviewed</h4>
                {results.sources.map((source) => <SourceCard key={source.id} source={source} evidence={filteredSourceEvidence} relationships={results.source_relationships} sources={results.sources} />)}
              </div> : <p className={styles.empty}>{finished ? "No external sources were collected for this investigation." : "Source checks are still in progress. Results will appear here when available."}</p>}
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

              <div className={styles.mediaEvidenceGrid}>
                <section className={styles.mediaGroup} aria-labelledby="provenance-title">
                  <p className={styles.sectionKicker}>Image origin</p><h4 id="provenance-title">Origin &amp; history</h4>
                  {provenance ? <>
                    <div className={styles.provenanceStatus}><span aria-hidden="true">{provenance.status === "VALID" ? "✓" : provenance.status === "NOT_PRESENT" ? "○" : "?"}</span><strong>{provenancePresentation(provenance.status).label}</strong></div>
                    <p>{provenancePresentation(provenance.status).explanation}</p>
                    {aiDeclarationCopy(provenance.ai_disclosures) && <p className={styles.aiDeclaration}>{aiDeclarationCopy(provenance.ai_disclosures)}</p>}
                    <p className={styles.caution}>{provenancePresentation(provenance.status).limitation}</p>
                    <details className={styles.offlineDetails}><summary>What does this mean?</summary><p>Content credentials can provide information about where an image came from or how it was edited. Their presence does not prove the event shown is true, and their absence does not mean an image is fake.</p><p>Technical details: credentials were checked on the uploaded file. Online certificate checks were not performed.</p></details>
                    {provenance.limitations.map((item) => <small className={styles.muted} key={item}>{safeEvidenceText(item)}</small>)}
                  </> : <p className={styles.muted}>{finished ? "No image origin information is available." : "Checking available origin information…"}</p>}
                </section>

                <section className={styles.mediaGroup} aria-labelledby="metadata-title">
                  <p className={styles.sectionKicker}>File information</p><h4 id="metadata-title">File details</h4>
                  {metadataEvidence.length ? metadataEvidence.map((item) => {
                    const fields = technicalMetadata(item.content);
                    return <div key={item.id}>{fields.length ? <dl className={styles.metadataList}>{fields.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl> : <p>Allowlisted technical metadata was examined.</p>}{item.limitations && <p className={styles.caution}>{safeEvidenceText(item.limitations)}</p>}</div>;
                  }) : <p className={styles.muted}>{finished ? "No useful file details are available." : "Reviewing file details…"}</p>}
                </section>

                <section className={styles.mediaGroup} aria-labelledby="visual-title">
                  <p className={styles.sectionKicker}>Visual review</p><h4 id="visual-title">What Agent 0 can see</h4>
                  {visualEvidence.length ? visualEvidence.flatMap((item): { observation: string; relevance: string; limitations: string[] }[] => visualObservations(item.content)).map((item, index) => <article className={styles.observation} key={`${item.observation}-${index}`}><span>OBSERVATION</span><p>{item.observation}</p>{item.relevance && <small>Relevance: {item.relevance}</small>}{item.limitations.map((limitation) => <small className={styles.caution} key={limitation}>{limitation}</small>)}</article>) : <p className={styles.muted}>{mediaNotice ? "Visual interpretation did not complete." : finished ? "No visual observations were recorded." : "Visual review is still in progress…"}</p>}
                  <p className={styles.caution}>Visual interpretation may be incomplete or mistaken; it is not forensic proof.</p>
                </section>
              </div>
            </section>}

            <section className={styles.limitations} aria-labelledby="limitations-title">
              <div><p className={styles.sectionKicker}>Read with care</p><h3 id="limitations-title">Limitations</h3></div>
              <ul>
                {presentedLimitations(results).map((item) => <li key={item}>{item}</li>)}
                {!results.brief?.limitations.length && !evidence.some((item) => item.limitations) && <li>{finished ? "Evidence collection is limited to the sources and media available in this investigation." : "Limitations will be summarized after the evidence review."}</li>}
                {originalMedia && <li>Reverse-image search was not performed.</li>}
              </ul>
            </section>

            <section id="brief" className={styles.brief} aria-labelledby="brief-title">
              <div className={styles.sectionHeading}><div><p className={styles.sectionKicker}>A newsroom-ready summary</p><h3 id="brief-title">Verification brief</h3></div></div>
              {results.brief && finished ? <>
                {claims.map((claim) => {
                  const finding = results.findings.find((item) => item.claim_id === claim.id);
                  const view = finding ? statusPresentation(finding.status) : null;
                  return <article className={styles.briefClaim} key={claim.id}><h4>Claim</h4><p>{safeEvidenceText(claim.text)}</p>{finding && <><h4>Status</h4><p>{view?.label} — {safeEvidenceText(finding.statement)}</p><h4>Key evidence</h4>{findingRelationship(finding, evidence).map(({ item, relationship }) => <a key={item.id} href={`#evidence-${item.id}`}>{relationshipPresentation(relationship)} · View cited evidence</a>)}</>}</article>;
                })}
                {claims.length === 0 && <article className={styles.briefClaim}><h4>{originalMedia && !content.trim() ? "Image review" : "Submitted question"}</h4><p>{content.trim() ? safeEvidenceText(content.trim()) : originalMedia ? "No claim or context is available for this image review. Available image signals do not establish where or when the depicted event occurred." : "No verifiable claim was extracted from this request."}</p><p>No factual finding was produced from the question alone.</p></article>}
                {originalMedia && <><h4>Image origin &amp; history</h4><p>{provenance ? `${provenancePresentation(provenance.status).label}. ${provenancePresentation(provenance.status).limitation}` : "An image was submitted; no origin information is available."}</p></>}
                <h4>Assessment summary</h4><p className={styles.briefSummary}>{safeEvidenceText(results.brief.summary)}</p>
                <h4>Unknowns</h4><ul>{unknowns.map((item) => <li key={item}>{item}</li>)}</ul>
                <h4>Recommended next steps</h4><ul>{nextSteps.length ? nextSteps.map((item) => <li key={item}>{item}</li>) : <li>Review all cited material with an editor.</li>}</ul>
                <h4>Limitations</h4><ul>{presentedLimitations(results).map((item) => <li key={item}>{item}</li>)}</ul>
              </> : <p className={styles.muted}>{finished ? "A verification brief is not available for this investigation." : "The brief will appear when evidence review is complete."}</p>}
            </section>
          </>}
        </section>}
      </div>
    </main>
  );
}
