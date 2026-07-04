# HF-only 3m Normative Connectome Fiber-Level 模型

## 研究问题

全公共 connectome 中哪些被 HF stimulation 直接接触到的 streamlines，在 fiber-level DBS Fiber Filtering 框架下，与更好的 3 个月 HF-only 临床结局相关？

这是 normative connectome **fiber-level** 模型。它采用 reference Nature papers 中的 DBS Fiber Filtering 思路：单条 streamline 是主建模单位；target atlas 只用于解剖标注、分层 QC、display grouping 和解释。该模型不是 target-level seed-target 聚合模型。

频率定义固定为：

```text
HF  = high-frequency stimulation component, frequency_Hz >= 100
ULF = ultra-low-frequency stimulation component, frequency_Hz <= 50
```

## 终点

主终点：

```text
Y_post = raw HF-only 3-month clinical score
```

主协变量：

```text
Y_base = raw preoperative clinical score
```

默认 first-pass scales：

```text
MDS-UPDRS III score (STN, 3 m)
MDS-UPDRS III axial score (STN, 3 m)
```

原始 post 和 baseline 分数来自：

```text
/Users/mojackhu/Research/STNSNr/summary/cohort/subj/subject_effect_origin.xlsx
```

影像与临床通过 `ID` (`SNr003`, `SNr006` 等) 连接。该模型不使用改善率表。量表方向从共享 direction table 读取；未知量表必须在运行前显式指定 higher-is-better 或 lower-is-better。

## 输入

- `3m/STN` 条件下的 HF-only raw `sim-efield`。使用 `sim-efield`，不用 `sim-efieldgauss`，单位为 `V/m`。
- Lead-DBS 公共 dMRI structural connectomes：

  ```text
  PPMI 85 (Ewert 2017)                 smoke
  MGH-USC HCP 32 (Horn 2017)           intermediate
  dTOR-985 Full (Elias 2024)           main
  ```

- 每个 connectome `data.mat` 中的右侧 canonical fibers。
- 通过 `ea_flip_lr_nonlinear` 完成 left/right homology transform。
- 仅用于标注/QC 的 target 和 anatomical atlases：

  ```text
  STNSNr-connected regions
  STN-connected regions
  SNr-connected regions
  Custom STN/SNr overlays
  ```

- OSS-DBS pathway activation sensitivity 使用：

  ```text
  conda env: ossdbsv2
  ```

pipeline 只做最小 e-field availability check：路径存在、subject/side/condition 唯一匹配、文件为 raw `sim-efield`、单位记录为 `V/m`。若 e-field 缺失或多重匹配，则该 scale/run 失败。不自动补算 e-field。

## 特征构建

候选全集是完整公共 connectome，而不是 target-restricted seed-target tracts。

右侧 canonical fiber model：

```text
canonical side = right
E_R_i(l)      = peak raw sim-efield along right canonical fiber l
E_L_to_R_i(l) = peak left e-field after ea_flip_lr_nonlinear along the same right canonical fiber l
X_HF_i(l)     = (E_R_i(l) + E_L_to_R_i(l)) / 2
```

可执行模型使用右侧 canonical streamline feature space。左侧刺激先翻转到右侧 canonical space，再沿同一组右侧 streamline features 采样。因此模型使用双侧 E-field 信息，但 streamline feature set 本身是单侧 canonical，而不是真正的双侧 streamline set。

同侧 alternating HF 子程序先按 voxel-wise maximum 合并后再进行 fiber sampling。Exposure 不按 frequency 或 pulse width 缩放。

主候选规则：

```text
tau_primary = 800 V/m
tau_sensitivity = 1500 V/m
Coverage_tau(l) = sum_i I[X_HF_i(l) > tau]
F_candidate_tau = {l: Coverage_tau(l) >= 5}
```

fiber model 使用与 HF direct voxel model 一致的 coverage 口径：coverage 按患者层面平均后的 right-canonical exposure rows 计数。患者层面的平均暴露 `X_HF_i(l)` 同时用于 candidate definition、fiber-wise association、scoring、LOOCV 和 prediction。

dTOR connectome 很大（`idx` 约 1182 万条 fibers）。所有 dTOR exposure 和 candidate 计算必须 chunked processing。任何一次性把完整 dTOR `fibers` 矩阵载入内存的实现都无效。

## 统计模型

### 主估计器：Baseline-Adjusted Partial Spearman

对每条 candidate fiber `l`，使用 average ranks 的 rank-residual partial Spearman：

