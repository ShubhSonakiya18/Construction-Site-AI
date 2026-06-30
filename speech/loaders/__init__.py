"""speech/loaders/ — Audio file loading and format detection."""
from speech.loaders.format_detector import detect_format, is_supported_format
from speech.loaders.audio_loader import AudioLoader

__all__ = ["detect_format", "is_supported_format", "AudioLoader"]
