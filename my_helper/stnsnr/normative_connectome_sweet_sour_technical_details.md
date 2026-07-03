# HF/ULF Normative Connectome Sweet/Sour Spot Technical Details

Date: 2026-07-01

## Purpose

This document fixes the technical design for symptom-specific HF-only efficacy and HF-adjusted ULF-only add-on target-level seed-target analyses based on the current clinical programming data, public normative structural connectomes, and individualized DWI tractography.

The analysis has two main goals:

1. Identify HF-only target-level connectivity features associated with stable HF therapeutic benefit.
2. Identify ULF-only target-level connectivity features associated with additional benefit after ULF is added to HF stimulation, while adjusting for predicted HF efficacy change.
3. Use voxel and fiber outputs as secondary localization, QC, and visualization products rather than as the primary predictor-selection unit.

The main model assignment is frequency-component based rather than nucleus-assignment based. STN/SNr anatomy is retained for cohort description, stimulation territory, target registry, and visualization overlays.

Frequency definitions are fixed as:

```text
HF  = high-frequency stimulation component, frequency_Hz >= 100
ULF = ultra-low-frequency stimulation component, frequency_Hz <= 50
```

This is an internal technical document, not a manuscript Methods section. It records data sources, modeling definitions, execution steps, expected outputs, and interpretation limits.

## Model Summary Documents

The six model-specific summaries are:

| Research question | Model class | Summary document |
|---|---|---|
| HF-only 3m efficacy | Direct voxel-level | [`hf_3m_direct_voxel_model.md`](model_summaries/hf_3m_direct_voxel_model.md) |
| HF-only 3m efficacy | Normative connectome seed-target / fiber-derived target-level | [`hf_3m_normative_connectome_seed_target_model.md`](model_summaries/hf_3m_normative_connectome_seed_target_model.md) |
| HF-only 3m efficacy | Individualized DWI seed-target / fiber-derived target-level | [`hf_3m_individualized_dwi_seed_target_model.md`](model_summaries/hf_3m_individualized_dwi_seed_target_model.md) |
| HF-adjusted ULF-only add-on gain | Direct voxel-level | [`ulf_addon_gain_direct_voxel_model.md`](model_summaries/ulf_addon_gain_direct_voxel_model.md) |
| HF-adjusted ULF-only add-on gain | Normative connectome seed-target / fiber-derived target-level | [`ulf_addon_gain_normative_connectome_seed_target_model.md`](model_summaries/ulf_addon_gain_normative_connectome_seed_target_model.md) |
| HF-adjusted ULF-only add-on gain | Individualized DWI seed-target / fiber-derived target-level | [`ulf_addon_gain_individualized_dwi_seed_target_model.md`](model_summaries/ulf_addon_gain_individualized_dwi_seed_target_model.md) |

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

Do not use the improvement-rate table as the primary HF or ULF spatial model target unless explicitly running a sensitivity analysis.

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

- Combined STN/SNr ROI and endpoint grouping should use `STNSNr-connected regions` first:

```text
/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/atlases/STNSNr-connected regions
```

- Each connected-region atlas contains side-specific binary masks and `roi_manifest.csv`; use these files directly for model gating, candidate fiber classification, endpoint grouping, coverage summaries, and visualization overlays.
- In `STNSNr-connected regions`, `STNSNr` is the side-specific STN/SNr union and `STNSNrplus` is `STNSNr` with 2 mm dilation.
- `Custom_Ewert_Zhang_Middlebrooks0.05` remains the upstream source for STN/SNr masks inside the connected-region atlases and is retained as a sensitivity or fallback source for standalone STN/SNr masks.
- Non-STN/SNr cortical, thalamic, PPN, and superior colliculus endpoint definitions follow the connected-region atlas manifests and the seed-target atlas registry.

## Exposure Definitions

### Main Stimulation Exposure

The main exposure is full-field peak E-field or E-field-like proxy exposure.

For each subject, side, protocol, and phase, construct stimulation exposure maps for:

