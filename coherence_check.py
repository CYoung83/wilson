"""
Wilson - Coherence Checking Module

Given a legal proposition, a cited case, and the full opinion text,
asks a local LLM via Ollama whether the case actually supports
the proposition it is cited for.

This is Phase 3 of Wilson's pipeline:
  Phase 1: Does the citation exist? (smoke_test.py)
  Phase 2: Does the quoted text appear in the opinion? (quote_verify.py)
  Phase 3: Does the case actually support the proposition? (this file)

Phase 3 requires a local Ollama instance. Configure OLLAMA_HOST,
OLLAMA_MODEL, and OLLAMA_CONTEXT_SIZE in your .env file.

If not configured, Wilson reports Phase 3 as skipped and completes
Phases 1 and 2 only.

Uses local inference — no case data leaves the machine.
"""

import os
import re
import json
import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

CL_TOKEN = os.getenv("COURTLISTENER_TOKEN")
CL_HEADERS = {"Authorization": f"Token {CL_TOKEN}"}

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
OLLAMA_CONTEXT_SIZE = int(os.getenv("OLLAMA_CONTEXT_SIZE", "32000"))

SYSTEM_PROMPT = """You are a legal citation auditor. You ALWAYS respond with only a valid JSON object and nothing else. Never respond with prose, explanation, or thinking before or after the JSON. Your entire response must be a single parseable JSON object in this exact format:

{"verdict": "SUPPORTS", "confidence": "HIGH", "reasoning": "Your explanation here."}

Valid values for verdict: SUPPORTS, DOES_NOT_SUPPORT, UNCERTAIN
Valid values for confidence: HIGH, MEDIUM, LOW"""


def coherence_available():
    """
    Check whether a local LLM is configured and reachable.
    Returns (available: bool, message: str)
    """
    if not OLLAMA_HOST:
        return False, "OLLAMA_HOST not configured in .env"
    try:
        resp = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            model_names = [m["name"] for m in models]
            if any(OLLAMA_MODEL in name for name in model_names):
                return True, f"Ollama reachable at {OLLAMA_HOST} — model {OLLAMA_MODEL} loaded (context: {OLLAMA_CONTEXT_SIZE:,} tokens)"
            else:
                return False, f"Ollama reachable but model '{OLLAMA_MODEL}' not found. Available: {model_names}"
        return False, f"Ollama returned status {resp.status_code}"
    except requests.exceptions.ConnectionError:
        return False, f"Cannot reach Ollama at {OLLAMA_HOST} — is it running?"
    except Exception as e:
        return False, f"Ollama check failed: {e}"


def fetch_opinion_text(cluster_id):
    """
    Fetch full opinion text from CourtListener.
    Returns plain text with HTML stripped, or None on failure.
    """
    url = f"https://www.courtlistener.com/api/rest/v4/opinions/?cluster={cluster_id}&fields=id,html_with_citations"
    resp = requests.get(url, headers=CL_HEADERS, timeout=15)

    if resp.status_code != 200:
        return None

    data = resp.json()
    results = data.get("results", [])

    if not results:
        return None

    full_text = ""
    for opinion in results:
        html = opinion.get("html_with_citations", "")
        if html:
            soup = BeautifulSoup(html, "lxml")
            full_text += soup.get_text(separator=" ") + "\n"

    return full_text.strip() if full_text else None


def truncate_opinion(opinion_text, max_chars=None):
    """
    Truncate opinion text to fit in context window.
    Uses OLLAMA_CONTEXT_SIZE from .env if max_chars not specified.

    With large context models (nemotron 256k, llama3.1 128k),
    sends the full opinion text without truncation.

    Conversion: roughly 3 chars per token, leaving room for
    prompt template and system message overhead.
    """
    if max_chars is None:
        max_chars = OLLAMA_CONTEXT_SIZE * 3

    if len(opinion_text) <= max_chars:
        return opinion_text

    # For truncated opinions: first 75%, last 25%
    # Holdings appear at start, conclusions at end
    first_chunk = int(max_chars * 0.75)
    last_chunk = max_chars - first_chunk

    return (
        opinion_text[:first_chunk] +
        "\n\n[... opinion truncated — context limit reached ...]\n\n" +
        opinion_text[-last_chunk:]
    )


