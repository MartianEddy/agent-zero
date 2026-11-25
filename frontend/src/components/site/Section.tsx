import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Reveal } from "@/components/motion/Reveal";

export function Container({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn("mx-auto w-full max-w-6xl px-5 sm:px-8", className)}>{children}</div>;
}

type Tone = "plain" | "surface" | "subtle" | "dark" | "lime" | "mint" | "violet" | "sky";
const TONES: Record<Tone, string> = {
  plain: "",
  surface: "bg-surface",
  subtle: "bg-subtle",
  dark: "bg-night text-white",
  lime: "bg-lime-soft",
  mint: "bg-teal-soft",
  violet: "bg-violet-soft",
  sky: "bg-sky-soft",
};

export function Section({ className, children, tone = "plain", id }: { className?: string; children: ReactNode; tone?: Tone; id?: string }) {
  return (
    <section id={id} className={cn("relative py-16 sm:py-24", TONES[tone], className)}>
      <Container>{children}</Container>
    </section>
  );
}

export function Eyebrow({ children, className, dark = false }: { children: ReactNode; className?: string; dark?: boolean }) {
  return (
    <p className={cn("mb-4 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-[0.1em]", dark ? "border-brand/30 bg-brand/10 text-brand" : "border-brand-ink/20 bg-brand-soft text-brand-ink", className)}>
      <span className={cn("size-1.5 rounded-full", dark ? "bg-brand" : "bg-brand-ink")} />{children}
    </p>
  );
}

export function SectionHeading({ eyebrow, title, intro, className, dark = false, center = false }: { eyebrow?: string; title: string; intro?: string; className?: string; dark?: boolean; center?: boolean }) {
  return (
    <Reveal className={cn("mb-12 max-w-2xl", center && "mx-auto text-center", className)}>
      {eyebrow && <Eyebrow dark={dark}>{eyebrow}</Eyebrow>}
      <h2 className={cn("text-3xl font-semibold leading-[1.08] tracking-tight sm:text-5xl", dark ? "text-white" : "text-ink")}>{title}</h2>
      {intro && <p className={cn("mt-4 text-base leading-7 sm:text-lg sm:leading-8", dark ? "text-white/65" : "text-muted")}>{intro}</p>}
    </Reveal>
  );
}

export function PageHero({ eyebrow, title, intro, children }: { eyebrow: string; title: string; intro: string; children?: ReactNode }) {
  return (
    <div className="relative isolate overflow-hidden bg-night text-white">
      <div className="bg-grid-dark pointer-events-none absolute inset-0 -z-10" />
      <div className="pointer-events-none absolute -left-24 -top-32 -z-10 size-[420px] rounded-full bg-brand/20 blur-[110px]" />
      <div className="pointer-events-none absolute -right-24 top-10 -z-10 size-[380px] rounded-full bg-teal/20 blur-[110px]" />
      <Container className="py-16 sm:py-24">
        <Reveal>
          <Eyebrow dark>{eyebrow}</Eyebrow>
          <h1 className="max-w-3xl text-4xl font-semibold leading-[1.04] tracking-tight sm:text-6xl">{title}</h1>
          <p className="mt-6 max-w-2xl text-base leading-7 text-white/65 sm:text-lg sm:leading-8">{intro}</p>
          {children && <div className="mt-9 flex flex-wrap gap-3">{children}</div>}
        </Reveal>
      </Container>
    </div>
  );
}

export function CtaBand({ title, text, children }: { title: string; text: string; children: ReactNode }) {
  return (
    <section className="relative isolate overflow-hidden bg-night py-20 text-white sm:py-24">
      <div className="bg-grid-dark pointer-events-none absolute inset-0 -z-10" />
      <div className="pointer-events-none absolute left-1/2 top-0 -z-10 h-72 w-[640px] -translate-x-1/2 rounded-full bg-brand/25 blur-[120px]" />
      <Container>
        <Reveal className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl font-semibold tracking-tight sm:text-5xl">{title}</h2>
          <p className="mt-4 text-lg text-white/65">{text}</p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">{children}</div>
        </Reveal>
      </Container>
    </section>
  );
}
