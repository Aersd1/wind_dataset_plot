# 出版图说明

这批图在 `publication_results/server_run_maxcap/figures/`。图 1–4 与图 7 由 `tools/replot_publication_max_capacity.py` 用已有中间表重绘；图 5、图 6 与图 8 由 `tools/replot_umap_daily_spread.py` 在同一套表上重算并重绘。绘图函数在 `wind_dataset_plot/publication_plotting.py`，统计函数在 `wind_dataset_plot/analysis.py`、`wind_dataset_plot/revised.py` 和 `wind_dataset_plot/publication.py`。

样本是 131 个场站、1770 个对齐片段、5,270,583 个完整小时、218,076 个完整日。功率是 15 分钟瞬时值，时间统一为 UTC。

## 共同计算

### 容量因子

原始 CSV 里的功率先换成 kW，再除以该场站容量（kW），得到容量因子：

```text
CF = 功率(kW) / 容量(kW)
```

换算在 `wind_dataset_plot/io.py` 的 `to_cf`。负功率保留为负的容量因子，不截成 0。

```python
def to_cf(values, unit, capacity_kw, interval_minutes):
    unit = normalize_unit(unit)
    values = np.asarray(values, dtype=float)
    if unit == "capacity_factor":
        return values
    factor = {"W": .001, "kW": 1., "MW": 1000., "Wh": .001, "kWh": 1., "MWh": 1000.}[unit]
    power_kw = values * factor
    if unit.endswith("Wh"):
        power_kw = power_kw / (interval_minutes/60.)
    return power_kw / capacity_kw
```

容量默认是设备台数乘单机额定功率，来源字符串为 `xlsx_equipment_count_times_rated_kw`。有 11 个场站的功率超过这套设备额定值。这 11 个场站的分母改成该场站观测到的最大功率，容量因子按 `设备额定 / 观测最大功率` 缩小。名单和缩放系数在 `observed_maximum_capacity.csv`。其余场站仍用设备额定容量。只出现负功率、没有超出额定功率的场站不改分母。

线性量（容量因子分位数、均值、小时变化、日曲线）随这个比例缩放。STL 季节强度是方差比，分母缩放后不变，所以沿用第一次计算的结果。出力区间占比不是线性量，仍留在原分母上，当前这八张图都不用它。

### 完整小时与完整日

`analysis.hourly_runs` 只保留整点小时内 4 个 15 分钟样本都在的小时，取这 4 个样本的平均作为该小时的容量因子。缺测不插值，片段边界不连接。相邻小时如果中间断开，就切成独立的连续段，后面的差分和 STL 都不跨段。

`analysis.daily_profiles` 在这些小时上取完整日。一个完整日必须正好有 0–23 时各一个样本。被切段截断的日子、以及夏令时造成的 23 或 25 小时日，都不进入日曲线。本批数据时区是 UTC，所以没有夏令时截断。

`revised.derived_tables` 再把每个场站的全部完整日在 24 个小时上分别平均，得到一条场站平均日曲线，写入 `tables/farm_mean_daily_profile_percent.csv`，单位是额定容量的百分比。

`wind_dataset_plot/analysis.py`：

```python
def hourly_runs(runs, step):
    """Retain only fully observed clock hours; never interpolate or cross segment boundaries."""
    per_hour = int(pd.Timedelta("1h").value // step)
    result = []
    for run in runs:
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
            if len(day)==24 and np.array_equal(day.index.hour, np.arange(24)) and np.all(day.index.minute==0):
                profiles.append(day.to_numpy()); dates.append(date.isoformat())
    return np.asarray(profiles, dtype=float).reshape(-1,24), dates
```

`wind_dataset_plot/revised.py` 里场站平均日曲线：

```python
profiles_frame=pd.DataFrame(profiles,columns=[f'hour_{h:02}' for h in range(24)])
profiles_frame.insert(0,'dataset_id',daily.dataset_id.to_numpy())
hourly=profiles_frame.groupby('dataset_id',sort=False).mean().reindex(summary.dataset_id)*100
```

### 分组

- 场址：`offshore` / `onshore`，来自设备容量表。本批 31 个海上、100 个陆上。
- 容量：`revised.size_group`。小于 50 MW；50–150 MW（含两端）；大于 150 MW。替换观测最大功率后，Thorntonbank NE 从 50–150 MW 进入大于 150 MW。本批三组分别是 91、18、22 个场站。

