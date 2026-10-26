"""Contact-provider interface. Each provider turns a VO premises into candidate businesses."""
from typing import Protocol

from pydantic import BaseModel

from app.models import PropertyRecord


class ContactCandidate(BaseModel):
    name: str
    address: str  # as given by the source (street line(s), town)
    postcode: str = ""
    phone: str = ""  # raw, normalised later
    website: str = ""
    categories: list[str] = []
    closed: bool = False
    source: str  # provider id, e.g. "overture"
    source_url: str = ""
    source_id: str = ""
    source_confidence: float | None = None  # provider's own 0..1 confidence, if it has one
    distance_m: float | None = None  # set when matched by proximity rather than postcode


class ProviderError(Exception):
    """Base for recoverable provider failures; the record is marked lookup_failed, the job continues."""


class ProviderRateLimited(ProviderError):
    def __init__(self, retry_after: float | None = None):
        super().__init__(f"rate limited (retry after {retry_after}s)" if retry_after else "rate limited")
        self.retry_after = retry_after


class ProviderUnavailable(ProviderError):
    pass


class ContactProvider(Protocol):
    name: str

    async def candidates(self, record: PropertyRecord) -> list[ContactCandidate]: ...
