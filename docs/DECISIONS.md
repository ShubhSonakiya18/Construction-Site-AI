# Architecture Decision Record (ADR)

**Construction Site AI — Engineering Decisions Log**

Every significant technical decision is recorded here with context, rationale, alternatives considered, and consequences. This document allows future engineers (or future Claude sessions) to understand WHY decisions were made, not just WHAT was decided.

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
**Status:** Accepted — Non-negotiable requirement

**Context:**
We need AI capabilities (speech-to-text, text generation) for the core product. The choices are: cloud AI APIs or local models.

**Decision:**
100% local AI. Ollama + Qwen2.5 for language models. Faster Whisper for speech-to-text. No cloud AI APIs of any kind.

**Rationale:**
- **Cost**: Cloud APIs charge per token/request. At 5,000 daily logs per sprint, cloud API costs become significant.
- **Privacy**: Construction site data (client names, addresses, worker information) should not leave the contractor's infrastructure.
- **Reliability**: No external API dependency means no downtime from third-party service outages.
- **Control**: We can fine-tune local models on construction domain data in future sprints. Cannot fine-tune proprietary cloud APIs.
- **Vendor independence**: Not locked to any provider's pricing, terms, or availability.

**Alternatives Considered:**
- **OpenAI GPT-4**: Better quality, but paid, cloud-only, no fine-tuning on domain data.
- **Anthropic Claude API**: Same concerns.
- **Hybrid**: Use cloud for development, local for production. Adds complexity, two systems to maintain.

**Consequences:**
- Hardware requirements: Local AI needs GPU for reasonable performance. CPU-only is acceptable for development but slow.
- Model quality: Qwen2.5 7B is good but not GPT-4 level. Acceptable for structured extraction from constrained voice notes.
- Deployment: `docker-compose.yml` will include Ollama container. No external setup required.

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

## Pending Decisions (Future Sprints)

| Decision | Context | Sprint |
|----------|---------|--------|
| Redis vs in-memory caching | For caching Ollama inference results | Sprint 4 |
| Celery vs FastAPI Background Tasks | For async audio processing | Sprint 7 |
| PostgreSQL vs TimescaleDB | For time-series analytics data | Sprint 6 |
| Alembic auto-generate vs hand-write migrations | Database migration strategy | Sprint 6 |
| Docker multi-stage build | Optimize image size | Sprint 7+ |
| JWT vs Session tokens | Authentication strategy | Sprint 7 |
| FAISS vs ChromaDB vs Weaviate | Vector store for RAG | Future |
