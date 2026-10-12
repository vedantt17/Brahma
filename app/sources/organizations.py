"""Public Wikidata organization profiles, separate from legal registry identities."""
from __future__ import annotations

import asyncio
import time

from app.config import settings
from app.http_client import fetch_json
from app.resolution.engine import EntityRecord
from app.resolution.selection import company_name_key
from app.sources.people import API, _claims, _ids, _label, _qualifier_time, _value


class OrganizationRecords(list):
    def __init__(self, records, metadata):
        super().__init__(records)
        self.search_metadata = metadata


async def _entities(ids: list[str], *, labels_only: bool = False) -> dict:
    data = await fetch_json(API, params={"action": "wbgetentities", "ids": "|".join(ids),
                                      "format": "json", "languages": "en",
                                      "languagefallback": "1",
                                      "props": "labels" if labels_only else
                                      "labels|aliases|descriptions|claims"}, ttl_hours=24)
    if not isinstance(data, dict) or not isinstance(data.get("entities"), dict):
        raise RuntimeError("Wikidata organization profiles unavailable or malformed")
    return data["entities"]


async def search(name: str, country: str | None = None, limit: int = 20) -> OrganizationRecords:
    """Find public organization profiles; these never verify a legal entity."""
    started = time.monotonic()
    limit = max(1, min(int(limit), 20))
    data = await fetch_json(API, params={"action": "wbsearchentities", "search": name,
                                  "language": "en", "uselang": "en", "type": "item",
                                  "limit": str(limit), "format": "json"}, ttl_hours=24)
    if not isinstance(data, dict) or not isinstance(data.get("search"), list):
        raise RuntimeError("Wikidata organization search unavailable or malformed")
    ids = list(dict.fromkeys(item["id"] for item in data["search"]
                             if isinstance(item.get("id"), str) and
                             item["id"].startswith("Q") and item["id"][1:].isdigit()))[:limit]
    metadata = {"query": name, "truncated": "search-continue" in data,
                "candidate_limit": limit}
    if not ids:
        return OrganizationRecords([], {**metadata, "returned_count": 0})
    entities = await _entities(ids)
    query_key = company_name_key(name)
    organizations = [(qid, entities[qid]) for qid in ids if qid in entities
                     and "Q5" not in _ids(entities[qid], "P31")
                     and (_claims(entities[qid], "P856") or
                          _claims(entities[qid], "P169") or
                          _claims(entities[qid], "P112"))
                     and query_key in {company_name_key(n) for n in
                                       [_label(entities[qid]),
                                        *(a.get("value") for a in
                                          (entities[qid].get("aliases") or {}).get("en", []))] if n}]
    related = list(dict.fromkeys(qid for _, entity in organizations
                                for prop in ("P17", "P169", "P112")
                                for qid in _ids(entity, prop)))[:50]
    labels = {}
    if related:
        try:
            remaining = settings.investigation_timeout_seconds - (time.monotonic() - started) - 2
            if remaining <= 0:
                raise TimeoutError("Organization label enrichment budget exhausted")
            labels = await asyncio.wait_for(_entities(related, labels_only=True),
                                            timeout=min(8.0, remaining))
        except (RuntimeError, TimeoutError):
            metadata["labels_available"] = False
        else:
            metadata["labels_available"] = True
    records = []
    for qid, entity in organizations:
        label = _label(entity)
        if not label:
            continue
        urls = [v for c in _claims(entity, "P856")
                if isinstance(v := _value(c), str) and v.startswith(("https://", "http://"))]
        officers = []
        for prop, role in (("P169", "Chief executive officer"), ("P112", "Founder")):
            claims = _claims(entity, prop)
            active_ceos = {v.get("id") for c in claims
                           if prop == "P169" and not _qualifier_time(c, "P582")
                           and isinstance(v := _value(c), dict)}
            for claim in sorted(claims, key=lambda c: bool(_qualifier_time(c, "P582"))):
                value = _value(claim)
                person_id = value.get("id") if isinstance(value, dict) else None
                if not person_id or not _label(labels.get(person_id, {})):
                    continue
                end_date = _qualifier_time(claim, "P582")
                if prop == "P169" and end_date and person_id in active_ceos:
                    continue
                # Former CEOs remain source evidence, with their end date
                # clearly distinguished from an undated current claim.
                title = ("Former chief executive officer" if end_date else role) if prop == "P169" else role
                if any(o["id"] == person_id and o["role"] == title for o in officers):
                    continue
                officers.append({"id": person_id, "name": _label(labels[person_id]),
                                 "role": title, "end_date": end_date,
                                 "source_url": f"https://www.wikidata.org/wiki/{qid}#{prop}",
                                 "current_status": "end_date_recorded" if end_date else
                                 "current_status_unverified"})
        countries = _ids(entity, "P17")
        country_entity = labels.get(countries[0], {}) if len(countries) == 1 else {}
        code = next((v for c in _claims(country_entity, "P297")
                     if isinstance(v := _value(c), str)), None) or _label(country_entity)
        aliases = [a["value"] for a in (entity.get("aliases") or {}).get("en", [])
                   if a.get("value")]
        records.append(EntityRecord(
            source="Wikidata", source_id=qid, name=label, aliases=aliases,
            country=code, website=urls[0] if urls else None,
            officers=[o["name"] for o in officers],
            description=(entity.get("descriptions", {}).get("en") or {}).get("value"),
            url=f"https://www.wikidata.org/wiki/{qid}",
            raw={"entity_type": "organization", "public_profile": True,
                 "profile_identifier": qid, "officers": officers,
                 "country_basis": "Wikidata country", "source_url": f"https://www.wikidata.org/wiki/{qid}"},
        ))
    return OrganizationRecords(records, {**metadata, "returned_count": len(records)})