```text
HF-only component
HF+ULF HF component
HF+ULF ULF component
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

### Target-Derived Seed Voxel Visualization

The primary voxel-level visualization is a target-derived seed voxel map. It back-projects learned target weights into the seed nucleus using streamline density from each seed voxel to each same-side target.

This is a visualization and overlap-scoring layer for the target-level model, not a separate voxel-wise discovery model.

For each side `h` in `{L,R}`:

```text
Omega_h = same-side seed mask, STN for HF models and SNr for ULF add-on gain models
P_k,h   = same-side target k
G_h,k   = streamlines connecting the seed side to target P_k,h
```

For HF-only efficacy models:

```text
w_k = w_HF,k
S   = S_HF
Omega_h = same-side STN mask
```

For ULF add-on gain models:

```text
w_k = w_ULF,k
S   = S_SNr
Omega_h = same-side SNr mask
```

No left-right flip is performed. Left seed voxels use left targets, right seed voxels use right targets, and both sides share the same target weights `w_k`.

For each voxel `v` in `Omega_h`, compute target-specific streamline density:

```text
D_h,k(v) = sum_{j in G_h,k} a_v,j,h
```

Main contribution:

```text
a_v,j,h = 1 if streamline j passes through voxel v, otherwise 0
```

Display sensitivities:

```text
length-weighted:   a_v,j,h = length(streamline j inside voxel v)
distance-weighted: a_v,j,h = exp(-d(v, streamline j)^2 / (2 * sigma^2))
```

Use binary or length-weighted density as the main display. Distance-weighted density is exploratory only.

Normalize each target density so targets with more streamlines do not dominate only because of tractography density:

```text
Dnorm_h,k(v) = D_h,k(v) / (sum_{u in Omega_h} D_h,k(u) + lambda)
```

Given selected target set `S` and candidate target set `K`, compute:

```text
Coverage_h(v) = sum_{m in K} Dnorm_h,m(v)

Sweet_h(v) =
  sum_{k in S} max(w_k, 0) * Dnorm_h,k(v) / (Coverage_h(v) + lambda)

Sour_h(v) =
  sum_{k in S} max(-w_k, 0) * Dnorm_h,k(v) / (Coverage_h(v) + lambda)

Net_h(v) = Sweet_h(v) - Sour_h(v)
```

The net map is the main target-derived voxel-wise sweet/sour map. It answers whether a seed voxel's target connectivity profile is biased toward beneficial or detrimental targets learned by the target-level model.

For individualized DWI, compute patient-specific maps in native DWI or anchor-native space, transform them to template space, and generate a coverage-weighted group map:

```text
M_ind_group_h(v) =
  sum_i Coverage_ind_i,h(v) * M_ind_i,h(v)
  / (sum_i Coverage_ind_i,h(v) + lambda)
```

Recommended figure hierarchy:

1. Main figure: normative anatomical target-derived seed voxel map, because coverage is smoother and complete.
2. Supplementary or consistency figure: individualized-DWI coverage-weighted group map.
3. Required sidecar: coverage map for every displayed sweet/sour/net map.

Display rules:

```text
net map: diverging color scale centered at zero
positive: warm color, sweet-biased connectivity profile
negative: cool color, sour-biased connectivity profile
low coverage: transparent or gray
left/right: displayed separately without flipping
```

Recommended coverage thresholds:

```text
Coverage_h(v) above the 20th percentile
```

or:

```text
Coverage_h(v) >= 5 streamlines
```

For individualized DWI group maps, require voxel coverage in at least `4` or `5` patients before strong interpretation.

If voxel maps are converted to patient-level overlap scores for prediction, the voxel maps must be generated inside each training fold:

```text
VoxelScore_i =
  sum_h sum_{v in Omega_h} E_i,h(v) * Net_h(v)
  / (sum_h sum_{v in Omega_h} E_i,h(v) * Coverage_h(v) + lambda)
