# HF-only 3m 直接 Voxel-Level 模型

## 研究问题

哪些高频刺激 territory 内的 voxel，其 HF-only 暴露与更好的 3 个月 HF-only 临床结局相关？

这是一个局部刺激 sweet spot 模型。原 STN-only 阶段解释为 HF-only DBS territory，而不是解剖学 STN-only 模型。STN/SNr mask 只用于解剖 overlay 和覆盖描述，不用于把模型效应硬分给某一个核团。

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

首轮默认量表：

```text
MDS-UPDRS III score (STN, 3 m)
MDS-UPDRS III axial score (STN, 3 m)
```

raw post 和 baseline 分数来自：

```text
/Users/mojackhu/Research/STNSNr/summary/cohort/subj/subject_effect_origin.xlsx
```

临床行与影像按 `ID`（`SNr003`、`SNr006` 等）连接。本模型不使用改善率宽表。量表列表可配置；已知量表方向由内置方向表提供，未知量表必须在运行前显式指定 higher-is-better 或 lower-is-better。

## 输入

- stimulation metadata 审计来源：

  ```text
  /Users/mojackhu/Research/STNSNr/summary/cohort/subj/followup_stimulation.xlsx
  sheet = Contact Parameters
  ```

  该工作簿可用于审计 stimulation metadata，但当前 HF direct voxel 可执行分析假设既有 e-field 已在人工/临床 QC 后正确生成。本轮不自动生成缺失 e-field。

- 每侧 HF-only E-field 取自 Lead-DBS Horn/SimBio FEM 在 `3m/STN` 条件下的输出：

  ```text
  stimulations/MNI152NLin2009bAsym/<stimlabel>_3m_STN_*/sub-<Subject>_sim-efield_model-simbio_hemi-{L,R}.nii
  ```

  使用原始 `sim-efield`，不用 `sim-efieldgauss`。E-field 保持 Lead-DBS 原始单位 `V/m`。pipeline 只做最小可用性检查：路径必须存在，subject/side/condition 匹配必须唯一，文件必须是 raw `sim-efield`。若必需 e-field 缺失或存在多重匹配，则该 scale/run 以 QC 错误停止。不静默剔除 subject，也不在本模型内自动生成缺失 e-field。

- 交替刺激的 `3m/STN` 不按同时双阴极刺激建模。同侧多个 alternating 子程序 e-field 用逐 voxel 最大值合成为该侧 HF-only field。

- canonical reference mask：

  ```text
  templates/space/MNI152NLin2009bAsym/brainmask.nii.gz > 0
  ```

  candidate voxel 限制在右半球 voxel center，MNI world coordinate `x > 0`。

- 解剖 overlay mask：

  ```text
  templates/space/MNI152NLin2009bAsym/atlases/STNSNr-connected regions/{rh,lh}/STNSNrplus.nii.gz
  ```

  `STNSNrplus` 只用于 anatomical overlay 和 coverage/QC 背景。它不与 `Omega_HF_tau` 做 intersection，也不是统计 candidate mask。

- 左右同源变换：

  ```text
  helpers/ea_flip_lr_nonlinear.m
  templates/space/MNI152NLin2009bAsym/fliplr/{Composite,InverseComposite}.nii.gz
  ```

  本模型所有左右翻转均调用 `ea_flip_lr_nonlinear`，采用 Lead-DBS 默认插值行为。不得用自定义左右形变或手写插值替代该 helper。

- 参考方法文件：

  ```text
  /Volumes/VAL/STNSNr/reference/s41593-024-01570-1.pdf
  /Volumes/VAL/STNSNr/reference/41593_2024_1570_MOESM1_ESM.pdf
  /Volumes/VAL/STNSNr/reference/s41467-024-48731-1.pdf
  /Volumes/VAL/STNSNr/reference/41467_2024_48731_MOESM1_ESM.pdf
  ```

## 特征构建

使用右半球 MNI brainmask 网格作为 canonical statistical grid。左侧 HF e-field 通过 `ea_flip_lr_nonlinear` 翻转到右侧空间，得到右侧 canonical grid 上的 `E_L_to_R_i(v)`。右侧 HF e-field 在同一网格上采样为 `E_R_i(v)`。

患者层面的双侧暴露为：

```text
X_HF_only_i(v) = (E_R_i(v) + E_L_to_R_i(v)) / 2
```

这样每个患者每个同源 voxel 只有一个值，避免左右伪重复。暴露值不按 frequency 或 pulse width 缩放；frequency 只用于判定该 component 是否为 HF。

该模型不使用 paired-mask membership threshold。也就是说，可执行 HF direct voxel 模型中没有 `P_left_to_R`、没有 `Omega_pair`，也没有 `membership > 0.5` 或 `membership > 0.7` 规则。

sparse candidate 构建：

```text
candidate_threshold = 180 V/m
Candidate(v) = any valid subject has X_HF_only_i(v) > 180 V/m
```

candidate mask 只用于 sparse matrix construction，不是统计阈值。full-sample candidate mask 可在 LOOCV 前固定，因为它只移除所有有效患者都达不到最低敏感性阈值的 voxel。

每个 tau 独立定义：

```text
tau_primary = 200 V/m
tau_sensitivity = {180, 220} V/m
Coverage_tau(v) = sum_i I[X_HF_only_i(v) > tau]
Omega_HF_tau = {v in Candidate : Coverage_tau(v) >= 5}
```

模型在 `Omega_HF_tau` 内使用连续 `X_HF_only_i(v)` 拟合；`tau` 只用于 coverage 和 QC。`Coverage>=6` 和 `Coverage>=8` 是 primary mainline 的 optional sensitivity，不属于原始 `tau200/Coverage>=5` primary branch。当前唯一的 exploratory 例外是 A-model post-hoc threshold scan：它可以在 `Coverage=5,6,7,8,10,12` 上生成 scan-level 输出，但这些输出仍是 post-hoc，不能替代 primary branch。参考文献中的 `Coverage>=8` / 50% E-field coverage 保留在 reference-coverage checklist 中，但不作为本 `n=16` 队列的主规则。

coverage mask、voxel map、HF score 和验证预测均在每个 LOOCV training fold 内计算。留出患者不参与该 fold 的 `Omega_HF_tau` 或 voxel map 定义。

## 统计模型

### 主估计器：Baseline-Adjusted Partial Spearman

对每个 voxel `v`，使用 rank-residual partial Spearman，ties 使用 average ranks：

```text
rho_HF(v) =
  corr(
    resid(rank(Y_post_i)       ~ rank(Y_base_i)),
    resid(rank(X_HF_only_i(v)) ~ rank(Y_base_i))
  )
```

主模型不加入额外协变量。若某 voxel 的 exposure 方差、rank 方差或 residualized exposure 方差为 0，则设 `rho_HF(v)=NaN`，并从 HFScore 计算中排除。

Benefit-oriented map：

```text
M_HF(v) = -rho_HF(v)   for lower-is-better scales
M_HF(v) =  rho_HF(v)   for higher-is-better scales
```

正值统一表示 sweet 或 benefit-associated。

### 可选补充估计器：OLS ANCOVA

