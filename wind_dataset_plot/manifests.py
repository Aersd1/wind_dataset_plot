"""Farm-level joins for the supplied capacity table and long/wide segment manifests.

Never combine processing layers. File names and # source comments are not farm IDs
in this mode: the manifest's exact name/source join is authoritative.
"""
from pathlib import Path
import logging
import numpy as np
import pandas as pd

LOG = logging.getLogger(__name__)


def table(path, required):
    frame = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    missing = set(required) - set(frame.columns)
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")
    for col in required:
        if frame[col].str.strip().eq("").any():
            raise ValueError(f"{path}: empty {col}")
    return frame


def farm_keys(frame, label, unique=False):
    if frame.groupby("name").source.nunique().gt(1).any():
        raise ValueError(f"{label}: same farm name in multiple sources; disambiguate names first")
    if unique and frame.duplicated(["name", "source"]).any():
        raise ValueError(f"{label}: duplicate farm rows")
    return set(zip(frame.name, frame.source))


def mapped_path(value, manifest, mapping):
    value = value.replace("\\", "/")
    for old, new in sorted(mapping.items(), key=lambda item: -len(item[0])):
        old = old.replace("\\", "/").rstrip("/")
        if value == old or value.startswith(old + "/"):
            value = str(new).replace("\\", "/").rstrip("/") + value[len(old):]
            break
    path = Path(value).expanduser()
    return path if path.is_absolute() else Path(manifest).parent / path


def read_plan(cfg):
    """Validate only index tables; never open/stat raw CSVs or JSONs."""
    opts = cfg["inputs"]
    manifest = opts["segments_manifest"]
    if not manifest:
        raise ValueError("--inspect-manifests requires inputs.segments_manifest")
    raw = table(manifest, ["name", "source"])
    if "segment_csv_path" in raw:
        required = {"layer", "segment_csv_path"}
        if not required <= set(raw):
            raise ValueError("Long manifest needs layer and segment_csv_path")
        segments = raw[["name", "source", "layer", "segment_csv_path"]].copy()
    else:
        rows = []
        for row in raw.to_dict("records"):
            for layer, col, count in (("aligned_segments", "aligned_segment_paths", "n_aligned_segments"),
                                      ("data_process", "data_process_segment_paths", "n_data_process_segments")):
                if col not in row:
                    raise ValueError(f"Wide manifest needs {col}")
                paths = [p.strip() for p in row[col].split("|") if p.strip()]
                if count in row and int(row[count]) != len(paths):
                    raise ValueError(f"{row['name']}: {count} disagrees with path list")
                rows.extend(dict(name=row["name"], source=row["source"], layer=layer,
                                 segment_csv_path=p) for p in paths)
        farm_keys(raw, "wide manifest", unique=True)
        segments = pd.DataFrame(rows, columns=["name", "source", "layer", "segment_csv_path"])
    keys = farm_keys(segments, "segments")
    if not keys or segments.segment_csv_path.str.strip().eq("").any():
        raise ValueError("Segment manifest is empty or has empty paths")
    if set(segments.layer) - {"aligned_segments", "data_process"}:
        raise ValueError("Unknown processing layer in segment manifest")
    if segments.duplicated(["name", "source", "layer", "segment_csv_path"]).any():
        raise ValueError("Duplicate path rows in segment manifest")
    if segments.groupby("segment_csv_path").name.nunique().gt(1).any():
        raise ValueError("Same segment path assigned to multiple farms")
    capacities = table(opts["capacity_table"], ["name", "source", "rated_power_kW_used",
                                              "power_unit_original_csv", "rated_capacity_source"])
    cap_keys = farm_keys(capacities, "capacity table", unique=True)
    if keys - cap_keys:
        raise ValueError(f"Missing farm capacity rows: {sorted(keys-cap_keys)}")
    originals = {}
    if opts["original_manifest"]:
        frame = table(opts["original_manifest"], ["name", "source", "original_csv_path"])
        orig_keys = farm_keys(frame, "original manifest", unique=True)
        if keys - orig_keys:
            raise ValueError(f"Missing original provenance rows: {sorted(keys-orig_keys)}")
        originals = {(r["name"], r["source"]): r["original_csv_path"] for r in frame.to_dict("records")}
    cap_index = {(r["name"], r["source"]): r for r in capacities.to_dict("records")}
    farms, excluded = [], []
    for (name, source), group in segments.groupby(["name", "source"], sort=True):
        available = set(group.layer)
        layer = opts["segment_layer"]
        if layer == "prefer_data_process":
            layer = "data_process" if "data_process" in available else "aligned_segments"
        chosen = group[group.layer.eq(layer)]
        if chosen.empty:
            excluded.append(name)
            continue
        cap = cap_index[(name, source)]
        kw = float(cap["rated_power_kW_used"])
        if not np.isfinite(kw) or kw <= 0:
            raise ValueError(f"{name}: capacity must be finite and positive")
        if cap.get("rated_power_MW_used") and not np.isclose(kw, float(cap["rated_power_MW_used"])*1000, rtol=1e-6):
            raise ValueError(f"{name}: capacity kW/MW columns disagree")
        if cap["power_unit_original_csv"].strip().lower() != "mw":
            raise ValueError(f"{name}: expected instantaneous MW power in capacity table")
        proxy = "power_max" in cap["rated_capacity_source"].lower()
        paths = [mapped_path(p, manifest, opts["path_prefix_map"]) for p in chosen.segment_csv_path]
        if len(set(paths)) != len(paths):
            raise ValueError(f"{name}: path mapping collapses distinct segments")
        farms.append({"id": name, "source": source, "layer": layer, "files": paths,
                      "capacity_kw": kw, "capacity_source": cap["rated_capacity_source"],
                      "capacity_is_proxy": proxy, "capacity_table_site_type": cap.get("onshore_offshore", "").lower(),
                      "original_csv_path": originals.get((name, source)),
                      "fallback_to_aligned": opts["segment_layer"] == "prefer_data_process" and layer == "aligned_segments"})
    if not farms:
        raise ValueError("No farms have the selected processing layer")
    all_paths = [p for f in farms for p in f["files"]]
    if len(set(all_paths)) != len(all_paths):
        raise ValueError("Mapped paths overlap across farms")
    return farms, {"manifest_farms": len(keys), "manifest_rows": len(segments),
                   "selected_farms": len(farms), "selected_segments": len(all_paths),
                   "selected_layer": opts["segment_layer"], "excluded_farms": excluded,
                   "aligned_fallback_farms": [f["id"] for f in farms if f["fallback_to_aligned"]],
                   "capacity_proxy_farms": [f["id"] for f in farms if f["capacity_is_proxy"]]}


