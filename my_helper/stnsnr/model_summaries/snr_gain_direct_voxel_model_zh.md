# SNr 增益直接 Voxel-Level 模型

## 研究问题

哪些 SNr voxels 的 SNr-component 刺激暴露与在 STN 刺激基础上加入 SNr 后的额外获益相关？

这是一个局部 SNr 刺激 sweet spot 模型。它直接检验 voxel-level SNr E-field 暴露，而不是下游 target connectivity。

## 终点

两个终点分别建模：

```text
Chronic domain-specific gain:
  Y_AB3m_domain = raw STN+SNr 3-month clinical score for the selected domain
  covariates = Y_STN3m_domain + DeltaSTNScore_3m_domain

Immediate motor gain:
  Y_ABimmediate_motor = raw STN+SNr immediate motor score
  covariates = Y_STN3m_motor + DeltaSTNScore_immediate_motor
```

`Y_STN3m` 控制加入 SNr 前的临床状态。`DeltaSTNScore` 控制 combined 阶段 STN component reprogramming，它定义为 endpoint/domain-matched predicted STN efficacy-map alignment 的变化，而不是原始程控参数变化。

主 estimand 是 STN-change-adjusted local SNr component exposure-response association：

```text
Y_AB_post ~ X_SNr_component(v) + Y_STN3m_domain + DeltaSTNScore_domain
```

同时报告一个不包含 `DeltaSTNScore` 的 clinical optimized strategy sensitivity model：

```text
Y_AB_post ~ X_SNr_component(v) + Y_STN3m_domain
```

如果两类 map 明显不一致，应解释为 SNr exposure pattern 与 STN component reprogramming 强耦合。

## 输入

- STN+SNr 3 个月和 STN+SNr immediate programming 的 SNr-component stimulation fields。
- 来自 `SNr-connected regions` 的 SNr seed masks。
- STN-only 3 个月 raw score 和 post-combination raw scores。
- 由 pre-SNr STN-only data 训练得到的、针对各量表或症状域的 STN-only efficacy maps。
- 每个 endpoint 对应的 `DeltaSTNScore`，由相应 STN efficacy map 计算。
- 左右 SNr homologous voxel mapping QC 输出。

优先 STN adjustment 定义为：

```text
S_STN(E) =
  sum_{u in Omega_STN} E(u) * M_STN(u)
  / (sum_{u in Omega_STN} E(u) + lambda)

DeltaSTNScore_3m =
  S_STN_domain(E_STN_component,STN+SNr3m)
  - S_STN_domain(E_STN_component,STN-only3m)

DeltaSTNScore_immediate =
  S_STN_motor(E_STN_component,STN+SNrImmediate)
  - S_STN_motor(E_STN_component,STN-only3m)
```

对于低分更好的量表，`M_STN = -theta_STN`；对于 SE-ADL，`M_STN = theta_STN`。STN map 必须只使用加入 SNr 前的 STN-only outcomes 训练。

## 特征构建

以右侧 SNr 作为 canonical voxel grid。对每个右侧 canonical voxel center `c_R(v)`，定义同源左侧连续坐标：

```text
c_L(v) = phi_inverse_L_to_R(c_R(v))
```

用 trilinear interpolation 采样左侧 SNr E-field：

```text
E_L_to_R_i(v) = interp_linear(E_L_i, c_L(v))
```

患者层面的双侧 SNr 暴露：

```text
X_SNr_i(v) = (E_R_i(c_R(v)) + E_L_to_R_i(v)) / 2
```

主分析中，`X_SNr_i(v)` 是 SNr-component-specific exposure，不是组织实际接受的 total field。运行以下 field-definition sensitivities：

```text
X_SNr_component(v) = SNr-component field within SNr
X_SNr_total(v)     = total STN+SNr field within SNr
X_SNr_residual(v)  = residualized total field after regressing out STN-component field
X_SNr_shape(v)     = X_SNr_component(v) / (sum_u X_SNr_component(u) + lambda)
```

`X_SNr_total` 对应 SNr 内实际 total tissue exposure。`X_SNr_shape` 用于区分空间形状效应和整体剂量效应。

由于 STN 和 SNr 解剖上相邻，增加 border-zone sensitivity maps：

```text
SNr_eroded_0p5_to_1p0mm
d(v, STN) > 1.0 mm
d(v, STN) > 1.5 mm
cor(X_SNr_component(v), DeltaSTNScore)
```

与 `DeltaSTNScore` 高共线的 voxels，例如 `abs(r) > 0.6`，应降低其 SNr-specific 解释强度。

Paired mask：

```text
Omega_pair = {v in right SNr mask: P_left_to_R(v) > 0.5}
```

Coverage mask：

```text
Coverage(v) = sum_i 1[X_SNr_i(v) > tau]
tau = 0.2 V/mm
```

Full-sample map 主规则使用 `Coverage(v) >= 8/16`。在 LOOCV 中，必须在每个 training fold 内定义 mask：

