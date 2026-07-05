# HF/ULF Endpoint-Specific Sweet-Spot and Fiber Model Plan

Date: 2026-06-25

## Summary

This document records the planned analysis for symptom-specific HF-only efficacy and HF-adjusted ULF-only add-on gain mapping in the STN/SNr DBS cohort. The plan combines the endpoint-specific ANCOVA-style model in `/Users/mojackhu/Downloads/STN_SNr_endpoint_specific_sweetspot_pseudocode.md` with the previous decisions for public connectomes, individualized DWI tractography, ROI definition, streamline interpretation, stimulation exposure, and sensitivity analyses.

The primary scientific framing is frequency-component based rather than nucleus-assignment based. The former STN-only phase is treated as HF-only stimulation. The former combined STN+SNr phase is treated as HF+ULF stimulation. The two main estimands are:

```text
HF-only efficacy heatmap
HF-adjusted ULF-only add-on gain heatmap
```

Frequency definitions are fixed as:

```text
HF  = high-frequency stimulation component, frequency_Hz >= 100
ULF = ultra-low-frequency stimulation component, frequency_Hz <= 50
```

The HF and ULF normative connectome analyses now use fiber-level DBS Fiber Filtering models. Individual streamlines from the full public connectome are the primary modeling units, while target atlases are retained for anatomical labeling, QC, and visualization. Individualized DWI analyses remain target-level unless their model-specific documents state otherwise. STN and SNr are not used to crop VTA, truncate streamlines, or hard-assign model effects. Instead, prebuilt STN/SNr connected-region atlases define anatomical context, endpoint grouping, territory overlays, and sensitivity analyses.

If a voxel or streamline is activated by both HF and ULF components, it is attributed to the HF model and contributes to `DeltaHFScore` adjustment rather than to `X_ULF_only`. Only ULF-only activated voxels or streamlines enter the ULF add-on predictor.

The implementation-level technical details for normative connectome fiber-level analysis and individualized target-level connectivity analysis are recorded in:

`/Users/mojackhu/Github/leaddbs/my_helper/stnsnr/normative_connectome_sweet_sour_technical_details.md`

The DWI registration prerequisites are recorded in:

`/Users/mojackhu/Github/leaddbs/my_helper/stnsnr/dwi_registration_technical_details.md`

## Model Summary Documents

The six model-specific summaries are:

| Research question | Model class | Summary document |
|---|---|---|
| HF-only 3m efficacy | Direct voxel-level | [`hf_3m_direct_voxel_model.md`](model_summaries/hf_3m_direct_voxel_model.md) |
| HF-only 3m efficacy | Normative connectome DBS Fiber Filtering / fiber-level | [`hf_3m_normative_connectome_fiber_model.md`](model_summaries/hf_3m_normative_connectome_fiber_model.md) |
| HF-only 3m efficacy | Individualized DWI seed-target / fiber-derived target-level | [`hf_3m_individualized_dwi_seed_target_model.md`](model_summaries/hf_3m_individualized_dwi_seed_target_model.md) |
| HF-adjusted ULF-only add-on gain | Direct voxel-level | [`ulf_addon_gain_direct_voxel_model.md`](model_summaries/ulf_addon_gain_direct_voxel_model.md) |
| HF-adjusted ULF-only add-on gain | Normative connectome DBS Fiber Filtering / fiber-level | [`ulf_addon_gain_normative_connectome_fiber_model.md`](model_summaries/ulf_addon_gain_normative_connectome_fiber_model.md) |
| HF-adjusted ULF-only add-on gain | Individualized DWI seed-target / fiber-derived target-level | [`ulf_addon_gain_individualized_dwi_seed_target_model.md`](model_summaries/ulf_addon_gain_individualized_dwi_seed_target_model.md) |

For HF-only direct voxel model execution, the model-specific summary
[`hf_3m_direct_voxel_model.md`](model_summaries/hf_3m_direct_voxel_model.md)
is the authoritative specification.
HF direct voxel output file semantics are also defined there and should not be
duplicated as a separate source of truth in this master plan.

## Fixed Inputs and Defaults

- Repository root: `/Users/mojackhu/Github/leaddbs`.
- Helper root for implementation: `/Users/mojackhu/Github/leaddbs/my_helper/fiber`.
- Topic-level documentation root: `/Users/mojackhu/Github/leaddbs/my_helper/stnsnr`.
- STN/SNr pipeline scripts remain under `/Users/mojackhu/Github/leaddbs/my_helper/fiber/stnsnr` and should only call reusable core functions.
- Core functions should remain under `/Users/mojackhu/Github/leaddbs/my_helper/fiber/core`.
- Default Conda environment for Lead-DBS tasks: `leaddbs`.
- Python statistical postprocessing for the HF/LF model family should run in the `leaddbs` Conda environment; installing or adjusting required Python packages in that environment is allowed when recorded in the run manifest or an environment export.
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

### Model Territory and ROI Priority

For model-level territory definitions and seed-target endpoint grouping, prefer the prebuilt connected-region atlases:

```text
HF territory atlas:
  /Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/atlases/STN-connected regions

ULF territory atlas:
  /Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/atlases/SNr-connected regions

Combined STN/SNr territory atlas:
  /Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/atlases/STNSNr-connected regions
```

Each connected-region atlas contains side-specific binary masks and a `roi_manifest.csv` that records the upstream atlas source, threshold, role, and category for each ROI. Use the connected-region atlas ROI files directly for candidate fiber classification, endpoint grouping, coverage summaries, and visualization overlays. Do not use these masks to hard-split overlapping VTA or streamlines into anatomic STN versus SNr effects.

For HF-only analyses, use `STN-connected regions` first as the historical HF territory atlas. Its primary ROIs include `STN`, `SNr`, `M1`, `SMA`, `preSMA`, `premotor`, `GPe`, and `GPi`, with optional or exploratory `DLPFC`, `ACC`, `OFC`, and `vmPFC` masks.

For ULF-only add-on analyses, use `SNr-connected regions` first as the historical ULF target-territory atlas. Its primary ROIs include `SNr`, `STN`, `VA_thalamus`, `VLA_thalamus`, `VLP_thalamus`, `VM_thalamus`, `posterior_putamen`, `PPN`, and `superior_colliculus`, with optional or exploratory `caudate`, `MD_thalamus`, `CM_thalamus`, `Pf_thalamus`, `sPf_thalamus`, `FEF`, `SMA`, `preSMA`, `premotor`, `M1`, and `DLPFC` masks.

For combined STN/SNr analyses, use `STNSNr-connected regions` first. Its primary combined seed is `STNSNr`; `STNSNrplus` is the same seed with 2 mm dilation. Single-component `STN` and `SNr` masks remain available in the same atlas for component context.

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

## Target-Level Seed-Target Connectivity For Individualized DWI

### Core Unit

This section applies to individualized DWI seed-target models, target-derived visualization, and explicitly labeled target-level sensitivity analyses. It does not define the primary HF or ULF normative connectome models, which are right-canonical full-connectome fiber-level DBS Fiber Filtering models. It also does not define direct voxel models.

For target-level model families, the primary connectivity predictor is the bilateral seed-target feature:

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

For historical or explicitly labeled normative target-level sensitivity analyses:

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

Predictor selection is performed at the target label level, not at the individual fiber level, only for target-level model families. The current HF and ULF normative connectome project files use fiber-level fitting and do not use this target-level selection rule.

For each target `k`, fit a target-wise ANCOVA or rank-based partial model in the training data:

```text
Y_post(i) = alpha_k
          + theta_k * Z(C_bilat(i,k))
          + beta_k  * Z(Y_baseline(i))
          + gamma_k * Z(DeltaHFScore(i))
          + error(i,k)
```

For HF-only target-level sensitivity models, `Y_baseline` is `Y_Preop` and `DeltaHFScore` is omitted unless the model explicitly studies HF reprogramming. For ULF add-on gain target-level sensitivity models, use the model-specific clinical reference `Y_HF_ref` and retain model-family-matched `DeltaHFScore`.

Define the benefit-oriented target weight as:

```text
w_k = -theta_k
```

for lower-is-better scales, and:

```text
w_k = theta_k
```

for SE-ADL. Positive `w_k` always means more connectivity to that target predicts better outcome.

Target quality filtering precedes efficacy ranking. Exclude targets with too few streamlines, near-zero across-patient variance, excessive individualized-DWI reconstruction failure, or high collinearity with baseline or `DeltaHFScore`.

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
Y_post ~ Y_baseline + DeltaHFScore
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

Use two HF-only model layers.

Primary HF model:

```text
chronic HF-only efficacy model
```

This model answers:

```text
Which normative connectome streamlines directly touched by HF stimulation are associated with stable HF-only benefit at 3 months?
```

