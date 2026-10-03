import Link from "next/link";
import { Arrow } from "@/components/Arrow";
import { AgentMark } from "@/components/AgentMark";
import styles from "./page.module.css";

export default function InvestigatePage() {
  return <main className={styles.page}><header><Link href="/" aria-label="Return to Agent 0 home"><AgentMark /></Link><span className={styles.label}>INVESTIGATION WORKSPACE</span></header>
    <section><p className="eyebrow">Your next step</p><h1>The investigation workspace is being prepared.</h1><p>There is no live investigation service connected yet. When it is available, you&apos;ll be able to submit a claim and review its evidence here.</p><Link className="button button-primary" href="/">Return to Agent 0 <Arrow /></Link></section>
  </main>;
}
