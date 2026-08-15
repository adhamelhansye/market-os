"""Redis job queue helpers (arq).

These are thin wrappers: they only enqueue; execution happens in the worker
process. Job names are stable strings so the worker and the enqueuer never
go out of sync accidentally.
"""

from arq import create_pool
from arq.connections import RedisSettings

from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)

JOB_INITIAL_SYNC = "shopify_initial_sync"
JOB_INCREMENTAL_SYNC = "shopify_incremental_sync"
JOB_WEBHOOK_PROCESSING = "shopify_webhook_processing"
JOB_META_INITIAL_SYNC = "meta_initial_sync"
JOB_META_INCREMENTAL_SYNC = "meta_incremental_sync"


async def _enqueue(job_name: str, *args) -> None:
    settings = get_settings()
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await pool.enqueue_job(job_name, *args)
    finally:
        await pool.aclose()


async def enqueue_initial_sync(connection_id: str) -> None:
    await _enqueue(JOB_INITIAL_SYNC, connection_id)


async def enqueue_incremental_sync(connection_id: str, resources: list[str]) -> None:
    await _enqueue(JOB_INCREMENTAL_SYNC, connection_id, resources)


async def enqueue_webhook_processing(event_id: str) -> None:
    await _enqueue(JOB_WEBHOOK_PROCESSING, event_id)


async def enqueue_meta_initial_sync(connection_id: str) -> None:
    await _enqueue(JOB_META_INITIAL_SYNC, connection_id)


async def enqueue_meta_incremental_sync(connection_id: str, resources: list[str]) -> None:
    await _enqueue(JOB_META_INCREMENTAL_SYNC, connection_id, resources)