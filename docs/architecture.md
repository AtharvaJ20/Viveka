━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Document:    Architecture Overview — Personal Stock Research & Monitoring Agent
ID:          ARCH-20260923-001
Author:      Mayasura
Owner:       Atharva
Date:        2026-09-23
Version:     v1.0
Status:      Accepted
References:  PRD-20260909-001 v2.0, IMP-20260923-001, ADR-001 through ADR-005
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Architecture Overview — Personal Stock Research & Monitoring Agent

---

## 1. Architectural Philosophy for This Project

This is a personal-use system with one developer, ₹0 infrastructure budget, and a hard
₹500/month LLM ceiling. These constraints are not limitations to work around — they are
the architecture.

Three principles govern every decision here:

1. **The monolith earns every component it adds.** A two-process system is twice the
   operational complexity of a one-process system. Add complexity only when the alternative
   is clearly worse.

2. **Interfaces hide implementation, not complexity.** The parser interface exists so
   that OCR can be added later without touching the pipeline. The LLM client exists so
   that model routing is config, not code. These are the two places where future change
   is most certain — so these are the two places where the interface investment is justified.

3. **Every number in every report knows where it came from.** Provenance is not an
   add-on feature. It is a correctness requirement. A figure without a traceable source
   cannot be trusted. Build provenance in from row zero of the schema.

---

## 2. System Context Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                          External World                             │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  NSE / BSE   │  │  yfinance /  │  │  Anthropic Claude API    │  │
│  │  Exchange    │  │  nsepython   │  │  (Haiku 4.5 / Sonnet 4.6)│  │
│  │  (RSS, PPTX, │  │  (OHLCV,     │  │                          │  │
│  │   PDFs)      │  │   sector)    │  │                          │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────────┘  │
│         │                 │                     │                   │
└─────────┼─────────────────┼─────────────────────┼───────────────────┘
          │                 │                     │
          ▼                 ▼                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│              Oracle Cloud Always Free Instance (IST)                │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                     Caddy (reverse proxy + TLS)              │  │
│  └────────────────────┬─────────────────────────────────────────┘  │
│                       │                                             │
│         ┌─────────────┴──────────────┐                             │
│         ▼                            ▼                             │
│  ┌─────────────┐            ┌─────────────────┐                    │
│  │  FastAPI    │            │  Next.js        │                    │
│  │  (Python)   │◄──────────►│  (Node.js)      │◄──── Browser      │
│  │  :8000      │  REST API  │  :3000          │      (User)        │
│  └──────┬──────┘            └─────────────────┘                    │
│         │                                                           │
│         │  ┌──────────────────────────────────────────────────┐   │
│         ├──► APScheduler (embedded, PostgreSQL job store)      │   │
│         │  └──────────────────────────────────────────────────┘   │
│         │                                                           │
│         ▼                                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    PostgreSQL                               │   │
│  │  (market data · documents · reports · watchlist ·          │   │
│  │   users · sessions · jobs · cost tracking)                 │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                  File Storage (local disk)                  │   │
│  │  /data/documents/{company_id}/{doc_id}.{pdf,pptx}          │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Container Architecture

