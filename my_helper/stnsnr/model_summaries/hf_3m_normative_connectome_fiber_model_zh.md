# HF-Only 3m Normative Connectome Fiber-Level Model

## Research Question

哪些被 HF stimulation 触碰到的 normative connectome streamlines 与更好的 3-month HF-only 临床结局相关？

这是一个 full-connectome fiber-level DBS Fiber Filtering model。单条 streamline 是建模单位。Target atlases 只在建模后用于 endpoint labels、anatomical enrichment、QC 和 display grouping；它们不定义主预测变量。

Frequency definitions:

```text
HF  = high-frequency stimulation component, frequency_Hz >= 100
ULF = ultra-low-frequency stimulation component, frequency_Hz <= 50
```

## Endpoint

Primary endpoint:

```text
Y_post = raw HF-only 3-month clinical score
```

Primary covariate:

```text
Y_base = raw preoperative clinical score
```

Default first-pass scales:

```text
MDS-UPDRS III score (STN, 3 m)
MDS-UPDRS III axial score (STN, 3 m)
```

Raw scores 来源：

```text
/Users/mojackhu/Research/STNSNr/summary/cohort/subj/subject_effect_origin.xlsx
```

临床行按 `ID` 连接（如 `SNr003`, `SNr006`）。本模型不使用 improvement-rate table。Scale direction 来自共享 direction table；未知量表必须在运行前显式定义 higher-is-better 或 lower-is-better。

## Inputs

- `3m/STN` 条件下的 HF-only raw `sim-efield` maps，单位为 `V/m`。使用 raw `sim-efield`，不使用 `sim-efieldgauss`。
- Public Lead-DBS structural connectomes：

  ```text
  PPMI 85 (Ewert 2017)          observed figure-grade robustness
  MGH-USC HCP 32 (Horn 2017)    observed figure-grade robustness
  dTOR-985 Full (Elias 2024)    primary analysis
  ```

- 每个 connectome `data.mat` 中的 right canonical streamline features。
- 使用 `ea_flip_lr_nonlinear` 做 left/right homology。
- Anatomical atlases 只用于 labeling/QC/display：

  ```text
  STNSNr-connected regions
  STN-connected regions
  SNr-connected regions
  Custom STN/SNr overlays
  ```

- OSS-DBS sensitivity environment：

  ```text
  conda env: ossdbsv2
  ```

在任何正式 OSS-DBS sensitivity run 前，必须锁定 primary OSS parameter set，并写入该 branch manifest：

```text
oss_model_set = primary_locked
axon_model = OSS-DBS default mammalian myelinated axon model
axon_diameter_um = locked_default_from_ossdbs_or_leaddbs_config
n_nodes = locked_default_from_ossdbs_or_leaddbs_config
waveform = clinical rectangular pulse unless otherwise specified
frequency_Hz = clinical HF frequency
pulse_width_us = clinical pulse width
amplitude = clinical amplitude
tissue_model = same as accepted Lead-DBS / OSS-DBS project default
conductivity_model = locked and recorded
activation_output = fractional activation if available, else binary activation
```

最低 e-field 检查：必需路径存在、subject/side/condition 唯一匹配、文件为 raw `sim-efield`、单位记录为 `V/m`。缺失或多重匹配会使该 scale/run 失败。E-fields 不自动补算。

## Feature Construction

候选全集是 full public connectome，而不是 target-restricted seed-target tracts。

Right canonical fiber model:

```text
canonical side = right
E_R_i(l)      = peak raw sim-efield along right canonical fiber l
E_L_to_R_i(l) = peak left e-field after ea_flip_lr_nonlinear along the same right canonical fiber l
X_HF_i(l)     = (E_R_i(l) + E_L_to_R_i(l)) / 2
```

左侧刺激先翻转到 right canonical space，再沿同一组 right-sided streamline features 采样。因此模型使用双侧 E-field 信息，但 streamline feature set 是单侧 canonical，而不是真正的 bilateral streamline set。

同侧 alternating HF subprogram e-fields 在 fiber sampling 前按 voxel-wise maximum 合并。Exposure 不按 frequency 或 pulse width 缩放。

候选规则与 HF direct voxel coverage logic 保持一致：

```text
tau_primary = 800 V/m
tau_sensitivity = 1500 V/m
Coverage_tau(l) = sum_i I[X_HF_i(l) > tau]
F_candidate_tau = {l: Coverage_tau(l) >= 5}
```

`X_HF_i(l)` 用于 candidate definition、fiber-wise association、scoring、LOOCV 和 prediction。dTOR exposure 和 candidate 计算必须 chunked；一次性载入完整 dTOR `fibers` matrix 或全部 exposure values 是无效实现。

OSS-DBS branch 继承同一个 peak E-field candidate universe。`X_HF_OSS_i(l)` 只在 candidate selection 之后引入，不能重新定义、缩小或扩大 `F_candidate_tau`。

## Statistical Model

### Primary Estimator

对每条 candidate fiber `l`，使用 baseline-adjusted partial Spearman，并对 ties 使用 average ranks：

```text
rho_HF(l) =
  corr(
    resid(rank(Y_post_i)  ~ rank(Y_base_i)),
    resid(rank(X_HF_i(l)) ~ rank(Y_base_i))
  )
```

如果 fiber 的 exposure variance、rank variance 或 residualized exposure variance 为 0，则设 `rho_HF(l)=NaN`，并从 scoring 中排除。

Benefit-oriented fiber weight:

```text
M_HF(l) = -rho_HF(l)   for lower-is-better scales
M_HF(l) =  rho_HF(l)   for higher-is-better scales
```

正值 `M_HF(l)` 表示 sweet 或 benefit-associated。负值 `M_HF(l)` 表示 sour 或 worse-outcome-associated。FDR q-values 只用于 QC/display，不筛选主模型，也不定义 scoring fiber set。

### Optional Supplemental Estimator

OLS ANCOVA 保留为未来可选补充估计器。当前可执行分析不运行该分支，也不生成对应输出文件。

```text
Y_post_i = alpha_l
         + theta_HF(l) * X_HF_i(l)
         + beta_l      * Y_base_i
         + error_i,l
```

如果未来启用，`theta_HF(l)` 将作为 fiber-wise OLS ANCOVA coefficient 报告。当前模型只使用 baseline-adjusted partial Spearman `rho_HF(l)` 估计器进行 map fitting、`NetFiberScore`、LOOCV、permutation、bootstrap 和 display outputs。

### Patient-Level Score

在每个 full-sample map 或 LOOCV training fold 内：

```text
F+ = top 1% fibers with largest positive M_HF(l)
F- = top 0.5% fibers with most negative M_HF(l)

SweetWeighted_i(l) = X_HF_i(l) * M_HF(l),      l in F+
SourWeighted_i(l)  = X_HF_i(l) * [-M_HF(l)],   l in F-

SweetPeak5_i = mean of top 5% largest SweetWeighted_i(l)
SourPeak5_i  = mean of top 5% largest SourWeighted_i(l)

NetFiberScore_i = SweetPeak5_i - SourPeak5_i
```

