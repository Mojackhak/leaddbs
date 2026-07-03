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

- e-field 查找或缺失补算的程控参数来源：

  ```text
  /Users/mojackhu/Research/STNSNr/summary/cohort/subj/followup_stimulation.xlsx
  sheet = Contact Parameters
  ```

  缺失 e-field 需要补算时，该工作簿是权威参数来源。已有 cohort QC CSV 可用于审计，但不是补算参数的主来源。

- 每侧 HF-only E-field 取自 Lead-DBS Horn/SimBio FEM 在 `3m/STN` 条件下的输出：

  ```text
  stimulations/MNI152NLin2009bAsym/<stimlabel>_3m_STN_*/sub-<Subject>_sim-efield_model-simbio_hemi-{L,R}.nii
  ```

  使用原始 `sim-efield`，不用 `sim-efieldgauss`。E-field 保持 Lead-DBS 原始单位 `V/m`。如果必需的 e-field 缺失，pipeline 应根据 `followup_stimulation.xlsx` 补算；若补算失败，则该 scale/run 以 QC 错误停止，不静默剔除 subject。

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

模型在 `Omega_HF_tau` 内使用连续 `X_HF_only_i(v)` 拟合；`tau` 只用于 coverage 和 QC。参考文献中的 `Coverage>=8` / 50% E-field coverage 仅记录在 reference-coverage checklist 中，不生成单独 HF direct voxel 结果。

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

主模型不加入额外协变量。若某 voxel 的 exposure 方差、rank 方差或 residualized exposure 方差为 0，则设 `rho_HF(v)=NaN`，并从 HFScore numerator 和 denominator 中排除。

Benefit-oriented map：

```text
M_HF(v) = -rho_HF(v)   for lower-is-better scales
M_HF(v) =  rho_HF(v)   for higher-is-better scales
```

正值统一表示 sweet 或 benefit-associated。

### 补充估计器：OLS ANCOVA

OLS ANCOVA 作为完整平行补充分析：

```text
Y_post_i = alpha_v
         + theta_HF(v) * X_HF_only_i(v)
         + beta_v      * Y_base_i
         + error_i,v
```

OLS estimator 在 `ols_ancova/` estimator 目录下生成同一套输出。该目录下的 `direct_voxel_HF_coef.nii.gz` 存储 `theta_HF(v)`；主分析 `partial_spearman/` 目录下的同名文件存储 `rho_HF(v)`。

### 患者层面 Score

患者层面 HF sweet-spot score：

```text
HFScore_i =
  sum_v X_HF_only_i(v) * M_HF(v)
  / sum_v X_HF_only_i(v)
```

denominator 只在具有有效 `M_HF(v)` 的 voxel 上计算。如果某 subject/fold 的 denominator 为 0，则 `HFScore_i` 和对应 prediction 记为 `NaN`，并从该指标计算中排除。

最终预测模型：

```text
Y_post_i = alpha
         + delta * HFScore_i
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

- Patient-level Freedman-Lane permutation 在正式分析中使用 `B=10000` 和随机种子 `42`。smoke/exploratory 运行使用 `B=1000`。每次置换先拟合 nuisance model `Y_post ~ Y_base`，置换 nuisance residuals，重构 `Y*`，然后完整重跑 LOOCV pipeline，包括 coverage、map、score 和 prediction。主置换统计量为 LOOCV Spearman rho。
- permutation p value 使用 plus-one two-sided：

  ```text
  p = (1 + count(|stat_perm| >= |stat_obs|)) / (B + 1)
  ```

- Subject-level bootstrap 在正式分析中使用 `B=10000` 和随机种子 `42`。smoke/exploratory 运行使用 `B=1000`。每次 bootstrap 重采样都重跑完整 map-building 流程，包括 `Omega_HF_tau`；`direct_voxel_HF_bootstrap_se.nii.gz` 存储 estimator map 的 voxel-wise 标准差。

## 执行结构

后续代码实现应将影像预处理与统计后处理分开：

- MATLAB/Lead-DBS 预处理：
  - 查找或补算必需的 HF-only e-field；
  - 对同侧 alternating 子程序做逐 voxel 最大值合并；
  - 所有左右翻转均调用 `ea_flip_lr_nonlinear`；
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
  - 执行 LOOCV、完整 Freedman-Lane permutation、完整 bootstrap、OLS supplemental analysis 和 jitter QC sensitivity；
  - 用 `nibabel` 写出 CSV/JSON、PDF QC figures 和 NIfTI maps；
  - 将 candidate vector 填回右半球 MNI reference grid。

Python 统计后处理必须在 `leaddbs` Conda 环境中运行，例如使用 `conda run -n leaddbs python ...`，或先激活 `leaddbs` 环境后执行。若分析需要，允许在该环境内安装、升级或调整必要 Python 包；最终包状态必须写入 run manifest。记录 `conda list --explicit` 和 `python -m pip freeze` 输出或其路径。

默认资源使用应尽量高效且可复现：

```text
MATLAB preprocessing workers: 8
Python statistical jobs: 14
random seed: 42
```

并行任务从 seed `42` 派生确定性子种子。MATLAB 预处理与 Python 后处理分阶段运行，避免 CPU oversubscription。smoke mode 使用 `B=1000` 次 permutation/bootstrap 重采样和 `B=100` 次 jitter 重采样。

保留中间审计输出，包括 right/flipped exposure products、candidate masks、ROI design matrices、manifest、lock files 和 completion markers。默认跳过已完成结果，同时提供 force-rerun 选项。

## 下游可视化和输出

输出根目录按每个量表、tau 和 estimator 分层：

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale_slug>/preprocess/
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale_slug>/tau180/partial_spearman/
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale_slug>/tau180/ols_ancova/
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale_slug>/tau200/partial_spearman/   # primary
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale_slug>/tau200/ols_ancova/
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale_slug>/tau220/partial_spearman/
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale_slug>/tau220/ols_ancova/
```

