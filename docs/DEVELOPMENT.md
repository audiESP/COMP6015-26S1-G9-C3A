# Development Environment

This guide reproduces the C3A development setup and explains which external
services are required. Commands are shown for Windows PowerShell because that
is the team's current environment; equivalent Bash commands are included where
they materially differ.

## 1. Component and port map

| Component | Directory or process | Default address | Required |
|---|---|---:|---|
| Expo UI | `c3a-core/c3a-core-ui` | Expo development URL | Yes |
| API gateway | `c3a-core/c3a-core-api` | `127.0.0.1:8000` | Yes |
| AI service | `c3a-core/c3a-core-ai` | `127.0.0.1:8001` | Yes |
| Ollama | external local process | `127.0.0.1:11434` | For generated answers |
| PostgreSQL | external/Neon | configured by `DATABASE_URL` | For visit and patient data |
| Qdrant | external/Qdrant Cloud | configured by `QDRANT_URL` | For RAG citations |
| Speech service | Docker Compose | `127.0.0.1:8002` | Optional |
| Tavily | external API | HTTPS | Optional training fallback |

Only the API gateway should be configured in the UI. The AI and speech
services are internal dependencies of the backend.

## 2. Toolchain

Recommended baseline:

- Git.
- Python 3.11 with `venv` and pip.
- Node.js/npm compatible with the checked-in Expo 57 application; install with
  `npm ci` to honour `package-lock.json`.
- PostgreSQL `psql` client for applying raw SQL migrations.
- Ollama and `llama3.1:8b`, unless another compatible text model is configured.
- Docker Desktop/Engine with Compose for speech recognition.

The repository does not contain a Python lockfile or a full-stack Docker image.
For reproducible results, record the Python version and the output of
`python -m pip freeze` with each formal test run. Do not commit secrets or a
virtual environment.

## 3. Install dependencies

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

Bash activation is `source .venv/bin/activate`; backend startup can then use
`../.venv/bin/python` from either service directory.

## 4. Configure environment files

```powershell
Copy-Item .\c3a-core-api\.env.example .\c3a-core-api\.env
Copy-Item .\c3a-core-ai\.env.example .\c3a-core-ai\.env
Copy-Item .\c3a-core-ui\.env.example .\c3a-core-ui\.env
```

The `.env` files are ignored by Git. The examples must contain placeholders
only.

### UI settings

| Variable | Purpose | Default/example |
|---|---|---|
| `EXPO_PUBLIC_API_BASE_URL` | API gateway visible to the device | `http://127.0.0.1:8000` |
| `EXPO_PUBLIC_WORKER_ID` | Seeded worker identity used by the prototype | `cw-001` |
| `EXPO_PUBLIC_SHIFT_DATE` | Initial date; needed to open fixed seed visits | `2026-09-04` |

Use the host computer's LAN IP for a physical device. Android emulators often
need a host alias instead of `127.0.0.1`; confirm the address for the chosen
emulator rather than changing backend code.

### API settings

The required values are `DATABASE_URL` and `C3A_AI_BASE_URL`. Pool sizes,
timeouts, the API port, upload size, and debug logging have documented defaults
in `c3a-core-api/.env.example`.

### AI settings

- `DATABASE_URL` enables patient-record context and should target the same
  development database as the API.
- `QDRANT_URL`, `QDRANT_API_KEY`, and `QDRANT_COLLECTION` enable the knowledge
  store. Use `CHAT_RAG_ENABLED=false` for a deliberate non-RAG development run.
- `OLLAMA_BASE_URL` and `OLLAMA_MODEL` select local generation.
- `TAVILY_API_KEY` is optional; an empty value disables web-search fallback.
- `SPEECH_SERVICE_URL` points to the optional local container.
- `DEBUG_BACKEND=true` logs request previews and should never be used with
  sensitive data.

## 5. Prepare PostgreSQL

