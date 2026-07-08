# CHANGELOG

All notable changes to Construction Site AI are documented here.
Format: `[Sprint X] Date — Description`

---

## [Sprint 5.1] 2026-07-08 — Hardening & Optimization Pass

### Added

#### Prompt Cache Improvements
- `generation/prompts/loader.py` — `PromptLoader` now tracks `_mtime: dict[str, float]`; every `.load()` call compares the current `os.path.getmtime()` against the stored mtime and automatically evicts and reloads changed files. Prompt engineers can edit `.md` files with no process restart required.

#### Prompt Registry
- `generation/prompts/registry.py` — New `PromptRegistry` + `PromptRegistration`; `DEFAULT_PROMPT_REGISTRY` pre-registers all 4 built-in prompts with name, description, `expected_output`, service class name, and required variables. `validate()` detects unknown prompt names early.

#### Service Registry
- `generation/services/registry.py` — New `ServiceRegistry` + `ServiceRegistration`; `DEFAULT_SERVICE_REGISTRY` pre-registers all 4 built-in services. `create_all()` instantiates services with shared dependencies. Adding a new service = create class + call `register()`. Zero `AIServiceManager` changes.
- `generation/manager.py` — `AIServiceManager.__init__()` refactored to call `registry.create_all()`. New `service_registry=` parameter for partial-registry DI in tests.

#### Generation ID
- `generation/models/outputs.py` — `ServiceMetadata` gains `generation_id: str` (UUID4, auto-assigned). Correlation key linking logger lines, events, and results. Fully backward-compatible — existing tests unaffected.

#### Observability Layer
- `generation/observability/__init__.py` — Public API: `METRICS`, `GenerationMetrics`, `Timer`
- `generation/observability/events.py` — 9 typed frozen event dataclasses: `GenerationStartedEvent`, `GenerationCompletedEvent`, `GenerationFailedEvent`, `RetryStartedEvent`, `RetryCompletedEvent`, `ValidationFailedEvent`, `PromptCacheHitEvent`, `PromptCacheMissEvent`
- `generation/observability/timers.py` — `Timer` context manager (`time.monotonic()`; `elapsed`, `is_running`, explicit `start()`/`stop()`, `__enter__`/`__exit__`)
- `generation/observability/metrics.py` — `GenerationMetrics` in-memory accumulator; per-service buckets; `summary()` returns totals, cache stats, per-service stats; `METRICS` global singleton; `reset()` for test isolation

#### Tests (109 new tests — 595 total, 1 skipped)
- `tests/test_prompt_cache.py` — 12 tests: mtime tracking, automatic reload, clear_cache, multi-prompt independence, real prompt files
- `tests/test_prompt_registry.py` — 23 tests: register/get/validate/list_names, error cases, DEFAULT_PROMPT_REGISTRY built-in entries
- `tests/test_service_registry.py` — 24 tests: register/get/create_all, error cases, DEFAULT_SERVICE_REGISTRY, AIServiceManager DI
- `tests/test_observability.py` — 48 tests: Timer API, all 9 event types, GenerationMetrics counters/aggregates/reset, METRICS global
- `tests/test_generation_models.py` — 5 new tests for `generation_id` (UUID4, uniqueness, explicit override, serialization)

### Changed

#### Performance & Architecture
- `generation/services/base_service.py` — Removed instance-level `self._loaded_prompt` cache; `generate()` now always calls `self._prompt_loader.load(prompt_name)`. PromptLoader is the single cache. Enables mtime invalidation end-to-end. Adds observability events (`GenerationStarted`, `GenerationCompleted`, `GenerationFailed`, `RetryStarted`, `ValidationFailed`).
- `tests/test_generation_services.py` — `TestPromptCaching` updated: `test_prompt_loaded_only_once_across_multiple_generate_calls` renamed to `test_prompt_loader_called_on_every_generate` with corrected `call_count == 3` assertion. New `test_prompt_loader_cache_serves_repeated_loads` verifies PromptLoader caching.

