# HF-adjusted ULF-only Add-On Gain Normative Connectome Fiber 模型

## 研究问题

加入 ULF 刺激后，哪些 ULF-only normative connectome streamlines 与额外疗效相关，并且这种关联已校正 HF 临床状态和模型预测的 HF fiber engagement 变化？

这是 right-canonical、full-connectome、fiber-level 模型。公共 structural connectome 中的单条 streamline 是主建模单位。Target atlas 只用于 endpoint labeling、anatomical enrichment、QC 和 visualization。

频率定义固定为：

```text
HF  = high-frequency stimulation component, frequency_Hz >= 100
ULF = ultra-low-frequency stimulation component, frequency_Hz <= 50
```

## 终点

两个 endpoint family 分别建模：

```text
Chronic domain-specific endpoint:
  Y_HFplusULF_3m_domain = raw HF+ULF 3-month clinical score
  nuisance covariates = Y_HF3m_domain + DeltaHFScore_3m_domain

Immediate motor endpoint:
  Y_HFplusULF_immediate_motor = raw HF+ULF immediate motor score
  nuisance covariates = Y_HF3m_motor + DeltaHFScore_immediate_motor
```

主要 estimand：

```text
HF-adjusted ULF-only add-on gain
```

低分更好和高分更好的量表方向，使用与 HF 模型相同的内置 scale direction table。

## 输入

- Public Lead-DBS structural connectomes：PPMI 85、MGH-USC HCP 32 和 dTOR-985 Full。
- 拆分为 HF 和 ULF component 的 HF+ULF programming。
- HF component 和 ULF component 的 raw `sim-efield` 或已接受的 e-field-like exposure maps。
- 来自 [`hf_3m_normative_connectome_fiber_model.md`](hf_3m_normative_connectome_fiber_model.md) 的 normative HF fiber-level model 输出。
- HF-only 和 HF+ULF 原始临床分数。
- 用于 endpoint labels、anatomical enrichment 和 STN/SNr contextual overlays 的 connected-region atlases。

模型匹配的 HF adjustment 来自 normative HF fiber-level model：

```text
DeltaHFScore =
  S_HF_norm_fiber(E_HF_component,HF+ULF)
  - S_HF_norm_fiber(E_HF_only,HF-only)

S_HF_norm_fiber(E) = NetFiberScore(E)
```

`DeltaHFScore` 在每个 training fold 内估计。它可以在该 fold 内 z-score，但不预先设置固定缩放系数。

## 特征构建

可执行 feature space 是 right-canonical streamline feature space。左侧刺激通过 `ea_flip_lr_nonlinear` 翻转到右侧 canonical space 后，在同一组右侧 streamlines 上采样。因此模型使用双侧 e-field 信息，但 streamline feature set 本身是单侧 canonical，而不是真正的 bilateral streamline set。

对每个 patient `i` 和 right-canonical streamline `l`，计算 component-level peak exposure：

```text
E_HF_R_i(l)       = peak HF-component exposure along right-side fiber l
E_HF_L_to_R_i(l)  = peak left HF-component exposure after nonlinear L-to-R flip
E_ULF_R_i(l)      = peak ULF-component exposure along right-side fiber l
E_ULF_L_to_R_i(l) = peak left ULF-component exposure after nonlinear L-to-R flip

X_HF_component_i(l)  = (E_HF_R_i(l)  + E_HF_L_to_R_i(l))  / 2
X_ULF_component_i(l) = (E_ULF_R_i(l) + E_ULF_L_to_R_i(l)) / 2
```

同侧 alternating ULF subprograms 先按 voxel-wise 或 streamline-wise maximum 合并，再做双侧平均。Peak E-field branch 不按 frequency 或 pulse width 缩放 exposure；这些参数只记录在 provenance 中。

由于 HF-overlap streamlines 会从 ULF predictor 中排除，ULF-only exposure 是 threshold-specific：

```text
ULF_touched_i(l,tau) = X_ULF_component_i(l) > tau
HF_touched_i(l,tau)  = X_HF_component_i(l)  > tau

X_ULF_only_i(l,tau) =
  X_ULF_component_i(l), if ULF_touched_i(l,tau) and not HF_touched_i(l,tau)
  0,                   otherwise
```

