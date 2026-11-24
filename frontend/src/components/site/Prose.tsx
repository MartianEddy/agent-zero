import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Prose({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn(
      "text-[15px] leading-7 text-muted sm:text-base sm:leading-8",
      "[&_h2]:mb-3 [&_h2]:mt-12 [&_h2]:scroll-mt-24 [&_h2]:text-2xl [&_h2]:font-semibold [&_h2]:text-ink [&_h2:first-child]:mt-0",
      "[&_h3]:mb-2 [&_h3]:mt-6 [&_h3]:text-base [&_h3]:font-semibold [&_h3]:text-ink",
      "[&_p]:mb-4 [&_ul]:mb-5 [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:mb-5 [&_ol]:list-decimal [&_ol]:pl-6 [&_li]:mb-2 [&_li]:pl-1",
      "[&_strong]:font-semibold [&_strong]:text-ink [&_a]:font-medium [&_a]:text-brand-ink [&_a]:underline [&_a]:underline-offset-4",
      className,
    )}>{children}</div>
  );
}

export function Note({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "warn" }) {
  return <div className={cn("my-6 rounded-lg border-l-4 px-5 py-4 text-sm leading-7", tone === "warn" ? "border-[#d6a93a] bg-[#fff9e8] text-[#6b5420]" : "border-brand-ink bg-brand-soft/60 text-ink-soft")}>{children}</div>;
}
