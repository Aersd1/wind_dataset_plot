"""Explicit units, clock convention and reproducible analysis settings."""
from pathlib import Path
import copy
import json

DEFAULTS = {
    "data_dir": "data", "metadata_dir": "metadata", "output_dir": "results",
    "csv_glob": "**/*.csv", "segments_only": True, "palette": "plasma",
    "source_dataset_map": {}, "datasets": {},
    "inputs": {"segments_manifest": None, "capacity_table": None,
               "original_manifest": None, "segment_layer": "aligned_segments",
               "path_prefix_map": {}},
    "defaults": {
        "time_column": None, "value_column": None, "value_unit": None,
        "rated_capacity_kw": None, "timezone": "UTC", "timestamp_format": None,
        "timestamp_unit": None, "timestamp_position": "start",
        "interval_minutes": None, "csv_separator": ",",
    },
    "analysis": {
        "clock_timezone": "UTC", "low_cf": 0.05, "high_cf": 0.8,
        "min_stl_cycles": 3, "stl_window_hours": 1344,
        "max_stl_windows": 0, "max_daily_profiles_per_dataset": 0,
        "clusters": "auto", "max_clusters": 12, "cluster_fit_limit": 5000,
        "silhouette_limit": 1500, "seed": 20260921,
    },
    "plots": {"layout": "clear", "panels": ["a", "b", "c", "d", "e", "f"],
              "formats": ["png", "pdf", "svg"], "dpi": 300,
              "rows_per_page": 45, "combined": True, "structure_comparison": True},  # rows_per_page: legacy
}


def load_config(path):
    path = Path(path).resolve()
    supplied = json.loads(path.read_text(encoding="utf-8-sig"))
    cfg = copy.deepcopy(DEFAULTS)
    for key, value in supplied.items():
        if key not in cfg:
            raise ValueError(f"Unknown config key: {key}")
        if key in ("defaults", "analysis", "plots", "inputs"):
            unknown = set(value) - set(cfg[key])
            if unknown:
                raise ValueError(f"Unknown {key} keys: {sorted(unknown)}")
            cfg[key].update(value)
        else:
            cfg[key] = value
    for key in ("data_dir", "metadata_dir", "output_dir"):
        p = Path(cfg[key]).expanduser()
        cfg[key] = str((path.parent / p).resolve() if not p.is_absolute() else p.resolve())
    for opts in cfg["datasets"].values():
        allowed = set(cfg["defaults"]) | {"metadata_file", "metadata_id", "site_type", "label"}
        if set(opts) - allowed:
            raise ValueError(f"Unknown dataset options: {set(opts)-allowed}")
        if opts.get("metadata_file"):
            p = Path(opts["metadata_file"]).expanduser()
            opts["metadata_file"] = str((path.parent / p).resolve() if not p.is_absolute() else p)
    for key in ("segments_manifest", "capacity_table", "original_manifest"):
        if cfg["inputs"][key]:
            p = Path(cfg["inputs"][key]).expanduser()
            cfg["inputs"][key] = str((path.parent / p).resolve() if not p.is_absolute() else p)
    if cfg["inputs"]["segment_layer"] not in ("prefer_data_process", "data_process", "aligned_segments"):
        raise ValueError("segment_layer must be prefer_data_process, data_process or aligned_segments")
    if cfg["inputs"]["segments_manifest"] and not cfg["inputs"]["capacity_table"]:
        raise ValueError("Manifest input requires capacity_table")
    if cfg["palette"] not in ("viridis", "plasma"):
        raise ValueError("palette must be viridis or plasma")
    a, p = cfg["analysis"], cfg["plots"]
    if p["layout"] not in ("clear", "legacy"):
        raise ValueError("plots.layout must be clear or legacy")
    if not isinstance(p["structure_comparison"],bool):
        raise ValueError("plots.structure_comparison must be true or false")
    if not 0 <= a["low_cf"] < a["high_cf"] <= 1:
        raise ValueError("Require 0 <= low_cf < high_cf <= 1")
    for key in ("max_stl_windows", "max_daily_profiles_per_dataset"):
        if not isinstance(a[key], int) or a[key] < 0:
            raise ValueError(f"{key} must be a nonnegative integer; 0 means all")
    if a["min_stl_cycles"] < 2 or a["stl_window_hours"] < 168*a["min_stl_cycles"]:
        raise ValueError("STL window must contain at least min_stl_cycles weekly cycles (>=2)")
    if a["clusters"] != "auto" and (not isinstance(a["clusters"], int) or a["clusters"] < 1):
        raise ValueError("clusters must be 'auto' or a positive integer")
    if min(a["cluster_fit_limit"], a["silhouette_limit"]) < 3 or a["max_clusters"] < 2:
        raise ValueError("Clustering sample limits must be >=3; max_clusters >=2")
    if not p["panels"] or set(p["panels"]) - set("abcdef"):
        raise ValueError("panels must be a nonempty selection from a,b,c,d,e,f")
    if not p["formats"] or set(p["formats"]) - {"png", "pdf", "svg"}:
        raise ValueError("formats must select png, pdf and/or svg")
    if p["rows_per_page"] < 1 or p["dpi"] < 72:
        raise ValueError("rows_per_page >=1 and dpi >=72 required")
    cfg["config_file"] = str(path)
    return cfg
