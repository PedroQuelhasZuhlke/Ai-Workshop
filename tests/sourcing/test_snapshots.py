"""Tests for `pcbpick.sourcing.suppliers.snapshots.write_snapshot`: content-addressed
ids, real `fetched_at`, and schema compatibility with `FixtureAdapter`.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from pcbpick.contracts.enums import SupplierId
from pcbpick.sourcing.suppliers.fixture import FixtureAdapter
from pcbpick.sourcing.suppliers.snapshots import write_snapshot

_RAW_PART = {
    "mpn": "RC0603FR-0710KL",
    "manufacturer": "YAGEO",
    "category": "resistor",
    "parameters": {},
    "footprint": {"raw_text": "0603"},
    "lifecycle": "active",
    "compliance": ["rohs"],
    "skus": [
        {
            "sku": "MOUSER-71-RC0603FR-10K",
            "packaging": "cut_tape",
            "stock": 1000,
            "moq": 1,
            "spq": 1,
            "price_breaks": [{"quantity": 1, "unit_price": "0.01", "currency": "USD"}],
            "lead_time_days": None,
        }
    ],
}


def test_write_snapshot_creates_content_addressed_file(tmp_path: Path) -> None:
    fetched_at = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)

    written = write_snapshot(
        supplier=SupplierId.MOUSER, parts=[_RAW_PART], fetched_at=fetched_at, snapshot_dir=tmp_path
    )

    assert written.path.exists()
    assert written.snapshot_id.startswith("mouser-")
    assert written.fetched_at == fetched_at

    on_disk = json.loads(written.path.read_text(encoding="utf-8"))
    assert on_disk["snapshot_id"] == written.snapshot_id
    assert on_disk["supplier"] == "mouser"
    assert on_disk["parts"][0]["mpn"] == "RC0603FR-0710KL"


def test_write_snapshot_is_loadable_by_fixture_adapter(tmp_path: Path) -> None:
    fetched_at = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    written = write_snapshot(
        supplier=SupplierId.MOUSER, parts=[_RAW_PART], fetched_at=fetched_at, snapshot_dir=tmp_path
    )

    adapter = FixtureAdapter([written.path], supplier=SupplierId.MOUSER)
    part = adapter.details("RC0603FR-0710KL")

    assert part is not None
    assert part.manufacturer == "Yageo"  # normalized on load, same as any other snapshot
    assert part.snapshot_id == written.snapshot_id
    assert part.fetched_at == fetched_at


def test_write_snapshot_ids_differ_for_different_fetch_times(tmp_path: Path) -> None:
    first = write_snapshot(
        supplier=SupplierId.MOUSER,
        parts=[_RAW_PART],
        fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
        snapshot_dir=tmp_path,
    )
    second = write_snapshot(
        supplier=SupplierId.MOUSER,
        parts=[_RAW_PART],
        fetched_at=datetime(2026, 2, 1, tzinfo=UTC),
        snapshot_dir=tmp_path,
    )

    assert first.snapshot_id != second.snapshot_id


def test_write_snapshot_ids_match_for_identical_content_and_time(tmp_path: Path) -> None:
    fetched_at = datetime(2026, 1, 1, tzinfo=UTC)

    first = write_snapshot(
        supplier=SupplierId.MOUSER, parts=[_RAW_PART], fetched_at=fetched_at, snapshot_dir=tmp_path
    )
    second = write_snapshot(
        supplier=SupplierId.MOUSER, parts=[_RAW_PART], fetched_at=fetched_at, snapshot_dir=tmp_path
    )

    assert first.snapshot_id == second.snapshot_id
