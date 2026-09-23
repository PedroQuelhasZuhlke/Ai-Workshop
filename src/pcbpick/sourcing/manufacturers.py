"""Canonical manufacturer name lookup.

Lives in `sourcing/`, not inside any one adapter, because it is shared infrastructure:
every `SupplierAdapter` must normalize the manufacturer name it returns before it leaves
the adapter (per `.github/instructions/supplier-adapters.instructions.md`), and candidate
assembly/dedup later needs the *same* canonical form to recognize that "TI", "Texas
Instruments", and "TEXAS INSTRUMENTS" from three different suppliers are one manufacturer.
Duplicating this table per adapter would let two adapters disagree on the canonical name
for the same manufacturer, silently breaking dedup.

Unknown names pass through unchanged: inventing a canonical form for a name this table
doesn't recognize would be a guess, not a normalization.
"""

_CANONICAL_BY_KEY: dict[str, str] = {
    "ti": "Texas Instruments",
    "texas instruments": "Texas Instruments",
    "st": "STMicroelectronics",
    "stmicro": "STMicroelectronics",
    "stmicroelectronics": "STMicroelectronics",
    "yageo": "Yageo",
    "murata": "Murata",
    "murata manufacturing": "Murata",
    "murata manufacturing co., ltd.": "Murata",
    "abracon": "Abracon",
    "abracon llc": "Abracon",
    "vishay": "Vishay",
    "vishay intertechnology": "Vishay",
    "littelfuse": "Littelfuse",
    "littelfuse inc": "Littelfuse",
    "littelfuse, inc.": "Littelfuse",
    "littelfuse inc.": "Littelfuse",
    "kemet": "KEMET",
    "kemet corporation": "KEMET",
    "kemet electronics": "KEMET",
    "kemet electronics corporation": "KEMET",
    "bel fuse": "Bel Fuse",
    "bel fuse inc": "Bel Fuse",
    "bel fuse inc.": "Bel Fuse",
    "belfuse": "Bel Fuse",
    "belfuse inc.": "Bel Fuse",
    "wurth elektronik": "Wurth Elektronik",
    "würth elektronik": "Wurth Elektronik",
    "wurth electronics": "Wurth Elektronik",
}


def normalize_manufacturer(name: str) -> str:
    """Maps a raw manufacturer string to its canonical form. Passes unknown names through."""
    key = " ".join(name.split()).casefold()
    return _CANONICAL_BY_KEY.get(key, name)
