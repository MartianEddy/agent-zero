import { CircleAlert, Info, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

const tones = {
  info: { box: "border-info-fg/20 bg-info-bg text-info-fg", Icon: Info },
  warn: { box: "border-mixed-fg/25 bg-mixed-bg text-mixed-fg", Icon: TriangleAlert },
  error: { box: "border-bad-fg/25 bg-bad-bg text-bad-fg", Icon: CircleAlert },
} as const;

export function Alert({ tone = "info", title, children, className }: { tone?: keyof typeof tones; title?: string; children?: ReactNode; className?: string }) {
  const { box, Icon } = tones[tone];
  return (
    <div role={tone === "error" ? "alert" : "status"} className={cn("flex gap-3 rounded-lg border px-4 py-3 text-sm leading-6", box, className)}>
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="min-w-0">{title && <p className="font-semibold">{title}</p>}{children && <div className={cn(title && "mt-0.5", "opacity-95")}>{children}</div>}</div>
    </div>
  );
}
