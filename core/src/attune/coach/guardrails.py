"""Enforced ethical guardrails (ADR-011, see docs/ETHICS.md).

Two layers of enforcement:
1. ``GUARDRAILS`` — injected verbatim into the coach's system prompt.
2. ``scrub()`` / ``is_compliant()`` — a post-hoc check on generated text. Even a careful
   prompt can drift, so no recommendation reaches a caller without passing this.

If a recommendation cannot be made compliant, the pipeline drops it rather than show it —
which is why the coach may emit fewer recommendations than there are moments.
"""

from __future__ import annotations

import re

GUARDRAILS = """\
You are a PRIVATE self-coaching assistant. The person is coaching themselves — you are never
an employer's, teacher's, or third party's evaluation of them.

Hard rules (these are correctness constraints, not style preferences):
1. NEVER claim or imply an emotional or cognitive state (anxious, nervous, stressed,
   confused, overwhelmed, panicking). You may quote the person's OWN words if they said it.
2. NEVER map a physiological value to a feeling. An elevated heart rate does NOT mean nervous
   or confused. Describe physiology ONLY relative to the person's own baseline
   (e.g. "elevated vs. your earlier readings"), and say explicitly that this alone does not
   establish how they felt.
3. Co-occurrence is not causation. If a vitals change and a conversation moment happened at
   the same time, say they co-occurred — do not say one caused the other.
4. No medical or diagnostic language. You are not detecting anxiety, panic, or illness.
5. Give suggestions as options/questions ("Want to…?"), never health directives.
6. Be brief, concrete, and kind. One observation + one actionable suggestion per moment.
"""

# Phrases that must never appear as assertions about the person's state.
# ``[^.?!]{0,30}?`` allows intervening words ("you were *clearly* anxious") without crossing
# a sentence boundary.
_EMOTION = (
    r"(?:anxious|nervous|stressed|stress|confused|overwhelmed|panick(?:ed|ing)|scared|afraid|upset)"
)
_BANNED = re.compile(
    rf"\byou\s+(?:were|are|was|seem|seemed|felt|feel|look|looked|get|got|became?)\b[^.?!]{{0,30}}?\b{_EMOTION}\b"
    rf"|\byour\s+(?:heart[\s_]?rate|hrv|vitals?|body|pulse)\b[^.?!]{{0,40}}?\b"
    rf"(?:means?|shows?|showed|proves?|indicates?|because)\b[^.?!]{{0,30}}?\b{_EMOTION}\b"
    r"|\b(?:diagnos(?:e|ed|is)|panic attack|anxiety disorder)\b",
    re.IGNORECASE,
)

# Soft causal claims we rewrite to co-occurrence language.
_CAUSAL = re.compile(r"\b(because your (heart rate|hrv|vitals?))\b", re.IGNORECASE)


def is_compliant(text: str) -> bool:
    """True if ``text`` contains no banned emotional/diagnostic assertions."""
    return _BANNED.search(text) is None


def scrub(text: str) -> str | None:
    """Return a compliant version of ``text``, or ``None`` if it can't be salvaged.

    - Rewrites obvious causal phrasing to co-occurrence.
    - Rejects (returns ``None``) anything still asserting an emotional/diagnostic state.
    """
    cleaned = _CAUSAL.sub("around the time your $1 was elevated,", text)
    if not is_compliant(cleaned):
        return None
    return cleaned
