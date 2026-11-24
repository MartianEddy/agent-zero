import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Container, CtaBand, PageHero } from "@/components/site/Section";
import { SitePage } from "@/components/site/SitePage";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = { title: "FAQ", description: "Answers about what Agent 0 can check, how it reaches a result, and how your information is handled." };

const groups: { title: string; items: [string, string][] }[] = [
  { title: "Using Agent 0", items: [
    ["What can I check?", "A specific factual claim, a public link, or an image or short video together with the claim it makes. Opinions and predictions cannot be fact-checked."],
    ["Do I have to sign up?", "Not in this demo. Anyone can start a check from the website or on WhatsApp."],
    ["How long does a check take?", "Usually a few minutes. You can leave the page. Your case keeps its reference, and both the workspace and WhatsApp let you come back to it."],
    ["Why does Agent 0 show me the claim first?", "So you stay in control. Research only starts once you confirm the claim is what you meant. On the web you can also edit or split claims."],
    ["Can I use it in Kiswahili?", "On WhatsApp you can write in Kiswahili or mix languages, and shortcuts like MSAADA and MATOKEO work. Coverage of sources in Kiswahili is still limited."],
  ] },
  { title: "Understanding results", items: [
    ["What does \"Not enough evidence yet\" mean?", "Agent 0 could not find enough solid, independent sources either way. It does not mean the claim is false."],
    ["Is evidence strength the chance a claim is true?", "No. It shows how much solid, independent evidence was found. The methodology page has the exact rules."],
    ["Why did it not use a website I know is reliable?", "Only passages Agent 0 could open and read count. Its list of recognised official sources is still small, so some good sources count for less than they should."],
    ["Can the AI get it wrong?", "Yes. The AI suggests and fixed rules decide, and every result links to the passages it relied on so you can check them. Please do, before publishing."],
  ] },
  { title: "Your information", items: [
    ["Who can see my checks?", "In this shared demo, case history is visible to other visitors, so use public, non-sensitive claims only. WhatsApp chats are scoped to your number."],
    ["Is my data used to train AI models?", "Not by default. Submissions are treated as private and are not used for training unless that is separately agreed with you."],
    ["Where is the full policy?", "The privacy page has a plain-language summary of what we store."],
  ] },
];

export default function FaqPage() {
  return (
    <SitePage>
      <PageHero eyebrow="FAQ" title="Questions, answered plainly." intro="Cannot find yours? Message us on WhatsApp from the footer." />
      <Container className="max-w-3xl py-14 sm:py-20">
        {groups.map((group) => (
          <section key={group.title} className="mb-12" aria-labelledby={group.title.replaceAll(" ", "-")}>
            <h2 id={group.title.replaceAll(" ", "-")} className="mb-4 text-xl font-semibold">{group.title}</h2>
            <Accordion type="single" collapsible className="grid gap-2">
              {group.items.map(([question, answer]) => <AccordionItem key={question} value={question}><AccordionTrigger>{question}</AccordionTrigger><AccordionContent>{answer}</AccordionContent></AccordionItem>)}
            </Accordion>
          </section>
        ))}
        <p className="text-sm text-muted"><Link href="/methodology" className="font-medium text-brand-ink underline underline-offset-4">How results are decided</Link> and <Link href="/privacy" className="font-medium text-brand-ink underline underline-offset-4">Privacy</Link></p>
      </Container>
      <CtaBand title="Ready to check something?" text="Start with a claim, a link or an image."><Button asChild size="lg"><Link href="/investigate">Start a check <ArrowRight /></Link></Button></CtaBand>
    </SitePage>
  );
}
