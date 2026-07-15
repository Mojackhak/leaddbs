# HF-Status-Resolved ULF-Only Add-On Gain Direct Voxel-Level Model

## YAML Core Interface (Predecessor Implemented; Acceptance Paused)

The predecessor configuration/orchestration contract is documented in
`my_helper/stnsnr/four_model_yaml_core_refactor_plan.md`. This model summary
remains authoritative for ULF branch inputs, HF-derived intended branch role,
branch-specific source resolution, fallback-final realization, formal
resampling, and sensitivities. The `four_model_v1` profile, identity, catalog,
state, run store, configured service, and DAG executor exist. The paused
MDS-UPDRS III/IV acceptance run reached the ULF direct path, but its two ULF
direct tasks ended in an adapter execution failure; the adapter repair has not
received a new immutable real-run acceptance lineage. The approved strict dual-
frequency successor is documented in
`my_helper/stnsnr/dual_frequency_core_decoupling_design.md` and has status
`implementation_not_started`. Current outputs remain read-only.

All configured ULF/frequency-2 endpoint scales are engineering-equivalent within
their applicable endpoint families. Chronic, immediate, total, axial, and other
configured scales use the same task factories and status fields. Public
YAML provides the shared `four_model_v1` scientific/formal/sensitivity profile.
The direct-voxel sparse candidate threshold is `internal-derived` as
`min(tau_grid_v_per_m)` and is not exposed. Equivalence and smoke parameters are
`internal-test`; matched HF status, ULF branch statuses, the unique final model,
and artifact paths are `runtime output`.

The core statistical domain remains the right-canonical brainmask. Anatomical
ROI restriction, VTA/ROI postprocessing, regional heatmaps, and GUI are outside
the planned core refactor.

## Research Question

Which ultra-low-frequency stimulation territory voxels have ULF-only exposure associated with additional clinical benefit after ULF stimulation is added to HF stimulation, after adjusting for the patient's same-day HF clinical state and model-predicted change in HF efficacy?

This is a direct local ULF-only add-on sweet-spot model. It does not define the main question as an anatomic SNr effect. The STN/SNr and peri-STN/SNr region is treated as one stimulation territory, with HF and ULF components separated by stimulation frequency and exposure overlap.

Frequency definitions:

```text
HF  = high-frequency stimulation class, frequency_Hz > 100
ULF = ultra-low-frequency stimulation class, frequency_Hz < 50
unclassified = 50 <= frequency_Hz <= 100
```

STN/SNr is raw target identity. HF/ULF is derived from frequency alone; Target
does not participate in source classification.

Voxels co-activated by HF and ULF are attributed to the HF adjustment model and are excluded from the primary ULF-only predictor. This is a modeling choice, not a biological claim that ULF cannot have an effect in HF-overlap territory.

## Follow-Up Timeline

The model assumes the following visit sequence:

```text
T0 = preoperative baseline assessment

T1 = postoperative 1-month HF immediate activation / opening assessment

T2 = HF-only 3-month follow-up
     same day, before adding ULF:
       raw HF-only 3-month clinical state is measured
     same day, after switching to HF+ULF:
       raw HF+ULF immediate clinical state is measured

T3 = HF+ULF 3-month follow-up
     approximately 3 months after T2:
       raw HF+ULF chronic 3-month clinical state is measured
```

The immediate HF+ULF endpoint and the HF-only 3-month clinical reference state are therefore same-day measurements. The immediate endpoint is not confounded by a different visit day relative to the HF-only 3-month reference. The chronic endpoint is a post-add-on follow-up endpoint, using the T2 HF-only 3-month state as the pre-ULF clinical reference.

## Endpoint Definitions

Two endpoint families are modeled separately.

### Primary Chronic Post-Add-On Endpoint

```text
Y_post_chronic = raw HF+ULF 3-month clinical score at T3
Y_HF_ref       = raw HF-only 3-month clinical score at T2, same scale/domain
DeltaHFScore_chronic = predicted change in HF efficacy between
                       HF+ULF chronic programming and HF-only T2 programming
```

Primary chronic estimand:

```text
HF-state-adjusted ULF-only chronic add-on association
```

This endpoint estimates whether ULF-only exposure explains the T3 HF+ULF outcome after accounting for the patient's T2 HF clinical state and the modeled change in HF-component efficacy.

### Key Same-Day Immediate Endpoint

```text
Y_post_immediate = raw HF+ULF immediate clinical score at T2, after switching to HF+ULF
Y_HF_ref         = raw HF-only 3-month clinical score at T2, before switching to HF+ULF
DeltaHFScore_immediate = predicted change in HF efficacy between
                         immediate HF+ULF programming and HF-only T2 programming
```

Immediate estimand:

```text
same-day HF-state-adjusted ULF-only acute add-on association
```

Because `Y_post_immediate` and `Y_HF_ref` are measured on the same day, this endpoint is a valid same-day add-on response endpoint. Chronic and same-day immediate endpoint families are modeled separately, but engineering execution treats every available endpoint/scale row equivalently within its endpoint family. Reporting hierarchy may designate chronic rows as primary and immediate rows as secondary or explicitly promoted co-primary; this hierarchy does not change resolver classification, branch role, prediction-status assignment, or output generation.

### Direction-Normalized Gain Sensitivity Endpoints

The primary model uses raw post-HF+ULF scores with HF-state adjustment. Direction-normalized gain endpoints are retained as sensitivity analyses.

For lower-is-better scales:

```text
Gain_immediate = Y_HF_ref - Y_post_immediate
Gain_chronic   = Y_HF_ref - Y_post_chronic
```

For higher-is-better scales:

```text
Gain_immediate = Y_post_immediate - Y_HF_ref
Gain_chronic   = Y_post_chronic - Y_HF_ref
```

Positive gain always means improvement after adding ULF. The immediate gain endpoint is the cleanest direct same-day add-on effect estimate. The chronic gain endpoint combines add-on response, time-on-stimulation, adaptation, medication/assessment variability, and disease-course effects.

Executable endpoint rows:

```text
all available HF+ULF post-add-on clinical scales joined by ID
within the chronic and same-day immediate endpoint families
```

Raw scores come from the raw clinical table used by the HF direct voxel model:

```text
/Users/mojackhu/Research/STNSNr/summary/cohort/subj/subject_effect_origin.xlsx
```

Clinical rows are joined to imaging by `ID` (`SNr003`, `SNr006`, etc.). Improvement-rate tables are not used by the primary raw-score model. Scale direction is read from the same internal direction table as the HF direct voxel model. Unknown scales must provide an explicit higher-is-better or lower-is-better direction before the run starts.

## Inputs

- Stimulation parameter audit source:

  ```text
  /Users/mojackhu/Research/STNSNr/summary/cohort/subj/followup_stimulation.xlsx
  sheet = Contact Parameters
  ```

  This workbook is used to audit HF and ULF component identity, frequencies, pulse widths, amplitudes, sides, contacts, and phase labels. Existing e-fields are treated as accepted inputs after prior manual/clinical QC. The current ULF direct voxel analysis does not automatically create missing e-fields.

- HF-only reference E-field per side from the T2 HF-only 3-month phase, used to compute the reference HF score.

- HF component E-field and ULF component E-field per side from same-day T2 immediate HF+ULF programming, used for the immediate endpoint.

- HF component E-field and ULF component E-field per side from T3 chronic HF+ULF programming, used for the chronic endpoint. If the T3 stimulation settings are unchanged from T2 immediate HF+ULF programming, the manifest must explicitly record that the same component e-fields were reused.

- Direct voxel-level HF efficacy map trained from HF-only outcomes, matching the model type:

  ```text
  DeltaHFScore source = HF direct voxel model
  ```

  The ULF direct voxel model must not use a normative fiber HF score as the HF adjustment. Voxel-level ULF models adjust with voxel-level HF models.

- Canonical reference mask:

  ```text
  templates/space/MNI152NLin2009bAsym/brainmask.nii.gz > 0
  ```

  Candidate voxels are restricted to right-hemisphere voxel centers with MNI world coordinate `x > 0`.

- Anatomical overlay masks:

  ```text
  templates/space/MNI152NLin2009bAsym/atlases/STNSNr-connected regions/{rh,lh}/STNSNrplus.nii.gz
  ```

  `STNSNrplus` is used only for anatomical overlay, territory coverage, and QC background. It is not intersected with `Omega_ULF_tau_coverage` and is not the statistical candidate mask.

- Left/right homology transform:

  ```text
  helpers/ea_flip_lr_nonlinear.m
  templates/space/MNI152NLin2009bAsym/fliplr/{Composite,InverseComposite}.nii.gz
  ```

  All left/right flipping in this model uses `ea_flip_lr_nonlinear` with the Lead-DBS default interpolation behavior.

Minimum e-field checks: required paths must exist, subject/side/component/phase matches must be unique, files must be raw `sim-efield`, and units must be recorded as `V/m`. Missing or multiply matched e-fields fail the endpoint/run. Subjects are not silently excluded and missing e-fields are not automatically created.

## Locked HF Prerequisite

The ULF direct voxel model may enter Round 2 only after the matched HF direct voxel resolver has been locked. The DeltaHF-adjusted ULF branch may enter formal analysis only when the HF resolver has accepted a source and fold-specific `DeltaHFScore` can be computed.

Locked HF resolver fields when a source exists:

```text
model_family = hf_3m_direct_voxel_model
scale        = matched scale/domain
hf_voxel_source_status = pre_specified_accepted | scan_fallback_accepted
hf_voxel_prediction_status = error_predictive | error_nonpredictive
tau          = hf_voxel_selected_tau_v_per_m
coverage     = hf_voxel_selected_coverage
score        = HFScore_mean_main
map source   = training-fold map for LOOCV
full-sample map = descriptive and full-sample score output only
```

The ULF direct voxel implementation is a three-layer resolver:

```text
1. HF-derived intended branch role
2. branch-specific ULF source resolver with tau/Coverage scan
3. endpoint primary realization
```

The first layer does not use ULF tau or Coverage. It reads only the matched HF direct-voxel resolver fields and `DeltaHFScore` input status to decide which ULF branches should be attempted and which branch is the intended primary branch. The complete ULF voxel model is not defined until the intended branch has completed its own ULF tau/Coverage source resolver.

HF-derived intended branch role:

```text
if hf_voxel_source_status = pre_specified_accepted or scan_fallback_accepted:
  run no_delta_hf
  run delta_hf_adjusted only if fold-specific DeltaHFScore inputs are valid

if hf_voxel_prediction_status = error_predictive:
  ulf_primary_branch = delta_hf_adjusted
  delta_hfscore_role = primary_error_predictive_hf_adjustment
  no_delta_hf_role   = sensitivity

if hf_voxel_prediction_status = error_nonpredictive:
  ulf_primary_branch = no_delta_hf
  delta_hfscore_role = stable_error_nonpredictive_hf_adjustment_sensitivity
  no_delta_hf_role   = primary

if hf_voxel_source_status = absent_no_stable_grid:
  run no_delta_hf only
  ulf_primary_branch = no_delta_hf
  delta_hfscore_role = not_run_no_stable_hf_voxel_source

if hf_voxel_prediction_status = error_predictive
and fold-specific DeltaHFScore inputs are invalid:
  ulf_primary_branch = delta_hf_adjusted
  delta_hfscore_role = primary_input_failure
  no_delta_hf_role   = fallback_final_if_accepted_source
```

When `ulf_primary_branch = delta_hf_adjusted` but `DeltaHFScore` inputs are invalid, the HF-derived primary branch is not executable. The endpoint primary status remains `primary_branch_input_failure`; if `no_delta_hf` has an accepted ULF source, it becomes the endpoint's fallback final model rather than a non-final sensitivity result. The same one-way fallback applies when intended `delta_hf_adjusted` is evaluable but its source resolver returns `absent_no_stable_grid`. An accepted adjusted comparison branch is never promoted when intended `no_delta_hf` fails, and technical execution failure never triggers fallback.

The branch-role decision must be written to the model manifest:

```text
hf_voxel_source_status
hf_voxel_prediction_status
hf_voxel_threshold_source
hf_voxel_selected_tau_v_per_m
hf_voxel_selected_coverage
hf_voxel_selected_adjacent_passing_grid_cells
ulf_primary_branch
ulf_primary_branch_run_status
ulf_final_model_branch
ulf_final_model_role
ulf_final_model_status
ulf_final_model_selection_reason
ulf_core_branches_run
ulf_sensitivity_branches
fallback_final_branch
ulf_fallback_final_status
delta_hfscore_role
branch_role_decision_reason
hf_model_support_status
```

If the matched HF resolver returns `absent_no_stable_grid`, the DeltaHF-adjusted branch is not run for that endpoint and `no_delta_hf` is the primary branch. If the HF-derived primary branch is `delta_hf_adjusted` but accepted HF support cannot provide valid fold-specific `DeltaHFScore`, do not relabel `no_delta_hf` as the HF-derived primary branch; record `ulf_endpoint_model_status = primary_branch_input_failure` and, if `no_delta_hf` has an accepted ULF source, set `ulf_final_model_branch = no_delta_hf` and `ulf_final_model_role = fallback_final`. The same final-role assignment applies if intended adjusted has `absent_no_stable_grid` and no-delta has an accepted source. A `scan_fallback_accepted` HF source may define the intended primary ULF branch when its `hf_voxel_prediction_status` is `error_predictive`, but the manifest must still record `hf_voxel_threshold_source = scan_fallback`.

## ULF Voxel Source And Prediction Resolver

The HF-derived intended branch role decides which branches are attempted and which branch is intended primary. The branch-specific ULF source resolver then evaluates each executable branch independently. Each branch may select a different tau/Coverage source because `delta_hf_adjusted` and `no_delta_hf` have different nuisance designs and may produce different valid ULF scoring supports. ULF source or prediction status must not change the HF-derived intended primary branch; it determines whether that intended branch is realized as a stable ULF model or whether the endpoint is reported as input-failed, absent, predictive, or nonpredictive.

The hard computability filter for each executable ULF endpoint, branch, and tau/Coverage grid cell is:

```text
n_subjects >= 12
n_voxels_full >= 20
fold_n_voxels_min >= 10
ULFScore_mean_main is non-constant in every LOOCV fold
branch nuisance design is valid
all held-out predictions are finite
```

`branch nuisance design is valid` means that the branch-specific nuisance model is estimable in the full sample and in every LOOCV training fold:

```text
no_delta_hf nuisance design:
  intercept + Y_HF_ref

delta_hf_adjusted nuisance design:
  intercept + Y_HF_ref + DeltaHFScore

required checks:
  all nuisance covariates are finite
  Y_HF_ref is non-constant
  DeltaHFScore is finite and non-constant, for delta_hf_adjusted only
  design matrix has full column rank in the full sample
  design matrix has full column rank in every LOOCV training fold
  n_train > number_of_design_columns in every LOOCV training fold
  no exact or near-exact collinearity makes residualization unstable
```

If the nuisance design fails, the branch is not interpreted as nonpredictive. It is recorded as an input/design failure:

```text
ulf_branch_input_status = invalid_delta_reference_scaling
  if DeltaHFScore is constant or otherwise cannot be scaled

ulf_branch_input_status = invalid_nuisance_design
  if the full-sample or any fold-specific nuisance matrix is rank deficient
  or otherwise not estimable
```

The generic runtime name for the first status is `invalid_delta_reference_scaling`; `DeltaHFScore` is the STNSNr compatibility name for the corresponding `DeltaReferenceScore`. Both statuses invalidate only `delta_hf_adjusted`; they do not prevent an otherwise valid `no_delta_hf` branch from running.

Branch input/design failure has priority over `absent_no_stable_grid`. If a branch cannot evaluate the declared grid because branch-specific inputs or the branch nuisance design are invalid, record `ulf_endpoint_model_status = primary_branch_input_failure` when that branch is primary. Do not reclassify this condition as `absent_no_stable_grid`.

The pre-specified ULF source is:

```text
tau = 200 V/m
Coverage >= 5
estimator = branch-specific partial Spearman
score = ULFScore_mean_main
validation = LOOCV
```

If the pre-specified source is not accepted, the fallback source must be selected only from the declared ULF tau/Coverage scan grid:

```text
tau, V/m:
  100, 150, 180, 200, 220, 250, 300, 350, 400, 500

Coverage:
  5, 6, 7, 8, 10, 12
```

Define ULF voxel source status for every executable endpoint, phase, and branch:

```text
ulf_voxel_source_status = pre_specified_accepted
  if the pre-specified tau200/Coverage>=5 grid cell passes the hard computability filter
  and at least 2 adjacent tau/Coverage grid cells also pass the hard computability filter

ulf_voxel_source_status = scan_fallback_accepted
  if tau200/Coverage>=5 does not pass the source-stability rule
  and a predeclared ULF source scan contains another grid cell passing the same rule

ulf_voxel_source_status = absent_no_stable_grid
  if no evaluated tau/Coverage grid cell passes the source-stability rule
```

For `scan_fallback_accepted`, choose the fallback grid without using outcome-performance metrics:

```text
1. minimize grid distance from tau200/Coverage>=5
2. maximize adjacent passing grid cells
3. maximize fold_n_voxels_min
4. prefer stricter Coverage
5. prefer higher tau
```

Adjacent grid cells are defined on the declared ULF source scan grid; horizontal, vertical, and diagonal one-step neighbors all count. The Round 2 scan table must contain all declared grid cells needed to assign `pre_specified_accepted`, `scan_fallback_accepted`, or `absent_no_stable_grid`.

Define ULF voxel prediction status only after a branch-specific source exists:

```text
ulf_voxel_prediction_status = error_predictive
  if MAE_model < MAE_nuisance_baseline
  and RMSE_model < RMSE_nuisance_baseline

ulf_voxel_prediction_status = error_nonpredictive
  if a ULF voxel source exists
  but MAE_model >= MAE_nuisance_baseline
  or RMSE_model >= RMSE_nuisance_baseline

ulf_voxel_prediction_status = not_applicable
  if ulf_voxel_source_status = absent_no_stable_grid
```

The nuisance baseline is branch-specific:

```text
no_delta_hf:
  nuisance baseline = Y_post ~ Y_HF_ref

delta_hf_adjusted:
  nuisance baseline = Y_post ~ Y_HF_ref + DeltaHFScore
```

`Q2`, LOOCV Spearman rho, and nominal p values remain required report fields, but they are not ULF source filters. MAE/RMSE define ULF prediction-error status after a ULF source is accepted.

Endpoint primary realization combines the HF-derived intended primary branch with that branch's own ULF source resolver result:

```text
ulf_endpoint_model_status = primary_branch_error_predictive
  if the intended primary branch has ulf_voxel_source_status in
  {pre_specified_accepted, scan_fallback_accepted}
  and the intended primary branch has ulf_voxel_prediction_status = error_predictive

ulf_endpoint_model_status = primary_branch_error_nonpredictive
  if the intended primary branch has an accepted ULF source
  but the intended primary branch has ulf_voxel_prediction_status = error_nonpredictive

ulf_endpoint_model_status = absent_no_stable_ulf_grid
  if the intended primary branch is executable
  but has ulf_voxel_source_status = absent_no_stable_grid

ulf_endpoint_model_status = primary_branch_input_failure
  if the intended primary branch cannot be evaluated because required clinical, e-field,
  HF-source, DeltaHFScore, or nuisance-design inputs are invalid
```

Final-model status is assigned after endpoint primary realization. Fallback is one-way: if intended `delta_hf_adjusted` has input/design failure or `absent_no_stable_grid`, an accepted `no_delta_hf` becomes the fallback final model. Intended `no_delta_hf` failure never promotes adjusted, and technical execution failure never triggers fallback:

```text
if ulf_endpoint_model_status in
  {primary_branch_error_predictive, primary_branch_error_nonpredictive}:
    ulf_final_model_branch = intended_primary_branch
    ulf_final_model_role = primary

ulf_final_model_branch = no_delta_hf
ulf_final_model_role = fallback_final
  if intended_primary_branch = delta_hf_adjusted
  and ulf_endpoint_model_status in
    {primary_branch_input_failure, absent_no_stable_ulf_grid}
  and no_delta_hf has an accepted ULF source

ulf_final_model_branch = none
ulf_final_model_role = no_final_model
  if the intended primary branch has no accepted source
  and no permitted no_delta_hf fallback has an accepted source
```

The final ULF model is unique for each endpoint:

```text
ulf_final_model =
  endpoint + phase + ulf_final_model_branch
  + selected_tau + selected_coverage + estimator
```

High-leverage dominance, excessive DeltaHFScore delta-support limitation, and nonfatal nuisance collinearity are QC limitations. They must be recorded in the manifest, but they do not replace `ulf_voxel_source_status`, `ulf_voxel_prediction_status`, or `ulf_endpoint_model_status` unless they make the hard computability filter or branch input checks fail.

Required ULF resolver manifest/QC fields:

```text
ulf_voxel_source_status
ulf_voxel_prediction_status
ulf_endpoint_model_status
ulf_fallback_final_status
ulf_branch_input_status
ulf_voxel_threshold_source
ulf_voxel_selected_tau_v_per_m
ulf_voxel_selected_coverage
ulf_voxel_selected_adjacent_passing_grid_cells
ulf_voxel_selected_grid_distance_from_pre_specified
intended_primary_branch
ulf_final_model_id
fallback_final_branch
fallback_final_source_status
fallback_final_prediction_status
branch_nuisance_design_status
branch_nuisance_design_rank_full
branch_nuisance_design_rank_min_fold
MAE_model
MAE_nuisance_baseline
RMSE_model
RMSE_nuisance_baseline
Q2
rho_obs
```

