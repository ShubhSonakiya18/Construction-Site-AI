"""app/schemas/ — Pydantic request/response models for the HTTP API.

Deliberately separate from database/models/ (SQLAlchemy ORM classes):
    ORM models describe how data is stored (columns, FKs, mixins).
    Schemas describe what a client sends/receives over HTTP — a narrower,
    stable, versioned contract. Coupling them would mean any internal
    column rename (e.g. adding an index, splitting a JSON blob into a
    child table) breaks the public API contract. Sprint 7 keeps these two
    concerns separate from day one, matching FastAPI's own convention.

envelope.py defines the response shape every endpoint returns; the other
modules define the `data` payload shape for each resource.
"""
