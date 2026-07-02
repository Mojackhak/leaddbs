# HF-adjusted ULF-only Add-On Gain 直接 Voxel-Level 模型

## 研究问题

在加入 ULF 刺激后，哪些 ULF-only voxel 与额外疗效相关，并且这种关联在模型中已经校正患者的 HF 临床状态和预测的 HF 疗效变化？

这是一个局部 ULF-only sweet spot 模型。主问题不再定义为解剖 SNr 效应。STN/SNr 及周围区域被视为一个 stimulation territory，HF 与 ULF component 按刺激频率和 exposure overlap 进行区分。


频率定义固定为：

```text
HF  = high-frequency stimulation component, frequency_Hz >= 100
ULF = ultra-low-frequency stimulation component, frequency_Hz <= 50
```

## 终点

两个终点分别建模：

```text
Chronic domain-specific endpoint:
  Y_HFplusULF_3m_domain = raw HF+ULF 3-month clinical score
  covariates = Y_HF3m_domain + DeltaHFScore_3m_domain

Immediate motor endpoint:
  Y_HFplusULF_immediate_motor = raw HF+ULF immediate motor score
  covariates = Y_HF3m_motor + DeltaHFScore_immediate_motor
```

主要 estimand：

```text
HF-adjusted ULF-only add-on gain
```

## 输入

- pre-ULF 阶段的 HF-only stimulation field。
- HF+ULF programming 中的 HF component field 和 ULF component field。
- 由 HF-only 结局训练得到的 direct voxel-level HF efficacy map。
- HF-only 和 HF+ULF 原始临床分数。
- 用于 overlay 和 territory QC 的 STN/SNr 解剖 mask。

模型匹配的 HF adjustment 定义为：

```text
S_HF_voxel(E) =
  sum_{u in Omega_HF} E(u) * M_HF(u)
  / (sum_{u in Omega_HF} E(u) + lambda)

DeltaHFScore_3m =
  S_HF_voxel,domain(E_HF_component,HF+ULF3m)
  - S_HF_voxel,domain(E_HF_only,HF-only3m)

DeltaHFScore_immediate =
  S_HF_voxel,motor(E_HF_component,HF+ULFImmediate)
  - S_HF_voxel,motor(E_HF_only,HF-only3m)
```

`DeltaHFScore` 在进入模型前不设置固定生物学缩放系数。它可以在 training fold 内 z-score 以改善数值稳定性；其与结局的关联由回归系数估计。

## 特征构建

定义 HF 与 ULF active exposure：

```text
HF_active_i(v) = E_HF_component_i(v) > tau
ULF_active_i(v) = E_ULF_component_i(v) > tau
tau = 0.2 V/mm
```

ULF predictor 只使用 ULF-only exposure：

```text
X_ULF_only_i(v) =
  E_ULF_component_i(v), if ULF_active_i(v) and not HF_active_i(v)
  0,                   otherwise
```

如果某个 voxel 同时被 HF 和 ULF component 激活，它归入 HF model，并通过 `DeltaHFScore` adjustment 进入模型，而不是进入 `X_ULF_only`。

左右侧 ULF-only feature 分别计算后求平均：

```text
X_ULF_only_bilat_i(v) =
  (X_ULF_only_left_i(v) + X_ULF_only_right_i(v)) / 2
```

使用 `0.18` 和 `0.22 V/mm` 做阈值敏感性分析。还需报告 total-field 和 shape-normalized ULF sensitivity，但主预测变量保持为 ULF-only exposure。

## 统计模型

对每个 endpoint 和 voxel `v`：

```text
Y_HFplusULF_post_i = alpha_v
                  + theta_ULF(v) * X_ULF_only_bilat_i(v)
                  + beta_v      * Y_HF3m_i
                  + gamma_v     * DeltaHFScore_i
                  + error_i,v
```

敏感性模型：

```text
Y_HFplusULF_post_i = alpha_v
                  + theta_ULF(v) * X_ULF_only_bilat_i(v)
                  + beta_v      * Y_HF3m_i
                  + error_i,v
```

Benefit-oriented map：

```text
M_ULF(v) = -theta_ULF(v)   for lower-is-better scales
M_ULF(v) =  theta_ULF(v)   for SE-ADL
```

## 验证

- Chronic 3-month 和 immediate endpoint 分开建模。
- 使用 fully nested leave-one-patient-out cross-validation。
- 在每个 outer fold 内训练 direct voxel-level HF map，再计算 fold-specific `DeltaHFScore`。
- 与 covariate-only model `Y_HFplusULF_post ~ Y_HF3m + DeltaHFScore` 比较。
- 报告不含 `DeltaHFScore` 的敏感性模型。
- 报告 LOOCV Pearson `r`、Spearman `rho`、MAE、RMSE、`Q2` 和 patient-level Freedman-Lane permutation P value。

## 下游可视化

分别为 chronic 和 immediate endpoint 导出：

```text
direct_voxel_ULF_only_coverage.nii.gz
direct_voxel_ULF_only_coef.nii.gz
direct_voxel_ULF_only_sweet_sour.nii.gz
direct_voxel_ULF_only_stability.nii.gz
direct_voxel_ULF_only_bootstrap_se.nii.gz
direct_voxel_ULF_only_scores.csv
direct_voxel_ULF_only_loocv_predictions.csv
direct_voxel_ULF_only_permutation_summary.csv
direct_voxel_ULF_only_HF_overlap_exclusion_mask.nii.gz
```

显示 ULF-only sweet/sour map，同时叠加被排除的 HF-overlap 区域以及 STN/SNr 解剖边界。

## 解释边界

该模型估计 HF-adjusted ULF-only add-on association。它不是解剖 SNr gain 模型。被 HF 与 ULF 同时激活的 voxel 在主分析中视为 HF-dominant，因此 ULF map 表示在校正 HF 疗效变化后由 ULF 唯一招募的区域。
