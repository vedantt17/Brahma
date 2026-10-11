"""Public Google News RSS search; headline evidence, never article bodies."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

from app.http_client import fetch
from app.risk import bias
from app.risk.taxonomy import categories_for
from app.risk.term_matcher import match_terms
from app.sources import gdelt

SEARCH_URL = "https://news.google.com/rss/search"


async def search(name: str) -> gdelt.MediaResults:
    subject = gdelt.search_name(name)
    if not subject:
        raise ValueError("A subject is required for news search")
    days = gdelt.search_months() * 30
    query = (f'"{subject}" (lawsuit OR sued OR investigation OR fraud OR '
             f'antitrust OR settlement OR scandal OR fined) when:{days}d')
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
        if not categories:
            continue
        seen.add(key)
        rows.append({"title": title, "source": publisher, "provider": "Google News RSS",
                     "url": link, "date": date.astimezone(timezone.utc).date().isoformat(),
                     "language": "English", "source_country": None, "sentiment": "negative",
                     "severity": round(max(c["severity"] for c in categories), 2),
                     "categories": categories, "category_keys": [c["key"] for c in categories],
                     "risk_terms": list(match_terms(title)), "body": None,
                     "bias": bias.analyze(title), "confidence": .95,
                     "matched_terms": sorted({t for c in categories for t in c["matched_terms"]})})
    rows.sort(key=lambda a: a["severity"], reverse=True)
    return gdelt.MediaResults(rows[:40], {
        "provider": "Google News RSS", "search_name": subject, "query": query,
        "lookback_months": gdelt.search_months(), "raw_count": len(items),
        "matched_count": len(rows), "returned_count": min(40, len(rows)),
        "max_records": 100, "result_limit_reached": len(items) >= 100 or len(rows) > 40,
    })
