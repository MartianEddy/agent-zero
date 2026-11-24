import { Check, LoaderCircle } from "lucide-react";
import { progressStepForStage, stagePresentation } from "@/app/investigate/presentation.mjs";
import type { Investigation, Results } from "@/app/investigate/types";
import { Card, CardBody } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const STEPS = ["Understanding the claim", "Searching for sources", "Reading and comparing", "Writing the result"];

export function ProgressCard({ investigation, results }: { investigation: Investigation; results: Results | null }) {
  const active = progressStepForStage(investigation.current_stage) as number;
  return (
    <Card className="mb-6 border-info-fg/20 bg-info-bg/40">
      <CardBody>
        <div className="flex items-center gap-3" role="status" aria-live="polite">
          <LoaderCircle className="size-5 animate-spin text-info-fg" aria-hidden />
          <div><p className="font-semibold">{stagePresentation(investigation.current_stage, results) as string}</p><p className="text-sm text-muted">This usually takes a few minutes. You can leave this page and come back with your reference.</p></div>
        </div>
        <ol className="mt-5 grid gap-3 sm:grid-cols-4" aria-label="Progress">
          {STEPS.map((step, index) => {
            const state = index < active ? "done" : index === active ? "current" : "next";
            return (
              <li key={step} aria-current={state === "current" ? "step" : undefined} className="flex items-center gap-3 sm:flex-col sm:items-start sm:gap-2">
                <span className={cn("grid size-7 shrink-0 place-items-center rounded-full border text-xs font-semibold", state === "done" && "border-ok-fg bg-ok-fg text-white", state === "current" && "border-info-fg bg-surface text-info-fg", state === "next" && "border-line-strong bg-surface text-faint")}>
                  {state === "done" ? <Check className="size-3.5" aria-hidden /> : index + 1}
                </span>
                <span className={cn("text-sm", state === "next" ? "text-faint" : "font-medium text-ink")}>{step}</span>
              </li>
            );
          })}
        </ol>
      </CardBody>
    </Card>
  );
}
