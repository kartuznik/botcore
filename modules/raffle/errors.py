"""Errors the raffle module turns into readable answers instead of crashes."""

from __future__ import annotations


class RaffleError(Exception):
    """Base error of the raffle module."""


class RaffleNotFoundError(RaffleError):
    def __init__(self, raffle_id: int) -> None:
        self.raffle_id = raffle_id
        super().__init__(f"Розыгрыш #{raffle_id} не найден.")


class RaffleClosedError(RaffleError):
    def __init__(self, raffle_id: int, status: str) -> None:
        self.raffle_id = raffle_id
        self.status = status
        super().__init__(f"Розыгрыш #{raffle_id} уже закрыт (статус: {status}).")


class NoEligibleParticipantsError(RaffleError):
    def __init__(self, raffle_id: int) -> None:
        self.raffle_id = raffle_id
        super().__init__(f"В розыгрыше #{raffle_id} нет участников, прошедших проверку.")


class ChannelAccessError(RaffleError):
    """Bot cannot read the channel membership — usually it is not an admin there."""

    def __init__(self, channel: str, reason: str) -> None:
        self.channel = channel
        self.reason = reason
        super().__init__(f"Нет доступа к каналу {channel}: {reason}")
