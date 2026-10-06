"""slop API — fuzzy static AI-slop linter.

POST /lint   {"html": "..."}   → findings + review items + score
POST /scan   {"url": "..."}    → server-side fetch + lint
GET  /rules                    → active detector ids + definitions version
"""

from __future__ import annotations

import base64
import logging

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from . import DEFINITIONS_VERSION
from .detectors import run_all, score
from .page_model import PageModel

router = APIRouter()

MAX_HTML_BYTES = 2 * 1024 * 1024  # self-contained pages; 2MB is generous
FETCH_TIMEOUT_S = 20


class LintBody(BaseModel):
    """Exactly one of `html` (raw) or `html_base64` must be provided.

    extra='forbid' so a hand-rolled client sending {"html": "<base64>",
    "base64": true} fails LOUDLY (422) instead of silently linting the
    base64 string — which would always report Clean.
    """

    model_config = ConfigDict(extra='forbid')
    html: str | None = Field(None, min_length=1)
    html_base64: str | None = Field(None, min_length=1)


class ScanBody(BaseModel):
    url: str = Field(..., description="Page URL to fetch and lint")


def _lint(html: str) -> dict:
    page = PageModel.parse(html)
    findings = run_all(page)
    out_findings = [                       # hard: card-accent family, gates
        {'id': f.id, 'weight': f.weight, 'confidence': round(f.confidence, 2),
         'evidence': f.evidence, 'selector': f.selector, 'fix': f.fix}
        for f in findings
        if f.band() == 'finding' and f.level == 'hard'
    ]
    out_info = [                           # reported, never gates
        {'id': f.id, 'confidence': round(f.confidence, 2),
         'evidence': f.evidence, 'fix': f.fix}
        for f in findings
        if f.band() != 'silent' and f.level == 'info'
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
        'info': out_info,
        'review': review,
        'definitions_version': DEFINITIONS_VERSION,
    }


@router.post('/lint')
async def lint(body: LintBody) -> dict:
    """Lint a self-contained HTML document. Deterministic, no browser."""
    if body.html is None and body.html_base64 is None:
        raise HTTPException(422, 'provide exactly one of html | html_base64')
    if body.html is not None and body.html_base64 is not None:
        raise HTTPException(422, 'provide exactly one of html | html_base64')
    if body.html_base64 is not None:
        try:
            html = base64.b64decode(body.html_base64, validate=True).decode(
                'utf-8', 'replace')
        except Exception:
            raise HTTPException(400, 'html_base64 is not valid base64')
    else:
        html = body.html or ''
    if len(html.encode('utf-8', 'replace')) > MAX_HTML_BYTES:
        raise HTTPException(413, 'HTML too large (max 2MB)')
    try:
        return _lint(html)
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
