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

The AI layer calls a local Ollama instance and uses `llama3:latest` by default.
Install and start the model before launching the AI service:

```bash
ollama pull llama3
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
