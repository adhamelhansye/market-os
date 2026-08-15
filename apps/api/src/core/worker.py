"""Background worker (arq, backed by Redis).

Job functions create their OWN database session and Redis client: the
worker never shares state with the API process. Retries:

- transient provider failures (5xx, rate limits) -> Retry with exponential
  backoff (capped), bounded by each job's max_tries;
- provider auth failures -> terminal (the connection needs reconnecting,
  retrying would burn rate limits);
- everything else -> terminal, surfaced as a failed job (and, for syncs, a
  failed SyncRun row).

Never log: credentials, tokens, or provider secrets.
"""

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

logger = get_logger(__name__)

_MAX_TRIES = 4
_RETRY_KEY = "arq:retry:{}"


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


class WorkerSettings:
    functions = [
        shopify_initial_sync,
        shopify_incremental_sync,
        shopify_webhook_processing,
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 8
    job_timeout = 1800
    keep_result = 0
    max_tries = _MAX_TRIES