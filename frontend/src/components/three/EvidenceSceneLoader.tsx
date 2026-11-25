"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

// The 3D bundle (three.js) loads only when the hero is on screen and the device can run it.
const EvidenceScene = dynamic(() => import("./EvidenceScene"), { ssr: false });

function canUseWebGL() {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

/** Pure-CSS stand-in used while loading, when WebGL is unavailable, and for reduced motion. */
function StaticConstellation() {
  return (
    <div className="absolute inset-0 grid place-items-center" aria-hidden>
      <div className="relative size-[min(78%,360px)]">
        <div className="absolute inset-0 rounded-full border border-brand/25" />
        <div className="absolute inset-[14%] rounded-full border border-teal/30" />
        <div className="absolute inset-[30%] rounded-full bg-[radial-gradient(circle_at_35%_30%,#4dbd1f,#0d1612_70%)] shadow-glow" />
        {[["8%", "28%", "bg-brand"], ["80%", "20%", "bg-sky"], ["70%", "78%", "bg-brand"], ["18%", "74%", "bg-coral"]].map(([left, top, color]) => (
          <span key={`${left}${top}`} className={cn("absolute size-3 rounded-full", color)} style={{ left, top }} />
        ))}
      </div>
    </div>
  );
}

export function EvidenceSceneLoader({ className }: { className?: string }) {
  const host = useRef<HTMLDivElement>(null);
  const [enabled, setEnabled] = useState(false);
  const [visible, setVisible] = useState(false);
  const [everVisible, setEverVisible] = useState(false);

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const saveData = Boolean((navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData);
    const timer = window.setTimeout(() => setEnabled(!reduce && !saveData && canUseWebGL()), 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    const observer = new IntersectionObserver(([entry]) => {
      setVisible(entry.isIntersecting);
      if (entry.isIntersecting) setEverVisible(true);
    }, { rootMargin: "80px" });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={host} data-scene={enabled ? (everVisible ? "live" : "ready") : "static"} className={cn("relative", className)} aria-hidden>
      {!(enabled && everVisible) && <StaticConstellation />}
      {enabled && everVisible && <div className="absolute inset-0 animate-fade-in [mask-image:radial-gradient(closest-side,#000_62%,transparent_100%)]"><EvidenceScene paused={!visible} /></div>}
    </div>
  );
}
