import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold leading-none [&_svg]:size-3.5", {
  variants: {
    tone: {
      neutral: "bg-subtle text-muted",
      ok: "bg-ok-bg text-ok-fg",
      bad: "bg-bad-bg text-bad-fg",
      mixed: "bg-mixed-bg text-mixed-fg",
      unknown: "bg-unknown-bg text-unknown-fg",
      opinion: "bg-opinion-bg text-opinion-fg",
      info: "bg-info-bg text-info-fg",
    },
  },
  defaultVariants: { tone: "neutral" },
});

export type BadgeTone = NonNullable<VariantProps<typeof badgeVariants>["tone"]>;

export function Badge({ className, tone, ...props }: ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
