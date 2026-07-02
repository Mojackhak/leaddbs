# HF-Only 3m Normative Connectome Seed-Target Model

## Research Question

Which predefined targets connected to the HF stimulation territory show normative seed-target connectivity associated with better 3-month HF-only clinical outcome?

This is a seed-target / fiber-derived target-level model. Individual streamlines are used to build target features, QC, contribution maps, and visualizations. Single streamlines are not selected as the primary top-correlation predictors.

## Endpoint

Primary endpoint:

```text
Y_HF3m = raw HF-only 3-month clinical score
```

Primary covariate:

```text
Y_Preop = raw preoperative clinical score
```

## Inputs

- HF-only stimulation exposure maps for each side.
- Public structural connectomes available in Lead-DBS.
- Seed and target masks from the connected-region atlas registry.
- STN/SNr anatomical masks for overlay and territory QC.
- Raw clinical scores from `subject_effect_origin.xlsx`.

## Feature Construction

For each subject, side, and target `k`, compute a normative target connectivity feature from streamlines that connect the HF stimulation territory to target `k`:

```text
C_norm_HF_side_i(k) =
  aggregate_l peak_E_HF_i(l) for streamlines l assigned to target k
```

The primary activation weight is peak E-field or E-field-like exposure along the streamline. Binary VTA intersection and alternative exposure summaries are sensitivity analyses.

Left and right features are computed separately and then averaged:

```text
C_norm_HF_bilat_i(k) =
  (C_norm_HF_left_i(k) + C_norm_HF_right_i(k)) / 2
```

Target-level features may be normalized within subject or z-scored within training folds. Any scaling must be learned inside cross-validation folds.

## Statistical Model

For each target `k`:

```text
Y_HF3m_i = alpha_k
         + theta_HF(k) * C_norm_HF_bilat_i(k)
         + beta_k      * Y_Preop_i
         + error_i,k
```

Benefit-oriented target weights:

```text
W_HF(k) = -theta_HF(k)   for lower-is-better scales
W_HF(k) =  theta_HF(k)   for SE-ADL
```

Patient-level normative HF target score:

```text
HFTargetScore_norm_i =
  sum_k C_norm_HF_bilat_i(k) * W_HF(k)
  / (sum_k abs(C_norm_HF_bilat_i(k)) + lambda)
```

Final prediction model:

```text
Y_HF3m_i = alpha
         + delta * HFTargetScore_norm_i
         + beta  * Y_Preop_i
         + error_i
```

## Validation

- Use fully nested leave-one-patient-out cross-validation.
- Select targets, fit target weights, and compute `HFTargetScore_norm` only within training folds.
- Compare against `Y_HF3m ~ Y_Preop`.
- Report LOOCV Pearson `r`, Spearman `rho`, MAE, RMSE, `Q2`, and permutation P value.
- Repeat the analysis across available normative connectomes as connectome sensitivity analysis.

## Downstream Visualization

Export:

```text
normative_HF_target_weights.csv
normative_HF_target_scores.csv
normative_HF_loocv_predictions.csv
normative_HF_permutation_summary.csv
normative_HF_streamline_contribution_map.nii.gz
normative_HF_target_network_map.nii.gz
```

Visualize target weights, target-level predicted benefit, and streamline contribution density. STN/SNr boundaries and the HF stimulation territory are shown as contextual overlays.

## Interpretation Boundary

This model estimates an HF-only network-informed association. It supports target-level mechanism and prediction hypotheses, but it does not prove that an individual streamline is causal. The primary predictors are target-level features, not top-ranked single fibers.
