"""Meta payload → canonical data mapping.

Pure functions; validated Meta schemas in, canonical MarketingOS types out.
Money values stay numeric strings until here and become Decimal — never
float. No other module knows Meta response formats.

Insight conversions are deterministic aggregates of provider-reported
facts: `conversions` sums the count of EVERY attributed action (all action
types, per Meta's default attribution), `conversion_value` sums every
reported value. These are raw facts, NOT purchases and NOT KPIs.
"""

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from src.modules.integrations.base.errors import ProviderDataError
from src.modules.integrations.base.types import (
    CanonicalAd,
    CanonicalAdAccount,
    CanonicalAdInsight,
    CanonicalAdSet,
    CanonicalCampaign,
    CanonicalCreative,
)
from src.modules.integrations.meta.constants import ACCOUNT_STATUS_LABELS
from src.modules.integrations.meta.schemas import (
    AdAccountResponse,
    AdResponse,
    AdSetResponse,
    CampaignResponse,
    CreativeResponse,
    InsightItem,
)


def _parse_datetime(value) -> datetime | None:
    """Meta sends RFC3339-ish offsets like +0000; normalize to UTC."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except ValueError:
        return None


def _to_decimal(value, field: str) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ProviderDataError(f"Invalid numeric value in Meta field {field}") from None


def _to_int(value, field: str) -> int:
    try:
        return int(_to_decimal(value, field))
    except (InvalidOperation, TypeError, ValueError):
        raise ProviderDataError(f"Invalid integer value in Meta field {field}") from None


def _negative(decimal_value: Decimal, field: str) -> None:
    if decimal_value < 0:
        raise ProviderDataError(f"Negative value in Meta field {field}")


def _story_spec(
    spec: dict | None,
) -> tuple[str | None, str | None, str | None]:
    """Best-effort extraction from object_story_spec; nothing is invented."""
    if not isinstance(spec, dict):
        return None, None, None
    title = spec.get("name") or None
    link_data = spec.get("link_data") or {}
    body = link_data.get("message") or None
    cta = None
    if isinstance(link_data.get("call_to_action"), dict):
        cta = link_data["call_to_action"].get("type") or None
    return title, body, cta


def map_ad_account(raw: AdAccountResponse) -> CanonicalAdAccount:
    external_id = raw.account_id or raw.id or ""
    external_id = external_id.removeprefix("act_")
    if not external_id.isdigit():
        raise ProviderDataError("Meta ad account id is malformed")
    raw_status = str(raw.account_status)
    status_label = ACCOUNT_STATUS_LABELS.get(raw_status, raw_status or "UNKNOWN")
    offset = None
    if raw.timezone_offset_hours_utc is not None:
        offset = _to_decimal(raw.timezone_offset_hours_utc, "timezone_offset_hours_utc")
    currency = (raw.currency or "").strip().upper()
    if len(currency) != 3:
        currency = "USD"
    return CanonicalAdAccount(
        external_id=external_id,
        name=raw.name or None,
        currency=currency,
        timezone=raw.timezone_name,
        timezone_offset_hours_utc=offset,
        status=status_label,
    )


def map_campaign(raw: CampaignResponse) -> CanonicalCampaign:
    return CanonicalCampaign(
        external_id=raw.id,
        name=raw.name or "",
        status=raw.effective_status or raw.status or "UNKNOWN",
        objective=raw.objective or None,
        buying_type=raw.buying_type or None,
        created_time=_parse_datetime(raw.created_time),
        updated_at=_parse_datetime(raw.updated_time),
    )


def map_ad_set(raw: AdSetResponse) -> CanonicalAdSet:
    return CanonicalAdSet(
        external_id=raw.id,
        campaign_external_id=raw.campaign_id,
        name=raw.name or "",
        status=raw.effective_status or raw.status or "UNKNOWN",
        optimization_goal=raw.optimization_goal or None,
        billing_event=raw.billing_event or None,
        created_time=_parse_datetime(raw.created_time),
        updated_at=_parse_datetime(raw.updated_time),
    )


def map_creative(raw: CreativeResponse) -> CanonicalCreative:
    title, body, cta = _story_spec(raw.object_story_spec)
    return CanonicalCreative(
        external_id=raw.id,
        name=raw.name or None,
        type=raw.object_type or None,
        title=title,
        body=body,
        call_to_action=cta,
        thumbnail_url=raw.thumbnail_url or None,
        created_time=_parse_datetime(raw.created_time),
        updated_at=_parse_datetime(raw.updated_time),
    )


def map_ad(raw: AdResponse, creative: CanonicalCreative | None) -> CanonicalAd:
    return CanonicalAd(
        external_id=raw.id,
        campaign_external_id=raw.campaign_id,
        ad_set_external_id=raw.adset_id,
        name=raw.name or "",
        status=raw.effective_status or raw.status or "UNKNOWN",
        created_time=_parse_datetime(raw.created_time),
        updated_at=_parse_datetime(raw.updated_time),
        creative=creative,
    )


def _sum_action_counts(actions: list | None) -> int | None:
    if not actions:
        return None
    total = 0
    for action in actions:
        if not isinstance(action, dict) and not hasattr(action, "model_dump"):
            continue
        values = action if isinstance(action, dict) else action.model_dump()
        count = values.get("count")
        if count is None or count == "":
            count = values.get("value")
        if count is None or count == "":
            continue
        try:
            total += int(Decimal(str(count)))
        except (InvalidOperation, TypeError, ValueError):
            raise ProviderDataError("Invalid action count in Meta insight") from None
    return total


def _sum_action_values(values: list | None) -> Decimal | None:
    if not values:
        return None
    total = Decimal("0")
    for action in values:
        if not isinstance(action, dict) and not hasattr(action, "model_dump"):
            continue
        item = action if isinstance(action, dict) else action.model_dump()
        raw = item.get("value")
        if raw is None or raw == "":
            continue
        try:
            total += Decimal(str(raw))
        except (InvalidOperation, TypeError, ValueError):
            raise ProviderDataError("Invalid action value in Meta insight") from None
    return total


def map_insight(raw: InsightItem) -> CanonicalAdInsight:
    try:
        from datetime import date as _date

        parts = (raw.date_start or "").split("-")
        fact_date = _date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError, TypeError):
        raise ProviderDataError("Meta insight date is malformed") from None

    impressions = _to_int(raw.impressions, "impressions")
    clicks = _to_int(raw.clicks, "clicks")
    spend = _to_decimal(raw.spend, "spend")
    _negative(Decimal(impressions), "impressions")
    _negative(Decimal(clicks), "clicks")
    _negative(spend, "spend")

    reach = _to_int(raw.reach, "reach") if raw.reach is not None else None
    if reach is not None:
        _negative(Decimal(reach), "reach")
    frequency = _to_decimal(raw.frequency, "frequency") if raw.frequency is not None else None
    if frequency is not None:
        _negative(frequency, "frequency")
    link_clicks = (
        _to_int(raw.inline_link_clicks, "inline_link_clicks")
        if raw.inline_link_clicks is not None
        else None
    )
    if link_clicks is not None:
        _negative(Decimal(link_clicks), "inline_link_clicks")
    landing_page_views = (
        _to_int(raw.landing_page_views, "landing_page_views")
        if raw.landing_page_views is not None
        else None
    )
    if landing_page_views is not None:
        _negative(Decimal(landing_page_views), "landing_page_views")

    conversions = _sum_action_counts(raw.actions)
    conversion_value = _sum_action_values(raw.action_values)
    if conversion_value is not None:
        _negative(conversion_value, "conversion_value")

    return CanonicalAdInsight(
        date=fact_date,
        currency="",
        impressions=impressions,
        spend=spend,
        clicks=clicks,
        reach=reach,
        frequency=frequency,
        link_clicks=link_clicks,
        landing_page_views=landing_page_views,
        conversions=conversions,
        conversion_value=conversion_value,
        campaign_external_id=raw.campaign_id,
        ad_set_external_id=raw.adset_id,
        ad_external_id=raw.ad_id,
    )