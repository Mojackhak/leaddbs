# HF/ULF Normative Connectome Sweet/Sour Spot Technical Details

Date: 2026-07-01

## Purpose

This document fixes the technical design for symptom-specific HF-only efficacy and HF-status-resolved ULF-only add-on analyses based on the current clinical programming data, public normative structural connectomes, and individualized DWI tractography.

The analysis has two main goals:

1. Identify HF-only normative connectome fiber-level profiles associated with stable HF therapeutic benefit.
2. Identify ULF-only normative connectome fiber-level profiles associated with additional benefit after ULF is added to HF stimulation, while running both DeltaHF-adjusted and no-DeltaHF core branches and assigning the interpretive primary branch from the locked HF result.
3. Use voxel and target-label outputs as localization, QC, and visualization products without overriding each model-specific primary unit.

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
| HF-only 3m efficacy | Normative connectome DBS Fiber Filtering / fiber-level | [`hf_3m_normative_connectome_fiber_model.md`](model_summaries/hf_3m_normative_connectome_fiber_model.md) |
| HF-only 3m efficacy | Individualized DWI seed-target / fiber-derived target-level | [`hf_3m_individualized_dwi_seed_target_model.md`](model_summaries/hf_3m_individualized_dwi_seed_target_model.md) |
| HF-status-resolved ULF-only add-on gain | Direct voxel-level | [`ulf_addon_gain_direct_voxel_model.md`](model_summaries/ulf_addon_gain_direct_voxel_model.md) |
| HF-status-resolved ULF-only add-on gain | Normative connectome DBS Fiber Filtering / fiber-level | [`ulf_addon_gain_normative_connectome_fiber_model.md`](model_summaries/ulf_addon_gain_normative_connectome_fiber_model.md) |
| HF-status-resolved ULF-only add-on gain | Individualized DWI seed-target / fiber-derived target-level | [`ulf_addon_gain_individualized_dwi_seed_target_model.md`](model_summaries/ulf_addon_gain_individualized_dwi_seed_target_model.md) |

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

Use the raw clinical score workbook for the current raw-score spatial models:

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

- Each connected-region atlas contains side-specific binary masks and `roi_manifest.csv`; use these files for endpoint grouping, anatomical enrichment, coverage summaries, and visualization overlays. Do not use them to define the primary direct-voxel candidate grid or the primary normative full-connectome fiber candidate universe.
- In `STNSNr-connected regions`, `STNSNr` is the side-specific STN/SNr union and `STNSNrplus` is `STNSNr` with 2 mm dilation.
- `Custom_Ewert_Zhang_Middlebrooks0.05` remains the upstream source for STN/SNr masks inside the connected-region atlases and is retained as a sensitivity or fallback source for standalone STN/SNr masks.
- Non-STN/SNr cortical, thalamic, PPN, and superior colliculus endpoint definitions follow the connected-region atlas manifests and the seed-target atlas registry.

## Exposure Definitions

### Main Stimulation Exposure

The executable non-individualized models use accepted raw Lead-DBS `sim-efield`
maps in `V/m` as the primary exposure source.

For each subject, side, protocol, and phase, construct stimulation exposure maps for:

```text
HF-only component
HF+ULF HF component
HF+ULF ULF component
```

Missing or multiply matched required e-field inputs fail the relevant executable
run unless a model document explicitly defines a separate proxy-only smoke
branch. Gaussian contact-centered proxy exposure and random-parameter exposure
are retained only for legacy development, smoke testing, or explicitly labeled
proxy branches.

Pulse width and frequency must still be stored in provenance. They may be used
in sensitivity analyses, such as charge-rate proxy:

```text
abs(voltage_V) * pulse_width_us * frequency_Hz
```

### VTA Boundary Rule

Do not crop VTA, e-field, or proxy maps to STN/SNr boundaries. VTA may extend beyond the nucleus edge, and this extension is part of the modeled stimulation exposure.

Connected-region atlas masks are used for:

```text
endpoint grouping
voxel-map anatomical overlays
coverage summaries
fiber label enrichment
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

For the current executable direct voxel and normative fiber models, same-component alternating subprograms are combined by pointwise maximum:

```text
E_component = max(E_A, E_B, ...)
X_component = max exposure sampled from E_component
```

Descriptive interleaving output:

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

Use frequency-weighted exposure only when timing, pulse-count, or duty-cycle information is reliable. Otherwise, report union and overlap without inventing timing weights. Union and overlap are descriptive or sensitivity outputs unless a model-specific document explicitly promotes them to a main predictor.

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

This section applies to individualized DWI seed-target models and target-derived visualization outputs. It no longer defines the primary HF or ULF normative connectome models, which are specified as fiber-level DBS Fiber Filtering models in `model_summaries/hf_3m_normative_connectome_fiber_model.md` and `model_summaries/ulf_addon_gain_normative_connectome_fiber_model.md`.

For target-level model families, the primary connectivity model uses target-level features rather than top single-fiber predictors.

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

Voxel-wise models use subject-level stimulation exposure at each voxel. The current executable HF and ULF direct voxel models define their candidate masks and coverage rules in their model-specific documents.

Legacy generic voxel analysis mask:

```text
cohort stimulation union mask
```

The mask should include voxels exposed in at least a prespecified minimum number of subjects. Low-coverage voxels must be reported and should not receive strong anatomical interpretation.

### Target-Derived Seed Voxel Visualization

For target-level individualized DWI models and explicitly labeled target-level
sensitivities, the voxel-level visualization is a target-derived seed voxel map.
It back-projects learned target weights into the seed nucleus using streamline
density from each seed voxel to each same-side target.

This is a visualization and overlap-scoring layer for the target-level model, not a separate voxel-wise discovery model. It is distinct from the executable HF and ULF direct voxel models, which are specified in their model summary files.

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
- uses `Coverage(v) >= 5` for the primary HF mainline;
- documents `Coverage>=6` and `Coverage>=8` as optional sensitivities for the primary mainline; the A-model tau/Coverage source resolver scan evaluates the pre-specified source first and uses fallback cells only when the pre-specified source is not accepted;
- uses baseline-adjusted partial Spearman as the primary estimator and keeps OLS ANCOVA as optional future supplemental analysis not run in the current executable analysis;
- uses voxel-count-normalized `HFScore_mean_main = sum_v X_HF_only(v) * M_HF(v) / n_valid_score_voxels` as the primary patient-level score;
- uses `ea_flip_lr_nonlinear` for left-to-right E-field mapping;
- records a left/right flip deformation audit as warning-only QC;
- does not use `Omega_pair`, paired-mask membership thresholds, or `direct_voxel_<seed>_paired_mask.nii.gz`;
- treats existing e-fields as correct inputs after prior manual/clinical QC and performs only minimum availability/uniqueness checks;
- restricts formal permutation/bootstrap to `tau200/partial_spearman`;
- records, but does not use as a primary rule, the reference-literature `Coverage>=8` / 50% E-field rule;
- uses LOOCV as the sole validation design for `n = 16`;
- adds report-only top 10% + direction-stability display masks that are not significance maps.

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
V_score = Omega_HF_tau intersect valid M_HF voxels
n_valid_score_voxels = |V_score|

HFScore_mean_main_i =
  sum_{v in V_score} X_HF_only_i(v) * M_HF(v)
  / n_valid_score_voxels
```

`HFScore_mean_main_i` is the primary score. It is divided by the number of valid scoring voxels so full-sample and fold-specific scores remain comparable when `Omega_HF_tau` sizes differ. It is not divided by `sum(X)`. Empty `V_score` is a branch/fold QC failure; no score should be emitted. The unnormalized `HFScore_sum_descriptive_i = sum_v X_i(v) * M(v)` is retained only as a documented concept; it is not computed or written by the current executable analysis and does not enter prediction, LOOCV, permutation, or bootstrap.

The final prediction model is:

```text
Y_post_i = alpha
         + delta * HFScore_mean_main_i
         + beta  * Y_base_i
         + error_i
```

Primary validation statistic is LOOCV Spearman rho. Pearson `r`, MAE, RMSE, and `Q2` are secondary metrics.

#### Generic ULF Direct Voxel Context

The current executable ULF direct voxel model is fully specified in:

```text
model_summaries/ulf_addon_gain_direct_voxel_model.md
```

It follows the HF direct voxel infrastructure where applicable, but it has its own ULF-only exposure definition, HF-overlap exclusion, and `DeltaHFScore` support QC:

```text
Y_post_i = alpha
         + delta * ULFScore_mean_main_i
         + beta  * Y_HF_ref_i
         + gamma * DeltaHFScore_i
         + error_i
```

Key differences from HF direct voxel:

- `Y_HF_ref` is the raw HF-only 3-month clinical state at T2 before ULF addition.
- Chronic `Y_post` is the raw HF+ULF 3-month score at T3.
- Immediate `Y_post` is the same-day raw HF+ULF immediate score at T2 after ULF addition.
- `X_ULF_only(v,phase,tau)` is tau-specific and excludes voxels co-activated by HF and ULF at the same tau.
- `DeltaHFScore` comes from the locked HF direct voxel model, not from the normative fiber model.
- The primary score is `ULFScore_mean_main`.
- OLS ANCOVA is optional future supplemental analysis and is not run in the current executable analysis.

