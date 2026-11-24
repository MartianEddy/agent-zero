import type { ReactNode } from "react";
import { SiteFooter } from "./SiteFooter";
import { SiteHeader } from "./SiteHeader";

export function SitePage({ children }: { children: ReactNode }) {
  return <><SiteHeader /><main id="content">{children}</main><SiteFooter /></>;
}