def extract_verdict_from_prose(prose):
    """
    Fallback verdict extraction when JSON parsing fails.
    Scans prose for verdict indicators and returns best guess.
    """
    prose_lower = prose.lower()

    supports_phrases = [
        "supports the proposition",
        "does support",
        "seminal case establishing",
        "correctly states",
        "accurately reflects",
        "establishes the two-prong",
        "establishes the standard",
        "case does stand for",
        "proposition is correct",
        "holding supports",
    ]

    does_not_support_phrases = [
        "does not support",
        "no discussion of",
        "not address",
        "does not address",
        "irrelevant to",
        "does not hold",
        "contains no",
        "no mention of",
        "cannot support",
        "fails to support",
        "not about",
    ]

    uncertain_phrases = [
        "unclear",
        "ambiguous",
        "partially supports",
        "could be read",
        "might support",
    ]

    supports_score = sum(1 for p in supports_phrases if p in prose_lower)
    not_support_score = sum(1 for p in does_not_support_phrases if p in prose_lower)
    uncertain_score = sum(1 for p in uncertain_phrases if p in prose_lower)

    if supports_score > not_support_score and supports_score > uncertain_score:
        return "SUPPORTS"
    elif not_support_score > supports_score:
        return "DOES_NOT_SUPPORT"
    elif uncertain_score > 0:
        return "UNCERTAIN"
    else:
        return None


def check_coherence(proposition, case_name, cluster_id, opinion_text=None):
    """
    Ask the local LLM whether a cited case supports a legal proposition.

    Args:
        proposition: The legal argument the case is cited for
        case_name: Name of the cited case
        cluster_id: CourtListener cluster ID
        opinion_text: Full opinion text (fetched if not provided)

    Returns:
        dict with keys:
            verdict: SUPPORTS | DOES_NOT_SUPPORT | UNCERTAIN | SKIPPED | ERROR
            confidence: HIGH | MEDIUM | LOW | None
            reasoning: Explanation
            thinking: LLM chain of thought if available
    """
    # Check LLM availability first
    available, availability_message = coherence_available()
    if not available:
        return {
            "verdict": "SKIPPED",
            "confidence": None,
            "reasoning": (
                f"Phase 3 skipped — {availability_message}. "
                f"Configure OLLAMA_HOST and OLLAMA_MODEL in .env to enable coherence checking."
            ),
            "thinking": None
        }

    if opinion_text is None:
        print(f"  [COHERENCE] Fetching opinion for cluster {cluster_id}...")
        opinion_text = fetch_opinion_text(cluster_id)

    if not opinion_text:
        return {
            "verdict": "ERROR",
            "confidence": None,
            "reasoning": f"Could not retrieve opinion text for cluster {cluster_id}",
            "thinking": None
        }

    truncated = truncate_opinion(opinion_text)
    char_count = len(truncated)
    was_truncated = len(opinion_text) > char_count

    print(f"  [COHERENCE] Opinion: {len(opinion_text):,} chars"
          f"{' → truncated to ' + str(char_count) + ' chars' if was_truncated else ' (full text)'}")

    prompt = f"""Determine whether the cited case supports the legal proposition.

LEGAL PROPOSITION:
"{proposition}"

CITED CASE:
{case_name}

OPINION TEXT:
{truncated}

---

Respond with ONLY a JSON object. No prose. No explanation outside the JSON.
Example: {{"verdict": "SUPPORTS", "confidence": "HIGH", "reasoning": "The case holds X which directly supports the proposition."}}

JSON RESPONSE:"""

    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "system": SYSTEM_PROMPT,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 1024,
                    "num_ctx": OLLAMA_CONTEXT_SIZE
                }
            },
            timeout=300
        )

        data = resp.json()
        raw_response = data.get("response", "")

        # Extract and remove thinking block if present
        thinking = None
        thinking_match = re.search(r'<think>(.*?)</think>', raw_response, re.DOTALL)
        if thinking_match:
            thinking = thinking_match.group(1).strip()
            raw_response = re.sub(
                r'<think>.*?</think>', '', raw_response, flags=re.DOTALL
            ).strip()

        # Try markdown code block first, then bare JSON
        json_str = None
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', raw_response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_match = re.search(r'(\{[^{}]*"verdict"[^{}]*\})', raw_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)

        if json_str:
            result = json.loads(json_str)
            return {
                "verdict": result.get("verdict", "UNCERTAIN"),
                "confidence": result.get("confidence", "LOW"),
                "reasoning": result.get("reasoning", "No reasoning provided"),
                "thinking": thinking
            }

        # Fallback: extract verdict from prose
        print(f"  [COHERENCE] JSON parse failed, attempting prose extraction...")
        fallback_verdict = extract_verdict_from_prose(raw_response)

        if fallback_verdict:
            reasoning_snippet = raw_response.strip()[:400]
            return {
                "verdict": fallback_verdict,
                "confidence": "LOW",
                "reasoning": f"[Extracted from prose] {reasoning_snippet}",
                "thinking": thinking
            }

        return {
            "verdict": "ERROR",
            "confidence": None,
            "reasoning": f"Could not parse model response: {raw_response[:200]}",
            "thinking": thinking
        }

    except json.JSONDecodeError as e:
        return {
            "verdict": "ERROR",
            "confidence": None,
            "reasoning": f"JSON parse error: {e}. Raw: {raw_response[:200]}",
            "thinking": None
        }
    except Exception as e:
        return {
            "verdict": "ERROR",
            "confidence": None,
            "reasoning": f"Inference error: {e}",
            "thinking": None
        }


