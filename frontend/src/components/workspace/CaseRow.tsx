import Link from "next/link";
import { FileText, Image as ImageIcon, Link2, Video } from "lucide-react";
import { safeEvidenceText } from "@/app/investigate/presentation.mjs";
import { ACTIVE_STATUSES, INPUT_TYPE_LABEL, timeAgo, type HistoryItem } from "@/lib/api";
import { StateBadge, VerdictBadge } from "./VerdictBadge";

function displayTitle(item: HistoryItem) {
  const raw = (item.title || "").trim();
  if (/^https?:\/\//i.test(raw)) {
    try { return `Link from ${new URL(raw).hostname.replace(/^www\./, "")}`; } catch { return "Submitted link"; }
  }
  return safeEvidenceText(raw || "Untitled check") as string;
}

const ICONS = { TEXT: FileText, URL: Link2, IMAGE: ImageIcon, VIDEO: Video, AUDIO: FileText, DOCUMENT: FileText } as const;

export function CaseRow({ item }: { item: HistoryItem }) {
  const Icon = ICONS[item.input_type] ?? FileText;
  const attention = item.status === "FAILED" || item.status === "NEEDS_REVIEW";
  return (
    <Link href={`/investigations/${encodeURIComponent(item.id)}`} className="group flex items-center gap-4 px-4 py-3.5 transition-colors hover:bg-subtle sm:px-5">
      <span className="grid size-9 shrink-0 place-items-center rounded-md bg-subtle text-muted group-hover:bg-surface"><Icon className="size-4" aria-hidden /></span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[15px] font-medium text-ink">{displayTitle(item)}</span>
        <span className="mt-0.5 block truncate font-mono text-xs text-faint">{item.reference} · {INPUT_TYPE_LABEL[item.input_type]}{item.sources_count ? ` · ${item.sources_count} sources` : ""} · {timeAgo(item.created_at)}</span>
      </span>
      <span className="shrink-0">
        {item.finding_status ? <VerdictBadge status={item.finding_status} short />
          : <StateBadge kind={ACTIVE_STATUSES.has(item.status) ? "active" : attention ? "attention" : "none"} />}
      </span>
    </Link>
  );
}