如果 streamline 同时被 HF 和 ULF component 激活，它归入 HF model，并通过 `DeltaHFScore` adjustment 进入模型，而不是作为 ULF-only predictor。

Candidate fibers 与 HF normative fiber model 保持一致：

```text
tau_primary = 800 V/m
tau_sensitivity = 1500 V/m

Coverage_tau(l) = sum_i I[X_ULF_only_i(l,tau) > tau]
F_candidate_tau = {l: Coverage_tau(l) >= 5}
```

Candidate universe 是完整 public connectome，不是 target-restricted seed-target tracts。

## 统计模型

主估计器是 fiber-level nuisance-adjusted partial Spearman：

```text
rho_ULF(l) =
  corr(
    resid(rank(Y_post_i)          ~ rank(Y_HF3m_i) + rank(DeltaHFScore_i)),
    resid(rank(X_ULF_only_i(l))   ~ rank(Y_HF3m_i) + rank(DeltaHFScore_i))
  )
```

ties 使用 average ranks。Chronic 和 immediate endpoints 使用相同 estimator，但 `Y_post`、`Y_HF3m` 和 `DeltaHFScore` 必须 endpoint-matched。

Benefit-oriented fiber weights：

```text
M_ULF(l) = -rho_ULF(l)   for lower-is-better scales
M_ULF(l) =  rho_ULF(l)   for higher-is-better scales
```

Positive/sweet selected fibers：

```text
F+ = top 1% fibers with largest positive M_ULF(l)
```

Negative/sour selected fibers：

```text
F- = top 0.5% fibers with most negative M_ULF(l)
```

对每个 patient：

```text
SweetWeighted_i(l) = X_ULF_only_i(l) * M_ULF(l),      l in F+
SourWeighted_i(l)  = X_ULF_only_i(l) * [-M_ULF(l)],   l in F-

SweetPeak5_i = mean of top 5% largest SweetWeighted_i(l)
SourPeak5_i  = mean of top 5% largest SourWeighted_i(l)

NetULFFiberScore_i = SweetPeak5_i - SourPeak5_i
```

选择规则和边界情况：

- `F+` 和 `F-` 在 `F_candidate_tau` 内选择，并排除 `NaN` 或 degenerate fibers。
- percentile counts 使用 `ceil(percent * n)`；当对应 positive 或 negative pool 非空时至少选择 1 条 fiber。
- 如果 `F+` 为空，`SweetPeak5_i = 0`。
- 如果 `F-` 为空，`SourPeak5_i = 0`。
- 如果 selected set 非空但某个 patient 对所有 selected fibers 的 ULF-only exposure 都为 0，对应 peak score 记为 `0`。

预测模型：

```text
Y_post_i = alpha
         + delta * NetULFFiberScore_i
         + beta  * Y_HF3m_i
         + gamma * DeltaHFScore_i
         + error_i
```

Nuisance-only baseline：

```text
Y_post_i = alpha
         + beta  * Y_HF3m_i
         + gamma * DeltaHFScore_i
         + error_i
```

可选补充估计器，本次执行计划不运行：

```text
OLS ANCOVA:
  Y_post_i ~ X_ULF_only_i(l) + Y_HF3m_i + DeltaHFScore_i
```

可选 ANCOVA branch 仅保留给未来 sensitivity work，不替代主 partial Spearman estimator。

## 验证

使用 fully nested leave-one-patient-out cross-validation。

对每个 connectome、scale、endpoint family 和 outer fold：

```text
train = all patients except held-out patient h
test  = patient h
```

在 training fold 内：

1. 从 HF normative fiber model 重新计算 fold-specific `DeltaHFScore`。
2. 用 training patients 计算 fold-specific `X_ULF_only_i(l,tau)` 并定义 candidate。
3. 由 training-patient `Coverage_tau(l) >= 5` 定义 `F_candidate_tau`。
4. 只用 training patients 拟合 `rho_ULF(l)` 和 `M_ULF(l)`。
5. 选择 fold-specific `F+` 和 `F-`。
6. 为 training patients 和 held-out patient 计算 `SweetPeak5`、`SourPeak5` 和 `NetULFFiberScore`。
7. 在 training patients 中拟合 `Y_post ~ NetULFFiberScore + Y_HF3m + DeltaHFScore`。
8. 预测 held-out `Y_post`。

