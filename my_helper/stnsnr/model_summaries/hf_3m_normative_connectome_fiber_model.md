# HF-Only 3m Normative Connectome Fiber-Level Model — Revised

Version: 2026-07-06 threshold-scan and downstream-status specification
Scope: HF-only 3m normative connectome fiber-level model; provides source-model status and DeltaHFScore eligibility for ULF add-on fiber models.

## YAML Core Interface (Implemented; Real Acceptance Pending)

The future configuration/orchestration contract is documented in
`my_helper/stnsnr/four_model_yaml_core_refactor_plan.md`. This model summary
remains authoritative for connectome roles, exposure, source resolution,
formal resampling, controls, OSS, jitter, and numeric reporting. Shared profile,
identity, catalog, state, run-store, configured model service, final-model
resolver, formal/sensitivity adapters, OSS producer/consumer, and numeric
reporting are implemented. The configured-core regression currently passes
300 tests, and the related HF/ULF/statistics selftests pass. Real MDS-UPDRS
III/IV execution and artifact acceptance remain pending; existing legacy output
trees are unchanged until that run completes.

All configured HF/frequency-1 endpoint scales are engineering-equivalent.
PPMI, MGH, and dTOR roles may differ as declared below, but scale identity does
not change execution or resolver rules. Public YAML provides the shared
`four_model_v1` model/formal/sensitivity parameters. Normative fiber has no
global candidate-threshold parameter; candidates are `internal-derived` for
each tau/Coverage cell and training fold. Equivalence and smoke parameters are
`internal-test`; selected source/status fields and artifact paths are
`runtime output`.

The core statistical domain remains the configured whole connectome before
stimulation tau/Coverage filtering. Anatomical ROI restriction, VTA/ROI
postprocessing, regional heatmaps, and GUI are outside the planned core
refactor.

## Research Question

Which normative connectome streamlines touched by HF stimulation are associated with better 3-month HF-only clinical outcome?

This is a full-connectome fiber-level DBS Fiber Filtering model. Individual streamlines are the modeling unit. Target atlases are used only after modeling for endpoint labels, anatomical enrichment, QC, and display grouping; they do not define the primary predictors.

Frequency definitions:

```text
HF  = high-frequency stimulation component, frequency_Hz >= 100
ULF = ultra-low-frequency stimulation component, frequency_Hz <= 50
```

## Endpoint

Primary endpoint:

```text
Y_post = raw HF-only 3-month clinical score
```

Primary covariate:

```text
Y_base = raw preoperative clinical score
```

Executable endpoint rows:

```text
all available HF-only 3-month clinical scales joined by ID
```

Engineering implementation treats every available endpoint/scale equivalently. No scale receives special execution status in the model resolver. Reporting hierarchy may still name a clinical primary endpoint, but this hierarchy does not change engineering execution, source resolver, prediction-status assignment, or output generation.

Raw scores come from:

```text
/Users/mojackhu/Research/STNSNr/summary/cohort/subj/subject_effect_origin.xlsx
```

Rows are joined by `ID` (`SNr003`, `SNr006`, etc.). The improvement-rate table is not used by this model. Scale direction is read from the shared direction table; unknown scales must explicitly define whether higher or lower values are better.

## Inputs

- HF-only raw `sim-efield` maps from the `3m/STN` condition, in `V/m`. Use raw `sim-efield`, not `sim-efieldgauss`.
- Public Lead-DBS structural connectomes:

  ```text
  PPMI 85 (Ewert 2017)          observed robustness
  MGH-USC HCP 32 (Horn 2017)    observed robustness
  dTOR-985 Full (Elias 2024)    primary analysis
  ```

- Right canonical streamline features from each connectome `data.mat`.
- Left/right homology via `ea_flip_lr_nonlinear`.
- Anatomical atlases for labeling/QC/display only:

  ```text
  STNSNr-connected regions
  STN-connected regions
  SNr-connected regions
  Custom STN/SNr overlays
  ```

- OSS-DBS sensitivity environment:

  ```text
  conda env: ossdbsv2
  ```

Before any OSS-DBS sensitivity run, the primary pPAM parameter set must be locked and written to the branch manifest:

```text
oss_model_set = primary_locked
oss_model = OSS-DBSv2
activation_model = pPAM
deterministic_PAM = fallback/debugging only
cond_model = ColeCole4
conductivity = isotropic
patient_DTI_anisotropic_conductivity = not_used
probabilistic_parameter = Fiber Diameter
fiber_diameter_range_um = [1, 4]
sampling_distribution = Equidistant
N_samples = 10
waveform = clinical rectangular pulse unless otherwise specified
frequency_Hz = clinical HF frequency
pulse_width_us = clinical pulse width
amplitude = clinical amplitude
activation_output = pPAM_activation_probability_float32
current_activation_output_subtype = deterministic_binary_0_1
hemisphere_source_merge_rule = max_probability_union
```

The OSS JSON frequency must be verified before the sidecar is valid:

```text
requested_frequency_hz == oss_parameter_frequency_hz
```

Minimum e-field checks: required path exists, subject/side/condition match is unique, file is raw `sim-efield`, and units are recorded as `V/m`. Missing or multiply matched e-fields fail the scale/run. E-fields are not automatically recomputed.


## Feature Construction

The candidate universe is the full public connectome, not target-restricted seed-target tracts.

Right canonical fiber model:

```text
canonical side = right
E_R_i(l)      = peak raw sim-efield along right canonical fiber l
E_L_to_R_i(l) = peak left e-field after ea_flip_lr_nonlinear along the same right canonical fiber l
X_HF_i(l)     = (E_R_i(l) + E_L_to_R_i(l)) / 2
```

Left-sided stimulation is flipped into the right canonical space and sampled along the same right-sided streamline features. Bilateral E-field information is used, but the streamline feature set is one-sided/canonical rather than a true bilateral streamline set.

Alternating same-side HF subprogram e-fields are combined by voxel-wise maximum before fiber sampling. Exposure is not scaled by frequency or pulse width.

Primary candidate rule:

```text
tau_primary = 800 V/m
coverage_primary = Coverage>=5
Coverage_tau(l) = sum_i I[X_HF_i(l) > tau]
F_candidate_tau = {l: Coverage_tau(l) >= coverage_min}
```

The pre-specified HF normative fiber source is:

```text
peak_efield_tau800_cov5_primary
```

The high-threshold single sensitivity remains:

```text
peak_efield_tau1500_cov5_sensitivity
```

A dedicated tau/Coverage threshold scan is part of the executable source resolver:

```text
hf_norm_fiber_threshold_scan_tau_grid_v_per_m = [400, 600, 800, 1000, 1200, 1500, 2000]
hf_norm_fiber_threshold_scan_coverage_grid    = [5, 6, 7, 8, 10, 12]
```

Interpretation of threshold families:

```text
tau800/Coverage>=5:
  pre-specified source

tau1500/Coverage>=5:
  predeclared high-threshold sensitivity

full tau x Coverage scan:
  fallback source search if tau800/Coverage>=5 is not accepted
  otherwise reported as source-neighborhood robustness
```

`X_HF_i(l)` is used for candidate definition, fiber-wise association, scoring, LOOCV, and prediction. dTOR exposure and candidate calculations must be chunked; loading the complete dTOR `fibers` matrix or all exposure values into memory is invalid.

For the source resolver scan, only `tau` and `Coverage` vary. The score rule is fixed:

```text
F_valid = coverage-passing fibers intersect finite-weight fibers
K+ = min(N+, max(ceil(0.01 * N+), 200))
K- = min(N-, max(ceil(0.005 * N-), 100))
H+ = min(K+, max(ceil(0.05 * K+), 20))
H- = min(K-, max(ceil(0.05 * K-), 20))
NetFiberScore = mean top-H+ positive weighted values
                - mean top-H- negative weighted values
```

Do not scan `top-k`, `top percentile`, `SweetPeak percentile`, `SourPeak percentile`, estimator family, connectome choice, or OSS-DBS activation variables inside the same threshold search. Top-count sensitivity remains a separate branch.

The OSS-DBS branch inherits the peak E-field candidate universe from the branch being tested. `X_HF_OSS_i(l)` is introduced only after candidate selection and must not redefine, shrink, or expand `F_candidate_tau`.

## Statistical Model

### Primary Estimator

For each candidate fiber `l`, use baseline-adjusted partial Spearman with average ranks for ties:

```text
rho_HF(l) =
  corr(
    resid(rank(Y_post_i)  ~ rank(Y_base_i)),
    resid(rank(X_HF_i(l)) ~ rank(Y_base_i))
  )
```

Degenerate fibers with zero exposure variance, zero rank variance, or zero residualized exposure variance are assigned `rho_HF(l)=NaN` and excluded from scoring.

Benefit-oriented fiber weight:

```text
M_HF(l) = -rho_HF(l)   for lower-is-better scales
M_HF(l) =  rho_HF(l)   for higher-is-better scales
```

Positive `M_HF(l)` means sweet or benefit-associated. Negative `M_HF(l)` means sour or worse-outcome-associated. FDR q-values and enrichment caches are computed for QC/display/interpretation only and stay outside resolver decisions and score-defining fiber sets.

### Optional Supplemental Estimator

OLS ANCOVA is retained as an optional future supplemental estimator. It is not run in the current executable analysis and does not generate output files in this run.

```text
Y_post_i = alpha_l
         + theta_HF(l) * X_HF_i(l)
         + beta_l      * Y_base_i
         + error_i,l
```

If enabled in a future run, `theta_HF(l)` would be reported as the fiber-wise OLS ANCOVA coefficient. The current model uses only the baseline-adjusted partial Spearman `rho_HF(l)` estimator for map fitting, `NetFiberScore`, LOOCV, permutation, bootstrap, and display outputs.

### Patient-Level Score

Within each full-sample map or LOOCV training fold, recompute the valid signed
fiber pools, outer libraries, and patient-level peak counts:

```text
F_valid = F_candidate_tau_cov intersect {l: M_HF(l) is finite}
F+_pool = {l in F_valid: M_HF(l) > 0}
F-_pool = {l in F_valid: M_HF(l) < 0}
K+ = min(N+, max(ceil(0.01 * N+), 200))
K- = min(N-, max(ceil(0.005 * N-), 100))
F+ = K+ largest positive weights, tie-broken by canonical fiber id
F- = K- most negative weights, tie-broken by canonical fiber id

SweetWeighted_i(l) = X_HF_i(l) * M_HF(l),      l in F+
SourWeighted_i(l)  = X_HF_i(l) * [-M_HF(l)],   l in F-

H+ = min(K+, max(ceil(0.05 * K+), 20))
H- = min(K-, max(ceil(0.05 * K-), 20))
SweetPeak5_i = mean of the H+ largest SweetWeighted_i(l)
SourPeak5_i  = mean of the H- largest SourWeighted_i(l)

NetFiberScore_i = SweetPeak5_i - SourPeak5_i
```

The historical output names `SweetPeak5` and `SourPeak5` are compatibility
field names; they no longer mean an unconstrained 5% rule. Empty positive or
negative pools contribute `0` and are labeled one-sided. Full sample and every
fold record `adequate_two_sign`, `limited_two_sign`,
`limited_positive_only`, `limited_negative_only`, or
`absent_no_valid_signed_fibers`, together with requested/actual K/H counts,
minimum-dominated flags, and selected-ID hashes. These support labels do not
change source or prediction classification.

Final prediction model:

```text
Y_post_i = alpha
         + delta * NetFiberScore_i
         + beta  * Y_base_i
         + error_i
```

The model is fit on the raw post-score scale. The primary validation statistic is LOOCV Spearman rho between held-out predictions and held-out raw outcomes.

## Validation

- Use leave-one-patient-out cross-validation.
- In each fold, rebuild `F_candidate_tau`, fit `M_HF(l)`, select fold-specific `F+` and `F-`, compute training and held-out `NetFiberScore`, and fit the prediction model using training patients only.
- Compare against the covariate-only baseline `Y_post ~ Y_base`.
- Primary metrics: LOOCV Spearman rho and plus-one permutation P value.
- Secondary metrics: LOOCV Pearson `r`, MAE, RMSE, and `Q2`.

Define `Q2` against the covariate-only clinical baseline:

```text
Q2 = 1 - SSE_NetFiberScore_model / SSE_YBase_only
```

- Formal Freedman-Lane permutation: `B=10000`, seed `42`, dTOR final-source branch for endpoint rows with an accepted HF final source.
- Subject-level bootstrap: `B=10000`, seed `42`, dTOR final-source branch for endpoint rows with an accepted HF final source.
- Smoke permutation/bootstrap: `B=1000`, seed `42`.
- Optional OLS ANCOVA is documented for future sensitivity analysis but is not run in the current execution.

PPMI, MGH, and dTOR all produce observed robustness outputs. dTOR additionally carries formal permutation, bootstrap, jitter QC, and the default FDR/enrichment figure-cache path when those caches are generated for selected final branches. OSS activation sensitivity is tracked separately. The Nature paper 5-fold/10-fold CV settings are documented in the reference checklist only; LOOCV is the executable validation design for this `n=16` cohort.


### HF Normative Fiber Source And Prediction Resolver

Source stability and patient-level prediction error are separate evidence axes. The source resolver first decides whether a normative HF fiber map is stable enough to define `DeltaHFScore`; prediction-error status then decides how downstream ULF branches are interpreted. `Q2`, LOOCV rho, nominal p values, bootstrap stability, selected-fiber stability, cross-connectome support, and burden-control behavior are report or robustness fields. They do not define the source resolver unless they expose an input/design failure.

The hard computability filter for each scale, connectome, and tau/Coverage grid cell is:

```text
n_subjects >= 12
fold_n_candidate_fibers_min >= 1000 for dTOR
fold_n_candidate_fibers_min >= 100 for PPMI/MGH observed robustness
selected fiber pools are computable
NetFiberScore is non-constant in every LOOCV fold
Y_base nuisance design is valid in the full sample and every LOOCV fold
all held-out predictions are finite
```

The pre-specified source is:

```text
tau = 800 V/m
Coverage >= 5
estimator = baseline-adjusted partial Spearman
score = NetFiberScore
validation = LOOCV
```

If the pre-specified source is not accepted, the fallback source must be selected only from the declared HF tau/Coverage scan grid:

```text
tau, V/m:
  400, 600, 800, 1000, 1200, 1500, 2000

Coverage:
  5, 6, 7, 8, 10, 12
```

Define HF normative fiber source status:

```text
hf_norm_fiber_source_status = pre_specified_accepted
  if the pre-specified tau800/Coverage>=5 grid cell passes the hard computability filter
  and at least 2 adjacent tau/Coverage grid cells also pass the hard computability filter

hf_norm_fiber_source_status = scan_fallback_accepted
  if tau800/Coverage>=5 does not pass the source-stability rule
  and a predeclared HF source scan contains another grid cell passing the same rule

hf_norm_fiber_source_status = absent_no_stable_grid
  if no evaluated tau/Coverage grid cell passes the source-stability rule
```

For `scan_fallback_accepted`, choose the fallback grid without using outcome-performance metrics:

```text
1. minimize grid distance from tau800/Coverage>=5
2. maximize adjacent passing grid cells
3. maximize fold_n_candidate_fibers_min
4. prefer stricter Coverage
5. prefer higher tau
```

Adjacent grid cells are defined on the declared HF source scan grid; horizontal, vertical, and diagonal one-step neighbors all count. The scan table must contain all declared grid cells needed to assign `pre_specified_accepted`, `scan_fallback_accepted`, or `absent_no_stable_grid`.

Define HF normative fiber prediction status only after a source exists:

```text
hf_norm_fiber_prediction_status = error_predictive
  if MAE_model < MAE_YBase_only
  and RMSE_model < RMSE_YBase_only

hf_norm_fiber_prediction_status = error_nonpredictive
  if a HF normative fiber source exists
  but MAE_model >= MAE_YBase_only
  or RMSE_model >= RMSE_YBase_only

hf_norm_fiber_prediction_status = not_applicable
  if hf_norm_fiber_source_status = absent_no_stable_grid
```

HF final-model source is selected automatically from the source resolver:

```text
if hf_norm_fiber_source_status = pre_specified_accepted:
  hf_final_model_source = pre_specified
  hf_final_model_role = primary

if hf_norm_fiber_source_status = scan_fallback_accepted:
  hf_final_model_source = scan_fallback
  hf_final_model_role = fallback_final

if hf_norm_fiber_source_status = absent_no_stable_grid:
  hf_final_model_source = none
  hf_final_model_role = no_final_model

hf_final_model_status = final_model_error_predictive
  if an HF final source exists and hf_norm_fiber_prediction_status = error_predictive

hf_final_model_status = final_model_error_nonpredictive
  if an HF final source exists and hf_norm_fiber_prediction_status = error_nonpredictive

hf_final_model_status = no_final_model_absent_no_stable_grid
  if hf_norm_fiber_source_status = absent_no_stable_grid
```

Burden-dominated flag:

```text
hf_norm_fiber_burden_dominated = true
  if PlainExposureTop5 + Y_base performs similarly to or better than
     NetFiberScore + Y_base
  or NetFiberScore loses sign/benefit after PlainExposureTop5 is added
  or |corr(NetFiberScore, PlainExposureTop5)| >= 0.95
```

A burden-dominated HF fiber model may still be reported as a stimulation-burden / placement-associated finding. This flag is a QC and interpretation field; it does not change `hf_norm_fiber_source_status`, `hf_norm_fiber_prediction_status`, or downstream ULF branch-role assignment.

Downstream ULF rule:

```text
hf_norm_fiber_source_status = absent_no_stable_grid:
  DeltaHFScore is not computed for the DeltaHF-adjusted ULF branch.
  ULF no_delta_hf is the intended primary branch.

hf_norm_fiber_source_status in {pre_specified_accepted, scan_fallback_accepted}
and hf_norm_fiber_prediction_status = error_predictive:
  DeltaHFScore may define the intended DeltaHF-adjusted ULF primary branch.

hf_norm_fiber_source_status in {pre_specified_accepted, scan_fallback_accepted}
and hf_norm_fiber_prediction_status = error_nonpredictive:
  DeltaHFScore may be computed for sensitivity only.
  ULF no_delta_hf is the intended primary branch.
```

Required manifest/QC fields:

```text
hf_norm_fiber_source_status
hf_norm_fiber_prediction_status
hf_final_model_source
hf_final_model_role
hf_final_model_status
hf_final_model_selection_reason
hf_norm_fiber_source_failure_reasons
hf_norm_fiber_burden_dominated
hf_norm_fiber_threshold_source
hf_norm_fiber_selected_tau_v_per_m
hf_norm_fiber_selected_coverage
hf_norm_fiber_selected_adjacent_passing_grid_cells
hf_norm_fiber_selected_grid_distance_from_pre_specified
rho_obs
p_perm if available
Q2
MAE_model
MAE_YBase_only
RMSE_model
RMSE_YBase_only
corr_NetFiberScore_YBase
corr_NetFiberScore_PlainExposureTop5
plain_control_incremental_status
high_leverage_subjects
selected_fiber_stability_summary
cross_connectome_support_status
delta_hfscore_allowed_role
```

Scientific interpretation:

```text
Stable normative fiber-map behavior can support a network-level spatial hypothesis.
It does not by itself validate NetFiberScore as an individual HF efficacy predictor.
```

## Sensitivity And Controls

Executable branches:

```text
primary:
  peak_efield_tau800_cov5_primary

sensitivity:
  peak_efield_tau1500_cov5_sensitivity
  top1500_top500_sensitivity
  ossdbs_activation_sensitivity

source_resolver_scan:
  tau_coverage_source_resolver_scan

control:
  plain_connected_streamline_control
```


### Tau/Coverage Source Resolver Scan

Purpose: determine whether the pre-specified tau800/Coverage>=5 HF source is computable and locally stable; if it is not, select a predeclared fallback tau/Coverage source using outcome-independent stability criteria.

This scan is part of the HF source resolver:

```text
pre-specified source = tau800/Coverage>=5
fallback source = selected scan grid cell, if the pre-specified source is not accepted
```

Executable grid:

```text
tau_grid_v_per_m = [400, 600, 800, 1000, 1200, 1500, 2000]
coverage_grid    = [5, 6, 7, 8, 10, 12]
```

For each grid cell:

