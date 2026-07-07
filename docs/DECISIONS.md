# Architecture Decision Record (ADR)

**Construction Site AI — Engineering Decisions Log**

Every significant technical decision is recorded here with context, rationale, alternatives considered, and consequences. This document allows future engineers to understand WHY decisions were made, not just WHAT was decided.

---

## ADR-001: JSON Schema as Schema Source of Truth

**Date:** Sprint 1
**Status:** Accepted

**Context:**
We needed a schema format for `ConstructionDailyLog` that could serve as the single source of truth across multiple programming languages and layers.

**Decision:**
Use JSON Schema draft-07 as the master schema definition.

**Rationale:**
- Language-agnostic: works for Python (Pydantic generation), TypeScript (frontend types), and any other language
- Can auto-generate Pydantic v2 models using `datamodel-code-generator`
- Can auto-generate TypeScript types using `json-schema-to-typescript`
- Human-readable JSON format
- Supported by vast tooling ecosystem

**Alternatives Considered:**
- **Pydantic directly**: Python-specific. Frontend cannot use it. Forces import of app code in scripts.
- **Protobuf**: Compiled format. Adds build step. Poor human readability. Overkill for a web API.
- **OpenAPI 3.0**: Good for API contracts but less suitable as a standalone data model schema.

**Consequences:**
- Schema changes require bumping version and regenerating code models
- Pydantic models in Sprint 4 will be generated FROM this schema, not written by hand
- TypeScript types in future frontend sprint will be generated from this schema

---

## ADR-002: UUID Primary Keys

**Date:** Sprint 1
**Status:** Accepted

**Context:**
All entity IDs in the schema need to be chosen. Two main options: auto-increment integers or UUIDs.

**Decision:**
Use UUID (version 4) for all primary keys.

**Rationale:**
- **Security**: Integer IDs allow enumeration attacks (`GET /logs/1`, `/logs/2`, ...). UUIDs prevent this.
- **Distributed generation**: Mobile apps can generate UUIDs before sending to server, enabling offline-first operation.
- **Database merging**: When merging logs from multiple sites, integer IDs always collide. UUIDs never do.
- **Industry standard**: Stripe, Twilio, GitHub all use UUID or ULID for public-facing IDs.

**Alternatives Considered:**
- **Auto-increment integers**: Simpler, smaller storage. Defeated by security and distribution concerns.
- **ULID (Lexicographically Sortable UUID)**: Good for time-ordered queries. Slightly more complex. Would consider if ordering becomes critical.

**Consequences:**
- UUIDs are 36 characters. Marginally larger storage than integers.
- Indexes on UUID columns are less cache-friendly than sequential integers. Irrelevant at startup scale.
- All `$id` fields use `"format": "uuid"` in the JSON Schema.

---

## ADR-003: Explicit Null Typing for Optional Fields

**Date:** Sprint 1
**Status:** Accepted

**Context:**
In JSON, optional fields can be handled two ways: omit the field, or include it with `null` value. We needed to choose how the AI extraction engine would handle fields not mentioned in the voice recording.

**Decision:**
All optional fields are typed as `["type", "null"]` (e.g., `["string", "null"]`). The AI extraction engine must output `null` for fields not mentioned, never omit them.

**Rationale:**
- **Audit trail**: `null` means "AI processed this field and found nothing." Missing means "this field didn't exist in the schema version at creation time." These are different states.
- **Migration safety**: When we add new fields in v1.1.0, existing v1.0.0 records won't have them. `null` vs missing lets the migration script know the difference.
- **Debugging**: When AI extraction produces wrong output, we can tell whether a field was missed (null) or not in scope (missing).
- **Pydantic compatibility**: `Optional[str]` in Pydantic explicitly allows null. Aligns with our schema design.

**Alternatives Considered:**
- **Omit optional fields entirely**: Simpler JSON. Loses the audit trail. Migration is harder.
- **Default values instead of null**: Misleading. A default of `""` for inspector_name looks like the AI extracted an empty name, not that no inspection happened.

**Consequences:**
- All AI extraction prompts must explicitly instruct the model to output `null` for missing fields, not omit them.
- JSON documents are slightly larger (null fields still present in output).

---

## ADR-004: 12-Section Schema Architecture

**Date:** Sprint 1
**Status:** Accepted

**Context:**
The ConstructionDailyLog has 80+ fields. We needed to organize them to be understandable and maintainable.

