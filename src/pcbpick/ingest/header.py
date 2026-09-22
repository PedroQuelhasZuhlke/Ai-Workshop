"""Header-row detection: scan the first rows of a grid for a title block above the header.

See `.github/skills/bom-ingest/SKILL.md` step 2. Exports routinely carry a title
block, logo rows, or project metadata above the real header — this scores each of
the first ~30 rows as a header candidate rather than assuming row 0.
"""

from pcbpick.ingest.synonyms import ALL_HEADER_TOKENS, normalize_header, normalize_header_base

SCAN_LIMIT = 30

_FILL_WEIGHT = 0.3
_TOKEN_WEIGHT = 0.6
_NEXT_ROW_DATA_WEIGHT = 0.1


def find_header_row(grid: list[list[str]]) -> int:
    """Index of the best-scoring header candidate among the first `SCAN_LIMIT` rows."""
    best_index = 0
    best_score = -1.0
    for index in range(min(len(grid), SCAN_LIMIT)):
        score = _score_candidate(grid, index)
        if score > best_score:
            best_score = score
            best_index = index
    return best_index


def _score_candidate(grid: list[list[str]], index: int) -> float:
    row = grid[index]
    non_empty = sum(1 for cell in row if cell.strip())
    if non_empty == 0:
        return -1.0

    fill_ratio = non_empty / len(row)
    token_hits = sum(1 for cell in row if _is_known_token(cell))
    token_ratio = token_hits / non_empty

    next_row_has_data = 0.0
    if index + 1 < len(grid) and any(cell.strip() for cell in grid[index + 1]):
        next_row_has_data = 1.0

    return (
        fill_ratio * _FILL_WEIGHT
        + token_ratio * _TOKEN_WEIGHT
        + next_row_has_data * _NEXT_ROW_DATA_WEIGHT
    )


def _is_known_token(cell: str) -> bool:
    if not cell.strip():
        return False
    return (
        normalize_header(cell) in ALL_HEADER_TOKENS
        or normalize_header_base(cell) in ALL_HEADER_TOKENS
    )
