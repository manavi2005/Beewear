"""Source adapters: translate external data into the canonical model (ADR-007).

Every source has a live implementation and a replay/synthetic twin (ADR-010), selected by
config (ADR-012). Use the factory helpers below rather than importing concrete classes.
"""

from __future__ import annotations

from attune.config import Settings
from attune.sources.base import ConversationSource, VitalsSource


def build_conversation_source(settings: Settings) -> ConversationSource:
    """Instantiate the configured conversation source."""
    name = settings.conversation_source
    if name == "synthetic":
        from attune.sources.synthetic import SyntheticConversationSource

        return SyntheticConversationSource()
    if name == "replay":
        from attune.sources.bee_replay import BeeReplaySource

        return BeeReplaySource()
    if name == "bee":
        from attune.sources.bee import BeeProxySource

        return BeeProxySource(settings.bee_proxy_url)
    raise ValueError(f"Unknown conversation source: {name!r}")


def build_vitals_source(settings: Settings) -> VitalsSource:
    """Instantiate the configured vitals source.

    Note: ``api`` means "vitals are pushed in by the companion app via POST /ingest/vitals"
    (ADR-009) — there is no pull-based source object, so the pipeline reads them from the
    store instead. We return a Synthetic source's *empty* sibling for that case.
    """
    name = settings.vitals_source
    if name == "synthetic":
        from attune.sources.synthetic import SyntheticVitalsSource

        return SyntheticVitalsSource()
    if name == "health_export":
        from attune.sources.health_export import HealthExportSource

        return HealthExportSource(settings.health_export_path)
    if name == "api":
        from attune.sources.base import EmptyVitalsSource

        return EmptyVitalsSource()
    raise ValueError(f"Unknown vitals source: {name!r}")


__all__ = [
    "ConversationSource",
    "VitalsSource",
    "build_conversation_source",
    "build_vitals_source",
]
