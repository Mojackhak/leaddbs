# HF-status-resolved ULF-only Add-On Gain 直接 Voxel-Level 模型

## Research Question / 研究问题

加入 ULF 刺激后，哪些超低频刺激 territory voxels 的 ULF-only exposure 与额外临床获益相关，并且这种关联已校正患者 same-day HF clinical state 和模型预测的 HF efficacy 变化？

这是 direct local ULF-only add-on sweet-spot model。主问题不是解剖 SNr 效应。STN/SNr 及 peri-STN/SNr 区域被视为一个 stimulation territory；HF 和 ULF components 通过 stimulation frequency 和 exposure overlap 区分。

频率定义固定为：

```text
HF  = high-frequency stimulation component, frequency_Hz >= 100
ULF = ultra-low-frequency stimulation component, frequency_Hz <= 50
```

同时被 HF 和 ULF 激活的 voxels 归入 HF adjustment model，并从 primary ULF-only predictor 中排除。这是建模选择，不是声称 ULF 在 HF-overlap territory 中不可能有生物学效应。

## Follow-Up Timeline / 随访时间线

模型假定以下 visit sequence：

```text
T0 = preoperative baseline assessment

T1 = postoperative 1-month HF immediate activation / opening assessment

T2 = HF-only 3-month follow-up
     same day, before adding ULF:
       raw HF-only 3-month clinical state is measured
     same day, after switching to HF+ULF:
       raw HF+ULF immediate clinical state is measured

T3 = HF+ULF 3-month follow-up
     approximately 3 months after T2:
       raw HF+ULF chronic 3-month clinical state is measured
```

因此，immediate HF+ULF endpoint 与 HF-only 3-month clinical reference state 是同一天测量。Immediate endpoint 相对于 HF-only 3-month reference 不受不同 visit day 的混杂。Chronic endpoint 是 add-on 后随访 endpoint，以 T2 HF-only 3-month state 作为 pre-ULF clinical reference。

## Endpoint Definitions / 终点定义

两个 endpoint families 分开建模。

### Primary Chronic Post-Add-On Endpoint

```text
Y_post_chronic = raw HF+ULF 3-month clinical score at T3
Y_HF_ref       = raw HF-only 3-month clinical score at T2, same scale/domain
DeltaHFScore_chronic = predicted change in HF efficacy between
                       HF+ULF chronic programming and HF-only T2 programming
```

Primary chronic estimand：

```text
HF-state-adjusted ULF-only chronic add-on association
```

该 endpoint 估计：在校正患者 T2 HF 临床状态和模型预测的 HF-component efficacy change 后，ULF-only exposure 是否解释 T3 HF+ULF outcome。

### Key Same-Day Immediate Endpoint

```text
Y_post_immediate = raw HF+ULF immediate clinical score at T2, after switching to HF+ULF
Y_HF_ref         = raw HF-only 3-month clinical score at T2, before switching to HF+ULF
DeltaHFScore_immediate = predicted change in HF efficacy between
                         immediate HF+ULF programming and HF-only T2 programming
```

Immediate estimand：

```text
same-day HF-state-adjusted ULF-only acute add-on association
```

因为 `Y_post_immediate` 和 `Y_HF_ref` 在同一天测量，该 endpoint 是有效的 same-day add-on response endpoint。它仍然与 chronic endpoint 分开建模。默认可作为 key secondary endpoint；只有在 formal resampling 前显式声明时，才可提升为 co-primary。

### Direction-Normalized Gain Sensitivity Endpoints

主模型使用 raw post-HF+ULF scores 并进行 HF-state adjustment。Direction-normalized gain endpoints 保留为 sensitivity analyses。

低分更好量表：

```text
Gain_immediate = Y_HF_ref - Y_post_immediate
Gain_chronic   = Y_HF_ref - Y_post_chronic
```

高分更好量表：

```text
Gain_immediate = Y_post_immediate - Y_HF_ref
Gain_chronic   = Y_post_chronic - Y_HF_ref
```

正 gain 始终表示加入 ULF 后改善。Immediate gain endpoint 是最直接的 same-day add-on effect estimate。Chronic gain endpoint 混合了 add-on response、time-on-stimulation、adaptation、medication/assessment variability 和 disease-course effects。

默认 first-pass endpoints：

```text
1. MDS-UPDRS III total chronic HF+ULF 3-month score at T3
2. MDS-UPDRS III total same-day immediate HF+ULF score at T2, if available
```

Raw scores 来自 HF direct voxel model 使用的原始临床表：

```text
/Users/mojackhu/Research/STNSNr/summary/cohort/subj/subject_effect_origin.xlsx
```

Clinical rows 通过 `ID`（`SNr003`、`SNr006` 等）与 imaging 数据连接。Improvement-rate tables 不用于 primary raw-score model。Scale direction 读取与 HF direct voxel model 相同的 internal direction table；未知量表必须在运行前显式指定 higher-is-better 或 lower-is-better。

## Inputs / 输入

- Stimulation parameter audit source：

  ```text
  /Users/mojackhu/Research/STNSNr/summary/cohort/subj/followup_stimulation.xlsx
  sheet = Contact Parameters
  ```

  该 workbook 用于审计 HF 和 ULF component identity、frequencies、pulse widths、amplitudes、sides、contacts 和 phase labels。Existing e-fields 在既往 manual/clinical QC 后视为 accepted inputs。当前 ULF direct voxel analysis 不自动创建 missing e-fields。

- T2 HF-only 3-month phase 的 HF-only reference E-field per side，用于计算 reference HF score。

- Same-day T2 immediate HF+ULF programming 中的 HF component E-field 和 ULF component E-field per side，用于 immediate endpoint。

- T3 chronic HF+ULF programming 中的 HF component E-field 和 ULF component E-field per side，用于 chronic endpoint。如果 T3 stimulation settings 与 T2 immediate HF+ULF programming 不变，manifest 必须明确记录复用了同一组 component e-fields。

- 与模型类型匹配的 direct voxel-level HF efficacy map：

  ```text
  DeltaHFScore source = HF direct voxel model
  ```

  ULF direct voxel model 不得使用 normative fiber HF score 作为 HF adjustment。Voxel-level ULF models 必须用 voxel-level HF models 调整。

- Canonical reference mask：

  ```text
  templates/space/MNI152NLin2009bAsym/brainmask.nii.gz > 0
  right hemisphere voxel centers, MNI x > 0
  ```