```python
def size_group(mw):
    if not np.isfinite(mw) or mw <= 0:
        raise ValueError('Rated capacity must be positive and finite')
    return '<50 MW' if mw < 50 else ('50–150 MW' if mw <= 150 else '>150 MW')
```
- 气候：元数据中的原始气候标签映射到五个组，分别是 Humid continental 39、Oceanic 27、Arid / semi-arid 27、Other climates 21、Humid subtropical 17。气候不从功率反推。

## 图 1　叶轮直径与轮毂高度

文件：`figures/01_rotor_diameter_and_hub_height.png`

左图是叶轮直径，右图是轮毂高度。每个点是一个场站在设备表里记录的一个规格值。同一场站若有多组机组、因而有多个直径或轮毂高度，就画多个点，纵坐标相同。圆点是海上，三角是陆上。纵轴没有刻度，点只在组内错开，避免重叠，不表示排序或数值。

这张图不读功率 CSV。`publication_plotting.equipment_plot` 使用 `turbine_groups_long.csv` 里 `record_kind == unit_group` 的记录，并去掉虚拟场站。有设备记录、且对应字段非空的场站才出现：叶轮直径海上 20/20、陆上 26/27；轮毂高度海上 19/20、陆上 25/27。图中不画参考机型。逐点数值在 `tables/equipment_distribution_source.csv`。

```python
for ax,field,label in zip(axes,['rotor_m','hub_m'],['Rotor diameter (m)','Hub height (m)']):
    for kind in ['offshore','onshore']:
        ids=sorted(meta.loc[meta.site_type.eq(kind)&~meta.is_virtual,'dataset_id'])
        for identifier in ids:
            g=selected[selected.dataset_id.eq(identifier)&selected.record_kind.eq('unit_group')]
            vals=np.sort(g[field].dropna().unique())
            if not len(vals):continue
            ax.scatter(vals,np.full(len(vals),offsets[identifier]),s=14,facecolors=COLORS[kind],edgecolors=COLORS[kind],
                marker='o' if kind=='offshore' else '^',linewidths=.5,alpha=.8)
```

## 图 2　海上与陆上的小时波动

文件：`figures/02_volatility_onshore_offshore.png`

每个点是一个场站。纵轴是平均绝对小时变化，单位是额定容量的百分点：

```text
mean_hourly_change_pp = 100 × mean(|CF_t − CF_{t−1}|)
```

差分只在 `hourly_runs` 保留下来的连续小时内部计算。海上 31 个点、陆上 100 个点全部有效。组内横向位置是固定错开，不表示第二个变量。

`wind_dataset_plot/analysis.py` 的 `analyze_dataset`：

```python
ramps = [np.abs(np.diff(s.to_numpy())) for s in hourly if len(s)>1]
ramps = np.concatenate(ramps) if ramps else np.array([])
ramp_mean = ramps.mean() if len(ramps) else np.nan
```

`wind_dataset_plot/revised.py` 的 `derived_tables`：

```python
summary['mean_hourly_change_pp']=summary.ramp_mean*100
```

`publication_plotting.volatility_scatter` 只把这个数画成散点，中位数和四分位距只写入 CSV：

```python
values=g.mean_hourly_change_pp.to_numpy(dtype=float)
values=values[np.isfinite(values)]
ax.scatter(x-.07+categorical_offsets(len(values),.42),values,color=color,marker=marker,
           s=13,alpha=.75,linewidths=.3,edgecolors='white',zorder=3)
q25,median,q75=np.quantile(values,[.25,.5,.75])
```

图上只有散点。组中位数和四分位距写在 `figures/02_volatility_onshore_offshore_group_summary.csv`，不画在图上。海上中位数 4.83 个百分点，陆上中位数 6.84 个百分点。

## 图 3　按额定容量分组的小时波动

文件：`figures/03_volatility_capacity_groups.png`

与图 2 使用同一个场站指标，分组改成额定容量三档。绘图函数仍是 `volatility_scatter`，参数 `by='capacity_group'`。小于 50 MW、50–150 MW、大于 150 MW 的中位数分别是 6.86、6.26、4.64 个百分点，对应表是 `figures/03_volatility_capacity_groups_group_summary.csv`。同样只画散点。