if __name__ == "__main__":
    print("=" * 60)
    print("WILSON — COHERENCE CHECK TEST")
    print("=" * 60)

    # Check LLM availability before running tests
    available, message = coherence_available()
    print(f"\nLLM Status: {message}")

    if not available:
        print("\nPhase 3 coherence checking requires a local Ollama instance.")
        print("Set OLLAMA_HOST and OLLAMA_MODEL in your .env file.")
        print("Install Ollama at https://ollama.com")
        exit(0)

    # Test 1: Correct use of Strickland
    print("\n[TEST 1] Correct proposition — Strickland")
    print("Proposition: To prevail on an ineffective assistance claim,")
    print("a defendant must show deficient performance and prejudice.")

    result = check_coherence(
        proposition="To prevail on an ineffective assistance of counsel claim, a defendant must demonstrate that counsel's performance was deficient and that the deficient performance prejudiced the defense.",
        case_name="Strickland v. Washington",
        cluster_id=111170
    )

    print(f"\n  Verdict:    {result['verdict']}")
    print(f"  Confidence: {result['confidence']}")
    print(f"  Reasoning:  {result['reasoning']}")
    if result['thinking']:
        print(f"  Thinking:   {result['thinking'][:300]}...")

    print("\n" + "-" * 60)

    # Test 2: Wrong proposition attributed to Strickland
    print("\n[TEST 2] Incorrect proposition — Strickland")
    print("Proposition: Defense counsel must be present at all")
    print("pretrial hearings or the conviction is automatically reversed.")

    result2 = check_coherence(
        proposition="Defense counsel must be physically present at all pretrial hearings or the resulting conviction must be automatically reversed on appeal.",
        case_name="Strickland v. Washington",
        cluster_id=111170
    )

    print(f"\n  Verdict:    {result2['verdict']}")
    print(f"  Confidence: {result2['confidence']}")
    print(f"  Reasoning:  {result2['reasoning']}")
    if result2['thinking']:
        print(f"  Thinking:   {result2['thinking'][:300]}...")

    print("\n" + "-" * 60)

    # Test 3: Subtle misrepresentation
    print("\n[TEST 3] Subtle misrepresentation — Strickland")
    print("Proposition: A defendant is entitled to a new trial whenever")
    print("counsel makes any error during proceedings.")

    result3 = check_coherence(
        proposition="A criminal defendant is entitled to a new trial whenever defense counsel makes any error during the proceedings, regardless of whether that error affected the outcome.",
        case_name="Strickland v. Washington",
        cluster_id=111170
    )

    print(f"\n  Verdict:    {result3['verdict']}")
    print(f"  Confidence: {result3['confidence']}")
    print(f"  Reasoning:  {result3['reasoning']}")
    if result3['thinking']:
        print(f"  Thinking:   {result3['thinking'][:300]}...")

    print("\n" + "=" * 60)
    print("COHERENCE CHECK TEST COMPLETE")
    print("=" * 60)