Secondary HF model:

```text
early / acute HF-only response model
```

This model answers:

```text
Which target-level HF seed-target connectivity features are associated with the early response after STN activation?
```

The chronic HF-only model is the primary HF model because it localizes stable HF DBS benefit and uses the same HF-only 3m clinical state that serves as the baseline for ULF-addition models.

#### Primary Chronic HF Normative Fiber-Level Model

For each scale and candidate fiber `l`:

```text
rho_HF(l) =
  corr(
    resid(rank(Y_HF3m_i) ~ rank(Y_Preop_i)),
    resid(rank(X_HF_i(l)) ~ rank(Y_Preop_i))
  )
```

Definitions:

- `Y_HF3m_i`: raw HF-only 3-month clinical score for patient `i`.
- `Y_Preop_i`: raw preoperative score for patient `i`.
- `E_R_i(l)`: right-side peak raw sim-efield sampled along right canonical normative fiber `l`.
- `E_L_to_R_i(l)`: left-side peak raw sim-efield after `ea_flip_lr_nonlinear`, sampled along the same right canonical normative fiber `l`.
- `X_HF_i(l) = (E_R_i(l) + E_L_to_R_i(l)) / 2`: patient-level right canonical bilateral HF peak e-field exposure for normative fiber `l`.
- `rho_HF(l)`: baseline-adjusted fiber-wise association.

Benefit-oriented fiber weight:

```text
M_HF(l) = -rho_HF(l)   for lower-is-better scales
M_HF(l) =  rho_HF(l)   for higher-is-better scales
```

Candidate fibers are drawn from the full public connectome, not predefined target-restricted tracts:

```text
tau_primary = 800 V/m
tau_sensitivity = 1500 V/m
Coverage_tau(l) = sum_i I[X_HF_i(l) > tau]
F_candidate_tau = {l: Coverage_tau(l) >= 5}
```

The executable HF normative fiber model uses a right-canonical streamline feature space and the same patient-level coverage rule as the HF direct voxel model. Left stimulation is flipped into the same right-sided feature set; bilateral E-field information is averaged into `X_HF_i(l)`, but the streamline features are not a true bilateral streamline set.

Do not use change score or percent improvement as the primary HF sweet-spot outcome. The existing improvement-rate table can be used for compatibility checks, smoke tests, descriptive reporting, and sensitivity analyses.

#### HF Fiber Score And Visualization

The primary HF normative connectome score is a net sweet-minus-sour peak score:

```text
F+ = top 1% fibers with largest positive M_HF(l)
F- = top 0.5% fibers with most negative M_HF(l)

SweetWeighted_i(l) = X_HF_i(l) * M_HF(l),      l in F+
SourWeighted_i(l)  = X_HF_i(l) * [-M_HF(l)],   l in F-

SweetPeak5_i = mean of top 5% largest SweetWeighted_i(l)
SourPeak5_i  = mean of top 5% largest SourWeighted_i(l)

NetFiberScore_i = SweetPeak5_i - SourPeak5_i
```

This score is the primary HF normative connectome predictor for prediction and cross-validation. Target atlases label selected fibers after model fitting, but target labels do not define the primary predictor.

After fitting the HF fiber-level model, export selected fiber and density visualizations:

```text
normative_HF_fiber_display_top1_positive.tck
normative_HF_fiber_display_top0p5_sour.tck
normative_HF_fiber_density_map.nii.gz
normative_HF_fiber_endpoint_labels.csv
normative_HF_fiber_cortical_endpoint_summary.csv
normative_HF_fiber_subcortical_crossing_summary.csv
normative_HF_fiber_label_enrichment.csv
normative_HF_fiber_unthresholded_weighted_density.nii.gz
normative_HF_fiber_neglogp_density.nii.gz
fdr_summary_by_scale.csv
connectome_scale_performance_summary.csv
normative_HF_plain_connected_model_comparison.csv
```

These HF maps answer:

```text
Which normative streamlines and streamline-density regions are most strongly associated with better or worse HF-only outcomes?
```

They are fiber-level association maps, not target-level seed-zone maps and not patient-specific causal tract proof.

#### Secondary Early / Acute STN-Only Model

For scales with valid immediate STN assessment, fit an early HF-only model.

If only preoperative baseline is available:

```text
Y_STNImmediate_i = alpha_0
                 + alpha_HF,k_early * C_STNImmediate_bilat(i,k)
                 + alpha_B           * Y_Preop_i
                 + error_i
```

Name this model:

```text
early HF-only response model
```

Do not call it a pure acute STN effect, because the preoperative-to-immediate interval may include perioperative recovery, microlesion effects, medication changes, and timing differences.

If a same-day STN-OFF baseline exists at the first programming visit, use it instead of preoperative baseline:

```text
Y_STNImmediate_i = alpha_0
                 + alpha_HF,k_acute * C_STNImmediate_bilat(i,k)
                 + alpha_B           * Y_STNOffSameDay_i
                 + error_i
```

Name this cleaner version:

```text
acute STN stimulation response model
```

With the currently inspected score tables, immediate STN and STN+SNr assessments are available for `UPDRS-III` and `UPDRS-III axial`. Pain, quality-of-life, and most non-motor scales should not be forced into immediate HF models unless valid immediate assessments exist.

#### Optional STN Chronic Adaptation Model

Use this only as a secondary mechanism model when STN-immediate and STN-3m programming differ enough to justify studying chronic adaptation or programming optimization:

```text
Y_HF3m_i = alpha_0
          + alpha_HF,k_adapt * C_HF3m_bilat(i,k)
          + alpha_B           * Y_STNImmediate_i
          + alpha_D           * DeltaHFScore_ImmTo3m_i
          + error_i
```

where:

```text
DeltaHFScore_ImmTo3m = HFScore_STN3m - HFScore_STNImmediate
```

Here `HFScore` should use the same endpoint/domain-matched and model-family-matched HF efficacy-model scoring function `S_HF_family(E)`, not raw programming parameters. This optional adaptation covariate is distinct from the ULF-add-on-gain `DeltaHFScore`, which compares the HF-only 3-month setting with the HF component of combined STN+SNr stimulation.

This optional model should not replace the primary chronic HF-only model.

The chronic HF model also supports an optional residualized ULF model by predicting the HF contribution under the HF component of combined stimulation.

### ULF Add-On Gain Endpoint Selection

The ULF add-on model should use raw post-combination scores when available, following an ANCOVA-style endpoint-specific design. The ULF add-on model family has one primary estimand:

```text
clinical optimization-informed ULF-only add-on model
```

This model asks whether final clinician-optimized ULF-only fiber exposure predicts better STN+SNr outcome after controlling the pre-ULF HF-only 3-month clinical state and the concurrent HF efficacy-map score change of the HF component.

The model has two endpoints:

```text
chronic ULF add-on gain endpoint:
  clinical reference = Y_HF_ref, raw HF-only 3-month score at T2
  post score         = raw HF+ULF 3-month score at T3
  model class    = chronic

immediate ULF add-on gain endpoint:
  clinical reference = Y_HF_ref, raw HF-only 3-month score at T2 before same-day ULF addition
  post score         = raw HF+ULF immediate score at T2 after same-day ULF addition
  model class    = immediate
```

Use `MIN_N_FOR_MODEL = 12`. Do not hard-code scale names into endpoint selection. Choose each endpoint per scale based on complete paired score and exposure availability.

### DeltaHFScore Construction

`DeltaHFScore` is the scalar covariate used to control HF component reprogramming in ULF add-on gain models. The preferred definition is not a raw voltage, pulse-width, frequency, or contact-change summary. It is the change in predicted HF efficacy of the HF component between the HF-only 3-month setting and the combined HF+ULF setting.

The HF adjustment must be model-family matched:

```text
ULF direct voxel-level model
  -> use HF direct voxel-level efficacy model

ULF normative connectome fiber-level model
  -> use HF normative connectome fiber-level efficacy model

ULF individualized DWI seed-target model
  -> use HF individualized DWI seed-target efficacy model
```

Do not use a cross-family HF adjustment as the primary covariate. For example, do not use a direct voxel-level HF map as the main `DeltaHFScore` in a normative fiber-level or individualized seed-target ULF model.

For the direct voxel-level family, train an endpoint/domain-matched HF efficacy map using only pre-ULF HF-only data. The formula below is schematic; the current executable HF direct voxel model uses baseline-adjusted partial Spearman and `HFScore_mean_main`, with OLS ANCOVA documented only as optional future supplemental analysis:

```text
Y_HF3m_i = alpha_u
          + theta_HF(u) * X_HF_only_i(u)
          + beta_u       * Y_Preop_i
          + error_i,u
```

