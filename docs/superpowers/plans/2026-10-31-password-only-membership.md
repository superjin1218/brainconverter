# Password-only Membership Implementation Plan

> Execution: implement inline in this session, as requested; deploy after tests.

> 2026-10-31 SQL revision: user now requires reporting the corrected migration BEFORE any execution. Do not run the migration, the historical reset migration, or redeploy as part of this revision. Previous execution authorization does not apply to these actions.

**Goal:** Public email/password signup without email verification, with pending/member defaults and approved-only conversion.

**Architecture:** Supabase continues password authentication; FastAPI keeps HttpOnly sessions and checks database-owned approval. A new, rerunnable SQL migration replaces approval/admission/budget functions without running historical accounting resets or changing existing rows. Legacy email links only clear URL credentials.

**Tech Stack:** FastAPI, static HTML/JavaScript, Supabase Auth/PostgreSQL, systemd.

- [x] Modify `backend/app/membership.py`: require passwords of 6–256 characters for signup/login, remove confirmed-email authorization, send only display name to signup, check autoconfirm before signup to avoid sending mail with stale dashboard settings, retire confirmation endpoint.
- [x] Modify `backend/app/static/index.html`, `js/membership.js`, `js/auth-callback.js`: consistent password validation and signup/login copy; retain URL credential cleanup; allow approval without email verification; show administrators that email/name do not establish identity.
- [x] Add `supabase/migrations/202610310001_password_only_membership.sql`: replace `brain_set_member_status`, `brain_reserve`, `brain_budget_reserve`; retain status/role checks, concurrency, quotas, accounting and function grants. Add service-only read-only policy readiness RPC.
- [x] Modify `supabase/bootstrap_operator.sql`: require an explicitly selected immutable user UUID; never grant administrator based on a claimed email address.
- [x] Update `backend/tests/test_membership.py`, `frontend_state.test.mjs`, `auth_callback.test.mjs`, `test_membership_sql.py`: short-password rejection, simple six-character passwords, unconfirmed approved users, pending/admin denials, signup-to-approval-to-mock-conversion, safe legacy links, SQL rerun/data preservation.
- [x] Run `.venv/bin/pytest -q`, `node --test backend/tests/*.test.mjs`, `.venv/bin/ruff check backend scripts/check_production_config.py scripts/verify_production.py`. Run actual SQL tests against disposable PostgreSQL; no production reservations or AI calls.
- [x] Update `README.md`, `docs/UBUNTU_OPERATIONS.md`, `scripts/verify_production.py`: new dashboard policy, SMTP independence, impersonation risk, DB migration and verification instructions.
- [ ] Apply only the new migration when DB credentials are available; otherwise provide the exact SQL Editor file and clearly report pending remote work. User changes Confirm email OFF, minimum length 6, password character requirements empty, Custom SMTP OFF.
- [ ] Restart `brainconverter.service`, verify service/loopback/public responses and policy readiness without invoking paid OpenAI. Record verified outcomes and external prerequisites in `docs/PASSWORD_ONLY_DEPLOYMENT_REPORT.md`.

## Execution result

Code, SQL migration, docs, 548 Python/SQL tests, 49 JS tests and 10 browser checks completed. Production readiness failed as expected: Confirm email still ON; new SQL absent. Restart after tests timed out in Ubuntu Polkit; existing Python PID 10057 remains active. Dashboard/SQL and OS authentication require user action; see `docs/PASSWORD_ONLY_DEPLOYMENT_REPORT.md`. No paid OpenAI calls or production account/data changes were made.