```

LOOCV workflow:

1. Learn `w_k` and selected target set `S` from training patients only.
2. Generate fold-specific `Net_h^{(-t)}(v)`.
3. Compute the held-out patient's voxel overlap score using the fold-specific map.
4. Predict the held-out outcome.

Fold-specific maps should be summarized with:

```text
MeanMap_h(v) = mean_t Net_h^{(-t)}(v)
Stability_h(v) = number of folds with Net_h^{(-t)}(v) > 0 / number of folds
```

Interpretation boundary:

```text
The map is a connectivity-derived candidate sweet/sour seed-zone visualization.
It is not direct voxel-wise causal evidence.
```

### Direct Voxel-Level Sweet Spot Mapping

Direct voxel-level sweet spot mapping is a secondary local stimulation analysis. It directly relates voxel-level E-field exposure to clinical outcome. It is separate from target-derived voxel visualization.

The executable HF direct voxel model is fully specified in:

```text
my_helper/stnsnr/model_summaries/hf_3m_direct_voxel_model.md
```

That model supersedes older generic direct-voxel notes for HF. In particular, the HF model:

- uses a right-hemisphere MNI brainmask candidate grid (`brainmask > 0`, voxel-center `x > 0`);
- uses sparse candidate construction based on any valid subject with `X_HF_only > 180 V/m`;
- uses `Coverage(v) >= 5` only for all generated HF results;
- uses baseline-adjusted partial Spearman as the primary estimator and OLS ANCOVA as a full supplemental estimator;
- uses `ea_flip_lr_nonlinear` for left-to-right E-field mapping;
- does not use `Omega_pair`, paired-mask membership thresholds, or `direct_voxel_<seed>_paired_mask.nii.gz`;
- records, but does not generate, the reference-literature `Coverage>=8` / 50% E-field rule;
- uses LOOCV as the sole validation design for `n = 16`.

#### HF Direct Voxel Model

For each canonical right-hemisphere candidate voxel `v`, the primary map is:

```text
rho_HF(v) =
  corr(
    resid(rank(Y_post_i)       ~ rank(Y_base_i)),
    resid(rank(X_HF_only_i(v)) ~ rank(Y_base_i))
  )
```

Benefit orientation:

```text
M_HF(v) = -rho_HF(v)   for lower-is-better scales
M_HF(v) =  rho_HF(v)   for higher-is-better scales
```

The OLS ANCOVA map is supplemental:

```text
Y_post_i = alpha_v
         + theta_HF(v) * X_HF_only_i(v)
         + beta_v      * Y_base_i
         + error_i,v
```

The patient-level score is:

```text
HFScore_i =
  sum_v X_HF_only_i(v) * M_HF(v)
  / sum_v X_HF_only_i(v)
```

The final prediction model is:

```text
Y_post_i = alpha
         + delta * HFScore_i
         + beta  * Y_base_i
         + error_i
```

Primary validation statistic is LOOCV Spearman rho. Pearson `r`, MAE, RMSE, and `Q2` are secondary metrics.

#### Generic ULF Direct Voxel Context

ULF direct voxel models may still use a model-specific anatomical/candidate mask and covariate structure:

```text
Y_AB_post_i = alpha_v
            + theta_ULF(v) * X_ULF_only_i(v)
            + beta_v       * Y_HF3m_i
            + gamma_v      * DeltaHFScore_i
            + error_i,v
```

The ULF model should explicitly state whether it follows the HF candidate-grid approach or a separate ULF-specific mask. Do not inherit HF settings silently.

#### HF Direct Voxel Outputs

For each scale, tau, and estimator:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale_slug>/tau*/partial_spearman/
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale_slug>/tau*/ols_ancova/
```

export:

```text
direct_voxel_HF_coverage.nii.gz
direct_voxel_HF_coef.nii.gz
direct_voxel_HF_sweet_sour.nii.gz
direct_voxel_HF_stability.nii.gz
direct_voxel_HF_bootstrap_se.nii.gz
direct_voxel_HF_scores.csv
direct_voxel_HF_loocv_predictions.csv
direct_voxel_HF_permutation_summary.csv
direct_voxel_HF_mapping_qc.json
direct_voxel_HF_generation_manifest.json
```