OLS ANCOVA 保留为未来可选补充估计器。当前可执行分析不运行该分支，也不生成对应输出文件。

```text
Y_post_i = alpha_v
         + theta_HF(v) * X_HF_only_i(v)
         + beta_v      * Y_base_i
         + error_i,v
```

如果未来启用 OLS estimator，它应在 `ols_ancova/` estimator 目录下生成同一套输出。该目录下的 `direct_voxel_HF_coef.nii.gz` 存储 `theta_HF(v)`；当前主分析 `partial_spearman/` 目录下的同名文件存储 `rho_HF(v)`。

### 患者层面 Score

主患者层面 HF sweet-spot score：

```text
V_score = Omega_HF_tau intersect valid M_HF voxels
n_valid_score_voxels = |V_score|

HFScore_mean_main_i =
  sum_{v in V_score} X_HF_only_i(v) * M_HF(v)
  / n_valid_score_voxels
```

这是主分析 score，表示在对应 full-sample map 或 LOOCV training fold 的固定 scoring voxel set 上，按 voxel 数归一化的 voxel 相关性加权平均 exposure。它除以 `n_valid_score_voxels`，使不同 fold 的 `Omega_HF_tau` 大小不同时 score 数值仍更可比。它不除以 `sum(X)`，也不乘 voxel volume。若 `V_score` 为空，则该 branch/fold 以 QC failure 停止，不生成 score。若某 subject/fold 在非空有效 scoring voxel set 内没有 exposure，则 `HFScore_mean_main_i` 记为 `0`。

对应的未归一化总剂量 exposure score 仅作为文档中的描述性概念保留：

```text
HFScore_sum_descriptive_i =
  sum_{v in V_score} X_HF_only_i(v) * M_HF(v)
```

`HFScore_sum_descriptive_i` 当前不实际计算，也不写入输出文件；它不参与主 prediction model、LOOCV statistic、permutation 或 bootstrap。文档中保留它只是为了说明主 score 与此前讨论的总剂量 exposure 的关系。

最终预测模型：

```text
Y_post_i = alpha
         + delta * HFScore_mean_main_i
         + beta  * Y_base_i
         + error_i
```

prediction model 在 raw post-score 尺度上拟合。主验证统计量仍然是 rank-based LOOCV Spearman rho。

缺失处理：若某 scale 缺 `Y_post`、缺 `Y_base`，或 e-field 可用性 QC 失败，则该 scale/run 失败。未来扩展量表时，有效样本数低于 12 的 scale 跳过。

## 验证

- 使用 leave-one-patient-out cross-validation，不做 inner hyperparameter tuning。
- 每个 outer fold 内重新构建 `Omega_HF_tau`、拟合 voxel map、计算 training 与 held-out HF score，并只用 training patients 拟合最终预测模型。
- 与 covariate-only baseline `Y_post ~ Y_base` 比较。
- 主验证统计量：held-out prediction 与 held-out raw outcome 的 LOOCV Spearman rho。
- 次要指标：原始 raw outcome 尺度上的 LOOCV Pearson `r`、MAE、RMSE 和 `Q2`。
- `Q2` 相对 covariate-only baseline 定义：

  ```text
  Q2 = 1 - SSE_HFScore_model / SSE_YBase_only
  ```

- Patient-level Freedman-Lane permutation 在正式主分析中使用 `B=10000` 和随机种子 `42`。smoke/exploratory 运行使用 `B=1000`。正式 permutation 只对 `tau200/partial_spearman` 运行。每次置换先拟合 nuisance model `Y_post ~ Y_base`，置换 nuisance residuals，重构 `Y*`，然后完整重跑 LOOCV pipeline，包括 coverage、map、`HFScore_mean_main` 和 prediction。主置换统计量为 LOOCV Spearman rho。
- permutation p value 使用 plus-one two-sided：

  ```text
  p = (1 + count(|stat_perm| >= |stat_obs|)) / (B + 1)
  ```

- Subject-level bootstrap 在正式主分析中使用 `B=10000` 和随机种子 `42`。smoke/exploratory 运行使用 `B=1000`。正式 bootstrap 只对 `tau200/partial_spearman` 运行。每次 bootstrap 重采样都重跑完整 map-building 流程，包括 `Omega_HF_tau`；`direct_voxel_HF_bootstrap_se.nii.gz` 存储 estimator map 的 voxel-wise 标准差。

对非主已执行分支（`tau180/partial_spearman` 和 `tau220/partial_spearman`），仍运行 LOOCV，但不生成正式 permutation/bootstrap 输出。对应 manifest 和 QC JSON 必须记录：

```text
resampling_status = not_run_nonprimary
resampling_reason = formal resampling restricted to tau200/partial_spearman
```

## 执行结构

后续代码实现应将影像预处理与统计后处理分开：

- MATLAB/Lead-DBS 预处理：
  - 查找并检查必需 HF-only e-field 的可用性；
  - 对同侧 alternating 子程序做逐 voxel 最大值合并；
  - 所有左右翻转均调用 `ea_flip_lr_nonlinear`；
  - 计算左右翻转 deformation audit 指标，只记录 warning，不自动排除；
  - 将 exposure 采样到右半球 MNI brainmask candidate grid；
  - 写出 MAT v7 design matrix，并可选写出 compressed NPZ mirror。

- 必需 design matrix schema：
  - `X(subject x candidate_voxel)` continuous HF exposure；
  - candidate voxel `ijk` 和 MNI `xyz_mm`；
  - NIfTI affine/header reference；
  - `subject_id`、source e-field paths、side metadata 和 clinical raw values；
  - tau/candidate metadata、flip metadata 和 jitter metadata placeholder。

- `leaddbs` Conda 环境中的 Python 后处理：
  - 读取 MAT v7 design matrix 或 optional NPZ mirror；
  - 对所有生成的 tau/estimator 分支执行 LOOCV；
  - 仅对 `tau200/partial_spearman` 执行正式 Freedman-Lane permutation 和 full bootstrap；
  - 对主分析 `tau200/partial_spearman` 执行 jitter QC sensitivity；
  - 记录可选 OLS ANCOVA 在当前执行中未运行；
  - 用 `nibabel` 写出 CSV/JSON、PDF QC figures 和 NIfTI maps；
  - 将 candidate vector 填回右半球 MNI reference grid。

Python 统计后处理必须在 `leaddbs` Conda 环境中运行，例如使用 `conda run -n leaddbs python ...`，或先激活 `leaddbs` 环境后执行。若分析需要，允许在该环境内安装、升级或调整必要 Python 包；最终包状态必须写入 run manifest。记录 `conda list --explicit` 和 `python -m pip freeze` 输出或其路径。

默认资源使用应尽量高效且可复现：

```text
MATLAB preprocessing workers: 8
Python statistical jobs: 14
random seed: 42
```

并行任务从 seed `42` 派生确定性子种子。MATLAB 预处理与 Python 后处理分阶段运行，避免 CPU oversubscription。smoke mode 对主分支使用 `B=1000` 次 permutation/bootstrap 重采样和 `B=100` 次 jitter 重采样。

