"""Pure policy rule functions and the top-level `evaluate_candidate` entry point.

Evaluation follows the cheap-to-expensive order in
`.github/skills/substitution-policy/SKILL.md`: category match, footprint identity,
criticality gate, hard parameter comparisons with derating, dielectric/material class,
qualification and compliance, lifecycle, then tier assignment. Every rule this module
evaluates emits a `PolicyResult` — passes included — so an engineer can see what was
checked, not just what failed.
"""

from decimal import Decimal

from pcbpick.contracts.common import Footprint, ParameterValue
from pcbpick.contracts.enums import (
    ComplianceTag,
    ComponentCategory,
    Criticality,
    Lifecycle,
    SubstitutionTier,
)
from pcbpick.contracts.policy import PolicyResult
from pcbpick.contracts.requirement import NormalizedRequirement
from pcbpick.policy.candidate_input import PrePolicyCandidate
from pcbpick.policy.derating_config import DEFAULT_DERATING_CONFIG, DeratingConfig, DeratingFactor
from pcbpick.policy.safety import effective_criticality

# Rules in this set are declarative/informational: a `passed=False` entry never by
# itself rejects a candidate. Rejection always comes from a dedicated gating rule
# (e.g. `safety_critical_exact_mpn_only`, not `criticality_gate` itself).
_INFORMATIONAL_RULES = frozenset(
    {"category_match", "mpn_identity", "criticality_gate", "tier_cap_ic_cross_manufacturer"}
)

_IC_CATEGORIES = frozenset(
    {
        ComponentCategory.IC_ANALOG,
        ComponentCategory.IC_DIGITAL,
        ComponentCategory.IC_POWER,
        ComponentCategory.IC_RF,
    }
)

# Mechanical/timing identity dominates substitution for these categories per
# category-rules.md ("Crystal substitution is tier 2 minimum"; connectors/switches/
# relays/transformers are "tier 2 minimum and frequently tier 3").
_TIER_2_MINIMUM_CATEGORIES = frozenset(
    {
        ComponentCategory.CRYSTAL,
        ComponentCategory.OSCILLATOR,
        ComponentCategory.CONNECTOR,
        ComponentCategory.SWITCH,
        ComponentCategory.RELAY,
        ComponentCategory.TRANSFORMER,
    }
)

_FOOTPRINT_FIELDS = (
    "package_code",
    "mounting",
    "pin_count",
    "pitch_mm",
    "length_mm",
    "width_mm",
    "height_mm",
    "thermal_pad",
)


def _footprint_label(footprint: Footprint) -> str:
    return footprint.raw_text or footprint.package_code or "unspecified"


def _footprint_identity_rule(requirement_fp: Footprint, candidate_fp: Footprint) -> PolicyResult:
    if all(getattr(requirement_fp, field) is None for field in _FOOTPRINT_FIELDS):
        reason = (
            "requirement footprint has no identifying fields recorded; footprint identity "
            "cannot be verified and fails closed"
        )
        return PolicyResult(rule_name="footprint_identity", passed=False, reason=reason)
    mismatches = [
        field
        for field in _FOOTPRINT_FIELDS
        if getattr(requirement_fp, field) != getattr(candidate_fp, field)
    ]
    req_label = _footprint_label(requirement_fp)
    cand_label = _footprint_label(candidate_fp)
    if not mismatches:
        reason = f"footprint matches exactly ({req_label}, {requirement_fp.package_code})"
        return PolicyResult(rule_name="footprint_identity", passed=True, reason=reason)
    reason = (
        f"footprint mismatch: requirement {req_label} ({requirement_fp.package_code}) vs "
        f"candidate {cand_label} ({candidate_fp.package_code}); differs in {', '.join(mismatches)}"
    )
    return PolicyResult(rule_name="footprint_identity", passed=False, reason=reason)


def _category_match_rule(requirement: NormalizedRequirement) -> PolicyResult:
    reason = f"requirement category '{requirement.category.value}' recognized for policy evaluation"
    return PolicyResult(rule_name="category_match", passed=True, reason=reason)


