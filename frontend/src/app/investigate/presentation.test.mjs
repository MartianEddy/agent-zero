import test from "node:test";
import assert from "node:assert/strict";
import {
  aiDeclarationCopy,
  findingEvidenceReferences,
  inferInputType,
  provenancePresentation,
  presentedLimitations,
  recommendedNextSteps,
  safeEvidenceText,
  stagePresentation,
  relationshipPresentation,
  statusPresentation,
  technicalMetadata,
  unknownsFromResults,
  uploadErrorMessage,
  visualAnalysisNotice,
  visualObservations,
} from "./presentation.mjs";

const baseResults = {
  claims: [],
  evidence: [],
  findings: [],
  sources: [],
  evidence_coverage: {
    claims_total: 1,
    claims_with_linked_evidence: 0,
    claims_without_linked_evidence: 1,
    findings_total: 1,
    findings_with_evidence: 0,
    sources_total: 0,
    sources_retrieved: 0,
  },
  usage_summary: { limitations: [] },
};

test("all claim finding statuses have readable labels and explanations", () => {
  for (const status of ["SUPPORTED", "CONTRADICTED", "UNVERIFIED", "INCONCLUSIVE"]) {
    const copy = statusPresentation(status);
    assert.ok(copy.icon);
    assert.ok(copy.label);
    assert.ok(copy.explanation);
  }
});

test("backend verdicts map to calm, non-binary language", () => {
  assert.equal(statusPresentation("SUPPORTED").label, "Supported by evidence");
  assert.equal(statusPresentation("CONTRADICTED").label, "Contradicted by evidence");
  assert.equal(statusPresentation("UNVERIFIED").label, "Not verified");
  assert.equal(statusPresentation("INCONCLUSIVE").label, "Inconclusive");
  assert.equal(statusPresentation("UNVERIFIED").explanation, "There isn’t enough reliable evidence to confirm this yet.");
});

test("unified input infers web links without asking for a mode", () => {
  assert.equal(inferInputType("  https://example.org/story  "), "URL");
  assert.equal(inferInputType("Is this claim accurate?"), "TEXT");
  assert.equal(inferInputType("www.example.org/story"), "TEXT");
});

test("required backend configuration errors explain that investigation is temporarily unavailable", () => {
  assert.match(
    uploadErrorMessage({ code: "REQUIRED_DEPENDENCY_UNAVAILABLE", dependency: "investigation_engine" }),
    /temporarily unavailable/i,
  );
});

test("processing and evidence relationships use reader-facing language", () => {
  assert.equal(stagePresentation("CORROBORATING"), "Comparing what the evidence says");
  assert.equal(relationshipPresentation("SUPPORTS"), "Supports this");
  assert.equal(relationshipPresentation("CONTRADICTS"), "Challenges this");
  assert.equal(relationshipPresentation("CONTEXTUALIZES"), "Adds context");
});

test("content credential states explain what was found without authenticity verdicts", () => {
  for (const [state, expected] of [
    ["VALID", "checked on the uploaded file"],
    ["NOT_PRESENT", "No supported origin credentials"],
    ["INVALID", "could not confirm their details"],
  ]) {
    const copy = provenancePresentation(state);
    assert.match(copy.explanation, new RegExp(expected, "i"));
    assert.ok(copy.limitation);
    assert.doesNotMatch(`${copy.label} ${copy.explanation}`, /\b(fake|real|authentic)\b/i);
  }
});

test("AI declarations use declaration language only", () => {
  assert.equal(
    aiDeclarationCopy(["GENERATIVE_AI_CREATION_DECLARED"]),
    "AI use was declared. The image’s attached origin information states that generative AI was used during its creation or editing.",
  );
  assert.equal(aiDeclarationCopy([]), null);
});

