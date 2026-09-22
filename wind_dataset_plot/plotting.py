"""Six coordinated panels; no separate small-multiple daily curves."""
from pathlib import Path
import inspect
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


def quantile_envelopes(frame):
    """Across-farm quartiles at each within-farm quantile; every farm has equal weight."""
    columns=["cf_p10", "cf_p25", "cf_median", "cf_p75", "cf_p90"]
    output=[]
    for site in ("offshore", "onshore"):
        values=frame.loc[frame.site_type.eq(site), columns].to_numpy(float)
        values=values[np.isfinite(values).all(axis=1)]
        if len(values):
            output.append((site, len(values), np.quantile(values, [.25,.5,.75], axis=0)))
    return output


def draw(panel, ax, result, cfg, fontsize=9):
    full=result["summary"]
    cmap=plt.get_cmap(cfg["palette"])
    c1,c2=cmap(.22),cmap(.72)
    ax.set_title(f"{panel}  {TITLES[panel]}",loc="left",fontweight="bold",fontsize=fontsize+1,pad=10)
    a=cfg["analysis"]
    if panel=="a":
        z=feature_z(full)
        handles=[]
        for site,offset,color,marker in (("offshore",-.18,c1,"o"),("onshore",.18,c2,"s")):
            selected=z[full.site_type.eq(site).to_numpy()]
            if not len(selected): continue
            handles.append(Line2D([],[],color=color,marker=marker,ls="",label=f"{site.title()} (n={len(selected)})"))
            for j in range(4):
                values=selected[:,j]; values=values[np.isfinite(values)]
                pos=j+offset
                if not len(values):
                    ax.text(0,pos,"NA",fontsize=fontsize-2,va="center",color=color)
                    continue
                if len(values)>1 and np.ptp(values)>1e-10:
                    orientation=({"orientation":"horizontal"} if "orientation" in inspect.signature(ax.violinplot).parameters
                                 else {"vert":False})  # Matplotlib 3.8/3.9 compatibility
                    violin=ax.violinplot([values],positions=[pos],widths=.3,
                                         showextrema=False,showmedians=False,**orientation)
                    for body in violin["bodies"]:
                        body.set_facecolor(color); body.set_edgecolor(color); body.set_alpha(.28)
                q=np.quantile(values,[.25,.5,.75])
                ax.plot(q[[0,2]],[pos,pos],color=color,lw=2.3,solid_capstyle="round")
                ax.scatter(q[1],pos,c=[color],marker=marker,s=15,zorder=3)
        ax.axvline(0,color=".7",lw=.6,ls="--",zorder=0)
        ax.set(yticks=range(4),yticklabels=["CF interquartile range","Hourly |ramp|: P95",
               f"Fraction at CF < {a['low_cf']:g}",f"Fraction at CF > {a['high_cf']:g}"],
               ylim=(3.65,-.65),xlabel="Feature z-score across farms")
        ax.legend(handles=handles,loc="upper center",bbox_to_anchor=(.5,-.18),ncol=2,frameon=False,fontsize=fontsize-1)
        ax.grid(axis="x",color=".93",lw=.6); ax.set_axisbelow(True)
    elif panel=="b":
        for site,n,q in quantile_envelopes(full):
            color=c1 if site=="offshore" else c2
            x=[10,25,50,75,90]
            ax.fill_between(x,q[0],q[2],color=color,alpha=.18,lw=0)
            ax.plot(x,q[1],color=color,lw=1.7,marker="o" if site=="offshore" else "s",
                    ms=4,ls="-" if site=="offshore" else "--",label=f"{site.title()} (n={n})")
        ax.set(xticks=[10,25,50,75,90],xlabel="Within-farm CF percentile",ylabel="Capacity factor")
        ax.grid(color=".93",lw=.6); ax.set_axisbelow(True)
        if ax.get_legend_handles_labels()[0]: ax.legend(frameon=False,fontsize=fontsize-1,loc="best")
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
        cb.set_label("Farms with a fully observed hour",fontsize=fontsize-1)
        cb.locator=MaxNLocator(integer=True,nbins=5); cb.update_ticks()
    elif panel=="d":
        pairs=full[["stl_daily","stl_weekly"]].to_numpy(float)
        valid=np.isfinite(pairs).all(axis=1); pairs=pairs[valid]
        if not len(pairs):
            no_data(ax,f"No farms with both seasonal strengths\n{len(full)} unavailable pairs"); return
        im=ax.hexbin(pairs[:,0],pairs[:,1],gridsize=12,extent=(0,1,0,1),mincnt=1,
                     cmap=cmap,linewidths=0,vmin=0)
        ax.plot([0,1],[0,1],color=".65",lw=.7,ls="--",zorder=0)
        ax.set(xlim=(0,1),ylim=(0,1),xlabel="Daily STL strength",ylabel="Weekly STL strength")
        ax.text(.03,.97,f"{len(pairs)} valid farms; {len(full)-len(pairs)} unavailable",
                transform=ax.transAxes,va="top",fontsize=fontsize-1,
                bbox=dict(facecolor="white",edgecolor="none",alpha=.8,pad=2))
        cb=ax.figure.colorbar(im,ax=ax,pad=.02,fraction=.045)
        cb.set_label("Farms per cell",fontsize=fontsize-1)
        cb.locator=MaxNLocator(integer=True,nbins=4); cb.update_ticks()
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
    outputs=[]; frame=result["summary"]; plots=cfg["plots"]
    offshore=int((frame.site_type=="offshore").sum()); onshore=len(frame)-offshore
    heading=f"{len(frame)} farms | {offshore} offshore, {onshore} onshore"
    if result.get("preview_label"): heading=result["preview_label"]+" | "+heading
    for panel in plots["panels"]:
        height=max(4.5,len(result["patterns"])*.25+2) if panel=="f" else 5.
        fig,ax=plt.subplots(figsize=(8.5 if panel in "af" else 7.,height))
        draw(panel,ax,result,cfg)
        fig.suptitle(heading,fontsize=10,y=1.01)
        if panel=="b":
            fig.text(.5,-.04,"Line: across-farm median; band: across-farm 25–75% range at each percentile\nEach farm has equal weight; bands are not confidence intervals",ha="center",fontsize=8)
        save(fig,out/f"{panel}_{TITLES[panel].lower().replace(' ','_')}",cfg,outputs)
    if plots["combined"] and set(plots["panels"])==set("abcdef"):
        fig=plt.figure(figsize=(15,12))
        gs=fig.add_gridspec(3,3,height_ratios=[1,1,1],width_ratios=[1.2,1.2,.7],wspace=.75,hspace=.85)
        positions={"a":gs[0,:2],"b":gs[1,0],"c":gs[:2,2],"d":gs[1,1],"e":gs[2,0],"f":gs[2,1:]}
        for panel in "abcdef": draw(panel,fig.add_subplot(positions[panel]),result,cfg,fontsize=8)
        fig.suptitle(f"Wind corpus diversity | {heading}",fontsize=13,y=.96)
        fig.text(.5,.025,"a: distributions across farms; point / bar = median / IQR.   b: median and IQR across farm quantiles (not confidence intervals).\n"
                 "a, b, d: equal farm weighting.   e, f: equal day weighting.",
                 ha="center",fontsize=8,color=".3")
        save(fig,out/"figure5_corpus_diversity",cfg,outputs)
    return outputs
