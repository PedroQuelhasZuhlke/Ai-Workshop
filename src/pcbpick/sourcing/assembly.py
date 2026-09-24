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

## Offer union

Every pair also carries the `SupplierOffer`s the `source` stage fetched for that
specific hit's SKU. When two hits (e.g. two SKUs of the same manufacturer part)
dedup to the same candidate key, their offers are unioned rather than one winning
over the other — a candidate should expose every purchasable SKU sourcing found for
it, not just the first one. The union is keyed on `(supplier.value, sku)` and sorted
on that same key before being attached, so the result never depends on dict/set
iteration order or on the order `pairs` arrived in.
"""

from pcbpick.contracts.offer import SupplierOffer
from pcbpick.contracts.version import SCHEMA_VERSION
from pcbpick.policy.candidate_input import PrePolicyCandidate
from pcbpick.sourcing.manufacturers import normalize_manufacturer
from pcbpick.sourcing.types import CatalogPart


def build_candidate(
    requirement_id: str, part: CatalogPart, offers: list[SupplierOffer] | None = None
) -> PrePolicyCandidate:
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
        offers=offers or [],
    )


def dedup_candidate_pairs(
    pairs: list[tuple[str, CatalogPart, list[SupplierOffer]]],
) -> list[PrePolicyCandidate]:
    """Collapses `(requirement_id, CatalogPart, offers)` pairs into distinct candidates.

    See the module docstring for the exact dedup key, the two cases that are
    deliberately *not* collapsed, and how offers are unioned across pairs that do
    share a key. The input is sorted internally before dedup so the result never
    depends on the order `pairs` arrives in — this function does not assume its
    caller already sorted it.
    """
    ordered = sorted(
        pairs,
        key=lambda pair: (pair[0], pair[1].mpn, normalize_manufacturer(pair[1].manufacturer)),
    )

    candidates_by_key: dict[tuple[str, str, str], PrePolicyCandidate] = {}
    offers_by_key: dict[tuple[str, str, str], dict[tuple[str, str], SupplierOffer]] = {}
    for requirement_id, part, offers in ordered:
        key = (
            requirement_id,
            part.mpn,
            normalize_manufacturer(part.manufacturer),
        )
        candidates_by_key.setdefault(
            key, build_candidate(requirement_id, part)
        )  # first-encountered wins for non-offer fields; see docstring
        offer_map = offers_by_key.setdefault(key, {})
        for offer in offers:
            offer_map[(offer.supplier.value, offer.sku)] = offer

    result: list[PrePolicyCandidate] = []
    for key, candidate in candidates_by_key.items():
        merged_offers = [offers_by_key[key][offer_key] for offer_key in sorted(offers_by_key[key])]
        result.append(candidate.model_copy(update={"offers": merged_offers}))

    # `manufacturer` makes this key total on its own -- see the dedup rule above,
    # the multi-manufacturer-MPN case means `(requirement_id, mpn)` alone can tie.
    result.sort(key=lambda c: (c.requirement_id, c.mpn, c.manufacturer))
    return result