For lower-is-better scales:

```text
M_HF(u) = -theta_HF(u)
```

For SE-ADL:

```text
M_HF(u) = theta_HF(u)
```

Then score any HF setting `E` against this direct voxel-level HF efficacy map:

```text
S_HF_voxel(E) =
  sum_{u in V_HF_score} E(u) * M_HF(u)
  / n_valid_HF_score_voxels
```

For the normative connectome family, use the HF normative fiber-level score:

```text
S_HF_norm_fiber(E) = NetFiberScore(E)
```

For the individualized DWI seed-target family, use the HF individualized DWI target-level score:

```text
S_HF_ind(E) =
  sum_{k in S_HF_ind} w_HF,k_ind * Z_train(C_ind_HF_component(E,k))
  / sum_{k in S_HF_ind} abs(w_HF,k_ind)
```

Use the score from the matching model family:

```text
DeltaHFScore_family,i =
  S_HF_family(E_HF_component_i,combined)
  - S_HF_family(E_HF_component_i,HF-only3m)
```

Interpretation:

```text
DeltaHFScore_i > 0
  combined-phase HF component is closer to the learned HF efficacy map

DeltaHFScore_i < 0
  combined-phase HF component is less aligned with the learned HF efficacy map
```

This definition is acceptable because the HF efficacy model is trained on HF-only 3-month outcomes before ULF is added; it is not trained on STN+SNr outcomes. In strict prediction, target selection, weights, voxel maps, patient-specific reconstruction, and `Z_train()` scaling are all learned or computed within the outer training fold.

Endpoint/domain matching is required:

- For chronic ULF 3-month models, train the HF map from the matching HF-only 3-month scale or symptom domain.
- For immediate ULF motor models, use a motor-specific HF map trained from HF-only 3-month motor outcome as the main definition.
- A HF immediate motor-derived acute map may be used only as sensitivity analysis.
- Do not use a total-score HF map as the main `DeltaHFScore` for a motor-only immediate endpoint.

For strict ULF LOOCV prediction, train the model-matched HF efficacy model inside each outer training fold and use that fold-specific HF model to compute `DeltaHFScore` for both training and held-out patients. For final descriptive maps, a full-sample pre-ULF HF model may be used and should be reported as a same-cohort, pre-ULF-derived nuisance adjustment rather than an external independent model.

Required diagnostics:

```text
cor(DeltaHFScore, Y_HF_ref)
cor(DeltaHFScore, ULF exposure features)
```

Also run a physical HF-change sensitivity covariate that does not depend on clinical outcome, such as charge-rate or e-field overlap change, to test whether conclusions depend on the learned HF efficacy map.

### Primary ULF Add-On Gain Model

The ULF add-on family is model-specific. Direct voxel, normative connectome fiber, and individualized DWI target-level models share the same clinical covariates but use different primary predictors.

For direct voxel ULF:

```text
Y_post_i = alpha
         + delta * ULFScore_mean_main_i
         + beta  * Y_HF_ref_i
         + gamma * DeltaHFScore_i
         + error_i
```

For normative connectome ULF fiber-level analysis:

```text
Y_post_i = alpha
         + delta * NetULFFiberScore_i
         + beta  * Y_HF_ref_i
         + gamma * DeltaHFScore_i
         + error_i
```

For individualized DWI target-level sensitivity:

```text
Y_post_i = alpha_0
         + theta_ULF,k * C_ULF_only_bilat(i,k)
         + beta         * Y_HF_ref_i
         + gamma        * DeltaHFScore_i
         + error_i
```

Definitions:

- `Y_post_i`: selected post-HF+ULF raw clinical score for patient `i`.
- `Y_HF_ref_i`: raw HF-only 3-month clinical state at `T2` before ULF addition, using the same scale or symptom domain.
- `ULFScore_mean_main_i`: direct voxel ULF-only score from `ulf_addon_gain_direct_voxel_model.md`.
- `NetULFFiberScore_i`: normative connectome ULF-only fiber score from `ulf_addon_gain_normative_connectome_fiber_model.md`.
- `C_ULF_only_bilat(i,k)`: individualized DWI target-level bilateral seed-target connectivity for target `k`.
- `DeltaHFScore_i`: endpoint/domain-matched and model-family-matched change in predicted HF efficacy score for the HF component.

Question:

```text
Among patients with comparable HF-only 3-month clinical state and comparable HF-component changes,
does final ULF-only exposure or connectivity predict better HF+ULF outcome?
```

Interpretation:

The ULF coefficient or score association is conditional on pre-ULF clinical state and concurrent HF reprogramming. In the normative connectome ULF model, the association is estimated at fiber level using `NetULFFiberScore`; target-level notation is retained only for individualized DWI seed-target sensitivity models. Benefit-oriented maps are sign-oriented inside each model-specific document so positive values consistently indicate better predicted clinical outcome.

#### Chronic ULF Add-On Gain Model

Use this model to estimate the long-term ULF-associated post-add-on outcome after adding ULF to HF stimulation:

```text
Y_post_chronic = raw HF+ULF 3-month score at T3
Y_HF_ref       = raw HF-only 3-month score at T2
DeltaHFScore   = DeltaHFScore_chronic
```

Question:

```text
In patients with the same HF-only 3-month clinical state and the same HF component change,
does final ULF-only exposure or connectivity predict better HF+ULF 3-month outcome?
```

#### Immediate ULF Add-On Gain Model

Use this model to estimate the same-day immediate ULF-associated add-on outcome after adding ULF to HF stimulation:

```text
Y_post_immediate = raw HF+ULF immediate score at T2 after same-day ULF addition
Y_HF_ref         = raw HF-only 3-month score at T2 before same-day ULF addition
DeltaHFScore     = DeltaHFScore_immediate
```

Question:

```text
In patients with the same HF-only 3-month clinical state and the same immediate-phase HF component change,
does final ULF-only exposure or connectivity predict better same-day HF+ULF immediate outcome?
```

The `Y_HF_ref` covariate controls the pre-ULF clinical state. For the immediate endpoint, `Y_HF_ref` and `Y_post_immediate` are same-day T2 measurements before and after ULF addition. `DeltaHFScore_immediate` controls concurrent HF component reprogramming in the immediate HF+ULF setting using a motor-domain and model-family-matched HF efficacy model.

#### Rank-Based ULF Implementation

Use a rank-based partial Spearman estimator as the main implementation for `n = 16`:

1. Rank-transform `Y_post`, the ULF predictor, `Y_HF_ref`, and `DeltaHFScore`.
2. Regress ranked `Y_post` on ranked `Y_HF_ref` and ranked `DeltaHFScore`; keep residuals.
3. Regress the ranked ULF predictor on ranked `Y_HF_ref` and ranked `DeltaHFScore`; keep residuals. For direct voxel ULF, the predictor is voxel-level `X_ULF_only(v,tau)`. For normative connectome ULF, the predictor is fiber-level `X_ULF_only(l,tau)`. For individualized DWI seed-target sensitivity, the predictor remains target-level `C_ULF_only_bilat(k)`.
4. Correlate the two residual vectors.
5. Flip sign when higher clinical score means worse outcome, so positive scores always indicate benefit.

```text
M_ULF > 0 means stronger ULF-only exposure predicts better HF+ULF outcome after HF-state and DeltaHFScore adjustment.
```

### ULF Add-On Gain Estimand Boundaries

The time zero for ULF-addition models is:

```text
HF-only 3-month assessment, immediately before adding or optimizing ULF stimulation
```

The ULF add-on models do not estimate:

```text
total STN+SNr improvement from preoperative baseline
percent improvement difference between STN+SNr and HF-only
the outcome each patient would have had at every untested ULF location
```

They estimate target-level spatial associations between final ULF seed-target connectivity and post-combination outcome after conditioning on the selected baseline state.

The observed final ULF location is clinician-selected:

```text
C_i* = final ULF setting selected for patient i after clinical programming
```

Thus the observed outcome is:

```text
Y_i(C_i*)
```

not the full set of counterfactual outcomes:

```text
Y_i(s) for every possible ULF location s
```

Therefore, the ULF voxel maps, fiber maps, target maps, and patient scores are patient-level between-subject spatial association models. They are not within-patient randomized location-response maps.

### Scientific Preconditions for ULF Add-On Gain Inference

The ULF add-on gain analyses are scientifically meaningful under these conditions:

- `Y_HF_ref` adequately represents the clinical state before ULF addition.
- `DeltaHFScore` is constructed from an endpoint/domain-matched and model-family-matched HF efficacy model trained only on pre-ULF HF-only data.
- The final ULF setting is a clinically optimized setting, not an arbitrary or poorly explored setting.
- Acute programming response and side-effect thresholds used to choose the final ULF setting have reasonable relevance to the 3-month outcome.
- ULF-only voxel, fiber, or target-level exposure has enough across-patient variability to estimate model weights.
- Within comparable ranges of `Y_HF_ref` and `DeltaHFScore`, there is sufficient overlap in ULF-only exposure to avoid relying mainly on extrapolation.
- Unmeasured prognosis factors, symptom subtypes, medication changes, rehabilitation intensity, anatomy, and programming style do not strongly determine both the final ULF location and the later STN+SNr outcome.
- STN and SNr effects are sufficiently separable for an additive model to remain interpretable.

Coverage must be reported for every target-level model and every secondary voxel or fiber output:

```text
Coverage(k) = number of patients with usable bilateral connectivity for target k
ExposureCoverage = model-specific coverage of ULF-only voxels, fibers, or targets
```

Only targets, regions, or streamlines with adequate coverage should receive strong anatomical interpretation.

### Potential Problems with the ULF Add-On Gain Definition

Main limitations:

- The maps are not pure causal maps of SNr spatial efficacy.
- Clinician selection can induce indication bias because different SNr regions may be selected for different patient subtypes.
- `Y_HF_ref` controls total pre-ULF severity, but may not fully control symptom composition, DBS responsiveness, future prognosis, or side-effect limitations.
- `DeltaHFScore` is a same-cohort, pre-ULF-derived nuisance adjustment unless an external model-family-matched HF efficacy model is used.
- `DeltaHFScore` may be an incomplete summary of HF reprogramming because HF component changes can involve contact, amplitude, pulse width, frequency, e-field shape, and fiber recruitment.
- `DeltaHFScore` may be noisy or overfit because the model-matched HF efficacy model is trained in the same small cohort.
- The model-specific ULF predictor and `DeltaHFScore` may be collinear if certain ULF exposure profiles are systematically paired with certain HF programming changes.
- Low-coverage targets, locations, or streamlines can generate unstable coefficients.
- With `n = 16`, interaction models such as `ULFPredictor * subtype` or `ULFPredictor * DeltaHFScore` are usually too unstable for primary inference.
- Normative connectomes support group-level structural interpretation; individualized DWI analyses are needed for subject-specific anatomy but remain limited by reconstruction quality.
- Random or Gaussian proxy stimulation results validate the pipeline only and should not be biologically interpreted.

The most defensible wording is:

```text
adjusted relative ULF-only add-on map
clinical optimization-informed ULF-only add-on map
```

Avoid:

```text
absolute causal map of SNr efficacy
evidence that every patient should be stimulated at this location
```

### STN Reprogramming Confound

Do not interpret `STN+SNr - STN-alone` as pure SNr benefit if STN parameters changed between phases.

The primary ULF add-on gain model controls this by including:

```text
DeltaHFScore =
  S_HF_family(E_HF_component,combined)
  - S_HF_family(E_HF_component,HF-only3m)
```

where `S_HF_family` is the HF efficacy score computed from the model-family-matched HF model trained only on pre-ULF HF-only data.

Do not use raw contact, voltage, pulse width, or frequency change as the main `DeltaHFScore`. Those physical summaries are sensitivity covariates.

Main chronic SNr 3-month analysis:

```text
DeltaHFScore_3m =
  S_HF_family,domain(E_HF_component,STN+SNr3m)
  - S_HF_family,domain(E_HF_component,HF-only3m)
```

Main SNr immediate motor analysis:

```text
DeltaHFScore_immediate =
  S_HF_family,motor(E_HF_component,STN+SNr immediate)
  - S_HF_family,motor(E_HF_component,HF-only3m)
```

Report this as a same-cohort, pre-ULF-derived nuisance adjustment unless the model-matched HF efficacy model comes from an external dataset.

### Residualized SNr Sensitivity Model

As a complementary sensitivity analysis:

1. Train an STN response model on STN-alone data.
2. Predict the expected HF contribution in the combined phase using the combined-phase HF component.
3. Compute:

```text
Y_SNr_residual = observed STN+SNr outcome - predicted HF contribution
```

4. Model `Y_SNr_residual` against ULF-component target-level connectivity.

Use leave-one-patient-out predictions for any residualized model to avoid optimistic reuse of the same patient in both training and prediction.

## Target, Fiber, and Sweet-Spot Definitions

### Voxel Sweet Spot

Voxel sweet spots are secondary localization outputs. For each voxel and outcome, model the relation between subject-level stimulation exposure at that voxel and clinical response after the target-level model has been specified.

For the HF model, use HF-only exposure and HF response. For the ULF add-on gain model, use ULF-component exposure and endpoint-specific post-score models adjusted for HF-3m baseline and endpoint/domain-matched HF efficacy-map score change. Run the chronic gain endpoint for `STN+SNr 3m` and the immediate gain endpoint for `STN+SNr immediate`.

Voxel maps should not drive primary predictor selection.

### Direct Voxel-Level Sweet Spot Mapping

Direct voxel-level sweet spot mapping is added as a separate local stimulation analysis. It is distinct from the target-derived seed voxel maps below.

The direct voxel model asks:

```text
Within the covered right-canonical stimulation territory, which voxels have component-specific stimulation exposure associated with better clinical outcome?
```

It follows the voxel sweet-spot logic used in DBS sweet spot mapping studies: compute patient-specific E-field magnitude at each voxel, fit a voxel-wise clinical association model, then compute a patient-level sweet spot overlap score for cross-validated prediction.

This analysis is a local stimulation association model. It is complementary to normative fiber-level and individualized target-level network models because `n = 16` and the number of voxels is much larger than the number of patients.

#### HF Direct Voxel Model

For the HF-only chronic efficacy model, the exposure is the HF-only component from the historical STN-only phase:

```text
Y_HF3m_i = alpha_v
          + theta_HF(v) * X_HF_only_i(v)
          + beta_v       * Y_Preop_i
          + error_i,v
```

Definitions:

- `Y_HF3m_i`: raw HF-only 3-month clinical score.
- `Y_Preop_i`: raw preoperative clinical score.
- `X_HF_only_i(v)`: bilateral homologous HF E-field exposure at canonical right-hemisphere voxel `v`.
- `theta_HF(v)`: optional direct HF voxel OLS coefficient; the current executable partial Spearman map stores `rho_HF(v)`.

For lower-is-better scales:

```text
M_HF(v) = -theta_HF(v)
```

For SE-ADL:

```text
M_HF(v) = theta_HF(v)
```

Positive `M_HF(v)` means stronger HF exposure at voxel `v` predicts better baseline-adjusted HF-only outcome.

Resolved HF/STN settings (these fix, for the HF/STN direct voxel model only, the options left open in the generic subsections below; see `model_summaries/hf_3m_direct_voxel_model.md`). The generic subsections still apply to the ULF/SNr direct voxel model unchanged unless explicitly overridden there.

