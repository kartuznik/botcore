"""Registration, login and token refresh."""

from __future__ import annotations

from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from api.app import create_app
from api.config import ApiConfigError, ApiSettings, load_api_settings
from api.container import ApiContainer
from api.security import create_access_token, hash_password, verify_password
from tests.conftest import API_PASSWORD, API_USERNAME

CREDENTIALS = {"username": API_USERNAME, "password": API_PASSWORD}


async def test_register_returns_the_created_account(api_client: AsyncClient) -> None:
    response = await api_client.post("/auth/register", json=CREDENTIALS)

    assert response.status_code == 201
    body = response.json()
    assert body["username"] == API_USERNAME
    assert body["id"] > 0
    assert "password" not in body
    assert "password_hash" not in body


async def test_password_is_stored_as_a_bcrypt_hash(
    api_client: AsyncClient,
    api_settings: ApiSettings,
) -> None:
    await api_client.post("/auth/register", json=CREDENTIALS)

    app = create_app(api_settings)
    container: ApiContainer = app.state.container
    try:
        user = await container.users.get_by_username(API_USERNAME)
        assert user is not None
        assert user.password_hash != API_PASSWORD
        assert user.password_hash.startswith("$2b$")
        assert verify_password(API_PASSWORD, user.password_hash)
    finally:
        await container.close()


async def test_register_rejects_a_taken_username(api_client: AsyncClient) -> None:
    await api_client.post("/auth/register", json=CREDENTIALS)

    response = await api_client.post("/auth/register", json=CREDENTIALS)

    assert response.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {"username": "ad", "password": API_PASSWORD},
        {"username": API_USERNAME, "password": "short"},
        {"username": "bad user", "password": API_PASSWORD},
        {"username": API_USERNAME},
    ],
)
async def test_register_validates_its_input(
    api_client: AsyncClient,
    payload: dict[str, str],
) -> None:
    response = await api_client.post("/auth/register", json=payload)

    assert response.status_code == 422


async def test_login_returns_both_tokens(api_client: AsyncClient) -> None:
    await api_client.post("/auth/register", json=CREDENTIALS)

    response = await api_client.post("/auth/login", json=CREDENTIALS)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 15 * 60
    assert body["access_token"] and body["refresh_token"]
    assert body["access_token"] != body["refresh_token"]


@pytest.mark.parametrize(
    "payload",
    [
        {"username": API_USERNAME, "password": "wrong-password"},
        {"username": "nobody", "password": API_PASSWORD},
    ],
)
async def test_login_rejects_bad_credentials(
    api_client: AsyncClient,
    payload: dict[str, str],
) -> None:
    await api_client.post("/auth/register", json=CREDENTIALS)

    response = await api_client.post("/auth/login", json=payload)

    assert response.status_code == 401


async def test_refresh_issues_a_new_access_token(api_client: AsyncClient) -> None:
    await api_client.post("/auth/register", json=CREDENTIALS)
    tokens = (await api_client.post("/auth/login", json=CREDENTIALS)).json()

    response = await api_client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert "refresh_token" not in body

    protected = await api_client.get(
        "/raffles",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert protected.status_code == 200


async def test_refresh_rejects_an_access_token(
    api_client: AsyncClient,
    api_settings: ApiSettings,
) -> None:
    await api_client.post("/auth/register", json=CREDENTIALS)
    access = create_access_token(api_settings, API_USERNAME)

    response = await api_client.post("/auth/refresh", json={"refresh_token": access})

    assert response.status_code == 401
    assert "refresh" in response.json()["detail"]


async def test_refresh_rejects_garbage(api_client: AsyncClient) -> None:
    response = await api_client.post("/auth/refresh", json={"refresh_token": "not-a-jwt"})

    assert response.status_code == 401


async def test_tokens_signed_with_another_secret_are_rejected(
    api_client: AsyncClient,
    api_settings: ApiSettings,
) -> None:
    await api_client.post("/auth/register", json=CREDENTIALS)
    foreign = create_access_token(
        ApiSettings(jwt_secret="another-secret-" * 4, database_path=api_settings.database_path),
        API_USERNAME,
    )

    response = await api_client.get("/raffles", headers={"Authorization": f"Bearer {foreign}"})

    assert response.status_code == 401


async def test_expired_access_token_is_rejected(
    api_client: AsyncClient,
    api_settings: ApiSettings,
) -> None:
    await api_client.post("/auth/register", json=CREDENTIALS)
    expired_settings = ApiSettings(
        jwt_secret=api_settings.jwt_secret,
        database_path=api_settings.database_path,
        access_ttl=timedelta(seconds=-1),
    )
    expired = create_access_token(expired_settings, API_USERNAME)

    response = await api_client.get("/raffles", headers={"Authorization": f"Bearer {expired}"})

    assert response.status_code == 401


async def test_registration_can_be_closed_after_the_first_account(
    api_settings: ApiSettings,
) -> None:
    closed = ApiSettings(
        jwt_secret=api_settings.jwt_secret,
        database_path=api_settings.database_path,
        registration_open=False,
    )
    app = create_app(closed)
    container: ApiContainer = app.state.container
    await container.init()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://api.test",
        ) as client:
            first = await client.post("/auth/register", json=CREDENTIALS)
            second = await client.post(
                "/auth/register",
                json={"username": "second", "password": API_PASSWORD},
            )
    finally:
        await container.close()

    assert first.status_code == 201
    assert second.status_code == 403


def test_api_does_not_start_without_a_secret() -> None:
    with pytest.raises(ApiConfigError) as error:
        load_api_settings({"STORAGE_PATH": "data/botcore.db"})

    assert "API_JWT_SECRET" in str(error.value)


def test_hashes_of_one_password_differ() -> None:
    first = hash_password(API_PASSWORD)
    second = hash_password(API_PASSWORD)

    assert first != second
    assert verify_password(API_PASSWORD, first)
    assert verify_password(API_PASSWORD, second)
    assert not verify_password("other-password", first)
