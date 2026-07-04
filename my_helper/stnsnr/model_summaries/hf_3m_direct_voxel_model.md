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
V_score = Omega_HF_tau intersect valid M_HF voxels
n_valid_score_voxels = |V_score|

HFScore_mean_main_i =
  sum_{v in V_score} X_HF_only_i(v) * M_HF(v)
  / n_valid_score_voxels
```

This is the primary analysis score. It is a voxel-count-normalized, voxel-correlation-weighted mean exposure over the fixed scoring voxel set for the corresponding full-sample map or LOOCV training fold. It is divided by `n_valid_score_voxels` so scores remain comparable when fold-specific `Omega_HF_tau` sizes differ. It is not divided by `sum(X)` and is not multiplied by voxel volume. If `V_score` is empty, the branch/fold fails QC instead of producing a score. If a subject/fold has no exposure in a non-empty valid scoring voxel set, `HFScore_mean_main_i` is recorded as `0`.

The corresponding unnormalized total exposure score is retained only as a documented descriptive concept:

```text
HFScore_sum_descriptive_i =
  sum_{v in V_score} X_HF_only_i(v) * M_HF(v)
```

`HFScore_sum_descriptive_i` is not computed or written by the current executable analysis, and it is not used for the primary prediction model, LOOCV statistic, permutation, or bootstrap. It is kept in the document only to clarify how the main score relates to the previously discussed total dose exposure.

Final prediction model:

```text
Y_post_i = alpha
         + delta * HFScore_mean_main_i
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