- Exposure `X_HF_only`: the real Horn/SimBio `sim-efield` (raw variant, kept in `V/m`) from each subject's `3m/STN` MNI stimulation folder `stimulations/MNI152NLin2009bAsym/*_3m_STN_*/sub-*_sim-efield_model-simbio_hemi-{L,R}.nii`. Combine alternating same-side subprograms by voxel-wise maximum.
- E-field availability: assume existing e-fields have passed prior manual/clinical QC. The executable HF model only checks path existence, unique subject/side/condition matching, raw `sim-efield` identity, and `V/m` unit provenance. Missing or multiply matched e-fields fail the scale/run; the HF direct voxel model does not automatically recompute e-fields or silently exclude subjects.
- Candidate / coverage: use the MNI152NLin2009bAsym `brainmask.nii.gz > 0` right hemisphere (`x > 0`) as the canonical reference mask. Build a sparse candidate mask from any valid subject with `X_HF_only > 180 V/m`; fit each tau where `Coverage(v) >= 5`, with `tau = 200 V/m` primary and `180`/`220 V/m` sensitivity. Do not intersect `Omega_HF_tau` with `right_STNSNrplus`; keep `STNSNr-connected regions/{rh,lh}/STNSNrplus.nii.gz` only as anatomical overlay and coverage/QC background. `Coverage>=6` and `Coverage>=8` are documented optional sensitivities only and are not generated in the current executable HF analysis.
- Bilateral homology: map the left E-field to the right canonical brainmask grid with `ea_flip_lr_nonlinear` + `templates/space/MNI152NLin2009bAsym/fliplr/Composite.nii.gz`; no paired-mask membership threshold is used for the HF direct voxel executable model. A flip deformation audit records grid/affine, finite/nonzero voxel counts, max/p95/p99/sum, suprathreshold volumes, centroid, and right-brainmask overlap as warnings only.
- Estimator: primary baseline-adjusted partial Spearman with average ranks and benefit-oriented `rho`; OLS ANCOVA is optional future supplemental analysis and is not run in the current executable analysis. The primary patient-level score is `HFScore_mean_main = sum_v X_HF_only(v) * M_HF(v) / n_valid_score_voxels`, using the fixed scoring voxel set for the corresponding full-sample map or LOOCV training fold. It is voxel-count-normalized for fold-to-fold comparability, but it is not divided by `sum(X)` and is not multiplied by voxel volume. `HFScore_sum_descriptive` is kept only as a documented concept and is not computed by the current executable analysis.
- Permutation: patient-level Freedman-Lane, formal `B = 10000`, smoke/exploratory `B = 1000`, seed `42`, primary statistic LOOCV Spearman rho, plus-one two-sided p value. Formal permutation is restricted to `tau200/partial_spearman`; non-primary branches record `not_run_nonprimary`. The primary `coef` map stores `rho_HF(v)`; the OLS supplemental `coef` map stores `theta_HF(v)`. No per-voxel FDR is applied.
- Bootstrap: subject-level full-process bootstrap, formal `B = 10000`, smoke/exploratory `B = 1000`, seed `42`; rerun map building including `Omega_HF_tau` and store voxel-wise estimator standard error for `tau200/partial_spearman` only. Non-primary branches do not generate bootstrap SE maps.
- Spatial jitter QC: primary `tau200/partial_spearman` only, formal `B = 1000`, smoke `B = 100`, independent subject-side 3D translation jitter with Gaussian `FWHM = 2 mm`, linear E-field interpolation, and outside fill `0`.
- Endpoints: first pass = MDS-UPDRS III and MDS-UPDRS III axial (both lower-is-better) from `subject_effect_origin.xlsx`, joined by `ID`; a patient missing `Y_HF3m` or a side's e-field fails scale-level QC as specified in the model summary.
- Outputs: keep the `direct_voxel_HF_*` file names under `/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale_slug>/tau180|tau200|tau220/partial_spearman/`; optional future OLS outputs would use sibling `ols_ancova/` directories if explicitly enabled. `tau200/partial_spearman` and unsmoothed maps are primary, `1-2 mm` FWHM smoothed maps are display-only outputs. Report-only sweet/sour display masks use top 10% same-sign map values plus direction-specific stability `>=0.75`; they are not significance maps.

#### ULF Direct Voxel Model

The executable ULF direct voxel model is fully specified in `model_summaries/ulf_addon_gain_direct_voxel_model.md`. It is not an anatomic SNr-only model. It treats the STN/SNr and peri-STN/SNr region as a stimulation territory and separates HF and ULF effects by frequency component and HF-overlap exclusion.

```text
rho_ULF(v) =
  corr(
    resid(rank(Y_post_i)                   ~ rank(Y_HF_ref_i) + rank(DeltaHFScore_i)),
    resid(rank(X_ULF_only_i(v, phase,tau)) ~ rank(Y_HF_ref_i) + rank(DeltaHFScore_i))
  )
```

Definitions:

- `Y_post_i`: raw HF+ULF post-addition clinical score for the selected chronic or same-day immediate endpoint.
- `Y_HF_ref_i`: raw HF-only 3-month clinical state at T2 before ULF addition.
- `X_ULF_only_i(v, phase,tau)`: tau-specific ULF component exposure after excluding voxels co-activated by HF at the same tau.
- `DeltaHFScore_i`: endpoint/domain-matched change in predicted HF efficacy score from the locked HF direct voxel model.
- `rho_ULF(v)`: covariate-adjusted partial Spearman association.

For lower-is-better scales:

```text
M_ULF(v) = -rho_ULF(v)
```

For SE-ADL:

```text
M_ULF(v) = rho_ULF(v)
```

Positive `M_ULF(v)` means stronger ULF-only exposure at voxel `v` predicts better adjusted HF+ULF outcome.

The patient-level direct voxel ULF score is:

```text
ULFScore_mean_main_i =
  sum_{v in V_score} X_ULF_only_i(v, phase,tau) * M_ULF(v)
  / n_valid_score_voxels
```

Final prediction:

```text
Y_post_i = alpha
         + delta * ULFScore_mean_main_i
         + beta  * Y_HF_ref_i
         + gamma * DeltaHFScore_i
         + error_i
```

Primary ULF direct voxel settings:

- `tau=200 V/m` primary; `180/220 V/m` sensitivity.
- `Coverage_ULF_tau(v) >= 5`.
- `X_ULF_only` is tau-specific because tau defines ULF active voxels, HF active voxels, overlap exclusion, coverage, and score input.
- Formal permutation/bootstrap is restricted to the primary chronic `tau200/partial_spearman` branch unless the same-day immediate endpoint is explicitly promoted.
- OLS ANCOVA is optional future supplemental analysis and is not run in the current executable analysis.

#### Bilateral Homologous Voxel Exposure

Unlike target-level models, direct voxel-level models require a homologous voxel coordinate system if a shared bilateral map is learned.

The recommended main direct voxel analysis is:

```text
bilateral homologous voxel-pair ANCOVA
```

Use the right seed nucleus as the canonical voxel grid. For each canonical right voxel center:

```text
c_R(v)
```

define the left homologous location as a continuous coordinate using the inverse left-to-right deformation:

```text
c_L(v) = phi_inverse_L_to_R(c_R(v))
```

Do not require the transformed left voxel center to land exactly on a right voxel center. Homology is defined in continuous physical space, not by discrete voxel index matching.

For continuous E-field maps, map the left side into right canonical space using the model-specific left/right transform. The HF direct voxel executable model uses `ea_flip_lr_nonlinear` with Lead-DBS default interpolation, as fixed in `model_summaries/hf_3m_direct_voxel_model.md`.

```text
E_L_to_R_i(v) = transformed left-side exposure on the right canonical grid
```

The patient-level bilateral exposure for voxel `v` is:

```text
X_i(v) = (E_R_i(c_R(v)) + E_L_to_R_i(v)) / 2
```

This gives one value per patient per homologous voxel, keeping the model at:

```text
n = 16
```

and avoiding left/right pseudo-replication.

The default executable HF direct voxel mask is not a paired-membership mask and is not hard-gated by the model-specific anatomical territory. It is defined by the training-fold coverage mask:

```text
Omega_direct = {Coverage(v) >= threshold}
```

Do not introduce a left-to-right paired-mask membership threshold for the HF direct voxel model. Any future paired-mask analysis would be a separate, explicitly labeled sensitivity model rather than the primary executable specification.

#### Coverage Mask

Do not fit direct voxel models in all seed voxels. First define an E-field coverage mask:

```text
Coverage(v) = sum_i 1[X_i(v) > tau]
```

Main threshold:

```text
tau = 0.2 V/mm
```

because `200 V/m = 0.2 V/mm`.

Sensitivity thresholds:

```text
tau = 0.18, 0.20, 0.22 V/mm
```

Generic non-HF preferred coverage rule:

```text
Coverage(v) >= 8
```

meaning at least 50% of patients have suprathreshold exposure at that voxel. This generic rule is not used to generate HF direct voxel results. The HF executable model uses `Coverage(v) >= 5` only and records the 50% rule in its reference-coverage checklist.

```text
Coverage(v) >= 5 or 6
```

Coverage masks must be generated within each training fold for cross-validation. The held-out patient must not contribute to fold-specific coverage mask definition.

#### Estimator

Use residualized ANCOVA or adjusted partial Spearman.

Residualized ANCOVA:

```text
Y_post ~ baseline_covariates
X(v)   ~ baseline_covariates
theta(v) = regression coefficient linking residualized X(v) to residualized Y_post
```

Adjusted partial Spearman:

1. rank-transform `Y_post`, `X(v)`, and covariates;
2. residualize ranked `Y_post` against ranked covariates;
3. residualize ranked `X(v)` against ranked covariates;
4. correlate residuals.

The adjusted partial Spearman version is closer to published voxel sweet-spot mapping, while still accommodating model-specific clinical covariates such as `Y_Preop`, `Y_HF_ref`, and `DeltaHFScore`.

#### Sweet Spot Score

After a direct voxel map `M(v)` is learned, compute patient-level overlap:

```text
SweetSpotScore_i =
  sum_{v in Omega_direct} X_i(v) * M(v)
  / (sum_{v in Omega_direct} X_i(v) + lambda)
```

Then fit the final prediction model:

```text
Y_post_i = alpha
         + delta * SweetSpotScore_i
         + covariates
         + error_i
```

For lower-is-better scales, the expected direction is:

```text
delta < 0
```

because higher sweet spot overlap should predict lower post-treatment score.

