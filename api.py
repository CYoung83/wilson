"""
Wilson API v0.0.5

FastAPI-based REST API and web interface for Wilson citation verification.
Uses Server-Sent Events (SSE) for streaming phase-by-phase results.
Citations CSV loaded into memory at startup for fast offline lookup.

Run with:
  uvicorn api:app --reload --host 0.0.0.0 --port 8000

API docs: http://localhost:8000/docs
"""

import os
import time
import re
import json
import pandas as pd
from typing import Optional, AsyncGenerator
from datetime import datetime, timezone
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv
import requests as http_requests
from eyecite import get_citations
from rapidfuzz import fuzz
from sse_starlette.sse import EventSourceResponse

from quote_verify import verify_quote
from coherence_check import check_coherence, coherence_available

load_dotenv()

CL_TOKEN = os.getenv("COURTLISTENER_TOKEN")
CL_HEADERS = {"Authorization": f"Token {CL_TOKEN}"}
CITATIONS_CSV = os.getenv("CITATIONS_CSV", "data/citations-2026-03-31.csv")
CASE_NAME_MATCH_THRESHOLD = 75

# ------------------------------------------------------------------------------
# Load CSV into memory at startup for fast offline lookup
# First query triggers load; all subsequent queries use in-memory dataframe
# ------------------------------------------------------------------------------
_citations_df = None


def get_citations_df():
    global _citations_df
    if _citations_df is None and os.path.exists(CITATIONS_CSV):
        print(f"Loading citations CSV into memory: {CITATIONS_CSV}")
        _citations_df = pd.read_csv(CITATIONS_CSV, dtype=str)
        print(f"Loaded {len(_citations_df):,} citation records")
    return _citations_df


# Trigger load at startup
if os.path.exists(CITATIONS_CSV):
    print("Citations CSV found — will load on first request")


app = FastAPI(
    title="Wilson",
    description="AI Reasoning Auditor -- Open-source legal citation verification",
    version="0.0.5",
)

templates = Jinja2Templates(directory="templates")


# ------------------------------------------------------------------------------
# Models
# ------------------------------------------------------------------------------

class VerifyRequest(BaseModel):
    citation: str
    quoted_text: Optional[str] = None
    proposition: Optional[str] = None


# ------------------------------------------------------------------------------
# Pipeline functions
# ------------------------------------------------------------------------------

def lookup_citation_api(text: str):
    """Returns (found, cluster_id, actual_case_name, message)"""
    try:
        url = "https://www.courtlistener.com/api/rest/v4/citation-lookup/"
        resp = http_requests.post(
            url, json={"text": text}, headers=CL_HEADERS, timeout=10
        )
        results = resp.json()
        if not results:
            return False, None, None, "No results returned"
        first = results[0]
        if first.get("status") == 404:
            return False, None, None, first.get("error_message", "Citation not found")
        clusters = first.get("clusters", [])
        if not clusters:
            return False, None, None, "Citation found but no cluster data"
        cluster_id = clusters[0]["id"]
        actual_case_name = clusters[0].get("case_name", "Unknown")
        return True, cluster_id, actual_case_name, f"Found -- {actual_case_name} (cluster {cluster_id})"
    except Exception as e:
        return None, None, None, f"API error: {e}"


def lookup_by_name(case_name: str):
    """
    Fallback: search CourtListener by case name when no reporter citation available.
    Returns (found, cluster_id, actual_case_name, full_citation, message)
    """
    try:
        url = "https://www.courtlistener.com/api/rest/v4/search/"
        resp = http_requests.get(
            url,
            params={"q": case_name, "type": "o"},
            headers=CL_HEADERS,
            timeout=10
        )
        data = resp.json()
        results = data.get("results", [])
        if not results:
            return False, None, None, None, "No cases found matching that name"
        top = results[0]
        cluster_id = top.get("cluster_id")
        actual_name = top.get("caseName", "Unknown")
        citations = top.get("citation", [])
        full_citation = citations[0] if citations else None
        return True, cluster_id, actual_name, full_citation, f"Found by name -- {actual_name}"
    except Exception as e:
        return None, None, None, None, f"Name lookup error: {e}"


def check_local_csv(vol, reporter, page):
    """
    Fast in-memory CSV lookup.
    Returns (found: bool or None, message)
    """
    df = get_citations_df()
    if df is None:
        return None, "Local CSV not configured"
    try:
        match = df[
            (df["volume"] == vol) &
            (df["reporter"] == reporter) &
            (df["page"] == page)
        ]
        if len(match) > 0:
            return True, f"Found in local CSV ({len(match)} match(es))"
        return False, "Not found in local CSV"
    except Exception as e:
        return None, f"CSV error: {e}"


