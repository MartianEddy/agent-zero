import { CircleHelp, ExternalLink } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";

export function ResultPreview() {
  return (
    <Card className="overflow-hidden shadow-card">
      <div className="flex items-center justify-between border-b border-line bg-subtle px-5 py-2.5">
        <span className="text-xs font-semibold uppercase tracking-wider text-faint">Illustrative example</span>
        <span className="text-xs text-faint">Not a live check</span>
      </div>
      <div className="p-5 sm:p-6">
        <p className="text-xs font-semibold uppercase tracking-wider text-faint">Claim</p>
        <p className="mt-1 text-lg font-semibold leading-snug">Schools in Nyeri County will remain closed tomorrow.</p>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Badge tone="unknown" className="py-1.5 text-[13px]"><CircleHelp /> Not enough evidence yet</Badge>
          <span className="text-sm text-muted">Evidence strength: <strong className="text-ink">Low</strong></span>
        </div>
        <p className="mt-4 text-sm leading-6 text-muted">We could not confirm the announcement from the sources reviewed. That does not mean it did not happen.</p>
        <dl className="mt-5 grid gap-3 border-t border-line pt-5 text-sm sm:grid-cols-2">
          <div><dt className="font-semibold">Official sources</dt><dd className="mt-0.5 text-muted">No matching announcement found.</dd></div>
          <div><dt className="font-semibold">Independent reporting</dt><dd className="mt-0.5 text-muted">Some reports repeat the same notice.</dd></div>
          <div><dt className="font-semibold">Still unknown</dt><dd className="mt-0.5 text-muted">Who first shared the notice.</dd></div>
          <div><dt className="font-semibold">Suggested next step</dt><dd className="mt-0.5 text-muted">Check with the county education office before sharing.</dd></div>
        </dl>
        <p className="mt-5 inline-flex items-center gap-1.5 text-sm font-semibold text-brand-ink">Every result links to its sources <ExternalLink className="size-3.5" /></p>
      </div>
    </Card>
  );
}
