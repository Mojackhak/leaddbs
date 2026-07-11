# Threshold-Scan- and HF-Status-Resolved ULF-Only Add-On Gain Normative Connectome Fiber Model — Revised

Version: 2026-07-06 threshold-scan and HF-source-status specification
Scope: ULF add-on normative connectome fiber-level model, aligned to `hf_3m_normative_connectome_fiber_model.md`.

---

## YAML Core Interface (Predecessor Implemented; Acceptance Paused)

The configuration/orchestration contract is documented in
`my_helper/stnsnr/four_model_yaml_core_refactor_plan.md`. This model summary
records matched-HF dependency, branch-specific exposure and nuisance design,
endpoint realization, fallback-final selection, formal resampling, controls,
OSS, jitter, and numeric reporting. Explicit user decisions govern when this
record conflicts with code, results, or another document. Shared profile,
identity, catalog, state, run store, configured branch services, final-model
realization, formal/sensitivity adapters, OSS producer/consumer, and numeric
reporting exist under `four_model_v1`. The paused acceptance run completed the
MDS-UPDRS III chronic dTOR branch through final realization, formal inference,
cheap sensitivity, and selected-source neighborhood, then stopped with OSS
source wiring failed and jitter checkpointed at `388/1000`. MDS-UPDRS IV paths
did not complete. These artifacts are bounded evidence, not complete
acceptance. The approved strict dual-frequency successor is documented in
`my_helper/stnsnr/dual_frequency_core_decoupling_design.md` and remains
`implementation_not_started`. Existing output trees remain read-only.

All configured ULF/frequency-2 endpoint scales are engineering-equivalent within
their applicable endpoint families. Chronic, immediate, total, axial, and other
configured scales use the same task factories and status fields.
Public YAML provides the shared `four_model_v1` model/formal/sensitivity
parameters. Normative fiber has no global candidate-threshold parameter;
candidate fibers are `internal-derived` by tau/Coverage cell and training fold.
Equivalence and smoke parameters are `internal-test`; matched HF status,
branch statuses, the unique final model, and artifact paths are `runtime output`.

The core statistical domain remains the configured whole connectome before
stimulation tau/Coverage filtering. Anatomical ROI restriction, VTA/ROI
postprocessing, regional heatmaps, and GUI are outside the planned core
refactor.

## 1. Research Question

Which ULF-only normative connectome streamlines are associated with additional clinical benefit after ULF stimulation is added to HF stimulation, after adjusting for the patient's pre-ULF HF clinical state, with the role of model-derived `DeltaHFScore` resolved by the matched HF normative fiber source and prediction statuses.

This is a right-canonical, full-connectome, fiber-level model. Individual streamlines from public structural connectomes are the primary modeling units. Target atlases are used only after modeling for endpoint labels, anatomical enrichment, QC, display grouping, and interpretation. They do not define the primary candidate universe or primary predictors.

Frequency definitions:

```text
HF  = high-frequency stimulation component, frequency_Hz >= 100
ULF = ultra-low-frequency stimulation component, frequency_Hz <= 50
```

The primary predictor represents streamlines uniquely recruited by the ULF component. HF-overlap streamlines are excluded from the ULF-only exposure definition. `DeltaHFScore` is run when available, but it is interpreted as the primary adjustment only when the matched HF normative fiber source exists and `hf_norm_fiber_prediction_status = error_predictive`.

---

## 2. Study Timeline And Endpoint Definitions

The clinical timeline is explicitly modeled as:

```text
T0:
  preoperative baseline assessment

T1:
  postoperative 1-month HF immediate activation assessment

T2:
  3 months after HF activation
  HF-only 3-month follow-up assessment
  same-day switch to HF+ULF
  same-day HF+ULF immediate assessment

T3:
  3 months after HF+ULF switch
  HF+ULF 3-month follow-up assessment
```

The immediate HF+ULF outcome and the HF-only 3-month clinical reference state are measured on the same day at `T2`. Therefore, the immediate endpoint is a valid same-day acute add-on endpoint, not a cross-day comparator.

Use endpoint-specific variable names:

```text
Y_HF_ref_T2_domain =
  raw HF-only 3-month score measured at T2 immediately before same-day HF+ULF switch

Y_HFplusULF_immediate_T2_domain =
  raw same-day HF+ULF immediate score after switching to HF+ULF at T2

Y_HFplusULF_3m_T3_domain =
  raw HF+ULF 3-month score measured at T3
```

Two endpoint families are modeled separately.

### 2.1 Chronic endpoint

```text
Y_post = Y_HFplusULF_3m_T3_domain
Y_HF_ref = Y_HF_ref_T2_domain
DeltaHFScore = DeltaHFScore_chronic_domain
```

Interpretation:

```text
sustained HF-state-adjusted ULF add-on association after 3 months of HF+ULF exposure
```

### 2.2 Immediate endpoint

```text
Y_post = Y_HFplusULF_immediate_T2_domain
Y_HF_ref = Y_HF_ref_T2_domain
DeltaHFScore = DeltaHFScore_immediate_domain
```

Interpretation:

```text
same-day HF-state-adjusted ULF acute add-on association
```

### 2.3 Executable endpoint rows and reporting hierarchy

Executable endpoint rows:

```text
all available HF+ULF post-add-on clinical scales joined by ID
within the chronic and same-day immediate endpoint families
```

Engineering implementation treats every available endpoint/scale row equivalently within its endpoint family. No scale receives special execution status in the ULF source resolver, prediction-status assignment, endpoint realization, or output generation.

Reporting hierarchy may still name one chronic clinical row as primary and may still treat same-day immediate rows as secondary or explicitly promoted co-primary. This hierarchy is a reporting/resource decision and does not change the model definition for other available endpoint rows.

### 2.4 Add-on gain sensitivity endpoints

Because the primary model is a raw post-score ANCOVA-style model, add-on gain should be reported as sensitivity.

For lower-is-better scales:

```text
Gain_immediate_i = Y_HF_ref_T2_i - Y_HFplusULF_immediate_T2_i
Gain_chronic_i   = Y_HF_ref_T2_i - Y_HFplusULF_3m_T3_i
```

For higher-is-better scales:

```text
Gain_immediate_i = Y_HFplusULF_immediate_T2_i - Y_HF_ref_T2_i
Gain_chronic_i   = Y_HFplusULF_3m_T3_i - Y_HF_ref_T2_i
```

In all gain definitions:

```text
positive Gain = improvement after adding ULF
```

Gain sensitivity models are branch-specific:

```text
no_delta_hf:
  Gain_i = alpha
         + delta * NetULFFiberScore_noDeltaHF_i
         + error_i

delta_hf_adjusted:
  Gain_i = alpha
         + delta * NetULFFiberScore_deltaHF_i
         + gamma * DeltaHFScore_i
         + error_i
```

This sensitivity checks whether the primary raw post-score model agrees with a direct within-subject add-on gain formulation.

---

## 3. Inputs

Required inputs:

```text
Public Lead-DBS structural connectomes:
  PPMI 85
  MGH-USC HCP 32
  dTOR-985 Full

HF+ULF programming split into HF and ULF components
Raw sim-efield or accepted e-field-like exposure maps for HF component and ULF component
HF-only reference e-fields from the pre-ULF HF-only phase
Raw HF-only and HF+ULF clinical scores
Normative HF fiber-level model outputs from hf_3m_normative_connectome_fiber_model.md
Connected-region atlases for endpoint labels, anatomical enrichment, and STN/SNr overlays
```

E-field rules:

```text
use raw sim-efield or explicitly accepted e-field-like exposure maps
record units as V/m
record frequency, pulse width, amplitude, contacts, side, phase, and component labels
missing or multiply matched e-fields fail the endpoint/run
subjects are not silently excluded
missing e-fields are not automatically created by this model
```

Component-specific proxy fields are allowed only if the manifest records the proxy status:

```text
component_field_type:
  true_component_separable
  interleaved_proxy
  synchronous_mixed_proxy
  ambiguous_component_assignment
```

If a majority of cases use proxy fields, interpretation must use:

```text
ULF-component proxy exposure association
```

rather than:

```text
direct ULF biophysical field association
```

---


## 4. Locked HF Adjustment Source And Intended Branch Role

The ULF normative fiber implementation is a three-layer resolver:

```text
1. HF-derived intended branch role
2. branch-specific ULF source resolver with tau/Coverage scan
3. endpoint primary realization
```

The first layer does not use ULF tau or Coverage. It reads the matched HF normative fiber resolver fields to decide the intended primary branch, and then checks branch-specific `DeltaHFScore` input readiness to decide whether the DeltaHF-adjusted branch can be attempted. The complete ULF normative fiber model is not defined until the intended branch has completed its own ULF tau/Coverage source resolver.

Pre-specified locked HF source:

```text
model_family = hf_3m_normative_connectome_fiber_model
connectome = connectome-matched
branch = peak_efield_tau800_cov5_primary
tau = 800 V/m
coverage = Coverage>=5
estimator = partial_spearman
score = NetFiberScore
F_valid = coverage-passing fibers intersect finite HF weights
K+ = min(N+, max(ceil(0.01 * N+), 200))
K- = min(N-, max(ceil(0.005 * N-), 100))
H+ = min(K+, max(ceil(0.05 * K+), 20))
H- = min(K-, max(ceil(0.05 * K-), 20))
SweetPeak5/SourPeak5 = compatibility fields computed from H+/H-
map source in LOOCV = training-fold HF model
full-sample HF model = descriptive scores only
```

Allowed scan-fallback HF source:

```text
model_family = hf_3m_normative_connectome_fiber_model
branch = tau_coverage_source_resolver_selected_candidate
tau = selected_tau_v_per_m
coverage = selected_coverage
hf_norm_fiber_source_status = scan_fallback_accepted
```

A scan-fallback HF source may define the model-family-matched `DeltaHFScore` source when tau800/Coverage>=5 is not accepted. The manifest must record `hf_norm_fiber_threshold_source = scan_fallback`, selected tau/Coverage, and adjacent support.

Connectome-matched rule:

```text
ULF/PPMI uses HF/PPMI DeltaHFScore
ULF/MGH  uses HF/MGH  DeltaHFScore
ULF/dTOR uses HF/dTOR DeltaHFScore
```

A shared dTOR-HF adjustment across all ULF connectomes may be reported only as a sensitivity:

```text
shared_dTOR_HF_adjustment_sensitivity
```

Required HF source fields:

```text
hf_norm_fiber_source_status
hf_norm_fiber_prediction_status
hf_norm_fiber_source_failure_reasons
hf_norm_fiber_burden_dominated
hf_norm_fiber_threshold_source
hf_norm_fiber_selected_tau_v_per_m
hf_norm_fiber_selected_coverage
hf_norm_fiber_selected_adjacent_passing_grid_cells
hf_norm_fiber_selected_grid_distance_from_pre_specified
delta_hfscore_allowed_role
```

HF-derived intended branch role:

```text
if hf_norm_fiber_source_status = pre_specified_accepted or scan_fallback_accepted:
  run no_delta_hf
  run delta_hf_adjusted only if fold-specific DeltaHFScore inputs are valid

if hf_norm_fiber_prediction_status = error_predictive:
  intended_primary_branch = delta_hf_adjusted
  ulf_primary_branch = delta_hf_adjusted
  delta_hfscore_role = primary_error_predictive_hf_adjustment
  no_delta_hf_role   = sensitivity

if hf_norm_fiber_prediction_status = error_nonpredictive:
  intended_primary_branch = no_delta_hf
  ulf_primary_branch = no_delta_hf
  delta_hfscore_role = stable_error_nonpredictive_hf_adjustment_sensitivity
  no_delta_hf_role   = primary

if hf_norm_fiber_source_status = absent_no_stable_grid:
  run no_delta_hf only
  intended_primary_branch = no_delta_hf
  ulf_primary_branch = no_delta_hf
  delta_hfscore_role = not_run_no_stable_hf_norm_fiber_source

if hf_norm_fiber_prediction_status = error_predictive
and fold-specific DeltaHFScore inputs are invalid:
  intended_primary_branch = delta_hf_adjusted
  ulf_primary_branch = delta_hf_adjusted
  delta_hfscore_role = primary_input_failure
  no_delta_hf_role   = fallback_final_if_accepted_source
```

The ULF implementation runs both core branches when inputs permit:

```text
ulf_peak_efield_tau800_cov5_delta_hf_adjusted
ulf_peak_efield_tau800_cov5_no_delta_hf
```

When `intended_primary_branch = delta_hf_adjusted` but `DeltaHFScore` inputs are invalid, the HF-derived primary branch is not executable. The endpoint primary status remains `primary_branch_input_failure`; if `no_delta_hf` has an accepted ULF source, it becomes the endpoint's fallback final model. The same one-way fallback applies when intended adjusted is evaluable but its source resolver returns `absent_no_stable_grid`. Intended no-delta failure never promotes adjusted, and technical execution failure never triggers fallback.

Required branch-role manifest fields:

```text
hf_norm_fiber_source_status
hf_norm_fiber_prediction_status
hf_norm_fiber_burden_dominated
hf_norm_fiber_threshold_source
hf_norm_fiber_selected_tau_v_per_m
hf_norm_fiber_selected_coverage
hf_norm_fiber_selected_adjacent_passing_grid_cells
intended_primary_branch
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

If the matched HF resolver returns `absent_no_stable_grid`, the DeltaHF-adjusted branch is not run for that endpoint and `no_delta_hf` is the intended primary branch. If the HF-derived intended primary branch is `delta_hf_adjusted` but accepted HF support cannot provide valid fold-specific `DeltaHFScore`, do not relabel `no_delta_hf` as the HF-derived primary branch; record `ulf_norm_fiber_endpoint_model_status = primary_branch_input_failure` and, if `no_delta_hf` has an accepted ULF source, set `ulf_final_model_branch = no_delta_hf` and `ulf_final_model_role = fallback_final`. The same final-role assignment applies if intended adjusted has `absent_no_stable_grid` and no-delta has an accepted source.

## 5. Feature Construction

The executable feature space is a right-canonical streamline feature space. Left-sided stimulation is flipped into the right canonical space with `ea_flip_lr_nonlinear` and sampled along the same right-sided streamline features.

For patient `i` and right-canonical streamline `l`:

```text
E_HF_R_i(l)       = peak HF-component exposure along right canonical fiber l
E_HF_L_to_R_i(l)  = peak left HF-component exposure after nonlinear L-to-R flip
E_ULF_R_i(l)      = peak ULF-component exposure along right canonical fiber l
E_ULF_L_to_R_i(l) = peak left ULF-component exposure after nonlinear L-to-R flip

X_HF_component_i(l)  = (E_HF_R_i(l)  + E_HF_L_to_R_i(l))  / 2
X_ULF_component_i(l) = (E_ULF_R_i(l) + E_ULF_L_to_R_i(l)) / 2
```

HF-only reference exposure for `DeltaHFScore`:

```text
E_HFonly_ref_R_i(l)      = peak HF-only reference exposure along right canonical fiber l
E_HFonly_ref_L_to_R_i(l) = peak left HF-only reference exposure after nonlinear L-to-R flip

X_HFonly_ref_i(l) =
  (E_HFonly_ref_R_i(l) + E_HFonly_ref_L_to_R_i(l)) / 2
```

Same-side same-frequency alternating subprograms:

```text
primary rule:
  combine same-side same-frequency subprogram e-fields by voxel-wise maximum
  before streamline sampling

allowed optimization:
  streamline-wise maximum only if exact-equivalence testing proves equality
  against voxel-wise maximum on a deterministic subset
```

Exposure is not scaled by frequency or pulse width in the peak E-field branch. Frequency classifies the component as HF or ULF; pulse width and frequency are recorded in provenance.

---


## 6. ULF-Only Exposure And Candidate Fibers

ULF-only exposure is tau-specific because tau defines ULF component activity, ULF-only zeroing, ULF coverage, and ULF QC. HF component activity for HF-overlap exclusion is not defined by the ULF source tau.

Pre-specified ULF source:

```text
tau_primary = 800 V/m
coverage_primary = Coverage>=5
```

Predeclared single high-threshold sensitivity:

```text
tau_sensitivity = 1500 V/m
coverage_sensitivity = Coverage>=5
```

ULF source resolver scan:

```text
ulf_threshold_scan_tau_grid_v_per_m = [400, 600, 800, 1000, 1200, 1500, 2000]
ulf_threshold_scan_coverage_grid    = [5, 6, 7, 8, 10, 12]
```

For each ULF source tau:

```text
tau_ULF_source =
  current ULF source-grid tau

tau_HF_overlap =
  hf_norm_fiber_selected_tau_v_per_m,
    if hf_norm_fiber_source_status is pre_specified_accepted or scan_fallback_accepted
  +Inf,
    if hf_norm_fiber_source_status is absent_no_stable_grid

ULF_touched_i(l,tau_ULF_source) =
  X_ULF_component_i(l) > tau_ULF_source

HF_touched_i(l) =
  X_HF_component_i(l) > tau_HF_overlap

X_ULF_only_i(l,tau_ULF_source) =
  X_ULF_component_i(l), if ULF_touched_i(l,tau_ULF_source) and not HF_touched_i(l)
  0,                   otherwise
```

If an HF source exists, HF-overlap exclusion uses the locked HF selected tau so every HF-component decision in the ULF model is aligned with the HF normative fiber source used to compute `DeltaHFScore`. If no HF source exists, `tau_HF_overlap = +Inf`, no HF-overlap streamlines are excluded, and ULF-only exposure equals ULF exposure after ULF thresholding.

Candidate rule:

```text
Coverage_ULF_tau(l) = sum_i I[X_ULF_only_i(l,tau) > tau]
F_candidate_ULF_tau_cov = {l: Coverage_ULF_tau(l) >= coverage_min}
```

The candidate universe is the full public connectome, not target-restricted seed-target tracts.

Important interpretation rule:

```text
For ULF, tau is part of the biological exposure definition.
It is not merely a candidate coverage threshold.
```

Therefore a scan-fallback ULF source is interpreted as:

```text
branch-specific selected ULF source
```

not as:

```text
HF-derived branch-role replacement
```

The ULF source resolver scan is run independently for every executable branch. `delta_hf_adjusted` and `no_delta_hf` may select different tau/Coverage sources because their nuisance designs differ.

## 7. DeltaHFScore: Matched HF Normative Fiber Score Projection

`DeltaHFScore` is a generated nuisance covariate derived from the locked HF normative fiber model.

For each LOOCV training fold, define the training-fold HF score operator:

```text
O_HF_fold = {
  M_HF_fold(l),
  F+_HF_fold,
  F-_HF_fold,
  K+/K- and H+/H- score rules,
  NetFiberScore rule
}
```

For any HF exposure matrix `E`, define:

```text
S_HF_norm_fiber(E; O_HF_fold)_i = NetFiberScore_i obtained by applying
                                  the locked training-fold HF operator
                                  to exposure E for patient i
```

Explicitly:

```text
SweetWeighted_HF_i(l) = X_E_i(l) * M_HF_fold(l),       l in F+_HF_fold
SourWeighted_HF_i(l)  = X_E_i(l) * [-M_HF_fold(l)],    l in F-_HF_fold

SweetPeak5_HF_i = mean of the H+ largest SweetWeighted_HF_i(l)
SourPeak5_HF_i  = mean of the H- largest SourWeighted_HF_i(l)

S_HF_norm_fiber(E; O_HF_fold)_i = SweetPeak5_HF_i - SourPeak5_HF_i
```

Then:

```text
DeltaHFScore_chronic_i =
  S_HF_norm_fiber(E_HF_component_T3_HFplusULF; O_HF_fold)_i
  - S_HF_norm_fiber(E_HFonly_ref_T2; O_HF_fold)_i

DeltaHFScore_immediate_i =
  S_HF_norm_fiber(E_HF_component_T2_HFplusULF_immediate; O_HF_fold)_i
  - S_HF_norm_fiber(E_HFonly_ref_T2; O_HF_fold)_i
```

Rules:

```text
Do not refit the HF model using HF+ULF outcomes.
Do not refit the HF model using HF+ULF exposure as the HF training exposure.
Do not use full-sample HF M_HF, F+, or F- to score held-out patients in LOOCV.
Do not replace the HF normative score with a direct voxel HF score.
Do not replace the connectome-matched HF score with another connectome unless running an explicitly labeled sensitivity.
```

`DeltaHFScore` may be z-scored inside each training fold for numerical stability. The z-scoring parameters are learned on training patients only and applied to the held-out patient. No fixed biological scaling coefficient is imposed before regression.

---


## 8. DeltaHFScore Support And Out-Of-Support HF Exposure

### 8.1 Support definitions

The matched HF 3-month model has a finite learned support determined by its source branch.

For each HF training fold:

```text
F_HF_candidate_fold =
  candidate fibers satisfying source tau and source Coverage in the HF training fold

F_HF_valid_fold =
  F_HF_candidate_fold intersect fibers with finite non-degenerate M_HF_fold(l)

F_HF_score_fold =
  F+_HF_fold union F-_HF_fold
```

Source threshold metadata are explicit:

```text
hf_source_tau_v_per_m
hf_source_coverage
hf_source_threshold_source = pre_specified | scan_fallback
hf_source_status
hf_source_prediction_status
```

`DeltaHFScore` is calculated only through the locked HF scoring operator:

```text
F_HF_score_fold = F+_HF_fold union F-_HF_fold
```

Fibers outside `F_HF_score_fold` do not contribute to `DeltaHFScore`. This means "outside the locked HF NetFiberScore operator," not "biologically no HF effect."

### 8.2 If HF+ULF HF-component exposure touches fibers outside HF support

If `E_HF_component` during HF+ULF touches fibers outside the HF 3-month model's coverage or score support:

```text
Do not extrapolate M_HF to those fibers.
Do not smooth weights onto those fibers.
Do not assign nearest-neighbor HF weights.
Do not add those fibers into F+ or F-.
Do not retrain the HF model using HF+ULF exposure or outcome.
```

The primary `DeltaHFScore` remains an in-support projection:

```text
DeltaHFScore_in_support =
  S_HF_norm_fiber(E_HF_component; O_HF_fold)
  - S_HF_norm_fiber(E_HFonly_ref; O_HF_fold)