- STN/SNr and STNSNrplus masks are overlay/QC context only：

  ```text
  Custom_Ewert_Zhang_Middlebrooks0.05
  STN-connected regions
  SNr-connected regions
  STNSNr-connected regions
  ```

  `STNSNrplus` 仅用于 anatomical overlay、territory coverage 和 QC background。它不与 `Omega_ULF_tau` 相交，也不是 statistical candidate mask。

- Python postprocessing environment：

  ```text
  conda environment = leaddbs
  package changes allowed if recorded in generation manifest
  ```

## Locked HF Prerequisite / 锁定 HF 前置条件

ULF direct voxel analysis 依赖已锁定的 HF direct voxel model。正式运行 ULF 前必须固定：

```text
hf_model_family = direct_voxel
hf_estimator = partial_spearman
hf_tau = 200 V/m
hf_score = HFScore_mean_main
hf_map = direct_voxel_HF_sweet_sour.nii.gz
hf_support = V_HF_score
hf_generation_manifest
hf_mapping_qc
```

HF map 必须 endpoint/domain-matched。Chronic ULF endpoint 使用 3-month HF model；immediate motor endpoint 使用 motor-domain HF model。Held-out ULF predictions 必须使用 training-fold HF map 计算 `DeltaHFScore`，不得用 full-sample HF map 给 held-out patient 打分。

ULF direct voxel 实现层面不在运行前固定唯一主分支。只要输入可用，DeltaHF-adjusted 和 no-DeltaHF 两个核心分支以同等地位运行；随后根据已锁定 HF 结果在文档和 manifest 中记录哪个分支是解释上的 primary branch：

```text
if HF model is predictive_valid:
  ulf_primary_branch = delta_hf_adjusted
  delta_hfscore_role = primary nuisance adjustment
  no_delta_hf_role   = sensitivity

if HF model is stable_nonpredictive:
  ulf_primary_branch = no_delta_hf
  delta_hfscore_role = sensitivity / compatibility adjustment
  no_delta_hf_role   = primary

if HF model is failed_unstable:
  ulf_primary_branch = no_delta_hf when ULF inputs remain valid
  delta_hfscore_role = exploratory only, or not run if HF support is unavailable
  no_delta_hf_role   = primary exploratory branch
```

Branch-role decision 必须写入 manifest：

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

如果 locked HF branch 未通过 QC、`HFScore_mean_main` 近似常数、fold scoring mask 为空，或无法提供可解释的 HF map support，则 `DeltaHFScore` 必须标记为不稳定 generated covariate，不能定义 ULF 的 primary interpretation。

Post-hoc HF threshold candidates 遵循 `hf_3m_direct_voxel_model.md` 中定义的 level system。Level 0 和 Level 1 candidates 不得传播进入 ULF。Level 2 和 Level 3 candidates 只能生成独立的 exploratory `DeltaHFScore` sensitivity branches。Level 4 candidates，或原始 `tau200/Coverage>=5` primary HF branch 在 `predictive_valid` 时，才可以定义 primary DeltaHF-adjusted ULF interpretation。每个 endpoint 最多只能有一个 selected post-hoc candidate 生成 ULF branch；neighboring support cells 是 robustness evidence，不是单独 covariates。

## Feature Construction / 特征构建

使用 right-hemisphere MNI brainmask grid 作为 canonical statistical grid。左侧 HF 和 ULF component fields 使用 `ea_flip_lr_nonlinear` 翻转到右侧空间。右侧 fields 采样到同一 right canonical grid。

对每个 patient `i` 和 voxel `v`：

```text
E_HF_R_i(v)       = right HF component e-field
E_HF_L_to_R_i(v)  = left HF component e-field flipped to right canonical space
E_ULF_R_i(v)      = right ULF component e-field
E_ULF_L_to_R_i(v) = left ULF component e-field flipped to right canonical space
```

如果同侧存在多个 subprogram：

```text
E_HF_side_i(v)  = voxel-wise maximum over same-side HF subprograms
E_ULF_side_i(v) = voxel-wise maximum over same-side ULF subprograms
```

Interleaving 不建模为 simultaneous double-cathode stimulation。如果某个 clinical condition 包含 synchronous mixed HF+ULF programming，并通过只开启分配给某个 frequency component 的 contacts 生成 component-specific fields，manifest 必须将这些 fields 标记为 component-specific proxies。

Bilateral component exposure：

```text
E_HF_component_i(v) =
  (E_HF_R_i(v) + E_HF_L_to_R_i(v)) / 2

E_ULF_component_i(v) =
  (E_ULF_R_i(v) + E_ULF_L_to_R_i(v)) / 2
```

Frequency 只用于将 component 分类为 HF 或 ULF。主 direct voxel analysis 中 exposure 不按 frequency 或 pulse width 缩放。

### ULF Candidate Space

```text
candidate grid = right hemisphere MNI brainmask voxels
Candidate_ULF(v) = any valid subject has E_ULF_component_i(v) > 180 V/m

tau_primary = 200 V/m
tau_sensitivity = 180 / 220 V/m
Coverage threshold = >= 5 subjects
```

对每个 `tau`：

```text
HF_active_i(v)  = E_HF_component_i(v)  > tau
ULF_active_i(v) = E_ULF_component_i(v) > tau

X_ULF_only_i(v) =
  E_ULF_component_i(v), if ULF_active_i(v) and not HF_active_i(v)
  0,                   otherwise

Coverage_ULF_tau(v) = sum_i I[X_ULF_only_i(v) > tau]
Omega_ULF_tau = {v in Candidate_ULF : Coverage_ULF_tau(v) >= 5}
```

`Omega_ULF_tau` 内使用 continuous `X_ULF_only_i(v)` 建模；`tau` 只用于定义 component activity、HF-overlap exclusion、coverage 和 QC。同时被 HF 和 ULF 激活的 voxels 从 ULF predictor 中排除，并在输出中显式记录。

### HF-Overlap Exclusion Outputs

必须输出：

```text
direct_voxel_ULF_only_HF_overlap_exclusion_mask.nii.gz
direct_voxel_ULF_only_HF_overlap_exclusion_summary.csv
```

`HF_overlap_exclusion_mask` 是 threshold-specific group-level summary，表示至少一个 subject 中被 HF 和 ULF 同时激活而从 ULF-only predictor 排除的 voxels。Subject-level overlap counts 和 volumes 写入 summary CSV 和 mapping QC JSON。

Coverage masks、voxel maps、ULF scores、`DeltaHFScore` 和 validation predictions 都在每个 LOOCV training fold 内计算。Held-out patient 不参与该 fold 的 `Omega_ULF_tau`、ULF voxel map 或 HF adjustment map。

