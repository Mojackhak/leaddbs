# DBS Voxel 与 Streamline 激活阈值文献总结

## 来源概要

- 用途：为 STN/SNr DBS direct voxel 与 streamline-based / fiber-level 模型记录常见 E-field 阈值、文献出处和解释边界。
- 适用范围：Lead-DBS / sweet spot / fiber filtering / pathway activation modeling 的方法学阈值说明；不替代任何已锁定的 executable model specification。
- 核心区分：`voxel/VTA 被纳入`、`streamline 被 E-field 触碰或筛入候选集`、`axon model 产生 action potential` 是三层不同概念，不能互相等同。

## 单位换算

文献中常同时出现 `V/mm` 和 `V/m`。本文统一按：

```text
1 V/mm = 1000 V/m

0.10 V/mm = 100 V/m
0.18 V/mm = 180 V/m
0.20 V/mm = 200 V/m
0.22 V/mm = 220 V/m
0.80 V/mm = 800 V/m
1.50 V/mm = 1500 V/m
```

如果 Lead-DBS 输出的 raw `sim-efield` 图像单位为 `V/m`，则分析代码中的阈值应写成 `200`、`800`、`1500` 等数值，而不是 `0.2`、`0.8`、`1.5`。

## Voxel / VTA 模型阈值

### 1. 最常见经验阈值：0.2 V/mm = 200 V/m

在 DBS voxel、VTA、sweet spot 和 local stimulation-volume 文献里，最常见的 E-field magnitude 二值化阈值是：

```text
E(v) >= 0.2 V/mm
```

也就是：

```text
E(v) >= 200 V/m
```

Lead-DBS v3.0 文章明确把这个值描述为 Åström-style heuristic threshold：用 `0.2 V/mm` threshold E-field magnitude，生成 binary stimulation volume / VTA。这个做法适合解释为“该 voxel 位于经验性 stimulation volume 内”，不应直接写成“该 voxel 内所有神经元或轴突都被真实激活”。

因此，voxel 模型中更严谨的表述是：

```text
E(v) >= 200 V/m
=> voxel belongs to a heuristic stimulation volume / VTA proxy
```

而不是：

```text
E(v) >= 200 V/m
=> biological activation is proven at cellular or axonal level
```

### 2. Nature Neuroscience 2024：local voxel sweet spot 用 200 V/m

Hollunder et al. 的 Nature Neuroscience 2024 local sweet spot mapping 使用 `200 V/m` 作为常用、估计足以影响/激活 axons 的 E-field magnitude 阈值，并报告 `180`、`200`、`220 V/m` sensitivity analysis。该文的 voxel sweet spot 分支还要求 voxel 在足够比例的 E-fields 中被覆盖，然后在候选 voxels 内使用连续 E-field magnitude 与临床改善做 voxel-wise association。

这里需要注意两点：

- `200 V/m` 是 voxel/local sweet spot 阈值，不是该文 fiber filtering 主阈值。
- coverage rule 是“有多少 E-fields / patients 覆盖该 voxel”的纳入规则，不是 E-field 强度单位。

### 3. Lead-DBS Sweetspot Explorer：binary VTA 常用 200 V/m，continuous E-field 可用更低展示/纳入阈值

Lead-DBS Sweetspot Explorer 文档把 voxel-level stimulation representation 分为 active contact Gaussian、binary VTA 和 continuous E-field 等形式。其界面和参数说明中，binary VTA 可使用 `200 V/m` 阈值；continuous E-field 分析可以使用较低的 E-field threshold，例如 `100 V/m`，来限制远场低强度 voxels。

因此：

```text
binary VTA / stimulation volume: commonly 200 V/m
continuous E-field inclusion or display: can use lower thresholds such as 100 V/m
```

`100 V/m` 不应被解释为 axonal activation threshold；它更像 continuous E-field 分析中的低强度纳入或显示边界。

### 4. 0.18-0.22 V/mm 的敏感性解释

`180/200/220 V/m` 对应 `0.18/0.20/0.22 V/mm`。这些值适合作为 direct voxel model 的 threshold sensitivity range，因为它们围绕最常见的 `0.2 V/mm` 经验 VTA 阈值。

在 STN/SNr direct voxel 模型中，`200 V/m` 可作为 primary tau；`180` 和 `220 V/m` 应解释为 VTA / exposure definition robustness，不是新的生物学激活机制。

## Streamline / Fiber-Level 模型阈值

