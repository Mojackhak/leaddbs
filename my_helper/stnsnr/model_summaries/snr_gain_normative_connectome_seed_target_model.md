# SNr Gain Normative Connectome Seed-Target Model

## Research Question

Which SNr-connected targets in public normative connectomes are associated with additional benefit after SNr is added to STN stimulation?

This is a seed-target / fiber-derived target-level model. Individual streamlines construct target features and downstream visualization; they are not selected as top-correlated primary predictors.

## Endpoint

Two endpoints are modeled separately:

```text
Chronic gain:
  Y_AB3m = raw STN+SNr 3-month clinical score
  covariates = Y_STN3m + DeltaSTNScore_3m

Immediate gain:
  Y_ABimmediate = raw STN+SNr immediate clinical score
  covariates = Y_STN3m + DeltaSTNScore_immediate
```

## Inputs

- Public Lead-DBS structural connectomes: dTOR-985 Full, MGH-USC HCP 32, and PPMI 85.
- SNr seed and target masks from `SNr-connected regions`.
- SNr targets from the seed-target atlas registry, including VA/VLA/VLP/VM thalamus, STN, posterior putamen, caudate, PPN, superior colliculus, MD, CM, Pf, sPf, FEF, SMA, preSMA, premotor, M1, and DLPFC.
- SNr-component stimulation maps for each endpoint.
- Raw clinical scores.
- STN-only efficacy maps trained from pre-SNr STN-only data for each scale or symptom domain.
- `DeltaSTNScore` for each endpoint, computed from the corresponding STN efficacy map.

The preferred STN adjustment is:

```text
S_STN(E) =
  sum_{u in Omega_STN} E(u) * M_STN(u)
  / (sum_{u in Omega_STN} E(u) + lambda)

DeltaSTNScore_3m =
  S_STN_domain(E_STN_component,STN+SNr3m)
  - S_STN_domain(E_STN_component,STN-only3m)

DeltaSTNScore_immediate =
  S_STN_motor(E_STN_component,STN+SNrImmediate)
  - S_STN_motor(E_STN_component,STN-only3m)
```

For lower-is-better scales, `M_STN = -theta_STN`; for SE-ADL, `M_STN = theta_STN`. The STN map must be trained only on STN-only outcomes before SNr is added.

## Feature Construction

For patient `i`, side `h`, and target `k`, define same-side normative SNr streamlines:

```text
G_norm_SNr(k,h) = streamlines connecting same-side SNr seed to target P(k,h)
```

Side-specific target connectivity:

```text
C_norm_SNr(i,h,k) =
  sum_j max exposure along streamline j
  / (number of streamlines in G_norm_SNr(k,h) + lambda)
```

Patient-level bilateral feature:

```text
C_norm_SNr_bilat(i,k) =
  (C_norm_SNr(i,L,k) + C_norm_SNr(i,R,k)) / 2
```

Use equal streamline weights within target for the main analysis.

## Statistical Model

For each endpoint and target `k`:

```text
Y_AB_post_i = alpha_k
            + theta_SNr,k * Z(C_norm_SNr_bilat(i,k))
            + beta_k      * Z(Y_STN3m_i)
            + gamma_k     * Z(DeltaSTNScore_i)
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
Y_AB_post_i = alpha
            + delta * SNrTargetScore_norm_i
            + beta  * Y_STN3m_i
            + gamma * DeltaSTNScore_i
            + error_i
```

## Validation

- Run chronic gain and immediate gain separately.
- Use fully nested leave-one-patient-out cross-validation.
- Estimate target weights, select targets, and standardize features inside training folds only.
- For strict out-of-sample prediction, train the STN efficacy map inside each outer fold before computing fold-specific `DeltaSTNScore`.
- Compare against covariate-only prediction: `Y_AB_post ~ Y_STN3m + DeltaSTNScore`.
- Run `DeltaSTNPhys` sensitivity using an outcome-independent STN-change measure such as charge-rate change, raw STN e-field energy change, STN VTA overlap change, or STN field centroid distance.
- Report LOOCV metrics, target selection stability, cross-connectome agreement, and permutation P value.

## Downstream Visualization

Export separately for chronic gain and immediate gain:

```text
target weights and target ranking tables
SNrTargetScore_norm.csv
selected-target fiber subsets
target-weighted streamline density maps
SNr_lh_coverage/sweet/sour/net/stability.nii.gz
SNr_rh_coverage/sweet/sour/net/stability.nii.gz
```

The SNr voxel maps are target-derived seed voxel maps created by back-projecting `w_SNr,k` into SNr using normative streamline density.

## Interpretation Boundary

This model estimates clinical optimization-informed SNr target-gain associations adjusted for STN 3-month baseline and concurrent STN reprogramming. It supports network interpretation but does not prove that any individual streamline or target is causally sufficient. Unless an external STN efficacy map is used, `DeltaSTNScore` is a same-cohort, pre-SNr-derived nuisance adjustment and may be noisy in a small cohort.
