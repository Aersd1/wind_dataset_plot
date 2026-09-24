# 七类数据特征图：当前方案

此方案取代之前的累计容量曲线、每日热图以及 MSE 分组方案。当前图组只回答数据本身的设备、出力、波动、气候关联和周期特征。

## 图形及含义

| 文件 | 内容 | 直接读出的信息 |
|---|---|---|
| 01_rotor_diameter_and_hub_height | 叶轮直径、轮毂高度两个散点面板 | 海上与陆上实际设备尺寸的分布；只有 Offshore、Onshore，无 model 类别，无连接线 |
| 02_volatility_onshore_offshore | 横轴平均出力占容量百分比，纵轴平均逐小时变化（pp） | 每个点一个风场，颜色/形状区分海上与陆上；位置越高，逐小时变化越大 |
| 03_volatility_capacity_groups | 与图 02 相同坐标 | 用不同颜色/形状区分 <50 MW、50–150 MW、>150 MW，便于比较规模组的波动分布 |
| 04_pooled_capacity_factor_distribution | 所有有效小时观测汇总的小提琴轮廓 | 在什么容量因子附近，观测出现得更频繁；散点是各风场的平均容量因子，黑线是所有小时的汇总均值 |
| 05_daily_profiles_umap_by_climate | 每个完整日一粒点，颜色来自该风场的气候类别 | 看不同气候的日出力行为相近、重叠或分散的位置；不预设不同气候一定分离 |
| 06_daily_power_panels | 多个 0–23 UTC 时的容量归一化出力小图 | 默认按气候分面；曲线为典型日内出力，阴影为风场间第 25–75 百分位范围 |
| 07_daily_weekly_periodicity | 日、周 STL 强度箱线与散点 | 越接近 1，相应周期越突出；点颜色区分海上/陆上 |

图名和统计解释不写进图像底部；坐标、必要图例、气候分面标签保留。全部导出独立 PDF、SVG、600 dpi PNG。

## 容量、统计单位与设备尺寸

容量是整座风场的额定总功率，单位 MW。容量因子 CF = 瞬时功率 MW / 风场额定功率 MW。额定容量不由观测最大值替代；不同机型按机组数量乘单机额定功率后求和。

波动指标为 `100 × mean(|CF(t+1) − CF(t)|)`，单位为百分点 pp。例如从容量的 30% 变到 35%，对应 5 pp。它是功率的实际变化，不是模型预测误差 MSE。
50 MW 和 150 MW 两个边界均归入中等容量组。CSV 的容量、海陆分类和图形分组使用同一份匹配表。

原 131 场站的 1770 个 aligned_segments 是时序输入。一个风场切成多段仍只计为一个风场；data_process 层不混入。
每小时必须包含全部预期原始采样点；缺口及片段边界不计算相邻变化。一个完整日必须来自同一连续片段的 24 个完整 UTC 小时。

尺寸图仅使用表中实际设备记录，不将 NREL 虚拟机组的拟合参考型号混入实际安装尺寸。
原清单中有 46 个此类场站：叶轮直径有记录的为 46 个，轮毂高有记录的为 44 个；原表近似尺寸按原值展示，其标记保留在 CSV 中。
同一风场有多个已知尺寸时分别画点，不用均值替代，也不画连接线。纵向轻微错开只为避免重叠，不表示额外数值。每个字段实际包含哪些场站见 equipment_distribution_source.csv。
NREL 等所有 131 场站仍用于其余时序图；设备参数表完整保留参考型号字段，但图中不设 model 分组。

完整工作簿有 132 行，额外 huaneng 保留在完整 CSV 中；本版时序输入延续原 131 场站清单。

## Pooled 图：轮廓、散点和横线是三个明确统计量

轮廓汇总所有场站的全部完整小时 CF，每个场站-小时权重相同。因此记录较长的风场贡献更多观测；它不是先求风场均值再画小提琴。
为避免对海量观测抽样，程序汇总 2000 个等宽区间，再以 Scott 带宽进行高斯平滑，并在 0、1 边界反射。保留区间计数、平滑密度、总小时数和带宽供复核。
散点为各风场的平均 CF，紫色圆点代表海上、橙色三角形代表陆上；横线为全部小时 CF 的汇总均值。
该轮廓是基于全部小时直方图的平滑密度近似，不称为直接对每个原始样本计算的精确 KDE。

## 气候 UMAP 和每日大图

气候按作者指定的五类分组，UMAP 图例与每日曲线面板使用相同的名称、顺序和颜色：

| 图例类别 | 原表标签归并 |
|---|---|
| Humid continental | 湿润大陆性气候的暖夏、热夏亚型 |
| Arid / semi-arid | 寒冷/炎热半干旱、半干旱、寒冷沙漠气候 |
| Humid subtropical | 湿润亚热带气候 |
| Oceanic | 温带海洋性、海洋性、温带海洋气候 |
| Other climates | 地中海、亚寒带、热带季风、苔原、未细分温带/大陆性，以及地中海–半干旱过渡类型 |

原始气候描述完整保留；`climate_groups.csv` 逐条记录对应关系。过渡类型保留在 Other climates 中，不推断为纯粹的半干旱气候。这是用于展示的五类归并，不是从功率序列重新推断气候。未知原始标签会报错；五类名称及状态由 `climate_groups_status.json` 核验。

UMAP 输入每个完整日的 24 维小时 CF，采用欧氏距离，保留所有符合条件的完整日。坐标不带物理单位，颜色不是聚类编号；绘图仅打散显示顺序以避免某一组始终遮盖其他组。
不同气候也可能重叠，图形本身不证明气候造成差异；表中同时导出气候与数据来源的交叉计数。

