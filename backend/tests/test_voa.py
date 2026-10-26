import sqlite3

import pytest

from app.jobs import mark_duplicates
from app.models import SearchRequest
from app.voa.importer import parse_record
from app.voa.repository import DatasetMissingError, VoaRepository
from tests.conftest import SAMPLE_LINES


def test_parse_record_maps_spec_fields():
    row = parse_record(SAMPLE_LINES[0].split("*"))
    assert row[0] == "300675222"           # UARN
    assert row[15:19] == ("CV1 1FJ", "CV1", "CV1 1", 22000)


def test_parse_record_skips_deleted_and_malformed():
    assert parse_record(SAMPLE_LINES[9].split("*")) is None   # null RV
    assert parse_record(["too", "short"]) is None


def test_import_counts_and_meta(settings):
    con = sqlite3.connect(settings.voa_db_path)
    assert con.execute("SELECT COUNT(*) FROM properties").fetchone()[0] == 9
    meta = dict(con.execute("SELECT key, value FROM meta"))
    assert meta["row_count"] == "9" and "historic" not in meta["source_file"]
    assert not settings.voa_db_path.with_suffix(".importing").exists()


def test_missing_dataset_raises(tmp_path):
    with pytest.raises(DatasetMissingError):
        VoaRepository(tmp_path / "nope.sqlite").meta()


@pytest.fixture
def repo(settings):
    return VoaRepository(settings.voa_db_path)


def uarns(repo, **kw):
    records, _ = repo.search(SearchRequest(**kw), limit=100)
    return [r.uarn for r in records]


def test_search_full_postcode_returns_all_listed(repo):
    # No filters except the postcode: everything listed there, like the site (deleted entry excluded at import)
    assert len(uarns(repo, postcode="CV1 1FJ")) == 5


def test_search_rv_from_to(repo):
    assert set(uarns(repo, postcode="CV1 1FJ", rv_from=12000)) == {"300675222", "235950222", "3529303000", "11602154000"}
    assert set(uarns(repo, postcode="CV1 1FJ", rv_from=0, rv_to=16000)) == {"113420222", "3529303000"}


def test_search_by_sector_outward_and_town(repo):
    assert len(uarns(repo, postcode="CV1 1")) == 5
    assert len(uarns(repo, postcode="CV1")) == 7
    assert uarns(repo, town="grays") == ["999000003"]
    assert uarns(repo, town="Horton") == ["999000004"]  # matches postal district as well as town
    assert uarns(repo, town="Coventry", postcode="RM17 5RZ") == []


def test_search_description_code(repo):
    assert set(uarns(repo, postcode="CV1", description_code="CS")) == {"300675222", "235950222", "999000002"}
    assert uarns(repo, postcode="CV1", description_code="CS3") == ["113420222"]   # CS3 is not swallowed by CS
    assert uarns(repo, postcode="CV1", description_code="CR1") == ["11602154000"]  # stored as CR1O
    assert uarns(repo, town="Wimborne", description_code="cl") == ["999000004"]


def test_primary_code_mapping():
    from app.voa.description_codes import description_codes, primary_code

    assert len(description_codes()) == 117
    assert primary_code("CS") == "CS" and primary_code("CS3") == "CS3"
    assert primary_code("CWO") == "CW" and primary_code("IF3W") == "IF3"
    assert primary_code("ZZ9") is None


def test_search_truncation(repo):
    records, truncated = repo.search(SearchRequest(postcode="CV1"), limit=2)
    assert len(records) == 2 and truncated


def test_record_display_fields(repo):
    rec = repo.search(SearchRequest(town="Grays"), limit=5)[0][0]
    assert rec.address == "69, Lodge Lane, Grays, RM17 5RZ"
    assert rec.firm_name == "Grays Express Ltd"
    assert rec.source_url.endswith("/valuations/start/999000003")


def test_mark_duplicates_links_same_address_but_keeps_both(repo):
    records, _ = repo.search(SearchRequest(postcode="CV1 3AX", min_rv=0), limit=10)
    assert len(records) == 2
    assert mark_duplicates(records) == 1
    assert records[1].possible_duplicate_of == records[0].uarn


def test_latest_baseline_url_picks_newest_epoch():
    from app.voa.importer import latest_baseline_url

    html = (
        '<a href="https://x/uk-englandwales-ndr-2026-listentries-compiled-epoch-0004-baseline-csv.zip">'
        '<a href="https://x/uk-englandwales-ndr-2026-listentries-compiled-epoch-0005-baseline-csv.zip">'
        '<a href="https://x/uk-englandwales-ndr-2026-listentries-compiled-epoch-0005-changeupdate-0001-csv.zip">'
        '<a href="https://x/uk-englandwales-ndr-2023-listentries-compiled-epoch-0030-baseline-csv.zip">'
    )
    assert latest_baseline_url(2026, html).endswith("epoch-0005-baseline-csv.zip")
    with pytest.raises(RuntimeError):
        latest_baseline_url(2031, html)


def test_town_suggestions(repo):
    assert [t["value"] for t in repo.suggest_towns("cov")] == ["Coventry"]
    assert repo.suggest_towns("")[0] == {"value": "Coventry", "count": 7}       # biggest first
    assert {t["value"] for t in repo.suggest_towns("hor")} == {"Horton"}          # localities too


def test_postcode_suggestions_narrow_from_district_to_postcode(repo):
    assert [p["value"] for p in repo.suggest_postcodes("Coventry", "")] == ["CV1"]
    assert [p["value"] for p in repo.suggest_postcodes("Coventry", "CV1")] == ["CV1 1", "CV1 3"]
    assert [p["value"] for p in repo.suggest_postcodes("Coventry", "CV1 1")] == ["CV1 1FJ"]
    assert repo.suggest_postcodes("Grays", "CV1") == []                           # only that town's postcodes
    assert [p["value"] for p in repo.suggest_postcodes("", "RM")] == ["RM17"]
