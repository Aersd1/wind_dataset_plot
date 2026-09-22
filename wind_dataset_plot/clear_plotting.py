"""Four direct questions at final print size; method-heavy summaries are supplemental."""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import MaxNLocator

TITLES={"a":"Output distribution", "b":"Differences among farms", "c":"Data available over time",
        "d":"Output by month", "e":"Repeated temporal structure", "f":"All daily profiles"}
OUTPUT_COLUMNS=[f"output_fraction_{i:02}" for i in range(12)]


def monthly_coverage(counts):
    """Average hourly farm count over hours inside the corpus observation span."""
    return counts.resample("MS").mean().rename("mean_farms_with_data")


def group_monthly_output(frame):
    """Equal farm weights within each site/month; missing months stay missing."""
    columns=[f"month_{month:02}_mean_cf" for month in range(1,13)]
    if set(columns)-set(frame.columns):
        raise ValueError("Monthly output statistics missing; rerun analysis with the updated code")
    rows=[]
    for site in ("offshore","onshore"):
        farms=frame.loc[frame.site_type.eq(site)]
        for month,column in enumerate(columns,1):
            values=farms[column].to_numpy(float)
            values=values[np.isfinite(values)]
            rows.append({"site_type":site,"month":month,"n_farms":len(values),
                         "mean_output_percent":float(values.mean()*100) if len(values) else np.nan})
    return pd.DataFrame(rows)


def group_output(frame):
    """Mean per-farm frequency, not pooled hours or an average of quantiles."""
    missing=set(OUTPUT_COLUMNS)-set(frame.columns)
    if missing: raise ValueError("Output-bin statistics missing; rerun analysis with the updated code")
    groups=[]
    for site in ("offshore","onshore"):
        values=frame.loc[frame.site_type.eq(site),OUTPUT_COLUMNS].to_numpy(float)
        values=values[np.isfinite(values).all(axis=1)]
        if len(values): groups.append((site,len(values),values.mean(axis=0)*100))
    return groups


def no_data(ax,message):
    ax.text(.5,.5,message,ha="center",va="center",transform=ax.transAxes,fontsize=6.5,wrap=True)
    ax.set(xticks=[],yticks=[])


def heading(ax,panel):
    label={"e":"S1","f":"S2"}.get(panel,panel)
    ax.text(-.15,1.06,label,transform=ax.transAxes,fontweight="bold",fontsize=8)
    ax.set_title(TITLES[panel],loc="left",fontsize=7,fontweight="bold",pad=7)


