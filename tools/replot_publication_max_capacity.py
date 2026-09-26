"""Redraw publication figures using saved farm statistics.

Farms whose power exceeded the equipment rated capacity use that farm's observed
maximum MW as the capacity denominator. Capacity-factor statistics and daily
profiles already computed with the rated capacity are rescaled by
rated / observed_maximum. STL strengths are unchanged because they are variance
ratios. The pooled hourly histogram was not saved, so it is recomputed from the
power CSVs with the updated denominators.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter1d

from wind_dataset_plot.analysis import hourly_runs
from wind_dataset_plot.config import load_config
from wind_dataset_plot.io import load_runs
from wind_dataset_plot.publication import climate_profiles
from wind_dataset_plot.publication_plotting import plot_publication
from wind_dataset_plot.revised import embed_profiles, prepare, size_group

ROOT = Path(__file__).resolve().parents[1]
PREV = ROOT / "publication_results" / "server_run"
OUT = ROOT / "publication_results" / "server_run_maxcap"
TABLES = PREV / "tables"
META = ROOT / "inputs" / "revised_metadata"
EPS = 1e-9
SCALE_COLUMNS = [
    "cf_p10", "cf_p25", "cf_median", "cf_p75", "cf_p90", "cf_mean", "cf_iqr",
    "ramp_p95", "ramp_mean", "mean_hourly_change_pp", "large_hourly_change_pp",
] + [f"month_{m:02}_mean_cf" for m in range(1, 13)]


def substitution_table():
    query = pd.read_csv(TABLES / "server_capacity_query.csv")
    over = query.loc[query.raw_above_rated > 0, ["dataset_id", "rated_capacity_mw", "observed_max_mw"]].copy()
    over["scale"] = over.rated_capacity_mw / over.observed_max_mw
    over["capacity_rule"] = "observed_maximum_because_power_exceeded_rated"
    return over.set_index("dataset_id")


def scaled_summary(factors):
    summary = pd.read_csv(TABLES / "farm_statistics.csv")
    summary["equipment_rated_capacity_mw"] = summary.rated_capacity_mw
    for farm, row in factors.iterrows():
        mask = summary.dataset_id.eq(farm)
        summary.loc[mask, SCALE_COLUMNS] = summary.loc[mask, SCALE_COLUMNS] * row.scale
        summary.loc[mask, "rated_capacity_mw"] = row.observed_max_mw
        summary.loc[mask, "capacity_kw"] = row.observed_max_mw * 1000
        summary.loc[mask, "capacity_source"] = summary.loc[mask, "capacity_source"].astype(str) + "|" + row.capacity_rule
        summary.loc[mask, "capacity_is_proxy"] = True
    summary["capacity_group"] = summary.rated_capacity_mw.map(size_group)
    return summary


def scaled_profiles(summary, factors):
    daily = pd.read_csv(TABLES / "daily_profiles_index.csv")
    profiles = np.load(TABLES / "daily_profiles.npz")["profiles"].astype(float)
    if len(daily) != len(profiles):
        raise ValueError("daily index and profile matrix differ")
    scale = daily.dataset_id.map(factors.scale).fillna(1.0).to_numpy(float)
    profiles = profiles * scale[:, None]
    daily["mean_cf"] = profiles.mean(axis=1)
    daily["mean_abs_hourly_ramp"] = np.abs(np.diff(profiles, axis=1)).mean(axis=1)
    daily["rated_capacity_mw"] = daily.dataset_id.map(summary.set_index("dataset_id").rated_capacity_mw)
    hourly = pd.DataFrame(profiles, columns=[f"hour_{h:02}" for h in range(24)])
    hourly.insert(0, "dataset_id", daily.dataset_id.to_numpy())
    farm = hourly.groupby("dataset_id", sort=False).mean().reindex(summary.dataset_id) * 100
    farm.index.name = "dataset_id"
    return daily, profiles, farm


def pooled_histogram(cfg):
    datasets, _ = prepare(cfg)
    edges = np.linspace(0.0, 1.0, 2001)
    counts = np.zeros(2000, dtype=np.int64)
    n = 0
    total = 0.0
    squared = 0.0
    below = 0
    for i, ds in enumerate(datasets, 1):
        print(f"[{i}/{len(datasets)}] histogram {ds.id}", flush=True)
        raw, step, _, _ = load_runs(ds)
        hourly = hourly_runs(raw, step)
        if not hourly:
            continue
        values = np.concatenate([s.to_numpy(dtype=float) for s in hourly])
        values = values[np.isfinite(values)]
        low = values < -EPS
        below += int(low.sum())
        kept = values[~low].copy()
        kept[(kept < 0) & (kept >= -EPS)] = 0
        kept[(kept > 1) & (kept <= 1 + EPS)] = 1
        if np.any(kept > 1 + EPS):
            raise ValueError(f"{ds.id} still exceeds the capacity denominator after the observed-maximum substitution")
        counts += np.histogram(kept, bins=edges)[0]
        n += len(kept)
        total += float(kept.sum())
        squared += float(np.square(kept).sum())
    if counts.sum() != n:
        raise ValueError("Pooled counts do not cover the in-range complete hours")
    mean = total / n
    variance = max(0.0, (squared - total ** 2 / n) / max(1, n - 1))
    dx = edges[1] - edges[0]
    bandwidth = max(np.sqrt(variance) * n ** (-0.2), dx)
    density = gaussian_filter1d(counts.astype(float), bandwidth / dx, mode="reflect") / (n * dx)
    table = pd.DataFrame({"cf": (edges[:-1] + edges[1:]) / 2, "count": counts, "density": density})
    stats = {
        "complete_hour_count": n,
        "hours_below_zero_excluded": below,
        "pooled_mean_cf": mean,
        "bandwidth_cf": bandwidth,
        "density_method": "In-range complete hours on 2000 bins; Gaussian smoothing with Scott bandwidth",
    }
    return table, stats


def write_capacity_inputs(factors):
    folder = OUT / "inputs"
    folder.mkdir(parents=True, exist_ok=True)
    capacity = pd.read_csv(META / "farm_capacity_units_131_updated.csv")
    meta = pd.read_csv(META / "farm_numeric_metadata.csv")
    for farm, row in factors.iterrows():
        capacity.loc[capacity.name.eq(farm), ["rated_power_kW_used", "rated_power_MW_used"]] = [
            row.observed_max_mw * 1000, row.observed_max_mw]
        meta.loc[meta.dataset_id.eq(farm), "rated_capacity_mw"] = row.observed_max_mw
        meta.loc[meta.dataset_id.eq(farm), "capacity_group"] = size_group(row.observed_max_mw)
    capacity.to_csv(folder / "farm_capacity_units_131_updated.csv", index=False)
    meta.to_csv(folder / "farm_numeric_metadata.csv", index=False)
    cfg = json.loads((ROOT / "publication_config.json").read_text())
    cfg["data_dir"] = str(Path(cfg["data_dir"]).resolve())
    cfg["metadata_dir"] = str(META)
    cfg["output_dir"] = str(OUT)
    cfg["inputs"]["capacity_table"] = str(folder / "farm_capacity_units_131_updated.csv")
    cfg["inputs"]["segments_manifest"] = str(META / "farm_paths_segmented_long_131.csv")
    cfg["inputs"]["original_manifest"] = str(META / "farm_paths_original_131.csv")
    (folder / "publication_config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return folder / "publication_config.json", meta


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    factors = substitution_table()
    factors.to_csv(OUT / "observed_maximum_capacity.csv")
    config_path, meta = write_capacity_inputs(factors)
    summary = scaled_summary(factors)
    daily, profiles, farm = scaled_profiles(summary, factors)
    result = {
        "summary": summary,
        "daily": daily,
        "profiles": profiles,
        "farm_hourly_profile": farm,
    }
    result["climate_profiles"] = climate_profiles(result)
    print(f"UMAP on {len(profiles)} daily profiles", flush=True)
    # Installed scikit-learn 1.5 still uses force_all_finite; umap 0.5.9 passes ensure_all_finite.
    import sklearn.utils.validation as validation
    import umap.umap_ as umap_module
    original = validation.check_array
    def check_array(*args, **kwargs):
        if "ensure_all_finite" in kwargs and "force_all_finite" not in kwargs:
            kwargs["force_all_finite"] = kwargs.pop("ensure_all_finite")
        else:
            kwargs.pop("ensure_all_finite", None)
        return original(*args, **kwargs)
    validation.check_array = check_array
    umap_module.check_array = check_array
    result = embed_profiles(result, 20260924)
    cfg = load_config(config_path)
    density, pooled = pooled_histogram(cfg)
    result["pooled_density"] = density
    result["pooled_mean"] = pooled["pooled_mean_cf"]
    tables = OUT / "tables"
    tables.mkdir(exist_ok=True)
    summary.to_csv(tables / "farm_statistics.csv", index=False)
    daily.to_csv(tables / "daily_profiles_index.csv", index=False)
    np.savez_compressed(tables / "daily_profiles.npz", profiles=profiles)
    farm.to_csv(tables / "farm_mean_daily_profile_percent.csv")
    result["climate_profiles"].to_csv(tables / "climate_daily_profiles.csv", index=False)
    density.to_csv(tables / "pooled_capacity_factor_density.csv", index=False)
    equipment = pd.read_csv(META / "turbine_groups_long.csv")
    figures = plot_publication(result, meta, equipment, OUT, "climate")
    manifest = {
        "status": "complete",
        "capacity_rule": "Farms with power above equipment rated capacity use observed maximum MW",
        "substituted_farms": factors.reset_index().to_dict(orient="records"),
        "pooled": pooled,
        "figures": figures,
        "reused_tables": str(TABLES),
        "stl": "Reused; seasonal strength is invariant to rescaling the capacity denominator",
        "volatility_figure": "Scatter points only; median and interquartile marks are not drawn",
    }
    (OUT / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote {len(figures)} figures to {OUT / 'figures'}")


if __name__ == "__main__":
    main()
