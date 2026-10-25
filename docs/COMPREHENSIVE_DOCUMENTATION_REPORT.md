# Comprehensive Documentation

The C3A project is supported by a structured documentation set that enables a
new developer or assessor to understand, configure, run, and evaluate the
system. The repository-level `README.md` is the primary entry point. It explains
the purpose of the Clinical Context-Aware Consultation Assistant, its research
and safety boundaries, the system architecture, repository layout, core
features, quick-start procedure, normal usage workflow, and service health
checks. Three supporting guides provide greater technical detail:

- `docs/DEVELOPMENT.md` describes dependencies, environment variables,
  PostgreSQL preparation, Qdrant ingestion, Ollama configuration, the optional
  speech container, startup order, and troubleshooting.
- `docs/DATA_MANAGEMENT.md` describes project inputs and outputs, storage
  locations, database ownership, RAG provenance, retention, backup, deletion,
  privacy, and access controls.
- `docs/TESTING.md` documents automated tests, PostgreSQL integration tests,
  the 180-case AI evaluation framework, verified results, release checks, and
  known limitations.

The documentation reflects the implemented three-layer architecture. The
React Native/Expo user interface communicates only with the FastAPI gateway.
The gateway provides the frontend-facing API and owns the persistent visit
workflow, while a second FastAPI service performs request routing, local Ollama
generation, PostgreSQL patient-context retrieval, Qdrant retrieval-augmented
generation (RAG), optional web-resource retrieval, translation, risk analysis,
and speech-service integration. This separation allows the user interface,
business workflow, and AI functions to be understood and tested independently.

The documented user workflow begins with selecting a worker visit, confirming
arrival through GPS or a recorded manual override, reviewing the synthetic
patient context, and recording care-task and medication-support outcomes. A
worker can then ask patient-specific or guideline questions, review the
assistant's structured source references, action risk alerts, generate a draft
visit report, and complete the visit. Training materials can also be browsed or
searched independently. The documentation emphasises that generated content
and source retrieval must be reviewed by a human and that the prototype is not
clinically validated.

# Development Environment

The development environment can be reproduced using Python, Node.js, Ollama,
PostgreSQL, and, where required, Qdrant and Docker. Python 3.11 is recommended
because it matches the optional speech-service container. The Expo application
is installed with `npm ci` so that the committed `package-lock.json` is used.
The API and AI services use separate requirements files, and local secrets are
stored in ignored `.env` files copied from checked-in placeholder examples.

The normal setup sequence is:

1. Create a Python virtual environment under `c3a-core/.venv`.
2. Install `c3a-core-api/requirements.txt` and
   `c3a-core-ai/requirements.txt`.
3. Run `npm ci` in `c3a-core-ui`.
4. Copy each `.env.example` file to `.env` and supply development credentials.
5. Configure the same `DATABASE_URL` for the API and AI services.
6. Start Ollama and pull the configured model, currently `llama3.1:8b`.
7. Configure Qdrant and ingest the approved PDF sources when RAG is required,
   or explicitly disable RAG for a non-RAG development run.
8. Start the AI service on port 8001, the API gateway on port 8000, and the Expo
   development server.

The PostgreSQL setup requires an existing synthetic `c3a_synthea_*` schema.
The C3A migrations then add operational tables for workers, profiles, shifts,
visits, care tasks, location snapshots, events, medication-support records,
risk alerts, alert actions, and training resources. The SQL files must be
applied in numerical order on a new disposable development database. Several
seed and catalogue migrations contain deliberate reset or replacement
operations, so the documentation requires a backup and migration review before
they are applied to an existing database.

The optional speech environment is reproducible through
`c3a-core/docker-compose.speech.yml` and `c3a-core-ai/Dockerfile.speech`. The
container installs Python 3.11, FFmpeg, and the speech dependencies, and mounts
Omnilingual ASR and Silero VAD model files from a read-only host directory. It
binds the speech endpoint to `127.0.0.1:8002`, preventing accidental public
exposure during development.

At present, the API, AI, Ollama, PostgreSQL, and Qdrant components are not
packaged as one full-stack Docker environment. Python dependencies also use
version ranges rather than a fully locked dependency file. Therefore, formal
test runs should record the operating system, Python version, installed Python
packages, Node/npm versions, Ollama model digest, embedding model, PostgreSQL
schema revision, and Qdrant collection snapshot. A full-stack Compose file and
locked Python dependency set would further improve reproducibility.

# Data Management

The project uses synthetic data and separates operational data, patient
context, knowledge documents, and transient user-interface data. PostgreSQL is
the source of truth for persistent visit operations and synthetic patient
records. The `c3a_app_*` tables store workers, shifts, visits, tasks, locations,
events, medication-support records, risk alerts, alert actions, and the training
catalogue. The pre-existing `c3a_synthea_*` tables store synthetic demographics,
cultural and language profiles, conditions, medications, allergies,
encounters, and observations.

Qdrant stores embedded chunks extracted from approved PDF documents. Each
vector payload includes the chunk text, document and content hashes, source
title, filename, source path, document type, language, page range, section
heading, chunk index, and ingestion timestamp. This metadata enables a
generated answer to return a structured citation that can be checked against
the original document. The PDFs themselves are external project inputs and
should be maintained in a controlled source archive with publisher, version,
licence, checksum, and ingestion information.

The main input and output data are summarised below.

