# HF-Only 3m Direct Voxel-Level Model

## Research Question

Which high-frequency stimulation territory voxels have HF-only exposure associated with better 3-month HF-only clinical outcome?

This is a direct local stimulation sweet-spot model. The former STN-only phase is interpreted as HF-only DBS territory, not as an anatomic STN-only model. STN/SNr masks are used for anatomical overlays and coverage description, not for hard assignment of model effects to either nucleus.

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

Raw post and baseline scores come from:

```text
/Users/mojackhu/Research/STNSNr/summary/cohort/subj/subject_effect_origin.xlsx
```

Clinical rows are joined to imaging by `ID` (`SNr003`, `SNr006`, etc.). The improvement-rate table is not used by this model. The scale list is configurable. Scale direction is read from an internal direction table for known scales; unknown scales must provide an explicit higher-is-better or lower-is-better direction before the run starts.

## Inputs

- Stimulation parameter audit source:

  ```text
  /Users/mojackhu/Research/STNSNr/summary/cohort/subj/followup_stimulation.xlsx
  sheet = Contact Parameters
  ```

  This workbook can be used to audit stimulation metadata, but the executable HF direct voxel analysis assumes existing e-fields have already been generated correctly after prior manual/clinical QC. The current run does not automatically create missing e-fields.

- HF-only E-field per side, taken from the Lead-DBS Horn/SimBio FEM output for the `3m/STN` condition:

  ```text
  stimulations/MNI152NLin2009bAsym/<stimlabel>_3m_STN_*/sub-<Subject>_sim-efield_model-simbio_hemi-{L,R}.nii
  ```

  Use the raw `sim-efield` variant, not `sim-efieldgauss`. E-field values stay in Lead-DBS native units of `V/m`. The pipeline only performs a minimum availability check: the path must exist, the subject/side/condition match must be unique, and the file must be the raw `sim-efield`. If a required e-field is missing or has multiple matches, the scale/run fails with a QC error. Subjects are not silently excluded and missing e-fields are not automatically created in this model.

- Alternating `3m/STN` programs are not modeled as simultaneous double-cathode stimulation. Same-side alternating subprogram e-fields are combined by voxel-wise maximum to form one HF-only field per side.

- Canonical reference mask:

  ```text
  templates/space/MNI152NLin2009bAsym/brainmask.nii.gz > 0
  ```

  Candidate voxels are restricted to right-hemisphere voxel centers with MNI world coordinate `x > 0`.

- Anatomical overlay masks:

  ```text
  templates/space/MNI152NLin2009bAsym/atlases/STNSNr-connected regions/{rh,lh}/STNSNrplus.nii.gz
  ```

  `STNSNrplus` is used only for anatomical overlay and coverage/QC background. It is not intersected with `Omega_HF_tau` and is not the statistical candidate mask.

- Left/right homology transform:

  ```text
  helpers/ea_flip_lr_nonlinear.m
  templates/space/MNI152NLin2009bAsym/fliplr/{Composite,InverseComposite}.nii.gz
  ```

  All left/right flipping in this model uses `ea_flip_lr_nonlinear` with the Lead-DBS default interpolation behavior. No custom left/right deformation or manual interpolation replaces this helper.

- Reference methodology files that define the covered parameter family:

  ```text
  /Volumes/VAL/STNSNr/reference/s41593-024-01570-1.pdf
  /Volumes/VAL/STNSNr/reference/41593_2024_1570_MOESM1_ESM.pdf
  /Volumes/VAL/STNSNr/reference/s41467-024-48731-1.pdf
  /Volumes/VAL/STNSNr/reference/41467_2024_48731_MOESM1_ESM.pdf
  ```

## Feature Construction

Use the right-hemisphere MNI brainmask grid as the canonical statistical grid. The left HF e-field is flipped into right space with `ea_flip_lr_nonlinear`, producing `E_L_to_R_i(v)` on the right canonical grid. The right HF e-field is sampled on the same grid as `E_R_i(v)`.

Patient-level bilateral exposure is:

```text
X_HF_only_i(v) = (E_R_i(v) + E_L_to_R_i(v)) / 2
```

This keeps one homologous voxel value per patient and avoids left/right pseudo-replication. Exposure is not scaled by stimulation frequency or pulse width; frequency only classifies the component as HF.

The model does not use a paired-mask membership threshold. In particular, there is no `P_left_to_R`, no `Omega_pair`, and no `membership > 0.5` or `membership > 0.7` rule in the executable HF direct voxel model.

