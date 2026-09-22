"""Synthetic style preview only. These illustrative descriptors are NOT research results.

Run from an installed checkout:
python examples/preview_aggregate.py --output results/style_preview --farms 131
Never reads user CSV/JSON files. Seasonal strengths here are random layout fixtures,
not estimates; the production CLI still calculates all statistics from retained CSVs.
"""
import argparse
import copy
from pathlib import Path
import numpy as np
import pandas as pd
from wind_dataset_plot.config import DEFAULTS
from wind_dataset_plot.plotting import plot_all
from wind_dataset_plot.analysis import output_fractions, cluster_profiles


def make_preview(n=131):
    if n < 1: raise ValueError("farms must be positive")
    rng=np.random.default_rng(20260922)
    sites=np.where(np.arange(n)<max(1,round(n*31/131)),"offshore","onshore")
    rows=[]; days=[]; profiles=[]
    for i,site in enumerate(sites):
        hour=np.arange(24)
        level=rng.uniform(.15,.7)
        # A synthetic 360-day year, with 30 days per illustrative calendar month.
        month=np.repeat(np.arange(12),30)
        daily_level=np.clip(level+.10*np.cos(2*np.pi*month[:,None]/12)+rng.normal(0,.17,(360,1)),.04,.92)
        amplitude=rng.uniform(.02,.25)
        power=np.clip(daily_level+amplitude*np.sin(2*np.pi*hour/24+rng.uniform(0,2*np.pi,(360,1)))
                      +rng.normal(0,.015 if site=="offshore" else .035,(360,24)),0,1)
        q=np.quantile(power,[.1,.25,.5,.75,.9])
        rows.append(dict(dataset_id=f"PRIVATE_FARM_{i:03}",label=f"Private farm {i:03}",site_type=site,
                         cf_p10=q[0],cf_p25=q[1],cf_median=q[2],cf_p75=q[3],cf_p90=q[4],
                         cf_mean=power.mean(),cf_iqr=q[3]-q[1],ramp_mean=np.abs(np.diff(power,axis=1)).mean(),
                         ramp_p95=np.quantile(np.abs(np.diff(power,axis=1)),.95),
                         low_fraction=np.mean(power<.05),high_fraction=np.mean(power>.8),
                         stl_daily=rng.beta(2,3),stl_weekly=rng.beta(2,4)))
        rows[-1].update({f"output_fraction_{j:02}":v for j,v in enumerate(output_fractions(power.ravel()))})
        for m in range(1,13):
            rows[-1][f"month_{m:02}_mean_cf"]=power[month==m-1].mean()
            rows[-1][f"month_{m:02}_hours"]=int(np.sum(month==m-1)*24)
        days.extend(dict(mean_cf=day.mean(),mean_abs_hourly_ramp=np.abs(np.diff(day)).mean()) for day in power)
        profiles.extend(power)
    summary=pd.DataFrame(rows)
    if n>4: summary.loc[::17,"stl_weekly"]=np.nan
    _,patterns,medians,_=cluster_profiles(np.array(profiles),{**DEFAULTS["analysis"],"clusters":6})
    index=pd.date_range("2018-01-01",periods=24*365*3,freq="1h",tz="UTC")
    coverage=np.clip(n*(.45+.2*np.sin(np.linspace(0,8,len(index))))+rng.normal(0,n*.06,len(index)),0,n).astype(int)
    coverage[8000:8250]=0
    return dict(summary=summary,daily=pd.DataFrame(days),coverage=pd.Series(coverage,index=index),
                patterns=patterns,medians=medians,preview_label="SYNTHETIC STYLE PREVIEW")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",default="results/clear_preview")
    parser.add_argument("--farms",type=int,default=131)
    parser.add_argument("--palette",choices=["viridis","plasma"],default="plasma")
    parser.add_argument("--layout",choices=["clear","legacy"],default="clear")
    args=parser.parse_args()
    cfg=copy.deepcopy(DEFAULTS)
    cfg.update(output_dir=str(Path(args.output).resolve()),palette=args.palette)
    cfg["plots"]["dpi"]=150
    cfg["plots"]["layout"]=args.layout
    for path in plot_all(make_preview(args.farms),cfg): print(path)


if __name__=="__main__": main()
