# Task 4 - Rate Limiter and Fallback

Router that limits each API key to 50,000 tokens per minute and falls back to a backup model if the primary returns 429, fails or takes more than 3 seconds.

```
pip install -r requirements.txt
python -m pytest -q tests
```

To try the fallback manually (primary is slow on purpose):

```
MOCK_NAME=primary MOCK_MODE=slow uvicorn mock_providers:app --port 9101
MOCK_NAME=backup uvicorn mock_providers:app --port 9102
uvicorn router:app --port 8000
curl -si localhost:8000/v1/chat/completions -H "Authorization: Bearer my-key" -H "content-type: application/json" -d '{"messages":[{"role":"user","content":"hi"}]}'
```

Rate limiter (`rate_limiter.py`):
- each request is saved in sqlite as (api_key, time, tokens)
- usage is the sum of tokens in the last 60 seconds, older rows get deleted
- before calling the model it saves an estimate (text length / 4 + max_tokens), then updates it with the real count from the response
- if both models fail the row is deleted so the user isn't charged
- uses `BEGIN IMMEDIATE` so two requests at the same time can't both go over the limit

Fallback (`router.py`):
- `asyncio.wait_for` with 3 seconds on the whole primary call
- 429, 5xx, connection errors and bad JSON also go to the backup
- if both fail it returns 503

Errors always have the same format and don't include stack traces or internal urls:

```
{"error": {"type": "upstream_unavailable", "message": "All models are unavailable. Please try again later."}}
```