**Decision:**
Organize the schema into 12 named sections: Metadata, Project Context, Construction Stage, Weather, Workforce, Work Completed, Materials, Equipment, Safety, Delays, Tomorrow's Plan, Client Communication, Attachments, Financials, AI Generated Outputs, Audit.

**Rationale:**
- **Cognitive manageability**: 80 flat fields is unreadable. 12 sections of 5-8 fields each is manageable.
- **Database mapping**: Each section maps directly to one or more database tables in Sprint 6. Schema design anticipates the ORM model structure.
- **AI prompt design**: Sprint 4 extraction prompts can address one section at a time, reducing hallucination from prompt overload.
- **API design**: Sprint 7 API can return partial log updates (only the safety section, for example) without returning the entire document.
- **Separation of concerns**: Safety data lives in one place. Financial data in another. No mixing.

**Consequences:**
- Nested JSON structure. Slightly more verbose to access: `log.workforce.total_workers_present` vs `log.total_workers`.
- AI extraction must handle nested output format.

---

## ADR-005: All AI Runs Locally (No Paid APIs)

**Date:** Sprint 1
**Status:** Partially superseded by ADR-015 (Sprint 4) — see note below.

**Context:**
We need AI capabilities (speech-to-text, text generation) for the core product. The choices are: cloud AI APIs or local models.

**Original Decision (Sprint 1):**
100% local AI. Ollama + Qwen2.5 for language models. Faster Whisper for speech-to-text. No cloud AI APIs of any kind.

**Revision (Sprint 4):**
The original intent — zero token costs, no proprietary paid APIs — is preserved. However, the specific implementation changed: Ollama + Qwen2.5 was replaced by the **Groq free-tier cloud API** (`groq` Python package, `llama-3.3-70b-versatile` model). This was a deliberate trade-off:
- Ollama required ~5 GB local disk space for model weights — infeasible for many developer environments.
- Groq's free tier imposes no per-token charges at current usage scales.
- The `BaseLLMProvider` + `EngineFactory` architecture (ADR-015) means Groq can be swapped for a local model without touching business logic.

**What did NOT change:**
- No paid APIs (OpenAI, Anthropic, Gemini, Azure AI, AWS AI). Groq's free tier is used exclusively.
- Speech-to-text still runs 100% locally via Faster Whisper.
- The engine abstraction means a future sprint can add a local LLM provider without rewriting callers.

**Consequences (updated):**
- `GROQ_API_KEY` must be set in `.env` for real language-model calls. Tests run fully without it via `MockExtractionEngine`.
- Construction data sent to the transcript-extraction step passes through Groq's API. This is a privacy trade-off documented in HANDOVER.md.
- Hardware requirements reduced significantly: no GPU needed, no large model download.

---

## ADR-006: Knowledge Base in JSON (Not a Database)

**Date:** Sprint 1
**Status:** Accepted

**Context:**
The construction domain knowledge (stages, rules, ontology) needs to be accessible to multiple modules: dataset generators, AI extraction, validation, RAG systems.

**Decision:**
Store knowledge base as JSON files in `knowledge/` directory, loaded into memory at module startup.

**Rationale:**
- **Simplicity**: JSON files require no database setup, no migrations, no connection management.
- **Version control**: JSON files are tracked in git. Every change is auditable.
- **Portability**: Any module can load a JSON file. No database driver needed.
- **AI-friendly**: JSON files can be loaded directly into prompts. JSON is the native format of language model outputs.
- **Fast reads**: For read-only knowledge that doesn't change at runtime, an in-memory JSON is faster than any database query.

**Alternatives Considered:**
- **Neo4j graph database**: Perfect for the ontology. But requires running another service, adds complexity. Better as a future enhancement when RAG is implemented.
- **PostgreSQL JSONB columns**: Would require the database to be running during development. Overkill for read-only knowledge.
- **SQLite**: Local database is acceptable but adds setup complexity over plain JSON files.

**Consequences:**
- Knowledge base is static (read-only at runtime). Dynamic updates require file edits and service restart.
- For RAG, knowledge base JSON will be loaded and indexed in FAISS (future sprint).
- JSON files have no query language. Full-text search requires loading everything and filtering in Python.

---

## ADR-007: Synthetic Dataset Generation (No Real Data Collection)

**Date:** Sprint 1
**Status:** Accepted

**Context:**
No public dataset exists for construction site daily logs. We need training and test data for Sprint 4 AI validation and Sprint 5 service testing.