def _mpn_identity_rule(
    requirement: NormalizedRequirement, candidate: PrePolicyCandidate
) -> PolicyResult:
    specified = requirement.specified_mpn
    assert specified is not None  # only called when specified_mpn is present
    if candidate.mpn == specified.mpn:
        reason = f"candidate MPN '{candidate.mpn}' matches specified MPN '{specified.mpn}'"
        return PolicyResult(rule_name="mpn_identity", passed=True, reason=reason)
    reason = (
        f"candidate MPN '{candidate.mpn}' differs from specified MPN '{specified.mpn}' "
        "(not eligible for tier 0)"
    )
    return PolicyResult(rule_name="mpn_identity", passed=False, reason=reason)


def _criticality_gate_result(criticality: Criticality) -> PolicyResult:
    # Informational: this rule reports that the gate is active, it never itself fails a
    # candidate. Rejection is `_exact_mpn_gate_result`'s job -- keeping this `passed=True`
    # keeps a fully-valid tier-0 match from showing a spurious failure in the audit trail.
    if criticality == Criticality.SAFETY:
        reason = (
            "criticality safety: substitution is restricted to tier 0 (exact specified MPN only)"
        )
    else:
        reason = "criticality do_not_substitute: only the engineer-specified MPN may be used"
    return PolicyResult(rule_name="criticality_gate", passed=True, reason=reason)


def _exact_mpn_gate_result(
    criticality: Criticality, requirement: NormalizedRequirement, candidate: PrePolicyCandidate
) -> PolicyResult:
    rule_name = (
        "engineer_do_not_substitute"
        if criticality == Criticality.DO_NOT_SUBSTITUTE
        else "safety_critical_exact_mpn_only"
    )
    specified = requirement.specified_mpn
    kind = (
        "do_not_substitute" if criticality == Criticality.DO_NOT_SUBSTITUTE else "safety-critical"
    )
    if specified is None:
        reason = f"no specified MPN recorded for this {kind} requirement; cannot verify exact match"
        return PolicyResult(rule_name=rule_name, passed=False, reason=reason)
    if candidate.mpn == specified.mpn:
        reason = (
            f"candidate MPN '{candidate.mpn}' matches the specified MPN '{specified.mpn}'; "
            "tier 0 permitted"
        )
        return PolicyResult(rule_name=rule_name, passed=True, reason=reason)
    reason = (
        f"candidate MPN '{candidate.mpn}' does not match the required specified MPN "
        f"'{specified.mpn}'; only the exact specified MPN may be substituted for this "
        f"{kind} requirement"
    )
    return PolicyResult(rule_name=rule_name, passed=False, reason=reason)


def _required_parameter_unknown(param_name: str) -> PolicyResult:
    reason = (
        f"required parameter '{param_name}' is unknown (no value recorded) on the candidate; "
        "cannot verify against the requirement"
    )
    return PolicyResult(rule_name="required_parameter_unknown", passed=False, reason=reason)


def _nominal_value_rule(
    param_name: str, params_r: dict[str, ParameterValue], params_c: dict[str, ParameterValue]
) -> PolicyResult | None:
    req = params_r.get(param_name)
    if req is None or req.value is None:
        return None
    cand = params_c.get(param_name)
    if cand is None or cand.value is None:
        return _required_parameter_unknown(param_name)
    tol_param = params_r.get("tolerance_pct")
    tol_value = (
        tol_param.value if tol_param is not None and tol_param.value is not None else Decimal("0")
    )
    allowed_delta = abs(req.value) * (tol_value / Decimal("100"))
    lower = req.value - allowed_delta
    upper = req.value + allowed_delta
    passed = lower <= cand.value <= upper
    reason = (
        f"{param_name} requirement {req.value} {req.unit} (+/-{tol_value}%) allows {lower} to "
        f"{upper}; candidate {cand.value} {cand.unit}"
    )
    return PolicyResult(rule_name=f"{param_name}_value_match", passed=passed, reason=reason)


def _tolerance_direction_rule(
    params_r: dict[str, ParameterValue], params_c: dict[str, ParameterValue]
) -> PolicyResult | None:
    req = params_r.get("tolerance_pct")
    if req is None or req.value is None:
        return None
    cand = params_c.get("tolerance_pct")
    if cand is None or cand.value is None:
        return _required_parameter_unknown("tolerance_pct")
    if cand.value < req.value:
        word = "tighter"
    elif cand.value == req.value:
        word = "equal"
    else:
        word = "looser"
    passed = cand.value <= req.value
    reason = f"tolerance_pct requirement {req.value}%, candidate {cand.value}% ({word})"
    return PolicyResult(rule_name="tolerance_direction", passed=passed, reason=reason)