- Patient-level Freedman-Lane permutation uses `B=10000` and random seed `42` for the formal primary analysis. Smoke/exploratory runs use `B=1000`. Formal permutation is run only for `tau200/partial_spearman`. For each permutation, fit the nuisance model `Y_post ~ Y_base`, permute the nuisance residuals, reconstruct `Y*`, and rerun the full LOOCV pipeline including coverage, map, `HFScore_mean_main`, and prediction. The primary permutation statistic is LOOCV Spearman rho.
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
- `direct_voxel_HF_scores.csv` stores patient-level map matching scores. Required fields include `HFScore_mean_main`, `exposure_sum_valid_voxels`, `n_valid_score_voxels`, `score_map_source`, and `is_primary_score`. `HFScore_mean_main` is the only primary prediction score. `HFScore_sum_descriptive` is documented only and is not a required output field.
- `direct_voxel_HF_loocv_predictions.csv` stores held-out LOOCV predictions, including `HFScore_LOOCV`, true outcome, HFScore-model prediction, covariate-only baseline prediction, and residuals.
- `direct_voxel_HF_permutation_summary.csv` stores the Freedman-Lane permutation summary for the primary branch only, including observed LOOCV Spearman rho, plus-one two-sided p value, secondary metrics, and `B`.
- `direct_voxel_HF_mapping_qc.json` stores scale/tau/estimator QC, including patient inclusion, candidate mask size, coverage distribution, `Omega_HF_tau` voxel count, low-coverage warning, degenerate voxels, NaN handling, zero-exposure score counts, `corr(HFScore_mean_main, Y_base)`, prediction coefficient signs, optional VIF or equivalent collinearity diagnostics, flip deformation audit metrics, and design-matrix dimensions.
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
paper-like spatial similarity score sensitivity: not included; HFScore_mean_main is the primary score
automatic localization/normalization/electrode reconstruction QC: not included; existing e-fields are assumed to have passed prior manual/clinical QC
```

## Interpretation Boundary

This model estimates local HF-only stimulation association with 3-month raw post-treatment outcome while controlling baseline. It should be interpreted as an HF efficacy heatmap over the stimulation-exposed right canonical brainmask candidate space, not as a pure anatomic STN map, a target-level network mechanism map, or voxel-wise causal proof.

Because the cohort has `n=16`, the result is hypothesis-generating. LOOCV may be non-significant; a non-significant LOOCV result should not be interpreted as proof that no biological HF sweet spot exists. `Y_base` is used in the voxel map through partial Spearman residualization and is also retained in the final prediction model to test the incremental predictive value of `HFScore_mean_main`. The QC report must therefore include the association between `HFScore_mean_main` and `Y_base` and a basic collinearity diagnostic for the final prediction model.

## Execution Efficiency

This section defines implementation-level rules to increase project-level computational efficiency for the HF direct voxel analysis. These rules change only how computations are scheduled, cached, vectorized, and written to disk. They do not change the statistical estimands, validation design, output semantics, file naming, or interpretation of any `direct_voxel_HF_*` output.

The optimized implementation must preserve the logical full-process semantics described above. In particular, LOOCV training folds still define their own `Omega_HF_tau`, voxel maps, HF scores, and held-out predictions. Formal Freedman-Lane permutation and subject-level bootstrap still use `B=10000` and seed `42` for the primary `tau200/partial_spearman` branch. Smoke runs still use `B=1000` for permutation/bootstrap and `B=100` for jitter. The optimized implementation may reuse mathematically invariant cached subcomputations, but it must not use full-sample ranks, full-sample training masks, approximate ranks, adaptive early stopping, changed tau thresholds, changed estimators, or reduced formal resampling counts to gain speed.

### Equivalence Contract

The following quantities are part of the executable statistical definition and must remain unchanged:

```text
tau = 180, 200, 220 V/m
primary tau = 200 V/m
Coverage>=5
LOOCV patient split
primary estimator = baseline-adjusted partial Spearman
supplemental estimator = OLS ANCOVA
primary score = HFScore_mean_main
formal permutation B = 10000
formal bootstrap B = 10000
formal jitter B = 1000
seed = 42
primary permutation statistic = LOOCV Spearman rho
```

Numerical reductions should use `float64` where feasible. Final NIfTI outputs keep the existing output dtypes: `float32` for coefficient, sweet/sour, stability, and bootstrap SE maps, and `int16` for coverage maps. Existing degenerate-voxel and NaN rules remain unchanged.

The implementation must preserve the distinction between logical full-process recomputation and cached mathematically equivalent computation. For example, a permutation run must still behave as if the LOOCV map and `HFScore_mean_main` were recomputed for every permuted outcome, but fixed exposure-derived fold caches may be reused when they are independent of the permuted outcome.

### Preprocessing Sidecar Cache

MATLAB/Lead-DBS preprocessing must continue to write the documented MAT v7 design matrix using the existing subject-major schema:

```text
X(subject x candidate_voxel)
```

In addition, formal runs must write memmap-friendly voxel-major sidecar files for Python postprocessing:

```text
X_float32_voxel_major.npy       # shape = candidate_voxel x subject
S180_bool.npy                   # X > 180 V/m
S200_bool.npy                   # X > 200 V/m
S220_bool.npy                   # X > 220 V/m
candidate_ijk.npy
candidate_xyz_mm.npy
candidate_mask_metadata.json
```

`X_float32_voxel_major.npy` is the preferred formal-loop input because voxel chunks are contiguous on disk. A subject-major mirror may be written for convenience, but formal permutation/bootstrap loops should avoid compressed random-access formats. Formula notation such as `X_all[:, V]` denotes the logical subject-major view; implementation may obtain that view from the voxel-major sidecar by chunked reads or transposition.

MAT and compressed NPZ files may be retained for archival, compatibility, and debugging. Compressed NPZ must not be used as the primary random-access input inside formal permutation, bootstrap, or jitter loops.

The sidecar metadata must record:

```text
subject order
candidate voxel order
affine/header reference
dtype
array shape
memory layout
source MAT path
source MAT hash if available
sidecar creation time
software version
```

### Coverage And Fold Mask Cache

For each tau, precompute full-sample suprathreshold indicators and coverage once:

```text
S_tau(v, i) = I[X_i(v) > tau]
Coverage_tau_all(v) = sum_i S_tau(v, i)
```

For LOOCV fold `h`, derive training-fold coverage by subtraction:

```text
Coverage_tau_fold_h(v) =
  Coverage_tau_all(v) - S_tau(v, h)
```

Then define the fold-specific statistical mask:

```text
Omega_HF_tau_fold_h =
  {v in Candidate : Coverage_tau_fold_h(v) >= 5}
```

The held-out patient therefore still does not contribute to the fold-specific `Omega_HF_tau`, but the mask is computed by vectorized subtraction rather than by rescanning the full exposure matrix.

### Vectorized Partial Spearman Kernel

The primary voxel map must use a vectorized rank-residual partial Spearman kernel.

For each training fold, ranks must be computed within the training set only. Full-sample ranks are prohibited for LOOCV map fitting, permutation map fitting, bootstrap maps, and jitter resamples.

For each fold `h`:

```text
b_h = rank(Y_base_train)

R_h = residual-maker matrix for:
      intercept + b_h
```

For each voxel chunk:

```text
xrank_h(v) = rank(X_train(v)) within the training fold
xres_h(v)  = R_h xrank_h(v)
```

Degenerate voxels with zero exposure variance, zero rank variance, or zero residualized exposure variance keep the existing NaN rule and are excluded from `HFScore_mean_main`.

The exact partial Spearman coefficient is:

```text
yrank_h = rank(Y_post_train)
yres_h  = R_h yrank_h

rho_HF_h(v) =
  dot(yres_h, xres_h(v))
  / sqrt(sum(yres_h^2) * sum(xres_h(v)^2))
