"""Unit tests for `pcbpick.pipeline.replay`: a determinism proof for the replay path
itself -- running `PipelineRunner.run()` then replaying from each registered stage
must diff as identical against the artifacts the run itself just wrote.
"""

from pathlib import Path

import pytest

from pcbpick.errors import RunNotFoundError
from pcbpick.pipeline.replay import replay_run
from pcbpick.pipeline.runner import PipelineRunner


@pytest.fixture
def source_file(tmp_path: Path) -> Path:
    path = tmp_path / "board.csv"
    path.write_text("Designator,Value\nR1,10k\nR2,4k7\n", encoding="utf-8")
    return path


def test_replay_from_ingest_is_identical_to_the_stored_run(
    tmp_path: Path, source_file: Path
) -> None:
    runs_root = tmp_path / "runs"
    runner = PipelineRunner(runs_root)
    run_id = runner.run(source_file, run_id="fixed-id")

    result = replay_run(run_id, runs_root=runs_root, from_stage="ingest")

    assert result.is_identical
    assert [d.stage_name for d in result.stage_diffs] == ["ingest", "normalize"]
    for stage_diff in result.stage_diffs:
        assert stage_diff.diff.is_identical, stage_diff.diff.changes


def test_replay_from_normalize_is_identical_to_the_stored_run(
    tmp_path: Path, source_file: Path
) -> None:
    runs_root = tmp_path / "runs"
    runner = PipelineRunner(runs_root)
    run_id = runner.run(source_file, run_id="fixed-id")

    result = replay_run(run_id, runs_root=runs_root, from_stage="normalize")

    assert result.is_identical
    assert [d.stage_name for d in result.stage_diffs] == ["normalize"]


@pytest.mark.parametrize("malicious_run_id", ["../escape", "..\\escape", "..", "", "a/b"])
def test_replay_rejects_a_run_id_that_could_escape_runs_root(
    tmp_path: Path, malicious_run_id: str
) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()

    with pytest.raises(RunNotFoundError):
        replay_run(malicious_run_id, runs_root=runs_root, from_stage="ingest")