## DeltaHFScore

模型匹配的 HF adjustment 来自 HF direct voxel model：

```text
V_HF_score = Omega_HF_tau intersect valid M_HF voxels
n_valid_HF_score_voxels = |V_HF_score|

S_HF_voxel(E)_i =
  sum_{u in V_HF_score} E_i(u) * M_HF(u)
  / n_valid_HF_score_voxels

DeltaHFScore_chronic_i =
  S_HF_voxel(E_HF_component, HF+ULF chronic)_i
  - S_HF_voxel(E_HF_only, HF-only T2)_i

DeltaHFScore_immediate_i =
  S_HF_voxel(E_HF_component, HF+ULF immediate)_i
  - S_HF_voxel(E_HF_only, HF-only T2)_i
```

`DeltaHFScore` 在建模前不赋予固定生物学缩放系数。它可在 training folds 内 z-score 以改善数值稳定性；其 regression coefficient 估计它与 outcome 的关联。在 LOOCV 中，held-out patient 的 `DeltaHFScore` 必须由 training-fold HF map 计算，不能使用 full-sample HF map。

### HF-Map Support And Out-Of-Support HF Exposure

因为 HF+ULF programming 中的 HF component 可能落在 HF-only model learned support 之外，必须审计 `DeltaHFScore` 是否充分覆盖 HF component reprogramming。

对每个 patient 和 endpoint：

```text
HF_component_total_exposure =
  sum_v E_HF_component_i(v)

HF_component_in_support_exposure =
  sum_{v in V_HF_score} E_HF_component_i(v)

HF_component_out_support_exposure =
  HF_component_total_exposure - HF_component_in_support_exposure

HF_out_support_fraction =
  HF_component_out_support_exposure / HF_component_total_exposure
```

也为 HF-only reference field 计算同样指标。QC 必须报告：

```text
HF_out_support_fraction_mean
HF_out_support_fraction_median
HF_out_support_fraction_max
subject-level HF_out_support_fraction
corr(DeltaHFScore, HF_out_support_fraction)
corr(ULFScore_mean_main, HF_out_support_fraction)
```

如果 `HF_out_support_fraction` 很高，不能把 `DeltaHFScore` 解释为完全控制 HF contribution。此时主分析仍可运行，但 interpretation boundary 必须降级；可运行预先声明的 sensitivity：

```text
Y_post_i = alpha
         + delta * ULFScore_mean_main_i
         + beta  * Y_HF_ref_i
         + gamma * DeltaHFScore_i
         + eta   * HF_out_support_fraction_i
         + error_i
```

该 sensitivity 只用于 QC 和解释边界，不替代 primary model。

## Statistical Model / 统计模型

### Core Branch A: DeltaHF-Adjusted Partial Spearman

对每个 endpoint 和 voxel `v`，使用 rank-residual partial Spearman，并对 ties 使用 average ranks：

```text
rho_ULF(v) =
  corr(
    resid(rank(Y_post_i)          ~ rank(Y_HF_ref_i) + rank(DeltaHFScore_i)),
    resid(rank(X_ULF_only_i(v))   ~ rank(Y_HF_ref_i) + rank(DeltaHFScore_i))
  )
```

如果 voxel 的 ULF-only exposure variance、rank variance 或 residualized exposure variance 为 0，则设为 `rho_ULF(v)=NaN`，并从 `ULFScore_mean_main` 中排除。

Benefit-oriented map：

```text
M_ULF(v) = -rho_ULF(v)   for lower-is-better scales
M_ULF(v) =  rho_ULF(v)   for higher-is-better scales
```

正值 `M_ULF(v)` 一律表示 ULF-only sweet 或 benefit-associated。负值 `M_ULF(v)` 表示 ULF-only sour 或 worse-outcome-associated。

### Core Branch B: No-DeltaHF Partial Spearman

No-DeltaHF estimator 移除 `DeltaHFScore`，但保留当前 HF clinical state：

```text
rho_ULF_noDeltaHF(v) =
  corr(
    resid(rank(Y_post_i)        ~ rank(Y_HF_ref_i)),
    resid(rank(X_ULF_only_i(v)) ~ rank(Y_HF_ref_i))
  )
```

该 branch 不天然是次要分支。当匹配的 HF model 稳定但预测力不足以支持把 `DeltaHFScore` 作为主 nuisance adjustment 时，它就是解释上的 primary branch。否则，它用于报告 ULF map 对 model-derived HF adjustment 的依赖程度。

### Gain Endpoint Sensitivity Estimator

Gain endpoint sensitivity 使用 direction-normalized gain 作为 outcome：

```text
rho_ULF_gain(v) =
  corr(
    resid(rank(Gain_i)          ~ rank(DeltaHFScore_i)),
    resid(rank(X_ULF_only_i(v)) ~ rank(DeltaHFScore_i))
  )
```

该分支回答“加入 ULF 后相对同日 HF state 的改善量”是否与 ULF-only exposure 相关。它是 sensitivity，不替代 raw post-score primary model。

### Total ULF Exposure Sensitivity

主模型排除 HF-overlap voxels。Total ULF exposure sensitivity 不排除 HF-overlap：

```text
X_ULF_total_i(v) = E_ULF_component_i(v)
```

该分支用于评估 HF-overlap exclusion rule 对结果的影响。它不是 primary branch。

### Optional Supplemental Estimator: OLS ANCOVA

可选补充估计器，本次不执行：

```text
Y_post_i = alpha_v
         + theta_ULF(v) * X_ULF_only_i(v)
         + beta_v      * Y_HF_ref_i
         + gamma_v     * DeltaHFScore_i
         + error_i,v
```

如果未来启用，OLS estimator 应在 `ols_ancova/` estimator directory 下生成同一 output family。其 `direct_voxel_ULF_only_coef.nii.gz` 存储 `theta_ULF(v)`，而主 `partial_spearman/` coefficient file 存储 `rho_ULF(v)`。

### Patient-Level Score

主患者级 ULF-only sweet-spot score：

```text
V_score = Omega_ULF_tau intersect valid M_ULF voxels
n_valid_score_voxels = |V_score|

ULFScore_mean_main_i =
  sum_{v in V_score} X_ULF_only_i(v) * M_ULF(v)
  / n_valid_score_voxels
```

这是主 ULF-only prediction score。它是在对应 full-sample map 或 LOOCV training fold 的固定 scoring voxel set 上，按 voxel 数归一化的 voxel 相关性加权平均 ULF-only exposure。它不除以 `sum(X)`，也不乘 voxel volume。若 `V_score` 为空，则该 branch/fold 以 QC failure 停止，不生成 score。若某 subject/fold 在非空有效 scoring voxel set 内没有 ULF-only exposure，则 `ULFScore_mean_main_i` 记为 `0`。

