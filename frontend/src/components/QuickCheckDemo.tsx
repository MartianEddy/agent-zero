"use client";

import { useState, type FormEvent } from "react";
import styles from "./QuickCheckDemo.module.css";

export function QuickCheckDemo() {
  const [message, setMessage] = useState("");
  const [fileName, setFileName] = useState("");
  const [hasResult, setHasResult] = useState(false);
  const [error, setError] = useState("");
  const hasInnovationWeekFixture = /mt\s*kenya/i.test(message) && /innovation\s*week/i.test(message) && /(today|final|last day|closing)/i.test(message);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!message.trim() && !fileName) {
      setError("Paste a message or choose a file to try the demo.");
      setHasResult(false);
      return;
    }
    setError("");
    setHasResult(true);
  }

  return <section className={styles.section} aria-labelledby="quick-check-title">
    <div className={styles.intro}>
      <p className="eyebrow">Try the simple demo</p>
      <h2 id="quick-check-title">Paste a message.<br /><span>See what a check looks like.</span></h2>
      <p>Try the researched Mt Kenya Innovation Week example, or enter your own text to see the investigation steps. Other inputs are not searched live.</p>
    </div>
    <form className={styles.form} onSubmit={submit}>
      <label htmlFor="demo-message">Message or claim</label>
      <textarea id="demo-message" value={message} onChange={event => { setMessage(event.target.value); setHasResult(false); }} placeholder="Paste a claim or message here…" rows={4} />
      <label className={styles.uploadLabel} htmlFor="demo-file">Or choose a file <span>Image, video, audio, PDF, or text</span></label>
      <input id="demo-file" type="file" accept="image/*,video/*,audio/*,.pdf,.txt,.doc,.docx" onChange={event => { setFileName(event.target.files?.[0]?.name ?? ""); setHasResult(false); }} />
      {fileName && <p className={styles.fileName}>Selected: {fileName}</p>}
      {error && <p className={styles.error} role="alert">{error}</p>}
      <button className="button button-primary" type="submit">Show demo result</button>
    </form>
    {hasResult && <div className={styles.result} role="status" aria-live="polite">
      {hasInnovationWeekFixture ? <>
        <div className={styles.resultHead}><span>SAMPLE SOURCE REVIEW · CHECKED 3 OCT 2026</span><b>Conflicts with schedule</b></div>
        <h3>The published programme does not show October 3 as the final day.</h3>
        <p>The claim appears to be: “Today, October 3, is the final day of Mt Kenya Innovation Week.” The official programme lists the week as running October 2–9, 2026. October 3 is scheduled for continuing hackathons; the exhibition, awards and closing ceremony are listed for October 9.</p>
        <div className={styles.nextSteps}><strong>Investigation flow</strong><ol><li><b>Extracted:</b> event name, date (“today”), and the claim that it is the final day.</li><li><b>Checked:</b> the event’s published dates and daily programme.</li><li><b>Compared:</b> the programme places closing activities on October 9, not October 3.</li><li><b>Limit:</b> this is one publisher’s schedule; it confirms the announced programme, not whether activities actually took place.</li></ol></div>
        <div className={styles.sources}><strong>Sources reviewed</strong><a href="https://www.mtkenyainnovationweek.com/index.php" target="_blank" rel="noreferrer">Official programme — event dates and daily schedule</a><a href="https://www.mtkenyainnovationweek.com/attend.php" target="_blank" rel="noreferrer">Official attendee schedule — October 2–9 activities</a></div>
        <small>Example result based on the published programme checked October 3, 2026. The demo does not search sources live.</small>
      </> : <>
        <div className={styles.resultHead}><span>INVESTIGATION PREVIEW</span><b>No live sources searched</b></div>
        <h3>{message.trim() ? "Your message is ready for a source check." : "Your file is ready for a source check."}</h3>
        <p>{message.trim() ? `“${message.trim().slice(0, 220)}${message.trim().length > 220 ? "…" : ""}”` : fileName}</p>
        <div className={styles.nextSteps}><strong>Investigation flow</strong><ol><li>Identify the specific claim, people, places and dates.</li><li>Find original sources and related reporting.</li><li>Compare independent sources and note contradictions.</li><li>Prepare a brief showing evidence, uncertainty and next steps.</li></ol></div>
        <small>This prototype has no live search connection, so it cannot report findings for this input. Your selected file is not uploaded or inspected.</small>
      </>}
    </div>}
  </section>;
}
