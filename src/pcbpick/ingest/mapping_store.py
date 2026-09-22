"""Per-project confirmed column-mapping persistence.

A mapping profile is a project's engineer-confirmed column -> target-field resolution,
stored as JSON keyed by project id so the next BOM revision for that project resolves
via `MappingMethod.PROJECT_MEMORY` instead of falling through to heuristics again.

This module performs disk I/O and is deliberately kept out of `ingest/stage.py`: per
`pipeline-stages.instructions.md`, a stage may not read files itself. The caller (CLI
or, eventually, the API layer) loads a mapping with `load()` before invoking the
stage, and persists a *confirmed* mapping with `save()` after an engineer approves
it — ingest never calls `save()` on its own heuristic guess.
"""

import json
from pathlib import Path


class MappingProfileStore:
    """Reads and writes confirmed mappings under `<root>/<project_id>.json`."""

    def __init__(self, root: Path) -> None:
        self._root = root

    def load(self, project_id: str) -> dict[str, str] | None:
        path = self._root / f"{project_id}.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {str(key): str(value) for key, value in payload.items()}

    def save(self, project_id: str, mapping: dict[str, str]) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._root / f"{project_id}.json"
        path.write_text(json.dumps(mapping, indent=2, sort_keys=True), encoding="utf-8")
