# STN/SNr Normative Connectome Sweet/Sour Spot Technical Details

Date: 2026-07-01

## Purpose

This document fixes the technical design for symptom-specific STN and SNr sweet/sour spot analyses based on the current clinical programming data and public normative structural connectomes.

The analysis has two main goals:

1. Identify STN-only stimulation voxels and streamlines associated with stable STN therapeutic benefit.
2. Identify SNr stimulation voxels and streamlines associated with additional benefit after SNr is added to STN stimulation.

This is an internal technical document, not a manuscript Methods section. It records data sources, modeling definitions, execution steps, expected outputs, and interpretation limits.

## Data Sources

### Programming Data

Use the current follow-up stimulation workbook as the authoritative programming source:

```text
/Users/mojackhu/Research/STNSNr/summary/cohort/subj/followup_stimulation.xlsx
```

Use the `Contact Parameters` sheet for model input. It contains one row per subject, phase, protocol, target, side, contact, and stimulation program.

Required columns:

```text
ID
Phase
Protocol
Contact
Target
Side
Voltage
PulseWidth
Frequency
ParameterSource
StimulationPattern
AlternatingGroup
Notes
```

Current inspected table characteristics:

```text
subjects: 16
contact-parameter rows: 194
phases: immediate, 3m
protocols: STN, STN+SNr
targets: STN, SNr
stimulation patterns: continuous, alternating
```

### Clinical Score Data

Use the raw clinical score workbook for primary ANCOVA-style endpoint models:

```text
/Users/mojackhu/Research/STNSNr/summary/cohort/subj/subject_effect_origin.xlsx
```

The current inspected conditions are:

```text
Pre-op
STN (immediate)
STN (3 m)
STN+SNr (immediate)
STN+SNr (3 m)
```

Use the improvement-rate table for direction checks, descriptive summaries, smoke tests, and sensitivity analyses:

```text
/Users/mojackhu/Research/STNSNr/summary/cohort/subj/subj_delta_effect.xlsx
```

Do not use the improvement-rate table as the primary STN or SNr spatial model target unless explicitly running a sensitivity analysis.

### Normative Structural Connectomes

Use the locally installed Lead-DBS dMRI structural connectomes:

```text
/Users/mojackhu/Github/leaddbs/connectomes/dMRI/dTOR-985 Full (Elias 2024)/data.mat
/Users/mojackhu/Github/leaddbs/connectomes/dMRI/MGH-USC HCP 32 (Horn 2017)/data.mat
/Users/mojackhu/Github/leaddbs/connectomes/dMRI/PPMI 85 (Ewert 2017)/data.mat
```

Execution order:

1. Run pipeline smoke tests on `PPMI 85 (Ewert 2017)`.
2. Run intermediate-scale validation on `MGH-USC HCP 32 (Horn 2017)`.
3. Run the main analysis on `dTOR-985 Full (Elias 2024)`.

The dTOR and MGH connectomes are large. Implementations must use chunked access and must not load all streamlines into memory at once.

### Atlas And ROI Data

The authoritative target-atlas registry is:

```text
/Users/mojackhu/Github/leaddbs/my_helper/stnsnr/stnsnr_seed_target_atlas_registry.md
```

Main rules:

- Primary STN and SNr ROIs use `Custom_Ewert_Zhang_Middlebrooks0.05`.
- Custom STN/SNr masks are used for anatomical classification and reporting, not for clipping stimulation fields.
- Non-STN/SNr cortical and whole-brain endpoint labeling uses `HCPex (Huang 2021)` when suitable labels exist.
- Thalamic subnuclei, PPN, and superior colliculus targets follow the atlas registry.

## Exposure Definitions

### Main Stimulation Exposure

The main exposure is full-field peak E-field or E-field-like proxy exposure.

For each subject, side, protocol, and phase, construct stimulation exposure maps for:

```text
STN-only STN component
STN+SNr STN component
STN+SNr SNr component
```

When true Lead-DBS e-field maps are available, use them as the primary exposure source. When they are not available, use a documented e-field-like proxy:

```text
Gaussian contact-centered exposure
weighted by absolute voltage
default sigma = 1.5 mm
multiple contacts in one component combined by voxel-wise maximum
```

Pulse width and frequency must be stored in provenance. They may be used in sensitivity analyses, such as charge-rate proxy:

```text
abs(voltage_V) * pulse_width_us * frequency_Hz
```

### VTA Boundary Rule

Do not crop VTA, e-field, or proxy maps to STN/SNr boundaries. VTA may extend beyond the nucleus edge, and this extension is part of the modeled stimulation exposure.

Custom STN/SNr masks are used only for:

```text
fiber classification
voxel-map anatomical overlays
coverage summaries
interpretation boundaries
```

### Interleaving Handling

Interleaving stimulation is not equivalent to simultaneous double-cathode stimulation.

