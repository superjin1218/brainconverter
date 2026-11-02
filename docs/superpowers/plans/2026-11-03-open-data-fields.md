# Open Data Fields Implementation Plan

> Execute inline, then commit and push to brainconverter/main as requested. No production SQL, paid inference, or service redeployment.

**Goal:** Allow model-selected financial and other BRAIN data identifiers without a fixed indicator-to-field mapping.

**Architecture:** Share identifier syntax validation across Pydantic schemas and the typed AST compiler. Keep allowed expression structures, operators, source evidence, preference checks, approval and budget controls. Remove category-based rejection from prompts and source guards; leave BRAIN catalog availability unverified and disclose that in generated assumptions.

**Tech Stack:** Python, Pydantic, FastAPI, static HTML, pytest, Node tests.

### 1. Schema and compiler

- [x] Add `backend/app/data_fields.py` with `is_data_field(name)` for ASCII identifiers (letter first, letters/digits/underscores, at most 128 characters), excluding Python keywords/constants and reserved group identifiers. No indicator table, aliases, external catalog or templates.
- [x] In `backend/app/models.py`, replace field enums with a shared annotated string type, including `IntentMetric.reference`, `SignalIR.field` and `EntryIR.field`.
- [x] In `backend/app/draft_compiler.py`, accept validated names as series and preserve them verbatim; keep existing friendly price labels only for explanations. Remove financial/news category rejection from both this file and `backend/app/compiler.py`; preserve execution-rule checks.
- [x] Include the new validation module in `backend/app/provider_diagnostics.py`'s revision digest. Add a generated assumption for model-selected fields whose labels/catalog availability the server does not know.

### 2. Instructions and product copy

- [x] Update `backend/app/skills/brain-strategy/SKILL.md`: model selects identifiers for all data categories; never reject merely because input mentions financial data; no fixed examples mapping indicators to fields. Keep source grounding and execution limitations, and never claim catalog/simulation verification.
- [x] Update `README.md` and `backend/app/static/index.html` to match the expanded scope and explain BRAIN availability checks.

### 3. Regression tests, verification, publication

- [x] Test arbitrary model-chosen identifiers through real adapter parsing with mocked HTTP and full compilation: raw, ratio, time-series and entry-condition fields; two different identifiers for the same input must remain distinct. Verify schema has no six-field enum and reject code fragments/attribute access/subscripts/functions as fields.
- [x] Update obsolete tests that classify all financial data as unsupported; retain execution and malformed-expression rejection tests.
- [x] Run `env -u RUN_SQL_TESTS .venv/bin/pytest -q --ignore=backend/tests/test_membership_sql.py`, `node --test backend/tests/*.test.mjs`, Ruff and `git diff --check`. Verify the 2,000-character request still fits the existing 16,000-byte budget. Do not execute SQL or paid OpenAI.
- [ ] Commit only this change and push `main` to `https://github.com/superjin1218/brainconverter.git`; keep the private screenshot untracked and verify the remote commit equals HEAD.

## Validation result

Python: 555 passed with SQL tests explicitly excluded. JavaScript: 49 passed. Ruff and whitespace checks passed. The 2,000-character input request is 14,816 bytes, within the unchanged 16,000-byte cap. New tests exercise the actual OpenAI adapter using mocked HTTP; no paid inference, database operations or server restart. Fields in tests are synthetic model output, not verified BRAIN identifiers or a production mapping. Existing authentication, approval and budgets are unchanged.
