# HF-status-resolved ULF-only Add-On Gain Normative Connectome Fiber 模型 - Revised

Version: 2026-07-05 revised specification
Scope: ULF add-on normative connectome fiber-level model, aligned to `hf_3m_normative_connectome_fiber_model.md`.

---

## 1. Research Question / 研究问题

加入 ULF 刺激后，哪些 ULF-only normative connectome streamlines 与额外临床获益相关，并且这种关联已经校正：

```text
1. the patient's pre-ULF HF clinical state, and
2. the matched HF normative fiber model's predicted change in HF-component engagement.
```

这是 right-canonical、full-connectome、fiber-level 模型。公共 structural connectomes 中的单条 streamline 是主建模单位。Target atlases 只在建模之后用于 endpoint labels、anatomical enrichment、QC、display grouping 和 interpretation。它们不定义 primary candidate universe，也不定义 primary predictors。

频率定义固定为：

```text
HF  = high-frequency stimulation component, frequency_Hz >= 100
ULF = ultra-low-frequency stimulation component, frequency_Hz <= 50
```

Primary predictor 表示在 HF-overlap streamlines 通过 `DeltaHFScore` 归入 HF adjustment 后，由 ULF component 唯一招募的 streamlines。

---

## 2. Study Timeline And Endpoint Definitions / 研究时间线与终点定义

临床时间线显式定义为：

```text
T0:
  preoperative baseline assessment

T1:
  postoperative 1-month HF immediate activation assessment

T2:
  3 months after HF activation
  HF-only 3-month follow-up assessment
  same-day switch to HF+ULF
  same-day HF+ULF immediate assessment

T3:
  3 months after HF+ULF switch
  HF+ULF 3-month follow-up assessment
```

Immediate HF+ULF outcome 和 HF-only 3-month clinical reference state 均在 `T2` 同一天测量。因此 immediate endpoint 是有效的 same-day acute add-on endpoint，不是跨天 comparator。

使用 endpoint-specific variable names：

```text
Y_HF_ref_T2_domain =
  raw HF-only 3-month score measured at T2 immediately before same-day HF+ULF switch

Y_HFplusULF_immediate_T2_domain =
  raw same-day HF+ULF immediate score after switching to HF+ULF at T2

Y_HFplusULF_3m_T3_domain =
  raw HF+ULF 3-month score measured at T3
```

两个 endpoint families 分开建模。

### 2.1 Chronic endpoint

```text
Y_post = Y_HFplusULF_3m_T3_domain
Y_HF_ref = Y_HF_ref_T2_domain
DeltaHFScore = DeltaHFScore_chronic_domain
```

解释：

```text
sustained HF-state-adjusted ULF add-on association after 3 months of HF+ULF exposure
```

### 2.2 Immediate endpoint

```text
Y_post = Y_HFplusULF_immediate_T2_domain
Y_HF_ref = Y_HF_ref_T2_domain
DeltaHFScore = DeltaHFScore_immediate_domain
```

解释：

```text
same-day HF-state-adjusted ULF acute add-on association
```

### 2.3 Endpoint hierarchy

默认 first-pass endpoints：

```text
Primary formal endpoint:
  MDS-UPDRS III total chronic HF+ULF 3-month score

Key secondary endpoint:
  MDS-UPDRS III total same-day HF+ULF immediate score, if available
```

Immediate endpoint 只有在 pre-run 显式决定后才提升为 co-primary。若未提升，则只运行 observed LOOCV 和可选 smoke resampling，不默认运行 formal `B=10000` resampling。

### 2.4 Add-on gain sensitivity endpoints

主模型是 raw post-score ANCOVA-style model，因此 add-on gain 仅作为 sensitivity 报告。

低分更好量表：

```text
Gain_immediate_i = Y_HF_ref_T2_i - Y_HFplusULF_immediate_T2_i
Gain_chronic_i   = Y_HF_ref_T2_i - Y_HFplusULF_3m_T3_i
```

高分更好量表：

```text
Gain_immediate_i = Y_HFplusULF_immediate_T2_i - Y_HF_ref_T2_i
Gain_chronic_i   = Y_HFplusULF_3m_T3_i - Y_HF_ref_T2_i
```

所有 gain 定义中：

```text
positive Gain = improvement after adding ULF
```

Gain sensitivity model：

```text
Gain_i = alpha
       + delta * NetULFFiberScore_i
       + gamma * DeltaHFScore_i
       + error_i
```

该 sensitivity 检查 primary raw post-score model 是否与 direct within-subject add-on gain formulation 一致。

---

## 3. Inputs / 输入

必需输入：

```text
Public Lead-DBS structural connectomes:
  PPMI 85
  MGH-USC HCP 32
  dTOR-985 Full

HF+ULF programming split into HF and ULF components
Raw sim-efield or accepted e-field-like exposure maps for HF component and ULF component
HF-only reference e-fields from the pre-ULF HF-only phase
Raw HF-only and HF+ULF clinical scores
Normative HF fiber-level model outputs from hf_3m_normative_connectome_fiber_model.md
Connected-region atlases for endpoint labels, anatomical enrichment, and STN/SNr overlays
```

E-field 规则：

```text
use raw sim-efield or explicitly accepted e-field-like exposure maps
record units as V/m
record frequency, pulse width, amplitude, contacts, side, phase, and component labels
missing or multiply matched e-fields fail the endpoint/run
subjects are not silently excluded
missing e-fields are not automatically created by this model
```

Component-specific proxy fields 只在 manifest 记录 proxy status 后允许：

```text
component_field_type:
  true_component_separable
  interleaved_proxy
  synchronous_mixed_proxy
  ambiguous_component_assignment
```

如果大多数病例使用 proxy fields，解释必须写作：

```text
ULF-component proxy exposure association
```

