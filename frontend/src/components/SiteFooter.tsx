import Link from "next/link";
import { AgentMark } from "@/components/AgentMark";
import { WHATSAPP_CONTACT_URL } from "@/lib/contact";
import styles from "./SiteFooter.module.css";
const links = [{ label: "Product", href: "/product" }, { label: "How it works", href: "/how-it-works" }, { label: "For Newsrooms", href: "/newsrooms" }, { label: "About", href: "/about" }];
export function SiteFooter() {
  return <footer className={styles.footer}>
    <div className={`container ${styles.main}`}>
      <div className={styles.identity}>
        <Link href="/" className={styles.brand} aria-label="Agent 0 home"><AgentMark /></Link>
        <p>Evidence for better-informed<br />human decisions.</p>
      </div>
      <nav className={styles.navigation} aria-label="Footer navigation">
        <p className={styles.navLabel}>Explore Agent 0</p>
        <div className={styles.links}>{links.map((link) => <Link key={link.href} href={link.href}>{link.label}<span aria-hidden="true">↗</span></Link>)}<a href={WHATSAPP_CONTACT_URL} target="_blank" rel="noopener noreferrer">WhatsApp us<span aria-hidden="true">↗</span></a></div>
      </nav>
    </div>
    <div className={styles.base}><p>Assume nothing. <span>Follow the evidence.</span></p></div>
  </footer>;
}
