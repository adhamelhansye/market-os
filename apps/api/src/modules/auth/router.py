"""Authentication endpoints: signup, login, refresh, logout, me."""

import uuid
from typing import Annotated

import jwt as pyjwt
from fastapi import APIRouter, Depends, Request, Response

from src.core.config import Settings
from src.core.dependencies import (
    CurrentUser,
    DbSession,
    RedisClient,
    SettingsDep,
    rate_limit,
)
from src.core.exceptions import AuthenticationError
from src.core.security import (
    REFRESH_TOKEN_TYPE,
    decode_token,
    refresh_cookie_attributes,
    refresh_cookie_max_age,
)
from src.db.models import User
from src.modules.auth import service
from src.modules.auth.schemas import (
    AuthResponse,
    LoginRequest,
    MembershipRead,
    MeResponse,
    RefreshResponse,
    SignupRequest,
)
from src.schemas.entities import UserRead

router = APIRouter(tags=["auth"])

signup_limit = Depends(rate_limit(5, 60))
login_limit = Depends(rate_limit(10, 60))
refresh_limit = Depends(rate_limit(20, 60))


def _set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        max_age=refresh_cookie_max_age(settings),
        **{k: v for k, v in refresh_cookie_attributes(settings).items() if k != "max_age"},
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        path="/api/v1/auth",
    )


@router.post("/signup", response_model=AuthResponse, status_code=201)
async def signup_endpoint(
    payload: SignupRequest,
    response: Response,
    session: DbSession,
    redis: RedisClient,
    settings: SettingsDep,
    _rate_limiter: Annotated[None, signup_limit] = None,
) -> AuthResponse:
    user, _ = await service.signup(
        session,
        name=payload.name,
        email=str(payload.email),
        password=payload.password,
        organization_name=payload.organization_name,
        organization_type=payload.organization_type,
    )
    access, refresh, jti = service.issue_tokens(user, settings)
    await service.store_refresh_token(redis, jti, refresh, settings)
    _set_refresh_cookie(response, refresh, settings)
    return AuthResponse(access_token=access, user=UserRead.model_validate(user))


@router.post("/login", response_model=AuthResponse)
async def login_endpoint(
    payload: LoginRequest,
    response: Response,
    session: DbSession,
    redis: RedisClient,
    settings: SettingsDep,
    _rate_limiter: Annotated[None, login_limit] = None,
) -> AuthResponse:
    user = await service.authenticate(session, str(payload.email), payload.password)
    access, refresh, jti = service.issue_tokens(user, settings)
    await service.store_refresh_token(redis, jti, refresh, settings)
    _set_refresh_cookie(response, refresh, settings)
    return AuthResponse(access_token=access, user=UserRead.model_validate(user))


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_endpoint(
    request: Request,
    response: Response,
    session: DbSession,
    redis: RedisClient,
    settings: SettingsDep,
    _rate_limiter: Annotated[None, refresh_limit] = None,
) -> RefreshResponse:
    token = request.cookies.get(settings.refresh_cookie_name)
    if not token:
        raise AuthenticationError("No refresh token provided")
    try:
        payload = decode_token(token, settings.jwt_refresh_secret, REFRESH_TOKEN_TYPE)
    except pyjwt.InvalidTokenError:
        raise AuthenticationError("Invalid or expired refresh token") from None
    jti = payload.get("jti")
    # Atomic consume: validates the fingerprint AND revokes the session in
    # one Redis operation, so a replayed token (even concurrent) can only
    # win once. The used session is already deleted at this point.
    if not jti or not await service.consume_refresh_token(redis, jti, token):
        raise AuthenticationError("Invalid or expired refresh token")

    user_id = uuid.UUID(payload["sub"])
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Invalid or expired refresh token")

    access, refresh, new_jti = service.issue_tokens(user, settings)
    await service.store_refresh_token(redis, new_jti, refresh, settings)
    _set_refresh_cookie(response, refresh, settings)
    return RefreshResponse(access_token=access)


@router.post("/logout", status_code=204)
async def logout_endpoint(
    request: Request,
    response: Response,
    redis: RedisClient,
    settings: SettingsDep,
) -> Response:
    token = request.cookies.get(settings.refresh_cookie_name)
    if token:
        try:
            payload = decode_token(token, settings.jwt_refresh_secret, REFRESH_TOKEN_TYPE)
            jti = payload.get("jti")
            if jti:
                await service.revoke_refresh_token(redis, jti)
        except pyjwt.InvalidTokenError:
            pass  # Nothing to revoke; the cookie is cleared regardless.
    _clear_refresh_cookie(response, settings)
    return Response(status_code=204)


@router.get("/me", response_model=MeResponse)
async def me_endpoint(
    user: CurrentUser,
    session: DbSession,
) -> MeResponse:
    memberships = await service.list_memberships(session, user.id)
    active_organization_id: uuid.UUID | None = None
    if memberships:
        active_organization_id = memberships[0][0].id
    return MeResponse(
        user=UserRead.model_validate(user),
        active_organization_id=active_organization_id,
        memberships=[
            MembershipRead(
                organization=org,
                role_name=role.name,
                permissions=role.permissions_json or [],
            )
            for org, role in memberships
        ],
    )