```

where `S_HF_norm_fiber` uses only `F_HF_score_fold` from the locked HF source.

### 8.3 Required support QC metrics

For each subject, endpoint, connectome, ULF branch, HF source branch, and LOOCV fold, compute support QC using the HF source tau:

```text
HF_component_total_touched_count_source_tau
HF_component_total_exposure_sum_source_tau
HF_component_total_exposure_top5_source_tau

HF_component_in_HF_candidate_count_source_tau
HF_component_in_HF_candidate_sum_source_tau
HF_component_in_HF_candidate_top5_source_tau

HF_component_in_HF_valid_count_source_tau
HF_component_in_HF_valid_sum_source_tau
HF_component_in_HF_valid_top5_source_tau

HF_component_in_HF_selected_count_source_tau
HF_component_in_HF_selected_sum_source_tau
HF_component_in_HF_selected_top5_source_tau

HF_component_out_HF_candidate_count_source_tau
HF_component_out_HF_candidate_sum_source_tau
HF_component_out_HF_candidate_top5_source_tau

HF_component_out_HF_selected_count_source_tau
HF_component_out_HF_selected_sum_source_tau
HF_component_out_HF_selected_top5_source_tau

HF_out_candidate_fraction_source_tau =
  HF_component_out_HF_candidate_sum_source_tau
  / HF_component_total_exposure_sum_source_tau

HF_out_selected_fraction_source_tau =
  HF_component_out_HF_selected_sum_source_tau
  / HF_component_total_exposure_sum_source_tau
```

If `HF_component_total_touched_count_source_tau = 0` or `HF_component_total_exposure_sum_source_tau <= 0` for any required subject or fold, set:

```text
delta_hfscore_support_status = invalid_no_hfcomponent_exposure
```

Do not compute support fractions by adding an epsilon denominator in that case, and do not classify the branch as `adequate`.

Write:

```text
normative_ULF_fiber_delta_hf_support_summary.csv
normative_ULF_fiber_delta_hf_support_qc.json
normative_ULF_fiber_sensitivity_readiness_status.json
```

For backward compatibility, tau800-specific aliases may be emitted when the selected HF source is tau800/Coverage>=5:

```text
HF_out_candidate_fraction_tau800
HF_out_selected_fraction_tau800
```

### 8.4 DeltaHFScore support status for out-of-support exposure

Default support-status thresholds:

```text
delta_hfscore_support_status = adequate
  if cohort median HF_out_candidate_fraction_source_tau <= 0.20
  and no more than 25% of subjects have HF_out_candidate_fraction_source_tau > 0.50

delta_hfscore_support_status = limited
  if support is worse than adequate
  but does not meet invalid_extreme_out_of_support

delta_hfscore_support_status = invalid_extreme_out_of_support
  if cohort median HF_out_candidate_fraction_source_tau > 0.50
  or more than 25% of subjects have HF_out_candidate_fraction_source_tau > 0.80
  or any required subject or LOOCV fold has
     HF_out_candidate_fraction_source_tau > 0.95

delta_hfscore_support_status = invalid_no_hfcomponent_exposure
  if a required subject/fold has no suprathreshold HF-component exposure
  or nonpositive total HF-component exposure under the locked HF source tau
```

`Nearly completely outside` is therefore a fixed numeric rule (`> 0.95`), not
a qualitative reviewer judgment.
The comparison is strict: a value equal to `0.95` does not satisfy this extreme
subject/fold criterion.

Interpretation:

```text
adequate:
  DeltaHFScore inputs are valid without support downgrade.

limited:
  DeltaHFScore inputs remain valid, but the branch must report the support limitation.

invalid_extreme_out_of_support:
  DeltaHFScore inputs are invalid for the DeltaHF-adjusted branch.
  If the DeltaHF-adjusted branch is the intended primary branch,
  record ulf_norm_fiber_endpoint_model_status = primary_branch_input_failure.

invalid_no_hfcomponent_exposure:
  DeltaHFScore inputs are invalid because the HF-component projection
  cannot be interpreted for at least one required subject/fold.
  If the DeltaHF-adjusted branch is the intended primary branch,
  record ulf_norm_fiber_endpoint_model_status = primary_branch_input_failure.
```

If out-of-support exposure is substantial, add a QC-only or secondary sensitivity model:

```text
Y_post ~ NetULFFiberScore
       + Y_HF_ref
       + DeltaHFScore_in_support
       + PlainHFOutSupportTop5
```

Do not force this variable into the main model if it is highly collinear with `NetULFFiberScore`, `DeltaHFScore`, or `Y_HF_ref`. With `n=16`, it is primarily diagnostic.

### 8.5 Fibers inside HF candidate support but outside HF selected score support

If a fiber is inside `F_HF_candidate_fold` or `F_HF_valid_fold` but not in `F_HF_score_fold`, it is within the learned HF model universe but outside the HF NetFiberScore operator. It does not contribute to `DeltaHFScore` because the locked HF scoring model did not select it.

This is not a technical failure. Report it as:

```text
in-candidate / non-selected HF-component exposure
```

not as out-of-coverage exposure.

### 8.6 Fibers absent from the public connectome

If an anatomical pathway is not represented by the public connectome, it cannot be scored in either HF or ULF normative models. This is a connectome limitation, not evidence that the pathway is irrelevant.

Report as:

```text
not represented in the normative connectome feature space
```

No imputation is allowed.


## 9. Core Statistical Models

The ULF normative fiber implementation runs executable core branches when inputs permit. Their intended roles are assigned by the HF-derived intended branch-role resolver, and their realized source status is assigned by the branch-specific ULF tau/Coverage source resolver.

### 9.0 Core Branch A: DeltaHF-Adjusted Partial Spearman

The DeltaHF-adjusted fiber-level estimator is nuisance-adjusted partial Spearman.

For each endpoint and candidate fiber `l`:

```text
rho_ULF_deltaHF(l) =
  corr(
    resid(rank(Y_post_i)            ~ rank(Y_HF_ref_i) + rank(DeltaHFScore_i)),
    resid(rank(X_ULF_only_i(l,tau)) ~ rank(Y_HF_ref_i) + rank(DeltaHFScore_i))
  )
```

Ties use average ranks. Degenerate fibers with zero ULF-only exposure variance, zero rank variance, or zero residualized exposure variance are assigned:

```text
rho_ULF_deltaHF(l) = NaN
```

and excluded from selected-fiber sets and scoring.

Benefit-oriented fiber weight:

```text
M_ULF_deltaHF(l) = -rho_ULF_deltaHF(l)   for lower-is-better scales
M_ULF_deltaHF(l) =  rho_ULF_deltaHF(l)   for higher-is-better scales
```

### 9.1 Core Branch B: No-DeltaHF Partial Spearman

The no-DeltaHF estimator removes the model-generated HF score but keeps the observed pre-ULF HF clinical state:

```text
rho_ULF_noDeltaHF(l) =
  corr(
    resid(rank(Y_post_i)            ~ rank(Y_HF_ref_i)),
    resid(rank(X_ULF_only_i(l,tau)) ~ rank(Y_HF_ref_i))
  )
```

Benefit-oriented fiber weight:

```text
M_ULF_noDeltaHF(l) = -rho_ULF_noDeltaHF(l)   for lower-is-better scales
M_ULF_noDeltaHF(l) =  rho_ULF_noDeltaHF(l)   for higher-is-better scales
```

This branch is the intended primary branch when the matched HF normative fiber source is absent or `error_nonpredictive`. It also becomes the fallback final model when intended DeltaHF-adjusted has input/design failure or `absent_no_stable_grid` and `no_delta_hf` has an accepted ULF source.

### 9.2 Patient-level NetULFFiberScore

Within each full-sample map or LOOCV training fold:

```text
F_valid_ULF = branch candidate fibers intersect finite branch weights
K+ = min(N+, max(ceil(0.01 * N+), 200))
K- = min(N-, max(ceil(0.005 * N-), 100))
F+_ULF = K+ largest positive weights, tie-broken by canonical fiber id
F-_ULF = K- most negative weights, tie-broken by canonical fiber id
```

For each patient:

```text
SweetWeighted_ULF_i(l) = X_ULF_only_i(l,tau) * M_ULF(l),      l in F+_ULF
SourWeighted_ULF_i(l)  = X_ULF_only_i(l,tau) * [-M_ULF(l)],   l in F-_ULF

H+ = min(K+, max(ceil(0.05 * K+), 20))
H- = min(K-, max(ceil(0.05 * K-), 20))
SweetPeak5_ULF_i = mean of the H+ largest SweetWeighted_ULF_i(l)
SourPeak5_ULF_i  = mean of the H- largest SourWeighted_ULF_i(l)

NetULFFiberScore_i = SweetPeak5_ULF_i - SourPeak5_ULF_i
```

`M_ULF(l)` is branch-specific:

```text
delta_hf_adjusted branch uses M_ULF_deltaHF(l)
no_delta_hf branch uses M_ULF_noDeltaHF(l)
```

Selection and edge cases:

```text
F+ and F- are selected within F_candidate_ULF_tau_cov intersect finite weights
NaN or degenerate fibers are excluded
outer counts use the fixed 1%/0.5% fractions with 200/100 minima
patient peak counts use the fixed 5% fraction with minimum 20 per nonempty side
empty F+ gives SweetPeak5 = 0
empty F- gives SourPeak5 = 0
if a selected set is non-empty but a patient has zero exposure to all selected fibers, that peak component is 0
```

`SweetPeak5` and `SourPeak5` remain compatibility output names; they do not
mean an unconstrained 5% score. Full sample and every fold record
`adequate_two_sign`, `limited_two_sign`, `limited_positive_only`,
`limited_negative_only`, or `absent_no_valid_signed_fibers`, plus requested and
actual K/H counts, minimum-dominated flags, and selected-ID hashes. These
support labels do not alter branch source, prediction, endpoint, or final role.

### 9.3 Final prediction models

DeltaHF-adjusted prediction model:

```text
Y_post_i = alpha
         + delta * NetULFFiberScore_deltaHF_i
         + beta  * Y_HF_ref_i
         + gamma * DeltaHFScore_i
         + error_i
```

DeltaHF-adjusted nuisance-only baseline:

```text
Y_post_i = alpha
         + beta  * Y_HF_ref_i
         + gamma * DeltaHFScore_i
         + error_i
```

No-DeltaHF prediction model:

```text
Y_post_i = alpha
         + delta * NetULFFiberScore_noDeltaHF_i
         + beta  * Y_HF_ref_i
         + error_i
```

No-DeltaHF nuisance-only baseline:

```text
Y_post_i = alpha
         + beta * Y_HF_ref_i
         + error_i
