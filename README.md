# Wind dataset plots

从 **切割后保留的、未归一化 CSV 时序**计算数据集特征，生成论文训练语料多样性图。支持场站路径清单，也支持 `linear_artifact_remover.py` 的来源注释。清单模式使用容量表，并从 JSON 读取海陆类型；不使用 JSON 的 `history`、`statistics` 或预测结果。

项目没有附带研究原始数据或预计算论文结果。测试只使用代码临时生成的小型合成数据。

## 1. 在服务器安装

Python 3.10+（建议 3.11 或 3.12），无需桌面、GPU 或外部绘图服务。

```bash
git clone https://github.com/Aersd1/wind_dataset_plot.git
cd wind_dataset_plot
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Windows 激活命令为 `.venv\Scripts\Activate.ps1`。也可以不安装本项目：安装 `requirements.txt` 后，从项目根目录执行 `python -m wind_dataset_plot`。

### 使用本次提供的容量表和路径清单（推荐入口）

复制 `examples/config.manifests.json` 到项目根目录，命名为 `local_config.json`。将 `整理/` 文件夹放在配置文件旁，或将配置中的三个表路径改为服务器上的实际位置；`metadata_dir` 填写场站 JSON 的根目录。

```text
local_config.json
整理/
  farm_capacity_units_131.csv
  farm_data_paths_131/
    farm_paths_segmented_long_131.csv
    farm_paths_segmented_131.csv
    farm_paths_original_131.csv
```

本次已明确选择 **`segment_layer: "aligned_segments"`**。提供的长表共有 2,168 行，其中仅取 aligned 的 **131 个场站、1,770 个片段**，排除 data_process 的 398 行。这些是对本次索引表的核查结果，不是程序写死的数量。

- 按精确的 `name` + `source` 连接场站、容量和来源。`name` 保留完整数字后缀，片段只归属于其对应场站。
- 长表读取 `layer`、`segment_csv_path`。也可将 `segments_manifest` 改为 `farm_paths_segmented_131.csv`，程序分别拆分 `aligned_segment_paths` / `data_process_segment_paths` 中的 `|`；两种表等价，任选其一。
- `farm_paths_original_131.csv` 仅用于校验场站并记录原始来源，**不读其中时序、不加入计算**。
- 容量采用 `rated_power_kW_used`，并与 `rated_power_MW_used` 校验。CSV 的 `power` 明确为瞬时 MW，计算 `CF = power_MW × 1000 / rated_power_kW_used`；不乘除 15 分钟或一小时。小时值为完整小时内等间隔样本的算术均值，不是累计发电量。
- JSON 仅提供 `onshore` / `offshore`。在清单模式下，JSON 的容量、单位叙述、z-score 历史和统计值均不覆盖容量表与 MW 定义。若 JSON 海陆类型与表中 `onshore_offshore` 不一致，程序报错。
- 配置示例按 `aligned_15min` 设置采样间隔 15 分钟。时间列可以自动识别；时间格式与时区须以实际 CSV 为准。若日期为 `18/01/01 00:45`，需明确设 `timestamp_format: "%y/%m/%d %H:%M"`；若是 ISO 日期则保留 `null`。不要从 JSON 的窗口时间格式推断 CSV。

先在本地或服务器只核对清单（无需访问服务器时序或 JSON，不生成图和结果文件）：

```bash
python -m wind_dataset_plot --config local_config.json --inspect-manifests
```

服务器数据和 JSON 就绪后，验证路径、海陆类型和 CSV 列名；第二条命令才开始正式计算：

```bash
python -m wind_dataset_plot --config local_config.json --validate-only
python -m wind_dataset_plot --config local_config.json
```

若服务器挂载点变化，可配置 `inputs.path_prefix_map`，按路径边界替换最长匹配的前缀，例如 `{"/old/mount": "/new/mount"}`。路径清单内的相对路径以清单所在目录为基准。缺失已选择的文件直接报错，不偷偷改用另一层。

**容量来源核查：** 当前表中 `BANC DE GUERANDE 2`、`BRDUW-1`、`BRYBW-1`、`GULLRWF1` 的 `rated_capacity_source` 标明使用观测最大功率替代容量。程序按提供表使用这些分母，同时在日志、`dataset_summary.csv`、`run_manifest.json` 和图注草稿中标记 `capacity_is_proxy`，不把它们当作已核实的额定容量。正式论文解释物理 CF 前应核实这四项。程序不会自行从真实时序估算或替换容量。

`inputs.segment_layer` 也支持显式选择 `data_process`，或 `prefer_data_process`（逐场站优先该层、缺失才选 aligned，并记录回退名单）。**本次配置与默认值均为 aligned_segments；任何模式都不会合并两层。** 场站数、片段数由输入动态决定。

下文的目录扫描方式保留给没有这些索引表的数据；配置 `inputs.segments_manifest` 后，以清单作为输入，不再扫描 `data_dir`。

## 2. 数据目录与“同一个数据集”的定义

```text
retained_csv_root/
  farm_A.csv                  # 未切割原始文件：默认忽略
  farm_A_seq/
    farm_A_0.csv
    farm_A_1.csv               # 与 farm_A_0.csv 一起计为 farm_A
  farm_B_12_seq/
    farm_B_12_0.csv            # 原始 ID 为 farm_B_12，不会误改成 farm_B
