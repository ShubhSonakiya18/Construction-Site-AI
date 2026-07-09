# AI Pipeline — Construction Site AI

**Status:** Speech (Sprint 3), Extraction (Sprint 4), and Generation (Sprint 5) stages COMPLETE.
Persistence (Sprint 6) and Delivery (Sprint 7) are the next phases.

This document describes the full intended data flow from a foreman's voice
note to a structured, validated construction daily log — and which parts of
that flow exist today versus which are planned.

---

## End-to-end flow

```
[1] Foreman speaks a voice note on their phone
        |
        v
[2] SPEECH STAGE (Sprint 3 — COMPLETE)
    speech.SpeechProcessingPipeline.process(audio_path)
    Audio file -> SpeechProcessingResult
    (clean transcript text + timestamps + confidence + metadata)
        |
        v
[3] EXTRACTION STAGE (Sprint 4 — COMPLETE)
    extraction.ExtractionPipeline.extract(transcript_text)
    Transcript text -> ExtractionResult
    (ExtractionResult.extracted_log is a ConstructionDailyLog dict,
     validated against schema + business rules, with per-field confidences)
    Engine: GroqEngine (llama-3.3-70b-versatile or any BaseLLMProvider subclass via EngineFactory)
        |
        v
[4] GENERATION STAGE (Sprint 5 — COMPLETE)
    generation.AIServiceManager.generate_all(extracted_log)
    ConstructionDailyLog dict -> GenerationResult
    (4 typed outputs: DailyReport, CustomerUpdate, ToolboxTalk, MaterialReminder)
    Same EngineFactory + BaseLLMProvider abstraction as Sprint 4
        |
        v
[5] PERSISTENCE STAGE (Sprint 6 — next)
    GenerationResult + ExtractionResult -> PostgreSQL
    SQLAlchemy ORM models, Alembic migrations
        |
        v
[6] DELIVERY STAGE (Sprint 7 — planned)
    REST API (FastAPI) serving all outputs; audio upload endpoint;
    full pipeline orchestration via background tasks
```

---

## Why this order

Each stage produces a typed, structured output that the next stage consumes
— never raw bytes, never untyped dicts passed across stage boundaries:

| Stage | Input | Output |
|---|---|---|
| Speech | audio file path | `SpeechProcessingResult` (`speech/models/`) |
| Extraction | `Transcript.text` + segments | `ExtractionResult` containing `ConstructionDailyLog` dict |
| Generation | `ConstructionDailyLog` dict | `GenerationResult` (4 typed AI outputs) |
| Persistence | `ExtractionResult` + `GenerationResult` | DB rows |
| Delivery | DB rows | API response / customer summary |

This lets every stage be independently testable and independently
replaceable. `speech/` has zero imports from `dataset_generation_framework/`
or `knowledge/`, and nothing outside `speech/` imports `faster_whisper` directly.

---

## What exists today

### Knowledge base (Sprint 1)
`knowledge/` — the domain model. Construction stages, the
`ConstructionDailyLog` schema, business rules, dependency graph. Pure data +
a `KnowledgeBase` loader. No application logic.

### Synthetic Data Generation Framework (Sprint 2)
`dataset_generation_framework/` — generates realistic, schema-valid
`ConstructionDailyLog` records (and related: schedules, safety talks,
materials, customer updates) for training and validating the extraction model.
Uses `StageMachine` + `RuleEngine` to guarantee sequencing correctness.
Entry point: `generate.py`.

The validation pipeline built here (`ValidationResult`, 4-phase rule
checking) is reused unchanged by the extraction stage — a real extracted log
is validated the same way a synthetic one is.

### Speech Processing Framework (Sprint 3)
`speech/` — converts audio to structured transcript. See
[`SPEECH_PIPELINE.md`](SPEECH_PIPELINE.md) for full detail. Key point for
this document: the framework is **engine-agnostic**. `faster_whisper` is
imported in exactly one file (`speech/whisper/engine.py`). Replacing it with
a different local STT engine requires a new `BaseSTTEngine` subclass — no
changes anywhere else.

```python
from speech import SpeechProcessingPipeline

result = SpeechProcessingPipeline().process("voice_note.wav")
if result.success:
    transcript_text = result.plain_text()   # consumed by Sprint 4
```

### AI Extraction Framework (Sprint 4)
`extraction/` — converts a transcript into a `ConstructionDailyLog`. Key points:
- `ExtractionPipeline.extract(transcript_text) -> ExtractionResult`
- `GroqEngine` is the only file calling the Groq API — `BaseLLMProvider`
  is the interface everything else depends on; `EngineFactory` maps provider
  names to engine classes so the pipeline never imports a concrete engine
- `ExtractionResult.extracted_log` is the ConstructionDailyLog dict,
  validated by the Sprint 2 `ValidationPipeline` (`applies_to="ai_extraction"`)
- Real extractions require `GROQ_API_KEY` in `.env`. Tests run fully without
  an API key via `MockExtractionEngine`.

```python
from extraction import ExtractionPipeline

pipeline = ExtractionPipeline()
result = pipeline.extract("Today we had 5 workers. Framing the second floor. Sunny weather.")
if result.success:
    print(result.current_stage())      # 'framing'
    print(result.worker_count())       # 5
    print(result.to_json())            # full ExtractionResult JSON
```

### AI Generation Services (Sprint 5)
`generation/` — takes `ExtractionResult.extracted_log` (a validated
`ConstructionDailyLog`) and produces 4 typed business outputs via Groq:

- **`DailyReportService`** — formal contractor site report
- **`CustomerUpdateService`** — client-facing progress email
- **`SafetyTalkService`** — OSHA-referenced toolbox talk
- **`MaterialReminderService`** — procurement reminder

All 4 services are orchestrated by `AIServiceManager`. The same
`BaseLLMProvider` + `EngineFactory` abstraction from Sprint 4 is reused
via duck typing — no Sprint 4 code was modified. See `docs/AI_SERVICES.md`.

```python
from generation import AIServiceManager

manager = AIServiceManager()
result = manager.generate_all(extracted_log)   # GenerationResult with 4 outputs
print(result.daily_report.content)
print(result.customer_update.content)
```

---

## What's next

### Persistence (Sprint 6)
PostgreSQL schema mirroring `construction_daily_log_schema.json`.
SQLAlchemy ORM models + Alembic migrations. See `docs/NEXT_SPRINT.md`.

### Delivery (Sprint 7)
FastAPI REST API with audio upload, pipeline orchestration endpoint
(upload → transcribe → extract → generate → persist), and async background
tasks via Celery.

### Streaming / real-time (future)
The `BaseSTTEngine` interface is shaped so a future streaming engine could
implement it without changing `SpeechProcessingPipeline`'s public contract.

---

## Hard constraints across every stage

These apply to every AI/ML component in this pipeline, present and future:

- **No paid-per-token APIs.** No OpenAI, Anthropic, Gemini, Azure AI, or AWS AI.
  Speech-to-text (Faster Whisper) runs fully locally. Language model inference
  uses Groq's free-tier cloud API — zero per-token cost at current usage.
- **Open source / free tier only.** Faster Whisper is open-weight and local.
  Groq's free tier provides cloud inference at no cost.
- **Structured, typed boundaries.** No stage hands the next stage a raw
  string or untyped dict where a dataclass or schema-validated object is
  possible.
- **Engine/model abstraction.** Every ML-backed stage hides its specific
  model behind an interface (`BaseSTTEngine` for speech; `BaseLLMProvider` +
  `EngineFactory` for language models) so the underlying model can change
  without rewriting callers.