```

Primary validation statistic for the final model:

```text
LOOCV Spearman rho between held-out predicted Y_post and held-out observed Y_post
```

Secondary metrics:

```text
LOOCV Pearson r
MAE
RMSE
Q2 relative to branch-specific nuisance-only baseline
```

```text
Q2 = 1 - SSE_ULFScore_model / SSE_branch_specific_nuisance_only_baseline
```

Missing-data rule: missing `Y_post`, missing `Y_HF_ref`, or failed e-field availability fails the endpoint/run after QC. Missing or invalid `DeltaHFScore` fails only the DeltaHF-adjusted branch; the no-DeltaHF branch may still run and must record why the adjusted branch was unavailable. For configurable future endpoints, the endpoint is skipped if the valid sample size falls below 12.

### 9.4 ULF Normative Fiber Source And Endpoint Resolver

The HF-derived intended branch role decides which branches are attempted and which branch is intended primary. The branch-specific ULF source resolver then evaluates each executable branch independently. Each branch may select a different tau/Coverage source because `delta_hf_adjusted` and `no_delta_hf` have different nuisance designs and may produce different valid ULF scoring supports. ULF source or prediction status must not change the HF-derived intended primary branch; it determines whether that intended branch is realized as a stable ULF model or whether the endpoint is reported as input-failed, absent, predictive, or nonpredictive.

The hard computability filter for each executable endpoint, phase, branch, and tau/Coverage grid cell is:

```text
n_subjects >= 12
fold_n_candidate_fibers_min >= 1000 for dTOR
fold_n_candidate_fibers_min >= 100 for PPMI/MGH observed robustness
selected fiber pools are computable
NetULFFiberScore is non-constant in every LOOCV fold
branch nuisance design is valid
all held-out predictions are finite
```

Branch input/design failure has priority over `absent_no_stable_grid`. If a branch cannot evaluate the declared grid because branch-specific clinical inputs, e-field inputs, `DeltaHFScore` inputs, or the branch nuisance design are invalid, record `ulf_norm_fiber_endpoint_model_status = primary_branch_input_failure` when that branch is primary. Do not reclassify this condition as `absent_no_stable_grid`.

This priority rule applies before assigning `ulf_norm_fiber_source_status`: `absent_no_stable_grid` means the declared grid was evaluable but no stable source was found.

The pre-specified ULF source is:

```text
tau = 800 V/m
Coverage >= 5
estimator = branch-specific partial Spearman
score = NetULFFiberScore
validation = LOOCV
```

If the pre-specified source is not accepted, the fallback source must be selected only from the declared ULF tau/Coverage scan grid:

```text
tau, V/m:
  400, 600, 800, 1000, 1200, 1500, 2000

Coverage:
  5, 6, 7, 8, 10, 12
```

Define ULF normative fiber source status for every executable endpoint, phase, and branch:

```text
ulf_norm_fiber_source_status = pre_specified_accepted
  if the pre-specified tau800/Coverage>=5 grid cell passes the hard computability filter
  and at least 2 adjacent tau/Coverage grid cells also pass the hard computability filter

ulf_norm_fiber_source_status = scan_fallback_accepted
  if tau800/Coverage>=5 does not pass the source-stability rule
  and a predeclared ULF source scan contains another grid cell passing the same rule

ulf_norm_fiber_source_status = absent_no_stable_grid
  if no evaluated tau/Coverage grid cell passes the source-stability rule
```

For `scan_fallback_accepted`, choose the fallback grid without using `Q2`, rho, nominal p value, MAE, or RMSE:

```text
1. minimize grid distance from tau800/Coverage>=5
2. maximize adjacent passing grid cells
3. maximize fold_n_candidate_fibers_min
4. prefer stricter Coverage
5. prefer higher tau
```

Define ULF normative fiber prediction status only after a branch-specific source exists:

```text
ulf_norm_fiber_prediction_status = error_predictive
  if MAE_model < MAE_branch_specific_nuisance_only_baseline
  and RMSE_model < RMSE_branch_specific_nuisance_only_baseline

ulf_norm_fiber_prediction_status = error_nonpredictive
  if a ULF normative fiber source exists
  but MAE_model >= MAE_branch_specific_nuisance_only_baseline
  or RMSE_model >= RMSE_branch_specific_nuisance_only_baseline

ulf_norm_fiber_prediction_status = not_applicable
  if ulf_norm_fiber_source_status = absent_no_stable_grid
```

Endpoint primary realization combines the HF-derived intended primary branch with that branch's own ULF source resolver result:

```text
ulf_norm_fiber_endpoint_model_status = primary_branch_error_predictive
  if the intended primary branch has ulf_norm_fiber_source_status in
  {pre_specified_accepted, scan_fallback_accepted}
  and the intended primary branch has ulf_norm_fiber_prediction_status = error_predictive

ulf_norm_fiber_endpoint_model_status = primary_branch_error_nonpredictive
  if the intended primary branch has an accepted ULF source
  but the intended primary branch has ulf_norm_fiber_prediction_status = error_nonpredictive

ulf_norm_fiber_endpoint_model_status = absent_no_stable_ulf_grid
  if the intended primary branch is executable
  but has ulf_norm_fiber_source_status = absent_no_stable_grid

ulf_norm_fiber_endpoint_model_status = primary_branch_input_failure
  if the intended primary branch cannot be evaluated because required clinical,
  e-field, DeltaHFScore, or nuisance-design inputs are invalid
```

Final-model status is assigned after endpoint primary realization. Fallback is one-way: if intended `delta_hf_adjusted` has input/design failure or `absent_no_stable_grid`, accepted `no_delta_hf` becomes the fallback final model. Intended no-delta failure never promotes adjusted, and technical execution failure never triggers fallback:

```text
if ulf_norm_fiber_endpoint_model_status in
  {primary_branch_error_predictive, primary_branch_error_nonpredictive}:
    ulf_final_model_branch = intended_primary_branch
    ulf_final_model_role = primary

ulf_final_model_branch = no_delta_hf
ulf_final_model_role = fallback_final
  if intended_primary_branch = delta_hf_adjusted
  and ulf_norm_fiber_endpoint_model_status in
    {primary_branch_input_failure, absent_no_stable_ulf_grid}
  and no_delta_hf has an accepted ULF source

ulf_final_model_branch = none
ulf_final_model_role = no_final_model
  if the intended primary branch has no accepted source
  and no permitted no_delta_hf fallback has an accepted source
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

The final ULF normative fiber model is unique for each endpoint. Non-final branch outputs can be retained as sensitivity/comparison outputs, but formal permutation, bootstrap, jitter, and OSS attach to `ulf_final_model_branch`:

```text
ulf_final_model =
  endpoint + phase + ulf_final_model_branch
  + selected_tau + selected_coverage + estimator
```


## 10. Sensitivity Models

### 10.1 Non-selected core branch comparison

Purpose: compare executable non-final core branches against the final model without changing endpoint primary status.

```text
if intended_primary_branch = delta_hf_adjusted
and delta_hf_adjusted has an accepted ULF source:
  comparison branch = no_delta_hf

if intended_primary_branch = no_delta_hf
and no_delta_hf has an accepted ULF source:
  comparison branch = delta_hf_adjusted, if DeltaHFScore inputs are valid

if intended_primary_branch = delta_hf_adjusted
and ulf_norm_fiber_endpoint_model_status in
  {primary_branch_input_failure, absent_no_stable_ulf_grid}
and no_delta_hf has an accepted ULF source:
  no_delta_hf is the fallback final model
```

No-DeltaHF branch name:

```text
ulf_peak_efield_tau800_cov5_no_delta_hf
```

DeltaHF-adjusted branch name:

```text
ulf_peak_efield_tau800_cov5_delta_hf_adjusted
```

The non-final core branch receives observed LOOCV outputs but does not receive formal `B=10000` resampling unless explicitly promoted.

### 10.2 HF Source-Neighborhood DeltaHFScore Sensitivity

If the HF source resolver records neighboring stable tau/Coverage cells around the selected HF source, one explicitly labeled source-neighborhood DeltaHFScore sensitivity may be reported:

```text
ulf_peak_efield_tau800_cov5_delta_hf_from_hf_neighbor_tau{tau}_cov{coverage}_sensitivity
```

Rules:

```text
at most one neighboring HF source sensitivity per endpoint/scale
neighboring threshold cells are robustness evidence only
no multiple DeltaHFScore_tau*_cov* covariates in the same n=16 ULF model
the locked HF source remains the one selected by the HF source resolver
```

### 10.3 ULF Tau/Coverage Source Resolver Scan

Purpose: first evaluate the pre-specified tau800/Coverage>=5 ULF source for each executable branch; if it is not accepted, select a predeclared fallback tau/Coverage source using outcome-independent stability criteria.

Executable grid:

```text
ulf_threshold_scan_tau_grid_v_per_m = [400, 600, 800, 1000, 1200, 1500, 2000]
ulf_threshold_scan_coverage_grid    = [5, 6, 7, 8, 10, 12]
```

Run the scan independently for every executable branch. `delta_hf_adjusted` and `no_delta_hf` may select different tau/Coverage sources because their nuisance designs differ.

Each grid cell reruns:

```text
ULF_touched / HF_touched
HF-overlap exclusion
X_ULF_only
Coverage_ULF_tau_cov
F_candidate_ULF_tau_cov
rho_ULF
M_ULF
F+_ULF / F-_ULF
NetULFFiberScore
branch-specific prediction model
branch-specific nuisance-only baseline
LOOCV metrics
```

Source resolver:

```text
pre_specified_accepted:
  tau800/Coverage>=5 passes the hard computability filter
  and at least 2 adjacent tau/Coverage cells also pass

scan_fallback_accepted:
  tau800/Coverage>=5 is not accepted
  and at least one scan cell passes the same source-stability rule

absent_no_stable_grid:
  no evaluated tau/Coverage cell passes the source-stability rule
```

For `scan_fallback_accepted`, choose the fallback cell without using `Q2`, rho, nominal p value, MAE, or RMSE:

```text
1. minimize grid distance from tau800/Coverage>=5
2. maximize adjacent passing grid cells
3. maximize fold_n_candidate_fibers_min
4. prefer stricter Coverage
5. prefer higher tau
```

If the selected ULF source is described as threshold-scan significant, use max-stat permutation over the full ULF tau/Coverage grid. If threshold selection itself is part of a predictive algorithm claim, use nested/adaptive LOOCV or independent validation. These analyses do not replace the source resolver.

### 10.4 Total ULF exposure sensitivity

Purpose: test whether hard HF-overlap exclusion removes biologically relevant ULF effects.

Exposure:

```text
X_ULF_total_i(l) = X_ULF_component_i(l)
```

No HF-overlap exclusion is applied. The nuisance adjustment follows the branch-role resolver:

```text
if delta_hf_adjusted is selected or being tested:
  Y_post ~ NetULFFiberScore_total + Y_HF_ref + DeltaHFScore

if no_delta_hf is selected or being tested:
  Y_post ~ NetULFFiberScore_total + Y_HF_ref
```

Branch name:

```text
ulf_total_exposure_tau800_cov5_sensitivity
```

This branch is not primary. If total ULF exposure is positive but ULF-only exposure is negative or null, interpretation should state that the hard-exclusion definition may have removed co-modulated ULF effects.

### 10.5 Tau1500 ULF-only exposure-definition sensitivity

Branch:

```text
ulf_peak_efield_tau1500_cov5_sensitivity
```

This is not merely a high-threshold robustness check. It changes ULF touched status, HF touched status, HF-overlap exclusion, `X_ULF_only`, candidate fibers, and patient scores.

### 10.6 Top1500/top500 selected-fiber sensitivity

Branch:

```text
ulf_top1500_top500_sensitivity
```

