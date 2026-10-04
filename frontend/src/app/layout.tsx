import type { Metadata } from "next";
import WhatsAppFloat from "@/components/WhatsAppFloat";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Agent 0 — Follow the evidence", template: "%s — Agent 0" },
  description: "Investigate questionable claims, links and images. See the available evidence, what remains uncertain, and what to check next.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}<WhatsAppFloat /></body></html>;
}
