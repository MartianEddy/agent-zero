import Image from "next/image";
import Link from "next/link";
import { ArrowRight, Building2, FileSearch, GraduationCap, Layers, Link2, Newspaper, Scale, Search, ShieldCheck, Smartphone, TextCursorInput, Users } from "lucide-react";
import { ChatMock } from "@/components/site/ChatMock";
import { QuickCheck } from "@/components/site/QuickCheck";
import { ResultPreview } from "@/components/site/ResultPreview";
import { Container, CtaBand, Eyebrow, Section, SectionHeading } from "@/components/site/Section";
import { SitePage } from "@/components/site/SitePage";
import { Button } from "@/components/ui/button";
import { WHATSAPP_CONTACT_URL } from "@/lib/contact";

const promises = [
  { icon: ShieldCheck, title: "You approve the claim first", text: "Agent 0 shows what it understood. Nothing is researched until you confirm." },
  { icon: Link2, title: "Every result links to its sources", text: "Open the exact passages behind a result, and see which sources could not be read." },
  { icon: Layers, title: "Gaps stay visible", text: "Not enough evidence is reported as exactly that. It is never presented as false." },
];

const steps = [
  { icon: TextCursorInput, title: "Share it", text: "Paste a claim or a link, or upload an image or short video with the question you have." },
  { icon: Search, title: "We look for sources", text: "Official records first, then independent reporting and earlier fact-checks." },
  { icon: Scale, title: "We compare what we find", text: "Sources that copy each other count once. Fixed rules, not a guess, set the result." },
  { icon: FileSearch, title: "You decide", text: "Read the result, open the sources and see what is still unknown." },
];

const audiences = [
  { icon: Newspaper, title: "Journalists", text: "Check a claim or image before it moves into a story." },
  { icon: Building2, title: "Editors and desks", text: "Review the evidence and its limits before an editorial call." },
  { icon: Users, title: "Fact-checkers and researchers", text: "Compare accounts and keep a clear record of what was examined." },
  { icon: GraduationCap, title: "Everyone else", text: "Decide whether a message is worth sharing, in a minute." },
];