```text
rho_HF(l) =
  corr(
    resid(rank(Y_post_i)  ~ rank(Y_base_i)),
    resid(rank(X_HF_i(l)) ~ rank(Y_base_i))
  )
```

若 fiber 的 exposure variance、rank variance 或 residualized exposure variance 为 0，则 `rho_HF(l)=NaN`，并从 scoring 中排除。

Benefit-oriented fiber weight：

```text
M_HF(l) = -rho_HF(l)   for lower-is-better scales
M_HF(l) =  rho_HF(l)   for higher-is-better scales
```

正值 `M_HF(l)` 表示 sweet / benefit-associated。负值 `M_HF(l)` 表示 sour / worse-outcome-associated。

FDR q 值只用于 QC/display，不用于筛选主模型，也不定义 scoring fiber set。

### 可选补充估计器：OLS ANCOVA

OLS ANCOVA 保留为未来可选补充估计器。当前可执行分析不运行该分支，也不生成对应输出文件。

```text
Y_post_i = alpha_l
         + theta_HF(l) * X_HF_i(l)
         + beta_l      * Y_base_i
         + error_i,l
```

如果未来启用，`theta_HF(l)` 将作为 fiber-wise OLS ANCOVA coefficient 报告。当前模型只使用 baseline-adjusted partial Spearman `rho_HF(l)` 估计器进行 map fitting、`NetFiberScore`、LOOCV、permutation、bootstrap 和 display outputs。

### 主患者层面 Score

主 patient-level score 是 net sweet-minus-sour peak score。在每个 full-sample map 或 LOOCV training fold 内，定义 benefit-oriented fiber weights：

```text
M_HF(l) = -rho_HF(l)   for lower-is-better scales
M_HF(l) =  rho_HF(l)   for higher-is-better scales
```

Positive/sweet selected fibers：

```text
F+ = top 1% fibers with largest positive M_HF(l)
```

Negative/sour selected fibers：

```text
F- = top 0.5% fibers with most negative M_HF(l)
```

对每个 patient `i`：

```text
SweetWeighted_i(l) = X_HF_i(l) * M_HF(l),      l in F+
SourWeighted_i(l)  = X_HF_i(l) * [-M_HF(l)],   l in F-

SweetPeak5_i = mean of top 5% largest SweetWeighted_i(l)
SourPeak5_i  = mean of top 5% largest SourWeighted_i(l)

NetFiberScore_i = SweetPeak5_i - SourPeak5_i
```

`F+` 和 `F-` 在 `F_candidate_tau` 内选择，并排除 NaN 或 degenerate fibers。Percentile counts 使用 `ceil(percent * n)`；当对应 positive 或 negative pool 非空时，至少保留 1 条 fiber。

如果 `F+` 为空，则 `SweetPeak5_i = 0`。如果 `F-` 为空，则 `SourPeak5_i = 0`。如果 selected set 非空但某个 patient 对所有 selected fibers 的 exposure 都为 0，则对应 peak score 为 `0`。

该 score 有意贴近 Nature Neuroscience 的 weighted peak Fiber R score，而不是 target-level aggregate。这里采用 peak means 而不是 sums，以增强不同 fold selected fiber set 之间的可比性，并显式惩罚 sour fiber engagement。

此前讨论过的 total fiber exposure score 当前可执行分析不实际计算。

最终预测模型：

```text
Y_post_i = alpha
         + delta * NetFiberScore_i
         + beta  * Y_base_i
         + error_i
```

prediction model 在 raw post-score 尺度上拟合。主验证统计量是 held-out prediction 与 held-out raw outcome 之间的 LOOCV Spearman rho。

## 验证与敏感性分析

- 主验证使用 leave-one-patient-out cross-validation。
- 每个 fold 内重建 `F_candidate_tau`、拟合 `M_HF(l)`、选择 fold-specific `F+` 和 `F-`、计算 training 和 held-out `SweetPeak5`、`SourPeak5` 与 `NetFiberScore`，并且只用 training patients 拟合最终 prediction model。
- 与 covariate-only baseline `Y_post ~ Y_base` 比较。
- 主指标：LOOCV Spearman rho 和 plus-one permutation P value。
- 次要指标：LOOCV Pearson `r`、MAE、RMSE 和 `Q2`。
- Formal Freedman-Lane permutation 使用 `B=10000`、seed `42`，仅限 primary dTOR peak-E-field branch。
- Smoke permutation 使用 `B=1000`、seed `42`。
- Subject-level bootstrap 使用 `B=10000`、seed `42`，仅限 primary dTOR peak-E-field branch。
- 可选 OLS ANCOVA 仅作为未来敏感性分析记录，当前执行不运行。

