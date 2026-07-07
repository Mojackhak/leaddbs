# Four-Model Execution Plan (Codex + Subagent Orchestration)

> **Purpose.** This is the `/goal` plan document for executing the four STN/SNr HF/ULF modeling tracks.
> **Authoritative model specs.** The English files under `my_helper/stnsnr/model_summaries/` define model-level executable behavior. This document defines cross-model orchestration, current implementation state, current status results, and the next engineering priorities.
> **Workspace.** `/Users/mojackhu/Github/leaddbs`
> **Last updated.** 2026-07-07

---

## Pause Checkpoint

Execution has resumed through the 2026-07-07 status, formal-target, and
formal-readiness refresh. The current checkpoint has completed
observed/non-formal branches, lightweight readiness/status generation, the
final-model formal target worklist, and the final-model formal readiness audit:

```text
A HF direct voxel observed branch rerun from /Users/mojackhu/Github/leaddbs
B PPMI/MGH/dTOR HF normative fiber observed branches rerun from /Users/mojackhu/Github/leaddbs using the legacy/current output branch name that maps to revised `peak_efield_tau800_cov5_primary`
C ULF direct voxel observed branches rerun from /Users/mojackhu/Github/leaddbs
C ULF direct voxel gain/total-ULF observed sensitivity branches rerun from /Users/mojackhu/Github/leaddbs
D ULF normative fiber PPMI observed branches rerun from /Users/mojackhu/Github/leaddbs using selected-source tau600 scan-fallback output branches
D ULF normative fiber dTOR observed branches rerun from /Users/mojackhu/Github/leaddbs using selected-source tau400 scan-fallback output branches
legacy/current A/B status CSV refreshed
ULF readiness refreshed with C -> A, D PPMI -> B_PPMI, and D dTOR -> B_DTOR dependency mapping
C direct voxel source resolver refreshed
D PPMI normative fiber source resolver refreshed
D dTOR normative fiber source resolver refreshed
Consolidated status refreshed under /Volumes/VAL/STNSNr/summary/four_model_execution/status/
Final-model formal target worklist refreshed under /Volumes/VAL/STNSNr/summary/four_model_execution/formal_worklist/
Final-model formal readiness audit refreshed under /Volumes/VAL/STNSNr/summary/four_model_execution/formal_readiness/
A/C direct-voxel formal permutation refreshed under /Volumes/VAL/STNSNr/summary/four_model_execution/direct_voxel_formal_permutation/
A/C direct-voxel formal bootstrap refreshed under /Volumes/VAL/STNSNr/summary/four_model_execution/direct_voxel_formal_bootstrap/
A/C direct-voxel formal jitter QC refreshed under /Volumes/VAL/STNSNr/summary/four_model_execution/direct_voxel_formal_jitter/
B_DTOR/D_DTOR dTOR normative-fiber smoke permutation refreshed under /Volumes/VAL/STNSNr/summary/four_model_execution/normative_fiber_smoke_permutation/
B_DTOR/D_DTOR dTOR normative-fiber formal permutation refreshed under /Volumes/VAL/STNSNr/summary/four_model_execution/normative_fiber_formal_permutation/
B_DTOR/D_DTOR dTOR normative-fiber formal bootstrap refreshed under /Volumes/VAL/STNSNr/summary/four_model_execution/normative_fiber_formal_bootstrap/
B_DTOR/D_DTOR dTOR normative-fiber sensitivity readiness refreshed under /Volumes/VAL/STNSNr/summary/four_model_execution/normative_fiber_sensitivity_readiness/
Final reporting and figure-output readiness refreshed under /Volumes/VAL/STNSNr/summary/four_model_execution/final_reporting/
All-endpoint reporting and missing-work audit refreshed under /Volumes/VAL/STNSNr/summary/four_model_execution/all_endpoint_reporting/
ULF component readiness refreshed with STN+SNr 3m and immediate component rows under /Volumes/VAL/STNSNr/summary/four_model_execution/ulf_component_readiness/
C ULF direct voxel same-day immediate observed endpoint-family outputs refreshed from /Users/mojackhu/Github/leaddbs
D ULF normative fiber same-day immediate observed endpoint-family outputs refreshed from /Users/mojackhu/Github/leaddbs
```

