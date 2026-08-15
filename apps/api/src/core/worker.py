"""Background worker (arq, backed by Redis).

Job functions create their OWN database session and Redis client: the
worker never shares state with the API process. Retries:

- transient provider failures (5xx, rate limits) -> Retry with exponential
  backoff (capped), bounded by each job's max_tries;
- provider auth failures -> terminal (the connection needs reconnecting,
  retrying would burn rate limits);
- everything else -> terminal, surfaced as a failed job (and, for syncs, a
  failed SyncRun row).

Meta syncs additionally hold a per-connection Redis lock (SET NX PX): two
concurrent jobs for the same ad account never run at once, and the lock is
crash-tolerant (TTL) and safely released only by its owner.

Never log: credentials, tokens, or provider secrets.
"""

import secrets

from arq import Retry, func
from arq.connections import RedisSettings
from redis.asyncio import Redis

from src.core.config import get_settings
from src.core.logging import get_logger
from src.db.session import create_engine, create_session_factory
from src.modules.integrations import service
from src.modules.integrations.base.errors import (
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
)
from src.modules.integrations.meta.constants import (
    INITIAL_RESOURCES as META_INITIAL_RESOURCES,
)

logger = get_logger(__name__)

_MAX_TRIES = 4
_RETRY_KEY = "arq:retry:{}"

_META_LOCK_KEY = "meta:sync:lock:{}"
_META_LOCK_TTL_MS = 1800_000  # 30 minutes > job_timeout; crash-tolerant
_META_LOCK_RELEASE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


async def _retry_defer(ctx: dict, exc: ProviderError) -> Retry:
    """Exponential backoff bounded by the attempt counter arq keeps in
    Redis (the same counter that enforces max_tries)."""
    try:
        attempts = int(await ctx["redis"].get(_RETRY_KEY.format(ctx["job_id"])) or 1)
    except (TypeError, ValueError, KeyError):
        attempts = 1
    defer = min(2 ** max(attempts - 1, 0) * 5, 300)
    logger.warning(
        "sync retry scheduled (attempt=%s, defer=%ss, error=%s)",
        attempts,
        defer,
        exc.code,
    )
    return Retry(defer=defer)


async def startup(ctx: dict) -> None:
    settings = get_settings()
    ctx["redis"] = Redis.from_url(settings.redis_url, decode_responses=True)
    logger.info("marketingos worker started")


async def shutdown(ctx: dict) -> None:
    await ctx["redis"].aclose()
    logger.info("marketingos worker stopped")


async def _run_sync(
    ctx: dict, connection_id: str, resources: tuple[str, ...], *, initial: bool
) -> dict[str, int]:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            try:
                results = await service.run_sync(
                    session,
                    connection_id=connection_id,
                    resources=resources,
                    initial=initial,
                )
            except ProviderAuthError:
                logger.error(
                    "sync failed: provider auth rejected (connection=%s)", connection_id
                )
                raise
            except (ProviderRateLimitError, ProviderError) as exc:
                raise await _retry_defer(ctx, exc) from exc
        logger.info(
            "sync completed (connection=%s, initial=%s, results=%s)",
            connection_id,
            initial,
            results,
        )
        return results
    finally:
        await engine.dispose()


async def _shopify_initial_sync(ctx: dict, connection_id: str) -> dict[str, int]:
    return await _run_sync(
        ctx, connection_id, service.INITIAL_RESOURCES, initial=True
    )


async def _shopify_incremental_sync(
    ctx: dict, connection_id: str, resources: list[str]
) -> dict[str, int]:
    return await _run_sync(ctx, connection_id, tuple(resources), initial=False)


async def _shopify_webhook_processing(ctx: dict, event_id: str) -> None:
    settings = get_settings()
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            redis = Redis.from_url(settings.redis_url, decode_responses=True)
            try:
                try:
                    await service.process_webhook_event(
                        session, redis, settings, event_id=event_id
                    )
                except (ProviderRateLimitError, ProviderError) as exc:
                    raise await _retry_defer(ctx, exc) from exc
            finally:
                await redis.aclose()
        logger.info("webhook processed (event=%s)", event_id)
    finally:
        await engine.dispose()


async def _release_meta_lock(redis: Redis, lock_key: str, token: str) -> None:
    """Safe release: the lock is only deleted while its value is still our
    token (a crashed job leaves the lock to expire via TTL)."""
    try:
        await redis.eval(_META_LOCK_RELEASE, 1, lock_key, token)
    except Exception:  # noqa: BLE001 - best effort; TTL covers it
        logger.warning("meta sync lock release failed; TTL will expire it")


async def _run_meta_sync(
    ctx: dict, connection_id: str, resources: tuple[str, ...], *, initial: bool
) -> dict:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    lock_key = _META_LOCK_KEY.format(connection_id)
    token = secrets.token_urlsafe(16)
    acquired = await redis.set(lock_key, token, nx=True, px=_META_LOCK_TTL_MS)
    if not acquired:
        logger.warning(
            "meta sync skipped: lock held by another run (connection=%s)", connection_id
        )
        await redis.aclose()
        return {"skipped": "locked"}

    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            try:
                results = await service.run_sync(
                    session,
                    connection_id=connection_id,
                    resources=resources,
                    initial=initial,
                )
            except ProviderAuthError:
                # Token rejected by Meta: stop, mark the connection for
                # re-authorization, and never burn rate limits retrying.
                await service.mark_meta_reconnect_required(session, connection_id)
                logger.error(
                    "meta sync failed: provider auth rejected (connection=%s)",
                    connection_id,
                )
                raise
            except (ProviderRateLimitError, ProviderError) as exc:
                raise await _retry_defer(ctx, exc) from exc
        logger.info(
            "meta sync completed (connection=%s, initial=%s, results=%s)",
            connection_id,
            initial,
            results,
        )
        return results
    finally:
        await _release_meta_lock(redis, lock_key, token)
        await redis.aclose()
        await engine.dispose()


async def _meta_initial_sync(ctx: dict, connection_id: str) -> dict:
    return await _run_meta_sync(
        ctx, connection_id, tuple(META_INITIAL_RESOURCES), initial=True
    )


async def _meta_incremental_sync(ctx: dict, connection_id: str, resources: list[str]) -> dict:
    return await _run_meta_sync(ctx, connection_id, tuple(resources), initial=False)


# Job names are the stable contract with jobs.py enqueue helpers.
shopify_initial_sync = func(
    _shopify_initial_sync, name="shopify_initial_sync", max_tries=_MAX_TRIES, keep_result=0
)
shopify_incremental_sync = func(
    _shopify_incremental_sync,
    name="shopify_incremental_sync",
    max_tries=_MAX_TRIES,
    keep_result=0,
)
shopify_webhook_processing = func(
    _shopify_webhook_processing,
    name="shopify_webhook_processing",
    max_tries=_MAX_TRIES,
    keep_result=0,
)
meta_initial_sync = func(
    _meta_initial_sync, name="meta_initial_sync", max_tries=_MAX_TRIES, keep_result=0
)
meta_incremental_sync = func(
    _meta_incremental_sync,
    name="meta_incremental_sync",
    max_tries=_MAX_TRIES,
    keep_result=0,
)


class WorkerSettings:
    functions = [
        shopify_initial_sync,
        shopify_incremental_sync,
        shopify_webhook_processing,
        meta_initial_sync,
        meta_incremental_sync,
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 8
    job_timeout = 1800
    keep_result = 0
    max_tries = _MAX_TRIES