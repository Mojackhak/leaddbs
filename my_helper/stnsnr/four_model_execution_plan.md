# Four-Model Execution Plan (Codex + Subagent Orchestration)

> **Purpose.** This is the `/goal` plan document for executing the four STN/SNr HF/ULF modeling tracks.
> **Authoritative model specs.** The English files under `my_helper/stnsnr/model_summaries/` define model-level executable behavior. This document defines cross-model orchestration, current implementation state, current gate/status results, and the next engineering priorities.
> **Workspace.** `/Users/mojackhu/.codex/worktrees/a409/leaddbs`
> **Last updated.** 2026-07-06

---

## 1. Goal

Run a reproducible, manifest-backed four-model program on the `n=16` STN/SNr DBS cohort:

1. **A: HF direct voxel model**
2. **B: HF normative connectome fiber model**
3. **C: ULF add-on direct voxel model**
4. **D: ULF add-on normative connectome fiber model**

The scientific goal is to separate:

```text
HF-only efficacy / association maps
HF-conditioned or HF-aware ULF-only add-on gain maps
```

Because `n=16`, all model outputs remain hypothesis-generating unless validated by the declared permutation, bootstrap, jitter, threshold-selection, or external-replication steps.

---

## 2. Authoritative Model Documents

| Model | Authoritative spec | Current role |
|---|---|---|
| A | `model_summaries/hf_3m_direct_voxel_model.md` | Foundational HF direct local sweet-spot model |
| B | `model_summaries/hf_3m_normative_connectome_fiber_model.md` | Foundational HF full-connectome fiber-filtering model |
| C | `model_summaries/ulf_addon_gain_direct_voxel_model.md` | ULF-only add-on voxel model with two core branch roles |
| D | `model_summaries/ulf_addon_gain_normative_connectome_fiber_model.md` | ULF-only add-on fiber model with two core branch roles |

Chinese `_zh.md` files are synchronized mirrors. If a conflict remains, the English model summary is the executable source of truth.

Out of scope for this four-model execution pass:

```text
hf_3m_individualized_dwi_seed_target_model.md
ulf_addon_gain_individualized_dwi_seed_target_model.md
OLS ANCOVA optional estimator
```

---

## 3. Four-Model Dependency Policy

### A/B Foundational HF Models

A and B are foundational HF models. They can run independently and in parallel:

```text
A = HF direct voxel, tau200/Coverage>=5 primary
B = HF normative fiber, tau800/Coverage>=5 primary
```

Their outputs are classified by fitted results:

```text
predictive_valid
stable_nonpredictive
failed_unstable
```

The strict target definition is:

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

C and D must not be treated as blocked simply because matched HF is not `predictive_valid`. Their engineering implementation should run both core branches whenever inputs allow:

```text
delta_hf_adjusted:
  ULF predictor + Y_HF_ref + DeltaHFScore

no_delta_hf:
  ULF predictor + Y_HF_ref
```

The interpretation role is resolved after reading the matched HF result:

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

Manifests for C/D must record:

```text
hf_prediction_validity_status
ulf_primary_branch
ulf_core_branches_run
delta_hfscore_role
branch_role_decision_reason
hf_model_support_status
```

---

## 4. Current Implementation State

The current codebase is no longer greenfield. The following layers already exist.

### Implemented

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

### Not Yet Implemented

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

`my_helper/stnsnr/four_model_execution_implementation_notes.md` records implementation-layer details and should be updated whenever a new executable layer is added.

---

## 5. Current Run State

Current status is based on existing outputs under:

```text
/Volumes/VAL/STNSNr/summary/four_model_execution/
```

### A/B Primary Observed Branches

Current `four_model_gate_status.csv` reports:

| Model | Branch | rho | Q2 | Gate |
|---|---:|---:|---:|---|
| A HF direct voxel | `tau200/partial_spearman` | `-0.0265` | `-0.2230` | `STOP_FORMAL_REMAIN_EXPLORATORY` |
| B PPMI | `peak_efield_tau800_primary` | `-0.1652` | `-0.4476` | `STOP_FORMAL_REMAIN_EXPLORATORY` |
| B MGH | `peak_efield_tau800_primary` | `-0.0855` | `-0.2916` | `STOP_FORMAL_REMAIN_EXPLORATORY` |
| B dTOR | `peak_efield_tau800_primary` | `-0.1829` | `-0.4976` | `STOP_FORMAL_REMAIN_EXPLORATORY` |

These observed branches exist and have finite predictions, but they do not justify formal primary-branch permutation/bootstrap. They should be reported as exploratory/negative unless a new pre-declared branch passes a valid gate.

### C/D ULF Readiness

Current execution status reports:

```text
ULF component e-fields: 64/64 existing
C dependency: A is exploratory/unstable
D dependency: B_dTOR is exploratory/unstable
```

Therefore C/D are executable only under the ULF branch-role policy:

```text
no_delta_hf = primary / primary exploratory
delta_hf_adjusted = sensitivity or unstable-generated-covariate branch
```

### A All-Scale Post-Hoc Scan