```text
Coverage_minus_t(v) = sum_{i != t} 1[X_SNr_i(v) > tau]
```

Fold 内主规则使用 `Coverage_minus_t(v) >= 8/15`，并将 `>= 6/15` 或 `>= 5/15` 作为放宽敏感性分析。

## 统计模型

对每个 endpoint 和 voxel `v`：

```text
Y_AB_post_domain_i = alpha_v
            + theta_SNr(v) * X_SNr_component_i(v)
            + beta_v       * Y_STN3m_domain_i
            + gamma_v      * DeltaSTNScore_domain_i
            + error_i,v
```

Benefit-oriented map：

```text
M_SNr(v) = -theta_SNr(v)   for lower-is-better scales
M_SNr(v) =  theta_SNr(v)   for SE-ADL
```

患者层面的 direct voxel score：

```text
SweetSpotScore_i =
  sum_v X_SNr_i(v) * M_SNr(v)
  / (sum_v X_SNr_i(v) + lambda)
```

最终预测模型：

```text
Y_AB_post_domain_i = alpha
            + delta * SweetSpotScore_i
            + beta  * Y_STN3m_domain_i
            + gamma * DeltaSTNScore_domain_i
            + error_i
```

## 验证

- Chronic gain 和 immediate gain 分别建模。
- 对 chronic 3 个月结局，在数据支持时运行 domain-specific models：motor、axial/gait、nonmotor、total、QoL 或 ADL。
- 对 immediate outcomes，使用 motor-specific `Y_STN3m_motor` 和 motor-specific `DeltaSTNScore_immediate_motor`。
- 使用 fully nested leave-one-patient-out cross-validation。
- Coverage mask 和 voxel maps 必须只用 training patients 定义和拟合。
- 严格 out-of-sample prediction 中，STN efficacy map 必须在每个 outer fold 内训练，再计算 fold-specific `DeltaSTNScore`。
- 报告用于构建 `DeltaSTNScore` 的 STN efficacy-map validation：LOOCV `Q2`、相对 `Y_STN3m ~ Y_Preop` 的改进、以及 STN map stability。如果 STN map 不稳定，`DeltaSTNScore` 应降级为 exploratory adjustment。
- 与 covariate-only prediction 比较：`Y_AB_post_domain ~ Y_STN3m_domain + DeltaSTNScore_domain`。
- 与不包含 `DeltaSTNScore` 的 clinical optimized strategy model 比较。
- 运行 `DeltaSTNPhys` 敏感性分析，使用 outcome-independent STN-change 指标，例如 charge-rate change、raw STN e-field energy change、STN VTA overlap change 或 STN field centroid distance。
- 报告 component-field、total-field、residual-field、shape-normalized、eroded-SNr、distance-to-STN 和 collinearity sensitivity results。
- 报告 LOOCV Pearson `r`、Spearman `rho`、MAE、RMSE、`Q2` 和 patient-level Freedman-Lane permutation P value。`n = 16` 时不要把 voxel-wise P values 作为主要证据。

## 下游可视化

对 chronic gain 和 immediate gain 分别导出：

```text
direct_voxel_SNr_coverage.nii.gz
direct_voxel_SNr_coef.nii.gz
direct_voxel_SNr_sweet_sour.nii.gz
direct_voxel_SNr_stability.nii.gz
direct_voxel_SNr_bootstrap_se.nii.gz
direct_voxel_SNr_paired_mask.nii.gz
direct_voxel_SNr_total_field_sensitivity.nii.gz
direct_voxel_SNr_residual_field_sensitivity.nii.gz
direct_voxel_SNr_shape_normalized_sensitivity.nii.gz
direct_voxel_SNr_distance_to_STN.nii.gz
direct_voxel_SNr_deltaSTN_collinearity.nii.gz
direct_voxel_SNr_sweetspot_scores.csv
direct_voxel_SNr_loocv_predictions.csv
direct_voxel_SNr_permutation_summary.csv
direct_voxel_SNr_homologous_mapping_qc.json
```

显示 map 时叠加 coverage overlays。低覆盖 SNr voxels 显示为透明或灰色。

## 解释边界

该模型是 SNr add-on benefit 的局部 SNr / STN-SNr border-zone 刺激关联模型。它不是 network mechanism model，也不应被解释为刺激单个 SNr voxel 必然产生获益的纯因果证据。由于 STN 和 SNr 相邻，表面上的 SNr sweet voxels 可能反映 dorsal SNr、ventral STN、STN-SNr border zone 或 passing fibers。除非使用外部 STN efficacy map，否则 `DeltaSTNScore` 是 same-cohort、pre-SNr-derived nuisance adjustment，在小样本中可能有噪声。

主模型估计 STN-change-adjusted SNr add-on association，而不是 optimized combined STN+SNr programming strategy 的总体真实世界效果。
