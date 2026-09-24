"""`pcbpick` command-line entry point."""

from pathlib import Path

import click

from pcbpick.errors import PcbPickError
from pcbpick.pipeline.replay import replay_run
from pcbpick.pipeline.runner import STAGES, PipelineRunner

DEFAULT_RUNS_ROOT = Path("runs")


@click.group()
@click.option(
    "--runs-root",
    type=click.Path(path_type=Path),
    default=None,
    envvar="PCBPICK_RUNS_ROOT",
    help="Directory to store run artifacts (default: ./runs).",
)
@click.pass_context
def main(ctx: click.Context, runs_root: Path | None) -> None:
    """pcbpick: BOM to sourced, policy-checked purchase plans."""
    ctx.obj = PipelineRunner(runs_root or DEFAULT_RUNS_ROOT)


@main.command("run")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--project-id", default=None, help="Project id to resolve a persisted column mapping against."
)
@click.pass_obj
def run_command(runner: PipelineRunner, file: Path, project_id: str | None) -> None:
    """Run the pipeline against FILE and print the resulting run id."""
    try:
        run_id = runner.run(file, project_id=project_id)
    except PcbPickError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(run_id)


@main.command("resume")
@click.argument("run_id")
@click.option("--from", "from_stage", required=True, help="Stage name to resume from.")
@click.pass_obj
def resume_command(runner: PipelineRunner, run_id: str, from_stage: str) -> None:
    """Resume RUN_ID from FROM_STAGE."""
    try:
        runner.resume(run_id, from_stage=from_stage)
    except PcbPickError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"resumed {run_id} from {from_stage}")


@main.command("replay")
@click.argument("run_id")
@click.option(
    "--from",
    "from_stage",
    default=STAGES[0].name,
    show_default=True,
    help="Stage name to replay from.",
)
@click.pass_obj
def replay_command(runner: PipelineRunner, run_id: str, from_stage: str) -> None:
    """Re-run RUN_ID's stage chain from FROM_STAGE and diff against stored artifacts.

    Exits non-zero if any replayed stage's output differs from what was originally
    stored -- replay divergence is the entire point of this command, so it must be
    visible in the exit code, not just printed.
    """
    try:
        result = replay_run(run_id, runs_root=runner.runs_root, from_stage=from_stage)
    except PcbPickError as exc:
        raise click.ClickException(str(exc)) from exc

    for stage_diff in result.stage_diffs:
        if stage_diff.diff.is_identical:
            click.echo(f"[{stage_diff.seq:03d}] {stage_diff.stage_name}: identical")
            continue
        click.echo(f"[{stage_diff.seq:03d}] {stage_diff.stage_name}: DIFFERS")
        for change in stage_diff.diff.changes:
            click.echo(
                f"    {change.kind} {change.path}: before={change.before!r} after={change.after!r}"
            )

    if not result.is_identical:
        raise click.ClickException(
            f"replay of {run_id!r} from {from_stage!r} diverged from the stored artifacts"
        )