每日大图默认与气候 UMAP 配套：先在各风场内部平均完整日，得到 24 小时平均日内曲线，再在同一气候的风场间取逐小时中位数与四分位区间，每个风场等权。
曲线是平均日内轮廓，不是一段特定真实日期的轨迹；阴影是风场间差异，不是置信区间。全部小时为 UTC，不能当成各地当地太阳时。

若需要类似原图的多个日曲线类型小面板，增加 `--daily-panels patterns`。
该模式对全部完整日的原始 24 维 CF 向量作 KMeans（默认 16 类），不是在 UMAP 平面上聚类；每类画逐小时中位数与四分位区间。
类别按平均出力排序，实际类别数受数据中的不同曲线数量限制。UMAP 仍按气候着色，不改成类别色。

## 周期性

在连续完整小时窗口中分别进行 24 小时和 168 小时的稳健 STL 分解，强度为 `max(0, 1 − Var(residual)/Var(seasonal + residual))`。
窗口至少覆盖三个相应周期，所有合格窗口按小时数加权汇总到风场。图中使用同时有日/周强度的风场。
日与周是两个独立分解结果；不能把周强度解释为扣除日周期后剩余的周效应。常数序列的方差比未定义，不填成虚假的 0 或 1。

## 服务器运行

在仓库根目录执行（推荐 Python 3.11 或 3.12）：

```sh
git pull --ff-only
python -m pip install -e . -r requirements-qa.txt
python -m wind_dataset_plot.publication --config publication_config.json --inspect
```

该检查只读清单及元数据，应显示 131 场站、1770 个 aligned_segments、5 个气候分组。
功率 CSV 的 power 是瞬时 MW，采样间隔默认 15 min；无时区的时间戳按配置中的 UTC 解释。如果服务器源文件采用其他时区，须明确设置 defaults.timezone。
服务器路径改变时修改 inputs.path_prefix_map，例如将原路径前缀映射到新的挂载目录。

先查询 CSV 元数据表无法提供的时序统计：

```sh
python -m wind_dataset_plot.publication --config publication_config.json --query-only --output-dir publication_results/server_query
```

查询读取服务器功率序列，输出观测最小/最大 MW、时间跨度、完整小时/日数、平均与中位出力、逐小时变化等。
`server_capacity_query.csv` 比较观测功率与额定容量；`capacity_consistent` 应为 True。
正式绘图会阻止使用明显超出 0–额定容量的数据；只容许 1e-9 CF 的浮点比较误差，不静默截断、不把观测峰值改成容量。若不一致，先核对原始数据和机组容量记录，并同步更新容量表和数值元数据表。

正式运行全部七图：

```sh
python -m wind_dataset_plot.publication --config publication_config.json
python tools/check_publication_figures.py publication_results/server_run
```

图形在 publication_results/server_run/figures，统计表和源数据在 tables，运行状态在 run_manifest.json。
完整日较多时 UMAP 需要较多时间与内存；程序不会为了好看而自动抽掉研究样本。
输出目录非空时程序会拒绝覆盖。建议使用新的 `--output-dir`；确需覆盖可加 `--overwrite`，只有 run_manifest.json 的 status=complete 才表示本轮七图全部完成。

仅重画设备尺寸图、不读取功率时序：

```sh
python -m wind_dataset_plot.publication --config metadata_config.json --metadata-only --overwrite
python tools/check_publication_figures.py publication_results/local_metadata
```

服务器结果生成后，可提交 figures 中的 PDF/PNG/SVG、tables 中的汇总 CSV、QA 和 run_manifest。
逐日矩阵 daily_profiles.npz 和逐日索引较大，作为服务器源数据保留，默认不纳入 Git；这不影响任何图的计算或展示。输入原始时序不纳入 Git。

## 可直接用于论文的英文图注

**Equipment dimensions.** Rotor diameter and hub height reported for offshore and onshore farms. Points denote recorded farm-specific dimensions; multiple dimensions are retained for farms with mixed equipment. Vertical offsets avoid overlap. Virtual-turbine reference models are excluded.

**Output variability by farm type.** Mean capacity-normalized output versus mean absolute change between consecutive complete hours. Each point represents one original wind farm; colours and symbols distinguish offshore and onshore sites. Changes are expressed in percentage points of rated farm capacity and do not span gaps or segment boundaries.

**Output variability by rated capacity.** The same farm-level output and variability measures, grouped by rated farm capacity: <50 MW, 50–150 MW and >150 MW. Both boundary values belong to the middle group.

**Pooled capacity-factor distribution.** The violin shows the smoothed distribution of all complete hourly capacity factors, with equal weight per farm-hour. Points indicate individual farm means and the black line the pooled hourly mean. Purple circles and orange triangles denote offshore and onshore farms, respectively.

**Daily output profiles across climates.** UMAP representation of complete daily profiles, each comprising 24 hourly capacity factors. Each point represents one farm-day and is coloured by the farm's recorded climate group. The embedding describes profile similarity and has no physical coordinate units.

**Daily output profiles by climate.** Curves show the median of farm-level mean daily profiles within each climate group; shading denotes the interquartile range across farms. Output is expressed as a percentage of rated farm capacity and time is in UTC.

**Daily and weekly periodicity.** Farm-level seasonal strengths from separate robust STL decompositions with periods of 24 and 168 hours. Boxes show interquartile ranges, centre lines medians and whiskers the most extreme values within 1.5 interquartile ranges; all eligible farm points are shown. Larger strengths indicate more pronounced periodic components.

上述时序图注在服务器得到真实结果后使用；本机只生成设备尺寸图，未生成占位时序研究图。
