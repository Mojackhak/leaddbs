# STN/SNr Endpoint-Specific Sweet-Spot and Fiber Model Plan

Date: 2026-06-25

## Summary

This document records the planned analysis for symptom-specific STN and SNr sweet-spot and target-level seed-target models in the STN/SNr DBS cohort. The plan combines the endpoint-specific ANCOVA-style model in `/Users/mojackhu/Downloads/STN_SNr_endpoint_specific_sweetspot_pseudocode.md` with the previous decisions for public connectomes, individualized DWI tractography, ROI definition, streamline interpretation, stimulation exposure, and sensitivity analyses.

The primary seed-target connectivity analysis uses target-level predictors. Individual streamlines are used to construct target connectivity features, QC, and visualization, but top correlated fibers are not selected as the primary predictive variables. STN and SNr are not used to crop VTA or truncate streamlines. Instead, prebuilt STN/SNr connected-region atlases define anatomical gating, endpoint grouping, and interpretation for the model outputs.

The implementation-level technical details for normative and individualized DWI target-level connectivity analysis are recorded in:

`/Users/mojackhu/Github/leaddbs/my_helper/stnsnr/normative_connectome_sweet_sour_technical_details.md`

The DWI registration prerequisites are recorded in:

`/Users/mojackhu/Github/leaddbs/my_helper/stnsnr/dwi_registration_technical_details.md`

## Fixed Inputs and Defaults

- Repository root: `/Users/mojackhu/Github/leaddbs`.
- Helper root for implementation: `/Users/mojackhu/Github/leaddbs/my_helper/fiber`.
- Topic-level documentation root: `/Users/mojackhu/Github/leaddbs/my_helper/stnsnr`.
- STN/SNr pipeline scripts remain under `/Users/mojackhu/Github/leaddbs/my_helper/fiber/stnsnr` and should only call reusable core functions.
- Core functions should remain under `/Users/mojackhu/Github/leaddbs/my_helper/fiber/core`.
- Default Conda environment for Lead-DBS tasks: `leaddbs`.
- Random seed for all stochastic analysis steps: `42`.
- Current placeholder stimulation table:
  `/Users/mojackhu/Research/STNSNr/summary/cohort/lead/contact_activation_dataset/random_stimulation_parameters.csv`.
- Active contact table:
  `/Users/mojackhu/Research/STNSNr/summary/cohort/lead/contact_activation_dataset/active_contacts.csv`.
- Primary improvement-rate table for compatibility checks and smoke tests:
  `/Users/mojackhu/Research/STNSNr/summary/cohort/subj/subj_delta_effect.xlsx`.
- Current programming workbook:
  `/Users/mojackhu/Research/STNSNr/summary/cohort/subj/followup_stimulation.xlsx`, sheet `Contact Parameters`.
- Current DWI import log:
  `/Volumes/VAL/STNSNr/derivatives/leaddbs/import_logs/dwi_import_20260701_013240.csv`.
- Current raw clinical score workbook:
  `/Users/mojackhu/Research/STNSNr/summary/cohort/subj/subject_effect_origin.xlsx`.
- Preferred raw score sources for the final ANCOVA endpoint model:
  `/Users/mojackhu/Research/STNSNr/summary/stats/clinic/coords/scale_raw/scale_subject.xlsx` and
  `/Users/mojackhu/Research/STNSNr/summary/stats/clinic/effect/3m/scale_subject.xlsx`.

## Atlases and Connectomes

### Seed-Target Atlas Registry

The authoritative STN/SNr seed-target target-atlas registry is:

`/Users/mojackhu/Github/leaddbs/my_helper/stnsnr/stnsnr_seed_target_atlas_registry.md`

For seed-target fiber tracking, target ROI source, threshold, sensitivity atlas, and interpretation boundaries should follow this registry. The current section records the broader sweet-spot plan, while the registry is the fixed source for pathway-specific target atlas selection.

### Model ROI Priority

For model-level ROI definitions, prefer the prebuilt connected-region atlases:

```text
STN model ROI atlas:
  /Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/atlases/STN-connected regions

SNr model ROI atlas:
  /Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/atlases/SNr-connected regions
```

Each connected-region atlas contains side-specific binary masks and a `roi_manifest.csv` that records the upstream atlas source, threshold, role, and category for each ROI. Use the connected-region atlas ROI files directly for model gating, candidate fiber classification, endpoint grouping, coverage summaries, and visualization overlays.

For STN analyses, use `STN-connected regions` first. Its primary ROIs include `STN`, `SNr`, `M1`, `SMA`, `preSMA`, `premotor`, `GPe`, and `GPi`, with optional or exploratory `DLPFC`, `ACC`, `OFC`, and `vmPFC` masks.

For SNr analyses, use `SNr-connected regions` first. Its primary ROIs include `SNr`, `STN`, `VA_thalamus`, `VLA_thalamus`, `VLP_thalamus`, `VM_thalamus`, `posterior_putamen`, `PPN`, and `superior_colliculus`, with optional or exploratory `caudate`, `MD_thalamus`, `CM_thalamus`, `Pf_thalamus`, `sPf_thalamus`, `FEF`, `SMA`, `preSMA`, `premotor`, `M1`, and `DLPFC` masks.

`Custom_Ewert_Zhang_Middlebrooks0.05` remains the upstream source for the STN and SNr masks inside the connected-region atlases and is retained as a sensitivity or fallback source for standalone STN/SNr masks. Neither connected-region ROIs nor Custom STN/SNr masks should be used to clip stimulation fields.

### Endpoint Parcellation

Use connected-region atlas endpoint masks for primary model endpoint grouping. HCPex remains the underlying cortical label source for many connected-region masks and may be used for additional non-STN/SNr endpoint labeling:

`/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/labeling/HCPex (Huang 2021).nii`

Connected-region STN/SNr labels override any substantia nigra labels from HCPex for STN/SNr-specific reporting.

### Public Structural Connectomes

Run the analysis on all locally available Lead-DBS dMRI structural connectomes:

- `dTOR-985 Full (Elias 2024)`
- `MGH-USC HCP 32 (Horn 2017)`
- `PPMI 85 (Ewert 2017)`

Because dTOR and MGH are large, implementations must use chunked `matfile` access and must not load all fibers into memory.

### Individualized DWI Connectomes

Individualized DWI tractography is incorporated into the same target-level seed-target framework.

Primary DWI source:

```text
/Volumes/VAL/STNSNr/derivatives/leaddbs/import_logs/dwi_import_20260701_013240.csv
```

Programming source for stimulation fields:

```text
/Users/mojackhu/Research/STNSNr/summary/cohort/subj/followup_stimulation.xlsx
sheet: Contact Parameters
```

Technical registration plan:

```text
/Users/mojackhu/Github/leaddbs/my_helper/stnsnr/dwi_registration_technical_details.md
```

Use three coordinated connectivity analyses:

- `Normative-only`: learn and test target-level features from public connectomes only.
- `Normative-guided individualized DWI`: learn target weights and selected targets from normative connectomes, then compute the same target-level score in each patient's individualized DWI tractography.
- `Individualized-DWI-only`: learn target weights directly from individualized DWI features as a sensitivity analysis.

The preferred connectivity model after DWI QC passes is:

```text
normative-guided individualized DWI target-level model
```

This keeps target selection more stable while testing whether the normative target pattern is expressed in each patient's own DWI tractography.

## Stimulation Exposure Models

### Main Exposure Model

Use peak VTA/e-field-like exposure along the full streamline:

```text
X_subject,fiber = max stimulation exposure sampled along the full streamline
```

For the current random stimulation table, use an e-field-like proxy:

- Gaussian contact-centered exposure, weighted by absolute voltage.
- Suggested default sigma: `1.5 mm`.
- Multiple contacts in the same component are combined by voxel-wise maximum.
- `pulse_width_us` and `frequency_Hz` are stored in provenance and may be used in sensitivity analyses, but are not part of the main spatial exposure weight.

When real programming parameters and Lead-DBS stimulation outputs are available, replace the proxy with true e-field maps without changing the downstream modeling interface.

### Interleaving Stimulation Handling

Interleaving stimulation must not be modeled as simultaneous double-cathode stimulation.

For interleaving programs, compute stimulation fields separately for each subprogram or active contact program:

```text
Program A: VTA_A or E_A
Program B: VTA_B or E_B
```

Then represent the overall interleaving exposure with explicit derived maps:

```text
Union exposure:
  VTA_interleaving_union = VTA_A union VTA_B

Overlap exposure:
  VTA_interleaving_overlap = VTA_A intersect VTA_B

Optional weighted exposure:
  E_interleaving_weighted = w_A * E_A + w_B * E_B
```

where `w_A` and `w_B` should be prespecified from pulse counts, frequency, or duty-cycle information when available. If reliable timing information is unavailable, report unweighted union and overlap maps rather than inventing a timing weight.

For target connectivity construction and secondary fiber summaries, compute streamline exposure from each representation:

```text
X_union(i,f)   = max exposure along fiber f in the union map
X_overlap(i,f) = max exposure along fiber f in the overlap map
X_weighted(i,f) = max exposure along fiber f in the weighted exposure map
```

The default interleaving representation for the main VTA-like exposure is:

```text
union map = tissue exposed to at least one subprogram during the interleaving cycle
```

The overlap map should be reported separately because it represents tissue exposed to both pulse trains and may approximate higher pulse density or repeated stimulation exposure.

Do not replace interleaving with:

```text
simultaneous C+ / contact1- contact2-
```

unless the clinical record explicitly indicates simultaneous multi-cathode stimulation. Simultaneous double-cathode stimulation has a different boundary condition:

```text
E_simultaneous(x) = E_1(x) + E_2(x)
```

For simultaneous multi-cathode stimulation, record whether the device/programming mode used independent current control or a single source with impedance-dependent current splitting. These two cases can yield different fields and should not be silently merged:

```text
Independent current control:
  contact1- = specified current
  contact2- = specified current

Single-source coactivation:
  total current is split across cathodes, potentially by impedance
```

Interleaving is time-separated:

```text
E_interleaving(x,t) = E_1(x) at pulse train A
                    = E_2(x) at pulse train B
```

and should therefore be represented by subprogram maps plus union, overlap, and optional timing-weighted summaries.

If OSS-DBS or another pathway activation model supports explicit pulse timing, use the true interleaving pulse sequence for advanced sensitivity analysis. If explicit timing is not supported, compute each subprogram separately and summarize activation with union, overlap, and optional frequency-weighted pathway activation.

### VTA Boundary Rule

Do not crop VTA, e-field, or proxy maps to STN/SNr boundaries. VTA may extend beyond the nucleus edge, and this extension is part of the modeled stimulation effect.

Report target connectivity patterns, secondary sweet-spot maps, and selected-target fiber contribution maps with connected-region STN/SNr outlines overlaid for anatomical interpretation.

### Advanced Sensitivity Model

Use OSS-DBS / pathway activation modeling as an advanced sensitivity analysis. The implementation should reuse Lead-DBS/OSS-DBS outputs when available, especially files matching:

```text
fiberActivation_model-ossdbs_hemi-*.mat
```

For OSS-DBS sensitivity, the streamline activation value is the pathway activation state or activation probability from OSS-DBS/PAM rather than peak e-field magnitude.

## Target-Level Seed-Target Connectivity

### Core Unit

The primary connectivity predictor is the target-level bilateral seed-target feature:

```text
C_bilat(i,k)
```

where `i` is patient and `k` is a predefined target label from the STN/SNr seed-target atlas registry.

The model does not learn a separate weight for left and right homologous targets. For example:

```text
left SMA and right SMA -> target label SMA -> one shared weight w_SMA
```

Left and right sides are still calculated separately before patient-level averaging:

```text
left stimulation  -> left homologous target
right stimulation -> right homologous target
```

