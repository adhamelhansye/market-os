"""ARQ enqueue helper for research collection."""

from __future__ import annotations

import uuid

from arq import create_pool
from arq.connections import RedisSettings

from src.core.config import get_settings


async def enqueue_collection_job(job_id: uuid.UUID) -> str:
    pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    try:
        result = await pool.enqueue_job("research_collection", str(job_id), _job_id=str(job_id))
        return result.job_id if result else str(job_id)
    finally:
        await pool.aclose()
