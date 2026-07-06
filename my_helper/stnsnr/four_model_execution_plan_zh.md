# Four-Model 执行方案（Codex + Subagent Orchestration）

> **用途。** 这是执行 STN/SNr HF/ULF 四模型程序的 `/goal` 总方案文档。
> **权威模型规格。** `my_helper/stnsnr/model_summaries/` 下的英文文档定义各模型的 executable behavior。本文件定义跨模型编排、当前实现状态、当前 gate/status 结果和下一步工程优先级。
> **Workspace。** `/Users/mojackhu/.codex/worktrees/a409/leaddbs`
> **Last updated。** 2026-07-06

---

## 1. Goal

在 `n=16` STN/SNr DBS 队列上运行可复现、带 manifest 的四模型程序：

1. **A: HF direct voxel model**
2. **B: HF normative connectome fiber model**
3. **C: ULF add-on direct voxel model**
4. **D: ULF add-on normative connectome fiber model**

科学目标是区分：

```text
HF-only efficacy / association maps
HF-conditioned or HF-aware ULF-only add-on gain maps
```

由于样本量为 `n=16`，除非经过已声明的 permutation、bootstrap、jitter、threshold-selection 或外部复现验证，所有结果均应解释为 hypothesis-generating。

---

## 2. 权威模型文档

| Model | Authoritative spec | Current role |
|---|---|---|
| A | `model_summaries/hf_3m_direct_voxel_model.md` | Foundational HF direct local sweet-spot model |
| B | `model_summaries/hf_3m_normative_connectome_fiber_model.md` | Foundational HF full-connectome fiber-filtering model |
| C | `model_summaries/ulf_addon_gain_direct_voxel_model.md` | ULF-only add-on voxel model with two core branch roles |
| D | `model_summaries/ulf_addon_gain_normative_connectome_fiber_model.md` | ULF-only add-on fiber model with two core branch roles |

中文 `_zh.md` 文件是同步镜像。如仍存在冲突，以英文 model summary 作为 executable source of truth。

本轮 four-model execution 不包括：

```text
hf_3m_individualized_dwi_seed_target_model.md
ulf_addon_gain_individualized_dwi_seed_target_model.md
OLS ANCOVA optional estimator
```

---

## 3. 四模型依赖策略

### A/B Foundational HF Models

A 和 B 是 foundational HF 模型，可独立并行运行：

```text
A = HF direct voxel, tau200/Coverage>=5 primary
B = HF normative fiber, tau800/Coverage>=5 primary
```

其输出按拟合结果分类：

```text
predictive_valid
stable_nonpredictive
failed_unstable
```

严格目标定义为：

```text
predictive_valid:
  LOOCV rho > 0
  Q2 > 0
  MAE_model < MAE_baseline
  RMSE_model < RMSE_baseline
  score is not near-constant
  result is not dominated by one high-leverage subject

stable_nonpredictive:
  map/rank direction appears stable or biologically interpretable
  but Q2 <= 0 or MAE/RMSE do not improve over baseline

failed_unstable:
  negative or degenerate prediction
  unstable direction
  insufficient support
  non-finite predictions
  or obvious high-leverage/threshold-fragile behavior
```

### C/D ULF Branch Role Resolution

C 和 D 不应因为 matched HF 不是 `predictive_valid` 就完全阻断。只要输入允许，工程实现应同时运行两个核心分支：

```text
delta_hf_adjusted:
  ULF predictor + Y_HF_ref + DeltaHFScore

no_delta_hf:
  ULF predictor + Y_HF_ref
```

解释角色由 matched HF 结果决定：

```text
if matched HF is predictive_valid:
  ulf_primary_branch = delta_hf_adjusted
  delta_hfscore_role = primary_nuisance_adjustment
  no_delta_hf_role   = sensitivity

if matched HF is stable_nonpredictive:
  ulf_primary_branch = no_delta_hf
  delta_hfscore_role = unstable_generated_covariate_sensitivity
  no_delta_hf_role   = primary

if matched HF is failed_unstable:
  ulf_primary_branch = no_delta_hf when ULF inputs remain valid
  delta_hfscore_role = exploratory_only_or_not_run
  no_delta_hf_role   = primary exploratory branch
```

C/D manifest 必须记录：

```text
hf_prediction_validity_status
ulf_primary_branch
ulf_core_branches_run
delta_hfscore_role
branch_role_decision_reason
hf_model_support_status
```

---

## 4. 当前实现状态

当前代码已经不是 greenfield。以下层级已经存在。

### 已实现

