"""Run replay: re-runs the registered stage chain for a run from a chosen stage
onward, using that stage's stored predecessor artifact as input, and structurally
diffs each recomputed stage's output against what was actually stored.

Scope note: `pipeline.runner.PipelineRunner`/`STAGES` registers only `ingest` and
`normalize` today (see `docs/decision-log.md` section 17's "Gap found before the API
could be built" note) -- `expand`/`source`/`policy`/`evaluate`/`plan`/`export` are
driven directly by `api/orchestrator.py` for the interactive web flow and never write
a `runs/<run_id>/<seq>-<stage>.json` artifact today. This module replays exactly the
chain that actually produced `runs/<run_id>`'s artifacts (`STAGES`, imported directly
from the runner rather than re-listed here) -- it grows automatically the day
`PipelineRunner` registers more stages, with no change needed here.

Known limitation: `IngestInput.project_mapping` (an engineer-confirmed column
mapping, resolved from `mapping_profiles/` at original run time) is not recorded in
`meta.json`/`RunManifest` today, so replaying `--from ingest` for a run that used a
persisted project mapping cannot reproduce that mapping and will show a spurious
`mapping_requires_confirmation`-shaped diff for such runs. Flagged for the
observability follow-up rather than silently worked around here.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Any

from pcbpick.contracts.mapping import IngestResult
from pcbpick.contracts.requirement import NormalizedRequirement
from pcbpick.errors import RunNotFoundError, StageNotFoundError
from pcbpick.ingest.stage import IngestInput
from pcbpick.pipeline.context import PipelineConfig, StageContext
from pcbpick.pipeline.diff import ArtifactDiff, diff_json_values
from pcbpick.pipeline.models import RunManifest
from pcbpick.pipeline.runner import STAGES, safe_run_dir, serialize_stage_result
from pcbpick.pipeline.stage import Stage

# How to turn a stored `<seq>-<stage>.json`'s `"output"` payload back into the typed
# value the *next* stage's `run()` expects as input. Extend when `STAGES` grows.
_STAGE_OUTPUT_DESERIALIZERS: dict[str, Any] = {
    "ingest": lambda raw: IngestResult.model_validate(raw),
    "normalize": lambda raw: [NormalizedRequirement.model_validate(item) for item in raw],
}


@dataclass(frozen=True)
class StageReplayDiff:
    """One replayed stage's structural diff against its originally stored artifact."""

    seq: int
    stage_name: str
    diff: ArtifactDiff


@dataclass(frozen=True)
class ReplayResult:
    run_id: str
    from_stage: str
    stage_diffs: list[StageReplayDiff]

    @property
    def is_identical(self) -> bool:
        return all(d.diff.is_identical for d in self.stage_diffs)


def replay_run(run_id: str, *, runs_root: Path, from_stage: str) -> ReplayResult:
    """Re-runs `STAGES[from_stage:]` for `run_id` and diffs each stage's output
    against the artifact `pcbpick run` originally stored for it."""
    run_dir = safe_run_dir(runs_root, run_id)
    if not run_dir.exists():
        raise RunNotFoundError(f"no run directory for {run_id!r}")

    stage_names = [stage.name for stage in STAGES]
    if from_stage not in stage_names:
        raise StageNotFoundError(
            f"stage {from_stage!r} is not registered; registered stages: {stage_names!r}"
        )
    from_index = stage_names.index(from_stage)

    manifest = RunManifest.model_validate_json((run_dir / "meta.json").read_text(encoding="utf-8"))
    ctx = StageContext(
        run_id=run_id, now=manifest.created_at, rng=Random(run_id), config=PipelineConfig()
    )

    payload: Any
    if from_index == 0:
        source_path = Path(manifest.source_file)
        payload = IngestInput(file_name=source_path.name, content=source_path.read_bytes())
    else:
        predecessor_name = stage_names[from_index - 1]
        predecessor_seq = from_index - 1
        payload = _load_stage_output(run_dir, predecessor_seq, predecessor_name)

    stage_diffs: list[StageReplayDiff] = []
    for seq in range(from_index, len(STAGES)):
        stage: Stage = STAGES[seq]
        result = stage.run(payload, ctx)
        replayed_payload = serialize_stage_result(result)

        artifact_path = run_dir / f"{seq:03d}-{stage.name}.json"
        original_payload = _read_json(artifact_path) if artifact_path.exists() else {}

        stage_diffs.append(
            StageReplayDiff(
                seq=seq,
                stage_name=stage.name,
                diff=diff_json_values(original_payload, replayed_payload),
            )
        )
        payload = result.output

    return ReplayResult(run_id=run_id, from_stage=from_stage, stage_diffs=stage_diffs)


def _load_stage_output(run_dir: Path, seq: int, stage_name: str) -> Any:
    artifact_path = run_dir / f"{seq:03d}-{stage_name}.json"
    payload = _read_json(artifact_path)
    deserializer = _STAGE_OUTPUT_DESERIALIZERS.get(stage_name)
    if deserializer is None:
        raise StageNotFoundError(
            f"no output deserializer registered for stage {stage_name!r}; add one to "
            "pcbpick.pipeline.replay._STAGE_OUTPUT_DESERIALIZERS"
        )
    return deserializer(payload["output"])


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
