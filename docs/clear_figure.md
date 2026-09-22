# 四块主图：直接展示数据特征

本版本对应 `plots.layout: "clear"`（默认）。a 为无填充的海陆出力分布曲线，b 为匿名风场散点，c 为原文样式的竖向窄时间覆盖热图，d 为海上/陆上各月份的平均出力曲线。周期强度和完整日模式放到补充图。正式图像不包含图名、面板编号、样本数标注或底部解释文字，便于后期排版；保留坐标轴、图例和色条。本文的 a–d 仅用于说明与文件名对应关系。

另附 [风场结构对比图](structure_comparison.md)，用半小提琴和风场散点展示典型出力、出力范围与较大的小时变化。默认额外生成 `farm_structure_comparison`，与本页的四面板总览分别保存；设置 `plots.structure_comparison: false` 可关闭。

## 四个面板分别回答什么

| 面板 | 问题 | 一眼读图的方法 |
|---|---|---|
| a Output distribution | 数据经常处于哪些出力水平？ | 横轴为容量百分比，纵轴为每个等宽区间的时间占比，海上/陆上两条曲线直接对比 |
| b Differences among farms | 风场之间的平均出力和小时变化有多大差异？ | 每点一个匿名风场，越靠右平均出力越高，越靠上平均变化越大 |
| c Temporal coverage | 哪些时期有更多风场记录？ | 纵轴为时间；颜色越接近色条的高值端，同一小时有完整记录的风场越多 |
| d Output by month | 哪些月份的平均出力较高或较低？ | 横轴 1–12 月，纵轴平均出力百分比；海上/陆上各一条线，点越高表示该月平均出力越高 |

a/b 分别保留了原文“输出分布”和“风场差异”的问题；c 展示各个时期的数据覆盖；d 展示一年中不同月份的出力水平。c 数的是有记录的风场，d 算的是出力，两个面板回答不同问题。PCA/UMAP 投影轴不再出现在主图。不能沿用旧图的解释方差、silhouette 或固定类别数。

## 面向非专业读者的逐图解释

**a：这些风场平时发出多少电？** 100% 代表功率等于容量分母，50% 代表一半。曲线在某个出力区间越高，说明该类风场处于这个区间的时间越多。例如，横轴 45% 对应 40–50% 区间；若纵轴为 15%，含义是“组内风场平均有 15% 的有效小时处于这个出力区间”。这不是发电量占比，也不是某个瞬时功率恰好出现的概率。海上和陆上的曲线可直接比较出力水平分布。

**b：不同风场的出力和变化幅度是否相似？** 每个点代表一个风场。向右代表平均出力较高，向上代表相邻小时的平均变化较大。例如，横轴 40%、纵轴 5 个百分点，表示该风场平均出力为容量的 40%，相邻有效小时之间平均上下变化 5 个百分点。右下方表示平均出力较高且小时变化较小；不能把它直接解释为预测更容易、效益更高或模型更好。

**c：我们在什么时期拥有多少数据？** 这是竖向窄色带，年份从下向上增加，右侧标出时间，底部色条给出风场数。例如某段时间的颜色对应 80，表示这些小时中有 80 个不同风场提供完整小时记录；同一风场切成多个文件也只计一次。颜色只表达数据覆盖，不表达功率高低、停机或退役。横向宽度只用于显示颜色，没有第二个数据维度。没有记录的小时仍显示为零。

**d：哪些月份出力较高，哪些月份较低？** 横轴是 1–12 月，纵轴是平均功率占容量的百分比，两条线分别表示海上和陆上。先把每个风场各年的同一月份小时出力放在一起求平均，再对组内有数据的风场等权平均。例如，某组 1 月为 45%、7 月为 30%，表示其保留记录中 1 月平均出力较高。这两个数仅为读图举例，不是真实结果。45% 不代表该月占全年发电量的 45%。曲线只描述当前数据：各月的风场、年份及保留小时可能不同，因此不能仅凭峰谷就声称发现了普遍的季节规律，更不能把全球数据中的某月份统一叫作冬季或夏季。