| Category | Inputs | Outputs and storage |
|---|---|---|
| Visit workflow | worker/visit IDs, task outcomes, medication-support status, notes, alert actions | PostgreSQL scenario state and auditable visit events |
| Location | GPS coordinates, accuracy, permission state, manual-override reason | PostgreSQL location snapshot; server-derived distance and location-risk alert |
| AI assistant | chat text, current patient/worker/visit/task/risk context, retrieved evidence | answer text, streaming tokens, source references; chat remains in UI memory |
| Patient summary | synthetic PostgreSQL clinical rows | generated summary and structured record references |
| Training and RAG | catalogue SQL, resource links, approved PDFs, optional allow-listed web results | training responses, task-linked resources, Qdrant chunks and citations |
| Speech | temporary audio, language, and speaker role | transcript returned to the UI; speech service is designed as non-persistent |
| Visit report | care-outcome form, vitals, tasks, events, alerts, and patient context | draft report; stored as a visit-completion event note only when submitted |
| Evaluation | 180 synthetic case specifications and temporary fictional fixtures | response JSONL, judge output, manifests, and reports under ignored `evaluation/results/` |

The UI uses the latest server response as the authoritative scenario and does
not convert a failed write into a local success. Chat history and pending
attachments are currently memory-only. One legacy `/upload` endpoint writes a
decoded file to the host `/tmp` directory and returns a nominal file URL, but
there is no corresponding static-file route or automatic cleanup policy. This
endpoint is documented as unmanaged and should be disabled or redesigned
before broader deployment.

Project data must not include real patient information. The prototype has no
token-based authentication, uses permissive CORS, and communicates over plain
HTTP during local development. Some workflow endpoints compare the supplied
worker identity and role with database assignments, but this is authorisation
logic rather than proof of identity. Logs may contain identifiers and shortened
user-query previews, particularly when backend debug logging is enabled.
Consequently, services must remain on loopback or a trusted development
network, logs and backups must be access controlled, and AI, speech,
translation, web-search, and retrieval outputs require human verification.

The repository previously contained live development credentials in tracked
files. The current examples use placeholders; however, old values may remain in
Git history and existing clones. All affected PostgreSQL, Qdrant, and
web-search credentials must be rotated, and repository-history remediation
should be considered before the project is shared further.

# Testing & Quality

Testing is divided into deterministic software tests, database integration
tests, static frontend checks, and probabilistic AI evaluation. API tests cover
chat-source forwarding, checklist monitoring, location calculations,
medication-risk rules, visit access, risk-alert lifecycle behaviour, training
schemas, and visit-date validation. AI tests cover routing, database/RAG
orchestration, structured current-record answers, Ollama prompts and parsing,
risk-analysis safeguards, Qdrant client lifecycle, speech processing, and
web-result filtering. Strict TypeScript compilation provides the current
frontend static check.

The PostgreSQL integration tests are deliberately opt-in through
`RUN_POSTGRES_INTEGRATION_TESTS=1`. They verify persisted checklist and
medication alerts, location-alert resolution, database role/visit-assignment
rules, multilingual training resources, search behaviour, and migration
idempotency. These tests must be run against a dedicated development or test
database rather than production data.

The AI evaluation contains 180 synthetic cases across six domains: mobility,
medication support, risk state, workflow state, communication, and
identity/missing data. It includes 36 baseline cases, 36 relevant-context
changes, 36 irrelevant changes, 36 context-omitted controls, and 12 three-turn
sequences containing 36 multi-turn requests. The case validator confirms the
pairing, uniqueness, controlled changes, and request structure before any
endpoint calls are made.

The larger project evaluation reported HTTP 200 responses for all 180 requests
and showed that the targeted stale multi-turn current-record behaviour was
repaired for the 24 affected update follow-ups. This improvement is narrow and
does not establish general context awareness or clinical safety. The evaluation
also identified continuing risks: listed medicines may be described as if they
are confirmed as taken; declined medication support may be over-interpreted;
missing context can become an incorrect definite statement or invented patient
fact; interpreter requirements can be omitted or overstated; and retrieved
evidence can be only partially relevant to the generated advice. In addition,
the repaired current-record path can state the current value but cannot prove
the exact change from an earlier structured snapshot because the request
contains only the latest snapshot.

The repository was checked on 20 October 2026 with the following result:

| Check | Result |
|---|---|
| API unit-test discovery | 52 tests: 41 passed and 11 opt-in PostgreSQL tests skipped |
| AI unit-test discovery | 67 tests: 66 passed and one environment error because `qdrant_client` was not installed in the active interpreter |
| Frontend strict TypeScript check | Passed |
| Evaluation case validation | Passed for all 180 unique specifications |
| Evaluation dry run | Passed: 180 cases arranged into 156 execution units; no HTTP requests sent |

The missing Qdrant package is included in the AI requirements and the AI suite
must be rerun inside a correctly prepared virtual environment before it is
considered fully green. Live PostgreSQL, Ollama, Qdrant, Tavily, speech, and
end-to-end Expo tests were outside that verification pass.

The principal known quality limitations are the absence of frontend
unit/component/end-to-end tests, no continuous-integration workflow, no code
coverage threshold, range-based rather than locked Python dependencies, no
database migration ledger, fixed-date demo visits, memory-only chat history,
and missing versioned raw evaluation outputs and source PDFs. Model-based
judging is also not sufficient as the sole pass/fail authority because the
generator and judge can share correlated errors; earlier calibration detected
false-negative judgments. A release-quality assessment should therefore use a
clean environment, run deterministic and integration tests, execute the AI
regression set against versioned data and model snapshots, perform target-device
UI testing, scan both the working tree and Git history for secrets, and obtain
independent domain-expert review for safety-critical behaviour.