export default function HomePage() {
  return (
    <SitePage>
      <div className="border-b border-line bg-surface">
        <Container className="grid gap-12 py-14 sm:py-20 lg:grid-cols-[1.05fr_1fr] lg:items-center">
          <div>
            <Eyebrow>Claim checking for everyone</Eyebrow>
            <h1 className="text-5xl font-semibold leading-[1.02] sm:text-6xl">Check a claim <span className="text-brand-ink">before you share it.</span></h1>
            <p className="mt-6 max-w-xl text-lg leading-8 text-muted">Paste a claim, a link or an image. Agent 0 finds the sources, compares what they say, and tells you plainly what holds up and what does not.</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button asChild size="lg"><Link href="/investigate">Start a check <ArrowRight /></Link></Button>
              <Button asChild size="lg" variant="outline"><a href={WHATSAPP_CONTACT_URL} target="_blank" rel="noopener noreferrer"><Smartphone /> Check on WhatsApp</a></Button>
            </div>
            <p className="mt-6 text-sm text-faint">For journalists, editors, fact-checkers, researchers and anyone checking what they have seen.</p>
          </div>
          <QuickCheck />
        </Container>
      </div>

      <Section tone="plain" className="py-12 sm:py-16">
        <ul className="grid gap-6 md:grid-cols-3">
          {promises.map(({ icon: Icon, title, text }) => (
            <li key={title} className="flex gap-4">
              <span className="grid size-10 shrink-0 place-items-center rounded-md bg-brand-soft text-brand-ink"><Icon className="size-5" aria-hidden /></span>
              <div><h2 className="text-base font-semibold">{title}</h2><p className="mt-1 text-sm leading-6 text-muted">{text}</p></div>
            </li>
          ))}
        </ul>
      </Section>

      <Section tone="subtle" id="how-it-works">
        <SectionHeading eyebrow="How it works" title="From a question to evidence you can inspect." intro="Four steps, and you stay in control of each one." />
        <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {steps.map(({ icon: Icon, title, text }, index) => (
            <li key={title} className="rounded-lg border border-line bg-surface p-5">
              <div className="mb-4 flex items-center justify-between"><span className="grid size-10 place-items-center rounded-md bg-subtle text-ink"><Icon className="size-5" aria-hidden /></span><span className="font-mono text-xs text-faint">0{index + 1}</span></div>
              <h3 className="text-base font-semibold">{title}</h3><p className="mt-1.5 text-sm leading-6 text-muted">{text}</p>
            </li>
          ))}
        </ol>
        <p className="mt-6 text-sm"><Link href="/methodology" className="font-semibold text-brand-ink underline underline-offset-4">Read the exact rules behind a result</Link></p>
      </Section>

      <Section>
        <div className="grid gap-12 lg:grid-cols-[1fr_1.1fr] lg:items-center">
          <div>
            <Eyebrow>A clear answer</Eyebrow>
            <h2 className="text-3xl font-semibold leading-[1.1] sm:text-4xl">The result first. The reasons right behind it.</h2>
            <p className="mt-4 text-lg leading-8 text-muted">You get a plain verdict, how strong the evidence is, what could not be confirmed, and a suggested next step.</p>
            <ul className="mt-6 grid gap-3 text-[15px] text-ink-soft">
              {["Five outcomes, each in plain words", "Evidence strength: Low, Medium or High", "What is still unknown, and what to check next"].map((item) => <li key={item} className="flex items-center gap-3"><span className="size-1.5 rounded-full bg-brand-ink" aria-hidden />{item}</li>)}
            </ul>
          </div>
          <ResultPreview />
        </div>
      </Section>

      <Section tone="surface">
        <SectionHeading eyebrow="Who it is for" title="Useful wherever verification happens." />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {audiences.map(({ icon: Icon, title, text }) => (
            <div key={title} className="rounded-lg border border-line bg-bg p-5"><Icon className="mb-4 size-5 text-brand-ink" aria-hidden /><h3 className="text-base font-semibold">{title}</h3><p className="mt-1.5 text-sm leading-6 text-muted">{text}</p></div>
          ))}
        </div>
        <div className="mt-10 overflow-hidden rounded-xl border border-line">
          <Image src="/images/press-briefing.webp" alt="Journalists at a press briefing" width={1800} height={900} sizes="(max-width: 1152px) 100vw, 1152px" className="h-56 w-full object-cover sm:h-72" />
        </div>
      </Section>

      <Section tone="subtle">
        <div className="grid gap-12 lg:grid-cols-2 lg:items-center">
          <div className="order-2 flex justify-center lg:order-1"><ChatMock /></div>
          <div className="order-1 lg:order-2">
            <Eyebrow>On WhatsApp</Eyebrow>
            <h2 className="text-3xl font-semibold leading-[1.1] sm:text-4xl">Check it where you got it.</h2>
            <p className="mt-4 text-lg leading-8 text-muted">Forward a message, paste a link, or just ask. You get a plain answer with sources you can open, in English or Kiswahili.</p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Button asChild><a href={WHATSAPP_CONTACT_URL} target="_blank" rel="noopener noreferrer">Open WhatsApp <ArrowRight /></a></Button>
              <Button asChild variant="outline"><Link href="/whatsapp">How it works</Link></Button>
            </div>
          </div>
        </div>
      </Section>

      <CtaBand title="Do not guess. Check." text="Assume nothing. Follow the evidence.">
        <Button asChild size="lg"><Link href="/investigate">Start a check <ArrowRight /></Link></Button>
        <Button asChild size="lg" variant="outline" className="border-white/30 bg-transparent text-white hover:bg-white/10"><Link href="/methodology">See the method</Link></Button>
      </CtaBand>
    </SitePage>
  );
}
