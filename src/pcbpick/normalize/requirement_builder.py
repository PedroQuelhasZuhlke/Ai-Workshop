"""Orchestrates one `BomLine` -> `NormalizedRequirement`.

Order matters: category hint first (value grammar depends on it), then primary-value
parsing, then ratings/dielectric/compliance extraction, then package resolution,
required-parameter validation, criticality, and finally LLM fallback — only for rows
where the deterministic classifier found nothing at all to route on.
"""

from pcbpick.classify.criticality import determine_criticality
from pcbpick.classify.router import hint_category, missing_required_parameters
from pcbpick.contracts.bom import BomLine
from pcbpick.contracts.common import Confidence, Footprint, MpnRef, ParameterValue
from pcbpick.contracts.enums import ComponentCategory, ValueSource
from pcbpick.contracts.requirement import NormalizedRequirement
from pcbpick.ingest.synonyms import matches_target
from pcbpick.llm.client import LLMClient
from pcbpick.normalize import ratings, value_parser
from pcbpick.normalize.llm_fallback import run_normalize_fallback
from pcbpick.normalize.package import resolve_package
from pcbpick.normalize.tolerance import parse_explicit_tolerance_pct
from pcbpick.pipeline.results import Severity, StageIssue

_PRIMARY_PARAMETER_NAME: dict[ComponentCategory, str] = {
    ComponentCategory.RESISTOR: "resistance",
    ComponentCategory.CAPACITOR: "capacitance",
    ComponentCategory.INDUCTOR: "inductance",
}
_PRIMARY_PARSER = {
    ComponentCategory.RESISTOR: value_parser.parse_resistance,
    ComponentCategory.CAPACITOR: value_parser.parse_capacitance,
    ComponentCategory.INDUCTOR: value_parser.parse_inductance,
}
_TOLERANCE_ELIGIBLE_CATEGORIES = frozenset(
    {ComponentCategory.RESISTOR, ComponentCategory.CAPACITOR, ComponentCategory.INDUCTOR}
)


def _find_column(raw: dict[str, str], target: str) -> str | None:
    for header in raw:
        if matches_target(header, target):
            return header
    return None


def _cell(raw: dict[str, str], target: str) -> str:
    column = _find_column(raw, target)
    return raw.get(column, "").strip() if column else ""


