import Link from "next/link";
import Image from "next/image";
import { LandingInvestigationInput } from "@/components/LandingInvestigationInput";
import { Arrow } from "@/components/Arrow";
import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import styles from "./home.module.css";

const questions = [
  ["A screenshot arrives.", "Is it original? Where did it come from?"],
  ["A claim starts spreading.", "Who said it? Is there an official source?"],
  ["Several articles repeat it.", "Are they independent—or repeating the same source?"],
];

const steps = ["Understand what was shared", "Look for reliable sources", "Compare the available evidence"];

export default function HomePage() {
  return <main className={styles.page}>
    <SiteHeader />

    <section className={styles.hero}>
      <div className={styles.heroInner}>
        <div className={styles.heroCopy}>
          <p className={styles.eyebrow}>AI-assisted verification for everyone</p>
          <h1>Know what<br />holds up before<br /><span>you publish.</span></h1>
          <p className={styles.lede}>Agent 0 helps you investigate questionable claims, links and images—so you can see what the evidence supports and what remains uncertain.</p>
          <p className={styles.audience}>For journalists, editors, researchers, fact-checkers and anyone checking what they’ve seen.</p>
          <div className={styles.heroActions}><a className="button button-primary" href="#investigate">Start investigating <Arrow /></a><a href="#how-it-works">See how it works <Arrow /></a></div>
          <ul className={styles.trustRow} aria-label="What you can check"><li><span aria-hidden="true">↗</span> Claims, links<br />and images</li><li><span aria-hidden="true">⌕</span> Sources and<br />media details</li><li><span aria-hidden="true">✓</span> Clear results<br />with uncertainty</li></ul>
        </div>
        <div className={styles.inputColumn} id="investigate"><div className={styles.heroScene}><span className={styles.sceneLabel}>A clear place to start</span><LandingInvestigationInput /></div></div>
      </div>
      <p className={styles.brandLine}>Assume nothing. <span>Follow the evidence.</span><b>AI investigates. Humans decide.</b></p>
    </section>

    <section className={styles.problem}>
      <div className={styles.sectionHeader}><p className={styles.eyebrow}>The work behind a simple question</p><h2>Information moves fast.<br />Verification takes work.</h2><p>Agent 0 helps bring these questions into one investigation.</p></div>
      <div className={styles.questionGrid}>{questions.map(([title, text], index) => <article key={title}><span>0{index + 1}</span><h3>{title}</h3><p>{text}</p></article>)}</div>
    </section>

    <section className={styles.example} id="how-it-works">
      <div className={styles.exampleIntro}><p className={styles.eyebrow}>A sample investigation</p><h2>From claim<br />to evidence.</h2><p>See how the workspace keeps the question, the evidence and what remains uncertain together.</p><Link href="/investigate">Investigate something <Arrow /></Link></div>
      <div className={styles.sample}>
        <div className={styles.sampleLabel}>ILLUSTRATIVE EXAMPLE · NOT A LIVE CHECK</div>
        <p className={styles.sampleKicker}>Claim</p><h3>“Schools in Nyeri County will remain closed tomorrow.”</h3>
        <div className={styles.steps}>{steps.map((step, index) => <div key={step} className={styles.step}><span>{index + 1}</span><p>{step}</p></div>)}</div>
        <div className={styles.sampleResult}><p className={styles.sampleKicker}>Result</p><strong>Not enough evidence yet</strong><p>We couldn’t confirm the announcement from the sources reviewed. That does not mean it didn’t happen.</p></div>
        <div className={styles.sampleEvidence}><h4>Why it isn’t verified</h4><ul><li>Official sources: no matching announcement found</li><li>Independent reporting: some reports repeat the same notice</li><li>Image origin: original publisher not established</li></ul></div>
        <div className={styles.sampleClose}><p className={styles.sampleUnknown}><strong>Still unknown</strong><br />Who first shared the notice, and whether the named authority issued it.</p><p className={styles.sampleNext}><strong>A useful next step</strong><br />Check with the county education office before sharing the notice.</p></div>
      </div>
    </section>

    <section className={styles.imageStory}>
      <div className={styles.imageIntro}><p className={styles.eyebrow}>Image investigation</p><h2>An image is more than what it shows.</h2><p>Agent 0 describes the information it can inspect, and is clear about the details it could not establish.</p></div>
      <div className={styles.imagePanel}>
        <div className={styles.imageIllustration} role="img" aria-label="Illustration of an uploaded notice image"><div className={styles.mockPhoto}><span>EXAMPLE IMAGE</span><i /><b /><small>NOTICE</small><em>County Education Office</em><hr /><hr /><hr /></div></div>
        <div className={styles.imageFacts}>
          <article><h3>Origin &amp; history</h3><strong>No content credentials found</strong><p>This doesn’t mean the image is fake. Its origin could not be established from attached credentials.</p></article>
          <article><h3>What the file tells us</h3><p>File type and image dimensions can help describe the file, but don’t establish where it came from.</p></article>
          <article><h3>What Agent 0 can see</h3><p>Visible text and details are presented as observations that should be checked against other evidence.</p></article>
          <article className={styles.unknownBlock}><h3>Still unknown</h3><p>Original uploader · first publication · whether the named authority issued the notice</p></article>
        </div>
      </div>
      <p className={styles.imageFootnote}>Example only. Content credentials can help describe an image’s history; their presence or absence does not prove whether the depicted event is true.</p>
    </section>

    <section className={styles.newsroom}>
      <div className={styles.audienceFeature}>
        <div className={styles.audiencePhoto}><Image src="/images/presenter-studio.webp" alt="A presenter recording a show in a small studio" width={1800} height={1200} sizes="(max-width: 760px) 100vw, 48vw" /></div>
        <div className={styles.audienceCopy}><p className={styles.eyebrow}>For newsrooms and beyond</p><h2>For anyone who needs to check what they’ve seen.</h2><p>Bring a question into one place, review the available evidence, and decide what to do with it.</p><ul className={styles.audienceList}><li>Journalists checking a claim before publication</li><li>Editors reviewing evidence and open questions</li><li>Researchers and fact-checkers comparing accounts</li><li>Everyday readers deciding whether to share</li></ul></div>
      </div>
      <div className={styles.journey}><div><span>1</span><p><strong>Share</strong> a claim, link or image</p></div><i aria-hidden="true">→</i><div><span>2</span><p><strong>Review</strong> evidence and uncertainty</p></div><i aria-hidden="true">→</i><div><span>3</span><p><strong>Decide</strong> what to do next</p></div></div>
    </section>

    <section className={styles.transparency}>
      <div><p className={styles.eyebrow}>A tool for judgment—not a substitute for it</p><h2>Evidence in view.<br />Decisions in your hands.</h2><p>Agent 0 helps you examine what is available. It does not decide what is true or what you should publish.</p></div>
      <div className={styles.principles}>
        <article><h3>Follow the source</h3><p>Review the material behind important findings.</p></article>
        <article><h3>Keep the gaps visible</h3><p>See what couldn’t be confirmed or completed.</p></article>
        <article><h3>Make your own call</h3><p>Use the evidence with your own judgment and standards.</p></article>
      </div>
    </section>

    <section className={styles.finalCta}><div className={styles.ctaMark}><Image src="/brand/agent-0-logo.png" alt="Agent 0" width={1774} height={887} sizes="150px" /></div><p className={styles.eyebrow}>A question worth checking?</p><h2>Don’t guess. Investigate.</h2><p>Assume nothing. Follow the evidence.</p><Link className="button button-primary" href="/investigate">Start an investigation <Arrow /></Link><Link className={styles.secondaryLink} href="/how-it-works">See how Agent 0 works</Link></section>

    <SiteFooter />
  </main>;
}
