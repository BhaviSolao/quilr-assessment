# Task 3 - PII Redaction on Streams

LLM gateway that streams the response back and replaces emails, SSNs and card numbers with `[REDACTED]`.

```
pip install -r requirements.txt
python -m pytest -q tests
```

To try it manually:

```
MOCK_DELAY=0.3 uvicorn mock_provider:app --port 9002
uvicorn gateway:app --port 8000
curl -N localhost:8000/v1/chat/completions -H "content-type: application/json" -d '{"stream":true,"messages":[]}'
```

The main problem is PII getting split between chunks, like `john.do` + `e@example.com`.

How `redactor.py` handles it:
- emails and SSNs don't have spaces, card numbers only have spaces between digits
- so it's safe to cut the text at any space that isn't right after a digit
- everything before the last safe space is redacted and sent right away, the rest is held until the next chunk
- at the end of the stream whatever is left is redacted and sent

So the user only waits for about one word, and at most 300 characters are held in memory.

Limitations:
- SSNs without dashes aren't detected
- any 13-19 digit number is treated as a card number
