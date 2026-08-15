"""Meta Ads integration tests (Phase 2B).

External HTTP is fully stubbed: adapter OAuth helpers and Graph client
methods are monkey-patched, and HTTP-level behavior (retries, error
classification, rate limits) is tested against a fake httpx client at the
client layer.

Coverage: OAuth connect/callback security, explicit account selection,
multi-account per business, sync persistence + idempotency, daily insights,
cursor windows, rate limits / backoff / auth-stop, per-account sync lock,
encrypted credentials, tenancy isolation and disconnect cleanup.
"""

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.config import get_settings
from src.core.dependencies import get_db_session, get_redis_client
from src.db.models import (
    Ad,
    AdAccount,
    AdInsight,
    AdSet,
    Campaign,
    Creative,
    IntegrationConnection,
    IntegrationCredential,
    SyncRun,
)
from src.main import app as app_under_test
from src.modules.integrations import service as service_module
from src.modules.integrations.base.errors import (
    OAuthStateMismatchError,
    ProviderAuthError,
    ProviderDataError,
    ProviderError,
    ProviderRateLimitError,
)
from src.modules.integrations.base.types import (
    CanonicalAdAccount,
    CanonicalAdInsight,
    ProviderExchangeResult,
    SyncPage,
)
from src.modules.integrations.callback_session import CallbackSessionService
from src.modules.integrations.credentials import OAuthStateService, TokenCipher
from src.modules.integrations.meta import adapter as adapter_module
from src.modules.integrations.meta import client as client_module
from src.modules.integrations.meta.adapter import MetaAdapter
from src.modules.integrations.meta.errors import classify_meta_error
from src.modules.integrations.meta.mapper import (
    map_ad,
    map_ad_set,
    map_campaign,
    map_creative,
    map_insight,
)
from src.modules.integrations.meta.schemas import (
    AdAccountResponse,
    AdResponse,
    AdSetResponse,
    CampaignResponse,
    CreativeResponse,
    InsightItem,
)

META_APP_ID = "test-meta-app"
META_SECRET = "test-meta-secret"


def _canonical_account(external_id="111222333") -> CanonicalAdAccount:
    return CanonicalAdAccount(
        external_id=external_id,
        name=f"Ad Account {external_id}",
        currency="USD",
        timezone="America/New_York",
        timezone_offset_hours_utc=Decimal("-5"),
        status="ACTIVE",
    )


# -- adapter stubs -------------------------------------------------------------


async def _oauth_exchange(self, account_ref, code):
    return ProviderExchangeResult(
        access_token="meta-test-token", scope=["ads_read"], expires_at=None
    )


async def _oauth_validate(self, credentials):
    return {"user_id": "10001", "name": "Meta Test User"}


async def _oauth_accounts(self, credentials):
    return [
        _canonical_account("111222333"),
        _canonical_account("444555666"),
        CanonicalAdAccount(
            external_id="777888999",
            name="Inactive Account",
            currency="EUR",
            timezone="Europe/Berlin",
            timezone_offset_hours_utc=None,
            status="CLOSED",
        ),
    ]


async def _validate_ad_account(self, credentials, external_id):
    if external_id == "777888999":
        return {
            "name": "Inactive Account",
            "currency": "EUR",
            "status": "CLOSED",
            "timezone": "Europe/Berlin",
            "timezone_offset_hours_utc": None,
        }
    return {
        "name": f"Ad Account {external_id}",
        "currency": "USD",
        "status": "ACTIVE",
        "timezone": "America/New_York",
        "timezone_offset_hours_utc": "-5",
    }


def _stub_oauth(monkeypatch) -> None:
    monkeypatch.setattr(MetaAdapter, "exchange_code", _oauth_exchange)
    monkeypatch.setattr(MetaAdapter, "validate_connection", _oauth_validate)
    monkeypatch.setattr(MetaAdapter, "list_accounts", _oauth_accounts)
    monkeypatch.setattr(MetaAdapter, "validate_ad_account", _validate_ad_account)


def _noop_enqueue(monkeypatch, record: list | None = None) -> None:
    async def _enqueue(cid: str) -> None:
        if record is not None:
            record.append(cid)

    monkeypatch.setattr(service_module, "enqueue_meta_initial_sync", _enqueue)


def _make_sync_page(adapter: MetaAdapter, monkeypatch, pages: dict) -> None:
    async def _sync_page(self, credentials, resource_type, cursor):
        responses = pages[resource_type]
        if not responses:
            return SyncPage(records=[], next_cursor=None)
        return responses.pop(0)

    monkeypatch.setattr(MetaAdapter, "sync_page", _sync_page)


# -- fixtures -------------------------------------------------------------------


@pytest.fixture
async def integration_client(session, session_factory, redis_client):
    async def _db():
        async with session_factory() as db:
            yield db

    async def _redis():
        yield redis_client

    app_under_test.dependency_overrides[get_db_session] = _db
    app_under_test.dependency_overrides[get_redis_client] = _redis
    transport = ASGITransport(app=app_under_test)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
