# HF-Only 3m Normative Connectome Fiber-Level Model — Revised

Version: 2026-07-06 threshold-scan and downstream-status specification
Scope: HF-only 3m normative connectome fiber-level model; provides source-model status and DeltaHFScore eligibility for ULF add-on fiber models.

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

Default first-pass scales:

```text
MDS-UPDRS III score (STN, 3 m)
MDS-UPDRS III axial score (STN, 3 m)
```

Raw scores come from:

```text
/Users/mojackhu/Research/STNSNr/summary/cohort/subj/subject_effect_origin.xlsx
```

Rows are joined by `ID` (`SNr003`, `SNr006`, etc.). The improvement-rate table is not used by this model. Scale direction is read from the shared direction table; unknown scales must explicitly define whether higher or lower values are better.

## Inputs

- HF-only raw `sim-efield` maps from the `3m/STN` condition, in `V/m`. Use raw `sim-efield`, not `sim-efieldgauss`.
- Public Lead-DBS structural connectomes:

  ```text
  PPMI 85 (Ewert 2017)          observed figure-grade robustness
  MGH-USC HCP 32 (Horn 2017)    observed figure-grade robustness
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

Before any formal OSS-DBS sensitivity run, the primary OSS parameter set must be locked and written to the branch manifest:

```text
oss_model_set = primary_locked
axon_model = OSS-DBS default mammalian myelinated axon model
axon_diameter_um = locked_default_from_ossdbs_or_leaddbs_config
n_nodes = locked_default_from_ossdbs_or_leaddbs_config
waveform = clinical rectangular pulse unless otherwise specified
frequency_Hz = clinical HF frequency
pulse_width_us = clinical pulse width
amplitude = clinical amplitude
tissue_model = same as accepted Lead-DBS / OSS-DBS project default
conductivity_model = locked and recorded
activation_output = fractional activation if available, else binary activation
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

The original interpretive primary branch remains:

```text
peak_efield_tau800_cov5_primary
```

The high-threshold single sensitivity remains:

```text
peak_efield_tau1500_cov5_sensitivity
```

A dedicated post-hoc tau/Coverage threshold scan is now part of the executable exploratory family:

```text
hf_norm_fiber_threshold_scan_tau_grid_v_per_m = [400, 600, 800, 1000, 1200, 1500, 2000]
hf_norm_fiber_threshold_scan_coverage_grid    = [5, 6, 7, 8, 10, 12]
```

Interpretation of threshold families:

```text
tau800/Coverage>=5:
  original primary branch

tau1500/Coverage>=5:
  predeclared high-threshold sensitivity

full tau x Coverage scan:
  post-hoc high-dose / high-coverage candidate search
  not a replacement for the original primary branch
```

`X_HF_i(l)` is used for candidate definition, fiber-wise association, scoring, LOOCV, and prediction. dTOR exposure and candidate calculations must be chunked; loading the complete dTOR `fibers` matrix or all exposure values into memory is invalid.

For the post-hoc threshold scan, only `tau` and `Coverage` vary. The selected-fiber rule is fixed:

```text
F+ = top 1% positive fibers
F- = top 0.5% sour fibers
SweetPeak5/SourPeak5 = patient-level mean of top 5% weighted selected fibers
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

Positive `M_HF(l)` means sweet or benefit-associated. Negative `M_HF(l)` means sour or worse-outcome-associated. FDR q-values are computed for QC/display only and do not filter the primary model or scoring fiber set.

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

Within each full-sample map or LOOCV training fold:

```text
F+ = top 1% fibers with largest positive M_HF(l)
F- = top 0.5% fibers with most negative M_HF(l)

SweetWeighted_i(l) = X_HF_i(l) * M_HF(l),      l in F+
SourWeighted_i(l)  = X_HF_i(l) * [-M_HF(l)],   l in F-

SweetPeak5_i = mean of top 5% largest SweetWeighted_i(l)
SourPeak5_i  = mean of top 5% largest SourWeighted_i(l)

