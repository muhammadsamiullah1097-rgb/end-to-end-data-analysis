#!/usr/bin/env python3
"""
clean_data.py — Reproducible cleaning pipeline for the
"End-to-End Data Analysis: 2022 Pakistan Floods" project.

WHAT IT DOES
------------
Takes two REAL raw datasets and produces cleaned, analysis-ready CSVs:

  1. UNOSAT "Preliminary Satellite Derived Flood Evolution Assessment,
     Islamic Republic of Pakistan - 22 October 2022"
     (https://data.humdata.org — district-level flood water extent in km2
     and population potentially exposed, Aug-Nov 2022, 9 time windows)

  2. OCHA Pakistan "Who does What, Where, When and for Whom (5W)"
     resource "PAK_5W_Aug 22 to Dec 23.xlsx"
     (https://data.humdata.org — 91,094 relief-activity rows, all tagged
     "Monsoon Floods 2022": households reached, beneficiaries, sectors,
     organisations, by district)

USAGE
-----
    python3 scripts/clean_data.py \
        --unosat /path/to/unosat.xlsx \
        --w5     /path/to/PAK_5W_Aug_22_to_Dec_23.xlsx \
        --outdir data

Outputs (in --outdir):
    cleaned_district_flood.csv    — one row per district: province,
                                    area_km2, population, peak flood water
                                    extent (km2), peak exposed population
    cleaned_relief_by_district.csv — one row per district: relief
                                    beneficiaries/households reached,
                                    people targeted, activities, sectors,
                                    organisations
    gap_analysis.csv              — districts joined: exposed population vs
                                    beneficiaries reached, coverage ratio,
                                    gap flag
    raw_samples/raw_sample_unosat.csv — first 12 UNEDITED rows (messiness kept)
    raw_samples/raw_sample_5w.csv     — 12 UNEDITED 5W rows (messiness kept)
    cleaning_log.json             — machine-readable log of every fix

Design decisions (also shown in the app):
  * Province rows in the UNOSAT sheet ("Balochistan", "Azad Kashmir (2)", …)
    are summary/header rows, not districts → removed, but their values are
    kept as province-level aggregates via the district sums.
  * Footnote/UN-disclaimer rows and the exact-duplicate "Islamabad" row
    are dropped (logged).
  * "Peak" flood extent / exposed population = maximum across the 9
    satellite time windows (documented, not hidden).
  * Float artefacts (e.g. 877964.6739099998) are rounded to sane precision.
  * District names are canonicalised between the two sources
    (case/whitespace/punctuation + a small documented alias map) so the
    NEED (flood) and RELIEF (5W) tables can be joined.
  * Coverage = beneficiaries_reached / exposed_population. It can exceed 1
    because 5W counts are self-reported by agencies and one person can be
    reached by several activities; the app says so honestly.
"""

import argparse
import json
import os
import re
import sys

import pandas as pd

# ---------------------------------------------------------------- constants
PROVINCES = {
    "azad kashmir": "Azad Jammu & Kashmir",
    "gilgit baltistan": "Gilgit-Baltistan",
    "balochistan": "Balochistan",
    "khyber pakhtunkhwa": "Khyber Pakhtunkhwa",
    "punjab": "Punjab",
    "sindh": "Sindh",
    "islamabad": "Islamabad",
    "azad jammu and kashmir": "Azad Jammu & Kashmir",
}

# 5W spellings -> canonical UNOSAT spellings (both normalised first)
ALIAS = {
    "shaheedbenazirabad": "Shaheed Benazir Abad",
    "shaheedbenazir abad": "Shaheed Benazir Abad",
    "kambershahdadkot": "Kambar Shahdad Kot",
    "kambarshahdadkot": "Kambar Shahdad Kot",
    "qambarshahdadkot": "Kambar Shahdad Kot",
    "umerkot": "Umer Kot",
    "umer kot": "Umer Kot",
    "mirpurkhas": "Mirpur Khas",
    "mirpur khas": "Mirpur Khas",
    "dikhan": "D. I. Khan",
    "d i khan": "D. I. Khan",
    "dera ismail khan": "D. I. Khan",
    "deraismailkhan": "D. I. Khan",
    "chitral-lower": "Chitral Lower",
    "chitral-upper": "Chitral Upper",
    "kohistanlower": "Kohistan Lower",
    "kohistanupper": "Kohistan Upper",
    "kohistan lower": "Kohistan Lower",
    "kohistan upper": "Kohistan Upper",
    "nawabshah": "Shaheed Benazir Abad",
    "kashmore-kandhkot": "Kashmore",
    "kashmorekandhkot": "Kashmore",
    "nausheroferoze": "Naushahro Feroze",
    "naushahroferoze": "Naushahro Feroze",
    "jhelumvalley": "Jhelum Valley",
    "centralkarachi": "Central Karachi",
    "eastkarachi": "East Karachi",
    "westkarachi": "West Karachi",
    "southkarachi": "South Karachi",
    "korangikarachi": "Korangi Karachi",
    "malirkarachi": "Malir Karachi",
    "karachicentral": "Central Karachi",
    "karachieast": "East Karachi",
    "karachiwest": "West Karachi",
    "karachisouth": "South Karachi",
    "karachimalir": "Malir Karachi",
    "karachikorangi": "Korangi Karachi",
}

