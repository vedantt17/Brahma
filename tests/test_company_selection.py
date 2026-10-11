from app.resolution.engine import EntityRecord, ResolutionResult
import pytest
from app.resolution.selection import company_name_key, select_company


def candidate(name, *, source="GLEIF", identifier=None, confidence=.95, aliases=None,
              country=None, website=None, **raw):
    record = EntityRecord(source=source, name=name, source_id=identifier,
                          aliases=aliases or [], country=country, website=website, raw=raw)
    return ResolutionResult(record, confidence, confidence >= .72, {}, {}, "test")


def test_business_words_are_distinct_from_legal_forms():
    assert company_name_key("Acme, PBC") == "acme"
    assert company_name_key("Acme International Holdings LLC") == "acme international holdings"


@pytest.mark.parametrize("name", ["Microsoft", "Apple", "NVIDIA", "Meta", "Amazon", "Tesla", "ABC Engineering", "Northwind"])
def test_general_brand_names_never_choose_an_exact_namesake_over_another_entity(name):
    namesake = candidate(name + " LLC", identifier="namesake", country="US")
    operating = candidate(name + " Technologies Ltd", identifier="operating", country="US", confidence=.5)
    selection = select_company([namesake, operating], query_name=name.lower())
    assert selection.status == "ambiguous"
    assert selection.best is None


def test_brand_only_multiple_legal_entities_remain_ambiguous():
    a = candidate("OpenAI Global LLC", identifier="a", aliases=["OpenAI"])
    b = candidate("OpenAI Foundation Inc", identifier="b", aliases=["OpenAI"])
    selection = select_company([a, b], query_name="OpenAI")
    assert selection.best is None and selection.status == "ambiguous"


def test_partial_high_score_fund_is_never_selected():
    fund = candidate("Anthropic AI Lab Ecosystem ETF", confidence=.99)
    assert select_company([fund], query_name="Anthropic").best is None


def test_website_disambiguates_authoritative_alias_records():
    a = candidate("Acme Global LLC", identifier="a", aliases=["Acme"], website="acme.com")
    b = candidate("Acme Group LLC", identifier="b", aliases=["Acme"], website="other.com")
    assert select_company([b, a], query_name="Acme", website="https://www.acme.com").best is a


def test_country_disambiguates_without_treating_unknown_as_match():
    a = candidate("Acme LLC", identifier="a", country="US")
    b = candidate("Acme Ltd", identifier="b", country="GB")
    unknown = candidate("Acme Ltd", identifier="c")
    assert select_company([b, a], query_name="Acme", country="United States").best is a
    selection = select_company([unknown, b, a], query_name="Acme", country="United States")
    assert selection.best is None and selection.status == "ambiguous"


def test_explicit_identifier_never_falls_back_to_name():
    lei = "984500B6DEB8CEBC4Z70"
    a = candidate("Anthropic, PBC", identifier=lei, lei=lei)
    b = candidate("Anthropic AI Lab Ecosystem ETF", confidence=.99)
    assert select_company([b, a], query_name="Anthropic", registration_number=lei).best is a
    assert select_company([b], query_name="Anthropic", registration_number=lei).best is None
    assert select_company([a], query_name="Unrelated", registration_number=lei).status == "conflict"


def test_matching_source_records_merge_but_conflicting_identifiers_do_not():
    a = candidate("Acme LLC", identifier="a", lei="a", country="US")
    b = candidate("Acme Inc", source="SEC", identifier="10", cik="10", country="US")
    assert select_company([a, b], query_name="Acme").status == "selected"
    c = candidate("Acme LLC", identifier="c", lei="c", country="US")
    assert select_company([a, c], query_name="Acme").status == "ambiguous"


def test_local_registration_and_cik_are_explicit_discriminators():
    a = candidate("Acme LLC", source="SEC", identifier="0000012", cik="0000012")
    assert select_company([a], query_name="Acme", registration_number="CIK:12").best is a
    b = candidate("Acme LLC", registered_as="REG-123")
    assert select_company([b], query_name="Acme", registration_number="REG-123").best is b


def test_exact_namesake_cannot_beat_other_credible_brand_entities():
    namesake = candidate("OpenAI S.R.L.", identifier="a")
    global_company = candidate("OpenAI Global LLC", identifier="b", confidence=.5)
    selection = select_company([namesake, global_company], query_name="OpenAI")
    assert selection.status == "ambiguous"
    assert selection.best is None
    assert global_company in selection.candidates


def test_single_prefix_record_is_a_candidate_not_an_established_brand():
    record = candidate("Acme Global LLC", identifier="a", confidence=.5)
    assert select_company([record], query_name="Acme").status == "ambiguous"


def test_manual_candidate_choice_supplies_legal_name_and_lei():
    lei = "984500B6DEB8CEBC4Z70"
    candidate_record = candidate("Acme Global LLC", identifier=lei, country="US", lei=lei)
    assert select_company([candidate_record], query_name="Acme").status == "ambiguous"
    selection = select_company([candidate_record], query_name="Acme Global LLC", country="US", registration_number=lei)
    assert selection.best is candidate_record and selection.status == "selected"


def test_supplied_country_must_not_select_a_namesake_over_unknown_country_brand():
    namesake = candidate("OpenAI Ltd", identifier="a", country="US")
    brand = candidate("OpenAI Global LLC", identifier="b", confidence=.4)
    assert select_company([namesake, brand], query_name="OpenAI", country="US").status == "ambiguous"
