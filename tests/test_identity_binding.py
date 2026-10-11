"""A requested identifier must never produce a hybrid lookalike identity."""
import asyncio

from app.pipeline import _build_supplier, _same_identity_records, _select_identity
from app.resolution.engine import EntityRecord, ResolutionResult, resolve

LEI = "984500B6DEB8CEBC4Z70"


def result(name, source, confidence, **raw):
    return ResolutionResult(EntityRecord(source=source, name=name, raw=raw),
                            confidence, confidence >= .72, {}, {}, "test")


def test_supplied_lei_anchors_selection_even_if_lookalike_scores_higher():
    etf = result("Anthropic AI Lab Ecosystem ETF", "SEC", .95, cik="999")
    company = result("ANTHROPIC, PBC", "GLEIF", .78, lei=LEI)
    assert _select_identity([etf, company], LEI.lower()) is company
    assert _select_identity([etf], LEI) is None


def test_supplier_identifiers_never_merge_from_lookalike():
    company = result("ANTHROPIC, PBC", "GLEIF", .93, lei=LEI, registered_as="company-id")
    etf = result("Anthropic AI Lab Ecosystem ETF", "SEC", .85, cik="999")
    supplier = _build_supplier("Anthropic", "US", None, company,
                               [company, etf], .93, "verified")
    assert supplier["lei"] == LEI
    assert supplier["cik"] is None
    assert _same_identity_records(company, [company, etf]) == [company]


def test_conflicting_name_does_not_become_verified_from_identifier_binding():
    records = asyncio.run(resolve(query_name="Completely Different Business",
                                  candidates=[EntityRecord(source="GLEIF", name="ANTHROPIC, PBC", raw={"lei": LEI})]))
    selected = _select_identity(records, LEI)
    assert selected is records[0]
    assert not selected.matched


def test_same_brand_does_not_merge_distinct_business_words_or_identifiers():
    company = result("Acme, PBC", "GLEIF", .93, lei=LEI)
    holding = result("Acme Holdings", "SEC", .9, cik="999")
    other_lei = result("Acme, PBC", "GLEIF", .95, lei="OTHER")
    assert _same_identity_records(company, [company, holding, other_lei]) == [company]
