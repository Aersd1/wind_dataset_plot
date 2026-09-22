# 图 5 的统计含义与论文表述

本说明对应当前六面板聚合方案，不对应 main.tex 中旧版 PCA/UMAP 图。当前提供的路径清单选择 aligned_segments：131 个场站、1,770 个片段。真实时序尚未在本地运行；示例图中的海陆数量、年份、聚类数和分布形状均为模拟，不可直接用于论文结果。

建议总标题：**Operating characteristics and temporal structure of the wind-power corpus**。

这是一张语料描述图：解释保留数据覆盖哪些出力水平、变化幅度、时间区间和日内模式。它不能单独证明模型泛化能力、预测精度或风电数据的全球代表性。若这 131 个场站尚未确认全部属于预训练训练集，使用 corpus，不写 training corpus。

## 共同定义

CSV 的 power 是瞬时 MW。程序以 `power_MW * 1000 / rated_power_kW_used` 归一化，之后在每个完整小时内取等间隔样本的算术均值。这里不是把 MW 换算为 kWh。计算保留缺口和文件边界，不跨片段计算相邻小时变化、STL 或完整日。以下 CF 指该归一化量；只有容量分母为核实的额定容量时，它才有标准物理容量因子的含义。

当前容量表四项为观测最大功率替代值：BANC DE GUERANDE 2、BRDUW-1、BRYBW-1、GULLRWF1。正式投稿前应核实分母，或披露这些替代值并做排除/修正它们的敏感性分析。不能把最大功率归一化结果无条件称为额定容量因子。

## a — Operating-characteristic distributions

问题：海上和陆上风场各自覆盖怎样的运行特征，组内差异有多大？

每个风场先计算四个特征：小时 CF 四分位距、连续相邻小时 CF 绝对变化的第 95 百分位、CF < 0.05 的小时比例、CF > 0.8 的小时比例。每项特征在全部有效风场之间做 z-score，随后按海陆类型画分布。

横轴大于零表示高于该项特征的全体风场平均值，不表示 CF 为正；不同特征的 z-score 不是同一种物理量。小提琴是平滑密度，圆/方点为组中位数，粗线为组内 25–75% 范围。每个小提琴最大宽度相同，不能通过宽度比较海陆样本量。缺失值按特征分别剔除，最终需报告实际有效样本数。

可以据真实结果描述组间位置差异和组内异质性。没有统计检验时，不写 significant；低出力比例不能直接等同于无风时长，高出力比例也不是装机利用效率。

建议横轴：Standardized feature value (z-score)。建议图注关键词：distributions across farms，而非 uncertainty。

## b — Capacity-factor quantile profiles

问题：典型风场的出力分布是什么形状，同类型风场之间有多大差异？

先对每个风场的小时 CF 计算 P10、P25、P50、P75、P90。然后在每个分位点上，分别计算海上/陆上风场之间的中位数和四分位范围。横轴是风场内百分位，纵轴是 CF；线为风场间中位数，阴影为风场间 IQR。

例如横轴 50 处的线值是“各风场中位数的中位数”，不是所有小时合并后的中位数。每个风场等权，长记录不会因为小时多而在此面板占更大权重。阴影不是置信区间；线段只连接所计算的五个百分位，不是拟合的概率模型，也不是 CDF。

图注务必写：Lines and shaded bands denote the median and interquartile range across farms at each within-farm percentile, respectively.

## c — Temporal data coverage

问题：每个时刻，语料中有多少个风场提供完整的小时记录？

纵轴为 UTC 时间，颜色为该小时的有效风场数。同风场多个片段最多计一次。零表示没有符合完整小时要求的记录，不能解释为总发电量为零。这里描述所选保留语料的时间覆盖，不是风场投运数量、寿命或额定容量总和。

最终年份范围和最大同时覆盖数必须从 coverage_hourly.csv 读取；131 是纳入风场总数，不保证任何小时同时覆盖全部 131 个。

建议色条：Farms with complete hourly records (n)。

## d — Seasonal-strength distribution

问题：风场在 24 小时和 168 小时周期设定下的重复结构有多强，两种指标如何共同分布？

对连续小时序列分别做 period=24 和 period=168 的 STL 分解。单窗口强度为 F = max(0, 1 - Var(R)/Var(S+R))，S 为季节项，R 为残差；风场内按有效窗口长度加权汇总。横纵轴分别为两个周期的强度，颜色是六边形内的风场数量，每个有效风场只计一次。虚线表示两种强度相等。任一指标缺失的风场不进入密度图，图上记录剔除数量。

默认窗口最多 1,344 小时，至少包含指定周期的三个循环，日指标和周指标的有效窗口可能不同。两个 STL 是独立拟合，不是同时分离日周期与周周期的模型：168 小时季节项可以吸收日内结构，因此不能称为“去除日周期后的纯周效应”。强度也不是预测准确率或解释总功率方差的比例。

建议轴名：STL strength (24-h period) 与 STL strength (168-h period)。

## e — Daily output–variability distribution

问题：语料包含哪些日均出力与小时波动的组合？

