"""
app/services/worker_matching.py — Sprint 15: match free-text incident names
to real Worker records for OSHA reporting.

ADR-061: exact match only, never WorkerRepository.find_by_name()'s
substring search. That method is a reasonable fit for an admin-facing
search box (a human picks the right result from a list), but wrong for
this use case: the result here is written unattended to
LogSafetyIncident.worker_id and can end up on a government compliance
form. A substring match ("Mike" matching both "Mike Johnson" and
"Michael Rodriguez") would need a human to disambiguate anyway, so
there's no reliability gained over leaving it unmatched — and a wrong
automatic match is worse than an honest "needs review" for a document a
company could be legally liable for getting wrong.

Session-bound (not session-free like schedule_service.py/cost_service.py):
this needs a live query against Worker records, unlike those two modules'
pure arithmetic over already-fetched values.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from database.repositories.worker import WorkerRepository


@dataclass
class WorkerMatchResult:
    worker_id: Optional[UUID]
    status: str  # matched | no_match | needs_review


def match_worker_by_name(
    worker_repo: WorkerRepository, *, company_id: UUID, name: Optional[str]
) -> WorkerMatchResult:
    """Attempt to resolve a free-text name (e.g. LogSafetyIncident.worker_involved)
    to a real Worker record, exact match only.

    status:
        matched       -- exactly one active worker's full_name matches
                         `name` case-insensitively (ignoring surrounding
                         whitespace). worker_id is set.
        needs_review  -- more than one active worker shares that exact
                         name (a real possibility with common names), or
                         `name` matched a worker's first/last name via
                         find_by_name()'s substring search but not their
                         full name exactly -- ambiguous, a human must
                         pick. worker_id is None.
        no_match      -- no active worker in the company matches at all,
                         or `name` was None/blank to begin with.
                         worker_id is None.
    """
    if not name or not name.strip():
        return WorkerMatchResult(worker_id=None, status="no_match")

    normalized_input = name.strip()
    normalized = normalized_input.casefold()

    # find_by_name() checks its search term as a substring of first_name
    # OR last_name separately -- passing a full "First Last" string
    # through unchanged matches nothing, since neither name field alone
    # contains the two-word substring. Search on the last whitespace-
    # separated token (typically the surname) to get real candidates,
    # then narrow to an exact full-name match below; the substring
    # search is only ever used to build a candidate pool, never trusted
    # as the match itself.
    search_token = normalized_input.split()[-1]
    candidates = worker_repo.find_by_name(company_id, search_token)
    exact_matches = [w for w in candidates if w.full_name.casefold() == normalized]

    if len(exact_matches) == 1:
        return WorkerMatchResult(worker_id=exact_matches[0].id, status="matched")
    if len(exact_matches) > 1:
        # Two active workers with the identical full name -- a real
        # possibility, and exactly the case an automatic match must not
        # silently resolve on its own.
        return WorkerMatchResult(worker_id=None, status="needs_review")
    if candidates:
        # find_by_name() matched on a first/last-name substring but not
        # the full name exactly (e.g. "Miguel" alone, or a mis-transcribed
        # partial name) -- there's a plausible worker, but not a
        # confident-enough match to write unattended onto an OSHA record.
        return WorkerMatchResult(worker_id=None, status="needs_review")

    return WorkerMatchResult(worker_id=None, status="no_match")
