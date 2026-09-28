━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Document:    Phase 1 Execution Plan — Daily Briefing
ID:          EXP-20260926-001
Author:      Krishna (PM)
Owner:       Atharva
Date:        2026-09-26
Version:     v1.1
Status:      Active — In Progress (2026-09-28)
References:  IMP-20260923-001, PRD-20260909-001 v2.0, ADR-001–005
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Phase 1 Execution Plan — Daily Briefing

---

## 1. Phase Goal

**Goal:** The 21:00 IST automated daily briefing is live and readable in the dashboard on trading days. The first user-visible output of the platform.

**Done looks like:** A scheduled job runs at 21:00 IST on every NSE trading day, produces sector rankings and trigger summaries, persists the report, and the dashboard displays it. The job is skipped (not silenced — logged and exited) on weekends and holidays. A developer can re-run any past day from the CLI.

---

## 1a. Phase 1 Progress Summary (as of 2026-09-28)

| Task | Owner | Status |
|---|---|---|
| T-VYS-01: DataFetcher + OHLCV Ingestion | Vyasa | ✓ Done |
| T-VYS-02: Sector Classification Mapping | Vyasa | ✓ Done |
| T-VYS-03: Trading Calendar | Vyasa | ✓ Done |
| T-VYS-04: Staleness / Empty-Data Detection | Vyasa | ✓ Done |
| T-VYS-05: News + Exchange Announcement Ingestion | Vyasa | ✓ Done |
| T-VIS-01: Sector Ranking Logic (Narada-approved) | Vishwakarma | ✓ Done |
| T-VIS-02: LLMClient + Trigger Analysis | Vishwakarma | ✓ Done |
| T-ARJ-01: Web App Shell | Arjun | ✓ Done |
| T-BHM-04: Schema Decision — News Storage | Bhima | ✓ Done (Option B chosen) |
| T-BHM-01: APScheduler Setup | Bhima | ✓ Done |
| T-BHM-02: Job Pipeline Orchestration | Bhima | ✓ Done |
| T-BHM-03: Manual Re-run CLI | Bhima | ✓ Done |
| T-BHM-05: Report Persistence + REST API | Bhima | Not started |
| T-ARJ-02: Dashboard — Sector Rankings | Arjun | Not started (blocked on T-BHM-05) |
| T-NAK-01: APScheduler Deployment + Caddy Update | Nakula | BLOCKED — OCI provisioning |
| T-SAD-01: Phase 1 QA Gate | Sahadeva | Not started (gated on T-BHM-05 + T-ARJ-02 + T-NAK-01) |

**Critical path remaining:** T-BHM-05 → T-ARJ-02 → T-SAD-01

**Alembic chain:** a0001→a0013 (a0013 fixes job_executions CHECK constraint defect — see RSK-20260923-001 R-P1-08)

---

## 2. Current State (Phase 0 Handoff)

All Phase 0 exit criteria passed. Sahadeva issued GO for Phase 1 kickoff on 2026-09-26.

**What is ready:**
- PostgreSQL schema: 11 migrations (a0001–a0011). Tables live: `users`, `sessions`, `sectors`, `companies`, `company_sectors`, `price_data`, `trading_calendar`, `documents`, `document_pages`, `extracted_figures`, `financials`, `watchlist_items`, `reports`, `job_executions`, `llm_usage`.
- Auth shell: 46/46 tests passing, all 13 SR-AUTH requirements met.
- FastAPI application shell: `backend/app/main.py`, `backend/app/api/v1/auth.py`.
- Frontend scaffold: Next.js 14, Tailwind CSS, design tokens wired. Landing page, login page, auth-protected app layout stub, dashboard stub.
- Deployment scaffold: `deploy/bootstrap.sh`, `deploy/Caddyfile`, `deploy/viveka-api.service`, `deploy/runbook.md`.
- LLMClient abstraction: defined in ADR-005; implementation is Vishwakarma's responsibility in Phase 1.

**Open items carried from Phase 0 (not blockers for Phase 1 code work):**
- **OCI-001:** Live Oracle Cloud instance not yet provisioned. Atharva must provision the instance and run `deploy/bootstrap.sh` before live end-to-end test is possible. Does not block code development.
- **OCI-002 (SR-AUTH-011):** `git ls-files` check for `.env` files — Nakula's responsibility at first-commit time.

---

## 3. Pre-conditions for Phase 1 Kickoff

All must be true before any Phase 1 task begins:

| # | Condition | Status |
|---|---|---|
| P1 | Phase 0 Sahadeva QA: GO | ✓ Confirmed 2026-09-26 |
| P2 | All Phase 0 lint defects (BUG-003, BUG-004) closed | ✓ Confirmed 2026-09-26 |
| P3 | Design tokens available in `frontend/styles/tokens.css` | ✓ Done |
| P4 | `backend/app/db/models/` ORM models available | ✓ Done (a0001–a0011) |
| P5 | ADR-005 (LLMClient) available for Vishwakarma | ✓ Done |
| P6 | `deploy/viveka-api.service` uses `--workers 1` | ✓ Nakula confirmed |

---

## 4. Schema Gap — Decision Required Before Work Starts

**Issue:** The Phase 0 schema has no dedicated table for news or exchange announcements. REQ-021 requires news ingestion; REQ-002 requires news per stock for trigger analysis.

**Options:**
- **Option A (Transient):** Vyasa fetches news at pipeline execution time. Raw items are never persisted. The LLM trigger summary (2–4 sentences) is stored in the report JSONB only.
- **Option B (Persistent):** Bhima creates migration `a0012_news_items` with `(id, ticker, headline, source_name, url, published_at, fetched_at, exchange)`. Enables re-running trigger analysis against the same news without re-fetching. Supports future audit.

**Recommendation:** Option B. The additional migration is trivial. Debugging a wrong trigger summary weeks later requires knowing what news was available at the time. Re-fetching is not always possible (some exchange feeds are not historical). The persistent table costs one migration and a handful of rows per day — negligible.

