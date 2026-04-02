"""
Wilson v0.0.2 - Integration Test

Demonstrates the complete Phase 1 + Phase 2 pipeline:

Phase 1: Citation existence verification
  - Extract citation with eyecite
  - Verify against CourtListener API (v4)
  - Verify against local citations CSV (18M records, optional)

Phase 2: Quote verification
  - Fetch full opinion text from CourtListener
  - Check whether quoted language appears in the opinion
  - Return confidence score and closest matching passage

Test cases:
  A) Known fabricated citation (Mata v. Avianca) — should fail existence check
  B) Real citation with real quote (Strickland) — should pass existence and quote check
  C) Real citation with fabricated quote (Strickland) — should pass existence, fail quote check

Local CSV is optional. If not present, Step 3 is skipped gracefully.
Configure CITATIONS_CSV in .env or download bulk data per README instructions.
"""

import os
import pandas as pd
from dotenv import load_dotenv
import requests
from eyecite import get_citations
from quote_verify import verify_quote

load_dotenv()

CL_TOKEN = os.getenv("COURTLISTENER_TOKEN")
CL_HEADERS = {"Authorization": f"Token {CL_TOKEN}"}

CITATIONS_CSV = os.getenv(
    "CITATIONS_CSV",
    "/var/mnt/wilson-data/courtlistener/citations-2026-03-31.csv"
)


def lookup_citation(text):
    """
    Look up a citation via CourtListener API v4.
    Returns (found: bool, cluster_id: int or None, message: str)
    """
    url = "https://www.courtlistener.com/api/rest/v4/citation-lookup/"
    resp = requests.post(url, json={"text": text}, headers=CL_HEADERS)
    results = resp.json()

    if not results:
        return False, None, "No results returned"

    first = results[0]

    if first.get("status") == 404:
        return False, None, first.get("error_message", "Citation not found")

    clusters = first.get("clusters", [])
    if not clusters:
        return False, None, "Citation found but no cluster data returned"

    cluster_id = clusters[0]["id"]
    return True, cluster_id, f"Found — cluster ID {cluster_id}"


def check_local_csv(citations):
    """
    Check extracted eyecite citations against local bulk CSV.
    Returns (found: bool or None, message: str)
    None indicates the check was skipped (CSV not available).
    """
    if not citations:
        return False, "No citations extracted"

    if not os.path.exists(CITATIONS_CSV):
        return None, (
            f"Local CSV not found at {CITATIONS_CSV} — skipping offline check. "
            f"See README for bulk data download instructions."
        )

    c = citations[0]
    groups = c.groups
    vol = groups.get("volume")
    reporter = groups.get("reporter")
    page = groups.get("page")

    try:
        df = pd.read_csv(CITATIONS_CSV, dtype=str)
        match = df[
            (df["volume"] == vol) &
            (df["reporter"] == reporter) &
            (df["page"] == page)
        ]
        if len(match) > 0:
            return True, f"Found in local CSV ({len(match)} match(es))"
        else:
            return False, "Not found in local CSV"
    except Exception as e:
        return None, f"CSV error: {e}"


def run_test(label, citation_text, quoted_text=None):
    """
    Run the full Wilson pipeline on a citation and optional quote.
    """
    print(f"\n{'=' * 60}")
    print(f"TEST: {label}")
    print(f"{'=' * 60}")

    # Step 1: Extract with eyecite
    print(f"\n[STEP 1] Extracting citation...")
    citations = get_citations(citation_text)
    if citations:
        print(f"  FOUND: {citations[0]}")
    else:
        print(f"  ERROR: eyecite found no citations")
        return

    # Step 2: API lookup
    print(f"\n[STEP 2] CourtListener API lookup...")
    found, cluster_id, message = lookup_citation(citation_text)
    print(f"  {'FOUND' if found else 'NOT FOUND'}: {message}")

    # Step 3: Local CSV
    print(f"\n[STEP 3] Local CSV verification...")
    csv_found, csv_message = check_local_csv(citations)
    if csv_found is None:
        print(f"  SKIPPED: {csv_message}")
    else:
        print(f"  {'FOUND' if csv_found else 'NOT FOUND'}: {csv_message}")

    # Step 4: Quote verification (only if citation exists and quote provided)
    if quoted_text:
        print(f"\n[STEP 4] Quote verification...")
        if not found or not cluster_id:
            print(f"  SKIPPED: Citation does not exist — quote verification not applicable")
        else:
            result = verify_quote(quoted_text, cluster_id)
            print(f"  Result: {result['result']}")
            print(f"  Score:  {round(result['score'], 1)}")
            print(f"  Reasoning: {result['reasoning']}")
            if result['passage']:
                print(f"  Passage: {result['passage'][:200]}")


if __name__ == "__main__":
    print("=" * 60)
    print("WILSON v0.0.2 — FULL PIPELINE TEST")
    print("=" * 60)

    # Report CSV status upfront
    if os.path.exists(CITATIONS_CSV):
        print(f"\nLocal CSV: {CITATIONS_CSV}")
        print(f"Offline verification: ENABLED")
    else:
        print(f"\nLocal CSV: NOT FOUND")
        print(f"Offline verification: DISABLED")
        print(f"To enable: download bulk data per README instructions")
        print(f"Configure path via CITATIONS_CSV in .env")

    # Test A: Known fabricated citation — should fail at existence
    run_test(
        label="A — Fabricated citation (Mata v. Avianca)",
        citation_text="Varghese v. China Southern Airlines Co., Ltd., 925 F.3d 1339 (11th Cir. 2019)",
        quoted_text="An airline's duty of care extends to all foreseeable risks of international travel"
    )

    # Test B: Real citation, real quote — should pass both
    run_test(
        label="B — Real citation, real quote (Strickland)",
        citation_text="Strickland v. Washington, 466 U.S. 668, 688 (1984)",
        quoted_text="The proper measure of attorney performance is reasonableness under prevailing professional norms"
    )

    # Test C: Real citation, fabricated quote — should pass existence, fail quote
    run_test(
        label="C — Real citation, fabricated quote (Strickland)",
        citation_text="Strickland v. Washington, 466 U.S. 668, 688 (1984)",
        quoted_text="Defense counsel must achieve perfect performance under all circumstances regardless of resources"
    )

    print(f"\n{'=' * 60}")
    print("PIPELINE TEST COMPLETE")
    print("=" * 60)