FOOTNOTE_MARKERS = (
    "(1) the designations",
    "(2) the final status",
    "analysis: united nations satellite centre",
    "boundary data:",
    "population data:",
)

log = {"issues": [], "actions": []}


def note(issue, action, count=None):
    entry = {"issue": issue, "action": action}
    if count is not None:
        entry["count"] = int(count)
    log["issues"].append(entry)
    msg = f"ISSUE: {issue}\n  -> {action}"
    if count is not None:
        msg += f" (n={count})"
    print(msg, flush=True)


def norm_key(name):
    """Canonical join key: lowercase, no spaces/dots/hyphens."""
    return re.sub(r"[\s.\-_']", "", str(name).strip().lower())


def canon_district(raw):
    key = norm_key(raw)
    if key in ALIAS:
        return ALIAS[key]
    # Title-case normalisation: 'RAJANPUR' -> 'Rajanpur',
    # 'DERA GHAZI KHAN' -> 'Dera Ghazi Khan'
    return " ".join(w[:1].upper() + w[1:].lower()
                    for w in str(raw).strip().split())


# ------------------------------------------------------------------ UNOSAT
def clean_unosat(path):
    u = pd.read_excel(path, sheet_name="Statistics by district level",
                      engine="openpyxl")
    raw_rows = len(u)
    note("Raw district sheet has no real header separation",
         "Used first row as header; kept all 175 raw rows for inspection",
         raw_rows)

    names = u.iloc[:, 0].astype(str).str.strip()

    # 0) exact-duplicate data rows FIRST ('Islamabad' is listed twice with
    #    identical values — one copy would otherwise be misread as a
    #    province header below)
    dup_mask = u.duplicated(keep="first")
    n_dup = int(dup_mask.sum())
    if n_dup:
        dup_names = sorted(set(names[dup_mask].tolist()))
        note("Exact duplicate data rows",
             f"Dropped duplicate rows (districts: {', '.join(dup_names)})",
             n_dup)
    u = u.loc[~dup_mask].reset_index(drop=True)
    names = u.iloc[:, 0].astype(str).str.strip()

    # 0b) junk rows: merged-cell artefacts, e.g. a row whose "district"
    #     name is literally a concatenation of the satellite window labels
    #     ('satellitedata:satellitedata:between25to31august,...')
    is_junk = (names.str.contains("satellitedata", case=False, na=False)
               | (names.str.len() > 50))
    n_junk = int(is_junk.sum())
    if n_junk:
        note("Junk rows from merged spreadsheet cells "
             "(satellite window labels glued into the district column)",
             "Dropped junk rows", n_junk)

    # 1) footnote / UN disclaimer rows
    is_footnote = names.str.lower().str.startswith(FOOTNOTE_MARKERS)
    n_foot = int(is_footnote.sum())
    note("Footnote/UN-disclaimer rows mixed into the data table",
         "Dropped footnote rows", n_foot)

    # 2) country row
    is_country = names.str.lower() == "pakistan"

    # 3) province header rows: known province names, with or without "(N)"
    prov_pat = names.str.replace(r"\s*\(\d+\)$", "", regex=True).str.lower()
    is_province = prov_pat.isin(PROVINCES.keys()) & ~is_footnote & ~is_country \
        & ~is_junk
    n_prov = int(is_province.sum())
    note("Province names appear as rows inside the district table "
         "(e.g. 'Balochistan', 'Azad Kashmir (2)')",
         "Marked them as province headers; districts below each inherit it",
         n_prov)

    # assign province to following district rows
    province_of = []
    current = None
    for i, nm in enumerate(names):
        if is_province.iloc[i]:
            key = re.sub(r"\s*\(\d+\)$", "", nm).strip().lower()
            current = PROVINCES.get(key, nm)
        elif is_country.iloc[i] or is_footnote.iloc[i] or is_junk.iloc[i]:
            province_of.append(None)
            continue
        province_of.append(current)

    keep = ~(is_footnote | is_country | is_province | is_junk)

    # A "province header" with no districts under it is actually a district
    # (this happens for 'Islamabad': the lone row was being read as a
    # province header with an empty group)
    prov_idx = names[is_province].index.tolist()
    district_counts = {}
    for k, pi in enumerate(prov_idx):
        nxt = prov_idx[k + 1] if k + 1 < len(prov_idx) else len(names)
        district_counts[pi] = int(
            ((names.index >= pi + 1) & (names.index < nxt) & keep).sum())
    for pi, cnt in district_counts.items():
        if cnt == 0:
            is_province.iloc[pi] = False
            keep.iloc[pi] = True
            note("Row read as a province header but with no districts under it",
                 f"Treated {names.iloc[pi]!r} as a district of itself")

    d = u.loc[keep].copy()
    d["province"] = [p for i, p in enumerate(province_of) if keep.iloc[i]]
    d["district_raw"] = names.loc[keep].values

    # sanity: join keys must be unique now
    d["district"] = d["district_raw"].apply(canon_district)
    d["join_key"] = d["district"].apply(norm_key)
    n_dupkey = int(d["join_key"].duplicated().sum())
    if n_dupkey:
        note("Districts still duplicated after cleaning",
             "Kept first; investigate before publishing", n_dupkey)
        d = d.drop_duplicates(subset=["join_key"], keep="first")

    # 5) metric columns: 9 time windows -> peak across windows
    cols = list(u.columns)
    extent_idx = [5, 10, 15, 20, 25, 30, 35, 40, 45]
    expos_idx = [6, 11, 16, 21, 26, 31, 36, 41, 46]
    for idx in extent_idx + expos_idx + [1, 2]:
        d[cols[idx]] = pd.to_numeric(d[cols[idx]], errors="coerce")

    note("9 overlapping satellite time windows (Aug-Nov 2022)",
         "Took the MAXIMUM flood extent and exposed population across "
         "windows as the district's 'peak' value (documented, not hidden)")

    d["area_km2"] = d[cols[1]].round(1)
    d["population"] = d[cols[2]].round(0).astype("Int64")
    d["flood_extent_km2"] = d[[cols[i] for i in extent_idx]].max(axis=1).round(1)
    d["exposed_pop"] = (d[[cols[i] for i in expos_idx]]
                        .max(axis=1).round(0).astype("Int64"))

    # 6) float precision artefacts
    note("Float precision artefacts (e.g. 877964.6739099998)",
         "Rounded areas to 1 decimal, people to whole numbers")

    # 7) missing values
    n_missing = int(d["exposed_pop"].isna().sum() + d["flood_extent_km2"].isna().sum())
    note("Missing values in metric columns",
         "Left as blank (not filled with 0 — a blank means 'not measured')",
         n_missing)

    out = d[["district", "province", "area_km2", "population",
             "flood_extent_km2", "exposed_pop", "join_key"]].copy()
    out = out.sort_values("exposed_pop", ascending=False,
                          na_position="last").reset_index(drop=True)
    return out, names, keep


