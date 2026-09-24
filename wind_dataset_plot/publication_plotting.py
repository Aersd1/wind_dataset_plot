"""Seven figures requested by the author; raw-data figures are server outputs."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from .revised_plotting import categorical_offsets,COLORS,SIZE_COLORS
from ._panel_alignment import require_matplotlib_panel_alignment

plt.rcParams.update({'font.family':'Arial','font.sans-serif':['Arial','DejaVu Sans'],
    'font.size':7,'axes.labelsize':7,'xtick.labelsize':6.5,'ytick.labelsize':6.5,
    'legend.fontsize':6.5,'legend.frameon':False,'pdf.fonttype':42,'svg.fonttype':'none'})

def save(fig,path):
    fig.canvas.draw()
    require_matplotlib_panel_alignment(fig,json_out=str(path)+'.alignment.json',strict=True,
                                      tolerance_pt=1.5,gutter_tolerance_pt=1.5)
    fig.savefig(path.with_suffix('.pdf'))
    fig.savefig(path.with_suffix('.svg'))
    fig.savefig(path.with_suffix('.png'),dpi=600)
    plt.close(fig)
    return str(path.with_suffix('.pdf'))

def climate_colors(groups):
    ordered=sorted(groups)
    return dict(zip(ordered,plt.get_cmap('plasma')(np.linspace(.05,.9,max(1,len(ordered))))))

def equipment_plot(meta,equipment,out):
    out=Path(out);folder=out/'figures';folder.mkdir(parents=True,exist_ok=True)
    selected=equipment[equipment.dataset_id.isin(meta.dataset_id)].copy()
    fig,axes=plt.subplots(1,2,figsize=(7.2047244,2.519685))
    fig.subplots_adjust(left=.12,right=.98,bottom=.22,top=.97,wspace=.22)
    source=[];counts=[]
    for ax,field,label in zip(axes,['rotor_m','hub_m'],['Rotor diameter (m)','Hub height (m)']):
        for y,kind in enumerate(['offshore','onshore']):
            ids=sorted(meta.loc[meta.site_type.eq(kind)&~meta.is_virtual,'dataset_id'])
            n_valid=0
            for offset,identifier in zip(categorical_offsets(len(ids),.5),ids):
                g=selected[selected.dataset_id.eq(identifier)&selected.record_kind.eq('unit_group')]
                vals=np.sort(g[field].dropna().unique())
                if not len(vals):continue
                n_valid+=1
                ax.scatter(vals,np.full(len(vals),y+offset),s=14,facecolors=COLORS[kind],edgecolors=COLORS[kind],
                    marker='o' if kind=='offshore' else '^',linewidths=.5,alpha=.8)
                for v in vals:source.append({'dataset_id':identifier,'site_type':kind,'parameter':field,'value_m':v,
                    'basis':'recorded_equipment'})
            counts.append({'parameter':field,'site_type':kind,'eligible_recorded_farms':len(ids),'shown_farms':n_valid,
                           'visual_unit':'Farm-specific equipment specification','reference_models_displayed':False})
        ax.set(xlabel=label,ylim=(1.5,-.5),yticks=[0,1])
        ax.tick_params(axis='y',length=0)
        ax.spines['left'].set_visible(False)
    axes[0].set_yticklabels(['Offshore','Onshore'])
    axes[1].set_yticklabels([])
    pd.DataFrame(source).to_csv(out/'tables/equipment_distribution_source.csv',index=False)
    (out/'tables/equipment_counts.json').write_text(json.dumps(counts,indent=2),encoding='utf-8')
    return save(fig,folder/'01_rotor_diameter_and_hub_height')

def volatility_scatter(summary,path,by):
    fig,ax=plt.subplots(figsize=(3.5433071,3.0708661))
    fig.subplots_adjust(left=.2,right=.97,bottom=.18,top=.84)
    groups=['offshore','onshore'] if by=='site_type' else ['<50 MW','50–150 MW','>150 MW']
    colors=[COLORS[x] for x in groups] if by=='site_type' else SIZE_COLORS
    markers=['o','^'] if by=='site_type' else ['o','s','^']
    for group,color,marker in zip(groups,colors,markers):
        g=summary[summary[by].eq(group)]
        ax.scatter(g.cf_mean*100,g.mean_hourly_change_pp,color=color,marker=marker,
                   s=16,alpha=.8,linewidths=.3,edgecolors='white',label=group.title() if by=='site_type' else group)
    ax.set(xlabel='Mean output (% of rated capacity)',ylabel='Mean absolute hourly change (pp)',xlim=(0,100),ylim=(0,None))
    ax.legend(loc='lower center',bbox_to_anchor=(.5,1.02),ncol=len(groups),handletextpad=.25,columnspacing=.7)
    return save(fig,path)

def pooled_plot(result,path):
    density=result['pooled_density'];y=density.cf.to_numpy()
    width=density.density.to_numpy()/density.density.max()*.42
    fig,ax=plt.subplots(figsize=(3.5433071,3.3464567))
    fig.subplots_adjust(left=.19,right=.96,bottom=.16,top=.98)
    ax.fill_betweenx(y,-width,width,color='#9CB9D7',alpha=.6,lw=.8,edgecolor='#6889AE')
    summary=result['summary']
    for kind,marker in [('offshore','o'),('onshore','^')]:
        g=summary[summary.site_type.eq(kind)]
        ax.scatter(categorical_offsets(len(g),.3),g.cf_mean,s=12,edgecolors=COLORS[kind],facecolors='none',
                   marker=marker,linewidths=.65,alpha=.8)
    ax.plot([-.2,.2],[result['pooled_mean']]*2,color='#202020',lw=1.2)
    ax.set(xlim=(-.55,.55),ylim=(0,1.04),ylabel='Capacity factor',xticks=[0],xticklabels=['All farms'],yticks=np.arange(0,1.01,.2))
    return save(fig,path)

def climate_umap(result,path):
    daily=result['daily'];colors=climate_colors(daily.climate_group.unique())
    fig,ax=plt.subplots(figsize=(7.2047244,4.7244094))
    fig.subplots_adjust(left=.1,right=.98,bottom=.3,top=.98)
    # Mix drawing order deterministically; every eligible day remains unchanged.
    order=np.argsort((np.arange(len(daily),dtype=float)*.61803398875)%1,kind='stable')
    frame=daily.iloc[order]
    ax.scatter(frame.umap_1,frame.umap_2,c=[colors[x] for x in frame.climate_group],s=1.1,alpha=.6,
               linewidths=0,rasterized=True)
    ax.set(xlabel='UMAP 1',ylabel='UMAP 2',xticks=[],yticks=[])
    handles=[Line2D([],[],marker='o',linestyle='none',color=c,markersize=4,label=g) for g,c in colors.items()]
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.53,.015),ncol=3,
               columnspacing=1.4,handletextpad=.35)
    return save(fig,path)

def daily_panels(result,path,by='climate'):
    table=result['climate_profiles'] if by=='climate' else result['pattern_profiles']
    column='climate_group' if by=='climate' else 'pattern'
    groups=sorted(table[column].unique())
    if not groups:raise ValueError('No complete days for daily panels')
    ncols=min(len(groups),3 if by=='climate' else 4);nrows=int(np.ceil(len(groups)/ncols))
    colors=climate_colors(groups)
    height=max(2.6,nrows*1.6)
    fig,axes=plt.subplots(nrows,ncols,figsize=(7.2047244,height),squeeze=False)
    fig.subplots_adjust(left=.1,right=.98,bottom=.42/height,top=1-.32/height,hspace=.58,wspace=.25)
    for i,(ax,group) in enumerate(zip(axes.flat,groups)):
        g=table[table[column].eq(group)].sort_values('hour_utc')
        ax.fill_between(g.hour_utc,g.q25_cf*100,g.q75_cf*100,color=colors[group],alpha=.2,lw=0)
        ax.plot(g.hour_utc,g.median_cf*100,color=colors[group],lw=1.2)
        label=group.replace(' / ',' /\n')
        ax.text(0,1.04,label,transform=ax.transAxes,ha='left',va='bottom',fontsize=7)
        ax.set(xlim=(0,23),ylim=(0,100),xticks=[0,6,12,18,23],yticks=[0,50,100])
        if i % ncols:ax.set_yticklabels([])
        if i//ncols<nrows-1:ax.set_xticklabels([])
    for ax in list(axes.flat)[len(groups):]:fig.delaxes(ax)
    fig.supxlabel('Hour of day (UTC)',fontsize=7,y=.06/height)
    fig.supylabel('Output (% of rated capacity)',fontsize=7,x=.015)
    return save(fig,path)

def periodicity_plot(summary,path):
    fig,ax=plt.subplots(figsize=(3.5433071,3.0708661))
    fig.subplots_adjust(left=.18,right=.97,bottom=.18,top=.84)
    paired=summary.dropna(subset=['stl_daily','stl_weekly'])
    for i,column in enumerate(['stl_daily','stl_weekly']):
        values=paired[column].to_numpy()
        if len(values):
            ax.boxplot([values],positions=[i],widths=.5,showfliers=False,manage_ticks=False,patch_artist=True,
                       boxprops={'facecolor':'#D9DCE8','linewidth':.7},medianprops={'color':'#222222','linewidth':1.1},
                       whiskerprops={'linewidth':.7},capprops={'linewidth':.7})
        for kind,marker in [('offshore','o'),('onshore','^')]:
            vals=paired.loc[paired.site_type.eq(kind),column].to_numpy()
            ax.scatter(i+categorical_offsets(len(vals),.3),vals,s=12,color=COLORS[kind],marker=marker,alpha=.8,linewidths=0,zorder=3)
    ax.set(xticks=[0,1],xticklabels=['Daily (24 h)','Weekly (168 h)'],ylabel='STL seasonal strength',ylim=(0,1),xlim=(-.6,1.6))
    handles=[Line2D([],[],marker=m,color=COLORS[k],linestyle='none',markersize=4,label=k.title())
             for k,m in [('offshore','o'),('onshore','^')]]
    ax.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,1.02),ncol=2,columnspacing=1)
    return save(fig,path)

def plot_publication(result,meta,equipment,out,daily_by):
    folder=Path(out)/'figures';folder.mkdir(parents=True,exist_ok=True)
    summary=result['summary']
    counts={'farms':len(summary),'scatter_valid_farms':int(summary[['cf_mean','mean_hourly_change_pp']].notna().all(axis=1).sum()),
            'periodicity_paired_farms':int(summary[['stl_daily','stl_weekly']].notna().all(axis=1).sum()),
            'complete_days':len(result['daily']),'climate_groups':result['daily'].climate_group.value_counts().to_dict(),
            'daily_panel_weighting':'Equal farms after per-farm averaging across complete days' if daily_by=='climate' else 'All complete days within each profile cluster'}
    (Path(out)/'tables/panel_sample_counts.json').write_text(json.dumps(counts,indent=2),encoding='utf-8')
    return [equipment_plot(meta,equipment,out),
        volatility_scatter(summary,folder/'02_volatility_onshore_offshore','site_type'),
        volatility_scatter(summary,folder/'03_volatility_capacity_groups','capacity_group'),
        pooled_plot(result,folder/'04_pooled_capacity_factor_distribution'),
        climate_umap(result,folder/'05_daily_profiles_umap_by_climate'),
        daily_panels(result,folder/'06_daily_power_panels',daily_by),
        periodicity_plot(summary,folder/'07_daily_weekly_periodicity')]