The C3A migrations are **not a complete standalone database bootstrap**. They
reference pre-existing `c3a_synthea_*` tables and fixed synthetic patient UUIDs.
Obtain the synthetic Synthea schema/import from the project data owner before
running these migrations.

Use a dedicated development database. Migration `002` resets events, location
snapshots, risk alerts, and medication-support records for the seeded visits;
migrations `006` and `007` rebuild the training-material catalogue. Do not run
the full sequence against a database containing data that must be retained.

For a new disposable database with the prerequisite Synthea data:

```powershell
$env:DATABASE_URL = 'postgresql://USER:PASSWORD@HOST/DATABASE?sslmode=require'
Set-Location .\c3a-core-api
Get-ChildItem .\migrations\*.sql |
  Sort-Object Name |
  ForEach-Object { psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -f $_.FullName }
```

For an existing catalogue already at migration `008`, apply `009` and `010`
together:

```powershell
psql "$env:DATABASE_URL" -v ON_ERROR_STOP=1 -1 `
  -f .\migrations\009_training_material_resource_links.sql `
  -f .\migrations\010_training_resources_in_existing_materials.sql
```

If `009` is already applied, apply only `010`; it is designed to be reapplied
without duplicating grouped resources. There is no migration ledger, so record
applied filenames in deployment/change records.

## 6. Prepare Ollama and Qdrant

```powershell
ollama pull llama3.1:8b
ollama serve
```

With valid Qdrant configuration in `c3a-core-ai/.env`:

```powershell
Set-Location .\c3a-core-ai
& ..\.venv\Scripts\python.exe -m scripts.init_qdrant
& ..\.venv\Scripts\python.exe -m scripts.ingest_pdfs --input C:\path\to\pdfs --replace
```

PDFs are not bundled in this repository. `--replace` removes chunks with the
same source filename before inserting the newly extracted chunks. It does not
delete unrelated documents. Keep a source manifest containing file name,
publisher, version/date, checksum, licence, and ingestion time.

## 7. Optional speech container

The speech image installs FFmpeg and the Python speech dependencies, while
model files remain on the host and are mounted read-only. Expected layout:

```text
<models>/
├── omnilingual-asr/
│   ├── model.int8.onnx
│   └── tokens.txt
└── silero-vad/
    └── silero_vad.onnx
```

```powershell
$env:C3A_SPEECH_MODELS_DIR = 'C:\absolute\path\to\models'
docker compose -f .\docker-compose.speech.yml up --build
Invoke-RestMethod http://127.0.0.1:8002/health
```

The Compose file binds port 8002 to loopback only. Do not change this to a
public bind without authentication, TLS, request limits, and a privacy review.

## 8. Run and verify

Start Ollama first, then the AI service, API gateway, and UI as shown in the
root README. Expected checks:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/ai/health | ConvertTo-Json -Depth 6
Invoke-RestMethod http://127.0.0.1:8000/health | ConvertTo-Json -Depth 6
```

`status: ok` at the gateway does not mean every dependency is healthy; inspect
the nested `ai`, `database`, `rag`, and model fields.

## 9. Common problems

| Symptom | Likely cause and action |
|---|---|
| No visits appear | Use the seeded date `2026-09-04`, confirm worker `cw-001`, and verify migrations/data. |
| UI works in browser but not on phone | Replace loopback with the host LAN IP and check firewall/network isolation. |
| API returns 502 for AI operations | Start the AI service and confirm `C3A_AI_BASE_URL`. |
| AI health reports model unavailable | Start Ollama and pull the exact `OLLAMA_MODEL`. |
| Answers have no knowledge citations | Configure Qdrant, initialise the collection, ingest PDFs, and check `CHAT_RAG_ENABLED`. |
| Patient-specific answer lacks records | Configure AI `DATABASE_URL` and confirm the requested synthetic patient exists. |
| Speech returns unavailable | Start the speech container and validate the mounted model paths. |
| Attachment request is rejected | The default local Llama model is text-only; attachment analysis is not implemented. |