## 图 4　全体容量因子分布

文件：`figures/04_pooled_capacity_factor_distribution.png`

背景色带是全部场站、全部完整小时合在一起的容量因子密度。每个完整小时权重相同，记录长的场站贡献更多小时。

重绘时的直方图在 `tools/replot_publication_max_capacity.py` 的 `pooled_histogram`：

1. 用更新后的容量把每个完整小时换成容量因子。
2. 容量因子小于 −1e−9 的小时排除，不截成 0。这样的小时有 7,878 个。
3. 其余 5,262,705 个小时放入 [0, 1] 上的 2000 个等宽箱。
4. 用 Scott 带宽做高斯平滑，边界用反射，再除以样本量和箱宽，得到密度。
5. 密度除以自身最大值后，画成水平方向的小提琴，纵轴仍是容量因子。

```python
edges = np.linspace(0.0, 1.0, 2001)
values = values[np.isfinite(values)]
low = values < -EPS
kept = values[~low].copy()
kept[(kept < 0) & (kept >= -EPS)] = 0
kept[(kept > 1) & (kept <= 1 + EPS)] = 1
counts += np.histogram(kept, bins=edges)[0]
mean = total / n
variance = max(0.0, (squared - total ** 2 / n) / max(1, n - 1))
dx = edges[1] - edges[0]
bandwidth = max(np.sqrt(variance) * n ** (-0.2), dx)
density = gaussian_filter1d(counts.astype(float), bandwidth / dx, mode="reflect") / (n * dx)
```

画小提琴和场站均值的是 `publication_plotting.pooled_plot`：

```python
width=density.density.to_numpy()/density.density.max()*.42
ax.fill_betweenx(y,-width,width,color='#9CB9D7',alpha=.6,lw=.8,edgecolor='#6889AE')
ax.scatter(categorical_offsets(len(g),.3),g.cf_mean,s=12,edgecolors=COLORS[kind],facecolors='none',
           marker=marker,linewidths=.65,alpha=.8)
ax.plot([-.2,.2],[result['pooled_mean']]*2,color='#202020',lw=1.2)
```

平滑带宽约 0.0164。全体小时均值是 0.420。中间短横线是这个均值，不是中位数。

两侧空心点是各场站自己的平均容量因子，圆点海上、三角陆上，横向位置同样只为错开。场站均值的中位数是 0.418。这些点与背景密度的权重不同：背景是小时等权，散点是场站等权。

## 图 5　场站日型的亲疏

文件：`figures/05_farm_profile_similarity.png`

每个点是一个场站，一共 131 个点，颜色是气候组。一个场站的特征是它的 24 小时平均容量因子。两点越近，这两条平均日曲线的欧氏距离越小，日型越接近。气候只用来着色，不参与摆放。

坐标是这 131 条曲线的主成分，也就是欧氏距离的经典标度，不是 UMAP。UMAP 主要保留局部邻域，拉远之后的距离不能再当成亲疏。前两个主成分合计保留 93% 的日型方差：PC1 占 76%，载荷在 24 个小时上都是正的，与平均出力的相关系数是 0.99，所以越靠右平均出力越高；PC2 占 17%，清晨为负、午后为正，与“16–19 时均值减去 2–6 时均值”的相关系数是 0.87，所以越靠上，出力越偏向午后而不是清晨。符号已经按这两个方向定好，距离不因翻号而改变。

坐标和载荷在 `tables/farm_profile_similarity.csv` 与 `tables/farm_profile_similarity_loadings.csv`。绘图函数是 `publication_plotting.climate_profile_similarity`。

```python
from sklearn.decomposition import PCA
profile=result['farm_hourly_profile']
hours=[column for column in profile.columns if str(column).startswith('hour_')]
values=profile[hours].to_numpy(dtype=float)/100
model=PCA(n_components=2,svd_solver='full').fit(values)
xy=model.transform(values)
if np.corrcoef(xy[:,0],values.mean(axis=1))[0,1]<0:
    xy[:,0]*=-1; model.components_[0]*=-1
afternoon=values[:,16:20].mean(axis=1)-values[:,2:7].mean(axis=1)
if np.corrcoef(xy[:,1],afternoon)[0,1]<0:
    xy[:,1]*=-1; model.components_[1]*=-1
```

