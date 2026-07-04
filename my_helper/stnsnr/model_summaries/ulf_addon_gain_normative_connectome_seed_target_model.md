# HF-Adjusted ULF-Only Add-On Gain Normative Connectome Seed-Target Model

## Research Question

Which ULF-only normative seed-target connectivity features are associated with additional benefit after ULF stimulation is added to HF stimulation, after adjusting for HF clinical state and model-predicted change in HF fiber engagement?

This is a seed-target / fiber-derived target-level model. The main predictor is target-level ULF-only connectivity, not top-ranked single streamlines.


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

- Public structural connectomes available in Lead-DBS.
- HF-only stimulation exposure maps.
- HF and ULF component exposure maps from HF+ULF programming.
- Normative HF fiber-level model trained from HF-only outcomes.
- Seed and target masks from the connected-region atlas registry.
- Raw HF-only and HF+ULF clinical scores.

The model-matched HF adjustment is computed from the normative HF fiber-level model described in [`hf_3m_normative_connectome_fiber_model.md`](hf_3m_normative_connectome_fiber_model.md):

```text
DeltaHFScore =
  S_HF_norm_fiber(E_HF_component,HF+ULF)
  - S_HF_norm_fiber(E_HF_only,HF-only)

S_HF_norm_fiber(E) = HFFiberScore_top5_mean(E)
```

`DeltaHFScore` may be z-scored inside training folds, but no fixed scaling coefficient is imposed before regression.

## Feature Construction

For each streamline `l`, define HF and ULF activation:

```text
A_HF_i(l) = max_x E_HF_component_i(x on l) > tau
A_ULF_i(l) = max_x E_ULF_component_i(x on l) > tau
tau = 0.2 V/mm
```

The ULF-only streamline weight is:

```text
w_ULF_only_i(l) =
  peak_E_ULF_i(l), if A_ULF_i(l) and not A_HF_i(l)
  0,              otherwise
```

If a streamline is activated by both HF and ULF components, it is attributed to the HF model and contributes to `DeltaHFScore` adjustment rather than to the ULF-only predictor.

For each side and target `k`:

```text
C_norm_ULF_only_side_i(k) =
  aggregate_l w_ULF_only_i(l) for streamlines l assigned to target k
```

Left and right target features are computed separately and then averaged:

```text
C_norm_ULF_only_bilat_i(k) =
  (C_norm_ULF_only_left_i(k) + C_norm_ULF_only_right_i(k)) / 2
```

## Statistical Model

For each target `k`:

```text
Y_HFplusULF_post_i = alpha_k
                  + theta_ULF(k) * C_norm_ULF_only_bilat_i(k)
                  + beta_k      * Y_HF3m_i
                  + gamma_k     * DeltaHFScore_i
                  + error_i,k
```

Sensitivity model:

```text
Y_HFplusULF_post_i = alpha_k
                  + theta_ULF(k) * C_norm_ULF_only_bilat_i(k)
                  + beta_k      * Y_HF3m_i
                  + error_i,k
```

Benefit-oriented target weights:

```text
W_ULF(k) = -theta_ULF(k)   for lower-is-better scales
W_ULF(k) =  theta_ULF(k)   for SE-ADL
```

Patient-level ULF-only target score:

```text
ULFTargetScore_norm_i =
  sum_k C_norm_ULF_only_bilat_i(k) * W_ULF(k)
  / (sum_k abs(C_norm_ULF_only_bilat_i(k)) + lambda)
```

## Validation

- Run chronic 3-month and immediate endpoints as separate models.
- Use fully nested leave-one-patient-out cross-validation.
- Train the normative HF fiber-level model inside each outer fold before computing fold-specific `DeltaHFScore`.
- Select ULF targets, fit ULF weights, and compute `ULFTargetScore_norm` inside training folds.
- Compare against `Y_HFplusULF_post ~ Y_HF3m + DeltaHFScore`.
- Repeat across available normative connectomes and threshold sensitivities.
- Report LOOCV Pearson `r`, Spearman `rho`, MAE, RMSE, `Q2`, and permutation P value.

## Downstream Visualization

Export:

```text
normative_ULF_only_target_weights.csv
normative_ULF_only_target_scores.csv
normative_ULF_only_loocv_predictions.csv
normative_ULF_only_permutation_summary.csv
normative_ULF_only_streamline_contribution_map.nii.gz
normative_ULF_only_target_network_map.nii.gz
normative_ULF_only_HF_overlap_exclusion_summary.csv
```

Visualize ULF-only target weights, ULF-only streamline contribution density, and excluded HF-overlap streamlines. STN/SNr boundaries remain contextual overlays.

## Interpretation Boundary

This model estimates HF-adjusted ULF-only target-level association using public connectomes. It does not claim that ULF effects are anatomically restricted to SNr. The ULF predictor represents only streamlines uniquely recruited by ULF after HF-overlap streamlines are assigned to the HF adjustment.