`<scale_slug>` 是确定性转换：小写、非字母数字替换为下划线、连续下划线合并、移除首尾下划线。原始 scale column name 写入 manifest。

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

输出语义：

- `direct_voxel_HF_coverage.nii.gz` 存储 `Coverage_tau(v) = sum_i I(X_HF_i(v) > tau)`。使用 `int16`。
- `direct_voxel_HF_coef.nii.gz` 在 `partial_spearman/` 中存储 `rho_HF(v)`，在 `ols_ancova/` 中存储 `theta_HF(v)`。使用 `float32`。不做逐 voxel FDR。
- `direct_voxel_HF_sweet_sour.nii.gz` 存储 benefit-oriented `M_HF(v)`。
- `direct_voxel_HF_stability.nii.gz` 存储 LOOCV training folds 中 benefit-oriented map value 为正的折比例。它是方向稳定性 map，不是 p 值，也不是显著性阈值图。
- `direct_voxel_HF_bootstrap_se.nii.gz` 存储 full-process bootstrap 下 estimator map 的标准差。
- `direct_voxel_HF_scores.csv` 存储由 full-sample reporting map 计算的患者级 exposure-weighted map matching score。
- `direct_voxel_HF_loocv_predictions.csv` 存储 held-out LOOCV predictions，包括 `HFScore_LOOCV`、真实结局、HFScore-model 预测值、covariate-only baseline 预测值和残差。
- `direct_voxel_HF_permutation_summary.csv` 存储 Freedman-Lane permutation 汇总，包括 observed LOOCV Spearman rho、plus-one two-sided p value、secondary metrics 和 `B`。
- `direct_voxel_HF_mapping_qc.json` 存储 scale/tau/estimator 级 QC，包括患者纳入、candidate mask 大小、coverage、`Omega_HF_tau` voxel 数、退化 voxel、NaN 处理、denominator-zero 计数和 design matrix 维度。
- `direct_voxel_HF_generation_manifest.json` 存储 provenance，包括输入、输出、参数、随机种子、代码版本、Conda `leaddbs` 环境、Python 包状态、reference-coverage checklist 和 estimator identity。

主统计 map 不平滑。display smoothing 只在系数估计后生成，不用于 HFScore、LOOCV、permutation 或 bootstrap：

```text
display_smooth_fwhm1mm/
display_smooth_fwhm2mm/
```

仅为了可视化生成双侧 homologous display NIfTI：用 `ea_flip_lr_nonlinear` 将右侧 canonical map 翻转到左侧，并与右侧统计 map 合并。该双侧展示图不是独立的 side-specific statistical model。

PDF-only QC figures：

```text
coverage histogram
score-vs-outcome scatter
LOOCV observed-vs-predicted scatter
permutation null distribution
bootstrap stability summary
jitter stability summary
```

## Spatial Jitter QC Sensitivity

Spatial jitter 是用于测试 stimulation localization 和 normalization 空间不确定性的 QC sensitivity。它只对主分析 `tau200/partial_spearman` 运行。

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
Freedman-Lane permutation
partial Spearman voxel association
OLS supplemental estimator
2 mm FWHM spatial jitter QC
1 mm and 2 mm display smoothing
```

已覆盖但不生成单独 HF direct voxel 结果：

```text
Coverage>=8 / 50% E-field rule: only documented; primary rule remains Coverage>=5
5/7/10-fold CV: only documented; LOOCV is the sole validation design for n=16
OSS-DBS: not included in the HF direct voxel model
```

## 解释边界

该模型估计在控制 baseline 后，HF-only 局部刺激暴露与 3 个月 raw post-treatment outcome 的关联。它应解释为 stimulation-exposed right canonical brainmask candidate space 内的 HF efficacy heatmap，而不是纯解剖 STN map、target-level network mechanism map，也不是 voxel-wise 因果证据。