```text
Coverage_tau(l) = sum_i I[X_HF_i(l) > tau]
F_candidate_tau_cov = {l: Coverage_tau(l) >= coverage_min}
```

Each grid cell reruns the complete observed LOOCV workflow:

```text
fold-specific candidate fibers
rho_HF(l)
M_HF(l)
fold-local finite signed pools
K+/K- outer libraries with 200/100 minima
H+/H- patient peaks with minimum 20
SweetPeak5 / SourPeak5 compatibility fields
NetFiberScore
Y_post ~ NetFiberScore + Y_base
LOOCV prediction
covariate-only baseline comparison
```

Hard computability filter for a source grid cell:

```text
n_subjects >= 12
fold_n_candidate_fibers_min >= 1000 for dTOR
fold_n_candidate_fibers_min >= 100 for PPMI/MGH observed robustness
selected fiber pools are computable
NetFiberScore non-constant in every fold
Y_base nuisance design is valid in every fold
all held-out predictions finite
```

Source selection rule:

```text
selection_connectome = dTOR
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

PPMI and MGH are not used to select the source. They provide observed cross-connectome robustness for the dTOR-selected and neighboring cells.

If a selected source is to be described as threshold-scan significant, run max-stat permutation over the full tau x Coverage family:

```text
for each permutation:
  rerun all grid cells
  record max statistic over eligible cells

p_max = plus-one probability of permuted max >= observed max
```

A stronger predictive claim may still be supported by nested/adaptive validation or independent validation, but that validation does not replace the source resolver:

```text
outer fold:
  leave one patient out
inner training set:
  scan tau/Coverage and select threshold
outer held-out patient:
  score and predict using the selected inner-fold threshold and map
```

Only one selected HF source per endpoint/scale may generate a downstream ULF `DeltaHFScore` branch. Neighboring threshold cells provide robustness evidence; they are not separate nuisance covariates in the same `n=16` ULF model.

### OSS-DBS Activation Sensitivity

OSS-DBS replaces peak E-field exposure with pathway/axon activation after the peak E-field candidate set has been defined:

```text
X_HF_OSS_i(l) = pPAM activation probability for fiber l under subject i HF stimulation
```

The sidecar column universe is the final selected-source tau/Coverage candidate
fiber id order, not the whole dTOR connectome atlas, not a parent raw
`fiber_ids.npy` when that file stores the full exposure universe, and not the
top sweet/sour display fibers. OSS activation must not redefine, shrink,
expand, or rescan the candidate fiber universe. The actual OSS column order is
recorded as `oss_fiber_ids.npy` or an equivalent sidecar manifest field.

For alternating same-side HF subprograms, OSS activation is computed per subprogram and then max-reduced:

```text
A_side_i,p(l) = pPAM activation probability under HF subprogram p
A_side_i(l)   = max_p A_side_i,p(l)
```

The right-canonical OSS probability sidecar uses activation union, and the
canonical fitting exposure is its 0.5-thresholded binary form:

```text
X_HF_OSS_probability_i(l) = max(A_R_i(l), A_L_to_R_i(l))
X_HF_OSS_i(l) = I[X_HF_OSS_probability_i(l) >= 0.5]
```

`A_L_to_R_i(l)` is computed by transforming the left electrode/stimulation
geometry and reconstruction coordinates into right-canonical space with
`ea_flip_lr_nonlinear`, then running OSS directly on the same ordered
`final.valid_feature_axis` used by the right side. No equality between native
left and right local fiber IDs is assumed. The canonical OSS exposure uses
`max_probability_union`; bilateral mean p(A) cannot replace it in fitting.

The OSS branch uses the selected-source candidate rule from the locked peak
E-field branch. It must use the endpoint row's resolved selected tau and
Coverage, not a hard-coded tau800/Coverage>=5 rule:

```text
Coverage_selected_tau(l) = sum_i I[X_HF_i(l) > selected_tau]
F_candidate_selected = {l: Coverage_selected_tau(l) >= selected_Coverage}
selected_tau = endpoint-specific selected source tau
selected_Coverage = endpoint-specific selected source Coverage
```

Candidate fibers are not selected by OSS activation. This prevents the sensitivity branch from adding an extra modeling degree of freedom.

The stored pPAM probability is:

```text
p(A_i,l) = number of activated pPAM samples for subject i and fiber l / N_samples
```

The configured producer runs ten complete OSS samples with Fiber Diameter
sampled equidistantly over `[1, 4]` micrometers. Stored p(A) must therefore be
an exact `activated_count / 10` value on the `0.0, 0.1, ..., 1.0` lattice.
`oss_time_result_PAM.h5` availability status is not the activation result. The
`p(A) >= 0.5` binary representation is the canonical fitting matrix.

OSS fiber-wise estimator:

```text
rho_HF_OSS(l) =
  corr(
    resid(rank(Y_post_i)      ~ rank(Y_base_i)),
    resid(rank(X_HF_OSS_i(l)) ~ rank(Y_base_i))
  )

M_HF_OSS(l) = -rho_HF_OSS(l)   for lower-is-better scales
M_HF_OSS(l) =  rho_HF_OSS(l)   for higher-is-better scales
```

Positive `M_HF_OSS(l)` means activation of that streamline is benefit-associated. Negative `M_HF_OSS(l)` means activation is worse-outcome-associated.

OSS patient-level score:

```text
F+_OSS and F-_OSS use the same fold-local K+/K- rule and 200/100 minima

SweetWeighted_OSS_i(l) = X_HF_OSS_i(l) * M_HF_OSS(l),       l in F+_OSS
SourWeighted_OSS_i(l)  = X_HF_OSS_i(l) * [-M_HF_OSS(l)],    l in F-_OSS

SweetPeak5_OSS_i = mean of the fold-local H+ largest SweetWeighted_OSS_i(l)
SourPeak5_OSS_i  = mean of the fold-local H- largest SourWeighted_OSS_i(l)

NetFiberScore_OSS_i = SweetPeak5_OSS_i - SourPeak5_OSS_i
```

OSS prediction model:

```text
Y_post_i = alpha
         + delta * NetFiberScore_OSS_i
         + beta  * Y_base_i
         + error_i