Use fixed selected-fiber counts:

```text
top 1500 positive fibers
top 500 negative/sour fibers
```

This checks dependence on the percentile selected-fiber rule. Do not combine top-k scanning with tau/Coverage scanning.

### 10.7 Add-on gain endpoint sensitivity

Because the primary model is a raw post-score ANCOVA-style model, add-on gain remains sensitivity. The nuisance set follows the branch-role resolver.

For no-DeltaHF:

```text
Gain_i = alpha + delta * NetULFFiberScore_noDeltaHF_i + error_i
```

For DeltaHF-adjusted:

```text
Gain_i = alpha
       + delta * NetULFFiberScore_deltaHF_i
       + gamma * DeltaHFScore_i
       + error_i
```

### 10.8 Optional OLS ANCOVA

Documented only, not run by default:

```text
Y_post_i ~ X_ULF_only_i(l,tau) + Y_HF_ref_i + DeltaHFScore_i
Y_post_i ~ X_ULF_only_i(l,tau) + Y_HF_ref_i
```

This does not replace the primary partial Spearman estimator.

### 10.9 ULF OSS-DBS activation sensitivity

ULF OSS-DBS activation sensitivity is a planned sensitivity round. It tests whether the realized primary ULF peak-E-field source remains interpretable when the ULF exposure value is replaced by modeled ULF pathway/axon activation.

It does not participate in:

```text
HF-derived branch-role assignment
ULF tau/Coverage source resolver
ulf_norm_fiber_source_status
ulf_norm_fiber_prediction_status
ulf_norm_fiber_endpoint_model_status
DeltaHFScore source definition
```

Candidate inheritance:

```text
oss_candidate_source_branch = ulf_final_model_id
oss_inherited_tau_v_per_m = realized_primary_selected_tau_v_per_m
oss_inherited_coverage = realized_primary_selected_coverage
F_candidate_ULF_OSS = F_candidate_ULF_selected_tau_selected_coverage
```

OSS activation must not redefine candidate fibers and must not participate in tau/Coverage threshold selection.

For each subject and fiber:

```text
A_ULF_OSS_i(l) = pPAM activation probability for the ULF component along fiber l
```

The canonical OSS sidecar is `X_oss_float32_fiber_major.npy`. Its columns are
the realized primary ULF branch selected-source tau/Coverage candidate fiber id
order, not the whole connectome atlas and not a parent raw `fiber_ids.npy` when
that file stores the full exposure universe. OSS does not redefine, shrink,
expand, or rescan candidate fibers. The actual OSS column order is recorded as
`oss_fiber_ids.npy` or an equivalent sidecar manifest field.

OSS activation uses the right-canonical feature space. Right-sided activation
uses the native right geometry. Left electrode/stimulation geometry and
reconstruction coordinates are transformed with `ea_flip_lr_nonlinear`, and
OSS is run directly on the same ordered `final.valid_feature_axis`; native
left/right local fiber-ID equality is never assumed. Left-transformed and
right probabilities are merged by `max_probability_union`, and the
0.5-thresholded binary form is used for fitting:

```text
X_ULF_OSS_probability_i(l) = max(A_ULF_OSS_R_i(l), A_ULF_OSS_L_to_R_i(l))
X_ULF_OSS_i(l) = I[X_ULF_OSS_probability_i(l) >= 0.5]
```

The configured producer runs ten complete OSS samples with Fiber Diameter
sampled equidistantly over `[1, 4]` micrometers. Stored float32 p(A) is exact
`activated_count / 10` on the `0.0, 0.1, ..., 1.0` lattice. Canonical fitting
derives `I[p(A) >= 0.5]` and uses that binary matrix in `M_ULF_OSS`,
`NetULFFiberScore_OSS`, LOOCV, and smoke permutation.

If the ULF component cannot be separated from the stimulation protocol, the output may only be labeled `HF+ULF total OSS pPAM sensitivity`; it must not be called ULF-only OSS exposure.

HF-overlap exclusion remains the same peak-E-field rule used by the realized primary ULF model:

```text
HF_touched_i(l) =
  X_HF_component_i(l) > hf_norm_fiber_selected_tau_v_per_m,
    if matched HF source exists
  false,
    if matched HF source is absent_no_stable_grid
```

The OSS ULF-only exposure is:

```text
X_ULF_only_OSS_i(l) =
  X_ULF_OSS_i(l), if l in F_candidate_ULF_OSS and not HF_touched_i(l)
  0,              otherwise
```

The OSS branch inherits the nuisance design of the realized primary branch.

No-DeltaHF OSS prediction model:

```text
Y_post_i = alpha
         + delta * NetULFFiberScore_OSS_i
         + beta  * Y_HF_ref_i
         + error_i
```

DeltaHF-adjusted OSS prediction model:

```text
Y_post_i = alpha
         + delta * NetULFFiberScore_OSS_i
         + beta  * Y_HF_ref_i
         + gamma * DeltaHFScore_i
         + error_i
```

`DeltaHFScore` remains the matched HF normative fiber score projection. It is not replaced by an HF OSS score.

Within the inherited candidate universe, recompute:

```text
M_ULF_OSS(l)
F+_ULF_OSS and F-_ULF_OSS use the same fold-local K+/K- rule and 200/100 minima
SweetPeak5_ULF_OSS
SourPeak5_ULF_OSS
NetULFFiberScore_OSS
LOOCV predictions
```

Run order:

```text
dTOR realized-primary final branch observed LOOCV
dTOR smoke Freedman-Lane permutation B=1000
```

Default ULF OSS uses smoke `B=1000` only. `B=10000` OSS permutation/bootstrap is not part of the default ULF OSS round and would require a separate model-document revision. The OSS result is activation-model robustness evidence only.

Required OSS manifest fields:

```text
ulf_oss_sensitivity_status
oss_model_set
axon_model
axon_diameter_um
n_nodes
waveform
ULF_frequency_Hz
pulse_width_us
amplitude
tissue_model
conductivity_model
activation_output_type
oss_candidate_source_branch
oss_inherited_tau_v_per_m
oss_inherited_coverage
oss_hf_overlap_tau_source
branch_role
delta_hfscore_role
```

Allowed `ulf_oss_sensitivity_status` values:

```text
not_run_no_formal_realized_primary
not_run_missing_oss_inputs
passed_activation_consistent
passed_activation_model_dependent
failed_activation_degenerate
failed_oss_design_or_prediction
```


## 11. Validation

Use fully nested leave-one-patient-out cross-validation for each executed branch.

For each connectome, endpoint, scale, branch, tau, coverage, and held-out patient `h`:

```text
train = all patients except h
test  = patient h
```

Within each training fold:

```text
1. Read the matched HF normative source status and source threshold metadata.
2. If the branch uses DeltaHFScore, fit or retrieve the matched training-fold HF normative fiber model and compute fold-specific DeltaHFScore for training patients and the held-out patient.
3. Compute fold-specific X_ULF_only_i(l,tau) using the branch tau.
4. Define F_candidate_ULF_tau_cov using training-patient Coverage_ULF_tau(l) >= coverage_min.
5. Estimate branch-specific rho_ULF(l) and M_ULF(l) using training patients only.
6. Select fold-specific F+_ULF and F-_ULF.
7. Compute branch-specific NetULFFiberScore for training patients and the held-out patient.
8. Fit the branch-specific prediction model on training patients.
9. Predict held-out Y_post.
10. Compare against the branch-specific nuisance-only baseline.
```

For the OSS sensitivity branch, steps 3-7 inherit the realized primary branch's selected-source candidate universe and HF-overlap exclusion rule, replace `X_ULF_only` with `X_ULF_only_OSS`, and recompute `M_ULF_OSS`, `F+_ULF_OSS`, `F-_ULF_OSS`, `SweetPeak5_ULF_OSS`, `SourPeak5_ULF_OSS`, and `NetULFFiberScore_OSS` within the training fold.

Forbidden fold-level operations:

```text
no full-sample ULF candidate mask for LOOCV scoring
no full-sample ranks
no full-sample M_ULF
no full-sample F+_ULF or F-_ULF
no full-sample F+_ULF_OSS or F-_ULF_OSS for OSS branches
no held-out patient in candidate definition
no held-out patient in ULF map fitting
no held-out patient in selected-fiber selection
no held-out patient in final prediction-model fitting
no full-sample HF model for held-out DeltaHFScore
no threshold selected using the held-out patient's outcome in nested/adaptive validation
no OSS activation-defined candidate set
```

Core observed stage:

```text
always run when inputs permit:
  ulf_peak_efield_tau800_cov5_delta_hf_adjusted
  ulf_peak_efield_tau800_cov5_no_delta_hf
```

The branch-role resolver records the intended primary branch before ULF source resolution. Formal resampling follows the final model's accepted source. A separately declared co-primary endpoint may receive its own automatically selected final model, but a sensitivity branch does not replace the final model.


## 12. Permutation, Bootstrap, And Threshold-Scan Inference

### 12.1 Freedman-Lane permutation

Formal permutation is restricted to the dTOR final model's accepted source for each endpoint included in formal reporting.

```text
connectome = dTOR
branch = ulf_final_model_branch at its accepted final source
formal B = 10000
smoke B = 1000
seed = 42
primary statistic = LOOCV Spearman rho
p_plus_one = (1 + count(|stat_perm| >= |stat_obs|)) / (B + 1)
```

Branch-specific nuisance model:

```text
delta_hf_adjusted: Y_post ~ Y_HF_ref + DeltaHFScore
no_delta_hf:       Y_post ~ Y_HF_ref
```

Permutation workflow:

```text
1. Fit branch-specific nuisance model.
2. Permute nuisance residuals.
3. Reconstruct permuted Y*.
4. Rerun full ULF LOOCV workflow:
   - ULF-only exposure definition
   - candidate definition
   - rho_ULF
   - M_ULF
   - F+_ULF / F-_ULF
   - NetULFFiberScore
   - held-out prediction
   - LOOCV statistic
```

`DeltaHFScore` in ULF permutation:

```text
DeltaHFScore is fold-dependent and HF-model-dependent.
It is not dependent on the permuted ULF outcome.
```

Therefore, within a fixed outer fold and fixed HF model cache, `DeltaHFScore` may be reused across ULF outcome permutations. Bootstrap must recompute `DeltaHFScore` when bootstrap subject multiplicity changes the HF model fitting sample.

### 12.2 Subject-level bootstrap

Formal bootstrap is restricted to the dTOR final model's accepted source for each endpoint included in formal reporting.

```text
formal B = 10000
smoke B = 1000
seed = 42
```

Each bootstrap resample must rerun:

```text
matched HF model fitting / DeltaHFScore when used
ULF-only exposure and coverage
F_candidate_ULF_tau_cov
rho_ULF
M_ULF
F+_ULF / F-_ULF
NetULFFiberScore
bootstrap stability summaries
```

If an OSS bootstrap is added by a future model-document revision, rerun OSS activation scoring inside the inherited selected-source candidate universe and recompute `M_ULF_OSS`, `F+_ULF_OSS`, `F-_ULF_OSS`, and `NetULFFiberScore_OSS`. OSS bootstrap is not part of the default ULF OSS round.

Do not store full `B=10000` fiber-weight tables. Use streaming finite-count, selection-frequency, and sign-stability summaries.

