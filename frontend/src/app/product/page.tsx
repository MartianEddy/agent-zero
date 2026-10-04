import Link from "next/link";
import Image from "next/image";
import { Arrow } from "@/components/Arrow";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import styles from "../public.module.css";

const capabilities = [
  ["01", "Check a claim", "Bring a question or statement into an investigation and see what available evidence supports or challenges it."],
  ["02", "Review a link", "Examine public reporting and follow important findings back to the source."],
  ["03", "Examine an image", "Review image origin information, useful file details and visible observations—alongside their limits."],
  ["04", "Prepare a brief", "Bring together the result, key evidence, open questions and useful next steps."],
];

export default function ProductPage() {
  return <main className={styles.page}><SiteHeader activeHref="/product" />
    <section className={styles.hero}><div className={`${styles.heroInner} ${styles.heroSplit}`}><div><p className={styles.eyebrow}>Product</p><h1>Investigate information before you rely on it.</h1><p>Agent 0 helps people review questionable claims, links and images by gathering available evidence in one readable workspace.</p><Link href="/investigate" className="button button-primary">Investigate something <Arrow /></Link></div><figure className={styles.heroVisual}><Image src="/images/reporter-interview.webp" alt="A journalist interviews a subject on camera" width={1500} height={1000} sizes="(max-width: 640px) 100vw, 48vw" priority /><figcaption>Start with a question. Follow the evidence.</figcaption></figure></div></section>
    <section className={styles.section}><div className={styles.sectionInner}><h2>Start with what you have.</h2><p className={styles.intro}>Paste a claim, add a public link, or upload an image. Agent 0 routes the material to the checks it can perform.</p><div className={styles.steps}>{capabilities.map(([number, title, description]) => <article key={number}><span>{number}</span><h3>{title}</h3><p>{description}</p></article>)}</div></div></section>
    <section className={styles.sectionAlt}><div className={styles.sectionInner}><h2>See the evidence. Keep the uncertainty.</h2><p className={styles.intro}>Results are designed to help a person understand what was found, why it matters, and what still needs checking.</p><div className={styles.values}><article><h3>Sources you can inspect</h3><p>Follow key findings to the sources and material reviewed.</p></article><article><h3>Clear, measured results</h3><p>Understand what evidence supports, challenges or cannot resolve.</p></article><article><h3>Image details in context</h3><p>Learn what attached credentials and file information can tell you—and what they cannot.</p></article><article><h3>People make the decision</h3><p>Agent 0 supports review. Editorial and personal decisions stay with people.</p></article></div></div></section>
    <section className={styles.cta}><div className={styles.ctaInner}><div><h2>Bring something you want to check.</h2><p>Start with a claim, a public link or an image.</p></div><Link href="/investigate" className="button button-primary">Start investigating <Arrow /></Link></div></section>
    <SiteFooter />
  </main>;
}
