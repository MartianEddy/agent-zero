"use client";

import { useEffect, useState } from "react";
import type { HistoryItem } from "@/lib/api";

export function useHistory() {
  const [items, setItems] = useState<HistoryItem[] | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let cancelled = false;
    fetch("/api/investigations/history", { cache: "no-store" })
      .then((response) => { if (!response.ok) throw new Error(); return response.json() as Promise<HistoryItem[]>; })
      .then((data) => { if (!cancelled) setItems(data); })
      .catch(() => { if (!cancelled) setError(true); });
    return () => { cancelled = true; };
  }, []);
  return { items, error, loading: items === null && !error };
}
