# HF-adjusted ULF-only Add-On Gain 直接 Voxel-Level 模型

## 研究问题

加入 ULF 刺激后，哪些 ULF-only voxel 的 exposure 与额外临床获益相关，并且这种关联已经校正患者的 HF 临床状态和模型预测的 HF 疗效变化？

这是一个局部 ULF-only add-on sweet-spot 模型。主问题不再定义为解剖 SNr 效应。STN/SNr 及周围区域被视为一个 stimulation territory，HF 和 ULF components 按刺激频率和 exposure overlap 区分。

频率定义：

```text
HF  = high-frequency stimulation component, frequency_Hz >= 100
ULF = ultra-low-frequency stimulation component, frequency_Hz <= 50
```

同时被 HF 和 ULF 激活的 voxels 归入 HF adjustment model，并从主 ULF-only predictor 中排除。

## 终点

两个 endpoint families 分开建模。

Chronic endpoint：

```text
Y_post = raw HF+ULF 3-month clinical score
Y_HF   = raw HF-only 3-month clinical score for the same scale/domain
DeltaHFScore = predicted change in HF efficacy between HF+ULF programming and HF-only programming
```

Immediate endpoint：

```text
Y_post = raw HF+ULF immediate clinical score
Y_HF   = raw HF-only 3-month clinical score for the corresponding motor scale/domain
DeltaHFScore = predicted change in HF efficacy between HF+ULF immediate programming and HF-only programming
```

主要 estimand：

```text
HF-adjusted ULF-only add-on gain
```

默认 first-pass endpoints：

```text
MDS-UPDRS III total chronic HF+ULF 3-month score
MDS-UPDRS III total immediate HF+ULF score, if available
```

Raw scores 来源于 HF direct voxel model 使用的原始临床表：

```text
/Users/mojackhu/Research/STNSNr/summary/cohort/subj/subject_effect_origin.xlsx
```

Clinical rows 通过 `ID`（`SNr003`、`SNr006` 等）与 imaging 数据连接。Improvement-rate tables 不用于该模型。Scale direction 读取与 HF direct voxel model 相同的 internal direction table；未知量表必须在运行前显式指定 higher-is-better 或 lower-is-better。

## 输入

- Stimulation parameter audit source：

  ```text
  /Users/mojackhu/Research/STNSNr/summary/cohort/subj/followup_stimulation.xlsx
  sheet = Contact Parameters
  ```

  该 workbook 用于审计 HF 和 ULF component identity、frequencies、pulse widths、amplitudes、sides、contacts 和 phase labels。Existing e-fields 在既往 manual/clinical QC 后视为 accepted inputs。当前 ULF direct voxel analysis 不自动创建 missing e-fields。

- pre-ULF HF phase 的 HF-only E-field per side，用于计算 reference HF score。

- HF+ULF programming 中的 HF component E-field 和 ULF component E-field per side，用于计算 `DeltaHFScore` 和 ULF-only predictor。

- 与模型类型匹配的 direct voxel-level HF efficacy map：

  ```text
  DeltaHFScore source = HF direct voxel model
  ```

  ULF direct voxel model 不得使用 normative fiber HF score 作为 HF adjustment。Voxel-level ULF models 必须用 voxel-level HF models 进行调整。

- Canonical reference mask：

  ```text
  templates/space/MNI152NLin2009bAsym/brainmask.nii.gz > 0
  ```

  Candidate voxels 限制在右半球 voxel centers，MNI world coordinate `x > 0`。

- Anatomical overlay masks：

  ```text
  templates/space/MNI152NLin2009bAsym/atlases/STNSNr-connected regions/{rh,lh}/STNSNrplus.nii.gz
  ```

  `STNSNrplus` 仅用于 anatomical overlay、territory coverage 和 QC background。它不与 `Omega_ULF_tau` 相交，也不是 statistical candidate mask。

- Left/right homology transform：

  ```text
  helpers/ea_flip_lr_nonlinear.m
  templates/space/MNI152NLin2009bAsym/fliplr/{Composite,InverseComposite}.nii.gz
  ```

  本模型所有左右翻转都使用 `ea_flip_lr_nonlinear` 和 Lead-DBS default interpolation behavior。

最低 e-field 检查：必需路径存在，subject/side/component/phase 唯一匹配，文件是 raw `sim-efield`，单位记录为 `V/m`。缺失或多重匹配 e-fields 会使 endpoint/run 失败。Subjects 不 silent exclusion，missing e-fields 不自动创建。

## 特征构建

