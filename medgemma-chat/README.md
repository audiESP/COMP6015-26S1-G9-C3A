# C3A Core

Clinical Context-Aware Consultation Assistant split into three HTTP-connected
layers:

- `c3a-core-ui`: React Native / Expo frontend.
- `c3a-core-api`: FastAPI gateway used by the frontend.
- `c3a-core-ai`: FastAPI AI service for MedGemma inference and Qdrant RAG.

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

