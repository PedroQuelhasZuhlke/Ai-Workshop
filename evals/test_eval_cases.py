"""Golden-BOM eval suite entry point: `pytest evals/`.

Drives `src/pcbpick/pipeline/eval_runner.py` against every `evals/cases/*/case.json`
and asserts every field actually present in that case's `expect` block passes --
never an aggregate boolean. A failing field's `FieldScore.detail` is included in the
assertion message so a broken run reports exactly which field regressed, not just
which case.
"""

from pathlib import Path

import pytest

from pcbpick.pipeline.eval_runner import EvalCaseResult, discover_case_paths, run_eval_case

_CASES_ROOT = Path(__file__).resolve().parent / "cases"

# Per-case fields known to fail against the case file's own hand-verified `expect`
# map, for a documented, deliberate reason -- see each case's own
# `hand_verified_reasoning` for the "M8 delta" note explaining when/why an entry was
# added or removed. Empty today: the one prior entry
# (`kicad_bom_ingest_normalize_all_unresolved`'s `footprint.package_code`) was a
# genuine gap in `normalize/package.py`'s footprint recognition, fixed directly
# (`_MECHANICAL_FAMILIES`) rather than left as a permanent known-issue.
_KNOWN_CASE_FILE_DEFECTS: dict[str, frozenset[str]] = {}


def _case_ids() -> list[str]:
    return [path.parent.name for path in discover_case_paths(_CASES_ROOT)]


@pytest.mark.parametrize("case_path", discover_case_paths(_CASES_ROOT), ids=_case_ids())
def test_eval_case_passes(case_path: Path) -> None:
    result = run_eval_case(case_path)
    _print_report(result)
    known = _KNOWN_CASE_FILE_DEFECTS.get(result.case_id, frozenset())
    unexpected = [s for s in result.failed_scores if s.field not in known]
    assert not unexpected, f"{result.case_id}: {len(unexpected)} field(s) failed:\n" + "\n".join(
        f"  - {s.field}: {s.detail}" for s in unexpected
    )


def test_eval_suite_is_deterministic_across_runs() -> None:
    for case_path in discover_case_paths(_CASES_ROOT):
        first = run_eval_case(case_path)
        second = run_eval_case(case_path)
        assert first.field_scores == second.field_scores


def _print_report(result: EvalCaseResult) -> None:
    known = _KNOWN_CASE_FILE_DEFECTS.get(result.case_id, frozenset())
    unexpected_failures = [s for s in result.failed_scores if s.field not in known]
    status = "PASS" if not unexpected_failures else "FAIL"
    print(f"\n[{status}] {result.case_id} ({len(result.field_scores)} field(s) scored)")
    for score in result.field_scores:
        if score.passed:
            mark = "ok"
        elif score.field in known:
            mark = "KNOWN-ISSUE"
        else:
            mark = "FAIL"
        print(f"    [{mark}] {score.field}: {score.detail}")