The formal rerun manifests for direct-voxel permutation/bootstrap/jitter,
dTOR normative-fiber smoke/formal permutation, and dTOR normative-fiber formal
bootstrap record `code_provenance.git_short_commit = c6e0bb328`. The refreshed
dTOR normative-fiber sensitivity-readiness manifests/status files record
`code_provenance.git_short_commit = 2f30e8cfb`.

The formal readiness audit does not run formal permutation, bootstrap, jitter,
OSS-DBS, or display generation. It consumes the final-model formal target
worklist and checks that each final branch/source has the manifest, QC, score,
and LOOCV prediction files required by future formal drivers.

Final-model selection is automatic at the orchestration layer. The formal
target worklist consumes the model-specific resolver fields, HF-derived ULF
branch-role rules, branch-specific input/design status, and formal-analysis
connectome policy, then emits the unique final branch for each formal target.
No separate manual reporting-branch selection is required once a target is
`READY_FOR_FORMAL_DRIVER`.

Automatic final-model selection is also the tie-breaker for resumed execution.
If an HF model has an accepted source, that accepted source is the unique HF
final model for downstream formal work, regardless of whether it is
`error_predictive` or `error_nonpredictive`. If a ULF HF-derived primary branch
is executable, that branch is the unique ULF final model. If the intended ULF
primary branch has input/design failure and an executable no-DeltaHF branch has
an accepted source, that no-DeltaHF branch is the unique fallback final model.
If neither condition holds, the endpoint has no final model and downstream
formal drivers must skip it with an explicit status row. Formal permutation,
bootstrap, jitter, OSS, display, and enrichment drivers must consume these
worklist-selected final targets and must not request another branch choice.

Current status snapshot after the source-resolver refresh already performed in
this branch:

```text
A direct voxel final source = pre_specified; final_model_error_nonpredictive
B_PPMI final source = pre_specified; final_model_error_nonpredictive
B_MGH final source = pre_specified; final_model_error_nonpredictive
B_DTOR final source = pre_specified; final_model_error_nonpredictive
C direct voxel final model = no_delta_hf; final_model_error_nonpredictive
D PPMI normative fiber final model = no_delta_hf at scan-fallback tau600/Coverage>=5; final_model_error_nonpredictive
D dTOR normative fiber final model = no_delta_hf at scan-fallback tau400/Coverage>=5; final_model_error_nonpredictive
formal target worklist = 4/7 READY_FOR_FORMAL_RESAMPLING; 3/7 OBSERVED_ROBUSTNESS_NO_FORMAL_RESAMPLING
formal readiness audit = 4/4 formal targets READY_FOR_FORMAL_DRIVER
direct-voxel formal permutation = A and C complete at B=10000, seed=42
direct-voxel formal bootstrap = A and C complete at B=10000, seed=42
direct-voxel formal jitter = A and C complete at B=1000, seed=42, FWHM=2 mm
dTOR normative-fiber smoke permutation = B_DTOR and D_DTOR complete at B=1000, seed=42
dTOR normative-fiber formal permutation = B_DTOR and D_DTOR complete at B=10000, seed=42
dTOR normative-fiber formal bootstrap = B_DTOR and D_DTOR complete at B=10000, seed=42
dTOR fiber jitter/OSS = not_run_missing_inputs
final reporting/readiness = 7 rows; n=16 hypothesis-generating; A/C direct voxel display maps ready; fiber density/label caches missing
all-endpoint reporting = 79 rows; A all-endpoint scan rows = 30; discovered branch manifests = 35; missing-work audit rows = 6, with all C/D observed sensitivity and same-day immediate work items detected
```

Current direct-voxel formal permutation snapshot:

```text
A direct voxel: observed rho = -0.0265487881; p_plus_one_two_sided = 0.9455054495; B = 10000
C ULF direct voxel no_delta_hf final model: observed rho = 0.9189995239; p_plus_one_two_sided = 0.2324767523; B = 10000
```

Current direct-voxel formal bootstrap snapshot:

```text
A direct voxel: bootstrap_status = complete; B = 10000; finite_bootstrap_count = 10000; bootstrap_candidate_voxels_min = 230; bootstrap_candidate_voxels_median = 650.0; voxel_finite_count_median = 405.0
C ULF direct voxel no_delta_hf final model: bootstrap_status = complete; B = 10000; finite_bootstrap_count = 10000; bootstrap_candidate_voxels_min = 88; bootstrap_candidate_voxels_median = 616.0; voxel_finite_count_median = 0.0
```

Current direct-voxel formal jitter snapshot:

```text
A direct voxel: jitter_status = complete; B = 1000; finite_jitter_count = 1000; map_pearson_r_median = 0.6292842164; loocv_spearman_rho_median = 0.0530975762; support_jaccard_median = 0.5909748473
C ULF direct voxel no_delta_hf final model: jitter_status = complete; B = 1000; finite_jitter_count = 1000; map_pearson_r_median = 0.5419336816; loocv_spearman_rho_median = 0.9278360578; support_jaccard_median = 0.6550356201
```

Current dTOR normative-fiber smoke permutation snapshot:

```text
B_DTOR HF normative fiber: observed rho = -0.1828916512; p_plus_one_two_sided = 0.6343656344; B = 1000
D_DTOR ULF normative fiber no_delta_hf final model: observed rho = 0.9410908586; p_plus_one_two_sided = 0.0879120879; B = 1000
```

Current dTOR normative-fiber formal permutation snapshot:

```text
B_DTOR HF normative fiber: observed rho = -0.1828916512; p_plus_one_two_sided = 0.6331366863; B = 10000
D_DTOR ULF normative fiber no_delta_hf final model: observed rho = 0.9410908586; p_plus_one_two_sided = 0.0889911009; B = 10000
```

Current dTOR normative-fiber formal bootstrap snapshot:

```text
B_DTOR HF normative fiber: bootstrap_status = complete; B = 10000; finite_bootstrap_count = 10000; bootstrap_candidate_fibers_min = 485; bootstrap_candidate_fibers_median = 2971.5
D_DTOR ULF normative fiber no_delta_hf final model: bootstrap_status = complete; B = 10000; finite_bootstrap_count = 10000; bootstrap_candidate_fibers_min = 95; bootstrap_candidate_fibers_median = 1940.0
```

Current dTOR normative-fiber sensitivity readiness snapshot:

```text
B_DTOR HF normative fiber: oss_sensitivity_status = not_run_missing_oss_inputs; jitter_qc_status = not_run_missing_jitter_inputs
D_DTOR ULF normative fiber no_delta_hf final model: oss_sensitivity_status = not_run_missing_oss_inputs; jitter_qc_status = not_run_missing_jitter_inputs
consolidated formal_resampling_status = FORMAL_BOOTSTRAP_COMPLETE_SENSITIVITY_INPUTS_MISSING for B_DTOR and D_DTOR
```

Current final reporting and figure-output readiness snapshot:

```text
output root = /Volumes/VAL/STNSNr/summary/four_model_execution/final_reporting/
four_model_final_report.csv rows = 7
four_model_figure_output_readiness.csv rows = 7
A direct voxel: figure_output_status = ready_from_existing_direct_voxel_maps
C ULF direct voxel no_delta_hf: figure_output_status = ready_from_existing_direct_voxel_maps
B/D normative fiber rows: figure_output_status = not_run_missing_density_label_cache
manifest cohort_n = 16; interpretation = hypothesis_generating
```

Current all-endpoint reporting and missing-work audit snapshot:

```text
output root = /Volumes/VAL/STNSNr/summary/four_model_execution/all_endpoint_reporting/
four_model_all_endpoint_report.csv rows = 79
four_model_all_endpoint_missing_work.csv rows = 6
source_table_counts = 30 A all-endpoint scan rows, 35 discovered branch manifests, 7 observed summary rows, 7 final-report rows
C chronic gain endpoint sensitivity = observed_outputs_detected
C same-day immediate endpoint family = observed_outputs_detected
C total-ULF exposure sensitivity = observed_outputs_detected
D chronic gain endpoint sensitivity = observed_outputs_detected
D same-day immediate endpoint family = observed_outputs_detected
D total-ULF exposure sensitivity = observed_outputs_detected
```

The observed-only D chronic gain and total-ULF exposure sensitivity branches
are run for the existing D chronic endpoint and current observed connectomes,
using each connectome's ULF source selected by the D resolver:

```text
PPMI selected source = tau600/Coverage>=5
dTOR selected source = tau400/Coverage>=5

D gain endpoint sensitivity:
  outcome = direction-normalized chronic gain
  exposure = selected-source HF-overlap-excluded ULF-only fiber exposure
  nuisance = DeltaHFFiberScore

D total-ULF exposure sensitivity:
  outcome = chronic post HF+ULF score
  exposure = total ULF component fiber exposure from the matched component cache
  nuisance = Y_HF_ref
```

These sensitivity outputs are observed-only. They do not replace the unique D
final model and do not receive formal permutation/bootstrap/jitter unless the
model documents are revised before formal resampling.

When execution is resumed from this checkpoint, expensive dTOR fiber formal
drivers must use the automatically selected final-model formal target worklist.
They must not ask for a new branch choice and must not promote observed
robustness branches into formal resampling.

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

A and B also resolve one final HF source per endpoint:

```text
if source status is pre_specified_accepted:
  hf_final_model_source = pre_specified
  hf_final_model_role = primary

if source status is scan_fallback_accepted:
  hf_final_model_source = scan_fallback
  hf_final_model_role = fallback_final

if source status is absent_no_stable_grid:
  hf_final_model_source = none
  hf_final_model_role = no_final_model

hf_final_model_status =
  final_model_error_predictive
  final_model_error_nonpredictive
  no_final_model_absent_no_stable_grid
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
  no_delta_hf becomes the fallback final model if it is executable
  if no_delta_hf is also not executable, record no final ULF model for that endpoint
```

Each C/D endpoint has exactly one final reporting model after endpoint
classification:

```text
if the HF-derived intended primary branch is executable:
  ulf_final_model_branch = ulf_primary_branch
  ulf_final_model_role = primary

if the HF-derived intended primary branch has input/design failure
and no_delta_hf is executable:
  ulf_final_model_branch = no_delta_hf
  ulf_final_model_role = fallback_final

if neither the intended primary branch nor fallback no_delta_hf is executable:
  ulf_final_model_branch = none
  ulf_final_model_role = no_final_model
```