### Architecture Decisions (ADR-021 through ADR-025)
- ADR-021: Mtime-aware prompt cache invalidation (PromptLoader + removal of BaseAIService dual-cache)
- ADR-022: PromptRegistry for domain-level prompt discovery and validation
- ADR-023: ServiceRegistry for open/closed service registration
- ADR-024: `generation_id` UUID4 correlation key in ServiceMetadata
- ADR-025: Lightweight in-process observability layer (no Prometheus, no cloud)

---

## [Sprint 5.0] 2026-07-08 — AI Generation Service Layer

### Added

#### generation/ Package
- `generation/__init__.py` — Public API (AIServiceManager + all output types)
- `generation/config.py` — `GenerationConfig` + `GenerationGroqConfig`; mirrors `ExtractionConfig` structure for `EngineFactory` duck-typing compatibility
- `generation/manager.py` — `AIServiceManager`: single orchestration point; receives `ConstructionDailyLog` dict, routes to all 4 services, returns `GenerationResult`
- `generation/models/outputs.py` — Pydantic v2 output models: `ServiceType` (enum), `ServiceMetadata`, `ServiceOutput`, `DailyReport`, `CustomerUpdate`, `ToolboxTalk`, `MaterialReminder`, `GenerationResult`
- `generation/prompts/loader.py` — `PromptLoader`: loads versioned `.md` prompts with YAML-like frontmatter; per-instance caching; zero external dependencies
- `generation/prompts/daily_report.md` — v1.0.0 formal contractor daily report prompt
- `generation/prompts/customer_update.md` — v1.0.0 client-facing email prompt
- `generation/prompts/safety_talk.md` — v1.0.0 OSHA-referenced safety toolbox talk prompt
- `generation/prompts/material_reminder.md` — v1.0.0 procurement reminder prompt
- `generation/services/base_service.py` — `BaseAIService` abstract class (Template Method pattern): load prompt → build user message → call LLM with retry → validate → return typed output
- `generation/services/daily_report.py` — `DailyReportService`
- `generation/services/customer_update.py` — `CustomerUpdateService`
- `generation/services/safety_talk.py` — `SafetyTalkService`
- `generation/services/material_reminder.py` — `MaterialReminderService`
- `generation/validators/content_validator.py` — `ContentValidator`: 6 AI output quality checks (empty, min/max length, required phrases, placeholder detection, duplicate sentences, markdown structure)

#### CLI
- `report.py` — Sprint 5 CLI entry point: accepts `ExtractionResult` JSON or raw `ConstructionDailyLog`; flags: `--service`, `--output`, `--stdin`, `--check`, `--provider`

#### Tests (164 new tests — all pass without GROQ_API_KEY)
- `tests/test_generation_models.py` — 27 tests for all Pydantic output models
- `tests/test_generation_config.py` — 14 tests for config defaults, env overrides, duck-typing compatibility
- `tests/test_generation_prompts.py` — 22 tests for prompt loading, frontmatter parsing, caching
- `tests/test_content_validator.py` — 23 tests for all 6 content validation checks
- `tests/test_generation_services.py` — 25 tests for all 4 services, retry logic, prompt caching
- `tests/test_generation_manager.py` — 19 tests for orchestration, DI, serialization

#### Documentation
- `docs/AI_SERVICES.md` — Complete Sprint 5 framework reference (architecture, models, config, usage examples, prompt format, validation, extensibility guide, ADR summary, test coverage table)

#### Infrastructure
- `data/generated/.gitkeep` — Output directory for runtime-generated files (git-ignored)
- `pydantic==2.13.4` added to `requirements-dev.txt`
- `GENERATION_*` env vars added to `.env.example`
- `data/generated/*` added to `.gitignore` (with `.gitkeep` exception)

### Changed
- `docs/ROADMAP.md` — Sprint 5 marked complete with full deliverable list
- `docs/HANDOVER.md` — Updated to Sprint 5 complete state
- `docs/NEXT_SPRINT.md` — Updated to Sprint 6 spec
- `docs/PROJECT_STATE.md` — Updated sprint status and repo structure

