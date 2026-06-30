# STN/SNr Endpoint-Specific Sweet-Spot and Fiber Model Plan

Date: 2026-06-25

## Summary

This document records the planned analysis for symptom-specific STN and SNr sweet-spot and fiber models in the STN/SNr DBS cohort. The plan combines the endpoint-specific ANCOVA-style model in `/Users/mojackhu/Downloads/STN_SNr_endpoint_specific_sweetspot_pseudocode.md` with the previous decisions for public connectomes, ROI definition, streamline interpretation, stimulation exposure, and sensitivity analyses.

The primary analysis uses full-field VTA/e-field-like exposure and whole-streamline fiber filtering. STN and SNr are not used to crop VTA or truncate streamlines. Instead, Custom STN/SNr ROIs define anatomical gating and interpretation, while HCPex labels non-STN/SNr endpoint regions.

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
- Preferred raw score sources for the final ANCOVA endpoint model:
  `/Users/mojackhu/Research/STNSNr/summary/stats/clinic/coords/scale_raw/scale_subject.xlsx` and
  `/Users/mojackhu/Research/STNSNr/summary/stats/clinic/effect/3m/scale_subject.xlsx`.

## Atlases and Connectomes

### Seed-Target Atlas Registry

The authoritative STN/SNr seed-target target-atlas registry is:

`/Users/mojackhu/Github/leaddbs/my_helper/stnsnr/stnsnr_seed_target_atlas_registry.md`

For seed-target fiber tracking, target ROI source, threshold, sensitivity atlas, and interpretation boundaries should follow this registry. The current section records the broader sweet-spot plan, while the registry is the fixed source for pathway-specific target atlas selection.

### STN/SNr ROI

Use `Custom_Ewert_Zhang_Middlebrooks0.05` as the primary STN/SNr ROI source:

`/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/atlases/Custom_Ewert_Zhang_Middlebrooks0.05`

The Custom STN/SNr masks are used to classify fibers as STN-passing, SNr-passing, STN+SNr-passing, or non-passing. They should not be used to clip stimulation fields.

### Endpoint Parcellation

Use HCPex for non-STN/SNr endpoint labeling:

`/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/labeling/HCPex (Huang 2021).nii`

Custom STN/SNr labels override any substantia nigra labels from HCPex for STN/SNr-specific reporting.

### Public Structural Connectomes

Run the analysis on all locally available Lead-DBS dMRI structural connectomes:

- `dTOR-985 Full (Elias 2024)`
- `MGH-USC HCP 32 (Horn 2017)`
- `PPMI 85 (Ewert 2017)`

Because dTOR and MGH are large, implementations must use chunked `matfile` access and must not load all fibers into memory.

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

For fiber models, compute streamline exposure from each representation:

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

Report sweet spots and sweet fibers with Custom STN/SNr outlines overlaid for anatomical interpretation.

### Advanced Sensitivity Model

Use OSS-DBS / pathway activation modeling as an advanced sensitivity analysis. The implementation should reuse Lead-DBS/OSS-DBS outputs when available, especially files matching:

```text
fiberActivation_model-ossdbs_hemi-*.mat
```

For OSS-DBS sensitivity, the streamline activation value is the pathway activation state or activation probability from OSS-DBS/PAM rather than peak e-field magnitude.

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
Which voxels or streamlines are associated with stable STN-only benefit at 3 months?
```

Secondary STN model:

```text
early / acute STN-only response model
```

This model answers:

```text
Which voxels or streamlines are associated with the early response after STN activation?
```

The chronic STN-only model is the primary STN model because it localizes stable STN DBS benefit and uses the same STN-3m clinical state that serves as the baseline for SNr-addition models.

#### Primary Chronic STN-Only Model

For each scale and streamline:

```text
Y_STN3m_i = alpha_0
          + alpha_STN,f * X_STN3m,i,f
          + alpha_B     * Y_Preop_i
          + error_i
