"""`ExportTemplate` — one versioned supplier column list.

Stored as plain Python modules with dataclass literals rather than YAML: PyYAML is
not a project dependency (see `pyproject.toml`), and
`.github/instructions/python.instructions.md` disallows adding a new dependency for
a need this small. `openpyxl` (already a dependency) has no bearing on this format
choice -- it is unrelated, used only by `xlsx_writer`.
"""

from dataclasses import dataclass

from pcbpick.contracts.enums import SupplierId


@dataclass(frozen=True)
class ExportTemplate:
    """One supplier's column template at one version."""

    supplier: SupplierId
    version: str
    columns: list[str]
    verified_date: str
    notes: str
