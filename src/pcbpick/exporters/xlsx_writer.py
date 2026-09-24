"""XLSX writer for supplier export files.

Same neutralization as `csv_writer`. Part numbers and SKUs that look numeric (e.g.
`0402`) or scientific-notation-like (e.g. `1E4`) must never be coerced into numbers
or dates -- see `.github/skills/supplier-export/SKILL.md`'s "Formula injection" and
"Encoding and formatting" sections.
"""

import io
from datetime import UTC, datetime

from openpyxl import Workbook

from pcbpick.exporters.csv_writer import neutralize

# openpyxl stamps a fresh `datetime.now()` into the workbook's core-properties
# created/modified fields unless told otherwise, which would make this "pure"
# function's output depend on the wall clock -- pinned to a fixed epoch instead so
# two calls with identical rows/columns produce byte-identical files.
_FIXED_TIMESTAMP = datetime(1980, 1, 1, tzinfo=UTC)


def write_xlsx(rows: list[dict[str, str]], columns: list[str]) -> bytes:
    """Renders `rows` restricted to `columns` (in that order) into a single-sheet
    workbook, header row plus one data row per entry in `rows`."""
    workbook = Workbook()
    workbook.properties.created = _FIXED_TIMESTAMP
    workbook.properties.modified = _FIXED_TIMESTAMP
    sheet = workbook.active
    assert sheet is not None  # a freshly constructed Workbook always has an active sheet
    sheet.append(columns)
    for row in rows:
        sheet.append([neutralize(row.get(column, "")) for column in columns])

    # Writing plain `str` values already stops openpyxl's own type inference, but
    # Excel re-infers types from cell content on open unless the cell's own
    # number_format pins it to text -- "@" is that pin, applied to every data cell so
    # a value like "0402" or a neutralize-prefixed "'=SUM(...)" round-trips as text.
    for row_cells in sheet.iter_rows(min_row=2, max_row=sheet.max_row):
        for cell in row_cells:
            cell.number_format = "@"

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
