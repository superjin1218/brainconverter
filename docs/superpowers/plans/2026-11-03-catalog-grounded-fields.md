# Catalog-grounded Conversion Implementation Plan

> Execute inline. User requests fixing field/type/source errors, five live experiments, commit and push. Do not run production SQL or change membership/budget policies.

**Goal:** The model selects real field IDs from a scoped catalog; fabricated IDs, type-invalid operations and punctuation-only source failures are prevented.

**Architecture:** Refresh an account-authorized WQ catalog into ignored local data, build a local semantic index, plan English search concepts with the same fixed model, retrieve candidates with OpenAI embeddings, and provide a bounded candidate list in one intent-generation request. Bind that same list to the response schema and compiler using request-scoped context. VECTOR-to-series conversion uses field metadata, never an indicator-to-field recipe. Source normalization retains original spans for overlap checks.

**Tech Stack:** FastAPI/Pydantic, OpenAI text-embedding-3-small (384 dimensions), NumPy, HTTPX, existing OpenAI and WQ APIs.

- [x] Add `scripts/refresh_brain_catalog.py`: authenticated scoped field/operator discovery, safe credential handling, local snapshot and embedding-index preparation. Ignore `data/brain_catalog/`; runtime never copies WQ credentials into prompts or Git.
- [x] Add `backend/app/field_catalog.py`: scoped snapshot validation, multilingual concept search and embedding retrieval plus lexical matching, immutable request candidates, bounded prompt context, and no hardcoded financial mapping. Missing/mismatched catalogs fail before paid inference.
- [x] Bind candidate IDs to `response_schema.strict_schema()` using request-local context and also verify compiled identifiers. Add catalog-based VECTOR reduction and operator permission checks. Preserve one intent generation and the aggregate 34-KRW reserve across all three API stages.
- [x] Update `HarnessService`, prompt and schema integration; include all catalog logic in source revision diagnostics. Do not claim field-ID/type validation proves semantic or performance correctness.
- [x] Fix punctuation-only source quote mismatches using original offset maps; keep duplicate-source and paraphrase rejection. Detect explicit daily-return-volatility mismatches without inventing financial field mappings.
- [x] Add offline tests with injected catalogs/encoders, including concurrent request isolation, unlisted IDs, vector/reference/entry handling, schema enum, input-size limits, wrong scopes, source spans, and recorded failure regressions.
- [x] Update README, dependency/lock files and deployment preflight with catalog setup and scope requirements. Run Python/JS/Ruff checks without SQL tests.
- [x] Run five actual OpenAI/WQ experiments covering ROE, PER punctuation, news/vector, analyst fields and return volatility; preserve raw outcomes and show errors honestly. No alpha submission or uncontrolled repair loops.
- [x] Commit reviewed code and push to `brainconverter/main`; exclude credentials, catalog/model blobs, screenshots and test artifacts. Report live-test scope and any remaining limitations.
