"""Health and readiness endpoints. Never expose connection details."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from src.core.dependencies import DbSession, RedisClient

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(session: DbSession, redis: RedisClient) -> JSONResponse:
    checks: dict[str, str] = {}
    database_ok = True
    redis_ok = True

    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        database_ok = False
        checks["database"] = "error"

    try:
        await redis.ping()
        checks["redis"] = "ok"
    except Exception:
        redis_ok = False
        checks["redis"] = "error"

    status = "ok" if database_ok and redis_ok else "degraded"
    return JSONResponse(
        status_code=200 if database_ok and redis_ok else 503,
        content={"status": status, "checks": checks},
    )