For each alternating program, compute each subprogram separately:

```text
Program A -> exposure_A
Program B -> exposure_B
```

Main interleaving output:

```text
union exposure = tissue or streamlines exposed by at least one subprogram
```

Required sensitivity or descriptive output:

```text
overlap exposure = tissue or streamlines exposed by both subprograms
```

Optional sensitivity output:

```text
frequency-weighted exposure = weighted sum of subprogram exposures
```

Use frequency-weighted exposure only when timing, pulse-count, or duty-cycle information is reliable. Otherwise, report union and overlap without inventing timing weights.

### Streamline Exposure

Use whole streamlines from the public connectome. Do not truncate streamlines to the internal STN/SNr segment.

Main streamline exposure:

```text
X_subject,fiber = max exposure along the full streamline
```

Sensitivity summaries:

```text
mean exposure along the full streamline
top-5% exposure along the full streamline
binary VTA intersection
OSS-DBS / pathway activation value when available
```

### Voxel Exposure

Voxel-wise models use subject-level stimulation exposure at each voxel.

Main voxel analysis mask:

```text
cohort stimulation union mask
```

The mask should include voxels exposed in at least a prespecified minimum number of subjects. Low-coverage voxels must be reported and should not receive strong anatomical interpretation.

## Clinical Endpoint Direction

All model scores must be oriented so that positive benefit scores mean better predicted clinical outcome.

Lower scores indicate better status for:

```text
UPDRS-III
UPDRS-III axial
FOG-Q
PDQ-39
KPPS
MADRS
ADL
```

For these scales, lower post-treatment raw scores indicate better outcome. Residuals or coefficients must be sign-flipped when generating benefit-oriented maps.

SE-ADL is higher-is-better. Do not sign-flip SE-ADL outcome residuals when generating benefit-oriented maps.

## STN Model

### Primary Chronic STN-Only Efficacy Model

Purpose:

```text
Identify voxels or streamlines where stronger STN-only exposure predicts better stable STN 3-month outcome.
```

For each clinical scale and each voxel or streamline location `s`:

```text
Y_STN3m_i = alpha_0
          + alpha_STN(s) * X_STN3m_i(s)
          + beta         * Y_Preop_i
          + error_i
```

Definitions:

```text
Y_STN3m_i    = raw STN-only 3-month clinical score for subject i
Y_Preop_i    = raw preoperative clinical score for subject i
X_STN3m_i(s) = STN-only 3-month stimulation exposure at voxel/streamline s
alpha_STN(s) = STN spatial coefficient of interest
```

Main estimator:

```text
rank-based partial Spearman / residualized regression
```

Benefit-oriented implementation:

```text
STNBenefitScore(s) =
  corr(
    residual(rank(X_STN3m(s)) ~ rank(Y_Preop)),
    benefit_oriented_residual(rank(Y_STN3m) ~ rank(Y_Preop))
  )
```

Interpretation:

```text
STNBenefitScore(s) > 0 = stronger STN exposure predicts better baseline-adjusted STN 3-month outcome
STNBenefitScore(s) < 0 = stronger STN exposure predicts worse baseline-adjusted STN 3-month outcome
```

### Secondary STN Immediate Response Model

Run this model only for scales with valid immediate STN assessment.

Default model when only preoperative baseline is available:

```text
Y_STNImmediate_i = alpha_0
                 + alpha_STN_immediate(s) * X_STNImmediate_i(s)
                 + beta                   * Y_Preop_i
                 + error_i
```

If a same-day STN-off baseline exists later, use that baseline instead:

```text
Y_STNImmediate_i = alpha_0
                 + alpha_STN_acute(s) * X_STNImmediate_i(s)
                 + beta               * Y_STNOffSameDay_i
                 + error_i
```

The same-day baseline version can be called an acute STN stimulation response model. The preoperative-baseline version should be called an early STN-only response model.

## SNr Gain Models

The SNr model family has one primary estimand:

```text
clinical optimization-informed SNr-target gain model
```

It asks whether the final clinician-optimized SNr component exposure predicts better STN+SNr outcome after controlling the pre-SNr STN 3-month clinical state and the concurrent STN component exposure change.

The model has two endpoints:

```text
chronic SNr gain endpoint: STN+SNr 3m relative to STN 3m
immediate SNr gain endpoint: STN+SNr immediate relative to STN 3m
```

### Chronic SNr Gain Model

Purpose:

```text
Estimate the long-term spatial distribution of SNr-associated gain after adding SNr to STN stimulation.
```

Model:

```text
Y_AB3m_i = alpha_0
         + theta_SNr_chronic(s) * X_SNr3m_i(s)
         + beta                 * Y_STN3m_i
         + gamma                * DeltaSTNScore_3m_i
         + error_i
```

Definitions:

```text
Y_AB3m_i            = raw STN+SNr 3-month clinical score for subject i
Y_STN3m_i           = raw STN-only 3-month clinical score for subject i
X_SNr3m_i(s)        = STN+SNr 3-month SNr-component exposure at voxel/streamline s
DeltaSTNScore_3m_i  = scalar STN component exposure change from STN-only 3m to STN+SNr 3m
theta_SNr_chronic   = chronic SNr gain spatial coefficient of interest
```

Interpretation:

```text
Among subjects with comparable STN-only 3-month clinical state and comparable STN component change,
does final SNr 3-month exposure at s predict better STN+SNr 3-month outcome?
```

### Immediate SNr Gain Model

Purpose:

```text
Estimate the immediate spatial distribution of SNr-associated gain after adding SNr to STN stimulation.
```

Model:

```text
Y_ABimmediate_i = alpha_0
                + theta_SNr_immediate(s) * X_SNrImmediate_i(s)
                + beta                   * Y_STN3m_i
                + gamma                  * DeltaSTNScore_immediate_i
                + error_i
```

Definitions:

```text
Y_ABimmediate_i              = raw STN+SNr immediate clinical score for subject i
Y_STN3m_i                    = raw STN-only 3-month clinical score for subject i
X_SNrImmediate_i(s)          = STN+SNr immediate SNr-component exposure at voxel/streamline s
DeltaSTNScore_immediate_i    = scalar STN component exposure change from STN-only 3m to STN+SNr immediate
theta_SNr_immediate          = immediate SNr gain spatial coefficient of interest
```

Interpretation:

```text
Among subjects with comparable STN-only 3-month clinical state and comparable immediate-phase STN component change,
does final SNr immediate exposure at s predict better STN+SNr immediate outcome?
```

The `Y_STN3m` covariate controls the pre-SNr disease state. `DeltaSTNScore_immediate` controls concurrent STN component reprogramming in the immediate STN+SNr setting. If a same-day pre-SNr STN-only score becomes available, add a sensitivity model using that same-day baseline to control short-term disease fluctuation more directly.

### SNr Rank-Based Implementation

For `n = 16`, use rank-based partial Spearman or equivalent residualized regression as the main implementation.

For each endpoint and each voxel or streamline `s`:

1. Rank-transform `Y_AB`, `X_SNr(s)`, `Y_STN3m`, and `DeltaSTNScore`.
2. Regress ranked `Y_AB` on ranked `Y_STN3m` and ranked `DeltaSTNScore`; keep residuals.
3. Regress ranked `X_SNr(s)` on ranked `Y_STN3m` and ranked `DeltaSTNScore`; keep residuals.
4. Correlate the two residual vectors.
5. Orient the resulting score so positive values mean better clinical outcome.

For lower-is-better scales:

```text
H_SNr(s) = -theta_SNr(s)
```

For SE-ADL:

```text
H_SNr(s) = theta_SNr(s)
```

Output names:

```text
SNrChronicGainScore(s)
SNrImmediateGainScore(s)
```

Positive values indicate sweet regions or sweet streamlines. Negative values indicate sour regions or sour streamlines.

## Streamline-Based Outputs

For each connectome, model class, scale, and endpoint, export:

```text
fiber_id
connectome_name
scale
endpoint_class
model_name
benefit_score
rho_or_beta
p_value
q_value
coverage
exposure_prevalence
sweet_or_sour
intersects_custom_stn
intersects_custom_snr
intersects_both_stn_snr
endpoint_labels
```

Also export:

```text
top sweet streamline subsets
top sour streamline subsets
sweet streamline density maps
sour streamline density maps
coverage density maps
```

## Voxel-Based Outputs

For each model, scale, and endpoint, export NIfTI or MATLAB volumes for:

```text
rho_or_beta map
p-value map
q-value map
sweet binary map
sour binary map
coverage map
bootstrap stability map
```

Voxel maps should be interpreted with Custom STN/SNr outlines and target-atlas overlays, but the model itself is not cropped to those ROIs.

## Execution Plan

### Stage 1: Input Validation

1. Confirm that `followup_stimulation.xlsx` exists and contains `Contact Parameters`.
2. Confirm required programming columns are present.
3. Confirm that subject IDs match between programming data and clinical score tables.
4. Confirm that raw score conditions include `Pre-op`, `STN (3 m)`, `STN+SNr (immediate)`, and `STN+SNr (3 m)`.
5. Confirm that the three normative connectome `data.mat` files are present.
6. Confirm atlas registry paths exist.

### Stage 2: Exposure Map Construction

1. Parse STN-only, STN+SNr STN-component, and STN+SNr SNr-component programming rows.
2. Split interleaving rows by `AlternatingGroup`.
3. Generate component exposure maps for each subject, side, phase, protocol, and target.
4. Generate interleaving union and overlap maps.
5. Save provenance for voltage, pulse width, frequency, contacts, target, side, phase, and protocol.

