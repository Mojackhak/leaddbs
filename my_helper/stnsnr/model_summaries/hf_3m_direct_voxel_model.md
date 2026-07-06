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

Clinical rows are joined to imaging by `ID` (`SNr003`, `SNr006`, etc.). `subject_effect_origin.xlsx` is a raw endpoint table rebuilt from `scale_subject.xlsx`: `Scale` stores the 28 clinical feature names, `Protocol`/`Phase` store the stimulation condition, `Baseline` stores the corresponding `Pre-op` score, and `Value` stores the raw post/intervention score. The table must not contain `Δ...` derived rows. The improvement-rate table is not used by this model. The scale list is configurable. Scale direction is read from an internal direction table for known scales; unknown scales must provide an explicit higher-is-better or lower-is-better direction before the run starts.

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

Continuous `X_HF_only_i(v)` values are used for modeling inside `Omega_HF_tau`; `tau` is only used to define coverage and QC. `Coverage>=6` and `Coverage>=8` are documented optional sensitivity settings for the primary mainline and are not part of the original `tau200/Coverage>=5` primary branch. The dedicated A-model post-hoc threshold scan is the only current exploratory exception: it may generate scan-level outputs across `Coverage=5,6,7,8,10,12`, but these outputs remain post-hoc and do not replace the primary branch. `Coverage>=8` / 50% E-field coverage from the reference literature is retained in the reference-coverage checklist, but it is not used as the main rule for this `n=16` cohort.

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

### Optional Supplemental Estimator: OLS ANCOVA

OLS ANCOVA is retained as an optional future supplemental estimator. It is not run in the current executable analysis and does not generate output files in this run.

```text
Y_post_i = alpha_v
         + theta_HF(v) * X_HF_only_i(v)
         + beta_v      * Y_base_i
         + error_i,v
```

If enabled in a future run, the OLS estimator should generate the same output family under an `ols_ancova/` estimator directory. Its `direct_voxel_HF_coef.nii.gz` would store `theta_HF(v)`, whereas the primary `partial_spearman/` coefficient file stores `rho_HF(v)`.

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

For non-primary executed branches (`tau180/partial_spearman` and `tau220/partial_spearman`), LOOCV is still run, but formal permutation/bootstrap outputs are not generated. Their manifests and QC JSON files must record:

```text
resampling_status = not_run_nonprimary
resampling_reason = formal resampling restricted to tau200/partial_spearman
```


### HF Voxel Source Resolver And Downstream Role

Source stability and patient-level prediction error are treated as separate evidence axes. The source resolver first decides whether an HF direct-voxel map is stable enough to define `DeltaHFScore`; prediction-error status then decides how downstream ULF branches are interpreted.

The hard computability filter for each tau/Coverage grid cell is:

```text
n_subjects >= 12
n_voxels_full >= 20
fold_n_voxels_min >= 10
HFScore_mean_main is non-constant in every LOOCV fold
all held-out predictions are finite
```

`Q2`, LOOCV Spearman rho, MAE, and RMSE remain required report fields, but `Q2` and rho are not hard filters. MAE/RMSE define prediction-error status after a source is accepted.

Define the HF voxel source status for every endpoint:

```text
hf_voxel_source_status = pre_specified_accepted
  if the pre-specified tau200/Coverage>=5 grid cell passes the hard computability filter
  and at least 2 adjacent tau/Coverage grid cells also pass the hard computability filter

hf_voxel_source_status = scan_fallback_accepted
  if tau200/Coverage>=5 does not pass the source-stability rule
  and another grid cell passes the same source-stability rule

hf_voxel_source_status = absent_no_stable_grid
  if no tau/Coverage grid cell passes the source-stability rule
```

For `scan_fallback_accepted`, choose the fallback grid without using outcome-performance metrics:

```text
1. minimize grid distance from tau200/Coverage>=5
2. maximize adjacent passing grid cells
3. maximize fold_n_voxels_min
4. prefer stricter Coverage
5. prefer higher tau
```

Adjacent grid cells are defined on the declared tau/Coverage grid; horizontal, vertical, and diagonal one-step neighbors all count.

Define the HF voxel prediction status only after a source exists:

```text
hf_voxel_prediction_status = error_predictive
  if MAE_model < MAE_baseline
  and RMSE_model < RMSE_baseline

hf_voxel_prediction_status = error_nonpredictive
  if an HF voxel source exists
  but MAE_model >= MAE_baseline
  or RMSE_model >= RMSE_baseline

hf_voxel_prediction_status = not_applicable
  if hf_voxel_source_status = absent_no_stable_grid
```