NetFiberScore_i = SweetPeak5_i - SourPeak5_i
```

`F+` and `F-` are selected within `F_candidate_tau`, excluding NaN or degenerate fibers. Percentile counts use `ceil(percent * n)` with at least 1 fiber when the corresponding positive or negative pool is non-empty. Empty `F+` or `F-` contributes `0` for that component. If a selected set is non-empty but a patient has zero exposure to all selected fibers, the corresponding peak score is `0`.

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

- Formal Freedman-Lane permutation: `B=10000`, seed `42`, dTOR primary peak-E-field branch only.
- Subject-level bootstrap: `B=10000`, seed `42`, dTOR primary peak-E-field branch only.
- Smoke permutation/bootstrap: `B=1000`, seed `42`.
- Optional OLS ANCOVA is documented for future sensitivity analysis but is not run in the current execution.

PPMI, MGH, and dTOR all produce observed figure-grade outputs. dTOR additionally carries formal permutation, bootstrap, and jitter QC. The Nature paper 5-fold/10-fold CV settings are documented in the reference checklist only; LOOCV is the executable validation design for this `n=16` cohort.


### Prediction-Validity Status And ULF Propagation

Spatial, selected-fiber, bootstrap, fold-sign, cross-connectome, or nominal permutation stability and patient-level predictive validity are separate evidence axes. A normative HF fiber profile may be anatomically or directionally stable while failing to improve out-of-sample individual prediction beyond the clinical baseline model.

Define the HF normative fiber source-model status for every scale, connectome, and branch that may feed ULF `DeltaHFScore`:

```text
hf_norm_fiber_prediction_validity_status = predictive_valid
  if LOOCV rho_obs > 0
  and Q2 > 0
  and MAE_model < MAE_YBase_only
  and RMSE_model < RMSE_YBase_only
  and NetFiberScore is not near-constant
  and all held-out predictions are finite
  and no single high-leverage subject explains the result
  and selected F+/F- stability is acceptable
  and the result is not fully replaced by PlainExposureTop5

hf_norm_fiber_prediction_validity_status = stable_nonpredictive
  if fiber direction, selected-fiber density, bootstrap/fold stability,
  nominal rho/p behavior, or cross-connectome anatomical support appears stable,
  but Q2 <= 0
  or MAE/RMSE do not improve over Y_base-only
  or NetFiberScore does not add prediction beyond plain stimulation burden

hf_norm_fiber_prediction_validity_status = failed_unstable
  if LOOCV rho_obs <= 0
  or candidate fibers are empty/near-empty in multiple folds
  or rho_HF is all/mostly NaN
  or NetFiberScore is near-constant
  or predictions are non-finite
  or F+/F- selection is highly unstable
  or one high-leverage subject dominates
  or connectome-specific contradiction is severe and unexplained
```

Burden-dominated flag:

```text
hf_norm_fiber_burden_dominated = true
  if PlainExposureTop5 + Y_base performs similarly to or better than
     NetFiberScore + Y_base
  or NetFiberScore loses sign/benefit after PlainExposureTop5 is added
  or |corr(NetFiberScore, PlainExposureTop5)| >= 0.95
```

A burden-dominated HF fiber model may still be reported as a stimulation-burden / placement-associated finding, but it must not be treated as a mechanistic patient-level HF efficacy-change predictor.

Downstream ULF rule:

```text
predictive_valid:
  DeltaHFScore may be treated as a model-supported HF efficacy-change covariate.
  ULF delta_hf_adjusted may be the interpretive primary branch.

stable_nonpredictive:
  DeltaHFScore may be computed for engineering compatibility and sensitivity only.
  It must be labeled unstable_generated_covariate.
  ULF no_delta_hf is the interpretive primary branch.

failed_unstable:
  DeltaHFScore must not define primary ULF interpretation.
  It may be omitted, or computed only for explicit fragility reporting if finite support exists.
  ULF no_delta_hf is the exploratory primary branch when ULF inputs are otherwise valid.

burden_dominated:
  DeltaHFScore may be used only as a burden/placement sensitivity covariate.
  It cannot be interpreted as a clean HF efficacy-change adjustment.
```

Required manifest/QC fields:

```text
hf_norm_fiber_prediction_validity_status
hf_norm_fiber_prediction_failure_reasons
hf_norm_fiber_burden_dominated
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

posthoc_candidate_search:
  posthoc_tau_coverage_threshold_scan

