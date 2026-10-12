"""Public Wikidata human profiles; a name hit alone never establishes identity."""
from __future__ import annotations

import asyncio
import re
import time

from app.config import settings

from app.http_client import fetch_json
from app.resolution.engine import EntityRecord

API = "https://www.wikidata.org/w/api.php"
_QID = re.compile(r"Q[1-9][0-9]*", re.I)


class PeopleRecords(list):
    def __init__(self, records, metadata):
        super().__init__(records)
        self.search_metadata = metadata


def _claims(entity: dict, prop: str) -> list[dict]:
    return [claim for claim in (entity.get("claims") or {}).get(prop, [])
            if claim.get("rank") != "deprecated"]


def _value(claim: dict):
    snak = claim.get("mainsnak") or {}
    return (snak.get("datavalue") or {}).get("value") if snak.get("snaktype") == "value" else None


def _ids(entity: dict, prop: str) -> list[str]:
    return list(dict.fromkeys(value["id"] for claim in _claims(entity, prop)
                             if isinstance(value := _value(claim), dict)
                             and _QID.fullmatch(value.get("id", ""))))


def _label(entity: dict) -> str | None:
    labels = entity.get("labels") or {}
    return (labels.get("en") or next(iter(labels.values()), {})).get("value")


async def _entities(ids: list[str], *, labels_only: bool = False) -> dict:
    params = {"action": "wbgetentities", "ids": "|".join(ids), "format": "json",
              "languages": "en", "languagefallback": "1",
              "props": "labels|claims" if labels_only else "labels|aliases|descriptions|claims"}
    data = await fetch_json(API, params=params, ttl_hours=24)
    if not isinstance(data, dict) or not isinstance(data.get("entities"), dict):
        raise RuntimeError("Wikidata profile retrieval unavailable or malformed")
    return data["entities"]


def _qualifier_time(claim: dict, prop: str) -> str | None:
    for snak in (claim.get("qualifiers") or {}).get(prop, []):
        value = (snak.get("datavalue") or {}).get("value") or {}
        if isinstance(value, dict) and value.get("time"):
            return value["time"].lstrip("+").split("T")[0]
    return None


async def search(name: str, country: str | None = None, limit: int = 10,
                 *, profile_identifier: str | None = None) -> list[EntityRecord]:
    """Retrieve at most 20 human candidates; country is not inferred from residence."""
    started = time.monotonic()
    limit = max(1, min(int(limit), 20))
    identifier = (profile_identifier or "").strip().upper()
    if identifier and not _QID.fullmatch(identifier):
        raise ValueError("A Wikidata profile identifier must be a Q identifier")
    metadata = {"query": name, "profile_identifier": identifier or None,
                "truncated": False, "candidate_limit": limit}
    if identifier:
        ids = [identifier]
    else:
        data = await fetch_json(API, params={"action": "wbsearchentities", "search": name,
                                "language": "en", "uselang": "en", "type": "item",
                                "limit": str(limit), "format": "json"}, ttl_hours=24)
        if not isinstance(data, dict) or not isinstance(data.get("search"), list):
            raise RuntimeError("Wikidata person search unavailable or malformed")
        ids = list(dict.fromkeys(item["id"] for item in data["search"]
                                if _QID.fullmatch(item.get("id", ""))))[:limit]
        metadata["truncated"] = "search-continue" in data
    if not ids:
        return PeopleRecords([], {**metadata, "returned_count": 0})
    entities = await _entities(ids)
    humans = [(qid, entities[qid]) for qid in ids if qid in entities
              and "Q5" in _ids(entities[qid], "P31")]
    related = list(dict.fromkeys(qid for _, entity in humans
                                for prop in ("P108", "P106", "P27") for qid in _ids(entity, prop)))
    # A label batch is bounded independently of search results. Unlabelled
    # claim IDs remain visible; no names are invented when enrichment fails.
    related = related[:50]
    label_entities = {}
    if related:
        try:
            # Labels enrich already-retrieved human identities. A slow label
            # endpoint must not discard those profiles at the pipeline deadline.
            remaining = settings.investigation_timeout_seconds - (time.monotonic() - started) - 2
            if remaining <= 0:
                raise TimeoutError("Profile label enrichment budget exhausted")
            label_entities = await asyncio.wait_for(
                _entities(related, labels_only=True), timeout=min(8.0, remaining))
        except (RuntimeError, TimeoutError):
            metadata["labels_available"] = False
        else:
            metadata["labels_available"] = True
    records = []
    for qid, entity in humans:
        label = _label(entity)
        if not label:
            continue
        source_url = f"https://www.wikidata.org/wiki/{qid}"
        employers = []
        for claim in _claims(entity, "P108"):
            value = _value(claim)
            employer_id = value.get("id") if isinstance(value, dict) else None
            if not employer_id or not _QID.fullmatch(employer_id):
                continue
            employers.append({"id": employer_id, "name": _label(label_entities.get(employer_id, {})),
                              "source_url": source_url + "#P108", "property": "P108",
                              "current_status": "end_date_recorded" if _qualifier_time(claim, "P582")
                              else "current_status_unverified",
                              "start_date": _qualifier_time(claim, "P580"),
                              "end_date": _qualifier_time(claim, "P582")})
        occupations = [{"id": oid, "name": _label(label_entities.get(oid, {}))}
                       for oid in _ids(entity, "P106")]
        countries = [{"id": cid, "name": _label(label_entities.get(cid, {})),
                      "code": next((v for c in _claims(label_entities.get(cid, {}), "P297")
                                    if isinstance(v := _value(c), str)), None)}
                     for cid in _ids(entity, "P27")]
        dob = next((v["time"].lstrip("+").split("T")[0]
                    for c in _claims(entity, "P569")
                    if isinstance(v := _value(c), dict) and v.get("time")
                    and v.get("precision", 0) >= 11), None)
        aliases = [entry["value"] for entry in (entity.get("aliases") or {}).get("en", [])
                   if entry.get("value")]
        records.append(EntityRecord(source="Wikidata", source_id=qid, name=label,
            aliases=aliases, description=(entity.get("descriptions", {}).get("en") or {}).get("value"),
            # Citizenship is separate from residence; preserve that basis.
            country=countries[0]["code"] if len(countries) == 1 else None,
            url=source_url, raw={"entity_type": "individual", "profile_identifier": qid,
                "employers": employers, "occupations": occupations, "date_of_birth": dob,
                "countries": countries, "country_basis": "citizenship", "source_url": source_url}))
    return PeopleRecords(records, {**metadata, "returned_count": len(records)})