Fold-level 禁止项：

- 不用 full-sample candidate mask 做 LOOCV scoring。
- 不用 full-sample ranks。
- 不用 full-sample `M_ULF`。
- 不用 full-sample `F+` 或 `F-`。
- held-out patient 不参与 candidate definition、ULF map fitting、selected-fiber selection 或 final prediction-model fitting。

主验证指标：

```text
LOOCV Spearman rho
LOOCV Pearson r
MAE
RMSE
Q2 relative to nuisance-only baseline
```

dTOR primary branch 使用 Freedman-Lane permutation：

```text
formal B = 10000
smoke B = 1000
seed = 42
primary statistic = LOOCV Spearman rho
p_plus_one = (1 + count(|stat_perm| >= |stat_obs|)) / (B + 1)
```

每次 permutation 都必须重跑完整 LOOCV workflow，包括 candidate definition、`rho_ULF`、`M_ULF`、`F+`、`F-`、`NetULFFiberScore` 和 held-out prediction。

dTOR primary branch 的 subject-level bootstrap：

```text
formal B = 10000
smoke B = 1000
seed = 42
```

PPMI 和 MGH 是 observed robustness branches。它们需要 observed LOOCV、scores、maps、labels 和 display outputs，但不运行 formal `B=10000` permutation/bootstrap。

## Plain Connected-Streamline Control

Plain control 用于检验 ULF 结果是否只是 stimulation burden、lead placement 或 connectome density，而不是 outcome-filtered fiber specificity。

对每个 patient：

```text
Touched_ULF_only_i(l) = I[X_ULF_only_i(l,tau) > tau]

PlainTouchedCount_i = sum_l Touched_ULF_only_i(l)
PlainExposureSum_i  = sum_l X_ULF_only_i(l,tau)
PlainExposureTop5_i = mean top 5% X_ULF_only_i(l,tau) among touched candidate fibers
```

比较：

```text
Y_post ~ Y_HF3m + DeltaHFScore
Y_post ~ PlainExposureTop5 + Y_HF3m + DeltaHFScore
Y_post ~ NetULFFiberScore + Y_HF3m + DeltaHFScore
Y_post ~ NetULFFiberScore + PlainExposureTop5 + Y_HF3m + DeltaHFScore
```

Joint model 只作为 QC。由于 `n=16`，不能将其解释为强因果分解。

## 下游可视化

输出根目录：

```text
/Volumes/VAL/STNSNr/summary/normative_connectome_fiber/ulf/<connectome_slug>/<endpoint_slug>/<scale_slug>/<branch>/
```

每个已完成 branch 的必需 numeric outputs：

```text
normative_ULF_fiber_weights.csv
normative_ULF_fiber_scores.csv
normative_ULF_fiber_loocv_predictions.csv
normative_ULF_fiber_permutation_summary.csv
normative_ULF_fiber_mapping_qc.json
normative_ULF_fiber_generation_manifest.json
normative_ULF_fiber_HF_overlap_exclusion_summary.csv
```

Score outputs 包含：

```text
SweetPeak5
SourPeak5
NetULFFiberScore
DeltaHFScore
Y_HF3m
n_sweet_selected_fibers
n_sour_selected_fibers
n_sweet_peak_fibers
n_sour_peak_fibers
PlainExposureTop5
is_primary_score
```

Display 和 anatomical interpretation outputs：

