"""Named EDA export profiles: column layouts docs/skills know in advance.

See `.github/skills/bom-ingest/references/eda-export-profiles.md` for the source
material. Profiles are the first and most confident mapping tier — but they are
still just a starting hypothesis, scored against the actual header row, never a
guarantee.
"""

from dataclasses import dataclass

from pcbpick.ingest.synonyms import normalize_header, normalize_header_base

# A profile match requires its designated referrence-designator column to be present
# (the anchor) and enough of its declared header signature to overlap.
PROFILE_MATCH_THRESHOLD = 0.5


@dataclass(frozen=True)
class EdaProfile:
    """One named EDA tool's expected header layout."""

    name: str
    header_signature: frozenset[str]  # normalized header tokens expected from this tool
    refdes_column: str  # normalized header token that carries reference designators
    quantity_column: str | None  # normalized header token that carries stated quantity
    populate_column: str | None  # normalized header token that carries an explicit DNP flag


def _sig(*headers: str) -> frozenset[str]:
    return frozenset(normalize_header(h) for h in headers)


PROFILES: tuple[EdaProfile, ...] = (
    EdaProfile(
        name="altium",
        header_signature=_sig(
            "Designator",
            "Comment",
            "Description",
            "Footprint",
            "LibRef",
            "Quantity",
            "Manufacturer",
            "Manufacturer Part Number",
            "Supplier 1",
            "Supplier Part Number 1",
        ),
        refdes_column=normalize_header("Designator"),
        quantity_column=normalize_header("Quantity"),
        populate_column=normalize_header("Fitted"),
    ),
    EdaProfile(
        name="kicad",
        header_signature=_sig(
            "Reference", "Value", "Datasheet", "Footprint", "Qty", "DNP", "Exclude from BOM"
        ),
        refdes_column=normalize_header("Reference"),
        quantity_column=normalize_header("Qty"),
        populate_column=normalize_header("DNP"),
    ),
    EdaProfile(
        name="kicad_legacy",
        header_signature=_sig(
            "Ref", "Qnty", "Value", "Cmp name", "Footprint", "Description", "Vendor"
        ),
        refdes_column=normalize_header("Ref"),
        quantity_column=normalize_header("Qnty"),
        populate_column=None,
    ),
    EdaProfile(
        name="eagle_fusion",
        header_signature=_sig("Part", "Value", "Device", "Package", "Description"),
        refdes_column=normalize_header("Part"),
        quantity_column=None,
        populate_column=None,
    ),
    EdaProfile(
        name="orcad_allegro",
        header_signature=_sig(
            "Item", "Quantity", "Reference", "Part Number", "PCB Footprint", "Value", "Description"
        ),
        refdes_column=normalize_header("Reference"),
        quantity_column=normalize_header("Quantity"),
        populate_column=None,
    ),
)


def match_eda_profile(headers: list[str]) -> tuple[EdaProfile, float] | None:
    """Best-scoring profile whose anchor (refdes) column is present, above threshold."""
    normalized_bases = {normalize_header_base(h) for h in headers} | {
        normalize_header(h) for h in headers
    }

    best: tuple[EdaProfile, float] | None = None
    for profile in PROFILES:
        if profile.refdes_column not in normalized_bases:
            continue
        overlap = len(profile.header_signature & normalized_bases)
        score = overlap / len(profile.header_signature)
        if best is None or score > best[1]:
            best = (profile, score)

    if best is not None and best[1] >= PROFILE_MATCH_THRESHOLD:
        return best
    return None


def find_column(headers: list[str], normalized_target: str) -> str | None:
    """First original header whose normalized (or trailing-digit-stripped) form matches."""
    for header in headers:
        if (
            normalize_header(header) == normalized_target
            or normalize_header_base(header) == normalized_target
        ):
            return header
    return None
