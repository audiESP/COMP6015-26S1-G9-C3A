# C3A Core

Clinical Context-Aware Consultation Assistant split into three HTTP-connected
layers:

- `c3a-core-ui`: React Native / Expo frontend.
- `c3a-core-api`: FastAPI gateway used by the frontend.
- `c3a-core-ai`: FastAPI AI service for local Ollama inference and Qdrant RAG.

The UI only calls the API layer. The API layer calls the AI layer over HTTP. The
AI layer owns model inference, retrieval, citations, and PDF ingestion scripts.

## Configuration

Create local `.env` files from the checked-in examples. Do not commit real
secrets.

```bash
cp c3a-core-ui/.env.example c3a-core-ui/.env
cp c3a-core-api/.env.example c3a-core-api/.env
cp c3a-core-ai/.env.example c3a-core-ai/.env
```

Set `QDRANT_URL` and `QDRANT_API_KEY` in `c3a-core-ai/.env`.

The AI layer calls a local Ollama instance and uses `llama3.1:8b` by default.
Install and start the model before launching the AI service:

```bash
ollama pull llama3.1:8b
ollama serve
```

Set `OLLAMA_BASE_URL` and `OLLAMA_MODEL` in `c3a-core-ai/.env` when Ollama is
running on a different address or a different text model should be used. The
default `llama3:latest` model does not accept image or document attachments.

Set `DATABASE_URL` in `c3a-core-api/.env` to connect the API gateway to Neon
PostgreSQL. Use the connection string from the Neon console and keep
`sslmode=require` enabled. Do not commit real database credentials.

```bash
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DB?sslmode=require&channel_binding=require
```

The current API integration only checks database connectivity through
`GET /health`; it does not create tables or store chat data.

## Local Startup

Use three terminals from the project root.

### AI Layer

```bash
cd c3a-core-ai
../.venv/bin/python -m main
```

The AI service runs on `http://127.0.0.1:8001` by default.

### API Layer

```bash
cd c3a-core-api
../.venv/bin/python -m main
```

The API gateway runs on `http://127.0.0.1:8000` by default.

### UI Layer

```bash
cd c3a-core-ui
npm install
npx expo start
```

The frontend calls `EXPO_PUBLIC_API_BASE_URL`, which defaults to
`http://127.0.0.1:8000`.

## Training resources

Training topics and materials are stored in PostgreSQL. Apply migrations
`005` through `010` in order when setting up a new training catalogue. For an
existing catalogue through `008`, apply `009` and `010` together in a transaction
before starting the updated API. If `009` is already applied, apply only
`c3a-core-api/migrations/010_training_resources_in_existing_materials.sql`.
Do not replay the earlier catalogue-reset migrations on an existing database.
Migration `010` restores the original CPR file and excerpt replaced by `009`,
then groups related resources on the original CPR, falls, manual handling and
hand hygiene pages. It can be reapplied without duplicating resources.

Original materials keep their IDs, titles, excerpts, sources, file URLs and
reading times. Each of the four supplemented pages has one new summary paragraph
introducing its original material and additional resources together.
The additional `resource_links` JSON array is returned as `resourceLinks` by
both the topic-materials and search endpoints. Each link has `title`, `url`,
`language` (BCP 47) and `type` (`pdf` or `link`). Related PDFs, official resource
pages and translations appear together on one material detail page. Link titles
use the document's language, and native-language titles are searchable. The
pressure injury material contains all nine supplied language versions.

New entries use descriptive summaries and links to the original publications.
Their `body` is empty, so summaries are not labelled as verbatim quotations.
Original source buttons remain visible alongside a separate resource section.
When a new material already lists its source URL as a resource, the same link is
not repeated. The five new pages cover mealtimes, worker resources, the Code of
Conduct and the grouped pressure injury translations.

To verify the migration and API against PostgreSQL, run from `c3a-core-api` in
PowerShell:

```powershell
$env:RUN_POSTGRES_INTEGRATION_TESTS = '1'
python -m unittest discover -s tests -p test_training_resources.py -v
```

These checks use a separate schema inside a rolled-back transaction and leave
the application catalogue untouched.
