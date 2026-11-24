import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Container, CtaBand, PageHero, Section } from "@/components/site/Section";
import { SitePage } from "@/components/site/SitePage";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = { title: "About", description: "Why Agent 0 exists and the principles behind it." };

const principles = [
  ["Start with evidence", "Treat a question as something to examine, not a conclusion to confirm."],
  ["Show the way through", "Help people follow important findings back to what was reviewed."],
  ["Respect uncertainty", "Keep missing information and conflicting accounts visible."],
  ["Leave decisions with people", "Use AI to support investigation while people remain accountable."],
];

export default function AboutPage() {
  return (
    <SitePage>
      <PageHero eyebrow="About" title="The internet does not need another AI telling people what to believe." intro="It needs better tools for examining evidence. Assume nothing. Follow the evidence." />
      <Section>
        <Container className="grid gap-12 px-0 sm:px-0 lg:grid-cols-[1fr_1.2fr]">
          <div>
            <h2 className="text-3xl font-semibold leading-[1.1]">Why Agent 0 exists</h2>
            <p className="mt-4 leading-8 text-muted">Information moves quickly between people and platforms. Checking it takes deliberate work: finding sources, comparing accounts, understanding media, and being clear about what remains unknown. Agent 0 is being built to make that work easier to follow.</p>
          </div>
          <ol className="grid gap-3">
            {principles.map(([title, text], index) => (
              <li key={title} className="flex gap-4 rounded-lg border border-line bg-surface p-5"><span className="font-mono text-xs leading-6 text-faint">0{index + 1}</span><div><h3 className="font-semibold">{title}</h3><p className="mt-1 text-sm leading-6 text-muted">{text}</p></div></li>
            ))}
          </ol>
        </Container>
      </Section>
      <Section tone="subtle">
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-brand-ink">The principle</p>
        <p className="mt-3 max-w-3xl text-3xl font-semibold leading-tight sm:text-4xl">AI investigates. Humans decide.</p>
        <p className="mt-5 max-w-2xl leading-8 text-muted">A result should come with the evidence behind it, the limitations that matter and a clear view of what could not be established. Read exactly how results are reached on the <Link href="/methodology" className="font-medium text-brand-ink underline underline-offset-4">methodology page</Link>.</p>
      </Section>
      <CtaBand title="Follow a question where the evidence leads." text="Start with a claim, a link or an image."><Button asChild size="lg"><Link href="/investigate">Start a check <ArrowRight /></Link></Button></CtaBand>
    </SitePage>
  );
}
