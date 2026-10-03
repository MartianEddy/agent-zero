"use client";
import Link from "next/link";
import { useState } from "react";
import { AgentMark } from "@/components/AgentMark";
import { Arrow } from "@/components/Arrow";
import styles from "./SiteHeader.module.css";

const links = [{ label: "Home", href: "/" }, { label: "Product", href: "/product" }, { label: "Demo", href: "/demo" }, { label: "How it works", href: "/how-it-works" }, { label: "Methodology & FAQ", href: "/methodology" }, { label: "For Newsrooms", href: "/newsrooms" }, { label: "About", href: "/about" }];
export function SiteHeader({ activeHref = "/" }: { activeHref?: string }) {
  const [open, setOpen] = useState(false);
  return <header className={styles.header}><div className={`container ${styles.inner}`}>
    <Link href="/" className={styles.brand} aria-label="Agent 0 home"><AgentMark /></Link>
    <nav className={styles.desktopNav} aria-label="Main navigation">{links.map((link) => <Link key={link.href} href={link.href} aria-current={link.href === activeHref ? "page" : undefined} className={link.href === activeHref ? styles.active : undefined}>{link.label}</Link>)}</nav>
    <Link href="/demo" className={`button button-primary ${styles.cta}`}>Explore the demo <Arrow /></Link>
    <button className={styles.menuButton} aria-expanded={open} aria-controls="mobile-navigation" aria-label={open ? "Close navigation" : "Open navigation"} onClick={() => setOpen((value) => !value)}><span /><span /></button>
  </div>{open && <nav id="mobile-navigation" className={styles.mobileNav} aria-label="Mobile navigation">
    {links.map((link) => <Link key={link.href} href={link.href} onClick={() => setOpen(false)}>{link.label}</Link>)}
    <Link className={styles.mobileCta} href="/demo" onClick={() => setOpen(false)}>Explore the demo <Arrow /></Link>
  </nav>}</header>;
}
