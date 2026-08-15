import { apiGet } from "@/lib/api-client";

import type { components } from "@marketing-os/shared-types";

export type SummaryRead = components["schemas"]["SummaryRead"];
export type TimeseriesRead = components["schemas"]["TimeseriesRead"];
export type FunnelRead = components["schemas"]["FunnelRead"];
export type CampaignsRead = components["schemas"]["CampaignsRead"];
export type AdSetsRead = components["schemas"]["AdSetsRead"];
export type AdsRead = components["schemas"]["AdsRead"];
export type ProductsRead = components["schemas"]["ProductsRead"];
export type DataQualityRead = components["schemas"]["DataQualityRead"];
export type ComparisonRead = components["schemas"]["ComparisonReadResponse"];

export type MeasureRead = components["schemas"]["MeasureRead"];
export type MoneyMeasureRead = components["schemas"]["MoneyMeasureRead"];

export type RangeKind =
  | "today"
  | "yesterday"
  | "last_7_days"
  | "last_14_days"
  | "last_30_days"
  | "month_to_date";

function metricsUrl(businessId: string, path: string, rangeKind: RangeKind): string {
  const params = new URLSearchParams({ range_kind: rangeKind });
  return `/api/v1/businesses/${businessId}/metrics/${path}?${params.toString()}`;
}

export function fetchMetricsSummary(
  businessId: string,
  rangeKind: RangeKind
): Promise<SummaryRead> {
  return apiGet<SummaryRead>(metricsUrl(businessId, "summary", rangeKind));
}

export function fetchMetricsTimeseries(
  businessId: string,
  rangeKind: RangeKind
): Promise<TimeseriesRead> {
  return apiGet<TimeseriesRead>(metricsUrl(businessId, "timeseries", rangeKind));
}

export function fetchMetricsFunnel(
  businessId: string,
  rangeKind: RangeKind
): Promise<FunnelRead> {
  return apiGet<FunnelRead>(metricsUrl(businessId, "funnel", rangeKind));
}

export function fetchMetricsCampaigns(
  businessId: string,
  rangeKind: RangeKind
): Promise<CampaignsRead> {
  return apiGet<CampaignsRead>(metricsUrl(businessId, "campaigns", rangeKind));
}

export function fetchMetricsDataQuality(
  businessId: string,
  rangeKind: RangeKind
): Promise<DataQualityRead> {
  return apiGet<DataQualityRead>(metricsUrl(businessId, "data-quality", rangeKind));
}

export function fetchMetricsComparison(
  businessId: string,
  rangeKind: RangeKind
): Promise<ComparisonRead> {
  return apiGet<ComparisonRead>(metricsUrl(businessId, "comparison", rangeKind));
}