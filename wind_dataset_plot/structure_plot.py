"""Anonymous farm-level distributions: location, spread and temporal changes."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import gaussian_kde

METRICS=(
    ("cf_median","Typical output","Typical power output\n(% of farm capacity)"),
    ("cf_iqr","Output spread","Typical output range\n(% of farm capacity)"),
    ("ramp_p95","Large hourly changes","Large hourly power change\n(% of farm capacity)"),
)


def structure_groups(frame):
    required={"dataset_id","site_type",*(m[0] for m in METRICS)}
    if required-set(frame): raise ValueError(f"Missing structure statistics: {sorted(required-set(frame))}")
    if frame.dataset_id.isna().any() or frame.dataset_id.duplicated().any():
        raise ValueError("Structure input must have one row per original farm, not one row per segment")
    if not frame.site_type.isin(["offshore","onshore"]).all():
        raise ValueError("Structure input site_type must be offshore or onshore")
    for key,title,label in METRICS:
        for site in ("offshore","onshore"):
            values=frame.loc[frame.site_type.eq(site),key].to_numpy(float)*100
            yield key,title,label,site,values[np.isfinite(values)]


def structure_summary(frame):
    rows=[]
    for key,_,_,site,values in structure_groups(frame):
        q=np.quantile(values,[.25,.5,.75]) if len(values) else [np.nan]*3
        rows.append(dict(metric=key,site_type=site,n_farms=len(values),
                         q25=q[0],median=q[1],q75=q[2],
                         unit="percent_of_capacity" if key=="cf_median" else "percentage_points"))
    return pd.DataFrame(rows)


def draw_structure(axes,frame,palette,seed=20260921):
    cmap=plt.get_cmap(palette)
    groups=list(structure_groups(frame))
    rng=np.random.default_rng(seed)
    for i,(key,title,label) in enumerate(METRICS):
        ax=axes[i]; pooled=[]; ticklabels=[]
        for pos,site in enumerate(("offshore","onshore")):
            values=next(g[4] for g in groups if g[0]==key and g[3]==site)
            color=cmap(.20 if site=="offshore" else .68)
            ticklabels.append(f"{site.title()}\n(n={len(values)})")
            if not len(values): continue
            pooled.extend(values)
            # Truncate KDE at observed extrema: no fabricated tails outside sample support.
            if len(values)>1 and np.ptp(values)>1e-10:
                grid=np.linspace(values.min(),values.max(),180)
                density=gaussian_kde(values,bw_method="scott")(grid)
                width=.32*density/density.max()
                ax.fill_betweenx(grid,pos-.04-width,pos-.04,color=color,alpha=.24,lw=.5,edgecolor=color)
            jitter=rng.uniform(.05,.29,len(values))
            ax.scatter(pos+jitter,values,s=8,color=color,alpha=.60,linewidths=0,
                       marker="o" if site=="offshore" else "^",zorder=3)
            median=float(np.median(values))
            ax.plot([pos-.17,pos+.015],[median,median],color="black",lw=1.4,zorder=4)
        ax.set_title(title,loc="left",fontsize=7,fontweight="bold",pad=8)
        ax.text(-.20,1.065,"abc"[i],transform=ax.transAxes,fontsize=8,fontweight="bold")
        ax.set(xticks=[0,1],xticklabels=ticklabels,xlim=(-.5,1.48),ylabel=label)
        if pooled:
            low=min(0,float(np.min(pooled))); high=max(1,float(np.max(pooled)))
            ax.set_ylim(low-.02*(high-low),high+.12*(high-low))
        else:
            ax.text(.5,.5,"No valid farm statistics",ha="center",transform=ax.transAxes,fontsize=6)
        ax.tick_params(labelsize=6,length=2.5,width=.5)
        ax.spines[["top","right"]].set_visible(False)
        for spine in ax.spines.values(): spine.set_linewidth(.5)


def plot_structure(result,cfg):
    out=Path(cfg["output_dir"])/"figures"; out.mkdir(parents=True,exist_ok=True)
    with plt.rc_context({"font.family":"sans-serif","font.sans-serif":["Arial","Helvetica","DejaVu Sans"],
                         "font.size":7,"axes.labelsize":7,"pdf.fonttype":42,"svg.fonttype":"none"}):
        fig,axes=plt.subplots(1,3,figsize=(183/25.4,82/25.4))
        fig.subplots_adjust(left=.085,right=.985,bottom=.25,top=.84,wspace=.70)
        draw_structure(axes,result["summary"],cfg["palette"],cfg["analysis"]["seed"])
        fig.text(.5,.055,"Each point: one farm    |    Black line: group median    |    Wider shape: greater concentration",
                 ha="center",fontsize=6)
        if result.get("preview_label"):
            fig.text(.5,.98,result["preview_label"],ha="center",va="top",fontsize=6,color=".35")
        paths=[]
        for fmt in cfg["plots"]["formats"]:
            path=out/f"farm_structure_comparison.{fmt}"
            fig.savefig(path,dpi=cfg["plots"]["dpi"],facecolor="white")
            paths.append(str(path))
        plt.close(fig)
    return paths


def main(argv=None):
    parser=argparse.ArgumentParser(description="Plot structural differences from a pipeline-generated dataset_summary.csv.")
    parser.add_argument("--summary",required=True)
    parser.add_argument("--output",required=True,help="A new or empty output directory")
    parser.add_argument("--palette",choices=["viridis","plasma"],default="plasma")
    args=parser.parse_args(argv)
    out=Path(args.output)
    if out.exists() and any(out.iterdir()): parser.error("Choose a new or empty output directory")
    frame=pd.read_csv(args.summary)
    summary=structure_summary(frame)  # Validate before creating outputs.
    from .config import DEFAULTS
    import copy
    cfg=copy.deepcopy(DEFAULTS); cfg.update(output_dir=str(out),palette=args.palette)
    paths=plot_structure({"summary":frame},cfg)
    summary.to_csv(out/"structure_summary.csv",index=False)
    (out/"source.json").write_text(json.dumps({"source_summary":str(Path(args.summary).resolve()),
                                             "palette":args.palette,"figures":paths},indent=2),encoding="utf-8")
    print("\n".join(paths))
    return 0


if __name__=="__main__": main()
