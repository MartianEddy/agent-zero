"use client";

import { Accordion as A } from "radix-ui";
import { ChevronDown } from "lucide-react";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export const Accordion = A.Root;

export function AccordionItem({ className, ...props }: ComponentProps<typeof A.Item>) {
  return <A.Item className={cn("rounded-lg border border-line bg-surface data-[state=open]:shadow-card", className)} {...props} />;
}
export function AccordionTrigger({ className, children, ...props }: ComponentProps<typeof A.Trigger>) {
  return <A.Header className="flex"><A.Trigger className={cn("group flex min-h-14 flex-1 items-center justify-between gap-4 rounded-lg px-5 text-left text-[15px] font-semibold text-ink", className)} {...props}>{children}<ChevronDown aria-hidden className="size-4 shrink-0 text-faint transition-transform duration-200 group-data-[state=open]:rotate-180" /></A.Trigger></A.Header>;
}
export function AccordionContent({ className, children, ...props }: ComponentProps<typeof A.Content>) {
  return <A.Content className="overflow-hidden text-sm leading-7 text-muted data-[state=closed]:animate-[fade-in_120ms_reverse] data-[state=open]:animate-fade-in" {...props}><div className={cn("px-5 pb-5", className)}>{children}</div></A.Content>;
}
