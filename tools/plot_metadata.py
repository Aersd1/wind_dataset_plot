"""Figures backed only by recalculated metadata and supplied forecasting results."""
from pathlib import Path
import argparse
import json
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

COLORS={'offshore':'#6500A8','onshore':'#EB7754'}
SIZE_COLORS=['#6500A8','#B53679','#FCA636']
plt.rcParams.update({'font.family':'Arial','font.size':7,'axes.labelsize':7,
                     'xtick.labelsize':6.5,'ytick.labelsize':6.5,'legend.fontsize':6.5,
                     'axes.spines.top':False,'axes.spines.right':False,
                     'axes.linewidth':.65,'xtick.major.width':.65,'ytick.major.width':.65,'legend.frameon':False,
                     'pdf.fonttype':42,'svg.fonttype':'none','savefig.facecolor':'white'})

def export(fig, path, qa_dir, exclude_axes=None):
    sys.path.insert(0,str(qa_dir))
    from audit_panel_alignment import require_matplotlib_panel_alignment
    fig.canvas.draw()
    require_matplotlib_panel_alignment(fig,json_out=str(path)+'.alignment.json',
                                      tolerance_pt=1.5,gutter_tolerance_pt=1.5,
                                      exclude_axes=exclude_axes or [],strict=True)
    fig.savefig(path.with_suffix('.pdf'))
    fig.savefig(path.with_suffix('.svg'))
    fig.savefig(path.with_suffix('.png'),dpi=600)
    plt.close(fig)

def capacity_figure(farms, out, qa):
    fig,ax=plt.subplots(figsize=(3.5433071,2.7559055))
    fig.subplots_adjust(left=.17,right=.98,bottom=.18,top=.97)
    for kind in ['offshore','onshore']:
        x=np.sort(farms.loc[farms.site_type.eq(kind),'rated_capacity_mw'].to_numpy())
        if not len(x): continue
        if np.any(x<=0): raise ValueError('Log capacity axis requires positive values')
        unique,count=np.unique(x,return_counts=True)
        ax.step(np.r_[unique[0],unique],np.r_[0,np.cumsum(count)/len(x)*100],where='post',
                color=COLORS[kind],lw=1.4,label=kind.title())
    ax.set_xscale('log')
    ax.set(ylim=(0,102),xlim=(1.6,800),xlabel='Farm rated capacity (MW)',
           ylabel='Farms at or below this capacity (%)')
    ax.set_xticks([2,10,50,150,600],labels=['2','10','50','150','600'])
    ax.set_yticks([0,25,50,75,100])
    ax.legend(loc='upper left')
    export(fig,out/'rated_capacity_distribution',qa)

def geometry_figure(farms, equipment, out, qa):
    included=set(farms.loc[~farms.is_virtual,'dataset_id'])
    equipment=equipment[equipment.dataset_id.isin(included) & equipment.record_kind.eq('unit_group')]
    fig,axes=plt.subplots(1,3,figsize=(7.2047244,2.7165354))
    fig.subplots_adjust(left=.105,right=.985,bottom=.23,top=.965,wspace=.43)
    counts={}
    for ax,field,label,limits in zip(axes,['rotor_m','blade_m','hub_m'],
                                    ['Rotor diameter (m)','Blade length (m)','Hub height (m)'],
                                    [(55,180),(25,90),(50,115)]):
        valid_ids=set()
        for j,kind in enumerate(['offshore','onshore']):
            g=equipment[equipment.site_type.eq(kind)]
            ids=sorted(g.dataset_id.unique())
            offsets=np.linspace(-.24,.24,max(len(ids),1))
            for offset,identifier in zip(offsets,ids):
                vals=np.sort(g.loc[g.dataset_id.eq(identifier),field].dropna().unique())
                if not len(vals):continue
                valid_ids.add(identifier)
                y=j+offset
                if len(vals)>1:ax.plot([vals.min(),vals.max()],[y,y],color=COLORS[kind],lw=.65,alpha=.65)
                ax.scatter(vals,np.full(len(vals),y),s=11,color=COLORS[kind],alpha=.8,
                           linewidths=0,marker='o' if kind=='offshore' else '^')
        ax.set(xlabel=label,yticks=[0,1],yticklabels=['Offshore','Onshore'],ylim=(1.5,-.5),xlim=limits)
        ax.spines['left'].set_visible(False)
        ax.tick_params(axis='y',length=0,pad=4)
        counts[field]={'eligible_actual_farms':len(included),'plotted_farms':len(valid_ids),
                       'missing_farms':sorted(included-valid_ids)}
    export(fig,out/'turbine_geometry_diversity',qa)
    return counts

