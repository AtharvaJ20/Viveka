━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Document:    PostgreSQL Schema — Personal Stock Research & Monitoring Agent
ID:          SCH-20260923-001
Author:      Mayasura
Owner:       Atharva
Date:        2026-09-23
Version:     v1.0
Status:      Accepted — to be implemented by Bhima in Phase 0
References:  ARCH-20260923-001, ADR-001, ADR-003, ADR-004
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# PostgreSQL Schema

This schema covers all entities required through Phase 4. Phase 5+ additions
(PWA push subscriptions, cost ceiling config) are additive and will not require
changes to tables defined here.

Bhima implements this as Alembic migrations. Every table below is a separate migration.
The order of migrations must respect the foreign key dependencies shown.

---

## Migration Order

```
001_users_sessions
002_sectors_companies
003_price_data
004_trading_calendar
005_documents_pages
006_extracted_figures
007_financials
008_watchlist
009_reports
010_job_executions
011_llm_usage
012_apscheduler (APScheduler creates this automatically)
```

---

## Table Definitions

---

### users

```sql
CREATE TABLE users (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(255) NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,          -- Argon2id hash
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at   TIMESTAMPTZ
);
```

---

### sessions

```sql
CREATE TABLE sessions (
    id              BIGSERIAL PRIMARY KEY,
    user_id         INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash      CHAR(64) NOT NULL UNIQUE,  -- SHA-256 of the random session token
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_agent      TEXT,
    ip_address      INET
);

CREATE INDEX idx_sessions_token_hash ON sessions(token_hash);
CREATE INDEX idx_sessions_user_id    ON sessions(user_id);
```

---

### sectors

```sql
CREATE TABLE sectors (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    classification_source VARCHAR(50) NOT NULL,  -- 'nse_industry', 'bse_industry'
    version         INT NOT NULL DEFAULT 1,
    effective_date  DATE NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (name, classification_source, version)
);
```

Rationale (REQ-037): version increments when a reclassification event occurs.
Historical reports reference the version that was active when they were generated.

---

### companies

```sql
CREATE TABLE companies (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    ticker_nse      VARCHAR(20),            -- NULL if not NSE-listed
    ticker_bse      VARCHAR(20),            -- NULL if not BSE-listed
    isin            CHAR(12),
    exchange        VARCHAR(10) NOT NULL    -- 'NSE', 'BSE', 'NSE_BSE', 'SME_NSE', 'SME_BSE'
        CHECK (exchange IN ('NSE', 'BSE', 'NSE_BSE', 'SME_NSE', 'SME_BSE')),
    listed_date     DATE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_companies_ticker_nse ON companies(ticker_nse) WHERE ticker_nse IS NOT NULL;
CREATE UNIQUE INDEX idx_companies_ticker_bse ON companies(ticker_bse) WHERE ticker_bse IS NOT NULL;
CREATE INDEX        idx_companies_isin        ON companies(isin)        WHERE isin IS NOT NULL;
```

---

### sector_mappings

```sql
CREATE TABLE sector_mappings (
    id              SERIAL PRIMARY KEY,
    company_id      INT NOT NULL REFERENCES companies(id),
    sector_id       INT NOT NULL REFERENCES sectors(id),
    is_current      BOOLEAN NOT NULL DEFAULT TRUE,
    effective_date  DATE NOT NULL,
    superseded_date DATE,               -- set when is_current becomes FALSE
    source          VARCHAR(50) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_sector_mappings_company ON sector_mappings(company_id, is_current);
CREATE INDEX idx_sector_mappings_sector  ON sector_mappings(sector_id,  is_current);
```

Only one row per company may have `is_current = TRUE`. Enforced at application level
(not a partial unique index — reclassification events must be auditable).

---

### price_data

```sql
CREATE TABLE price_data (
    id              BIGSERIAL PRIMARY KEY,
    company_id      INT NOT NULL REFERENCES companies(id),
    trading_date    DATE NOT NULL,
    exchange        VARCHAR(10) NOT NULL CHECK (exchange IN ('NSE', 'BSE')),
    open            NUMERIC(14,4),
    high            NUMERIC(14,4),
    low             NUMERIC(14,4),
    close           NUMERIC(14,4) NOT NULL,
    volume          BIGINT,
    traded_value_inr NUMERIC(20,2),      -- for REQ-009 liquidity floor check
    fetcher_source  VARCHAR(30) NOT NULL, -- 'yfinance', 'bse_bhavcopy', 'nsepython'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (company_id, trading_date, exchange)
);

CREATE INDEX idx_price_data_company_date ON price_data(company_id, trading_date DESC);
CREATE INDEX idx_price_data_date         ON price_data(trading_date);
```

Partitioning by year is not needed at launch. Revisit after 2 years of data.

---

### trading_calendar

