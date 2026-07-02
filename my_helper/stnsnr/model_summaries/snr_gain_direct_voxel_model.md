# SNr Gain Direct Voxel-Level Model

## Research Question

Which SNr voxels have SNr-component stimulation exposure associated with additional benefit after SNr is added to STN stimulation?

This is a local SNr stimulation sweet spot model. It directly tests voxel-level SNr E-field exposure, not downstream target connectivity.

## Endpoint

Two endpoints are modeled separately:

```text
Chronic gain:
  Y_AB3m = raw STN+SNr 3-month clinical score
  covariates = Y_STN3m + DeltaSTNScore_3m

Immediate gain:
  Y_ABimmediate = raw STN+SNr immediate clinical score
  covariates = Y_STN3m + DeltaSTNScore_immediate
```

`Y_STN3m` controls the pre-SNr clinical state. `DeltaSTNScore` controls concurrent STN component reprogramming as an endpoint/domain-matched change in predicted STN efficacy-map alignment, not as a raw programming-parameter change.

## Inputs

- SNr-component stimulation fields for STN+SNr 3-month and STN+SNr immediate programming.
- SNr seed masks from `SNr-connected regions`.
- STN-only 3-month raw score and post-combination raw scores.
- STN-only efficacy maps trained from pre-SNr STN-only data for each scale or symptom domain.
- `DeltaSTNScore` for each endpoint, computed from the corresponding STN efficacy map.
- Homologous left-right SNr voxel mapping QC outputs.

The preferred STN adjustment is:

```text
S_STN(E) =
  sum_{u in Omega_STN} E(u) * M_STN(u)
  / (sum_{u in Omega_STN} E(u) + lambda)

DeltaSTNScore_3m =
  S_STN_domain(E_STN_component,STN+SNr3m)
  - S_STN_domain(E_STN_component,STN-only3m)

DeltaSTNScore_immediate =
  S_STN_motor(E_STN_component,STN+SNrImmediate)
  - S_STN_motor(E_STN_component,STN-only3m)
```

For lower-is-better scales, `M_STN = -theta_STN`; for SE-ADL, `M_STN = theta_STN`. The STN map must be trained only on STN-only outcomes before SNr is added.

## Feature Construction

Use the right SNr as the canonical voxel grid. For each canonical right voxel center `c_R(v)`, define the homologous left continuous coordinate:

```text
c_L(v) = phi_inverse_L_to_R(c_R(v))
```

Sample the left SNr E-field with trilinear interpolation:

```text
E_L_to_R_i(v) = interp_linear(E_L_i, c_L(v))
```

Patient-level bilateral SNr exposure:

```text
X_SNr_i(v) = (E_R_i(c_R(v)) + E_L_to_R_i(v)) / 2
```

Paired mask:

```text
Omega_pair = {v in right SNr mask: P_left_to_R(v) > 0.5}
```

Coverage mask:

```text
Coverage(v) = sum_i 1[X_SNr_i(v) > tau]
tau = 0.2 V/mm
```

Use `Coverage(v) >= 8` as the preferred rule, with `>= 5` or `>= 6` as exploratory relaxed thresholds.

## Statistical Model

For each endpoint and voxel `v`:

```text
Y_AB_post_i = alpha_v
            + theta_SNr(v) * X_SNr_i(v)
            + beta_v       * Y_STN3m_i
            + gamma_v      * DeltaSTNScore_i
            + error_i,v
```

Benefit-oriented map:

```text
M_SNr(v) = -theta_SNr(v)   for lower-is-better scales
M_SNr(v) =  theta_SNr(v)   for SE-ADL
```

Patient-level direct voxel score:

```text
SweetSpotScore_i =
  sum_v X_SNr_i(v) * M_SNr(v)
  / (sum_v X_SNr_i(v) + lambda)
```

Final prediction model:

```text
Y_AB_post_i = alpha
            + delta * SweetSpotScore_i
            + beta  * Y_STN3m_i
            + gamma * DeltaSTNScore_i
            + error_i
```

## Validation

- Run chronic gain and immediate gain as separate models.
- Use fully nested leave-one-patient-out cross-validation.
- Define coverage mask and fit voxel maps using training patients only.
- For strict out-of-sample prediction, train the STN efficacy map inside each outer fold before computing fold-specific `DeltaSTNScore`.
- Compare against covariate-only prediction: `Y_AB_post ~ Y_STN3m + DeltaSTNScore`.
- Run `DeltaSTNPhys` sensitivity using an outcome-independent STN-change measure such as charge-rate change, raw STN e-field energy change, STN VTA overlap change, or STN field centroid distance.
- Report LOOCV Pearson `r`, Spearman `rho`, MAE, RMSE, `Q2`, and patient-level Freedman-Lane permutation P value.

## Downstream Visualization

Export separately for chronic gain and immediate gain:

```text
direct_voxel_SNr_coverage.nii.gz
direct_voxel_SNr_coef.nii.gz
direct_voxel_SNr_sweet_sour.nii.gz
direct_voxel_SNr_stability.nii.gz
direct_voxel_SNr_bootstrap_se.nii.gz
direct_voxel_SNr_paired_mask.nii.gz
direct_voxel_SNr_sweetspot_scores.csv
direct_voxel_SNr_loocv_predictions.csv
direct_voxel_SNr_permutation_summary.csv
direct_voxel_SNr_homologous_mapping_qc.json
```

Display maps with coverage overlays. Low-coverage SNr voxels should be transparent or gray.

## Interpretation Boundary

This model is a local SNr stimulation association model for SNr add-on benefit. It is not a network mechanism model and should not be interpreted as pure causal evidence that stimulating a single SNr voxel guarantees benefit. Unless an external STN efficacy map is used, `DeltaSTNScore` is a same-cohort, pre-SNr-derived nuisance adjustment and may be noisy in a small cohort.