**Decision:**
Generate 5 synthetic datasets using Python scripts that follow the construction rules and validation rules defined in Sprint 1 knowledge base.

**Rationale:**
- **No real data available**: There is no public dataset of construction daily logs. Industry data is proprietary.
- **Privacy**: Even if we could collect real data, it would contain client names, addresses, worker PII — we'd need GDPR/CCPA-compliant data handling before using it for training.
- **Reproducibility**: Synthetic data with a fixed random seed is 100% reproducible. Real data changes.
- **Edge case control**: We can generate exactly the edge cases we want to test (failed inspections, weather delays, material shortages) in controlled proportions.
- **Rule compliance**: Generated data follows `validation_rules.json` rules — no invalid sequencing, no concrete during painting stage.

**Alternatives Considered:**
- **Manually write 50 example logs**: Not scalable. Human bias. Not enough diversity.
- **Scrape contractor reports online**: Privacy issues. Quality varies. Legal risk.
- **Partner with a contractor for real data**: Good for future fine-tuning, but not feasible for Sprint 2 timeline.

**Consequences:**
- Generated data will not have the linguistic quirks of real voice recordings. Extraction model may struggle with real-world recordings that differ from training distribution.
- Mitigation: Sprint 3 includes multiple real voice recording tests before Sprint 4 AI is built.

---

## ADR-008: JSON Schema Stage Enum Has 22 Values (Not 11)

**Date:** Sprint 1.1 (Sprint 1 Review)
**Status:** Accepted

**Context:**
Sprint 1 research documented 11 broad construction stages. The `ConstructionDailyLog` schema's `current_stage` enum has 22 values. This appears to be a discrepancy.

**Decision:**
This is intentional. The 11 stages are broad phases. The 22 enum values are more granular sub-stages. Both are correct.

**Rationale:**
- The 11 stages are conceptual groupings for the knowledge base and research documentation.
- The 22 enum values reflect the granularity a foreman actually uses ("electrical finish" is distinct from "electrical rough-in").
- Forcing everything into 11 values would lose important distinction (e.g., "plumbing rough-in" vs "plumbing finish" are completely different work with different workers, materials, and timing).

**Resolution:**
- `construction_stages.json` documents the 11 broad phases with full detail.
- `construction_ontology.json` and `dependency_graph.json` model all 22 granular stages.
- `validation_rules.json` uses the 22 granular stage values for precise rule application.

**Consequences:**
- Dataset generators (Sprint 2) must use the 22-value enum for `current_stage`, not just 11 values.
- AI extraction (Sprint 4) must output one of the 22 exact enum values. Prompt must include the enum list.

---

---

## ADR-009: Production Framework Architecture Over One-Off Scripts

**Date:** Sprint 2
**Status:** Accepted

**Context:**
Sprint 2 requires generating 5 datasets. The simplest approach would be 5 standalone Python scripts, one per dataset.

**Decision:**
Build a reusable `dataset_generation_framework/` package with a proper pipeline architecture: Generators → Rule Engine → Validation Pipeline → Exporters → Statistics.

**Rationale:**
- **Scalability**: Scripts break at 100k records (memory). Framework streams records through pipeline — same peak memory at 500k as at 5k.
- **Reusability**: Sprint 4 AI extraction uses the same ValidationPipeline. Sprint 7 API uses the same KnowledgeBase. One implementation, multiple consumers.
- **Correctness**: Scripts generate records independently. Framework simulates complete projects day-by-day, guaranteeing sequencing correctness.
- **Configurability**: Change 5 constants in `config.py` to scale from 5k to 500k. No business logic changes.
- **Testability**: Framework modules are independently testable. Scripts are not.

**Consequences:**
- More upfront complexity vs. 5 simple scripts.
- `dataset_generation_framework/` is the foundation Sprint 3+ modules build on.

---

## ADR-010: Project Simulation Over Random Record Generation

**Date:** Sprint 2
**Status:** Accepted

**Context:**
The daily log generator needs to produce 5,000 logs. Two approaches: (a) pick a random stage and random field values for each log, or (b) simulate complete construction projects day-by-day.

**Decision:**
Project simulation. DailyLogGenerator runs ~50 complete residential projects, each progressing through the DAG in strict topological order.

