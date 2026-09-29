"""MarkdownV2 escaping and Telegram message chunking (stdlib only)."""

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
