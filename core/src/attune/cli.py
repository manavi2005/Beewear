"""Command-line entry point: ``attune``.

Commands:
    attune run      Run the pipeline over a time window and print moments + recommendations.
    attune serve    Start the FastAPI ingestion/run service for the companion app.
    attune version  Print the version and active configuration.

The defaults run entirely on synthetic data with the free coach — ``attune run`` works on a
fresh clone with no hardware, keys, or network.
"""

from __future__ import annotations

from datetime import datetime, timezone

import typer

from attune import __version__
from attune.config import get_settings
from attune.pipeline import Pipeline, PipelineResult, default_window

app = typer.Typer(add_completion=False, help="Attune — adaptive coach base layer.")


def _fmt_ts(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%H:%M:%S")


def _print_human(result: PipelineResult) -> None:
    w0, w1 = _fmt_ts(result.start_ms), _fmt_ts(result.end_ms)
    typer.secho(
        f"\n  Attune run  ·  window {w0}–{w1} UTC  ·  coach={result.coach_backend}", bold=True
    )
    typer.echo(
        f"  ingested: {result.n_conversations} conversation(s), "
        f"{result.n_utterances} utterance(s), {result.n_vitals} vital sample(s), "
        f"{result.n_checkins} check-in(s)\n"
    )

    typer.secho(f"  Salient moments ({len(result.salient_moments)}):", bold=True)
    if not result.salient_moments:
        typer.echo("    (none — try `attune run --source synthetic`)")
    for m in result.salient_moments:
        kinds = ", ".join(sorted({s.kind for s in m.signals}))
        typer.echo(f'    [{_fmt_ts(m.ts_ms)}] {m.utterance.speaker}: "{m.utterance.text}"')
        typer.secho(
            f"              signals: {kinds}  (salience {m.salience:.2f})", fg="bright_black"
        )

    typer.secho(f"\n  Recommendations ({len(result.recommendations)}):", bold=True)
    if not result.recommendations:
        typer.echo("    (none)")
    for i, rec in enumerate(result.recommendations, 1):
        typer.secho(f"    {i}. {rec.title}", fg="cyan", bold=True)
        typer.echo(f"       {rec.body}")
        typer.secho(f"       — by {rec.generated_by}", fg="bright_black")
    typer.echo("")


@app.command()
def run(
    source: str | None = typer.Option(None, help="Conversation source: synthetic|replay|bee"),
    vitals: str | None = typer.Option(None, help="Vitals source: synthetic|health_export|api"),
    lookback: int = typer.Option(60, help="Minutes to look back from now."),
    start_ms: int | None = typer.Option(None, help="Explicit window start (UTC epoch ms)."),
    end_ms: int | None = typer.Option(None, help="Explicit window end (UTC epoch ms)."),
    json_out: bool = typer.Option(False, "--json", help="Emit the full result as JSON."),
) -> None:
    """Run source → align → detect → coach and print the result."""
    settings = get_settings()
    overrides: dict = {}
    if source:
        overrides["conversation_source"] = source
    if vitals:
        overrides["vitals_source"] = vitals
    if overrides:
        settings = settings.model_copy(update=overrides)

    window = (start_ms, end_ms) if (start_ms and end_ms) else default_window(lookback)
    result = Pipeline(settings).run(*window)

    if json_out:
        typer.echo(result.model_dump_json(indent=2))
    else:
        _print_human(result)


@app.command()
def serve(
    host: str | None = typer.Option(None, help="Bind host (default from config)."),
    port: int | None = typer.Option(None, help="Bind port (default from config)."),
) -> None:
    """Start the ingestion + run HTTP service (for the companion app)."""
    import uvicorn

    s = get_settings()
    uvicorn.run("attune.api:app", host=host or s.api_host, port=port or s.api_port, reload=False)


@app.command()
def version() -> None:
    """Print version and the active (free-by-default) configuration."""
    s = get_settings()
    typer.echo(f"attune {__version__}")
    typer.echo(f"  vertical            = {s.vertical}")
    typer.echo(f"  conversation_source = {s.conversation_source}")
    typer.echo(f"  vitals_source       = {s.vitals_source}")
    typer.echo(f"  coach_backend       = {s.coach_backend}"
               f"{'  (PAID)' if s.coach_is_paid else '  (free)'}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
