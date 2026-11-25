import Image from "next/image";
import Link from "next/link";
import { ArrowRight, Building2, CircleCheck, Eye, FileSearch, GraduationCap, Layers, Link2, Newspaper, Scale, Smartphone, Sparkles, Users } from "lucide-react";
import { Reveal } from "@/components/motion/Reveal";
import { Tilt } from "@/components/motion/Tilt";
import { ChatMock } from "@/components/site/ChatMock";
import { FlowDemo } from "@/components/site/FlowDemo";
import { QuickCheck } from "@/components/site/QuickCheck";
import { Container, CtaBand, Eyebrow, Section, SectionHeading } from "@/components/site/Section";
import { SitePage } from "@/components/site/SitePage";
import { EvidenceSceneLoader } from "@/components/three/EvidenceSceneLoader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { WHATSAPP_CONTACT_URL } from "@/lib/contact";
import { VERDICT_ORDER, verdictView } from "@/lib/verdict";

const TILE: Record<string, string> = {
  SUPPORTED: "from-ok-bg to-white", CONTRADICTED: "from-bad-bg to-white", PARTLY_TRUE: "from-mixed-bg to-white",
  INSUFFICIENT_EVIDENCE: "from-unknown-bg to-white", NOT_VERIFIABLE: "from-opinion-bg to-white",
};

const audiences = [
  { icon: Newspaper, title: "Journalists", text: "Check a claim or image before it moves into a story.", tint: "bg-lime-soft" },
  { icon: Building2, title: "Editors and desks", text: "Review the evidence and its limits before an editorial call.", tint: "bg-sky-soft" },
  { icon: Users, title: "Fact-checkers and researchers", text: "Compare accounts and keep a clear record of what was examined.", tint: "bg-violet-soft" },
  { icon: GraduationCap, title: "Everyone else", text: "Decide whether a message is worth sharing, in a minute.", tint: "bg-amber-soft" },
];

