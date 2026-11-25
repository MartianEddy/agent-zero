"use client";

import { useRef, type ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Subtle 3D tilt that follows the pointer. Plain CSS transforms, no WebGL.
 * Disabled for touch input and for people who prefer reduced motion.
 */
export function Tilt({ children, className, max = 7 }: { children: ReactNode; className?: string; max?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const frame = useRef(0);

  function move(event: React.PointerEvent<HTMLDivElement>) {
    if (event.pointerType !== "mouse" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width - 0.5;
    const y = (event.clientY - rect.top) / rect.height - 0.5;
    cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(() => {
      el.style.transform = `perspective(900px) rotateX(${(-y * max).toFixed(2)}deg) rotateY(${(x * max).toFixed(2)}deg) translateZ(0)`;
    });
  }
  function leave() {
    cancelAnimationFrame(frame.current);
    if (ref.current) ref.current.style.transform = "";
  }
  return <div ref={ref} onPointerMove={move} onPointerLeave={leave} className={cn("transition-transform duration-200 ease-out will-change-transform", className)}>{children}</div>;
}