**Owner:** Bhima must make this decision and either create migration a0012 or explicitly choose Option A and document it before T-VYS-05 begins.

---

## 5. Task Registry

Tasks are grouped by agent. Each task has a unique ID, explicit inputs, explicit outputs, acceptance criteria, and all upstream dependencies.

---

### 5.1 Vyasa — Data Layer

Vyasa owns the data ingestion stream. Tasks T-VYS-01, T-VYS-02, and T-VYS-03 are independent and can be developed in parallel within a session. T-VYS-04 and T-VYS-05 depend on earlier Vyasa work.

---

#### T-VYS-01: DataFetcher Protocol + OHLCV Ingestion (REQ-020)

**Owner:** Vyasa  
**Depends on:** Phase 0 schema (migration a0003 `price_data`)

**Description:** Implement the `DataFetcher` abstraction defined in ARCH §6. The fetcher routes by exchange (NSE vs BSE). Phase 1 uses NSE via yfinance. The BSE Bhavcopy CSV route must be **stubbed and registered** in Phase 1 — not implemented — so the router exists and Phase 5 only adds the BSE implementation without changing the pipeline.

Fetch daily OHLCV for all tracked NSE companies at the end of each trading day. Persist to `price_data` table. Include the 20-day trailing volume data needed by REQ-001 (volume ratio ranking).

**Inputs:**
- `docs/architecture.md` ARCH §6 — DataFetcher abstraction spec
- `backend/app/db/models/price_data.py` — ORM model
- NSE ticker list from `companies` table (populated by T-VYS-02)

**Outputs:**
- `backend/app/fetchers/__init__.py` — DataFetcher Protocol definition
- `backend/app/fetchers/nse_yfinance.py` — NSE fetcher (yfinance)
- `backend/app/fetchers/bse_stub.py` — BSE stub (raises `NotImplementedError` with message "BSE Bhavcopy fetcher not implemented until Phase 5")
- `backend/app/fetchers/registry.py` — exchange → fetcher router
- Unit tests: mock yfinance responses for 5 NSE tickers, verify persistence to `price_data`

**Acceptance Criteria:**
- Given a list of NSE tickers and a date, when the fetcher runs, then OHLCV rows are written to `price_data` with `exchange='NSE'`, `ticker`, `date`, `open`, `high`, `low`, `close`, `volume`, `source='yfinance'`.
- Given an empty yfinance response for a ticker, when the fetcher runs, then the ticker is logged as a warning and skipped; no partial row is written; the job does not abort.
- Given `exchange='BSE'`, when the fetcher runs, then a `NotImplementedError` is raised immediately (no silent failure).
- Given 20 previous trading days exist in `price_data` for a ticker, when the fetcher runs, then the row for today includes a computed `volume_20d_avg` (or this is computed by the ranking layer — **Vyasa must decide which layer owns this computation and document the decision**).
- All code paths covered by unit tests using mock data.

---

#### T-VYS-02: Sector Classification Mapping (REQ-037)

**Owner:** Vyasa  
**Depends on:** Phase 0 schema (migrations a0002 `sectors`, `companies`, `company_sectors`)

**Description:** Create a versioned sector → company mapping. Source must be documented (NIFTY sectoral index constituents from NSE is the recommended source). The mapping file has a version string so that every sector ranking report records which sector map version was active.

Seed `sectors` and `companies` tables (NSE mainboard stocks with sector assignments). The mapping must support the `SECTOR_MIN_CONSTITUENTS` threshold (sectors with fewer members are excluded from rankings).

**Inputs:**
- NSE sectoral index constituent data (downloadable from NSE website)
- `backend/app/db/models/sectors.py`, `companies.py`, `company_sectors.py` — ORM models
- REQ-037: versioned mapping requirement

**Outputs:**
- `backend/app/data/sector_map_v1.yaml` (or CSV) — versioned sector → ticker mapping with `version: "v1"` header
- `backend/app/data/loader.py` — loads mapping from file, seeds/updates database
- `backend/app/db/models/` — confirm `sector_map_version` field exists on `sectors` table or decide where version is tracked
- Seeded database: all NSE mainboard sectors and companies populated
- Unit tests: loader reads file, inserts correct rows, handles duplicate ticker gracefully

**Acceptance Criteria:**
- Given a fresh database, when the loader runs, then `sectors`, `companies`, and `company_sectors` are populated and `SELECT COUNT(*) FROM sectors` returns ≥ 10.
- Given version = "v1", then every sector row has `map_version = 'v1'` (or equivalent version tracking at the sector_map level).
- Given a sector with fewer than `SECTOR_MIN_CONSTITUENTS` tickers, when rankings run, then that sector is excluded from both rankings.
- Given the same loader run twice, the second run is idempotent (no duplicate rows).
- Data source documented in comments or README within `backend/app/data/`.

**Decision Required:** Where is `map_version` stored — on each `company_sectors` row, in a separate `sector_map_versions` table, or as a static field on `sectors`? Vyasa must decide and implement consistently.

---

#### T-VYS-03: Trading Calendar (REQ-035)

**Owner:** Vyasa  
**Depends on:** Phase 0 schema (migration a0004 `trading_calendar`, composite PK `(trading_date, exchange)`)

**Description:** Populate `trading_calendar` with NSE and BSE holiday calendars for the current year (2026) and next year (2027). Include the Diwali Muhurat session date as a non-trading day (per PRD REQ-003). Provide a utility function used by the scheduler and job pipeline.

**Inputs:**
- NSE and BSE official holiday calendars (public, downloadable)
- `backend/app/db/models/trading_calendar.py` — ORM model

