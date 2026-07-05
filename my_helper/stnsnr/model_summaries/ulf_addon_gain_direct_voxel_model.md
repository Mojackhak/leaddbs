# HF-Adjusted ULF-Only Add-On Gain Direct Voxel-Level Model

## Research Question

Which ultra-low-frequency stimulation territory voxels have ULF-only exposure associated with additional clinical benefit after ULF stimulation is added to HF stimulation, after adjusting for the patient's HF clinical state and model-predicted change in HF efficacy?

This is a direct local ULF-only add-on sweet-spot model. It does not define the main question as an anatomic SNr effect. The STN/SNr and peri-STN/SNr region is treated as one stimulation territory, with HF and ULF components separated by stimulation frequency and exposure overlap.

Frequency definitions:

```text
HF  = high-frequency stimulation component, frequency_Hz >= 100
ULF = ultra-low-frequency stimulation component, frequency_Hz <= 50
```

Voxels co-activated by HF and ULF are attributed to the HF adjustment model and are excluded from the primary ULF-only predictor.

## Endpoint

Two endpoint families are modeled separately.

Chronic endpoint:

```text
Y_post = raw HF+ULF 3-month clinical score
Y_HF   = raw HF-only 3-month clinical score for the same scale/domain
DeltaHFScore = predicted change in HF efficacy between HF+ULF programming and HF-only programming
```

Immediate endpoint:

```text
Y_post = raw HF+ULF immediate clinical score
Y_HF   = raw HF-only 3-month clinical score for the corresponding motor scale/domain
DeltaHFScore = predicted change in HF efficacy between HF+ULF immediate programming and HF-only programming
```

The primary estimand is:

```text
HF-adjusted ULF-only add-on gain
```

Default first-pass endpoints:

```text
MDS-UPDRS III total chronic HF+ULF 3-month score
MDS-UPDRS III total immediate HF+ULF score, if available
```

Raw scores come from the raw clinical table used by the HF direct voxel model:

```text
/Users/mojackhu/Research/STNSNr/summary/cohort/subj/subject_effect_origin.xlsx
```

Clinical rows are joined to imaging by `ID` (`SNr003`, `SNr006`, etc.). Improvement-rate tables are not used by this model. Scale direction is read from the same internal direction table as the HF direct voxel model; unknown scales must provide an explicit higher-is-better or lower-is-better direction before the run starts.

## Inputs

- Stimulation parameter audit source:

  ```text
  /Users/mojackhu/Research/STNSNr/summary/cohort/subj/followup_stimulation.xlsx
  sheet = Contact Parameters
  ```

  This workbook is used to audit HF and ULF component identity, frequencies, pulse widths, amplitudes, sides, contacts, and phase labels. Existing e-fields are treated as accepted inputs after prior manual/clinical QC. The current ULF direct voxel analysis does not automatically create missing e-fields.

- HF-only E-field per side from the pre-ULF HF phase, used to compute the reference HF score.

- HF component E-field and ULF component E-field per side from HF+ULF programming, used to compute `DeltaHFScore` and the ULF-only predictor.

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

  `STNSNrplus` is used only for anatomical overlay, territory coverage, and QC background. It is not intersected with `Omega_ULF_tau` and is not the statistical candidate mask.

- Left/right homology transform:

  ```text
  helpers/ea_flip_lr_nonlinear.m
  templates/space/MNI152NLin2009bAsym/fliplr/{Composite,InverseComposite}.nii.gz
  ```

  All left/right flipping in this model uses `ea_flip_lr_nonlinear` with the Lead-DBS default interpolation behavior.

Minimum e-field checks: required paths must exist, subject/side/component/phase matches must be unique, files must be raw `sim-efield`, and units must be recorded as `V/m`. Missing or multiply matched e-fields fail the endpoint/run. Subjects are not silently excluded and missing e-fields are not automatically created.

## Feature Construction

Use the right-hemisphere MNI brainmask grid as the canonical statistical grid. Left-sided HF and ULF component fields are flipped into right space with `ea_flip_lr_nonlinear`. Right-sided fields are sampled on the same right canonical grid.