```

For every connectome, scale, and LOOCV fold `h`:

```text
train = all patients except h
test  = patient h
```

The fold workflow is:

1. Use training patients only to compute peak E-field `Coverage_selected_tau_fold_h`.
2. Define `F_candidate_selected_fold_h = {l: Coverage_selected_tau_fold_h(l) >= selected_Coverage}`.
3. Read training and held-out `X_HF_OSS` values from the OSS sidecar for those candidate fibers.
4. Estimate `rho_HF_OSS(l)` on training patients only.
5. Convert to `M_HF_OSS(l)`.
6. Select fold-specific `F+_OSS` and `F-_OSS`.
7. Compute training and held-out `NetFiberScore_OSS`.
8. Fit `Y_post ~ NetFiberScore_OSS + Y_base` on training patients only.
9. Predict held-out `Y_post`.
10. Write the held-out row to `normative_HF_fiber_oss_loocv_predictions.csv`.

Fold-level prohibitions:

```text
no full-sample ranks
no full-sample M_HF_OSS
no full-sample F+_OSS or F-_OSS
no held-out patient in candidate definition
no held-out patient in prediction model fitting
```

OSS branch permutation is smoke-only:

```text
B = 1000
seed = 42
```

It uses Freedman-Lane residual permutation:

1. Fit nuisance model `Y_post ~ Y_base`.
2. Extract residuals `e_i`.
3. Permute residuals to `e_perm_i`.
4. Reconstruct `Y*_i = fitted_Y_base_i + e_perm_i`.
5. For each permutation, rerun the full OSS LOOCV workflow, including candidate definition, `rho_HF_OSS`, `M_HF_OSS`, `F+_OSS`/`F-_OSS`, `NetFiberScore_OSS`, held-out prediction, and LOOCV Spearman rho.

Permutation p value:

```text
p_plus_one = (1 + count(|stat_perm| >= |stat_obs|)) / (B + 1)
```

Default HF OSS uses smoke `B=1000` only. `B=10000` OSS permutation/bootstrap is not part of the default HF OSS round and would require a separate model-document revision.

OSS plain activation control tests whether the OSS result mainly reflects activation burden or lead placement:

```text
PlainOSSActivated_i(l) = I[X_HF_OSS_i(l) > 0]
PlainOSSActivationCount_i = sum_l PlainOSSActivated_i(l)
PlainOSSActivationSum_i   = sum_l X_HF_OSS_i(l)
PlainOSSActivationTop5_i  = mean top 5% X_HF_OSS_i(l) among activated candidate fibers
```

OSS control model comparisons:

```text
Y_post ~ Y_base
Y_post ~ PlainOSSActivationTop5 + Y_base
Y_post ~ NetFiberScore_OSS + Y_base
Y_post ~ NetFiberScore_OSS + PlainOSSActivationTop5 + Y_base
```

The OSS joint model is QC only for this `n=16` cohort and is not interpreted as a causal decomposition.

Plain connected-streamline control intentionally does not use clinical outcome, `rho_HF(l)`, `M_HF(l)`, or sweet/sour weights:

```text
Touched_i(l) = I[X_HF_i(l) > tau]
PlainCoverage(l) = sum_i Touched_i(l)
PlainTouchedCount_i = sum_l Touched_i(l)
PlainExposureSum_i  = sum_l X_HF_i(l)
PlainExposureTop5_i = mean top 5% X_HF_i(l) among touched fibers
```

Control model comparisons:

```text
Y_post ~ Y_base
Y_post ~ PlainExposureTop5 + Y_base
Y_post ~ NetFiberScore + Y_base
Y_post ~ NetFiberScore + PlainExposureTop5 + Y_base
```

The joint model is QC only for this `n=16` cohort. It tests whether outcome-filtered fibers add information beyond stimulation burden, lead placement, and connectome density.

Jitter QC has two levels for dTOR:

```text
jitter_level_1_selected_display = selected/display fibers only
jitter_level_2_model_density    = model-density robustness over candidate fibers or feasible subset
```

## Outputs

Output root:

```text
/Volumes/VAL/STNSNr/summary/normative_connectome_fiber/hf/<connectome_slug>/<scale_slug>/<branch>/
```

Required observed outputs per branch:

```text
normative_HF_fiber_weights.csv
normative_HF_fiber_scores.csv
normative_HF_fiber_loocv_predictions.csv
normative_HF_fiber_mapping_qc.json
normative_HF_fiber_generation_manifest.json
normative_HF_fiber_display_top1_positive.tck
normative_HF_fiber_display_top1_positive.mat
normative_HF_fiber_display_top0p5_sour.tck
normative_HF_fiber_display_top0p5_sour.mat
normative_HF_fiber_density_map.nii.gz
normative_HF_fiber_endpoint_labels.csv
normative_HF_fiber_cortical_endpoint_summary.csv
normative_HF_fiber_subcortical_crossing_summary.csv
normative_HF_fiber_label_enrichment.csv
normative_HF_fiber_enrichment_cache.csv
normative_HF_fiber_enrichment_cache_manifest.json
normative_HF_fiber_unthresholded_weighted_density.nii.gz
normative_HF_fiber_positive_weighted_density.nii.gz
normative_HF_fiber_negative_weighted_density.nii.gz
normative_HF_fiber_neglogp_density.nii.gz
normative_HF_fiber_qvalue_summary.csv
normative_HF_fiber_fdr_cache.csv
normative_HF_fiber_fdr_cache_manifest.json
normative_HF_fiber_top_percentile_sweep_summary.csv
fdr_summary_by_scale.csv
fdr_thresholded_positive_density_q05.nii.gz
fdr_thresholded_negative_density_q05.nii.gz
fdr_thresholded_positive_density_q10.nii.gz
fdr_thresholded_negative_density_q10.nii.gz
```

For continuous/statistical NIfTI outputs, non-covered or non-modeled voxels are written as `NaN`, not `0`. This applies to weighted density, positive/negative weighted density, `-log(p)` density, FDR-thresholded density, stability density, jitter density, plain touched density, and display-smoothed density maps outside the density support or model candidate support. `0` is reserved for a true zero contribution inside support. Count/binary masks, if emitted, remain `0` outside support because their semantics are count/false.

dTOR primary branch additionally writes:

```text
normative_HF_fiber_permutation_summary.csv
normative_HF_fiber_bootstrap_summary.csv
normative_HF_fiber_bootstrap_se.csv
normative_HF_fiber_bootstrap_selection_frequency.csv
normative_HF_fiber_bootstrap_sign_stability.csv
normative_HF_fiber_fold_selection_frequency.csv
normative_HF_fiber_fold_sign_stability.csv
normative_HF_fiber_stability_density_map.nii.gz
normative_HF_fiber_jitter_summary.csv
normative_HF_fiber_jitter_model_similarity.csv
normative_HF_fiber_jitter_selected_overlap.csv
normative_HF_fiber_jitter_density_correlation.csv
normative_HF_fiber_jitter_example_density_maps/
normative_HF_fiber_sensitivity_readiness_status.json
```

Plain connected-streamline control writes:

```text
normative_HF_plain_touched_fibers.tck
normative_HF_plain_touched_density_map.nii.gz
normative_HF_plain_touched_summary.csv
normative_HF_plain_connected_model_comparison.csv
```

OSS-DBS activation sensitivity writes:

```text
normative_HF_fiber_oss_parameter_manifest.json
normative_HF_fiber_oss_activation_matrix_summary.csv
normative_HF_fiber_oss_loocv_predictions.csv
normative_HF_fiber_oss_permutation_summary.csv
normative_HF_plain_oss_activation_summary.csv
normative_HF_plain_oss_activation_model_comparison.csv
```

Cross-connectome summaries are written at the HF normative connectome fiber summary root:

```text
connectome_scale_performance_summary.csv
connectome_scale_overlap_summary.csv
connectome_density_correlation_summary.csv
connectome_selected_label_summary.csv
```

Source resolver scan outputs are written under:

```text
/Volumes/VAL/STNSNr/summary/normative_connectome_fiber/hf/<connectome_slug>/<scale_slug>/source_resolver_scan/
```

Required source resolver scan outputs:

```text
normative_HF_fiber_threshold_scan_results.csv
normative_HF_fiber_threshold_scan_heatmap_q2.csv
normative_HF_fiber_threshold_scan_heatmap_rho.csv
normative_HF_fiber_threshold_scan_heatmap_mae_delta.csv
normative_HF_fiber_threshold_scan_heatmap_rmse_delta.csv
normative_HF_fiber_threshold_scan_heatmap_n_fibers.csv
normative_HF_fiber_threshold_scan_selected_manifest.json
normative_HF_fiber_threshold_scan_maxstat_permutation_summary.csv, if run
normative_HF_fiber_threshold_scan_nested_validation_predictions.csv, if run
```

Minimum table semantics:

- `normative_HF_fiber_weights.csv`: `connectome`, `fiber_id`, `tau_v_per_m`, `coverage`, `rho_HF`, `p_uncorrected`, `q_fdr`, `M_HF`, `direction_class`, display/sensitivity flags, and target labels for QC.
- `normative_HF_fiber_scores.csv`: `subject_id`, `score_map_source`, `connectome`, `branch`, compatibility fields `SweetPeak5`/`SourPeak5`, `NetFiberScore`, all requested/actual K/H counts, support status, dominated flags, selected-ID hashes, and `is_primary_score`.
- `normative_HF_fiber_scores.csv` in the OSS branch additionally stores `SweetPeak5_OSS`, `SourPeak5_OSS`, and `NetFiberScore_OSS`.
- `normative_HF_fiber_fdr_cache.csv`: canonical fiber-wise FDR cache defined in `my_helper/stnsnr/normative_fiber_fdr_enrichment_cache_definition.md`; it is a QC/display output and is not a source or prediction gate.
- `normative_HF_fiber_enrichment_cache.csv`: canonical fiber-level anatomical/pathway enrichment cache defined in `my_helper/stnsnr/normative_fiber_fdr_enrichment_cache_definition.md`; its background is the selected-source tau/Coverage candidate fiber universe.
- `fdr_summary_by_scale.csv`: derived q-threshold counts and overlap between percentile-selected fibers and q-ranked fibers.
- `normative_HF_fiber_label_enrichment.csv`: derived display summary from the enrichment cache for selected sweet/sour fibers.
- `normative_HF_fiber_mapping_qc.json`: candidate counts, coverage distribution, degenerate fiber counts, empty-fold failures, FDR method, label summaries, chunking parameters, memory use summaries, OSS-DBS status, OSS activation-output type, `hf_norm_fiber_source_status`, `hf_norm_fiber_prediction_status`, burden flag, and DeltaHFScore downstream role.
- `normative_HF_fiber_threshold_scan_results.csv`: one row per connectome, scale, tau, and coverage cell; includes candidate counts, selected-fiber counts, LOOCV metrics, baseline comparisons, plain-control status, high-leverage diagnostics, source-stability fields, adjacent support, and branch-role fields for downstream ULF.

PPMI and MGH observed branches do not require formal permutation/bootstrap files. Their manifests record:

```text
resampling_status = observed_only_connectome_robustness
```

## Visualization

Display outputs include:

- selected `K+` sweet library by `M_HF(l)`;
- selected `K-` sour library by negative `M_HF(l)`;
- selected-fiber density maps;
- unthresholded weighted-density maps;
- `-log(P)` density maps and q-value summaries;
- endpoint, cortical-origin, subcortical-crossing, and label-enrichment tables;
- plain touched-streamline density maps;
- STN/SNr and STNSNrplus anatomical overlays.

No display subset is the primary statistical significance map. FDR q-values, q-thresholded density maps, and enrichment caches are generated for QC/display/interpretation transparency, but they do not define resolver outputs or `F+`/`F-`, and they do not enter `NetFiberScore`.

## Execution Efficiency

Formal runs must be chunked and memmap-friendly.

PPMI/MGH may use single sidecar arrays:

```text
X_float32_fiber_major.npy       # shape = fiber x subject, averaged X_HF
S400_bool.npy                   # X_HF > 400 V/m, if threshold scan enabled
S600_bool.npy                   # X_HF > 600 V/m, if threshold scan enabled
S800_bool.npy                   # X_HF > 800 V/m
S1000_bool.npy                  # X_HF > 1000 V/m, if threshold scan enabled
S1200_bool.npy                  # X_HF > 1200 V/m, if threshold scan enabled
S1500_bool.npy                  # X_HF > 1500 V/m
S2000_bool.npy                  # X_HF > 2000 V/m, if threshold scan enabled
fiber_id.npy
candidate_fiber_metadata.json
```

dTOR must use chunked sidecars:

```text
chunks/
  X_float32_fiber_major_chunk-000001.npy
  S400_bool_chunk-000001.npy
  S600_bool_chunk-000001.npy
  S800_bool_chunk-000001.npy
  S1000_bool_chunk-000001.npy
  S1200_bool_chunk-000001.npy
  S1500_bool_chunk-000001.npy
  S2000_bool_chunk-000001.npy
  fiber_id_chunk-000001.npy
