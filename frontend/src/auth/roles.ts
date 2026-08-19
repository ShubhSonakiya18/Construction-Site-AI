// Mirrors the relevant slice of app/core/permissions.py's ROLE_PERMISSIONS
// (Sprint 8) for the specific actions this frontend conditionally shows —
// NOT a full reimplementation of the backend's permission system. The
// backend's require_permission() is the real authorization boundary
// regardless of what this file says; hiding a button a role's request
// would 403 on is a UX nicety (Sprint 10, Deliverable 7's client-portal
// verification — "the same app with fewer buttons" decision), the same
// posture LogReviewPage.tsx's REVIEWER_ROLES already established for
// Approve/Reject.
//
// Kept as three named sets (not a full role->permission map) because
// that's the exact and only shape the frontend currently needs — see
// docs/DECISIONS.md if this needs to grow into something more general
// later; three roles is not yet enough duplication to justify a bigger
// abstraction.

// Permission.DAILY_LOG_APPROVE / DAILY_LOG_REJECT
export const REVIEWER_ROLES = new Set(['owner', 'admin', 'project_manager', 'system_admin'])

// Permission.DAILY_LOG_GENERATE
export const GENERATE_ROLES = new Set(['owner', 'admin', 'project_manager', 'system_admin'])

// Permission.DAILY_LOG_SEND_OUTPUT
export const SEND_OUTPUT_ROLES = new Set(['owner', 'admin', 'project_manager', 'system_admin'])

// Permission.AUDIO_UPLOAD — foreman has this (uploads their own
// recordings) even though foreman lacks GENERATE/SEND_OUTPUT/REVIEWER.
export const AUDIO_UPLOAD_ROLES = new Set([
  'owner',
  'admin',
  'project_manager',
  'foreman',
  'system_admin',
])
