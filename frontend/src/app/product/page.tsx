import Link from "next/link";
import { Arrow } from "@/components/Arrow";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import styles from "./page.module.css";

const features = [
  ["01", "Trace sources", "Follow a claim back to original sources where available, and see where information has been repeated."],
  ["02", "Compare evidence", "Review source accounts together to find agreement, conflict and missing context."],
  ["03", "Analyze media", "Bring images, audio, video and documents into the investigation alongside text claims."],
  ["04", "Keep a timeline", "Understand how a claim developed and which events or reports came first."],
  ["05", "Preserve uncertainty", "See what is supported, what conflicts and what still needs verification."],
  ["06", "Build a verification brief", "Organize findings, evidence and recommended next steps in a clear summary."],
];

export default function ProductPage() {
  return <main className={styles.page}><SiteHeader activeHref="/product" />
    <section className={styles.hero}><div className="container"><p className="eyebrow">Product</p><h1>A transparent investigation workspace <span>for journalists.</span></h1><p>Investigate claims, trace sources, compare evidence and prepare a verification brief with the evidence visible at every step.</p><Link href="/investigate" className="button button-primary">Start investigating <Arrow /></Link>
      <div className={styles.workspace} aria-label="Example evidence overview interface"><div className={styles.workspaceTop}><b>AGENT <span>0</span></b><small>INVESTIGATION / SAMPLE</small><i>UNVERIFIED</i></div><div className={styles.workspaceClaim}>Claim under investigation<h2>“Schools in Nyeri County will remain closed tomorrow.”</h2><p>Evidence is currently insufficient to verify this claim.</p></div><div className={styles.metrics}><div><b>8</b><span>Sources examined</span></div><div><b>3</b><span>Independent sources</span></div><div><b>0</b><span>Original sources located</span></div></div><div className={styles.findings}><h3>Evidence at a glance</h3><p><i /> No official statement located</p><p><i /> Local media reporting, but no primary source</p><p><i /> Earlier reports contain conflicting information</p></div></div>
    </div></section>
    <section className={styles.features}><div className="container"><p className={styles.darkEyebrow}>A considered set of tools</p><h2>Everything in the investigation,<br />with its context intact.</h2><div className={styles.grid}>{features.map(([number, title, text]) => <article key={number}><span>{number}</span><h3>{title}</h3><p>{text}</p></article>)}</div></div></section>
    <section className={styles.principle}><div className="container"><p className="eyebrow">The product principle</p><h2>Evidence should be inspectable.</h2><p>Agent 0 is intended to make the path from claim to evidence easier to follow. It supports analysis without turning uncertainty into a score or conclusion that asks to be trusted blindly.</p></div></section>
    <section className={styles.cta}><div className="container"><div><p className="eyebrow">Ready when you are</p><h2>Start with the claim.</h2><p>Bring the information you need to investigate.</p></div><Link href="/investigate" className="button button-primary">Start investigating <Arrow /></Link></div></section>
    <SiteFooter />
  </main>;
}