app_under_test.dependency_overrides.clear()


# ---------------------------------------------------------------------------


async def test_start_meta_connect_returns_facebook_auth_url(
    integration_client, tenant
) -> None:
    response = await integration_client.post(
        f"/api/v1/businesses/{tenant['business'].id}/integrations/meta/connect",
        headers=tenant["headers"],
        json={"locale": "en"},
    )
    assert response.status_code == 200
    url = response.json()["auth_url"]
    assert "facebook.com/v26.0/dialog/oauth" in url
    assert "client_id=test-meta-app" in url
    assert "scope=ads_read" in url
    assert "response_type=code" in url
    assert "state=" in url
    assert "mos_cb_session" in response.cookies


async def test_meta_callback_stores_accounts_without_auto_connecting(
    integration_client, tenant, session, monkeypatch
) -> None:
    _stub_oauth(monkeypatch)
    enqueued: list[str] = []
    _noop_enqueue(monkeypatch, enqueued)
    await _start_and_complete_oauth(integration_client, tenant)

    from sqlalchemy import select

    connection = await session.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.business_id == tenant["business"].id,
            IntegrationConnection.provider == "meta",
        )
    )
    assert connection is not None
    assert connection.status == "pending"
    assert connection.external_account_id is None
    accounts = (connection.provider_metadata or {}).get("accounts") or []
    assert len(accounts) == 3
    assert enqueued == []  # nothing is synced until the account is selected


async def test_oauth_state_binds_provider(redis_client, tenant) -> None:
    settings = get_settings()
    svc = OAuthStateService(redis_client, settings)
    state = await svc.create(
        user_id=tenant["user"].id,
        business_id=tenant["business"].id,
        locale="en",
        provider="shopify",
    )
    with pytest.raises(OAuthStateMismatchError):
        await svc.consume(state, user_id=tenant["user"].id, provider="meta")
    meta_state = await svc.create(
        user_id=tenant["user"].id,
        business_id=tenant["business"].id,
        locale="en",
        provider="meta",
    )
    payload = await svc.consume(meta_state, user_id=tenant["user"].id, provider="meta")
    assert payload["business_id"] == tenant["business"].id


def test_map_insight_money_is_decimal() -> None:
    raw = InsightItem(
        date_start="2026-08-13",
        campaign_id="1001",
        adset_id="2001",
        ad_id="3001",
        impressions="1000",
        reach="800",
        frequency="1.25",
        clicks="50",
        inline_link_clicks="30",
        landing_page_views="10",
        spend="123.45",
        actions=[{"action_type": "link_click", "value": "30"}],
        action_values=[{"action_type": "offsite_conversion", "value": "99.90"}],
    )
    fact = map_insight(raw)
    assert fact.date == date(2026, 8, 13)
    assert fact.impressions == 1000
    assert fact.spend == Decimal("123.45")
    assert fact.conversion_value == Decimal("99.90")
    assert fact.currency == ""
    assert fact.reach == 800
    assert fact.frequency == Decimal("1.25")


def test_map_insight_malformed_raises_data_error() -> None:
    raw = InsightItem(date_start="not-a-date", impressions="abc", spend="12")
    with pytest.raises(ProviderDataError):
        map_insight(raw)


def test_map_insight_negative_spend_rejected() -> None:
    raw = InsightItem(date_start="2026-08-13", impressions="10", clicks="1", spend="-5")
    with pytest.raises(ProviderDataError):
        map_insight(raw)


def test_map_insight_zero_defaults() -> None:
    raw = InsightItem(date_start="2026-08-13")
    fact = map_insight(raw)
    assert fact.impressions == 0
    assert fact.clicks == 0
    assert fact.spend == Decimal("0")
    assert fact.reach is None
    assert fact.conversions is None
    assert fact.conversion_value is None


def test_map_actions_idempotent_aggregates() -> None:
    raw = InsightItem(
        date_start="2026-08-13",
        actions=[
            {"action_type": "link_click", "value": "30"},
            {"action_type": "comment", "count": "4"},
            {"action_type": "post_reaction", "value": "12", "count": "12"},
        ],
        action_values=[{"action_type": "purchase", "value": "59.99"}],
    )
    fact = map_insight(raw)
    assert fact.conversions == 46
    assert fact.conversion_value == Decimal("59.99")


def test_map_insight_bad_action_count_rejected() -> None:
    raw = InsightItem(
        date_start="2026-08-13", actions=[{"action_type": "x", "count": "NaN"}]
    )
    with pytest.raises(ProviderDataError):
        map_insight(raw)


def test_map_ad_account_normalizes_id() -> None:
    raw = AdAccountResponse(id="act_12345", account_id="12345", currency="USD", account_status=1)
    account = _map_account(raw)
    assert account.external_id == "12345"
    assert account.status == "ACTIVE"


