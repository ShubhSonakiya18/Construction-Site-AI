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

Why logging.basicConfig() is called here (found while verifying Sprint 9's
email delivery):
    No module in app/ ever configured the root logger, so every
    logger.info()/logger.debug() call across the whole app package —
    "Queued pipeline for audio_file_id=...", "auth.forgot_password: reset
    token issued...", and Sprint 9's own
    "DevConsoleEmailSender: email NOT actually sent... to=... subject=..."
    — was silently dropped under `uvicorn app.main:app`, since Python's
    root logger defaults to WARNING and nothing ever lowered it. This
    predates Sprint 9 (confirmed: it affected Sprint 7/8's own INFO log
    lines too), but was only caught now because DevConsoleEmailSender's
    entire purpose — a developer reading the reset token from the server
    log instead of the HTTP response — depends on INFO actually reaching
    the console. `celery -A celery_app worker` was unaffected: Celery's
    own CLI configures logging via --loglevel, independent of this file.
"""
import logging

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from app.create_app import create_app  # noqa: E402 — must follow load_dotenv()

app = create_app()
