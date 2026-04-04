# Wilson

> Wilson removes the advantage afforded to those who will lie.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Version: 0.1.0](https://img.shields.io/badge/Version-0.1.0--dev-orange.svg)]()
[![Tests](https://img.shields.io/badge/Tests-36%20passing-green.svg)]()
[![Built with: Python](https://img.shields.io/badge/Built%20with-Python-3776AB.svg)]()

---

## What is Wilson?

Wilson is an open-source AI reasoning auditor. It verifies legal citations against primary sources and reconstructs the reasoning chain behind AI-generated outputs with enough granularity to hold them accountable.

Where existing tools check whether a citation exists and return a verdict, Wilson follows the citation into the source and audits whether it actually supports the proposition it is cited for -- returning a documented evidence chain, not just a score.

An auditor you cannot audit is just another black box. Wilson is open because auditability requires transparency.

---

## Why does it exist?

AI systems generate confident, plausible-sounding outputs through intentionally closed processes. 729+ documented cases of AI-fabricated citations have reached US courtrooms since 2023 -- accelerating. Every existing solution is proprietary and opaque.

Wilson is the accountability layer those systems cannot provide for themselves.

Accountability should be democratized. Wilson is free because a proprietary accountability tool has a conflict of interest baked into it.

---

## Current Status

**v0.0.5 -- Published.** Full three-phase pipeline with web interface and Windows installer.

**v0.1.0 -- In development.** Document upload portal, batch processing, pipeline improvements, settings panel.

Verified against Mata v. Avianca (1:22-cv-01461, S.D.N.Y.) -- the most sanctioned AI hallucination case in US legal history. Wilson correctly identified all six citations in the original filing: three fabricated, two misattributed to wrong cases at valid coordinates, one legitimate. 6/6 accuracy. Zero false positives.

---

## How Wilson Works

### Phase 1 -- Citation Existence
- Extracts legal citations using [eyecite](https://github.com/freelawproject/eyecite) (Free Law Project)
- Verifies existence against 18 million federal case records -- fast offline lookup
- Catches misattributed citations where coordinates belong to a different case
- Name-based fallback when only a case name is provided
- Verdicts: **FABRICATED** | **MISATTRIBUTED** | **EXISTS**

### Phase 2 -- Quote Verification
- Fetches full opinion text from CourtListener
- Checks whether quoted language appears verbatim or approximately in the opinion
- Flags false quotes and paraphrasing presented as direct quotation
- Verdicts: **100% MATCH** | **XX% MATCH** | **NOT FOUND**

### Phase 3 -- Coherence Checking
- Sends full opinion text to a local LLM via Ollama (nothing leaves your machine)
- Asks whether the cited case actually supports the proposition it is cited for
- Falls back to CourtListener semantic search when Ollama is unavailable
- Verdicts: **SUPPORTS** | **DOES_NOT_SUPPORT** | **UNCERTAIN** | **SKIPPED**

---

## Installation

### Windows (recommended for non-developers)

Download `Wilson-Setup-0.0.5.exe` from the [releases page](https://github.com/CYoung83/wilson/releases).

- No admin required -- installs to your user folder
- No Python installation needed -- bundled runtime included
- Self-contained -- everything lives in the Wilson folder
- First launch collects credentials and optionally downloads bulk citation data
- Double-click `Wilson.bat` to start -- browser opens automatically

**Requirements:** Windows 10/11 x64. Free [CourtListener API token](https://www.courtlistener.com/sign-in/). Ollama optional for Phase 3.

### Linux / macOS

```bash
git clone https://github.com/CYoung83/wilson.git
cd wilson
chmod +x setup.sh
./setup.sh
```

**Requirements:** Python 3.12+. Free [CourtListener API token](https://www.courtlistener.com/sign-in/). Ollama optional for Phase 3.

### Manual setup

```bash
git clone https://github.com/CYoung83/wilson.git
cd wilson
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your CourtListener API token
uvicorn api:app --host 0.0.0.0 --port 8000
```

---

## Configuration

Edit `.env`:

```bash
# Required
COURTLISTENER_TOKEN=your_token_here   # Free at courtlistener.com/sign-in

# Optional -- fast offline verification (~1.9GB)
CITATIONS_CSV=/path/to/citations-2026-03-31.csv

# Optional -- Phase 3 coherence checking
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen3.5:35b
OLLAMA_CONTEXT_SIZE=245760
```

### Download bulk citation data (optional)

```bash
wget "https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/bulk-data/citations-2026-03-31.csv.bz2"
bunzip2 citations-2026-03-31.csv.bz2
```

---

## Features

### Single Citation Verification
Navigate to `http://localhost:8000` and enter any legal citation. Wilson runs all three phases and streams results in real time.

### Document Upload Portal
Navigate to `http://localhost:8000/upload` to upload a PDF, DOCX, or TXT document. Wilson extracts all legal citations, lets you review and edit proposed propositions, then runs the full verification pipeline in batch.

### Settings Panel
Click the gear icon in any Wilson page to access settings: theme (dark/light/high contrast/auto), font size, layout density, Ollama configuration, CourtListener token management, and CSV status.

### Privacy Compliance
Wilson respects CourtListener's privacy removal system. When an opinion has been flagged for privacy protection, Wilson skips Phase 2 and Phase 3 and notes this in the results.

---

## Architecture

```
Input (citation text, case name, or uploaded document)
              |
    Citation Extraction (eyecite -- Free Law Project)
              |
+------------------------------------------+
|  PHASE 1: Existence Verification         |
|  - CourtListener API citation lookup     |
|  - Local bulk CSV (18M records)          |
|  - Case name fuzzy match (75% min)       |
|  - Privacy flag check (blocked field)    |
|  -> FABRICATED / MISATTRIBUTED / EXISTS  |
+------------------------------------------+
              | (if EXISTS and not blocked)
+------------------------------------------+
|  PHASE 2: Quote Verification             |
|  - Fetch full opinion text               |
|  - Exact + fuzzy string match            |
|  -> 100% MATCH / XX% MATCH / NOT FOUND  |
+------------------------------------------+
              | (if proposition provided)
+------------------------------------------+
|  PHASE 3: Coherence Checking             |
|  Primary: Ollama local LLM               |
|  Fallback: CourtListener semantic search |
|  -> SUPPORTS / DOES_NOT_SUPPORT /        |
|     UNCERTAIN / SKIPPED                  |
+------------------------------------------+
              |
  Full Reasoning Trace
```

---

## Data Sources

| Source | Purpose | License |
|--------|---------|---------|
| [CourtListener](https://www.courtlistener.com) | Case lookup, full opinion text | CC BY-ND |
| [Free Law Project Bulk Data](https://www.courtlistener.com/help/api/bulk-data/) | Local citation database (18M records) | CC BY-ND |
| [eyecite](https://github.com/freelawproject/eyecite) | Citation extraction | BSD |
| [Charlotin Hallucination Database](https://www.damiencharlotin.com/hallucinations/) | Primary test dataset | Research use |

Wilson uses CourtListener data in accordance with their privacy policy. Wilson does not republish case content -- it performs private forensic analysis and returns verdicts.

---

## Roadmap

### v0.0.5 (current release)
- [x] Three-phase citation verification pipeline
- [x] Real-time streaming web interface
- [x] 18M record offline bulk CSV support
- [x] Windows self-contained installer with first-launch wizard
- [x] Mata v. Avianca proof of concept -- 6/6 verified

### v0.1.0 (in development)
- [x] Document upload portal -- PDF, DOCX, TXT batch verification
- [x] CourtListener semantic search as Phase 3 fallback
- [x] Privacy compliance -- blocked flag detection
- [x] Name confidence threshold with "did you mean?" suggestions
- [x] CSV update notifications
- [ ] Settings panel -- theme, font size, Ollama config, token management
- [ ] Branding -- favicon, about modal
- [ ] GitHub Actions release workflow with build provenance attestation

### Future
- HTML report generation
- PACER integration
- Docker deployment
- Full SPA with client-side routing

---

## Contributing

Wilson is open source because auditability requires transparency. Contributions are welcome.

Design specifications for every feature live in `docs/superpowers/specs/`. Read the spec before submitting a PR -- it explains the reasoning behind decisions, not just what was built.

Open an issue before submitting a pull request.

---

## Background

Named for the volleyball in *Cast Away* -- something real built under duress because survival required it. A thinking partner that keeps you sane when the system breaks down around you.

Wilson is developed by [National Standard Consulting LLC](https://github.com/CYoung83), a Service-Disabled Veteran-Owned Small Business.

---

## License

Apache 2.0 -- see [LICENSE](LICENSE) for details.

---

*Wilson does not make decisions. It makes decisions auditable.*
