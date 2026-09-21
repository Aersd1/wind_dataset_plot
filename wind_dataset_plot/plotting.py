"""Six coordinated panels; no separate small-multiple daily curves."""
from pathlib import Path
import math
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.colors import LogNorm
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator
from mpl_toolkits.axes_grid1 import make_axes_locatable

TITLES={"a":"Operating characteristics", "b":"Output distributions",
        "c":"Temporal coverage", "d":"Daily and weekly seasonality",
        "e":"Daily output and variability", "f":"Daily-pattern matrix"}


def style():
    plt.rcParams.update({"font.family":"DejaVu Sans", "font.size":9,
                         "axes.spines.top":False,"axes.spines.right":False,
                         "axes.linewidth":.6,"xtick.major.width":.6,"ytick.major.width":.6,
                         "pdf.fonttype":42,"ps.fonttype":42,"svg.fonttype":"none",
                         "savefig.facecolor":"white"})


def no_data(ax, text):
    ax.text(.5,.5,text,ha="center",va="center",transform=ax.transAxes,wrap=True)
    ax.set_axis_off()


def dataset_labels(frame):
    # Real IDs/explicit short labels; never substitute fabricated farm names.
    return frame["label"].astype(str).tolist()


def feature_z(frame):
    cols=["cf_iqr","ramp_p95","low_fraction","high_fraction"]
    x=frame[cols].to_numpy(float)
    z=np.full_like(x,np.nan)
    for j in range(x.shape[1]):
        finite=np.isfinite(x[:,j])
        if finite.any():
            sd=x[finite,j].std()
            z[finite,j]=(x[finite,j]-x[finite,j].mean())/sd if sd>1e-12 else 0
    return z


def draw(panel, ax, result, cfg, frame=None, fontsize=9):
    full=result["summary"]
    frame=full if frame is None else frame
    cmap=plt.get_cmap(cfg["palette"])
    c1,c2=cmap(.22),cmap(.72)
    ax.set_title(f"{panel}  {TITLES[panel]}",loc="left",fontweight="bold",fontsize=fontsize+1,pad=10)
    y=np.arange(len(frame))
    a=cfg["analysis"]
    if panel=="a":
        z=feature_z(full)
        valid=z[np.isfinite(z)]
        bound=max(1.,float(np.max(np.abs(valid)))) if valid.size else 1.
        cm=cmap.with_extremes(bad="#dddddd")
        im=ax.imshow(z[frame.index],aspect="auto",cmap=cm,vmin=-bound,vmax=bound,interpolation="nearest")
        ax.set_xticks(range(4),["CF\nIQR","95th-pct.\n|hourly ramp|",f"Time at\nCF < {a['low_cf']:g}",f"Time at\nCF > {a['high_cf']:g}"])
        ax.set_yticks(y,dataset_labels(frame))
        cbax=make_axes_locatable(ax).append_axes("bottom",size=.09,pad=.62)
        cb=ax.figure.colorbar(im,cax=cbax,orientation="horizontal")
        cb.set_label("Feature z-score\nGrey = unavailable",fontsize=fontsize-1)
    elif panel=="b":
        for j,(_,row) in enumerate(frame.iterrows()):
            color=c1 if row.site_type=="offshore" else c2
            ax.plot([row.cf_p10,row.cf_p90],[j,j],color=color,alpha=.5,lw=1)
            ax.plot([row.cf_p25,row.cf_p75],[j,j],color=color,lw=3)
            ax.scatter(row.cf_median,j,c=[color],marker="o" if row.site_type=="offshore" else "s",
                       s=25,edgecolors="white",linewidths=.5,zorder=3)
        ax.set(yticks=y,yticklabels=dataset_labels(frame),ylim=(len(frame)-.5,-.5),xlabel="Capacity factor")
        ax.grid(axis="x",color=".9",lw=.6); ax.set_axisbelow(True)
        ax.legend(handles=[Line2D([],[],color=c1,marker="o",ls="",label="Offshore"),
                           Line2D([],[],color=c2,marker="s",ls="",label="Onshore")],
                  frameon=False,fontsize=fontsize-1,loc="best")
    elif panel=="c":
        counts=result["coverage"]
        start=mdates.date2num(counts.index[0].to_pydatetime())
        end=mdates.date2num((counts.index[-1]+pd.Timedelta("1h")).to_pydatetime())
        im=ax.imshow(counts.to_numpy()[:,None],extent=(0,1,start,end),origin="lower",aspect="auto",
                     cmap=cmap,vmin=0,vmax=len(full),interpolation="nearest")
        ax.yaxis_date(); locator=mdates.AutoDateLocator(minticks=3,maxticks=8)
        ax.yaxis.set_major_locator(locator); ax.yaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
        ax.set(xticks=[],ylabel="Time (UTC)")
        cb=ax.figure.colorbar(im,ax=ax,orientation="horizontal",pad=.11,fraction=.035)
        cb.set_label("Original datasets with a fully observed hour",fontsize=fontsize-1)
        cb.locator=MaxNLocator(integer=True,nbins=5); cb.update_ticks()
    elif panel=="d":
        for j,(_,row) in enumerate(frame.iterrows()):
            d,w=row.stl_daily,row.stl_weekly
            if np.isfinite(d) and np.isfinite(w):
                ax.plot([d,w],[j,j],color=".75",lw=1)
            if np.isfinite(d): ax.scatter(d,j,color=c1,s=22)
            if np.isfinite(w): ax.scatter(w,j,edgecolors=[c2],facecolors="white",marker="s",s=24,lw=1.1)
            if not np.isfinite(d) or not np.isfinite(w):
                text="D,W: NA" if not np.isfinite(d) and not np.isfinite(w) else ("D: NA" if not np.isfinite(d) else "W: NA")
                ax.text(1.01,j,text,va="center",fontsize=fontsize-2)
        ax.set(xlim=(-.025,1.025),xticks=np.linspace(0,1,6),ylim=(len(frame)-.5,-.5),
               yticks=y,yticklabels=dataset_labels(frame),xlabel="STL seasonal strength")
        ax.grid(axis="x",color=".9",lw=.6); ax.set_axisbelow(True)
        ax.legend(handles=[Line2D([],[],marker="o",color=c1,ls="",label="Daily"),
                           Line2D([],[],marker="s",markerfacecolor="white",color=c2,ls="",label="Weekly")],
                  loc="best",frameon=False,fontsize=fontsize-1)
    elif panel=="e":
        daily=result["daily"]
        if daily.empty:
            no_data(ax,"No gap-free, complete 24-hour days"); return
        im=ax.hexbin(daily.mean_cf,daily.mean_abs_hourly_ramp,gridsize=30,mincnt=1,
                     cmap=cmap,norm=LogNorm(),linewidths=0)
        ax.set(xlabel="Daily mean capacity factor",ylabel="Mean absolute hourly change in CF")
        cb=ax.figure.colorbar(im,ax=ax,pad=.02,fraction=.045)
        cb.set_label("Days per cell (log colour scale)",fontsize=fontsize-1)
    elif panel=="f":
        patterns=result["patterns"]; medians=result["medians"]
        if patterns.empty:
            no_data(ax,"No complete daily profiles available for clustering"); return
        im=ax.imshow(medians,aspect="auto",cmap=cmap,vmin=min(0.,float(medians.min())),
                     vmax=max(1.,float(medians.max())),interpolation="nearest",extent=(-.5,23.5,len(medians)-.5,-.5))
        ax.set(xticks=[0,6,12,18,23],xlabel=f"Hour of day ({a['clock_timezone']})",
               yticks=np.arange(len(medians)),yticklabels=patterns.pattern.tolist(),ylabel="Daily pattern")
        for j,row in patterns.iterrows():
            ax.text(24.2,j,f"{row['share']:.1%}",va="center",fontsize=fontsize-1,clip_on=False)
        ax.text(1.03,1.03,"Share",fontsize=fontsize-1,transform=ax.transAxes)
        cbax=make_axes_locatable(ax).append_axes("bottom",size=.09,pad=.55)
        cb=ax.figure.colorbar(im,cax=cbax,orientation="horizontal")
        cb.set_label("Median capacity factor; common scale across patterns",fontsize=fontsize-1)
    ax.tick_params(labelsize=fontsize-1)


