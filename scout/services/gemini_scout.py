"""
services/gemini_scout.py
-------------------------
Isolated service layer that talks to Google's Gemini API to discover
real, currently-open opportunities (funded MSc programs, quant roles,
hackathons, fellowships) using live Google Search grounding, and returns
strictly validated, structured JSON.

This module has NO Django ORM knowledge - it only knows how to call
Gemini and hand back clean Python dicts. `management/commands/run_scout.py`
is responsible for persisting the results.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings
from google import genai
from google.genai import types

logger = logging.getLogger("scout")


# ---------------------------------------------------------------------------
# The JSON schema we force Gemini to answer in. Because `google_search`
# grounding and `response_mime_type=application/json` cannot always be
# combined natively in every SDK version, we ALSO enforce the shape via a
# strict instruction + a post-hoc validation/repair pass (see `_extract_json`).
# ---------------------------------------------------------------------------
RESPONSE_SCHEMA_DESCRIPTION = """
Return ONLY a JSON array (no markdown fences, no prose, no commentary).
Each element must be an object with EXACTLY these keys:

- "title": string. The exact name of the opportunity/program/role.
- "organization": string. The university, company, or org running it.
- "category": one of ["MSc", "PhD", "Quant Role", "SWE Role", "Hackathon", "Fellowship", "Scholarship", "Other"].
- "url": string. Direct URL to the official page (not a search results page).
- "funding_status": one of ["Fully Funded", "Partial", "Cash Prize", "Paid Role", "Unfunded"].
- "deadline": string in YYYY-MM-DD format. If genuinely rolling/unknown, use "".
- "summary": string, 2-4 sentences, plain text.
- "eligibility_criteria": string, plain text, key eligibility bullet points joined by "; ".

