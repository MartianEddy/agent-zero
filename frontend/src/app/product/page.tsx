import Link from "next/link";
import Image from "next/image";
import { Arrow } from "@/components/Arrow";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import styles from "../public.module.css";

const capabilities = [
  ["01", "Shape the claim first", "Review, edit or split the proposed claims before Agent 0 starts its source research."],
  ["02", "Follow a public source", "Review retrieved material separately from search leads and open the original source."],
  ["03", "Inspect media in context", "Review bounded image or video checks while keeping file details and visual observations distinct from verification."],
  ["04", "Review the case", "See findings, evidence links, source relationships, limitations and a verification brief in one place."],
];

export default function ProductPage() {
  return <main className={styles.page}><SiteHeader activeHref="/product" />
    <section className={styles.hero}><div className={`${styles.heroInner} ${styles.heroSplit}`}><div><p className={styles.eyebrow}>Product</p><h1>Investigate information before you rely on it.</h1><p>Agent 0 helps people review questionable claims, links and images by gathering available evidence in one readable workspace.</p><Link href="/investigate" className="button button-primary">Investigate something <Arrow /></Link></div><figure className={styles.heroVisual}><Image src="/images/reporter-interview.webp" alt="A journalist interviews a subject on camera" width={1500} height={1000} sizes="(max-width: 640px) 100vw, 48vw" priority /><figcaption>Start with a question. Follow the evidence.</figcaption></figure></div></section>
    <section className={styles.section}><div className={styles.sectionInner}><p className={styles.eyebrow}>One clear path</p><h2>Start with what you have.</h2><p className={styles.intro}>Paste a factual claim or public link, or attach an image or short video with the claim you want examined. Agent 0 pauses for claim review before source research begins.</p><div className={styles.steps}>{capabilities.map(([number, title, description]) => <article key={number}><span>{number}</span><h3>{title}</h3><p>{description}</p></article>)}</div></div></section>
    <section className={styles.sectionAlt}><div className={styles.sectionInner}><h2>See the evidence. Keep the uncertainty.</h2><p className={styles.intro}>Results are designed to help a person understand what was found, why it matters, and what still needs checking.</p><div className={styles.values}><article><h3>Sources you can inspect</h3><p>Follow key findings to the sources and material reviewed.</p></article><article><h3>Clear, measured results</h3><p>Understand what evidence supports, challenges or cannot resolve.</p></article><article><h3>Image details in context</h3><p>Learn what attached credentials and file information can tell you—and what they cannot.</p></article><article><h3>People make the decision</h3><p>Agent 0 supports review. Editorial and personal decisions stay with people.</p></article></div></div></section>
    <section className={styles.cta}><div className={styles.ctaInner}><div><h2>Bring something you want to check.</h2><p>Start with a claim, a public link or an image.</p></div><Link href="/investigate" className="button button-primary">Start investigating <Arrow /></Link></div></section>
    <SiteFooter />
  </main>;
}
