"""Builds the list of enabled contact providers from settings / available datasets."""
import logging

from app.config import Settings
from app.contacts.base import ContactProvider

log = logging.getLogger(__name__)


def build_providers(settings: Settings) -> list[ContactProvider]:
    providers: list[ContactProvider] = []
    if settings.places_db_path.exists():
        from app.contacts.local_places import LocalPlacesProvider

        providers.append(LocalPlacesProvider(settings.places_db_path))
    if not providers:
        log.warning("No contact providers available — searches will return premises without phone numbers.")
    return providers
