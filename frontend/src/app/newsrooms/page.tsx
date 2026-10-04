import Link from "next/link";
import Image from "next/image";
import { Arrow } from "@/components/Arrow";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import styles from "../public.module.css";

const people = [
  ["01", "Journalists", "Check a claim or image before it moves into a story."],
  ["02", "Editors", "Review the material and its limits before making an editorial decision."],
  ["03", "Researchers & fact-checkers", "Compare accounts and keep a clear record of what was examined."],
  ["04", "Anyone checking information", "Understand what the available evidence can—and cannot—show."],
];

export default function NewsroomsPage() {
  return <main className={styles.page}><SiteHeader activeHref="/newsrooms" />
    <section className={styles.hero}><div className={`${styles.heroInner} ${styles.heroSplit}`}><div><p className={styles.eyebrow}>For newsrooms and beyond</p><h1>Make evidence easier to review.</h1><p>Agent 0 helps people checking fast-moving information see the sources, the result and the questions that remain.</p><Link href="/investigate" className="button button-primary">Start an investigation <Arrow /></Link><div className={styles.manifesto}><p>Evidence in view.<br />Human judgment in human hands.</p></div></div><figure className={styles.heroVisual}><Image src="/images/press-briefing.webp" alt="Journalists and cameras gathered at a press briefing" width={1500} height={1000} sizes="(max-width: 640px) 100vw, 48vw" priority /><figcaption>For reporters, editors, researchers and anyone checking information.</figcaption></figure></div></section>
    <section className={styles.section}><div className={styles.sectionInner}><h2>Useful wherever verification happens.</h2><p className={styles.intro}>The same careful questions matter in a newsroom, a research desk, a classroom, a public office or when deciding whether to share a message.</p><div className={styles.steps}>{people.map(([number, title, description]) => <article key={number}><span>{number}</span><h3>{title}</h3><p>{description}</p></article>)}</div></div></section>
    <section className={styles.sectionAlt}><div className={styles.sectionInner}><h2>Support the decision. Don’t make it for people.</h2><p className={styles.intro}>Agent 0 is an investigation aid. It organizes available information and keeps its limitations visible; it does not replace newsroom standards, expert review or personal judgment.</p><div className={styles.values}><article><h3>Before a story moves forward</h3><p>Review available sources and identify gaps that need follow-up.</p></article><article><h3>When an image raises questions</h3><p>Check attached origin details and visible observations in context.</p></article><article><h3>When accounts conflict</h3><p>See where reports agree, differ or appear to rely on the same source.</p></article><article><h3>When the answer is still unclear</h3><p>Keep “not established yet” distinct from a false claim.</p></article></div></div></section>
    <section className={styles.cta}><div className={styles.ctaInner}><div><h2>Bring a question into view.</h2><p>Investigate a claim, link or image.</p></div><Link href="/investigate" className="button button-primary">Investigate something <Arrow /></Link></div></section>
    <SiteFooter />
  </main>;
}