No left-right flip is required for the target-level model, because the target label is shared after side-specific same-hemisphere connectivity is computed.

### Side-Specific Connectivity

For patient `i`, side `h` in `{L,R}`, and target `k`, compute:

```text
C(i,h,k)
```

as the stimulation-weighted seed-target connectivity between the stimulated seed side and the same-side target mask.

For a normative connectome:

```text
G_norm(k,h) = streamlines with endpoint in target P(k,h)
A_norm(i,h,j) = max exposure from stimulation E(i,h) along streamline j

C_norm(i,h,k) =
  sum_j A_norm(i,h,j) / (number of streamlines in G_norm(k,h) + lambda)
```

For individualized DWI:

```text
G_ind(i,k,h) = patient i streamlines with endpoint in target P(k,h)
A_ind(i,h,j) = max exposure from stimulation E(i,h) along patient streamline j

C_ind(i,h,k) =
  sum_j A_ind(i,h,j) / (number of streamlines in G_ind(i,k,h) + lambda)
```

The main analysis uses equal streamline weights within each target:

```text
q_j = 1
```

Non-outcome-derived streamline quality weights may be tested later as sensitivity analyses, but they are not part of the main model.

### Patient-Level Bilateral Feature

Before entering any clinical model, the side-specific features are collapsed to one patient-level feature per target:

```text
C_bilat(i,k) = (C(i,L,k) + C(i,R,k)) / 2
```

The primary data table therefore has one row per patient:

```text
n = 16
```

Do not treat left and right hemispheres as 32 independent samples in the primary model. If a side-level sensitivity model is ever used, it must use patient clustering or patient random intercepts, and cross-validation must leave out the whole patient.

If valid left/right symptom severity scores are available, use side-symptom-weighted averaging only as a sensitivity analysis:

```text
C_bilat_weighted(i,k) = rho(i,L) * C(i,L,k) + rho(i,R) * C(i,R,k)
```

The default remains the simple bilateral average.

### Target-Level Predictor Selection

Predictor selection is performed at the target label level, not at the individual fiber level.

For each target `k`, fit a target-wise ANCOVA or rank-based partial model in the training data:

```text
Y_post(i) = alpha_k
          + theta_k * Z(C_bilat(i,k))
          + beta_k  * Z(Y_baseline(i))
          + gamma_k * Z(DeltaSTNScore(i))
          + error(i,k)
```

For STN-only models, `Y_baseline` is `Y_Preop` and `DeltaSTNScore` is omitted unless the model explicitly studies STN reprogramming. For SNr gain models, `Y_baseline` is `Y_STN3m` and `DeltaSTNScore` is retained.

Define the benefit-oriented target weight as:

```text
w_k = -theta_k
```

for lower-is-better scales, and:

```text
w_k = theta_k
```

for SE-ADL. Positive `w_k` always means more connectivity to that target predicts better outcome.

Target quality filtering precedes efficacy ranking. Exclude targets with too few streamlines, near-zero across-patient variance, excessive individualized-DWI reconstruction failure, or high collinearity with baseline or `DeltaSTNScore`.

Default target selection in each training fold:

```text
top 3 sweet targets
top 2 sour targets
maximum selected targets = 5
```

The selected target set forms a patient-level efficacy score:

```text
Score(i) =
  sum_k w_k * Z(C_bilat(i,k)) / sum_k abs(w_k)
```

This score, not a list of top single fibers, is the primary connectivity predictor used for patient-level prediction.

### Nested Validation

All target selection, weight estimation, standardization, and score construction must occur inside the training fold.

For leave-one-patient-out validation:

1. Hold out one patient, including both hemispheres.
2. Estimate target weights and select targets using only the remaining patients.
3. Compute the held-out patient's target score with the training-fold targets, weights, and standardization parameters.
4. Fit the final training-fold ANCOVA model.
5. Predict the held-out patient's outcome.

Compare the full model against a covariate-only model:

```text
Y_post ~ Y_baseline + DeltaSTNScore
```

The target-level score must provide predictive information beyond these covariates to support a connectivity claim.

## Clinical Endpoints

### Scale-Specific Primary Modeling Policy

Use scale-specific models under one shared modeling framework. Do not pool UPDRS-III, axial UPDRS-III, FOG-Q, KPPS, PDQ-39, MADRS, ADL, SE-ADL, or any later-added clinical scales into one primary patient-level regression model.

The primary modeling unit is:

```text
one scale -> one endpoint selection -> one STN or SNr sweet-spot model
```

Rationale:

- different scales measure different clinical constructs;
- acute and chronic endpoints estimate different effects;
- stacking scales does not create additional independent patients;
- a pooled model may obscure symptom-specific SNr networks.

The implementation should therefore provide a common function, not a common primary regression:

```text
for each scale:
  select endpoint
  fit the scale-specific model
  save the scale-specific map
```

### Clinical Score Direction

Use one prespecified direction rule per clinical scale before computing improvement rates, model targets, or benefit-oriented residuals.

Current target scales where lower scores indicate better clinical status:

```text
UPDRS-III
UPDRS-III axial
FOG-Q
PDQ-39
KPPS
MADRS
ADL
```

For these scales:

```text
STN improvement percent = (Pre-op - STN score) / Pre-op * 100
SNr add-on improvement percent = (STN score - STN+SNr score) / Pre-op * 100
```

SE-ADL is the exception in the current target table: higher scores indicate better clinical status.

For SE-ADL:

```text
STN improvement percent = (STN score - Pre-op) / Pre-op * 100
SNr add-on improvement percent = (STN+SNr score - STN score) / Pre-op * 100
```

In all models, orient coefficients and residual scores so that positive benefit scores mean better predicted clinical outcome.

### STN-Alone Efficacy Model

Use two STN-only model layers.

Primary STN model:

```text
chronic STN-only efficacy model
```

This model answers:

```text
Which target-level STN seed-target connectivity features are associated with stable STN-only benefit at 3 months?
```

