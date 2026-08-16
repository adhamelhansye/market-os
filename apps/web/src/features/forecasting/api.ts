import { apiGet, apiPost } from "@/lib/api-client";
import type { components } from "@marketing-os/shared-types";

export type ForecastSummaryRead = components["schemas"]["ForecastSummaryRead"];
export type ForecastRead = components["schemas"]["ForecastRead"];
export type ForecastWithPointsRead = components["schemas"]["ForecastWithPointsRead"];
export type CampaignForecastRead = components["schemas"]["CampaignForecastRead"];
export type ForecastGenerateRequest = components["schemas"]["ForecastGenerateRequest"];

function businessForecastUrl(businessId: string, path: string, horizonDays: number): string {
  const params = new URLSearchParams({ horizon_days: String(horizonDays) });
  return `/api/v1/businesses/${businessId}/forecast/${path}?${params.toString()}`;
}

export function fetchForecastSummary(businessId: string, horizonDays: number): Promise<ForecastSummaryRead> {
  return apiGet<ForecastSummaryRead>(businessForecastUrl(businessId, "summary", horizonDays));
}

export function fetchBusinessForecasts(businessId: string, horizonDays: number, metricCode?: string): Promise<ForecastWithPointsRead[]> {
  const params = new URLSearchParams({ horizon_days: String(horizonDays) });
  if (metricCode) {
    params.set("metric_code", metricCode);
  }
  return apiGet<ForecastWithPointsRead[]>(`/api/v1/businesses/${businessId}/forecast?${params.toString()}`);
}

export async function generateBusinessForecast(
  businessId: string,
  payload: ForecastGenerateRequest
): Promise<ForecastWithPointsRead[]> {
  return apiPost<ForecastWithPointsRead[]>(
    `/api/v1/businesses/${businessId}/forecast/generate`,
    payload
  );
}

export function fetchCampaignForecast(businessId: string, campaignId: string, horizonDays: number): Promise<CampaignForecastRead> {
  const params = new URLSearchParams({ horizon_days: String(horizonDays) });
  return apiGet<CampaignForecastRead>(
    `/api/v1/businesses/${businessId}/campaigns/${campaignId}/forecast?${params.toString()}`
  );
}