# ---------------------------------------------------------------------- 5W
def clean_5w(path):
    w = pd.read_excel(path, sheet_name="PAK_5Ws", engine="openpyxl")
    raw_rows = len(w)
    note("Raw 5W workbook: 91k rows x 75 columns",
         "Kept only the columns needed for the analysis", raw_rows)

    def find(*needles):
        for c in w.columns:
            s = str(c).strip().upper()
            if all(n in s for n in needles):
                return c
        return None

    c_prov = find("PROVINCE")
    c_dist = find("DISTRICT")
    c_ben = find("TOTAL NUMBER OF BENEFICIARIES")
    c_hh = find("HOUSEHOLDS REACHED")
    c_tgt = find("PEOPLE TARGETED")
    c_sec = find("SECTOR")
    c_lead = find("LEAD AGENCY")
    c_stat = find("STATUS")
    note("Column names are messy in the raw file",
         f"Examples: column literally named {c_prov!r} (trailing space), "
         f"'IMPLEMENTNG PARTNER' (typo), 'GIRLS (0017 yrs)' (missing dash)")

    # provinces: case/whitespace variants
    prov_raw = w[c_prov].astype(str)
    prov_variants = (prov_raw[prov_raw.str.strip().str.lower()
                              .isin(PROVINCES.keys())]
                     .value_counts())
    note("Same province spelled many ways",
         f"'{c_prov}' values included: "
         + ", ".join(f"{k!r} ({v})" for k, v in prov_variants.head(12).items()),
         len(prov_variants))
    w["_province"] = (prov_raw.str.strip().str.lower()
                      .map(PROVINCES).fillna(prov_raw.str.strip()))

    # districts: case variants + non-district entries
    dist_raw = w[c_dist].astype(str).str.strip()
    n_dist_raw = dist_raw.nunique()
    note("District column has case variants and non-district entries",
         "Examples: 'AWARAN' vs 'Awaran', 'CENTRAL KARACHI', 'CHITRAL LOWER'; "
         "normalised with the alias map",
         n_dist_raw)
    w["_district"] = dist_raw.apply(canon_district)
    w["_join_key"] = w["_district"].apply(norm_key)

    # numerics
    for c, label in ((c_ben, "beneficiaries"), (c_hh, "households"),
                     (c_tgt, "people targeted")):
        num = pd.to_numeric(w[c], errors="coerce")
        n_bad = int(((w[c].notna()) & (num.isna())).sum())
        if n_bad:
            note(f"Non-numeric values in {label} column",
                 "Coerced to blank (NaN); treated as 0 in district sums",
                 n_bad)
        w[c] = num.fillna(0)

    # status variants
    stat_raw = w[c_stat].astype(str)
    stat_variants = stat_raw.value_counts()
    w["_status"] = stat_raw.str.strip().str.title()
    note("Activity-status spelled inconsistently",
         "Examples: " + ", ".join(f"{k!r}" for k in stat_variants.index[:6]),
         len(stat_variants))

    # districts sometimes sit under the wrong province ('Nasirabad' appears
    # in 4 provinces — data-entry slips); collapse to one row per district
    # using the most common label
    def _mode(s):
        m = s.mode()
        return m.iloc[0] if len(m) else None

    g = w.groupby("_join_key", dropna=False)
    agg = g.agg(
        district=("_district", _mode),
        province=("_province", _mode),
        beneficiaries_reached=(c_ben, "sum"),
        households_reached=(c_hh, "sum"),
        people_targeted=(c_tgt, "sum"),
        activities=(c_ben, "size"),
        sectors=(c_sec, lambda s: "; ".join(sorted(set(str(x).strip()
                                                       for x in s.dropna()
                                                       if str(x).strip())))),
        lead_agencies=(c_lead, "nunique"),
        pct_complete=("_status", lambda s: round(
            (s == "Complete").mean() * 100, 1)),
    ).reset_index().rename(columns={"_join_key": "join_key"})
    agg["beneficiaries_reached"] = agg["beneficiaries_reached"].round(0).astype(int)
    agg["households_reached"] = agg["households_reached"].round(0).astype(int)
    agg["people_targeted"] = agg["people_targeted"].round(0).astype(int)
    note("District column collapsed from raw variants to canonical districts",
         "Grouped 91k activity rows by canonical district",
         len(agg))
    return agg.sort_values("beneficiaries_reached", ascending=False)


