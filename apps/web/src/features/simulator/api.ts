import { apiGet, apiPost } from "@/lib/api-client";
import type { components } from "@marketing-os/shared-types";

export type SimulationRead = components["schemas"]["SimulationRead"];
export type SimulationSummaryRead = components["schemas"]["SimulationSummaryRead"];
export type SimulationCreateRequest = components["schemas"]["SimulationCreateRequest"];
export type SimulationOverrideInput = components["schemas"]["SimulationOverrideInput"];
export type AssumptionRead = components["schemas"]["AssumptionRead"];
export type ScenarioResultRead = components["schemas"]["ScenarioResultRead"];
export type ScenarioMetricsRead = components["schemas"]["ScenarioMetricsRead"];
export type SensitivityTableRead = components["schemas"]["SensitivityTableRead"];
export type SensitivityRowRead = components["schemas"]["SensitivityRowRead"];
export type BreakEvenRead = components["schemas"]["BreakEvenRead"];
export type ProfitabilityRead = components["schemas"]["ProfitabilityRead"];
export type TargetComparisonRead = components["schemas"]["TargetComparisonRead"];

export const SIMULATION_WINDOWS = [7, 14, 30, 60, 90] as const;
export type SimulationWindow = (typeof SIMULATION_WINDOWS)[number];

export const OVERRIDE_KEYS = [
  "budget",
  "ctr",
  "cpc",
  "cpm",
  "cvr",
  "aov",
  "refund_rate",
  "contribution_margin",
  "shipping_cost",
  "payment_fees",
] as const;
export type OverrideKey = (typeof OVERRIDE_KEYS)[number];

export function fetchSimulations(businessId: string): Promise<SimulationSummaryRead> {
  return apiGet<SimulationSummaryRead>(`/api/v1/businesses/${businessId}/simulations`);
}

export function fetchSimulation(
  businessId: string,
  simulationId: string
): Promise<SimulationRead> {
  return apiGet<SimulationRead>(
    `/api/v1/businesses/${businessId}/simulations/${simulationId}`
  );
}

export function createSimulation(
  businessId: string,
  payload: SimulationCreateRequest
): Promise<SimulationRead> {
  return apiPost<SimulationRead>(`/api/v1/businesses/${businessId}/simulations`, payload);
}

export function rerunSimulation(
  businessId: string,
  simulationId: string
): Promise<SimulationRead> {
  return apiPost<SimulationRead>(
    `/api/v1/businesses/${businessId}/simulations/${simulationId}/rerun`,
    {}
  );
}

export function simulateCampaign(
  businessId: string,
  campaignId: string,
  payload: SimulationCreateRequest
): Promise<SimulationRead> {
  return apiPost<SimulationRead>(
    `/api/v1/businesses/${businessId}/campaigns/${campaignId}/simulate`,
    payload
  );
}