# HF-only 3m Individualized DWI Seed-Target 模型

## 研究问题

来自 HF stimulation territory 的 subject-specific DWI seed-target connectivity 特征中，哪些与更好的 3 个月 HF-only 临床结局相关？

这是 individualized seed-target / fiber-derived target-level 模型。它使用每个 subject 的 DWI tractography，而不是只依赖公共 normative connectome。

## 终点

主终点：

```text
Y_HF3m = raw HF-only 3-month clinical score
```

主协变量：

```text
Y_Preop = raw preoperative clinical score
```

## 输入

- 具有可用 DWI 的 subject 的 individualized DWI-derived tractography。
- 每侧 HF-only stimulation exposure map。
- 来自 connected-region atlas registry 的 seed 和 target mask。
- DWI-to-MNI 和 MNI-to-DWI registration QC 输出。
- 用于 overlay 和 territory QC 的 STN/SNr 解剖 mask。
- 来自 `subject_effect_origin.xlsx` 的原始临床分数。

## 特征构建

对每个 subject、side 和 target `k`，使用 subject 自身 streamline 构建 individualized target connectivity feature：

```text
C_ind_HF_side_i(k) =
  aggregate_l peak_E_HF_i(l) for subject-specific streamlines l assigned to target k
```

主分析的 activation weight 为 streamline 上的 peak E-field 或 E-field-like exposure。可用时，SIFT2 weight、streamline count、binary VTA intersection 和其他 exposure summary 作为敏感性分析。

左右侧 feature 分别计算后求平均：

```text
C_ind_HF_bilat_i(k) =
  (C_ind_HF_left_i(k) + C_ind_HF_right_i(k)) / 2
```

Feature scaling、target filtering 和 imputation 必须在 training fold 内学习。

## 统计模型

对每个 target `k`：

```text
Y_HF3m_i = alpha_k
         + theta_HF(k) * C_ind_HF_bilat_i(k)
         + beta_k      * Y_Preop_i
         + error_i,k
```

Benefit-oriented target weights：

```text
W_HF(k) = -theta_HF(k)   for lower-is-better scales
W_HF(k) =  theta_HF(k)   for SE-ADL
```

患者层面的 individualized HF target score：

```text
HFTargetScore_ind_i =
  sum_k C_ind_HF_bilat_i(k) * W_HF(k)
  / (sum_k abs(C_ind_HF_bilat_i(k)) + lambda)
```

最终预测模型：

```text
Y_HF3m_i = alpha
         + delta * HFTargetScore_ind_i
         + beta  * Y_Preop_i
         + error_i
```

## 验证

- 使用 fully nested leave-one-patient-out cross-validation。
- 在每个 training fold 内完成 target 选择、feature scaling、模型拟合和 score 计算。
- 与 `Y_HF3m ~ Y_Preop` 比较。
- 报告 LOOCV Pearson `r`、Spearman `rho`、MAE、RMSE、`Q2` 和 permutation P value。
- 将 tractography 和 registration QC failure rate 与预测性能分开报告。

## 下游可视化

导出：

```text
individualized_HF_target_weights.csv
individualized_HF_target_scores.csv
individualized_HF_loocv_predictions.csv
individualized_HF_permutation_summary.csv
individualized_HF_streamline_contribution_map.nii.gz
individualized_HF_subject_qc.csv
```

可视化 target-level weight、subject-level connectivity contribution map 和 HF stimulation territory overlay。

## 解释边界

该模型估计 individualized HF-only target-level association。它可能比 normative connectome 更贴近个体解剖，但可靠性依赖 DWI 质量、registration、tractography 参数和小样本限制。
