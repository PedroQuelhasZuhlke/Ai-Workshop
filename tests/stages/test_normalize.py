"""Stage tests for `normalize`: golden-path against the hand-verified edge-case
fixture, one test per `BLOCKING` issue code, LLM-fallback behavior, and a
determinism check, per `.github/instructions/pipeline-stages.instructions.md`.
"""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from random import Random

import pytest

from pcbpick.contracts.enums import ComponentCategory
from pcbpick.ingest.stage import IngestInput, IngestStage
from pcbpick.llm.client import LLMClient
from pcbpick.llm.fakes import FakeLLMClient
from pcbpick.normalize.stage import NormalizeStage
from pcbpick.pipeline.context import PipelineConfig, StageContext
from pcbpick.pipeline.results import Severity

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "boms"
EDGE_CASES_FILE = "normalize_edge_cases.csv"

_CONFIDENCE_HIGH_THRESHOLD = 0.9
_CONFIDENCE_LOW_THRESHOLD = 0.5


def _make_ctx() -> StageContext:
    return StageContext(
        run_id="test-run",
        now=datetime(2026, 9, 22, tzinfo=UTC),
        rng=Random("test-run"),
        config=PipelineConfig(),
    )


def _load_expected() -> dict:
    path = FIXTURES_DIR / "normalize_edge_cases.expected.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _run_normalize(fixture_name: str, llm_client: LLMClient | None = None):
    content = (FIXTURES_DIR / fixture_name).read_bytes()
    ctx = _make_ctx()
    ingest_result = (
        IngestStage().run(IngestInput(file_name=fixture_name, content=content), ctx).output
    )
    stage = NormalizeStage(llm_client=llm_client)
    return stage.run(ingest_result, ctx)


def _confidence_tier(score: float) -> str:
    if score >= _CONFIDENCE_HIGH_THRESHOLD:
        return "high"
    if score >= _CONFIDENCE_LOW_THRESHOLD:
        return "medium"
    return "low"


@pytest.mark.parametrize("row", _load_expected()["rows"], ids=lambda row: row["case"])
def test_edge_case_rows_match_hand_verified_expectations(row: dict) -> None:
    result = _run_normalize(EDGE_CASES_FILE)
    requirement = result.output[row["row_index"]]

    assert requirement.reference_designators == row["reference_designators"]
    assert requirement.category.value == row["expected_category"]
    assert sorted(requirement.unresolved) == sorted(row["expected_unresolved"])
    assert requirement.criticality.value == row["expected_criticality"]
    assert _confidence_tier(requirement.confidence.score) == row["expected_confidence_tier"]

    for name, expected_param in row["expected_parameters"].items():
        actual = requirement.parameters.get(name)
        assert actual is not None, f"expected parameter {name!r} to be resolved"
        assert actual.value == Decimal(expected_param["value"])
        if "min" in expected_param:
            assert actual.min == Decimal(expected_param["min"])
        if "max" in expected_param:
            assert actual.max == Decimal(expected_param["max"])


def test_ambiguous_rows_never_guess_a_value() -> None:
    """Every row with a non-empty `unresolved` must have NOTHING guessed in its place."""
    expected = _load_expected()
    result = _run_normalize(EDGE_CASES_FILE)

    for row in expected["rows"]:
        if not row["expected_unresolved"]:
            continue
        requirement = result.output[row["row_index"]]
        for dotted in row["expected_unresolved"]:
            if dotted.startswith("parameters."):
                param_name = dotted.removeprefix("parameters.")
                assert param_name not in requirement.parameters, (
                    f"{row['case']}: {param_name!r} must not be silently filled in "
                    "while also being reported unresolved"
                )


def test_every_unresolved_requirement_raises_a_blocking_issue() -> None:
    result = _run_normalize(EDGE_CASES_FILE)
    blocking_ids = {
        issue.item_id
        for issue in result.issues
        if issue.code == "normalization_unresolved" and issue.severity == Severity.BLOCKING
    }
    for requirement in result.output:
        if requirement.unresolved:
            assert requirement.requirement_id in blocking_ids


