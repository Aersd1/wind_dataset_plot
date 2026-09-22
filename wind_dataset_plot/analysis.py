"""All statistics originate in CSV observations, never JSON history/statistics."""
import hashlib
import logging
import numpy as np
import pandas as pd
from .io import load_runs

LOG = logging.getLogger(__name__)


def output_fractions(values):
    """Per-farm time fractions: <0, ten 10%-wide bins in [0,1], >1.

    Exact zero and one are included in the finite bins; outliers are never clipped.
    """
    values=np.asarray(values,float)
    values=values[np.isfinite(values)]
    if not len(values): return np.full(12,np.nan)
    inside=values[(values>=0)&(values<=1)]
    counts=np.r_[np.sum(values<0),np.histogram(inside,bins=np.linspace(0,1,11))[0],np.sum(values>1)]
    return counts/len(values)


def hourly_runs(runs, step):
    """Retain only fully observed clock hours; never interpolate or cross segment boundaries."""
    per_hour = int(pd.Timedelta("1h").value // step)
    result = []
    for run in runs:
        # Regular power samples (or converted interval means) must align with clock hours.
        if np.any(run.index.asi8 % step):
            raise ValueError("Native intervals are not aligned to clock-hour boundaries")
        resampler = run.resample("1h", label="left", closed="left")
        hourly = resampler.mean()
        hourly = hourly[resampler.count() == per_hour]
        if hourly.empty:
            continue
        cuts = np.flatnonzero(np.diff(hourly.index.asi8) != pd.Timedelta("1h").value)+1
        result.extend(hourly.iloc[part] for part in np.split(np.arange(len(hourly)), cuts))
    return result


def daily_profiles(hours, timezone):
    profiles, dates = [], []
    for run in hours:
        local = run.tz_convert(timezone)
        for date, day in local.groupby(local.index.normalize()):
            # DST days with 23/25 hours and days cut across separate files are excluded.
            if len(day)==24 and np.array_equal(day.index.hour, np.arange(24)) and np.all(day.index.minute==0):
                profiles.append(day.to_numpy()); dates.append(date.isoformat())
    return np.asarray(profiles, dtype=float).reshape(-1,24), dates


def seasonal_strength(hours, period, settings):
    from statsmodels.tsa.seasonal import STL
    candidates = []
    minimum = period*settings["min_stl_cycles"]
    for run in hours:
        for offset in range(0,len(run),settings["stl_window_hours"]):
            window = run.iloc[offset:offset+settings["stl_window_hours"]]
            if len(window)>=minimum:
                candidates.append(window)
    limit = settings["max_stl_windows"]
    eligible = len(candidates)
    if limit and eligible>limit:
        candidates = [candidates[i] for i in np.linspace(0,eligible-1,limit,dtype=int)]
    scores, sizes = [], []
    for window in candidates:
        values = window.to_numpy()
        if np.var(values)<1e-15:
            continue  # constant signals have undefined variance-ratio strength, not strength 0/1
        fit = STL(values, period=period, seasonal=7, robust=True).fit()
        denominator = np.var(fit.seasonal+fit.resid)
        if denominator>1e-15:
            scores.append(max(0.,1.-np.var(fit.resid)/denominator)); sizes.append(len(window))
    score = float(np.average(scores,weights=sizes)) if scores else np.nan
    return score, len(scores), int(sum(sizes)), eligible


def analyze_dataset(ds, cfg):
    raw, step, audit, files = load_runs(ds)
    hourly = hourly_runs(raw, step)
    if not hourly:
        raise ValueError(f"{ds.id}: no fully observed hourly bins; check cadence and timestamp convention")
    # All farm descriptors use the same hourly cadence across datasets.
    values = np.concatenate([s.to_numpy() for s in hourly])
    ramps = [np.abs(np.diff(s.to_numpy())) for s in hourly if len(s)>1]
    ramps = np.concatenate(ramps) if ramps else np.array([])
    q = np.quantile(values,[.1,.25,.5,.75,.9])
    a = cfg["analysis"]
    summary = {"dataset_id": ds.id, "label": ds.options.get("label",ds.id), "site_type": ds.site_type,
               "capacity_kw": ds.capacity_kw, "capacity_source": ds.provenance.get("capacity_source", "JSON/config"),
               "capacity_is_proxy": ds.provenance.get("capacity_is_proxy", False),
               "input_layer": ds.provenance.get("layer", "directory_scan"),
               "n_segments":len(ds.files), "n_hourly":len(values), "cf_p10":q[0], "cf_p25":q[1],
               "cf_median":q[2], "cf_p75":q[3], "cf_p90":q[4], "cf_mean":values.mean(),
               "cf_iqr":q[3]-q[1], "ramp_p95":np.quantile(ramps,.95) if len(ramps) else np.nan,
               "ramp_mean":ramps.mean() if len(ramps) else np.nan,
               "low_fraction":np.mean(values<a["low_cf"]), "high_fraction":np.mean(values>a["high_cf"])}
    summary.update({f"output_fraction_{j:02}":v for j,v in enumerate(output_fractions(values))})
    for name,period in (("daily",24),("weekly",168)):
        seasonal_panel="e" if cfg["plots"].get("layout","clear")=="clear" else "d"
        if seasonal_panel in cfg["plots"]["panels"]:
            score,n,used,eligible = seasonal_strength(hourly,period,a)
        else:
            score,n,used,eligible=np.nan,0,0,0
        summary.update({f"stl_{name}":score, f"stl_{name}_windows":n,
                        f"stl_{name}_hours":used,f"stl_{name}_eligible_windows":eligible})
    profiles,dates = daily_profiles(hourly,a["clock_timezone"])
    total_days=len(profiles)
    limit=a["max_daily_profiles_per_dataset"]
    if limit and total_days>limit:
        stable=int.from_bytes(hashlib.sha256(ds.id.encode()).digest()[:4],"little")
        rng=np.random.default_rng(a["seed"]+stable)
        selected=np.sort(rng.choice(total_days,limit,replace=False))
        profiles=profiles[selected]; dates=[dates[i] for i in selected]
    summary.update(n_complete_days=total_days,n_selected_days=len(profiles))
    audit.update(n_complete_hours=len(values), n_complete_days=total_days,
                 native_rows_not_in_complete_hours=audit["retained_rows"]-int(len(values)*pd.Timedelta("1h").value/step))
    daily = pd.DataFrame({"dataset_id":[ds.id]*len(profiles),"date":dates,
                          "mean_cf":profiles.mean(1),
                          "mean_abs_hourly_ramp":np.abs(np.diff(profiles,axis=1)).mean(1)})
    # Per-dataset union means overlapping segments can never increase coverage counts.
    coverage=pd.DatetimeIndex(np.unique(np.concatenate([s.index.asi8 for s in hourly]))).tz_localize("UTC")
    return summary,audit,files,daily,profiles,coverage


def cluster_profiles(profiles, settings):
    """Cluster raw 24-hour CF vectors, not a two-dimensional embedding."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    n=len(profiles)
    if not n:
        return np.array([],dtype=int),pd.DataFrame(),np.empty((0,24)),pd.DataFrame()
    rng=np.random.default_rng(settings["seed"])
    fit_idx=np.sort(rng.choice(n,min(n,settings["cluster_fit_limit"]),replace=False))
    fit_data=profiles[fit_idx]
    distinct=len(np.unique(fit_data,axis=0))
    requested=settings["clusters"]
    candidates=[]
    best_model=None; best_score=-np.inf
    if distinct==1 or n<3:
        k=1
    elif requested=="auto":
        max_k=min(settings["max_clusters"],distinct,len(fit_data)-1)
        for k in range(2,max_k+1):
            model=KMeans(n_clusters=k,n_init=10,random_state=settings["seed"]).fit(fit_data)
            sample_size=min(len(fit_data),settings["silhouette_limit"])
            try:
                score=silhouette_score(fit_data,model.labels_,sample_size=sample_size,random_state=settings["seed"])
            except ValueError:
                score=np.nan
            candidates.append({"k":k,"silhouette":score,"fit_days":len(fit_data),"score_sample_limit":sample_size})
            if np.isfinite(score) and score>best_score:
                best_score=score; best_model=model
        k=1 if best_model is None else best_model.n_clusters
    else:
        k=min(requested,distinct,len(fit_data))
        if k!=requested:
            LOG.warning("Requested %s clusters; only %s distinct fit profiles available; using %s",requested,distinct,k)
    if best_model is None:
        best_model=KMeans(n_clusters=k,n_init=10,random_state=settings["seed"]).fit(fit_data)
    old=best_model.predict(profiles)
    actual=np.unique(old)
    medians=np.array([np.median(profiles[old==j],axis=0) for j in actual])
    sort=np.argsort(medians.mean(1),kind="stable")
    mapping={int(actual[i]):j for j,i in enumerate(sort)}
    assigned=np.array([mapping[int(i)] for i in old])
    medians=medians[sort]
    summary=pd.DataFrame([{"pattern":f"P{j+1:02}","n_days":int(np.sum(assigned==j)),
                          "share":float(np.mean(assigned==j)),"mean_cf":float(medians[j].mean())}
                         for j in range(len(medians))])
    return assigned,summary,medians,pd.DataFrame(candidates)


def analyze(datasets,cfg):
    summaries=[]; audits=[]; files=[]; days=[]; profiles=[]; coverage=[]
    for i,ds in enumerate(datasets,1):
        LOG.info("[%s/%s] %s (%s segments)",i,len(datasets),ds.id,len(ds.files))
        s,a,f,d,p,c=analyze_dataset(ds,cfg)
        summaries.append(s); audits.append(a); files.extend(f); days.append(d); profiles.append(p); coverage.append(c)
    frame=pd.DataFrame(summaries).sort_values(["site_type","cf_median","dataset_id"],kind="stable").reset_index(drop=True)
    daily=pd.concat(days,ignore_index=True)
    vectors=np.concatenate(profiles,axis=0)
    counts=pd.Series(0,index=pd.date_range(min(x.min() for x in coverage),max(x.max() for x in coverage),freq="1h"),dtype=int)
    for timestamps in coverage:
        counts.loc[timestamps]+=1
    counts.index.name="timestamp_utc"; counts.name="datasets_with_complete_hour"
    if "f" in cfg["plots"]["panels"]:
        assigned,patterns,medians,candidates=cluster_profiles(vectors,cfg["analysis"])
        daily["pattern"]=[f"P{x+1:02}" for x in assigned]
    else:
        patterns,medians,candidates=pd.DataFrame(),np.empty((0,24)),pd.DataFrame()
    return dict(summary=frame,audit=pd.DataFrame(audits),files=pd.DataFrame(files),daily=daily,
                profiles=vectors,coverage=counts,patterns=patterns,medians=medians,candidates=candidates)
