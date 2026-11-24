import { ExternalLink, FileSearch } from "lucide-react";
import {
  aiDeclarationCopy, provenancePresentation, publicationDateLabel, relationshipPresentation, safeEvidenceText,
  technicalMetadata, visualObservations,
} from "@/app/investigate/presentation.mjs";
import type { Evidence, Results, Source } from "@/app/investigate/types";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { CaseModel } from "./model";

export type EvidenceFilter = "ALL" | "SUPPORTS" | "CONTRADICTS" | "CONTEXT";
const FILTERS: EvidenceFilter[] = ["ALL", "SUPPORTS", "CONTRADICTS", "CONTEXT"];

const ROLE_LABEL: Record<string, string> = {
  PRIMARY: "Official or original", AUTHORITATIVE: "Authoritative", INDEPENDENT: "Independent reporting", DERIVATIVE: "Based on another source", SECONDARY: "Secondary source",
};

export function EvidenceCard({ item, relationship, showSourceLink = true }: { item: Evidence; relationship?: string; showSourceLink?: boolean }) {
  const isMetadata = item.method === "MEDIA_TECHNICAL_METADATA" || item.method === "MEDIA_METADATA";
  const metadata = isMetadata ? (technicalMetadata(item.content) as [string, string][]) : [];
  const observations = item.method === "MEDIA_VISUAL_OBSERVATION" ? (visualObservations(item.content) as { observation: string }[]) : [];
  const provenance = item.method === "MEDIA_PROVENANCE" ? provenancePresentation(item.provenance?.status) : null;
  const family = item.source ? "Passage from a source" : item.method === "MEDIA_PROVENANCE" ? "Origin and history" : isMetadata ? "File details" : item.method === "MEDIA_VISUAL_OBSERVATION" ? "What Agent 0 can see" : "Evidence reviewed";
  return (
    <article id={`evidence-${item.id}`} className="scroll-mt-24 rounded-lg border border-line bg-bg p-4 target:ring-2 target:ring-brand-ink">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-faint">{family}</span>
        {relationship && <Badge tone={relationship === "SUPPORTS" ? "ok" : relationship === "CONTRADICTS" ? "bad" : "neutral"}>{relationshipPresentation(relationship) as string}</Badge>}
      </div>
      <div className="text-sm leading-6 text-ink-soft">
        {isMetadata ? (metadata.length ? <dl className="grid gap-1.5 sm:grid-cols-2">{metadata.map(([label, value]) => <div key={label}><dt className="text-xs text-faint">{label}</dt><dd>{value}</dd></div>)}</dl> : <p>No useful file details were available.</p>)
          : item.method === "MEDIA_VISUAL_OBSERVATION" ? (observations.length ? observations.map((o, i) => <p key={i}>{o.observation}</p>) : <p>No visual notes were recorded.</p>)
          : provenance ? <p>{provenance.explanation as string} {aiDeclarationCopy(item.provenance?.ai_disclosures ?? []) as string}</p>
          : <p>{safeEvidenceText(item.content)}</p>}
      </div>
      {item.source && (
        <dl className="mt-3 grid gap-x-6 gap-y-1 border-t border-line pt-3 text-xs text-muted sm:grid-cols-2">
          <div className="flex gap-2"><dt className="text-faint">Published</dt><dd>{item.published_date ? ((publicationDateLabel(item.published_date) as string | null) || item.published_date) : "Date unavailable"}{item.is_stale === true ? " (may be outdated)" : ""}</dd></div>
          <div className="flex gap-2"><dt className="text-faint">Passage check</dt><dd>{item.excerpt_validated ? "Matched to the page" : "Could not be matched"}</dd></div>
        </dl>
      )}
      {item.limitations && <p className="mt-2 text-xs text-muted">{safeEvidenceText(item.limitations)}</p>}
      {showSourceLink && item.source && <a className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-brand-ink hover:underline" href={item.source.url} target="_blank" rel="noreferrer">Open source <ExternalLink className="size-3.5" aria-hidden /></a>}
    </article>
  );
}

function SourceCard({ source, evidence, relationships, sources, lane }: { source: Source; evidence: Evidence[]; relationships: Results["source_relationships"]; sources: Source[]; lane: "RECENT" | "HISTORICAL" | "OTHER" }) {
  const excerpts = evidence.filter((item) => item.source?.id === source.id);
  const related = relationships.filter((r) => r.source_id === source.id || r.related_source_id === source.id);
  const retrieved = source.retrieval_status === "RETRIEVED";
  const failed = source.retrieval_status === "FAILED";
  return (
    <Card className="p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium text-faint">{safeEvidenceText(source.publisher || source.domain || source.source_type)}</p>
          <h4 className="mt-0.5 text-[15px] font-semibold leading-snug">{safeEvidenceText(source.title || source.url)}</h4>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {lane !== "OTHER" && <Badge tone="info">{lane === "RECENT" ? "Recent" : "Historical"}</Badge>}
          <Badge>{ROLE_LABEL[source.source_role] ?? "Source"}</Badge>
          <Badge tone={retrieved ? "ok" : failed ? "bad" : "mixed"}>{retrieved ? "Page read" : failed ? "Could not open" : "Lead only"}</Badge>
        </div>
      </div>
      <p className="mt-2 text-xs text-muted">{source.published_at ? `Published ${(publicationDateLabel(source.published_at) as string | null) ?? "date unavailable"}` : "Publication date unavailable"}{source.author ? ` · ${safeEvidenceText(source.author)}` : ""}</p>
      {source.discovery_method === "SUBMITTED_URL" && <p className="mt-2 text-xs text-muted">This is the page you submitted. Its claims are context, not independent evidence.</p>}
      {source.discovery_method === "MODEL_PROPOSED" && <p className="mt-2 text-xs text-muted">Suggested during the check. Agent 0 could not confirm it in the recorded search results.</p>}
      {failed && <p className="mt-2 text-xs text-muted">Agent 0 could not open this page.</p>}
      {source.authoritative_for.length > 0 && <p className="mt-2 text-xs text-muted">Relevant to: {safeEvidenceText(source.authoritative_for.join("; "))}</p>}
      {related.length > 0 && <ul className="mt-2 grid gap-0.5 text-xs text-muted" aria-label="Source relationships">{related.map((r, i) => { const otherId = r.source_id === source.id ? r.related_source_id : r.source_id; const other = sources.find((s) => s.id === otherId); return <li key={i}>{relationshipPresentation(r.relationship) as string}: {other ? safeEvidenceText(other.title || other.domain || "related source") : "related source"}</li>; })}</ul>}
      <div className="mt-3 grid gap-3">
        {excerpts.length ? excerpts.map((item) => <EvidenceCard key={item.id} item={item} relationship={item.claim_links[0]?.relationship} showSourceLink={false} />) : <p className="text-sm text-muted">No relevant passage from this source is available.</p>}
      </div>
      <a className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-brand-ink hover:underline" href={source.url} target="_blank" rel="noreferrer">Open source <ExternalLink className="size-3.5" aria-hidden /></a>
    </Card>
  );
}

export function EvidenceTab({ results, model, filter, onFilter }: { results: Results; model: CaseModel; filter: EvidenceFilter; onFilter: (filter: EvidenceFilter) => void }) {
  const passes = (item: Evidence) => {
    if (filter === "ALL") return true;
    const links = item.claim_links.map((l) => l.relationship);
    if (filter === "SUPPORTS") return links.includes("SUPPORTS");
    if (filter === "CONTRADICTS") return links.includes("CONTRADICTS");
    return links.some((v) => ["CONTEXTUALIZES", "MENTIONS", "UNKNOWN"].includes(v));
  };
  const filtered = model.evidence.filter(passes);
  const sourceEvidence = filtered.filter((item) => Boolean(item.source));
  const other = filtered.filter((item) => !item.source && !item.media_asset);
  const hasOther = model.evidence.some((item) => !item.source && !item.media_asset);
  const coverage = results.evidence_coverage;
  const allRetrieved = results.sources.length > 0 && results.sources.every((s) => s.retrieval_status === "RETRIEVED");

  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">{allRetrieved ? "Sources reviewed" : "Sources found"}</h2>
        <div role="group" aria-label="Filter evidence" className="flex flex-wrap gap-2">
          {FILTERS.map((item) => (
            <button key={item} type="button" aria-pressed={filter === item} onClick={() => onFilter(item)}
              className={cn("h-8 rounded-full border border-line-strong bg-surface px-3 text-xs font-semibold text-muted hover:bg-subtle", filter === item && "border-ink bg-ink text-white hover:bg-ink")}>
              {item === "ALL" ? "All" : item === "CONTEXT" ? "Context" : (relationshipPresentation(item) as string)}
            </button>
          ))}
        </div>
      </div>

      <p className="text-sm leading-6 text-muted">
        {model.searchedProviders.length ? `Searched with ${model.searchedProviders.join(" and ")}. ` : "Searches have not returned yet. "}
        {model.lanes.length ? `Looked at ${model.lanes.join(", then ")}. ` : "Official records come first. "}
        Search results are only leads until the page is opened and read. Agent 0 does not search logged-in pages or social feeds.
      </p>
      {model.readerFailure && <Alert tone="warn">{model.readerFailure}</Alert>}
      {model.failedProviders.length > 0 && results.sources.length > 0 && <Alert tone="warn">Could not search {model.failedProviders.join(" and ")}, so results from {model.searchedProviders.join(" and ") || "the available providers"} may be incomplete.</Alert>}
      {!model.retrievalDisabled && model.unretrieved > 0 && <Alert tone="info">{coverage.sources_retrieved === 0 ? "No source pages were opened in this check. What you see are search leads only: titles and dates are not evidence." : "Some results are leads only. Their titles and dates are not evidence until the page is opened and read."}</Alert>}
      {model.retrievalDisabled && <Alert tone="info">Search found candidates, but page reading is switched off for this run. Titles are not evidence.</Alert>}

      {results.sources.length > 0 ? model.sourceGroups.map((group) => (
        <section key={group.lane} className="grid gap-3" aria-label={group.title}>
          <h3 className="text-sm font-semibold uppercase tracking-wider text-faint">{group.title}</h3>
          {group.sources.map((source) => <SourceCard key={source.id} source={source} evidence={sourceEvidence} relationships={results.source_relationships} sources={results.sources} lane={group.lane} />)}
        </section>
      )) : (
        <Card className="flex items-start gap-3 p-5 text-sm text-muted">
          <FileSearch className="mt-0.5 size-5 shrink-0 text-faint" aria-hidden />
          <p>{!model.finished ? "Source checks are still in progress. Results will appear here." : model.searchUnavailable ? `Search could not be completed by ${model.failedProviders.join(" and ")}. No outside sources were assessed. This does not tell us whether the claim is true or false.` : "No sources were found for this check. That does not tell us whether the claim is true or false."}</p>
        </Card>
      )}

      {hasOther && (
        <section className="grid gap-3" aria-label="Other evidence checked">
          <h3 className="text-sm font-semibold uppercase tracking-wider text-faint">Other evidence checked</h3>
          {other.length ? other.map((item) => <EvidenceCard key={item.id} item={item} relationship={item.claim_links[0]?.relationship} />) : <p className="text-sm text-muted">Nothing else matches this filter.</p>}
        </section>
      )}
    </div>
  );
}