Sparse candidate construction:

```text
candidate_threshold = 180 V/m
Candidate(v) = any valid subject has X_HF_only_i(v) > 180 V/m
```

The candidate mask is used only for sparse matrix construction. It is not the statistical threshold. The full-sample candidate mask can be fixed before LOOCV because it only removes voxels that never reach the lowest sensitivity threshold in any valid subject.

For each tau:

```text
tau_primary = 200 V/m
tau_sensitivity = {180, 220} V/m
Coverage_tau(v) = sum_i I[X_HF_only_i(v) > tau]
Omega_HF_tau = {v in Candidate : Coverage_tau(v) >= 5}
```

Continuous `X_HF_only_i(v)` values are used for modeling inside `Omega_HF_tau`; `tau` is only used to define coverage and QC. `Coverage>=6` and `Coverage>=8` are documented optional sensitivity settings only. The current executable analysis does not generate `Coverage>=6/8` maps, scores, LOOCV predictions, permutation results, or bootstrap results. `Coverage>=8` / 50% E-field coverage from the reference literature is retained in the reference-coverage checklist, but it is not used as the main rule for this `n=16` cohort.

Coverage masks, voxel maps, HF scores, and validation predictions are computed inside each LOOCV training fold. The held-out patient never contributes to that fold's `Omega_HF_tau` or voxel map.

## Statistical Model

### Primary Estimator: Baseline-Adjusted Partial Spearman

For each voxel `v`, use rank-residual partial Spearman with average ranks for ties:

```text
rho_HF(v) =
  corr(
    resid(rank(Y_post_i)       ~ rank(Y_base_i)),
    resid(rank(X_HF_only_i(v)) ~ rank(Y_base_i))
  )
```

No additional covariates are included in the primary model. Degenerate voxels with zero exposure variance, zero rank variance, or zero residualized exposure variance are assigned `rho_HF(v)=NaN` and excluded from HFScore computation.

Benefit-oriented map:

```text
M_HF(v) = -rho_HF(v)   for lower-is-better scales
M_HF(v) =  rho_HF(v)   for higher-is-better scales
```

Positive `M_HF(v)` consistently means sweet or benefit-associated.

### Supplemental Estimator: OLS ANCOVA

Run OLS ANCOVA as a full parallel supplemental analysis:

```text
Y_post_i = alpha_v
         + theta_HF(v) * X_HF_only_i(v)
         + beta_v      * Y_base_i
         + error_i,v
```

The OLS estimator generates the same output family under the `ols_ancova/` estimator directory. Its `direct_voxel_HF_coef.nii.gz` stores `theta_HF(v)`, whereas the primary `partial_spearman/` coefficient file stores `rho_HF(v)`.

### Patient-Level Score

Primary patient-level HF sweet-spot score:

```text
HFScore_sum_i =
  sum_{v in Omega_HF_tau, valid M_HF} X_HF_only_i(v) * M_HF(v)
```

This is the primary analysis score. It is an unnormalized voxel-correlation-weighted total dose exposure. It is not divided by `sum(X)` and is not multiplied by voxel volume; with a fixed isotropic grid, voxel volume only adds a constant scaling factor. If a subject/fold has no exposure in valid scoring voxels, `HFScore_sum_i` is recorded as `0`.

The previous normalized score is retained only as a descriptive field:

```text
HFScore_normalized_descriptive_i =
  sum_{v in Omega_HF_tau, valid M_HF} X_HF_only_i(v) * M_HF(v)
  / sum_{v in Omega_HF_tau, valid M_HF} X_HF_only_i(v)
```

`HFScore_normalized_descriptive_i` is not used for the primary prediction model, LOOCV statistic, permutation, or bootstrap. If its denominator is zero, the descriptive normalized score is recorded as `NaN`.

Final prediction model:

```text
Y_post_i = alpha
         + delta * HFScore_sum_i
         + beta  * Y_base_i
         + error_i
```

The prediction model is fit on the raw post-score scale. The primary validation statistic remains rank-based LOOCV Spearman rho.

Missing-data rule: missing `Y_post`, missing `Y_base`, or failed e-field availability fails the scale/run after QC. For configurable future scales, the scale is skipped if the valid sample size falls below 12.

## Validation

