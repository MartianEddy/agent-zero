import type { Metadata } from "next";
import Link from "next/link";
import { Arrow } from "@/components/Arrow";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import styles from "./page.module.css";

export const metadata: Metadata = { title: "Methodology and FAQ", description: "How Agent 0 is designed to trace sources, compare evidence, communicate uncertainty and support human editorial judgment." };

const principles = [
  ["Traceability", "Findings should link back to the material they rely on, with source identity and provenance made visible where available."],
  ["Independence", "Repeated reports are not automatically independent corroboration. The relationships between sources should be examined and stated."],
  ["Proportional conclusions", "A conclusion should reflect the strength and limits of the material reviewed. Missing evidence does not by itself disprove a claim."],
  ["Human review", "AI can help organize and compare material. People remain responsible for interpreting evidence and making editorial decisions."],
];
const questions = [
  ["What is Agent 0?", "Agent 0 is an AI-assisted verification workspace designed for the MCK, journalists, editors and media practitioners. It should help people investigate claims by tracing sources, comparing evidence, identifying gaps and preparing a reviewable brief. People remain responsible for editorial judgment."],
  ["Are the investigation and its numbers real?", "Yes. In the flow, a user submits a claim,text, link or media; Agent 0 breaks it into checkable details, gathers related sources, compares what they say, surfaces conflicts and gaps, and assembles a brief with evidence and uncertainty visible. This prototype does not perform those live checks yet."],
  ["How is a source considered independent?", "Agent 0 checks where each account got its information and whether multiple reports trace back to the same original source. Reports that repeat one statement should be grouped as a shared source trail, not counted as separate corroboration. The brief should show those relationships and leave independence uncertain when provenance cannot be established."],
  ["Does Agent 0 decide whether a claim is true?", "Agent 0 supports investigation and communicates evidence and uncertainty. Editorial conclusions remain with people who makes the judgment."],
  ["What happens to submitted material?", "Messages and images submitted through WhatsApp or the website are processed in memory to check them against known misinformation patterns and live fact-check databases they are not stored or logged anywhere in the current build. The system returns a report and discards the input. If we move beyond the hackathon prototype, any future logging (e.g. to track which misinformation patterns are actually circulating) would be anonymized and disclosed upfront, never tied to a sender's identity without consent."],
  ["Can my newsroom join a pilot?", "There's no formal pilot program running today. We're genuinely interested in partnering with newsrooms once the tool is further validated.If you'd like to be first in line when a pilot opens, reach out to us."],
];

export default function MethodologyPage() {
  return <main className={styles.page}><SiteHeader activeHref="/methodology" />
    <section className={styles.hero}><div className="container"><p className="eyebrow">Methodology & FAQ</p><h1>Make the evidence <span>inspectable.</span></h1><p>These are the principles the product is being designed around. The current website is a prototype; the method below describes intended practice, not a live system that has already been validated.</p></div></section>
    <section className={styles.principles}><div className="container"><p className={styles.darkEyebrow}>Design principles</p><h2>What a responsible brief should show.</h2><div className={styles.grid}>{principles.map(([title, text], i) => <article key={title}><span>0{i + 1}</span><h3>{title}</h3><p>{text}</p></article>)}</div></div></section>
    <section className={styles.faq}><div className="container"><p className={styles.darkEyebrow}>Frequently asked questions</p><h2>What to expect today.</h2><div className={styles.questions}>{questions.map(([q, a]) => <details key={q}><summary>{q}<span aria-hidden="true">+</span></summary><p>{a}</p></details>)}</div></div></section>
    <section className={styles.cta}><div className="container"><div><p className="eyebrow">See the interface</p><h2>Explore the sample investigation.</h2><p>All content is labeled as illustrative sample data.</p></div><Link href="/demo" className="button button-primary">Explore the demo <Arrow /></Link></div></section>
    <SiteFooter />
  </main>;
}