The system is a **modular monolith**. One Python process; one database; one deployment unit.
See ADR-002 for the decision rationale.

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Python Application Process                      │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  FastAPI Application Layer                                   │  │
│  │  ┌────────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │  │
│  │  │  /api/v1/  │  │  /auth   │  │  /admin  │  │  /ws     │  │  │
│  │  │  reports   │  │          │  │  (cost,  │  │  (deep   │  │  │
│  │  │  companies │  │  login   │  │   jobs)  │  │  dive    │  │  │
│  │  │  watchlist │  │  session │  │          │  │  status) │  │  │
│  │  └────────────┘  └──────────┘  └──────────┘  └──────────┘  │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Service / Application Layer                                 │  │
│  │  ┌─────────────────┐  ┌──────────────────┐                  │  │
│  │  │  BriefingService│  │  DeepDiveService │                  │  │
│  │  │  WeeklyService  │  │  WatchlistService│                  │  │
│  │  │  CalendarService│  │  CostService     │                  │  │
│  │  └─────────────────┘  └──────────────────┘                  │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Domain Layer (no framework dependencies)                    │  │
│  │  ┌──────────────┐  ┌─────────────┐  ┌────────────────────┐  │  │
│  │  │  SectorRanker│  │  Reconciler │  │  EarningsAnalyser  │  │  │
│  │  │  TriggerFinder│  │  (REQ-011B)│  │  OrderBookTracker  │  │  │
│  │  │  (REQ-001,02)│  │             │  │  ForwardEstimator  │  │  │
│  │  └──────────────┘  └─────────────┘  └────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Infrastructure Layer                                        │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐ │  │
│  │  │  DataFetcher │  │  DocParser   │  │  LLMClient         │ │  │
│  │  │  (abstraction│  │  (abstraction│  │  (abstraction over │ │  │
│  │  │  over sources│  │  over parsers│  │  Anthropic API)    │ │  │
│  │  │  — see §6)   │  │  — see §5)   │  │  — see §7)         │ │  │
│  │  └──────────────┘  └──────────────┘  └────────────────────┘ │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Scheduler (APScheduler + PostgreSQL job store)              │  │
│  │  Jobs: daily_briefing (21:00 IST), weekly_report (Fri),     │  │
│  │        watchlist_news (EOD), calendar_refresh (monthly)     │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Key Data Flows

### 4.1 Daily Briefing (21:00 IST)

```
Scheduler triggers daily_briefing job
  │
  ├─► CalendarService.is_trading_day(today) → False? → exit, log skip
  │
  ├─► DataFetcher.fetch_ohlcv(today) → empty? → exit, notify (REQ-036)
  │
  ├─► SectorRanker.rank(ohlcv_data, sector_mapping)
  │     → price_ranking (top 3, median method)
  │     → volume_ranking (top 3, 20-day ratio method)
  │
  ├─► TriggerFinder.analyse(top_stocks, news_cache)
  │     → LLMClient.call(model="haiku-4-5", task="sector_trigger")
  │     → TriggerSummary per stock (2–4 sentences)
  │
  ├─► ReportBuilder.build_daily_briefing(rankings, triggers)
  │     → Report (JSONB) saved to reports table
  │
  └─► Report published → visible in web app dashboard (WEB-005)
```

### 4.2 Deep Dive Request

```
User requests deep dive on Company X
  │
  ├─► CostService.check_monthly_ceiling() → above ₹500? → reject
  │
  ├─► DocumentFetcher.fetch_latest(company, quarter)
  │     → PDF transcript → DocParser.parse() → ParseResult
  │     → PPTX presentation → DocParser.parse() → ParseResult
  │     → Unreadable? → stored in unread_documents (REQ-011F)
  │
  ├─► [if both read] Reconciler.reconcile(transcript, presentation)
  │     → conflicts flagged, transcript authoritative (REQ-011B)
  │
  ├─► [parallel LLM calls on Sonnet 4.6]
  │     ├─► concall_summary (REQ-011)
  │     ├─► ppt_extraction (REQ-011A)
  │     ├─► earnings_quality (REQ-013)
  │     ├─► orderbook_analysis (REQ-012)
  │     └─► forward_pe [only if guidance data present] (REQ-014)
  │
  ├─► FivePointAnalyser.analyse(all_above) (REQ-015)
  │
  ├─► ReportBuilder.build_deep_dive(all_above)
  │     → Every figure tagged with ExtractedFigure.id (provenance)
  │     → Unread documents listed in "Not read" section (REQ-011F)
  │
  └─► Report published → streamed to client via WebSocket
```

---

## 5. Parser Interface Contract

See ADR-003 for full rationale. The contract is:

