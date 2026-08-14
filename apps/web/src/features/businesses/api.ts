import { apiGet } from "@/lib/api-client";

import type { components } from "@marketing-os/shared-types";

export type Business = components["schemas"]["BusinessRead"];

export function fetchBusinesses(): Promise<Business[]> {
  return apiGet<Business[]>("/api/v1/businesses");
}

export function fetchBusiness(businessId: string): Promise<Business> {
  return apiGet<Business>(`/api/v1/businesses/${businessId}`);
}