Secondary STN model:

```text
early / acute STN-only response model
```

This model answers:

```text
Which target-level STN seed-target connectivity features are associated with the early response after STN activation?
```

The chronic STN-only model is the primary STN model because it localizes stable STN DBS benefit and uses the same STN-3m clinical state that serves as the baseline for SNr-addition models.

#### Primary Chronic STN-Only Model

For each scale and target `k`:

```text
Y_STN3m_i = alpha_0
          + alpha_STN,k * C_STN3m_bilat(i,k)
          + alpha_B     * Y_Preop_i
          + error_i
```

Definitions:

- `Y_STN3m_i`: raw STN-only 3-month clinical score for patient `i`.
- `Y_Preop_i`: raw preoperative score for patient `i`.
- `C_STN3m_bilat(i,k)`: bilateral target-level STN seed-target connectivity for target `k` under STN-only 3-month programming.
- `alpha_STN,k`: target-specific STN efficacy coefficient.

Use a baseline-adjusted rank-based partial Spearman estimator for the main implementation:

```text
STNBenefitScore_k =
  corr_spearman(
    residual(rank(C_STN3m_bilat(k)) ~ rank(Y_Preop)),
    benefit_oriented_residual(rank(Y_STN3m) ~ rank(Y_Preop))
  )
```

For scales where lower scores are better, multiply the outcome residual by `-1` before the final correlation. For SE-ADL, keep the residual direction because higher scores are better.

```text
STNBenefitScore_k > 0 means stronger target-level STN connectivity predicts better baseline-adjusted STN-3m outcome.
```

Do not use change score or percent improvement as the primary STN sweet-spot outcome. The existing improvement-rate table can be used for compatibility checks, smoke tests, descriptive reporting, and sensitivity analyses.

Voxel- and fiber-level STN maps are secondary localization and visualization outputs. They must not replace target-level predictor selection in the primary connectivity model.

#### Secondary Early / Acute STN-Only Model

For scales with valid immediate STN assessment, fit an early STN-only model.

If only preoperative baseline is available:

```text
Y_STNImmediate_i = alpha_0
                 + alpha_STN,k_early * C_STNImmediate_bilat(i,k)
                 + alpha_B           * Y_Preop_i
                 + error_i
```

Name this model:

```text
early STN-only response model
```

Do not call it a pure acute STN effect, because the preoperative-to-immediate interval may include perioperative recovery, microlesion effects, medication changes, and timing differences.

If a same-day STN-OFF baseline exists at the first programming visit, use it instead of preoperative baseline:

```text
Y_STNImmediate_i = alpha_0
                 + alpha_STN,k_acute * C_STNImmediate_bilat(i,k)
                 + alpha_B           * Y_STNOffSameDay_i
                 + error_i
```

Name this cleaner version:

```text
acute STN stimulation response model
```

With the currently inspected score tables, immediate STN and STN+SNr assessments are available for `UPDRS-III` and `UPDRS-III axial`. Pain, quality-of-life, and most non-motor scales should not be forced into immediate STN models unless valid immediate assessments exist.

#### Optional STN Chronic Adaptation Model

Use this only as a secondary mechanism model when STN-immediate and STN-3m programming differ enough to justify studying chronic adaptation or programming optimization:

```text
Y_STN3m_i = alpha_0
          + alpha_STN,k_adapt * C_STN3m_bilat(i,k)
          + alpha_B           * Y_STNImmediate_i
          + alpha_D           * DeltaSTNScore_ImmTo3m_i
          + error_i
```

where:

```text
DeltaSTNScore_ImmTo3m = STNScore_STN3m - STNScore_STNImmediate
```

This optional model should not replace the primary chronic STN-only model.

The chronic STN model also supports an optional residualized SNr model by predicting the STN contribution under the STN component of combined stimulation.

### SNr Gain Endpoint Selection

The SNr model should use raw post-combination scores when available, following an ANCOVA-style endpoint-specific design. The SNr model family has one primary estimand:

```text
clinical optimization-informed SNr-target gain model
```

This model asks whether the final clinician-optimized SNr component exposure predicts better STN+SNr outcome after controlling the pre-SNr STN 3-month clinical state and the concurrent STN component exposure change.

The model has two endpoints:

```text
chronic SNr gain endpoint:
  baseline phase = STN-3m
  post phase     = STN+SNr-3m
  model class    = chronic

immediate SNr gain endpoint:
  baseline phase = STN-3m
  post phase     = STN+SNr-immediate
  model class    = immediate
```

Use `MIN_N_FOR_MODEL = 12`. Do not hard-code scale names into endpoint selection. Choose each endpoint per scale based on complete paired score and exposure availability.

### Primary SNr Gain Model

For each scale and target `k`, fit the clinical optimization-informed SNr-target gain model:

```text
Y_AB_post_i = alpha_0
            + theta_SNr,k * C_SNr_bilat(i,k)
            + beta         * Y_STN3m_i
            + gamma        * DeltaSTNScore_i
            + error_i
```

Definitions:

- `Y_AB_post_i`: selected post-combination raw clinical score for patient `i`.
- `Y_STN3m_i`: STN-only 3-month raw clinical score for patient `i`.
- `C_SNr_bilat(i,k)`: final SNr-component target-level bilateral seed-target connectivity for target `k`.
- `DeltaSTNScore_i`: scalar summary of STN component exposure change between STN-only and combined programming.
- `theta_SNr,k`: SNr gain target coefficient of interest.

Question:

```text
Among patients with comparable STN-only 3-month clinical state and comparable STN-component changes,
does final SNr seed-target connectivity to target k predict better STN+SNr outcome?
```

Interpretation:

`theta_SNr,k` is the adjusted target-level association between clinician-optimized final SNr-component connectivity and the STN+SNr outcome, conditional on pre-SNr clinical state and concurrent STN reprogramming.

For scales where lower scores are better:

```text
H_SNr,k = -theta_SNr,k
```

For SE-ADL, where higher scores are better:

