"""12-factor configuration (ADR-012).

All runtime behavior — which sources are active, where Bee/Health data lives, which
model to use — is driven by environment variables (optionally via a ``.env`` file).
Nothing is hard-coded, and the defaults run the full pipeline on synthetic data.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ConversationSourceName = Literal["synthetic", "replay", "bee"]
VitalsSourceName = Literal["synthetic", "health_export", "api"]
# Coach backends (ADR-014/017):
#   template  — deterministic, no network, ZERO cost (the default)
#   ollama    — a local LLM via Ollama, free (runs on your machine)
#   anthropic — Claude via the Anthropic API, PAID per token (opt-in only)
CoachBackend = Literal["template", "ollama", "anthropic"]
ProductVertical = Literal["generic", "neurolearn"]


class Settings(BaseSettings):
    """Process-wide settings. Prefix every env var with ``ATTUNE_`` (except standard keys)."""

    model_config = SettingsConfigDict(
        env_prefix="ATTUNE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Source selection (ADR-010)
    conversation_source: ConversationSourceName = "synthetic"
    vitals_source: VitalsSourceName = "synthetic"

    # Vertical selection (ADR-022). NeuroLearn is the chosen demo vertical; "generic"
    # keeps the reusable Attune base layer available for future concepts.
    vertical: ProductVertical = "neurolearn"

    # Bee local proxy (ADR-003)
    bee_proxy_url: str = "http://127.0.0.1:8787"

    # Apple Health export (ADR-006)
    health_export_path: str = "./fixtures/health_export_sample.xml"

    # Storage (ADR-013)
    db_path: str = "./attune.db"

    # Alignment (ADR-008/011)
    align_window_s: int = 45
    baseline_window_s: int = 600

    # Coach (ADR-014/017). Default is the FREE template backend — nothing calls a paid
    # API unless you set coach_backend="anthropic" yourself.
    coach_backend: CoachBackend = "template"
    coach_max_moments: int = 8

    # Paid Anthropic path (only used when coach_backend="anthropic"). The key is read
    # without the ATTUNE_ prefix. Defaults to Opus (most capable) per Anthropic guidance;
    # switch to claude-sonnet-5-5 / claude-haiku-5-5 to lower cost.
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    coach_model: str = "claude-opus-5-5"

    # Free local-LLM path (only used when coach_backend="ollama"). Install from ollama.com,
    # then `ollama pull llama3.2`. Runs entirely on your machine at no cost.
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2"

    # API service (ADR-009)
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    @property
    def align_window_ms(self) -> int:
        return self.align_window_s * 1000

    @property
    def baseline_window_ms(self) -> int:
        return self.baseline_window_s * 1000

    @property
    def coach_is_paid(self) -> bool:
        """True only for the Anthropic backend — the one path that can incur cost."""
        return self.coach_backend == "anthropic"


@lru_cache
def get_settings() -> Settings:
    """Cached singleton. Call ``get_settings.cache_clear()`` in tests to reload."""
    return Settings()