而不是：

```text
direct ULF biophysical field association
```

---

## 4. Locked HF Adjustment Source / 锁定 HF 调整来源

只有在 matched HF normative fiber model source for `DeltaHFScore` 已锁定后，ULF model 才可进入 formal analysis。

Locked HF source：

```text
model_family = hf_3m_normative_connectome_fiber_model
connectome = connectome-matched
branch = peak_efield_tau800_primary
tau = 800 V/m
coverage = Coverage>=5
estimator = partial_spearman
score = NetFiberScore
F+ = top 1% positive HF fibers
F- = top 0.5% sour HF fibers
SweetPeak5/SourPeak5 = mean top 5% patient-specific weighted selected fibers
map source in LOOCV = training-fold HF model
full-sample HF model = descriptive scores only
```

Connectome-matched rule：

```text
ULF/PPMI uses HF/PPMI DeltaHFScore
ULF/MGH  uses HF/MGH  DeltaHFScore
ULF/dTOR uses HF/dTOR DeltaHFScore
```

跨所有 ULF connectomes 共享 dTOR-HF adjustment 只能作为 sensitivity 报告：

```text
shared_dTOR_HF_adjustment_sensitivity
```

不要把 DeltaHF-adjusted ULF branch 解释为 primary，除非 matched HF normative branch 已满足以下条件：

```text
observed LOOCV completed
non-empty candidate fibers in all relevant folds
NetFiberScore nonzero variance
finite LOOCV predictions
interpretable Q2 against Y_base-only baseline
no severe selected-fiber instability
no severe plain-control replacement
```

只要输入可用，ULF normative fiber 实现层面同时运行 DeltaHF-adjusted 和 no-DeltaHF 两个同等地位的 core branch。随后根据 locked HF result 在 model report 中记录哪个 branch 是解释上的 primary branch：

```text
if HF model is predictive_valid:
  ulf_primary_branch = delta_hf_adjusted
  delta_hfscore_role = primary nuisance adjustment
  no_delta_hf_role   = sensitivity

if HF model is stable_nonpredictive:
  ulf_primary_branch = no_delta_hf
  delta_hfscore_role = sensitivity / compatibility adjustment
  no_delta_hf_role   = primary

if HF model is unstable_or_failed:
  ulf_primary_branch = no_delta_hf when ULF inputs remain valid
  delta_hfscore_role = exploratory only, or not run if HF support is unavailable
  no_delta_hf_role   = primary exploratory branch
```

Branch-role decision 必须写入 model manifest：

```text
hf_prediction_validity_status
hf_prediction_validity_source
ulf_primary_branch
ulf_core_branches_run
ulf_sensitivity_branches
delta_hfscore_role
branch_role_decision_reason
hf_model_support_status
```

如果 matched HF branch 失败或技术退化，`DeltaHFScore` 必须标记为不稳定 generated covariate，不能定义 ULF 的 primary interpretation。

---

## 5. Feature Construction / 特征构建

可执行 feature space 是 right-canonical streamline feature space。左侧刺激通过 `ea_flip_lr_nonlinear` 翻转到 right canonical space 后，在同一组 right-sided streamline features 上采样。

对 patient `i` 和 right-canonical streamline `l`：

```text
E_HF_R_i(l)       = peak HF-component exposure along right canonical fiber l
E_HF_L_to_R_i(l)  = peak left HF-component exposure after nonlinear L-to-R flip
E_ULF_R_i(l)      = peak ULF-component exposure along right canonical fiber l
E_ULF_L_to_R_i(l) = peak left ULF-component exposure after nonlinear L-to-R flip

X_HF_component_i(l)  = (E_HF_R_i(l)  + E_HF_L_to_R_i(l))  / 2
X_ULF_component_i(l) = (E_ULF_R_i(l) + E_ULF_L_to_R_i(l)) / 2
```

用于 `DeltaHFScore` 的 HF-only reference exposure：

```text
E_HFonly_ref_R_i(l)      = peak HF-only reference exposure along right canonical fiber l
E_HFonly_ref_L_to_R_i(l) = peak left HF-only reference exposure after nonlinear L-to-R flip

X_HFonly_ref_i(l) =
  (E_HFonly_ref_R_i(l) + E_HFonly_ref_L_to_R_i(l)) / 2
```

Same-side same-frequency alternating subprograms：

```text
primary rule:
  combine same-side same-frequency subprogram e-fields by voxel-wise maximum
  before streamline sampling

allowed optimization:
  streamline-wise maximum only if exact-equivalence testing proves equality
  against voxel-wise maximum on a deterministic subset
```

Peak E-field branch 中 exposure 不按 frequency 或 pulse width 缩放。Frequency 只用于把 component 分类为 HF 或 ULF；pulse width 和 frequency 记录在 provenance 中。

---

## 6. ULF-Only Exposure And Candidate Fibers / ULF-only exposure 与候选纤维

ULF-only exposure 是 tau-specific，因为 tau 同时定义 component activity 和 HF-overlap exclusion。

对每个 tau：

```text
tau_primary = 800 V/m
tau_sensitivity = 1500 V/m

ULF_touched_i(l,tau) = X_ULF_component_i(l) > tau
HF_touched_i(l,tau)  = X_HF_component_i(l)  > tau

X_ULF_only_i(l,tau) =
  X_ULF_component_i(l), if ULF_touched_i(l,tau) and not HF_touched_i(l,tau)
  0,                   otherwise
```

如果某条 streamline 在 branch tau 下同时被 HF 和 ULF components touched，则分配给 HF adjustment，并从 primary ULF-only predictor 中排除。

Candidate rule：

```text
Coverage_ULF_tau(l) = sum_i I[X_ULF_only_i(l,tau) > tau]
F_candidate_ULF_tau = {l: Coverage_ULF_tau(l) >= 5}
```