ULF output root:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/<tau_slug>/partial_spearman/
```

#### HF Direct Voxel Outputs

For each scale, tau, and estimator:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale_slug>/tau*/partial_spearman/
optional future OLS outputs would use sibling `ols_ancova/` directories only if explicitly enabled
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

`direct_voxel_HF_bootstrap_se.nii.gz` and `direct_voxel_HF_permutation_summary.csv` are generated only for `tau200/partial_spearman`. Non-primary branches record `resampling_status = not_run_nonprimary` in the manifest/QC JSON instead of writing placeholder resampling files.

`direct_voxel_HF_scores.csv` must identify `HFScore_mean_main` as the primary score. `HFScore_sum_descriptive` is documented only and is not a required output field. Report-only sweet/sour display masks use the top 10% same-sign `M_HF` voxels plus direction-specific stability `>=0.75`; they are not significance maps.

For exported continuous/statistical NIfTI maps, non-covered or non-modeled voxels must be written as `NaN`, not `0`. This applies to coefficient, sweet/sour, stability, bootstrap SE, density, weighted-density, and display-smoothed statistical maps. Integer coverage/count maps and binary masks are the exception and may use `0` outside support because their semantics are count/false. This rule prevents non-covered regions from being interpreted as neutral true-zero model effects.

Display smoothing is output only under:

```text
display_smooth_fwhm1mm/
display_smooth_fwhm2mm/
```

and must not be used for HFScore, LOOCV, permutation, or bootstrap.

#### HF QC Sensitivity

Left/right flip deformation audit is warning-only QC. It records grid/affine, finite and nonzero voxel counts, max/p95/p99/sum, suprathreshold volumes at 180/200/220 V/m, intensity-weighted centroid, right-brainmask overlap, and optional roundtrip metrics. Empty maps, all-NaN maps, non-finite maps, or path mismatches are data-integrity failures, but ordinary deformation/interpolation differences do not automatically exclude subjects.

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
For n=16, HF direct voxel results are hypothesis-generating even when LOOCV is positive.
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

## HF Normative Fiber-Level Model

### Primary Chronic HF-Only Efficacy Model

Purpose:

```text
Identify normative connectome streamlines where stronger HF-only modulation predicts better stable HF-only 3-month outcome.
```

For each clinical scale and each candidate fiber `l`:

```text
rho_HF(l) =
  corr(
    resid(rank(Y_HF3m_i) ~ rank(Y_Preop_i)),
    resid(rank(X_HF_i(l)) ~ rank(Y_Preop_i))
  )
```

Definitions:

```text
Y_HF3m_i = raw HF-only 3-month clinical score for subject i
Y_Preop_i = raw preoperative clinical score for subject i
E_R_i(l) = right-side peak raw sim-efield sampled along right canonical normative fiber l
E_L_to_R_i(l) = left-side peak raw sim-efield after ea_flip_lr_nonlinear, sampled along the same right canonical normative fiber l
X_HF_i(l) = (E_R_i(l) + E_L_to_R_i(l)) / 2
rho_HF(l) = baseline-adjusted fiber-wise association
```

Candidate fibers:

```text
candidate universe = full public connectome, not target-restricted
canonical side = right
tau_primary = 800 V/m
coverage_primary = Coverage>=5
tau_sensitivity = 1500 V/m
coverage_sensitivity = Coverage>=5
threshold_scan_tau_grid_v_per_m = [400, 600, 800, 1000, 1200, 1500, 2000]
threshold_scan_coverage_grid = [5, 6, 7, 8, 10, 12]
Coverage_tau(l) = sum_i I[X_HF_i(l) > tau]
F_candidate_tau = {l: Coverage_tau(l) >= coverage_min}
```

The executable model uses a right-canonical streamline feature space and the same patient-level coverage rule as the HF direct voxel model. Left-sided stimulation is flipped into the right canonical space and sampled along the same right-sided streamline features. Bilateral E-field information is averaged into `X_HF_i(l)`, but the feature set itself remains one-sided/canonical.

The pre-specified HF normative fiber source is `peak_efield_tau800_cov5_primary`. The predeclared high-threshold sensitivity is `peak_efield_tau1500_cov5_sensitivity`. The full tau x Coverage grid is the HF normative fiber source resolver scan; it is used only when tau800/Coverage>=5 is not accepted, and may define a `scan_fallback_accepted` HF source with recorded selected tau/Coverage and adjacent support.

Benefit-oriented implementation:

```text
M_HF(l) = -rho_HF(l)   for lower-is-better scales
M_HF(l) =  rho_HF(l)   for higher-is-better scales
```

Interpretation:

```text
M_HF(l) > 0 = stronger HF modulation of this fiber predicts better baseline-adjusted HF-only 3-month outcome
M_HF(l) < 0 = stronger HF modulation of this fiber predicts worse baseline-adjusted HF-only 3-month outcome
```

FDR q-values are computed for QC/display only and are not used to filter the primary model.

### HF Fiber Score And Fiber Display

The primary HF normative connectome predictor is a net sweet-minus-sour peak score:

```text
F+ = top 1% fibers with largest positive M_HF(l)
F- = top 0.5% fibers with most negative M_HF(l)

