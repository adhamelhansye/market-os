import { apiGet, apiPost } from "@/lib/api-client";

import type { components } from "@marketing-os/shared-types";

export type Connection = components["schemas"]["ConnectionRead"];
export type SyncRun = components["schemas"]["SyncRunRead"];
export type MetaAccount = components["schemas"]["MetaAccountRead"];

export function fetchConnections(businessId: string): Promise<Connection[]> {
  return apiGet<Connection[]>(`/api/v1/businesses/${businessId}/integrations`);
}

export function connectShopify(
  businessId: string,
  shopDomain: string
): Promise<components["schemas"]["ShopifyConnectResponse"]> {
  return apiPost<components["schemas"]["ShopifyConnectResponse"]>(
    `/api/v1/businesses/${businessId}/integrations/shopify/connect`,
    { shop_domain: shopDomain }
  );
}

export function connectMeta(
  businessId: string,
  locale: string
): Promise<components["schemas"]["MetaConnectResponse"]> {
  return apiPost<components["schemas"]["MetaConnectResponse"]>(
    `/api/v1/businesses/${businessId}/integrations/meta/connect`,
    { locale }
  );
}

export function fetchMetaAccounts(
  businessId: string
): Promise<components["schemas"]["MetaAccountsResponse"]> {
  return apiGet<components["schemas"]["MetaAccountsResponse"]>(
    `/api/v1/businesses/${businessId}/integrations/meta/accounts`
  );
}

export function selectMetaAccount(
  businessId: string,
  externalAccountId: string
): Promise<Connection> {
  return apiPost<Connection>(
    `/api/v1/businesses/${businessId}/integrations/meta/accounts/select`,
    { external_account_id: externalAccountId }
  );
}

export function syncConnection(
  businessId: string,
  connectionId: string,
  resources?: string[]
): Promise<components["schemas"]["SyncResponse"]> {
  return apiPost(
    `/api/v1/businesses/${businessId}/integrations/${connectionId}/sync`,
    resources ? { resources } : {}
  );
}

export function disconnectConnection(
  businessId: string,
  connectionId: string
): Promise<Connection> {
  return apiPost<Connection>(
    `/api/v1/businesses/${businessId}/integrations/${connectionId}/disconnect`,
    {}
  );
}