metadata/
  farm_A.json                 # 或 farm_A_000000.json 等窗口 JSON
  farm_B_12.json
```

切割脚本输出的格式可直接读取，无需删除注释：

```csv
# source: /original/csv/farm_A.csv
# segment: 0
# range: [0, 480)
# start_date: 2020-01-01 00:00:00
# end_date: 2020-01-05 23:45:00
# n_points: 480
timestamp,power
2020-01-01 00:00:00,12345.0
2020-01-01 00:15:00,12600.0
```

以上数据行仅示意 CSV 结构。

分组规则：

1. 优先用注释 `# source:` 的原始文件名识别数据集，支持 Linux/Windows 路径。
2. 没有该注释时，只有 `{原始名}_seq/{原始名}_{数字}.csv` 才按切割片段归并。
3. 不会盲目删除所有文件名末尾的数字，避免把本来不同的风场合并。
4. 同名但来自不同原始路径的文件默认报错，必须明确指定映射。
5. 默认 `segments_only: true`，防止同时把未切割原文件与保留片段算入。
6. 一个原始数据集产生一行风场统计；时间覆盖每小时也最多计数一次。片段数单独记录，不当作数据集数。

若同一个物理风场有多个独立原始文件，程序不会自行猜测其身份。可显式归并或区分：

```json
"source_dataset_map": {
  "/archive/year1/farm_A.csv": "farm_A",
  "/archive/year2/farm_A.csv": "farm_A",
  "renamed_folder/part_0.csv": "farm_A"
}
```

映射键可以是精确的 `# source:` 值，也可以是相对于 `data_dir` 的 CSV 路径（使用 `/`）。有多个来源时请明确映射每个来源。切割边界即使紧邻，也不跨界计算爬坡、STL 或完整日曲线。

## 3. JSON、容量与单位

推荐结构：

```json
{
  "dataset_name": "farm_A",
  "site_type": "offshore",
  "rated_capacity_mw": 50,
  "value_unit": "kW"
}
```

- 支持嵌套字典中的 `site_type`、`farm_type`、`onshore_offshore`、`Onshore/Offshore` 等字段。
- 没有结构化类型时，支持 `farm_description` 中明确的 `onshore wind farm` / `offshore wind farm`。
- 不会因为环境描述含有 `offshore roughness` 就把陆上风场判成海上。
- 额定容量支持 `rated_capacity_kw/mw`、`capacity_kw/mw`、`installed_capacity_kw/mw`。
- 兼容现有描述中的 `summing to roughly 106.6 MW of rated capacity`；若描述只是粗略值，正式分析应提供经核实的结构化容量或配置覆盖值。
- 文件名自动匹配 `数据集名.json` 或 `数据集名_数字.json`。多个窗口 JSON 的元数据必须一致。
- JSON 内若提供 `description.dataset_name` / `dataset_name` / `dataset_id`，会校验其与目标元数据 ID 一致。
- 不自行凭文字中的风机型号/单机功率猜测总容量，也不自行用观测最大值估计装机容量；清单模式显式提供的容量替代值会按前述规则标记。

**单位必须明确提供。** 配置项优先于结构化 JSON；不会从 `value` 列、数值大小或自由文本的 `kwh` 猜单位。

| CSV 数值含义 | `value_unit` | 容量因子计算 |
|---|---|---|
| 瞬时功率或区间平均功率 | `W` / `kW` / `MW` | 换算为 kW 后除以额定容量 kW |
| 每采样间隔的能量 | `Wh` / `kWh` / `MWh` | 换算为 kWh，除以间隔小时数，再除以额定容量 kW |
| 已有容量因子 | `capacity_factor` / `cf` | 直接使用，无需额定容量 |

不接受累计电量表读数或 z-score 归一化序列。需先在上游转换为每间隔能量/原始功率。物理意义不能靠自动识别保证。