control:
  plain_connected_streamline_control
```


### Post-Hoc Tau/Coverage Threshold Scan

Purpose: identify whether a high-dose / high-coverage normative streamline core shows stronger patient-level predictive signal than the original broad primary branch.

This branch is exploratory model selection. It does not relabel or rescue the original primary branch:

```text
primary result = tau800/Coverage>=5 result
posthoc result = selected high-core candidate, if any
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
F+ = top 1% positive fibers
F- = top 0.5% sour fibers
SweetPeak5 / SourPeak5
NetFiberScore
Y_post ~ NetFiberScore + Y_base
LOOCV prediction
covariate-only baseline comparison
```

Hard filters for a usable grid cell:

```text
fold_n_candidate_fibers_min >= 1000 for dTOR
fold_n_candidate_fibers_min >= 100 for PPMI/MGH observed robustness
n_positive_pool_min >= 20
n_negative_pool_min >= 10
NetFiberScore non-constant in every fold
all held-out predictions finite
LOOCV rho_obs > 0
Q2 > 0
MAE_model < MAE_YBase_only
RMSE_model < RMSE_YBase_only
no single high-leverage subject explains the result
not burden-dominated by PlainExposureTop5
```

Selection rule for post-hoc candidate reporting:

```text
selection_connectome = dTOR
selection_statistic = Q2 first, then LOOCV rho as tie-breaker
eligible_cells = cells passing hard filters
neighbor_support = adjacent tau/Coverage cells with positive rho and Q2 > 0
```

PPMI and MGH are not used to select the threshold. They provide observed cross-connectome robustness for the dTOR-selected and neighboring cells.

If a selected branch is to be described as threshold-scan significant, run max-stat permutation over the full tau x Coverage family:

```text
for each permutation:
  rerun all grid cells
  record max statistic over eligible cells

p_max = plus-one probability of permuted max >= observed max
```

A stronger predictive claim requires nested/adaptive validation or independent validation:

```text
outer fold:
  leave one patient out
inner training set:
  scan tau/Coverage and select threshold
outer held-out patient:
  score and predict using the selected inner-fold threshold and map
```

Candidate levels:

```text
Level 0 = failed_grid_cell
  any hard-filter criterion fails
  ULF propagation = not allowed

Level 1 = fragile_exploratory_candidate
  hard filters pass but signal is isolated, Q2 is weak, neighboring cells disagree,
  selected fibers are unstable, or burden-dominated behavior is present
  ULF propagation = not recommended

Level 2 = usable_exploratory_candidate
  hard filters pass, at least 3 grid cells pass, at least 1 adjacent cell supports,
  Q2 > 0.05, MAE/RMSE both improve, and no severe plain-control replacement
  ULF propagation = exploratory DeltaHFScore sensitivity only

Level 3 = robust_exploratory_candidate
  Level 2 plus at least 5 passing grid cells, at least 2 adjacent supporting cells,
  Q2 >= 0.10, selected nominal p < 0.05, stable selected-fiber density,
  no high-leverage domination, and at least one non-dTOR connectome has compatible support
  ULF propagation = priority exploratory DeltaHFScore sensitivity only

Level 4 = post_selection_validated_hf_norm_fiber_model
  Level 3 plus nested/adaptive validation or equivalent post-selection validation with
  outer LOOCV rho > 0, Q2 > 0, MAE/RMSE improvement, and preferably max-stat p <= 0.05
  ULF propagation = may define DeltaHF-adjusted ULF primary branch
