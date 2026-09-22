"""Closed value sets used across the contract layer.

Adding a member here is a minor version bump. Removing one is major and requires a
migration (see `contracts/migrations/`). Any `match` statement over these enums must
handle every member explicitly — never absorb a new member into a catch-all `case _`.
"""

from enum import IntEnum, StrEnum


class ComponentCategory(StrEnum):
    """The category a requirement or candidate belongs to. Drives `categories.py`."""

    RESISTOR = "resistor"
    CAPACITOR = "capacitor"
    INDUCTOR = "inductor"
    FERRITE_BEAD = "ferrite_bead"
    DIODE = "diode"
    LED = "led"
    TRANSISTOR = "transistor"
    IC_ANALOG = "ic_analog"
    IC_DIGITAL = "ic_digital"
    IC_POWER = "ic_power"
    IC_RF = "ic_rf"
    CRYSTAL = "crystal"
    OSCILLATOR = "oscillator"
    CONNECTOR = "connector"
    SWITCH = "switch"
    RELAY = "relay"
    FUSE = "fuse"
    TRANSFORMER = "transformer"
    MECHANICAL = "mechanical"
    MODULE = "module"
    UNKNOWN = "unknown"


class SupplierId(StrEnum):
    MOUSER = "mouser"
    DIGIKEY = "digikey"
    FARNELL = "farnell"
    FIXTURE = "fixture"


class Lifecycle(StrEnum):
    ACTIVE = "active"
    NRND = "nrnd"
    EOL = "eol"
    OBSOLETE = "obsolete"
    UNKNOWN = "unknown"


class Packaging(StrEnum):
    CUT_TAPE = "cut_tape"
    REEL = "reel"
    TUBE = "tube"
    TRAY = "tray"
    BULK = "bulk"


class SubstitutionTier(IntEnum):
    """0 = exact match, 3 = broadest substitution the policy engine allows."""

    TIER_0 = 0
    TIER_1 = 1
    TIER_2 = 2
    TIER_3 = 3


class Criticality(StrEnum):
    STANDARD = "standard"
    SAFETY = "safety"
    DO_NOT_SUBSTITUTE = "do_not_substitute"


class ComplianceTag(StrEnum):
    ROHS = "rohs"
    REACH = "reach"
    AEC_Q100 = "aec_q100"
    AEC_Q200 = "aec_q200"


class DecisionMode(StrEnum):
    LOWEST_COST = "lowest_cost"
    FASTEST_DELIVERY = "fastest_delivery"
    FEWEST_SUPPLIERS = "fewest_suppliers"
    BALANCED = "balanced"
    LOWEST_RISK = "lowest_risk"


class ValueSource(StrEnum):
    PARSED = "parsed"
    LLM_INFERRED = "llm_inferred"
    ENGINEER_ENTERED = "engineer_entered"
    DATASHEET = "datasheet"


class MountingType(StrEnum):
    """Footprint mounting style — part of footprint identity, so it is closed here."""

    SMT = "smt"
    THT = "tht"


class ExportFormat(StrEnum):
    CSV = "csv"
    XLSX = "xlsx"


class PlanWarningKind(StrEnum):
    """Reasons a plan is flagged for engineer attention before approval."""

    STALE_OFFER = "stale_offer"
    NRND_LIFECYCLE = "nrnd_lifecycle"
    EOL_LIFECYCLE = "eol_lifecycle"
    HIGH_TIER_SUBSTITUTION = "high_tier_substitution"
