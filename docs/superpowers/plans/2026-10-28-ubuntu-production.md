# Ubuntu Production Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve Brain Converter over the existing Cloudflare Tunnel with Supabase signup, confirmed-email login, and database-owned approval, preserving all existing data.

**Architecture:** FastAPI serves the static site and proxies Supabase Auth/RPC calls. Email confirmation returns to a dedicated callback that removes URL credentials and verifies the confirmed identity, then asks for password login; only password login/refresh writes HttpOnly cookies. One Uvicorn worker binds to 127.0.0.1:3000 under systemd. AI conversion stays explicitly disabled.

**Tech Stack:** Python 3.12, FastAPI, HTTPX, Uvicorn, static JavaScript, Supabase Auth/PostgREST, systemd, existing cloudflared.

---

### Task 1: Authentication callback and production controls

Files: `backend/app/config.py`, `main.py`, `membership.py`, `conversion.py`, `static/js/auth-callback.js`, `static/js/membership.js`, `static/js/provider.js`, `static/index.html`.

- [x] Add `CONVERSIONS_ENABLED=false` support; require identity/approval before reporting AI unavailability, and stop before provider initialization, reservations, or budget writes.
- [x] Route signup redirects to `/auth/callback`; serve the existing page there without caching.
- [x] Clear Supabase fragments synchronously, validate the confirmation access token through `/auth/v1/user`, and require password login. Never import URL credentials into session cookies or local storage.
- [x] Retain Secure/HttpOnly/SameSite=Lax cookies and exact Origin/custom-header checks. Add production host validation, HSTS, and restrictive document directives.
- [x] Test callback errors, forged/unconfirmed tokens, no cookie writes on confirmation, disabled conversion, and production response headers.

Validation: `.venv/bin/pytest -q` and `node --test backend/tests/frontend_state.test.mjs backend/tests/auth_callback.test.mjs`. All remote authentication/AI responses in automated tests must be mocked. Do not enable SQL integration tests.

### Task 2: Reviewable Ubuntu service

Files: `deploy/brainconverter.service`, `deploy/install-systemd.sh`, `.env.local` (ignored), `docs/UBUNTU_OPERATIONS.md`.

- [x] Reuse the Python 3.12 virtualenv, install declared dependencies and test tooling, and record the deployed versions.
- [x] Set production/Supabase/canonical HTTPS configuration in `.env.local`, retaining mode 600 and all existing keys. Set `CONVERSIONS_ENABLED=false`.
- [x] Prepare a system service running as jinwoo, one worker, loopback port 3000, restart on failure, journal logging without request URLs, and boot enablement. Strip `OPENAI_API_KEY` from the service environment.
- [x] Run `systemd-analyze verify deploy/brainconverter.service`. Refuse to overwrite an existing unit or occupy a busy port.
- [x] Ask for the privileged installation only after the unit and installer are reviewable. A sudo password is required on this machine and must never be requested in chat.
- [x] Install and start the system unit after the user's sudo action. Active/enabled; installed unit matches source.

Install: `sudo bash deploy/install-systemd.sh`; expected: enabled and active `brainconverter.service`. Do not modify cloudflared or DNS.

### Task 3: Live read-only checks and operational report

Files: `scripts/verify_production.py`, `supabase/audit_production_readonly.sql`, `docs/UBUNTU_DEPLOYMENT_REPORT.md`.

- [x] Verify Supabase health/settings, REST RPC registration, private-schema exclusion, and anonymous read-RPC denials without invoking mutating RPCs.
- [x] Prepare a transaction-read-only catalog audit for full RLS/grants/trigger checks; execute only if database access is available. Report the distinction between source definitions and live evidence.
- [x] Compare actual local and public HTML/JS/CSS, auth callback, cache/security headers, anonymous API denials, CSRF denials, and invalid JWT rejection. Also verify public HTTP redirects to HTTPS.
- [x] Verify startup and restart behavior after systemd installation. Check cloudflared active/enabled without printing its token-bearing command line. An intentional process failure recovered in 5.86 seconds; actual host reboot remains untested.
- [ ] Obtain explicit test-account authorization before real signup. User-controlled email/password login and administrator approval are manual until authorized credentials/actions are available. Do not manufacture administrators or approvals.
- [x] Report tested and untested results separately, with redeployment, journal, recovery, and optional reboot verification commands.

No migrations, bootstrap scripts, Vercel deployment scripts, paid AI requests, budget resets, or existing data changes are authorized by this plan.
