# HF-Adjusted ULF-Only Add-On Gain Direct Voxel-Level Model

## Research Question

Which ULF-only voxels are associated with additional benefit after ULF stimulation is added to HF stimulation, after adjusting for the patient's HF clinical state and predicted change in HF efficacy?

This is a direct local ULF-only sweet-spot model. It does not define the main question as an anatomic SNr effect. The STN/SNr and peri-STN/SNr region is treated as one stimulation territory, with HF and ULF components separated by stimulation frequency and exposure overlap.


Frequency definitions:

```text
HF  = high-frequency stimulation component, frequency_Hz >= 100
ULF = ultra-low-frequency stimulation component, frequency_Hz <= 50
```

## Endpoint

Two endpoints are modeled separately:

```text
Chronic domain-specific endpoint:
  Y_HFplusULF_3m_domain = raw HF+ULF 3-month clinical score
  covariates = Y_HF3m_domain + DeltaHFScore_3m_domain

Immediate motor endpoint:
  Y_HFplusULF_immediate_motor = raw HF+ULF immediate motor score
  covariates = Y_HF3m_motor + DeltaHFScore_immediate_motor
```

The primary estimand is:

```text
HF-adjusted ULF-only add-on gain
```

## Inputs

- HF-only stimulation field from the pre-ULF phase.
- HF component and ULF component fields from HF+ULF programming.
- Direct voxel-level HF efficacy map trained from HF-only outcomes.
- Raw HF-only and HF+ULF clinical scores.
- STN/SNr anatomical masks for overlays and territory QC.

The model-matched HF adjustment is:

```text
S_HF_voxel(E) =
  sum_{u in Omega_HF} E(u) * M_HF(u)
  / (sum_{u in Omega_HF} E(u) + lambda)

DeltaHFScore_3m =
  S_HF_voxel,domain(E_HF_component,HF+ULF3m)
  - S_HF_voxel,domain(E_HF_only,HF-only3m)

DeltaHFScore_immediate =
  S_HF_voxel,motor(E_HF_component,HF+ULFImmediate)
  - S_HF_voxel,motor(E_HF_only,HF-only3m)
```

`DeltaHFScore` is not given a fixed biological scaling coefficient before modeling. It may be z-scored inside training folds for numerical stability; the regression coefficient estimates its association with outcome.

## Feature Construction

Define active HF and ULF exposure:

```text
HF_active_i(v) = E_HF_component_i(v) > tau
ULF_active_i(v) = E_ULF_component_i(v) > tau
tau = 0.2 V/mm
```

The ULF predictor uses only ULF-only exposure:

```text
X_ULF_only_i(v) =
  E_ULF_component_i(v), if ULF_active_i(v) and not HF_active_i(v)
  0,                   otherwise
```

If a voxel is activated by both HF and ULF components, it is attributed to the HF model and contributes to `DeltaHFScore` adjustment rather than to `X_ULF_only`.

Left and right ULF-only features are computed separately and then averaged:

```text
X_ULF_only_bilat_i(v) =
  (X_ULF_only_left_i(v) + X_ULF_only_right_i(v)) / 2
```

Run `0.18` and `0.22 V/mm` threshold sensitivities. Also report total-field and shape-normalized ULF sensitivities, but keep ULF-only exposure as the primary predictor.

## Statistical Model

For each endpoint and voxel `v`:

```text
Y_HFplusULF_post_i = alpha_v
                  + theta_ULF(v) * X_ULF_only_bilat_i(v)
                  + beta_v      * Y_HF3m_i
                  + gamma_v     * DeltaHFScore_i
                  + error_i,v
```

Sensitivity model:

```text
Y_HFplusULF_post_i = alpha_v
                  + theta_ULF(v) * X_ULF_only_bilat_i(v)
                  + beta_v      * Y_HF3m_i
                  + error_i,v
```

Benefit-oriented map:

```text
M_ULF(v) = -theta_ULF(v)   for lower-is-better scales
M_ULF(v) =  theta_ULF(v)   for SE-ADL
```

## Validation

- Run chronic 3-month and immediate endpoints as separate models.
- Use fully nested leave-one-patient-out cross-validation.
- Train the direct voxel-level HF map inside each outer fold before computing fold-specific `DeltaHFScore`.
- Compare against the covariate-only model `Y_HFplusULF_post ~ Y_HF3m + DeltaHFScore`.
- Report the sensitivity model without `DeltaHFScore`.
- Report LOOCV Pearson `r`, Spearman `rho`, MAE, RMSE, `Q2`, and patient-level Freedman-Lane permutation P value.

## Downstream Visualization

Export separately for chronic and immediate endpoints:

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
```

Display the ULF-only sweet/sour map with the excluded HF-overlap region and STN/SNr anatomical outlines as overlays.

## Interpretation Boundary

This model estimates HF-adjusted ULF-only add-on association. It is not an anatomic SNr gain model. Voxels co-activated by HF and ULF are treated as HF-dominant for the primary analysis, so the ULF map represents regions uniquely recruited by ULF stimulation after accounting for HF efficacy changes.
