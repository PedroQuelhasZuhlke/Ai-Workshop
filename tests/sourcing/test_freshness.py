"""Tests for the pure `pcbpick.sourcing.freshness.is_stale` freshness check."""

from datetime import UTC, datetime, timedelta

from pcbpick.sourcing.freshness import is_stale


def test_fresh_offer_within_max_age_is_not_stale() -> None:
    fetched_at = datetime(2026, 1, 1, tzinfo=UTC)
    now = fetched_at + timedelta(days=10)

    assert is_stale(fetched_at, now=now, max_age=timedelta(days=90)) is False


def test_offer_older_than_max_age_is_stale() -> None:
    fetched_at = datetime(2026, 1, 1, tzinfo=UTC)
    now = fetched_at + timedelta(days=91)

    assert is_stale(fetched_at, now=now, max_age=timedelta(days=90)) is True


def test_offer_exactly_at_max_age_boundary_is_not_stale() -> None:
    fetched_at = datetime(2026, 1, 1, tzinfo=UTC)
    now = fetched_at + timedelta(days=90)

    assert is_stale(fetched_at, now=now, max_age=timedelta(days=90)) is False
