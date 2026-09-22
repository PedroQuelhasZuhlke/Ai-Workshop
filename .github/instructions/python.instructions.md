---
description: "Python conventions for the PCB parts picking tool: Decimal money, SI units, None for unknown, pure functions, typing and error handling."
applyTo: "**/*.py"
---

# Python Conventions

## Types and values

- Python 3.12+. Full type annotations on every public function. `from __future__ import annotations` is unnecessary — use modern syntax (`str | None`, `list[str]`).
- Money is `Decimal` plus an explicit ISO 4217 currency code. `float` for money is a bug.
- Physical quantities are `Decimal` in SI base units (`ohm`, `farad`, `henry`, `volt`, `ampere`, `watt`, `kelvin`), with the original string preserved.
- Unknown is `None`. Never `0`, `-1`, `""`, `"N/A"`, or `"unknown"` as a sentinel.
- Enums for all closed value sets. No bare string literals for categories, suppliers, lifecycle states, decision modes.

```python
# wrong
unit_price: float = 0.0
stock = row.get("stock", 0)

# right
unit_price: Decimal | None = None
currency: str = "EUR"
stock: int | None = _parse_int(row.get("stock"))
```

## Purity

- Business logic modules (`normalize`, `classify`, `policy`, `planning`, `exporters`) perform no I/O, read no environment variables, and call no clock. Pass time in.
- Randomness and `datetime.now()` come from `StageContext`, never from module level. Runs must be reproducible.
- No module-level mutable state, no singletons, no import-time side effects.

## Errors

- Raise domain exceptions from `pcbpick.errors`, not bare `ValueError`.
- Never swallow an exception to return a default. If a value cannot be determined, return `None` and record the reason in the artifact.
- `except Exception` is only acceptable at a stage boundary or adapter boundary, and must log with the run id and re-raise or convert to a recorded failure.

## Structure

- Functions do one thing. If a function both parses and decides, split it.
- Prefer module-level pure functions over classes. Use classes for adapters, protocols, and Pydantic models.
- Keep public surface small: `__all__` in package `__init__.py`.

## Formatting and tooling

- `ruff` for lint and format, `mypy --strict` for `src/`. Both must pass before a change is complete.
- `uv` for dependency and environment management. Do not invoke `pip` directly.

## Comments

Write a comment only to explain something the code cannot show — a datasheet
convention, a supplier quirk, a regulatory constraint. Do not restate the code.

```python
# SPQ, not MOQ, drives the rounding: suppliers ship whole packs even above MOQ.
order_qty = _round_up_to_multiple(required_qty, offer.spq)
```
