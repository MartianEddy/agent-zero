import Link from "next/link";
import type { Metadata } from "next";
import { Arrow } from "@/components/Arrow";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { InvestigationDemo } from "@/components/InvestigationDemo";
import styles from "./home.module.css";

export const metadata: Metadata = { title: "Assume nothing. Follow the evidence.", description: "Agent 0 is an AI-assisted verification workspace in development for journalists. Explore an illustrative sample investigation and see the intended evidence trail." };

const capabilities = ["Trace sources", "Compare evidence", "Find corroboration", "Surface contradictions", "Build a verification brief"];
const stages = [
  { number: "01", title: "Submit", text: "Paste a claim or URL, or upload an image, video, audio or document." },
  { number: "02", title: "Investigate", text: "Agent 0 searches relevant sources and gathers evidence." },
  { number: "03", title: "Corroborate", text: "Compare independent information, identify contradictions and trace provenance." },
  { number: "04", title: "Build brief", text: "Produce a clear summary of evidence, uncertainty and recommended next steps." },
];
const roles = [
  { title: "Journalists", text: "Verify claims, sources and media before publishing." },
  { title: "Editors", text: "Review evidence trails and support editorial decisions." },
  { title: "Fact-checkers", text: "Investigate and document claims with transparent evidence." },
  { title: "Newsrooms", text: "Strengthen verification workflows across teams." },
];

function Glyph({ type }: { type: string }) {
  const paths: Record<string, string> = {
    search: "M10.8 18a7.2 7.2 0 1 1 0-14.4 7.2 7.2 0 0 1 0 14.4ZM16 16l5 5",
    compare: "M5 3h11l4 4v14H5zM16 3v5h4M8 12h8M8 16h8",
    network: "M12 5v6m0 0-6 7m6-7 6 7M12 4a2 2 0 1 0 0 .1M5 19a2 2 0 1 0 0 .1M19 19a2 2 0 1 0 0 .1",
    contradictions: "M12 3 22 21H2L12 3Zm0 6v5m0 3v.1",
    brief: "M6 3h12v18H6zM9 8h6M9 12h6M9 16h4",
  };
  return <svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d={paths[type] ?? paths.search} /></svg>;
}

function EvidenceRing() {
  return <div className={styles.ringScene} aria-hidden="true"><div className={styles.orbit} /><div className={styles.orbitInner} />
    <i className={`${styles.node} ${styles.nodeOne}`} /><i className={`${styles.node} ${styles.nodeTwo}`} /><i className={`${styles.node} ${styles.nodeThree}`} /><i className={`${styles.node} ${styles.nodeFour}`} /><span className={styles.ringCore}>0</span>
  </div>;
}

function InvestigationPreview() {
  return <div className={styles.preview} aria-label="Illustrative Agent 0 investigation preview">
    <div className={styles.previewTop}><div className={styles.previewBrand}>AGENT <span>0</span></div><div className={styles.previewMeta}>INVESTIGATION <i>DEMO DATA</i></div><div className={styles.avatar}>A</div></div>
    <div className={styles.previewBody}>
      <aside className={styles.sidebar} aria-label="Sample workspace sections">
        <div className={styles.sideActive}><Glyph type="search" /> New investigation</div><div><Glyph type="brief" /> Investigations</div><div><Glyph type="network" /> Sources</div><div><Glyph type="compare" /> Media analysis</div><div><Glyph type="compare" /> Timeline</div><div><Glyph type="brief" /> Brief</div><div className={styles.sideBottom}>EVIDENCE WORKSPACE</div>
      </aside>
      <div className={styles.investigation}>
        <div className={styles.claimLine}><div><p className={styles.micro}>CLAIM UNDER INVESTIGATION</p><h2>“Schools in Nyeri County will remain closed tomorrow.”</h2></div><div className={styles.status}><span /> UNVERIFIED</div></div>
        <p className={styles.statusExplain}>Evidence is currently insufficient to verify this claim.</p>
        <div className={styles.tabs}><span>Overview</span><span>Sources <b>(8)</b></span><span>Media</span><span>Timeline</span><span>Brief</span></div>
        <div className={styles.metrics}><div><strong className={styles.limeNumber}>8</strong><span>Sources examined</span></div><div><strong>3</strong><span>Independent sources</span></div><div><strong className={styles.redNumber}>0</strong><span>Original sources</span></div><div><small>LAST CHECKED</small><strong className={styles.timeValue}>03:42</strong><span>Sample timestamp</span></div></div>
        <div className={styles.findings}><div><h3>Key findings</h3><p><i className={styles.greenDot} />No official statement located</p><p><i className={styles.greenDot} />Some local media reporting, but no primary source</p><p><i className={styles.amberDot} />Contradictory information from earlier reports</p><p><i className={styles.amberDot} />More evidence needed to verify this claim</p></div>
          <div className={styles.sourceBreakdown}><h3>Source breakdown</h3><p>Official sources <b>0</b></p><p>News media <span><i style={{ width: "72%" }} /></span><b>4</b></p><p>Social media <span><i style={{ width: "48%" }} /></span><b>3</b></p><p>Other <span><i style={{ width: "18%" }} /></span><b>1</b></p></div></div>
      </div>
    </div>
    <div className={styles.previewFoot}><span>Illustrative interface · sample claim and values</span><span>HUMANS MAKE THE CALL</span></div>
  </div>;
}

