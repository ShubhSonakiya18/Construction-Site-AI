"""
speech/utils/constants.py — Framework-wide constants.

All values here are audio processing constraints, not construction domain knowledge.
Construction domain knowledge lives exclusively in knowledge/*.json.
"""

FRAMEWORK_VERSION = "1.0.0"

# ── Supported audio formats ────────────────────────────────────────────────────
# Faster Whisper uses ffmpeg internally, so in practice it handles many more
# formats. This set defines what the AudioValidator will accept.
SUPPORTED_AUDIO_FORMATS: frozenset[str] = frozenset(
    {"wav", "mp3", "m4a", "flac", "ogg", "aac", "webm", "opus"}
)

# MIME types for each supported format (for HTTP upload validation in Sprint 7)
FORMAT_TO_MIME: dict[str, str] = {
    "wav":  "audio/wav",
    "mp3":  "audio/mpeg",
    "m4a":  "audio/mp4",
    "flac": "audio/flac",
    "ogg":  "audio/ogg",
    "aac":  "audio/aac",
    "webm": "audio/webm",
    "opus": "audio/opus",
}

# ── File size limits ───────────────────────────────────────────────────────────
MAX_FILE_SIZE_MB: float = 500.0   # realistic upper bound for voice recordings
MIN_FILE_SIZE_BYTES: int = 1024   # files smaller than 1 KB are probably corrupt

# ── Duration limits ────────────────────────────────────────────────────────────
MIN_DURATION_SECONDS: float = 0.5    # below 0.5s: no meaningful speech
MAX_DURATION_SECONDS: float = 7200.0 # 2 hours; longer files should be split upstream

# ── Audio quality thresholds ──────────────────────────────────────────────────
MIN_SAMPLE_RATE: int = 8_000         # telephone-quality minimum
RECOMMENDED_SAMPLE_RATE: int = 16_000  # Whisper's native sample rate
MAX_CHANNELS: int = 8                  # mono/stereo/surround; beyond this is unusual

# ── Silence detection ─────────────────────────────────────────────────────────
SILENCE_THRESHOLD_DB: float = -50.0   # dBFS below which a frame counts as silence
MAX_SILENCE_RATIO: float = 0.95       # files >95% silent are rejected

# ── STT engine defaults ───────────────────────────────────────────────────────
DEFAULT_WHISPER_MODEL: str = "base"      # usable without GPU; medium for production
DEFAULT_DEVICE: str = "cpu"
DEFAULT_COMPUTE_TYPE: str = "int8"
DEFAULT_LANGUAGE: str | None = None      # None = auto-detect
DEFAULT_BEAM_SIZE: int = 5
DEFAULT_TASK: str = "transcribe"         # "transcribe" or "translate"

# ── Chunking ───────────────────────────────────────────────────────────────────
DEFAULT_CHUNK_LENGTH_SECONDS: float = 30.0
DEFAULT_CHUNK_OVERLAP_SECONDS: float = 1.0

# ── Confidence thresholds ─────────────────────────────────────────────────────
MIN_SEGMENT_CONFIDENCE: float = 0.0    # segments below this get flagged
LOW_CONFIDENCE_WARNING: float = 0.5    # overall result: add warning below this

# ── Retry policy ─────────────────────────────────────────────────────────────
DEFAULT_MAX_RETRIES: int = 3
DEFAULT_RETRY_DELAY_SECONDS: float = 1.0
DEFAULT_RETRY_BACKOFF: float = 2.0     # exponential multiplier

# ── Post-processing ───────────────────────────────────────────────────────────
# Filler words removed by TranscriptCleaner
FILLER_WORDS: frozenset[str] = frozenset(
    {"um", "uh", "hmm", "like", "you know", "so", "basically", "actually"}
)

# Construction term normalization: spoken form -> canonical form.
# Only output-display corrections — no construction domain logic.
CONSTRUCTION_TERM_CORRECTIONS: dict[str, str] = {
    # Rebar variants
    "re bar": "rebar",
    "re-bar": "rebar",
    # Lumber/panel products
    "o s b": "OSB",
    "osb board": "OSB sheathing",
    "l v l": "LVL",
    "l v p": "LVP",
    # Piping
    "p v c": "PVC",
    "p e x": "PEX",
    # HVAC
    "h v a c": "HVAC",
    # Electrical
    "a f c i": "AFCI",
    "g f c i": "GFCI",
    "n m cable": "NM cable",
    "n e c": "NEC",
    # Standards
    "o s h a": "OSHA",
    "i r c": "IRC",
    "n f p a": "NFPA",
    # Measurements
    "four by eight": "4x8",
    "two by four": "2x4",
    "two by six": "2x6",
    "two by ten": "2x10",
}
