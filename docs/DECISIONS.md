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

## ADR-017: Prompts as Versioned .md Files

**Date:** Sprint 5
**Status:** Accepted

**Context:**
Four AI generation services each need a prompt. Hardcoding prompts in Python forces a
code change and redeploy for every prompt iteration.

**Decision:**
Store prompts as `.md` files in `generation/prompts/` with YAML-like frontmatter
(`name`, `version`, `description`, `supported_models`, `variables`, `expected_output`, `last_updated`).

**Rationale:**
- Non-developers (product owners, prompt engineers) can iterate prompts without touching Python
- `.md` renders in GitHub — reviewers can read and comment directly
- Frontmatter provides version history and compatibility metadata
- `PromptLoader` caches per-instance → zero I/O cost after first load

**Alternatives Considered:**
- **Hardcoded strings**: Code change + redeploy per prompt iteration. No versioning visible in git.
- **Database storage**: Adds complexity; not warranted before Sprint 6 database exists.
- **`.txt` files**: No metadata. Cannot version without external tracking.

**Trade-offs:**
- Prompts are not validated by Python type system.
- A missing file raises `FileNotFoundError` at runtime (caught in tests).

---

## ADR-018: Pydantic for Generation Output Models

**Date:** Sprint 5
**Status:** Accepted

**Context:**
Sprints 2–4 use Python `dataclasses` for internal data structures. Sprint 5
introduces *business outputs* that callers will eventually consume via a REST API.

**Decision:**
Use Pydantic `BaseModel` for Sprint 5 output models (`ServiceOutput`, `GenerationResult`, etc.).
Sprints 2–4 retain `dataclasses`.

