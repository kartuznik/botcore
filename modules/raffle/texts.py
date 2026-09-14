"""User-facing texts of the raffle module."""

from __future__ import annotations

from collections.abc import Sequence

from modules.raffle.errors import ChannelAccessError
from modules.raffle.models import (
    DrawOutcome,
    JoinResult,
    RaffleStatus,
    RaffleSummary,
)

ADMIN_ONLY = "Эта команда доступна только администратору розыгрышей."
JOIN_USAGE = "Укажите номер розыгрыша: /join 1. Список открытых — /raffles."
DRAW_USAGE = "Укажите номер розыгрыша: /draw 1."
NO_RAFFLES = "Розыгрышей пока нет. Администратор создаёт их командой /newraffle."

STATUS_LABELS = {
    RaffleStatus.OPEN: "открыт",
    RaffleStatus.DRAWN: "проведён",
    RaffleStatus.CANCELLED: "отменён",
}

JOIN_TEXTS = {
    JoinResult.JOINED: "Вы в розыгрыше #{raffle_id}. Не отписывайтесь от каналов до тиража.",
    JoinResult.DUPLICATE: "Вы уже участвуете в розыгрыше #{raffle_id}, второй раз не считается.",
    JoinResult.CLOSED: "Розыгрыш #{raffle_id} уже закрыт, вступить нельзя.",
    JoinResult.EXPIRED: "Приём заявок в розыгрыш #{raffle_id} закончился.",
    JoinResult.NOT_FOUND: "Розыгрыш #{raffle_id} не найден. Список — /raffles.",
}


def render_raffle_list(summaries: Sequence[RaffleSummary]) -> str:
    if not summaries:
        return NO_RAFFLES
    lines = ["Розыгрыши:"]
    for summary in summaries:
        raffle = summary.raffle
        channels = ", ".join(raffle.channels) if raffle.channels else "без условия подписки"
        lines.append(
            f"\n#{raffle.id} — {raffle.title}"
            f"\n  статус: {STATUS_LABELS[raffle.status]}"
            f"\n  победителей: {raffle.winners_count}"
            f"\n  дедлайн: {raffle.deadline_at:%d.%m.%Y %H:%M} UTC"
            f"\n  условие: {channels}"
            f"\n  участников: {summary.participants_count}"
        )
    return "".join(lines)


def render_draw_outcome(outcome: DrawOutcome) -> str:
    winners = "\n".join(
        f"  {index}. {winner.label}" for index, winner in enumerate(outcome.winners, 1)
    )
    lines = [
        f"Тираж розыгрыша #{outcome.raffle.id} — {outcome.raffle.title}",
        f"Участников: {outcome.participants_count}, допущено: {outcome.eligible_count}",
        "Победители:",
        winners,
    ]
    if outcome.excluded:
        excluded = "\n".join(f"  id{item.user_id}: {item.reason}" for item in outcome.excluded)
        lines.append(f"Исключены при проверке ({len(outcome.excluded)}):\n{excluded}")
    if len(outcome.winners) < outcome.raffle.winners_count:
        lines.append(
            f"Допущенных участников меньше, чем мест: выбрано {len(outcome.winners)} "
            f"из {outcome.raffle.winners_count}."
        )
    lines.append(f"Протокол тиража сохранён (запись #{outcome.draw_id}).")
    return "\n".join(lines)


def render_demo_outcome(outcome: DrawOutcome) -> str:
    return (
        "Демо-тираж выполнен на демо-таблицах, боевые данные не затронуты.\n\n"
        f"{render_draw_outcome(outcome)}"
    )


def render_channel_error(error: ChannelAccessError) -> str:
    return (
        f"Не удалось проверить подписку: {error.reason} ({error.channel}).\n"
        "Добавьте бота администратором канала и повторите тираж — "
        "результат не сохранён, розыгрыш остался открытым."
    )