`F+` 和 `F-` 在 `F_candidate_tau` 内选择，并排除 NaN 或 degenerate fibers。Percentile counts 使用 `ceil(percent * n)`；当对应 positive 或 negative pool 非空时至少保留 1 条 fiber。空 `F+` 或 `F-` 对应 component 记为 `0`。如果 selected set 非空但某患者对所有 selected fibers 的 exposure 都为 0，则对应 peak score 记为 `0`。

Final prediction model:

```text
Y_post_i = alpha
         + delta * NetFiberScore_i
         + beta  * Y_base_i
         + error_i
```

模型在 raw post-score 尺度上拟合。主验证统计量是 held-out predictions 与 held-out raw outcomes 之间的 LOOCV Spearman rho。

## Validation

- 使用 leave-one-patient-out cross-validation。
- 每个 fold 内重建 `F_candidate_tau`、拟合 `M_HF(l)`、选择 fold-specific `F+` 和 `F-`、计算 training 和 held-out `NetFiberScore`，并且只用 training patients 拟合 prediction model。
- 与 covariate-only baseline `Y_post ~ Y_base` 比较。
- Primary metrics：LOOCV Spearman rho 和 plus-one permutation P value。
- Secondary metrics：LOOCV Pearson `r`、MAE、RMSE 和 `Q2`。
- Formal Freedman-Lane permutation：`B=10000`，seed `42`，仅限 dTOR primary peak-E-field branch。
- Subject-level bootstrap：`B=10000`，seed `42`，仅限 dTOR primary peak-E-field branch。
- Smoke permutation/bootstrap：`B=1000`，seed `42`。
- Optional OLS ANCOVA 仅作为未来 sensitivity analysis 记录，当前执行不运行。

PPMI、MGH 和 dTOR 都生成 observed figure-grade outputs。dTOR 额外承担 formal permutation、bootstrap 和 jitter QC。参考 Nature papers 中的 5-fold/10-fold CV 只写入 reference checklist；对本 `n=16` 队列，LOOCV 是可执行验证设计。

## Sensitivity And Controls

Executable branches:

```text
peak_efield_tau800_primary
peak_efield_tau1500_sensitivity
top1500_top500_sensitivity
ossdbs_activation_sensitivity
plain_connected_streamline_control
```

### OSS-DBS Activation Sensitivity

OSS-DBS 在 peak E-field candidate set 已经定义之后，用 pathway/axon activation 替代 peak E-field exposure：

```text
X_HF_OSS_i(l) = OSS-DBS activation value for fiber l under subject i HF stimulation
```

对同侧 alternating HF subprograms，先分别计算每个 subprogram 的 OSS activation，再取最大值：

```text
A_side_i,p(l) = OSS activation under HF subprogram p
A_side_i(l)   = max_p A_side_i,p(l)
```

双侧 right-canonical OSS activation exposure 定义为：

```text
X_HF_OSS_i(l) = (A_R_i(l) + A_L_to_R_i(l)) / 2
```

OSS branch 使用与 peak E-field branch 相同的 candidate rule：

```text
Coverage_tau(l) = sum_i I[X_HF_i(l) > tau]
F_candidate_tau = {l: Coverage_tau(l) >= 5}
tau_primary = 800 V/m
```

Candidate fibers 不由 OSS activation 筛选。这样避免 sensitivity branch 引入额外建模自由度。

OSS fiber-wise estimator：

```text
rho_HF_OSS(l) =
  corr(
    resid(rank(Y_post_i)      ~ rank(Y_base_i)),
    resid(rank(X_HF_OSS_i(l)) ~ rank(Y_base_i))
  )

M_HF_OSS(l) = -rho_HF_OSS(l)   for lower-is-better scales
M_HF_OSS(l) =  rho_HF_OSS(l)   for higher-is-better scales
```

正值 `M_HF_OSS(l)` 表示 activation of that streamline is benefit-associated。负值 `M_HF_OSS(l)` 表示 activation is worse-outcome-associated。

OSS patient-level score：

```text
F+_OSS = top 1% fibers with largest positive M_HF_OSS(l)
F-_OSS = top 0.5% fibers with most negative M_HF_OSS(l)

SweetWeighted_OSS_i(l) = X_HF_OSS_i(l) * M_HF_OSS(l),       l in F+_OSS
SourWeighted_OSS_i(l)  = X_HF_OSS_i(l) * [-M_HF_OSS(l)],    l in F-_OSS

SweetPeak5_OSS_i = mean top 5% largest SweetWeighted_OSS_i(l)
SourPeak5_OSS_i  = mean top 5% largest SourWeighted_OSS_i(l)

NetFiberScore_OSS_i = SweetPeak5_OSS_i - SourPeak5_OSS_i
```

OSS prediction model：

```text
Y_post_i = alpha
         + delta * NetFiberScore_OSS_i
         + beta  * Y_base_i
         + error_i
```

对每个 connectome、scale 和 LOOCV fold `h`：

```text
train = all patients except h
test  = patient h
```

Fold workflow：

1. 只用 training patients 计算 peak E-field `Coverage_tau800_fold_h`。
2. 定义 `F_candidate_tau800_fold_h = {l: Coverage_tau800_fold_h(l) >= 5}`。
3. 从 OSS sidecar 读取这些 candidate fibers 上 training 和 held-out 的 `X_HF_OSS`。
4. 只在 training patients 上估计 `rho_HF_OSS(l)`。
5. 转换为 `M_HF_OSS(l)`。
6. 选择 fold-specific `F+_OSS` 和 `F-_OSS`。
7. 计算 training 和 held-out `NetFiberScore_OSS`。
8. 只用 training patients 拟合 `Y_post ~ NetFiberScore_OSS + Y_base`。
9. 预测 held-out `Y_post`。
10. 将 held-out 行写入 `normative_HF_fiber_oss_loocv_predictions.csv`。

Fold-level prohibitions：

```text
no full-sample ranks
no full-sample M_HF_OSS
no full-sample F+_OSS or F-_OSS
no held-out patient in candidate definition
no held-out patient in prediction model fitting
```

OSS branch permutation 只做 smoke：

```text
B = 1000
seed = 42
```

采用 Freedman-Lane residual permutation：

1. 拟合 nuisance model `Y_post ~ Y_base`。
2. 提取 residuals `e_i`。
3. 置换 residuals 得到 `e_perm_i`。
4. 重构 `Y*_i = fitted_Y_base_i + e_perm_i`。
5. 每次 permutation 都完整重跑 OSS LOOCV workflow，包括 candidate definition、`rho_HF_OSS`、`M_HF_OSS`、`F+_OSS`/`F-_OSS`、`NetFiberScore_OSS`、held-out prediction 和 LOOCV Spearman rho。

Permutation p value：

```text
p_plus_one = (1 + count(|stat_perm| >= |stat_obs|)) / (B + 1)
```

OSS 不运行 formal `B=10000` permutation，也不运行 bootstrap。

OSS plain activation control 用于检验 OSS result 是否主要反映 activation burden 或 lead placement：

