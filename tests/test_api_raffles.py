"""Raffle routes: authentication, creation, listing and details."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from api.config import ApiSettings
from modules.raffle.models import RaffleSource
from modules.raffle.repository import LIVE_TABLES, RaffleDatabase, RaffleRepository
from modules.raffle.service import AllowAllChecker, RaffleService

PROTECTED = [("GET", "/raffles"), ("POST", "/raffles"), ("GET", "/raffles/1")]


def raffle_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "title": "Розыгрыш через API",
        "winners_count": 2,
        "deadline_at": (datetime.now(UTC) + timedelta(hours=2)).isoformat(),
        "channels": ["@corerebot_channel"],
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(("method", "path"), PROTECTED)
async def test_protected_routes_reject_a_missing_token(
    api_client: AsyncClient,
    method: str,
    path: str,
) -> None:
    response = await api_client.request(method, path, json=raffle_payload())

    assert response.status_code == 401


@pytest.mark.parametrize(("method", "path"), PROTECTED)
async def test_protected_routes_reject_an_invalid_token(
    api_client: AsyncClient,
    method: str,
    path: str,
) -> None:
    response = await api_client.request(
        method,
        path,
        json=raffle_payload(),
        headers={"Authorization": "Bearer definitely.not.a.jwt"},
    )

    assert response.status_code == 401


async def test_create_raffle_stores_it_as_an_api_raffle(
    api_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await api_client.post("/raffles", json=raffle_payload(), headers=auth_headers)

    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["title"] == "Розыгрыш через API"
    assert body["winners_count"] == 2
    assert body["channels"] == ["@corerebot_channel"]
    assert body["status"] == "open"
    assert body["source"] == RaffleSource.API.value
    assert body["participants_count"] == 0


@pytest.mark.parametrize(
    "payload",
    [
        raffle_payload(title=""),
        raffle_payload(winners_count=0),
        raffle_payload(deadline_at="yesterday"),
        raffle_payload(deadline_at=(datetime.now(UTC) - timedelta(hours=1)).isoformat()),
    ],
)
async def test_create_raffle_validates_its_input(
    api_client: AsyncClient,
    auth_headers: dict[str, str],
    payload: dict[str, object],
) -> None:
    response = await api_client.post("/raffles", json=payload, headers=auth_headers)

    assert response.status_code == 422


async def test_list_raffles_returns_what_was_created(
    api_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    created = await api_client.post(
        "/raffles",
        json=raffle_payload(title="Первый"),
        headers=auth_headers,
    )
    await api_client.post("/raffles", json=raffle_payload(title="Второй"), headers=auth_headers)

    response = await api_client.get("/raffles", headers=auth_headers)

    assert response.status_code == 200
    titles = [item["title"] for item in response.json()]
    assert titles == ["Второй", "Первый"]
    assert created.json()["id"] in {item["id"] for item in response.json()}


async def test_raffle_details_show_participants_and_draw_results(
    api_client: AsyncClient,
    auth_headers: dict[str, str],
    api_settings: ApiSettings,
) -> None:
    created = await api_client.post(
        "/raffles",
        json=raffle_payload(winners_count=1, channels=[]),
        headers=auth_headers,
    )
    raffle_id = created.json()["id"]

    # The bot side of the shared database: two people join and the draw happens.
    database = RaffleDatabase(api_settings.database_path)
    service = RaffleService(RaffleRepository(database, LIVE_TABLES))
    try:
        await service.join(raffle_id, 1001, "first")
        await service.join(raffle_id, 1002, "second")
        outcome = await service.draw(raffle_id, 0, AllowAllChecker())
    finally:
        await database.close()

    response = await api_client.get(f"/raffles/{raffle_id}", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "drawn"
    assert body["participants_count"] == 2
    assert {item["user_id"] for item in body["participants"]} == {1001, 1002}
    assert len(body["draws"]) == 1
    draw = body["draws"][0]
    assert draw["winners"] == [winner.user_id for winner in outcome.winners]
    assert draw["participants"] == [1001, 1002]
    assert draw["drawn_by"] == 0


async def test_unknown_raffle_returns_404(
    api_client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    response = await api_client.get("/raffles/404", headers=auth_headers)

    assert response.status_code == 404


async def test_swagger_and_openapi_are_served(api_client: AsyncClient) -> None:
    docs = await api_client.get("/docs")
    schema = await api_client.get("/openapi.json")

    assert docs.status_code == 200
    assert schema.status_code == 200
    paths = schema.json()["paths"]
    assert {"/auth/register", "/auth/login", "/auth/refresh", "/raffles"} <= set(paths)