### 1. 0.2 V/mm 可以作为 VTA-touch proxy，但不适合作为高置信 fiber filtering 主阈值

如果一条 streamline 穿过 `E > 0.2 V/mm` 的 VTA，传统 connectivity analysis 可把它记作被 stimulation volume touched。但这只是 VTA-touch 或 weak exposure proxy，不等于 cable model 证明这条 axon 产生 action potential。

在 full-connectome fiber filtering 中，`0.2 V/mm` 通常过宽，尤其在 dTOR 等大规模 connectome 上容易纳入大量边缘触碰 streamlines，增加 weak modulation、connectome density 和 chance correlation bias。因此它更适合做 plain connected-streamline control 或低阈值参考，不适合作为当前 STN/SNr normative fiber 主 candidate threshold。

### 2. Nature Neuroscience 2024 fiber filtering：0.8 V/mm = 800 V/m

Nature Neuroscience 2024 的 DBS Fiber Filtering 分支采用比 voxel sweet spot 更高的 streamline candidate 阈值：

```text
E along streamline > 0.8 V/mm
```

即：

```text
E along streamline > 800 V/m
```

并要求 streamlines 在 cohort 中超过一定比例的 E-fields 中达到该阈值。随后，每条 streamline 上使用 peak E-field magnitude 作为连续暴露量，与临床改善做 fiber-wise association；patient-level scoring 再基于 benefit-associated streamlines 构造 Fiber R / weighted peak score。

对当前 STN/SNr normative connectome fiber model，`800 V/m` 是合理的 primary peak-E-field candidate threshold，因为它比 `200 V/m` 更接近高置信 fiber filtering，而仍比更严格的 `1500 V/m` 保留更多候选 streamlines。

### 3. Nature Communications 2024 symptom-tract model：1.5 V/mm = 1500 V/m

Nature Communications 2024 的 Parkinson's disease symptom-specific tract model 使用更严格的 tract filtering：

```text
peak E-field intensity > 1.5 V/mm
```

即：

```text
peak E-field intensity > 1500 V/m
```

并要求每条 tract 被超过一定比例的 E-fields 经过。该设定用于排除没有被 stimulation field 强烈调制、却可能因 subthreshold intensities 偶然相关而得到高 correlation 的 tracts。作者还报告，将任意阈值提高到 `2 V/mm` 或 `4 V/mm` 不会 qualitatively alter results。

对当前 STN/SNr fiber-level 模型，`1500 V/m` 适合作为 strong threshold sensitivity，而不应替代 `800 V/m` primary，除非预先把分析目标改成更保守的 high-intensity tract library。

## PAM / OSS-DBS：真正 axonal activation 不使用固定 E-field magnitude 阈值

如果研究问题是“axon 是否真正被激活”，最严格的定义不应是 `200`、`800` 或 `1500 V/m`，而应是 pathway activation modeling / axon-cable model 是否产生 action potential：

```text
activated fiber = axon model generates action potential
```

Lead-DBS v3.0 把 E-field based stimulation volumes 与 pathway/tract activation models 明确区分：后者沿 anatomical tracts 放置 axonal cable models，估计电流是否诱发 action potentials。Nature Communications 2024 的 OSS-DBS branch 也是这种逻辑：先把 electric potential 沿 fibers 输入 mammalian axon model，再根据 action potential 判定 fiber activation。

Brain Communications 的 activation metrics 文献进一步强调，thresholded E-field magnitude 只是 activation proxy；pathway activation modeling 会考虑 fiber orientation、polarity、axon model 和 fiber diameter 等因素。该方向还可能使用 probabilistic activation：

```text
p(A) = activation probability
p(A) = 1.0      all sampled fiber diameters activate
p(A) >= 0.1     at least one sampled fiber diameter activates
```

因此，PAM / OSS-DBS 分支应作为 mechanistic sensitivity 或 validation branch，不能简单用更高的 E-field threshold 替代。

## 其他非等价阈值

部分早期或替代方法使用的不是 E-field magnitude，因此不能和 `0.2/0.8/1.5 V/mm` 直接合并解释。

| 指标类型 | 例子 | 解释边界 |
|---|---:|---|
| activating function | `100 mV/mm^2` | 通常基于沿 fiber tangent 的电位二阶导数，不是 E-field magnitude。 |
| simplified conventional model | `0.15 mV/mm` | 属于特定简化模型或 activation-radius 近似，不等于 `V/mm` E-field magnitude threshold。 |
| E-field projection along fiber | 例如 `125 V/m` | 是投影到 fiber 方向的 component，可与 magnitude proxy 比较，但物理量不同。 |
| probabilistic PAM | `p(A)` threshold | 是模型化 action potential probability，不是固定 E-field intensity。 |