- Use leave-one-patient-out cross-validation with no inner hyperparameter tuning.
- In each outer fold, rebuild `Omega_HF_tau`, fit the voxel map, compute training and held-out HF scores, and fit the final prediction model using only training patients.
- Compare against the covariate-only baseline `Y_post ~ Y_base`.
- Primary validation statistic: LOOCV Spearman rho between held-out predictions and held-out raw outcomes.
- Secondary metrics: LOOCV Pearson `r`, MAE, RMSE, and `Q2` on the original raw outcome scale.
- Define `Q2` relative to the covariate-only baseline:

  ```text
  Q2 = 1 - SSE_HFScore_model / SSE_YBase_only
  ```

- Patient-level Freedman-Lane permutation uses `B=10000` and random seed `42` for the formal primary analysis. Smoke/exploratory runs use `B=1000`. Formal permutation is run only for `tau200/partial_spearman`. For each permutation, fit the nuisance model `Y_post ~ Y_base`, permute the nuisance residuals, reconstruct `Y*`, and rerun the full LOOCV pipeline including coverage, map, `HFScore_sum`, and prediction. The primary permutation statistic is LOOCV Spearman rho.
- Permutation p value is plus-one two-sided:

  ```text
  p = (1 + count(|stat_perm| >= |stat_obs|)) / (B + 1)
  ```

- Subject-level bootstrap uses `B=10000` and seed `42` for the formal primary analysis. Smoke/exploratory runs use `B=1000`. Formal bootstrap is run only for `tau200/partial_spearman`. Each bootstrap resample reruns the full map-building process, including `Omega_HF_tau`, and `direct_voxel_HF_bootstrap_se.nii.gz` stores voxel-wise standard deviation of the estimator map.

For non-primary branches (`tau180/partial_spearman`, `tau220/partial_spearman`, and all `ols_ancova` branches), LOOCV is still run, but formal permutation/bootstrap outputs are not generated. Their manifests and QC JSON files must record:

```text
resampling_status = not_run_nonprimary
resampling_reason = formal resampling restricted to tau200/partial_spearman
```

## Execution Structure

The later code implementation should keep image preprocessing and statistical postprocessing separated:

- MATLAB/Lead-DBS preprocessing:
  - discover and availability-check required HF-only e-fields;
  - combine alternating same-side subprograms by voxel-wise maximum;
  - call `ea_flip_lr_nonlinear` for all left/right flips;
  - compute left/right flip deformation audit metrics and record warnings without automatic exclusion;
  - sample exposure into the right-hemisphere MNI brainmask candidate grid;
  - write a MAT v7 design matrix and, optionally, a compressed NPZ mirror.

- Required design matrix schema:
  - `X(subject x candidate_voxel)` continuous HF exposure;
  - candidate voxel `ijk` and MNI `xyz_mm`;
  - NIfTI affine/header reference;
  - `subject_id`, source e-field paths, side metadata, and clinical raw values;
  - tau/candidate metadata, flip metadata, and jitter metadata placeholders.

- Python postprocessing in the `leaddbs` Conda environment:
  - read the MAT v7 design matrix or optional NPZ mirror;
  - run LOOCV for all generated tau/estimator branches;
  - run formal Freedman-Lane permutation and full bootstrap only for `tau200/partial_spearman`;
  - run OLS supplemental analysis and jitter QC sensitivity;
  - write CSV/JSON outputs, PDF QC figures, and NIfTI maps with `nibabel`;
  - fill candidate vectors back into the right-hemisphere MNI reference grid.

Python statistical postprocessing must run through the `leaddbs` Conda environment, for example with `conda run -n leaddbs python ...` or an activated `leaddbs` shell. Installing, upgrading, or adjusting Python packages inside this environment is acceptable when required for the analysis, but the final package state must be recorded in the run manifest. Record both `conda list --explicit` and `python -m pip freeze` outputs or their paths.

Default resource use should be optimized but reproducible:

```text
MATLAB preprocessing workers: 8
Python statistical jobs: 14
random seed: 42
```

Parallel jobs derive deterministic child seeds from seed `42`. MATLAB preprocessing and Python postprocessing run as separate phases to avoid CPU oversubscription. A smoke mode should use `B=1000` permutation/bootstrap resamples for the primary branch and `B=100` jitter resamples.

Intermediate audit outputs are retained, including right/flipped exposure products, candidate masks, ROI design matrices, manifests, lock files, and completion markers. Completed outputs are skipped by default; force-rerun options should be available.

## Downstream Visualization And Outputs