## Feature Construction

Use the right-hemisphere MNI brainmask grid as the canonical statistical grid. Left-sided HF and ULF component fields are flipped into right space with `ea_flip_lr_nonlinear`. Right-sided fields are sampled on the same right canonical grid.

For each subject, side, and endpoint phase:

```text
E_HF_R_i(v, phase)       = right HF component e-field
E_HF_L_to_R_i(v, phase)  = left HF component e-field flipped to right canonical space
E_ULF_R_i(v, phase)      = right ULF component e-field
E_ULF_L_to_R_i(v, phase) = left ULF component e-field flipped to right canonical space
```

Same-side alternating subprograms are handled by component:

```text
E_HF_side_i(v, phase)  = voxel-wise maximum over same-side HF subprograms
E_ULF_side_i(v, phase) = voxel-wise maximum over same-side ULF subprograms
```

Interleaving is not modeled as simultaneous double-cathode stimulation. If a clinical condition contains synchronous mixed HF+ULF programming and component-specific fields are generated by turning on only the contacts assigned to one frequency component, the manifest must label those fields as component-specific proxies.

Patient-level bilateral component exposure:

```text
E_HF_component_i(v, phase) =
  (E_HF_R_i(v, phase) + E_HF_L_to_R_i(v, phase)) / 2

E_ULF_component_i(v, phase) =
  (E_ULF_R_i(v, phase) + E_ULF_L_to_R_i(v, phase)) / 2
```

Frequency only classifies the component as HF or ULF. Exposure is not scaled by frequency or pulse width in the primary direct voxel analysis.

### ULF Candidate Space

Sparse ULF candidate construction is phase-specific:

```text
candidate_sparse_threshold = 100 V/m
Candidate_ULF_phase(v) = any valid subject has E_ULF_component_i(v, phase) > 100 V/m
```

The candidate mask is used only for sparse matrix construction. It is not the statistical threshold. A candidate mask built at `180 V/m` is incomplete for the intended resolver because the declared scan includes `tau=100` and `tau=150`.

The declared ULF source scan grid is:

```text
tau, V/m:
  100, 150, 180, 200, 220, 250, 300, 350, 400, 500

Coverage:
  5, 6, 7, 8, 10, 12
```

For each ULF source tau, Coverage threshold, and endpoint phase:

```text
tau_ULF_source =
  current ULF source-grid tau

tau_HF_overlap =
  hf_voxel_selected_tau_v_per_m,
    if hf_voxel_source_status is pre_specified_accepted or scan_fallback_accepted
  +Inf,
    if hf_voxel_source_status is absent_no_stable_grid

HF_active_i(v, phase) =
  E_HF_component_i(v, phase) > tau_HF_overlap

Coverage_ULF_tau(v, phase) =
  sum_i I[
    E_ULF_component_i(v, phase) > tau_ULF_source
    and not HF_active_i(v, phase)
  ]

Omega_ULF_tau_coverage(phase) =
  {v in Candidate_ULF_phase : Coverage_ULF_tau(v, phase) >= coverage_threshold}

X_ULF_only_i(v, phase, tau_ULF_source, coverage_threshold) =
  E_ULF_component_i(v, phase),
    if v in Omega_ULF_tau_coverage(phase)
    and not HF_active_i(v, phase)
  0, otherwise
```

For both HF/reference and ULF/add-on direct voxel models, tau defines Coverage
and Omega only. Once a voxel enters Omega, every non-overlap subject retains
the continuous ULF E-field value even when that subject's value is at or below
the current ULF tau. HF component activity for overlap exclusion is defined by
the locked HF selected tau, not the ULF source tau. If no HF source exists,
`tau_HF_overlap = +Inf`, no HF-overlap voxels are excluded, and ULF-only
exposure equals continuous ULF exposure inside Omega. Round 2 first evaluates
the pre-specified `ULF tau=200 V/m, Coverage>=5` source, then evaluates the
declared scan grid if needed. Round 7 uses `0.9 * selected_tau` and
`1.1 * selected_tau` at `selected_coverage`.

Continuous `X_ULF_only_i(v, phase, tau)` values are used for modeling inside `Omega_ULF_tau_coverage`. Voxels with both HF and ULF activation are excluded from the primary ULF-only predictor and represented by HF-overlap outputs.

### HF-Overlap Exclusion Outputs

HF-overlap is subject-specific, phase-specific, Omega-specific, and HF-overlap-rule-specific:

```text
HF_ULF_overlap_i(v, phase, tau_ULF_source, coverage_threshold, tau_HF_overlap) =
  HF_active_i(v, phase) and v in Omega_ULF_tau_coverage(phase)
```

When `tau_HF_overlap = +Inf`, the overlap mask is all false and the manifest must record `hf_overlap_rule = no_hf_source_no_overlap_exclusion`.

Do not store only one ambiguous binary overlap mask. Required overlap outputs are:

```text
direct_voxel_ULF_only_HF_overlap_coverage.nii.gz
direct_voxel_ULF_only_HF_overlap_fraction.nii.gz
direct_voxel_ULF_only_HF_overlap_subject_summary.csv
direct_voxel_ULF_only_HF_overlap_exclusion_mask_display.nii.gz
```

The display exclusion mask may be a full-sample `any-subject overlap` or `coverage>=1` mask, but its definition must be recorded explicitly in the manifest.

## DeltaHFScore

The model-matched HF adjustment comes from the locked HF direct voxel model.

For a given full-sample map or LOOCV training fold:

```text
V_HF_score = Omega_HF_selected_tau_selected_coverage intersect valid M_HF voxels
n_valid_HF_score_voxels = |V_HF_score|

S_HF_voxel(E)_i =
  sum_{u in V_HF_score} E_i(u) * M_HF(u)
  / n_valid_HF_score_voxels
```

Endpoint-specific HF efficacy-change covariates:

```text
DeltaHFScore_immediate_i =
  S_HF_voxel(E_HF_component, T2 immediate HF+ULF programming)_i
  - S_HF_voxel(E_HF_only_reference, T2 HF-only 3m programming)_i

DeltaHFScore_chronic_i =
  S_HF_voxel(E_HF_component, T3 HF+ULF 3m programming)_i
  - S_HF_voxel(E_HF_only_reference, T2 HF-only 3m programming)_i
```

If the HF component settings in HF+ULF are identical to the T2 HF-only reference settings, `DeltaHFScore` should be near zero except for numerical interpolation and component-labeling differences. If the HF component changed, `DeltaHFScore` captures the model-predicted HF efficacy shift caused by HF-component reprogramming.

`DeltaHFScore` is not assigned a fixed biological scaling coefficient before modeling. It must be z-scored for the adjusted nuisance design. Full-sample descriptive fitting uses the full-sample mean and population standard deviation. In LOOCV, the mean and population standard deviation are estimated from the training rows only and then applied to both training and held-out values. The held-out patient's raw `DeltaHFScore` must itself be computed from the training-fold HF map, not a full-sample HF map. A zero or non-estimable training-fold standard deviation is `invalid_delta_reference_scaling`, not an error-nonpredictive result.

### HF-Map Support And DeltaHFScore Support Adequacy

`M_HF(u)` is defined only on `V_HF_score`. DeltaHFScore must quantify the predicted effect of HF component reprogramming only where the locked HF selected source has learned support. Voxels outside the accepted HF source must not be extrapolated, smoothed into support, nearest-neighbor assigned, or added to the locked HF map post hoc.

Primary rule:

```text
DeltaHFScore uses in-support HF projection only.
```

That is:

```text
S_HF_voxel(E)_i =
  sum_{u in V_HF_score} E_i(u) * M_HF(u)
  / n_valid_HF_score_voxels
```

HF exposure outside `V_HF_score` contributes `0` to `DeltaHFScore` because the HF model has no learned coefficient there. This zero contribution means "unscored / outside learned support", not "biologically no HF effect".

DeltaHFScore support adequacy is defined from the HF+ULF HF-component suprathreshold coverage range, not from e-field intensity sums or from the HF-only reference coverage. The coverage threshold is the locked HF selected tau:

```text
tau_HF_selected =
  hf_voxel_selected_tau_v_per_m

A_HFplusULF_HFcomp_i =
  {u in right_canonical_HF_grid : E_HFplusULF_HFcomp_i(u) > tau_HF_selected}

HF_component_coverage_total_voxels_i =
  count(A_HFplusULF_HFcomp_i)

HF_component_coverage_in_support_voxels_i =
  count(A_HFplusULF_HFcomp_i intersect V_HF_score)

HF_component_coverage_out_support_fraction_i =
  1 - HF_component_coverage_in_support_voxels_i
      / HF_component_coverage_total_voxels_i
```

If `HF_component_coverage_total_voxels_i = 0` for any required subject or fold, set `delta_hfscore_support_status = invalid_no_hfcomponent_coverage` for that branch. Do not compute the fraction by adding an epsilon denominator. Do not use the intensity sum of `DeltaE_HF_i(u)` as the support adequacy criterion.

Required outputs:

```text
direct_voxel_ULF_only_delta_hf_support_summary.csv
direct_voxel_ULF_only_delta_hf_support_qc.json
```

Required fields include:

```text
subject_id
endpoint
phase
hf_selected_tau_v_per_m
hf_selected_coverage
ulf_selected_tau_v_per_m
ulf_selected_coverage
score_map_source
n_hf_score_voxels
tau_HF_selected
HF_component_coverage_total_voxels
HF_component_coverage_in_support_voxels
HF_component_coverage_out_support_fraction
delta_hfscore_support_status
DeltaHFScore_in_support
DeltaHFScore_source_branch
fold_id if LOOCV
```

Default decision rules:

```text
Proceed without downgrading:
  delta_hfscore_support_status = adequate
  cohort median HF_component_coverage_out_support_fraction <= 0.20
  and no more than 25% of subjects have HF_component_coverage_out_support_fraction > 0.50

Proceed but downgrade interpretation:
  delta_hfscore_support_status = limited
  support is worse than adequate
  but not invalid_extreme_out_of_support

Do not run the DeltaHF-adjusted branch:
  delta_hfscore_support_status = invalid_no_hfcomponent_coverage
  or
  delta_hfscore_support_status = invalid_extreme_out_of_support
  cohort median HF_component_coverage_out_support_fraction > 0.50
  or more than 25% of subjects have HF_component_coverage_out_support_fraction > 0.80
  or any required subject or LOOCV fold has
     HF_component_coverage_out_support_fraction > 0.95.

`Almost entirely outside` is therefore a fixed numeric rule (`> 0.95`), not a
qualitative reviewer judgment.
The comparison is strict: a value equal to `0.95` does not satisfy this extreme
subject/fold criterion.
```