**补充 S1：是否存在重复的日/周结构？** 两个箱体汇总各风场在 24 小时、168 小时尺度的 STL 季节强度。数值接近 1 表示该拟合尺度的重复结构较强，接近 0 表示较弱；不是模型精度。它需要方法知识，因此不放主图。

**补充 S2：一天的出力形态有哪些常见类型？** 每行一个聚类，横轴为一天的小时，颜色为该类的小时中位出力，右侧为该类在已选完整日中的占比。它用紧凑热图代替多张小曲线图；聚类只是数据摘要，不是已验证的物理类别。

## 统计口径

**共同单位。** 数值先按容量表归一化，图中乘以 100，显示为容量百分比。平均小时绝对变化也乘 100，单位为百分点；例如 30% 到 40% 的变化是 10 个百分点，不是相对增长 10%。四个观测最大功率替代容量的既有核查事项仍适用，改图不会修正容量分母。

**a 出力频率。** 每个风场的完整小时出力按 [0,10), [10,20), …, [90,100]% 统计，最后一个常规区间包括恰好 100%。先将每个风场的计数除以全部有效小时数，再对海陆组内风场等权平均。曲线连接区间中心，不做平滑、拟合或面积填充。图中仅显示 0–100% 的十个常规区间，不显示 `<0` / `>100` 及其标记。尾部值仍在原始分母、十二区间汇总表和质量审计中保留，不裁剪、不并入边界，也不因隐藏而重新归一化。因此有尾部值时，图中十个区间的频率之和可以小于 100%。全部十二区间合计为 100%，这不是曲线下面积。组汇总导出到 `output_distribution.csv`。

**b 风场散点。** 横轴为风场全部保留完整小时的平均出力；纵轴为同一连续段内相邻小时绝对差的平均值。每个风场一份记录，不跨缺口和切割边界计算变化。无有效相邻对的场站不能提供纵轴值，予以排除。图内不标场站名，但审计表保留身份。

**c 时间覆盖。** 每个 UTC 小时统计提供完整记录的不同原始风场数，同风场最多一次。将小时计数按时间顺序画成单列窄热图，不求月均值、不插值；色标范围为 0 至本次纳入风场总数，实际覆盖峰值可以低于总数。完整小时计数导出为 `coverage_hourly.csv`。`coverage_monthly.csv` 仍保留为辅助统计表，但不再是 c 的绘图来源。窄色带只能概览长时段覆盖，精确小时数应读取 CSV。

**d 各月份平均出力。** 使用全部保留的完整小时，不要求整天完整，不受日样本抽样上限影响。月份按 `analysis.clock_timezone`（默认 UTC）确定。同一风场的同一日历月跨年份合并，按小时等权求均值；再对相应海陆组中该月有有效记录的风场等权平均，乘 100 后绘图。每个风场每月最多贡献一个均值，不因切割成更多文件而增加权重。风场内部，拥有更多保留小时的年份贡献更大；不是先按年等权。缺失月份为 NaN，线段断开，不填零、不插值，也不额外拟合或平滑。真实零出力照常参与统计，超出 0–100% 的值不裁剪。没有置信带。`monthly_output.csv` 导出每组每月的平均出力和风场数；`dataset_summary.csv` 的 `month_XX_mean_cf` / `month_XX_hours` 保存每个风场各月的出力均值和有效小时数。月份间参与风场可能变化，应结合计数解释差异。

**补充 S1（配置面板 e）。** 同时具有 24 h/168 h 估计的风场进入箱线图。箱体为 IQR，中线为中位数，须为 1.5 IQR 范围内的最远样本，独立点为离群值。两个 STL 单独拟合，不能解释为已从 168 h 结构中移除日周期。

**补充 S2（配置面板 f）。** 所有日聚类按平均出力排序的中位数热图，附占全部已选日样本的比例。聚类对原始归一化 24 维向量进行，受出力水平和形状共同影响。默认 UTC 时间对齐，不能据此解释各地共同的太阳时日内机制。