#### Nested Validation

Direct voxel-level sweet spot mapping must be evaluated with fully nested leave-one-patient-out cross-validation.

For each held-out patient:

1. define coverage mask using training patients only;
2. fit the voxel map using training patients only;
3. compute training and held-out `SweetSpotScore` from the training-fold voxel map;
4. fit the training-fold prediction model;
5. predict the held-out patient.

The full-cohort map is useful for visualization but is circular for prediction and should not be used to claim out-of-sample performance.

Compare the direct voxel model against a covariate-only baseline:

```text
Y_post ~ covariates
```

Report:

```text
model-specific primary LOOCV statistic
LOOCV Pearson r as a secondary metric when not primary
LOOCV Spearman rho
MAE
RMSE
Q2
permutation P value
```

Use Freedman-Lane permutation for significance testing:

1. fit the covariate-only model;
2. permute residuals at the patient level;
3. reconstruct pseudo-outcomes;
4. rerun the full nested direct voxel pipeline;
5. compare observed `Q2` or `r_LOO` against the permutation distribution.

Suggested permutations:

```text
formal analysis: B = 10000
smoke/exploratory: B = 1000
```

Use seed `42` and compute Monte Carlo permutation P values with the plus-one correction.

Suggested subject-level bootstrap resamples:

```text
formal analysis: B = 10000
smoke/exploratory: B = 1000
```

Use seed `42`. The bootstrap is used to estimate map stability/resampling uncertainty, not as the primary voxel-wise significance test.

#### Direct Voxel Outputs

For the executable HF direct voxel model, the resolved exposure/territory/estimator/permutation/endpoint choices are listed under "Resolved HF/STN settings" in the `HF Direct Voxel Model` subsection above; HF outputs keep the `direct_voxel_HF_*` file names and land under `/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale_slug>/tau*/partial_spearman/`. Optional future OLS outputs would use sibling `ols_ancova/` directories only if explicitly enabled.

For each generic non-HF/ULF direct voxel model, export:

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

The executable HF and ULF direct voxel models are exceptions to this generic legacy list. HF uses `direct_voxel_HF_scores.csv`; ULF uses `direct_voxel_ULF_only_scores.csv`; both follow their model-summary output semantics.

Smoothing is optional and should be light:

```text
FWHM = 1-2 mm
```

Apply smoothing after coefficient estimation, then re-mask to the seed nucleus. Report unsmoothed and smoothed maps as sensitivity outputs.

#### Homologous Mapping QC

Required QC for nonlinear left-to-right homologous voxel mapping:

- Dice overlap between the right seed mask and the left seed mask warped to the right canonical grid.
- Size of right seed mask, warped-left seed mask, and paired mask.
- Inverse-consistency error if forward and inverse deformation fields are available.
- Jacobian positivity check; large regions with `Jacobian <= 0` invalidate the homology mapping.
- Visual overlays of right seed mask, warped-left seed mask, paired mask, warped-left E-field, right E-field, and averaged bilateral exposure.

#### Interpretation Boundary

Direct voxel-level sweet spot maps are local stimulation association maps:

```text
voxel-level: where inside STN/SNr stimulation exposure is associated with outcome
target-level: which connected targets explain or predict that benefit
```

Direct voxel maps are not definitive causal maps. Low-coverage voxels and regions outside the fold-specific coverage mask should not be interpreted.

### Target-Derived Seed Voxel Maps

The main voxel-level visualization is generated by projecting target-level weights back into the stimulated seed nucleus. It is not a separate voxel-wise discovery model.

For the HF model, the seed nucleus is STN. For the ULF add-on gain model, the seed nucleus is SNr. In the A/B notation used in the uploaded modeling notes, `B` corresponds to the added ULF component for ULF-add-on-gain analyses.

The target-level model first estimates target weights:

```text
w_k = benefit-oriented target weight
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

Then the visualization asks:

```text
Within the seed nucleus, which voxels connect preferentially to sweet targets,
and which voxels connect preferentially to sour targets?
```

For each side `h` in `{L,R}`, keep separate seed masks:

```text
Omega_h = same-side STN or SNr seed mask
```

Do not left-right flip these voxel maps. Left seed voxels are projected to left homologous targets, right seed voxels to right homologous targets, using the same target weights `w_k`.

For each seed voxel `v`, side `h`, and target `k`, compute target-specific streamline density:

```text
D_h,k(v) = sum of streamline contributions through voxel v
```

The main contribution can be binary:

```text
a_v,j,h = 1 if streamline j passes through voxel v, otherwise 0
D_h,k(v) = sum_{j in G_h,k} a_v,j,h
```

where `G_h,k` is the same-side streamline set connecting the seed nucleus to target `P_k,h`.

Length-weighted streamline contribution is an optional display sensitivity:

```text
a_v,j,h = length(streamline j inside voxel v)
```

Distance-kernel contribution is exploratory only:

```text
a_v,j,h = exp(-d(v, streamline j)^2 / (2 * sigma^2))
sigma = 0.5-1.5 mm
```

To preserve the equal-within-target model logic, normalize each target density before applying target weights:

```text
Dnorm_h,k(v) = D_h,k(v) / (sum_{u in Omega_h} D_h,k(u) + lambda)
```

or equivalently approximate the denominator with the number of streamlines in `G_h,k`. This prevents high-density targets from dominating the map solely because they have more streamlines.

The raw target-weighted seed voxel map is:

```text
M_raw_h(v) = sum_{k in S} w_k * Dnorm_h,k(v)
```

where `S` is the selected target set from the training fold, for example top 3 sweet and top 2 sour targets.

For display, use a coverage-corrected map:

```text
Coverage_h(v) = sum_{m in K} Dnorm_h,m(v)

M_display_h(v) =
  sum_{k in S} w_k * Dnorm_h,k(v) / (Coverage_h(v) + lambda)
```

Here `K` is the full candidate target set, not only selected targets. `M_display_h(v)` shows whether the local connectivity profile of voxel `v` is biased toward sweet or sour targets after correcting for total tractography coverage.

Generate separate sweet, sour, and net maps:

```text
Sweet_h(v) =
  sum_{k in S} max(w_k, 0) * Dnorm_h,k(v) / (Coverage_h(v) + lambda)

Sour_h(v) =
  sum_{k in S} max(-w_k, 0) * Dnorm_h,k(v) / (Coverage_h(v) + lambda)

Net_h(v) = Sweet_h(v) - Sour_h(v)
```

Minimum visualization outputs for each side:

```text
<seed>_<side>_coverage.nii.gz
<seed>_<side>_sweet.nii.gz
<seed>_<side>_sour.nii.gz
<seed>_<side>_net.nii.gz
<seed>_<side>_stability.nii.gz
```

Display rules:

- show `Net_h(v)` with a diverging color scale centered at zero;
- use warm colors for positive sweet-biased voxels;
- use cool colors for negative sour-biased voxels;
- show coverage alongside the net map;
- make low-coverage voxels transparent or gray;
- display left and right maps separately without flipping.

Recommended coverage thresholds:

```text
Coverage_h(v) above the 20th percentile
```

or:

```text
Coverage_h(v) >= 5 streamlines
```

For individualized DWI maps, additionally require that a voxel has coverage in at least `4` or `5` patients before strong interpretation.

Normative and individualized DWI versions should both be supported:

- `Normative anatomical map`: use normative streamline geometry and normative-derived target weights. This is the clearest main figure because coverage is smoother and complete.
- `Individualized DWI average map`: compute patient-specific seed voxel maps from individualized DWI, warp them to template space, and average them as a consistency figure.

For individualized DWI, the preferred group map is coverage-weighted:

```text
M_ind_group_h(v) =
  sum_i Coverage_ind_i,h(v) * M_ind_i,h(v)
  / (sum_i Coverage_ind_i,h(v) + lambda)
```

If a voxel map is used to compute a patient-level overlap score for prediction, generate the voxel map inside the training fold to avoid circularity:

```text
VoxelScore_i =
  sum_h sum_{v in Omega_h} E_i,h(v) * M_h(v)
  / (sum_h sum_{v in Omega_h} E_i,h(v) * Coverage_h(v) + lambda)
