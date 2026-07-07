# Four-Model Execution Plan (Codex + Subagent Orchestration)

> **Purpose.** This is the `/goal` plan document for executing the four STN/SNr HF/ULF modeling tracks.
> **Authoritative model specs.** The English files under `my_helper/stnsnr/model_summaries/` define model-level executable behavior. This document defines cross-model orchestration, current implementation state, current status results, and the next engineering priorities.
> **Workspace.** `/Users/mojackhu/Github/leaddbs`
> **Last updated.** 2026-07-07

---

## Pause Checkpoint

Execution is paused after the 2026-07-07 status refresh. The current checkpoint
has completed only observed/non-formal branches and lightweight readiness/status
generation:

```text
A HF direct voxel observed branch rerun from /Users/mojackhu/Github/leaddbs
B PPMI/MGH/dTOR HF normative fiber observed branches rerun from /Users/mojackhu/Github/leaddbs using the legacy/current output branch name that maps to revised `peak_efield_tau800_cov5_primary`
C ULF direct voxel observed branches rerun from /Users/mojackhu/Github/leaddbs
D ULF normative fiber PPMI observed branches rerun from /Users/mojackhu/Github/leaddbs using selected-source tau600 scan-fallback output branches
legacy/current A/B status CSV refreshed
ULF readiness refreshed with C -> A and D PPMI -> B_PPMI dependency mapping
C direct voxel source resolver refreshed
D PPMI normative fiber source resolver refreshed
Consolidated status refreshed under /Volumes/VAL/STNSNr/summary/four_model_execution/status/
```

Current status snapshot after the source-resolver refresh already performed in
this branch:

```text
A direct voxel = pre_specified_accepted + error_nonpredictive
B_PPMI = pre_specified_accepted + error_nonpredictive
B_MGH = pre_specified_accepted + error_nonpredictive
B_DTOR = pre_specified_accepted + error_nonpredictive
C direct voxel = observed primary realized as no_delta_hf; primary_branch_error_nonpredictive
D PPMI normative fiber = observed primary realized as no_delta_hf at scan-fallback tau600/Coverage>=5; primary_branch_error_nonpredictive
formal permutation/bootstrap/jitter/OSS = not run
```

Do not continue execution from this checkpoint unless explicitly resumed.

---

## Patch / Rerun Policy

Any patch that changes executable model behavior invalidates the affected current
outputs until the affected branches are rerun and their status manifests are
refreshed. This includes patches to:

```text
source resolver logic
hard computability filters
prediction-status definitions
branch-role assignment
DeltaHFScore construction or support QC
tau/Coverage grids or fallback ranking
HF-overlap exclusion
OSS-DBS activation sensitivity
manifest/QC schema
output naming or branch mapping
```

After such a patch, do not interpret stale output tables, maps, prediction CSVs,
or consolidated status files as current results. The rerun must record:

```text
git branch
git commit or local patch identifier
authoritative model document version/date
affected model(s)
affected endpoint rows
affected branches
rerun command
input/output roots
manifest/QC refresh timestamp
```

Documentation-only wording changes do not by themselves require rerunning model
outputs unless they change the declared executable behavior. If documentation
changes the intended resolver or branch-role rule, the matching implementation
and outputs must be patched and rerun before being reported as current.

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

Chinese `_zh.md` mirrors were removed from `my_helper/stnsnr`; the English model summaries are the executable source of truth.

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

A and B use parallel HF dependency vocabularies. Each first resolves whether an HF source exists and is stable enough to define model-family-matched `DeltaHFScore`; prediction-error status then determines the ULF branch role.

```text
A direct voxel source status:
  pre_specified_accepted
  scan_fallback_accepted
  absent_no_stable_grid

A direct voxel prediction status:
  error_predictive
  error_nonpredictive
  not_applicable

B normative fiber source status:
  pre_specified_accepted
  scan_fallback_accepted
  absent_no_stable_grid

B normative fiber prediction status:
  error_predictive
  error_nonpredictive
  not_applicable
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

if matched B normative fiber source exists:
  run delta_hf_adjusted when fold-specific DeltaHFScore inputs are valid
  run no_delta_hf

if matched B normative fiber hf_norm_fiber_prediction_status is error_predictive:
  ulf_primary_branch = delta_hf_adjusted
  delta_hfscore_role = primary_error_predictive_hf_adjustment

if matched B normative fiber hf_norm_fiber_prediction_status is error_nonpredictive:
  ulf_primary_branch = no_delta_hf
  delta_hfscore_role = stable_error_nonpredictive_hf_adjustment_sensitivity

if matched B normative fiber source is absent_no_stable_grid:
  run no_delta_hf only
  ulf_primary_branch = no_delta_hf
  delta_hfscore_role = not_run_no_stable_hf_norm_fiber_source

if the HF-derived intended primary branch is delta_hf_adjusted but DeltaHFScore inputs fail:
  endpoint status = primary_branch_input_failure
  no_delta_hf may be reported only as fallback sensitivity
```