**Outputs:**
- `backend/app/data/holidays_2026.yaml` + `holidays_2027.yaml` — raw holiday lists (NSE + BSE separately)
- `backend/app/utils/calendar.py`:
  - `is_trading_day(date: date, exchange: str = "NSE") -> bool`
  - `next_trading_day(from_date: date, exchange: str = "NSE") -> date`
  - `last_trading_day(from_date: date, exchange: str = "NSE") -> date`
- Database seeder for `trading_calendar` (idempotent)
- Unit tests: verify 5 known 2026 NSE holidays return `is_trading_day=False`; verify 3 known trading days return `True`; verify Saturday always returns `False`.

**Acceptance Criteria:**
- Given NSE Independence Day 2026 (15 Aug), when `is_trading_day(2026-08-15, "NSE")` is called, then `False` is returned.
- Given any Saturday or Sunday, when `is_trading_day` is called, then `False` is returned regardless of exchange.
- Given Diwali Muhurat 2026, when `is_trading_day` is called, then `False` is returned.
- Given a regular Monday, when `is_trading_day` is called, then `True` is returned.
- Holiday data sourced from official NSE/BSE calendar, not inferred. Source URL documented in comments.

---

#### T-VYS-04: Staleness / Empty-Data Detection (REQ-036)

**Owner:** Vyasa  
**Depends on:** T-VYS-01, T-VYS-03

**Description:** Before the ranking job runs, verify that price data for today is actually present. If today is a trading day per the calendar AND `price_data` has no rows for today's date, the job must abort cleanly and log the reason. This prevents a stale or empty report from being generated and published.

**Inputs:**
- `backend/app/utils/calendar.py` (T-VYS-03)
- `backend/app/db/models/price_data.py` (T-VYS-01)

**Outputs:**
- `backend/app/utils/staleness.py`:
  - `check_data_freshness(date: date, exchange: str, session) -> StalenessResult`
  - `StalenessResult` — dataclass with `is_fresh: bool`, `reason: str`, `row_count: int`
- Unit tests: verify detection fires when price_data is empty for today; verify it passes when rows exist; verify it does not fire on a non-trading day.

**Acceptance Criteria:**
- Given today is a trading day and `price_data` has zero rows for today, when `check_data_freshness` is called, then `is_fresh=False` and `reason` names the missing data.
- Given today is a trading day and `price_data` has ≥ N rows for today (N configurable, default 50), then `is_fresh=True`.
- Given today is a non-trading day, then `check_data_freshness` returns `is_fresh=True` with reason "non-trading day" (the job should not run at all — staleness is not the abort reason).
- The ranking job **never proceeds** past the staleness check when `is_fresh=False`.

---

#### T-VYS-05: News + Exchange Announcement Ingestion (REQ-021)

**Owner:** Vyasa (with Sanjaya advisory on exchange API patterns)  
**Depends on:** T-BHM-04 (schema decision), T-VYS-02 (company list)

**Description:** Fetch exchange announcements and financial news for NSE-listed companies. This data is used by Vishwakarma's trigger analysis (T-VIS-02) to identify the cause of sector moves.

**Invoke Sanjaya before implementing.** Sanjaya provides the correct NSE/BSE announcement API endpoints, rate limits, and known parsing quirks before Vyasa writes a single line of fetcher code.

**Inputs:**
- NSE announcement API / RSS (Sanjaya to provide endpoint details)
- BSE announcement API / RSS (Sanjaya to provide endpoint details)
- Schema decision from T-BHM-04

**Outputs:**
- `backend/app/fetchers/news_nse.py` — NSE announcements fetcher
- `backend/app/fetchers/news_bse.py` — BSE announcements fetcher (at minimum a stub for Phase 1; NSE is higher priority)
- `backend/app/fetchers/news_aggregator.py` — combines sources, deduplicates by URL
- Unit tests with mocked HTTP responses for 3 NSE ticker announcements
- If Option B (persistent): migration `a0012_news_items` and ORM model `backend/app/db/models/news_item.py`

**Acceptance Criteria:**
- Given a ticker `RELIANCE.NS` with one known announcement, when the fetcher runs, then the announcement headline, source URL, and `published_at` timestamp are captured.
- Given a non-trading day, the news fetcher still runs (news is published on non-trading days too). The staleness guard applies to price data only, not news.
- Given an HTTP 429 or 503 from the exchange API, then the fetcher retries twice with exponential backoff and logs the failure; the trigger analysis job proceeds with whatever news was fetched (partial is acceptable; failure to fetch is not a job-abort condition).
- Given Option B: news items are persisted with `ticker`, `headline`, `source_name`, `url`, `published_at`, `fetched_at`. Duplicate URLs are ignored on re-fetch.

---

### 5.2 Vishwakarma — Ranking and Trigger Logic

Vishwakarma's work depends on T-VYS-01 and T-VYS-02 being complete. Narada must review T-VIS-01 before Vishwakarma proceeds to T-VIS-02.

---

#### T-VIS-01: Sector Ranking Logic (REQ-001)

**Owner:** Vishwakarma  
**Reviewer:** Narada (statistical validation of median and volume ratio method)  
**Depends on:** T-VYS-01, T-VYS-02

**Description:** Implement the two independent sector ranking algorithms. Price ranking: median percentage change of a sector's constituent stocks for the trading day. Volume ranking: total sector volume for the day divided by the sector's trailing 20-day average volume. Both rankings exclude sectors below `SECTOR_MIN_CONSTITUENTS`. Each ranked sector also exposes its single strongest contributing stock (by absolute price move).

**Inputs:**
- `price_data` table (OHLCV for today + 20-day lookback from T-VYS-01)
- `sectors`, `company_sectors`, `companies` tables (T-VYS-02)
- Config: `SECTOR_RANK_METHOD` (default `"median"`), `VOLUME_LOOKBACK_DAYS` (default 20), `SECTOR_MIN_CONSTITUENTS` (default — Vishwakarma to propose)
- ADR-005: LLMClient is NOT used in this task (rankings are pure computation)