```

Definitions:

- `Y_STN3m_i`: raw STN-only 3-month clinical score for patient `i`.
- `Y_Preop_i`: raw preoperative score for patient `i`.
- `X_STN3m,i,f`: STN-component exposure along streamline `f` under STN-only 3-month programming.
- `alpha_STN,f`: streamline-specific STN efficacy coefficient.

Use a baseline-adjusted rank-based partial Spearman estimator for the main implementation:

```text
STNBenefitScore_f =
  corr_spearman(
    residual(rank(X_STN3m,f) ~ rank(Y_Preop)),
    benefit_oriented_residual(rank(Y_STN3m) ~ rank(Y_Preop))
  )
```

For scales where lower scores are better, multiply the outcome residual by `-1` before the final correlation. For SE-ADL, keep the residual direction because higher scores are better.

```text
STNBenefitScore_f > 0 means stronger STN exposure predicts better baseline-adjusted STN-3m outcome.
```

Do not use change score or percent improvement as the primary STN sweet-spot outcome. The existing improvement-rate table can be used for compatibility checks, smoke tests, descriptive reporting, and sensitivity analyses.

#### Secondary Early / Acute STN-Only Model

For scales with valid immediate STN assessment, fit an early STN-only model.

If only preoperative baseline is available:

```text
Y_STNImmediate_i = alpha_0
                 + alpha_STN,f_early * X_STNImmediate,i,f
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
                 + alpha_STN,f_acute * X_STNImmediate,i,f
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
          + alpha_STN,f_adapt * X_STN3m,i,f
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

### SNr Add-On Endpoint Selection

The SNr model should use raw post-combination scores when available, following an ANCOVA-style endpoint-specific design:

```text
If valid STN+SNr immediate data exist:
  baseline phase = STN-3m
  post phase     = STN+SNr-immediate
  model class    = acute

Otherwise, if valid STN+SNr 3m data exist:
  baseline phase = STN-3m
  post phase     = STN+SNr-3m
  model class    = chronic
```

Use `MIN_N_FOR_MODEL = 12`. Do not hard-code scale names into endpoint selection. Choose the endpoint per scale based on complete paired score and exposure availability.

### Two Primary SNr Best-Site Estimands

Keep two primary SNr best-site analyses because they answer different but complementary questions.

#### Scheme 1: SNr-Component Adjusted Map

This is the component-focused SNr model:

```text
Y_post_i = alpha_0
         + theta_SNr(s) * X_SNr,i(s)
         + beta         * Y_STN3m_i
         + gamma        * DeltaSTNScore_i
         + error_i
```

Question:

```text
Among patients with comparable STN-only 3-month status and comparable STN-component changes,
does final SNr exposure at location s, voxel v, or streamline f predict better STN+SNr outcome?
```

Interpretation:

```text
theta_SNr(s)
```

is the adjusted spatial association between SNr-component exposure and the STN+SNr outcome, conditional on pre-SNr clinical status and concurrent STN reprogramming.

Use this model when the goal is to isolate the SNr component as much as possible with the available observational data.

#### Scheme 2: Clinician-Optimized Final A+B Strategy Map

This is the policy or strategy-focused model:

```text
Y_post_i = alpha_0
         + theta_opt(s) * X_SNr,i(s)
         + beta         * Y_STN3m_i
         + error_i
```

Question:

```text
Under the actual clinical programming policy, after clinicians selected the final optimized STN+SNr setting,
which final SNr locations, voxels, or streamlines are associated with better STN+SNr outcome?
```

This model does not adjust for `DeltaSTNScore` because STN changes are treated as part of the final clinician-optimized A+B treatment strategy. It should not be interpreted as an independent SNr-component effect.

Interpretation:

```text
theta_opt(s)
```

is the adjusted spatial association between the clinician-selected final SNr exposure and the overall optimized STN+SNr outcome, conditional on pre-SNr clinical status.

This map should be named:

```text
clinician-optimized final SNr setting outcome map
clinical optimization-informed SNr sweet-spot map
```

It should not be named:

```text
pure causal SNr efficacy map
absolute biological efficacy map of the SNr target
```

For scales where lower scores are better:

```text
H_SNr(s) = -theta_SNr(s)
H_opt(s) = -theta_opt(s)
```

For SE-ADL, where higher scores are better:

```text
H_SNr(s) = theta_SNr(s)
H_opt(s) = theta_opt(s)
```

Positive heatmap values always indicate better predicted clinical outcome.

### Primary SNr Component Model

For each scale and streamline:

```text
Y_post_i = alpha_0
         + alpha_SNr,f * X_SNr,i,f
         + alpha_B     * Y_STN3m_i
         + alpha_D     * DeltaSTNScore_i
         + error_i
```

Definitions:

- `Y_post_i`: selected post-combination raw clinical score for patient `i`.
- `Y_STN3m_i`: STN-only 3-month raw score for patient `i`.
- `X_SNr,i,f`: SNr-component streamline exposure for fiber `f`.
- `DeltaSTNScore_i`: scalar summary of STN exposure change between STN-only and combined programming.
- `alpha_SNr,f`: streamline-specific coefficient of interest.

Use a rank-based partial Spearman estimator as the main implementation for `n = 16`:

1. Rank-transform `Y_post`, `X_SNr,f`, `Y_STN3m`, and `DeltaSTNScore`.
2. Regress ranked `Y_post` on ranked `Y_STN3m` and ranked `DeltaSTNScore`; keep residuals.
3. Regress ranked `X_SNr,f` on ranked `Y_STN3m` and ranked `DeltaSTNScore`; keep residuals.
4. Correlate the two residual vectors.
5. Flip sign when higher clinical score means worse outcome, so positive scores always indicate benefit.

```text
SNrBenefitScore_f > 0 means stronger SNr exposure predicts better clinical outcome.
```

This model implements Scheme 1 above. Scheme 2 uses the same endpoint selection, exposure definitions, and benefit-score orientation, but omits `DeltaSTNScore` because it describes the final optimized A+B strategy rather than the SNr component adjusted for STN reprogramming.

### SNr Best-Site Estimand Boundaries

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

They estimate spatial associations between final SNr exposure and post-combination outcome after conditioning on the selected baseline state.

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

Therefore, the SNr maps are patient-level between-subject spatial association maps. They are not within-patient randomized location-response maps.

### Scientific Preconditions for SNr Best-Site Inference

The SNr best-site analyses are scientifically meaningful under these conditions:

- `Y_STN3m` adequately represents the clinical state before SNr addition.
- `DeltaSTNScore` adequately summarizes STN-component changes for Scheme 1.
- The final SNr setting is a clinically optimized setting, not an arbitrary or poorly explored setting.
- Acute programming response and side-effect thresholds used to choose the final SNr setting have reasonable relevance to the 3-month outcome.
- SNr exposure has enough spatial variability across patients to estimate a map.
- Within comparable ranges of `Y_STN3m` and, for Scheme 1, `DeltaSTNScore`, there is sufficient overlap in SNr locations to avoid relying mainly on extrapolation.
- Unmeasured prognosis factors, symptom subtypes, medication changes, rehabilitation intensity, anatomy, and programming style do not strongly determine both the final SNr location and the later STN+SNr outcome.
- STN and SNr effects are sufficiently separable for an additive model to remain interpretable.

Coverage must be reported for every surface, voxel, and fiber model:

```text
Coverage(s) = sum_i X_SNr,i(s)
```

Only regions or streamlines with adequate coverage should receive strong anatomical interpretation.

### Potential Problems with the SNr Best-Site Definition

Main limitations:

