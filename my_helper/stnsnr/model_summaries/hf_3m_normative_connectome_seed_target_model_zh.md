# HF-only 3m Normative Connectome Seed-Target 模型

## 研究问题

与 HF stimulation territory 相连的预定义 target 中，哪些 normative seed-target connectivity 特征与更好的 3 个月 HF-only 临床结局相关？

这是 seed-target / fiber-derived target-level 模型。单条 streamline 用于构建 target feature、QC、贡献图和可视化，但不作为主分析中的 top-correlation predictor。

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

- 每侧 HF-only stimulation exposure map。
- Lead-DBS 中可用的公共 structural connectome。
- 来自 connected-region atlas registry 的 seed 和 target mask。
- 用于 overlay 和 territory QC 的 STN/SNr 解剖 mask。
- 来自 `subject_effect_origin.xlsx` 的原始临床分数。

## 特征构建

对每个 subject、side 和 target `k`，使用连接 HF stimulation territory 与 target `k` 的 streamline 构建 normative target connectivity feature：

```text
C_norm_HF_side_i(k) =
  aggregate_l peak_E_HF_i(l) for streamlines l assigned to target k
```

主分析的 activation weight 为 streamline 上的 peak E-field 或 E-field-like exposure。Binary VTA intersection 和其他 exposure summary 作为敏感性分析。

左右侧 feature 分别计算后求平均：

```text
C_norm_HF_bilat_i(k) =
  (C_norm_HF_left_i(k) + C_norm_HF_right_i(k)) / 2
```

Target-level feature 可做 within-subject normalization 或在 training fold 内 z-score。所有 scaling 必须在 cross-validation fold 内学习。

## 统计模型

对每个 target `k`：

```text
Y_HF3m_i = alpha_k
         + theta_HF(k) * C_norm_HF_bilat_i(k)
         + beta_k      * Y_Preop_i
         + error_i,k
```

Benefit-oriented target weights：

```text
W_HF(k) = -theta_HF(k)   for lower-is-better scales
W_HF(k) =  theta_HF(k)   for SE-ADL
```

患者层面的 normative HF target score：

```text
HFTargetScore_norm_i =
  sum_k C_norm_HF_bilat_i(k) * W_HF(k)
  / (sum_k abs(C_norm_HF_bilat_i(k)) + lambda)
```

最终预测模型：

```text
Y_HF3m_i = alpha
         + delta * HFTargetScore_norm_i
         + beta  * Y_Preop_i
         + error_i
```

## 验证

- 使用 fully nested leave-one-patient-out cross-validation。
- Target 选择、target weight 拟合和 `HFTargetScore_norm` 计算均在 training fold 内完成。
- 与 `Y_HF3m ~ Y_Preop` 比较。
- 报告 LOOCV Pearson `r`、Spearman `rho`、MAE、RMSE、`Q2` 和 permutation P value。
- 在不同 normative connectome 中重复分析，作为 connectome 敏感性分析。

## 下游可视化

导出：

```text
normative_HF_target_weights.csv
normative_HF_target_scores.csv
normative_HF_loocv_predictions.csv
normative_HF_permutation_summary.csv
normative_HF_streamline_contribution_map.nii.gz
normative_HF_target_network_map.nii.gz
```

可视化 target weight、target-level predicted benefit 和 streamline contribution density。STN/SNr 边界与 HF stimulation territory 只作为背景 overlay。

## 解释边界

该模型估计 HF-only 的 network-informed association。它支持 target-level 机制和预测假设，但不能证明某一条 streamline 具有因果性。主预测变量是 target-level feature，而不是 top-ranked single fiber。
