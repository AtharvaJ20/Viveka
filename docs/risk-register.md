━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Document:    Risk Register — Personal Stock Research & Monitoring Agent
ID:          RSK-20260923-001
Author:      Krishna (PM) · Yudhishthira (Product)
Owner:       Atharva
Date:        2026-09-23
Version:     v1.1
Status:      Active
References:  PRD-20260909-001 v2.0, IMP-20260923-001, EXP-20260926-001
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Risk Register — Personal Stock Research & Monitoring Agent

Reviewed: 2026-09-28 (Phase 1 mid-sprint — tasks T-VYS-01–05, T-VIS-01–02, T-ARJ-01, T-BHM-01–04 complete)
Next review: Phase 1 QA gate (T-SAD-01)

---

## Risk Matrix

| ID | Risk | Phase | Likelihood | Impact | Score | Owner | Response |
|---|---|---|---|---|---|---|---|
| R-001 | yfinance unreliable for BSE/SME tickers | 1+ | High | High | 9 | Vyasa | Mitigate |
| R-002 | Indian earnings PPTs are scanned → high unread rate | 2+ | Medium | High | 6 | Vyasa | Accept + surface |
| R-003 | APScheduler misses 21:00 IST on server restart | 1+ | Medium | Medium | 4 | Nakula | Mitigate |
| R-004 | Sector classification inconsistent across providers | 1 | High | High | 9 | Vyasa | Avoid |
| R-005 | Cost ceiling breached by accidental bulk deep dive | 4 | Low | High | 3 | Nakula | Mitigate |
| R-006 | NSE holiday calendar stale / unscheduled closure | 1+ | Medium | Medium | 4 | Vyasa | Mitigate |
| R-007 | Document backfill accidentally triggers at scale | 2 | Low | High | 3 | Bhima | Avoid |
| R-008 | Phase 2 document parsing quality worse than expected | 2 | Medium | Medium | 4 | Vyasa | Accept + REQ-011E |
| R-009 | PostgreSQL concurrent read issues on single instance | 0 | Low | Low | 1 | Bhima | Accept |
| R-010 | Oracle Cloud Always Free tier availability SLA | 1+ | Low | High | 3 | Nakula | Accept |
| R-P1-01 | yfinance returns empty or malformed data for NSE tickers | 1 | High | High | 9 | Vyasa | Mitigate |
| R-P1-02 | Sector classification inconsistency (NIFTY map vs yfinance symbols) | 1 | High | High | 9 | Vyasa | Avoid |
| R-P1-03 | APScheduler misses 21:00 job on service restart | 1 | Medium | Medium | 4 | Nakula | Mitigate |
| R-P1-04 | NSE announcement API rate-limited or unavailable | 1 | Medium | Medium | 4 | Vyasa | Mitigate |
| R-P1-05 | LLM cost overshoot if trigger analysis uses wrong model | 1 | Medium | High | 6 | Vishwakarma | Mitigate |
| R-P1-06 | OCI instance not provisioned before Phase 1 live test | 1 | High | Low/High | — | Atharva | Accept |
| R-P1-07 | Sector ranking produces identical results for price and volume | 1 | Low | Low | 1 | Narada | Accept |
| R-P1-08 | job_executions CHECK constraint mismatch ('success' vs 'completed') | 1 | — | — | — | Bhima | **CLOSED** |

*Score = Likelihood × Impact (H=3, M=2, L=1)*

---

## Detailed Risk Entries

---

### R-001 — yfinance Unreliable for BSE/SME Tickers

**Description:** yfinance coverage degrades significantly for BSE-only and SME-listed
names. Ticker resolution, OHLCV completeness, and corporate action data are all
unreliable for this segment. NSE names are covered well; BSE SME names are not.

**Affected phases:** 1, 2, 5 (BSE/SME section is Phase 5 but data gaps surface in Phase 1)

**Likelihood:** High — known limitation of yfinance
**Impact:** High — BSE and SME coverage is an explicit goal (REQ-017). A broken data
source produces silent gaps in the briefing.

