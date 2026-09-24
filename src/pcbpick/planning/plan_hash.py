"""`compute_plan_hash` — the canonical, reproducible digest of a `PurchasePlan`.

Pure function, no wall-clock dependency: the plan's own fields are already fully
determined by the time this is called. Used both as the persisted audit anchor (via
`exporters.stage.ExportStage`) and internally, as `planning.decision_modes`'s final
tie-breaker between equally-scored candidate plans.
"""

import hashlib
import json

from pcbpick.contracts.plan import PurchasePlan


def compute_plan_hash(plan: PurchasePlan) -> str:
    """SHA-256 hex digest of the plan's canonical (sorted-key) JSON representation."""
    canonical = json.dumps(plan.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
