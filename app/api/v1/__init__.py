"""app/api/v1/ — Version 1 of the REST API.

Every router in this package is mounted under /api/v1 in create_app.py.
A future /api/v2 would be a sibling package (app/api/v2/) with its own
routers — v1 routers, schemas, and business logic are never modified to
support v2; a v2 concern gets a v2 file. See docs/BACKEND_ARCHITECTURE.md
"API Versioning Strategy".
"""