Manifests for C/D must record:

```text
hf_voxel_source_status, for C/A direct-voxel dependencies
hf_voxel_prediction_status, for C/A direct-voxel dependencies
hf_voxel_threshold_source, for C/A direct-voxel dependencies
hf_voxel_selected_tau_v_per_m, for C/A direct-voxel dependencies
hf_voxel_selected_coverage, for C/A direct-voxel dependencies
hf_voxel_selected_adjacent_passing_grid_cells, for C/A direct-voxel dependencies
hf_norm_fiber_source_status, for D/B normative fiber dependencies
hf_norm_fiber_prediction_status, for D/B normative fiber dependencies
hf_norm_fiber_threshold_source, for D/B normative fiber dependencies
hf_norm_fiber_selected_tau_v_per_m, for D/B normative fiber dependencies
hf_norm_fiber_selected_coverage, for D/B normative fiber dependencies
hf_norm_fiber_selected_adjacent_passing_grid_cells, for D/B normative fiber dependencies
hf_norm_fiber_source_failure_reasons, for D/B normative fiber dependencies
ulf_voxel_source_status, for C direct-voxel branch status
ulf_voxel_prediction_status, for C direct-voxel branch status
ulf_endpoint_model_status, for C direct-voxel endpoint status
ulf_norm_fiber_source_status, for D normative-fiber branch status
ulf_norm_fiber_prediction_status, for D normative-fiber branch status
ulf_norm_fiber_endpoint_model_status, for D normative-fiber endpoint status
ulf_branch_input_status, for C direct-voxel branch status
branch_nuisance_design_status, for C direct-voxel branches
intended_primary_branch
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
| A Round 2 tau/Coverage resolver scan | `my_helper/fiber/stnsnr/run_stnsnr_hf_direct_voxel_posthoc_threshold_scan.py` | `my_helper/fiber/core/analysis/stnsnr_hf_direct_voxel_posthoc_threshold_scan.py` | implemented |
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
C formal ULF direct voxel resampling, gain endpoints, total-ULF sensitivity, and all-endpoint reporting driver
D formal ULF normative fiber resampling, dTOR main branch, OSS, and figure-grade outputs
shared reusable resolver/manifest/score architecture across voxel, fiber, HF, and ULF models
formal B=10000 permutation/bootstrap loops
formal spatial jitter loops
OSS-DBS activation branch
nested/adaptive threshold-source validation
max-stat permutation for threshold-source selection
OLS ANCOVA optional estimator
figure-grade display/FDR/enrichment layers beyond existing source-resolver heatmaps
```

`my_helper/stnsnr/four_model_execution_implementation_notes.md` records implementation-layer details and should be updated whenever a new executable layer is added.

---

## 5. Current Run State

Current status is based on existing outputs under:

```text
/Volumes/VAL/STNSNr/summary/four_model_execution/
```

### A/B Primary Observed Branches

Current `four_model_gate_status.csv` was generated by older status code and is
kept only as a legacy/current-output summary. The consolidated execution status
must use the intended resolver fields where available.

| Model | Branch | rho | Q2 | Intended dependency field |
|---|---|---:|---:|---|
| A HF direct voxel | `tau200/partial_spearman` | `-0.0265` | `-0.2230` | current resolver row = `pre_specified_accepted` + `error_nonpredictive` |
| B PPMI | legacy/current output `peak_efield_tau800_primary`; revised spec `peak_efield_tau800_cov5_primary` | `-0.1652` | `-0.4476` | current resolver manifest = `pre_specified_accepted` + `error_nonpredictive` |
| B MGH | legacy/current output `peak_efield_tau800_primary`; revised spec `peak_efield_tau800_cov5_primary` | `-0.0855` | `-0.2916` | current resolver manifest = `pre_specified_accepted` + `error_nonpredictive` |
| B dTOR | legacy/current output `peak_efield_tau800_primary`; revised spec `peak_efield_tau800_cov5_primary` | `-0.1829` | `-0.4976` | current resolver manifest = `pre_specified_accepted` + `error_nonpredictive` |

