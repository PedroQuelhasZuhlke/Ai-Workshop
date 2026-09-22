"""Quantity parsing and refdes/quantity reconciliation.

`BomLine.quantity` always holds the *stated* value verbatim — recomputing it against
the reference-designator count is `normalize`'s job (M2). Ingest only flags disagreement.
"""


def parse_quantity(raw: str | None) -> int | None:
    """Parse a stated quantity cell. `None` for missing/blank/unparseable — never a guess."""
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def has_quantity_mismatch(stated: int | None, designators: list[str]) -> bool:
    """Whether the stated quantity disagrees with the reference-designator count.

    No designators at all means there is nothing to reconcile against (e.g. a
    mechanical item quantified only by the stated column) — not a mismatch.
    """
    if stated is None or not designators:
        return False
    return stated != len(designators)