Candidate universe 是完整 public connectome，而不是 target-restricted seed-target tracts。

重要解释规则：

```text
For ULF, tau is part of the exposure definition.
It is not merely a candidate coverage threshold.
```

因此：

```text
ulf_peak_efield_tau1500_sensitivity
```

是 ULF-only exposure-definition sensitivity，而不是简单的 threshold robustness check。

---

## 7. DeltaHFScore: Matched HF Normative Fiber Score Projection

`DeltaHFScore` 是由 locked HF normative fiber model 派生的 nuisance covariate。

对每个 LOOCV training fold，定义 training-fold HF score operator：

```text
O_HF_fold = {
  M_HF_fold(l),
  F+_HF_fold,
  F-_HF_fold,
  SweetPeak5 rule,
  SourPeak5 rule,
  NetFiberScore rule
}
```

对任意 HF exposure matrix `E`，定义：

```text
S_HF_norm_fiber(E; O_HF_fold)_i = NetFiberScore_i obtained by applying
                                  the locked training-fold HF operator
                                  to exposure E for patient i
```

显式写为：

```text
SweetWeighted_HF_i(l) = X_E_i(l) * M_HF_fold(l),       l in F+_HF_fold
SourWeighted_HF_i(l)  = X_E_i(l) * [-M_HF_fold(l)],    l in F-_HF_fold

SweetPeak5_HF_i = mean top 5% largest SweetWeighted_HF_i(l)
SourPeak5_HF_i  = mean top 5% largest SourWeighted_HF_i(l)

S_HF_norm_fiber(E; O_HF_fold)_i = SweetPeak5_HF_i - SourPeak5_HF_i
```

然后：

```text
DeltaHFScore_chronic_i =
  S_HF_norm_fiber(E_HF_component_T3_HFplusULF; O_HF_fold)_i
  - S_HF_norm_fiber(E_HFonly_ref_T2; O_HF_fold)_i

DeltaHFScore_immediate_i =
  S_HF_norm_fiber(E_HF_component_T2_HFplusULF_immediate; O_HF_fold)_i
  - S_HF_norm_fiber(E_HFonly_ref_T2; O_HF_fold)_i
```

规则：

```text
Do not refit the HF model using HF+ULF outcomes.
Do not refit the HF model using HF+ULF exposure as the HF training exposure.
Do not use full-sample HF M_HF, F+, or F- to score held-out patients in LOOCV.
Do not replace the HF normative score with a direct voxel HF score.
Do not replace the connectome-matched HF score with another connectome unless running an explicitly labeled sensitivity.
```

`DeltaHFScore` 可在每个 training fold 内 z-score 以改善数值稳定性。Z-scoring parameters 只从 training patients 学得，并应用到 held-out patient。回归前不施加固定生物学缩放系数。

---

## 8. DeltaHFScore Support And Out-Of-Support HF Exposure

### 8.1 Support definitions

Locked HF 3-month model 有有限 learned support。

对每个 HF training fold：

```text
F_HF_candidate_fold =
  candidate fibers satisfying HF tau800 Coverage>=5 in the HF training fold

F_HF_valid_fold =
  F_HF_candidate_fold intersect fibers with finite non-degenerate M_HF_fold(l)

F_HF_score_fold =
  F+_HF_fold union F-_HF_fold
```

`DeltaHFScore` 只通过 locked HF scoring operator 计算：

```text
F_HF_score_fold = F+_HF_fold union F-_HF_fold
```

`F_HF_score_fold` 外的 fibers 不贡献 `DeltaHFScore`。

这不是将该 fiber 的生物学 HF 效应插补为 0。它只表示：

```text
outside the locked HF NetFiberScore operator
```

### 8.2 If HF+ULF HF-component exposure touches fibers outside HF-3m coverage

如果 HF+ULF 期间的 `E_HF_component` touched 了 HF-3m model coverage 或 score support 外的 fibers：

```text
Do not extrapolate M_HF to those fibers.
Do not smooth weights onto those fibers.
Do not assign nearest-neighbor HF weights.
Do not add those fibers into F+ or F-.
Do not retrain the HF model using HF+ULF exposure or outcome.
```

Primary `DeltaHFScore` 仍为：

```text
DeltaHFScore_in_support =
  S_HF_norm_fiber(E_HF_component; O_HF_fold)
  - S_HF_norm_fiber(E_HFonly_ref; O_HF_fold)
```

其中 `S_HF_norm_fiber` 只使用 `F_HF_score_fold`。

Learned HF support 外的所有 HF-component exposure 均作为 QC 报告，不能静默视为已完全控制。

### 8.3 Required support QC metrics

对每个 subject、endpoint、connectome、branch 和 LOOCV fold，计算：

```text
HF_component_total_touched_count_tau800
HF_component_total_exposure_sum_tau800
HF_component_total_exposure_top5_tau800

HF_component_in_HF_candidate_count_tau800
HF_component_in_HF_candidate_sum_tau800
HF_component_in_HF_candidate_top5_tau800

HF_component_in_HF_valid_count_tau800
HF_component_in_HF_valid_sum_tau800
HF_component_in_HF_valid_top5_tau800

HF_component_in_HF_selected_count_tau800
HF_component_in_HF_selected_sum_tau800
HF_component_in_HF_selected_top5_tau800

HF_component_out_HF_candidate_count_tau800
HF_component_out_HF_candidate_sum_tau800
HF_component_out_HF_candidate_top5_tau800

HF_component_out_HF_selected_count_tau800
HF_component_out_HF_selected_sum_tau800
HF_component_out_HF_selected_top5_tau800

HF_out_candidate_fraction_tau800 =
  HF_component_out_HF_candidate_sum_tau800
  / max(HF_component_total_exposure_sum_tau800, epsilon)

HF_out_selected_fraction_tau800 =
  HF_component_out_HF_selected_sum_tau800
  / max(HF_component_total_exposure_sum_tau800, epsilon)
```

