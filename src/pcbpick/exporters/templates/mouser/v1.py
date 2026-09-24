"""Mouser BOM upload column template, version 1.

Not verified against Mouser's own current documentation -- see `verified_date` and
`notes`. Per `.github/skills/supplier-export/SKILL.md`: "Verify the current template
against the supplier's own documentation before trusting any column list, including
the ones below. Treat these as starting points."
"""

from pcbpick.contracts.enums import SupplierId
from pcbpick.exporters.templates.base import ExportTemplate

MOUSER_V1 = ExportTemplate(
    supplier=SupplierId.MOUSER,
    version="v1",
    columns=[
        "Mouser Part Number",
        "Manufacturer Part Number",
        "Quantity",
        "Customer Part Number",
    ],
    verified_date="unverified",
    notes=(
        "Verify the current template against the supplier's own documentation before "
        "trusting any column list, including the ones below. Treat these as starting points."
    ),
)
