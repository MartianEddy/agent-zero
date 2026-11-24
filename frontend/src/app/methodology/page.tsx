import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Container, CtaBand, PageHero } from "@/components/site/Section";
import { Note, Prose } from "@/components/site/Prose";
import { SitePage } from "@/components/site/SitePage";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { VERDICT_ORDER, verdictView } from "@/lib/verdict";

export const metadata: Metadata = { title: "How results are decided", description: "What counts as evidence, how sources are compared, and what each outcome means." };

const toc = [["steps", "The steps"], ["evidence", "What counts as evidence"], ["independence", "Independent sources"], ["outcomes", "The five outcomes"], ["strength", "Evidence strength"], ["media", "Images and video"], ["limits", "Limits"]];
const rules: Record<string, string> = {
  SUPPORTED: "At least two independent source groups back the claim, or one directly relevant official record settles a basic fact. Nothing credible contradicts it.",
  CONTRADICTED: "The same standard, in the other direction.",
  PARTLY_TRUE: "The claim has distinct parts, and independent evidence backs some and challenges others. Two sources merely disagreeing is not enough for this label.",
  INSUFFICIENT_EVIDENCE: "We could not find enough solid, independent evidence either way. This is not the same as false.",
  NOT_VERIFIABLE: "The statement is an opinion or a prediction, not a factual claim.",
};

export default function MethodologyPage() {
  return (
    <SitePage>
      <PageHero eyebrow="Methodology" title="How results are decided." intro="An AI model can suggest, but fixed rules you can read decide. This page explains those rules in plain language." />
      <Container className="grid gap-10 py-14 lg:grid-cols-[220px_1fr] lg:gap-16 lg:py-20">
        <nav aria-label="On this page" className="lg:sticky lg:top-24 lg:self-start">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-faint">On this page</p>
          <ul className="flex flex-wrap gap-2 lg:grid lg:gap-1">
            {toc.map(([id, label]) => <li key={id}><a href={`#${id}`} className="inline-flex rounded-md border border-line px-3 py-1.5 text-sm text-muted hover:bg-subtle hover:text-ink lg:border-0 lg:px-2">{label}</a></li>)}
          </ul>
        </nav>
        <Prose className="max-w-3xl">
          <h2 id="steps">The steps</h2>
          <ol>
            <li><strong>Understand the request.</strong> Agent 0 picks out the specific claims that can be checked, and asks you a question if a name, place or date is missing.</li>
            <li><strong>You review the claims.</strong> Nothing is researched until you confirm what will be checked.</li>
            <li><strong>Search.</strong> It looks first for official records and subject authorities, then widens to independent reporting and earlier fact-checks to fill specific gaps.</li>
            <li><strong>Read the sources.</strong> Search results are only leads. Agent 0 opens the pages and keeps the exact passages that speak to your claim.</li>
            <li><strong>Compare.</strong> Each passage is judged against the claim: does it support, challenge, or only give background?</li>
            <li><strong>Apply the rules.</strong> The rules below set the final outcome. The AI suggestion cannot override them.</li>
          </ol>

          <h2 id="evidence">What counts as evidence</h2>
          <p>Only text that was actually retrieved from a source and checked against the page counts. A search result title, a snippet, or a source reputation does not.</p>
          <ul>
            <li>Pages that could not be opened are listed as gaps, never as evidence.</li>
            <li>Social media posts and unknown sites can be shown for context but cannot settle a result.</li>
            <li>Fact-checks by others are leads. Agent 0 follows them back to the records they cite.</li>
            <li>The page you submitted is context, not proof of its own claim.</li>
          </ul>

          <h2 id="independence">Independent sources</h2>
          <p>Ten articles repeating the same press release are one source, not ten. Agent 0 groups together sources from the same publisher and sources that copy or cite each other, and counts each group once.</p>
          <Note tone="warn">Grouping is not perfect. Sources owned by the same company under different web addresses, or wire stories republished without a link, can still be counted separately. Check the cited sources yourself on anything important.</Note>

          <h2 id="outcomes">The five outcomes</h2>
          <ul className="!list-none !pl-0 grid gap-3">
            {VERDICT_ORDER.map((status) => { const view = verdictView(status); const Icon = view.icon; return (
              <li key={status} className="!mb-0 grid gap-2 rounded-lg border border-line bg-surface p-4 !pl-4 sm:grid-cols-[250px_1fr] sm:gap-5">
                <div><Badge tone={view.tone} className="py-1.5 text-[13px]"><Icon /> {view.label}</Badge></div>
                <p className="!mb-0 text-sm leading-6">{rules[status]}</p>
              </li>); })}
          </ul>

          <h2 id="strength">Evidence strength</h2>
          <p>Each result also shows <strong>Low</strong>, <strong>Medium</strong> or <strong>High</strong> evidence strength. It describes how much solid, independent evidence was found. It is <em>not</em> the chance that the claim is true.</p>
          <ul>
            <li><strong>Low:</strong> little or no usable evidence, one independent source, or only background material.</li>
            <li><strong>Medium:</strong> at least two independent sources, but gaps remain in authority, directness or agreement.</li>
            <li><strong>High:</strong> a clear result backed by at least two independent official sources that fit the topic, with no conflict.</li>
          </ul>

          <h2 id="media">Images and video</h2>
          <p>For media, Agent 0 reports what it can inspect: file details, any attached content credentials, and what is visibly shown. File details can be edited. Missing credentials do not mean an image is fake, and how an image looks cannot prove it was made or altered by AI. Video audio is not transcribed yet.</p>

          <h2 id="limits">Limits you should know about</h2>
          <ul>
            <li>The list of recognised official sources is still small and centred on Kenya. Credible sources outside it can still be found and shown, but count for less until reviewed.</li>
            <li>Agent 0 can be wrong. It works best as a fast, organised first pass with a person making the call.</li>
            <li>Results can lag breaking events. Recent claims often return &ldquo;not enough evidence yet&rdquo;.</li>
            <li>A formal accuracy benchmark is still being built. Until it is published, treat results as unmeasured.</li>
          </ul>
          <p><Link href="/faq">Read the FAQ</Link> or <Link href="/investigate">run a check</Link> and open any source behind a result.</p>
        </Prose>
      </Container>
      <CtaBand title="See the rules at work." text="Every result links to the passages it relied on."><Button asChild size="lg"><Link href="/investigate">Start a check <ArrowRight /></Link></Button></CtaBand>
    </SitePage>
  );
}