These observed branches exist and have finite predictions in the current
snapshot. The current B-family dependency status points D toward no-DeltaHF as
the intended primary branch for matched dependencies, because the matched B
sources are accepted but `error_nonpredictive`.

### C/D ULF Readiness

Current execution status reports available ULF component inputs:

```text
ULF component e-fields: 64/64 existing
```

Under the revised resolvers, C and D are executable with both branches when the matched HF source exists and branch-specific inputs are valid. The primary branch is `delta_hf_adjusted` only if the matched HF source is `error_predictive`; otherwise `no_delta_hf` is primary or the only branch.

```text
matched HF source absent:
  no_delta_hf only

matched HF source exists + error_predictive:
  delta_hf_adjusted intended primary
  no_delta_hf fallback/sensitivity

matched HF source exists + error_nonpredictive:
  no_delta_hf intended primary
  delta_hf_adjusted sensitivity, if inputs are valid
```

### C ULF Direct Voxel Observed Branch

The C observed-only driver has been implemented and run for the current-output chronic endpoint row:

```text
post scale = MDS-UPDRS III score (STN+SNr, 3 m)
HF reference = MDS-UPDRS III score (STN, 3 m)
output root = /Volumes/VAL/STNSNr/summary/direct_voxel/ulf/mds_updrs_iii_score_stn_snr_3_m/tau200/
```

Current observed outputs:

| Branch | rho | Q2 | Interpretation role |
|---|---:|---:|---|
| `partial_spearman_no_delta_hf` | `0.9190` | `-0.1442` | realized HF-derived intended primary; C source resolver = `pre_specified_accepted` + `error_nonpredictive`; endpoint status = `primary_branch_error_nonpredictive` |
| `partial_spearman_delta_hf_adjusted` | `0.9543` | `0.1238` | sensitivity because matched A source is accepted but `error_nonpredictive`; C source resolver = `pre_specified_accepted` + `error_predictive` |

Both branches write scores, LOOCV predictions, NIfTI maps, QC JSON, and manifests. Formal resampling has not been run.

### D ULF Normative Fiber Observed Branch

The D observed-only driver has been implemented and run for the current-output chronic endpoint row and PPMI connectome:

```text
post scale = MDS-UPDRS III score (STN+SNr, 3 m)
HF reference = MDS-UPDRS III score (STN, 3 m)
connectome = PPMI 85 (Ewert 2017)
default scan root = /Volumes/VAL/STNSNr/summary/normative_connectome_fiber/ulf/ppmi_85_ewert_2017/mds_updrs_iii_score_stn_snr_3_m/peak_efield_tau800_observed/
selected-source output root = /Volumes/VAL/STNSNr/summary/normative_connectome_fiber/ulf/ppmi_85_ewert_2017/mds_updrs_iii_score_stn_snr_3_m/peak_efield_tau600_observed/
```

Current observed outputs:

| Branch | rho | Q2 | Interpretation role |
|---|---:|---:|---|
| selected-source output `ulf_peak_efield_tau600_no_delta_hf`; revised scan-fallback spec `ulf_peak_efield_tau600_cov5_no_delta_hf` | `0.9161` | `0.0719` | realized HF-derived intended primary; D source resolver = `scan_fallback_accepted` + `error_nonpredictive`; endpoint status = `primary_branch_error_nonpredictive` |
| selected-source output `ulf_peak_efield_tau600_delta_hf_adjusted`; revised scan-fallback spec `ulf_peak_efield_tau600_cov5_delta_hf_adjusted` | `0.9087` | `-0.0598` | sensitivity because matched B_PPMI source is accepted but `error_nonpredictive`; D source resolver = `scan_fallback_accepted` + `error_nonpredictive` |

Both branches write scores, LOOCV predictions, fiber weights, QC JSON, and manifests. Formal resampling, OSS-DBS activation, density maps, endpoint enrichment, and dTOR-scale figure-grade outputs have not been run.

### A Round 2 All-Endpoint Tau/Coverage Resolver Scan

The A-model all-endpoint tau/Coverage resolver scan exists at the legacy/current output path:

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

