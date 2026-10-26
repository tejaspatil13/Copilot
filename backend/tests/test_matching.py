import pytest

from app.contacts.base import ContactCandidate
from app.matching import choose, normalize_phone
from app.models import ContactStatus, PropertyRecord

REC = PropertyRecord(
    uarn="300675222", address="13, Trinity Street, Coventry, CV1 1FJ", street="Trinity Street",
    number_or_name="13", town="Coventry", postcode="CV1 1FJ", description="Shop and Premises", rv=22000,
)


def cand(name="Games Workshop", address="13 Trinity St, Coventry", postcode="CV1 1FJ", phone="+44 24 7622 7311", **kw):
    return ContactCandidate(name=name, address=address, postcode=postcode, phone=phone, source="test", **kw)


@pytest.mark.parametrize("raw,expected", [
    ("+44 24 7622 7311", "+44 24 7622 7311"), ("024 7622 7311", "+44 24 7622 7311"),
    ("02476227311", "+44 24 7622 7311"), ("07877 545372", "+44 7877 545372"),
    ("12345", None), ("", None), ("+1 212 555 0100", None),
])
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def test_verified_needs_postcode_number_and_street():
    m = choose(REC, [cand()])
    assert m.status == ContactStatus.VERIFIED and m.phone == "+44 24 7622 7311" and m.score >= 90
    assert "building number matches" in m.reasons


def test_wrong_building_number_is_not_verified():
    status, *_ = choose(REC, [cand(address="31 Trinity St, Coventry")])
    assert status in (ContactStatus.REVIEW, ContactStatus.NO_CONTACT)


def test_name_alone_never_verifies():
    rec = REC.model_copy(update={"firm_name": "Games Workshop"})
    status, *_ = choose(rec, [cand(address="1 Other Road, Leeds", postcode="LS1 1AA")])
    assert status == ContactStatus.NO_CONTACT


def test_named_building_without_number_caps_at_probable():
    rec = REC.model_copy(update={"number_or_name": "The Old Mill", "address": "The Old Mill, Trinity Street"})
    status, *_ = choose(rec, [cand(name="The Old Mill Tearooms", address="Trinity St, Coventry")])
    assert status == ContactStatus.PROBABLE
    # Same street and postcode but nothing tying it to the building -> a human has to check
    status, *_ = choose(rec, [cand(address="Trinity St, Coventry")])
    assert status == ContactStatus.REVIEW


def test_two_businesses_at_same_address_give_a_number_to_confirm_plus_alternatives():
    m = choose(REC, [cand(), cand(name="Phone Repairs 4U", phone="024 7600 0000")])
    assert m.status == ContactStatus.REVIEW and m.phone in ("+44 24 7622 7311", "+44 24 7600 0000")
    assert len(m.others) == 1 and m.phone not in m.others[0]
    assert any("confirm who answers" in w for w in m.reasons)


def test_other_numbers_only_include_the_same_building():
    m = choose(REC, [cand(), cand(name="Next Door Cafe", address="15 Trinity St, Coventry", phone="024 7600 2222"),
                     cand(name="Upstairs Agency", phone="024 7600 3333")])
    assert m.others == ["Upstairs Agency: +44 24 7600 3333"]


def test_listing_with_phone_preferred_over_equal_listing_without():
    m = choose(REC, [cand(name="No Phone Ltd", phone=""), cand()])
    assert m.phone == "+44 24 7622 7311" and m.candidate.name == "Games Workshop"


def test_phone_taken_from_lower_scoring_listing_when_best_has_none():
    # e.g. "Games Workshop" (no phone) and its brand "Warhammer" (with phone) at the same address
    best = cand(phone="", categories=["arts_crafts_and_hobby_store"])
    brand = cand(name="Warhammer", categories=["media_service"])
    m = choose(REC, [best, brand])
    assert m.status == ContactStatus.REVIEW and m.phone == "+44 24 7622 7311"


def test_uk_number_missing_plus_sign_is_accepted():
    assert normalize_phone("442073752600") == "+44 20 7375 2600"


def test_same_business_listed_twice_is_not_ambiguous():
    status, *_ = choose(REC, [cand(), cand(source_id="dup")])
    assert status == ContactStatus.VERIFIED


def test_closed_business_is_rejected():
    status, *_ = choose(REC, [cand(closed=True)])
    assert status != ContactStatus.VERIFIED


def test_match_without_phone_is_no_contact_but_keeps_name():
    status, best, phone, *_ = choose(REC, [cand(phone="")])
    assert status == ContactStatus.NO_CONTACT and best.name == "Games Workshop" and phone == ""


def test_invalid_phone_is_not_used():
    m = choose(REC, [cand(phone="123")])
    assert m.phone == "" and m.status == ContactStatus.NO_CONTACT


def test_proximity_match_without_postcode_caps_at_probable():
    status, *_ = choose(REC, [cand(postcode="", distance_m=30)])
    assert status == ContactStatus.PROBABLE


def test_low_source_confidence_downgrades_verified():
    status, *_ = choose(REC, [cand(source_confidence=0.3)])
    assert status == ContactStatus.PROBABLE


def test_no_candidates():
    assert choose(REC, [])[0] == ContactStatus.NO_CONTACT


def test_office_business_at_shop_premises_loses_the_tie():
    # 13 Trinity Street: the shop downstairs and an agency upstairs share the building number
    shop = cand(categories=["arts_crafts_and_hobby_store"])
    office = cand(name="Blue Arrow Catering", phone="024 7600 0000", categories=["professional_service"])
    status, best, phone, *_ = choose(REC, [office, shop])
    assert status == ContactStatus.VERIFIED and best.name == "Games Workshop" and phone == "+44 24 7622 7311"


def test_two_shops_at_same_number_still_need_review():
    a = cand(categories=["restaurant"])
    b = cand(name="Albemarle & Bond", phone="024 7600 0000", categories=["second_hand_store"])
    assert choose(REC, [a, b])[0] == ContactStatus.REVIEW


def test_advertising_rights_and_bus_shelters_never_get_a_phone():
    for number, desc in (("Advert Right on Bus Shelter O/s 13", "Shop and Premises"),
                         ("13", "Advertising Right and Premises"),
                         ("13", "Car Park and Premises")):
        rec = REC.model_copy(update={"number_or_name": number, "description": desc})
        m = choose(rec, [cand()])
        assert m.status == ContactStatus.NO_CONTACT and m.phone == "" and "not a trading business" in m.reasons[0]
