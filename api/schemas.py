"""Pydantic schemas: validation on the way in, serialization on the way out."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from modules.raffle.models import (
    DrawRecord,
    ExcludedParticipant,
    Participant,
    Raffle,
    RaffleSummary,
)

USERNAME_PATTERN = r"^[A-Za-z0-9_.-]+$"
MAX_TITLE_LENGTH = 120
MAX_WINNERS = 1000
MAX_CHANNELS = 10


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=USERNAME_PATTERN)
    password: str = Field(min_length=8, max_length=72)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=72)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class UserResponse(BaseModel):
    id: int
    username: str
    created_at: datetime


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")


class TokenPairResponse(AccessTokenResponse):
    refresh_token: str


class RaffleCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=MAX_TITLE_LENGTH)
    winners_count: int = Field(ge=1, le=MAX_WINNERS)
    deadline_at: datetime = Field(description="Deadline in ISO 8601; naive values are read as UTC")
    channels: list[str] = Field(default_factory=list, max_length=MAX_CHANNELS)

    @field_validator("deadline_at")
    @classmethod
    def _must_be_in_the_future(cls, value: datetime) -> datetime:
        moment = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        if moment <= datetime.now(tz=UTC):
            raise ValueError("deadline_at must be in the future")
        return moment

    @field_validator("channels")
    @classmethod
    def _clean_channels(cls, value: list[str]) -> list[str]:
        return [channel.strip() for channel in value if channel.strip()]


class RaffleResponse(BaseModel):
    id: int
    title: str
    winners_count: int
    deadline_at: datetime
    channels: list[str]
    status: str
    source: str
    created_by: int
    created_at: datetime
    participants_count: int

    @classmethod
    def from_summary(cls, summary: RaffleSummary) -> RaffleResponse:
        return cls.from_raffle(summary.raffle, summary.participants_count)

    @classmethod
    def from_raffle(cls, raffle: Raffle, participants_count: int) -> RaffleResponse:
        return cls(
            id=raffle.id,
            title=raffle.title,
            winners_count=raffle.winners_count,
            deadline_at=raffle.deadline_at,
            channels=list(raffle.channels),
            status=raffle.status.value,
            source=raffle.source.value,
            created_by=raffle.created_by,
            created_at=raffle.created_at,
            participants_count=participants_count,
        )


class ParticipantResponse(BaseModel):
    user_id: int
    username: str | None
    joined_at: datetime

    @classmethod
    def from_participant(cls, participant: Participant) -> ParticipantResponse:
        return cls(
            user_id=participant.user_id,
            username=participant.username,
            joined_at=participant.joined_at,
        )


class ExcludedResponse(BaseModel):
    user_id: int
    reason: str

    @classmethod
    def from_excluded(cls, excluded: ExcludedParticipant) -> ExcludedResponse:
        return cls(user_id=excluded.user_id, reason=excluded.reason)


class DrawResponse(BaseModel):
    id: int
    drawn_at: datetime
    drawn_by: int = Field(description="Telegram id of the admin, or 0 for an automatic draw")
    participants: list[int]
    eligible: list[int]
    excluded: list[ExcludedResponse]
    winners: list[int]

    @classmethod
    def from_record(cls, record: DrawRecord) -> DrawResponse:
        return cls(
            id=record.id,
            drawn_at=record.drawn_at,
            drawn_by=record.drawn_by,
            participants=list(record.participants_snapshot),
            eligible=list(record.eligible_snapshot),
            excluded=[ExcludedResponse.from_excluded(item) for item in record.excluded_snapshot],
            winners=list(record.winners),
        )


class RaffleDetailResponse(RaffleResponse):
    participants: list[ParticipantResponse]
    draws: list[DrawResponse]

    @classmethod
    def build(
        cls,
        raffle: Raffle,
        participants: list[Participant],
        draws: list[DrawRecord],
    ) -> RaffleDetailResponse:
        base = RaffleResponse.from_raffle(raffle, len(participants))
        return cls(
            **base.model_dump(),
            participants=[ParticipantResponse.from_participant(item) for item in participants],
            draws=[DrawResponse.from_record(item) for item in draws],
        )


class ErrorResponse(BaseModel):
    detail: str