DeltaHF-adjusted prediction model：

```text
Y_post_i = alpha
         + delta * ULFScore_mean_main_i
         + beta  * Y_HF_ref_i
         + gamma * DeltaHFScore_i
         + error_i
```

DeltaHF-adjusted covariate-only baseline：

```text
Y_post_i = alpha
         + beta  * Y_HF_ref_i
         + gamma * DeltaHFScore_i
         + error_i
```

No-DeltaHF prediction model：

```text
Y_post_i = alpha
         + delta * ULFScore_mean_main_i
         + beta  * Y_HF_ref_i
         + error_i
```

No-DeltaHF covariate-only baseline：

```text
Y_post_i = alpha
         + beta * Y_HF_ref_i
         + error_i
```

两个核心 branch 的 prediction model 均在 raw post-score 尺度上拟合。主验证统计量仍为 rank-based LOOCV Spearman rho。Branch-role resolver 决定哪个分支的 LOOCV statistic 被报告为 primary statistic。

Missing-data rule：missing `Y_post`、missing `Y_HF_ref` 或 e-field availability failure 会在 QC 后使 endpoint/run 失败。Missing 或 invalid `DeltaHFScore` 只使 DeltaHF-adjusted branch 失败；no-DeltaHF branch 仍可运行，并必须记录 adjusted branch 不可用的原因。未来 configurable endpoints 若有效样本量低于 12，则跳过该 endpoint。

## Validation / 验证

- Chronic 和 immediate endpoints 分开建模。
- 主 validation 使用 fully nested LOOCV。
- 每个 outer fold 内，重建 branch-specific nuisance inputs，重建 `Omega_ULF_tau`、拟合 ULF-only voxel map、计算 training 和 held-out `ULFScore_mean_main`，并且只用 training patients 拟合 final prediction model。
- 对 DeltaHF-adjusted branch，重建计算 `DeltaHFScore` 所需的 HF direct voxel map，计算 fold-specific `DeltaHFScore` 和 HF out-of-support burden，并与 `Y_post ~ Y_HF_ref + DeltaHFScore` 比较。
- 对 no-DeltaHF branch，在 map estimation、scoring、prediction、permutation nuisance model 和 baseline comparison 中均不纳入 `DeltaHFScore`；与 `Y_post ~ Y_HF_ref` 比较。
- 只要输入允许，observed LOOCV 阶段同时运行两个核心 branch。HF 结果分类后，由 branch-role resolver 记录哪一个被解释为 primary。
- 主验证统计量：held-out predictions 与 held-out raw outcomes 的 LOOCV Spearman rho。
- Secondary metrics：LOOCV Pearson `r`、MAE、RMSE 和 original raw outcome scale 上的 `Q2`。

```text
Q2 = 1 - SSE_ULFScore_model / SSE_covariate_only
```

- Patient-level Freedman-Lane permutation 对 branch-role resolver 记录为 primary 的分支使用 `B=10000` 和随机种子 `42`。Smoke/exploratory 运行使用 `B=1000`。Formal permutation 只对 selected primary `tau200/partial_spearman` chronic endpoint branch 运行，除非 immediate endpoint 被明确提升为 co-primary。
- 每次 permutation 使用 branch-specific nuisance model，置换 nuisance residuals，重构 `Y*`，然后完整重跑 LOOCV pipeline，包括 branch-specific nuisance inputs、ULF coverage、ULF map、`ULFScore_mean_main` 和 prediction。主 permutation statistic 为 LOOCV Spearman rho。
- p value 使用 plus-one two-sided：

```text
p = (1 + count(|stat_perm| >= |stat_obs|)) / (B + 1)
```

- Subject-level bootstrap 对 branch-role resolver 记录为 primary 的分支使用 `B=10000` 和 seed `42`。Smoke/exploratory 运行使用 `B=1000`。每次 bootstrap resample 都重跑完整 branch-specific map-building process；只有 DeltaHF-adjusted branch 需要重建 `DeltaHFScore` 和 HF support QC；所有 branch 都重建 `Omega_ULF_tau`。`direct_voxel_ULF_only_bootstrap_se.nii.gz` 存储 estimator map 的 voxel-wise standard deviation。

对非主已执行分支（`tau180/partial_spearman`、`tau220/partial_spearman`、未被选为 primary 的核心 branch、gain endpoint sensitivity、total ULF exposure sensitivity，以及未设为 co-primary 的 immediate endpoints），仍运行 LOOCV，但不生成 formal permutation/bootstrap outputs。对应 manifests 和 QC JSON 必须记录：

```text
resampling_status = not_run_nonprimary
resampling_reason = formal resampling restricted to primary tau200/partial_spearman branch
```

## Execution Structure / 执行结构

MATLAB preprocessing 负责：

- discover and availability-check required HF-only, HF-component, and ULF-component e-fields；
- 按 frequency 分类 components（`HF >= 100 Hz`，`ULF <= 50 Hz`）；
- 同侧 alternating subprograms 用 voxel-wise maximum 合并；
- 用 `ea_flip_lr_nonlinear` 执行 left-to-right flip；
- 将 HF 和 ULF component exposure 采样到 right-hemisphere MNI brainmask candidate grid；
- 写出 MAT v7 ROI design matrix 和 optional memmap sidecars。

Preprocessing output schema 至少包括：

- `X_ULF_only(subject x candidate_voxel)` continuous ULF-only exposure；
- `E_HF_component(subject x candidate_voxel)` continuous HF component exposure，用于 overlap exclusion 和 `DeltaHFScore`；
- `E_ULF_component(subject x candidate_voxel)` total ULF component exposure，用于 sensitivity；
- subject IDs、phase/endpoint labels、side/source e-field paths；
- raw clinical values `Y_HF_ref`、`Y_post_chronic`、`Y_post_immediate`；
- tau/candidate metadata、HF-overlap exclusion metadata、HF support metadata、flip metadata 和 jitter metadata placeholders。

Python postprocessing 负责：

- fit partial Spearman ULF maps；
- compute fold-specific `DeltaHFScore`；
- build LOOCV scores and predictions；
- run permutation/bootstrap/jitter；
- write CSV/JSON/NIfTI outputs and figures；
- record Conda `leaddbs` environment state。