> **Schema correction (2026-09-25, Bhima):** Original DDL had `trading_date DATE PRIMARY KEY`
> (single-column PK). Corrected to composite `PRIMARY KEY (trading_date, exchange)` during
> Phase 0 implementation. Rationale: REQ-035 covers both NSE and BSE holiday calendars; NSE
> and BSE may have different holidays on the same date (e.g. BSE closes for a regional event
> while NSE does not). A single-column PK on `trading_date` makes it impossible to store
> separate rows for the two exchanges on the same date. No ADR required — this is a schema
> correctness fix, not an architectural decision.

```sql
CREATE TABLE trading_calendar (
    trading_date    DATE NOT NULL,
    is_trading_day  BOOLEAN NOT NULL,
    reason          VARCHAR(100),       -- 'weekend', 'public_holiday', 'exchange_holiday',
                                        -- 'muhurat', 'unscheduled_closure'
    exchange        VARCHAR(10) NOT NULL DEFAULT 'NSE',
    source          VARCHAR(50),        -- 'nse_website', 'bse_website', 'inferred'
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (trading_date, exchange)
);
```

`is_trading_day()` queries this table filtering on `exchange`. Muhurat sessions have
`is_trading_day = FALSE` per REQ-003 and REQ-035. Query pattern:

```sql
SELECT is_trading_day FROM trading_calendar
 WHERE trading_date = $1 AND exchange = $2
```

---

### documents

```sql
CREATE TABLE documents (
    id              BIGSERIAL PRIMARY KEY,
    company_id      INT NOT NULL REFERENCES companies(id),
    document_type   VARCHAR(20) NOT NULL
        CHECK (document_type IN ('transcript', 'presentation', 'filing', 'annual_report')),
    fiscal_year     SMALLINT,           -- e.g. 2026 for FY2025-26
    quarter         SMALLINT CHECK (quarter IN (1,2,3,4)),
    filing_date     DATE,
    source_url      TEXT NOT NULL,
    alt_source_url  TEXT,               -- populated by REQ-011G alternate resolution
    alt_source_attempts INT NOT NULL DEFAULT 0,
    file_path       TEXT,               -- local path after download; NULL if not fetched
    file_hash       CHAR(64),           -- SHA-256 of downloaded file
    file_size_bytes BIGINT,
    parse_status    VARCHAR(10) NOT NULL DEFAULT 'pending'
        CHECK (parse_status IN ('pending', 'read', 'partial', 'unread')),
    parse_reason    TEXT,               -- why unread/partial; NULL if read
    parser_version  VARCHAR(20),        -- set after first parse attempt
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    parsed_at       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_documents_company     ON documents(company_id);
CREATE INDEX idx_documents_type_status ON documents(document_type, parse_status);
CREATE INDEX idx_documents_company_quarter ON documents(company_id, fiscal_year, quarter);
```

`first_seen_at` and `parser_version` are the FUT-005 cutoff fields.
`parse_status = 'unread'` rows populate the REQ-011F surfacing list.

---

### document_pages

```sql
CREATE TABLE document_pages (
    id                  BIGSERIAL PRIMARY KEY,
    document_id         BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_number         INT NOT NULL,           -- 1-based
    is_read             BOOLEAN NOT NULL,
    char_count          INT NOT NULL DEFAULT 0,
    number_count        INT NOT NULL DEFAULT 0,
    table_count         INT NOT NULL DEFAULT 0,
    chart_count         INT NOT NULL DEFAULT 0,
    extraction_method   VARCHAR(20) NOT NULL
        CHECK (extraction_method IN ('text_layer', 'chart_xml', 'unread')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, page_number)
);

CREATE INDEX idx_doc_pages_document ON document_pages(document_id);
```

This table is the REQ-011E coverage log. `Chitragupta` reads from this table to
produce coverage distribution reports.

---

### extracted_figures

```sql
CREATE TABLE extracted_figures (
    id                  BIGSERIAL PRIMARY KEY,
    document_id         BIGINT NOT NULL REFERENCES documents(id),
    page_number         INT NOT NULL,
    extraction_method   VARCHAR(20) NOT NULL
        CHECK (extraction_method IN ('text_layer', 'chart_xml', 'unread')),
    parser_version      VARCHAR(20) NOT NULL,
    raw_text            TEXT,
    value_numeric       NUMERIC,
    value_text          VARCHAR(100),
    unit                VARCHAR(50),
    label               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_extracted_figures_document ON extracted_figures(document_id);
```

See ADR-004 for the full provenance model.

---

### financials_quarterly

```sql
CREATE TABLE financials_quarterly (
    id              BIGSERIAL PRIMARY KEY,
    company_id      INT NOT NULL REFERENCES companies(id),
    fiscal_year     SMALLINT NOT NULL,
    quarter         SMALLINT NOT NULL CHECK (quarter IN (1,2,3,4)),
    revenue_cr      NUMERIC(14,2),
    ebitda_cr       NUMERIC(14,2),
    ebitda_pct      NUMERIC(6,3),
    pat_cr          NUMERIC(14,2),
    pat_pct         NUMERIC(6,3),
    eps             NUMERIC(10,4),
    yoy_revenue_pct NUMERIC(8,3),
    yoy_pat_pct     NUMERIC(8,3),
    data_source     VARCHAR(50),        -- 'screener', 'bse_filing', 'nsepython'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (company_id, fiscal_year, quarter)
);

CREATE INDEX idx_fin_q_company ON financials_quarterly(company_id, fiscal_year, quarter);
```

