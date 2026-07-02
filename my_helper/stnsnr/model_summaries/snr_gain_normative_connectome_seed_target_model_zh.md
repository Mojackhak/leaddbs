# SNr 增益 Normative Connectome Seed-Target 模型

## 研究问题

公共 normative connectomes 中哪些 SNr-connected targets 与在 STN 刺激基础上加入 SNr 后的额外获益相关？

这是一个 seed-target / fiber-derived target-level 模型。单条 streamline 用于构建 target features 和下游可视化；主预测变量不是 top-correlated individual streamlines。

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
Y_AB_post ~ C_norm_SNr_component(k) + Y_STN3m_domain + DeltaSTNScore_domain
```

同时报告一个不包含 `DeltaSTNScore` 的 clinical optimized strategy sensitivity model：

```text
Y_AB_post ~ C_norm_SNr_component(k) + Y_STN3m_domain
```

如果两类 map 明显不一致，应解释为 SNr target pattern 与 STN component reprogramming 强耦合。

## 输入

- 公共 Lead-DBS structural connectomes：dTOR-985 Full、MGH-USC HCP 32、PPMI 85。
- 来自 `SNr-connected regions` 的 SNr seed 和 target masks。
- 来自 seed-target atlas registry 的 SNr targets，包括 VA/VLA/VLP/VM thalamus、STN、posterior putamen、caudate、PPN、superior colliculus、MD、CM、Pf、sPf、FEF、SMA、preSMA、premotor、M1 和 DLPFC。
- 每个 endpoint 的 SNr-component stimulation maps。
- 原始临床分数。
- 由 pre-SNr STN-only data 训练得到的、针对各量表或症状域的 STN normative connectome seed-target efficacy models。
- 每个 endpoint 对应的 `DeltaSTNScore`，由相应 normative STN target-level score 计算。

优先 STN adjustment 必须与该 normative connectome seed-target SNr 模型对应。它来自 STN 3m normative connectome seed-target 模型，而不是 direct voxel-level 或 individualized DWI STN 模型：

```text
S_STN_norm(E) =
  sum_{k in S_STN_norm} w_STN,k_norm * Z_train(C_norm_STN_component(E,k))
  / sum_{k in S_STN_norm} abs(w_STN,k_norm)

DeltaSTNScore_3m =
  S_STN_norm,domain(E_STN_component,STN+SNr3m)
  - S_STN_norm,domain(E_STN_component,STN-only3m)

DeltaSTNScore_immediate =
  S_STN_norm,motor(E_STN_component,STN+SNrImmediate)
  - S_STN_norm,motor(E_STN_component,STN-only3m)
```

对于低分更好的量表，`w_STN,k_norm = -theta_STN,k`；对于 SE-ADL，`w_STN,k_norm = theta_STN,k`。Target selection、target weights 和 `Z_train()` scaling 必须在同一 training fold 内由 STN-only outcomes 学习，且发生在加入 SNr 之前。

## 特征构建

对患者 `i`、侧别 `h` 和 target `k`，定义同侧 normative SNr streamlines：

```text
G_norm_SNr(k,h) = streamlines connecting same-side SNr seed to target P(k,h)
```

Side-specific target connectivity：

```text
C_norm_SNr_component(i,h,k) =
  sum_j max exposure along streamline j
  / (number of streamlines in G_norm_SNr(k,h) + lambda)
```

患者层面的双侧特征：

```text
C_norm_SNr_bilat(i,k) =
  (C_norm_SNr_component(i,L,k) + C_norm_SNr_component(i,R,k)) / 2
```

主分析中同一 target 内 streamlines 采用 equal weights。

主分析中，target connectivity 使用沿 streamlines 的 peak SNr-component exposure。运行以下 field-definition sensitivities：

```text
C_norm_SNr_component(k) = SNr-component peak exposure along SNr-target streamlines
C_norm_SNr_total(k)     = total STN+SNr peak exposure along the same streamlines
C_norm_SNr_residual(k)  = residualized total-field connectivity after regressing out STN-component connectivity
C_norm_SNr_shape(k)     = shape-normalized SNr-component connectivity
```

由于 STN 和 SNr 相邻，SNr-target connectivity 仍可能反映 STN-SNr border-zone recruitment 或 passing fibers。运行 border-zone sensitivity analyses：

```text
eroded SNr seed contribution
streamline seed-point distance to STN
exclude or down-weight seed contributions with d(seed, STN) <= 1.0 mm
exclude or down-weight seed contributions with d(seed, STN) <= 1.5 mm
cor(C_norm_SNr_bilat(k), DeltaSTNScore)
```

与 `DeltaSTNScore` 高共线的 targets，例如 `abs(r) > 0.6`，应降低其 SNr-specific 解释强度。

## 统计模型

对每个 endpoint 和 target `k`：

```text
Y_AB_post_domain_i = alpha_k
            + theta_SNr,k * Z(C_norm_SNr_bilat(i,k))
            + beta_k      * Z(Y_STN3m_domain_i)
            + gamma_k     * Z(DeltaSTNScore_domain_i)
            + error_i,k