**Rationale:**
- **Sequencing correctness**: Random generation cannot guarantee painting never appears before drywall. Simulation guarantees it because the StageMachine enforces the DAG.
- **Cross-record consistency**: Logs from the same project have consistent project metadata, realistic completion percentage progression, and correct material-to-stage alignment.
- **Training data quality**: AI models trained on independent random records learn no sequencing knowledge. AI models trained on simulated project records learn realistic construction progressions.

**Consequences:**
- Daily log generation is significantly more complex than other generators.
- `StageMachine` became a core framework module rather than a generator-internal detail.

---

## ADR-011: Streaming Generators — O(1) Peak Memory

**Date:** Sprint 2
**Status:** Accepted

**Context:**
At 500,000 records, loading all generated records into a list before writing would consume 500MB+ of RAM.

**Decision:**
All generators use Python generator functions (`yield`). Exporters buffer `BATCH_SIZE` (1,000) records before flushing to disk. Peak memory = O(BATCH_SIZE) regardless of total count.

**Rationale:**
- **Scalability**: Same codebase handles 5k and 500k with identical memory profile.
- **Simplicity**: Python's generator protocol handles backpressure automatically.
- **Industry standard**: All production data pipelines stream data — loading everything into memory is a known anti-pattern at scale.

**Consequences:**
- `BaseGenerator.stream()` returns a generator, not a list. Callers must consume it (iterate or pipe to exporter).
- DailyLogGenerator overrides `stream()` rather than `generate_one()` because project simulation requires state across multiple records.

---

## ADR-012: Engine-Agnostic Speech Framework via BaseSTTEngine Abstraction

**Date:** Sprint 3
**Status:** Accepted

**Context:**
Sprint 3 needs speech-to-text. Faster Whisper is the chosen engine (free,
local, no paid API), but engines change — a future sprint may swap in a
different local model, a fine-tuned variant, or a streaming-capable engine.
The risk: if `faster_whisper` types and calls leak into business logic,
swapping engines later means rewriting every caller.

**Decision:**
Build `speech/` as a standalone package. Define `BaseSTTEngine` (abstract
base class: `transcribe(audio_path) -> Transcript`, `is_available() -> bool`)
in `speech/whisper/engine.py`. `FasterWhisperEngine` is the only concrete
implementation. The `faster_whisper` import is deferred inside
`FasterWhisperEngine._load_model()` — it appears in exactly one file in the
entire codebase. `SpeechProcessingPipeline` depends on `BaseSTTEngine`, never
on `FasterWhisperEngine` or `faster_whisper` directly, and accepts any
`BaseSTTEngine` via constructor injection.

**Rationale:**
- **Replaceability**: Swapping engines means writing one new `BaseSTTEngine`
  subclass. Zero changes to `SpeechProcessingPipeline`, exporters,
  postprocessors, or any future caller (Sprint 4 extraction, Sprint 7 API).
- **Testability**: Tests inject a `MockSTTEngine` instead of loading a real
  150MB+ Whisper model. The full pipeline integration suite runs in under a
  second with zero GPU, network, or model-download dependency.
- **Same pattern as ADR-009**: the dataset generation framework already
  proved that an abstraction layer over the "thing that changes" pays for
  itself. This applies the same principle to the STT engine.

**Alternatives Considered:**
- **Call `faster_whisper.WhisperModel` directly from business logic**:
  Simpler short-term. Rejected — violates the explicit Sprint 3 requirement
  that business logic never call Faster Whisper directly, and makes future
  engine swaps a multi-file rewrite.
- **Wrap Faster Whisper in a thin function instead of a class hierarchy**:
  Works for one engine, but provides no enforced contract for a second
  implementation and no clean injection point for tests.

**Consequences:**
- Every new STT engine must implement `BaseSTTEngine` fully (`transcribe`,
  `is_available`).
- `speech/models/transcript.py` (`Transcript`, `TranscriptSegment`,
  `WordTimestamp`) is the permanent contract between any STT engine and the
  rest of the framework — these dataclasses must stay engine-neutral.

---

## ADR-013: Lazy Model Loading for STT Engines

**Date:** Sprint 3
**Status:** Accepted

**Context:**
Faster Whisper models range from 75MB (`tiny`) to 3GB (`large-v3`) and are
downloaded/loaded from disk on first use. If `FasterWhisperEngine.__init__()`
loaded the model immediately, simply importing `speech` or constructing a
`SpeechProcessingPipeline` (e.g., in a test file, or a process that only
needs validation) would trigger a multi-second-to-multi-minute model load.