**Mitigation:**
- Design a `DataFetcher` abstraction from Phase 0 (Vyasa) that routes by exchange.
- Primary: `yfinance` for NSE tickers.
- Fallback: Direct BSE Bhavcopy daily CSV download for BSE tickers (free, official,
  reliable — published at bhavdata.bseindia.com after market close).
- `nsepython` for NSE corporate announcements and actions.
- Fallback must be designed into the architecture even if not built in Phase 1.
- Phase 1 exit criteria must explicitly test a BSE-only ticker.

**Owner:** Vyasa  
**Status:** Open

---

### R-002 — Indian Earnings PPTs Are Scanned → High Unread Rate

**Description:** Many Indian companies, particularly smallcaps and SME-listed names,
publish earnings presentations as scanned PDFs rather than native PPTX or text-layer PDFs.
REQ-011C prohibits OCR (text-only parsing only in v1.0). REQ-011G allows an alternate
source lookup (other exchange, IR page) before declaring unread. REQ-011F surfaces all
unread documents with source links.

**Affected phases:** 2+

**Likelihood:** Medium — prevalent in the SME/smallcap segment the system specifically
targets
**Impact:** High — a research report on a company where the earnings PPT is unread is
materially incomplete. If not surfaced prominently, the report reads as complete when
it is not.

**Mitigation (accepted risk, not fully mitigable in v1.0):**
- REQ-011F is the safeguard — every unread document is surfaced with source URL for
  manual reading. This is non-negotiable and must ship in Phase 2.
- REQ-011G alternate source resolution catches most cases for well-documented companies.
- REQ-011E coverage logging will quantify the rate in production — if materially
  disruptive, it triggers the Section 7.1 OCR adoption decision.
- User must be explicitly told at Phase 2 launch: deep dives on SME names may have
  unread presentations. The unread section is there for a reason.

**Owner:** Vyasa (document parsing), Ganesha (research quality acknowledgement)
**Status:** Accepted — surfaced via REQ-011F

---

### R-003 — APScheduler Misses 21:00 IST on Server Restart

**Description:** APScheduler on a single Oracle Cloud instance loses scheduled jobs
on process restart. A server update, OOM kill, or crash at 20:55 IST means no briefing.

**Affected phases:** 1+

**Likelihood:** Medium — server restarts are infrequent but not rare on a personal instance
**Impact:** Medium — a missed briefing is an inconvenience (PRD §5.2), not an incident.
95% delivery target allows ~1 miss per month.

**Mitigation:**
- APScheduler persists job state to PostgreSQL (not in-memory store) — jobs survive restarts.
- Manual re-run command ships in Phase 1 (REQ-030 acceptance criterion — mandatory).
- Nakula sets up a watchdog (systemd service with `Restart=always`) for the Python process.
- Consider: a lightweight cron-level check that verifies the briefing was published by
  21:30 IST and alerts if not (Phase 5 monitoring extension).

**Owner:** Nakula
**Status:** Open

---

### R-004 — Sector Classification Inconsistent Across Providers

**Description:** yfinance, nsepython, and other providers return inconsistent sector/
industry labels for the same stock — especially for smallcaps and SME names. A live
sector read produces different results on different days. Week-on-week comparison becomes
meaningless if the mapping changes silently.

**Affected phases:** 1+ (REQ-037 is a Phase 1 requirement)

**Likelihood:** High — verified as a known issue with Indian equity data providers
**Impact:** High — the entire sector ranking system depends on a stable, consistent mapping

**Avoidance (not just mitigation):**
- REQ-037 mandates a versioned local sector-to-stock mapping. This is the only correct
  response — never read live from a provider.
- Vyasa seeds the mapping from exchange industry classification (NSE industry list,
  BSE industry list) in Phase 1, stored in PostgreSQL with a version and effective date.
