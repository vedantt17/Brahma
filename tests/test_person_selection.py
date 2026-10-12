from app.resolution.engine import EntityRecord, ResolutionResult
from app.resolution.person_selection import person_name_key, select_person


def person(name="Sam Example", *, qid="Q1", country=None, **raw):
    record = EntityRecord(source="Wikidata", source_id=qid, name=name, country=country,
                          raw={"entity_type": "individual", "qid": qid, **raw})
    return ResolutionResult(record, .95, True, {}, {}, "test")


def test_person_names_preserve_business_suffix_words_and_surname_order():
    assert person_name_key("Alex Co") != person_name_key("Alex")
    assert person_name_key("García, José") == person_name_key("José Garcia")


def test_namesakes_never_choose_first():
    a, b = person(qid="Q1"), person(qid="Q2")
    result = select_person([a, b], query_name="Sam Example")
    assert result.status == "ambiguous" and result.best is None


def test_explicit_public_profile_choice_is_selected_without_verification_claim():
    a, b = person(qid="Q1"), person(qid="Q2")
    result = select_person([a, b], query_name="Sam Example", profile_id="q2")
    assert result.best is b and "unverified" in result.reason
    assert select_person([a], query_name="Other Name", profile_id="Q1").status == "conflict"


def test_country_and_birth_disambiguate_published_facts_only():
    a = person(qid="Q1", country="US", date_of_birth="1980-01-01")
    b = person(qid="Q2", country="GB", date_of_birth="1981-01-01")
    assert select_person([a, b], query_name="Sam Example", country="United States").best is a
    assert select_person([a, b], query_name="Sam Example", date_of_birth="1981-01-01").best is b
    unknown = person(qid="Q3")
    assert select_person([a, unknown], query_name="Sam Example", country="US").status == "ambiguous"


def test_employer_must_match_source_employer_facts():
    a = person(qid="Q1", employers=[{"label": "Example Labs", "id": "Q100"}])
    b = person(qid="Q2", employers=[{"label": "Other Organization"}])
    assert select_person([a, b], query_name="Sam Example", employer="Example Labs").best is a
    assert select_person([a, person(qid="Q3")], query_name="Sam Example", employer="Example Labs").status == "ambiguous"


def test_company_records_never_establish_a_person():
    record = EntityRecord(source="GLEIF", name="Sam Example", raw={"entity_type": "organization"})
    result = ResolutionResult(record, .99, True, {}, {}, "test")
    assert select_person([result], query_name="Sam Example").status == "unresolved"


def test_identifier_failure_never_falls_back_and_duplicate_qids_dedupe():
    a = person(qid="Q1")
    assert select_person([a], query_name="Sam Example", profile_id="Q2").best is None
    assert select_person([a, a], query_name="Sam Example").best is a


def test_year_precision_does_not_eliminate_unknown_or_falsely_confirm_exact_dob():
    a = person(qid="Q1", date_of_birth="1980")
    b = person(qid="Q2", date_of_birth="1980-05-05")
    assert select_person([a, b], query_name="Sam Example", date_of_birth="1980-05-05").status == "ambiguous"


def test_query_year_compares_only_year_against_full_published_birth():
    record = person(date_of_birth="1985-04-22")
    assert select_person([record], query_name="Sam Example", date_of_birth="1985").best is record
    assert select_person([record], query_name="Sam Example", date_of_birth="1984").status == "conflict"


def test_multiple_citizenships_accept_either_published_country():
    record = person(countries=[{"code": "US", "name": "United States"},
                               {"code": "GB", "name": "United Kingdom"}])
    assert select_person([record], query_name="Sam Example", country="UK").best is record
    assert select_person([record], query_name="Sam Example", country="US").best is record
    assert select_person([record], query_name="Sam Example", country="Germany").status == "conflict"


def test_former_employer_does_not_disambiguate_current_employer():
    former = person(qid="Q1", employers=[{"name": "Example Labs", "end_date": "2020-01-01",
                                         "current_status": "end_date_recorded"}])
    current = person(qid="Q2", employers=[{"name": "Example Labs", "current_status": "current_status_unverified"}])
    assert select_person([former, current], query_name="Sam Example", employer="Example Labs").status == "ambiguous"
