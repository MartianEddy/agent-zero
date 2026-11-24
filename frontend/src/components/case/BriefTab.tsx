import { relationshipPresentation, safeEvidenceText, statusPresentation } from "@/app/investigate/presentation.mjs";
import type { Results } from "@/app/investigate/types";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Card, CardBody } from "@/components/ui/card";
import { citedEvidence, type CaseModel } from "./model";

export function BriefTab({ results, model }: { results: Results; model: CaseModel }) {
  if (!results.brief || !model.finished) return <p className="text-sm text-muted">{model.finished ? "A summary is not available for this check." : "The summary will appear when the review is complete."}</p>;
  return (
    <div className="grid max-w-3xl gap-5">
      <p className="text-sm leading-6 text-muted">A short, shareable summary of this check. It is a starting point for your own judgment, not a final ruling.</p>
      {model.claims.map((claim) => {
        const finding = results.findings.find((f) => f.claim_id === claim.id);
        const cited = finding ? citedEvidence(finding, model.evidence) : [];
        return (
          <Card key={claim.id}><CardBody className="grid gap-3 text-sm leading-6">
            <div><p className="text-xs font-semibold uppercase tracking-wider text-faint">Claim</p><p className="mt-0.5 font-medium">{safeEvidenceText(claim.text)}</p></div>
            {finding && <>
              <div><p className="text-xs font-semibold uppercase tracking-wider text-faint">Result</p><p className="mt-0.5">{statusPresentation(finding.status).label as string}. {safeEvidenceText(finding.statement)}</p></div>
              {finding.evidence_confidence && <div><p className="text-xs font-semibold uppercase tracking-wider text-faint">Evidence strength</p><p className="mt-0.5">{finding.evidence_confidence.charAt(0) + finding.evidence_confidence.slice(1).toLowerCase()}{finding.confidence_rationale ? `. ${safeEvidenceText(finding.confidence_rationale)}` : ""}</p></div>}
              {cited.length > 0 && <div><p className="text-xs font-semibold uppercase tracking-wider text-faint">Key sources</p><ul className="mt-0.5 grid gap-1">{cited.map(({ item, relationship }) => <li key={item.id}>{relationshipPresentation(relationship) as string}: {item.source ? <a className="font-medium text-brand-ink underline underline-offset-4" href={item.source.url} target="_blank" rel="noreferrer">{item.source.url}</a> : "attached evidence"}</li>)}</ul></div>}
            </>}
          </CardBody></Card>
        );
      })}
      {model.claims.length === 0 && <Card><CardBody className="text-sm leading-6">{safeEvidenceText(results.brief.summary)}</CardBody></Card>}
      {model.claims.length > 0 && <Card><CardBody><p className="text-xs font-semibold uppercase tracking-wider text-faint">Summary</p><p className="mt-1 text-sm leading-6">{safeEvidenceText(results.brief.summary)}</p></CardBody></Card>}
      <Accordion type="single" collapsible>
        <AccordionItem value="limits"><AccordionTrigger>Limitations and review notes</AccordionTrigger><AccordionContent><ul className="list-disc pl-5">{model.limitations.map((item) => <li key={item}>{item}</li>)}{model.limitations.length === 0 && <li>Evidence collection is limited to the sources and media available in this check.</li>}</ul></AccordionContent></AccordionItem>
      </Accordion>
    </div>
  );
}
