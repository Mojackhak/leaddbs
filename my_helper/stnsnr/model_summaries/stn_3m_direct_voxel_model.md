# STN 3m Direct Voxel-Level Model

## Research Question

Which STN voxels have STN-only stimulation exposure associated with better 3-month STN-only clinical outcome?

This is a local stimulation sweet spot model. It directly tests voxel-level STN E-field exposure, not target connectivity or fiber-level mechanisms.

## Endpoint

Primary endpoint:

```text
Y_STN3m = raw STN-only 3-month clinical score
```

Primary covariate:

```text
Y_Preop = raw preoperative clinical score
```

For lower-is-better scales, positive model maps indicate benefit after sign flip. For SE-ADL, positive coefficients already indicate benefit.

## Inputs

- STN-only 3-month stimulation field for left and right STN components.
- STN seed masks from `STN-connected regions`.
- Raw clinical scores from `subject_effect_origin.xlsx`.
- Homologous left-right STN voxel mapping QC outputs.

## Feature Construction

Use the right STN as the canonical voxel grid. For each canonical right voxel center `c_R(v)`, define the homologous left continuous coordinate:

```text
c_L(v) = phi_inverse_L_to_R(c_R(v))
```

Sample the left E-field at `c_L(v)` using trilinear interpolation:

```text
E_L_to_R_i(v) = interp_linear(E_L_i, c_L(v))
```

Define patient-level bilateral STN exposure:

```text
X_STN3m_i(v) = (E_R_i(c_R(v)) + E_L_to_R_i(v)) / 2
```

The paired analysis mask is:

```text
Omega_pair = {v in right STN mask: P_left_to_R(v) > 0.5}
```

Coverage mask:

```text
Coverage(v) = sum_i 1[X_STN3m_i(v) > tau]
tau = 0.2 V/mm
```

Use `Coverage(v) >= 8` as the preferred rule, with `>= 5` or `>= 6` as exploratory relaxed thresholds if coverage is too sparse.

## Statistical Model

For each voxel `v`:

```text
Y_STN3m_i = alpha_v
          + theta_STN(v) * X_STN3m_i(v)
          + beta_v       * Y_Preop_i
          + error_i,v
```

Benefit-oriented map:

```text
M_STN(v) = -theta_STN(v)   for lower-is-better scales
M_STN(v) =  theta_STN(v)   for SE-ADL
```

Patient-level sweet spot score:

```text
SweetSpotScore_i =
  sum_v X_STN3m_i(v) * M_STN(v)
  / (sum_v X_STN3m_i(v) + lambda)
```

Final prediction model:

```text
Y_STN3m_i = alpha
          + delta * SweetSpotScore_i
          + beta  * Y_Preop_i
          + error_i
```

## Validation

- Use fully nested leave-one-patient-out cross-validation.
- Define coverage mask, fit voxel map, and compute sweet spot scores inside each training fold.
- Compare against covariate-only prediction: `Y_STN3m ~ Y_Preop`.
- Report LOOCV Pearson `r`, Spearman `rho`, MAE, RMSE, `Q2`, and permutation P value.
- Use patient-level Freedman-Lane permutation for final significance testing.

## Downstream Visualization

Export:

```text
direct_voxel_STN_coverage.nii.gz
direct_voxel_STN_coef.nii.gz
direct_voxel_STN_sweet_sour.nii.gz
direct_voxel_STN_stability.nii.gz
direct_voxel_STN_bootstrap_se.nii.gz
direct_voxel_STN_paired_mask.nii.gz
direct_voxel_STN_sweetspot_scores.csv
direct_voxel_STN_loocv_predictions.csv
direct_voxel_STN_permutation_summary.csv
direct_voxel_STN_homologous_mapping_qc.json
```

Display the sweet/sour map with a diverging color scale centered at zero. Show low-coverage voxels as transparent or gray. If smoothing is used, use only `1-2 mm` FWHM and also report unsmoothed maps.

## Interpretation Boundary

This model is a direct local STN stimulation association model. It answers where STN exposure is associated with STN-only 3-month outcome. It does not explain which downstream targets or fibers mediate the effect, and it should not be interpreted as definitive voxel-wise causal evidence.
