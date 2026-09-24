"""Recompute requested temporal panels using explicit equipment-based capacities.

All retained segments of a manifest farm remain one statistical unit.
No existing PNG, standardized training JSON or observed power maximum is a data source.
"""
from pathlib import Path
import argparse
import hashlib
import json
import logging
import numpy as np
import pandas as pd
from .config import load_config
from .manifests import read_plan, discover_manifest
from .analysis import analyze


def size_group(mw):
    if not np.isfinite(mw) or mw <= 0:
        raise ValueError('Rated capacity must be positive and finite')
    return '<50 MW' if mw < 50 else ('50–150 MW' if mw <= 150 else '>150 MW')


def prepare(cfg, access_files=True):
    if cfg['inputs']['segment_layer'] != 'aligned_segments':
        raise ValueError('The revised analysis requires aligned_segments only')
    farms, report=read_plan(cfg)
    if report['capacity_proxy_farms']:
        raise ValueError('Observed-maximum capacity proxies are not permitted')
    if any('xlsx_equipment_count_times_rated_kw' not in f['capacity_source'] for f in farms):
        raise ValueError('Use the recalculated equipment capacity table')
    if not access_files:
        return farms,report
    datasets,_=discover_manifest(cfg)
    for ds in datasets:
        ds.capacity_kw=ds.provenance['capacity_kw']
        ds.site_type=ds.provenance['capacity_table_site_type']
        if ds.site_type not in ('onshore','offshore'):
            raise ValueError(f'{ds.id}: missing site type in the equipment table')
    return datasets,report


def derived_tables(result):
    summary=result['summary'].copy()
    summary['rated_capacity_mw']=summary.capacity_kw/1000
    summary['capacity_group']=summary.rated_capacity_mw.map(size_group)
    summary['mean_hourly_change_pp']=summary.ramp_mean*100
    summary['large_hourly_change_pp']=summary.ramp_p95*100
    result['summary']=summary
    daily=result['daily'].copy()
    profiles=np.asarray(result['profiles'])
    if profiles.shape != (len(daily),24):
        raise ValueError('Daily profile identities and 24-hour vectors disagree')
    profiles_frame=pd.DataFrame(profiles,columns=[f'hour_{h:02}' for h in range(24)])
    profiles_frame.insert(0,'dataset_id',daily.dataset_id.to_numpy())
    # One farm contributes one row; averaging is across its complete retained UTC days.
    hourly=profiles_frame.groupby('dataset_id',sort=False).mean().reindex(summary.dataset_id)*100
    hourly.index.name='dataset_id'
    daily['site_type']=daily.dataset_id.map(summary.set_index('dataset_id').site_type)
    daily['rated_capacity_mw']=daily.dataset_id.map(summary.set_index('dataset_id').rated_capacity_mw)
    result['daily']=daily
    result['farm_hourly_profile']=hourly
    rows=[]
    for category in ['site_type','capacity_group']:
        for group,g in summary.groupby(category,sort=False):
            v=g.mean_hourly_change_pp.dropna()
            rows.append({'group_type':category,'group':group,'farms':len(g),'valid_farms':len(v),
                         'median_mean_hourly_change_pp':v.median(),
                         'q25':v.quantile(.25),'q75':v.quantile(.75)})
    result['volatility_groups']=pd.DataFrame(rows)
    return result


def embed_profiles(result,seed):
    import umap
    vectors=np.asarray(result['profiles'],dtype=np.float32)
    if len(vectors)<4 or len(np.unique(vectors,axis=0))<3:
        raise ValueError('UMAP requires at least four days and three distinct daily profiles')
    # Every eligible farm-day is embedded; no plotting subsample is taken.
    model=umap.UMAP(n_components=2,n_neighbors=min(30,len(vectors)-1),min_dist=.12,
                    metric='euclidean',random_state=seed,n_jobs=1)
    xy=model.fit_transform(vectors)
    result['daily']['umap_1']=xy[:,0]
    result['daily']['umap_2']=xy[:,1]
    return result


