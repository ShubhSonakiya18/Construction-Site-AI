"""
app/main.py — ASGI entry point.

Run with:
    uvicorn app.main:app --reload          (development)
    uvicorn app.main:app --host 0.0.0.0 --port 8000  (no reload, closer to prod)

See docs/BACKEND_STARTUP.md for the full startup sequence (PostgreSQL,
Alembic migration, seed scripts, dev admin bootstrap) before running this.

Why load_dotenv() is called here, explicitly, before anything else:
    Every Sprint 1-6 CLI entry point (transcribe.py, extract.py,
    verify_sprint6.py) hand-rolls its own _load_env() that reads .env into
    os.environ before importing any *Config.from_env() class — because
    DatabaseConfig, ExtractionConfig, GenerationConfig, and
    SpeechProcessingConfig all read os.environ directly and have no
    built-in .env file support. app/core/config.py's Settings DOES parse
    .env on its own (via pydantic-settings' env_file=".env"), but that only
    populates the Settings object's own fields — it does NOT also populate
    os.environ, so the other four *Config classes still see nothing when
    launched via `uvicorn app.main:app` with no .env already exported by
    the shell. python-dotenv's load_dotenv() (already an indirect
    dependency via pydantic-settings) populates os.environ itself, which
    every from_env() classmethod in this codebase already knows how to
    read. This one line is what makes `uvicorn app.main:app` work from a
    fresh shell exactly like `python extract.py` already does.
"""
from dotenv import load_dotenv

load_dotenv()

from app.create_app import create_app  # noqa: E402 — must follow load_dotenv()

app = create_app()