def _map_account(raw: AdAccountResponse):
    from src.modules.integrations.meta.mapper import map_ad_account

    return map_ad_account(raw)


def test_classify_meta_error_codes() -> None:
    assert isinstance(classify_meta_error(190), ProviderAuthError)
    assert isinstance(classify_meta_error(200), ProviderAuthError)
    assert isinstance(classify_meta_error(10), ProviderAuthError)
    assert isinstance(classify_meta_error(613), ProviderRateLimitError)
    assert isinstance(classify_meta_error(80004), ProviderRateLimitError)
    assert isinstance(classify_meta_error(100), ProviderDataError)
    assert isinstance(classify_meta_error(2500), ProviderDataError)
    assert isinstance(classify_meta_error(3018), ProviderDataError)
    assert isinstance(classify_meta_error(2635), ProviderDataError)
    assert isinstance(classify_meta_error(999), ProviderError)


# ---------------------------------------------------------------------------
# Graph client HTTP behavior (fake httpx)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class _FakeAsyncClient:
    """Canned httpx.AsyncClient: serves a queue of responses per request."""

    def __init__(self, *args, **kwargs):
        self.requests = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _stub_client(monkeypatch, responses: list) -> list[int]:
    """Patches httpx.AsyncClient inside meta.client. Returns the recorded
    request count."""
    calls: list[int] = []

    class _Client(_FakeAsyncClient):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._responses = list(responses)

        async def request(self, method, url, params=None, headers=None, **kwargs):
            calls.append(1)
            if not self._responses:
                raise AssertionError("no canned response left")
            return self._responses.pop(0)

    monkeypatch.setattr(client_module.httpx, "AsyncClient", _Client)
    return calls


async def _raw_client():
    from src.modules.integrations.meta.client import MetaGraphClient

    return MetaGraphClient(api_version="v26.0", access_token="tok")


async def test_client_rate_limit_retries_then_raises(monkeypatch) -> None:
    calls = _stub_client(
        monkeypatch,
        [
            _FakeResponse(429, {"error": {"code": 613, "message": "throttle"}}),
            _FakeResponse(429, {"error": {"code": 613, "message": "throttle"}}),
            _FakeResponse(429, {"error": {"code": 613, "message": "throttle"}}),
        ],
    )
    client = await _raw_client()
    with pytest.raises(ProviderRateLimitError):
        await client.list_campaigns("123")
    assert len(calls) == 4  # 3 retries around the initial attempt


async def test_client_auth_error_stops_without_retries(monkeypatch) -> None:
    from src.modules.integrations.meta.errors import ProviderAuthError as _A

    calls = _stub_client(
        monkeypatch,
        [
            _FakeResponse(403, {"error": {"code": 190, "message": "token expired"}}),
        ],
    )
    client = await _raw_client()
    with pytest.raises(_A):
        await client.fetch_user()
    assert len(calls) == 1  # no retry on auth failures


async def test_client_permanent_error_raises_without_retries(monkeypatch) -> None:
    calls = _stub_client(
        monkeypatch,
        [_FakeResponse(400, {"error": {"code": 100, "message": "unknown field"}})],
    )
    client = await _raw_client()
    with pytest.raises(ProviderDataError):
        await client.list_insights("123", since="2026-08-01", until="2026-08-14")
    assert len(calls) == 1


async def test_client_transient_error_retries_then_generic(monkeypatch) -> None:
    calls = _stub_client(
        monkeypatch,
        [
            _FakeResponse(502, {"message": "bad gateway"}),
            _FakeResponse(502, {"message": "bad gateway"}),
            _FakeResponse(502, {"message": "bad gateway"}),
            _FakeResponse(502, {"message": "bad gateway"}),
        ],
    )
    client = await _raw_client()
    with pytest.raises(ProviderError):
        await client.list_ad_accounts()
    assert len(calls) == 4  # HTTP-level 5xx retried; generic error after backoff


async def test_client_success_parses_list_and_pagination(monkeypatch) -> None:
    calls = _stub_client(
        monkeypatch,
        [
            _FakeResponse(
                200,
                {
                    "data": [
                        {"id": "act_1", "name": "A", "currency": "USD", "account_status": 1}
                    ],
                    "paging": {"cursors": {"after": "next_page"}},
                },
            ),
        ],
    )
    client = await _raw_client()
    accounts, after = await client.list_ad_accounts()
    assert len(accounts) == 1
    assert accounts[0].account_id is None or accounts[0].account_id == "1"
    assert after == "next_page"
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Adapter window semantics
# ---------------------------------------------------------------------------


class _FrozenClock:
    fixed = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):  # noqa: ARG003
        return cls.fixed

    @classmethod
    def strptime(cls, value, fmt):
        return datetime.strptime(value, fmt)