# ------------------------------------------------------------------- join
def build_gap(flood, relief):
    j = flood.merge(relief, on="join_key", how="outer",
                    suffixes=("_flood", "_relief"))
    j["district"] = j["district_flood"].fillna(j["district_relief"])
    j["province"] = j["province_flood"].fillna(j["province_relief"])
    j["exposed_pop"] = j["exposed_pop"].fillna(0).astype(int)
    j["flood_extent_km2"] = j["flood_extent_km2"].fillna(0)
    j["beneficiaries_reached"] = j["beneficiaries_reached"].fillna(0).astype(int)
    j["households_reached"] = j["households_reached"].fillna(0).astype(int)
    j["activities"] = j["activities"].fillna(0).astype(int)

    n_no_flood = int(j["district_flood"].isna().sum())
    n_no_relief = int(((j["district_relief"].isna()) &
                       (j["exposed_pop"] > 0)).sum())
    note("Districts with relief reports but no UNOSAT flood record",
         "Kept in the table (exposed_pop = 0); they are real places with "
         "real relief — the satellite assessment simply did not cover them",
         n_no_flood)
    note("Flood-hit districts with NO relief rows in the 5W file",
         "Flagged as 'BIG GAP — no relief rows at all' — a core finding",
         n_no_relief)
    n_zero_ben = int(((j["district_relief"].notna()) &
                      (j["beneficiaries_reached"] == 0) &
                      (j["exposed_pop"] > 0)).sum())
    note("Districts WITH relief rows but 0 beneficiaries reported "
         "(activities exist on paper, nobody counted as reached — "
         "e.g. Sialkot: 2 'Complete' activities, 0 beneficiaries)",
         "Flagged as 'BIG GAP — relief rows exist, 0 beneficiaries reported'",
         n_zero_ben)

    j["coverage_ratio"] = j.apply(
        lambda r: (r["beneficiaries_reached"] / r["exposed_pop"]
                   if r["exposed_pop"] > 0 else None), axis=1)

    def gap(r):
        if pd.isna(r["district_flood"]):
            return "no flood record"
        if r["exposed_pop"] == 0:
            return "no flooding measured"
        if pd.isna(r["district_relief"]):
            return "BIG GAP — no relief rows at all"
        if r["beneficiaries_reached"] == 0:
            return "BIG GAP — relief rows exist, 0 beneficiaries reported"
        if r["coverage_ratio"] < 0.25:
            return "BIG GAP — relief far below need"
        if r["coverage_ratio"] < 0.75:
            return "partial gap"
        return "covered"

    j["gap_flag"] = j.apply(gap, axis=1)
    cols = ["district", "province", "area_km2", "population",
            "flood_extent_km2", "exposed_pop", "beneficiaries_reached",
            "households_reached", "people_targeted", "activities",
            "coverage_ratio", "gap_flag"]
    return j[cols].sort_values("exposed_pop", ascending=False)


