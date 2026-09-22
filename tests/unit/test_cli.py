from pathlib import Path

from click.testing import CliRunner

from pcbpick.cli import main


def test_run_then_resume_from_unregistered_stage(tmp_path: Path) -> None:
    source = tmp_path / "board.csv"
    source.write_text("Designator,Value\nR1,10k\n", encoding="utf-8")
    runs_root = tmp_path / "runs"

    runner = CliRunner()
    result = runner.invoke(main, ["--runs-root", str(runs_root), "run", str(source)])
    assert result.exit_code == 0, result.output
    run_id = result.output.strip()
    assert (runs_root / run_id / "meta.json").exists()

    resume_result = runner.invoke(
        main, ["--runs-root", str(runs_root), "resume", run_id, "--from", "policy"]
    )
    assert resume_result.exit_code != 0
    assert "policy" in resume_result.output


def test_run_then_resume_from_registered_stage(tmp_path: Path) -> None:
    source = tmp_path / "board.csv"
    source.write_text("Designator,Value\nR1,10k\n", encoding="utf-8")
    runs_root = tmp_path / "runs"

    runner = CliRunner()
    result = runner.invoke(main, ["--runs-root", str(runs_root), "run", str(source)])
    assert result.exit_code == 0, result.output
    run_id = result.output.strip()

    resume_result = runner.invoke(
        main, ["--runs-root", str(runs_root), "resume", run_id, "--from", "normalize"]
    )
    assert resume_result.exit_code == 0, resume_result.output


def test_resume_unknown_run_id_fails(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    runs_root.mkdir()

    runner = CliRunner()
    result = runner.invoke(
        main, ["--runs-root", str(runs_root), "resume", "nope", "--from", "ingest"]
    )
    assert result.exit_code != 0
    assert "nope" in result.output