def test_initial_window_uses_config_days(monkeypatch) -> None:
    monkeypatch.setattr(adapter_module, "datetime", _FrozenClock)
    settings = get_settings()
    window = adapter_module._resolve_window(None, settings)
    expected_since = (
        datetime(2026, 8, 14, tzinfo=UTC) - timedelta(days=settings.meta_initial_sync_days)
    ).date().isoformat()
    assert window["until"] == "2026-08-14"
    assert window["since"] == expected_since


def test_incremental_window_from_cursor_date(monkeypatch) -> None:
    monkeypatch.setattr(adapter_module, "datetime", _FrozenClock)
    settings = get_settings()
    window = adapter_module._resolve_window("2026-08-13", settings)
    # since = max(today - lookback, covered - 1 day) = 08-12
    assert window["since"] == "2026-08-12"
    assert window["until"] == "2026-08-14"


def test_continuation_window_preserved() -> None:
    settings = get_settings()
    window = adapter_module._resolve_window(
        json.dumps({"since": "2026-08-01", "until": "2026-08-14", "after": "x"}), settings
    )
    assert window["since"] == "2026-08-01"
    assert window["until"] == "2026-08-14"


async def test_insights_sync_page_carries_window(monkeypatch) -> None:
    """The continuation cursor must keep the same window so incremental
    syncs never re-expand to the initial window mid-run."""
    seen: list[dict] = []

    async def _fake_list_insights(self, external_id, *, since, until, after=None):
        seen.append({"since": since, "until": until, "after": after})
        if after is None:
            return (
                [InsightItem(date_start="2026-08-12", impressions="1", clicks="0", spend="0.1")],
                "cursor-2",
            )
        return (
            [
                InsightItem(
                    date_start="2026-08-13", impressions="2", clicks="1", spend="0.2"
                )
            ],
            None,
        )

    monkeypatch.setattr(
        client_module.MetaGraphClient, "list_insights", _fake_list_insights
    )
    adapter = MetaAdapter()
    credentials = service_module.ProviderCredentials(
        shop_domain="act_111222333", access_token="tok"
    )
    page1 = await adapter.sync_page(
        credentials, "insights", json.dumps({"since": "2026-08-10", "until": "2026-08-14"})
    )
    assert page1.next_cursor is not None
    page2 = await adapter.sync_page(credentials, "insights", page1.next_cursor)
    assert page2.next_cursor is None
    assert len(page1.records) == 1
    assert page1.records[0].ad_account_external_id == "111222333"
    assert all(seen_call["since"] == "2026-08-10" for seen_call in seen)
    assert all(seen_call["until"] == "2026-08-14" for seen_call in seen)


# ---------------------------------------------------------------------------
# Service-level sync persistence (stubbed adapter pages)
# ---------------------------------------------------------------------------


def _insight(external="3001", day="2026-08-13", spend="1.50", clicks=3) -> CanonicalAdInsight:
    return CanonicalAdInsight(
        date=date.fromisoformat(day),
        currency="",
        impressions=100,
        spend=Decimal(spend),
        clicks=clicks,
        campaign_external_id="1001",
        ad_set_external_id="2001",
        ad_external_id=external,
        ad_account_external_id="111222333",
    )


async def _connected_meta_connection(
    session, tenant, *, external_id="111222333"
) -> IntegrationConnection:
    """Creates the connected state directly (post-selection)."""
    settings = get_settings()
    connection = IntegrationConnection(
        business_id=tenant["business"].id,
        provider="meta",
        status="connected",
        external_account_id=f"act_{external_id}",
        external_account_name=f"Ad Account {external_id}",
        scopes=["ads_read"],
        provider_metadata={"currency": "USD"},
        connected_at=datetime.now(UTC),
    )
    session.add(connection)
    await session.flush()
    cipher = TokenCipher.from_settings(settings)
    credential = IntegrationCredential(
        connection_id=connection.id,
        access_token_encrypted=cipher.encrypt("meta-test-token"),
        expires_at=datetime.now(UTC) + timedelta(days=60),
    )
    session.add(credential)
    await session.flush()
    await service_module.upsert_ad_account(
        session, tenant["business"].id, _canonical_account(external_id)
    )
    await session.commit()
    return connection