- The maps are not pure causal maps of SNr spatial efficacy.
- Clinician selection can induce indication bias because different SNr regions may be selected for different patient subtypes.
- `Y_STN3m` controls total pre-SNr severity, but may not fully control symptom composition, DBS responsiveness, future prognosis, or side-effect limitations.
- `DeltaSTNScore` may be an incomplete summary of STN reprogramming because STN changes can involve contact, amplitude, pulse width, frequency, e-field shape, and fiber recruitment.
- `X_SNr(s)` and `DeltaSTNScore` may be collinear if certain SNr locations are systematically paired with certain STN programming changes.
- Low-coverage locations or streamlines can generate unstable coefficients.
- With `n = 16`, interaction models such as `X_SNr(s) * subtype` or `X_SNr(s) * DeltaSTNScore` are usually too unstable for primary inference.
- Normative connectomes support group-level structural interpretation, not individualized tractography.
- Random or Gaussian proxy stimulation results validate the pipeline only and should not be biologically interpreted.

The most defensible wording is:

```text
adjusted relative SNr-target sweet-spot map
clinical optimization-informed final SNr setting outcome map
```

Avoid:

```text
absolute causal map of SNr efficacy
evidence that every patient should be stimulated at this location
```

### STN Reprogramming Confound

Do not interpret `STN+SNr - STN-alone` as pure SNr benefit if STN parameters changed between phases.

SNr Scheme 1 controls this by including:

```text
DeltaSTNScore = STN exposure scalar in combined setting - STN exposure scalar in STN-alone setting
```

Recommended main scalar:

```text
STNScore_i = sum of STN-component exposure in a prespecified STN motor ROI
```

or, once an STN model is available:

```text
STNScore_i = weighted overlap with the learned STN sweet-spot or sweet-fiber model
```

### Residualized SNr Sensitivity Model

As a complementary sensitivity analysis:

1. Train an STN response model on STN-alone data.
2. Predict the expected STN contribution in the combined phase using the combined-phase STN component.
3. Compute:

```text
Y_SNr_residual = observed STN+SNr outcome - predicted STN contribution
```

4. Model `Y_SNr_residual` against SNr-component exposure.

Use leave-one-patient-out predictions for any residualized model to avoid optimistic reuse of the same patient in both training and prediction.

## Fiber and Sweet-Spot Definitions

### Voxel Sweet Spot

For each voxel and outcome, model the relation between subject-level stimulation exposure at that voxel and clinical response.

For the STN model, use STN-alone exposure and STN response. For SNr Scheme 1, use SNr-component exposure and endpoint-specific post-score models adjusted for STN-3m baseline and STN exposure change. For SNr Scheme 2, use SNr-component exposure and endpoint-specific post-score models adjusted for STN-3m baseline only, because this scheme estimates the clinician-optimized final A+B strategy map.

### Whole-Streamline Fiber Filtering

Use whole streamlines from the public connectome. Do not crop streamlines to STN/SNr internal segments.

Main candidate fiber definitions:

```text
STN-associated candidate fiber:
  whole streamline intersects Custom STN ROI

SNr-associated candidate fiber:
  whole streamline intersects Custom SNr ROI

STN+SNr-associated candidate fiber:
  whole streamline intersects both Custom STN and Custom SNr ROIs
```

The exposure value is still sampled from the full stimulation map along the whole streamline:

```text
X_subject,fiber = max exposure along the full streamline
```

The peak may occur near the nucleus edge or outside the strict ROI boundary.

### Endpoint-Specific Reporting

For each significant or top-ranked fiber:

- report connectome name;
- report streamline ID;
- report model class: `acute` or `chronic`;
- report scale;
- report `SNrBenefitScore` or STN benefit score;
- report whether it intersects Custom STN, Custom SNr, or both;
- report HCPex endpoint labels;
- report whether the effect is sweet or sour.

## Statistical Plan

### Main Tests

