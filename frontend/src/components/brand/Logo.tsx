import Image from "next/image";
import { cn } from "@/lib/utils";

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn("relative inline-flex h-9 w-[110px] items-center justify-center overflow-hidden rounded-md border border-[#29312a] bg-[#0b0d0e] align-middle", className)}>
      <Image className="block h-[55px] w-[110px] max-w-none flex-none object-cover" src="/brand/agent-0-logo.png" alt="Agent 0" width={1774} height={887} priority />
    </span>
  );
}
