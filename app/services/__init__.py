"""app/services/ — Business logic orchestration layer.

Routers (app/api/v1/*.py) never call speech/, extraction/, generation/, or
database/repositories/ directly for multi-step operations — they call a
function here. A service function's job is to sequence repository calls
and Sprint 1-6 pipeline calls; it never touches a Request/Response object
or raises HTTPException (that translation happens in the router).

Not every router needs a service — app/api/v1/auth.py's login is a single
repository lookup + one password check + one token encode, simple enough
to live directly in the route (see its module docstring for the
reasoning). Services exist where there is real multi-step orchestration:
pipeline_service.py chains 4 separate Sprint 1-6 subsystems.
"""