```

The benefit-oriented map remains:

```text
M_HF_h(v) = -rho_HF_h(v)   for lower-is-better scales
M_HF_h(v) =  rho_HF_h(v)   for higher-is-better scales
```

### Fold-Level Score Operator For Permutation

Formal Freedman-Lane permutation for the primary `tau200/partial_spearman` branch should use a fold-level score operator.

Within a fixed LOOCV fold, the following quantities are independent of the permuted outcome:

```text
X exposure matrix
tau200 suprathreshold indicators
Coverage_tau200_fold_h
Omega_HF_tau200_fold_h
valid nondegenerate exposure voxels
n_valid_score_voxels
rank(Y_base_train)
residualized and normalized rank(X_train(v))
held-out exposure values
all-subject exposure values used for scoring
```

For each fold `h`, define the valid scoring voxel set:

```text
V_h = Omega_HF_tau200_fold_h intersect valid exposure-residual voxels
n_h = |V_h|
```

Let `Z_h` be the normalized residualized exposure-rank matrix over `V_h`:

```text
Z_h(:, v) =
  resid(rank(X_train(v)) ~ 1 + rank(Y_base_train))
  / sqrt(sum(resid_X_h(v)^2))
```

Let `X_score_h` be the continuous exposure matrix for all patients over `V_h`, not ranked:

```text
X_score_h = X_all(:, V_h)
```

The fold-level score operator is:

```text
A_h =
  direction_sign * X_score_h @ Z_h.T / n_h

direction_sign = -1 for lower-is-better scales
direction_sign =  1 for higher-is-better scales
```

For an observed or permuted outcome, compute:

```text
yres_h =
  resid(rank(Y_train) ~ 1 + rank(Y_base_train))

u_h =
  yres_h / sqrt(sum(yres_h^2))
```

Then all patient scores for this fold are obtained by:

```text
HFScore_mean_main_all_patients_h = A_h @ u_h
```

This is equivalent to computing the fold-specific partial Spearman map and then applying:

```text
HFScore_mean_main_i =
  sum_{v in V_h} X_i(v) * M_HF_h(v) / n_h
```

For formal permutation, the implementation should recompute `u_h` for each reconstructed `Y*` but reuse `A_h`.

The exact normalized partial Spearman scaling must be retained by default. A common positive fold-permutation scaling factor may be omitted only in internal null-statistic-only computations that do not write maps, scores, coefficients, or fold-level model coefficients. Observed outputs and any debug comparison outputs must use exact normalization.

Permutation runs must not write per-permutation voxel maps, per-permutation NIfTI files, or per-permutation score CSV files. They should write only the final permutation summary and any compact null-statistic arrays required to reproduce the summary.

### Vectorized OLS ANCOVA Kernel

The supplemental OLS ANCOVA branch should use a Frisch-Waugh-Lovell residualization kernel instead of fitting a separate statsmodels or polyfit model for every voxel.

For each fold or full-sample map:

```text
yres = resid(Y_post ~ 1 + Y_base)
xres(v) = resid(X(v) ~ 1 + Y_base)

theta_HF(v) =
  dot(yres, xres(v)) / sum(xres(v)^2)
```

This produces the same OLS ANCOVA coefficient `theta_HF(v)` while avoiding voxel-wise Python model fitting overhead.

### Score Computation

For observed maps and non-permutation branches, compute `HFScore_mean_main` by one matrix-vector product per map:

```text
scores =
  X_all[:, V_score] @ M_HF[V_score] / n_valid_score_voxels
```

`X_all` is continuous exposure, not ranked exposure. Rank transformation is used only for estimating the partial Spearman voxel map.

No subject-loop by voxel-loop implementation is allowed for formal runs.

### Bootstrap Efficiency

Subject-level bootstrap remains a full-process map stability analysis for the primary `tau200/partial_spearman` branch. It still uses `B=10000` and seed `42`.

However, bootstrap must reuse exposure-derived caches whenever possible.

For each bootstrap resample, represent the resampled patients by subject counts:

```text
w_i = number of times subject i appears in the bootstrap sample
```

Then compute bootstrap coverage without rescanning image data:

```text
Coverage_tau200_boot(v) =
  sum_i w_i * I[X_i(v) > 200]
```

The bootstrap `Omega_HF_tau200_boot` is then:

```text
Omega_HF_tau200_boot =
  {v in Candidate : Coverage_tau200_boot(v) >= 5}