```text
PlainOSSActivated_i(l) = I[X_HF_OSS_i(l) > 0]
PlainOSSActivationCount_i = sum_l PlainOSSActivated_i(l)
PlainOSSActivationSum_i   = sum_l X_HF_OSS_i(l)
PlainOSSActivationTop5_i  = mean top 5% X_HF_OSS_i(l) among activated candidate fibers
```

OSS control model comparisons：

```text
Y_post ~ Y_base
Y_post ~ PlainOSSActivationTop5 + Y_base
Y_post ~ NetFiberScore_OSS + Y_base
Y_post ~ NetFiberScore_OSS + PlainOSSActivationTop5 + Y_base
```

在本 `n=16` 队列中，OSS joint model 只作为 QC，不解释为 causal decomposition。

Plain connected-streamline control 故意不使用 clinical outcome、`rho_HF(l)`、`M_HF(l)` 或 sweet/sour weights：

```text
Touched_i(l) = I[X_HF_i(l) > tau]
PlainCoverage(l) = sum_i Touched_i(l)
PlainTouchedCount_i = sum_l Touched_i(l)
PlainExposureSum_i  = sum_l X_HF_i(l)
PlainExposureTop5_i = mean top 5% X_HF_i(l) among touched fibers
```

Control model comparisons:

```text
Y_post ~ Y_base
Y_post ~ PlainExposureTop5 + Y_base
Y_post ~ NetFiberScore + Y_base
Y_post ~ NetFiberScore + PlainExposureTop5 + Y_base
```

在本 `n=16` 队列中，joint model 只作为 QC。它用于检验 outcome-filtered fibers 是否提供超出 stimulation burden、lead placement 和 connectome density 的信息。

dTOR jitter QC 分两层：

```text
jitter_level_1_selected_display = selected/display fibers only
jitter_level_2_model_density    = model-density robustness over candidate fibers or feasible subset
```

## Outputs

Output root:

```text
/Volumes/VAL/STNSNr/summary/normative_connectome_fiber/hf/<connectome_slug>/<scale_slug>/<branch>/
```

Required observed outputs per branch:

```text
normative_HF_fiber_weights.csv
normative_HF_fiber_scores.csv
normative_HF_fiber_loocv_predictions.csv
normative_HF_fiber_mapping_qc.json
normative_HF_fiber_generation_manifest.json
normative_HF_fiber_display_top1_positive.tck
normative_HF_fiber_display_top1_positive.mat
normative_HF_fiber_display_top0p5_sour.tck
normative_HF_fiber_display_top0p5_sour.mat
normative_HF_fiber_density_map.nii.gz
normative_HF_fiber_endpoint_labels.csv
normative_HF_fiber_cortical_endpoint_summary.csv
normative_HF_fiber_subcortical_crossing_summary.csv
normative_HF_fiber_label_enrichment.csv
normative_HF_fiber_unthresholded_weighted_density.nii.gz
normative_HF_fiber_positive_weighted_density.nii.gz
normative_HF_fiber_negative_weighted_density.nii.gz
normative_HF_fiber_neglogp_density.nii.gz
normative_HF_fiber_qvalue_summary.csv
normative_HF_fiber_top_percentile_sweep_summary.csv
fdr_summary_by_scale.csv
fdr_thresholded_positive_density_q05.nii.gz
fdr_thresholded_negative_density_q05.nii.gz
fdr_thresholded_positive_density_q10.nii.gz
fdr_thresholded_negative_density_q10.nii.gz
```

对于连续型/统计型 NIfTI 输出，未覆盖或未建模的 voxel 写为 `NaN`，不是 `0`。这包括 density support 或 model candidate support 外的 weighted density、positive/negative weighted density、`-log(p)` density、FDR-thresholded density、stability density、jitter density、plain touched density 和 display-smoothed density maps。`0` 只表示 support 内真实的零贡献。如果输出 count/binary masks，它们由于语义是计数/false，在 support 外仍写为 `0`。

dTOR primary branch additionally writes:

```text
normative_HF_fiber_permutation_summary.csv
normative_HF_fiber_bootstrap_se.csv
normative_HF_fiber_bootstrap_selection_frequency.csv
normative_HF_fiber_bootstrap_sign_stability.csv
normative_HF_fiber_fold_selection_frequency.csv
normative_HF_fiber_fold_sign_stability.csv
normative_HF_fiber_stability_density_map.nii.gz
normative_HF_fiber_jitter_summary.csv
normative_HF_fiber_jitter_model_similarity.csv
normative_HF_fiber_jitter_selected_overlap.csv
normative_HF_fiber_jitter_density_correlation.csv
normative_HF_fiber_jitter_example_density_maps/
```

Plain connected-streamline control writes:

```text
normative_HF_plain_touched_fibers.tck
normative_HF_plain_touched_density_map.nii.gz
normative_HF_plain_touched_summary.csv
normative_HF_plain_connected_model_comparison.csv
```

OSS-DBS activation sensitivity writes:

```text
normative_HF_fiber_oss_parameter_manifest.json
normative_HF_fiber_oss_activation_matrix_summary.csv
normative_HF_fiber_oss_loocv_predictions.csv
normative_HF_fiber_oss_permutation_summary.csv
normative_HF_plain_oss_activation_summary.csv
normative_HF_plain_oss_activation_model_comparison.csv
```

Cross-connectome summaries 写在 HF normative connectome fiber summary root：

```text
connectome_scale_performance_summary.csv
connectome_scale_overlap_summary.csv
connectome_density_correlation_summary.csv
connectome_selected_label_summary.csv
```

Minimum table semantics:

- `normative_HF_fiber_weights.csv`: `connectome`, `fiber_id`, `tau_v_per_m`, `coverage`, `rho_HF`, `p_uncorrected`, `q_fdr`, `M_HF`, `direction_class`, display/sensitivity flags, and target labels for QC。
- `normative_HF_fiber_scores.csv`: `subject_id`, `score_map_source`, `connectome`, `branch`, `SweetPeak5`, `SourPeak5`, `NetFiberScore`, candidate/selected/peak fiber counts, and `is_primary_score`。
- OSS branch 中的 `normative_HF_fiber_scores.csv` 额外记录 `SweetPeak5_OSS`、`SourPeak5_OSS` 和 `NetFiberScore_OSS`。
- `fdr_summary_by_scale.csv`: q-threshold counts 以及 percentile-selected fibers 与 q-ranked fibers 的 overlap。
- `normative_HF_fiber_label_enrichment.csv`: selected sweet/sour fibers 相对 plain touched-streamline background 的 enrichment。
- `normative_HF_fiber_mapping_qc.json`: candidate counts、coverage distribution、degenerate fiber counts、empty-fold failures、FDR method、label summaries、chunking parameters、memory use summaries、OSS-DBS status 和 OSS activation-output type。

PPMI 和 MGH observed branches 不要求 formal permutation/bootstrap files。其 manifests 记录：

```text
resampling_status = observed_only_connectome_robustness
```

## Visualization

Display outputs include:

- top 1% positive fibers by `M_HF(l)`；
- top 0.5% sour fibers by negative `M_HF(l)`；
- selected-fiber density maps；
- unthresholded weighted-density maps；
- `-log(P)` density maps and q-value summaries；
- endpoint、cortical-origin、subcortical-crossing 和 label-enrichment tables；
- plain touched-streamline density maps；
- STN/SNr and STNSNrplus anatomical overlays。

