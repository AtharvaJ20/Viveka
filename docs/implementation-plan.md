━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Document:    Implementation Plan — Personal Stock Research & Monitoring Agent
ID:          IMP-20260923-001
Author:      Krishna (PM)
Owner:       Atharva
Date:        2026-09-23
Version:     v1.0
Status:      Active
References:  PRD-20260909-001 v2.0, BRF-20260923-001
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Implementation Plan — Personal Stock Research & Monitoring Agent

---

## 1. Delivery Philosophy

This is a single-developer, personal-use project. Process overhead must be proportional to
complexity. The rules applied here:

- **One agent per lane** — see agent roster in §3.
- **Phases gate each other** — Phase N does not begin until Phase N-1 has passed Sahadeva QA.
- **No silent scope additions** — every change to phase scope is recorded in INBOX.md.
- **Manual re-run capability ships with every scheduled job** — not as a post-MVP add.

---

## 2. Phase Plan

### Phase 0 — Foundation
**Goal:** Design system, auth shell, and database schema settled before any screen is built.
**Duration:** ~2 weeks
**First user-visible output:** None. This phase exists to prevent rework in all subsequent phases.

| Requirement | Owner Agent | Supporting |
|---|---|---|
| WEB-004 — Auth shell + allowlist | Hanuman (security review), Bhima (implementation) | Arjun |
| WEB-013 — Design system (tokens, dark mode default) | frontend-design → Usha (handoff) | Arjun |
| REQ-032 — PostgreSQL schema, Alembic migrations | Bhima | Mayasura |
| Architecture note — parser interface, provenance model | Mayasura | Bhima |

**Phase 0 exit criteria:**
- [ ] Design token system documented and implemented (colour, typography, spacing, component)
- [ ] Dark mode defined at token level
- [ ] PostgreSQL schema covers all entities needed through Phase 2 (prices, sectors, documents,
      reports, watchlist, users, sessions, cost tracking)
- [ ] Auth shell: session-based login, allowlist enforcement, no open registration path
- [ ] Parser interface defined with `read`/`partial`/`unread` result status contract
- [ ] Every document row has `first_seen_at` and `parser_version` fields
- [ ] Mayasura ADR written for: database choice (PostgreSQL vs SQLite), parser interface
      contract, document provenance model

---

### Phase 1 — Daily Briefing
**Goal:** 21:00 IST daily briefing live, holiday-aware, readable in the dashboard.
**Duration:** ~3 weeks
**First user-visible output:** Daily sector briefing with price/volume rankings and trigger summaries.

| Requirement | Owner Agent | Supporting |
|---|---|---|
| REQ-020 — OHLCV + sector data ingestion | Vyasa | — |
| REQ-037 — Versioned sector classification mapping | Vyasa | Ganesha |
| REQ-035 — Trading calendar (NSE + BSE holidays) | Vyasa | Bhima |
| REQ-036 — Calendar vs data staleness detection | Vyasa | Bhima |
| REQ-021 — News + exchange announcement ingestion | Vyasa | Sanjaya |
| REQ-001 — Sector rankings (price median + volume ratio) | Vishwakarma | Narada |
| REQ-002 — Trigger analysis for top-sector stocks | Vishwakarma | Narada |
| REQ-003 — Scheduled delivery at 21:00 IST, trading days only | Bhima | Nakula |
| REQ-030 — Scheduler + retry logic | Bhima | Nakula |
| REQ-031 — Report publication to web app | Bhima | Arjun |
| WEB-001 — Responsive web app shell | Arjun | — |
| WEB-005 — Dashboard: sector rankings with drill-down | Arjun | — |

**Phase 1 exit criteria:**
- [ ] Daily briefing delivered at 21:00 IST on 3 consecutive simulated trading days
- [ ] Briefing skipped on weekend and holiday (verified with a test date)
- [ ] Two independent rankings produced: price (median) and volume (20-day ratio)
- [ ] Strongest single contributor shown per sector alongside sector-level figure
- [ ] Trigger summary (2–4 sentences) produced for each flagged stock
- [ ] Manual re-run command available and tested
- [ ] Dashboard renders both rankings; each sector expandable to constituents
- [ ] REQ-036: empty-data detection fires and aborts job without generating report
- [ ] Sahadeva QA sign-off

---

### Phase 2 — Document Parsing + Company Pages
**Goal:** Concall and presentation study (text only), unread reporting, company pages.
**Duration:** ~3 weeks
**User value:** Deep reading of concall transcripts and earnings decks without opening a PDF.

