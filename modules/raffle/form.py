"""Inline form behind /newraffle: title, winners, deadline, channels, confirmation."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from core.logging_setup import get_logger
from modules.raffle.parsing import (
    MAX_TITLE_LENGTH,
    MAX_WINNERS,
    parse_channels,
    parse_deadline,
    parse_positive_int,
)
from modules.raffle.service import RaffleService, utcnow
from modules.raffle.texts import ADMIN_ONLY

CANCEL_DATA = "raffle:cancel"
CONFIRM_DATA = "raffle:confirm"
SKIP_CHANNELS_DATA = "raffle:skip-channels"

STEP_TITLE = "Шаг 1/4. Пришлите название розыгрыша."
STEP_WINNERS = f"Шаг 2/4. Сколько будет победителей? Число от 1 до {MAX_WINNERS}."
STEP_DEADLINE = (
    "Шаг 3/4. До какого момента принимаем заявки?\n"
    "Можно относительно: 30m, 2h, 3d. Можно точно: 2026-09-20 18:00 или 20.09.2026 (UTC)."
)
STEP_CHANNELS = (
    "Шаг 4/4. Каналы, подписку на которые проверяем при тираже.\n"
    "Через запятую: @channel, -1001234567890 или ссылка t.me/channel.\n"
    "Если условия нет — нажмите кнопку ниже."
)
BAD_TITLE = (
    f"Название не должно быть пустым и длиннее {MAX_TITLE_LENGTH} символов. Попробуйте ещё раз."
)
BAD_WINNERS = f"Нужно целое число от 1 до {MAX_WINNERS}. Попробуйте ещё раз."
BAD_DEADLINE = "Не понял дедлайн или он уже в прошлом. Примеры: 2h, 3d, 2026-09-20 18:00."
BAD_CHANNELS = "Не разобрал ни одного канала. Пришлите @имя или id, либо нажмите кнопку."
CANCELLED = "Создание розыгрыша отменено."
NEEDS_TEXT = "Жду текстом, пожалуйста."

logger = get_logger(__name__)


class NewRaffleForm(StatesGroup):
    """Steps of the /newraffle dialog."""

    title = State()
    winners = State()
    deadline = State()
    channels = State()
    confirm = State()


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data=CANCEL_DATA)]]
    )


def channels_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Без условия подписки", callback_data=SKIP_CHANNELS_DATA)],
            [InlineKeyboardButton(text="Отмена", callback_data=CANCEL_DATA)],
        ]
    )


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Создать", callback_data=CONFIRM_DATA)],
            [InlineKeyboardButton(text="Отмена", callback_data=CANCEL_DATA)],
        ]
    )


def render_summary(data: Mapping[str, Any]) -> str:
    channels = read_channels(data)
    deadline = read_deadline(data)
    return (
        "Проверьте розыгрыш:\n"
        f"  название: {read_text(data, 'title')}\n"
        f"  победителей: {read_int(data, 'winners')}\n"
        f"  дедлайн: {deadline:%d.%m.%Y %H:%M} UTC\n"
        f"  условие: {', '.join(channels) if channels else 'без условия подписки'}"
    )


def read_text(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    return value if isinstance(value, str) else ""


def read_int(data: Mapping[str, Any], key: str) -> int:
    value = data.get(key)
    return value if isinstance(value, int) else 0


def read_channels(data: Mapping[str, Any]) -> tuple[str, ...]:
    value = data.get("channels")
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def read_deadline(data: Mapping[str, Any]) -> datetime:
    return datetime.fromisoformat(read_text(data, "deadline"))


async def answer_callback(callback: CallbackQuery, text: str) -> None:
    message = callback.message
    if isinstance(message, Message):
        await message.answer(text)


def register_new_raffle_form(
    router: Router,
    *,
    service: RaffleService,
    admin_ids: frozenset[int],
) -> None:
    """Attach the /newraffle dialog to the module router."""

    def is_admin(user_id: int | None) -> bool:
        return user_id is not None and user_id in admin_ids

    @router.message(Command("newraffle"))
    async def start_form(message: Message, state: FSMContext) -> None:
        user = message.from_user
        if not is_admin(None if user is None else user.id):
            await message.answer(ADMIN_ONLY)
            return
        await state.clear()
        await state.set_state(NewRaffleForm.title)
        await message.answer(STEP_TITLE, reply_markup=cancel_keyboard())

    @router.message(Command("cancel"))
    async def cancel_command(message: Message, state: FSMContext) -> None:
        if await state.get_state() is None:
            return
        await state.clear()
        await message.answer(CANCELLED)

    @router.callback_query(F.data == CANCEL_DATA)
    async def cancel_button(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await callback.answer()
        await answer_callback(callback, CANCELLED)

    @router.message(NewRaffleForm.title)
    async def set_title(message: Message, state: FSMContext) -> None:
        title = (message.text or "").strip()
        if not title or len(title) > MAX_TITLE_LENGTH:
            await message.answer(BAD_TITLE, reply_markup=cancel_keyboard())
            return
        await state.update_data(title=title)
        await state.set_state(NewRaffleForm.winners)
        await message.answer(STEP_WINNERS, reply_markup=cancel_keyboard())

    @router.message(NewRaffleForm.winners)
    async def set_winners(message: Message, state: FSMContext) -> None:
        winners = parse_positive_int(message.text, MAX_WINNERS)
        if winners is None:
            await message.answer(BAD_WINNERS, reply_markup=cancel_keyboard())
            return
        await state.update_data(winners=winners)
        await state.set_state(NewRaffleForm.deadline)
        await message.answer(STEP_DEADLINE, reply_markup=cancel_keyboard())

    @router.message(NewRaffleForm.deadline)
    async def set_deadline(message: Message, state: FSMContext) -> None:
        deadline = parse_deadline(message.text or "", utcnow())
        if deadline is None:
            await message.answer(BAD_DEADLINE, reply_markup=cancel_keyboard())
            return
        await state.update_data(deadline=deadline.isoformat())
        await state.set_state(NewRaffleForm.channels)
        await message.answer(STEP_CHANNELS, reply_markup=channels_keyboard())

    @router.message(NewRaffleForm.channels)
    async def set_channels(message: Message, state: FSMContext) -> None:
        raw = (message.text or "").strip()
        if not raw:
            await message.answer(NEEDS_TEXT, reply_markup=channels_keyboard())
            return
        channels = parse_channels(raw)
        if not channels and raw.lower() not in {"-", "нет", "no", "skip"}:
            await message.answer(BAD_CHANNELS, reply_markup=channels_keyboard())
            return
        await state.update_data(channels=list(channels))
        await state.set_state(NewRaffleForm.confirm)
        await message.answer(
            render_summary(await state.get_data()), reply_markup=confirm_keyboard()
        )

    @router.callback_query(NewRaffleForm.channels, F.data == SKIP_CHANNELS_DATA)
    async def skip_channels(callback: CallbackQuery, state: FSMContext) -> None:
        await state.update_data(channels=[])
        await state.set_state(NewRaffleForm.confirm)
        await callback.answer()
        message = callback.message
        if isinstance(message, Message):
            await message.answer(
                render_summary(await state.get_data()), reply_markup=confirm_keyboard()
            )

    @router.callback_query(NewRaffleForm.confirm, F.data == CONFIRM_DATA)
    async def confirm(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        await state.clear()
        await callback.answer()
        raffle = await service.create_raffle(
            title=read_text(data, "title"),
            winners_count=read_int(data, "winners"),
            deadline_at=read_deadline(data),
            channels=read_channels(data),
            created_by=callback.from_user.id,
        )
        logger.info("raffle created: id=%s by=%s", raffle.id, callback.from_user.id)
        await answer_callback(
            callback,
            f"Розыгрыш #{raffle.id} создан.\n"
            f"Участники вступают командой /join {raffle.id}.\n"
            f"Тираж — /draw {raffle.id}.",
        )