fiber_chunk_manifest.json
candidate_fiber_metadata.json
```

OSS activation sidecars are written after peak E-field candidate construction
and use the same selected-source candidate fiber id order:

```text
X_oss_float32_fiber_major.npy
oss_parameter_manifest.json
oss_activation_sidecar_metadata.json
```

`X_oss_float32_fiber_major.npy` stores pPAM activation probability
with rows = final branch subjects and columns = selected-source candidate fiber
ids. The configured producer stores exact ten-sample pPAM probabilities. For alternating HF subprograms, subprogram-level activation matrices may
be cached, but the executable analysis uses the max-reduced `A_side_i(l)` and
`max_probability_union` probability variables documented above, then derives
`X_HF_OSS_i(l) = I[p(A_i,l) >= 0.5]` for model fitting. A `p(A) >= 0.05`
plain-activation file may be written as a QC/display/plain-burden control. The
stored probability sidecar remains the provenance input and is not overwritten
by the task-local binary fitting matrix.

For LOOCV fold `h`, derive training-fold selected-source coverage by subtraction:

```text
S_selected_tau(l, i) = I[X_HF_i(l) > selected_tau]
Coverage_selected_tau_all(l) = sum_i S_selected_tau(l, i)
Coverage_selected_tau_fold_h(l) = Coverage_selected_tau_all(l) - S_selected_tau(l, h)
F_candidate_selected_fold_h = {l : Coverage_selected_tau_fold_h(l) >= selected_Coverage}
```

Optimization must not change the estimand: ranks are computed within training folds, full-sample ranks are prohibited, `F+`/`F-` are reselected in each fold/permutation/bootstrap, and formal resampling counts are not reduced for speed. Streaming top-k reducers should be used for dTOR `SweetPeak5` and `SourPeak5`; formal loops must not write full per-permutation or per-bootstrap fiber-weight tables unless debug output is explicitly enabled.

`normative_HF_fiber_generation_manifest.json` records runtime profile, connectome slug, branch, chunk size/count, sidecar dtype/layout, Python jobs, BLAS threads, candidate counts, coverage summaries, bootstrap finite-count summaries, and whether the optimized equivalence test passed.

## Interpretation Boundary

This model estimates normative fiber-level HF stimulation associations. It is closer to DBS Fiber Filtering than to seed-target target-level modeling, but it still uses population connectomes and does not prove patient-specific axonal causality.

Interpret as:

```text
HF stimulation appears more beneficial when it strongly modulates this normative streamline profile.
```

Do not interpret as:

```text
Every displayed streamline is a proven causal tract in every patient.
```

The primary model claim is defined by the dTOR selected-source model and its
resolver/prediction status, with PPMI/MGH cross-connectome consistency and the
plain connected-streamline control reported as robustness evidence. Label
enrichment is required only for interpretation transparency in full
figure-grade reporting; it does not define the primary model claim.



If the selected source is locally stable but does not improve MAE/RMSE over the `Y_base`-only baseline, interpret the result as:

```text
error_nonpredictive normative HF fiber source
```

This status can support a hypothesis about a reproducible fiber-level stimulation pattern, but it does not validate `NetFiberScore` as a patient-level counterfactual HF efficacy model. In downstream ULF analysis, a `DeltaHFScore` derived from this source is used only as sensitivity, with no-DeltaHF as the intended primary branch.

If tau800/Coverage>=5 is not accepted by the source resolver, a locally stable scan fallback may define the HF source for downstream `DeltaHFScore`. The manifest must record `hf_norm_fiber_threshold_source = scan_fallback`, selected tau/Coverage, and adjacent support.

## Additional Exact-Equivalence Optimization Rules

This section defines implementation-level acceleration rules only. These rules may change scheduling, caching, vectorization, scratch storage, and checkpointing. They must not change `rho_HF`, `M_HF`, `F+`, `F-`, `SweetPeak5`, `SourPeak5`, `NetFiberScore`, LOOCV, permutation p values, bootstrap summaries, or OSS-DBS branch semantics.

### Outcome-Independent Cache Boundary

Outcome-independent artifacts may be reused across scales, folds, permutations, bootstraps, OSS branches, and display branches when their cache keys match:

```text
fiber geometry
fiber_id order
right-canonical streamline coordinates
E_R_i(l)
E_L_to_R_i(l)
X_HF_i(l)
S_tau_R(l,i)
S_tau_L_to_R(l,i)
Coverage_tau_all(l)
fold-specific candidate masks by subtraction
endpoint labels
subcortical crossing labels
streamline-to-voxel density lookup
OSS activation sidecars for a fixed OSS parameter set
plain exposure and plain activation summaries
```

Outcome-dependent artifacts must be recomputed whenever `Y_post`, `Y_base`, training membership, permutation residuals, or bootstrap subject counts change:

```text
rank(Y_post_train)
rank(Y_base_train), if scale-specific
rho_HF(l)
M_HF(l)
F+
F-
SweetPeak5
SourPeak5
NetFiberScore
LOOCV prediction model
permutation statistic
bootstrap map and stability summaries
```

Exposure sidecars are connectome- and branch-specific, not scale-specific, unless scale-specific subject inclusion differs. When two scales use the same valid subjects, they reuse the same exposure sidecars, candidate masks, plain touched-streamline control sidecars, endpoint labels, density lookup tables, and OSS activation sidecars. If a scale has missing subjects, create a subject-subset view rather than resampling fibers.

### Cache Keys And Invalidation

Every sidecar and intermediate cache records a deterministic cache key:

```json
{
  "cache_key": {
    "connectome_slug": null,
    "connectome_path_hash": null,
    "fiber_id_hash": null,
    "subject_order_hash": null,
    "efield_path_manifest_hash": null,
    "efield_file_hashes": null,
    "left_to_right_transform_hash": null,
    "tau_values": [400, 600, 800, 1000, 1200, 1500, 2000],
    "coverage_rule": "Coverage_tau(l) = sum_i I[X_HF_i(l) > tau]; Coverage >= 5",
    "candidate_rule": "fold-specific candidate masks by training-subject coverage",
    "branch": null,
    "oss_parameter_manifest_hash": null,
    "software_version": null
  }
}
```

A cache is invalid if any cache-key field changes. If only `Y_post` or `Y_base` changes, exposure sidecars remain valid. If only the scale changes and subject inclusion is identical, exposure sidecars and candidate masks remain valid. If only display settings change, statistical sidecars remain valid. If OSS parameters change, OSS activation sidecars are invalid but peak E-field sidecars remain valid.

### Fold-Level Rank Residual Cache

For each LOOCV fold `h` and fiber chunk, the implementation may cache exposure-rank residuals computed within the training set only:

```text
xrank_h(l) = rank(X_train(l)) within training fold
xres_h(l)  = resid(xrank_h(l) ~ 1 + rank(Y_base_train))
znorm_h(l) = xres_h(l) / sqrt(sum(xres_h(l)^2))
```

Suggested cache files:

```text
Z_rankresid_float32_or_float64_chunk-000001_fold-01.npy
valid_exposure_rankresid_bool_chunk-000001_fold-01.npy
```

For observed and permuted outcomes, only the outcome side is recomputed:

```text
yrank_h = rank(Y*_train)
yres_h  = resid(yrank_h ~ 1 + rank(Y_base_train))
unorm_h = yres_h / sqrt(sum(yres_h^2))
rho_HF(l) = dot(znorm_h(l), unorm_h)
```

`Z_h` may be reused within LOOCV permutation. It cannot be reused across bootstrap resamples because bootstrap changes training-sample multiplicity. It cannot be reused across scales when `Y_base` is scale-specific. Full-sample ranks remain prohibited.

### Batched Permutation Kernel

Permutation dot products may be batched for linear algebra efficiency:

```text
permutation_batch_size = 32 or 64
U_h = [u_h_perm1, u_h_perm2, ..., u_h_permK]   # train_subject x K
RHO_chunk = Z_h_chunk @ U_h
```

Batching is allowed only for exact vectorized linear algebra. Each permutation still has its own `M_HF(l)`, `F+`, `F-`, `SweetPeak5`, `SourPeak5`, `NetFiberScore`, prediction model, and LOOCV statistic. No permutation may use an averaged, pooled, or shared selected-fiber set.

### Deterministic Top-K Tie Policy

Optimized `argpartition`, heap, or streaming top-k implementations must match brute-force stable sorting. Tie-breaking is deterministic:

```text
F+ selection key:
  (-M_HF(l), fiber_id)

F- selection key:
  (M_HF(l), fiber_id)

Patient-specific SweetPeak5/SourPeak5 key:
  (-weighted_value, fiber_id)
