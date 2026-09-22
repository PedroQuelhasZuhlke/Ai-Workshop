"""Stage tests for `ingest`: golden-path per fixture, one test per BLOCKING issue code,
and a determinism check, per `.github/instructions/pipeline-stages.instructions.md`.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from random import Random

import pytest

from pcbpick.contracts.enums import MappingMethod
from pcbpick.ingest.mapping_store import MappingProfileStore
from pcbpick.ingest.stage import IngestInput, IngestStage
from pcbpick.pipeline.context import PipelineConfig, StageContext
from pcbpick.pipeline.results import Severity, StageResult

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "boms"

WELL_KNOWN_FIXTURES = [
    "altium_bom.csv",
    "kicad_bom.csv",
    "eagle_bom.csv",
    "orcad_bom.csv",
    "kicad_edge_cases.csv",
]
ALL_FIXTURES = [*WELL_KNOWN_FIXTURES, "unknown_format.xlsx"]


def _make_ctx() -> StageContext:
    return StageContext(
        run_id="test-run",
        now=datetime(2026, 9, 22, tzinfo=UTC),
        rng=Random("test-run"),
        config=PipelineConfig(),
    )


def _load_expected(fixture_name: str) -> dict:
    stem = fixture_name.rsplit(".", 1)[0]
    path = FIXTURES_DIR / f"{stem}.expected.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _run_ingest(fixture_name: str, project_mapping: dict[str, str] | None = None) -> StageResult:
    content = (FIXTURES_DIR / fixture_name).read_bytes()
    stage = IngestStage()
    inp = IngestInput(file_name=fixture_name, content=content, project_mapping=project_mapping)
    return stage.run(inp, _make_ctx())


@pytest.mark.parametrize("fixture_name", ALL_FIXTURES)
def test_golden_path_matches_hand_verified_expectations(fixture_name: str) -> None:
    expected = _load_expected(fixture_name)
    result = _run_ingest(fixture_name)
    ingest_result = result.output

    expected_profile = None if expected["eda_profile"] == "unknown" else expected["eda_profile"]
    assert ingest_result.mapping_proposal.eda_profile == expected_profile
    assert ingest_result.mapping_proposal.header_row_index == expected["header_row_index"]
    assert len(ingest_result.lines) == expected["row_count"]

    for expected_row, line in zip(expected["rows"], ingest_result.lines, strict=True):
        assert line.row_index == expected_row["row_index"]
        assert line.reference_designators == expected_row["reference_designators"]
        assert line.quantity == expected_row["quantity_stated"]
        assert line.populate == (not expected_row.get("dnp", False))


@pytest.mark.parametrize("fixture_name", WELL_KNOWN_FIXTURES)
def test_known_eda_profiles_do_not_require_confirmation(fixture_name: str) -> None:
    result = _run_ingest(fixture_name)
    assert result.output.mapping_proposal.requires_confirmation is False
    assert not any(issue.code == "mapping_requires_confirmation" for issue in result.issues)


def test_range_with_gap_expands_every_designator() -> None:
    result = _run_ingest("kicad_edge_cases.csv")
    line = next(line for line in result.output.lines if "U5" in line.reference_designators)
    assert line.reference_designators == ["U1", "U2", "U3", "U5"]


def test_quantity_mismatch_is_flagged_not_fixed() -> None:
    expected = _load_expected("kicad_edge_cases.csv")
    result = _run_ingest("kicad_edge_cases.csv")

    mismatch_rows = [row for row in expected["rows"] if row["quantity_mismatch"]]
    assert mismatch_rows, "fixture must contain at least one quantity/refdes mismatch"

    for expected_row in mismatch_rows:
        line = result.output.lines[expected_row["row_index"]]
        # stated quantity is preserved verbatim -- ingest never silently corrects it.
        assert line.quantity == expected_row["quantity_stated"]
        assert len(line.reference_designators) == expected_row["quantity_expected"]
        assert any(
            issue.code == "quantity_mismatch"
            and issue.item_id == f"row-{expected_row['row_index']}"
            for issue in result.issues
        )


def test_dnp_rows_are_carried_through_not_dropped() -> None:
    for fixture_name in ("kicad_bom.csv", "kicad_edge_cases.csv"):
        expected = _load_expected(fixture_name)
        result = _run_ingest(fixture_name)
        for expected_row in expected["rows"]:
            if not expected_row.get("dnp"):
                continue
            line = result.output.lines[expected_row["row_index"]]
            assert line.populate is False
            assert line.reference_designators, "DNP line must still be present, not dropped"


def test_unknown_format_produces_a_mapping_proposal_not_an_error() -> None:
    expected = _load_expected("unknown_format.xlsx")

    result = _run_ingest("unknown_format.xlsx")  # must not raise

    proposal = result.output.mapping_proposal
    assert proposal.eda_profile is None
    assert proposal.requires_confirmation is True
    assert "reference_designators" in proposal.missing_required_fields
    assert any(issue.code == "mapping_requires_confirmation" for issue in result.issues)
    assert len(result.output.lines) == expected["row_count"]
    assert all(line.reference_designators == [] for line in result.output.lines)
    assert all(line.quantity is None for line in result.output.lines)


def test_duplicate_reference_designators_across_lines_are_blocking() -> None:
    content = b"Designator,Value,Quantity\nR1,10k,1\nR1,4k7,1\n"
    stage = IngestStage()

    result = stage.run(IngestInput(file_name="dupes.csv", content=content), _make_ctx())

    assert any(
        issue.code == "duplicate_reference_designator" and issue.severity == Severity.BLOCKING
        for issue in result.issues
    )


def test_invalid_reference_designator_range_is_a_warning_not_dropped() -> None:
    content = b"Designator,Value,Quantity\nR1-C4,10k,1\n"
    stage = IngestStage()

    result = stage.run(IngestInput(file_name="bad_range.csv", content=content), _make_ctx())

    line = result.output.lines[0]
    assert line.reference_designators == ["R1-C4"]  # passed through unexpanded, not dropped
    assert any(
        issue.code == "invalid_refdes_range" and issue.severity == Severity.WARNING
        for issue in result.issues
    )


def test_project_memory_mapping_resolves_an_otherwise_unknown_format(tmp_path: Path) -> None:
    store = MappingProfileStore(tmp_path / "mapping_profiles")
    store.save("proj-1", {"reference_designators": "Where", "quantity": "How Many"})

    result = _run_ingest("unknown_format.xlsx", project_mapping=store.load("proj-1"))

    proposal = result.output.mapping_proposal
    refdes_mapping = next(m for m in proposal.mappings if m.target_field == "reference_designators")
    assert refdes_mapping.method == MappingMethod.PROJECT_MEMORY
    assert refdes_mapping.source_column == "Where"
    assert result.output.lines[0].reference_designators == ["R1", "R2", "R3"]


@pytest.mark.parametrize("fixture_name", ALL_FIXTURES)
def test_ingest_is_deterministic_across_runs(fixture_name: str) -> None:
    first = _run_ingest(fixture_name)
    second = _run_ingest(fixture_name)

    assert first.output.model_dump_json() == second.output.model_dump_json()
    assert [(i.severity, i.code, i.message, i.item_id) for i in first.issues] == [
        (i.severity, i.code, i.message, i.item_id) for i in second.issues
    ]