| Requirement | Owner Agent | Supporting |
|---|---|---|
| REQ-022 — Filings ingestion (PDF + PPTX) | Vyasa | Vishwakarma |
| REQ-011 — Concall transcript summarisation | Vyasa | Vishwakarma |
| REQ-011A — Earnings presentation parsing (PPT first-class) | Vyasa | Vishwakarma |
| REQ-011B — Transcript vs presentation reconciliation | Vyasa | Vishwakarma |
| REQ-011C — Text-only parsing, unread classification | Vyasa | — |
| REQ-011D — Native chart XML extraction from PPTX | Vyasa | — |
| REQ-011E — Per-slide extraction coverage logging | Vyasa | Chitragupta |
| REQ-011F — Unread document surfacing (manual review list) | Vyasa | Arjun |
| REQ-011G — Alternate source resolution before declaring unread | Vyasa | — |
| REQ-013 — Earnings quality assessment (one-off vs. sustainable) | Ganesha | Vishwakarma |
| WEB-007 — Company page (price history, financials, concall summaries, unread docs) | Arjun | — |

**Phase 2 exit criteria:**
- [ ] PDF concall transcript parsed and summarised (all 7 structured sections from REQ-011)
- [ ] PPTX earnings presentation parsed slide-by-slide; tables extracted as data, not prose
- [ ] Native chart XML extracted from PPTX where present
- [ ] Per-slide coverage log populated (chars, numbers, tables, charts per slide)
- [ ] Transcript vs presentation reconciliation runs; conflicts flagged explicitly
- [ ] Alternate source resolution attempted before declaring document unread (cap 2 attempts)
- [ ] Unread document list surfaced in every report with company, type, reason, URL
- [ ] Earnings quality report addresses one-off items and 1–2 year sustainability
- [ ] Company page loads with price history, financial history, concall summaries by quarter
- [ ] Unread docs shown on company page with source links
- [ ] Sahadeva QA sign-off

---

### Phase 3 — Watchlist + Weekly Report + Archive
**Goal:** Watchlist management, Friday weekly report, searchable report archive.
**Duration:** ~2 weeks

| Requirement | Owner Agent | Supporting |
|---|---|---|
| REQ-007 — Watchlist CRUD + 50-stock cap | Bhima | — |
| REQ-008 — End-of-day watchlist news | Bhima | Vyasa |
| REQ-005 — Weekly sector report (Friday, fallback on holiday) | Vishwakarma | Vyasa |
| REQ-006 — Weekly report trigger analysis + structural narrative | Vishwakarma | Narada |
| WEB-006 — Report archive (search + filter by date, sector, company) | Arjun | — |
| WEB-008 — Watchlist management UI | Arjun | — |

**Phase 3 exit criteria:**
- [ ] Watchlist add/remove persists across restart
- [ ] Watchlist capped at 50; count shown on every display
- [ ] End-of-day news report: stocks with news listed with one-line summary + source link
- [ ] Weekly report delivered on Friday (or last trading day of week if Friday is holiday)
- [ ] Weekly report covers same date range and trading day count
- [ ] Reliability caveat included when week has ≤3 trading days
- [ ] Report archive searchable by date range, sector, company
- [ ] Sahadeva QA sign-off

---

### Phase 4 — Full Deep Research Pipeline
**Goal:** End-to-end deep dive on any listed company with full provenance.
**Duration:** ~3 weeks
**User value:** Replace analyst reports — a single sitting produces the full research picture.

| Requirement | Owner Agent | Supporting |
|---|---|---|
| REQ-010 — Deep dive request entry point | Ganesha | Bhima |
| REQ-012 — Order book tracking + revenue impact | Ganesha | Vyasa |
| REQ-014 — Forward valuation (guidance-dependent, no extrapolation) | Ganesha | Narada |
| REQ-015 — Five-point framework (opportunity, position, economics, ROCE, valuation) | Ganesha | Narada, Vishwakarma |
| REQ-016 — Critical posture: counter-argument required for every positive conclusion | Ganesha | — |
| REQ-023 — Historical financials backfill (8Q / 3Y) | Vyasa | — |
| WEB-009 — Deep dive request + progress tracking in UI | Arjun | — |
| WEB-011 — Figure provenance: source doc, page/slide, extraction method, link | Arjun | — |

**Phase 4 exit criteria:**
- [ ] Deep dive report covers: concall summary, PPT analysis, earnings quality, order book,
      forward valuation (or explicit skip with reason), five-point framework
- [ ] No projection produced when guidance is absent; skip section states missing inputs
- [ ] Every positive conclusion carries the strongest available counter-argument
- [ ] Financial backfill runs for newly tracked company (8Q quarterly, 3Y annual)
- [ ] Document backfill limited to 4 quarters; older docs indexed with URL only
- [ ] Every figure in report links to source document, page/slide, extraction method
- [ ] Deep dive completes within 5 minutes (performance requirement)
- [ ] Immediate acknowledgement sent on request
- [ ] Sahadeva QA sign-off