Display smoothing is output only under:

```text
display_smooth_fwhm1mm/
display_smooth_fwhm2mm/
```

and must not be used for HFScore, LOOCV, permutation, or bootstrap.

#### HF QC Sensitivity

Spatial jitter QC is run only for the primary `tau200/partial_spearman` model:

```text
formal jitter resamples: B = 1000
smoke jitter resamples:  B = 100
FWHM = 2 mm
sigma = 0.849 mm
```

Each subject-side E-field receives an independent 3D translation, then the model reruns candidate construction, `Omega_HF_tau`, full-sample map building, HF scores, and LOOCV metrics. Save summary tables and jitter standard deviation maps, not every jittered NIfTI map.

Interpretation boundary:

```text
Direct voxel maps are local stimulation association maps.
They are not target-level network mechanism maps and not definitive causal maps.
```

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
Identify targets where stronger HF-only target connectivity predicts better stable HF-only 3-month outcome.
```

For each clinical scale and each target `k`:

```text
Y_HF3m_i = alpha_0
          + alpha_HF,k * C_HF3m_bilat(i,k)
          + beta         * Y_Preop_i
          + error_i
```

Definitions:

```text
Y_HF3m_i    = raw HF-only 3-month clinical score for subject i
Y_Preop_i    = raw preoperative clinical score for subject i
C_HF3m_bilat(i,k) = bilateral HF target-level connectivity for target k
alpha_HF,k = HF target coefficient of interest
```

Main estimator:

```text
rank-based partial Spearman / residualized regression
```

Benefit-oriented implementation:

```text
STNBenefitScore_k =
  corr(
    residual(rank(C_HF3m_bilat(k)) ~ rank(Y_Preop)),
    benefit_oriented_residual(rank(Y_HF3m) ~ rank(Y_Preop))
  )
```

Interpretation:

```text
STNBenefitScore_k > 0 = stronger HF target connectivity predicts better baseline-adjusted STN 3-month outcome
STNBenefitScore_k < 0 = stronger HF target connectivity predicts worse baseline-adjusted STN 3-month outcome
```

### STN Target Score And STN Seed Voxel Map

The primary HF connectivity predictor is a target-level score, not a top-fiber score.

For each HF target `k`, define:

```text
w_HF,k = benefit-oriented HF target weight
```

For lower-is-better scales:

```text
w_HF,k = -alpha_HF,k
```

For SE-ADL:

```text
w_HF,k = alpha_HF,k
```

Select STN sweet and sour targets inside the training fold:

```text
S_HF = selected HF target set
```

Build the patient-level HF target score:

```text
HFTargetScore_i =
  sum_{k in S_HF} w_HF,k * Z(C_HF3m_bilat(i,k))
  / sum_{k in S_HF} abs(w_HF,k)
```

For HF voxel-level visualization, back-project `w_HF,k` into the HF territory using target-specific streamline density:

```text
Omega_h = same-side STN mask
G_h,k   = streamlines connecting same-side STN to target P_k,h
```

The same target-derived seed voxel formulas are used:

```text
Coverage_h(v)
Sweet_h(v)
Sour_h(v)
Net_h(v)
Stability_h(v)
```

Required STN output files:

```text
STN_lh_coverage.nii.gz
STN_lh_sweet.nii.gz
STN_lh_sour.nii.gz
STN_lh_net.nii.gz
STN_lh_stability.nii.gz

STN_rh_coverage.nii.gz
STN_rh_sweet.nii.gz
STN_rh_sour.nii.gz
STN_rh_net.nii.gz
STN_rh_stability.nii.gz
```

These maps show which STN voxels have connectivity profiles biased toward beneficial or detrimental HF targets. They are target-derived visualization maps and should not be interpreted as direct voxel-wise causal efficacy estimates.

### Secondary STN Immediate Response Model

Run this model only for scales with valid immediate STN assessment.

Default model when only preoperative baseline is available:

```text
Y_STNImmediate_i = alpha_0
                 + alpha_HF_immediate,k * C_STNImmediate_bilat(i,k)
                 + beta                   * Y_Preop_i
                 + error_i
