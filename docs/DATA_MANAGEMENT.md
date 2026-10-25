# Data Management

This document identifies all inputs and outputs visible in the repository and
states where each data class is stored. It applies to development and research
evaluation only; the project should use synthetic data.

## 1. Data ownership and sources of truth

| Data class | System of record | Examples |
|---|---|---|
| Visit operations | PostgreSQL `c3a_app_*` tables | workers, shifts, visits, tasks, locations, events, medication support, alerts, alert actions |
| Synthetic patient records | PostgreSQL `c3a_synthea_*` tables | demographics, CALD profile, conditions, medicines, allergies, encounters, observations |
| Training catalogue | PostgreSQL | topics, material text, source URLs, multilingual resource links |
| Guideline knowledge base | Qdrant | PDF chunk text, embeddings, source/title/page metadata, hashes, ingestion time |
| Active UI state | Device memory | current scenario, visit queue, pending attachments, chat messages |
| Speech input | Device cache then local speech service | temporary audio upload and transcript |
| Evaluation definitions | Git | `c3a-core-ai/evaluation/cases.jsonl` (180 synthetic cases) |
| Evaluation outputs | Local ignored directory | response JSONL, judge JSONL, manifests, generated reports under `evaluation/results/` |
| Service diagnostics | Console/local log files | request IDs, timings, dependency status, limited payload previews |

The UI treats server responses as authoritative. Chat messages are not written
to PostgreSQL and disappear when the UI process/app state is reset. A generated
visit report is persisted only when it is supplied to the finish-visit endpoint;
the repository stores it as the note on the corresponding `visit_completed`
event.

## 2. Inputs

### User and device inputs

- Chat text and prior in-memory messages.
- Selected images/documents encoded as base64, although the default model
  rejects attachment analysis.
- Care-task status and notes, medication-support status/items/notes, patient
  care-preference edits, and risk-alert actions.
- GPS coordinates, accuracy, permission state, manual-override note, and local
  timestamp for check-in/check-out. The API recalculates distance and expected
  area instead of trusting client-derived values.
- Recorded audio, source language, speaker role, and optional visit ID.
- Care-outcome form content used to generate a draft visit report.

### Reference and external inputs

- Synthetic Synthea/PostgreSQL records.
- Curated training-material SQL and linked official resources.
- PDFs explicitly passed to `scripts.ingest_pdfs`.
- Optional Tavily results restricted by the allow-listed Australian health and
  aged-care domains in `web_search.py` and filtered for practical relevance.
- Ollama model output. This is probabilistic generated data, not a source of
  clinical truth.

## 3. Outputs

- API scenario snapshots, queues, visit dates, summaries, and training records.
- Persistent workflow changes and audit events in PostgreSQL.
- AI answers, NDJSON streaming tokens, translations, risk-analysis suggestions,
  task-material suggestions, patient summaries, and draft visit reports.
- Structured citations for synthetic database rows, Qdrant chunks, and selected
  web sources.
- Speech transcripts and device text-to-speech playback.
- Evaluation JSONL/manifests/reports when evaluation scripts are run.
- `/upload` currently writes decoded files into the host's `/tmp` directory and
  returns a nominal `/files/...` URL. No matching static-file route or cleanup
  policy exists, so this endpoint must not be treated as managed storage.

## 4. PostgreSQL schema and migration policy

The operational migration sequence is:

| Migration | Purpose | Important behaviour |
|---|---|---|
| `001` | Core workers, profiles, shifts, visits, tasks, locations, events, alerts | Requires existing Synthea patients |
| `002` | Deterministic demo worker/visits/tasks/alerts | Resets related records for seeded visits |
| `003` | Medication-support records | One current record per visit |
| `004` | Alert lifecycle and action audit | Adds acknowledge/resolve/dismiss history |
| `005` | Training topics/materials | Initial catalogue |
| `006`–`008` | Authoritative/verbatim/additional training content | `006` and `007` rebuild catalogue rows |
| `009`–`010` | Multilingual/grouped resource links | Use the sequencing rules in the development guide |

There is no programmatic migration runner or schema-version table. Before a
change, back up the target database, identify the last applied file, review SQL
for deletes/updates, run against a disposable copy, and record the outcome.

## 5. Qdrant ingestion and provenance

The PDF ingester extracts text, creates approximately 450-word chunks with
overlap, embeds them with the configured model, and uses a stable point ID. A
payload includes:

- chunk text and content hash;
- document hash, title, filename, and original ingestion path;
- document type and language;
- page range, detected section heading, chunk index, and ingestion timestamp.

The original PDFs are external inputs and are not present in this repository.
Preserve a separate licensed source archive and manifest. The stored
`source_path` may reveal a developer filesystem path; use a controlled staging
path for formal ingestion if that metadata is exported.

## 6. Data lifecycle

### Creation and update

- Repository mutations are transaction-backed PostgreSQL writes.
- Risk alerts use stable keys and separate action records for auditability.
- RAG ingestion is an upsert; `--replace` first deletes chunks matching one
  source filename.
- Full cloud evaluation creates UUID-scoped fictional patient fixtures and a
  temporary case table. Its `finally` cleanup and manifest are required parts
  of the process.

### Retention

No automated retention schedule exists for PostgreSQL, Qdrant, `/tmp` uploads,
or service logs. Owners must define retention before using any non-synthetic
data. UI chat is ephemeral, but operating-system/device caches may temporarily
retain selected media and audio.

### Backup and restore

For a formal test or before migrations:

```powershell
pg_dump "$env:DATABASE_URL" --format=custom --file .\c3a-development.backup
```

Store backups outside Git in encrypted, access-controlled storage and test
restore into a separate database. Use the Qdrant provider's collection snapshot
facility and record the snapshot identifier/hash with AI evaluation results.
The current evaluation tooling records a collection name but does not capture
an immutable Qdrant snapshot.

### Deletion

Many visit-child tables use `ON DELETE CASCADE`, but the application exposes no
general patient/export/deletion API. Deletion is an administrator-controlled
database operation and must be tested against foreign keys and audit-retention
requirements. The evaluation runner may delete only fixtures it created and
verifies batch ownership before changing them.

## 7. Privacy and security controls

- Use synthetic data only; never put names, recordings, images, addresses, or
  health information from real people into this prototype.
- Keep `.env`, backups, logs, raw PDFs, model files, and evaluation outputs out
  of Git unless explicitly reviewed and sanitised.
- Rotate PostgreSQL, Qdrant, and Tavily credentials that appeared in earlier
  repository revisions. Cleaning the current files is not sufficient because
  Git history and existing clones can retain them.
- The API has permissive CORS and no token-based authentication. It checks a
  claimed worker ID/role against visit assignment for sensitive workflows, but
  that is authorisation logic, not proof of identity.
- Local services use plain HTTP. Bind them to loopback or a trusted development
  network only.
- `DEBUG_BACKEND=true` can log payload previews. Even normal logs include some
  user-query previews and identifiers; treat logs as sensitive.
- Base64 bodies are redacted by the logging helper, and the database health
  checker masks the connection URL/password in returned errors.
- Outputs from an LLM, RAG retrieval, translation, web search, and speech
  recognition require human verification before they enter a care record.

## 8. Data access checklist

Before sharing data or results, record:

1. data owner and purpose;
2. synthetic/real-data classification;
3. database and Qdrant snapshot/version;
4. source PDF manifest and licences;
5. who has access and when it expires;
6. retention and deletion date;
7. model and embedding versions;
8. sanitisation of logs, paths, prompts, outputs, and credentials.

