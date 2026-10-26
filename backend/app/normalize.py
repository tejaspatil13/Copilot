"""Text, postcode and address normalisation shared by the VO, places and matching code."""
import re

# Full UK postcode, e.g. "CV1 1FJ", "SW1A 2AA", "M1 1AE".
_FULL_PC = re.compile(r"^([A-Z]{1,2}[0-9][A-Z0-9]?)\s*([0-9][A-Z]{2})$")
# Outward code ("CV1") or sector ("CV1 1").
_OUTWARD = re.compile(r"^[A-Z]{1,2}[0-9][A-Z0-9]?$")
_SECTOR = re.compile(r"^([A-Z]{1,2}[0-9][A-Z0-9]?)\s*([0-9])$")
_PC_IN_TEXT = re.compile(r"\b([A-Z]{1,2}[0-9][A-Z0-9]?)\s*([0-9][A-Z]{2})\b", re.I)

_WS = re.compile(r"\s+")


def clean_ws(value: str | None) -> str:
    """Collapse all whitespace (incl. newlines, NBSP) to single spaces and strip."""
    if not value:
        return ""
    return _WS.sub(" ", value.replace("\xa0", " ")).strip()


def normalize_postcode(value: str | None) -> str | None:
    """Return a canonical full postcode ("CV1 1FJ") or None if it is not a full postcode."""
    v = clean_ws(value).upper()
    m = _FULL_PC.match(v)
    return f"{m.group(1)} {m.group(2)}" if m else None


def parse_postcode_query(value: str) -> tuple[str, str] | None:
    """Classify a user postcode query.

    Returns (kind, canonical) where kind is "full", "sector" or "outward", or None if invalid.
    """
    v = clean_ws(value).upper()
    if full := normalize_postcode(v):
        return "full", full
    if m := _SECTOR.match(v):
        return "sector", f"{m.group(1)} {m.group(2)}"
    if _OUTWARD.match(v.replace(" ", "")):
        return "outward", v.replace(" ", "")
    return None


def postcode_in_text(text: str | None) -> str | None:
    m = _PC_IN_TEXT.search(text or "")
    return f"{m.group(1).upper()} {m.group(2).upper()}" if m else None


_JOINERS = {"AND", "OF", "THE", "AT", "ON", "IN", "TO"}


def smart_title(value: str | None) -> str:
    """Title-case an upper-case VO string ("9-11, TRINITY STREET" -> "9-11, Trinity Street").

    Tokens containing digits (postcodes, unit codes like "2A") stay upper-case.
    """
    out = []
    for i, word in enumerate(clean_ws(value).split(" ")):
        starts_segment = i == 0 or out[-1].endswith(",")
        if re.fullmatch(r"\d+(ST|ND|RD|TH),?", word, re.I):
            out.append(word.lower())  # ordinals: "1ST" -> "1st"
        elif any(ch.isdigit() for ch in word):
            out.append(word.upper())
        elif not starts_segment and word.upper().strip(",") in _JOINERS:
            out.append(word.lower())
        else:
            out.append("-".join(p[:1].upper() + p[1:].lower() for p in word.split("-")))
    return " ".join(out)


# Abbreviations used interchangeably by VO, Google-style and OSM-style addresses.
_STREET_ABBR = {
    "st": "street", "rd": "road", "ave": "avenue", "av": "avenue", "ln": "lane", "dr": "drive",
    "ct": "court", "pl": "place", "sq": "square", "cres": "crescent", "gdns": "gardens",
    "terr": "terrace", "ter": "terrace", "pde": "parade", "hwy": "highway", "cl": "close",
    "gr": "grove", "bldgs": "buildings", "ind": "industrial", "est": "estate",
}
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")


def street_key(street: str | None) -> str:
    """Comparable street name: lower-case, punctuation-free, abbreviations expanded."""
    words = _NON_ALNUM.sub(" ", clean_ws(street).lower()).split()
    return " ".join(_STREET_ABBR.get(w, w) for w in words)


_NUM_TOKEN = re.compile(r"\b(\d+)\s*([a-z])?\b", re.I)


def house_numbers(text: str | None) -> set[str]:
    """Extract house/unit numbers ("1-3" -> {"1","2","3"}, "12a" -> {"12a"}) from an address fragment."""
    t = clean_ws(text).lower()
    nums: set[str] = set()
    for a, b in re.findall(r"\b(\d+)\s*-\s*(\d+)\b", t):
        lo, hi = int(a), int(b)
        if 0 < hi - lo <= 20:
            nums.update(str(n) for n in range(lo, hi + 1))
    for n, letter in _NUM_TOKEN.findall(t):
        nums.add(n + (letter or "").lower())
        nums.add(n)
    return nums


def name_key(name: str | None) -> str:
    """Comparable business name: lower-case, no punctuation or legal suffixes."""
    t = _NON_ALNUM.sub(" ", clean_ws(name).lower())
    words = [w for w in t.split() if w not in {"ltd", "limited", "plc", "llp", "the", "co", "uk"}]
    return " ".join(words)
