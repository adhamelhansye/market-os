# Shopify provider

## Scope

Phase 2A implements the Shopify adapter (`src/modules/integrations/shopify/`):
OAuth app install, full + incremental sync of products, orders, customers and
inventory levels, and webhooks for live updates. Meta, GA4, TikTok and Google
Ads adapters are **not** implemented yet — the provider enum and adapter
registry are extensible, but only `shopify` exists.

## OAuth

1. `connect` validates the shop domain (`^[a-z0-9][a-z0-9-]{0,62}\.myshopify\.com$`,
   host extracted before validation — a redirect URL is never accepted).
2. `build_authorize_url` builds the standard Shopify authorization URL with
   the scopes `read_products`, `read_orders`, `read_customers`,
   `read_inventory`, `unauthenticated_read_product_listings`.
3. On callback, `exchange_code` posts the code to
   `POST /admin/oauth/access_token` (offline access token) and `fetch_shop`
   confirms the token + reads `currency` into `provider_metadata`.

Configuration: `SHOPIFY_CLIENT_ID`, `SHOPIFY_CLIENT_SECRET`,
`SHOPIFY_REDIRECT_URI` (`src/core/config.py`).

## Sync resources

| Resource | REST endpoint | Canonical destination |
| --- | --- | --- |
| products | `GET /admin/api/2026-01/products.json` | `products`, `product_prices` (lowest variant price = anchor) |
| orders | `GET /orders.json` (status=any) | `orders`, `order_items` |
| customers | `GET /customers.json` | `customers` |
| inventory | `GET /inventory_levels.json` + variant index | `inventory_snapshots` (source `shopify`, only on quantity change) |

- Products also emit per-variant inventory records; paging uses rel=next
  link headers.
- Orders: subtotal/total/shipping/discount are Shopify's own figures mapped
  as-is; the canonical total equals Shopify `total_price`; line items are
  replaced wholesale on re-sync so edits converge instead of accumulating.
- Customers normalize email to lowercase.
- The sync cursor is the last `updated_at` from the previous completed run;
  incremental jobs fetch `updated_at>cursor` in ascending order.

## Webhooks

Topics handled: `products/create|update`, `orders/create|updated|cancelled`,
`customers/create|update`, `inventory_levels/update`.

- Signature: HMAC-SHA256 of the raw body with the client secret, compared
  constant-time; verified twice (endpoint intake + worker before apply).
- The unique `(provider, external_event_id)` constraint deduplicates
  Shopify's at-least-once delivery.
- Unhandled topics (e.g. `app/uninstalled`) are acknowledged, logged, and
  skipped without failing the event.

## Client behavior

`ShopifyClient` (`client.py`):

- 30 s timeouts, no redirect following; retries on 5xx/429 up to
  `_MAX_RETRIES` with exponential backoff (honoring `Retry-After`, capped
  30 s).
- 401/403 → `ProviderAuthError` (the stored token is invalid — surfaced to
  operators, never the token); other 4xx → `ProviderError` (bounded
  response snippet in the message, never headers).
- Money parsing (`ProductionMoney` in the mapper): Shopify sends prices as
  strings; they become `Decimal` in the mapper only — invalid values raise
  `ProviderDataError`, which the worker records as a partial sync instead of
  crashing.

## Error taxonomy

`src/modules/integrations/base/errors.py`:

| Error | Meaning |
| --- | --- |
| `InvalidShopDomainError` | Rejects `connect` / webhook shop spoofing (404/400 to client) |
| `ProviderAuthError` | Token rejected by Shopify → connection flagged |
| `ProviderRateLimitError` | 429 with retries exhausted |
| `ProviderDataError` | Marketplace payload/money malformed → partial sync |
| `WebhookVerificationError` | HMAC mismatch → 401, event not recorded |
| `ProviderError` | Generic provider failure (retryable) |

## Frontend

`/business/{business_id}/integrations`:

- Empty state: shop-domain form → `connect` → `auth_url` navigation.
- Connected state: store name/domain, status, product/order/customer/
  inventory counts, last sync + result, `Sync now`, `Disconnect`
  (credential revoked server-side; already-synced data stays in MarketingOS).
- Survey params `?connected=1` / `?error=connect_failed` render localized
  success/error banners; no credentials are ever exposed in the UI.
- Polling (3 s) only while a sync run is `running`.