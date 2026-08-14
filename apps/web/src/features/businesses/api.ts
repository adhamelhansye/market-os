import { apiGet, apiPatch, apiPost, apiPut } from "@/lib/api-client";

import type { components } from "@marketing-os/shared-types";

export type Business = components["schemas"]["BusinessRead"];
export type BusinessCreate = components["schemas"]["BusinessCreate"];
export type BusinessUpdate = components["schemas"]["BusinessUpdate"];
export type BusinessProfile = components["schemas"]["BusinessProfileRead"];
export type BusinessProfileWrite = components["schemas"]["BusinessProfileWrite"];

export function fetchBusinesses(): Promise<Business[]> {
  return apiGet<Business[]>("/api/v1/businesses");
}

export function fetchBusiness(businessId: string): Promise<Business> {
  return apiGet<Business>(`/api/v1/businesses/${businessId}`);
}

export function createBusiness(payload: BusinessCreate): Promise<Business> {
  return apiPost<Business>("/api/v1/businesses", payload);
}

export function updateBusiness(
  businessId: string,
  payload: BusinessUpdate
): Promise<Business> {
  return apiPatch<Business>(`/api/v1/businesses/${businessId}`, payload);
}

export function fetchBusinessProfile(businessId: string): Promise<BusinessProfile> {
  return apiGet<BusinessProfile>(`/api/v1/businesses/${businessId}/profile`);
}

export function updateBusinessProfile(
  businessId: string,
  payload: BusinessProfileWrite
): Promise<BusinessProfile> {
  return apiPut<BusinessProfile>(`/api/v1/businesses/${businessId}/profile`, payload);
}