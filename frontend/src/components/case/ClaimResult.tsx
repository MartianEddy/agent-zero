import { ArrowDown } from "lucide-react";
import { relationshipPresentation, safeEvidenceText, statusPresentation } from "@/app/investigate/presentation.mjs";
import type { Claim, Evidence, Finding } from "@/app/investigate/types";
import { Card } from "@/components/ui/card";
import { VerdictBadge } from "@/components/workspace/VerdictBadge";
import { CLAIM_TYPE_LABEL } from "@/lib/api";
import { cn } from "@/lib/utils";
import { citedEvidence } from "./model";

const STRENGTH = { LOW: 1, MEDIUM: 2, HIGH: 3 } as const;

function citationLabel(evidence: Evidence | undefined, fallback: number) {
  if (!evidence?.source?.url) return String(fallback);
  try { return new URL(evidence.source.url).hostname.replace(/^www\./, ""); } catch { return String(fallback); }
}

export function ClaimResult({ claim, finding, evidence, finished, dateBasis, onCite }: {
  claim: Claim; finding?: Finding; evidence: Evidence[]; finished: boolean; dateBasis: string | null; onCite: (evidenceId: string) => void;
}) {
  const cited = finding ? citedEvidence(finding, evidence) : [];
  const strength = finding?.evidence_confidence ? STRENGTH[finding.evidence_confidence] : 0;
  return (
    <Card className="overflow-hidden">
      <div className="border-b border-line bg-subtle/60 px-5 py-3 sm:px-6">
        <p className="text-xs font-semibold uppercase tracking-wider text-faint">Claim checked · {CLAIM_TYPE_LABEL[claim.type] ?? claim.type}</p>
      </div>
      <div className="grid gap-5 p-5 sm:p-6">
        <h2 className="text-xl font-semibold leading-snug sm:text-2xl">{safeEvidenceText(claim.text)}</h2>
        {dateBasis && <p className="rounded-md bg-subtle px-3 py-2 text-sm text-muted">{safeEvidenceText(dateBasis)}</p>}

        {finding ? (
          <>
            <div>
              <VerdictBadge status={finding.status} className="px-3 py-2 text-sm" />
              <p className="mt-3 max-w-2xl leading-7 text-muted">{statusPresentation(finding.status).explanation as string}</p>
            </div>

            <div className="max-w-2xl leading-7 text-ink-soft">
              {finding.explanation?.length ? finding.explanation.map((item, index) => (
                <span key={`${finding.id}-${index}`}>{safeEvidenceText(item.sentence)}{" "}
                  {item.evidence_ids.map((id, i) => <button key={id} type="button" onClick={() => onCite(id)} aria-label="Show the cited evidence" className="mx-0.5 inline-flex translate-y-[-1px] items-center rounded border border-line-strong bg-surface px-1.5 py-0.5 align-middle font-mono text-[11px] text-brand-ink hover:bg-brand-soft">{citationLabel(evidence.find((e) => e.id === id), i + 1)}</button>)}{" "}
                </span>
              )) : <p>{safeEvidenceText(finding.statement)}</p>}
            </div>
            {finding.unsupported_statements_removed && <p className="text-sm text-muted" role="status">Some statements were removed because they could not be tied to a source.</p>}

            {finding.evidence_confidence && (
              <div className="rounded-lg border border-line p-4">
                <div className="flex items-center gap-3">
                  <p className="text-sm font-semibold">Evidence strength: {finding.evidence_confidence.charAt(0) + finding.evidence_confidence.slice(1).toLowerCase()}</p>
                  <div className="flex gap-1" aria-hidden>{[1, 2, 3].map((n) => <span key={n} className={cn("h-1.5 w-7 rounded-full", n <= strength ? "bg-brand-ink" : "bg-line-strong")} />)}</div>
                </div>
                {finding.confidence_rationale && <p className="mt-2 text-sm leading-6 text-muted">{safeEvidenceText(finding.confidence_rationale)}</p>}
                <p className="mt-2 text-xs text-faint">This shows how much solid evidence was found. It is not the chance the claim is true.</p>
              </div>
            )}
            {finding.limitations && <p className="text-sm leading-6 text-muted">{safeEvidenceText(finding.limitations)}</p>}

            <div className="flex flex-wrap gap-2">
              {cited.length > 0 ? cited.map(({ item, relationship }) => (
                <button key={item.id} type="button" onClick={() => onCite(item.id)} className="inline-flex items-center gap-1.5 rounded-full border border-line-strong px-3 py-1.5 text-xs font-medium text-ink-soft hover:bg-subtle">
                  {relationshipPresentation(relationship) as string}<ArrowDown className="size-3" aria-hidden />
                </button>
              )) : <p className="text-sm text-muted">No retrieved passage was linked to this result. Search leads are listed under Evidence for reference only.</p>}
            </div>
          </>
        ) : <p className="text-muted">{finished ? "No result was recorded for this claim." : "Agent 0 is still working on this claim. The result will appear here."}</p>}
      </div>
    </Card>
  );
}
