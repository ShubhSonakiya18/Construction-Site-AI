"""speech/whisper/ — STT engine abstraction layer."""
from speech.whisper.engine import BaseSTTEngine, FasterWhisperEngine

__all__ = ["BaseSTTEngine", "FasterWhisperEngine"]
