"""Farnell / element14 BOM upload column template, version 1.

Not verified against Farnell's own current documentation -- see `verified_date` and
`notes`. Per `.github/skills/supplier-export/SKILL.md`: "Verify the current template
against the supplier's own documentation before trusting any column list, including
the ones below. Treat these as starting points."
"""

from pcbpick.contracts.enums import SupplierId
from pcbpick.exporters.templates.base import ExportTemplate

FARNELL_V1 = ExportTemplate(
    supplier=SupplierId.FARNELL,
    version="v1",
    columns=["Order Code", "Quantity", "Line Note"],
    verified_date="unverified",
    notes=(
        "Verify the current template against the supplier's own documentation before "
        "trusting any column list, including the ones below. Treat these as starting points."
    ),
)