For each subject, side, and endpoint phase:

```text
E_HF_R_i(v)       = right HF component e-field
E_HF_L_to_R_i(v)  = left HF component e-field flipped to right canonical space
E_ULF_R_i(v)      = right ULF component e-field
E_ULF_L_to_R_i(v) = left ULF component e-field flipped to right canonical space
```

Same-side alternating subprograms are handled by component:

```text
E_HF_side_i(v)  = voxel-wise maximum over same-side HF subprograms
E_ULF_side_i(v) = voxel-wise maximum over same-side ULF subprograms
```

Interleaving is not modeled as simultaneous double-cathode stimulation. If a clinical condition contains synchronous mixed HF+ULF programming and component-specific fields are generated by turning on only the contacts assigned to one frequency component, the manifest must label those fields as component-specific proxies.

Patient-level bilateral component exposure:

```text
E_HF_component_i(v) =
  (E_HF_R_i(v) + E_HF_L_to_R_i(v)) / 2

E_ULF_component_i(v) =
  (E_ULF_R_i(v) + E_ULF_L_to_R_i(v)) / 2
```

Frequency only classifies the component as HF or ULF. Exposure is not scaled by frequency or pulse width in the primary direct voxel analysis.

Sparse candidate construction:

```text
candidate_threshold = 180 V/m
Candidate_ULF(v) = any valid subject has E_ULF_component_i(v) > 180 V/m
```

For each tau:

```text
tau_primary = 200 V/m
tau_sensitivity = {180, 220} V/m

HF_active_i(v)  = E_HF_component_i(v)  > tau
ULF_active_i(v) = E_ULF_component_i(v) > tau

X_ULF_only_i(v) =
  E_ULF_component_i(v), if ULF_active_i(v) and not HF_active_i(v)
  0,                   otherwise

Coverage_ULF_tau(v) = sum_i I[X_ULF_only_i(v) > tau]
Omega_ULF_tau = {v in Candidate_ULF : Coverage_ULF_tau(v) >= 5}
```

Continuous `X_ULF_only_i(v)` values are used for modeling inside `Omega_ULF_tau`; `tau` is used to define component activity, HF-overlap exclusion, coverage, and QC. Voxels with both HF and ULF activation are excluded from the ULF predictor and are represented in:

```text
direct_voxel_ULF_only_HF_overlap_exclusion_mask.nii.gz
```

Coverage masks, voxel maps, ULF scores, `DeltaHFScore`, and validation predictions are computed inside each LOOCV training fold. The held-out patient never contributes to that fold's `Omega_ULF_tau`, ULF voxel map, or HF adjustment map.

### DeltaHFScore

The model-matched HF adjustment comes from the HF direct voxel model:

```text
V_HF_score = Omega_HF_tau intersect valid M_HF voxels
n_valid_HF_score_voxels = |V_HF_score|

S_HF_voxel(E)_i =
  sum_{u in V_HF_score} E_i(u) * M_HF(u)
  / n_valid_HF_score_voxels

DeltaHFScore_3m_i =
  S_HF_voxel(E_HF_component, HF+ULF 3m)_i
  - S_HF_voxel(E_HF_only, HF-only 3m)_i

DeltaHFScore_immediate_i =
  S_HF_voxel(E_HF_component, HF+ULF immediate)_i
  - S_HF_voxel(E_HF_only, HF-only 3m)_i
```

`DeltaHFScore` is not assigned a fixed biological scaling coefficient before modeling. It may be z-scored within training folds for numerical stability; its regression coefficient estimates its association with outcome. In LOOCV, `DeltaHFScore` for the held-out patient must be computed from the training-fold HF map, not a full-sample HF map.

## Statistical Model

### Primary Estimator: Covariate-Adjusted Partial Spearman

For each endpoint and voxel `v`, use rank-residual partial Spearman with average ranks for ties:

```text
rho_ULF(v) =
  corr(
    resid(rank(Y_post_i)          ~ rank(Y_HF_i) + rank(DeltaHFScore_i)),
    resid(rank(X_ULF_only_i(v))   ~ rank(Y_HF_i) + rank(DeltaHFScore_i))
  )
```