## 服务器使用

```bash
git pull --ff-only origin main
python -m pip install -e .
```

保留已有服务器数据路径，在 `local_config.json` 中设置新的输出目录，例如 `results/aligned_farms_clear`，并设置：

```json
"plots": {
  "layout": "clear",
  "panels": ["a", "b", "c", "d", "e", "f"],
  "formats": ["png", "pdf", "svg"],
  "dpi": 300,
  "combined": true
}
```

仅需主图时将 panels 设为 `["a","b","c","d"]`，程序会跳过补充图所需的 STL 和 KMeans，但仍计算完整日统计。完整流程：

```bash
python -m wind_dataset_plot --config local_config.json --validate-only
python -m wind_dataset_plot --config local_config.json
```

完整流程从 CSV 计算出力频率、平均小时绝对变化、逐小时覆盖和按月份的出力统计。代码不会读取截图估计数据。本次排版修改不改变这些统计口径；片段归并、aligned_segments 选择、MW 单位和容量表连接规则保持一致。服务器重新运行时建议选择新的输出目录。

输出为 `figures/main_a~d`、`figures/supplement_e/f`、`figures/figure5_clear`，各有 PNG/PDF/SVG。若只生成主图，则不输出补充图。

## Nature 排版

主图画布固定为 183 × 145 mm，普通文字 5.5–7 pt，不用 tight 裁切改变最终物理尺寸。a、b 位于左侧上排，d 位于左侧下排，c 是右侧贯穿上下的窄色带。普通单面板为 89 × 80 mm；c 单独输出为 45 × 105 mm，S2 仍为 70 × 95 mm。所有正式图像不嵌入标题或 a/b/c 等编号，后期排版自行添加；样本数保留在统计表与图注中，结构图的点/黑线/宽度说明移至图注。PDF 保留可编辑文字，优先 Arial，服务器缺少时回退到其他无衬线字体。默认色系为 plasma，也支持 viridis；c 沿用所选色系，不复制原文 c 的颜色。模拟预览保留 SYNTHETIC STYLE PREVIEW 来源标识，正式数据输出没有该标识。

这按 Nature 官方主图指南的尺寸和字号范围设计，但不表示期刊已审核或接收。正式输出后仍需检查真实数据下的边界、长日期标签和有效样本数。

官方依据：
- https://research-figure-guide.nature.com/figures/building-and-exporting-figure-panels/
- https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/

## 英文图注模板

**Output distributions, variability and temporal coverage of the retained wind-power corpus.** Power is expressed as a percentage of each farm's capacity denominator, using complete hourly observations from retained segments. **a,** Offshore and onshore output-frequency curves. Frequencies are calculated in 10-percentage-point bins for each farm and averaged within site types with equal farm weights; lines connect bin centres. Only bins within 0–100% are displayed. Observations outside this range remain in the frequency denominator and audit tables; displayed frequencies are not renormalized. **b,** Mean output versus mean absolute change between consecutive hours, with one point per farm. Changes are expressed in percentage points and calculated only within continuous segments. **c,** Temporal coverage shown as a narrow vertical colour strip. Time increases upwards; colour represents the number of distinct farms with a complete record in each UTC hour. Each original farm is counted at most once per hour, and hours without records remain zero. **d,** Mean power output by calendar month for offshore and onshore farms. Within each farm, complete hourly observations from the same calendar month are pooled across years and averaged. Available farm means are then averaged with equal weights within each site type and month. Missing months remain missing. Contributing farms, years and retained hours may differ among months; the curves describe the retained corpus rather than an isolated climatic seasonal effect. Gaps and segment boundaries are preserved throughout.

真实运行会自动生成包含风场数、片段数、有效日数和补充图说明的 `figure_description.md`。容量替代值仍由程序附注，不应删除。不要把模拟预览的数值或形状作为真实结果。
