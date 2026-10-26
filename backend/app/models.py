"""API request/response models."""
from datetime import datetime
from enum import StrEnum
from urllib.parse import quote_plus

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from app.normalize import clean_ws, parse_postcode_query
from app.voa.description_codes import description_codes


class SearchRequest(BaseModel):
    """Mirrors the VO Find-a-property advanced search fields."""

    town: str = Field("", max_length=60, description="Town, e.g. 'Coventry'")
    postcode: str = Field("", max_length=10, description="Full postcode, sector ('CV1 1') or outward code ('CV1')")
    description_code: str = Field("", max_length=4, description="VO description code, e.g. 'CS'; empty = Any")
    rv_from: int | None = Field(None, ge=0, le=100_000_000, description="Rateable value from (£)")
    rv_to: int | None = Field(None, ge=0, le=100_000_000, description="Rateable value to (£)")

    @field_validator("town")
    @classmethod
    def _clean_town(cls, v: str) -> str:
        v = clean_ws(v)
        if v and not all(ch.isalnum() or ch in " -'&.," for ch in v):
            raise ValueError("may only contain letters, numbers, spaces and - ' & . ,")
        return v

    @field_validator("description_code")
    @classmethod
    def _check_code(cls, v: str) -> str:
        v = clean_ws(v).upper()
        if v and v not in description_codes():
            raise ValueError("is not one of the VO description codes")
        return v

    @field_validator("postcode")
    @classmethod
    def _check_postcode(cls, v: str) -> str:
        v = clean_ws(v)
        if v and parse_postcode_query(v) is None:
            raise ValueError("must be a full UK postcode, sector (e.g. 'CV1 1') or outward code (e.g. 'CV1')")
        return v

    @model_validator(mode="after")
    def _need_location(self) -> "SearchRequest":
        if not self.town and not self.postcode:
            raise ValueError("Enter a town, a postcode, or both.")
        if self.rv_from is not None and self.rv_to is not None and self.rv_from > self.rv_to:
            raise ValueError("Rateable value 'from' cannot be greater than 'to'.")
        return self


class ContactStatus(StrEnum):
    VERIFIED = "verified"
    PROBABLE = "probable"
    REVIEW = "needs_review"
    NO_CONTACT = "no_contact"
    LOOKUP_FAILED = "lookup_failed"
    NOT_SEARCHED = "not_searched"


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "completed_partial"
    NO_RESULTS = "no_results"
    FAILED = "failed"


class PropertyRecord(BaseModel):
    """One VO rating-list entry (a rateable premises, not necessarily a distinct business)."""

    uarn: str
    address: str  # display address incl. postcode
    street: str
    number_or_name: str
    town: str
    postcode: str
    description: str
    rv: int
    firm_name: str = ""
    possible_duplicate_of: str | None = None  # UARN of another entry at the same address

    @computed_field
    @property
    def source_url(self) -> str:
        """The property's page on the VO Find-a-property site."""
        return f"https://www.tax.service.gov.uk/business-rates-find/valuations/start/{self.uarn}"


class ResultRecord(PropertyRecord):
    business_name: str = ""
    phone: str = ""
    contact_status: ContactStatus = ContactStatus.NOT_SEARCHED
    match_score: int | None = None
    match_reasons: list[str] = []
    contact_source: str = ""
    contact_source_url: str = ""
    contact_address: str = ""
    other_numbers: list[str] = []  # other businesses at the same address, "Name: phone"
    business_address: str = ""  # the address as the business itself lists it (street, town, postcode)
    match_note: str = ""  # one short line explaining the match
    collected_at: datetime | None = None

    @computed_field
    @property
    def google_maps_url(self) -> str:
        """Google Maps search for the matched business, for manual checking.

        Searches the business's own listed name + street address + postcode when a business was
        matched (VO floor/unit text like "Bst-Grd Flr" confuses Maps), otherwise the VO address.
        Uses the documented Maps URLs format (no API key, no scraping).
        """
        if self.business_name and self.business_address:
            query = f"{self.business_name}, {self.business_address}"
        else:
            query = ", ".join(p for p in (self.business_name, self.address) if p)
        return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(query)


class JobSummary(BaseModel):
    source_records: int = 0
    unique_premises: int = 0
    phones_found: int = 0
    verified: int = 0
    probable: int = 0
    needs_review: int = 0
    no_contact: int = 0
    lookup_failed: int = 0


class JobStatus(BaseModel):
    id: str
    state: JobState
    stage: str
    progress: float = 0.0  # 0..1 within the whole job
    message: str = ""
    request: SearchRequest
    summary: JobSummary = JobSummary()
    created_at: datetime
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    download_ready: bool = False
    errors: list[str] = []
    employee: str = ""  # who ran the search (free text entered on the dashboard)

    @computed_field
    @property
    def label(self) -> str:
        """Short human name for the search, e.g. "LONDON · EC1V 9LT · CO · £5,000–£50,000"."""
        return search_label(self.request)


def search_label(req: SearchRequest) -> str:
    parts = [req.town.upper(), req.postcode.upper(), req.description_code]
    if req.rv_from is not None or req.rv_to is not None:
        lo = f"£{req.rv_from:,}" if req.rv_from is not None else "£0"
        hi = f"£{req.rv_to:,}" if req.rv_to is not None else "any"
        parts.append(f"{lo}–{hi}")
    return " · ".join(p for p in parts if p)


def clean_employee(name: str) -> str:
    """Validated display name for an employee; raises ValueError when unusable."""
    name = clean_ws(name)
    if not name or len(name) > 60 or not all(ch.isalnum() or ch in " -'." for ch in name):
        raise ValueError("Enter a name of up to 60 letters, numbers, spaces, hyphens or apostrophes.")
    return name