```

Higher weight wins; ties are broken by smaller deterministic `fiber_id`. If `argpartition` is used, it must overselect a boundary buffer, stable-sort the buffer with the documented key, and keep the exact requested count.

### dTOR Two-Pass Streaming Top-K

dTOR formal runs must not materialize full candidate-by-subject weighted matrices.

Pass 1 selects fibers across chunks:

```text
compute rho_HF(l)
compute M_HF(l)
update global heap for F+
update global heap for F-
```

Pass 2 scores patients by rereading only chunks that contain selected `F+` or `F-` fibers:

```text
SweetWeighted_i(l) = X_i(l) * M_HF(l)
SourWeighted_i(l)  = X_i(l) * [-M_HF(l)]
SweetPeak5_i       = patient-level mean over the H+ largest SweetWeighted_i(l)
SourPeak5_i        = patient-level mean over the H- largest SourWeighted_i(l)
NetFiberScore_i    = SweetPeak5_i - SourPeak5_i
```

Full candidate-weight tables are allowed only for observed small-connectome debug runs. dTOR formal runs must use two-pass streaming selected-fiber and patient-level top-k reducers.

### Coverage Bitmasks And Candidate Unions

Subject-side suprathreshold indicators may be stored as `uint32` or `uint64` bitmasks with popcount-based coverage calculation:

```text
bit 0 = subject 1 right
bit 1 = subject 1 left-to-right
bit 2 = subject 2 right
bit 3 = subject 2 left-to-right
...
```

The transparent bool arrays remain the reference representation:

```text
S_tau_*_bool.npy
S_tau_subjectside_u32.npy
```

Bitmask coverage is permitted only if it passes exact equivalence against bool-array coverage. Fold-specific candidate masks are still defined by held-out subtraction. A `union_of_folds` mask may be cached to reduce IO:

```text
candidate_tau{selected_tau}_cov{selected_coverage}_fold_01_bool ... candidate_tau{selected_tau}_cov{selected_coverage}_fold_16_bool
candidate_tau{scan_tau}_cov{scan_coverage}_fold_01_bool ... candidate_tau{scan_tau}_cov{scan_coverage}_fold_16_bool
candidate_tau{selected_tau}_cov{selected_coverage}_union_of_folds_bool
candidate_tau{scan_tau}_cov{scan_coverage}_union_of_folds_bool
```

`union_of_folds` may restrict IO, OSS activation, labeling, and density precomputation. Each fold must still use its own fold-specific candidate mask.

### OSS Candidate-First Activation

OSS-DBS activation is computed only for the final selected-source candidate
fiber ids required by the executable OSS branch:

```text
final selected-source candidate fiber id order
```

Non-candidate fibers are not used by `rho_HF_OSS`, `F+_OSS`, `F-_OSS`, `NetFiberScore_OSS`, LOOCV, or smoke permutation. Omitting their OSS activation does not change the OSS branch result.

OSS activation cache granularity:

```text
connectome x subject x side x subprogram x oss_parameter_hash x candidate_union
```

Reusable only when subject, side, subprogram, OSS parameter manifest, candidate fiber set, and connectome geometry match. Changing axon model, axon diameter, pulse width, amplitude, conductivity model, lead/e-field input, connectome geometry, or candidate fiber ids invalidates the cache.

Recommended OSS cache manifests:

```text
oss_activation_cache_key.json
oss_subprogram_activation_manifest.csv
oss_max_reduction_manifest.csv
```

### Scratch, Checkpoint, And Random Index Control

Formal loops should use local NVMe scratch when available and atomically promote final outputs after validation:

```text
scratch_root = /local_scratch/<run_id>/
final_root   = /Volumes/VAL/STNSNr/summary/...
```

Scratch relocation must not change file contents, subject order, fiber order, random seeds, or output semantics.

Permutation and bootstrap run in resumable blocks:

```text
permutation_block_size = 100 or 250
bootstrap_block_size   = 100 or 250
perm_block_0001_stats.npy
perm_block_0001_manifest.json
perm_block_0001.done
boot_block_0001_accumulator.npz
boot_block_0001_manifest.json
boot_block_0001.done
```

Partial blocks are never counted. Rerun blocks must reuse the same random indices. Workers write block-local outputs only; final CSV/JSON outputs are written atomically by the main process.

Random arrays are generated once from seed `42` and become part of the run definition:

```text
permutation_indices_seed42.npy
bootstrap_subject_counts_seed42.npy
```

Resumed runs must reuse the same arrays and recorded hashes.

### Label, Density, Rank-Pattern, And Chunk Autotune Caches

Endpoint labeling and density maps use precomputed lookup caches:

```text
fiber_endpoint_label_cache.parquet
fiber_subcortical_crossing_cache.parquet
fiber_to_voxel_sparse_index.npz
fiber_length_cache.npy
fiber_display_geometry_index.npy
```

Density maps are generated by joining selected fiber ids to the sparse voxel accumulator. The sparse density lookup must use the same affine, interpolation, streamline sampling rule, and voxelization rule as the brute-force display implementation.

Exact rank-pattern caching is allowed, especially for binary or sparse OSS activation:

```text
rank_pattern_key = hash(bytes(X_train_l) + train_subject_ids + dtype)
```

Only exact byte-identical exposure vectors may share rank-residual results. No rounding, binning, or approximate hashing is allowed in formal runs.

Chunk-size autotuning may benchmark:

```text
50k fibers
100k fibers
250k fibers
500k fibers
1M fibers
```

The selected chunk size is the fastest tested size that keeps peak memory below `memory_budget * 0.7`. The manifest records tested sizes, selected size, memory budget, peak memory, and throughput.

### Stage Scheduling

Recommended execution stages:

```text
Stage 1: sidecar cache and coverage cache
Stage 2: deterministic equivalence test
Stage 3: observed LOOCV numeric outputs
Stage 4: smoke permutation/bootstrap
Stage 5: source/prediction resolver and plain-control role assignment
Stage 6: tau/Coverage source resolver scan if tau800/Coverage>=5 is not accepted
Stage 7: optional max-stat or nested/adaptive validation for selected source robustness
Stage 8: formal dTOR permutation for the resolved selected source
Stage 9: formal dTOR bootstrap for the resolved selected source
Stage 10: OSS smoke branch
Stage 11: endpoint labels and density maps
Stage 12: FDR/display-only maps
Stage 13: cross-connectome summaries
```

Display and anatomical-label outputs are delayed, not omitted. They are generated exactly once from finalized selected-fiber ids after numeric QC passes.

### Disallowed Acceleration Shortcuts

The following are not valid acceleration strategies because they change the estimand, validation design, or statistical interpretation:

```text
reducing formal B=10000
adaptive permutation early stopping
full-sample ranks in fold-level estimation
approximate ranks
full-sample candidate mask replacing fold-specific candidate masks
fixed full-sample F+/F- used for LOOCV scoring
permutation score computed only from observed maps
outcome- or preliminary-rho-based fiber prefiltering
skip sour fibers
rewriting SweetPeak5/SourPeak5 as a linear matrix product
OSS activation only for observed selected fibers instead of the fold candidate universe
```

Any optimized implementation must pass an exact-equivalence regression test against a brute-force reference on a small deterministic subset before formal runs.

## Execution Priority And Resolver Checkpoints

The normative connectome fiber analysis is executed through ordered engineering checkpoints. These checkpoints ensure inputs and outputs are computable; they do not add outcome-performance gates beyond the source and prediction resolver defined above.

Current executable branch families:

```text
primary:
  peak_efield_tau800_cov5_primary

sensitivity:
  peak_efield_tau1500_cov5_sensitivity
  top1500_top500_sensitivity
  ossdbs_activation_sensitivity

source_resolver_scan:
  tau_coverage_source_resolver_scan

control:
  plain_connected_streamline_control
```

Current connectome roles:

```text
PPMI 85 (Ewert 2017)          observed robustness
MGH-USC HCP 32 (Horn 2017)    observed robustness
dTOR-985 Full (Elias 2024)    primary analysis
```

Use the current document version as the only executable specification:

```text
tau_primary = 800 V/m
coverage_primary = Coverage>=5
tau_sensitivity = 1500 V/m
threshold_scan_tau_grid_v_per_m = [400, 600, 800, 1000, 1200, 1500, 2000]
threshold_scan_coverage_grid = [5, 6, 7, 8, 10, 12]
Coverage_tau(l) = sum_i I[X_HF_i(l) > tau]
F_candidate_tau = {l: Coverage_tau(l) >= coverage_min}
```

Any legacy `cov3` or `EFieldCoverage>=3` rule is non-executable unless the model document is explicitly revised again. OLS ANCOVA remains a future supplemental estimator and is not run. FDR, enrichment, labels, density maps, q-thresholded maps, and display fibers are QC/display/interpretation outputs only; they stay outside resolver decisions, `F+`, `F-`, and `NetFiberScore`.

### Round 0: Version, Branch, Input, And Manifest Freeze

Purpose: guarantee all later outputs correspond to one locked document version and one locked parameter set.

Run checks only; do not run statistics:

```text
lock document version
lock scale list
lock connectome list
lock branch list
lock tau800/Coverage>=5 primary parameters
lock tau1500/Coverage>=5 sensitivity parameters
lock tau/Coverage source-resolver scan grid
lock score / validation parameters
lock random seed = 42
check output root writability
check e-field path manifest
check clinical table ID join
check scale direction
check PPMI / MGH / dTOR data.mat readability
check ea_flip_lr_nonlinear availability
check OSS conda env availability, without running OSS
```

Write:

```text
run_master_manifest.json
scale_manifest.csv
connectome_manifest.csv
branch_manifest.csv
efield_input_manifest.csv
clinical_join_manifest.csv
environment_manifest.json
```

Proceed to Round 1 only if:

```text
document version is unique
branch list is unique
tau800/Coverage>=5 primary, tau1500/Coverage>=5 sensitivity, and threshold-scan grid are locked
subject_id order is locked
Y_post / Y_base join by ID
scale direction is defined
all required e-field paths exist and are unique by subject/side/condition
PPMI / MGH / dTOR data.mat are readable
output root is writable
seed = 42 is recorded
```

Failure means stop before sidecar generation or LOOCV because inputs are not uniquely defined.

### Round 1: Sidecar Cache And Exact-Equivalence Regression Test

Purpose: validate implementation equivalence before formal statistics.

Run:

```text
PPMI / MGH sidecars:
  X_float32_fiber_major.npy
  S{tau}_bool.npy for tau in [400,600,800,1000,1200,1500,2000]
  fiber_id.npy
  candidate_fiber_metadata.json

dTOR chunked sidecars:
  chunks/X_float32_fiber_major_chunk-*.npy
  chunks/S{tau}_bool_chunk-*.npy for tau in [400,600,800,1000,1200,1500,2000]
  chunks/fiber_id_chunk-*.npy
  fiber_chunk_manifest.json
  candidate_fiber_metadata.json

coverage / candidate cache:
  Coverage_tau{tau}_all for all scan taus
  F_candidate_tau{tau}_cov{coverage}_full for all required tau/Coverage cells
  fold-specific candidate masks by subtraction
  candidate_tau{tau}_cov{coverage}_union_of_folds for executable primary, sensitivity, and scan cells
```

Run exact-equivalence test on a small deterministic subset:

```text
n_fiber_subset = 1000 to 10000
B_perm = 20
B_boot = 20
seed = 42
```

Compare optimized against brute-force for:

```text
fold-specific F_candidate_tau
rho_HF(l)
M_HF(l)
F+
F-
SweetPeak5
SourPeak5
NetFiberScore
LOOCV held-out predictions
LOOCV Spearman rho
small permutation null statistics
small bootstrap finite-count summaries
NaN / degenerate fiber locations
```

Proceed to Round 2 only if:

```text
subject order exactly matches
fiber_id order exactly matches
S800 / S1500 coverage exactly matches brute-force
fold-specific candidate masks exactly match
F+ / F- exactly match
NaN / degenerate locations exactly match
float outputs match within predefined float64 tolerance
small plus-one p value matches
dTOR chunked IO has no memory error
optimized_equivalence_test_passed = true
```

Failure means stop and fix sidecar, coverage, rank, top-k tie policy, or dTOR chunking because the optimized implementation is not validated.

### Round 2: Observed LOOCV For All Available HF-only 3m Endpoint Rows

Purpose: run the pre-specified observed primary branch for every available HF-only 3-month endpoint/scale row and record endpoint-level computability.

Run:

```text
for each available endpoint/scale:
  branch = peak_efield_tau800_cov5_primary
  connectome order = PPMI observed -> MGH observed -> dTOR observed
  engineering status = endpoint rows are processed equivalently
