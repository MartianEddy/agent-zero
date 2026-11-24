"use client";

import { useParams } from "next/navigation";
import { CaseView } from "@/components/case/CaseView";

export default function CasePage() {
  const params = useParams<{ id: string }>();
  return <CaseView id={params.id} />;
}
