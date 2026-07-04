# HF-Only 3m Normative Connectome Fiber-Level Model

## Research Question

Which normative connectome streamlines directly touched by HF stimulation show fiber-level DBS Fiber Filtering associations with better 3-month HF-only clinical outcome?

This is a normative connectome **fiber-level** model. It follows the DBS Fiber Filtering logic used in the reference Nature papers: individual streamlines are the primary modeling units, while target atlases are used only for anatomical labeling, stratified QC, display grouping, and interpretation. The model is not a target-level seed-target aggregation model.

Frequency definitions:

```text
HF  = high-frequency stimulation component, frequency_Hz >= 100
ULF = ultra-low-frequency stimulation component, frequency_Hz <= 50
```

## Endpoint

Primary endpoint:

```text
Y_post = raw HF-only 3-month clinical score
```

Primary covariate:

```text
Y_base = raw preoperative clinical score
```

Default first-pass scales:

```text
MDS-UPDRS III score (STN, 3 m)
MDS-UPDRS III axial score (STN, 3 m)
```

Raw post and baseline scores come from:

```text
/Users/mojackhu/Research/STNSNr/summary/cohort/subj/subject_effect_origin.xlsx
```

Rows are joined by `ID` (`SNr003`, `SNr006`, etc.). The improvement-rate table is not used by this model. Scale direction is read from the shared direction table; unknown scales must explicitly define whether higher or lower values are better.

## Inputs

- HF-only raw `sim-efield` maps from the `3m/STN` condition. Use `sim-efield`, not `sim-efieldgauss`, in `V/m`.
- Public Lead-DBS dMRI structural connectomes:

  ```text
  PPMI 85 (Ewert 2017)                 smoke
  MGH-USC HCP 32 (Horn 2017)           intermediate
  dTOR-985 Full (Elias 2024)           main
  ```

- Right canonical connectome fibers loaded from each connectome `data.mat`.
- Left/right homology transform through `ea_flip_lr_nonlinear`.
- Target and anatomical atlases for labeling/QC only:

  ```text
  STNSNr-connected regions
  STN-connected regions
  SNr-connected regions
  Custom STN/SNr overlays
  ```

- OSS-DBS environment for pathway activation sensitivity:

  ```text
  conda env: ossdbsv2
  ```

The pipeline performs only minimum e-field availability checks: required path exists, subject/side/condition match is unique, file is raw `sim-efield`, and units are recorded as `V/m`. Missing or multiply matched e-fields fail the scale/run. E-fields are not automatically recomputed.

## Feature Construction

The candidate universe is the full public connectome, not target-restricted seed-target tracts.

Right canonical fiber model:

```text
canonical side = right
X_R_i(l)      = peak raw sim-efield along right canonical fiber l
X_L_to_R_i(l) = peak left e-field after ea_flip_lr_nonlinear along the same right canonical fiber l
X_HF_i(l)     = (X_R_i(l) + X_L_to_R_i(l)) / 2
```

Alternating same-side HF subprogram e-fields are combined by voxel-wise maximum before fiber sampling. Exposure is not scaled by frequency or pulse width.

Primary candidate rule:

```text
tau_primary = 800 V/m
tau_sensitivity = 1500 V/m
Coverage_tau(l) = sum_i I[X_HF_i(l) > tau]
F_candidate_tau = {l: Coverage_tau(l) >= 5}
```

`Coverage>=5` is the executable rule. The lower `>0.5% E-fields` criterion in the Nature Communications tract-library paper is documented in the reference checklist, but for this `n=16` cohort it would be effectively too permissive. The current implementation therefore uses `Coverage>=5` for stability.

The dTOR connectome is large (`idx` has about 11.82 million fibers). All dTOR exposure and candidate calculations must be chunked. Any implementation that loads the complete dTOR `fibers` matrix into memory is invalid.

## Statistical Model

### Primary Estimator: Baseline-Adjusted Partial Spearman

For each candidate fiber `l`, use rank-residual partial Spearman with average ranks for ties:

```text
rho_HF(l) =
  corr(
    resid(rank(Y_post_i)  ~ rank(Y_base_i)),
    resid(rank(X_HF_i(l)) ~ rank(Y_base_i))
  )
```

Degenerate fibers with zero exposure variance, zero rank variance, or zero residualized exposure variance are assigned `rho_HF(l)=NaN` and excluded from scoring.

Benefit-oriented fiber weight:

```text
M_HF(l) = -rho_HF(l)   for lower-is-better scales
M_HF(l) =  rho_HF(l)   for higher-is-better scales
```

Positive `M_HF(l)` means sweet or benefit-associated. Negative `M_HF(l)` means sour or worse-outcome-associated.

FDR q-values are computed for QC/display only. They are not used to filter the primary model or to define the scoring fiber set.

### Main Patient Score

The primary patient-level score is sweet-only weighted peak 5% mean:

```text
sweet fibers = {l in F_candidate_tau: M_HF(l) > 0}
weighted_l_i = X_HF_i(l) * M_HF(l)

HFFiberScore_top5_mean_i =
  mean(top 5% largest weighted_l_i among sweet fibers)
```

If a full-sample map or LOOCV training fold has no sweet fibers, that branch/fold fails QC. If sweet fibers exist but a patient has zero exposure to them, `HFFiberScore_top5_mean_i = 0`.

This score is intentionally closer to the Nature Neuroscience weighted peak Fiber R score than to a target-level aggregate. It uses mean rather than sum so that scores remain more comparable across fold-specific candidate sets.

The previously discussed total fiber exposure score is retained only as a documented concept and is not computed by the current executable analysis:

```text
HFFiberScore_sum_descriptive_i =
  sum_l X_HF_i(l) * M_HF(l)
```

Final prediction model:

```text
Y_post_i = alpha
         + delta * HFFiberScore_top5_mean_i
         + beta  * Y_base_i
         + error_i
```

The prediction model is fit on the raw post-score scale. The primary validation statistic is LOOCV Spearman rho between held-out predictions and held-out raw outcomes.

## Validation And Sensitivity

- Primary validation is leave-one-patient-out cross-validation.
- In each fold, rebuild `F_candidate_tau`, fit fiber weights, compute training and held-out `HFFiberScore_top5_mean`, and fit the final prediction model using training patients only.
- Compare against the covariate-only baseline `Y_post ~ Y_base`.
- Primary metrics: LOOCV Spearman rho and plus-one permutation P value.
- Secondary metrics: LOOCV Pearson `r`, MAE, RMSE, and `Q2`.
- Formal Freedman-Lane permutation uses `B=10000`, seed `42`, and is restricted to the primary dTOR peak-E-field branch.
- Smoke permutation uses `B=1000`, seed `42`.
- Subject-level bootstrap uses `B=10000`, seed `42`, and is restricted to the primary dTOR peak-E-field branch.

Reference sensitivities:

```text
1500 V/m candidate threshold sensitivity
top 1% positive fibers for display
top 1% sour fibers for display
top1500 positive / top500 negative fiber-score sensitivity for PPMI, MGH, and dTOR
OSS-DBS all-candidate sensitivity for PPMI, MGH, and dTOR
2 mm FWHM spatial jitter QC for dTOR selected/display fibers only
```

The Nature paper 5-fold/10-fold CV settings are documented in the reference checklist only. They are not generated for the current `n=16` execution; LOOCV is the executable validation design.

## OSS-DBS Sensitivity

OSS-DBS is generated in the `ossdbsv2` Conda environment for all candidate fibers in PPMI, MGH, and dTOR.

The OSS branch replaces peak E-field exposure with pathway/axon activation:

```text
X_HF_OSS_i(l) = OSS-DBS activation value for fiber l under subject i HF stimulation
```

The OSS branch runs the same fiber-wise estimator, sweet-only top 5% scoring, and LOOCV prediction workflow. It runs smoke permutation only:

```text
B = 1000
seed = 42
```

Formal `B=10000` permutation/bootstrap is not required for the OSS branch.

## Outputs

Output root:

```text
/Volumes/VAL/STNSNr/summary/normative_connectome_fiber/hf/<connectome_slug>/<scale_slug>/<branch>/
```

Branches:

```text
peak_efield_tau800_primary
peak_efield_tau1500_sensitivity
top1500_top500_sensitivity
ossdbs_activation_sensitivity
```

Required outputs per branch:

```text
normative_HF_fiber_weights.csv
normative_HF_fiber_scores.csv
normative_HF_fiber_loocv_predictions.csv
normative_HF_fiber_permutation_summary.csv
normative_HF_fiber_mapping_qc.json
normative_HF_fiber_generation_manifest.json
normative_HF_fiber_display_top1_positive.tck
normative_HF_fiber_display_top1_positive.mat
normative_HF_fiber_display_top1_sour.tck
normative_HF_fiber_display_top1_sour.mat
normative_HF_fiber_density_map.nii.gz
```

Primary dTOR peak-E-field branch additionally writes:

```text
normative_HF_fiber_bootstrap_se.csv
normative_HF_fiber_jitter_summary.csv
```

OSS branch additionally writes:

```text
normative_HF_fiber_oss_activation_matrix_summary.csv
normative_HF_fiber_oss_loocv_predictions.csv
normative_HF_fiber_oss_permutation_summary.csv
```

`normative_HF_fiber_weights.csv` includes at least:

```text
connectome
fiber_id
tau_v_per_m
coverage
rho_HF
p_uncorrected
q_fdr
M_HF
direction_class
target_labels_for_qc
is_top1_positive_display
is_top1_sour_display
is_top1500_positive
is_top500_negative
```

`normative_HF_fiber_scores.csv` includes:

```text
subject_id
score_map_source
connectome
branch
HFFiberScore_top5_mean
n_candidate_fibers
n_sweet_fibers
n_top5_fibers
is_primary_score
```

`normative_HF_fiber_mapping_qc.json` records candidate counts, coverage distribution, degenerate fiber counts, empty-fold failures, FDR method, target-label summaries, chunking parameters, memory use summaries, and OSS-DBS status.

## Visualization

Target atlases are used after fiber modeling to label and summarize fibers, not to define primary predictors.

Display outputs:

- top 1% positive fibers by `M_HF(l)` for sweet streamline visualization;
- top 1% sour fibers by negative `M_HF(l)` for avoidance/sour visualization;
- streamline density maps for selected/display fibers;
- target-label summary tables showing which atlas targets are traversed or contacted by selected fibers;
- STN/SNr and STNSNrplus overlays as anatomical context only.

No display fiber subset is a statistical significance map. FDR q-values may be shown in QC tables, but the display rule is based on rank/percentile and direction stability rather than q-value thresholding.

## Interpretation Boundary

This model estimates normative fiber-level HF stimulation associations. It is closer to DBS Fiber Filtering than to seed-target target-level modeling, but it still uses population connectomes and therefore does not prove patient-specific axonal causality.

The model should be interpreted as:

```text
HF stimulation appears more beneficial when it strongly modulates this normative streamline profile.
```

It should not be interpreted as:

```text
Every displayed streamline is a proven causal tract in every patient.
```

The primary claim requires cross-connectome consistency, dTOR primary performance, and transparent reporting of PPMI/MGH sensitivity results.