`values[:,16:20]` 是 16–19 时，`values[:,2:7]` 是 2–6 时。翻号只统一读图方向，两点之间的距离不变。

## 图 6　五个气候的典型日出力

文件：`figures/06_daily_power_panels.png`

五个气候面板排成一行。曲线是该气候内各场站平均日曲线的中位数。色带不是这些平均曲线的四分位距。

计算在 `publication.climate_profiles`，每个场站权重相同：

1. 对该场站的全部完整日，在每个小时上取平均，得到一条 24 小时平均曲线。
2. 再对该场站的全部完整日，在每个小时上取 25% 和 75% 分位数，得到这个场站自己的逐日变化区间。
3. 在同一气候的场站之间，对平均曲线取中位数，画成实线。
4. 对每个小时，把各场站的 25% 分位数再取中位数，作为色带下沿；75% 分位数再取中位数，作为色带上沿。

因此色带表示的是“这一气候里，一个典型场站一天之内的中间 50% 日子落在哪里”，而不是“各场站平均日型彼此差多少”。

上一版色带用的是第 1 步那些平均曲线的 25%–75% 分位数。同一气候里的平均日型很接近，这条带的宽度中位数只有约 11 个百分点，画在 0–100 的纵轴上几乎是一条细线。当前色带的宽度中位数约 60 个百分点（约 50–78 个百分点）。结果表是 `tables/climate_daily_profiles.csv`，其中 `q25_cf` 和 `q75_cf` 已是新定义。

纵轴是额定容量的百分比，范围固定为 0–100，横轴是 UTC 的 0–23 时。五个面板排成一行，在 `publication_plotting.daily_panels` 里 `ncols=len(groups)`。

`wind_dataset_plot/publication.py` 的 `climate_profiles`：

```python
for climate,farms in climates.groupby(climates).groups.items():
    means=[];low=[];high=[]
    for farm in farms:
        idx=grouped.get(farm)
        if not idx:continue
        block=profiles[idx]
        means.append(block.mean(axis=0))
        low.append(np.quantile(block,.25,axis=0))
        high.append(np.quantile(block,.75,axis=0))
    means,low,high=np.vstack(means),np.vstack(low),np.vstack(high)
    for hour in range(24):
        rows.append({'climate_group':climate,'hour_utc':hour,'farms':len(means),
                     'median_cf':float(np.median(means[:,hour])),
                     'q25_cf':float(np.median(low[:,hour])),
                     'q75_cf':float(np.median(high[:,hour]))})
```

`publication_plotting.daily_panels` 把容量因子乘 100 后作图：

```python
g=table[table[column].eq(group)].sort_values('hour_utc')
ax.fill_between(g.hour_utc,g.q25_cf*100,g.q75_cf*100,color=colors[group],alpha=.22,lw=0)
ax.plot(g.hour_utc,g.median_cf*100,color=colors[group],lw=1.2)
```

## 图 7　日周期与周周期强度

文件：`figures/07_daily_weekly_periodicity.png`

每个点仍是一个场站。箱线给出全体场站的分布，不画离群点。圆点海上，三角陆上。131 个场站的日周期和周周期强度都有定义。

强度来自 `analysis.seasonal_strength`。对每个连续小时段，按 1344 小时（8 周）取窗，窗长至少要覆盖 3 个周期：日周期至少 72 小时，周周期至少 504 小时。`max_stl_windows=0` 表示不抽样，所有合格窗都参加计算。每个窗做稳健 STL，周期分别是 24 和 168，季节平滑长度为 7。强度是

```text
max(0, 1 − Var(残差) / Var(季节项 + 残差))
```

方差几乎为 0 的窗跳过，不记成 0 或 1。一个场站有多个窗时，按窗内小时数加权平均。这个比值不随容量因子的统一缩放改变，所以 11 个改过分母的场站直接沿用了第一次 STL 结果。

左箱是日周期（24 小时），右箱是周周期（168 小时）。纵轴是 0 到 1，越大表示该周期越稳定。

`wind_dataset_plot/analysis.py` 的 `seasonal_strength`：