def _derated_minimum_rule(
    rule_name: str,
    param_name: str,
    params_r: dict[str, ParameterValue],
    params_c: dict[str, ParameterValue],
    factor: DeratingFactor,
) -> PolicyResult | None:
    req = params_r.get(param_name)
    if req is None or req.value is None:
        return None
    cand = params_c.get(param_name)
    if cand is None or cand.value is None:
        return _required_parameter_unknown(param_name)
    unit = req.unit
    derated_min = req.value * factor.multiplier
    passed = cand.value >= derated_min
    reason = (
        f"{param_name}: requirement applied {req.value} {unit} derates to a minimum candidate "
        f"rating of {derated_min} {unit} ({factor.description}); candidate rated {cand.value} "
        f"{unit}"
    )
    return PolicyResult(rule_name=rule_name, passed=passed, reason=reason)


_CLASS_I_TOKENS = ("C0G", "NP0")
_CLASS_II_TOKENS = ("X5R", "X6S", "X7R", "X7S", "Y5V", "Z5U", "U2J")
_TANTALUM_POLYMER_TOKENS = ("TANTALUM POLYMER", "POLYMER TANTALUM", "TANTALUM-POLYMER", "TA-POLY")
_TANTALUM_TOKENS = ("TANTALUM",)
_ELECTROLYTIC_TOKENS = ("ELECTROLYTIC", "ALU ELEC", "AL ELEC")
_FILM_TOKENS = ("FILM", "POLYPROPYLENE", "POLYESTER", "MKP", "MKT", "PPS")


def _dielectric_class(raw_text: str | None) -> str | None:
    if not raw_text:
        return None
    upper = raw_text.upper()
    for token in _CLASS_I_TOKENS:
        if token in upper:
            return "class_i"
    for token in _CLASS_II_TOKENS:
        if token in upper:
            return "class_ii"
    # Check polymer before plain tantalum: "tantalum polymer" would otherwise match both.
    for token in _TANTALUM_POLYMER_TOKENS:
        if token in upper:
            return "tantalum_polymer"
    for token in _TANTALUM_TOKENS:
        if token in upper:
            return "tantalum"
    for token in _ELECTROLYTIC_TOKENS:
        if token in upper:
            return "electrolytic"
    for token in _FILM_TOKENS:
        if token in upper:
            return "film"
    return None


_DIELECTRIC_LABEL = {
    "class_i": "Class I",
    "class_ii": "Class II",
    "electrolytic": "aluminium electrolytic",
    "tantalum": "tantalum (non-polymer)",
    "tantalum_polymer": "tantalum polymer",
    "film": "film",
}


def _dielectric_class_rule(
    params_r: dict[str, ParameterValue], params_c: dict[str, ParameterValue]
) -> PolicyResult | None:
    req = params_r.get("dielectric")
    if req is None:
        return None
    req_cls = _dielectric_class(req.raw_text)
    cand = params_c.get("dielectric")
    cand_raw_text = cand.raw_text if cand is not None else None
    cand_cls = _dielectric_class(cand_raw_text)
    if req_cls is None or cand_cls is None:
        reason = (
            f"unable to classify dielectric ('{req.raw_text}' vs '{cand_raw_text}') into a "
            "known dielectric/material class; failing closed"
        )
        return PolicyResult(rule_name="dielectric_class", passed=False, reason=reason)
    passed = req_cls == cand_cls
    reason = (
        f"dielectric requirement {_DIELECTRIC_LABEL[req_cls]} ({req.raw_text}) vs candidate "
        f"{_DIELECTRIC_LABEL[cand_cls]} ({cand_raw_text})"
    )
    return PolicyResult(rule_name="dielectric_class", passed=passed, reason=reason)


_CAPACITOR_VOLTAGE_FACTOR_BY_CLASS = {
    "class_i": "capacitor_class_i_voltage",
    "class_ii": "capacitor_class_ii_voltage",
    "electrolytic": "capacitor_electrolytic_voltage",
    "tantalum": "capacitor_tantalum_voltage",
    "tantalum_polymer": "capacitor_tantalum_polymer_voltage",
    "film": "capacitor_film_voltage",
}


