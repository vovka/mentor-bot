"""Markdown → Telegram HTML, MarkdownV2 escaping and message chunking (stdlib only)."""

import html
import re

_RESERVED = r"_*[]()~`>#+-=|{}.!"


def escape_v2(text: str) -> str:
    return "".join(f"\\{c}" if c in _RESERVED else c for c in text)


def chunk(text: str, limit: int = 4096) -> list[str]:
    """Split on line boundaries; only split mid-line when one line exceeds limit."""
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(line) <= limit:
            current = line
        else:
            for i in range(0, len(line), limit):
                chunks.append(line[i : i + limit])
            current = ""
    if current:
        chunks.append(current)
    return chunks or [""]


_INLINE = [
    (re.compile(r"`([^`\n]+)`"), r"<code>\1</code>"),
    (re.compile(r"\*\*(.+?)\*\*"), r"<b>\1</b>"),
    (re.compile(r"__(.+?)__"), r"<b>\1</b>"),
    (re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])"), r"<i>\1</i>"),
    (re.compile(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)"), r"<i>\1</i>"),
    (re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)"), r'<a href="\2">\1</a>'),
]


def to_html(text: str) -> str:
    """The Markdown agents write (bold, italics, `code`, ```blocks```, links, # headings) as Telegram HTML."""
    parts = re.split(r"```(?:\w+)?\n?(.*?)```", text, flags=re.S)
    out = []
    for i, part in enumerate(parts):
        if i % 2:
            out.append(f"<pre>{html.escape(part.rstrip())}</pre>")
            continue
        part = re.sub(r"^#{1,6} +(.+)$", r"**\1**", html.escape(part, quote=False), flags=re.M)
        for pattern, repl in _INLINE:
            part = pattern.sub(repl, part)
        out.append(part)
    return "".join(out)