```

If a same-day STN-off baseline exists later, use that baseline instead:

```text
Y_STNImmediate_i = alpha_0
                 + alpha_HF_acute,k * C_STNImmediate_bilat(i,k)
                 + beta               * Y_STNOffSameDay_i
                 + error_i
```

The same-day baseline version can be called an acute STN stimulation response model. The preoperative-baseline version should be called an early HF-only response model.

## ULF Add-On Gain Models

The ULF add-on model family has one primary estimand:

```text
clinical optimization-informed ULF-target gain model
```

It asks whether the final clinician-optimized ULF component target-level connectivity predicts better STN+SNr outcome after controlling the pre-ULF HF-only 3-month clinical state and the concurrent HF component efficacy-map score change.

The model has two endpoints:

```text
chronic ULF add-on gain endpoint: STN+SNr 3m relative to HF-only 3m
immediate ULF add-on gain endpoint: STN+SNr immediate relative to HF-only 3m
```

### DeltaHFScore Construction

`DeltaHFScore` is the nuisance covariate used to control HF component reprogramming in ULF add-on gain models. The preferred definition is an endpoint/domain-matched change in predicted HF efficacy-model alignment, not a raw contact, amplitude, pulse-width, or frequency-change summary.

The HF adjustment must be model-family matched:

```text
ULF direct voxel-level model
  -> HF direct voxel-level efficacy model

ULF normative connectome seed-target model
  -> HF normative connectome seed-target efficacy model

ULF individualized DWI seed-target model
  -> HF individualized DWI seed-target efficacy model
```

Do not use cross-family HF adjustment as the primary `DeltaHFScore`.

For the direct voxel-level family, train an HF-only efficacy map using only pre-ULF HF-only data:

```text
Y_HF3m_i = alpha_u
          + theta_HF(u) * X_HF_only_i(u)
          + beta_u       * Y_Preop_i
          + error_i,u
```

Orient the map so positive values mean better STN response:

```text
M_HF(u) = -theta_HF(u)   for lower-is-better scales
M_HF(u) =  theta_HF(u)   for SE-ADL
```

Then score any STN stimulation component `E` by its exposure-weighted alignment with the learned direct voxel-level HF efficacy map:

```text
S_HF_voxel(E) =
  sum_{u in Omega_HF} E(u) * M_HF(u)
  / (sum_{u in Omega_HF} E(u) + lambda)
```

For normative seed-target models, use the model-matched HF target-level score:

```text
S_HF_norm(E) =
  sum_{k in S_HF_norm} w_HF,k_norm * Z_train(C_norm_HF_component(E,k))
  / sum_{k in S_HF_norm} abs(w_HF,k_norm)
```

For individualized DWI seed-target models, use the model-matched HF target-level score:

```text
S_HF_ind(E) =
  sum_{k in S_HF_ind} w_HF,k_ind * Z_train(C_ind_HF_component(E,k))
  / sum_{k in S_HF_ind} abs(w_HF,k_ind)
```

For ULF add-on gain models, use the matching score family:

```text
DeltaHFScore_family,i =
  S_HF_family(E_HF_component_i,combined)
  - S_HF_family(E_HF_component_i,HF-only3m)
