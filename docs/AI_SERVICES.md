# AI Generation Service Layer — Sprint 5 Reference

**Created:** 2026-07-08
**Sprint:** 5 — AI Generation Services
**Status:** Complete

---

## 1. Overview

Sprint 5 builds the AI Generation Service Layer. It receives a validated
`ConstructionDailyLog` dict (produced by Sprint 4's `ExtractionPipeline`) and
produces four typed business outputs using the Groq LLM API (free tier).

```
ConstructionDailyLog (dict)
    │
    └─► AIServiceManager
            ├─► DailyReportService    ──► DailyReport    (Markdown)
            ├─► CustomerUpdateService ──► CustomerUpdate  (Email)
            ├─► SafetyTalkService     ──► ToolboxTalk    (Markdown)
            └─► MaterialReminderService ► MaterialReminder (Markdown)
```

**Hard constraint:** Business logic NEVER calls Groq directly. All LLM
communication passes through `AIServiceManager`.

---

## 2. Package Structure

```
generation/
├── __init__.py                  Public API (AIServiceManager, all output types)
├── config.py                    GenerationConfig + GenerationGroqConfig
├── manager.py                   AIServiceManager — single orchestration point
│
├── models/
│   ├── __init__.py
│   └── outputs.py               Pydantic output models (ServiceOutput, GenerationResult, ...)
│
├── prompts/
│   ├── __init__.py
│   ├── loader.py                PromptLoader — versioned .md file loading + caching
│   ├── daily_report.md          v1.0.0
│   ├── customer_update.md       v1.0.0
│   ├── safety_talk.md           v1.0.0
│   └── material_reminder.md     v1.0.0
│
├── services/
│   ├── __init__.py
│   ├── base_service.py          BaseAIService (Template Method pattern)
│   ├── daily_report.py          DailyReportService
│   ├── customer_update.py       CustomerUpdateService
│   ├── safety_talk.py           SafetyTalkService
│   └── material_reminder.py     MaterialReminderService
│
└── validators/
    ├── __init__.py
    └── content_validator.py     ContentValidator — AI output quality checks

report.py                        CLI entry point
data/generated/                  Runtime outputs (git-ignored, .gitkeep tracked)
```

---

## 3. Output Models (Pydantic)

### ServiceType (enum)

| Value | Description |
|-------|-------------|
| `daily_report` | Formal Markdown daily site report |
| `customer_update` | Client-facing email |
| `safety_talk` | OSHA-referenced crew safety briefing (Markdown) |
| `material_reminder` | Procurement action list (Markdown) |

### ServiceMetadata

Attached to every successful `ServiceOutput`. Provides full observability:

| Field | Type | Description |
|-------|------|-------------|
| `service_type` | ServiceType | Which service produced this |
| `provider` | str | LLM provider name (e.g. "groq") |
| `model` | str | Model used (e.g. "llama-3.3-70b-versatile") |
| `prompt_name` | str | Prompt file stem |
| `prompt_version` | str | Semantic version from frontmatter |
| `generated_at` | datetime | UTC timestamp |
| `response_time_seconds` | float | LLM call duration |
| `validation_time_seconds` | float | Content validation duration |
| `retry_count` | int | How many retries were needed |
| `prompt_tokens` | int | Tokens sent |
| `completion_tokens` | int | Tokens received |
| `total_tokens` | int | Total token usage |
| `estimated_cost_usd` | float | Always 0.0 (Groq free tier) |

### ServiceOutput

Base type for all service results:

```python
class ServiceOutput(BaseModel):
    success: bool
    service_type: ServiceType
    content: str          # AI-generated text
    errors: list[str]     # empty on success
    warnings: list[str]   # non-fatal quality notes
    metadata: ServiceMetadata | None
```

Typed subclasses: `DailyReport`, `CustomerUpdate`, `ToolboxTalk`, `MaterialReminder`.

### GenerationResult

Aggregated output from `AIServiceManager.generate_all()`:

```python
class GenerationResult(BaseModel):
    success: bool          # True if at least one service succeeded
    log_id: str
    log_date: str
    current_stage: str
    daily_report: DailyReport
    customer_update: CustomerUpdate
    safety_talk: ToolboxTalk
    material_reminder: MaterialReminder
    errors: list[str]
    generated_at: datetime
```

---

## 4. Configuration

Environment variables (all have sensible defaults — only `GROQ_API_KEY` is required):

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | — | Shared with extraction. Get free at console.groq.com |
| `GENERATION_PROVIDER` | `groq` | LLM provider name |
| `GENERATION_GROQ_MODEL` | `llama-3.3-70b-versatile` | Model ID |
| `GENERATION_GROQ_TEMPERATURE` | `0.3` | Higher than extraction (0.1) for natural prose |
| `GENERATION_GROQ_TIMEOUT` | `90` | Seconds (generation takes longer than extraction) |
| `GENERATION_GROQ_MAX_TOKENS` | `2048` | Max tokens per response |
| `GENERATION_MAX_RETRIES` | `3` | Retry attempts on engine failure |

---

## 5. How to Use

### Minimal usage

```python
from generation import AIServiceManager

manager = AIServiceManager()  # reads all config from env

# extracted_log is a ConstructionDailyLog dict from ExtractionResult.extracted_log
result = manager.generate_all(extracted_log)

if result.success:
    print(result.daily_report.content)       # Markdown report
    print(result.customer_update.content)    # Email text
    print(result.safety_talk.content)        # Safety briefing
    print(result.material_reminder.content)  # Procurement list
```

### Single service

```python
from generation import AIServiceManager
from generation.models.outputs import ServiceType

manager = AIServiceManager()
output = manager.generate(ServiceType.DAILY_REPORT, extracted_log)

if output.success:
    print(output.content)
    print(f"Tokens used: {output.metadata.total_tokens}")
```

### CLI

```bash
# Generate all 4 outputs from an extraction result
python report.py data/extracted/result.json --output data/generated/

# Generate a single service
python report.py data/extracted/result.json --service daily_report

# Pipe from extract.py
python extract.py voice_note.json | python report.py --stdin

# Check API availability
python report.py --check
```

### Testing without API key (mock injection)

```python
from extraction.engines.base_engine import BaseLLMProvider
from generation import AIServiceManager

class MockEngine(BaseLLMProvider):
    @property
    def model_name(self): return "mock"
    @property
    def host(self): return "mock://localhost"
    def is_available(self): return True
    def extract(self, prompt): return "## Report\n...", {"prompt_tokens": 10, "completion_tokens": 50}

manager = AIServiceManager(engine=MockEngine())
result = manager.generate_all(log_dict)
```

---

## 6. Prompt System

Prompts live in `generation/prompts/` as `.md` files with versioning frontmatter:

```markdown
---
name: daily_report
version: 1.0.0
description: Generates a formal daily site report for contractor records
supported_models:
  - llama-3.3-70b-versatile
variables:
  - log_date
  - current_stage
  - work_completed
expected_output: markdown
last_updated: 2026-07-08
---

[Prompt body — the instructions sent to the LLM]
```

**To update a prompt:** Edit the `.md` file, bump the `version`, update `last_updated`. No code changes needed. The `PromptLoader` caches per-instance, so a new `AIServiceManager` picks up the change.

**To add a new prompt:** Create a new `.md` file in `generation/prompts/`. The new service's `prompt_name` property returns the file stem.

---

## 7. Content Validation

`ContentValidator` runs on every AI response before it is accepted. Checks:

| Check | What it catches | Error or Warning? |
|-------|----------------|-------------------|
| Empty output | AI returns blank string | Error (immediate) |
| Minimum length | Response too short to be useful | Error |
| Maximum length | Unusually verbose response | Warning |
| Required phrases | Key sections not present | Error |
| Placeholder detection | `{{var}}`, `[INSERT ...]` not filled | Error |
| Duplicate sentences | AI repeating itself | Warning |
| Markdown structure | Headers missing when expected | Warning |

**Per-service minimum lengths:**
- `daily_report`: 300 chars
- `customer_update`: 100 chars
- `safety_talk`: 250 chars
- `material_reminder`: 100 chars

A validation failure (`errors` non-empty) sets `success=False` on the `ServiceOutput`. The raw AI content is preserved in `content` for debugging. Unlike engine exceptions, validation failures do NOT trigger a retry.

---

## 8. Adding a New Service (Future Extensibility)

1. Create `generation/services/new_service.py` implementing `BaseAIService`:

```python
class NewService(BaseAIService):
    @property
    def service_type(self): return ServiceType.NEW_TYPE    # add to enum
    @property
    def prompt_name(self): return "new_service"
    def _build_user_message(self, log: dict) -> str:
        return f"LOG DATA:\n{self._fmt_dict(log.get('new_section'))}"
```

2. Add `NEW_TYPE = "new_type"` to `ServiceType` enum in `generation/models/outputs.py`.

3. Add a field to `GenerationResult`: `new_output: NewOutput`.

4. Register in `AIServiceManager._services` dict.

5. Create `generation/prompts/new_service.md`.

6. Write tests in `tests/test_generation_services.py`.

**No other files need to change.**

---

## 9. Architecture Decisions

See [DECISIONS.md](DECISIONS.md) for full ADR records. Key Sprint 5 decisions:

**ADR-017: Prompts as versioned .md files (not hardcoded strings)**
Prompts are product artifacts, not code. Non-developers must be able to iterate
them without Python knowledge. `.md` files render in GitHub and editors.

**ADR-018: Pydantic for generation output models**
Generation produces business-facing outputs that become API response bodies in
Sprint 7 (FastAPI). Pydantic's `BaseModel` provides JSON serialization and schema
generation needed for OpenAPI docs. Sprints 2–4 keep dataclasses (internal structures).

**ADR-019: One shared engine, full prompts in user message**
`GroqEngine`'s system_prompt is set at construction time (Sprint 4, FROZEN).
Modifying it to support per-call overrides would break the frozen interface.
Solution: one shared engine, system instructions embedded in the user message via
the prompt template file. More efficient (one `is_available()` check), no Sprint 4 changes.

**ADR-020: Prompts in generation/prompts/ (not app/prompts/)**
The specification said `app/prompts/`. But `app/` is Sprint 7's FastAPI directory.
Creating it in Sprint 5 violates the "never create files for future sprints" constraint.
Pattern follows `extraction/prompts/` (module-local prompts).

---

## 10. Test Coverage

| File | Tests | Coverage |
|------|-------|----------|
| `test_generation_models.py` | 27 | Output models, serialization, factory methods |
| `test_generation_config.py` | 14 | Config defaults, env overrides, duck typing |
| `test_generation_prompts.py` | 22 | Prompt loading, frontmatter parsing, caching |
| `test_content_validator.py` | 23 | All 6 validation checks, per-service rules |
| `test_generation_services.py` | 25 | All 4 services, retry, prompt caching |
| `test_generation_manager.py` | 19 | Orchestration, DI, serialization |
| **Total** | **130** | No API key required for any test |

All tests pass with mock injection. Real generation requires `GROQ_API_KEY` in `.env`.