任何 display subset 都不是主统计显著性图。FDR q-values 和 q-thresholded density maps 用于 QC/display 透明性，但不筛选主模型、不定义 `F+`/`F-`，也不进入 `NetFiberScore`。

## Execution Efficiency

Formal runs 必须 chunked 且 memmap-friendly。

PPMI/MGH 可使用单个 sidecar arrays：

```text
X_float32_fiber_major.npy       # shape = fiber x subject, averaged X_HF
S800_bool.npy                   # X_HF > 800 V/m
S1500_bool.npy                  # X_HF > 1500 V/m
fiber_id.npy
candidate_fiber_metadata.json
```

dTOR 必须使用 chunked sidecars：

```text
chunks/
  X_float32_fiber_major_chunk-000001.npy
  S800_bool_chunk-000001.npy
  S1500_bool_chunk-000001.npy
  fiber_id_chunk-000001.npy
fiber_chunk_manifest.json
candidate_fiber_metadata.json
```

OSS activation sidecars 在 peak E-field candidate construction 后写出，并使用同一组 fiber ids：

```text
X_oss_float32_fiber_major.npy
PlainOSSActivated_bool.npy
oss_parameter_manifest.json
oss_activation_sidecar_metadata.json
```

对 alternating HF subprograms，可以缓存 subprogram-level activation matrices，但可执行分析使用上文定义的 max-reduced `A_side_i(l)` 和 averaged `X_HF_OSS_i(l)`。

对 LOOCV fold `h`，通过 subtraction 得到 training-fold coverage：

```text
S_tau(l, i) = I[X_HF_i(l) > tau]
Coverage_tau_all(l) = sum_i S_tau(l, i)
Coverage_tau_fold_h(l) = Coverage_tau_all(l) - S_tau(l, h)
F_candidate_tau_fold_h = {l : Coverage_tau_fold_h(l) >= 5}
```

优化实现不得改变 estimand：ranks 必须在 training folds 内计算，禁止 full-sample ranks，`F+`/`F-` 必须在每个 fold/permutation/bootstrap 中重新选择，formal resampling counts 不得为了提速降低。dTOR 的 `SweetPeak5` 和 `SourPeak5` 应使用 streaming top-k reducers；除非显式开启 debug output，formal loops 不得写出完整 per-permutation 或 per-bootstrap fiber-weight tables。

`normative_HF_fiber_generation_manifest.json` 记录 runtime profile、connectome slug、branch、chunk size/count、sidecar dtype/layout、Python jobs、BLAS threads、candidate counts、coverage summaries、bootstrap finite-count summaries，以及 optimized equivalence test 是否通过。

## Interpretation Boundary

该模型估计 normative fiber-level HF stimulation associations。它比 seed-target target-level modeling 更接近 DBS Fiber Filtering，但仍使用 population connectomes，不能证明 patient-specific axonal causality。

应解释为：

```text
HF stimulation appears more beneficial when it strongly modulates this normative streamline profile.
```

不应解释为：

```text
Every displayed streamline is a proven causal tract in every patient.
```

主结论需要 dTOR primary performance、PPMI/MGH cross-connectome consistency、transparent label enrichment，以及与 plain connected-streamline control 的清晰区分。

## Additional Exact-Equivalence Optimization Rules / 额外精确等价优化规则

本节只定义 implementation-level acceleration rules。这些规则可以改变调度、缓存、向量化、scratch storage 和 checkpointing，但不得改变 `rho_HF`、`M_HF`、`F+`、`F-`、`SweetPeak5`、`SourPeak5`、`NetFiberScore`、LOOCV、permutation p values、bootstrap summaries 或 OSS-DBS branch semantics。

### Outcome-Independent Cache Boundary

当 cache keys 匹配时，outcome-independent artifacts 可以跨 scales、folds、permutations、bootstraps、OSS branches 和 display branches 复用：

```text
fiber geometry
fiber_id order
right-canonical streamline coordinates
E_R_i(l)
E_L_to_R_i(l)
X_HF_i(l)
S_tau_R(l,i)
S_tau_L_to_R(l,i)
Coverage_tau_all(l)
fold-specific candidate masks by subtraction
endpoint labels
subcortical crossing labels
streamline-to-voxel density lookup
OSS activation sidecars for a fixed OSS parameter set
plain exposure and plain activation summaries
```

当 `Y_post`、`Y_base`、training membership、permutation residuals 或 bootstrap subject counts 改变时，outcome-dependent artifacts 必须重算：

```text
rank(Y_post_train)
rank(Y_base_train), if scale-specific
rho_HF(l)
M_HF(l)
F+
F-
SweetPeak5
SourPeak5
NetFiberScore
LOOCV prediction model
permutation statistic
bootstrap map and stability summaries
```

Exposure sidecars 是 connectome- and branch-specific，而不是 scale-specific，除非 scale-specific subject inclusion 不同。当两个 scales 使用完全相同的 valid subjects 时，它们复用同一套 exposure sidecars、candidate masks、plain touched-streamline background、endpoint labels、density lookup tables 和 OSS activation sidecars。如果某个 scale 缺失 subjects，应创建 subject-subset view，而不是重新采样 fibers。

### Cache Keys And Invalidation

每个 sidecar 和 intermediate cache 都必须记录 deterministic cache key：

```json
{
  "cache_key": {
    "connectome_slug": null,
    "connectome_path_hash": null,
    "fiber_id_hash": null,
    "subject_order_hash": null,
    "efield_path_manifest_hash": null,
    "efield_file_hashes": null,
    "left_to_right_transform_hash": null,
    "tau_values": [800, 1500],
    "coverage_rule": "Coverage_tau(l) = sum_i I[X_HF_i(l) > tau]; Coverage >= 5",
    "candidate_rule": "fold-specific candidate masks by training-subject coverage",
    "branch": null,
    "oss_parameter_manifest_hash": null,
    "software_version": null
  }
}
```

任一 cache-key field 改变时，该 cache 即失效。如果只改变 `Y_post` 或 `Y_base`，exposure sidecars 仍有效。如果只改变 scale 且 subject inclusion 相同，exposure sidecars 和 candidate masks 仍有效。如果只改变 display settings，statistical sidecars 仍有效。如果 OSS parameters 改变，OSS activation sidecars 失效，但 peak E-field sidecars 仍有效。

### Fold-Level Rank Residual Cache

对每个 LOOCV fold `h` 和 fiber chunk，可以缓存只在 training set 内计算的 exposure-rank residuals：

```text
xrank_h(l) = rank(X_train(l)) within training fold
xres_h(l)  = resid(xrank_h(l) ~ 1 + rank(Y_base_train))
znorm_h(l) = xres_h(l) / sqrt(sum(xres_h(l)^2))
```

建议 cache files：

```text
Z_rankresid_float32_or_float64_chunk-000001_fold-01.npy
valid_exposure_rankresid_bool_chunk-000001_fold-01.npy
```