```

Interpretation:

```text
DeltaHFScore_i > 0: combined-phase HF component is more aligned with the learned model-matched HF efficacy model
DeltaHFScore_i < 0: combined-phase HF component is less aligned with the learned model-matched HF efficacy model
```

This definition is acceptable because the HF efficacy model is trained on HF-only 3-month outcomes before ULF is added; it is not trained on STN+SNr outcomes.

Endpoint/domain matching and model-family matching are required. For chronic ULF 3-month models, use the HF-only 3-month model for the matching scale or symptom domain. For immediate ULF motor models, use a motor-domain HF model, preferably trained from HF-only 3-month motor outcome. Do not use a total-score HF model as the main `DeltaHFScore` for a motor-only immediate endpoint.

For strict ULF LOOCV prediction, train the model-matched HF efficacy model inside each outer training fold and use that fold-specific model to compute `DeltaHFScore` for both training and held-out patients. For final descriptive visualization, a full-sample HF-only model can be used and should be reported as a same-cohort, pre-ULF-derived nuisance adjustment rather than an external independent model.

Run the following diagnostics:

```text
cor(DeltaHFScore, Y_HF3m)
cor(DeltaHFScore, ULF exposure features)
```

Also run a physical HF-change sensitivity covariate that is not outcome-derived, such as charge-rate change, raw HF e-field energy change, HF VTA overlap change, or HF field centroid distance. This sensitivity can be named `DeltaHFPhys`.

### Chronic ULF Add-On Gain Model

Purpose:

```text
Estimate the long-term target-level distribution of ULF-associated gain after adding ULF to HF stimulation.
```

Model:

```text
Y_AB3m_i = alpha_0
         + theta_ULF_chronic,k * C_ULF_only_3m_bilat(i,k)
         + beta                 * Y_HF3m_i
         + gamma                * DeltaHFScore_3m_i
         + error_i
```

Definitions:

```text
Y_AB3m_i            = raw STN+SNr 3-month clinical score for subject i
Y_HF3m_i           = raw HF-only 3-month clinical score for subject i
C_ULF_only_3m_bilat(i,k)  = STN+SNr 3-month ULF-component bilateral connectivity to target k
DeltaHFScore_3m_i  = endpoint/domain-matched and model-family-matched change in HF efficacy-model score from HF-only 3m to the HF component of STN+SNr 3m
theta_ULF_chronic,k = chronic ULF add-on gain target coefficient of interest
```

Interpretation:

```text
Among subjects with comparable HF-only 3-month clinical state and comparable HF component change,
does final ULF 3-month connectivity to target k predict better STN+SNr 3-month outcome?
```

### Immediate ULF Add-On Gain Model

Purpose:

```text
Estimate the immediate target-level distribution of ULF-associated gain after adding ULF to HF stimulation.
```

Model:

```text
Y_ABimmediate_i = alpha_0
                + theta_ULF_immediate,k * C_ULF_only_immediate_bilat(i,k)
                + beta                   * Y_HF3m_i
                + gamma                  * DeltaHFScore_immediate_i
                + error_i
```

Definitions:

```text
Y_ABimmediate_i              = raw STN+SNr immediate clinical score for subject i
Y_HF3m_i                    = raw HF-only 3-month clinical score for subject i
C_ULF_only_immediate_bilat(i,k)    = STN+SNr immediate ULF-component bilateral connectivity to target k
DeltaHFScore_immediate_i    = motor-domain and model-family-matched change in HF efficacy-model score from HF-only 3m to the HF component of STN+SNr immediate
theta_ULF_immediate,k        = immediate ULF add-on gain target coefficient of interest
```

Interpretation:

```text
Among subjects with comparable HF-only 3-month clinical state and comparable immediate-phase HF component change,
does final ULF immediate connectivity to target k predict better STN+SNr immediate outcome?
```

The `Y_HF3m` covariate controls the pre-ULF disease state. `DeltaHFScore_immediate` controls concurrent HF component reprogramming in the immediate HF+ULF setting using a motor-domain and model-family-matched HF efficacy model. If a same-day pre-ULF HF-only score becomes available, add a sensitivity model using that same-day baseline to control short-term disease fluctuation more directly.

### SNr Rank-Based Implementation

For `n = 16`, use rank-based partial Spearman or equivalent residualized regression as the main implementation.

For each endpoint and each target `k`:

1. Rank-transform `Y_AB`, `C_ULF_only_bilat(k)`, `Y_HF3m`, and `DeltaHFScore`.
2. Regress ranked `Y_AB` on ranked `Y_HF3m` and ranked `DeltaHFScore`; keep residuals.
3. Regress ranked `C_ULF_only_bilat(k)` on ranked `Y_HF3m` and ranked `DeltaHFScore`; keep residuals.
4. Correlate the two residual vectors.
5. Orient the resulting score so positive values mean better clinical outcome.

For lower-is-better scales:

```text
H_ULF,k = -theta_ULF,k
```

For SE-ADL:

```text
H_ULF,k = theta_ULF,k
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

