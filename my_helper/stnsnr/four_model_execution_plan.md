# Four-Model Execution Plan (Codex + Subagent Orchestration)

> **Purpose.** This is the `/goal` plan document for executing the four STN/SNr HF/ULF modeling tracks.
> **Authoritative model specs.** The English files under `my_helper/stnsnr/model_summaries/` define model-level executable behavior. This document defines cross-model orchestration, current implementation state, current gate/status results, and the next engineering priorities.
> **Workspace.** `/Users/mojackhu/Github/leaddbs`
> **Last updated.** 2026-07-06

---

## Pause Checkpoint

Execution is paused after the 2026-07-06 status refresh. The current checkpoint
has completed only observed/non-formal branches and lightweight readiness/status
generation:

```text
A HF direct voxel observed branch rerun from /Users/mojackhu/Github/leaddbs
B PPMI/MGH/dTOR HF normative fiber observed branches rerun from /Users/mojackhu/Github/leaddbs
C ULF direct voxel observed branches rerun from /Users/mojackhu/Github/leaddbs
D ULF normative fiber PPMI observed branches rerun from /Users/mojackhu/Github/leaddbs
A/B gate status refreshed with explicit hf_prediction_validity_status
ULF readiness refreshed with C -> A and D PPMI -> B_PPMI dependency mapping
Consolidated status refreshed under /Volumes/VAL/STNSNr/summary/four_model_execution/status/
```

Current gate result:

```text
A, B_PPMI, B_MGH, B_DTOR = failed_unstable
C, D = OBSERVED_COMPLETE_EXPLORATORY
formal permutation/bootstrap/jitter/OSS = not run, correctly skipped by gate
```

Do not continue execution from this checkpoint unless explicitly resumed.

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
| C observed ULF direct voxel | `my_helper/fiber/stnsnr/run_stnsnr_ulf_direct_voxel_observed.py` | `my_helper/fiber/core/analysis/stnsnr_ulf_direct_voxel_observed.py` | implemented |
| D observed ULF normative fiber PPMI | `my_helper/fiber/stnsnr/run_stnsnr_ulf_normative_fiber_observed.py` | `my_helper/fiber/core/analysis/stnsnr_ulf_normative_fiber_observed.py` | implemented |
| Raw clinical rebuild | direct core script | `my_helper/fiber/core/analysis/stnsnr_rebuild_subject_effect_origin.py` | implemented |

### Not Yet Implemented

