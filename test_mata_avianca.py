"""
Wilson - Mata v. Avianca Proof of Concept

The fabricated citations from Mata v. Avianca (1:22-cv-01461, S.D.N.Y.)
are documented in Judge Castel's June 22, 2023 sanctions order and
extensively reported in public record.

This test runs Wilson's full pipeline against the known fabricated
citations to demonstrate detection capability.

Sources:
- Judge Castel's sanctions order, June 22, 2023
- Charlotin AI Hallucination Database
- Public reporting (Reuters, NYT, Law360)
"""

import os
import sys
from dotenv import load_dotenv
from eyecite import get_citations
from rapidfuzz import fuzz

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

import requests
CL_TOKEN = os.getenv("COURTLISTENER_TOKEN")
CL_HEADERS = {"Authorization": f"Token {CL_TOKEN}"}

CASE_NAME_MATCH_THRESHOLD = 60


def lookup_citation(text):
    """
    Look up citation via CourtListener API v4.
    Returns (found, cluster_id, actual_case_name, message)
    """
    url = "https://www.courtlistener.com/api/rest/v4/citation-lookup/"
    resp = requests.post(url, json={"text": text}, headers=CL_HEADERS, timeout=10)
    results = resp.json()

    if not results:
        return False, None, None, "No results"

    first = results[0]

    if first.get("status") == 404:
        return False, None, None, "NOT FOUND"

    clusters = first.get("clusters", [])
    if not clusters:
        return False, None, None, "No cluster data"

    cluster_id = clusters[0]["id"]
    actual_case_name = clusters[0].get("case_name", "Unknown")
    return True, cluster_id, actual_case_name, f"FOUND: {actual_case_name} (cluster {cluster_id})"


def verify_case_name(cited_name, actual_name):
    """
    Fuzzy match cited case name against actual case name at those coordinates.
    Returns (score, matches) where matches is True if score >= threshold.

    Handles common abbreviations, formatting differences, and partial names.
    A low score means the citation coordinates belong to a different case —
    a MISATTRIBUTED verdict rather than FABRICATED or FOUND.
    """
    score = fuzz.partial_ratio(cited_name.lower(), actual_name.lower())
    matches = score >= CASE_NAME_MATCH_THRESHOLD
    return score, matches


def extract_case_name(citation_text):
    """
    Extract the case name portion from a full citation string.
    e.g. "Petersen v. Iran Air, 905 F.2d 1011 (7th Cir. 1990)" -> "Petersen v. Iran Air"
    """
    # Split on the volume number pattern
    import re
    match = re.split(r',\s*\d+\s+\w', citation_text)
    if match:
        return match[0].strip()
    return citation_text.strip()


def run_wilson(citation_text, context=None):
    """
    Run Wilson's full pipeline on a single citation.
    Returns verdict: FABRICATED | MISATTRIBUTED | EXISTS
    """
    print(f"\n  Citation: {citation_text}")
    if context:
        print(f"  Context:  {context}")

    # Step 1: Extract with eyecite
    citations = get_citations(citation_text)
    if not citations:
        print(f"  Eyecite:  Could not parse citation")
        return "UNPARSEABLE"

    print(f"  Eyecite:  Parsed — {citations[0].groups}")

    # Step 2: API lookup
    found, cluster_id, actual_case_name, message = lookup_citation(citation_text)
    print(f"  API:      {message}")

    if not found:
        print(f"  VERDICT:  FABRICATED — citation does not exist")
        return "FABRICATED"

    # Step 3: Case name verification
    cited_name = extract_case_name(citation_text)
    score, matches = verify_case_name(cited_name, actual_case_name)

    print(f"  Cited:    '{cited_name}'")
    print(f"  Actual:   '{actual_case_name}'")
    print(f"  Match:    {score}/100 — {'MATCH' if matches else 'MISMATCH'}")

    if not matches:
        print(f"  VERDICT:  MISATTRIBUTED — coordinates exist but case name does not match")
        return "MISATTRIBUTED"

    print(f"  VERDICT:  EXISTS — citation verified")
    return "EXISTS"


# ============================================================
# MATA v. AVIANCA — KNOWN FABRICATED CITATIONS
# Source: Judge Castel's sanctions order, June 22, 2023
# ============================================================

CITATIONS = [
    {
        "citation": "Varghese v. China Southern Airlines Co., Ltd., 925 F.3d 1339 (11th Cir. 2019)",
        "context": "Cited re: Montreal Convention — confirmed fabricated in sanctions order",
        "expected": "FABRICATED"
    },
    {
        "citation": "Shaboon v. Egyptair, 2013 WL 3829266 (N.D. Ill. 2013)",
        "context": "Cited re: Article 17 liability — confirmed fabricated in sanctions order",
        "expected": "FABRICATED"
    },
    {
        "citation": "Petersen v. Iran Air, 905 F.2d 1011 (7th Cir. 1990)",
        "context": "Cited re: Warsaw Convention — coordinates exist but belong to different case",
        "expected": "MISATTRIBUTED"
    },
    {
        "citation": "Zicherman v. Korean Air Lines Co., 516 U.S. 217 (1996)",
        "context": "Real case — correctly cited, should be verified",
        "expected": "EXISTS"
    },
    {
        "citation": "Carey v. Pakistani Int'l Airlines Corp., 987 F.2d 1192 (6th Cir. 1993)",
        "context": "Cited re: Article 17 bodily injury — coordinates exist but belong to different case",
        "expected": "MISATTRIBUTED"
    },
    {
        "citation": "Martinez v. Delta Air Lines, 2019 WL 4748390 (E.D. Pa. 2019)",
        "context": "Cited re: emotional distress — confirmed fabricated in sanctions order",
        "expected": "FABRICATED"
    },
]


if __name__ == "__main__":
    print("=" * 60)
    print("WILSON — MATA v. AVIANCA PROOF OF CONCEPT")
    print("=" * 60)
    print(f"\nCase: Mata v. Avianca, Inc., 1:22-cv-01461 (S.D.N.Y.)")
    print(f"Sanctions: Judge P. Kevin Castel, June 22, 2023")
    print(f"Lawyers sanctioned: Steven Schwartz, Peter LoDuca")
    print(f"\nRunning Wilson against {len(CITATIONS)} citations...")

    verdicts = {
        "FABRICATED": 0,
        "MISATTRIBUTED": 0,
        "EXISTS": 0,
        "UNPARSEABLE": 0
    }
    correct = 0

    for i, item in enumerate(CITATIONS):
        print(f"\n[{i+1}/{len(CITATIONS)}]")
        verdict = run_wilson(item["citation"], item["context"])
        verdicts[verdict] = verdicts.get(verdict, 0) + 1

        expected = item["expected"]
        if verdict == expected:
            correct += 1
            print(f"  Expected: {expected} ✓")
        else:
            print(f"  Expected: {expected} ✗ — got {verdict}")

    print(f"\n{'=' * 60}")
    print(f"RESULTS")
    print(f"{'=' * 60}")
    print(f"Citations checked:   {len(CITATIONS)}")
    print(f"FABRICATED:          {verdicts['FABRICATED']}")
    print(f"MISATTRIBUTED:       {verdicts['MISATTRIBUTED']}")
    print(f"EXISTS:              {verdicts['EXISTS']}")
    print(f"UNPARSEABLE:         {verdicts['UNPARSEABLE']}")
    print(f"\nAccuracy:            {correct}/{len(CITATIONS)} expected verdicts matched")
    print(f"{'=' * 60}")