For target-derived seed voxel visualization, export side-specific NIfTI files:

```text
<seed>_lh_coverage.nii.gz
<seed>_lh_sweet.nii.gz
<seed>_lh_sour.nii.gz
<seed>_lh_net.nii.gz
<seed>_lh_stability.nii.gz

<seed>_rh_coverage.nii.gz
<seed>_rh_sweet.nii.gz
<seed>_rh_sour.nii.gz
<seed>_rh_net.nii.gz
<seed>_rh_stability.nii.gz
```

where `<seed>` is `STN` for HF models and `SNr` for ULF add-on gain models.

Thus the required target-derived voxel outputs include both HF efficacy maps and ULF add-on gain maps when the corresponding model is run:

```text
STN_lh_net.nii.gz
STN_rh_net.nii.gz
SNr_lh_net.nii.gz
SNr_rh_net.nii.gz
```

Also export:

```text
target_density_by_seed_voxel.mat
target_density_manifest.csv
voxel_map_display_thresholds.json
voxel_overlap_scores.csv
loocv_fold_voxel_scores.csv
```

Voxel maps are secondary localization outputs. They should be interpreted with connected-region STN/SNr outlines and target-atlas overlays, but the primary target-level model itself is not cropped to those ROIs.

For direct voxel-level sweet spot models, export:

```text
direct_voxel_<seed>_coverage.nii.gz
direct_voxel_<seed>_coef.nii.gz
direct_voxel_<seed>_sweet_sour.nii.gz
direct_voxel_<seed>_stability.nii.gz
direct_voxel_<seed>_bootstrap_se.nii.gz
direct_voxel_<seed>_paired_mask.nii.gz
direct_voxel_<seed>_sweetspot_scores.csv
direct_voxel_<seed>_loocv_predictions.csv
direct_voxel_<seed>_permutation_summary.csv
direct_voxel_<seed>_homologous_mapping_qc.json
```

This generic output list does not apply to the executable HF direct voxel model. HF uses the `direct_voxel_HF_*` output family under `<scale_slug>/tau*/partial_spearman|ols_ancova/`, does not export `paired_mask`, and uses `direct_voxel_HF_scores.csv` rather than `sweetspot_scores.csv`.

## Execution Plan

### Stage 1: Input Validation

1. Confirm that `followup_stimulation.xlsx` exists and contains `Contact Parameters`.
2. Confirm required programming columns are present.
3. Confirm that subject IDs match between programming data and clinical score tables.
4. Confirm that raw score conditions include `Pre-op`, `STN (3 m)`, `STN+SNr (immediate)`, and `STN+SNr (3 m)`.
5. Confirm that the three normative connectome `data.mat` files are present.
6. Confirm atlas registry paths exist.

### Stage 2: Exposure Map Construction

1. Parse HF-only, STN+SNr HF-component, and STN+SNr ULF-component programming rows.
2. Split interleaving rows by `AlternatingGroup`.
3. Generate component exposure maps for each subject, side, phase, protocol, and target.
4. Generate interleaving union and overlap maps.
5. Save provenance for voltage, pulse width, frequency, contacts, target, side, phase, and protocol.

### Stage 3: Clinical Endpoint Assembly

1. Build scale-specific raw score tables.
2. Select STN chronic endpoints using `Pre-op` and `STN (3 m)`.
3. Select ULF chronic add-on gain endpoints using `STN (3 m)` and `STN+SNr (3 m)`.
4. Select ULF immediate add-on gain endpoints using `STN (3 m)` and `STN+SNr (immediate)`.
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
5. Compute target-derived seed voxel density, normalized density, coverage, sweet, sour, net, and stability maps for HF efficacy models and ULF add-on gain models.
6. Compute direct voxel-level STN and SNr sweet spot models using bilateral homologous voxel exposure, nested LOOCV, and patient-level permutation.
7. Save coverage and exposure prevalence maps.