Output root：

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/<tau_slug>/<branch_slug>/
```

Core branches：

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau200/partial_spearman_delta_hf_adjusted/
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau200/partial_spearman_no_delta_hf/
```

Sensitivity branches：

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau180/partial_spearman_delta_hf_adjusted/
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau180/partial_spearman_no_delta_hf/
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau220/partial_spearman_delta_hf_adjusted/
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau220/partial_spearman_no_delta_hf/
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau200/partial_spearman_gain_endpoint/
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau200/partial_spearman_total_ulf_exposure/
```

`<endpoint_slug>` examples：

```text
chronic_3m
same_day_immediate
gain_chronic
gain_immediate
```

All stochastic operations use seed `42` with deterministic derived sub-seeds recorded in manifest.

## Downstream Visualization And Outputs / 下游可视化和输出

Each executed `tau/estimator/endpoint/scale` directory writes:

```text
direct_voxel_ULF_only_coverage.nii.gz
direct_voxel_ULF_only_coef.nii.gz
direct_voxel_ULF_only_sweet_sour.nii.gz
direct_voxel_ULF_only_stability.nii.gz
direct_voxel_ULF_only_bootstrap_se.nii.gz
direct_voxel_ULF_only_scores.csv
direct_voxel_ULF_only_loocv_predictions.csv
direct_voxel_ULF_only_permutation_summary.csv
direct_voxel_ULF_only_HF_overlap_coverage.nii.gz
direct_voxel_ULF_only_HF_overlap_fraction.nii.gz
direct_voxel_ULF_only_HF_overlap_subject_summary.csv
direct_voxel_ULF_only_HF_overlap_exclusion_mask_display.nii.gz
direct_voxel_ULF_only_delta_hf_support_summary.csv
direct_voxel_ULF_only_delta_hf_support_qc.json
direct_voxel_ULF_only_mapping_qc.json
direct_voxel_ULF_only_generation_manifest.json
```

`direct_voxel_ULF_only_bootstrap_se.nii.gz` 和 `direct_voxel_ULF_only_permutation_summary.csv` 只在 branch-role resolver 选中的 primary branch 中生成。非 primary branch 不写占位文件，而是在 manifest 和 QC JSON 中记录 `not_run_nonprimary`。

对于连续型/统计型 NIfTI 输出，model support 外的 voxel 写为 `NaN`，不是 `0`。这包括 `Omega_ULF_tau` 或 right-canonical candidate grid 外的 coefficient、sweet/sour、stability、bootstrap SE、HF-overlap fraction、smoothed-display 和 homologous-display statistical maps。`0` 只表示 support 内真实的零效应或零数值。整数型 coverage/count maps 和 binary/exclusion display masks 由于语义和数据类型是计数/false，在 support 外仍写为 `0`。

Output semantics：

- `direct_voxel_ULF_only_coverage.nii.gz` stores `Coverage_ULF_tau(v)=sum_i I[X_ULF_only_i(v, phase,tau)>tau]`. Use `int16`.
- `direct_voxel_ULF_only_coef.nii.gz` stores `rho_ULF(v)` for the executed `partial_spearman/` estimator. Optional future OLS outputs would store `theta_ULF(v)`.
- `direct_voxel_ULF_only_sweet_sour.nii.gz` stores benefit-oriented `M_ULF(v)`. Positive values indicate ULF-only benefit-associated voxels.
- `direct_voxel_ULF_only_stability.nii.gz` stores LOOCV training-fold direction stability of `M_ULF(v)>0` or `M_ULF(v)<0`, depending on display class. It is not a p value.
- `direct_voxel_ULF_only_bootstrap_se.nii.gz` stores full-process bootstrap standard deviation of the estimator map for the primary branch only.
- `direct_voxel_ULF_only_scores.csv` stores patient-level scores, including `branch`, `branch_role`, `delta_hfscore_role`, `ULFScore_mean_main`, `DeltaHFScore` when applicable, `Y_HF_ref`, `HF_out_support_fraction`, `score_map_source`, `n_valid_score_voxels`, and `is_primary_score`.
- `direct_voxel_ULF_only_loocv_predictions.csv` stores held-out predictions, observed raw outcome, branch-specific nuisance-only prediction, `ULFScore_mean_main`, `DeltaHFScore` when applicable, HF support burden fields, and residuals.
- `direct_voxel_ULF_only_permutation_summary.csv` stores Freedman-Lane permutation summary for the primary branch only.
- HF-overlap files store subject-level and cohort-level voxels excluded from the ULF-only predictor because both HF and ULF are active at the branch tau.
- DeltaHFScore support files store the in-support and out-of-support HF component exposure used to determine whether `DeltaHFScore` is within the learned HF model support.
- `direct_voxel_ULF_only_mapping_qc.json` stores endpoint/tau/estimator QC, including patient inclusion, candidate mask size, coverage distribution, `Omega_ULF_tau` voxel count, HF-overlap exclusion volume, HF out-of-support burden, degenerate voxels, NaN handling, zero-exposure score counts, `corr(ULFScore_mean_main, Y_HF_ref)`, `corr(ULFScore_mean_main, DeltaHFScore)`, `corr(Y_HF_ref, DeltaHFScore)`, coefficient signs, VIF or equivalent collinearity diagnostics, flip deformation audit metrics, and design-matrix dimensions.
- `direct_voxel_ULF_only_generation_manifest.json` stores provenance, parameters, code version, conda environment, package state, random seeds, visit labels, same-day immediate reference confirmation, component-proxy labels, and runtime profile.

Display outputs：

```text
display_smooth_fwhm1mm/
display_smooth_fwhm2mm/
bilateral_homologous_display/
qc_figures/
```

Main statistical maps are right-canonical and unsmoothed. Smoothing and bilateral homologous maps are display only and must not enter scoring, LOOCV, permutation, bootstrap, or jitter.

Report-only display masks：

```text
sweet_display_mask:
  M_ULF(v) > 0
  positive M_ULF(v) within top 10% among positive voxels in Omega_ULF_tau
  positive-direction stability >= 0.75

sour_display_mask:
  M_ULF(v) < 0
  absolute negative M_ULF(v) within top 10% among negative voxels in Omega_ULF_tau
  negative-direction stability >= 0.75
