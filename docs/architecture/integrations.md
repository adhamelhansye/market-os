# Integrations

## Overview

The integration core connects MarketingOS to external marketing and sales
providers behind a single adapter interface. All provider-specific code lives
in provider adapters; core business logic only ever talks to `IntegrationAdapter`
(`src/modules/integrations/base/protocol.py`).

Endpoints (all under `/api/v1`, tenant + permission checked server-side):

```
GET    /businesses/{business_id}/integrations                     → connections + counts
GET    /businesses/{business_id}/integrations/{connection_id}     → single connection
POST   /businesses/{business_id}/integrations/shopify/connect     → { auth_url } (OAuth start)
GET    /integrations/shopify/callback                             → 302 to frontend
POST   /businesses/{business_id}/integrations/{connection_id}/sync        → enqueue sync
POST   /businesses/{business_id}/integrations/{connection_id}/disconnect  → revoke + clear
POST   /integrations/shopify/webhook                              → HMAC-verified event intake
```

Meta Ads endpoints (see `meta.md` for the full provider doc):

```
POST   /businesses/{business_id}/integrations/meta/connect        → { auth_url } (OAuth start)
GET    /integrations/meta/callback                                → 302 to frontend
GET    /businesses/{business_id}/integrations/meta/accounts       → discovered ad accounts
POST   /businesses/{business_id}/integrations/meta/accounts/select → connect one account
```

Reads require `business:read`, mutations require `business:write`.

## Adapter protocol

`IntegrationAdapter` is the contract every provider implements:

- `resource_types` — resource kinds the provider supports (e.g.
  `products`, `orders`, `customers`, `inventory`).
- `validate_connect_input(raw) -> str` — validates/deduplicates the connect
  identifier (e.g. strips a Shopify URL down to `*.myshopify.com`).
- `build_authorize_url(shop, state) -> str` and `exchange_code(shop, code)`
  — OAuth authorization + token exchange (`ProviderExchangeResult`:
  access token, scopes, expiry; never logged).
- `validate_connection(credentials) -> dict` — confirms the token works and
  returns identity/currency metadata.
- `sync_page(credentials, resource, cursor) -> SyncPage` — one page of
  canonical records + next cursor.
- `verify_webhook(raw_body, headers)` / `resolve_webhook_topic(...)` /
  `resolve_webhook(topic, raw_body)` — webhook signature check and
  deserialization into canonical records.
- `disconnect(credentials)` / `health_check(credentials)`.

`src/modules/integrations/registry.py` maps `provider` string → adapter
instance; core never imports a provider module directly.

## Credentials

- Provider tokens are encrypted at rest with AES-256-GCM
  (`credentials.py`, `TokenCipher`): key material is derived from
  `ENCRYPTION_KEY` via HKDF-SHA256; ciphertext is versioned
  (`v1:...`), so rotation only requires decoding old versions.
- Credentials rows are tied 1:1 to a connection
  (`integration_credentials.connection_id` unique, cascade delete).
- Decryption happens only inside provider calls; encrypted blobs are never
  returned by APIs and never logged.
- OAuth state (`OAuthStateService`) is a server-generated random token
  stored in Redis (`oauth:state:{state}`) bound to the user + business +
  locale, single-use via `GETDEL`.

## Connect flow

1. `POST .../shopify/connect` validates the shop domain server-side,
   upserts a `pending` connection, and responds with `{ auth_url }` plus an
   httpOnly `SameSite=Lax` callback session cookie (`mos_cb_session`,
   `oauth:cb-session:{token}`, 15 min TTL).
2. Shopify redirects the browser to the callback, which:
   - resolves the user from the callback session cookie (never trusts query
     params); the state is **not** consumed if the cookie is invalid;
   - consumes the single-use state and re-checks access to the bound
     business (RBAC runs again here, not just at connect time);
   - exchanges the code, validates the token, stores the credential and
     marks the connection `connected` with the store currency;
   - enqueues `shopify_initial_sync` and 302-redirects to the frontend
     (`.../integrations?connected=1`, or `?error=connect_failed`).

The same shop cannot be connected to two businesses: the unique credential
insert triggers `ConflictError`.

## Sync

- `request_sync` enqueues `shopify_incremental_sync` (explicit `resources`
  honored even on a first sync; `None` on a never-synced connection means
  the provider's full initial set).
- Jobs (`src/core/worker.py`, arq) run per resource: a `sync_runs` row moves
  `pending → running → success | partial | failed`; malformed records are
  skipped and counted, so a bad row never aborts a store-wide sync.
- The next run's cursor is the newest record `updated_at` from the last
  **completed** run — failed runs never advance the watermark.
- Retries: network/rate-limit failures retry with exponential backoff
  (bounded `max_tries`); a unique-constraint race on upsert triggers one
  in-place retry (`persistence.py`, `_persist_with_retry`).
- Idempotency anchor is the database schema itself:
  `unique(business_id, external_id)` for products/customers,
  `unique(business_id, source, external_id)` for orders, `inventory_snapshots`
  written only when the quantity actually changed.
- Money is `NUMERIC`/`Decimal` everywhere; anchors are provider currency,
  Shopify prices go to `product_prices` (append-only on change, COGS never
  auto-written).

## Webhooks

- The endpoint verifies the HMAC over the **raw bytes** before parsing, then
  records a `webhook_events` row. `(provider, external_event_id)` is unique:
  a duplicate delivery is a no-op.
- The worker atomically claims the event (`received → processing` via
  `UPDATE ... WHERE status = 'received'`), re-verifies the signature against
  the exact original bytes (stored base64 in Redis,
  `webhook:payload:{id}` + `webhook:meta:{id}`, 24 h TTL), then applies the
  same canonical persistence as sync.
- Unhandled topics are acknowledged and dropped (recorded, not failed).

## Data model

`integration_connections` (provider, status, store identity, currency,
sync watermark) → `integration_credentials` (encrypted token) — both
business-scoped, UUID keys, UTC timestamps. `sync_runs` and `webhook_events`
are audit/operator records; canonical business data lands in the existing
`products`, `orders`, `customers`, `inventory_snapshots`, `order_items`,
`product_prices` tables with `external_id`/`external_source` set.

## Operator notes

- The worker container runs `arq src.core.worker.WorkerSettings`; job names
  are the contract between `jobs.py` and the worker.
- Rate-limit and transient failures use arq `Retry` with exponential
  backoff; a job that exhausts retries leaves `failed` state in `sync_runs`.
- All worker log lines are structured; tokens and secrets never appear.