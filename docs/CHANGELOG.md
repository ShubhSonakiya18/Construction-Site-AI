# CHANGELOG

All notable changes to Construction Site AI are documented here.
Format: `[Sprint X] Date — Description`

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
