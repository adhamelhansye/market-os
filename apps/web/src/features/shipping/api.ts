import { apiGet, apiPatch, apiPost } from "@/lib/api-client";

import type { components } from "@marketing-os/shared-types";

export type ShippingRule = components["schemas"]["ShippingRuleRead"];
export type ShippingRuleCreate = components["schemas"]["ShippingRuleCreate"];
export type ShippingRuleUpdate = components["schemas"]["ShippingRuleUpdate"];

export function fetchShippingRules(businessId: string): Promise<ShippingRule[]> {
  return apiGet<ShippingRule[]>(`/api/v1/businesses/${businessId}/shipping-rules`);
}

export function createShippingRule(
  businessId: string,
  payload: ShippingRuleCreate
): Promise<ShippingRule> {
  return apiPost<ShippingRule>(
    `/api/v1/businesses/${businessId}/shipping-rules`,
    payload
  );
}

export function updateShippingRule(
  businessId: string,
  ruleId: string,
  payload: ShippingRuleUpdate
): Promise<ShippingRule> {
  return apiPatch<ShippingRule>(
    `/api/v1/businesses/${businessId}/shipping-rules/${ruleId}`,
    payload
  );
}