```text
C formal ULF direct voxel resampling, gain endpoints, total-ULF sensitivity, and all-scale driver
D formal ULF normative fiber resampling, dTOR main branch, OSS, and figure-grade outputs
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

| Model | Branch | rho | Q2 | Gate | HF validity |
|---|---:|---:|---:|---|---|
| A HF direct voxel | `tau200/partial_spearman` | `-0.0265` | `-0.2230` | `STOP_FORMAL_REMAIN_EXPLORATORY` | `failed_unstable` |
| B PPMI | `peak_efield_tau800_primary` | `-0.1652` | `-0.4476` | `STOP_FORMAL_REMAIN_EXPLORATORY` | `failed_unstable` |
| B MGH | `peak_efield_tau800_primary` | `-0.0855` | `-0.2916` | `STOP_FORMAL_REMAIN_EXPLORATORY` | `failed_unstable` |
| B dTOR | `peak_efield_tau800_primary` | `-0.1829` | `-0.4976` | `STOP_FORMAL_REMAIN_EXPLORATORY` | `failed_unstable` |

These observed branches exist and have finite predictions, but their explicit
HF validity state is `failed_unstable`; they do not justify formal
primary-branch permutation/bootstrap. They should be reported as
exploratory/negative unless a new pre-declared branch passes a valid gate.

### C/D ULF Readiness

Current execution status reports:

```text
ULF component e-fields: 64/64 existing
C dependency: A is exploratory/unstable
D PPMI dependency: B_PPMI is exploratory/unstable
```

Therefore C/D are executable only under the ULF branch-role policy:

```text
no_delta_hf = primary / primary exploratory
delta_hf_adjusted = sensitivity or unstable-generated-covariate branch
```

### C ULF Direct Voxel Observed Branch

The C observed-only driver has been implemented and run for the default chronic endpoint:

```text
post scale = MDS-UPDRS III score (STN+SNr, 3 m)
HF reference = MDS-UPDRS III score (STN, 3 m)
output root = /Volumes/VAL/STNSNr/summary/direct_voxel/ulf/mds_updrs_iii_score_stn_snr_3_m/tau200/
```

Current observed outputs:

| Branch | rho | Q2 | Interpretation role |
|---|---:|---:|---|
| `partial_spearman_no_delta_hf` | `0.9190` | `-0.1442` | interpretation-primary under current failed HF dependency, but not predictive by Q2 |
| `partial_spearman_delta_hf_adjusted` | `0.9543` | `0.1238` | unstable-generated-covariate sensitivity because matched A primary HF is `failed_unstable` |

Both branches write scores, LOOCV predictions, NIfTI maps, QC JSON, and manifests. Formal resampling remains gated and has not been run.

### D ULF Normative Fiber Observed Branch

The D observed-only driver has been implemented and run for the default chronic endpoint and PPMI connectome:

```text
post scale = MDS-UPDRS III score (STN+SNr, 3 m)
HF reference = MDS-UPDRS III score (STN, 3 m)
connectome = PPMI 85 (Ewert 2017)
output root = /Volumes/VAL/STNSNr/summary/normative_connectome_fiber/ulf/ppmi_85_ewert_2017/mds_updrs_iii_score_stn_snr_3_m/peak_efield_tau800_observed/
```

Current observed outputs:

| Branch | rho | Q2 | Interpretation role |
|---|---:|---:|---|
| `ulf_peak_efield_tau800_no_delta_hf` | `0.9293` | `0.0922` | interpretation-primary under current failed B_PPMI dependency |
| `ulf_peak_efield_tau800_delta_hf_adjusted` | `0.9411` | `0.1170` | unstable-generated-covariate sensitivity because matched B_PPMI primary HF is `failed_unstable` |

Both branches write scores, LOOCV predictions, fiber weights, QC JSON, and manifests. Formal resampling, OSS-DBS activation, density maps, endpoint enrichment, and dTOR-scale figure-grade outputs remain gated and have not been run.

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

Post-hoc candidates are level-gated before ULF propagation:

```text
Level 0 failed_grid_cell:
  fails any hard filter
  ULF propagation = not allowed

Level 1 fragile_exploratory_candidate:
  hard filters pass, but support is isolated/fragile or Q2 < 0.05
  ULF propagation = not recommended

Level 2 usable_exploratory_candidate:
  hard filters pass, n_passing_grid_cells >= 3, at least 1 adjacent support cell,
  positive neighboring rho direction, selected Q2 > 0.05, and interpretable map
  ULF propagation = exploratory DeltaHFScore sensitivity only

Level 3 robust_exploratory_candidate:
  Level 2 plus n_passing_grid_cells >= 5, at least 2 adjacent support cells,
  selected Q2 >= 0.10, nominal p < 0.05, and no obvious single-subject leverage
  ULF propagation = priority exploratory DeltaHFScore sensitivity

Level 4 post_selection_validated_hf_model:
  post-selection validation passes by nested/adaptive LOOCV or equivalent validation
  ULF propagation = may define a primary DeltaHF-adjusted ULF candidate
