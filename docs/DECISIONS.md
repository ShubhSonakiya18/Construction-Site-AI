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
The original intent — zero token costs, no proprietary paid APIs — is preserved. However, the specific implementation changed: Ollama + Qwen2.5 was replaced by the **Groq free-tier cloud API** (`groq` Python package, originally the `llama-3.3-70b-versatile` model — **superseded post-Sprint-8** after that model was decommissioned; the current default is `openai/gpt-oss-120b`, see the "Known Bugs Found and Fixed — Post-Sprint-8" section below for the model migration and the blind-availability-check bug it caused). This was a deliberate trade-off:
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

## ADR-042: Grounded Project Q&A — Context-Stuffed Prompt, Not a Vector Store

**Date:** Post-Sprint-8, 2026-08-19
**Status:** Accepted

**Context:** Users want to ask free-form questions about a project ("were there any delays this week?") and get an answer drawn from that project's actual daily-log data, not from the LLM's general training knowledge. This is the classic hallucination-risk shape: an unconstrained prompt lets the model invent plausible-sounding numbers, dates, or names that were never in any log.

**Decision:** `POST /api/v1/projects/{id}/ask` retrieves the project's most recent *approved* daily logs (`DailyLogRepository.list_recent_with_children_scoped()`, limit 10, tenant-scoped) with all child tables eagerly loaded, flattens them into compact per-date fact dicts, and stuffs that directly into one prompt (`generation/prompts/project_qa.md`) with an explicit instruction: answer ONLY from the supplied context, and say so plainly when the context doesn't cover the question. `ProjectQAService` (`generation/services/project_qa.py`) is a fifth entry in `DEFAULT_SERVICE_REGISTRY`, reusing `BaseAIService`/`BaseLLMProvider.extract()` unchanged — no new LLM-calling code path.

The request pipeline runs every guard before touching the LLM or the database: Authentication → Authorization (`Permission.PROJECT_READ`) → Tenant Check → Project Check (404 if absent/cross-tenant) → Retrieve approved logs → Context Builder → Prompt → Groq → Answer. Retrieval is approved-logs-only by design: draft/rejected logs have not passed human review, so treating them as grounding context would let unreviewed AI extractions become authoritative answers.

**Why context-stuffing, not a vector store / RAG pipeline:** At the current scale (≤10 logs per answer, small structured records) the entire grounding context fits comfortably in one prompt with no retrieval-ranking step needed — there's nothing to rank when "the last 10 logs" is already the complete relevant set. Adding a vector database, embeddings, and a similarity-search step here would be infrastructure with no payoff at this data volume, and directly contradicts this project's established "no unnecessary infra, no paid services" posture (ADR-005, ADR-007, ADR-025).

**Migration trigger (future Sprint):** If a project's approved-log history grows large enough that "last 10 logs" is no longer a good proxy for "logs relevant to this question" (e.g. a user asking about something from 6 months and 200 logs ago), that becomes a new ADR for a retrieval step — not a silent change to this service's behavior.

**What tests can and cannot prove:** `tests/test_api_project_qa.py` asserts what context the endpoint hands to the model — non-empty, correctly shaped, scoped to the requested project and tenant. Whether a real LLM then obeys the "answer only from context" instruction is the prompt's responsibility, not something a mock engine can validate; that was confirmed instead via live testing against real Groq (see the Known Bugs section below) — a budget question and a client-contact question, neither answerable from the seeded log, both correctly declined rather than fabricated an answer.

**Content-length floor:** `ContentValidator`'s per-service minimum length for `PROJECT_QA` was initially set to 15 chars by estimate, then lowered to 10 after live testing produced a correct, truthful refusal of exactly "Not covered." (12 chars) — a stricter floor would have rejected precisely the honest, non-hallucinated answers the grounding instruction is designed to produce.

---

## Known Bugs Found and Fixed — Post-Sprint-8 (2026-08-19)

Discovered while verifying the grounded Q&A feature above against a real Groq call — none of these were caught by the 913-test Sprint 8 suite because every existing generation/extraction test uses `MockLLMProvider`, and the one test that would have caught it was itself broken (see below).

1. **Critical — the configured Groq model was decommissioned.** `llama-3.3-70b-versatile` (the hardcoded default in `extraction/config.py`, `generation/config.py`, and `.env`) no longer exists on Groq's API; every real `extract()` call returned `404 model_not_found`. This silently broke extraction, all 4 generation services, `/daily-logs/{id}/generate`, and the audio pipeline's extraction step — in production, not just in this feature. **Fix:** migrated the default model to `openai/gpt-oss-120b` everywhere it was hardcoded, plus `.env`/`.env.example`.

2. **`GroqEngine.is_available()` could not detect bug #1.** It called `models.list()` to confirm the API key was valid, then returned `True` unconditionally — never checking whether the *configured model* was in that list. `/api/v1/health` reported `groq_extraction_engine: "up"` the entire time real calls were 404ing, which is precisely the failure mode a health check exists to catch. **Fix:** `is_available()` now checks `self._model` against the live model list from Groq and returns `False` (logging the available alternatives) if it's not present.

3. **The one test that exercises a real Groq call had never actually run.** `tests/test_extraction_pipeline.py` gates its live-API test on `HAS_GROQ = bool(os.getenv("GROQ_API_KEY"))`, computed at import time. Only `app/main.py` calls `load_dotenv()`; pytest never goes through that module, so `GROQ_API_KEY` was always unset under pytest and the test silently, permanently skipped — including in the "913 passed, 1 skipped" count reported as Sprint 8's baseline. Bug #1 could have shipped past this exact test with zero indication. **Fix:** `tests/conftest.py` now calls `load_dotenv(override=False)` for the whole suite; the test now runs and passes against the corrected model.

**Root-cause pattern across all three:** a health check that validates credentials but not configuration, and a regression test that was gated shut rather than gated correctly, together let a real outage hide behind an all-green test suite and an "up" status page. Neither individually would have hidden it — the health check's blind spot and the test's silent skip had to both be present.

---

## ADR-043: Celery Retry at the Task-Wrapper Layer, Not Inside run_pipeline()

**Date:** Sprint 9
**Status:** Accepted

**Context:** `docs/NEXT_SPRINT.md` Deliverable 1 calls for "retry policy for transient failures (Groq rate limits, Whisper OOM)." `run_pipeline()` (Sprint 7, `app/services/pipeline_service.py`) was deliberately shaped so migrating from `BackgroundTasks` to Celery would be a decorator + call-site change, not a rewrite — but it also never raises: every stage failure is caught internally and converted to `AudioFile.processing_status = "failed"`. A naive `autoretry_for=(Exception,)` wrapped around a function that never raises would never actually fire.

**Decision:** Retry lives in `app/tasks/pipeline_tasks.py`'s `run_pipeline_task`, not inside `run_pipeline()` itself. This is correct, not just convenient: `run_pipeline()`'s stage 2 (`ExtractionPipeline.extract()`) already retries the Groq call internally with its own exponential backoff before ever returning a failure — by the time `run_pipeline()` observes that failure, it has already survived N in-process retries and is a considered result, not a raw transient error worth repeating. What the Celery-level retry protects against instead is the failure surface `run_pipeline()`'s own per-stage try/except blocks do NOT cover: the initial `get_engine()`/session setup, and stage 5 (persisting generation outputs), both unguarded — plus a genuine worker-process crash (OOM-killed loading a Whisper model), which bypasses Python exception handling entirely and is instead caught by `task_acks_late=True` + `task_reject_on_worker_lost=True` re-queuing the task.

**Consequence:** `run_pipeline()`'s function body required zero changes for the Celery migration, exactly as Sprint 7 designed it to. The retry policy is a genuinely separate concern from the queuing mechanism, living in the one place (`pipeline_tasks.py`) that knows about both Celery and the stages `run_pipeline()` doesn't self-guard.

---

## ADR-044: RedisRateLimiter — Lua Script for Cross-Process Atomicity

**Date:** Sprint 9
**Status:** Accepted (implements the migration ADR-041 already planned)

**Context:** ADR-041 (Sprint 8) specified the target shape: a Redis sorted set (`ZADD`/`ZREMRANGEBYSCORE`/`ZCARD`) implementing the same `RateLimiter` Protocol as `MemoryRateLimiter`. `MemoryRateLimiter` gets its atomicity from an in-process `threading.Lock` — the equivalent guarantee is needed across processes now that Redis is shared state, or concurrent requests for the same rate-limit key could each read a stale `ZCARD` before either's `ZADD` lands, letting more than `limit` requests through under load.

**Decision:** `RedisRateLimiter.check()` runs all four Redis operations (prune expired, count, add, set expiry) as a single Lua script via `EVAL`, executed atomically by Redis itself — no separate round-trips a race could interleave between. A unique member per attempt (timestamp + a UUID4 suffix, not just the timestamp) prevents two attempts in the same millisecond from colliding as the same sorted-set member and under-counting.

**Verification:** `tests/test_redis_rate_limiter.py::TestRedisRateLimiterAtomicity` fires 30 concurrent requests (real threads, real Redis) against a limit of 10 and asserts exactly 10 succeed — a regression here would show up as more than 10 successes, which a single-threaded test cannot catch.

**Consequence:** Solves `MemoryRateLimiter`'s documented Sprint 8 limitation (per-process counters, N workers = N× the effective limit, reset on restart) with zero changes to any caller — `get_rate_limiter()`'s callers depend only on the `RateLimiter` Protocol, per ADR-041's original design intent.

---

## ADR-045: EmailSender — Protocol with a Dev-Console Default, Not a Mandatory SMTP Dependency

**Date:** Sprint 9
**Status:** Accepted

