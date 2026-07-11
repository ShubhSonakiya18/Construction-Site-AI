"""app/api/ — HTTP-facing routers and their dependencies.

dependencies.py holds every FastAPI Depends() callable shared across
routers (DB session, current user, repository factories). Routers in
app/api/v1/ never construct a Session or a repository directly — they
receive both through Depends().
"""
