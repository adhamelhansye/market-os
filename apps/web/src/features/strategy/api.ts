import { apiDelete, apiGet, apiPost } from "@/lib/api-client";
import type { components } from "@marketing-os/shared-types";

export type PositioningResponse = components["schemas"]["PositioningResponse"];
export type PositioningCandidateRead = components["schemas"]["PositioningCandidateRead"];
export type PositioningCandidateCreate = components["schemas"]["PositioningCandidateCreate"];
export type PositioningVersionsResponse = components["schemas"]["PositioningVersionsResponse"];
export type OfferResponse = components["schemas"]["OfferResponse"];
export type OfferCandidateRead = components["schemas"]["OfferCandidateRead"];
export type OfferCandidateCreate = components["schemas"]["OfferCandidateCreate"];
export type StrategySummaryResponse = components["schemas"]["StrategySummaryResponse"];
export type StrategySnapshotResponse = components["schemas"]["StrategySnapshotResponse"];
export type StrategyDecisionRead = components["schemas"]["StrategyDecisionRead"];
export type StrategyDecisionEvaluateRequest = components["schemas"]["StrategyDecisionEvaluateRequest"];
export type StrategyDecisionListResponse = components["schemas"]["StrategyDecisionListResponse"];
export type StrategyDecisionProvenanceResponse = components["schemas"]["StrategyDecisionProvenanceResponse"];
export type MessagingStrategyRead = components["schemas"]["MessagingStrategyRead"];
export type MessageComponentRead = components["schemas"]["MessageComponentRead"];
export type MessageAngleRead = components["schemas"]["MessageAngleRead"];
export type MessagingGenerateRequest = components["schemas"]["MessagingGenerateRequest"];
export type MessagingVersionsResponse = components["schemas"]["MessagingVersionsResponse"];
export type FunnelStrategyRead = components["schemas"]["FunnelStrategyRead"];
export type FunnelStageRead = components["schemas"]["FunnelStageRead"];
export type FunnelGapRead = components["schemas"]["FunnelGapRead"];
export type FunnelGenerateRequest = components["schemas"]["FunnelGenerateRequest"];
export type FunnelVersionsResponse = components["schemas"]["FunnelVersionsResponse"];
export type FunnelProvenanceResponse = components["schemas"]["FunnelProvenanceResponse"];
export type PerformanceLinkCreate = components["schemas"]["PerformanceLinkCreate"];
export type PerformanceLinkRead = components["schemas"]["PerformanceLinkRead"];
export type PerformanceReportResponse = components["schemas"]["PerformanceReportResponse"];
export type EntityPerformanceResponse = components["schemas"]["EntityPerformanceResponse"];
export type SnapshotCreatedResponse = components["schemas"]["SnapshotCreatedResponse"];
export type SnapshotSummaryRead = components["schemas"]["SnapshotSummaryRead"];

function strategyUrl(businessId: string, path: string): string {
  return `/api/v1/businesses/${businessId}/strategy/${path}`;
}

export function fetchPositioning(businessId: string): Promise<PositioningResponse> {
  return apiGet<PositioningResponse>(strategyUrl(businessId, "positioning"));
}

export function createPositioningCandidate(
  businessId: string,
  payload: PositioningCandidateCreate
): Promise<PositioningCandidateRead> {
  return apiPost<PositioningCandidateRead>(strategyUrl(businessId, "positioning/candidates"), payload);
}

export function recommendPositioning(businessId: string): Promise<PositioningResponse> {
  return apiPost<PositioningResponse>(strategyUrl(businessId, "positioning/recommend"), {});
}

export function fetchOffers(businessId: string): Promise<OfferResponse> {
  return apiGet<OfferResponse>(strategyUrl(businessId, "offers"));
}

export function createOfferCandidate(
  businessId: string,
  payload: OfferCandidateCreate
): Promise<OfferCandidateRead> {
  return apiPost<OfferCandidateRead>(strategyUrl(businessId, "offers/candidates"), payload);
}

export function validateOffer(businessId: string, candidateId: string): Promise<OfferResponse> {
  return apiPost<OfferResponse>(strategyUrl(businessId, "offers/validate"), { candidate_id: candidateId });
}

export function recommendOffer(businessId: string): Promise<OfferResponse> {
  return apiPost<OfferResponse>(strategyUrl(businessId, "offers/recommend"), {});
}

export function fetchStrategySummary(businessId: string): Promise<StrategySummaryResponse> {
  return apiGet<StrategySummaryResponse>(strategyUrl(businessId, "summary"));
}

export function fetchStrategySnapshot(businessId: string): Promise<StrategySnapshotResponse> {
  return apiGet<StrategySnapshotResponse>(strategyUrl(businessId, "snapshot"));
}

export function fetchStrategyDecisions(businessId: string): Promise<StrategyDecisionListResponse> {
  return apiGet<StrategyDecisionListResponse>(strategyUrl(businessId, "decisions"));
}

export function evaluateStrategyDecision(
  businessId: string,
  payload: StrategyDecisionEvaluateRequest
): Promise<StrategyDecisionRead> {
  return apiPost<StrategyDecisionRead>(strategyUrl(businessId, "decisions/evaluate"), payload);
}

export function fetchStrategyDecisionProvenance(
  businessId: string,
  decisionId: string
): Promise<StrategyDecisionProvenanceResponse> {
  return apiGet<StrategyDecisionProvenanceResponse>(strategyUrl(businessId, `decisions/${decisionId}/provenance`));
}

