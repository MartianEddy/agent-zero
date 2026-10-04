"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { AgentMark } from "@/components/AgentMark";
import { statusPresentation, safeEvidenceText } from "@/app/investigate/presentation.mjs";
import type { Investigation, Results } from "@/app/investigate/types";
import styles from "./history.module.css";

type HistoryItem = { investigation: Investigation; results: Results | null };
type Filter = "ALL" | "SUPPORTED" | "CONTRADICTED" | "UNVERIFIED" | "INCONCLUSIVE";

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
        const response = await fetch("/api/investigations", { cache: "no-store" });
        if (!response.ok) throw new Error("Investigation history couldn’t be loaded. Try again shortly.");
        const investigations = (await response.json()) as Investigation[];
        const recent = investigations.slice(0, 20);
        const values = await Promise.all(recent.map(async (investigation) => {
          const resultResponse = await fetch(`/api/investigations/${investigation.id}/results`, { cache: "no-store" });
          const results = resultResponse.ok ? (await resultResponse.json()) as Results : null;
          return { investigation, results };
        }));
        if (!cancelled) setItems(values);
      } catch (reason) {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Investigation history couldn’t be loaded.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    return () => { cancelled = true; };
  }, []);

  const filtered = useMemo(() => items.filter(({ investigation, results }) => {
    const title = results?.claims[0]?.text ?? (results?.media_assets?.length ? "Image investigation" : "Investigation");
    const status = results?.findings[0]?.status;
    return (filter === "ALL" || status === filter) && `${title} ${investigation.reference}`.toLowerCase().includes(query.toLowerCase());
  }), [items, query, filter]);

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
    <header className={styles.header}><Link href="/" aria-label="Agent 0 home"><AgentMark /></Link><nav aria-label="Main navigation"><Link href="/investigate">Investigate</Link><Link href="/investigations" aria-current="page">Investigations</Link><Link href="/how-it-works">How it works</Link></nav></header>
    <div className={styles.content}>
      <p className={styles.demoNotice}>Public demo workspace. Use public information only; investigation history is shared.</p>
      <div className={styles.titleRow}><div><p className={styles.eyebrow}>Your workspace</p><h1>Investigations</h1><p>Return to a claim, link or image you’ve already checked.</p></div><Link className="button button-primary" href="/investigate">New investigation <span aria-hidden="true">→</span></Link></div>

      <form className={styles.referenceLookup} onSubmit={reopenByReference}>
        <div><h2>Reopen an investigation</h2><p>Enter the reference shown when you submitted it.</p></div>
        <label htmlFor="reference-lookup">Investigation reference</label>
        <div className={styles.referenceControls}><input id="reference-lookup" value={reference} onChange={(event) => setReference(event.target.value.toUpperCase())} placeholder="AZ-261004-ABC123" autoCapitalize="characters" autoComplete="off" required /><button className="button button-secondary" type="submit" disabled={referenceBusy}>{referenceBusy ? "Finding…" : "Open case"}</button></div>
        {referenceError && <p className={styles.referenceError} role="alert">{referenceError}</p>}
      </form>

      <div className={styles.controls}><label className={styles.searchLabel} htmlFor="history-search">Search investigations</label><input id="history-search" type="search" placeholder="Search by claim or reference" value={query} onChange={(event) => setQuery(event.target.value)} /><div className={styles.filters} role="group" aria-label="Filter by result">{(["ALL", "SUPPORTED", "CONTRADICTED", "UNVERIFIED", "INCONCLUSIVE"] as const).map((item) => <button key={item} type="button" aria-pressed={filter === item} onClick={() => setFilter(item)}>{item === "ALL" ? "All results" : statusPresentation(item).label}</button>)}</div></div>

      {loading ? <div className={styles.loading} aria-live="polite">Loading investigations…</div> : error ? <div className={styles.empty} role="alert"><p>{error}</p><button type="button" onClick={() => window.location.reload()}>Try again</button></div> : items.length === 0 ? <div className={styles.empty}><h2>No investigations yet.</h2><p>Check a claim, link or image to get started.</p><Link href="/investigate">Start an investigation →</Link></div> : filtered.length === 0 ? <div className={styles.empty}><h2>No matching investigations.</h2><p>Try a different search or result filter.</p></div> : <ul className={styles.list}>
        {filtered.map(({ investigation, results }) => {
          const claim = results?.claims[0]?.text;
          const image = results?.media_assets?.some((asset) => asset.role.toUpperCase() === "ORIGINAL");
          const status = results?.findings[0]?.status;
          return <li key={investigation.id}><Link className={styles.item} href={`/investigate?investigation=${encodeURIComponent(investigation.id)}`}>
            <span className={styles.typeIcon} aria-hidden="true">{image ? "▧" : "“ ”"}</span>
            <span className={styles.mainText}><strong>{safeEvidenceText(claim || (image ? "Image investigation" : "Investigation in progress"))}</strong><small>{image ? "Image" : results?.sources.length ? "Claim · source checks" : "Claim"}{results?.sources.length ? ` · ${results.sources.length} sources` : ""}{investigation.status !== "COMPLETE" ? ` · ${stageLabel(investigation.status)}` : ""}</small></span>
            <span className={`${styles.result} ${status ? statusTone(status) : ""}`}>{status ? statusPresentation(status).label : investigation.status === "COMPLETE" ? "No finding" : "In progress"}</span>
            <time dateTime={investigation.created_at}>{relativeDate(investigation.created_at)}</time>
          </Link></li>;
        })}
      </ul>}
    </div>
  </main>;
}

function stageLabel(status: string) {
  if (["FAILED", "NEEDS_REVIEW"].includes(status)) return "Review needed";
  return "In progress";
}

function statusTone(status: string) {
  if (status === "SUPPORTED") return styles.statusSupported;
  if (status === "CONTRADICTED") return styles.statusContradicted;
  if (status === "UNVERIFIED") return styles.statusUnverified;
  return styles.statusInconclusive;
}