export default function HomePage() {
  return <main><SiteHeader />
    <section className={styles.hero}><div className={`container ${styles.heroGrid}`}>
      <div className={styles.heroCopy}><p className="eyebrow">Investigative intelligence for journalists</p><h1>Assume nothing.<br /><span>Follow the evidence.</span></h1>
        <p className={styles.lede}>Investigate suspicious claims, media and documents against available evidence before they become tomorrow&apos;s headline.</p>
        <div className={styles.heroActions}><Link href="/demo" className="button button-primary">Explore the sample investigation <Arrow /></Link><a href="#how-it-works" className="button button-secondary"><span className={styles.playIcon} /> See how it works</a></div>
        <p className={styles.forWho}><Glyph type="network" /><span>Built for journalists, editors and media practitioners</span></p>
      </div><div className={styles.previewWrap}><EvidenceRing /><InvestigationPreview /></div>
    </div></section>

    <section id="capabilities" className={styles.capabilities} aria-label="Agent 0 capabilities"><div className={`container ${styles.capabilityRow}`}>{capabilities.map((label, index) => <div className={styles.capability} key={label}><Glyph type={["search", "compare", "network", "contradictions", "brief"][index]} /><span>{label}</span></div>)}</div></section>

    <InvestigationDemo />

    <section className={styles.spread}><div className={`container ${styles.spreadGrid}`}>
      <div className={styles.spreadDiagram} aria-label="Illustration of information shared between sources"><div className={styles.postCard}><span>SCREENSHOT</span><strong>“Schools closed tomorrow?”</strong><div className={styles.postLines} /></div><span className={styles.diagramArrow}>→</span><div className={styles.socialStack}><div>REPOST <b>↗</b></div><div>MESSAGING <b>↗</b></div><div>SOCIAL POST <b>↗</b></div></div><span className={styles.diagramArrow}>→</span><div className={styles.newsroomNode}><span className={styles.newsroomDot} /><strong>NEWSROOM</strong><small>verify before publishing</small></div></div>
      <div className={styles.spreadCopy}><p className="eyebrow">The problem</p><h2>Information moves<br />faster than verification.</h2><p>A claim can move from a screenshot to a repost, into chats and across social platforms before it reaches a newsroom. Verification takes deliberate work.</p><div className={styles.flowLabels}><span>Screenshot</span><i>→</i><span>Repost</span><i>→</i><span>Messaging</span><i>→</i><span>Social</span><i>→</i><span>Newsroom</span></div></div>
    </div></section>

    <section id="how-it-works" className={styles.process}><div className="container"><div className={styles.sectionIntro}><div><p className={styles.eyebrowDark}>How Agent 0 works</p><h2>From claim to clarity.</h2></div><p>Follow a transparent process with evidence visible at every step. Agent 0 supports the investigation; people decide what the evidence means.</p></div>
      <div className={styles.stages}>{stages.map((stage, index) => <article className={styles.stage} key={stage.number}><div className={styles.stageTop}><span>{stage.number}</span>{index < stages.length - 1 && <i />}</div><h3>{stage.title}</h3><p>{stage.text}</p></article>)}</div>
      <Link href="/how-it-works" className={`${styles.textLink} ${styles.darkLink}`}>See how Agent 0 works <Arrow /></Link>
    </div></section>

    <section id="newsrooms" className={styles.audience}><div className="container"><div className={styles.sectionIntro}><div><p className="eyebrow">Built for real-world newsrooms</p><h2>Support every step of<br />the verification process.</h2></div><p>Designed for people who need to understand where information came from, what supports it and what remains uncertain.</p></div>
      <div className={styles.roleGrid}>{roles.map(({ title, text }, index) => <article className={styles.role} key={title}><span className={styles.roleNumber}>0{index + 1}</span><h3>{title}</h3><p>{text}</p><span className={styles.roleMark} aria-hidden="true">↗</span></article>)}</div>
    </div></section>

    <section id="principle" className={styles.principle}><div className={`container ${styles.principleInner}`}><div className={styles.principleRing} aria-hidden="true"><span>0</span><i /><i /><i /></div><div><p className={styles.eyebrowDark}>The principle</p><h2>AI investigates.<br /><span>Humans decide.</span></h2><p>Agent 0 organizes evidence, exposes sources and preserves uncertainty. It should help you see what is known and what is missing—not ask you to trust a generated truth score.</p></div></div></section>

    <section className={styles.finalCta}><div className={`container ${styles.finalInner}`}><div><p className="eyebrow">Explore the prototype</p><h2>See an investigation take shape.</h2><p>Review illustrative sample material; no live claim check is connected.</p></div><Link href="/demo" className="button button-primary">Explore the demo <Arrow /></Link></div></section>
    <SiteFooter />
  </main>;
}