```text
H_SNr,k = theta_SNr,k
```

Positive heatmap values always indicate better predicted clinical outcome.

#### Chronic SNr Gain Model

Use this model to estimate the long-term target-level distribution of SNr-associated gain after adding SNr to STN stimulation:

```text
Y_AB3m_i = alpha_0
         + theta_SNr_chronic,k * C_SNr3m_bilat(i,k)
         + beta                 * Y_STN3m_i
         + gamma                * DeltaSTNScore_3m_i
         + error_i
```

Definitions:

- `Y_AB3m_i`: raw STN+SNr 3-month clinical score for patient `i`.
- `C_SNr3m_bilat(i,k)`: STN+SNr 3-month SNr-component bilateral connectivity to target `k`.
- `DeltaSTNScore_3m_i`: STN component exposure change from STN-only 3 months to STN+SNr 3 months.
- `theta_SNr_chronic,k`: chronic SNr gain target coefficient.

Question:

```text
In patients with the same STN-only 3-month clinical state and the same STN component change,
does final SNr 3-month connectivity to target k predict better STN+SNr 3-month outcome?
```

#### Immediate SNr Gain Model

Use this model to estimate the immediate target-level distribution of SNr-associated gain after adding SNr to STN stimulation:

```text
Y_ABimmediate_i = alpha_0
                + theta_SNr_immediate,k * C_SNrImmediate_bilat(i,k)
                + beta                   * Y_STN3m_i
                + gamma                  * DeltaSTNScore_immediate_i
                + error_i
```

Definitions:

- `Y_ABimmediate_i`: raw STN+SNr immediate clinical score for patient `i`.
- `C_SNrImmediate_bilat(i,k)`: STN+SNr immediate SNr-component bilateral connectivity to target `k`.
- `DeltaSTNScore_immediate_i`: STN component exposure change from STN-only 3 months to STN+SNr immediate programming.
- `theta_SNr_immediate,k`: immediate SNr gain target coefficient.

Question:

```text
In patients with the same STN-only 3-month clinical state and the same immediate-phase STN component change,
does final SNr immediate connectivity to target k predict better STN+SNr immediate outcome?
```

The `Y_STN3m` covariate controls the pre-SNr disease state. `DeltaSTNScore_immediate` controls concurrent STN component reprogramming in the immediate STN+SNr setting. If a same-day pre-SNr STN-only score becomes available, add a sensitivity model using that same-day baseline to control short-term disease fluctuation more directly.

#### Rank-Based SNr Implementation

Use a rank-based partial Spearman estimator as the main implementation for `n = 16`:

1. Rank-transform `Y_AB_post`, `C_SNr_bilat(k)`, `Y_STN3m`, and `DeltaSTNScore`.
2. Regress ranked `Y_AB_post` on ranked `Y_STN3m` and ranked `DeltaSTNScore`; keep residuals.
3. Regress ranked `C_SNr_bilat(k)` on ranked `Y_STN3m` and ranked `DeltaSTNScore`; keep residuals.
4. Correlate the two residual vectors.
5. Flip sign when higher clinical score means worse outcome, so positive scores always indicate benefit.

```text
SNrChronicGainScore_k > 0 means stronger target-level SNr connectivity predicts better chronic STN+SNr outcome.
SNrImmediateGainScore_k > 0 means stronger target-level SNr connectivity predicts better immediate STN+SNr outcome.
```

### SNr Gain Estimand Boundaries

The time zero for SNr-addition models is:

```text
STN-only 3-month assessment, immediately before adding or optimizing SNr stimulation
```

The SNr models do not estimate:

```text
total STN+SNr improvement from preoperative baseline
percent improvement difference between STN+SNr and STN-only
the outcome each patient would have had at every untested SNr location
```

They estimate target-level spatial associations between final SNr seed-target connectivity and post-combination outcome after conditioning on the selected baseline state.

The observed final SNr location is clinician-selected:

```text
C_i* = final SNr setting selected for patient i after clinical programming
```

Thus the observed outcome is:

```text
Y_i(C_i*)
```

not the full set of counterfactual outcomes:

```text
Y_i(s) for every possible SNr location s
```

Therefore, the SNr target maps and target scores are patient-level between-subject spatial association models. They are not within-patient randomized location-response maps.

### Scientific Preconditions for SNr Gain Inference

The SNr gain analyses are scientifically meaningful under these conditions:

- `Y_STN3m` adequately represents the clinical state before SNr addition.
- `DeltaSTNScore` adequately summarizes STN-component changes for the SNr gain model.
- The final SNr setting is a clinically optimized setting, not an arbitrary or poorly explored setting.
- Acute programming response and side-effect thresholds used to choose the final SNr setting have reasonable relevance to the 3-month outcome.
- SNr target-level connectivity has enough across-patient variability to estimate target weights.
- Within comparable ranges of `Y_STN3m` and `DeltaSTNScore`, there is sufficient overlap in SNr target connectivity to avoid relying mainly on extrapolation.
- Unmeasured prognosis factors, symptom subtypes, medication changes, rehabilitation intensity, anatomy, and programming style do not strongly determine both the final SNr location and the later STN+SNr outcome.
- STN and SNr effects are sufficiently separable for an additive model to remain interpretable.

Coverage must be reported for every target-level model and every secondary voxel or fiber output:

```text
Coverage(k) = number of patients with usable bilateral connectivity for target k
ExposureCoverage(k) = sum_i C_SNr_bilat(i,k)
```

Only targets, regions, or streamlines with adequate coverage should receive strong anatomical interpretation.

### Potential Problems with the SNr Gain Definition

Main limitations:

