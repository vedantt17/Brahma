"""Public Google News RSS search; headline evidence, never article bodies."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

from app.http_client import fetch
from app.risk import bias
from app.risk.taxonomy import categories_for, SEARCH_TERMS
from app.risk.term_matcher import match_terms
from app.sources import gdelt

SEARCH_URL = "https://news.google.com/rss/search"


async def search(name: str) -> gdelt.MediaResults:
    try:
        primary = await _search(name)
    except RuntimeError:
        primary = None
    if primary:
        return primary
    # Search engines need not apply risk terms identically. A second bounded
    # subject-only feed can recover headlines; local entity/date/risk checks
    # remain mandatory, so generic news does not become adverse evidence.
    try:
        broad = await _search(name, broad=True)
    except RuntimeError:
        if primary is None:
            raise
        primary.search_metadata["broad_search_available"] = False
        return primary
    broad.search_metadata["broad_search_available"] = True
    broad.search_metadata["targeted_search_available"] = primary is not None
    broad.search_metadata["targeted_raw_count"] = primary.search_metadata["raw_count"] if primary is not None else None
    return broad


async def search_recent(name: str) -> gdelt.MediaResults:
    """Recent subject headlines, separately from adverse-media evidence."""
    return await _search(name, broad=True, include_general=True)


async def _search(name: str, *, broad: bool = False, include_general: bool = False) -> gdelt.MediaResults:
    subject = gdelt.search_name(name)
    if not subject:
        raise ValueError("A subject is required for news search")
    days = gdelt.search_months() * 30
    risk = " OR ".join(f'"{term}"' if " " in term else term
                       for term in dict.fromkeys([*SEARCH_TERMS, "sued", "antitrust", "scandal", "fined", "controversy"]))
    query = f'"{subject}" ' + ("" if broad else f"({risk}) ") + f"when:{days}d"
    body = await fetch(SEARCH_URL, params={"q": query, "hl": "en-US", "gl": "US",
                                         "ceid": "US:en"}, ttl_hours=1, retries=1)
    if not body or len(body) > 2_000_000 or re.search(r"<!\s*(?:DOCTYPE|ENTITY)", body, re.I):
        raise RuntimeError("Google News feed unavailable or unsafe")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise RuntimeError("Google News returned malformed RSS") from exc
    channel = root.find("channel") if root.tag == "rss" else None
    if channel is None:
        raise RuntimeError("Google News returned an unexpected feed")
    items = channel.findall("item")
    rows, seen = [], set()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    for item in items[:100]:
        title = (item.findtext("title") or "").strip()
        source = item.find("source")
        publisher = (source.text or "").strip() if source is not None else "Google News"
        # Google appends the publisher to its title; don't classify that text.
        if publisher and title.endswith(" - " + publisher):
            title = title[:-(len(publisher) + 3)].strip()
        link = (item.findtext("link") or "").strip()
        parsed_link = urlparse(link)
        if parsed_link.scheme not in {"http", "https"} or not parsed_link.netloc:
            continue
        try:
            date = parsedate_to_datetime(item.findtext("pubDate") or "")
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            continue
        if not cutoff <= date <= now + timedelta(hours=24):
            continue
        key = title.casefold()
        if not title or key in seen or gdelt._MARKET_NOISE.search(title):
            continue
        if gdelt._mentions_company(title, subject) < 1.0:
            continue
        categories = categories_for(title)
        if not categories and not include_general:
            continue
        seen.add(key)
        rows.append({"title": title, "source": publisher, "provider": "Google News RSS",
                     "url": link, "date": date.astimezone(timezone.utc).date().isoformat(),
                     "language": "English", "source_country": None,
                     "evidence_scope": "general_news" if include_general else "adverse_media",
                     "sentiment": "unclassified" if include_general else "negative",
                     "severity": round(max((c["severity"] for c in categories), default=0), 2),
                     "categories": categories, "category_keys": [c["key"] for c in categories],
                     "risk_terms": list(match_terms(title)), "body": None,
                     "bias": bias.analyze(title), "confidence": .95,
                     "matched_terms": sorted({t for c in categories for t in c["matched_terms"]})})
    rows.sort(key=lambda a: a["date"] if include_general else a["severity"], reverse=True)
    return gdelt.MediaResults(rows[:40], {
        "provider": "Google News RSS", "search_name": subject, "query": query,
        "lookback_months": gdelt.search_months(), "lookback_days": days,
        "query_strategy": "subject_only" if broad else "subject_and_risk_terms",
        "evidence_scope": "general_news" if include_general else "adverse_media",
        "raw_count": len(items),
        "matched_count": len(rows), "returned_count": min(40, len(rows)),
        "max_records": 100, "result_limit_reached": len(items) >= 100 or len(rows) > 40,
    })