### Stage 6: Model Fitting

Fit each model separately by scale:

```text
STN chronic model
STN immediate model when valid
ULF chronic add-on gain model
ULF immediate add-on gain model
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
target-derived seed voxel NIfTI maps
voxel overlap score tables
direct voxel sweet spot maps
direct voxel LOOCV prediction tables
direct voxel permutation summaries
homologous voxel mapping QC
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
voxel_maps/target_derived/stn/
voxel_maps/target_derived/snr/
voxel_maps/loocv/stn/
voxel_maps/loocv/snr/
voxel_maps/dwi_group/stn/
voxel_maps/dwi_group/snr/
direct_voxel/stn/
direct_voxel/snr/
direct_voxel/qc/
exposure/
exposure/interleaving/
models/hf/chronic/
models/stn/immediate/
models/snr/chronic_gain/
models/snr/immediate_gain/
models/cross_scale/
sensitivity/
visualization/
```

## Limitations And Interpretation Boundaries

### Observational Spatial Association

The ULF add-on gain target maps and target scores are between-subject spatial association models. They are not within-patient randomized location-response maps.

The observed final ULF setting is:

```text
C_i* = final ULF setting selected for subject i after clinical programming
```

The observed outcome is:

```text
Y_i(C_i*)
```

The data do not contain:

```text
Y_i(s) for every possible ULF location s
```

Therefore, the target maps and secondary localization outputs should not be described as pure causal efficacy maps showing that every patient should be stimulated at a specific ULF location.

### Residual Confounding

`Y_HF3m` controls the pre-ULF total clinical state. It may not fully control:

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

`DeltaHFScore` controls the endpoint/domain-matched and model-family-matched change in predicted HF efficacy-model alignment caused by HF component reprogramming. Unless an external model-matched HF efficacy model is used, it should be described as a same-cohort, pre-ULF-derived nuisance adjustment. It may still be noisy or incomplete because it may not fully capture changes in:

```text
contact location
amplitude
pulse width
frequency
field shape
fiber recruitment
STN-SNr interaction
```

Check collinearity between `DeltaHFScore`, `Y_HF3m`, and ULF exposure features. Also run `DeltaHFPhys` as an outcome-independent sensitivity covariate.

### Coverage And Sample Size

The cohort currently has `n = 16`. High-dimensional interaction models should not be used for primary inference.

Low-coverage targets, voxels, or streamlines can produce unstable coefficients. Every model must export target coverage summaries and, for secondary maps, coverage maps.

Direct voxel-level sweet spot maps are especially sensitive to small sample size, coverage imbalance, and homologous voxel mapping quality. They should be interpreted as local stimulation association maps and should not replace the target-level seed-target model for primary network interpretation.

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
target-derived voxel maps are generated by target-weight back-projection, not by top voxel-wise correlation
HF target-derived voxel maps are generated from HF target weights and HF seed/territory masks
ULF target-derived voxel maps are generated from ULF target weights and SNr seed masks
left and right target-derived voxel maps are generated separately without flipping
coverage, sweet, sour, net, and stability maps are exported for every reported seed voxel visualization
low-coverage seed voxels are transparent or gray in visualization
voxel overlap scores used for prediction are generated from training-fold maps only
direct voxel-level sweet spot mapping is secondary/exploratory and does not replace target-level primary inference
direct voxel models use bilateral homologous voxel exposure and keep one row per patient
nonlinear homologous voxel mapping uses model-specific transform rules; the executable HF model uses `ea_flip_lr_nonlinear`, while inverse-sampling/trilinear descriptions are generic non-HF context only
direct voxel coverage masks are defined inside each training fold during LOOCV
direct voxel models are compared against covariate-only models with patient-level permutation tests
PPMI smoke test completes before MGH or dTOR
STN chronic, ULF chronic add-on gain, and ULF immediate add-on gain outputs are created
low-coverage targets, voxels, and streamlines are flagged
all outputs include provenance
```
