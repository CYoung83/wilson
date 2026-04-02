"""
Wilson - Charlotin Database Processor

Runs Wilson's citation verification pipeline against the Charlotin
AI hallucination database (US lawyer cases only).

For each case:
1. Extracts citations from Hallucination Items text using eyecite
2. Verifies existence against CourtListener API
3. Records results for analysis

Output: charlotin_results.csv in /var/mnt/wilson-data/charlotin/
"""

import os
import re
import time
import pandas as pd
from dotenv import load_dotenv
import requests
from eyecite import get_citations

load_dotenv()
CL_TOKEN = os.getenv("COURTLISTENER_TOKEN")
CL_HEADERS = {"Authorization": f"Token {CL_TOKEN}"}

CHARLOTIN_CSV = os.getenv("CHARLOTIN_CSV", "data/Charlotin-hallucination_cases.csv")
RESULTS_CSV = os.getenv("RESULTS_CSV", "data/charlotin_results.csv")
CITATIONS_CSV = os.getenv("CITATIONS_CSV", "data/citations-2026-03-31.csv")


def lookup_citation_api(citation_text):
    """
    Look up citation via CourtListener API v4.
    Returns (found, cluster_id, message)
    """
    try:
        url = "https://www.courtlistener.com/api/rest/v4/citation-lookup/"
        resp = requests.post(
            url,
            json={"text": citation_text},
            headers=CL_HEADERS,
            timeout=10
        )
        results = resp.json()

        if not results:
            return False, None, "No results"

        first = results[0]

        if first.get("status") == 404:
            return False, None, "NOT FOUND"

        clusters = first.get("clusters", [])
        if not clusters:
            return False, None, "No cluster data"

        cluster_id = clusters[0]["id"]
        case_name = clusters[0].get("case_name", "Unknown")
        return True, cluster_id, f"FOUND: {case_name} (cluster {cluster_id})"

    except Exception as e:
        return None, None, f"API ERROR: {e}"


def extract_citation_strings(hallucination_text):
    """
    Extract quoted case citations from Charlotin hallucination item text.
    Looks for patterns like 'Case Name, 123 F.3d 456' embedded in prose.
    Returns list of candidate citation strings for eyecite to parse.
    """
    if not hallucination_text or pd.isna(hallucination_text):
        return []

    # Split on || to get individual hallucination items
    items = hallucination_text.split("||")
    candidates = []

    for item in items:
        # Only process Fabricated and False Quotes items
        item = item.strip()
        if not item.startswith(("Fabricated", "False Quotes")):
            continue

        # Extract text after the | description marker
        parts = item.split("|", 2)
        if len(parts) >= 3:
            description = parts[2].strip()
        else:
            description = item

        # Look for quoted citation patterns in single quotes
        quoted = re.findall(r"'([^']+)'", description)
        for q in quoted:
            if any(c.isdigit() for c in q):  # citations have numbers
                candidates.append(q)

        # Also try the full description text with eyecite directly
        candidates.append(description)

    return candidates


def process_charlotin():
    """
    Main processor. Runs Wilson pipeline against Charlotin US lawyer cases.
    """
    print("=" * 60)
    print("WILSON — CHARLOTIN DATABASE PROCESSOR")
    print("=" * 60)

    # Load dataset
    df = pd.read_csv(CHARLOTIN_CSV)
    us_lawyers = df[
        (df["State(s)"] == "USA") &
        (df["Party(ies)"] == "Lawyer")
    ].copy().reset_index(drop=True)

    print(f"\nLoaded {len(us_lawyers)} US lawyer cases")

    # Load local citations CSV for offline verification
    print("Loading local citations CSV...")
    citations_df = pd.read_csv(CITATIONS_CSV, dtype=str)
    print(f"Loaded {len(citations_df):,} citation records")

    results = []
    total_citations_checked = 0
    total_found = 0
    total_not_found = 0
    total_errors = 0

    for idx, row in us_lawyers.head(5).iterrows():
        case_name = row["Case Name"]
        date = row["Date"]
        hallucination_text = row["Hallucination Items"]
        outcome = row["Outcome"]

        print(f"\n[{idx+1}/{len(us_lawyers)}] {case_name} ({date})")

        # Extract candidate citation strings
        candidates = extract_citation_strings(hallucination_text)

        if not candidates:
            print(f"  No citation candidates found")
            results.append({
                "case_name": case_name,
                "date": date,
                "outcome": outcome,
                "citation_text": None,
                "citation_found": None,
                "cluster_id": None,
                "api_message": "No citations extracted",
                "local_csv_found": None,
            })
            continue

        # Run eyecite on each candidate
        citations_found_in_case = 0

        for candidate in candidates:
            extracted = get_citations(candidate)

            if not extracted:
                continue

            for citation in extracted:
                total_citations_checked += 1
                citations_found_in_case += 1

                citation_str = str(citation)
                groups = citation.groups
                vol = groups.get("volume")
                reporter = groups.get("reporter")
                page = groups.get("page")

                print(f"  Checking: {vol} {reporter} {page}")

                # Local CSV check
                local_match = citations_df[
                    (citations_df["volume"] == vol) &
                    (citations_df["reporter"] == reporter) &
                    (citations_df["page"] == page)
                ]
                local_found = len(local_match) > 0

                # API check
                api_found, cluster_id, api_message = lookup_citation_api(candidate)

                if api_found:
                    total_found += 1
                    status = "FOUND"
                elif api_found is False:
                    total_not_found += 1
                    status = "NOT FOUND"
                else:
                    total_errors += 1
                    status = "ERROR"

                print(f"    API: {status} | Local CSV: {'FOUND' if local_found else 'NOT FOUND'}")

                results.append({
                    "case_name": case_name,
                    "date": date,
                    "outcome": outcome,
                    "citation_text": f"{vol} {reporter} {page}",
                    "citation_found": api_found,
                    "cluster_id": cluster_id,
                    "api_message": api_message,
                    "local_csv_found": local_found,
                })

                # Rate limit — be respectful to CourtListener
                time.sleep(0.5)

        if citations_found_in_case == 0:
            print(f"  No parseable citations found in candidates")
            results.append({
                "case_name": case_name,
                "date": date,
                "outcome": outcome,
                "citation_text": None,
                "citation_found": None,
                "cluster_id": None,
                "api_message": "No parseable citations",
                "local_csv_found": None,
            })

    # Save results
    results_df = pd.DataFrame(results)
    results_df.to_csv(RESULTS_CSV, index=False)

    print(f"\n{'=' * 60}")
    print(f"PROCESSING COMPLETE")
    print(f"{'=' * 60}")
    print(f"Cases processed:      {len(us_lawyers)}")
    print(f"Citations checked:    {total_citations_checked}")
    print(f"Found:                {total_found}")
    print(f"Not found:            {total_not_found}")
    print(f"Errors:               {total_errors}")
    print(f"\nResults saved to: {RESULTS_CSV}")

    if total_citations_checked > 0:
        detection_rate = (total_not_found / total_citations_checked) * 100
        print(f"\nWilson detection rate: {detection_rate:.1f}% of checked citations flagged as NOT FOUND")


if __name__ == "__main__":
    process_charlotin()