```

Only one selected post-hoc HF candidate per endpoint/scale may generate a downstream ULF `DeltaHFScore` branch. Neighboring threshold cells provide robustness evidence; they are not separate nuisance covariates in the same `n=16` ULF model.

### OSS-DBS Activation Sensitivity

OSS-DBS replaces peak E-field exposure with pathway/axon activation after the peak E-field candidate set has been defined:

```text
X_HF_OSS_i(l) = OSS-DBS activation value for fiber l under subject i HF stimulation
```

For alternating same-side HF subprograms, OSS activation is computed per subprogram and then max-reduced:

```text
A_side_i,p(l) = OSS activation under HF subprogram p
A_side_i(l)   = max_p A_side_i,p(l)
```

The bilateral right-canonical OSS activation exposure is:

```text
X_HF_OSS_i(l) = (A_R_i(l) + A_L_to_R_i(l)) / 2
```

The OSS branch uses the same candidate rule as the peak E-field branch:

```text
Coverage_tau(l) = sum_i I[X_HF_i(l) > tau]
F_candidate_tau = {l: Coverage_tau(l) >= 5}
tau_primary = 800 V/m
```

Candidate fibers are not selected by OSS activation. This prevents the sensitivity branch from adding an extra modeling degree of freedom.

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
F+_OSS = top 1% fibers with largest positive M_HF_OSS(l)
F-_OSS = top 0.5% fibers with most negative M_HF_OSS(l)

SweetWeighted_OSS_i(l) = X_HF_OSS_i(l) * M_HF_OSS(l),       l in F+_OSS
SourWeighted_OSS_i(l)  = X_HF_OSS_i(l) * [-M_HF_OSS(l)],    l in F-_OSS

SweetPeak5_OSS_i = mean top 5% largest SweetWeighted_OSS_i(l)
SourPeak5_OSS_i  = mean top 5% largest SourWeighted_OSS_i(l)

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

1. Use training patients only to compute peak E-field `Coverage_tau800_fold_h`.
2. Define `F_candidate_tau800_fold_h = {l: Coverage_tau800_fold_h(l) >= 5}`.
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

OSS does not run formal `B=10000` permutation and does not run bootstrap.

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
normative_HF_fiber_unthresholded_weighted_density.nii.gz
normative_HF_fiber_positive_weighted_density.nii.gz
normative_HF_fiber_negative_weighted_density.nii.gz
normative_HF_fiber_neglogp_density.nii.gz
normative_HF_fiber_qvalue_summary.csv
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

Post-hoc threshold scan outputs are written under:

```text
/Volumes/VAL/STNSNr/summary/normative_connectome_fiber/hf/<connectome_slug>/<scale_slug>/posthoc_threshold_scan/
```

Required post-hoc threshold scan outputs:

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
- `normative_HF_fiber_scores.csv`: `subject_id`, `score_map_source`, `connectome`, `branch`, `SweetPeak5`, `SourPeak5`, `NetFiberScore`, candidate/selected/peak fiber counts, and `is_primary_score`.
- `normative_HF_fiber_scores.csv` in the OSS branch additionally stores `SweetPeak5_OSS`, `SourPeak5_OSS`, and `NetFiberScore_OSS`.
- `fdr_summary_by_scale.csv`: q-threshold counts and overlap between percentile-selected fibers and q-ranked fibers.
- `normative_HF_fiber_label_enrichment.csv`: enrichment of selected sweet/sour fibers relative to the plain touched-streamline background.
- `normative_HF_fiber_mapping_qc.json`: candidate counts, coverage distribution, degenerate fiber counts, empty-fold failures, FDR method, label summaries, chunking parameters, memory use summaries, OSS-DBS status, OSS activation-output type, prediction-validity status, burden-dominated flag, and DeltaHFScore downstream eligibility.
- `normative_HF_fiber_threshold_scan_results.csv`: one row per connectome, scale, tau, and coverage cell; includes candidate counts, selected-fiber counts, LOOCV metrics, baseline comparisons, plain-control status, high-leverage diagnostics, post-hoc candidate level, and ULF propagation role.

PPMI and MGH observed branches do not require formal permutation/bootstrap files. Their manifests record:

```text
resampling_status = observed_only_connectome_robustness
```

## Visualization

Display outputs include:

- top 1% positive fibers by `M_HF(l)`;
- top 0.5% sour fibers by negative `M_HF(l)`;
- selected-fiber density maps;
- unthresholded weighted-density maps;
- `-log(P)` density maps and q-value summaries;
- endpoint, cortical-origin, subcortical-crossing, and label-enrichment tables;
- plain touched-streamline density maps;
- STN/SNr and STNSNrplus anatomical overlays.

No display subset is the primary statistical significance map. FDR q-values and q-thresholded density maps are generated for QC/display transparency, but they do not filter the primary model, define `F+`/`F-`, or enter `NetFiberScore`.

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

OSS activation sidecars are written after peak E-field candidate construction and use the same fiber ids:

```text
X_oss_float32_fiber_major.npy
PlainOSSActivated_bool.npy
oss_parameter_manifest.json
oss_activation_sidecar_metadata.json
```

For alternating HF subprograms, subprogram-level activation matrices may be cached, but the executable analysis uses the max-reduced `A_side_i(l)` and averaged `X_HF_OSS_i(l)` variables documented above.

For LOOCV fold `h`, derive training-fold coverage by subtraction:

```text
S_tau(l, i) = I[X_HF_i(l) > tau]
Coverage_tau_all(l) = sum_i S_tau(l, i)
Coverage_tau_fold_h(l) = Coverage_tau_all(l) - S_tau(l, h)
F_candidate_tau_fold_h = {l : Coverage_tau_fold_h(l) >= 5}
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

