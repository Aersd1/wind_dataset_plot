"""Generate GASF images from retained power segments and explore them without labels."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_mutual_info_score, silhouette_score

from wind_dataset_plot.config import load_config
from wind_dataset_plot.io import Dataset, load_runs
from wind_dataset_plot.manifests import read_plan
from wind_dataset_plot.publication import climate_metadata


def gasf(cf: np.ndarray, scale: str = "fixed") -> np.ndarray:
    """GASF = cos(phi_i + phi_j), phi = arccos(x), x in [-1, 1]."""
    values = np.asarray(cf, dtype=np.float64)
    if values.ndim != 1 or not np.isfinite(values).all() or np.any((values < -1e-9) | (values > 1 + 1e-9)):
        raise ValueError("GASF input must be a finite capacity-factor vector within [0, 1]")
    values = np.clip(values, 0, 1)
    if scale == "fixed":
        x = 2 * values - 1
    elif scale == "shape":
        lo, hi = values.min(), values.max()
        x = np.zeros_like(values) if hi == lo else 2 * (values - lo) / (hi - lo) - 1
    else:
        raise ValueError(f"Unknown scale: {scale}")
    sine = np.sqrt(np.maximum(0, 1 - x * x))
    return np.outer(x, x) - np.outer(sine, sine)


def candidate_windows(runs, length: int, stride: int):
    """Window starts stay inside one finite, constant-cadence source run."""
    candidates = []
    for run_index, run in enumerate(runs):
        if len(run) < length:
            continue
        values = run.to_numpy()
        bad = ((values < -1e-9) | (values > 1 + 1e-9)).astype(np.int64)
        prefix = np.concatenate(([0], np.cumsum(bad)))
        starts = np.arange(0, len(run) - length + 1, stride)
        candidates.extend((run_index, int(start)) for start in starts
                          if prefix[start + length] == prefix[start])
    return candidates


def spread_indices(size: int, limit: int) -> np.ndarray:
    if size <= limit:
        return np.arange(size)
    return np.unique(np.rint(np.linspace(0, size - 1, limit)).astype(int))


def matrix_features(image: np.ndarray) -> np.ndarray:
    """224 x 224 -> 32 x 32 area means; same transform for every image."""
    if image.shape != (224, 224):
        raise ValueError("Expected a 224 x 224 GASF image")
    return image.reshape(32, 7, 32, 7).mean(axis=(1, 3)).ravel()


def make_dataset(farm: dict, defaults: dict) -> Dataset:
    opts = {**defaults, "value_column": "power", "value_unit": "MW", "timestamp_position": "instantaneous"}
    return Dataset(farm["id"], files=farm["files"], options=opts, capacity_kw=farm["capacity_kw"])


def describe_clusters(table: pd.DataFrame, out: Path) -> dict:
    summary = {}
    for field in ("climate_group", "source", "site_type"):
        cross = pd.crosstab(table["cluster"], table[field])
        cross.to_csv(out / f"cluster_by_{field}.csv")
        summary[field] = float(adjusted_mutual_info_score(table["cluster"], table[field]))
    same_source = table[table.source.eq("nrel_wtk")]
    if same_source.climate_group.nunique() > 1 and same_source.cluster.nunique() > 1:
        summary["climate_within_nrel_wtk"] = float(adjusted_mutual_info_score(
            same_source.cluster, same_source.climate_group))
    table.groupby(["dataset_id", "climate_group", "source", "site_type", "cluster"], observed=True).size().rename("windows").reset_index().to_csv(
        out / "farm_cluster_counts.csv", index=False)
    return summary


def plot_embedding(table: pd.DataFrame, out: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5), constrained_layout=True)
    for ax, field in zip(axes, ("climate_group", "source", "cluster")):
        for label, frame in table.groupby(field, sort=True):
            ax.scatter(frame.pc1, frame.pc2, s=15, alpha=.65, label=str(label))
        ax.set(xlabel="GASF PC1", ylabel="GASF PC2", title=field.replace("_", " "))
        ax.legend(fontsize=7, frameon=False, markerscale=1.5)
    fig.savefig(out / "gaf_embedding.png", dpi=220)
    fig.savefig(out / "gaf_embedding.pdf")
    plt.close(fig)


def plot_examples(examples: list, out: Path) -> None:
    fig, axes = plt.subplots(len(examples), 3, figsize=(11, 2.1 * len(examples)),
                             constrained_layout=True, squeeze=False)
    for row, (farm_id, climate, cf) in enumerate(examples):
        axes[row, 0].plot(np.arange(224), cf, color="#245f86", lw=1)
        axes[row, 0].set_ylim(-.03, 1.03)
        axes[row, 0].set_ylabel(f"{farm_id}\n{climate}", fontsize=7)
        for col, scale in ((1, "fixed"), (2, "shape")):
            axes[row, col].imshow(gasf(cf, scale), cmap="gray", vmin=-1, vmax=1,
                                  interpolation="nearest", origin="lower")
            axes[row, col].set_xticks([])
            axes[row, col].set_yticks([])
    for ax, title in zip(axes[0], ("Capacity factor, 224 points", "GASF, fixed scale", "GASF, shape scale")):
        ax.set_title(title)
    axes[-1, 0].set_xlabel("15-minute sample index")
    fig.savefig(out / "gaf_examples.png", dpi=170)
    fig.savefig(out / "gaf_examples.pdf")
    plt.close(fig)


def run(settings_path: Path, output: Path, inspect: bool = False) -> dict:
    settings_path = settings_path.resolve()
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    cfg = load_config(settings_path.parent / settings["publication_config"])
    if settings["window_points"] != 224:
        raise ValueError("This analysis requires exactly 224 points")
    stride, limit, clusters = (int(settings[k]) for k in ("stride_points", "max_windows_per_farm", "clusters"))
    if min(stride, limit) < 1 or clusters < 2:
        raise ValueError("stride, window limit and cluster count must be positive")
    farms, input_report = read_plan(cfg)
    selected = settings["farms"]
    if not selected or len(selected) != len(set(selected)):
        raise ValueError("Select distinct farm IDs")
    by_id = {farm["id"]: farm for farm in farms}
    missing = set(selected) - set(by_id)
    if missing:
        raise ValueError(f"Farm IDs absent from manifest: {sorted(missing)}")
    meta = climate_metadata(Path(cfg["metadata_dir"]) / "farm_numeric_metadata.csv",
                            Path(cfg["metadata_dir"]) / "climate_groups.csv", selected)
    if not np.allclose(meta.rated_capacity_mw, meta.dataset_id.map({f["id"]: f["capacity_kw"] / 1000 for f in farms})):
        raise ValueError("Capacity table and metadata disagree")
    report = {"status": "inspected" if inspect else "running", "selected_farms": selected,
              "manifest_layer": input_report["selected_layer"],
              "selected_climate_counts": meta.climate_group.value_counts().to_dict(),
              "raw_series_accessed": False}
    if inspect:
        return report
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"Output folder is not empty: {output}")
    images = output / "images"
    images.mkdir(parents=True)
    features = {"fixed": [], "shape": []}
    records, audits, examples = [], [], []
    metadata = meta.set_index("dataset_id")
    for farm_id in selected:
        farm = by_id[farm_id]
        ds = make_dataset(farm, cfg["defaults"])
        runs, step, audit, _ = load_runs(ds)
        if step != 15 * 60 * 10**9:
            raise ValueError(f"{farm_id}: expected 15-minute samples, found {step / 60e9:g} minutes")
        candidates = candidate_windows(runs, 224, stride)
        audits.append({**audit, "eligible_windows": len(candidates), "selected_windows": min(len(candidates), limit)})
        if not candidates:
            raise ValueError(f"{farm_id}: no valid 224-point windows")
        selected_indices = spread_indices(len(candidates), limit)
        for sample_number, index in enumerate(selected_indices):
            run_index, start = candidates[index]
            segment = runs[run_index].iloc[start:start + 224]
            cf = np.clip(segment.to_numpy(dtype=float), 0, 1)
            if sample_number == len(selected_indices) // 2:
                examples.append((farm_id, metadata.at[farm_id, "climate_group"], cf.copy()))
            identifier = hashlib.sha256(f"{farm_id}|{segment.index[0].isoformat()}".encode()).hexdigest()[:16]
            for scale in features:
                image = gasf(cf, scale)
                features[scale].append(matrix_features(image))
                path = images / scale / farm_id / f"{identifier}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                plt.imsave(path, image, vmin=-1, vmax=1, cmap="gray")
            records.append({"image_id": identifier, "dataset_id": farm_id,
                            "start_utc": segment.index[0].isoformat(), "end_utc": segment.index[-1].isoformat(),
                            "climate_group": metadata.at[farm_id, "climate_group"],
                            "climate_original": metadata.at[farm_id, "climate"],
                            "source": metadata.at[farm_id, "source"], "site_type": metadata.at[farm_id, "site_type"],
                            "rated_capacity_mw": metadata.at[farm_id, "rated_capacity_mw"],
                            "mean_cf": float(cf.mean()), "range_cf": float(np.ptp(cf))})
    table = pd.DataFrame(records)
    if len(table) <= clusters:
        raise ValueError("Need more windows than clusters")
    table.to_csv(output / "windows.csv", index=False)
    pd.DataFrame(audits).to_csv(output / "farm_audit.csv", index=False)
    plot_examples(examples, output)
    results = {}
    for scale, vectors in features.items():
        x = np.asarray(vectors)
        embedding = PCA(n_components=2, random_state=settings["seed"]).fit_transform(x)
        model = KMeans(n_clusters=clusters, random_state=settings["seed"], n_init=20)
        labels = model.fit_predict(x)
        frame = table.copy()
        frame["pc1"], frame["pc2"], frame["cluster"] = embedding[:, 0], embedding[:, 1], labels
        folder = output / scale
        folder.mkdir()
        frame.to_csv(folder / "embedding.csv", index=False)
        results[scale] = {"adjusted_mutual_information": describe_clusters(frame, folder),
                          "silhouette": float(silhouette_score(x, labels, sample_size=min(len(x), 1000),
                                                              random_state=settings["seed"])) if len(set(labels)) > 1 else None,
                          "pca_explained_variance": PCA(n_components=2).fit(x).explained_variance_ratio_.tolist()}
        plot_embedding(frame, folder)
    report.update(status="complete", raw_series_accessed=True, windows=len(table),
                  settings=settings, publication_config=str(settings_path.parent / settings["publication_config"]),
                  windows_per_farm=table.dataset_id.value_counts().to_dict(), analyses=results,
                  methods={"field": "GASF = cos(arccos(x_i) + arccos(x_j))",
                           "fixed_scale": "x = 2 * capacity_factor - 1",
                           "shape_scale": "per-window min-max; constant windows map to zero",
                           "feature": "32 x 32 block means of 224 x 224 GASF",
                           "clustering": "KMeans on the 1024-dimensional GASF features",
                           "embedding": "PCA for display only; clustering is not done in PCA space",
                           "sampling": "non-overlapping candidate windows spread across each farm's available runs"})
    (output / "run_manifest.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).with_name("results"))
    parser.add_argument("--inspect", action="store_true", help="Check manifests and climate metadata without raw series")
    args = parser.parse_args()
    print(json.dumps(run(args.config, args.output_dir.resolve(), args.inspect), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
