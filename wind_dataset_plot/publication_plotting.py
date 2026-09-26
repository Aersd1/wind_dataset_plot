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

CLIMATE_ORDER = ('Humid continental', 'Arid / semi-arid', 'Humid subtropical', 'Oceanic', 'Other climates')


def ordered_climates(groups):
    present=set(groups)
    return [g for g in CLIMATE_ORDER if g in present]+sorted(present-set(CLIMATE_ORDER))


def climate_colors(groups):
    present=set(groups)
    if present.issubset(CLIMATE_ORDER):
        palette=dict(zip(CLIMATE_ORDER,plt.get_cmap('plasma')(np.linspace(.05,.9,5))))
        return {g:palette[g] for g in ordered_climates(present)}
    ordered=sorted(present)
    return dict(zip(ordered,plt.get_cmap('plasma')(np.linspace(.05,.9,max(1,len(ordered))))))


def equipment_plot(meta,equipment,out):
    out=Path(out);folder=out/'figures';folder.mkdir(parents=True,exist_ok=True)
    selected=equipment[equipment.dataset_id.isin(meta.dataset_id)].copy()
    fig,axes=plt.subplots(1,2,figsize=(7.2047244,2.0472441))
    fig.subplots_adjust(left=.065,right=.985,bottom=.25,top=.78,wspace=.2)
    all_ids=sorted(meta.loc[~meta.is_virtual,'dataset_id'])
    offsets=dict(zip(all_ids,categorical_offsets(len(all_ids),.5)))
    source=[];counts=[]
    for ax,field,label in zip(axes,['rotor_m','hub_m'],['Rotor diameter (m)','Hub height (m)']):
        for kind in ['offshore','onshore']:
            ids=sorted(meta.loc[meta.site_type.eq(kind)&~meta.is_virtual,'dataset_id'])
            n_valid=0
            for identifier in ids:
                g=selected[selected.dataset_id.eq(identifier)&selected.record_kind.eq('unit_group')]
                vals=np.sort(g[field].dropna().unique())
                if not len(vals):continue
                n_valid+=1
                ax.scatter(vals,np.full(len(vals),offsets[identifier]),s=14,facecolors=COLORS[kind],edgecolors=COLORS[kind],
                    marker='o' if kind=='offshore' else '^',linewidths=.5,alpha=.8)
                for v in vals:source.append({'dataset_id':identifier,'site_type':kind,'parameter':field,'value_m':v,
                    'basis':'recorded_equipment'})
            counts.append({'parameter':field,'site_type':kind,'eligible_recorded_farms':len(ids),'shown_farms':n_valid,
                           'visual_unit':'Farm-specific equipment specification','reference_models_displayed':False})
        ax.set(xlabel=label,ylim=(-.4,.4),yticks=[])
        ax.tick_params(axis='y',length=0)
        ax.spines['left'].set_visible(False)
    handles=[Line2D([],[],marker=marker,color=COLORS[kind],linestyle='none',markersize=4,label=kind.title())
             for kind,marker in [('offshore','o'),('onshore','^')]]
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.525,.99),ncol=2,
               columnspacing=1.8,handletextpad=.4)
    pd.DataFrame(source).to_csv(out/'tables/equipment_distribution_source.csv',index=False)
    (out/'tables/equipment_counts.json').write_text(json.dumps(counts,indent=2),encoding='utf-8')
    return save(fig,folder/'01_rotor_diameter_and_hub_height')