写出：

```text
normative_ULF_fiber_delta_hf_support_summary.csv
normative_ULF_fiber_delta_hf_support_qc.json
```

将 `HF_out_candidate_fraction_tau800` 解释为主要 support failure indicator。

`HF_out_selected_fraction_tau800` 需要更谨慎解释，因为 NetFiberScore 本来就只使用 selected sweet/sour HF fibers。刺激接触许多 nonscoring fibers 时，high out-selected exposure 是预期现象；high out-candidate exposure 更令人担忧。

### 8.4 Gatekeeping rules for out-of-support exposure

默认 gate：

```text
Proceed without downgrading:
  cohort median HF_out_candidate_fraction_tau800 <= 0.20
  and no more than 25% of subjects have HF_out_candidate_fraction_tau800 > 0.50

Proceed but downgrade interpretation:
  cohort median HF_out_candidate_fraction_tau800 > 0.20
  or more than 25% of subjects have HF_out_candidate_fraction_tau800 > 0.50

Do not present the ULF branch as formally HF-adjusted:
  HF_out_candidate_fraction_tau800 is extreme enough that DeltaHFScore no longer represents the HF-component change for many subjects
  or HF component programming moved mainly into territory never covered by the locked HF model
```

如果 out-of-support exposure 很大，增加 QC-only 或 secondary sensitivity model：

```text
Y_post ~ NetULFFiberScore
       + Y_HF_ref
       + DeltaHFScore_in_support
       + PlainHFOutSupportTop5
```

其中：

```text
PlainHFOutSupportTop5 =
  mean top 5% X_HF_component_i(l)
  among HF-component-touched fibers outside F_HF_candidate_fold
```

如果该变量与 `NetULFFiberScore`、`DeltaHFScore` 或 `Y_HF_ref` 高度共线，不要强行纳入主模型。对于 `n=16`，它主要是 diagnostic。

### 8.5 Fibers inside HF candidate support but outside HF selected score support

如果 fiber 位于 `F_HF_candidate_fold` 或 `F_HF_valid_fold` 内，但不在 `F_HF_score_fold` 中，它位于 learned HF model universe 内，但在 HF NetFiberScore operator 外。它不贡献 `DeltaHFScore`，因为 locked HF scoring model 没有选择它。

这不是技术失败。报告为：

```text
in-candidate / non-selected HF-component exposure
```

而不是 out-of-coverage exposure。

### 8.6 Fibers absent from the public connectome

如果某条解剖通路未被 public connectome 表示，它无法在 HF 或 ULF normative models 中评分。这是 connectome limitation，不是该通路无关的证据。

报告为：

```text
not represented in the normative connectome feature space
```

不允许 imputation。

---

## 9. Core Statistical Models / 核心统计模型

### 9.0 Core Branch A: DeltaHF-Adjusted Partial Spearman

DeltaHF-adjusted fiber-level estimator 是 nuisance-adjusted partial Spearman。

对每个 endpoint 和 candidate fiber `l`：

```text
rho_ULF(l) =
  corr(
    resid(rank(Y_post_i)             ~ rank(Y_HF_ref_i) + rank(DeltaHFScore_i)),
    resid(rank(X_ULF_only_i(l,tau))  ~ rank(Y_HF_ref_i) + rank(DeltaHFScore_i))
  )
```

ties 使用 average ranks。ULF-only exposure variance、rank variance 或 residualized exposure variance 为 0 的 degenerate fibers 赋值为：

```text
rho_ULF(l) = NaN
```

并从 selected-fiber sets 和 scoring 中排除。

Benefit-oriented fiber weight：

```text
M_ULF(l) = -rho_ULF(l)   for lower-is-better scales
M_ULF(l) =  rho_ULF(l)   for higher-is-better scales
```

解释：

```text
M_ULF(l) > 0:
  ULF-only exposure to this streamline is benefit-associated

M_ULF(l) < 0:
  ULF-only exposure to this streamline is worse-outcome-associated
```

### 9.1 Patient-level NetULFFiberScore

在每个 full-sample map 或 LOOCV training fold 内：

```text
F+_ULF = top 1% fibers with largest positive M_ULF(l)
F-_ULF = top 0.5% fibers with most negative M_ULF(l)
```

对每个 patient：

```text
SweetWeighted_ULF_i(l) = X_ULF_only_i(l,tau) * M_ULF(l),      l in F+_ULF
SourWeighted_ULF_i(l)  = X_ULF_only_i(l,tau) * [-M_ULF(l)],   l in F-_ULF

SweetPeak5_ULF_i = mean top 5% largest SweetWeighted_ULF_i(l)
SourPeak5_ULF_i  = mean top 5% largest SourWeighted_ULF_i(l)

NetULFFiberScore_i = SweetPeak5_ULF_i - SourPeak5_ULF_i
```

Selection and edge cases：

```text
F+ and F- are selected within F_candidate_ULF_tau
NaN or degenerate fibers are excluded
percentile counts use ceil(percent * n)
minimum count is 1 when the corresponding positive or negative pool is non-empty
empty F+ gives SweetPeak5 = 0
empty F- gives SourPeak5 = 0
if a selected set is non-empty but a patient has zero exposure to all selected fibers, that peak component is 0
```

### 9.2 Final prediction model

DeltaHF-adjusted prediction model：

```text
Y_post_i = alpha
         + delta * NetULFFiberScore_i
         + beta  * Y_HF_ref_i
         + gamma * DeltaHFScore_i
         + error_i
```

