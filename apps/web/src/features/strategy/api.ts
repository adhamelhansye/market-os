import { apiGet, apiPost } from "@/lib/api-client";
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