def save(fig,path,cfg,outputs):
    for fmt in cfg["plots"]["formats"]:
        target=path.with_suffix("."+fmt)
        fig.savefig(target,dpi=cfg["plots"]["dpi"],bbox_inches="tight",pad_inches=.16)
        outputs.append(str(target))
    plt.close(fig)


def plot_all(result,cfg):
    style()
    out=Path(cfg["output_dir"])/"figures"; out.mkdir(parents=True,exist_ok=True)
    outputs=[]; frame=result["summary"]; plots=cfg["plots"]; limit=plots["rows_per_page"]
    offshore=int((frame.site_type=="offshore").sum()); onshore=len(frame)-offshore
    for panel in plots["panels"]:
        pages=math.ceil(len(frame)/limit) if panel in "abd" else 1
        for page in range(pages):
            selected=frame.iloc[page*limit:(page+1)*limit] if panel in "abd" else frame
            height=max(4.,len(selected)*.21+1.8) if panel in "abd" else (max(4.5,len(result["patterns"])*.25+2) if panel=="f" else 5.)
            fig,ax=plt.subplots(figsize=(8.5 if panel in "abdf" else 7.,height))
            draw(panel,ax,result,cfg,selected)
            fig.suptitle(f"{len(frame)} original datasets | {offshore} offshore, {onshore} onshore",fontsize=10,y=1.01)
            if panel=="b":
                fig.text(.5,-.02,"Point: median; thick line: 25–75%; thin line: 10–90% (not confidence intervals)",ha="center",fontsize=8)
            suffix=f"_{page+1:02}" if pages>1 else ""
            save(fig,out/f"{panel}_{TITLES[panel].lower().replace(' ','_')}{suffix}",cfg,outputs)
    if plots["combined"] and set(plots["panels"])==set("abcdef") and len(frame)<=limit:
        fig=plt.figure(figsize=(15,max(12,len(frame)*.32+5)))
        gs=fig.add_gridspec(3,3,height_ratios=[1.2,1.2,.85],wspace=.8,hspace=.65)
        positions={"a":gs[0,0],"b":gs[0,1],"c":gs[0,2],"d":gs[1,0],"e":gs[1,1:],"f":gs[2,:]}
        for panel in "abcdef": draw(panel,fig.add_subplot(positions[panel]),result,cfg,fontsize=8)
        fig.suptitle(f"Wind training-corpus diversity | {len(frame)} original datasets",fontsize=15,y=.98)
        save(fig,out/"figure5_corpus_diversity",cfg,outputs)
    return outputs