DeltaHF-adjusted nuisance-only baseline：

```text
Y_post_i = alpha
         + beta  * Y_HF_ref_i
         + gamma * DeltaHFScore_i
         + error_i
```

No-DeltaHF prediction model：

```text
Y_post_i = alpha
         + delta * NetULFFiberScore_noDeltaHF_i
         + beta  * Y_HF_ref_i
         + error_i
```

No-DeltaHF nuisance-only baseline：

```text
Y_post_i = alpha
         + beta * Y_HF_ref_i
         + error_i
```

Branch-role resolver 选中分支的 primary validation statistic：

```text
LOOCV Spearman rho between held-out predicted Y_post and held-out observed Y_post
```

Secondary metrics：

```text
LOOCV Pearson r
MAE
RMSE
Q2 relative to branch-specific nuisance-only baseline
```

```text
Q2 = 1 - SSE_ULFScore_model / SSE_branch_specific_nuisance_only_baseline
```

---

## 10. Sensitivity Models / 敏感性模型

### 10.1 Non-selected core branch comparison

目的：比较未被选为 primary 的 core branch 与 selected primary branch。当 matched HF model 为 `stable_nonpredictive` 时，no-DeltaHF branch 是 primary，DeltaHF-adjusted branch 是 comparison branch。当 matched HF model 为 `predictive_valid` 时，DeltaHF-adjusted branch 是 primary，no-DeltaHF branch 是 comparison branch。

Fiber estimator：

```text
rho_ULF_noDeltaHF(l) =
  corr(
    resid(rank(Y_post_i)            ~ rank(Y_HF_ref_i)),
    resid(rank(X_ULF_only_i(l,tau)) ~ rank(Y_HF_ref_i))
  )
```

Prediction：

```text
Y_post_i = alpha
         + delta * NetULFFiberScore_noDeltaHF_i
         + beta  * Y_HF_ref_i
         + error_i
```

No-DeltaHF branch name：

```text
ulf_peak_efield_tau800_no_delta_hf
```

该 branch 不自动是次要分支。它的角色由 branch-role resolver 指定。未被选为 primary 的 core branch 生成 observed LOOCV outputs，但除非显式提升，否则不接受 formal `B=10000` resampling。

### 10.2 Total ULF exposure sensitivity

目的：检验 hard HF-overlap exclusion 是否移除了生物学上相关的 ULF effects。

Exposure：

```text
X_ULF_total_i(l) = X_ULF_component_i(l)
```

该分支不做 HF-overlap exclusion，但仍调整 `Y_HF_ref` 和 `DeltaHFScore`。

Branch name：

```text
ulf_total_exposure_tau800_sensitivity
```

该 branch 不是 primary。如果 total ULF exposure 为正，但 ULF-only exposure 为负或 null，解释应说明 primary hard-exclusion definition 可能移除了 co-modulated ULF effects。

### 10.3 Tau1500 ULF-only exposure-definition sensitivity

Branch：

```text
ulf_peak_efield_tau1500_sensitivity
```

这不仅是 high-threshold robustness check。它会改变 ULF touched status、HF touched status、HF-overlap exclusion、`X_ULF_only`、candidate fibers 和 patient scores。

### 10.4 Top1500/top500 selected-fiber sensitivity

Branch：

```text
ulf_top1500_top500_sensitivity
```

使用 fixed selected-fiber counts：

```text
top 1500 positive fibers
top 500 negative/sour fibers
```

该分支检查结果对 percentile selected-fiber rule 的依赖程度。

### 10.5 Optional OLS ANCOVA

仅文档记录，默认不运行：

```text
Y_post_i ~ X_ULF_only_i(l,tau) + Y_HF_ref_i + DeltaHFScore_i
```

它不替代 primary partial Spearman estimator。

### 10.6 Future ULF OSS-DBS activation sensitivity

除非显式启用，否则不属于当前 executable mainline。

若启用，OSS branch 应继承 ULF peak-E-field candidate universe，并在 candidate definition 后用 modeled ULF activation 替换 `X_ULF_only`。OSS activation 不得重新定义 candidate fibers。

---

## 11. Validation / 验证

使用 fully nested leave-one-patient-out cross-validation。

对每个 connectome、endpoint、scale、branch 和 held-out patient `h`：

```text
train = all patients except h
test  = patient h
```

每个 training fold 内：

```text
1. Fit or retrieve the matched training-fold HF normative fiber model.
2. Compute fold-specific DeltaHFScore for training patients and the held-out patient.
3. Compute fold-specific X_ULF_only_i(l,tau).
4. Define F_candidate_ULF_tau using training-patient Coverage_ULF_tau(l) >= 5.
5. Estimate rho_ULF(l) and M_ULF(l) using training patients only.
6. Select fold-specific F+_ULF and F-_ULF.
7. Compute NetULFFiberScore for training patients and the held-out patient.
8. Fit the branch-specific prediction model on training patients.
9. Predict held-out Y_post.
```

Fold-level 禁止项：

```text
no full-sample ULF candidate mask for LOOCV scoring
no full-sample ranks
no full-sample M_ULF
no full-sample F+_ULF or F-_ULF
no held-out patient in candidate definition
no held-out patient in ULF map fitting
no held-out patient in selected-fiber selection
no held-out patient in final prediction-model fitting
no full-sample HF model for held-out DeltaHFScore
```

---

## 12. Permutation And Bootstrap

### 12.1 Freedman-Lane permutation

Formal permutation 只限 branch-role resolver 记录为 primary 的 dTOR branch，除非另一个 endpoint 被显式提升。

```text
connectome = dTOR
branch = ulf_peak_efield_tau800_primary_by_hf_status
formal B = 10000
smoke B = 1000
seed = 42
primary statistic = LOOCV Spearman rho
p_plus_one = (1 + count(|stat_perm| >= |stat_obs|)) / (B + 1)
```