---

### Phase 5 — BSE/SME, PWA, Push, Cost Visibility
**Goal:** BSE/SME dedicated coverage, PWA install, push notifications, cost enforcement UI.
**Duration:** ~2 weeks

| Requirement | Owner Agent | Supporting |
|---|---|---|
| REQ-017 — BSE/SME dedicated section in daily + weekly | Ganesha | Chitragupta |
| REQ-018 — SME liquidity + disclosure-quality caveat | Ganesha | — |
| REQ-009 — Volume surge + price move alerting for watchlist | Bhima | Vyasa |
| REQ-034 — LLM cost tracking + ceiling enforcement (₹350 warn, ₹500 cap) | Nakula | Chitragupta |
| WEB-002 — PWA: home-screen install, offline last-loaded report | Nakula | Arjun |
| WEB-003 — Landing page (unauthenticated, no data exposed) | Arjun | — |
| WEB-010 — Push notifications on new report | Nakula | Arjun |
| WEB-012 — Cost dashboard (MTD spend, by job type, by model) | Arjun | Nakula |

**Phase 5 exit criteria:**
- [ ] BSE SME and NSE Emerge movers, listings, filings reported separately from mainboard
- [ ] SME report carries liquidity, lot size, and reduced-disclosure caveat
- [ ] Volume surge: 2.5x 20-day average AND ≥₹50,00,000 traded value (both conditions)
- [ ] Price move: >5% flagged independently of volume
- [ ] Cost tracking live: token usage, estimated INR cost, by job type and model
- [ ] Warning delivered at ₹350 MTD
- [ ] Deep dives suspended at ₹500 MTD; scheduled briefings continue on Haiku
- [ ] PWA installs to home screen on mobile; serves last-loaded report offline
- [ ] Landing page carries disclaimer; no report or watchlist data reachable unauthenticated
- [ ] Push notification delivered when report is ready (where permission granted)
- [ ] Cost dashboard shows MTD spend and ceiling
- [ ] Sahadeva QA sign-off

---

### Phase 6 — Data Density + Accessibility
**Goal:** Production-quality reading experience. Research tool standards, not generic web app.
**Duration:** ~1 week

| Requirement | Owner Agent | Supporting |
|---|---|---|
| WEB-014 — Data density (decimal-aligned tables, 4-level hierarchy, no horizontal scroll) | Usha (review) → Arjun (implementation) | frontend-design |
| WEB-015 — Accessibility: WCAG AA contrast, keyboard reachable, screen reader navigable | frontend-design (audit) → Arjun (fixes) | Usha |

**Phase 6 exit criteria:**
- [ ] Numeric tables aligned on decimal in all report views
- [ ] Typographic hierarchy has ≥4 distinguishable levels
- [ ] No horizontal scroll required on 360px viewport for any table
- [ ] WCAG AA contrast ratios pass on all text elements (light and dark mode)
- [ ] Every interactive element keyboard reachable and screen-reader navigable
- [ ] Sahadeva final QA sign-off for v1.0 release

---

## 3. Agent Roster

| Agent | Invoke with | Primary Phase(s) | Domain in this project |
|---|---|---|---|
| **Mayasura** | `/mayasura` | Phase 0 | Architecture, parser interface contract, provenance model, ADRs |
| **frontend-design** | `/frontend-design` | Phase 0, Phase 6 | Design system definition (tokens, dark mode, component library baseline); Phase 6 accessibility audit |
| **Usha** | `/usha` | Phase 0, Phase 6 | Design system handoff to Arjun; information architecture of report pages; Phase 6 data density review |
| **Hanuman** | `/hanuman` | Phase 0 | Auth security review; threat model for session management and allowlist |
| **Bhima** | `/bhima` | Phase 0–3, 5 | Database schema, auth implementation, scheduler, watchlist, persistence layer |
| **Arjun** | `/arjun` | Phase 1–6 | All frontend implementation — dashboard, company pages, archive, deep dive UI, PWA, landing page |
| **Vyasa** | `/vyasa` | Phase 1–4 | All data ingestion — OHLCV, news, filings, transcripts, presentations, financials, trading calendar |
| **Vishwakarma** | `/vishwakarma` | Phase 1–3 | Sector ranking logic, trigger analysis, weekly report narrative, LLM orchestration for scheduled jobs |
| **Ganesha** | `/ganesha` | Phase 2–5 | Earnings quality, order book tracking, forward valuation, five-point framework, BSE/SME analysis, critical posture |
| **Narada** | `/narada` | Phase 1–4 | Supporting statistical work — sector ranking validation, projection inputs, five-point framework |
| **Chitragupta** | `/chitragupta` | Phase 2, 5 | Extraction coverage analysis (REQ-011E), cost tracking and reporting (REQ-034) |
| **Nakula** | `/nakula` | Phase 1, 5 | Oracle Cloud deployment, APScheduler setup, IST timezone config, PWA build, push notifications |
| **Sanjaya** | `/sanjaya` | Phase 1 | Exchange integration guidance — NSE/BSE API patterns, announcement scraping |
| **Sahadeva** | `/sahadeva` | All phases (exit gates) | QA for every phase; acceptance testing against PRD Section 4; v1.0 release recommendation |
| **Valmiki** | `/valmiki` | As needed | ADRs, architecture notes, meeting notes, decision records |

