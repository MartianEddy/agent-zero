import Image from "next/image";
import { useState } from "react";
import { aiDeclarationCopy, provenancePresentation, safeEvidenceText, technicalMetadata, visualObservations } from "@/app/investigate/presentation.mjs";
import type { Investigation } from "@/app/investigate/types";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody } from "@/components/ui/card";
import { formatBytes } from "@/lib/api";
import { EvidenceCard } from "./EvidenceTab";
import type { CaseModel } from "./model";

export function MediaTab({ investigation, model }: { investigation: Investigation; model: CaseModel }) {
  const [previewFailed, setPreviewFailed] = useState(false);
  const { originalImage, originalVideo, provenance, mediaEvidence, finished } = model;
  const metadata = mediaEvidence.filter((item) => item.method === "MEDIA_TECHNICAL_METADATA" || item.method === "MEDIA_METADATA");
  const visual = mediaEvidence.filter((item) => item.method === "MEDIA_VISUAL_OBSERVATION");
  const prov = provenance ? provenancePresentation(provenance.status) : null;

  return (
    <div className="grid gap-5">
      {originalImage && (
        <Card><CardBody className="grid gap-5 sm:grid-cols-[minmax(0,320px)_1fr]">
          <div className="grid min-h-48 place-items-center overflow-hidden rounded-lg bg-subtle">
            {!finished ? <p className="p-4 text-sm text-muted">Preparing a safe preview.</p>
              : previewFailed ? <p className="p-4 text-sm text-muted">A safe preview is not available.</p>
              : <Image src={`/api/investigations/${investigation.id}/media-preview`} alt="Safe preview of the submitted image, with hidden file data removed" width={960} height={640} unoptimized onError={() => setPreviewFailed(true)} className="h-auto w-full" />}
          </div>
          <div>
            <h2 className="text-lg font-semibold">Image submitted</h2>
            <p className="mt-1 text-sm text-muted">{originalImage.mime_type} · {formatBytes(originalImage.size_bytes)}</p>
            <p className="mt-3 text-sm leading-6 text-muted">The preview is a cleaned copy. Hidden file data has been removed.</p>
          </div>
        </CardBody></Card>
      )}
      {originalVideo && (
        <Card><CardBody>
          <h2 className="text-lg font-semibold">Video submitted</h2>
          <p className="mt-1 text-sm text-muted">{originalVideo.mime_type} · {formatBytes(originalVideo.size_bytes)}</p>
          <p className="mt-3 text-sm leading-6 text-muted">Agent 0 looks at up to four frames from videos under 90 seconds. Audio is not transcribed, so spoken claims are not checked.</p>
        </CardBody></Card>
      )}
      {model.mediaNotice && <Alert tone="warn">{model.mediaNotice}</Alert>}

      {originalImage && (
        <div className="grid gap-4 lg:grid-cols-3">
          <Card><CardBody>
            <h3 className="font-semibold">Origin and history</h3>
            {prov && provenance ? <>
              <Badge className="mt-2">{prov.label as string}</Badge>
              <p className="mt-3 text-sm leading-6 text-muted">{prov.explanation as string}</p>
              {(aiDeclarationCopy(provenance.ai_disclosures) as string) && <p className="mt-2 text-sm leading-6 text-muted">{aiDeclarationCopy(provenance.ai_disclosures) as string}</p>}
              <p className="mt-2 text-xs leading-5 text-faint">{prov.limitation as string} Missing credentials do not mean an image is fake.</p>
            </> : <p className="mt-2 text-sm text-muted">{finished ? "No origin information is available." : "Checking origin information."}</p>}
          </CardBody></Card>
          <Card><CardBody>
            <h3 className="font-semibold">File details</h3>
            {metadata.length ? metadata.map((item) => { const fields = technicalMetadata(item.content) as [string, string][]; return fields.length ? <dl key={item.id} className="mt-3 grid gap-2 text-sm">{fields.map(([label, value]) => <div key={label}><dt className="text-xs text-faint">{label}</dt><dd className="text-ink-soft">{value}</dd></div>)}</dl> : <p key={item.id} className="mt-2 text-sm text-muted">Technical details were checked.</p>; }) : <p className="mt-2 text-sm text-muted">{finished ? "No useful file details are available." : "Reviewing file details."}</p>}
            <p className="mt-3 text-xs leading-5 text-faint">File details can be edited, so they cannot prove where or when an image was made.</p>
          </CardBody></Card>
          <Card><CardBody>
            <h3 className="font-semibold">What Agent 0 can see</h3>
            {visual.length ? <ul className="mt-3 grid gap-2 text-sm text-ink-soft">{visual.flatMap((item) => visualObservations(item.content) as { observation: string }[]).map((o, i) => <li key={i}>{safeEvidenceText(o.observation)}</li>)}</ul> : <p className="mt-2 text-sm text-muted">{model.mediaNotice ? "Visual review did not finish." : finished ? "No visual notes were recorded." : "Visual review is in progress."}</p>}
            <p className="mt-3 text-xs leading-5 text-faint">These are observations, not forensic proof. How an image looks cannot show whether it was made or changed by AI.</p>
          </CardBody></Card>
        </div>
      )}
      {originalVideo && <div className="grid gap-3">{mediaEvidence.length ? mediaEvidence.map((item) => <EvidenceCard key={item.id} item={item} relationship={item.claim_links[0]?.relationship} />) : <p className="text-sm text-muted">{finished ? "No video observations were recorded." : "Video observations are still being prepared."}</p>}</div>}
    </div>
  );
}