---

### financials_annual

```sql
CREATE TABLE financials_annual (
    id              BIGSERIAL PRIMARY KEY,
    company_id      INT NOT NULL REFERENCES companies(id),
    fiscal_year     SMALLINT NOT NULL,
    revenue_cr      NUMERIC(14,2),
    ebitda_cr       NUMERIC(14,2),
    ebitda_pct      NUMERIC(6,3),
    pat_cr          NUMERIC(14,2),
    pat_pct         NUMERIC(6,3),
    roce_pct        NUMERIC(6,3),
    debt_to_equity  NUMERIC(8,4),
    book_value_per_share NUMERIC(10,4),
    data_source     VARCHAR(50),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (company_id, fiscal_year)
);
```

---

### watchlist

```sql
CREATE TABLE watchlist (
    id              SERIAL PRIMARY KEY,
    user_id         INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    company_id      INT NOT NULL REFERENCES companies(id),
    added_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    notes           TEXT,
    UNIQUE (user_id, company_id)
);

CREATE INDEX idx_watchlist_user ON watchlist(user_id);
```

Max 50 entries per user enforced at application layer (REQ-007).

---

### reports

```sql
CREATE TABLE reports (
    id              BIGSERIAL PRIMARY KEY,
    report_type     VARCHAR(30) NOT NULL
        CHECK (report_type IN (
            'daily_briefing', 'weekly_report', 'deep_dive',
            'watchlist_news', 'bse_sme_section'
        )),
    trading_date    DATE,               -- the market day the report covers
    week_start_date DATE,               -- set for weekly_report
    week_end_date   DATE,               -- set for weekly_report
    company_id      INT REFERENCES companies(id),  -- set for deep_dive
    requested_by    INT REFERENCES users(id),       -- set for deep_dive
    status          VARCHAR(10) NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'published', 'failed')),
    content         JSONB,              -- structured report content
    generated_at    TIMESTAMPTZ,
    published_at    TIMESTAMPTZ,
    error_message   TEXT,               -- set if status='failed'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_reports_type_date    ON reports(report_type, trading_date DESC);
CREATE INDEX idx_reports_company      ON reports(company_id) WHERE company_id IS NOT NULL;
CREATE INDEX idx_reports_status       ON reports(status);
CREATE INDEX idx_reports_content_gin  ON reports USING GIN(content);
```

The GIN index on `content` enables efficient JSONB search for the WEB-006 archive.

---

### job_executions

```sql
CREATE TABLE job_executions (
    id              BIGSERIAL PRIMARY KEY,
    job_name        VARCHAR(50) NOT NULL,   -- 'daily_briefing', 'weekly_report', etc.
    triggered_by    VARCHAR(20) NOT NULL    -- 'scheduler', 'manual'
        CHECK (triggered_by IN ('scheduler', 'manual')),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    status          VARCHAR(10) NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'success', 'failed', 'skipped')),
    skip_reason     TEXT,               -- 'non_trading_day', 'no_market_data', etc.
    retry_count     SMALLINT NOT NULL DEFAULT 0,
    error_message   TEXT,
    report_id       BIGINT REFERENCES reports(id)
);

CREATE INDEX idx_job_executions_name_date ON job_executions(job_name, started_at DESC);
```

---

### llm_usage

```sql
CREATE TABLE llm_usage (
    id              BIGSERIAL PRIMARY KEY,
    job_type        VARCHAR(50) NOT NULL,   -- matches MODELS config key
    model           VARCHAR(60) NOT NULL,
    input_tokens    INT NOT NULL,
    output_tokens   INT NOT NULL,
    cost_usd        NUMERIC(10,6) NOT NULL,
    cost_inr        NUMERIC(10,4) NOT NULL,
    usd_to_inr_rate NUMERIC(8,4) NOT NULL,
    report_id       BIGINT REFERENCES reports(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_llm_usage_created ON llm_usage(created_at);
CREATE INDEX idx_llm_usage_report  ON llm_usage(report_id) WHERE report_id IS NOT NULL;
```

Monthly ceiling check: `SELECT SUM(cost_inr) FROM llm_usage WHERE date_trunc('month', created_at) = date_trunc('month', now())`

---

## Entity Relationship Summary

```
users ──────────── sessions
  │
  └──────────────── watchlist ──── companies ──┬── sector_mappings ── sectors
                                               │
                                               ├── price_data
                                               │
                                               ├── documents ──── document_pages
                                               │        │
                                               │        └──────── extracted_figures
                                               │
                                               ├── financials_quarterly
                                               ├── financials_annual
                                               └── reports (deep_dive) ── llm_usage

reports ─────────────────────────────────────────── llm_usage
job_executions ──────────────────────────────────── reports
trading_calendar (standalone)
```

---

*SCH-20260923-001 · v1.0 · Mayasura · Accepted · 2026-09-23*
*To be implemented by Bhima as Alembic migrations*
