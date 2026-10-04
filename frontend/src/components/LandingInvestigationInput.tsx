"use client";

import { FormEvent, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { inferInputType, uploadErrorMessage } from "@/app/investigate/presentation.mjs";
import styles from "./LandingInvestigationInput.module.css";

const examples = ["Did the government announce this?", "Is this image from today’s event?", "Has this claim been reported elsewhere?"];

export function LandingInvestigationInput() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [content, setContent] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      let response: Response;
      if (file) {
        const body = new FormData();
        body.set("file", file);
        body.set("prompt", content.trim());
        response = await fetch("/api/investigations/media", { method: "POST", body });
      } else {
        response = await fetch("/api/investigations", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ input_type: inferInputType(content), content: content.trim() }),
        });
      }
      if (!response.ok) {
        let detail: unknown;
        try { detail = (await response.json() as { detail?: unknown }).detail; } catch { detail = null; }
        throw new Error(uploadErrorMessage(detail));
      }
      const created = await response.json() as { id: string };
      router.push(`/investigate?investigation=${encodeURIComponent(created.id)}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The investigation couldn’t be started. Try again.");
      setBusy(false);
    }
  }

  function chooseFile(value: File | null) {
    if (!value) return;
    if (!["image/jpeg", "image/png", "image/webp"].includes(value.type)) {
      setError("Choose a JPEG, PNG or WebP image.");
      return;
    }
    setFile(value);
    setError("");
  }

  return <div className={styles.wrap}>
    <form className={styles.form} onSubmit={submit} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); chooseFile(event.dataTransfer.files?.[0] ?? null); }} onPaste={(event) => { const image = Array.from(event.clipboardData.items).find((item) => item.type.startsWith("image/"))?.getAsFile(); if (image) { event.preventDefault(); chooseFile(image); } }}>
      <label htmlFor="landing-investigation-input">What do you want to check?</label>
      <textarea id="landing-investigation-input" rows={3} maxLength={20000} placeholder="Paste a claim or link…" value={content} onChange={(event) => setContent(event.target.value)} aria-describedby="landing-input-help" />
      <p className={styles.help} id="landing-input-help">Paste a claim, a web link, or drop an image here. Agent 0 will work out what you shared.</p>
      <input ref={inputRef} className={styles.fileInput} type="file" accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp" aria-label="Choose an image" onChange={(event) => chooseFile(event.target.files?.[0] ?? null)} />
      {file && <div className={styles.file}><span aria-hidden="true">▧</span><div><strong>{file.name || "Selected image"}</strong><small>{file.type} · {Math.max(1, Math.round(file.size / 1024))} KB</small></div><button type="button" onClick={() => { setFile(null); if (inputRef.current) inputRef.current.value = ""; }}>Remove</button></div>}
      <div className={styles.actions}><button className={styles.addImage} type="button" onClick={() => inputRef.current?.click()}>＋ Add image</button><button className={styles.submit} disabled={busy || (!content.trim() && !file)}>{busy ? "Starting investigation…" : <>Investigate <span aria-hidden="true">→</span></>}</button></div>
      {error && <p className={styles.error} role="alert">{error}</p>}
    </form>
    <div className={styles.tryExamples}><span>Try an example</span>{examples.map((example) => <button key={example} type="button" onClick={() => setContent(example)}>{example}</button>)}</div>
  </div>;
}
