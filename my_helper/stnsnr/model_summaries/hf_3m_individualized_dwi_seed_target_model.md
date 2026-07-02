# HF-Only 3m Individualized DWI Seed-Target Model

## Research Question

Which subject-specific DWI seed-target connectivity features from the HF stimulation territory are associated with better 3-month HF-only clinical outcome?

This is an individualized seed-target / fiber-derived target-level model. It uses each subject's DWI-derived tractography rather than only public normative connectomes.

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

- Individual DWI-derived tractography for subjects with usable DWI.
- HF-only stimulation exposure maps for each side.
- Seed and target masks from the connected-region atlas registry.
- DWI-to-MNI and MNI-to-DWI registration QC outputs.
- STN/SNr anatomical masks for overlay and territory QC.
- Raw clinical scores from `subject_effect_origin.xlsx`.

## Feature Construction

For each subject, side, and target `k`, compute an individualized target connectivity feature from the subject's own streamlines:

```text
C_ind_HF_side_i(k) =
  aggregate_l peak_E_HF_i(l) for subject-specific streamlines l assigned to target k
```

The primary activation weight is peak E-field or E-field-like exposure along the streamline. SIFT2 weights, streamline count, binary VTA intersection, and alternative exposure summaries are sensitivity analyses when available.

Left and right features are computed separately and then averaged:

```text
C_ind_HF_bilat_i(k) =
  (C_ind_HF_left_i(k) + C_ind_HF_right_i(k)) / 2
```

Feature scaling, target filtering, and any imputation must be learned inside training folds.

## Statistical Model

For each target `k`:

```text
Y_HF3m_i = alpha_k
         + theta_HF(k) * C_ind_HF_bilat_i(k)
         + beta_k      * Y_Preop_i
         + error_i,k
```

Benefit-oriented target weights:

```text
W_HF(k) = -theta_HF(k)   for lower-is-better scales
W_HF(k) =  theta_HF(k)   for SE-ADL
```

Patient-level individualized HF target score:

```text
HFTargetScore_ind_i =
  sum_k C_ind_HF_bilat_i(k) * W_HF(k)
  / (sum_k abs(C_ind_HF_bilat_i(k)) + lambda)
```

Final prediction model:

```text
Y_HF3m_i = alpha
         + delta * HFTargetScore_ind_i
         + beta  * Y_Preop_i
         + error_i
```

## Validation

- Use fully nested leave-one-patient-out cross-validation.
- Perform target selection, feature scaling, model fitting, and score computation inside each training fold.
- Compare against `Y_HF3m ~ Y_Preop`.
- Report LOOCV Pearson `r`, Spearman `rho`, MAE, RMSE, `Q2`, and permutation P value.
- Report tractography and registration QC failure rates separately from predictive performance.

## Downstream Visualization

Export:

```text
individualized_HF_target_weights.csv
individualized_HF_target_scores.csv
individualized_HF_loocv_predictions.csv
individualized_HF_permutation_summary.csv
individualized_HF_streamline_contribution_map.nii.gz
individualized_HF_subject_qc.csv
```

Visualize target-level weights, subject-level connectivity contribution maps, and HF stimulation territory overlays.

## Interpretation Boundary

This model estimates individualized HF-only target-level associations. It may better reflect patient-specific anatomy than normative connectomes, but its reliability depends on DWI quality, registration, tractography parameters, and the small sample size.