### Stage 3: Clinical Endpoint Assembly

1. Build scale-specific raw score tables.
2. Select STN chronic endpoints using `Pre-op` and `STN (3 m)`.
3. Select SNr chronic gain endpoints using `STN (3 m)` and `STN+SNr (3 m)`.
4. Select SNr immediate gain endpoints using `STN (3 m)` and `STN+SNr (immediate)`.
5. Record missingness per scale and endpoint.
6. Apply `MIN_N_FOR_MODEL = 12`.

### Stage 4: Streamline Exposure Extraction

1. Run PPMI smoke test first.
2. Load connectome streamlines in chunks.
3. Compute full-streamline peak exposure for each subject.
4. Record candidate fiber classes using Custom STN and SNr intersection.
5. Label endpoints using HCPex and registry-defined target atlases when available.
6. Repeat for MGH and dTOR after PPMI validation.

### Stage 5: Voxel Exposure Extraction

1. Build cohort stimulation union mask.
2. Apply minimum coverage rules.
3. Extract subject-by-voxel exposure matrices in chunks when needed.
4. Save coverage and exposure prevalence maps.

### Stage 6: Model Fitting

Fit each model separately by scale:

```text
STN chronic model
STN immediate model when valid
SNr chronic gain model
SNr immediate gain model
```

Use patient-level permutation tests with random seed `42`. Correct multiple comparisons within each scale, connectome, endpoint, and model class using FDR.

### Stage 7: Stability And Sensitivity

Run:

```text
leave-one-patient-out validation
bootstrap stability
binary VTA intersection sensitivity
mean and top-5% streamline exposure sensitivity
interleaving overlap sensitivity
charge-rate proxy sensitivity
OSS-DBS / pathway activation sensitivity when valid outputs exist
repeated analyses across PPMI, MGH, and dTOR
```

### Stage 8: Reporting

Generate:

```text
QC tables
subject inclusion tables
model setting provenance
streamline score tables
voxel maps
top fiber lists
atlas endpoint summaries
coverage summaries
cross-connectome consistency summaries
```

## Expected Output Root

Use an output root outside tracked source code:

```text
/Users/mojackhu/Github/leaddbs/connectomes/dMRI/public_tracking/STN_SNr/endpoint_specific_sweetspot/
```

Recommended subdirectories:

```text
provenance/
qc/
exposure/
exposure/interleaving/
models/stn/chronic/
models/stn/immediate/
models/snr/chronic_gain/
models/snr/immediate_gain/
models/cross_scale/
sensitivity/
visualization/
```

## Limitations And Interpretation Boundaries

### Observational Spatial Association

The SNr gain maps are between-subject spatial association maps. They are not within-patient randomized location-response maps.

The observed final SNr setting is:

```text
C_i* = final SNr setting selected for subject i after clinical programming
```

The observed outcome is:

```text
Y_i(C_i*)
```

The data do not contain:

```text
Y_i(s) for every possible SNr location s
```

Therefore, the maps should not be described as pure causal efficacy maps showing that every patient should be stimulated at a specific SNr location.

### Residual Confounding

`Y_STN3m` controls the pre-SNr total clinical state. It may not fully control:

```text
symptom composition
long-term prognosis
DBS responsiveness
medication changes
rehabilitation exposure
side-effect thresholds
clinician programming strategy
individual anatomy
```

`DeltaSTNScore` controls a scalar summary of STN component reprogramming. It may not fully capture changes in:

```text
contact location
amplitude
pulse width
frequency
field shape
fiber recruitment
STN-SNr interaction
```

### Coverage And Sample Size

The cohort currently has `n = 16`. High-dimensional interaction models should not be used for primary inference.

Low-coverage voxels or streamlines can produce unstable coefficients. Every model must export coverage maps or coverage summaries.

### Normative Connectome Limits

Normative connectomes support group-level structural interpretation. They do not represent each subject's individual DWI anatomy.

Cross-connectome replication is required before making strong pathway-specific claims.

### dTOR Processing Limit

The dTOR connectome is large. All dTOR analyses must use chunked streamline and exposure processing. Any implementation that loads the full dTOR `fibers` matrix into memory is invalid.

## Acceptance Checks

Before running full analysis, confirm:

```text
random seed is 42
programming table and raw score table subject IDs match
STN/SNr atlas registry is used for ROI definitions
VTA/e-field/proxy maps are not cropped to STN/SNr
interleaving is split into subprograms
union and overlap interleaving outputs are generated
PPMI smoke test completes before MGH or dTOR
STN chronic, SNr chronic gain, and SNr immediate gain outputs are created
low-coverage voxels and streamlines are flagged
all outputs include provenance
```