export function fetchMessaging(businessId: string): Promise<MessagingStrategyRead> {
  return apiGet<MessagingStrategyRead>(strategyUrl(businessId, "messaging"));
}

export function generateMessaging(
  businessId: string,
  payload: MessagingGenerateRequest = {}
): Promise<MessagingStrategyRead> {
  return apiPost<MessagingStrategyRead>(strategyUrl(businessId, "messaging/generate"), payload);
}

export function fetchMessagingVersions(businessId: string): Promise<MessagingVersionsResponse> {
  return apiGet<MessagingVersionsResponse>(strategyUrl(businessId, "messaging/versions"));
}

export function fetchFunnel(businessId: string): Promise<FunnelStrategyRead> {
  return apiGet<FunnelStrategyRead>(strategyUrl(businessId, "funnel"));
}

export function generateFunnel(
  businessId: string,
  payload: FunnelGenerateRequest = { range_kind: "last_30_days" }
): Promise<FunnelStrategyRead> {
  return apiPost<FunnelStrategyRead>(strategyUrl(businessId, "funnel/generate"), payload);
}

export function fetchFunnelVersions(businessId: string): Promise<FunnelVersionsResponse> {
  return apiGet<FunnelVersionsResponse>(strategyUrl(businessId, "funnel/versions"));
}

export function fetchFunnelProvenance(
  businessId: string,
  funnelId: string
): Promise<FunnelProvenanceResponse> {
  return apiGet<FunnelProvenanceResponse>(strategyUrl(businessId, `funnel/${funnelId}/provenance`));
}

// ---------------------------------------------------------------------------
// Creative performance intelligence (Phase 8C) — observed data only
//
// Engine evidence blocks are versioned structured payloads on the wire
// (each stamps its own rules_version), so their shapes are declared
// explicitly here rather than via the loose generated dict types.
// ---------------------------------------------------------------------------

export type PerformanceSignal = {
  code: string;
  value: string | null;
  status: string;
  reason: string | null;
  unit: string;
  source: string;
};

export type PerformanceTrend = {
  status: string;
  metrics: Record<string, { direction?: string }>;
};

export type PerformanceFatigue = {
  status: string;
  signals: { code: string; triggered: boolean }[];
};

export type PerformanceClassification = {
  status: string;
  rule: string;
  reasons: string[];
};

export type PerformanceReadinessGate = {
  code: string;
  met: boolean;
  value: string | number | null;
  threshold_value: string | number | null;
};

export type PerformanceReadiness = {
  status: string;
  ready_for_review: boolean;
  gates: PerformanceReadinessGate[];
};

export type PerformanceEntityResult = {
  link_id: string | null;
  entity: { type: string; id: string };
  attribution: { status: string; reason: string | null };
  context: Record<string, unknown>;
  observation: {
    entity: { type: string; id: string };
    range: { kind: string };
    days_covered: number;
    totals: Record<string, string | null>;
  };
  signals: PerformanceSignal[];
  trend: PerformanceTrend;
  fatigue: PerformanceFatigue & { score?: number | null };
  classification: PerformanceClassification;
  scaling_readiness: PerformanceReadiness;
  provenance: { chain: { step: string; id?: string }[] };
};

export type PerformanceComparisonGroup = {
  ranked: { rank: number; entity: { id: string }; value: string | null }[];
  excluded: { entity: { id: string }; reasons: string[] }[];
  spread: { absolute_change: string | null; percentage_change: string | null } | null;
};

export type CreativePerformanceReport = {
  business_id: string;
  currency: string;
  range: { kind: string; start: string; end: string };
  rules_versions: Record<string, string>;
  break_even_roas_available: boolean;
  attribution: { status: string; reason?: string; linked_entities: number };
  entities: PerformanceEntityResult[];
  comparisons: Record<string, Record<string, PerformanceComparisonGroup>>;
  fingerprint: string;
};

function performanceUrl(businessId: string, path = ""): string {
  return `/api/v1/businesses/${businessId}/strategy/creative/performance${path}`;
}

export async function fetchCreativePerformanceReport(
  businessId: string,
  rangeKind: string = "last_30_days"
): Promise<CreativePerformanceReport> {
  const raw = await apiGet<PerformanceReportResponse>(
    `${performanceUrl(businessId, "/report")}?range_kind=${encodeURIComponent(rangeKind)}`
  );
  return raw as unknown as CreativePerformanceReport;
}

export function fetchCreativePerformanceEntity(
  businessId: string,
  entityType: "creative_concept" | "creative_test_variant",
  entityId: string,
  rangeKind: string = "last_30_days"
): Promise<EntityPerformanceResponse> {
  return apiGet<EntityPerformanceResponse>(
    `${performanceUrl(businessId, `/entities/${entityType}/${entityId}`)}?range_kind=${encodeURIComponent(rangeKind)}`
  );
}

export function fetchCreativePerformanceLinks(businessId: string): Promise<PerformanceLinkRead[]> {
  return apiGet<PerformanceLinkRead[]>(performanceUrl(businessId, "/links"));
}

export async function deleteCreativePerformanceLink(
  businessId: string,
  linkId: string
): Promise<void> {
  await apiDelete(`/api/v1/businesses/${businessId}/strategy/creative/performance/links/${linkId}`);
}

export async function createCreativePerformanceSnapshot(
  businessId: string,
  rangeKind: string = "last_30_days"
): Promise<SnapshotCreatedResponse> {
  return apiPost<SnapshotCreatedResponse>(
    `${performanceUrl(businessId, "/snapshots")}?range_kind=${encodeURIComponent(rangeKind)}`,
    {}
  );
}
