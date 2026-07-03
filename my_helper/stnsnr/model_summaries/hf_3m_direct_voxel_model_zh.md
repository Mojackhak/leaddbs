# HF-only 3m 直接 Voxel-Level 模型

## 研究问题

哪些高频刺激 territory 内的 voxel，其 HF-only 暴露与更好的 3 个月 HF-only 临床结局相关？

这是一个局部刺激 sweet spot 模型。原 STN-only 阶段在这里解释为 HF-only DBS territory，而不是解剖学 STN-only 模型。STN/SNr mask 只用于 territory 定义、覆盖描述和可视化 overlay，不用于把模型效应硬分给某一个核团。

频率定义固定为：

```text
HF  = high-frequency stimulation component, frequency_Hz >= 100
ULF = ultra-low-frequency stimulation component, frequency_Hz <= 50
```

## 终点

主终点：

```text
Y_HF3m = raw HF-only 3-month clinical score
```

主协变量：

```text
Y_Preop = raw preoperative clinical score
```

首轮默认量表：

```text
MDS-UPDRS III score (STN, 3 m)
MDS-UPDRS III axial score (STN, 3 m)
```

量表列表可配置。已知量表的方向由内置方向表提供；未知量表必须在运行前显式指定 higher-is-better 或 lower-is-better。两个首轮默认量表均为低分更好，因此 benefit-oriented map 为 `M_HF(v) = -theta_HF(v)`。

## 输入

- 原始临床分数来自：

  ```text
  /Users/mojackhu/Research/STNSNr/summary/cohort/subj/subject_effect_origin.xlsx
  ```

  临床行与影像按 `ID`（`SNr003`、`SNr006` 等）连接。subject directory 与 `NameEn` 通过刺激参数工作簿解析，只作为后续文件系统 metadata。

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

  使用原始 `sim-efield`，不用 `sim-efieldgauss`。E-field 保持 Lead-DBS 原始单位 `V/m`。如果必需的 e-field 缺失，pipeline 应根据 `followup_stimulation.xlsx` 补算；若补算失败，则以 QC 错误停止，不静默剔除该 subject。

- 交替刺激的 `3m/STN` 不按同时双阴极刺激建模。同侧多个 alternating 子程序 e-field 用逐 voxel 最大值合成为该侧 HF-only field。

- Territory mask：

  ```text
  templates/space/MNI152NLin2009bAsym/atlases/STNSNr-connected regions/{rh,lh}/STNSNrplus.nii.gz
  ```

  manifest：`dilate_mm(2 mm, union(STN>0.05, SNr>0.05))`，位于 MNI152NLin2009bAsym 参考网格。不再额外扩张。

- 左右同源变换：

  ```text
  helpers/ea_flip_lr_nonlinear.m
  templates/space/MNI152NLin2009bAsym/fliplr/{Composite,InverseComposite}.nii.gz
  ```

  本模型所有左右翻转均调用 `ea_flip_lr_nonlinear`，采用 Lead-DBS 默认插值行为。不得用自定义左右形变或手写插值替代该 helper。

## 特征构建

以右侧 `STNSNrplus` 网格作为标准统计网格。左侧 HF e-field 通过 `ea_flip_lr_nonlinear` 翻转到右侧空间，得到右侧标准网格上的 `E_L_to_R_i(v)`。右侧 HF e-field 在同一网格上采样为 `E_R_i(v)`。

患者层面的双侧暴露为：

```text
X_HF_only_i(v) = (E_R_i(v) + E_L_to_R_i(v)) / 2
```

这样每个患者每个同源 voxel 只有一个值，避免左右伪重复。暴露值不按 frequency 或 pulse width 缩放；frequency 只用于判定该 component 是否为 HF。

该模型不使用 paired-mask membership threshold。也就是说，可执行 HF direct voxel 模型中没有 `P_left_to_R`、没有 `Omega_pair`，也没有 `membership > 0.5` 或 `membership > 0.7` 规则。

