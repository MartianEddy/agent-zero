import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, FileSearch, ListChecks, Scale, Search, TextCursorInput, UserCheck } from "lucide-react";
import { CtaBand, PageHero, Section, SectionHeading } from "@/components/site/Section";
import { SitePage } from "@/components/site/SitePage";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = { title: "How it works", description: "From a question to evidence you can inspect, in five clear steps." };

const steps = [
  { icon: TextCursorInput, title: "Bring in the material", text: "Start with a claim, a public link, or an image or short video together with the question you have. You can also send it on WhatsApp." },
  { icon: ListChecks, title: "Review the claim", text: "Agent 0 proposes one or more specific claims it can check. Edit or split them. Nothing is researched until you confirm." },
  { icon: Search, title: "Follow the sources", text: "It searches official records first, then independent reporting and earlier fact-checks. Pages it could not open are listed as gaps." },
  { icon: Scale, title: "Compare what was found", text: "Each passage is judged against your claim. Sources that copy each other count once, and fixed rules set the result." },
  { icon: UserCheck, title: "Make the human decision", text: "Use the result, the sources and the open questions to guide your next step. The decision stays with you." },
];

const reading = [
  { title: "What supports the claim", text: "Evidence that agrees with what was submitted." },
  { title: "What challenges the claim", text: "Reliable material that points in another direction." },
  { title: "What adds context", text: "Information that helps interpret a claim without settling it." },
  { title: "What to check next", text: "Open questions and suggested actions to continue your work." },
];

export default function HowItWorksPage() {
  return (
    <SitePage>
      <PageHero eyebrow="How it works" title="From a question to evidence you can inspect." intro="Agent 0 makes its work easy to follow, so you can see what was checked and where the gaps remain.">
        <Button asChild size="lg"><Link href="/investigate">Start a check <ArrowRight /></Link></Button>
        <Button asChild size="lg" variant="outline"><Link href="/methodology">Read the method</Link></Button>
      </PageHero>

      <Section>
        <SectionHeading eyebrow="Five steps" title="A clear path through every check." />
        <ol className="relative grid gap-4">
          {steps.map(({ icon: Icon, title, text }, index) => (
            <li key={title} className="grid gap-4 rounded-lg border border-line bg-surface p-5 sm:grid-cols-[auto_1fr] sm:gap-6 sm:p-6">
              <div className="flex items-center gap-4 sm:flex-col sm:items-start"><span className="grid size-11 place-items-center rounded-md bg-brand-soft text-brand-ink"><Icon className="size-5" aria-hidden /></span><span className="font-mono text-xs text-faint">Step {index + 1}</span></div>
              <div><h3 className="text-lg font-semibold">{title}</h3><p className="mt-1.5 max-w-2xl leading-7 text-muted">{text}</p></div>
            </li>
          ))}
        </ol>
      </Section>

      <Section tone="subtle">
        <SectionHeading eyebrow="Reading a result" title="A result is a starting point for your judgment." intro="A missing source does not make a claim false. A source count is not a verdict. When Agent 0 cannot establish something, it says so." />
        <div className="grid gap-4 sm:grid-cols-2">
          {reading.map((item) => <div key={item.title} className="rounded-lg border border-line bg-surface p-5"><FileSearch className="mb-3 size-5 text-brand-ink" aria-hidden /><h3 className="font-semibold">{item.title}</h3><p className="mt-1 text-sm leading-6 text-muted">{item.text}</p></div>)}
        </div>
      </Section>

      <CtaBand title="See what Agent 0 can examine." text="Start with a claim, a link or an image.">
        <Button asChild size="lg"><Link href="/investigate">Start a check <ArrowRight /></Link></Button>
      </CtaBand>
    </SitePage>
  );
}