Degenerate voxels with zero ULF-only exposure variance, zero rank variance, or zero residualized exposure variance are assigned `rho_ULF(v)=NaN` and excluded from `ULFScore_mean_main`.

Benefit-oriented map:

```text
M_ULF(v) = -rho_ULF(v)   for lower-is-better scales
M_ULF(v) =  rho_ULF(v)   for higher-is-better scales
```

Positive `M_ULF(v)` consistently means ULF-only sweet or benefit-associated. Negative `M_ULF(v)` means ULF-only sour or worse-outcome-associated.

### DeltaHFScore Sensitivity Estimator

The main sensitivity estimator removes `DeltaHFScore` but keeps the current HF clinical state:

```text
rho_ULF_noDeltaHF(v) =
  corr(
    resid(rank(Y_post_i)        ~ rank(Y_HF_i)),
    resid(rank(X_ULF_only_i(v)) ~ rank(Y_HF_i))
  )
```

This branch is used to report how much the ULF map depends on the model-derived HF adjustment. It is not the primary branch.

### Optional Supplemental Estimator: OLS ANCOVA

OLS ANCOVA is retained as an optional future supplemental estimator. It is not run in the current executable analysis and does not generate output files in this run.

```text
Y_post_i = alpha_v
         + theta_ULF(v) * X_ULF_only_i(v)
         + beta_v      * Y_HF_i
         + gamma_v     * DeltaHFScore_i
         + error_i,v
```

If enabled in a future run, the OLS estimator should generate the same output family under an `ols_ancova/` estimator directory. Its `direct_voxel_ULF_only_coef.nii.gz` would store `theta_ULF(v)`, whereas the current `partial_spearman/` coefficient file stores `rho_ULF(v)`.

### Patient-Level Score

Primary patient-level ULF-only sweet-spot score:

```text
V_score = Omega_ULF_tau intersect valid M_ULF voxels
n_valid_score_voxels = |V_score|

ULFScore_mean_main_i =
  sum_{v in V_score} X_ULF_only_i(v) * M_ULF(v)
  / n_valid_score_voxels
```

This is the primary ULF-only prediction score. It is a voxel-count-normalized, voxel-correlation-weighted mean ULF-only exposure over the fixed scoring voxel set for the corresponding full-sample map or LOOCV training fold. It is not divided by `sum(X)` and is not multiplied by voxel volume. If `V_score` is empty, the branch/fold fails QC instead of producing a score. If a subject/fold has no ULF-only exposure in a non-empty valid scoring voxel set, `ULFScore_mean_main_i` is recorded as `0`.

Final prediction model:

```text
Y_post_i = alpha
         + delta * ULFScore_mean_main_i
         + beta  * Y_HF_i
         + gamma * DeltaHFScore_i
         + error_i
```

Covariate-only baseline:

```text
Y_post_i = alpha
         + beta  * Y_HF_i
         + gamma * DeltaHFScore_i
         + error_i
```

No-DeltaHF sensitivity baseline:

```text
Y_post_i = alpha
         + beta * Y_HF_i
         + error_i
```

The prediction model is fit on the raw post-score scale. The primary validation statistic remains rank-based LOOCV Spearman rho.

Missing-data rule: missing `Y_post`, missing `Y_HF`, missing `DeltaHFScore`, or failed e-field availability fails the endpoint/run after QC. For configurable future endpoints, the endpoint is skipped if the valid sample size falls below 12.

## Validation

- Model chronic 3-month and immediate endpoints separately.
- Use leave-one-patient-out cross-validation with no inner hyperparameter tuning.
- In each outer fold, rebuild the HF direct voxel map needed for `DeltaHFScore`, compute fold-specific `DeltaHFScore`, rebuild `Omega_ULF_tau`, fit the ULF-only voxel map, compute training and held-out `ULFScore_mean_main`, and fit the final prediction model using only training patients.
- Compare against the covariate-only baseline `Y_post ~ Y_HF + DeltaHFScore`.
- Report the no-DeltaHF sensitivity model `Y_post ~ ULFScore_mean_main + Y_HF`.
- Primary validation statistic: LOOCV Spearman rho between held-out predictions and held-out raw outcomes.
- Secondary metrics: LOOCV Pearson `r`, MAE, RMSE, and `Q2` on the original raw outcome scale.
- Define `Q2` relative to the covariate-only baseline:

  ```text
  Q2 = 1 - SSE_ULFScore_model / SSE_covariate_only
  ```