Downstream ULF rule:

```text
if hf_voxel_source_status is pre_specified_accepted or scan_fallback_accepted:
  compute DeltaHFScore when HF support is available
  run both no_delta_hf and delta_hf_adjusted ULF branches

if hf_voxel_prediction_status == error_predictive:
  ulf_primary_branch = delta_hf_adjusted

if hf_voxel_prediction_status == error_nonpredictive:
  ulf_primary_branch = no_delta_hf

if hf_voxel_source_status == absent_no_stable_grid:
  do not compute a DeltaHFScore-adjusted ULF branch
  run no_delta_hf only
```

Required manifest/QC fields:

```text
hf_voxel_source_status
hf_voxel_prediction_status
hf_voxel_threshold_source
selected_tau_v_per_m
selected_coverage
selected_grid_distance_from_pre_specified
selected_adjacent_passing_grid_cells
rho_obs
p_perm if available
Q2
MAE_model
MAE_baseline
RMSE_model
RMSE_baseline
hf_downstream_delta_hfscore_role
```

The scientific interpretation is therefore:

```text
Stable map behavior can support a spatial hypothesis.
It does not by itself validate HFScore_mean_main as a patient-level counterfactual HF efficacy model.
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
  - run jitter QC sensitivity for the primary `tau200/partial_spearman` branch;
  - record optional OLS ANCOVA as not run in the current execution;
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
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale_slug>/tau200/partial_spearman/   # primary
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale_slug>/tau220/partial_spearman/
```

Optional future OLS ANCOVA outputs would use sibling `ols_ancova/` directories, but those directories are not generated by the current run.

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

For continuous/statistical NIfTI outputs, voxels outside the model support are written as `NaN`, not `0`. This applies to coefficient, sweet/sour, stability, bootstrap SE, smoothed-display, and homologous-display statistical maps outside `Omega_HF_tau` or outside the right-canonical candidate grid. `0` is reserved for true zero-valued estimates inside support. Integer coverage/count maps and binary display masks remain `0` outside support because their data type and semantics are count/false rather than continuous effect.

Output semantics:

- `direct_voxel_HF_coverage.nii.gz` stores `Coverage_tau(v) = sum_i I(X_HF_i(v) > tau)`. Use `int16`.
- `direct_voxel_HF_coef.nii.gz` stores `rho_HF(v)` for the executed `partial_spearman/` estimator. If optional OLS ANCOVA is enabled in a future run, the corresponding `ols_ancova/` file stores `theta_HF(v)`. Use `float32`. No per-voxel FDR is applied.
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
subject-level bootstrap for tau200/partial_spearman
left/right flip deformation audit
report-only top 10% + stability display masks
2 mm FWHM spatial jitter QC
1 mm and 2 mm display smoothing
```

Covered but not generated as separate HF direct voxel results:

```text
Coverage>=6 optional sensitivity: not generated in the primary mainline; allowed only inside the A-model post-hoc threshold scan
Coverage>=8 / 50% E-field rule: not generated in the primary mainline; primary rule remains Coverage>=5
5/7/10-fold CV: documented only; LOOCV is the sole validation design for n=16
OSS-DBS: not included in the HF direct voxel model
optional OLS supplemental estimator: documented only; not run in the current execution
paper-like spatial similarity score sensitivity: not included; HFScore_mean_main is the primary score
automatic localization/normalization/electrode reconstruction QC: not included; existing e-fields are assumed to have passed prior manual/clinical QC
```

## Interpretation Boundary

This model estimates local HF-only stimulation association with 3-month raw post-treatment outcome while controlling baseline. It should be interpreted as an HF efficacy heatmap over the stimulation-exposed right canonical brainmask candidate space, not as a pure anatomic STN map, a target-level network mechanism map, or voxel-wise causal proof.

Because the cohort has `n=16`, the result is hypothesis-generating. LOOCV may be non-significant; a non-significant LOOCV result should not be interpreted as proof that no biological HF sweet spot exists. `Y_base` is used in the voxel map through partial Spearman residualization and is also retained in the final prediction model to test the incremental predictive value of `HFScore_mean_main`. The QC report must therefore include the association between `HFScore_mean_main` and `Y_base` and a basic collinearity diagnostic for the final prediction model.

If the source resolver accepts a map but MAE or RMSE does not improve over the `Y_base`-only baseline, the correct interpretation is `error_nonpredictive`: the source is stable enough to generate `DeltaHFScore`, but it is not the predictive primary HF adjustment for ULF. In that case, downstream ULF should still run both core branches when inputs allow, with no-DeltaHF recorded as the primary branch.

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
optional supplemental estimator = OLS ANCOVA, not run in the current execution
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

### Optional Vectorized OLS ANCOVA Kernel

If OLS ANCOVA is enabled in a future run, it should use a Frisch-Waugh-Lovell residualization kernel instead of fitting a separate statsmodels or polyfit model for every voxel.

For each fold or full-sample map:

```text
yres = resid(Y_post ~ 1 + Y_base)
xres(v) = resid(X(v) ~ 1 + Y_base)

