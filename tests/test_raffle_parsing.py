"""Parsing of admin input for the raffle form and commands."""

from __future__ import annotations

from datetime import UTC, datetime

from modules.raffle.parsing import parse_channels, parse_deadline, parse_demo_args

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)


def test_relative_deadlines() -> None:
    assert parse_deadline("30m", NOW) == datetime(2026, 9, 14, 12, 30, tzinfo=UTC)
    assert parse_deadline("2h", NOW) == datetime(2026, 9, 14, 14, 0, tzinfo=UTC)
    assert parse_deadline("3d", NOW) == datetime(2026, 9, 17, 12, 0, tzinfo=UTC)


def test_absolute_deadlines_and_rejections() -> None:
    assert parse_deadline("2026-09-20 18:00", NOW) == datetime(2026, 9, 20, 18, 0, tzinfo=UTC)
    assert parse_deadline("2026-09-01 18:00", NOW) is None  # in the past
    assert parse_deadline("завтра", NOW) is None


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
