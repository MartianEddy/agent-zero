"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { WorkspaceHeader } from "@/components/WorkspaceHeader";
import { statusPresentation, safeEvidenceText } from "@/app/investigate/presentation.mjs";
import type { Investigation, InvestigationStatus, InputType, FindingStatus } from "@/app/investigate/types";
import styles from "./history.module.css";

type HistoryItem = {
  id: string;
  reference: string;
  status: InvestigationStatus;
  input_type: InputType;
  current_stage: string;
  created_at: string;
  title: string;
  finding_status: FindingStatus | null;
  sources_count: number;
};
type Filter = "ALL" | FindingStatus;

function relativeDate(value: string) {
  const minutes = Math.round((new Date(value).getTime() - Date.now()) / 60_000);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  if (Math.abs(minutes) < 60) return formatter.format(minutes, "minute");
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return formatter.format(hours, "hour");
  return formatter.format(Math.round(hours / 24), "day");
}

export default function InvestigationsPage() {
  const router = useRouter();
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [query, setQuery] = useState("");
  const [reference, setReference] = useState("");
  const [referenceBusy, setReferenceBusy] = useState(false);
  const [referenceError, setReferenceError] = useState("");
  const [filter, setFilter] = useState<Filter>("ALL");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const response = await fetch("/api/investigations/history", { cache: "no-store" });
        if (!response.ok) throw new Error("Investigation history couldn’t be loaded. Try again shortly.");
        const history = (await response.json()) as HistoryItem[];
        if (!cancelled) setItems(history);
      } catch (reason) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Investigation history couldn’t be loaded.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, []);

  const filtered = useMemo(() => items.filter((item) =>
    (filter === "ALL" || item.finding_status === filter) && `${item.title} ${item.reference}`.toLowerCase().includes(query.toLowerCase()),
  ), [items, query, filter]);

  async function reopenByReference(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setReferenceBusy(true);
    setReferenceError("");
    try {
      const response = await fetch(`/api/investigations/reference?reference=${encodeURIComponent(reference)}`, { cache: "no-store" });
      if (!response.ok) {
        const payload = await response.json().catch(() => null) as { detail?: string } | null;
        throw new Error(payload?.detail || "We couldn’t find an investigation with that reference.");
      }
      const investigation = await response.json() as Investigation;
      router.push(`/investigate?investigation=${encodeURIComponent(investigation.id)}`);
    } catch (reason) {
      setReferenceError(reason instanceof Error ? reason.message : "We couldn’t find that investigation. Try again.");
    } finally {
      setReferenceBusy(false);
    }
  }

  return <main className={styles.page}>
    <WorkspaceHeader activeHref="/investigations" />
    <div className={styles.content}>
      <p className={styles.demoNotice}>Shared public demo. Other visitors can view this investigation history. Use public information only.</p>
      <div className={styles.titleRow}><div><p className={styles.eyebrow}>Public demo history</p><h1>Investigations</h1><p>Reopen a claim, source, image, or video checked in this demo.</p></div><Link className="button button-primary" href="/investigate">New investigation <span aria-hidden="true">→</span></Link></div>

      <form className={styles.referenceLookup} onSubmit={reopenByReference}>
        <div><h2>Reopen an investigation</h2><p>Enter the reference shown when you submitted it.</p></div>
        <label htmlFor="reference-lookup">Investigation reference</label>
        <div className={styles.referenceControls}><input id="reference-lookup" value={reference} onChange={(event) => setReference(event.target.value.toUpperCase())} placeholder="AZ-261004-ABC123" autoCapitalize="characters" autoComplete="off" required /><button className="button button-secondary" type="submit" disabled={referenceBusy}>{referenceBusy ? "Finding…" : "Open case"}</button></div>
        {referenceError && <p className={styles.referenceError} role="alert">{referenceError}</p>}
      </form>

      <div className={styles.controls}><label className={styles.searchLabel} htmlFor="history-search">Search recent investigations</label><input id="history-search" type="search" placeholder="Search by claim or reference" value={query} onChange={(event) => setQuery(event.target.value)} /><div className={styles.filters} role="group" aria-label="Filter by result">{(["ALL", "SUPPORTED", "CONTRADICTED", "PARTLY_TRUE", "INSUFFICIENT_EVIDENCE", "NOT_VERIFIABLE"] as const).map((item) => <button key={item} type="button" aria-pressed={filter === item} onClick={() => setFilter(item)}>{item === "ALL" ? "All results" : statusPresentation(item).label}</button>)}</div></div>
      {items.length === 50 && <p className={styles.loading}>Showing the latest 50 cases. Use an investigation reference to reopen an older case.</p>}

      {loading ? <div className={styles.loading} aria-live="polite">Loading investigations…</div> : error ? <div className={styles.empty} role="alert"><p>{error}</p><button type="button" onClick={() => window.location.reload()}>Try again</button></div> : items.length === 0 ? <div className={styles.empty}><h2>No investigations yet.</h2><p>Check a claim, link or image to get started.</p><Link href="/investigate">Start an investigation →</Link></div> : filtered.length === 0 ? <div className={styles.empty}><h2>No matching investigations.</h2><p>Try a different search or result filter.</p></div> : <ul className={styles.list}>
        {filtered.map((item) => {
          const status = item.finding_status;
          return <li key={item.id}><Link className={styles.item} href={`/investigate?investigation=${encodeURIComponent(item.id)}`}>
            <span className={styles.typeIcon} aria-hidden="true">{item.input_type === "IMAGE" ? "▧" : item.input_type === "VIDEO" ? "▣" : "“ ”"}</span>
            <span className={styles.mainText}><strong>{safeEvidenceText(item.title || "Investigation")}</strong><small>{inputTypeLabel(item.input_type)}{item.sources_count ? ` · ${item.sources_count} sources` : ""}{item.status !== "COMPLETE" ? ` · ${stageLabel(item.status)}` : ""}</small></span>
            <span className={`${styles.result} ${status ? statusTone(status) : ""}`}>{status ? statusPresentation(status).label : item.status === "COMPLETE" ? "No finding" : "In progress"}</span>
            <time dateTime={item.created_at}>{relativeDate(item.created_at)}</time>
          </Link></li>;
        })}
      </ul>}
    </div>
  </main>;
}

function inputTypeLabel(inputType: InputType) {
  const labels: Record<InputType, string> = {
    TEXT: "Claim",
    URL: "Public source",
    IMAGE: "Image",
    VIDEO: "Video",
    AUDIO: "Audio",
    DOCUMENT: "Document",
  };
  return labels[inputType];
}

function stageLabel(status: string) {
  if (["FAILED", "NEEDS_REVIEW"].includes(status)) return "Review needed";
  return "In progress";
}

function statusTone(status: string) {
  if (status === "SUPPORTED") return styles.statusSupported;
  if (status === "CONTRADICTED") return styles.statusContradicted;
  if (status === "PARTLY_TRUE") return styles.statusPartlyTrue;
  if (status === "NOT_VERIFIABLE") return styles.statusNotVerifiable;
  return styles.statusInsufficient;
}