The scan is part of Round 2. It first evaluates the pre-specified `tau200/Coverage>=5` cell for each endpoint, then uses the remaining grid cells only when that pre-specified source is not accepted. The hard computability filter is:

```text
n_subjects >= 12
n_voxels_full >= 20
fold_n_voxels_min >= 10
HFScore nonconstant in all folds
all predictions finite
```

If the pre-specified grid and at least 2 adjacent grid cells pass the filter, `hf_voxel_source_status = pre_specified_accepted`. Otherwise, the fallback grid is selected by distance to `tau200/Coverage>=5`, adjacent support count, `fold_n_voxels_min`, stricter Coverage, and then higher tau. If no stable grid exists, `hf_voxel_source_status = absent_no_stable_grid`.

`MAE_model < MAE_baseline` and `RMSE_model < RMSE_baseline` define `hf_voxel_prediction_status = error_predictive`; otherwise an accepted source is `error_nonpredictive`. `Q2` and LOOCV Spearman rho are report metrics, not direct-voxel source filters.

### B Normative Fiber Tau/Coverage Source Resolver Status

The revised B-model specification adds an executable source resolver scan:

```text
branch = tau_coverage_source_resolver_scan
tau_grid_v_per_m = [400, 600, 800, 1000, 1200, 1500, 2000]
coverage_grid = [5, 6, 7, 8, 10, 12]
```

B-model normative fiber source-resolver output currently exists for PPMI, MGH,
and dTOR and records `pre_specified_accepted + error_nonpredictive`. When a B
source resolver is refreshed, tau800/Coverage>=5 is evaluated first. If it is not
accepted, a locally stable
scan fallback may define `hf_norm_fiber_source_status = scan_fallback_accepted`
and may provide the B-family `DeltaHFScore` source for D. If no stable grid
exists, record `hf_norm_fiber_source_status = absent_no_stable_grid` and D runs
no-DeltaHF only for that matched dependency.

---

## 6. Resolver Definitions

A direct voxel uses `hf_voxel_source_status` and `hf_voxel_prediction_status`. `Q2`, LOOCV rho, permutation p values, bootstrap stability, and jitter stability are reporting fields and do not define A source existence or prediction status.

B normative fiber uses `hf_norm_fiber_source_status` and `hf_norm_fiber_prediction_status`. `Q2`, LOOCV rho, permutation p values, bootstrap stability, jitter stability, burden-control behavior, and cross-connectome support are reporting or robustness fields unless they expose input/design failure.


---

## 7. Execution Order From Current State

### Current Completed Observed/Resolver Steps

1. C ULF direct voxel observed has been implemented with both branches:

   ```text
   tau200/partial_spearman_delta_hf_adjusted
   tau200/partial_spearman_no_delta_hf
   ```

   Under the revised A resolver, no-DeltaHF is the current HF-derived intended
   primary because the matched A source is accepted but `error_nonpredictive`.
   The refreshed C resolver records no-DeltaHF as
   `pre_specified_accepted + error_nonpredictive` and DeltaHF-adjusted as
   `pre_specified_accepted + error_predictive`. The endpoint-level primary
   realization remains `primary_branch_error_nonpredictive` because the
   HF-derived intended primary branch is no-DeltaHF.

2. D ULF normative fiber PPMI observed has been implemented with both branches
   at the selected-source scan-fallback threshold:

   ```text
   selected-source output: ulf_peak_efield_tau600_delta_hf_adjusted
   revised scan-fallback spec: ulf_peak_efield_tau600_cov5_delta_hf_adjusted

   selected-source output: ulf_peak_efield_tau600_no_delta_hf
   revised scan-fallback spec: ulf_peak_efield_tau600_cov5_no_delta_hf
   ```

   Under the revised B_PPMI resolver, no-DeltaHF is the current HF-derived
   intended primary because the matched B_PPMI source is accepted but
   `error_nonpredictive`. The refreshed D PPMI resolver records both ULF
   branches as `scan_fallback_accepted + error_nonpredictive` at
   tau600/Coverage>=5. The endpoint-level primary realization is
   `primary_branch_error_nonpredictive`.

### Immediate Next Steps

1. Decide whether to extend the D observed/resolver execution beyond PPMI to
   dTOR now, or keep dTOR as deferred formal/reporting work. The B dTOR
   dependency now resolves as `pre_specified_accepted + error_nonpredictive`,
   so a matched D-dTOR no-DeltaHF primary branch is interpretable once run.
