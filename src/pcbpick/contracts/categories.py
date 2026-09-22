"""Per-category required/optional parameter declarations.

Normalization validates a requirement's `parameters` dict against these sets before it
is allowed to proceed to sourcing. Keys match the parameter names used in
`NormalizedRequirement.parameters` and `PartCandidate.parameters`.
"""

from dataclasses import dataclass, field

from pcbpick.contracts.enums import ComponentCategory


@dataclass(frozen=True)
class CategoryParameterSpec:
    """The parameter names normalization must (`required`) and may (`optional`) populate."""

    required: frozenset[str] = field(default_factory=frozenset)
    optional: frozenset[str] = field(default_factory=frozenset)


_EMPTY = CategoryParameterSpec()

CATEGORY_PARAMETERS: dict[ComponentCategory, CategoryParameterSpec] = {
    ComponentCategory.RESISTOR: CategoryParameterSpec(
        required=frozenset({"resistance", "tolerance_pct"}),
        optional=frozenset({"power_rating", "temperature_coefficient"}),
    ),
    ComponentCategory.CAPACITOR: CategoryParameterSpec(
        required=frozenset({"capacitance", "voltage_rating", "dielectric"}),
        optional=frozenset({"tolerance_pct", "esr"}),
    ),
    ComponentCategory.INDUCTOR: CategoryParameterSpec(
        required=frozenset({"inductance"}),
        optional=frozenset(
            {"tolerance_pct", "current_rating", "dc_resistance", "saturation_current"}
        ),
    ),
    ComponentCategory.FERRITE_BEAD: CategoryParameterSpec(
        required=frozenset({"impedance_at_frequency"}),
        optional=frozenset({"current_rating", "dc_resistance"}),
    ),
    ComponentCategory.DIODE: CategoryParameterSpec(
        required=frozenset({"reverse_voltage", "forward_current"}),
        optional=frozenset({"forward_voltage", "diode_type"}),
    ),
    ComponentCategory.LED: CategoryParameterSpec(
        required=frozenset({"forward_voltage", "forward_current"}),
        optional=frozenset({"color", "luminous_intensity", "viewing_angle"}),
    ),
    ComponentCategory.TRANSISTOR: CategoryParameterSpec(
        required=frozenset({"voltage_rating", "current_rating"}),
        optional=frozenset({"power_rating", "gain_hfe", "transistor_type"}),
    ),
    ComponentCategory.IC_ANALOG: CategoryParameterSpec(
        optional=frozenset({"supply_voltage", "package_pin_count"}),
    ),
    ComponentCategory.IC_DIGITAL: CategoryParameterSpec(
        optional=frozenset({"supply_voltage", "package_pin_count", "logic_family"}),
    ),
    ComponentCategory.IC_POWER: CategoryParameterSpec(
        required=frozenset({"output_voltage"}),
        optional=frozenset(
            {"input_voltage_range", "output_current", "switching_frequency", "package_pin_count"}
        ),
    ),
    ComponentCategory.IC_RF: CategoryParameterSpec(
        optional=frozenset({"frequency_range", "supply_voltage", "output_power"}),
    ),
    ComponentCategory.CRYSTAL: CategoryParameterSpec(
        required=frozenset({"frequency"}),
        optional=frozenset({"load_capacitance", "frequency_tolerance_ppm", "esr"}),
    ),
    ComponentCategory.OSCILLATOR: CategoryParameterSpec(
        required=frozenset({"frequency"}),
        optional=frozenset({"supply_voltage", "frequency_stability_ppm", "output_type"}),
    ),
    ComponentCategory.CONNECTOR: CategoryParameterSpec(
        required=frozenset({"pin_count"}),
        optional=frozenset({"pitch", "current_rating", "voltage_rating", "mounting_type"}),
    ),
    ComponentCategory.SWITCH: CategoryParameterSpec(
        optional=frozenset({"current_rating", "voltage_rating", "actuation_type"}),
    ),
    ComponentCategory.RELAY: CategoryParameterSpec(
        required=frozenset({"coil_voltage", "contact_current_rating"}),
        optional=frozenset({"contact_voltage_rating", "coil_resistance"}),
    ),
    ComponentCategory.FUSE: CategoryParameterSpec(
        required=frozenset({"current_rating", "voltage_rating"}),
        optional=frozenset({"breaking_capacity", "response_time"}),
    ),
    ComponentCategory.TRANSFORMER: CategoryParameterSpec(
        optional=frozenset({"turns_ratio", "primary_inductance", "isolation_voltage"}),
    ),
    ComponentCategory.MECHANICAL: _EMPTY,
    ComponentCategory.MODULE: _EMPTY,
    ComponentCategory.UNKNOWN: _EMPTY,
}
