"""Stage tests for `expand`: requirement -> query mapping, unresolved-requirement
exclusion, and determinism, per
`.github/instructions/pipeline-stages.instructions.md`.
"""

from datetime import UTC, datetime
from decimal import Decimal
from random import Random

from pcbpick.contracts.common import Confidence, Footprint, MpnRef, ParameterValue
from pcbpick.contracts.enums import ComplianceTag, ComponentCategory, Criticality, ValueSource
from pcbpick.contracts.requirement import NormalizedRequirement
from pcbpick.pipeline.context import PipelineConfig, StageContext
from pcbpick.pipeline.results import Severity
from pcbpick.sourcing.expand import ExpandStage


def _make_ctx() -> StageContext:
    return StageContext(
        run_id="test-run",
        now=datetime(2026, 9, 22, tzinfo=UTC),
        rng=Random("test-run"),
        config=PipelineConfig(),
    )


def _requirement(
    requirement_id: str,
    *,
    unresolved: list[str] | None = None,
    specified_mpn: MpnRef | None = None,
) -> NormalizedRequirement:
    return NormalizedRequirement(
        requirement_id=requirement_id,
        reference_designators=["R1"],
        quantity_per_board=1,
        category=ComponentCategory.RESISTOR,
        parameters={
            "resistance": ParameterValue(
                value=Decimal("10000"), unit="ohm", raw_text="10k", source=ValueSource.PARSED
            )
        },
        footprint=Footprint(package_code="RESC1608X55N"),
        specified_mpn=specified_mpn,
        criticality=Criticality.STANDARD,
        compliance_required=[ComplianceTag.ROHS],
        notes=None,
        confidence=Confidence(score=0.95),
        unresolved=unresolved or [],
    )


def test_confirmed_requirement_maps_to_one_query() -> None:
    mpn = MpnRef(mpn="RC0603FR-0710KL", manufacturer="Yageo", source=ValueSource.PARSED)
    requirement = _requirement("REQ-1", specified_mpn=mpn)

    result = ExpandStage().run([requirement], _make_ctx())

    assert len(result.output) == 1
    query = result.output[0]
    assert query.requirement_id == "REQ-1"
    assert query.category == requirement.category
    assert query.parameters == requirement.parameters
    assert query.footprint == requirement.footprint
    assert query.specified_mpn == mpn
    assert not result.issues


def test_unresolved_requirement_is_excluded_with_info_issue() -> None:
    requirement = _requirement("REQ-2", unresolved=["parameters.tolerance_pct"])

    result = ExpandStage().run([requirement], _make_ctx())

    assert result.output == []
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.severity == Severity.INFO
    assert issue.code == "requirement_unresolved_excluded_from_sourcing"
    assert issue.item_id == "REQ-2"


def test_mixed_batch_only_expands_confirmed_requirements() -> None:
    clean = _requirement("REQ-CLEAN")
    dirty = _requirement("REQ-DIRTY", unresolved=["category"])

    result = ExpandStage().run([dirty, clean], _make_ctx())

    assert [q.requirement_id for q in result.output] == ["REQ-CLEAN"]
    assert any(
        issue.code == "requirement_unresolved_excluded_from_sourcing"
        and issue.item_id == "REQ-DIRTY"
        for issue in result.issues
    )


def test_output_is_sorted_by_requirement_id() -> None:
    requirements = [_requirement("REQ-B"), _requirement("REQ-A"), _requirement("REQ-C")]

    result = ExpandStage().run(requirements, _make_ctx())

    assert [q.requirement_id for q in result.output] == ["REQ-A", "REQ-B", "REQ-C"]


def test_expand_is_deterministic_across_runs() -> None:
    requirements = [
        _requirement("REQ-B"),
        _requirement("REQ-A", unresolved=["category"]),
        _requirement("REQ-C"),
    ]
    ctx = _make_ctx()

    first = ExpandStage().run(requirements, ctx)
    second = ExpandStage().run(requirements, ctx)

    assert [q.model_dump_json() for q in first.output] == [
        q.model_dump_json() for q in second.output
    ]
    assert [(i.severity, i.code, i.message, i.item_id) for i in first.issues] == [
        (i.severity, i.code, i.message, i.item_id) for i in second.issues
    ]