### 12.3 Max-stat permutation for threshold scans

If a selected ULF or HF-derived threshold-scan branch is described as significant, single-cell nominal p values are insufficient.

For max-stat permutation:

```text
for each permutation:
  rerun the entire tau x Coverage grid for the same branch family
  record the maximum selected statistic over eligible grid cells

observed_max = maximum observed statistic over eligible grid cells
p_max = plus-one probability(permuted_max >= observed_max)
```

Recommended statistics:

```text
primary = Q2 or LOOCV Spearman rho, predeclared before scan-level inference
secondary = MAE/RMSE improvement over branch-specific nuisance baseline
```

### 12.4 Nested/adaptive validation for threshold-selected models

If threshold selection is part of the model to be carried forward, validate the whole adaptive algorithm:

```text
outer LOOCV:
  leave one patient out

inner training set:
  scan tau/Coverage
  select threshold using predeclared rule
  train ULF map and score model

outer held-out patient:
  score with the inner-selected threshold and map
  predict held-out outcome
```

Only nested/adaptive validation or an independent dataset can support the predictive performance of the threshold-selection procedure itself.

## 13. Plain Controls And Burden QC


Plain control models are branch-specific. When the final model is no-DeltaHF, omit `DeltaHFScore` from the plain-control nuisance set. When the DeltaHF-adjusted branch is tested, include the same `DeltaHFScore` source and role label used by that branch.

### 13.1 ULF-only plain connected-streamline control

For each patient:

```text
Touched_ULF_only_i(l) = I[X_ULF_only_i(l,tau) > tau]

PlainULFOnlyTouchedCount_i = sum_l Touched_ULF_only_i(l)
PlainULFOnlyExposureSum_i  = sum_l X_ULF_only_i(l,tau)
PlainULFOnlyExposureTop5_i = mean top 5% X_ULF_only_i(l,tau) among touched candidate fibers
```

Compare for DeltaHF-adjusted branches:

```text
Y_post ~ Y_HF_ref + DeltaHFScore
Y_post ~ PlainULFOnlyExposureTop5 + Y_HF_ref + DeltaHFScore
Y_post ~ NetULFFiberScore + Y_HF_ref + DeltaHFScore
Y_post ~ NetULFFiberScore + PlainULFOnlyExposureTop5 + Y_HF_ref + DeltaHFScore
```

Compare for no-DeltaHF branches:

```text
Y_post ~ Y_HF_ref
Y_post ~ PlainULFOnlyExposureTop5 + Y_HF_ref
Y_post ~ NetULFFiberScore + Y_HF_ref
Y_post ~ NetULFFiberScore + PlainULFOnlyExposureTop5 + Y_HF_ref
```

The joint model is QC only. With `n=16`, it must not be interpreted as strong causal decomposition.

### 13.2 OSS activation plain control

For OSS sensitivity branches, compute a plain activation burden control within the inherited selected-source candidate universe:

```text
PlainOSSActivated_i(l) = I[X_ULF_only_OSS_i(l) > 0]
PlainOSSActivationCount_i = sum_l PlainOSSActivated_i(l)
PlainOSSActivationSum_i   = sum_l X_ULF_only_OSS_i(l)
PlainOSSActivationTop5_i  = mean top 5% X_ULF_only_OSS_i(l) among activated candidate fibers
```

Compare for DeltaHF-adjusted OSS branches:

```text
Y_post ~ Y_HF_ref + DeltaHFScore
Y_post ~ PlainOSSActivationTop5 + Y_HF_ref + DeltaHFScore
Y_post ~ NetULFFiberScore_OSS + Y_HF_ref + DeltaHFScore
Y_post ~ NetULFFiberScore_OSS + PlainOSSActivationTop5 + Y_HF_ref + DeltaHFScore
```

Compare for no-DeltaHF OSS branches:

```text
Y_post ~ Y_HF_ref
Y_post ~ PlainOSSActivationTop5 + Y_HF_ref
Y_post ~ NetULFFiberScore_OSS + Y_HF_ref
Y_post ~ NetULFFiberScore_OSS + PlainOSSActivationTop5 + Y_HF_ref
```

The OSS joint control model is QC only. It tests whether the OSS sensitivity result mainly reflects activation burden rather than outcome-filtered activation profile.

### 13.3 Additional burden QC variables

Compute but do not force into the primary model:

```text
PlainULFTotalExposureTop5
PlainHFComponentExposureTop5
PlainHFOverlapExposureTop5
PlainHFOutSupportTop5
HFOverlapFraction
ULFOnlyToTotalULFFraction
```

Required correlations / diagnostics:

```text
corr(NetULFFiberScore, Y_HF_ref)
corr(NetULFFiberScore, DeltaHFScore)
corr(Y_HF_ref, DeltaHFScore)
corr(NetULFFiberScore, PlainULFOnlyExposureTop5)
corr(NetULFFiberScore, PlainULFTotalExposureTop5)
corr(NetULFFiberScore, PlainHFOverlapExposureTop5)
corr(NetULFFiberScore, PlainHFOutSupportTop5)
VIF / condition number for final model
leave-one-subject-out coefficient sign stability
Cook's distance / DFBETA for final model
```

Collinearity flags:

```text
|corr| < 0.85: acceptable
0.85 <= |corr| < 0.95: high collinearity warning
|corr| >= 0.95: severe collinearity warning
```

---

## 14. Outputs

Output root:

```text
/Volumes/VAL/STNSNr/summary/normative_connectome_fiber/ulf/<connectome_slug>/<endpoint_slug>/<scale_slug>/<branch>/
```

Required numeric outputs per completed branch:

```text
normative_ULF_fiber_weights.csv
normative_ULF_fiber_scores.csv
normative_ULF_fiber_loocv_predictions.csv
normative_ULF_fiber_permutation_summary.csv
normative_ULF_fiber_bootstrap_summary.csv
normative_ULF_fiber_mapping_qc.json
normative_ULF_fiber_generation_manifest.json
normative_ULF_fiber_HF_overlap_exclusion_summary.csv
normative_ULF_fiber_delta_hf_support_summary.csv
normative_ULF_fiber_delta_hf_support_qc.json
```

Threshold scan outputs, if run:

```text
normative_ULF_fiber_threshold_scan_results.csv
normative_ULF_fiber_threshold_scan_heatmap_q2.csv
normative_ULF_fiber_threshold_scan_heatmap_rho.csv
normative_ULF_fiber_threshold_scan_heatmap_n_fibers.csv
normative_ULF_fiber_threshold_scan_selected_manifest.json
normative_ULF_fiber_threshold_scan_maxstat_permutation_summary.csv, if run
normative_ULF_fiber_threshold_scan_nested_validation_predictions.csv, if run
```

OSS-DBS activation sensitivity outputs, if run:

```text
normative_ULF_fiber_oss_parameter_manifest.json
normative_ULF_fiber_oss_activation_matrix_summary.csv
normative_ULF_fiber_oss_loocv_predictions.csv
normative_ULF_fiber_oss_permutation_summary.csv
normative_ULF_plain_oss_activation_summary.csv
normative_ULF_plain_oss_activation_model_comparison.csv
```

`normative_ULF_fiber_weights.csv` fields:

```text
connectome
endpoint_slug
scale_slug
branch
branch_role
intended_primary_branch
ulf_final_model_id
delta_hfscore_role
fallback_final_branch
ulf_fallback_final_status
hf_source_status
hf_source_prediction_status
hf_source_threshold_source
hf_source_tau_v_per_m
hf_source_coverage
hf_source_adjacent_passing_grid_cells
ulf_norm_fiber_source_status
ulf_norm_fiber_prediction_status
ulf_norm_fiber_endpoint_model_status
ulf_norm_fiber_selected_adjacent_passing_grid_cells
ulf_oss_sensitivity_status
oss_activation_output_type
oss_candidate_source_branch
oss_inherited_tau_v_per_m
oss_inherited_coverage
fiber_id
tau_v_per_m
coverage_ULF_only
rho_ULF
p_uncorrected
q_fdr
M_ULF
direction_class
is_top1_positive
is_top0p5_sour
is_top1500_positive
is_top500_negative
HF_overlap_coverage
ULF_only_to_total_ULF_exposure_fraction
target_labels_for_qc
```

`normative_ULF_fiber_scores.csv` fields:

```text
subject_id
connectome
endpoint_slug
scale_slug
branch
branch_role
intended_primary_branch
ulf_final_model_id
delta_hfscore_role
fallback_final_branch
ulf_fallback_final_status
score_map_source
Y_post
Y_HF_ref
DeltaHFScore
DeltaHFScore_in_support
hf_source_status
hf_source_prediction_status
hf_source_tau_v_per_m
hf_source_coverage
hf_source_adjacent_passing_grid_cells
ulf_norm_fiber_source_status
ulf_norm_fiber_prediction_status
ulf_norm_fiber_endpoint_model_status
ulf_oss_sensitivity_status
oss_activation_output_type
oss_candidate_source_branch
oss_inherited_tau_v_per_m
oss_inherited_coverage
NetULFFiberScore
NetULFFiberScore_OSS
SweetPeak5_ULF
SourPeak5_ULF
SweetPeak5_ULF_OSS
SourPeak5_ULF_OSS
PlainULFOnlyExposureTop5
PlainULFTotalExposureTop5
PlainHFComponentExposureTop5
PlainHFOverlapExposureTop5
PlainHFOutSupportTop5
HF_out_candidate_fraction_source_tau
HF_out_selected_fraction_source_tau
n_candidate_fibers
n_sweet_selected_fibers
n_sour_selected_fibers
n_sweet_peak_fibers
n_sour_peak_fibers
is_primary_score
```

LOOCV prediction file:

```text
normative_ULF_fiber_loocv_predictions.csv
```

Required fields:

```text
subject_id
fold_id
endpoint_slug
scale_slug
connectome
branch
Y_post_observed
Y_post_predicted_ULF_model
Y_post_predicted_nuisance_only
NetULFFiberScore_LOOCV
NetULFFiberScore_OSS_LOOCV
Y_HF_ref
DeltaHFScore_LOOCV
DeltaHFScore_z_LOOCV
HF_out_candidate_fraction_source_tau_LOOCV
residual_ULF_model
residual_nuisance_only
```

Display and anatomical outputs:

```text
normative_ULF_fiber_display_top1_positive.tck
normative_ULF_fiber_display_top1_positive.mat
normative_ULF_fiber_display_top0p5_sour.tck
normative_ULF_fiber_display_top0p5_sour.mat
normative_ULF_fiber_density_map.nii.gz
normative_ULF_fiber_endpoint_labels.csv
normative_ULF_fiber_cortical_endpoint_summary.csv
normative_ULF_fiber_subcortical_crossing_summary.csv
normative_ULF_fiber_label_enrichment.csv
normative_ULF_fiber_enrichment_cache.csv
normative_ULF_fiber_enrichment_cache_manifest.json
normative_ULF_fiber_unthresholded_weighted_density.nii.gz
normative_ULF_fiber_positive_weighted_density.nii.gz
normative_ULF_fiber_negative_weighted_density.nii.gz
normative_ULF_fiber_neglogp_density.nii.gz
normative_ULF_fiber_qvalue_summary.csv
normative_ULF_fiber_fdr_cache.csv
normative_ULF_fiber_fdr_cache_manifest.json
fdr_summary_by_scale.csv
fdr_thresholded_positive_density_q05.nii.gz
fdr_thresholded_negative_density_q05.nii.gz
fdr_thresholded_positive_density_q10.nii.gz
fdr_thresholded_negative_density_q10.nii.gz
connectome_scale_performance_summary.csv
connectome_scale_overlap_summary.csv
connectome_density_correlation_summary.csv
connectome_selected_label_summary.csv
```