```

For each endpoint/scale and connectome compute:

```text
full-sample rho_HF / M_HF
K+ selected sweet library with minimum 200
K- selected sour library with minimum 100
SweetPeak5
SourPeak5
NetFiberScore
LOOCV prediction
covariate-only baseline comparison
basic mapping QC
endpoint-level computability status
```

Write numeric core outputs first for each endpoint/scale and connectome:

```text
normative_HF_fiber_weights.csv
normative_HF_fiber_scores.csv
normative_HF_fiber_loocv_predictions.csv
normative_HF_fiber_mapping_qc.json
normative_HF_fiber_generation_manifest.json
```

Delay `.tck` display, density maps, endpoint labels, FDR maps, q-thresholded maps, and label enrichment until numeric QC passes.

Proceed to Round 3 after every requested endpoint row either completes observed outputs or records an endpoint-level technical failure:

```text
endpoint/scale row is joined by ID, or records missing clinical data
at least one dTOR endpoint row completes observed LOOCV for downstream reporting
each completed endpoint row records pre-specified tau800/Coverage>=5 candidate support
rho_HF is computed or an endpoint-level technical reason is recorded
NetFiberScore variance is computed or an endpoint-level technical reason is recorded
held-out prediction status is computed or an endpoint-level technical reason is recorded
pre-specified observed model is fit or an endpoint-level technical reason is recorded
LOOCV Spearman / Pearson / MAE / RMSE / Q2 are computed or marked not applicable
mapping_qc.json records endpoint-level status
```

Round 2 does not decide whether the endpoint's final source is
`pre_specified_accepted`, `scan_fallback_accepted`, or `absent_no_stable_grid`.
That decision is made by the source resolver after the tau/Coverage scan.

QC warnings:

```text
dTOR observed looks technically unstable for an endpoint row
PPMI/MGH and dTOR have completely unexplained direction conflict for an endpoint row
Q2 is extremely worse than baseline-only for an endpoint row
```

Technical failure means fix tau800/Coverage>=5/e-field sampling, exposure variance, rank ties, top-k reducer, dTOR chunking, fiber ids, or sidecar alignment before running sensitivity or formal branches for that endpoint row. Poor Q2 or rho values remain report metrics and do not by themselves change `hf_norm_fiber_source_status` or `hf_norm_fiber_prediction_status`.

### Round 3: Plain Connected-Streamline Control

Purpose: test whether the outcome-filtered fiber model is merely stimulation burden, lead placement, or connectome density.

Run for endpoint rows and connectomes with computable observed outputs:

```text
branch = plain_connected_streamline_control
Touched_i(l) = I[X_HF_i(l) > tau]
PlainTouchedCount_i
PlainExposureSum_i
PlainExposureTop5_i
```

Compare:

```text
Y_post ~ Y_base
Y_post ~ PlainExposureTop5 + Y_base
Y_post ~ NetFiberScore + Y_base
Y_post ~ NetFiberScore + PlainExposureTop5 + Y_base
```

Write:

```text
normative_HF_plain_touched_summary.csv
normative_HF_plain_connected_model_comparison.csv
```

Delay:

```text
normative_HF_plain_touched_fibers.tck
normative_HF_plain_touched_density_map.nii.gz
```

Plain-control failures do not change `hf_norm_fiber_source_status`,
`hf_norm_fiber_prediction_status`, or the final selected-source branch. Evaluate
the following control-readiness criteria for interpretation:

```text
PlainExposureTop5 is computable for accepted endpoint rows
plain model is fit
joint model is not singular
NetFiberScore and PlainExposureTop5 are not perfectly collinear
```

If `PlainExposureTop5` is not computable, the plain model is not fit, the joint
model is singular, or `NetFiberScore` is perfectly collinear with
`PlainExposureTop5`, record the branch-level control-readiness failure and
continue with available formal readiness fields. Such failures reduce
burden/placement interpretability only.

Recommended collinearity flags:

```text
|corr(NetFiberScore, PlainExposureTop5)| < 0.85 = ideal
0.85 to 0.95 = high collinearity warning
>= 0.95 = severe collinearity warning
```

If plain control fully explains an endpoint row, that row may continue as a
minimal formal report, but interpretation is downgraded to stimulation burden /
placement-associated. Planned OSS and jitter layers may still record their
technical status, but they must not be used to strengthen mechanism
interpretation for that endpoint row.

### Round 4: dTOR Candidate-Source Smoke Permutation And Bootstrap

Purpose: test full-process resampling before formal `B=10000`.

Run only:

```text
connectome = dTOR
branch = candidate source branch under smoke validation
initial candidate branch = peak_efield_tau800_cov5_primary
final-source confirmation = repeat or reuse only when the selected source matches the smoked candidate
endpoint rows = computable endpoint/source rows that may enter formal reporting
Freedman-Lane smoke permutation B=1000
subject-level smoke bootstrap B=1000
seed = 42
```

If Round 5.5 later selects `scan_fallback_accepted`, the selected fallback
source needs its own smoke confirmation before Round 6 formal resampling. A
pre-specified-branch smoke result cannot be reused as smoke validation for a
different tau/Coverage source.

Each permutation must rerun the full LOOCV workflow:

```text
fold-specific candidate
rho_HF
M_HF
F+ / F-
SweetPeak5 / SourPeak5
NetFiberScore
held-out prediction
LOOCV Spearman
```

Write:

```text
smoke_permutation_summary.csv
smoke_bootstrap_qc_summary.csv
runtime_profile update
empty_fold_summary
degenerate_fiber_summary
bootstrap_finite_count_summary
```

Proceed to Round 5 after each candidate source either satisfies these smoke
technical-pass criteria or records an explicit endpoint/source technical-failure
status:

```text
B=1000 permutation completes
B=1000 bootstrap completes
plus-one p is computable
bootstrap finite count distribution is interpretable
there are not many empty F_candidate folds
there are not many all-NaN / degenerate maps
runtime profile indicates B=10000 is feasible
```

Do not use smoke `p < 0.05` as a hard gate. If smoke technically fails, fix
resampling, chunking, top-k, or rank cache for that endpoint/source row before
formal resampling; other endpoint/source rows may continue. If smoke technically
passes but results are fully degenerate, record the degeneracy and let the
source resolver decide whether a stable final source exists.

### Round 5: Cheap Observed Sensitivity

Purpose: test whether the primary result depends entirely on tau800 or selected-fiber rule before formal heavy computation.

Run:

```text
branches:
  peak_efield_tau1500_cov5_sensitivity
  top1500_top500_sensitivity

connectomes:
  PPMI
  MGH
  dTOR
```

Run:

```text
full-sample map
LOOCV prediction
scores
selected fiber summary
mapping QC
```

Do not run:

```text
formal B=10000 permutation
formal bootstrap
OSS
jitter
```

Write:

```text
normative_HF_fiber_weights.csv
normative_HF_fiber_scores.csv
normative_HF_fiber_loocv_predictions.csv
normative_HF_fiber_mapping_qc.json
normative_HF_fiber_top_percentile_sweep_summary.csv
```

Cheap observed sensitivity does not gate Round 5.5. Evaluate and record these
sensitivity-readiness criteria before the resolver summary:

```text
tau1500 branch completes, or records candidate-empty / threshold-too-strict
top1500/top500 branch completes
LOOCV outputs are finite
mapping QC is interpretable
```

If a sensitivity branch is candidate-empty, threshold-too-strict, nonfinite, or
otherwise not interpretable, record the branch-level sensitivity status and
continue to the endpoint-wise source resolver. Sensitivity-readiness failures do
not change `hf_norm_fiber_source_status`, `hf_norm_fiber_prediction_status`, or
the selected tau/Coverage source.

QC warning:

```text
tau800 and tau1500 are directionally consistent, or differences are explained by sparse coverage
top1500/top500 does not fully reverse the top1%/top0.5% mainline
dTOR and PPMI/MGH have directionally or anatomically interpretable consistency
```

If tau1500 is empty, record high-threshold sensitivity empty; this is not a technical failure. If top1500/top500 fully reverses the mainline, mark the result top-k dependent and downgrade interpretation.


### Round 5.5: Source/Predictive Status Resolver And Tau/Coverage Scan

Purpose: first decide whether tau800/Coverage>=5 is a computable, locally stable HF normative fiber source; if not, scan the predeclared tau/Coverage grid for a fallback source. Prediction-error status is assigned only after a source exists.

Assign:

```text
hf_norm_fiber_source_status =
  pre_specified_accepted
  scan_fallback_accepted
  absent_no_stable_grid

hf_norm_fiber_prediction_status =
  error_predictive
  error_nonpredictive
  not_applicable
