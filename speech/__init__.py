"""
speech/ — Speech Processing Framework for Construction Site AI.

Public API
----------
The only imports your business logic needs:

    from speech import SpeechProcessingPipeline
    from speech import SpeechProcessingConfig, WhisperConfig
    from speech import SpeechProcessingResult

Everything else (engines, validators, preprocessors, exporters) is an
implementation detail. Import from submodules only when extending the framework.

Usage
-----
    # Default: base model, CPU, int8
    pipeline = SpeechProcessingPipeline()
    result = pipeline.process("site_recording.wav")

    if result.success:
        print(result.plain_text())
        print(f"Duration: {result.duration_seconds():.1f}s")
        print(f"Language: {result.language()}")
        print(f"Confidence: {result.confidence():.2%}")

    # Batch
    results = pipeline.process_batch(["a.wav", "b.wav", "c.wav"])

    # Production config
    from speech import WhisperConfig
    config = SpeechProcessingConfig(
        whisper=WhisperConfig(model_size="large-v3", device="cuda"),
    )
    pipeline = SpeechProcessingPipeline(config=config)

    # From environment variables
    config = SpeechProcessingConfig.from_env()

    # Export result
    from speech.exporters import JSONExporter, TextExporter
    JSONExporter().export(result, "output/result.json")
    TextExporter().export(result, "output/transcript.txt")
"""
from speech.config import (
    AudioValidationConfig,
    PostprocessingConfig,
    PreprocessingConfig,
    SpeechProcessingConfig,
    WhisperConfig,
)
from speech.models.metadata import AudioFileInfo, ProcessingStats, SpeechProcessingMetadata
from speech.models.processing_result import AudioValidationResult, SpeechProcessingResult
from speech.models.transcript import Transcript, TranscriptSegment, WordTimestamp
from speech.pipeline import SpeechProcessingPipeline

__version__ = "1.0.0"

__all__ = [
    # Pipeline — the primary entry point
    "SpeechProcessingPipeline",
    # Config
    "SpeechProcessingConfig",
    "WhisperConfig",
    "AudioValidationConfig",
    "PreprocessingConfig",
    "PostprocessingConfig",
    # Result types
    "SpeechProcessingResult",
    "AudioValidationResult",
    # Transcript types
    "Transcript",
    "TranscriptSegment",
    "WordTimestamp",
    # Metadata types
    "SpeechProcessingMetadata",
    "AudioFileInfo",
    "ProcessingStats",
    # Version
    "__version__",
]
