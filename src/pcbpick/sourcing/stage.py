"""The `source` pipeline stage: turns `SourcingQuery`s into `PrePolicyCandidate`s.

Purity note: the only I/O this stage performs is calling the `SupplierAdapter`s it
was constructed with — adapters are the sanctioned I/O exception per
`.github/instructions/pipeline-stages.instructions.md`; this stage itself opens no
connection and reads no file. No clock, no RNG.

## The manufacturer-ambiguous `details()` case

`SupplierAdapter.details(mpn)` takes only an MPN and, per its documented contract
(see `pcbpick.sourcing.suppliers.fixture`'s module docstring), can return at most one
`CatalogPart` — the first the adapter finds. When one MPN string is shared by
multiple manufacturers (the "multi-manufacturer-MPN" case), `search()` surfaces every
manufacturer as a distinct `CatalogHit`, but `details()` cannot be asked for a
specific one: calling it repeatedly for the same MPN always returns the same
(arbitrary, first-loaded) part.

This stage never attributes that returned `CatalogPart`'s data to a hit whose
manufacturer doesn't match it — doing so would silently invent electrical
parameters, lifecycle, and compliance facts for a part the adapter never actually
returned. Instead, a hit is only turned into a candidate when the fetched
`CatalogPart.manufacturer` (normalized) matches the hit's own `manufacturer`
(normalized); otherwise it is skipped and recorded as a `catalog_details_missing`
issue — from this stage's point of view, authoritative details for that specific
manufacturer are unavailable through this adapter, which is true even though
`details()` did technically return *something*.
"""

from pcbpick.contracts.offer import SupplierOffer
from pcbpick.pipeline.context import StageContext
from pcbpick.pipeline.results import Severity, StageIssue, StageResult
from pcbpick.policy.candidate_input import PrePolicyCandidate
from pcbpick.sourcing.assembly import dedup_candidate_pairs
from pcbpick.sourcing.manufacturers import normalize_manufacturer
from pcbpick.sourcing.suppliers.protocol import SupplierAdapter
from pcbpick.sourcing.types import CatalogPart, SourcingQuery


class SourceStage:
    """Searches every configured adapter for each query and assembles deduped candidates."""

    name = "source"

    def __init__(self, adapters: list[SupplierAdapter]) -> None:
        self._adapters = adapters

    def run(
        self, inp: list[SourcingQuery], ctx: StageContext
    ) -> StageResult[list[PrePolicyCandidate]]:
        del ctx  # source needs no clock or randomness

        output: list[PrePolicyCandidate] = []
        issues: list[StageIssue] = []

        for query in inp:
            pairs: list[tuple[str, CatalogPart, list[SupplierOffer]]] = []

            for adapter in self._adapters:
                for hit in adapter.search(query):
                    part = adapter.details(hit.mpn)
                    if part is None:
                        issues.append(
                            StageIssue(
                                severity=Severity.WARNING,
                                code="catalog_details_missing",
                                message=(
                                    f"adapter {adapter.supplier_id.value!r} returned a search "
                                    f"hit for mpn {hit.mpn!r} (sku {hit.sku!r}) but details() "
                                    "returned no CatalogPart"
                                ),
                                item_id=query.requirement_id,
                            )
                        )
                        continue

                    if normalize_manufacturer(part.manufacturer) != normalize_manufacturer(
                        hit.manufacturer
                    ):
                        # details() can only ever return one manufacturer's data for a
                        # shared MPN; see the module docstring. Attributing it to a hit
                        # from a different manufacturer would invent facts about a part
                        # the adapter never actually returned.
                        issues.append(
                            StageIssue(
                                severity=Severity.WARNING,
                                code="catalog_details_missing",
                                message=(
                                    f"adapter {adapter.supplier_id.value!r} search hit for mpn "
                                    f"{hit.mpn!r} attributed to manufacturer "
                                    f"{hit.manufacturer!r}, but details() can only return the "
                                    f"{part.manufacturer!r} part for this MPN; skipping rather "
                                    "than attributing mismatched data"
                                ),
                                item_id=query.requirement_id,
                            )
                        )
                        continue

                    # quantity=1 is a nominal lookup value -- the fixture adapter ignores
                    # it and always returns the full pinned price-break ladder; a future
                    # adapter that filters by quantity would still return usable offers.
                    offers = adapter.offers(hit.sku, quantity=1)
                    pairs.append((query.requirement_id, part, offers))

            candidates = dedup_candidate_pairs(pairs)
            if not candidates:
                issues.append(
                    StageIssue(
                        severity=Severity.WARNING,
                        code="no_candidates_found",
                        message=(
                            f"no candidates found for requirement {query.requirement_id} "
                            "across any configured adapter"
                        ),
                        item_id=query.requirement_id,
                    )
                )
            output.extend(candidates)

        # `manufacturer` makes this key total: the multi-manufacturer-MPN case (see
        # `sourcing.assembly`'s module docstring) means `(requirement_id, mpn)` alone can tie.
        output.sort(key=lambda c: (c.requirement_id, c.mpn, c.manufacturer))
        return StageResult(output=output, issues=issues)
