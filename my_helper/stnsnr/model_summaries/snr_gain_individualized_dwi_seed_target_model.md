# SNr Gain Individualized DWI Seed-Target Model

## Research Question

Do patient-specific DWI seed-target connectivity features from SNr predict additional benefit after SNr is added to STN stimulation?

This is a seed-target / fiber-derived target-level model using individualized DWI tractography.

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

The primary estimand is a STN-change-adjusted SNr target-connectivity association:

```text
Y_AB_post ~ C_ind_SNr_component(k) + Y_STN3m_domain + DeltaSTNScore_domain
```

Also report a clinical optimized strategy sensitivity model that omits `DeltaSTNScore`:

```text
Y_AB_post ~ C_ind_SNr_component(k) + Y_STN3m_domain
```

If these maps diverge, interpret the SNr target pattern as strongly coupled to STN component reprogramming.

## Inputs

- Individualized DWI tractography from the imported DWI cohort.
- DWI registration outputs described in `dwi_registration_technical_details.md`.
- SNr seed and target masks projected into patient DWI space.
- SNr-component stimulation maps or e-field-like proxy maps projected into DWI space.
- Raw clinical scores.
- STN individualized DWI seed-target efficacy models trained from pre-SNr STN-only data for each scale or symptom domain.
- `DeltaSTNScore` for each endpoint, computed from the corresponding individualized DWI STN target-level score.

The preferred STN adjustment is model-matched to this individualized DWI seed-target SNr model. It must come from the STN 3m individualized DWI seed-target model, not from a direct voxel-level or normative-only STN model. For the preferred normative-guided individualized DWI SNr model, use the same normative-guided individualized DWI strategy for the STN adjustment; for an individualized-DWI-only sensitivity model, use an individualized-DWI-only STN adjustment.

```text
S_STN_ind(E) =
  sum_{k in S_STN_ind} w_STN,k_ind * Z_train(C_ind_STN_component(E,k))
  / sum_{k in S_STN_ind} abs(w_STN,k_ind)

DeltaSTNScore_3m =
  S_STN_ind,domain(E_STN_component,STN+SNr3m)
  - S_STN_ind,domain(E_STN_component,STN-only3m)

DeltaSTNScore_immediate =
  S_STN_ind,motor(E_STN_component,STN+SNrImmediate)
  - S_STN_ind,motor(E_STN_component,STN-only3m)
```

For lower-is-better scales, `w_STN,k_ind = -theta_STN,k`; for SE-ADL, `w_STN,k_ind = theta_STN,k`. Target selection, target weights, patient-specific target reconstruction, and `Z_train()` scaling must be learned or computed without the held-out patient in strict prediction.

## Feature Construction

For patient `i`, side `h`, and target `k`, define individualized SNr streamlines:

```text
G_ind_SNr(i,k,h) = patient i streamlines connecting same-side SNr seed to target P(k,h)
```

Side-specific target connectivity:

```text
C_ind_SNr_component(i,h,k) =
  sum_j max exposure along patient streamline j
  / (number of streamlines in G_ind_SNr(i,k,h) + lambda)
```

Patient-level bilateral feature:

```text
C_ind_SNr_bilat(i,k) =
  (C_ind_SNr_component(i,L,k) + C_ind_SNr_component(i,R,k)) / 2
```

Run target coverage QC before modeling. Low-reconstruction targets should be excluded from primary interpretation.

For the main analysis, target connectivity uses peak SNr-component exposure along patient-specific streamlines. Run these field-definition sensitivities:

```text
C_ind_SNr_component(k) = SNr-component peak exposure along individualized SNr-target streamlines
C_ind_SNr_total(k)     = total STN+SNr peak exposure along the same streamlines
C_ind_SNr_residual(k)  = residualized total-field connectivity after regressing out STN-component connectivity
C_ind_SNr_shape(k)     = shape-normalized SNr-component connectivity
```

Because STN and SNr are adjacent, individualized SNr-target streamlines can still reflect STN-SNr border-zone recruitment, registration error, or passing fibers. Run border-zone sensitivity analyses:

```text
eroded SNr seed contribution
streamline seed-point distance to STN
exclude or down-weight seed contributions with d(seed, STN) <= 1.0 mm
exclude or down-weight seed contributions with d(seed, STN) <= 1.5 mm
cor(C_ind_SNr_bilat(k), DeltaSTNScore)
```

