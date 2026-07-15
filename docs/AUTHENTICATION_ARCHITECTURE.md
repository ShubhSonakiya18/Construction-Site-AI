# Authentication Architecture — Sprint 8

**Package:** `app/` (auth surface), `database/models/auth.py`, `database/models/password_reset.py`
**Status:** COMPLETE
**Prerequisites:** Sprints 1–7 (FROZEN), Sprint 8 Subsystems 1 & 5
**Companion doc:** `docs/AUTHORIZATION_ARCHITECTURE.md` (roles, permissions, tenant isolation)

This document explains how a user authenticates against the Construction Site AI backend: the token model, the session lifecycle, password management, and the account-lockout and rate-limiting defenses. It covers the design decisions and the *why* behind each — especially the ones that required a deliberate architectural choice.

---

## 1. Token Model — Two Different Mechanisms, Deliberately

The backend issues **two kinds of token** with fundamentally different properties:

| | Access token | Refresh token |
|---|---|---|
| Format | Signed JWT (HS256) | Opaque random string (32 bytes, base64url) |
| Contains claims? | Yes — `sub`, `company_id`, `role`, `email`, `exp` | No — it is just an unguessable secret |
| Verified how? | Signature check, **zero I/O** | Server-side lookup against `user_sessions` table |
| Lifetime | Short (default 60 min) | Long (default 30 days) |
| Revocable before expiry? | **No** | **Yes** — that's the whole point |
| Stored server-side? | No | Yes, as a **SHA-256 hash** (never the raw value) |

**Why two mechanisms rather than one:** an access token is fast to verify precisely because it carries no server-side state — the server just checks the signature. That speed is why it must be short-lived: there is no way to revoke a stateless token before it expires without maintaining a blacklist of every token ever issued, which defeats the purpose of statelessness. A refresh token is the opposite: it has no embedded meaning, its only property is being unguessable, and its validity comes entirely from a server-side lookup — which is exactly what makes it **revocable**. Logout, logout-all-devices, and "a password change invalidates every session" are all just `UPDATE user_sessions SET revoked_at = now()`.

See `app/core/security.py` for the primitives (`create_access_token`, `decode_access_token`, `generate_refresh_token`, `hash_refresh_token`).

### Why a database-backed session store, not stateless-JWT-only refresh tokens

This was an explicit design decision at the start of Subsystem 1. The spec required "Logout All Devices" and "Token Revocation" — both **impossible** with a pure stateless JWT refresh token, because there is no server-side record to delete. A JWT refresh token would need the exact same `user_sessions` table to be revocable, so making it a JWT would add signature-verification overhead for zero benefit. An opaque token + a server-side row is simpler and just as secure.

**Redis was considered and rejected for Sprint 8**: Redis is not introduced until a later sprint, and PostgreSQL is already the single datastore. A `user_sessions` table is consistent with how Sprint 8 handles all new persistent state (also `password_reset_tokens`, also the account-lockout columns).

---

## 2. The `user_sessions` Table

One row per issued refresh token — i.e. **one row per logged-in device/session**. See `database/models/auth.py`.

| Column | Purpose |
|---|---|
| `refresh_token_hash` | SHA-256 hex digest of the raw token. The raw token is never stored. |
| `user_id` | Whose session this is (FK to `users`, `ON DELETE CASCADE`). |
| `issued_at` / `expires_at` | When issued; absolute expiry (cannot refresh past this even if never revoked). |
| `last_used_at` | Timestamp of the most recent successful refresh using this token. |
| `revoked_at` / `revoke_reason` | NULL = active. Non-null = dead, regardless of `expires_at`. Reasons: `logout`, `logout_all`, `rotated`, `password_changed`, `admin_revoked`, `user_deactivated`. |
| `device_name` / `user_agent` / `ip_address` | Session-list context for a future "your devices" UI. |

**Why a hash, never the raw token:** this table is a credential store, same threat model as the password column. If the database were exfiltrated, a raw refresh token would be a live Bearer credential an attacker could use immediately; a SHA-256 hash is not (the raw token cannot be recovered from it). Unlike a password, a refresh token is already high-entropy random data, so a fast hash (SHA-256, not bcrypt) is correct — bcrypt's deliberate slowness defends against low-entropy human input, which isn't the threat here.

---

## 3. Session Lifecycle