保留中间审计输出，包括 right/flipped exposure products、candidate masks、ROI design matrices、manifest、lock files 和 completion markers。默认跳过已完成结果，同时提供 force-rerun 选项。

## 下游可视化和输出

输出根目录按每个量表、tau 和 estimator 分层：

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale_slug>/preprocess/
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale_slug>/tau180/partial_spearman/
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale_slug>/tau200/partial_spearman/   # primary
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale_slug>/tau220/partial_spearman/
```

`<scale_slug>` 是确定性转换：小写、非字母数字替换为下划线、连续下划线合并、移除首尾下划线。原始 scale column name 写入 manifest。

未来可选 OLS ANCOVA 输出会使用同级 `ols_ancova/` 目录，但当前运行不生成这些目录。

每个 tau/estimator 目录导出：

```text
direct_voxel_HF_coverage.nii.gz
direct_voxel_HF_coef.nii.gz
direct_voxel_HF_sweet_sour.nii.gz
direct_voxel_HF_stability.nii.gz
direct_voxel_HF_bootstrap_se.nii.gz
direct_voxel_HF_scores.csv
direct_voxel_HF_loocv_predictions.csv
direct_voxel_HF_permutation_summary.csv
direct_voxel_HF_mapping_qc.json
direct_voxel_HF_generation_manifest.json
```

`direct_voxel_HF_bootstrap_se.nii.gz` 和 `direct_voxel_HF_permutation_summary.csv` 只在主分支 `tau200/partial_spearman` 下生成。非主分支不生成这些文件，并在 manifest 和 QC JSON 中记录 `not_run_nonprimary`。

输出语义：

- `direct_voxel_HF_coverage.nii.gz` 存储 `Coverage_tau(v) = sum_i I(X_HF_i(v) > tau)`。使用 `int16`。
- `direct_voxel_HF_coef.nii.gz` 在当前执行的 `partial_spearman/` estimator 中存储 `rho_HF(v)`。如果未来启用可选 OLS ANCOVA，则对应 `ols_ancova/` 文件存储 `theta_HF(v)`。使用 `float32`。不做逐 voxel FDR。
- `direct_voxel_HF_sweet_sour.nii.gz` 存储 benefit-oriented `M_HF(v)`。
- `direct_voxel_HF_stability.nii.gz` 存储 LOOCV training folds 中 benefit-oriented map value 为正的折比例。它是方向稳定性 map，不是 p 值，也不是显著性阈值图。
- `direct_voxel_HF_bootstrap_se.nii.gz` 只在主分支中存储 full-process bootstrap 下 estimator map 的标准差。
- `direct_voxel_HF_scores.csv` 存储患者级 map matching scores。必需字段包括 `HFScore_mean_main`、`exposure_sum_valid_voxels`、`n_valid_score_voxels`、`score_map_source` 和 `is_primary_score`。只有 `HFScore_mean_main` 是主预测 score。`HFScore_sum_descriptive` 仅在文档中保留，不是必需输出字段。
- `direct_voxel_HF_loocv_predictions.csv` 存储 held-out LOOCV predictions，包括 `HFScore_LOOCV`、真实结局、HFScore-model 预测值、covariate-only baseline 预测值和残差。
- `direct_voxel_HF_permutation_summary.csv` 只在主分支中存储 Freedman-Lane permutation 汇总，包括 observed LOOCV Spearman rho、plus-one two-sided p value、secondary metrics 和 `B`。
- `direct_voxel_HF_mapping_qc.json` 存储 scale/tau/estimator 级 QC，包括患者纳入、candidate mask 大小、coverage distribution、`Omega_HF_tau` voxel 数、low-coverage warning、退化 voxel、NaN 处理、zero-exposure score 计数、`corr(HFScore_mean_main, Y_base)`、prediction coefficient signs、optional VIF 或等价共线性诊断、flip deformation audit metrics 和 design matrix 维度。
- `direct_voxel_HF_generation_manifest.json` 存储 provenance，包括输入、输出、参数、随机种子、代码版本、Conda `leaddbs` 环境、Python 包状态、reference-coverage checklist 和 estimator identity。

主统计 map 不平滑。display smoothing 只在系数估计后生成，不用于 HFScore、LOOCV、permutation 或 bootstrap：

```text
display_smooth_fwhm1mm/
display_smooth_fwhm2mm/
```

仅为了可视化生成双侧 homologous display NIfTI：用 `ea_flip_lr_nonlinear` 将右侧 canonical map 翻转到左侧，并与右侧统计 map 合并。该双侧展示图不是独立的 side-specific statistical model。

仅对主分支生成报告用 display masks。这些 mask 不是显著性图，不得用于 scoring、LOOCV、permutation 或 bootstrap：

```text
sweet_display_mask:
  M_HF(v) > 0
  positive M_HF(v) within top 10% among positive voxels in Omega_HF_tau
  positive-direction stability >= 0.75

sour_display_mask:
  M_HF(v) < 0
  absolute negative M_HF(v) within top 10% among negative voxels in Omega_HF_tau
  negative-direction stability >= 0.75