def _capacitor_voltage_factor(
    params_r: dict[str, ParameterValue], config: DeratingConfig
) -> DeratingFactor | None:
    dielectric = params_r.get("dielectric")
    if dielectric is None:
        return None
    cls = _dielectric_class(dielectric.raw_text)
    by_class: dict[str, DeratingFactor] = {
        "class_i": config.capacitor_class_i_voltage,
        "class_ii": config.capacitor_class_ii_voltage,
        "electrolytic": config.capacitor_electrolytic_voltage,
        "tantalum": config.capacitor_tantalum_voltage,
        "tantalum_polymer": config.capacitor_tantalum_polymer_voltage,
        "film": config.capacitor_film_voltage,
    }
    if cls is None:
        return None
    return by_class[cls]


# Rating-like parameters where "higher/equal is safe" per the skill's direction table,
# used as a fail-closed catch-all for any category without a category-specific derating
# factor above (never derate the candidate; compare requirement is derated 1:1 if no
# factor applies -- see `DeratingConfig.no_headroom`).
_RATING_LIKE_PARAMS = (
    "voltage_rating",
    "current_rating",
    "power_rating",
    "reverse_voltage",
    "forward_current",
    "forward_voltage",
    "coil_voltage",
    "contact_current_rating",
    "contact_voltage_rating",
    "breaking_capacity",
    "saturation_current",
)


def _generic_rating_direction_rules(
    params_r: dict[str, ParameterValue],
    params_c: dict[str, ParameterValue],
    config: DeratingConfig,
    handled: frozenset[str],
) -> list[PolicyResult]:
    """Fail-closed floor for any rating-like parameter no category branch already covered."""
    results: list[PolicyResult] = []
    for name in _RATING_LIKE_PARAMS:
        if name in handled:
            continue
        rule = _derated_minimum_rule(
            f"{name}_direction", name, params_r, params_c, config.no_headroom
        )
        if rule is not None:
            results.append(rule)
    return results


def _crystal_frequency_rule(
    params_r: dict[str, ParameterValue], params_c: dict[str, ParameterValue]
) -> PolicyResult | None:
    req = params_r.get("frequency")
    if req is None or req.value is None:
        return None
    cand = params_c.get("frequency")
    if cand is None or cand.value is None:
        return _required_parameter_unknown("frequency")
    tol_param = params_r.get("frequency_tolerance_ppm")
    tol_ppm = (
        tol_param.value if tol_param is not None and tol_param.value is not None else Decimal("0")
    )
    allowed_delta = abs(req.value) * (tol_ppm / Decimal("1000000"))
    lower = req.value - allowed_delta
    upper = req.value + allowed_delta
    passed = lower <= cand.value <= upper
    reason = (
        f"frequency requirement {req.value} {req.unit} (+/-{tol_ppm}ppm) allows {lower} to "
        f"{upper}; candidate {cand.value} {cand.unit}"
    )
    return PolicyResult(rule_name="frequency_match", passed=passed, reason=reason)