```

Benefit-oriented target weight：

```text
w_SNr,k = -theta_SNr,k   for lower-is-better scales
w_SNr,k =  theta_SNr,k   for SE-ADL
```

患者层面的 normative SNr target score：

```text
SNrTargetScore_norm_i =
  sum_{k in S_SNr} w_SNr,k * Z(C_norm_SNr_bilat(i,k))
  / sum_{k in S_SNr} abs(w_SNr,k)
```

最终预测模型：

```text
Y_AB_post_domain_i = alpha
            + delta * SNrTargetScore_norm_i
            + beta  * Y_STN3m_domain_i
            + gamma * DeltaSTNScore_domain_i
            + error_i
```

## 验证

- Chronic gain 和 immediate gain 分别建模。
- 对 chronic 3 个月结局，在数据支持时运行 domain-specific models：motor、axial/gait、nonmotor、total、QoL 或 ADL。
- 对 immediate outcomes，使用 motor-specific `Y_STN3m_motor` 和 motor-specific `DeltaSTNScore_immediate_motor`。
- 使用 fully nested leave-one-patient-out cross-validation。
- Target weights、target selection 和 feature standardization 只能在 training folds 内完成。
- 严格 out-of-sample prediction 中，model-matched normative STN seed-target model 必须在每个 outer fold 内训练，再计算 fold-specific `DeltaSTNScore`。
- 报告用于构建 `DeltaSTNScore` 的 normative STN target-model validation：LOOCV `Q2`、相对 `Y_STN3m ~ Y_Preop` 的改进、target selection stability 和 target-weight stability。如果 STN target model 不稳定，`DeltaSTNScore` 应降级为 exploratory adjustment。
- 与 covariate-only prediction 比较：`Y_AB_post_domain ~ Y_STN3m_domain + DeltaSTNScore_domain`。
- 与不包含 `DeltaSTNScore` 的 clinical optimized strategy model 比较。
- 运行 `DeltaSTNPhys` 敏感性分析，使用 outcome-independent STN-change 指标，例如 charge-rate change、raw STN e-field energy change、STN VTA overlap change 或 STN field centroid distance。
- 报告 component-field、total-field、residual-field、shape-normalized、eroded-SNr、distance-to-STN 和 `DeltaSTNScore` collinearity sensitivity results。
- 在 prediction analyses 中，target inclusion、streamline-count 和 coverage thresholds 必须在每个 training fold 内定义。
- 报告 LOOCV metrics、target selection stability、cross-connectome agreement 和 patient-level permutation P value。`n = 16` 时不要把 target-wise P values 作为主要证据。

## 下游可视化

对 chronic gain 和 immediate gain 分别导出：

```text
target weights and target ranking tables
SNrTargetScore_norm.csv
selected-target fiber subsets
target-weighted streamline density maps
SNr_lh_coverage/sweet/sour/net/stability.nii.gz
SNr_rh_coverage/sweet/sour/net/stability.nii.gz
component_vs_total_field_sensitivity tables
residual_field_sensitivity tables
shape_normalized_sensitivity tables
seed_distance_to_STN summaries
DeltaSTNScore_collinearity tables
```

SNr voxel maps 是通过 normative streamline density 将 `w_SNr,k` 反投影到 SNr 得到的 target-derived seed voxel maps。

## 解释边界

该模型估计 clinical optimization-informed SNr target-gain associations，并调整 STN 3 个月 baseline 和 concurrent STN reprogramming。它支持 network interpretation，但不能证明任何单条 streamline 或 target 具有充分因果性。由于 STN 和 SNr 相邻，SNr-target maps 可能反映 dorsal SNr、ventral STN、STN-SNr border zone 或 passing fibers。除非使用外部且 model-matched 的 normative STN target model，否则 `DeltaSTNScore` 是 same-cohort、pre-SNr-derived nuisance adjustment，在小样本中可能有噪声。

主模型估计 STN-change-adjusted SNr add-on target-connectivity association，而不是 optimized combined STN+SNr programming strategy 的总体真实世界效果。