Branch-specific nuisance model：

```text
delta_hf_adjusted: Y_post ~ Y_HF_ref + DeltaHFScore
no_delta_hf:       Y_post ~ Y_HF_ref
```

Permutation workflow：

```text
1. Fit nuisance model.
2. Permute nuisance residuals.
3. Reconstruct permuted Y*.
4. Rerun full ULF LOOCV workflow:
   - candidate definition
   - rho_ULF
   - M_ULF
   - F+_ULF / F-_ULF
   - NetULFFiberScore
   - held-out prediction
   - LOOCV statistic
```

ULF permutation 中的 `DeltaHFScore`：

```text
DeltaHFScore is fold-dependent and HF-model-dependent.
It is not dependent on the permuted ULF outcome.
```

因此，在固定 outer fold 和固定 HF model cache 内，`DeltaHFScore` 可跨 ULF outcome permutations 复用。这是允许的 exact optimization。Bootstrap 必须重算 `DeltaHFScore`，因为 bootstrap subject multiplicity 会改变 HF model fitting sample。

### 12.2 Subject-level bootstrap

Formal bootstrap 只限 branch-role resolver 记录为 primary 的 dTOR branch，除非另一个 endpoint 被显式提升。

```text
formal B = 10000
smoke B = 1000
seed = 42
```

每个 bootstrap resample 必须重跑：

```text
matched HF model fitting / DeltaHFScore
ULF-only exposure and coverage
F_candidate_ULF_tau
rho_ULF
M_ULF
F+_ULF / F-_ULF
NetULFFiberScore
bootstrap stability summaries
```

不要存储完整 `B=10000` fiber-weight tables。使用 streaming finite-count、selection-frequency 和 sign-stability summaries。

---

## 13. Plain Controls And Burden QC

### 13.1 ULF-only plain connected-streamline control

对每个 patient：

```text
Touched_ULF_only_i(l) = I[X_ULF_only_i(l,tau) > tau]

PlainULFOnlyTouchedCount_i = sum_l Touched_ULF_only_i(l)
PlainULFOnlyExposureSum_i  = sum_l X_ULF_only_i(l,tau)
PlainULFOnlyExposureTop5_i = mean top 5% X_ULF_only_i(l,tau) among touched candidate fibers
```

比较：

```text
Y_post ~ Y_HF_ref + DeltaHFScore
Y_post ~ PlainULFOnlyExposureTop5 + Y_HF_ref + DeltaHFScore
Y_post ~ NetULFFiberScore + Y_HF_ref + DeltaHFScore
Y_post ~ NetULFFiberScore + PlainULFOnlyExposureTop5 + Y_HF_ref + DeltaHFScore
```

Joint model 只作为 QC。对于 `n=16`，不能解释为强因果分解。

### 13.2 Additional burden QC variables

计算但不强制进入 primary model：

```text
PlainULFTotalExposureTop5
PlainHFComponentExposureTop5
PlainHFOverlapExposureTop5
PlainHFOutSupportTop5
HFOverlapFraction
ULFOnlyToTotalULFFraction
```

必需 correlations / diagnostics：

```text
corr(NetULFFiberScore, Y_HF_ref)
corr(NetULFFiberScore, DeltaHFScore)
corr(Y_HF_ref, DeltaHFScore)
corr(NetULFFiberScore, PlainULFOnlyExposureTop5)
corr(NetULFFiberScore, PlainULFTotalExposureTop5)
corr(NetULFFiberScore, PlainHFOverlapExposureTop5)
corr(NetULFFiberScore, PlainHFOutSupportTop5)
VIF / condition number for final model
leave-one-subject-out coefficient sign stability
Cook's distance / DFBETA for final model
```

Collinearity flags：

```text
|corr| < 0.85: acceptable
0.85 <= |corr| < 0.95: high collinearity warning
|corr| >= 0.95: severe collinearity warning
```

---

## 14. Outputs / 输出

输出根目录：

```text
/Volumes/VAL/STNSNr/summary/normative_connectome_fiber/ulf/<connectome_slug>/<endpoint_slug>/<scale_slug>/<branch>/
```

每个 completed branch 的 required numeric outputs：

```text
normative_ULF_fiber_weights.csv
normative_ULF_fiber_scores.csv
normative_ULF_fiber_loocv_predictions.csv
normative_ULF_fiber_permutation_summary.csv
normative_ULF_fiber_bootstrap_summary.csv
normative_ULF_fiber_mapping_qc.json
normative_ULF_fiber_generation_manifest.json
normative_ULF_fiber_HF_overlap_exclusion_summary.csv
normative_ULF_fiber_delta_hf_support_summary.csv
normative_ULF_fiber_delta_hf_support_qc.json
```

`normative_ULF_fiber_weights.csv` fields：

```text
connectome
endpoint_slug
scale_slug
branch
branch_role
delta_hfscore_role
fiber_id
tau_v_per_m
coverage_ULF_only
rho_ULF
p_uncorrected
q_fdr
M_ULF
direction_class
is_top1_positive
is_top0p5_sour
is_top1500_positive
is_top500_negative
HF_overlap_coverage
ULF_only_to_total_ULF_exposure_fraction
target_labels_for_qc
```

`normative_ULF_fiber_scores.csv` fields：

```text
subject_id
connectome
endpoint_slug
scale_slug
branch
branch_role
delta_hfscore_role
score_map_source
Y_post
Y_HF_ref
DeltaHFScore
DeltaHFScore_in_support
NetULFFiberScore
SweetPeak5_ULF
SourPeak5_ULF
PlainULFOnlyExposureTop5
PlainULFTotalExposureTop5
PlainHFComponentExposureTop5
PlainHFOverlapExposureTop5
PlainHFOutSupportTop5
HF_out_candidate_fraction_tau800
HF_out_selected_fraction_tau800
n_candidate_fibers
n_sweet_selected_fibers
n_sour_selected_fibers
n_sweet_peak_fibers
n_sour_peak_fibers
is_primary_score
```

