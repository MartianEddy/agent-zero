const STATUS_COPY = {
  SUPPORTED: {
    icon: "✓",
    label: "Supported by evidence",
    explanation: "Available reliable evidence supports this claim.",
  },
  CONTRADICTED: {
    icon: "×",
    label: "Contradicted by evidence",
    explanation: "Reliable evidence conflicts with this claim.",
  },
  UNVERIFIED: {
    icon: "○",
    label: "Not verified",
    explanation: "The evidence reviewed did not establish whether this claim is accurate.",
  },
  INCONCLUSIVE: {
    icon: "?",
    label: "Inconclusive",
    explanation: "Retrieved evidence conflicts or cannot be reconciled into a clear conclusion.",
  },
  MISLEADING_CONTEXT: {
    icon: "!",
    label: "Misleading context",
    explanation: "The evidence indicates that context may be misleading.",
  },
  ALTERED_MEDIA: {
    icon: "!",
    label: "Altered media",
    explanation: "Evidence indicates that the media may have been altered.",
  },
  OUTDATED_CONTEXT: {
    icon: "↻",
    label: "Outdated context",
    explanation: "The evidence indicates that the context may be outdated.",
  },
};

const PROVENANCE_COPY = {
  VALID: {
    label: "Content credentials found",
    explanation: "Attached content credentials were found and checked on the uploaded file.",
    limitation: "These details do not establish whether the event shown or the claim is true.",
  },
  NOT_PRESENT: {
    label: "No content credentials found",
    explanation: "No supported origin credentials were attached to this image.",
    limitation: "Their absence does not mean an image is fake or manipulated.",
  },
  INVALID: {
    label: "Credentials could not be checked",
    explanation: "Content credentials were present, but Agent 0 could not confirm their details.",
    limitation: "Failed validation does not establish that the image or depicted event is false.",
  },
  INDETERMINATE: {
    label: "Couldn’t confirm the credentials",
    explanation: "Some details about these content credentials could not be confirmed.",
    limitation: "An incomplete validation does not establish authenticity or manipulation.",
  },
  UNSUPPORTED: {
    label: "Couldn’t read these credentials",
    explanation: "Agent 0 could not read this credential format.",
    limitation: "Unsupported credentials do not establish authenticity or manipulation.",
  },
  ERROR: {
    label: "Image origin check unavailable",
    explanation: "Agent 0 could not complete the image origin check.",
    limitation: "No authenticity conclusion was drawn.",
  },
};

const STAGE_COPY = {
  RECEIVED: "Understanding what you shared",
  PROCESSING: "Preparing the investigation",
  ANALYZING: "Examining what you shared",
  RESEARCHING: "Looking for reliable sources",
  CORROBORATING: "Comparing what the evidence says",
  GENERATING_BRIEF: "Preparing the result",
  COMPLETE: "Investigation complete",
  NEEDS_REVIEW: "Part of the investigation needs review",
  FAILED: "Part of the investigation could not be completed",
  CANCELLED: "Investigation stopped",
};

const PROGRESS_STEP_BY_STAGE = {
  RECEIVED: 0,
  PROCESSING: 0,
  ANALYZING: 0,
  RESEARCHING: 1,
  CORROBORATING: 2,
  GENERATING_BRIEF: 3,
};

