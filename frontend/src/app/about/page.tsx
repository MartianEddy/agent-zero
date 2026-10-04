import Link from "next/link";
import { Arrow } from "@/components/Arrow";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import styles from "../public.module.css";

const principles = [
  ["01", "Start with evidence", "Treat a question as something to examine, not a conclusion to confirm."],
  ["02", "Show the way through", "Help people follow important findings back to what was reviewed."],
  ["03", "Respect uncertainty", "Keep missing information and conflicting accounts visible."],
  ["04", "Leave decisions with people", "Use AI to support investigation while people remain accountable."],
];

export default function AboutPage() {
  return <main className={styles.page}><SiteHeader activeHref="/about" />
    <section className={styles.hero}><div className={styles.heroInner}><p className={styles.eyebrow}>About Agent 0</p><h1>The internet doesn’t need another AI telling people what to believe.</h1><p>It needs better tools for examining evidence.</p><div className={styles.manifesto}><p>Assume nothing.<br /><strong>Follow the evidence.</strong></p></div></div></section>
    <section className={styles.section}><div className={styles.sectionInner}><h2>Why Agent 0 exists.</h2><p className={styles.intro}>Information can move quickly between people and platforms. Checking it takes deliberate work: finding sources, comparing accounts, understanding media and being clear about what remains unknown. Agent 0 is being built to make that work easier to follow.</p><div className={styles.steps}>{principles.map(([number, title, description]) => <article key={number}><span>{number}</span><h3>{title}</h3><p>{description}</p></article>)}</div></div></section>
    <section className={styles.sectionAlt}><div className={styles.sectionInner}><p className={styles.eyebrow}>The principle</p><h2>AI investigates.<br />Humans decide.</h2><p className={styles.intro}>A result should come with the evidence behind it, the limitations that matter and a clear view of what could not be established.</p></div></section>
    <section className={styles.cta}><div className={styles.ctaInner}><div><h2>Follow a question where the evidence leads.</h2><p>Start with a claim, a link or an image.</p></div><Link href="/investigate" className="button button-primary">Start investigating <Arrow /></Link></div></section>
    <SiteFooter />
  </main>;
}
