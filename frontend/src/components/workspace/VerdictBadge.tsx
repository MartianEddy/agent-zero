import { CircleDashed, LoaderCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { FindingStatus } from "@/app/investigate/types";
import { verdictView } from "@/lib/verdict";

export function VerdictBadge({ status, short = false, className }: { status: FindingStatus; short?: boolean; className?: string }) {
  const view = verdictView(status);
  const Icon = view.icon;
  return <Badge tone={view.tone} className={className}><Icon aria-hidden />{short ? view.short : view.label}</Badge>;
}

export function StateBadge({ kind }: { kind: "active" | "attention" | "none" }) {
  if (kind === "active") return <Badge tone="info"><LoaderCircle className="animate-spin" aria-hidden />In progress</Badge>;
  if (kind === "attention") return <Badge tone="mixed">Needs attention</Badge>;
  return <Badge><CircleDashed aria-hidden />No finding</Badge>;
}