def volatility_scatter(summary,path,by):
    """Farm-level grouped dots. Group median and interquartile range stay in the CSV only."""
    fig,ax=plt.subplots(figsize=(3.5433071,3.0708661))
    fig.subplots_adjust(left=.25,right=.98,bottom=.19,top=.97)
    groups=['offshore','onshore'] if by=='site_type' else ['<50 MW','50–150 MW','>150 MW']
    colors=[COLORS[x] for x in groups] if by=='site_type' else SIZE_COLORS
    markers=['o','^'] if by=='site_type' else ['o','s','^']
    rows=[]
    for x,(group,color,marker) in enumerate(zip(groups,colors,markers)):
        g=summary[summary[by].eq(group)].sort_values('dataset_id')
        values=g.mean_hourly_change_pp.to_numpy(dtype=float)
        values=values[np.isfinite(values)]
        row={'group':group,'farms_total':len(g),'farms_plotted':len(values),
             'excluded_undefined_metric':len(g)-len(values)}
        if len(values):
            ax.scatter(x-.07+categorical_offsets(len(values),.42),values,color=color,marker=marker,
                       s=13,alpha=.75,linewidths=.3,edgecolors='white',zorder=3)
            q25,median,q75=np.quantile(values,[.25,.5,.75])
            row.update(q25=q25,median=median,q75=q75)
        rows.append(row)
    labels=['Offshore','Onshore'] if by=='site_type' else groups
    finite=summary.mean_hourly_change_pp.to_numpy(dtype=float)
    finite=finite[np.isfinite(finite)]
    upper=max(1,float(finite.max())*1.08) if len(finite) else 1
    ax.set(xticks=range(len(groups)),xticklabels=labels,xlim=(-.55,len(groups)-.45),ylim=(0,upper),
           xlabel='Farm type' if by=='site_type' else 'Rated farm capacity',
           ylabel='Mean absolute hourly change\n(% of rated capacity)')
    ax.spines[['top','right']].set_visible(False)
    ax.spines[['left','bottom']].set_linewidth(1)
    ax.tick_params(width=1)
    pd.DataFrame(rows).to_csv(path.with_name(path.name+'_group_summary.csv'),index=False)
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

def climate_profile_similarity(result,path):
    """One point per farm. Proximity is Euclidean similarity of the 24-hour mean profile.

    Principal components are the classical scaling of that distance. Climate
    colors the points and is not used to place them.
    """
    from sklearn.decomposition import PCA
    profile=result['farm_hourly_profile']
    hours=[column for column in profile.columns if str(column).startswith('hour_')]
    values=profile[hours].to_numpy(dtype=float)/100
    model=PCA(n_components=2,svd_solver='full').fit(values)
    xy=model.transform(values)
    if np.corrcoef(xy[:,0],values.mean(axis=1))[0,1]<0:
        xy[:,0]*=-1;model.components_[0]*=-1
    afternoon=values[:,16:20].mean(axis=1)-values[:,2:7].mean(axis=1)
    if np.corrcoef(xy[:,1],afternoon)[0,1]<0:
        xy[:,1]*=-1;model.components_[1]*=-1
    climates=result['summary'].set_index('dataset_id').climate_group.reindex(profile.index)
    frame=pd.DataFrame({'dataset_id':profile.index,'climate_group':climates.to_numpy(),
                        'pc1':xy[:,0],'pc2':xy[:,1],'mean_cf':values.mean(axis=1)})
    colors=climate_colors(frame.climate_group.unique())
    fig,ax=plt.subplots(figsize=(7.2047244,4.7244094))
    fig.subplots_adjust(left=.12,right=.98,bottom=.22,top=.96)
    for group,color in colors.items():
        g=frame[frame.climate_group.eq(group)]
        ax.scatter(g.pc1,g.pc2,s=36,color=color,alpha=.92,linewidths=.4,edgecolors='white',zorder=3)
    share=model.explained_variance_ratio_
    ax.set(xlabel=f'PC1 ({share[0]*100:.0f}% of profile variance)',
           ylabel=f'PC2 ({share[1]*100:.0f}% of profile variance)')
    ax.spines[['top','right']].set_visible(False)
    handles=[Line2D([],[],marker='o',linestyle='none',color=c,markersize=5,label=g) for g,c in colors.items()]
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.55,.02),ncol=3,
               columnspacing=1.4,handletextpad=.35)
    tables=path.parent.parent/'tables'
    frame.to_csv(tables/'farm_profile_similarity.csv',index=False)
    pd.DataFrame(model.components_,columns=hours,index=['pc1','pc2']).to_csv(tables/'farm_profile_similarity_loadings.csv')
    (tables/'farm_profile_similarity.json').write_text(json.dumps({
        'method':'PCA of the 24-hour mean capacity-factor profile, one row per farm',
        'distance':'Euclidean distance among those profiles; the first two components are its classical scaling',
        'explained_variance_ratio':[float(x) for x in share],
        'pc1_correlation_with_mean_cf':float(np.corrcoef(xy[:,0],values.mean(axis=1))[0,1]),
        'pc2_correlation_with_afternoon_minus_morning':float(np.corrcoef(xy[:,1],afternoon)[0,1]),
        'climate':'Color only; climate is not an input to the coordinates'},indent=2))
    return save(fig,path)

def _draw_daily_curve(ax,hours,low,median,high,color):
    ax.fill_between(hours,low,high,color=color,alpha=.22,lw=0)
    ax.plot(hours,median,color=color,lw=1.2)
    ax.set(xlim=(0,23),ylim=(0,100),xticks=[0,6,12,18,23],yticks=[0,50,100])