| Layer | Pipeline entrypoint | Core implementation | Status |
|---|---|---|---|
| M0 readiness | `my_helper/fiber/stnsnr/run_stnsnr_four_model_m0_readiness.py` | `my_helper/fiber/core/analysis/stnsnr_four_model_readiness.py` | implemented |
| M1 stats selftest | `my_helper/fiber/stnsnr/run_stnsnr_four_model_m1_selftest.py` | `my_helper/fiber/core/analysis/stnsnr_four_model_stats.py` | implemented |
| A observed primary | `my_helper/fiber/stnsnr/run_stnsnr_hf_direct_voxel_smoke.py` | `my_helper/fiber/core/analysis/stnsnr_hf_direct_voxel_smoke.py` | implemented |
| A post-hoc scan | `my_helper/fiber/stnsnr/run_stnsnr_hf_direct_voxel_posthoc_threshold_scan.py` | `my_helper/fiber/core/analysis/stnsnr_hf_direct_voxel_posthoc_threshold_scan.py` | implemented |
| B observed primary | `my_helper/fiber/stnsnr/run_stnsnr_hf_normative_fiber_smoke.py` | `my_helper/fiber/core/analysis/stnsnr_hf_normative_fiber_smoke.py` | implemented |
| A/B gate status | `my_helper/fiber/stnsnr/run_stnsnr_four_model_gate_status.py` | `my_helper/fiber/core/analysis/stnsnr_four_model_gate_status.py` | implemented |
| Four-model status | `my_helper/fiber/stnsnr/run_stnsnr_four_model_execution_status.py` | `my_helper/fiber/core/analysis/stnsnr_four_model_execution_status.py` | implemented |
| ULF component readiness | `my_helper/fiber/stnsnr/run_stnsnr_ulf_component_readiness.py` | `my_helper/fiber/core/analysis/stnsnr_ulf_component_readiness.py` | implemented |
| ULF e-field worklist | `my_helper/fiber/stnsnr/run_stnsnr_ulf_component_efield_worklist.py` | `my_helper/fiber/core/analysis/stnsnr_ulf_component_efield_worklist.py` | implemented |
| Raw clinical rebuild | direct core script | `my_helper/fiber/core/analysis/stnsnr_rebuild_subject_effect_origin.py` | implemented |

### 尚未实现

```text
C formal ULF direct voxel model driver
D formal ULF normative fiber model driver
formal B=10000 permutation/bootstrap loops
formal spatial jitter loops
OSS-DBS activation branch
nested/adaptive post-hoc threshold validation
max-stat permutation for post-hoc threshold selection
OLS ANCOVA optional estimator
figure-grade display/FDR/enrichment layers beyond existing post-hoc heatmaps
```

`my_helper/stnsnr/four_model_execution_implementation_notes.md` 记录 implementation-layer 细节。每新增一个 executable layer 后都应同步更新该文件。

---

## 5. 当前运行状态

当前状态基于以下目录中的既有输出：

```text
/Volumes/VAL/STNSNr/summary/four_model_execution/
```

### A/B Primary Observed Branches

当前 `four_model_gate_status.csv` 报告：

| Model | Branch | rho | Q2 | Gate |
|---|---:|---:|---:|---|
| A HF direct voxel | `tau200/partial_spearman` | `-0.0265` | `-0.2230` | `STOP_FORMAL_REMAIN_EXPLORATORY` |
| B PPMI | `peak_efield_tau800_primary` | `-0.1652` | `-0.4476` | `STOP_FORMAL_REMAIN_EXPLORATORY` |
| B MGH | `peak_efield_tau800_primary` | `-0.0855` | `-0.2916` | `STOP_FORMAL_REMAIN_EXPLORATORY` |
| B dTOR | `peak_efield_tau800_primary` | `-0.1829` | `-0.4976` | `STOP_FORMAL_REMAIN_EXPLORATORY` |

这些 observed branches 已存在且 predictions finite，但不足以支持 formal primary-branch permutation/bootstrap。除非新的预声明分支通过有效 gate，否则应报告为 exploratory/negative。

### C/D ULF Readiness

当前 execution status 报告：

```text
ULF component e-fields: 64/64 existing
C dependency: A is exploratory/unstable
D dependency: B_dTOR is exploratory/unstable
```

因此 C/D 只能按 ULF branch-role policy 执行和解释：

```text
no_delta_hf = primary / primary exploratory
delta_hf_adjusted = sensitivity or unstable-generated-covariate branch
```

### A All-Scale Post-Hoc Scan

A-model all-scale post-hoc scan 已存在于：

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/posthoc_threshold_scan_all_scales/
  all_scales_posthoc_threshold_scan_long.csv
  all_scales_posthoc_threshold_scan_summary.csv
  all_scales_posthoc_threshold_scan_manifest.json
```

其中包含：

```text
30 endpoints x 60 tau/Coverage grid cells = 1800 rows
```

该 scan 属于 **exploratory threshold optimization**，不能替代原始 primary `tau200/Coverage>=5` branch。被选中的 high-core threshold 只能作为 candidate branch；若要声称 post-selection significance，仍需 nested/adaptive LOOCV、max-stat permutation、独立 endpoint 复现或前瞻性验证。

---

## 6. Gate Definitions

### 当前已实现 Gate

当前 `run_stnsnr_four_model_gate_status.py` 使用较粗的 observed-signal gate：

```text
PASS_TO_NEXT_ROUND:
  output exists
  predictions are finite
  LOOCV Spearman rho > 0
  Q2 >= 0