```

sweet display 的 stability 定义为 LOOCV training folds 中 `M_HF(v)>0` 的比例。sour display 的 stability 定义为 LOOCV training folds 中 `M_HF(v)<0` 的比例。解剖显示汇总应报告 display voxels 位于 `STNSNrplus`、Custom STN、Custom SNr 以及这些 mask 外部的数量和比例。

PDF-only QC figures：

```text
coverage histogram
score-vs-outcome scatter
LOOCV observed-vs-predicted scatter
permutation null distribution
bootstrap stability summary
jitter stability summary
```

## 左右翻转 Deformation Audit

所有左右翻转仍然使用 `ea_flip_lr_nonlinear`。flip audit 记录变形质量和明显异常值，但普通翻转差异只作为 warning，不会自动导致 run 失败或 subject 排除。

在 `direct_voxel_HF_mapping_qc.json` 中记录：

```text
input/output grid and affine
finite voxel count
nonzero voxel count
max, p95, p99, sum
suprathreshold volume at 180, 200, and 220 V/m
intensity-weighted centroid
L-to-R output overlap with the right canonical brainmask
optional roundtrip metrics if generated
```

空图、全 NaN、非有限值或明显路径错误属于 input availability/data-integrity failure。常规插值或形变差异只记录为 warning。

## Spatial Jitter QC Sensitivity

Spatial jitter 是施加在已接受 e-field 输入上的可选稳健性压力测试。它不是自动 localization/normalization QC，也不是输入有效性的门槛。它只对主分析 `tau200/partial_spearman` 运行。

```text
formal jitter resamples: B = 1000
smoke jitter resamples:  B = 100
FWHM = 2 mm
sigma = 2 / 2.355 = 0.849 mm
```

每次 jitter iteration 对每个 subject-side E-field 独立抽取 3D translation vector：

```text
dx, dy, dz ~ Normal(0, sigma^2)
```

对 E-field 进行 translation-only resampling，使用 linear interpolation，outside fill value 为 `0`。随后重新计算 candidate mask、`Omega_HF_tau`、full-sample map、HF scores 和 LOOCV validation metrics。不保存每次 jitter 的完整 NIfTI map；只保存 summary table、map correlation/stability summary 和 voxel-wise jitter standard deviation map。

## Reference-Parameter Coverage

`direct_voxel_HF_generation_manifest.json` 和 `direct_voxel_HF_mapping_qc.json` 必须包含 `/Volumes/VAL/STNSNr/reference` 本地参考文献的 parameter coverage checklist。

已覆盖并生成结果：

```text
raw E-field magnitude model
tau = 180, 200, 220 V/m
LOOCV validation
Freedman-Lane permutation for tau200/partial_spearman
partial Spearman voxel association
subject-level bootstrap for tau200/partial_spearman
left/right flip deformation audit
report-only top 10% + stability display masks
2 mm FWHM spatial jitter QC
1 mm and 2 mm display smoothing
```

已覆盖但不生成单独 HF direct voxel 结果：

```text
Coverage>=6 optional sensitivity: 不在 primary mainline 中生成；仅允许出现在 A-model post-hoc threshold scan 中
Coverage>=8 / 50% E-field rule: 不在 primary mainline 中生成；primary rule 仍为 Coverage>=5
5/7/10-fold CV: only documented; LOOCV is the sole validation design for n=16
OSS-DBS: not included in the HF direct voxel model
optional OLS supplemental estimator: only documented; not run in the current execution
paper-like spatial similarity score sensitivity: not included; HFScore_mean_main is the primary score
automatic localization/normalization/electrode reconstruction QC: not included; existing e-fields are assumed to have passed prior manual/clinical QC
```

## 解释边界

该模型估计在控制 baseline 后，HF-only 局部刺激暴露与 3 个月 raw post-treatment outcome 的关联。它应解释为 stimulation-exposed right canonical brainmask candidate space 内的 HF efficacy heatmap，而不是纯解剖 STN map、target-level network mechanism map，也不是 voxel-wise 因果证据。

由于队列为 `n=16`，结果属于 hypothesis-generating。LOOCV 可能不显著；LOOCV 不显著不应解释为不存在生物学 HF sweet spot。`Y_base` 在 voxel map 阶段通过 partial Spearman residualization 控制，同时也保留在最终 prediction model 中，用于评估 `HFScore_mean_main` 的增量预测价值。因此 QC report 必须包含 `HFScore_mean_main` 与 `Y_base` 的关联，以及最终 prediction model 的基础共线性诊断。

## Execution Efficiency

本节定义用于提高 HF direct voxel analysis 项目级计算效率的 implementation-level rules。这些规则只改变 computation scheduling、cache、vectorization 和 disk writing，不改变 statistical estimands、validation design、output semantics、file naming，也不改变任何 `direct_voxel_HF_*` 输出的解释。

优化实现必须保留上文定义的 logical full-process semantics。特别是，LOOCV training folds 仍然各自定义自己的 `Omega_HF_tau`、voxel maps、HF scores 和 held-out predictions。Formal Freedman-Lane permutation 和 subject-level bootstrap 对 primary `tau200/partial_spearman` branch 仍使用 `B=10000` 和 seed `42`。Smoke runs 对 permutation/bootstrap 仍使用 `B=1000`，对 jitter 仍使用 `B=100`。优化实现可以复用数学上不变的 cached subcomputations，但不得为了提速使用 full-sample ranks、full-sample training masks、approximate ranks、adaptive early stopping、改变 tau thresholds、改变 estimators，或降低 formal resampling counts。

### Equivalence Contract

以下量属于 executable statistical definition，必须保持不变：

```text
tau = 180, 200, 220 V/m
primary tau = 200 V/m
Coverage>=5
LOOCV patient split
primary estimator = baseline-adjusted partial Spearman
optional supplemental estimator = OLS ANCOVA, not run in the current execution
primary score = HFScore_mean_main
formal permutation B = 10000
formal bootstrap B = 10000
formal jitter B = 1000
seed = 42
primary permutation statistic = LOOCV Spearman rho
```

Numerical reductions 尽量使用 `float64`。最终 NIfTI outputs 保持既有 output dtypes：coefficient、sweet/sour、stability 和 bootstrap SE maps 使用 `float32`，coverage maps 使用 `int16`。既有 degenerate-voxel 和 NaN 规则保持不变。

实现必须保留 logical full-process recomputation 与 mathematically equivalent cached computation 的区别。例如，permutation run 逻辑上仍必须等价于为每个 permuted outcome 重新计算 LOOCV map 和 `HFScore_mean_main`，但当 fixed exposure-derived fold caches 与 permuted outcome 无关时，可以复用这些 caches。

### Preprocessing Sidecar Cache

MATLAB/Lead-DBS preprocessing 必须继续按既有 subject-major schema 写出文档化的 MAT v7 design matrix：

```text
X(subject x candidate_voxel)
```

此外，formal runs 必须写出 memmap-friendly voxel-major sidecar files 供 Python postprocessing 使用：

```text
X_float32_voxel_major.npy       # shape = candidate_voxel x subject
S180_bool.npy                   # X > 180 V/m
S200_bool.npy                   # X > 200 V/m
S220_bool.npy                   # X > 220 V/m
candidate_ijk.npy
candidate_xyz_mm.npy
candidate_mask_metadata.json
```

`X_float32_voxel_major.npy` 是 formal loop 首选输入，因为 voxel chunks 在磁盘上连续。可以额外写出 subject-major mirror 以便使用，但 formal permutation/bootstrap loops 应避免使用 compressed random-access formats。公式中的 `X_all[:, V]` 表示 logical subject-major view；实现可以通过 chunked reads 或 transposition 从 voxel-major sidecar 得到该 view。

MAT 和 compressed NPZ files 可以保留用于 archival、compatibility 和 debugging。Compressed NPZ 不得作为 formal permutation、bootstrap 或 jitter loops 内的主要 random-access input。

Sidecar metadata 必须记录：

```text
subject order
candidate voxel order
affine/header reference
dtype
array shape
memory layout
source MAT path
source MAT hash if available
sidecar creation time
software version
```

### Coverage And Fold Mask Cache

对每个 tau，先一次性预计算 full-sample suprathreshold indicators 和 coverage：

```text
S_tau(v, i) = I[X_i(v) > tau]
Coverage_tau_all(v) = sum_i S_tau(v, i)
```

对 LOOCV fold `h`，通过 subtraction 得到 training-fold coverage：

```text
Coverage_tau_fold_h(v) =
  Coverage_tau_all(v) - S_tau(v, h)
```

然后定义 fold-specific statistical mask：

```text
Omega_HF_tau_fold_h =
  {v in Candidate : Coverage_tau_fold_h(v) >= 5}
```

因此 held-out patient 仍不贡献该 fold-specific `Omega_HF_tau`，但 mask 通过 vectorized subtraction 计算，而不是重新扫描完整 exposure matrix。

### Vectorized Partial Spearman Kernel

Primary voxel map 必须使用 vectorized rank-residual partial Spearman kernel。

每个 training fold 的 ranks 必须只在 training set 内计算。LOOCV map fitting、permutation map fitting、bootstrap maps 和 jitter resamples 都禁止使用 full-sample ranks。

对每个 fold `h`：

```text
b_h = rank(Y_base_train)

