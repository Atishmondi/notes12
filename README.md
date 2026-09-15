# Notes12

Notes12 is a Discord-based AI note-taking system.

## V0 scope (locked)

V0 is ONLY:

- text → AI → validated structured Notes12 JSON

Explicitly NOT in V0:

- Discord bot
- Screenshot / image processing
- Web frontend / TypeScript
- Database
- Changes to the locked Notes12 JSON schema

We are building incrementally. V0 Step 3 adds the first working pipeline:
raw text → Gemini structured output → Pydantic-validated `Notes12Document`.
No retry, Discord, frontend, database, or image input yet.

## Stack

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/) for project / dependency management
- [Pydantic v2](https://docs.pydantic.dev/) for schema / data validation
- [google-genai](https://github.com/googleapis/python-genai) (official Google Gen AI SDK) for Gemini
- [pytest](https://docs.pytest.org/) for testing
- [Ruff](https://docs.astral.sh/ruff/) via `uv check` / `uv format` for lint / format

## Project structure

```text
.
├── .env.example          # placeholder config (never commit real keys)
├── pyproject.toml      # project metadata, deps, ruff + pytest config
├── uv.lock             # locked dependencies (committed)
├── src/notes12/        # backend package
│   ├── __init__.py
│   ├── schema.py       # LOCKED Notes12 Pydantic contract
│   └── extractor.py    # Gemini structured extraction (text → Notes12Document)
├── tests/              # pytest tests (offline; Gemini calls are mocked)
│   ├── test_setup.py
│   ├── test_schema.py
│   └── test_extractor.py
└── README.md
```

## Gemini setup

1. Create a key in Google AI Studio (free): https://aistudio.google.com/apikey
2. Export it locally (never commit it):
```bash
export GEMINI_API_KEY="your-key-here"
```
3. Optional: copy `.env.example` to `.env` for local reference (`.env` is git-ignored).
   No `dotenv` loading is built in — the adapter reads `GEMINI_API_KEY` from the environment,
   or accepts `api_key=` explicitly (useful for tests).

## Usage

```python
import os
from notes12 import extract_notes

doc = extract_notes(
    "Photosynthesis uses chlorophyll to convert light into energy.",
    api_key=os.environ["GEMINI_API_KEY"],  # or rely on the env var automatically
    # model="gemini-3.6-flash",  # default; override if needed
)
print(doc.model_dump_json(indent=2))
```

Failures (missing key, empty input, API error, invalid model output) raise
`notes12.GeminiExtractionError`. Transient server/rate-limit failures
(HTTP 429/500/502/503/504) are retried up to `max_retries` times
(default 2, i.e. up to 3 attempts) with exponential backoff
(`retry_base_delay * 2**n` seconds, default base 1s); auth/config errors
are never retried. Tests never hit the network: they inject a fake client.

## Manual smoke test (real API, local only)

`scripts/gemini_smoke.py` runs real extraction for three built-in evaluation
inputs (technical concept, timeline, cause/effect). It is NOT part of pytest.

```bash
export GEMINI_API_KEY="your-key-here"
uv run scripts/gemini_smoke.py --case all
uv run scripts/gemini_smoke.py --case A --model gemini-3.6-flash
```

It prints title, summary, map_type, node/relationship counts and details,
plus the full validated JSON. It never prints the API key.

## Development

Requires `uv` (installed via Homebrew on macOS: `brew install uv`).

```bash
# sync dependencies (creates .venv)
uv sync

# run tests
uv run pytest

# lint check
uv check

# format check
uv format --check

# apply formatting
uv format
```
