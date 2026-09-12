"""Read-only FastAPI service over the existing Postgres repositories.

Additive and read-only by design (Phase 1 of docs/MODERNIZATION_AUDIT.md
§03/§04): every endpoint is a typed pass-through over a ScanRepository /
OutcomesRepository / MlModelsRepository method that already exists for the
Streamlit dashboard, the digest job, or the ML pipeline. This package does
not write to the database and does not touch scoring/eligibility/tier logic
(engine/, scoring/, factors/, filters/, regime/, strategies/, lynch/,
report/) — those stay exactly as the CLI scanners already run them.
"""