Reference sensitivities：

```text
1500 V/m candidate threshold sensitivity with Coverage>=5
top 1% positive fibers for display
top 0.5% sour fibers for display
top1500 positive / top500 negative fiber-score sensitivity for PPMI, MGH, and dTOR
OSS-DBS all-candidate sensitivity for PPMI, MGH, and dTOR
jitter_level_1_selected_display for dTOR selected/display fibers
jitter_level_2_model_density for dTOR model-density robustness
plain_connected_streamline_control for PPMI, MGH, and dTOR
```

reference papers 中的 5-fold/10-fold CV 设置只写入 reference checklist。当前 `n=16` 执行不生成这些结果；LOOCV 是可执行验证设计。

PPMI、MGH 和 dTOR 都必须生成 figure-grade observed outputs：full-sample maps、LOOCV predictions、score CSVs、selected sweet/sour fibers、density maps、candidate and coverage summaries 和 label summaries。dTOR 额外承担 formal `B=10000` permutation、`B=10000` bootstrap 和 jitter QC。

## OSS-DBS 敏感性分析

OSS-DBS 在 `ossdbsv2` Conda 环境中运行，并对 PPMI、MGH 和 dTOR 的 all candidate fibers 生成。

OSS branch 用 pathway/axon activation 代替 peak E-field exposure：

```text
X_HF_OSS_i(l) = OSS-DBS activation value for fiber l under subject i HF stimulation
```

OSS branch 使用同样的 fiber-wise estimator、net sweet-minus-sour peak scoring 和 LOOCV prediction workflow。OSS branch 只运行 smoke permutation：

```text
B = 1000
seed = 42
```

OSS branch 不要求 formal `B=10000` permutation/bootstrap。

## 输出

输出根目录：

```text
/Volumes/VAL/STNSNr/summary/normative_connectome_fiber/hf/<connectome_slug>/<scale_slug>/<branch>/
```

Branches：

```text
peak_efield_tau800_primary
peak_efield_tau1500_sensitivity
top1500_top500_sensitivity
ossdbs_activation_sensitivity
plain_connected_streamline_control
```

每个 branch 必需 observed outputs：

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

Primary dTOR peak-E-field branch 额外输出：

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

PPMI 和 MGH observed branches 不要求 formal permutation/bootstrap outputs。其 manifest 记录 `resampling_status = observed_only_connectome_robustness`。

OSS branch 额外输出：

```text
normative_HF_fiber_oss_activation_matrix_summary.csv
normative_HF_fiber_oss_loocv_predictions.csv
normative_HF_fiber_oss_permutation_summary.csv
```

Plain connected-streamline control branch 输出：

```text
normative_HF_plain_touched_fibers.tck
normative_HF_plain_touched_density_map.nii.gz
normative_HF_plain_touched_summary.csv
normative_HF_plain_connected_model_comparison.csv
```

Cross-connectome figure summaries 输出在 HF normative connectome fiber summary root：

```text
connectome_scale_performance_summary.csv
connectome_scale_overlap_summary.csv
connectome_density_correlation_summary.csv
connectome_selected_label_summary.csv
```

`normative_HF_fiber_weights.csv` 至少包括：

```text
connectome
fiber_id
tau_v_per_m
coverage
rho_HF
p_uncorrected
q_fdr
M_HF
direction_class
target_labels_for_qc
is_top1_positive_display
is_top0p5_sour_display
is_top1500_positive
is_top500_negative
```

`fdr_summary_by_scale.csv` 至少包括：

```text
scale
connectome
branch
n_q05_positive
n_q05_negative
n_q10_positive
n_q10_negative
top1_positive_overlap_q_ranked
top0p5_sour_overlap_q_ranked
```

`normative_HF_fiber_scores.csv` 至少包括：

```text
subject_id
score_map_source
connectome
branch
SweetPeak5
SourPeak5
NetFiberScore
n_candidate_fibers
n_sweet_selected_fibers
n_sour_selected_fibers
n_sweet_peak_fibers
n_sour_peak_fibers
is_primary_score
```

`normative_HF_fiber_mapping_qc.json` 记录 candidate counts、coverage distribution、degenerate fiber counts、empty-fold failures、FDR method、target-label summaries、chunking parameters、memory use summaries 和 OSS-DBS status。

