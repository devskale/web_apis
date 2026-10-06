"""slop API — fuzzy static AI-slop linter.

POST /lint   {"html": "..."}   → findings + review items + score
POST /scan   {"url": "..."}    → server-side fetch + lint
GET  /rules                    → active detector ids + definitions version
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import DEFINITIONS_VERSION
from .detectors import run_all, score
from .page_model import PageModel

router = APIRouter()

MAX_HTML_BYTES = 2 * 1024 * 1024  # self-contained pages; 2MB is generous
FETCH_TIMEOUT_S = 20


class LintBody(BaseModel):
    html: str = Field(..., min_length=1, description="Full HTML document")


class ScanBody(BaseModel):
    url: str = Field(..., description="Page URL to fetch and lint")


def _lint(html: str) -> dict:
    page = PageModel.parse(html)
    findings = run_all(page)
    out_findings = [
        {'id': f.id, 'weight': f.weight, 'confidence': round(f.confidence, 2),
         'evidence': f.evidence, 'selector': f.selector, 'fix': f.fix}
        for f in findings if f.band() == 'finding'
    ]
    review = [
        {'id': f.id, 'evidence': f.evidence, 'selector': f.selector,
         'fix': f.fix,
         'question': f'possible {f.id}: decoration or meaningful? review this'}
        for f in findings if f.band() == 'review'
    ]
    s = score(findings)
    return {
        'score': s['score'],
        'tier': s['tier'],
        'findings': out_findings,
        'review': review,
        'definitions_version': DEFINITIONS_VERSION,
    }


@router.post('/lint')
async def lint(body: LintBody) -> dict:
    """Lint a self-contained HTML document. Deterministic, no browser."""
    if len(body.html.encode('utf-8', 'replace')) > MAX_HTML_BYTES:
        raise HTTPException(413, 'HTML too large (max 2MB)')
    try:
        return _lint(body.html)
    except Exception:
        logging.exception('slop/lint failed')
        raise HTTPException(500, 'Lint failed.')


@router.post('/scan')
async def scan(body: ScanBody) -> dict:
    """Fetch a URL server-side and lint it."""
    try:
        async with httpx.AsyncClient(
                timeout=FETCH_TIMEOUT_S, follow_redirects=True) as client:
            resp = await client.get(body.url)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(502, f'Fetch failed: {e.__class__.__name__}')
    if len(resp.content) > MAX_HTML_BYTES:
        raise HTTPException(413, 'Page too large (max 2MB)')
    result = _lint(resp.text)
    result['url'] = str(resp.url)
    result['title'] = _title(resp.text)
    return result


def _title(html: str) -> str:
    import re
    m = re.search(r'<title[^>]*>(.*?)</title>', html, re.S)
    return m.group(1).strip() if m else ''


@router.get('/rules')
async def rules() -> dict:
    """Active detectors + version — agent self-documentation."""
    from .detectors import _STRUCTURAL
    return {
        'definitions_version': DEFINITIONS_VERSION,
        'detectors': [
            {'id': d.id, 'weight': d.weight,
             'doc': (d.__doc__ or '').strip().split('\n')[0]}
            for d in _STRUCTURAL
        ],
        'bands': {'finding': '>= 0.7', 'review': '0.3 - 0.7',
                  'silent': '< 0.3'},
    }