### Architecture Decisions (ADR-017 through ADR-020)
- ADR-017: Prompts as versioned `.md` files (product artifacts, not code)
- ADR-018: Pydantic for generation output models (Sprint 7 FastAPI readiness)
- ADR-019: One shared engine, system instructions embedded in user message (Sprint 4 FROZEN interface respected)
- ADR-020: Prompts in `generation/prompts/` not `app/prompts/` (`app/` is Sprint 7's directory)

---

## [Sprint 1.1] 2026-06-30 — Sprint 1 Freeze & Knowledge Base Extension

### Added
- `knowledge/construction_rules.json` — 38 machine-readable construction rules (sequential, parallel, material consistency, worker consistency, safety constraints, weather constraints, quantity sanity)
- `knowledge/dependency_graph.json` — Complete DAG of residential construction workflow with 23 nodes, 33 edges, critical path, parallel groups, and topological sort
- `knowledge/validation_rules.json` — 35 machine-readable validation rules with conditions, severities, error messages, and suggested fixes (consumed by Sprint 2 generators and Sprint 4 AI validator)
- `knowledge/construction_ontology.json` — Complete entity-relationship ontology covering trades, materials, equipment, hazards, PPE, worker roles, inspection types, delay types, and weather conditions with 40+ relationships. Designed for future RAG/FAISS integration
- `docs/CHANGELOG.md` — This file (project change history)
- `docs/DECISIONS.md` — Architecture decision record
- `docs/PROJECT_STATE.md` — Official project state (moved from root to docs/)
- `docs/NEXT_SPRINT.md` — Sprint 2 preparation document
- `docs/ROADMAP.md` — Full product roadmap
- `docs/HANDOVER.md` — Complete handover document for new sessions

### Fixed (Sprint 1 Gaps Identified)
- Gap: `construction_stages.json` covered only 11 stages but `current_stage` schema enum had 22 values. The ontology and dependency graph now cover all 22 stages.
- Gap: Sequencing rules were embedded inside `construction_stages.json` as a sub-object. Extracted to dedicated `construction_rules.json`.
- Gap: No machine-readable validation for dataset generators. Resolved with `validation_rules.json`.
- Gap: No entity-relationship model for future AI/RAG use. Resolved with `construction_ontology.json`.

---

## [Sprint 1.0] 2026-06-30 — Sprint 1 Initial Delivery

### Added
- `knowledge/construction_stages.json` — Knowledge base for all 11 residential construction stages with workers, materials, tools, delays, safety hazards, and daily report fields
- `knowledge/construction_daily_log_schema.json` — Master ConstructionDailyLog JSON Schema v1.0.0 with 12 sections, 80+ fields, UUID keys, explicit null typing, enum validation, and complete example
- `docs/sprint_1/CONSTRUCTION_RESEARCH.md` — Human-readable domain research on all 11 stages
- `docs/sprint_1/SCHEMA_DESIGN.md` — Architecture decisions explaining schema design choices
- `README.md` — Project overview with tech stack and sprint progress
- `.gitignore` — Python, Node, Docker, and AI model ignore rules
- `.env.example` — Complete environment variable template for all future modules
- `PROJECT_STATE.md` (root) — Sprint 1 state document (frozen as Sprint 1 artifact)

---

## [Sprint 2.0] 2026-06-30 — Synthetic Construction Data Generation Framework

### Added

#### Framework Infrastructure
- `dataset_generation_framework/` — Production-grade, reusable data generation framework
- `dataset_generation_framework/config.py` — Single source of truth for all generation parameters. Change 5 size constants to scale from 5,000 to 500,000+ records.
- `dataset_generation_framework/core/knowledge_loader.py` — Singleton KnowledgeBase with O(1) lookup indexes for all 6 Sprint 1 knowledge files
- `dataset_generation_framework/core/stage_machine.py` — DAG-based construction project state machine (ProjectState + StageMachine). Enforces topological stage ordering from `dependency_graph.json`
- `dataset_generation_framework/core/rule_engine.py` — Query interface for `construction_rules.json`. Answers questions like "Can roofing and HVAC run in parallel?" and "What materials are expected for framing?"
- `dataset_generation_framework/validation/pipeline.py` — 4-phase ValidationPipeline (blocking → errors → warnings → info). Fail-fast on Phase 1.
- `dataset_generation_framework/generators/base_generator.py` — Abstract `BaseGenerator` with streaming yield, seeded RNG, and `GeneratorStats` tracking
- `dataset_generation_framework/exporters/jsonl_exporter.py` — Batched JSONL file writer with context manager API
- `dataset_generation_framework/exporters/csv_exporter.py` — Batched CSV writer with auto-inferred headers, None→"", list→";" conversion
- `dataset_generation_framework/statistics/report_generator.py` — Post-generation statistical analysis and summary report

#### Dataset Generators
- `dataset_generation_framework/generators/daily_log_generator.py` — Simulates complete construction projects day-by-day to produce `ConstructionDailyLog` records. Uses StageMachine + RuleEngine to guarantee sequencing correctness.
- `dataset_generation_framework/generators/schedule_generator.py` — Generates project schedules with planned vs. actual dates and delay breakdown
- `dataset_generation_framework/generators/safety_talk_generator.py` — Generates safety toolbox talk records from OSHA knowledge and ontology hazards
- `dataset_generation_framework/generators/material_generator.py` — Generates construction material catalog entries from ontology
- `dataset_generation_framework/generators/customer_update_generator.py` — Generates (raw foreman notes, customer email) training pairs

#### Entry Point
- `generate.py` — CLI entry point: `python generate.py`, `python generate.py --dataset daily_logs --count 5000 --seed 42`

#### Tests
- `tests/test_knowledge_loader.py` — Unit tests for KnowledgeBase singleton, all API domains
- `tests/test_stage_machine.py` — Unit tests for StageMachine, ProjectState, can_start(), advance_day()
- `tests/test_validation_pipeline.py` — Unit tests for ValidationResult, 4-phase pipeline, all rule types
- `tests/test_generators.py` — Unit tests for all 5 generators (count, keys, range validation, reproducibility)
- `tests/test_integration.py` — End-to-end pipeline tests (generator → exporter → file → read-back validation)

#### Dataset Infrastructure
- `datasets/raw/`, `datasets/generated/`, `datasets/validated/`, `datasets/exports/` — Dataset directory structure
- `datasets/README.md` — Dataset documentation: format, schema, purpose, generation commands
- `requirements-dev.txt` — Python development dependencies (jsonschema, faker, pytest, pytest-cov, tqdm)

### Architecture Decisions (Sprint 2)
- ADR-009: Production framework architecture over one-off scripts (see DECISIONS.md)
- ADR-010: Project simulation over random record generation (see DECISIONS.md)
- ADR-011: Streaming generators — same peak memory at 500k as at 5k (see DECISIONS.md)

---

## [Sprint 3.0] 2026-07-01 — Speech Processing Framework

### Added

#### Framework Infrastructure
- `speech/` — Standalone, engine-agnostic Speech Processing Framework. Zero imports from `dataset_generation_framework/` or `knowledge/`. Public API: `SpeechProcessingPipeline.process(audio_path) -> SpeechProcessingResult`
- `speech/config.py` — `SpeechProcessingConfig` with nested `AudioValidationConfig`, `WhisperConfig`, `PreprocessingConfig`, `PostprocessingConfig`. `from_env()` reads `SPEECH_WHISPER_MODEL_SIZE`, `SPEECH_WHISPER_DEVICE`, `SPEECH_WHISPER_COMPUTE_TYPE`, `SPEECH_WHISPER_LANGUAGE`, `SPEECH_MAX_FILE_SIZE_MB`, `SPEECH_MAX_DURATION_SECONDS`, `SPEECH_ENABLE_NOISE_REDUCTION`, `SPEECH_MODELS_DIR`
- `speech/utils/constants.py` — Framework-wide constants (supported formats, size/duration limits, filler words, construction term corrections)
- `speech/utils/retry.py` — Exponential backoff `@retry` decorator for transient STT failures
- `speech/pipeline.py` — `SpeechProcessingPipeline`, the main orchestrator: validation → preprocessing → STT → postprocessing → result. Supports single-file `process()` and `process_batch()`. Same API from 1 recording to 100,000+

#### Data Models
- `speech/models/transcript.py` — `WordTimestamp`, `TranscriptSegment`, `Transcript` dataclasses. The permanent, engine-neutral contract between any STT engine and the rest of the framework
- `speech/models/metadata.py` — `AudioFileInfo`, `ProcessingStats`, `SpeechProcessingMetadata` — full audit trail for every pipeline run
- `speech/models/processing_result.py` — `AudioValidationResult`, `SpeechProcessingResult`. Structured object returned by every `process()` call, never plain text. `to_dict()`/`to_json()` for lossless serialization

#### Audio Loading & Validation
- `speech/loaders/format_detector.py` — Format detection via extension + magic-byte fallback, independent of file extension correctness
- `speech/loaders/audio_loader.py` — Audio metadata extraction via soundfile (WAV/FLAC/OGG) with librosa fallback (MP3/M4A). Graceful degradation to `is_readable=False` if neither package is installed
- `speech/validators/audio_validator.py` — 8 blocking pre-transcription checks (existence, size, format, readability, duration, sample rate, channels) + 3 non-blocking warnings, run before any transcription attempt

#### Preprocessing
- `speech/preprocessors/audio_normalizer.py` — Peak normalization to -3 dBFS; no-op fallback if numpy/soundfile unavailable
- `speech/preprocessors/noise_reducer.py` — Optional `noisereduce`-based noise reduction; disabled by default, no-op pass-through if package missing
- `speech/preprocessors/chunker.py` — `AudioChunker` reports expected chunk boundaries for long recordings (Whisper handles actual chunking internally)

#### STT Engine
- `speech/whisper/engine.py` — `BaseSTTEngine` abstract interface + `FasterWhisperEngine` implementation. `faster_whisper` is imported in this file only — nowhere else in the codebase. Lazy model loading (model loads on first `transcribe()` call, not at construction). Wrapped in `@retry` for transient load failures

#### Postprocessing
- `speech/postprocessors/construction_normalizer.py` — Pattern-based construction terminology correction (`re bar` → `rebar`, `h v a c` → `HVAC`, `p v c` → `PVC`, etc.). Pure text correction, zero domain knowledge
- `speech/postprocessors/transcript_cleaner.py` — `TranscriptCleaner` drops Whisper hallucination artifacts (`[INAUDIBLE]`, `[Music]`, YouTube-style artifacts), strips filler words, applies construction normalization. Returns new `Transcript`, never mutates input

#### Metadata & Export
- `speech/metadata/extractor.py` — `MetadataExtractor` builds `SpeechProcessingMetadata` at pipeline start, finalizes processing stats after transcription completes
- `speech/exporters/base_exporter.py` — `BaseExporter` abstract interface for result exporters
- `speech/exporters/json_exporter.py` — `JSONExporter` (full structured JSON) and `JSONLExporter` (append-mode, one line per result, for batch runs)
- `speech/exporters/text_exporter.py` — `TextExporter` (plain transcript text) and `VerboseTextExporter` (timestamps + confidence + metadata header)

#### CLI
- `transcribe.py` — CLI entry point. Single file, `--batch DIR` mode, `--dry-run` validation-only mode, `--format json|jsonl|text|verbose-text`, `--model`/`--device`/`--compute-type` overrides

#### Tests
- `tests/conftest.py` — Synthetic WAV generation (sine tones via numpy+soundfile, stdlib `wave` fallback), shared fixtures for valid/short/long/stereo/empty/fake audio
- `tests/test_speech_models.py` — Data model construction, serialization round-trips
- `tests/test_speech_config.py` — Default config, constructor overrides, `from_env()` env-var reading
- `tests/test_speech_validator.py` — All 8 blocking checks + 3 warnings, boundary cases
- `tests/test_transcript_cleaner.py` — Filler removal, hallucination dropping, construction-term normalization
- `tests/test_audio_pipeline.py` — Full pipeline integration via injected `MockSTTEngine` (no GPU, no model download, no network); real-engine tests gated `@pytest.mark.skipif(not HAS_FASTER_WHISPER, ...)`

#### Sample Data
- `scripts/create_sample_audio.py` — Generates 10 synthetic sine-tone WAV files covering validator boundary conditions (short/long duration, stereo, low/high sample rate, chunk boundaries)
- `data/sample_audio/` — 10 synthetic WAV files + ground-truth placeholder `.txt` files + `README.md` explaining synthetic vs real audio and how to add real recordings for WER testing
- `data/transcripts/raw/`, `data/transcripts/cleaned/` — Output directories for CLI transcription runs (gitkept, generated content gitignored)

#### Documentation
- `docs/AI_PIPELINE.md` — Full application AI pipeline reference: speech → extraction → validation → persistence → delivery, what exists vs. what's planned
- `docs/SPEECH_PIPELINE.md` — Speech Processing Framework reference: architecture, pipeline stages, public API, configuration, CLI, testing

#### Dependencies
- `requirements-dev.txt` — Added `numpy`, `soundfile`, `faster-whisper`, `librosa`, `noisereduce`, `jiwer`. All free, open source, no paid APIs

### Fixed
- `speech/pipeline.py` passed `chunk_overlap_seconds=` to `AudioChunker.__init__()`, which expects `overlap_seconds=`. Fixed during Sprint 3 test verification.

### Architecture Decisions (Sprint 3)
- ADR-012: Engine-agnostic speech framework via `BaseSTTEngine` abstraction (see DECISIONS.md)
- ADR-013: Lazy model loading for STT engines (see DECISIONS.md)
- ADR-014: `SpeechProcessingResult` as a structured object, never plain text (see DECISIONS.md)

---

## [Sprint 4.0] 2026-07-04 — AI Information Extraction Framework

### Added

#### Framework Infrastructure
- `extraction/` — Standalone, engine-agnostic AI Extraction Framework. Zero imports from `speech/`, `dataset_generation_framework/`, or `knowledge/` except via well-defined interfaces. Public API: `ExtractionPipeline.extract(transcript_text) -> ExtractionResult`
- `extraction/config.py` — `ExtractionConfig` with nested `OllamaConfig`. `from_env()` reads `EXTRACTION_OLLAMA_MODEL`, `EXTRACTION_OLLAMA_HOST`, `EXTRACTION_OLLAMA_TEMPERATURE`, `EXTRACTION_OLLAMA_TIMEOUT`, `EXTRACTION_MAX_RETRIES`, `EXTRACTION_KNOWLEDGE_DIR`
- `extraction/pipeline.py` — `ExtractionPipeline` orchestrator: build prompt → call engine → parse JSON → validate → return `ExtractionResult`. Supports `extract(text)` and `extract_from_speech_result(SpeechProcessingResult)`. Retry with exponential backoff for LLM call failures.

#### Data Models
- `extraction/models/extraction_result.py` — `ExtractionResult` and `ExtractionMetadata` dataclasses. Structured result for every extraction run, never a raw dict. `to_dict()`/`to_json()` for lossless serialization. `ExtractionResult.failure()` factory ensures every code path returns a complete, serializable result.

#### Extraction Engine
- `extraction/engines/base_engine.py` — `BaseExtractionEngine` abstract interface (`extract()`, `is_available()`, `model_name`, `host`). The only interface extraction business logic and tests depend on.
- `extraction/engines/ollama_engine.py` — `OllamaEngine` implementation. The ONLY file in the codebase that calls Ollama's REST API (`POST /api/chat`). Uses `requests` (already a transitive dependency) — no separate `ollama` Python package needed. Graceful `is_available()` check before every extraction run.

#### Prompt Engineering
- `extraction/prompts/system_prompt.txt` — System prompt instructing the LLM to extract only mentioned fields, use exact enum values, output pure JSON, and signal `{"extraction_possible": false}` for unusable transcripts.
- `extraction/prompts/builder.py` — `PromptBuilder` builds per-run extraction prompts with schema-derived context (stage enums, weather enums, trade enums, field reference). Constructed once per pipeline; `build_prompt()` called per extraction.

#### Postprocessing
- `extraction/postprocessors/json_repairer.py` — `repair_json()` extracts valid JSON from raw LLM output via three strategies: direct parse, markdown fence extraction (` ```json ... ``` `), and outermost-brace search. Returns `(dict, was_repaired)`. `JSONRepairError` on total failure.

#### Validation
- `extraction/validators/schema_validator.py` — `SchemaValidator` runs two-stage validation: JSON Schema structural check (via `jsonschema`) then Sprint 2 `ValidationPipeline` business rules (`applies_to="ai_extraction"`). Reuses existing validation logic with zero duplication.

#### CLI
- `extract.py` — CLI entry point. Extract from a Sprint 3 `SpeechProcessingResult` JSON file, from `--text` string, or check engine availability with `--check`. Supports `--model`, `--host`, `--output`, `--log-date` overrides.

#### Tests
- `tests/test_extraction_models.py` — `ExtractionResult` and `ExtractionMetadata` construction, serialization, accessors, failure factory
- `tests/test_extraction_config.py` — Default config values, `from_env()` env-var reading, partial overrides
- `tests/test_json_repairer.py` — All three repair strategies, boundary cases, error cases
- `tests/test_extraction_pipeline.py` — Full pipeline integration via injected `MockExtractionEngine` (no Ollama, no network, no GPU). Failure modes, JSON repair, `extract_from_speech_result()`, real-Ollama test gated with `skipif`

### Architecture Decisions (Sprint 4)
- ADR-015: Engine-agnostic extraction framework via `BaseLLMProvider` + `EngineFactory` (see DECISIONS.md)
- ADR-016: `ExtractionResult` as a structured object, never a raw dict (see DECISIONS.md)

---

## [Sprint 4.1] 2026-07-06 — Groq Migration + Provider-Agnostic Factory

### Changed

#### Architecture
- Replaced `OllamaEngine` with `GroqEngine` (Groq cloud API, free tier). No disk-resident model required.
- Renamed `BaseExtractionEngine` → `BaseLLMProvider` throughout.
- Introduced `EngineFactory` in `extraction/engines/factory.py`: registry-based factory so `ExtractionPipeline` is provider-blind. Adding a future provider requires only: implement `BaseLLMProvider`, add config, register in factory — zero pipeline changes.
- Renamed `OllamaConfig` → `GroqConfig`; added `provider: str = "groq"` field to `ExtractionConfig`.
- Renamed `ExtractionMetadata.ollama_host` → `engine_endpoint`.
- Removed `--host` CLI flag (Ollama-specific); added `--provider` flag.

#### Removed
- `extraction/engines/ollama_engine.py` — deleted (no Ollama code remains in repo).
- `requests` dependency — was only needed for Ollama REST calls; `groq` package uses httpx.

#### Added
- `extraction/engines/factory.py` — `EngineFactory` with `register()`, `create_from_config()`, `available()`.
- `groq` Python package added to `requirements-dev.txt`.
- `GROQ_API_KEY` env var in `.env` (gitignored) and `.env.example`.
- `TestEngineFactory` test class: registration, creation, unknown-provider error, custom-provider registration/cleanup.

### Architecture Decisions
- ADR-015 revised: documents `BaseLLMProvider` + `EngineFactory` pattern (see DECISIONS.md)