**Context:** `docs/NEXT_SPRINT.md` Deliverable 2 requires real email delivery for password reset while explicitly preserving "no paid SaaS." Sprint 8 had no email provider at all and worked around it by returning the raw reset token directly in the API response outside production — a real security smell (the token is a bearer credential; putting it in an HTTP response body is strictly worse than putting it in an email only the recipient's inbox holds).

**Decision:** `EmailSender` is a `typing.Protocol` (mirroring `RateLimiter`'s ADR-041 precedent) with `DevConsoleEmailSender` (logs the email; zero setup) and `SMTPEmailSender` (real `smtplib` delivery, any provider — free-tier or self-hosted, never vendor-specific) as its two implementations, selected by whether `Settings.smtp_host` is configured. The Sprint 8 raw-token-in-response behavior becomes explicit opt-in via `Settings.expose_raw_reset_token_in_response` (default off) rather than environment-implicit — per the doc's own suggested path.

**Why NOT a process-wide singleton** (unlike `MemoryRateLimiter`/`RedisRateLimiter`): a `RateLimiter`'s entire purpose is sharing counters across requests within one process; an `EmailSender` has no cross-request state to share, and `SMTPEmailSender.send()` opens a fresh connection per call regardless. A singleton here would only introduce a bug: because tests construct their own `Settings` per test, caching the first call's choice would let whichever test ran first silently decide every later test's sender. `get_email_sender()` is a per-request FastAPI dependency instead — "per call" in practice means "per request," which is exactly the right granularity, with none of the caching hazard.

**Consequence:** A `send()` failure never raises (a delivery failure caught internally and logged) — required so `AuthService.forgot_password()`'s account-enumeration-avoidance guarantee (identical response whether or not the email exists) can't be defeated by a distinguishable failure mode when the email does exist but delivery breaks.

---

## ADR-046: PDF Export — reportlab, Not weasyprint

**Date:** Sprint 10, Deliverable 4
**Status:** Accepted

**Context:** Sprint 10 needed to export the `safety_talk` document (Markdown text) as a downloadable PDF — the first PDF generation of any kind in this codebase. Two realistic free/open-source options: `weasyprint` (renders HTML/CSS to PDF — a clean Markdown→HTML→PDF pipeline with rich, easy styling) and `reportlab` (pure Python, builds a PDF by direct API calls — more manual layout, no CSS).

**Decision:** `reportlab`. `weasyprint` depends on GTK3/Pango/Cairo native libraries that are not reliably `pip install`-able on Windows — a well-documented source of install friction (missing DLLs, PATH issues) outside WSL or Docker, and this project's primary dev environment is native Windows (see `docs/BACKEND_STARTUP.md`'s whole startup sequence, which assumes no WSL/Docker requirement for the Python side — Docker is used only for Redis, Sprint 9). `reportlab` installs with a plain `pip install reportlab` and needs no system dependency, at the cost of writing layout code by hand instead of CSS.

**Consequence:** `app/services/pdf_export.py`'s `render_markdown_pdf()` hand-parses the specific Markdown shape `generation/prompts/*.md`'s REQUIRED SECTIONS convention actually produces (`##` headers, `**bold**`, `- ` bullets) rather than depending on a general Markdown library — see that module's docstring for why a general parser would be solving a problem this codebase doesn't have. A real, unanticipated consequence of the reportlab choice surfaced immediately in live testing — see Known Bug #2 below.

---

## ADR-047: One Schedule Per Project, No Revision History (Sprint 11)

**Date:** Sprint 11, Deliverable 1
**Status:** Accepted

**Context:** `docs/NEXT_SPRINT.md` left open whether `ProjectSchedule` should support multiple schedule revisions (replanning history) or exactly one active schedule per project.

**Decision:** Exactly one schedule per project, enforced with a `UniqueConstraint` on `project_schedules.project_id` at the database level — not just an application-layer convention. `ProjectSchedule` also does not get `SoftDeleteMixin`: a schedule that's no longer wanted is a real, undecided design question (replace it in place? archive and recreate?) that adding soft-delete now would implicitly answer without that decision actually having been made.

**Consequence:** If multiple schedule revisions become a real product need later, `project_schedules` gains a `status`/`is_active` column and the unique constraint changes to `(project_id, is_active)` where `is_active` — an additive migration, not a rewrite. `build_schedule_for_project()` (`database/repositories/schedule.py`) already returns the existing schedule unchanged if one exists, rather than erroring, so the "one schedule" invariant reads as "idempotent creation," not "creation fails on retry."

---

## ADR-048: Schedule Variance and Delay Propagation Are Pure Computation, Not an AI Service (Sprint 11)

**Date:** Sprint 11, Deliverables 3 and 6
**Status:** Accepted

**Context:** `docs/NEXT_SPRINT.md`'s example variance message — "you're 5 days behind on framing" — reads like natural-language output, which could plausibly go through `AIServiceManager` as a 6th `ServiceType`. Deliverable 6 (delay impact prediction) uses the word "prediction," which could be misread as inviting an ML or LLM approach.

**Decision:** Both are pure Python arithmetic (`app/services/schedule_service.py`'s `compute_variance()` and `propagate_delay_impact()`), with no `ServiceType`, no `AIServiceManager` call, and no Groq round-trip. Variance messages are built from an f-string template over real date deltas already in the database — not generated text. Delay-impact "prediction" is a breadth-first graph walk over `dependency_graph.json`'s edges propagating a known day-count forward, matching CPM's own definition of how a delay on a chain of dependent tasks moves a project's end date — not a forecast produced by a model.

**Consequence:** Both functions are deterministic, have no external API dependency (no Groq quota/rate-limit/latency to account for), and are fully unit-testable against small hand-built fixtures with an exact expected answer (`tests/test_schedule_variance.py`, `tests/test_critical_path.py`) — the same "no AI where deterministic logic suffices" posture ADR-005 and ADR-007 already established, applied consistently rather than reached for by default because generation/ existed and was convenient to extend.

---

## ADR-049: Per-Project Critical Path Diverges From dependency_graph.json's Generic Path — By Design (Sprint 11)

**Date:** Sprint 11, Deliverable 5
**Status:** Accepted

**Context:** `knowledge/dependency_graph.json` ships a precomputed "typical" critical path (97 days, 13 nodes) as reference data. Running a real CPM forward/backward pass (`compute_critical_path()`) over the same 23 nodes / 33 edges for the seeded sample project produces a **108-day** path through 14 nodes — different both in total length and in which parallel-track tasks (`hvac_rough_in`/`plumbing_finish` rather than the file's `electrical_rough_in`/`electrical_finish`) end up on it.

**Decision:** This divergence is correct and expected, not a bug to reconcile. `dependency_graph.json`'s "typical" path is a hand-authored illustrative example across three parallel rough-in/finish tracks that happen to have equal typical durations in the reference data; a real CPM pass has no reason to prefer one parallel branch over another except actual duration and lag, and will pick whichever branch is genuinely longest. `docs/NEXT_SPRINT.md` anticipated exactly this ("A per-project critical path... is a real computation... may differ from the generic `typical_total_days`").

**Consequence:** `ScheduleTask.is_on_critical_path` and `ProjectSchedule.critical_path_total_days` are always sourced from `compute_critical_path()`'s own output, never copied from `dependency_graph.json`'s `critical_path` key — that key remains useful only as a human-readable illustrative default, not as ground truth for any per-project schedule. A related correctness fix caught during this same implementation: `critical_path_total_days` must be the latest `planned_end_date` offset across *all* tasks (which already folds in inter-task lag, e.g. the 7-day foundation→framing concrete-cure lag), not a sum of critical-path task durations alone — the naive sum undercounted the real project span by exactly the lag amount.

---

## ADR-050: Inventory is Project-Scoped, Not Global — and Supplier Is a Plain String (Sprint 12)

**Date:** Sprint 12, Deliverables 1 and 6
**Status:** Accepted

**Context:** `docs/NEXT_SPRINT.md` left two related design choices open for Deliverable 1: whether `inventory_items` should track quantity globally (one company, one running total across every project) or per-project, and whether suppliers need their own normalized table now that purchase orders reference them.

**Decision:** Project-scoped inventory — a `UniqueConstraint` on `(project_id, material_name)`, matching how `LogMaterialUsed` is already scoped per log per project, not globally per company. "Cement bags" on two different projects are two independent rows with independent quantities; a company-wide rollup, if ever needed, is a read-time aggregation across projects, not a schema decision made now. `preferred_supplier` / `purchase_orders.supplier` stay plain strings, matching `LogMaterialUsed.supplier`'s existing shape, not a `suppliers` table with contact details or credentials — the same documented-denormalization reasoning `database/models/project.py`'s `client_name` docstring already applies to an analogous case.

**Consequence:** A material genuinely shared across every project a company runs (e.g. a company that only ever buys from one lumber yard) still gets one `inventory_items` row per project, each independently tracking its own on-hand quantity — this is a deliberate trade-off favoring the "what does THIS project have on hand" question the sprint's actual deliverables need answered, over a "what does the company have across all sites" question nothing in this sprint's scope asks. If a real cross-project rollup or a genuinely shared-supplier-relationship need surfaces later, both are additive: a company-scoped view/aggregation query for the former, a `suppliers` table for the latter — neither requires reworking `inventory_items`' existing rows or its `(project_id, material_name)` uniqueness.

---

## ADR-051: Auto-Generated Reorder Quantity Uses a Flat Multiple, Not a Consumption-Rate Formula (Sprint 12)

**Date:** Sprint 12, Deliverable 3
**Status:** Accepted

**Context:** `docs/NEXT_SPRINT.md` left the auto-generated purchase order's suggested quantity formula open: "reorder_point × 2, or driven by typical_lead_time_days × average daily consumption rate if that's computable from log history."

**Decision:** `reorder_point × 2` (`_AUTO_REORDER_MULTIPLE = 2` in `database/repositories/inventory.py`). A consumption-rate-driven formula needs a real history of `LogMaterialUsed` events over time to compute a meaningful daily rate — for a project early in its lifecycle (the exact seeded sample project used throughout this sprint's live verification has, at most, a handful of approved logs), that rate would be noisy or undefined on the first few reconciliations, which is precisely when an auto-suggested reorder quantity is most useful. A flat multiple of the already-configured `reorder_point` gives an immediately sensible restock suggestion — "you've hit half your comfortable buffer, order enough to refill it twice over" — without depending on data that may not exist yet.

**Consequence:** This is explicitly a starting point, not a claim that `reorder_point × 2` is the right quantity for every material in every project — a human reviewing a `status="draft"` auto-generated PO (which every such PO always is; see `PurchaseOrder.status`'s doc comment) is expected to adjust the quantity before submitting if it looks wrong for that specific case, exactly the same trust relationship `MaterialReminderService`'s "Source TBD" placeholder already establishes for supplier gaps. A consumption-rate-driven formula remains a reasonable future refinement once a project has enough approved-log history for the rate to be meaningful — worth revisiting as its own decision if it becomes a real friction point, not built speculatively now.

---

## ADR-052: Completion Trend Gains a Projected-Completion Overlay — Same Endpoint, Not a New One (Sprint 13)

**Date:** Sprint 13, Deliverable 1
**Status:** Accepted

**Context:** `docs/NEXT_SPRINT.md` left open whether Deliverable 1 ("project completion trends") means the existing `GET /projects/{id}/analytics` completion-trend series rendered with more sophistication, or a genuinely new metric/endpoint.

**Decision:** Extend the existing response, not a new endpoint. `ProjectAnalyticsResponseData` gains `projected_completion_date` and `delay_adjusted_completion_date` (both `Optional[date]`, sourced directly from Sprint 11's `ProjectSchedule` when one exists for the project) alongside the existing `completion_trend` series. `AnalyticsPanel.tsx`'s "Completion trend" chart shows both dates as a text summary above the chart, not a graphical reference line: `completion_trend`'s x-axis is a categorical list of the project's actual log dates (a string axis, not a true time scale), and a projected/delay-adjusted date almost never falls exactly on an existing log date — a recharts `ReferenceLine` positioned against a category axis either silently fails to render or misplaces itself when the target value isn't one of the axis's own categories. A plain text line ("Planned completion: 2026-06-26 · delay-adjusted: 2026-07-02") states the same information accurately regardless of where those dates fall relative to the logged history, which the chart's own x-axis literally cannot represent. This is the first place in the app these two data sources (Sprint 10's log-derived analytics, Sprint 11's schedule) are shown together.

**Consequence:** A project with no schedule yet (Sprint 11's `POST /projects/{id}/schedule` was never called) simply omits both new fields — `null`, not an error — since analytics has never required a schedule to exist. Matches the pattern every optional cross-feature field in this codebase already follows (e.g. `daily_log_id` on `AudioStatusResponseData` staying `null` until a pipeline run actually produces one). No new endpoint means no new tenant-scoping code path to get wrong, and the frontend's existing single `getProjectAnalytics()` call already has everything Deliverable 1 needs without an extra request.

---

## ADR-053: Delay-by-Trade Uses a Broad "On Site That Day" Join, Not Text-Matching (Sprint 13)

**Date:** Sprint 13, Deliverable 2
**Status:** Accepted

**Context:** `docs/NEXT_SPRINT.md` flagged this as a real design decision: `LogDelay` has no `trade` column, so cross-referencing delays against trades requires picking a join path. Two candidates: (a) broad — every `LogTradeOnSite` row for the same `daily_log_id` as the delay ("which trades were present the day this delay happened"), or (b) narrow — text-matching `LogDelay.tasks_affected` (an unstructured JSON list of free-text strings, per that column's own doc comment) against `LogWorkItem.task_description` to infer which specific trade's work was blocked.

**Decision:** Broad join. `DailyLogRepository.get_delay_frequency_by_trade_scoped()` joins `LogTradeOnSite` to `LogDelay` on a shared `daily_log_id`, credits every trade present that day with every delay recorded that day, and aggregates `(trade, delay_count, total_hours_lost)` — the same shape and tenant-scoping pattern as Sprint 10's `get_delay_frequency_scoped()`. `tasks_affected` is free text with no controlled vocabulary tying it to `LogTradeOnSite.trade`'s enum; matching one against the other would be exactly the kind of fragile heuristic ADR-005/ADR-007/ADR-048 have consistently ruled out in favor of deterministic joins over real foreign keys. A trade being on site the day a delay happened is a verifiable fact directly in the schema; which trade's work a delay specifically blocked is not reliably recoverable without either an LLM guess or a new structured field — neither of which this sprint's constraints permit (no new schema, no AI calls for analytics).

**Consequence:** A log with multiple trades on site and multiple delays over-attributes — every trade present gets credited with every delay that day, whether or not that trade's own work was actually the one blocked (e.g. a material-shortage delay affecting only framing still counts against an electrician who happened to be on site the same day). This is a known, documented imprecision, not a bug: the field is framed as "delay frequency by trade" (co-occurrence), not "delays caused by trade" (attribution), and the response field is named `delay_frequency_by_trade` rather than something implying causation. If a future sprint adds a structured trade reference on `LogDelay` (e.g. captured at extraction time), this method should be revisited rather than assumed permanent.

---

## ADR-054: Safety Incident Trends Report Incident-Days Only, and an Unassessed OSHA Flag Doesn't Count as "Not Recordable" (Sprint 13)

**Date:** Sprint 13, Deliverable 3
**Status:** Accepted

**Context:** `LogSafetyIncident.osha_recordable` is a nullable boolean — an incident can be explicitly recordable (`True`), explicitly not (`False`), or not yet assessed (`NULL`, the common case immediately after extraction, before a safety officer reviews it). `docs/NEXT_SPRINT.md` asked for "incident count over time... plus a breakdown by incident_type and osha_recordable" without specifying how the trend series should handle days with zero incidents, or how the nullable flag should be counted.

**Decision:** Two fields, mirroring Deliverable 1/2's time-view/category-view split: `safety_incident_trend` (per log_date, approved logs only) and `safety_incident_breakdown` (per incident_type). Both report `incident_count` and `osha_recordable_count` side by side. `safety_incident_trend` includes only days that actually recorded at least one incident — an incident-free day is absent from the series, not present with a `0`, matching `get_delay_frequency_scoped()`'s own precedent of only reporting categories that occurred. `osha_recordable_count` counts strictly `osha_recordable = True` rows (`COUNT(CASE WHEN osha_recordable IS TRUE THEN 1 END)`, not a plain `COUNT` over a boolean filter that would also silently miss `NULL` correctly, but is written explicitly here so the intent — not just the SQL semantics — is unambiguous at the call site) — an unassessed incident still counts toward `incident_count` (it happened, it needs review) but never toward `osha_recordable_count`, since "not yet assessed" and "assessed and found not recordable" are different facts and conflating them would understate exposure in one direction or overstate compliance risk in the other, either of which is worse than an under-informative `NULL`.

**Consequence:** Unlike the delay-by-trade and completion-trend sections, `AnalyticsPanel.tsx`'s "Safety incidents" section is never hidden, even when both arrays are empty — it explicitly states "No safety incidents recorded on this project's approved logs." A safety section that silently disappears when there's nothing to show is indistinguishable from a safety section that was never wired up at all; for compliance-adjacent data, an explicit zero is worth the extra UI branch that every other empty-list section in this panel skips.

---

## ADR-055: "Productivity" Means Average Logged Task-Completion Percent by (Stage, Trade) — Nothing Cost- or Time-Adjusted (Sprint 13)

**Date:** Sprint 13, Deliverable 4
**Status:** Accepted

**Context:** "Productivity" is not a field anywhere in the schema, and the word means different things in construction (units per labor-hour, cost per unit, schedule adherence, ...). `docs/NEXT_SPRINT.md` flagged this as the one Sprint 13 deliverable needing a genuinely new metric definition, and named the most defensible option available without new fields: `LogWorkItem.task_completion_percent` averaged per `(current_stage, trade)`.

**Decision:** `get_productivity_by_stage_and_trade_scoped()` computes exactly that — `AVG(task_completion_percent)` grouped by `(DailyLog.current_stage, LogWorkItem.trade)`, over approved logs, excluding rows where `task_completion_percent` was never recorded (a `NULL` there means "not reported," not "0% complete," so including it would silently drag every average down). Unlike Deliverable 2's `LogDelay`→`LogTradeOnSite` join, `LogWorkItem.trade` is a direct column on the same row as `task_completion_percent` — this is a real per-row join, not a same-day co-occurrence approximation, so no broad/narrow tradeoff applies here. The response includes `work_item_count` alongside every average specifically so a caller can tell "92% from one work item" apart from "92% from thirty" — an unweighted average with no attached sample size is the kind of number that gets over-trusted.

**Consequence:** This is explicitly *not* labor productivity in the industry-standard sense (units installed per man-hour), not cost-adjusted, and not compared against a planned or budgeted rate — none of those are computable from today's schema without new fields Sprint 13's constraints don't permit (no new tables). A `(stage, trade)` pair averaging 60% either means the trade is genuinely behind, or means most of its work items were still mid-task when logged and would show higher on a later day's log for the same stage — the metric can't distinguish "slow" from "not done yet as of this log," because `task_completion_percent` is a point-in-time snapshot per work item, not a rate. The field and its UI label should keep language close to "average reported completion," not bare "productivity," to avoid implying a comparison this data can't support. If a future sprint wants true throughput (units/hour) or cost-adjusted productivity, that requires either new structured fields at extraction time or joining against Sprint 12's `LogMaterialUsed.unit_cost_usd`/`quantity` — both out of scope here.

---

## ADR-056: Client-Role Analytics Curation Is Frontend-Only, Matching Sprint 10's "Same App, Fewer Buttons" Precedent (Sprint 13)

**Date:** Sprint 13, Deliverable 5
**Status:** Accepted

**Context:** `docs/NEXT_SPRINT.md` asked which of Deliverables 1–4's new fields a `client`-role user should see on `GET /projects/{id}/analytics`, and whether curation should happen as (a) role-conditional rendering in the frontend over an unchanged response, or (b) a backend router-level omission of fields for non-staff roles. `client` already holds `Permission.PROJECT_READ` and `Permission.DAILY_LOG_READ` (`app/core/permissions.py`) and nothing else relevant — Sprint 10, Deliverable 7 already established the precedent for this exact question on a different feature: the known-bugs entry for that sprint (`docs/DECISIONS.md`, Post-Sprint-8 section) describes hiding Approve/Reject/Generate/Mark-as-sent buttons and the Record nav link from a `client`-role user in the frontend (`frontend/src/auth/roles.ts`'s named role sets), explicitly *not* a new backend authorization system — "the backend's `require_permission()` remains the real boundary regardless of what the frontend shows."

**Decision:** Option (a), following that precedent exactly. `GET /projects/{id}/analytics` returns the identical, uncurated response to every role that can call it — no router-level field omission. `frontend/src/auth/roles.ts` gains `STAFF_ONLY_ANALYTICS_ROLES` (owner, admin, project_manager, foreman, safety_officer, system_admin — every role except `client`), and `AnalyticsPanel.tsx` uses it to hide two sections from a `client`-role viewer: **Safety incidents** (incident-level detail, including near-misses and unresolved OSHA-recordability, is staff-internal risk information a client doesn't need and a GC likely doesn't want surfaced pre-resolution) and **Delay frequency by trade** (ADR-053 already documents this field's broad-join imprecision — crediting a trade with a delay merely for being on site that day — which is an acceptable internal planning signal but too easily misread by a client as "this subcontractor is the problem"). Completion trend, planned/delay-adjusted completion dates, plain delay-type frequency, and productivity-by-stage-trade all remain visible to `client` — these describe project progress and pace, which is exactly what a client-facing "progress portal" is for.

**Consequence:** No new backend code path, no new tenant-scoping surface to get wrong, and the frontend's existing single `getProjectAnalytics()` call is unchanged — curation is purely which of the already-fetched sections render. This also means a `client` user with direct API access (not just the browser UI) still receives the full response; the boundary here is explicitly a UX curation for the dashboard, not a data-confidentiality guarantee, the same tradeoff Sprint 10's precedent already accepted for documents and actions. If safety or delay-attribution data is later judged to need an actual confidentiality boundary (not just a curated default view), that would need a real backend permission check and is a different, larger decision than this deliverable's scope.

---

## ADR-057: Sprint 13 Stays Per-Project-Only — No Company-Wide Analytics View (Sprint 13)

**Date:** Sprint 13, Deliverable 6
**Status:** Accepted

**Context:** `docs/NEXT_SPRINT.md` flagged this as an explicit open question, not an assumed deliverable: does "Analytics Dashboard" mean richer per-project analytics (Deliverables 1–5, all still scoped to one project) or a new cross-project, company-wide dashboard (e.g. "average completion % across all active projects," "which project has the most delays this month")? The roadmap's five bullet points — completion trends, delay pattern analysis by trade, safety incident trends, productivity by stage/trade, client-facing progress portal — all read naturally as per-project enrichment; none of them say "across projects." The instruction was to default to per-project only, and only pull a company-wide view into this sprint if a concrete need surfaced during implementation of Deliverables 1–5.

**Decision:** No company-wide view. Deliverables 1–5 were implemented and none of them surfaced a concrete need for cross-project aggregation — every new field (`projected_completion_date`, `delay_frequency_by_trade`, `safety_incident_trend`/`breakdown`, `productivity_by_stage_trade`) is naturally a property of one project's own logs and schedule, and the client-facing curation decision (ADR-056) was itself scoped per-project (a client only ever has one project's worth of data to see, not a cross-project view of a GC's whole book of business — that would leak information about a GC's other clients' projects to this client, an actual confidentiality problem `PROJECT_READ`'s per-project scoping already prevents). `GET /projects/{id}/analytics` remains the only analytics endpoint; no `GET /companies/{id}/analytics` or similar was added.

**Consequence:** A company-wide dashboard (e.g. "which of our active projects is most behind schedule right now," useful to an `owner`/`admin` managing a portfolio) remains a real, plausible future need — it just isn't this sprint's. Building it would mean either a genuinely new endpoint aggregating across a company's `Project` rows (not a trivial per-project loop client-side, since that scales requests linearly with project count) or a new repository method grouping by `company_id` directly. Flagged here as a candidate for a future sprint rather than silently deferred with no record of the decision being made.

---

## ADR-058: Cost Extraction Asks the LLM Only for Reported Figures — Derived Totals Are Computed Server-Side (Sprint 14)

**Date:** Sprint 14, Deliverable 1
**Status:** Accepted

**Context:** `knowledge/construction_daily_log_schema.json` has always defined a complete 8-field `financials` object — its own `description` reads *"Primarily populated by the cost tracking module (future sprint)"* — and `SchemaValidator` has always validated against it. But no real voice log has ever had a populated `financials`, because `extraction/prompts/builder.py`'s `_build_schema_reference()` — the text block actually sent to Groq — never mentioned the section at all. Persistence (`DailyLogRepository.create_from_extraction_result()`) and read (`GET /daily-logs/{id}`) already handled the field wholesale. The gap was exactly one file, and three of the eight fields are derived values rather than things a foreman would state.

**Decision:** Add a `financials` block to the extraction prompt asking for only the five *reported* fields: `daily_labor_cost_usd`, `daily_material_cost_usd`, `daily_equipment_cost_usd`, `daily_subcontractor_cost_usd`, `financial_notes`. Deliberately **omit** the three derived fields:
- `cumulative_spend_to_date_usd` and `budget_remaining_usd` — a single transcript cannot know a running total across prior logs. Asking an LLM for a number it has no way to compute invites a confident fabrication, the exact failure the system prompt's "never guess or invent values" rule exists to prevent. These are read-time projections over prior approved logs (Deliverable 2's territory), following the same never-persisted pattern as Sprint 11's schedule variance and Sprint 12's lead-time warnings.
- `daily_total_cost_usd` — computable exactly as the sum of the four component fields. `dataset_generation_framework`'s own `VAL-FIN-001` validation rule exists specifically to catch generated records where this total disagrees with its components; rather than ask the LLM to add four numbers and then validate its arithmetic, the app computes it. There is no reason to trust an LLM's addition when the code can do it deterministically.

**Consequence:** `financials` stays a JSON column rather than becoming normalized columns or its own table — unlike `change_orders` (ADR-059), a `financials` object has no independent identity, no lifecycle, and no status that changes after the log is approved; it is exactly one immutable object per log, the same shape `weather` and `tomorrow_plan` already use successfully as JSON. A log whose transcript mentions no money at all gets `financials` with all-null fields (or the key absent entirely) rather than zeros — null means "not reported," and treating it as `$0` would silently understate project spend in any aggregation built on top. Material cost now has two potential sources — the LLM's `daily_material_cost_usd` estimate and the real `LogMaterialUsed.quantity_used × unit_cost_usd` structured data from Sprint 6 — and any analytics built on these should prefer the structured data where both exist, since real recorded line items beat a spoken estimate of the same number.

---

## ADR-059: Change Orders Are Normalized Out of `client_communication` — Status Outlives the Log That Reported It (Sprint 14)

**Date:** Sprint 14, Deliverable 4
**Status:** Accepted

**Context:** `client_communication.change_orders[]` is fully defined in `knowledge/construction_daily_log_schema.json` (`change_order_id`, `description`, `estimated_cost_impact_usd`, `estimated_schedule_impact_days`, and a `status` enum of `pending_approval` | `approved` | `rejected` | `under_negotiation`), but like `financials` it was never asked for in the extraction prompt, so no log has ever recorded one. `database/models/log_items.py`'s own module docstring states the normalization rule this codebase has followed since Sprint 6: *"Will we ever need to query an individual element independently? If yes → normalize. If no → JSON column."* — and it explicitly listed `client_communication` among the JSON-kept fields, on the assumption that it is "always consumed as a complete object by AI generators; no sub-field queries."

**Decision:** That assumption holds for every part of `client_communication` **except** `change_orders`, which is normalized into a new `LogChangeOrder` table (migration `007`) while the rest of the object stays JSON. The deciding factor is not query convenience but **mutability after log approval**: a change order discussed today commonly moves from `pending_approval` to `approved` or `rejected` days or weeks later, long after the daily log that first reported it has been approved and effectively frozen. A JSON array on an approved `DailyLog` has nowhere to record that transition without mutating an already-approved log's payload in place — something nothing else in this codebase does, and something that would silently rewrite the historical record of what was actually said that day. A separate table lets the log stay an immutable record of the conversation while the change order carries its own lifecycle, exactly as Sprint 12's `PurchaseOrder.status` does (also a status that moves after its originating event, also given its own table for that reason). The extracted `client_communication` JSON keeps its verbatim `change_orders` array as the record of what extraction reported; the table is the queryable, mutable source of truth going forward.

**Consequence:** `LogChangeOrder` follows `LogDelay`/`LogSafetyIncident`'s shape exactly (UUID PK, `daily_log_id` FK with `ondelete="CASCADE"`, `TimestampMixin`, indexes on `daily_log_id` and `status`) — no new patterns introduced. `change_order_id` is a plain nullable string, not a foreign key: it is the GC's own external paperwork reference (e.g. "CO-014"), frequently absent when a change is first discussed, and never a key into any table here — the same "plain string, no normalized table" reasoning ADR-050 applied to supplier names. A change order extracted with no description is skipped rather than persisted with an empty required field: unlike a delay or hazard (where a generic `"other"` type still meaningfully records "something happened, details unclear"), a change order with no description carries no information at all and would only be noise in cost reporting. This is the first time a nested field inside a JSON column has been normalized out while its parent stays JSON — the module docstring in `database/models/log_items.py` was updated to say so explicitly, so the rule reads as "per-array" rather than "per-column" for future maintainers.

---

## ADR-060: Earned Value Management Definitions — Log-Reported Completion for EV, Linear Accrual for PV (Sprint 14)

**Date:** Sprint 14, Deliverable 3
**Status:** Accepted

**Context:** `docs/NEXT_SPRINT.md` named real EVM terms (PV, EV, AC, CPI, SPI) and flagged that each needs mapping onto what this schema can actually compute, since none of them are stored directly. Two real ambiguities exist: EV could derive from Sprint 10's log-reported `overall_project_completion_percent` or from a schedule-stage-based percent-complete (Sprint 11); PV requires an assumption about how cost accrues across a schedule that has no per-stage budget breakdown, only a single `Project.contract_value_usd` total (Sprint 14, Deliverable 2's own finding).

**Decision:**
- **AC (Actual Cost)** = Deliverable 2's `total_spend_to_date_usd` — the already-computed cumulative sum of reported daily costs. Not re-derived; EVM reuses the one number this sprint already trusts as "how much has actually been spent."
- **EV (Earned Value)** = `contract_value_usd × (overall_project_completion_percent / 100)`, using the most recent approved log's self-reported completion percent — the same figure `completion_trend` (Sprint 10) already shows as "how much is done." The alternative (a schedule-stage-based percent-complete from Sprint 11) was rejected specifically because it would let EV silently disagree with what every other part of this same analytics response already calls "completion" — a dashboard showing two different "percent done" numbers side by side is a worse outcome than picking one and being consistent about it.
- **PV (Planned Value)** = `contract_value_usd × elapsed_schedule_fraction`, where the fraction is `(as_of − schedule_start_date) / (projected_completion_date − schedule_start_date)`, clamped to `[0, 1]`. This assumes cost accrues **linearly** across the schedule — the same magnitude of spend every day regardless of what stage is underway. That assumption is false in construction (site prep and punch-list days cost far less than framing or MEP rough-in days) but is the only assumption computable without inventing a per-stage budget breakdown Sprint 6–13 never built. Documented here rather than hidden, the same way ADR-055 documented "productivity"'s own necessary simplification.
- **CPI** = `EV / AC`, **SPI** = `EV / PV` — the standard formulas, computed only when both operands are available and the denominator is positive; otherwise `null`, never a fabricated value or a division error.

**Consequence:** A project with no schedule (`ProjectSchedule` never created) gets `planned_value_usd: null` and therefore `schedule_performance_index: null`, but `earned_value_usd`/`cost_performance_index` can still compute from contract value and completion percent alone — EVM degrades gracefully by field rather than becoming entirely unavailable for a project one input short. Because PV assumes linear cost accrual, SPI is a directional signal ("are we earning value faster or slower than a flat-rate schedule would predict"), not a precise cost-weighted schedule metric — this caveat belongs in the UI wherever SPI is shown, not only in this document. This is a single as-of-today snapshot, not a time series: no `daily_cost_trend`-style history of PV/EV/AC/CPI/SPI over time is computed or stored this sprint, since nothing in the roadmap's "cost prediction" wording asked for a historical EVM trend and a fifth chart series was judged out of scope without a concrete need for it.

---

## Known Bugs Found and Fixed — Pre-Sprint-15 (2026-09-16)

Found while investigating the real state of safety-incident data before scoping Sprint 15 (Autonomous Safety Compliance), applying the exact discipline Sprint 14 used for `financials`/`client_communication`: trace the actual JSON Schema file and the actual prompt text, don't assume either is complete just because a table exists for the data. Both bugs are pre-existing — present since whenever `extraction/prompts/builder.py`'s safety block was originally written — not introduced by any change in this session.

1. **`hazards_identified` crashed the entire daily log save whenever a real voice log mentioned a hazard.** The extraction prompt asked the LLM for `"hazards_identified": [<string>]` — a bare list of strings. `DailyLogRepository.create_from_extraction_result()` has always expected a list of objects (`item.get("hazard_type")`, `item.get("severity")`, etc. — the same code that correctly handles `delays`, `inspections`, and every other child-table array). Calling `.get()` on a plain Python `str` raises `AttributeError`, which is not caught anywhere in the persistence path — so a real transcript mentioning any hazard (a genuinely common thing for a foreman to mention) would fail to save **the entire log**, not just the hazard: workforce, materials, safety meeting data, everything in that `create_from_extraction_result()` call. **Confirmed live**: reproduced against the real Groq pipeline and the real database with a transcript describing a trip hazard near scaffolding — `AttributeError: 'str' object has no attribute 'get'`, log never persisted.
2. **`incidents` was extracted as a permanently-empty array, silently.** The prompt's `safety` block had `"incidents": []` — not a placeholder describing the object shape (compare `delays`, which correctly shows `{{"delay_type": ..., "hours_lost": ...}}`), but a literal empty array with no indication to the LLM that this field should ever contain anything. **Confirmed live**: a transcript explicitly describing a real injury (a carpenter slipping and twisting an ankle, first aid administered, reported to the site supervisor) produced `"incidents": []` from real Groq — the incident was mentioned clearly and in detail, and the model still returned nothing, because nothing in the prompt told it an incident object had a shape to fill in. This directly explains why Sprint 13's safety-incident analytics (`safety_incident_trend`/`safety_incident_breakdown`) showed empty results for the seeded project despite that project's real voice-log history plausibly containing safety-relevant content.
3. **Three safety-meeting fields were asked for under the wrong names, so they were silently dropped regardless of what the LLM returned.** The prompt asked for `safety_meeting_held`/`safety_meeting_topic`/`ppe_compliance_percent`; `DailyLogRepository.create_from_extraction_result()` has always read `safety_meeting_conducted`/`safety_meeting_topics`/`ppe_compliance_observed` (the real column names on `DailyLog`, matching `knowledge/construction_daily_log_schema.json` exactly) — a complete name mismatch, so even a "safety_meeting_held": true response from the LLM was discarded rather than persisted. `ppe_required_today` was defined in the schema and read by persistence but never asked for in the prompt at all.

**Fix:** `extraction/prompts/builder.py`'s `safety` block rewritten to match `knowledge/construction_daily_log_schema.json` exactly — real field names throughout, full object shapes (with every enum value) for `incidents` and `hazards_identified`, and `ppe_required_today` added. No changes needed to `database/repositories/daily_log.py` or any model — persistence was already correct; only the prompt had drifted. Verified live end-to-end with the identical transcript that previously crashed: now produces a correctly-typed `incidents` entry, a correctly-typed `hazards_identified` entry, correct safety-meeting fields, and persists cleanly with zero errors. Regression coverage: `tests/test_prompt_builder.py`'s `TestSafetySection` (field names and full object shapes present in the built prompt) and `tests/test_db_repositories.py`'s `TestSafetyIncidentAndHazardPersistence` (a dict-shaped hazard/incident persists correctly; a bare-string hazard — the old prompt's shape — still raises `AttributeError`, pinning that the fix belongs in the prompt, not in making the repository silently tolerant of malformed input).

A related, independently-discovered inaccuracy fixed in the same pass: `database/models/worker.py`'s class docstring claimed `worker_identifier` in `log_trades_on_site` "is linked to `Worker.id` via the repository layer when an exact name match is found" — no such code exists anywhere in the codebase (confirmed by a full-repo search). `WorkerRepository.find_by_name()`'s own docstring made an equally false claim about being "used by the repository layer to link voice-extracted `foreman_name` strings." Both docstrings corrected to state plainly that no such linking existed prior to Sprint 15's `worker_matching.py` (see ADR-061) — neither claim caused a functional bug (nothing depended on the false claims being true), but both were exactly the kind of confidently-wrong documentation this project has repeatedly found costs real investigation time when trusted at face value.

---

## ADR-061: OSHA Classification Is Human-Entered, Not LLM-Inferred; Worker Matching Is Exact-Name-Only (Sprint 15)

**Date:** Sprint 15, Deliverables 1–2
**Status:** Accepted

**Context:** `docs/NEXT_SPRINT.md` identified real gaps between what OSHA Form 300 legally requires (a case number, employee job title, a classification into death/days-away/job-transfer/other-recordable, an injury-type category, and day counts) and what `LogSafetyIncident` had before this sprint (a severity/category triage, not OSHA's required classification; `worker_involved` as free text with no link to a real `Worker` record). Two decisions had to be made explicitly rather than assumed: where the new classification fields' values come from, and how confidently a free-text name should be resolved to a real employee for a document with real legal weight.

**Decision — classification source:** `days_away_from_work_count`/`days_of_job_transfer_or_restriction_count` are voice-extracted (added to the extraction prompt) because a foreman can plausibly state them as an observed fact ("he'll be out about a week"). `osha_classification` (death/days-away/transfer/other) and `injury_illness_type` (injury/skin disorder/respiratory/poisoning/hearing loss/all other illness) are **not** extracted — they stay `NULL` until a human enters them, via a future review endpoint. A foreman narrating a voice log is not making a legal determination about OSHA recordability categories, and an LLM inferring one risks a confidently wrong classification on an official government compliance form — a materially different risk profile than Sprint 14's `financials` (a wrong dollar estimate is corrected by the next log; a wrong OSHA classification is a compliance document). `case_number` is likewise left `NULL` at write time — no per-calendar-year sequencing exists anywhere in this codebase to auto-assign one correctly, and inventing one now, before the PDF-generation deliverable defines how sequencing should actually work, would be guessing at a decision that deliverable owns.

**Decision — worker matching:** `LogSafetyIncident.worker_id` is populated by `app/services/worker_matching.py`'s `match_worker_by_name()`, **exact full-name match only** (case-insensitive), never `WorkerRepository.find_by_name()`'s substring search used directly. Two or more active workers sharing an exact name, or a name that only partially matches (a first name alone, a mis-transcribed partial name), both resolve to `needs_review`, not a best guess — `worker_match_status` (`matched | no_match | needs_review`) makes every outcome explicit rather than leaving `worker_id: null` to mean two different things. The reasoning mirrors the classification decision: a substring/fuzzy match is a reasonable UX for an admin picking from a dropdown, but wrong for a value written unattended onto a document establishing which employee was injured.

**Consequence:** A meaningful fraction of real incidents will have `worker_match_status: "needs_review"` or `"no_match"` rather than a populated `worker_id` — this is intentional, not a shortfall to fix by loosening the match criteria. Deliverable 3's PDF generation must treat an incident with no OSHA classification, no matched worker, or `needs_review` status as needing a human pass before it can appear on a generated OSHA 300 Log (excluded with a clear count, or included with explicit blank/TBD markers — that specific choice belongs to Deliverable 3, not this ADR). `match_worker_by_name()` is session-bound (unlike `schedule_service.py`/`cost_service.py`'s session-free pure-function modules) because it needs a live query against `Worker` records; `create_from_extraction_result()` fetches the owning project's `company_id` lazily, only when a log actually has at least one incident to match, so the overwhelmingly common no-incident case pays no extra query cost.

---

## ADR-062: OSHA 300 Log PDF Gets Its Own Table-Rendering Path; "Not Recordable" and "Not Yet Assessed" Are Different Exclusions (Sprint 15)

**Date:** Sprint 15, Deliverable 3
**Status:** Accepted

**Context:** `docs/NEXT_SPRINT.md` flagged, before implementation began, that `app/services/pdf_export.py`'s `render_markdown_pdf()` (Sprint 10) is deliberately scoped to the Markdown shape (`##` headers, `**bold**`, `- ` bullets) the 4 document-generation services produce, with no table-rendering path — while an OSHA Form 300 Log is fundamentally tabular. `reportlab` (already a dependency) has a real `Table`/`TableStyle` API, but using it meant writing a genuinely separate rendering path rather than extending the existing function. Separately, `classify_incident_readiness()`'s first implementation treated every incident with `osha_recordable != True` identically — but an incident explicitly marked `osha_recordable=False` (a safety officer already decided it doesn't belong on the log) and one with `osha_recordable=None` (never assessed at all) are not the same fact, and conflating them was caught only by a live end-to-end test against the real database.

**Decision:** `app/services/osha_log_export.py` is a new module with its own `SimpleDocTemplate`/`Table` construction, not an extension of `render_markdown_pdf()` — confirming the pre-implementation investigation was right. It reuses `pdf_export.py`'s `_sanitize_for_pdf_font()` directly (imported, not duplicated) for all table cell text and headings, since the same Unicode-punctuation-crashes-Helvetica failure mode applies identically to incident descriptions as to LLM-generated document prose. `classify_incident_readiness()` returns `(is_ready: bool, reason: Optional[str])` where `reason=None` specifically means "not applicable, no review needed" (an explicit `osha_recordable=False`) and a non-`None` reason means "a real candidate missing something" (`osha_recordable=None`, no classification, or an unresolved worker match) — `build_osha_300_log()` filters its "excluded, needs review" count on `reason is not None`, so an incident a safety officer already correctly excluded from OSHA reporting is never miscounted as still needing their attention.

**Consequence:** Two real bugs were found and fixed via live verification, not the unit test suite alone (both now regression-tested): (1) `SimpleDocTemplate(title=...)` used an unsanitized f-string containing a literal em-dash, which crashed every real request with a `'latin-1' codec` error the instant a real project name (the seeded sample project's own name contains one) or heading text needed non-ASCII punctuation — HTTP header/PDF-metadata encoding requirements are stricter than the PDF body text `_sanitize_for_pdf_font()` was already protecting; (2) the `Content-Disposition` filename built from `project.name` had the identical unsanitized-Unicode exposure, fixed with a proper ASCII-only slugify rather than a naive lowercase-and-replace-spaces. Both fixes generalize: any future PDF- or header-generating code in this codebase that interpolates real user/project data into a title, filename, or other latin-1-constrained field needs the same sanitization discipline, not just PDF body text.

---

## ADR-063: Safety "Proactive Warning" Is a Computed Read-Time Field; the OSHA Incidence Rate Has a Reliability Floor (Sprint 15)

**Date:** Sprint 15, Deliverable 4
**Status:** Accepted

**Context:** `docs/NEXT_SPRINT.md` resolved "proactive warning" the same way Sprint 14's Deliverable 2 resolved "budget variance alert" — this codebase has no scheduler (Celery Beat confirmed absent by the resume audit) and no notification infrastructure, so a "warning" can only mean a computed field surfaced on a read, not a pushed notification. Two further open questions the spec flagged: whether Sprint 13's existing `safety_incident_trend`/`safety_incident_breakdown` already covers "trend analysis" (yes — this deliverable adds only what's genuinely new: unresolved hazards and an incidence rate), and whether `LogTradeOnSite.hours_worked`'s aggregate is a trustworthy-enough denominator for OSHA's own incidence-rate formula without overstating precision.

**Decision:** `safety_proactive_warnings` on the analytics response carries three signals, all computed at read time in `app/services/safety_trend_service.py` and never persisted: unresolved hazards (from `LogHazard` where `corrective_action_completed=False`, sorted by severity then age — a critical hazard open 30 days outranks a low-severity one open 2), days since the most recent recorded incident (`None` distinct from `0`, so "no history" isn't confused with "incident-free today"), and an OSHA-standard incidence rate (`recordable_cases × 200,000 / hours_worked`, OSHA's own published constant). The hours-worked denominator sums `DailyLog.total_man_hours_worked` — the single foreman-reported total per log — rather than summing per-trade `LogTradeOnSite.hours_worked` rows independently, since that field is nullable per-row and summing it separately risks double-counting or omitting workers never tied to a specific trade. The incidence rate is withheld (returned as `None` with an explanatory `incidence_rate_unavailable_reason`) below a 1,000-hour floor — a deliberately conservative, project-chosen threshold (not an OSHA-defined minimum sample size), because extrapolating "cases per 100 workers per year" from a handful of logged hours produces a number that swings wildly on one more or fewer incident: technically correct arithmetic, practically misleading precision. Confirmed live against the real seeded project, which has only 54 total logged hours — the rate is correctly withheld with a clear reason rather than shown as a real but meaningless figure.

**Consequence:** Every real project will show `incidence_rate_unavailable_reason` rather than a number until it accumulates real logged hours — this is intentional, not a gap to fix by lowering the floor. `LogHazard` (identified-but-not-yet-incident hazards) was explicitly out of scope for Sprint 13's OSHA-compliance-adjacent safety analytics but is exactly the right fit here, matching `docs/NEXT_SPRINT.md`'s own framing: "an unresolved hazard is a legitimate thing to warn about, distinct from generating an official OSHA form for it" (ADR-062). If a future sprint wants a real scheduled digest or push notification built on these same signals, that requires actual notification infrastructure this codebase doesn't have — a separate, larger decision than this deliverable's scope.

---

## ADR-064: Extraction Translates to English Via a Prompt Rule — Whisper Stays in `task="transcribe"` Mode (Sprint 16)

**Date:** Sprint 16, Deliverable 1
**Status:** Accepted

**Context:** `docs/NEXT_SPRINT.md` identified faster-whisper as already multilingual and auto-detecting language correctly (confirmed: `SpeechTranscript.language_code` is real, populated data), but flagged the real open question as `task="transcribe"` (keeps text in the spoken language) vs. `task="translate"` (Whisper translates directly to English) vs. a third option — an English-output instruction added to the extraction prompt itself, translating during extraction rather than during transcription. The spec explicitly required live verification before trusting any strategy, since neither the extraction prompt nor the generation prompts had ever been exercised against non-English input.

**Decision:** Generated a real Spanish audio sample (`gTTS`, a foreman-style narration covering stage, workforce, weather, work completed, and a near-miss incident naming a worker) and ran it through the real pipeline twice. First, with today's defaults (`task="transcribe"`, no prompt change): Whisper correctly auto-detected `language="es"` and produced an accurate Spanish transcript; `ExtractionPipeline.extract()` on that transcript correctly identified `current_stage="framing"`, `total_workers_present=6`, `weather.morning_condition="sunny"`, and even correctly extracted the near-miss incident (`incident_type="near_miss"`, `worker_involved="Miguel"`) — but every free-text field (`task_description`, `location_on_site`, the incident `description`, `weather_notes`) was left in Spanish, verbatim from the transcript. Second, with a single rule added to `extraction/prompts/system_prompt.txt` ("The transcript may be in any language. Always write every text field... in English, regardless of the transcript's language — translate as you extract"): the identical Spanish transcript now produced fully English output across every field ("Installed second floor walls", "Carpenter Miguel slipped near the scaffold but was not injured"), with no other change to the pipeline.

This resolves the strategy question decisively: **keep `speech/utils/constants.py`'s `DEFAULT_TASK="transcribe"` unchanged** (the original-language transcript is preserved — real value for audit/compliance records, per the spec's own concern about `task="translate"` discarding it) **and add the English-output rule to the extraction system prompt** rather than switching Whisper's task mode. Groq's model is itself multilingual enough to translate accurately during structured extraction — a genuinely lower-cost fix than adding a second translation stage (post-extraction or post-transcription) would have been, and one that required changing a single sentence in one file to prove out.

**Consequence:** `SpeechTranscript.raw_text` continues to store the transcript in its original spoken language (already true today, unaffected by this change) — this is the record a compliance audit or a bilingual reviewer would want, and it is preserved rather than lost to an upstream translation step. `DailyLog`'s extracted fields, and everything generated from them (daily reports, customer updates, etc.), are in English regardless of the source language — no changes needed to any of the 4 generation prompts, since they already only ever see English-language extracted data by the time they run. This was proven with Spanish specifically; Portuguese/Mandarin/French are presumed to behave similarly given Groq's general multilingual capability, but per `docs/NEXT_SPRINT.md`'s own scope, verifying each individually is explicitly out of scope for this sprint unless Spanish verification had surfaced a language-specific problem (it did not).

---

## Known Bugs Found and Fixed — Sprint 11 (2026-09-15)

1. **`compute_variance()` and `propagate_delay_impact()` read a `.label` attribute that doesn't exist on `ScheduleTask`.** The `ScheduleTaskLike` structural type and the real `ScheduleTask` ORM model both name the field `stage_label`; an early draft of `app/services/schedule_service.py` used `.label` throughout (matching `TaskPlan`'s field name, a *different* dataclass in the same file that legitimately has `.label`). Every unit test passed, because `tests/test_critical_path.py`'s fixtures were hand-built with whatever attribute name the test itself declared — the mismatch only showed up against the real ORM model. Found immediately on the first live `POST /projects/{id}/schedule` call: a 500 with `AttributeError: 'ScheduleTask' object has no attribute 'label'`. **Fix:** renamed every `t.label`/`v.label` reference inside `compute_variance()`/`propagate_delay_impact()`'s call sites to `t.stage_label`, and corrected the `ScheduleTaskLike` documentation type to match. (`VarianceEntry.label` itself is unrelated and correctly named — it's a different, new object being constructed, not the field being read from `ScheduleTask`.)

2. **`ProjectSchedule.critical_path_total_days` undercounted by exactly the amount of inter-task lag on the critical path.** The first implementation set it to `sum(duration_days for critical-path tasks)` — but `knowledge/dependency_graph.json` has one real lag edge (foundation→framing, 7 days, concrete cure time) that adds to the project's total span without being any task's own duration. Live-computed: 101 days (naive sum) vs. 108 days (the CPM pass's own correct `planned_end_offset_days` for the last task) — a 7-day discrepancy that exactly matches the one lag edge in the graph, caught by comparing the two numbers rather than trusting either one at face value. **Fix:** `critical_path_total_days` (and `projected_completion_date`) now use `max(planned_end_offset_days across all tasks)` from the CPM pass's own output, which already accounts for lag, instead of re-deriving a total from durations alone. See ADR-049.

3. **The Deliverable 4 approval hook initially shared one transaction with the approval itself, so a schedule-update failure would have silently undone the approval too.** `get_db()`'s session only auto-commits once at the very end of a request and rolls back everything in the transaction on any exception (the same mechanism behind the Sprint 8 account-lockout bug, ADR/Known Bugs — Sprint 8). The best-effort schedule-progress update was written to run inside a `try/except` that called `session.rollback()` on failure — but since `repo.approve()`'s change hadn't been separately committed yet, that rollback would have discarded the approval the endpoint's response already promised had succeeded. Caught during implementation, before any live test exercised the failure path, by tracing exactly what `get_db()`'s commit/rollback boundary actually covers. **Fix:** the approval is now committed on its own, in its own transaction, immediately after `repo.approve()` and before the schedule-update attempt — which then runs fully isolated, with its own commit/rollback, unable to affect the already-committed approval regardless of what it does.

4. **A read-only schedule-response computation (delay-impact propagation) mutated real ORM-tracked rows in place.** `_to_schedule_response()`'s delay-impact section originally passed `tasks_sorted` — the same `ScheduleTask` objects the session is tracking — directly into a loop that wrote shifted dates onto `t.planned_end_date`, to fold multiple delays' effects together. Nothing in this endpoint is supposed to persist anything (delay impact is deliberately a read-time projection per ADR-048, recomputed fresh on every `GET`), so a stray `session.commit()` anywhere later in the same request (there wasn't one here, but the risk was structural) could have silently written speculative delay-adjusted dates into the real schedule. Caught during implementation, before this reached a live test, by reviewing what the mutation loop was actually operating on. **Fix:** the delay-impact folding loop now runs over small disposable plain-object copies (a local `_MutableTask` with just `stage_id`/`planned_end_date`), never touching the real `ScheduleTask` instances `tasks_sorted` holds.

---

## Known Bugs Found and Fixed — Sprint 10 (2026-08-19)

1. **`GET /daily-logs/{id}/outputs` accumulated duplicate documents on every regeneration.** `POST /daily-logs/{id}/generate` is explicitly designed to be re-runnable (its own router summary: "re-run the 4 AI documents for this log"), and `GenerationRepository.get_latest_for_log(log_id, service_type)` already existed for fetching one type's current version — but the list endpoint used `list_for_log()`, which returns every historical row unfiltered. Found via a real Playwright browser click on the Sprint 10 Documents panel, clicking "Regenerate" on a log that had been generated multiple times across this session's earlier verification runs: the UI showed 3 copies of every document instead of 4 total. Confirmed against the real database: 16 rows (4 generation runs × 4 types) for one log. Sprint 7's original endpoint had never been exercised by a real UI before this sprint — only spot-checked once via curl/Postman, which never triggers the duplicate-accumulation path. **Fix:** new `GenerationRepository.list_latest_for_log()` — a `ROW_NUMBER() OVER (PARTITION BY service_type ORDER BY created_at DESC)` window query, filtered to rank 1, portable across SQLite (tests) and PostgreSQL (no `DISTINCT ON`, which SQLite lacks). Verified live post-fix: the same log, still holding all 16 historical rows in the real database, correctly shows exactly 4 current documents.

2. **Real Groq-generated safety_talk PDFs rendered black-box glyphs (■) in place of common punctuation.** reportlab's default font (Helvetica, a PDF core font using WinAnsi/CP1252 encoding, ~256 glyphs) cannot render any character outside that set — not an error, a silent visual corruption. Synthetic test content (plain ASCII) never exercised this; a real LLM generation did, on the very first live download: `≈12 kg` (U+2248 approximately-equal) and every compound word the model wrote with a Unicode non-breaking hyphen (U+2011, e.g. "second‑floor", "cut‑resistant") rendered as ■. Ordinary em/en dashes (U+2013/U+2014) were unaffected — both are in WinAnsi already — which is why they didn't appear broken in the same document. **Fix:** `_sanitize_for_pdf_font()` in `app/services/pdf_export.py` — a `str.translate()` table mapping the specific Unicode punctuation LLM prose routinely produces (smart quotes, en/em dashes, non-breaking hyphen, approximately-equal, multiplication/division signs, degree sign, fraction glyphs) to ASCII equivalents, applied to every piece of text before it reaches reportlab's `Paragraph`, including the document title (which had bypassed the existing inline-markup sanitizer entirely — a second bug within the same fix). Chosen over bundling a full Unicode TTF font: proportionate to the actual failure mode (a short, known list of "smart" punctuation characters, not CJK or emoji) without adding a font-file dependency this project doesn't otherwise have. Verified live: the exact real-world document that produced ■ glyphs, re-downloaded after the fix, rendered every character correctly.

3. **The frontend offered Generate/Regenerate, Mark-as-sent, and voice recording to every role, including ones the backend would 403.** Only Approve/Reject (`LogReviewPage.tsx`'s `REVIEWER_ROLES`, added in the original Sprint 9 build) were ever role-gated in the UI. `DocumentsPanel`'s Generate and Mark-as-sent buttons, and the `/record` nav item + page, showed unconditionally for every authenticated role — a `client` or `safety_officer` user (neither holds `Permission.DAILY_LOG_GENERATE`, `DAILY_LOG_SEND_OUTPUT`, or `AUDIO_UPLOAD`) would see fully clickable buttons that always fail with a 403 on click. Found while doing Sprint 10 Deliverable 7's own explicit task — verifying the client role's experience — by creating a real `client`-role user and logging in as them in a real browser, not by reading the code. **Fix:** `frontend/src/auth/roles.ts` — four named role sets mirroring the relevant slice of `app/core/permissions.py`'s `ROLE_PERMISSIONS`, applied to `DocumentsPanel`'s two buttons, `AppLayout`'s Record nav link, and `RecordPage` itself (a second guard for direct URL navigation, since hiding the nav link alone doesn't block that). Not a new authorization system — the backend's `require_permission()` remains the real boundary regardless of what the frontend shows; this closes the UX gap of offering an action that was always going to fail. Verified live: the same real client-role user, logged in, sees the full log and all 4 documents (read access, correctly still granted) but no Approve/Reject/Generate/Mark-as-sent buttons and no Record nav link; a direct visit to `/record` shows a permission message instead of the recorder.

---

## Known Bugs Found and Fixed — Sprint 9 (2026-08-19)

1. **`app/main.py` never called `logging.basicConfig()`.** Every `logger.info()` call across the whole `app/` package — not just Sprint 9's own, e.g. Sprint 7's "Queued pipeline for audio_file_id=..." and Sprint 8's "auth.forgot_password: reset token issued..." — was silently dropped under `uvicorn app.main:app`, since Python's root logger defaults to `WARNING` and nothing had ever lowered it. Found while verifying `DevConsoleEmailSender` live: the log line it exists to produce never appeared. **Fix:** added `logging.basicConfig(level=logging.INFO, ...)` to `app/main.py`. Predates Sprint 9; `celery -A celery_app worker` was unaffected (Celery's own CLI configures logging independently via `--loglevel`).

2. **`get_rate_limiter()`'s new `Settings` parameter was nearly shipped as a plain `settings=None` default.** Caught during implementation, before merge: an untyped, non-`Depends` parameter on a function used as `Depends(get_rate_limiter)` is not injected by FastAPI at all — it would have been silently (mis)treated as an unbound query parameter, meaning `settings` would stay `None` on every real request and the whole `RedisRateLimiter` migration would have quietly reverted to never actually running in production, while every test that constructs `Settings` directly (bypassing the dependency-injection path) kept passing. **Fix:** `settings: Settings = Depends(get_app_settings)` — the same pattern `app/services/email_sender.py`'s `get_email_sender()` already established for exactly this reason.

---

## Known Bugs Found and Fixed — Sprint 8

Two structurally identical bugs were found during Subsystem 5 and Subsystem 6 testing, both caused by the same root mechanism: the request-scoped database session (`database/session.py:get_session()`, mirrored in `tests/conftest_api.py`) rolls back on **any** exception — including an intentionally-raised `HTTPException` the route itself is about to return as a normal 401/403/423/429 response.

1. **Subsystem 5 — Account lockout never actually persisted.** `AuthService._record_failed_login()` incremented `User.failed_login_attempts` and flushed it, then the caller (`login()`) raised `HTTPException(401)` for the wrong password. The session's rollback-on-exception discarded the increment on every single failed attempt, making the 5-attempt lockout threshold permanently unreachable in both tests and production. **Fix:** `_record_failed_login()` now calls `self._session.commit()` itself, in a small sub-transaction scoped to just that state change, before returning to the caller that raises.

2. **Subsystem 6 — Several audit events (`security.unauthorized_access`, `security.forbidden_access`, rate-limit and lockout events) were silently discarded.** Same root cause: `safe_log_event()` flushed but did not commit, and the events in question are logged immediately before the caller raises the corresponding `HTTPException`. **Fix:** `safe_log_event()` now commits immediately after a successful write (see ADR-040), so the audit row survives regardless of what the caller does next.

Both were caught by dedicated tests asserting the persisted database state (not just the HTTP response code), not by manual inspection — reinforcing that HTTP-response-only test assertions can pass while the underlying state change silently fails.

A third, unrelated bug was found and fixed during Subsystem 4 (User Management): `UserRead`'s Pydantic schema declared `id`/`company_id` as `str` instead of `UUID`, causing every user create/read response to fail model validation and surface as a misleading `409` (the `ValueError → 409` global exception mapping intercepted the Pydantic `ValidationError`). Fixed by correcting the field types to `UUID` (matching every other `*Read` schema in the codebase, e.g. `app/schemas/daily_log.py`).

---

## Known Bugs Found and Fixed — Post-Resume-Audit Cleanup (2026-09-15)

Two real, pre-existing correctness bugs `docs/RESUME_AUDIT_2026-09-15.md` flagged as P1 backlog items, fixed and verified live in the same session as Sprint 11.

1. **`POST /daily-logs/{id}/generate` silently dropped 7 of the 14 data categories a daily log actually holds when regenerating documents.** The reconstruction of the extraction-shaped dict (from the persisted `DailyLog` row and its children) only included `weather`, total worker count, `work_completed`, `materials_used`, `safety_notes`, `tomorrow_plan`, and `client_communication` — `delays`, `equipment`, `hazards`, `work_in_progress`, `materials_delivered`, `materials_required`, and `trades_on_site` were never read at all. A log recording a two-hour weather delay, when regenerated, produced a daily report with no "Delays and Issues" section whatsoever — the same content, same prompts, same model, but silently thinner than what `run_pipeline()` (the original, non-regenerated path) would have produced from the identical log, because that function passes the *full* extraction output while this endpoint only ever rebuilt a partial one. **Fix:** `app/api/v1/daily_logs.py`'s `_rebuild_extracted_log()` now mirrors every field `DailyLogRepository.create_from_extraction_result()` (the write-path inverse) reads, across all 11 child tables. Verified live: regenerating a real log with a recorded weather delay and required-materials entries now correctly includes both in the output — confirmed by reading the actual generated Markdown, not just checking the endpoint returned 200. Regression coverage: `tests/test_api_daily_logs.py`'s `TestGenerateRebuildsFullExtractedLog`, which asserts on the exact `log_dict` passed to `AIServiceManager.generate_all()`.

2. **`processing_status = "complete"` did not distinguish a fully successful pipeline run from one where generation failed entirely or partially.** `run_pipeline()`'s generation stage either raised (caught, logged, but the audio file was still marked `complete` with no indication anything went wrong) or returned outputs where some/all had empty `content` (silently skipped by the `if output and output.content` guard, again with no record). A caller polling `GET /audio/{id}/status` saw an identical response — `processing_status: "complete"`, no error — whether all 4 documents were generated or zero were. **Fix:** `_mark_complete()` now accepts an optional `generation_warning`, set when generation raised or when fewer than 4 outputs were actually saved (with an exact count in the message). Written to the (previously-unused-by-this-endpoint) `validation_warnings` column, newly exposed through `AudioStatusResponseData.validation_warnings`/`warning_message` and rendered on `RecordPage.tsx` as a distinct amber warning banner — separate from the red error banner, which stays reserved for a genuine `failed` status. Regression coverage: `tests/test_pipeline_service.py`'s `TestGenerationFailureIsNotSilentSuccess` (3 tests: exception path, zero-documents path, and a control asserting the happy path sets no warning) plus 2 new frontend tests in `RecordPage.test.tsx`.

A related cosmetic bug, `RecordPage.tsx`'s failed-upload banner showing the same error text twice (once as `error_message`, once again as the sole item in a `validation_errors` bullet list — `error_message` is already that list `"; "`-joined by the backend), was fixed in the same pass: the bullet list now renders only when there are 2+ distinct errors, and the single-line message otherwise.

Also closed in this pass (not bugs, but drift the resume audit flagged): `database/base.py` gained a `JSONType` variant (`JSON` on SQLite, `JSONB` on PostgreSQL) resolving 22 columns' worth of permanent `alembic check` drift that existed because every model declared plain `JSON` while migration `001` had always created the columns as `JSONB` — the live database was correct, the models understated it. Two further, narrower drift items fixed alongside it: `DailyLog.reviewed_at` now explicitly declares `DateTime(timezone=True)` (previously inferred a naive type against a `TIMESTAMPTZ` column), and `Worker.user_id` no longer declares a `ForeignKey` the database was never given (ADR-026's Company↔User circular-dependency avoidance applies here too — the model just hadn't said so). The remaining ~82 `alembic check` entries are `server_default` values declared in migrations but not mirrored as `server_default=` in the models (the models use Python-side `default=` instead, which produces the identical column value) — confirmed benign by comparing live column defaults against expected values; left as-is rather than touching 82 columns across frozen Sprint 1–10 models for a cosmetic-only gain.

---

## Pending Decisions (Future Sprints)

| Decision | Context | Sprint | Status |
|----------|---------|--------|--------|
| Redis vs in-memory caching | For caching LLM inference results (Groq or future local) | Sprint 10+ | Open |
| Redis-backed RateLimiter | Migrate `MemoryRateLimiter` to `RedisRateLimiter` per ADR-041's documented migration path | Sprint 9 | **Resolved — see ADR-044**, delivered in Sprint 9 |
| Celery vs FastAPI Background Tasks | For async audio processing | Sprint 7 | **Resolved — BackgroundTasks for Sprint 7; migrated to Celery + Redis in Sprint 9, see ADR-043** |
| `GET /projects` list endpoint | Project CRUD, deferred since Sprint 7 | Sprint 10+ | **Resolved — delivered in Sprint 10, Deliverable 1.** Dashboard now uses a real project picker instead of a manually-entered id. |
| asyncpg vs psycopg3 | For async PostgreSQL in FastAPI | Sprint 7 | **Resolved — asyncpg (see ADR-031); repository layer itself stays sync** |
| Row-level security | PostgreSQL RLS for multi-tenancy enforcement | Sprint 8 | **Resolved — application-layer `TenantScopedRepository` (ADR-037) chosen over PostgreSQL RLS; RLS remains open as a future defense-in-depth layer, not required given the ORM-mediated access pattern** |
| Alembic auto-generate vs hand-write migrations | Database migration strategy | Sprint 6 | Resolved (Sprint 6) |
| Docker multi-stage build | Optimize image size | Sprint 10+ | Open |
| JWT vs Session tokens | Authentication strategy | Sprint 7 | **Resolved — JWT access tokens (HS256) + opaque server-backed refresh tokens (ADR-035), see `app/core/security.py`.** |
| FAISS vs ChromaDB vs Weaviate | Vector store for RAG | Future | Open |
| Persist observability events | Write GenerationMetrics to DB / emit to queue | Sprint 9+ | Open |
| Email provider for password reset | Sprint 8 built the token lifecycle only (dev-mode raw-token response); real delivery is unimplemented | Sprint 9+ | **Resolved — see ADR-045.** `EmailSender` Protocol with `DevConsoleEmailSender`/`SMTPEmailSender`, delivered in Sprint 9. |
