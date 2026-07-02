# HF-Only 3m Direct Voxel-Level Model

## Research Question

Which voxels in the high-frequency stimulation territory have HF-only exposure associated with better 3-month HF-only clinical outcome?

This is a direct local stimulation sweet-spot model. The former STN-only phase is interpreted as HF-only DBS territory, not as an anatomic STN-only model. STN/SNr masks are used for territory definition, coverage description, and visualization overlays, not for hard assignment of model effects to one nucleus.

Frequency definitions:

```text
HF  = high-frequency stimulation component, frequency_Hz >= 100
ULF = ultra-low-frequency stimulation component, frequency_Hz <= 50
```

## Endpoint

Primary endpoint:

```text
Y_HF3m = raw HF-only 3-month clinical score
```

Primary covariate:

```text
Y_Preop = raw preoperative clinical score
```

Default first-pass scales:

```text
MDS-UPDRS III score (STN, 3 m)
MDS-UPDRS III axial score (STN, 3 m)
```

The scale list is configurable. Scale direction is read from an internal direction table for known scales; unknown scales must provide an explicit higher-is-better or lower-is-better direction before the run starts. Both default first-pass scales are lower-is-better, so the benefit-oriented map is `M_HF(v) = -theta_HF(v)`.

## Inputs

- Raw clinical scores from:

  ```text
  /Users/mojackhu/Research/STNSNr/summary/cohort/subj/subject_effect_origin.xlsx
  ```

  Clinical rows are joined to imaging by `ID` (`SNr003`, `SNr006`, etc.). Subject directory and `NameEn` are resolved through the stimulation parameter workbook and used only as downstream file-system metadata.

- Stimulation parameters for e-field discovery or recomputation:

  ```text
  /Users/mojackhu/Research/STNSNr/summary/cohort/subj/followup_stimulation.xlsx
  sheet = Contact Parameters
  ```

  This workbook is the authoritative source when a missing e-field must be recomputed. Existing cohort QC CSV files can be used for audit, but they are not the primary parameter source for recomputation.

- HF-only E-field per side, taken from the Lead-DBS Horn/SimBio FEM output for the `3m/STN` condition:

  ```text
  stimulations/MNI152NLin2009bAsym/<stimlabel>_3m_STN_*/sub-<Subject>_sim-efield_model-simbio_hemi-{L,R}.nii
  ```

  Use the raw `sim-efield` variant, not `sim-efieldgauss`. E-field values stay in Lead-DBS native units of `V/m`. If a required e-field is missing, the pipeline should recompute it from `followup_stimulation.xlsx`; if recomputation fails, the run stops with a QC error instead of silently excluding the subject.

- Alternating `3m/STN` programs are not modeled as simultaneous double-cathode stimulation. Same-side alternating subprogram e-fields are combined by voxel-wise maximum to form one HF-only field per side.

- Territory mask:

  ```text
  templates/space/MNI152NLin2009bAsym/atlases/STNSNr-connected regions/{rh,lh}/STNSNrplus.nii.gz
  ```

  Manifest: `dilate_mm(2 mm, union(STN>0.05, SNr>0.05))` on the MNI152NLin2009bAsym reference grid. No further dilation is applied.

- Left/right homology transform:

  ```text
  helpers/ea_flip_lr_nonlinear.m
  templates/space/MNI152NLin2009bAsym/fliplr/{Composite,InverseComposite}.nii.gz
  ```

  All left/right flipping in this model uses `ea_flip_lr_nonlinear` with the Lead-DBS default interpolation behavior. No custom left/right deformation or manual interpolation replaces this helper.

## Feature Construction

Use the right `STNSNrplus` grid as the canonical statistical grid. The left HF e-field is flipped into right space with `ea_flip_lr_nonlinear`, producing `E_L_to_R_i(v)` on the right canonical grid. The right HF e-field is sampled on the same grid as `E_R_i(v)`.

Patient-level bilateral exposure is:

```text
X_HF_only_i(v) = (E_R_i(v) + E_L_to_R_i(v)) / 2
```

This keeps one homologous voxel value per patient and avoids left/right pseudo-replication. Exposure is not scaled by stimulation frequency or pulse width; frequency only classifies the component as HF.

The model does not use a paired-mask membership threshold. In particular, there is no `P_left_to_R`, no `Omega_pair`, and no `membership > 0.5` or `membership > 0.7` rule in the executable HF direct voxel model.

Define the analysis mask inside each training set:

```text
tau_primary = 200 V/m
tau_sensitivity = {180, 220} V/m
Coverage_tau(v) = sum_i 1[X_HF_only_i(v) > tau]
Omega_HF_tau = right_STNSNrplus intersect {v : Coverage_tau(v) >= 5}
```

Continuous `X_HF_only_i(v)` values are used for modeling inside `Omega_HF_tau`; `tau` is only used to define coverage and QC. Main output uses `tau=200 V/m`; `tau=180` and `tau=220 V/m` are full sensitivity analyses.

Coverage masks, voxel maps, HF scores, and validation predictions are computed inside each LOOCV training fold. The held-out patient never contributes to that fold's coverage mask or voxel map.

## Statistical Model

For each voxel `v`, estimate a residualized ANCOVA OLS coefficient. Residualize both `Y_HF3m` and `X_HF_only(v)` on `Y_Preop`, then regress residualized outcome on residualized exposure:

```text
Y_HF3m_i = alpha_v
         + theta_HF(v) * X_HF_only_i(v)
         + beta_v      * Y_Preop_i
         + error_i,v
```

No standardization is applied to `X_HF_only(v)` or `M_HF(v)`.

