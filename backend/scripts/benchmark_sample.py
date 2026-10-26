"""Measure contact-discovery accuracy against the client's manually researched sample sheet.

The sample's address cells hyperlink to VO valuation pages (…/valuations/start/<UARN>) and the
"Contact no" column holds the phone number a person found by hand. For every row with both, we
run the real provider + matcher on the VO record and compare.

Only aggregate numbers are printed — no names, numbers or comments from the sheet.

    python scripts/benchmark_sample.py "../khushi new (2).xlsx"
"""
import asyncio
import re
import sys
import time
from collections import Counter
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.contacts.registry import build_providers  # noqa: E402
from app.matching import choose, normalize_phone  # noqa: E402
from app.models import ContactStatus  # noqa: E402
from app.voa.repository import VoaRepository  # noqa: E402

UARN_LINK = re.compile(r"/valuations/(?:start/)?(\d+)")


def truth_rows(path: Path) -> dict[str, str]:
    """UARN -> expected phone (UK national format) from every sheet that uses the call-list layout."""
    wb = openpyxl.load_workbook(path)
    truth: dict[str, str] = {}
    for ws in wb.worksheets:
        for row in ws.iter_rows(min_row=2):
            if len(row) < 4 or not row[1].hyperlink:
                continue
            m = UARN_LINK.search(row[1].hyperlink.target or "")
            raw = str(row[3].value or "").replace("\xa0", " ").strip()
            if not m or not raw:
                continue
            digits = re.sub(r"\D", "", raw)
            digits = digits[2:] if digits.startswith("44") else digits
            if phone := normalize_phone("0" + digits.lstrip("0")):
                truth[m.group(1)] = phone
    return truth


async def main(sample: Path) -> None:
    settings = get_settings()
    providers = build_providers(settings)
    if not providers:
        sys.exit("No contact provider available (import Overture places first).")
    truth = truth_rows(sample)
    records = VoaRepository(settings.voa_db_path).get_many(list(truth))
    print(f"sample rows with VO link + phone: {len(truth):,}; found in 2026 VO list: {len(records):,}")

    started = time.monotonic()
    outcome: Counter = Counter()
    for uarn, rec in records.items():
        cands = []
        for p in providers:
            cands += await p.candidates(rec)
        status, phone = (m := choose(rec, cands)).status, m.phone
        any_cand_has_truth = any(normalize_phone(c.phone) == truth[uarn] for c in cands)
        outcome[(status, "phone=truth" if phone == truth[uarn] else "phone!=truth" if phone else "no phone")] += 1
        outcome[("candidates contain true number", any_cand_has_truth)] += 1
    elapsed = time.monotonic() - started

    n = len(records)
    print(f"\nlookups: {n:,} in {elapsed:.1f}s ({n / max(elapsed, 1e-9):,.0f}/s)\n")
    print(f"{'status':<16}{'same as sheet':>15}{'different':>12}{'no phone':>10}")
    for st in ContactStatus:
        row = [outcome[(st, k)] for k in ("phone=truth", "phone!=truth", "no phone")]
        if any(row):
            print(f"{st.value:<16}{row[0]:>15,}{row[1]:>12,}{row[2]:>10,}")
    answered = sum(outcome[(s, "phone=truth")] + outcome[(s, "phone!=truth")] for s in ContactStatus)
    agree = sum(outcome[(s, "phone=truth")] for s in ContactStatus)
    print(f"\nphone returned for {answered:,}/{n:,} ({answered / n:.0%}); agrees with sheet in {agree:,} ({agree / max(answered, 1):.0%} of returned)")
    for st in (ContactStatus.VERIFIED, ContactStatus.PROBABLE):
        t, d = outcome[(st, "phone=truth")], outcome[(st, "phone!=truth")]
        if t + d:
            print(f"  {st.value}: {t / (t + d):.0%} agree ({t:,}/{t + d:,})")
    hit = outcome[("candidates contain true number", True)]
    print(f"true number present among candidates (upper bound for this source): {hit:,}/{n:,} ({hit / n:.0%})")


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1])))
