"""Select public human profiles without implying identity verification.

A selected profile establishes which published record was requested. It does
not verify a person's identity or constitute sanctions clearance.
"""
from __future__ import annotations

import re
import unicodedata

from app.resolution.engine import ResolutionResult
from app.resolution.normalize import normalize_country
from app.resolution.selection import CompanySelection


def person_name_key(name: str | None) -> str:
    value = unicodedata.normalize("NFKD", name or "").casefold()
    value = "".join(c for c in value if not unicodedata.combining(c))
    return " ".join(sorted(re.findall(r"\w+", value)))


def _profile_id(result: ResolutionResult) -> str:
    return str(result.record.raw.get("profile_id") or result.record.raw.get("profile_identifier") or result.record.raw.get("qid")
               or result.record.source_id or "").strip().upper()


def _birth(result: ResolutionResult) -> str:
    # Only compare published calendar values. A year-only fact cannot verify
    # the caller's exact birth date.
    value = str(result.record.raw.get("date_of_birth") or result.record.raw.get("birth_date") or "")
    match = re.match(r"^\+?(\d{4}-\d{2}-\d{2})", value)
    return match.group(1) if match else value.strip()


def _employers(result: ResolutionResult) -> set[str]:
    values = result.record.raw.get("employers") or []
    if isinstance(values, (str, dict)):
        values = [values]
    keys = set()
    for value in values:
        if isinstance(value, dict):
            if value.get("end_date") or value.get("current_status") in {
                    "end_date_recorded", "former", "ended"}:
                continue
            for field in ("name", "label", "id", "qid"):
                if value.get(field):
                    keys.add(person_name_key(str(value[field])))
        elif isinstance(value, str):
            keys.add(person_name_key(value))
    return keys


def _countries(result: ResolutionResult) -> set[str]:
    values = result.record.raw.get("countries") or result.record.raw.get("citizenships") or []
    if isinstance(values, (str, dict)):
        values = [values]
    countries = set()
    for value in values:
        if isinstance(value, dict):
            for field in ("code", "name", "label"):
                if value.get(field):
                    countries.add(normalize_country(str(value[field])))
        elif isinstance(value, str):
            countries.add(normalize_country(value))
    if result.record.country:
        countries.add(normalize_country(result.record.country))
    return countries - {""}


def select_person(
    resolutions: list[ResolutionResult], *, query_name: str,
    aliases: list[str] | None = None, country: str | None = None,
    date_of_birth: str | None = None, employer: str | None = None,
    profile_id: str | None = None,
) -> CompanySelection:
    names = {person_name_key(n) for n in [query_name, *(aliases or [])]} - {""}
    qc = normalize_country(country)
    dob = (date_of_birth or "").strip()
    qe = person_name_key(employer)
    requested_id = (profile_id or "").strip().upper()
    eligible = []
    conflicts = []
    seen: set[tuple[str, str]] = set()
    for result in resolutions:
        record = result.record
        if record.raw.get("entity_type") != "individual":
            continue
        identifier = _profile_id(result)
        if requested_id and requested_id != identifier:
            continue
        record_names = {person_name_key(n) for n in [record.name, *record.aliases]} - {""}
        if not names & record_names:
            if requested_id:
                conflicts.append(result)
            continue
        countries = _countries(result)
        birth = _birth(result)
        employers = _employers(result)
        contradictory = bool(qc and countries and qc not in countries)
        if dob and birth:
            # Published year precision can contradict a year, never establish
            # an exact birth date absent month/day precision.
            contradictory |= dob[:4] != birth[:4] or (
                len(birth) >= 10 and len(dob) >= 10 and dob[:10] != birth[:10])
        if qe and employers and qe not in employers:
            contradictory = True
        if contradictory:
            conflicts.append(result)
            continue
        key = (record.source.casefold(), identifier)
        if identifier and key in seen:
            continue
        if identifier:
            seen.add(key)
        eligible.append(result)

    if not eligible:
        return CompanySelection(None, "conflict" if conflicts else "unresolved",
            "Published profile details conflict with the supplied person details."
            if conflicts else "No matching public human profile was found.", conflicts)
    # Unknown published fields remain plausible namesakes. Caller-supplied
    # details cannot manufacture corroboration or eliminate missing facts.
    if len(eligible) != 1:
        return CompanySelection(None, "ambiguous",
            "Several public profiles share this name; choose a profile or supply distinguishing public details.", eligible)
    return CompanySelection(eligible[0], "selected",
        "A public human profile was selected; identity and screening remain unverified.", eligible)