SweetWeighted_i(l) = X_HF_i(l) * M_HF(l),      l in F+
SourWeighted_i(l)  = X_HF_i(l) * [-M_HF(l)],   l in F-

SweetPeak5_i = mean of top 5% largest SweetWeighted_i(l)
SourPeak5_i  = mean of top 5% largest SourWeighted_i(l)

NetFiberScore_i = SweetPeak5_i - SourPeak5_i
```

If `F+` is empty, `SweetPeak5=0`. If `F-` is empty, `SourPeak5=0`. If a selected set is non-empty but patient exposure to all selected fibers is zero, the corresponding peak score is `0`.

Final prediction model:

```text
Y_HF3m_i = alpha
         + delta * NetFiberScore_i
         + beta  * Y_Preop_i
         + error_i
```

Display outputs:

```text
top 1% positive fibers for sweet streamline display
top 0.5% sour fibers for avoidance/sour display
streamline density maps for selected/display fibers
unthresholded weighted-density maps
-log(P) statistical-certainty density maps
FDR q-value summaries and q-thresholded density maps for QC/display
endpoint/cortical/subcortical label summaries for QC and anatomical interpretation
plain connected-streamline control summaries
```

Reference sensitivity coverage:

```text
peak_efield_tau1500_cov5_sensitivity
top1500 positive / top500 negative fiber-score sensitivity
OSS-DBS all-candidate sensitivity
tau_coverage_source_resolver_scan
plain_connected_streamline_control
jitter_level_1_selected_display
jitter_level_2_model_density
5-fold and 10-fold CV documented only; LOOCV remains executable validation
```

The model-specific source of truth is:

```text
model_summaries/hf_3m_normative_connectome_fiber_model.md
```

### Historical / Future HF Immediate Response Sketch

This section is retained only as a future or historical sketch. It is not part of the current non-individualized executable model-summary files. Do not run or report it as a current primary or secondary analysis unless a dedicated model summary is created and reconciled with the HF/ULF documentation set.

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

The ULF add-on model family has one primary estimand, but the primary branch is resolved from the matched HF result rather than hard-coded:

```text
clinical optimization-informed HF-status-resolved ULF-only add-on model
```

It asks whether the final clinician-optimized ULF component predicts better HF+ULF outcome after controlling the pre-ULF HF clinical state, with or without the concurrent HF component efficacy-map score change depending on the matched HF source and prediction status.

Engineering rule:

```text
Always run the two core ULF branches when inputs are available:
  delta_hf_adjusted: Y_post ~ ULFPredictor + Y_HF_ref + DeltaHFScore
  no_delta_hf:       Y_post ~ ULFPredictor + Y_HF_ref

Then assign the interpretive primary branch from the locked HF result:
  direct voxel error_predictive HF source     -> delta_hf_adjusted is primary
  direct voxel error_nonpredictive HF source  -> no_delta_hf is primary
  direct voxel absent_no_stable_grid          -> no_delta_hf only
  normative fiber source exists + error_predictive -> delta_hf_adjusted is primary
  normative fiber source exists + error_nonpredictive -> no_delta_hf is primary
  normative fiber absent_no_stable_grid -> no_delta_hf only
