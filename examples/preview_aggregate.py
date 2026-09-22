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


def make_preview(n=131):
    if n < 1: raise ValueError("farms must be positive")
    rng=np.random.default_rng(20260922)
    sites=np.where(np.arange(n)%3==0,"offshore","onshore")
    rows=[]; days=[]
    for i,site in enumerate(sites):
        power=rng.beta(2.5 if site=="offshore" else 1.7,3+rng.uniform(-.7,.7),size=(30,24))
        q=np.quantile(power,[.1,.25,.5,.75,.9])
        rows.append(dict(dataset_id=f"PRIVATE_FARM_{i:03}",label=f"Private farm {i:03}",site_type=site,
                         cf_p10=q[0],cf_p25=q[1],cf_median=q[2],cf_p75=q[3],cf_p90=q[4],
                         cf_iqr=q[3]-q[1],ramp_p95=np.quantile(np.abs(np.diff(power,axis=1)),.95),
                         low_fraction=np.mean(power<.05),high_fraction=np.mean(power>.8),
                         stl_daily=rng.beta(2,3),stl_weekly=rng.beta(2,4)))
        days.extend(dict(mean_cf=day.mean(),mean_abs_hourly_ramp=np.abs(np.diff(day)).mean()) for day in power)
    summary=pd.DataFrame(rows)
    if n>4: summary.loc[::17,"stl_weekly"]=np.nan
    hour=np.arange(24)
    medians=np.array([level+.05*np.sin(2*np.pi*hour/24+phase)
                      for level,phase in zip(np.linspace(.12,.8,6),np.linspace(0,2*np.pi,6))])
    shares=np.array([.1,.18,.26,.23,.15,.08])
    patterns=pd.DataFrame(dict(pattern=[f"P{i+1:02}" for i in range(6)],share=shares))
    index=pd.date_range("2018-01-01",periods=24*365*3,freq="1h",tz="UTC")
    coverage=np.clip(np.linspace(1,n,len(index))+rng.normal(0,n*.035,len(index)),0,n).astype(int)
    coverage[8000:8250]=0
    return dict(summary=summary,daily=pd.DataFrame(days),coverage=pd.Series(coverage,index=index),
                patterns=patterns,medians=medians,preview_label="SYNTHETIC STYLE PREVIEW")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",default="results/style_preview")
    parser.add_argument("--farms",type=int,default=131)
    parser.add_argument("--palette",choices=["viridis","plasma"],default="viridis")
    args=parser.parse_args()
    cfg=copy.deepcopy(DEFAULTS)
    cfg.update(output_dir=str(Path(args.output).resolve()),palette=args.palette)
    cfg["plots"]["dpi"]=150
    for path in plot_all(make_preview(args.farms),cfg): print(path)


if __name__=="__main__": main()