The final model is unique for reporting and downstream formal resampling.
Non-final branches may still be retained as sensitivity outputs, but they are
not co-primary and do not define the endpoint's final model.

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
hf_final_model_source, for A/B foundational HF models
hf_final_model_role, for A/B foundational HF models
hf_final_model_status, for A/B foundational HF models
hf_final_model_selection_reason, for A/B foundational HF models
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
ulf_final_model_branch
ulf_final_model_role
ulf_final_model_status
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
| Final-model formal target worklist | `my_helper/fiber/stnsnr/run_stnsnr_four_model_formal_worklist.py` | `my_helper/fiber/core/analysis/stnsnr_four_model_formal_worklist.py` | implemented |
| Final-model formal readiness audit | `my_helper/fiber/stnsnr/run_stnsnr_four_model_formal_readiness.py` | `my_helper/fiber/core/analysis/stnsnr_four_model_formal_readiness.py` | implemented |
| Direct-voxel final-model formal permutation | `my_helper/fiber/stnsnr/run_stnsnr_direct_voxel_formal_permutation.py` | `my_helper/fiber/core/analysis/stnsnr_direct_voxel_formal_permutation.py` | implemented |
| Direct-voxel final-model formal bootstrap | `my_helper/fiber/stnsnr/run_stnsnr_direct_voxel_formal_bootstrap.py` | `my_helper/fiber/core/analysis/stnsnr_direct_voxel_formal_bootstrap.py` | implemented |
| Direct-voxel final-model formal jitter QC | `my_helper/fiber/stnsnr/run_stnsnr_direct_voxel_formal_jitter.py` | `my_helper/fiber/core/analysis/stnsnr_direct_voxel_formal_jitter.py` | implemented |
| dTOR normative-fiber smoke/formal permutation | `my_helper/fiber/stnsnr/run_stnsnr_normative_fiber_smoke_permutation.py` | `my_helper/fiber/core/analysis/stnsnr_normative_fiber_smoke_permutation.py` | implemented |
| dTOR normative-fiber formal bootstrap | `my_helper/fiber/stnsnr/run_stnsnr_normative_fiber_formal_bootstrap.py` | `my_helper/fiber/core/analysis/stnsnr_normative_fiber_formal_bootstrap.py` | implemented |
| dTOR normative-fiber sensitivity readiness audit | `my_helper/fiber/stnsnr/run_stnsnr_normative_fiber_sensitivity_readiness.py` | `my_helper/fiber/core/analysis/stnsnr_normative_fiber_sensitivity_readiness.py` | implemented |
| Final reporting and figure-output readiness | `my_helper/fiber/stnsnr/run_stnsnr_four_model_final_reporting.py` | `my_helper/fiber/core/analysis/stnsnr_four_model_final_reporting.py` | implemented |
| All-endpoint reporting and missing-work audit | `my_helper/fiber/stnsnr/run_stnsnr_four_model_all_endpoint_reporting.py` | `my_helper/fiber/core/analysis/stnsnr_four_model_all_endpoint_reporting.py` | implemented |
| Shared IO/provenance helpers | direct core module | `my_helper/fiber/core/analysis/stnsnr_io.py` | implemented |
| ULF component readiness | `my_helper/fiber/stnsnr/run_stnsnr_ulf_component_readiness.py` | `my_helper/fiber/core/analysis/stnsnr_ulf_component_readiness.py` | implemented |
| ULF e-field worklist | `my_helper/fiber/stnsnr/run_stnsnr_ulf_component_efield_worklist.py` | `my_helper/fiber/core/analysis/stnsnr_ulf_component_efield_worklist.py` | implemented |
| C observed ULF direct voxel | `my_helper/fiber/stnsnr/run_stnsnr_ulf_direct_voxel_observed.py` | `my_helper/fiber/core/analysis/stnsnr_ulf_direct_voxel_observed.py` | implemented |
| C observed gain/total-ULF direct-voxel sensitivities | `my_helper/fiber/stnsnr/run_stnsnr_ulf_direct_voxel_sensitivity_observed.py` | `my_helper/fiber/core/analysis/stnsnr_ulf_direct_voxel_sensitivity_observed.py` | implemented |
| C same-day immediate endpoint-family observed driver | `my_helper/fiber/stnsnr/run_stnsnr_ulf_direct_voxel_immediate_observed.py` | `my_helper/fiber/core/analysis/stnsnr_ulf_direct_voxel_immediate_observed.py` | implemented |
| D observed ULF normative fiber PPMI | `my_helper/fiber/stnsnr/run_stnsnr_ulf_normative_fiber_observed.py` | `my_helper/fiber/core/analysis/stnsnr_ulf_normative_fiber_observed.py` | implemented |
| D same-day immediate endpoint-family observed driver | `my_helper/fiber/stnsnr/run_stnsnr_ulf_normative_fiber_immediate_observed.py` | `my_helper/fiber/core/analysis/stnsnr_ulf_normative_fiber_immediate_observed.py` | implemented |
| D observed gain/total-ULF normative-fiber sensitivities | `my_helper/fiber/stnsnr/run_stnsnr_ulf_normative_fiber_sensitivity_observed.py` | `my_helper/fiber/core/analysis/stnsnr_ulf_normative_fiber_sensitivity_observed.py` | implemented |
| Raw clinical rebuild | direct core script | `my_helper/fiber/core/analysis/stnsnr_rebuild_subject_effect_origin.py` | implemented |

### Not Yet Implemented

