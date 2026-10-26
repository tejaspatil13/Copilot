import pytest
from pydantic import ValidationError

from app.models import SearchRequest
from app.normalize import (
    clean_ws, house_numbers, name_key, normalize_postcode, parse_postcode_query, smart_title, street_key,
)


@pytest.mark.parametrize("raw,expected", [
    ("cv1 1fj", "CV1 1FJ"), ("CV11FJ", "CV1 1FJ"), (" sw1a 2aa ", "SW1A 2AA"), ("M1 1AE", "M1 1AE"),
    ("CV1", None), ("not a postcode", None), ("", None), (None, None),
])
def test_normalize_postcode(raw, expected):
    assert normalize_postcode(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("cv1 1fj", ("full", "CV1 1FJ")), ("CV1 1", ("sector", "CV1 1")), ("cv1", ("outward", "CV1")),
    ("M1", ("outward", "M1")), ("SW1A", ("outward", "SW1A")), ("12345", None), ("CV1 1FJX", None),
])
def test_parse_postcode_query(raw, expected):
    assert parse_postcode_query(raw) == expected


def test_clean_ws_handles_newlines_and_nbsp():
    assert clean_ws("\nM Hussain (Chemists) Ltd\n") == "M Hussain (Chemists) Ltd"
    assert clean_ws("\xa020 8517 8570") == "20 8517 8570"


def test_smart_title():
    assert smart_title("9-11, TRINITY STREET, COVENTRY") == "9-11, Trinity Street, Coventry"
    assert smart_title("UNIT 2A, HICKS YARD AND MILL") == "Unit 2A, Hicks Yard and Mill"
    assert smart_title("STRATFORD-UPON-AVON") == "Stratford-Upon-Avon"
    assert smart_title("GND & 1ST FLRS AT 5, THE PRECINCT, COVENTRY") == "Gnd & 1st Flrs at 5, The Precinct, Coventry"


def test_house_numbers_ranges_and_letters():
    assert {"1", "2", "3"} <= house_numbers("1 -3, Lower Holyhead Road")
    assert {"12a", "12"} <= house_numbers("12A High St")
    assert house_numbers("The Horton Inn") == set()


def test_street_and_name_keys():
    assert street_key("23 Trinity St") == street_key("23 TRINITY STREET")
    assert name_key("Grays Express Ltd") == name_key("GRAYS EXPRESS")


def test_search_request_valid():
    r = SearchRequest(town="  Coventry ", postcode="cv1 1fj", description_code="cs", rv_from=12000)
    assert r.town == "Coventry" and r.description_code == "CS" and r.rv_from == 12000 and r.rv_to is None


@pytest.mark.parametrize("payload,fragment", [
    ({}, "Enter a town, a postcode"),
    ({"postcode": "ZZZ"}, "must be a full UK postcode"),
    ({"town": "Coventry; DROP TABLE"}, "may only contain"),
    ({"town": "Coventry", "rv_from": 20000, "rv_to": 1000}, "cannot be greater"),
    ({"town": "Coventry", "rv_from": -5}, "greater than or equal"),
    ({"town": "Coventry", "description_code": "XYZ"}, "not one of the VO description codes"),
])
def test_search_request_invalid(payload, fragment):
    with pytest.raises(ValidationError) as exc:
        SearchRequest(**payload)
    assert fragment in str(exc.value)
