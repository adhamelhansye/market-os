import { apiGet } from "@/lib/api-client";

import type { components } from "@marketing-os/shared-types";

export type OrganizationSummary = components["schemas"]["OrganizationSummaryRead"];

export function fetchOrganizations(): Promise<OrganizationSummary[]> {
  return apiGet<OrganizationSummary[]>("/api/v1/organizations");
}

export function fetchOrganization(organizationId: string): Promise<components["schemas"]["OrganizationRead"]> {
  return apiGet<components["schemas"]["OrganizationRead"]>(
    `/api/v1/organizations/${organizationId}`
  );
}