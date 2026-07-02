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

For lower-is-better scales, coefficients are sign-flipped for benefit-oriented maps. For SE-ADL, positive coefficients already indicate benefit.

Scale scope for the first implementation pass (expand later):

```text
scales = { MDS-UPDRS III, MDS-UPDRS III axial }   # both lower-is-better
```

Each scale is fit independently and writes its own maps. Both first-pass scales are lower-is-better, so `M_HF(v) = -theta_HF(v)`.

## Inputs

- HF-only continuous E-field per side, taken directly from the Lead-DBS Horn/SimBio FEM output for the `3m/STN` (STN-only 3-month) condition:

  ```text
  stimulations/MNI152NLin2009bAsym/<stimlabel>_3m_STN_continuous/sub-<Subject>_sim-efield_model-simbio_hemi-{L,R}.nii
  ```

  Use the raw `sim-efield` variant (not `sim-efieldgauss`). The `<stimlabel>` prefix varies per subject (e.g. `stnsnr_vta_SNr026`); resolve the folder by globbing `*_3m_STN_*` under the subject's MNI stimulations directory. E-field values are kept in Lead-DBS native units of `V/m`. No re-export is required; these maps already exist on disk.
- Alternating `3m/STN` programs (e.g. no `_continuous` folder, only `_3m_STN_alt_*` subprograms): combine same-side subprogram continuous E-fields by voxel-wise maximum to form one HF-only field per side. Do not treat alternating subprograms as simultaneous double-cathode stimulation.
- Territory mask (already 2 mm dilated STN∪SNr, one per side):

  ```text
  templates/space/MNI152NLin2009bAsym/atlases/STNSNr-connected regions/{rh,lh}/STNSNrplus.nii.gz
  ```

  Manifest: `dilate_mm(2 mm, union(STN>0.05, SNr>0.05))` on the MNI152NLin2009bAsym reference grid. No further dilation is applied.
- Left→right homology warp (Lead-DBS built-in asymmetric nonlinear flip):

  ```text
  helpers/ea_flip_lr_nonlinear.m
  templates/space/MNI152NLin2009bAsym/fliplr/{Composite,InverseComposite}.nii.gz
  ```

- Raw clinical scores from `subject_effect_origin.xlsx` (upstream source `scale_raw/scale_subject.xlsx`). Rows are joined to imaging by subject name (e.g. `ChenLingHua`); exact sheet/column names are resolved at implementation time by reading the workbook.

STN/SNr anatomical masks remain available for overlays and coverage summaries only.

## Feature Construction

Define the stimulation territory as a data-driven coverage envelope intersected with the anatomical mask:

```text
Omega_HF = { v : Coverage(v) >= 5 }  intersected with  STNSNrplus (right canonical grid)
```

The model does not split overlapping or border-zone voxels into STN versus SNr.

### Bilateral homologous voxel exposure

Direct voxel-level models require a homologous voxel coordinate system. Use the right `STNSNrplus` grid as the canonical grid. For each canonical right voxel center `c_R(v)`, define the left homologous continuous location via the inverse left-to-right deformation:

```text
c_L(v) = phi_inverse_L_to_R(c_R(v))
```

Sample the left E-field at that continuous location with trilinear interpolation. In practice, flip the left E-field into right space with `ea_flip_lr_nonlinear` (using `fliplr/Composite.nii.gz`), which yields `E_L_to_R_i(v)` directly on the canonical grid. The patient-level bilateral exposure is:

```text
X_HF_only_i(v) = ( E_R_i(c_R(v)) + E_L_to_R_i(v) ) / 2
```

This keeps one value per patient per homologous voxel (`n = 16` maximum), avoiding left/right pseudo-replication.

The paired analysis mask keeps only right canonical voxels whose inverse-warped left homologous location remains inside the left territory mask:

```text
P_left_to_R(v) = interp_linear(1_left_STNSNrplus, c_L(v))
Omega_pair = { v in Omega_R : P_left_to_R(v) > 0.5 }
```

Use `> 0.7` as a conservative sensitivity threshold.

### Coverage

Use continuous exposure for model fitting inside the coverage mask. The active-voxel threshold is used for coverage/QC:

```text
tau = 200 V/m            # equivalent to 0.2 V/mm
Coverage(v) = sum_i 1[X_HF_only_i(v) > tau]
```

Fit where `Coverage(v) >= 5`, with `tau = 180` and `220 V/m` as threshold sensitivity analyses. Coverage masks, paired masks, voxel maps, and scores are all computed inside each cross-validation training fold; the held-out patient never contributes to fold-specific mask or map definition.

## Statistical Model

For each voxel `v`, use a residualized ANCOVA (OLS) estimator. Residualize `Y_HF3m` and `X_HF_only(v)` on `Y_Preop`, then take the OLS coefficient of residualized exposure on residualized outcome:

```text
Y_HF3m_i = alpha_v
         + theta_HF(v) * X_HF_only_i(v)
         + beta_v      * Y_Preop_i
         + error_i,v
```

No standardization is applied to `X_HF_only(v)` or `M_HF(v)`.

Benefit-oriented map:

```text
M_HF(v) = -theta_HF(v)   for lower-is-better scales
M_HF(v) =  theta_HF(v)   for SE-ADL
```

Patient-level HF sweet-spot score (`lambda = 0`):

```text
HFScore_i =
  sum_v X_HF_only_i(v) * M_HF(v)
  / sum_v X_HF_only_i(v)
```

Final prediction model:

```text
Y_HF3m_i = alpha
         + delta * HFScore_i
         + beta  * Y_Preop_i
         + error_i
```

For lower-is-better scales the expected direction is `delta < 0` (higher sweet-spot overlap predicts a lower post-treatment score).

Missing-data rule: a missing `Y_HF3m` for a scale, or a missing side's E-field, removes that patient from that scale only (per-scale `n` may fall below 16).

## Validation

- Use fully nested leave-one-patient-out cross-validation.
- Define coverage masks, fit voxel maps, and compute HF scores inside each training fold.
- Compare against the covariate-only model `Y_HF3m ~ Y_Preop`.
- Report LOOCV Pearson `r`, Spearman `rho`, MAE, RMSE, `Q2`, and permutation P value.
- Significance testing uses patient-level Freedman-Lane permutation with `B = 1000` and random seed `42`; the primary permutation statistic is LOOCV Pearson `r`.

## Downstream Visualization

Output root (parallel to the VTA-coverage cohort outputs), one subfolder per scale:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale>/
```

Export:

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
```

Map definitions:

- `direct_voxel_HF_coef.nii.gz` stores the raw `theta_HF(v)`; no per-voxel FDR is applied.
- `direct_voxel_HF_stability.nii.gz` is the fraction of LOOCV folds with `theta_HF(v) > 0`.
- `direct_voxel_HF_bootstrap_se.nii.gz` is the standard deviation of `theta_HF(v)` over patient-level bootstrap resampling (`B = 1000`, seed `42`).

Smoothing is optional and light (`FWHM = 1-2 mm`), applied after coefficient estimation and then re-masked to the territory. Report the unsmoothed map as the main output and the smoothed map as a sensitivity output.

Display the HF sweet/sour map with a diverging color scale centered at zero. Show low-coverage voxels (below the fold coverage rule) as transparent or gray. STN and SNr boundaries are overlays only.

## Interpretation Boundary

This model estimates local HF-only stimulation association with 3-month outcome. It should be interpreted as an HF efficacy heatmap within the STN/SNr stimulation territory, not as a pure anatomic STN map or as voxel-wise causal proof.
