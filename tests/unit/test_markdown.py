from mentor.adapters.telegram.markdown import chunk, escape_v2

_RESERVED = r"_*[]()~`>#+-=|{}.!"


def test_escape_v2_covers_all_reserved_chars():
    assert escape_v2(_RESERVED) == "".join(f"\\{c}" for c in _RESERVED)


def test_escape_v2_leaves_plain_text_untouched():
    assert escape_v2("hello world") == "hello world"


def test_chunk_never_exceeds_limit():
    text = "\n".join("some line of text" for _ in range(500))
    for part in chunk(text, limit=100):
        assert len(part) <= 100


def test_chunk_never_splits_a_short_line():
    text = ("a" * 50) + "\n" + ("b" * 50)
    chunks = chunk(text, limit=60)
    assert "a" * 50 in chunks
    assert "b" * 50 in chunks


def test_chunk_splits_an_oversized_single_line():
    text = "x" * 250
    chunks = chunk(text, limit=100)
    assert len(chunks) == 3
    assert all(len(c) <= 100 for c in chunks)
    assert "".join(chunks) == text


def test_chunk_empty_text_returns_single_empty_chunk():
    assert chunk("") == [""]
