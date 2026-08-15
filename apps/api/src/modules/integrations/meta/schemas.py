"""Meta Graph API response schemas.

Only the fields Phase 2B needs. Pydantic validation is the defense against
malformed provider payloads (a payload that fails to parse becomes
ProviderDataError). Money stays numeric strings; conversion to Decimal
happens in the mapper. `extra="allow"` ignores any new Meta fields.

Every id/numeric field tolerates both int and string representations
because Meta mixes them across endpoints.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _to_str(value: Any) -> str:
    return str(value)


class MetaErrorBody(BaseModel):
    model_config = ConfigDict(extra="allow")

    message: str = ""
    type: str | None = None
    code: int | None = None
    error_subcode: int | None = None
    fbtrace_id: str | None = None


class MetaErrorResponse(BaseModel):
    error: MetaErrorBody


class TokenExchangeResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int | None = None


class UserResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int | str
    name: str | None = None


class Paging(BaseModel):
    model_config = ConfigDict(extra="allow")

    cursors: dict[str, str] | None = None
    next: str | None = None

    @property
    def after(self) -> str | None:
        if self.cursors:
            return self.cursors.get("after")
        return None


class AdAccountResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | int = ""
    account_id: str | int | None = None
    name: str | None = None
    currency: str | None = None
    account_status: str | int | None = None
    timezone_name: str | None = None
    timezone_offset_hours_utc: str | float | None = None

    @field_validator("id", "account_id")
    @classmethod
    def _ids_to_str(cls, value: str | int | None) -> str | None:
        if value is None:
            return None
        return _to_str(value)


class CampaignResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | int
    name: str = ""
    status: str | None = None
    effective_status: str | None = None
    objective: str | None = None
    buying_type: str | None = None
    created_time: str | datetime | None = None
    updated_time: str | datetime | None = None

    @field_validator("id")
    @classmethod
    def _id_to_str(cls, value: str | int) -> str:
        return _to_str(value)


class AdSetResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | int
    name: str = ""
    status: str | None = None
    effective_status: str | None = None
    campaign_id: str | int | None = None
    optimization_goal: str | None = None
    billing_event: str | None = None
    created_time: str | datetime | None = None
    updated_time: str | datetime | None = None

    @field_validator("id", "campaign_id")
    @classmethod
    def _ids_to_str(cls, value: str | int | None) -> str | None:
        if value is None:
            return None
        return _to_str(value)


class CreativeResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | int
    name: str | None = None
    status: str | None = None
    object_type: str | None = None
    thumbnail_url: str | None = None
    object_story_spec: dict | None = None
    created_time: str | datetime | None = None
    updated_time: str | datetime | None = None

    @field_validator("id")
    @classmethod
    def _id_to_str(cls, value: str | int) -> str:
        return _to_str(value)


class AdResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | int
    name: str = ""
    status: str | None = None
    effective_status: str | None = None
    campaign_id: str | int | None = None
    adset_id: str | int | None = None
    creative: CreativeResponse | None = None
    created_time: str | datetime | None = None
    updated_time: str | datetime | None = None

    @field_validator("id", "campaign_id", "adset_id")
    @classmethod
    def _ids_to_str(cls, value: str | int | None) -> str | None:
        if value is None:
            return None
        return _to_str(value)


class AdsActionStats(BaseModel):
    model_config = ConfigDict(extra="allow")

    action_type: str | None = None
    value: str | int | float | None = None
    count: str | int | None = None


class InsightItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    date_start: str = ""
    campaign_id: str | int | None = None
    adset_id: str | int | None = None
    ad_id: str | int | None = None
    impressions: str | int | None = None
    reach: str | int | None = None
    frequency: str | int | float | None = None
    clicks: str | int | None = None
    inline_link_clicks: str | int | None = None
    landing_page_views: str | int | None = None
    spend: str | int | float | None = None
    actions: list[AdsActionStats] | None = None
    action_values: list[AdsActionStats] | None = None

    @field_validator("campaign_id", "adset_id", "ad_id")
    @classmethod
    def _ids_to_str(cls, value: str | int | None) -> str | None:
        if value is None:
            return None
        return _to_str(value)


class Envelope(BaseModel):
    """Wraps an API list response `{data: [...], paging: {...}}`."""

    model_config = ConfigDict(extra="allow")

    data: list[dict] = Field(default_factory=list)
    paging: Paging | None = None