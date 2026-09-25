# ADR-002: Modular Monolith Architecture

**Status:** Accepted
**Date:** 2026-09-23
**Author:** Mayasura
**References:** PRD §10.1, ARCH-20260923-001

---

## Context

The system has a scheduler, a REST API, a document processing pipeline, and a background
LLM orchestration layer. A naive reading could suggest multiple services: a "data ingestion
service", an "LLM orchestration service", an "API service". The question is whether these
should be separate deployable processes.

**Forces at play:**
- Single developer (Atharva). Each additional process is additional operational surface.
- Oracle Cloud Always Free — one instance. No managed container runtime, no load balancer,
  no service discovery. Running microservices on a single VM is not microservices; it is
  a distributed monolith with extra configuration overhead.
- The ₹0 infrastructure constraint eliminates cloud-native orchestration (ECS, GKE, etc.)
  that would make microservices operationally tractable.
- The domain boundaries are clear but the components share data heavily. The daily briefing
  pipeline, the deep dive pipeline, and the API all read from the same PostgreSQL tables.
  Shared data across service boundaries requires either a shared database (coupling
  anti-pattern) or inter-service APIs (latency and complexity).
- The system processes ~26 batch jobs per month. It is not a high-throughput real-time system.

**Microservices' case:**
- Independent scaling of the scheduler vs. the API. (Not relevant — single instance.)
- Independent deployment of each component. (Not relevant — single developer, no CI/CD gates.)
- Technology diversity per component. (Not needed — Python throughout is the right call here.)

**Modular monolith's case:**
- One process to deploy, monitor, and restart.
- Shared in-process data access without API overhead.
- Domain modules (briefing, deep_dive, watchlist, ingestion) are independently structured
  within the codebase — extraction to separate services is possible later if load justifies it.
- APScheduler embedded in the same process as FastAPI is standard practice for this scale.

---

## Decision

**Modular monolith: one Python process.**

The process structure: FastAPI (serves HTTP) + APScheduler (runs background jobs) in a
single Python application, started by a single `systemd` service. Modules are separated
by directory (not by network boundary). Inter-module calls are function calls, not HTTP.

**Module structure:**
```
app/
  api/            # FastAPI routers — HTTP boundary only
  services/       # Application logic — orchestrates domain + infra
  domain/         # Pure business logic — no I/O, no framework dependencies
  ingestion/      # Data fetching, document fetching, parsing
  scheduler/      # APScheduler job definitions and registration
  llm/            # LLM client abstraction
  db/             # SQLAlchemy models, Alembic migrations, session management
  config/         # Settings (pydantic-settings), model routing config
```

This structure enforces the layering discipline without requiring a service boundary to
enforce it. The `domain/` layer has zero imports from `api/`, `ingestion/`, or `llm/`.

---

## Consequences

**Easier:**
- Single `systemd` unit for the entire application.
- No inter-service latency for pipeline steps.
- Shared SQLAlchemy session across the application — consistent transaction boundaries.
- Single `.env` file, single config, single log stream.
- On-call debugging: `journalctl -u stock-research.service` shows everything.

**Harder:**
- A CPU-intensive parsing job (large PPTX with many slides) will compete with API request
  handling in the same process. Mitigation: run heavy parsing as a background thread or
  use Python's `ProcessPoolExecutor` for CPU-bound document parsing tasks.
- Memory usage is shared — a memory leak in the parsing pipeline affects API availability.
  Mitigation: run parsing in a subprocess with a memory limit via `resource` module.

**Technical debt:**
- If the system ever serves more than ~20 concurrent users (beyond the stated 3–5),
  the API and scheduler sharing a process will require revisiting. This is explicitly
  accepted for v1.0.

**Extraction path (not for v1.0):**
If a component needs independent scaling or a language boundary in the future:
1. The `ingestion/` module is the most likely extraction candidate (I/O-bound, can
   run as an independent worker reading from a queue).
2. The `llm/` module could become a proxy service to enforce the cost ceiling centrally.
3. Neither extraction is warranted until load justifies it. The module boundary makes
   it possible when needed — it is not urgent now.
