"""
Wilson - Quote Verification Module

Given a quoted passage and a case citation, fetches the full opinion
text from CourtListener and checks whether the quoted language appears
in the opinion - exactly or approximately.

Returns a structured result Wilson can include in its reasoning trace.
"""

import os
import re
import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
from bs4 import BeautifulSoup
from rapidfuzz import fuzz
from dotenv import load_dotenv

load_dotenv()
CL_TOKEN = os.getenv("COURTLISTENER_TOKEN")
CL_HEADERS = {"Authorization": f"Token {CL_TOKEN}"}


def fetch_opinion_text(cluster_id):
    """
    Fetch full opinion text from CourtListener using a cluster ID.
    Returns plain text with HTML stripped, or None on failure.
    """
    url = f"https://www.courtlistener.com/api/rest/v4/opinions/?cluster={cluster_id}&fields=id,html_with_citations"
    resp = requests.get(url, headers=CL_HEADERS)
    
    if resp.status_code != 200:
        return None
    
    data = resp.json()
    results = data.get("results", [])
    
    if not results:
        return None
    
    # Combine all opinion parts (majority, concurrence, dissent)
    full_text = ""
    for opinion in results:
        html = opinion.get("html_with_citations", "")
        if html:
            soup = BeautifulSoup(html, "lxml")
            full_text += soup.get_text(separator=" ") + "\n"
    
    return full_text.strip() if full_text else None


def verify_quote(quoted_text, cluster_id, threshold=85):
    """
    Check whether quoted_text appears in the opinion identified by cluster_id.
    
    Args:
        quoted_text: The language quoted in the brief
        cluster_id: CourtListener cluster ID for the cited case
        threshold: Fuzzy match minimum score (0-100), default 85
    
    Returns:
        dict with keys:
            result: EXACT_MATCH | FUZZY_MATCH | NOT_FOUND | ERROR
            score: fuzzy match score (100 = exact)
            passage: closest matching passage found in opinion
            reasoning: explanation for Wilson's trace
    """
    print(f"\n[QUOTE VERIFY] Checking: '{quoted_text[:80]}...'")
    print(f"[QUOTE VERIFY] Fetching opinion cluster {cluster_id}...")
    
    opinion_text = fetch_opinion_text(cluster_id)
    
    if not opinion_text:
        return {
            "result": "ERROR",
            "score": 0,
            "passage": None,
            "reasoning": f"Could not retrieve opinion text for cluster {cluster_id}"
        }
    
    print(f"[QUOTE VERIFY] Opinion retrieved ({len(opinion_text)} chars). Searching...")
    
    # Step 1: Exact match
    if quoted_text.lower() in opinion_text.lower():
        return {
            "result": "EXACT_MATCH",
            "score": 100,
            "passage": quoted_text,
            "reasoning": f"Quoted language found verbatim in opinion cluster {cluster_id}"
        }
    
    # Step 2: Fuzzy match against sliding windows
    # Break opinion into overlapping windows roughly the size of the quote
    quote_len = len(quoted_text)
    window_size = quote_len + 50  # allow some surrounding context
    step = max(1, quote_len // 2)
    
    best_score = 0
    best_passage = ""
    
    for i in range(0, len(opinion_text) - window_size, step):
        window = opinion_text[i:i + window_size]
        score = fuzz.partial_ratio(quoted_text.lower(), window.lower())
        if score > best_score:
            best_score = score
            best_passage = window.strip()
    
    if best_score >= threshold:
        return {
            "result": "FUZZY_MATCH",
            "score": best_score,
            "passage": best_passage,
            "reasoning": f"Quoted language approximately matched in opinion cluster {cluster_id} (score: {best_score}/100). Review passage for accuracy."
        }
    else:
        return {
            "result": "NOT_FOUND",
            "score": best_score,
            "passage": best_passage,
            "reasoning": f"Quoted language not found in opinion cluster {cluster_id}. Best fuzzy match score: {best_score}/100. Possible misquotation or fabrication."
        }


if __name__ == "__main__":
    # Test with a known real quote from Strickland v. Washington
    # Cluster ID 111170 is Strickland v. Washington in CourtListener
    
    print("=" * 60)
    print("WILSON QUOTE VERIFICATION TEST")
    print("=" * 60)
    
    # Real quote - should match
    real_quote = "The proper measure of attorney performance is reasonableness under prevailing professional norms"
    result = verify_quote(real_quote, cluster_id=111170)
    
    print(f"\nResult: {result['result']}")
    print(f"Score: {result['score']}")
    print(f"Reasoning: {result['reasoning']}")
    if result['passage']:
        print(f"Passage: {result['passage'][:200]}...")
    
    print("\n" + "-" * 60)
    
    # Fabricated quote - should NOT match
    fake_quote = "Defense counsel must achieve perfect performance under all circumstances"
    result2 = verify_quote(fake_quote, cluster_id=111170)
    
    print(f"\nResult: {result2['result']}")
    print(f"Score: {result2['score']}")
    print(f"Reasoning: {result2['reasoning']}")
    
    print("\n" + "=" * 60)
    print("QUOTE VERIFICATION TEST COMPLETE")
    print("=" * 60)
