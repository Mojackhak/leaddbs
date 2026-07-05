# HF-Only 3m Normative Connectome Fiber-Level Model

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

Candidate rule, matched to the HF direct voxel coverage logic:

```text
tau_primary = 800 V/m
tau_sensitivity = 1500 V/m
Coverage_tau(l) = sum_i I[X_HF_i(l) > tau]
F_candidate_tau = {l: Coverage_tau(l) >= 5}
```

`X_HF_i(l)` is used for candidate definition, fiber-wise association, scoring, LOOCV, and prediction. dTOR exposure and candidate calculations must be chunked; loading the complete dTOR `fibers` matrix or all exposure values into memory is invalid.

The OSS-DBS branch inherits this same peak E-field candidate universe. `X_HF_OSS_i(l)` is introduced only after candidate selection and must not redefine, shrink, or expand `F_candidate_tau`.

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
- Formal Freedman-Lane permutation: `B=10000`, seed `42`, dTOR primary peak-E-field branch only.
- Subject-level bootstrap: `B=10000`, seed `42`, dTOR primary peak-E-field branch only.
- Smoke permutation/bootstrap: `B=1000`, seed `42`.
- Optional OLS ANCOVA is documented for future sensitivity analysis but is not run in the current execution.

PPMI, MGH, and dTOR all produce observed figure-grade outputs. dTOR additionally carries formal permutation, bootstrap, and jitter QC. The Nature paper 5-fold/10-fold CV settings are documented in the reference checklist only; LOOCV is the executable validation design for this `n=16` cohort.

## Sensitivity And Controls

Executable branches:

```text
peak_efield_tau800_primary
peak_efield_tau1500_sensitivity
top1500_top500_sensitivity
ossdbs_activation_sensitivity
plain_connected_streamline_control
```

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

Minimum table semantics:

- `normative_HF_fiber_weights.csv`: `connectome`, `fiber_id`, `tau_v_per_m`, `coverage`, `rho_HF`, `p_uncorrected`, `q_fdr`, `M_HF`, `direction_class`, display/sensitivity flags, and target labels for QC.
- `normative_HF_fiber_scores.csv`: `subject_id`, `score_map_source`, `connectome`, `branch`, `SweetPeak5`, `SourPeak5`, `NetFiberScore`, candidate/selected/peak fiber counts, and `is_primary_score`.
- `normative_HF_fiber_scores.csv` in the OSS branch additionally stores `SweetPeak5_OSS`, `SourPeak5_OSS`, and `NetFiberScore_OSS`.
- `fdr_summary_by_scale.csv`: q-threshold counts and overlap between percentile-selected fibers and q-ranked fibers.
- `normative_HF_fiber_label_enrichment.csv`: enrichment of selected sweet/sour fibers relative to the plain touched-streamline background.
- `normative_HF_fiber_mapping_qc.json`: candidate counts, coverage distribution, degenerate fiber counts, empty-fold failures, FDR method, label summaries, chunking parameters, memory use summaries, OSS-DBS status, and OSS activation-output type.

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
S800_bool.npy                   # X_HF > 800 V/m
S1500_bool.npy                  # X_HF > 1500 V/m
fiber_id.npy
candidate_fiber_metadata.json
```

dTOR must use chunked sidecars:

```text
chunks/
  X_float32_fiber_major_chunk-000001.npy
  S800_bool_chunk-000001.npy
  S1500_bool_chunk-000001.npy
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
