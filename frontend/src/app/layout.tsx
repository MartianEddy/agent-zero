import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Agent 0 — Assume nothing. Follow the evidence.", template: "%s — Agent 0" },
  description: "Investigate suspicious claims, media and documents against available evidence.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