```python
minimum = period*settings["min_stl_cycles"]
for run in hours:
    for offset in range(0,len(run),settings["stl_window_hours"]):
        window = run.iloc[offset:offset+settings["stl_window_hours"]]
        if len(window)>=minimum:
            candidates.append(window)
for window in candidates:
    values = window.to_numpy()
    if np.var(values)<1e-15:
        continue
    fit = STL(values, period=period, seasonal=7, robust=True).fit()
    denominator = np.var(fit.seasonal+fit.resid)
    if denominator>1e-15:
        scores.append(max(0.,1.-np.var(fit.resid)/denominator)); sizes.append(len(window))
score = float(np.average(scores,weights=sizes)) if scores else np.nan
```

调用时日周期 `period=24`，周周期 `period=168`。`min_stl_cycles=3`，`stl_window_hours=1344`，`max_stl_windows=0`。

## 图 8　十二个场站的日出力

文件：`figures/08_twelve_farm_daily_profiles.png`

这是新增的图，两行六列，每个面板一个场站。画法和图 6 相同：实线是该场站全部完整日在每个小时上的中位数，色带是这些日在该小时的 25%–75% 分位数。颜色仍表示气候，图例在上方。计算和绘图在 `publication_plotting.farm_daily_panels`，挑选名单在 `tools/replot_umap_daily_spread.py` 的 `SELECTION`，并写入 `tables/twelve_farm_daily_selection.csv`。

挑选规则是五种气候都出现，同时兼顾海上和陆上，以及较低到较高的平均容量因子。NREL 场站的面板标题用数据集编号里的地名，完整编号在选择表里。

| 面板标题 | 气候 | 场址 | 完整日 |
| --- | --- | --- | --- |
| Lake Huron | Humid continental | 海上 | 1922 |
| Roanoke | Humid continental | 陆上 | 1194 |
| Randolph | Humid continental | 陆上 | 467 |
| SNOWSTH1 | Arid / semi-arid | 陆上 | 364 |
| Fremont | Arid / semi-arid | 陆上 | 2557 |
| Gulf LA | Humid subtropical | 海上 | 1721 |
| Comanche | Humid subtropical | 陆上 | 2469 |
| LARYO-1 | Oceanic | 海上 | 1180 |
| BALDHWF1 | Oceanic | 陆上 | 364 |
| BRBEO-1 | Oceanic | 海上 | 863 |
| UP_BDDSLDSRDI_1 | Other climates | 陆上 | 3960 |
| WATERLWF | Other climates | 陆上 | 364 |

图 6 的色带是许多场站逐日区间的中位数；图 8 的色带就是这一个场站自己的逐日区间，所以各面板宽窄不同。

`publication_plotting.farm_daily_panels`：

```python
block=profiles[grouped[item['dataset_id']]]
median=np.median(block,axis=0)*100
low=np.quantile(block,.25,axis=0)*100
high=np.quantile(block,.75,axis=0)*100
ax.fill_between(hours,low,high,color=color,alpha=.22,lw=0)
ax.plot(hours,median,color=color,lw=1.2)
```

`block` 的每一行是该场站的一个完整日，24 列是 0–23 时的容量因子。

## 代码对应

| 图 | 统计 | 绘图 |
| --- | --- | --- |
| 1 | 设备表，不经功率计算 | `publication_plotting.equipment_plot` |
| 2、3 | `analysis.analyze_dataset` 的 `ramp_mean`，`revised.derived_tables` 乘 100 | `publication_plotting.volatility_scatter` |
| 4 | `tools/replot_publication_max_capacity.py` 的 `pooled_histogram` | `publication_plotting.pooled_plot` |
| 5 | 各场站 24 小时平均日曲线的主成分 | `publication_plotting.climate_profile_similarity` |
| 6 | `publication.climate_profiles` | `publication_plotting.daily_panels` |
| 7 | `analysis.seasonal_strength` | `publication_plotting.periodicity_plot` |
| 8 | 各场站完整日的逐小时中位数与四分位数 | `publication_plotting.farm_daily_panels` |

重绘入口：

- 图 1–4、图 7：`tools/replot_publication_max_capacity.py`
- 图 5、图 6、图 8：`tools/replot_umap_daily_spread.py`

两次重绘都读取 `publication_results/server_run_maxcap/tables/` 里已经按观测最大功率缩放过的场站统计和日曲线，不再扫描全部原始 CSV。图 4 的直方图是例外，它在容量替换后重新读过功率 CSV。