export default function HomePage() {
  return (
    <SitePage>
      {/* Hero */}
      <div className="relative isolate overflow-hidden bg-night text-white">
        <div className="bg-grid-dark pointer-events-none absolute inset-0 -z-10" />
        <div className="pointer-events-none absolute -left-32 top-0 -z-10 size-[520px] rounded-full bg-brand/20 blur-[130px]" />
        <div className="pointer-events-none absolute -right-20 top-24 -z-10 size-[460px] rounded-full bg-teal/25 blur-[130px]" />
        <Container className="grid items-center gap-8 pb-28 pt-14 sm:pt-20 lg:grid-cols-[1.05fr_1fr]">
          <Reveal>
            <Eyebrow dark><Sparkles className="size-3.5" /> AI investigates. Humans decide.</Eyebrow>
            <h1 className="text-5xl font-semibold leading-[1.0] tracking-tight sm:text-7xl">
              Check it before <span className="text-gradient">you share it.</span>
            </h1>
            <p className="mt-6 max-w-xl text-lg leading-8 text-white/65">Paste a claim, a link or an image. Agent 0 finds the sources, compares what they say, and tells you in plain words what holds up and what does not.</p>
            <div className="mt-9 flex flex-wrap gap-3">
              <Button asChild size="lg"><Link href="/investigate">Start a check <ArrowRight /></Link></Button>
              <Button asChild size="lg" variant="glass"><a href={WHATSAPP_CONTACT_URL} target="_blank" rel="noopener noreferrer"><Smartphone /> Check on WhatsApp</a></Button>
            </div>
            <ul className="mt-9 flex flex-wrap gap-x-6 gap-y-2 text-sm text-white/55">
              {["Free to try", "English and Kiswahili", "Every result links to its sources"].map((item) => <li key={item} className="flex items-center gap-2"><CircleCheck className="size-4 text-brand" aria-hidden />{item}</li>)}
            </ul>
          </Reveal>

          <div className="relative mx-auto h-[380px] w-full max-w-[520px] sm:h-[460px]">
            <EvidenceSceneLoader className="absolute inset-0" />
            <div className="glass absolute left-0 top-[12%] hidden animate-float rounded-xl px-3.5 py-2.5 text-xs text-white sm:block"><span className="mr-2 inline-block size-2 rounded-full bg-brand" />Official record supports</div>
            <div className="glass absolute right-0 top-[30%] hidden animate-float-slow rounded-xl px-3.5 py-2.5 text-xs text-white sm:block"><span className="mr-2 inline-block size-2 rounded-full bg-coral" />One report challenges</div>
            <div className="glass absolute bottom-[10%] left-[8%] hidden animate-float rounded-xl px-3.5 py-2.5 text-xs text-white sm:block"><span className="mr-2 inline-block size-2 rounded-full bg-sky" />Context added</div>
          </div>
        </Container>
      </div>

      {/* Floating composer overlapping the hero */}
      <Container className="relative z-10 -mt-20">
        <Reveal><QuickCheck className="mx-auto max-w-3xl border-night-line/40 shadow-pop" /></Reveal>
      </Container>

      {/* Principles */}
      <Section className="pb-8 sm:pb-12">
        <ul className="grid gap-4 md:grid-cols-3">
          {[
            { icon: Eye, title: "You approve the claim first", text: "Agent 0 shows what it understood. Nothing is researched until you confirm.", tint: "bg-lime-soft text-brand-ink" },
            { icon: Link2, title: "Every result links to sources", text: "Open the exact passages behind a result, and see which pages could not be read.", tint: "bg-sky-soft text-info-fg" },
            { icon: Layers, title: "Gaps stay visible", text: "Not enough evidence is reported as exactly that. It is never presented as false.", tint: "bg-violet-soft text-opinion-fg" },
          ].map(({ icon: Icon, title, text, tint }, index) => (
            <Reveal key={title} delay={index * 0.08}>
              <li className="h-full rounded-2xl border border-line bg-surface p-6 shadow-card">
                <span className={`mb-4 grid size-11 place-items-center rounded-xl ${tint}`}><Icon className="size-5" aria-hidden /></span>
                <h2 className="text-lg font-semibold">{title}</h2><p className="mt-1.5 text-sm leading-6 text-muted">{text}</p>
              </li>
            </Reveal>
          ))}
        </ul>
      </Section>

      {/* Flow */}
      <Section id="how-it-works">
        <SectionHeading eyebrow="See the flow" title="From a question to an answer you can check." intro="Four steps. Pick one to see what you will see on screen." />
        <FlowDemo />
        <p className="mt-8 text-sm"><Link href="/methodology" className="font-semibold text-brand-ink underline underline-offset-4">Read the exact rules behind a result</Link></p>
      </Section>

      {/* Bento */}
      <Section tone="subtle">
        <SectionHeading eyebrow="What you get" title="Clear answers, built to be trusted." />
        <div className="grid gap-4 md:grid-cols-6">
          <Reveal className="md:col-span-4">
            <Tilt className="h-full"><div className="relative h-full overflow-hidden rounded-2xl bg-night p-7 text-white">
              <div className="pointer-events-none absolute -right-10 -top-10 size-56 rounded-full bg-brand/25 blur-[70px]" />
              <Scale className="mb-4 size-6 text-brand" aria-hidden />
              <h3 className="text-2xl font-semibold">A plain verdict, then the reasons.</h3>
              <p className="mt-2 max-w-md text-white/65">Five outcomes in everyday words, with how strong the evidence is. Not enough evidence is never called false.</p>
              <div className="mt-6 flex flex-wrap gap-2">{VERDICT_ORDER.map((status) => { const view = verdictView(status); const Icon = view.icon; return <Badge key={status} tone={view.tone}><Icon aria-hidden />{view.short}</Badge>; })}</div>
            </div></Tilt>
          </Reveal>
          <Reveal className="md:col-span-2" delay={0.08}>
            <Tilt className="h-full"><div className="h-full rounded-2xl bg-brand p-7 text-ink">
              <FileSearch className="mb-4 size-6" aria-hidden />
              <h3 className="text-xl font-semibold">Passages, not just links.</h3>
              <p className="mt-2 text-sm leading-6 text-ink/75">See the exact sentences from each page that the result rests on.</p>
            </div></Tilt>
          </Reveal>
          <Reveal className="md:col-span-2" delay={0.04}>
            <Tilt className="h-full"><div className="h-full rounded-2xl bg-sky-soft p-7">
              <Layers className="mb-4 size-6 text-info-fg" aria-hidden />
              <h3 className="text-xl font-semibold">Copies count once.</h3>
              <p className="mt-2 text-sm leading-6 text-muted">Ten sites repeating one press release are one source, not ten.</p>
              <div className="mt-4 flex items-center gap-1.5" aria-hidden>{Array.from({ length: 10 }).map((_, i) => <span key={i} className="size-2.5 rounded-full bg-info-fg/40" />)}<ArrowRight className="mx-1 size-4 text-info-fg" /><span className="size-3.5 rounded-full bg-info-fg" /></div>
            </div></Tilt>
          </Reveal>
          <Reveal className="md:col-span-2" delay={0.08}>
            <Tilt className="h-full"><div className="h-full rounded-2xl bg-violet-soft p-7">
              <Eye className="mb-4 size-6 text-opinion-fg" aria-hidden />
              <h3 className="text-xl font-semibold">What is still unknown.</h3>
              <p className="mt-2 text-sm leading-6 text-muted">Open questions and a suggested next step come with every result.</p>
            </div></Tilt>
          </Reveal>
          <Reveal className="md:col-span-2" delay={0.12}>
            <Tilt className="h-full"><div className="h-full rounded-2xl bg-amber-soft p-7">
              <Smartphone className="mb-4 size-6 text-mixed-fg" aria-hidden />
              <h3 className="text-xl font-semibold">Right in WhatsApp.</h3>
              <p className="mt-2 text-sm leading-6 text-muted">Forward a message and get the answer in the same chat.</p>
            </div></Tilt>
          </Reveal>
        </div>
      </Section>

      {/* Verdicts */}
      <Section>
        <SectionHeading eyebrow="Five outcomes" title="Every result means one thing." intro="No scores to decode. Each outcome says what the evidence shows, and what it does not." />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {VERDICT_ORDER.map((status, index) => { const view = verdictView(status); const Icon = view.icon; return (
            <Reveal key={status} delay={index * 0.06}>
              <Tilt className="h-full"><div className={`h-full rounded-2xl border border-line bg-gradient-to-b ${TILE[status]} p-5 shadow-card`}>
                <Badge tone={view.tone}><Icon aria-hidden />{view.short}</Badge>
                <h3 className="mt-4 text-[15px] font-semibold leading-snug">{view.label}</h3>
                <p className="mt-2 text-sm leading-6 text-muted">{view.meaning}</p>
              </div></Tilt>
            </Reveal>
          ); })}
        </div>
      </Section>

      {/* Trust */}
      <section className="relative isolate overflow-hidden bg-night py-20 text-white sm:py-28">
        <div className="bg-grid-dark pointer-events-none absolute inset-0 -z-10" />
        <div className="pointer-events-none absolute right-0 top-0 -z-10 size-[420px] rounded-full bg-teal/20 blur-[120px]" />
        <Container>
          <SectionHeading dark eyebrow="Why you can trust it" title="AI suggests. Fixed rules decide. You make the call." intro="A language model reads the sources. It cannot set the result. The rules below do." />
          <div className="grid gap-4 md:grid-cols-3">
            {[
              { n: "01", title: "AI reads", text: "It finds the passages in each source that speak to your claim, and says whether each one supports or challenges it." },
              { n: "02", title: "Rules decide", text: "Two independent sources are needed, or one official record for a basic fact or a statistic. A conflict stays unresolved." },
              { n: "03", title: "You review", text: "Open every source. Edit the claim and try again. Agent 0 shows its limits and does not hide gaps." },
            ].map((item, index) => (
              <Reveal key={item.n} delay={index * 0.08}>
                <div className="glass gradient-border h-full rounded-2xl p-6"><span className="font-mono text-sm text-brand">{item.n}</span><h3 className="mt-3 text-xl font-semibold">{item.title}</h3><p className="mt-2 text-sm leading-6 text-white/65">{item.text}</p></div>
              </Reveal>
            ))}
          </div>
          <div className="mt-10"><Button asChild variant="glass" size="lg"><Link href="/methodology">Read the methodology <ArrowRight /></Link></Button></div>
        </Container>
      </section>

      {/* Audiences */}
      <Section>
        <SectionHeading eyebrow="Who it is for" title="Useful wherever verification happens." />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {audiences.map(({ icon: Icon, title, text, tint }, index) => (
            <Reveal key={title} delay={index * 0.06}><div className={`h-full rounded-2xl p-6 ${tint}`}><Icon className="mb-4 size-6 text-ink" aria-hidden /><h3 className="text-lg font-semibold">{title}</h3><p className="mt-1.5 text-sm leading-6 text-ink-soft/80">{text}</p></div></Reveal>
          ))}
        </div>
        <Reveal className="mt-8"><div className="overflow-hidden rounded-2xl border border-line"><Image src="/images/press-briefing.webp" alt="Journalists at a press briefing" width={1800} height={900} sizes="(max-width: 1152px) 100vw, 1152px" className="h-56 w-full object-cover sm:h-80" /></div></Reveal>
      </Section>

      {/* WhatsApp */}
      <section className="relative isolate overflow-hidden bg-gradient-to-br from-[#0f3d2e] via-[#0b2a21] to-night py-20 text-white sm:py-28">
        <div className="pointer-events-none absolute -left-20 top-10 -z-10 size-[380px] rounded-full bg-brand/20 blur-[120px]" />
        <Container className="grid gap-12 lg:grid-cols-2 lg:items-center">
          <Reveal className="flex justify-center"><div className="animate-float-slow"><ChatMock /></div></Reveal>
          <Reveal delay={0.1}>
            <Eyebrow dark>On WhatsApp</Eyebrow>
            <h2 className="text-3xl font-semibold leading-[1.08] tracking-tight sm:text-5xl">Check it where you got it.</h2>
            <p className="mt-5 text-lg leading-8 text-white/70">Forward a message, paste a link, or just ask. You get a plain answer with sources you can open, in English or Kiswahili. Reply YES to start, and RESULT to see it again.</p>
            <div className="mt-8 flex flex-wrap gap-3"><Button asChild size="lg"><a href={WHATSAPP_CONTACT_URL} target="_blank" rel="noopener noreferrer">Open WhatsApp <ArrowRight /></a></Button><Button asChild size="lg" variant="glass"><Link href="/whatsapp">How it works</Link></Button></div>
          </Reveal>
        </Container>
      </section>

      <CtaBand title="Do not guess. Check." text="Assume nothing. Follow the evidence.">
        <Button asChild size="lg"><Link href="/investigate">Start a check <ArrowRight /></Link></Button>
        <Button asChild size="lg" variant="glass"><Link href="/faq">Read the FAQ</Link></Button>
      </CtaBand>
    </SitePage>
  );
}
