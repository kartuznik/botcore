"""Parsing of admin input for the raffle form and commands."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from modules.raffle.form import BAD_DEADLINE_FORMAT, BAD_DEADLINE_PAST, STEP_DEADLINE
from modules.raffle.parsing import (
    DeadlineError,
    DeadlineFormatError,
    DeadlinePastError,
    parse_channels,
    parse_deadline,
    parse_demo_args,
)

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)


def test_bare_number_is_read_as_hours() -> None:
    assert parse_deadline("2", NOW) == NOW + timedelta(hours=2)
    assert parse_deadline(" 12 ", NOW) == NOW + timedelta(hours=12)


def test_relative_deadlines() -> None:
    assert parse_deadline("30m", NOW) == NOW + timedelta(minutes=30)
    assert parse_deadline("2h", NOW) == NOW + timedelta(hours=2)
    assert parse_deadline("3d", NOW) == NOW + timedelta(days=3)


def test_absolute_deadlines() -> None:
    assert parse_deadline("2026-09-20 18:00", NOW) == datetime(2026, 9, 20, 18, 0, tzinfo=UTC)
    assert parse_deadline("20.09.2026", NOW) == datetime(2026, 9, 20, 23, 59, tzinfo=UTC)


@pytest.mark.parametrize("raw", ["2026-09-01 18:00", "01.01.2020", "0", "0h"])
def test_past_moments_raise_past_error(raw: str) -> None:
    with pytest.raises(DeadlinePastError):
        parse_deadline(raw, NOW)


@pytest.mark.parametrize("raw", ["abc", "", "   ", "-3", "2x", "завтра", "2026-13-40 18:00"])
def test_garbage_raises_format_error(raw: str) -> None:
    with pytest.raises(DeadlineFormatError):
        parse_deadline(raw, NOW)


def test_the_two_deadline_errors_cannot_collapse_into_one() -> None:
    assert issubclass(DeadlineFormatError, DeadlineError)
    assert issubclass(DeadlinePastError, DeadlineError)
    assert not issubclass(DeadlineFormatError, DeadlinePastError)
    assert not issubclass(DeadlinePastError, DeadlineFormatError)


def test_format_and_past_messages_stay_separate() -> None:
    assert BAD_DEADLINE_FORMAT != BAD_DEADLINE_PAST
    assert "30m" in BAD_DEADLINE_FORMAT
    assert "2026-09-20 18:00" in BAD_DEADLINE_FORMAT
    # the "already passed" answer must not repeat the format cheat sheet
    assert "30m" not in BAD_DEADLINE_PAST
    assert "2026" not in BAD_DEADLINE_PAST


def test_deadline_step_mentions_the_bare_number_shortcut() -> None:
    assert "поймём как часы" in STEP_DEADLINE


def test_channels_are_normalized_and_deduplicated() -> None:
    assert parse_channels("@one, t.me/two, https://t.me/one, -1001234567890") == (
        "@one",
        "@two",
        "-1001234567890",
    )
    assert parse_channels("нет") == ()


def test_demo_arguments() -> None:
    default = parse_demo_args(None, 10)
    assert (default.participants, default.winners, default.user_ids) == (10, 1, None)

    sized = parse_demo_args("20 3", 10)
    assert (sized.participants, sized.winners, sized.user_ids) == (20, 3, None)

    listed = parse_demo_args("11,22,33 2", 10)
    assert listed.user_ids == (11, 22, 33)
    assert (listed.participants, listed.winners) == (3, 2)
