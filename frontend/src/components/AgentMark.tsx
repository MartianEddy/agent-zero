import Image from "next/image";

export function AgentMark({ compact = false }: { compact?: boolean }) {
  return <span className={`agent-mark${compact ? " agent-mark--compact" : ""}`}>
    <Image className="agent-mark__image" src="/brand/agent-0-logo.png" alt="Agent 0" width={1774} height={887} priority />
  </span>;
}
