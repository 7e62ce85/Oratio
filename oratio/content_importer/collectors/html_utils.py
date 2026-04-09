"""
Shared HTML-to-text conversion utilities for all collectors.

Problem:
  Most external sources return content with HTML markup (<br>, <p>, <li>, etc.).
  Naively stripping tags with `re.sub(r"<[^>]+>", "", html)` causes:
    - Line breaks disappearing (sentences merging together)
    - List items merging into one blob
    - URLs broken by <wbr> tags (4chan specific)
    - HTML entities not decoded
    - Excessive whitespace / blank lines

This module provides a single robust `clean_html_to_text()` function that all
collectors should use instead of rolling their own regex.
"""

from __future__ import annotations

import html as html_module
import re

# ── Block-level tags that should produce a newline ──────────────────────────
_BLOCK_TAGS = re.compile(
    r"</?(?:p|div|br|hr|li|ul|ol|tr|th|td|h[1-6]|blockquote|pre|section|article|header|footer|aside|nav|details|summary|figure|figcaption)\b[^>]*/?>",
    re.IGNORECASE,
)

# ── <wbr> tags (word break opportunity, used by 4chan in URLs) ──────────────
_WBR_TAG = re.compile(r"<wbr\s*/?>", re.IGNORECASE)

# ── All remaining HTML tags ─────────────────────────────────────────────────
_ALL_TAGS = re.compile(r"<[^>]+>")

# ── Whitespace normalization ────────────────────────────────────────────────
_MULTI_NEWLINES = re.compile(r"\n{3,}")        # 3+ newlines → 2
_TRAILING_SPACES = re.compile(r"[ \t]+$", re.MULTILINE)  # trailing spaces per line
_LEADING_SPACES = re.compile(r"^[ \t]+", re.MULTILINE)   # leading spaces per line
_MULTI_SPACES = re.compile(r"[ \t]{2,}")       # 2+ spaces → 1


def clean_html_to_text(text: str, *, preserve_newlines: bool = True) -> str:
    """
    Convert HTML-formatted text to clean plain text.

    Parameters
    ----------
    text : str
        Raw HTML string (e.g. 4chan comment, Reddit body, RSS summary).
    preserve_newlines : bool
        If True (default), block-level tags become ``\\n`` so paragraph
        structure is preserved.  If False, they become a single space
        (useful for titles or single-line fields).

    Returns
    -------
    str
        Clean plain text with proper line breaks and decoded entities.

    Examples
    --------
    >>> clean_html_to_text('Hello<br>World<br><br>New paragraph')
    'Hello\\nWorld\\n\\nNew paragraph'

    >>> clean_html_to_text('Check this: https://exam<wbr>ple.com/path')
    'Check this: https://example.com/path'

    >>> clean_html_to_text('<p>First</p><p>Second</p>', preserve_newlines=False)
    'First Second'
    """
    if not text:
        return ""

    separator = "\n" if preserve_newlines else " "

    # 1. Remove <wbr> tags first (before other processing, to rejoin URLs)
    text = _WBR_TAG.sub("", text)

    # 2. Block-level tags → newline (or space)
    text = _BLOCK_TAGS.sub(separator, text)

    # 3. Remove all remaining HTML tags (spans, anchors, etc.)
    text = _ALL_TAGS.sub("", text)

    # 4. Decode HTML entities (&amp; &gt; &lt; &#039; &#x27; etc.)
    #    html.unescape handles ALL standard + numeric entities
    text = html_module.unescape(text)

    # 5. Normalize whitespace
    if preserve_newlines:
        # Collapse 3+ consecutive newlines to 2 (one blank line max)
        text = _MULTI_NEWLINES.sub("\n\n", text)
        # Remove trailing/leading spaces per line
        text = _TRAILING_SPACES.sub("", text)
        text = _LEADING_SPACES.sub("", text)
    else:
        # Flatten everything to single spaces
        text = text.replace("\n", " ")

    # Collapse multiple spaces to one
    text = _MULTI_SPACES.sub(" ", text)

    return text.strip()
