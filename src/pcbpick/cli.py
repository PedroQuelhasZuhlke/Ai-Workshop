"""`pcbpick` command-line entry point."""

from pathlib import Path

import click

from pcbpick.errors import PcbPickError
from pcbpick.pipeline.runner import PipelineRunner

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
