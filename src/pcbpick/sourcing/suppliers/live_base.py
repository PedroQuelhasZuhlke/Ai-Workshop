"""Shared HTTP orchestration for live `SupplierAdapter` implementations.

Handles what Mouser, DigiKey, and Farnell all need identically: turning one
supplier-specific `httpx.Request` into a `httpx.Response` through the shared
`ResilientCaller`, writing a content-addressed snapshot of whatever it fetched,
stamping the result with that snapshot's real `snapshot_id`/`fetched_at`, and
logging the attempt without ever including a credential. Each concrete adapter
(`mouser.py`, `digikey.py`, `farnell.py`) supplies only the supplier-specific pieces —
how to build a request and how to parse that supplier's JSON response shape into the
`FixtureAdapter` part/sku dict schema. Those response shapes never escape this
package; only `CatalogHit`/`CatalogPart`/`SupplierOffer` do.
"""

import logging
import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from pcbpick.contracts.enums import ComplianceTag, Lifecycle, SupplierId
from pcbpick.contracts.offer import SupplierOffer
from pcbpick.sourcing.freshness import is_stale
from pcbpick.sourcing.manufacturers import normalize_manufacturer
from pcbpick.sourcing.suppliers.resilience import AdapterHttpError, ResilientCaller
from pcbpick.sourcing.suppliers.snapshots import WrittenSnapshot, write_snapshot
from pcbpick.sourcing.types import CatalogHit, CatalogPart, SourcingQuery

logger = logging.getLogger(__name__)

_REDACTED = "<redacted>"
# Every header name (lowercased) that may carry a credential, across all three
# suppliers, so `redact_headers` is one shared list instead of one per adapter.
_SENSITIVE_HEADERS = {"authorization", "x-digikey-client-id", "apikey", "x-api-key"}


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """A copy of `headers` safe to log: every credential-bearing header value replaced."""
    return {
        name: (_REDACTED if name.lower() in _SENSITIVE_HEADERS else value)
        for name, value in headers.items()
    }


def bearer_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# Matches "non"/"not" followed, with no requirement of a word boundary right after
# (so concatenated forms like "noncompliant"/"notrohscompliant" are still caught),
# optionally through "-rohs"/"_rohs"/" rohs", by "compliant" -- e.g. "non-compliant",
# "not compliant", "non-rohs compliant", "not rohs compliant", "noncompliant" -- so a
# negative status is never matched by the bare "compliant" substring check below.
_NEGATED_COMPLIANCE_RE = re.compile(r"\b(non|not)[\s_-]*(rohs[\s_-]*)?compliant")

_LIFECYCLE_KEYWORDS: tuple[tuple[str, Lifecycle], ...] = (
    ("obsolete", Lifecycle.OBSOLETE),
    ("discontinued", Lifecycle.OBSOLETE),
    ("end of life", Lifecycle.EOL),
    ("eol", Lifecycle.EOL),
    ("not recommended", Lifecycle.NRND),
    ("nrnd", Lifecycle.NRND),
    ("active", Lifecycle.ACTIVE),
)


def map_lifecycle(raw: str | None) -> Lifecycle:
    """Maps a supplier's own free-form lifecycle/status string to `Lifecycle`.

    Keyword-matched against the supplier's *stated* word, never inferred from
    anything the supplier didn't say. Unmapped or missing input is `Lifecycle.UNKNOWN`,
    not a guess at `ACTIVE`.
    """
    if raw is None:
        return Lifecycle.UNKNOWN
    lowered = raw.strip().casefold()
    for keyword, lifecycle in _LIFECYCLE_KEYWORDS:
        if keyword in lowered:
            return lifecycle
    return Lifecycle.UNKNOWN


def map_rohs_compliance(rohs_raw: str | bool | None) -> list[ComplianceTag]:
    """Maps a supplier's RoHS flag to `[ComplianceTag.ROHS]` or `[]`.

    Never adds `ComplianceTag.REACH` — no supplier field mapped here states it, and
    inventing it would be a guess, not a normalization. Matched by keyword containment
    (e.g. DigiKey's `"RoHS Compliant"`, Mouser's `"RoHS Compliant"`, Farnell's
    `"Compliant"`) rather than exact equality, but a negation ("non"/"not", optionally
    followed by "rohs") appearing anywhere before "compliant" — e.g.
    `"Non-RoHS Compliant"`, `"Not Compliant"` — must check first so the "compliant"
    substring inside a negative status never flips it to a positive.
    """
    if rohs_raw is None:
        return []
    if isinstance(rohs_raw, bool):
        return [ComplianceTag.ROHS] if rohs_raw else []
    lowered = rohs_raw.strip().casefold()
    if _NEGATED_COMPLIANCE_RE.search(lowered) is not None:
        return []
    is_compliant = lowered in {"yes", "y", "true"} or "compliant" in lowered
    return [ComplianceTag.ROHS] if is_compliant else []


def hits_for_raw_part(raw_part: dict[str, Any]) -> list[CatalogHit]:
    """Mirrors `FixtureAdapter._hits_for_part`, but starting from a not-yet-validated dict."""
    manufacturer = normalize_manufacturer(raw_part["manufacturer"])
    return [
        CatalogHit(mpn=raw_part["mpn"], manufacturer=manufacturer, sku=sku["sku"])
        for sku in raw_part.get("skus", [])
    ]