**Outputs:**
- `backend/app/jobs/ranking.py`:
  - `compute_price_ranking(session, date) -> list[SectorRank]`
  - `compute_volume_ranking(session, date) -> list[SectorRank]`
  - `SectorRank` — dataclass: `sector_name`, `sector_score`, `top_constituent` (ticker + score), `constituent_count`, `map_version`
- Unit tests: 3 mock sectors with known OHLCV data → verify correct median, volume ratio, top constituent, exclusion of thin sectors.
- Narada review: Vishwakarma must produce a 1-page description of the algorithm (why median, how volume ratio is computed, what edge cases are handled) and hand it to Narada before proceeding to T-VIS-02.

**Acceptance Criteria:**
- Given 3 sectors with known price moves, when `compute_price_ranking` runs, then the top 3 are returned ordered by descending median price change.
- Given a sector where one stock is up 30% and all others are flat, then the sector's score is approximately 0% (median, not max) — this is the explicit PRD design intent.
- Given a sector with fewer than `SECTOR_MIN_CONSTITUENTS` members, then it is absent from both rankings.
- Given `SECTOR_RANK_METHOD = "max"`, then the ranking switches to max constituent move (the fallback mode documented in the PRD warning block).
- Given 20 days of volume data, then volume ratio = today's total / 20-day average × 100, rounded to 2 decimal places.
- The `map_version` from the active sector map is included in every `SectorRank` result.
- Narada sign-off obtained before T-VIS-02 starts.

---

#### Narada Review: Validate Ranking Statistics

**Owner:** Narada (advisory; not an implementation task)  
**Depends on:** T-VIS-01 algorithm document from Vishwakarma

**Narada must confirm:**
- Median is the statistically appropriate central measure for price-change distribution (vs. mean, which is sensitive to outliers in a small sector).
- Volume ratio formula is sound and consistent units (daily volume / 20-day daily average — not mixing daily with weekly).
- Edge cases: single-constituent sector, all-zero volume day, negative close price (bad data), missing OHLCV rows.
- Any statistical concern must be documented as a recommendation. Vishwakarma decides whether to accept or counter. If disputed, flag to Atharva.

**Output:** Written comment in INBOX.md: "Narada → STATUS: Ranking algorithm validated / Narada → STATUS: Concern found: [description]."

---

#### T-VIS-02: LLMClient Implementation + Trigger Analysis (REQ-002)

**Owner:** Vishwakarma  
**Depends on:** T-VIS-01 (Narada-approved), T-VYS-05

**Description:** Implement the `LLMClient` abstraction (ADR-005) and use it for trigger analysis. For each stock returned by T-VIS-01 as the top contributor in a top-3 sector, search the news items from T-VYS-05 and produce a 2–4 sentence trigger summary. If no relevant news is found, the summary must be `"No identifiable trigger found for this move."` — never an LLM-fabricated explanation.

**LLMClient implementation** (per ADR-005):
- Zero direct Anthropic SDK calls outside `LLMClient`.
- Cost ceiling enforced before every call: check `llm_usage` table for current month's spend; abort if within 10% of ₹500 ceiling.
- Model routing via config dict `MODELS`. Phase 1 trigger analysis: `MODELS["trigger_analysis"]` defaults to `"claude-haiku-4-5-20251001"` (cost-conscious; trigger summaries are short).
- All calls log to `llm_usage` table: `job_type`, `model`, `input_tokens`, `output_tokens`, `cost_inr`, `called_at`.

**Inputs:**
- T-VIS-01 output: ranked stocks needing trigger analysis
- T-VYS-05 output: news items for those tickers (from DB or in-memory)
- ADR-005 spec
- `backend/app/db/models/llm_usage.py` — ORM model (migration a0011)
- Anthropic SDK (add to `pyproject.toml` if not already present)

**Outputs:**
- `backend/app/services/llm_client.py` — LLMClient implementation
- `backend/app/jobs/trigger_analysis.py`:
  - `analyze_triggers(session, ranked_stocks: list[SectorRank], date: date) -> list[TriggerResult]`
  - `TriggerResult` — dataclass: `ticker`, `sector_name`, `trigger_summary`, `news_urls_used: list[str]`, `model_used`, `tokens_used`
- Unit tests: mock LLMClient, verify "no identifiable trigger" path when no news; verify cost guard fires when within 10% of ceiling.

**Acceptance Criteria:**
- Given 3 flagged stocks and matching news items, when `analyze_triggers` runs, then each stock has a `trigger_summary` of 2–4 sentences.
- Given a stock with no matching news items, then `trigger_summary = "No identifiable trigger found for this move."` — the LLM is NOT called for this stock (zero tokens consumed).
- Given current month's LLM spend is ≥ ₹450 (90% of ₹500), then trigger analysis is skipped for all stocks and a warning is logged; daily price/volume rankings are still published (rankings are LLM-free).
- Every successful LLM call produces a row in `llm_usage` with correct `model`, `input_tokens`, `output_tokens`, `cost_inr` (₹ conversion must use a documented exchange-rate config value, not a hardcoded assumption).
- Token costs are computed as: (input_tokens × input_price_per_token + output_tokens × output_price_per_token) × USD_TO_INR. All three config values are in `app/config.py`.

---

### 5.3 Bhima — Scheduler, Persistence, and API

---

#### T-BHM-04: Schema Decision — News Storage

**Owner:** Bhima (with Vyasa input)  
**Depends on:** Nothing (must happen before T-VYS-05)

**Description:** Decide Option A (transient) or Option B (persistent `news_items` table) per §4 above. Document the decision in INBOX.md. If Option B, write migration `a0012_news_items` before T-VYS-05 begins.

**Output:** INBOX.md entry `[date] Bhima → DECISION: news storage: [Option A / Option B + rationale]`. If Option B: `backend/alembic/versions/012_news_items.py` and `backend/app/db/models/news_item.py`.

---