使用 right-hemisphere MNI brainmask grid 作为 canonical statistical grid。左侧 HF 和 ULF component fields 使用 `ea_flip_lr_nonlinear` 翻转到右侧空间。右侧 fields 采样到同一 right canonical grid。

对每个 subject、side 和 endpoint phase：

```text
E_HF_R_i(v)       = right HF component e-field
E_HF_L_to_R_i(v)  = left HF component e-field flipped to right canonical space
E_ULF_R_i(v)      = right ULF component e-field
E_ULF_L_to_R_i(v) = left ULF component e-field flipped to right canonical space
```

Same-side alternating subprograms 按 component 处理：

```text
E_HF_side_i(v)  = voxel-wise maximum over same-side HF subprograms
E_ULF_side_i(v) = voxel-wise maximum over same-side ULF subprograms
```

Interleaving 不建模为 simultaneous double-cathode stimulation。如果某个 clinical condition 包含 synchronous mixed HF+ULF programming，并通过只开启分配给某个 frequency component 的 contacts 来生成 component-specific fields，manifest 必须将这些 fields 标记为 component-specific proxies。

患者级双侧 component exposure：

```text
E_HF_component_i(v) =
  (E_HF_R_i(v) + E_HF_L_to_R_i(v)) / 2

E_ULF_component_i(v) =
  (E_ULF_R_i(v) + E_ULF_L_to_R_i(v)) / 2
```

Frequency 只用于将 component 分类为 HF 或 ULF。主 direct voxel analysis 中 exposure 不按 frequency 或 pulse width 缩放。

Sparse candidate construction：

```text
candidate_threshold = 180 V/m
Candidate_ULF(v) = any valid subject has E_ULF_component_i(v) > 180 V/m
```

对每个 tau：

```text
tau_primary = 200 V/m
tau_sensitivity = {180, 220} V/m

HF_active_i(v)  = E_HF_component_i(v)  > tau
ULF_active_i(v) = E_ULF_component_i(v) > tau

X_ULF_only_i(v) =
  E_ULF_component_i(v), if ULF_active_i(v) and not HF_active_i(v)
  0,                   otherwise

Coverage_ULF_tau(v) = sum_i I[X_ULF_only_i(v) > tau]
Omega_ULF_tau = {v in Candidate_ULF : Coverage_ULF_tau(v) >= 5}
```

`Omega_ULF_tau` 内使用 continuous `X_ULF_only_i(v)` 建模；`tau` 只用于定义 component activity、HF-overlap exclusion、coverage 和 QC。同时被 HF 和 ULF 激活的 voxels 从 ULF predictor 中排除，并在下列文件中表示：

```text
direct_voxel_ULF_only_HF_overlap_exclusion_mask.nii.gz
```

Coverage masks、voxel maps、ULF scores、`DeltaHFScore` 和 validation predictions 都在每个 LOOCV training fold 内计算。Held-out patient 不参与该 fold 的 `Omega_ULF_tau`、ULF voxel map 或 HF adjustment map。

### DeltaHFScore

模型匹配的 HF adjustment 来自 HF direct voxel model：

```text
V_HF_score = Omega_HF_tau intersect valid M_HF voxels
n_valid_HF_score_voxels = |V_HF_score|

S_HF_voxel(E)_i =
  sum_{u in V_HF_score} E_i(u) * M_HF(u)
  / n_valid_HF_score_voxels

DeltaHFScore_3m_i =
  S_HF_voxel(E_HF_component, HF+ULF 3m)_i
  - S_HF_voxel(E_HF_only, HF-only 3m)_i

DeltaHFScore_immediate_i =
  S_HF_voxel(E_HF_component, HF+ULF immediate)_i
  - S_HF_voxel(E_HF_only, HF-only 3m)_i
```

`DeltaHFScore` 在建模前不赋予固定生物学缩放系数。它可在 training folds 内 z-score 以改善数值稳定性；其 regression coefficient 估计它与 outcome 的关联。在 LOOCV 中，held-out patient 的 `DeltaHFScore` 必须由 training-fold HF map 计算，不能使用 full-sample HF map。

## 统计模型

### 主估计器：Covariate-Adjusted Partial Spearman

对每个 endpoint 和 voxel `v`，使用 rank-residual partial Spearman，并对 ties 使用 average ranks：

```text
rho_ULF(v) =
  corr(
    resid(rank(Y_post_i)          ~ rank(Y_HF_i) + rank(DeltaHFScore_i)),
    resid(rank(X_ULF_only_i(v))   ~ rank(Y_HF_i) + rank(DeltaHFScore_i))
  )
```

