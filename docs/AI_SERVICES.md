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

4. Register in `DEFAULT_SERVICE_REGISTRY` in `generation/services/registry.py`.

5. Create `generation/prompts/new_service.md`.

6. Register in `DEFAULT_PROMPT_REGISTRY` in `generation/prompts/registry.py`.

7. Write tests.

**No other files need to change.**

---

## 9. Sprint 5.1 — Hardening Additions

### Prompt Cache (mtime-aware)

`PromptLoader` tracks each cached file's modification time. On every `load()` call, if the file was edited since it was cached, the stale entry is evicted and the file is re-read. No process restart needed during prompt development.

```python
# Edit generation/prompts/daily_report.md → picked up on next generate() call
loader = PromptLoader()
prompt = loader.load("daily_report")  # disk read if changed, cache hit if unchanged
```

### Prompt Registry

```python
from generation.prompts.registry import DEFAULT_PROMPT_REGISTRY

# Discover all registered prompts
names = DEFAULT_PROMPT_REGISTRY.list_names()  # ['customer_update', 'daily_report', ...]

# Get metadata for a prompt
entry = DEFAULT_PROMPT_REGISTRY.get("daily_report")
print(entry.expected_output)  # "markdown"
print(entry.variables)        # ['log_date', 'current_stage', ...]

# Validate a prompt name (raises ValueError if not registered)
DEFAULT_PROMPT_REGISTRY.validate("unknown_prompt")

# Register a new prompt (add this to registry.py):
DEFAULT_PROMPT_REGISTRY.register(PromptRegistration(
    name="punch_list",
    description="End-of-project punch list",
    expected_output="markdown",
    service_class_name="PunchListService",
    variables=["log_date", "current_stage", "work_completed"],
))
```

### Service Registry

```python
from generation.services.registry import DEFAULT_SERVICE_REGISTRY

# List all registered service types
types = DEFAULT_SERVICE_REGISTRY.list_types()

# Register a new service (add this to registry.py):
DEFAULT_SERVICE_REGISTRY.register(ServiceRegistration(
    service_type=ServiceType.PUNCH_LIST,
    service_class=PunchListService,
    description="End-of-project punch list",
))

# AIServiceManager with partial registry (for testing):
from generation.services.registry import ServiceRegistry, ServiceRegistration
mini_reg = ServiceRegistry()
mini_reg.register(ServiceRegistration(
    service_type=ServiceType.DAILY_REPORT,
    service_class=DailyReportService,
    description="",
))
manager = AIServiceManager(engine=mock_engine, service_registry=mini_reg)
```

### Observability

```python
from generation.observability import METRICS, Timer

# Timer usage
with Timer() as t:
    result = manager.generate_all(log)
print(f"Total: {t.elapsed:.2f}s")

# Metrics summary
summary = METRICS.summary()
print(summary["totals"]["success_rate"])
print(summary["cache"]["hit_rate"])
print(summary["per_service"]["daily_report"]["avg_response_time_seconds"])

# Reset between runs (in tests, done automatically via autouse fixture)
METRICS.reset()
```

Events are emitted automatically by `BaseAIService.generate()`. No caller changes needed.

### generation_id Correlation

Every `ServiceMetadata` now carries a `generation_id` (UUID4). The same ID is used in all log messages and observability events for that generation call.

```python
result = manager.generate(ServiceType.DAILY_REPORT, log)
if result.metadata:
    print(result.metadata.generation_id)  # e.g. "a3f7c2d1-..."
```

---

## 10. Architecture Decisions

See [DECISIONS.md](DECISIONS.md) for full ADR records.

**ADR-017: Prompts as versioned .md files** — Product artifacts, not code. Non-developers iterate without Python.

**ADR-018: Pydantic for generation output models** — Sprint 7 FastAPI readiness; `model_dump(mode="json")` for free.

**ADR-019: One shared engine, system instructions in user message** — Respects Sprint 4 FROZEN interface.

**ADR-020: Prompts in generation/prompts/** — Follows `extraction/prompts/` pattern; `app/` is Sprint 7.

**ADR-021: Mtime-aware prompt cache** — File edits picked up without restart; removes dual-cache anti-pattern.

**ADR-022: PromptRegistry** — Domain-level prompt discovery; separates I/O (PromptLoader) from domain (what exists).

**ADR-023: ServiceRegistry** — Open/Closed extensibility; adding a service = 1 class + 1 register call.

**ADR-024: generation_id UUID4** — Per-call correlation key across logs, events, and DB records.

**ADR-025: Lightweight in-process observability** — No Prometheus, no cloud. Forward-compatible with Sprint 7.

---

## 11. Test Coverage

| File | Tests | Coverage |
|------|-------|----------|
| `test_generation_models.py` | 32 | Output models, serialization, generation_id |
| `test_generation_config.py` | 14 | Config defaults, env overrides, duck typing |
| `test_generation_prompts.py` | 22 | Prompt loading, frontmatter parsing, caching |
| `test_content_validator.py` | 23 | All 6 validation checks, per-service rules |
| `test_generation_services.py` | 26 | All 4 services, retry, prompt caching |
| `test_generation_manager.py` | 19 | Orchestration, DI, serialization |
| `test_prompt_cache.py` | 12 | Mtime tracking, auto-reload, multi-prompt |
| `test_prompt_registry.py` | 23 | Register/get/validate, DEFAULT_PROMPT_REGISTRY |
| `test_service_registry.py` | 24 | Register/create_all, DEFAULT_SERVICE_REGISTRY, DI |
| `test_observability.py` | 48 | Timer, all event types, metrics counters/aggregates |
| **Total** | **243** | No API key required for any test |

All tests pass with mock injection. Real generation requires `GROQ_API_KEY` in `.env`.
