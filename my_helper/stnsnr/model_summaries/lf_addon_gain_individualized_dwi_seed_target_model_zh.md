# HF-adjusted LF-only Add-On Gain Individualized DWI Seed-Target 模型

## 研究问题

加入 LF 刺激后，哪些 subject-specific LF-only DWI seed-target connectivity 特征与额外疗效相关，并且这种关联已校正 HF 临床状态和预测的 HF target engagement 变化？

这是 individualized seed-target / fiber-derived target-level 模型。它使用 subject-specific tractography，并把 STN/SNr 作为背景 territory，而不是主模型归属规则。

## 终点

两个终点分别建模：

```text
Chronic domain-specific endpoint:
  Y_HFplusLF_3m_domain = raw HF+LF 3-month clinical score
  covariates = Y_HF3m_domain + DeltaHFScore_3m_domain

Immediate motor endpoint:
  Y_HFplusLF_immediate_motor = raw HF+LF immediate motor score
  covariates = Y_HF3m_motor + DeltaHFScore_immediate_motor
```

主要 estimand：

```text
HF-adjusted LF-only add-on gain
```

## 输入

- 具有可用 DWI 的 subject 的 individualized DWI-derived tractography。
- HF-only stimulation exposure map。
- HF+LF programming 中的 HF 和 LF component exposure map。
- 由 HF-only 结局训练得到的 individualized DWI HF target-level model。
- 来自 connected-region atlas registry 的 seed 和 target mask。
- DWI registration 和 tractography QC 输出。
- HF-only 和 HF+LF 原始临床分数。

模型匹配的 HF adjustment 来自 individualized HF target-level model：

```text
DeltaHFScore =
  S_HF_ind(C_ind_HF_component,HF+LF)
  - S_HF_ind(C_ind_HF_only,HF-only)
```

`DeltaHFScore` 可以在 training fold 内 z-score，但不预先设置固定缩放系数。

## 特征构建

对每条 subject-specific streamline `l`，定义 HF 和 LF activation：

```text
A_HF_i(l) = max_x E_HF_component_i(x on l) > tau
A_LF_i(l) = max_x E_LF_component_i(x on l) > tau
tau = 0.2 V/mm
```

LF-only streamline weight：

```text
w_LF_only_i(l) =
  peak_E_LF_i(l), if A_LF_i(l) and not A_HF_i(l)
  0,              otherwise
```

如果 streamline 同时被 HF 和 LF component 激活，它归入 HF model，并通过 `DeltaHFScore` adjustment 进入模型，而不是作为 LF-only predictor。

对每侧和 target `k`：

```text
C_ind_LF_only_side_i(k) =
  aggregate_l w_LF_only_i(l) for subject-specific streamlines l assigned to target k
```

左右侧 target feature 分别计算后求平均：

```text
C_ind_LF_only_bilat_i(k) =
  (C_ind_LF_only_left_i(k) + C_ind_LF_only_right_i(k)) / 2
```

## 统计模型

对每个 target `k`：

```text
Y_HFplusLF_post_i = alpha_k
                  + theta_LF(k) * C_ind_LF_only_bilat_i(k)
                  + beta_k      * Y_HF3m_i
                  + gamma_k     * DeltaHFScore_i
                  + error_i,k
```

敏感性模型：

```text
Y_HFplusLF_post_i = alpha_k
                  + theta_LF(k) * C_ind_LF_only_bilat_i(k)
                  + beta_k      * Y_HF3m_i
                  + error_i,k
```

Benefit-oriented target weights：

```text
W_LF(k) = -theta_LF(k)   for lower-is-better scales
W_LF(k) =  theta_LF(k)   for SE-ADL
```

患者层面的 individualized LF-only target score：

```text
LFTargetScore_ind_i =
  sum_k C_ind_LF_only_bilat_i(k) * W_LF(k)
  / (sum_k abs(C_ind_LF_only_bilat_i(k)) + lambda)
```

## 验证

- Chronic 3-month 和 immediate endpoint 分开建模。
- 使用 fully nested leave-one-patient-out cross-validation。
- 在每个 outer fold 内训练 individualized HF target-level model，再计算 fold-specific `DeltaHFScore`。
- LF target 选择、LF weight 拟合和 `LFTargetScore_ind` 计算均在 training fold 内完成。
- 与 `Y_HFplusLF_post ~ Y_HF3m + DeltaHFScore` 比较。
- 单独报告 DWI registration、tractography 和 missing-feature QC。
- 报告 LOOCV Pearson `r`、Spearman `rho`、MAE、RMSE、`Q2` 和 permutation P value。

## 下游可视化

导出：

```text
individualized_LF_only_target_weights.csv
individualized_LF_only_target_scores.csv
individualized_LF_only_loocv_predictions.csv
individualized_LF_only_permutation_summary.csv
individualized_LF_only_streamline_contribution_map.nii.gz
individualized_LF_only_subject_qc.csv
individualized_LF_only_HF_overlap_exclusion_summary.csv
```

可视化 subject-specific LF-only target weight、LF-only streamline contribution density 和被排除的 HF-overlap streamline，并叠加 STN/SNr territory overlay。

## 解释边界

该模型使用 individualized DWI 估计 HF-adjusted LF-only target-level association。它比 normative model 更个体化，但仍受 DWI 质量、tractography uncertainty、registration、小样本以及“HF/LF overlap streamline 归入 HF 而非 LF”这一规则限制。