def daily_panels(result,path,by='climate'):
    table=result['climate_profiles'] if by=='climate' else result['pattern_profiles']
    column='climate_group' if by=='climate' else 'pattern'
    groups=ordered_climates(table[column].unique()) if by=='climate' else sorted(table[column].unique())
    if not groups:raise ValueError('No complete days for daily panels')
    ncols=len(groups) if by=='climate' else min(len(groups),4)
    nrows=int(np.ceil(len(groups)/ncols))
    colors=climate_colors(groups)
    height=2.55 if by=='climate' else max(2.6,nrows*1.6)
    fig,axes=plt.subplots(nrows,ncols,figsize=(7.2047244,height),squeeze=False)
    if by=='climate':
        fig.subplots_adjust(left=.075,right=.985,bottom=.2,top=.8,wspace=.32)
    else:
        fig.subplots_adjust(left=.1,right=.98,bottom=.42/height,top=1-.32/height,hspace=.58,wspace=.25)
    for i,(ax,group) in enumerate(zip(axes.flat,groups)):
        g=table[table[column].eq(group)].sort_values('hour_utc')
        _draw_daily_curve(ax,g.hour_utc,g.q25_cf*100,g.median_cf*100,g.q75_cf*100,colors[group])
        ax.set_title(group,fontsize=6.5,pad=3,loc='left')
        if i % ncols:ax.set_yticklabels([])
        if i//ncols<nrows-1:ax.set_xticklabels([])
    for ax in list(axes.flat)[len(groups):]:fig.delaxes(ax)
    fig.supxlabel('Hour of day (UTC)',fontsize=7,y=.045 if by=='climate' else .06/height)
    fig.supylabel('Output (% of rated capacity)',fontsize=7,x=.012 if by=='climate' else .015)
    return save(fig,path)

def farm_daily_panels(result,selection,path):
    """Two rows of per-farm daily curves. Each panel is one dataset."""
    daily=result['daily']
    profiles=np.asarray(result['profiles'],dtype=float)
    grouped={}
    for index,farm in enumerate(daily.dataset_id.to_numpy()):
        grouped.setdefault(farm,[]).append(index)
    colors=climate_colors([item['climate_group'] for item in selection])
    ncols,nrows=6,2
    if len(selection)!=ncols*nrows:raise ValueError('This figure is laid out as two rows of six farms')
    fig,axes=plt.subplots(nrows,ncols,figsize=(7.2047244,3.7),squeeze=False)
    fig.subplots_adjust(left=.07,right=.985,bottom=.14,top=.86,hspace=.62,wspace=.28)
    hours=np.arange(24)
    for i,(ax,item) in enumerate(zip(axes.flat,selection)):
        block=profiles[grouped[item['dataset_id']]]
        median=np.median(block,axis=0)*100
        low=np.quantile(block,.25,axis=0)*100
        high=np.quantile(block,.75,axis=0)*100
        _draw_daily_curve(ax,hours,low,median,high,colors[item['climate_group']])
        ax.set_title(item['label'],fontsize=6.5,pad=2,loc='left')
        if i % ncols:ax.set_yticklabels([])
        if i//ncols<nrows-1:ax.set_xticklabels([])
    fig.supxlabel('Hour of day (UTC)',fontsize=7,y=.02)
    fig.supylabel('Output (% of rated capacity)',fontsize=7,x=.01)
    handles=[Line2D([],[],color=c,lw=1.4,label=g) for g,c in colors.items()]
    fig.legend(handles=handles,loc='upper center',bbox_to_anchor=(.53,.995),ncol=5,
               columnspacing=.8,handletextpad=.35)
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
            'daily_panel_weighting':'Equal farms: median of farm-mean profiles; band is the median of each farm day-level interquartile range' if daily_by=='climate' else 'All complete days within each profile cluster'}
    (Path(out)/'tables/panel_sample_counts.json').write_text(json.dumps(counts,indent=2),encoding='utf-8')
    return [equipment_plot(meta,equipment,out),
        volatility_scatter(summary,folder/'02_volatility_onshore_offshore','site_type'),
        volatility_scatter(summary,folder/'03_volatility_capacity_groups','capacity_group'),
        pooled_plot(result,folder/'04_pooled_capacity_factor_distribution'),
        climate_profile_similarity(result,folder/'05_farm_profile_similarity'),
        daily_panels(result,folder/'06_daily_power_panels',daily_by),
        periodicity_plot(summary,folder/'07_daily_weekly_periodicity')]
