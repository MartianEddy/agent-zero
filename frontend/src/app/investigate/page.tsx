import Link from "next/link";
import { Arrow } from "@/components/Arrow";
import { AgentMark } from "@/components/AgentMark";
import styles from "./page.module.css";

export default function InvestigatePage() {
  return <main className={styles.page}><header><Link href="/" aria-label="Return to Agent 0 home"><AgentMark /></Link><span className={styles.label}>PROTOTYPE</span></header>
    <section><p className="eyebrow">No live service connected</p><h1>The investigation workspace is a prototype.</h1><p>This site cannot accept claims or produce live verification briefs yet. You can explore the sample investigation to see the intended evidence review experience.</p><Link className="button button-primary" href="/demo">Explore the sample investigation <Arrow /></Link><p><Link href="/methodology" className={styles.secondaryLink}>Read the methodology and FAQ</Link></p></section>
  </main>;
}