def _category_hard_rules(
    category: ComponentCategory,
    params_r: dict[str, ParameterValue],
    params_c: dict[str, ParameterValue],
    config: DeratingConfig,
) -> list[PolicyResult]:
    results: list[PolicyResult] = []
    handled: set[str] = set()
    if category == ComponentCategory.RESISTOR:
        handled.add("power_rating")
        for rule in (
            _nominal_value_rule("resistance", params_r, params_c),
            _tolerance_direction_rule(params_r, params_c),
            _derated_minimum_rule(
                "power_derating", "power_rating", params_r, params_c, config.resistor_power
            ),
        ):
            if rule is not None:
                results.append(rule)
    elif category == ComponentCategory.CAPACITOR:
        handled.add("voltage_rating")
        for rule in (
            _nominal_value_rule("capacitance", params_r, params_c),
            _tolerance_direction_rule(params_r, params_c),
            _dielectric_class_rule(params_r, params_c),
        ):
            if rule is not None:
                results.append(rule)
        voltage_factor = _capacitor_voltage_factor(params_r, config)
        if voltage_factor is not None:
            rule = _derated_minimum_rule(
                "voltage_derating", "voltage_rating", params_r, params_c, voltage_factor
            )
            if rule is not None:
                results.append(rule)
    elif category == ComponentCategory.INDUCTOR:
        handled.update({"saturation_current", "current_rating"})
        for rule in (
            _nominal_value_rule("inductance", params_r, params_c),
            _tolerance_direction_rule(params_r, params_c),
            _derated_minimum_rule(
                "saturation_current_derating",
                "saturation_current",
                params_r,
                params_c,
                config.inductor_saturation_current,
            ),
            _derated_minimum_rule(
                "rms_current_derating",
                "current_rating",
                params_r,
                params_c,
                config.inductor_rms_current,
            ),
        ):
            if rule is not None:
                results.append(rule)
    elif category == ComponentCategory.FERRITE_BEAD:
        handled.add("current_rating")
        for rule in (
            _nominal_value_rule("impedance_at_frequency", params_r, params_c),
            _derated_minimum_rule(
                "current_derating",
                "current_rating",
                params_r,
                params_c,
                config.ferrite_bead_current,
            ),
        ):
            if rule is not None:
                results.append(rule)
    elif category == ComponentCategory.DIODE:
        handled.update({"reverse_voltage", "forward_current"})
        for rule in (
            _derated_minimum_rule(
                "reverse_voltage_derating",
                "reverse_voltage",
                params_r,
                params_c,
                config.diode_reverse_voltage,
            ),
            _derated_minimum_rule(
                "forward_current_derating",
                "forward_current",
                params_r,
                params_c,
                config.diode_forward_current,
            ),
        ):
            if rule is not None:
                results.append(rule)
    elif category == ComponentCategory.LED:
        handled.add("forward_current")
        for rule in (
            _derated_minimum_rule(
                "forward_current_derating",
                "forward_current",
                params_r,
                params_c,
                config.led_forward_current,
            ),
            _nominal_value_rule("forward_voltage", params_r, params_c),
        ):
            if rule is not None:
                results.append(rule)
    elif category == ComponentCategory.TRANSISTOR:
        handled.update({"voltage_rating", "current_rating"})
        for rule in (
            _derated_minimum_rule(
                "voltage_derating", "voltage_rating", params_r, params_c, config.transistor_voltage
            ),
            _derated_minimum_rule(
                "current_derating", "current_rating", params_r, params_c, config.transistor_current
            ),
        ):
            if rule is not None:
                results.append(rule)
    elif category == ComponentCategory.FUSE:
        handled.add("current_rating")
        for rule in (
            _derated_minimum_rule(
                "current_derating",
                "current_rating",
                params_r,
                params_c,
                config.fuse_continuous_current,
            ),
        ):
            if rule is not None:
                results.append(rule)
    elif category == ComponentCategory.RELAY:
        handled.add("contact_current_rating")
        for rule in (
            _nominal_value_rule("coil_voltage", params_r, params_c),
            _derated_minimum_rule(
                "contact_current_derating",
                "contact_current_rating",
                params_r,
                params_c,
                config.relay_contact_current,
            ),
        ):
            if rule is not None:
                results.append(rule)
    elif category == ComponentCategory.CONNECTOR:
        handled.add("current_rating")
        for rule in (
            _nominal_value_rule("pin_count", params_r, params_c),
            _derated_minimum_rule(
                "contact_current_derating",
                "current_rating",
                params_r,
                params_c,
                config.connector_contact_current,
            ),
        ):
            if rule is not None:
                results.append(rule)
    elif category in (ComponentCategory.CRYSTAL, ComponentCategory.OSCILLATOR):
        for rule in (
            _crystal_frequency_rule(params_r, params_c),
            _nominal_value_rule("load_capacitance", params_r, params_c),
        ):
            if rule is not None:
                results.append(rule)
    elif category == ComponentCategory.TRANSFORMER:
        for rule in (
            _nominal_value_rule("turns_ratio", params_r, params_c),
            _nominal_value_rule("primary_inductance", params_r, params_c),
        ):
            if rule is not None:
                results.append(rule)
    results.extend(_generic_rating_direction_rules(params_r, params_c, config, frozenset(handled)))
    return results


