# C3A — Clinical Context-Aware Consultation Assistant

C3A is a Curtin University COMP6015 project that prototypes a context-aware
assistant for home-care workers. It combines a React Native/Expo application,
a FastAPI application gateway, a separate AI service, PostgreSQL operational
and synthetic patient data, Qdrant retrieval, local Ollama inference, and an
optional local speech-to-text service.

> **Research prototype:** the repository is designed for synthetic/demo data.
> It is not clinically validated, is not a medical device, and must not be used
> to make unsupervised care decisions or to store real patient information.

## Comprehensive documentation

- [Development environment](docs/DEVELOPMENT.md) — prerequisites, configuration,
  database setup, RAG ingestion, speech container, startup, and troubleshooting.
- [Data management](docs/DATA_MANAGEMENT.md) — data inventory, ownership, flow,
  persistence, migrations, backup, deletion, privacy, and security boundaries.
- [Testing and quality](docs/TESTING.md) — automated checks, the 180-case AI
  evaluation, the latest verification snapshot, and known limitations.

## System architecture

```text
React Native / Expo UI (c3a-core-ui)
                 |
                 | HTTP / NDJSON streaming
                 v
FastAPI gateway (c3a-core-api) ----------> PostgreSQL
                 |                         operational + synthetic data
                 | HTTP
                 v
FastAPI AI service (c3a-core-ai) --------> Ollama (local LLM)
        |             |          |
        |             |          +-------> optional Tavily search
        |             +------------------> Qdrant knowledge vectors
        +--------------------------------> local speech container
```

The UI calls only the API gateway. The gateway owns the frontend-facing
contract and persistent visit workflow. The AI service routes each request to
synthetic patient records, the guideline knowledge base, both, or direct local
generation, then returns the answer with structured source references.

### Main capabilities

- Worker visit queue, calendar, check-in/check-out, and location verification.
- Patient care-preference updates and synthetic clinical-record summaries.
- Care-task, medication-support, risk-alert, and audit-event workflows.
- Context-aware chat, streaming answers, citations, translation, and visit
  report generation.
- Searchable training topics and task-linked learning materials.
- Optional on-device recording with a locally hosted speech recogniser.

## Repository layout

```text
.
├── README.md
├── start-windows.bat     Windows one-click launcher
├── start-linux.sh        Linux launcher
├── start-macos.command   macOS launcher
├── docs/
│   ├── DEVELOPMENT.md
│   ├── DATA_MANAGEMENT.md
│   └── TESTING.md
└── c3a-core/
    ├── c3a-core-ui/       Expo / React Native client
    ├── c3a-core-api/      FastAPI gateway, repositories, SQL migrations, tests
    ├── c3a-core-ai/       AI routing, Ollama, RAG, speech, evaluation, tests
    └── docker-compose.speech.yml
```

## Quick start

The root launchers start Ollama, the AI service, the API, and the UI on Windows,
Linux, or macOS. See the [development guide](docs/DEVELOPMENT.md) for full
database, RAG, speech, and troubleshooting details.

### 1. Install prerequisites

- Python 3.11 and `venv` (also used by the speech image).
- Node.js and npm; use `npm ci` with the checked-in lockfile.
- Ollama with the configured model.
- Access to a development PostgreSQL database containing the prerequisite
  `c3a_synthea_*` schema.
- Qdrant credentials if RAG is enabled.
- Docker only if local speech recognition is required.

### 2. Install dependencies and create local configuration

From the repository root:

```powershell
Set-Location c3a-core
py -3.11 -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r .\c3a-core-api\requirements.txt
python -m pip install -r .\c3a-core-ai\requirements.txt

Set-Location .\c3a-core-ui
npm ci
Set-Location ..

Copy-Item .\c3a-core-api\.env.example .\c3a-core-api\.env
Copy-Item .\c3a-core-ai\.env.example .\c3a-core-ai\.env
Copy-Item .\c3a-core-ui\.env.example .\c3a-core-ui\.env
```

> **Required — provide your own API keys and credentials:** before starting the
> application, open the copied `.env` files and replace the example values with
> credentials from your own accounts. The launchers do not create, supply, or
> validate API keys for you.

At minimum, set your own `DATABASE_URL` in both backend `.env` files. In
`c3a-core/c3a-core-ai/.env`, set your own `QDRANT_URL` and `QDRANT_API_KEY` when
RAG is enabled, and set your own `TAVILY_API_KEY` when web search is enabled.
Alternatively, disable integrations for which you do not have credentials, for
example with `CHAT_RAG_ENABLED=false`; leaving `TAVILY_API_KEY` empty disables
Tavily web search. Never use another developer's credentials and never commit
local `.env` files.

