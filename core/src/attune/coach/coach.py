"""The coach (ADR-014/017): turns ranked moments into hedged recommendations.

Three interchangeable backends behind one ``Coach`` protocol, selected by config:

- :class:`TemplateCoach` — deterministic, offline, **zero cost** (the default).
- :class:`OllamaCoach` — a local LLM via Ollama, **free** (runs on the user's machine).
- :class:`AnthropicCoach` — Claude via the Anthropic API, **paid** (opt-in only).

Every backend's output passes through ``scrub()`` (ADR-011) before it is returned, so the
ethical guardrails hold regardless of which engine produced the text. A backend may emit
*fewer* recommendations than moments: non-compliant ones are dropped.
"""

from __future__ import annotations

import json
import re
from typing import Protocol

from attune.coach.guardrails import GUARDRAILS, scrub
from attune.config import Settings
from attune.models import Moment, Recommendation

# ──────────────────────────────────────────────────────────────────────────────
# Shared prompt scaffolding for the two LLM backends
# ──────────────────────────────────────────────────────────────────────────────
_TASK = """\
You will receive a JSON array of "moments" from a private self-coaching session. Each moment
has: the person's own words, detector signals (hesitation, self-correction, stated uncertainty,
a repeated topic), and — where available — baseline-relative vitals context.

For each moment worth acting on, write ONE recommendation: a single-sentence observation
grounded in the person's OWN words or a recurring topic, optionally noting any vitals change
strictly relative to their own baseline, followed by ONE concrete, optional suggestion.

Respond with ONLY a JSON array (no prose, no code fences). Each element:
{"moment_ts_ms": <int, copied from the moment>, "title": "<=6 words", "body": "<=2 sentences",
 "basis": ["<the signal/evidence you used>", ...]}
"""

_SYSTEM = GUARDRAILS + "\n\n" + _TASK


def _moments_payload(moments: list[Moment]) -> list[dict]:
    """Serialize moments into the compact JSON the LLM backends consume."""
    payload = []
    for m in moments:
        payload.append(
            {
                "moment_ts_ms": m.ts_ms,
                "speaker": m.utterance.speaker or "me",
                "said": m.utterance.text,
                "signals": [
                    {"kind": s.kind, "evidence": s.evidence, "weight": round(s.weight, 2)}
                    for s in m.signals
                ],
                "vitals": {
                    vt.value: {
                        "direction": d.direction,
                        "value": d.value,
                        "baseline": d.baseline,
                        "z": d.z,
                    }
                    for vt, d in m.vitals_context.items()
                },
            }
        )
    return payload


def _parse_recommendations(text: str, generated_by: str) -> list[Recommendation]:
    """Parse an LLM's JSON-array reply into guardrail-compliant Recommendations."""
    text = text.strip()
    # Tolerate accidental code fences.
    fence = re.search(r"\[.*\]", text, re.DOTALL)
    if fence:
        text = fence.group(0)
    try:
        items = json.loads(text)
    except json.JSONDecodeError:
        return []
    out: list[Recommendation] = []
    for it in items if isinstance(items, list) else []:
        body = scrub(str(it.get("body", "")))
        if not body:
            continue  # dropped by guardrails
        out.append(
            Recommendation(
                moment_ts_ms=int(it.get("moment_ts_ms", 0)),
                title=str(it.get("title", "")).strip() or "Worth revisiting",
                body=body,
                basis=[str(b) for b in it.get("basis", []) if b],
                generated_by=generated_by,  # type: ignore[arg-type]
            )
        )
    return out


class Coach(Protocol):
    """Anything that turns ranked moments into recommendations."""

    def generate(self, moments: list[Moment]) -> list[Recommendation]: ...