2. Keep C/D formal resampling, gain endpoints, total-ULF sensitivity, all-endpoint
   reporting, OSS, jitter, and figure-grade outputs deferred until the selected
   reporting branches are explicitly chosen.
3. Any additional executable patch to resolver, branch-role, DeltaHFScore,
   HF-overlap, tau/Coverage, or manifest logic requires rerunning the affected
   observed/status branches before their outputs are described as current.

### Deferred Expensive Work

Run these only after the relevant resolver/status fields identify the branch to report:

```text
formal B=10000 permutation
formal B=10000 bootstrap
formal FWHM 2 mm jitter
HF/ULF normative fiber OSS-DBS activation sensitivity
figure-grade FDR/enrichment/display outputs
```

If any upstream model or resolver patch lands before this work starts, rerun the
affected observed/status branches first and treat previous downstream-ready flags
as stale until refreshed.

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
workflow endpoint selection for requested runs
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

### Reusable Four-Model Architecture

The four model documents intentionally share many concepts. New implementation
work should increase reuse instead of copying model-specific logic across A/B/C/D.
The reusable backend layer should expose shared components for:

```text
endpoint-row loading and ID joins
tau/Coverage grid evaluation
pre-specified versus scan-fallback source resolution
adjacent-grid support counting
hard computability filter evaluation
prediction-status evaluation from MAE/RMSE versus baseline
LOOCV prediction and nuisance-only baseline fitting
permutation/bootstrap/jitter orchestration
branch-role resolution from matched HF source/prediction status
DeltaHFScore projection and support QC
HF-overlap exclusion
NetScore construction for voxel and fiber families
manifest/QC schema writing
stale-output detection after executable patches
```

Model-specific workflow scripts should provide configuration, not duplicate
algorithms:

```text
model family = direct_voxel or normative_fiber
therapy role = HF foundational or ULF add-on
feature backend = voxel or streamline
pre-specified tau/Coverage
scan grids
endpoint family
branch names
output roots
connectome selection
OSS enabled or disabled
```

The same shared resolver contract should produce parallel fields for direct
voxel and normative fiber:

```text
hf_voxel_source_status
hf_voxel_prediction_status
hf_norm_fiber_source_status
hf_norm_fiber_prediction_status
ulf_voxel_source_status
ulf_voxel_prediction_status
ulf_norm_fiber_source_status
ulf_norm_fiber_prediction_status
ulf_endpoint_model_status
ulf_norm_fiber_endpoint_model_status
```

Any new code that implements one of these shared concepts for only one model
must either place the reusable logic in `my_helper/fiber/core/` immediately or
document why temporary duplication is required and add a follow-up refactor task.

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

A HF direct voxel Round 2 tau/Coverage resolver scan, one endpoint:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_hf_direct_voxel_posthoc_threshold_scan.py \
  --scale "MDS-UPDRS III score (STN, 3 m)"
```

A HF direct voxel Round 2 tau/Coverage resolver scan, all endpoints:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_hf_direct_voxel_posthoc_threshold_scan.py \
  --all-scales
```

A source-resolver plot-only refresh using the legacy/current script name:

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

C ULF direct voxel tau/Coverage source resolver scan:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_direct_voxel_observed.py \
  --source-resolver-scan
```

D ULF normative fiber PPMI observed branch:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_normative_fiber_observed.py --connectome ppmi
```

D ULF normative fiber PPMI tau/Coverage source resolver scan:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_normative_fiber_observed.py \
  --connectome ppmi \
  --source-resolver-scan
```

D ULF normative fiber PPMI selected-source observed branch after current scan fallback:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_normative_fiber_observed.py \
  --connectome ppmi \
  --tau 600 \
  --min-coverage 5
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
A has current direct-voxel source/prediction status; B has current normative-fiber source/prediction status.
C and D have both delta_hf_adjusted and no_delta_hf outputs when inputs allow.
Each model records which branch is interpretation-primary and why.
Every branch has QC JSON, manifest JSON, predictions CSV, and score CSV.
Formal resampling is tied to the resolver-selected reporting branch.
Fallback-selected thresholds are explicitly labeled as scan-fallback sources and are never relabeled as pre-specified sources.
The final report states n=16 and hypothesis-generating interpretation.
All affected outputs and consolidated status files have been rerun after the latest executable patch.
Reusable backend components cover shared resolver, branch-role, score, DeltaHFScore, manifest, and stale-output logic.
```