Output root, one folder per scale, tau, and estimator:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale_slug>/preprocess/
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale_slug>/tau180/partial_spearman/
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale_slug>/tau180/ols_ancova/
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale_slug>/tau200/partial_spearman/   # primary
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale_slug>/tau200/ols_ancova/
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale_slug>/tau220/partial_spearman/
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale_slug>/tau220/ols_ancova/
```

`<scale_slug>` is deterministic: lowercase, non-alphanumeric characters converted to underscores, repeated underscores collapsed, and leading/trailing underscores removed. The original scale column name is recorded in the manifest.

Export per tau/estimator folder:

```text
direct_voxel_HF_coverage.nii.gz
direct_voxel_HF_coef.nii.gz
direct_voxel_HF_sweet_sour.nii.gz
direct_voxel_HF_stability.nii.gz
direct_voxel_HF_bootstrap_se.nii.gz
direct_voxel_HF_scores.csv
direct_voxel_HF_loocv_predictions.csv
direct_voxel_HF_permutation_summary.csv
direct_voxel_HF_mapping_qc.json
direct_voxel_HF_generation_manifest.json
```

`direct_voxel_HF_bootstrap_se.nii.gz` and `direct_voxel_HF_permutation_summary.csv` are generated only for the primary `tau200/partial_spearman` branch. Non-primary branches omit these files and record `not_run_nonprimary` in their manifest and QC JSON.

Output semantics:

- `direct_voxel_HF_coverage.nii.gz` stores `Coverage_tau(v) = sum_i I(X_HF_i(v) > tau)`. Use `int16`.
- `direct_voxel_HF_coef.nii.gz` stores `rho_HF(v)` for `partial_spearman/` and `theta_HF(v)` for `ols_ancova/`. Use `float32`. No per-voxel FDR is applied.
- `direct_voxel_HF_sweet_sour.nii.gz` stores benefit-oriented `M_HF(v)`.
- `direct_voxel_HF_stability.nii.gz` stores the fraction of LOOCV training folds with positive benefit-oriented map value. It is a direction-stability map, not a p-value or thresholded significance map.
- `direct_voxel_HF_bootstrap_se.nii.gz` stores full-process bootstrap standard deviation of the estimator map for the primary branch only.
- `direct_voxel_HF_scores.csv` stores patient-level map matching scores. Required fields include `HFScore_sum_main`, `HFScore_normalized_descriptive`, `exposure_sum_valid_voxels`, `n_valid_score_voxels`, `score_map_source`, and `is_primary_score`. `HFScore_sum_main` is the only primary prediction score.
- `direct_voxel_HF_loocv_predictions.csv` stores held-out LOOCV predictions, including `HFScore_LOOCV`, true outcome, HFScore-model prediction, covariate-only baseline prediction, and residuals.
- `direct_voxel_HF_permutation_summary.csv` stores the Freedman-Lane permutation summary for the primary branch only, including observed LOOCV Spearman rho, plus-one two-sided p value, secondary metrics, and `B`.
- `direct_voxel_HF_mapping_qc.json` stores scale/tau/estimator QC, including patient inclusion, candidate mask size, coverage distribution, `Omega_HF_tau` voxel count, low-coverage warning, degenerate voxels, NaN handling, zero-exposure score counts, `corr(HFScore_sum, Y_base)`, prediction coefficient signs, optional VIF or equivalent collinearity diagnostics, flip deformation audit metrics, and design-matrix dimensions.
- `direct_voxel_HF_generation_manifest.json` stores provenance, including inputs, outputs, parameters, random seed, code version, Conda `leaddbs` environment, Python package state, reference-coverage checklist, and estimator identity.

Primary statistical maps are unsmoothed. Display smoothing is generated only after coefficient estimation and must not be used for HFScore, LOOCV, permutation, or bootstrap:

```text
display_smooth_fwhm1mm/
display_smooth_fwhm2mm/
```

Generate bilateral homologous display NIfTI files for visualization only by flipping the right canonical map to the left side with `ea_flip_lr_nonlinear` and combining the right statistical map with the flipped left display copy. The bilateral display map is not a separate side-specific statistical model.

Generate report-only display masks for the primary branch. These masks are not significance maps and must not be used for scoring, LOOCV, permutation, or bootstrap:

```text
sweet_display_mask:
  M_HF(v) > 0
  positive M_HF(v) within top 10% among positive voxels in Omega_HF_tau
  positive-direction stability >= 0.75

