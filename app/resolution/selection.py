"""Conservative company selection, separate from fuzzy candidate ranking.

A similarity score ranks candidates; it cannot establish which of several
companies sharing a trading name the caller meant.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
import unicodedata

from app.resolution.engine import ResolutionResult
from app.resolution.normalize import normalize_country, normalize_domain

_LEGAL_END = re.compile(
    r"(?:[\s,]+)(?:p\.?b\.?c\.?|i\.?n\.?c\.?|incorporated|"
    r"l\.?l\.?c\.?|l\.?l\.?p\.?|ltd\.?|limited|corp\.?|corporation|"
    r"plc\.?|gmbh|sarl|s\.?r\.?l\.?|s\.?a\.?|sas|b\.?v\.?|n\.?v\.?|pty\.?|pte\.?)(?:[\s,.]*)$", re.I
)


def company_name_key(name: str | None) -> str:
    value = unicodedata.normalize("NFKD", name or "").casefold()
    value = "".join(c for c in value if not unicodedata.combining(c))
    while True:
        trimmed = _LEGAL_END.sub("", value).strip(" ,.")
        if not trimmed or trimmed == value:
            break
        value = trimmed
    return re.sub(r"[^\w]+", " ", value).strip()


@dataclass
class CompanySelection:
    best: ResolutionResult | None
    status: str
    reason: str
    candidates: list[ResolutionResult] = field(default_factory=list)


def _identifiers(result: ResolutionResult) -> dict[str, str]:
    record = result.record
    ids = {k: str(record.raw[k]).strip().upper() for k in ("lei", "cik", "registered_as")
           if record.raw.get(k)}
    if record.source_id and record.source.upper() in {"GLEIF", "SEC"}:
        ids.setdefault("lei" if record.source.upper() == "GLEIF" else "cik",
                       str(record.source_id).strip().upper())
    if "cik" in ids:
        ids["cik"] = ids["cik"].removeprefix("CIK:").lstrip("0") or "0"
    return ids


def _identifier_matches(result: ResolutionResult, identifier: str) -> bool:
    ids = _identifiers(result)
    if re.fullmatch(r"[A-Z0-9]{18}[0-9]{2}", identifier):
        return ids.get("lei") == identifier
    if identifier.startswith("CIK:"):
        return ids.get("cik") == (identifier[4:].lstrip("0") or "0")
    return identifier in ids.values()


def _same_company(left: ResolutionResult, right: ResolutionResult) -> bool:
    li, ri = _identifiers(left), _identifiers(right)
    shared = li.keys() & ri.keys()
    # Local registration numbers do not share a namespace across countries.
    lc, rc = normalize_country(left.record.country), normalize_country(right.record.country)
    if lc and rc and lc != rc:
        return False
    if any(li[k] != ri[k] for k in shared):
        return False
    if any(li[k] == ri[k] for k in shared):
        return True
    # Distinct same-source records remain distinct even with the same name.
    if left.record.source == right.record.source:
        return left.record.source_id is not None and left.record.source_id == right.record.source_id
    return company_name_key(left.record.name) == company_name_key(right.record.name)


def select_company(
    resolutions: list[ResolutionResult], *, query_name: str,
    query_aliases: list[str] | None = None, country: str | None = None,
    website: str | None = None, registration_number: str | None = None,
) -> CompanySelection:
    query_keys = {company_name_key(n) for n in [query_name, *(query_aliases or [])]} - {""}
    identifier = (registration_number or "").strip().upper()
    qc, qw = normalize_country(country), normalize_domain(website)
    eligible: list[ResolutionResult] = []
    conflicts: list[ResolutionResult] = []
    for result in resolutions:
        record = result.record
        keys = {company_name_key(n) for n in [record.name, *record.aliases]} - {""}
        exact_name = bool(query_keys & keys)
        # Registries commonly omit trading aliases. A brand-prefix record is
        # a credible alternative, never proof that it is the intended company.
        prefix_name = any(k.startswith(q + " ") for q in query_keys for k in keys)
        investment = record.raw.get("category") == "FUND" or any(
            token in company_name_key(record.name).split() for token in ("etf", "fund"))
        prefix_name = prefix_name and not investment
        rc, rw = normalize_country(record.country), normalize_domain(record.website)
        identifier_hit = bool(identifier and _identifier_matches(result, identifier))
        website_hit = bool(qw and rw and qw == rw)
        if identifier and not identifier_hit:
            continue
        # Missing source fields provide no corroboration, never a match.
        if not identifier_hit and not exact_name and not prefix_name and not (website_hit and result.matched):
            continue
        contradictory = (qc and rc and qc != rc) or (qw and rw and qw != rw)
        if identifier_hit and not exact_name:
            contradictory = True
        if contradictory:
            conflicts.append(result)
            continue
        if identifier_hit or exact_name or prefix_name or website_hit:
            eligible.append(result)

    if not eligible:
        return CompanySelection(None, "conflict" if conflicts else "unresolved",
            "Supplied details contradict matching registry records; review the candidates."
            if conflicts else "No registry record establishes this company identity.", conflicts)

    # A supplied domain/country can distinguish records with affirmative matches.
    # Unknown fields cannot outweigh an authoritative positive match.
    if not identifier:
        if qw and any(normalize_domain(r.record.website) == qw for r in eligible):
            eligible = [r for r in eligible if normalize_domain(r.record.website) == qw]

    groups: list[list[ResolutionResult]] = []
    for result in eligible:
        group = next((g for g in groups if all(_same_company(result, other) for other in g)), None)
        if group is None:
            groups.append([result])
        else:
            group.append(result)
    if len(groups) != 1:
        return CompanySelection(None, "ambiguous",
            "Several distinct registry entities match; supply a website, country, or registration identifier.", eligible)
    best = max(groups[0], key=lambda r: r.confidence)
    if not identifier and not (query_keys & {company_name_key(n) for n in
                               [best.record.name, *best.record.aliases]}) and not (
            qw and normalize_domain(best.record.website) == qw):
        return CompanySelection(None, "ambiguous",
            "A related registry name was found, but its trading identity is not established; choose a candidate or supply its identifier.", eligible)
    return CompanySelection(best, "selected",
        "Selected by supplied registry identifier." if identifier else
        "One registry identity matches the supplied name and available details.", eligible)


def select_public_organization(
    resolutions: list[ResolutionResult], *, query_name: str,
    country: str | None = None, website: str | None = None,
) -> CompanySelection:
    """Select a public brand profile without treating it as a legal registry ID."""
    key = company_name_key(query_name)
    qc, qw = normalize_country(country), normalize_domain(website)
    eligible = []
    for result in resolutions:
        record = result.record
        if record.source != "Wikidata" or not record.raw.get("public_profile"):
            continue
        if key not in {company_name_key(n) for n in [record.name, *record.aliases]}:
            continue
        rc, rw = normalize_country(record.country), normalize_domain(record.website)
        if (qc and rc and qc != rc) or (qw and rw != qw):
            continue
        # A published website or officer claim distinguishes an organization
        # profile from product pages and similarly named search results.
        if rw or record.raw.get("officers"):
            eligible.append(result)
    if qw and any(normalize_domain(r.record.website) == qw for r in eligible):
        eligible = [r for r in eligible if normalize_domain(r.record.website) == qw]
    elif not qw and any(r.record.website for r in eligible):
        eligible = [r for r in eligible if r.record.website]
    if len(eligible) == 1:
        return CompanySelection(eligible[0], "selected",
            "A public organization profile matches this name"
            + (" and website" if qw else "")
            + "; its legal entity and current leadership are not independently verified.", eligible)
    return CompanySelection(None, "ambiguous" if eligible else "unresolved",
        "Several public organization profiles match; supply a website or legal identifier."
        if eligible else "No matching public organization profile was found.", eligible)
