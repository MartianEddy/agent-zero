import { CircleCheck, CircleHelp, CircleX, MessageSquareQuote, Scale, type LucideIcon } from "lucide-react";
import { statusPresentation } from "@/app/investigate/presentation.mjs";
import type { BadgeTone } from "@/components/ui/badge";
import type { FindingStatus } from "@/app/investigate/types";

export type VerdictView = { label: string; short: string; tone: BadgeTone; icon: LucideIcon; meaning: string };

const META: Record<FindingStatus, { short: string; tone: BadgeTone; icon: LucideIcon; meaning: string }> = {
  SUPPORTED: { short: "Supported", tone: "ok", icon: CircleCheck, meaning: "Independent sources back the claim." },
  CONTRADICTED: { short: "Challenged", tone: "bad", icon: CircleX, meaning: "Independent sources challenge the claim." },
  PARTLY_TRUE: { short: "Partly supported", tone: "mixed", icon: Scale, meaning: "Some parts hold up and others do not." },
  INSUFFICIENT_EVIDENCE: { short: "Not enough evidence", tone: "unknown", icon: CircleHelp, meaning: "Not enough solid evidence either way. This is not the same as false." },
  NOT_VERIFIABLE: { short: "Not checkable", tone: "opinion", icon: MessageSquareQuote, meaning: "An opinion or prediction, so it cannot be fact-checked." },
};

export const VERDICT_ORDER: FindingStatus[] = ["SUPPORTED", "CONTRADICTED", "PARTLY_TRUE", "INSUFFICIENT_EVIDENCE", "NOT_VERIFIABLE"];

export function verdictView(status: FindingStatus): VerdictView {
  // The long label comes from presentation.mjs so web and WhatsApp share one wording.
  return { label: statusPresentation(status).label as string, ...META[status] };
}
