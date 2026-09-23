"""Full-chain pipeline test: `ExpandStage` -> `SourceStage` -> `PolicyStage` ->
`EvaluateStage`, per `.github/instructions/testing.instructions.md`'s pipeline-layer
table ("Full run against fixture adapters").

No live network or LLM calls: `FixtureAdapter` reads the pinned local
`kicad_golden_snapshot.json` and `FakeLLMClient` returns a canned, valid
`candidate_rationale` response.

## Why these requirements are hand-built, not run through `ingest`+`normalize`

Running the real `IngestStage`+`NormalizeStage` against `fixtures/boms/kicad_bom.csv`
leaves *every* row with a non-empty `unresolved` list (the KiCad export has no
tolerance/voltage-rating/dielectric columns for passives, so those parameters stay
unresolved pending engineer input) — `ExpandStage` correctly refuses to source any
of them, per its own excluded-requirement issue. That is exhaustively covered by
`tests/stages/test_expand.py`'s exclusion tests and is *correct*, not a bug to route
around here. To exercise the `expand -> source -> policy -> evaluate` chain
end-to-end, this test hand-builds a handful of already-confirmed
(`unresolved=[]`) requirements whose parameters/footprints mirror rows in
`kicad_golden_snapshot.json`, matching `tests/stages/test_policy.py`'s precedent of
hand-built `NormalizedRequirement`/`PrePolicyCandidate` fixtures rather than routing
through upstream stages that don't apply to this scenario.
"""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from random import Random

from pcbpick.contracts.candidate import PartCandidate
from pcbpick.contracts.common import Confidence, Footprint, ParameterValue
from pcbpick.contracts.enums import (
    ComplianceTag,
    ComponentCategory,
    Criticality,
    MountingType,
    SubstitutionTier,
    ValueSource,
)
from pcbpick.contracts.requirement import NormalizedRequirement
from pcbpick.llm.fakes import FakeLLMClient
from pcbpick.pipeline.context import PipelineConfig, StageContext
from pcbpick.pipeline.results import Severity, StageIssue
from pcbpick.policy.stage import PolicyStage, PolicyStageInput
from pcbpick.sourcing.evaluate import EvaluateStage, EvaluateStageInput
from pcbpick.sourcing.expand import ExpandStage
from pcbpick.sourcing.stage import SourceStage
from pcbpick.sourcing.suppliers.fixture import FixtureAdapter

CATALOG_PATH = (
    Path(__file__).resolve().parents[2] / "fixtures" / "catalogs" / "kicad_golden_snapshot.json"
)


def _make_ctx() -> StageContext:
    return StageContext(
        run_id="test-run",
        now=datetime(2026, 9, 22, tzinfo=UTC),
        rng=Random("test-run"),
        config=PipelineConfig(),
    )


def _requirements() -> list[NormalizedRequirement]:
    common = {
        "quantity_per_board": 1,
        "specified_mpn": None,
        "criticality": Criticality.STANDARD,
        "compliance_required": [ComplianceTag.ROHS],
        "notes": None,
        "confidence": Confidence(score=0.95),
        "unresolved": [],
    }
    return [
        NormalizedRequirement(
            requirement_id="req-r1",
            reference_designators=["R1", "R2", "R3"],
            category=ComponentCategory.RESISTOR,
            parameters={
                "resistance": ParameterValue(
                    value=Decimal("10000"), unit="ohm", raw_text="10.0k", source=ValueSource.PARSED
                )
            },
            footprint=Footprint(
                package_code="RESC1608X55N",
                mounting=MountingType.SMT,
                pin_count=2,
                length_mm=Decimal("1.6"),
                width_mm=Decimal("0.8"),
                height_mm=Decimal("0.55"),
                raw_text="0603",
            ),
            **common,
        ),
        NormalizedRequirement(
            requirement_id="req-c1",
            reference_designators=["C1", "C2"],
            category=ComponentCategory.CAPACITOR,
            parameters={
                "capacitance": ParameterValue(
                    value=Decimal("1E-7"), unit="farad", raw_text="100n", source=ValueSource.PARSED
                )
            },
            footprint=Footprint(
                package_code="CAPC1005X55N",
                mounting=MountingType.SMT,
                pin_count=2,
                length_mm=Decimal("1.0"),
                width_mm=Decimal("0.5"),
                height_mm=Decimal("0.55"),
                raw_text="0402",
            ),
            **common,
        ),
        NormalizedRequirement(
            requirement_id="req-u1",
            reference_designators=["U1"],
            category=ComponentCategory.IC_ANALOG,
            parameters={},
            footprint=Footprint(
                package_code="SOIC127P600X175-8N",
                mounting=MountingType.SMT,
                pin_count=8,
                pitch_mm=Decimal("1.27"),
                length_mm=Decimal("4.9"),
                width_mm=Decimal("3.9"),
                height_mm=Decimal("1.75"),
                raw_text="SOIC-8",
            ),
            **common,
        ),
        NormalizedRequirement(
            requirement_id="req-y1",
            reference_designators=["Y1"],
            category=ComponentCategory.CRYSTAL,
            parameters={
                "frequency": ParameterValue(
                    value=Decimal("16000000"),
                    unit="hertz",
                    raw_text="16MHz",
                    source=ValueSource.PARSED,
                )
            },
            footprint=Footprint(
                package_code="XTAL3225-4N",
                mounting=MountingType.SMT,
                pin_count=4,
                length_mm=Decimal("3.2"),
                width_mm=Decimal("2.5"),
                height_mm=Decimal("0.8"),
                raw_text="3225 4-pin",
            ),
            **common,
        ),
    ]


