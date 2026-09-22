import json
from pathlib import Path

import pytest

from pcbpick.errors import RunNotFoundError, StageNotFoundError
from pcbpick.pipeline.runner import PipelineRunner


@pytest.fixture
def source_file(tmp_path: Path) -> Path:
    path = tmp_path / "board.csv"
    path.write_text("Designator,Value\nR1,10k\n", encoding="utf-8")
    return path


def test_run_writes_a_manifest_recording_the_ingest_stage(
    tmp_path: Path, source_file: Path
) -> None:
    runner = PipelineRunner(tmp_path / "runs")

    run_id = runner.run(source_file)

    manifest_path = tmp_path / "runs" / run_id / "meta.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["run_id"] == run_id
    assert manifest["source_file"] == str(source_file)
    assert [stage["stage_name"] for stage in manifest["stages"]] == ["ingest", "normalize"]
    assert (tmp_path / "runs" / run_id / "000-ingest.json").exists()
    assert (tmp_path / "runs" / run_id / "001-normalize.json").exists()


def test_manifest_content_is_stable_across_runs_with_the_same_input(
    tmp_path: Path, source_file: Path
) -> None:
    first_runner = PipelineRunner(tmp_path / "runs1")
    first_runner.run(source_file, run_id="fixed-id")
    first = json.loads((tmp_path / "runs1" / "fixed-id" / "meta.json").read_text(encoding="utf-8"))

    second_runner = PipelineRunner(tmp_path / "runs2")
    second_runner.run(source_file, run_id="fixed-id")
    second = json.loads((tmp_path / "runs2" / "fixed-id" / "meta.json").read_text(encoding="utf-8"))

    assert first["source_file_sha256"] == second["source_file_sha256"]
    # duration_seconds is wall-clock timing and legitimately varies between runs.
    first_stable = [
        {k: v for k, v in stage.items() if k != "duration_seconds"} for stage in first["stages"]
    ]
    second_stable = [
        {k: v for k, v in stage.items() if k != "duration_seconds"} for stage in second["stages"]
    ]
    assert first_stable == second_stable
    assert [stage["stage_name"] for stage in first["stages"]] == ["ingest", "normalize"]


def test_run_rejects_a_reused_run_id(tmp_path: Path, source_file: Path) -> None:
    runner = PipelineRunner(tmp_path / "runs")
    runner.run(source_file, run_id="dupe")

    with pytest.raises(FileExistsError):
        runner.run(source_file, run_id="dupe")


def test_resume_requires_an_existing_run(tmp_path: Path) -> None:
    runner = PipelineRunner(tmp_path / "runs")

    with pytest.raises(RunNotFoundError):
        runner.resume("does-not-exist", from_stage="ingest")


def test_resume_requires_a_registered_stage(tmp_path: Path, source_file: Path) -> None:
    runner = PipelineRunner(tmp_path / "runs")
    run_id = runner.run(source_file)

    with pytest.raises(StageNotFoundError):
        runner.resume(run_id, from_stage="policy")