- A reclassification is applied explicitly, with the old and new labels both recorded.
- The mapping seeding exercise must be completed and reviewed before Phase 1 can
  produce a valid briefing. This is a Phase 1 prerequisite, not a Phase 1 deliverable.

**Owner:** Vyasa
**Status:** Open — seeding exercise must complete before Phase 1 exit

---

### R-005 — Cost Ceiling Breached by Accidental Bulk Deep Dive

**Description:** A single bulk request (e.g., deep dive on all 50 watchlist stocks) or
a document backfill misconfiguration could trigger enough Sonnet 4.6 calls to breach
the ₹500/month ceiling in a single job.

**Affected phases:** 4+ (deep research pipeline)

**Likelihood:** Low — this requires an explicit user action or a configuration error
**Impact:** High — breaching ₹500 is defined as a defect (PRD §5.3), not an overage

**Mitigation:**
- REQ-034 enforcement must ship before Phase 4 opens (hard gate in the implementation plan).
- Deep dive endpoint enforces per-request cost estimate before execution (not just after).
- Bulk or wildcard deep dive requests are prohibited at the API level.
- Document backfill is explicitly shallow (4 quarters for docs vs 8 quarters for financials)
  and must not be triggered automatically on watchlist add.
- Cost dashboard (WEB-012) gives the user visibility before the ceiling is approached.

**Owner:** Nakula (enforcement), Chitragupta (monitoring)
**Status:** Open — REQ-034 is a Phase 5 requirement; must be moved earlier if Phase 4 opens first

---

### R-006 — NSE Holiday Calendar Stale / Unscheduled Closure

**Description:** Exchanges declare unscheduled closures that are not on the published
holiday list (e.g., natural disaster, exchange system failure). A system that trusts the
calendar blindly generates a confident report from an empty trading day.

**Affected phases:** 1+ (REQ-036)

**Likelihood:** Medium — rare but happens (2–3 unscheduled closures per year on Indian exchanges)
**Impact:** Medium — a briefing generated from zero data would be wrong and confidently delivered

**Mitigation:**
- REQ-036 is the defence: if market data ingestion returns no data for a date the calendar
  says is a trading day, the job aborts and notifies the user.
- Calendar refresh is monthly (REQ-035 config: `TRADING_CALENDAR_REFRESH_DAYS = 30`).
- Fallback to cached calendar with warning when the refresh fetch fails.
- The calendar-vs-data check (REQ-036) is a Phase 1 requirement and must ship with the
  first scheduled briefing.

**Owner:** Vyasa
**Status:** Open

---

### R-007 — Document Backfill Accidentally Triggers at Scale

**Description:** A coding error or misconfiguration could trigger full document backfill
(parsing + LLM summarisation) for all historical quarters when a company is added to the
watchlist. At Sonnet 4.6 rates, 12 quarters × 2 documents × ~25K tokens per summarisation
= ~₹250 per company. Add 5 companies = ₹1,250. Ceiling breached.

**Affected phases:** 2, 4

**Likelihood:** Low — but the consequence is severe
**Impact:** High — would breach the ₹500 ceiling immediately

**Avoidance:**
- REQ-023 explicitly splits financial and document backfill depths.
- Adding a company to the watchlist must never trigger any parsing job.
- Financials backfill (structured, cheap): 8 quarters, runs automatically.
- Document backfill (expensive): 4 quarters, runs only when a deep dive is explicitly
  requested for those quarters.
- Older documents are indexed (URL + metadata only) and fetched only on individual request.
- Code review gate: Bhima must demonstrate that watchlist add triggers financials fetch only,
  with a test that confirms no LLM calls are made on watchlist add.

**Owner:** Bhima (persistence layer)
**Status:** Open

---

### R-008 — Document Parsing Quality Worse Than Expected

**Description:** The REQ-011E coverage logging requirement exists precisely because the
true fraction of slides that yield extractable text on Indian earnings presentations is
unknown upfront. If, for example, 40% of slides in a typical deck are image-only and
carry figures not available in the chart XML, the deep dive reports will have material
gaps that REQ-011E will quantify but not fix.

