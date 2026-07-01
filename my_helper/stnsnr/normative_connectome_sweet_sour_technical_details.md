# STN/SNr Normative Connectome Sweet/Sour Spot Technical Details

Date: 2026-07-01

## Purpose

This document fixes the technical design for symptom-specific STN and SNr target-level seed-target analyses based on the current clinical programming data, public normative structural connectomes, and individualized DWI tractography.

The analysis has two main goals:

1. Identify STN-only target-level connectivity features associated with stable STN therapeutic benefit.
2. Identify SNr target-level connectivity features associated with additional benefit after SNr is added to STN stimulation.
3. Use voxel and fiber outputs as secondary localization, QC, and visualization products rather than as the primary predictor-selection unit.

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

### Individualized DWI Tractography

Use the current imported DWI log as the individualized DWI source:

```text
/Volumes/VAL/STNSNr/derivatives/leaddbs/import_logs/dwi_import_20260701_013240.csv
```

The DWI registration prerequisites are fixed in:

```text
/Users/mojackhu/Github/leaddbs/my_helper/stnsnr/dwi_registration_technical_details.md
```

Individualized DWI is incorporated as a target-level seed-target feature source:

```text
C_ind(i,h,k) = patient i, side h, target k connectivity
C_ind_bilat(i,k) = (C_ind(i,L,k) + C_ind(i,R,k)) / 2
```

Main DWI interpretation requires target coverage QC. A target should not enter the main individualized-DWI model if it is missing or unreliably reconstructed in too many patients. The preferred threshold is that a target has usable bilateral streamlines in at least `12/16` patients, with `13/16` as a stricter sensitivity rule.

The three planned data-source models are:

- `Normative-only`: target weights and scores from public connectomes.
- `Normative-guided individualized DWI`: target selection and weights from normative connectomes, score computed from individualized DWI features.
- `Individualized-DWI-only`: target selection and weights from individualized DWI features as sensitivity analysis.

The preferred connectivity model after DWI QC is the normative-guided individualized DWI target-level model.

### Atlas And ROI Data

The authoritative target-atlas registry is:

```text
/Users/mojackhu/Github/leaddbs/my_helper/stnsnr/stnsnr_seed_target_atlas_registry.md
```

Main rules:

- Model-level STN ROI and endpoint grouping should use `STN-connected regions` first:

```text
/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/atlases/STN-connected regions
```

- Model-level SNr ROI and endpoint grouping should use `SNr-connected regions` first:

```text
/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/atlases/SNr-connected regions
```

- Each connected-region atlas contains side-specific binary masks and `roi_manifest.csv`; use these files directly for model gating, candidate fiber classification, endpoint grouping, coverage summaries, and visualization overlays.
- `Custom_Ewert_Zhang_Middlebrooks0.05` remains the upstream source for STN/SNr masks inside the connected-region atlases and is retained as a sensitivity or fallback source for standalone STN/SNr masks.
- Non-STN/SNr cortical, thalamic, PPN, and superior colliculus endpoint definitions follow the connected-region atlas manifests and the seed-target atlas registry.

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

Connected-region atlas masks are used for:

```text
fiber classification
endpoint grouping
voxel-map anatomical overlays
coverage summaries
interpretation boundaries
```

Custom STN/SNr standalone masks are used only as sensitivity or fallback ROIs when the connected-region atlas is unavailable or when a high-confidence core threshold is explicitly being tested.

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

### Target-Level Connectivity Features

The primary connectivity model uses target-level features rather than top single-fiber predictors.

For each target label `k`, each patient `i`, and each side `h` in `{L,R}`, compute side-specific connectivity:

```text
C(i,h,k)
```

For public normative connectomes:

```text
G_norm(k,h) = streamlines with endpoint in same-side target P(k,h)
A_norm(i,h,j) = max exposure along streamline j from stimulation side h

C_norm(i,h,k) =
  sum_j A_norm(i,h,j) / (number of streamlines in G_norm(k,h) + lambda)
```

For individualized DWI:

```text
G_ind(i,k,h) = patient i streamlines with endpoint in same-side target P(k,h)
A_ind(i,h,j) = max exposure along patient streamline j from stimulation side h

C_ind(i,h,k) =
  sum_j A_ind(i,h,j) / (number of streamlines in G_ind(i,k,h) + lambda)
```

Use equal streamline weights within a target for the main analysis:

```text
q_j = 1
```

Left and right sides are then averaged to one patient-level feature:

```text
C_bilat(i,k) = (C(i,L,k) + C(i,R,k)) / 2
```

The primary statistical table has one row per patient (`n = 16`). Do not treat left and right hemispheres as independent observations. Left and right stimulation are computed in their own hemispheres against same-side homologous targets; no left-right flip is required for the target-level model.

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
Identify targets where stronger STN-only target connectivity predicts better stable STN 3-month outcome.
```

For each clinical scale and each target `k`:

```text
Y_STN3m_i = alpha_0
          + alpha_STN,k * C_STN3m_bilat(i,k)
          + beta         * Y_Preop_i
          + error_i
