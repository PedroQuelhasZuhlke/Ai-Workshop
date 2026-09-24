"""Content-addressed snapshot writer for live supplier adapters.

Every live `search()`/`details()`/`offers()` call that reaches the network writes one
JSON file here, in the same schema `FixtureAdapter` reads (see that module's
docstring for the exact shape) — never a time-addressed cache that can expire and
disappear, per `.github/instructions/supplier-adapters.instructions.md`. `snapshot_id`
is derived from the written content itself, so a caller can never fabricate one that
doesn't correspond to what is actually on disk.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pcbpick.contracts.enums import SupplierId


@dataclass(frozen=True)
class WrittenSnapshot:
    snapshot_id: str
    fetched_at: datetime
    path: Path


def write_snapshot(
    *,
    supplier: SupplierId,
    parts: list[dict[str, Any]],
    fetched_at: datetime,
    snapshot_dir: Path,
) -> WrittenSnapshot:
    """Writes `parts` (already shaped like `FixtureAdapter`'s snapshot `"parts"` array)
    to a content-addressed file under `snapshot_dir`, creating it if needed.
    """
    fetched_at_iso = fetched_at.isoformat().replace("+00:00", "Z")
    body = {"supplier": supplier.value, "fetched_at": fetched_at_iso, "parts": parts}
    # sort_keys makes the hash stable regardless of dict insertion order.
    content = json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
    snapshot_id = f"{supplier.value}-{digest}"

    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_dir / f"{snapshot_id}.json"
    record = {"snapshot_id": snapshot_id, **body}
    path.write_text(json.dumps(record, indent=2, sort_keys=True, default=str), encoding="utf-8")

    return WrittenSnapshot(snapshot_id=snapshot_id, fetched_at=fetched_at, path=path)