例如 `62.5 kWh / 15 min / 1000 kW = 0.25`，不能直接用 `62.5 / 1000`。缺容量或单位时程序停止。

## 4. 配置与运行

复制 `examples/config.json` 为 `local_config.json`，填写服务器数据、JSON 和输出目录。相对路径以配置文件所在目录为基准。

最小配置示例（仅在确认所有 CSV 都是 kW 时使用）：

```json
{
  "data_dir": "/server/data/retained",
  "metadata_dir": "/server/data/json",
  "output_dir": "/server/output/wind_corpus_v1",
  "palette": "viridis",
  "defaults": {"value_unit": "kW", "timezone": "UTC"}
}
```

不同数据集可以分别配置：

```json
"datasets": {
  "farm_A": {
    "time_column": "date",
    "value_column": "power",
    "value_unit": "kW",
    "rated_capacity_kw": 50000,
    "timestamp_format": "%Y-%m-%d %H:%M:%S",
    "timezone": "Europe/London",
    "label": "Farm A"
  },
  "farm_B_12": {
    "metadata_file": "/server/json/B_window.json",
    "metadata_id": "B",
    "value_unit": "kWh",
    "interval_minutes": 15,
    "timestamp_position": "end"
  }
}
```

首先仅验证身份映射、元数据、单位和列名，不分析、不出图：

```bash
python -m wind_dataset_plot --config local_config.json --validate-only
```

确认后在服务器完整执行：

```bash
python -m wind_dataset_plot --config local_config.json
```

已有非空输出目录默认拒绝写入；推荐每次使用新目录。`--overwrite` 允许覆盖同名产物，但不会清理旧版本不再生成的文件，判断本次产物时应以本次日志/清单为准。

## 5. 时间处理：不穿越被切除的区域

- 每个 CSV 内的时间必须按顺序排列，重复时间点数值相同则去重，不同则报错。
- 非有限数值会剔除并形成断点，记录在质量审计中。
- 不跨文件边界，不跨缺失时段插值，不把删除前后的点直接连接。
- 推断原始间隔时，仅使用文件内时间差的众数；可用 `interval_minutes` 覆盖。发现非整数倍间隔时停止，避免误解不同采样率。
- 原始间隔需不超过 1 小时且能整除 1 小时。小时边界对齐后，只有样本齐全的小时才保留。缺一个原始采样点，该小时就不参与统计。
- `timestamp_position: start` 表示时间戳标记间隔起点；`end` 表示终点，会先减去一个原始间隔。
- 未带时区的时间按 `defaults.timezone` 或数据集覆盖值解释；默认 UTC 是配置约定，不是从数据推断出的当地时区。
- 数字时间必须指定 `timestamp_unit`（`s/ms/us/ns`）。不会把整数行号当作真实时间。
- `18/01/01` 这种不明确格式必须指定 `timestamp_format: "%y/%m/%d %H:%M"`。
- 统计与覆盖使用 UTC 小时序列。日模式使用 `analysis.clock_timezone`，默认 UTC；跨洲风场因此默认比较同一 UTC 时钟，而非当地太阳时。若研究需要当地时钟，应按共同时间区间分组分析或明确调整设计。
- 日曲线要求在同一个连续片段中完整覆盖 00:00–23:00；不接受跨片段拼出的天，不接受 DST 的 23/25 小时天。

## 6. 六张图与科学含义

| 图 | 展示形式 | 计算基础 |
|---|---|---|
| a | 数据集 × 运行特征热图 | 小时 CF 的 IQR、小时绝对爬坡 P95、低/高出力时间比例；每列跨数据集 z-score |
| b | 每个数据集的点与区间 | 中位数、25–75%、10–90% 经验分位区间；不是置信区间 |
| c | 时间覆盖色带 | 每个 UTC 小时有完整数据的原始数据集数；没有数据的时间为 0 |
| d | 日/周周期强度配对点图 | 在各连续小时窗口独立计算 STL，每个数据集汇总成一对点 |
| e | 日均出力 × 日内变化幅度的密度图 | 完整日 CF 均值与相邻小时绝对变化均值，颜色为日样本数量 |
| f | 单张日模式热图，旁列样本占比 | 24 维 CF 日曲线聚类、各组逐小时中位数；不再输出 16 张小曲线 |

默认生成每个面板和组合图，配色只选 `viridis` 或 `plasma`，海陆类型另用形状辅助区分。数据集超过 `rows_per_page` 时，a/b/d 自动分页，并省略拥挤的组合图；f 行数随实际聚类结果变化。

