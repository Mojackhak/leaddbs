# Four-Model Execution Plan (Codex + Subagent Orchestration)

> **Purpose.** This is the `/goal` plan document for executing the four STN/SNr HF/ULF modeling tracks.
> **Authoritative model specs.** The English files under `my_helper/stnsnr/model_summaries/` define model-level executable behavior. This document defines cross-model orchestration, current implementation state, current status results, and the next engineering priorities.
> **Workspace.** `/Users/mojackhu/Github/leaddbs`
> **Last updated.** 2026-07-06

---

## Pause Checkpoint

Execution is paused after the 2026-07-06 status refresh. The current checkpoint
has completed only observed/non-formal branches and lightweight readiness/status
generation:

```text
A HF direct voxel observed branch rerun from /Users/mojackhu/Github/leaddbs
B PPMI/MGH/dTOR HF normative fiber observed branches rerun from /Users/mojackhu/Github/leaddbs using the legacy/current output branch name that maps to revised `peak_efield_tau800_cov5_primary`
C ULF direct voxel observed branches rerun from /Users/mojackhu/Github/leaddbs
D ULF normative fiber PPMI observed branches rerun from /Users/mojackhu/Github/leaddbs using legacy/current output branch names that map to revised cov5 branch names
legacy/current A/B status CSV refreshed
ULF readiness refreshed with C -> A and D PPMI -> B_PPMI dependency mapping
Consolidated status refreshed under /Volumes/VAL/STNSNr/summary/four_model_execution/status/
```

Current status snapshot:

```text
A direct voxel = observed output exists; intended resolver fields require refresh
B_PPMI, B_MGH, B_DTOR = normative-fiber status fields available
C, D = OBSERVED_COMPLETE_EXPLORATORY
formal permutation/bootstrap/jitter/OSS = not run
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
B = HF normative fiber, peak_efield_tau800_cov5_primary
```

A and B now use different HF dependency vocabularies. A direct voxel uses the source resolver below; B normative fiber keeps the revised normative-fiber validity and burden rules.

```text
A direct voxel source status:
  pre_specified_accepted
  scan_fallback_accepted
  absent_no_stable_grid

A direct voxel prediction status:
  error_predictive
  error_nonpredictive
  not_applicable

B normative fiber validity status:
  predictive_valid
  stable_nonpredictive
  failed_unstable
```

### C/D ULF Branch Role Resolution

C and D must not be treated as blocked simply because the matched HF model is not predictive under its model-specific vocabulary. Their engineering implementation should run both core branches whenever inputs allow:

```text
delta_hf_adjusted:
  ULF predictor + Y_HF_ref + DeltaHFScore

no_delta_hf:
  ULF predictor + Y_HF_ref
```

The interpretation role is resolved after reading the matched HF result:

```text
if matched A direct voxel source exists:
  run delta_hf_adjusted
  run no_delta_hf

if matched A direct voxel hf_voxel_prediction_status is error_predictive:
  ulf_primary_branch = delta_hf_adjusted
  delta_hfscore_role = primary_error_predictive_hf_adjustment
  no_delta_hf_role   = sensitivity

if matched A direct voxel hf_voxel_prediction_status is error_nonpredictive:
  ulf_primary_branch = no_delta_hf
  delta_hfscore_role = stable_error_nonpredictive_hf_adjustment_sensitivity
  no_delta_hf_role   = primary

if matched A direct voxel source is absent_no_stable_grid:
  run no_delta_hf only
  ulf_primary_branch = no_delta_hf
  delta_hfscore_role = not_run_no_stable_hf_voxel_source

if matched B normative fiber is predictive_valid and not burden_dominated:
  ulf_primary_branch = delta_hf_adjusted
  delta_hfscore_role = primary_nuisance_adjustment

if matched B normative fiber is stable_nonpredictive, failed_unstable, or burden_dominated:
  ulf_primary_branch = no_delta_hf
  delta_hfscore_role = sensitivity_or_not_run_by_normative_fiber_status
```

Manifests for C/D must record:

```text
hf_voxel_source_status, for C/A direct-voxel dependencies
hf_voxel_prediction_status, for C/A direct-voxel dependencies
hf_voxel_threshold_source, for C/A direct-voxel dependencies
hf_voxel_selected_tau_v_per_m, for C/A direct-voxel dependencies
hf_voxel_selected_coverage, for C/A direct-voxel dependencies
hf_voxel_selected_adjacent_passing_grid_cells, for C/A direct-voxel dependencies
hf_norm_fiber_prediction_validity_status, for D/B normative fiber dependencies
hf_norm_fiber_burden_dominated, for D/B normative fiber dependencies
hf_norm_fiber_threshold_source, for D/B normative fiber dependencies
hf_norm_fiber_selected_tau_v_per_m, for D/B normative fiber dependencies
hf_norm_fiber_selected_coverage, for D/B normative fiber dependencies
hf_norm_fiber_posthoc_candidate_level, for D/B normative fiber dependencies
ulf_voxel_source_status, for C direct-voxel branch status
ulf_voxel_prediction_status, for C direct-voxel branch status
ulf_endpoint_model_status, for C direct-voxel endpoint status
ulf_branch_input_status, for C direct-voxel branch status
branch_nuisance_design_status, for C direct-voxel branches
ulf_primary_branch
ulf_core_branches_run
delta_hfscore_role
delta_hfscore_allowed_role
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
| Legacy A/B status CSV | `my_helper/fiber/stnsnr/run_stnsnr_four_model_gate_status.py` | `my_helper/fiber/core/analysis/stnsnr_four_model_gate_status.py` | implemented |
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

Current `four_model_gate_status.csv` was generated by older status code. For A direct voxel, it is not the intended resolver output; refresh A from `hf_voxel_source_status` and `hf_voxel_prediction_status` before using it as a C-model dependency.

| Model | Branch | rho | Q2 | Intended dependency field |
|---|---|---:|---:|---|
| A HF direct voxel | `tau200/partial_spearman` | `-0.0265` | `-0.2230` | refresh from `hf_voxel_source_status` and `hf_voxel_prediction_status` |
| B PPMI | legacy/current output `peak_efield_tau800_primary`; revised spec `peak_efield_tau800_cov5_primary` | `-0.1652` | `-0.4476` | `hf_norm_fiber_prediction_validity_status` |
| B MGH | legacy/current output `peak_efield_tau800_primary`; revised spec `peak_efield_tau800_cov5_primary` | `-0.0855` | `-0.2916` | `hf_norm_fiber_prediction_validity_status` |
| B dTOR | legacy/current output `peak_efield_tau800_primary`; revised spec `peak_efield_tau800_cov5_primary` | `-0.1829` | `-0.4976` | `hf_norm_fiber_prediction_validity_status` |

These observed branches exist and have finite predictions in the current snapshot. For B normative fiber, the revised normative-fiber validity fields remain the active dependency record.

### C/D ULF Readiness

Current execution status reports available ULF component inputs:

```text
ULF component e-fields: 64/64 existing
```

Under the revised direct-voxel resolver, C is executable with both branches when a stable HF voxel source exists; the primary branch is `delta_hf_adjusted` only if `hf_voxel_prediction_status = error_predictive`. D continues to follow the normative-fiber branch-role policy:

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
| `partial_spearman_no_delta_hf` | `0.9190` | `-0.1442` | legacy/current interpretation-primary; revised role awaits direct-voxel resolver refresh |
| `partial_spearman_delta_hf_adjusted` | `0.9543` | `0.1238` | legacy/current sensitivity; revised role awaits `hf_voxel_prediction_status` |

Both branches write scores, LOOCV predictions, NIfTI maps, QC JSON, and manifests. Formal resampling has not been run.

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
| legacy/current output `ulf_peak_efield_tau800_no_delta_hf`; revised spec `ulf_peak_efield_tau800_cov5_no_delta_hf` | `0.9293` | `0.0922` | interpretation-primary under current failed B_PPMI dependency |
| legacy/current output `ulf_peak_efield_tau800_delta_hf_adjusted`; revised spec `ulf_peak_efield_tau800_cov5_delta_hf_adjusted` | `0.9411` | `0.1170` | unstable-generated-covariate sensitivity because matched B_PPMI primary HF is `failed_unstable` |

Both branches write scores, LOOCV predictions, fiber weights, QC JSON, and manifests. Formal resampling, OSS-DBS activation, density maps, endpoint enrichment, and dTOR-scale figure-grade outputs have not been run.

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

The scan is used by the A-model source resolver only if the pre-specified `tau200/Coverage>=5` branch is not accepted. The hard computability filter is:

```text
n_subjects >= 12
n_voxels_full >= 20
fold_n_voxels_min >= 10
HFScore nonconstant in all folds
all predictions finite
```

If the pre-specified grid and at least 2 adjacent grid cells pass the filter, `hf_voxel_source_status = pre_specified_accepted`. Otherwise, the fallback grid is selected by distance to `tau200/Coverage>=5`, adjacent support count, `fold_n_voxels_min`, stricter Coverage, and then higher tau. If no stable grid exists, `hf_voxel_source_status = absent_no_stable_grid`.

`MAE_model < MAE_baseline` and `RMSE_model < RMSE_baseline` define `hf_voxel_prediction_status = error_predictive`; otherwise an accepted source is `error_nonpredictive`. `Q2` and LOOCV Spearman rho are report metrics, not direct-voxel source filters.

### B Normative Fiber Post-Hoc Threshold Scan Status

The revised B-model specification adds an executable exploratory scan:

```text
branch = posthoc_tau_coverage_threshold_scan
tau_grid_v_per_m = [400, 600, 800, 1000, 1200, 1500, 2000]
coverage_grid = [5, 6, 7, 8, 10, 12]
```

No B-model normative fiber threshold-scan output is assumed to exist in the current status snapshot. If it is run later, the original tau800/Coverage>=5 branch remains `peak_efield_tau800_cov5_primary`; a selected post-hoc B candidate may feed D only as a separately named `DeltaHFScore` sensitivity unless it reaches Level 4 post-selection validation.

---

## 6. Resolver Definitions

A direct voxel uses `hf_voxel_source_status` and `hf_voxel_prediction_status`. `Q2`, LOOCV rho, permutation p values, bootstrap stability, and jitter stability are reporting fields and do not define A source existence or prediction status.

B normative fiber uses its model-specific validity, burden, and post-hoc Level rules. Those normative-fiber fields do not apply to direct voxel models.


---

## 7. Execution Order From Current State

### Immediate Next Steps

1. Refresh A direct voxel from the intended source/prediction resolver before assigning C branch roles from A.
2. C ULF direct voxel observed has been implemented with both branches:

   ```text
   tau200/partial_spearman_delta_hf_adjusted
   tau200/partial_spearman_no_delta_hf
   ```

   Under the revised A resolver, the DeltaHF-adjusted branch is primary only when the matched HF direct-voxel source exists and `hf_voxel_prediction_status = error_predictive`; otherwise no-DeltaHF is primary or the only branch. Each executed C branch must also record its own `ulf_voxel_source_status` and `ulf_voxel_prediction_status`; these ULF statuses qualify whether the HF-selected primary branch is stable and error-predictive, but they do not change the HF-derived branch role.

3. D ULF normative fiber PPMI observed has been implemented with both branches:

   ```text
   legacy/current output: ulf_peak_efield_tau800_delta_hf_adjusted
   revised spec:          ulf_peak_efield_tau800_cov5_delta_hf_adjusted

   legacy/current output: ulf_peak_efield_tau800_no_delta_hf
   revised spec:          ulf_peak_efield_tau800_cov5_no_delta_hf
   ```

   Given the current B_PPMI normative-fiber status, the no-DeltaHF branch is the interpretation-primary branch unless a matched HF fiber model is later upgraded to `predictive_valid` and not burden-dominated, or a selected normative-fiber HF source reaches post-hoc Level 4. dTOR main execution remains deferred until a justified fiber branch satisfies the relevant normative-fiber status criteria or is explicitly run as exploratory.

### Deferred Expensive Work

Run these only after the relevant resolver/status fields identify the branch to report:

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

Legacy A/B status CSV:

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
A has current direct-voxel source/prediction status; B has current normative-fiber validity status.
C and D have both delta_hf_adjusted and no_delta_hf outputs when inputs allow.
Each model records which branch is interpretation-primary and why.
Every branch has QC JSON, manifest JSON, predictions CSV, and score CSV.
Formal resampling is tied to the resolver-selected reporting branch.
Post-hoc selected thresholds are never relabeled as original primary analysis.
The final report states n=16 and hypothesis-generating interpretation.
```