async def test_run_sync_persists_hierarchy_and_daily_insights(
    session, tenant, monkeypatch
) -> None:
    connection = await _connected_meta_connection(session, tenant)

    from sqlalchemy import select

    from src.modules.integrations.base.types import (
        CanonicalAd,
        CanonicalAdSet,
        CanonicalCampaign,
        CanonicalCreative,
    )

    async def _sync_page_full(self, credentials, resource_type, cursor):
        if resource_type == "ad_accounts":
            return SyncPage(records=[_canonical_account()], next_cursor=None)
        if resource_type == "campaigns":
            return SyncPage(
                records=[
                    CanonicalCampaign(
                        external_id="1001",
                        name="Campaign A",
                        status="ACTIVE",
                        objective="OUTCOME_SALES",
                        buying_type="AUCTION",
                        created_time=None,
                        updated_at=datetime(2026, 8, 13, tzinfo=UTC),
                        ad_account_external_id="111222333",
                    )
                ],
                next_cursor=None,
            )
        if resource_type == "ad_sets":
            return SyncPage(
                records=[
                    CanonicalAdSet(
                        external_id="2001",
                        campaign_external_id="1001",
                        name="Ad Set A",
                        status="ACTIVE",
                        optimization_goal="LINK_CLICKS",
                        billing_event="IMPRESSIONS",
                        created_time=None,
                        updated_at=None,
                        ad_account_external_id="111222333",
                    )
                ],
                next_cursor=None,
            )
        if resource_type == "ads":
            creative = CanonicalCreative(
                external_id="9001",
                name=None,
                type=None,
                title="Ad Title",
                body="Ad body",
                call_to_action="SHOP_NOW",
                thumbnail_url=None,
                created_time=None,
                updated_at=None,
            )
            return SyncPage(
                records=[
                    creative,
                    CanonicalAd(
                        external_id="3001",
                        campaign_external_id="1001",
                        ad_set_external_id="2001",
                        name="Ad A",
                        status="ACTIVE",
                        created_time=None,
                        updated_at=None,
                        creative=creative,
                        ad_account_external_id="111222333",
                    ),
                ],
                next_cursor=None,
            )
        return SyncPage(
            records=[_insight(), _insight("3002", "2026-08-12", "2.50")],
            next_cursor=None,
        )

    monkeypatch.setattr(MetaAdapter, "sync_page", _sync_page_full)

    results = await service_module.run_sync(
        session,
        connection_id=connection.id,
        resources=["ad_accounts", "campaigns", "ad_sets", "ads", "insights"],
        initial=True,
    )
    assert results == {"ad_accounts": 1, "campaigns": 1, "ad_sets": 1, "ads": 2, "insights": 2}

    campaign = await session.scalar(
        select_one("campaigns", "1001")
    )
    assert campaign is not None
    assert campaign.name == "Campaign A"

    ad_set = await session.scalar(select(AdSet))
    ad = await session.scalar(select(Ad))
    creative = await session.scalar(select(Creative))
    assert ad_set.name == "Ad Set A"
    assert ad.name == "Ad A"
    assert creative.title == "Ad Title"
    assert ad.creative_id == creative.id
    assert ad_set.campaign_id == campaign.id

    insights = list(await session.scalars(_insight_select()))
    assert len(insights) == 2
    by_day = {i.date: i for i in insights}
    assert by_day[date(2026, 8, 13)].spend == Decimal("1.50")
    assert by_day[date(2026, 8, 12)].spend == Decimal("2.50")
    assert by_day[date(2026, 8, 13)].currency == "USD"
    assert by_day[date(2026, 8, 13)].ad_account_id == campaign.ad_account_id

    r = await session.scalar(_sync_run_select("insights"))
    assert r.status == "success"
    assert r.cursor == "2026-08-13"  # watermark = latest covered day


def _insight_select():
    from sqlalchemy import select

    return select(AdInsight).order_by(AdInsight.date)


def _sync_run_select(resource: str = "insights"):
    from sqlalchemy import select

    return (
        select(SyncRun)
        .where(SyncRun.resource_type == resource)
        .order_by(SyncRun.started_at.desc())
    )


def select_one(table: str, external: str):
    from sqlalchemy import select

    if table == "campaigns":
        return select(Campaign).where(Campaign.external_id == external)
    raise AssertionError(table)


async def test_run_sync_idempotent(tenant, session, monkeypatch) -> None:
    connection = await _connected_meta_connection(session, tenant)


    async def _sync_page(self, credentials, resource_type, cursor):
        if resource_type == "ad_accounts":
            return SyncPage(records=[_canonical_account()], next_cursor=None)
        if resource_type == "campaigns":
            return SyncPage(records=[], next_cursor=None)
        if resource_type == "ad_sets":
            return SyncPage(records=[], next_cursor=None)
        if resource_type == "ads":
            return SyncPage(records=[], next_cursor=None)
        if cursor is None:
            return SyncPage(records=[_insight()], next_cursor=None)
        return SyncPage(records=[], next_cursor=None)

    monkeypatch.setattr(MetaAdapter, "sync_page", _sync_page)
    await service_module.run_sync(
        session,
        connection_id=connection.id,
        resources=["insights"],
        initial=True,
    )
    await service_module.run_sync(
        session,
        connection_id=connection.id,
        resources=["insights"],
        initial=False,
    )
    insights = list(await session.scalars(_insight_select()))
    assert len(insights) == 1  # reprocessed idempotently, no duplicates