**Affected phases:** 2+

**Likelihood:** Medium
**Impact:** Medium — mitigated by REQ-011F surfacing, but the research quality suffers

**Acceptance:**
- This is a known, accepted limitation of text-only parsing (PRD §7.1 rationale).
- REQ-011E logs are the early warning system. If the data shows systematic gaps,
  it triggers the Section 7.1 OCR adoption discussion — not before.
- Phase 2 exit criteria must include a review of REQ-011E data from at least 5 decks
  before declaring Phase 2 complete.

**Owner:** Vyasa (logging), Ganesha (research quality judgment)
**Status:** Accepted

---

---

### R-P1-01 — yfinance Returns Empty or Malformed Data for NSE Tickers

**Description:** During Phase 1 data ingestion, yfinance may return partial, empty, or
malformed OHLCV responses for NSE tickers. This produces a misleading briefing or causes
the pipeline to crash mid-run.

**Affected phases:** 1
**Likelihood:** High — yfinance coverage inconsistency is documented
**Impact:** High — partial data silently poisons sector rankings

**Mitigation:**
- T-VYS-04 (staleness guard): if `price_data` has fewer than `MIN_ROWS=50` rows for the
  trading day, `check_data_freshness` returns `is_fresh=False` and the pipeline aborts
  before any ranking computation. No partial report is published.
- Empty rows per ticker are skipped at the fetcher level (logged as warning, not error).

**Owner:** Vyasa  
**Status:** Mitigated — T-VYS-04 implemented and tested ✓

---

### R-P1-02 — Sector Classification Inconsistency

**Description:** yfinance symbol format may not match the NIFTY sectoral index constituent
tickers exactly (e.g., `HDFCBANK.NS` vs `HDFCBANK`). If symbol mapping is wrong, companies
are silently excluded from rankings.

**Affected phases:** 1
**Likelihood:** High — known Indian equity data provider inconsistency
**Impact:** High — missing companies distort sector-level medians

**Mitigation (avoidance):**
- T-VYS-02 uses bare NSE ticker (no `.NS` suffix) as canonical symbol throughout — the
  `sector_map_v1.yaml` seeding exercise uses the same bare ticker format that `price_data`
  stores, eliminating symbol-format divergence.
- Sanjaya confirmed canonical ticker = `companies.ticker_nse` (bare NSE symbol). T-VYS-05
  uses the same convention. No cross-format lookup at runtime.

**Owner:** Vyasa  
**Status:** Avoided — canonical ticker convention enforced in T-VYS-02 ✓

---

### R-P1-03 — APScheduler Misses 21:00 Job on Service Restart

**Description:** A server restart between 21:00 IST and the job's execution window could
cause APScheduler to miss the scheduled fire. The briefing is not generated.

**Affected phases:** 1+
**Likelihood:** Medium — restarts are infrequent but possible
**Impact:** Medium — one missed briefing; 95% delivery target allows ~1 miss/month

**Mitigation:**
- APScheduler configured with `coalesce=True` and `misfire_grace_time=3600` (T-BHM-01).
  If the process restarts within 1 hour of the missed fire, the job executes immediately.
- T-BHM-03 (manual re-run CLI) is the human recovery path.
- T-NAK-01 verifies systemd `Restart=always` on Oracle Cloud instance.

**Owner:** Nakula  
**Status:** Mitigated — coalesce + misfire grace implemented in T-BHM-01 ✓

---

### R-P1-04 — NSE Announcement API Rate-Limited or Unavailable

**Description:** NSE runs Cloudflare anti-bot protection. Session warm-up may fail or
be rate-limited, causing news ingestion to return empty results.

**Affected phases:** 1
**Likelihood:** Medium — Sanjaya flagged NSE session management as the highest-risk piece
**Impact:** Medium — trigger analysis proceeds with whatever news was fetched; rankings
are unaffected (they are news-free). Partial news is acceptable; job abort is not.

