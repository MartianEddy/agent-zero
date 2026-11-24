"use client";

import { useRouter } from "next/navigation";
import { useId, useState, type FormEvent } from "react";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/field";
import { cn } from "@/lib/utils";

const EXAMPLES = [
  "Nairobi is the capital of Kenya.",
  "The Great Wall of China is visible from the Moon with the naked eye.",
  "Schools in Nyeri County will remain closed tomorrow.",
];

export function QuickCheck({ className, autoFocus = false }: { className?: string; autoFocus?: boolean }) {
  const router = useRouter();
  const id = useId();
  const [text, setText] = useState("");

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = text.trim();
    router.push(value ? `/investigate?q=${encodeURIComponent(value)}` : "/investigate");
  }

  return (
    <form onSubmit={submit} className={cn("rounded-xl border border-line bg-surface p-4 shadow-card", className)}>
      <label htmlFor={id} className="mb-2 block text-sm font-semibold text-ink">What would you like to check?</label>
      <Textarea id={id} rows={3} maxLength={20000} autoFocus={autoFocus} value={text} onChange={(event) => setText(event.target.value)} placeholder="Paste a claim, a link, or ask a question" />
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-faint">You will see what will be checked before any research starts.</p>
        <Button type="submit">Review claim <ArrowRight /></Button>
      </div>
      <div className="mt-4 border-t border-line pt-3">
        <p className="mb-2 text-xs font-medium text-faint">Try an example</p>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map((example) => (
            <button key={example} type="button" onClick={() => setText(example)} className="rounded-full border border-line px-3 py-1.5 text-left text-xs text-muted transition-colors hover:border-line-strong hover:bg-subtle hover:text-ink">{example}</button>
          ))}
        </div>
      </div>
    </form>
  );
}
