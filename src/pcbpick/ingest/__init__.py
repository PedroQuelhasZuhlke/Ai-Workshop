"""Turns an arbitrary BOM export into `IngestResult` without losing or inventing data.

See `.github/skills/bom-ingest/SKILL.md` for the domain rules this package implements.
"""

from pcbpick.ingest.stage import IngestInput, IngestStage

__all__ = ["IngestInput", "IngestStage"]
