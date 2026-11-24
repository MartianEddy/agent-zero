import { uploadErrorMessage } from "@/app/investigate/presentation.mjs";

export const ACTIVE_STATUSES = new Set(["RECEIVED", "PROCESSING", "ANALYZING", "RESEARCHING", "CORROBORATING", "GENERATING_BRIEF"]);

export async function readError(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "detail" in body) return uploadErrorMessage((body as { detail: unknown }).detail);
  } catch { /* fall through */ }
  return "The request could not be completed. Please try again.";
}

export function formatBytes(value: number) {
  if (value < 1024 * 1024) return `${Math.max(1, Math.round(value / 1024))} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function timeAgo(value: string) {
  const minutes = Math.round((new Date(value).getTime() - Date.now()) / 60_000);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  if (Math.abs(minutes) < 60) return formatter.format(minutes, "minute");
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return formatter.format(hours, "hour");
  return formatter.format(Math.round(hours / 24), "day");
}

export type HistoryItem = {
  id: string;
  reference: string;
  status: import("@/app/investigate/types").InvestigationStatus;
  input_type: import("@/app/investigate/types").InputType;
  current_stage: string;
  created_at: string;
  title: string;
  finding_status: import("@/app/investigate/types").FindingStatus | null;
  sources_count: number;
};

export const INPUT_TYPE_LABEL: Record<HistoryItem["input_type"], string> = {
  TEXT: "Claim", URL: "Link", IMAGE: "Image", VIDEO: "Video", AUDIO: "Audio", DOCUMENT: "Document",
};

export const CLAIM_TYPE_LABEL: Record<import("@/app/investigate/types").ClaimType, string> = {
  SETTLED_FACT: "Well-established fact",
  CHECKABLE_EVENT: "Specific event or statement",
  STATISTICAL: "Number or statistic",
  MEDIA_CLAIM: "Claim about an image or video",
  CONTESTED: "Disputed or debated",
  OPINION_OR_PREDICTION: "Opinion or prediction",
};
