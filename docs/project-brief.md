━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Document:    Project Brief — Personal Stock Research & Monitoring Agent
ID:          BRF-20260923-001
Author:      Yudhishthira (Product) · Krishna (PM)
Owner:       Atharva
Date:        2026-09-23
Version:     v1.0
Status:      Active
References:  PRD-20260909-001 v2.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Project Brief — Personal Stock Research & Monitoring Agent

---

## 1. Problem Statement

Retail research on Indian equities is fragmented. Price and volume data lives on one platform,
concall transcripts on the exchange website, order book announcements in scattered filings, and
news across a dozen sources. Connecting a sector move to its actual trigger, and then judging
whether an earnings jump is sustainable, currently takes 60–90 minutes of manual work per day.

---

## 2. Product Vision

> We help independent retail investors in Indian equities to research and monitor companies
> deeply and systematically, so that hours of daily manual work are replaced by structured,
> automated intelligence — without sacrificing the critical posture that makes research
> trustworthy.

---

## 3. Goals

| Goal | Measure |
|---|---|
| Automated daily briefing at 21:00 IST | ≥95% of trading days |
| Sector trigger accuracy | 8 of 10 spot checks accurate |
| Concall summary usable without reading source | Author rates ≥4/5 on 5 consecutive summaries |
| Manual research time replaced | <15 min/day (from 60–90) |
| Deep dive pipeline coverage | 100% of P0 requirements in first 3 reports |

---

## 4. What We Are Building

- Automated daily sector briefing (price + volume rankings, trigger analysis)
- Weekly sector review delivered Fridays
- Persistent personal watchlist with end-of-day news monitoring
- On-demand deep research pipeline (concall summaries, PPT analysis, earnings quality,
  order book tracking, forward valuation, five-point framework)
- Responsive web application as primary reading surface (PWA, offline-capable)
- BSE and SME-listed company first-class coverage
- Cost tracking and enforcement against ₹500/month LLM ceiling

---

## 5. What We Are NOT Building

- Public product, sign-up, payments, multi-tenant architecture
- Investment advice or buy/sell signals
- Broker integration or order placement
- Intraday or tick-level data
- Native mobile app (App Store / Play Store) — PWA covers the need at ₹0
- Social media sentiment ingestion
- Vision/OCR extraction (deferred, see PRD Section 7.1)

---

## 6. Constraints

| Constraint | Detail |
|---|---|
| Infrastructure cost | ₹0/month — Oracle Cloud Always Free tier |
| LLM cost ceiling | ₹500/month hard ceiling, enforced by REQ-034 |
| Data sources | Free only — yfinance, nsepython, exchange RSS, Google News RSS |
| Developer | Single developer (Atharva) |
| Language | Python 3.11+ (backend), Next.js/React (frontend) |
| Hosting | Oracle Cloud Always Free — 4 ARM cores, 24 GB RAM, IST timezone |
| Deployment | Single instance, no Kubernetes, no managed services |

---

## 7. Success Metrics (OKRs)

**Objective:** Replace manual daily equity research with automated, structured intelligence
that is trusted on first use.

| KR | Target |
|---|---|
| KR1: Daily briefing delivered on schedule | ≥95% of trading days |
| KR2: Sector trigger accuracy | 8 of 10 manual spot checks correct |
| KR3: Concall summary quality | Author rates ≥4/5 on 5 consecutive summaries |
| KR4: Research time replaced | 60–90 min → <15 min/day |
| KR5: Deep dive P0 coverage | 100% of P0 requirements in first 3 reports |

---

## 8. Stakeholders

| Role | Name | RACI |
|---|---|---|
| Product Owner / Decision Authority | Atharva | Accountable |
| Users (author + contacts) | Atharva + 2–4 contacts | Informed |
| Agent Team | See Implementation Plan §3 | Responsible |

---

## 9. Out of Scope (Explicitly Deferred)

- Vision/OCR extraction (FUT-001 to FUT-006) — deferred pending budget increase
- Portfolio tracking with P&L
- Derivatives/F&O analytics
- Public signup or open registration

---

## 10. Definition of Done

v1.0 is done when:

1. All P0 requirements (Phases 0–5) are implemented and pass acceptance criteria
2. Daily briefing has run successfully for 10 consecutive trading days
3. At least 3 end-to-end deep dives have been reviewed and rated ≥4/5
4. Application is deployed and accessible on Oracle Cloud
5. REQ-034 cost enforcement is live and tested
6. Sahadeva has issued a "Go" or "Go with risks" QA release recommendation

---

*BRF-20260923-001 · v1.0 · Atharva · Active · 2026-09-23*
