type AgentMarkProps = { compact?: boolean };
export function AgentMark({ compact = false }: AgentMarkProps) {
  return <span className="agent-mark" aria-label="Agent 0">
    {!compact && <span className="agent-mark__word">AGENT</span>}
    <svg className="agent-mark__ring" viewBox="0 0 32 32" aria-hidden="true">
      <circle cx="16" cy="16" r="11.6" fill="none" stroke="currentColor" strokeWidth="3.1" strokeDasharray="14 5 11 5 14 24" transform="rotate(-90 16 16)" />
      <circle cx="16" cy="3.7" r="2.1" fill="var(--signal)" /><circle cx="27.6" cy="16" r="2.1" fill="var(--paper)" /><circle cx="16" cy="28.3" r="2.1" fill="var(--signal)" />
    </svg>
  </span>;
}
