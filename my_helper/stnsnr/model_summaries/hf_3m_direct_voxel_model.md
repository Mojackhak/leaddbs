# HF-Only 3m Direct Voxel-Level Model

## Research Question

Which voxels in the high-frequency stimulation territory have HF-only exposure associated with better 3-month HF-only clinical outcome?

This is a direct local stimulation sweet-spot model. The former STN-only phase is interpreted as HF-only DBS territory, not as an anatomic STN-only model. STN/SNr masks are used for territory definition, coverage description, and visualization overlays, not for hard assignment of model effects to one nucleus.

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

## Inputs

- HF-only stimulation E-field or E-field-like exposure maps for each side.
- A stimulation-territory mask spanning the cohort-relevant STN/SNr and peri-STN/SNr region.
- STN/SNr anatomical masks for overlays and coverage summaries.
- Raw clinical scores from `subject_effect_origin.xlsx`.
- Left/right voxel correspondence or common-space sampling QC outputs.

## Feature Construction

Define a canonical stimulation territory:

```text
Omega_HF = cohort-covered HF stimulation territory within the STN/SNr and peri-STN/SNr region
```

The model does not split overlapping or border-zone voxels into STN versus SNr. Side-specific exposures are sampled in a common space and averaged:

```text
X_HF_only_i(v) = (X_HF_left_i(v) + X_HF_right_i(v)) / 2
```

Use continuous exposure for model fitting inside the coverage mask. The active-voxel threshold is used for coverage/QC and HF/LF overlap assignment:

```text
tau = 0.2 V/mm
Coverage(v) = sum_i 1[X_HF_only_i(v) > tau]
```

Use `Coverage(v) >= 8` as the preferred rule, with `0.18` and `0.22 V/mm` as threshold sensitivity analyses.

## Statistical Model

For each voxel `v`:

```text
Y_HF3m_i = alpha_v
         + theta_HF(v) * X_HF_only_i(v)
         + beta_v      * Y_Preop_i
         + error_i,v
```

Benefit-oriented map:

```text
M_HF(v) = -theta_HF(v)   for lower-is-better scales
M_HF(v) =  theta_HF(v)   for SE-ADL
```

Patient-level HF sweet-spot score:

```text
HFScore_i =
  sum_v X_HF_only_i(v) * M_HF(v)
  / (sum_v X_HF_only_i(v) + lambda)
```

Final prediction model:

```text
Y_HF3m_i = alpha
         + delta * HFScore_i
         + beta  * Y_Preop_i
         + error_i
```

## Validation

- Use fully nested leave-one-patient-out cross-validation.
- Define coverage masks, fit voxel maps, and compute HF scores inside each training fold.
- Compare against the covariate-only model `Y_HF3m ~ Y_Preop`.
- Report LOOCV Pearson `r`, Spearman `rho`, MAE, RMSE, `Q2`, and permutation P value.
- Use patient-level Freedman-Lane permutation for final significance testing.

## Downstream Visualization

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

Display the HF sweet/sour map with a diverging color scale centered at zero. Show low-coverage voxels as transparent or gray. STN and SNr boundaries are overlays only.

## Interpretation Boundary

This model estimates local HF-only stimulation association with 3-month outcome. It should be interpreted as an HF efficacy heatmap within the STN/SNr stimulation territory, not as a pure anatomic STN map or as voxel-wise causal proof.
