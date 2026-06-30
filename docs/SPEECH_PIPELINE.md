# Speech Processing Framework

**Module:** `speech/`
**Status:** Sprint 3 — COMPLETE
**Public entry point:** `speech.SpeechProcessingPipeline`

---

## Purpose

Converts a raw audio recording (a foreman's voice note) into a structured
`SpeechProcessingResult` — clean transcript text, per-segment timestamps,
confidence scores, and a full audit trail of how the result was produced.

Business logic never talks to a speech-to-text engine directly. It talks to
`SpeechProcessingPipeline.process()`, which returns a `SpeechProcessingResult`.
The current implementation uses Faster Whisper, but nothing outside
`speech/whisper/engine.py` knows that.

```
[Audio file] -> SpeechProcessingPipeline.process() -> SpeechProcessingResult
```

---

## Design Principle: Engine Abstraction

> "Business logic should never directly call Faster Whisper."

This is enforced structurally, not by convention:

```
speech/whisper/engine.py
    from faster_whisper import WhisperModel   <-- the ONLY import of faster_whisper
                                                   in the entire framework
```

Every other file in `speech/` — and every file outside `speech/` — talks to
the `BaseSTTEngine` interface:

```python
class BaseSTTEngine(ABC):
    @abstractmethod
    def transcribe(self, audio_path: str) -> Transcript: ...

    @abstractmethod
    def is_available(self) -> bool: ...
```

`FasterWhisperEngine` is the only concrete implementation today. Swapping in a
different engine (a future local model, a different CTranslate2 backend, a
hand-rolled wav2vec2 wrapper) means writing a new `BaseSTTEngine` subclass and
passing it to `SpeechProcessingPipeline(engine=...)`. No other file changes.

```python
class MyAlternativeEngine(BaseSTTEngine):
    def transcribe(self, audio_path: str) -> Transcript: ...
    def is_available(self) -> bool: ...

pipeline = SpeechProcessingPipeline(engine=MyAlternativeEngine())
```

---

## Pipeline Stages

`SpeechProcessingPipeline.process(audio_path)` runs these stages in order.
Each stage is independently recoverable — a failure in preprocessing does not
abort the run; a failure in validation or transcription does.

| # | Stage | Module | On failure |
|---|---|---|---|
| 1 | Metadata init | `metadata/extractor.py` | N/A (always succeeds) |
| 2 | Validation | `validators/audio_validator.py` | **Abort.** Return `SpeechProcessingResult.failure()` |
| 3 | Normalization | `preprocessors/audio_normalizer.py` | Warn, continue with original file |
| 4 | Noise reduction | `preprocessors/noise_reducer.py` | Warn, continue with original file |
| 5 | Transcription | `whisper/engine.py` | **Abort.** Return `SpeechProcessingResult.failure()` |
| 6 | Postprocessing | `postprocessors/transcript_cleaner.py` | Warn, use raw transcript |
| 7 | Metadata finalize | `metadata/extractor.py` | N/A (always succeeds) |

### Stage 2 — Validation (`AudioValidator`)

Runs **before** any transcription attempt. Eight blocking checks, in order
(each short-circuits on first failure to avoid wasted work):

1. File existence
2. Minimum file size (rejects empty/stub files, default 1 KB)
3. Format recognition (extension + magic-byte fallback)
4. Maximum file size (default 500 MB)
5. Readability (can soundfile/librosa open it?)
6. Duration bounds (default 0.5s–7200s / 2 hours)
7. Minimum sample rate (default 8000 Hz)
8. Maximum channel count (default 2)

Three non-blocking warnings: sample rate below 16 kHz, stereo audio (will be
downmixed), duration near the maximum limit.

### Stage 3–4 — Preprocessing (optional, config-gated)

- `AudioNormalizer` — peak-normalizes to -3 dBFS using numpy + soundfile.
  Falls back to a no-op pass-through if either package is missing.
- `NoiseReducer` — wraps the optional `noisereduce` package. Disabled by
  default (`SpeechProcessingConfig.preprocessing.enable_noise_reduction`).
  `NoiseReducer.is_available` reports whether the package is installed before
  the pipeline attempts to use it.

Both write to a per-run temp directory that is cleaned up in a `finally`
block regardless of success or failure.

### Stage 5 — Transcription (`FasterWhisperEngine`)

- Model is **lazy-loaded**: `WhisperModel(...)` is constructed on the first
  `transcribe()` call, not at import time or pipeline construction. Importing
  `speech` does not download or load anything.
- Wrapped in `@retry(max_attempts=3, delay_seconds=1.0, backoff=2.0)` for
  transient failures (e.g., disk I/O hiccups during model load).
- Converts every `faster_whisper` segment into a `TranscriptSegment`
  dataclass. `confidence` is derived as `exp(clamp(avg_logprob, -10.0))` since
  Whisper's `avg_logprob` can be `-inf` for silent segments.

### Stage 6 — Postprocessing (`TranscriptCleaner`)

Returns a **new** `Transcript`; never mutates the input. Order of operations:

1. Drop hallucinated/artifact segments (`[INAUDIBLE]`, `[Music]`,
   punctuation-only segments, YouTube-style artifacts like "thanks for
   watching")
2. Strip filler words (`um`, `uh`, `like`, `you know`) — whole-word match only
   so "umbrella" survives
3. Apply construction-term normalization (`ConstructionNormalizer`):
   `re bar` -> `rebar`, `h v a c` -> `HVAC`, `p v c` -> `PVC`, etc. — purely
   textual corrections, zero domain knowledge (that lives in `knowledge/`)
4. Rebuild `full_text` from the cleaned segments and fix whitespace/punctuation

---

## Public API

```python
from speech import SpeechProcessingPipeline, SpeechProcessingConfig, WhisperConfig

# Default config: base model, CPU, int8
pipeline = SpeechProcessingPipeline()
result = pipeline.process("site_recording.wav")

if result.success:
    print(result.plain_text())
    print(f"Confidence: {result.confidence():.2%}")
    print(f"Language:   {result.language()}")
else:
    print(f"Failed: {result.errors}")

# Batch processing — same API, scales from 1 file to 100,000+
results = pipeline.process_batch(["a.wav", "b.wav", "c.wav"])

# Production config
config = SpeechProcessingConfig(
    whisper=WhisperConfig(model_size="large-v3", device="cuda", compute_type="float16"),
)
pipeline = SpeechProcessingPipeline(config=config)

# From environment variables
config = SpeechProcessingConfig.from_env()
```

### `SpeechProcessingResult` — what you get back

```python
result.success            # bool
result.audio_id           # str (UUID, auto-generated or caller-supplied)
result.transcript         # Transcript | None — text, segments, word timestamps
result.metadata           # SpeechProcessingMetadata — audio facts + processing stats
result.validation         # AudioValidationResult — what the validator found
result.errors             # list[str]
result.warnings           # list[str]

result.plain_text()       # convenience: full transcript text, "" on failure
result.confidence()       # convenience: avg segment confidence, 0.0 on failure
result.duration_seconds() # convenience: audio duration
result.language()         # convenience: detected/forced language code

result.to_dict()          # full structured dict, fully JSON-serializable
result.to_json(indent=2)  # JSON string
```

Failures are **never exceptions** for expected error conditions (bad file,
STT error) — they are `SpeechProcessingResult` objects with `success=False`
and `errors` populated. Callers check `result.success`, not try/except.

### Exporters

```python
from speech.exporters import JSONExporter, JSONLExporter, TextExporter, VerboseTextExporter

JSONExporter().export(result, "output/result.json")       # full structured JSON
JSONLExporter().export(result, "output/batch.jsonl")       # append-mode, one line per call
TextExporter().export(result, "output/transcript.txt")     # plain text, one line per segment
VerboseTextExporter().export(result, "output/report.txt")  # + timestamps, confidence, metadata header
```

---

## Configuration

All tunables live in `speech/config.py` as nested dataclasses — zero magic
numbers elsewhere in the framework.

```python
@dataclass
class SpeechProcessingConfig:
    validation: AudioValidationConfig
    whisper: WhisperConfig
    preprocessing: PreprocessingConfig
    postprocessing: PostprocessingConfig
    max_retries: int
    retry_delay_seconds: float
    retry_backoff: float
    progress_callback: Callable[[str, float], None] | None
```

`SpeechProcessingConfig.from_env()` reads:

| Variable | Default | Purpose |
|---|---|---|
| `SPEECH_WHISPER_MODEL_SIZE` | `base` | `tiny`\|`base`\|`small`\|`medium`\|`large-v3` |
| `SPEECH_WHISPER_DEVICE` | `cpu` | `cpu`\|`cuda`\|`auto` |
| `SPEECH_WHISPER_COMPUTE_TYPE` | `int8` | `int8`\|`float16`\|`float32` |
| `SPEECH_WHISPER_LANGUAGE` | auto-detect | Force a language code, e.g. `en` |
| `SPEECH_MAX_FILE_SIZE_MB` | `500` | Validation ceiling |
| `SPEECH_MAX_DURATION_SECONDS` | `7200` | Validation ceiling |
| `SPEECH_ENABLE_NOISE_REDUCTION` | `false` | Requires `noisereduce` installed |
| `SPEECH_MODELS_DIR` | `speech/.model_cache/` | Where Whisper models are downloaded |

The single biggest quality/speed knob is `whisper.model_size`:

| Model | Size | Notes |
|---|---|---|
| `tiny` | 75 MB | Dev/testing only |
| `base` | 150 MB | Development default |
| `small` | 250 MB | Good balance |
| `medium` | 1.5 GB | Recommended for production CPU |
| `large-v3` | 3 GB | Best accuracy, GPU recommended |

---

## CLI — `transcribe.py`

```bash
# Single file
python transcribe.py recording.wav

# Batch (all supported audio files in a directory)
python transcribe.py --batch data/sample_audio/ --output-dir data/transcripts/raw

# Validate only, no transcription
python transcribe.py recording.wav --dry-run

# Larger model, GPU
python transcribe.py recording.wav --model large-v3 --device cuda --compute-type float16

# Verbose text export with timestamps
python transcribe.py recording.wav --format verbose-text
```

---

## Testing

| File | Covers |
|---|---|
| `tests/conftest.py` | Synthetic WAV generation (sine tones via numpy+soundfile), shared fixtures |
| `tests/test_speech_models.py` | Dataclass construction, serialization round-trips |
| `tests/test_speech_config.py` | Default config, constructor overrides, `from_env()` |
| `tests/test_speech_validator.py` | All 8 blocking checks + 3 warnings, boundary cases |
| `tests/test_transcript_cleaner.py` | Filler removal, hallucination dropping, construction-term normalization |
| `tests/test_audio_pipeline.py` | Full pipeline integration via an injected `MockSTTEngine` — no GPU, no model download, no network required |

The integration tests inject a `MockSTTEngine` (a `BaseSTTEngine` subclass
returning canned transcripts) instead of `FasterWhisperEngine`, so the suite
runs in under a second with zero external dependencies. A separate
`TestRealSTTEngine` class is gated with
`@pytest.mark.skipif(not HAS_FASTER_WHISPER, ...)` for environments where the
real model is available.

Run the suite:

```bash
pip install -r requirements-dev.txt
pytest tests/test_speech_models.py tests/test_speech_config.py \
       tests/test_speech_validator.py tests/test_transcript_cleaner.py \
       tests/test_audio_pipeline.py -v
```

### Sample audio

`data/sample_audio/` contains 10 synthetic sine-tone WAV files generated by
`scripts/create_sample_audio.py`. They exercise validator boundary
conditions (duration limits, sample rate, channel count, chunk boundaries)
but contain no real speech — they cannot be used for transcription accuracy
(WER) testing. See `data/sample_audio/README.md` for how to add real
recordings for that purpose.

---

## What Sprint 3 deliberately does NOT do

- **No AI field extraction.** The framework produces text + metadata only.
  Turning that text into a `ConstructionDailyLog` is Sprint 4.
- **No database writes.** `SpeechProcessingResult` is exported to files
  (JSON/JSONL/text). Persistence is a future sprint's concern.
- **No real-time/streaming transcription.** The `BaseSTTEngine` interface is
  shaped to support it later (engine swap, no pipeline changes), but
  `FasterWhisperEngine.transcribe()` is currently a synchronous, file-based
  call.
- **No GPU requirement.** Default config runs on CPU with the `base` model
  and `int8` compute type. GPU is opt-in via config.
