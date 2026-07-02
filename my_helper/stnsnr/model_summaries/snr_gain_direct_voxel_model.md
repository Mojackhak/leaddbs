# SNr Gain Direct Voxel-Level Model

## Research Question

Which SNr voxels have SNr-component stimulation exposure associated with additional benefit after SNr is added to STN stimulation?

This is a local SNr stimulation sweet spot model. It directly tests voxel-level SNr E-field exposure, not downstream target connectivity.

## Endpoint

Two endpoints are modeled separately:

```text
Chronic domain-specific gain:
  Y_AB3m_domain = raw STN+SNr 3-month clinical score for the selected domain
  covariates = Y_STN3m_domain + DeltaSTNScore_3m_domain

Immediate motor gain:
  Y_ABimmediate_motor = raw STN+SNr immediate motor score
  covariates = Y_STN3m_motor + DeltaSTNScore_immediate_motor
```

`Y_STN3m` controls the pre-SNr clinical state. `DeltaSTNScore` controls concurrent STN component reprogramming as an endpoint/domain-matched change in predicted STN efficacy-map alignment, not as a raw programming-parameter change.

The primary estimand is a STN-change-adjusted local SNr component exposure-response association:

```text
Y_AB_post ~ X_SNr_component(v) + Y_STN3m_domain + DeltaSTNScore_domain
```

Also report a clinical optimized strategy sensitivity model that omits `DeltaSTNScore`:

```text
Y_AB_post ~ X_SNr_component(v) + Y_STN3m_domain
```

If these maps diverge, interpret the SNr exposure pattern as strongly coupled to STN component reprogramming.

## Inputs

- SNr-component stimulation fields for STN+SNr 3-month and STN+SNr immediate programming.
- SNr seed masks from `SNr-connected regions`.
- STN-only 3-month raw score and post-combination raw scores.
- STN direct voxel-level efficacy maps trained from pre-SNr STN-only data for each scale or symptom domain.
- `DeltaSTNScore` for each endpoint, computed from the corresponding direct voxel-level STN efficacy map.
- Homologous left-right SNr voxel mapping QC outputs.

The preferred STN adjustment is model-matched to this direct voxel-level SNr model. It must come from the STN 3m direct voxel-level model, not from a seed-target or target-level STN model:

```text
S_STN_voxel(E) =
  sum_{u in Omega_STN} E(u) * M_STN(u)
  / (sum_{u in Omega_STN} E(u) + lambda)

DeltaSTNScore_3m =
  S_STN_voxel,domain(E_STN_component,STN+SNr3m)
  - S_STN_voxel,domain(E_STN_component,STN-only3m)

DeltaSTNScore_immediate =
  S_STN_voxel,motor(E_STN_component,STN+SNrImmediate)
  - S_STN_voxel,motor(E_STN_component,STN-only3m)
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

For the main analysis, `X_SNr_i(v)` is SNr-component-specific exposure, not the total tissue field. Run these field-definition sensitivities:

```text
X_SNr_component(v) = SNr-component field within SNr
X_SNr_total(v)     = total STN+SNr field within SNr
X_SNr_residual(v)  = residualized total field after regressing out STN-component field
X_SNr_shape(v)     = X_SNr_component(v) / (sum_u X_SNr_component(u) + lambda)
```

`X_SNr_total` addresses actual total tissue exposure. `X_SNr_shape` separates spatial field shape from global dose.

Because STN and SNr are anatomically adjacent, add border-zone sensitivity maps:

```text
SNr_eroded_0p5_to_1p0mm
d(v, STN) > 1.0 mm
d(v, STN) > 1.5 mm
cor(X_SNr_component(v), DeltaSTNScore)
```

Voxels with high collinearity with `DeltaSTNScore`, for example `abs(r) > 0.6`, should be interpreted as less SNr-specific.

Paired mask:

```text
Omega_pair = {v in right SNr mask: P_left_to_R(v) > 0.5}
```

Coverage mask:

```text
Coverage(v) = sum_i 1[X_SNr_i(v) > tau]
tau = 0.2 V/mm
```

Use `Coverage(v) >= 8/16` as the preferred full-sample rule. In LOOCV, define the mask inside each training fold:

```text
Coverage_minus_t(v) = sum_{i != t} 1[X_SNr_i(v) > tau]
```

Use `Coverage_minus_t(v) >= 8/15` as the preferred fold rule, with `>= 6/15` or `>= 5/15` as relaxed sensitivities.

## Statistical Model

For each endpoint and voxel `v`:

```text
Y_AB_post_domain_i = alpha_v
            + theta_SNr(v) * X_SNr_component_i(v)
            + beta_v       * Y_STN3m_domain_i
            + gamma_v      * DeltaSTNScore_domain_i
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
Y_AB_post_domain_i = alpha
            + delta * SweetSpotScore_i
            + beta  * Y_STN3m_domain_i
            + gamma * DeltaSTNScore_domain_i
            + error_i
