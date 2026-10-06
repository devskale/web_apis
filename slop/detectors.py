"""Detector base contract + registry.

One file per tell in detectors/ — drop-in discovery, no central register to
maintain (Krebs' template bar: deterministic, common, precise, visible).
Declarative fuzzy rules live in rules/*.yaml and compile into detectors at
load time; both tiers build on fuzzy.py primitives.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .fuzzy import (color_confidence, fuzzy_member, is_neutral,
                    is_purple, parse_color, sequence_run)
from .page_model import PageModel

# Connector neutrals: custom props that are structural lines, not decoration.
CONNECTOR_PROPS = re.compile(r'--(line|muted|soft|ink)')


@dataclass
class Finding:
    id: str
    weight: int
    confidence: float
    evidence: str
    selector: str
    fix: str
    level: str = 'info'   # 'hard' = card-accent family (gates the share)

    def band(self) -> str:
        from . import FIND, REVIEW
        if self.confidence >= FIND:
            return 'finding'
        if self.confidence >= REVIEW:
            return 'review'
        return 'silent'


class Detector:
    id: str = ''
    weight: int = 4
    # 'hard': decorative color on containers (stripes, capsules, fills) —
    # gates the share. 'info': reported, never gates.
    level: str = 'info'

    def detect(self, page: PageModel) -> list[Finding]:
        raise NotImplementedError


# ── Structural detectors (Tier 1) ───────────────────────────────────────────

class EdgeStripe(Detector):
    """One-sided colored border on a card — any of the four edges.

    The auditflow finding: border-top:4px solid var(--cat-a) was invisible to
    a border-left-only regex. Width scales confidence: >=3px saturated is a
    FINDING, 2px is REVIEW, thin or neutral passes (timeline spines).
    """
    id = 'edge_stripe'
    weight = 6
    level = 'hard'

    def detect(self, page):
        out = []
        for rule in page.rules:
            for side in ('left', 'top', 'right', 'bottom'):
                b = page.border_of(rule.decls, side)
                if not b:
                    continue
                w, color = b
                if w < 2:
                    continue
                raw = color
                if raw.startswith('var('):
                    m = re.search(r'--[a-z0-9-]+', raw)
                    if m and CONNECTOR_PROPS.match(m.group(0)):
                        continue  # structural connector, passes
                resolved = page.resolve_color(color)
                hsl = parse_color(resolved)
                if hsl is None:
                    continue  # unknown color — never flag
                if is_neutral(hsl):
                    continue
                conf = color_confidence(hsl, False)
                if w >= 3:
                    conf = max(conf, 0.85)
                if w < 3:
                    conf = min(conf, 0.65)
                out.append(Finding(
                    self.id, self.weight, conf,
                    f'border-{side}:{w:g}px solid {resolved} on "{rule.selector[:40]}"',
                    rule.selector[:60],
                    'put the hue on content (label/dot/value), not on the card edge',
                    self.level))
        return out


class Pill(Detector):
    """Pastel pill capsule: border-radius 999px + colored background.

    Info-level, not a gate: pills are a taste call (Johann 2026-10:
    "pills sind ok") — reported, never blocks a share.
    """
    id = 'pill'
    weight = 5
    level = 'info'

    def detect(self, page):
        out = []
        for rule in page.rules:
            if not re.search(r'border-radius\s*:\s*99[0-9]px', rule.decls):
                continue
            m = re.search(r'background(?:-color)?\s*:\s*([^;]+)', rule.decls)
            if not m:
                continue
            resolved = page.resolve_color(m.group(1).strip())
            hsl = parse_color(resolved)
            if hsl is None or is_neutral(hsl):
                continue
            out.append(Finding(
                self.id, self.weight, color_confidence(hsl, False),
                f'pill capsule (border-radius:999px + {resolved}) on "{rule.selector[:40]}"',
                rule.selector[:60],
                'use a small square dot + severity text instead of a tinted capsule',
                self.level))
        return out


class CircleBadge(Detector):
    """Large colored circle badge (>=20px); small category dots pass."""
    id = 'circle_badge'
    weight = 4
    level = 'hard'

    def detect(self, page):
        out = []
        for rule in page.rules:
            if not re.search(r'border-radius\s*:\s*50%', rule.decls):
                continue
            m = re.search(r'background(?:-color)?\s*:\s*([^;]+)', rule.decls)
            if not m:
                continue
            resolved = page.resolve_color(m.group(1).strip())
            hsl = parse_color(resolved)
            if hsl is None or is_neutral(hsl):
                continue
            sizes = [float(x) * (16 if u == 'rem' else 1)
                     for x, u in re.findall(
                         r'(?:width|height)\s*:\s*([\d.]+)(px|rem)', rule.decls)]
            if sizes and max(sizes) >= 20:
                out.append(Finding(
                    self.id, self.weight, 0.8,
                    f'circle badge ({max(sizes):g}px, {resolved}) on "{rule.selector[:40]}"',
                    rule.selector[:60],
                    'use a square swatch or text label instead of a big colored circle',
                    self.level))
        return out


class PurpleCta(Detector):
    """Vibe purple: filled indigo/violet backgrounds (CTAs, hero chips)."""
    id = 'purple_cta'
    weight = 8
    level = 'hard'

    def detect(self, page):
        out = []
        for rule in page.rules:
            m = re.search(r'background(?:-color)?\s*:\s*([^;]+)', rule.decls)
            if not m:
                continue
            resolved = page.resolve_color(m.group(1).strip())
            hsl = parse_color(resolved)
            if hsl is None or not is_purple(hsl):
                continue
            # Small filled elements are category dots/swatches — structural
            # color per house style, not CTAs. Stay silent on them.
            size = page.rule_size(rule)
            if size is not None and size <= 14:
                continue
            out.append(Finding(
                self.id, self.weight, 0.85,
                f'vibe purple fill ({resolved}) on "{rule.selector[:40]}"',
                rule.selector[:60],
                'violet/indigo fills read as AI default — use a neutral fill or put hue on text',
                self.level))
        return out


class GradientText(Detector):
    """background-clip:text + gradient on headings."""
    id = 'gradient_text'
    weight = 6

    def detect(self, page):
        for rule in page.rules:
            if (re.search(r'background-clip\s*:\s*text', rule.decls)
                    and re.search(r'gradient\(', rule.decls)):
                return [Finding(
                    self.id, self.weight, 0.9,
                    f'gradient text on "{rule.selector[:40]}"',
                    rule.selector[:60],
                    'solid ink for headings; gradients on type read as AI default')]
        return []


class Glass(Detector):
    """Glassmorphism: backdrop-filter blur on translucent layers."""
    id = 'glass'
    weight = 4

    def detect(self, page):
        for rule in page.rules:
            if (re.search(r'backdrop-filter\s*:[^;]*blur\(', rule.decls)
                    or re.search(r'-webkit-backdrop-filter\s*:[^;]*blur\(',
                                 rule.decls)):
                return [Finding(
                    self.id, self.weight, 0.8,
                    f'glassmorphism (backdrop-filter blur) on "{rule.selector[:40]}"',
                    rule.selector[:60],
                    'frosted-glass panels are an AI default — use a solid surface')]
        return []


class Glow(Detector):
    """Big colored box-shadow glow (>=24px blur, saturated hue)."""
    id = 'glow'
    weight = 4

    def detect(self, page):
        for rule in page.rules:
            for m in re.finditer(r'box-shadow\s*:\s*([^;]+)', rule.decls):
                sh = m.group(1)
                for lm in re.finditer(r'rgba?\([^)]+\)|#[0-9a-fA-F]{6}', sh):
                    hsl = parse_color(lm.group(0))
                    if hsl is None or is_neutral(hsl):
                        continue
                    blur = re.findall(r'(\d+)px', sh)
                    if blur and max(int(b) for b in blur) >= 24:
                        return [Finding(
                            self.id, self.weight, 0.75,
                            f'colored glow (box-shadow, {lm.group(0)}) on "{rule.selector[:40]}"',
                            rule.selector[:60],
                            'drop the glow — elevation via shadow should be neutral')]
        return []


class SlopFonts(Detector):
    """AI-default font stacks: Inter / Geist / Space Grotesk / Instrument Serif."""
    id = 'slop_fonts'
    weight = 8
    NEEDLES = ('Inter', 'Geist', 'Space Grotesk', 'Instrument Serif')

    def detect(self, page):
        for rule in page.rules:
            m = re.search(r'font-family\s*:\s*([^;]+)', rule.decls)
            if not m:
                continue
            hit = fuzzy_member(m.group(1), self.NEEDLES)
            if hit:
                return [Finding(
                    self.id, self.weight, 0.7,
                    f'AI-default font "{hit}" on "{rule.selector[:40]}"',
                    rule.selector[:60],
                    'use the system font stack or a deliberate typeface choice')]
        return []


class AllCaps(Detector):
    """All-caps labels. A few kickers are fine; a wall of them is autopilot.

    Count-scaled confidence: <=5 passes (structural kickers), 6-10 REVIEW,
    >10 is a FINDING.
    """
    id = 'all_caps'
    weight = 3

    def detect(self, page):
        n = sum(1 for r in page.rules
                if re.search(r'text-transform\s*:\s*uppercase', r.decls))
        if n <= 5:
            return []
        conf = 0.5 if n <= 10 else 0.75
        return [Finding(
            self.id, self.weight, conf,
            f'{n} text-transform:uppercase rules — all-caps autopilot',
            ':root',
            'keep all-caps for 2-3 kickers max; use weight/size for the rest')]


class StatBanner(Detector):
    """Big-number stat rows: "10k+", "99.9%", "$2M+" style claims."""
    id = 'stat_banner'
    weight = 3
    _STAT = re.compile(
        r'\b\d+(?:[.,]\d+)?\s*(?:k\+?|M\+?|Mr[d.]?\+?|%|Millionen|Mrd)')

    def detect(self, page):
        hits = self._STAT.findall(page.text)
        if len(hits) < 3:
            return []
        return [Finding(
            self.id, self.weight, 0.7,
            f'stat-banner pattern: {len(hits)} big-number claims ({", ".join(hits[:3])}…)',
            'body',
            'stat walls read as AI landingpage — cite sources or cut to one number')]


class NumberedSteps(Detector):
    """Decorative "1 · 2 · 3" step sequences.

    On documentation pages numbering can be a real process — this detector
    deliberately stays at REVIEW confidence and hands the decision back.
    """
    id = 'numbered_steps'
    weight = 3

    def detect(self, page):
        run = sequence_run(page.element_texts)
        if run < 3:
            return []
        return [Finding(
            self.id, self.weight, 0.5,
            f'numbered step sequence (run of {run}) — process or decoration?',
            'body',
            'if the numbers carry real process meaning, keep them; if they are '
            'landingpage decoration, flatten to plain headings')]


class TailwindPill(Detector):
    """Tailwind pill classes: rounded-full + tinted bg utility in one class attr."""
    id = 'pill'
    weight = 5
    _TINTED = re.compile(
        r'\bbg-(?:emerald|amber|red|rose|blue|sky|indigo|violet|purple|'
        r'fuchsia|pink|cyan|teal|lime|green|orange|yellow)-\d{2,3}\b')

    def detect(self, page):
        # Scans class tokens, not rules — needs the raw class list.
        return []  # handled by scan_classes below


# ── Registry ────────────────────────────────────────────────────────────────

_STRUCTURAL: list[Detector] = [
    EdgeStripe(), Pill(), CircleBadge(), PurpleCta(), GradientText(),
    Glass(), Glow(), SlopFonts(), AllCaps(), StatBanner(), NumberedSteps(),
]


def run_all(page: PageModel) -> list[Finding]:
    findings: list[Finding] = []
    for det in _STRUCTURAL:
        findings.extend(det.detect(page))
    # Tailwind pill check on class tokens (shares id/weight with Pill).
    tinted = [c for c in page.classes if c.startswith('rounded-full')]
    if tinted:
        joined = ' '.join(page.classes)
        m = TailwindPill._TINTED.search(joined)
        if m:
            findings.append(Finding(
                'pill', 5, 0.75,
                f'Tailwind pill classes (rounded-full + {m.group(0)})',
                'class',
                'use a small square dot + severity text instead of a tinted capsule',
                'info'))
    return findings


def score(findings: list[Finding]) -> dict[str, Any]:
    """Weighted confidence sum -> score + tier (slop-detect-compatible)."""
    total = sum(f.weight * f.confidence
                for f in findings if f.band() != 'silent')
    if total >= 30:
        tier = 'Heavy'
    elif total >= 10:
        tier = 'Mild'
    else:
        tier = 'Clean'
    return {'score': round(total, 1), 'tier': tier}
