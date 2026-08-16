import { apiGet, apiPost } from "@/lib/api-client";
import type { RangeKind } from "@/features/metrics/api";

import type { components } from "@marketing-os/shared-types";

export type DecisionsRead = components["schemas"]["DecisionsRead"];
export type DecisionRead = components["schemas"]["DecisionRead"];
export type DecisionSummaryRead = components["schemas"]["DecisionSummaryRead"];
export type GenerateRequest = components["schemas"]["GenerateRequest"];

function recommendationsUrl(businessId: string, path: string, rangeKind: RangeKind): string {
  const params = new URLSearchParams({ range_kind: rangeKind });
  return `/api/v1/businesses/${businessId}/recommendations${path}?${params.toString()}`;
}

export function fetchRecommendations(
  businessId: string,
  rangeKind: RangeKind
): Promise<DecisionsRead> {
  return apiGet<DecisionsRead>(recommendationsUrl(businessId, "", rangeKind));
}

export function fetchRecommendationsSummary(
  businessId: string,
  rangeKind: RangeKind
): Promise<DecisionSummaryRead> {
  return apiGet<DecisionSummaryRead>(
    recommendationsUrl(businessId, "/summary", rangeKind)
  );
}

export async function generateRecommendations(
  businessId: string,
  rangeKind: RangeKind
): Promise<DecisionsRead> {
  const payload: GenerateRequest = { range_kind: rangeKind };
  return apiPost<DecisionsRead>(
    `/api/v1/businesses/${businessId}/recommendations/generate`,
    payload
  );
}

export function fetchCampaignRecommendation(
  businessId: string,
  campaignId: string,
  rangeKind: RangeKind
): Promise<DecisionRead> {
  const params = new URLSearchParams({ range_kind: rangeKind });
  return apiGet<DecisionRead>(
    `/api/v1/businesses/${businessId}/campaigns/${campaignId}/recommendation?${params.toString()}`
  );
}