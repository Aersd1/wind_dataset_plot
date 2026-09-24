"""Requested stand-alone panels; captions and farm identities stay in companion tables."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from ._panel_alignment import require_matplotlib_panel_alignment

COLORS={'offshore':'#6500A8','onshore':'#EB7754'}
SIZE_COLORS=['#6500A8','#B53679','#FCA636']
plt.rcParams.update({'font.family':'Arial','font.sans-serif':['Arial','DejaVu Sans'],
                     'font.size':7,'axes.labelsize':7,'xtick.labelsize':6.5,'ytick.labelsize':6.5,
                     'legend.fontsize':6.5,'legend.frameon':False,'axes.spines.top':False,
                     'axes.spines.right':False,'axes.linewidth':.65,'pdf.fonttype':42,'svg.fonttype':'none'})

def save(fig,path,exclude_axes=None):
    fig.canvas.draw()
    require_matplotlib_panel_alignment(fig,json_out=str(path)+'.alignment.json',strict=True,
                                      tolerance_pt=1.5,gutter_tolerance_pt=1.5,exclude_axes=exclude_axes or [])
    fig.savefig(path.with_suffix('.pdf'))
    fig.savefig(path.with_suffix('.svg'))
    fig.savefig(path.with_suffix('.png'),dpi=600)
    plt.close(fig)
    return str(path.with_suffix('.pdf'))

def categorical_offsets(n,width=.22):
    return ((np.arange(n)*.61803398875)%1-.5)*width

def violin(ax,values,x,color,width=.6):
    values=np.asarray(values,float);values=values[np.isfinite(values)]
    if len(values)>1 and np.ptp(values)>0:
        bodies=ax.violinplot([values],positions=[x],widths=width,showextrema=False)['bodies']
        for body in bodies:
            body.set_facecolor(color);body.set_edgecolor(color);body.set_alpha(.24)
    if len(values):
        ax.plot([x-width*.3,x+width*.3],[np.median(values)]*2,color='#252525',lw=1.1)

def output_panel(summary,path):
    fig,ax=plt.subplots(figsize=(3.5433071,2.9527559))
    fig.subplots_adjust(left=.2,right=.975,bottom=.16,top=.97)
    v=summary.cf_mean.to_numpy()*100
    violin(ax,v,0,'#66719E',width=.8)
    for kind in ['offshore','onshore']:
        values=summary.loc[summary.site_type.eq(kind),'cf_mean'].dropna().to_numpy()*100
        ax.scatter(categorical_offsets(len(values)),values,s=12,color=COLORS[kind],linewidths=0,
                   marker='o' if kind=='offshore' else '^',alpha=.7)
    ax.set(xticks=[0],xticklabels=['All farms'],ylabel='Mean output (% of rated capacity)',xlim=(-.65,.65))
    ax.legend(handles=[Line2D([],[],color=COLORS[k],marker='o' if k=='offshore' else '^',linestyle='none',
                            label=k.title(),markersize=4) for k in ['offshore','onshore']],loc='best')
    return save(fig,path)

def stl_panel(summary,path):
    fig,ax=plt.subplots(figsize=(3.5433071,2.9527559))
    fig.subplots_adjust(left=.18,right=.97,bottom=.18,top=.97)
    paired=summary.dropna(subset=['stl_daily','stl_weekly'])
    for x,col in enumerate(['stl_daily','stl_weekly']):
        vals=paired[col].to_numpy()
        if len(vals):
            ax.boxplot([vals],positions=[x],widths=.52,showfliers=False,patch_artist=True,
                       manage_ticks=False,boxprops={'facecolor':'#C8CCDF','linewidth':.7},
                       medianprops={'color':'#252525','linewidth':1.1},
                       whiskerprops={'linewidth':.7},capprops={'linewidth':.7})
        for kind in ['offshore','onshore']:
            values=paired.loc[paired.site_type.eq(kind),col].to_numpy()
            ax.scatter(x+categorical_offsets(len(values),.34),values,s=9,color=COLORS[kind],alpha=.65,
                       marker='o' if kind=='offshore' else '^',linewidths=0)
    ax.set(xticks=[0,1],xticklabels=['Daily (24 h)','Weekly (168 h)'],ylim=(0,1),ylabel='STL seasonal strength')
    ax.legend(handles=[Line2D([],[],color=COLORS[k],marker='o' if k=='offshore' else '^',linestyle='none',
                            label=k.title(),markersize=4) for k in ['offshore','onshore']],loc='upper right')
    return save(fig,path)

def umap_panel(result,path):
    daily=result['daily']
    if not {'umap_1','umap_2','pattern'}<=set(daily):raise ValueError('Missing UMAP or daily-profile groups')
    codes=daily.pattern.str.extract(r'(\d+)')[0].astype(int).to_numpy()
    fig,ax=plt.subplots(figsize=(3.5433071,3.1496063))
    fig.subplots_adjust(left=.17,right=.77,bottom=.15,top=.96)
    scatter=ax.scatter(daily.umap_1,daily.umap_2,c=codes,cmap='plasma',s=1.3,linewidths=0,
                       alpha=.7,rasterized=True,vmin=.5,vmax=max(codes)+.5)
    ax.set(xlabel='UMAP 1',ylabel='UMAP 2',xticks=[],yticks=[])
    cax=fig.add_axes([.82,.17,.035,.75])
    ticks=np.unique(np.linspace(1,max(codes),min(5,max(codes))).round().astype(int))
    fig.colorbar(scatter,cax=cax,ticks=ticks,label='Daily-profile group')
    return save(fig,path,exclude_axes=[cax])

def daily_heatmap(result,path):
    frame=result['farm_hourly_profile'].copy()
    ordering=frame.mean(axis=1).sort_values(kind='stable',na_position='last').index
    frame=frame.reindex(ordering)
    frame.to_csv(path.parent.parent/'tables/f_daily_heatmap_source.csv',encoding='utf-8-sig')
    values=frame.to_numpy()
    finite=values[np.isfinite(values)]
    if not len(finite):raise ValueError('No complete days for the requested daily panel')
    lower=min(0.,float(np.floor(finite.min()/10)*10))
    upper=max(100.,float(np.ceil(finite.max()/10)*10))
    fig,ax=plt.subplots(figsize=(7.2047244,3.5433071))
    fig.subplots_adjust(left=.12,right=.85,bottom=.15,top=.975)
    cmap=plt.get_cmap('plasma').copy();cmap.set_bad('#EEEEEE')
    image=ax.imshow(values,aspect='auto',origin='lower',interpolation='nearest',cmap=cmap,vmin=lower,vmax=upper,
                    extent=[-.5,23.5,.5,len(frame)+.5])
    ticks=sorted(set([1,max(1,len(frame)//2),len(frame)]))
    ax.set(xlabel='Hour of day (UTC)',ylabel='Farms ordered by mean output',
           xticks=[0,4,8,12,16,20,23],yticks=ticks)
    cax=fig.add_axes([.89,.2,.018,.72])
    fig.colorbar(image,cax=cax,label='Mean output (% of rated capacity)')
    return save(fig,path,exclude_axes=[cax])

def median_panel(summary,path):
    fig,ax=plt.subplots(figsize=(3.5433071,2.9527559))
    fig.subplots_adjust(left=.2,right=.975,bottom=.17,top=.97)
    for x,kind in enumerate(['offshore','onshore']):
        values=summary.loc[summary.site_type.eq(kind),'cf_median'].dropna().to_numpy()*100
        violin(ax,values,x,COLORS[kind],width=.6)
        ax.scatter(x+categorical_offsets(len(values)),values,s=11,color=COLORS[kind],linewidths=0,alpha=.7)
    ax.set(xticks=[0,1],xticklabels=['Offshore','Onshore'],ylabel='Median output (% of rated capacity)')
    return save(fig,path)

def volatility_panels(summary,path):
    fig,axes=plt.subplots(1,2,figsize=(7.2047244,3.0708661))
    fig.subplots_adjust(left=.11,right=.985,bottom=.19,top=.96,wspace=.36)
    maximum=summary.mean_hourly_change_pp.max()
    for ax,column,groups,colors in [(axes[0],'capacity_group',['<50 MW','50–150 MW','>150 MW'],SIZE_COLORS),
                                   (axes[1],'site_type',['offshore','onshore'],[COLORS['offshore'],COLORS['onshore']])]:
        for i,(group,color) in enumerate(zip(groups,colors)):
            values=summary.loc[summary[column].eq(group),'mean_hourly_change_pp'].dropna().to_numpy()
            if not len(values):continue
            ax.boxplot([values],positions=[i],widths=.5,patch_artist=True,showfliers=False,manage_ticks=False,
                       boxprops={'facecolor':color,'alpha':.2,'linewidth':.7},
                       medianprops={'color':'#222222','linewidth':1.1},
                       whiskerprops={'linewidth':.7},capprops={'linewidth':.7})
            ax.scatter(i+categorical_offsets(len(values),.3),values,s=10,color=color,linewidths=0,alpha=.75)
        labels=[x.title() for x in groups] if column=='site_type' else groups
        ax.set(xticks=range(len(groups)),xticklabels=labels,
               ylabel='Mean absolute hourly change (pp)',ylim=(0,max(1,maximum*1.12)))
    return save(fig,path)

def plot_revised(result,out,skip_umap=False):
    out=Path(out);folder=out/'figures';folder.mkdir(parents=True,exist_ok=True)
    summary=result['summary']
    # Preserve sample counts and identities outside the artwork.
    paired=summary[['stl_daily','stl_weekly']].notna().all(axis=1)
    counts={'input_farms':len(summary),'mean_output_farms':int(summary.cf_mean.notna().sum()),
            'median_output_farms':int(summary.cf_median.notna().sum()),
            'stl_paired_farms':int(paired.sum()),
            'stl_excluded_farms':summary.loc[~paired,'dataset_id'].tolist(),
            'daily_heatmap_farms_with_days':int(result['farm_hourly_profile'].notna().any(axis=1).sum()),
            'umap_days':0 if skip_umap else len(result['daily']),
            'volatility_farms':int(summary.mean_hourly_change_pp.notna().sum())}
    (out/'tables/panel_sample_counts.json').write_text(json.dumps(counts,indent=2),encoding='utf-8')
    files=[output_panel(summary,folder/'original_b_mean_output'),
           stl_panel(summary,folder/'original_d_seasonal_strength'),
           daily_heatmap(result,folder/'revised_f_daily_output_heatmap'),
           median_panel(summary,folder/'optional_previous_e_median_output'),
           volatility_panels(summary,folder/'volatility_by_capacity_and_site_type')]
    if not skip_umap:files.append(umap_panel(result,folder/'original_e_daily_profile_umap'))
    return files
