# SNr Gain Normative Connectome Seed-Target Model

## Research Question

Which SNr-connected targets in public normative connectomes are associated with additional benefit after SNr is added to STN stimulation?

This is a seed-target / fiber-derived target-level model. Individual streamlines construct target features and downstream visualization; they are not selected as top-correlated primary predictors.

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
Y_AB_post ~ C_norm_SNr_component(k) + Y_STN3m_domain + DeltaSTNScore_domain
```

Also report a clinical optimized strategy sensitivity model that omits `DeltaSTNScore`:

```text
Y_AB_post ~ C_norm_SNr_component(k) + Y_STN3m_domain
```

If these maps diverge, interpret the SNr target pattern as strongly coupled to STN component reprogramming.

## Inputs

- Public Lead-DBS structural connectomes: dTOR-985 Full, MGH-USC HCP 32, and PPMI 85.
- SNr seed and target masks from `SNr-connected regions`.
- SNr targets from the seed-target atlas registry, including VA/VLA/VLP/VM thalamus, STN, posterior putamen, caudate, PPN, superior colliculus, MD, CM, Pf, sPf, FEF, SMA, preSMA, premotor, M1, and DLPFC.
- SNr-component stimulation maps for each endpoint.
- Raw clinical scores.
- STN normative connectome seed-target efficacy models trained from pre-SNr STN-only data for each scale or symptom domain.
- `DeltaSTNScore` for each endpoint, computed from the corresponding normative STN target-level score.

The preferred STN adjustment is model-matched to this normative connectome seed-target SNr model. It must come from the STN 3m normative connectome seed-target model, not from a direct voxel-level or individualized DWI STN model:

```text
S_STN_norm(E) =
  sum_{k in S_STN_norm} w_STN,k_norm * Z_train(C_norm_STN_component(E,k))
  / sum_{k in S_STN_norm} abs(w_STN,k_norm)

DeltaSTNScore_3m =
  S_STN_norm,domain(E_STN_component,STN+SNr3m)
  - S_STN_norm,domain(E_STN_component,STN-only3m)

DeltaSTNScore_immediate =
  S_STN_norm,motor(E_STN_component,STN+SNrImmediate)
  - S_STN_norm,motor(E_STN_component,STN-only3m)
```

For lower-is-better scales, `w_STN,k_norm = -theta_STN,k`; for SE-ADL, `w_STN,k_norm = theta_STN,k`. Target selection, target weights, and `Z_train()` scaling must be learned from STN-only outcomes inside the same training fold before SNr is added.

## Feature Construction

For patient `i`, side `h`, and target `k`, define same-side normative SNr streamlines:

```text
G_norm_SNr(k,h) = streamlines connecting same-side SNr seed to target P(k,h)
```

Side-specific target connectivity:

```text
C_norm_SNr_component(i,h,k) =
  sum_j max exposure along streamline j
  / (number of streamlines in G_norm_SNr(k,h) + lambda)
```

Patient-level bilateral feature:

```text
C_norm_SNr_bilat(i,k) =
  (C_norm_SNr_component(i,L,k) + C_norm_SNr_component(i,R,k)) / 2
```

Use equal streamline weights within target for the main analysis.

For the main analysis, target connectivity uses peak SNr-component exposure along streamlines. Run these field-definition sensitivities:

```text
C_norm_SNr_component(k) = SNr-component peak exposure along SNr-target streamlines
C_norm_SNr_total(k)     = total STN+SNr peak exposure along the same streamlines
C_norm_SNr_residual(k)  = residualized total-field connectivity after regressing out STN-component connectivity
C_norm_SNr_shape(k)     = shape-normalized SNr-component connectivity
```

Because STN and SNr are adjacent, SNr-target connectivity can still reflect STN-SNr border-zone recruitment or passing fibers. Run border-zone sensitivity analyses:

```text
eroded SNr seed contribution
streamline seed-point distance to STN
exclude or down-weight seed contributions with d(seed, STN) <= 1.0 mm
exclude or down-weight seed contributions with d(seed, STN) <= 1.5 mm
cor(C_norm_SNr_bilat(k), DeltaSTNScore)
```

Targets with high collinearity with `DeltaSTNScore`, for example `abs(r) > 0.6`, should be interpreted as less SNr-specific.

## Statistical Model

For each endpoint and target `k`:

```text
Y_AB_post_domain_i = alpha_k
            + theta_SNr,k * Z(C_norm_SNr_bilat(i,k))
            + beta_k      * Z(Y_STN3m_domain_i)
            + gamma_k     * Z(DeltaSTNScore_domain_i)
            + error_i,k