**Decision:**
`FasterWhisperEngine.__init__()` sets `self._model = None`. The model is
constructed inside `_load_model()`, called lazily on the first
`transcribe()` invocation, wrapped in the existing `@retry` decorator for
transient load failures (e.g., a flaky first-time download).

**Rationale:**
- **Fast imports and fast test collection**: `import speech` and
  `SpeechProcessingPipeline()` must be cheap. Tests inject a mock engine
  precisely so the real model never has to load during the test suite, but
  lazy loading also protects any other code path that constructs a pipeline
  without immediately transcribing.
- **Resource control**: A long-running batch process (Sprint 3 spec target:
  scale from 1 to 100,000+ recordings) should load the model exactly once,
  on first actual use — not once per pipeline construction.

**Consequences:**
- `FasterWhisperEngine.unload()` exists to explicitly release the model
  after a large batch job, since the lazy-load pattern means nothing else
  automatically frees it.
- The first `transcribe()` call in any process is slower than subsequent
  calls (model load time). Acceptable — documented in `SPEECH_PIPELINE.md`.

---

## ADR-014: SpeechProcessingResult as a Structured Object, Never Plain Text

**Date:** Sprint 3
**Status:** Accepted

**Context:**
The simplest possible speech pipeline returns a string: the transcript text.
That is insufficient for this project — Sprint 4 extraction needs segment
timestamps to ground extracted fields to moments in the recording, Sprint 6
persistence needs an audit trail of how a transcript was produced, and
operators need confidence scores to flag low-quality transcriptions for
human review.

**Decision:**
`SpeechProcessingPipeline.process()` always returns a `SpeechProcessingResult`
dataclass — never a string, never an exception for expected failure modes.
It carries `success`, `transcript` (full `Transcript` with segments and word
timestamps), `metadata` (`SpeechProcessingMetadata` — audio file facts +
processing stats), `validation` (what the validator found), and `errors`/
`warnings`. Convenience methods (`plain_text()`, `confidence()`,
`duration_seconds()`, `language()`) cover the common case without forcing
callers to walk the full object graph. `to_dict()`/`to_json()` make the
entire result losslessly serializable.

**Rationale:**
- **Mirrors ADR-003**: explicit `null`/structured-failure over silent
  omission. A failed transcription is `success=False` with populated
  `errors`, not a thrown exception the caller must guess to catch.
- **Mirrors ADR-004**: every downstream stage gets a typed, structured input.
  Sprint 4 extraction will consume `result.transcript.segments` directly
  rather than re-parsing a flat string.
- **Audit and debugging**: `metadata.stats` records which pipeline stages
  ran, how long each took, what model/device/compute-type was used, and
  retry counts — essential once this runs against thousands of real
  recordings and something inevitably needs investigating.

**Alternatives Considered:**
- **Return `(text, metadata_dict)` tuple**: Untyped, easy to misuse, no
  IDE autocomplete, no schema to validate against in tests.
- **Raise exceptions for STT failures**: Forces every caller into
  try/except for an expected, common condition (bad audio file, OOM on a
  large model). `SpeechProcessingResult.failure()` makes the expected-failure
  path a normal return value instead.

**Consequences:**
- Every pipeline stage that can fail non-fatally (preprocessing) degrades to
  a warning and continues, rather than aborting the whole result — only
  validation failure and STT failure produce `success=False`.
- Exporters (`JSONExporter`, `TextExporter`, etc.) all operate on
  `SpeechProcessingResult`, giving a single object multiple output
  representations without re-running the pipeline.

---

## ADR-015: Provider-Agnostic Extraction Framework via BaseLLMProvider + EngineFactory

**Date:** Sprint 4 (revised post-Sprint 4)
**Status:** Accepted

**Context:**
Sprint 4 builds a framework for transcript → ConstructionDailyLog extraction.
Initially built around Ollama (local LLM). After Sprint 4 completion, the team
standardised on Groq (cloud, free tier) to eliminate the ~5 GB local model
download requirement. This revision documents the final architecture.

**Decision:**
`extraction/` is built as a standalone, provider-agnostic package.

- `BaseLLMProvider` (ABC) in `extraction/engines/base_engine.py` defines the
  interface: `extract(prompt) -> (str, dict)`, `is_available() -> bool`,
  `model_name`, `host`. This is the only type `ExtractionPipeline` depends on.
