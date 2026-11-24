import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Building2, GraduationCap, Newspaper, Users } from "lucide-react";
import { CtaBand, PageHero, Section, SectionHeading } from "@/components/site/Section";
import { SitePage } from "@/components/site/SitePage";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = { title: "For teams", description: "Make evidence easier to review in newsrooms, research desks and public offices." };

const people = [
  { icon: Newspaper, title: "Journalists", text: "Check a claim or image before it moves into a story." },
  { icon: Building2, title: "Editors", text: "Review the material and its limits before an editorial decision." },
  { icon: Users, title: "Researchers and fact-checkers", text: "Compare accounts and keep a clear record of what was examined." },
  { icon: GraduationCap, title: "Anyone checking information", text: "Understand what the available evidence can and cannot show." },
];
const moments = [
  ["Before a story moves forward", "Review the available sources and find gaps that need follow-up."],
  ["When an image raises questions", "Check attached origin details and visible observations in context."],
  ["When accounts conflict", "See where reports agree, differ or appear to rely on the same source."],
  ["When the answer is still unclear", "Keep \"not established yet\" separate from \"false\"."],
];

export default function NewsroomsPage() {
  return (
    <SitePage>
      <PageHero eyebrow="For teams" title="Make evidence easier to review." intro="Agent 0 helps people who check fast-moving information see the sources, the result and the questions that remain.">
        <Button asChild size="lg"><Link href="/investigate">Start a check <ArrowRight /></Link></Button>
      </PageHero>

      <Section>
        <SectionHeading eyebrow="Who uses it" title="Useful wherever verification happens." intro="The same careful questions matter in a newsroom, a research desk, a classroom or a public office." />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {people.map(({ icon: Icon, title, text }) => <div key={title} className="rounded-lg border border-line bg-surface p-5"><Icon className="mb-4 size-5 text-brand-ink" aria-hidden /><h3 className="font-semibold">{title}</h3><p className="mt-1.5 text-sm leading-6 text-muted">{text}</p></div>)}
        </div>
      </Section>

      <Section tone="subtle">
        <SectionHeading eyebrow="In practice" title="Support the decision. Do not make it for people." intro="Agent 0 is an investigation aid. It keeps its limits visible and does not replace newsroom standards, expert review or personal judgment." />
        <dl className="grid gap-4 sm:grid-cols-2">
          {moments.map(([title, text]) => <div key={title} className="rounded-lg border border-line bg-surface p-5"><dt className="font-semibold">{title}</dt><dd className="mt-1 text-sm leading-6 text-muted">{text}</dd></div>)}
        </dl>
        <p className="mt-8 max-w-2xl text-sm leading-6 text-muted">Cases can be exported as JSON from the workspace. Reviewer sign-in and team accounts are not available yet, and this demo is shared, so please do not use it for private or sensitive material.</p>
      </Section>

      <CtaBand title="Bring a question into view." text="Check a claim, a link or an image.">
        <Button asChild size="lg"><Link href="/investigate">Start a check <ArrowRight /></Link></Button>
      </CtaBand>
    </SitePage>
  );
}
