import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Container({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("mx-auto w-full max-w-6xl px-5 sm:px-8", className)}>{children}</div>;
}

export function Section({ className, children, tone = "plain", id }: { className?: string; children: ReactNode; tone?: "plain" | "surface" | "subtle" | "dark"; id?: string }) {
  return (
    <section id={id} className={cn("py-16 sm:py-24", tone === "surface" && "bg-surface", tone === "subtle" && "bg-subtle", tone === "dark" && "bg-ink text-white", className)}>
      <Container>{children}</Container>
    </section>
  );
}

export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cn("mb-3 text-xs font-semibold uppercase tracking-[0.12em] text-brand-ink", className)}>{children}</p>;
}

export function SectionHeading({ eyebrow, title, intro, className }: { eyebrow?: string; title: string; intro?: string; className?: string }) {
  return (
    <div className={cn("mb-10 max-w-2xl", className)}>
      {eyebrow && <Eyebrow>{eyebrow}</Eyebrow>}
      <h2 className="text-3xl font-semibold leading-[1.1] sm:text-4xl">{title}</h2>
      {intro && <p className="mt-4 text-base leading-7 text-muted sm:text-lg sm:leading-8">{intro}</p>}
    </div>
  );
}

export function PageHero({ eyebrow, title, intro, children }: { eyebrow: string; title: string; intro: string; children?: ReactNode }) {
  return (
    <div className="border-b border-line bg-surface">
      <Container className="py-14 sm:py-20">
        <Eyebrow>{eyebrow}</Eyebrow>
        <h1 className="max-w-3xl text-4xl font-semibold leading-[1.05] sm:text-5xl">{title}</h1>
        <p className="mt-5 max-w-2xl text-base leading-7 text-muted sm:text-lg sm:leading-8">{intro}</p>
        {children && <div className="mt-8 flex flex-wrap gap-3">{children}</div>}
      </Container>
    </div>
  );
}

export function CtaBand({ title, text, children }: { title: string; text: string; children: ReactNode }) {
  return (
    <Section tone="dark" className="py-14 sm:py-16">
      <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="max-w-xl"><h2 className="text-2xl font-semibold sm:text-3xl">{title}</h2><p className="mt-2 text-white/70">{text}</p></div>
        <div className="flex flex-wrap gap-3">{children}</div>
      </div>
    </Section>
  );
}