# ──────────────────────────────────────────────────────────────────────────────
# Free, deterministic backend (default)
# ──────────────────────────────────────────────────────────────────────────────
class TemplateCoach:
    """Zero-cost, offline coach built from the detector signals.

    Phrasing is written to be guardrail-compliant by construction; ``scrub()`` is still run
    as a final safety net.
    """

    _STOP = {"the", "a", "an", "to", "of", "and", "that", "this", "would", "could", "how"}
    _word = re.compile(r"[a-zA-Z][a-zA-Z\-]{3,}")

    def generate(self, moments: list[Moment]) -> list[Recommendation]:
        recs: list[Recommendation] = []
        for m in moments:
            rec = self._for_moment(m)
            if rec is not None:
                recs.append(rec)
        return recs

    def _topic(self, m: Moment) -> str:
        for s in m.signals:
            if s.kind == "repeated_topic" and ":" in s.evidence:
                return s.evidence.split(":", 1)[1].split(",")[0].strip()
        words = [w for w in self._word.findall(m.utterance.text) if w.lower() not in self._STOP]
        return max(words, key=len).lower() if words else "this topic"

    def _for_moment(self, m: Moment) -> Recommendation | None:
        kinds = {s.kind for s in m.signals}
        if not kinds:
            return None
        topic = self._topic(m)

        if "uncertainty" in kinds:
            observation = f"You flagged {topic} as something you wanted to clarify."
            suggestion = f"Want a short review of {topic}, then re-explain it in your own words?"
        elif "self_correction" in kinds:
            observation = f"You revised your answer while working through {topic}."
            suggestion = f"Want to rehearse {topic} once more and see if it comes out cleaner?"
        elif "repeated_topic" in kinds:
            observation = f"{topic.capitalize()} came up several times in this session."
            suggestion = f"Consider making {topic} the focus of your next review block."
        elif "hesitation" in kinds:
            observation = f"You paused while talking through {topic}."
            suggestion = f"Want to practice explaining {topic} end to end?"
        else:  # vitals_delta only
            observation = f"A physiological change co-occurred while discussing {topic}."
            suggestion = f"Want to revisit {topic} when you have a calm moment and compare?"

        # Baseline-relative vitals note (never a feeling; ETHICS rules 1–3).
        vitals_note = ""
        for s in m.signals:
            if s.kind == "vitals_delta":
                vitals_note = (
                    f" Around that time, {s.evidence}; that alone doesn't establish how you felt."
                )
                break

        body = scrub(observation + vitals_note + " " + suggestion)
        if not body:
            return None
        return Recommendation(
            moment_ts_ms=m.ts_ms,
            title=self._title(kinds, topic),
            body=body,
            basis=[s.evidence for s in m.signals if s.evidence],
            generated_by="template",
        )

    @staticmethod
    def _title(kinds: set[str], topic: str) -> str:
        if "uncertainty" in kinds:
            return f"Clarify {topic}"
        if "self_correction" in kinds:
            return f"Rehearse {topic}"
        if "repeated_topic" in kinds:
            return f"Review {topic}"
        return f"Revisit {topic}"


# ──────────────────────────────────────────────────────────────────────────────
# Free, local LLM backend (opt-in)
# ──────────────────────────────────────────────────────────────────────────────
class OllamaCoach:
    """Local LLM via Ollama's HTTP API — free, runs on the user's machine.

    Falls back to :class:`TemplateCoach` if Ollama is unreachable, so a run never fails just
    because the local server isn't up.
    """

    def __init__(self, url: str, model: str, max_moments: int):
        self.url = url.rstrip("/")
        self.model = model
        self.max_moments = max_moments

    def generate(self, moments: list[Moment]) -> list[Recommendation]:
        import httpx

        payload = _moments_payload(moments[: self.max_moments])
        try:
            resp = httpx.post(
                f"{self.url}/api/chat",
                timeout=60.0,
                json={
                    "model": self.model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": _SYSTEM},
                        {"role": "user", "content": json.dumps(payload)},
                    ],
                },
            )
            resp.raise_for_status()
            text = resp.json().get("message", {}).get("content", "")
        except Exception:
            return TemplateCoach().generate(moments[: self.max_moments])
        recs = _parse_recommendations(text, generated_by="ollama")
        return recs or TemplateCoach().generate(moments[: self.max_moments])


# ──────────────────────────────────────────────────────────────────────────────
# Paid Claude backend (opt-in only)
# ──────────────────────────────────────────────────────────────────────────────
class AnthropicCoach:
    """Claude via the Anthropic API. PAID per token — only constructed when the user sets
    ``coach_backend="anthropic"``."""

    def __init__(self, api_key: str | None, model: str, max_moments: int):
        self.model = model
        self.max_moments = max_moments
        self._api_key = api_key

    def generate(self, moments: list[Moment]) -> list[Recommendation]:
        import anthropic

        client = (
            anthropic.Anthropic(api_key=self._api_key) if self._api_key else anthropic.Anthropic()
        )
        payload = _moments_payload(moments[: self.max_moments])
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=2048,
                output_config={"effort": "low"},  # simple generation; keep it cheap/fast
                system=_SYSTEM,
                messages=[{"role": "user", "content": json.dumps(payload)}],
            )
        except anthropic.APIError:
            return TemplateCoach().generate(moments[: self.max_moments])
        if response.stop_reason == "refusal":
            return []
        text = "".join(b.text for b in response.content if b.type == "text")
        recs = _parse_recommendations(text, generated_by="claude")
        return recs or TemplateCoach().generate(moments[: self.max_moments])


def build_coach(settings: Settings) -> Coach:
    """Instantiate the configured coach. Default (``template``) never costs money (ADR-017)."""
    if settings.coach_backend == "anthropic":
        return AnthropicCoach(
            settings.anthropic_api_key, settings.coach_model, settings.coach_max_moments
        )
    if settings.coach_backend == "ollama":
        return OllamaCoach(settings.ollama_url, settings.ollama_model, settings.coach_max_moments)
    return TemplateCoach()
