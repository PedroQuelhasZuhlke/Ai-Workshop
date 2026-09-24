"""DigiKey BOM upload column template, version 1.

Not verified against DigiKey's own current documentation -- see `verified_date` and
`notes`. Per `.github/skills/supplier-export/SKILL.md`: "Verify the current template
against the supplier's own documentation before trusting any column list, including
the ones below. Treat these as starting points."
"""

from pcbpick.contracts.enums import SupplierId
from pcbpick.exporters.templates.base import ExportTemplate

DIGIKEY_V1 = ExportTemplate(
    supplier=SupplierId.DIGIKEY,
    version="v1",
    columns=[
        "Quantity",
        "Digi-Key Part Number",
        "Manufacturer Part Number",
        "Customer Reference",
    ],
    verified_date="unverified",
    notes=(
        "Verify the current template against the supplier's own documentation before "
        "trusting any column list, including the ones below. Treat these as starting points."
    ),
)