每个观测单位是一个风场的一个无缺口完整日，即 farm-day。横轴为 24 个小时 CF 的平均值，纵轴为同一天 23 对相邻小时 CF 绝对差的平均值。色条显示六边形内 farm-day 数量，颜色采用对数尺度，不是概率密度或风场数量。

靠右表示较高日均出力，靠上表示较强的平均小时变化。该图不保留变化方向，不能区分上升/下降爬坡，也不直接刻画极端爬坡。每天等权，记录更长的风场可能贡献更多天；同风场相邻日期不应称为独立实验重复。

建议横轴：Daily mean CF；纵轴：Mean absolute hourly CF change；色条：Farm-days per bin (log scale)。

## f — Cluster-median daily profiles

问题：大量完整日曲线可以用哪些代表性的出力水平和日内形状概括？

每个完整日形成 24 维 CF 向量，在该空间直接做 KMeans。每行表示一个聚类，每列表示一天中的小时；颜色为该类在相应小时的 CF 中位数，行按平均中位曲线水平排序。右侧比例为该类已选 farm-day 数/全部已选 farm-day 数。每行不对应一个风场，比例不是风场占比，热图也不展示类内 IQR。

默认自动选择 K，实际类别数由结果决定，不能把示例的 6 类或旧图的 16 类写入结论。未逐日标准化，所以聚类同时受绝对出力水平和形状影响，不能称为纯形状聚类、自然物理类型或经过验证的气象机制。

默认按 UTC 对齐；跨经度的同一小时不是同一当地太阳时。因此只可描述 UTC 时刻的曲线特征，不能直接写“普遍的清晨爬坡/午间峰值”。若研究问题确实是本地昼夜机制，需要场站时区/太阳时对齐后重新分析。

建议横轴：Hour of day (UTC)；纵轴：Daily-profile cluster；色条：Median CF；右栏：Farm-days (%)。

## 可直接改写使用的英文总图注

**Fig. 5 | Operating characteristics and temporal structure of the wind-power corpus.** Statistics summarize retained records from 131 farms. Capacity-normalized power (CF) is instantaneous power divided by the capacity denominator recorded for each farm; hourly values are means of complete sets of native samples. **a,** Offshore and onshore distributions of four farm-level descriptors: CF interquartile range, the 95th percentile of absolute hourly CF changes, and fractions of hours with CF below 0.05 or above 0.8. Each descriptor is standardized across farms. Violins show smoothed distributions; symbols and thick lines indicate medians and interquartile ranges. **b,** Within-farm CF quantile profiles. At each percentile, lines and shaded bands show the median and interquartile range across farms of the same site type, respectively, not confidence intervals. **c,** Number of distinct farms with complete hourly records over time (UTC). **d,** Joint distribution of STL seasonal strengths estimated separately using 24-h and 168-h periods. Colour indicates farms per hexagonal bin; the diagonal denotes equal strengths. Farms lacking either estimate are excluded and counted in the annotation. **e,** Joint distribution of daily mean CF and mean absolute change between consecutive hours within complete days. Colour indicates farm-day counts on a logarithmic scale. **f,** Hourly median CF within clusters of 24-dimensional daily profiles, ordered by mean profile level. Percentages indicate each cluster’s share of selected farm-days. Panels a, b and d weight farms equally; e and f weight selected farm-days equally. Gaps and segment boundaries are preserved throughout.

这段图注是方法描述稿，不替代正式数据结果。保留当前四个替代容量时，应补充：**Four capacity denominators are observed-maximum proxies.** 并在 Methods/Supplementary Information 实际记录来源和敏感性分析。最终还需补齐真实海陆有效样本数、e/f 的 farm-day 总数和 f 的实际 K。分组标注的 n 为风场数，不能让读者误解为独立日样本数。

## 与 Nature 图稿要求衔接

Nature 官方主图指南给出 89 mm 单栏、183 mm 双栏、最大高度 170 mm；正文图内字体通常为最终尺寸下 5–7 pt，面板字母为 8 pt 加粗小写。采用可编辑文本及矢量线条，优先提供 PDF；去掉不必要网格、装饰和图内长段解释。不同 Nature 系列期刊应另核对目标刊的具体要求。

当前 15 × 12 inch 组合图是阅读/版式预览。不能直接缩成 183 mm 后声称符合最终字号要求：例如原 7 pt 标签等比例缩放后只有约 3.4 pt（紧裁切会略改变实际值）。投稿图须按最终物理尺寸重新排版，并核对各面板 n、颜色含义和文字可读性。图名与长解释放在图注；保持海陆配色和形状/线型一致。

官方来源（核对日期 2026-09-22）：

- https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/
- https://research-figure-guide.nature.com/figures/building-and-exporting-figure-panels/

## 与现有 main.tex 的不一致

main.tex 的旧版 Fig. 5 和相邻正文仍包括 31 个训练场站、PCA 解释率、UMAP、6,200 个日样本、16 个聚类及 silhouette=0.21 等数值。本版 a/e/f 已不再对应这些分析，不能只把 31 改为 131。应在服务器真实数据计算完成后，用当前方法描述及新结果一起替换旧段落；本说明没有改动 main.tex 或推断未计算的结果。