The checked-in demo visits are dated `2026-09-04`. Keep
`EXPO_PUBLIC_SHIFT_DATE=2026-09-04` while using that seed data.

### 3. Start all services

Run the launcher for your operating system from the repository root. Each
launcher checks Python, npm, and Ollama; starts the Ollama server when needed;
pulls `llama3.1:8b-instruct-q4_K_M` when it is missing; and then starts the AI,
API, and Expo UI services.

Windows:

```powershell
.\start-windows.bat
```

Linux:

```bash
chmod +x ./start-linux.sh
./start-linux.sh
```

macOS:

```bash
chmod +x ./start-macos.command
./start-macos.command
```

The first run can take time because the model download is about 4.9 GB. An
already-running Ollama server is reused. On Linux and macOS, press `Ctrl+C` to
stop the processes started by the launcher. Add `--check` to any launcher to
run its checks without starting services or downloading the model.

### 4. Manual startup (optional)

To start everything manually, first run Ollama:

```powershell
ollama pull llama3.1:8b-instruct-q4_K_M
ollama serve
```

The launchers set `OLLAMA_MODEL` for the AI process. For manual startup, set
`OLLAMA_MODEL=llama3.1:8b-instruct-q4_K_M` in
`c3a-core/c3a-core-ai/.env`. Then open three terminals from `c3a-core`:

```powershell
# Terminal 1: AI service — http://127.0.0.1:8001
Set-Location .\c3a-core-ai
& ..\.venv\Scripts\python.exe -m main
```

```powershell
# Terminal 2: API gateway — http://127.0.0.1:8000
Set-Location .\c3a-core-api
& ..\.venv\Scripts\python.exe -m main
```

```powershell
# Terminal 3: Expo UI
Set-Location .\c3a-core-ui
npm start
```

Confirm the backend from another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health | ConvertTo-Json -Depth 6
```

Interactive API schemas are available at:

- `http://127.0.0.1:8000/docs` — frontend-facing API.
- `http://127.0.0.1:8001/docs` — internal AI API.

For a physical phone, `127.0.0.1` points to the phone. Set
`EXPO_PUBLIC_API_BASE_URL` to the development computer's LAN address, for
example `http://192.168.1.20:8000`, and allow the port through the local
firewall. Do not expose either backend to the public internet.

## Basic usage

1. Open the app and select the seeded visit date and a visit.
2. Start the visit with GPS permission or a documented manual override.
3. Review the patient, record task and medication-support outcomes, and action
   any risk alerts.
4. Ask the assistant patient-specific or guideline questions; inspect the
   returned source references rather than treating generated text as fact.
5. Generate and review the visit report, then finish the visit.
6. Use the Training area to browse database-backed learning materials.

All successful workflow writes are returned as a new authoritative scenario
snapshot. The UI does not treat a failed request as a local success.

## Development environment

The application services currently run natively; the optional speech service
is reproducible through `c3a-core/docker-compose.speech.yml`. Python dependency
files use version ranges rather than a lockfile, while the UI has a committed
`package-lock.json`. Exact setup and container instructions are in
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Data management

PostgreSQL is the source of truth for visit workflow, training content, and the
synthetic Synthea patient dataset. Qdrant stores embedded PDF chunks and their
citation metadata. Chat history is currently in UI memory only; generated
visit reports are stored as visit-event notes when the visit is completed.
See [docs/DATA_MANAGEMENT.md](docs/DATA_MANAGEMENT.md) before changing,
exporting, or deleting data.

## Testing and quality

```powershell
# API unit tests; PostgreSQL tests skip unless explicitly enabled
Set-Location c3a-core\c3a-core-api
python -m unittest discover -s tests -v

# AI unit tests
Set-Location ..\c3a-core-ai
python -m unittest discover -s tests -v

# Frontend strict type check
Set-Location ..\c3a-core-ui
npx tsc --noEmit

# Validate the 180 synthetic AI cases without calling a service
Set-Location ..\c3a-core-ai
python evaluation\validate_cases.py
python evaluation\run_cases.py
```

The evaluation is a project-specific engineering test, not clinical
validation. Full commands, the current results, and unresolved quality risks
are recorded in [docs/TESTING.md](docs/TESTING.md).

## Security notice

Real service credentials were previously present in tracked development files.
The current examples contain placeholders, but removing a value from the
working tree does not remove it from Git history. Project owners must rotate
all previously exposed PostgreSQL, Qdrant, and web-search credentials before
further use and use a history-rewriting process if the repository is shared.