theta_HF(v) =
  dot(yres, xres(v)) / sum(xres(v)^2)
```

This would produce the same OLS ANCOVA coefficient `theta_HF(v)` while avoiding voxel-wise Python model fitting overhead. The current execution does not run this branch.

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
7. optional OLS ANCOVA supplemental branches only if explicitly enabled in a future run
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

## Execution Priority And Reporting Workflow

The HF direct voxel analysis is executed in stages so the intended source resolver is available before expensive reporting analyses run. The pre-specified branch is:

```text
tau200 / partial_spearman / Coverage>=5 / HFScore_mean_main
```

Non-primary branches and display outputs are delayed until the resolver fields are written. They do not redefine the HF voxel source or prediction status.

### Round 0: Input Readiness And Environment Lock

Run:

```text
clinical table audit:
  Y_post exists
  Y_base exists
  ID joins to imaging subject
  scale direction is defined

e-field availability check:
  each subject x side has a unique 3m/STN raw sim-efield
  sim-efieldgauss is not used
  units are recorded as V/m
  alternating subprograms can be identified and max-combined

left/right flip input audit:
  ea_flip_lr_nonlinear is callable
  Composite and InverseComposite transforms exist
  right canonical grid and brainmask are readable

environment manifest:
  MATLAB / Lead-DBS version
  Python conda env = leaddbs
  conda list --explicit
  python -m pip freeze
  seed = 42
```

Continue only if:

```text
the endpoint has n_subjects >= 12 with Y_post and Y_base
all subject-side e-field paths are uniquely matched
no missing or duplicated raw e-field
no empty, all-NaN, or non-finite e-field
left/right flip helper is callable
```

Stop and fix inputs if any required e-field is missing or duplicated, clinical merge is incomplete, or scale direction is undefined. Do not silently exclude subjects.

### Round 1: Preprocessing Sidecars And Minimal QC

Run:

```text
MATLAB / Lead-DBS preprocessing:
  discover accepted HF-only e-fields
  combine same-side alternating subprograms by voxel-wise maximum
  flip left e-field to right canonical space
  sample right e-field on the right canonical grid

patient-level exposure:
  X_HF_only_i(v) = (E_R_i(v) + E_L_to_R_i(v)) / 2

sparse candidate sidecars:
  X_float32_voxel_major.npy
  S180_bool.npy
  S200_bool.npy
  S220_bool.npy
  candidate_ijk.npy
  candidate_xyz_mm.npy
  candidate_mask_metadata.json

flip audit summary:
  nonzero voxel count
  max, p95, p99, sum
  suprathreshold volume at 180 / 200 / 220 V/m
  intensity-weighted centroid
  L-to-R output overlap with right canonical brainmask
```

Continue to observed modeling only if:

```text
X matrix shape = n_subjects x n_candidate_voxels
n_subjects exactly matches the clinical table
candidate_voxels > 0
S180 / S200 / S220 are not all zero
each subject has nonzero exposure on at least one side
full-sample tau200 Coverage>=5 Omega is non-empty
flip audit has no obvious path mismatch
```

Soft warnings that do not automatically fail the run but must be recorded:

```text
extreme subject-level suprathreshold volume outlier
left-to-right flipped exposure centroid outside plausible brain bounds
exposure_sum_valid_voxels dominated by one or two subjects
```

If `Omega_tau200` is empty, the pre-specified grid cannot be accepted; the scan resolver determines whether a fallback source exists.

### Round 2: Observed LOOCV And Source Resolver

Run only the primary branch:

```text
scale = MDS-UPDRS III total
branch = tau200 / partial_spearman
candidate threshold = 180 V/m
Omega_HF_tau200 = Coverage_200 >= 5
estimator = baseline-adjusted partial Spearman
score = HFScore_mean_main
validation = LOOCV
baseline = Y_post ~ Y_base
```

Generate:

```text
direct_voxel_HF_coverage.nii.gz
direct_voxel_HF_coef.nii.gz
direct_voxel_HF_sweet_sour.nii.gz
direct_voxel_HF_stability.nii.gz
direct_voxel_HF_scores.csv
direct_voxel_HF_loocv_predictions.csv
direct_voxel_HF_mapping_qc.json
direct_voxel_HF_generation_manifest.json
```

Do not run in this round:

```text
axial scale
tau180 / tau220
formal permutation
formal bootstrap
formal jitter
OLS
display smoothing
top 10% display masks
```

The hard computability filter for each endpoint and tau/Coverage grid cell is:

```text
n_subjects >= 12
n_voxels_full >= 20
fold_n_voxels_min >= 10
HFScore_mean_main is non-constant in every LOOCV fold
all held-out predictions are finite
```

Numerical singularity, near-collinearity with `Y_base`, high-leverage dominance, or extreme support imbalance are QC limitations. They must be recorded in the manifest, but they do not replace the source resolver unless they make the hard computability filter fail.

Resolve HF voxel status as:

```text
pre_specified_accepted if tau200/Coverage>=5 and at least 2 adjacent cells pass the hard computability filter
scan_fallback_accepted if a non-primary grid cell passes the same source-stability rule
absent_no_stable_grid if no stable grid cell exists

error_predictive if MAE_model < MAE_baseline and RMSE_model < RMSE_baseline
error_nonpredictive if an accepted source does not improve both MAE and RMSE
```

`Q2`, LOOCV Spearman rho, permutation p values, bootstrap stability, and jitter stability are reporting fields. They do not change `hf_voxel_source_status` or `hf_voxel_prediction_status`. If `absent_no_stable_grid` is assigned, do not compute a DeltaHFScore-adjusted ULF branch for that endpoint.

### Round 3: Equivalence Test And Smoke Reporting

Run:

```text
deterministic equivalence / regression test:
  voxel subset = 100 to 1000
  B_perm = 20
  B_boot = 20
  seed = 42
  compare brute-force vs optimized

smoke permutation:
  tau200 / partial_spearman
  B = 1000
  Freedman-Lane
  full LOOCV recomputation semantics
  statistic = LOOCV Spearman rho

smoke bootstrap:
  tau200 / partial_spearman
  B = 1000
  streaming SE summary

smoke jitter:
  tau200 / partial_spearman
  B = 100
  FWHM = 2 mm
```

Formal reporting analyses require:

```text
fold-specific Omega_HF_tau exactly matches brute-force reference
subject IDs / voxel IDs / split indices exactly match
rho map approximately matches
M_HF map approximately matches
HFScore_mean_main approximately matches
LOOCV predictions approximately match
same NaN / degenerate voxel locations
small-test plus-one p value matches
permutation null is generated without crash
bootstrap finite-count distribution is acceptable
jitter map correlation is recorded
jitter LOOCV direction is recorded
```

Stop and fix implementation only if optimized and brute-force paths are not equivalent or smoke resampling cannot run. Ordinary `Q2`, rho, p-value, or jitter results are reported as inference-strength and robustness information.

### Round 4: Formal Permutation Reporting

Run:

```text
scale = MDS-UPDRS III total
branch = tau200 / partial_spearman
resampling = Freedman-Lane permutation
B = 10000
seed = 42
statistic = LOOCV Spearman rho
output = direct_voxel_HF_permutation_summary.csv
```

Each permutation must logically rerun:

```text
Y_post ~ Y_base nuisance model
permute residuals
reconstruct Y*
rebuild fold-wise map
recompute HFScore_mean_main
rerun LOOCV prediction
compute LOOCV Spearman
```

Permutation output is reportable if:

```text
formal permutation completes
plus-one p value is finite
observed rho is recorded consistently with the smoke run
permutation null distribution has no implementation artifact
```

Interpretation:

```text
accepted source with error_predictive status:
  report predictive and inferential summaries

accepted source with error_nonpredictive status:
  report source/support summaries and avoid claiming patient-level prediction

absent_no_stable_grid:
  report no stable HF voxel source for that endpoint
```

For this cohort, do not use a permutation p value, `Q2`, or LOOCV rho sign to redefine source existence or prediction status. Interpret them together with threshold-source status, MAE/RMSE status, and influence diagnostics.

### Round 5: Formal Bootstrap

Run:

```text
scale = MDS-UPDRS III total
branch = tau200 / partial_spearman
resampling = subject-level bootstrap
B = 10000
seed = 42
output = direct_voxel_HF_bootstrap_se.nii.gz
```

Bootstrap must rebuild:

```text
bootstrap sample
Coverage_tau200_boot
Omega_HF_tau200_boot
partial Spearman map
M_HF map
bootstrap SE
```

Do not save 10000 bootstrap maps. Use streaming Welford accumulation.

Bootstrap reports:

```text
bootstrap finite-count distribution is not too low
primary sweet/sour regions are not completely swamped by SE
direction-stable areas overlap the LOOCV stability map
most bootstrap maps are not empty
median finite bootstrap count / B >= 0.70
core positive-region sign stability >= 0.70
LOOCV positive-direction stability >= 0.75 regions remain anatomically interpretable
```

If map direction flips frequently or is supported by only a small subset of bootstrap resamples, report the spatial claim as fragile.

### Round 6: Formal Spatial Jitter

Run:

```text
scale = MDS-UPDRS III total
branch = tau200 / partial_spearman
jitter B = 1000
FWHM = 2 mm
sigma = 0.849 mm
independent 3D translation per subject-side e-field
```

Each jitter iteration must rebuild:

```text
jittered exposure matrix
candidate mask
Omega_HF_tau200
full-sample map
HF scores
LOOCV validation metrics
```

Jitter reports:

```text
median jitter map correlation > 0.5
median jitter LOOCV direction
core sweet/sour direction does not systematically reverse
core-region spatial drift stays within an anatomically interpretable range
```

If jitter map correlation is near zero, LOOCV direction is unstable, or the core region disappears with 1 to 2 mm translation, describe the spatial report as:

```text
spatially fragile exploratory association
```

### Round 7: Tau Sensitivity

Run observed LOOCV only:

```text
scale = MDS-UPDRS III total
branches:
  tau180 / partial_spearman
  tau220 / partial_spearman
```

Do not run formal permutation or formal bootstrap for non-primary branches. Non-primary manifests must record:

```text
resampling_status = not_run_nonprimary
resampling_reason = formal resampling restricted to tau200/partial_spearman
```

Tau sensitivity reports:

```text
tau180, tau200, and tau220 LOOCV directions
Q2 across thresholds
sweet/sour map spatial correlation or core overlap is acceptable
Omega size changes monotonically with tau
```

Interpretation:

```text
tau180 / tau220 agree with tau200:
  supports threshold robustness

only tau200 has signal:
  report primary result as threshold-sensitive

tau180 or tau220 reverses direction:
  avoid strong sweet spot interpretation
```

### Round 8: Secondary Axial Scale

Run as a secondary endpoint report:

```text
scale = MDS-UPDRS III axial score
first branch = tau200 / partial_spearman
tau180 / tau220 only if tau200 axial passes QC
validation = observed LOOCV
smoke permutation = optional
```

Do not immediately run formal `B=10000` permutation, formal bootstrap, or formal jitter for axial unless axial is promoted to a co-primary endpoint or both total and axial show consistent primary signal.

Optional axial reporting records:

```text
axial tau200 LOOCV folds all finish
HFScore is not constant
rho_obs direction
Q2
map has plausible spatial overlap with the total-score map
```

Report axial limitations if:

```text
map is completely inconsistent with total score
one subject determines the result
```

### Round 9: Display, PDF QC, And Final Manifests

Run only after statistical branches are complete:

```text
display_smooth_fwhm1mm/
display_smooth_fwhm2mm/
bilateral homologous display maps
sweet_display_mask
sour_display_mask

PDF QC:
  coverage histogram
  score-vs-outcome scatter
  LOOCV observed-vs-predicted scatter
  permutation null distribution
  bootstrap stability summary
  jitter stability summary
```

Display outputs must not feed back into:

```text
HFScore
LOOCV
permutation
bootstrap
jitter
```

Final reporting requires:

```text
complete manifest for every generated branch
mapping_qc.json includes coverage, degenerate voxels, and zero-exposure score counts
corr(HFScore_mean_main, Y_base) is recorded
prediction coefficient signs and collinearity diagnostics are recorded
flip audit is recorded
package/environment provenance is recorded
```

### Round 10: Optional Future Analyses

These are not part of the current direct voxel executable mainline:

```text
OLS ANCOVA
Coverage>=6
Coverage>=8 / 50% rule
5/7/10-fold CV
OSS-DBS
paper-like spatial similarity score
automatic localization / electrode reconstruction QC
```

OLS ANCOVA is an optional future supplemental estimator and does not generate outputs in the current run. OSS-DBS does not belong to direct voxel analysis and should remain in normative fiber / activation sensitivity documentation.

### Post-hoc Tau/Coverage Threshold Scan

The A-model post-hoc threshold scan is an exploratory branch for selecting a core HF sweet spot threshold when the pre-specified tau200/Coverage>=5 grid is not accepted by the source resolver. It may generate a biologically plausible high-dose/high-coverage core-territory hypothesis, but it must not replace or relabel the original primary analysis:

```text
primary branch:
  tau = 200 V/m
  Coverage >= 5

post-hoc scan:
  output root = posthoc_threshold_scan/
  interpretation = exploratory / post-hoc threshold optimization
```

The single-scale default scan is restricted to the first default endpoint:

```text
endpoint = MDS-UPDRS III score (STN, 3 m)
estimator = baseline-adjusted partial Spearman
score = HFScore_mean_main
validation = LOOCV
baseline model = Y_post ~ Y_base
```

An all-scale exploratory mode may also run the same scan for every `Scale` in `subject_effect_origin.xlsx`:

```text
--all-scales
```

This all-scale mode scans 30 HF-only endpoints: the 28 raw clinical scales under the `STN, 3 m` condition plus the two available `STN, immediate` UPDRS endpoints (`MDS-UPDRS III score` and `MDS-UPDRS III axial score`). It does not scan `Δ...` endpoints because `subject_effect_origin.xlsx` no longer stores derived delta rows. `STN+SNr` raw endpoints remain available in the workbook for ULF/add-on reconstruction and secondary analyses, but they are not part of the A-model HF-only all-scale scan unless explicitly requested.

The scan grid is:

```text
tau, V/m:
  100, 150, 180, 200, 220, 250, 300, 350, 400, 500

Coverage:
  5, 6, 7, 8, 10, 12
```

This yields `10 x 6 = 60` grid cells. Because `tau=100` and `tau=150` are below the default sparse candidate threshold used by the primary run, the scan must build or reuse a dedicated post-hoc exposure sidecar with:

```text
candidate_sparse_threshold = 100 V/m
```

Using the original `candidate_threshold=180 V/m` sidecar to evaluate `tau=100` or `tau=150` would be incomplete and is not allowed for the post-hoc scan.

Each grid cell reports:

```text
tau
coverage
n_voxels_full
fold_n_voxels_min
fold_n_voxels_median
fold_n_voxels_max
LOOCV Spearman rho
LOOCV Spearman nominal p
LOOCV Pearson r
Q2
MAE_model
MAE_baseline
RMSE_model
RMSE_baseline
corr(HFScore_mean_main, Y_base)
delta_median
delta_min
delta_max
```

The hard computability filter is:

```text
n_subjects >= 12
n_voxels_full >= 20
fold_n_voxels_min >= 10
HFScore non-constant in every fold
all held-out predictions finite
```

The resolver first tests the pre-specified `tau200/Coverage>=5` grid cell. It is accepted when that cell passes the hard computability filter and at least 2 adjacent grid cells also pass. If it is not accepted, choose a fallback only among grid cells passing the same source-stability rule, using this priority order:

```text
1. closer to tau200/Coverage>=5
2. more adjacent passing grid cells
3. higher fold_n_voxels_min
4. stricter Coverage
5. higher tau
```

Required outputs are:

```text
posthoc_threshold_scan_results.csv
posthoc_threshold_scan_heatmap_q2.csv
posthoc_threshold_scan_heatmap_rho.csv
posthoc_threshold_scan_heatmap_n_voxels.csv
posthoc_threshold_scan_heatmap_rho_annotated_source.csv
posthoc_selected_threshold_manifest.json
```

Figure outputs, when the plotting environment is available, should mirror the CSV heatmaps and include a publication-style annotated rho heatmap:

```text
posthoc_threshold_scan_heatmap_q2.png
posthoc_threshold_scan_heatmap_rho.png
posthoc_threshold_scan_heatmap_n_voxels.png
posthoc_threshold_scan_heatmap_rho_annotated.svg
posthoc_threshold_scan_heatmap_rho_annotated.pdf
posthoc_threshold_scan_heatmap_rho_annotated.png
```

The annotated rho heatmap uses:

```text
x axis = tau (V/m)
y axis = Coverage threshold
cell color = LOOCV Spearman rho, centered at rho = 0
cell label = rho rounded to 2 decimals plus nominal-p stars on the next line
primary branch tau=200 / Coverage>=5 = thin black outline
post-hoc selected branch = thick black outline
hard-computability-passing cells = light gray auxiliary marker or outline
```

Nominal-p stars are:

```text
*   p < 0.05
**  p < 0.01
*** p < 0.001
```

Grid-cell p values are nominal only and are not corrected by FDR or max-stat permutation. The fallback resolver does not use `Q2`, rho, or nominal p for source selection; these values are reported for interpretation. If a fallback branch is later described as significant after threshold scanning, a max-stat permutation is required:

```text
for each permutation:
  rerun all 60 tau x Coverage cells
  record max Q2 or max LOOCV rho

smoke max-stat permutation:
  B = 1000

formal max-stat permutation:
  B = 10000

seed = 42
```

The max-stat permutation is not part of the initial post-hoc scan output unless explicitly requested.

### HF Voxel Source Resolver And ULF Propagation

Each endpoint is assigned exactly one source status before any `DeltaHFScore` is propagated to ULF modeling:

```text
pre_specified_accepted:
  tau200/Coverage>=5 passes the hard computability filter
  and at least 2 adjacent grid cells pass the hard computability filter

scan_fallback_accepted:
  tau200/Coverage>=5 is not accepted
  and a fallback grid cell passes the same source-stability rule

absent_no_stable_grid:
  no grid cell passes the source-stability rule
```

For accepted sources, prediction status is assigned from error improvement only:

```text
error_predictive:
  MAE_model < MAE_baseline
  and RMSE_model < RMSE_baseline

error_nonpredictive:
  accepted source exists
  but either MAE or RMSE does not improve over baseline
```

If an HF voxel source exists, ULF should run both `delta_hf_adjusted` and `no_delta_hf` branches when inputs allow. `delta_hf_adjusted` is primary when `hf_voxel_prediction_status = error_predictive`; otherwise `no_delta_hf` is primary. If no stable HF voxel source exists, do not run a DeltaHFScore-adjusted ULF branch for that endpoint.

All-scale mode additionally writes:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/posthoc_threshold_scan_all_scales/
  all_scales_posthoc_threshold_scan_long.csv
  all_scales_posthoc_threshold_scan_summary.csv
  all_scales_posthoc_threshold_scan_manifest.json
```

`all_scales_posthoc_threshold_scan_long.csv` contains `30 x 60 = 1800` rows when all 30 HF-only endpoints are available. `all_scales_posthoc_threshold_scan_summary.csv` contains one row per endpoint, including selected `tau`, selected `Coverage`, selected rho, nominal p, Q2, voxel count, endpoint family, and number of hard-computability-passing grid cells. If an endpoint has no passing grid cell, selected threshold fields remain empty and `n_passing_grid_cells = 0`.

All-scale mode uses condition-specific shared HF exposure caches to avoid recomputing the same e-field sampling for every endpoint:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/_shared/posthoc_threshold_scan/preprocess_candidate_tau100/stn_3m/
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/_shared/posthoc_threshold_scan/preprocess_candidate_tau100/stn_immediate/
```

The `STN, 3 m` endpoints use `3m/STN` e-fields; the two `STN, immediate` endpoints use `immediate/STN` e-fields. If a shared cache is missing, the pipeline first reuses the matching single-endpoint tau100 cache when the subject order and exposure condition match; otherwise it rebuilds the shared cache from the corresponding HF e-field inputs.

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
MDS-UPDRS III total
tau200
partial_spearman
Coverage>=5
HFScore_mean_main
LOOCV
Y_base-only comparison
equivalence test
smoke permutation B=1000
smoke bootstrap B=1000
smoke jitter B=100
basic QC JSON + manifest
```

Only after this batch passes should the analysis proceed to `B=10000` formal permutation and bootstrap.