如果 voxel 的 ULF-only exposure variance、rank variance 或 residualized exposure variance 为 0，则设为 `rho_ULF(v)=NaN`，并从 `ULFScore_mean_main` 中排除。

Benefit-oriented map：

```text
M_ULF(v) = -rho_ULF(v)   for lower-is-better scales
M_ULF(v) =  rho_ULF(v)   for higher-is-better scales
```

正值 `M_ULF(v)` 一律表示 ULF-only sweet 或 benefit-associated。负值 `M_ULF(v)` 表示 ULF-only sour 或 worse-outcome-associated。

### DeltaHFScore Sensitivity Estimator

主要 sensitivity estimator 移除 `DeltaHFScore`，但保留当前 HF clinical state：

```text
rho_ULF_noDeltaHF(v) =
  corr(
    resid(rank(Y_post_i)        ~ rank(Y_HF_i)),
    resid(rank(X_ULF_only_i(v)) ~ rank(Y_HF_i))
  )
```

该分支用于报告 ULF map 对 model-derived HF adjustment 的依赖程度。它不是 primary branch。

### 可选补充估计器：OLS ANCOVA

OLS ANCOVA 保留为未来可选补充估计器。当前可执行分析不运行该分支，也不生成对应输出文件。

```text
Y_post_i = alpha_v
         + theta_ULF(v) * X_ULF_only_i(v)
         + beta_v      * Y_HF_i
         + gamma_v     * DeltaHFScore_i
         + error_i,v
```

如果未来启用，OLS estimator 应在 `ols_ancova/` estimator directory 下生成同一 output family。其 `direct_voxel_ULF_only_coef.nii.gz` 存储 `theta_ULF(v)`，而主 `partial_spearman/` coefficient file 存储 `rho_ULF(v)`。

### 患者层面 Score

主患者级 ULF-only sweet-spot score：

```text
V_score = Omega_ULF_tau intersect valid M_ULF voxels
n_valid_score_voxels = |V_score|

ULFScore_mean_main_i =
  sum_{v in V_score} X_ULF_only_i(v) * M_ULF(v)
  / n_valid_score_voxels
```

这是主 ULF-only prediction score。它是在对应 full-sample map 或 LOOCV training fold 的固定 scoring voxel set 上，按 voxel 数归一化的 voxel 相关性加权平均 ULF-only exposure。它不除以 `sum(X)`，也不乘 voxel volume。若 `V_score` 为空，则该 branch/fold 以 QC failure 停止，不生成 score。若某 subject/fold 在非空有效 scoring voxel set 内没有 ULF-only exposure，则 `ULFScore_mean_main_i` 记为 `0`。

Final prediction model：

```text
Y_post_i = alpha
         + delta * ULFScore_mean_main_i
         + beta  * Y_HF_i
         + gamma * DeltaHFScore_i
         + error_i
```

Covariate-only baseline：

```text
Y_post_i = alpha
         + beta  * Y_HF_i
         + gamma * DeltaHFScore_i
         + error_i
```

No-DeltaHF sensitivity baseline：

```text
Y_post_i = alpha
         + beta * Y_HF_i
         + error_i
```

Prediction model 在 raw post-score 尺度上拟合。主验证统计量仍为 rank-based LOOCV Spearman rho。

Missing-data rule：missing `Y_post`、missing `Y_HF`、missing `DeltaHFScore` 或 e-field availability failure 会在 QC 后使 endpoint/run 失败。未来 configurable endpoints 若有效样本量低于 12，则跳过该 endpoint。

## 验证

- Chronic 3-month 和 immediate endpoints 分开建模。
- 使用 leave-one-patient-out cross-validation，不做 inner hyperparameter tuning。
- 每个 outer fold 内，先重建计算 `DeltaHFScore` 所需的 HF direct voxel map，计算 fold-specific `DeltaHFScore`，再重建 `Omega_ULF_tau`、拟合 ULF-only voxel map、计算 training 和 held-out `ULFScore_mean_main`，并且只用 training patients 拟合 final prediction model。
- 与 covariate-only baseline `Y_post ~ Y_HF + DeltaHFScore` 比较。
- 报告 no-DeltaHF sensitivity model `Y_post ~ ULFScore_mean_main + Y_HF`。
- 主验证统计量：held-out predictions 与 held-out raw outcomes 的 LOOCV Spearman rho。
- Secondary metrics：LOOCV Pearson `r`、MAE、RMSE 和 original raw outcome scale 上的 `Q2`。
- `Q2` 相对 covariate-only baseline 定义：

  ```text
  Q2 = 1 - SSE_ULFScore_model / SSE_covariate_only
  ```