```

Ranks for `Y_post`, `Y_base`, and `X(v)` must still be computed within the expanded bootstrap resample or an exactly equivalent weighted-resample representation. Full-sample ranks are prohibited.

Bootstrap SE must be accumulated by streaming Welford updates. The implementation must not store 10000 bootstrap maps.

For each voxel, maintain:

```text
bootstrap_mean
bootstrap_M2
bootstrap_finite_count
```

Voxels absent from a bootstrap map, outside the bootstrap `Omega_HF_tau200_boot`, or degenerate under that bootstrap resample follow the existing NaN/out-of-valid-map rule and are not silently imputed as zero.

The final `direct_voxel_HF_bootstrap_se.nii.gz` stores the voxel-wise standard deviation of finite bootstrap estimator values. The QC JSON should record the finite bootstrap count distribution.

### Spatial Jitter Efficiency

Spatial jitter is run only for the primary `tau200/partial_spearman` branch and keeps the existing formal and smoke settings:

```text
formal jitter resamples = 1000
smoke jitter resamples  = 100
```

Jitter changes the e-field geometry. Therefore, primary `X`-derived caches are invalid under jitter and must not be reused as if the exposure matrix were unchanged.

The jitter implementation may reuse:

```text
accepted e-field path manifest
subject/side metadata
right canonical reference grid
candidate grid metadata
affine/header information
preallocated arrays
```

For each jitter iteration, it must rebuild the jittered exposure matrix, candidate mask, `Omega_HF_tau200`, full-sample map, HF scores, and LOOCV validation metrics as defined in the Spatial Jitter QC Sensitivity section.

Do not save every jittered NIfTI map. Save only:

```text
jitter summary table
map correlation/stability summary
voxel-wise jitter SD map
```

### MATLAB/Lead-DBS Preprocessing Efficiency

For each subject-side, accepted HF e-fields should be processed once.

Same-side alternating subprograms are combined by voxel-wise maximum before left/right flipping. The left combined HF e-field is then flipped once using `ea_flip_lr_nonlinear`. The right combined HF e-field is sampled once on the right canonical grid.

Recommended preprocessing artifacts:

```text
subject_side_right_grid_exposure.nii.gz or .npy
subject_left_to_right_grid_exposure.nii.gz or .npy
subject_level_X_HF_only.npy
flip_audit_summary.json
```

These artifacts may be reused by downstream Python postprocessing and jitter setup, but jittered exposure matrices must be generated separately for each jitter iteration.

### Parallel Execution

MATLAB preprocessing and Python statistical postprocessing remain separate phases to avoid CPU oversubscription.

Python postprocessing should be orchestrated from a single long-running Python entry point inside the `leaddbs` Conda environment. Repeated short `conda run` calls inside tau, fold, permutation, bootstrap, or jitter loops should be avoided.

Python worker-level parallelism is preferred. Nested BLAS oversubscription must be disabled before importing NumPy/SciPy:

```bash
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
```

The run manifest must record the effective worker count and BLAS thread settings.

Recommended scheduling order:

```text
1. MATLAB/Lead-DBS preprocessing and sidecar cache generation
2. tau200/partial_spearman observed LOOCV
3. tau200/partial_spearman smoke permutation/bootstrap/jitter
4. tau200/partial_spearman formal permutation
5. tau200/partial_spearman formal bootstrap
6. tau180/tau220 partial_spearman observed LOOCV
7. all OLS ANCOVA supplemental branches
8. display smoothing, bilateral display maps, PDF QC, and final manifests
```

Primary-branch QC failures should stop the run before non-primary sensitivity branches are launched.

### Intermediate File Policy

Formal loops must not write fold, permutation, bootstrap, or jitter intermediate maps unless a debug flag is explicitly enabled.

Default formal outputs remain the existing documented outputs:

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

Workers must not concurrently append to shared CSV or JSON files. Workers should return structured block results to the main process, and the main process writes final CSV/JSON outputs atomically.

Completed outputs are skipped by default according to the existing completion-marker and force-rerun policy.

### Prohibited Speed Shortcuts

The following shortcuts are not allowed in formal runs:

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
using the descriptive sum score in place of HFScore_mean_main
using compressed NPZ as the random-access formal-loop input
loop-internal compression/decompression for speed-critical arrays
```

### Runtime Profile

`direct_voxel_HF_generation_manifest.json` should include a runtime profile:

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
    "python_jobs": null,
    "blas_threads": null,
    "memmap_sidecars": [],
    "score_operator_enabled": null,
    "score_operator_exact_scaling": null,
    "bootstrap_finite_count_summary": null
  }
}
```

### Equivalence And Regression Tests

Implementation should include a small deterministic equivalence test before formal runs.

For a small voxel subset and small resampling count:

```text
B_perm = 20
B_boot = 20
n_voxel_subset = 100 to 1000
seed = 42
```

Compare brute-force and optimized implementations for:

```text
fold-specific Omega_HF_tau
partial Spearman rho map
benefit-oriented M_HF map
HFScore_mean_main
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

The final run manifest should record whether the optimized equivalence test passed.