```

The manifest must record direct-voxel HF resolver fields (`hf_voxel_source_status`, `hf_voxel_prediction_status`, `hf_voxel_threshold_source`, selected tau/coverage, and adjacent support) when the matched HF dependency is direct voxel. ULF direct voxel manifests must also record the ULF branch's own resolver fields: `ulf_voxel_source_status`, `ulf_voxel_prediction_status`, `ulf_endpoint_model_status`, `ulf_branch_input_status`, `branch_nuisance_design_status`, selected ULF tau/coverage, and adjacent support. For normative fiber dependencies, the manifest must record `hf_norm_fiber_source_status`, `hf_norm_fiber_prediction_status`, `hf_norm_fiber_threshold_source`, selected tau/coverage fields, adjacent support, and source failure reasons. ULF normative fiber manifests must also record `ulf_norm_fiber_source_status`, `ulf_norm_fiber_prediction_status`, `ulf_norm_fiber_endpoint_model_status`, branch-specific input readiness, selected ULF tau/coverage, and adjacent support. All ULF manifests must record `intended_primary_branch`, `ulf_primary_branch`, `delta_hfscore_role`, and `branch_role_decision_reason`.

The model has two endpoints:

```text
chronic ULF add-on endpoint:
  Y_post = raw HF+ULF 3-month score at T3
  Y_HF_ref = raw HF-only 3-month score at T2

same-day immediate ULF add-on endpoint:
  Y_post = raw HF+ULF immediate score at T2 after ULF addition
  Y_HF_ref = raw HF-only 3-month score at T2 before ULF addition
```

### DeltaHFScore Construction

`DeltaHFScore` is the candidate nuisance covariate used to control HF component reprogramming in the DeltaHF-adjusted ULF add-on branch. The preferred definition is an endpoint/domain-matched change in predicted HF efficacy-model alignment, not a raw contact, amplitude, pulse-width, or frequency-change summary.

The HF adjustment must be model-family matched:

```text
ULF direct voxel-level model
  -> HF direct voxel-level efficacy model

ULF normative connectome fiber-level model
  -> HF normative connectome fiber-level efficacy model

ULF individualized DWI seed-target model
  -> HF individualized DWI seed-target efficacy model
```

Do not use cross-family HF adjustment as the `DeltaHFScore` for the DeltaHF-adjusted branch.

For the direct voxel-level family, train an HF-only efficacy map using only pre-ULF HF-only data. The formula below is schematic; the current executable HF direct voxel model uses baseline-adjusted partial Spearman and `HFScore_mean_main`, with OLS ANCOVA documented only as optional future supplemental analysis:

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

Then score any HF stimulation component `E` by its exposure-weighted alignment with the learned direct voxel-level HF efficacy map:

```text
S_HF_voxel(E) =
  sum_{u in V_HF_score} E(u) * M_HF(u)
  / n_valid_HF_score_voxels
```

For normative connectome models, use the model-matched HF fiber-level score:

```text
S_HF_norm_fiber(E) = NetFiberScore(E)
```

For ULF normative fiber models, `DeltaHFScore` is interpreted as the primary HF adjustment only when the matched HF normative fiber source exists (`pre_specified_accepted` or `scan_fallback_accepted`) and `hf_norm_fiber_prediction_status = error_predictive`. If the HF normative fiber source exists but is `error_nonpredictive`, `DeltaHFScore` may be computed only as a sensitivity covariate. If `hf_norm_fiber_source_status = absent_no_stable_grid`, the DeltaHF-adjusted ULF branch is not run.

For individualized DWI seed-target models, use the model-matched HF target-level score:

```text
S_HF_ind(E) =
  sum_{k in S_HF_ind} w_HF,k_ind * Z_train(C_ind_HF_component(E,k))
  / sum_{k in S_HF_ind} abs(w_HF,k_ind)
```

For the DeltaHF-adjusted ULF add-on branch, use the matching score family:

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

For strict ULF LOOCV prediction in the DeltaHF-adjusted branch, train the model-matched HF efficacy model inside each outer training fold and use that fold-specific model to compute `DeltaHFScore` for both training and held-out patients. The no-DeltaHF branch omits `DeltaHFScore` from map fitting, scoring, prediction, permutation nuisance models, and baseline comparison. For final descriptive visualization, a full-sample HF-only model can be used and should be reported as a same-cohort, pre-ULF-derived nuisance adjustment rather than an external independent model.

Run the following diagnostics:

```text
cor(DeltaHFScore, Y_HF_ref)
cor(DeltaHFScore, ULF exposure features)
```

Also run a physical HF-change sensitivity covariate that is not outcome-derived, such as charge-rate change, raw HF e-field energy change, HF VTA overlap change, or HF field centroid distance. This sensitivity can be named `DeltaHFPhys`.

### ULF Direct Voxel Add-On Model

The direct voxel model is specified in `model_summaries/ulf_addon_gain_direct_voxel_model.md`. It runs both core branches when inputs are available. The DeltaHF-adjusted branch uses:

```text
rho_ULF(v) =
  corr(
    resid(rank(Y_post_i)                   ~ rank(Y_HF_ref_i) + rank(DeltaHFScore_i)),
    resid(rank(X_ULF_only_i(v, phase,tau)) ~ rank(Y_HF_ref_i) + rank(DeltaHFScore_i))
  )
