import { Fragment } from "react";
import { cn } from "@/lib/utils";

type Bubble = { from: "me" | "agent"; text: string } | { from: "buttons"; labels: string[] };

const DEFAULT_CHAT: Bubble[] = [
  { from: "me", text: "Schools in Nyeri will stay closed tomorrow, is that true?" },
  { from: "agent", text: "Here is the claim I will check:\n\n- Schools in Nyeri County will remain closed tomorrow.\n\n*Nothing has started yet.* Tap a button below." },
  { from: "buttons", labels: ["Submit claim", "Edit claim", "Cancel"] },
  { from: "me", text: "Submit claim" },
  { from: "agent", text: "*Got it. I am checking this now.*\n\nIt usually takes a few minutes." },
  { from: "agent", text: "*Not enough evidence yet*\n\n*Claim:* Schools in Nyeri County will remain closed tomorrow.\n\n*Why:* No official announcement was found. That does not mean it did not happen." },
];

// Renders WhatsApp-style *bold*, as the real chat does.
function rich(text: string) {
  return text.split(/(\*[^*]+\*)/g).map((part, index) => (part.length > 2 && part.startsWith("*") && part.endsWith("*") ? <strong key={index}>{part.slice(1, -1)}</strong> : <Fragment key={index}>{part}</Fragment>));
}

export function ChatMock({ chat = DEFAULT_CHAT, className }: { chat?: Bubble[]; className?: string }) {
  return (
    <div role="img" aria-label="Example WhatsApp conversation with Agent 0" className={cn("w-full max-w-sm rounded-[28px] border border-line-strong bg-[#e8e3d8] p-3 shadow-pop", className)}>
      <div className="mb-3 flex items-center gap-3 rounded-[18px] bg-[#1d5a43] px-3.5 py-2.5 text-sm font-semibold text-white">
        <span className="grid size-8 place-items-center rounded-full bg-brand text-xs font-bold text-ink">A0</span>Agent 0
      </div>
      <div className="grid gap-2">
        {chat.map((item, index) => item.from === "buttons" ? (
          <div key={index} className="grid grid-cols-3 gap-1.5">{item.labels.map((label) => <span key={label} className="rounded-md bg-white px-1 py-2 text-center text-[11px] font-semibold text-[#1f6f8f] shadow-sm">{label}</span>)}</div>
        ) : (
          <div key={index} className={cn("max-w-[88%] whitespace-pre-line rounded-lg px-3 py-2 text-[13px] leading-[1.5] text-ink shadow-sm", item.from === "me" ? "justify-self-end bg-[#d8f5c3]" : "bg-white")}>{rich(item.text)}</div>
        ))}
      </div>
    </div>
  );
}
