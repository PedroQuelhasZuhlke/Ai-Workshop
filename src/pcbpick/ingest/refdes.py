"""Reference-designator splitting, range expansion, and duplicate detection.

See `.github/skills/bom-ingest/SKILL.md` step 4. Ranges only expand when the prefix
matches on both ends and both suffixes are numeric — `R1-C4` is an error, not a range.
"""

import re

_SPLIT_RE = re.compile(r"[,;]|\s+")
_TOKEN_RE = re.compile(r"^([A-Za-z]+)(\d+)$")


def split_designator_field(raw: str) -> list[str]:
    """Split a raw designator cell on commas/semicolons/whitespace (ranges not yet expanded)."""
    if not raw or not raw.strip():
        return []
    return [token for token in _SPLIT_RE.split(raw.strip()) if token]


def expand_reference_designators(raw: str) -> tuple[list[str], list[str]]:
    """Expand a raw designator field. Returns `(designators, errors)`.

    An unexpandable range token (mismatched prefixes, non-numeric suffix, or reversed
    bounds) is passed through unchanged and recorded as an error rather than dropped.
    """
    designators: list[str] = []
    errors: list[str] = []
    for token in split_designator_field(raw):
        has_dash = "-" in token and not token.startswith("-")
        separator = "-" if has_dash else ".." if ".." in token else None
        if separator is None:
            designators.append(token)
            continue
        left, _, right = token.partition(separator)
        expanded = _expand_range(left, right)
        if expanded is None:
            errors.append(f"invalid reference designator range: {token!r}")
            designators.append(token)
            continue
        designators.extend(expanded)
    return designators, errors


def _expand_range(left: str, right: str) -> list[str] | None:
    left_match = _TOKEN_RE.match(left)
    right_match = _TOKEN_RE.match(right)
    if not left_match or not right_match:
        return None
    left_prefix, left_num = left_match.groups()
    right_prefix, right_num = right_match.groups()
    if left_prefix != right_prefix:
        return None
    start, end = int(left_num), int(right_num)
    if end < start:
        return None
    width = len(left_num)
    return [f"{left_prefix}{str(n).zfill(width)}" for n in range(start, end + 1)]


def find_duplicate_designators(lines_designators: list[list[str]]) -> list[str]:
    """Designators appearing on more than one line across the whole BOM — always `BLOCKING`."""
    seen: set[str] = set()
    dupes: set[str] = set()
    for designators in lines_designators:
        for designator in designators:
            if designator in seen:
                dupes.add(designator)
            seen.add(designator)
    return sorted(dupes)
