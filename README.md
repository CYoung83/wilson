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

**Proof of concept — pipeline functional as of April 2, 2026.**

The current implementation:
- Extracts legal citations from any text using [eyecite](https://github.com/freelawproject/eyecite)
- Verifies existence against 18 million federal case records from [CourtListener](https://www.courtlistener.com)
- Returns a full reasoning trace at each verification step
- Operates against both live API and local bulk data — air gap capable

**Next milestone:** Coherence checking — auditing whether a citation actually supports the proposition it's cited for, not just whether it exists.

---

## Quick Start

### Prerequisites
- Python 3.12+
- CourtListener API token (free at [courtlistener.com](https://www.courtlistener.com))

### Setup
```bash
git clone https://github.com/CYoung83/wilson.git
cd wilson
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
echo "COURTLISTENER_TOKEN=your_token_here" > .env
```

### Run the smoke test
```bash
python3 smoke_test.py
```

Expected output: Wilson extracts a known fabricated citation from *Mata v. Avianca* — the first major AI hallucination sanctions case — verifies it against CourtListener's API and local bulk data, and returns NOT FOUND with a full reasoning trace.

---

## Architecture

Wilson's core pipeline:
```
Input (legal text)
    ↓
Citation Extraction (eyecite)
    ↓
Existence Verification (CourtListener API + local bulk data)
    ↓
Reasoning Trace (documented evidence chain)
    ↓
Verdict (VERIFIED / NOT FOUND / MISREPRESENTED) + full chain
```

**Design principles:**
- No privileged access to audited systems — Wilson reads public records and logs
- Air gap capable — core pipeline functions offline against local bulk data
- No proprietary dependencies — eyecite (BSD), CourtListener (CC BY-ND), CAP (CC0)
- Every output includes the reasoning chain that produced it

---

## Roadmap

- [x] Citation extraction (eyecite)
- [x] Existence verification against CourtListener API
- [x] Existence verification against local bulk data (18M records)
- [x] Full reasoning trace generation
- [ ] Coherence checking — does the citation support the cited proposition?
- [ ] Quote verification — does the quoted text appear in the cited opinion?
- [ ] Batch processing — full document audit
- [ ] HTML report generation
- [ ] API endpoint for workflow integration
- [ ] Front-end interface

---

## Data Sources

| Source | Purpose | License |
|--------|---------|---------|
| [CourtListener](https://www.courtlistener.com) | Case lookup and verification | CC BY-ND |
| [Free Law Project Bulk Data](https://www.courtlistener.com/help/api/bulk-data/) | Local citation database (18M records) | CC BY-ND |
| [eyecite](https://github.com/freelawproject/eyecite) | Citation extraction | BSD |
| [Charlotin Hallucination Database](https://www.damiencharlotin.com/hallucinations/) | Primary test dataset | — |

---

## Contributing

Wilson is open source because auditability requires transparency. Contributions are welcome — particularly in the following areas:

- Coherence checking logic
- Quote verification against full opinion text
- Additional data source integrations
- Documentation and test coverage

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
