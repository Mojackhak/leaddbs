# STN 3m Normative Connectome Seed-Target Model

## Research Question

Which STN-connected targets in public normative connectomes are associated with better STN-only 3-month clinical outcome?

This is a seed-target / fiber-derived target-level model. Individual streamlines construct target connectivity features and visualization outputs; individual top-correlated fibers are not the primary predictors.

## Endpoint

Primary endpoint:

```text
Y_STN3m = raw STN-only 3-month clinical score
```

Primary covariate:

```text
Y_Preop = raw preoperative clinical score
```

## Inputs

- Public Lead-DBS structural connectomes: dTOR-985 Full, MGH-USC HCP 32, and PPMI 85.
- STN seed and target masks from `STN-connected regions`.
- STN targets from the seed-target atlas registry, including M1, SMA, preSMA, premotor, GPe, GPi, DLPFC, ACC, OFC, vmPFC, and SNr.
- STN-only 3-month stimulation exposure maps or e-field-like proxy maps.
- Raw clinical scores from `subject_effect_origin.xlsx`.

## Feature Construction

For patient `i`, side `h`, and target `k`, define same-side normative streamlines:

```text
G_norm_STN(k,h) = streamlines connecting same-side STN seed to target P(k,h)
```

Streamline exposure:

```text
A_norm_i,h,j = max exposure along streamline j
```

Target-level side-specific connectivity:

```text
C_norm_STN(i,h,k) =
  sum_j A_norm_i,h,j / (number of streamlines in G_norm_STN(k,h) + lambda)
```

Patient-level bilateral feature:

```text
C_norm_STN_bilat(i,k) =
  (C_norm_STN(i,L,k) + C_norm_STN(i,R,k)) / 2
```

Use equal streamline weights within each target for the main analysis.

## Statistical Model

For each target `k`:

```text
Y_STN3m_i = alpha_k
          + theta_STN,k * Z(C_norm_STN_bilat(i,k))
          + beta_k      * Z(Y_Preop_i)
          + error_i,k
```

Benefit-oriented target weight:

```text
w_STN,k = -theta_STN,k   for lower-is-better scales
w_STN,k =  theta_STN,k   for SE-ADL
```

Select targets inside the training fold:

```text
S_STN = top sweet and sour STN targets
```

Patient-level normative STN target score:

```text
STNTargetScore_norm_i =
  sum_{k in S_STN} w_STN,k * Z(C_norm_STN_bilat(i,k))
  / sum_{k in S_STN} abs(w_STN,k)
```

Final prediction model:

```text
Y_STN3m_i = alpha
          + delta * STNTargetScore_norm_i
          + beta  * Y_Preop_i
          + error_i
```

## Validation

- Use fully nested leave-one-patient-out cross-validation.
- In each fold, estimate target weights, select targets, standardize features, and fit the final model using training patients only.
- Compare against covariate-only prediction: `Y_STN3m ~ Y_Preop`.
- Report cross-validated Pearson `r`, Spearman `rho`, MAE, RMSE, `Q2`, target selection stability, and permutation P value.
- Run PPMI first as a smoke test, then MGH, then dTOR with chunked access.

## Downstream Visualization

Export:

```text
target weights and target ranking tables
STNTargetScore_norm.csv
selected-target fiber subsets
target-weighted streamline density maps
STN_lh_coverage/sweet/sour/net/stability.nii.gz
STN_rh_coverage/sweet/sour/net/stability.nii.gz
```

The STN voxel maps are target-derived seed voxel maps created by back-projecting `w_STN,k` into the STN seed using normative streamline density. They are not direct voxel-wise discovery maps.

## Interpretation Boundary

This model is a network-informed normative connectome model. It identifies STN-connected targets associated with clinical benefit and provides fiber-derived anatomical explanation. It does not prove single-fiber causality and should not be described as a top-correlated-fiber primary model.