The primary claim requires dTOR primary performance, PPMI/MGH cross-connectome consistency, transparent label enrichment, and clear separation from the plain connected-streamline control.



If the map appears stable but has `Q2 <= 0` or does not improve MAE/RMSE over the `Y_base`-only baseline, interpret the result as:

```text
stable_nonpredictive normative HF fiber profile
```

This status can support a hypothesis about a reproducible fiber-level stimulation pattern, but it does not validate `NetFiberScore` as a patient-level counterfactual HF efficacy model. In downstream ULF analysis, a `DeltaHFScore` derived from this source must be labeled as an unstable generated covariate and used only as sensitivity, with no-DeltaHF as the interpretive primary branch.

High-tau/high-Coverage post-hoc scan results may define candidate high-dose core streamline profiles, but they do not replace the original tau800/Coverage>=5 primary branch unless they pass explicit post-selection validation and are recorded as Level 4.

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

Exposure sidecars are connectome- and branch-specific, not scale-specific, unless scale-specific subject inclusion differs. When two scales use the same valid subjects, they reuse the same exposure sidecars, candidate masks, plain touched-streamline background, endpoint labels, density lookup tables, and OSS activation sidecars. If a scale has missing subjects, create a subject-subset view rather than resampling fibers.

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
SweetPeak5_i       = patient-level top 5% mean over SweetWeighted_i(l)
SourPeak5_i        = patient-level top 5% mean over SourWeighted_i(l)
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
candidate_tau800_fold_01_bool ... candidate_tau800_fold_16_bool
candidate_tau1500_fold_01_bool ... candidate_tau1500_fold_16_bool
candidate_tau800_union_of_folds_bool
candidate_tau1500_union_of_folds_bool
```

`union_of_folds` may restrict IO, OSS activation, labeling, and density precomputation. Each fold must still use its own fold-specific candidate mask.

### OSS Candidate-First Activation

OSS-DBS activation is computed only for the union of peak E-field candidate fibers required by the executable OSS branch:

```text
F_candidate_tau800_union_of_folds
F_candidate_tau1500_union_of_folds, if sensitivity is requested
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
Stage 5: prediction-validity classification and plain-control role assignment
Stage 6: optional post-hoc tau/Coverage threshold scan
Stage 7: optional max-stat or nested/adaptive validation for selected post-hoc candidate
Stage 8: formal dTOR permutation for the resolved primary branch
Stage 9: formal dTOR bootstrap for the resolved primary branch
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

## Execution Priority And Gatekeeping

The normative connectome fiber analysis must be executed as a gated sequence. This section applies only to the HF-only 3m normative connectome fiber-level model and does not apply to direct voxel models.

Current executable branch families:

```text
primary:
  peak_efield_tau800_cov5_primary

sensitivity:
  peak_efield_tau1500_cov5_sensitivity
  top1500_top500_sensitivity
  ossdbs_activation_sensitivity

posthoc_candidate_search:
  posthoc_tau_coverage_threshold_scan

control:
  plain_connected_streamline_control
```

Current connectome roles:

```text
PPMI 85 (Ewert 2017)          observed figure-grade robustness
MGH-USC HCP 32 (Horn 2017)    observed figure-grade robustness
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

Any legacy `cov3` or `EFieldCoverage>=3` rule is non-executable unless the model document is explicitly revised again. OLS ANCOVA remains a future supplemental estimator and is not run. FDR, labels, density maps, q-thresholded maps, and display fibers are QC/display outputs only; they do not define `F+`, `F-`, or `NetFiberScore`.

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
lock post-hoc tau/Coverage threshold-scan grid
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

Enter Round 1 only if:

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

Failure means stop before sidecar generation or LOOCV.

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

Enter Round 2 only if:

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

Failure means stop and fix sidecar, coverage, rank, top-k tie policy, or dTOR chunking.

### Round 2: Primary Observed Run, Total Scale

Purpose: run the lowest-cost observed primary branch and check for non-degenerate behavior.

Run:

```text
scale = MDS-UPDRS III score
branch = peak_efield_tau800_cov5_primary
connectome order = PPMI observed -> MGH observed -> dTOR observed
```

For each connectome compute:

```text
full-sample rho_HF / M_HF
F+ top 1%
F- top 0.5%
SweetPeak5
SourPeak5
NetFiberScore
LOOCV prediction
covariate-only baseline comparison
basic mapping QC
```

Write numeric core outputs first:

```text
normative_HF_fiber_weights.csv
normative_HF_fiber_scores.csv
normative_HF_fiber_loocv_predictions.csv
normative_HF_fiber_mapping_qc.json
normative_HF_fiber_generation_manifest.json
```

Delay `.tck` display, density maps, endpoint labels, FDR maps, q-thresholded maps, and label enrichment until numeric QC passes.

Enter Round 3 only if:

```text
at least dTOR primary observed LOOCV completes
each LOOCV fold has non-empty F_candidate_tau800
rho_HF is not all NaN
NetFiberScore has nonzero variance
held-out prediction is not constant
final model is fit
LOOCV Spearman / Pearson / MAE / RMSE / Q2 are finite
mapping_qc.json has no fatal error
```

Soft warnings:

```text
dTOR observed looks technically unstable
PPMI/MGH and dTOR have completely unexplained direction conflict
Q2 is extremely worse than baseline-only
```

Failure means fix tau800/Coverage>=5/e-field sampling, exposure variance, rank ties, top-k reducer, dTOR chunking, fiber ids, or sidecar alignment before running sensitivity or formal branches.

### Round 3: Primary Observed Run, Axial Scale

Purpose: cover the second default first-pass scale while reusing exposure sidecars.

Run:

```text
scale = MDS-UPDRS III axial score
branch = peak_efield_tau800_cov5_primary
connectome order = PPMI observed -> MGH observed -> dTOR observed
```

Run the same observed outputs as Round 2.

Enter Round 4 if:

```text
axial Y_post / Y_base join succeeds
valid subjects match sidecar subject order, or a legal subject-subset view exists
candidate masks are non-empty
NetFiberScore is not constant
LOOCV prediction is fit
```

If axial is missing, low variance, or technically degenerate, mark it as scale-specific failed/not interpretable. Total score may continue. If both total and axial fail, stop the mainline.

### Round 4: Plain Connected-Streamline Control

Purpose: test whether the outcome-filtered fiber model is merely stimulation burden, lead placement, or connectome density.

Run for scales/connectomes that passed observed gates:

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

Enter Round 5 only if:

```text
PlainExposureTop5 is computable
plain model is fit
joint model is not singular
NetFiberScore and PlainExposureTop5 are not perfectly collinear
```

Recommended collinearity flags:

```text
|corr(NetFiberScore, PlainExposureTop5)| < 0.85 = ideal
0.85 to 0.95 = high collinearity warning
>= 0.95 = severe collinearity warning
```

If plain control fully explains the primary branch, the main branch may continue as a minimal formal report, but interpretation is downgraded to stimulation burden / placement-associated and OSS/jitter are not recommended.

### Round 5: dTOR Primary Smoke Permutation And Bootstrap

Purpose: test full-process resampling before formal `B=10000`.

Run only:

```text
connectome = dTOR
branch = peak_efield_tau800_cov5_primary
scales = scales that passed Round 2/3
Freedman-Lane smoke permutation B=1000
subject-level smoke bootstrap B=1000
seed = 42
```

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

Enter Round 6 only if:

```text
B=1000 permutation completes
B=1000 bootstrap completes
plus-one p is computable
bootstrap finite count distribution is interpretable
there are not many empty F_candidate folds
there are not many all-NaN / degenerate maps
runtime profile indicates B=10000 is feasible
```

Do not use smoke `p < 0.05` as a hard gate. If smoke technically fails, stop and fix resampling, chunking, top-k, or rank cache. If smoke technically passes but results are fully degenerate, either stop formal as pre-specified futility or run formal only for total scale.

### Round 6: Cheap Observed Sensitivity

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

Enter Round 7 only if:

```text
tau1500 branch completes, or records candidate-empty / threshold-too-strict
top1500/top500 branch completes
LOOCV outputs are finite
mapping QC is interpretable
```

Soft gate:

```text
tau800 and tau1500 are directionally consistent, or differences are explained by sparse coverage
top1500/top500 does not fully reverse the top1%/top0.5% mainline
dTOR and PPMI/MGH have directionally or anatomically interpretable consistency
```

If tau1500 is empty, record high-threshold sensitivity empty; this is not a technical failure. If top1500/top500 fully reverses the mainline, mark the result top-k dependent and downgrade interpretation.


### Round 6.5: Prediction-Validity Classification And Optional Post-Hoc Threshold Scan

Purpose: separate stable-map behavior from patient-level predictive validity, and optionally search for a high-dose/high-coverage core-fiber candidate.

First classify the original tau800/Coverage>=5 branch:

```text
predictive_valid
stable_nonpredictive
failed_unstable
```

Also assign:

```text
hf_norm_fiber_burden_dominated
plain_control_incremental_status
selected_fiber_stability_summary
delta_hfscore_allowed_role
```

If the original branch is `predictive_valid`, it remains the locked primary HF source for downstream ULF. The post-hoc threshold scan may still be run as exploratory robustness, but it cannot replace the original branch.

If the original branch is `stable_nonpredictive`, export its finite map/support metadata for audit and ULF sensitivity only. It must not be used as a validated `DeltaHFScore` source. In this state, the ULF no-DeltaHF branch is the interpretive primary branch.

If the original branch is `failed_unstable`, do not run heavy formal resampling unless explicitly required for a minimal fragility report. ULF may still proceed through no-DeltaHF if ULF inputs are valid.

Optional threshold scan:

```text
run dTOR full tau x Coverage scan
run PPMI/MGH observed robustness for selected and neighboring dTOR cells
assign Level 0-4 candidate status
```

Proceed to max-stat permutation or nested/adaptive validation only if the selected dTOR cell is Level 3 or better and the result is not burden-dominated.

### Round 7: dTOR Primary Formal Permutation And Bootstrap

Purpose: generate the core statistical evidence for the current document.

Run only:

```text
connectome = dTOR
branch = peak_efield_tau800_cov5_primary
scales = scales that passed smoke and sensitivity hard gates
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

