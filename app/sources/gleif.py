"""GLEIF - global legal entity identity and ownership.

Gives the authoritative legal name, jurisdiction, registered address and the
LEI-to-LEI parent relationships that expose ownership structure.
"""

from __future__ import annotations

import logging
import re
import asyncio

from app.http_client import fetch_json
from app.resolution.engine import EntityRecord

log = logging.getLogger(__name__)

BASE = "https://api.gleif.org/api/v1"
SEARCH_URL = f"{BASE}/lei-records"


class CandidateRecords(list):
    """Registry candidates with explicit bounded retrieval provenance."""

    def __init__(self, records, metadata):
        super().__init__(records)
        self.search_metadata = metadata


async def enrich(record: EntityRecord) -> EntityRecord:
    """Fetch ownership only after the caller has selected this identity."""
    if record.source != "GLEIF" or not record.source_id:
        return record
    relations = await asyncio.gather(*(
        _relation(record.source_id, kind)
        for kind in ("direct-parent", "ultimate-parent")
    ))
    record.raw["parents"] = [relation for relation in relations if relation]
    return record


def _address_text(block: dict | None) -> tuple[str | None, str | None, str | None]:
    if not block:
        return None, None, None
    lines = [line for line in (block.get("addressLines") or []) if line]
    city = block.get("city")
    country = block.get("country")
    parts = lines + [p for p in (city, block.get("postalCode")) if p]
    return (", ".join(parts) or None), city, country


async def _relation(lei: str, kind: str) -> dict | None:
    """kind is 'direct-parent' or 'ultimate-parent'. 404 simply means none."""
    data = await fetch_json(
        f"{SEARCH_URL}/{lei}/{kind}", ttl_hours=168, retries=2, expect_missing=True
    )
    if not isinstance(data, dict):
        return None
    node = data.get("data")
    if not isinstance(node, dict):
        return None
    entity = (node.get("attributes") or {}).get("entity") or {}
    name = (entity.get("legalName") or {}).get("name")
    if not name:
        return None
    return {
        "name": name,
        "lei": node.get("id"),
        "jurisdiction": entity.get("jurisdiction"),
        "relationship": kind.replace("-", "_"),
    }


async def search(
    name: str, country: str | None = None, limit: int = 100,
    *, registration_number: str | None = None,
) -> list[EntityRecord]:
    identifier = (registration_number or "").strip().upper()
    if re.fullmatch(r"[A-Z0-9]{18}[0-9]{2}", identifier):
        # An LEI identifies a registry record directly; do not discard it and
        # rely on a fuzzy full-text name query instead.
        data = await fetch_json(f"{SEARCH_URL}/{identifier}", ttl_hours=24)
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            data = {**data, "data": [data["data"]]}
        nodes = data.get("data") if isinstance(data, dict) else None
        metadata = {"exact_identifier": True, "truncated": False}
    else:
        # Full-text relevance can rank funds mentioning a company ahead of
        # the company itself. Search the legal-name field instead.
        budget = max(1, min(int(limit), 100))
        nodes = []
        metadata = {"exact_identifier": False, "truncated": False,
                    "legal_candidate_limit": budget, "alias_candidate_limit": 50,
                    "search_name": name}
        # The default eight-result window often contained only investment
        # products mentioning a brand. Collect legal-name candidates first,
        # then a bounded full-text pass for registered trading/other names.
        legal_total = None
        for page in range(1, 3):
            params = {"filter[entity.legalName]": name,
                      "page[size]": str(min(50, budget)), "page[number]": str(page)}
            data = await fetch_json(SEARCH_URL, params=params, ttl_hours=24)
            if not isinstance(data, dict) or not isinstance(data.get("data"), list):
                if not nodes:
                    raise RuntimeError("GLEIF search unavailable or malformed")
                metadata["truncated"] = True
                break
            nodes.extend(data["data"])
            pagination = (data.get("meta") or {}).get("pagination") or {}
            legal_total = pagination.get("total", legal_total)
            has_next = bool((data.get("links") or {}).get("next")) or (
                isinstance(pagination.get("lastPage"), int) and page < pagination["lastPage"])
            if len(nodes) >= budget or not has_next:
                metadata["truncated"] = has_next
                break
        metadata["legal_name_result_count"] = legal_total
        # GLEIF rejects filter[entity.otherNames.name]. Its documented
        # fulltext endpoint can retrieve aliases; local resolution must still
        # compare the legal/other names instead of trusting fulltext rank.
        alias_data = await fetch_json(SEARCH_URL, params={"filter[fulltext]": name,
                                      "page[size]": "50"}, ttl_hours=24)
        if isinstance(alias_data, dict) and isinstance(alias_data.get("data"), list):
            nodes.extend(alias_data["data"])
            metadata["alias_search_available"] = True
            alias_pagination = (alias_data.get("meta") or {}).get("pagination") or {}
            metadata["alias_result_count"] = alias_pagination.get("total")
            metadata["truncated"] |= bool((alias_data.get("links") or {}).get("next")) or (
                isinstance(alias_pagination.get("lastPage"), int)
                and alias_pagination["lastPage"] > 1)
        else:
            metadata["alias_search_available"] = False
    if not isinstance(nodes, list):
        raise RuntimeError("GLEIF search unavailable or malformed")

    records: list[EntityRecord] = []
    seen = set()
    for node in nodes:
        attrs = node.get("attributes") or {}
        entity = attrs.get("entity") or {}
        legal_name = (entity.get("legalName") or {}).get("name")
        if not legal_name:
            continue

        lei = attrs.get("lei") or node.get("id")
        if lei in seen:
            continue
        seen.add(lei)
        address, city, addr_country = _address_text(entity.get("legalAddress"))
        hq_address, hq_city, hq_country = _address_text(
            entity.get("headquartersAddress")
        )
        aliases = [
            other.get("name")
            for other in (entity.get("otherNames") or [])
            if other.get("name")
        ]

        records.append(
            EntityRecord(
                source="GLEIF",
                source_id=lei,
                name=legal_name,
                aliases=aliases,
                country=addr_country or hq_country,
                city=city or hq_city,
                address=address or hq_address,
                officers=[],
                description=(entity.get("legalForm") or {}).get("id"),
                url=f"https://search.gleif.org/#/record/{lei}" if lei else None,
                raw={
                    "lei": lei,
                    "status": entity.get("status"),
                    "registration_status": (attrs.get("registration") or {}).get(
                        "status"
                    ),
                    "jurisdiction": entity.get("jurisdiction"),
                    "legal_form": (entity.get("legalForm") or {}).get("id"),
                    "category": entity.get("category"),
                    "registered_as": entity.get("registeredAs"),
                    "legal_address": address,
                    "headquarters_address": hq_address,
                    "parents": [],
                },
            )
        )

    metadata["returned_count"] = len(records)
    return CandidateRecords(records, metadata)
