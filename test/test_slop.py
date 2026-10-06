"""Golden fixtures for the slop linter — pin detector behavior.

One positive + one negative fixture per tell (Krebs' merge bar: a tell that
flags good design is noise). The auditflow case must produce the edge_stripe
FINDING that the old border-left-only regex missed.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from slop.detectors import run_all, score                     # noqa: E402
from slop.page_model import PageModel                          # noqa: E402


def _lint(html: str):
    return run_all(PageModel.parse(html))


def _ids(findings):
    return [f.id for f in findings]


# ── edge_stripe ─────────────────────────────────────────────────────────────

def test_edge_stripe_top_finding():
    """The auditflow case: border-top 4px in a saturated var() color."""
    html = """<style>
      :root { --cat-a: #4f46e5; }
      .path-card { border-top: 4px solid var(--cat-a); background: #fff; }
    </style><div class="path-card">Pfad A</div>"""
    fs = [f for f in _lint(html) if f.id == 'edge_stripe']
    assert fs, 'border-top stripe in var() color must be found'
    assert fs[0].confidence >= 0.7
    assert 'border-top' in fs[0].evidence


def test_edge_stripe_all_four_sides():
    for side in ('left', 'top', 'right', 'bottom'):
        html = f"""<style>
          .c {{ border-{side}: 4px solid #e11d48; }}
        </style><div class="c">x</div>"""
        fs = [f for f in _lint(html) if f.id == 'edge_stripe']
        assert fs, f'border-{side} stripe must be found'


def test_edge_stripe_neutral_passes():
    """Thin neutral spines (timeline connectors) pass."""
    html = """<style>
      :root { --line: #e4e4e7; }
      .spine { border-left: 1px solid var(--line); }
      .card2 { border-top: 1px solid #cbd5e1; }
    </style><div class="spine">t</div>"""
    assert 'edge_stripe' not in _ids(_lint(html))


def test_edge_stripe_thin_colored_is_review():
    """2px colored edge is borderline — REVIEW band, not a hard finding."""
    html = """<style>.c { border-left: 2px solid #0ea5e9; }</style>"""
    fs = [f for f in _lint(html) if f.id == 'edge_stripe']
    assert fs and fs[0].confidence < 0.7


# ── pill ────────────────────────────────────────────────────────────────────

def test_pill_finding():
    html = """<style>.badge { border-radius: 999px; background: #fef3c7; }</style>"""
    fs = [f for f in _lint(html) if f.id == 'pill']
    assert fs and fs[0].confidence >= 0.7


def test_pill_neutral_passes():
    html = """<style>.badge { border-radius: 999px; background: #f4f4f5; }</style>"""
    assert 'pill' not in _ids(_lint(html))


def test_tailwind_pill():
    html = '<span class="rounded-full bg-emerald-100">ok</span>'
    assert 'pill' in _ids(_lint(html))


# ── purple_cta ──────────────────────────────────────────────────────────────

def test_purple_cta_finding():
    html = """<style>.cta { background: #6366f1; color: #fff; }
      .cta2 { background: #8b5cf6; color: #fff; }</style>"""
    fs = [f for f in _lint(html) if f.id == 'purple_cta']
    assert fs and fs[0].confidence >= 0.7


def test_purple_single_is_review():
    """One purple element could be brand color — REVIEW, not FINDING."""
    html = """<style>
      .a { background: #6366f1; }
    </style>"""
    fs = [f for f in _lint(html) if f.id == 'purple_cta']
    assert fs and fs[0].confidence < 0.7


def test_purple_hsl_notation():
    html = """<style>.c { background: hsl(258, 90%, 66%); }</style>"""
    fs = [f for f in _lint(html) if f.id == 'purple_cta']
    assert fs


# ── gradient_text / glass / glow ────────────────────────────────────────────

def test_gradient_text():
    html = """<style>h1 { background: linear-gradient(90deg,#f00,#00f);
      -webkit-background-clip: text; color: transparent; }</style>"""
    assert 'gradient_text' in _ids(_lint(html))


def test_glass():
    html = """<style>.g { backdrop-filter: blur(12px);
      background: rgba(255,255,255,.5); }</style>"""
    assert 'glass' in _ids(_lint(html))


def test_glow():
    html = """<style>.h { box-shadow: 0 0 48px rgba(139,92,246,.5); }</style>"""
    assert 'glow' in _ids(_lint(html))


def test_glow_neutral_shadow_passes():
    html = """<style>.h { box-shadow: 0 4px 24px rgba(0,0,0,.15); }</style>"""
    assert 'glow' not in _ids(_lint(html))


# ── slop_fonts ──────────────────────────────────────────────────────────────

def test_slop_fonts_inter():
    html = """<style>body { font-family: Inter, system-ui, sans-serif; }</style>"""
    assert 'slop_fonts' in _ids(_lint(html))


def test_slop_fonts_interstate_passes():
    html = """<style>body { font-family: Interstate, sans-serif; }</style>"""
    assert 'slop_fonts' not in _ids(_lint(html))


def test_slop_fonts_system_stack_passes():
    html = """<style>body { font-family: -apple-system, BlinkMacSystemFont,
      "Segoe UI", Roboto, sans-serif; }</style>"""
    assert 'slop_fonts' not in _ids(_lint(html))


# ── all_caps / stat_banner / numbered_steps ─────────────────────────────────

def test_all_caps_wall_finding():
    css = '\n'.join(f'.k{i} {{ text-transform: uppercase; }}' for i in range(12))
    fs = [f for f in _lint(f'<style>{css}</style>') if f.id == 'all_caps']
    assert fs and fs[0].confidence >= 0.7


def test_all_caps_few_kickers_pass():
    css = '\n'.join(f'.k{i} {{ text-transform: uppercase; }}' for i in range(3))
    assert 'all_caps' not in _ids(_lint(f'<style>{css}</style>'))


def test_stat_banner():
    html = ('<body><div>10k+ users</div><div>99.9% uptime</div>'
            '<div>$2M+ saved</div></body>')
    fs = [f for f in _lint(html) if f.id == 'stat_banner']
    assert fs


def test_stat_banner_two_numbers_pass():
    html = '<body><div>99.9% uptime</div><div>10k+ users</div></body>'
    assert 'stat_banner' not in _ids(_lint(html))


def test_numbered_steps_is_review():
    html = ('<body><h2>Step 1 Planen</h2><h2>Step 2 Bauen</h2>'
            '<h2>Step 3 Testen</h2></body>')
    fs = [f for f in _lint(html) if f.id == 'numbered_steps']
    assert fs and fs[0].confidence < 0.7  # handed back for review


# ── score / bands ────────────────────────────────────────────────────────────

def test_score_tiers():
    stripe = """<style>.c { border-top: 4px solid #e11d48; }</style>"""
    s = score(_lint(stripe))
    assert s['score'] > 0
    assert s['tier'] in ('Clean', 'Mild', 'Heavy')


def test_clean_page_scores_low():
    html = """<style>
      :root { --ink: #1a1a1a; --line: #e4e4e7; --paper: #fafaf9; }
      body { font-family: -apple-system, sans-serif; color: var(--ink);
             background: var(--paper); }
      .card { border: 1px solid var(--line); border-radius: 8px; }
    </style><body><h1>Report</h1><div class="card">content</div></body>"""
    s = score(_lint(html))
    assert s['tier'] == 'Clean'
    assert s['score'] < 5


# ── auditflow live page (the founding case) ──────────────────────────────────

def test_auditflow_page():
    """The page that started this: 4px var() stripes the old linter missed."""
    import urllib.request
    try:
        html = urllib.request.urlopen(
            'https://skale.dev/throway/d/agentosreview/auditflow-overview.html',
            timeout=15).read().decode('utf-8', 'replace')
    except Exception:
        import pytest
        pytest.skip('auditflow page not reachable')
    fs = _lint(html)
    stripes = [f for f in fs if f.id == 'edge_stripe']
    assert stripes, 'the border-top var() stripes must be found'
    assert any(f.confidence >= 0.7 for f in stripes)
    assert 'numbered_steps' in _ids(fs)  # process vs decoration → review