- Patient-level Freedman-Lane permutation uses `B=10000` and random seed `42` for the formal primary ULF branch. Smoke/exploratory runs use `B=1000`. Formal permutation is run only for the primary `tau200/partial_spearman` chronic endpoint branch unless the immediate endpoint is explicitly promoted to co-primary.
- For each permutation, fit the nuisance model `Y_post ~ Y_HF + DeltaHFScore`, permute nuisance residuals, reconstruct `Y*`, and rerun the full LOOCV pipeline including HF adjustment, ULF coverage, ULF map, `ULFScore_mean_main`, and prediction. The primary permutation statistic is LOOCV Spearman rho.
- Permutation p value is plus-one two-sided:

  ```text
  p = (1 + count(|stat_perm| >= |stat_obs|)) / (B + 1)
  ```

- Subject-level bootstrap uses `B=10000` and seed `42` for the formal primary branch. Smoke/exploratory runs use `B=1000`. Each bootstrap resample reruns the full map-building process, including `DeltaHFScore`, `Omega_ULF_tau`, and `direct_voxel_ULF_only_bootstrap_se.nii.gz` stores voxel-wise standard deviation of the estimator map.

For non-primary executed branches (`tau180/partial_spearman`, `tau220/partial_spearman`, no-DeltaHF sensitivity, and immediate endpoints unless co-primary), LOOCV is still run, but formal permutation/bootstrap outputs are not generated. Their manifests and QC JSON files must record:

```text
resampling_status = not_run_nonprimary
resampling_reason = formal resampling restricted to primary tau200/partial_spearman chronic branch
```

## Execution Structure

The later code implementation should keep image preprocessing and statistical postprocessing separated.

MATLAB/Lead-DBS preprocessing:

- discover and availability-check required HF-only, HF-component, and ULF-component e-fields;
- classify components by frequency (`HF >= 100 Hz`, `ULF <= 50 Hz`);
- combine same-side same-frequency alternating subprograms by voxel-wise maximum;
- call `ea_flip_lr_nonlinear` for all left/right flips;
- compute left/right flip deformation audit metrics and record warnings without automatic exclusion;
- sample HF and ULF component exposure into the right-hemisphere MNI brainmask candidate grid;
- write a MAT v7 design matrix and optional compressed NPZ mirror.

Required design matrix schema:

- `X_ULF_only(subject x candidate_voxel)` continuous ULF-only exposure;
- `E_HF_component(subject x candidate_voxel)` continuous HF component exposure used for overlap exclusion and `DeltaHFScore`;
- candidate voxel `ijk` and MNI `xyz_mm`;
- NIfTI affine/header reference;
- `subject_id`, source e-field paths, side metadata, component labels, frequency labels, and clinical raw values;
- tau/candidate metadata, HF-overlap exclusion metadata, flip metadata, and jitter metadata placeholders.

Python postprocessing in the `leaddbs` Conda environment:

- read the MAT v7 design matrix or optional NPZ mirror;
- construct `Omega_ULF_tau` inside each fold;
- compute fold-specific HF direct voxel maps and `DeltaHFScore`;
- run partial Spearman map fitting, LOOCV, permutation, bootstrap, and display output generation;
- write CSV, JSON, NIfTI maps, and figures.

Default parallelism follows the HF direct voxel model:

```text
MATLAB preprocessing workers: 8
Python jobs: 14
seed: 42
```

## Downstream Visualization And Outputs

Output root:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/<tau_slug>/partial_spearman/
```

Primary branch:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau200/partial_spearman/
```

