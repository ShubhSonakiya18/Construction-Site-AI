"""
app/ — Sprint 7 FastAPI backend.

Public API:
    from app.create_app import create_app
    app = create_app()

This package is the single HTTP entry point for the platform. Every future
frontend, mobile client, dashboard, or external integration talks to this
backend — never directly to speech/, extraction/, generation/, or database/.

Sprint 1-6 packages (knowledge/, speech/, extraction/, generation/,
database/) are FROZEN and imported from, never modified, by this package.
"""
