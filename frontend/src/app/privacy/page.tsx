import type { Metadata } from "next";
import Link from "next/link";
import { Container, PageHero } from "@/components/site/Section";
import { Note, Prose } from "@/components/site/Prose";
import { SitePage } from "@/components/site/SitePage";

export const metadata: Metadata = { title: "Privacy", description: "A plain-language summary of what Agent 0 stores and why." };

export default function PrivacyPage() {
  return (
    <SitePage>
      <PageHero eyebrow="Privacy" title="What we store, and why." intro="A plain-language summary of how this demo handles your information." />
      <Container className="max-w-3xl py-14 sm:py-20">
        <Note tone="warn"><strong>Demo notice.</strong> This is a shared demonstration service. Please submit public, non-sensitive information only. This summary is not a final legal policy and is pending legal review.</Note>
        <Prose>
          <h2>On the website</h2>
          <ul>
            <li><strong>What you submit:</strong> the claim, link, or image or video you send, and the case we build from it (claims, sources, evidence, result).</li>
            <li><strong>Who can see it:</strong> in this demo, case history is shared, so other visitors can see it. Do not submit anything private.</li>
            <li><strong>Why:</strong> only to run your check and show you the result.</li>
          </ul>
          <h2>On WhatsApp</h2>
          <ul>
            <li>We keep your phone number as a keyed hash to match your chat to your cases. A separately encrypted copy is kept so Agent 0 can send you a result.</li>
            <li>Chat context is short-lived and deleted automatically after it expires, about 24 hours after your last message.</li>
            <li>Cases you confirm are saved with a reference so you can use RESULT and HISTORY later.</li>
            <li>Reply <strong>STOP</strong> to turn off automatic result messages. Your checks still run.</li>
          </ul>
          <h2>AI providers and search</h2>
          <p>To do its work, Agent 0 sends the text of your claim, and the public pages it found, to AI and search services. Their handling of that data is governed by their own terms.</p>
          <h2>Training AI models</h2>
          <p>Your submissions are not used to train AI models by default.</p>
          <h2>Still being decided</h2>
          <ul>
            <li>How long saved cases are kept, and how you can ask for deletion.</li>
            <li>Sign-in and per-user privacy, so that cases are visible only to their owner.</li>
          </ul>
          <p>Questions? See the <Link href="/faq">FAQ</Link> or message us on WhatsApp.</p>
        </Prose>
      </Container>
    </SitePage>
  );
}
