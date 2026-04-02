# Wilson — API Access & Data Source Notes

Reference document for Wilson deployment requirements.
Updated: April 2, 2026

---

## CourtListener API

**Base URL:** https://www.courtlistener.com/api/rest/v4/
**Auth:** Token-based (free registration at courtlistener.com)
**Docs:** https://www.courtlistener.com/api/rest/docs/

### Free Token — Confirmed Working

| Endpoint | Method | Purpose | Status |
|----------|--------|---------|--------|
| /citation-lookup/ | POST | Verify citation existence, get cluster ID and case name | ✓ Working |
| /opinions/ | GET | Fetch full opinion text (html_with_citations field) | ✓ Working |
| /clusters/ | GET | Case metadata, judges, dates, citations | ✓ Working |
| /search/ | GET | Full-text search across opinions and dockets | ✓ Working |
| /courts/ | GET | Court metadata | ✓ Working |

### Free Token — Access Denied

| Endpoint | Method | Purpose | Status |
|----------|--------|---------|--------|
| /docket-entries/ | GET | List documents filed in a case | ✗ PACER required |
| /recap-documents/ | GET | Access RECAP-collected PACER documents | ✗ PACER required |

### Notes on Free Tier
- Citation lookup returns cluster ID, case name, docket ID, sub-opinion URLs
- Opinion text via html_with_citations includes hyperlinked citations with data-id attributes
- Full opinion text available for most federal cases — quality varies by source
- Rate limiting applies — Wilson uses 0.5s delay between API calls
- Bulk data download available separately (see below)

---

## CourtListener Bulk Data

**URL:** https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/bulk-data/
**License:** CC BY-ND — attribution required, no derivative databases
**Auth:** None required — public S3 bucket

### Downloaded to /var/mnt/wilson-data/courtlistener/

| File | Size | Records | Purpose |
|------|------|---------|---------|
| citations-2026-03-31.csv | 1.9GB | 18,116,834 | Offline citation existence verification |
| courts-2026-03-31.csv | 748KB | — | Court metadata |
| load-bulk-data-2026-03-31.sh | 18KB | — | Load script |

### Bulk Data Schema (citations CSV)
```
id, volume, reporter, page, type, cluster_id, date_created, date_modified
```

`cluster_id` links to full case data via API. This is the bridge between
offline existence checking and online full-text retrieval.

### Offline Capability
Wilson can verify citation existence entirely offline against the bulk CSV.
No API calls required for existence checking. API required for:
- Case name verification (catching misattributed citations)
- Full opinion text retrieval (quote verification)

---

## Harvard Caselaw Access Project (CAP)

**URL:** https://case.law / https://huggingface.co/datasets/free-law/Caselaw_Access_Project
**License:** CC0 — no restrictions, commercial use permitted
**Auth:** Hugging Face account required for bulk download

### Coverage
- 6.7 million US court decisions
- Federal and state courts
- 1658 through 2020 (not updated after 2020)
- All jurisdictions including territories

### Status
- Not yet downloaded — deferred pending need
- CourtListener API covers post-2020 cases and is more practical
  for the Charlotin dataset (mostly recent cases)
- CAP useful for historical case research and offline state court coverage

### When to Use CAP vs CourtListener API
- CourtListener API: Recent federal cases, online operation
- CAP bulk download: Historical cases, air-gap operation, state courts
- Both: Cross-validation, coverage gaps

---

## PACER

**URL:** https://pacer.uscourts.gov
**Auth:** PACER account required (free registration)
**Cost:** $0.10/page for documents (fee waiver available for researchers)

### What PACER Unlocks in CourtListener
- /docket-entries/ — list of all documents filed in a case
- /recap-documents/ — RECAP-collected copies of PACER documents
- Access to original filed briefs, motions, and exhibits

### Wilson Use Case
PACER access enables Wilson to audit the original filing rather than
reconstructing citations from secondary sources. This is the gold standard
for pre-filing audit and post-filing forensic reconstruction.

### Current Status
- PACER registration: PENDING
- CourtListener PACER link: NOT CONFIGURED
- Workaround: Using published opinions and known citation lists for testing

---

## Charlotin AI Hallucination Database

**URL:** https://www.damiencharlotin.com/hallucinations/
**License:** Unspecified — research use, do not redistribute as derivative
**Auth:** None — public website, CSV download available

### Dataset Stats
- 1,222 total cases (as of download date)
- 304 US lawyer cases (Wilson's immediate scope)
- Fields: Case Name, Court, Date, Party, AI Tool, Hallucination Items,
  Outcome, Monetary Penalty, Professional Sanction

### Hallucination Type Breakdown (US Lawyers)
| Type | Count | Wilson Coverage |
|------|-------|-----------------|
| Fabricated | 538 | ✓ Phase 1 — existence checking |
| Misrepresented | 361 | ✗ Phase 3 — requires LLM reasoning |
| False Quotes | 297 | ✓ Phase 2 — quote verification |
| Outdated Advice | 11 | ✗ Phase 4 — requires citator |

**Wilson addresses 835/1,207 hallucination items (69%) with current pipeline.**

### Data Limitation
Charlotin documents that hallucinations occurred but does not always
preserve the exact fabricated citation text. Many entries describe
hallucinations in prose rather than providing parseable citation strings.
Original court filings (via PACER) provide the actual citation text.

---

## eyecite

**Repo:** https://github.com/freelawproject/eyecite
**License:** BSD — attribution required, commercial use permitted
**Auth:** None — local Python library

### Capabilities
- Extracts legal citations from any text
- Parses volume, reporter, page, court, year, parties
- Handles standard reporters (F.3d, U.S., S. Ct., WL, etc.)
- Returns structured FullCaseCitation objects

### Limitations
- Cannot parse citations without reporter information
- Name-only citations (e.g., "McIntyre v. Phx. Newspapers") not parseable
- Westlaw (WL) citations parseable but not verifiable via CourtListener bulk data

---

## Deployment Tiers

### Tier 1 — Free / Air-Gap Capable
**Requirements:** CourtListener API token (free), bulk CSV download
**Capabilities:**
- Citation existence verification against 18M records (offline)
- Case name mismatch detection (online)
- Quote verification against opinion text (online)
- Verdicts: FABRICATED, MISATTRIBUTED, EXISTS

### Tier 2 — PACER Required
**Requirements:** Tier 1 + PACER account
**Capabilities:** All of Tier 1 plus:
- Original filing retrieval
- Complete document audit without reconstruction
- Retroactive case reconstruction from filed documents

### Tier 3 — Full Coherence Checking (Not Yet Built)
**Requirements:** Tier 2 + LLM inference capability
**Capabilities:** All of Tier 2 plus:
- Does the cited case actually support the cited proposition?
- Holding verification
- Argument coherence analysis

---

*This document is maintained as part of Wilson's open source commitment.
Auditability requires transparency about data sources and access requirements.*