def _run_chain(
    requirements: list[NormalizedRequirement], ctx: StageContext, *, fake_response: str
) -> tuple[list[PartCandidate], list[PartCandidate], list[StageIssue]]:
    requirement_by_id = {r.requirement_id: r for r in requirements}

    expand_result = ExpandStage().run(requirements, ctx)
    source_result = SourceStage([FixtureAdapter([CATALOG_PATH])]).run(expand_result.output, ctx)

    policy_result = PolicyStage().run(
        PolicyStageInput(
            pairs=[(requirement_by_id[c.requirement_id], c) for c in source_result.output]
        ),
        ctx,
    )

    evaluate_result = EvaluateStage(
        llm_client=FakeLLMClient(model_id="fake-1", default_response=fake_response)
    ).run(
        EvaluateStageInput(
            pairs=[(requirement_by_id[c.requirement_id], c) for c in policy_result.output]
        ),
        ctx,
    )

    return evaluate_result.output, policy_result.output, evaluate_result.issues


def test_full_chain_never_surfaces_a_tier3_candidate_and_every_survivor_is_explained() -> None:
    ctx = _make_ctx()
    requirements = _requirements()
    fake_response = json.dumps({"rationale": "Meets every checked requirement.", "concerns": []})

    final, policy_candidates, evaluate_issues = _run_chain(
        requirements, ctx, fake_response=fake_response
    )

    assert final  # the hand-built requirements are sourceable and policy-clean candidates exist
    # the parametric resistor/capacitor/crystal queries surface wrong-footprint decoys that
    # policy must reject at tier 3 -- confirm this scenario actually exercises that path.
    assert any(c.substitution_tier == SubstitutionTier.TIER_3 for c in policy_candidates)

    # policy runs before evaluate: no tier-3 candidate ever reaches the final output.
    assert all(c.substitution_tier != SubstitutionTier.TIER_3 for c in final)

    # every surviving candidate either has a rationale, or a recorded BLOCKING issue
    # explaining why it doesn't (llm failure) -- never silently unexplained.
    blocking_ids = {
        issue.item_id
        for issue in evaluate_issues
        if issue.severity == Severity.BLOCKING and issue.code == "candidate_rationale_llm_failed"
    }
    for candidate in final:
        assert candidate.rationale is not None or candidate.requirement_id in blocking_ids

    # tier-3 rejects from policy must show up as skipped (INFO), never sent to the LLM.
    tier3_requirement_ids = {
        c.requirement_id
        for c in policy_candidates
        if c.substitution_tier == SubstitutionTier.TIER_3
    }
    skipped_ids = {
        issue.item_id
        for issue in evaluate_issues
        if issue.code == "rationale_skipped_rejected_candidate"
    }
    assert tier3_requirement_ids <= skipped_ids


def test_full_chain_is_deterministic_across_runs() -> None:
    ctx = _make_ctx()
    requirements = _requirements()
    fake_response = json.dumps({"rationale": "Meets every checked requirement.", "concerns": []})

    first, _, _ = _run_chain(requirements, ctx, fake_response=fake_response)
    second, _, _ = _run_chain(requirements, ctx, fake_response=fake_response)

    assert [c.model_dump_json() for c in first] == [c.model_dump_json() for c in second]
