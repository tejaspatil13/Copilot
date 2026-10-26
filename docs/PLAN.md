# UK Business Contact Finder — Phase 1 findings & plan

_Research date: 26 Oct 2026. Everything marked **verified** was checked directly against the live source on that date._

## 1. What the manual workflow actually is

1. Search the VO "Find a property" service for an area (postcode / street+town / advanced).
2. Open each property to read its **rateable value (RV)**.
3. Keep premises above an RV threshold (sample data: lowest RV is £12,250 → looks like "RV > £12,000", i.e. outside full Small Business Rate Relief).
4. Google the address to find **which business occupies it** and its phone number.
5. Paste name / address / RV / phone into the sheet; callers then fill `comments` (call outcome).

Important: the VO site lists **premises (hereditaments), not businesses**. It never shows the occupier's name
(verified — results show only Address + Description; the bulk data has a firm name on just 3.5% of 2.18M entries).
The business name therefore always comes from the contact-discovery step, which makes matching-by-address the core problem.

## 2. The sample spreadsheet (`khushi new (2).xlsx`) — verified

| Sheet | Contents |
|---|---|
| **Sheet1** (main, 2,870 rows) | `A business name` · `B add` · `C 15000` (header is literally the number 15000; values are RVs, `#,##0`) · `D Contact no` · `E comments` · autofilter A1:F168, bold headers, wrap text, Calibri 11. Cols F–O hold ~46 stray notes. |
| Sheet2 | Dated log of a few calls (dates as separator rows). |
| Sheet3 | Scratch calculator: `ACTUAL BR BILL = RV × 49.3%`, `÷4` (“WITH 75%”), `÷10` (monthly). Plus stray phone numbers / emails. |
| Sheet4 | Same layout, header `RM`, often two RVs (`"17,000 11,750"`) — likely current vs previous list. |
| Sheet5 | Same layout, header `RV`. |

Findings:
- **Column C is the VO rateable value.** Verified: 13 Trinity Street, Coventry CV1 1FJ = Games Workshop, sheet says 18,250 = VO **2023 list** RV (£18,250). The **2026 list** (live since 1 Apr 2026) now says £22,000.
- Phone numbers are stored **without the leading 0** (`24 7655 9900`), mostly as text, some as integers — looks pasted from `+44 …` format.
- `comments` is the caller's outcome log (unavailable / not interested / DNC / names) — it is personal data and is **not** something the tool should produce or copy.
- No formulas in the main sheet; Sheet3's formulas are a manual calculator. The 49.3% multiplier is **not** a current official multiplier I can confirm — we will not compute bills; we only output RV.
- Addresses come in two styles: VO style (`1 -3, The Burges, Coventry, CV1 1HN`) and Google style (`23 Trinity St, Coventry CV1 1FJ, United Kingdom`).