对 observed 和 permuted outcomes，只重算 outcome 侧：

```text
yrank_h = rank(Y*_train)
yres_h  = resid(yrank_h ~ 1 + rank(Y_base_train))
unorm_h = yres_h / sqrt(sum(yres_h^2))
rho_HF(l) = dot(znorm_h(l), unorm_h)
```

`Z_h` 可在 LOOCV permutation 内复用。它不能跨 bootstrap resamples 复用，因为 bootstrap 改变 training-sample multiplicity。如果 `Y_base` 是 scale-specific，它也不能跨 scales 复用。仍然禁止 full-sample ranks。

### Batched Permutation Kernel

Permutation dot products 可以按 batch 做线性代数加速：

```text
permutation_batch_size = 32 or 64
U_h = [u_h_perm1, u_h_perm2, ..., u_h_permK]   # train_subject x K
RHO_chunk = Z_h_chunk @ U_h
```

Batching 只允许用于 exact vectorized linear algebra。每个 permutation 仍必须拥有自己的 `M_HF(l)`、`F+`、`F-`、`SweetPeak5`、`SourPeak5`、`NetFiberScore`、prediction model 和 LOOCV statistic。任何 permutation 都不得使用 averaged、pooled 或 shared selected-fiber set。

### Deterministic Top-K Tie Policy

优化后的 `argpartition`、heap 或 streaming top-k implementation 必须与 brute-force stable sorting 一致。Tie-breaking 固定为：

```text
F+ selection key:
  (-M_HF(l), fiber_id)

F- selection key:
  (M_HF(l), fiber_id)

Patient-specific SweetPeak5/SourPeak5 key:
  (-weighted_value, fiber_id)
```

更高 weight 优先；tie 时选择更小的 deterministic `fiber_id`。如果使用 `argpartition`，必须 overselect boundary buffer，再用上述 key 对 buffer stable-sort，并保留精确数量。

### dTOR Two-Pass Streaming Top-K

dTOR formal runs 不得 materialize full candidate-by-subject weighted matrices。

Pass 1 跨 chunks 选择 fibers：

```text
compute rho_HF(l)
compute M_HF(l)
update global heap for F+
update global heap for F-
```

Pass 2 只重新读取包含 selected `F+` 或 `F-` fibers 的 chunks 来计算 patient scores：

```text
SweetWeighted_i(l) = X_i(l) * M_HF(l)
SourWeighted_i(l)  = X_i(l) * [-M_HF(l)]
SweetPeak5_i       = patient-level top 5% mean over SweetWeighted_i(l)
SourPeak5_i        = patient-level top 5% mean over SourWeighted_i(l)
NetFiberScore_i    = SweetPeak5_i - SourPeak5_i
```

Full candidate-weight tables 只允许用于 observed small-connectome debug runs。dTOR formal runs 必须使用 two-pass streaming selected-fiber 和 patient-level top-k reducers。

### Coverage Bitmasks And Candidate Unions

Subject-side suprathreshold indicators 可以存为 `uint32` 或 `uint64` bitmasks，并用 popcount 计算 coverage：

```text
bit 0 = subject 1 right
bit 1 = subject 1 left-to-right
bit 2 = subject 2 right
bit 3 = subject 2 left-to-right
...
```

Transparent bool arrays 仍是 reference representation：

```text
S_tau_*_bool.npy
S_tau_subjectside_u32.npy
```

Bitmask coverage 只有在通过 bool-array coverage 的 exact equivalence test 后才允许使用。Fold-specific candidate masks 仍由 held-out subtraction 定义。可以缓存 `union_of_folds` mask 来减少 IO：

```text
candidate_tau800_fold_01_bool ... candidate_tau800_fold_16_bool
candidate_tau1500_fold_01_bool ... candidate_tau1500_fold_16_bool
candidate_tau800_union_of_folds_bool
candidate_tau1500_union_of_folds_bool
```

`union_of_folds` 可用于缩小 IO、OSS activation、labeling 和 density precomputation。每个 fold 仍必须使用自己的 fold-specific candidate mask。

### OSS Candidate-First Activation

OSS-DBS activation 只为 executable OSS branch 所需的 peak E-field candidate fiber union 计算：

```text
F_candidate_tau800_union_of_folds
F_candidate_tau1500_union_of_folds, if sensitivity is requested
```

Non-candidate fibers 不进入 `rho_HF_OSS`、`F+_OSS`、`F-_OSS`、`NetFiberScore_OSS`、LOOCV 或 smoke permutation。因此省略这些 fibers 的 OSS activation 不改变 OSS branch result。

OSS activation cache granularity：

```text
connectome x subject x side x subprogram x oss_parameter_hash x candidate_union
```

只有 subject、side、subprogram、OSS parameter manifest、candidate fiber set 和 connectome geometry 一致时才可复用。axon model、axon diameter、pulse width、amplitude、conductivity model、lead/e-field input、connectome geometry 或 candidate fiber ids 任一改变都会使 cache 失效。

建议 OSS cache manifests：

```text
oss_activation_cache_key.json
oss_subprogram_activation_manifest.csv
oss_max_reduction_manifest.csv
```

### Scratch, Checkpoint, And Random Index Control

Formal loops 应在可用时使用 local NVMe scratch，并在验证后 atomic promotion 到最终输出目录：

```text
scratch_root = /local_scratch/<run_id>/
final_root   = /Volumes/VAL/STNSNr/summary/...
```

Scratch relocation 不得改变 file contents、subject order、fiber order、random seeds 或 output semantics。

Permutation 和 bootstrap 使用 resumable blocks：

```text
permutation_block_size = 100 or 250
bootstrap_block_size   = 100 or 250
perm_block_0001_stats.npy
perm_block_0001_manifest.json
perm_block_0001.done
boot_block_0001_accumulator.npz
boot_block_0001_manifest.json
boot_block_0001.done
```

Partial blocks 永不计入。Rerun blocks 必须复用相同 random indices。Workers 只能写 block-local outputs；最终 CSV/JSON outputs 由 main process atomic 写出。

Random arrays 从 seed `42` 一次性生成，并成为 run definition 的一部分：

```text
permutation_indices_seed42.npy
bootstrap_subject_counts_seed42.npy
```

Resumed runs 必须复用同一 arrays 及其 recorded hashes。

### Label, Density, Rank-Pattern, And Chunk Autotune Caches

Endpoint labeling 和 density maps 使用预计算 lookup caches：

```text
fiber_endpoint_label_cache.parquet
fiber_subcortical_crossing_cache.parquet
fiber_to_voxel_sparse_index.npz
fiber_length_cache.npy
fiber_display_geometry_index.npy
```

Density maps 通过 selected fiber ids join 到 sparse voxel accumulator 生成。Sparse density lookup 必须使用与 brute-force display implementation 相同的 affine、interpolation、streamline sampling rule 和 voxelization rule。

允许 exact rank-pattern caching，尤其适合 binary 或 sparse OSS activation：

```text
rank_pattern_key = hash(bytes(X_train_l) + train_subject_ids + dtype)
```

只有 exact byte-identical exposure vectors 可以共享 rank-residual results。Formal runs 中禁止 rounding、binning 或 approximate hashing。

