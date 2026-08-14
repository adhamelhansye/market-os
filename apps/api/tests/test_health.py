"""Health endpoint tests (no secrets or connection details exposed)."""

from httpx import AsyncClient


async def test_health_ok(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_ok_when_postgres_and_redis_up(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["redis"] == "ok"
    # Never leak connection details.
    assert all(key not in response.text for key in ("postgres", "localhost", "redis://"))


async def test_response_has_request_id_header(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.headers.get("X-Request-Id")


async def test_response_has_security_headers(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("Referrer-Policy")