STOP_FORMAL_REMAIN_EXPLORATORY:
  output exists
  predictions are finite
  but rho <= 0 or Q2 < 0
```

这个 gate 足以阻止在明显 negative observed branch 上运行昂贵 formal loops。

### 后续应对齐的目标 Gate

后续代码应升级为输出更严格的 HF state：

```text
predictive_valid
stable_nonpredictive
failed_unstable
```

更严格的目标 gate 需要纳入：

```text
Q2 > 0
MAE_model < MAE_baseline
RMSE_model < RMSE_baseline
score non-constant
all held-out predictions finite
no single high-leverage subject explains the result
threshold-neighborhood or resampling stability when available
```

在该代码对齐完成前，现有 gate-status CSV 应解释为工程 stop/go gate，而不是完整科学 prediction-validity classifier。

---

## 7. 从当前状态出发的执行顺序

### Immediate Next Steps

1. 将 A/B 默认 primary branches 保持标记为 exploratory/negative；不要在这些 failed branches 上运行 formal B=10000 resampling。
2. 若使用 A post-hoc high-core candidates，先运行 post-selection validation：

   ```text
   nested/adaptive LOOCV
   max-stat permutation over the full tau/Coverage grid
   endpoint replication or external validation when possible
   ```

3. 实现 C ULF direct voxel driver，并同时运行：

   ```text
   tau200/partial_spearman_delta_hf_adjusted
   tau200/partial_spearman_no_delta_hf
   ```

   在当前 A gate 下，除非 matched HF model 后续升级为 `predictive_valid`，否则 no-DeltaHF branch 是解释上的 primary branch。

4. 实现 D ULF normative fiber driver，并同时运行：

   ```text
   ulf_peak_efield_tau800_delta_hf_adjusted
   ulf_peak_efield_tau800_no_delta_hf
   ```

   在当前 B_dTOR gate 下，除非 matched HF fiber model 后续升级为 `predictive_valid`，否则 no-DeltaHF branch 是解释上的 primary branch。

### Deferred Expensive Work

除非分支通过相应 gate，否则不要运行：

```text
formal B=10000 permutation
formal B=10000 bootstrap
formal FWHM 2 mm jitter
OSS-DBS activation sensitivity
figure-grade FDR/enrichment/display outputs
```

---

## 8. Shared Implementation Contract

所有现有和未来 drivers 必须保持：

```text
Conda environment: leaddbs
random seed: 42
left/right flip: ea_flip_lr_nonlinear
raw E-field input: sim-efield, not sim-efieldgauss
HF frequency: >=100 Hz
ULF frequency: <=50 Hz
no full-sample ranks inside LOOCV
no full-sample map/F+/F- for held-out scoring
no anatomical overlay mask as statistical ROI
manifest and QC for every branch
```

对于 C/D：

```text
ULF-only predictor must exclude HF-overlap exposure
DeltaHFScore is model-derived and branch-role-dependent
HF out-of-support burden must be audited
```

对于 B/D：

```text
candidate universe is full public connectome
right-canonical streamline feature space
dTOR must be chunked/memmaped
NetFiberScore = SweetPeak5 - SourPeak5
```

---

## 9. Command Index

从 worktree 运行：

```bash
cd /Users/mojackhu/.codex/worktrees/a409/leaddbs
```

M0 readiness：

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_four_model_m0_readiness.py \
  --run-matlab-check
```

M1 shared stats selftest：

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_four_model_m1_selftest.py
```

A HF direct voxel observed primary：

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_hf_direct_voxel_smoke.py
```

A HF direct voxel post-hoc scan，单一 scale：

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_hf_direct_voxel_posthoc_threshold_scan.py \
  --scale "MDS-UPDRS III score (STN, 3 m)"
```

A HF direct voxel post-hoc scan，全部 scales：

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_hf_direct_voxel_posthoc_threshold_scan.py \
  --all-scales
```

A post-hoc plot-only refresh：

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_hf_direct_voxel_posthoc_threshold_scan.py \
  --all-scales \
  --plot-only
```

B HF normative fiber observed branch：

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_hf_normative_fiber_smoke.py \
  --connectome ppmi
```

A/B gate status：

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_four_model_gate_status.py
```

ULF component readiness：

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_component_readiness.py
```

ULF component e-field worklist：

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_component_efield_worklist.py
```

Consolidated execution status：

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_four_model_execution_status.py
```

---

## 10. Definition Of Done

Four-model program 完成的最低条件为：

```text
A and B have current observed branch summaries and explicit HF validity status.
C and D have both delta_hf_adjusted and no_delta_hf outputs when inputs allow.
Each model records which branch is interpretation-primary and why.
Every branch has QC JSON, manifest JSON, predictions CSV, and score CSV.
Formal resampling is run only for branches that pass the declared gate.
Post-hoc selected thresholds are never relabeled as original primary analysis.
The final report states n=16 and hypothesis-generating interpretation.
```
