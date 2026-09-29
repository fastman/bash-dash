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
def render_description(text: str) -> str:
    parts = _FENCE.split(escape(text or ''))
    # re.split with one group alternates: text, fence body, text, ...
    html = ''.join(f'<pre>{p}</pre>' if i % 2 else _inline(p) for i, p in enumerate(parts))
    return mark_safe(html)
