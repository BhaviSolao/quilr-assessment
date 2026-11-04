import re

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CARD = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")

MAX_HELD = 300


def redact(text):
    text = EMAIL.sub("[REDACTED]", text)
    text = SSN.sub("[REDACTED]", text)
    text = CARD.sub("[REDACTED]", text)
    return text


def find_safe_cut(text):
    # emails/SSNs have no spaces and cards only have spaces between digits,
    # so any space not right after a digit is a safe place to cut
    for i in range(len(text) - 1, -1, -1):
        if text[i].isspace():
            after_digit = i > 0 and text[i - 1].isdigit()
            if not after_digit:
                return i + 1
    return 0


class StreamRedactor:
    def __init__(self):
        self.held = ""

    def feed(self, chunk):
        text = self.held + chunk
        cut = find_safe_cut(text)
        cut = max(cut, len(text) - MAX_HELD)
        self.held = text[cut:]
        return redact(text[:cut])

    def flush(self):
        text = redact(self.held)
        self.held = ""
        return text
