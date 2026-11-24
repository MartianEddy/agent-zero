import type { ComponentProps } from "react";
import { cn } from "@/lib/utils";

const base = "w-full rounded-md border border-line-strong bg-surface px-3.5 py-3 text-[15px] text-ink placeholder:text-faint transition-[border-color,box-shadow] duration-150 focus:border-brand-ink focus:outline-none focus:ring-4 focus:ring-brand/40 disabled:opacity-60";

export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn(base, "h-11 py-0", className)} {...props} />;
}
export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea className={cn(base, "min-h-28 resize-y leading-relaxed", className)} {...props} />;
}
export function Label({ className, ...props }: ComponentProps<"label">) {
  return <label className={cn("mb-1.5 block text-sm font-semibold text-ink", className)} {...props} />;
}
export function Select({ className, ...props }: ComponentProps<"select">) {
  return <select className={cn(base, "h-11 py-0", className)} {...props} />;
}
