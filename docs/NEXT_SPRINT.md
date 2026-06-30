# Next Sprint: Sprint 4 — AI Information Extraction

**Status:** AWAITING SPRINT 3 APPROVAL — Do not begin until Sprint 3 is approved.
**Prerequisites:** Sprint 3 APPROVED and FROZEN
**Supersedes:** The previous version of this document, which specified Sprint 3
(Audio Processing). Sprint 3 is now complete — see `docs/SPEECH_PIPELINE.md`
and `docs/AI_PIPELINE.md` for what was actually built. The delivered
architecture (`speech/` package, `BaseSTTEngine` abstraction) differs in
structure from the original Sprint 3 sketch below but satisfies the same
objectives; the dataset/training-data references in that original sketch are
preserved here for history.

---

## Context: Why Sprint 4

Sprint 3 produces a clean, structured transcript (`SpeechProcessingResult`)
from a foreman's voice note. Sprint 4 turns that transcript into a
schema-valid `ConstructionDailyLog` record.

```
[Foreman speaks voice note on phone]
    ↓
[Sprint 3 — DONE: speech.SpeechProcessingPipeline → SpeechProcessingResult]
    ↓
[Sprint 4: Local LLM extracts ConstructionDailyLog from transcript text]
    ↓
[Sprint 5: AI-generated customer update from log]
    ↓
[Sprint 7: API + web app delivers update to client]
```

Sprint 4 is the EXTRACTION layer: transcript text in, validated
`ConstructionDailyLog` out.

---

## High-Level Objectives (per ROADMAP.md)

1. **Local LLM integration** — Qwen2.5 (or comparable open-weight model) via
   Ollama, no paid API
2. **Structured extraction** — transcript text → `ConstructionDailyLog`
   matching `knowledge/construction_daily_log_schema.json`
3. **Prompt engineering** — extraction prompts, few-shot examples drawn from
   the Sprint 2 synthetic dataset
4. **Schema validation** — every extraction validated against the schema and
   `knowledge/validation_rules.json` (reusing the Sprint 2
   `dataset_generation_framework` validation pipeline, per ADR precedent of
   not duplicating validation logic)
5. **Retry / repair logic** — invalid or malformed JSON output must be
   retried or rejected; malformed JSON is never stored
6. **Confidence handling** — partial or ambiguous transcripts should produce
   partial extractions with field-level confidence, not silent failures

---

## Explicitly Deferred to Sprint Kickoff

Per the project's "never create files or folders for future sprints" rule,
this document intentionally does **not** prescribe a module layout, file
list, or detailed acceptance criteria yet. Those will be defined at the
start of Sprint 4, informed by:
- The `speech/` package's engine-abstraction pattern (`BaseSTTEngine`) as a
  precedent for an analogous extraction-engine interface
- Lessons from Sprint 3 (lazy model loading, structured result objects,
  graceful degradation for optional dependencies)

---

## Dependencies

**Must be complete before Sprint 4 starts:**
- [x] Sprint 1: All 6 knowledge files
- [x] Sprint 2: `ConstructionDailyLog` schema v1.0.0 + synthetic dataset generators
- [x] Sprint 3: `speech/` framework producing `SpeechProcessingResult`

**Likely new tooling (to be confirmed at Sprint 4 kickoff):**
- Ollama (local LLM runtime, free/open source)
- Qwen2.5 model weights (free, open weight)

No paid APIs. No cloud inference. Consistent with the project's hard
constraint of free/open-source-only AI components.

---

## Important Note

**This document outlines Sprint 4 at a high level only. Do NOT implement
Sprint 4 until Sprint 3 is explicitly approved.**

Sprint 3 must be reviewed and the project owner must say "Sprint 3 approved"
before any Sprint 4 work begins.

The STOP rule applies: after completing any sprint, stop and wait for
explicit approval.