If you cannot verify a field, use an empty string for it rather than guessing wildly,
but make a best-effort real answer using search results. Do not invent URLs.
Only include opportunities that appear to currently be open (deadline today or later,
or rolling/no fixed deadline). Do not include duplicates within the array.
"""

# ---------------------------------------------------------------------------
# Search "lanes" - rotated across runs to keep coverage broad without
# blowing the free-tier daily request budget in a single run.
# ---------------------------------------------------------------------------
SEARCH_LANES: list[dict[str, str]] = [
    
    {
        "key": "swe_roles",
        "prompt": (
            "Search for entry-level or new-grad Software Engineer / Backend Engineer roles at "
            "well-known tech companies that explicitly offer visa sponsorship or relocation "
            "support for candidates currently based in Nigeria or Africa, in the UK, EU, Canada, "
            "or the Middle East (Dubai tech hubs)."
        ),
    },
    {
        "key": "hackathons",
        "prompt": (
            "Search for global technology hackathons, AI/ML competitions, or coding competitions "
            "with cash prizes that are open to international/remote participants right now, with "
            "submission deadlines that have not yet passed. Include university-run and "
            "corporate-sponsored hackathons (e.g. MLH, Devpost-hosted, Kaggle competitions)."
        ),
    },
        {
        "key": "fellowships",
        "prompt": (
            "Search for tech, research, or entrepreneurship fellowships open to applicants from "
            "Nigeria or Africa that are fully funded or provide a stipend, in areas like software "
            "engineering, AI research, quantitative research, or data science, with open "
            "application windows right now."
        ),
    },
    

]


@dataclass
class ScoutResult:
    lane_key: str
    raw_text: str = ""
    items: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


def _get_client() -> genai.Client:
    if not settings.GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set in the environment.")
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def _build_contents(lane_prompt: str) -> str:
    return (
        f"{lane_prompt}\n\n"
        "Use live Google Search to find REAL, currently-open opportunities. "
        "Verify each URL points to an official/legitimate source before including it.\n\n"
        f"{RESPONSE_SCHEMA_DESCRIPTION}"
    )


def _extract_json(raw_text: str) -> list[dict[str, Any]]:
    """
    Gemini occasionally wraps JSON in markdown fences, adds stray text even
    when instructed not to, or emits raw control characters (literal
    newlines/tabs) inside string values that break strict JSON parsing.
    This defensively extracts and repairs the first valid JSON array.
    """
    text = raw_text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()

    # Fast path
    try:
        parsed = json.loads(text, strict=False)
        if isinstance(parsed, dict):
            parsed = parsed.get("results") or parsed.get("opportunities") or [parsed]
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass

    # Fallback: find the outermost [ ... ] block
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        snippet = text[start : end + 1]
        try:
            parsed = json.loads(snippet, strict=False)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse extracted JSON snippet: %s", exc)
            # Last resort: Gemini sometimes emits literal control characters
            # (raw newlines/tabs) inside string values, which even strict=False
            # doesn't always tolerate consistently. Strip control chars that
            # appear *inside* quoted strings before retrying.
            repaired = _repair_control_chars_in_strings(snippet)
            try:
                parsed = json.loads(repaired, strict=False)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError as exc2:
                logger.warning("Repair pass also failed: %s", exc2)

    raise ValueError("Could not extract a valid JSON array from Gemini response.")


def _repair_control_chars_in_strings(text: str) -> str:
    """
    Walk the raw text and replace literal control characters (newline, tab,
    carriage return, etc.) that occur inside JSON string literals with their
    escaped equivalents, without disturbing the surrounding JSON structure.
    """
    out = []
    in_string = False
    escape_next = False
    for ch in text:
        if escape_next:
            out.append(ch)
            escape_next = False
            continue
        if ch == "\\":
            out.append(ch)
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            out.append(ch)
            continue
        if in_string and ch == "\n":
            out.append("\\n")
            continue
        if in_string and ch == "\r":
            out.append("\\r")
            continue
        if in_string and ch == "\t":
            out.append("\\t")
            continue
        if in_string and ord(ch) < 0x20:
            # Drop other stray control characters entirely
            continue
        out.append(ch)
    return "".join(out)


def run_lane(lane: dict[str, str]) -> ScoutResult:
    """Execute a single search lane against Gemini with Google Search grounding."""
    client = _get_client()
    contents = _build_contents(lane["prompt"])

    try:
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.4,
                max_output_tokens=8192,
            ),
        )
    except Exception as exc:  # noqa: BLE001 - we want to log & continue other lanes
        logger.exception("Gemini API call failed for lane '%s'", lane["key"])
        return ScoutResult(lane_key=lane["key"], error=str(exc))

    raw_text = (response.text or "").strip()

    try:
        items = _extract_json(raw_text)
    except ValueError as exc:
        logger.error("Lane '%s' returned unparseable content: %s", lane["key"], exc)
        return ScoutResult(lane_key=lane["key"], raw_text=raw_text, error=str(exc))

    validated = [item for item in (validate_item(i) for i in items) if item is not None]
    return ScoutResult(lane_key=lane["key"], raw_text=raw_text, items=validated)


VALID_CATEGORIES = {"MSc", "PhD", "Quant Role", "SWE Role", "Hackathon", "Fellowship", "Scholarship", "Other"}
VALID_FUNDING = {"Fully Funded", "Partial", "Cash Prize", "Paid Role", "Unfunded"}


def validate_item(item: dict[str, Any]) -> dict[str, Any] | None:
    """Coerce/validate a single Gemini result item. Returns None if unusable."""
    if not isinstance(item, dict):
        return None

    title = str(item.get("title") or "").strip()
    url = str(item.get("url") or "").strip()
    if not title or not url or not url.startswith("http"):
        return None

    category = item.get("category") if item.get("category") in VALID_CATEGORIES else "Other"
    funding_status = (
        item.get("funding_status") if item.get("funding_status") in VALID_FUNDING else "Unfunded"
    )

    deadline_raw = str(item.get("deadline") or "").strip()
    deadline = deadline_raw if _looks_like_date(deadline_raw) else ""

    return {
        "title": title[:300],
        "organization": str(item.get("organization") or "").strip()[:200],
        "category": category,
        "url": url[:600],
        "funding_status": funding_status,
        "deadline": deadline,
        "summary": str(item.get("summary") or "").strip(),
        "eligibility_criteria": str(item.get("eligibility_criteria") or "").strip(),
    }


def _looks_like_date(value: str) -> bool:
    if not value or len(value) != 10:
        return False
    parts = value.split("-")
    return len(parts) == 3 and all(p.isdigit() for p in parts)


def run_all_lanes(lane_keys: list[str] | None = None) -> list[ScoutResult]:
    """
    Run every configured search lane (or a filtered subset by key) and return
    one ScoutResult per lane. Each lane is an independent Gemini call, so a
    failure in one lane never blocks the others.
    """
    lanes = SEARCH_LANES if not lane_keys else [l for l in SEARCH_LANES if l["key"] in lane_keys]
    results = []
    for lane in lanes:
        logger.info("Running scout lane: %s", lane["key"])
        results.append(run_lane(lane))
    return results