def extract_case_name(citation_text: str) -> str:
    match = re.split(r',\s*\d+\s+\w', citation_text)
    if match:
        return match[0].strip()
    return citation_text.strip()


def verify_case_name(cited_name: str, actual_name: str):
    score = fuzz.partial_ratio(cited_name.lower(), actual_name.lower())
    return score, score >= CASE_NAME_MATCH_THRESHOLD


def evt(type: str, **kwargs) -> dict:
    return {"type": type, **kwargs}


def csv_status_string(csv_found):
    if csv_found is True:
        return "Found"
    elif csv_found is False:
        return "Not found"
    else:
        return "Not configured" if not os.path.exists(CITATIONS_CSV) else "Error"


# ------------------------------------------------------------------------------
# Streaming pipeline
# ------------------------------------------------------------------------------

async def run_pipeline(
    citation_text: str,
    quoted_text: Optional[str],
    proposition: Optional[str]
) -> AsyncGenerator[dict, None]:

    start_time = time.time()

    yield evt("status", message="Extracting citation...")

    citations = get_citations(citation_text)
    used_fallback = False
    fallback_citation = None

    if not citations:
        yield evt("status", message="Standard parsing failed -- trying name-based lookup...")
        fb_found, fb_cluster_id, fb_case_name, fb_full_citation, fb_message = lookup_by_name(citation_text)

        if fb_found and fb_full_citation:
            citations = get_citations(fb_full_citation)
            used_fallback = True
            fallback_citation = fb_full_citation
            yield evt("status", message=f"Found via name search: {fb_full_citation}")
        else:
            yield evt("unparseable", message=(
                f"Could not extract a citation from the provided text. "
                f"Wilson needs a full citation including volume, reporter, and page number. "
                f"Example: Obergefell v. Hodges, 576 U.S. 644 (2015). "
                f"Name search result: {fb_message}"
            ))
            yield evt("done", duration=round(time.time() - start_time, 2))
            return

    if not citations:
        yield evt("unparseable", message=(
            "Could not extract a citation. "
            "Please include volume, reporter, and page number. "
            "Example: Miranda v. Arizona, 384 U.S. 436 (1966)"
        ))
        yield evt("done", duration=round(time.time() - start_time, 2))
        return

    c = citations[0]
    groups = c.groups
    vol = groups.get("volume")
    reporter = groups.get("reporter")
    page = groups.get("page")

    parsed = {
        "volume": vol,
        "reporter": reporter,
        "page": page,
        "court": c.metadata.court if hasattr(c, "metadata") else None,
        "year": c.metadata.year if hasattr(c, "metadata") else None,
        "plaintiff": c.metadata.plaintiff if hasattr(c, "metadata") else None,
        "defendant": c.metadata.defendant if hasattr(c, "metadata") else None,
        "used_fallback": used_fallback,
        "fallback_citation": fallback_citation,
    }

    yield evt("parsed", data=parsed)

    yield evt("phase1_start", message="Checking CourtListener API and local database...")

    api_found, cluster_id, actual_case_name, api_message = lookup_citation_api(
        fallback_citation if used_fallback else citation_text
    )
    csv_found, csv_message = check_local_csv(vol, reporter, page)
    csv_status = csv_status_string(csv_found)

    if api_found is False:
        yield evt("phase1_complete", data={
            "verdict": "FABRICATED",
            "api_found": False,
            "local_csv": csv_status,
            "message": (
                "Citation not found in CourtListener or local database. "
                "This citation does not exist in 18 million federal case records."
            )
        })
        yield evt("done", duration=round(time.time() - start_time, 2))
        return

    if api_found is None:
        yield evt("phase1_complete", data={
            "verdict": "ERROR",
            "api_found": None,
            "local_csv": csv_status,
            "message": api_message
        })
        yield evt("done", duration=round(time.time() - start_time, 2))
        return

    cited_name = extract_case_name(citation_text)
    match_score, name_matches = verify_case_name(cited_name, actual_case_name)
    match_pct = round(match_score)

    if not name_matches:
        yield evt("phase1_complete", data={
            "verdict": "MISATTRIBUTED",
            "cluster_id": cluster_id,
            "case_name": actual_case_name,
            "cited_name": cited_name,
            "match_pct": match_pct,
            "api_found": True,
            "local_csv": csv_status,
            "message": (
                f"The citation coordinates ({vol} {reporter} {page}) exist in the database "
                f"but belong to a different case. "
                f"You cited '{cited_name}' but those coordinates belong to '{actual_case_name}'. "
                f"Name similarity: {match_pct}% (minimum {CASE_NAME_MATCH_THRESHOLD}% required). "
                f"This typically means the case name was fabricated while reusing real reporter "
                f"coordinates, or the citation was copied incorrectly."
            )
        })
        yield evt("done", duration=round(time.time() - start_time, 2))
        return

    yield evt("phase1_complete", data={
        "verdict": "EXISTS",
        "cluster_id": cluster_id,
        "case_name": actual_case_name,
        "cited_name": cited_name,
        "match_pct": match_pct,
        "api_found": True,
        "local_csv": csv_status,
        "message": f"Citation verified -- {actual_case_name} ({match_pct}% name match)"
    })

    if quoted_text and cluster_id:
        yield evt("phase2_start", message="Fetching opinion text and checking quoted language...")
        result = verify_quote(quoted_text, cluster_id)

        score = result.get("score", 0)
        score_pct = round(score) if score else 0
        raw_verdict = result.get("result", "NOT_FOUND")

        if raw_verdict == "EXACT_MATCH":
            display_verdict = "100% MATCH"
        elif raw_verdict == "FUZZY_MATCH":
            display_verdict = f"{score_pct}% MATCH"
        else:
            display_verdict = "NOT FOUND"

        yield evt("phase2_complete", data={
            "verdict": raw_verdict,
            "display_verdict": display_verdict,
            "score_pct": score_pct,
            "passage": result.get("passage", "")[:300] if result.get("passage") else None,
            "reasoning": result.get("reasoning", "")
        })

    if proposition and cluster_id:
        yield evt("phase3_start", message="Running coherence check -- reading full opinion...")
        result = check_coherence(
            proposition=proposition,
            case_name=actual_case_name,
            cluster_id=cluster_id
        )
        yield evt("phase3_complete", data={
            "verdict": result.get("verdict", "ERROR"),
            "confidence": result.get("confidence"),
            "reasoning": result.get("reasoning", "")
        })

    yield evt("done", duration=round(time.time() - start_time, 2))


# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    available, llm_message = coherence_available()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "llm_available": available,
            "llm_message": llm_message,
            "csv_available": os.path.exists(CITATIONS_CSV),
        }
    )


@app.get("/health")
async def health():
    llm_available, llm_message = coherence_available()
    csv_available = os.path.exists(CITATIONS_CSV)
    df = get_citations_df()
    cl_available = False
    try:
        resp = http_requests.get(
            "https://www.courtlistener.com/api/rest/v4/",
            headers=CL_HEADERS,
            timeout=5
        )
        cl_available = resp.status_code == 200
    except Exception:
        pass
    return {
        "status": "operational",
        "version": "0.0.5",
        "phases": {
            "phase1_api": {
                "available": cl_available,
                "description": "Citation existence via CourtListener API"
            },
            "phase1_offline": {
                "available": csv_available,
                "description": "Citation existence via local bulk CSV (18M records)",
                "csv_path": CITATIONS_CSV if csv_available else None,
                "loaded_in_memory": df is not None,
                "record_count": len(df) if df is not None else 0
            },
            "phase2": {
                "available": cl_available,
                "description": "Quote verification against full opinion text"
            },
            "phase3": {
                "available": llm_available,
                "description": "Coherence checking via local LLM",
                "message": llm_message
            }
        }
    }


@app.post("/verify/stream")
async def verify_stream(request: VerifyRequest):
    """Stream Wilson pipeline results as Server-Sent Events."""
    citation_text = request.citation.strip()
    quoted_text = request.quoted_text.strip() if request.quoted_text else None
    proposition = request.proposition.strip() if request.proposition else None

    async def generate():
        async for e in run_pipeline(citation_text, quoted_text, proposition):
            yield {"data": json.dumps(e)}

    return EventSourceResponse(generate())


@app.post("/verify")
async def verify(request: VerifyRequest):
    """Run Wilson pipeline and return complete JSON. Use /verify/stream for streaming."""
    citation_text = request.citation.strip()
    quoted_text = request.quoted_text.strip() if request.quoted_text else None
    proposition = request.proposition.strip() if request.proposition else None

    result = {
        "citation": citation_text,
        "version": "0.0.5",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    async for e in run_pipeline(citation_text, quoted_text, proposition):
        t = e.get("type")
        if t == "parsed":
            result["parsed"] = e.get("data")
        elif t == "phase1_complete":
            result["phase1"] = e.get("data")
        elif t == "phase2_complete":
            result["phase2"] = e.get("data")
        elif t == "phase3_complete":
            result["phase3"] = e.get("data")
        elif t == "done":
            result["duration_seconds"] = e.get("duration")
        elif t == "unparseable":
            result["error"] = e.get("message")

    return result
