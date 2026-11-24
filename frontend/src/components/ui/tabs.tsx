"use client";

import { Tabs as T } from "radix-ui";
import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

export const Tabs = T.Root;
export function TabsList({ className, ...props }: ComponentProps<typeof T.List>) {
  return <T.List className={cn("inline-flex gap-1 rounded-lg bg-subtle p-1", className)} {...props} />;
}
export function TabsTrigger({ className, ...props }: ComponentProps<typeof T.Trigger>) {
  return <T.Trigger className={cn("inline-flex h-9 items-center gap-2 rounded-md px-3.5 text-sm font-semibold text-muted transition-colors hover:text-ink data-[state=active]:bg-surface data-[state=active]:text-ink data-[state=active]:shadow-sm [&_svg]:size-4", className)} {...props} />;
}
export function TabsContent({ className, ...props }: ComponentProps<typeof T.Content>) {
  return <T.Content className={cn("mt-5 animate-fade-in focus-visible:outline-none", className)} {...props} />;
}
