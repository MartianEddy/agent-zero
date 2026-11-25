"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";
import { CircleHelp, FileSearch, Link2, LoaderCircle, Pencil, Scale, Send } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const STEPS = [
  { title: "Share it", text: "Paste a claim or a link, or add an image. Type it the way you would say it." },
  { title: "Review the claim", text: "Agent 0 shows exactly what it understood. You edit it and confirm. Nothing starts before that." },
  { title: "It finds the sources", text: "Official records first, then independent reporting. It opens each page and reads the passages." },
  { title: "You get a plain answer", text: "A clear result, how strong the evidence is, what is still unknown, and every source to open." },
] as const;

const CLAIM = "Kenya's population is 60 million people.";

function Window({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <div className="overflow-hidden rounded-xl border border-night-line bg-night-2 shadow-pop" role="img" aria-label={label}>
      <div className="flex items-center gap-1.5 border-b border-night-line bg-night-3/70 px-4 py-2.5">
        <span className="size-2.5 rounded-full bg-coral/80" /><span className="size-2.5 rounded-full bg-amber/80" /><span className="size-2.5 rounded-full bg-brand/80" />
        <span className="ml-3 truncate font-mono text-[11px] text-white/40">agent0.app / new check</span>
      </div>
      <div className="min-h-[300px] p-5 sm:p-6">{children}</div>
    </div>
  );
}

function ShareScreen() {
  return (
    <div className="grid gap-4">
      <p className="text-sm font-semibold text-white">What do you want to check?</p>
      <div className="rounded-lg border border-night-line bg-night p-4 text-[15px] leading-7 text-white/90">{CLAIM}<span className="ml-0.5 inline-block h-5 w-px translate-y-1 animate-pulse bg-brand" /></div>
      <div className="flex flex-wrap gap-2 text-xs text-white/60"><span className="rounded-full border border-night-line px-3 py-1.5">Add image or video</span><span className="rounded-full border border-night-line px-3 py-1.5">Paste a link</span></div>
      <div className="mt-2 flex justify-end"><span className="inline-flex items-center gap-2 rounded-md bg-brand px-4 py-2.5 text-sm font-semibold text-ink">Review claim <Send className="size-4" /></span></div>
    </div>
  );
}
function ReviewScreen() {
  return (
    <div className="grid gap-4">
      <p className="text-sm font-semibold text-white">Review what will be checked</p>
      <div className="rounded-lg border border-brand/40 bg-brand/5 p-4">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-brand">Claim 1 · Number or statistic</p>
        <p className="mt-1.5 text-[15px] leading-7 text-white">{CLAIM}</p>
        <span className="mt-2 inline-flex items-center gap-1.5 text-xs text-white/50"><Pencil className="size-3" /> You can edit or split this</span>
      </div>
      <p className="text-xs text-white/50">Nothing has started yet.</p>
      <div className="mt-1 flex justify-end"><span className="inline-flex items-center gap-2 rounded-md bg-brand px-4 py-2.5 text-sm font-semibold text-ink">Confirm and start checking</span></div>
    </div>
  );
}
function ResearchScreen() {
  const rows = [
    { name: "KNBS: 2019 Census results", tag: "Official record", state: "Page read", ok: true },
    { name: "Nation Africa: population estimate", tag: "News report", state: "Page read", ok: true },
    { name: "Social post about population", tag: "Social media", state: "Lead only", ok: false },
  ];
  return (
    <div className="grid gap-4">
      <div className="flex items-center gap-3 text-sm font-semibold text-white"><LoaderCircle className="size-4 animate-spin text-brand" /> Reading sources</div>
      <ul className="grid gap-2.5">
        {rows.map((row, index) => (
          <motion.li key={row.name} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.15 * index }} className="flex items-center gap-3 rounded-lg border border-night-line bg-night p-3">
            <FileSearch className="size-4 shrink-0 text-white/40" aria-hidden />
            <div className="min-w-0 flex-1"><p className="truncate text-sm text-white">{row.name}</p><p className="text-xs text-white/45">{row.tag}</p></div>
            <span className={cn("rounded-full px-2.5 py-1 text-[11px] font-semibold", row.ok ? "bg-brand/15 text-brand" : "bg-amber/15 text-amber")}>{row.state}</span>
          </motion.li>
        ))}
      </ul>
      <div className="h-1.5 overflow-hidden rounded-full bg-night-3"><motion.div className="h-full bg-gradient-to-r from-brand to-teal" initial={{ width: "10%" }} animate={{ width: "78%" }} transition={{ duration: 3.2 }} /></div>
    </div>
  );
}
function ResultScreen() {
  return (
    <div className="grid gap-4">
      <p className="text-sm text-white/60">{CLAIM}</p>
      <Badge tone="unknown" className="w-fit px-3 py-2 text-[13px]"><CircleHelp /> Not enough evidence yet</Badge>
      <p className="text-sm leading-6 text-white/80">The latest census counted about 47.6 million people. Projections are lower than 60 million, but they are estimates.</p>
      <div className="flex items-center gap-3 rounded-lg border border-night-line bg-night p-3"><Scale className="size-4 text-brand" aria-hidden /><div className="text-sm text-white">Evidence strength: <strong>Low</strong></div><div className="ml-auto flex gap-1">{[1, 2, 3].map((n) => <span key={n} className={cn("h-1.5 w-6 rounded-full", n === 1 ? "bg-brand" : "bg-night-line")} />)}</div></div>
      <div className="flex flex-wrap gap-2 text-xs"><span className="inline-flex items-center gap-1.5 rounded-full border border-night-line px-3 py-1.5 text-white/70"><Link2 className="size-3" /> knbs.or.ke</span><span className="inline-flex items-center gap-1.5 rounded-full border border-night-line px-3 py-1.5 text-white/70"><Link2 className="size-3" /> nation.africa</span></div>
    </div>
  );
}