R_h = residual-maker matrix for:
      intercept + b_h
```

对每个 voxel chunk：

```text
xrank_h(v) = rank(X_train(v)) within the training fold
xres_h(v)  = R_h xrank_h(v)
```

零 exposure variance、零 rank variance 或零 residualized exposure variance 的 degenerate voxels 保持既有 NaN 规则，并从 `HFScore_mean_main` 中排除。

精确 partial Spearman coefficient 为：

```text
yrank_h = rank(Y_post_train)
yres_h  = R_h yrank_h

rho_HF_h(v) =
  dot(yres_h, xres_h(v))
  / sqrt(sum(yres_h^2) * sum(xres_h(v)^2))
```

Benefit-oriented map 保持：

```text
M_HF_h(v) = -rho_HF_h(v)   for lower-is-better scales
M_HF_h(v) =  rho_HF_h(v)   for higher-is-better scales
```

### Fold-Level Score Operator For Permutation

Formal Freedman-Lane permutation for the primary `tau200/partial_spearman` branch 应使用 fold-level score operator。

在固定 LOOCV fold 内，以下量与 permuted outcome 无关：

```text
X exposure matrix
tau200 suprathreshold indicators
Coverage_tau200_fold_h
Omega_HF_tau200_fold_h
valid nondegenerate exposure voxels
n_valid_score_voxels
rank(Y_base_train)
residualized and normalized rank(X_train(v))
held-out exposure values
all-subject exposure values used for scoring
```

对每个 fold `h`，定义 valid scoring voxel set：

```text
V_h = Omega_HF_tau200_fold_h intersect valid exposure-residual voxels
n_h = |V_h|
```

令 `Z_h` 为 `V_h` 上的 normalized residualized exposure-rank matrix：

```text
Z_h(:, v) =
  resid(rank(X_train(v)) ~ 1 + rank(Y_base_train))
  / sqrt(sum(resid_X_h(v)^2))
```

令 `X_score_h` 为所有 patients 在 `V_h` 上的 continuous exposure matrix，不是 ranked exposure：

```text
X_score_h = X_all(:, V_h)
```

Fold-level score operator 为：

```text
A_h =
  direction_sign * X_score_h @ Z_h.T / n_h

direction_sign = -1 for lower-is-better scales
direction_sign =  1 for higher-is-better scales
```

对 observed 或 permuted outcome，计算：

```text
yres_h =
  resid(rank(Y_train) ~ 1 + rank(Y_base_train))

u_h =
  yres_h / sqrt(sum(yres_h^2))
```

然后该 fold 的所有 patient scores 由下式得到：

```text
HFScore_mean_main_all_patients_h = A_h @ u_h
```

这等价于先计算 fold-specific partial Spearman map，再应用：

```text
HFScore_mean_main_i =
  sum_{v in V_h} X_i(v) * M_HF_h(v) / n_h
```

对 formal permutation，实现应为每个 reconstructed `Y*` 重新计算 `u_h`，但可以复用 `A_h`。

默认必须保留精确 normalized partial Spearman scaling。只有在不写出 maps、scores、coefficients 或 fold-level model coefficients 的 internal null-statistic-only computations 中，才可以省略 common positive fold-permutation scaling factor。Observed outputs 和任何 debug comparison outputs 必须使用精确 normalization。

Permutation runs 不得写出 per-permutation voxel maps、per-permutation NIfTI files 或 per-permutation score CSV files。只应写出最终 permutation summary，以及复现该 summary 所需的 compact null-statistic arrays。

### Optional Vectorized OLS ANCOVA Kernel

如果未来启用 OLS ANCOVA，应使用 Frisch-Waugh-Lovell residualization kernel，而不是为每个 voxel 单独拟合 statsmodels 或 polyfit model。

对每个 fold 或 full-sample map：

```text
yres = resid(Y_post ~ 1 + Y_base)
xres(v) = resid(X(v) ~ 1 + Y_base)

theta_HF(v) =
  dot(yres, xres(v)) / sum(xres(v)^2)
```

这会在避免 voxel-wise Python model fitting overhead 的同时，产生相同的 OLS ANCOVA coefficient `theta_HF(v)`。当前执行不运行该分支。

### Score Computation

对 observed maps 和 non-permutation branches，用每个 map 一次 matrix-vector product 计算 `HFScore_mean_main`：

```text
scores =
  X_all[:, V_score] @ M_HF[V_score] / n_valid_score_voxels
```

`X_all` 是 continuous exposure，不是 ranked exposure。Rank transformation 只用于估计 partial Spearman voxel map。

Formal runs 不允许使用 subject-loop by voxel-loop 实现。

### Bootstrap Efficiency

Subject-level bootstrap 仍是 primary `tau200/partial_spearman` branch 的 full-process map stability analysis。它仍使用 `B=10000` 和 seed `42`。

但是，bootstrap 必须尽可能复用 exposure-derived caches。

对每个 bootstrap resample，用 subject counts 表示 resampled patients：

```text
w_i = number of times subject i appears in the bootstrap sample
```

然后在不重新扫描 image data 的情况下计算 bootstrap coverage：

```text
Coverage_tau200_boot(v) =
  sum_i w_i * I[X_i(v) > 200]
```

Bootstrap `Omega_HF_tau200_boot` 为：

```text
Omega_HF_tau200_boot =
  {v in Candidate : Coverage_tau200_boot(v) >= 5}
