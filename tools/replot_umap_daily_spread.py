"""Redraw the farm-profile heatmap, the climate daily panels, and a 12-farm daily figure.

Uses the capacity-rescaled tables in publication_results/server_run_maxcap.
Figure 5 places one point per farm by principal components of the mean daily profile. Climate bands use each farm's own
day-to-day interquartile range, then the median of those ranges across farms.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd

from wind_dataset_plot.publication import climate_profiles
from wind_dataset_plot.publication_plotting import climate_profile_similarity, daily_panels, farm_daily_panels

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "publication_results" / "server_run_maxcap"
TABLES = OUT / "tables"

# Two from each climate would be ten farms. These twelve keep every climate,
# mix offshore and onshore, and span low to high mean capacity factor.
# NREL labels are the place token already stored in the dataset id.
SELECTION = [
    {"dataset_id": "NREL_WTK_site114665_Offshore-LakeHuron_offshore_16MW_2007-2013", "label": "Lake Huron"},
    {"dataset_id": "NREL_WTK_site39992_Virginia-Roanoke_class2_14MW_2007-2013", "label": "Roanoke"},
    {"dataset_id": "NREL_WTK_site48998_WestVirginia-Randolph_class3_10MW_2007-2013", "label": "Randolph"},
    {"dataset_id": "SNOWSTH1", "label": "SNOWSTH1"},
    {"dataset_id": "NREL_WTK_site80793_Wyoming-Fremont_class2_16MW_2007-2013", "label": "Fremont"},
    {"dataset_id": "NREL_WTK_site3044_Offshore-Gulf-LA_offshore_16MW_2007-2013", "label": "Gulf LA"},
    {"dataset_id": "NREL_WTK_site16069_Oklahoma-Comanche_class1_2MW_2007-2013", "label": "Comanche"},
    {"dataset_id": "LARYO-1", "label": "LARYO-1"},
    {"dataset_id": "BALDHWF1", "label": "BALDHWF1"},
    {"dataset_id": "BRBEO-1", "label": "BRBEO-1"},
    {"dataset_id": "UP_BDDSLDSRDI_1", "label": "UP_BDDSLDSRDI_1"},
    {"dataset_id": "WATERLWF", "label": "WATERLWF"},
]


def load_result():
    summary = pd.read_csv(TABLES / "farm_statistics.csv")
    daily = pd.read_csv(TABLES / "daily_profiles_index.csv")
    profiles = np.load(TABLES / "daily_profiles.npz")["profiles"]
    if len(daily) != len(profiles):
        raise ValueError("daily index and profile matrix differ")
    farm = pd.read_csv(TABLES / "farm_mean_daily_profile_percent.csv").set_index("dataset_id")
    farm = farm.reindex(summary.dataset_id)
    return {
        "summary": summary,
        "daily": daily,
        "profiles": profiles,
        "farm_hourly_profile": farm,
    }


def main():
    result = load_result()
    meta = result["summary"].set_index("dataset_id")
    missing = [item["dataset_id"] for item in SELECTION if item["dataset_id"] not in meta.index]
    if missing:
        raise SystemExit(f"Selected farms missing from the summary: {missing}")
    for item in SELECTION:
        row = meta.loc[item["dataset_id"]]
        item["climate_group"] = row.climate_group
        item["site_type"] = row.site_type
        item["n_complete_days"] = int(row.n_complete_days)
        item["cf_mean"] = float(row.cf_mean)
    result["climate_profiles"] = climate_profiles(result)
    figures = OUT / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    written = [
        climate_profile_similarity(result, figures / "05_farm_profile_similarity"),
        daily_panels(result, figures / "06_daily_power_panels", "climate"),
        farm_daily_panels(result, SELECTION, figures / "08_twelve_farm_daily_profiles"),
    ]
    result["climate_profiles"].to_csv(TABLES / "climate_daily_profiles.csv", index=False)
    pd.DataFrame(SELECTION).to_csv(TABLES / "twelve_farm_daily_selection.csv", index=False)
    note = {
        "figure_05": "PCA scatter, one point per farm mean daily profile; proximity is profile similarity",
        "climate_band": "Median across farms of each farm's day-level 25th and 75th percentile",
        "why_previous_band_was_narrow": "Previous band was the interquartile range of farm-mean profiles",
        "twelve_farm_figure": "Two rows of six; band is that farm's own day-level interquartile range",
        "figures": written,
    }
    (TABLES / "umap_daily_redraw.json").write_text(json.dumps(note, indent=2), encoding="utf-8")
    print("\n".join(written))


if __name__ == "__main__":
    main()
