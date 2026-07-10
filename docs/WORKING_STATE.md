# Working State — Construction Site AI (through Sprint 6)

**Last verified:** 2026-07-11
**Status:** Sprints 1–6 complete and working end-to-end. Sprint 7 (FastAPI REST API) not yet started.

This is a quick reference of everything that is **built and verified working** up to the end of Sprint 6. For deep architecture, see `docs/HANDOVER.md`, `docs/DATABASE_ARCHITECTURE.md`, and `docs/AI_SERVICES.md`.

---

## 1. The End-to-End Pipeline

A foreman's voice note becomes structured data and four business documents, all stored in PostgreSQL:

```
  🎙️  Audio file (.mp4 / .wav)
        │
        ▼  [Sprint 3]  speech/  — Faster Whisper (local, free)
  📝  Transcript (text + confidence)
        │
        ▼  [Sprint 4]  extraction/  — Groq LLM (llama-3.3-70b-versatile)
  🧱  ConstructionDailyLog (structured JSON, schema v1.0.0)
        │
        ├──────────────► [Sprint 6]  database/  — PostgreSQL persistence
        │                 DailyLogRepository.create_from_extraction_result()
        │
        ▼  [Sprint 5]  generation/  — Groq LLM
  📄  4 business documents:
        1. Daily Site Report      (contractor record)
        2. Customer Update        (client-facing email)
        3. Safety Toolbox Talk    (crew briefing)
        4. Material Reminder      (procurement list)
        │
        ▼  [Sprint 6]  database/  — GenerationRepository.create_from_service_output()
  🗄️  All outputs persisted to generation_outputs table
```

---

## 2. What Each Layer Does

| Sprint | Package | Responsibility | Key Tech | Status |
|--------|---------|----------------|----------|--------|
| 1 | `knowledge/` | Domain knowledge base + master schema | JSON Schema draft-07 | FROZEN |
| 2 | `dataset_generation_framework/` | Synthetic training data generation | Python | FROZEN |
| 3 | `speech/` | Audio → transcript | Faster Whisper (local) | FROZEN |
| 4 | `extraction/` | Transcript → structured log | Groq (free tier) | FROZEN |
| 5 | `generation/` | Log → 4 business documents | Groq (free tier) | FROZEN |
| 6 | `database/` | Persist everything | PostgreSQL 15 + SQLAlchemy 2.x + Alembic | COMPLETE |

**Free-only constraint honored:** Faster Whisper runs locally; Groq is the one approved free-tier cloud LLM. No paid APIs anywhere.

---

## 3. How To Run Each Piece (Verified Commands)

All commands run from the project root with the venv active.

### Transcribe audio → text
```powershell
python transcribe.py data\sample_audio\foreman_recording.wav --output-dir data\transcripts\raw --format json
```
> MP4 input must first be converted to WAV (Whisper can't decode MP4 directly). Conversion uses PyAV, which is already installed.

### Extract text → structured JSON
```powershell
python extract.py data\transcripts\raw\foreman_recording.json --output data\extracted\foreman_recording_extracted.json
```

### Check the Groq engine is reachable
```powershell
python extract.py --check
# → Engine available: provider=groq model=llama-3.3-70b-versatile
```

### Full end-to-end verification (extract → DB → generate → DB)
```powershell
python verify_sprint6.py
```

---

## 4. Database (Sprint 6) — Verified Live State

**PostgreSQL 15.18**, database `construction_site_ai`, port `5432`.

| Item | Value |
|------|-------|
| Tables | 27 (26 domain tables + `alembic_version`) |
| ORM | SQLAlchemy 2.x, `Mapped[T]` declarative style |
| Migrations | Alembic — `alembic upgrade head` builds all tables |
| Repositories | 12 typed repository classes (clean data-access layer) |
| Seed data | 25 trades, 22 construction stages, 16 material categories, 16 PPE types |
| Demo data | 1 company, 1 project, 3 workers, sample daily logs |

### Setup from scratch
```powershell
# 1. Create the database (one time)
$env:PGPASSWORD = "<your-postgres-password>"
& "C:\Program Files\PostgreSQL\15\bin\createdb.exe" -U postgres construction_site_ai

# 2. Build all tables from migrations
alembic upgrade head

# 3. Seed reference + demo data (run from a Python shell / script)
#    seed_all_reference_data(session)  then  seed_sample_data(session)
```

### Inspect data in pgAdmin
```sql
SELECT * FROM daily_logs ORDER BY created_at DESC;
SELECT trade, workers_count FROM log_trades_on_site WHERE daily_log_id = '<id>';
SELECT service_type, LEFT(content, 200) FROM generation_outputs WHERE daily_log_id = '<id>';
```

---

## 5. Configuration (`.env`)

Read by `DatabaseConfig`, `ExtractionConfig`, `GenerationConfig`, `SpeechProcessingConfig` (`.from_env()`). See `.env.example` for the full annotated list. The essentials:

```
GROQ_API_KEY=gsk_...                                  # required for extraction + generation
DATABASE_URL=postgresql://postgres:<pw>@localhost:5432/construction_site_ai
SPEECH_WHISPER_MODEL_SIZE=base                        # tiny|base|small|medium|large-v3
HF_HUB_OFFLINE=1                                      # load cached Whisper model, skip remote check
```
> In `DATABASE_URL`, a `@` in the password must be URL-encoded as `%40`.

---

## 6. Tests

```powershell
python -m pytest tests/ -q
```

**Last run: 718 passed, 1 skipped, 0 failures.**
All database tests use SQLite in-memory — no PostgreSQL required for CI.

---

## 7. Health Check (all green as of 2026-07-11)

| Layer | Check | Result |
|-------|-------|--------|
| Imports | All 12 core modules | ✅ Load cleanly |
| CLI | `transcribe.py`, `extract.py`, `generate.py` | ✅ Work |
| Extraction engine | Groq reachable | ✅ `llama-3.3-70b-versatile` |
| Database | PostgreSQL 15.18 | ✅ 27 tables |
| Reference data | trades / stages | ✅ 25 / 22 |
| Pipeline output | daily_logs / generation_outputs | ✅ persisted |
| Test suite | pytest | ✅ 718 passed |

---

## 8. Known Notes / Gotchas

- **Audio quality matters.** Low-quality recordings (noisy, thick accent) can drop Whisper confidence below ~30%, producing garbled text. The Groq extractor then correctly *rejects* the transcript rather than inventing data. Record in a quiet room for best results.
- **LLM can emit explicit `null`.** Per ADR-003, the extractor sets optional fields to `null` (not omitted). The repository layer guards every NOT NULL column with `value or default` — `dict.get(key, default)` alone does **not** protect against explicit null.
- **No REST endpoints yet.** All interfaces are CLI + internal Python APIs. HTTP endpoints are what Sprint 7 (FastAPI) will add.

---

## 9. Next: Sprint 7

FastAPI REST API over the working pipeline — upload → transcribe → extract → persist → generate → retrieve. Full spec in `docs/NEXT_SPRINT.md`.