```

`Y_post`、`Y_base` 和 `X(v)` 的 ranks 必须在 expanded bootstrap resample 内计算，或使用完全等价的 weighted-resample representation。禁止使用 full-sample ranks。

Bootstrap SE 必须通过 streaming Welford updates 累积。实现不得保存 10000 个 bootstrap maps。

对每个 voxel，维护：

```text
bootstrap_mean
bootstrap_M2
bootstrap_finite_count
```

某个 bootstrap map 中缺失、位于 bootstrap `Omega_HF_tau200_boot` 外，或在该 bootstrap resample 中 degenerate 的 voxels，遵循既有 NaN/out-of-valid-map 规则，不得静默填充为 0。

最终 `direct_voxel_HF_bootstrap_se.nii.gz` 存储 finite bootstrap estimator values 的 voxel-wise standard deviation。QC JSON 应记录 finite bootstrap count distribution。

### Spatial Jitter Efficiency

Spatial jitter 只对 primary `tau200/partial_spearman` branch 运行，并保持既有 formal 和 smoke 设置：

```text
formal jitter resamples = 1000
smoke jitter resamples  = 100
```

Jitter 会改变 e-field geometry。因此 primary `X`-derived caches 在 jitter 下失效，不得假装 exposure matrix 未改变而复用。

Jitter 实现可以复用：

```text
accepted e-field path manifest
subject/side metadata
right canonical reference grid
candidate grid metadata
affine/header information
preallocated arrays
```

每次 jitter iteration 必须按 Spatial Jitter QC Sensitivity 一节的定义，重建 jittered exposure matrix、candidate mask、`Omega_HF_tau200`、full-sample map、HF scores 和 LOOCV validation metrics。

不要保存每一张 jittered NIfTI map。只保存：

```text
jitter summary table
map correlation/stability summary
voxel-wise jitter SD map
```

### MATLAB/Lead-DBS Preprocessing Efficiency

每个 subject-side 的 accepted HF e-fields 应只处理一次。

同侧 alternating subprograms 在 left/right flipping 前按 voxel-wise maximum 合并。然后左侧 combined HF e-field 使用 `ea_flip_lr_nonlinear` 翻转一次。右侧 combined HF e-field 在 right canonical grid 上采样一次。

推荐 preprocessing artifacts：

```text
subject_side_right_grid_exposure.nii.gz or .npy
subject_left_to_right_grid_exposure.nii.gz or .npy
subject_level_X_HF_only.npy
flip_audit_summary.json
```

这些 artifacts 可以被 downstream Python postprocessing 和 jitter setup 复用，但每次 jitter iteration 必须单独生成 jittered exposure matrices。

### Parallel Execution

MATLAB preprocessing 和 Python statistical postprocessing 保持分阶段运行，以避免 CPU oversubscription。

Python postprocessing 应在 `leaddbs` Conda environment 内由单一 long-running Python entry point 调度。应避免在 tau、fold、permutation、bootstrap 或 jitter loops 内反复调用短生命周期 `conda run`。

优先使用 Python worker-level parallelism。导入 NumPy/SciPy 前必须禁用 nested BLAS oversubscription：

```bash
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
```

Run manifest 必须记录有效 worker count 和 BLAS thread settings。

推荐 scheduling order：

```text
1. MATLAB/Lead-DBS preprocessing and sidecar cache generation
2. tau200/partial_spearman observed LOOCV
3. tau200/partial_spearman smoke permutation/bootstrap/jitter
4. tau200/partial_spearman formal permutation
5. tau200/partial_spearman formal bootstrap
6. tau180/tau220 partial_spearman observed LOOCV
7. optional OLS ANCOVA supplemental branches only if explicitly enabled in a future run
8. display smoothing, bilateral display maps, PDF QC, and final manifests
```

Primary-branch QC failures 应在启动 non-primary sensitivity branches 前停止运行。

### Intermediate File Policy

Formal loops 不得写出 fold、permutation、bootstrap 或 jitter intermediate maps，除非显式开启 debug flag。

Default formal outputs 仍为既有文档化输出：

```text
direct_voxel_HF_coverage.nii.gz
direct_voxel_HF_coef.nii.gz
direct_voxel_HF_sweet_sour.nii.gz
direct_voxel_HF_stability.nii.gz
direct_voxel_HF_bootstrap_se.nii.gz
direct_voxel_HF_scores.csv
direct_voxel_HF_loocv_predictions.csv
direct_voxel_HF_permutation_summary.csv
direct_voxel_HF_mapping_qc.json
direct_voxel_HF_generation_manifest.json
```

Workers 不得并发 append 同一个 CSV 或 JSON。Workers 应返回 structured block results 给主进程，由主进程原子写出最终 CSV/JSON outputs。

Completed outputs 默认按既有 completion-marker 和 force-rerun policy 跳过。

### Prohibited Speed Shortcuts

Formal runs 中禁止以下 shortcuts：

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
using the descriptive sum score in place of HFScore_mean_main
using compressed NPZ as the random-access formal-loop input
loop-internal compression/decompression for speed-critical arrays
```

### Runtime Profile

`direct_voxel_HF_generation_manifest.json` 应包含 runtime profile：

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
    "python_jobs": null,
    "blas_threads": null,
    "memmap_sidecars": [],
    "score_operator_enabled": null,
    "score_operator_exact_scaling": null,
    "bootstrap_finite_count_summary": null
  }
}
```

### Equivalence And Regression Tests

正式运行前，实现应包含一个小规模 deterministic equivalence test。

对 small voxel subset 和 small resampling count：

```text
B_perm = 20
B_boot = 20
n_voxel_subset = 100 to 1000
seed = 42
```

比较 brute-force 和 optimized implementations：

```text
fold-specific Omega_HF_tau
partial Spearman rho map
benefit-oriented M_HF map
HFScore_mean_main
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

Final run manifest 应记录 optimized equivalence test 是否通过。

## 执行优先级与 Gatekeeping

HF direct voxel analysis 必须按 gatekeeping 分轮执行。目标不是一次性跑完所有已记录的敏感性分析，而是先判断主分支：

```text
tau200 / partial_spearman / Coverage>=5 / HFScore_mean_main
```

是否能在 LOOCV 中提供超过 covariate-only baseline 的可解释增量信号：

```text
Y_post ~ Y_base
```

非主分支和显示层输出都必须延后到主分支通过相应 gate 后再生成。

### Round 0: Input Readiness And Environment Lock

运行：

```text
clinical table audit:
  Y_post exists
  Y_base exists
  ID joins to imaging subject
  scale direction is defined

e-field availability check:
  each subject x side has a unique 3m/STN raw sim-efield
  sim-efieldgauss is not used
  units are recorded as V/m
  alternating subprograms can be identified and max-combined

left/right flip input audit:
  ea_flip_lr_nonlinear is callable
  Composite and InverseComposite transforms exist
  right canonical grid and brainmask are readable

environment manifest:
  MATLAB / Lead-DBS version
  Python conda env = leaddbs
  conda list --explicit
  python -m pip freeze
  seed = 42
```

只有满足以下条件才进入 Round 1：

```text
all primary-scale subjects have Y_post and Y_base
all subject-side e-field paths are uniquely matched
no missing or duplicated raw e-field
no empty, all-NaN, or non-finite e-field
left/right flip helper is callable
MDS-UPDRS III total has n >= 12, ideally n = 16
```

如果 required e-field 缺失或重复、clinical merge 不完整，或 scale direction 未定义，则停止并修复输入。不得 silent exclusion subjects。

### Round 1: Preprocessing Sidecars And Minimal QC

运行：

```text
MATLAB / Lead-DBS preprocessing:
  discover accepted HF-only e-fields
  combine same-side alternating subprograms by voxel-wise maximum
  flip left e-field to right canonical space
  sample right e-field on the right canonical grid

patient-level exposure:
  X_HF_only_i(v) = (E_R_i(v) + E_L_to_R_i(v)) / 2

sparse candidate sidecars:
  X_float32_voxel_major.npy
  S180_bool.npy
  S200_bool.npy
  S220_bool.npy
  candidate_ijk.npy
  candidate_xyz_mm.npy
  candidate_mask_metadata.json

flip audit summary:
  nonzero voxel count
  max, p95, p99, sum
  suprathreshold volume at 180 / 200 / 220 V/m
  intensity-weighted centroid
  L-to-R output overlap with right canonical brainmask
```

只有满足以下条件才进入 Round 2：

```text
X matrix shape = n_subjects x n_candidate_voxels
n_subjects exactly matches the clinical table
candidate_voxels > 0
S180 / S200 / S220 are not all zero
each subject has nonzero exposure on at least one side
full-sample tau200 Coverage>=5 Omega is non-empty
flip audit has no obvious path mismatch
```

