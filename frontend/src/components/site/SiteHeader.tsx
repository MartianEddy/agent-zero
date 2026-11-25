"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowRight, Menu, X } from "lucide-react";
import { Logo } from "@/components/brand/Logo";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { SITE_LINKS } from "./nav";

export function SiteHeader() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header className={cn("sticky top-0 z-40 border-b transition-colors duration-300", scrolled || open ? "border-night-line bg-night/90 backdrop-blur-md" : "border-transparent bg-night")}>
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center gap-6 px-5 sm:px-8">
        <Link href="/" aria-label="Agent 0 home" className="shrink-0"><Logo /></Link>
        <nav aria-label="Main" className="ml-auto hidden items-center gap-1 lg:flex">
          {SITE_LINKS.map((link) => (
            <Link key={link.href} href={link.href} aria-current={pathname === link.href ? "page" : undefined}
              className={cn("rounded-md px-3 py-2 text-sm font-medium text-white/65 transition-colors hover:text-white", pathname === link.href && "bg-white/10 text-white")}>
              {link.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2 lg:ml-2">
          <Button asChild size="sm" className="hidden sm:inline-flex"><Link href="/investigate">Start a check <ArrowRight /></Link></Button>
          <Button variant="ghost" size="icon" className="text-white hover:bg-white/10 lg:hidden" aria-expanded={open} aria-controls="mobile-nav" aria-label={open ? "Close menu" : "Open menu"} onClick={() => setOpen((value) => !value)}>
            {open ? <X /> : <Menu />}
          </Button>
        </div>
      </div>
      {open && (
        <nav id="mobile-nav" aria-label="Mobile" className="animate-fade-in border-t border-night-line bg-night px-5 pb-5 pt-3 lg:hidden">
          <ul className="grid gap-1">
            {SITE_LINKS.map((link) => (
              <li key={link.href}><Link href={link.href} onClick={() => setOpen(false)} className="flex min-h-12 items-center rounded-md px-3 text-[15px] font-medium text-white/85 hover:bg-white/10">{link.label}</Link></li>
            ))}
            <li><Link href="/dashboard" onClick={() => setOpen(false)} className="flex min-h-12 items-center rounded-md px-3 text-[15px] font-medium text-white/85 hover:bg-white/10">Open workspace</Link></li>
          </ul>
          <Button asChild className="mt-3 w-full"><Link href="/investigate" onClick={() => setOpen(false)}>Start a check <ArrowRight /></Link></Button>
        </nav>
      )}
    </header>
  );
}