def build_requirement(
    line: BomLine,
    *,
    row_index: int,
    llm_client: LLMClient | None,
    max_llm_retries: int,
) -> tuple[NormalizedRequirement, list[StageIssue]]:
    issues: list[StageIssue] = []
    unresolved: list[str] = []
    reasons: list[str] = []
    any_llm_inferred = False

    primary_refdes = line.reference_designators[0] if line.reference_designators else ""
    value_text = _cell(line.raw, "value")
    description_text = _cell(line.raw, "description")
    footprint_text = _cell(line.raw, "footprint")
    manufacturer_text = _cell(line.raw, "manufacturer")
    mpn_text = _cell(line.raw, "mpn")
    combined_text = f"{value_text} {description_text}".strip()

    hint = hint_category(primary_refdes, description_text)
    category = hint.category
    reasons.append(hint.reason)
    if not hint.confident:
        unresolved.append("category")

    parameters: dict[str, ParameterValue] = {}

    parser = _PRIMARY_PARSER.get(category)
    if parser is not None and value_text:
        parsed = parser(value_text)
        param_name = _PRIMARY_PARAMETER_NAME[category]
        reasons.append(parsed.reason)
        if parsed.ambiguous or parsed.value is None:
            unresolved.append(f"parameters.{param_name}")
            reasons.extend(parsed.candidates)
        else:
            parameters[param_name] = ParameterValue(
                value=parsed.value,
                unit=parsed.unit,
                min=parsed.min,
                max=parsed.max,
                raw_text=value_text,
                source=ValueSource.PARSED,
            )
            if parsed.tolerance_pct is not None:
                parameters["tolerance_pct"] = ParameterValue(
                    value=parsed.tolerance_pct,
                    unit="percent",
                    raw_text=value_text,
                    source=ValueSource.PARSED,
                )

    # Explicit tolerance stated separately in free text (e.g. "Resistor 1%") — only
    # used when the value itself didn't already resolve one via a tolerance-table
    # letter, so a code-derived tolerance is never silently overwritten.
    if "tolerance_pct" not in parameters and category in _TOLERANCE_ELIGIBLE_CATEGORIES:
        explicit_pct = parse_explicit_tolerance_pct(combined_text)
        if explicit_pct is not None:
            parameters["tolerance_pct"] = ParameterValue(
                value=explicit_pct,
                unit="percent",
                raw_text=combined_text,
                source=ValueSource.PARSED,
            )

    voltage = ratings.extract_voltage_rating(combined_text)
    if voltage is not None:
        value, matched_text = voltage
        parameters["voltage_rating"] = ParameterValue(
            value=value, unit="volt", raw_text=matched_text, source=ValueSource.PARSED
        )

    current = ratings.extract_current_rating(combined_text)
    if current is not None:
        value, matched_text = current
        parameters["current_rating"] = ParameterValue(
            value=value, unit="ampere", raw_text=matched_text, source=ValueSource.PARSED
        )

    if category == ComponentCategory.CAPACITOR:
        dielectric = ratings.extract_dielectric(combined_text)
        if dielectric is not None:
            parameters["dielectric"] = ParameterValue(
                value=None, unit="", raw_text=dielectric, source=ValueSource.PARSED
            )

    unresolved.extend(missing_required_parameters(category, parameters))

    resolved_package = resolve_package(footprint_text)
    footprint = Footprint(
        package_code=resolved_package.package_code,
        mounting=resolved_package.mounting,
        length_mm=resolved_package.length_mm,
        width_mm=resolved_package.width_mm,
        raw_text=footprint_text or None,
    )
    if footprint_text:
        if not resolved_package.recognized:
            unresolved.append("footprint.package_code")
            reasons.append(f"unrecognized package {footprint_text!r}")
        elif resolved_package.ambiguous_system:
            unresolved.append("footprint.package_system")
            reasons.append(
                f"package {footprint_text!r} states no dimension system and collides "
                "between imperial and metric readings"
            )

    compliance_required, conflicting_compliance = ratings.extract_compliance(combined_text)
    if conflicting_compliance:
        unresolved.append("compliance_required")
        reasons.append("conflicting compliance assertions in free text")
        compliance_required = []

    specified_mpn = (
        MpnRef(mpn=mpn_text, manufacturer=manufacturer_text or None, source=ValueSource.PARSED)
        if mpn_text
        else None
    )

    criticality = determine_criticality(category, combined_text)

    # LLM fallback is only for rows the deterministic classifier found nothing to
    # route on at all — not every partial ambiguity. `call_structured` degrades
    # gracefully (and this stays an INFO issue, never BLOCKING) when no client is
    # configured, matching the M1 column-mapping LLM-tier precedent.
    if category == ComponentCategory.UNKNOWN:
        fallback = run_normalize_fallback(
            client=llm_client,
            raw_cells={
                "value": value_text,
                "description": description_text,
                "footprint": footprint_text,
            },
            category_hint=None,
            max_retries=max_llm_retries,
        )
        if fallback.failed:
            issues.append(
                StageIssue(
                    severity=Severity.INFO,
                    code="llm_fallback_unavailable",
                    message=f"normalize_fallback did not produce a usable result: {fallback.error}",
                    item_id=f"row-{row_index}",
                )
            )
        else:
            fragment = fallback.value
            assert fragment is not None
            any_llm_inferred = True
            reasons.append("category/parameters supplemented by normalize_fallback (llm_inferred)")
            if fragment.category is not None:
                category = fragment.category
            for name, param in fragment.parameters.items():
                parameters.setdefault(name, param)
            if fragment.compliance_required and not compliance_required:
                compliance_required = fragment.compliance_required

    unresolved = sorted(set(unresolved))
    confidence = (
        Confidence(score=0.3, reasons=reasons or ["unresolved fields present"])
        if unresolved or any_llm_inferred
        else Confidence(
            score=0.95, reasons=reasons or ["all required parameters parsed deterministically"]
        )
    )

    requirement = NormalizedRequirement(
        requirement_id=f"req-{row_index:04d}",
        reference_designators=line.reference_designators,
        quantity_per_board=len(line.reference_designators),
        category=category,
        parameters=parameters,
        footprint=footprint,
        specified_mpn=specified_mpn,
        criticality=criticality,
        compliance_required=compliance_required,
        notes=description_text or None,
        confidence=confidence,
        unresolved=unresolved,
    )
    return requirement, issues