```text
D OSS and full fiber figure-grade density/FDR/enrichment outputs, pending required caches
remaining shared score, stale-output, and cross-family manifest-schema architecture across voxel, fiber, HF, and ULF models
fiber OSS-DBS activation branch execution, pending required inputs
fiber density/label/FDR/enrichment cache construction
nested/adaptive threshold-source validation
max-stat permutation for threshold-source selection
OLS ANCOVA optional estimator
full figure-grade display/FDR/enrichment layers beyond final reporting/readiness summaries
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

Both branches write scores, LOOCV predictions, NIfTI maps, QC JSON, and manifests. The automatically selected no-DeltaHF final model has completed formal permutation, bootstrap, and jitter QC. The DeltaHF-adjusted branch remains a sensitivity branch and does not receive final-model formal resampling.

The C gain/total-ULF sensitivity layer is an observed-only chronic-endpoint driver:

```text
driver = run_stnsnr_ulf_direct_voxel_sensitivity_observed.py
outputs = partial_spearman_gain_endpoint and partial_spearman_total_ulf_exposure
formal permutation/bootstrap/jitter = not run
same-day immediate endpoint family = not included in this driver
```

Current observed sensitivity outputs:

| Branch | rho | Q2 | Interpretation role |
|---|---:|---:|---|
| `partial_spearman_gain_endpoint` | `0.4763` | `0.1981` | chronic gain endpoint sensitivity; observed only |
| `partial_spearman_total_ulf_exposure` | `0.9278` | `-0.0372` | total ULF exposure sensitivity; observed only |

The gain endpoint reuses the selected chronic ULF-only source and replaces
`Y_post` with direction-normalized `Gain_chronic`. The total-ULF sensitivity
keeps the chronic raw post-score endpoint and branch-specific nuisance design,
but uses total ULF component exposure rather than HF-overlap-excluded ULF-only
exposure. These are sensitivity outputs only and cannot replace the unique C
final model selected by the source resolver.

The C same-day immediate endpoint-family layer is a separate observed-only
driver:

```text
driver = run_stnsnr_ulf_direct_voxel_immediate_observed.py
endpoint rows = all available STN+SNr immediate clinical scales with paired STN 3m reference and n_subjects >= 12
currently available rows = MDS-UPDRS III score and MDS-UPDRS III axial score
per endpoint row = observed LOOCV plus tau/Coverage source-resolver scan
formal permutation/bootstrap/jitter = not run unless an immediate endpoint is explicitly promoted before formal resampling
same-day gain sensitivity = not included in this driver
```

This layer requires ULF component readiness to include `STN+SNr immediate`
HF/ULF component e-field rows. Immediate outputs are endpoint-family outputs,
not replacements for the chronic C final model unless the model documents are
explicitly revised before formal resampling.

Current same-day immediate observed outputs:

| Endpoint row | Branch | rho | Q2 | Resolver status |
|---|---|---:|---:|---|
| MDS-UPDRS III axial score (STN+SNr, immediate) | `no_delta_hf` | `-0.1663` | `-0.0688` | `pre_specified_accepted` + `error_nonpredictive` |
| MDS-UPDRS III axial score (STN+SNr, immediate) | `delta_hf_adjusted` | `-0.0817` | `-0.0444` | `pre_specified_accepted` + `error_nonpredictive` |
| MDS-UPDRS III score (STN+SNr, immediate) | `no_delta_hf` | `0.8755` | `0.0225` | `pre_specified_accepted` + `error_nonpredictive` |
| MDS-UPDRS III score (STN+SNr, immediate) | `delta_hf_adjusted` | `0.8209` | `0.1584` | `pre_specified_accepted` + `error_nonpredictive` |

Both endpoint rows record `ulf_endpoint_model_status =
primary_branch_error_nonpredictive`. These observed immediate outputs remain
non-formal unless an immediate endpoint is explicitly promoted before formal
resampling.

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

Both branches write scores, LOOCV predictions, fiber weights, QC JSON, and manifests. PPMI is an observed robustness connectome in the current worklist, so it does not receive formal resampling unless the model documents are revised. OSS-DBS activation, density maps, endpoint enrichment, and figure-grade outputs have not been run.

### D ULF Normative Fiber dTOR Observed Branch

The D dTOR observed-only driver has been run for the current-output chronic endpoint row and selected-source scan-fallback threshold:

```text
post scale = MDS-UPDRS III score (STN+SNr, 3 m)
HF reference = MDS-UPDRS III score (STN, 3 m)
connectome = dTOR-985 Full (Elias 2024)
default scan root = /Volumes/VAL/STNSNr/summary/normative_connectome_fiber/ulf/dtor_985_full_elias_2024/mds_updrs_iii_score_stn_snr_3_m/peak_efield_tau800_observed/
selected-source output root = /Volumes/VAL/STNSNr/summary/normative_connectome_fiber/ulf/dtor_985_full_elias_2024/mds_updrs_iii_score_stn_snr_3_m/peak_efield_tau400_observed/
```

Current observed outputs:

| Branch | rho | Q2 | Interpretation role |
|---|---:|---:|---|
| selected-source output `ulf_peak_efield_tau400_no_delta_hf`; revised scan-fallback spec `ulf_peak_efield_tau400_cov5_no_delta_hf` | `0.9411` | `-0.0849` | realized HF-derived intended primary; D_DTOR source resolver = `scan_fallback_accepted` + `error_nonpredictive`; endpoint status = `primary_branch_error_nonpredictive` |
| selected-source output `ulf_peak_efield_tau400_delta_hf_adjusted`; revised scan-fallback spec `ulf_peak_efield_tau400_cov5_delta_hf_adjusted` | `0.9470` | `0.2169` | sensitivity because matched B_DTOR source is accepted but `error_nonpredictive`; D_DTOR source resolver = `scan_fallback_accepted` + `error_predictive` |

Both branches write scores, LOOCV predictions, fiber weights, QC JSON, and manifests. The automatically selected no-DeltaHF dTOR final model has completed formal permutation and bootstrap. OSS-DBS activation and jitter QC are recorded as missing-input sensitivity-readiness statuses, so the consolidated status records `D_DTOR = FORMAL_BOOTSTRAP_COMPLETE_SENSITIVITY_INPUTS_MISSING`.

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

3. D ULF normative fiber dTOR observed has been implemented with both branches
   at the selected-source scan-fallback threshold:

   ```text
   selected-source output: ulf_peak_efield_tau400_delta_hf_adjusted
   revised scan-fallback spec: ulf_peak_efield_tau400_cov5_delta_hf_adjusted

   selected-source output: ulf_peak_efield_tau400_no_delta_hf
   revised scan-fallback spec: ulf_peak_efield_tau400_cov5_no_delta_hf
   ```

   Under the revised B_DTOR resolver, no-DeltaHF is the current HF-derived
   intended primary because the matched B_DTOR source is accepted but
   `error_nonpredictive`. The refreshed D dTOR resolver records no-DeltaHF as
   `scan_fallback_accepted + error_nonpredictive` and DeltaHF-adjusted as
   `scan_fallback_accepted + error_predictive` at tau400/Coverage>=5. The
   endpoint-level primary realization is `primary_branch_error_nonpredictive`.

### Immediate Next Steps

1. Keep B_DTOR and D_DTOR fiber OSS/jitter as explicit missing-input
   sensitivity-readiness statuses until the required sensitivity sidecars exist.
2. Formal resampling, OSS, jitter, and figure-grade outputs attach to the
   generated final-model formal target worklist for model families that define
   formal inference. The current formal targets are A, B_DTOR, C, and D_DTOR.
   B_PPMI, B_MGH, and D_PPMI remain observed robustness outputs and must not be
   promoted into formal resampling unless the model documents are explicitly
   revised. If a ULF intended primary branch has input/design failure, the
   executable fallback no-DeltaHF branch becomes the unique final model for that
   endpoint.
3. Regenerate the final reporting and figure-output readiness package after any
   upstream resolver, status, formal summary, or sensitivity-readiness output
   changes. This package is the executable Round 8/9/10 boundary for the
   current output state: it summarizes final models, formal inference,
   direct-voxel display-source availability, and missing fiber density/label
   caches without fabricating unavailable figure-grade fiber maps.
4. Regenerate the all-endpoint reporting and missing-work audit package after
   any upstream endpoint, branch-manifest, final-report, or sensitivity output
   changes. This package consumes the
   existing A all-scale source-resolver scan, observed branch manifests,
   consolidated final-model outputs, and ULF sensitivity-output searches. This
   reporting package must explicitly label C/D gain endpoints, same-day
   immediate endpoints, and total-ULF sensitivities as detected or not run from
   observed output files. The current C gain, C same-day immediate, and C
   total-ULF sensitivity outputs are detected; all D sensitivity work items
   remain not run.
5. Any additional executable patch to resolver, branch-role, DeltaHFScore,
   HF-overlap, tau/Coverage, or manifest logic requires rerunning the affected
   observed/status branches before their outputs are described as current.

If required OSS activation sidecars or jittered exposure sidecars are absent,
write explicit branch-level and cross-target sensitivity-readiness status
instead of marking the sensitivity layer complete. Missing sensitivity inputs do
not change the selected final model or the completed permutation/bootstrap
status; they only prevent OSS/jitter robustness support from being claimed.
The consolidated status should then report
`FORMAL_BOOTSTRAP_COMPLETE_SENSITIVITY_INPUTS_MISSING`.

### Deferred Expensive Work

Run these only after the relevant resolver/status fields identify the unique
final model branch:

```text
HF/ULF normative fiber OSS-DBS activation sensitivity when inputs exist
full fiber density/FDR/enrichment/display outputs when density and label caches exist
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

