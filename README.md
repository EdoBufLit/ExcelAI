# Excel AI Transformer (MVP)

MVP web app per trasformare file Excel/CSV con piano JSON generato da LLM e applicazione sicura lato backend.

## Stack
- Backend: FastAPI + Python + pandas
- Frontend: React + Vite
- File supportati: `.xlsx`, `.csv`
- LLM: provider OpenAI-compatible (OpenAI/Kimi) con fallback locale se API key non impostata

## Funzionalita MVP
- Upload file Excel/CSV
- Analisi struttura dataset (colonne, tipi, preview)
- Prompt utente per trasformazioni
- Preset rapidi sopra il prompt con tooltip descrittivo e testo modificabile
- Generazione piano di trasformazione JSON via LLM
- Gestione ambiguita: richiesta chiarimento prima di qualsiasi esecuzione
- Applicazione sicura (allowlist operazioni, no codice arbitrario)
- Preview risultato
- Download file trasformato
- Limite free: massimo 5 trasformazioni per `user_id`

## Struttura progetto
```text
backend/
  app/
    main.py
    config.py
    models.py
    routers/transform.py
    services/
      analyzer.py
      file_store.py
      llm_planner.py
      transformer.py
      usage_limiter.py
  tests/
frontend/
  src/
docker-compose.yml
```

## Backend local setup
```bash
cd backend
python -m venv .venv
. .venv/Scripts/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

### Config LLM (OpenAI + Kimi compatible)
- Variabili consigliate (future-proof): `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`
- Compatibilita legacy mantenuta: `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL`
- Alias Kimi supportati: `KIMI_API_KEY`, `KIMI_MODEL`, `KIMI_BASE_URL`

## Frontend local setup
```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

Frontend default: `http://localhost:5173`  
Backend default: `http://localhost:8000`

## Run con Docker Compose
```bash
copy .env.example .env
docker compose up --build
```

## Endpoint principali backend
- `POST /api/files/upload` -> upload + analisi iniziale
- `POST /api/plan` -> genera piano JSON da prompt
  - include `needs_clarification` e `clarification_question` se il prompt e ambiguo
- `POST /api/transform/preview` -> preview risultato + summary/steps prima della conferma finale
- `POST /api/transform` -> applica piano e salva output
- `GET /api/results/{result_id}/download` -> download file risultato
- `GET /api/usage/{user_id}` -> consumo attuale + residuo

## Operazioni trasformazione supportate
- `rename_column`
- `drop_columns`
- `fill_null`
- `cast_type`
- `trim_whitespace`
- `change_case`
- `derive_numeric`
- `filter_rows`
- `sort_rows`

## Test backend
```bash
cd backend
pytest
```

## Analytics usage logging
- Eventi business sono salvati localmente in SQLite (`analytics_events`).
- Dettagli schema + query in `backend/docs/analytics.md`.
