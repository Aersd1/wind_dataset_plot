"""Requested publication figures: compute raw-power statistics on the server only."""
from pathlib import Path
import argparse
import hashlib
import json
import logging
import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter1d
from .analysis import analyze, cluster_profiles
from .config import load_config
from .revised import prepare, derived_tables, embed_profiles

LOG=logging.getLogger(__name__)
EPS=1e-9  # Floating-point comparison only; not a physical exceedance allowance.

def climate_metadata(table,mapping,ids):
    meta=pd.read_csv(table)
    if meta.dataset_id.duplicated().any():raise ValueError('Duplicate metadata farm IDs')
    meta=meta.set_index('dataset_id').reindex(ids)
    if meta.climate.isna().any():raise ValueError('Missing farm climate metadata; do not infer climate from power')
    groups=pd.read_csv(mapping)
    if groups.climate_original.duplicated().any():raise ValueError('Duplicate climate mapping keys')
    meta['climate_group']=meta.climate.map(groups.set_index('climate_original').climate_group)
    if meta.climate_group.isna().any():raise ValueError('Unmapped climate labels: '+str(meta.loc[meta.climate_group.isna(),'climate'].unique()))
    return meta.reset_index()

class ObservationCollector:
    """Fixed-grid density from every complete hour; no random observation sampling."""
    def __init__(self,bins=2000):
        self.edges=np.linspace(0.,1.,bins+1)
        self.counts=np.zeros(bins,dtype=np.int64)
        self.n=0;self.total=0.;self.squared=0.;self.audit=[]

    def __call__(self,ds,raw,hourly):
        raw_values=np.concatenate([s.to_numpy() for s in raw])
        values=np.concatenate([s.to_numpy() for s in hourly])
        lower=int(np.sum(raw_values < -EPS));upper=int(np.sum(raw_values>1+EPS))
        self.audit.append({'dataset_id':ds.id,'rated_capacity_mw':ds.capacity_kw/1000,
            'observed_min_mw':float(raw_values.min()*ds.capacity_kw/1000),
            'observed_max_mw':float(raw_values.max()*ds.capacity_kw/1000),
            'max_fraction_of_rated_capacity':float(raw_values.max()),
            'raw_samples':len(raw_values),'raw_below_zero':lower,'raw_above_rated':upper,
            'complete_hours':len(values),'first_timestamp_utc':str(min(s.index.min() for s in raw)),
            'last_timestamp_utc':str(max(s.index.max() for s in raw)),
            'capacity_consistent':not(lower or upper)})
        # Snap machine-rounding deviations only. Real out-of-bounds data fail the gate below.
        rounded=values.copy()
        rounded[(rounded<0)&(rounded>=-EPS)]=0
        rounded[(rounded>1)&(rounded<=1+EPS)]=1
        self.counts+=np.histogram(rounded,bins=self.edges)[0]
        self.n+=len(values);self.total+=float(values.sum());self.squared+=float(np.square(values).sum())

    def require_capacity_bounds(self):
        bad=[x['dataset_id'] for x in self.audit if not x['capacity_consistent']]
        if bad:raise ValueError('Power/capacity inconsistencies in '+str(bad)+'. See tables/server_capacity_query.csv; correct source metadata/data explicitly, never replace capacity with observed maximum.')
        if self.counts.sum()!=self.n:raise ValueError('Pooled counts do not cover all complete hours')

    def density(self):
        self.require_capacity_bounds()
        if not self.n:raise ValueError('No complete hourly data')
        mean=self.total/self.n
        variance=max(0.,(self.squared-self.total**2/self.n)/max(1,self.n-1))
        dx=self.edges[1]-self.edges[0]
        bandwidth=max(np.sqrt(variance)*self.n**(-.2),dx)
        density=gaussian_filter1d(self.counts.astype(float),bandwidth/dx,mode='reflect')/(self.n*dx)
        return pd.DataFrame({'cf':(self.edges[:-1]+self.edges[1:])/2,'count':self.counts,'density':density}),{
            'complete_hour_count':self.n,'pooled_mean_cf':mean,'bandwidth_cf':bandwidth,
            'density_method':'All-hour histogram (2000 bins), Gaussian smoothing with Scott bandwidth and reflected boundaries; not a subsampled KDE',
            'weighting':'Each complete farm-hour has equal weight; longer records contribute more hours'}