Enter Round 8 only if:

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

If formal technically fails, do not run OSS, jitter, or final display. If formal completes but is negative, proceed only to minimal display/report and do not use OSS/jitter as mechanism strengthening.

### Round 8: OSS-DBS Activation Sensitivity

Purpose: test whether the peak E-field fiber profile remains interpretable under pathway/axon activation variables. OSS is sensitivity, not primary.

Run:

```text
oss_model_set = primary_locked
axon_model
axon_diameter_um
n_nodes
waveform
frequency_Hz
pulse_width_us
amplitude
tissue_model
conductivity_model
activation_output
oss_parameter_manifest.json
```

OSS candidate rule:

```text
inherit F_candidate_tau800 from peak E-field branch
do not redefine candidates by OSS activation
```

Generate:

```text
X_oss_float32_fiber_major.npy
PlainOSSActivated_bool.npy
oss_activation_sidecar_metadata.json
```

Run order:

```text
PPMI / ossdbs_activation_sensitivity / observed LOOCV
MGH / ossdbs_activation_sensitivity / observed LOOCV
OSS plain activation control

then, only if PPMI/MGH are technically normal:
  dTOR / ossdbs_activation_sensitivity / observed LOOCV
  dTOR / OSS smoke permutation B=1000
  OSS plain activation control
```

Write:

```text
normative_HF_fiber_oss_parameter_manifest.json
normative_HF_fiber_oss_activation_matrix_summary.csv
normative_HF_fiber_oss_loocv_predictions.csv
normative_HF_fiber_oss_permutation_summary.csv
normative_HF_plain_oss_activation_summary.csv
normative_HF_plain_oss_activation_model_comparison.csv
```

Enter Round 9 only if:

```text
OSS parameter manifest is locked
OSS sidecar candidate fiber ids align with peak branch candidate ids
OSS activation matrix is not all NaN
OSS activation matrix is not all zero
NetFiberScore_OSS has nonzero variance
OSS LOOCV is fit
OSS B=1000 smoke permutation completes
PlainOSSActivationTop5 is computable
OSS joint control model is fit
```

Soft support:

```text
corr(NetFiberScore_OSS, NetFiberScore_peak) > 0
F+_OSS and F+_peak have nonzero overlap
selected density / label summary is partly consistent with peak branch
OSS plain activation control does not fully replace NetFiberScore_OSS
```

If OSS activation is all zero or mostly tied, mark OSS as failed sensitivity. If OSS and peak branch fully disagree, interpret the result as activation-model dependent. If OSS plain activation fully explains the result, downgrade mechanism interpretation to activation burden.

### Round 9: dTOR Jitter QC

Purpose: test dTOR primary spatial robustness.

Run only:

```text
connectome = dTOR
branch = peak_efield_tau800_cov5_primary
scale = scales with completed formal primary result
```

Level 1:

```text
jitter_level_1_selected_display
selected F+ / F- overlap
display fiber robustness
selected density correlation
```

Level 2, only if Level 1 is technically valid:

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

Enter Round 10 only if:

```text
jitter outputs are writable
jitter selected overlap is computable
jitter density correlation is computable
model similarity is computable
there are no all-empty jitter runs
```

If Level 1 technically fails, do not run Level 2. If Level 1 passes but is unstable, skip Level 2 and label the final result spatially sensitive. If both levels are stable, use them as spatial robustness support.

### Round 10: Display, FDR, Labels, Density, And Cross-Connectome Summaries

Purpose: generate display and interpretation outputs after numeric branches are locked. Display, FDR q-values, q-thresholded density maps, and label outputs never define the primary model and never enter `NetFiberScore`.

Generate for completed branches:

```text
top 1% positive fibers
top 0.5% sour fibers
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
normative_HF_fiber_unthresholded_weighted_density.nii.gz
normative_HF_fiber_positive_weighted_density.nii.gz
normative_HF_fiber_negative_weighted_density.nii.gz
normative_HF_fiber_neglogp_density.nii.gz
normative_HF_fiber_qvalue_summary.csv
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
FDR / label / display outputs are not used to select the primary model
label enrichment uses the plain touched-streamline background
PPMI/MGH manifests record observed_only_connectome_robustness
dTOR primary manifest records formal permutation/bootstrap status
OSS manifest records smoke-only status
unrun branches record explicit not-run reason
```

### Recommended Minimal Execution Path

The most resource-conscious path that still covers the mainline and planned sensitivity hierarchy is:

```text
1. Round 0-1:
   freeze document/inputs, build sidecars, run equivalence tests

2. Round 2:
   total scale tau800 primary observed
   PPMI -> MGH -> dTOR

3. Round 3:
   axial scale tau800 primary observed
   PPMI -> MGH -> dTOR

4. Round 4:
   plain connected-streamline control

5. Round 5:
   dTOR tau800 primary smoke permutation/bootstrap B=1000

6. Round 6:
   tau1500 sensitivity + top1500/top500 sensitivity observed

7. Round 7:
   dTOR tau800 primary formal permutation/bootstrap B=10000

8. Round 8:
   OSS-DBS sensitivity, PPMI/MGH first, then dTOR, B=1000 only

9. Round 9:
   dTOR jitter QC

10. Round 10:
   display / FDR / labels / cross-connectome summaries
```

The core principle is to prove `peak_efield_tau800_cov5_primary` is technically valid on total and axial scales, use plain control to separate outcome-filtered fibers from stimulation burden, run dTOR formal inference, and only then invest in OSS, jitter, and display-layer outputs.
