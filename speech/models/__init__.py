"""
speech/models/ — Data classes that form the contract between every pipeline stage.

Nothing in this package has side effects. No I/O. No framework dependencies.
Every class is serializable to a plain dict so that exporters can convert to
any output format without knowing internal structure.
"""
from speech.models.transcript import WordTimestamp, TranscriptSegment, Transcript
from speech.models.metadata import AudioFileInfo, ProcessingStats, SpeechProcessingMetadata
from speech.models.processing_result import AudioValidationResult, SpeechProcessingResult

__all__ = [
    "WordTimestamp",
    "TranscriptSegment",
    "Transcript",
    "AudioFileInfo",
    "ProcessingStats",
    "SpeechProcessingMetadata",
    "AudioValidationResult",
    "SpeechProcessingResult",
]