```

Display masks are not significance maps and do not define inference.

QC figures are PDF only：

```text
coverage histogram
HF-overlap exclusion summary
HF out-of-support summary
score-vs-outcome scatter
LOOCV observed-vs-predicted
DeltaHFScore-vs-outcome scatter
permutation null
bootstrap/jitter stability summary
```

## Left/Right Flip Deformation Audit / 左右翻转 Deformation Audit

`ea_flip_lr_nonlinear` 是唯一左右翻转方法。每个 subject-side component field 的 flip QC 记录：

```text
input/output grid and affine
finite voxel count
nonzero voxel count
max, p95, p99, sum
suprathreshold volume at 180/200/220 V/m
intensity-weighted centroid
L-to-R output overlap with right canonical brainmask
component label, phase label, and side metadata
```

Empty images、all-NaN images、non-finite values、missing paths 和 obvious path/component mismatches 是 hard failures。普通 deformation differences 记录为 warnings。

## Spatial Jitter QC Sensitivity

Spatial jitter 是对 accepted e-field inputs 的 robustness stress test。它不是 automatic localization/normalization QC，也不是 input-validity gate。除非某 endpoint 被显式提升为 co-primary，否则只对 selected primary ULF branch 运行。

```text
formal jitter resamples: B = 1000
smoke jitter resamples:  B = 100
seed: 42
FWHM: 2 mm
sigma: 2 / 2.355 = 0.849 mm
```

每次 jitter iteration，为每个 subject-side HF 和 ULF component e-field 独立抽取 3D translation vector。使用 linear interpolation 和 outside fill value `0` 执行 translation-only e-field resampling。随后重建 ULF-only exposure、HF-overlap exclusion、`Omega_ULF_tau`、`DeltaHFScore`、HF out-of-support support QC、full-sample map、ULF scores 和 LOOCV validation metrics。

不保存每次 jittered NIfTI map。保存 summary table、map correlation/stability summary 和 voxel-wise jitter standard deviation map。

## Reference-Parameter Coverage

ULF direct voxel model 在适用处覆盖与 HF direct voxel model 相同的 direct voxel parameter family：

```text
raw sim-efield, not sim-efieldgauss
right canonical voxel grid
ea_flip_lr_nonlinear left/right flip
tau = 180 / 200 / 220 V/m
Coverage>=5
covariate-adjusted partial Spearman
LOOCV
Freedman-Lane permutation for the primary branch
subject-level bootstrap for the primary branch
2 mm FWHM spatial jitter QC
display smoothing FWHM 1 mm and 2 mm, display only
```

当前 ULF direct voxel execution 中仅文档化、不生成结果的项目：

```text
Coverage>=6 optional sensitivity: documented only; no current ULF direct voxel outputs
Coverage>=8 / 50% E-field rule: documented only; primary rule remains Coverage>=5
5/7/10-fold CV: documented only; LOOCV is executable
optional OLS supplemental estimator: documented only; not run in the current execution
OSS-DBS: not part of direct voxel; belongs to normative fiber / activation sensitivity
paper-like spatial similarity score sensitivity: not included; ULFScore_mean_main is the primary score
automatic localization / electrode reconstruction QC: not included; prior manual QC is assumed
```

## Interpretation Boundary / 解释边界

该模型估计 HF-state-adjusted ULF-only add-on association。它不是解剖 SNr gain 模型。主分析中，同时被 HF 和 ULF 激活的 voxels 被视为 HF-dominant，因此 ULF map 表示在校正 HF clinical state 和 model-predicted HF efficacy changes 后，由 ULF 唯一招募的区域。

因为 immediate HF+ULF endpoint 和 HF-only 3-month clinical reference 在同一天测量，immediate model 可解释为 same-day acute add-on association。Chronic model 仍是 post-add-on follow-up association。

由于 cohort 为 `n=16`，结果是 hypothesis-generating。非显著 LOOCV 结果不应解释为不存在 ULF add-on sweet spot。QC report 必须包括 `ULFScore_mean_main`、`Y_HF_ref` 和 `DeltaHFScore` 之间的关联，`DeltaHFScore` 的 support coverage，以及 final prediction model 的基本 collinearity diagnostic。

应解释为：

```text
After accounting for same-day or pre-ULF HF state and modeled HF efficacy changes,
additional ULF-only exposure in this territory is associated with better or worse
post-HF+ULF outcome.
```

不应解释为：

```text
The displayed voxels prove an anatomic SNr-specific causal effect.
HF-overlap voxels have no ULF biological effect.
HF-component exposure outside the learned HF map has no biological effect.
DeltaHFScore fully removes all HF contribution when out-of-support burden is large.
```

## Execution Efficiency

优化实现必须保持上述 full-process semantics。特别是，LOOCV training folds 仍然必须定义自己的 HF adjustment map、`DeltaHFScore`、HF support QC、`Omega_ULF_tau`、ULF voxel map、ULF scores 和 held-out predictions。Formal Freedman-Lane permutation 和 subject-level bootstrap 对 primary branch 仍使用 `B=10000` 和 seed `42`。Smoke runs 对 permutation/bootstrap 使用 `B=1000`，对 jitter 使用 `B=100`。

### Equivalence Contract

Optimization 可复用数学不变的 cached subcomputations，但不得为提速而使用 full-sample ranks、full-sample training masks、approximate ranks、adaptive early stopping、changed tau thresholds、changed estimators、changed HF support rules 或 reduced formal resampling counts。

Numerical reductions 应尽可能使用 `float64`。最终 NIfTI 输出中，coefficient、sweet/sour、stability 和 bootstrap SE maps 使用 `float32`，coverage 和 binary/exclusion masks 使用 `int16`。

### Preprocessing Sidecar Cache

Preferred formal-loop input：

```text
E_ULF_component_<phase>_float32_voxel_major.npy
E_HF_component_<phase>_on_ulf_grid_float32_voxel_major.npy
E_HF_component_<phase>_on_hf_score_grid_float32_voxel_major.npy
E_HF_only_reference_on_hf_score_grid_float32_voxel_major.npy
X_ULF_only_tau180_<phase>_float32_voxel_major.npy
X_ULF_only_tau200_<phase>_float32_voxel_major.npy
X_ULF_only_tau220_<phase>_float32_voxel_major.npy
S180_ULF_only_<phase>_bool.npy
S200_ULF_only_<phase>_bool.npy
S220_ULF_only_<phase>_bool.npy
HF_overlap_tau180_<phase>_bool.npy
HF_overlap_tau200_<phase>_bool.npy
HF_overlap_tau220_<phase>_bool.npy
candidate_voxel_ijk.npy
candidate_voxel_mni.npy
preprocess_sidecar_metadata.json
```

MAT v7 design matrix remains the compatibility/archive format. Formal Python loops should use uncompressed memmap-friendly `.npy` sidecars rather than compressed NPZ random access.

### Coverage And Fold Mask Cache

For each endpoint phase:

```text
S_tau(v, i, phase) = I[X_ULF_only_i(v, phase,tau) > tau]
Coverage_tau_all(v, phase) = sum_i S_tau(v, i, phase)
Coverage_tau_fold_h(v, phase) = Coverage_tau_all(v, phase) - S_tau(v, h, phase)
Omega_ULF_tau_fold_h(phase) = {v : Coverage_tau_fold_h(v, phase) >= 5}
```

`HF_overlap_tau*_bool` 可缓存，因为它只依赖 accepted HF/ULF component exposures 和 tau，不依赖 outcome。

### Vectorized Partial Spearman Kernel

每个 training fold 内，ranks 只能在 training set 内计算。LOOCV map fitting、permutation map fitting、bootstrap maps 和 jitter resamples 中禁止使用 full-sample ranks。

DeltaHF-adjusted core branch 同时 residualize outcome 和 exposure against：

```text
rank(Y_HF_ref_train)
rank(DeltaHFScore_train)
```

No-DeltaHF core branch 只 residualize against：

```text
rank(Y_HF_ref_train)
```

### Fold-Level Score Operator For Permutation

Primary branch 的 formal Freedman-Lane permutation 可使用 fold-level score operator，但逻辑上必须等价于对每个 permuted outcome 重新计算完整 ULF map 和 `ULFScore_mean_main`。

Score operator 必须保留：

```text
DeltaHFScore if recomputed under the fold/HF map semantics
rho_ULF(v)
M_ULF(v)
V_score
ULFScore_mean_main
prediction model
LOOCV statistic
```

### Bootstrap Efficiency

Subject-level bootstrap 仍然是 primary branch 的 full-process map stability analysis。它必须重建 bootstrap `DeltaHFScore`、HF support QC、`Omega_ULF_tau`、`rho_ULF` 和 `M_ULF`。Bootstrap SE 通过 streaming Welford updates 累积。实现不得保存 10000 张 bootstrap maps。

### Spatial Jitter Efficiency

Jitter 改变 e-field geometry。Primary `X`-derived caches 在 jitter 下失效，不能当作 exposure 未变化来复用。每次 jitter iteration 必须重建 HF component exposure、ULF component exposure、HF-overlap exclusion、ULF-only exposure、candidate mask、`Omega_ULF_tau`、`DeltaHFScore`、HF support QC、map、scores 和 LOOCV metrics。

### Prohibited Speed Shortcuts

```text
lowering B=10000 formal permutation/bootstrap
adaptive permutation early stopping
changed tau thresholds
changed Coverage>=5 rule
changed estimator
approximate ranks
full-sample ranks inside LOOCV/permutation/bootstrap
full-sample Omega used for fold scoring
reusing full-sample DeltaHFScore for held-out patients
using a tau-independent X_ULF_only matrix
using total ULF exposure in place of ULF-only exposure for the primary branch
including HF-overlap voxels in the primary ULF predictor
expanding the locked HF score support after seeing ULF results
imputing or smoothing HF map coefficients outside V_HF_score
```

### Runtime Profile

`direct_voxel_ULF_only_generation_manifest.json` should include：

```text
runtime_profile:
  preprocess_s
  sidecar_write_s
  load_design_s
  hf_score_support_qc_s
  observed_loocv_s
  no_delta_hf_s
  gain_endpoint_s
  permutation_s
  bootstrap_s
  jitter_s
  display_qc_s
  n_voxels_candidate
  n_voxels_tau200_mean/min/max
  n_voxels_hf_overlap_mean/min/max
  n_voxels_hf_score_support
  python_jobs
  blas_threads
  memmap_sidecars
  score_operator_enabled
  score_operator_exact_scaling
  bootstrap_finite_count_summary