```

Also assign:

```text
hf_norm_fiber_threshold_source
hf_norm_fiber_selected_tau_v_per_m
hf_norm_fiber_selected_coverage
hf_norm_fiber_selected_adjacent_passing_grid_cells
hf_norm_fiber_burden_dominated
plain_control_incremental_status
selected_fiber_stability_summary
delta_hfscore_allowed_role
```

If tau800/Coverage>=5 is `pre_specified_accepted`, it remains the locked HF source for downstream ULF. The scan grid may still be summarized as source-neighborhood robustness, but it does not change the selected source.

If tau800/Coverage>=5 is not accepted and the scan finds a stable fallback, record `hf_norm_fiber_source_status = scan_fallback_accepted` and use the selected tau/Coverage source for downstream `DeltaHFScore`. If its prediction status is `error_predictive`, ULF may treat the DeltaHF-adjusted branch as intended primary; if it is `error_nonpredictive`, ULF uses no-DeltaHF as intended primary and keeps DeltaHFScore only as sensitivity.

If no stable source exists, record `hf_norm_fiber_source_status = absent_no_stable_grid`; do not compute a DeltaHFScore-adjusted ULF branch from this HF family. ULF may still proceed through no-DeltaHF if ULF inputs are valid.

Source scan:

```text
run dTOR full tau x Coverage scan
run PPMI/MGH observed robustness for selected and neighboring dTOR cells
assign source status, prediction status, selected tau/Coverage, and adjacent support
```

Proceed to max-stat permutation or nested/adaptive validation only for the selected source when a stronger source-robustness claim is needed. These analyses do not override the resolver status.

### Round 6: dTOR Selected-Source Formal Permutation And Bootstrap

Purpose: generate the core statistical evidence for the current document.

Run only:

```text
connectome = dTOR
branch = peak_efield_tau800_cov5_primary when pre_specified_accepted
or branch = tau_coverage_source_resolver_scan selected source when scan_fallback_accepted
endpoint rows = accepted HF final-source endpoint rows
```

Recommended order:

```text
formal permutation B=10000
formal bootstrap B=10000
seed = 42
```

Permutation:

```text
primary statistic = LOOCV Spearman rho
p = plus-one two-sided
```

Bootstrap:

```text
bootstrap SE
bootstrap selection frequency
bootstrap sign stability
finite-count summaries
```

Write:

```text
normative_HF_fiber_permutation_summary.csv
normative_HF_fiber_bootstrap_se.csv
normative_HF_fiber_bootstrap_selection_frequency.csv
normative_HF_fiber_bootstrap_sign_stability.csv
normative_HF_fiber_fold_selection_frequency.csv
normative_HF_fiber_fold_sign_stability.csv
normative_HF_fiber_stability_density_map.nii.gz
```

Proceed to Round 7 only if:

```text
B=10000 permutation completes
B=10000 bootstrap completes
all block checkpoints are complete
plus-one p is computable
bootstrap finite counts are interpretable
fold selection frequency is computable
fold sign stability is computable
manifest records resampling_status = formal_complete
```

If formal technically fails, record the endpoint-level formal failure and do not claim OSS, jitter, or full figure-grade readiness for that endpoint row. If formal completes but is statistically negative, keep the selected final model unchanged; OSS and jitter may still be recorded as activation/spatial robustness layers, but they cannot override the formal result or become mechanism-strengthening evidence.

### Round 7: OSS-DBS Activation Sensitivity

Purpose: test whether the peak E-field fiber profile remains interpretable under pathway/axon activation variables. OSS is sensitivity, not primary.

Run:

```text
oss_model_set = primary_locked
oss_model = OSS-DBSv2
activation_model = pPAM
probabilistic_parameter = Fiber Diameter
fiber_diameter_range_um = [1, 4]
sampling_distribution = Equidistant
N_samples = 10
waveform
requested_frequency_hz
oss_parameter_frequency_hz
frequency_validation_status
pulse_width_us
amplitude
cond_model = ColeCole4
conductivity = isotropic
activation_output
oss_parameter_manifest.json
```

OSS candidate rule:

```text
inherit final selected-source tau/Coverage candidate fiber ids from peak E-field branch
write oss_fiber_ids.npy, or an equivalent manifest-recorded column order
do not redefine candidates by OSS activation
```

Generate:

```text
X_oss_float32_fiber_major.npy
oss_activation_sidecar_metadata.json
```

`X_oss_float32_fiber_major.npy` stores exact ten-sample pPAM activation probability on the realized valid axis. The hemisphere/source merge rule is `max_probability_union`.
Thresholded plain-activation files may be written only as QC/display/plain-burden controls.

Run order:

```text
dTOR final selected-source branch only
dTOR / ossdbs_activation_sensitivity / observed LOOCV
dTOR / OSS smoke permutation B=1000
OSS plain activation control
```

PPMI and MGH remain peak-E-field observed cross-connectome robustness branches.
Required OSS sidecars are limited to the final dTOR branch unless a future model document explicitly promotes cross-connectome OSS sensitivity.

Write:

```text
normative_HF_fiber_oss_parameter_manifest.json
normative_HF_fiber_oss_activation_matrix_summary.csv
normative_HF_fiber_oss_loocv_predictions.csv
normative_HF_fiber_oss_permutation_summary.csv
normative_HF_plain_oss_activation_summary.csv
normative_HF_plain_oss_activation_model_comparison.csv
```

OSS does not gate Round 8. Evaluate the following OSS technical-pass criteria when
OSS inputs are available:

```text
OSS parameter manifest is locked
OSS sidecar candidate fiber ids align with peak branch selected-source candidate ids
OSS activation matrix is not all NaN
OSS activation matrix is not all zero
NetFiberScore_OSS has nonzero variance
OSS LOOCV is fit
OSS B=1000 smoke permutation completes
PlainOSSActivationTop5 is computable
OSS joint control model is fit
```

QC support:

```text
corr(NetFiberScore_OSS, NetFiberScore_peak) > 0
F+_OSS and F+_peak have nonzero overlap
selected density / label summary is partly consistent with peak branch
OSS plain activation control does not fully replace NetFiberScore_OSS
```

If OSS activation is all zero or mostly tied, mark `hf_oss_sensitivity_status = failed_activation_degenerate` and continue without using OSS as robustness support. If required OSS activation files or locked OSS parameter metadata are missing, mark `hf_oss_sensitivity_status = not_run_missing_oss_inputs`. If OSS and peak branch disagree while remaining technically valid, mark `hf_oss_sensitivity_status = passed_activation_model_dependent`. If OSS plain activation fully explains the result, downgrade mechanism interpretation to activation burden. None of these OSS statuses changes `hf_norm_fiber_source_status`, `hf_norm_fiber_prediction_status`, or the final selected-source branch.

### Round 8: dTOR Jitter QC

Purpose: test dTOR primary spatial robustness.

Run only:

```text
connectome = dTOR
branch = final selected-source branch for the endpoint row
endpoint rows = endpoint rows with completed formal final result
```

Jitter tier 1:

```text
jitter_level_1_selected_display
selected F+ / F- overlap
display fiber robustness
selected density correlation
```

Jitter tier 2, only if jitter tier 1 is technically valid:

```text
jitter_level_2_model_density
candidate fibers or feasible subset
density robustness
model similarity
```

Write:

```text
normative_HF_fiber_jitter_summary.csv
normative_HF_fiber_jitter_model_similarity.csv
normative_HF_fiber_jitter_selected_overlap.csv
normative_HF_fiber_jitter_density_correlation.csv
normative_HF_fiber_jitter_example_density_maps/
```

Jitter does not gate Round 9 display generation. Evaluate the following jitter
technical-pass criteria when jitter inputs are available:

```text
jitter outputs are writable
jitter selected overlap is computable
jitter density correlation is computable
model similarity is computable
there are no all-empty jitter runs
```

If jitter inputs are missing or technically invalid, record the branch-level
jitter status and continue to Round 9 with the available formal, OSS, density,
label, FDR, and enrichment readiness fields. Jitter status cannot change
`hf_norm_fiber_source_status`, `hf_norm_fiber_prediction_status`, or the final
selected-source branch.

If jitter tier 1 technically fails, do not run jitter tier 2. If jitter tier 1 passes but is unstable, skip jitter tier 2 and label the final result spatially sensitive. If both tiers are stable, use them as spatial robustness support.

### Round 9: Display, FDR, Labels, Density, And Cross-Connectome Summaries

Purpose: generate display and interpretation outputs after numeric branches are locked. Display, FDR q-values, q-thresholded density maps, enrichment caches, and label outputs stay outside the resolver and never enter `NetFiberScore`. Canonical FDR and enrichment cache definitions are maintained in `my_helper/stnsnr/normative_fiber_fdr_enrichment_cache_definition.md`.

Generate according to the branch reporting role:

```text
all completed numeric branches:
  selected-fiber displays, density maps, endpoint labels, connected-region labels,
  plain touched-streamline density maps, and cross-connectome summaries when requested

formal or explicitly promoted figure-grade selected final branches:
  FDR cache, q-value summaries, FDR-thresholded display density maps,
  enrichment cache, and derived label-enrichment summaries
```

Output families:

```text
selected K+ sweet library
selected K- sour library
selected-fiber density maps
unthresholded weighted-density maps
positive weighted-density maps
negative weighted-density maps
neglogp density maps
qvalue summary
FDR q05 / q10 display density maps
endpoint labels
cortical endpoint summary
subcortical crossing summary
label enrichment
FDR cache
enrichment cache
plain touched-streamline density maps
STN/SNr overlays
cross-connectome summaries
```

Write:

```text
normative_HF_fiber_display_top1_positive.tck
normative_HF_fiber_display_top1_positive.mat
normative_HF_fiber_display_top0p5_sour.tck
normative_HF_fiber_display_top0p5_sour.mat
normative_HF_fiber_density_map.nii.gz
normative_HF_fiber_endpoint_labels.csv
normative_HF_fiber_cortical_endpoint_summary.csv
normative_HF_fiber_subcortical_crossing_summary.csv
normative_HF_fiber_label_enrichment.csv
normative_HF_fiber_enrichment_cache.csv
normative_HF_fiber_enrichment_cache_manifest.json
normative_HF_fiber_unthresholded_weighted_density.nii.gz
normative_HF_fiber_positive_weighted_density.nii.gz
normative_HF_fiber_negative_weighted_density.nii.gz
normative_HF_fiber_neglogp_density.nii.gz
normative_HF_fiber_qvalue_summary.csv
normative_HF_fiber_fdr_cache.csv
normative_HF_fiber_fdr_cache_manifest.json
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

Completion conditions:

```text
display files derive only from finalized numeric outputs
FDR / enrichment / label / display outputs stay outside resolver decisions
FDR and enrichment caches follow the canonical cache definition document
enrichment background is the selected-source tau/Coverage candidate fiber universe
observed-robustness rows without promoted figure-grade status may stop at density and label outputs
PPMI/MGH manifests record observed_only_connectome_robustness
dTOR primary manifest records formal permutation/bootstrap status
OSS manifest/status records smoke-only status when run, or an explicit not-run reason
unrun branches record explicit not-run reason
```

### Recommended Minimal Execution Path

The most resource-conscious path that still covers the mainline and planned sensitivity hierarchy is:

```text
1. Round 0-1:
   freeze document/inputs, build sidecars, run equivalence tests

2. Round 2:
   all available HF-only 3-month endpoint rows, tau800 primary observed
   PPMI -> MGH -> dTOR

3. Round 3:
   plain connected-streamline control

4. Round 4:
   dTOR selected endpoint rows, tau800 primary smoke permutation/bootstrap B=1000

5. Round 5:
   tau1500 sensitivity + top1500/top500 sensitivity observed

6. Round 5.5:
   endpoint-wise source/prediction resolver and tau/Coverage scan

7. Round 6:
   dTOR selected-source formal permutation/bootstrap B=10000

8. Round 7:
   dTOR final-branch OSS-DBS sensitivity, B=1000 smoke only

9. Round 8:
   dTOR jitter QC

10. Round 9:
   display / FDR / labels / cross-connectome summaries
```

The core principle is to process all available endpoint rows equivalently,
evaluate the pre-specified `peak_efield_tau800_cov5_primary` source first, let
the endpoint-wise resolver choose either the pre-specified source or a stable
tau/Coverage fallback, use plain control to separate outcome-filtered fibers
from stimulation burden, select endpoint rows for formal dTOR reporting as a
reporting/resource decision, and only then invest in OSS, jitter, and
display-layer outputs.
