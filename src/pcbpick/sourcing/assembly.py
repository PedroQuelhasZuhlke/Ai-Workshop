"""Candidate assembly: turns fetched `CatalogPart` data into `PrePolicyCandidate`s.

Pure functions only — no I/O. The `source` stage is the one that calls a
`SupplierAdapter`; this module only transforms data it already has in hand.

## Dedup rule

Two `(requirement_id, CatalogPart)` pairs are the *same* candidate if they share
`(requirement_id, mpn, manufacturer)` after manufacturer normalization. Manufacturer
is normalized here too — defensively and idempotently — even though `FixtureAdapter`
already normalizes on load, because nothing in the `SupplierAdapter` protocol
requires every future adapter to do the same.

This is deliberately an *exact-string* match on `mpn`, never fuzzy or
prefix-based matching:

- Same MPN, **different** manufacturer (the multi-manufacturer-MPN case, e.g. one
  MPN string sold by two makers) is **not** deduped — these are legitimately
  different parts that happen to share an MPN string, and collapsing them would
  hide a real electrical difference (e.g. one is NRND, the other active).
- **Different** MPN strings that merely *look* similar (e.g. a `-TR`
  tape-and-reel packaging suffix on an otherwise identical part) are likewise
  **not** deduped. A naive `str.startswith`/`str.contains` matcher could conflate
  these; this dedup function deliberately does not, because two MPN strings are
  two SKU-orderable part numbers even when they describe the same electrical part.
  Whether they represent "the same part" is a sourcing/procurement judgment call
  for a human or a later stage, not something `assembly.py` silently decides.

When two pairs *do* share the same `(requirement_id, mpn, manufacturer)` key but
their `CatalogPart` payload disagrees (should never happen from one well-formed
snapshot — the same MPN+manufacturer combination describing two different parts
would itself be a data error), the first one encountered in the given input order
wins. This is a defensive-only path, not an expected one.
"""

from pcbpick.contracts.version import SCHEMA_VERSION
from pcbpick.policy.candidate_input import PrePolicyCandidate
from pcbpick.sourcing.manufacturers import normalize_manufacturer
from pcbpick.sourcing.types import CatalogPart


def build_candidate(requirement_id: str, part: CatalogPart) -> PrePolicyCandidate:
    """Maps one fetched `CatalogPart` to a `PrePolicyCandidate` for `requirement_id`."""
    return PrePolicyCandidate(
        schema_version=SCHEMA_VERSION,
        requirement_id=requirement_id,
        mpn=part.mpn,
        manufacturer=normalize_manufacturer(part.manufacturer),
        parameters=part.parameters,
        footprint=part.footprint,
        lifecycle=part.lifecycle,
        compliance=part.compliance,
        snapshot_id=part.snapshot_id,
        fetched_at=part.fetched_at,
    )


def dedup_candidate_pairs(
    pairs: list[tuple[str, CatalogPart]],
) -> list[PrePolicyCandidate]:
    """Collapses `(requirement_id, CatalogPart)` pairs into distinct candidates.

    See the module docstring for the exact dedup key and the two cases that are
    deliberately *not* collapsed. The input is sorted internally before dedup so the
    result never depends on the order `pairs` arrives in — this function does not
    assume its caller already sorted it.
    """
    ordered = sorted(
        pairs,
        key=lambda pair: (pair[0], pair[1].mpn, normalize_manufacturer(pair[1].manufacturer)),
    )

    candidates_by_key: dict[tuple[str, str, str], PrePolicyCandidate] = {}
    for requirement_id, part in ordered:
        candidate = build_candidate(requirement_id, part)
        key = (candidate.requirement_id, candidate.mpn, candidate.manufacturer)
        candidates_by_key.setdefault(key, candidate)  # first-encountered wins; see docstring

    result = list(candidates_by_key.values())
    result.sort(key=lambda c: (c.requirement_id, c.mpn))
    return result
