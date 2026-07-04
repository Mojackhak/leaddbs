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

OSS-DBS 用 pathway/axon activation 替代 peak E-field exposure：

```text
X_HF_OSS_i(l) = OSS-DBS activation value for fiber l under subject i HF stimulation
```

OSS branch 使用相同 estimator、`NetFiberScore` 和 LOOCV workflow。它只运行 smoke permutation（`B=1000`，seed `42`）。

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
- `fdr_summary_by_scale.csv`: q-threshold counts 以及 percentile-selected fibers 与 q-ranked fibers 的 overlap。
- `normative_HF_fiber_label_enrichment.csv`: selected sweet/sour fibers 相对 plain touched-streamline background 的 enrichment。
- `normative_HF_fiber_mapping_qc.json`: candidate counts、coverage distribution、degenerate fiber counts、empty-fold failures、FDR method、label summaries、chunking parameters、memory use summaries 和 OSS-DBS status。

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