When downgraded, report:

```text
DeltaHFScore represents only the in-support projection of HF-component change.
Substantial HF+ULF HF-component suprathreshold coverage lay outside the learned HF 3-month map support.
```

Recommended sensitivity when delta-support limitation is nontrivial:

```text
Y_post ~ ULFScore_mean_main + Y_HF_ref + DeltaHFScore_in_support
```

with `HF_component_coverage_out_support_fraction` reported descriptively. Do not include raw HF out-of-support exposure as a fourth predictor in the primary DeltaHFScore support analysis.

Do not expand the locked HF support after seeing ULF results. DeltaHFScore must use the HF selected source recorded by the HF resolver. Voxels outside the accepted HF source remain unscored.

## Statistical Model

### Core Branch A: DeltaHF-Adjusted Partial Spearman

For each endpoint, phase, tau, and voxel `v`, use rank-residual partial Spearman with average ranks for ties:

```text
rho_ULF(v) =
  corr(
    resid(rank(Y_post_i)                  ~ rank(Y_HF_ref_i) + rank(DeltaHFScore_i)),
    resid(rank(X_ULF_only_i(v, phase,tau)) ~ rank(Y_HF_ref_i) + rank(DeltaHFScore_i))
  )
```

Degenerate voxels with zero ULF-only exposure variance, zero rank variance, or zero residualized exposure variance are assigned `rho_ULF(v)=NaN` and excluded from `ULFScore_mean_main`.

Benefit-oriented map:

```text
M_ULF(v) = -rho_ULF(v)   for lower-is-better scales
M_ULF(v) =  rho_ULF(v)   for higher-is-better scales
```

Positive `M_ULF(v)` consistently means ULF-only sweet or benefit-associated. Negative `M_ULF(v)` means ULF-only sour or worse-outcome-associated.

### Core Branch B: No-DeltaHF Partial Spearman

The no-DeltaHF estimator removes `DeltaHFScore` but keeps the same-day or pre-ULF HF clinical state:

```text
rho_ULF_noDeltaHF(v) =
  corr(
    resid(rank(Y_post_i)                  ~ rank(Y_HF_ref_i)),
    resid(rank(X_ULF_only_i(v, phase,tau)) ~ rank(Y_HF_ref_i))
  )
```

This branch is not intrinsically secondary. It is the intended primary branch when the matched HF voxel source exists but `hf_voxel_prediction_status = error_nonpredictive`, and it is the only primary branch when the matched HF voxel source is absent. When HF is `error_predictive` but intended adjusted has invalid inputs, invalid design, or `absent_no_stable_grid`, accepted no-delta may be reported as `fallback_final_no_delta_hf`. Otherwise, it reports how much the ULF map depends on the model-derived HF adjustment.

### Gain Endpoint Sensitivity Estimator

For direction-normalized gain endpoints:

```text
rho_ULF_gain(v) =
  corr(
    resid(rank(Gain_i)                    ~ rank(DeltaHFScore_i)),
    resid(rank(X_ULF_only_i(v, phase,tau)) ~ rank(DeltaHFScore_i))
  )
```

For the immediate endpoint, this is a same-day add-on gain sensitivity. For chronic endpoint, it is a post-add-on change sensitivity.

### Total ULF Exposure Sensitivity

The primary predictor excludes HF-overlap voxels. A predeclared sensitivity keeps total ULF component exposure:

```text
X_ULF_total_i(v, phase) = E_ULF_component_i(v, phase)
```

The total-ULF branch uses the same covariates, estimator, score definition, LOOCV logic, and output family, but it is explicitly labeled:

```text
branch = total_ulf_exposure_sensitivity
```

This branch tests whether ULF-associated signal is lost when the primary model hard-excludes HF-overlap territory.

### Optional Supplemental Estimator: OLS ANCOVA

OLS ANCOVA is retained as an optional future supplemental estimator. It is not run in the current executable analysis and does not generate output files in this run.

```text
delta_hf_adjusted:
  Y_post_i = alpha_v
           + theta_ULF(v) * X_ULF_only_i(v)
           + beta_v      * Y_HF_ref_i
           + gamma_v     * DeltaHFScore_i
           + error_i,v

no_delta_hf:
  Y_post_i = alpha_v
           + theta_ULF(v) * X_ULF_only_i(v)
           + beta_v      * Y_HF_ref_i
           + error_i,v
```

If enabled in a future run, the OLS estimator should generate the same output family under an `ols_ancova/` estimator directory. Its `direct_voxel_ULF_only_coef.nii.gz` would store `theta_ULF(v)`, whereas the current `partial_spearman/` coefficient file stores `rho_ULF(v)`.

### Patient-Level Score

Primary patient-level ULF-only sweet-spot score:

```text
V_score = Omega_ULF_tau_coverage intersect valid M_ULF voxels
n_valid_score_voxels = |V_score|

ULFScore_mean_main_i =
  sum_{v in V_score} X_ULF_only_i(v, phase,tau) * M_ULF(v)
  / n_valid_score_voxels
```

This is the primary ULF-only prediction score. It is a voxel-count-normalized, voxel-correlation-weighted mean ULF-only exposure over the fixed scoring voxel set for the corresponding full-sample map or LOOCV training fold. It is not divided by `sum(X)` and is not multiplied by voxel volume. If `V_score` is empty, the branch/fold fails QC instead of producing a score. If a subject/fold has no ULF-only exposure in a non-empty valid scoring voxel set, `ULFScore_mean_main_i` is recorded as `0`.

DeltaHF-adjusted prediction model:

```text
Y_post_i = alpha
         + delta * ULFScore_mean_main_i
         + beta  * Y_HF_ref_i
         + gamma * DeltaHFScore_i
         + error_i
```

DeltaHF-adjusted covariate-only baseline:

```text
Y_post_i = alpha
         + beta  * Y_HF_ref_i
         + gamma * DeltaHFScore_i
         + error_i
```

No-DeltaHF prediction model:

```text
Y_post_i = alpha
         + delta * ULFScore_mean_main_i
         + beta  * Y_HF_ref_i
         + error_i
```

No-DeltaHF covariate-only baseline:

```text
Y_post_i = alpha
         + beta * Y_HF_ref_i
         + error_i
```

Both core branch prediction models are fit on the raw post-score scale. The primary validation statistic remains rank-based LOOCV Spearman rho. The HF branch-role resolver determines the intended primary branch; the ULF voxel resolver determines whether that branch is realized as a selected-source primary model and whether it is source-stable and error-predictive.

Missing-data rule: missing `Y_post`, missing `Y_HF_ref`, or failed e-field availability fails the endpoint/run after QC. Missing or invalid `DeltaHFScore` fails only the DeltaHF-adjusted branch; the no-DeltaHF branch may still run and must record why the adjusted branch was unavailable. For configurable future endpoints, the endpoint is skipped if the valid sample size falls below 12.

## Validation

- Model chronic T3 and same-day immediate T2 endpoints separately.
- Use leave-one-patient-out cross-validation with no inner hyperparameter tuning.
- In each outer fold, rebuild the branch-specific nuisance inputs, rebuild `Omega_ULF_tau_coverage`, fit the ULF-only voxel map, compute training and held-out `ULFScore_mean_main`, and fit the final prediction model using only training patients.
- For the DeltaHF-adjusted branch, rebuild the HF direct voxel map needed for `DeltaHFScore`, compute fold-specific `DeltaHFScore`, compute fold-specific `HF_component_coverage_out_support_fraction`, and compare against `Y_post ~ Y_HF_ref + DeltaHFScore`.
- For the no-DeltaHF branch, omit `DeltaHFScore` from map estimation, scoring, prediction, permutation nuisance models, and baseline comparison; compare against `Y_post ~ Y_HF_ref`.
- Run executable core branches at the observed LOOCV stage according to the locked HF branch-role rules. The branch-role resolver records the intended primary branch before ULF tau/Coverage source resolution.
- For each executable branch, assign `ulf_voxel_source_status` from the ULF hard computability filter and local tau/Coverage support.
- For each accepted ULF source, assign `ulf_voxel_prediction_status` from MAE/RMSE improvement over the branch-specific nuisance-only baseline.
- Report the gain endpoint sensitivity when endpoint data are complete.
- Primary validation statistic: LOOCV Spearman rho between held-out predictions and held-out raw outcomes.
- Secondary metrics: LOOCV Pearson `r`, MAE, RMSE, and `Q2` on the original raw outcome scale.
- Define `Q2` relative to the covariate-only baseline:

  ```text
  Q2 = 1 - SSE_ULFScore_model / SSE_covariate_only
  ```

- Patient-level Freedman-Lane permutation uses `B=10000` and random seed `42` for the final model's accepted source. Smoke/exploratory runs use `B=1000`. Formal permutation is run only when that final model has `ulf_voxel_source_status` equal to `pre_specified_accepted` or `scan_fallback_accepted`, unless the immediate endpoint is explicitly promoted to co-primary.
- For each permutation, fit the branch-specific nuisance model, permute nuisance residuals, reconstruct `Y*`, and rerun the full LOOCV pipeline including branch-specific nuisance inputs, ULF coverage, ULF map, `ULFScore_mean_main`, and prediction. The primary permutation statistic is LOOCV Spearman rho.
- Permutation p value is plus-one two-sided:

  ```text
  p = (1 + count(|stat_perm| >= |stat_obs|)) / (B + 1)
  ```

- Subject-level bootstrap uses `B=10000` and seed `42` for the final model's accepted source. Smoke/exploratory runs use `B=1000`. Each bootstrap resample reruns the full branch-specific map-building process, including `DeltaHFScore` and HF support QC only for the DeltaHF-adjusted branch, `Omega_ULF_tau_coverage`, and `direct_voxel_ULF_only_bootstrap_se.nii.gz` stores voxel-wise standard deviation of the estimator map.

For non-final executable branches, non-selected tau/Coverage cells, gain endpoint sensitivity, total-ULF sensitivity, and immediate endpoints unless co-primary, LOOCV may be run for reporting, but formal permutation/bootstrap outputs are not generated. Branches with no stable ULF source also omit formal resampling. Their manifests and QC JSON files must record:

```text
resampling_status = not_run_nonfinal | not_run_no_stable_source
resampling_reason = formal resampling restricted to accepted final model unless endpoint promoted to co-primary
```

## Execution Structure

The later code implementation should keep image preprocessing and statistical postprocessing separated.

MATLAB/Lead-DBS preprocessing:

- discover and availability-check required HF-only reference, HF-component, and ULF-component e-fields;
- classify sources by frequency (`HF > 100 Hz`, `ULF < 50 Hz`, otherwise unclassified);
- combine same-side same-frequency alternating subprograms by voxel-wise maximum;
- call `ea_flip_lr_nonlinear` for all left/right flips;
- compute left/right flip deformation audit metrics and record warnings without automatic exclusion;
- sample HF and ULF component exposure into right-hemisphere MNI grids required for ULF modeling and HF-score projection;
- write a MAT v7 design matrix and optional compressed NPZ mirror.

Required design matrix schema:

- `E_ULF_component_phase(subject x ulf_candidate_voxel)` continuous ULF component exposure;
- `E_HF_component_phase_on_ulf_grid(subject x ulf_candidate_voxel)` continuous HF component exposure used for HF-overlap exclusion;
- `X_ULF_only_tau{100,150,180,200,220,250,300,350,400,500}_phase(subject x ulf_candidate_voxel)` tau-specific ULF-only exposure;
- `S_tau{100,150,180,200,220,250,300,350,400,500}_ULF_only_phase(subject x ulf_candidate_voxel)` Boolean suprathreshold ULF-only sidecars;
- `HF_overlap_ulf_tau{100,150,180,200,220,250,300,350,400,500}_hf_overlap_rule_phase(subject x ulf_candidate_voxel)` Boolean HF/ULF overlap sidecars;
- `E_HF_component_phase_on_hf_score_grid(subject x hf_score_voxel)` continuous HF component exposure used for `DeltaHFScore`;
- `E_HF_only_reference_on_hf_score_grid(subject x hf_score_voxel)` continuous HF-only reference exposure used for `DeltaHFScore`;
- ULF candidate voxel `ijk` and MNI `xyz_mm`;
- HF score-support voxel `ijk` and MNI `xyz_mm`;
- NIfTI affine/header references;
- `subject_id`, source e-field paths, side metadata, component labels, frequency labels, visit labels, and clinical raw values;
- tau/candidate metadata, HF-overlap exclusion metadata, HF-support metadata, flip metadata, and jitter metadata placeholders.

The implementation must not store a single ULF-tau-independent `X_ULF_only` as the formal input. `X_ULF_only` is ULF-tau-specific because `tau_ULF_source` defines ULF activity and ULF coverage, while the locked HF-overlap rule defines HF activity for overlap exclusion.

Python postprocessing in the `leaddbs` Conda environment:

- read the MAT v7 design matrix or optional NPZ mirror;
- construct `Omega_ULF_tau_coverage` inside each fold;
- compute fold-specific HF direct voxel maps and `DeltaHFScore`;
- compute DeltaHFScore delta-support adequacy;
- run partial Spearman map fitting, LOOCV, permutation, bootstrap, and display output generation;
- write CSV, JSON, NIfTI maps, and figures.

Default parallelism follows the HF direct voxel model:

```text
MATLAB preprocessing workers: 8
Python jobs: 14
seed: 42
```

## Downstream Visualization And Outputs

For the future configured `direct_voxel_model_v1` publisher, the authoritative
stable layout, generic reference/add-on filenames, final-branch references, and
artifact schemas are defined in
`../config/four_model_v1/direct_voxel_output_contract.md`. The paths and
`direct_voxel_ULF_only_*` filenames below document the current legacy
executable layout only. They are not the configured publisher contract.

Output root:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/<source_slug>/<branch_slug>/
```

Selected-source branch examples:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau200_cov5/partial_spearman_delta_hf_adjusted/
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau200_cov5/partial_spearman_no_delta_hf/
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau<selected>_cov<selected>/partial_spearman_<branch_role>/
```

