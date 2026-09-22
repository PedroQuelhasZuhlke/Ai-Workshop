"""Contract migrations for stored run artifacts.

Empty at `v1`. This package starts accepting modules the first time a breaking change
lands (see `.github/instructions/contracts.instructions.md`): each future major bump
adds a module here that upgrades a stored artifact dict from the previous
`schema_version` to the next. Stages never carry compatibility shims for this — the
migration is the only place old data gets translated forward.
"""
