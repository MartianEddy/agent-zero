import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { ChatMock } from "@/components/site/ChatMock";
import { Container, CtaBand, Eyebrow, Section, SectionHeading } from "@/components/site/Section";
import { SitePage } from "@/components/site/SitePage";
import { Button } from "@/components/ui/button";
import { WHATSAPP_CONTACT_URL } from "@/lib/contact";

export const metadata: Metadata = { title: "Check on WhatsApp", description: "Send Agent 0 a claim, link or question on WhatsApp and get a plain-language answer with sources." };

const steps = [
  ["Send it", "Paste the claim or a link, or ask a question in English, Kiswahili or a mix."],
  ["Confirm", "Agent 0 shows the exact claim it will check. Nothing starts until you tap Submit."],
  ["Get the answer", "You get the result first, then why, how strong the evidence is, and the sources to read."],
  ["Come back later", "Every check has a reference. Send RESULT or HISTORY any time."],
];
const commands: [string, string][] = [
  ["RESULT", "Your latest result, or RESULT followed by a reference for a specific check."],
  ["HISTORY", "Your recent checks with their references."],
  ["STATUS", "How a check is going."],
  ["RETRY", "Try a stopped check again without resending the claim."],
  ["STOP or ALERTS ON", "Turn automatic result messages off or on."],
  ["HELP or MSAADA", "What Agent 0 can do."],
];

export default function WhatsAppPage() {
  return (
    <SitePage>
      <div className="border-b border-line bg-surface">
        <Container className="grid gap-12 py-14 sm:py-20 lg:grid-cols-[1.1fr_1fr] lg:items-center">
          <div>
            <Eyebrow>On WhatsApp</Eyebrow>
            <h1 className="text-4xl font-semibold leading-[1.05] sm:text-5xl">Check a claim right where you got it.</h1>
            <p className="mt-5 max-w-xl text-lg leading-8 text-muted">Forward a message, paste a link, or just ask. Agent 0 shows you what it understood, checks public sources, and replies in plain language with links you can open.</p>
            <div className="mt-8 flex flex-wrap gap-3"><Button asChild size="lg"><a href={WHATSAPP_CONTACT_URL} target="_blank" rel="noopener noreferrer">Open WhatsApp <ArrowRight /></a></Button><Button asChild size="lg" variant="outline"><Link href="/privacy">Privacy on WhatsApp</Link></Button></div>
          </div>
          <div className="flex justify-center lg:justify-end"><ChatMock /></div>
        </Container>
      </div>
      <Section>
        <SectionHeading eyebrow="How it works" title="From claim to answer in a few taps." />
        <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{steps.map(([title, text], index) => <li key={title} className="rounded-lg border border-line bg-surface p-5"><span className="font-mono text-xs text-faint">0{index + 1}</span><h3 className="mt-3 font-semibold">{title}</h3><p className="mt-1.5 text-sm leading-6 text-muted">{text}</p></li>)}</ol>
      </Section>
      <Section tone="subtle">
        <SectionHeading eyebrow="Shortcuts" title="You do not need them. They are there when you want speed." intro="You can simply talk to Agent 0. Shortcuts are single words you can send at any time." />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{commands.map(([code, text]) => <div key={code} className="rounded-lg border border-line bg-surface p-5"><code className="rounded bg-brand-soft px-2 py-1 font-mono text-xs font-semibold text-brand-ink">{code}</code><p className="mt-3 text-sm leading-6 text-muted">{text}</p></div>)}</div>
        <p className="mt-6 text-sm text-muted">Kiswahili shortcuts: MSAADA, MATOKEO, HALI, HISTORIA, GHAIRI.</p>
      </Section>
      <CtaBand title="Unsure about a message?" text="Send it to Agent 0 before you share it."><Button asChild size="lg"><a href={WHATSAPP_CONTACT_URL} target="_blank" rel="noopener noreferrer">Open WhatsApp <ArrowRight /></a></Button></CtaBand>
    </SitePage>
  );
}