Sensitivity branches:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau180/partial_spearman/
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau220/partial_spearman/
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau200/partial_spearman_no_delta_hf/
```

Required outputs:

```text
direct_voxel_ULF_only_coverage.nii.gz
direct_voxel_ULF_only_coef.nii.gz
direct_voxel_ULF_only_sweet_sour.nii.gz
direct_voxel_ULF_only_stability.nii.gz
direct_voxel_ULF_only_bootstrap_se.nii.gz
direct_voxel_ULF_only_scores.csv
direct_voxel_ULF_only_loocv_predictions.csv
direct_voxel_ULF_only_permutation_summary.csv
direct_voxel_ULF_only_HF_overlap_exclusion_mask.nii.gz
direct_voxel_ULF_only_mapping_qc.json
direct_voxel_ULF_only_generation_manifest.json
```

`direct_voxel_ULF_only_bootstrap_se.nii.gz` and `direct_voxel_ULF_only_permutation_summary.csv` are generated only for the primary branch. Non-primary branches omit these files and record `not_run_nonprimary` in their manifest and QC JSON.

Output semantics:

- `direct_voxel_ULF_only_coverage.nii.gz` stores `Coverage_ULF_tau(v)=sum_i I[X_ULF_only_i(v)>tau]`. Use `int16`.
- `direct_voxel_ULF_only_coef.nii.gz` stores `rho_ULF(v)` for the executed `partial_spearman/` estimator. Optional future OLS outputs would store `theta_ULF(v)`.
- `direct_voxel_ULF_only_sweet_sour.nii.gz` stores benefit-oriented `M_ULF(v)`. Positive values indicate ULF-only benefit-associated voxels.
- `direct_voxel_ULF_only_stability.nii.gz` stores LOOCV training-fold direction stability of `M_ULF(v)>0` or `M_ULF(v)<0`, depending on display class. It is not a p value.
- `direct_voxel_ULF_only_bootstrap_se.nii.gz` stores full-process bootstrap standard deviation of the estimator map for the primary branch only.
- `direct_voxel_ULF_only_scores.csv` stores patient-level scores, including `ULFScore_mean_main`, `DeltaHFScore`, `Y_HF`, `score_map_source`, `n_valid_score_voxels`, and `is_primary_score`.
- `direct_voxel_ULF_only_loocv_predictions.csv` stores held-out predictions, observed raw outcome, covariate-only prediction, `ULFScore_mean_main`, `DeltaHFScore`, and residuals.
- `direct_voxel_ULF_only_permutation_summary.csv` stores Freedman-Lane permutation summary for the primary branch only.
- `direct_voxel_ULF_only_HF_overlap_exclusion_mask.nii.gz` stores voxels excluded from the ULF-only predictor because both HF and ULF are active at the branch tau.
- `direct_voxel_ULF_only_mapping_qc.json` stores endpoint/tau/estimator QC, including patient inclusion, candidate mask size, coverage distribution, `Omega_ULF_tau` voxel count, HF-overlap exclusion volume, degenerate voxels, NaN handling, zero-exposure score counts, `corr(ULFScore_mean_main, Y_HF)`, `corr(ULFScore_mean_main, DeltaHFScore)`, coefficient signs, collinearity diagnostics, flip deformation audit metrics, and design-matrix dimensions.
- `direct_voxel_ULF_only_generation_manifest.json` stores provenance, parameters, code version, conda environment, package state, random seeds, and runtime profile.

Primary statistical maps are unsmoothed. Display smoothing is generated only after coefficient estimation and must not be used for ULFScore, LOOCV, permutation, bootstrap, or jitter:

```text
display_smooth_fwhm1mm/
display_smooth_fwhm2mm/
```

Display maps should overlay:

```text
ULF-only sweet/sour map
HF-overlap exclusion mask
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
component label and side metadata
```

Empty images, all-NaN images, non-finite values, missing paths, and obvious path/component mismatches are hard failures. Ordinary deformation differences are warnings.

## Spatial Jitter QC Sensitivity

Spatial jitter is a robustness stress test applied to accepted e-field inputs. It is not an automatic localization/normalization QC procedure and is not an input-validity gate. It is run only for the primary ULF branch unless an endpoint is explicitly promoted to co-primary.

```text
formal jitter resamples: B = 1000
smoke jitter resamples:  B = 100
seed: 42
FWHM: 2 mm
sigma: 2 / 2.355 = 0.849 mm
```

For each jitter iteration, draw an independent 3D translation vector for each subject-side HF and ULF component e-field. Apply translation-only e-field resampling with linear interpolation and outside fill value `0`. Then rebuild ULF-only exposure, HF-overlap exclusion, `Omega_ULF_tau`, `DeltaHFScore`, full-sample map, ULF scores, and LOOCV validation metrics.

Do not save every jittered NIfTI map. Save a summary table, map correlation/stability summary, and voxel-wise jitter standard deviation map.

## Reference-Parameter Coverage

The ULF direct voxel model covers the same direct voxel parameter family as the HF direct voxel model where applicable:

```text
raw sim-efield, not sim-efieldgauss
right canonical voxel grid
ea_flip_lr_nonlinear left/right flip
tau = 180 / 200 / 220 V/m
Coverage>=5
baseline/covariate-adjusted partial Spearman
LOOCV
Freedman-Lane permutation for the primary branch
subject-level bootstrap for the primary branch
2 mm FWHM spatial jitter QC
display smoothing FWHM 1 mm and 2 mm, display only
```

Documented-only items for the current ULF direct voxel execution:

```text
Coverage>=6 optional sensitivity: documented only; no current ULF direct voxel outputs
Coverage>=8 / 50% E-field rule: documented only; primary rule remains Coverage>=5
5/7/10-fold CV: documented only; LOOCV is executable
optional OLS supplemental estimator: documented only; not run in the current execution
OSS-DBS: not part of direct voxel; belongs to normative fiber / activation sensitivity
paper-like spatial similarity score sensitivity: not included; ULFScore_mean_main is the primary score
automatic localization / electrode reconstruction QC: not included; prior manual QC is assumed
```

## Interpretation Boundary

This model estimates HF-adjusted ULF-only add-on association. It is not an anatomic SNr gain model. Voxels co-activated by HF and ULF are treated as HF-dominant for the primary analysis, so the ULF map represents regions uniquely recruited by ULF stimulation after accounting for HF clinical state and model-predicted HF efficacy changes.

Because the cohort has `n=16`, the result is hypothesis-generating. A non-significant LOOCV result should not be interpreted as proof that no biological ULF add-on sweet spot exists. The QC report must include the association between `ULFScore_mean_main`, `Y_HF`, and `DeltaHFScore`, plus a basic collinearity diagnostic for the final prediction model.

Interpret as:

```text
After accounting for HF state and modeled HF efficacy changes, additional ULF-only exposure in this territory is associated with better or worse post-HF+ULF outcome.
```

Do not interpret as:

```text
The displayed voxels prove an anatomic SNr-specific causal effect.
```

## Execution Efficiency

The optimized implementation must preserve the logical full-process semantics described above. In particular, LOOCV training folds still define their own HF adjustment map, `DeltaHFScore`, `Omega_ULF_tau`, ULF voxel map, ULF scores, and held-out predictions. Formal Freedman-Lane permutation and subject-level bootstrap still use `B=10000` and seed `42` for the primary branch. Smoke runs use `B=1000` for permutation/bootstrap and `B=100` for jitter.

### Equivalence Contract

Optimization may reuse mathematically invariant cached subcomputations, but it must not use full-sample ranks, full-sample training masks, approximate ranks, adaptive early stopping, changed tau thresholds, changed estimators, or reduced formal resampling counts to gain speed.

Numerical reductions should use `float64` where feasible. Final NIfTI outputs use `float32` for coefficient, sweet/sour, stability, and bootstrap SE maps, and `int16` for coverage and binary/exclusion masks.

### Preprocessing Sidecar Cache

Preferred formal-loop input:

```text
X_ULF_only_float32_voxel_major.npy
E_HF_component_float32_voxel_major.npy
S180_ULF_only_bool.npy
S200_ULF_only_bool.npy
S220_ULF_only_bool.npy
HF_overlap_tau180_bool.npy
HF_overlap_tau200_bool.npy
HF_overlap_tau220_bool.npy
candidate_ijk.npy
candidate_xyz_mm.npy
candidate_mask_metadata.json
```

Voxel-major layout is preferred because voxel chunks are contiguous on disk. MAT and compressed NPZ files may be retained for archival, compatibility, and debugging. Compressed NPZ must not be the primary random-access input inside formal permutation, bootstrap, or jitter loops.

### Coverage And Fold Mask Cache

For each tau, precompute:

```text
S_tau(v, i) = I[X_ULF_only_i(v) > tau]
Coverage_tau_all(v) = sum_i S_tau(v, i)
Coverage_tau_fold_h(v) = Coverage_tau_all(v) - S_tau(v, h)
Omega_ULF_tau_fold_h = {v : Coverage_tau_fold_h(v) >= 5}
```

`HF_overlap_tau*_bool` can be cached because it depends only on accepted HF/ULF component exposures and tau, not on outcome.

### Vectorized Partial Spearman Kernel

For every training fold, ranks are computed within the training set only. Full-sample ranks are prohibited for LOOCV map fitting, permutation map fitting, bootstrap maps, and jitter resamples.

The ULF primary estimator residualizes both outcome and exposure against:

```text
rank(Y_HF_train)
rank(DeltaHFScore_train)
```

The no-DeltaHF sensitivity residualizes against:

```text
rank(Y_HF_train)
```

### Fold-Level Score Operator For Permutation

Formal Freedman-Lane permutation for the primary branch may use a fold-level score operator, but it must remain logically equivalent to recomputing the full ULF map and `ULFScore_mean_main` for every permuted outcome.

Each permutation must have its own:

```text
rho_ULF(v)
M_ULF(v)
V_score
ULFScore_mean_main
held-out prediction
LOOCV statistic
```

### Bootstrap Efficiency

Subject-level bootstrap remains a full-process map stability analysis for the primary branch. It must rebuild bootstrap `DeltaHFScore`, `Omega_ULF_tau`, `rho_ULF`, and `M_ULF`. Bootstrap SE is accumulated by streaming Welford updates. The implementation must not store 10000 bootstrap maps.

### Spatial Jitter Efficiency

Jitter changes e-field geometry. Primary `X`-derived caches are invalid under jitter and must not be reused as if exposure were unchanged. Each jitter iteration must rebuild HF component exposure, ULF component exposure, HF-overlap exclusion, ULF-only exposure, candidate mask, `Omega_ULF_tau`, `DeltaHFScore`, map, scores, and LOOCV metrics.

### Prohibited Speed Shortcuts

Formal runs prohibit:

```text
adaptive permutation early stopping
reduced formal B
changed tau thresholds
changed Coverage>=5 rule
changed estimator
full-sample ranks inside LOOCV/permutation/bootstrap
approximate ranks
using anatomical overlay masks as the analysis mask
dropping requested jitter QC
using total ULF exposure in place of ULF-only exposure
including HF-overlap voxels in the primary ULF predictor
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
    "n_voxels_tau200_mean": null,
    "n_voxels_tau200_min": null,
    "n_voxels_tau200_max": null,
    "n_hf_overlap_tau200_mean": null,
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
fold-specific Omega_ULF_tau
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