```

Definitions:

```text
Y_STN3m_i    = raw STN-only 3-month clinical score for subject i
Y_Preop_i    = raw preoperative clinical score for subject i
C_STN3m_bilat(i,k) = bilateral STN target-level connectivity for target k
alpha_STN,k = STN target coefficient of interest
```

Main estimator:

```text
rank-based partial Spearman / residualized regression
```

Benefit-oriented implementation:

```text
STNBenefitScore_k =
  corr(
    residual(rank(C_STN3m_bilat(k)) ~ rank(Y_Preop)),
    benefit_oriented_residual(rank(Y_STN3m) ~ rank(Y_Preop))
  )
```

Interpretation:

```text
STNBenefitScore_k > 0 = stronger STN target connectivity predicts better baseline-adjusted STN 3-month outcome
STNBenefitScore_k < 0 = stronger STN target connectivity predicts worse baseline-adjusted STN 3-month outcome
```

### Secondary STN Immediate Response Model

Run this model only for scales with valid immediate STN assessment.

Default model when only preoperative baseline is available:

```text
Y_STNImmediate_i = alpha_0
                 + alpha_STN_immediate,k * C_STNImmediate_bilat(i,k)
                 + beta                   * Y_Preop_i
                 + error_i
```

If a same-day STN-off baseline exists later, use that baseline instead:

```text
Y_STNImmediate_i = alpha_0
                 + alpha_STN_acute,k * C_STNImmediate_bilat(i,k)
                 + beta               * Y_STNOffSameDay_i
                 + error_i
```

The same-day baseline version can be called an acute STN stimulation response model. The preoperative-baseline version should be called an early STN-only response model.

## SNr Gain Models

The SNr model family has one primary estimand:

```text
clinical optimization-informed SNr-target gain model
```

It asks whether the final clinician-optimized SNr component target-level connectivity predicts better STN+SNr outcome after controlling the pre-SNr STN 3-month clinical state and the concurrent STN component exposure change.

The model has two endpoints:

```text
chronic SNr gain endpoint: STN+SNr 3m relative to STN 3m
immediate SNr gain endpoint: STN+SNr immediate relative to STN 3m
```

### Chronic SNr Gain Model

Purpose:

```text
Estimate the long-term target-level distribution of SNr-associated gain after adding SNr to STN stimulation.
```

Model:

```text
Y_AB3m_i = alpha_0
         + theta_SNr_chronic,k * C_SNr3m_bilat(i,k)
         + beta                 * Y_STN3m_i
         + gamma                * DeltaSTNScore_3m_i
         + error_i
```

Definitions:

```text
Y_AB3m_i            = raw STN+SNr 3-month clinical score for subject i
Y_STN3m_i           = raw STN-only 3-month clinical score for subject i
C_SNr3m_bilat(i,k)  = STN+SNr 3-month SNr-component bilateral connectivity to target k
DeltaSTNScore_3m_i  = scalar STN component exposure change from STN-only 3m to STN+SNr 3m
theta_SNr_chronic,k = chronic SNr gain target coefficient of interest
```

Interpretation:

```text
Among subjects with comparable STN-only 3-month clinical state and comparable STN component change,
does final SNr 3-month connectivity to target k predict better STN+SNr 3-month outcome?
```

### Immediate SNr Gain Model

Purpose:

```text
Estimate the immediate target-level distribution of SNr-associated gain after adding SNr to STN stimulation.
```

Model:

```text
Y_ABimmediate_i = alpha_0
                + theta_SNr_immediate,k * C_SNrImmediate_bilat(i,k)
                + beta                   * Y_STN3m_i
                + gamma                  * DeltaSTNScore_immediate_i
                + error_i
