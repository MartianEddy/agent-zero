import Link from "next/link";
import { Arrow } from "@/components/Arrow";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import styles from "./page.module.css";

const steps = [
  ["01", "Submit", "Paste a claim or link, or provide an image, video, audio clip or document."],
  ["02", "Decompose", "Identify the individual claims, people, places and context that need to be checked."],
  ["03", "Investigate", "Search relevant sources and gather material connected to the claim."],
  ["04", "Corroborate", "Compare independent accounts and note where they agree, diverge or leave gaps."],
  ["05", "Trace", "Follow information toward its origin and record how the claim has spread."],
  ["06", "Build a brief", "Bring together evidence, unknowns and suggested next verification steps."],
];

export default function HowItWorksPage() {
  return <main className={styles.page}><SiteHeader activeHref="/how-it-works" />
    <section className={styles.hero}><div className="container"><p className="eyebrow">How it works</p><h1>From a claim<br />to a <span>clear briefing.</span></h1><p>Agent 0 follows a transparent, step-by-step process to investigate claims, trace sources, compare evidence and preserve what remains unknown.</p><Link href="/investigate" className="button button-primary">Start investigating <Arrow /></Link>
      <div className={styles.progress} aria-label="Six stages from claim submission to verification brief">{steps.map(([number, title], index) => <div key={number}><span>{number}</span><b>{title}</b>{index < steps.length - 1 && <i />}</div>)}</div>
    </div></section>
    <section className={styles.detail}><div className="container"><p className={styles.darkEyebrow}>The process</p><h2>Every step leaves a trail.</h2><div className={styles.steps}>{steps.map(([number, title, text]) => <article key={number}><span>{number}</span><div><h3>{title}</h3><p>{text}</p></div></article>)}</div></div></section>
    <section className={styles.evidence}><div className="container"><div><p className="eyebrow">Keep the evidence visible</p><h2>Uncertainty is part<br />of the finding.</h2></div><div className={styles.evidenceCopy}><p>A source count is not a verdict. A missing source does not make a claim false. The briefing should show the material examined, distinguish independent sources and make contradictions and gaps easy to spot.</p><ul><li>Evidence remains traceable to its source.</li><li>Conflicting accounts remain visible.</li><li>Conclusions stay proportional to the evidence.</li></ul></div></div></section>
    <section className={styles.cta}><div className="container"><div><p className="eyebrow">Follow the evidence</p><h2>Start with what you know.</h2><p>Bring a claim or source into an investigation.</p></div><Link href="/investigate" className="button button-primary">Start an investigation <Arrow /></Link></div></section>
    <SiteFooter />
  </main>;
}