`normative_HF_fiber_endpoint_labels.csv` 保存每条 fiber 的 cortical、subcortical 和 STN/SNr territory endpoint/crossing labels。Endpoint labels 只用于 anatomical enrichment、cortical-origin summaries 和 figure annotation，不定义主候选全集或 scoring set。

`normative_HF_fiber_label_enrichment.csv` 将 selected sweet/sour fibers 与 plain touched-streamline background 比较，使 outcome-filtered fibers 可以相对于非 outcome 加权的 stimulation-connectivity density 解释。

### Plain Connected-Streamline Control

Plain control 故意不使用 clinical outcome、`rho_HF(l)`、`M_HF(l)` 或 sweet/sour weights。它只回答 outcome filtering 前 HF stimulation 会触碰到哪些 normative streamlines：

```text
Touched_i(l) = I[X_HF_i(l) > tau]
PlainCoverage(l) = sum_i Touched_i(l)
PlainDensityMap = streamline density of all touched fibers
```

患者层面 plain scores：

```text
PlainTouchedCount_i = sum_l Touched_i(l)
PlainExposureSum_i  = sum_l X_HF_i(l)
PlainExposureTop5_i = mean top 5% X_HF_i(l) among touched fibers
```

模型比较：

```text
Y_post ~ Y_base
Y_post ~ PlainExposureTop5 + Y_base
Y_post ~ NetFiberScore + Y_base
Y_post ~ NetFiberScore + PlainExposureTop5 + Y_base
```

在本 `n=16` 队列中，联合 `NetFiberScore + PlainExposureTop5` 模型只作为 QC，不作为 primary inference。它用于评估 outcome-filtered fiber profile 是否提供超出 stimulation burden、lead placement 和 connectome density 的信息。

## 可视化

Target atlases 只在 fiber 建模之后用于 label 和 summary，不定义主预测变量。

Display outputs：

- 按 `M_HF(l)` 选取 top 1% positive fibers 用于 sweet streamline visualization；
- 按负向 `M_HF(l)` 选取 top 0.5% sour fibers 用于 avoidance/sour visualization；
- selected/display fibers 的 streamline density maps；
- unthresholded weighted-density maps，展示不经 percentile thresholding 的完整 fiber landscape；
- `-log(P)` density maps 和 q-value summaries，用于 statistical-certainty display；
- target-label、cortical endpoint 和 subcortical crossing summary tables，说明 selected fibers 穿过或接触哪些 atlas territories；
- plain touched-streamline density maps，作为非 outcome 加权的 stimulation-connectivity controls；
- STN/SNr 和 STNSNrplus overlays 只作为解剖背景。

任何 display fiber subset 都不是主统计显著性图。FDR q 值和 q-thresholded density maps 用于 QC/display 透明性，但不筛选主模型、不定义 `F+`/`F-`，也不进入 `NetFiberScore`。

## 解释边界

该模型估计 normative fiber-level HF stimulation association。它比 seed-target target-level model 更接近 DBS Fiber Filtering，但仍然使用 population connectome，因此不能证明 patient-specific axonal causality。

模型应解释为：

```text
当 HF stimulation 更强地调制这一 normative streamline profile 时，疗效似乎更好。
```

不应解释为：

```text
每一条显示的 streamline 都是每个患者中的确定因果 tract。
```

主要结论需要依赖 cross-connectome consistency、dTOR 主结果，以及 PPMI/MGH sensitivity results 的透明报告。

## Execution Efficiency

本节定义用于提高 HF normative connectome fiber analysis 项目级计算效率的 implementation-level rules。这些规则只改变 computation scheduling、cache、chunking、vectorization 和 disk writing，不改变 statistical estimands、validation design、output semantics、file naming，也不改变任何 `normative_HF_fiber_*` 输出的解释。

优化实现必须保留上文定义的 logical full-process semantics。LOOCV training folds 仍然各自定义 `F_candidate_tau`、fiber-wise maps、selected `F+`/`F-`、`SweetPeak5`、`SourPeak5`、`NetFiberScore` 和 held-out predictions。Formal Freedman-Lane permutation 与 subject-level bootstrap 对 primary dTOR peak-E-field branch 仍使用 `B=10000` 和 seed `42`。Smoke runs 仍使用 `B=1000`。优化实现可以复用数学上不变的 cached subcomputations，但不得为了提速使用 full-sample ranks、full-sample training masks、approximate ranks、adaptive early stopping、改变 thresholds、改变 estimators、改变 selected-fiber percentages，或降低 formal resampling counts。