# ------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unosat", required=True)
    ap.add_argument("--w5", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    os.makedirs(os.path.join(args.outdir, "raw_samples"), exist_ok=True)

    log["sources"] = {
        "unosat": {
            "title": "Preliminary Satellite Derived Flood Evolution "
                     "Assessment, Islamic Republic of Pakistan - "
                     "22 October 2022",
            "publisher": "United Nations Satellite Centre (UNOSAT)",
            "url": "https://data.humdata.org/dataset/740ff03f-5bf9-49b1-"
                   "a125-a1e3ad114938",
            "license": "Creative Commons Attribution-ShareAlike 4.0 (HDX)",
        },
        "ocha_5w": {
            "title": "Pakistan: Who does What, Where, When and for Whom "
                     "(5W) — resource PAK_5W_Aug 22 to Dec 23",
            "publisher": "OCHA Pakistan",
            "url": "https://data.humdata.org/dataset/41cfeb67-7eee-434a-"
                   "8687-0670eb50ebb3",
            "license": "Creative Commons Attribution-ShareAlike 4.0 (HDX)",
        },
    }

    flood, raw_names, keep = clean_unosat(args.unosat)
    relief = clean_5w(args.w5)
    gap = build_gap(flood, relief)

    flood.to_csv(os.path.join(args.outdir, "cleaned_district_flood.csv"),
                 index=False)
    relief.to_csv(os.path.join(args.outdir, "cleaned_relief_by_district.csv"),
                  index=False)
    gap.to_csv(os.path.join(args.outdir, "gap_analysis.csv"), index=False)

    # raw (dirty) samples for the "see dirty vs clean" toggle
    u = pd.read_excel(args.unosat, sheet_name="Statistics by district level",
                      engine="openpyxl")
    u.head(12).to_csv(os.path.join(args.outdir, "raw_samples",
                                   "raw_sample_unosat.csv"), index=False)
    w = pd.read_excel(args.w5, sheet_name="PAK_5Ws", engine="openpyxl",
                      nrows=5000)
    c_prov = next(c for c in w.columns if str(c).strip().upper() == "PROVINCE")
    c_dist = next(c for c in w.columns if str(c).strip().upper() == "DISTRICT")
    c_ben = next(c for c in w.columns if "TOTAL NUMBER OF BENEFICIARIES" in str(c))
    c_sec = next(c for c in w.columns if str(c).strip().upper() == "SECTOR")
    w[[c_prov, c_dist, c_sec, c_ben]].head(12).to_csv(
        os.path.join(args.outdir, "raw_samples", "raw_sample_5w.csv"),
        index=False)

    log["outputs"] = {
        "districts_flood": len(flood),
        "districts_relief": len(relief),
        "districts_joined": len(gap),
        "total_exposed_pop": int(gap["exposed_pop"].sum()),
        "total_beneficiaries": int(gap["beneficiaries_reached"].sum()),
    }
    with open(os.path.join(args.outdir, "cleaning_log.json"), "w") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)

    print("\n==== SUMMARY ====")
    print(f"districts (flood): {len(flood)} | districts (relief): "
          f"{len(relief)} | joined: {len(gap)}")
    print(f"total exposed pop: {log['outputs']['total_exposed_pop']:,}")
    print(f"total beneficiaries reached: "
          f"{log['outputs']['total_beneficiaries']:,}")
    print("cleaning log written to cleaning_log.json")


if __name__ == "__main__":
    main()
