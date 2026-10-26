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

- [Comprehensive technical documentation](docs/C3A_Comprehensive_Technical_Documentation.docx) — consolidated Word report covering the documentation set, architecture, development environment, data management, testing, deployment infrastructure, future work, and handover guidance.
- [Development environment](docs/DEVELOPMENT.md) — prerequisites, configuration,
  database setup, RAG ingestion, speech container, startup, troubleshooting,
  deployment boundaries, and reproducibility.
- [Data management](docs/DATA_MANAGEMENT.md) — data inventory, ownership, flow,
  persistence, migrations, backup, deletion, privacy, and security boundaries.
- [Testing and quality](docs/TESTING.md) — automated checks, the 180-case AI
  evaluation, the latest verification snapshot, known limitations, and
  recommendations for the next development team.

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
├── tools/
│   └── sync_env.py        Environment validation and synchronization
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
```

> **Required — provide your own API keys and credentials:** the launchers never
> generate or supply credentials. Configure `DATABASE_URL` in both backend
> environments and configure `QDRANT_URL`, `QDRANT_API_KEY`, and
> `TAVILY_API_KEY` for the AI environment.

Every launcher applies the following environment-file rules before installing
packages or starting a service:

1. It discovers every `.env.example`/`.env` pair in the repository and validates
   the available files' syntax and key schema.
2. If every `.env` contains every key from its example and all required private
   values are configured, startup continues immediately. Differences from
   `.env.example` do not overwrite an already complete `.env`.
3. If any `.env` is missing or incomplete, all example credentials are checked.
   Keys ending in `API_KEY`, `TOKEN`, `SECRET`, or `PASSWORD`, plus
   `DATABASE_URL` and `QDRANT_URL`, must not be empty, too short, or placeholder
   values. One invalid example value causes a warning and aborts startup before
   any file is copied.
4. If all required example values are configured, each missing or incomplete
   `.env` is atomically replaced from its matching `.env.example`. An existing
   file is first backed up as `.env.pre-sync.bak`.
5. Malformed entries, duplicate keys, unmatched files, read failures, backup
   failures, and copy failures stop startup and display the exact reason.

> **Security warning:** `.env.example` files are tracked by Git. Prefer keeping
> real secrets only in the ignored `.env` files. If you temporarily configure an
> example so it can repair an incomplete `.env`, never stage or commit that
> example; restore its placeholder values afterward. Never use another
> developer's credentials. `.env`, `.env.pre-sync.bak`, and temporary sync files
> are ignored by Git.

The checked-in demo visits are dated `2026-09-04`. Keep
`EXPO_PUBLIC_SHIFT_DATE=2026-09-04` while using that seed data.

### 3. Start all services

Run the launcher for your operating system from the repository root. Its
preflight validates Python, pip, Node.js, npm, and Ollama and applies the
environment rules above. It then installs the API and AI Python requirements
with:

```text
python -m pip install -r c3a-core/c3a-core-api/requirements.txt
python -m pip install -r c3a-core/c3a-core-ai/requirements.txt
```

For the UI, the launcher runs `npm ls --depth=0` to validate the existing
environment. If `node_modules` is missing or invalid, it runs `npm ci` using the
checked-in lockfile; if no lockfile exists, it falls back to `npm install`.
Only after these dependency steps succeed does it start or reuse the Ollama
server, pull `llama3.1:8b-instruct-q4_K_M` when missing, and start the AI, API,
and Expo UI services. A failed dependency installation stops the launch.

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
check environment completeness, report any synchronization that a normal run
would perform, and check commands, files, pip, and UI dependencies without
copying or installing anything, starting services, or downloading the model.

#### Using `.env` files kept outside the repository

Any launcher also accepts a folder that holds your `.env` files in the same
layout as the repository:

```text
my-secrets/
└── c3a-core/
    ├── c3a-core-ai/.env
    ├── c3a-core-api/.env
    └── c3a-core-ui/.env
```

```bash
./start-macos.command /path/to/my-secrets
./start-linux.sh /path/to/my-secrets
```

```powershell
.\start-windows.bat C:\path\to\my-secrets
```

Before the normal validation runs, every `.env` in that folder is checked
against its `.env.example`; a missing file or key stops startup without
changing anything. Valid files are then copied into the repository, and any
different existing `.env` is first backed up as `.env.pre-sync.bak`. Combine
it with `--check` (for example `./start-macos.command --check /path/to/my-secrets`)
to validate the folder without copying.

If environment validation or synchronization fails, a required command,
entrypoint, requirements file, or package environment is missing, or an
installation, Ollama startup, or model download fails, the launcher stops and
displays the specific reason. Windows uses a system warning dialog and macOS
uses a native alert. Linux uses `zenity` or `kdialog` when available, with
`notify-send` as a desktop-notification fallback. Headless Linux environments
always receive the same error in the terminal because no GUI is available.

#### macOS: step-by-step startup with the iOS Simulator

Requires Xcode with the iOS Simulator, Expo Go installed in the simulator,
Ollama, Node.js, and Python 3.11 or newer. For the simulator, set
`EXPO_PUBLIC_API_BASE_URL=http://127.0.0.1:8000` in the UI `.env`, because the
simulator reaches services on the Mac through `127.0.0.1`.

Terminal 1, from the repository root:

```bash
cd c3a-core
python3 -m venv .venv && source .venv/bin/activate
pip install -r c3a-core-api/requirements.txt -r c3a-core-ai/requirements.txt
cd c3a-core-ui && npm ci && cd ../..
bash ./start-macos.command /path/to/my-secrets
```

The launcher picks up `c3a-core/.venv` automatically and keeps running in the
foreground; wait until Expo reports that Metro is running on port 8081. Omit
the folder argument if the `.env` files are already in the repository.

Terminal 2, after the services have started:

```bash
open -a Simulator
xcrun simctl openurl booted exp://127.0.0.1:8081
```

Wait for the simulator to finish booting before running `openurl`. Optionally,
set the simulator's location to the visit's planned coordinates so the check-in
location check passes:

```bash
xcrun simctl location booted set <latitude>,<longitude>
```

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
The committed versions of `.env.example` files must contain placeholders; any
local real values used for repair must never be staged or committed. Removing a
value from the working tree does not remove it from Git history. Project owners
must rotate all previously exposed PostgreSQL, Qdrant, and web-search
credentials before further use and use a history-rewriting process if the
repository is shared.
