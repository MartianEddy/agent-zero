"use client";

import { useState } from "react";
import styles from "./InvestigationDemo.module.css";

const tabs = ["Overview", "Evidence", "Source trail", "Brief"] as const;
type Tab = (typeof tabs)[number];

const sampleSources = [
  { kind: "OFFICIAL", name: "County education office", note: "No closure notice found on the official channels checked.", status: "No primary statement located" },
  { kind: "NEWS", name: "Local newsroom report", note: "Reports a possible closure, citing an unnamed parent group.", status: "Secondary; attribution unclear" },
  { kind: "SOCIAL", name: "Shared screenshot", note: "Circulating image has no visible date or original post link.", status: "Origin not established" },
];

export function InvestigationDemo() {
  const [active, setActive] = useState<Tab>("Overview");
  return <section className={styles.demo} aria-labelledby="demo-title">
    <div className={styles.heading}><div><p className="eyebrow">Explore a sample</p><h2 id="demo-title">A claim, with its evidence in view.</h2></div><span className={styles.sample}>SAMPLE DATA · NOT A LIVE CHECK</span></div>
    <div className={styles.frame}>
      <div className={styles.top}><strong>INVESTIGATION <span>/ 0042</span></strong><span className={styles.unverified}>UNVERIFIED</span></div>
      <div className={styles.claim}><small>CLAIM UNDER INVESTIGATION</small><h3>“Schools in Nyeri County will remain closed tomorrow.”</h3><p>This sample has insufficient evidence to verify the claim.</p></div>
      <div className={styles.tabs} role="tablist" aria-label="Sample investigation sections">
        {tabs.map((tab, index) => <button key={tab} role="tab" id={`tab-${tab}`} tabIndex={active === tab ? 0 : -1} aria-selected={active === tab} aria-controls="demo-panel" onClick={() => setActive(tab)} onKeyDown={event => {
          if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
          event.preventDefault();
          const offset = event.key === "ArrowRight" ? 1 : -1;
          const next = tabs[(index + offset + tabs.length) % tabs.length];
          setActive(next);
          document.getElementById(`tab-${next}`)?.focus();
        }}>{tab}</button>)}
      </div>
      <div id="demo-panel" role="tabpanel" aria-labelledby={`tab-${active}`} className={styles.panel}>
        {active === "Overview" && <><div className={styles.metrics}><div><b>8</b><span>Items reviewed</span></div><div><b>3</b><span>Independent accounts</span></div><div><b>0</b><span>Original notices found</span></div></div><h4>What remains unclear</h4><p>No official closure notice was located in the sample material. The reports shown below do not independently confirm the claim.</p></>}
        {active === "Evidence" && <><h4>Evidence notes</h4><ul className={styles.notes}><li><span>GAP</span>No primary announcement located in the checked sample channels.</li><li><span>LIMIT</span>Two reports repeat information attributed to the same unnamed group.</li><li><span>UNKNOWN</span>The sample does not establish whether the screenshot is authentic or current.</li></ul></>}
        {active === "Source trail" && <><h4>Sources examined</h4><div className={styles.sources}>{sampleSources.map(source => <article key={source.name}><small>{source.kind}</small><div><b>{source.name}</b><p>{source.note}</p></div><span>{source.status}</span></article>)}</div></>}
        {active === "Brief" && <><h4>Verification brief · sample</h4><p className={styles.brief}>The available sample material does not establish whether schools in Nyeri County will be closed tomorrow. No primary notice is included, and the secondary accounts do not provide independent confirmation.</p><p>Suggested next step: check directly with the county education office and the relevant school administrations.</p></>}
      </div>
      <div className={styles.disclaimer}>Illustrative content only. This is not a current investigation or a factual update.</div>
    </div>
  </section>;
}
