"""PageModel — one parse, shared by every detector.

Parses <style> blocks and inline style="" attributes into rules, resolves CSS
custom properties (--cat-a: #4f46e5) so var() colors become inspectable, and
keeps the DOM structure + text for context checks. Built once per lint call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Rule:
    selector: str
    decls: str


@dataclass
class PageModel:
    rules: list[Rule] = field(default_factory=list)
    custom_props: dict[str, str] = field(default_factory=dict)
    text: str = ""
    classes: list[str] = field(default_factory=list)
    element_texts: list[str] = field(default_factory=list)

    @classmethod
    def parse(cls, html: str) -> "PageModel":
        page = cls()
        # Strip comments so colors inside HTML/CSS comments don't count.
        src = re.sub(r'<!--.*?-->', '', html, flags=re.S)
        for m in re.finditer(r'<style[^>]*>(.*?)</style>', src, flags=re.S):
            css = re.sub(r'/\*.*?\*/', '', m.group(1), flags=re.S)
            for pm in re.finditer(r'([^{}]+)\{([^{}]*)\}', css):
                sel, decls = pm.group(1).strip(), pm.group(2)
                page.rules.append(Rule(sel, decls))
                if sel.startswith(':root') or sel == 'html' or sel == 'body':
                    for cm in re.finditer(
                            r'(--[a-z0-9-]+)\s*:\s*([^;]+)', decls):
                        page.custom_props[cm.group(1)] = cm.group(2).strip()
        # Custom props can also be defined in other selectors.
        for rule in page.rules:
            for cm in re.finditer(r'(--[a-z0-9-]+)\s*:\s*([^;]+)', rule.decls):
                page.custom_props.setdefault(cm.group(1), cm.group(2).strip())
        # Inline style attributes become rules keyed by tag+classes, so
        # detectors can correlate a fill with the element's size context
        # (a purple 8px dot is a category swatch, not a CTA). The attrs scan
        # tolerates quoted values containing '>' and finds class/style in
        # any order.
        for m in re.finditer(
                r'<([a-zA-Z][a-zA-Z0-9]*)((?:[^>"]|"[^"]*")*)>', src):
            tag, attrs = m.group(1), m.group(2)
            sm = re.search(r'\sstyle="([^"]*)"', attrs)
            if not sm:
                continue
            cm = re.search(r'\sclass="([^"]*)"', attrs)
            classes = cm.group(1).split() if cm else []
            sel = tag + ('.' + '.'.join(classes) if classes else '')
            page.rules.append(Rule(sel, sm.group(1)))
        # Tailwind/utility classes (the style-block parser never sees them).
        for m in re.finditer(r'class="([^"]*)"', src):
            page.classes.extend(m.group(1).split())
        # Visible text (for content tells) and element texts.
        body = re.sub(r'<style.*?</style>', '', src, flags=re.S)
        page.text = re.sub(r'<[^>]+>', ' ', body)
        page.text = re.sub(r'\s+', ' ', page.text).strip()
        for m in re.finditer(r'>([^<>]{2,200})<', src):
            t = m.group(1).strip()
            if t:
                page.element_texts.append(t)
        return page

    def resolve_color(self, value: str) -> str:
        """Resolve one level of var(--x) to its custom-prop value.

        Unresolvable vars return the original string; parse_color then yields
        None (unknown), and detectors must not flag unknowns.
        """
        m = re.fullmatch(r'\s*var\(\s*(--[a-z0-9-]+)\s*\)\s*', value.strip())
        if m:
            return self.custom_props.get(m.group(1), value)
        # var(--x, fallback)
        m = re.fullmatch(
            r'\s*var\(\s*(--[a-z0-9-]+)\s*,\s*([^)]+)\)\s*', value.strip())
        if m:
            return self.custom_props.get(m.group(1), m.group(2))
        return value

    def border_of(self, decls: str, side: str) -> tuple[float, str] | None:
        """Extract (width_px, color_str) of border-<side> if declared."""
        m = re.search(
            r'border-' + side + r'\s*:\s*([\d.]+)(px|rem)\s+solid\s+([^;]+)',
            decls)
        if not m:
            return None
        w = float(m.group(1)) * (16 if m.group(2) == 'rem' else 1)
        return (w, m.group(3).strip())

    def rule_size(self, rule: Rule) -> float | None:
        """Best-effort rendered size (max px) for a rule's element context.

        Looks at the rule's own declarations, then at size declarations from
        class rules referenced by its selector (inline styles carry the fill,
        the class carries the geometry).
        """
        sizes = [float(x) * (16 if u == 'rem' else 1)
                 for x, u in re.findall(
                     r'(?:^|[;\s])(?:width|height)\s*:\s*([\d.]+)(px|rem)',
                     rule.decls)]
        if sizes:
            return max(sizes)
        for part in rule.selector.split('.'):  # look up class rules
            if not part or part == rule.selector.split('.')[0]:
                continue
            for r in self.rules:
                if re.search(r'\.' + re.escape(part) + r'(?![\w-])', r.selector):
                    m = re.findall(
                        r'(?:^|[;\s])(?:width|height)\s*:\s*([\d.]+)(px|rem)',
                        r.decls)
                    if m:
                        return max(float(x) * (16 if u == 'rem' else 1)
                                   for x, u in m)
        return None

    def looks_like_card(self, selector: str) -> bool:
        """Heuristic: does this selector target a card/panel (vs a dot/label)?"""
        s = selector.lower()
        if re.search(r'card|panel|box|tile|item|cell|callout|note|path|step',
                     s):
            return True
        return 'border-radius' in selector or 'bg' in s.split('-')
