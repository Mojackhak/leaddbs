# STN 3m 直接 Voxel-Level 模型

## 研究问题

哪些 STN voxel 的 STN 单独刺激暴露与更好的 STN-only 3 个月临床结局相关？

这是一个局部刺激 sweet spot 模型。它直接检验 voxel-level STN E-field 暴露，而不是 target connectivity 或 fiber-level 机制。

## 终点

主终点：

```text
Y_STN3m = STN-only 3-month raw clinical score
```

主协变量：

```text
Y_Preop = raw preoperative clinical score
```

对于低分更好的量表，模型图谱需要 sign flip 后正值才表示获益。对于 SE-ADL，正系数本身表示获益。

## 输入

- 左右 STN component 的 STN-only 3 个月刺激场。
- 来自 `STN-connected regions` 的 STN seed masks。
- 来自 `subject_effect_origin.xlsx` 的原始临床分数。
- 左右 STN homologous voxel mapping QC 输出。

## 特征构建

以右侧 STN 作为 canonical voxel grid。对每个右侧 canonical voxel center `c_R(v)`，定义其同源左侧连续坐标：

```text
c_L(v) = phi_inverse_L_to_R(c_R(v))
```

用 trilinear interpolation 在 `c_L(v)` 处采样左侧 E-field：

```text
E_L_to_R_i(v) = interp_linear(E_L_i, c_L(v))
```

定义患者层面的双侧 STN 暴露：

```text
X_STN3m_i(v) = (E_R_i(c_R(v)) + E_L_to_R_i(v)) / 2
```

配对分析 mask：

```text
Omega_pair = {v in right STN mask: P_left_to_R(v) > 0.5}
```

Coverage mask：

```text
Coverage(v) = sum_i 1[X_STN3m_i(v) > tau]
tau = 0.2 V/mm
```

主分析优先使用 `Coverage(v) >= 8`。如果覆盖过稀，可将 `>= 5` 或 `>= 6` 作为探索性放宽阈值。

## 统计模型

对每个 voxel `v`：

```text
Y_STN3m_i = alpha_v
          + theta_STN(v) * X_STN3m_i(v)
          + beta_v       * Y_Preop_i
          + error_i,v
```

Benefit-oriented map：

```text
M_STN(v) = -theta_STN(v)   for lower-is-better scales
M_STN(v) =  theta_STN(v)   for SE-ADL
```

患者层面的 sweet spot score：

```text
SweetSpotScore_i =
  sum_v X_STN3m_i(v) * M_STN(v)
  / (sum_v X_STN3m_i(v) + lambda)
```

最终预测模型：

```text
Y_STN3m_i = alpha
          + delta * SweetSpotScore_i
          + beta  * Y_Preop_i
          + error_i
```

## 验证

- 使用 fully nested leave-one-patient-out cross-validation。
- 在每个 training fold 内定义 coverage mask、拟合 voxel map、计算 sweet spot scores。
- 与 covariate-only prediction 比较：`Y_STN3m ~ Y_Preop`。
- 报告 LOOCV Pearson `r`、Spearman `rho`、MAE、RMSE、`Q2` 和 permutation P value。
- 最终显著性检验使用 patient-level Freedman-Lane permutation。

## 下游可视化

导出：

```text
direct_voxel_STN_coverage.nii.gz
direct_voxel_STN_coef.nii.gz
direct_voxel_STN_sweet_sour.nii.gz
direct_voxel_STN_stability.nii.gz
direct_voxel_STN_bootstrap_se.nii.gz
direct_voxel_STN_paired_mask.nii.gz
direct_voxel_STN_sweetspot_scores.csv
direct_voxel_STN_loocv_predictions.csv
direct_voxel_STN_permutation_summary.csv
direct_voxel_STN_homologous_mapping_qc.json
```

使用以 0 为中心的 diverging color scale 展示 sweet/sour map。低覆盖 voxel 显示为透明或灰色。如果使用 smoothing，仅使用 `1-2 mm` FWHM，同时报告 unsmoothed maps。

## 解释边界

该模型是直接的局部 STN 刺激关联模型。它回答 STN 暴露在哪里与 STN-only 3 个月结局相关。它不解释哪些下游 target 或 fiber 介导了该效应，也不应被解释为确定性的 voxel-wise 因果证据。