```text
normative_ULF_fiber_display_top1_positive.tck
normative_ULF_fiber_display_top1_positive.mat
normative_ULF_fiber_display_top0p5_sour.tck
normative_ULF_fiber_display_top0p5_sour.mat
normative_ULF_fiber_density_map.nii.gz
normative_ULF_fiber_endpoint_labels.csv
normative_ULF_fiber_cortical_endpoint_summary.csv
normative_ULF_fiber_subcortical_crossing_summary.csv
normative_ULF_fiber_label_enrichment.csv
normative_ULF_fiber_unthresholded_weighted_density.nii.gz
normative_ULF_fiber_positive_weighted_density.nii.gz
normative_ULF_fiber_negative_weighted_density.nii.gz
normative_ULF_fiber_neglogp_density.nii.gz
normative_ULF_fiber_qvalue_summary.csv
fdr_summary_by_scale.csv
fdr_thresholded_positive_density_q05.nii.gz
fdr_thresholded_negative_density_q05.nii.gz
fdr_thresholded_positive_density_q10.nii.gz
fdr_thresholded_negative_density_q10.nii.gz
connectome_scale_performance_summary.csv
connectome_scale_overlap_summary.csv
connectome_density_correlation_summary.csv
connectome_selected_label_summary.csv
```

Plain-control outputs：

```text
normative_ULF_plain_touched_summary.csv
normative_ULF_plain_connected_model_comparison.csv
normative_ULF_plain_touched_fibers.tck
normative_ULF_plain_touched_density_map.nii.gz
```

FDR q-values、q-thresholded maps、endpoint labels 和 display fibers 只用于 QC/display。它们不定义 `F+`、`F-`、`NetULFFiberScore` 或主模型。

## Execution Efficiency

加速规则沿用 HF normative fiber model，并且必须保持 exact equivalence。

允许的 caches：

```text
X_ULF_component_float32_fiber_major.npy
X_HF_component_float32_fiber_major.npy
X_ULF_only_tau800_float32_fiber_major.npy
X_ULF_only_tau1500_float32_fiber_major.npy
S800_ULF_only_bool.npy
S1500_ULF_only_bool.npy
fiber_id.npy
candidate_fiber_metadata.json
```

dTOR 必须使用 chunked sidecars 处理。实现不得一次性把所有 dTOR streamlines 加载进内存。

Outcome-independent caches 可跨 scale 和 endpoint family 复用：

- raw component exposure sidecars
- ULF-only overlap-exclusion masks
- `Coverage_tau` caches
- candidate fiber metadata
- endpoint label lookup
- density lookup

Outcome-dependent objects 必须在每个 training fold 内重算：

- `DeltaHFScore`
- nuisance residuals
- `rho_ULF`
- `M_ULF`
- `F+`
- `F-`
- `SweetPeak5`
- `SourPeak5`
- `NetULFFiberScore`
- final prediction model

禁止作为加速手段的做法：

```text
reducing formal B=10000
adaptive permutation early stopping
full-sample ranks in fold-level estimation
approximate ranks
full-sample candidate mask replacing fold-specific candidate masks
fixed full-sample F+/F- used for LOOCV scoring
permutation score computed only from observed maps
outcome- or preliminary-rho-based fiber prefiltering
skipping sour fibers
using target-level aggregation as the primary model
```

任何 optimized implementation 在正式执行前，都必须在一个 small deterministic brute-force subset 上通过 exact-equivalence regression test。

## 执行优先级与 Gatekeeping

该模型按 gatekeeping 顺序执行。

当前可执行 branches：

```text
primary:
  ulf_peak_efield_tau800_primary

sensitivity:
  ulf_peak_efield_tau1500_sensitivity
  ulf_top1500_top500_sensitivity

control:
  ulf_plain_connected_streamline_control
```

当前 connectome 角色：

```text
PPMI 85 (Ewert 2017)          observed figure-grade robustness
MGH-USC HCP 32 (Horn 2017)    observed figure-grade robustness
dTOR-985 Full (Elias 2024)    primary analysis
```

### Round 0: Version, Input, And Manifest Freeze

只运行检查：

```text
lock document version
lock endpoint list
lock scale list
lock connectome list
lock branch list
lock tau800 / tau1500 / Coverage>=5
lock seed = 42
check HF and ULF e-field manifests
check clinical ID join
check scale direction
check DeltaHFScore source
check PPMI / MGH / dTOR readability
check output root writability
```