在每个 training set 内定义分析 mask：

```text
tau_primary = 200 V/m
tau_sensitivity = {180, 220} V/m
Coverage_tau(v) = sum_i 1[X_HF_only_i(v) > tau]
Omega_HF_tau = {v : Coverage_tau(v) >= 5}
```

模型在 `Omega_HF_tau` 内使用连续 `X_HF_only_i(v)` 拟合；`tau` 只用于 coverage 和 QC。`Omega_HF_tau` 不再与 `right_STNSNrplus` 做 intersection；`STNSNrplus` 只作为 canonical/reference grid、解剖 overlay 和 coverage/QC 背景。主分析使用 `tau=200 V/m`；`tau=180` 和 `tau=220 V/m` 是完整敏感性分析。

coverage mask、voxel map、HF score 和验证预测均在每个 LOOCV training fold 内计算。留出患者不参与该 fold 的 coverage mask 或 voxel map 定义。

## 统计模型

对每个 voxel `v`，估计残差化 ANCOVA OLS 系数。先将 `Y_HF3m` 和 `X_HF_only(v)` 分别对 `Y_Preop` 残差化，再用残差化暴露回归残差化结局：

```text
Y_HF3m_i = alpha_v
         + theta_HF(v) * X_HF_only_i(v)
         + beta_v      * Y_Preop_i
         + error_i,v
```

不对 `X_HF_only(v)` 或 `M_HF(v)` 做标准化。

若某 voxel 的 exposure 方差为 0，或残差化后 exposure 方差为 0，则设 `theta_HF(v)=NaN`，并从 HFScore 的 numerator 和 denominator 中排除。

Benefit-oriented map：

```text
M_HF(v) = -theta_HF(v)   for lower-is-better scales
M_HF(v) =  theta_HF(v)   for higher-is-better scales
```

患者层面 HF sweet-spot score：

```text
HFScore_i =
  sum_v X_HF_only_i(v) * M_HF(v)
  / sum_v X_HF_only_i(v)
```

denominator 只在具有有效 `M_HF(v)` 的 voxel 上计算。如果某 subject/fold 的 denominator 为 0，则 `HFScore_i` 和对应 prediction 记为 `NaN`，并从该指标计算中排除。

最终预测模型：

```text
Y_HF3m_i = alpha
         + delta * HFScore_i
         + beta  * Y_Preop_i
         + error_i
```

对低分更好的量表，期望方向为 `delta < 0`。

缺失处理：若某 scale 缺 `Y_HF3m`、缺 `Y_Preop`，或 e-field 可用性 QC 失败，则该患者只从该 scale 中剔除。未来扩展量表时，有效样本数低于 12 的 scale 跳过。

## 验证

- 使用 leave-one-patient-out cross-validation，不做 inner hyperparameter tuning。
- 每个 outer fold 内重新构建 `Omega_HF_tau`、拟合 voxel map、计算 training 与 held-out HF score，并只用 training patients 拟合最终预测模型。
- 与 covariate-only baseline `Y_HF3m ~ Y_Preop` 比较。
- 在原始 raw outcome 尺度上报告 Pearson `r`、Spearman `rho`、MAE、RMSE 和 `Q2`。
- `Q2` 相对 covariate-only baseline 定义：

  ```text
  Q2 = 1 - SSE_HFScore_model / SSE_YPreop_only
  ```

- Patient-level Freedman-Lane permutation 在正式分析中使用 `B=10000` 和随机种子 `42`。smoke/exploratory 运行使用 `B=1000`。每次置换先拟合 nuisance model `Y ~ Y_Preop`，置换 nuisance residuals，重构 `Y*`，然后完整重跑 LOOCV pipeline，包括 coverage、map、score 和 prediction。主置换统计量为 LOOCV Pearson `r`。
- Subject-level bootstrap 在正式分析中使用 `B=10000` 和随机种子 `42`。smoke/exploratory 运行使用 `B=1000`。每次 bootstrap 重采样都重跑完整 map-building 流程，包括 `Omega_HF_tau`；`direct_voxel_HF_bootstrap_se.nii.gz` 存储 `theta_HF(v)` 的 voxel-wise 标准差。

