"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { ArrowUpRight, BookOpen, CircleHelp, FolderOpen, LayoutDashboard, Plus, Smartphone } from "lucide-react";
import { Logo } from "@/components/brand/Logo";
import { WHATSAPP_CONTACT_URL } from "@/lib/contact";
import { cn } from "@/lib/utils";

const primary = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard, match: (path: string) => path === "/dashboard" },
  { href: "/investigate", label: "New check", icon: Plus, match: (path: string) => path === "/investigate" },
  { href: "/investigations", label: "Cases", icon: FolderOpen, match: (path: string) => path.startsWith("/investigations") },
];
const learn = [
  { href: "/methodology", label: "How results are decided", icon: BookOpen },
  { href: "/faq", label: "Help and FAQ", icon: CircleHelp },
  { href: "/whatsapp", label: "Check on WhatsApp", icon: Smartphone },
];

function NavLink({ href, label, icon: Icon, active }: { href: string; label: string; icon: typeof Plus; active?: boolean }) {
  return (
    <Link href={href} aria-current={active ? "page" : undefined}
      className={cn("flex h-10 items-center gap-3 rounded-md px-3 text-sm font-medium text-muted transition-colors hover:bg-subtle hover:text-ink", active && "bg-brand-soft font-semibold text-ink")}>
      <Icon className={cn("size-4", active && "text-brand-ink")} aria-hidden />{label}
    </Link>
  );
}

export function WorkspaceShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() ?? "";
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[256px_minmax(0,1fr)]">
      <aside aria-label="Workspace" className="sticky top-0 hidden h-screen flex-col gap-1 overflow-y-auto border-r border-line bg-surface px-4 py-5 lg:flex">
        <Link href="/" aria-label="Agent 0 home" className="mb-5 ml-1 inline-flex w-fit"><Logo /></Link>
        <nav aria-label="Workspace navigation" className="grid gap-1">
          {primary.map((item) => <NavLink key={item.href} {...item} active={item.match(pathname)} />)}
        </nav>
        <p className="mb-1 mt-6 px-3 text-[11px] font-semibold uppercase tracking-wider text-faint">Learn</p>
        <nav aria-label="Help" className="grid gap-1">{learn.map((item) => <NavLink key={item.href} {...item} />)}</nav>
        <div className="mt-auto rounded-lg border border-mixed-fg/20 bg-mixed-bg p-3.5">
          <p className="text-xs font-semibold text-mixed-fg">Shared demo</p>
          <p className="mt-1 text-xs leading-5 text-mixed-fg/90">Case history is visible to other visitors. Use public, non-sensitive claims only.</p>
        </div>
        <div className="mt-3 flex items-center justify-between px-1 text-xs text-faint">
          <a href={WHATSAPP_CONTACT_URL} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 hover:text-ink">Contact <ArrowUpRight className="size-3" /></a>
          <Link href="/privacy" className="hover:text-ink">Privacy</Link>
        </div>
      </aside>

      <div className="min-w-0 pb-20 lg:pb-0">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-line bg-bg/90 px-4 backdrop-blur-md lg:hidden">
          <Link href="/" aria-label="Agent 0 home"><Logo className="h-8 w-[98px]" /></Link>
          <Link href="/investigate" className="inline-flex h-9 items-center gap-1.5 rounded-md bg-brand px-3.5 text-sm font-semibold text-ink"><Plus className="size-4" aria-hidden />New check</Link>
        </header>
        <main id="content">{children}</main>
      </div>

      <nav aria-label="Workspace tabs" className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-4 border-t border-line bg-surface/95 pb-[env(safe-area-inset-bottom)] backdrop-blur-md lg:hidden">
        {[...primary, { href: "/faq", label: "Help", icon: CircleHelp, match: (path: string) => path === "/faq" }].map(({ href, label, icon: Icon, match }) => (
          <Link key={href} href={href} aria-current={match(pathname) ? "page" : undefined} className={cn("flex min-h-14 flex-col items-center justify-center gap-0.5 text-[11px] font-medium text-muted", match(pathname) && "text-brand-ink")}>
            <Icon className="size-5" aria-hidden />{label}
          </Link>
        ))}
      </nav>
    </div>
  );
}

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0 max-w-2xl">
        {eyebrow && <p className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-brand-ink">{eyebrow}</p>}
        <h1 className="text-3xl font-semibold leading-tight sm:text-4xl">{title}</h1>
        {description && <p className="mt-3 leading-7 text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function WorkspacePage({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("mx-auto w-full max-w-5xl px-4 py-8 sm:px-8 sm:py-12", className)}>{children}</div>;
}
