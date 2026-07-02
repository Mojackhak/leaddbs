# HF-Adjusted LF-Only Add-On Gain Individualized DWI Seed-Target Model

## Research Question

Which subject-specific LF-only DWI seed-target connectivity features are associated with additional benefit after LF stimulation is added to HF stimulation, after adjusting for HF clinical state and predicted change in HF target engagement?

This is an individualized seed-target / fiber-derived target-level model. It uses subject-specific tractography and treats STN/SNr as contextual territory rather than the main model assignment rule.

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

- Individual DWI-derived tractography for subjects with usable DWI.
- HF-only stimulation exposure maps.
- HF and LF component exposure maps from HF+LF programming.
- Individualized DWI HF target-level model trained from HF-only outcomes.
- Seed and target masks from the connected-region atlas registry.
- DWI registration and tractography QC outputs.
- Raw HF-only and HF+LF clinical scores.

The model-matched HF adjustment is computed from the individualized HF target-level model:

```text
DeltaHFScore =
  S_HF_ind(C_ind_HF_component,HF+LF)
  - S_HF_ind(C_ind_HF_only,HF-only)
```

`DeltaHFScore` may be z-scored inside training folds, but no fixed scaling coefficient is imposed before regression.

## Feature Construction

For each subject-specific streamline `l`, define HF and LF activation:

```text
A_HF_i(l) = max_x E_HF_component_i(x on l) > tau
A_LF_i(l) = max_x E_LF_component_i(x on l) > tau
tau = 0.2 V/mm
```

The LF-only streamline weight is:

```text
w_LF_only_i(l) =
  peak_E_LF_i(l), if A_LF_i(l) and not A_HF_i(l)
  0,              otherwise
```

If a streamline is activated by both HF and LF components, it is attributed to the HF model and contributes to `DeltaHFScore` adjustment rather than to the LF-only predictor.

For each side and target `k`:

```text
C_ind_LF_only_side_i(k) =
  aggregate_l w_LF_only_i(l) for subject-specific streamlines l assigned to target k
```

Left and right target features are computed separately and then averaged:

```text
C_ind_LF_only_bilat_i(k) =
  (C_ind_LF_only_left_i(k) + C_ind_LF_only_right_i(k)) / 2
```

## Statistical Model

For each target `k`:

```text
Y_HFplusLF_post_i = alpha_k
                  + theta_LF(k) * C_ind_LF_only_bilat_i(k)
                  + beta_k      * Y_HF3m_i
                  + gamma_k     * DeltaHFScore_i
                  + error_i,k
```

Sensitivity model:

```text
Y_HFplusLF_post_i = alpha_k
                  + theta_LF(k) * C_ind_LF_only_bilat_i(k)
                  + beta_k      * Y_HF3m_i
                  + error_i,k
```

Benefit-oriented target weights:

```text
W_LF(k) = -theta_LF(k)   for lower-is-better scales
W_LF(k) =  theta_LF(k)   for SE-ADL
```

Patient-level individualized LF-only target score:

```text
LFTargetScore_ind_i =
  sum_k C_ind_LF_only_bilat_i(k) * W_LF(k)
  / (sum_k abs(C_ind_LF_only_bilat_i(k)) + lambda)
```

## Validation

- Run chronic 3-month and immediate endpoints as separate models.
- Use fully nested leave-one-patient-out cross-validation.
- Train the individualized HF target-level model inside each outer fold before computing fold-specific `DeltaHFScore`.
- Select LF targets, fit LF weights, and compute `LFTargetScore_ind` inside training folds.
- Compare against `Y_HFplusLF_post ~ Y_HF3m + DeltaHFScore`.
- Report DWI registration, tractography, and missing-feature QC separately.
- Report LOOCV Pearson `r`, Spearman `rho`, MAE, RMSE, `Q2`, and permutation P value.

## Downstream Visualization

Export:

```text
individualized_LF_only_target_weights.csv
individualized_LF_only_target_scores.csv
individualized_LF_only_loocv_predictions.csv
individualized_LF_only_permutation_summary.csv
individualized_LF_only_streamline_contribution_map.nii.gz
individualized_LF_only_subject_qc.csv
individualized_LF_only_HF_overlap_exclusion_summary.csv
```

Visualize subject-specific LF-only target weights, LF-only streamline contribution density, and excluded HF-overlap streamlines with STN/SNr territory overlays.

## Interpretation Boundary

This model estimates HF-adjusted LF-only target-level association using individualized DWI. It is more anatomically personalized than the normative model, but it remains limited by DWI quality, tractography uncertainty, registration, small sample size, and the rule that HF/LF-overlap streamlines are assigned to HF rather than LF.
