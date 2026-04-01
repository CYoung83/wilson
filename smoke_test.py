"""
Wilson v0.0.1 Smoke Test

Takes one known-fabricated citation from the Charlotin database,
extracts it with eyecite, and checks it against:
1. CourtListener API (v4 citation-lookup)
2. Local citations CSV (offline verification)

Expected result: NOT FOUND on both — confirming Wilson's
core pipeline functions end to end.
"""

import os
import pandas as pd
from dotenv import load_dotenv
import requests
from eyecite import get_citations

load_dotenv()
CL_TOKEN = os.getenv("COURTLISTENER_TOKEN")
CL_HEADERS = {"Authorization": f"Token {CL_TOKEN}"}

# Known fabricated citation from Mata v. Avianca (Charlotin database)
# This case does not exist — confirmed NOT FOUND via API test
test_text = "Varghese v. China Southern Airlines Co., Ltd., 925 F.3d 1339 (11th Cir. 2019)"

print("=" * 60)
print("WILSON v0.0.1 SMOKE TEST")
print("=" * 60)

# Step 1: Extract citation with eyecite
print("\n[STEP 1] Extracting citation with eyecite...")
citations = get_citations(test_text)
print(f"  Found {len(citations)} citation(s)")

if not citations:
    print("  ERROR: eyecite found no citations. Pipeline broken.")
    exit(1)

c = citations[0]
print(f"  Citation: {c}")

# Step 2: Check against CourtListener API
print("\n[STEP 2] Checking CourtListener API (v4)...")
lookup_url = "https://www.courtlistener.com/api/rest/v4/citation-lookup/"
resp = requests.post(lookup_url, json={"text": test_text}, headers=CL_HEADERS)
results = resp.json()

if results and results[0].get('status') == 404:
    print(f"  STATUS: NOT FOUND (expected)")
    print(f"  Message: {results[0].get('error_message')}")
elif results and results[0].get('clusters'):
    print(f"  STATUS: FOUND — unexpected, investigation needed")
else:
    print(f"  STATUS: UNEXPECTED RESPONSE — {results}")

# Step 3: Check against local citations CSV
print("\n[STEP 3] Checking local citations CSV...")
citations_path = "/mnt/wilson-data/courtlistener/citations-2026-03-31.csv"

try:
    # Extract volume, reporter, page from eyecite result
    groups = c.groups
    vol = groups.get('volume')
    reporter = groups.get('reporter')
    page = groups.get('page')
    
    print(f"  Looking for: {vol} {reporter} {page}")
    
    df = pd.read_csv(citations_path, dtype=str)
    match = df[
        (df['volume'] == vol) &
        (df['reporter'] == reporter) &
        (df['page'] == page)
    ]
    
    if len(match) == 0:
        print(f"  STATUS: NOT FOUND in local CSV (expected)")
    else:
        print(f"  STATUS: FOUND — {len(match)} match(es)")
        print(match)

except Exception as e:
    print(f"  ERROR: {e}")

print("\n" + "=" * 60)
print("SMOKE TEST COMPLETE")
print("If both steps show NOT FOUND — Wilson v0.0.1 pipeline works.")
print("=" * 60)