```

Benefit-oriented target weight:

```text
w_SNr,k = -theta_SNr,k   for lower-is-better scales
w_SNr,k =  theta_SNr,k   for SE-ADL
```

Patient-level normative SNr target score:

```text
SNrTargetScore_norm_i =
  sum_{k in S_SNr} w_SNr,k * Z(C_norm_SNr_bilat(i,k))
  / sum_{k in S_SNr} abs(w_SNr,k)
```

Final prediction model:

```text
Y_AB_post_domain_i = alpha
            + delta * SNrTargetScore_norm_i
            + beta  * Y_STN3m_domain_i
            + gamma * DeltaSTNScore_domain_i
            + error_i
```

## Validation

- Run chronic gain and immediate gain separately.
- For chronic 3-month outcomes, run domain-specific models where data support them: motor, axial/gait, nonmotor, total, QoL, or ADL.
- For immediate outcomes, use motor-specific `Y_STN3m_motor` and motor-specific `DeltaSTNScore_immediate_motor`.
- Use fully nested leave-one-patient-out cross-validation.
- Estimate target weights, select targets, and standardize features inside training folds only.
- For strict out-of-sample prediction, train the model-matched normative STN seed-target model inside each outer fold before computing fold-specific `DeltaSTNScore`.
- Report the normative STN target-model validation used to build `DeltaSTNScore`: LOOCV `Q2`, improvement over `Y_STN3m ~ Y_Preop`, target selection stability, and target-weight stability. If the STN target model is unstable, downgrade `DeltaSTNScore` to exploratory adjustment.
- Compare against covariate-only prediction: `Y_AB_post_domain ~ Y_STN3m_domain + DeltaSTNScore_domain`.
- Compare against the clinical optimized strategy model without `DeltaSTNScore`.
- Run `DeltaSTNPhys` sensitivity using an outcome-independent STN-change measure such as charge-rate change, raw STN e-field energy change, STN VTA overlap change, or STN field centroid distance.
- Report component-field, total-field, residual-field, shape-normalized, eroded-SNr, distance-to-STN, and `DeltaSTNScore` collinearity sensitivity results.
- Define target inclusion, streamline-count, and coverage thresholds inside each training fold for prediction analyses.
- Report LOOCV metrics, target selection stability, cross-connectome agreement, and patient-level permutation P value. Do not emphasize target-wise P values as primary evidence with `n = 16`.

## Downstream Visualization

Export separately for chronic gain and immediate gain:

```text
target weights and target ranking tables
SNrTargetScore_norm.csv
selected-target fiber subsets
target-weighted streamline density maps
SNr_lh_coverage/sweet/sour/net/stability.nii.gz
SNr_rh_coverage/sweet/sour/net/stability.nii.gz
component_vs_total_field_sensitivity tables
residual_field_sensitivity tables
shape_normalized_sensitivity tables
seed_distance_to_STN summaries
DeltaSTNScore_collinearity tables
```

The SNr voxel maps are target-derived seed voxel maps created by back-projecting `w_SNr,k` into SNr using normative streamline density.

## Interpretation Boundary

This model estimates clinical optimization-informed SNr target-gain associations adjusted for STN 3-month baseline and concurrent STN reprogramming. It supports network interpretation but does not prove that any individual streamline or target is causally sufficient. Because STN and SNr are adjacent, SNr-target maps may reflect dorsal SNr, ventral STN, the STN-SNr border zone, or passing fibers. Unless an external model-matched normative STN target model is used, `DeltaSTNScore` is a same-cohort, pre-SNr-derived nuisance adjustment and may be noisy in a small cohort.

The main model estimates a STN-change-adjusted SNr add-on target-connectivity association, not the overall real-world effect of an optimized combined STN+SNr programming strategy.