```

## Validation

- Run chronic gain and immediate gain as separate models.
- For chronic 3-month outcomes, run domain-specific models where data support them: motor, axial/gait, nonmotor, total, QoL, or ADL.
- For immediate outcomes, use motor-specific `Y_STN3m_motor` and motor-specific `DeltaSTNScore_immediate_motor`.
- Use fully nested leave-one-patient-out cross-validation.
- Define coverage mask and fit voxel maps using training patients only.
- For strict out-of-sample prediction, train the model-matched direct voxel-level STN efficacy map inside each outer fold before computing fold-specific `DeltaSTNScore`.
- Report the direct voxel-level STN efficacy-map validation used to build `DeltaSTNScore`: LOOCV `Q2`, improvement over `Y_STN3m ~ Y_Preop`, and STN map stability. If the STN map is unstable, downgrade `DeltaSTNScore` to exploratory adjustment.
- Compare against covariate-only prediction: `Y_AB_post_domain ~ Y_STN3m_domain + DeltaSTNScore_domain`.
- Compare against the clinical optimized strategy model without `DeltaSTNScore`.
- Run `DeltaSTNPhys` sensitivity using an outcome-independent STN-change measure such as charge-rate change, raw STN e-field energy change, STN VTA overlap change, or STN field centroid distance.
- Report component-field, total-field, residual-field, shape-normalized, eroded-SNr, distance-to-STN, and collinearity sensitivity results.
- Report LOOCV Pearson `r`, Spearman `rho`, MAE, RMSE, `Q2`, and patient-level Freedman-Lane permutation P value. Do not emphasize voxel-wise P values as primary evidence with `n = 16`.

## Downstream Visualization

Export separately for chronic gain and immediate gain:

```text
direct_voxel_SNr_coverage.nii.gz
direct_voxel_SNr_coef.nii.gz
direct_voxel_SNr_sweet_sour.nii.gz
direct_voxel_SNr_stability.nii.gz
direct_voxel_SNr_bootstrap_se.nii.gz
direct_voxel_SNr_paired_mask.nii.gz
direct_voxel_SNr_total_field_sensitivity.nii.gz
direct_voxel_SNr_residual_field_sensitivity.nii.gz
direct_voxel_SNr_shape_normalized_sensitivity.nii.gz
direct_voxel_SNr_distance_to_STN.nii.gz
direct_voxel_SNr_deltaSTN_collinearity.nii.gz
direct_voxel_SNr_sweetspot_scores.csv
direct_voxel_SNr_loocv_predictions.csv
direct_voxel_SNr_permutation_summary.csv
direct_voxel_SNr_homologous_mapping_qc.json
```

Display maps with coverage overlays. Low-coverage SNr voxels should be transparent or gray.

## Interpretation Boundary

This model is a local SNr / STN-SNr border-zone stimulation association model for SNr add-on benefit. It is not a network mechanism model and should not be interpreted as pure causal evidence that stimulating a single SNr voxel guarantees benefit. Because STN and SNr are adjacent, apparent SNr sweet voxels may reflect dorsal SNr, ventral STN, the STN-SNr border zone, or passing fibers. Unless an external model-matched direct voxel-level STN efficacy map is used, `DeltaSTNScore` is a same-cohort, pre-SNr-derived nuisance adjustment and may be noisy in a small cohort.

The main model estimates a STN-change-adjusted SNr add-on association, not the overall real-world effect of an optimized combined STN+SNr programming strategy.
