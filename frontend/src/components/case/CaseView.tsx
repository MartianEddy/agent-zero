"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Download, Link2, LoaderCircle, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { relationshipPresentation, safeEvidenceText } from "@/app/investigate/presentation.mjs";
import { PageHeader, WorkspacePage, WorkspaceShell } from "@/components/workspace/WorkspaceShell";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useCase } from "@/lib/use-case";
import { BriefTab } from "./BriefTab";
import { ClaimResult } from "./ClaimResult";
import { EvidenceTab, type EvidenceFilter } from "./EvidenceTab";
import { MediaTab } from "./MediaTab";
import { buildCaseModel, citedEvidence } from "./model";
import { ProgressCard } from "./ProgressCard";

export function CaseView({ id }: { id: string }) {
  const { investigation, results, lastChecked, error, loading, retry } = useCase(id);
  const [tab, setTab] = useState("summary");
  const [filter, setFilter] = useState<EvidenceFilter>("ALL");
  const [focus, setFocus] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);

  const model = useMemo(() => (investigation ? buildCaseModel(investigation, results) : null), [investigation, results]);

  useEffect(() => {
    if (!focus || tab !== "evidence") return;
    const timer = window.setTimeout(() => {
      const element = document.getElementById(`evidence-${focus}`);
      element?.scrollIntoView({ behavior: "smooth", block: "center" });
      element?.focus?.({ preventScroll: true });
      setFocus(null);
    }, 80);
    return () => window.clearTimeout(timer);
  }, [focus, tab]);

  function cite(evidenceId: string) { setFilter("ALL"); setTab("evidence"); setFocus(evidenceId); }

  async function copyLink() {
    try { await navigator.clipboard.writeText(window.location.href); toast.success("Link copied", { description: "Anyone on this shared demo can open it." }); }
    catch { toast.error("Could not copy the link", { description: "Copy it from the address bar instead." }); }
  }
  async function doRetry() {
    setRetrying(true);
    try { await retry(); toast.success("Trying again", { description: "Your saved claim is being checked again." }); }
    catch (reason) { toast.error("Could not retry", { description: reason instanceof Error ? reason.message : "Please try again." }); }
    finally { setRetrying(false); }
  }

  if (loading) return <WorkspaceShell><WorkspacePage><Skeleton className="mb-4 h-4 w-24" /><Skeleton className="mb-3 h-10 w-2/3" /><Skeleton className="mb-8 h-4 w-1/3" /><Skeleton className="h-64 w-full" /></WorkspacePage></WorkspaceShell>;

  if (!investigation || !model) {
    return (
      <WorkspaceShell><WorkspacePage>
        <Link href="/investigations" className="mb-6 inline-flex items-center gap-1.5 text-sm font-medium text-muted hover:text-ink"><ArrowLeft className="size-4" /> Cases</Link>
        <Card><CardBody className="py-12 text-center">
          <h1 className="text-xl font-semibold">We could not open this case</h1>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted">{error || "It may have been removed, or the link may be incorrect."}</p>
          <Button asChild className="mt-6"><Link href="/investigations">Back to cases</Link></Button>
        </CardBody></Card>
      </WorkspacePage></WorkspaceShell>
    );
  }

  const { finished, completed } = model;
  const stopped = investigation.status === "FAILED" || investigation.status === "NEEDS_REVIEW";
  const title = completed ? "What Agent 0 found" : stopped ? "This check stopped early" : investigation.status === "CANCELLED" ? "This check was cancelled" : "Checking now";
  const hasMedia = Boolean(model.originalImage || model.originalVideo);
  const keyEvidence = results ? model.claims.flatMap((claim) => { const f = results.findings.find((x) => x.claim_id === claim.id); return f ? citedEvidence(f, model.evidence).slice(0, 4) : []; }).slice(0, 4) : [];

  return (
    <WorkspaceShell>
      <WorkspacePage>
        <Link href="/investigations" className="mb-5 inline-flex items-center gap-1.5 text-sm font-medium text-muted hover:text-ink"><ArrowLeft className="size-4" aria-hidden /> Cases</Link>
        <PageHeader eyebrow={`Case ${investigation.reference}`} title={title}
          description={lastChecked ? `Last updated ${new Date(lastChecked).toLocaleTimeString()}` : undefined}
          actions={<>
            <Button variant="outline" size="sm" onClick={() => void copyLink()}><Link2 /> Copy link</Button>
            {results && <Button asChild variant="outline" size="sm"><a href={`/api/investigations/${investigation.id}/export`} download><Download /> Export</a></Button>}
            {results?.retry_allowed && <Button size="sm" variant="dark" disabled={retrying} onClick={() => void doRetry()}>{retrying ? <LoaderCircle className="animate-spin" /> : <RotateCcw />} Try again</Button>}
          </>} />

        {!finished && <ProgressCard investigation={investigation} results={results} />}
        {investigation.failure_reason && <Alert tone="warn" title="Agent 0 stopped before finishing" className="mb-6">{safeEvidenceText(investigation.failure_reason)} Review anything already gathered before drawing a conclusion.</Alert>}
        {error && <Alert tone="error" className="mb-6">{error}</Alert>}

        {results && (
          <Tabs value={tab} onValueChange={setTab}>
            <TabsList className="max-w-full overflow-x-auto">
              <TabsTrigger value="summary">Summary</TabsTrigger>
              <TabsTrigger value="evidence">Evidence{results.sources.length ? ` (${results.sources.length})` : ""}</TabsTrigger>
              {hasMedia && <TabsTrigger value="media">Media</TabsTrigger>}
              {finished && results.brief && <TabsTrigger value="brief">Brief</TabsTrigger>}
            </TabsList>

            <TabsContent value="summary" className="grid gap-6">
              {model.claims.length > 0 ? model.claims.map((claim) => (
                <ClaimResult key={claim.id} claim={claim} finding={results.findings.find((f) => f.claim_id === claim.id)} evidence={model.evidence} finished={finished} dateBasis={model.dateBasis} onCite={cite} />
              )) : (
                <Card><CardBody>
                  <h2 className="text-lg font-semibold">{hasMedia ? "Media review" : "Your request"}</h2>
                  <p className="mt-2 max-w-2xl leading-7 text-muted">{!finished ? "Agent 0 is looking at what you shared and working out what can be checked." : safeEvidenceText(results.brief?.summary ?? "A specific claim could not be identified. Share the exact statement, who or what it concerns, and any date or place.")}</p>
                </CardBody></Card>
              )}

              {model.claims.length > 0 && model.unretrieved > 0 && <Alert tone="info">{results.evidence_coverage.sources_retrieved === 0 ? "No source pages could be opened for this check, so no result here rests on source text." : `${model.unretrieved} source${model.unretrieved === 1 ? " was" : "s were"} found but not opened. They are leads only and are not counted as evidence.`}</Alert>}

              {keyEvidence.length > 0 && (
                <section aria-labelledby="key-title">
                  <h2 id="key-title" className="mb-3 text-lg font-semibold">The clearest signals</h2>
                  <div className="grid gap-3 sm:grid-cols-2">
                    {keyEvidence.map(({ item, relationship }) => (
                      <Card key={item.id} className="flex flex-col p-4">
                        <p className="text-xs font-semibold text-faint">{item.source ? safeEvidenceText(results.sources.find((s) => s.id === item.source?.id)?.publisher || "Source") : "Image evidence"}</p>
                        <p className="mt-1.5 flex-1 text-sm leading-6 text-ink-soft">{safeEvidenceText(item.content).slice(0, 280)}{item.content.length > 280 ? "..." : ""}</p>
                        <button type="button" onClick={() => cite(item.id)} className="mt-3 w-fit text-sm font-medium text-brand-ink hover:underline">{relationshipPresentation(relationship) as string}. See details</button>
                      </Card>
                    ))}
                  </div>
                </section>
              )}

              {model.claims.length > 0 && (
                <div className="grid gap-4 md:grid-cols-2">
                  <Card><CardBody>
                    <h2 className="font-semibold">What we still do not know</h2>
                    {model.unknowns.length ? <ul className="mt-3 grid list-disc gap-2 pl-5 text-sm leading-6 text-muted">{model.unknowns.map((item) => <li key={item}>{safeEvidenceText(item)}</li>)}</ul> : <p className="mt-2 text-sm text-muted">{finished ? "No further unknowns were recorded." : "Open questions appear when the review is complete."}</p>}
                  </CardBody></Card>
                  <Card><CardBody>
                    <h2 className="font-semibold">What you can do next</h2>
                    {model.nextSteps.length ? <ol className="mt-3 grid list-decimal gap-2 pl-5 text-sm leading-6 text-muted">{model.nextSteps.map((item) => <li key={item}>{item}</li>)}</ol> : <p className="mt-2 text-sm text-muted">{finished ? "Review the cited sources with an editor before publishing." : "Suggested next steps appear when the review is complete."}</p>}
                  </CardBody></Card>
                </div>
              )}
            </TabsContent>

            <TabsContent value="evidence"><EvidenceTab results={results} model={model} filter={filter} onFilter={setFilter} /></TabsContent>
            {hasMedia && <TabsContent value="media"><MediaTab investigation={investigation} model={model} /></TabsContent>}
            {finished && results.brief && <TabsContent value="brief"><BriefTab results={results} model={model} /></TabsContent>}
          </Tabs>
        )}
        {!results && !finished && <p className="text-sm text-muted">Results will appear here as soon as they are ready.</p>}
      </WorkspacePage>
    </WorkspaceShell>
  );
}
