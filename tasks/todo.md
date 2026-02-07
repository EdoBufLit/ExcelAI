# MVP Plan - Excel AI Transformer

## Objectives
- Build a deploy-ready MVP with FastAPI backend and React frontend.
- Support secure AI-guided spreadsheet transformations for CSV/XLSX files.
- Enforce free-tier limit of 5 transformations per user.

## Checklist
- [x] Scaffold monorepo structure (`backend/`, `frontend/`, shared docs).
- [x] Implement backend API: upload, schema analysis, LLM plan generation, safe transform apply, result preview/download.
- [x] Implement free usage limiter (5 uses) with persistent local storage.
- [x] Implement robust transformation engine with strict operation allowlist.
- [x] Build React UI flow: upload -> inspect -> prompt -> plan -> preview -> download.
- [x] Add configuration, env examples, and deployment artifacts (Docker + compose).
- [x] Add tests for critical backend flows (usage limit + transformation safety).
- [x] Run validation checks and update this file with review results.

## Review
- Backend tests passed: `python -m pytest backend/tests` (4 tests, all passed).
- Frontend build passed: `npm run build` in `frontend/`.
- Security posture in MVP scope:
  - Transformation engine uses strict allowlist and rejects unsupported operation types.
  - No eval/dynamic code execution in transformation flow.
  - Upload accepts only `.csv` and `.xlsx`.
- Free tier limit enforced with persistent SQLite usage store (5 uses by `user_id`).
- LLM planner:
  - Uses OpenAI API when `OPENAI_API_KEY` is set.
  - Falls back to deterministic local heuristic planner otherwise.
- UX increment (confirmation flow):
  - Added pre-apply confirmation screen with LLM plan summary, step-by-step impacts, and impacted columns.
  - Added preview endpoint (`/api/transform/preview`) returning max 10 rows without consuming free-tier usage.
  - Apply action is disabled when preview is unavailable.
- Product increment (quick presets):
  - Added configurable JSON preset catalog for prompt templates.
  - Added React preset component above prompt with tooltip descriptions and editable prefilled prompt behavior.
- Growth increment (free usage visibility):
  - Added persistent remaining-uses badge (`X / 5 elaborazioni rimaste`) with sticky visibility.
  - Added realtime refresh after each transformation job.
  - Added limit-reached state with execution block and "Passa al piano Pro" CTA.
- Data increment (business analytics logging):
  - Added local SQLite analytics schema (`analytics_events`) for transformation jobs.
  - Added backend hook in `/api/transform` capturing type, file size, processing time, status/error, and plan tier placeholder.
  - Added analysis query examples in `backend/docs/analytics.md`.
- AI product increment (ambiguity handling):
  - Extended LLM planner system prompt to return clarification state when prompt is ambiguous.
  - Added API contract fields (`needs_clarification`, `clarification_question`) and blocked preview/apply execution on ambiguity.
  - Added frontend clarification UI state with explicit question and execution lock until prompt is clarified.
- UX writing increment (human result summary):
  - Added frontend function that converts transformation plan into a non-technical explanation.
  - Output is capped at 3 bullet points and shown in final result section.
- UX increment (error message quality):
  - Added explicit map error -> human UI message with next-step suggestion.
  - Removed technical raw error exposure from API layer and added fallback safe generic messaging.
  - Added friendly handling for invalid JSON plan editing in preview/apply flow.
- Reliability increment (stream + provider compatibility):
  - Fixed frontend response error handling to read response body exactly once and parse JSON safely.
  - Added OpenAI-compatible base_url support with LLM/OpenAI/Kimi env aliases, without breaking existing OPENAI_* configuration.
- Residual note:
  - Python 3.14 emits deprecation warnings from FastAPI/Starlette/OpenAI dependencies, but functional tests pass.
