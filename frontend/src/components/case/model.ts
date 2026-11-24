import {
  findingEvidenceReferences, presentedLimitations, recommendedNextSteps, relativeDateBasis,
  sourceResearchLane, unknownsFromResults, visualAnalysisNotice,
} from "@/app/investigate/presentation.mjs";
import type { Evidence, Finding, Investigation, Results, Source } from "@/app/investigate/types";
import { ACTIVE_STATUSES } from "@/lib/api";

export type CitedEvidence = { item: Evidence; relationship: string };

export function citedEvidence(finding: Finding, evidence: Evidence[]): CitedEvidence[] {
  const links = findingEvidenceReferences(finding, evidence) as Evidence[];
  const byId = new Map(links.map((item) => [item.id, item]));
  return finding.evidence_ids.flatMap((id) => {
    const item = byId.get(id);
    if (!item) return [];
    const relationship = item.claim_links.find((link) => link.claim_id === finding.claim_id)?.relationship;
    return [{ item, relationship: relationship ?? "UNKNOWN" }];
  });
}

export function buildCaseModel(investigation: Investigation, results: Results | null) {
  const finished = !ACTIVE_STATUSES.has(investigation.status);
  const completed = investigation.status === "COMPLETE";
  const claims = results?.claims ?? [];
  const evidence = (results?.evidence ?? []).filter((item) => item.method !== "MEDIA_FINGERPRINT");
  const mediaEvidence = evidence.filter((item) => Boolean(item.media_asset));
  const mediaAssets = results?.media_assets ?? mediaEvidence.flatMap((item) => (item.media_asset ? [item.media_asset] : []));
  const originalImage = mediaAssets.find((asset) => asset.media_type === "IMAGE" && asset.role.toUpperCase() === "ORIGINAL");
  const originalVideo = mediaAssets.find((asset) => asset.media_type === "VIDEO" && asset.role.toUpperCase() === "ORIGINAL");
  const provenance = mediaEvidence.find((item) => item.provenance)?.provenance ?? null;

  const traces = results?.search_traces ?? [];
  const providerName = (provider: string) => provider.replaceAll("_", " ").toLowerCase();
  const failedProviders = [...new Set(traces.filter((t) => ["unavailable", "error", "budget_exceeded"].includes(t.action)).map((t) => providerName(t.provider)))];
  const searchedProviders = [...new Set(traces.filter((t) => ["search", "empty"].includes(t.action)).map((t) => providerName(t.provider)))];
  const laneNames = { PRIMARY: "official records", REFERENCE_REPORTING: "independent reporting", FACT_CHECK: "earlier fact-checks", SOCIAL: "social sources" } as const;
  const lanes = [...new Set(traces.filter((t) => ["search", "empty"].includes(t.action)).map((t) => t.route?.source_lane).filter((lane): lane is keyof typeof laneNames => Boolean(lane)))].map((lane) => laneNames[lane]);

  const sources = results?.sources ?? [];
  const sourceGroups = results ? ([
    { lane: "RECENT" as const, title: "Recent coverage", sources: sources.filter((s) => sourceResearchLane(s, traces) === "RECENT") },
    { lane: "HISTORICAL" as const, title: "Historical context", sources: sources.filter((s) => sourceResearchLane(s, traces) === "HISTORICAL") },
    { lane: "OTHER" as const, title: "Other sources found", sources: sources.filter((s) => sourceResearchLane(s, traces) === "OTHER") },
  ].filter((group) => group.sources.length > 0)) : [];

  const retrievalDisabled = Boolean(results?.usage_summary?.limitations.some((item) => item.includes("Source retrieval is disabled")));
  const readerReason = sources.find((s: Source) => s.retrieval_failure_reason)?.retrieval_failure_reason;
  const readerFailure = readerReason === "JINA_RATE_LIMITED" ? "The page reader hit a rate limit, so source pages could not be opened. Please retry in a few minutes."
    : readerReason === "JINA_QUOTA_EXHAUSTED" ? "The page reader has run out of capacity, so source pages could not be opened. Please try again later."
    : readerReason === "JINA_AUTHENTICATION_FAILED" ? "The page reader could not sign in, so source pages could not be opened. This is a configuration problem on our side."
    : null;

  return {
    finished, completed, claims, evidence, mediaEvidence, originalImage, originalVideo, provenance,
    failedProviders, searchedProviders, lanes, sourceGroups, retrievalDisabled, readerFailure,
    unretrieved: sources.filter((s) => s.retrieval_status !== "RETRIEVED").length,
    unknowns: results ? (unknownsFromResults(results, finished) as string[]) : [],
    nextSteps: results ? (recommendedNextSteps(results, finished) as string[]) : [],
    limitations: results ? (presentedLimitations(results) as string[]) : [],
    mediaNotice: results ? (visualAnalysisNotice(results) as string | null) : null,
    dateBasis: relativeDateBasis(claims.map((c) => c.text).join(" "), investigation.created_at) as string | null,
    searchUnavailable: failedProviders.length > 0 && searchedProviders.length === 0,
  };
}
export type CaseModel = ReturnType<typeof buildCaseModel>;
