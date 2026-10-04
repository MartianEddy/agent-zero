export type InvestigationStatus =
  | "RECEIVED"
  | "PROCESSING"
  | "ANALYZING"
  | "RESEARCHING"
  | "CORROBORATING"
  | "GENERATING_BRIEF"
  | "COMPLETE"
  | "NEEDS_REVIEW"
  | "FAILED"
  | "CANCELLED";

export type FindingStatus =
  | "SUPPORTED"
  | "CONTRADICTED"
  | "UNVERIFIED"
  | "INCONCLUSIVE"
  | "MISLEADING_CONTEXT"
  | "ALTERED_MEDIA"
  | "OUTDATED_CONTEXT";

export type Investigation = {
  id: string;
  reference: string;
  status: InvestigationStatus;
  current_stage: string;
  created_at: string;
  failure_reason?: string | null;
};

export type Claim = { id: string; text: string; type: string };
export type EvidenceRelationship = {
  claim_id: string;
  relationship: string;
};

export type ProvenanceSummary = {
  status: string | null;
  credentials_present: boolean;
  validation_state: string | null;
  signature_state: string | null;
  signer_identity_available: boolean;
  actions: { action?: string; digital_source_type?: string | null }[];
  ai_disclosures: string[];
  ingredient_count: number;
  validation_codes: string[];
  limitations: string[];
  analysis_run_id?: string;
};

export type MediaAssetSummary = {
  id: string;
  media_type: string;
  mime_type: string;
  size_bytes: number;
  role: string;
  artifact_type?: string | null;
  parent_asset_id?: string | null;
};

export type Source = {
  id: string;
  url: string;
  title?: string | null;
  publisher?: string | null;
  domain?: string | null;
  source_type: string;
  source_role: string;
  registry_jurisdiction?: string | null;
  authoritative_for: string[];
  canonical_url?: string | null;
  author?: string | null;
  published_at?: string | null;
  modified_at?: string | null;
  retrieval_status: string;
  retrieval_failure_reason?: string | null;
  retrieval_provider?: string | null;
  retrieved_at?: string | null;
  discovery_method: string;
};

export type Evidence = {
  id: string;
  content: string;
  method: string;
  limitations?: string | null;
  origin: { source_id?: string | null; media_asset_id?: string | null };
  claim_links: EvidenceRelationship[];
  source?: { id: string; url: string } | null;
  media_asset?: MediaAssetSummary | null;
  provenance?: ProvenanceSummary | null;
};

export type Finding = {
  id: string;
  claim_id: string;
  status: FindingStatus;
  statement: string;
  limitations?: string | null;
  evidence_ids: string[];
};

export type Results = {
  investigation_id: string;
  status: InvestigationStatus;
  current_stage: string;
  media_assets?: MediaAssetSummary[];
  claims: Claim[];
  sources: Source[];
  source_relationships: {
    source_id: string;
    related_source_id: string;
    relationship: string;
    basis: string;
  }[];
  search_traces: {
    id: string;
    provider: string;
    action: string;
    query?: string | null;
    url?: string | null;
    sources: { url: string; title: string }[];
    citations: { url: string; title: string }[];
  }[];
  claim_evidence: { claim_id: string; evidence_id: string; relationship: string }[];
  evidence: Evidence[];
  findings: Finding[];
  evidence_coverage: {
    claims_total: number;
    claims_with_linked_evidence: number;
    claims_without_linked_evidence: number;
    findings_total: number;
    findings_with_evidence: number;
    sources_total: number;
    sources_retrieved: number;
  };
  brief?: { summary: string; limitations: string[]; version: number } | null;
  retry_allowed?: boolean;
  usage_summary?: {
    model_calls: number;
    search_calls: number;
    sources_discovered: number;
    sources_retrieved: number;
    input_tokens: number;
    output_tokens: number;
    limitations: string[];
  } | null;
};