def save_tables(result,cfg,report,out):
    tables=out/'tables';tables.mkdir(parents=True,exist_ok=True)
    for key,name in [('summary','dataset_summary'),('audit','quality_audit'),('files','file_audit'),
                     ('daily','daily_profiles_index'),('patterns','daily_pattern_summary'),
                     ('candidates','cluster_selection'),('volatility_groups','volatility_groups')]:
        result[key].to_csv(tables/f'{name}.csv',index=False,encoding='utf-8-sig')
    result['farm_hourly_profile'].to_csv(tables/'farm_hourly_mean_percent.csv',encoding='utf-8-sig')
    pd.DataFrame(result['medians'],columns=[f'hour_{h:02}' for h in range(24)]).to_csv(
        tables/'daily_pattern_medians.csv',index=False)
    np.savez_compressed(tables/'daily_profiles.npz',profiles=result['profiles'])
    source_mix=pd.crosstab(result['summary'].capacity_group,
                          result['summary'].dataset_id.str.startswith('NREL_WTK_').map({True:'NREL WTK',False:'Other sources'}))
    source_mix.to_csv(tables/'capacity_group_source_composition.csv',encoding='utf-8-sig')
    metadata={'input_report':report,'config':cfg,
              'capacity_sha256':hashlib.sha256(Path(cfg['inputs']['capacity_table']).read_bytes()).hexdigest(),
              'analysis_unit':'One original manifest farm, independent of number of retained segments',
              'daily_clock':'UTC; not local solar time',
              'volatility':'mean(abs(P[t+1]-P[t])) / rated_capacity * 100; consecutive complete hours only',
              'capacity_boundaries':'<50 MW; 50–150 MW inclusive; >150 MW',
              'b_statistic':'Distribution of per-farm mean hourly output, not a pooled hourly distribution',
              'f_statistic':'Per-farm mean output at each UTC hour across complete retained days',
              'group_interpretation':'Descriptive; size groups may have different source composition',
              'umap':'All retained complete days, Euclidean distance on 24 hourly capacity-normalized values',
              'stl':'Independent period-24 and period-168 fits; weekly score is not a residual weekly component',
              'figures_recomputed':False}
    (out/'run_manifest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    return metadata


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',required=True)
    p.add_argument('--inspect',action='store_true',help='Validate manifests/capacities without opening time-series files')
    p.add_argument('--overwrite',action='store_true')
    p.add_argument('--skip-umap',action='store_true',help='Explicitly omit original panel e, useful for initial server checks')
    args=p.parse_args(argv)
    logging.basicConfig(level=logging.INFO,format='%(levelname)s: %(message)s')
    logging.getLogger('fontTools').setLevel(logging.WARNING)
    cfg=load_config(args.config)
    cfg['plots'].update(layout='legacy',panels=['b','d','e','f'])
    cfg['analysis']['max_daily_profiles_per_dataset']=0
    cfg['analysis']['max_stl_windows']=0
    cfg['analysis']['cluster_fit_limit']=2**31-1
    if cfg['analysis']['clock_timezone']!='UTC':
        raise ValueError('Revised farm-day plots currently require UTC')
    datasets,report=prepare(cfg,access_files=not args.inspect)
    if args.inspect:
        print(json.dumps(report,ensure_ascii=False,indent=2));return 0
    out=Path(cfg['output_dir'])
    if out.exists() and any(out.iterdir()) and not args.overwrite:
        raise ValueError('Output folder is not empty; use a new folder or --overwrite')
    out.mkdir(parents=True,exist_ok=True)
    result=derived_tables(analyze(datasets,cfg))
    metadata=save_tables(result,cfg,report,out)
    if not args.skip_umap:
        result=embed_profiles(result,cfg['analysis']['seed'])
        result['daily'].to_csv(out/'tables/daily_profiles_index.csv',index=False,encoding='utf-8-sig')
    from .revised_plotting import plot_revised
    files=plot_revised(result,out,skip_umap=args.skip_umap)
    metadata['figures_recomputed']=True
    metadata['skipped_panels']=['original_e_umap'] if args.skip_umap else []
    metadata['figures']=files
    (out/'run_manifest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    logging.info('Completed %d original farms; outputs: %s',len(datasets),out)
    return 0

if __name__=='__main__':
    raise SystemExit(main())