**Mitigation:**
- T-VYS-05 makes NSE failure non-fatal: empty news result is valid input for trigger analysis.
- BSE XML feed is the fallback source.
- Retry: exponential backoff on HTTP 429/503; failure logged, job continues.

**Owner:** Vyasa  
**Status:** Mitigated — non-fatal failure path implemented in T-VYS-05 ✓

---

### R-P1-05 — LLM Cost Overshoot if Trigger Analysis Uses Wrong Model

**Description:** If `MODELS["trigger_analysis"]` is misconfigured to use Sonnet or Opus
instead of Haiku, a single daily run could cost 10–30× more than expected and approach
the monthly ceiling within days.

**Affected phases:** 1
**Likelihood:** Medium — misconfiguration is possible on first deploy
**Impact:** High — could breach ₹500 ceiling quickly

**Mitigation:**
- T-VIS-02: `MODELS["trigger_analysis"]` defaults to `"claude-haiku-4-5-20251001"` in config.
- LLMClient cost guard checks `llm_usage` before every call; aborts if spend ≥ ₹450 (90%
  of ₹500 ceiling). Rankings are still published even when trigger analysis is skipped.

**Owner:** Vishwakarma  
**Status:** Mitigated — cost guard implemented in T-VIS-02 ✓

---

### R-P1-06 — OCI Instance Not Provisioned Before Phase 1 Live Test

**Description:** All Phase 1 code can be developed and tested offline. But exit criteria
E1 (3 consecutive simulated trading days) and E2 (live holiday skip) require a running
Oracle Cloud instance. If provisioning is delayed at QA time, Sahadeva cannot complete
the full Phase 1 QA gate.

**Affected phases:** 1
**Likelihood:** High (provisioning not yet done) / Impact: Low (code work) / High (E2E test)
**Impact:** Blocks live E2E verification only

**Acceptance:**
- Phase 1 code development proceeds without OCI instance.
- If OCI provisioning is delayed at Sahadeva's QA gate, Sahadeva may issue "GO WITH RISKS"
  deferring E1/E2 to post-provisioning verification.

**Owner:** Atharva (external action)  
**Status:** Open — instance not yet provisioned (BLOCKED: Atharva)

---

### R-P1-07 — Sector Ranking Produces Identical Results for Price and Volume

**Description:** On low-volatility days, the top sectors by price change and volume ratio
may be largely identical, reducing the signal value of publishing two rankings.

**Affected phases:** 1
**Likelihood:** Low — volume and price moves are generally uncorrelated
**Impact:** Low — cosmetic; rankings are still correct

**Acceptance:**
- Narada validated in T-VIS-01 review that the two algorithms are independent (price = median
  intraday return; volume = today/20-day-average ratio). Identical top-3 on a given day is
  not a defect — it is a valid signal that the same sectors drove both dimensions.

**Owner:** Narada (monitoring)  
**Status:** Accepted — Narada validation complete ✓

---

### R-P1-08 — job_executions CHECK Constraint Mismatch (CLOSED)

**Description:** Migration a0010 declared `status CHECK (... 'success' ...)` but
`scheduler.py _mark_completed` writes `'completed'`. Every successful live scheduler run
would raise a PostgreSQL CHECK constraint violation, leaving the row stuck in
`status='running'`. Root cause: design-time value ('success') diverged from implementation
('completed'). Tests never caught it because they mock the SQLAlchemy session — no
PostgreSQL enforcement at test time.

**Affected phases:** 1
**Discovery:** T-BHM-04 schema review (2026-09-28)
**Fix:** Migration a0013 (`013_fix_job_executions_status.py`) replaces `'success'` with
`'completed'` in the CHECK constraint. Alembic chain: a0013 is the new head.

**Owner:** Bhima  
**Status:** CLOSED — migration a0013 created 2026-09-28 ✓

---

*RSK-20260923-001 · v1.1 · Atharva · Active · last updated 2026-09-28*