def _temperature_range_rule(
    params_r: dict[str, ParameterValue], params_c: dict[str, ParameterValue]
) -> PolicyResult | None:
    req_min = params_r.get("operating_temp_min")
    req_max = params_r.get("operating_temp_max")
    if req_min is None or req_max is None or req_min.value is None or req_max.value is None:
        return None
    cand_min = params_c.get("operating_temp_min")
    cand_max = params_c.get("operating_temp_max")
    if cand_min is None or cand_max is None or cand_min.value is None or cand_max.value is None:
        reason = (
            "required parameter 'operating_temp_min'/'operating_temp_max' is unknown on the "
            "candidate; cannot verify against the requirement"
        )
        return PolicyResult(rule_name="required_parameter_unknown", passed=False, reason=reason)
    passed = cand_min.value <= req_min.value and cand_max.value >= req_max.value
    reason = (
        f"temperature range requires {req_min.value} to {req_max.value} {req_min.unit} "
        f"(wider-or-equal at both ends); candidate covers {cand_min.value} to {cand_max.value} "
        f"{cand_min.unit}"
    )
    return PolicyResult(rule_name="temperature_range", passed=passed, reason=reason)


def _compliance_gate_rules(
    requirement: NormalizedRequirement, candidate: PrePolicyCandidate
) -> list[PolicyResult]:
    results: list[PolicyResult] = []
    for tag, rule_name, label in (
        (ComplianceTag.ROHS, "compliance_rohs", "RoHS"),
        (ComplianceTag.REACH, "compliance_reach", "REACH"),
    ):
        if tag not in requirement.compliance_required:
            continue
        passed = tag in candidate.compliance
        reason = (
            f"{label} required and present in candidate compliance record"
            if passed
            else f"{label} required but candidate compliance record does not include it "
            "(non-compliant or unknown)"
        )
        results.append(PolicyResult(rule_name=rule_name, passed=passed, reason=reason))
    for tag, rule_name, label in (
        (ComplianceTag.AEC_Q100, "qualification_aec_q100", "AEC-Q100"),
        (ComplianceTag.AEC_Q200, "qualification_aec_q200", "AEC-Q200"),
    ):
        if tag not in requirement.compliance_required:
            continue
        passed = tag in candidate.compliance
        reason = (
            f"{label} required and present in candidate compliance record"
            if passed
            else f"{label} required but not recorded for this candidate; qualification may "
            "never be lost"
        )
        results.append(PolicyResult(rule_name=rule_name, passed=passed, reason=reason))
    return results


_LIFECYCLE_RESULTS: dict[Lifecycle, tuple[bool, str]] = {
    Lifecycle.ACTIVE: (True, "candidate lifecycle is active"),
    Lifecycle.NRND: (
        True,
        "candidate lifecycle is nrnd (not recommended for new designs); flagged for review, "
        "not blocked",
    ),
    Lifecycle.EOL: (
        True,
        "candidate lifecycle is eol; stock coverage must be verified downstream before it can be "
        "treated as available",
    ),
    Lifecycle.OBSOLETE: (
        False,
        "candidate lifecycle is obsolete; obsolete parts are never eligible for substitution",
    ),
    Lifecycle.UNKNOWN: (
        True,
        "candidate lifecycle is unknown; never eligible for tier 0 or 1 substitution",
    ),
}


def _lifecycle_rule(lifecycle: Lifecycle) -> PolicyResult:
    passed, reason = _LIFECYCLE_RESULTS[lifecycle]
    return PolicyResult(rule_name="lifecycle", passed=passed, reason=reason)