def climate_profiles(result):
    """Typical farm profile first, then equal-farm median and IQR within climate."""
    farm=result['farm_hourly_profile']/100
    types=result['summary'].set_index('dataset_id').climate_group
    rows=[]
    for climate in sorted(types.unique()):
        group=farm.reindex(types[types.eq(climate)].index).dropna(how='all')
        if group.empty:continue
        for hour in range(24):
            x=group.iloc[:,hour].dropna()
            rows.append({'climate_group':climate,'hour_utc':hour,'farms':len(x),
                         'median_cf':x.median(),'q25_cf':x.quantile(.25),'q75_cf':x.quantile(.75)})
    return pd.DataFrame(rows)

def write_tables(result,collector,meta,out):
    tables=out/'tables';tables.mkdir(parents=True,exist_ok=True)
    for key,name in [('summary','farm_statistics'),('audit','quality_audit'),('files','file_audit'),
                     ('daily','daily_profiles_index'),('volatility_groups','volatility_groups')]:
        result[key].to_csv(tables/f'{name}.csv',index=False,encoding='utf-8-sig')
    meta.to_csv(tables/'matched_farm_metadata.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(collector.audit).to_csv(tables/'server_capacity_query.csv',index=False,encoding='utf-8-sig')
    result['farm_hourly_profile'].to_csv(tables/'farm_mean_daily_profile_percent.csv',encoding='utf-8-sig')
    np.savez_compressed(tables/'daily_profiles.npz',profiles=result['profiles'])
    pd.crosstab(result['summary'].capacity_group,result['summary'].source).to_csv(tables/'size_group_source_composition.csv')
    pd.crosstab(result['summary'].climate_group,result['summary'].source).to_csv(tables/'climate_source_composition.csv')

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',required=True)
    p.add_argument('--output-dir',type=Path,help='Override output folder, relative to current directory')
    p.add_argument('--inspect',action='store_true',help='Read local manifests and metadata only')
    p.add_argument('--metadata-only',action='store_true',help='Draw rotor/hub distributions; never open power CSVs')
    p.add_argument('--query-only',action='store_true',help='SERVER: derive missing descriptive statistics; no STL, UMAP or figures')
    p.add_argument('--daily-panels',choices=['climate','patterns'],default='climate')
    p.add_argument('--overwrite',action='store_true')
    args=p.parse_args(argv)
    if sum([args.inspect,args.metadata_only,args.query_only])>1:p.error('Choose only one inspection mode')
    logging.basicConfig(level=logging.INFO,format='%(levelname)s: %(message)s')
    logging.getLogger('fontTools').setLevel(logging.WARNING)
    cfg=load_config(args.config)
    if args.output_dir is not None:cfg['output_dir']=str(args.output_dir.expanduser().resolve())
    metadata_dir=Path(cfg['metadata_dir'])
    plan,report=prepare(cfg,access_files=False)
    meta=climate_metadata(metadata_dir/'farm_numeric_metadata.csv',metadata_dir/'climate_groups.csv',[x['id'] for x in plan])
    capacities={x['id']:x['capacity_kw']/1000 for x in plan}
    if not np.allclose(meta.rated_capacity_mw,meta.dataset_id.map(capacities),rtol=1e-9,atol=1e-9):
        raise ValueError('Metadata and normalization capacity table disagree; update both explicitly')
    report['climate_groups']=meta.climate_group.value_counts().to_dict()
    grouping_status_file=metadata_dir/'climate_groups_status.json'
    if grouping_status_file.exists():
        grouping_status=json.loads(grouping_status_file.read_text(encoding='utf-8-sig'))
        report['climate_grouping_status']=grouping_status
        valid_grouping=(grouping_status.get('status')=='confirmed' and
                        meta.climate_group.nunique()==grouping_status.get('required_groups') and
                        set(meta.climate_group)==set(grouping_status.get('group_names',meta.climate_group)))
        if not (args.inspect or args.metadata_only or args.query_only) and not valid_grouping:
            raise ValueError('Climate grouping must match the confirmed author-defined five categories. Update climate_groups.csv and climate_groups_status.json before formal plotting. Metadata-only and server query modes remain available.')
    if args.inspect:print(json.dumps(report,ensure_ascii=False,indent=2));return 0
    out=Path(cfg['output_dir'])
    if out.exists() and any(out.iterdir()) and not args.overwrite:
        raise ValueError('Output exists; choose a new folder or --overwrite')
    out.mkdir(parents=True,exist_ok=True);(out/'tables').mkdir(exist_ok=True)
    state={'status':'metadata_only' if args.metadata_only else 'running','raw_series_accessed':False,
        'input_report':report,'config':cfg,'daily_panels':args.daily_panels,
        'normalization':'Instantaneous MW / equipment-based farm rated MW; never observed maximum',
        'capacity_sha256':hashlib.sha256(Path(cfg['inputs']['capacity_table']).read_bytes()).hexdigest(),
        'farm_weighting':'One original farm, irrespective of number of segments',
        'daily_clock':'UTC; not local solar time',
        'umap':'Every complete 24-hour day; Euclidean distance on capacity-factor vectors; colored by recorded climate group',
        'climate_inference':'Descriptive associations; separation is not imposed, and climate is not inferred from power',
        'periodicity':'Independent robust STL fits at 24 h and 168 h; variance-ratio strength',
        'volatility':'Mean absolute consecutive-hour capacity-factor change times 100, in percentage points',
        'size_groups':'<50 MW; 50–150 MW inclusive; >150 MW'}
    state_path=out/'run_manifest.json'
    def checkpoint():state_path.write_text(json.dumps(state,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
    checkpoint()
    from .publication_plotting import equipment_plot, plot_publication
    if args.metadata_only:
        state['figures']=[equipment_plot(meta,pd.read_csv(metadata_dir/'turbine_groups_long.csv'),out)]
        checkpoint();return 0
    datasets,_=prepare(cfg)
    if cfg['analysis']['clock_timezone']!='UTC':raise ValueError('Daily profiles require UTC in this version')
    cfg['plots'].update(layout='legacy',panels=['b'] if args.query_only else ['b','d'])
    cfg['analysis'].update(max_daily_profiles_per_dataset=0,max_stl_windows=0,cluster_fit_limit=2**31-1)
    state['raw_series_accessed']=True;checkpoint()
    collector=ObservationCollector()
    result=derived_tables(analyze(datasets,cfg,observer=collector))
    result['summary']=result['summary'].merge(meta[['dataset_id','source','climate','climate_group']],on='dataset_id',validate='one_to_one')
    result['daily']['climate_group']=result['daily'].dataset_id.map(meta.set_index('dataset_id').climate_group)
    write_tables(result,collector,meta,out)
    if args.query_only:
        state['status']='query_complete';state['capacity_consistent']=all(x['capacity_consistent'] for x in collector.audit)
        checkpoint();return 0
    try:result['pooled_density'],state['pooled']=collector.density()
    except ValueError as exc:
        state.update(status='capacity_review_required',error=str(exc));checkpoint();raise
    result['pooled_mean']=state['pooled']['pooled_mean_cf']
    result['pooled_density'].to_csv(out/'tables/pooled_capacity_factor_density.csv',index=False)
    result['climate_profiles']=climate_profiles(result)
    result['climate_profiles'].to_csv(out/'tables/climate_daily_profiles.csv',index=False)
    if args.daily_panels=='patterns':
        labels,patterns,medians,candidates=cluster_profiles(result['profiles'],cfg['analysis'])
        result['daily']['pattern']=[f'P{x+1:02}' for x in labels]
        rows=[]
        for j,label in enumerate(patterns.pattern):
            v=result['profiles'][labels==j]
            for h in range(24):rows.append({'pattern':label,'hour_utc':h,'median_cf':np.median(v[:,h]),
                'q25_cf':np.quantile(v[:,h],.25),'q75_cf':np.quantile(v[:,h],.75),'days':len(v)})
        result['pattern_profiles']=pd.DataFrame(rows)
        result['pattern_profiles'].to_csv(out/'tables/pattern_daily_profiles.csv',index=False)
    result=embed_profiles(result,cfg['analysis']['seed'])
    result['daily'].to_csv(out/'tables/daily_profiles_index.csv',index=False,encoding='utf-8-sig')
    state['figures']=plot_publication(result,meta,pd.read_csv(metadata_dir/'turbine_groups_long.csv'),out,args.daily_panels)
    state['status']='complete';checkpoint()
    LOG.info('Completed %s farms; %s',len(datasets),out)
    return 0

if __name__=='__main__':raise SystemExit(main())