For continuous/statistical NIfTI outputs, non-covered or non-modeled voxels are written as `NaN`, not `0`. This applies to weighted density, positive/negative weighted density, `-log(p)` density, FDR-thresholded density, stability density, jitter density, plain touched density, and display-smoothed density maps outside the density support or model candidate support. `0` is reserved for a true zero contribution inside support. Count/binary masks, if emitted, remain `0` outside support because their semantics are count/false.

FDR q-values, q-thresholded maps, endpoint labels, enrichment caches, and display fibers are QC/display/interpretation outputs only. They stay outside resolver decisions, `F+`, `F-`, and `NetULFFiberScore`. Canonical FDR and enrichment cache definitions are maintained in `my_helper/stnsnr/normative_fiber_fdr_enrichment_cache_definition.md`.

---

## 15. Execution Efficiency

Efficiency rules follow the HF normative fiber model and must preserve exact equivalence.

### 15.1 Required sidecars

PPMI/MGH may use single sidecars. dTOR must use chunked sidecars.

```text
X_ULF_component_float32_fiber_major.npy
X_HF_component_float32_fiber_major.npy
X_HFonly_ref_float32_fiber_major.npy
X_ULF_only_tau{tau}_hf_overlap_rule_float32_fiber_major.npy for tau in [400,600,800,1000,1200,1500,2000]
S{tau}_ULF_only_bool.npy for tau in [400,600,800,1000,1200,1500,2000]
S_HF_component_hf_overlap_rule_bool.npy
S{tau}_ULF_total_bool.npy for tau in [400,600,800,1000,1200,1500,2000]
HF_overlap_ulf_tau{tau}_hf_overlap_rule_bool.npy for tau in [400,600,800,1000,1200,1500,2000]
fiber_id.npy
candidate_fiber_metadata.json
X_oss_float32_fiber_major.npy, pPAM activation probability for inherited selected-source candidates if OSS is run
OSS_ULFActivated_bool.npy, for inherited selected-source candidates if OSS is run
oss_parameter_manifest.json, if OSS is run
oss_activation_sidecar_metadata.json, if OSS is run
```

For dTOR:

```text
chunks/
  X_ULF_component_float32_fiber_major_chunk-*.npy
  X_HF_component_float32_fiber_major_chunk-*.npy
  X_HFonly_ref_float32_fiber_major_chunk-*.npy
  X_ULF_only_tau{tau}_hf_overlap_rule_float32_fiber_major_chunk-*.npy for tau in [400,600,800,1000,1200,1500,2000]
  S{tau}_ULF_only_bool_chunk-*.npy for tau in [400,600,800,1000,1200,1500,2000]
  S_HF_component_hf_overlap_rule_bool_chunk-*.npy
  HF_overlap_ulf_tau{tau}_hf_overlap_rule_bool_chunk-*.npy for tau in [400,600,800,1000,1200,1500,2000]
  X_oss_float32_fiber_major_chunk-*.npy, pPAM activation probability for inherited selected-source candidates if OSS is run
  OSS_ULFActivated_bool_chunk-*.npy, for inherited selected-source candidates if OSS is run
  fiber_id_chunk-*.npy
fiber_chunk_manifest.json
candidate_fiber_metadata.json
oss_parameter_manifest.json, if OSS is run
oss_activation_sidecar_metadata.json, if OSS is run
```

Loading all dTOR streamlines or all dTOR exposure values into memory is invalid.

### 15.2 Outcome-independent caches

May be reused across scales and endpoint families when cache keys match:

```text
raw component exposure sidecars
HF-only reference exposure sidecars
ULF-only overlap-exclusion masks
Coverage_ULF_tau caches
candidate fiber metadata
endpoint label lookup
density lookup
HF support lookup for locked HF model
OSS activation sidecars for a fixed OSS parameter set and inherited candidate source
```

### 15.3 Outcome-dependent objects

Must be recomputed inside each training fold:

```text
DeltaHFScore
DeltaHFScore z-scoring parameters
nuisance residuals
rho_ULF
M_ULF
F+_ULF
F-_ULF
SweetPeak5_ULF
SourPeak5_ULF
NetULFFiberScore
M_ULF_OSS, for OSS branches
F+_ULF_OSS, for OSS branches
F-_ULF_OSS, for OSS branches
SweetPeak5_ULF_OSS, for OSS branches
SourPeak5_ULF_OSS, for OSS branches
NetULFFiberScore_OSS, for OSS branches
final prediction model
```

### 15.4 Disallowed shortcuts

```text
reducing formal B=10000
adaptive permutation early stopping
full-sample ranks in fold-level estimation
approximate ranks
full-sample candidate mask replacing fold-specific candidate masks
fixed full-sample F+/F- used for LOOCV scoring
permutation score computed only from observed maps
outcome- or preliminary-rho-based fiber prefiltering
skipping sour fibers
using target-level aggregation as the primary model
using total ULF exposure in place of ULF-only exposure for the primary model
using full-sample HF model to compute held-out DeltaHFScore
extrapolating HF weights to out-of-support fibers
using OSS activation to redefine ULF candidate fibers
using OSS activation to select tau/Coverage source cells
using HF OSS activation to redefine HF-overlap exclusion
```

Every optimized implementation must pass exact-equivalence regression testing against a small deterministic brute-force subset before formal execution.

---


## 16. Execution Priority And Resolver Checkpoints

Run the model through ordered engineering checkpoints. These checkpoints verify computability and branch-specific input readiness; they do not add outcome-performance gates beyond the HF-derived branch-role resolver and the ULF source/prediction resolver.

Executable branches:

```text
core branches:
  ulf_peak_efield_tau800_cov5_delta_hf_adjusted
  ulf_peak_efield_tau800_cov5_no_delta_hf

sensitivity:
  non-selected core branch comparison
  ulf_peak_efield_tau1500_cov5_sensitivity
  ulf_top1500_top500_sensitivity
  ulf_total_exposure_tau800_cov5_sensitivity
  ulf_gain_endpoint_sensitivity
  ulf_delta_hf_from_hf_neighbor_source_sensitivity
  ulf_ossdbs_activation_sensitivity

source_resolver_scan:
  ulf_tau_coverage_source_resolver_scan

control:
  ulf_plain_connected_streamline_control
  ulf_hf_out_support_burden_control
```

Connectome roles:

```text
PPMI 85                 observed robustness
MGH-USC HCP 32          observed robustness
dTOR-985 Full           primary formal analysis
```

### Round 0: Version, input, HF source, and manifest freeze

Run checks only:

```text
lock document version
lock endpoint list
lock timeline labels T0/T1/T2/T3
lock scale list
lock connectome list
lock core branch pair
lock tau800/Coverage>=5 primary ULF parameters
lock tau1500/Coverage>=5 sensitivity parameters
lock ULF tau/Coverage source-resolver scan grid
lock seed = 42
check HF and ULF e-field manifests
check HF-only reference e-field manifest
check component labels and proxy status
check clinical ID join
check same-day T2 immediate/HF reference pairing
check scale direction
check matched HF normative model source
read hf_norm_fiber_source_status
read hf_norm_fiber_prediction_status
read hf_norm_fiber_burden_dominated
read hf_norm_fiber_threshold_source
read hf_norm_fiber_selected_tau_v_per_m
read hf_norm_fiber_selected_coverage
read hf_norm_fiber_selected_adjacent_passing_grid_cells
check HF support output availability when DeltaHFScore is to be computed
check PPMI / MGH / dTOR readability
check output root writability
```

Proceed to Round 1 only if all inputs are uniquely resolved and the manifest records the locked parameter set.

### Round 1: Sidecar cache, HF support cache, and equivalence test

Build PPMI/MGH sidecars and dTOR chunked sidecars for:

```text
HF component exposure
ULF component exposure
HF-only reference exposure
tau-specific ULF-only exposure for primary/sensitivity/scan taus
HF-overlap masks
matched HF source support masks
out-of-support QC summaries
```

Run deterministic small-subset equivalence testing for:

```text
candidate definition
HF support classification
DeltaHFScore
partial Spearman
selected fibers
NetULFFiberScore
LOOCV prediction
smoke permutation
bootstrap summaries
```

Proceed to Round 2 only if optimized and brute-force outputs match within tolerance and dTOR chunked IO has no memory error.

### Round 2: Chronic Observed LOOCV, Source Resolver, And Endpoint Realization

Run:

```text
for each available endpoint/scale row in the chronic endpoint family:
  core branches =
    ulf_peak_efield_tau800_cov5_delta_hf_adjusted
    ulf_peak_efield_tau800_cov5_no_delta_hf
  connectome order = PPMI observed -> MGH observed -> dTOR observed
  engineering status = endpoint rows are processed equivalently within endpoint family
```

For each endpoint row, after the locked HF resolver is read, define the HF-derived intended branch role. This step does not use ULF tau or Coverage; it only defines branch identity before branch-specific ULF source resolution:

```text
hf_norm_fiber_source_status in {pre_specified_accepted, scan_fallback_accepted}
and hf_norm_fiber_prediction_status = error_predictive:
  intended_primary_branch = delta_hf_adjusted

hf_norm_fiber_source_status in {pre_specified_accepted, scan_fallback_accepted}
and hf_norm_fiber_prediction_status = error_nonpredictive:
  intended_primary_branch = no_delta_hf

hf_norm_fiber_source_status = absent_no_stable_grid:
  intended_primary_branch = no_delta_hf

hf_norm_fiber_prediction_status = error_predictive
and DeltaHFScore inputs are invalid:
  intended_primary_branch = delta_hf_adjusted
  ulf_norm_fiber_endpoint_model_status = primary_branch_input_failure
  ulf_final_model_branch = no_delta_hf, if it has an accepted ULF source
  ulf_final_model_role = fallback_final, if it has an accepted ULF source

intended_primary_branch = delta_hf_adjusted
and delta_hf_adjusted has ulf_norm_fiber_source_status = absent_no_stable_grid
and no_delta_hf has an accepted ULF source:
  ulf_final_model_branch = no_delta_hf
  ulf_final_model_role = fallback_final
```

For each executable endpoint row and branch, run the tau/Coverage source resolver:

```text
first evaluate tau800/Coverage>=5
if not accepted, scan tau [400,600,800,1000,1200,1500,2000]
and Coverage [5,6,7,8,10,12]
assign ulf_norm_fiber_source_status
assign ulf_norm_fiber_prediction_status after a source exists
realize ulf_norm_fiber_endpoint_model_status from the intended primary branch
```

Round 2 records the following for each requested endpoint row before any downstream formal reporting:

