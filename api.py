"""
Wilson API v0.0.5

FastAPI-based REST API and web interface for Wilson citation verification.
Uses Server-Sent Events (SSE) for streaming phase-by-phase results.
Citations CSV loaded into memory at startup for fast offline lookup.

Run with:
  uvicorn api:app --host 0.0.0.0 --port 8000

API docs: http://localhost:8000/docs
"""

import os
import time
import re
import json
import asyncio
import pandas as pd
from typing import Optional, AsyncGenerator
from datetime import datetime, timezone
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from dotenv import load_dotenv
import requests as http_requests

# Pydantic models for settings API
class OllamaModelRequest(BaseModel):
    model: str

class OllamaHostRequest(BaseModel):
    host: str
    save: bool = False

class CourtListenerTokenRequest(BaseModel):
    token: str
    save: bool = False
from eyecite import get_citations
from rapidfuzz import fuzz

from quote_verify import verify_quote
from coherence_check import check_coherence, coherence_available

load_dotenv()

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup tasks: pre-load CSV, check for updates."""
    # Pre-load CSV into memory on startup (not on first request)
    if os.path.exists(CITATIONS_CSV):
        print("Pre-loading citations CSV into memory...")
        get_citations_df()
        # Check for CSV updates in background (non-blocking)
        import asyncio
        asyncio.get_event_loop().run_in_executor(None, check_csv_update_available)
    yield

CL_TOKEN = os.getenv("COURTLISTENER_TOKEN")
CL_HEADERS = {"Authorization": f"Token {CL_TOKEN}"}
CITATIONS_CSV = os.getenv("CITATIONS_CSV", "data/citations-2026-03-31.csv")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3:latest")
CASE_NAME_MATCH_THRESHOLD = 75
FALLBACK_CONFIDENCE_THRESHOLD = 60
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB in bytes

# Path to .env file -- resolved relative to this script for portability
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

# ------------------------------------------------------------------------------
# In-memory CSV — loaded once at first request, reused for all subsequent queries
# ------------------------------------------------------------------------------
_citations_df = None


def get_citations_df():
    global _citations_df
    if _citations_df is None and os.path.exists(CITATIONS_CSV):
        print(f"Loading citations CSV into memory: {CITATIONS_CSV}")
        _citations_df = pd.read_csv(CITATIONS_CSV, dtype=str)
        print(f"Loaded {len(_citations_df):,} citation records")
    return _citations_df


def write_env_value(key: str, value: str) -> bool:
    """
    Update a single key=value pair in the .env file.

    If the key exists, replaces its value in-place.
    If the key does not exist, appends it.
    Never raises -- returns False on any error.

    Args:
        key: environment variable name (e.g. "OLLAMA_MODEL")
        value: new value to set

    Returns:
        True on success, False on any error
    """
    try:
        if os.path.exists(ENV_PATH):
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()
        else:
            lines = []

        found = False
        new_lines = []
        for line in lines:
            if line.startswith(f"{key}=") or line.startswith(f"{key} ="):
                new_lines.append(f"{key}={value}\n")
                found = True
            else:
                new_lines.append(line)

        if not found:
            new_lines.append(f"{key}={value}\n")

        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        return True
    except Exception as e:
        print(f"write_env_value failed for {key}: {e}")
        return False


# CSV update check -- populated at startup, checked by /health endpoint
CSV_UPDATE_AVAILABLE = False
CSV_LATEST_FILENAME = None


def parse_csv_date(csv_path: Optional[str]):
    """
    Extract the date from a CourtListener bulk CSV filename.

    CourtListener names bulk files as citations-YYYY-MM-DD.csv.
    Returns a datetime.date object or None if no date found.

    Args:
        csv_path: Full path or filename of the CSV file

    Returns:
        datetime.date if parseable, None otherwise
    """
    if not csv_path:
        return None
    import re
    from datetime import date
    filename = os.path.basename(csv_path)
    match = re.search(r"citations-(\d{4})-(\d{2})-(\d{2})", filename)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def check_csv_update_available() -> bool:
    """
    Check CourtListener S3 for bulk citation CSV files newer than the current one.

    Queries the public S3 bucket listing for files matching the citations-*.csv.bz2
    pattern and compares dates against the current CSV filename.

    Returns True if a newer file is found, False otherwise (including on errors).
    Errors are logged but never raised -- update check is informational only.
    """
    global CSV_UPDATE_AVAILABLE, CSV_LATEST_FILENAME

    current_date = parse_csv_date(CITATIONS_CSV)
    if not current_date:
        return False

    try:
        import xml.etree.ElementTree as ET
        resp = http_requests.get(
            "https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/",
            params={"prefix": "bulk-data/citations-", "delimiter": "/"},
            timeout=10
        )
        if resp.status_code != 200:
            return False

        root = ET.fromstring(resp.text)
        ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
        keys = [
            el.text for el in root.findall(".//s3:Key", ns)
            if el.text and el.text.endswith(".csv.bz2")
        ]

        latest = None
        latest_key = None
        for key in keys:
            d = parse_csv_date(key)
            if d and (latest is None or d > latest):
                latest = d
                latest_key = key

        if latest and latest > current_date:
            CSV_UPDATE_AVAILABLE = True
            CSV_LATEST_FILENAME = latest_key.split("/")[-1] if latest_key else None
            print(f"CSV update available: {CSV_LATEST_FILENAME}")
            return True

        CSV_UPDATE_AVAILABLE = False
        return False

    except Exception as e:
        print(f"CSV update check failed: {e}")
        return False


app = FastAPI(
    title="Wilson",
    description="AI Reasoning Auditor -- Open-source legal citation verification",
    version="0.1.0",
    lifespan=lifespan,
)

templates = Jinja2Templates(directory="templates")


# ------------------------------------------------------------------------------
# Models
# ------------------------------------------------------------------------------

class VerifyRequest(BaseModel):
    citation: str
    quoted_text: Optional[str] = None
    proposition: Optional[str] = None


class CitationRequest(BaseModel):
    citation_text: str
    context_snippet: str


class BatchPropositionsRequest(BaseModel):
    citations: list[CitationRequest]


class BatchStreamRequest(BaseModel):
    citations: list[dict]
    depth: str


# ------------------------------------------------------------------------------
# Pipeline functions
# ------------------------------------------------------------------------------

def lookup_citation_api(text: str):
    """
    Look up citation via CourtListener API v4.
    Returns (found, cluster_id, actual_case_name, message)
    """
    try:
        resp = http_requests.post(
            "https://www.courtlistener.com/api/rest/v4/citation-lookup/",
            json={"text": text},
            headers=CL_HEADERS,
            timeout=10
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
        case_name = clusters[0].get("case_name", "Unknown")
        return True, cluster_id, case_name, f"Found -- {case_name} (cluster {cluster_id})"
    except Exception as e:
        return None, None, None, f"API error: {e}"


def fetch_cluster_blocked(cluster_id: int) -> bool:
    """
    Check whether a CourtListener cluster has been flagged for privacy protection.

    CourtListener allows individuals to request de-indexing of their cases.
    When blocked=True, Wilson skips Phase 2 and Phase 3 out of respect for
    that privacy request. On any API error, returns False (do not block on
    uncertainty -- better to over-verify than under-verify).

    Args:
        cluster_id: CourtListener cluster ID from Phase 1 verification

    Returns:
        True if the cluster is privacy-protected, False otherwise
    """
    try:
        resp = http_requests.get(
            f"https://www.courtlistener.com/api/rest/v4/clusters/{cluster_id}/",
            headers=CL_HEADERS,
            timeout=5
        )
        if resp.status_code == 200:
            return bool(resp.json().get("blocked", False))
        return False
    except Exception:
        return False


def lookup_by_name(case_name: str):
    """
    Fallback: search CourtListener by case name when no reporter citation available.
    Returns (found, cluster_id, actual_case_name, full_citation, message)
    """
    try:
        resp = http_requests.get(
            "https://www.courtlistener.com/api/rest/v4/search/",
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


def check_local_csv(vol: str, reporter: str, page: str):
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
    """Extract plaintiff v. defendant from full citation string."""
    match = re.split(r',\s*\d+\s+\w', citation_text)
    return match[0].strip() if match else citation_text.strip()


def verify_case_name(cited: str, actual: str):
    """Returns (score, matches)"""
    score = fuzz.partial_ratio(cited.lower(), actual.lower())
    return score, score >= CASE_NAME_MATCH_THRESHOLD


def csv_status(csv_found) -> str:
    if csv_found is True:
        return "Found"
    if csv_found is False:
        return "Not found"
    return "Not configured" if not os.path.exists(CITATIONS_CSV) else "Error"


def make_event(type: str, **kwargs) -> str:
    """
    Format a Server-Sent Event string.
    Explicit formatting ensures immediate flush on all platforms.
    """
    data = json.dumps({"type": type, **kwargs})
    return f"data: {data}\n\n"


# ------------------------------------------------------------------------------
# Streaming pipeline
# ------------------------------------------------------------------------------

async def run_pipeline(
    citation_text: str,
    quoted_text: Optional[str],
    proposition: Optional[str]
) -> AsyncGenerator[str, None]:
    """
    Run Wilson's full pipeline, yielding SSE-formatted strings as each phase completes.
    Using raw StreamingResponse instead of sse_starlette for reliable cross-platform flushing.
    """
    start_time = time.time()

    yield make_event("status", message="Extracting citation...")
    await asyncio.sleep(0)  # Force flush

    # Extract citation with eyecite
    citations = get_citations(citation_text)
    used_fallback = False
    fallback_citation = None

    if not citations:
        yield make_event("status", message="Standard parsing failed -- trying name-based lookup...")
        await asyncio.sleep(0)

        fb_found, _, fb_case_name, fb_full_citation, fb_message = lookup_by_name(citation_text)

        if fb_found and fb_full_citation:
            # Check confidence before proceeding -- low similarity means
            # Wilson may have found the wrong case
            from rapidfuzz import fuzz as _fuzz
            fallback_similarity = _fuzz.partial_ratio(
                citation_text.lower(),
                (fb_case_name or "").lower()
            )
            if fallback_similarity < FALLBACK_CONFIDENCE_THRESHOLD:
                yield make_event("suggestion", data={
                    "user_input": citation_text,
                    "suggested_citation": fb_full_citation,
                    "suggested_name": fb_case_name,
                    "similarity": round(fallback_similarity),
                    "message": (
                        f"Wilson found a case that may match: {fb_case_name} "
                        f"({fb_full_citation}). Similarity to your input: "
                        f"{round(fallback_similarity)}%. "
                        f"Please verify this is the correct case before proceeding."
                    )
                })
                yield make_event("done", duration=round(time.time() - start_time, 2))
                return

            # Similarity acceptable -- proceed with fallback citation
            citations = get_citations(fb_full_citation)
            used_fallback = True
            fallback_citation = fb_full_citation
            yield make_event("status", message=f"Found via name search: {fb_full_citation}")
            await asyncio.sleep(0)
        else:
            yield make_event("unparseable", message=(
                f"Could not extract a citation from the provided text. "
                f"Wilson needs a full citation including volume, reporter, and page number. "
                f"Example: Obergefell v. Hodges, 576 U.S. 644 (2015). "
                f"Name search result: {fb_message}"
            ))
            yield make_event("done", duration=round(time.time() - start_time, 2))
            return

    if not citations:
        yield make_event("unparseable", message=(
            "Could not extract a citation. "
            "Please include volume, reporter, and page number. "
            "Example: Miranda v. Arizona, 384 U.S. 436 (1966)"
        ))
        yield make_event("done", duration=round(time.time() - start_time, 2))
        return

    c = citations[0]
    groups = c.groups
    vol = groups.get("volume")
    reporter = groups.get("reporter")
    page = groups.get("page")
    meta = getattr(c, "metadata", None)

    parsed = {
        "volume": vol,
        "reporter": reporter,
        "page": page,
        "court": getattr(meta, "court", None),
        "year": getattr(meta, "year", None),
        "plaintiff": getattr(meta, "plaintiff", None),
        "defendant": getattr(meta, "defendant", None),
        "used_fallback": used_fallback,
        "fallback_citation": fallback_citation,
    }

    yield make_event("parsed", data=parsed)
    await asyncio.sleep(0)

    # Phase 1: Existence verification
    yield make_event("phase1_start", message="Checking CourtListener API and local database...")
    await asyncio.sleep(0)

    lookup_text = fallback_citation if used_fallback else citation_text
    api_found, cluster_id, actual_case_name, api_message = lookup_citation_api(lookup_text)
    csv_found, csv_message = check_local_csv(vol, reporter, page)
    csv_stat = csv_status(csv_found)

    if api_found is False:
        yield make_event("phase1_complete", data={
            "verdict": "FABRICATED",
            "api_found": False,
            "local_csv": csv_stat,
            "message": (
                "Citation not found in CourtListener or local database. "
                "This citation does not exist in 18 million federal case records."
            )
        })
        yield make_event("done", duration=round(time.time() - start_time, 2))
        return

    if api_found is None:
        yield make_event("phase1_complete", data={
            "verdict": "ERROR",
            "api_found": None,
            "local_csv": csv_stat,
            "message": api_message
        })
        yield make_event("done", duration=round(time.time() - start_time, 2))
        return

    # Case name verification
    cited_name = extract_case_name(citation_text)
    match_score, name_matches = verify_case_name(cited_name, actual_case_name)
    match_pct = round(match_score)

    if not name_matches:
        yield make_event("phase1_complete", data={
            "verdict": "MISATTRIBUTED",
            "cluster_id": cluster_id,
            "case_name": actual_case_name,
            "cited_name": cited_name,
            "match_pct": match_pct,
            "api_found": True,
            "local_csv": csv_stat,
            "message": (
                f"The citation coordinates ({vol} {reporter} {page}) exist in the database "
                f"but belong to a different case. "
                f"You cited '{cited_name}' but those coordinates belong to '{actual_case_name}'. "
                f"Name similarity: {match_pct}% (minimum {CASE_NAME_MATCH_THRESHOLD}% required). "
                f"This typically means the case name was fabricated while reusing real reporter "
                f"coordinates, or the citation was copied incorrectly."
            )
        })
        yield make_event("done", duration=round(time.time() - start_time, 2))
        return

    yield make_event("phase1_complete", data={
        "verdict": "EXISTS",
        "cluster_id": cluster_id,
        "case_name": actual_case_name,
        "cited_name": cited_name,
        "match_pct": match_pct,
        "api_found": True,
        "local_csv": csv_stat,
        "privacy_protected": False,
        "message": f"Citation verified -- {actual_case_name} ({match_pct}% name match)"
    })
    await asyncio.sleep(0)

    # After phase1_complete yields EXISTS -- check privacy protection before Phase 2/3
    if cluster_id:
        is_blocked = fetch_cluster_blocked(cluster_id)
        if is_blocked:
            yield make_event("phase1_complete", data={
                "verdict": "EXISTS",
                "cluster_id": cluster_id,
                "case_name": actual_case_name,
                "cited_name": cited_name,
                "match_pct": match_pct,
                "api_found": True,
                "local_csv": csv_stat,
                "privacy_protected": True,
                "message": (
                    f"Citation verified -- {actual_case_name} ({match_pct}% name match). "
                    f"This opinion has been flagged for privacy protection. "
                    f"Quote verification and coherence checking are not available."
                )
            })
            yield make_event("done", duration=round(time.time() - start_time, 2))
            return

    # Phase 2: Quote verification
    if quoted_text and cluster_id:
        yield make_event("phase2_start", message="Fetching opinion text and checking quoted language...")
        await asyncio.sleep(0)

        result = verify_quote(quoted_text, cluster_id)
        score = result.get("score", 0) or 0
        score_pct = round(score)
        raw_verdict = result.get("result", "NOT_FOUND")

        if raw_verdict == "EXACT_MATCH":
            display_verdict = "100% MATCH"
        elif raw_verdict == "FUZZY_MATCH":
            display_verdict = f"{score_pct}% MATCH"
        else:
            display_verdict = "NOT FOUND"

        yield make_event("phase2_complete", data={
            "verdict": raw_verdict,
            "display_verdict": display_verdict,
            "score_pct": score_pct,
            "passage": (result.get("passage") or "")[:300] or None,
            "reasoning": result.get("reasoning", "")
        })
        await asyncio.sleep(0)

    # Phase 3: Coherence checking
    if proposition and cluster_id:
        yield make_event("phase3_start", message="Running coherence check -- reading full opinion...")
        await asyncio.sleep(0)

        result = check_coherence(
            proposition=proposition,
            case_name=actual_case_name,
            cluster_id=cluster_id
        )
        yield make_event("phase3_complete", data={
            "verdict": result.get("verdict", "ERROR"),
            "confidence": result.get("confidence"),
            "reasoning": result.get("reasoning", ""),
            "backend_used": result.get("backend_used")
        })
        await asyncio.sleep(0)

    yield make_event("done", duration=round(time.time() - start_time, 2))


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
            "csv_update_available": CSV_UPDATE_AVAILABLE,
            "csv_latest_filename": CSV_LATEST_FILENAME,
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
        },
        "csv_update": {
            "available": CSV_UPDATE_AVAILABLE,
            "latest_filename": CSV_LATEST_FILENAME
        }
    }


@app.get("/settings/ollama-models")
async def get_ollama_models():
    """
    Return available Ollama models by querying the configured Ollama instance.

    Proxies to OLLAMA_HOST/api/tags to avoid CORS issues in the browser.
    Returns empty list with ollama_available=False if Ollama is unreachable.
    """
    try:
        resp = http_requests.get(
            f"{OLLAMA_HOST}/api/tags",
            timeout=5
        )
        if resp.status_code == 200:
            models = [m["name"] for m in resp.json().get("models", [])]
            return {
                "models": models,
                "current": OLLAMA_MODEL,
                "ollama_available": True
            }
        return {"models": [], "current": OLLAMA_MODEL, "ollama_available": False}
    except Exception:
        return {"models": [], "current": OLLAMA_MODEL, "ollama_available": False}


@app.post("/settings/ollama-model")
async def update_ollama_model(request: OllamaModelRequest):
    """
    Update the active Ollama model in memory and persist to .env.

    Does not restart the server -- the new model takes effect on the
    next Phase 3 coherence check call.

    Args:
        request: OllamaModelRequest with model name

    Returns:
        success bool and updated model name
    """
    global OLLAMA_MODEL
    OLLAMA_MODEL = request.model
    write_env_value("OLLAMA_MODEL", request.model)
    return {"success": True, "model": request.model}


@app.post("/settings/ollama-host")
async def update_ollama_host(request: OllamaHostRequest):
    """
    Test and optionally update the Ollama host.

    If save=False, tests the connection without persisting.
    If save=True, tests the connection, updates OLLAMA_HOST global,
    and writes to .env.

    Args:
        request: OllamaHostRequest with host URL and save flag

    Returns:
        success bool, connected bool, available models list
    """
    global OLLAMA_HOST
    try:
        resp = http_requests.get(
            f"{request.host}/api/tags",
            timeout=5
        )
        connected = resp.status_code == 200
        models = []
        if connected:
            models = [m["name"] for m in resp.json().get("models", [])]
    except Exception as e:
        return {
            "success": False,
            "host": request.host,
            "connected": False,
            "models": [],
            "error": f"Cannot reach Ollama at {request.host}"
        }

    if request.save and connected:
        OLLAMA_HOST = request.host
        write_env_value("OLLAMA_HOST", request.host)

    return {
        "success": connected,
        "host": request.host,
        "connected": connected,
        "models": models
    }


@app.post("/settings/courtlistener-token")
async def update_courtlistener_token(request: CourtListenerTokenRequest):
    """
    Validate a CourtListener API token and optionally persist it.

    If save=False, validates without persisting.
    If save=True, validates, updates CL_TOKEN and CL_HEADERS globals,
    and writes to .env.

    Validation: GET to CourtListener API root with the token.
    200 = valid. Anything else = invalid.

    Args:
        request: CourtListenerTokenRequest with token and save flag

    Returns:
        success bool and valid bool
    """
    global CL_TOKEN, CL_HEADERS
    try:
        resp = http_requests.get(
            "https://www.courtlistener.com/api/rest/v4/",
            headers={"Authorization": f"Token {request.token}"},
            timeout=8
        )
        valid = resp.status_code == 200
    except Exception:
        return {"success": False, "valid": False}

    if request.save and valid:
        CL_TOKEN = request.token
        CL_HEADERS = {"Authorization": f"Token {CL_TOKEN}"}
        write_env_value("COURTLISTENER_TOKEN", request.token)

    return {"success": True, "valid": valid}


@app.post("/verify/stream")
async def verify_stream(request: VerifyRequest):
    """
    Stream Wilson pipeline results as Server-Sent Events.
    Uses raw StreamingResponse for reliable flushing on all platforms including Windows.
    """
    citation_text = request.citation.strip()
    quoted_text = request.quoted_text.strip() if request.quoted_text else None
    proposition = request.proposition.strip() if request.proposition else None

    return StreamingResponse(
        run_pipeline(citation_text, quoted_text, proposition),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )


@app.post("/verify")
async def verify(request: VerifyRequest):
    """
    Run Wilson pipeline and return complete JSON response.
    Use /verify/stream for real-time streaming results.
    """
    citation_text = request.citation.strip()
    quoted_text = request.quoted_text.strip() if request.quoted_text else None
    proposition = request.proposition.strip() if request.proposition else None

    result = {
        "citation": citation_text,
        "version": "0.0.5",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    async for raw in run_pipeline(citation_text, quoted_text, proposition):
        # raw is "data: {...}\n\n" — extract the JSON
        if not raw.startswith("data: "):
            continue
        try:
            e = json.loads(raw[6:].strip())
        except Exception:
            continue
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


@app.post("/batch/propositions")
async def batch_propositions(request: BatchPropositionsRequest):
    """
    Generate proposition suggestions for multiple citations in a single request.
    Calls suggest_propositions_batch() from document_parser.py.
    """
    from document_parser import suggest_propositions_batch

    # Convert request citations to the format expected by suggest_propositions_batch
    citations_list = [
        {
            "citation_text": c.citation_text,
            "context_snippet": c.context_snippet,
        }
        for c in request.citations
    ]

    # Generate propositions for all citations
    propositions = await suggest_propositions_batch(citations_list)

    # Build response
    return {
        "propositions": propositions,
        "total_citations": len(request.citations),
        "backend_used_count": sum(
            1 for p in propositions if p.get("backend_used") == "ollama"
        ),
    }


@app.post("/batch/stream")
async def batch_stream(request: BatchStreamRequest):
    """
    Stream verification results for multiple citations.
    Uses raw StreamingResponse with text/event-stream.
    """
    async def stream_citations():
        total = len(request.citations)
        start_time = time.time()

        # Batch start event
        yield make_event("batch_start", total=total)
        await asyncio.sleep(0)

        for i, citation in enumerate(request.citations):
            citation_text = citation.get("citation_text", "").strip()
            proposition = citation.get("proposition", "").strip()

            # Batch progress event
            yield make_event("batch_progress", current=i+1, total=total)
            await asyncio.sleep(0)

            # Run pipeline with depth control
            quoted_text = None
            if request.depth in ("quotes", "full"):
                quoted_text = None  # Batch stream doesn't include quoted_text

            # Stream pipeline results for this citation
            async for raw in run_pipeline(citation_text, quoted_text, proposition):
                # Send directly to client
                yield raw
                await asyncio.sleep(0)

            # Heartbeat every 3 seconds during long calls
            elapsed = time.time() - start_time
            if elapsed > 3 and request.depth == "full":
                yield make_event("heartbeat")
                await asyncio.sleep(0)

        # Batch done event
        duration = round(time.time() - start_time, 2)
        yield make_event("batch_done", total=total, duration=duration)

    return StreamingResponse(
        stream_citations(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )


@app.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    """Serve the document upload form."""
    return templates.TemplateResponse(
        request=request,
        name="upload.html"
    )


@app.post("/upload/parse")
async def parse_upload_file(file: UploadFile = File(...)):
    """
    Parse an uploaded document and extract citations with context.
    Enforces 50MB file size limit.
    Returns JSON with extraction results.
    """
    from document_parser import extract_text, extract_citations_with_context

    # Check file size
    file_size = 0
    chunks = []
    try:
        for chunk in file.file:
            file_size += len(chunk)
            chunks.append(chunk)
            if file_size > MAX_UPLOAD_SIZE:
                raise ValueError(
                    f"File too large: {file_size / (1024 * 1024):.2f}MB exceeds 50MB limit"
                )
    except Exception as e:
        raise ValueError(f"Error reading file: {e}")

    file.file.seek(0)  # Reset file pointer after reading chunks
    file_bytes = b''.join(chunks)

    try:
        # Extract text from file
        text_result = extract_text(file_bytes, file.filename)

        # Extract citations with context
        citations = extract_citations_with_context(
            text_result["text"],
            text_result["page_boundaries"]
        )

        # Build response
        response = {
            "filename": file.filename,
            "page_count": text_result["page_count"],
            "citation_count": len(citations),
            "citations": citations,
            "chunked": True,
            "total_pages": text_result["page_count"],
        }

        return response

    except ValueError as e:
        raise ValueError(str(e))
    except RuntimeError as e:
        raise ValueError(f"Extraction failed: {e}")
    except Exception as e:
        raise ValueError(f"Unexpected error: {e}")