### Equivalence Contract

以下量属于 executable statistical definition，必须保持不变：

```text
connectome order = PPMI observed figure-grade, MGH observed figure-grade, dTOR primary
canonical side = right
primary exposure = peak raw sim-efield along each normative fiber
tau_primary = 800 V/m
tau_sensitivity = 1500 V/m
Coverage>=5 counted over patient-level averaged right-canonical exposure rows
LOOCV patient split
primary estimator = baseline-adjusted partial Spearman
primary score = NetFiberScore
F+ = top 1% positive M_HF(l)
F- = top 0.5% most negative M_HF(l)
SweetPeak5/SourPeak5 = mean top 5% patient-specific weighted selected fibers
formal permutation B = 10000 for primary dTOR peak-E-field branch
formal bootstrap B = 10000 for primary dTOR peak-E-field branch
OSS-DBS permutation = smoke only, B = 1000
seed = 42
primary permutation statistic = LOOCV Spearman rho
```

Numerical reductions 尽量使用 `float64`。大型 exposure matrices 可用 `float32` 存储；最终 CSV summaries 必须记录每个阶段使用的 dtype。既有 degenerate-fiber 和 NaN 规则保持不变。

### Connectome Sidecar Cache

Formal runs 必须写出 memmap-friendly fiber-major sidecar files 供 Python postprocessing 使用。PPMI 和 MGH 在可行时可使用单个数组：

```text
X_float32_fiber_major.npy       # shape = fiber x subject, averaged X_HF
S800_bool.npy                   # X_HF > 800 V/m
S1500_bool.npy                  # X_HF > 1500 V/m
fiber_id.npy
candidate_fiber_metadata.json
```

dTOR 必须使用 chunked sidecars。一次性把完整 dTOR `fibers` matrix 或全部 dTOR exposure values 载入内存是无效实现：

```text
chunks/
  X_float32_fiber_major_chunk-000001.npy
  S800_bool_chunk-000001.npy
  S1500_bool_chunk-000001.npy
  fiber_id_chunk-000001.npy
fiber_chunk_manifest.json
candidate_fiber_metadata.json
```

sidecar metadata 必须记录 subject order、fiber order、connectome slug、chunk size、dtype、array shape、memory layout、source connectome path、可用时的 source hash、sidecar creation time、software version，以及该 branch 使用 peak E-field 还是 OSS-DBS activation values。

### Coverage And Fold Candidate Cache

对每个 tau，按 chunk 预计算 suprathreshold indicators 和 coverage：

```text
S_tau(l, i) = I[X_HF_i(l) > tau]
Coverage_tau_all(l) = sum_i S_tau(l, i)
```

对 LOOCV fold `h`，通过 subtraction 得到 training-fold coverage：

```text
Coverage_tau_fold_h(l) =
  Coverage_tau_all(l) - S_tau(l, h)

F_candidate_tau_fold_h =
  {l : Coverage_tau_fold_h(l) >= 5}
```

因此 held-out patient 仍不贡献该 fold-specific candidate set，但 candidate set 通过 chunked vectorized subtraction 计算，而不是重新扫描 streamlines 或 e-field images。

### Vectorized Fiber-Wise Partial Spearman

Primary fiber map 必须使用 chunked vectorized rank-residual partial Spearman kernel。

每个 training fold 的 ranks 必须只在 training set 内计算。LOOCV map fitting、permutation map fitting、bootstrap maps 和 OSS sensitivity 都禁止使用 full-sample ranks。对每个 fiber chunk，使用 vectorized reductions over subjects 计算 residualized ranked exposure、residualized ranked outcome 和 `rho_HF(l)`。零 exposure variance、零 rank variance 或零 residualized exposure variance 的 degenerate fibers 保持既有 NaN 规则，并从 selected-fiber sets 和 scoring 中排除。

### NetFiberScore Computation

direct voxel 的 linear score operator 不得直接复制到该模型。`NetFiberScore` 包含 selected `F+` 和 `F-` 上 patient-specific top-5% peak operations，因此不是简单线性矩阵乘。

对 observed maps 和每个 permutation/bootstrap fold，实现可以缓存 outcome-independent exposure chunks 和 coverage arrays，但必须重新计算 outcome-dependent pieces：

```text
M_HF(l)
F+
F-
SweetWeighted_i(l)
SourWeighted_i(l)
SweetPeak5_i
SourPeak5_i
NetFiberScore_i
```

