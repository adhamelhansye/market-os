"""Integration API schemas (explicit contracts; internal models are never
exposed directly). Money fields are Decimals (serialize as strings)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ShopifyConnectRequest(BaseModel):
    shop_domain: str = Field(min_length=1, max_length=255)
    locale: Literal["en", "ar"] = "en"


class ShopifyConnectResponse(BaseModel):
    auth_url: str


class SyncRunRead(BaseModel):
    id: uuid.UUID
    resource_type: str
    status: Literal["running", "success", "partial", "failed"]
    started_at: datetime
    finished_at: datetime | None
    records_processed: int
    error_summary: str | None = None


class ConnectionRead(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    provider: str
    status: Literal["pending", "connected", "disconnected", "error"]
    external_account_id: str | None = None
    external_account_name: str | None = None
    scopes: list[str] = Field(default_factory=list)
    metadata: dict | None = None
    connected_at: datetime | None = None
    last_sync_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    products_count: int = 0
    orders_count: int = 0
    customers_count: int = 0
    inventory_count: int = 0
    latest_sync: SyncRunRead | None = None


class SyncRequest(BaseModel):
    """Optional resource filter. Empty/absent syncs the incremental set."""

    resources: list[str] | None = None


class SyncResponse(BaseModel):
    status: Literal["accepted"] = "accepted"
    resources: list[str]


class WebhookAck(BaseModel):
    received: bool = True