- Patient-level Freedman-Lane permutation 在正式主 ULF branch 中使用 `B=10000` 和随机种子 `42`。Smoke/exploratory 运行使用 `B=1000`。Formal permutation 只对 primary `tau200/partial_spearman` chronic endpoint branch 运行，除非 immediate endpoint 被明确提升为 co-primary。
- 每次 permutation 先拟合 nuisance model `Y_post ~ Y_HF + DeltaHFScore`，置换 nuisance residuals，重构 `Y*`，然后完整重跑 LOOCV pipeline，包括 HF adjustment、ULF coverage、ULF map、`ULFScore_mean_main` 和 prediction。主 permutation statistic 为 LOOCV Spearman rho。
- Permutation p value 使用 plus-one two-sided：

  ```text
  p = (1 + count(|stat_perm| >= |stat_obs|)) / (B + 1)
  ```

- Subject-level bootstrap 对 formal primary branch 使用 `B=10000` 和 seed `42`。Smoke/exploratory 运行使用 `B=1000`。每次 bootstrap resample 都重跑完整 map-building process，包括 `DeltaHFScore`、`Omega_ULF_tau`；`direct_voxel_ULF_only_bootstrap_se.nii.gz` 存储 estimator map 的 voxel-wise standard deviation。

对非主已执行分支（`tau180/partial_spearman`、`tau220/partial_spearman`、no-DeltaHF sensitivity，以及未设为 co-primary 的 immediate endpoints），仍运行 LOOCV，但不生成 formal permutation/bootstrap outputs。对应 manifests 和 QC JSON 必须记录：

```text
resampling_status = not_run_nonprimary
resampling_reason = formal resampling restricted to primary tau200/partial_spearman chronic branch
```

## 执行结构

后续代码实现应分离 image preprocessing 和 statistical postprocessing。

MATLAB/Lead-DBS preprocessing：

- discover and availability-check required HF-only, HF-component, and ULF-component e-fields；
- 按 frequency 分类 components（`HF >= 100 Hz`，`ULF <= 50 Hz`）；
- same-side same-frequency alternating subprograms 按 voxel-wise maximum 合并；
- 所有左右翻转调用 `ea_flip_lr_nonlinear`；
- 计算 left/right flip deformation audit metrics，并只记录 warning，不自动排除；
- 将 HF 和 ULF component exposure 采样到 right-hemisphere MNI brainmask candidate grid；
- 写出 MAT v7 design matrix 和可选 compressed NPZ mirror。

Required design matrix schema：

- `X_ULF_only(subject x candidate_voxel)` continuous ULF-only exposure；
- `E_HF_component(subject x candidate_voxel)` continuous HF component exposure，用于 overlap exclusion 和 `DeltaHFScore`；
- candidate voxel `ijk` and MNI `xyz_mm`；
- NIfTI affine/header reference；
- `subject_id`、source e-field paths、side metadata、component labels、frequency labels 和 clinical raw values；
- tau/candidate metadata、HF-overlap exclusion metadata、flip metadata 和 jitter metadata placeholders。

Python postprocessing 在 `leaddbs` Conda environment 中运行：

- read the MAT v7 design matrix or optional NPZ mirror；
- 在每个 fold 内构建 `Omega_ULF_tau`；
- 计算 fold-specific HF direct voxel maps 和 `DeltaHFScore`；
- 运行 partial Spearman map fitting、LOOCV、permutation、bootstrap 和 display output generation；
- 写出 CSV、JSON、NIfTI maps 和 figures。

默认并行与 HF direct voxel model 保持一致：

```text
MATLAB preprocessing workers: 8
Python jobs: 14
seed: 42
```

## 下游可视化和输出

Output root：

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/<tau_slug>/partial_spearman/
```

Primary branch：

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau200/partial_spearman/
```