- STN primary model: baseline-adjusted partial Spearman between STN-only 3-month exposure and STN-only 3-month raw score, adjusting for preoperative raw score.
- STN secondary early model: baseline-adjusted partial Spearman between STN-immediate exposure and STN-immediate raw score, adjusting for preoperative score or same-day STN-OFF score when available.
- SNr Scheme 1 model: endpoint-specific partial Spearman model with `Y_STN3m` and `DeltaSTNScore` as covariates, estimating the SNr-component adjusted map.
- SNr Scheme 2 model: endpoint-specific partial Spearman model with `Y_STN3m` as the covariate, estimating the clinician-optimized final A+B strategy map.
- Primary inference is scale-specific; do not combine heterogeneous scales into one primary model.
- Correct multiple comparisons within each scale, connectome, and model class using FDR.
- Use patient-level permutation tests with seed `42` for empirical significance.

### Endpoint Hierarchy

Recommended reporting hierarchy:

- primary STN endpoint: chronic STN-only efficacy model using `Preop -> STN-3m`;
- secondary STN endpoint: early / acute STN-only response model using `Preop -> STN-immediate`, or `STN-OFF same-day -> STN-immediate` when same-day baseline exists;
- optional STN endpoint: chronic adaptation model using `STN-immediate -> STN-3m`;
- primary SNr best-site Scheme 1: SNr-component adjusted map with `DeltaSTNScore`;
- primary SNr best-site Scheme 2: clinician-optimized final A+B strategy map without `DeltaSTNScore`;
- primary SNr mechanistic endpoint within both schemes: UPDRS-III acute SNr-addition model when valid immediate data are available;
- key secondary SNr endpoint within both schemes: UPDRS-III chronic SNr-addition model to evaluate longer-term motor relevance;
- symptom-specific secondary SNr endpoints within both schemes: axial UPDRS-III, FOG-Q, KPPS, PDQ-39, MADRS, ADL, SE-ADL, and other available scales using their selected endpoints;
- exploratory cross-scale summaries: map overlap, meta-map, or pooled/global model.

### Cross-Validation

Use leave-one-patient-out cross-validation for `n = 16`.

For each held-out subject:

1. Train the sweet-spot or sweet-fiber model on the remaining subjects.
2. Compute the held-out subject's weighted exposure score.
3. Compare predicted score with observed adjusted outcome.

Report:

- cross-validated Spearman rho;
- permutation P value;
- number of complete subjects;
- endpoint class;
- sensitivity-model agreement.

### Cross-Scale Map-Level Summary

After fitting scale-specific models, evaluate convergence at the map level rather than by pooling clinical outcomes into one primary regression.

Recommended map-level metrics:

```text
spatial correlation between scale maps
Dice overlap of top 5% sweet maps
Jaccard overlap of top 5% sweet maps
center-of-mass distance between top sweet regions
```

A secondary global SNr benefit map may be generated only after scale-specific fitting:

```text
GlobalSNrScore_f = mean_s z(SNrBenefitScore_s,f)
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
- streamline-specific STN exposure change instead of scalar `DeltaSTNScore`;
- minimal-STN-change subgroup after excluding subjects with the largest absolute STN exposure change;
- binary VTA intersection instead of continuous peak exposure;
- interleaving-specific union, overlap, and frequency-weighted exposure summaries;
- local ROI-expanded peak exposure using Custom STN/SNr dilated by `2-3 mm`;
- charge-rate proxy using `abs(voltage_V) * pulse_width_us * frequency_Hz`;
- OSS-DBS/PAM pathway activation model when valid outputs exist;
- repeated analyses across dTOR-985, MGH-USC HCP 32, and PPMI 85 connectomes.

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
7. Extract voxel and streamline exposure matrices.
8. Fit the primary chronic STN-only model.
9. Fit secondary STN-only early / acute models where valid immediate data exist.
10. Fit optional STN chronic adaptation models when justified by programming changes.
11. Fit endpoint-specific SNr Scheme 1 models with `DeltaSTNScore`.
12. Fit endpoint-specific SNr Scheme 2 models without `DeltaSTNScore`.
13. Fit sensitivity models.
14. Label top fibers by Custom STN/SNr and HCPex endpoints.
15. Export CSV/Mat/JSON provenance and visualization-ready fiber subsets.

## Expected Outputs

Use an output root outside tracked code, for example:

```text
/Users/mojackhu/Github/leaddbs/connectomes/dMRI/public_tracking/STN_SNr/endpoint_specific_sweetspot/
```

Expected output groups:

- `provenance/`: input paths, software versions, random seed, model settings.
- `qc/`: subject inclusion, endpoint selection, missingness, ROI volumes, connectome availability.
- `exposure/`: subject-level exposure summaries and streamline exposure matrices.
- `exposure/interleaving/`: subprogram exposure maps, union maps, overlap maps, and optional timing-weighted maps.
- `models/stn/chronic/`: primary chronic STN-only sweet-spot and sweet-fiber results.
- `models/stn/early/`: secondary early / acute STN-only response results.
- `models/stn/adaptation/`: optional STN chronic adaptation results.
- `models/snr/component_adjusted/`: Scheme 1 endpoint-specific SNr-component adjusted model results.
- `models/snr/final_strategy/`: Scheme 2 clinician-optimized final A+B strategy model results.
- `models/cross_scale/`: map-level similarity metrics and secondary global maps.
- `sensitivity/`: all sensitivity model outputs.
- `visualization/`: top fiber subsets, sweet/sour maps, HCPex endpoint summaries.

## Acceptance Checks

- `random_seed` is `42` in all stochastic steps.
- The analysis does not crop VTA/e-field/proxy maps to STN/SNr masks.
- Interleaving stimulation is split into subprograms and is not treated as simultaneous double-cathode stimulation.
- Interleaving outputs include union exposure and overlap exposure when interleaving programs exist.
- Streamlines are whole connectome streamlines, not STN/SNr internal fragments.
- STN/SNr labels come from `Custom_Ewert_Zhang_Middlebrooks0.05`.
- Non-STN/SNr endpoint labels come from HCPex.
- The primary STN model uses raw STN-3m score adjusted for raw preoperative score, not percent improvement as the main outcome.
- STN-immediate models are marked secondary and use same-day STN-OFF baseline when available.
- SNr Scheme 1 includes both `Y_STN3m` and `DeltaSTNScore`.
- SNr Scheme 2 includes `Y_STN3m` and deliberately omits `DeltaSTNScore`.
- SNr results include coverage maps, and low-coverage regions or streamlines are not strongly interpreted.
- The implementation can run a PPMI smoke test before dTOR full-scale analysis.
- dTOR and MGH access is chunked and memory-safe.
- `my_helper/fiber/stnsnr` contains only pipeline scripts, not core helper functions.
- scale-specific maps are generated before any cross-scale summary map.
- any pooled cross-scale model is marked exploratory.

## Interpretation Rules

- Primary STN results can be described as chronic STN-only therapeutic fibers or sweet spots.
- STN-immediate results should be described as early STN-only response maps, or acute STN stimulation response maps only when same-day STN-OFF baseline is used.
- STN adaptation results should be described as secondary programming/adaptation analyses, not as the main STN efficacy model.
- SNr Scheme 1 results should be described as SNr add-on-associated effects adjusted for STN-3m baseline and concurrent STN exposure change.
- SNr Scheme 2 results should be described as clinician-optimized final SNr setting outcome maps for the overall optimized STN+SNr strategy.
- Residualized SNr results should be described as STN-model-adjusted SNr-associated residual benefit, not as definitive pure SNr causal effect.
- SNr maps should not be described as pure causal maps showing that every patient should be stimulated at a given SNr location.
- Interleaving union maps should be described as exposure across an interleaving cycle, not as one simultaneous continuous electric field.
- Interleaving overlap maps should be described as tissue or fibers exposed to both pulse trains.
- Scale-specific maps are the primary results for symptom-specific inference.
- Global or pooled maps are secondary/exploratory summaries of cross-scale convergence.
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