Targets with high collinearity with `DeltaSTNScore`, for example `abs(r) > 0.6`, should be interpreted as less SNr-specific.

## Statistical Model

Preferred model:

```text
normative-guided individualized DWI
```

Use normative connectome training folds to determine `S_SNr` and `w_SNr,k`, then compute individualized DWI score:

```text
SNrTargetScore_ind_norm_i =
  sum_{k in S_SNr_norm} w_SNr,k_norm * Z(C_ind_SNr_bilat(i,k))
  / sum_{k in S_SNr_norm} abs(w_SNr,k_norm)
```

Final model:

```text
Y_AB_post_domain_i = alpha
            + delta * SNrTargetScore_ind_norm_i
            + beta  * Y_STN3m_domain_i
            + gamma * DeltaSTNScore_domain_i
            + error_i
```

Sensitivity model:

```text
individualized-DWI-only
```

In that sensitivity model, `S_SNr` and `w_SNr,k` are learned from individualized DWI features inside each training fold.

## Validation

- Run chronic gain and immediate gain separately.
- For chronic 3-month outcomes, run domain-specific models where data support them: motor, axial/gait, nonmotor, total, QoL, or ADL.
- For immediate outcomes, use motor-specific `Y_STN3m_motor` and motor-specific `DeltaSTNScore_immediate_motor`.
- Use fully nested leave-one-patient-out cross-validation.
- For the normative-guided model, normative target weights and selected targets must be learned without the held-out patient.
- For DWI-only sensitivity, target weights, target selection, and standardization must occur inside training folds.
- For strict out-of-sample prediction, train the model-matched individualized DWI STN seed-target model inside each outer fold before computing fold-specific `DeltaSTNScore`.
- Report the individualized DWI STN target-model validation used to build `DeltaSTNScore`: LOOCV `Q2`, improvement over `Y_STN3m ~ Y_Preop`, target reconstruction coverage, target selection stability, and target-weight stability. If the individualized STN target model is unstable or sparse, downgrade `DeltaSTNScore` to exploratory adjustment.
- Compare against covariate-only prediction `Y_AB_post_domain ~ Y_STN3m_domain + DeltaSTNScore_domain` and against the normative-only model.
- Compare against the clinical optimized strategy model without `DeltaSTNScore`.
- Run `DeltaSTNPhys` sensitivity using an outcome-independent STN-change measure such as charge-rate change, raw STN e-field energy change, STN VTA overlap change, or STN field centroid distance.
- Report component-field, total-field, residual-field, shape-normalized, eroded-SNr, distance-to-STN, and `DeltaSTNScore` collinearity sensitivity results.
- Define target inclusion, streamline-count, and reconstruction coverage thresholds inside each training fold for prediction analyses.
- Report DWI coverage, target missingness, LOOCV metrics, agreement with normative SNr target patterns, and patient-level permutation P value. Do not emphasize target-wise P values as primary evidence with `n = 16`.

## Downstream Visualization

Export separately for chronic gain and immediate gain:

```text
DWI target coverage tables
C_ind_SNr_bilat matrices
SNrTargetScore_ind_norm.csv
SNrTargetScore_ind_only.csv
individualized-DWI selected-target fiber subsets
coverage-weighted group SNr seed voxel maps
component_vs_total_field_sensitivity tables
residual_field_sensitivity tables
shape_normalized_sensitivity tables
seed_distance_to_STN summaries
DeltaSTNScore_collinearity tables
```

Group SNr voxel maps are generated by warping patient-specific DWI target-derived maps to template space and averaging with voxel coverage weights.

## Interpretation Boundary

This model tests whether the SNr target-connectivity pattern associated with add-on benefit is present in each patient's own DWI tractography. It is subject-specific but limited by DWI tractography quality, registration, target coverage, and streamline false positives or false negatives. Missing or sparse streamlines should be treated as QC limitations, not evidence of absent biology. Because STN and SNr are adjacent, SNr-target maps may reflect dorsal SNr, ventral STN, the STN-SNr border zone, registration uncertainty, or passing fibers. Unless an external model-matched individualized DWI STN target model is used, `DeltaSTNScore` is a same-cohort, pre-SNr-derived nuisance adjustment and may be noisy in a small cohort.

The main model estimates a STN-change-adjusted SNr add-on target-connectivity association, not the overall real-world effect of an optimized combined STN+SNr programming strategy.
