"""Read remover provenance, JSON metadata and retained raw CSV observations."""
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
import json
import re
import numpy as np
import pandas as pd


@dataclass
class Dataset:
    id: str
    files: list = field(default_factory=list)
    sources: set = field(default_factory=set)
    options: dict = field(default_factory=dict)
    metadata_files: list = field(default_factory=list)
    site_type: str = ""
    capacity_kw: float | None = None
    provenance: dict = field(default_factory=dict)


def read_header(path):
    header = {}
    with Path(path).open(encoding="utf-8-sig") as handle:
        for line in handle:
            if not line.startswith("#"):
                break
            key, sep, value = line[1:].partition(":")
            if sep:
                header[key.strip()] = value.strip()
    return header


def source_stem(source):
    return PurePosixPath(source.replace("\\", "/")).stem


def discover(cfg):
    if cfg.get("inputs", {}).get("segments_manifest"):
        from .manifests import discover_manifest
        return discover_manifest(cfg)
    root = Path(cfg["data_dir"])
    if not root.is_dir():
        raise ValueError(f"CSV directory does not exist: {root}")
    groups, ignored = {}, []
    for path in sorted(root.glob(cfg["csv_glob"])):
        if not path.is_file():
            continue
        header = read_header(path)
        source = header.get("source")
        parent = path.parent.name
        # Remove a numeric suffix only when the remover directory proves its meaning.
        parent_id = parent[:-4] if parent.endswith("_seq") else None
        parent_match = parent_id and re.fullmatch(re.escape(parent_id)+r"_\d+", path.stem)
        is_segment = bool(source) or bool(parent_match)
        if cfg["segments_only"] and not is_segment:
            ignored.append(str(path.relative_to(root)))
            continue
        identity = source_stem(source) if source else (parent_id if parent_match else path.stem)
        mapped = cfg["source_dataset_map"].get(path.relative_to(root).as_posix())
        mapped = mapped or cfg["source_dataset_map"].get(source or "")
        if mapped:
            identity = mapped
        ds = groups.setdefault(identity, Dataset(identity))
        # Distinct source paths with the same basename require an explicit mapping.
        if source:
            normalized = source.replace("\\", "/")
            if ds.sources and normalized not in ds.sources and not mapped:
                raise ValueError(f"Source basename collision for {identity}: use source_dataset_map")
            ds.sources.add(normalized)
        ds.files.append(path)
    if not groups:
        raise ValueError("No retained CSV segments found. Keep remover # source headers or *_seq folders.")
    if not cfg["segments_only"]:
        for ds in groups.values():
            flags = [bool(read_header(p).get("source")) or p.parent.name.endswith("_seq") for p in ds.files]
            if any(flags) and not all(flags):
                raise ValueError(f"{ds.id}: both original and cut CSVs found; use segments_only=true")
    unknown = set(cfg["datasets"]) - set(groups)
    if unknown:
        raise ValueError(f"Configured dataset IDs not discovered: {sorted(unknown)}")
    for ds in groups.values():
        ds.options = {**cfg["defaults"], **cfg["datasets"].get(ds.id, {})}
    return list(groups.values()), ignored


def walk_dict(obj):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield str(key), value
            if isinstance(value, dict):
                yield from walk_dict(value)


