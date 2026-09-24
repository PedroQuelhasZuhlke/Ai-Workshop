"""Unit tests for `pcbpick.pipeline.diff`'s structural artifact diffing."""

from pcbpick.pipeline.diff import FieldChange, diff_json_values


def test_top_level_added_removed_changed() -> None:
    before = {"unchanged": 1, "changed": "old", "removed": "gone"}
    after = {"unchanged": 1, "changed": "new", "added": "new-value"}

    diff = diff_json_values(before, after)

    assert not diff.is_identical
    # `_diff_dict` walks `sorted(set(before) | set(after))`, so output order is
    # deterministic: "added", "changed", "removed".
    assert diff.changes == [
        FieldChange(path="added", kind="added", after="new-value"),
        FieldChange(path="changed", kind="changed", before="old", after="new"),
        FieldChange(path="removed", kind="removed", before="gone"),
    ]


def test_identical_values_produce_no_changes() -> None:
    value = {"a": 1, "b": [1, 2, 3]}

    diff = diff_json_values(value, value)

    assert diff.is_identical
    assert diff.changes == []


def test_nested_dict_paths_are_dotted() -> None:
    before = {"outer": {"inner": 1, "stable": "x"}}
    after = {"outer": {"inner": 2, "stable": "x"}}

    diff = diff_json_values(before, after)

    assert diff.changes == [FieldChange(path="outer.inner", kind="changed", before=1, after=2)]


def test_list_diffed_by_requirement_id() -> None:
    before = [
        {"requirement_id": "R1", "value": 10},
        {"requirement_id": "R2", "value": 20},
    ]
    after = [
        {"requirement_id": "R2", "value": 30},
        {"requirement_id": "R3", "value": 40},
    ]

    diff = diff_json_values(before, after)

    # `_diff_list_by_id` emits removed (sorted by id), then added (sorted by id),
    # then changed (sorted by id) -- deterministic order, so asserted as a list.
    assert diff.changes == [
        FieldChange(
            path="[requirement_id=R1]",
            kind="removed",
            before={"requirement_id": "R1", "value": 10},
        ),
        FieldChange(
            path="[requirement_id=R3]", kind="added", after={"requirement_id": "R3", "value": 40}
        ),
        FieldChange(path="[requirement_id=R2].value", kind="changed", before=20, after=30),
    ]


def test_list_diffed_by_mpn_when_requirement_id_is_absent() -> None:
    before = [{"mpn": "MPN-A", "price": "1.00"}]
    after = [{"mpn": "MPN-A", "price": "2.00"}]

    diff = diff_json_values(before, after)

    assert diff.changes == [
        FieldChange(path="[mpn=MPN-A].price", kind="changed", before="1.00", after="2.00")
    ]


def test_reordering_an_id_keyed_list_is_not_a_diff() -> None:
    before = [
        {"requirement_id": "R1", "value": 1},
        {"requirement_id": "R2", "value": 2},
    ]
    after = [
        {"requirement_id": "R2", "value": 2},
        {"requirement_id": "R1", "value": 1},
    ]

    diff = diff_json_values(before, after)

    assert diff.is_identical


def test_reordering_a_scalar_list_is_not_a_diff() -> None:
    before = [1, 2, 3]
    after = [3, 2, 1]

    diff = diff_json_values(before, after)

    assert diff.is_identical


def test_multiset_fallback_for_lists_with_no_stable_id() -> None:
    """No `_ID_KEY_CANDIDATES` key present: a changed item shows as remove+add,
    not a field-level change -- coarser, but still order-independent."""
    before = {"items": [{"foo": 1}, {"foo": 2}]}
    after = {"items": [{"foo": 1}, {"foo": 3}]}

    diff = diff_json_values(before, after)

    # `_diff_list_as_multiset` emits removed keys (sorted) before added keys (sorted).
    assert diff.changes == [
        FieldChange(path="items", kind="removed", before={"foo": 2}),
        FieldChange(path="items", kind="added", after={"foo": 3}),
    ]


def test_multiset_fallback_reordering_is_not_a_diff() -> None:
    before = {"items": [{"foo": 1}, {"foo": 2}]}
    after = {"items": [{"foo": 2}, {"foo": 1}]}

    diff = diff_json_values(before, after)

    assert diff.is_identical


def test_duplicate_requirement_id_falls_back_to_multiset_instead_of_collapsing() -> None:
    """Several `PartCandidate`s share one `requirement_id` (the normal shape once
    `source`/`policy`/`evaluate` land in `STAGES`) -- `requirement_id` is not a
    stable per-item id there, so id-keyed diffing must not collapse distinct
    candidates onto the same dict key and silently hide a real change. Here
    `requirement_id` repeats in `before` (so it's rejected), and `mpn` -- though
    unique in `before` -- is only trivially "unique" in `after` because `after` has
    a single item; `_detect_id_key` picks `requirement_id` for the single-item
    `after` list (first candidate checked, trivially unique) and `mpn` for
    `before`, so the two sides disagree on the key and the multiset fallback is
    used -- conservatively correct, since no key can be trusted as identical on
    both sides."""
    before = [
        {"requirement_id": "R1", "mpn": "MPN-A"},
        {"requirement_id": "R1", "mpn": "MPN-B"},
    ]
    after = [
        {"requirement_id": "R1", "mpn": "MPN-A"},
        # MPN-B's candidate disappeared entirely (e.g. a policy rule change) --
        # this must be visible, not hidden behind a same-requirement_id collapse.
    ]

    diff = diff_json_values(before, after)

    assert not diff.is_identical
    assert diff.changes == [
        FieldChange(path="$", kind="removed", before={"requirement_id": "R1", "mpn": "MPN-B"})
    ]


def test_id_key_unique_on_one_side_but_not_the_other_falls_back_to_multiset() -> None:
    """`mpn` is unique in `before` but repeats in `after` -- not a safe shared
    identity for id-keyed diffing on either side, so both must use the multiset
    fallback rather than trusting a key that's only unique on one side."""
    before = [{"mpn": "MPN-A", "value": 1}]
    after = [{"mpn": "MPN-A", "value": 1}, {"mpn": "MPN-A", "value": 2}]

    diff = diff_json_values(before, after)

    assert not diff.is_identical
    assert diff.changes == [FieldChange(path="$", kind="added", after={"mpn": "MPN-A", "value": 2})]
