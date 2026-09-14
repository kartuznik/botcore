"""Raffle management. The API only writes to the database; Telegram is the bot's job."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from api.dependencies import ContainerDep, CurrentUserDep
from api.schemas import (
    ErrorResponse,
    RaffleCreateRequest,
    RaffleDetailResponse,
    RaffleResponse,
)
from core.logging_setup import get_logger
from modules.raffle.models import RaffleSource

logger = get_logger(__name__)
router = APIRouter(
    prefix="/raffles",
    tags=["raffles"],
    responses={status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse}},
)


@router.get("", response_model=list[RaffleResponse], summary="List raffles")
async def list_raffles(container: ContainerDep, user: CurrentUserDep) -> list[RaffleResponse]:
    summaries = await container.raffles.list_raffles()
    return [RaffleResponse.from_summary(summary) for summary in summaries]


@router.post(
    "",
    response_model=RaffleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a raffle the bot will announce and draw",
)
async def create_raffle(
    payload: RaffleCreateRequest,
    container: ContainerDep,
    user: CurrentUserDep,
) -> RaffleResponse:
    raffle = await container.raffles.create_raffle(
        title=payload.title,
        winners_count=payload.winners_count,
        deadline_at=payload.deadline_at,
        channels=payload.channels,
        created_by=container.owner_id,
        source=RaffleSource.API,
    )
    logger.info("raffle %s created via api by %s", raffle.id, user.username)
    return RaffleResponse.from_raffle(raffle, participants_count=0)


@router.get(
    "/{raffle_id}",
    response_model=RaffleDetailResponse,
    summary="Raffle details with participants and draw results",
    responses={status.HTTP_404_NOT_FOUND: {"model": ErrorResponse}},
)
async def get_raffle(
    raffle_id: int,
    container: ContainerDep,
    user: CurrentUserDep,
) -> RaffleDetailResponse:
    repository = container.raffles.repository
    raffle = await repository.get_raffle(raffle_id)
    if raffle is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"raffle {raffle_id} not found")
    return RaffleDetailResponse.build(
        raffle,
        await repository.list_participants(raffle_id),
        await repository.list_draws(raffle_id),
    )
