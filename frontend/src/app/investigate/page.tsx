"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState, type DragEvent, type FormEvent } from "react";
import { ArrowRight, LoaderCircle, Paperclip, Plus, Trash2, UploadCloud, X } from "lucide-react";
import { inferInputType } from "./presentation.mjs";
import type { ClaimType, Investigation, TriageClaim, TriagePreview } from "./types";
import { PageHeader, WorkspacePage, WorkspaceShell } from "@/components/workspace/WorkspaceShell";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Label, Select, Textarea } from "@/components/ui/field";
import { CLAIM_TYPE_LABEL, formatBytes, readError } from "@/lib/api";
import { cn } from "@/lib/utils";

const MEDIA_TYPES = ["image/jpeg", "image/png", "image/webp", "video/mp4", "video/webm"];
const EXAMPLES = ["Nairobi is the capital of Kenya.", "The Great Wall of China is visible from the Moon with the naked eye.", "The COVID-19 pandemic began with a laboratory accident."];
const CLAIM_TYPES = Object.keys(CLAIM_TYPE_LABEL) as ClaimType[];

export default function InvestigatePage() {
  const router = useRouter();
  const textId = useId();
  const fileRef = useRef<HTMLInputElement>(null);
  const previewRef = useRef<string | null>(null);
  const [content, setContent] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [triage, setTriage] = useState<TriagePreview | null>(null);
  const [claims, setClaims] = useState<TriageClaim[]>([]);

  useEffect(() => {
    const prefill = new URLSearchParams(window.location.search).get("q");
    if (!prefill) return;
    const timer = window.setTimeout(() => setContent(prefill.slice(0, 20000)), 0);
    return () => window.clearTimeout(timer);
  }, []);
  useEffect(() => () => { if (previewRef.current) URL.revokeObjectURL(previewRef.current); }, []);

  function chooseFile(next: File | null) {
    if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    const safe = next && MEDIA_TYPES.includes(next.type) ? next : null;
    previewRef.current = safe ? URL.createObjectURL(safe) : null;
    setPreviewUrl(previewRef.current ?? "");
    setFile(safe);
    if (next && !safe) setError("Please choose a JPEG, PNG or WebP image, or an MP4 or WebM video.");
    else setError("");
    if (!safe && fileRef.current) fileRef.current.value = "";
  }

  function onDrop(event: DragEvent<HTMLFormElement>) {
    event.preventDefault(); setDragging(false);
    const dropped = event.dataTransfer.files?.[0];
    if (dropped) chooseFile(dropped);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true); setError("");
    try {
      if (file && !content.trim()) throw new Error("Add the claim or question that the image or video shows, so Agent 0 knows what to check.");
      const response = await fetch("/api/investigations/triage", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ input_type: file ? "TEXT" : inferInputType(content), content: content.trim() }),
      });
      if (!response.ok) throw new Error(await readError(response));
      const preview = (await response.json()) as TriagePreview;
      if (!preview.draft_id) { setError(preview.clarification_question || "Please add one specific factual claim so Agent 0 can check it."); return; }
      setTriage(preview); setClaims(preview.claims);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "We could not start this check. Please try again.");
    } finally { setBusy(false); }
  }

  async function confirm() {
    if (!triage?.draft_id || claims.length === 0) return;
    setBusy(true); setError("");
    try {
      let response: Response;
      if (file) {
        const form = new FormData();
        form.set("file", file); form.set("prompt", content.trim()); form.set("triage_id", triage.draft_id); form.set("claims_json", JSON.stringify(claims));
        response = await fetch("/api/investigations/media", { method: "POST", body: form });
      } else {
        response = await fetch(`/api/investigations/${triage.draft_id}/continue`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ claims }) });
      }
      if (!response.ok) throw new Error(await readError(response));
      const created = (await response.json()) as Investigation;
      router.push(`/investigations/${encodeURIComponent(created.id)}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "We could not continue. Please try again.");
      setBusy(false);
    }
  }

  const updateClaim = (index: number, patch: Partial<TriageClaim>) => setClaims((items) => items.map((item, i) => (i === index ? { ...item, ...patch } : item)));

  return (
    <WorkspaceShell>
      <WorkspacePage>
        {!triage ? (
          <>
            <PageHeader eyebrow="New check" title="What do you want to check?" description="Paste a claim or a public link, or add an image or short video with the question you have. You will review what Agent 0 understood before any research starts." />
            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
              <form onSubmit={submit} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={onDrop}
                onPaste={(event) => { const pasted = Array.from(event.clipboardData.items).find((item) => item.kind === "file" && MEDIA_TYPES.includes(item.type))?.getAsFile(); if (pasted) { event.preventDefault(); chooseFile(pasted); } }}
                className={cn("rounded-xl border bg-surface p-5 shadow-card transition-colors sm:p-6", dragging ? "border-brand-ink bg-brand-soft/40" : "border-line")}>
                <Label htmlFor={textId}>Claim, link or question</Label>
                <Textarea id={textId} rows={6} maxLength={20000} value={content} onChange={(event) => setContent(event.target.value)} placeholder="For example: The county announced that schools will stay closed tomorrow." aria-describedby={`${textId}-help`} />
                <p id={`${textId}-help`} className="mt-2 text-xs text-faint">Include who, what, where and when. A focused statement is easier to check.</p>

                <input ref={fileRef} type="file" className="sr-only" tabIndex={-1} aria-label="Choose an image or video" accept="image/jpeg,image/png,image/webp,video/mp4,video/webm,.jpg,.jpeg,.png,.webp,.mp4,.webm" onChange={(event) => chooseFile(event.target.files?.[0] ?? null)} />
                {file && (
                  <div className="mt-4 flex items-center gap-4 rounded-lg border border-line bg-bg p-3">
                    <div className="size-20 shrink-0 overflow-hidden rounded-md bg-subtle">
                      {previewUrl && (file.type.startsWith("video/") ? <video src={previewUrl} className="size-full object-cover" aria-label="Preview of the selected video" /> : <Image src={previewUrl} alt="Preview of the selected image" width={160} height={160} unoptimized className="size-full object-cover" />)}
                    </div>
                    <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{file.name || "Selected file"}</p><p className="text-xs text-faint">{file.type} · {formatBytes(file.size)}</p></div>
                    <Button type="button" variant="ghost" size="icon" aria-label="Remove file" onClick={() => chooseFile(null)}><X /></Button>
                  </div>
                )}

                <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <Button type="button" variant="outline" onClick={() => fileRef.current?.click()}><Paperclip /> Add image or video</Button>
                    <span className="hidden items-center gap-1.5 text-xs text-faint sm:inline-flex"><UploadCloud className="size-3.5" aria-hidden /> or drop a file here</span>
                  </div>
                  <Button type="submit" size="lg" disabled={busy || (!file && !content.trim())}>{busy ? <LoaderCircle className="animate-spin" /> : null}{busy ? "Reading your claim" : "Review claim"}{!busy && <ArrowRight />}</Button>
                </div>
                {error && <Alert tone="error" className="mt-4">{error}</Alert>}
                <p className="mt-4 text-xs text-faint">Video audio is not transcribed. This is a shared demo: use public information only.</p>
              </form>

              <aside className="grid content-start gap-4">
                <Card><CardBody>
                  <h2 className="text-sm font-semibold">What happens next</h2>
                  <ol className="mt-3 grid gap-3 text-sm text-muted">
                    {["Agent 0 picks out the claims it can check.", "You review and edit them. Nothing starts yet.", "You confirm, and it researches sources."].map((text, index) => <li key={text} className="flex gap-3"><span className="font-mono text-xs leading-5 text-faint">0{index + 1}</span>{text}</li>)}
                  </ol>
                </CardBody></Card>
                <Card><CardBody>
                  <h2 className="text-sm font-semibold">Try an example</h2>
                  <div className="mt-3 grid gap-2">{EXAMPLES.map((example) => <button key={example} type="button" onClick={() => { setContent(example); chooseFile(null); }} className="rounded-md border border-line px-3 py-2 text-left text-sm text-muted transition-colors hover:border-line-strong hover:bg-subtle hover:text-ink">{example}</button>)}</div>
                </CardBody></Card>
              </aside>
            </div>
          </>
        ) : (
          <>
            <PageHeader eyebrow="Step 2 of 2" title="Review what will be checked" description="Edit a claim, or split a long statement into separate claims. Research only starts when you confirm." />
            <div className="grid max-w-3xl gap-4">
              {claims.map((claim, index) => (
                <Card key={index}><CardBody className="grid gap-4">
                  <div className="flex items-center justify-between"><p className="text-sm font-semibold">Claim {index + 1}</p>{claims.length > 1 && <Button type="button" variant="ghost" size="sm" onClick={() => setClaims((items) => items.filter((_, i) => i !== index))}><Trash2 /> Remove</Button>}</div>
                  <div><Label htmlFor={`claim-${index}`}>What will be checked</Label><Textarea id={`claim-${index}`} rows={2} value={claim.text} onChange={(event) => updateClaim(index, { text: event.target.value })} className="min-h-20" /></div>
                  <div><Label htmlFor={`type-${index}`}>What kind of claim is it?</Label>
                    <Select id={`type-${index}`} value={claim.claim_type} onChange={(event) => { const claim_type = event.target.value as ClaimType; updateClaim(index, { claim_type, needs_deep_investigation: claim_type !== "SETTLED_FACT" }); }}>
                      {CLAIM_TYPES.map((type) => <option key={type} value={type}>{CLAIM_TYPE_LABEL[type]}</option>)}
                    </Select>
                  </div>
                </CardBody></Card>
              ))}
              <div><Button type="button" variant="outline" disabled={claims.length >= 3} onClick={() => setClaims((items) => [...items, { text: "", claim_type: "CHECKABLE_EVENT", needs_deep_investigation: true }])}><Plus /> Add another claim</Button>{claims.length >= 3 && <span className="ml-3 text-xs text-faint">Up to three claims per check.</span>}</div>
              {error && <Alert tone="error">{error}</Alert>}
              <div className="flex flex-wrap justify-between gap-3 border-t border-line pt-5">
                <Button type="button" variant="ghost" onClick={() => { setTriage(null); setError(""); }}>Back and edit</Button>
                <Button type="button" size="lg" disabled={busy || claims.some((claim) => claim.text.trim().length < 5)} onClick={() => void confirm()}>{busy ? <LoaderCircle className="animate-spin" /> : null}{busy ? "Starting" : "Confirm and start checking"}{!busy && <ArrowRight />}</Button>
              </div>
            </div>
          </>
        )}
      </WorkspacePage>
    </WorkspaceShell>
  );
}
