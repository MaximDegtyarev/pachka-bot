from app.pachca.client import _split


def test_short_message_not_split():
    assert _split("hello") == ["hello"]


def test_split_on_blank_lines():
    # 3 paragraphs, each ~50 chars; limit set low to force splitting
    para = "x" * 50
    text = f"{para}\n\n{para}\n\n{para}"
    chunks = _split(text, limit=120)
    assert len(chunks) == 2
    assert "x" * 50 in chunks[0]
    assert "x" * 50 in chunks[1]


def test_split_keeps_all_content():
    para = "y" * 100
    text = "\n\n".join([para] * 5)
    chunks = _split(text, limit=250)
    total = "\n\n".join(chunks)
    assert total.count(para) == 5


def test_single_oversized_paragraph_not_split():
    # If one paragraph alone exceeds the limit, keep it as one chunk.
    big = "z" * 5000
    chunks = _split(big, limit=100)
    assert chunks == [big]
