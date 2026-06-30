# Next Sprint: Sprint 3 — Audio Processing & AI Extraction Foundation

**Status:** AWAITING SPRINT 2 APPROVAL — Do not begin until Sprint 2 is approved.
**Prerequisites:** Sprint 2 APPROVED and FROZEN
**Estimated Duration:** 4–6 days of implementation

---

## Context: Why Sprint 3

Sprint 2 produced the training data. Sprint 3 processes real audio into the same structured format.

The core product flow is:
```
[Foreman speaks voice note on phone]
    ↓
[Sprint 3: Faster Whisper transcribes audio → raw text]
    ↓
[Sprint 4: Qwen2.5 extracts ConstructionDailyLog from text]
    ↓
[Sprint 5: AI-generated customer update from log]
    ↓
[Sprint 7: API + web app delivers update to client]
```

Sprint 3 is the INPUT layer: audio files in, validated transcript text out.

---

## Objectives

1. **Audio ingestion** — Accept MP3/WAV/M4A voice files from foreman's phone
2. **Transcription** — Faster Whisper running locally (no cloud, no paid API) converts audio to text
3. **Transcript validation** — Basic quality checks before passing to AI extraction
4. **Test transcripts** — 10+ real construction voice note recordings with ground-truth transcripts

---

## Deliverables

### 1. Audio Processing Module

```
audio_processing/
├── __init__.py
├── config.py              # Audio settings (model size, language, device)
├── transcriber.py         # FasterWhisper wrapper
├── audio_validator.py     # Pre-transcription audio quality checks
├── transcript_cleaner.py  # Post-transcription cleanup (filler words, [INAUDIBLE])
└── models/                # Faster Whisper model cache (not committed)
```

**Technology:** `faster-whisper` Python package. Uses Whisper-medium model locally.
No cloud. No OpenAI API. Everything runs on CPU (or GPU if available).

### 2. Sample Audio Files

```
data/sample_audio/
├── README.md             # Recording instructions for contractors
├── foundation_pour.mp3   # Example: foundation pour day
├── framing_day1.mp3      # Example: first day of framing
├── inspection_pass.mp3   # Example: inspection passed
├── rain_delay.mp3        # Example: weather delay
└── ...                   (10+ recordings minimum)
```

Ground-truth transcripts stored alongside each audio file.

### 3. Transcript Corpus

```
data/transcripts/
├── raw/           # Verbatim Whisper output
└── cleaned/       # Post-processed transcripts
```

### 4. Integration Test

`tests/test_audio_pipeline.py` — Runs full pipeline on sample audio files and
verifies transcripts match ground truth within acceptable word error rate (WER < 20%).

---

## Technical Requirements

### Faster Whisper Setup

```bash
pip install faster-whisper
```

Model sizes (tradeoffs):
| Model | Size | Speed | Accuracy |
|-------|------|-------|----------|
| tiny | 75MB | Very fast | Lower |
| base | 150MB | Fast | Medium |
| **medium** | **1.5GB** | **Moderate** | **Good** |
| large-v3 | 3GB | Slow | Best |

**Recommendation:** `medium` for development, `large-v3` for production.

### Hardware

- CPU-only: Acceptable for development (medium model ≈ 2-4x real time)
- GPU: Recommended for production (medium model ≈ 0.3x real time)
- M1/M2 Mac: Use `device="mps"` for Apple Silicon acceleration

### Language Handling

- Primary: English (`language="en"`)
- Future: Spanish (foreman population often bilingual — Sprint 8+)
- Faster Whisper auto-detects if `language=None`

---

## Acceptance Criteria

Sprint 3 is only complete when ALL of the following are true:

### Audio Processing
- [ ] `AudioTranscriber` class wraps Faster Whisper with clean API
- [ ] Supports MP3, WAV, M4A, OGG, FLAC input formats
- [ ] Returns transcript + confidence score + language detected
- [ ] Handles missing audio file gracefully (FileNotFoundError, not crash)
- [ ] Handles corrupt/empty audio gracefully

### Transcript Quality
- [ ] Word Error Rate (WER) < 20% on sample construction audio files
- [ ] Construction-specific terms transcribed correctly ≥ 80% of the time
  - "footing", "rebar", "fascia", "soffit", "drywall", "HVAC", "OSB", "PEX"
- [ ] Timestamps available for long recordings

### Sample Data
- [ ] Minimum 10 sample audio files with verified transcripts
- [ ] Minimum 3 files with construction-specific vocabulary
- [ ] At least 1 file with background noise (realistic site conditions)
- [ ] At least 1 file with multiple speakers
- [ ] Ground truth transcripts verified manually

### Testing
- [ ] `pytest tests/test_audio_pipeline.py` passes
- [ ] WER calculation implemented and passing threshold

### Documentation
- [ ] `audio_processing/README.md` — How to record, how to run transcription
- [ ] `data/sample_audio/README.md` — Recording instructions for contractors

---

## Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Construction jargon transcribed incorrectly | High | High | Custom vocabulary hints in Faster Whisper; curate examples of misrecognitions |
| Background noise degrades transcription | Medium | Medium | Use noise-cancelling settings; document recording best practices |
| GPU not available for development | Medium | Low | CPU mode is slower but works for development |
| "Rebar" transcribed as "re-bar" or "re bar" | High | Low | Transcript cleaner normalizes common construction term variations |

---

## Dependencies

**Must be complete before Sprint 3 starts:**
- [x] Sprint 1: All 6 knowledge files
- [x] Sprint 2: `ConstructionDailyLog` schema v1.0.0
- [x] Sprint 2: `dataset_generation_framework/` (for validation pipeline reuse in Sprint 4)

**New Python packages needed:**
```
faster-whisper==1.1.1    # Local speech-to-text (no cloud)
soundfile==0.12.1        # Audio file loading
librosa==0.10.2          # Audio analysis (duration, sample rate)
jiwer==3.0.4             # Word Error Rate calculation
```

**No Docker required for Sprint 3** — pure Python. Faster Whisper downloads models on first run.

---

## Important Note

**This document describes Sprint 3. Do NOT implement Sprint 3 until Sprint 2 is explicitly approved.**

Sprint 2 must be reviewed, all datasets generated successfully, and the project owner must say
"Sprint 2 approved" before any Sprint 3 work begins.

The STOP rule applies: after completing any sprint, stop and wait for explicit approval.
