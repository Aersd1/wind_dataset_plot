"""CLI: inspect provenance first; analyze only on an explicit normal invocation."""
import argparse
import importlib.metadata
import json
import logging
from pathlib import Path
import platform
import sys
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from .config import load_config
from .io import discover, resolve_metadata, csv_columns
from .analysis import analyze
from .plotting import plot_all


def export(result,cfg,datasets,ignored):
    out=Path(cfg["output_dir"]); tables=out/"tables"; tables.mkdir(parents=True,exist_ok=True)
    for key,name in (("summary","dataset_summary"),("audit","quality_audit"),("files","segment_inventory"),
                     ("daily","daily_statistics"),("patterns","pattern_summary"),("candidates","cluster_selection")):
        result[key].to_csv(tables/f"{name}.csv",index=False)
    result["coverage"].to_csv(tables/"coverage_hourly.csv")
    pd.DataFrame(result["medians"],columns=[f"hour_{h:02}" for h in range(24)]).assign(
        pattern=result["patterns"].get("pattern",pd.Series(dtype=str))).to_csv(tables/"pattern_medians.csv",index=False)
    # Profile rows align exactly with daily_statistics.csv for reproducibility.
    np.savez_compressed(tables/"daily_profiles.npz",profiles=result["profiles"])
    versions={name:importlib.metadata.version(name) for name in
              ("numpy","pandas","matplotlib","scipy","statsmodels","scikit-learn")}
    manifest={"created_utc":datetime.now(timezone.utc).isoformat(),"python":platform.python_version(),
              "versions":versions,"config":cfg,"ignored_nonsegment_csvs":ignored,
              "original_dataset_count":len(datasets),"segment_count":sum(len(d.files) for d in datasets),
              "selected_daily_profiles":len(result["daily"]),"actual_pattern_count":len(result["patterns"]),
              "datasets":[{"id":d.id,"site_type":d.site_type,"capacity_kw":d.capacity_kw,
                           "options":d.options,"sources":sorted(d.sources),
                           "metadata_files":[str(p) for p in d.metadata_files]} for d in datasets]}
    (out/"run_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    n=len(datasets); offshore=sum(d.site_type=="offshore" for d in datasets)
    text=f"""# Data-derived figure description (review before manuscript use)

The analysis comprises {n} original datasets ({offshore} offshore and {n-offshore} onshore),
represented by {sum(len(d.files) for d in datasets)} retained CSV segments. Segment files from
the same source are counted once. All temporal calculations preserve gaps and file boundaries.
Statistics use fully observed hourly means of capacity factor. No interpolation, min–max
normalization, or clipping to [0,1] is applied. Raw invalid and out-of-range counts are audited.

(a) Standardized operating descriptors: CF interquartile range, 95th percentile of absolute
within-run hourly ramps, and fractions below {cfg['analysis']['low_cf']} / above {cfg['analysis']['high_cf']} CF.
(b) Per-dataset median and 25–75% / 10–90% empirical intervals, not confidence intervals.
(c) Number of unique original datasets with a complete hour, on a UTC time axis; gaps remain zero.
(d) Daily and weekly STL seasonal strength, computed independently on eligible continuous
windows, then averaged with window-length weights per original dataset. NA denotes insufficient
or constant data. See dataset_summary.csv for eligible windows and hours used.
(e) Density of complete daily profiles by mean CF and mean absolute within-day hourly change.
(f) Median profiles of {len(result['patterns'])} data-derived groups, sorted by mean CF, with the
share of selected days. All {len(result['daily'])} selected days carry equal weight; datasets with
more selected days therefore contribute more. No natural/physical class claim is implied.
The clock timezone is {cfg['analysis']['clock_timezone']}. See cluster_selection.csv and the
manifest for the fitting sample limit, chosen K, sampling settings and library versions.

Only requested panels are generated. No silhouette score, farm count, year range or percentage
from an earlier manuscript is reused. This description does not infer model forecasting skill.
"""
    (out/"figure_description.md").write_text(text,encoding="utf-8")


def main(argv=None):
    parser=argparse.ArgumentParser(description="Calculate wind-corpus plots from retained raw CSV segments and JSON metadata.")
    parser.add_argument("--config",required=True,help="JSON config; relative paths are resolved beside this file")
    parser.add_argument("--validate-only",action="store_true",help="Check grouping, metadata, units and CSV column names only; do not analyze/plot")
    parser.add_argument("--overwrite",action="store_true",help="Allow output into a nonempty existing output directory")
    args=parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO,format="%(levelname)s: %(message)s")
    logging.getLogger("fontTools").setLevel(logging.WARNING)
    try:
        cfg=load_config(args.config)
        out=Path(cfg["output_dir"])
        data=Path(cfg["data_dir"])
        if out==data or out.is_relative_to(data) or data.is_relative_to(out):
            raise ValueError("output_dir and data_dir must not contain each other")
        datasets,ignored=discover(cfg)
        resolve_metadata(datasets,cfg)
        for ds in datasets:
            for path in ds.files: csv_columns(path,ds.options)
        logging.info("%s original datasets, %s retained segments; %s nonsegment CSVs ignored",
                     len(datasets),sum(len(d.files) for d in datasets),len(ignored))
        if args.validate_only:
            print(json.dumps({"datasets":[{"id":d.id,"segments":len(d.files),"site_type":d.site_type,
                                          "unit":d.options["value_unit"],"capacity_kw":d.capacity_kw} for d in datasets],
                              "ignored":ignored},ensure_ascii=False,indent=2))
            return 0
        if out.exists() and any(out.iterdir()) and not args.overwrite:
            raise ValueError("Output directory is nonempty. Choose a fresh directory or pass --overwrite.")
        result=analyze(datasets,cfg)
        out.mkdir(parents=True,exist_ok=True)
        export(result,cfg,datasets,ignored)
        outputs=plot_all(result,cfg)
        (out/"figure_files.json").write_text(json.dumps(outputs,indent=2),encoding="utf-8")
        logging.info("Wrote %s figure files to %s",len(outputs),out)
        if result["audit"].cf_outside_0_1.sum():
            logging.warning("CF outside [0,1] was preserved; review quality_audit.csv and units/capacity")
        return 0
    except (ValueError,FileNotFoundError,KeyError) as exc:
        parser.exit(2,f"Error: {exc}\n")


if __name__=="__main__":
    sys.exit(main())
