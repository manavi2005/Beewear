"""The coaching layer (ADR-014): turns notable moments into hedged, personalized,
guardrail-compliant recommendations."""

from attune.coach.coach import Coach, TemplateCoach, build_coach
from attune.coach.guardrails import GUARDRAILS, is_compliant, scrub

__all__ = ["Coach", "TemplateCoach", "build_coach", "GUARDRAILS", "is_compliant", "scrub"]
