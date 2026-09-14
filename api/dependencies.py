"""Auth guard for protected routes, expressed as FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.container import ApiContainer
from api.security import ACCESS_TOKEN_TYPE, TokenError, decode_token
from api.users import ApiUser

# auto_error=False: the default would answer 403 to a missing header, and the
# contract here is 401 for "no token" and 401 for "bad token" alike.
bearer_scheme = HTTPBearer(auto_error=False, description="Access token from POST /auth/login")


def get_container(request: Request) -> ApiContainer:
    container: ApiContainer = request.app.state.container
    return container


ContainerDep = Annotated[ApiContainer, Depends(get_container)]
CredentialsDep = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


async def get_current_user(container: ContainerDep, credentials: CredentialsDep) -> ApiUser:
    if credentials is None:
        raise _unauthorized("authorization header is missing")
    try:
        payload = decode_token(container.settings, credentials.credentials, ACCESS_TOKEN_TYPE)
    except TokenError as error:
        raise _unauthorized(str(error)) from error
    user = await container.users.get_by_username(payload.subject)
    if user is None:
        raise _unauthorized("account no longer exists")
    return user


CurrentUserDep = Annotated[ApiUser, Depends(get_current_user)]


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )
