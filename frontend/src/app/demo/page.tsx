import type { Metadata } from "next";
import Link from "next/link";
import { Arrow } from "@/components/Arrow";
import { InvestigationDemo } from "@/components/InvestigationDemo";
import { QuickCheckDemo } from "@/components/QuickCheckDemo";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import styles from "./page.module.css";

export const metadata: Metadata = { title: "Explore the sample investigation", description: "Explore an illustrative Agent 0 investigation, including evidence notes, source trail and a sample verification brief." };

export default function DemoPage() {
  return <main className={styles.page}><SiteHeader activeHref="/demo" />
    <section className={styles.hero}><div className="container"><p className="eyebrow">Product preview</p><h1>See how an investigation <span>takes shape.</span></h1><p>Explore a fictional, illustrative case. Switch between the overview, evidence notes, source trail and brief.</p><span className={styles.badge}>SAMPLE DATA · NOT LIVE OR VERIFIED</span></div></section>
    <QuickCheckDemo />
    <InvestigationDemo />
    <section className={styles.cta}><div className="container"><div><p className="eyebrow">For newsroom teams</p><h2>Interested in a pilot?</h2><p>Learn about the current prototype and pilot considerations.</p></div><Link href="/newsrooms#pilot" className="button button-primary">Explore newsroom pilots <Arrow /></Link></div></section>
    <SiteFooter />
  </main>;
}