LOOCV prediction file：

```text
normative_ULF_fiber_loocv_predictions.csv
```

Required fields：

```text
subject_id
fold_id
endpoint_slug
scale_slug
connectome
branch
Y_post_observed
Y_post_predicted_ULF_model
Y_post_predicted_nuisance_only
NetULFFiberScore_LOOCV
Y_HF_ref
DeltaHFScore_LOOCV
DeltaHFScore_z_LOOCV
HF_out_candidate_fraction_tau800_LOOCV
residual_ULF_model
residual_nuisance_only
```

Display and anatomical outputs：

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

对于连续型/统计型 NIfTI 输出，未覆盖或未建模的 voxel 写为 `NaN`，不是 `0`。这包括 density support 或 model candidate support 外的 weighted density、positive/negative weighted density、`-log(p)` density、FDR-thresholded density、stability density、jitter density、plain touched density 和 display-smoothed density maps。`0` 只表示 support 内真实的零贡献。如果输出 count/binary masks，它们由于语义是计数/false，在 support 外仍写为 `0`。

FDR q-values、q-thresholded maps、endpoint labels 和 display fibers 只用于 QC/display。它们不定义 `F+`、`F-`、`NetULFFiberScore` 或 primary model。

---

## 15. Execution Efficiency / 执行效率

效率规则沿用 HF normative fiber model，并且必须保持 exact equivalence。

### 15.1 Required sidecars

PPMI/MGH 可使用 single sidecars。dTOR 必须使用 chunked sidecars。

```text
X_ULF_component_float32_fiber_major.npy
X_HF_component_float32_fiber_major.npy
X_HFonly_ref_float32_fiber_major.npy
X_ULF_only_tau800_float32_fiber_major.npy
X_ULF_only_tau1500_float32_fiber_major.npy
S800_ULF_only_bool.npy
S1500_ULF_only_bool.npy
S800_HF_component_bool.npy
S1500_HF_component_bool.npy
S800_ULF_total_bool.npy
S1500_ULF_total_bool.npy
HF_overlap_tau800_bool.npy
HF_overlap_tau1500_bool.npy
fiber_id.npy
candidate_fiber_metadata.json
```

For dTOR：

```text
chunks/
  X_ULF_component_float32_fiber_major_chunk-*.npy
  X_HF_component_float32_fiber_major_chunk-*.npy
  X_HFonly_ref_float32_fiber_major_chunk-*.npy
  X_ULF_only_tau800_float32_fiber_major_chunk-*.npy
  X_ULF_only_tau1500_float32_fiber_major_chunk-*.npy
  S800_ULF_only_bool_chunk-*.npy
  S1500_ULF_only_bool_chunk-*.npy
  S800_HF_component_bool_chunk-*.npy
  S1500_HF_component_bool_chunk-*.npy
  HF_overlap_tau800_bool_chunk-*.npy
  HF_overlap_tau1500_bool_chunk-*.npy
  fiber_id_chunk-*.npy
fiber_chunk_manifest.json
candidate_fiber_metadata.json
```

一次性将全部 dTOR streamlines 或全部 dTOR exposure values 加载进内存是无效实现。

### 15.2 Outcome-independent caches

当 cache keys 匹配时，可跨 scales 和 endpoint families 复用：

```text
raw component exposure sidecars
HF-only reference exposure sidecars
ULF-only overlap-exclusion masks
Coverage_ULF_tau caches
candidate fiber metadata
endpoint label lookup
density lookup
HF support lookup for locked HF model
```

### 15.3 Outcome-dependent objects

必须在每个 training fold 内重算：

```text
DeltaHFScore
DeltaHFScore z-scoring parameters
nuisance residuals
rho_ULF
M_ULF
F+_ULF
F-_ULF
SweetPeak5_ULF
SourPeak5_ULF
NetULFFiberScore
final prediction model
```

### 15.4 Disallowed shortcuts

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
using total ULF exposure in place of ULF-only exposure for the primary model
using full-sample HF model to compute held-out DeltaHFScore
extrapolating HF weights to out-of-support fibers
```

任何 optimized implementation 在 formal execution 前，都必须在 small deterministic brute-force subset 上通过 exact-equivalence regression testing。

---

## 16. Execution Priority And Gatekeeping / 执行优先级与 Gatekeeping

模型按 gated sequence 执行。

Executable branches：

```text
primary:
  ulf_peak_efield_tau800_delta_hf_adjusted
  ulf_peak_efield_tau800_no_delta_hf

sensitivity:
  ulf_peak_efield_tau1500_sensitivity
  ulf_top1500_top500_sensitivity
  non-selected core branch comparison
  ulf_total_exposure_tau800_sensitivity
  ulf_gain_endpoint_sensitivity

control:
  ulf_plain_connected_streamline_control
  ulf_hf_out_support_burden_control
