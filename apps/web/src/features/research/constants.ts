export const PROJECT_TYPES = ["market", "customer", "competitor", "mixed"] as const;
export type ProjectType = (typeof PROJECT_TYPES)[number];

export const PROJECT_STATUSES = [
  "draft",
  "collecting",
  "processing",
  "completed",
  "failed",
  "archived",
] as const;
export type ProjectStatus = (typeof PROJECT_STATUSES)[number];

export const SOURCE_TYPES = [
  "website",
  "product_page",
  "landing_page",
  "advertisement",
  "social_profile",
  "social_post",
  "review",
  "article",
  "search_result",
  "uploaded_document",
  "manual",
  "other",
] as const;
export type SourceType = (typeof SOURCE_TYPES)[number];

export const EVIDENCE_TYPES = [
  "pricing",
  "offer",
  "product",
  "positioning",
  "feature",
  "benefit",
  "pain_point",
  "desire",
  "objection",
  "buying_trigger",
  "review",
  "complaint",
  "trust_signal",
  "messaging",
  "creative_pattern",
  "audience_signal",
  "market_signal",
  "competitor_gap",
  "funnel_signal",
  "other",
] as const;
export type EvidenceType = (typeof EVIDENCE_TYPES)[number];

export const FINDING_CATEGORIES = [
  "market",
  "customer",
  "competitor",
  "offer",
  "pricing",
  "positioning",
  "messaging",
  "creative",
  "funnel",
  "product",
  "retention",
] as const;
export type FindingCategory = (typeof FINDING_CATEGORIES)[number];

export const CLASSIFICATION_VALUES = ["observed", "inferred", "hypothesis"] as const;
export type Classification = (typeof CLASSIFICATION_VALUES)[number];

export const PROVENANCE_VALUES = [
  "collected",
  "cited",
  "paraphrased",
  "analyzed",
  "synthesized",
] as const;
export type Provenance = (typeof PROVENANCE_VALUES)[number];

export const IMPORTANCE_VALUES = ["low", "medium", "high"] as const;
export type Importance = (typeof IMPORTANCE_VALUES)[number];

export const EVIDENCE_STRENGTHS = ["strong", "moderate", "weak", "insufficient"] as const;
export type EvidenceStrength = (typeof EVIDENCE_STRENGTHS)[number];
