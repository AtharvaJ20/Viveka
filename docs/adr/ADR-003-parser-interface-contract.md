# ADR-003: Document Parser Interface Contract

**Status:** Accepted
**Date:** 2026-09-23
**Author:** Mayasura
**References:** PRD REQ-011C, REQ-011G, REQ-011F, Section 7.1, ARCH-20260923-001 §5

---

## Context

The system parses PDF and PPTX documents (concall transcripts, earnings presentations,
corporate filings). Two constraints govern the parsing design:

1. **v1.0 is text-only.** REQ-011C prohibits vision or OCR extraction. Unreadable
   documents are surfaced for manual review, not processed.

2. **OCR will be added later.** Section 7.1 explicitly defers OCR to a future phase when
   the LLM budget allows. The architectural prerequisite stated in PRD §7.3 is:
   "Document parsing lives behind a parser interface with a declared result status.
   Adding an OCR parser must mean registering a new implementation, not editing the pipeline."

These two constraints together define the design problem: the interface must be stable
enough that adding OCR later requires only adding a new implementation — not changing
the pipeline.

**What varies between parsers:**
- How text is extracted (pdfplumber text layer vs. pypdf vs. OCR vs. PPTX XML)
- Whether charts are readable (chart XML in PPTX, not available in PDF)
- What causes a page to be unreadable (scanned image, corrupt file, encoding error)
- The parser version (needed for FUT-005 backlog cutoff logic)

**What must be stable:**
- The result status (`read` / `partial` / `unread`) — the pipeline branches on this
- The page-level coverage metrics — REQ-011E logs these for every parsed deck
- The `first_seen_at` and `parser_version` on every document row — FUT-005 depends on them

---

## Decision

**The `DocumentParser` Protocol and `ParseResult` dataclasses are the interface.**
See ARCH-20260923-001 §5 for the full definition.

The key invariants that every implementation must satisfy:

1. `ParseResult.pages` is never empty, even if the document is entirely unread.
   Each page has an entry with `is_read=False` and `text=""`.

2. `ParseResult.parser_version` is always set. The version is the semver of the parser
   class itself, not the underlying library.

3. `PageResult.extraction_method` is always one of: `"text_layer"`, `"chart_xml"`,
   `"unread"`. The pipeline uses this to populate provenance records (ADR-004).

4. No parser may fall through to a different extraction method silently. If a page
   cannot be read by the parser's primary method, it is `unread` — not silently empty.

**Parser registry:** A `ParserRegistry` holds a prioritised list of parsers for each
file extension. The pipeline calls `registry.parse(file_path)` — it does not instantiate
parsers directly. Adding OCR means:
```python
registry.register(OcrFallbackParser(), priority=10, extensions=[".pdf", ".pptx"])
# Text parsers have priority 1 — OCR only fires if text parser returns status="unread"
```

**Alternate source resolution (REQ-011G):** Handled at the service layer, not inside
parsers. A parser returns `status="unread"` — the `DocumentFetcherService` then tries
alternate sources and re-invokes the parser registry on the new file. The parser
does not know about alternate sources.

---

## Consequences

**Easier:**
- Adding OCR (FUT-001) is a new class + one registry call. Zero pipeline changes.
- REQ-011E coverage logging writes directly from `PageResult` fields — no additional
  instrumentation needed.
- FUT-005 cutoff logic reads `parser_version` from the document row — no inference needed.
- Testing: each parser is independently testable against fixture files.

**Harder:**
- Every parser implementation must rigorously respect the invariants above — no shortcuts.
  A parser that returns `pages=[]` for an unreadable document breaks downstream logging.
- The `ParseResult.pages` for a 200-slide PPTX is a list of 200 `PageResult` objects.
  This is held in memory during parsing. For very large documents, this may require
  chunked processing. Mitigation: max document sizes are bounded by PRD §5.1
  (60 pages for transcripts, 80 slides for presentations) — in-memory is acceptable.

**Technical debt:**
None. The interface is designed specifically for the future change (OCR) that is known
to be coming. The debt would have been created by NOT having this interface.

**What must be monitored:**
- `parser_version` in the `documents` table — when the parser is upgraded, verify that
  the version field increments correctly in newly ingested documents.
- `ParseResult.status = "unread"` rate per document type — tracked by REQ-011E.
  If this rate is materially high, it surfaces for the Section 7.1 review.
