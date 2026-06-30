# ConstructionDailyLog Schema Design

**Sprint 1 Architecture Document**

---

## The Central Role of This Schema

The `ConstructionDailyLog` schema is the single most important piece of engineering in this project. Every other component is either a producer or consumer of this schema:

```
Voice Recording
      ↓
[Sprint 3] Faster Whisper → raw_transcript
      ↓
[Sprint 4] Qwen2.5 AI Extraction → ConstructionDailyLog (populated)
      ↓
[Sprint 5] Five AI Services consume ConstructionDailyLog:
           ├─ Daily Report Generator
           ├─ Customer Update Generator
           ├─ Safety Toolbox Generator
           └─ Material Reminder Generator
      ↓
[Sprint 6] PostgreSQL → Store ConstructionDailyLog fields across normalized tables
      ↓
[Future] Analytics, Scheduling, Cost Prediction — all read from same data
```

Getting this schema wrong means rewriting every downstream component. We design it to be complete now.

---

## Design Decisions and Why

### Decision 1: JSON Schema (not Pydantic first)

**What we chose:** JSON Schema draft-07 as the source of truth.

**Why not Pydantic directly?**

Pydantic is a Python library. If we define the schema in Pydantic first, the schema becomes Python-specific and hard to share:
- JavaScript frontend cannot read it
- Dataset generators (Python scripts) must import our app code just to validate data
- Documentation generators need to run Python

**Why JSON Schema?**

JSON Schema is language-agnostic. From one JSON Schema file, we can:
- Auto-generate Pydantic v2 models (`datamodel-code-generator`)
- Auto-generate TypeScript types for the React frontend (Sprint later)
- Validate data from any programming language
- Generate documentation automatically
- Use `$ref` to reference shared definitions

**Alternative considered:** Protobuf. Overkill for this use case. Adds compilation step, poor human readability, unnecessary for a web API.

---

### Decision 2: UUID Primary Keys (not auto-increment integers)

**What we chose:** UUID format strings for all ID fields.

**Why not auto-increment integers?**

Auto-increment integers (`1, 2, 3, 4...`) seem simpler but cause real problems:

1. **Enumeration attacks** — An API like `GET /logs/1, /logs/2, /logs/3` lets anyone scrape all logs sequentially. UUIDs make this impossible.
2. **Multi-database merging** — When we eventually need to merge logs from multiple sites or databases, integer IDs collide. UUIDs never collide.
3. **Client-side generation** — Mobile apps can generate their own UUID before sending to server, enabling offline-first operation. Can't do this with server-generated integers.
4. **Predictability** — Clients should not be able to infer "how many records exist" from an ID.

**Trade-off:** UUIDs are 36 characters vs 4-8 digits. Marginally larger storage. Completely irrelevant at this scale.

**Industry standard:** All major SaaS platforms (Stripe, Twilio, GitHub) use UUIDs or similar for public-facing IDs.

---

### Decision 3: Nullable Fields Are Explicit

**What we chose:** All optional fields are typed as `["string", "null"]` rather than just `"string"` with no requirement.

**Why this matters:**

This distinction is critical for the AI extraction pipeline:

```json
// Version A - field is missing entirely (bad):
{ "inspector_name": /* not present */ }

// Version B - field is explicitly null (good):
{ "inspector_name": null }
```

When the AI extracts data and a field is not mentioned in the transcript, it should output `null` — not omit the field. This allows us to know the difference between:
- **Field is null** → "The AI processed this field and found nothing"
- **Field is missing** → "This log was created by an old schema version that didn't have this field"

This distinction matters for data migration, debugging, and audit purposes.

**Common beginner mistake:** Making everything optional and never handling the difference between null and missing. This creates bugs that are very hard to find.

---

### Decision 4: Section Architecture — 12 Logical Sections

The schema is organized into 12 sections. Each section has a clear responsibility:

| Section | Primary Consumer | Why Separate |
|---------|-----------------|--------------|
| Metadata | All modules | Log identification, versioning, audit |
| Project Context | All modules | Identifies which project/client |
| Construction Stage | AI Extraction, Analytics | Enables stage validation rules |
| Weather | Safety module, Delay analysis | Impacts productivity and safety |
| Workforce | Daily Report, Cost Tracking | Core daily record |
| Work Completed | Customer Update, Progress | What happened today |
| Materials | Material Reminder, Inventory | Procurement intelligence |
| Equipment | Cost Tracking | Daily equipment cost |
| Safety | Safety Toolbox Generator | Tomorrow's toolbox topic |
| Delays | Schedule Analysis | Why progress is behind |
| Inspections | Compliance tracking | Code compliance record |
| Tomorrow's Plan | Material Reminder, Toolbox | Forward-looking planning |
| Client Communication | CRM integration | Relationship management |
| AI Generated Outputs | API responses | Stores generated content |
| Audit | Compliance | Who touched this record |

**Why not one flat structure?**

A flat structure with 80 fields at the same level is impossible to reason about. Grouping into sections:
- Makes it clear which fields belong together
- Allows the AI extraction prompt to address one section at a time
- Allows the database to normalize into sensible tables
- Makes the Pydantic models readable

---

### Decision 5: `ai_generated_outputs` Is Part of the Log

**What we chose:** Store AI-generated content (customer emails, safety talks, etc.) inside the ConstructionDailyLog document.

**Why not store them in separate documents?**

The AI outputs are always derived from a specific log. They are inseparable from their source. Keeping them together:
- One API call returns everything related to a day's log
- Easier to re-generate (just find the log, re-run AI)
- Simpler data model (no join required to get "the email generated from this log")

**Trade-off:** The JSON document becomes large (could be 20KB with all outputs). This is fine. PostgreSQL JSONB columns handle this efficiently.

**When this design breaks:** If we need to search across all customer emails ever generated, a JSON field is inefficient. At that point we'd extract the `customer_progress_update` into its own table. The schema supports this — the field is clearly named and typed.

---

### Decision 6: Explicit Enum Values for Key Fields

**What we chose:** Strict enums for fields like `current_stage`, `delay_type`, `trade`, `incident_type`.

**Why enums matter for AI systems:**

When Qwen2.5 extracts information and must choose a value for `delay_type`, it should choose from: `["weather", "material_shortage", "material_delivery_late", ...]` — not invent "rain delay" or "late materials" or "supply chain issue."

Standardized values enable:
- Aggregation queries ("How many weather delays this project?")
- Cross-project comparison ("Which trade has the most delay days?")
- Reliable filtering in the frontend
- Machine learning features in future modules

**Common beginner mistake:** Using free-text strings for values that are really categories. You end up with `"weather"`, `"Weather"`, `"rain"`, `"rain delay"`, `"weather delay"` all meaning the same thing, and analytics becomes impossible.

**Trade-off:** New delay types or trades not in the enum require a schema version bump. This is intentional — it forces us to think about categorization rather than accepting random strings.

---

### Decision 7: `raw_transcript` Stored on the Log

**What we chose:** Store the verbatim voice recording transcript on the log record.

**Why keep the raw transcript?**

1. **Re-processing** — If we improve the AI extraction model, we can re-run extraction on old transcripts without re-doing speech-to-text.
2. **Audit** — If a foreman claims they said something the AI missed, we have the transcript to check.
3. **Training data** — Transcript + extracted log = a training example for future fine-tuning.
4. **Debugging** — When AI extraction produces wrong output, the transcript tells us why.

**Storage concern:** A 5-minute voice recording transcribes to ~800 words. At 5,000 logs, that's 4 million words = ~30MB of text. Negligible.

---

### Decision 8: Forward Compatibility Fields

Several fields are designed for **future modules that don't exist yet:**

| Field | Future Module |
|-------|--------------|
| `attachments[].linked_defect_id` | Defect Detection module (Sprint ~8) |
| `attachments[].ai_analysis_result` | Computer Vision module |
| `financials.*` | Cost Tracking module |
| `tomorrow_plan.planned_tasks[].linked_schedule_task_id` | Scheduling module |
| `project.contract_value_usd` | Bid Estimation module |
| `materials.used_today[].unit_cost_usd` | Cost Prediction module |

**Why add these now if the modules don't exist?**

Because adding a field to a schema later requires:
1. Updating the JSON schema (minor)
2. Updating the Pydantic model (minor)
3. Running a database migration to add the column (non-trivial in production)
4. Updating the AI extraction prompt to populate the field (significant)
5. Re-processing all old logs to backfill the field (very expensive)

