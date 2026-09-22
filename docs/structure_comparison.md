# 新增图：风场数据的分布与动态差异

这一张独立图沿用原文 b 图“小提琴形状＋风场散点”的视觉思路，扩展为三个并排面板。它与四块总览主图一同输出，文件为 `figures/farm_structure_comparison.png/pdf/svg`。配置 `plots.structure_comparison` 默认为 true；设为 false 可关闭。此选项仅对 clear 布局生效。

## 怎么读

- 每一个小点代表一个原始风场，不标注风场名字。切割后的多个片段不会变成多个点。
- 紫色为海上、绿色为陆上（viridis 默认色）；也可配置 plasma。
- 每组黑色短横线是该组风场指标的中位数。
- 半小提琴在某个高度越宽，表示更多风场集中在这个取值附近。两组最大宽度一致，所以宽度不能用于比较风场总数；有效数量见 n。
- 散点横向移动只是为了避免遮挡，只有纵坐标具有数值意义。

**a 典型出力（Typical output）：这些风场平时处于什么出力水平？** 每座风场先求全部完整小时出力的中位数，一个点代表这一中位数。点越高，该风场的典型出力越高。海陆两组整体位置可比较典型水平，组内点的分散程度显示同一类型风场之间的差别。

**b 出力范围（Output spread）：风场的出力集中，还是跨越很大的范围？** 每座风场用小时出力的第 75 百分位减去第 25 百分位，得到中间一半记录所覆盖的范围。例如 25% 到 65% 对应 40 个百分点；这两个数是解释用例，不是真实结果。点越高，常见出力范围越宽。它反映出力分布宽度，不反映先后顺序；变化缓慢的风场也可能覆盖很宽的出力范围。

**c 较大的小时变化（Large hourly changes）：较大的相邻小时变化有多大？** 在同一连续段内计算相邻小时出力差的绝对值，再取第 95 百分位。它是较大变化的幅度指标，不是最大值，也不表示大变化发生得更频繁。点越高，该风场较大的小时变化幅度越大。它补充了 a/b 无法表达的相邻时间点变化。

因此，这张图把“典型水平、分布宽度、短时变化”分开展示。只有真实结果显示差异，才能写哪些组更高、更分散；模拟预览仅说明样式。三幅都是单个指标的边际分布，不展示指标之间的相关性，也不能据此断言形成了独立的物理类别。

## 与原文 b 图的区别

原图的小提琴合并了小时观测，散点却是每个风场的中位数，两者代表的统计层次不同。新版的小提琴与散点都来自风场级指标：每座风场等权，不因记录更长或切割更多而在组分布中占更大权重。该调整更直接地展示风场之间的差异。

所有指标使用完整小时功率、按容量分母归一化后计算。功率原单位 MW，百分比显示乘 100；出力范围和变化的单位为百分点。变化计算不跨缺口、文件边界。每个指标分别排除缺失值并标注有效 n；不会将缺失补零。超出常规范围的数值保留。原容量表的观测最大值替代容量事项仍适用。

半小提琴使用 Gaussian KDE、Scott 带宽，在每组观测最小值至最大值之间绘制，并把各组最大宽度归一化到相同值。单风场或常数分布只画散点和中位数，不虚构密度。半小提琴不是置信区间，不做显著性或因果判断。三面板采用各自物理坐标范围，不能比较小提琴的屏幕高度来判断哪个指标更重要。

## 服务器生成

正常运行新版完整流程会自动增加这张图及 `tables/structure_summary.csv`。如果服务器已经有旧流程生成的 `dataset_summary.csv`，其中已含 `cf_median`、`cf_iqr`、`ramp_p95`，只需重画这一张，无需重新扫描原始时序：

```bash
git pull --ff-only origin main
python -m wind_dataset_plot.structure_plot \
  --summary /path/to/results/tables/dataset_summary.csv \
  --output /path/to/results/structure_comparison_v1 \
  --palette viridis
```

输入必须是同一套分析流程导出的、每个原始风场一行的统计表；不能直接传入原始 `power` CSV 或一段一行的清单。输出目录须为空或尚不存在。该命令输出图像、组汇总表和输入路径记录；解释容量等信息时仍需保留原分析的质量审计和 manifest。

## 英文图注

**Differences in wind-farm operating characteristics.** Each point represents one original wind farm, grouped by offshore or onshore location. **a,** Median hourly power output, expressed as a percentage of the farm-specific capacity denominator. **b,** Within-farm interquartile range of hourly output. **c,** Within-farm 95th percentile of absolute changes between consecutive hourly values. Ranges and changes are expressed in percentage points. Hourly changes are calculated only within continuous retained segments. Half-violins show Gaussian kernel-density estimates of the farm-level descriptors using Scott bandwidth, restricted to the observed group ranges and normalized to equal maximum widths. Black lines indicate group medians. Horizontal jitter aids visibility and has no quantitative meaning. Each farm contributes equally; available sample sizes are shown separately for each panel. Density shapes are omitted for singleton or constant groups. The figure describes differences in output level, distributional spread and short-term changes in the retained corpus; it does not establish distinct physical classes or causal effects of site type.