```
POST /auth/login
    verify email + password
    → create user_sessions row (status: active)
    → return { access_token, refresh_token, session_id }

POST /auth/refresh  (with the refresh token)
    look up session by token hash
    → if active: REVOKE it (reason="rotated"), create a NEW row, return a new pair
    → if revoked/expired/unknown: 401  (see "Token Rotation" below)

POST /auth/logout  (with the refresh token)
    → revoke just that one session (reason="logout")

POST /auth/logout-all  (authenticated)
    → revoke every active session for the user (reason="logout_all")

password change / reset / user deactivation
    → revoke every active session for the user
      (reason="password_changed" / "user_deactivated")
```

### Token Rotation

Every successful `POST /auth/refresh` **revokes the token it was given** and issues a brand-new one. The submitted token can never be used a second time.

**Why:** rotation limits the damage window of a stolen refresh token to a single use. If an attacker steals a refresh token and uses it, the legitimate user's next refresh fails (their token was rotated away) — a detectable signal. And if the legitimate user refreshes first, the attacker's stolen copy is already dead.

**Reuse detection:** when a *revoked* token is presented again (via `POST /auth/refresh`), the backend logs `auth.invalid_refresh_token` with a warning — this is either an expired session being retried or a stolen token being replayed after the legitimate rotation. Either way the response is a uniform 401 that never distinguishes the cases (see §6).

### Retention

`user_sessions` rows are never deleted by normal operation — revoked rows stay for audit/session-history value. A future Sprint 10+ housekeeping job may hard-delete rows far past their `expires_at` purely for table size; that is a housekeeping concern, not a business-state change.

---

## 4. Password Management

### Change password (`POST /auth/change-password`, authenticated)
Requires the current password. On success: sets the new hash **and revokes every active session** (the client must log in again everywhere). A password change, however it happens, invalidates every existing login.

### Forgot / reset password

Sprint 8 builds the **token flow and lifecycle**, deliberately **not** an email provider (per explicit scope: "do not implement email provider yet").

```
POST /auth/forgot-password  { email }
    → ALWAYS returns the same generic message, whether or not the email exists
    → if the email is a real active account:
        - revoke any still-outstanding prior reset token for that user
        - create a password_reset_tokens row (hash-only, short-lived, single-use)
        - in development/testing ONLY: return the raw token in response metadata
          (the placeholder for the future email step)
    → in production: raw token is NEVER returned

POST /auth/reset-password  { reset_token, new_password }
    → verify the token: not used, not revoked, not expired
    → set the new password, mark the token used (single-use)
    → clear any account lockout, revoke every active session
```

The `password_reset_tokens` table (`database/models/password_reset.py`) stores `token_hash`, `expires_at` (default 30 min), `used_at`, `revoked_at`, plus `requested_ip` / `requested_user_agent` / `request_id` for audit.

**Why a dedicated table, not a JWT reset token:** a JWT reset token needs no migration, but it can't be made single-use or explicitly revocable (e.g. a second forgot-password request superseding an intercepted first one) without a second table tracking consumed tokens — at which point the table exists anyway, just with extra signature overhead. A dedicated table gets single-use (`used_at`) and revocability (`revoked_at`) for free.

**Why separate from `user_sessions`:** the two have different lifecycles (a refresh token is used repeatedly via rotation; a reset token is used exactly once then permanently dead) and different lifetimes (30 days vs 30 minutes). One polymorphic table would need a type discriminator on every query and nullable columns for every non-shared field.

---

## 5. Account Lockout & Rate Limiting

### Account lockout (per-account)

Stored as columns on `User` (`failed_login_attempts`, `locked_until`, `last_failed_login_at` — migration `003`). Fully configurable via `Settings`:

- **5** consecutive failed logins (`lockout_max_failed_attempts`) → account locked for **15 minutes** (`lockout_duration_minutes`).
- A **successful login** resets the counter to 0.
- A **password reset** clears the lockout.
- **Admin unlock** (`POST /users/{id}/unlock`, requires `user:unlock` permission) clears it immediately.
- **Automatic unlock** after `locked_until` passes — no job needed, it's checked on the next login attempt.

A locked account returns **423 Locked** even when the correct password is supplied — the password isn't re-verified while locked.

**Why columns on `User`, not a separate table:** the lockout counter's lifecycle is 1:1 with one User row (reset on success, incremented on failure). Unlike `user_sessions` (genuinely one-to-many per user), there is nothing to normalize out.

**Lockout does not apply to a nonexistent email** — there is no `User` row to record a failure against, and recording one would itself be an enumeration side channel (an attacker could infer "this email exists" from whether a lockout counter moves).

### Rate limiting (coarser, per-key)