```

Benefit orientation:

```text
M_ULF(v) = -rho_ULF(v)   for lower-is-better scales
M_ULF(v) =  rho_ULF(v)   for higher-is-better scales
```

Score and branch-specific prediction models:

```text
ULFScore_mean_main_i =
  sum_{v in V_score} X_ULF_only_i(v, phase,tau) * M_ULF(v)
  / n_valid_score_voxels

delta_hf_adjusted:
  Y_post_i = alpha
           + delta * ULFScore_mean_main_i
           + beta  * Y_HF_ref_i
           + gamma * DeltaHFScore_i
           + error_i

no_delta_hf:
  Y_post_i = alpha
           + delta * ULFScore_mean_main_i
           + beta  * Y_HF_ref_i
           + error_i
```

Key direct voxel implementation details:

```text
tau_primary = 200 V/m
tau_sensitivity = 180 / 220 V/m
Coverage_ULF_tau(v) >= 5
X_ULF_only is tau-specific and excludes HF-overlap voxels
DeltaHFScore source = locked HF direct voxel model for the delta_hf_adjusted branch
primary score = ULFScore_mean_main in both core branches
primary branch = resolved from hf_voxel_prediction_status
ULF branch stability = resolved from ulf_voxel_source_status
ULF branch prediction status = resolved from MAE/RMSE versus branch-specific nuisance baseline
optional OLS ANCOVA = documented only, not run
```

### ULF Normative Connectome Fiber-Level Add-On Model

The normative connectome fiber model is specified in `model_summaries/ulf_addon_gain_normative_connectome_fiber_model.md`. It uses right-canonical full-connectome fibers as primary fitted units and runs both core branches when inputs are available. The DeltaHF-adjusted branch uses:

```text
rho_ULF(l) =
  corr(
    resid(rank(Y_post_i)            ~ rank(Y_HF_ref_i) + rank(DeltaHFScore_i)),
    resid(rank(X_ULF_only_i(l,tau)) ~ rank(Y_HF_ref_i) + rank(DeltaHFScore_i))
  )
```

Candidate rule:

```text
tau_primary = 800 V/m
coverage_primary = Coverage>=5
tau_sensitivity = 1500 V/m
coverage_sensitivity = Coverage>=5
ulf_threshold_scan_tau_grid_v_per_m = [400, 600, 800, 1000, 1200, 1500, 2000]
ulf_threshold_scan_coverage_grid = [5, 6, 7, 8, 10, 12]
Coverage_ULF_tau(l) = sum_i I[X_ULF_only_i(l,tau) > tau]
F_candidate_ULF_tau_cov = {l: Coverage_ULF_tau(l) >= coverage_min}
```

The core tau800/Coverage>=5 branch pair is named `ulf_peak_efield_tau800_cov5_delta_hf_adjusted` and `ulf_peak_efield_tau800_cov5_no_delta_hf`. The matched HF-source resolver first defines the intended primary branch. Each executable ULF branch then runs its own tau/Coverage source resolver: tau800/Coverage>=5 is accepted when stable, otherwise a source-stable scan fallback may define that branch's selected ULF source. Endpoint status is realized from the intended primary branch after branch-specific input readiness and the ULF source resolver are evaluated.

Benefit-oriented fiber weights and patient score:

```text
M_ULF(l) = -rho_ULF(l)   for lower-is-better scales
M_ULF(l) =  rho_ULF(l)   for higher-is-better scales

F+_ULF = top 1% fibers with largest positive M_ULF(l)
F-_ULF = top 0.5% fibers with most negative M_ULF(l)

NetULFFiberScore_i = SweetPeak5_ULF_i - SourPeak5_ULF_i
```

Branch-specific prediction models:

```text
delta_hf_adjusted:
  Y_post_i = alpha
           + delta * NetULFFiberScore_i
           + beta  * Y_HF_ref_i
           + gamma * DeltaHFScore_i
           + error_i

no_delta_hf:
  Y_post_i = alpha
           + delta * NetULFFiberScore_i
           + beta  * Y_HF_ref_i
           + error_i