```text
endpoint row is joined by ID, or records missing clinical data
dTOR observed LOOCV completes for accepted endpoint rows
fold-specific ULF candidates are non-empty for accepted endpoint rows
NetULFFiberScore has nonzero variance for accepted endpoint rows
the intended primary branch has finite branch-specific nuisance inputs or records primary_branch_input_failure
DeltaHFScore support QC is recorded as adequate, limited, or invalid for branches that use DeltaHFScore
prediction metrics are finite when a source exists
ulf_primary_branch is recorded in the manifest
ulf_norm_fiber_endpoint_model_status is recorded in the manifest
```

Proceed to Round 2b after every requested chronic endpoint row either completes observed outputs or records an endpoint-level technical/input failure.

### Round 2b: Same-Day Immediate Observed LOOCV

The same-day immediate endpoint family uses the same Round 2 resolver. Any secondary or co-primary status is reporting hierarchy only, must be declared before formal resampling, and does not change resolver classification, branch role, prediction-status assignment, endpoint realization, or output generation. Its branch-specific covariates are:

```text
endpoint = same-day immediate HF+ULF score
delta_hf_adjusted nuisance baseline = Y_post_immediate ~ Y_HF_ref + DeltaHFScore_immediate
no_delta_hf nuisance baseline       = Y_post_immediate ~ Y_HF_ref
```

The same-day gain sensitivity can be run only after the same-day immediate selected-source resolver is complete:

```text
Gain_immediate ~ NetULFFiberScore_deltaHF + DeltaHFScore_immediate
Gain_immediate ~ NetULFFiberScore_noDeltaHF
```

Proceed to Round 3 after every requested same-day immediate endpoint row either completes observed outputs or records an endpoint-level technical/input failure. If no same-day immediate rows are requested or complete, record that fact and proceed to Round 3.

### Round 3: Plain controls and burden diagnostics

Run:

```text
ulf_plain_connected_streamline_control
ulf_hf_out_support_burden_control
```

Controls must use the same nuisance set as the branch being interpreted.

Plain-control and burden-control failures do not change
`ulf_norm_fiber_source_status`, `ulf_norm_fiber_prediction_status`, or the
automatically selected final model. If `PlainULFOnlyExposureTop5` is not
computable, a joint QC model is singular, or `NetULFFiberScore` is perfectly
collinear with the plain exposure or out-of-support burden metrics, record the
branch-level control-readiness failure and continue with available formal
readiness fields. Such failures reduce burden-mechanism interpretability only.

### Round 4: dTOR Realized-Primary Smoke Resampling

Run for dTOR accepted final models:

```text
Freedman-Lane smoke permutation B=1000
subject-level smoke bootstrap B=1000
seed = 42
```

Proceed to Round 5 after each selected endpoint/source row either satisfies
smoke technical-pass criteria or records an explicit smoke technical-failure
status. Smoke `p < 0.05` is not a hard gate. A smoke technical failure must be
fixed before that endpoint/source row enters formal `B=10000` resampling, but it
does not change the automatically selected final model or other endpoint rows.

### Round 5: Cheap observed sensitivity

Run observed-only sensitivity:

```text
non-selected core branch comparison
ulf_peak_efield_tau1500_cov5_sensitivity
ulf_top1500_top500_sensitivity
ulf_total_exposure_tau800_cov5_sensitivity
ulf_gain_endpoint_sensitivity
ulf_delta_hf_from_hf_neighbor_source_sensitivity, if a locked HF source-neighborhood sensitivity is declared
PPMI -> MGH -> dTOR
```

Do not run formal permutation/bootstrap for these branches. Formal inference is reserved for the endpoint's automatically selected final model.

### Round 6: Selected-Source Exposure-Definition Neighborhood Sensitivity

Run observed LOOCV sensitivity around each ULF source selected in Round 2:

```text
pre_specified_accepted:
  report 0.9 * selected_tau and 1.1 * selected_tau,
  at selected_coverage, for executable branches when inputs allow

scan_fallback_accepted:
  report 0.9 * selected_tau and 1.1 * selected_tau,
  at selected_coverage, for executable branches when inputs allow

absent_no_stable_grid:
  skip Round 6 for that branch; if intended adjusted has an accepted no-delta
  fallback, downstream final-model rounds use no-delta, otherwise report no
  final model in Round 10
```

Tau-neighborhood sensitivity cannot replace the selected source.

### Round 7: dTOR Final-Model Formal Resampling

Run only:

```text
connectome = dTOR
branch = ulf_final_model_branch at its accepted final source
endpoint rows = endpoint rows with an accepted final model
formal permutation B=10000
formal bootstrap B=10000
seed = 42
```

Proceed to Round 8 after Round 7 either completes formal resampling or records that no final model is available for the endpoint row.

If formal resampling completes, manifests record:

```text
resampling_status = formal_complete
```

### Round 8: ULF OSS-DBS Activation Sensitivity

Run after the dTOR realized-primary model has completed formal resampling for the endpoint row. If the endpoint row has no completed formal realized-primary model, record `ulf_oss_sensitivity_status = not_run_no_formal_realized_primary`.

OSS is activation-model robustness evidence and does not alter the final model, ULF source status, prediction status, endpoint status, or DeltaHFScore source.

Run:

```text
oss_model_set = primary_locked
candidate source = realized primary selected-source candidate universe
exposure replacement = pPAM X_ULF_only_OSS derived from X_oss_float32_fiber_major.npy
activation probability subtype = exact activated_count/10 over 10 pPAM samples
nuisance design = realized primary branch nuisance design
frequency validation = requested_frequency_hz equals oss_parameter_frequency_hz
dTOR realized-primary final branch observed LOOCV
dTOR smoke Freedman-Lane permutation B=1000
```

PPMI and MGH remain peak-E-field observed cross-connectome robustness branches.
Required OSS sidecars are limited to the final dTOR branch unless a future model document explicitly promotes cross-connectome OSS sensitivity.

Write:

```text
normative_ULF_fiber_oss_parameter_manifest.json
normative_ULF_fiber_oss_activation_matrix_summary.csv
normative_ULF_fiber_oss_loocv_predictions.csv
normative_ULF_fiber_oss_permutation_summary.csv
normative_ULF_plain_oss_activation_summary.csv
normative_ULF_plain_oss_activation_model_comparison.csv
```

OSS technical-pass criteria:

```text
OSS parameter manifest is locked
OSS activation sidecars align with inherited selected-source candidate fiber ids
OSS activation sidecars store exact ten-sample float32 p(A), and fitting uses I[p(A) >= 0.5]
OSS frequency is modeled and verified
OSS hemisphere/source merge rule is max_probability_union
OSS activation matrix is not all NaN
OSS activation matrix is not all zero
NetULFFiberScore_OSS has nonzero variance
OSS LOOCV is fit
OSS B=1000 smoke permutation completes
PlainOSSActivationTop5 is computable
OSS joint control model is fit
```

Proceed to Round 9 after OSS either satisfies the technical-pass criteria or records an explicit not-run/failure status. If OSS activation is all zero or mostly tied, mark `ulf_oss_sensitivity_status = failed_activation_degenerate` and continue to Round 9 without using OSS as robustness support. If OSS is technically valid and directionally consistent with the peak-E-field result, mark `ulf_oss_sensitivity_status = passed_activation_consistent`. If OSS and peak-E-field results disagree while remaining technically valid, mark `ulf_oss_sensitivity_status = passed_activation_model_dependent`.

If required OSS activation files, component labels, or locked OSS parameter metadata are missing, mark `ulf_oss_sensitivity_status = not_run_missing_oss_inputs`. If OSS inputs exist but the OSS branch nuisance design, LOOCV prediction model, or plain activation control is singular or otherwise not estimable, mark `ulf_oss_sensitivity_status = failed_oss_design_or_prediction`.

### Round 9: ULF jitter QC

Run only for dTOR branches with completed formal realized-primary results.

Jitter changes HF and ULF component geometry, so each jitter iteration must rebuild:

```text
HF component exposure
ULF component exposure
HF-only reference exposure if jitter is applied to reference phase
HF-overlap exclusion
ULF-only exposure
DeltaHFScore, if used by the branch
ULF candidate masks
M_ULF
NetULFFiberScore
LOOCV prediction
```

If jitter is unstable, report the result as spatially fragile.

### Round 10: Display, FDR, labels, density, and cross-connectome summaries

Generate display outputs only after numeric branches are locked. Display, FDR, enrichment, labels, density, and cross-connectome outputs must derive from finalized numeric outputs and stay outside resolver decisions. FDR and enrichment caches follow `my_helper/stnsnr/normative_fiber_fdr_enrichment_cache_definition.md`.

Generate according to branch reporting role:

```text
all completed numeric branches:
  selected-fiber displays, density maps, endpoint labels, connected-region labels,
  plain touched-streamline density maps, and cross-connectome summaries when requested

formal or explicitly promoted figure-grade selected final branches:
  FDR cache, q-value summaries, FDR-thresholded display density maps,
  enrichment cache, and derived label-enrichment summaries
```

Observed-robustness rows without promoted figure-grade status may stop at density
and label outputs. Missing FDR/enrichment caches for those rows are recorded as
`definition_documented_cache_not_generated` and do not change the ULF source
status, prediction status, endpoint status, or final model branch.


## 17. Interpretation Boundary

Interpret the final model according to `ulf_norm_fiber_endpoint_model_status`.

If `ulf_norm_fiber_endpoint_model_status = primary_branch_error_predictive` and the final model is DeltaHF-adjusted:

```text
After accounting for the patient's same-day/pre-ULF HF clinical state and a model-supported HF-component change score, ULF-only engagement of this outcome-filtered normative streamline profile is associated with post-HF+ULF clinical outcome.
```

If `ulf_norm_fiber_endpoint_model_status = primary_branch_error_predictive` or `primary_branch_error_nonpredictive` and the final model is no-DeltaHF:

```text
After accounting for the patient's same-day/pre-ULF HF clinical state, ULF-only engagement of this normative streamline profile is associated with post-HF+ULF clinical outcome. DeltaHFScore-adjusted results, when computable, are sensitivity analyses.
```

If intended adjusted has `ulf_norm_fiber_endpoint_model_status` equal to
`primary_branch_input_failure` or `absent_no_stable_ulf_grid` and accepted
no-delta is available:

```text
The HF-derived intended adjusted model could not be realized because required inputs/design failed or no stable adjusted source existed. Accepted no-DeltaHF is the endpoint's fallback final model and must be labeled `ulf_final_model_role = fallback_final`, not HF-derived primary.
```

Do not interpret as:

```text
ULF causal tract has been validated.
HF contribution has been fully removed.
HF-overlap streamlines have no ULF biological role.
HF out-of-support exposure has no effect.
Every selected streamline is patient-specific.
The result proves an anatomical SNr gain mechanism.
A non-final sensitivity result can replace the automatically selected final model.
A ULF tau/Coverage neighborhood sensitivity replaces the selected source.
```

Because `n=16`, all ULF fiber-level results are hypothesis-generating. Negative or unstable LOOCV results should not be interpreted as proof that ULF has no biological effect; they may reflect limited sample size, endpoint noise, stimulation-field uncertainty, HF adjustment instability, out-of-support HF-component exposure, threshold-definition sensitivity, or connectome limitations.
