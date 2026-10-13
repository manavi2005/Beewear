"""Command-line entry point: ``attune``.

Commands:
    attune run             Run the pipeline and print moments + recommendations.
    attune serve           Start the FastAPI ingestion/run service + dashboard.
    attune simulate-watch  Stream fake Apple Watch vitals to a running server (no Watch needed).
    attune doctor          Readiness check for testing on your Apple Watch.
    attune version         Print the version and active configuration.

The defaults run entirely on synthetic data with the free coach — ``attune run`` works on a
fresh clone with no hardware, keys, or network.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import typer

from attune import __version__
from attune.config import get_settings
from attune.pipeline import Pipeline, PipelineResult, default_window, now_ms

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
    lan: bool = typer.Option(
        False, "--lan", help="Bind 0.0.0.0 and print the LAN URL for your phone/Watch."
    ),
) -> None:
    """Start the ingestion + run HTTP service + dashboard (for the companion app)."""
    import uvicorn

    from attune.netutil import lan_url

    s = get_settings()
    bind_port = port or s.api_port
    bind_host = host or ("0.0.0.0" if lan else s.api_host)
    typer.secho(f"\n  Dashboard:  http://127.0.0.1:{bind_port}/", fg="cyan", bold=True)
    if lan:
        url = lan_url(bind_port)
        if url:
            typer.secho(f"  On the LAN: {url}/", fg="cyan")
            typer.secho(
                f"  → paste {url} into the companion app's backend URL (BackendConfig).\n",
                fg="bright_black",
            )
        else:
            typer.secho("  (couldn't detect a LAN IP — check your Wi-Fi)\n", fg="yellow")
    uvicorn.run("attune.api:app", host=bind_host, port=bind_port, reload=False)


@app.command("simulate-watch")
def simulate_watch(
    url: str = typer.Option("http://127.0.0.1:8000", help="Running attune server base URL."),
    minutes: float = typer.Option(3.0, help="How long to stream (live mode)."),
    interval: float = typer.Option(2.0, help="Seconds between heart-rate posts."),
    backfill: int = typer.Option(
        0, help="Instead of streaming, post this many minutes of history and exit."
    ),
    resting: float = typer.Option(72.0, help="Resting heart rate (bpm)."),
) -> None:
    """Stream fake Apple Watch vitals to a running `attune serve` — test the whole loop
    (server → store → dashboard) without the Watch built yet (ADR-023)."""
    import httpx

    from attune.simulate import WatchSimulator

    sim = WatchSimulator(resting_bpm=resting)
    base = url.rstrip("/")

    def post(samples: list) -> None:
        httpx.post(
            f"{base}/ingest/vitals",
            json=[s.model_dump(mode="json") for s in samples],
            timeout=10.0,
        )

    if backfill > 0:
        samples = sim.backfill(now_ms(), minutes=backfill)
        post(samples)
        typer.secho(f"  Backfilled {len(samples)} samples over {backfill} min → {base}", fg="green")
        return

    end = time.time() + minutes * 60
    mid = time.time() + minutes * 60 * 0.5  # one elevation around the midpoint
    typer.secho(
        f"  Streaming fake Watch vitals → {base}/ingest/vitals for {minutes:g} min "
        f"(Ctrl-C to stop)…\n",
        fg="green",
    )
    try:
        while time.time() < end:
            elevated = mid <= time.time() <= mid + 40
            samples = sim.tick(now_ms(), elevated=elevated)
            try:
                post(samples)
                hr = next(s.value for s in samples if s.type.value == "heart_rate")
                tag = "  ← elevated" if elevated else ""
                typer.echo(f"  {datetime.now().strftime('%H:%M:%S')}  {hr:5.0f} bpm{tag}")
            except Exception as e:  # noqa: BLE001 — surface any transport error and keep going
                typer.secho(f"  post failed ({e}); is `attune serve` running?", fg="red")
            time.sleep(interval)
    except KeyboardInterrupt:
        typer.echo("\n  stopped.")


@app.command()
def doctor(
    port: int | None = typer.Option(None, help="Server port to probe (default from config)."),
) -> None:
    """Readiness check for testing on your Apple Watch — prints what's done and what's left."""
    import httpx

    from attune.netutil import lan_ip

    s = get_settings()
    probe_port = port or s.api_port
    ok, warn, info = (
        typer.style("✓", fg="green"),
        typer.style("!", fg="yellow"),
        typer.style("·", fg="bright_black"),
    )
    typer.secho("\n  Apple Watch readiness\n", bold=True)

    # 1. LAN IP for the phone/Watch to reach this machine.
    ip = lan_ip()
    if ip:
        typer.echo(f"  {ok} LAN address detected: {ip}")
        typer.secho(
            f"      → set the companion app's backend URL to  http://{ip}:{probe_port}",
            fg="bright_black",
        )
    else:
        typer.echo(
            f"  {warn} No LAN IP found — connect to Wi-Fi so the Watch can reach this machine."
        )

    # 2. Vitals source should be 'api' to receive pushes from the app.
    if s.vitals_source == "api":
        typer.echo(f"  {ok} vitals_source = api (ready to receive Watch/app pushes)")
    else:
        typer.echo(
            f"  {warn} vitals_source = {s.vitals_source} — set ATTUNE_VITALS_SOURCE=api to take "
            "live Watch data."
        )

    # 3. Is a server already up?
    try:
        r = httpx.get(f"http://127.0.0.1:{probe_port}/health", timeout=1.5)
        health = r.json()
        typer.echo(f"  {ok} server reachable on :{probe_port} (vertical={health.get('vertical')})")
    except Exception:  # noqa: BLE001
        typer.echo(
            f"  {info} no server on :{probe_port} yet — start one with  attune serve --lan"
        )

    # 4. Bee proxy, only relevant for real conversations.
    if s.conversation_source == "bee":
        try:
            httpx.get(f"{s.bee_proxy_url}/v1/me", timeout=1.5)
            typer.echo(f"  {ok} Bee proxy reachable at {s.bee_proxy_url}")
        except Exception:  # noqa: BLE001
            typer.echo(
                f"  {warn} Bee proxy not reachable — run  bee login && bee proxy  "
                f"(or set ATTUNE_CONVERSATION_SOURCE=synthetic to demo without it)"
            )
    else:
        typer.echo(
            f"  {info} conversation_source = {s.conversation_source} (Bee proxy not required)"
        )

    typer.secho("\n  Next steps", bold=True)
    typer.echo("    1. attune serve --lan            # start server, note the LAN URL")
    typer.echo("    2. attune simulate-watch         # try the loop now, no Watch needed")
    typer.echo(f"    3. open http://127.0.0.1:{probe_port}/      # watch the dashboard update")
    typer.echo("    4. build companion/ in Xcode, set the LAN URL, stream from the real Watch\n")


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