**Rationale:**
- Sprint 7 FastAPI mandates Pydantic for request/response models (Pydantic v2 is FastAPI's native type system)
- `BaseModel` provides `.model_dump(mode="json")` and `.model_json_schema()` for free
- Type validation at object construction catches bugs early
- Starting in Sprint 5 avoids a full rewrite in Sprint 7

**Alternatives Considered:**
- **Dataclasses (consistent with Sprints 1–4)**: Would require rewrite in Sprint 7 for API responses.
- **TypedDict**: No validation, no `.to_json()`.

**Trade-offs:**
- Pydantic dependency added (`pydantic==2.13.4` in `requirements-dev.txt`)
- Mix of dataclasses (config) and Pydantic (outputs) in the codebase — documented in ADR

---

## ADR-019: One Shared Engine, System Instructions in User Message

**Date:** Sprint 5
**Status:** Accepted

**Context:**
Each AI service needs different system-level instructions (role, format, rules).
`GroqEngine` (Sprint 4, FROZEN) sets `system_prompt` at construction time, not
per-call. Creating 4 separate engine instances is possible but requires 4 separate
`is_available()` API calls.

**Decision:**
`AIServiceManager` creates ONE `GroqEngine` with `system_prompt=""`.
Each service embeds its system instructions directly in the user message via the
prompt template file. The full prompt = `[template body]\n\n---\n\n[log data]`.

**Rationale:**
- Zero modifications to Sprint 4's FROZEN `GroqEngine`/`BaseLLMProvider`
- One engine instance = one `is_available()` check per `generate_all()` call
- Modern LLMs (Llama 3.3) respond equally well to instructions in user messages

**Alternatives Considered:**
- **4 engine instances**: Would work but requires 4 API calls for `is_available()`.
- **Modify GroqEngine to accept per-call system_prompt**: Requires Sprint 4 change — FROZEN.

**Trade-offs:**
- Loses formal system/user message separation (minor impact on model quality)
- If the model changes behaviour due to instruction position, per-instance engines are the fix

---

## ADR-020: Prompts in generation/prompts/ Not app/prompts/

**Date:** Sprint 5
**Status:** Accepted

**Context:**
The Sprint 5 specification requested prompts under `app/prompts/`. However,
`app/` is the Sprint 7 FastAPI application directory. Creating it in Sprint 5
would violate the constraint: *"Never create files or folders for future sprints."*

**Decision:**
Use `generation/prompts/` — consistent with `extraction/prompts/` pattern.

**Rationale:**
- Respects the "no future sprint files" constraint
- Consistent with established `extraction/prompts/` pattern
- When Sprint 7 creates `app/`, prompts can be referenced or symlinked if needed

**Trade-offs:**
- Deviates from the original specification (documented here for transparency)

---

---

## ADR-021: Mtime-Aware Prompt Cache Invalidation

**Date:** Sprint 5.1
**Status:** Accepted

**Context:**
Sprint 5.0's `PromptLoader` cached `LoadedPrompt` objects by name. Once cached,
a prompt was never re-read — even if the `.md` file was edited. Prompt engineers
had to restart the process to pick up edits.

Additionally, `BaseAIService` held its own instance-level `self._loaded_prompt`
cache, duplicating the caching concern and bypassing `PromptLoader` on all but
the first `generate()` call per service instance.

**Decision:**
1. `PromptLoader` now stores `_mtime: dict[str, float]` alongside `_cache`. On
   every `.load()` call, `os.path.getmtime(path)` is compared against the stored
   mtime. If the file was modified, the cached entry is evicted and the file is
   re-read.
2. `BaseAIService`'s instance-level `self._loaded_prompt` cache is removed.
   `generate()` always calls `self._prompt_loader.load(self.prompt_name)`.

**Rationale:**
- With the service-level cache intact, `PromptLoader`'s mtime check was bypassed
  on all calls after the first — making the invalidation logic dead code.
- Removing the service-level cache makes `PromptLoader` the single source of
  truth for caching. The PromptLoader cache hit is O(1) dict lookup + one
  `os.stat()` call — negligible compared to network I/O.
- Prompt engineers can now edit `.md` files and see changes on the next
  `generate()` call without restarting the process. Critical during iterative
  prompt development.

**Alternatives Considered:**
- **File watcher (inotify/watchdog)**: Would push changes without polling. Adds
  a background thread and external dependency. `os.stat()` is simpler, cheaper,
  and sufficient for the CLI use case.
- **Keep service-level cache, add manual invalidation**: Would require callers to
  call `service.reload_prompt()`. Removes the automatic nature of the fix.

**Consequences:**
- Every `generate()` call performs one `os.stat()` syscall per prompt. Negligible
  vs. LLM network round-trip.
- The Sprint 5 test `test_prompt_loaded_only_once_across_multiple_generate_calls`
  was updated to reflect that `loader.load()` is called on every `generate()`.

---

## ADR-022: Prompt Registry for Domain-Level Prompt Discovery

**Date:** Sprint 5.1
**Status:** Accepted

**Context:**
`PromptLoader.list_available()` discovers prompts by scanning the filesystem for
`.md` files — it answers "what files exist?" There was no domain-level record of
"what prompts are expected to exist and what are their contracts."

**Decision:**
Create `generation/prompts/registry.py` with `PromptRegistry` and `PromptRegistration`.
The `DEFAULT_PROMPT_REGISTRY` pre-registers the 4 built-in prompts with their
name, description, `expected_output`, service class name, and required variables.
`validate(name)` raises `ValueError` if a prompt name is not registered.

**Rationale:**
- Separates I/O concern (PromptLoader) from domain concern (what prompts exist).
- Provides an authoritative list of expected prompts. Future Sprint 7 admin API
  can expose this list without reading the filesystem.
- `validate()` provides early error detection when an unknown prompt name is used.

**Trade-offs:**
- New prompts require one registration step in `registry.py` in addition to the
  `.md` file. Acceptable — the registration is one call.

---

## ADR-023: ServiceRegistry for Open/Closed Service Registration

**Date:** Sprint 5.1
**Status:** Accepted

**Context:**
`AIServiceManager.__init__()` manually constructed a dict `{ServiceType: ServiceInstance}`
with one dict entry per service. Adding a fifth service required editing the manager.

**Decision:**
Create `generation/services/registry.py` with `ServiceRegistry` and `ServiceRegistration`.
`AIServiceManager.__init__()` calls `registry.create_all(engine, loader, validator, config)`.
`DEFAULT_SERVICE_REGISTRY` is pre-populated with the 4 built-in services.
A new `service_registry=` parameter on `AIServiceManager` enables partial-registry
injection in tests.

**Rationale:**
- **Open/Closed Principle**: adding a new service requires 1 class + 1 `register()`
  call. Zero changes to `AIServiceManager`.
- `create_all()` centralises service instantiation — shared `engine`, `loader`,
  `validator`, `config` are wired once, not repeated for each service.

**Trade-offs:**
- Slight indirection. Accepted — the pattern pays for itself when a fifth service
  is added.

---

## ADR-024: generation_id as UUID4 Correlation Key in ServiceMetadata

**Date:** Sprint 5.1
**Status:** Accepted

**Context:**
`ServiceMetadata` lacked a unique identifier per generation call. When debugging
a failed generation, correlating `logger.warning()` output (which service, which
attempt) with the structured result was non-trivial.

**Decision:**
Add `generation_id: str = Field(default_factory=lambda: str(uuid4()))` to
`ServiceMetadata`. The same `generation_id` is passed to all observability events
fired during that `generate()` call, making log lines linkable to results.

**Rationale:**
- One UUID per `generate()` call (not per retry attempt) — the ID identifies the
  logical generation request.
- Auto-assigned by default (no callers need to change). Explicit override is
  supported for test assertions.
- Sprint 6 database will store `generation_id` as a column, enabling traces
  across logs ↔ DB rows without a secondary index.

**Trade-offs:**
- Minor overhead: one `uuid4()` call per generation. Negligible vs. LLM call.

---

## ADR-025: Lightweight In-Process Observability Layer

**Date:** Sprint 5.1
**Status:** Accepted

**Context:**
Production observability (dashboards, alerting, persistent metrics) requires
Sprint 7's async infrastructure (Celery, Redis). Sprint 5 had no observability
mechanism at all — no way to answer "how many generations succeeded?", "what is
the prompt cache hit rate?", "which service retries most?"

**Decision:**
Create `generation/observability/` with three modules:
- `events.py`: frozen dataclasses for 9 typed event types (no dicts, no strings)
- `timers.py`: `Timer` context manager (wraps `time.monotonic()`)
- `metrics.py`: `GenerationMetrics` in-memory accumulator + `METRICS` global

`BaseAIService.generate()` emits events to `METRICS` after each significant state
transition (started, completed, failed, retry, validation failed). `PromptLoader`
is updated to emit cache hit/miss events.

**Rationale:**
- **No external dependencies**: no Prometheus, no OpenTelemetry, no cloud agents.
  Pure stdlib. Aligns with the "free technologies" constraint.
- **Forward-compatible API**: Sprint 7 can add persistence (write events to DB)
  or push (emit to Redis Streams) without changing the event dataclasses.
- **Frozen events**: immutability prevents accidental mutation after emission.
- **`METRICS` global**: process-scoped singleton. Tests call `METRICS.reset()`
  in fixtures to prevent cross-test pollution.

**Alternatives Considered:**
- **Structured logging only**: Already done (logger calls). But logs are not
  queryable in-process. Metrics are.
- **OpenTelemetry now**: Adds 3+ dependencies and complex SDK configuration.
  Premature for a CLI-only sprint.

**Trade-offs:**
- In-memory only: metrics are lost on process exit. Acceptable for Sprint 5.1 CLI.
- No cross-process aggregation: each CLI run has independent METRICS.
  Sprint 7 Celery workers aggregate via DB or message queue.

---

## ADR-026: AuditUserMixin Without FK Constraints

**Date:** Sprint 6
**Status:** Accepted

**Context:**
Every business entity needs `created_by_id` and `updated_by_id` (who created/last-modified this record). The natural implementation is FK columns pointing to `users.id`. But `companies.created_by_id → users.id` while `users.company_id → companies.id` creates a circular FK dependency. PostgreSQL cannot satisfy both RESTRICT constraints simultaneously when seeding the first company and first user.

**Decision:**
`created_by_id` and `updated_by_id` in `AuditUserMixin` are plain `UUID` columns with NO FK constraints. The constraint is enforced at the application layer: repository methods validate that actor IDs exist before persisting.

**Consequences:**
- DB cannot enforce actor existence; audit columns can reference deleted users (acceptable — audit history must survive actor deletion)
- Application code must validate actor IDs (done in repository layer)
- Seeds run cleanly: company is created first, then user, with no FK bootstrapping problem

---

## ADR-027: Denormalized Transcript Data on DailyLog

**Date:** Sprint 6
**Status:** Accepted

**Context:**
`SpeechTranscript.raw_text` and `SpeechTranscript.avg_confidence` are already stored in the `speech_transcripts` table. The Sprint 7 daily-log detail API endpoint needs both the log and the original transcript text. Without denormalization: `daily_logs → audio_files → speech_transcripts` (2 extra joins on every log request).

**Decision:**
Store `raw_transcript` (TEXT) and `transcript_confidence` (NUMERIC) directly on `daily_logs` as denormalized copies of `speech_transcripts.raw_text` and `speech_transcripts.avg_confidence`.

**Consequences:**
- Transcript data can theoretically diverge if re-transcription occurs (acceptable: raw_transcript is append-only in practice)
- Sprint 7 log detail endpoint avoids 2 extra joins for the 99% read path

---

## ADR-028: JSON Blobs vs Normalized Child Tables

**Date:** Sprint 6
**Status:** Accepted

**Context:**
`ConstructionDailyLog` v1.0.0 has many array fields: trades_on_site, work_completed, materials, equipment, hazards, delays, inspections, and also weather, absences, visitors, tomorrow_plan, etc. The normalization question: when is a child table worth the extra join overhead?

**Decision:**
**Rule**: Arrays that are *independently queryable* (i.e., PM dashboards query individual rows) → child tables. Arrays that are *always fetched complete* and never queried individually → JSON blobs on `daily_logs`.

Child tables (11): trades_on_site, work_items, work_in_progress, materials_used, materials_delivered, materials_required, equipment, safety_incidents, hazards, delays, inspections.

JSON blobs (12 columns): weather, late_arrivals, absences, visitors, safety_meeting_topics, ppe_required_today, shortage_flags, tomorrow_plan, client_communication, attachments, financials, active_stages.

**Consequences:**
- Child tables: indexed, queryable ("all OSHA-recordable incidents this quarter"), but require JOIN
- JSON blobs: fetched as a unit, no JOIN, but non-indexable in SQLite (JSONB operators work in PostgreSQL)

---

## ADR-029: Soft Delete Pattern for Mutable Business Entities

**Date:** Sprint 6
**Status:** Accepted

**Context:**
Construction foremen sometimes create a daily log by mistake or delete a worker record. Hard delete destroys audit history and creates dangling FKs in child tables.

**Decision:**
Business entities use soft delete: `deleted_at TIMESTAMP` column. `deleted_at IS NULL` = active. `deleted_at IS NOT NULL` = deleted. All `list()` queries filter `WHERE deleted_at IS NULL` by default. `restore()` clears `deleted_at`.

Hard delete is reserved for GDPR right-to-erasure scenarios only.

**Tables with soft delete:** companies, users, workers, projects, daily_logs.
**Tables without:** reference tables (immutable enum data), audio_files, speech_transcripts, generation_outputs, audit_logs.

---

## ADR-030: AuditLog Immutability

**Date:** Sprint 6
**Status:** Accepted

**Context:**
An audit trail is only useful if it cannot be modified. OSHA compliance and general contractor insurance documentation require tamper-evident records of site safety incidents.

**Decision:**
`AuditLog` rows are never updated or deleted. The model has no `TimestampMixin` (no `updated_at`), no `SoftDeleteMixin`. It only has `UUIDPrimaryKeyMixin` + an explicit `created_at` with `server_default=func.now()` (DB sets the timestamp). The `AuditLogRepository.log_event()` method is the only write path.

**Consequences:**
- Audit trail cannot be modified even by admins (design intent, not limitation)
- Growing table: mitigate in Sprint 10+ via table partitioning by `created_at`

---

## ADR-031: Repository Layer Stays Synchronous; Routes Use Threadpool Offload

**Date:** Sprint 7
**Status:** Accepted

**Context:**
FastAPI route handlers benefit from async I/O. Sprint 7 added `database.session.get_async_session()` (SQLAlchemy `AsyncEngine`/`AsyncSession` backed by `asyncpg`). The natural next step would be for `app/api/v1/*.py` routes to use it directly with `database/repositories/*.py`.

**Decision:**
`database/repositories/base.py` and every repository built on it call `session.execute()`, `.get()`, `.flush()`, `.delete()` **without `await`** — these are synchronous calls. `AsyncSession`'s equivalent methods are coroutines; calling them unawaited does not raise, it silently returns an unawaited coroutine object instead of a result. Rather than rewrite all 12 repository classes as async (doubling the surface area, or breaking every Sprint 1-6 CLI tool that calls them synchronously today), FastAPI routes use the existing sync `get_session()` via `app/api/dependencies.py:get_db()` — a plain `def` (not `async def`) generator dependency, which FastAPI runs in a worker threadpool automatically. `get_async_session()` remains available for direct SQLAlchemy Core usage from async code that does not go through the repository layer.

**Consequences:**
- Route handlers are non-blocking (via threadpool offload) without the repository layer needing a parallel async implementation.
- Sprint 1-6 repositories are untouched — zero risk of regression to CLI tools or the existing test suite.
- Does not achieve the theoretical maximum concurrency of an all-async stack. Acceptable at this project's target scale (hundreds of companies, not tens of thousands — per the multi-tenancy design notes).
- If a future sprint's traffic profile genuinely requires async repositories, the migration path is documented in `docs/BACKEND_ARCHITECTURE.md` §7: `BaseRepository[T]`'s narrow, uniform interface makes an eventual async rewrite mechanical, not a redesign.

---

## ADR-032: `database/` Has Zero Dependency on `app/`

**Date:** Sprint 7
**Status:** Accepted

**Context:**
Sprint 7 needed one working demo login (`admin@example.com`) so `POST /api/v1/auth/login` has a real account to authenticate against. The direct approach — hash the password inside `database/seed/sample_data.py` — would import `app.core.security.hash_password()` into a Sprint 6 (frozen) module.

**Decision:**
`database/` stays framework-independent: usable from a CLI tool, a future non-FastAPI consumer, or a migration script without needing `app/`'s dependencies (`passlib`, `python-jose`, `pydantic-settings`, FastAPI itself) installed. `database/seed/sample_data.py` seeds a placeholder `User` row (`DEV_ADMIN_ID`) with `hashed_password=None` — no password logic, no import of `app/`. `app/core/dev_seed.py` is the one place in the codebase where the application layer reaches back into already-seeded data: `ensure_dev_admin_password()` looks up that row by its fixed UUID and sets the hash.

**Consequences:**
- Dependency direction is always `app/ → database/`, never the reverse. Verified: `grep -rn "^from app\|^import app" database/` returns zero matches.
- Seeding a working dev login requires two steps (`seed_sample_data()` then `ensure_dev_admin_password()`) instead of one — mitigated by `app.core.dev_seed.bootstrap_dev_environment()`, which chains both behind a single CLI command (`python -m app.core.dev_seed`).
- Establishes the pattern for any future case where `app/` needs to enrich already-seeded Sprint 1-6 data: the enrichment lives in `app/`, never as a new import inside the frozen package.

---

## ADR-033: `/api/v1` Prefix With Version-Isolated Router Packages

**Date:** Sprint 7
**Status:** Accepted

**Context:**
The API needs to support future breaking changes without forcing every existing client to migrate simultaneously.

**Decision:**
Every Sprint 7 router is mounted under `/api/v1` in `app/create_app.py`. `app/api/v1/` is a self-contained package — its routers and the schemas in `app/schemas/` they depend on belong to version 1 of the contract. A future `/api/v2` would be a sibling package (`app/api/v2/`) with its own routers, never a modification to `v1/`'s files. Version-specific behavior lives only in the router layer — `app/services/` and `database/repositories/` are version-agnostic; a v2 router would call the same service functions a v1 router does, wrapping the result in a v2-shaped schema only if the contract changed.

**Consequences:**
- A v1 client's contract never breaks because v2 was introduced.
- No versioning logic leaks into business logic or the repository layer.
- Full rationale and worked example in `docs/BACKEND_ARCHITECTURE.md` §5.

---

## ADR-034: Standard Response Envelope on Every Endpoint

**Date:** Sprint 7
**Status:** Accepted

**Context:**
FastAPI's default behavior returns a bare resource model on success and `{"detail": "..."}` on an `HTTPException` — two different shapes a client must special-case.

**Decision:**
Every endpoint returns `APIResponse[T]` (`app/schemas/envelope.py`): `{success, message, data, metadata, errors, timestamp, request_id}`, for both success and error responses. `request_id` and `timestamp` are populated automatically by `success_response()`/`error_response()` helpers (reading a `ContextVar` set by `RequestIDMiddleware`) — a route handler never has to remember to include them. The generic `[T]` parameter means OpenAPI still documents the real `data` type per endpoint instead of a vague `object`.

**Consequences:**
- Client code has exactly one parsing path — `success: bool` distinguishes outcome, not response shape.
- Every error (validation, business-rule 409, unexpected 500) surfaces through the same 5 centralized exception handlers (`app/middleware/exception_handlers.py`) rather than being hand-built per route.

---

## ADR-035: Refresh Tokens as Opaque Server-Backed Sessions, Not Stateless JWTs

**Date:** Sprint 8, Subsystem 1
**Status:** Accepted

**Context:** Sprint 7 shipped access-token-only login. Sprint 8 required Logout, Logout-All-Devices, and Token Revocation — none of which are achievable with a stateless JWT refresh token, since there is no server-side record to invalidate before natural expiry.

**Decision:** Refresh tokens are opaque, high-entropy random strings (`secrets.token_urlsafe(32)`), never JWTs. A new `user_sessions` table (`database/models/auth.py`) stores one row per issued refresh token: a SHA-256 hash of the token (never the raw value), issuance/expiry timestamps, and revocation state. Every refresh rotates the token (old one revoked, new one issued); logout/logout-all/password-change/deactivation revoke rows directly.

**Alternatives Considered:**
- **Stateless JWT refresh token:** Would still need the identical `user_sessions` table to be revocable, so the JWT format adds signature-verification overhead for zero benefit over an opaque string.
- **Redis-backed session store:** Rejected for Sprint 8 — Redis is not yet introduced; PostgreSQL is the single datastore this sprint, consistent with `password_reset_tokens` and the account-lockout columns.

**Consequences:**
- New table `user_sessions`, migration `002`.
- Access tokens remain non-revocable JWTs by design (short 60-min lifetime is the mitigation) — see `docs/AUTHENTICATION_ARCHITECTURE.md` §1.

---

## ADR-036: Extend Existing Roles, Add Only `system_admin` — Permission Layer Over Hardcoded Role Checks

**Date:** Sprint 8, Subsystem 2
**Status:** Accepted

**Context:** The Sprint 8 spec's illustrative role list (System Admin, Company Admin, Project Manager, Site Engineer, Foreman, Worker, Read Only) did not match the frozen Sprint 6 `User.role` values (`owner`, `admin`, `project_manager`, `foreman`, `safety_officer`, `client`).

**Decision:** Preserve all 6 existing roles unmodified (frozen schema, already seeded). Add exactly one new role, `system_admin` — a cross-company superuser with no existing equivalent, not seeded by default. Implement RBAC as a `Permission` enum + `ROLE_PERMISSIONS` mapping (`app/core/permissions.py`), replacing hardcoded `require_role(...)` lists at each endpoint with a single `require_permission(Permission.X)` dependency.

**Alternatives Considered:**
- **Replace the role set with the spec's exact list:** Rejected — would require a data migration remapping every seeded/existing row and would break the "do not modify frozen artifacts" constraint for no functional gain (a permission layer achieves the same fine-grained-access goal).

**Consequences:**
- Sprint 7 had permission checks on only 2 of 9 relevant endpoints; all 9 are now permission-gated.
- Role *assignment* uses a separate authority ordering, `ROLE_RANK`, so "who can grant which role" is independent of "what can this role do."

---

## ADR-037: Tenant Scoping at the Repository Layer, Not the Router Layer

**Date:** Sprint 8, Subsystem 3
**Status:** Accepted

**Context:** `CurrentUser.company_id` existed since Sprint 7 but nothing checked it against the resource being accessed — a real, exploitable cross-tenant data leak.

**Decision:** `TenantScopedRepository` (`database/repositories/tenant.py`) provides `*_scoped()` methods that build the company filter into the query itself, taking a `TenantContext` built only from the authenticated JWT (never from request input). Cross-tenant access is `system_admin`-only, via explicitly separate `*_cross_tenant()` methods (never a `company_id=None` sentinel), gated by `Permission.COMPANY_READ_ANY`, and mandatorily audited.

**Alternatives Considered:**
- **Router-layer checks** (fetch, then compare `company_id`, 404 on mismatch): rejected — requires every current and future router to remember the comparison; nothing stops an unscoped `get_by_id()` call from shipping.

**Consequences:**
- Cross-tenant access returns 404 (indistinguishable from nonexistent), not 403 — see ADR-038.
- `BaseRepository`'s unscoped methods are untouched for Sprint 1-7 non-HTTP callers (CLI scripts, `pipeline_service.py`) that are correctly scoped by construction.

---

## ADR-038: 404 (Not 403) for Cross-Tenant Access Attempts

**Date:** Sprint 8, Subsystem 3
**Status:** Accepted

**Context:** Needed a policy for what an authenticated user sees when requesting a real resource ID belonging to a different company.

**Decision:** Return 404, identical to a genuinely nonexistent ID. 403 is reserved for same-tenant-but-wrong-permission, where the resource's existence is already confirmed.

**Rationale:** Matches the account-enumeration-avoidance precedent already established at login (`app/api/v1/auth.py`) and `get_current_user()` — a 403 would confirm "this ID is real, you're just not allowed to see it," which is itself information leakage in a multi-tenant SaaS context.

---

## ADR-039: AuditLog Extended with First-Class Structured Columns, JSON Metadata Retained

**Date:** Sprint 8, Subsystem 6
**Status:** Accepted

**Context:** The frozen Sprint 6 `AuditLog` model had no dedicated columns for `ip_address`, `user_agent`, `request_id`, `success`/`failure`, or `target_user_id` — Sprint 8's spec required these as queryable fields, not buried in the `event_metadata` JSON blob.

**Decision:** Migration `004` adds five nullable columns (backward-compatible with every existing row) plus indexes. `event_metadata` is retained, unchanged, for genuinely event-specific context with no cross-event meaning (e.g. `locked_until` for a lockout event). No field is duplicated between a column and `event_metadata`.

**Rationale:** "Every failed login from IP X in the last hour" becomes an indexed column scan instead of a JSON-path filter across every row; every `log_event()` caller passes the same typed parameter for the same concept instead of risking inconsistent dict keys.

**Consequences:**
- `AuditLogRepository.log_event()` gained 5 new keyword parameters (additive, backward-compatible with all pre-Sprint-8 call sites).
- Three new query helpers: `list_by_request_id()`, `list_failures_by_ip()`, `list_for_target_user()`.

---

## ADR-040: Fail-Open Audit Logging, With One Deliberate Exception

**Date:** Sprint 8, Subsystem 6
**Status:** Accepted

**Context:** Explicit requirement: audit logging must never block business logic. But `AuditLogRepository.log_event()` itself can raise (e.g. a broken DB connection).

**Decision:** `app/services/audit_helpers.py:safe_log_event()` wraps `log_event()`, catching any exception, logging it to the application logger, and returning `None` instead of propagating. The **one exception**: `system_admin.cross_tenant_access` (ADR-037) uses the raw, must-succeed `log_event()` — because "every cross-tenant access must generate an audit entry" is a stronger requirement than "logging must never block," and an unaudited cross-tenant bypass is worse than a failed one.

**Consequences:** See the two commit-before-raise bugs documented in the "Known Bugs Found and Fixed — Sprint 8" section below — `safe_log_event()` must commit immediately on success, not just flush, because several audit events are logged immediately before the caller raises an intentional `HTTPException`.

---

## ADR-041: RateLimiter as a Swappable Protocol, In-Memory Implementation for Sprint 8

**Date:** Sprint 8, Subsystem 5
**Status:** Accepted

**Context:** Rate limiting needed a storage mechanism. Redis is not introduced until a later sprint; PostgreSQL round-trips on every request would add latency to a security-critical hot path.

**Decision:** `RateLimiter` is a `typing.Protocol` (`app/core/rate_limit.py`) with one method, `check(key, limit, window_seconds)`. `MemoryRateLimiter` (in-process, thread-safe sliding-window log) is the Sprint 8 implementation, injected via a FastAPI dependency (`get_rate_limiter()`).

**Documented limitation:** state is per-process — a multi-worker deployment has independent counters per worker, and a restart clears all state. Accepted at this project's current target scale (hundreds of companies, single-process dev/staging).

**Migration path (future Sprint):** `RedisRateLimiter` implements the identical `RateLimiter` Protocol using a Redis sorted set (`ZADD` / `ZREMRANGEBYSCORE` / `ZCARD` for the sliding window). Because every caller (routers, `AuthService`) depends only on the `RateLimiter` Protocol, swapping the implementation requires changing exactly one line — the object constructed and injected — with zero changes to any router or service.

---

## Known Bugs Found and Fixed — Sprint 8

Two structurally identical bugs were found during Subsystem 5 and Subsystem 6 testing, both caused by the same root mechanism: the request-scoped database session (`database/session.py:get_session()`, mirrored in `tests/conftest_api.py`) rolls back on **any** exception — including an intentionally-raised `HTTPException` the route itself is about to return as a normal 401/403/423/429 response.

1. **Subsystem 5 — Account lockout never actually persisted.** `AuthService._record_failed_login()` incremented `User.failed_login_attempts` and flushed it, then the caller (`login()`) raised `HTTPException(401)` for the wrong password. The session's rollback-on-exception discarded the increment on every single failed attempt, making the 5-attempt lockout threshold permanently unreachable in both tests and production. **Fix:** `_record_failed_login()` now calls `self._session.commit()` itself, in a small sub-transaction scoped to just that state change, before returning to the caller that raises.

2. **Subsystem 6 — Several audit events (`security.unauthorized_access`, `security.forbidden_access`, rate-limit and lockout events) were silently discarded.** Same root cause: `safe_log_event()` flushed but did not commit, and the events in question are logged immediately before the caller raises the corresponding `HTTPException`. **Fix:** `safe_log_event()` now commits immediately after a successful write (see ADR-040), so the audit row survives regardless of what the caller does next.

Both were caught by dedicated tests asserting the persisted database state (not just the HTTP response code), not by manual inspection — reinforcing that HTTP-response-only test assertions can pass while the underlying state change silently fails.

A third, unrelated bug was found and fixed during Subsystem 4 (User Management): `UserRead`'s Pydantic schema declared `id`/`company_id` as `str` instead of `UUID`, causing every user create/read response to fail model validation and surface as a misleading `409` (the `ValueError → 409` global exception mapping intercepted the Pydantic `ValidationError`). Fixed by correcting the field types to `UUID` (matching every other `*Read` schema in the codebase, e.g. `app/schemas/daily_log.py`).

---

## Pending Decisions (Future Sprints)

| Decision | Context | Sprint | Status |
|----------|---------|--------|--------|
| Redis vs in-memory caching | For caching LLM inference results (Groq or future local) | Sprint 9+ | Open |
| Redis-backed RateLimiter | Migrate `MemoryRateLimiter` to `RedisRateLimiter` per ADR-041's documented migration path | Sprint 9+ | Open |
| Celery vs FastAPI Background Tasks | For async audio processing | Sprint 7 | **Resolved — BackgroundTasks for Sprint 7; Celery migration explicitly deferred past Sprint 8 to Sprint 9 (not built this sprint — Sprint 8's actual scope was auth/authz hardening, not the task queue)** |
| asyncpg vs psycopg3 | For async PostgreSQL in FastAPI | Sprint 7 | **Resolved — asyncpg (see ADR-031); repository layer itself stays sync** |
| Row-level security | PostgreSQL RLS for multi-tenancy enforcement | Sprint 8 | **Resolved — application-layer `TenantScopedRepository` (ADR-037) chosen over PostgreSQL RLS; RLS remains open as a future defense-in-depth layer, not required given the ORM-mediated access pattern** |
| Alembic auto-generate vs hand-write migrations | Database migration strategy | Sprint 6 | Resolved (Sprint 6) |
| Docker multi-stage build | Optimize image size | Sprint 10+ | Open |
| JWT vs Session tokens | Authentication strategy | Sprint 7 | **Resolved — JWT access tokens (HS256) + opaque server-backed refresh tokens (ADR-035), see `app/core/security.py`.** |
| FAISS vs ChromaDB vs Weaviate | Vector store for RAG | Future | Open |
| Persist observability events | Write GenerationMetrics to DB / emit to queue | Sprint 9+ | Open |
| Email provider for password reset | Sprint 8 built the token lifecycle only (dev-mode raw-token response); real delivery is unimplemented | Sprint 9+ | Open |
