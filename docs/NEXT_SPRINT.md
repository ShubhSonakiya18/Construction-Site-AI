# Next Sprint: Sprint 5 — AI Generation Services

**Status:** AWAITING SPRINT 4 APPROVAL — Do not begin until Sprint 4 is approved.
**Prerequisites:** Sprint 4 APPROVED and FROZEN
**Supersedes:** Sprint 4 spec (now complete — see `extraction/` package and `docs/AI_PIPELINE.md`)

---

## Context: Why Sprint 5

Sprint 4 produces a validated `ExtractionResult` containing a
`ConstructionDailyLog` dict. Sprint 5 turns that structured log into the
human-readable outputs the product promises:

```
[Foreman speaks voice note]
    ↓
[Sprint 3 — DONE: speech/ → SpeechProcessingResult]
    ↓
[Sprint 4 — DONE: extraction/ → ExtractionResult (ConstructionDailyLog)]
    ↓
[Sprint 5: ExtractionResult → 4 AI-generated outputs]
        ├── Customer progress update (email)
        ├── Formal daily site report
        ├── Safety toolbox talk
        └── Material reminder / order list
    ↓
[Sprint 6: Save to PostgreSQL]
```

Sprint 5 is the GENERATION layer: structured log in, natural-language
outputs out.

---

## High-Level Objectives (per ROADMAP.md)

1. **Customer progress update generator** — plain-English email from the
   `ConstructionDailyLog`, suitable for sending directly to the client
2. **Daily report generator** — formal structured report for the contractor's
   records; includes all fields, not just the customer-friendly subset
3. **Safety toolbox talk generator** — OSHA-relevant safety briefing drawn
   from the day's hazards and incidents
4. **Material reminder generator** — concise list of materials to order /
   follow up on, derived from `materials.shortage_flags` and
   `tomorrows_plan.materials_to_order`
5. **All generators independently testable** — same pattern as Sprint 4:
   `BaseLLMProvider` interface, mock engine for tests, real `GroqEngine` gated
   behind `HAS_GROQ` check; uses `EngineFactory` for provider selection
6. **Prompts stored separately from code** — editable `.txt` files per
   generator, not hardcoded strings

---

## Explicitly Deferred to Sprint Kickoff

Per the project's "never create files or folders for future sprints" rule,
this document intentionally does **not** prescribe a module layout, file
list, or detailed acceptance criteria yet. Those will be defined at the start
of Sprint 5, informed by:
- The `extraction/` package pattern (`BaseLLMProvider`, `EngineFactory`, `ExtractionResult`,
  `PromptBuilder`) as the precedent for generation engine design
- Prompt engineering lessons from Sprint 4

---

## Dependencies

**Must be complete before Sprint 5 starts:**
- [x] Sprint 1: All 6 knowledge files
- [x] Sprint 2: `ConstructionDailyLog` schema + synthetic dataset (training examples)
- [x] Sprint 3: `speech/` framework → `SpeechProcessingResult`
- [x] Sprint 4: `extraction/` framework → `ExtractionResult`

**Likely new tooling (to be confirmed at Sprint 5 kickoff):**
- Groq API (same as Sprint 4) — `GROQ_API_KEY` already in `.env`; model can be
  overridden via `EXTRACTION_GROQ_MODEL` for a generation-optimised choice
- No new paid APIs — Groq free tier covers all usage so far

---

## Important Note

**This document outlines Sprint 5 at a high level only. Do NOT implement
Sprint 5 until Sprint 4 is explicitly approved.**

The STOP rule applies: after completing any sprint, stop and wait for
explicit approval.
