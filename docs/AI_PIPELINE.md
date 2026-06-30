# AI Pipeline — Construction Site AI

**Status:** Speech stage COMPLETE (Sprint 3). Extraction, persistence, and
delivery stages are future work.

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
[3] EXTRACTION STAGE (Sprint 4 — NOT STARTED)
    Transcript text -> structured ConstructionDailyLog fields
    Local LLM (Qwen2.5 or similar open-weight model) reads the cleaned
    transcript and extracts: work performed, materials used, crew present,
    delays, safety notes, weather — mapped to the schema in
    knowledge/construction_daily_log_schema.json
        |
        v
[4] VALIDATION STAGE (exists today, built in Sprint 1)
    dataset_generation_framework's validation pipeline
    (ValidationResult + 4-phase rule checking against
    knowledge/construction_rules.json) — currently used for synthetic
    training data; Sprint 4+ will run extracted real-world logs through
    the same validators
        |
        v
[5] PERSISTENCE STAGE (future sprint — NOT STARTED)
    Validated ConstructionDailyLog -> PostgreSQL
        |
        v
[6] DELIVERY STAGE (future sprint — NOT STARTED)
    Daily log -> customer-facing summary, API response, dashboard
```

---

## Why this order

Each stage produces a typed, structured output that the next stage consumes
— never raw bytes, never untyped dicts passed across stage boundaries:

| Stage | Input | Output |
|---|---|---|
| Speech | audio file path | `SpeechProcessingResult` (`speech/models/`) |
| Extraction (planned) | `Transcript.text` + segments | `ConstructionDailyLog` (`knowledge/construction_daily_log_schema.json`) |
| Validation (exists, reused) | `ConstructionDailyLog` | `ValidationResult` (`dataset_generation_framework/validators/`) |
| Persistence (planned) | validated `ConstructionDailyLog` | DB row |
| Delivery (planned) | DB row | API response / summary |

This lets every stage be independently testable and independently
replaceable. Sprint 3 proves the pattern: `speech/` has zero imports from
`dataset_generation_framework/` or `knowledge/`, and nothing outside `speech/`
imports `faster_whisper` directly.

---

## What exists today

### Knowledge base (Sprint 1)
`knowledge/` — the domain model. Construction stages, the
`ConstructionDailyLog` schema, business rules, dependency graph. Pure data +
a `KnowledgeBase` loader (`knowledge/loader.py`). No application logic.

### Synthetic Data Generation Framework (Sprint 2)
`dataset_generation_framework/` — generates realistic, schema-valid
`ConstructionDailyLog` records (and related: schedules, safety talks,
materials, customer updates) for training and validating the future
extraction model. Uses `StageMachine` + `RuleEngine` to guarantee
sequencing correctness. Entry point: `generate.py`.

The validation pipeline built here (`ValidationResult`, 4-phase rule
checking) is reused unchanged by the future extraction stage — a real
extracted log is validated the same way a synthetic one is.

### Speech Processing Framework (Sprint 3 — this sprint)
`speech/` — converts audio to structured transcript. See
[`SPEECH_PIPELINE.md`](SPEECH_PIPELINE.md) for full detail. Key point for
this document: the framework is **engine-agnostic**. `faster_whisper` is
imported in exactly one file (`speech/whisper/engine.py`). Replacing it with
a different local STT engine requires a new `BaseSTTEngine` subclass — no
changes anywhere else, including the extraction stage that will consume its
output.

```python
from speech import SpeechProcessingPipeline

result = SpeechProcessingPipeline().process("voice_note.wav")
if result.success:
    transcript_text = result.plain_text()   # <-- this is what Sprint 4 will consume
```

---

## What's planned (not built yet)

### Extraction (Sprint 4)
A local, open-weight LLM (likely Qwen2.5, run via Ollama or similar — no
paid API) reads `SpeechProcessingResult.transcript` and produces a
`ConstructionDailyLog` matching the Sprint 1 schema. Design questions for
that sprint: prompt structure, few-shot examples from the Sprint 2 synthetic
dataset, confidence scoring per extracted field, handling partial/ambiguous
transcripts.

### Persistence (future)
PostgreSQL schema mirroring `construction_daily_log_schema.json`. Not started
— no database exists in the codebase yet.

### Delivery (future)
API layer (likely FastAPI, free/open source) serving extracted logs to a
dashboard or customer-facing summary endpoint.

### Streaming / real-time (future)
The `BaseSTTEngine` interface in `speech/whisper/engine.py` is shaped so a
future streaming engine could implement it without changing
`SpeechProcessingPipeline`'s public contract, but no streaming engine exists
today. `FasterWhisperEngine.transcribe()` is a synchronous, file-based call.

---

## Hard constraints across every stage

These apply to every AI/ML component in this pipeline, present and future:

- **No paid APIs.** No OpenAI, Claude, Gemini, Azure AI, AWS AI, or other
  paid SaaS inference. Everything runs locally.
- **Open source only.** Faster Whisper (Sprint 3), and the planned local LLM
  for extraction (Sprint 4), are both free, open-weight models runnable on
  commodity hardware.
- **Structured, typed boundaries.** No stage hands the next stage a raw
  string or untyped dict where a dataclass or schema-validated object is
  possible.
- **Engine/model abstraction.** Every ML-backed stage hides its specific
  model behind an interface (`BaseSTTEngine` today; an analogous extraction
  interface is expected in Sprint 4) so the underlying model can change
  without rewriting callers.