Output plan: a fresh workbook per search, using Sheet1's layout (headers A, B, D, E kept verbatim; C header written as `RV` — sheets 4/5 already use that), same widths/fonts/number format/autofilter, then extra columns to the right:
`Description · Town · Postcode · VO UARN · VO link · Phone source · Source URL · Match status · Match score · Collected at`.
The existing 2,870 call-log rows are **not** copied into outputs (personal data, and they'd duplicate). They are reused as a **test set** (see §6).

## 3. Government data access — recommendation: **official bulk download**, not scraping

| Option | Findings |
|---|---|
| Live site `business-rates-find` | Plain server-rendered HTML + CSRF token + session cookie (no JS needed). 15 results/page, pagination is **session-stateful** (`?searchDirection=FORWARD`). Results contain **no RV** → one extra request per property. Advanced search supports `town`, partial `postCode` (prefix match), `from`/`to` RV range, description code, billing authority. Example: CV1 + RV≥12k = 1,755 items → ~117 page loads + 1,755 detail loads per search. No documented API. |
| **VO rating list bulk download** (`voaratinglists.blob.core.windows.net`) | Official, free, all England & Wales, 2.18M entries, asterisk-delimited CSV. Fields include UARN, full address, street/town/postcode, description code & text, **RV**, firm name (rare). Refreshed every ~2 months + twice-weekly change files. 2026 list zip = 94 MB (515 MB unzipped). **UARN = the ID in the site's URLs** (verified), so we can still link each row to its official page. |

→ Import the bulk list into SQLite once (filtered columns, indexed by postcode/town/RV), refresh on a schedule. A search becomes a local query that takes milliseconds, with zero load on HMRC's service and no anti-bot risk.

**Licence (both routes) — needs your confirmation.** The VO terms restrict use to *Non-Domestic Rating purposes* (letting interested persons — occupiers — and their representatives / service providers review valuations), prohibit onward disclosure for other purposes, exclude personal data, and require compliance with DPA and **PECR**. The bulk download is under the same restricted licence ("Open Government Licence does not apply"). If this is a business-rates review/appeal service for occupiers, that is the use case the licence describes; general sales prospecting is not. I can't decide this for you.

## 4. Phone-number discovery — options compared

| Source | Key | Cost | UK phone coverage | Terms for exporting to Excel |
|---|---|---|---|---|
| **Overture Maps Places** (bulk GeoParquet) | none | free | good in towns (sourced from Meta/Microsoft/Foursquare), has `phones`, `websites`, `confidence` | CDLA-Permissive-2.0 → export OK with attribution |
| **Foursquare OS Places** (bulk Parquet) | free HF account | free | unknown — to be measured; has `tel`, `website`, `date_closed` | Apache-2.0 → export OK with notice |
| OpenStreetMap (Overpass / Geofabrik extract) | none | free | low for small shops | ODbL → export OK, share-alike on the derived DB |
| **Google Places API (New)** | yes, billing account | phone fields = *Enterprise* SKU: Text Search $35/1k (1k free/mo). Cheapest pattern: Text Search *IDs-only* (free) + Place Details Enterprise (~$20/1k, verify) | best | **Problem**: Maps Platform terms forbid caching (except place IDs) and exporting Places content for use outside Google services; data shown without a map needs Google attribution. An exported call list is very likely outside the terms. |
| Business's own website | none | free | depends on finding the site | fine to read a public page politely (robots.txt) |
| Scraping Google Search / Maps | — | — | — | **Not permitted** — excluded. |
| Licensed UK marketing data (e.g. B2B data vendors) | contract | paid | high, often TPS/CTPS-screened | licensed for telemarketing |

**Recommendation:** Build a local "places index" from **Overture + Foursquare OS** (both free, bulk, export-permitted, no rate limits, no per-lookup cost), match each VO premises against it by postcode + house number + street, then optionally fetch the matched business's website to confirm the number. Keep a pluggable provider interface so Google Places (or a paid vendor) can be added later if you accept their terms/cost. Real coverage will be **measured against your 2,870 known rows** before we commit.

## 5. Matching rules (explainable score)

Per VO premises, candidates = places with the **same postcode** (fallback: within ~75 m of the postcode centroid).
- `+50` same postcode · `+30` same house number/unit (handles `1-3`, `Unit 6`, `Gnd Flr`) · `+15` street similarity ≥ 0.85 · `+5` category consistent with VO description (e.g. RESTAURANT ↔ restaurant) · `+5` VO firm name ≈ place name (when present) · `−40` place marked closed · `−20` ≥2 strong candidates at the same address.
- **Verified** ≥ 90 and unique and phone present; **Probable** 70–89; **Needs review** ambiguous/conflicting or 50–69; **No contact found** otherwise. Phone left blank unless Verified/Probable. A name match alone never yields Verified.

Phones are normalised with `phonenumbers` (UK), validated, and written in your sheet's style (see open questions).

## 6. Architecture (minimum viable, deployable)

```
Browser (dashboard)
   │  REST + polling (/jobs/{id})
FastAPI (one container)
   ├─ JobRunner (asyncio, bounded: N concurrent jobs, per-provider rate limits)
   ├─ VO adapter        → SQLite: rating_list (UARN, address parts, desc, RV)
   ├─ Places adapter(s) → SQLite: places (postcode-indexed, from Overture/FSQ)
   ├─ (optional) Website verifier → httpx, timeouts, robots.txt, retries/backoff
   ├─ Matcher / normaliser / dedupe (UARN is the stable key)
   └─ Excel writer (openpyxl, template-based, formula-injection safe) → /data/exports
SQLite: jobs, job_records (partial results survive restarts; retry = resume)
Scheduled task: refresh VO change files + places snapshots
```
- **No Redis/Celery**: everything except optional website checks is a local DB query, so a search finishes in seconds; an in-process job queue is enough. Can be swapped for RQ later.
- Frontend: small React (Vite) app built to static files and served by FastAPI → one deployable unit, no CORS/secrets in the browser.
- **Hosting:** needs a persistent disk (~2–4 GB for both datasets) → Render web service + disk, Fly.io + volume, or a small VPS (Docker). **Vercel/serverless is unsuitable** (read-only FS, size and time limits). Estimated ~$7–15/month; no per-search API cost in the default configuration.
- Security: env-based config, no secrets client-side, Pydantic validation (UK postcode regex, town whitelist from VO data), filenames generated server-side (UUID-based download IDs, no user paths), cells starting `= + - @ \t \r` prefixed with `'`, generic error messages, optional basic-auth / single shared password for the dashboard.

## 7. Phases

1. **Done:** inspection & research (this doc).
2. **MVP:** VO bulk importer → SQLite; `/search` (postcode / outward code / town, RV min/max, exclude non-trading descriptions like advertising rights, car parks, telecom masts); Excel export from template; basic dashboard + download. Tests with fixtures.
3. **Contact discovery:** Overture + FSQ importers, matcher, phone normalisation; **benchmark vs the 2,870 known rows** (precision/recall of phones, per status). Optional website verifier.
4. **Dashboard polish:** progress stages, results table with status filters, review list, partial-result download.
5. **Deploy:** Dockerfile, `.env.example`, README (setup, limits, costs, licences/attribution), deploy + live smoke test.

## 8. Risks / blockers

- VO licence purpose restriction (above) and **PECR**: unsolicited sales calls must be screened against **TPS/CTPS** (sole traders/partnerships are "individuals"; companies via CTPS). The tool can flag but not perform this without a TPS licence/file.
- Open-data phone coverage may be lower than Google's — to be measured, not assumed.
- Premises ≠ business: multi-occupancy, vacant units, recently changed occupiers → "Needs review".
- The 2023 vs 2026 RV difference changes which premises clear a threshold.