A `RateLimiter` protocol (`app/core/rate_limit.py`) with an in-memory sliding-window implementation (`MemoryRateLimiter`), applied to:
- `POST /auth/login` — default 10 attempts / 5 min per email.
- `POST /auth/forgot-password` — default 3 attempts / 1 hour per email.

All limits configurable via `Settings`. Rate limiting is a coarse backstop **layered above** per-account lockout — it catches e.g. a burst against many different emails that no single account's lockout would see.

**Why in-memory for Sprint 8, and its documented limits** (explicit decision, see also `docs/DECISIONS.md`): zero new infrastructure, no migration. Real limitation: state is **per-process** — a multi-worker deployment has N independent counters, and a restart clears them. Accepted at this project's documented target scale (hundreds of companies, single-process dev/staging). The `RateLimiter` protocol exists specifically so a future `RedisRateLimiter` (Redis sorted-set: `ZADD`/`ZREMRANGEBYSCORE`/`ZCARD`) replaces `MemoryRateLimiter` with **zero changes to any router or service** — only the constructed instance changes.

---

## 6. Uniform Failure Responses (Account-Enumeration Prevention)

Every authentication failure returns a response that does **not** reveal which specific thing went wrong:

- **Login**: wrong password, nonexistent email, and inactive account all return the identical `401 "Incorrect email or password."`
- **Token auth** (`get_current_user`): missing / malformed / expired / bad-signature token, and a valid token whose subject no longer resolves to an active user, all return the identical `401 "Invalid or expired token."`
- **Forgot-password**: identical generic message whether or not the email exists.
- **Refresh**: unknown / revoked / expired token all return the identical `401`.

**Why:** telling an attacker which case occurred is free reconnaissance (account enumeration). Only server-side logs (and the audit trail — see §7) distinguish the cases for legitimate debugging.

This is why the `401` vs `423` (locked) distinction is the one deliberate exception — a locked account is a state the legitimate user needs to understand ("try again later"), and by the time an account is locked the attacker already knows the email is valid (they triggered the lockout).

---

## 7. Audit Trail (Subsystem 6)

Every authentication event writes a first-class `AuditLog` row (see `docs/AUTHORIZATION_ARCHITECTURE.md` §5 for the audit schema). Auth events include: `user.login`, `user.login_failed`, `user.locked`, `user.unlocked`, `user.logout`, `user.logout_all`, `auth.refresh_token_issued`, `auth.refresh_token_revoked`, `auth.invalid_refresh_token`, `user.password_changed`, `user.password_change_failed`, `user.password_reset_requested`, `user.password_reset_completed`, plus the security events `security.unauthorized_access` and `security.rate_limit_triggered`.

Audit writes are **fail-open** (`app/services/audit_helpers.py:safe_log_event`) — a logging failure never blocks the underlying operation. Two subtleties, both learned by real bugs found in testing:
1. `safe_log_event` **commits immediately** on success, because several audit events are logged right before the request intentionally raises an `HTTPException` (e.g. `security.unauthorized_access` before a 401), and the request-scoped session rolls back on any exception — which would otherwise discard the just-written audit row.
2. The forgot-password event is logged **only** for a real, active user — logging on the nonexistent-email path would reintroduce the enumeration side channel §6 prevents.

---

## 8. Endpoint Summary

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/auth/login` | none | Verify credentials → access + refresh token |
| POST | `/auth/refresh` | refresh token | Rotate: revoke old, issue new pair |
| POST | `/auth/logout` | refresh token | Revoke one session |
| POST | `/auth/logout-all` | access token | Revoke all sessions |
| POST | `/auth/change-password` | access token | Change password, revoke all sessions |
| POST | `/auth/forgot-password` | none | Request a reset token (generic response) |
| POST | `/auth/reset-password` | reset token | Consume token, set password, revoke sessions |
| GET | `/auth/me` | access token | Current authenticated user |
| POST | `/users/{id}/unlock` | `user:unlock` | Admin: clear an account lockout |

---

## 9. Backward Compatibility

Every change in this subsystem is **additive**:
- `POST /auth/login`'s request/response contract is unchanged except for **new** response fields (`refresh_token`, `refresh_token_expires_in_days`, `session_id`) — a Sprint 7 client that ignores unknown fields still works.
- New tables (`user_sessions`, `password_reset_tokens`) and new columns (`User` lockout fields, `AuditLog` structured fields) are additive migrations; no existing table was modified destructively.
- No Sprint 1–7 code path was changed behaviorally except the verified-bug fixes documented in `docs/DECISIONS.md`.
