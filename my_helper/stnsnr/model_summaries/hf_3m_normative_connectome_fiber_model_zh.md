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
X_R_i(l)      = peak raw sim-efield along right canonical fiber l
X_L_to_R_i(l) = peak left e-field after ea_flip_lr_nonlinear along the same right canonical fiber l
X_HF_i(l)     = (X_R_i(l) + X_L_to_R_i(l)) / 2
```

同侧 alternating HF 子程序先按 voxel-wise maximum 合并后再进行 fiber sampling。Exposure 不按 frequency 或 pulse width 缩放。

主候选规则：

```text
tau_primary = 800 V/m
tau_sensitivity = 1500 V/m
Coverage_tau(l) = sum_i I[X_HF_i(l) > tau]
F_candidate_tau = {l: Coverage_tau(l) >= 5}
```

`Coverage>=5` 是当前可执行规则。Nature Communications tract-library paper 中的 `>0.5% E-fields` 规则记录在 reference checklist 中，但对本 `n=16` 队列几乎过于宽松。因此当前实现采用 `Coverage>=5` 以提高稳定性。

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

### 主患者层面 Score

主 patient-level score 是 sweet-only weighted peak 5% mean：

```text
sweet fibers = {l in F_candidate_tau: M_HF(l) > 0}
weighted_l_i = X_HF_i(l) * M_HF(l)

HFFiberScore_top5_mean_i =
  mean(top 5% largest weighted_l_i among sweet fibers)
```

如果 full-sample map 或 LOOCV training fold 中没有 sweet fibers，则该 branch/fold 以 QC failure 停止。若存在 sweet fibers 但某个 patient 对这些 fibers 的 exposure 为 0，则 `HFFiberScore_top5_mean_i = 0`。

该 score 有意贴近 Nature Neuroscience 的 weighted peak Fiber R score，而不是 target-level aggregate。这里采用 mean 而不是 sum，以增强不同 fold candidate set 之间的可比性。

此前讨论过的 total fiber exposure score 仅作为文档中的概念保留，当前可执行分析不实际计算：

```text
HFFiberScore_sum_descriptive_i =
  sum_l X_HF_i(l) * M_HF(l)
```

最终预测模型：

```text
Y_post_i = alpha
         + delta * HFFiberScore_top5_mean_i
         + beta  * Y_base_i
         + error_i
```

prediction model 在 raw post-score 尺度上拟合。主验证统计量是 held-out prediction 与 held-out raw outcome 之间的 LOOCV Spearman rho。

## 验证与敏感性分析

- 主验证使用 leave-one-patient-out cross-validation。
- 每个 fold 内重建 `F_candidate_tau`、拟合 fiber weights、计算 training 和 held-out `HFFiberScore_top5_mean`，并且只用 training patients 拟合最终 prediction model。
- 与 covariate-only baseline `Y_post ~ Y_base` 比较。
- 主指标：LOOCV Spearman rho 和 plus-one permutation P value。
- 次要指标：LOOCV Pearson `r`、MAE、RMSE 和 `Q2`。
- Formal Freedman-Lane permutation 使用 `B=10000`、seed `42`，仅限 primary dTOR peak-E-field branch。
- Smoke permutation 使用 `B=1000`、seed `42`。
- Subject-level bootstrap 使用 `B=10000`、seed `42`，仅限 primary dTOR peak-E-field branch。

Reference sensitivities：

```text
1500 V/m candidate threshold sensitivity
top 1% positive fibers for display
top 1% sour fibers for display
top1500 positive / top500 negative fiber-score sensitivity for PPMI, MGH, and dTOR
OSS-DBS all-candidate sensitivity for PPMI, MGH, and dTOR
2 mm FWHM spatial jitter QC for dTOR selected/display fibers only
```

reference papers 中的 5-fold/10-fold CV 设置只写入 reference checklist。当前 `n=16` 执行不生成这些结果；LOOCV 是可执行验证设计。

## OSS-DBS 敏感性分析

OSS-DBS 在 `ossdbsv2` Conda 环境中运行，并对 PPMI、MGH 和 dTOR 的 all candidate fibers 生成。

OSS branch 用 pathway/axon activation 代替 peak E-field exposure：

```text
X_HF_OSS_i(l) = OSS-DBS activation value for fiber l under subject i HF stimulation
```

OSS branch 使用同样的 fiber-wise estimator、sweet-only top 5% scoring 和 LOOCV prediction workflow。OSS branch 只运行 smoke permutation：

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
```

每个 branch 必需输出：

```text
normative_HF_fiber_weights.csv
normative_HF_fiber_scores.csv
normative_HF_fiber_loocv_predictions.csv
normative_HF_fiber_permutation_summary.csv
normative_HF_fiber_mapping_qc.json
normative_HF_fiber_generation_manifest.json
normative_HF_fiber_display_top1_positive.tck
normative_HF_fiber_display_top1_positive.mat
normative_HF_fiber_display_top1_sour.tck
normative_HF_fiber_display_top1_sour.mat
normative_HF_fiber_density_map.nii.gz
```

Primary dTOR peak-E-field branch 额外输出：

```text
normative_HF_fiber_bootstrap_se.csv
normative_HF_fiber_jitter_summary.csv
```

OSS branch 额外输出：

```text
normative_HF_fiber_oss_activation_matrix_summary.csv
normative_HF_fiber_oss_loocv_predictions.csv
normative_HF_fiber_oss_permutation_summary.csv
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
is_top1_sour_display
is_top1500_positive
is_top500_negative
```

`normative_HF_fiber_scores.csv` 至少包括：

```text
subject_id
score_map_source
connectome
branch
HFFiberScore_top5_mean
n_candidate_fibers
n_sweet_fibers
n_top5_fibers
is_primary_score
```

`normative_HF_fiber_mapping_qc.json` 记录 candidate counts、coverage distribution、degenerate fiber counts、empty-fold failures、FDR method、target-label summaries、chunking parameters、memory use summaries 和 OSS-DBS status。

## 可视化

Target atlases 只在 fiber 建模之后用于 label 和 summary，不定义主预测变量。

Display outputs：

- 按 `M_HF(l)` 选取 top 1% positive fibers 用于 sweet streamline visualization；
- 按负向 `M_HF(l)` 选取 top 1% sour fibers 用于 avoidance/sour visualization；
- selected/display fibers 的 streamline density maps；
- target-label summary tables，说明 selected fibers 穿过或接触哪些 atlas targets；
- STN/SNr 和 STNSNrplus overlays 只作为解剖背景。

任何 display fiber subset 都不是统计显著性图。FDR q 值可以显示在 QC 表中，但 display 规则基于 rank/percentile 和方向稳定性，而不是 q-value threshold。

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