Non-selected source-neighborhood, gain, and total-ULF sensitivity outputs may be generated for reporting, but they are not formal selected-source outputs:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/<neighborhood_source_slug>/partial_spearman_<branch_role>/
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/<selected_source_slug>/partial_spearman_gain_endpoint/
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/<selected_source_slug>/partial_spearman_total_ulf_exposure/
```

Required outputs:

```text
direct_voxel_ULF_only_coverage.nii.gz
direct_voxel_ULF_only_coef.nii.gz
direct_voxel_ULF_only_sweet_sour.nii.gz
direct_voxel_ULF_only_stability.nii.gz
direct_voxel_ULF_only_bootstrap_se.nii.gz
direct_voxel_ULF_only_bootstrap_summary.csv
direct_voxel_ULF_only_jitter_summary.csv
direct_voxel_ULF_only_jitter_model_similarity.csv
direct_voxel_ULF_only_jitter_selected_overlap.csv
direct_voxel_ULF_only_jitter_se.nii.gz
direct_voxel_ULF_only_scores.csv
direct_voxel_ULF_only_loocv_predictions.csv
direct_voxel_ULF_only_permutation_summary.csv
direct_voxel_ULF_only_HF_overlap_coverage.nii.gz
direct_voxel_ULF_only_HF_overlap_fraction.nii.gz
direct_voxel_ULF_only_HF_overlap_subject_summary.csv
direct_voxel_ULF_only_HF_overlap_exclusion_mask_display.nii.gz
direct_voxel_ULF_only_delta_hf_support_summary.csv
direct_voxel_ULF_only_delta_hf_support_qc.json
direct_voxel_ULF_only_mapping_qc.json
direct_voxel_ULF_only_generation_manifest.json
```

Selected-source NIfTI, score, and LOOCV prediction outputs are generated only for branches with `ulf_voxel_source_status` equal to `pre_specified_accepted` or `scan_fallback_accepted`. Endpoints or branches with `absent_no_stable_grid` generate only resolver scan tables plus QC/manifest rows.

`direct_voxel_ULF_only_bootstrap_se.nii.gz`, `direct_voxel_ULF_only_bootstrap_summary.csv`, and `direct_voxel_ULF_only_permutation_summary.csv` are generated only for the final model's accepted source. Non-final branches omit these files and record `not_run_nonfinal` in their manifest and QC JSON. Branches with no stable source record `not_run_no_stable_source`.

For continuous/statistical NIfTI outputs, voxels outside the model support are written as `NaN`, not `0`. This applies to coefficient, sweet/sour, stability, bootstrap SE, HF-overlap fraction, smoothed-display, and homologous-display statistical maps outside `Omega_ULF_tau_coverage` or outside the right-canonical candidate grid. `0` is reserved for true zero-valued estimates inside support. Integer coverage/count maps and binary/exclusion display masks remain `0` outside support because their data type and semantics are count/false rather than continuous effect.

Output semantics:

- `direct_voxel_ULF_only_coverage.nii.gz` stores `Coverage_ULF_tau(v)=sum_i I[X_ULF_only_i(v, phase,tau)>tau]` for the selected tau/Coverage source. Use `int16`.
- `direct_voxel_ULF_only_coef.nii.gz` stores `rho_ULF(v)` for the executed `partial_spearman/` estimator. Optional future OLS outputs would store `theta_ULF(v)`.
- `direct_voxel_ULF_only_sweet_sour.nii.gz` stores benefit-oriented `M_ULF(v)`. Positive values indicate ULF-only benefit-associated voxels.
- `direct_voxel_ULF_only_stability.nii.gz` stores LOOCV training-fold direction stability of `M_ULF(v)>0` or `M_ULF(v)<0`, depending on display class. It is not a p value.
- `direct_voxel_ULF_only_bootstrap_se.nii.gz` stores full-process bootstrap standard deviation of the estimator map for the final model's accepted source only.
- `direct_voxel_ULF_only_bootstrap_summary.csv` stores bootstrap status, `B`, finite bootstrap count, candidate voxel count distribution, and finite-count distribution for the final source branch only.
- `direct_voxel_ULF_only_jitter_summary.csv` stores formal jitter status, `B`, FWHM/sigma settings, finite jitter count, LOOCV direction summaries, map-correlation summaries, and support-overlap summaries for the final source branch only.
- `direct_voxel_ULF_only_jitter_model_similarity.csv` stores one row per jitter resample with LOOCV metrics and full-map correlation against the non-jittered final-source map.
- `direct_voxel_ULF_only_jitter_selected_overlap.csv` stores one row per jitter resample with valid-support overlap and sign-consistency summaries against the non-jittered final-source map.
- `direct_voxel_ULF_only_jitter_se.nii.gz` stores voxel-wise standard deviation of finite jittered benefit-oriented map values for the final source branch only.
- `direct_voxel_ULF_only_scores.csv` stores patient-level scores, including `branch`, `branch_role`, `intended_primary_branch`, `ulf_final_model_id`, `delta_hfscore_role`, `fallback_final_branch`, `ulf_fallback_final_status`, `ULFScore_mean_main`, `DeltaHFScore` when applicable, `Y_HF_ref`, `HF_component_coverage_out_support_fraction`, `delta_hfscore_support_status`, `score_map_source`, `n_valid_score_voxels`, `ulf_voxel_source_status`, `ulf_voxel_prediction_status`, `ulf_endpoint_model_status`, and `is_primary_score`.
- `direct_voxel_ULF_only_loocv_predictions.csv` stores held-out predictions, observed raw outcome, branch-specific nuisance-only prediction, `ULFScore_mean_main`, `DeltaHFScore` when applicable, DeltaHFScore support fields, `MAE_nuisance_baseline`, `RMSE_nuisance_baseline`, and residuals.
- `direct_voxel_ULF_only_permutation_summary.csv` stores Freedman-Lane permutation summary for the final model's accepted source only.
- HF-overlap files store subject-level and cohort-level voxels excluded from the ULF-only predictor because ULF is active at the ULF source tau and HF is active under the locked HF-overlap rule. If no HF source exists, `tau_HF_overlap = +Inf` and the overlap mask is all false.
- DeltaHFScore support files store the in-support and out-of-support HF+ULF HF-component suprathreshold coverage used to determine whether `DeltaHFScore` is within the learned HF model support.
- `direct_voxel_ULF_only_mapping_qc.json` stores endpoint/tau/Coverage/estimator QC, including patient inclusion, candidate mask size, coverage distribution, `Omega_ULF_tau_coverage` voxel count, HF-overlap exclusion volume, DeltaHFScore delta-support adequacy, degenerate voxels, NaN handling, zero-exposure score counts, `ulf_voxel_source_status`, `ulf_voxel_prediction_status`, `ulf_endpoint_model_status`, `ulf_fallback_final_status`, `ulf_branch_input_status`, `branch_nuisance_design_status`, `corr(ULFScore_mean_main, Y_HF_ref)`, `corr(ULFScore_mean_main, DeltaHFScore)`, `corr(Y_HF_ref, DeltaHFScore)`, coefficient signs, VIF or equivalent collinearity diagnostics, flip deformation audit metrics, and design-matrix dimensions.
- `direct_voxel_ULF_only_generation_manifest.json` stores provenance, parameters, code version, conda environment, package state, random seeds, visit labels, same-day immediate reference confirmation, component-proxy labels, HF-derived branch role fields, ULF resolver fields, and runtime profile.

Primary statistical maps are unsmoothed. Display smoothing is generated only after coefficient estimation and must not be used for ULFScore, LOOCV, permutation, bootstrap, or jitter:

```text
display_smooth_fwhm1mm/
display_smooth_fwhm2mm/
```

Display maps should overlay:

```text
ULF-only sweet/sour map
HF-overlap exclusion coverage/fraction map
DeltaHFScore delta-support summaries
STN/SNr anatomical outlines
STNSNrplus territory background
```

## Left/Right Flip Deformation Audit

`ea_flip_lr_nonlinear` remains the only supported left/right flip method. The audit records warnings but does not automatically exclude subjects unless there is an input integrity failure.

QC metrics:

```text
input/output grid and affine
finite voxel count
nonzero voxel count
max, p95, p99, sum
suprathreshold volume at 180 / 200 / 220 V/m
intensity-weighted centroid
L-to-R output overlap with right canonical brainmask
component label, phase label, and side metadata
```

Empty images, all-NaN images, non-finite values, missing paths, and obvious path/component mismatches are hard failures. Ordinary deformation differences are warnings.

## Spatial Jitter QC Sensitivity

Spatial jitter is a robustness stress test applied to accepted e-field inputs. It is not an automatic localization/normalization QC procedure and is not an input-validity gate. It is run only for the selected final model unless an endpoint is explicitly promoted to co-primary.

```text
formal jitter resamples: B = 1000
smoke jitter resamples:  B = 100
seed: 42
FWHM: 2 mm
sigma: 2 / 2.355 = 0.849 mm
```

For each jitter iteration, draw an independent 3D translation vector for each subject-side HF and ULF component e-field. Apply translation-only e-field resampling with linear interpolation and outside fill value `0`. Then rebuild ULF-only exposure, HF-overlap exclusion, `Omega_ULF_tau_coverage`, `DeltaHFScore`, DeltaHFScore delta-support QC, full-sample map, ULF scores, and LOOCV validation metrics.

Do not save every jittered NIfTI map. Save a summary table, map correlation/stability summary, and voxel-wise jitter standard deviation map.

## Reference-Parameter Coverage

The ULF direct voxel model covers the same direct voxel parameter family as the HF direct voxel model where applicable:

```text
raw sim-efield, not sim-efieldgauss
right canonical voxel grid
ea_flip_lr_nonlinear left/right flip
pre-specified source = tau200/Coverage>=5
declared tau scan grid = 100, 150, 180, 200, 220, 250, 300, 350, 400, 500 V/m
declared Coverage scan grid = 5, 6, 7, 8, 10, 12
branch-specific partial Spearman
LOOCV
Freedman-Lane permutation for accepted final model
subject-level bootstrap for accepted final model
2 mm FWHM spatial jitter QC for accepted final model
display smoothing FWHM 1 mm and 2 mm, display only
```

Documented-only items for the current ULF direct voxel execution:

```text
Coverage>=6 standalone sensitivity: not generated separately; Coverage>=6 can still become the selected source if the Round 2 resolver selects that grid cell
Coverage>=8 / 50% E-field standalone rule: not generated separately; Coverage>=8 can still become the selected source if the Round 2 resolver selects that grid cell
5/7/10-fold CV: documented only; LOOCV is executable
optional OLS supplemental estimator: documented only; not run in the current execution
OSS-DBS: not part of direct voxel; belongs to normative fiber / activation sensitivity
paper-like spatial similarity score sensitivity: not included; ULFScore_mean_main is the primary score
automatic localization / electrode reconstruction QC: not included; prior manual QC is assumed
```

## Interpretation Boundary

This model estimates HF-state-adjusted ULF-only add-on association. It is not an anatomic SNr gain model. Voxels co-activated by HF and ULF are treated as HF-dominant for the primary analysis, so the ULF map represents regions uniquely recruited by ULF stimulation after accounting for HF clinical state and model-predicted HF efficacy changes.

Because the immediate HF+ULF endpoint and the HF-only 3-month clinical reference are measured on the same day, the immediate model can be interpreted as a same-day acute add-on association. The chronic model remains a post-add-on follow-up association.

Because the cohort has `n=16`, the result is hypothesis-generating. A non-significant LOOCV result should not be interpreted as proof that no biological ULF add-on sweet spot exists. The QC report must include the association between `ULFScore_mean_main`, `Y_HF_ref`, and `DeltaHFScore`, the support coverage of `DeltaHFScore`, plus a basic collinearity diagnostic for the final prediction model.

Interpret as:

```text
After accounting for same-day or pre-ULF HF state and modeled HF efficacy changes,
additional ULF-only exposure in this territory is associated with better or worse
post-HF+ULF outcome.
```

Do not interpret as:

```text
The displayed voxels prove an anatomic SNr-specific causal effect.
HF-overlap voxels have no ULF biological effect.
HF-component exposure outside the learned HF map has no biological effect.
DeltaHFScore fully removes all HF contribution when HF component reprogramming change is mostly outside the locked HF model support.
```

## Execution Efficiency

The optimized implementation must preserve the logical full-process semantics described above. In particular, LOOCV training folds still define their own HF adjustment map, `DeltaHFScore`, HF support QC, `Omega_ULF_tau_coverage`, ULF voxel map, ULF scores, and held-out predictions. Formal Freedman-Lane permutation and subject-level bootstrap still use `B=10000` and seed `42` for accepted final models. Smoke runs use `B=1000` for permutation/bootstrap and `B=100` for jitter.

### Equivalence Contract

Optimization may reuse mathematically invariant cached subcomputations, but it must not use full-sample ranks, full-sample training masks, approximate ranks, adaptive early stopping, changed declared tau/Coverage settings, changed estimators, changed HF support rules, or reduced formal resampling counts to gain speed.

Numerical reductions should use `float64` where feasible. Final NIfTI outputs use `float32` for coefficient, sweet/sour, stability, and bootstrap SE maps, and `int16` for coverage and binary/exclusion masks.

### Preprocessing Sidecar Cache

Preferred formal-loop input:

```text
E_ULF_component_<phase>_float32_voxel_major.npy
E_HF_component_<phase>_on_ulf_grid_float32_voxel_major.npy
E_HF_component_<phase>_on_hf_score_grid_float32_voxel_major.npy
E_HF_only_reference_on_hf_score_grid_float32_voxel_major.npy
X_ULF_only_tau100_<phase>_float32_voxel_major.npy
X_ULF_only_tau150_<phase>_float32_voxel_major.npy
X_ULF_only_tau180_<phase>_float32_voxel_major.npy
X_ULF_only_tau200_<phase>_float32_voxel_major.npy
X_ULF_only_tau220_<phase>_float32_voxel_major.npy
X_ULF_only_tau250_<phase>_float32_voxel_major.npy
X_ULF_only_tau300_<phase>_float32_voxel_major.npy
X_ULF_only_tau350_<phase>_float32_voxel_major.npy
X_ULF_only_tau400_<phase>_float32_voxel_major.npy
X_ULF_only_tau500_<phase>_float32_voxel_major.npy
S_tau100_ULF_only_<phase>_bool.npy
S_tau150_ULF_only_<phase>_bool.npy
S_tau180_ULF_only_<phase>_bool.npy
S_tau200_ULF_only_<phase>_bool.npy
S_tau220_ULF_only_<phase>_bool.npy
S_tau250_ULF_only_<phase>_bool.npy
S_tau300_ULF_only_<phase>_bool.npy
S_tau350_ULF_only_<phase>_bool.npy
S_tau400_ULF_only_<phase>_bool.npy
S_tau500_ULF_only_<phase>_bool.npy
HF_overlap_ulf_tau100_hf_overlap_rule_<phase>_bool.npy
HF_overlap_ulf_tau150_hf_overlap_rule_<phase>_bool.npy
HF_overlap_ulf_tau180_hf_overlap_rule_<phase>_bool.npy
HF_overlap_ulf_tau200_hf_overlap_rule_<phase>_bool.npy
HF_overlap_ulf_tau220_hf_overlap_rule_<phase>_bool.npy
HF_overlap_ulf_tau250_hf_overlap_rule_<phase>_bool.npy
HF_overlap_ulf_tau300_hf_overlap_rule_<phase>_bool.npy
HF_overlap_ulf_tau350_hf_overlap_rule_<phase>_bool.npy
HF_overlap_ulf_tau400_hf_overlap_rule_<phase>_bool.npy
HF_overlap_ulf_tau500_hf_overlap_rule_<phase>_bool.npy
ulf_candidate_ijk.npy
ulf_candidate_xyz_mm.npy
hf_score_support_ijk.npy
hf_score_support_xyz_mm.npy
candidate_mask_metadata.json
hf_support_metadata.json
```

Voxel-major layout is preferred because voxel chunks are contiguous on disk. MAT and compressed NPZ files may be retained for archival, compatibility, and debugging. Compressed NPZ must not be the primary random-access input inside formal permutation, bootstrap, or jitter loops.

### Coverage And Fold Mask Cache

For each tau and phase, precompute:

```text
S_tau(v, i, phase) = I[X_ULF_only_i(v, phase,tau) > tau]
Coverage_tau_all(v, phase) = sum_i S_tau(v, i, phase)
Coverage_tau_fold_h(v, phase) = Coverage_tau_all(v, phase) - S_tau(v, h, phase)
Omega_ULF_tau_coverage_fold_h(phase) =
  {v : Coverage_tau_fold_h(v, phase) >= coverage_threshold}
