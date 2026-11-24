"use client";

import { useCallback, useEffect, useState } from "react";
import { ACTIVE_STATUSES, readError } from "@/lib/api";
import type { Investigation, Results } from "@/app/investigate/types";

export function useCase(id: string) {
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [results, setResults] = useState<Results | null>(null);
  const [lastChecked, setLastChecked] = useState<string>("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const [statusResponse, resultsResponse] = await Promise.all([
      fetch(`/api/investigations/${id}`, { cache: "no-store" }),
      fetch(`/api/investigations/${id}/results`, { cache: "no-store" }),
    ]);
    if (!statusResponse.ok) throw new Error(await readError(statusResponse));
    const current = (await statusResponse.json()) as Investigation;
    setInvestigation(current);
    setLastChecked(new Date().toISOString());
    if (resultsResponse.ok) setResults((await resultsResponse.json()) as Results);
    return current;
  }, [id]);

  useEffect(() => {
    let stopped = false;
    let timer: number | undefined;
    const tick = async (first: boolean) => {
      try {
        const current = await refresh();
        setError("");
        if (!ACTIVE_STATUSES.has(current.status)) return;
      } catch (reason) {
        if (first || !stopped) setError(reason instanceof Error ? reason.message : "This case could not be loaded.");
        if (first) return;
      } finally {
        if (first) setLoading(false);
      }
      if (!stopped) timer = window.setTimeout(() => void tick(false), 5000);
    };
    void tick(true);
    return () => { stopped = true; if (timer !== undefined) window.clearTimeout(timer); };
  }, [refresh]);

  const retry = useCallback(async () => {
    const response = await fetch(`/api/investigations/${id}`, { method: "POST" });
    if (!response.ok) throw new Error(await readError(response));
    setResults(null);
    await refresh();
  }, [id, refresh]);

  return { investigation, results, lastChecked, error, loading, refresh, retry };
}