const SCREENS = [<ShareScreen key="s" />, <ReviewScreen key="r" />, <ResearchScreen key="x" />, <ResultScreen key="y" />];
const LABELS = ["Step 1: type or paste a claim", "Step 2: review the claim", "Step 3: sources being read", "Step 4: the result"];

export function FlowDemo() {
  const reduce = useReducedMotion();
  const [active, setActive] = useState(0);
  const [hold, setHold] = useState(false);

  useEffect(() => {
    if (reduce || hold) return;
    const timer = window.setTimeout(() => setActive((value) => (value + 1) % STEPS.length), 5200);
    return () => window.clearTimeout(timer);
  }, [active, hold, reduce]);

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:items-center" onPointerEnter={() => setHold(true)} onPointerLeave={() => setHold(false)}>
      <ol className="grid gap-3">
        {STEPS.map((step, index) => (
          <li key={step.title}>
            <button type="button" onClick={() => setActive(index)} aria-current={active === index ? "step" : undefined}
              className={cn("group relative w-full overflow-hidden rounded-xl border p-4 text-left transition-colors sm:p-5", active === index ? "border-brand/50 bg-night-2 text-white shadow-glow" : "border-line bg-surface hover:border-line-strong")}>
              <div className="flex items-start gap-4">
                <span className={cn("grid size-9 shrink-0 place-items-center rounded-full font-mono text-sm font-semibold", active === index ? "bg-brand text-ink" : "bg-subtle text-muted")}>{index + 1}</span>
                <div>
                  <h3 className={cn("text-base font-semibold", active === index ? "text-white" : "text-ink")}>{step.title}</h3>
                  <p className={cn("mt-1 text-sm leading-6", active === index ? "text-white/70" : "text-muted")}>{step.text}</p>
                </div>
              </div>
              {active === index && !reduce && !hold && <motion.span key={`${active}-bar`} className="absolute bottom-0 left-0 h-0.5 bg-brand" initial={{ width: 0 }} animate={{ width: "100%" }} transition={{ duration: 5.2, ease: "linear" }} />}
            </button>
          </li>
        ))}
      </ol>
      <Window label={LABELS[active]}>
        <AnimatePresence mode="wait">
          <motion.div key={active} initial={reduce ? false : { opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={reduce ? undefined : { opacity: 0, y: -8 }} transition={{ duration: 0.25 }}>{SCREENS[active]}</motion.div>
        </AnimatePresence>
      </Window>
    </div>
  );
}

