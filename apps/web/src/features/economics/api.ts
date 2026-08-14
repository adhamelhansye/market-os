import { apiGet } from "@/lib/api-client";

import type { components } from "@marketing-os/shared-types";

export type EconomicsSummary = components["schemas"]["EconomicsSummaryRead"];
export type ProductEconomics = components["schemas"]["ProductEconomicsRead"];
export type Goal = components["schemas"]["GoalRead"];

export function fetchEconomicsSummary(businessId: string): Promise<EconomicsSummary> {
  return apiGet<EconomicsSummary>(
    `/api/v1/businesses/${businessId}/economics/summary`
  );
}

export function fetchEconomicsProducts(businessId: string): Promise<ProductEconomics[]> {
  return apiGet<ProductEconomics[]>(
    `/api/v1/businesses/${businessId}/economics/products`
  );
}

export function fetchEconomicsGoals(businessId: string): Promise<Goal[]> {
  return apiGet<Goal[]>(`/api/v1/businesses/${businessId}/economics/goals`);
}