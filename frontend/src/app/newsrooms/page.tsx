import Link from "next/link";
import type { Metadata } from "next";
import { Arrow } from "@/components/Arrow";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import styles from "./page.module.css";

export const metadata: Metadata = { title: "For Newsrooms", description: "How Agent 0 is being designed to support journalists, editors and fact-checkers with transparent evidence trails." };

const roles = [
  ["01", "Journalists", "Check claims, trace original sources and understand what is known before a story moves forward."],
  ["02", "Editors", "Review the material behind a claim and make editorial decisions with its limits in view."],
  ["03", "Fact-checkers", "Record evidence, compare accounts and keep a transparent trail for further review."],
  ["04", "Newsrooms", "Support a shared approach to verification across reporting and editorial work."],
];

export default function NewsroomsPage() {
  return <main className={styles.page}><SiteHeader activeHref="/newsrooms" />
    <section className={styles.hero}><div className="container"><p className="eyebrow">For newsrooms</p><h1>Make room for<br /><span>better verification.</span></h1><p>Agent 0 is being designed for the people who investigate information under real editorial pressure: journalists, editors and fact-checkers.</p><Link href="/demo" className="button button-primary">Explore the sample <Arrow /></Link>
      <div className={styles.quote}><span>THE WORK</span><p>Follow the trail.<br />Keep the uncertainty visible.</p><div className={styles.quoteRing}>0<i /><i /><i /></div></div>
    </div></section>
    <section className={styles.roles}><div className="container"><p className={styles.darkEyebrow}>Designed around newsroom roles</p><h2>Support every step<br />of the verification process.</h2><div className={styles.grid}>{roles.map(([number, title, text]) => <article key={number}><span>{number}</span><h3>{title}</h3><p>{text}</p></article>)}</div></div></section>
    <section className={styles.workflow}><div className="container"><div><p className="eyebrow">A practical workflow companion</p><h2>Evidence in view.<br />Editorial judgment in human hands.</h2></div><div><p>Agent 0 is intended to help organize a verification process, make source relationships easier to review and document what the evidence can and cannot establish.</p><p>The current workspace is a prototype. Team management, newsroom integrations, collaboration and live investigations are not available.</p></div></div></section>
    <section id="pilot" className={styles.pilot}><div className="container"><div><p className="eyebrow">Pilot readiness</p><h2>Designed with newsroom needs in mind.</h2><p>A real pilot should make its data handling, source coverage, review process and limitations clear before a newsroom relies on it.</p></div><ul><li>Agree which claims and formats are in scope.</li><li>Review source attribution and evidence trails with editors.</li><li>Set expectations for privacy, retention and access.</li><li>Keep editorial sign-off with the newsroom.</li></ul><p className={styles.pilotNote}>Pilot intake is not open yet. This prototype has no contact form or connected service for receiving requests.</p></div></section>
    <section className={styles.cta}><div className="container"><div><p className="eyebrow">Assume nothing</p><h2>Explore the sample case.</h2><p>See the intended evidence review flow.</p></div><Link href="/demo" className="button button-primary">Explore the demo <Arrow /></Link></div></section>
    <SiteFooter />
  </main>;
}