Chunk-size autotuning 可 benchmark：

```text
50k fibers
100k fibers
250k fibers
500k fibers
1M fibers
```

最终选择满足 peak memory 低于 `memory_budget * 0.7` 的最快 tested size。Manifest 记录 tested sizes、selected size、memory budget、peak memory 和 throughput。

### Stage Scheduling

推荐执行阶段：

```text
Stage 1: sidecar cache and coverage cache
Stage 2: deterministic equivalence test
Stage 3: observed LOOCV numeric outputs
Stage 4: smoke permutation/bootstrap
Stage 5: formal dTOR permutation
Stage 6: formal dTOR bootstrap
Stage 7: OSS smoke branch
Stage 8: endpoint labels and density maps
Stage 9: FDR/display-only maps
Stage 10: cross-connectome summaries
```

Display 和 anatomical-label outputs 是延后生成，不是省略。它们在 numeric QC 通过后，从 finalized selected-fiber ids 精确生成一次。

### Disallowed Acceleration Shortcuts

以下做法不是有效加速，因为它们会改变 estimand、validation design 或 statistical interpretation：

```text
reducing formal B=10000
adaptive permutation early stopping
full-sample ranks in fold-level estimation
approximate ranks
full-sample candidate mask replacing fold-specific candidate masks
fixed full-sample F+/F- used for LOOCV scoring
permutation score computed only from observed maps
outcome- or preliminary-rho-based fiber prefiltering
skip sour fibers
rewriting SweetPeak5/SourPeak5 as a linear matrix product
OSS activation only for observed selected fibers instead of the fold candidate universe
```

任何 optimized implementation 在正式运行前，都必须在一个 small deterministic subset 上通过相对 brute-force reference 的 exact-equivalence regression test。

## 执行优先级与 Gatekeeping

规范连接组 fiber 分析必须按 gatekeeping 顺序执行。本节只适用于 HF-only 3m normative connectome fiber-level model，不适用于 direct voxel models。

当前可执行 branch 家族：

```text
primary:
  peak_efield_tau800_primary

sensitivity:
  peak_efield_tau1500_sensitivity
  top1500_top500_sensitivity
  ossdbs_activation_sensitivity

control:
  plain_connected_streamline_control
```

当前 connectome 角色：

```text
PPMI 85 (Ewert 2017)          observed figure-grade robustness
MGH-USC HCP 32 (Horn 2017)    observed figure-grade robustness
dTOR-985 Full (Elias 2024)    primary analysis
```

当前文档版本是唯一可执行规格：

```text
tau_primary = 800 V/m
tau_sensitivity = 1500 V/m
Coverage_tau(l) = sum_i I[X_HF_i(l) > tau]
F_candidate_tau = {l: Coverage_tau(l) >= 5}
```

任何历史 `cov3` 或 `EFieldCoverage>=3` 规则均不是当前可执行规格，除非模型文档再次被显式修订。OLS ANCOVA 仍是未来可选补充估计器，本轮不执行。FDR、labels、density maps、q-thresholded maps 和 display fibers 只用于 QC/display，不定义 `F+`、`F-` 或 `NetFiberScore`。

### Round 0: Version, Branch, Input, And Manifest Freeze

目的：确保后续所有输出都对应同一个锁定文档版本和同一个锁定参数集。

只运行检查，不运行统计模型：

```text
lock document version
lock scale list
lock connectome list
lock branch list
lock tau / coverage / score / validation parameters
lock random seed = 42
check output root writability
check e-field path manifest
check clinical table ID join
check scale direction
check PPMI / MGH / dTOR data.mat readability
check ea_flip_lr_nonlinear availability
check OSS conda env availability, without running OSS
```

写出：

```text
run_master_manifest.json
scale_manifest.csv
connectome_manifest.csv
branch_manifest.csv
efield_input_manifest.csv
clinical_join_manifest.csv
environment_manifest.json
```

进入 Round 1 的条件：

```text
document version is unique
branch list is unique
tau800 / tau1500 / Coverage>=5 are locked
subject_id order is locked
Y_post / Y_base join by ID
scale direction is defined
all required e-field paths exist and are unique by subject/side/condition
PPMI / MGH / dTOR data.mat are readable
output root is writable
seed = 42 is recorded
```

若失败，停止在 sidecar generation 或 LOOCV 之前。

### Round 1: Sidecar Cache And Exact-Equivalence Regression Test

目的：在正式统计之前验证优化实现与 brute-force reference 精确等价。

运行：

```text
PPMI / MGH sidecars:
  X_float32_fiber_major.npy
  S800_bool.npy
  S1500_bool.npy
  fiber_id.npy
  candidate_fiber_metadata.json

dTOR chunked sidecars:
  chunks/X_float32_fiber_major_chunk-*.npy
  chunks/S800_bool_chunk-*.npy
  chunks/S1500_bool_chunk-*.npy
  chunks/fiber_id_chunk-*.npy
  fiber_chunk_manifest.json
  candidate_fiber_metadata.json

coverage / candidate cache:
  Coverage_tau800_all
  Coverage_tau1500_all
  F_candidate_tau800_full
  F_candidate_tau1500_full
  fold-specific candidate masks by subtraction
  candidate_tau800_union_of_folds
  candidate_tau1500_union_of_folds
```

在小型 deterministic subset 上运行 exact-equivalence test：

```text
n_fiber_subset = 1000 to 10000
B_perm = 20
B_boot = 20
seed = 42
```

比较 optimized 与 brute-force 的以下结果：

```text
fold-specific F_candidate_tau
rho_HF(l)
M_HF(l)
F+
F-
SweetPeak5
SourPeak5
NetFiberScore
LOOCV held-out predictions
LOOCV Spearman rho
small permutation null statistics
small bootstrap finite-count summaries
NaN / degenerate fiber locations
```

进入 Round 2 的条件：

```text
subject order exactly matches
fiber_id order exactly matches
S800 / S1500 coverage exactly matches brute-force
fold-specific candidate masks exactly match
F+ / F- exactly match
NaN / degenerate locations exactly match
float outputs match within predefined float64 tolerance
small plus-one p value matches
dTOR chunked IO has no memory error
optimized_equivalence_test_passed = true
```

若失败，先修复 sidecar、coverage、rank、top-k tie policy 或 dTOR chunking。

### Round 2: Primary Observed Run, Total Scale

目的：先运行成本最低的 observed primary branch，并检查模型是否非退化。

运行：

```text
scale = MDS-UPDRS III score
branch = peak_efield_tau800_primary
connectome order = PPMI observed -> MGH observed -> dTOR observed
```

每个 connectome 计算：

```text
full-sample rho_HF / M_HF
F+ top 1%
F- top 0.5%
SweetPeak5
SourPeak5
NetFiberScore
LOOCV prediction
covariate-only baseline comparison
basic mapping QC
```

优先写出 numeric core outputs：

```text
normative_HF_fiber_weights.csv
normative_HF_fiber_scores.csv
normative_HF_fiber_loocv_predictions.csv
normative_HF_fiber_mapping_qc.json
normative_HF_fiber_generation_manifest.json
```

