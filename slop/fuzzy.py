"""Fuzzy primitives shared by every slop detector.

Perceptual color math instead of hex whitelists: a color is neutral because
its saturation is low, purple because its hue sits in the violet band with
real saturation. String matching is word-boundary fuzzy so "Inter, system-ui"
matches Inter but "Interstate" does not.
"""

from __future__ import annotations

import colorsys
import re
from typing import Iterable


# ── Color parsing ────────────────────────────────────────────────────────────

_HEX3 = re.compile(r'^#([0-9a-fA-F])([0-9a-fA-F])([0-9a-fA-F])$')
_HEX6 = re.compile(r'^#([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})$')
_RGB = re.compile(r'^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)')
_HSL = re.compile(r'^hsla?\(\s*([\d.]+)(?:deg)?[\s,]+([\d.]+)%?[\s,]+([\d.]+)%?')


def parse_color(value: str) -> tuple[float, float, float] | None:
    """Parse any CSS color string into (h, s, l) with h in degrees, s/l 0..1.

    Returns None for anything unrecognized (named colors beyond the basics,
    gradients, currentColor, none, inherit). Callers treat None as "unknown"
    and must not flag on it.
    """
    v = value.strip().lower()
    if not v or v in ('inherit', 'initial', 'unset', 'currentcolor', 'transparent', 'none'):
        return None
    m = _HEX6.match(v)
    if m:
        r, g, b = (int(c, 16) / 255 for c in m.groups())
        return rgb_to_hsl(r, g, b)
    m = _HEX3.match(v)
    if m:
        r, g, b = (int(c, 16) / 255 for c in m.groups())
        return rgb_to_hsl(r, g, b)
    m = _RGB.match(v)
    if m:
        r, g, b = (int(float(c)) / 255 for c in m.groups())
        return rgb_to_hsl(r, g, b)
    m = _HSL.match(v)
    if m:
        h = float(m.group(1)) % 360
        s = float(m.group(2)) / 100
        l = float(m.group(3)) / 100
        return (h, s, l)
    named = {'white': (0, 0, 1), 'black': (0, 0, 0)}
    if v in named:
        return named[v]
    return None


def rgb_to_hsl(r: float, g: float, b: float) -> tuple[float, float, float]:
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return (h * 360, s, l)


# ── Fuzzy color predicates ──────────────────────────────────────────────────

def is_neutral(hsl: tuple[float, float, float] | None) -> bool:
    """Grey/paper family: low saturation, whatever the hue or hex."""
    return hsl is not None and hsl[1] < 0.12


def is_purple(hsl: tuple[float, float, float] | None) -> bool:
    """Vibe purple: violet-to-indigo hue band with real saturation.

    Saturation floor is deliberately low (0.25): the muted violets
    (#5a4a8a-family) are the same tell as the loud ones — damping the
    chroma does not make a card border structural.
    """
    return (hsl is not None and 235 <= hsl[0] <= 295
            and hsl[1] >= 0.25 and 0.15 <= hsl[2] <= 0.85)


def color_confidence(hsl: tuple[float, float, float],
                      neutral: bool) -> float:
    """Confidence that a color reads as 'colored' rather than neutral ink.

    Scales with saturation above the neutral band so a barely-tinted edge
    stays a REVIEW candidate while a saturated stripe is a FINDING.
    """
    if neutral:
        return 0.0
    s = hsl[1]
    if s < 0.15:
        return 0.35   # faint tint — review territory
    if s < 0.25:
        return 0.6
    return 0.9


# ── Fuzzy string matching ────────────────────────────────────────────────────

def fuzzy_member(haystack: str, needles: Iterable[str]) -> str | None:
    """Return the needle if it appears in haystack at word boundaries.

    "Inter, system-ui" contains Inter; "Interstate" does not.
    """
    for needle in needles:
        if re.search(r'(?<![\w-])' + re.escape(needle) + r'(?![\w-])',
                     haystack, re.IGNORECASE):
            return needle
    return None


# ── Tolerant sequence detection ─────────────────────────────────────────────

_STEP = re.compile(
    r'(?:^(?:step|phase|schritt)\s*[:\s-]?\s*([0-9]{1,2})\b)'
    r'|(?:^|[^0-9])([0-9]{1,2})\s*[.·:)]\s*(?=[A-ZÄÖÜ0-9])',
    re.IGNORECASE)


def _leading_number(text: str) -> int | None:
    m = _STEP.search(text.strip()[:16])
    if not m:
        return None
    return int(m.group(1) or m.group(2))


def sequence_run(texts: list[str]) -> int:
    """Longest run of strictly incrementing numbers across numbered texts.

    Catches "1 · 2 · 3", "Step 0 … Step 1 … Step 2", "Phase 1 … Phase 2"
    style numbered decorations. Non-numbered texts between numbered ones are
    tolerated (real process steps carry content between their numbers) —
    only the ORDER of the extracted numbers matters.
    """
    nums = [n for n in (_leading_number(t) for t in texts) if n is not None]
    best = 0
    run = 0
    prev = None
    for n in nums:
        if prev is not None and n == prev + 1:
            run += 1
            best = max(best, run)
        else:
            run = 1
        prev = n
    return best
