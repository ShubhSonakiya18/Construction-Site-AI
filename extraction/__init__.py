"""
extraction/ — Provider-agnostic AI Information Extraction Framework.

Public API:
    from extraction import ExtractionPipeline, ExtractionConfig, ExtractionResult

The only file that imports a provider-specific library is the engine file for
that provider (e.g. extraction/engines/groq_engine.py). Business logic, tests,
and callers always talk to BaseLLMProvider via EngineFactory.
"""
from extraction.pipeline import ExtractionPipeline
from extraction.config import ExtractionConfig, GroqConfig
from extraction.models.extraction_result import ExtractionResult

__all__ = ["ExtractionPipeline", "ExtractionConfig", "GroqConfig", "ExtractionResult"]
__version__ = "1.0.0"
