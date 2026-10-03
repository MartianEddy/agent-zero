import Link from "next/link";
import type { Metadata } from "next";
import { Arrow } from "@/components/Arrow";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import styles from "./page.module.css";

export const metadata: Metadata = { title: "About", description: "Learn about Agent 0, an AI-assisted verification workspace in development for journalists, editors and fact-checkers." };

const principles = [
  ["01", "Assume nothing", "Treat every claim as something to investigate. Start from the evidence, not the conclusion you expect."],
  ["02", "Show the trail", "Keep sources and the path between a claim and its evidence visible for review."],
  ["03", "Respect uncertainty", "Make gaps and conflicts clear. An absence of evidence is not evidence that a claim is false."],
  ["04", "Keep people accountable", "Use AI to support investigation. Leave editorial judgment and decisions with people."],
];

export default function AboutPage() {
  return <main className={styles.page}><SiteHeader activeHref="/about" />
    <section className={styles.hero}><div className="container"><p className="eyebrow">About Agent 0</p><h1>Information deserves<br />to be <span>investigated.</span></h1><p>Agent 0 is an AI-assisted verification workspace in development for journalists, editors, fact-checkers and newsrooms.</p><div className={styles.manifesto}><span className={styles.manifestoZero}>0</span><p>Assume nothing.<br /><b>Follow the evidence.</b></p></div></div></section>
    <section className={styles.mission}><div className="container"><div><p className={styles.darkEyebrow}>Why Agent 0</p><h2>Help people follow<br />information to its sources.</h2></div><div><p>Claims can move quickly between people and platforms. The work of checking them takes time: finding sources, comparing accounts, checking provenance and making uncertainty explicit.</p><p>Agent 0 is being built to organize that work in one place, so people can examine the evidence and make informed decisions.</p></div></div></section>
    <section className={styles.principles}><div className="container"><p className={styles.darkEyebrow}>The principles</p><h2>AI investigates.<br /><span>Humans decide.</span></h2><div className={styles.grid}>{principles.map(([number, title, text]) => <article key={number}><span>{number}</span><h3>{title}</h3><p>{text}</p></article>)}</div></div></section>
    <section className={styles.cta}><div className="container"><div><p className="eyebrow">Follow the evidence</p><h2>Explore a sample investigation.</h2><p>See how the intended workspace presents its evidence.</p></div><Link href="/demo" className="button button-primary">Explore the demo <Arrow /></Link></div></section>
    <SiteFooter />
  </main>;
}
