# C3A Core — Functional Test Results



## How to run

```bash
# AI layer
cd c3a-core-ai && ../../.venv/bin/python -m unittest discover -s tests

# API gateway (unit tests only, Postgres integration tests skipped)
cd c3a-core-api && ../../.venv/bin/python -m unittest discover -s tests

# API gateway, including the two Postgres integration test files
cd c3a-core-api && RUN_POSTGRES_INTEGRATION_TESTS=1 DATABASE_URL="<neon connection string>" \
  ../../.venv/bin/python -m unittest discover -s tests
```

## Result summary

| Suite | Tests | Result |
|---|---|---|
| `c3a-core-ai/tests/` | 93 | **All pass** |
| `c3a-core-api/tests/` (unit only) | 70 (11 Postgres tests skipped) | **All pass** |
| `c3a-core-api/tests/` (with `RUN_POSTGRES_INTEGRATION_TESTS=1`) | 70 (0 skipped) | **All pass** |
| **Total** | **163** | **All pass** |

`test_endpoint_coverage.py` is new in both services — added to close the gap
below, where several endpoints had no automated test before this round.

## Endpoint coverage matrix

Legend: covered = covered by an automated test · new = test added in this round ·
fixed = bug found and fixed while adding/running this coverage.

### c3a-core-api (gateway — the only service the UI calls directly)

| Endpoint | Test file | Status |
|---|---|---|
| `GET /health` | `test_endpoint_coverage.py` | new, covered |
| `GET /training/topics` | `test_training_resources.py` | covered |
| `GET /training/topics/{id}/materials` | `test_training_resources.py` | covered |
| `GET /training/materials/search` | `test_training_resources.py` | covered |
| `POST /training/task-materials` | `test_endpoint_coverage.py` | new, covered |
| `GET /workers/{id}/visits` | `test_endpoint_coverage.py` | new, covered |
| `GET /workers/{id}/visit-dates` | `test_visit_dates_api.py` | covered |
| `GET /workers/{id}/shift-summary` | `test_endpoint_coverage.py` | new, covered |
| `GET /visits/{id}` | `test_risk_alert_api.py`, `test_postgres_fr6_integration.py` | covered |
| `PATCH /patients/{id}/profile` | `test_endpoint_coverage.py` | new, covered |
| `POST /visits/{id}/start` | `test_risk_alert_api.py`, `test_postgres_fr6_integration.py` | covered |
| `POST /visits/{id}/tasks/{id}/complete` | `test_endpoint_coverage.py` | new, covered |
| `PATCH /visits/{id}/tasks/{id}` | `test_postgres_fr6_integration.py` | covered |
| `POST /visits/{id}/tasks/{id}/issue` | `test_endpoint_coverage.py` | new, covered |
| `PATCH /visits/{id}/medication-support` | `test_postgres_fr6_integration.py` | covered |
| `PATCH /visits/{id}/alerts/{id}` | `test_risk_alert_api.py`, `test_postgres_fr6_integration.py` | covered |
| `POST /visits/{id}/complete` | `test_postgres_fr6_integration.py` | covered |
| `POST /visits/{id}/report` | `test_endpoint_coverage.py` | new, covered |
| `GET /patients/{id}/summary` | `test_endpoint_coverage.py` | new, covered, fixed |
| `POST /ai/risk/analyse` (gateway proxy) | `test_endpoint_coverage.py` | new, covered |
| `POST /chat` | `test_chat_sources.py` | covered |
| `POST /chat/stream` | `test_chat_sources.py` | covered |
| `POST /translate` | `test_endpoint_coverage.py` | new, covered |
| `POST /speech/transcribe` | — | not covered (needs a real audio file; verify manually in the UI) |
| `POST /upload` | `test_endpoint_coverage.py` | new, covered |

### c3a-core-ai (AI service)

| Endpoint | Test file | Status |
|---|---|---|
| `GET /ai/health` | `test_endpoint_coverage.py` | new, covered |
| `POST /ai/speech/transcribe` | — | not covered (needs a real audio file; verify manually) |
| `POST /ai/patient-summary` | `test_endpoint_coverage.py` | new, covered, fixed |
| `POST /ai/chat` | `test_chat_orchestration.py` | covered |
| `POST /ai/chat/stream` | `test_chat_orchestration.py` | covered |
| `POST /ai/risk/analyse` | `test_endpoint_coverage.py` (endpoint) + `test_risk_analysis.py` (prompt/parser units) | new, covered |
| `POST /ai/translate` | `test_endpoint_coverage.py` | new, covered |
| `POST /ai/rag/search` | `test_endpoint_coverage.py` | new, covered |
| `POST /ai/training/task-materials` | `test_endpoint_coverage.py` (endpoint) + `test_web_search.py` (query-building units) | new, covered |

### c3a-core-ui

No automated test suite exists (no `*.test.ts(x)` files, no test script in
`package.json`). `npx tsc --noEmit` passes (type-check only). Functional
verification for this layer is manual: run `npx expo start` and walk the
care-task flow.

## Bugs found and fixed during this round

1. **AI service could never read patient records.**
   `c3a-core-ai/.env` had no `DATABASE_URL`. The gateway's `.env` has one, but
   the AI service is a separate process with its own `.env` and never
   inherited it. This silently broke `/ai/patient-summary` (always 404 "no
   database records") and the database-grounded part of `/ai/chat`'s routing
   since the service first shipped.
   **Fix:** added the same Neon connection string to `c3a-core-ai/.env` (and
   a placeholder to `.env.example`). Verified with a live call — patient
   summary now generates a real clinical summary from the Synthea tables.

2. Two test-script input mistakes surfaced during manual live probing
   (missing `status` on `/tasks/{id}/complete`, missing `medicationItems` on
   `/medication-support`) — not application bugs, just incomplete test
   payloads; both are now encoded correctly in `test_endpoint_coverage.py`.

## Known environment limitations (not application bugs)

- **Qdrant cluster unreachable** (`Connection reset by peer`). Diagnosed as
  the cluster being paused/suspended, not a local network or code issue.
  Needs the Qdrant account owner (per git history: Lantao Yang) to resume it
  in the Qdrant Cloud console. Until then, internal RAG retrieval returns no
  results and `/ai/training/task-materials` always falls back to Tavily web
  search.
- **Local Ollama is memory-constrained on this machine** (8GB RAM). Under
  memory pressure, `llama3.1:8b` can return a malformed empty response
  (`done:false` with empty content) instead of a clean error, and generation
  slows to ~4 tokens/sec instead of its normal speed. A clean restart of
  `ollama serve` recovers it; this does not reproduce on a machine with more
  headroom or a quieter desktop.