## Execution Priority And Gatekeeping

Run the ULF direct voxel analysis as a gatekeeping sequence. Do not run all sensitivity analyses at once.

### Round 0: Input Readiness

Run:

```text
clinical table audit:
  Y_post exists
  Y_HF exists
  DeltaHFScore inputs exist
  ID joins to imaging subject
  scale direction is defined

e-field availability check:
  HF-only pre-ULF e-fields exist
  HF+ULF HF-component e-fields exist
  HF+ULF ULF-component e-fields exist
  all matches are unique
  raw sim-efield is used

component audit:
  HF frequency >= 100 Hz
  ULF frequency <= 50 Hz
  mixed or proxy component fields are labeled
```

Enter Round 1 only if all primary endpoint subjects have complete clinical and e-field inputs, and valid sample size is at least 12.

### Round 1: Preprocessing And Overlap QC

Run preprocessing sidecars and flip audit. Confirm:

```text
X_ULF_only matrix is non-empty
HF_overlap exclusion mask is non-empty or explicitly zero
tau200 Coverage>=5 Omega_ULF is non-empty
each subject has nonzero HF component exposure
each subject has nonzero or explicitly absent ULF-only exposure
```

If ULF-only exposure is empty for most subjects, stop and report that the primary ULF-only predictor is not modelable.