def build_catalog_part(
    raw_part: dict[str, Any], *, snapshot_id: str, fetched_at: datetime
) -> CatalogPart:
    """Mirrors `FixtureAdapter._load_snapshot_file`'s merge, for a freshly fetched part.

    A raw sku whose `packaging` is `None` (the supplier stated no packaging signal at
    all) is dropped rather than validated with a guessed `Packaging` member —
    `CatalogSku.packaging` has no "unspecified" value to hold the truth honestly, so
    omitting the sku is the only non-fabricating option, exactly like the documented
    moq/spq gap in `build_offer` below.
    """
    skus = [sku for sku in raw_part.get("skus", []) if sku.get("packaging") is not None]
    merged = {
        **raw_part,
        "manufacturer": normalize_manufacturer(raw_part["manufacturer"]),
        "skus": skus,
        "snapshot_id": snapshot_id,
        "fetched_at": fetched_at,
    }
    return CatalogPart.model_validate(merged)


def build_offer(
    raw_sku: dict[str, Any],
    *,
    supplier: SupplierId,
    snapshot_id: str,
    fetched_at: datetime,
) -> SupplierOffer | None:
    """Builds one `SupplierOffer`, or `None` if `moq`/`spq`/`packaging` is unknown.

    `SupplierOffer.moq`/`.spq`/`.packaging` are required (non-`None`) fields today (a
    documented contract gap — see `fixture.py`'s module docstring); fabricating any of
    them to satisfy the type would violate "never default a load-bearing procurement
    value", so an offer that can't state them all is omitted here exactly as
    `FixtureAdapter.offers` omits the moq/spq case.
    """
    moq = raw_sku.get("moq")
    spq = raw_sku.get("spq")
    packaging = raw_sku.get("packaging")
    if moq is None or spq is None or packaging is None:
        return None
    return SupplierOffer.model_validate(
        {
            "supplier": supplier.value,
            "sku": raw_sku["sku"],
            "packaging": raw_sku["packaging"],
            "stock": raw_sku.get("stock"),
            "moq": moq,
            "spq": spq,
            "price_breaks": sorted(raw_sku.get("price_breaks", []), key=lambda pb: pb["quantity"]),
            "lead_time_days": raw_sku.get("lead_time_days"),
            "snapshot_id": snapshot_id,
            "fetched_at": fetched_at,
        }
    )


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


class LiveSupplierAdapter(ABC):
    """Base HTTP/resilience/snapshot/logging orchestration shared by every live adapter.

    Never touches the network at construction: `http_client` is injected (a real
    `httpx.Client` in production, an `httpx.MockTransport`-backed one in every test),
    so `__init__` cannot make a live call.
    """

    supplier_id: SupplierId

    def __init__(
        self,
        *,
        supplier_id: SupplierId,
        http_client: httpx.Client,
        resilient_caller: ResilientCaller,
        snapshot_dir: Path,
        now_fn: Callable[[], datetime] = lambda: datetime.now(UTC),
        run_id: str | None = None,
    ) -> None:
        self.supplier_id = supplier_id
        self._http_client = http_client
        self._resilient_caller = resilient_caller
        self._snapshot_dir = snapshot_dir
        self._now_fn = now_fn
        self._run_id = run_id

    @abstractmethod
    def search(self, query: SourcingQuery) -> list[CatalogHit]: ...

    @abstractmethod
    def details(self, mpn: str) -> CatalogPart | None: ...

    @abstractmethod
    def offers(self, sku: str, quantity: int) -> list[SupplierOffer]: ...

    def revalidate_if_stale(
        self,
        offer: SupplierOffer,
        *,
        quantity: int,
        now: datetime,
        max_age: timedelta,
    ) -> SupplierOffer | None:
        """Re-fetches `offer` only if `freshness.is_stale` judges it too old for export.

        The staleness *decision* is the pure `is_stale` check; this method is the one
        thing allowed to act on it with a network call. A stale offer that no longer
        exists in the supplier's catalog re-fetches to `None` rather than silently
        keeping the stale value.
        """
        if not is_stale(offer.fetched_at, now=now, max_age=max_age):
            return offer
        refreshed = self.offers(offer.sku, quantity)
        return refreshed[0] if refreshed else None

    def _send(self, request: httpx.Request, *, query: str) -> httpx.Response | None:
        """Sends `request` through the shared resilience helper. Logs without credentials."""

        def attempt() -> httpx.Response:
            try:
                response = self._http_client.send(request)
            except httpx.HTTPError as exc:
                raise AdapterHttpError(status_code=None) from exc
            if response.status_code >= 400:
                retry_after = _parse_retry_after(response.headers.get("retry-after"))
                raise AdapterHttpError(
                    status_code=response.status_code, retry_after_seconds=retry_after
                )
            return response

        result = self._resilient_caller.call(attempt)
        logger.info(
            "supplier_request",
            extra={
                "run_id": self._run_id,
                "supplier": self.supplier_id.value,
                "query": query,
                "method": request.method,
                "url": str(request.url),
                "headers": redact_headers(dict(request.headers)),
                "failed": result.failed,
                "error": result.error,
                "attempts": result.attempts,
            },
        )
        if result.failed:
            return None
        return result.value

    def _write_snapshot(self, parts: list[dict[str, Any]]) -> WrittenSnapshot:
        snapshot = write_snapshot(
            supplier=self.supplier_id,
            parts=parts,
            fetched_at=self._now_fn(),
            snapshot_dir=self._snapshot_dir,
        )
        logger.info(
            "supplier_snapshot_written",
            extra={
                "run_id": self._run_id,
                "supplier": self.supplier_id.value,
                "snapshot_id": snapshot.snapshot_id,
            },
        )
        return snapshot
