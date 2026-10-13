"""`load_template` — the versioned-template lookup by `SupplierId`.

Only `SupplierId.MOUSER`/`.DIGIKEY`/`.FARNELL` have a registered template;
`SupplierId.FIXTURE` is never a real export destination.
"""

from pcbpick.contracts.enums import SupplierId
from pcbpick.errors import ContractViolationError
from pcbpick.exporters.templates.base import ExportTemplate as ExportTemplate
from pcbpick.exporters.templates.digikey.v1 import DIGIKEY_V1
from pcbpick.exporters.templates.mouser.v1 import MOUSER_V1

_TEMPLATES: dict[SupplierId, ExportTemplate] = {
    SupplierId.MOUSER: MOUSER_V1,
    SupplierId.DIGIKEY: DIGIKEY_V1,
}


def load_template(supplier: SupplierId) -> ExportTemplate:
    """The current (highest-version) template registered for `supplier`.

    Raises `ContractViolationError` for a supplier with no template -- this is a
    programmer error (an unsupported export destination was requested), never bad
    input data.
    """
    template = _TEMPLATES.get(supplier)
    if template is None:
        raise ContractViolationError(f"no export template registered for supplier {supplier!r}")
    return template