The first reusable architecture layer is a small shared IO/provenance helper. It centralizes
timestamp creation, CSV/JSON read/write behavior, and optional
`code_provenance` insertion for manifest-like JSON outputs. It must be
behavior-preserving and must not change model formulas, resolver rules, or
output schemas except for consistently adding provenance when a caller requests
it. The C same-day immediate and C gain/total-ULF sensitivity drivers now use
this helper; broader migration remains part of the remaining shared
score/stale-output/manifest-schema work.

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

C ULF direct voxel gain/total-ULF observed sensitivities:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_direct_voxel_sensitivity_observed.py
```

C ULF direct voxel same-day immediate observed endpoint family:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_direct_voxel_immediate_observed.py
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

D ULF normative fiber dTOR observed branch:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_normative_fiber_observed.py \
  --connectome dtor
```

D ULF normative fiber dTOR tau/Coverage source resolver scan:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_normative_fiber_observed.py \
  --connectome dtor \
  --source-resolver-scan
```

D ULF normative fiber dTOR selected-source observed branch after current scan fallback:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_normative_fiber_observed.py \
  --connectome dtor \
  --tau 400 \
  --min-coverage 5
```

Consolidated execution status:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_four_model_execution_status.py
```

Final-model formal target worklist:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_four_model_formal_worklist.py
```