```python
from typing import Protocol, Literal
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class ChartData:
    chart_index: int           # 0-based within the slide/page
    categories: list[str]
    series: dict[str, list[float]]  # series_name → values
    extraction_method: str     # "chart_xml" | "unread"

@dataclass
class TableData:
    table_index: int
    headers: list[str]
    rows: list[list[str]]

@dataclass
class PageResult:
    page_number: int           # 1-based; slide number for PPTX
    is_read: bool
    text: str                  # empty string, never None, if unread
    tables: list[TableData]
    charts: list[ChartData]
    char_count: int
    number_count: int
    extraction_method: str     # "text_layer" | "chart_xml" | "unread"

@dataclass
class ParseResult:
    status: Literal["read", "partial", "unread"]
    pages: list[PageResult]
    parser_version: str        # semver, e.g. "1.0.0"
    reason: str | None         # populated when status != "read"

class DocumentParser(Protocol):
    """
    All parsers implement this Protocol.
    Adding OCR means: implement this Protocol, register the implementation.
    The pipeline never changes.
    """
    def parse(self, file_path: Path) -> ParseResult: ...
    def supports(self, file_path: Path) -> bool: ...
    @property
    def version(self) -> str: ...
```

**Invariants enforced by the interface:**
- `ParseResult.pages` is never empty. A completely unread document has one `PageResult`
  per page with `is_read=False`.
- `PageResult.text` is never `None`. Unread pages return an empty string.
- `parser_version` is always populated. Required for FUT-005 cutoff logic.
- `extraction_method` per page is always one of the three defined values.

**Registered implementations (v1.0):**
- `PdfPlumberParser` — primary PDF parser
- `PyPdfFallbackParser` — fallback for PDFs that fail pdfplumber
- `PptxParser` — native PPTX (text + chart XML per REQ-011D)
- `PdfDeckParser` — PDF-exported presentations (via pdfplumber)

**Adding OCR (future):**
- Implement `OcrFallbackParser(DocumentParser)`
- Register it in `ParserRegistry` with a priority after text parsers
- The pipeline invokes parsers in priority order; the first that returns
  `status != "unread"` wins

---

## 6. Data Fetcher Abstraction

The `DataFetcher` abstraction exists because yfinance is unreliable for BSE/SME tickers
(Risk R-001). The routing logic is configuration — not scattered conditionals.

```python
class DataFetcher(Protocol):
    def fetch_ohlcv(self, ticker: str, date: date) -> OHLCVResult: ...
    def fetch_ohlcv_range(self, ticker: str, start: date, end: date) -> list[OHLCVResult]: ...
    def supports(self, ticker: str, exchange: str) -> bool: ...

# Registry resolves by exchange:
# NSE tickers → YFinanceFetcher (primary) → NsePythonFetcher (fallback)
# BSE tickers → BseBhavcopyfetcher (primary) → YFinanceFetcher (fallback)
# SME tickers → BseBhavcopyfetcher (primary) → NsePythonFetcher (fallback)
```

The BSE Bhavcopy CSV is published at `bhavdata.bseindia.com` after market close. It is
official, free, and reliable. It must be designed as the primary fetcher for BSE/SME
tickers in Phase 1 — not deferred to Phase 5.

---

## 7. LLM Client Abstraction

Every LLM call goes through `LLMClient`. No code in the application layer calls the
Anthropic SDK directly.

```python
@dataclass
class LLMRequest:
    task: str                  # key in MODELS config dict
    system_prompt: str
    user_prompt: str
    max_tokens: int = 4096

@dataclass
class LLMResponse:
    content: str
    input_tokens: int
    output_tokens: int
    model: str
    cost_inr: float

class LLMClient:
    def call(self, request: LLMRequest) -> LLMResponse:
        # 1. Resolve model from config: MODELS[request.task]
        # 2. Check monthly ceiling — raise CostCeilingExceeded if over ₹500
        # 3. Call Anthropic API
        # 4. Log usage to llm_usage table
        # 5. Return LLMResponse
```

**Model routing config (from PRD §10.2, extended):**

```python
MODELS: dict[str, str] = {
    # Scheduled jobs — Haiku 4.5
    "sector_trigger":       "claude-haiku-4-5-20251001",
    "watchlist_news":       "claude-haiku-4-5-20251001",
    "weekly_report":        "claude-haiku-4-5-20251001",

    # Deep research — Sonnet 4.6
    "concall_summary":      "claude-sonnet-4-6",
    "ppt_extraction":       "claude-sonnet-4-6",
    "doc_reconciliation":   "claude-sonnet-4-6",
    "earnings_quality":     "claude-sonnet-4-6",
    "orderbook_analysis":   "claude-sonnet-4-6",
    "forward_pe":           "claude-sonnet-4-6",
    "sme_research":         "claude-sonnet-4-6",
    "five_point_framework": "claude-sonnet-4-6",
}
```