- `EngineFactory` in `extraction/engines/factory.py` maintains a registry of
  `provider_name → (EngineClass, config_extractor)`. `ExtractionPipeline` calls
  `EngineFactory.create_from_config(config, system_prompt)` — it never imports
  a concrete engine class or knows which provider is active.
- `GroqEngine` in `extraction/engines/groq_engine.py` is the only concrete
  implementation and the only file that imports the `groq` Python package.
  API key is read from `GROQ_API_KEY` env var.

**How to add a new provider (the complete list of required changes):**
1. Implement `BaseLLMProvider` in `extraction/engines/<name>_engine.py`
2. Add a `<Name>Config` dataclass to `extraction/config.py`
3. Add its config field to `ExtractionConfig` and `from_env()`
4. Call `EngineFactory.register(...)` in `extraction/engines/factory.py`

`ExtractionPipeline.extract()` requires zero changes.

**Rationale:**
- **Same pattern as ADR-012**: `BaseSTTEngine` proved in Sprint 3 that one
  abstract interface + one concrete file = independently testable, swappable,
  no multi-file rewrite when the underlying library changes.
- **Testability**: Tests inject a `MockExtractionEngine(BaseLLMProvider)` via
  the `engine=` constructor arg. The full suite runs without a live API key.
- **EngineFactory over direct import**: the pipeline never sees `GroqEngine`.
  Switching providers or adding one requires only the four steps above.

**Alternatives Considered:**
- **Direct import of GroqEngine in pipeline**: rejected — leaks the concrete
  dependency into business logic, making future swaps a multi-file rewrite.
- **Config-method `provider_kwargs()` approach**: elegant but the factory
  `config_extractor` lambda achieves the same decoupling with less indirection.

**Consequences:**
- Every new provider must implement `BaseLLMProvider` fully (four methods).
- `ExtractionResult` is the permanent contract between any engine and the rest
  of the framework — provider-neutral, fully serialisable.
- `GROQ_API_KEY` must be set in `.env` for real extractions. Tests run fully
  without it via `MockExtractionEngine`.

---

## ADR-016: ExtractionResult as a Structured Object, Never a Raw Dict

**Date:** Sprint 4
**Status:** Accepted

**Context:**
Same reasoning as ADR-014 for `SpeechProcessingResult`. The simplest
extraction pipeline returns a raw dict. That is insufficient — Sprint 6
persistence needs provenance (which model ran, how many attempts, were there
validation errors), and Sprint 7's API needs a typed object to respond with.

**Decision:**
`ExtractionPipeline.extract()` always returns an `ExtractionResult` dataclass.
It carries `success`, `extracted_log` (the `ConstructionDailyLog` dict),
`validation_passed`/`validation_errors`/`validation_warnings` (from the Sprint
2 `ValidationPipeline`), `field_confidences` (per-field 0.0–1.0 heuristic
scores), `errors`, `warnings`, and `metadata` (`ExtractionMetadata` — model,
host, token counts, duration, attempt count, repair flag). Convenience methods
(`current_stage()`, `worker_count()`, `plain_text()`) cover the common case.
`to_dict()`/`to_json()` make the result fully serializable.

**Rationale:**
- **Mirrors ADR-014 and ADR-003**: expected failures are structured data
  (`success=False` + `errors`), not thrown exceptions.
- **Reuses Sprint 2 validation**: `ValidationPipeline.validate(record,
  applies_to="ai_extraction")` runs the same 35 business rules against the
  extracted log as against synthetic records — no duplication of validation
  logic (per ADR-009 principle).

**Consequences:**
- `ExtractionResult.failure()` factory ensures every code path returns
  a complete, serializable result even when extraction cannot proceed.
- `field_confidences` is currently a heuristic (presence → 0.9, absence → 0.0).
  A future sprint can replace this with LLM-reported logprob scores without
  changing the result interface.

---

## Pending Decisions (Future Sprints)

| Decision | Context | Sprint |
|----------|---------|--------|
| Redis vs in-memory caching | For caching Ollama inference results | Sprint 5 |
| Celery vs FastAPI Background Tasks | For async audio processing | Sprint 7 |
| PostgreSQL vs TimescaleDB | For time-series analytics data | Sprint 6 |
| Alembic auto-generate vs hand-write migrations | Database migration strategy | Sprint 6 |
| Docker multi-stage build | Optimize image size | Sprint 7+ |
| JWT vs Session tokens | Authentication strategy | Sprint 7 |
| FAISS vs ChromaDB vs Weaviate | Vector store for RAG | Future |