### Design Ownership Split

| Work | Agent |
|---|---|
| Design token system, component baseline, dark mode definition | `/frontend-design` |
| Information architecture, report structure, UX wireframes | `/usha` |
| All frontend implementation, React components, TypeScript | `/arjun` |
| Accessibility audit (Phase 6) | `/frontend-design` |
| Data density review (Phase 6) | `/usha` |

---

## 4. Critical Path

The following are the hard dependencies that determine overall timeline:

```
[Phase 0: Schema + Design System + Auth]
        ↓
[Phase 1: Daily Briefing + Dashboard]     ← First user value
        ↓
[Phase 2: Document Parsing + Company Pages]
        ↓
[Phase 3: Watchlist + Weekly + Archive]
        ↓
[Phase 4: Deep Research Pipeline]          ← Core differentiation
        ↓
[Phase 5: BSE/SME + PWA + Cost]
        ↓
[Phase 6: Data Density + Accessibility]    ← v1.0 shippable
```

**REQ-034 (cost enforcement) must ship before Phase 4 opens.** Phase 4 is the highest
LLM-cost phase. Without enforcement live, a bulk accidental request can breach ₹500 in
a single job.

---

## 5. Risk Register

See `docs/risk-register.md` for full risk register. Top risks:

| Risk | Impact | Likelihood | Owner |
|---|---|---|---|
| yfinance unreliable for BSE/SME tickers | High | High | Vyasa |
| Indian earnings PPTs are scanned — high unread rate | High | Medium | Vyasa, Ganesha |
| APScheduler misses 21:00 IST on server restart | Medium | Medium | Nakula |
| Cost ceiling breached by accidental bulk deep dive | High | Low | Nakula, Chitragupta |
| Sector classification inconsistent across providers | High | High | Vyasa |

---

## 6. Estimation Notes

| Phase | Estimated Duration | Confidence |
|---|---|---|
| Phase 0 | 2 weeks | High |
| Phase 1 | 3 weeks | Medium (yfinance reliability risk) |
| Phase 2 | 3 weeks | Low-Medium (document parsing quality unknown upfront) |
| Phase 3 | 2 weeks | High |
| Phase 4 | 3 weeks | Medium (depends on Phase 2 parsing quality) |
| Phase 5 | 2 weeks | High |
| Phase 6 | 1 week | High |
| **Total** | **~16 weeks** | **Medium overall** |

Buffer applied: 20% on Phases 1, 2, 4 due to external API and document parsing unknowns.

---

## 7. Communication Plan

- **INBOX.md:** All agents append cross-lane handoffs, blockers, decisions here.
- **Sahadeva QA gate:** Required before each phase exit. No phase begins without prior
  phase QA sign-off from Sahadeva.
- **Valmiki ADRs:** Required for: database choice, parser interface contract, document
  provenance model, any technology selection with two or more real options.
- **Status:** Green/Amber/Red tracked in INBOX.md per phase.

---

## 8. First Actions (Phase 0 Kickoff)

In order:

1. **Mayasura** — Produce architecture note: system overview, parser interface contract,
   provenance model, technology stack rationale. Output: ADR + data model diagram.

2. **frontend-design** — Define design token system: colour palette (dark mode default),
   typography scale, spacing scale, component baseline. Handoff to Arjun + Usha.

3. **Bhima** — Design PostgreSQL schema covering all entities through Phase 2. Write
   Alembic migration for Phase 0. Schema must include `first_seen_at` and `parser_version`
   on every document row.

4. **Hanuman** — Security review of auth design (session-based, allowlist only).
   Threat model: session hijacking, allowlist bypass, API key exposure.

5. **Nakula** — Oracle Cloud instance setup: IST timezone, PostgreSQL install, Caddy
   reverse proxy + TLS, Python 3.11 environment, initial deployment scaffold.

---

*IMP-20260923-001 · v1.0 · Atharva · Active · 2026-09-23*
