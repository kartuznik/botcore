"""Registration and JWT issuing."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from api.dependencies import ContainerDep
from api.schemas import (
    AccessTokenResponse,
    ErrorResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPairResponse,
    UserResponse,
)
from api.security import (
    REFRESH_TOKEN_TYPE,
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from api.users import UsernameTakenError
from core.logging_setup import get_logger

INVALID_CREDENTIALS = "invalid username or password"
REGISTRATION_CLOSED = "registration is closed, ask the owner for an account"

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register an admin account",
    responses={
        status.HTTP_403_FORBIDDEN: {"model": ErrorResponse},
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
    },
)
async def register(payload: RegisterRequest, container: ContainerDep) -> UserResponse:
    # The first account can always be created; after that the owner may close the door.
    if not container.settings.registration_open and await container.users.count() > 0:
        raise HTTPException(status.HTTP_403_FORBIDDEN, REGISTRATION_CLOSED)
    try:
        user = await container.users.create(payload.username, hash_password(payload.password))
    except UsernameTakenError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, "username is already taken") from error
    logger.info("api account registered: %s", user.username)
    return UserResponse(id=user.id, username=user.username, created_at=user.created_at)


@router.post(
    "/login",
    response_model=TokenPairResponse,
    summary="Exchange credentials for an access and a refresh token",
    responses={status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse}},
)
async def login(payload: LoginRequest, container: ContainerDep) -> TokenPairResponse:
    user = await container.users.get_by_username(payload.username)
    if user is None or not verify_password(payload.password, user.password_hash):
        logger.info("failed login attempt for %s", payload.username)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_CREDENTIALS)
    settings = container.settings
    return TokenPairResponse(
        access_token=create_access_token(settings, user.username),
        refresh_token=create_refresh_token(settings, user.username),
        expires_in=int(settings.access_ttl.total_seconds()),
    )


@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    summary="Issue a new access token from a refresh token",
    responses={status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse}},
)
async def refresh(payload: RefreshRequest, container: ContainerDep) -> AccessTokenResponse:
    settings = container.settings
    try:
        token = decode_token(settings, payload.refresh_token, REFRESH_TOKEN_TYPE)
    except TokenError as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(error)) from error
    if await container.users.get_by_username(token.subject) is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "account no longer exists")
    return AccessTokenResponse(
        access_token=create_access_token(settings, token.subject),
        expires_in=int(settings.access_ttl.total_seconds()),
    )