Upgrading any single task to Opus requires one config change, no code change.

---

## 8. Report Storage Model

Reports are stored as **structured JSONB** in PostgreSQL, not as rendered HTML.
Rendering is the API layer's job. This decouples report content from presentation
and allows the frontend to render the same data at any fidelity.

```
Report (JSONB structure — daily briefing example):
{
  "report_type": "daily_briefing",
  "trading_date": "2026-09-23",
  "generated_at": "2026-09-23T15:32:00Z",
  "price_ranking": [
    {
      "rank": 1,
      "sector_id": 12,
      "sector_name": "Capital Goods",
      "median_change_pct": 3.2,
      "top_contributor": {
        "company_id": 445,
        "ticker": "BHEL.NS",
        "name": "Bharat Heavy Electricals",
        "change_pct": 7.1
      },
      "constituents": [...],
      "trigger": {
        "summary": "BHEL announced ₹2,400 Cr order...",
        "llm_model": "claude-haiku-4-5-20251001",
        "confidence": "identified_trigger"
      }
    }
  ],
  "volume_ranking": [...],
  "unread_documents": []     // always present; empty if none
}
```

Every figure in a deep dive report carries a `provenance` block:
```json
{
  "value": 2400,
  "unit": "crore_inr",
  "label": "Order book value",
  "provenance": {
    "document_id": 881,
    "page_or_slide": 14,
    "extraction_method": "text_layer",
    "parser_version": "1.0.0",
    "source_url": "https://www.bseindia.com/bseplus/AnnualReport/..."
  }
}
```

---

## 9. Authentication Architecture

Session-based auth. No JWT, no third-party auth service.

- Session token: 32-byte random, stored as Argon2 hash in `sessions` table.
- Allowlist: `ALLOWED_EMAILS` env var (comma-separated). Enforced at login — not at
  every request — because the allowlist is small and stable.
- Session expiry: configurable, default 30 days. Enforced on every request.
- No open registration path. Login attempts from non-allowlist addresses are rejected
  and logged (no information leakage about whether the email exists).

---

## 10. Deployment Topology

```
┌──────────────────────────────────────────────────┐
│           Oracle Cloud — ARM VM (IST)            │
│                                                  │
│  systemd: caddy.service                          │
│  systemd: stock-research.service (Python app)   │
│           └─ Restart=always                      │
│           └─ APScheduler (PostgreSQL job store)  │
│  systemd: postgresql.service                     │
│  systemd: node.service (Next.js, port 3000)      │
│                                                  │
│  /data/documents/    (filing storage)            │
│  /data/postgres/     (PostgreSQL data dir)       │
│  /etc/caddy/         (TLS + reverse proxy config)│
└──────────────────────────────────────────────────┘
```

**Caddy routing:**
- `stock.atharva.dev` (or free subdomain) → Next.js :3000 (frontend)
- `stock.atharva.dev/api/` → FastAPI :8000 (backend)
- TLS: automatic Let's Encrypt via Caddy

**APScheduler persistence:** Jobs stored in PostgreSQL (`apscheduler_jobs` table).
Process restart recovers all scheduled jobs automatically. Missed-fire grace: 60 seconds.

---

## 11. Assumptions and Risk Flags

| Assumption | If wrong, impact |
|---|---|
| yfinance + BSE Bhavcopy covers all needed tickers | DataFetcher returns gaps; briefing has empty sectors |
| APScheduler + PostgreSQL job store survives restarts reliably | Briefing missed; manual re-run required |
| Oracle Cloud Always Free remains free | Hosting cost rises from ₹0 |
| Anthropic API pricing stable at current rates | LLM cost estimate drifts; ceiling may need adjustment |
| Indian earnings PPTs are mostly text-extractable for mainboard companies | Deep dive quality degrades; REQ-011E data triggers OCR discussion |

---

*ARCH-20260923-001 · v1.0 · Mayasura · Accepted · 2026-09-23*
