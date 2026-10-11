"""CourtListener - US federal and state litigation.

The v4 search API is rate-limited for anonymous callers and generally needs a
free API token. Without one the source degrades to an explicit "unavailable"
rather than silently reporting zero litigation, so the risk engine can tell the
difference between "no cases" and "we could not look".
"""

from __future__ import annotations

import logging
import re

from app.config import settings
from app.http_client import fetch_json
from app.resolution.normalize import name_tokens

log = logging.getLogger(__name__)

SEARCH_URL = "https://www.courtlistener.com/api/rest/v4/search/"


def _headers() -> dict[str, str]:
    if settings.courtlistener_api_token:
        return {"Authorization": f"Token {settings.courtlistener_api_token}"}
    return {}


def _relevance(text: str, name: str) -> float:
    query_tokens = name_tokens(name)
    if not query_tokens:
        return 0.0
    body_tokens = name_tokens(text)
    return len(query_tokens & body_tokens) / len(query_tokens)


async def search(name: str, limit: int = 10) -> dict:
    """Returns {'available': bool, 'cases': [...], 'note': str|None}."""
    query_name = re.sub(r'["\\\x00-\x1f]', " ", name).strip()
    params = {
        "q": f'"{query_name}"',
        "type": "r",  # RECAP: federal district and appellate dockets
        "order_by": "score desc",
    }
    data = await fetch_json(
        SEARCH_URL, params=params, headers=_headers(), ttl_hours=24, retries=2
    )

    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        return {
            "available": False,
            "cases": [],
            "note": (
                "CourtListener unavailable - set COURTLISTENER_API_TOKEN for "
                "litigation coverage"
            ),
        }

    cases: list[dict] = []
    seen: set[tuple] = set()
    unidentified = 0
    for item in (data.get("results") or [])[: limit * 3]:
        case_name = item.get("caseName") or item.get("case_name") or ""
        if not case_name:
            continue
        # Suit descriptions and docket numbers do not identify a party.
        relevance = _relevance(case_name, name)
        if relevance < 1.0:
            continue

        docket_id = item.get("docket_id")
        court = item.get("court") or item.get("court_id")
        docket_number = item.get("docketNumber")
        if not docket_id and not (court and docket_number):
            unidentified += 1
            continue
        # RECAP search hits can be documents from the same docket. Document
        # IDs must never be used as docket IDs or counted as separate cases.
        key = ("id", str(docket_id)) if docket_id else (
            "number", str(court), str(docket_number))
        if key in seen:
            continue
        seen.add(key)
        cases.append(
            {
                "case": case_name,
                "docket_id": docket_id,
                "match_basis": "case_title_name_match",
                "court": item.get("court") or item.get("court_id"),
                "date": item.get("dateFiled") or item.get("dateArgued"),
                "docket_number": item.get("docketNumber"),
                "nature_of_suit": item.get("suitNature"),
                "url": (
                    f"https://www.courtlistener.com/docket/{docket_id}/"
                    if docket_id
                    else None
                ),
                "confidence": round(min(0.97, 0.55 + 0.4 * relevance), 4),
            }
        )
        if len(cases) >= limit:
            break

    source_count = data.get("count")
    return {
        "available": True, "cases": cases,
        "note": None if cases else "No qualifying title matches among retrieved hits; this is a limited search.",
        "search_query": params["q"], "returned_count": len(cases),
        "source_result_count": source_count, "limit": limit,
        "truncated": bool(data.get("next")) or len(cases) >= limit
        or len(data.get("results") or []) > limit * 3
        or (isinstance(source_count, int) and source_count > len(data.get("results") or [])),
        "unidentified_rejected_count": unidentified,
        "match_basis": "case_title_name_match",
    }
