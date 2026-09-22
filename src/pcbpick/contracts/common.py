"""Small value types embedded inside multiple top-level contract artifacts."""

from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from pcbpick.contracts.enums import MountingType, ValueSource


def _non_empty(text: str) -> str:
    if not text.strip():
        raise ValueError("must not be empty")
    return text


def _iso4217(code: str) -> str:
    if len(code) != 3 or not code.isalpha() or not code.isupper():
        raise ValueError("currency must be a 3-letter uppercase ISO 4217 code")
    return code


NonEmptyStr = Annotated[str, AfterValidator(_non_empty)]
CurrencyCode = Annotated[str, AfterValidator(_iso4217)]


class ParameterValue(BaseModel):
    """A single requirement or candidate parameter — always a value plus its provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: Decimal | None
    unit: str
    tolerance_pct: Annotated[Decimal, Field(ge=0)] | None = None
    min: Decimal | None = None
    max: Decimal | None = None
    raw_text: NonEmptyStr
    source: ValueSource


class Footprint(BaseModel):
    """Package/land-pattern identity. Substitutions must match every known field exactly."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    package_code: str | None = None
    mounting: MountingType | None = None
    pin_count: Annotated[int, Field(gt=0)] | None = None
    pitch_mm: Decimal | None = None
    length_mm: Decimal | None = None
    width_mm: Decimal | None = None
    height_mm: Decimal | None = None
    thermal_pad: bool | None = None
    raw_text: str | None = None


class MpnRef(BaseModel):
    """A manufacturer part number reference, with provenance for where it was captured."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mpn: NonEmptyStr
    manufacturer: str | None = None
    source: ValueSource


class Confidence(BaseModel):
    """Normalization confidence and the reasons behind it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    score: Annotated[float, Field(ge=0.0, le=1.0)]
    reasons: list[str] = Field(default_factory=list)


class Evidence(BaseModel):
    """A pointer to where a candidate's data came from — datasheet, catalog field, snapshot."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    description: NonEmptyStr
    url: str | None = None
    snapshot_id: str | None = None
    field_name: str | None = None


class PriceBreak(BaseModel):
    """One (quantity, unit_price) rung on a supplier's price-break ladder."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    quantity: Annotated[int, Field(gt=0)]
    unit_price: Annotated[Decimal, Field(ge=0)]
    currency: CurrencyCode