test("unknowns, limitations, next steps, and partial-analysis notice are available", () => {
  const results = {
    ...baseResults,
    claims: [{ id: "claim-1", text: "The event occurred." }],
    evidence: [{ id: "e1", provenance: { status: "NOT_PRESENT" } }],
    findings: [{ status: "INCONCLUSIVE" }],
    usage_summary: { limitations: ["Visual interpretation was unavailable after provider failure."] },
  };
  const unknowns = unknownsFromResults(results);
  assert.ok(unknowns.some((item) => item.includes("No evidence is linked")));
  assert.ok(unknowns.some((item) => item.includes("No supported Content Credentials")));
  assert.ok(recommendedNextSteps(results).some((item) => item.includes("original media")));
  assert.match(visualAnalysisNotice(results), /origin details, file information, and source information remain available/);
});

test("a question without an extracted claim remains visible as an unknown with useful next steps", () => {
  const results = {
    ...baseResults,
    media_assets: [{ media_type: "IMAGE", role: "ORIGINAL" }],
  };
  assert.ok(unknownsFromResults(results).some((item) => item.includes("No verifiable claim was extracted")));
  assert.ok(recommendedNextSteps(results).some((item) => item.includes("Content Credentials")));
});

test("visible observations render as observations and finding evidence resolves to detail", () => {
  const evidence = [{ id: "evidence-secret-id", content: "Visible text: station notice" }];
  const finding = { evidence_ids: ["evidence-secret-id", "missing"] };
  const [resolved] = findingEvidenceReferences(finding, evidence);
  assert.equal(resolved.content, "Visible text: station notice");
  const observations = visualObservations(
    'Structured visual observations (not forensic findings): [{"observation":"A sign reads Station 4","relevance":"Location text","limitations":["May be incomplete"]}]',
  );
  assert.equal(observations[0].observation, "A sign reads Station 4");
  assert.equal(observations[0].limitations[0], "May be incomplete");
});

test("technical metadata is allowlisted and upload errors are journalist-friendly", () => {
  const fields = technicalMetadata(
    'Safe decoded fields: {"format":"jpeg","width":800,"height":600,"gps_present":true,"serial":"private"}. Analyzed asset',
  );
  assert.deepEqual(fields.map(([label]) => label), ["Format", "Dimensions"]);
  assert.equal(uploadErrorMessage({ code: "UPLOAD_TOO_LARGE" }), "This image exceeds the 25 MB upload limit.");
  assert.match(uploadErrorMessage({ code: "IMAGE_PIXEL_LIMIT_EXCEEDED" }), /too large to process safely/);
  assert.match(uploadErrorMessage({ code: "UNSUPPORTED_MEDIA_TYPE" }), /JPEG, PNG and WebP/);
  assert.match(uploadErrorMessage({ code: "IMAGE_DECODE_FAILED" }), /could not safely decode/);
});

test("limitations do not say metadata was skipped when a metadata observation exists", () => {
  const results = {
    ...baseResults,
    evidence: [
      { id: "metadata", method: "MEDIA_TECHNICAL_METADATA" },
      { id: "provenance", method: "MEDIA_PROVENANCE", provenance: { limitations: ["Offline checks were not performed."] } },
    ],
    brief: {
      summary: "Review required.",
      version: 1,
      limitations: ["EXIF and C2PA provenance were not analyzed in this pass.", "C2PA validation did not complete."],
    },
  };
  const limitations = presentedLimitations(results);
  assert.ok(!limitations.includes("EXIF and C2PA provenance were not analyzed in this pass."));
  assert.ok(limitations.includes("Agent 0 couldn’t check the content credentials attached to this image."));
  assert.ok(limitations.includes("Offline checks were not performed."));
});

test("private coordinates, paths, URLs, and certificates are not rendered", () => {
  const rendered = safeEvidenceText(
    "GPS 36.8219,-1.2921 at private/media/original.png /home/bouric/private/original.png " +
      "https://private.invalid/cert " +
      "-----BEGIN CERTIFICATE-----secret-----END CERTIFICATE-----",
  );
  assert.doesNotMatch(rendered, /36\.8219|-1\.2921|private\/media|\/home\/bouric|https?:|BEGIN CERTIFICATE|secret/);
  const visual = visualObservations(
    'Structured visual observations (not forensic findings): [{"observation":"Coordinates 36.8219,-1.2921"}]',
  );
  assert.doesNotMatch(visual[0].observation, /36\.8219|-1\.2921/);
});
