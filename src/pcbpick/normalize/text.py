"""Text normalization shared by the value parser and ratings extraction."""

_MICRO_VARIANTS = {
    "\u00b5": "u",  # MICRO SIGN
    "\u03bc": "u",  # GREEK SMALL LETTER MU
    "\u03a9": "ohm",  # GREEK CAPITAL LETTER OMEGA
    "\u2126": "ohm",  # OHM SIGN
}


def normalize_value_text(raw: str) -> str:
    """Collapse micro-sign and ohm-sign variants to their ASCII equivalents.

    `raw_text` on the resulting `ParameterValue` always keeps the original spelling —
    this function only feeds the parsing grammar, it never reaches an artifact.
    """
    text = raw.strip()
    for variant, replacement in _MICRO_VARIANTS.items():
        text = text.replace(variant, replacement)
    return text
