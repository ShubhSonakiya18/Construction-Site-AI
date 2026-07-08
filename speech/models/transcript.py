"""
speech/models/transcript.py — Structured transcript returned by any STT engine.

Design intent: the STT engine (Faster Whisper today, anything else tomorrow) fills
these dataclasses. The rest of the pipeline — postprocessors, exporters, the
ConstructionDailyLog injector in Sprint 4 — consumes ONLY these types. No
downstream module ever imports faster_whisper directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WordTimestamp:
    """A single word with start/end time and per-word probability."""
    word: str
    start: float          # seconds from beginning of audio
    end: float            # seconds from beginning of audio
    probability: float    # 0.0–1.0; from STT engine confidence

    def to_dict(self) -> dict:
        return {
            "word": self.word,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "probability": round(self.probability, 4),
        }


@dataclass
class TranscriptSegment:
    """
    One continuous speech segment as returned by the STT engine.

    Segments map to natural pauses in speech. A 30-second recording typically
    produces 5–15 segments. The final transcript is the concatenation of all
    segment texts.
    """
    id: int
    text: str
    start: float                        # seconds
    end: float                          # seconds
    avg_logprob: float                  # log probability from beam search
    no_speech_prob: float               # probability this segment is silence
    confidence: float                   # derived: exp(avg_logprob) clamped 0–1
    words: list[WordTimestamp] = field(default_factory=list)

    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text.strip(),
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "duration": round(self.duration(), 3),
            "avg_logprob": round(self.avg_logprob, 4),
            "no_speech_prob": round(self.no_speech_prob, 4),
            "confidence": round(self.confidence, 4),
            "words": [w.to_dict() for w in self.words],
        }


@dataclass
class Transcript:
    """
    Complete structured output from the STT engine for one audio file.

    The canonical text field is the cleaned, concatenated transcript. Individual
    segments carry timestamps so Sprint 4 can ground extracted fields to specific
    moments in the recording.
    """
    text: str                           # full transcript, segments joined
    language: str                       # ISO 639-1 code, e.g. "en"
    language_probability: float         # 0.0–1.0, how confident the engine is
    duration_seconds: float             # total audio duration in seconds
    segments: list[TranscriptSegment] = field(default_factory=list)

    def word_count(self) -> int:
        return len(self.text.split()) if self.text.strip() else 0

    def avg_confidence(self) -> float:
        if not self.segments:
            return 0.0
        return sum(s.confidence for s in self.segments) / len(self.segments)

    def segment_count(self) -> int:
        return len(self.segments)

    def is_empty(self) -> bool:
        return not self.text.strip()

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "language": self.language,
            "language_probability": round(self.language_probability, 4),
            "duration_seconds": round(self.duration_seconds, 3),
            "word_count": self.word_count(),
            "segment_count": self.segment_count(),
            "avg_confidence": round(self.avg_confidence(), 4),
            "segments": [s.to_dict() for s in self.segments],
        }
