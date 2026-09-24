"""Structural artifact diffing: reports which fields/list-items changed, were added,
or removed between two JSON-shaped values -- never a raw byte/line diff.

List items keyed by a stable id (`requirement_id`, `mpn`, `row_index`, `sku`, ...,
see `_ID_KEY_CANDIDATES`) are diffed by that id, so reordering never spuriously
shows up as a full rewrite; list items with no detectable stable id fall back to an
order-insensitive multiset comparison (still order-independent, just coarser: a
changed item shows as one remove + one add rather than a field-level change).
"""

import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal

ChangeKind = Literal["added", "removed", "changed"]

# Checked in this order against a list's items (which must be dicts) to find a
# stable identity key for id-keyed diffing. First key present in *every* item wins.
_ID_KEY_CANDIDATES: tuple[str, ...] = (
    "requirement_id",
    "mpn",
    "row_index",
    "sku",
    "target_field",
)


@dataclass(frozen=True)
class FieldChange:
    """One structural difference: a dotted/bracketed path plus what changed."""

    path: str
    kind: ChangeKind
    before: Any = None
    after: Any = None


@dataclass(frozen=True)
class ArtifactDiff:
    """Every `FieldChange` found between two artifact payloads."""

    changes: list[FieldChange] = field(default_factory=list)

    @property
    def is_identical(self) -> bool:
        return not self.changes


# Stored run artifacts are ordinary pipeline output, never expected to nest anywhere
# near this deep -- this exists only to turn a pathological/corrupted artifact into a
# clean, reported error instead of a raw `RecursionError`.
_MAX_DIFF_DEPTH = 100


def diff_json_values(before: Any, after: Any) -> ArtifactDiff:
    """Structural diff between two already-deserialized JSON-shaped values."""
    return ArtifactDiff(changes=_diff_value("", before, after, depth=0))


def _diff_value(path: str, before: Any, after: Any, *, depth: int) -> list[FieldChange]:
    if depth > _MAX_DIFF_DEPTH:
        raise ValueError(f"artifact nesting exceeds max diff depth ({_MAX_DIFF_DEPTH}) at {path!r}")
    if isinstance(before, dict) and isinstance(after, dict):
        return _diff_dict(path, before, after, depth=depth)
    if isinstance(before, list) and isinstance(after, list):
        return _diff_list(path, before, after, depth=depth)
    if before != after:
        return [FieldChange(path=path or "$", kind="changed", before=before, after=after)]
    return []


def _diff_dict(
    path: str, before: dict[str, Any], after: dict[str, Any], *, depth: int
) -> list[FieldChange]:
    changes: list[FieldChange] = []
    for key in sorted(set(before) | set(after)):
        sub_path = f"{path}.{key}" if path else key
        if key not in before:
            changes.append(FieldChange(path=sub_path, kind="added", after=after[key]))
        elif key not in after:
            changes.append(FieldChange(path=sub_path, kind="removed", before=before[key]))
        else:
            changes.extend(_diff_value(sub_path, before[key], after[key], depth=depth + 1))
    return changes


def _detect_id_key(items: list[Any]) -> str | None:
    """A candidate id key only counts as a stable id if it is both present on every
    item *and* unique across the list -- a key that repeats (e.g. `requirement_id`
    on a `PartCandidate` list, where several candidates share one requirement) would
    silently collapse distinct items onto the same dict key in `_diff_list_by_id`,
    hiding a real divergence behind a false "identical" result. Falls back to the
    order-insensitive multiset comparison instead when no candidate is unique.
    """
    if not items or not all(isinstance(item, dict) for item in items):
        return None
    for candidate in _ID_KEY_CANDIDATES:
        if not all(candidate in item for item in items):
            continue
        keys = [item[candidate] for item in items]
        if len(set(keys)) == len(keys):
            return candidate
    return None


def _diff_list(path: str, before: list[Any], after: list[Any], *, depth: int) -> list[FieldChange]:
    # Require the same key to be independently unique on *both* sides -- a key
    # that's unique in `before` but repeats in `after` (or vice versa) is not a
    # safe shared identity for id-keyed diffing.
    before_key = _detect_id_key(before)
    after_key = _detect_id_key(after)
    id_key = before_key if before_key is not None and before_key == after_key else None
    if id_key is not None:
        return _diff_list_by_id(path, before, after, id_key, depth=depth)
    return _diff_list_as_multiset(path, before, after)


def _diff_list_by_id(
    path: str, before: list[Any], after: list[Any], id_key: str, *, depth: int
) -> list[FieldChange]:
    before_by_id = {item[id_key]: item for item in before}
    after_by_id = {item[id_key]: item for item in after}
    changes: list[FieldChange] = []

    for item_id in sorted(set(before_by_id) - set(after_by_id), key=str):
        item_path = f"{path}[{id_key}={item_id}]"
        changes.append(FieldChange(path=item_path, kind="removed", before=before_by_id[item_id]))
    for item_id in sorted(set(after_by_id) - set(before_by_id), key=str):
        item_path = f"{path}[{id_key}={item_id}]"
        changes.append(FieldChange(path=item_path, kind="added", after=after_by_id[item_id]))
    for item_id in sorted(set(before_by_id) & set(after_by_id), key=str):
        item_path = f"{path}[{id_key}={item_id}]"
        changes.extend(
            _diff_value(item_path, before_by_id[item_id], after_by_id[item_id], depth=depth + 1)
        )
    return changes


def _diff_list_as_multiset(path: str, before: list[Any], after: list[Any]) -> list[FieldChange]:
    """No stable id available: compare as an order-insensitive multiset of items.

    A changed item (same "slot", different content) shows as one removal + one
    addition rather than a field-level change -- coarser than the id-keyed path, but
    still never a spurious full-list rewrite from reordering alone.
    """

    def _key(item: Any) -> str:
        return json.dumps(item, sort_keys=True, default=str)

    before_counts = Counter(_key(item) for item in before)
    after_counts = Counter(_key(item) for item in after)
    changes: list[FieldChange] = []

    removed = before_counts - after_counts
    added = after_counts - before_counts
    for key in sorted(removed):
        for _ in range(removed[key]):
            changes.append(FieldChange(path=path or "$", kind="removed", before=json.loads(key)))
    for key in sorted(added):
        for _ in range(added[key]):
            changes.append(FieldChange(path=path or "$", kind="added", after=json.loads(key)))
    return changes
