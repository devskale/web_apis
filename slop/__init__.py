"""slop — fuzzy static AI-slop linter for self-contained HTML.

Deterministic, browser-less, LLM-less. Parses <style> blocks and inline
styles, resolves CSS custom properties, and runs fuzzy detectors that emit
confidence-scored findings. Uncertain findings are returned as REVIEW items
for the calling agent to judge — ambiguity stays visible, never hidden.

Design decisions (2026-10, session with Johann):
  * fuzzy, not regex-hard: colors compared perceptually (HSL), thresholds
    instead of hex whitelists; findings carry confidence 0..1
  * three bands: >=0.7 FINDING, 0.3..0.7 REVIEW (agent decides), <0.3 silent
  * extension: rules/*.yaml (declarative) + detectors/*.py (structural),
    both built on fuzzy.py primitives; registry by file discovery
  * calibration: golden fixtures pin behavior; corpus.json + confusion
    matrix (modeled on slop-detect's CALIBRATION.md, Krebs' merge bar:
    deterministic, common, precise, visible)

Pattern vocabulary derived from the MIT-licensed pattern lists of
design-slop-cop (Adrian Krebs) and slop-detect (ravidsrk), re-implemented
statically. Rendering-only patterns (centered hero geometry, icon-card grids,
bento layouts) are honestly skipped: a static linter must not guess geometry.
"""

DEFINITIONS_VERSION = "2026.10"

# Confidence bands
FIND = 0.7     # >= this: a definite finding
REVIEW = 0.3   # >= this: uncertain, hand back to the agent for review

# Tier thresholds on the weighted confidence sum (slop-detect-compatible)
TIER_CLEAN = 10
TIER_HEAVY = 30
