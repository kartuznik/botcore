"""Password hashing (bcrypt) and JWT issuing/validation (PyJWT)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from api.config import ApiSettings

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"
BCRYPT_MAX_PASSWORD_BYTES = 72


class TokenError(Exception):
    """Raised when a token is malformed, expired or of the wrong type."""


@dataclass(frozen=True, slots=True)
class TokenPayload:
    """The claims the API actually relies on."""

    subject: str
    token_type: str
    expires_at: datetime


def hash_password(password: str) -> str:
    """Hash a password with a per-user bcrypt salt."""
    return bcrypt.hashpw(_password_bytes(password), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Check a password against its hash; never raises on malformed input."""
    try:
        return bcrypt.checkpw(_password_bytes(password), password_hash.encode())
    except ValueError:
        return False


def create_access_token(settings: ApiSettings, subject: str) -> str:
    return _create_token(settings, subject, ACCESS_TOKEN_TYPE, settings.access_ttl)


def create_refresh_token(settings: ApiSettings, subject: str) -> str:
    return _create_token(settings, subject, REFRESH_TOKEN_TYPE, settings.refresh_ttl)


def decode_token(settings: ApiSettings, token: str, expected_type: str) -> TokenPayload:
    """Validate a token's signature, expiry and type."""
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=[settings.algorithm])
    except jwt.PyJWTError as error:
        raise TokenError("token is invalid or expired") from error
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise TokenError("token carries no subject")
    token_type = claims.get("type")
    if token_type != expected_type:
        raise TokenError(f"expected a {expected_type} token")
    return TokenPayload(
        subject=subject,
        token_type=expected_type,
        expires_at=datetime.fromtimestamp(int(claims["exp"]), tz=UTC),
    )


def _create_token(settings: ApiSettings, subject: str, token_type: str, ttl: timedelta) -> str:
    issued_at = datetime.now(tz=UTC)
    claims = {
        "sub": subject,
        "type": token_type,
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + ttl).timestamp()),
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.algorithm)


def _password_bytes(password: str) -> bytes:
    # bcrypt silently ignores everything past 72 bytes; refuse instead of pretending.
    encoded = password.encode()
    if len(encoded) > BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError("password must not exceed 72 bytes")
    return encoded