```

Connectome roles：

```text
PPMI 85                 observed figure-grade robustness
MGH-USC HCP 32          observed figure-grade robustness
dTOR-985 Full           primary formal analysis
```

### Round 0: Version, input, and manifest freeze

只运行检查：

```text
lock document version
lock endpoint list
lock timeline labels T0/T1/T2/T3
lock scale list
lock connectome list
lock branch list
lock tau800 / tau1500 / Coverage>=5
lock seed = 42
check HF and ULF e-field manifests
check HF-only reference e-field manifest
check component labels and proxy status
check clinical ID join
check same-day T2 immediate/HF reference pairing
check scale direction
check locked HF normative model source
check hf_prediction_validity_status
check HF support output availability
check PPMI / MGH / dTOR readability
check output root writability
```

只有当所有输入唯一解析，并且 manifest 记录 locked parameter set 后，才进入 Round 1。

### Round 1: Sidecar cache, HF support cache, and equivalence test

为以下内容构建 PPMI/MGH sidecars 和 dTOR chunked sidecars：

```text
HF component exposure
ULF component exposure
HF-only reference exposure
tau-specific ULF-only exposure
HF-overlap masks
HF support masks
out-of-support QC summaries
```

运行 deterministic small-subset equivalence testing，覆盖：

```text
candidate definition
HF support classification
DeltaHFScore
partial Spearman
selected fibers
NetULFFiberScore
LOOCV prediction
smoke permutation
bootstrap summaries
```

只有 optimized 和 brute-force outputs 在 tolerance 内匹配，且 dTOR chunked IO 没有 memory error，才进入 Round 2。

### Round 2: Core observed chronic endpoint

运行：

```text
endpoint = chronic 3-month HF+ULF add-on
scale = MDS-UPDRS III total
core branches =
  ulf_peak_efield_tau800_delta_hf_adjusted
  ulf_peak_efield_tau800_no_delta_hf
connectome order = PPMI observed -> MGH observed -> dTOR observed
```

进入 Round 3 的条件：

```text
dTOR observed LOOCV completes
fold-specific ULF candidates are non-empty
NetULFFiberScore has nonzero variance
the branch selected as primary has finite branch-specific nuisance inputs
HF_out_candidate_fraction gates are not extreme
validation metrics are finite
Q2 is interpretable against branch-specific nuisance-only baseline
ulf_primary_branch is recorded in the manifest
```

### Round 3: Same-day immediate endpoint

运行：

```text
endpoint = same-day HF+ULF immediate add-on
scale = MDS-UPDRS III total or motor domain as configured
core branches =
  ulf_peak_efield_tau800_delta_hf_adjusted
  ulf_peak_efield_tau800_no_delta_hf
connectome order = PPMI observed -> MGH observed -> dTOR observed
```

只有当 same-day endpoint join 正确、candidate masks 非空、`NetULFFiberScore` 非常数、`DeltaHFScore_immediate` 可计算且 LOOCV prediction 可拟合时，才进入 Round 4。

### Round 4: Plain controls and burden diagnostics

运行：

```text
ulf_plain_connected_streamline_control
ulf_hf_out_support_burden_control
```

只有当 `PlainULFOnlyExposureTop5` 可计算、joint QC models 非奇异，并且 `NetULFFiberScore` 不与 plain exposure 或 out-of-support burden metrics 完全共线时，才进入 Round 5。

### Round 5: dTOR primary smoke resampling

对通过 observed gates 的 dTOR primary branches 运行：

```text
Freedman-Lane smoke permutation B=1000
subject-level smoke bootstrap B=1000
seed = 42
```

只有当 smoke permutation/bootstrap 完成、plus-one p values 可计算、bootstrap finite counts 可解释，并且 runtime profile 表明 formal `B=10000` 可行时，才进入 Round 6。

### Round 6: Cheap observed sensitivity

运行 observed-only sensitivity：

```text
ulf_peak_efield_tau1500_sensitivity
ulf_top1500_top500_sensitivity
non-selected core branch comparison
ulf_total_exposure_tau800_sensitivity
ulf_gain_endpoint_sensitivity
PPMI -> MGH -> dTOR
```

除非明确提升，否则不为这些 branches 运行 formal permutation/bootstrap。

### Round 7: dTOR primary formal resampling

只运行：

```text
connectome = dTOR
branch = ulf_peak_efield_tau800_primary
endpoint = chronic 3-month HF+ULF add-on unless immediate endpoint is promoted
formal permutation B=10000
formal bootstrap B=10000
seed = 42
```

只有 formal resampling 完成，并且 manifests 记录以下内容后，才进入 Round 8：

```text
resampling_status = formal_complete
```

### Round 8: ULF jitter QC

只对已完成 formal primary results 的 dTOR branches 运行。

Jitter 会改变 HF 和 ULF component geometry，因此每次 jitter iteration 必须重建：

```text
HF component exposure
ULF component exposure
HF-only reference exposure if jitter is applied to reference phase
HF-overlap exclusion
ULF-only exposure
DeltaHFScore
ULF candidate masks
M_ULF
NetULFFiberScore
LOOCV prediction
```

如果 jitter 不稳定，将结果报告为 spatially fragile。

### Round 9: Display, FDR, labels, density, and cross-connectome summaries

只在 numeric branches 锁定后生成 display outputs。Display、FDR、labels、density 和 cross-connectome outputs 必须来自 finalized numeric outputs，并且不得改变 primary model。

---

## 17. Interpretation Boundary / 解释边界

应解释为：

```text
After accounting for the patient's same-day/pre-ULF HF clinical state and the matched HF normative fiber model's in-support predicted change in HF-component engagement, ULF-only engagement of this outcome-filtered normative streamline profile is associated with post-HF+ULF clinical outcome.
```

不应解释为：

```text
ULF causal tract has been validated.
HF contribution has been fully removed.
HF-overlap streamlines have no ULF biological role.
HF out-of-support exposure has no effect.
Every selected streamline is patient-specific.
The result proves an anatomical SNr gain mechanism.
```

由于 `n=16`，所有 ULF fiber-level 结果都是 hypothesis-generating。阴性或不稳定的 LOOCV 结果不应解释为 ULF 没有生物学效应；也可能反映样本量有限、endpoint 噪声、stimulation-field 不确定性、HF adjustment 不稳定、out-of-support HF-component exposure 或 connectome limitations。