```

The ULF normative model also writes HF-overlap exclusion summaries, `DeltaHFScore` support/out-of-support QC for the DeltaHF-adjusted branch, plain connected-streamline controls, ULF OSS-DBS activation sensitivity outputs, display density maps, endpoint/anatomical enrichment, and cross-connectome observed robustness summaries. Formal `B=10000` permutation/bootstrap is restricted to the dTOR branch recorded as primary by the branch-role resolver unless another endpoint is explicitly promoted; the default ULF OSS-DBS branch is smoke sensitivity and does not redefine the ULF source resolver or endpoint status.

### Individualized DWI Target-Level Rank-Based Implementation

For individualized-DWI target-level sensitivity models:

1. Rank-transform `Y_post`, `C_ULF_only_bilat(k)`, `Y_HF_ref`, and `DeltaHFScore`.
2. Regress ranked `Y_post` on ranked `Y_HF_ref` and ranked `DeltaHFScore`; keep residuals.
3. Regress ranked `C_ULF_only_bilat(k)` on ranked `Y_HF_ref` and ranked `DeltaHFScore`; keep residuals.
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
ULFTargetScore_k
```

Positive values indicate sweet targets. Negative values indicate sour targets. Secondary voxel and streamline outputs may be generated to localize or visualize these target-level sensitivity findings.

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

Target-derived voxel maps are secondary localization outputs for target-level model families. They should be interpreted with connected-region STN/SNr outlines and target-atlas overlays, but the primary target-level model itself is not cropped to those ROIs. This statement does not apply to the executable HF and ULF direct voxel models, which are independent local stimulation association models specified in their model-summary files.

For legacy generic direct voxel-level sweet spot models, export:

```text
direct_voxel_<seed>_coverage.nii.gz
direct_voxel_<seed>_coef.nii.gz
direct_voxel_<seed>_sweet_sour.nii.gz
direct_voxel_<seed>_stability.nii.gz
direct_voxel_<seed>_bootstrap_se.nii.gz
direct_voxel_<seed>_sweetspot_scores.csv
direct_voxel_<seed>_loocv_predictions.csv
direct_voxel_<seed>_permutation_summary.csv
direct_voxel_<seed>_homologous_mapping_qc.json
```

This generic output list does not apply to the executable HF or ULF direct voxel models. HF uses the `direct_voxel_HF_*` output family under `<scale_slug>/tau*/partial_spearman/`. ULF uses the `direct_voxel_ULF_only_*` output family under `<endpoint_slug>/tau*/partial_spearman/`. Both omit `paired_mask`; optional future OLS outputs would use sibling `ols_ancova/` directories only if explicitly enabled.

For continuous/statistical NIfTI maps in any direct-voxel or target-derived visualization family, non-covered or non-modeled voxels must be `NaN`, not `0`. Coverage/count maps and binary masks are the only exceptions.

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
4. Generate same-component max-combined executable exposure maps.
5. Generate interleaving union and overlap maps as descriptive or sensitivity outputs.
6. Save provenance for voltage, pulse width, frequency, contacts, target, side, phase, and protocol.

### Stage 3: Clinical Endpoint Assembly

1. Build scale-specific raw score tables.
2. Select HF chronic endpoints using `Pre-op` and `STN (3 m)`.
3. Select ULF chronic add-on gain endpoints using `Y_HF_ref = STN (3 m)` and `Y_post = STN+SNr (3 m)`.
4. Select ULF same-day immediate add-on endpoints using `Y_HF_ref = STN (3 m)` before ULF addition and `Y_post = STN+SNr (immediate)`.
5. Record missingness per scale and endpoint.
6. Apply `MIN_N_FOR_MODEL = 12`.

### Stage 4: Fiber And Target Connectivity Extraction

1. Load connectome streamlines in chunks.
2. For HF normative fiber modeling, generate figure-grade observed outputs for PPMI, MGH, and dTOR.
3. For ULF normative fiber modeling, generate ULF-only fiber-level sidecars after excluding HF-overlap streamlines and use `Coverage_ULF_tau(l) >= 5` with `tau800` primary and `tau1500` sensitivity.
4. For individualized-DWI target-level models, compute side-specific target connectivity `C(i,h,k)` using same-side targets.
5. Average left and right target-level individualized-DWI features into patient-level `C_bilat(i,k)`.
6. Record target coverage, streamline counts, candidate counts, label summaries, overlap-exclusion summaries, and reconstruction failures.
7. Reserve formal permutation/bootstrap and jitter QC for the dTOR primary HF and ULF normative fiber branches as specified in their model-specific documents.
8. Compute individualized DWI target connectivity and coverage after DWI registration QC passes.

### Stage 5: Direct Voxel And Secondary Fiber Extraction

