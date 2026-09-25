# ADR-004: Document Provenance Model

**Status:** Accepted
**Date:** 2026-09-23
**Author:** Mayasura
**References:** PRD REQ-011F, WEB-011, Section 7.3 prerequisites, ARCH-20260923-001 §8

---

## Context

PRD §7.3 states an architectural prerequisite:

> "Every extracted figure is stored with its provenance — which document, which page or
> slide, and which extraction method produced it. FUT-004 is impossible to add later if
> provenance was never recorded."

WEB-011 (Phase 4) requires every figure shown in the UI to link to its source document,
page/slide number, and extraction method.

The problem: provenance cannot be added retroactively. If figures are stored without
source attribution, there is no way to reconstruct where they came from. This must be
in the schema from day one — even though WEB-011 (the UI surface) ships in Phase 4.

**What provenance captures per figure:**
- Which document (document_id → file, company, quarter, type)
- Which page or slide within that document
- Which extraction method produced it (text_layer, chart_xml, unread)
- Which version of the parser produced it (for FUT-004 OCR confidence marking)

**What provenance does NOT capture:**
- The LLM prompt that interpreted the figure (LLM interpretation is logged separately in
  `llm_usage`; the figure itself is attributed to its source document, not to the LLM)
- User annotations or manual corrections

---

## Decision

**Two tables govern provenance: `extracted_figures` and the `provenance` JSONB block
embedded in report content.**

### Table: `extracted_figures`

Every numeric or date value extracted from a document gets a row here before any LLM
processing occurs. LLM processing reads from this table and references figure IDs.

```sql
CREATE TABLE extracted_figures (
    id              BIGSERIAL PRIMARY KEY,
    document_id     BIGINT NOT NULL REFERENCES documents(id),
    page_number     INT NOT NULL,          -- 1-based; slide number for PPTX
    extraction_method VARCHAR(20) NOT NULL  -- 'text_layer', 'chart_xml', 'unread'
        CHECK (extraction_method IN ('text_layer', 'chart_xml', 'unread')),
    parser_version  VARCHAR(20) NOT NULL,
    raw_text        TEXT,                  -- verbatim text surrounding the figure
    value_numeric   NUMERIC,               -- NULL if not numeric
    value_text      TEXT,                  -- verbatim value as it appears
    unit            VARCHAR(50),           -- 'crore_inr', '%', 'units', etc.
    label           TEXT,                  -- contextual label near the figure
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_extracted_figures_document ON extracted_figures(document_id);
```

### Provenance block in report JSONB

When a figure from `extracted_figures` appears in a report, the report's JSONB content
references it:

```json
{
  "value_numeric": 2400,
  "value_text": "₹2,400 Cr",
  "unit": "crore_inr",
  "label": "Order book value",
  "extracted_figure_id": 14837,
  "provenance": {
    "document_id": 881,
    "document_type": "presentation",
    "page_number": 14,
    "extraction_method": "text_layer",
    "parser_version": "1.0.0",
    "source_url": "https://www.bseindia.com/bseplus/AnnualReport/..."
  }
}
```

The `extracted_figure_id` foreign key allows the API to resolve full provenance from
a report figure with a single JOIN. The embedded `provenance` block allows the API
to return it without a JOIN — both are valid; the embedded version is used by the API
for performance.

### Table: `documents` (provenance-critical fields)

```sql
-- These fields are required from Phase 0. They cannot be added later without
-- losing provenance for all documents ingested before the migration.

first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
parser_version  VARCHAR(20) NOT NULL,
parse_status    VARCHAR(10) NOT NULL DEFAULT 'unread'
    CHECK (parse_status IN ('read', 'partial', 'unread')),
parse_reason    TEXT,       -- WHY unread, if status = 'unread'
source_url      TEXT NOT NULL,
alt_source_url  TEXT,       -- populated if REQ-011G found an alternate copy
alt_source_attempts INT NOT NULL DEFAULT 0
```

---

## Consequences

**Easier:**
- WEB-011 (figure provenance in UI) is a read operation on data that already exists.
  No backfill, no inference.
- FUT-004 (OCR confidence marking) adds a `confidence_level` field to `extracted_figures`
  and a new `extraction_method` value (`'ocr'`). No schema redesign.
- FUT-005 (OCR backlog cutoff) reads `first_seen_at` from `documents`. This field exists
  from day one.
- Debugging a wrong figure in a report is a lookup: `SELECT * FROM extracted_figures
  WHERE id = [figure_id]` → exact document, page, and raw text.

**Harder:**
- Every document extraction step must write to `extracted_figures` before passing data
  to the LLM. This is additional I/O compared to a design that passes figures directly.
  At the volumes in this system (80 slides per deck, ~10 deep dives per month) this is
  not a performance concern.
- The `extracted_figures` table will grow. At 500 figures per deck × 10 decks per month
  × 12 months = ~60,000 rows/year. Negligible. No partitioning needed.

**Technical debt:**
None introduced. The alternative — adding provenance later — was explicitly called out
as impossible in PRD §7.3. The debt was pre-empted.

**What must be monitored:**
- `documents.parse_status = 'unread'` rate, grouped by document type and company size.
  This is the REQ-011E signal. If the unread rate is consistently high for a particular
  document type, it surfaces for the Section 7.1 OCR review.
- `extracted_figures.extraction_method = 'unread'` — figures that could not be extracted
  appear here as unread entries, preserving the page coverage log (REQ-011E).