## 执行结构

后续代码实现应将影像预处理与统计后处理分开：

- MATLAB/Lead-DBS 预处理：
  - 查找或补算必需的 HF-only e-field；
  - 对同侧 alternating 子程序做逐 voxel 最大值合并；
  - 所有左右翻转均调用 `ea_flip_lr_nonlinear`；
  - 将 exposure 采样到右侧标准 `STNSNrplus` ROI；
  - 写出 MAT v7 ROI design matrix，包含 `X(subject x roi_voxel)`、voxel indices、subject metadata、clinical values、reference NIfTI path 和 QC metadata。

- `leaddbs` conda 环境中的 Python 后处理：
  - 读取 MAT v7 design matrix；
  - 执行 LOOCV、完整 Freedman-Lane permutation 和完整 bootstrap；
  - 用 `nibabel` 写出 CSV/JSON、figures 和 NIfTI maps；
  - 将 ROI vector 填回右侧标准 reference grid。

Python 统计后处理必须在 `leaddbs` Conda 环境中运行，例如使用
`conda run -n leaddbs python ...`，或先激活 `leaddbs` 环境后执行。
若分析需要，允许在该环境内安装、升级或调整必要 Python 包；最终包状态
应写入 run manifest，或另行导出 environment 文件，便于审计和复现。

默认资源使用应尽量高效且可复现：

```text
MATLAB preprocessing workers: 8
Python statistical jobs: 14
random seed: 42
```

并行任务从 seed `42` 派生确定性子种子。MATLAB 预处理与 Python 后处理分阶段运行，避免 CPU oversubscription。应提供 smoke mode，使用 `B=1000` 次 permutation/bootstrap 重采样，并减少 scale 和 tau 数量来快速检查流程。

保留中间审计输出，包括 right/flipped exposure products、ROI design matrices、manifest、lock files 和 completion markers。默认跳过已完成结果，同时提供 force-rerun 选项。

## 下游可视化

输出根目录按每个量表和 tau 分层：

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale>/tau180/
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale>/tau200/   # primary
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale>/tau220/
```

每个 tau 目录导出：

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

map 定义：

- `direct_voxel_HF_coef.nii.gz` 存储 full-sample final model 的原始 `theta_HF(v)`；不做逐 voxel FDR。
- `direct_voxel_HF_sweet_sour.nii.gz` 存储 benefit-oriented `M_HF(v)`。
- `direct_voxel_HF_stability.nii.gz` 是 LOOCV training folds 中 `theta_HF(v) > 0` 的折比例。
- `direct_voxel_HF_bootstrap_se.nii.gz` 是 full-process bootstrap 下 `theta_HF(v)` 的标准差。

主统计 map 不平滑。另在系数估计后生成 `FWHM=1 mm` 和 `FWHM=2 mm` 的敏感性展示 map，并重新回掩膜到 territory。

统计 map 在右侧标准网格上拟合。仅为了可视化，用 `ea_flip_lr_nonlinear` 将右侧 map 翻转到左侧，生成双侧同源展示图。该双侧展示图不是独立的 side-specific statistical model。

使用以 0 为中心的 diverging color scale 显示 HF sweet/sour map。低覆盖 voxel 显示为透明或灰色。STN 与 SNr 边界只作为 overlay。

## 解释边界

该模型估计 HF-only 局部刺激暴露与 3 个月结局的关联。它应解释为 STN/SNr stimulation territory 内的 HF efficacy heatmap，而不是纯解剖 STN map，也不是 voxel-wise 因果证据。