const PRIVATE_TEXT_PATTERNS = [
  /-----BEGIN [^-]+-----[\s\S]*?-----END [^-]+-----/gi,
  /(?:https?:\/\/|www\.)\S+/gi,
  /[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}/g,
  /(?:private|private-derived)\/[\w./-]+/gi,
  /\/(?:home|tmp|var|mnt|Users|Volumes)\/[^\s"'<>]+/gi,
  /\b[A-Z]:\\(?:Users|Temp|Windows)\\[^\s"'<>]+/gi,
  /(?<!\w)[+-]?\d{1,3}\.\d{4,}\s*[,/]\s*[+-]?\d{1,3}\.\d{4,}(?!\w)/g,
];

/** @param {string} value */
export function safeEvidenceText(value) {
  return PRIVATE_TEXT_PATTERNS.reduce((text, pattern) => text.replace(pattern, "[redacted]"), value);
}

/** @param {string} status */
export function statusPresentation(status) {
  return STATUS_COPY[status] ?? {
    icon: "?",
    label: "Under review",
    explanation: "Review the linked evidence and limitations before drawing a conclusion.",
  };
}

/** @param {string} content */
export function inferInputType(content) {
  return /^https?:\/\//i.test(content.trim()) ? "URL" : "TEXT";
}

/** @param {string | null | undefined} status */
export function provenancePresentation(status) {
  return PROVENANCE_COPY[status] ?? PROVENANCE_COPY.ERROR;
}

/** @param {string[]} declarations */
export function aiDeclarationCopy(declarations) {
  return declarations.some((item) => item === "GENERATIVE_AI_CREATION_DECLARED" || item === "GENERATIVE_AI_CONTRIBUTION_DECLARED")
    ? "AI use was declared. The image’s attached origin information states that generative AI was used during its creation or editing."
    : null;
}

/** @param {import('./types').Finding} finding @param {import('./types').Evidence[]} evidence */
export function findingEvidenceReferences(finding, evidence) {
  return finding.evidence_ids.flatMap((id) => {
    const item = evidence.find((candidate) => candidate.id === id);
    return item ? [item] : [];
  });
}

/** @param {import('./types').Results} results @param {boolean} reviewComplete */
export function unknownsFromResults(results, reviewComplete = true) {
  if (!reviewComplete) return [];
  const unknowns = [];
  if (results.claims.length === 0) {
    unknowns.push("No verifiable claim was extracted from the submitted request.");
  }
  if (results.evidence_coverage.claims_without_linked_evidence > 0) {
    unknowns.push("No retrieved evidence excerpt is linked to one or more claims, so those claims could not be assessed from source content.");
  }
  if (results.sources.length > 0 && results.evidence_coverage.sources_retrieved === 0) {
    unknowns.push(`${results.sources.length} source candidate${results.sources.length === 1 ? " was" : "s were"} found, but no page content could be retrieved. Candidate titles are leads, not evidence.`);
  }
  const provenance = results.evidence.find((item) => item.provenance)?.provenance;
  if (provenance?.status === "NOT_PRESENT") {
    unknowns.push("No supported Content Credentials were present; this does not indicate synthetic or manipulated media.");
  }
  if (results.findings.some((item) => item.status === "INCONCLUSIVE")) {
    unknowns.push("Retrieved evidence conflicts or leaves a material question unresolved.");
  }
  if (unknowns.length === 0 && results.findings.length > 0) {
    unknowns.push("No additional unknowns were recorded in this brief.");
  }
  return [...new Set(unknowns)];
}

/** @param {import('./types').Results} results @param {boolean} reviewComplete */
export function recommendedNextSteps(results, reviewComplete = true) {
  if (!reviewComplete) return [];
  if (results.claims.length === 0) {
    const steps = ["Add a specific, verifiable claim or question to investigate."];
    if (results.media_assets?.some((asset) => asset.media_type === "IMAGE" && asset.role.toUpperCase() === "ORIGINAL")) {
      steps.push("Review any available Content Credentials for an attributable AI declaration.");
      steps.push("Seek independent source evidence about the image's origin.");
    } else {
      steps.push("Review the submitted material and identify details that can be checked independently.");
    }
    return steps;
  }
  if (results.findings.every((item) => item.status === "SUPPORTED" || item.status === "CONTRADICTED") && results.evidence.length > 0) {
    return [];
  }
  const steps = [];
  if (results.sources.length === 0 || results.evidence_coverage.sources_retrieved === 0) {
    steps.push("Open a source candidate and provide an accessible primary source or article with the relevant passage.");
  }
  steps.push("Check for an official statement and compare it with an independent source.");
  if (results.media_assets?.some((asset) => asset.media_type === "IMAGE" && asset.role.toUpperCase() === "ORIGINAL")) {
    steps.push("Locate the original upload and consider an external reverse-image search; Agent 0 did not perform one.");
  }
  return steps;
}

/** @param {import('./types').Results} results */
export function visualAnalysisNotice(results) {
  const failed = results.usage_summary?.limitations.some((item) => item.toLowerCase().includes("visual interpretation was unavailable"));
  return failed
    ? "We couldn’t examine what is visible in the image, but origin details, file information, and source information remain available."
    : null;
}

/** @param {string} stage */
export function stagePresentation(stage) {
  return STAGE_COPY[stage] ?? "Preparing investigation";
}

/** @param {string} stage */
export function progressStepForStage(stage) {
  return PROGRESS_STEP_BY_STAGE[stage] ?? 0;
}

/** @param {string} relationship */
export function relationshipPresentation(relationship) {
  const labels = {
    SUPPORTS: "Supports this",
    CONTRADICTS: "Challenges this",
    CONTEXTUALIZES: "Adds context",
    MENTIONS: "Mentions",
    UNKNOWN: "Not yet assessed",
    DERIVES_FROM: "Shares an origin with",
    DUPLICATES: "Similar reporting",
    UNRELATED: "Unrelated",
    CITES: "Cites",
  };
  return labels[relationship] ?? "Context";
}

/** @param {string} content */
export function technicalMetadata(content) {
  const marker = "Safe decoded fields: ";
  const start = content.indexOf(marker);
  if (start < 0) return [];
  const end = content.indexOf(". Analyzed", start);
  if (end < 0) return [];
  try {
    const data = JSON.parse(content.slice(start + marker.length, end));
    return [
      ["Format", data.format],
      ["Dimensions", Number.isFinite(data.width) && Number.isFinite(data.height) ? `${data.width} × ${data.height}` : null],
      ["Transparency", data.alpha_present === true ? "Present" : data.alpha_present === false ? "Not detected" : null],
      ["Orientation metadata", data.orientation_present === true ? "Present" : data.orientation_present === false ? "Not detected" : null],
    ].filter((item) => item[1]);
  } catch {
    return [];
  }
}

const NORMALIZATION_LIMITATION = "EXIF and C2PA provenance were not analyzed in this pass.";

/** @param {string} value */
function humanizeLimitation(value) {
  if (/C2PA|content credentials?.*(failed|error|did not complete)|(?:failed|error|did not complete).*content credentials?/i.test(value)) {
    return "Agent 0 couldn’t check the content credentials attached to this image.";
  }
  if (/EXIF/i.test(value)) return "Some information stored in the image file was unavailable.";
  if (/visual interpretation|visual analysis/i.test(value)) return "Agent 0 couldn’t examine what is visible in the image.";
  if (/provider|pipeline|analyzer|MEDIA_|MediaAnalysisRun/i.test(value)) return "Part of the image review could not be completed.";
  return safeEvidenceText(value);
}

/** @param {{ evidence?: { method?: string; limitations?: string | null; provenance?: { limitations?: string[] } | null }[]; brief?: { limitations?: string[] } | null }} results */
export function presentedLimitations(results) {
  const metadataWasAnalyzed = results.evidence?.some((item) => item.method === "MEDIA_TECHNICAL_METADATA") ?? false;
  const limitations = [
    ...(results.brief?.limitations ?? []),
    ...(results.evidence ?? []).map((item) => item.limitations).filter(Boolean),
    ...(results.evidence ?? []).flatMap((item) => item.provenance?.limitations ?? []),
  ];
  return limitations
    .filter((item) => !(metadataWasAnalyzed && item === NORMALIZATION_LIMITATION))
    .map(humanizeLimitation)
    .filter((item, index, all) => all.indexOf(item) === index)
    .slice(0, 8);
}

/** @param {string} content */
export function visualObservations(content) {
  const marker = "Structured visual observations (not forensic findings): ";
  const start = content.indexOf(marker);
  if (start < 0) return [];
  try {
    const values = JSON.parse(content.slice(start + marker.length));
    if (!Array.isArray(values)) return [];
    return values.slice(0, 12).flatMap((item) => {
      if (!item || typeof item.observation !== "string") return [];
      return [{
        observation: safeEvidenceText(item.observation),
        relevance: typeof item.relevance === "string" ? safeEvidenceText(item.relevance) : "",
        limitations: Array.isArray(item.limitations)
          ? item.limitations.filter((value) => typeof value === "string").slice(0, 5).map(safeEvidenceText)
          : [],
      }];
    });
  } catch {
    return [];
  }
}

/** @param {unknown} error */
export function uploadErrorMessage(error) {
  const value = typeof error === "object" && error !== null ? error : {};
  const code = "code" in value && typeof value.code === "string" ? value.code : "";
  const messages = {
    REQUIRED_DEPENDENCY_UNAVAILABLE: "Agent 0’s investigation service is temporarily unavailable. Try again shortly.",
    UPLOAD_TOO_LARGE: "This image exceeds the 25 MB upload limit.",
    UNSUPPORTED_MEDIA_TYPE: "Agent 0 currently supports JPEG, PNG and WebP images.",
    IMAGE_PIXEL_LIMIT_EXCEEDED: "This image is too large to process safely.",
    INVALID_MEDIA: "Agent 0 could not safely decode this image.",
    IMAGE_DECODE_FAILED: "Agent 0 could not safely decode this image.",
  };
  if (messages[code]) return messages[code];
  if ("message" in value && typeof value.message === "string") return value.message;
  if (typeof error === "string") return error;
  return "The request could not be completed. Try again.";
}