#### T-BHM-01: APScheduler Setup (REQ-003, REQ-030)

**Owner:** Bhima  
**Depends on:** T-VYS-03 (trading calendar utility)

**Description:** Wire APScheduler into the FastAPI application. Add a CronTrigger for 21:00 IST (Asia/Kolkata timezone). Before the job runs, call `is_trading_day(today, "NSE")`; if False, log a skip entry to `job_executions` and exit cleanly — no report generated, no error. Include retry logic: on transient failure (HTTP error from data fetch, DB timeout), retry up to 2 times with 5-minute backoff. Log every execution start, completion, skip, and failure to `job_executions`.

**Critical constraint:** APScheduler must run inside the single FastAPI process — no forking, no subprocesses. Nakula's `--workers 1` constraint makes this safe. Do not use `BackgroundScheduler` if it spawns threads that outlive the gunicorn worker.

**Inputs:**
- `backend/app/utils/calendar.py` (T-VYS-03)
- `backend/app/db/models/job_executions.py` (migration a0010)
- `deploy/viveka-api.service` — confirms `--workers 1`
- APScheduler docs for `AsyncIOScheduler` (preferred for async FastAPI)

**Outputs:**
- `backend/app/scheduler.py`:
  - `create_scheduler() -> AsyncIOScheduler`
  - CronTrigger: `hour=21, minute=0, timezone="Asia/Kolkata"`
  - Job: `run_daily_briefing_job(date=None)` — `date=None` means today
- `backend/app/main.py` — updated lifespan handler to start/stop scheduler
- Unit tests: mock `is_trading_day`; verify skip is logged correctly on non-trading day; verify `job_executions` row is written on run and on skip.

**Acceptance Criteria:**
- Given 21:00 IST on a trading day, then `run_daily_briefing_job` is triggered.
- Given 21:00 IST on a holiday, then the job exits, a `job_executions` row is written with `status='skipped'` and `skip_reason='holiday'`, and nothing else runs.
- Given a transient DB exception during the job, then the job retries up to 2 times and logs `status='failed'` after exhausting retries.
- Given the FastAPI app restarts mid-day, then the scheduler re-registers and will fire at 21:00 that day if it hasn't already (APScheduler's `coalesce=True` or equivalent).
- APScheduler uses `AsyncIOScheduler`, not `BackgroundScheduler`, to remain compatible with async SQLAlchemy sessions.

---

#### T-BHM-02: Job Pipeline Orchestration

**Owner:** Bhima  
**Depends on:** T-BHM-01, T-VYS-04, T-VIS-02

**Description:** Implement the orchestration function that the scheduler calls. This function sequences: (1) staleness check, (2) OHLCV fetch, (3) news fetch, (4) sector ranking, (5) trigger analysis, (6) report assembly, (7) report persistence. Each step is invoked from its respective module. Bhima owns the orchestration logic, not the step implementations.

**Outputs:**
- `backend/app/jobs/daily_briefing.py`:
  - `run_daily_briefing(date: date, session) -> BriefingResult`
  - `BriefingResult` — dataclass: `report_id`, `date`, `rankings_price`, `rankings_volume`, `triggers`, `skipped: bool`, `skip_reason: str | None`

**Acceptance Criteria:**
- Given all upstream steps succeed, then a `BriefingResult` is returned with non-empty rankings and the result is persisted to `reports`.
- Given staleness check returns `is_fresh=False`, then the function returns `BriefingResult(skipped=True, skip_reason=..., report_id=None)` and nothing is written to `reports`.
- Given trigger analysis fails (all LLM calls fail), then rankings are still published — the briefing degrades gracefully, not silently.
- Every exception is caught at the orchestration level, logged with full traceback, and written to `job_executions` as `status='failed'`.

---

#### T-BHM-03: Manual Re-run CLI

**Owner:** Bhima  
**Depends on:** T-BHM-02

**Description:** A developer command to re-run the briefing for any past date without waiting for 21:00. Must be idempotent: running for a date that already has a report overwrites it, does not create a duplicate.

**Outputs:**
- `backend/app/jobs/run_briefing.py` — runnable as `python -m app.jobs.run_briefing --date 2026-09-25`
- If no `--date` flag, defaults to today.
- Prints result summary to stdout (report ID, skip reason if skipped, error if failed).

**Acceptance Criteria:**
- Given `--date 2026-09-25` (a known trading day with data), then a report is generated and `reports` has exactly one row for `2026-09-25` (overwritten if run twice).
- Given `--date 2026-09-27` (a Saturday), then output is `"Skipped: non-trading day"` and no report is written.
- Given `--date` with an invalid format, then a clear error message is printed and the script exits 1.

---

#### T-BHM-05: Report Persistence + REST API (REQ-031)

**Owner:** Bhima  
**Depends on:** T-BHM-02, migration a0009 (`reports` table)

**Description:** Persist the assembled briefing to the `reports` table as JSONB. Expose two REST endpoints for Arjun's dashboard. Reports must include embedded provenance: which sector map version was active, which model was used per trigger, and the news URLs used.

**Outputs:**
- `backend/app/api/v1/reports.py`:
  - `GET /api/v1/reports` — list of reports (paginated, most-recent first). Response: `[{id, report_type, report_date, generated_at, status}]`.
  - `GET /api/v1/reports/{id}` — full report JSONB. Response includes `price_rankings`, `volume_rankings`, `trigger_summaries`, `provenance`.
  - `GET /api/v1/reports/latest?type=daily_briefing` — latest report of a type (convenience endpoint for dashboard).