```

In LOOCV, for each held-out patient:

1. learn `w_k` and selected targets `S` using only the training patients;
2. generate fold-specific `M_h^{(-t)}(v)` using training-fold weights;
3. compute the held-out patient's voxel overlap score using `M_h^{(-t)}(v)`;
4. predict the held-out patient's outcome.

The fold maps can also be summarized as a stability map:

```text
MeanMap_h(v) = mean_t M_h^{(-t)}(v)
Stability_h(v) = number of folds with M_h^{(-t)}(v) > 0 / number of folds
```

Interpretation boundary:

```text
M_h(v) is a connectivity-derived sweet/sour seed voxel map.
```

It means the voxel's streamline profile is biased toward beneficial or detrimental targets learned by the target-level model. It should not be described as direct causal evidence that stimulating that voxel alone produces the displayed effect size.

### Whole-Streamline Fiber Filtering

Use whole streamlines from the public connectome or individualized DWI tractography. Do not crop streamlines to STN/SNr internal segments.

For HF and ULF normative connectome fiber-level models, the candidate universe is the full public connectome, not a target-restricted tract set:

```text
HF candidate fiber:
  Coverage_tau(l) = sum_i I[X_HF_i(l) > tau]
  F_candidate_tau = {l: Coverage_tau(l) >= 5}
  tau_primary = 800 V/m

ULF candidate fiber:
  Coverage_ULF_tau(l) = sum_i I[X_ULF_only_i(l,tau) > tau]
  F_candidate_ULF_tau = {l: Coverage_ULF_tau(l) >= 5}
  tau_primary = 800 V/m