```

### Equivalence And Regression Tests

Before formal execution, run a deterministic small-subset comparison against a brute-force implementation：

```text
n_subjects = all available subjects
n_voxels = 1000 to 10000 deterministic voxels
B_perm = 20
B_boot = 20
B_jitter = 5
seed = 42
```

Required exact-equivalence checks：

```text
fold-specific DeltaHFScore
fold-specific HF out-of-support burden
fold-specific Omega_ULF_tau
HF-overlap exclusion masks
partial Spearman rho map
benefit-oriented M_ULF map
ULFScore_mean_main
LOOCV held-out predictions
LOOCV Spearman rho
small permutation null statistics
small bootstrap finite-count summaries
```

Floating outputs must match within a predefined `float64` tolerance. Boolean masks and fold membership must match exactly.

## Execution Priority And Gatekeeping / 执行优先级与 Gatekeeping

ULF direct voxel analysis 必须按 gatekeeping sequence 执行。不要一次性运行所有 sensitivity analyses。

### Round 0: Input Readiness

运行：

```text
clinical table audit:
  Y_HF_ref exists at T2 HF-only 3-month same-day reference
  Y_post_immediate exists at T2 HF+ULF same-day immediate endpoint, if modeled
  Y_post_chronic exists at T3 HF+ULF 3-month endpoint, if modeled
  DeltaHFScore inputs exist
  ID joins to imaging subject
  scale direction is defined

visit chronology audit:
  T0 preoperative baseline exists when available
  T1 1-month HF immediate opening visit exists when available
  T2 HF-only 3-month and HF+ULF immediate are same-day or same-session
  T3 HF+ULF 3-month follow-up phase is labeled

e-field availability check:
  HF-only T2 reference e-fields exist
  HF+ULF immediate HF-component e-fields exist when immediate endpoint is modeled
  HF+ULF immediate ULF-component e-fields exist when immediate endpoint is modeled
  HF+ULF chronic HF-component e-fields exist when chronic endpoint is modeled
  HF+ULF chronic ULF-component e-fields exist when chronic endpoint is modeled
  all matches are unique
  raw sim-efield is used

component audit:
  HF frequency >= 100 Hz
  ULF frequency <= 50 Hz
  mixed or proxy component fields are labeled

locked HF model audit:
  hf_3m_direct_voxel_model tau200/partial_spearman source exists
  HFScore_mean_main and M_HF support are valid
  fold-specific map generation is available for LOOCV DeltaHFScore
  hf_prediction_validity_status is recorded