def canonical_key(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def metadata_fields(obj, site_only=False):
    pairs = list(walk_dict(obj))
    types = set()
    capacities = []
    units = set()
    for key, value in pairs:
        key = canonical_key(key)
        if key in ("sitetype", "farmtype", "onshoreoffshore", "offshoreonshore", "locationtype"):
            text = str(value).strip().lower()
            if text in ("onshore", "offshore"):
                types.add(text)
        if not site_only and key in ("ratedcapacitykw", "capacitykw", "installedcapacitykw",
                   "ratedcapacitymw", "capacitymw", "installedcapacitymw"):
            try:
                capacities.append(float(value) * (1000 if key.endswith("mw") else 1))
            except (ValueError, TypeError):
                raise ValueError(f"Invalid structured capacity {key}={value!r}")
        if not site_only and key in ("valueunit", "powerunit", "energyunit") and value:
            units.add(normalize_unit(str(value)))
    if not types:
        # Never search bare 'offshore' across environmental text.
        for key, value in pairs:
            if key in ("farm_description", "site_description") and isinstance(value, str):
                types.update(re.findall(r"\b(onshore|offshore)\s+wind\s+farm\b", value.lower()))
    if not capacities and not site_only:
        for key, value in pairs:
            if key in ("farm_description", "site_description") and isinstance(value, str):
                for number, unit in re.findall(
                    r"summing\s+to\s+(?:roughly\s+|approximately\s+)?([\d,.]+)\s*(MW|kW)\s+of\s+rated\s+capacity",
                    value, flags=re.I):
                    capacities.append(float(number.replace(",", ""))*(1000 if unit.lower()=="mw" else 1))
    if len(types) > 1:
        raise ValueError("Conflicting offshore/onshore metadata")
    if capacities and (not np.isfinite(capacities).all() or min(capacities) <= 0
                       or not np.allclose(capacities, capacities[0], rtol=1e-6)):
        raise ValueError("Conflicting or invalid rated capacities in metadata")
    if len(units) > 1:
        raise ValueError("Conflicting structured value units")
    return {"site_type": next(iter(types), None), "capacity_kw": capacities[0] if capacities else None,
            "value_unit": next(iter(units), None)}


def normalize_unit(unit):
    aliases = {"kw": "kW", "mw": "MW", "w": "W", "kwh": "kWh", "mwh": "MWh",
               "wh": "Wh", "cf": "capacity_factor", "capacity_factor": "capacity_factor"}
    if str(unit).strip().lower() not in aliases:
        raise ValueError(f"Unsupported or missing value_unit: {unit!r}; specify raw power/interval energy units")
    return aliases[str(unit).strip().lower()]


def resolve_metadata(datasets, cfg):
    paths = sorted(Path(cfg["metadata_dir"]).rglob("*.json"))
    for ds in datasets:
        opts = ds.options
        expected = opts.get("metadata_id", ds.id)
        if opts.get("metadata_file"):
            candidates = [Path(opts["metadata_file"])]
        else:
            candidates = [p for p in paths if p.stem == expected or
                          re.fullmatch(re.escape(expected)+r"_\d+", p.stem)]
        if not candidates:
            raise ValueError(f"{ds.id}: no matching JSON. Set datasets.{ds.id}.metadata_file or metadata_id")
        combined = {}
        for path in candidates:
            obj = json.loads(path.read_text(encoding="utf-8-sig"))
            declared = obj.get("dataset_id") or obj.get("dataset_name") or obj.get("description", {}).get("dataset_name")
            if declared and declared != expected:
                raise ValueError(f"{path}: JSON dataset name {declared!r} != {expected!r}; set metadata_id explicitly")
            fields = metadata_fields(obj, site_only=bool(ds.provenance))
            for key, value in fields.items():
                if value is not None and key in combined and combined[key] != value:
                    raise ValueError(f"{ds.id}: conflicting {key} across JSON files")
                if value is not None:
                    combined[key] = value
        ds.metadata_files = candidates
        ds.site_type = opts.get("site_type") or combined.get("site_type")
        if ds.site_type not in ("onshore", "offshore"):
            raise ValueError(f"{ds.id}: JSON needs site_type onshore/offshore, or set an explicit override")
        ds.capacity_kw = opts.get("rated_capacity_kw") if opts.get("rated_capacity_kw") is not None else combined.get("capacity_kw")
        if ds.provenance:
            ds.capacity_kw = ds.provenance["capacity_kw"]
            table_site = ds.provenance["capacity_table_site_type"]
            if table_site and table_site != ds.site_type:
                raise ValueError(f"{ds.id}: JSON site type disagrees with capacity table")
        opts["value_unit"] = normalize_unit(opts.get("value_unit") or combined.get("value_unit"))
        if ds.capacity_kw is not None and (not np.isfinite(ds.capacity_kw) or ds.capacity_kw <= 0):
            raise ValueError(f"{ds.id}: rated capacity must be positive")
        if opts["value_unit"] != "capacity_factor" and ds.capacity_kw is None:
            raise ValueError(f"{ds.id}: rated capacity is required; never use observed maximum as capacity")
        if opts["timestamp_position"] not in ("start", "end", "instantaneous"):
            raise ValueError("timestamp_position must be start, end or instantaneous")
    return datasets


TIME_ALIASES = {"timestamp", "datetime", "date", "time", "ds", "日期", "时间", "index"}
VALUE_ALIASES = {"power", "active_power", "power_kw", "power_mw", "value", "y", "target",
                 "production", "generation", "energy", "kwh", "功率", "发电量", "capacity_factor"}


def select_column(columns, explicit, aliases, label):
    if explicit is not None:
        if explicit not in columns:
            raise ValueError(f"Missing {label} column {explicit!r}; available {list(columns)}")
        return explicit
    matched = [c for c in columns if str(c).strip().lower() in aliases]
    if len(matched) != 1:
        raise ValueError(f"Cannot unambiguously detect {label}: {matched}; set {label}_column")
    return matched[0]


def csv_columns(path, opts):
    frame = pd.read_csv(path, comment="#", sep=opts["csv_separator"], encoding="utf-8-sig", nrows=0)
    return (select_column(frame.columns, opts["time_column"], TIME_ALIASES, "time"),
            select_column(frame.columns, opts["value_column"], VALUE_ALIASES, "value"))


def parse_time(values, opts):
    if pd.api.types.is_numeric_dtype(values):
        if not opts.get("timestamp_unit"):
            raise ValueError("Numeric timestamps need timestamp_unit (s/ms/us/ns); row indices are not timestamps")
        dates = pd.to_datetime(values, unit=opts["timestamp_unit"], utc=True, errors="raise")
    else:
        if not opts.get("timestamp_format"):
            ambiguous = values.astype(str).str.match(r"^\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}(?:\s|$)")
            if ambiguous.any():
                raise ValueError("Ambiguous date order: specify timestamp_format, e.g. %y/%m/%d %H:%M")
        dates = pd.to_datetime(values, format=opts.get("timestamp_format") or "ISO8601", errors="raise")
        dates = pd.DatetimeIndex(dates)
        if dates.tz is None:
            dates = dates.tz_localize(opts["timezone"], ambiguous="raise", nonexistent="raise")
    return pd.DatetimeIndex(dates).tz_convert("UTC").as_unit("ns")


def to_cf(values, unit, capacity_kw, interval_minutes):
    unit = normalize_unit(unit)
    values = np.asarray(values, dtype=float)
    if unit == "capacity_factor":
        return values
    factor = {"W": .001, "kW": 1., "MW": 1000., "Wh": .001, "kWh": 1., "MWh": 1000.}[unit]
    power_kw = values * factor
    if unit.endswith("Wh"):
        power_kw = power_kw / (interval_minutes/60.)
    return power_kw / capacity_kw


def load_runs(ds):
    """Return finite constant-cadence runs. Neither a file boundary nor a gap is bridged."""
    records, deltas = [], []
    for path in ds.files:
        tc, vc = csv_columns(path, ds.options)
        df = pd.read_csv(path, comment="#", sep=ds.options["csv_separator"], encoding="utf-8-sig", usecols=[tc, vc])
        if df.empty:
            raise ValueError(f"Empty segment: {path}")
        times = parse_time(df[tc], ds.options)
        values = pd.to_numeric(df[vc], errors="coerce").to_numpy(dtype=float)
        if times.hasnans:
            raise ValueError(f"Missing timestamp in {path}")
        if not times.is_monotonic_increasing:
            raise ValueError(f"Unsorted timestamps in {path}; resolve upstream before analysis")
        diff = np.diff(times.asi8)
        deltas.extend(diff[diff>0].tolist())
        records.append((path, times, values))
    if ds.options.get("interval_minutes"):
        step = int(float(ds.options["interval_minutes"])*60*1e9)
    elif deltas:
        choices, counts = np.unique(deltas, return_counts=True)
        step = int(choices[np.argmax(counts)])
    else:
        raise ValueError(f"{ds.id}: cannot infer cadence; specify interval_minutes")
    hour = int(pd.Timedelta("1h").value)
    if step <= 0 or step > hour or hour % step:
        raise ValueError(f"{ds.id}: native cadence must divide one hour; got {step/60e9:g} min")
    if deltas and any(d % step for d in deltas):
        raise ValueError(f"{ds.id}: irregular timestamps or mixed cadence; specify a correct interval_minutes")
    seen, runs, per_file = {}, [], []
    invalid = outside = duplicates = input_rows = 0
    for path, times, raw in records:
        if ds.options["timestamp_position"] == "end":
            times = times - pd.Timedelta(step, unit="ns")
        cf = to_cf(raw, ds.options["value_unit"], ds.capacity_kw, step/60e9)
        good = np.isfinite(cf)
        input_rows += len(cf); invalid += int((~good).sum())
        outside += int(((cf<0)|(cf>1))[good].sum())
        keep = good.copy()
        for j in np.flatnonzero(good):
            key = times[j].value
            if key in seen:
                if not np.isclose(seen[key], cf[j], rtol=1e-10, atol=1e-12):
                    raise ValueError(f"{ds.id}: conflicting overlapping values at {times[j]}")
                keep[j] = False; duplicates += 1
            else:
                seen[key] = cf[j]
        idx = np.flatnonzero(keep)
        if len(idx):
            breaks = np.flatnonzero((np.diff(idx)!=1) | (np.diff(times.asi8[idx])!=step))+1
            for part in np.split(idx, breaks):
                runs.append(pd.Series(cf[part], index=times[part], name=ds.id))
        per_file.append({"dataset_id": ds.id, "csv": str(path), "input_rows": len(cf),
                         "retained_unique_rows": int(keep.sum()), "start": str(times[0]), "end": str(times[-1]),
                         "size_bytes": path.stat().st_size, "mtime_ns": path.stat().st_mtime_ns})
    if not runs:
        raise ValueError(f"{ds.id}: no finite observations")
    runs.sort(key=lambda s: s.index[0])
    audit = {"dataset_id": ds.id, "n_files": len(ds.files), "n_runs": len(runs),
             "input_rows": input_rows, "invalid_values": invalid, "duplicate_rows_removed": duplicates,
             "cf_outside_0_1": outside, "retained_rows": sum(map(len,runs)), "interval_minutes": step/60e9}
    return runs, step, audit, per_file
