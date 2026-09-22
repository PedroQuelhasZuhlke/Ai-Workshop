"""Derating factors as versioned configuration, per `category-rules.md`.

These defaults are **proposed**, not engineering-signed-off physics (see the
"Status of these numbers" note at the top of
`.github/skills/substitution-policy/references/category-rules.md`). Bumping
`DERATING_CONFIG_VERSION` is required whenever a factor below changes, so a run
artifact can always point at the exact factor table that produced its results.
"""

from dataclasses import dataclass
from decimal import Decimal

DERATING_CONFIG_VERSION = "derating-2026.09-proposed-v2"


def _from_percent_of_rated(fraction: str) -> Decimal:
    """`fraction` is the "<=X% of rated" factor; returns the multiplier `1/fraction`."""
    return Decimal("1") / Decimal(fraction)


@dataclass(frozen=True)
class DeratingFactor:
    """`derated_minimum = applied_value * multiplier`."""

    multiplier: Decimal
    description: str


@dataclass(frozen=True)
class DeratingConfig:
    """One versioned snapshot of every derating factor the policy engine applies."""

    version: str
    resistor_power: DeratingFactor
    capacitor_class_i_voltage: DeratingFactor
    capacitor_class_ii_voltage: DeratingFactor
    capacitor_electrolytic_voltage: DeratingFactor
    capacitor_tantalum_voltage: DeratingFactor
    capacitor_tantalum_polymer_voltage: DeratingFactor
    capacitor_film_voltage: DeratingFactor
    inductor_saturation_current: DeratingFactor
    inductor_rms_current: DeratingFactor
    ferrite_bead_current: DeratingFactor
    diode_reverse_voltage: DeratingFactor
    diode_forward_current: DeratingFactor
    led_forward_current: DeratingFactor
    transistor_voltage: DeratingFactor
    transistor_current: DeratingFactor
    fuse_continuous_current: DeratingFactor
    relay_contact_current: DeratingFactor
    connector_contact_current: DeratingFactor
    no_headroom: DeratingFactor


DEFAULT_DERATING_CONFIG = DeratingConfig(
    version=DERATING_CONFIG_VERSION,
    resistor_power=DeratingFactor(
        _from_percent_of_rated("0.6"), "resistor power rating derated to <=60% of rated"
    ),
    capacitor_class_i_voltage=DeratingFactor(
        _from_percent_of_rated("0.8"),
        "Class I ceramic capacitor DC voltage derated to <=80% of rated",
    ),
    capacitor_class_ii_voltage=DeratingFactor(
        _from_percent_of_rated("0.5"),
        "Class II ceramic capacitor DC voltage derated to <=50% of rated",
    ),
    capacitor_electrolytic_voltage=DeratingFactor(
        _from_percent_of_rated("0.8"),
        "aluminium electrolytic capacitor voltage derated to <=80% of rated",
    ),
    capacitor_tantalum_voltage=DeratingFactor(
        _from_percent_of_rated("0.5"),
        "tantalum (non-polymer) capacitor voltage derated to <=50% of rated -- aggressive because "
        "a shorted tantalum capacitor can ignite",
    ),
    capacitor_tantalum_polymer_voltage=DeratingFactor(
        _from_percent_of_rated("0.8"),
        "tantalum polymer capacitor voltage derated to <=80% of rated",
    ),
    capacitor_film_voltage=DeratingFactor(
        _from_percent_of_rated("0.8"), "film capacitor voltage derated to <=80% of rated"
    ),
    inductor_saturation_current=DeratingFactor(
        Decimal("1.5"), "inductor saturation current Isat >= 1.5x peak applied current"
    ),
    inductor_rms_current=DeratingFactor(
        Decimal("1.25"), "inductor RMS current rating Irms >= 1.25x continuous applied current"
    ),
    ferrite_bead_current=DeratingFactor(
        _from_percent_of_rated("0.7"), "ferrite bead current rating derated to <=70% of rated"
    ),
    diode_reverse_voltage=DeratingFactor(
        _from_percent_of_rated("0.8"), "diode/rectifier reverse voltage derated to <=80% of Vrrm"
    ),
    diode_forward_current=DeratingFactor(
        _from_percent_of_rated("0.75"), "diode forward current derated to <=75% of If"
    ),
    led_forward_current=DeratingFactor(
        _from_percent_of_rated("0.8"), "LED forward current derated to <=80% of max"
    ),
    transistor_voltage=DeratingFactor(
        _from_percent_of_rated("0.8"),
        "transistor voltage rating (Vce/Vds) derated to <=80% of rated",
    ),
    transistor_current=DeratingFactor(
        _from_percent_of_rated("0.75"),
        "transistor continuous current (Id) derated to <=75% of rated",
    ),
    fuse_continuous_current=DeratingFactor(
        _from_percent_of_rated("0.75"), "fuse continuous current derated to <=75% of rating"
    ),
    relay_contact_current=DeratingFactor(
        _from_percent_of_rated("0.75"), "relay contact current derated to <=75% of rating"
    ),
    connector_contact_current=DeratingFactor(
        _from_percent_of_rated("0.8"), "connector contact current derated to <=80% of rating"
    ),
    no_headroom=DeratingFactor(
        Decimal("1"),
        "no category-specific derating factor is defined for this parameter; compared directly "
        "against the nameplate requirement with no additional headroom",
    ),
)
