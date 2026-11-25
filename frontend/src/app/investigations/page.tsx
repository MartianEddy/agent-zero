"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState, type FormEvent } from "react";
import { LoaderCircle, Plus, Search } from "lucide-react";
import { statusPresentation } from "@/app/investigate/presentation.mjs";
import type { FindingStatus, Investigation } from "@/app/investigate/types";
import { CaseRow } from "@/components/workspace/CaseRow";
import { PageHeader, WorkspacePage, WorkspaceShell } from "@/components/workspace/WorkspaceShell";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { useHistory } from "@/lib/use-history";
import { cn } from "@/lib/utils";

type Filter = "ALL" | FindingStatus;
const FILTERS: Filter[] = ["ALL", "SUPPORTED", "CONTRADICTED", "PARTLY_TRUE", "INSUFFICIENT_EVIDENCE", "NOT_VERIFIABLE"];

export default function CasesPage() {
  const router = useRouter();
  const { items, error, loading } = useHistory();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("ALL");
  const [reference, setReference] = useState("");
  const [lookupBusy, setLookupBusy] = useState(false);
  const [lookupError, setLookupError] = useState("");

  const filtered = useMemo(() => (items ?? []).filter((item) =>
    (filter === "ALL" || item.finding_status === filter) && `${item.title} ${item.reference}`.toLowerCase().includes(query.trim().toLowerCase()),
  ), [items, query, filter]);

  async function openByReference(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLookupBusy(true); setLookupError("");
    try {
      const response = await fetch(`/api/investigations/reference?reference=${encodeURIComponent(reference.trim())}`, { cache: "no-store" });
      if (!response.ok) {
        const payload = await response.json().catch(() => null) as { detail?: string } | null;
        throw new Error(typeof payload?.detail === "string" ? payload.detail : "We could not find a case with that reference.");
      }
      const found = await response.json() as Investigation;
      router.push(`/investigations/${encodeURIComponent(found.id)}`);
    } catch (reason) {
      setLookupError(reason instanceof Error ? reason.message : "We could not find that case. Please try again.");
      setLookupBusy(false);
    }
  }

  return (
    <WorkspaceShell>
      <WorkspacePage>
        <PageHeader eyebrow="Case history" title="Cases" description="Reopen any claim, link, image or video that was checked in this demo."
          actions={<Button asChild><Link href="/investigate"><Plus /> New check</Link></Button>} />

        <div className="mb-6 grid gap-4 lg:grid-cols-[1fr_auto] lg:items-end">
          <div>
            <Label htmlFor="case-search">Search cases</Label>
            <div className="relative"><Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-faint" aria-hidden /><Input id="case-search" type="search" className="pl-10" placeholder="Search by claim or reference" value={query} onChange={(event) => setQuery(event.target.value)} /></div>
          </div>
          <form onSubmit={openByReference} className="flex items-end gap-2">
            <div><Label htmlFor="case-reference">Open by reference</Label><Input id="case-reference" className="w-40 font-mono uppercase" placeholder="AZ-7KQ2F" value={reference} onChange={(event) => setReference(event.target.value.toUpperCase())} autoComplete="off" required /></div>
            <Button type="submit" variant="outline" disabled={lookupBusy}>{lookupBusy ? <LoaderCircle className="animate-spin" /> : null}Open</Button>
          </form>
        </div>
        {lookupError && <Alert tone="error" className="mb-4">{lookupError}</Alert>}

        <div role="group" aria-label="Filter by result" className="mb-5 flex flex-wrap gap-2">
          {FILTERS.map((item) => (
            <button key={item} type="button" aria-pressed={filter === item} onClick={() => setFilter(item)}
              className={cn("h-9 rounded-full border border-line-strong bg-surface px-3.5 text-sm font-medium text-muted transition-colors hover:bg-subtle", filter === item && "border-ink bg-ink text-white hover:bg-ink")}>
              {item === "ALL" ? "All results" : statusPresentation(item).label}
            </button>
          ))}
        </div>

        <Card className="overflow-hidden">
          {loading && <div className="divide-y divide-line">{[0, 1, 2, 3].map((key) => <div key={key} className="flex items-center gap-4 px-5 py-4"><Skeleton className="size-9" /><div className="flex-1 space-y-2"><Skeleton className="h-4 w-2/3" /><Skeleton className="h-3 w-1/4" /></div></div>)}</div>}
          {error && <div className="px-5 py-10 text-center"><p className="font-medium">Cases could not be loaded</p><p className="mt-1 text-sm text-muted">Please check your connection and try again.</p><Button className="mt-4" variant="outline" onClick={() => window.location.reload()}>Try again</Button></div>}
          {items && items.length === 0 && <div className="px-5 py-14 text-center"><p className="font-medium">No checks yet</p><p className="mt-1 text-sm text-muted">Check a claim, link or image to get started.</p><Button asChild className="mt-4"><Link href="/investigate">Start a check</Link></Button></div>}
          {items && items.length > 0 && filtered.length === 0 && <div className="px-5 py-12 text-center"><p className="font-medium">No matching cases</p><p className="mt-1 text-sm text-muted">Try a different search or filter.</p></div>}
          {filtered.length > 0 && <div className="divide-y divide-line">{filtered.map((item) => <CaseRow key={item.id} item={item} />)}</div>}
        </Card>
        {items?.length === 50 && <p className="mt-3 text-xs text-faint">Showing the latest 50 cases. Use a reference to open an older one.</p>}
      </WorkspacePage>
    </WorkspaceShell>
  );
}
