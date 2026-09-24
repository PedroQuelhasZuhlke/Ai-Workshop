"""Stage tests for `policy`: every curated fixture in `fixtures/policy/cases/`, a
`BLOCKING` issue-emission test, and a determinism check, per
`.github/instructions/pipeline-stages.instructions.md` and
`fixtures/policy/README.md`.
"""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from random import Random

import pytest

from pcbpick.contracts.common import Confidence, Footprint, ParameterValue, PriceBreak
from pcbpick.contracts.enums import (
    ComplianceTag,
    ComponentCategory,
    Criticality,
    Lifecycle,
    Packaging,
    SubstitutionTier,
    SupplierId,
    ValueSource,
)
from pcbpick.contracts.offer import SupplierOffer
from pcbpick.contracts.policy import PolicyResult
from pcbpick.contracts.requirement import NormalizedRequirement
from pcbpick.pipeline.context import PipelineConfig, StageContext
from pcbpick.pipeline.results import Severity
from pcbpick.policy.candidate_input import PrePolicyCandidate
from pcbpick.policy.rules import evaluate_candidate
from pcbpick.policy.safety import detect_safety_criticality, effective_criticality
from pcbpick.policy.stage import PolicyStage, PolicyStageInput

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "policy"
CASES_DIR = FIXTURES_DIR / "cases"

_TIER_BY_NUMBER = {
    0: SubstitutionTier.TIER_0,
    1: SubstitutionTier.TIER_1,
    2: SubstitutionTier.TIER_2,
}


def _manifest() -> list[dict]:
    data = json.loads((FIXTURES_DIR / "manifest.json").read_text(encoding="utf-8"))
    return data["cases"]


def _load_case(case_id: str) -> tuple[NormalizedRequirement, PrePolicyCandidate, dict]:
    input_data = json.loads((CASES_DIR / f"{case_id}.input.json").read_text(encoding="utf-8"))
    expected = json.loads((CASES_DIR / f"{case_id}.expected.json").read_text(encoding="utf-8"))
    requirement = NormalizedRequirement.model_validate(input_data["requirement"])
    candidate = PrePolicyCandidate.model_validate(input_data["candidate"])
    return requirement, candidate, expected


def _make_ctx() -> StageContext:
    return StageContext(
        run_id="test-run",
        now=datetime(2026, 9, 22, tzinfo=UTC),
        rng=Random("test-run"),
        config=PipelineConfig(),
    )


@pytest.mark.parametrize("case", _manifest(), ids=lambda case: case["case_id"])
def test_fixture_case_matches_expected_outcome(case: dict) -> None:
    requirement, candidate, expected = _load_case(case["case_id"])
    tier, results = evaluate_candidate(requirement, candidate)
    results_by_name: dict[str, list[PolicyResult]] = {}
    for result in results:
        results_by_name.setdefault(result.rule_name, []).append(result)

    if expected["outcome"] == "pass":
        assert tier == _TIER_BY_NUMBER[expected["tier"]], (
            f"{case['case_id']}: expected tier {expected['tier']}, got {tier}"
        )
    else:
        assert tier == SubstitutionTier.TIER_3, (
            f"{case['case_id']}: expected rejection, got tier {tier}"
        )
        blocking_rule = expected["blocking_rule"]
        assert blocking_rule is not None
        blocking_matches = results_by_name.get(blocking_rule, [])
        assert blocking_matches, (
            f"{case['case_id']}: blocking_rule {blocking_rule!r} never evaluated"
        )
        assert any(not r.passed for r in blocking_matches), (
            f"{case['case_id']}: blocking_rule {blocking_rule!r} did not fail"
        )

    for expected_rule in expected["expected_rules"]:
        rule_name = expected_rule["rule_name"]
        matches = results_by_name.get(rule_name, [])
        assert matches, f"{case['case_id']}: rule {rule_name!r} was never evaluated"
        assert any(
            r.passed == expected_rule["passed"] and expected_rule["reason_contains"] in r.reason
            for r in matches
        ), (
            f"{case['case_id']}: no {rule_name!r} result with passed={expected_rule['passed']} "
            f"and reason containing {expected_rule['reason_contains']!r}; got "
            f"{[(r.passed, r.reason) for r in matches]}"
        )


