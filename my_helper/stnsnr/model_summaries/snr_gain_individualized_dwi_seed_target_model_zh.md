# SNr 增益 Individualized DWI Seed-Target 模型

## 研究问题

患者个体 DWI 中来自 SNr 的 seed-target connectivity features 能否预测在 STN 刺激基础上加入 SNr 后的额外获益？

这是一个使用 individualized DWI tractography 的 seed-target / fiber-derived target-level 模型。

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

主 estimand 是 STN-change-adjusted SNr target-connectivity association：

```text
Y_AB_post ~ C_ind_SNr_component(k) + Y_STN3m_domain + DeltaSTNScore_domain
```

同时报告一个不包含 `DeltaSTNScore` 的 clinical optimized strategy sensitivity model：

```text
Y_AB_post ~ C_ind_SNr_component(k) + Y_STN3m_domain
```

如果两类 map 明显不一致，应解释为 SNr target pattern 与 STN component reprogramming 强耦合。

## 输入

- 来自 imported DWI cohort 的 individualized DWI tractography。
- `dwi_registration_technical_details.md` 中描述的 DWI registration outputs。
- 投影到患者 DWI space 的 SNr seed 和 target masks。
- 投影到 DWI space 的 SNr-component stimulation maps 或 e-field-like proxy maps。
- 原始临床分数。
- 由 pre-SNr STN-only data 训练得到的、针对各量表或症状域的 STN-only efficacy maps。
- 每个 endpoint 对应的 `DeltaSTNScore`，由相应 STN efficacy map 计算。

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

对患者 `i`、侧别 `h` 和 target `k`，定义 individualized SNr streamlines：

```text
G_ind_SNr(i,k,h) = patient i streamlines connecting same-side SNr seed to target P(k,h)
```

Side-specific target connectivity：

```text
C_ind_SNr_component(i,h,k) =
  sum_j max exposure along patient streamline j
  / (number of streamlines in G_ind_SNr(i,k,h) + lambda)
```

患者层面的双侧特征：

```text
C_ind_SNr_bilat(i,k) =
  (C_ind_SNr_component(i,L,k) + C_ind_SNr_component(i,R,k)) / 2
```

建模前运行 target coverage QC。低重建率 targets 应排除出主要解释。

主分析中，target connectivity 使用沿患者特异 streamlines 的 peak SNr-component exposure。运行以下 field-definition sensitivities：

```text
C_ind_SNr_component(k) = SNr-component peak exposure along individualized SNr-target streamlines
C_ind_SNr_total(k)     = total STN+SNr peak exposure along the same streamlines
C_ind_SNr_residual(k)  = residualized total-field connectivity after regressing out STN-component connectivity
C_ind_SNr_shape(k)     = shape-normalized SNr-component connectivity
```

由于 STN 和 SNr 相邻，individualized SNr-target streamlines 仍可能反映 STN-SNr border-zone recruitment、registration error 或 passing fibers。运行 border-zone sensitivity analyses：

```text
eroded SNr seed contribution
streamline seed-point distance to STN
exclude or down-weight seed contributions with d(seed, STN) <= 1.0 mm
exclude or down-weight seed contributions with d(seed, STN) <= 1.5 mm
cor(C_ind_SNr_bilat(k), DeltaSTNScore)
```

与 `DeltaSTNScore` 高共线的 targets，例如 `abs(r) > 0.6`，应降低其 SNr-specific 解释强度。

## 统计模型

优先模型：

```text
normative-guided individualized DWI
```

使用 normative connectome training folds 确定 `S_SNr` 和 `w_SNr,k`，再计算 individualized DWI score：

```text
SNrTargetScore_ind_norm_i =
  sum_{k in S_SNr_norm} w_SNr,k_norm * Z(C_ind_SNr_bilat(i,k))
  / sum_{k in S_SNr_norm} abs(w_SNr,k_norm)
```

最终模型：