`.tck` display、density maps、endpoint labels、FDR maps、q-thresholded maps 和 label enrichment 延后到 numeric QC 通过后生成。

进入 Round 3 的条件：

```text
at least dTOR primary observed LOOCV completes
each LOOCV fold has non-empty F_candidate_tau800
rho_HF is not all NaN
NetFiberScore has nonzero variance
held-out prediction is not constant
final model is fit
LOOCV Spearman / Pearson / MAE / RMSE / Q2 are finite
mapping_qc.json has no fatal error
```

软警告：

```text
dTOR observed looks technically unstable
PPMI/MGH and dTOR have completely unexplained direction conflict
Q2 is extremely worse than baseline-only
```

若失败，先修复 tau800/Coverage>=5/e-field sampling、exposure variance、rank ties、top-k reducer、dTOR chunking、fiber ids 或 sidecar alignment，再运行敏感性或 formal branches。

### Round 3: Primary Observed Run, Axial Scale

目的：复用 exposure sidecars，覆盖第二个默认 first-pass scale。

运行：

```text
scale = MDS-UPDRS III axial score
branch = peak_efield_tau800_primary
connectome order = PPMI observed -> MGH observed -> dTOR observed
```

运行与 Round 2 相同的 observed outputs。

进入 Round 4 的条件：

```text
axial Y_post / Y_base join succeeds
valid subjects match sidecar subject order, or a legal subject-subset view exists
candidate masks are non-empty
NetFiberScore is not constant
LOOCV prediction is fit
```

如果 axial 缺失、低方差或技术退化，将其标记为 scale-specific failed/not interpretable。Total score 可以继续。如果 total 和 axial 都失败，则停止主线。

### Round 4: Plain Connected-Streamline Control

目的：检验 outcome-filtered fiber model 是否只是 stimulation burden、lead placement 或 connectome density 的反映。

对通过 observed gates 的 scales/connectomes 运行：

```text
branch = plain_connected_streamline_control
Touched_i(l) = I[X_HF_i(l) > tau]
PlainTouchedCount_i
PlainExposureSum_i
PlainExposureTop5_i
```

比较：

```text
Y_post ~ Y_base
Y_post ~ PlainExposureTop5 + Y_base
Y_post ~ NetFiberScore + Y_base
Y_post ~ NetFiberScore + PlainExposureTop5 + Y_base
```

写出：

```text
normative_HF_plain_touched_summary.csv
normative_HF_plain_connected_model_comparison.csv
```

延后生成：

```text
normative_HF_plain_touched_fibers.tck
normative_HF_plain_touched_density_map.nii.gz
```

进入 Round 5 的条件：

```text
PlainExposureTop5 is computable
plain model is fit
joint model is not singular
NetFiberScore and PlainExposureTop5 are not perfectly collinear
```

推荐 collinearity flags：

```text
|corr(NetFiberScore, PlainExposureTop5)| < 0.85 = ideal
0.85 to 0.95 = high collinearity warning
>= 0.95 = severe collinearity warning
```

如果 plain control 完全解释 primary branch，主分支仍可作为 minimal formal report 继续，但解释降级为 stimulation burden / placement-associated，并且不推荐继续 OSS/jitter。

### Round 5: dTOR Primary Smoke Permutation And Bootstrap

目的：在正式 `B=10000` 前测试 full-process resampling。

只运行：

```text
connectome = dTOR
branch = peak_efield_tau800_primary
scales = scales that passed Round 2/3
Freedman-Lane smoke permutation B=1000
subject-level smoke bootstrap B=1000
seed = 42
```

每次 permutation 必须重跑完整 LOOCV workflow：

```text
fold-specific candidate
rho_HF
M_HF
F+ / F-
SweetPeak5 / SourPeak5
NetFiberScore
held-out prediction
LOOCV Spearman
```

写出：

```text
smoke_permutation_summary.csv
smoke_bootstrap_qc_summary.csv
runtime_profile update
empty_fold_summary
degenerate_fiber_summary
bootstrap_finite_count_summary
```

进入 Round 6 的条件：

```text
B=1000 permutation completes
B=1000 bootstrap completes
plus-one p is computable
bootstrap finite count distribution is interpretable
there are not many empty F_candidate folds
there are not many all-NaN / degenerate maps
runtime profile indicates B=10000 is feasible
```

不要把 smoke `p < 0.05` 作为硬 gate。如果 smoke 技术失败，则停止并修复 resampling、chunking、top-k 或 rank cache。如果 smoke 技术通过但结果完全退化，可按预设 futility 停止 formal，或只对 total scale 运行 formal。

### Round 6: Cheap Observed Sensitivity

目的：在 formal heavy computation 之前，检查 primary result 是否完全依赖 tau800 或 selected-fiber 规则。

运行：

```text
branches:
  peak_efield_tau1500_sensitivity
  top1500_top500_sensitivity

connectomes:
  PPMI
  MGH
  dTOR
```

运行：

```text
full-sample map
LOOCV prediction
scores
selected fiber summary
mapping QC
```

不运行：

```text
formal B=10000 permutation
formal bootstrap
OSS
jitter
```

写出：

```text
normative_HF_fiber_weights.csv
normative_HF_fiber_scores.csv
normative_HF_fiber_loocv_predictions.csv
normative_HF_fiber_mapping_qc.json
normative_HF_fiber_top_percentile_sweep_summary.csv
```

进入 Round 7 的条件：

```text
tau1500 branch completes, or records candidate-empty / threshold-too-strict
top1500/top500 branch completes
LOOCV outputs are finite
mapping QC is interpretable
```

软 gate：

```text
tau800 and tau1500 are directionally consistent, or differences are explained by sparse coverage
top1500/top500 does not fully reverse the top1%/top0.5% mainline
dTOR and PPMI/MGH have directionally or anatomically interpretable consistency
```

如果 tau1500 为空，记录 high-threshold sensitivity empty；这不是技术失败。如果 top1500/top500 完全反转主线，则标记结果依赖 top-k，并降低解释强度。

### Round 7: dTOR Primary Formal Permutation And Bootstrap

目的：生成当前文档的核心统计证据。

只运行：

```text
connectome = dTOR
branch = peak_efield_tau800_primary
scales = scales that passed smoke and sensitivity hard gates
```

推荐顺序：

```text
formal permutation B=10000
formal bootstrap B=10000
seed = 42
```

Permutation：

```text
primary statistic = LOOCV Spearman rho
p = plus-one two-sided
```

Bootstrap：

```text
bootstrap SE
bootstrap selection frequency
bootstrap sign stability
finite-count summaries
```

写出：

```text
normative_HF_fiber_permutation_summary.csv
normative_HF_fiber_bootstrap_se.csv
normative_HF_fiber_bootstrap_selection_frequency.csv
normative_HF_fiber_bootstrap_sign_stability.csv
normative_HF_fiber_fold_selection_frequency.csv
normative_HF_fiber_fold_sign_stability.csv
normative_HF_fiber_stability_density_map.nii.gz
```

进入 Round 8 的条件：