def reference_figure(equipment,out,qa):
    ref=equipment[equipment.record_kind.eq('reference_model')].copy()
    # These are the finite reference specifications, not counts of installed turbines.
    group_map={}
    for identifier,g in equipment.groupby('dataset_id'):
        units=g[g.record_kind.eq('unit_group')]
        if not units.empty and units.iloc[0].basis=='virtual_turbine':
            group_map[identifier]=str(units.iloc[0].model).replace(' power curve','').replace('IEC ','').title()
    ref['reference_class']=ref.dataset_id.map(group_map)
    ref=ref.drop_duplicates(['reference_class','model','rotor_m','blade_m','hub_m'])
    fig,axes=plt.subplots(1,3,figsize=(7.2047244,2.5984252))
    fig.subplots_adjust(left=.11,right=.985,bottom=.23,top=.965,wspace=.43)
    order=['Class 1','Class 2','Class 3','Offshore']
    for ax,field,label,limits in zip(axes,['rotor_m','blade_m','hub_m'],
                                    ['Reference rotor diameter (m)','Reference blade length (m)','Configured hub height (m)'],
                                    [(70,135),(30,68),(90,110)]):
        for j,kind in enumerate(order):
            vals=sorted(ref.loc[ref.reference_class.eq(kind),field].dropna().unique())
            offsets=np.linspace(-.1,.1,len(vals)) if len(vals)>1 else np.zeros(len(vals))
            ax.scatter(vals,j+offsets,s=20,color='#4F5480',linewidths=0)
        ax.set(yticks=range(4),yticklabels=order,ylim=(3.6,-.6),xlabel=label,xlim=limits)
        ax.tick_params(axis='y',length=0)
        ax.spines['left'].set_visible(False)
    export(fig,out/'virtual_reference_geometry',qa)

def prediction_figure(farms,results,out,qa,tables):
    scores=results[(results.experiment=='zeroshot') & (results.model=='Our Model') &
                   (results.metric=='MSE')].copy()
    metadata=farms[['dataset_id','rated_capacity_mw','capacity_group','site_type','source']]
    scores=scores.merge(metadata,left_on='dataset',right_on='dataset_id',how='left',validate='many_to_one')
    if scores.site_type.isna().any():raise ValueError('Unmatched prediction dataset')
    if scores.duplicated(['dataset','horizon']).any():raise ValueError('Duplicated MSE task')
    scores.to_csv(tables/'zero_shot_group_source.csv',index=False,encoding='utf-8-sig')
    summaries=[]
    fig,axes=plt.subplots(1,2,figsize=(7.2047244,3.2677165))
    fig.subplots_adjust(left=.085,right=.985,bottom=.19,top=.84,wspace=.23)
    for ax,col,groups,colors in [(axes[0],'site_type',['onshore','offshore'],[COLORS['onshore'],COLORS['offshore']]),
                                (axes[1],'capacity_group',['<50 MW','50–150 MW','>150 MW'],SIZE_COLORS)]:
        n=len(groups);width=.66/n
        for k,group in enumerate(groups):
            for j,horizon in enumerate([16,32,48,64]):
                values=scores.loc[scores[col].eq(group)&scores.horizon.eq(horizon),'value'].to_numpy()
                if not len(values):continue
                x=j+(k-(n-1)/2)*width
                bp=ax.boxplot([values],positions=[x],widths=width*.73,patch_artist=True,showfliers=False,
                              manage_ticks=False,boxprops={'facecolor':colors[k],'alpha':.2,'linewidth':.7},
                              medianprops={'color':colors[k],'linewidth':1.2},
                              whiskerprops={'color':colors[k],'linewidth':.7},capprops={'color':colors[k],'linewidth':.7})
                offsets=((np.arange(len(values))*.61803398875)%1-.5)*width*.5
                ax.scatter(x+offsets,values,s=6,color=colors[k],alpha=.65,linewidths=0)
                summaries.append(dict(group_type=col,group=group,horizon=horizon,farms=len(values),
                                      median_mse=float(np.median(values)),q25=float(np.quantile(values,.25)),
                                      q75=float(np.quantile(values,.75))))
        ax.set(xticks=range(4),xticklabels=['16','32','48','64'],xlabel='Prediction length (steps)',
               ylim=(0,.85),yticks=[0,.2,.4,.6,.8],ylabel='Zero-shot prediction error (MSE)')
        ax.legend(handles=[Line2D([],[],marker='o',linestyle='none',markersize=4,color=c,
                                 label=g.title() if col=='site_type' else g) for g,c in zip(groups,colors)],
                  loc='lower center',bbox_to_anchor=(.5,1.03),ncol=len(groups),columnspacing=1.0,handletextpad=.3)
    export(fig,out/'prediction_error_by_updated_groups',qa)
    pd.DataFrame(summaries).to_csv(tables/'zero_shot_group_summary.csv',index=False,encoding='utf-8-sig')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--tables',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--qa-dir',type=Path,required=True)
    p.add_argument('--results',type=Path,required=True)
    p.add_argument('--scope',choices=['manifest131','all'],default='manifest131')
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    farms=pd.read_csv(args.tables/'farm_numeric_metadata.csv')
    if args.scope=='manifest131':farms=farms[farms.in_manifest_131]
    equipment=pd.read_csv(args.tables/'turbine_groups_long.csv')
    capacity_figure(farms,args.output,args.qa_dir)
    counts=geometry_figure(farms,equipment,args.output,args.qa_dir)
    reference_figure(equipment[equipment.dataset_id.isin(farms.dataset_id)],args.output,args.qa_dir)
    prediction_figure(farms,pd.read_csv(args.results),args.output,args.qa_dir,args.tables)
    audit={'scope':args.scope,'farms':len(farms),'geometry':counts,
           'source_counts':farms.source.value_counts().to_dict(),
           'geometry_unit':'Unique equipment specification within a farm; multiple values connected',
           'reference_separation':'Virtual reference rotor/blade specifications are in a separate figure',
           'jitter':'Only categorical-axis offsets; measured dimensional values are not jittered',
           'capacity_distribution':'ECDF; one observation per manifest farm; log capacity axis',
           'forecast_error':'MSE is prediction error, not time-series volatility'}
    (args.output/'figure_audit.json').write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding='utf-8')

if __name__=='__main__': main()