- Authentication: all three endpoints require a valid session (use `require_auth` dep from Phase 0's `backend/app/api/deps.py`).
- Unit tests: verify list pagination, verify 404 on unknown ID, verify auth check.

**Report JSONB structure (minimum):**
```json
{
  "report_type": "daily_briefing",
  "report_date": "2026-09-25",
  "generated_at": "2026-09-25T21:03:12+05:30",
  "sector_map_version": "v1",
  "price_rankings": [
    {
      "rank": 1,
      "sector_name": "Banking",
      "sector_score": 2.34,
      "top_constituent": {"ticker": "HDFCBANK", "score": 4.1},
      "constituent_count": 12
    }
  ],
  "volume_rankings": [...],
  "trigger_summaries": [
    {
      "ticker": "HDFCBANK",
      "sector": "Banking",
      "summary": "HDFC Bank reported Q2 net profit...",
      "news_urls": ["https://..."],
      "model": "claude-haiku-4-5-20251001",
      "tokens_used": 312
    }
  ],
  "skipped": false,
  "skip_reason": null
}
```

**Acceptance Criteria:**
- Given a completed briefing, when `GET /api/v1/reports/latest?type=daily_briefing` is called with a valid session, then the most recent `daily_briefing` report is returned with its full JSONB.
- Given no report exists yet, then `GET /api/v1/reports/latest?type=daily_briefing` returns `404`.
- Given an unauthenticated request, then all three endpoints return `401`.
- JSONB structure includes `sector_map_version`, `trigger_summaries[].news_urls`, and `trigger_summaries[].model` — provenance is non-negotiable (ADR-004 principle extended to reports).

---

### 5.4 Arjun — Dashboard UI

Arjun can begin T-ARJ-01 in parallel with the data/backend work. T-ARJ-02 is gated on T-BHM-05 being complete, but Arjun should build the component structure against mock API responses first, then wire to live endpoints.

---

#### T-ARJ-01: Web App Shell (WEB-001)

**Owner:** Arjun  
**Depends on:** Phase 0 frontend scaffold (already in place), design tokens (`tokens.css`)

**Description:** Flesh out the authenticated app shell. The Phase 0 scaffold has `app/(app)/layout.tsx` as a stub. This task implements the full authenticated layout: persistent navigation, responsive sidebar or top-nav, auth guard (redirects to `/login` if no valid session), and the empty state for when no report exists yet.

**Note:** The login flow from Phase 0 authenticates against the Phase 0 auth API. Arjun must verify the session cookie is forwarded correctly in `lib/api.ts` before the dashboard API calls will work.

**Inputs:**
- `frontend/styles/tokens.css` — design tokens
- `frontend/app/(app)/layout.tsx` — existing stub
- `frontend/lib/api.ts` — typed fetch wrapper from Phase 0

**Outputs:**
- `frontend/app/(app)/layout.tsx` — full authenticated layout with nav and auth guard
- `frontend/components/layout/AppNav.tsx` — navigation component (links: Dashboard, Reports, Watchlist)
- `frontend/app/(app)/dashboard/page.tsx` — updated from stub to empty-state-aware component
- TypeScript: zero TS errors; ESLint: zero warnings

**Acceptance Criteria:**
- Given an unauthenticated user navigating to `/dashboard`, then they are redirected to `/login`.
- Given an authenticated user, then the app shell renders with navigation visible at all viewport widths ≥ 360px.
- Given the ThemeToggle component from Phase 0, then it is present and functional in the app shell nav.
- Zero console errors in Chrome DevTools on page load.

---

#### T-ARJ-02: Dashboard — Sector Rankings (WEB-005)

**Owner:** Arjun  
**Depends on:** T-ARJ-01, T-BHM-05

**Description:** Build the dashboard page that displays the daily briefing. Two tabs: Price Rankings and Volume Rankings. Each tab shows up to 3 sectors, expandable to show constituent stocks. For expanded sectors, trigger summaries are shown per flagged stock. Empty state when no report is available for today.

Build against mock data first; wire to `GET /api/v1/reports/latest?type=daily_briefing` once T-BHM-05 is available.

**Inputs:**
- T-BHM-05 API contract (report JSONB structure from §5.3 T-BHM-05)
- Design tokens and typography from Phase 0
- `frontend/lib/api.ts`

**Outputs:**
- `frontend/app/(app)/dashboard/page.tsx` — full dashboard implementation
- `frontend/components/dashboard/RankingTabs.tsx` — Price / Volume tab switcher
- `frontend/components/dashboard/SectorCard.tsx` — collapsed and expanded states
- `frontend/components/dashboard/TriggerSummary.tsx` — trigger text + news source links
- `frontend/components/dashboard/EmptyState.tsx` — "No briefing available for today" state
- TypeScript: zero TS errors; ESLint: zero warnings

**Acceptance Criteria:**
- Given a live report, when the dashboard loads, then both ranking tabs render with up to 3 sectors each.
- Given a sector card in its collapsed state, when clicked, then it expands to show constituent stocks and trigger summaries.
- Given a trigger summary with `news_urls`, then each URL is rendered as an accessible link (correct `href`, opens new tab, `rel="noopener noreferrer"`).
- Given a trigger summary of `"No identifiable trigger found for this move."`, then no news links are shown and the text is rendered in a visually subdued style (not identical to a real trigger).
- Given no report available, then the empty state is shown with a last-updated timestamp if available.
- Given a 360px viewport (mobile), then no horizontal scroll occurs and all text is legible.
- Given dark mode (data-theme="dark"), then all text meets WCAG AA contrast. (Pre-verification before Sahadeva tests; no Phase 6 audit required for Phase 1 sign-off, but obvious failures should be fixed.)
- Zero console errors in Chrome DevTools.

---

### 5.5 Nakula — Deployment

---

#### T-NAK-01: APScheduler Deployment + Caddy Update

**Owner:** Nakula  
**Depends on:** T-BHM-01, OCI instance provisioned by Atharva (external dependency)

**Description:** Verify the scheduler works correctly in the deployed environment. Confirm 21:00 IST timezone is correct on the Oracle Cloud instance (Asia/Kolkata). Uncomment the Next.js reverse proxy block in Caddyfile. Add log rotation (deferred from Phase 0). Verify `alembic upgrade head` runs cleanly on the live database.

**Inputs:**
- `deploy/Caddyfile` — Next.js block currently commented out
- `deploy/viveka-api.service` — `--workers 1` confirmed
- `deploy/runbook.md`

**Outputs:**
- Updated `deploy/Caddyfile` — Next.js reverse proxy block uncommented
- Updated `deploy/runbook.md` — Phase 1 deployment steps added (scheduler verification, log rotation, cert expiry check)
- Logrotate config or equivalent for `viveka-api` logs

**Acceptance Criteria:**
- Given the deployed service, when `date` is run on the Oracle Cloud instance, then the timezone displays `Asia/Kolkata` (IST).
- Given `alembic upgrade head` run on the live database, then all 11 (or 12 if T-BHM-04 chose Option B) migrations complete without error.
- Given the Caddyfile update, then `https://<domain>/` routes to Next.js and `https://<domain>/api/` routes to FastAPI.
- Given the service restarts (systemd restart), then the APScheduler fires the next scheduled 21:00 IST job without manual intervention.

**Blocked by:** OCI instance provisioning. Nakula cannot proceed until Atharva provisions the instance. This does not block T-BHM-01–T-BHM-05 or T-ARJ-01–T-ARJ-02.

---

### 5.6 Sahadeva — Phase 1 QA Gate

---

#### T-SAD-01: Phase 1 QA

**Owner:** Sahadeva  
**Depends on:** All T-BHM, T-ARJ tasks complete; T-NAK-01 complete (for live end-to-end)

**Sahadeva must receive a formal handoff from Bhima and Arjun before beginning.**

**Handoff from Bhima must include:**
- All backend tests passing (`pytest tests/ -v` exit 0)
- Manual re-run command working
- API endpoints documented (routes, request/response schema, auth requirement)
- Known limitations noted

**Handoff from Arjun must include:**
- `npm run lint` and `tsc --noEmit` both exit 0
- Dev server starts and dashboard renders with mock data
- Instructions for connecting to live backend

**QA scope:**
- All 8 Phase 1 exit criteria (see §6)
- Simulated trading day: run manual re-run for a past trading date with real or seeded data; verify report appears in dashboard
- Simulated holiday: run manual re-run for a known holiday; verify skip logged, no report created
- Weekend test: run manual re-run for a Saturday; verify skip
- Empty-data test: truncate `price_data` and run; verify staleness check aborts job
- LLM cost guard: seed `llm_usage` at ₹460 for current month; run trigger analysis; verify it is skipped
- Dashboard responsive test: 360px, 768px, 1280px viewports
- Auth guard: unauthenticated requests to all 3 API endpoints return 401; direct navigation to `/dashboard` redirects to `/login`
- Dark mode: dashboard renders without obvious contrast failures

**QA outputs:**
- `docs/qa/QA-RPT-20261XXX-001.md` — test report
- INBOX.md entry with GO / GO WITH RISKS / NO GO recommendation
- Handoffs to Bhima/Arjun for any defects found

---

## 6. Phase 1 Exit Criteria

From IMP-20260923-001 §Phase 1, with clarifications:

| # | Criterion | Owner | Verifier |
|---|---|---|---|
| E1 | Daily briefing delivered at 21:00 IST on 3 consecutive simulated trading days | Bhima (scheduler) | Sahadeva |
| E2 | Briefing skipped on weekend and holiday; skip logged; no report created | Bhima | Sahadeva |
| E3 | Two independent rankings produced: price (median) and volume (20-day ratio) | Vishwakarma | Sahadeva |
| E4 | Strongest single contributor shown per sector alongside sector-level figure | Vishwakarma | Sahadeva |
| E5 | Trigger summary (2–4 sentences) produced for each flagged stock | Vishwakarma | Sahadeva |
| E6 | Manual re-run command available, tested, idempotent | Bhima | Sahadeva |
| E7 | Dashboard renders both rankings; each sector expandable to constituents with trigger summary | Arjun | Sahadeva |
| E8 | Empty-data detection (REQ-036) fires and aborts job without generating a report | Vyasa | Sahadeva |

**All 8 must PASS for Sahadeva GO. Any P0 defect is a NO GO.**

---

## 7. Execution Order and Parallelism

The following streams can proceed in parallel once their pre-conditions are met:

```
STREAM A (Vyasa)
  T-VYS-02 ──┐
  T-VYS-03 ──┤── T-VYS-04 ──┐
  T-VYS-01 ──┘               │
  T-BHM-04 ─── T-VYS-05 ────┤
                              │
STREAM B (Vishwakarma)        │
  [wait T-VYS-01, T-VYS-02]──┤
  T-VIS-01 ── [Narada] ──────┤
  T-VIS-02 ──────────────────┘── T-BHM-02 ── T-BHM-03
                                            │
STREAM C (Bhima)                            │
  T-BHM-04 (early, unblocked)              T-BHM-05
  T-BHM-01 [wait T-VYS-03]
  
STREAM D (Arjun)                           T-ARJ-01 ── T-ARJ-02 [wait T-BHM-05]
  (T-ARJ-01 starts immediately)

STREAM E (Nakula)
  T-NAK-01 [wait T-BHM-01 + OCI instance]

STREAM F (Sahadeva)
  T-SAD-01 [wait all above]
```

**First agent to invoke:** Bhima (T-BHM-04 schema decision) in parallel with Sanjaya advisory consultation (before T-VYS-05). Arjun can also start T-ARJ-01 immediately.

**Critical path:** T-VYS-01+02+03 → T-VYS-04+T-VIS-01 → [Narada] → T-VIS-02+T-BHM-01 → T-BHM-02 → T-BHM-05 → T-ARJ-02 → T-SAD-01.

---

## 8. Handoff Contracts

| From | To | Handoff contains |
|---|---|---|
| Vyasa (T-VYS-01–04) | Vishwakarma | DataFetcher working for NSE, price_data populated for ≥5 tickers; is_trading_day utility tested; T-VYS-04 staleness guard implemented. |
| Vyasa (T-VYS-05) | Vishwakarma | News fetcher working; items available in DB (Option B) or fetcher callable (Option A). Confirm output format. |
| Sanjaya | Vyasa | Exchange API endpoints, rate limits, known parsing quirks for NSE/BSE announcements. |
| Vishwakarma (T-VIS-01) | Narada | Algorithm description: median formula, volume ratio formula, edge cases handled. |
| Narada | Vishwakarma | Written validation: confirmed sound / concern found. INBOX.md entry. |
| Vyasa + Vishwakarma | Bhima | DataFetcher, ranking functions, trigger analysis all importable and tested. Bhima wires them into the scheduler. |
| Bhima (T-BHM-05) | Arjun | API routes documented: path, method, request params, response schema, auth requirement. Dev server running. |
| Bhima | Sahadeva | Backend handoff per §5.6 |
| Arjun | Sahadeva | Frontend handoff per §5.6 |
| Sahadeva | Atharva / Nakula | QA report, GO/NO GO recommendation, defect list |

---

## 9. Risk Register — Phase 1 Specific

| ID | Risk | Likelihood | Impact | Owner | Mitigation |
|---|---|---|---|---|---|
| R-P1-01 | yfinance returns empty or malformed data for NSE tickers | High | High | Vyasa | T-VYS-04 staleness guard catches this and aborts job gracefully. Log the failure. Do not generate a partial report. |
| R-P1-02 | Sector classification inconsistency (NIFTY sector map incomplete or mismatched with yfinance symbols) | High | High | Vyasa | Use NIFTY sectoral indices as source of truth. Document each sector's constituent list. Accept that some tickers may not match yfinance symbol format — handle symbol mapping explicitly in T-VYS-02. |
| R-P1-03 | APScheduler misses 21:00 job on service restart | Medium | Medium | Nakula | APScheduler `coalesce=True` setting. Nakula verifies in T-NAK-01. Manual re-run (T-BHM-03) is the recovery path. |
| R-P1-04 | NSE announcement API rate-limited or unavailable | Medium | Medium | Vyasa | T-VYS-05: retry with backoff; degrade gracefully (rankings published without trigger summaries). |
| R-P1-05 | LLM cost overshoot if trigger analysis uses wrong model | Medium | High | Vishwakarma | T-VIS-02: `MODELS["trigger_analysis"]` defaults to Haiku. Cost guard in LLMClient enforced before every call. |
| R-P1-06 | OCI instance not provisioned before Phase 1 live test | High | Low (code-only) / High (E2E) | Atharva | Phase 1 code can be developed and tested offline. E2E test (E1, E2) requires live instance — if OCI provisioning is delayed, Sahadeva may issue "GO WITH RISKS" and defer E1/E2 to post-OCI verification. |
| R-P1-07 | Sector ranking produces identical results for price and volume (low signal) | Low | Low | Narada | Narada review catches this at T-VIS-01 review stage. |

---

## 10. Timeline Estimate

Estimate from IMP-20260923-001: ~3 weeks with 20% buffer applied.

| Stream | Tasks | Estimate (effort days) | Notes |
|---|---|---|---|
| Vyasa data layer | T-VYS-01–05 | 5–7 days | yfinance symbol mapping is the biggest unknown |
| Vishwakarma + Narada | T-VIS-01–02 + review | 3–4 days | Depends on Vyasa stream |
| Bhima backend | T-BHM-01–05 | 4–5 days | T-BHM-01 can start after T-VYS-03 |
| Arjun frontend | T-ARJ-01–02 | 3–4 days | T-ARJ-01 starts immediately |
| Nakula | T-NAK-01 | 1 day (+ OCI wait) | Blocked on Atharva provisioning |
| Sahadeva QA | T-SAD-01 | 1–2 days | Gated on all above |
| **Total** | | **~17–22 effort days** | Calendar duration ~3 weeks with 20% buffer |

**External dependency (critical):** OCI instance provisioning by Atharva. Must happen before T-NAK-01 and live E2E test.

---

## 11. Decisions Required Before Work Starts

| # | Decision | Owner | Deadline |
|---|---|---|---|
| D1 | News storage: Option A (transient) vs Option B (persistent `news_items` table) | Bhima | Before T-VYS-05 begins |
| D2 | Where is sector `map_version` stored (per company_sectors row vs separate table vs static on sectors) | Vyasa | Before T-VYS-02 begins |
| D3 | Which layer computes `volume_20d_avg` — DataFetcher or ranking layer | Vyasa + Vishwakarma | Before T-VYS-01 is finalized |
| D4 | USD→INR rate for LLM cost computation — hardcoded config, live API, or fixed monthly rate | Vishwakarma + Bhima | Before T-VIS-02 begins |
| D5 | `SECTOR_MIN_CONSTITUENTS` default value | Vishwakarma | Before T-VIS-01 begins |

---

## 12. First Actions

In order of priority:

1. **Bhima** — Make D1 (news storage decision). Document in INBOX.md. If Option B, write migration a0012.
2. **Sanjaya** — (invoked by Atharva) Provide NSE/BSE announcement API patterns to Vyasa.
3. **Arjun** — Begin T-ARJ-01 (web app shell). No backend dependency. Design tokens are ready.
4. **Vyasa** — Begin T-VYS-01, T-VYS-02, T-VYS-03 in parallel (once D2 and D3 are resolved with Vishwakarma).
5. **Bhima** — Begin T-BHM-01 as soon as T-VYS-03 (trading calendar) is available.
6. **Atharva** — Provision Oracle Cloud instance (external action required to unblock T-NAK-01 and live E2E).

---

*EXP-20260926-001 · v1.0 · Krishna (PM) · Active · 2026-09-26*
