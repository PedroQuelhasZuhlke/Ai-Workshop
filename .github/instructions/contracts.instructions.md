---
description: "Rules for editing Pydantic contract models and JSON Schema in src/pcbpick/contracts: versioning, breaking changes, provenance fields, migration requirements."
applyTo: "src/pcbpick/contracts/**"
---

# Contract Layer Rules

Read `docs/data-contracts.md` before changing anything in this package. The contracts
are the system's stable interface; stages are disposable, contracts are not.

## Before you edit

Ask whether the change belongs in a stage instead. New derived values usually do.
Only add a contract field when the value must cross a stage boundary or be persisted
in a run artifact.

## Versioning

| Change | Version impact | Required companion work |
|---|---|---|
| Add optional field | minor | none |
| Add required field | **major** | migration + fixtures + evals |
| Rename or retype field | **major** | migration + fixtures + evals |
| Remove field | **major** | migration + deprecation window |
| Add enum member | minor | verify exhaustive `match` statements |
| Remove enum member | **major** | migration |

A major bump requires, in the same change:

1. `schema_version` incremented in `contracts/version.py`
2. Regenerated JSON Schema under `contracts/schema/v<N>/`
3. A migration in `contracts/migrations/` for stored run artifacts
4. Updated fixtures in `fixtures/`
5. Updated golden expectations in `evals/`
6. Every dependent stage updated — no compatibility shims in stage code

Never reuse a field name with changed semantics. Add a new field and deprecate the old.

## Provenance is mandatory

Any field that can come from an external source carries its origin. A bare value with
no attribution is not acceptable in this layer.

```python
class ParameterValue(BaseModel):
    value: Decimal | None
    unit: str
    raw_text: str
    source: ValueSource  # parsed | llm_inferred | engineer_entered | datasheet
```

Supplier-derived models carry `snapshot_id` and `fetched_at`. No exceptions.

## Model configuration

- `model_config = ConfigDict(frozen=True, extra="forbid")` on all artifact models.
  Artifacts are immutable; stages produce new objects.
- `extra="forbid"` catches drift when an adapter or LLM returns unexpected keys.
- Use `Annotated` with validators rather than overriding `__init__`.
- Validators normalize, they do not invent. A validator must never fill in a missing
  value with a default that could be mistaken for real data.

## Enums

Closed sets live here, not in the stages that consume them: `ComponentCategory`,
`SupplierId`, `Lifecycle`, `Packaging`, `SubstitutionTier`, `Criticality`,
`ComplianceTag`, `DecisionMode`, `ValueSource`.

When adding an enum member, search for `match` statements over that enum and handle
the new case explicitly. Do not add a catch-all `case _` that silently absorbs it.

## JSON Schema export

Schema generation is a build step, not a manual edit. Run the export task after any
model change and commit the result — the frontend and artifact validator consume it.