def _ic_parametric_comparison_rule(
    params_r: dict[str, ParameterValue], params_c: dict[str, ParameterValue]
) -> PolicyResult | None:
    checks: list[str] = []
    all_passed = True
    for name, req in params_r.items():
        cand = params_c.get(name)
        if name == "package_pin_count":
            if req.value is None:
                continue
            if cand is None or cand.value is None:
                all_passed = False
                checks.append(f"{name}: candidate value unknown")
                continue
            ok = cand.value == req.value
            all_passed = all_passed and ok
            checks.append(
                f"{name}: requirement {req.value}, candidate {cand.value} "
                f"({'match' if ok else 'mismatch'})"
            )
            continue
        req_min = req.min if req.min is not None else req.value
        req_max = req.max if req.max is not None else req.value
        if req_min is None and req_max is None:
            continue
        if cand is None or (cand.value is None and cand.min is None and cand.max is None):
            all_passed = False
            checks.append(f"{name}: candidate value unknown")
            continue
        cand_min = cand.min if cand.min is not None else cand.value
        cand_max = cand.max if cand.max is not None else cand.value
        ok = (
            cand_min is not None
            and req_min is not None
            and cand_min <= req_min
            and cand_max is not None
            and req_max is not None
            and cand_max >= req_max
        )
        all_passed = all_passed and ok
        checks.append(
            f"{name}: requirement {req_min}-{req_max}, candidate {cand_min}-{cand_max} "
            f"({'covers' if ok else 'does not cover'})"
        )
    if not checks:
        return None
    reason = "; ".join(checks)
    return PolicyResult(rule_name="parametric_comparison", passed=all_passed, reason=reason)


def _assign_tier(
    requirement: NormalizedRequirement, candidate: PrePolicyCandidate, results: list[PolicyResult]
) -> SubstitutionTier:
    blocking_failed = any(not r.passed for r in results if r.rule_name not in _INFORMATIONAL_RULES)
    if blocking_failed:
        return SubstitutionTier.TIER_3
    specified = requirement.specified_mpn
    if specified is not None and candidate.mpn == specified.mpn:
        return SubstitutionTier.TIER_0
    if requirement.category in _IC_CATEGORIES:
        return SubstitutionTier.TIER_2
    if requirement.category in _TIER_2_MINIMUM_CATEGORIES:
        return SubstitutionTier.TIER_2
    if candidate.lifecycle == Lifecycle.UNKNOWN:
        return SubstitutionTier.TIER_2
    return SubstitutionTier.TIER_1


def evaluate_candidate(
    requirement: NormalizedRequirement,
    candidate: PrePolicyCandidate,
    config: DeratingConfig = DEFAULT_DERATING_CONFIG,
) -> tuple[SubstitutionTier, list[PolicyResult]]:
    """Score one candidate against one requirement. Pure: no I/O, no clock, no RNG."""
    results: list[PolicyResult] = [
        _category_match_rule(requirement),
        _footprint_identity_rule(requirement.footprint, candidate.footprint),
    ]

    criticality = effective_criticality(requirement)
    if criticality == Criticality.STANDARD:
        results.append(
            PolicyResult(
                rule_name="criticality_gate",
                passed=True,
                reason="criticality standard; substitution not restricted by the criticality gate",
            )
        )
        if requirement.specified_mpn is not None:
            results.append(_mpn_identity_rule(requirement, candidate))
    else:
        results.append(_criticality_gate_result(criticality))
        results.append(_exact_mpn_gate_result(criticality, requirement, candidate))

    if requirement.category in _IC_CATEGORIES:
        ic_result = _ic_parametric_comparison_rule(requirement.parameters, candidate.parameters)
        if ic_result is not None:
            results.append(ic_result)
        if criticality == Criticality.STANDARD:
            if requirement.specified_mpn is not None:
                if candidate.mpn != requirement.specified_mpn.mpn:
                    reason = (
                        f"IC requirement pins exact MPN '{requirement.specified_mpn.mpn}'; "
                        f"candidate '{candidate.mpn}' does not match and ICs require engineer "
                        "sign-off to substitute"
                    )
                    results.append(
                        PolicyResult(rule_name="ic_exact_mpn_required", passed=False, reason=reason)
                    )
            else:
                reason = (
                    f"pin-compatible parametric match from a different manufacturer "
                    f"('{candidate.manufacturer}') is capped at tier 2 per IC substitution policy"
                )
                results.append(
                    PolicyResult(
                        rule_name="tier_cap_ic_cross_manufacturer", passed=True, reason=reason
                    )
                )
    else:
        results.extend(
            _category_hard_rules(
                requirement.category, requirement.parameters, candidate.parameters, config
            )
        )

    temp_result = _temperature_range_rule(requirement.parameters, candidate.parameters)
    if temp_result is not None:
        results.append(temp_result)

    results.extend(_compliance_gate_rules(requirement, candidate))
    results.append(_lifecycle_rule(candidate.lifecycle))

    tier = _assign_tier(requirement, candidate, results)
    return tier, results