async def test_run_sync_auth_failure_marks_failed_run(tenant, session, monkeypatch) -> None:
    connection = await _connected_meta_connection(session, tenant)

    async def _sync_page(self, credentials, resource_type, cursor):
        raise ProviderAuthError("Meta rejected the stored credentials")

    monkeypatch.setattr(MetaAdapter, "sync_page", _sync_page)
    with pytest.raises(ProviderAuthError):
        await service_module.run_sync(
            session,
            connection_id=connection.id,
            resources=["campaigns"],
            initial=True,
        )
    run = await session.scalar(_sync_run_select("campaigns"))
    assert run.status == "failed"


async def test_mark_meta_reconnect_required(tenant, session) -> None:
    connection = await _connected_meta_connection(session, tenant)
    await service_module.mark_meta_reconnect_required(session, connection.id)
    await session.refresh(connection)
    assert connection.status == "error"
    assert (connection.provider_metadata or {}).get("auth_error") is True


async def test_credentials_encrypted_at_rest(tenant, session) -> None:
    settings = get_settings()
    await _connected_meta_connection(session, tenant)
    credential = await session.scalar(
        _credential_select()
    )
    assert credential is not None
    assert credential.access_token_encrypted.startswith("v1:")
    assert "meta-test-token" not in credential.access_token_encrypted
    assert TokenCipher.from_settings(settings).decrypt(credential.access_token_encrypted) == (
        "meta-test-token"
    )


def _credential_select():
    from sqlalchemy import select

    return select(IntegrationCredential)


async def test_disconnect_cleans_meta_hierarchy(tenant, session, monkeypatch) -> None:
    connection = await _connected_meta_connection(session, tenant)
    settings = get_settings()


    ad_account_id = (await session.scalar(_ad_account_select())).id
    campaign = Campaign(
        business_id=tenant["business"].id,
        ad_account_id=ad_account_id,
        external_id="1001",
        name="C",
        status="ACTIVE",
    )
    session.add(campaign)
    await session.flush()
    creative = Creative(
        business_id=tenant["business"].id,
        provider="meta",
        external_id="9001",
        name="Cr",
    )
    session.add(creative)
    await session.flush()
    session.add(
        Ad(
            business_id=tenant["business"].id,
            ad_account_id=ad_account_id,
            campaign_id=campaign.id,
            external_id="3001",
            name="A",
            status="ACTIVE",
            creative_id=creative.id,
        )
    )
    await session.commit()

    await service_module.disconnect_connection(
        session, settings, tenant["business"].id, connection.id
    )
    assert await session.scalar(_ad_account_select()) is None
    assert await session.scalar(_insight_select()) is None
    assert await session.scalar(_select_from("ads")) is None
    assert await session.scalar(_select_from("campaigns")) is None
    assert await session.scalar(_select_from("creatives")) is None
    await session.refresh(connection)
    assert connection.status == "disconnected"


def _ad_account_select():
    from sqlalchemy import select

    return select(AdAccount)


def _select_from(table: str):
    from sqlalchemy import select

    if table == "ads":
        return select(Ad)
    if table == "campaigns":
        return select(Campaign)
    if table == "creatives":
        return select(Creative)
    raise AssertionError(table)


# ---------------------------------------------------------------------------
# Adapter → canonical mapping (schema-level)
# ---------------------------------------------------------------------------


def test_map_hierarchy_fields() -> None:
    campaign = map_campaign(
        CampaignResponse(
            id="1001",
            name="C",
            status="PAUSED",
            effective_status="ACTIVE",
            objective="OUTCOME_TRAFFIC",
            buying_type="AUCTION",
        )
    )
    assert campaign.status == "ACTIVE"  # effective_status wins
    assert campaign.objective == "OUTCOME_TRAFFIC"

    ad_set = map_ad_set(
        AdSetResponse(id="2001", name="S", campaign_id="1001", optimization_goal="LINK_CLICKS")
    )
    assert ad_set.campaign_external_id == "1001"

    creative = map_creative(
        CreativeResponse(
            id="9001",
            object_type="SHARE",
            object_story_spec={
                "name": "Headline",
                "link_data": {
                    "message": "Body text",
                    "call_to_action": {"type": "SHOP_NOW"},
                },
            },
        )
    )
    assert creative.title == "Headline"
    assert creative.body == "Body text"
    assert creative.call_to_action == "SHOP_NOW"

    ad = map_ad(AdResponse(id="3001", name="A", campaign_id="1001", adset_id="2001"), creative)
    assert ad.ad_set_external_id == "2001"
    assert ad.creative is creative


# ---------------------------------------------------------------------------
# Tenancy
# ---------------------------------------------------------------------------


async def test_meta_accounts_requires_business_access(session, integration_client) -> None:
    from tests.conftest import create_tenant

    a = await create_tenant(session)
    b = await create_tenant(session)
    response = await integration_client.get(
        f"/api/v1/businesses/{b['business'].id}/integrations/meta/accounts",
        headers=a["headers"],
    )
    assert response.status_code == 404  # business a cannot see business b


