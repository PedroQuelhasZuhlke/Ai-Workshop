"""The `normalize_fallback` LLM call site — only for rows the deterministic parser
could not resolve at all. See `.github/instructions/llm-calls.instructions.md` and
`src/pcbpick/llm/templates/normalize_fallback.md`.
"""

from pcbpick.contracts.requirement import NormalizedRequirementFragment
from pcbpick.llm.client import LLMClient, StructuredCallResult, call_structured

TEMPLATE_NAME = "normalize_fallback"


def run_normalize_fallback(
    *,
    client: LLMClient | None,
    raw_cells: dict[str, str],
    category_hint: str | None,
    max_retries: int,
) -> StructuredCallResult[NormalizedRequirementFragment]:
    """Send only this row's cells and the category hint — never the whole BOM, per
    the prompt data-minimization rule. `raw_cells` must already have reference
    designators, project name, and file path stripped by the caller.
    """
    variables = {"row": str(raw_cells), "category_hint": category_hint or ""}
    return call_structured(
        client=client,
        template=TEMPLATE_NAME,
        response_model=NormalizedRequirementFragment,
        variables=variables,
        max_retries=max_retries,
    )
