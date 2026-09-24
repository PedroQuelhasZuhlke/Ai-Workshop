"""CSV writer for supplier export files.

Formula-injection neutralization, RFC 4180 quoting via `csv.DictWriter`, CRLF line
endings, UTF-8 with a BOM -- see `.github/skills/supplier-export/SKILL.md`'s
"Formula injection" and "Encoding and formatting" sections. Never build CSV with
string concatenation or f-strings.
"""

import csv
import io

_RISKY_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def neutralize(cell: str) -> str:
    """Prefixes a cell that Excel/Sheets/LibreOffice could interpret as a formula."""
    if cell and cell[0] in _RISKY_PREFIXES:
        return "'" + cell
    return cell


def write_csv(rows: list[dict[str, str]], columns: list[str]) -> bytes:
    """Renders `rows` restricted to `columns` (in that order) as CRLF, UTF-8-BOM CSV.

    Every cell is neutralized against formula injection, including system-generated
    values -- a manufacturer name or SKU sourced from a supplier catalog is untrusted
    input too.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=columns, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({column: neutralize(row.get(column, "")) for column in columns})
    return buffer.getvalue().encode("utf-8-sig")