```text
B=10000 permutation completes
B=10000 bootstrap completes
all block checkpoints are complete
plus-one p is computable
bootstrap finite counts are interpretable
fold selection frequency is computable
fold sign stability is computable
manifest records resampling_status = formal_complete
```

如果 formal 技术失败，不运行 OSS、jitter 或 final display。如果 formal 完成但结果为阴性，只进入 minimal display/report，不把 OSS/jitter 用作机制强化证据。

### Round 8: OSS-DBS Activation Sensitivity

目的：检验 peak E-field fiber profile 在 pathway/axon activation 变量下是否仍可解释。OSS 是敏感性分析，不是 primary。

运行：

```text
oss_model_set = primary_locked
axon_model
axon_diameter_um
n_nodes
waveform
frequency_Hz
pulse_width_us
amplitude
tissue_model
conductivity_model
activation_output
oss_parameter_manifest.json
```

OSS candidate rule：

```text
inherit F_candidate_tau800 from peak E-field branch
do not redefine candidates by OSS activation
```

生成：

```text
X_oss_float32_fiber_major.npy
PlainOSSActivated_bool.npy
oss_activation_sidecar_metadata.json
```

运行顺序：

```text
PPMI / ossdbs_activation_sensitivity / observed LOOCV
MGH / ossdbs_activation_sensitivity / observed LOOCV
OSS plain activation control

then, only if PPMI/MGH are technically normal:
  dTOR / ossdbs_activation_sensitivity / observed LOOCV
  dTOR / OSS smoke permutation B=1000
  OSS plain activation control
```

写出：

```text
normative_HF_fiber_oss_parameter_manifest.json
normative_HF_fiber_oss_activation_matrix_summary.csv
normative_HF_fiber_oss_loocv_predictions.csv
normative_HF_fiber_oss_permutation_summary.csv
normative_HF_plain_oss_activation_summary.csv
normative_HF_plain_oss_activation_model_comparison.csv
```

进入 Round 9 的条件：

```text
OSS parameter manifest is locked
OSS sidecar candidate fiber ids align with peak branch candidate ids
OSS activation matrix is not all NaN
OSS activation matrix is not all zero
NetFiberScore_OSS has nonzero variance
OSS LOOCV is fit
OSS B=1000 smoke permutation completes
PlainOSSActivationTop5 is computable
OSS joint control model is fit
```

软支持：

```text
corr(NetFiberScore_OSS, NetFiberScore_peak) > 0
F+_OSS and F+_peak have nonzero overlap
selected density / label summary is partly consistent with peak branch
OSS plain activation control does not fully replace NetFiberScore_OSS
```

如果 OSS activation 全零或大部分 tied，标记 OSS failed sensitivity。如果 OSS 与 peak branch 完全不一致，将结果解释为 activation-model dependent。如果 OSS plain activation 完全解释结果，降低机制解释为 activation burden。

### Round 9: dTOR Jitter QC

目的：检验 dTOR primary 的空间稳健性。

只运行：

```text
connectome = dTOR
branch = peak_efield_tau800_primary
scale = scales with completed formal primary result
```

Level 1：

```text
jitter_level_1_selected_display
selected F+ / F- overlap
display fiber robustness
selected density correlation
```

Level 2，仅在 Level 1 技术有效后运行：

```text
jitter_level_2_model_density
candidate fibers or feasible subset
density robustness
model similarity
```

写出：

```text
normative_HF_fiber_jitter_summary.csv
normative_HF_fiber_jitter_model_similarity.csv
normative_HF_fiber_jitter_selected_overlap.csv
normative_HF_fiber_jitter_density_correlation.csv
normative_HF_fiber_jitter_example_density_maps/
```

进入 Round 10 的条件：

```text
jitter outputs are writable
jitter selected overlap is computable
jitter density correlation is computable
model similarity is computable
there are no all-empty jitter runs
```

如果 Level 1 技术失败，不运行 Level 2。如果 Level 1 通过但不稳定，跳过 Level 2 并标记最终结果 spatially sensitive。如果两层都稳定，将其作为 spatial robustness 支持。

### Round 10: Display, FDR, Labels, Density, And Cross-Connectome Summaries

目的：在 numeric branches 锁定后生成展示与解释输出。Display、FDR q-values、q-thresholded density maps 和 label outputs 从不定义 primary model，也不进入 `NetFiberScore`。

对已完成 branches 生成：

```text
top 1% positive fibers
top 0.5% sour fibers
selected-fiber density maps
unthresholded weighted-density maps
positive weighted-density maps
negative weighted-density maps
neglogp density maps
qvalue summary
FDR q05 / q10 display density maps
endpoint labels
cortical endpoint summary
subcortical crossing summary
label enrichment
plain touched-streamline density maps
STN/SNr overlays
cross-connectome summaries
```

写出：

```text
normative_HF_fiber_display_top1_positive.tck
normative_HF_fiber_display_top1_positive.mat
normative_HF_fiber_display_top0p5_sour.tck
normative_HF_fiber_display_top0p5_sour.mat
normative_HF_fiber_density_map.nii.gz
normative_HF_fiber_endpoint_labels.csv
normative_HF_fiber_cortical_endpoint_summary.csv
normative_HF_fiber_subcortical_crossing_summary.csv
normative_HF_fiber_label_enrichment.csv
normative_HF_fiber_unthresholded_weighted_density.nii.gz
normative_HF_fiber_positive_weighted_density.nii.gz
normative_HF_fiber_negative_weighted_density.nii.gz
normative_HF_fiber_neglogp_density.nii.gz
normative_HF_fiber_qvalue_summary.csv
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

完成条件：

```text
display files derive only from finalized numeric outputs
FDR / label / display outputs are not used to select the primary model
label enrichment uses the plain touched-streamline background
PPMI/MGH manifests record observed_only_connectome_robustness
dTOR primary manifest records formal permutation/bootstrap status
OSS manifest records smoke-only status
unrun branches record explicit not-run reason
```

### Recommended Minimal Execution Path

最节省资源但仍覆盖主线和计划敏感性层级的路径是：

```text
1. Round 0-1:
   freeze document/inputs, build sidecars, run equivalence tests

2. Round 2:
   total scale tau800 primary observed
   PPMI -> MGH -> dTOR

3. Round 3:
   axial scale tau800 primary observed
   PPMI -> MGH -> dTOR

4. Round 4:
   plain connected-streamline control

5. Round 5:
   dTOR tau800 primary smoke permutation/bootstrap B=1000

6. Round 6:
   tau1500 sensitivity + top1500/top500 sensitivity observed

7. Round 7:
   dTOR tau800 primary formal permutation/bootstrap B=10000

8. Round 8:
   OSS-DBS sensitivity, PPMI/MGH first, then dTOR, B=1000 only

9. Round 9:
   dTOR jitter QC

10. Round 10:
   display / FDR / labels / cross-connectome summaries
```

核心原则是先证明 `peak_efield_tau800_primary` 在 total 和 axial scales 上技术有效，再用 plain control 区分 outcome-filtered fibers 与 stimulation burden，然后运行 dTOR formal inference，最后才投入 OSS、jitter 和 display-layer outputs。
