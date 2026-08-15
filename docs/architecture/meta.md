# Meta Ads integration

## Overview

Meta Ads is the second provider behind the shared `IntegrationAdapter`
interface (see `integrations.md`). MarketingOS connects to Meta with the
**official OAuth 2.0 dialog** and reads ad data through the **Graph API**
(`graph.facebook.com`, `meta_graph_api_version`, default `v26.0`) and the
**Marketing API**. The integration is strictly **read-only**:

- the OAuth scope is exactly `ads_read` — MarketingOS can never post,
  modify or delete anything in the ad account;
- there are no webhooks and no write calls of any kind;
- no numbers are invented: every metric comes from Meta's `insights`
  endpoint and is stored as-is.

## Connect flow

1. `POST /businesses/{business_id}/integrations/meta/connect` needs no user
   input (unlike Shopify there is no domain): it creates the OAuth state,
   sends the httpOnly `mos_cb_session` callback cookie, and returns
   `{ auth_url }` pointing at the official Facebook dialog (`locale` from
   the frontend is forwarded so the dialog matches the user language).
2. The user approves in the Facebook dialog — only the `ads_read`
   permission is requested.
3. `GET /integrations/meta/callback` validates the same way as the Shopify
   callback: user from the cookie, single-use Redis state bound to
   user + business + provider, RBAC re-check, then token exchange. The
   state is provider-bound (`oauth:state:{state}` stores the provider), so
   a state minted for Shopify can never authorize a Meta callback or vice
   versa.
4. The callback **does not auto-connect**: it stores a `pending` connection
   whose `provider_metadata` carries the server-side list of ad accounts
   that the granted token can read (queried via
   `GET /act_{id}`/`/me/adaccounts` with `is_paginated=true`,
   `AMOUNT_INITIAL_PER_PAGE=100`).
5. `GET .../integrations/meta/accounts` returns that discovered list
   (id, name, currency, status, timezone).
6. `POST .../integrations/meta/accounts/select` connects **exactly one
   explicitly chosen** account (the choice must be in the server-side list
   — a client can only pick what the authorization actually granted) and
   enqueues the initial sync.
7. Success lands on `.../integrations?connected=1`; failures on
   `.../dashboard?error=connect_failed`. The api never stores/returns the
   access token.

## Identities and access

- One `integration_connections` row per selected ad account: a business
  can connect several ad accounts.
- `connection.external_account_id` = `act_{numeric_id}`; the numeric id is
  stored on every canonical row (`ad_account_external_id`).
- The same ad account can only be connected to one business:
  `integration_connections` has a partial unique index on
  (business_id, provider, external_account_id) (migration 0005). A wrong
  account pick across businesses surfaces as a `ConflictError`-style 409.
- The access token is encrypted at rest with AES-256-GCM like Shopify
  (`credentials.py`, `v1:` prefix), scoped/permission-checked on every
  request, and cached per token in `MetaGraphClient`.
- `business:read` gates reads, `business:write` gates connect/select/sync/
  disconnect. Tenancy and permission checks run server-side on every call;
  the frontend can only start flows, never choose what to sync.

## Sync

`resource_types`: `ad_accounts, campaigns, ad_sets, ads, insights`.

- Initial sync downloads the account's own identity first, then the
  canonical objects, then daily insights.
- Date windowing:
  - initial: last `meta_initial_sync_days` (default 90) days, capped at
    the API's 37-month `time_range` limit;
  - incremental: `max(today - meta_incremental_lookback_days, covered - 1
    day)` so the daily rollup overlaps idempotently and catches late
    attribution.
- Pagination with `cursors.after` through the `insights` API; one page
  holds `PAGE_SIZE` (100) records.
- Concurrency: one arq job per connection at a time, guarded by a Redis
  lock (`meta:sync:lock:{connection_id}`, 30 min TTL, Lua-based safe
  release, crash-tolerant); a concurrent job is skipped, not queued.
- Retries: rate limits and transient API errors retry with bounded
  exponential backoff (jitter ≤ 60 s, `Retry-After` honored up to 120 s,
  `max_tries` bounded); permanent errors mark the run `failed` without
  wasting retries.
- Windows and runs are recorded in `sync_runs` exactly like Shopify:
  nothing is written unless a full page validated, and per-record
  malformed data is skipped and counted, never fatal.

### Error taxonomy (`meta/errors.py`)

| Family | Statuses / codes | Outcome |
| --- | --- | --- |
| Auth | 190 (and subcodes), 10, 101, 174, 200 | stop, mark connection `error`, needs re-auth |
| Rate limit | 429, 613, 80004 | bounded backoff + retry |
| Permanent/data | 3018 (date-range) + 2, 4, 17, 100, 368, 2500, 2635 | mark run `failed`, skip resource |
| Transient | network, 5xx, others | exponential backoff retry |

Raw Graph API error bodies are logged at debug level only (never
`META_APP_SECRET`, tokens or user data; x-app-usage over 80% logs a
structured warning).

## Data model

| Table | Content | Uniqueness |
| --- | --- | --- |
| `ad_accounts` | connected account identity + currency (from Meta, never guessed) | (business_id, ad_account_external_id) |
| `canonical_campaigns` | campaign (name, status, budget type...) | (business_id, ad_account_external_id, external_id) |
| `canonical_ad_sets` | ad set | (business_id, ad_account_external_id, external_id) |
| `canonical_ads` | ad | (business_id, ad_account_external_id, external_id) |
| `ad_insights` | daily rows, `grain='daily'` | (business_id, ad_account_external_id, external_id, date) |

- Money is `NUMERIC`/`Decimal` everywhere; insight currency comes from the
  connected account identity and is stored with each row.
- Upserts are idempotent: re-running a window converges to the same rows,
  so the watermark (latest covered insight date) only advances on
  completed runs.

## Out of scope (why)

- **No KPIs, attribution or reconciliation**: insights are raw daily
  facts; MarketingOS computes no CPA/ROAS/attribution from them yet.
- **No posting/budget changes**: the scope is `ads_read`; any future
  "optimize" features will need a separate (write) scope and explicit
  consent.
- **No webhooks**: daily polling via the existing sync flow is used; Meta
  webhook review is unnecessary for `ads_read`.
- **No lookalike/audience targeting data**: not granted by the scope.

## Settings & setup

`.env` / compose: `META_APP_ID`, `META_APP_SECRET`, `META_REDIRECT_URI`
(`http://localhost:8000/api/v1/integrations/meta/callback` in dev),
`META_GRAPH_API_VERSION` (default `v26.0`), `META_SCOPES` (default
`ads_read`), `META_INITIAL_SYNC_DAYS` (90), `META_INCREMENTAL_LOOKBACK_DAYS`
(2). App Review requirements change with Meta policies; for development,
use the app's own admin accounts with Advanced Access for `ads_read`.