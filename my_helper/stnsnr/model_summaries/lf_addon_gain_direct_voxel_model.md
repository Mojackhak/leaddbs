# HF-Adjusted LF-Only Add-On Gain Direct Voxel-Level Model

## Research Question

Which LF-only voxels are associated with additional benefit after LF stimulation is added to HF stimulation, after adjusting for the patient's HF clinical state and predicted change in HF efficacy?

This is a direct local LF-only sweet-spot model. It does not define the main question as an anatomic SNr effect. The STN/SNr and peri-STN/SNr region is treated as one stimulation territory, with HF and LF components separated by stimulation frequency and exposure overlap.

## Endpoint

Two endpoints are modeled separately:

```text
Chronic domain-specific endpoint:
  Y_HFplusLF_3m_domain = raw HF+LF 3-month clinical score
  covariates = Y_HF3m_domain + DeltaHFScore_3m_domain

Immediate motor endpoint:
  Y_HFplusLF_immediate_motor = raw HF+LF immediate motor score
  covariates = Y_HF3m_motor + DeltaHFScore_immediate_motor
```

The primary estimand is:

```text
HF-adjusted LF-only add-on gain
```

## Inputs

- HF-only stimulation field from the pre-LF phase.
- HF component and LF component fields from HF+LF programming.
- Direct voxel-level HF efficacy map trained from HF-only outcomes.
- Raw HF-only and HF+LF clinical scores.
- STN/SNr anatomical masks for overlays and territory QC.

The model-matched HF adjustment is:

```text
S_HF_voxel(E) =
  sum_{u in Omega_HF} E(u) * M_HF(u)
  / (sum_{u in Omega_HF} E(u) + lambda)

DeltaHFScore_3m =
  S_HF_voxel,domain(E_HF_component,HF+LF3m)
  - S_HF_voxel,domain(E_HF_only,HF-only3m)

DeltaHFScore_immediate =
  S_HF_voxel,motor(E_HF_component,HF+LFImmediate)
  - S_HF_voxel,motor(E_HF_only,HF-only3m)
```

`DeltaHFScore` is not given a fixed biological scaling coefficient before modeling. It may be z-scored inside training folds for numerical stability; the regression coefficient estimates its association with outcome.

## Feature Construction

Define active HF and LF exposure:

```text
HF_active_i(v) = E_HF_component_i(v) > tau
LF_active_i(v) = E_LF_component_i(v) > tau
tau = 0.2 V/mm
```

The LF predictor uses only LF-only exposure:

```text
X_LF_only_i(v) =
  E_LF_component_i(v), if LF_active_i(v) and not HF_active_i(v)
  0,                   otherwise
```

If a voxel is activated by both HF and LF components, it is attributed to the HF model and contributes to `DeltaHFScore` adjustment rather than to `X_LF_only`.

Left and right LF-only features are computed separately and then averaged:

```text
X_LF_only_bilat_i(v) =
  (X_LF_only_left_i(v) + X_LF_only_right_i(v)) / 2
```

Run `0.18` and `0.22 V/mm` threshold sensitivities. Also report total-field and shape-normalized LF sensitivities, but keep LF-only exposure as the primary predictor.

## Statistical Model

For each endpoint and voxel `v`:

```text
Y_HFplusLF_post_i = alpha_v
                  + theta_LF(v) * X_LF_only_bilat_i(v)
                  + beta_v      * Y_HF3m_i
                  + gamma_v     * DeltaHFScore_i
                  + error_i,v
```

Sensitivity model:

```text
Y_HFplusLF_post_i = alpha_v
                  + theta_LF(v) * X_LF_only_bilat_i(v)
                  + beta_v      * Y_HF3m_i
                  + error_i,v
```

Benefit-oriented map:

```text
M_LF(v) = -theta_LF(v)   for lower-is-better scales
M_LF(v) =  theta_LF(v)   for SE-ADL
```

## Validation

- Run chronic 3-month and immediate endpoints as separate models.
- Use fully nested leave-one-patient-out cross-validation.
- Train the direct voxel-level HF map inside each outer fold before computing fold-specific `DeltaHFScore`.
- Compare against the covariate-only model `Y_HFplusLF_post ~ Y_HF3m + DeltaHFScore`.
- Report the sensitivity model without `DeltaHFScore`.
- Report LOOCV Pearson `r`, Spearman `rho`, MAE, RMSE, `Q2`, and patient-level Freedman-Lane permutation P value.

## Downstream Visualization

Export separately for chronic and immediate endpoints:

```text
direct_voxel_LF_only_coverage.nii.gz
direct_voxel_LF_only_coef.nii.gz
direct_voxel_LF_only_sweet_sour.nii.gz
direct_voxel_LF_only_stability.nii.gz
direct_voxel_LF_only_bootstrap_se.nii.gz
direct_voxel_LF_only_scores.csv
direct_voxel_LF_only_loocv_predictions.csv
direct_voxel_LF_only_permutation_summary.csv
direct_voxel_LF_only_HF_overlap_exclusion_mask.nii.gz
```

Display the LF-only sweet/sour map with the excluded HF-overlap region and STN/SNr anatomical outlines as overlays.

## Interpretation Boundary

This model estimates HF-adjusted LF-only add-on association. It is not an anatomic SNr gain model. Voxels co-activated by HF and LF are treated as HF-dominant for the primary analysis, so the LF map represents regions uniquely recruited by LF stimulation after accounting for HF efficacy changes.