### Round 2: Primary Chronic Observed LOOCV

Run first:

```text
endpoint = MDS-UPDRS III total chronic HF+ULF 3-month score
branch = tau200 / partial_spearman
score = ULFScore_mean_main
covariates = Y_HF + DeltaHFScore
validation = LOOCV
```

Enter Round 3 only if all folds complete, `ULFScore_mean_main` is not constant, held-out predictions are finite, LOOCV rho is positive, `Q2 > 0`, and the ULFScore model improves over `Y_HF + DeltaHFScore`.

Stop if the primary chronic branch is negative, near-constant, or dominated by one high-leverage subject. Do not run `tau180/tau220` to search for a better threshold after primary failure.

### Round 3: Equivalence And Smoke Resampling

Run:

```text
deterministic equivalence test
smoke permutation B=1000
smoke bootstrap B=1000
smoke jitter B=100
```

Enter Round 4 only if optimized and brute-force paths match, smoke resampling runs without artifacts, bootstrap finite-count distribution is acceptable, and jitter does not reverse the signal direction.

### Round 4: Formal Permutation

Run only for the primary chronic branch:

```text
tau200 / partial_spearman
B = 10000
seed = 42
statistic = LOOCV Spearman rho
```

Proceed to bootstrap if the permutation completes, p value is finite, and the observed signal remains positive. If `p_perm > 0.10` and `Q2 <= 0`, stop heavy analyses and produce a minimal exploratory report.