只有当所有输入都唯一解析，并且 manifest 记录了锁定参数集后，才进入 Round 1。

### Round 1: Sidecar Cache And Equivalence Test

为 HF component exposure、ULF component exposure 和 tau-specific ULF-only exposure 构建 PPMI/MGH sidecars 与 dTOR chunked sidecars。运行 deterministic small-subset equivalence test，覆盖 candidate definition、partial Spearman、selected fibers、`NetULFFiberScore`、LOOCV prediction、smoke permutation 和 bootstrap summaries。

只有当 optimized 和 brute-force outputs 在预定义 tolerance 内一致，且 dTOR chunked IO 没有 memory error 时，才进入 Round 2。

### Round 2: Primary Observed Chronic Endpoint

运行：

```text
endpoint = chronic 3-month HF+ULF add-on
branch = ulf_peak_efield_tau800_primary
connectome order = PPMI observed -> MGH observed -> dTOR observed
```

只有当 dTOR observed LOOCV 完成、fold-specific candidates 非空、`NetULFFiberScore` 有非零方差、validation metrics 均有限时，才进入 Round 3。

### Round 3: Primary Observed Immediate Endpoint

运行：

```text
endpoint = immediate HF+ULF motor add-on
branch = ulf_peak_efield_tau800_primary
connectome order = PPMI observed -> MGH observed -> dTOR observed
```

只有当 immediate endpoint join 正确、candidate masks 非空、`NetULFFiberScore` 非常数且 LOOCV prediction 可拟合时，才进入 Round 4。

### Round 4: Plain Connected-Streamline Control

对通过 observed gates 的 endpoints/connectomes 运行 `ulf_plain_connected_streamline_control`。比较 nuisance-only、plain exposure、ULF net score 和 joint QC models。

只有当 `PlainExposureTop5` 可计算、joint QC model 非奇异、`NetULFFiberScore` 与 `PlainExposureTop5` 不完全共线时，才进入 Round 5。

### Round 5: dTOR Primary Smoke Resampling

只对通过 observed gates 的 dTOR primary branches 运行：

```text
Freedman-Lane smoke permutation B=1000
subject-level smoke bootstrap B=1000
seed = 42
```

只有当 smoke permutation/bootstrap 完成、plus-one p-values 可计算、bootstrap finite counts 可解释，并且 runtime profile 表明 formal `B=10000` 可行时，才进入 Round 6。

### Round 6: Cheap Observed Sensitivity

运行 observed-only sensitivity：

```text
ulf_peak_efield_tau1500_sensitivity
ulf_top1500_top500_sensitivity
PPMI -> MGH -> dTOR
```

这些 branches 不运行 formal permutation/bootstrap。只有当 sensitivity outputs 有限，或明确记录 candidate-empty / threshold-too-strict 状态后，才进入 Round 7。

### Round 7: dTOR Primary Formal Resampling

只运行：

```text
connectome = dTOR
branch = ulf_peak_efield_tau800_primary
formal permutation B=10000
formal bootstrap B=10000
seed = 42
```

只有当 formal resampling 完成，并且 manifest 记录 `resampling_status = formal_complete` 后，才进入 Round 8。

### Round 8: Display, FDR, Labels, Density, And Cross-Connectome Summaries

只在 numeric branches 锁定后生成 display 和 interpretation outputs。Display、FDR、label、density 和 cross-connectome outputs 必须来自 finalized numeric outputs，并且不得改变主模型。

## 解释边界

该模型使用 public normative connectomes 估计 HF-adjusted ULF-only add-on association。它不是解剖 SNr gain 模型，也不声称 ULF 效应局限于 SNr 或预定义 seed-target pathways。主 predictor 表示在 HF-overlap streamlines 归入 `DeltaHFScore` 的 HF adjustment 后，由 ULF 唯一招募的 streamlines。

由于 `n=16`，所有 ULF fiber-level 结果都是 hypothesis-generating。阴性或不稳定的 LOOCV 结果不应被解释为 ULF 没有生物学效应；它也可能反映样本量有限、endpoint 噪声、stimulation-field 不确定性或 connectome 局限。
