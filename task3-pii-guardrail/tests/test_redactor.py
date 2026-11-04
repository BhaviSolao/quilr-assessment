import random

import pytest

from redactor import MAX_HELD, StreamRedactor, redact


def stream(chunks):
    r = StreamRedactor()
    output = "".join(r.feed(c) for c in chunks)
    return output + r.flush()


@pytest.mark.parametrize("text", [
    "mail jane.doe@example.com now",
    "ssn 123-45-6789 ok",
    "card 4111111111111111 ok",
    "card 4111 1111 1111 1111 ok",
    "card 4111-1111-1111-1111 ok",
])
def test_redacts_pii(text):
    assert redact(text).count("[REDACTED]") == 1


def test_leaves_normal_text_alone():
    text = "Order #20240611 shipped. Call 555-1234 or visit user@localhost"
    assert redact(text) == text


@pytest.mark.parametrize("chunks", [
    ["Email john.do", "e@exam", "ple.com please"],
    ["SSN 123", "-45-", "6789 thanks"],
    ["card 4111 1111 ", "1111 1111 done"],
    ["ends with a@b.c", "om"],
])
def test_pii_split_across_chunks(chunks):
    assert stream(chunks) == redact("".join(chunks))
    assert "[REDACTED]" in stream(chunks)


def test_any_split_gives_same_result_as_whole_text():
    text = "hi this is ann (ann.lee@corp.io), SSN 078-05-1120, card 5555 5555 5555 4444. Bye!"
    expected = redact(text)
    for i in range(len(text)):
        assert stream([text[:i], text[i:]]) == expected


def test_random_splits():
    random.seed(1)
    text = "Contact bob@site.com or 123-45-6789, card 4111 1111 1111 1111, thanks! " * 5
    for _ in range(200):
        cuts = sorted(random.sample(range(len(text)), 8))
        chunks = [text[a:b] for a, b in zip([0] + cuts, cuts + [len(text)])]
        assert stream(chunks) == redact(text)


def test_sends_text_early():
    r = StreamRedactor()
    assert r.feed("The quick brown ") == "The quick brown "
    assert r.feed("fox jum") == "fox "
    assert r.held == "jum"


def test_memory_stays_small():
    r = StreamRedactor()
    for _ in range(1000):
        r.feed("x" * 50)
        assert len(r.held) <= MAX_HELD