```

The streamline exposure value is still sampled from the full stimulation map along the whole streamline:

```text
X_subject,fiber = max exposure along the full streamline
```

The peak may occur near the nucleus edge or outside the strict ROI boundary.

In normative connectome models, individual fibers are the primary fitted units. Target atlases are applied after fitting for endpoint labels, anatomical enrichment, QC, and visualization. In individualized DWI target-level models, individual streamlines remain contribution/QC outputs rather than primary predictors.

### Endpoint-Specific Reporting

For individualized target-level outputs, report each selected or high-ranked target:

- report target label;
- report target atlas source;
- report model class: `early`, `chronic`, `chronic_gain`, or `immediate_gain`;
- report scale;
- report target weight `w_k`;
- report target-level benefit or gain score depending on the model family;
- report left, right, and bilateral connectivity summaries;
- report normative-only, individualized-DWI, or normative-guided-DWI source;
- report whether the effect is sweet or sour.

For normative fiber-level outputs, report selected/high-ranked streamlines directly:

- report connectome name;
- report streamline ID;
- report model class and endpoint;
- report scale;
- report `M_HF(l)` or `M_ULF(l)`;
- report whether it is in the selected sweet or sour fiber set;
- report whether it intersects the connected-region STN ROI, SNr ROI, or both;
- report HCPex endpoint labels;
- report endpoint/anatomical enrichment labels.

## Statistical Plan

### Main Tests

- HF primary normative connectome model: baseline-adjusted partial Spearman between right-canonical fiber-level HF-only 3-month exposure and HF-only 3-month raw score, adjusting for preoperative raw score.
- STN secondary early model: baseline-adjusted partial Spearman or ANCOVA between target-level STN-immediate bilateral connectivity and STN-immediate raw score, adjusting for preoperative score or same-day STN-OFF score when available.
- ULF chronic add-on gain normative connectome model: endpoint-specific fiber-level partial Spearman with `Y_HF_ref` and `DeltaHFScore_chronic` as nuisance covariates, estimating adjusted chronic `M_ULF(l)` and `NetULFFiberScore`.
- ULF immediate add-on gain normative connectome model: endpoint-specific fiber-level partial Spearman with same-day `Y_HF_ref` and `DeltaHFScore_immediate` as nuisance covariates, estimating adjusted immediate `M_ULF(l)` and `NetULFFiberScore`.
- Primary inference is scale-specific; do not combine heterogeneous scales into one primary model.
- For HF and ULF normative fiber-level models, output fiber-wise FDR q-values for QC/display only. For individualized-DWI target-level models, correct multiple comparisons across tested targets within each scale, DWI source, and model class using FDR.
- Use patient-level permutation tests with seed `42` for empirical significance.

### Endpoint Hierarchy

Recommended reporting hierarchy:

- primary HF endpoint: chronic HF-only efficacy model using `Preop -> STN-3m`;
- secondary HF endpoint: early / acute HF-only response model using `Preop -> STN-immediate`, or `STN-OFF same-day -> STN-immediate` when same-day baseline exists;
- optional HF endpoint: chronic adaptation model using `STN-immediate -> STN-3m`;
- primary ULF chronic add-on gain endpoint: adjusted raw HF+ULF 3-month outcome model using `Y_HF_ref` and `DeltaHFScore_chronic`;
- key secondary or explicitly promoted co-primary ULF immediate endpoint: adjusted same-day raw HF+ULF immediate outcome model using same-day `Y_HF_ref` and `DeltaHFScore_immediate`;
- key secondary ULF endpoint: UPDRS-III chronic ULF-addition model to evaluate longer-term motor relevance;
- symptom-specific secondary ULF endpoints: axial UPDRS-III, FOG-Q, KPPS, PDQ-39, MADRS, ADL, SE-ADL, and other available scales using their selected endpoints;
- exploratory cross-scale summaries: map overlap, meta-map, or pooled/global model.

### Cross-Validation

Use leave-one-patient-out cross-validation for `n = 16`.

For each held-out subject:

1. Rebuild the model-specific candidate set using only the remaining subjects.
2. Fit the model-specific voxel, fiber, or target weights using training subjects only.
3. Build the held-out subject's model-specific score using training-fold parameters only.
4. Fit the final training-fold prediction model and predict the held-out subject's outcome.
5. Compare the full model with the appropriate covariate-only or nuisance-only baseline.

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

A secondary global ULF benefit map may be generated only after scale-specific fitting:

```text
GlobalULFWeight = mean_scale z(ULFBenefitWeight_scale)
```

Use equal weights by default. If non-equal weights are used, define them before looking at results and record them in provenance.

### Exploratory Pooled Model

A pooled cross-scale model is allowed only as exploratory support for a global ULF benefit network. It is not the primary localization model.

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
- HF-only negative-control model using ULF exposure to test whether ULF-addition maps reflect general electrode placement quality;
- model-family-matched and, for normative connectomes, connectome-matched HF efficacy-score change instead of a cross-family `DeltaHFScore`;
- minimal-physical-STN-change subgroup after excluding subjects with the largest absolute outcome-independent HF exposure change;
- binary VTA intersection instead of continuous peak exposure;
- interleaving-specific union, overlap, and frequency-weighted exposure summaries;
- local ROI-expanded peak exposure using connected-region STN/SNr primary masks dilated by `2-3 mm`;
- charge-rate proxy using `abs(voltage_V) * pulse_width_us * frequency_Hz`;
- OSS-DBS/PAM pathway activation model when valid outputs exist;
- repeated analyses across dTOR-985, MGH-USC HCP 32, and PPMI 85 connectomes;
- normative fiber, normative-guided individualized DWI, and individualized-DWI-only target-level model comparison.
- direct voxel-level sweet spot mapping for HF-only efficacy and ULF add-on gain using bilateral homologous voxel exposure;
- direct voxel coverage threshold sensitivity with `0.18`, `0.20`, and `0.22 V/mm`;
- direct voxel unsmoothed versus `1-2 mm` smoothed display sensitivity.

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
4. Build STN-alone, combined-HF-component, and combined-ULF-component exposure maps, including interleaving union and overlap maps where needed.
5. Load raw clinical scores and improvement-rate tables.
6. Select endpoint per scale.
7. Build HF and ULF normative fiber-level exposure sidecars for PPMI, MGH, and dTOR; build target-level connectivity matrices only for individualized DWI and explicitly labeled target-level sensitivities.
8. Extract direct voxel exposure matrices, fiber exposure matrices, and secondary target-derived streamline summaries for localization, QC, and visualization.
9. Fit the primary chronic HF-only direct voxel and normative fiber models.
10. Fit secondary HF-only early / acute target models where valid immediate data exist.
11. Fit optional HF chronic adaptation target models when justified by programming changes.
12. Fit endpoint-specific ULF chronic add-on gain direct voxel and normative fiber models with `Y_HF_ref` and `DeltaHFScore_chronic`.
13. Fit endpoint-specific ULF immediate add-on gain direct voxel and normative fiber models with same-day `Y_HF_ref` and `DeltaHFScore_immediate`.
14. Fit sensitivity models, including normative-only and DWI-only variants.
15. Label selected/high-ranked fibers by connected-region STN/SNr masks, endpoint masks, HCPex labels, and enrichment summaries.
16. Generate target-derived seed voxel maps only for target-level individualized DWI models and target-level sensitivities.
17. Run direct voxel-level HF and ULF sweet spot analyses with nested LOOCV and patient-level permutation tests as specified in their model documents.
18. Export CSV/Mat/JSON provenance, voxel/fiber/target weights, patient scores, direct voxel maps, target-derived maps where applicable, and visualization-ready fiber subsets.

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
- `models/hf/chronic/`: primary chronic HF-only normative fiber weights, fiber scores, selected fibers, density maps, and sensitivity outputs.
- `models/hf/early/`: secondary early / acute HF-only target results.
- `models/hf/adaptation/`: optional HF chronic adaptation target results.
- `models/ulf/chronic_gain/`: endpoint-specific chronic ULF direct voxel, normative fiber, and target-level sensitivity results.
- `models/ulf/immediate_gain/`: endpoint-specific immediate ULF direct voxel, normative fiber, and target-level sensitivity results.
- `models/cross_scale/`: map-level similarity metrics and secondary global maps.
- `fiber_maps/hf_normative/`: right canonical HF normative selected-fiber displays, fiber density maps, top 1% sweet and top 0.5% sour streamlines, endpoint/anatomical enrichment, unthresholded landscape maps, FDR display summaries, cross-connectome robustness tables, bootstrap/jitter stability outputs, and plain connected-streamline controls.
- `fiber_maps/ulf_normative/`: right canonical ULF normative selected-fiber displays, ULF-only fiber density maps, top 1% sweet and top 0.5% sour streamlines, HF-overlap exclusion summaries, DeltaHFScore support QC, endpoint/anatomical enrichment, FDR display summaries, cross-connectome robustness tables, and plain connected-streamline controls.
- `voxel_maps/target_derived/ulf/`: left/right target-derived ULF maps only for individualized DWI target-level models or explicitly labeled target-level sensitivities.
- `fiber_maps/loocv/hf_normative/`: fold-specific HF fiber-level weights, held-out `NetFiberScore`, and selected-fiber QC summaries.
- `voxel_maps/loocv/snr/`: fold-specific ULF target-derived maps and held-out voxel overlap scores when ULF voxel scores are used for prediction.
- `voxel_maps/dwi_group/stn/`: individualized-DWI group-average and coverage-weighted STN seed voxel maps.
- `voxel_maps/dwi_group/snr/`: individualized-DWI group-average and coverage-weighted SNr seed voxel maps.
- `direct_voxel/hf/`: executable HF direct voxel outputs under `<scale_slug>/tau*/partial_spearman/`; optional future OLS outputs use sibling `ols_ancova/` directories only if explicitly enabled.
- `direct_voxel/ulf/`: executable ULF direct voxel outputs under `<endpoint_slug>/tau*/partial_spearman/`, including ULF-only coverage, HF-overlap exclusion, DeltaHFScore support QC, scores, LOOCV predictions, and primary-branch permutation/bootstrap outputs.
- `direct_voxel/qc/`: homologous voxel mapping QC, deformation QC, and visual overlay summaries.
- `sensitivity/`: all sensitivity model outputs.
- `visualization/`: selected fiber subsets, sweet/sour target summaries for target-level models, secondary maps, HCPex endpoint summaries.

## Acceptance Checks

- `random_seed` is `42` in all stochastic steps.
- The analysis does not crop VTA/e-field/proxy maps to STN/SNr masks.
- Interleaving stimulation is split into subprograms and is not treated as simultaneous double-cathode stimulation.
- Interleaving outputs include union exposure and overlap exposure when interleaving programs exist.
- Streamlines are whole connectome streamlines, not STN/SNr internal fragments.
- STN/SNr model labels come from `STN-connected regions` and `SNr-connected regions`.
- Non-STN/SNr endpoint labels come from HCPex.
- HF normative connectome primary predictor selection is fiber-level DBS Fiber Filtering, not target-level aggregation.
- ULF normative connectome primary predictor selection is fiber-level DBS Fiber Filtering, not target-level aggregation.
- Target-level individualized-DWI connectivity is computed left and right separately and averaged into one patient-level bilateral feature before modeling.
- The primary model has one row per patient; left and right hemispheres are not treated as independent samples.
- Target-level DWI coverage is checked before individualized-DWI or normative-guided-DWI models are interpreted.
- Target-derived voxel maps for target-level models are generated by back-projecting target weights into the seed nucleus, not by selecting top voxel-wise correlations.
- HF normative connectome display maps are generated from fiber-level weights, selected streamlines, and streamline-density maps, not from HF target weights.
- ULF target-derived voxel maps are generated only for target-level individualized DWI models or explicitly labeled target-level sensitivities.
- Left and right seed voxel maps are generated separately without flipping.
- Voxel visualization includes coverage, sweet, sour, net, and stability maps.
- Any voxel-map overlap score used for prediction is generated inside the training fold, not from all subjects.
- Direct voxel-level sweet spot mapping is marked secondary/exploratory and does not replace the target-level primary model.
- Direct voxel models use bilateral homologous voxel exposure, keeping one value per patient per voxel.
- Nonlinear left/right homology uses model-specific transform rules. The executable HF direct voxel model uses `ea_flip_lr_nonlinear` into the right-hemisphere MNI brainmask candidate grid; older inverse-sampling/trilinear descriptions are generic/non-HF context only.
- Direct voxel coverage masks are defined within training folds for LOOCV.
- Direct voxel models are compared against covariate-only models and evaluated with patient-level permutation tests.
- The primary HF model uses raw STN-3m score adjusted for raw preoperative score, not percent improvement as the main outcome.
- HF-immediate models are marked secondary and use same-day STN-OFF baseline when available.
- ULF chronic add-on gain models include both `Y_HF_ref` and `DeltaHFScore_chronic`.
- ULF immediate add-on gain models include same-day `Y_HF_ref` and `DeltaHFScore_immediate`.
- ULF results include model-specific coverage summaries, HF-overlap exclusion summaries, and DeltaHFScore support QC; low-coverage targets, voxels, regions, or streamlines are not strongly interpreted.
- PPMI, MGH, and dTOR all produce figure-grade observed HF normative fiber outputs; dTOR additionally carries formal permutation/bootstrap and jitter QC.
- PPMI, MGH, and dTOR all produce figure-grade observed ULF normative fiber outputs; dTOR additionally carries formal permutation/bootstrap for the primary branch and model-specific stability outputs.
- dTOR and MGH access is chunked and memory-safe.
- `my_helper/fiber/stnsnr` contains only pipeline scripts, not core helper functions.
- scale-specific maps are generated before any cross-scale summary map.
- any pooled cross-scale model is marked exploratory.

## Interpretation Rules

- Primary HF normative connectome results should be described as chronic HF-only therapeutic fiber-level DBS Fiber Filtering profiles.
- HF fiber and density maps should be described as normative streamline association maps based on fiber-level HF efficacy weights.
- HF-immediate results should be described as early HF-only target connectivity response models, or acute STN stimulation response models only when same-day STN-OFF baseline is used.
- HF adaptation results should be described as secondary programming/adaptation analyses, not as the main HF efficacy model.
- ULF add-on gain results should be described by model family: direct voxel local stimulation association, normative connectome fiber-level DBS Fiber Filtering association, or individualized DWI target-level sensitivity, all adjusted for `Y_HF_ref` and model-family-matched `DeltaHFScore`.
- ULF chronic add-on gain normative connectome results should be described as adjusted fiber-level associations with `STN+SNr 3m` outcome.
- ULF immediate add-on gain results should be described as adjusted same-day HF-state associations with `STN+SNr immediate` outcome.
- Residualized ULF results should be described as HF-model-adjusted ULF-associated residual benefit, not as definitive pure SNr causal effect.
- ULF maps should not be described as pure causal maps showing that every patient should be stimulated at a given ULF location.
- Target-derived voxel maps should be described as connectivity-derived candidate sweet/sour seed zones, not direct voxel-wise causal efficacy maps.
- Positive target-derived seed voxels indicate connectivity profiles biased toward sweet targets; negative voxels indicate connectivity profiles biased toward sour targets.
- Low-coverage seed voxels should be shown as transparent or gray and should not receive strong anatomical interpretation.
- Direct voxel-level maps should be described as local stimulation association maps, not network mechanism maps.
- Direct voxel-level maps should not be interpreted outside their coverage masks or as definitive causal maps.
- In direct voxel maps, the displayed left/right maps are spatial expressions of one homologous voxel model unless a side-specific sensitivity model is explicitly reported.
- Interleaving union maps should be described as exposure across an interleaving cycle, not as one simultaneous continuous electric field.
- Interleaving overlap maps should be described as tissue or fibers exposed to both pulse trains.
- Scale-specific direct voxel and normative fiber models are the primary non-individualized results for symptom-specific inference; individualized DWI remains target-level unless its model document is revised.
- Global or pooled target maps are secondary/exploratory summaries of cross-scale convergence.
- Fiber subsets are primary selected/display outputs for normative fiber models and explanatory outputs within selected targets for individualized target-level models.
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
