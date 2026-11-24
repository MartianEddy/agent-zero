"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId, useMemo, useState, type FormEvent } from "react";
import { ArrowRight, ArrowUpRight, Paperclip, Smartphone } from "lucide-react";
import { CaseRow } from "@/components/workspace/CaseRow";
import { PageHeader, WorkspacePage, WorkspaceShell } from "@/components/workspace/WorkspaceShell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/skeleton";
import { ACTIVE_STATUSES } from "@/lib/api";
import { useHistory } from "@/lib/use-history";
import { VERDICT_ORDER, verdictView } from "@/lib/verdict";
import { WHATSAPP_CONTACT_URL } from "@/lib/contact";

export default function DashboardPage() {
  const router = useRouter();
  const id = useId();
  const { items, error, loading } = useHistory();
  const [claim, setClaim] = useState("");

  const stats = useMemo(() => {
    const list = items ?? [];
    return [
      { label: "Checks", value: list.length },
      { label: "Finished", value: list.filter((item) => item.status === "COMPLETE").length },
      { label: "In progress", value: list.filter((item) => ACTIVE_STATUSES.has(item.status)).length },
      { label: "Need attention", value: list.filter((item) => item.status === "FAILED" || item.status === "NEEDS_REVIEW").length },
    ];
  }, [items]);

  function start(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = claim.trim();
    router.push(text ? `/investigate?q=${encodeURIComponent(text)}` : "/investigate");
  }

  return (
    <WorkspaceShell>
      <WorkspacePage>
        <PageHeader eyebrow="Overview" title="What would you like to check today?" />

        <form onSubmit={start} className="mb-8 max-w-3xl rounded-xl border border-line bg-surface p-4 shadow-card focus-within:border-brand-ink focus-within:ring-4 focus-within:ring-brand/30">
          <label htmlFor={id} className="sr-only">Claim, link or question</label>
          <Textarea id={id} rows={2} maxLength={20000} value={claim} onChange={(event) => setClaim(event.target.value)} placeholder="Paste a claim, a link, or ask a question" className="border-0 px-1 shadow-none focus:ring-0" />
          <div className="mt-2 flex items-center justify-between gap-3">
            <Button asChild variant="ghost" size="sm"><Link href="/investigate"><Paperclip /> Add an image or video</Link></Button>
            <Button type="submit">Review claim <ArrowRight /></Button>
          </div>
        </form>

        <section aria-label="Your checks at a glance" className="mb-8 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {stats.map((stat) => (
            <Card key={stat.label} className="px-4 py-3.5">
              {loading ? <Skeleton className="h-8 w-10" /> : <p className="text-3xl font-semibold tracking-tight">{error ? "-" : stat.value}</p>}
              <p className="mt-0.5 text-xs text-muted">{stat.label}</p>
            </Card>
          ))}
        </section>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(260px,1fr)]">
          <Card className="overflow-hidden">
            <CardHeader className="pb-4"><CardTitle>Recent cases</CardTitle><Link href="/investigations" className="text-sm font-medium text-brand-ink hover:underline">View all</Link></CardHeader>
            <div className="divide-y divide-line border-t border-line">
              {loading && [0, 1, 2].map((key) => <div key={key} className="flex items-center gap-4 px-5 py-4"><Skeleton className="size-9" /><div className="flex-1 space-y-2"><Skeleton className="h-4 w-3/4" /><Skeleton className="h-3 w-1/3" /></div></div>)}
              {error && <p className="px-5 py-6 text-sm text-muted">Your cases could not be loaded right now. Please try again shortly.</p>}
              {items && items.length === 0 && <div className="px-5 py-10 text-center"><p className="font-medium">No checks yet</p><p className="mt-1 text-sm text-muted">Start your first check above.</p></div>}
              {items?.slice(0, 6).map((item) => <CaseRow key={item.id} item={item} />)}
            </div>
          </Card>

          <div className="grid content-start gap-6">
            <Card>
              <CardHeader><CardTitle>How to read a result</CardTitle><Link href="/methodology" className="text-sm font-medium text-brand-ink hover:underline">Details</Link></CardHeader>
              <CardBody>
                <ul className="grid gap-3.5">
                  {VERDICT_ORDER.map((status) => { const view = verdictView(status); const Icon = view.icon; return (
                    <li key={status}><Badge tone={view.tone}><Icon aria-hidden />{view.label}</Badge><p className="mt-1.5 text-xs leading-5 text-muted">{view.meaning}</p></li>
                  ); })}
                </ul>
              </CardBody>
            </Card>
            <Card className="border-brand-ink/20 bg-brand-soft/50">
              <CardBody>
                <Smartphone className="mb-3 size-5 text-brand-ink" aria-hidden />
                <h2 className="font-semibold">Prefer WhatsApp?</h2>
                <p className="mt-1.5 text-sm leading-6 text-muted">Send a claim, link or question and get a plain-language answer in chat.</p>
                <div className="mt-4 flex flex-wrap items-center gap-3">
                  <Button asChild size="sm" variant="dark"><a href={WHATSAPP_CONTACT_URL} target="_blank" rel="noopener noreferrer">Open WhatsApp <ArrowUpRight /></a></Button>
                  <Link href="/whatsapp" className="text-sm font-medium text-brand-ink hover:underline">How it works</Link>
                </div>
              </CardBody>
            </Card>
          </div>
        </div>
      </WorkspacePage>
    </WorkspaceShell>
  );
}