Final-model formal readiness audit:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_four_model_formal_readiness.py
```

Direct-voxel final-model formal permutation:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_direct_voxel_formal_permutation.py \
  --n-permutations 10000
```

Direct-voxel final-model formal bootstrap:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_direct_voxel_formal_bootstrap.py \
  --n-bootstraps 10000
```

Direct-voxel final-model formal jitter QC:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_direct_voxel_formal_jitter.py \
  --n-jitters 1000 \
  --jitter-fwhm-mm 2.0
```

dTOR normative-fiber smoke permutation:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_normative_fiber_smoke_permutation.py \
  --n-permutations 1000
```

dTOR normative-fiber formal permutation:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_normative_fiber_smoke_permutation.py \
  --tier formal \
  --n-permutations 10000
```

dTOR normative-fiber formal bootstrap:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_normative_fiber_formal_bootstrap.py \
  --n-bootstraps 10000
```

dTOR normative-fiber sensitivity readiness:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_normative_fiber_sensitivity_readiness.py
```

Final reporting and figure-output readiness:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_four_model_final_reporting.py
```

All-endpoint reporting and missing-work audit:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_four_model_all_endpoint_reporting.py
```

---

## 10. Definition Of Done

This four-model program is complete only when:

```text
A has current direct-voxel source/prediction status; B has current normative-fiber source/prediction status.
C and D have both delta_hf_adjusted and no_delta_hf outputs when inputs allow.
Each model records which branch is interpretation-primary and why.
Every branch has QC JSON, manifest JSON, predictions CSV, and score CSV.
Formal resampling is tied to the automatically selected resolver-derived final
unique model branch.
Every final-model formal target passes the readiness audit before expensive
formal drivers are started.
Fallback-selected thresholds are explicitly labeled as scan-fallback sources and are never relabeled as pre-specified sources.
The final reporting package records the unique final model for each formal target,
formal resampling status, direct-voxel display-source availability, and explicit
not-run statuses for unavailable fiber OSS/jitter/density/FDR/enrichment inputs.
The all-endpoint reporting package records A all-endpoint source-resolver rows,
observed branch manifests, final-report rows, and explicit not-run statuses for
C/D gain endpoints, same-day immediate endpoints, and total-ULF sensitivities.
The final report states n=16 and hypothesis-generating interpretation.
All affected outputs and consolidated status files have been rerun after the latest executable patch.
Reusable backend components cover shared resolver, branch-role, score, DeltaHFScore, manifest, and stale-output logic.
```