Degenerate voxels with zero exposure variance, or zero residualized exposure variance, are assigned `theta_HF(v)=NaN` and excluded from HFScore numerator and denominator.

Benefit-oriented map:

```text
M_HF(v) = -theta_HF(v)   for lower-is-better scales
M_HF(v) =  theta_HF(v)   for higher-is-better scales
```

Patient-level HF sweet-spot score:

```text
HFScore_i =
  sum_v X_HF_only_i(v) * M_HF(v)
  / sum_v X_HF_only_i(v)
```

The denominator is computed only over voxels with a valid `M_HF(v)`. If the denominator is zero for a subject/fold, `HFScore_i` and the corresponding prediction are recorded as `NaN` and excluded from that metric calculation.

Final prediction model:

```text
Y_HF3m_i = alpha
         + delta * HFScore_i
         + beta  * Y_Preop_i
         + error_i
```

For lower-is-better scales, the expected direction is `delta < 0`.

Missing-data rule: missing `Y_HF3m`, missing `Y_Preop`, or failed e-field availability removes that patient from that scale only after QC. For configurable future scales, the scale is skipped if the valid sample size falls below 12.

## Validation

- Use leave-one-patient-out cross-validation with no inner hyperparameter tuning.
- In each outer fold, rebuild `Omega_HF_tau`, fit the voxel map, compute training and held-out HF scores, and fit the final prediction model using only training patients.
- Compare against the covariate-only baseline `Y_HF3m ~ Y_Preop`.
- Report Pearson `r`, Spearman `rho`, MAE, RMSE, and `Q2` on the original raw outcome scale.
- Define `Q2` relative to the covariate-only baseline:

  ```text
  Q2 = 1 - SSE_HFScore_model / SSE_YPreop_only
  ```

- Patient-level Freedman-Lane permutation uses `B=10000` and random seed `42` for the formal analysis. Smoke/exploratory runs use `B=1000`. For each permutation, fit the nuisance model `Y ~ Y_Preop`, permute the nuisance residuals, reconstruct `Y*`, and rerun the full LOOCV pipeline including coverage, map, score, and prediction. The primary permutation statistic is LOOCV Pearson `r`.
- Subject-level bootstrap uses `B=10000` and seed `42` for the formal analysis. Smoke/exploratory runs use `B=1000`. Each bootstrap resample reruns the full map-building process, including `Omega_HF_tau`, and `direct_voxel_HF_bootstrap_se.nii.gz` stores voxel-wise standard deviation of `theta_HF(v)`.

## Execution Structure

The later code implementation should keep the image preprocessing and statistical postprocessing separated:

- MATLAB/Lead-DBS preprocessing:
  - discover or recompute required HF-only e-fields;
  - combine alternating same-side subprograms by voxel-wise maximum;
  - call `ea_flip_lr_nonlinear` for all left/right flips;
  - sample exposure into the right canonical `STNSNrplus` ROI;
  - write a MAT v7 ROI design matrix with `X(subject x roi_voxel)`, voxel indices, subject metadata, clinical values, reference NIfTI path, and QC metadata.

- Python postprocessing in the `leaddbs` conda environment:
  - read the MAT v7 design matrix;
  - run LOOCV, full Freedman-Lane permutation, and full bootstrap;
  - write CSV/JSON outputs, figures, and NIfTI maps with `nibabel`;
  - fill ROI vectors back into the right canonical reference grid.

Default resource use should be optimized but reproducible:

```text
MATLAB preprocessing workers: 8
Python statistical jobs: 14
random seed: 42
```

Parallel jobs derive deterministic child seeds from seed `42`. MATLAB preprocessing and Python postprocessing run as separate phases to avoid CPU oversubscription. A smoke mode should be available for quick pipeline checks by using `B=1000` permutations/bootstrap resamples and a reduced scale/tau set.

Intermediate audit outputs are retained, including right/flipped exposure products, ROI design matrices, manifests, lock files, and completion markers. Completed outputs are skipped by default; force-rerun options should be available.

## Downstream Visualization

Output root, one folder per scale and tau:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale>/tau180/
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale>/tau200/   # primary
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale>/tau220/
```

Export per tau folder:

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

Map definitions:

- `direct_voxel_HF_coef.nii.gz` stores the raw full-sample final-model `theta_HF(v)`; no per-voxel FDR is applied.
- `direct_voxel_HF_sweet_sour.nii.gz` stores the benefit-oriented `M_HF(v)`.
- `direct_voxel_HF_stability.nii.gz` is the fraction of LOOCV training folds with `theta_HF(v) > 0`.
- `direct_voxel_HF_bootstrap_se.nii.gz` is the full-process bootstrap standard deviation of `theta_HF(v)`.

Primary statistical maps are unsmoothed. Additional sensitivity display maps are generated after coefficient estimation with `FWHM=1 mm` and `FWHM=2 mm`, then re-masked to the territory.

The statistical map is fit on the right canonical grid. For visualization only, generate a bilateral homologous display map by flipping the right map to the left side with `ea_flip_lr_nonlinear` and combining the right statistical map with the flipped left display copy. The bilateral display map is not a separate side-specific statistical model.

Display the HF sweet/sour map with a diverging color scale centered at zero. Show low-coverage voxels as transparent or gray. STN and SNr boundaries are overlays only.

## Interpretation Boundary

This model estimates local HF-only stimulation association with 3-month outcome. It should be interpreted as an HF efficacy heatmap within the STN/SNr stimulation territory, not as a pure anatomic STN map or as voxel-wise causal proof.