Sensitivity branches：

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau180/partial_spearman/
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau220/partial_spearman/
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau200/partial_spearman_no_delta_hf/
```

Required outputs：

```text
direct_voxel_ULF_only_coverage.nii.gz
direct_voxel_ULF_only_coef.nii.gz
direct_voxel_ULF_only_sweet_sour.nii.gz
direct_voxel_ULF_only_stability.nii.gz
direct_voxel_ULF_only_bootstrap_se.nii.gz
direct_voxel_ULF_only_scores.csv
direct_voxel_ULF_only_loocv_predictions.csv
direct_voxel_ULF_only_permutation_summary.csv
direct_voxel_ULF_only_HF_overlap_exclusion_mask.nii.gz
direct_voxel_ULF_only_mapping_qc.json
direct_voxel_ULF_only_generation_manifest.json
```

`direct_voxel_ULF_only_bootstrap_se.nii.gz` 和 `direct_voxel_ULF_only_permutation_summary.csv` 只在 primary branch 中生成。Non-primary branches 不生成这些文件，并在 manifest 和 QC JSON 中记录 `not_run_nonprimary`。

Output semantics：

- `direct_voxel_ULF_only_coverage.nii.gz` 存储 `Coverage_ULF_tau(v)=sum_i I[X_ULF_only_i(v)>tau]`。使用 `int16`。
- `direct_voxel_ULF_only_coef.nii.gz` 在当前 `partial_spearman/` estimator 中存储 `rho_ULF(v)`。未来可选 OLS outputs 会存储 `theta_ULF(v)`。
- `direct_voxel_ULF_only_sweet_sour.nii.gz` 存储 benefit-oriented `M_ULF(v)`。正值表示 ULF-only benefit-associated voxels。
- `direct_voxel_ULF_only_stability.nii.gz` 存储 LOOCV training-fold direction stability，即按 display class 统计 `M_ULF(v)>0` 或 `M_ULF(v)<0` 的方向稳定性。它不是 p value。
- `direct_voxel_ULF_only_bootstrap_se.nii.gz` 只在 primary branch 中存储 full-process bootstrap 下 estimator map 的标准差。
- `direct_voxel_ULF_only_scores.csv` 存储 patient-level scores，包括 `ULFScore_mean_main`、`DeltaHFScore`、`Y_HF`、`score_map_source`、`n_valid_score_voxels` 和 `is_primary_score`。
- `direct_voxel_ULF_only_loocv_predictions.csv` 存储 held-out predictions、observed raw outcome、covariate-only prediction、`ULFScore_mean_main`、`DeltaHFScore` 和 residuals。
- `direct_voxel_ULF_only_permutation_summary.csv` 只在 primary branch 中存储 Freedman-Lane permutation summary。
- `direct_voxel_ULF_only_HF_overlap_exclusion_mask.nii.gz` 存储因 branch tau 下 HF 与 ULF 同时 active 而从 ULF-only predictor 中排除的 voxels。
- `direct_voxel_ULF_only_mapping_qc.json` 存储 endpoint/tau/estimator 级 QC，包括 patient inclusion、candidate mask size、coverage distribution、`Omega_ULF_tau` voxel count、HF-overlap exclusion volume、degenerate voxels、NaN handling、zero-exposure score counts、`corr(ULFScore_mean_main, Y_HF)`、`corr(ULFScore_mean_main, DeltaHFScore)`、coefficient signs、collinearity diagnostics、flip deformation audit metrics 和 design-matrix dimensions。
- `direct_voxel_ULF_only_generation_manifest.json` 存储 provenance、parameters、code version、conda environment、package state、random seeds 和 runtime profile。

主统计 maps 不平滑。Display smoothing 只在系数估计后生成，不用于 ULFScore、LOOCV、permutation、bootstrap 或 jitter：

```text
display_smooth_fwhm1mm/
display_smooth_fwhm2mm/
```

Display maps 应叠加：

```text
ULF-only sweet/sour map
HF-overlap exclusion mask
STN/SNr anatomical outlines
STNSNrplus territory background
```

## 左右翻转 Deformation Audit

`ea_flip_lr_nonlinear` 是唯一支持的左右翻转方法。Audit 只记录 warnings，不会自动排除 subjects，除非出现 input integrity failure。

QC metrics：

```text
input/output grid and affine
finite voxel count
nonzero voxel count
max, p95, p99, sum
suprathreshold volume at 180 / 200 / 220 V/m
intensity-weighted centroid
L-to-R output overlap with right canonical brainmask
component label and side metadata
```

空图、全 NaN 图、非有限值、missing paths 和明显 path/component mismatch 是 hard failures。普通 deformation differences 只作为 warnings。

## Spatial Jitter QC Sensitivity

Spatial jitter 是对已接受 e-field 输入的 robustness stress test。它不是 automatic localization/normalization QC，也不是 input-validity gate。除非某 endpoint 被明确提升为 co-primary，它只对 primary ULF branch 运行。

```text
formal jitter resamples: B = 1000
smoke jitter resamples:  B = 100
seed: 42
FWHM: 2 mm
sigma: 2 / 2.355 = 0.849 mm
```

每次 jitter iteration 对每个 subject-side HF 和 ULF component e-field 独立抽取 3D translation vector。对 e-field 执行 translation-only resampling，使用 linear interpolation，outside fill value 为 `0`。随后重建 ULF-only exposure、HF-overlap exclusion、`Omega_ULF_tau`、`DeltaHFScore`、full-sample map、ULF scores 和 LOOCV validation metrics。

不要保存每张 jittered NIfTI map。只保存 summary table、map correlation/stability summary 和 voxel-wise jitter standard deviation map。

## Reference-Parameter Coverage

ULF direct voxel model 在适用处覆盖与 HF direct voxel model 相同的 direct voxel parameter family：

```text
raw sim-efield, not sim-efieldgauss
right canonical voxel grid
ea_flip_lr_nonlinear left/right flip
tau = 180 / 200 / 220 V/m
Coverage>=5
baseline/covariate-adjusted partial Spearman
LOOCV
Freedman-Lane permutation for the primary branch
subject-level bootstrap for the primary branch
2 mm FWHM spatial jitter QC
display smoothing FWHM 1 mm and 2 mm, display only
```

当前 ULF direct voxel execution 中仅记录、不执行的项目：

```text
Coverage>=6 optional sensitivity: documented only; no current ULF direct voxel outputs
Coverage>=8 / 50% E-field rule: documented only; primary rule remains Coverage>=5
5/7/10-fold CV: documented only; LOOCV is executable
optional OLS supplemental estimator: documented only; not run in the current execution
OSS-DBS: not part of direct voxel; belongs to normative fiber / activation sensitivity
paper-like spatial similarity score sensitivity: not included; ULFScore_mean_main is the primary score
automatic localization / electrode reconstruction QC: not included; prior manual QC is assumed
```

## 解释边界

该模型估计 HF-adjusted ULF-only add-on association。它不是解剖 SNr gain 模型。被 HF 和 ULF 同时激活的 voxels 在主分析中视为 HF-dominant，因此 ULF map 表示在校正 HF clinical state 和 model-predicted HF efficacy changes 后，由 ULF 唯一招募的区域。

由于队列为 `n=16`，结果属于 hypothesis-generating。LOOCV 不显著不应解释为不存在生物学 ULF add-on sweet spot。QC report 必须包含 `ULFScore_mean_main`、`Y_HF` 和 `DeltaHFScore` 之间的关联，以及 final prediction model 的基础 collinearity diagnostic。

应解释为：

```text
After accounting for HF state and modeled HF efficacy changes, additional ULF-only exposure in this territory is associated with better or worse post-HF+ULF outcome.
```

不应解释为：

```text
The displayed voxels prove an anatomic SNr-specific causal effect.
```

## Execution Efficiency

优化实现必须保留上文定义的 logical full-process semantics。特别是，LOOCV training folds 仍然各自定义自己的 HF adjustment map、`DeltaHFScore`、`Omega_ULF_tau`、ULF voxel map、ULF scores 和 held-out predictions。Formal Freedman-Lane permutation 和 subject-level bootstrap 对 primary branch 仍使用 `B=10000` 和 seed `42`。Smoke runs 对 permutation/bootstrap 使用 `B=1000`，对 jitter 使用 `B=100`。

### Equivalence Contract

优化可以复用数学上不变的 cached subcomputations，但不得为了提速使用 full-sample ranks、full-sample training masks、approximate ranks、adaptive early stopping、changed tau thresholds、changed estimators 或 reduced formal resampling counts。

Numerical reductions 尽量使用 `float64`。最终 NIfTI outputs 中 coefficient、sweet/sour、stability 和 bootstrap SE maps 使用 `float32`，coverage 和 binary/exclusion masks 使用 `int16`。

### Preprocessing Sidecar Cache

Formal-loop 首选输入：

```text
X_ULF_only_float32_voxel_major.npy
E_HF_component_float32_voxel_major.npy
S180_ULF_only_bool.npy
S200_ULF_only_bool.npy
S220_ULF_only_bool.npy
HF_overlap_tau180_bool.npy
HF_overlap_tau200_bool.npy
HF_overlap_tau220_bool.npy
candidate_ijk.npy
candidate_xyz_mm.npy
candidate_mask_metadata.json
```

Voxel-major layout 是首选，因为 voxel chunks 在磁盘上连续。MAT 和 compressed NPZ files 可以保留用于 archival、compatibility 和 debugging。Compressed NPZ 不得作为 formal permutation、bootstrap 或 jitter loops 内的主要 random-access input。

### Coverage And Fold Mask Cache

对每个 tau，预计算：

```text
S_tau(v, i) = I[X_ULF_only_i(v) > tau]
Coverage_tau_all(v) = sum_i S_tau(v, i)
Coverage_tau_fold_h(v) = Coverage_tau_all(v) - S_tau(v, h)
Omega_ULF_tau_fold_h = {v : Coverage_tau_fold_h(v) >= 5}
```

`HF_overlap_tau*_bool` 可以缓存，因为它只依赖 accepted HF/ULF component exposures 和 tau，不依赖 outcome。

### Vectorized Partial Spearman Kernel

每个 training fold 的 ranks 必须只在 training set 内计算。LOOCV map fitting、permutation map fitting、bootstrap maps 和 jitter resamples 都禁止使用 full-sample ranks。

ULF 主估计器对 outcome 和 exposure 同时 residualize：

```text
rank(Y_HF_train)
rank(DeltaHFScore_train)
```

No-DeltaHF sensitivity 只 residualize：

```text
rank(Y_HF_train)
```

### Fold-Level Score Operator For Permutation

Primary branch 的 Formal Freedman-Lane permutation 可使用 fold-level score operator，但必须逻辑上等价于为每个 permuted outcome 重算完整 ULF map 和 `ULFScore_mean_main`。

每个 permutation 必须拥有自己的：

```text
rho_ULF(v)
M_ULF(v)
V_score
ULFScore_mean_main
held-out prediction
LOOCV statistic
```

### Bootstrap Efficiency

Subject-level bootstrap 仍是 primary branch 的 full-process map stability analysis。它必须重建 bootstrap `DeltaHFScore`、`Omega_ULF_tau`、`rho_ULF` 和 `M_ULF`。Bootstrap SE 通过 streaming Welford updates 累积。实现不得保存 10000 张 bootstrap maps。

### Spatial Jitter Efficiency

Jitter 会改变 e-field geometry。因此 primary `X`-derived caches 在 jitter 下失效，不能假装 exposure 未改变而复用。每次 jitter iteration 必须重建 HF component exposure、ULF component exposure、HF-overlap exclusion、ULF-only exposure、candidate mask、`Omega_ULF_tau`、`DeltaHFScore`、map、scores 和 LOOCV metrics。

### Prohibited Speed Shortcuts

Formal runs 禁止：

```text
adaptive permutation early stopping
reduced formal B
changed tau thresholds
changed Coverage>=5 rule
changed estimator
full-sample ranks inside LOOCV/permutation/bootstrap
approximate ranks
using anatomical overlay masks as the analysis mask
dropping requested jitter QC
using total ULF exposure in place of ULF-only exposure
including HF-overlap voxels in the primary ULF predictor
using compressed NPZ as the random-access formal-loop input
```

### Runtime Profile

`direct_voxel_ULF_only_generation_manifest.json` 应包含：

```json
{
  "runtime_profile": {
    "preprocess_s": null,
    "sidecar_write_s": null,
    "load_design_s": null,
    "observed_loocv_s": null,
    "permutation_s": null,
    "bootstrap_s": null,
    "jitter_s": null,
    "display_qc_s": null,
    "n_voxels_candidate": null,
    "n_voxels_tau200_mean": null,
    "n_voxels_tau200_min": null,
    "n_voxels_tau200_max": null,
    "n_hf_overlap_tau200_mean": null,
    "python_jobs": null,
    "blas_threads": null,
    "memmap_sidecars": [],
    "bootstrap_finite_count_summary": null
  }
}
```

### Equivalence And Regression Tests

正式运行前，在 deterministic subset 上比较 brute-force 和 optimized implementations：

```text
B_perm = 20
B_boot = 20
n_voxel_subset = 100 to 1000
seed = 42
```

比较：

```text
fold-specific DeltaHFScore
fold-specific Omega_ULF_tau
HF-overlap exclusion masks
partial Spearman rho map
benefit-oriented M_ULF map
ULFScore_mean_main
LOOCV held-out predictions
LOOCV Spearman rho
permutation null statistics
bootstrap SE for finite voxels
```

Required tolerances：

```text
exact equality for masks, subject IDs, voxel IDs, and split indices
near equality for float outputs under float64 reductions
same NaN/degenerate voxel locations
same plus-one p value for the deterministic small test
```

## 执行优先级与 Gatekeeping

ULF direct voxel analysis 应按 gatekeeping sequence 运行。不要一次性运行所有 sensitivity analyses。

### Round 0: Input Readiness

运行：

```text
clinical table audit:
  Y_post exists
  Y_HF exists
  DeltaHFScore inputs exist
  ID joins to imaging subject
  scale direction is defined