### Round 5: Formal Bootstrap

Run:

```text
tau200 / partial_spearman
B = 10000
seed = 42
```

Proceed only if bootstrap finite counts are acceptable, core sign stability is interpretable, and most bootstrap maps are not empty.

### Round 6: Formal Spatial Jitter

Run:

```text
tau200 / partial_spearman
B = 1000
FWHM = 2 mm
```

If jitter map correlation is near zero or the signal direction reverses, downgrade conclusions to spatially fragile exploratory association.

### Round 7: Tau Sensitivity

Run observed LOOCV only:

```text
tau180 / partial_spearman
tau220 / partial_spearman
```

Do not run formal permutation/bootstrap for tau sensitivity. Interpret tau180/tau220 as robustness checks, not threshold search.

### Round 8: Immediate Endpoint

Run only if the chronic primary branch is interpretable:

```text
endpoint = immediate HF+ULF motor score
branch = tau200 / partial_spearman
validation = observed LOOCV
smoke permutation optional
```

Formal resampling for immediate endpoints requires an explicit decision to treat the immediate endpoint as co-primary.

### Round 9: Display And Final Manifests

Generate display smoothing, bilateral homologous display maps, HF-overlap exclusion overlays, STN/SNr outlines, PDF QC, and final manifests only after statistical branches complete. Display outputs must not feed back into ULFScore, LOOCV, permutation, bootstrap, or jitter.

### Round 10: Optional Future Analyses

Not part of the current executable mainline:

```text
OLS ANCOVA
Coverage>=6
Coverage>=8 / 50% rule
5/7/10-fold CV
OSS-DBS direct voxel analysis
paper-like spatial similarity score
automatic localization / electrode reconstruction QC
```

### Recommended First Batch

The first practical run should cover only:

```text
Round 0
Round 1
Round 2
Round 3 smoke only
```

Concrete first-batch scope:

```text
MDS-UPDRS III total chronic endpoint
tau200
partial_spearman
Coverage>=5
ULF-only exposure
HF-overlap exclusion
DeltaHFScore-adjusted model
ULFScore_mean_main
LOOCV
covariate-only comparison
equivalence test
smoke permutation B=1000
smoke bootstrap B=1000
smoke jitter B=100
basic QC JSON + manifest
```