写作时应明确物理量，避免把 `V/m`、`V/mm`、`mV/mm^2`、projection threshold 和 `p(A)` 混作同一类 threshold。

## 对当前 STN/SNr 模型的推荐

| 模型分支 | 推荐 primary threshold | 推荐 sensitivity | 解释 |
|---|---:|---:|---|
| HF direct voxel | `200 V/m` (`0.2 V/mm`) | `180/220 V/m` | 常规 VTA / local sweet spot E-field threshold；适合 voxel exposure / VTA proxy。 |
| ULF direct voxel | `200 V/m` (`0.2 V/mm`) | `180/220 V/m` | `tau` 同时定义 ULF active、HF overlap exclusion 和 ULF-only exposure，应解释为 exposure-definition sensitivity。 |
| HF normative streamline / fiber | `800 V/m` (`0.8 V/mm`) | `1500 V/m` (`1.5 V/mm`) | `800 V/m` 对齐 Nature Neuroscience fiber filtering；`1500 V/m` 是更严格 high-intensity tract sensitivity。 |
| ULF normative streamline / fiber | `800 V/m` (`0.8 V/mm`) | `1500 V/m` (`1.5 V/mm`) | 与 HF fiber 分支保持一致；对 ULF 而言也是 exposure-definition sensitivity，因为 tau 定义 ULF-only 和 HF-overlap。 |
| OSS-DBS / PAM sensitivity | action potential | activation probability / coverage rules | 在 peak-E-field candidate universe 锁定之后运行；不得用 PAM 反向重定义 peak-E-field candidate set。 |

一句话总结：

```text
常规 DBS voxel/VTA threshold 是 0.2 V/mm = 200 V/m；
高置信 streamline fiber filtering 更常用 0.8 V/mm 或 1.5 V/mm；
真正 axonal activation 应由 PAM / OSS-DBS action potential 判定，而不是固定 E-field magnitude threshold。
```

## 注意事项与避免过度表述

- 不要把 `E > 200 V/m` 写成“组织被真实激活”；应写成 heuristic VTA / stimulation volume proxy。
- 不要把 voxel sweet spot 的 `200 V/m` 直接迁移成 full-connectome fiber filtering 主阈值；fiber filtering 文献中常用更高阈值。
- 不要把 coverage threshold 与 E-field intensity threshold 混淆。前者是“多少患者/多少 E-fields 覆盖该 voxel 或 streamline”，后者是“单个 E-field magnitude 多大”。
- 不要把 `mV/mm^2` activating function、E-field projection threshold 和 E-field magnitude threshold 放在同一列直接比较，除非明确说明物理量不同。
- PAM / OSS-DBS 分支如果用于当前项目，应在 manifest 中记录 axon model、diameter、waveform、pulse width、frequency、conductivity model 和 activation output definition。

## Citation Leads

- Lead-DBS v3.0: Horn et al. describe using a heuristic `0.2 V/mm` E-field magnitude threshold to create binary stimulation volumes and distinguish this from pathway/tract activation models based on action potentials. [PMC article](https://pmc.ncbi.nlm.nih.gov/articles/PMC10144063/)
- Hollunder et al., 2024, Nature Neuroscience: local sweet spot uses `200 V/m` with `180/200/220 V/m` sensitivity; fiber filtering uses a higher `0.8 V/mm` streamline threshold. [Publisher page](https://www.nature.com/articles/s41593-024-01570-1)
- Hollunder et al., 2024, Nature Communications: symptom-specific tract filtering uses `1.5 V/mm`, reports `2/4 V/mm` robustness, and includes OSS-DBS action-potential modeling. [Publisher page](https://www.nature.com/articles/s41467-024-48731-1)
- Lead-DBS Sweetspot Explorer documentation: describes binary VTA, continuous E-field thresholds, `VTA/E-Field Threshold`, and `Voxels covered` as separate user parameters. [Lead-DBS user guide](https://netstim.gitbook.io/leaddbs/lead-group/sweetspot-explorer)
- Brain Communications activation metrics article: compares thresholded E-field magnitude, E-field projection and pathway activation modeling, and treats E-field thresholding as an activation proxy rather than the same thing as axon-model activation. [OUP article](https://academic.oup.com/braincomms/article/7/5/fcaf301/8238244)