def test_dnp_lines_are_excluded_from_requirements_not_dropped_silently() -> None:
    content = (
        b"Designator,Value,Description,Package,Qty,DNP\n"
        b"R1,10k,Resistor 1%,RESC1608X55N,1,\n"
        b"R2,4k7,Resistor 1%,RESC1608X55N,1,DNP\n"
    )
    ctx = _make_ctx()
    ingest_result = IngestStage().run(IngestInput(file_name="dnp.csv", content=content), ctx).output
    result = NormalizeStage().run(ingest_result, ctx)

    assert [r.reference_designators for r in result.output] == [["R1"]]
    assert any(issue.code == "dnp_lines_excluded" for issue in result.issues)


def test_llm_fallback_unavailable_by_default_is_info_not_blocking() -> None:
    result = _run_normalize(EDGE_CASES_FILE)
    fallback_issues = [i for i in result.issues if i.code == "llm_fallback_unavailable"]
    assert fallback_issues
    assert all(issue.severity == Severity.INFO for issue in fallback_issues)


def test_llm_fallback_is_used_only_for_a_fully_unclassified_row_and_stays_unresolved() -> None:
    fake_response = json.dumps(
        {
            "category": "ic_analog",
            "parameters": {},
            "footprint": None,
            "compliance_required": [],
            "notes": "inferred from 'widget' description",
        }
    )
    client = FakeLLMClient(model_id="fake-1", default_response=fake_response)

    result = _run_normalize(EDGE_CASES_FILE, llm_client=client)
    unparseable = next(r for r in result.output if r.notes and "Special order widget" in r.notes)

    # A successful fallback may change the category, but the field stays in
    # `unresolved` and the confidence stays low — `llm_inferred` never satisfies a
    # hard check on its own.
    assert unparseable.category == ComponentCategory.IC_ANALOG
    assert "category" in unparseable.unresolved
    assert unparseable.confidence.score < _CONFIDENCE_HIGH_THRESHOLD


def test_normalize_is_deterministic_across_runs() -> None:
    first = _run_normalize(EDGE_CASES_FILE)
    second = _run_normalize(EDGE_CASES_FILE)

    first_json = [r.model_dump_json() for r in first.output]
    second_json = [r.model_dump_json() for r in second.output]
    assert first_json == second_json
    assert [(i.severity, i.code, i.message, i.item_id) for i in first.issues] == [
        (i.severity, i.code, i.message, i.item_id) for i in second.issues
    ]


@pytest.mark.parametrize(
    "fixture_name", ["altium_bom.csv", "kicad_bom.csv", "eagle_bom.csv", "orcad_bom.csv"]
)
def test_existing_ingest_fixtures_normalize_without_crashing(fixture_name: str) -> None:
    """Smoke test: every M1 fixture must survive the full normalize stage, even if
    some ICs land with an unresolved category (no rich description column to route
    on) — the point is no exception and no guessed value, not perfect coverage.
    """
    result = _run_normalize(fixture_name)
    assert result.output
    for requirement in result.output:
        # Never a guess: a category we couldn't determine is reported, not invented.
        if requirement.category == ComponentCategory.UNKNOWN:
            assert "category" in requirement.unresolved


def test_missing_required_parameter_is_blocking_and_unresolved() -> None:
    content = b"Designator,Value,Description\nR1,0R,Resistor jumper\n"
    ctx = _make_ctx()
    ingest_result = (
        IngestStage().run(IngestInput(file_name="jumper.csv", content=content), ctx).output
    )
    result = NormalizeStage().run(ingest_result, ctx)

    requirement = result.output[0]
    assert requirement.unresolved == ["parameters.tolerance_pct"]
    assert any(
        issue.code == "normalization_unresolved" and issue.severity == Severity.BLOCKING
        for issue in result.issues
    )