```

`coverage_threshold` is the current grid cell's Coverage value in Round 2 and `selected_coverage` for selected-source formal analyses. `HF_overlap_ulf_tau*_hf_overlap_rule_bool` can be cached because it depends only on accepted HF/ULF component exposures, ULF tau, and the locked HF-overlap rule, not on outcome.

### Vectorized Partial Spearman Kernel

For every training fold, ranks are computed within the training set only. Full-sample ranks are prohibited for LOOCV map fitting, permutation map fitting, bootstrap maps, and jitter resamples.

The DeltaHF-adjusted core branch residualizes both outcome and exposure against:

```text
rank(Y_HF_ref_train)
rank(DeltaHFScore_train)
```

The no-DeltaHF core branch residualizes against:

```text
rank(Y_HF_ref_train)
```

### Fold-Level Score Operator For Permutation

Formal Freedman-Lane permutation for the accepted final model may use a fold-level score operator, but it must remain logically equivalent to recomputing the full ULF map and `ULFScore_mean_main` for every permuted outcome.

Each permutation must have its own:

```text
DeltaHFScore if recomputed under the fold/HF map semantics
rho_ULF(v)
M_ULF(v)
V_score
ULFScore_mean_main
held-out prediction
LOOCV statistic
```

### Bootstrap Efficiency

Subject-level bootstrap remains a full-process map stability analysis for the accepted final model. It must rebuild bootstrap `DeltaHFScore`, HF support QC, `Omega_ULF_tau_coverage`, `rho_ULF`, and `M_ULF`. Bootstrap SE is accumulated by streaming Welford updates. The implementation must not store 10000 bootstrap maps.

### Spatial Jitter Efficiency

Jitter changes e-field geometry. Primary `X`-derived caches are invalid under jitter and must not be reused as if exposure were unchanged. Each jitter iteration must rebuild HF component exposure, ULF component exposure, HF-overlap exclusion, ULF-only exposure, candidate mask, `Omega_ULF_tau_coverage`, `DeltaHFScore`, HF support QC, map, scores, and LOOCV metrics.

### Prohibited Speed Shortcuts

Formal runs prohibit:

```text
adaptive permutation early stopping
reduced formal B
changed declared tau/Coverage settings
changed estimator
full-sample ranks inside LOOCV/permutation/bootstrap
approximate ranks
using anatomical overlay masks as the analysis mask
dropping requested jitter QC
using a tau-independent X_ULF_only matrix
using total ULF exposure in place of ULF-only exposure for the primary branch
including HF-overlap voxels in the primary ULF predictor
expanding the locked HF score support after seeing ULF results
imputing or smoothing HF map coefficients outside V_HF_score
using compressed NPZ as the random-access formal-loop input
```

### Runtime Profile

`direct_voxel_ULF_only_generation_manifest.json` should include:

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
    "selected_tau_v_per_m": null,
    "selected_coverage": null,
    "n_voxels_selected_mean": null,
    "n_voxels_selected_min": null,
    "n_voxels_selected_max": null,
    "n_hf_overlap_selected_mean": null,
    "hf_component_coverage_out_support_fraction_summary": null,
    "python_jobs": null,
    "blas_threads": null,
    "memmap_sidecars": [],
    "bootstrap_finite_count_summary": null
  }
}
```

### Equivalence And Regression Tests

Before formal runs, compare brute-force and optimized implementations on a deterministic subset:

```text
B_perm = 20
B_boot = 20
n_voxel_subset = 100 to 1000
seed = 42
```

Compare:

```text
fold-specific DeltaHFScore
fold-specific DeltaHFScore delta-support adequacy
fold-specific Omega_ULF_tau_coverage
HF-overlap exclusion masks
partial Spearman rho map
benefit-oriented M_ULF map
ULFScore_mean_main
LOOCV held-out predictions
LOOCV Spearman rho
permutation null statistics
bootstrap SE for finite voxels
```

Required tolerances:

```text
exact equality for masks, subject IDs, voxel IDs, and split indices
near equality for float outputs under float64 reductions
same NaN/degenerate voxel locations
same plus-one p value for the deterministic small test
```

## Execution Priority And Reporting Workflow

Run the ULF direct voxel analysis in stages so the HF-derived branch role, ULF selected source, and endpoint classification are written before expensive reporting analyses run.

### Round 0: Input Readiness And HF Resolver Lock

Run:

```text
clinical table audit:
  Y_HF_ref exists at T2 HF-only 3-month same-day reference
  Y_post_immediate exists at T2 HF+ULF same-day immediate endpoint, if modeled
  Y_post_chronic exists at T3 HF+ULF 3-month endpoint, if modeled
  ID joins to imaging subject
  scale direction is defined
  n_subjects >= 12 for every modeled endpoint row

visit chronology audit:
  T0 preoperative baseline exists when available
  T1 1-month HF immediate opening visit exists when available
  T2 HF-only 3-month and HF+ULF immediate are same-day or same-session
  T3 HF+ULF 3-month follow-up phase is labeled

e-field availability check:
  HF-only T2 reference e-fields exist
  HF+ULF immediate HF-component e-fields exist when immediate endpoint is modeled
  HF+ULF immediate ULF-component e-fields exist when immediate endpoint is modeled
  HF+ULF chronic HF-component e-fields exist when chronic endpoint is modeled
  HF+ULF chronic ULF-component e-fields exist when chronic endpoint is modeled
  all matches are unique
  raw sim-efield is used

component audit:
  HF frequency >= 100 Hz
  ULF frequency <= 50 Hz
  mixed or proxy component fields are labeled

locked HF model audit:
  hf_3m_direct_voxel_model source resolver fields exist
  hf_voxel_source_status is recorded
  hf_voxel_prediction_status is recorded
  hf_voxel_selected_tau_v_per_m and hf_voxel_selected_coverage are recorded when a source exists
  HFScore_mean_main and M_HF support are valid when a source exists
  fold-specific map generation is available for LOOCV DeltaHFScore when a source exists
```

`available_ulf_endpoint_count` is the number of ULF endpoint rows that pass Round 0 endpoint readiness, including clinical availability, defined scale direction, `n_subjects >= 12`, uniquely matched endpoint-specific raw e-fields, and at least one executable branch. Endpoint rows that fail Round 0 are recorded as input/readiness failures and are not included in the Round 2 all-endpoint denominator. Branch-specific inputs are evaluated separately: invalid `DeltaHFScore` fails only the `delta_hf_adjusted` branch, while `no_delta_hf` may still run.

After the locked HF resolver is read, define the HF-derived intended branch role. This step does not use ULF tau or Coverage; it only defines branch identity before branch-specific ULF source resolution:

```text
if hf_voxel_source_status is pre_specified_accepted or scan_fallback_accepted:
  run no_delta_hf
  attempt/run delta_hf_adjusted only if DeltaHFScore inputs are valid

if hf_voxel_prediction_status == error_predictive:
  intended_primary_branch = delta_hf_adjusted
  ulf_primary_branch = delta_hf_adjusted
  if DeltaHFScore inputs are invalid:
    ulf_endpoint_model_status = primary_branch_input_failure
    fallback_final_branch = no_delta_hf, if it has an accepted ULF source

if hf_voxel_prediction_status == error_nonpredictive:
  intended_primary_branch = no_delta_hf
  ulf_primary_branch = no_delta_hf

if hf_voxel_source_status == absent_no_stable_grid:
  run no_delta_hf only
  intended_primary_branch = no_delta_hf
  ulf_primary_branch = no_delta_hf
```

### Round 1: Preprocessing Sidecars, Overlap QC, And HF Support QC

Run preprocessing sidecars and flip audit:

```text
candidate_sparse_threshold = 100 V/m
E_ULF_component matrix is non-empty
E_HF_component matrix is non-empty
X_ULF_only_tau{100,150,180,200,220,250,300,350,400,500} sidecars are available
S_tau{100,150,180,200,220,250,300,350,400,500} sidecars are available
HF_overlap_ulf_tau{100,150,180,200,220,250,300,350,400,500}_hf_overlap_rule outputs are valid even if overlap is zero
each subject has nonzero HF component exposure
each subject has nonzero or explicitly absent ULF-only exposure
DeltaHFScore support summary is generated for delta_hf_adjusted branches
HF_component_coverage_out_support_fraction and delta_hfscore_support_status are recorded for delta_hf_adjusted branches
```

If the full-sample `tau200/Coverage>=5` ULF Omega is empty, Round 1 still proceeds to Round 2. The pre-specified grid cannot be accepted, and the scan resolver determines whether a fallback source exists. If ULF-only exposure is empty for most subjects across the declared grid, record the support limitation and allow Round 2 to assign `absent_no_stable_grid`.

### Round 2: Observed LOOCV, Tau/Coverage Scan, Branch Source Resolver, And Endpoint Realization

Run the same observed LOOCV resolver for every available ULF endpoint row, endpoint phase, and executable branch. The engineering implementation treats all available endpoints equivalently; chronic, immediate, total score, and subscale rows are endpoint rows, not special execution classes. `intended_primary_branch` is already defined before this round, but the realized ULF model is not defined until this round selects a branch-specific tau/Coverage source.

For each endpoint/phase/branch, first evaluate the pre-specified grid:

```text
branch = tau200 / Coverage>=5 / partial_spearman / <delta_hf_adjusted|no_delta_hf>
candidate_sparse_threshold = 100 V/m
Omega_ULF_tau200_cov5 = {v in Candidate_tau100 : Coverage_200 >= 5}
score = ULFScore_mean_main
validation = LOOCV
nuisance baseline:
  no_delta_hf:       Y_post ~ Y_HF_ref
  delta_hf_adjusted: Y_post ~ Y_HF_ref + DeltaHFScore
```

If the pre-specified grid is not accepted, use the tau/Coverage scan inside this same round to select a fallback source or declare no stable source. The scan grid is:

```text
tau, V/m:
  100, 150, 180, 200, 220, 250, 300, 350, 400, 500

Coverage:
  5, 6, 7, 8, 10, 12
```

This yields `60` grid cells per endpoint/phase/branch and `available_ulf_endpoint_count x executable_branch_count x 60` rows for a single phase. `tau=100` and `tau=150` require a dedicated candidate sidecar with `candidate_sparse_threshold = 100 V/m`; using a sidecar built at `180 V/m` for those cells is incomplete and not allowed.

Each grid cell reports:

```text
tau
coverage
branch
branch_role
n_subjects
n_voxels_full
fold_n_voxels_min
fold_n_voxels_median
fold_n_voxels_max
branch_nuisance_design_status
LOOCV Spearman rho
LOOCV Spearman nominal p
LOOCV Pearson r
Q2
MAE_model
MAE_nuisance_baseline
RMSE_model
RMSE_nuisance_baseline
corr(ULFScore_mean_main, Y_HF_ref)
corr(ULFScore_mean_main, DeltaHFScore) if applicable
HF_component_coverage_out_support_fraction_summary if applicable
```

Then assign:

```text
ulf_voxel_source_status =
  pre_specified_accepted if tau200/Coverage>=5 and at least 2 adjacent cells pass the hard computability filter
  scan_fallback_accepted if tau200/Coverage>=5 is not accepted and a fallback grid cell passes the same source-stability rule
  absent_no_stable_grid if no stable grid cell exists

ulf_voxel_prediction_status =
  error_predictive if MAE_model < MAE_nuisance_baseline and RMSE_model < RMSE_nuisance_baseline
  error_nonpredictive if a source exists but either error comparison fails
  not_applicable if no stable source exists
```

For `scan_fallback_accepted`, choose the fallback grid without using `Q2`, rho, nominal p, or any other outcome-performance metric:

```text
1. minimize grid distance from tau200/Coverage>=5
2. maximize adjacent passing grid cells
3. maximize fold_n_voxels_min
4. prefer stricter Coverage
5. prefer higher tau
```

Generate per endpoint/phase/branch with an accepted final source:

```text
direct_voxel_ULF_only_coverage.nii.gz
direct_voxel_ULF_only_coef.nii.gz
direct_voxel_ULF_only_sweet_sour.nii.gz
direct_voxel_ULF_only_stability.nii.gz
direct_voxel_ULF_only_scores.csv
direct_voxel_ULF_only_loocv_predictions.csv
direct_voxel_ULF_only_mapping_qc.json
direct_voxel_ULF_only_generation_manifest.json
```

For branches with `absent_no_stable_grid`, do not generate selected-source NIfTI maps, score files, LOOCV prediction files, permutation summaries, bootstrap maps, or jitter outputs. Generate only resolver scan tables plus a branch-level QC/manifest row recording `ulf_voxel_source_status = absent_no_stable_grid` and `ulf_voxel_prediction_status = not_applicable`.

Endpoint final-model realization first evaluates the HF-derived `intended_primary_branch`. If that branch has an accepted source, it is the endpoint's final model. If intended `delta_hf_adjusted` has input/design failure or `absent_no_stable_grid`, `no_delta_hf` becomes the fallback final model when it has an accepted source. This fallback is one-way. A non-final branch may still be retained as sensitivity/comparison output, but it does not otherwise define the endpoint's final model:

```text
ulf_endpoint_model_status = primary_branch_error_predictive
  if the intended primary branch has an accepted ULF source
  and ulf_voxel_prediction_status = error_predictive

ulf_endpoint_model_status = primary_branch_error_nonpredictive
  if the intended primary branch has an accepted ULF source
  but ulf_voxel_prediction_status = error_nonpredictive

ulf_endpoint_model_status = absent_no_stable_ulf_grid
  if the intended primary branch is executable
  but has ulf_voxel_source_status = absent_no_stable_grid

ulf_endpoint_model_status = primary_branch_input_failure
  if the intended primary branch cannot be evaluated because required inputs are invalid
```

Final model fields are then assigned as:

```text
if ulf_endpoint_model_status in
  {primary_branch_error_predictive, primary_branch_error_nonpredictive}:
    ulf_final_model_branch = intended_primary_branch
    ulf_final_model_role = primary

if intended_primary_branch = delta_hf_adjusted
and ulf_endpoint_model_status in
  {primary_branch_input_failure, absent_no_stable_ulf_grid}
and no_delta_hf has an accepted ULF source:
    ulf_final_model_branch = no_delta_hf
    ulf_final_model_role = fallback_final

if the intended primary branch has no accepted source
and no permitted no_delta_hf fallback has an accepted source:
    ulf_final_model_branch = none
    ulf_final_model_role = no_final_model
```

The final model status is assigned from the final branch:

```text
ulf_final_model_status = final_model_error_predictive
  if the final branch has an accepted ULF source and error_predictive status

ulf_final_model_status = final_model_error_nonpredictive
  if the final branch has an accepted ULF source and error_nonpredictive status

ulf_final_model_status = no_final_model_absent_no_stable_grid
  if no final branch has a stable ULF source

ulf_final_model_status = no_final_model_input_failure
  if no final branch is executable because required inputs or nuisance design fail
```

Permutation p values, LOOCV rho, `Q2`, bootstrap stability, and jitter stability are inference-strength or robustness fields. They do not change `ulf_voxel_source_status`, `ulf_voxel_prediction_status`, `ulf_endpoint_model_status`, `ulf_final_model_branch`, `ulf_final_model_role`, `ulf_final_model_status`, or the HF-derived `ulf_primary_branch`.

If Round 2 assigns `absent_no_stable_grid` to the intended primary branch and no permitted fallback final model exists, skip Round 3 through Round 7 for that endpoint/branch and proceed directly to Round 8 summary/manifest reporting. If intended `delta_hf_adjusted` has `primary_branch_input_failure` or `absent_no_stable_ulf_grid`, use accepted `no_delta_hf` as the final unique fallback model for downstream formal reporting.

### Alternate Assessment Periods

This is not a separate executable round. The generic runtime resolves exactly
one YAML-configured reference/add-on phase-and-program pair. A different
assessment period must be supplied through another explicit endpoint-pair
configuration and then uses the same Round 2 resolver and task factory. The
core does not define `chronic` or `immediate` endpoint classes or fields.

### Round 3: Equivalence And Smoke Reporting

Run only for accepted final models:

```text
deterministic equivalence test
smoke permutation B=1000
smoke bootstrap B=1000
smoke jitter B=100
```

Formal reporting analyses require optimized and brute-force paths to match, smoke resampling to run without artifacts, bootstrap finite-count distribution to be acceptable, and jitter direction to be recorded. Failure here does not create a new source candidate; it records an implementation or robustness limitation for the selected source.

### Round 4: Formal Permutation Reporting

Run only for the final model's accepted source:

```text
source = ulf_voxel_selected_tau_v_per_m / ulf_voxel_selected_coverage
branch_role = ulf_primary_branch
B = 10000
seed = 42
statistic = LOOCV Spearman rho
```

Permutation, p value, LOOCV rho, and `Q2` are inference-strength fields. They do not change source, prediction, endpoint, or branch-role status.

### Round 5: Formal Bootstrap

Run only for the final model's accepted source:

```text
source = ulf_voxel_selected_tau_v_per_m / ulf_voxel_selected_coverage
branch_role = ulf_primary_branch
B = 10000
seed = 42
```

Bootstrap finite counts, core sign stability, and empty-map frequency are robustness fields. They do not select a replacement source.

### Round 6: Formal Spatial Jitter

Run only for the final model's accepted source:

```text
source = ulf_voxel_selected_tau_v_per_m / ulf_voxel_selected_coverage
branch_role = ulf_primary_branch
B = 1000
FWHM = 2 mm
```

If jitter map correlation is near zero or the signal direction reverses, downgrade conclusions to spatially fragile exploratory association. Do not use jitter to select a new source.

### Round 7: Selected-Source Exposure-Definition Neighborhood Sensitivity

Run observed LOOCV sensitivity around the ULF source selected in Round 2:

```text
pre_specified_accepted:
  report 0.9 * selected_tau and 1.1 * selected_tau,
  at selected_coverage, for executable branches when inputs allow

scan_fallback_accepted:
  report 0.9 * selected_tau and 1.1 * selected_tau,
  at selected_coverage, for executable branches when inputs allow

absent_no_stable_grid:
  skip Round 7; report no stable source in Round 8
```

If `0.9 * selected_tau` or `1.1 * selected_tau` is outside the available exposure sidecar support or has no computable coverage, record that sensitivity branch as not computable. These tau-sensitivity branches are not fallback candidates and cannot replace the selected source. Coverage-neighborhood summaries may be reported separately using adjacent Coverage cells at `selected_tau`, but they are secondary support diagnostics.

Do not run formal permutation or formal bootstrap for tau-sensitivity or coverage-neighborhood cells. Non-selected manifests must record:

```text
resampling_status = not_run_nonfinal
resampling_reason = selected-source neighborhood sensitivity only
```

### Round 8: Additional Sensitivities And Endpoint Summary

Run after endpoint resolver fields are complete. For accepted final models, also wait for final-source reporting fields; for `absent_no_stable_grid` with no permitted fallback final model, use the absent QC/manifest row. When intended adjusted has `primary_branch_input_failure` or `absent_no_stable_ulf_grid`, include the primary failure reason and promote accepted `no_delta_hf` to `ulf_final_model_role = fallback_final`.

Accepted final model sensitivities:

```text
non-selected core branch comparison
gain endpoint sensitivity
total ULF exposure sensitivity
DeltaHFScore delta-support sensitivity when support limitation is nontrivial
Y_base-added collinearity sensitivity if baseline data are complete
```

One-way adjusted-primary failure fallback reporting:

```text
no_delta_hf fallback final source/prediction status
no_delta_hf fallback selected tau/Coverage when accepted
fallback observed LOOCV predictions and scores when available
fallback formal resampling status follows ulf_final_model_branch
```

The `Y_base`-added sensitivity is:

```text
delta_hf_adjusted:
  Y_post ~ ULFScore_mean_main + Y_HF_ref + DeltaHFScore + Y_base

no_delta_hf:
  Y_post ~ ULFScore_mean_main + Y_HF_ref + Y_base
```

It is a collinearity/stability check, not a replacement primary model.

Endpoint summary must include:

```text
hf_voxel_source_status
hf_voxel_prediction_status
intended_primary_branch
ulf_primary_branch
ulf_final_model_id
ulf_voxel_source_status
ulf_voxel_prediction_status
ulf_endpoint_model_status
ulf_fallback_final_status
fallback_final_branch
fallback_final_source_status
fallback_final_prediction_status
selected_tau_v_per_m
selected_coverage
selected_adjacent_passing_grid_cells
selected_grid_distance_from_pre_specified
MAE_model and MAE_nuisance_baseline
RMSE_model and RMSE_nuisance_baseline
Q2 and LOOCV rho
permutation null distribution when formal permutation exists
bootstrap finite-count summary when formal bootstrap exists
jitter stability summary when jitter exists
```

### Round 9: Display And Final Manifests

Generate display smoothing, bilateral homologous display maps, HF-overlap exclusion overlays, DeltaHFScore support summaries, STN/SNr outlines, PDF QC, and final manifests after resolver and reporting fields are complete. Display outputs must not feed back into ULFScore, LOOCV, permutation, bootstrap, jitter, source selection, prediction status, or endpoint status.

### Round 10: Optional Future Analyses

Not part of the current executable mainline:

```text
OLS ANCOVA
standalone Coverage sensitivity outside the Round 2 resolver
5/7/10-fold CV
OSS-DBS direct voxel analysis
paper-like spatial similarity score
automatic localization / electrode reconstruction QC
```

### Recommended First Batch

The first practical run should cover:

```text
Round 0
Round 1
Round 2 configured add-on observed LOOCV and source resolver
Round 3 smoke only for accepted final models
```

Concrete first-batch scope:

```text
all available ULF endpoint rows that pass Round 0
declared Round 2 tau/Coverage scan grid
executable branches determined by the locked HF resolver
partial_spearman
ULF-only exposure
HF-overlap exclusion
DeltaHFScore-adjusted branch when HF source exists and DeltaHFScore inputs are valid
no-DeltaHF branch
no-DeltaHF fallback final model when the intended DeltaHF-adjusted primary branch has input/design/source failure
DeltaHFScore delta-support QC when DeltaHFScore is used
ULFScore_mean_main
LOOCV
branch-specific nuisance-baseline comparison
equivalence test
smoke permutation B=1000 for accepted final models
smoke bootstrap B=1000 for accepted final models
smoke jitter B=100 for accepted final models
resolver scan tables
basic QC JSON + manifest
```

Only after this batch passes and an accepted final source exists should that endpoint proceed to `B=10000` formal permutation and bootstrap.
