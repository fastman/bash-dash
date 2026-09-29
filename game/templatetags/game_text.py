"""Render challenge descriptions: escaped text with ``` fences and `inline code` only.

No Markdown library on purpose (no links, no raw HTML): escape first, then add
the few tags we own.
"""

import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

# A fence swallows the newline right before and after it: <pre> is already a block.
_FENCE = re.compile(r'\n?```[^\n]*\n(.*?)\n?```\n?', re.S)
_INLINE = re.compile(r'`([^`\n]+)`')


def _inline(text: str) -> str:
    return _INLINE.sub(r'<code>\1</code>', text).replace('\n', '<br>')


@register.filter
def clock(remaining_ms) -> str:
    """Format milliseconds as m:ss, rounding up so the display hits 0:00 only at 0."""
    seconds = -(-max(0, int(remaining_ms)) // 1000)
    return f'{seconds // 60}:{seconds % 60:02d}'


@register.filter
def mmss(delta) -> str:
    """Format a timedelta as m:ss, rounding DOWN to whole seconds ("—" for None)."""
    if delta is None:
        return '\u2014'
    seconds = max(0, int(delta.total_seconds()))
    return f'{seconds // 60}:{seconds % 60:02d}'


@register.filter
def duration_text(seconds) -> str:
    seconds = int(seconds)
    if seconds % 60 == 0:
        n = seconds // 60
        return f'{n} minute{"" if n == 1 else "s"}'
    return f'{seconds} seconds'


@register.filter
def render_description(text: str) -> str:
    parts = _FENCE.split(escape(text or ''))
    # re.split with one group alternates: text, fence body, text, ...
    html = ''.join(f'<pre>{p}</pre>' if i % 2 else _inline(p) for i, p in enumerate(parts))
    return mark_safe(html)