The A-model all-scale post-hoc scan exists at:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/posthoc_threshold_scan_all_scales/
  all_scales_posthoc_threshold_scan_long.csv
  all_scales_posthoc_threshold_scan_summary.csv
  all_scales_posthoc_threshold_scan_manifest.json
```

It contains:

```text
30 endpoints x 60 tau/Coverage grid cells = 1800 rows
```

This scan is **exploratory threshold optimization**. It does not replace the original primary `tau200/Coverage>=5` branch. A selected high-core threshold becomes a candidate branch only; to claim post-selection significance it still requires nested/adaptive LOOCV, max-stat permutation, independent endpoint replication, or prospective validation.

---

## 6. Gate Definitions

### Currently Implemented Gate

The current `run_stnsnr_four_model_gate_status.py` code uses a coarse observed-signal gate:

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

This is sufficient to prevent expensive formal loops from running on clearly negative observed branches.

### Target Gate To Align With Model Specs

The code should later be upgraded to emit the stricter HF state:

```text
predictive_valid
stable_nonpredictive
failed_unstable
```

The stricter target gate must include:

```text
Q2 > 0
MAE_model < MAE_baseline
RMSE_model < RMSE_baseline
score non-constant
all held-out predictions finite
no single high-leverage subject explains the result
threshold-neighborhood or resampling stability when available
```

Until that code alignment is implemented, the existing gate-status CSV should be interpreted as an engineering stop/go gate, not a complete scientific prediction-validity classifier.

---

## 7. Execution Order From Current State

### Immediate Next Steps

1. Keep A/B default primary branches labeled exploratory/negative; do not run formal B=10000 resampling on those failed branches.
2. If using A post-hoc high-core candidates, run post-selection validation before upgrading any branch:

   ```text
   nested/adaptive LOOCV
   max-stat permutation over the full tau/Coverage grid
   endpoint replication or external validation when possible
   ```

3. Implement C ULF direct voxel driver with both branches:

   ```text
   tau200/partial_spearman_delta_hf_adjusted
   tau200/partial_spearman_no_delta_hf
   ```

   Given the current A gate, the no-DeltaHF branch is the interpretation-primary branch unless a matched HF model is later upgraded to `predictive_valid`.

4. Implement D ULF normative fiber driver with both branches:

   ```text
   ulf_peak_efield_tau800_delta_hf_adjusted
   ulf_peak_efield_tau800_no_delta_hf
   ```

   Given the current B_dTOR gate, the no-DeltaHF branch is the interpretation-primary branch unless a matched HF fiber model is later upgraded to `predictive_valid`.

### Deferred Expensive Work

Do not run these until a branch passes the relevant gate:

```text
formal B=10000 permutation
formal B=10000 bootstrap
formal FWHM 2 mm jitter
OSS-DBS activation sensitivity
figure-grade FDR/enrichment/display outputs
```

---

## 8. Shared Implementation Contract

All implemented and future drivers must preserve:

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

For C/D:

```text
ULF-only predictor must exclude HF-overlap exposure
DeltaHFScore is model-derived and branch-role-dependent
HF out-of-support burden must be audited
```

For B/D:

```text
candidate universe is full public connectome
right-canonical streamline feature space
dTOR must be chunked/memmaped
NetFiberScore = SweetPeak5 - SourPeak5
```

---

## 9. Command Index

Run from the worktree:

```bash
cd /Users/mojackhu/.codex/worktrees/a409/leaddbs
```

M0 readiness:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_four_model_m0_readiness.py \
  --run-matlab-check
```

M1 shared stats selftest:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_four_model_m1_selftest.py
```

A HF direct voxel observed primary:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_hf_direct_voxel_smoke.py
```

A HF direct voxel post-hoc scan, one scale:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_hf_direct_voxel_posthoc_threshold_scan.py \
  --scale "MDS-UPDRS III score (STN, 3 m)"
```

A HF direct voxel post-hoc scan, all scales:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_hf_direct_voxel_posthoc_threshold_scan.py \
  --all-scales
```

A post-hoc plot-only refresh:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_hf_direct_voxel_posthoc_threshold_scan.py \
  --all-scales \
  --plot-only
```

B HF normative fiber observed branch:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_hf_normative_fiber_smoke.py \
  --connectome ppmi
```

A/B gate status:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_four_model_gate_status.py
```

ULF component readiness:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_component_readiness.py
```

ULF component e-field worklist:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_component_efield_worklist.py
```

Consolidated execution status:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_four_model_execution_status.py
```

---

## 10. Definition Of Done

This four-model program is complete only when:

```text
A and B have current observed branch summaries and explicit HF validity status.
C and D have both delta_hf_adjusted and no_delta_hf outputs when inputs allow.
Each model records which branch is interpretation-primary and why.
Every branch has QC JSON, manifest JSON, predictions CSV, and score CSV.
Formal resampling is run only for branches that pass the declared gate.
Post-hoc selected thresholds are never relabeled as original primary analysis.
The final report states n=16 and hypothesis-generating interpretation.
```