Peak selection 应通过 streaming top-k reducers over selected fiber chunks 实现。Formal runs 不得在 streaming top-k 足够时把所有 selected dTOR fibers materialize 到内存中。

### Permutation And Bootstrap Efficiency

Freedman-Lane permutation 可以复用 fold-specific exposure sidecars、`S_tau` arrays、coverage subtraction、subject order、baseline ranks 和 chunk metadata。对每个 reconstructed `Y*`，仍必须重新拟合 fiber-wise association、重新选择 `F+`/`F-`、重新计算 `NetFiberScore`，并重新运行 LOOCV prediction statistic。

Subject-level bootstrap 仍是 primary dTOR peak-E-field branch 的 full-process map stability analysis。对每个 bootstrap resample，用 subject counts 表示采样患者：

```text
w_i = number of times subject i appears in the bootstrap sample

Coverage_tau_boot(l) =
  sum_i w_i * I[X_HF_i(l) > tau]
```

`Y_post`、`Y_base` 和 `X_HF(l)` 的 ranks 必须在 expanded bootstrap resample 内计算，或使用完全等价的 weighted-resample representation。禁止使用 full-sample ranks。Bootstrap summaries 应用 streaming finite-count updates 累积，不得保存 `B=10000` 个完整 fiber-weight tables。

### OSS-DBS Sensitivity Efficiency

OSS-DBS sensitivity 使用相同的 sidecar 和 chunking rules，只是把 peak E-field exposure 替换为 pathway/axon activation values。OSS activation matrices 应写为 all-candidate、connectome-specific sidecars，并带 chunk manifests。OSS runs 只生成 LOOCV 和 smoke permutation：

```text
B = 1000
seed = 42
```

Formal `B=10000` permutation/bootstrap 仍仅限 primary dTOR peak-E-field branch。

### Intermediate File Policy

Formal loops 不得写出 per-fold、per-permutation 或 per-bootstrap 的 full fiber-weight tables，除非显式开启 debug flag。dTOR display outputs 应限制为 selected/display fibers 和 density maps：

```text
top 1% positive fibers
top 0.5% sour fibers
top1500 positive / top500 negative sensitivity fibers
downsampled representative unthresholded landscape fibers when explicitly requested
streamline density maps
plain touched-streamline density maps
FDR-thresholded density maps
target-label QC summaries
```

workers 不得并发 append 同一个 CSV 或 JSON。workers 应返回 structured block results 给主进程，由主进程原子写出最终 CSV/JSON outputs。

### Runtime Profile

`normative_HF_fiber_generation_manifest.json` 应包含 runtime profile：

```json
{
  "runtime_profile": {
    "connectome_slug": null,
    "branch": null,
    "preprocess_s": null,
    "sidecar_write_s": null,
    "load_sidecar_s": null,
    "observed_loocv_s": null,
    "permutation_s": null,
    "bootstrap_s": null,
    "oss_activation_s": null,
    "display_qc_s": null,
    "n_fibers_total": null,
    "n_fibers_candidate_tau800_mean": null,
    "n_fibers_candidate_tau800_min": null,
    "n_fibers_candidate_tau800_max": null,
    "coverage_tau800_summary": null,
    "coverage_tau1500_summary": null,
    "n_chunks": null,
    "chunk_size": null,
    "python_jobs": null,
    "blas_threads": null,
    "fiber_major_sidecars": [],
    "streaming_topk_enabled": null,
    "bootstrap_finite_count_summary": null
  }
}
```

### Equivalence And Regression Tests

Formal runs 前应包含小规模 deterministic equivalence test。

对 small fiber subset 和 small resampling count：

```text
B_perm = 20
B_boot = 20
n_fiber_subset = 1000 to 10000
seed = 42
```

比较 brute-force 和 optimized implementations：

```text
fold-specific F_candidate_tau
Coverage_tau
partial Spearman rho_HF(l)
benefit-oriented M_HF(l)
F+ and F-
SweetPeak5
SourPeak5
NetFiberScore
LOOCV held-out predictions
LOOCV Spearman rho
permutation null statistics
bootstrap finite-count summaries
```

Required tolerances：

```text
exact equality for subject IDs, fiber IDs, split indices, F+, and F-
near equality for float outputs under float64 reductions
same NaN/degenerate fiber locations
same plus-one p value for the deterministic small test
```

最终 run manifest 应记录 optimized equivalence test 是否通过。