```

Definitions:

```text
Y_ABimmediate_i              = raw STN+SNr immediate clinical score for subject i
Y_STN3m_i                    = raw STN-only 3-month clinical score for subject i
C_SNrImmediate_bilat(i,k)    = STN+SNr immediate SNr-component bilateral connectivity to target k
DeltaSTNScore_immediate_i    = scalar STN component exposure change from STN-only 3m to STN+SNr immediate
theta_SNr_immediate,k        = immediate SNr gain target coefficient of interest
```

Interpretation:

```text
Among subjects with comparable STN-only 3-month clinical state and comparable immediate-phase STN component change,
does final SNr immediate connectivity to target k predict better STN+SNr immediate outcome?
```

The `Y_STN3m` covariate controls the pre-SNr disease state. `DeltaSTNScore_immediate` controls concurrent STN component reprogramming in the immediate STN+SNr setting. If a same-day pre-SNr STN-only score becomes available, add a sensitivity model using that same-day baseline to control short-term disease fluctuation more directly.

### SNr Rank-Based Implementation

For `n = 16`, use rank-based partial Spearman or equivalent residualized regression as the main implementation.

For each endpoint and each target `k`:

1. Rank-transform `Y_AB`, `C_SNr_bilat(k)`, `Y_STN3m`, and `DeltaSTNScore`.
2. Regress ranked `Y_AB` on ranked `Y_STN3m` and ranked `DeltaSTNScore`; keep residuals.
3. Regress ranked `C_SNr_bilat(k)` on ranked `Y_STN3m` and ranked `DeltaSTNScore`; keep residuals.
4. Correlate the two residual vectors.
5. Orient the resulting score so positive values mean better clinical outcome.

For lower-is-better scales:

```text
H_SNr,k = -theta_SNr,k
```

For SE-ADL:

```text
H_SNr,k = theta_SNr,k
```

Output names:

```text
SNrChronicGainScore_k
SNrImmediateGainScore_k
```

Positive values indicate sweet targets. Negative values indicate sour targets. Secondary voxel and streamline outputs may be generated to localize or visualize these target-level findings.

## Target-Level Outputs

For each connectome or DWI source, model class, scale, and endpoint, export:

```text
target_label
target_atlas
data_source
scale
endpoint_class
model_name
target_weight
benefit_score_k
rho_or_beta
p_value
q_value
coverage
C_left_summary
C_right_summary
C_bilat_summary
sweet_or_sour
endpoint_labels
```

For secondary fiber contribution outputs within selected targets, export:

```text
fiber_id
parent_target_label
connectome_name_or_dwi_subject
scale
endpoint_class
model_name
parent_target_weight
fiber_exposure_summary
coverage
intersects_custom_stn
intersects_custom_snr
intersects_both_stn_snr
endpoint_labels
```

Also export secondary visualization products:

```text
selected-target fiber subsets
target-weighted streamline density maps
target coverage maps
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

Voxel maps are secondary localization outputs. They should be interpreted with connected-region STN/SNr outlines and target-atlas overlays, but the primary target-level model itself is not cropped to those ROIs.

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

### Stage 4: Target Connectivity Extraction

1. Run PPMI smoke test first.
2. Load connectome streamlines in chunks.
3. Compute side-specific target connectivity `C(i,h,k)` using same-side targets.
4. Average left and right features into patient-level `C_bilat(i,k)`.
5. Record target coverage, streamline counts, and reconstruction failures.
6. Repeat for MGH and dTOR after PPMI validation.
7. Compute individualized DWI target connectivity and coverage after DWI registration QC passes.

### Stage 5: Secondary Voxel And Fiber Extraction

1. Build cohort stimulation union mask.
2. Apply minimum coverage rules.
3. Extract subject-by-voxel exposure matrices in chunks when needed.
4. Extract selected-target streamline exposure summaries for contribution and visualization.
5. Save coverage and exposure prevalence maps.

### Stage 6: Model Fitting

Fit each model separately by scale:

```text
STN chronic model
STN immediate model when valid
SNr chronic gain model
SNr immediate gain model
```

Use patient-level permutation tests with random seed `42`. Correct multiple comparisons across tested targets within each scale, connectome or DWI source, endpoint, and model class using FDR.

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
normative-only, normative-guided individualized DWI, and individualized-DWI-only target-level model comparison
```

### Stage 8: Reporting

Generate:

```text
QC tables
subject inclusion tables
model setting provenance
target weight tables
target connectivity matrices
target score tables
secondary streamline contribution tables
secondary voxel maps
selected-target fiber lists
atlas endpoint summaries
coverage summaries
cross-connectome consistency summaries
DWI coverage summaries
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
target_connectivity/
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

The SNr gain target maps and target scores are between-subject spatial association models. They are not within-patient randomized location-response maps.

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

Therefore, the target maps and secondary localization outputs should not be described as pure causal efficacy maps showing that every patient should be stimulated at a specific SNr location.

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

Low-coverage targets, voxels, or streamlines can produce unstable coefficients. Every model must export target coverage summaries and, for secondary maps, coverage maps.

### Normative Connectome Limits

Normative connectomes support group-level structural interpretation. They do not represent each subject's individual DWI anatomy. The normative-guided individualized DWI model tests whether the normative target pattern is expressed in each patient's own DWI tractography, but it remains limited by DWI reconstruction quality and coverage.

Cross-connectome replication is required before making strong pathway-specific claims.

### dTOR Processing Limit

The dTOR connectome is large. All dTOR analyses must use chunked streamline and exposure processing. Any implementation that loads the full dTOR `fibers` matrix into memory is invalid.

## Acceptance Checks

Before running full analysis, confirm:

```text
random seed is 42
programming table and raw score table subject IDs match
STN-connected regions and SNr-connected regions are used first for model ROI definitions
STN/SNr atlas registry is used for endpoint definitions and sensitivity/fallback ROI definitions
VTA/e-field/proxy maps are not cropped to STN/SNr
interleaving is split into subprograms
union and overlap interleaving outputs are generated
primary predictor selection is target-level, not top correlated single fibers
left and right connectivity are computed separately and averaged to one patient-level bilateral target feature
primary model tables have one row per patient, not one row per hemisphere
target-level DWI coverage is checked before individualized-DWI or normative-guided-DWI interpretation
PPMI smoke test completes before MGH or dTOR
STN chronic, SNr chronic gain, and SNr immediate gain outputs are created
low-coverage targets, voxels, and streamlines are flagged
all outputs include provenance
```