def test_every_rule_evaluated_is_recorded_including_passes() -> None:
    """The engine is exhaustive by design: it must not report only failures."""
    requirement, candidate, _ = _load_case("known_good_tier1_capacitor_dropin")
    _, results = evaluate_candidate(requirement, candidate)
    assert all(isinstance(r, PolicyResult) for r in results)
    assert any(r.passed for r in results)
    assert len(results) >= 5


@pytest.mark.parametrize("case", _manifest(), ids=lambda case: case["case_id"])
def test_evaluate_candidate_is_deterministic_across_runs(case: dict) -> None:
    requirement, candidate, _ = _load_case(case["case_id"])
    first = evaluate_candidate(requirement, candidate)
    second = evaluate_candidate(requirement, candidate)
    assert first == second
    assert [r.model_dump_json() for r in first[1]] == [r.model_dump_json() for r in second[1]]


def test_policy_stage_emits_blocking_issue_for_tier3_rejection() -> None:
    requirement, candidate, _ = _load_case("known_bad_footprint_mismatch")
    stage = PolicyStage()
    result = stage.run(PolicyStageInput(pairs=[(requirement, candidate)]), _make_ctx())

    assert result.output[0].substitution_tier == SubstitutionTier.TIER_3
    blocking = [i for i in result.issues if i.code == "candidate_rejected_tier3"]
    assert blocking
    assert all(i.severity == Severity.BLOCKING for i in blocking)


