"""Regenerates JSON Schema for every contract model under `schema/v<version>/`.

Run after any model change: `python -m pcbpick.contracts.export_schema`.
Schema generation is a build step — never hand-edit files under `schema/`.
"""

import json
from pathlib import Path

from pydantic import BaseModel

from pcbpick.contracts.bom import BomLine
from pcbpick.contracts.candidate import PartCandidate
from pcbpick.contracts.common import (
    Confidence,
    Evidence,
    Footprint,
    MpnRef,
    ParameterValue,
    PriceBreak,
)
from pcbpick.contracts.export import SupplierExport
from pcbpick.contracts.mapping import ColumnMapping, IngestResult, MappingProposal
from pcbpick.contracts.offer import SupplierOffer
from pcbpick.contracts.plan import (
    PlanLine,
    PlanTotals,
    PlanWarning,
    PurchasePlan,
    UnfilledRequirement,
)
from pcbpick.contracts.policy import PolicyResult
from pcbpick.contracts.requirement import NormalizedRequirement, NormalizedRequirementFragment
from pcbpick.contracts.version import SCHEMA_VERSION

MODELS: tuple[type[BaseModel], ...] = (
    BomLine,
    ColumnMapping,
    IngestResult,
    MappingProposal,
    NormalizedRequirement,
    NormalizedRequirementFragment,
    ParameterValue,
    PartCandidate,
    SupplierOffer,
    PurchasePlan,
    SupplierExport,
    Footprint,
    MpnRef,
    Confidence,
    PolicyResult,
    Evidence,
    PriceBreak,
    PlanLine,
    PlanTotals,
    UnfilledRequirement,
    PlanWarning,
)


def schema_dir() -> Path:
    return Path(__file__).parent / "schema" / SCHEMA_VERSION


def export_all(target_dir: Path | None = None) -> dict[str, Path]:
    """Write one JSON Schema file per model. Returns model name -> written path."""
    out_dir = target_dir or schema_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for model in MODELS:
        schema = model.model_json_schema()
        path = out_dir / f"{model.__name__}.json"
        path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written[model.__name__] = path
    return written


if __name__ == "__main__":
    for name, path in sorted(export_all().items()):
        print(f"wrote {name} -> {path}")