```text
Y_AB_post_domain_i = alpha
            + delta * SNrTargetScore_ind_norm_i
            + beta  * Y_STN3m_domain_i
            + gamma * DeltaSTNScore_domain_i
            + error_i
```

敏感性模型：

```text
individualized-DWI-only
```

在该敏感性模型中，`S_SNr` 和 `w_SNr,k` 从 individualized DWI features 中学习，并且必须在每个 training fold 内完成。

## 验证

- Chronic gain 和 immediate gain 分别建模。
- 对 chronic 3 个月结局，在数据支持时运行 domain-specific models：motor、axial/gait、nonmotor、total、QoL 或 ADL。
- 对 immediate outcomes，使用 motor-specific `Y_STN3m_motor` 和 motor-specific `DeltaSTNScore_immediate_motor`。
- 使用 fully nested leave-one-patient-out cross-validation。
- 对 normative-guided 模型，normative target weights 和 selected targets 必须在不包含 held-out patient 的情况下学习。
- 对 DWI-only 敏感性模型，target weights、target selection 和 standardization 必须在 training folds 内完成。
- 严格 out-of-sample prediction 中，STN efficacy map 必须在每个 outer fold 内训练，再计算 fold-specific `DeltaSTNScore`。
- 报告用于构建 `DeltaSTNScore` 的 STN efficacy-map validation：LOOCV `Q2`、相对 `Y_STN3m ~ Y_Preop` 的改进、以及 STN map stability。如果 STN map 不稳定，`DeltaSTNScore` 应降级为 exploratory adjustment。
- 与 covariate-only prediction `Y_AB_post_domain ~ Y_STN3m_domain + DeltaSTNScore_domain` 和 normative-only model 比较。
- 与不包含 `DeltaSTNScore` 的 clinical optimized strategy model 比较。
- 运行 `DeltaSTNPhys` 敏感性分析，使用 outcome-independent STN-change 指标，例如 charge-rate change、raw STN e-field energy change、STN VTA overlap change 或 STN field centroid distance。
- 报告 component-field、total-field、residual-field、shape-normalized、eroded-SNr、distance-to-STN 和 `DeltaSTNScore` collinearity sensitivity results。
- 在 prediction analyses 中，target inclusion、streamline-count 和 reconstruction coverage thresholds 必须在每个 training fold 内定义。
- 报告 DWI coverage、target missingness、LOOCV metrics、与 normative SNr target patterns 的一致性，以及 patient-level permutation P value。`n = 16` 时不要把 target-wise P values 作为主要证据。

## 下游可视化

对 chronic gain 和 immediate gain 分别导出：

```text
DWI target coverage tables
C_ind_SNr_bilat matrices
SNrTargetScore_ind_norm.csv
SNrTargetScore_ind_only.csv
individualized-DWI selected-target fiber subsets
coverage-weighted group SNr seed voxel maps
component_vs_total_field_sensitivity tables
residual_field_sensitivity tables
shape_normalized_sensitivity tables
seed_distance_to_STN summaries
DeltaSTNScore_collinearity tables
```

Group SNr voxel maps 通过将患者特异的 DWI target-derived maps warp 到 template space，并按 voxel coverage weights 平均得到。

## 解释边界

该模型检验与 add-on benefit 相关的 SNr target-connectivity pattern 是否存在于每个患者自己的 DWI tractography 中。它具有 subject-specific 特点，但受 DWI tractography 质量、registration、target coverage、streamline false positives 和 false negatives 限制。缺失或稀疏 streamlines 应被视为 QC 限制，而不是生物学不存在的证据。由于 STN 和 SNr 相邻，SNr-target maps 可能反映 dorsal SNr、ventral STN、STN-SNr border zone、registration uncertainty 或 passing fibers。除非使用外部 STN efficacy map，否则 `DeltaSTNScore` 是 same-cohort、pre-SNr-derived nuisance adjustment，在小样本中可能有噪声。

主模型估计 STN-change-adjusted SNr add-on target-connectivity association，而不是 optimized combined STN+SNr programming strategy 的总体真实世界效果。