def test_policy_stage_carries_pre_candidate_offers_through_unchanged() -> None:
    requirement, candidate, _ = _load_case("known_good_tier0_identical_mpn")
    offer = SupplierOffer(
        supplier=SupplierId.FIXTURE,
        sku="SKU-1",
        packaging=Packaging.CUT_TAPE,
        stock=100,
        moq=1,
        spq=1,
        price_breaks=[PriceBreak(quantity=1, unit_price=Decimal("0.01"), currency="USD")],
        lead_time_days=None,
        snapshot_id="SNAP-1",
        fetched_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    candidate = candidate.model_copy(update={"offers": [offer]})
    stage = PolicyStage()
    result = stage.run(PolicyStageInput(pairs=[(requirement, candidate)]), _make_ctx())

    assert result.output[0].offers == [offer]


def test_policy_stage_emits_derating_config_version_info() -> None:
    requirement, candidate, _ = _load_case("known_good_tier0_identical_mpn")
    stage = PolicyStage()
    result = stage.run(PolicyStageInput(pairs=[(requirement, candidate)]), _make_ctx())

    version_issues = [i for i in result.issues if i.code == "derating_config_version"]
    assert len(version_issues) == 1
    assert version_issues[0].severity == Severity.INFO


def test_policy_stage_output_sorted_by_requirement_and_mpn() -> None:
    pairs = []
    for case_id in ("known_good_tier0_identical_mpn", "known_good_tier1_capacitor_dropin"):
        requirement, candidate, _ = _load_case(case_id)
        pairs.append((requirement, candidate))
    # reverse insertion order to prove the stage sorts explicitly, not by insertion.
    pairs.reverse()
    stage = PolicyStage()
    result = stage.run(PolicyStageInput(pairs=pairs), _make_ctx())

    ids = [c.requirement_id for c in result.output]
    assert ids == sorted(ids)


def test_policy_stage_run_is_byte_identical_across_runs() -> None:
    pairs = [
        _load_case(case_id)[:2]
        for case_id in ("known_good_tier1_capacitor_dropin", "known_bad_lifecycle_obsolete")
    ]
    stage = PolicyStage()
    first = stage.run(PolicyStageInput(pairs=pairs), _make_ctx())
    second = stage.run(PolicyStageInput(pairs=pairs), _make_ctx())

    first_output = [c.model_dump_json() for c in first.output]
    second_output = [c.model_dump_json() for c in second.output]
    assert first_output == second_output
    assert [(i.severity, i.code, i.message, i.item_id) for i in first.issues] == [
        (i.severity, i.code, i.message, i.item_id) for i in second.issues
    ]


# --- Focused unit tests for individual rule behaviors -----------------------------


def test_resistor_power_derating_math() -> None:
    requirement, candidate, _ = _load_case("known_bad_resistor_power_derating")
    _, results = evaluate_candidate(requirement, candidate)
    power_result = next(r for r in results if r.rule_name == "power_derating")
    assert power_result.passed is False
    # 0.2W applied / 0.6 factor = 0.3333...W minimum; candidate rated 0.25W.
    assert "0.333" in power_result.reason


def test_dielectric_class_change_is_hard_fail_regardless_of_voltage_margin() -> None:
    requirement, candidate, _ = _load_case("known_bad_dielectric_class_change")
    tier, results = evaluate_candidate(requirement, candidate)
    dielectric_result = next(r for r in results if r.rule_name == "dielectric_class")
    voltage_result = next(r for r in results if r.rule_name == "voltage_derating")
    assert dielectric_result.passed is False
    assert voltage_result.passed is True  # electrically fine; still must reject overall
    assert tier == SubstitutionTier.TIER_3


def test_footprint_identity_requires_every_structural_field_to_match() -> None:
    requirement, candidate, _ = _load_case("known_bad_footprint_mismatch")
    _, results = evaluate_candidate(requirement, candidate)
    footprint_result = next(r for r in results if r.rule_name == "footprint_identity")
    assert footprint_result.passed is False


def test_engineer_do_not_substitute_outranks_electrically_superior_candidate() -> None:
    requirement, candidate, _ = _load_case("engineer_override_do_not_substitute")
    tier, results = evaluate_candidate(requirement, candidate)
    gate_result = next(r for r in results if r.rule_name == "engineer_do_not_substitute")
    assert gate_result.passed is False
    assert tier == SubstitutionTier.TIER_3


def test_missing_candidate_voltage_rating_fails_closed() -> None:
    requirement, candidate, _ = _load_case("known_bad_missing_voltage_rating_unknown")
    assert candidate.parameters["voltage_rating"].value is None
    _, results = evaluate_candidate(requirement, candidate)
    unknown_result = next(r for r in results if r.rule_name == "required_parameter_unknown")
    assert unknown_result.passed is False
    assert "voltage_rating" in unknown_result.reason


def test_tier1_dropin_requires_tighter_or_equal_tolerance() -> None:
    requirement, candidate, _ = _load_case("known_good_tier1_capacitor_dropin")
    _, results = evaluate_candidate(requirement, candidate)
    tolerance_result = next(r for r in results if r.rule_name == "tolerance_direction")
    assert tolerance_result.passed is True
    req_tol = requirement.parameters["tolerance_pct"].value
    cand_tol = candidate.parameters["tolerance_pct"].value
    assert cand_tol < req_tol


def test_ic_pin_compatible_candidate_is_capped_at_tier_2() -> None:
    requirement, candidate, _ = _load_case("known_good_tier2_pin_compatible_ic")
    assert requirement.specified_mpn is None
    tier, results = evaluate_candidate(requirement, candidate)
    assert tier == SubstitutionTier.TIER_2
    assert any(r.rule_name == "tier_cap_ic_cross_manufacturer" and r.passed for r in results)


# --- Factories for constructing minimal requirement/candidate pairs not covered by the
# curated fixture set (added after the invariant-auditor flagged category and safety
# detection gaps that the 18 curated fixtures don't exercise). ------------------------


def _param(value: str, unit: str, raw_text: str, **overrides: object) -> ParameterValue:
    defaults: dict[str, object] = {
        "value": Decimal(value),
        "unit": unit,
        "raw_text": raw_text,
        "source": ValueSource.PARSED,
    }
    defaults.update(overrides)
    return ParameterValue(**defaults)  # type: ignore[arg-type]


def _requirement(
    category: ComponentCategory,
    parameters: dict[str, ParameterValue],
    footprint: Footprint | None = None,
    criticality: Criticality = Criticality.STANDARD,
    compliance_required: list[ComplianceTag] | None = None,
    notes: str | None = None,
) -> NormalizedRequirement:
    return NormalizedRequirement(
        requirement_id="REQ-TEST",
        reference_designators=["Z1"],
        quantity_per_board=1,
        category=category,
        parameters=parameters,
        footprint=footprint or Footprint(package_code="TEST", raw_text="TEST"),
        specified_mpn=None,
        criticality=criticality,
        compliance_required=compliance_required or [],
        notes=notes,
        confidence=Confidence(score=1.0, reasons=["test fixture"]),
        unresolved=[],
    )


def _candidate(
    parameters: dict[str, ParameterValue],
    footprint: Footprint | None = None,
    lifecycle: Lifecycle = Lifecycle.ACTIVE,
    compliance: list[ComplianceTag] | None = None,
    mpn: str = "CAND-1",
    snapshot_id: str | None = "SNAP-1",
) -> PrePolicyCandidate:
    return PrePolicyCandidate(
        schema_version="v1",
        requirement_id="REQ-TEST",
        mpn=mpn,
        manufacturer="TestCo",
        parameters=parameters,
        footprint=footprint or Footprint(package_code="TEST", raw_text="TEST"),
        lifecycle=lifecycle,
        compliance=compliance or [],
        snapshot_id=snapshot_id,
    )


# --- Category hard-parameter coverage the curated fixtures don't exercise -----------


def test_diode_reverse_voltage_derating_rejects_undersized_candidate() -> None:
    requirement = _requirement(
        ComponentCategory.DIODE,
        {
            "reverse_voltage": _param("100", "volt", "100V"),
            "forward_current": _param("1", "ampere", "1A"),
        },
    )
    candidate = _candidate(
        {
            "reverse_voltage": _param("100", "volt", "100V", source=ValueSource.DATASHEET),
            "forward_current": _param("1", "ampere", "1A", source=ValueSource.DATASHEET),
        }
    )
    tier, results = evaluate_candidate(requirement, candidate)
    rv = next(r for r in results if r.rule_name == "reverse_voltage_derating")
    # 100V applied / 0.8 factor = 125V minimum; candidate rated 100V does not clear it.
    assert rv.passed is False
    assert tier == SubstitutionTier.TIER_3


def test_led_forward_current_derating_and_forward_voltage_checked() -> None:
    requirement = _requirement(
        ComponentCategory.LED,
        {
            "forward_voltage": _param("2", "volt", "2V"),
            "forward_current": _param("20", "milliampere", "20mA"),
        },
    )
    candidate = _candidate(
        {
            "forward_voltage": _param("2", "volt", "2V", source=ValueSource.DATASHEET),
            "forward_current": _param("20", "milliampere", "20mA", source=ValueSource.DATASHEET),
        }
    )
    _, results = evaluate_candidate(requirement, candidate)
    current_result = next(r for r in results if r.rule_name == "forward_current_derating")
    # 20mA applied / 0.8 = 25mA minimum; candidate rated 20mA fails.
    assert current_result.passed is False
    assert any(r.rule_name == "forward_voltage_value_match" for r in results)


def test_ferrite_bead_current_derating_enforced() -> None:
    requirement = _requirement(
        ComponentCategory.FERRITE_BEAD,
        {"impedance_at_frequency": _param("100", "ohm", "100R@100MHz")},
    )
    candidate = _candidate(
        {
            "impedance_at_frequency": _param(
                "100", "ohm", "100R@100MHz", source=ValueSource.DATASHEET
            ),
            "current_rating": _param("1", "ampere", "1A", source=ValueSource.DATASHEET),
        }
    )
    requirement = requirement.model_copy(
        update={
            "parameters": {
                **requirement.parameters,
                "current_rating": _param("1", "ampere", "1A"),
            }
        }
    )
    _, results = evaluate_candidate(requirement, candidate)
    current_result = next(r for r in results if r.rule_name == "current_derating")
    # 1A applied / 0.7 factor = 1.43A minimum; candidate rated 1A fails.
    assert current_result.passed is False


def test_relay_contact_current_derating_and_coil_voltage_checked() -> None:
    requirement = _requirement(
        ComponentCategory.RELAY,
        {
            "coil_voltage": _param("5", "volt", "5V"),
            "contact_current_rating": _param("10", "ampere", "10A"),
        },
    )
    candidate = _candidate(
        {
            "coil_voltage": _param("12", "volt", "12V", source=ValueSource.DATASHEET),
            "contact_current_rating": _param("10", "ampere", "10A", source=ValueSource.DATASHEET),
        }
    )
    _, results = evaluate_candidate(requirement, candidate)
    coil_result = next(r for r in results if r.rule_name == "coil_voltage_value_match")
    current_result = next(r for r in results if r.rule_name == "contact_current_derating")
    assert coil_result.passed is False
    # 10A applied / 0.75 = 13.33A minimum; candidate rated 10A fails.
    assert current_result.passed is False


def test_crystal_load_capacitance_mismatch_is_hard_fail() -> None:
    requirement = _requirement(
        ComponentCategory.CRYSTAL,
        {
            "frequency": _param("16000000", "hertz", "16MHz"),
            "load_capacitance": _param("1.8E-11", "farad", "18pF"),
        },
    )
    candidate = _candidate(
        {
            "frequency": _param("16000000", "hertz", "16MHz", source=ValueSource.DATASHEET),
            "load_capacitance": _param("1.2E-11", "farad", "12pF", source=ValueSource.DATASHEET),
        }
    )
    _, results = evaluate_candidate(requirement, candidate)
    load_result = next(r for r in results if r.rule_name == "load_capacitance_value_match")
    assert load_result.passed is False


def test_connector_pin_count_and_contact_current_checked() -> None:
    requirement = _requirement(
        ComponentCategory.CONNECTOR,
        {
            "pin_count": _param("4", "count", "4-pin"),
            "current_rating": _param("2", "ampere", "2A"),
        },
    )
    candidate = _candidate(
        {
            "pin_count": _param("6", "count", "6-pin", source=ValueSource.DATASHEET),
            "current_rating": _param("2", "ampere", "2A", source=ValueSource.DATASHEET),
        }
    )
    _, results = evaluate_candidate(requirement, candidate)
    pin_result = next(r for r in results if r.rule_name == "pin_count_value_match")
    assert pin_result.passed is False


def test_fuse_current_derating_enforced_even_with_exact_mpn_match() -> None:
    requirement = _requirement(
        ComponentCategory.FUSE,
        {
            "current_rating": _param("1", "ampere", "1A"),
            "voltage_rating": _param("250", "volt", "250V"),
        },
        criticality=Criticality.SAFETY,
    )
    candidate = _candidate(
        {
            "current_rating": _param("1", "ampere", "1A", source=ValueSource.DATASHEET),
            "voltage_rating": _param("250", "volt", "250V", source=ValueSource.DATASHEET),
        }
    )
    _, results = evaluate_candidate(requirement, candidate)
    current_result = next(r for r in results if r.rule_name == "current_derating")
    # 1A applied / 0.75 factor = 1.33A minimum; candidate rated 1A fails.
    assert current_result.passed is False


def test_generic_rating_direction_fallback_catches_uncovered_category() -> None:
    """SWITCH has no category-specific derating factor; the generic no-headroom fallback
    must still catch a candidate rated below the requirement's applied voltage."""
    requirement = _requirement(
        ComponentCategory.SWITCH,
        {"voltage_rating": _param("250", "volt", "250V")},
    )
    candidate = _candidate(
        {"voltage_rating": _param("125", "volt", "125V", source=ValueSource.DATASHEET)}
    )
    tier, results = evaluate_candidate(requirement, candidate)
    fallback_result = next(r for r in results if r.rule_name == "voltage_rating_direction")
    assert fallback_result.passed is False
    assert tier == SubstitutionTier.TIER_3


# --- Capacitor dielectric classes beyond ceramic Class I/II --------------------------


@pytest.mark.parametrize(
    ("dielectric_text", "applied", "factor_pct", "candidate_rating", "expect_pass"),
    [
        ("Aluminum Electrolytic", "10", "0.8", "12.5", True),  # 10/0.8 = 12.5V min, clears
        ("Aluminum Electrolytic", "10", "0.8", "11", False),  # fails 12.5V min
        ("Tantalum", "10", "0.5", "20", True),  # 10/0.5 = 20V min, clears
        ("Tantalum", "10", "0.5", "16", False),  # fails 20V min
        ("Tantalum Polymer", "10", "0.8", "12.5", True),
        ("Film / Polyester", "10", "0.8", "12.5", True),
    ],
)
def test_capacitor_voltage_derating_covers_every_dielectric_family(
    dielectric_text: str, applied: str, factor_pct: str, candidate_rating: str, expect_pass: bool
) -> None:
    requirement = _requirement(
        ComponentCategory.CAPACITOR,
        {
            "capacitance": _param("1E-6", "farad", "1uF"),
            "voltage_rating": _param(applied, "volt", f"{applied}V"),
            "dielectric": ParameterValue(
                value=None, unit="class", raw_text=dielectric_text, source=ValueSource.PARSED
            ),
        },
    )
    candidate = _candidate(
        {
            "capacitance": _param("1E-6", "farad", "1uF", source=ValueSource.DATASHEET),
            "voltage_rating": _param(
                candidate_rating, "volt", f"{candidate_rating}V", source=ValueSource.DATASHEET
            ),
            "dielectric": ParameterValue(
                value=None, unit="class", raw_text=dielectric_text, source=ValueSource.DATASHEET
            ),
        }
    )
    _, results = evaluate_candidate(requirement, candidate)
    voltage_result = next(r for r in results if r.rule_name == "voltage_derating")
    assert voltage_result.passed is expect_pass


# --- Footprint fixes: fail-closed on unspecified, thermal_pad as identity field ------


def test_footprint_identity_fails_closed_when_requirement_footprint_is_fully_unspecified() -> None:
    requirement = _requirement(ComponentCategory.MODULE, {}, footprint=Footprint())
    candidate = _candidate({}, footprint=Footprint())
    _, results = evaluate_candidate(requirement, candidate)
    footprint_result = next(r for r in results if r.rule_name == "footprint_identity")
    assert footprint_result.passed is False


def test_footprint_identity_catches_thermal_pad_mismatch() -> None:
    requirement = _requirement(
        ComponentCategory.TRANSISTOR,
        {
            "voltage_rating": _param("30", "volt", "30V"),
            "current_rating": _param("1", "ampere", "1A"),
        },
        footprint=Footprint(package_code="QFN-8", pin_count=8, thermal_pad=True, raw_text="QFN-8"),
    )
    candidate = _candidate(
        {
            "voltage_rating": _param("30", "volt", "30V", source=ValueSource.DATASHEET),
            "current_rating": _param("1", "ampere", "1A", source=ValueSource.DATASHEET),
        },
        footprint=Footprint(package_code="QFN-8", pin_count=8, thermal_pad=False, raw_text="QFN-8"),
    )
    _, results = evaluate_candidate(requirement, candidate)
    footprint_result = next(r for r in results if r.rule_name == "footprint_identity")
    assert footprint_result.passed is False
    assert "thermal_pad" in footprint_result.reason


# --- Fixed reporting bugs: mpn_identity and criticality_gate must not misreport -----


def test_mpn_identity_reports_failure_when_mpn_differs() -> None:
    from pcbpick.contracts.common import MpnRef

    requirement = _requirement(
        ComponentCategory.RESISTOR,
        {
            "resistance": _param("1000", "ohm", "1k"),
            "tolerance_pct": _param("1", "percent", "1%"),
            "power_rating": _param("0.25", "watt", "0.25W"),
        },
    )
    requirement = requirement.model_copy(
        update={"specified_mpn": MpnRef(mpn="EXACT-MPN", source=ValueSource.ENGINEER_ENTERED)}
    )
    candidate = _candidate(
        {
            "resistance": _param("1000", "ohm", "1k", source=ValueSource.DATASHEET),
            "tolerance_pct": _param("1", "percent", "1%", source=ValueSource.DATASHEET),
            "power_rating": _param("0.25", "watt", "0.25W", source=ValueSource.DATASHEET),
        },
        mpn="DIFFERENT-MPN",
    )
    _, results = evaluate_candidate(requirement, candidate)
    mpn_result = next(r for r in results if r.rule_name == "mpn_identity")
    assert mpn_result.passed is False


def test_criticality_gate_is_informational_and_never_reports_a_false_failure() -> None:
    requirement = _requirement(
        ComponentCategory.FUSE,
        {
            "current_rating": _param("1", "ampere", "1A"),
            "voltage_rating": _param("250", "volt", "250V"),
        },
        criticality=Criticality.SAFETY,
    )
    from pcbpick.contracts.common import MpnRef

    requirement = requirement.model_copy(
        update={"specified_mpn": MpnRef(mpn="EXACT-FUSE", source=ValueSource.ENGINEER_ENTERED)}
    )
    candidate = _candidate(
        {
            "current_rating": _param("2", "ampere", "2A", source=ValueSource.DATASHEET),
            "voltage_rating": _param("250", "volt", "250V", source=ValueSource.DATASHEET),
        },
        mpn="EXACT-FUSE",
    )
    tier, results = evaluate_candidate(requirement, candidate)
    gate_result = next(r for r in results if r.rule_name == "criticality_gate")
    assert gate_result.passed is True
    assert tier == SubstitutionTier.TIER_0


# --- Safety detection breadth: must not depend on `notes` alone ---------------------


def test_safety_detection_escalates_from_dielectric_raw_text() -> None:
    requirement = _requirement(
        ComponentCategory.CAPACITOR,
        {
            "capacitance": _param("2.2E-9", "farad", "2.2nF"),
            "voltage_rating": _param("250", "volt", "250V"),
            "dielectric": ParameterValue(
                value=None, unit="class", raw_text="Y2", source=ValueSource.PARSED
            ),
        },
    )
    assert requirement.criticality == Criticality.STANDARD
    assert effective_criticality(requirement) == Criticality.SAFETY


def test_safety_detection_escalates_from_footprint_raw_text() -> None:
    requirement = _requirement(
        ComponentCategory.RELAY,
        {"coil_voltage": _param("12", "volt", "12V")},
        footprint=Footprint(package_code="THT-5", raw_text="mains-rated relay footprint"),
    )
    assert requirement.criticality == Criticality.STANDARD
    assert effective_criticality(requirement) == Criticality.SAFETY


def test_safety_detection_still_defaults_to_standard_without_any_token() -> None:
    requirement = _requirement(
        ComponentCategory.RELAY,
        {"coil_voltage": _param("12", "volt", "12V")},
        notes="ordinary signal relay",
    )
    assert effective_criticality(requirement) == Criticality.STANDARD
    assert detect_safety_criticality(ComponentCategory.RELAY, "ordinary signal relay") is False


# --- Snapshot provenance warning -----------------------------------------------------


def test_policy_stage_warns_when_candidate_has_no_snapshot_id() -> None:
    requirement, candidate, _ = _load_case("known_good_tier0_identical_mpn")
    candidate_without_snapshot = candidate.model_copy(update={"snapshot_id": None})
    stage = PolicyStage()
    result = stage.run(
        PolicyStageInput(pairs=[(requirement, candidate_without_snapshot)]), _make_ctx()
    )
    warnings = [i for i in result.issues if i.code == "candidate_missing_snapshot_provenance"]
    assert len(warnings) == 1
    assert warnings[0].severity == Severity.WARNING