```

For ULF, Level 2/3 candidates are sensitivity-only. Only an original primary `predictive_valid` HF model or a Level 4 post-selection validated HF model can define primary `DeltaHFScore`. Per endpoint, only one selected post-hoc candidate may be propagated; neighboring cells are robustness evidence and must not be added as separate covariates.

---

## 6. Gate Definitions

### Currently Implemented Gate

The current `run_stnsnr_four_model_gate_status.py` code emits two related
fields:

```text
decision = coarse engineering stop/go gate
hf_prediction_validity_status = explicit HF model validity state
```

The coarse engineering gate remains:

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

The explicit HF validity state is:

```text
predictive_valid:
  rho > 0, Q2 > 0, model MAE/RMSE improve over baseline,
  score is non-constant, and residual-dominance proxy does not flag a single
  subject as dominating the result

stable_nonpredictive:
  output exists and predictions are finite, but the available predictive
  checks do not justify predictive_valid

failed_unstable:
  missing output, non-finite prediction, rho <= 0, Q2 <= 0,
  degenerate score, or otherwise failed observed prediction
```

The residual-dominance proxy is an implementation-level screen, not a full
influence analysis. If it blocks a candidate branch, the manifest should make
that reason explicit and the branch should remain exploratory.

This is sufficient to prevent expensive formal loops from running on clearly
negative observed branches while also satisfying the model requirement that A/B
carry an explicit HF validity status.

### Future Gate Extensions

Future code may add stronger diagnostics around the same state labels:

```text
formal influence diagnostics
threshold-neighborhood stability summaries
resampling stability summaries
```

These diagnostics should refine the evidence behind `predictive_valid` rather
than redefine post-hoc selected branches as original primary analyses.


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

3. C ULF direct voxel observed has been implemented with both branches:

   ```text
   tau200/partial_spearman_delta_hf_adjusted
   tau200/partial_spearman_no_delta_hf
   ```

   Given the current A gate, the no-DeltaHF branch is the interpretation-primary branch unless a matched HF model is later upgraded to `predictive_valid`.

4. D ULF normative fiber PPMI observed has been implemented with both branches:

   ```text
   ulf_peak_efield_tau800_delta_hf_adjusted
   ulf_peak_efield_tau800_no_delta_hf
   ```

   Given the current B_PPMI gate, the no-DeltaHF branch is the interpretation-primary branch unless a matched HF fiber model is later upgraded to `predictive_valid`. dTOR main execution remains deferred until a justified fiber branch passes the relevant gate or is explicitly run as exploratory.

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

### Backend / Workflow Separation

All new code must preserve a strict separation between reusable backend logic and
the STN/SNr project workflow.

Backend code belongs under:

```text
my_helper/fiber/core/
```

Backend responsibilities:

```text
statistical estimators
LOOCV / permutation / bootstrap kernels
voxel and streamline feature-matrix operations
NIfTI / connectome / sidecar readers and writers
generic score construction
generic QC table and manifest helpers
```

Generic NIfTI writers must accept an explicit support mask. For continuous/statistical maps, voxels outside that support are written as `NaN`; coverage/count maps and binary masks are the only outputs that use `0` outside support.

Backend code must be parameterized. It must not hard-code:

```text
/Users/mojackhu/... project paths
/Volumes/VAL/STNSNr/... output roots
STN/SNr-specific endpoint names as algorithm defaults
specific atlas folders or label choices
specific connectome choices as scientific defaults
specific subject IDs
```

STN/SNr workflow code belongs under:

```text
my_helper/fiber/stnsnr/
```

Workflow responsibilities:

```text
project path resolution
default endpoint selection
default connectome selection
atlas and ROI registry selection
STN/SNr-specific branch naming
calling backend functions with explicit config
recording project-specific manifests
```

Thin workflow scripts may call backend modules, but backend modules must remain
usable with explicit paths and parameters supplied by the workflow. If a backend
needs defaults for local convenience, those defaults must be overridable and
must not define the scientific model.

---

## 9. Command Index

Run from the worktree:

```bash
cd /Users/mojackhu/Github/leaddbs
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

C ULF direct voxel observed branch:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_direct_voxel_observed.py
```

D ULF normative fiber PPMI observed branch:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_normative_fiber_observed.py --connectome ppmi
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