e-field availability check:
  HF-only pre-ULF e-fields exist
  HF+ULF HF-component e-fields exist
  HF+ULF ULF-component e-fields exist
  all matches are unique
  raw sim-efield is used

component audit:
  HF frequency >= 100 Hz
  ULF frequency <= 50 Hz
  mixed or proxy component fields are labeled
```

只有 primary endpoint subjects 都有完整 clinical 和 e-field inputs，且有效样本量至少为 12，才进入 Round 1。

### Round 1: Preprocessing And Overlap QC

运行 preprocessing sidecars 和 flip audit。确认：

```text
X_ULF_only matrix is non-empty
HF_overlap exclusion mask is non-empty or explicitly zero
tau200 Coverage>=5 Omega_ULF is non-empty
each subject has nonzero HF component exposure
each subject has nonzero or explicitly absent ULF-only exposure
```

如果大多数 subjects 的 ULF-only exposure 为空，则停止并报告 primary ULF-only predictor 不可建模。

### Round 2: Primary Chronic Observed LOOCV

先运行：

```text
endpoint = MDS-UPDRS III total chronic HF+ULF 3-month score
branch = tau200 / partial_spearman
score = ULFScore_mean_main
covariates = Y_HF + DeltaHFScore
validation = LOOCV
```

只有所有 folds 完成、`ULFScore_mean_main` 非常数、held-out predictions finite、LOOCV rho 为正、`Q2 > 0`，且 ULFScore model 优于 `Y_HF + DeltaHFScore`，才进入 Round 3。

如果 primary chronic branch 为阴性、近常数，或由单个 high-leverage subject 决定，则停止。主分支失败后，不运行 `tau180/tau220` 来寻找更好的阈值。

### Round 3: Equivalence And Smoke Resampling

运行：

```text
deterministic equivalence test
smoke permutation B=1000
smoke bootstrap B=1000
smoke jitter B=100
```

只有 optimized 和 brute-force paths 匹配、smoke resampling 无 artifacts、bootstrap finite-count distribution 可接受，且 jitter 不反转信号方向时，才进入 Round 4。

### Round 4: Formal Permutation

只对 primary chronic branch 运行：

```text
tau200 / partial_spearman
B = 10000
seed = 42
statistic = LOOCV Spearman rho
```

Permutation 完成、p value finite 且 observed signal 仍为正时，进入 bootstrap。如果 `p_perm > 0.10` 且 `Q2 <= 0`，停止 heavy analyses，只生成 minimal exploratory report。

### Round 5: Formal Bootstrap

运行：

```text
tau200 / partial_spearman
B = 10000
seed = 42
```

只有 bootstrap finite counts 可接受、core sign stability 可解释，且多数 bootstrap maps 非空，才继续。

### Round 6: Formal Spatial Jitter

运行：

```text
tau200 / partial_spearman
B = 1000
FWHM = 2 mm
```

如果 jitter map correlation 接近 0 或 signal direction 反转，则将结论降级为 spatially fragile exploratory association。

### Round 7: Tau Sensitivity

只运行 observed LOOCV：

```text
tau180 / partial_spearman
tau220 / partial_spearman
```

Tau sensitivity 不运行 formal permutation/bootstrap。`tau180/tau220` 解释为 robustness checks，而不是 threshold search。

### Round 8: Immediate Endpoint

只在 chronic primary branch 可解释后运行：

```text
endpoint = immediate HF+ULF motor score
branch = tau200 / partial_spearman
validation = observed LOOCV
smoke permutation optional
```

Immediate endpoint 的 formal resampling 需要显式决定将其作为 co-primary。

### Round 9: Display And Final Manifests

只有在 statistical branches 完成后，才生成 display smoothing、bilateral homologous display maps、HF-overlap exclusion overlays、STN/SNr outlines、PDF QC 和 final manifests。Display outputs 不得回流到 ULFScore、LOOCV、permutation、bootstrap 或 jitter。

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

第一批实际运行只应覆盖：

```text
Round 0
Round 1
Round 2
Round 3 smoke only
```

具体 first-batch scope：

```text
MDS-UPDRS III total chronic endpoint
tau200
partial_spearman
Coverage>=5
ULF-only exposure
HF-overlap exclusion
DeltaHFScore-adjusted model
ULFScore_mean_main
LOOCV
covariate-only comparison
equivalence test
smoke permutation B=1000
smoke bootstrap B=1000
smoke jitter B=100
basic QC JSON + manifest
```
