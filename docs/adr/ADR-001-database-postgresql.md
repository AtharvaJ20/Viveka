# ADR-001: PostgreSQL as the Primary Database

**Status:** Accepted
**Date:** 2026-09-23
**Author:** Mayasura
**References:** PRD §10.1, IMP-20260923-001 Phase 0

---

## Context

The system requires persistent storage for: market price data, sector mappings, corporate
filings and document metadata, generated reports, watchlist, user sessions, scheduler job
state, and LLM cost tracking. Two options are viable: SQLite and PostgreSQL.

**Forces at play:**
- The web application (Phase 1 onward) requires concurrent reads from the FastAPI backend
  and the Next.js SSR layer simultaneously. SQLite writer locks prevent this.
- APScheduler requires a persistent job store that survives process restarts. Both SQLite
  and PostgreSQL support this, but PostgreSQL's implementation is more robust under
  concurrent scheduler + API access.
- JSONB (PostgreSQL native) is needed for flexible report content storage — report schemas
  evolve across phases and must not require a migration for every structural change.
- The Oracle Cloud Always Free instance has 24 GB RAM and 4 ARM cores. Running PostgreSQL
  alongside the Python app and Next.js process is well within this envelope.
- Infrastructure cost is ₹0 in both cases (self-hosted). There is no cloud database cost
  consideration here.

**SQLite's case:**
- Zero-configuration, no separate process.
- Simpler for a single-developer project.
- Acceptable for Phase 0 and Phase 1 if the application is purely single-writer.

**PostgreSQL's case:**
- Handles concurrent reads from multiple processes without locking.
- JSONB with GIN indexes for efficient report archive search (WEB-006).
- Full-text search via `tsvector` for report and document search.
- APScheduler's PostgreSQL job store is more reliable than the SQLite equivalent under
  concurrent process access.
- Alembic migrations are dialect-agnostic in principle but PostgreSQL-specific features
  (JSONB, `tsvector`, advisory locks) would require migration if switching later.

---

## Decision

**PostgreSQL from Phase 0.**

SQLite is rejected, not because PostgreSQL is better in the abstract, but because the
web application with concurrent FastAPI + Next.js access makes SQLite's write-locking
a real problem — and that problem appears in Phase 1, not later. Migrating from SQLite
to PostgreSQL after Phase 1 is built is expensive. The marginal operational cost of
running PostgreSQL on the Oracle Cloud instance is negligible.

---

## Consequences

**Easier:**
- Concurrent reads from API and scheduler without locking.
- JSONB report storage with efficient GIN-indexed search.
- Full APScheduler PostgreSQL job store (job persistence across restarts).
- Full-text search on reports and document content without an additional service.
- Alembic migrations are the standard approach; no improvisation needed.

**Harder:**
- Requires PostgreSQL running as a separate process (managed by systemd).
- Connection pooling needed from Phase 1 (PgBouncer or SQLAlchemy pool — see below).
- Slightly more configuration than SQLite.

**Connection pooling decision:**
SQLAlchemy's built-in connection pool (`pool_size=5`, `max_overflow=10`) is sufficient
for this single-instance deployment. PgBouncer adds operational complexity with minimal
benefit at this scale. Revisit if concurrent request count grows beyond ~50 simultaneous
connections — not expected for a 3–5 user personal tool.

**Technical debt created:**
None. PostgreSQL is the correct choice for this system's access patterns and will not
need to be revisited.

**What must be monitored:**
- Disk usage of the PostgreSQL data directory — price data, document text, and report
  JSONB accumulate over time. Alert if disk usage exceeds 60% of the instance's 50 GB
  free tier allocation.