If we design the field now, future modules can populate it without any schema or database changes. The field is nullable by default, so having it empty costs nothing.

---

### Decision 9: Versioning in the Schema

**What we chose:** `schema_version: "1.0.0"` on every log document.

**Why version the schema?**

Schemas change over time. When Sprint 4 finds that we need a field we didn't design in Sprint 1, we need to update the schema. When we do:
- Old logs will have `schema_version: "1.0.0"` with the old structure
- New logs will have `schema_version: "1.1.0"` with new fields
- The application can check `schema_version` to know how to interpret the document
- Migration scripts can upgrade old documents

Without versioning, you cannot tell whether a missing field means "this log was created before this field existed" or "the AI failed to extract this field." These require different handling.

---

## Fields That Enable Each AI Service

### AI Service 1: Structured Daily Report
Reads: `project`, `current_stage`, `weather`, `workforce`, `work_completed`, `delays`, `inspections`
Produces: `ai_generated_outputs.structured_daily_report`

### AI Service 2: Customer Progress Update
Reads: `project.client_name`, `current_stage`, `overall_project_completion_percent`, `work_completed`, `delays`, `tomorrow_plan`
Produces: `ai_generated_outputs.customer_progress_update`

### AI Service 3: Safety Toolbox Talk
Reads: `current_stage`, `tomorrow_plan.planned_tasks`, `safety.hazards_identified`, `safety.incidents`
Produces: `ai_generated_outputs.safety_toolbox_talk`
Logic: Tomorrow's planned work → look up hazards from `knowledge/construction_stages.json` → generate relevant safety talk

### AI Service 4: Material Reminder
Reads: `materials.shortage_flags`, `materials.required_for_tomorrow`, `tomorrow_plan.materials_to_order`
Produces: `ai_generated_outputs.material_reminder`

---

## Schema Validation Rules

The AI extraction engine (Sprint 4) must enforce:

### Hard Validation Rules
1. `log_date` must be a valid date in YYYY-MM-DD format
2. `current_stage` must be one of the defined enum values
3. `schema_version` must be "1.0.0" (current)
4. `project.project_id` must be a valid UUID format
5. `review_status` must default to "draft" on extraction
6. All percentage fields must be 0–100

### Business Logic Rules
1. If `delays` contains an item with `delay_type: "weather"`, then `weather.work_stopped_due_to_weather` should be `true`
2. If `safety.incidents` has items with `osha_recordable: true`, then `review_status` should be escalated
3. If `current_stage` is `"painting"`, then `work_completed` should not contain framing-related tasks
4. If `inspections` has items with `result: "failed"`, `delays` should reference an inspection failure

### What to Do with Invalid JSON from AI
The extraction engine will:
1. Attempt extraction (prompt → Qwen2.5 → JSON)
2. Parse the JSON
3. Validate against this schema
4. If validation fails: log error, retry with corrected prompt (max 3 retries)
5. If all retries fail: store the raw transcript, mark log as `review_status: "draft"` for human review
6. **Never store malformed JSON in the database**

---

## Future Schema Evolution

Planned additions in future sprints:

| Field | Sprint | Purpose |
|-------|--------|---------|
| `defects[]` | Sprint 8 | Defect tracking from photos |
| `schedule_variance_days` | Sprint 9 | Schedule adherence tracking |
| `cost_earned_value` | Sprint 10 | Earned value analysis |
| `weather.forecast_tomorrow` | Sprint 7 | Auto-fetched weather forecast |
| `crew_productivity_index` | Sprint 9 | ML-calculated productivity score |

---

## What We Did NOT Include and Why

### Worker PII (Personally Identifiable Information)
We store `worker_identifier` (a name or ID string) but not full worker profiles in the log. Full worker data lives in a separate `workers` table. This follows data minimization principles (GDPR, CCPA) — don't store more personal data than you need in each document.

### Real-time GPS Tracking
Not in scope. Adding GPS coordinates to the log is designed-in (`attachments[].gps_coordinates`) but live tracking is a separate system.

### Payroll/Wage Data
Daily labor cost is included as a summary field but individual worker wages are not in the log schema. Those belong in the payroll system.

### Weather Auto-fetch
The schema has weather fields but they are manually populated by AI extraction. Auto-fetching weather from an API is a future enhancement (we don't want external API dependencies in early sprints).