以下情况作为 soft warnings 记录，不自动失败：

```text
extreme subject-level suprathreshold volume outlier
left-to-right flipped exposure centroid outside plausible brain bounds
exposure_sum_valid_voxels dominated by one or two subjects
```

如果 `Omega_tau200` 为空，则在建模前停止，并报告 `tau200/Coverage>=5` 对当前数据不可建模。

### Round 2: Primary Observed LOOCV

只运行主分支：

```text
scale = MDS-UPDRS III total
branch = tau200 / partial_spearman
candidate threshold = 180 V/m
Omega_HF_tau200 = Coverage_200 >= 5
estimator = baseline-adjusted partial Spearman
score = HFScore_mean_main
validation = LOOCV
baseline = Y_post ~ Y_base
```

生成：

```text
direct_voxel_HF_coverage.nii.gz
direct_voxel_HF_coef.nii.gz
direct_voxel_HF_sweet_sour.nii.gz
direct_voxel_HF_stability.nii.gz
direct_voxel_HF_scores.csv
direct_voxel_HF_loocv_predictions.csv
direct_voxel_HF_mapping_qc.json
direct_voxel_HF_generation_manifest.json
```

本轮不运行：

```text
axial scale
tau180 / tau220
formal permutation
formal bootstrap
formal jitter
OLS
display smoothing
top 10% display masks
```

只有满足以下条件才进入 Round 3：

```text
all LOOCV folds finish
each fold has non-empty Omega_tau200
each fold has non-empty valid M_HF voxels
degenerate voxel fraction does not make scoring meaningless
HFScore_mean_main is not constant across subjects
all held-out predictions are finite
final prediction model is not numerically singular
LOOCV Spearman rho_obs > 0
Q2 > 0
HFScore model improves MAE or RMSE over Y_base-only baseline
delta coefficient direction matches benefit-oriented M_HF interpretation
corr(HFScore_mean_main, Y_base) is not near +/-1
```

如果满足任一停止条件，则停止或报告 negative/exploratory primary result：

```text
LOOCV rho_obs <= 0
Q2 <= 0
HFScore model does not improve on Y_base-only baseline
multiple folds have empty or near-empty V_score
HFScore_mean_main is nearly constant
prediction is driven by one high-leverage subject
```

当主分支失败时，不应继续跑 `tau180/tau220` 来寻找更好的阈值。

### Round 3: Equivalence Test And Smoke Resampling

运行：

```text
deterministic equivalence / regression test:
  voxel subset = 100 to 1000
  B_perm = 20
  B_boot = 20
  seed = 42
  compare brute-force vs optimized

smoke permutation:
  tau200 / partial_spearman
  B = 1000
  Freedman-Lane
  full LOOCV recomputation semantics
  statistic = LOOCV Spearman rho

smoke bootstrap:
  tau200 / partial_spearman
  B = 1000
  streaming SE summary

smoke jitter:
  tau200 / partial_spearman
  B = 100
  FWHM = 2 mm
```

只有满足以下条件才进入 Round 4：

```text
fold-specific Omega_HF_tau exactly matches brute-force reference
subject IDs / voxel IDs / split indices exactly match
rho map approximately matches
M_HF map approximately matches
HFScore_mean_main approximately matches
LOOCV predictions approximately match
same NaN / degenerate voxel locations
small-test plus-one p value matches
permutation null is generated without crash
bootstrap finite-count distribution is acceptable
jitter map correlation is not near zero
jitter LOOCV rho does not systematically reverse direction
```

如果 optimized 和 brute-force 路径不等价，则停止并修复实现。如果 smoke permutation 显示 observed rho 很普通，且 Round 2 已经 `Q2 <= 0`，则停止并报告 exploratory negative result。如果 smoke jitter 高度不稳定，除非明确需要 fragility report，否则不运行 formal jitter。

### Round 4: Formal Permutation

运行：

```text
scale = MDS-UPDRS III total
branch = tau200 / partial_spearman
resampling = Freedman-Lane permutation
B = 10000
seed = 42
statistic = LOOCV Spearman rho
output = direct_voxel_HF_permutation_summary.csv
```

每次 permutation 必须逻辑上重跑：

```text
Y_post ~ Y_base nuisance model
permute residuals
reconstruct Y*
rebuild fold-wise map
recompute HFScore_mean_main
rerun LOOCV prediction
compute LOOCV Spearman
```

只有满足以下条件才进入 Round 5：

```text
formal permutation completes
plus-one p value is finite
observed rho is consistent with the smoke run
permutation null distribution has no implementation artifact
```

解释 gate：

```text
p_perm <= 0.10:
  proceed to full bootstrap and sensitivity as a signal-bearing primary branch

p_perm > 0.10 and rho_obs > 0 and Q2 > 0:
  proceed only to limited stability/sensitivity; label conclusions exploratory

p_perm > 0.10 and Q2 <= 0:
  stop heavy analyses and produce a minimal report
```

对于本 `n=16` 队列，不应把 `p < 0.05` 作为唯一进入条件。Permutation p value 应与 LOOCV rho、Q2、baseline comparison 和 influence diagnostics 一起解释。

### Round 5: Formal Bootstrap

运行：

```text
scale = MDS-UPDRS III total
branch = tau200 / partial_spearman
resampling = subject-level bootstrap
B = 10000
seed = 42
output = direct_voxel_HF_bootstrap_se.nii.gz
```

Bootstrap 必须重建：

```text
bootstrap sample
Coverage_tau200_boot
Omega_HF_tau200_boot
partial Spearman map
M_HF map
bootstrap SE
```

不得保存 10000 张 bootstrap maps。必须使用 streaming Welford accumulation。

只有满足以下条件才进入 Round 6：

```text
bootstrap finite-count distribution is not too low
primary sweet/sour regions are not completely swamped by SE
direction-stable areas overlap the LOOCV stability map
most bootstrap maps are not empty
median finite bootstrap count / B >= 0.70
core positive-region sign stability >= 0.70
LOOCV positive-direction stability >= 0.75 regions remain anatomically interpretable
```

如果 map 方向频繁翻转，或只由少数 bootstrap resamples 支撑，则不应做强 spatial sweet spot 解释。

### Round 6: Formal Spatial Jitter

运行：

```text
scale = MDS-UPDRS III total
branch = tau200 / partial_spearman
jitter B = 1000
FWHM = 2 mm
sigma = 0.849 mm
independent 3D translation per subject-side e-field
```

每次 jitter iteration 必须重建：

```text
jittered exposure matrix
candidate mask
Omega_HF_tau200
full-sample map
HF scores
LOOCV validation metrics
```

只有满足以下条件才进入 Round 7：

```text
median jitter map correlation > 0.5
median jitter LOOCV rho remains positive
core sweet/sour direction does not systematically reverse
core-region spatial drift stays within an anatomically interpretable range
```

如果 jitter map correlation 接近 0、LOOCV rho 跨 0 且方向不稳定，或 core region 在 1 到 2 mm translation 后完全消失，则将结论降级为：

```text
spatially fragile exploratory association
```

### Round 7: Tau Sensitivity