def discover_manifest(cfg):
    from .io import Dataset
    farms, report = read_plan(cfg)
    unknown = set(cfg["datasets"]) - {f["id"] for f in farms}
    if unknown:
        raise ValueError(f"Configured dataset IDs not selected: {sorted(unknown)}")
    result = []
    for farm in farms:
        options = {**cfg["defaults"], **cfg["datasets"].get(farm["id"], {})}
        # This adapter targets the supplied MW instantaneous-power corpus explicitly.
        for key, expected in (("value_unit", "MW"), ("value_column", "power")):
            if options.get(key) is not None and options[key] != expected:
                raise ValueError(f"{farm['id']}: manifest mode requires {key}={expected}")
            options[key] = expected
        if options.get("rated_capacity_kw") is not None:
            raise ValueError("Manifest mode uses capacity table; update that table instead of a capacity override")
        if options["timestamp_position"] == "end":
            raise ValueError("Instantaneous MW observations must not use timestamp_position=end")
        options["timestamp_position"] = "instantaneous"
        for path in farm["files"]:
            if not path.is_file():
                raise FileNotFoundError(f"{farm['id']}: missing selected segment {path}; check server mount/path_prefix_map")
        provenance = {k: v for k, v in farm.items() if k not in ("files", "id")}
        ds = Dataset(farm["id"], files=farm["files"], options=options, provenance=provenance)
        if farm["original_csv_path"]:
            ds.sources.add(farm["original_csv_path"])
        result.append(ds)
    cfg["input_report"] = report
    if report["aligned_fallback_farms"]:
        LOG.warning("%s farms fall back to aligned_segments; inspect input_report in run_manifest", len(report["aligned_fallback_farms"]))
    if report["capacity_proxy_farms"]:
        LOG.warning("Observed-maximum capacity proxies supplied for: %s", ", ".join(report["capacity_proxy_farms"]))
    return result, report["excluded_farms"]
