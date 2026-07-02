# HF-only 3m 直接 Voxel-Level 模型

## 研究问题

哪些高频刺激 territory 内的 voxel，其 HF-only 暴露与更好的 3 个月 HF-only 临床结局相关？

这是一个局部刺激 sweet spot 模型。原 STN-only 阶段在这里解释为 HF-only DBS territory，而不是解剖学 STN-only 模型。STN/SNr mask 只用于 territory 定义、覆盖描述和可视化 overlay，不用于把模型效应硬分给某一个核团。

## 终点

主终点：

```text
Y_HF3m = raw HF-only 3-month clinical score
```

主协变量：

```text
Y_Preop = raw preoperative clinical score
```

对于低分更好的量表，系数需要 sign flip 后构成 benefit-oriented map。对于 SE-ADL，正系数本身表示获益。

## 输入

- 每侧 HF-only stimulation E-field 或 E-field-like exposure map。
- 覆盖队列相关 STN/SNr 及周围区域的 stimulation-territory mask。
- 用于 overlay 和 coverage summary 的 STN/SNr 解剖 mask。
- 来自 `subject_effect_origin.xlsx` 的原始临床分数。
- 左右 voxel correspondence 或 common-space sampling QC 输出。

## 特征构建

定义 canonical stimulation territory：

```text
Omega_HF = cohort-covered HF stimulation territory within the STN/SNr and peri-STN/SNr region
```

模型不把 overlap 或 border-zone voxel 强行分成 STN 或 SNr。左右侧暴露在 common space 中分别采样后求平均：

```text
X_HF_only_i(v) = (X_HF_left_i(v) + X_HF_right_i(v)) / 2
```

模型拟合使用 coverage mask 内的连续暴露值。active-voxel 阈值只用于 coverage/QC 以及 HF/LF overlap 归属：

```text
tau = 0.2 V/mm
Coverage(v) = sum_i 1[X_HF_only_i(v) > tau]
```

主分析优先使用 `Coverage(v) >= 8`，并以 `0.18` 和 `0.22 V/mm` 做阈值敏感性分析。

## 统计模型

对每个 voxel `v`：

```text
Y_HF3m_i = alpha_v
         + theta_HF(v) * X_HF_only_i(v)
         + beta_v      * Y_Preop_i
         + error_i,v
```

Benefit-oriented map：

```text
M_HF(v) = -theta_HF(v)   for lower-is-better scales
M_HF(v) =  theta_HF(v)   for SE-ADL
```

患者层面的 HF sweet-spot score：

```text
HFScore_i =
  sum_v X_HF_only_i(v) * M_HF(v)
  / (sum_v X_HF_only_i(v) + lambda)
```

最终预测模型：

```text
Y_HF3m_i = alpha
         + delta * HFScore_i
         + beta  * Y_Preop_i
         + error_i
```

## 验证

- 使用 fully nested leave-one-patient-out cross-validation。
- 在每个 training fold 内定义 coverage mask、拟合 voxel map、计算 HF score。
- 与 covariate-only model `Y_HF3m ~ Y_Preop` 比较。
- 报告 LOOCV Pearson `r`、Spearman `rho`、MAE、RMSE、`Q2` 和 permutation P value。
- 最终显著性检验使用 patient-level Freedman-Lane permutation。

## 下游可视化

导出：

```text
direct_voxel_HF_coverage.nii.gz
direct_voxel_HF_coef.nii.gz
direct_voxel_HF_sweet_sour.nii.gz
direct_voxel_HF_stability.nii.gz
direct_voxel_HF_bootstrap_se.nii.gz
direct_voxel_HF_scores.csv
direct_voxel_HF_loocv_predictions.csv
direct_voxel_HF_permutation_summary.csv
direct_voxel_HF_mapping_qc.json
```

使用以 0 为中心的 diverging color scale 显示 HF sweet/sour map。低覆盖 voxel 显示为透明或灰色。STN 与 SNr 边界只作为 overlay。

## 解释边界

该模型估计 HF-only 局部刺激暴露与 3 个月结局的关联。它应解释为 STN/SNr stimulation territory 内的 HF efficacy heatmap，而不是纯解剖 STN map，也不是 voxel-wise 因果证据。
