export function Arrow({ down = false }: { down?: boolean }) {
  return <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={down ? "M12 5v14M5 12l7 7 7-7" : "M5 12h14M13 6l6 6-6 6"} /></svg>;
}
