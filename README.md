# Pakistan Floods 2022 — End-to-End Data Analysis

A complete, honest, static web walkthrough of a **real** data analysis on **real**
Pakistan data: *which districts were hit hardest by the 2022 floods, and where
did relief fall short?* Built mobile-first in plain language, with the usually
hidden **cleaning stage made visible**.

**Live demo:** *(deploy this folder to GitHub Pages)*
**No invented data. No fake “live” badges — the app is labelled “Data snapshot — not live”.**

---

## 1. Data provenance (exact)

| # | Dataset (exact title) | Publisher | HDX link | Licence | Snapshot used |
|---|---|---|---|---|---|
| 1 | Preliminary Satellite Derived Flood Evolution Assessment, Islamic Republic of Pakistan — 22 October 2022 | UNOSAT | https://data.humdata.org/dataset/740ff03f-5bf9-49b1-a125-a1e3ad114938 | CC BY-SA 4.0 | District sheet, 175 rows × 55 cols, downloaded 2 Oct 2026 |
| 2 | Pakistan: Who does What, Where, When and for Whom (5W) — resource `PAK_5W_Aug 22 to Dec 23` | OCHA Pakistan | https://data.humdata.org/dataset/41cfeb67-7eee-434a-8687-0670eb50ebb3 | CC BY-SA 4.0 | 91,094 rows × 75 cols, all tagged “Monsoon Floods 2022”, downloaded 2 Oct 2026 |

Dataset 1 gives **need** (satellite-measured flood extent km² + people exposed,
per district, 9 time windows Aug–Nov 2022). Dataset 2 gives **response**
(91,094 relief-activity rows: district, sector, organisation, households and
beneficiaries reached, Aug 2022–Dec 2023).

## 2. The pipeline (5 stages, mirrored in the app)

1. **The Question** — which districts were hit hardest, and where did relief fall short?
2. **Raw Data** — the two files above, shown unedited (mess included).
3. **Cleaning** — `scripts/clean_data.py` fixes 16 real issues, e.g.:
   - province names sitting inside the district table (`Balochistan`, `Azad Kashmir (2)`) → used as headers
   - UN footnote/disclaimer rows + merged-cell junk rows (`satellitedata:satellitedata:between25to31august…`) → dropped
   - exact duplicate `Islamabad` row → deduped
   - 9 overlapping satellite windows → per-district **peak** (max) values, documented
   - float artefacts (`877964.6739099998`) → rounded; blanks left blank
   - 5W: column literally named `PROVINCE `, `IMPLEMENTNG PARTNER` typo, 16 province spellings, 239 district spellings → 133 canonical districts (documented alias map), `Nasirabad` filed under 4 provinces → collapsed to mode
4. **Exploration** — charts computed from the cleaned CSVs, each with a one-line plain-English takeaway.
5. **Findings & Recommendations** — citizen view (simple words) and official/NGO view (figures, gap table, export pack), plus an honest “what this data cannot tell us” box.

Outputs of the script land in `data/`:

- `cleaned_district_flood.csv` — 160 districts: province, area, population, peak flood extent, peak exposed population
- `cleaned_relief_by_district.csv` — 133 districts: beneficiaries/households reached, people targeted, activities, sectors, agencies
- `gap_analysis.csv` — the join: exposed vs reached, coverage ratio, gap flag
- `raw_samples/` — 12 unedited raw rows from each file (for the dirty-vs-clean toggle)
- `cleaning_log.json` — machine-readable log of every issue + fix

## 3. Key findings (from the cleaned data)

- **31.25M people** lived in flooded areas (UNOSAT Aug 2022 headline); **83,557 km²** max flood extent.
- **Sindh 59.8% + Punjab 30.8%** of exposed people — two provinces, >90% of impact.
- **27 districts** have satellite-measured flooding but **no relief rows at all** in the 5W file, led by Gujranwala (653K exposed), Sujawal (635K), Muzaffargarh (579K), Narowal (576K).
- **12 more districts** (led by Sialkot, 1.81M exposed) have relief *activities* on record — Sialkot’s 2 activities are even marked “Complete” — but **zero beneficiaries reported reached**. A sharper finding than “no rows”: the paperwork exists, the people aren’t counted.
- **Punjab’s coverage gap:** 9.82M exposed vs 5.69M beneficiaries; Sindh 19.09M vs 24.78M.
- Beneficiaries (46.6M) exceed exposed people (31.9M) — expected: agencies self-report and one person is counted per activity. Coverage is a *relative* signal.
- Widest sectors: Shelter/NFI (92 districts), Food Security (85), Health (82), WASH (79), Nutrition (77).

## 4. How to refresh / reproduce

```bash
# 1. Download the two raw files from the HDX links above, then:
python3 scripts/clean_data.py \
    --unosat /path/to/unosat_assessment.xlsx \
    --w5     /path/to/PAK_5W_Aug_22_to_Dec_23.xlsx \
    --outdir data
# 2. Open index.html (or serve the folder) — charts read the CSVs in data/.
```

Requirements: Python 3 + `pandas` + `openpyxl`. Charts use Chart.js from CDN
with automatic table fallbacks if the CDN is unreachable.

## 5. Honest limitations

- Satellite estimates, not door-to-door counts; cloud cover and timing affect them.
- 5W relief data is self-reported; double counting is certain.
- Flood windows (Aug–Nov 2022) vs relief window (to Dec 2023) — timing mismatch.
- Neither file contains deaths, injuries, destroyed houses or livestock — those need NDMA sitreps, which are not published as open district-level CSVs.
- District peaks happened in different weeks — don’t sum them as a “total”; the national figure is UNOSAT’s own 31.25M.

## 6. Project layout

```
├── index.html            # the 5-stage app
├── styles.css            # mobile-first styles
├── app.js                # stage nav, tables, charts, export
├── data/                 # cleaned CSVs + cleaning_log.json + raw_samples/
├── scripts/
│   └── clean_data.py     # raw XLSX → cleaned CSVs (reproducible)
└── README.md
```