1. Build model-specific direct voxel candidate matrices and coverage masks as specified in the HF and ULF direct voxel model documents.
2. Extract subject-by-voxel exposure matrices in chunks when needed.
3. Extract selected-target streamline exposure summaries for contribution and visualization.
4. Compute target-derived seed voxel density, normalized density, coverage, sweet, sour, net, and stability maps only for individualized DWI target-level models or explicitly labeled target-level sensitivities.
5. Compute direct voxel-level HF and ULF frequency-component sweet spot models using bilateral homologous voxel exposure, nested LOOCV, and patient-level permutation.
6. Save coverage and exposure prevalence maps.

### Stage 6: Model Fitting

Fit each model separately by endpoint/scale row:

```text
HF direct voxel 3-month model
HF normative connectome fiber 3-month model
ULF direct voxel chronic add-on gain model
ULF direct voxel immediate add-on gain model when promoted by the model summary
ULF normative connectome fiber chronic add-on gain model
ULF normative connectome fiber immediate add-on gain model when promoted by the model summary
individualized DWI target-level models only in their separate model-summary scope
```

For HF and ULF normative connectome fiber models, engineering execution and resolver classification treat all available endpoint/scale rows equivalently within the applicable endpoint family. Clinical reporting hierarchy can still select primary or secondary rows for formal reporting, but it does not change the model definition, source resolver, prediction-status assignment, or output generation rules.

Use patient-level permutation tests with random seed `42` according to the model-specific resolver and resampling checkpoints. For HF and ULF normative fiber-level models, fiber-wise FDR q-values are QC/display outputs rather than primary filters. For individualized-DWI target-level models, correct multiple comparisons across tested targets within each scale, DWI source, endpoint, and model class using FDR.

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
direct_voxel/hf/
direct_voxel/ulf/
direct_voxel/qc/
exposure/
exposure/interleaving/
models/hf/chronic/
models/stn/immediate/
models/ulf/chronic_gain/
models/ulf/immediate_gain/
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

`Y_HF_ref` controls the pre-ULF total clinical state. It may not fully control:

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

Check collinearity between `DeltaHFScore`, `Y_HF_ref`, and ULF exposure features. Also run `DeltaHFPhys` as an outcome-independent sensitivity covariate.

### Coverage And Sample Size

The cohort currently has `n = 16`. High-dimensional interaction models should not be used for primary inference.

Low-coverage targets, voxels, or streamlines can produce unstable coefficients. Every model must export target coverage summaries and, for secondary maps, coverage maps.

Direct voxel-level sweet spot maps are especially sensitive to small sample size, coverage imbalance, and homologous voxel mapping quality. They should be interpreted as local stimulation association maps and reported alongside normative fiber-level and individualized target-level analyses, not as target-level seed-target maps.

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
same-component alternating subprograms use max-combined exposure in the executable HF/ULF direct voxel and normative fiber models unless a model document states otherwise
union and overlap interleaving outputs are descriptive or sensitivity outputs
HF normative connectome primary predictor selection is fiber-level DBS Fiber Filtering, not target-level aggregation
ULF normative connectome connectivity is computed as right-canonical fiber-level ULF-only exposure with HF-overlap streamlines excluded
individualized-DWI target-level connectivity is computed left and right separately and averaged to one patient-level bilateral target feature
primary model tables have one row per patient, not one row per hemisphere
target-level DWI coverage is checked before individualized-DWI or normative-guided-DWI interpretation
target-derived voxel maps for individualized-DWI target-level models are generated by target-weight back-projection, not by top voxel-wise correlation
HF normative connectome display maps are generated from fiber-level weights, selected streamlines, and streamline-density maps
ULF normative connectome display maps are generated from fiber-level weights, selected streamlines, and streamline-density maps
left and right target-derived voxel maps are generated separately without flipping
coverage, sweet, sour, net, and stability maps are exported for every reported seed voxel visualization
low-coverage seed voxels are transparent or gray in visualization
voxel overlap scores used for prediction are generated from training-fold maps only
direct voxel-level sweet spot mapping is a non-individualized local stimulation association model, not a target-level seed-target model
direct voxel models use bilateral homologous voxel exposure and keep one row per patient
nonlinear homologous voxel mapping uses model-specific transform rules; the executable HF model uses `ea_flip_lr_nonlinear`, while inverse-sampling/trilinear descriptions are generic non-HF context only
direct voxel coverage masks are defined inside each training fold during LOOCV
direct voxel models are compared against covariate-only models with patient-level permutation tests
PPMI, MGH, and dTOR all produce figure-grade observed HF normative fiber summaries
dTOR primary HF normative fiber branch additionally produces formal permutation/bootstrap and jitter QC
STN chronic, ULF chronic add-on gain, and ULF immediate add-on gain outputs are created
low-coverage targets, voxels, and streamlines are flagged
all outputs include provenance
```
