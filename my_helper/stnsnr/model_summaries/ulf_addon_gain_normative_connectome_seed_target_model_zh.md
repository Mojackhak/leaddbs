# HF-adjusted ULF-only Add-On Gain Normative Connectome Seed-Target 模型

## 研究问题

加入 ULF 刺激后，哪些 ULF-only normative seed-target connectivity 特征与额外疗效相关，并且这种关联已校正 HF 临床状态和模型预测的 HF target engagement 变化？

这是 seed-target / fiber-derived target-level 模型。主预测变量是 target-level ULF-only connectivity，而不是 top-ranked single streamline。


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

- Lead-DBS 中可用的公共 structural connectome。
- HF-only stimulation exposure map。
- HF+ULF programming 中的 HF 和 ULF component exposure map。
- 由 HF-only 结局训练得到的 normative HF target-level model。
- 来自 connected-region atlas registry 的 seed 和 target mask。
- HF-only 和 HF+ULF 原始临床分数。

模型匹配的 HF adjustment 来自 normative HF target-level model：

```text
DeltaHFScore =
  S_HF_norm(C_norm_HF_component,HF+ULF)
  - S_HF_norm(C_norm_HF_only,HF-only)
```

`DeltaHFScore` 可以在 training fold 内 z-score，但不预先设置固定缩放系数。

## 特征构建

对每条 streamline `l`，定义 HF 和 ULF activation：

```text
A_HF_i(l) = max_x E_HF_component_i(x on l) > tau
A_ULF_i(l) = max_x E_ULF_component_i(x on l) > tau
tau = 0.2 V/mm
```

ULF-only streamline weight：

```text
w_ULF_only_i(l) =
  peak_E_ULF_i(l), if A_ULF_i(l) and not A_HF_i(l)
  0,              otherwise
```

如果 streamline 同时被 HF 和 ULF component 激活，它归入 HF model，并通过 `DeltaHFScore` adjustment 进入模型，而不是作为 ULF-only predictor。

对每侧和 target `k`：

```text
C_norm_LF_only_side_i(k) =
  aggregate_l w_ULF_only_i(l) for streamlines l assigned to target k
```

左右侧 target feature 分别计算后求平均：

```text
C_norm_LF_only_bilat_i(k) =
  (C_norm_LF_only_left_i(k) + C_norm_LF_only_right_i(k)) / 2
```

## 统计模型

对每个 target `k`：

```text
Y_HFplusULF_post_i = alpha_k
                  + theta_ULF(k) * C_norm_LF_only_bilat_i(k)
                  + beta_k      * Y_HF3m_i
                  + gamma_k     * DeltaHFScore_i
                  + error_i,k
```

敏感性模型：

```text
Y_HFplusULF_post_i = alpha_k
                  + theta_ULF(k) * C_norm_LF_only_bilat_i(k)
                  + beta_k      * Y_HF3m_i
                  + error_i,k
```

Benefit-oriented target weights：

```text
W_ULF(k) = -theta_ULF(k)   for lower-is-better scales
W_ULF(k) =  theta_ULF(k)   for SE-ADL
```

患者层面的 ULF-only target score：

```text
ULFTargetScore_norm_i =
  sum_k C_norm_LF_only_bilat_i(k) * W_ULF(k)
  / (sum_k abs(C_norm_LF_only_bilat_i(k)) + lambda)
```

## 验证

- Chronic 3-month 和 immediate endpoint 分开建模。
- 使用 fully nested leave-one-patient-out cross-validation。
- 在每个 outer fold 内训练 normative HF target-level model，再计算 fold-specific `DeltaHFScore`。
- ULF target 选择、ULF weight 拟合和 `ULFTargetScore_norm` 计算均在 training fold 内完成。
- 与 `Y_HFplusULF_post ~ Y_HF3m + DeltaHFScore` 比较。
- 在不同 normative connectome 和阈值敏感性中重复分析。
- 报告 LOOCV Pearson `r`、Spearman `rho`、MAE、RMSE、`Q2` 和 permutation P value。

## 下游可视化

导出：

```text
normative_ULF_only_target_weights.csv
normative_ULF_only_target_scores.csv
normative_ULF_only_loocv_predictions.csv
normative_ULF_only_permutation_summary.csv
normative_ULF_only_streamline_contribution_map.nii.gz
normative_ULF_only_target_network_map.nii.gz
normative_ULF_only_HF_overlap_exclusion_summary.csv
```

可视化 ULF-only target weight、ULF-only streamline contribution density 和被排除的 HF-overlap streamline。STN/SNr 边界只作为背景 overlay。

## 解释边界

该模型使用公共 connectome 估计 HF-adjusted ULF-only target-level association。它不声称 ULF 效应局限于解剖 SNr。ULF predictor 仅表示在 HF-overlap streamline 归入 HF adjustment 后，由 ULF 唯一招募的 streamlines。