```

只有当所有 primary endpoint subjects 具有完整 clinical 和 e-field inputs，运行 immediate endpoint 时已确认 same-day immediate reference，并且 valid sample size 至少为 12，才进入 Round 1。

### Round 1: Preprocessing, Overlap QC, And HF Support QC

运行 preprocessing sidecars 和 flip audit。确认：

```text
ULF component matrix is non-empty
X_ULF_only_tau200 matrix is non-empty
HF_overlap outputs are valid even if overlap is zero
tau200 Coverage>=5 Omega_ULF is non-empty
each subject has nonzero HF component exposure
each subject has nonzero or explicitly absent ULF-only exposure
DeltaHFScore support summary is generated
HF_out_support_fraction is not extreme enough to invalidate HF adjustment
```

如果大多数 subjects 的 ULF-only exposure 为空，停止并报告 primary ULF-only predictor 不可建模。如果 HF out-of-support burden 较大，则仅作为 exploratory 继续，或加入预先声明的 HF-out-of-support sensitivity。

### Round 2: Core Chronic Observed LOOCV

除非 immediate endpoint 被显式提升为 co-primary，否则先运行：

```text
endpoint = MDS-UPDRS III total chronic HF+ULF 3-month score
core branches =
  tau200 / partial_spearman / delta_hf_adjusted
  tau200 / partial_spearman / no_delta_hf
score = ULFScore_mean_main
covariates =
  delta_hf_adjusted: Y_HF_ref + DeltaHFScore
  no_delta_hf:       Y_HF_ref
validation = LOOCV
```

两个 core branches 完成后，根据 locked HF result 记录：

```text
ulf_primary_branch
delta_hfscore_role
branch_role_decision_reason
```

只有被 branch-role resolver 选为 primary 的分支满足所有 folds 完成、`ULFScore_mean_main` 非常数、held-out predictions 有限、LOOCV rho 为正、`Q2 > 0`，并且 ULFScore model 优于其 branch-specific nuisance-only baseline 时，才进入 Round 3。

如果两个 core chronic branches 都为负、近似常数、缺少必要输入支持，或被单个 high-leverage subject 主导，则停止。不要在 core-branch failure 后运行 `tau180/tau220` 来寻找更好 threshold。

### Round 2b: Same-Day Immediate Observed LOOCV

默认作为 key secondary 运行；只有显式声明时作为 co-primary：

```text
endpoint = MDS-UPDRS III total same-day immediate HF+ULF score
core branches =
  tau200 / partial_spearman / delta_hf_adjusted
  tau200 / partial_spearman / no_delta_hf
score = ULFScore_mean_main
covariates =
  delta_hf_adjusted: Y_HF_ref + DeltaHFScore_immediate
  no_delta_hf:       Y_HF_ref
validation = LOOCV
```

如果 complete，也运行 same-day gain sensitivity：

```text
endpoint = Gain_immediate
branch = tau200 / partial_spearman_gain_endpoint
```

如果 immediate endpoint 满足与 chronic observed LOOCV 相同的标准，则可进入 smoke resampling。

### Round 3: Equivalence And Smoke Resampling

运行：

```text
deterministic equivalence test
smoke permutation B=1000
smoke bootstrap B=1000
smoke jitter B=100
```

只有当 optimized 和 brute-force paths 一致、smoke resampling 无 artifacts、bootstrap finite-count distribution 可接受，并且 jitter 不反转 signal direction 时，才进入 Round 4。

### Round 4: Formal Permutation

只对 branch-role resolver 记录为 primary 的分支运行：

```text
tau200 / partial_spearman
branch_role = ulf_primary_branch
B = 10000
seed = 42
statistic = LOOCV Spearman rho
```

如果 permutation 完成、p value 有限，且 observed signal 仍为正，则进入 bootstrap。如果 `p_perm > 0.10` 且 `Q2 <= 0`，停止 heavy analyses 并生成 minimal exploratory report。

### Round 5: Formal Bootstrap

运行：

```text
tau200 / partial_spearman
branch_role = ulf_primary_branch
B = 10000
seed = 42
```

只有当 bootstrap finite counts 可接受、core sign stability 可解释，并且大多数 bootstrap maps 非空时，才继续。

### Round 6: Formal Spatial Jitter

运行：

```text
tau200 / partial_spearman
branch_role = ulf_primary_branch
B = 1000
FWHM = 2 mm
```

如果 jitter map correlation 接近 0 或 signal direction 反转，将结论降级为 spatially fragile exploratory association。

### Round 7: Tau Sensitivity

只运行 observed LOOCV：

```text
tau180 / partial_spearman
tau220 / partial_spearman
run for both delta_hf_adjusted and no_delta_hf core roles when inputs allow
```

不对 tau sensitivity 运行 formal permutation/bootstrap。将 tau180/tau220 解释为 exposure-definition robustness checks，而不是 threshold search。

### Round 8: Additional Sensitivities

只在 primary branch 可解释后运行：

```text
non-selected core branch comparison
gain endpoint sensitivity
total ULF exposure sensitivity
HF-out-of-support covariate sensitivity when support burden is nontrivial
Y_base-added collinearity sensitivity if baseline data are complete
```

`Y_base`-added sensitivity：

```text
delta_hf_adjusted:
  Y_post ~ ULFScore_mean_main + Y_HF_ref + DeltaHFScore + Y_base

no_delta_hf:
  Y_post ~ ULFScore_mean_main + Y_HF_ref + Y_base
```

它是 collinearity/stability check，不替代 primary model。

### Round 9: Display And Final Manifests

只有在 statistical branches 完成后，才生成 display smoothing、bilateral homologous display maps、HF-overlap exclusion overlays、HF support burden summaries、STN/SNr outlines、PDF QC 和 final manifests。Display outputs 不得反馈进入 ULFScore、LOOCV、permutation、bootstrap 或 jitter。

### Round 10: Optional Future Analyses

不属于当前 executable mainline：

```text
OLS ANCOVA
Coverage>=6
Coverage>=8 / 50% rule
5/7/10-fold CV
OSS-DBS direct voxel analysis
paper-like spatial similarity score
automatic localization / electrode reconstruction QC
```

### Recommended First Batch

第一批实际运行只覆盖：

```text
Round 0
Round 1
Round 2 chronic observed LOOCV
Round 2b immediate observed LOOCV, if same-day immediate data are complete
Round 3 smoke only
```

具体 first-batch scope：

```text
MDS-UPDRS III total chronic endpoint
MDS-UPDRS III total same-day immediate endpoint, if complete
tau200
partial_spearman
Coverage>=5
ULF-only exposure
HF-overlap exclusion
DeltaHFScore-adjusted model
HF out-of-support support QC
ULFScore_mean_main
LOOCV
covariate-only comparison
equivalence test
smoke permutation B=1000
smoke bootstrap B=1000
smoke jitter B=100
basic QC JSON + manifest
```