sour_display_mask:
  M_HF(v) < 0
  absolute negative M_HF(v) within top 10% among negative voxels in Omega_HF_tau
  negative-direction stability >= 0.75
```

For sweet display, stability is the fraction of LOOCV training folds with `M_HF(v)>0`. For sour display, stability is the fraction of LOOCV training folds with `M_HF(v)<0`. The anatomical display summary should report display voxels inside `STNSNrplus`, Custom STN, Custom SNr, and outside these masks.

PDF-only QC figures:

```text
coverage histogram
score-vs-outcome scatter
LOOCV observed-vs-predicted scatter
permutation null distribution
bootstrap stability summary
jitter stability summary
```

## Left/Right Flip Deformation Audit

All left/right flips still use `ea_flip_lr_nonlinear`. The flip audit records deformation quality and obvious abnormal values, but ordinary flip differences are warnings only and do not automatically fail the run or exclude subjects.

Record the following fields in `direct_voxel_HF_mapping_qc.json`:

```text
input/output grid and affine
finite voxel count
nonzero voxel count
max, p95, p99, sum
suprathreshold volume at 180, 200, and 220 V/m
intensity-weighted centroid
L-to-R output overlap with the right canonical brainmask
optional roundtrip metrics if generated
```

Empty maps, all-NaN maps, non-finite maps, or obvious path mismatches are input availability/data-integrity failures. Standard interpolation or deformation differences are recorded as warnings only.

## Spatial Jitter QC Sensitivity

Spatial jitter is an optional robustness stress test applied to the already accepted e-field inputs. It is not an automatic localization/normalization QC procedure and is not an input-validity gate. It is run only for the primary `tau200/partial_spearman` analysis.

```text
formal jitter resamples: B = 1000
smoke jitter resamples:  B = 100
FWHM = 2 mm
sigma = 2 / 2.355 = 0.849 mm
```

For each jitter iteration, draw an independent 3D translation vector for each subject-side E-field:

```text
dx, dy, dz ~ Normal(0, sigma^2)
```

Apply translation-only E-field resampling with linear interpolation and outside fill value `0`. Then rebuild the candidate mask, `Omega_HF_tau`, full-sample map, HF scores, and LOOCV validation metrics. Do not save every jittered NIfTI map. Save a summary table, map correlation/stability summary, and a voxel-wise jitter standard deviation map.

## Reference-Parameter Coverage

`direct_voxel_HF_generation_manifest.json` and `direct_voxel_HF_mapping_qc.json` must include a reference-coverage checklist for the local files under `/Volumes/VAL/STNSNr/reference`.

Covered and generated:

```text
raw E-field magnitude model
tau = 180, 200, 220 V/m
LOOCV validation
Freedman-Lane permutation for tau200/partial_spearman
partial Spearman voxel association
OLS supplemental estimator
subject-level bootstrap for tau200/partial_spearman
left/right flip deformation audit
report-only top 10% + stability display masks
2 mm FWHM spatial jitter QC
1 mm and 2 mm display smoothing
```

Covered but not generated as separate HF direct voxel results:

```text
Coverage>=6 optional sensitivity: documented only; no current HF direct voxel outputs
Coverage>=8 / 50% E-field rule: documented only; primary rule remains Coverage>=5
5/7/10-fold CV: documented only; LOOCV is the sole validation design for n=16
OSS-DBS: not included in the HF direct voxel model
paper-like spatial similarity score sensitivity: not included; HFScore_sum is the primary score
automatic localization/normalization/electrode reconstruction QC: not included; existing e-fields are assumed to have passed prior manual/clinical QC
```

## Interpretation Boundary

This model estimates local HF-only stimulation association with 3-month raw post-treatment outcome while controlling baseline. It should be interpreted as an HF efficacy heatmap over the stimulation-exposed right canonical brainmask candidate space, not as a pure anatomic STN map, a target-level network mechanism map, or voxel-wise causal proof.

Because the cohort has `n=16`, the result is hypothesis-generating. LOOCV may be non-significant; a non-significant LOOCV result should not be interpreted as proof that no biological HF sweet spot exists. `Y_base` is used in the voxel map through partial Spearman residualization and is also retained in the final prediction model to test the incremental predictive value of `HFScore_sum`. The QC report must therefore include the association between `HFScore_sum` and `Y_base` and a basic collinearity diagnostic for the final prediction model.
