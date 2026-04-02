# Wilson

> Wilson removes the advantage afforded to those who will lie.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Status: Proof of Concept](https://img.shields.io/badge/Status-Proof%20of%20Concept-yellow.svg)]()
[![Built with: Python](https://img.shields.io/badge/Built%20with-Python-3776AB.svg)]()

---

## What is Wilson?

Wilson is an open-source AI reasoning auditor. Where existing tools check whether a citation exists and return a verdict, Wilson follows the citation into the source and audits whether it actually supports the proposition it's cited for — returning a documented evidence chain, not just a score.

An auditor you can't audit is just another black box. Wilson is open because auditability requires transparency.

---

## Why does it exist?

AI systems generate confident, plausible-sounding outputs through intentionally closed processes. 315 documented cases of AI-fabricated citations by legal professionals have reached US courtrooms since 2023 — accelerating. Every existing solution is proprietary and opaque.

Wilson is the accountability layer those systems cannot provide for themselves.

---

## Current Status

**Proof of concept — full three-phase pipeline functional as of April 2, 2026.**

Verified against Mata v. Avianca (1:22-cv-01461, S.D.N.Y.) — the most sanctioned AI hallucination case in US legal history. Wilson correctly identified all six citations in the original filing: three fabricated, two misattributed to wrong cases at valid coordinates, one legitimate. 6/6 accuracy. Zero false positives.

### Phase 1 — Citation Existence
- Extracts legal citations from any text using [eyecite](https://github.com/freelawproject/eyecite)
- Verifies existence against 18 million federal case records from [CourtListener](https://www.courtlistener.com)
- Verifies case name against actual case at cited coordinates — catches misattributed citations
- Operates against both live API and local bulk data — air gap capable
- Verdicts: **FABRICATED** | **MISATTRIBUTED** | **EXISTS**

### Phase 2 — Quote Verification
- Fetches full opinion text from CourtListener (up to 212,000+ characters)
- Checks whether quoted language appears verbatim or approximately in the opinion
- Flags false quotes and paraphrasing presented as direct quotation
- Verdicts: **EXACT_MATCH** | **FUZZY_MATCH** | **NOT_FOUND**

### Phase 3 — Coherence Checking
- Sends full opinion text to a local LLM via Ollama
- Asks whether the cited case actually supports the proposition it is cited for
- Runs entirely locally — no case data leaves the machine
- Requires Ollama with any capable model (7B+ recommended)
- Verdicts: **SUPPORTS** | **DOES_NOT_SUPPORT** | **UNCERTAIN** | **SKIPPED**

---

## Quick Start

### Prerequisites
- Python 3.12+
- CourtListener API token — free at [courtlistener.com](https://www.courtlistener.com)
- Ollama (optional) — for Phase 3 coherence checking — [ollama.com](https://ollama.com)

### Setup
```bash
git clone https://github.com/CYoung83/wilson.git
cd wilson
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your CourtListener API token
```

### Configure

Edit `.env`:
```bash
COURTLISTENER_TOKEN=your_token_here

# Optional — Phase 3 coherence checking
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3
OLLAMA_CONTEXT_SIZE=32000
```

### Run the smoke test (Phases 1 + 2)
```bash
python3 smoke_test.py
```

Expected output: Wilson runs three test cases — a fabricated citation from Mata v. Avianca (NOT FOUND on both API and local CSV), a real citation with a real quote (FOUND + FUZZY_MATCH), and a real citation with a fabricated quote (FOUND + NOT_FOUND).

### Run the Mata v. Avianca proof of concept
```bash
python3 test_mata_avianca.py
```

Expected output: 6/6 correct verdicts across FABRICATED, MISATTRIBUTED, and EXISTS categories.

### Run coherence checking (Phase 3, requires Ollama)
```bash
python3 coherence_check.py
```

Expected output: Three Strickland v. Washington test cases — correct proposition (SUPPORTS), wrong proposition (DOES_NOT_SUPPORT), subtle misrepresentation (DOES_NOT_SUPPORT). All HIGH confidence.

---

## Architecture
```
Input (legal text or document)
         ↓
Citation Extraction (eyecite)
         ↓
┌─────────────────────────────────┐
│ PHASE 1: Existence Verification │
│  • CourtListener API lookup     │
│  • Local bulk CSV (18M records) │
│  • Case name verification       │
│  → FABRICATED / MISATTRIBUTED / EXISTS
└─────────────────────────────────┘
         ↓ (if EXISTS)
┌─────────────────────────────────┐
│ PHASE 2: Quote Verification     │
│  • Fetch full opinion text      │
│  • Exact + fuzzy match          │
│  → EXACT_MATCH / FUZZY_MATCH / NOT_FOUND
└─────────────────────────────────┘
         ↓ (if Ollama configured)
┌─────────────────────────────────┐
│ PHASE 3: Coherence Checking     │
│  • Full opinion → local LLM     │
│  • Does case support proposition?
│  → SUPPORTS / DOES_NOT_SUPPORT / UNCERTAIN
└─────────────────────────────────┘
         ↓
Full Reasoning Trace (every step documented)
```

**Design principles:**
- No privileged access to audited systems — Wilson reads public records
- Air gap capable — Phase 1 functions fully offline against local bulk data
- No proprietary dependencies — eyecite (BSD), CourtListener (CC BY-ND), CAP (CC0)
- Phase 3 runs locally — no case data sent to external services
- Every output includes the reasoning chain that produced it

---

## Deployment Tiers

| Tier | Requirements | Capabilities |
|------|-------------|--------------|
| Free / Air-Gap | CourtListener token + bulk CSV | Phases 1 + 2 |
| + Coherence | Tier 1 + Ollama (any model, 7B+) | Phases 1 + 2 + 3 |
| + Source Docs | Tier 2 + PACER account | Original filing retrieval |

See [API_ACCESS_NOTES.md](API_ACCESS_NOTES.md) for full data source documentation.

---

## Roadmap

- [x] Citation extraction (eyecite)
- [x] Existence verification against CourtListener API
- [x] Existence verification against local bulk data (18M records)
- [x] Case name verification — catches misattributed citations
- [x] Full reasoning trace generation
- [x] Quote verification — exact and fuzzy match against full opinion text
- [x] Coherence checking — local LLM audits whether case supports proposition
- [x] Proof of concept verified — Mata v. Avianca 6/6
- [ ] Batch processing — full document audit pipeline
- [ ] HTML report generation
- [ ] REST API endpoint for workflow integration
- [ ] Front-end interface
- [ ] PACER integration for original filing retrieval

---

## Data Sources

| Source | Purpose | License |
|--------|---------|---------|
| [CourtListener](https://www.courtlistener.com) | Case lookup, verification, full opinion text | CC BY-ND |
| [Free Law Project Bulk Data](https://www.courtlistener.com/help/api/bulk-data/) | Local citation database (18M records) | CC BY-ND |
| [Harvard CAP](https://case.law) | Historical caselaw (6.7M decisions, 1658–2020) | CC0 |
| [eyecite](https://github.com/freelawproject/eyecite) | Citation extraction | BSD |
| [Charlotin Hallucination Database](https://www.damiencharlotin.com/hallucinations/) | Primary test dataset | — |

---

## Contributing

Wilson is open source because auditability requires transparency. Contributions are welcome — particularly:

- Batch processing pipeline for full document audit
- HTML report generation
- REST API endpoint
- Additional data source integrations
- Test coverage expansion
- Documentation

Open an issue before submitting a pull request so we can discuss approach.

---

## Background

Named for the volleyball in *Cast Away* — something real built under duress because survival required it. A thinking partner that keeps you sane when the system breaks down around you.

Wilson is developed by [National Standard Consulting LLC](https://github.com/CYoung83), an SDVOSB founded by a US Navy veteran and former GS-13 Training and Exercise Program Specialist at USNORTHCOM.

---

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.

---

*Wilson does not make decisions. It makes decisions auditable.*
