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
    if cfg["plots"].get("layout","clear")=="clear":
        from .clear_plotting import group_output, monthly_coverage, group_monthly_output
        rows=[]
        bounds=[(None,0)]+[(i*10,(i+1)*10) for i in range(10)]+[(100,None)]
        for site,n,values in group_output(result["summary"]):
            rows.extend({"site_type":site,"n_farms":n,"bin":i,"lower_percent":lo,
                         "upper_percent":hi,"mean_time_percent":float(values[i])}
                        for i,(lo,hi) in enumerate(bounds))
        pd.DataFrame(rows).to_csv(tables/"output_distribution.csv",index=False)
        monthly_coverage(result["coverage"]).to_csv(tables/"coverage_monthly.csv",index_label="month_utc")
        group_monthly_output(result["summary"]).to_csv(tables/"monthly_output.csv",index=False)
        if cfg["plots"].get("structure_comparison",True):
            from .structure_plot import structure_summary
            structure_summary(result["summary"]).to_csv(tables/"structure_summary.csv",index=False)
    versions={name:importlib.metadata.version(name) for name in
              ("numpy","pandas","matplotlib","scipy","statsmodels","scikit-learn")}
    manifest={"created_utc":datetime.now(timezone.utc).isoformat(),"python":platform.python_version(),
              "versions":versions,"config":cfg,"ignored_nonsegment_csvs":ignored,
              "original_dataset_count":len(datasets),"segment_count":sum(len(d.files) for d in datasets),
              "selected_daily_profiles":len(result["daily"]),"actual_pattern_count":len(result["patterns"]),
              "datasets":[{"id":d.id,"site_type":d.site_type,"capacity_kw":d.capacity_kw,
                           "options":d.options,"sources":sorted(d.sources), "provenance":d.provenance,
                           "metadata_files":[str(p) for p in d.metadata_files]} for d in datasets]}
    (out/"run_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    n=len(datasets); offshore=sum(d.site_type=="offshore" for d in datasets)
    text=f"""# Data-derived figure description (review before manuscript use)

The analysis comprises {n} original datasets ({offshore} offshore and {n-offshore} onshore),
represented by {sum(len(d.files) for d in datasets)} retained CSV segments. Segment files from
the same source are counted once. All temporal calculations preserve gaps and file boundaries.
Statistics use fully observed hourly sample means of capacity factor. Instantaneous MW power
is divided by capacity in MW without an interval-duration conversion. No interpolation, min–max
normalization, or clipping to [0,1] is applied. Raw invalid and out-of-range counts are audited.

(a) Standardized operating descriptors: CF interquartile range, 95th percentile of absolute
within-run hourly ramps, and fractions below {cfg['analysis']['low_cf']} / above {cfg['analysis']['high_cf']} CF.
Each feature is standardized across farms, then its distribution is shown separately for
offshore and onshore farms. Violins use Gaussian KDE with Scott bandwidth and equal maximum
width; points/bars show medians/interquartile ranges. Missing values are omitted feature by
feature; constant or single-value groups show only a point/bar. No farm identities are plotted.
(b) Group quantile envelopes: compute each farm's hourly CF 10th, 25th, 50th, 75th and 90th
percentiles first. At each percentile, the line is the median across farms of that site type;
the band is the across-farm 25–75% range. These are not confidence intervals or quantiles of
pooled hourly observations. Farms lacking any of the five quantiles are excluded from this panel.
(c) Number of unique original datasets with a complete hour, on a UTC time axis; gaps remain zero.
(d) Joint hexagonal count map of daily versus weekly STL strength. Each eligible farm contributes
once; colour is the number of farms in a cell. The diagonal marks equal strengths. Strengths are
computed independently on continuous windows, then averaged with window-length weights per farm.
Pairs with an unavailable strength are excluded and recorded in the tables; no missing values
are filled with zero. See dataset_summary.csv for eligible windows and hours used.
(e) Density of complete daily profiles by mean CF and mean absolute within-day hourly change.
(f) Median profiles of {len(result['patterns'])} data-derived groups, sorted by mean CF, with the
share of selected days. All {len(result['daily'])} selected days carry equal weight; datasets with
more selected days therefore contribute more. No natural/physical class claim is implied.
The clock timezone is {cfg['analysis']['clock_timezone']}. See cluster_selection.csv and the
manifest for the fitting sample limit, chosen K, sampling settings and library versions.
Panels a, b and d weight farms equally; e and f weight selected days equally. All six panels
summarize the corpus without farm names, IDs, or one-row-per-farm displays. Internal farm identity
is retained in the audit tables for correct segment grouping and reproducibility.

Only requested panels are generated. No silhouette score, farm count, year range or percentage
from an earlier manuscript is reused. This description does not infer model forecasting skill.
"""
    if cfg["plots"].get("layout","clear")=="clear":
        text=f"""# Figure 5 | Output levels, variability and temporal coverage of the wind-power corpus

The corpus contains {n} farms ({offshore} offshore and {n-offshore} onshore), represented by
{sum(len(d.files) for d in datasets)} retained CSV segments. Power is expressed as a percentage
of the capacity denominator recorded for each farm. Hourly values average complete native
samples. Segment boundaries and gaps are preserved; out-of-range output is not clipped.

(a) Two output-frequency curves, connecting the centres of 10-percentage-point output bins.
Frequencies are calculated per
farm, then averaged within offshore/onshore groups, giving farms equal weight regardless
of record length. Frequencies across all twelve bins sum to 100%; the figure shows only
the ten bins within 0-100%. Tail values remain in the denominator and exported tables;
displayed frequencies are not renormalized and can sum to less than 100%. The lines connect
measured bin frequencies, not a fitted probability model. No shading or tail markers are
drawn. Exact 0% and 100% belong to the first and last regular bins.
(b) Mean output versus mean absolute change between consecutive hours, with one anonymous
point per farm. Changes are in percentage points and never cross gaps or segment boundaries.
(c) A narrow vertical temporal-coverage strip, with UTC time increasing upwards and colour
encoding the number of distinct farms with a complete hourly record. Each original farm is
counted at most once per hour, regardless of how many retained segments it has. Zero-coverage
hours remain zero; no monthly averaging or interpolation is applied to the plotted values.
The horizontal colour scale spans zero to the number of farms included in the analysis.
These counts measure record availability, not operating farms. Exact values are exported
in coverage_hourly.csv; coverage_monthly.csv remains a separate descriptive summary.
(d) Mean output by calendar month, shown separately for offshore and onshore farms.
Within each farm, complete hourly values belonging to the same month are pooled across
years and averaged. Farm means are then averaged with equal weights within each site type
and month. Missing months are omitted rather than filled with zero; lines break at missing
months. All valid hours are used, independently of any complete-day sampling limit.
The contributing farms and years can differ between months; this is a descriptive summary
of the retained corpus, not an estimate of a common climatic seasonal effect. Per-month
farm counts are exported in monthly_output.csv; per-farm monthly hours and means are in
dataset_summary.csv. No smoothing or uncertainty band is applied.
The clock timezone is {cfg['analysis']['clock_timezone']}; no local solar-time interpretation is implied.

Supplement S1 (panel e): distributions of paired 24-h and 168-h STL strength estimates.
Boxes show median and quartiles, whiskers extend to the most extreme values within 1.5 IQR,
and points show outliers. The two STL decompositions are fitted independently on eligible
continuous windows and summarized with window-length weights; 168-h strength is not an
isolated weekly component after removal of daily structure.
Supplement S2 (panel f): every cluster's hourly median and share of selected farm-days.
Clustering uses unstandardized 24-dimensional capacity-normalized profiles, so both output
level and temporal shape contribute. The patterns are descriptive, not verified physical regimes.

Only requested panels are generated. Main panels a-d form a 183 x 145 mm figure with editable
text; the narrow c strip occupies the right side, and e/f are supplemental. Titles, panel
letters, sample-size annotations and explanatory footers are omitted from production artwork
for later manuscript assembly. Axis labels, legends and colour scales are retained. Sample
sizes remain available in the exported tables. Synthetic previews alone retain a provenance
label to distinguish them from research results.
No statistical significance, forecasting skill or causal interpretation is inferred.
"""
        if cfg["plots"].get("structure_comparison",True):
            text+="""
Additional figure | Differences in wind-farm operating characteristics.
Each point represents one original farm. Panels show (a) median hourly output, (b) the
within-farm interquartile range of hourly output and (c) the within-farm 95th percentile
of absolute consecutive-hour changes, calculated only within continuous retained segments.
All three axes express the power level, range or change as a percentage of the farm's
capacity denominator. For b/c these numbers equal percentage-point differences in
normalized output, not relative changes from the preceding hour. The short axis labels
are defined precisely here: typical output is the median, typical range is the IQR,
and large hourly change is the 95th percentile of absolute hourly changes. Half-violins summarize the
distribution of farm-level descriptors, separately for offshore/onshore farms, using
Gaussian KDE with Scott bandwidth truncated at the observed group extrema. Maximum
widths are equal across groups and do not encode group size. Black lines mark group
medians. Points are horizontally jittered for visibility; horizontal position within a
group has no quantitative meaning. Constant/single-farm groups show points and a median
without a density shape. Each farm receives equal weight; missing descriptors are omitted
separately per panel, with valid counts retained in structure_summary.csv. Shapes are descriptive, not confidence
intervals or evidence of distinct physical classes. See tables/structure_summary.csv.
"""
    proxies = [d.id for d in datasets if d.provenance.get("capacity_is_proxy")]
    if proxies:
        text += "\nCapacity denominator caveat: the supplied table uses observed-maximum proxies, not verified rated capacities, for " + ", ".join(proxies) + ". Review these denominators before interpreting normalized power as physical capacity factor.\n"
    (out/"figure_description.md").write_text(text,encoding="utf-8")


def main(argv=None):
    parser=argparse.ArgumentParser(description="Calculate wind-corpus plots from retained raw CSV segments and JSON metadata.")
    parser.add_argument("--config",required=True,help="JSON config; relative paths are resolved beside this file")
    parser.add_argument("--validate-only",action="store_true",help="Check grouping, metadata, units and CSV column names only; do not analyze/plot")
    parser.add_argument("--inspect-manifests",action="store_true",help="Check only path/capacity index tables; never access raw time series or JSON, or create outputs")
    parser.add_argument("--overwrite",action="store_true",help="Allow output into a nonempty existing output directory")
    args=parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO,format="%(levelname)s: %(message)s")
    logging.getLogger("fontTools").setLevel(logging.WARNING)
    try:
        cfg=load_config(args.config)
        if args.inspect_manifests:
            from .manifests import read_plan
            _, report = read_plan(cfg)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
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