def draw_clear(panel,ax,result,cfg):
    heading(ax,panel)
    frame=result["summary"]; cmap=plt.get_cmap(cfg["palette"])
    colours={"offshore":cmap(.20),"onshore":cmap(.68)}
    if panel=="a":
        groups=group_output(frame)
        outside=any(v[0]>0 or v[-1]>0 for _,_,v in groups)
        x=np.arange(5,100,10)
        for j,(site,n,values) in enumerate(groups):
            ax.plot(x,values[1:11],color=colours[site],lw=1.2,marker="o" if j==0 else "s",
                    ms=2.3,ls="-" if j==0 else "--",label=f"{site.title()} (n={n})")
            ax.fill_between(x,values[1:11],color=colours[site],alpha=.10,lw=0)
            if outside:
                # Tail symbols are separate open-ended bins, never interpolated into the curve.
                ax.scatter([-8,108],values[[0,11]],s=9,marker="o" if j==0 else "s",
                           edgecolors=[colours[site]],facecolors="none",linewidths=.7)
        ax.set(xlabel="Power output (% of capacity)",ylabel="Share of time (%)",
               xticks=[0,20,40,60,80,100],xlim=(0,100))
        if outside: ax.set(xticks=[-8,0,25,50,75,100,108],xticklabels=["<0","0","25","50","75","100",">100"],xlim=(-13,113))
        ax.set_ylim(0,max(1.,max((v.max() for _,_,v in groups),default=1.))*1.25)
        ax.legend(frameon=False,fontsize=5.7,loc="upper right",handlelength=1)
    elif panel=="b":
        for site,marker in (("offshore","o"),("onshore","^")):
            data=frame.loc[frame.site_type.eq(site),["cf_mean","ramp_mean"]].dropna()
            if data.empty: continue
            ax.scatter(data.cf_mean*100,data.ramp_mean*100,s=11,color=colours[site],
                       marker=marker,alpha=.7,linewidths=.25,edgecolors="white",label=site.title())
        ax.set(xlabel="Mean output (% of capacity)",ylabel="Mean hourly change\n(percentage points)")
        ax.text(.98,.97,"One point = one farm",transform=ax.transAxes,ha="right",va="top",fontsize=5.7)
        ax.legend(frameon=False,fontsize=5.7,loc="upper left",handletextpad=.3)
        finite=frame.ramp_mean.to_numpy(float)*100
        finite=finite[np.isfinite(finite)]
        ax.set_ylim(0,max(1.,float(finite.max()) if finite.size else 1.)*1.35)
        ax.margins(x=.09)
    elif panel=="c":
        counts=monthly_coverage(result["coverage"])
        dates=counts.index+pd.Timedelta(days=14)
        ax.plot(dates,counts.to_numpy(),color=cmap(.4),lw=1.3,marker="o",ms=1.8)
        ax.fill_between(dates,counts.to_numpy(),0,color=cmap(.4),alpha=.10,lw=0)
        locator=mdates.AutoDateLocator(minticks=2,maxticks=5,interval_multiples=True)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
        ax.xaxis.get_offset_text().set_fontsize(5.5)
        ax.set(xlabel="Time (UTC)",ylabel="Farms with data\n(monthly mean)",ylim=(0,max(1,len(frame))*1.08))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=5,integer=True))
        ax.set_xlim(counts.index[0],counts.index[-1]+pd.offsets.MonthBegin(1))
    elif panel=="d":
        monthly=group_monthly_output(frame)
        finite=monthly.mean_output_percent.dropna().to_numpy()
        if not len(finite): no_data(ax,"No complete hourly records"); return
        for j,site in enumerate(("offshore","onshore")):
            data=monthly.loc[monthly.site_type.eq(site)]
            if not data.n_farms.any(): continue
            ax.plot(data.month,data.mean_output_percent,color=colours[site],lw=1.2,
                    marker="o" if j==0 else "s",ms=2.3,ls="-" if j==0 else "--",label=site.title())
        ax.set(xlabel="Month",ylabel="Mean output (% of capacity)",xlim=(.7,12.3),
               xticks=range(1,13),xticklabels=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],
               ylim=(min(0,float(finite.min())*1.1),max(100,float(finite.max())*1.1)))
        ax.tick_params(axis="x",labelrotation=45)
        ax.legend(frameon=False,fontsize=5.7,loc="upper right",handlelength=1.5)
    elif panel=="e":
        values=frame[["stl_daily","stl_weekly"]].to_numpy(float)
        values=values[np.isfinite(values).all(axis=1)]
        if not len(values): no_data(ax,"No valid paired STL estimates"); return
        boxes=ax.boxplot([values[:,0],values[:,1]],positions=[1,2],widths=.45,patch_artist=True,
                         medianprops=dict(color="black",lw=1),flierprops=dict(marker=".",markersize=2),
                         whiskerprops=dict(lw=.6),capprops=dict(lw=.6))
        for body,color in zip(boxes["boxes"],[cmap(.25),cmap(.7)]): body.set(facecolor=color,alpha=.4,linewidth=.6)
        ax.set(xticks=[1,2],xticklabels=["24 h","168 h"],xlabel="STL period",ylabel="Seasonal strength",ylim=(0,1))
        ax.text(.98,.97,f"{len(values)} paired farms",transform=ax.transAxes,ha="right",va="top",fontsize=5.7)
    elif panel=="f":
        patterns=result["patterns"]; medians=np.asarray(result["medians"])
        if patterns.empty: no_data(ax,"No complete daily records"); return
        im=ax.imshow(medians*100,cmap=cmap,aspect="auto",interpolation="nearest",
                     vmin=min(0,float(medians.min())*100),vmax=max(100,float(medians.max())*100))
        ax.set(xticks=[0,6,12,18,23],yticks=np.arange(len(patterns)),
               yticklabels=patterns.pattern.tolist(),xlabel=f"Hour of day ({cfg['analysis']['clock_timezone']})",
               ylabel="Profile cluster")
        for j,share in enumerate(patterns["share"]):
            ax.text(1.02,1-(j+.5)/len(patterns),f"{share:.1%}",va="center",transform=ax.transAxes,fontsize=5.5)
        cb=ax.figure.colorbar(im,ax=ax,orientation="horizontal",pad=.28,fraction=.07,aspect=35)
        cb.set_label("Median output (% of capacity)",fontsize=6)
        cb.ax.tick_params(labelsize=5.5)
    ax.tick_params(labelsize=6,width=.5,length=2.5)
    ax.spines[["top","right"]].set_visible(False)
    for spine in ax.spines.values(): spine.set_linewidth(.5)


def save_exact(fig,path,cfg,outputs):
    # No tight bounding-box crop: preserve the final publication dimensions.
    for fmt in cfg["plots"]["formats"]:
        target=path.with_suffix("."+fmt)
        fig.savefig(target,dpi=cfg["plots"]["dpi"],facecolor="white")
        outputs.append(str(target))
    plt.close(fig)


def plot_clear(result,cfg):
    out=Path(cfg["output_dir"])/"figures"; out.mkdir(parents=True,exist_ok=True)
    outputs=[]; selected=cfg["plots"]["panels"]
    settings={"font.family":"sans-serif","font.sans-serif":["Arial","Helvetica","DejaVu Sans"],
              "font.size":7,"axes.labelsize":7,"pdf.fonttype":42,"ps.fonttype":42,
              "svg.fonttype":"none","axes.grid":False}
    with plt.rc_context(settings):
        for panel in selected:
            fig,ax=plt.subplots(figsize=(89/25.4,80/25.4))
            fig.subplots_adjust(left=.21,right=.90,bottom=.21,top=.88)
            draw_clear(panel,ax,result,cfg)
            if result.get("preview_label"):
                fig.text(.5,.98,result["preview_label"],ha="center",va="top",fontsize=5.5,color=".35")
            stem=f"main_{panel}" if panel in "abcd" else f"supplement_{panel}"
            save_exact(fig,out/stem,cfg,outputs)
        if cfg["plots"]["combined"] and set("abcd")<=set(selected):
            fig,axes=plt.subplots(2,2,figsize=(183/25.4,145/25.4))
            fig.subplots_adjust(left=.10,right=.90,bottom=.10,top=.93,wspace=.48,hspace=.75)
            for panel,ax in zip("abcd",axes.flat): draw_clear(panel,ax,result,cfg)
            if result.get("preview_label"):
                fig.text(.5,.99,result["preview_label"],ha="center",va="top",fontsize=6,color=".35")
            save_exact(fig,out/"figure5_clear",cfg,outputs)
    return outputs
