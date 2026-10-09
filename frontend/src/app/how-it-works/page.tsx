import Link from "next/link";
import { Arrow } from "@/components/Arrow";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import styles from "../public.module.css";

const steps = [
  ["01", "Bring in the material", "Start with a claim, a public link or an image or short video with a factual question."],
  ["02", "Review the claim", "Agent 0 proposes one or more checkable claims. Edit or split them before research starts."],
  ["03", "Follow the available sources", "The workspace distinguishes retrieved material from source leads and shows when a step could not run."],
  ["04", "Compare what was found", "Review the evidence links, source relationships, limitations and questions that remain."],
  ["05", "Make the human decision", "Use the case record to guide your next reporting, research or editorial step."],
];

export default function HowItWorksPage() {
  return <main className={styles.page}><SiteHeader activeHref="/how-it-works" />
    <section className={styles.hero}><div className={styles.heroInner}><p className={styles.eyebrow}>How it works</p><h1>From a question to evidence you can inspect.</h1><p>Agent 0 makes its work easier to follow, so people can see what was checked and where the gaps remain.</p><Link href="/investigate" className="button button-primary">Try an investigation <Arrow /></Link></div></section>
    <section className={styles.section}><div className={styles.sectionInner}><p className={styles.eyebrow}>Five deliberate steps</p><h2>A clear path through the investigation.</h2><p className={styles.intro}>The claim stays visible as the case moves from triage to evidence review, so people can see what was checked at each stage.</p><div className={styles.steps}>{steps.map(([number, title, description]) => <article key={number}><span>{number}</span><h3>{title}</h3><p>{description}</p></article>)}</div></div></section>
    <section className={styles.sectionAlt}><div className={styles.sectionInner}><h2>A result is a starting point for human judgment.</h2><p className={styles.intro}>A missing source does not make a claim false. A source count is not a verdict. If Agent 0 cannot establish something, that uncertainty should remain visible.</p><div className={styles.values}><article><h3>What supports the claim</h3><p>See evidence that supports or agrees with what was submitted.</p></article><article><h3>What challenges the claim</h3><p>Review reliable material that points in another direction.</p></article><article><h3>What adds context</h3><p>Understand information that may help interpret a claim without settling it.</p></article><article><h3>What to check next</h3><p>Use open questions and suggested actions to continue your work.</p></article></div></div></section>
    <section className={styles.cta}><div className={styles.ctaInner}><div><h2>See what Agent 0 can examine.</h2><p>Start with a question, claim or image.</p></div><Link href="/investigate" className="button button-primary">Investigate something <Arrow /></Link></div></section>
    <SiteFooter />
  </main>;
}