- The maps are not pure causal maps of SNr spatial efficacy.
- Clinician selection can induce indication bias because different SNr regions may be selected for different patient subtypes.
- `Y_STN3m` controls total pre-SNr severity, but may not fully control symptom composition, DBS responsiveness, future prognosis, or side-effect limitations.
- `DeltaSTNScore` may be an incomplete summary of STN reprogramming because STN changes can involve contact, amplitude, pulse width, frequency, e-field shape, and fiber recruitment.
- `C_SNr_bilat(i,k)` and `DeltaSTNScore` may be collinear if certain SNr target connectivity profiles are systematically paired with certain STN programming changes.
- Low-coverage targets, locations, or streamlines can generate unstable coefficients.
- With `n = 16`, interaction models such as `C_SNr_bilat(k) * subtype` or `C_SNr_bilat(k) * DeltaSTNScore` are usually too unstable for primary inference.
- Normative connectomes support group-level structural interpretation; individualized DWI analyses are needed for subject-specific anatomy but remain limited by reconstruction quality.
- Random or Gaussian proxy stimulation results validate the pipeline only and should not be biologically interpreted.

The most defensible wording is:

```text
adjusted relative SNr-target gain map
clinical optimization-informed SNr-target gain map
```

Avoid:

```text
absolute causal map of SNr efficacy
evidence that every patient should be stimulated at this location
```

### STN Reprogramming Confound

Do not interpret `STN+SNr - STN-alone` as pure SNr benefit if STN parameters changed between phases.

The primary SNr gain model controls this by including:

```text
DeltaSTNScore = STN exposure scalar in combined setting - STN exposure scalar in STN-alone setting
```

Recommended main scalar:

```text
STNScore_i = sum of STN-component exposure in a prespecified STN motor ROI
```

or, once an STN model is available:

```text
STNScore_i = weighted overlap with the learned STN target-level or sweet-spot model
```

### Residualized SNr Sensitivity Model

As a complementary sensitivity analysis:

1. Train an STN response model on STN-alone data.
2. Predict the expected STN contribution in the combined phase using the combined-phase STN component.
3. Compute:

```text
Y_SNr_residual = observed STN+SNr outcome - predicted STN contribution
```

4. Model `Y_SNr_residual` against SNr-component target-level connectivity.

Use leave-one-patient-out predictions for any residualized model to avoid optimistic reuse of the same patient in both training and prediction.

## Target, Fiber, and Sweet-Spot Definitions

### Voxel Sweet Spot

Voxel sweet spots are secondary localization outputs. For each voxel and outcome, model the relation between subject-level stimulation exposure at that voxel and clinical response after the target-level model has been specified.

For the STN model, use STN-alone exposure and STN response. For the SNr gain model, use SNr-component exposure and endpoint-specific post-score models adjusted for STN-3m baseline and STN exposure change. Run the chronic gain endpoint for `STN+SNr 3m` and the immediate gain endpoint for `STN+SNr immediate`.

Voxel maps should not drive primary predictor selection.

### Whole-Streamline Fiber Filtering

Use whole streamlines from the public connectome or individualized DWI tractography to construct target-level connectivity features. Do not crop streamlines to STN/SNr internal segments.

Main candidate fiber definitions:

```text
STN-associated candidate fiber:
  whole streamline intersects the `STN-connected regions` STN ROI

SNr-associated candidate fiber:
  whole streamline intersects the `SNr-connected regions` SNr ROI

STN+SNr-associated candidate fiber:
  whole streamline intersects both connected-region STN and SNr ROIs
```

The streamline exposure value is still sampled from the full stimulation map along the whole streamline:

```text
X_subject,fiber = max exposure along the full streamline
```

The peak may occur near the nucleus edge or outside the strict ROI boundary.

Individual fibers are not selected as primary predictors by top correlation. Fiber subsets are exported only for target-level contribution decomposition, QC, visualization, and anatomical explanation of selected targets.

### Endpoint-Specific Reporting

For each selected or high-ranked target:

- report target label;
- report target atlas source;
- report model class: `early`, `chronic`, `chronic_gain`, or `immediate_gain`;
- report scale;
- report target weight `w_k`;
- report `STNBenefitScore_k`, `SNrChronicGainScore_k`, or `SNrImmediateGainScore_k`;
- report left, right, and bilateral connectivity summaries;
- report normative-only, individualized-DWI, or normative-guided-DWI source;
- report whether the effect is sweet or sour.

For fiber contribution outputs within selected targets:

- report connectome name;
- report streamline ID;
- report model class: `acute` or `chronic`;
- report scale;
- report parent target label and target weight;
- report whether it intersects the connected-region STN ROI, SNr ROI, or both;
- report HCPex endpoint labels;
- report whether it supports a sweet or sour target.

## Statistical Plan

### Main Tests

- STN primary model: baseline-adjusted partial Spearman or ANCOVA between target-level STN-only 3-month bilateral connectivity and STN-only 3-month raw score, adjusting for preoperative raw score.
- STN secondary early model: baseline-adjusted partial Spearman or ANCOVA between target-level STN-immediate bilateral connectivity and STN-immediate raw score, adjusting for preoperative score or same-day STN-OFF score when available.
- SNr chronic gain model: endpoint-specific target-level partial Spearman or ANCOVA with `Y_STN3m` and `DeltaSTNScore_3m` as covariates, estimating adjusted chronic SNr target weights.
- SNr immediate gain model: endpoint-specific target-level partial Spearman or ANCOVA with `Y_STN3m` and `DeltaSTNScore_immediate` as covariates, estimating adjusted immediate SNr target weights.
- Primary inference is scale-specific; do not combine heterogeneous scales into one primary model.
- Correct multiple comparisons across tested targets within each scale, connectome or DWI source, and model class using FDR.
- Use patient-level permutation tests with seed `42` for empirical significance.

### Endpoint Hierarchy

Recommended reporting hierarchy:

- primary STN endpoint: chronic STN-only efficacy model using `Preop -> STN-3m`;
- secondary STN endpoint: early / acute STN-only response model using `Preop -> STN-immediate`, or `STN-OFF same-day -> STN-immediate` when same-day baseline exists;
- optional STN endpoint: chronic adaptation model using `STN-immediate -> STN-3m`;
- primary SNr chronic gain endpoint: adjusted `STN+SNr 3m` outcome model using `Y_STN3m` and `DeltaSTNScore_3m`;
- primary SNr immediate gain endpoint: adjusted `STN+SNr immediate` outcome model using `Y_STN3m` and `DeltaSTNScore_immediate`;
- primary SNr mechanistic endpoint: UPDRS-III immediate SNr-addition model when valid immediate data are available;
- key secondary SNr endpoint: UPDRS-III chronic SNr-addition model to evaluate longer-term motor relevance;
- symptom-specific secondary SNr endpoints: axial UPDRS-III, FOG-Q, KPPS, PDQ-39, MADRS, ADL, SE-ADL, and other available scales using their selected endpoints;
- exploratory cross-scale summaries: map overlap, meta-map, or pooled/global model.

### Cross-Validation

Use leave-one-patient-out cross-validation for `n = 16`.

For each held-out subject:

1. Train target weights and select targets on the remaining subjects.
2. Build the held-out subject's bilateral target-level efficacy score using training-fold parameters only.
3. Fit the final training-fold model and predict the held-out subject's outcome.
4. Compare the full target-score model with a covariate-only model.

Report:

- cross-validated Spearman rho;
- permutation P value;
- number of complete subjects;
- endpoint class;
- sensitivity-model agreement;
- covariate-only baseline performance.

### Cross-Scale Map-Level Summary

After fitting scale-specific models, evaluate convergence at the map level rather than by pooling clinical outcomes into one primary regression.

Recommended map-level metrics:

```text
correlation between scale-specific target-weight vectors
overlap of selected sweet targets
overlap of selected sour targets
optional spatial correlation between secondary voxel/fiber density maps
```

A secondary global SNr benefit map may be generated only after scale-specific fitting:

```text
GlobalSNrTargetWeight_k = mean_scale z(SNrBenefitScore_scale,k)
```

Use equal weights by default. If non-equal weights are used, define them before looking at results and record them in provenance.

### Exploratory Pooled Model

A pooled cross-scale model is allowed only as exploratory support for a global SNr benefit network. It is not the primary localization model.

If implemented, it must:

- orient all clinical scores so higher values consistently mean greater benefit or worse status before modeling;
- z-score outcomes within scale;
- include scale fixed effects;
- include endpoint-class fixed effects when acute and chronic endpoints are mixed;
- account for repeated outcomes within patients, preferably with a patient random intercept;
- report that the resulting map estimates an average cross-scale effect, not symptom-specific networks.

### Sensitivity Analyses

Run the following sensitivity analyses:

- change-score model without baseline as a covariate;
- STN percent-improvement model for comparability with older STN DBS sweet-spot studies;
- one-at-a-time STN covariate sensitivity with medication or LEDD change when medication state differs;
- patient-level overlap with a published STN sweet spot as an external plausibility check;
- STN-only negative-control model using SNr exposure to test whether SNr-addition maps reflect general electrode placement quality;
- target-specific STN exposure change instead of scalar `DeltaSTNScore`;
- minimal-STN-change subgroup after excluding subjects with the largest absolute STN exposure change;
- binary VTA intersection instead of continuous peak exposure;
- interleaving-specific union, overlap, and frequency-weighted exposure summaries;
- local ROI-expanded peak exposure using connected-region STN/SNr primary masks dilated by `2-3 mm`;
- charge-rate proxy using `abs(voltage_V) * pulse_width_us * frequency_Hz`;
- OSS-DBS/PAM pathway activation model when valid outputs exist;
- repeated analyses across dTOR-985, MGH-USC HCP 32, and PPMI 85 connectomes;
- normative-only, normative-guided individualized DWI, and individualized-DWI-only target-level model comparison.

## Implementation Outline

### Documentation First

Before code changes, update the relevant documentation under `/Users/mojackhu/Github/leaddbs/my_helper/stnsnr` or `/Users/mojackhu/Github/leaddbs/my_helper/fiber/README.md`.

### Core Function Placement

Reusable functions should be grouped by responsibility:

- connectome enumeration, metadata, and chunked readers: `my_helper/fiber/core/connectomes`;
- ROI loading, voxelization, dilation, and HCPex endpoint labeling: `my_helper/fiber/core/roi`;
- stimulation proxy and future e-field/OSS-DBS adapters: `my_helper/fiber/core/stimulation`;
- streamline exposure extraction and statistics: `my_helper/fiber/core/tracking`;
- result tables and provenance writers: `my_helper/fiber/core/io`;
- figures and scene generation: `my_helper/fiber/core/visualization`.

`my_helper/fiber/stnsnr` should contain only pipeline scripts that call these core functions.

### Pipeline Stages

1. Validate inputs and write provenance.
2. Load active contact and stimulation parameter tables.
3. Detect interleaving programs and split them into explicit subprogram definitions.
4. Build STN-alone, combined-STN-component, and combined-SNr-component exposure maps, including interleaving union and overlap maps where needed.
5. Load raw clinical scores and improvement-rate tables.
6. Select endpoint per scale.
7. Build side-specific and bilateral target-level connectivity matrices for normative and individualized DWI sources.
8. Extract secondary voxel and streamline exposure matrices for localization, QC, and visualization.
9. Fit the primary chronic STN-only target model.
10. Fit secondary STN-only early / acute target models where valid immediate data exist.
11. Fit optional STN chronic adaptation target models when justified by programming changes.
12. Fit endpoint-specific SNr chronic gain target models with `Y_STN3m` and `DeltaSTNScore_3m`.
13. Fit endpoint-specific SNr immediate gain target models with `Y_STN3m` and `DeltaSTNScore_immediate`.
14. Fit sensitivity models, including normative-only and DWI-only variants.
15. Label fibers within selected targets by connected-region STN/SNr and endpoint masks, with HCPex labels as supplemental endpoint labels.
16. Export CSV/Mat/JSON provenance, target weights, target scores, and visualization-ready fiber subsets.

## Expected Outputs

Use an output root outside tracked code, for example:

```text
/Users/mojackhu/Github/leaddbs/connectomes/dMRI/public_tracking/STN_SNr/endpoint_specific_sweetspot/
```

Expected output groups:

- `provenance/`: input paths, software versions, random seed, model settings.
- `qc/`: subject inclusion, endpoint selection, missingness, ROI volumes, connectome availability, DWI coverage.
- `target_connectivity/`: left, right, and bilateral target-level connectivity matrices.
- `exposure/`: subject-level exposure summaries and secondary streamline exposure matrices.
- `exposure/interleaving/`: subprogram exposure maps, union maps, overlap maps, and optional timing-weighted maps.
- `models/stn/chronic/`: primary chronic STN-only target weights, target scores, and secondary maps.
- `models/stn/early/`: secondary early / acute STN-only target results.
- `models/stn/adaptation/`: optional STN chronic adaptation target results.
- `models/snr/chronic_gain/`: endpoint-specific chronic SNr target-gain model results.
- `models/snr/immediate_gain/`: endpoint-specific immediate SNr target-gain model results.
- `models/cross_scale/`: map-level similarity metrics and secondary global maps.
- `sensitivity/`: all sensitivity model outputs.
- `visualization/`: selected-target fiber subsets, sweet/sour target summaries, secondary maps, HCPex endpoint summaries.

## Acceptance Checks

- `random_seed` is `42` in all stochastic steps.
- The analysis does not crop VTA/e-field/proxy maps to STN/SNr masks.
- Interleaving stimulation is split into subprograms and is not treated as simultaneous double-cathode stimulation.
- Interleaving outputs include union exposure and overlap exposure when interleaving programs exist.
- Streamlines are whole connectome streamlines, not STN/SNr internal fragments.
- STN/SNr model labels come from `STN-connected regions` and `SNr-connected regions`.
- Non-STN/SNr endpoint labels come from HCPex.
- Primary predictor selection is target-level, not top correlated individual fibers.
- Left and right side connectivity are computed separately and averaged into one patient-level bilateral feature before modeling.
- The primary model has one row per patient; left and right hemispheres are not treated as independent samples.
- Target-level DWI coverage is checked before individualized-DWI or normative-guided-DWI models are interpreted.
- The primary STN model uses raw STN-3m score adjusted for raw preoperative score, not percent improvement as the main outcome.
- STN-immediate models are marked secondary and use same-day STN-OFF baseline when available.
- SNr chronic gain models include both `Y_STN3m` and `DeltaSTNScore_3m`.
- SNr immediate gain models include both `Y_STN3m` and `DeltaSTNScore_immediate`.
- SNr results include target coverage summaries and secondary coverage maps; low-coverage targets, regions, or streamlines are not strongly interpreted.
- The implementation can run a PPMI smoke test before dTOR full-scale analysis.
- dTOR and MGH access is chunked and memory-safe.
- `my_helper/fiber/stnsnr` contains only pipeline scripts, not core helper functions.
- scale-specific maps are generated before any cross-scale summary map.
- any pooled cross-scale model is marked exploratory.

## Interpretation Rules

- Primary STN results should be described as chronic STN-only therapeutic target connectivity patterns and, secondarily, sweet spots or fiber contribution maps.
- STN-immediate results should be described as early STN-only target connectivity response models, or acute STN stimulation response models only when same-day STN-OFF baseline is used.
- STN adaptation results should be described as secondary programming/adaptation analyses, not as the main STN efficacy model.
- SNr gain results should be described as clinical optimization-informed SNr target-level gain models adjusted for STN-3m baseline and concurrent STN exposure change.
- SNr chronic gain results should be described as adjusted target-level associations with `STN+SNr 3m` outcome.
- SNr immediate gain results should be described as adjusted target-level associations with `STN+SNr immediate` outcome.
- Residualized SNr results should be described as STN-model-adjusted SNr-associated residual benefit, not as definitive pure SNr causal effect.
- SNr target maps should not be described as pure causal maps showing that every patient should be stimulated at a given SNr location.
- Interleaving union maps should be described as exposure across an interleaving cycle, not as one simultaneous continuous electric field.
- Interleaving overlap maps should be described as tissue or fibers exposed to both pulse trains.
- Scale-specific target-level models are the primary results for symptom-specific inference.
- Global or pooled target maps are secondary/exploratory summaries of cross-scale convergence.
- Fiber subsets are explanatory outputs within selected targets, not the primary predictor selection mechanism.
- Random stimulation table results are pipeline validation only and should not be interpreted biologically.

## References

- Hollunder B. et al. Network-based sweet spots of deep brain stimulation. Nature Neuroscience, 2024. https://www.nature.com/articles/s41593-024-01570-1
- Rajamani N. et al. Symptom-specific therapeutic pathways for deep brain stimulation. Nature Communications, 2024. https://www.nature.com/articles/s41467-024-48731-1
- Juarez-Paz R. et al. In silico accuracy and energy efficiency of two steering paradigms in directional deep brain stimulation. Frontiers in Neurology, 2020. https://www.frontiersin.org/journals/neurology/articles/10.3389/fneur.2020.593798/full
- Modeling the volume of tissue activated in deep brain stimulation and its clinical influence: a review. Frontiers in Human Neuroscience, 2024. https://www.frontiersin.org/journals/human-neuroscience/articles/10.3389/fnhum.2024.1333183/full
- Butenko K. et al. OSS-DBS: Open-source simulation platform for deep brain stimulation with a comprehensive automated modeling. PLOS Computational Biology, 2020. https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1008023
- Vickers A.J. and Altman D.G. Analysing controlled trials with baseline and follow up measurements. BMJ, 2001.
- Clifton L. and Clifton D.A. The correlation between baseline score and post-intervention score, and its implications for statistical analysis. Trials, 2019.
- U.S. Food and Drug Administration. Multiple Endpoints in Clinical Trials: Guidance for Industry. https://www.fda.gov/regulatory-information/search-fda-guidance-documents/multiple-endpoints-clinical-trials
