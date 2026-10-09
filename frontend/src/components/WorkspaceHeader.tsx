"use client";

import Link from "next/link";
import { AgentMark } from "@/components/AgentMark";
import styles from "./WorkspaceHeader.module.css";

export function WorkspaceHeader({ activeHref }: { activeHref: "/investigate" | "/investigations" }) {
  return <header className={styles.header}>
    <div className={styles.inner}>
      <Link href="/" className={styles.brand} aria-label="Agent 0 home"><AgentMark /></Link>
      <nav className={styles.nav} aria-label="Workspace navigation">
        <Link href="/investigate" aria-current={activeHref === "/investigate" ? "page" : undefined}>Investigate</Link>
        <Link href="/investigations" aria-current={activeHref === "/investigations" ? "page" : undefined}>Case history</Link>
        <Link href="/how-it-works">How it works</Link>
      </nav>
      <Link href="/investigate" className={styles.newCase}>＋ New check</Link>
      <details className={styles.mobileMenu}>
        <summary aria-label="Open workspace navigation"><span /><span /></summary>
        <nav aria-label="Mobile workspace navigation">
          <Link href="/investigate" aria-current={activeHref === "/investigate" ? "page" : undefined}>Investigate</Link>
          <Link href="/investigations" aria-current={activeHref === "/investigations" ? "page" : undefined}>Case history</Link>
          <Link href="/how-it-works">How it works</Link>
        </nav>
      </details>
    </div>
  </header>;
}