只运行 observed LOOCV：

```text
scale = MDS-UPDRS III total
branches:
  tau180 / partial_spearman
  tau220 / partial_spearman
```

非主分支不运行 formal permutation 或 formal bootstrap。Non-primary manifests 必须记录：

```text
resampling_status = not_run_nonprimary
resampling_reason = formal resampling restricted to tau200/partial_spearman
```

只有满足以下条件才进入 Round 8：

```text
tau180, tau200, and tau220 LOOCV rho directions agree
Q2 is broadly consistent in direction
tau200 is not the only threshold with a non-reversed effect
sweet/sour map spatial correlation or core overlap is acceptable
Omega size changes monotonically with tau
```

解释标准：

```text
tau180 / tau220 agree with tau200:
  supports threshold robustness

only tau200 has signal:
  report primary result as threshold-sensitive

tau180 or tau220 reverses direction:
  avoid strong sweet spot interpretation
```

### Round 8: Secondary Axial Scale

只在 MDS-UPDRS III total 主线有可解释结果后运行：

```text
scale = MDS-UPDRS III axial score
first branch = tau200 / partial_spearman
tau180 / tau220 only if tau200 axial passes QC
validation = observed LOOCV
smoke permutation = optional
```

除非 axial 被提升为共同 primary endpoint，或 total 和 axial 都显示一致主信号，否则不要立即为 axial 运行 formal `B=10000` permutation、formal bootstrap 或 formal jitter。

满足以下条件时，可进入 optional axial smoke resampling 或 secondary reporting：

```text
axial tau200 LOOCV folds all finish
HFScore is not constant
rho_obs has the same direction as total score
Q2 is not worse than baseline
map has plausible spatial overlap with the total-score map
```

如果满足以下条件，则将 axial 报告为 negative 或 exploratory：

```text
axial tau200 rho <= 0
Q2 <= 0
map is completely inconsistent with total score
one subject determines the result
```

### Round 9: Display, PDF QC, And Final Manifests

只在统计分支完成后运行：

```text
display_smooth_fwhm1mm/
display_smooth_fwhm2mm/
bilateral homologous display maps
sweet_display_mask
sour_display_mask

PDF QC:
  coverage histogram
  score-vs-outcome scatter
  LOOCV observed-vs-predicted scatter
  permutation null distribution
  bootstrap stability summary
  jitter stability summary
```

Display outputs 不得回流到：

```text
HFScore
LOOCV
permutation
bootstrap
jitter
```

Final reporting 必须满足：

```text
complete manifest for every generated branch
mapping_qc.json includes coverage, degenerate voxels, and zero-exposure score counts
corr(HFScore_mean_main, Y_base) is recorded
prediction coefficient signs and collinearity diagnostics are recorded
flip audit is recorded
package/environment provenance is recorded
```

### Round 10: Optional Future Analyses

以下内容不属于当前 direct voxel executable mainline：

```text
OLS ANCOVA
Coverage>=6
Coverage>=8 / 50% rule
5/7/10-fold CV
OSS-DBS
paper-like spatial similarity score
automatic localization / electrode reconstruction QC
```

OLS ANCOVA 是 optional future supplemental estimator，当前 run 不生成输出。OSS-DBS 不属于 direct voxel analysis，应保留在 normative fiber / activation sensitivity 文档中。

### Post-hoc Tau/Coverage Threshold Scan

A 模型的 post-hoc threshold scan 是在原始 primary branch 未通过 gate 后，用于探索 core HF sweet spot 阈值的 exploratory branch。它不能替代或追认为原始 primary analysis：

```text
primary branch:
  tau = 200 V/m
  Coverage >= 5

post-hoc scan:
  output root = posthoc_threshold_scan/
  interpretation = exploratory / post-hoc threshold optimization
```

扫描只针对第一个默认 endpoint：

```text
endpoint = MDS-UPDRS III score (STN, 3 m)
estimator = baseline-adjusted partial Spearman
score = HFScore_mean_main
validation = LOOCV
baseline model = Y_post ~ Y_base
```

扫描网格为：

```text
tau, V/m:
  100, 150, 180, 200, 220, 250, 300, 350, 400, 500

Coverage:
  5, 6, 7, 8, 10, 12
```

共 `10 x 6 = 60` 个格点。由于 `tau=100` 和 `tau=150` 低于 primary run 默认使用的 sparse candidate threshold，扫描必须构建或复用一个专门的 post-hoc exposure sidecar：

```text
candidate_sparse_threshold = 100 V/m
```

不允许用原始 `candidate_threshold=180 V/m` sidecar 来评估 `tau=100` 或 `tau=150`，因为这会遗漏 100-180 V/m 范围内的候选 voxel。

每个格点输出：

```text
tau
coverage
n_voxels_full
fold_n_voxels_min
fold_n_voxels_median
fold_n_voxels_max
LOOCV Spearman rho
LOOCV Spearman nominal p
LOOCV Pearson r
Q2
MAE_model
MAE_baseline
RMSE_model
RMSE_baseline
corr(HFScore_mean_main, Y_base)
delta_median
delta_min
delta_max
```

硬性稳定性过滤规则为：

```text
n_voxels_full >= 20
fold_n_voxels_min >= 10
HFScore non-constant in every fold
all held-out predictions finite
Q2 > 0
LOOCV Spearman rho > 0
MAE_model < MAE_baseline
RMSE_model < RMSE_baseline
```

只在通过全部硬性过滤的格点中选择 exploratory branch，优先级为：

```text
1. highest Q2
2. higher LOOCV Spearman rho if Q2 is tied or practically equivalent
3. higher fold_n_voxels_min
4. closer to the original primary branch tau=200 / Coverage>=5
5. if still tied, stricter Coverage and then higher tau as the more core/conservative branch
```

必需输出为：

```text
posthoc_threshold_scan_results.csv
posthoc_threshold_scan_heatmap_q2.csv
posthoc_threshold_scan_heatmap_rho.csv
posthoc_threshold_scan_heatmap_n_voxels.csv
posthoc_selected_threshold_manifest.json
```

如果绘图环境可用，应同步输出与 CSV heatmap 对应的图：

```text
posthoc_threshold_scan_heatmap_q2.png
posthoc_threshold_scan_heatmap_rho.png
posthoc_threshold_scan_heatmap_n_voxels.png
```

每个格点的 p 值仅为 nominal p。若后续要声称“扫描后仍显著”，必须运行 max-stat permutation：

```text
for each permutation:
  rerun all 60 tau x Coverage cells
  record max Q2 or max LOOCV rho

smoke max-stat permutation:
  B = 1000

formal max-stat permutation:
  B = 10000

seed = 42
```

除非明确要求，max-stat permutation 不属于本轮 initial post-hoc scan 输出。

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
MDS-UPDRS III total
tau200
partial_spearman
Coverage>=5
HFScore_mean_main
LOOCV
Y_base-only comparison
equivalence test
smoke permutation B=1000
smoke bootstrap B=1000
smoke jitter B=100
basic QC JSON + manifest
```

只有这一批通过后，才进入 `B=10000` formal permutation 和 bootstrap。
