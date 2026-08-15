import { apiGet } from "@/lib/api-client";
import type { RangeKind } from "@/features/metrics/api";

import type { components } from "@marketing-os/shared-types";

export type DiagnosticsRead = components["schemas"]["DiagnosticsRead"];
export type DiagnosticsSummaryRead = components["schemas"]["DiagnosticsSummaryRead"];
export type CampaignDiagnosticsRead = components["schemas"]["CampaignDiagnosticsRead"];
export type FindingRead = components["schemas"]["FindingRead"];
export type CampaignStateRead = components["schemas"]["CampaignStateRead"];
export type ScalingReadinessRead = components["schemas"]["ScalingReadinessRead"];

function diagnosticsUrl(businessId: string, path: string, rangeKind: RangeKind): string {
  const params = new URLSearchParams({ range_kind: rangeKind });
  return `/api/v1/businesses/${businessId}/diagnostics${path}?${params.toString()}`;
}

export function fetchDiagnostics(
  businessId: string,
  rangeKind: RangeKind
): Promise<DiagnosticsRead> {
  return apiGet<DiagnosticsRead>(diagnosticsUrl(businessId, "", rangeKind));
}

export function fetchDiagnosticsSummary(
  businessId: string,
  rangeKind: RangeKind
): Promise<DiagnosticsSummaryRead> {
  return apiGet<DiagnosticsSummaryRead>(diagnosticsUrl(businessId, "/summary", rangeKind));
}

export function fetchCampaignDiagnostics(
  businessId: string,
  campaignId: string,
  rangeKind: RangeKind
): Promise<CampaignDiagnosticsRead> {
  return apiGet<CampaignDiagnosticsRead>(
    `/api/v1/businesses/${businessId}/campaigns/${campaignId}/diagnostics?${new URLSearchParams({
      range_kind: rangeKind,
    }).toString()}`
  );
}