没有固定 31 个数据集、12/19 海陆数量、6,200 个日样本或 16 类。标题、图注草稿、数量、年份、占比均来自本次输入。

### 周期强度

STL 独立使用日周期 24、周周期 168（小时），`robust=True`、`seasonal=7`。对每个无断点窗口计算：

```text
strength = max(0, 1 - Var(remainder) / Var(seasonal + remainder))
```

默认一个窗口最多 1,344 小时，需至少 3 个完整周期；窗口不重叠，不拼接短片段。各有效窗口强度按窗口小时数加权平均，得到每个原始数据集的一个指标。日、周拟合互相独立，并非多重季节性分解，也不保证周指标已经移除日周期。常量/方差不可定义或长度不足记 NA，不填成 0。

`max_stl_windows: 0` 使用所有合格窗口；若为正整数，按时间顺序等间隔选择窗口。输出同时记录合格/实际使用窗口数量和小时数。

### 日模式聚类与抽样

- 直接对原始 CF 的 24 维日向量做 KMeans；不对日向量逐日 z-score，也不在 UMAP 上聚类。
- 默认 `clusters: "auto"`：在 2 至 `max_clusters` 间，用固定随机种子拟合并比较 silhouette。自动选择是探索性摘要，不表示自然界恰好有这些物理类别。
- 最多随机选 `cluster_fit_limit` 天用于拟合；silhouette 最多用 `silhouette_limit` 个拟合样本。拟合后给全部已选择日曲线分配类别。
- `clusters: 8` 等正整数可固定 K；数据不足时降至可用数量并警告。只有一种有效曲线时输出 1 类；没有完整日时输出明确的“无可用数据”面板。
- `max_daily_profiles_per_dataset: 0` 保留全部完整日；正整数则对每个原始数据集固定种子抽样，**不会按片段分别抽样**。
- e/f 每个已选择日样本权重相同，因此长期数据集可能贡献更多日样本。a/b/d 则每个原始数据集一行。清单记录抽样规则与实际数量。
- f 按各类平均 CF 排序，标注该类占已选择日样本的比例；不在图上散放小曲线。

### 解释限制

这里的“原始时序”指所选层片段内未归一化的原始数值，不代表恢复被删除区间。出力分布、爬坡比例和周期性会受到该层保留规则影响。采用 `aligned_segments` 时应表述为 **retained aligned corpus**；只有确认它就是模型使用的训练语料时，才称为 retained training corpus。不能代表未切割完整风场的无偏长期统计。

CF 超出 [0,1] 会保留、审计并警告；不会静默裁剪。请检查真实单位、容量、限电/异常记录等。特征值差异和模式多样性不能单独证明模型预测性能提升。

## 7. 输出

```text
results/
  figures/                    # 独立面板及可用时的组合图：PNG / PDF / SVG
  tables/
    dataset_summary.csv       # 每个原始数据集一行，含特征、分位数、STL 使用量
    segment_inventory.csv     # 每个切割片段来源及实际保留样本数
    quality_audit.csv          # 非有限值、重复、CF 越界、不足完整小时的计数
    coverage_hourly.csv        # 原始数据集去重后的逐小时覆盖
    daily_statistics.csv      # 完整日身份、日期、均值、变化幅度及模式
    daily_profiles.npz        # 24 维向量；行顺序与 daily_statistics.csv 相同
    pattern_summary.csv       # 类别数量与日样本占比
    pattern_medians.csv        # 绘制 f 的逐小时中位数
    cluster_selection.csv     # 自动选 K 时的候选 silhouette
  run_manifest.json           # 生效配置、数据集/元数据映射、版本、实际数量
  figure_files.json           # 本次实际生成的图文件列表
  figure_description.md       # 基于本次数据的英文图注草稿，投稿前人工复核
```

输出记录可能含服务器数据路径，发布结果前自行检查。代码仓库不包含真实输入文件。

## 8. 本地/服务器测试

```bash
python -m unittest discover -s tests -v
```

测试包括原始数据集归并、数字后缀保护、原文件与片段混入防护、元数据冲突、单位换算、重复和冲突时间点、不跨切割边界、缺失小时/完整日、DST、覆盖去重、周期强度、动态聚类、viridis/plasma、分页及六面板 PNG/PDF/SVG 完整合成测试。不会访问用户真实 CSV 数据。

## 方法参考

- [STL implementation](https://www.statsmodels.org/stable/generated/statsmodels.tsa.seasonal.STL.html)
- [Seasonal-strength definition](https://otexts.com/fpp3/stlfeatures.html)
- [KMeans](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.KMeans.html)
- [Silhouette score](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.silhouette_score.html)