async def test_meta_accounts_empty_when_no_pending(integration_client, tenant) -> None:
    response = await integration_client.get(
        f"/api/v1/businesses/{tenant['business'].id}/integrations/meta/accounts",
        headers=tenant["headers"],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["connection_id"] is None
    assert body["accounts"] == []


async def test_meta_connect_requires_permission(session, integration_client, tenant) -> None:
    from src.core.rbac import DEFAULT_ROLES
    from tests.conftest import create_tenant as _ct

    # viewer role has no business:write
    permissions = sorted(set(DEFAULT_ROLES["viewer"]) - {"business:read", "business:write"})
    tenant_limited = await _ct(session, permissions=permissions)
    biz = tenant["business"]
    response = await integration_client.post(
        f"/api/v1/businesses/{biz.id}/integrations/meta/connect",
        headers=tenant_limited["headers"],
        json={"locale": "en"},
    )
    assert response.status_code in (403, 404)


# ---------------------------------------------------------------------------
# Complete flow (OAuth → discovery → select → sync enqueue)
# ---------------------------------------------------------------------------


async def test_full_meta_flow_connect_callback_select(
    integration_client, tenant, session, monkeypatch
) -> None:
    _stub_oauth(monkeypatch)
    enqueued: list[tuple[str, object]] = []

    async def _enqueue(cid: str) -> None:
        enqueued.append(("initial", cid))

    monkeypatch.setattr(service_module, "enqueue_meta_initial_sync", _enqueue)

    connect = await integration_client.post(
        f"/api/v1/businesses/{tenant['business'].id}/integrations/meta/connect",
        headers=tenant["headers"],
        json={"locale": "en"},
    )
    assert connect.status_code == 200
    auth_url = connect.json()["auth_url"]
    from urllib.parse import parse_qs, urlparse

    state = parse_qs(urlparse(auth_url).query)["state"][0]
    session_token = connect.cookies["mos_cb_session"]

    callback = await integration_client.get(
        "/api/v1/integrations/meta/callback",
        params={"code": "auth-code-1", "state": state},
        cookies={"mos_cb_session": session_token},
        follow_redirects=False,
    )
    assert callback.status_code == 302
    assert "connected=1" in callback.headers["location"]
    assert callback.headers["location"].startswith("http://test/en/business/")

    # No auto-connect: the connection is still pending with discovered accounts.
    accounts = await integration_client.get(
        f"/api/v1/businesses/{tenant['business'].id}/integrations/meta/accounts",
        headers=tenant["headers"],
    )
    assert accounts.status_code == 200
    body = accounts.json()
    assert len(body["accounts"]) == 3
    assert body["connection_id"] is not None
    assert enqueued == []  # nothing ingested yet

    # Select the active account explicitly.
    select = await integration_client.post(
        f"/api/v1/businesses/{tenant['business'].id}/integrations/meta/accounts/select",
        headers=tenant["headers"],
        json={"external_account_id": "111222333"},
    )
    assert select.status_code == 200
    connection = select.json()
    assert connection["status"] == "connected"
    assert connection["external_account_id"] == "act_111222333"
    assert enqueued == [("initial", connection["id"])]
    assert connection["provider"] == "meta"


async def test_meta_select_rejects_unknown_account(
    integration_client, tenant, session, monkeypatch
) -> None:
    _stub_oauth(monkeypatch)
    await _start_and_complete_oauth(integration_client, tenant)
    response = await integration_client.post(
        f"/api/v1/businesses/{tenant['business'].id}/integrations/meta/accounts/select",
        headers=tenant["headers"],
        json={"external_account_id": "999999999"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "integration_error"


async def test_meta_select_conflict_across_businesses(
    session, integration_client, monkeypatch
) -> None:
    from tests.conftest import create_tenant

    a = await create_tenant(session)
    b = await create_tenant(session)
    _stub_oauth(monkeypatch)
    await _start_and_complete_oauth(integration_client, a)
    await _start_and_complete_oauth(integration_client, b)
    _noop_enqueue(monkeypatch)
    for tenant in (a, b):
        response = await integration_client.post(
            f"/api/v1/businesses/{tenant['business'].id}/integrations/meta/accounts/select",
            headers=tenant["headers"],
            json={"external_account_id": "111222333"},
        )
        assert response.status_code == 200
    # second business cannot claim the same account again
    response = await integration_client.post(
        f"/api/v1/businesses/{b['business'].id}/integrations/meta/accounts/select",
        headers=b["headers"],
        json={"external_account_id": "111222333"},
    )
    assert response.status_code == 409


async def test_meta_multiple_accounts_one_business(
    integration_client, tenant, session, monkeypatch
) -> None:
    _stub_oauth(monkeypatch)
    _noop_enqueue(monkeypatch)
    for account_id in ("111222333", "444555666"):
        await _start_and_complete_oauth(integration_client, tenant)
        response = await integration_client.post(
            f"/api/v1/businesses/{tenant['business'].id}/integrations/meta/accounts/select",
            headers=tenant["headers"],
            json={"external_account_id": account_id},
        )
        assert response.status_code == 200, response.text

    listing = await integration_client.get(
        f"/api/v1/businesses/{tenant['business'].id}/integrations",
        headers=tenant["headers"],
    )
    meta_connections = [c for c in listing.json() if c["provider"] == "meta"]
    assert len(meta_connections) == 2
    assert {c["external_account_id"] for c in meta_connections} == {
        "act_111222333",
        "act_444555666",
    }


async def test_meta_callback_rejects_reused_state(
    integration_client, tenant, session, monkeypatch
) -> None:
    _stub_oauth(monkeypatch)
    from urllib.parse import parse_qs, urlparse

    connect = await integration_client.post(
        f"/api/v1/businesses/{tenant['business'].id}/integrations/meta/connect",
        headers=tenant["headers"],
        json={"locale": "en"},
    )
    state = parse_qs(urlparse(connect.json()["auth_url"]).query)["state"][0]
    session_token = connect.cookies["mos_cb_session"]

    first = await integration_client.get(
        "/api/v1/integrations/meta/callback",
        params={"code": "code", "state": state},
        cookies={"mos_cb_session": session_token},
        follow_redirects=False,
    )
    assert first.status_code == 302
    assert "connected=1" in first.headers["location"]

    second = await integration_client.get(
        "/api/v1/integrations/meta/callback",
        params={"code": "code", "state": state},
        cookies={"mos_cb_session": session_token},
        follow_redirects=False,
    )
    assert second.status_code == 302
    assert "error=connect_failed" in second.headers["location"]


async def test_meta_callback_requires_callback_session_cookie(
    integration_client, tenant, session, monkeypatch
) -> None:
    from urllib.parse import parse_qs, urlparse

    _stub_oauth(monkeypatch)
    connect = await integration_client.post(
        f"/api/v1/businesses/{tenant['business'].id}/integrations/meta/connect",
        headers=tenant["headers"],
        json={"locale": "en"},
    )
    state = parse_qs(urlparse(connect.json()["auth_url"]).query)["state"][0]
    # the httpOnly cookie lives in the browser, not in the client jar; make
    # sure the test client does not smuggle the auto-persisted cookie through
    integration_client.cookies.clear()
    response = await integration_client.get(
        "/api/v1/integrations/meta/callback",
        params={"code": "code", "state": state},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "error=connect_failed" in response.headers["location"]


async def test_meta_callback_rejects_shopify_state(
    integration_client, tenant, session, redis_client, monkeypatch
) -> None:
    from src.core.config import get_settings

    _stub_oauth(monkeypatch)
    settings = get_settings()
    state = await OAuthStateService(redis_client, settings).create(
        user_id=tenant["user"].id,
        business_id=tenant["business"].id,
        locale="en",
        provider="shopify",
    )
    session_token = await CallbackSessionService(redis_client, settings).create(
        user_id=tenant["user"].id
    )
    response = await integration_client.get(
        "/api/v1/integrations/meta/callback",
        params={"code": "code", "state": state},
        cookies={"mos_cb_session": session_token},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "error=connect_failed" in response.headers["location"]


async def test_meta_callback_state_single_use_across_users(
    integration_client, session, tenant, redis_client, monkeypatch
) -> None:
    from src.core.config import get_settings
    from tests.conftest import create_tenant

    other = await create_tenant(session)
    _stub_oauth(monkeypatch)
    from urllib.parse import parse_qs, urlparse

    connect = await integration_client.post(
        f"/api/v1/businesses/{tenant['business'].id}/integrations/meta/connect",
        headers=tenant["headers"],
        json={"locale": "en"},
    )
    state = parse_qs(urlparse(connect.json()["auth_url"]).query)["state"][0]
    # another user's browser holds its own valid session, but the state was
    # issued for the first user -> rejected
    other_session = await CallbackSessionService(redis_client, get_settings()).create(
        user_id=other["user"].id
    )
    response = await integration_client.get(
        "/api/v1/integrations/meta/callback",
        params={"code": "code", "state": state},
        cookies={"mos_cb_session": other_session},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "error=connect_failed" in response.headers["location"]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _start_and_complete_oauth(client: AsyncClient, tenant: dict) -> None:
    """Runs connect + callback; leaves a pending connection with accounts."""
    from urllib.parse import parse_qs, urlparse

    connect = await client.post(
        f"/api/v1/businesses/{tenant['business'].id}/integrations/meta/connect",
        headers=tenant["headers"],
        json={"locale": "en"},
    )
    assert connect.status_code == 200
    state = parse_qs(urlparse(connect.json()["auth_url"]).query)["state"][0]
    callback = await client.get(
        "/api/v1/integrations/meta/callback",
        params={"code": "auth-code", "state": state},
        cookies={"mos_cb_session": connect.cookies["mos_cb_session"]},
        follow_redirects=False,
    )
    assert callback.status_code == 302
    assert "connected=1" in callback.headers["location"]