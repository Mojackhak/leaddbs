# STN 3m Individualized DWI Seed-Target 模型

## 研究问题

患者个体 DWI 中来自 STN 的 seed-target connectivity features 能否预测 STN-only 3 个月临床结局？

这是一个使用 individualized DWI tractography 的 seed-target / fiber-derived target-level 模型。它检验 normative connectome 中观察到的 STN target pattern 是否也存在于每个患者自己的 tractography 中。

## 终点

主终点：

```text
Y_STN3m = raw STN-only 3-month clinical score
```

主协变量：

```text
Y_Preop = raw preoperative clinical score
```

## 输入

- 来自 imported DWI cohort 的 individualized DWI tractography。
- `dwi_registration_technical_details.md` 中描述的 DWI registration outputs。
- 投影到患者 DWI space 的 STN seed 和 target masks。
- 投影到 DWI space 的 STN-only 3 个月刺激暴露图或 e-field-like proxy maps。
- 来自 `subject_effect_origin.xlsx` 的原始临床分数。

## 特征构建

对患者 `i`、侧别 `h` 和 target `k`，定义 individualized streamlines：

```text
G_ind_STN(i,k,h) = patient i streamlines connecting same-side STN seed to target P(k,h)
```

Side-specific target connectivity：

```text
C_ind_STN(i,h,k) =
  sum_j max exposure along patient streamline j
  / (number of streamlines in G_ind_STN(i,k,h) + lambda)
```

患者层面的双侧特征：

```text
C_ind_STN_bilat(i,k) =
  (C_ind_STN(i,L,k) + C_ind_STN(i,R,k)) / 2
```

建模前运行 target coverage QC。只有当足够多患者的双侧 streamlines 可用时，才解释该 target；主规则为 `12/16`，更严格敏感性规则为 `13/16`。

## 统计模型

优先模型：

```text
normative-guided individualized DWI
```

使用 normative connectome training folds 确定 `S_STN` 和 `w_STN,k`，再计算 individualized DWI score：

```text
STNTargetScore_ind_norm_i =
  sum_{k in S_STN_norm} w_STN,k_norm * Z(C_ind_STN_bilat(i,k))
  / sum_{k in S_STN_norm} abs(w_STN,k_norm)
```

最终模型：

```text
Y_STN3m_i = alpha
          + delta * STNTargetScore_ind_norm_i
          + beta  * Y_Preop_i
          + error_i
```

敏感性模型：

```text
individualized-DWI-only
```

在该敏感性模型中，`S_STN` 和 `w_STN,k` 从 individualized DWI features 中学习，并且必须在每个 training fold 内完成。

## 验证

- 使用 fully nested leave-one-patient-out cross-validation。
- 对 normative-guided 模型，normative target weights 和 selected targets 必须在不包含 held-out patient 的情况下学习。
- 对 DWI-only 敏感性模型，target weights、target selection 和 feature standardization 都必须在 training fold 内完成。
- 与 covariate-only prediction 和 normative-only model 比较。
- 报告 DWI coverage、target missingness、LOOCV prediction metrics，以及与 normative target pattern 的一致性。

## 下游可视化

导出：

```text
DWI target coverage tables
C_ind_STN_bilat matrices
STNTargetScore_ind_norm.csv
STNTargetScore_ind_only.csv
individualized-DWI selected-target fiber subsets
coverage-weighted group STN seed voxel maps
```

Group STN voxel maps 通过将患者特异的 DWI target-derived maps warp 到 template space，并按 voxel coverage weights 平均得到。它们是 consistency maps，不是主要解剖图。

## 解释边界

该模型检验 STN target-connectivity pattern 的患者特异表达。它比 normative model 更个体化，但受 DWI 质量、registration 和 tractography coverage 限制。低覆盖 targets 不应被解释为阴性生物学证据。
