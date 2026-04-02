# Wilson

> Wilson removes the advantage afforded to those who will lie.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Version: 0.0.5](https://img.shields.io/badge/Version-0.0.5-blue.svg)]()
[![Status: Proof of Concept](https://img.shields.io/badge/Status-Proof%20of%20Concept-yellow.svg)]()
[![Built with: Python](https://img.shields.io/badge/Built%20with-Python-3776AB.svg)]()

---

## What is Wilson?

Wilson is an open-source AI reasoning auditor. Where existing tools check whether a citation exists and return a verdict, Wilson follows the citation into the source and audits whether it actually supports the proposition it is cited for — returning a documented evidence chain, not just a score.

An auditor you can't audit is just another black box. Wilson is open because auditability requires transparency.

---

## Why does it exist?

AI systems generate confident, plausible-sounding outputs through intentionally closed processes. 315 documented cases of AI-fabricated citations by legal professionals have reached US courtrooms since 2023 — accelerating. Every existing solution is proprietary and opaque.

Wilson is the accountability layer those systems cannot provide for themselves.

---

## Current Status

**v0.0.5 — Full three-phase pipeline with web interface, as of April 3, 2026.**

Verified against Mata v. Avianca (1:22-cv-01461, S.D.N.Y.) — the most sanctioned AI hallucination case in US legal history. Wilson correctly identified all six citations in the original filing: three fabricated, two misattributed to wrong cases at valid coordinates, one legitimate. 6/6 accuracy. Zero false positives.

### Phase 1 — Citation Existence
- Extracts legal citations from any text using [eyecite](https://github.com/freelawproject/eyecite)
- Name-based fallback lookup when only a case name is provided
- Verifies existence against 18 million federal case records — loaded into memory for fast offline lookup (~2GB RAM)
- Verifies case name against actual case at cited coordinates — catches misattributed citations
- Operates against both live API and local bulk data — air gap capable
- Verdicts: **FABRICATED** | **MISATTRIBUTED** | **EXISTS**

### Phase 2 — Quote Verification
- Fetches full opinion text from CourtListener (up to 212,000+ characters)
- Checks whether quoted language appears verbatim or approximately in the opinion
- Flags false quotes and paraphrasing presented as direct quotation
- Returns closest matching passage with confidence score
- Verdicts: **100% MATCH** | **XX% MATCH** | **NOT FOUND**

### Phase 3 — Coherence Checking
- Sends full opinion text to a local LLM via Ollama
- Asks whether the cited case actually supports the proposition it is cited for
- Runs entirely locally — no case data leaves the machine
- Requires Ollama with any capable model (7B+ recommended)
- Verdicts: **SUPPORTS** | **DOES_NOT_SUPPORT** | **UNCERTAIN** | **SKIPPED**

---

## Web Interface

Wilson includes a FastAPI web interface with real-time streaming results.

```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` in your browser. Results stream phase by phase as they complete — no waiting for the full pipeline before seeing output.

API documentation is auto-generated at `http://localhost:8000/docs`.

Both a streaming endpoint (`POST /verify/stream`) and a standard JSON endpoint (`POST /verify`) are available.

---

## Quick Start

### Prerequisites
- Python 3.12+
- CourtListener API token — free at [courtlistener.com](https://www.courtlistener.com)
- Ollama (optional) — for Phase 3 coherence checking — [ollama.com](https://ollama.com)

### One-command setup
```bash
git clone https://github.com/CYoung83/wilson.git
cd wilson
chmod +x setup.sh
./setup.sh
```

The setup script checks Python version, creates a virtual environment, installs dependencies, configures `.env`, optionally downloads bulk citation data, checks Ollama availability, and runs all three test suites.

### Manual setup
```bash
git clone https://github.com/CYoung83/wilson.git
cd wilson
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your CourtListener API token
```

### Optional — Download bulk citation data (enables offline verification)
```bash
# Download (~121MB compressed, ~1.9GB uncompressed)
wget "https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/bulk-data/citations-2026-03-31.csv.bz2"
bunzip2 citations-2026-03-31.csv.bz2

# Add path to .env
echo "CITATIONS_CSV=/path/to/citations-2026-03-31.csv" >> .env
```

Without the bulk data, Wilson still runs Phases 1 and 2 via the CourtListener API. The local CSV enables air-gap capable offline verification and loads into memory at startup for fast repeated queries.

### Configure `.env`
```bash
# Required
COURTLISTENER_TOKEN=your_token_here

# Optional — offline verification (fast in-memory lookup)
CITATIONS_CSV=/path/to/citations-2026-03-31.csv

# Optional — Phase 3 coherence checking
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3
OLLAMA_CONTEXT_SIZE=32000

# Optional — PACER credentials (enables original filing retrieval)
PACER_USERNAME=your_username
PACER_PASSWORD=your_password
```

---

## Running Wilson

### Web interface
```bash
source venv/bin/activate
uvicorn api:app --host 0.0.0.0 --port 8000
# Open http://localhost:8000
```

### Command line tests
```bash
# Phases 1 + 2 pipeline test
python3 smoke_test.py

# Mata v. Avianca proof of concept (6/6 verdict accuracy)
python3 test_mata_avianca.py

# Phase 3 coherence checking (requires Ollama)
python3 coherence_check.py

# Batch processing against Charlotin hallucination database
python3 charlotin_processor.py
```

---

## Architecture

```
Input (citation text or case name)
              ↓
    Citation Extraction (eyecite)
    + Name-based fallback lookup
              ↓
┌──────────────────────────────────────┐
│  PHASE 1: Existence Verification     │
│  • CourtListener API lookup          │
│  • Local bulk CSV (18M records,      │
│    in-memory for fast lookup)        │
│  • Case name fuzzy match (75% min)   │
│  → FABRICATED / MISATTRIBUTED /      │
│    EXISTS                            │
└──────────────────────────────────────┘
              ↓ (if EXISTS)
┌──────────────────────────────────────┐
│  PHASE 2: Quote Verification         │
│  • Fetch full opinion text           │
│    (up to 212,000+ chars)            │
│  • Exact + fuzzy string match        │
│  → 100% MATCH / XX% MATCH /          │
│    NOT FOUND                         │
└──────────────────────────────────────┘
              ↓ (if Ollama configured)
┌──────────────────────────────────────┐
│  PHASE 3: Coherence Checking         │
│  • Full opinion → local LLM          │
│  • Does case support proposition?    │
│  • Runs locally, no data egress      │
│  → SUPPORTS / DOES_NOT_SUPPORT /     │
│    UNCERTAIN / SKIPPED               │
└──────────────────────────────────────┘
              ↓
  Full Reasoning Trace
  (every step documented)
```

**Design principles:**
- No privileged access to audited systems — Wilson reads public records
- Air gap capable — Phase 1 functions fully offline against local bulk data
- No proprietary dependencies — eyecite (BSD), CourtListener (CC BY-ND), CAP (CC0)
- Phase 3 runs locally — no case data sent to external services
- Every output includes the reasoning chain that produced it
- Degrades gracefully — Phases 1 and 2 work without Ollama; offline CSV is optional

---

## Deployment Tiers

| Tier | Requirements | Capabilities |
|------|-------------|--------------|
| Free / Air-Gap | CourtListener token + bulk CSV | Phases 1 + 2, offline capable |
| + Coherence | Tier 1 + Ollama (any model, 7B+) | Phases 1 + 2 + 3, fully local |
| + Source Docs | Tier 2 + PACER account | Original filing retrieval |

See [API_ACCESS_NOTES.md](API_ACCESS_NOTES.md) for full data source documentation and access requirements.

---

## Roadmap

### Completed
- [x] Citation extraction (eyecite)
- [x] Existence verification against CourtListener API
- [x] Existence verification against local bulk data (18M records, in-memory)
- [x] Case name verification — catches misattributed citations
- [x] Name-based fallback lookup when no reporter citation available
- [x] Full reasoning trace generation
- [x] Quote verification — exact and fuzzy match against full opinion text
- [x] Coherence checking — local LLM audits whether case supports proposition
- [x] Proof of concept verified — Mata v. Avianca 6/6
- [x] FastAPI web interface with real-time streaming results
- [x] REST API with both streaming (SSE) and standard JSON endpoints
- [x] Portable setup script — one command from clone to running tests
- [x] Configurable LLM endpoint — any Ollama-compatible model

### In Progress (v0.1.0)
- [ ] UI settings panel — light/dark/high contrast themes, font size, density
- [ ] Favicon and branding
- [ ] Batch processing — full document audit pipeline
- [ ] Document upload portal
- [ ] Timer and token tally per query
- [ ] HTML report generation
- [ ] PACER integration for original filing retrieval

---

## Data Sources

| Source | Purpose | License |
|--------|---------|---------|
| [CourtListener](https://www.courtlistener.com) | Case lookup, verification, full opinion text | CC BY-ND |
| [Free Law Project Bulk Data](https://www.courtlistener.com/help/api/bulk-data/) | Local citation database (18M records) | CC BY-ND |
| [Harvard CAP](https://case.law) | Historical caselaw (6.7M decisions, 1658-2020) | CC0 |
| [eyecite](https://github.com/freelawproject/eyecite) | Citation extraction | BSD |
| [Charlotin Hallucination Database](https://www.damiencharlotin.com/hallucinations/) | Primary test dataset | Research use |

---

## Contributing

Wilson is open source because auditability requires transparency. Contributions are welcome.

Priority areas for contribution:
- Batch processing pipeline for full document audit
- HTML report generation
- Additional data source integrations
- Test coverage expansion — more cases from the Charlotin database
- Documentation and examples

Open an issue before submitting a pull request so we can discuss approach.

---

## Background

Named for the volleyball in *Cast Away* — something real built under duress because survival required it. A thinking partner that keeps you sane when the system breaks down around you.

Wilson is developed by [National Standard Consulting LLC](https://github.com/CYoung83), a disabled veteran owned small business.

---

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.

---

*Wilson does not make decisions. It makes decisions auditable.*
