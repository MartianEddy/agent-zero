import type { Metadata, Viewport } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import { Toaster } from "@/components/ui/toaster";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Agent 0: check a claim before you share it", template: "%s | Agent 0" },
  description: "Paste a claim, link or image. Agent 0 finds the sources, compares what they say, and tells you plainly what holds up and what does not.",
};
export const viewport: Viewport = { themeColor: "#fafaf7", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body>
        <a href="#content" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-ink focus:px-4 focus:py-2 focus:text-white">Skip to content</a>
        {children}
        <Toaster />
      </body>
    </html>
  );
}
