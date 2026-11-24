import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { Logo } from "@/components/brand/Logo";
import { WHATSAPP_CONTACT_URL } from "@/lib/contact";

const columns = [
  { title: "Product", links: [{ label: "How it works", href: "/how-it-works" }, { label: "Methodology", href: "/methodology" }, { label: "WhatsApp", href: "/whatsapp" }, { label: "Open workspace", href: "/dashboard" }] },
  { title: "Company", links: [{ label: "About", href: "/about" }, { label: "For teams", href: "/newsrooms" }, { label: "FAQ", href: "/faq" }, { label: "Privacy", href: "/privacy" }] },
];

export function SiteFooter() {
  return (
    <footer className="border-t border-line bg-surface">
      <div className="mx-auto grid w-full max-w-6xl gap-10 px-5 py-14 sm:px-8 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
        <div>
          <Link href="/" aria-label="Agent 0 home"><Logo /></Link>
          <p className="mt-4 max-w-xs text-sm leading-6 text-muted">Evidence for better-informed human decisions. Assume nothing. Follow the evidence.</p>
        </div>
        {columns.map((column) => (
          <nav key={column.title} aria-label={column.title}>
            <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-faint">{column.title}</p>
            <ul className="grid gap-2">
              {column.links.map((link) => <li key={link.href}><Link href={link.href} className="text-sm text-ink-soft hover:text-ink hover:underline underline-offset-4">{link.label}</Link></li>)}
            </ul>
          </nav>
        ))}
        <div>
          <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-faint">Contact</p>
          <a href={WHATSAPP_CONTACT_URL} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm text-ink-soft hover:text-ink hover:underline underline-offset-4">Message us on WhatsApp <ArrowUpRight className="size-3.5" /></a>
        </div>
      </div>
      <div className="border-t border-line">
        <p className="mx-auto w-full max-w-6xl px-5 py-5 text-xs text-faint sm:px-8">AI investigates. Humans decide. This is a shared demo: please use public information only.</p>
      </div>
    </footer>
  );
}
