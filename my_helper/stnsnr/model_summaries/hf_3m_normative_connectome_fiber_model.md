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
E_R_i(l)      = peak raw sim-efield along right canonical fiber l
E_L_to_R_i(l) = peak left e-field after ea_flip_lr_nonlinear along the same right canonical fiber l
X_HF_i(l)     = (E_R_i(l) + E_L_to_R_i(l)) / 2
```

The executable model uses a right-canonical streamline feature space. Left-sided stimulation is flipped into the right canonical space and sampled along the same right-sided streamline features. Bilateral E-field information is therefore used, but the streamline feature set itself is one-sided/canonical rather than a true bilateral streamline set.

Alternating same-side HF subprogram e-fields are combined by voxel-wise maximum before fiber sampling. Exposure is not scaled by frequency or pulse width.

Primary candidate rule:

```text
tau_primary = 800 V/m
tau_sensitivity = 1500 V/m
Coverage_tau(l) = sum_i I[X_HF_i(l) > tau]
F_candidate_tau = {l: Coverage_tau(l) >= 5}
```

The fiber model uses the same coverage logic as the HF direct voxel model: coverage is counted over patient-level averaged right-canonical exposure rows. The averaged patient-level `X_HF_i(l)` is the exposure used for candidate definition, fiber-wise association, scoring, LOOCV, and prediction.

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

The primary patient-level score is a net sweet-minus-sour peak score. Within each full-sample map or LOOCV training fold, define benefit-oriented fiber weights:

```text
M_HF(l) = -rho_HF(l)   for lower-is-better scales
M_HF(l) =  rho_HF(l)   for higher-is-better scales
```

Positive/sweet selected fibers:

```text
F+ = top 1% fibers with largest positive M_HF(l)
```

Negative/sour selected fibers:

```text
F- = top 0.5% fibers with most negative M_HF(l)
```

For each patient `i`:

```text
SweetWeighted_i(l) = X_HF_i(l) * M_HF(l),      l in F+
SourWeighted_i(l)  = X_HF_i(l) * [-M_HF(l)],   l in F-

SweetPeak5_i = mean of top 5% largest SweetWeighted_i(l)
SourPeak5_i  = mean of top 5% largest SourWeighted_i(l)

NetFiberScore_i = SweetPeak5_i - SourPeak5_i
```

`F+` and `F-` are selected within `F_candidate_tau`, excluding NaN or degenerate fibers. Percentile counts use `ceil(percent * n)` with at least 1 fiber when the corresponding positive or negative pool is non-empty.

If `F+` is empty, `SweetPeak5_i = 0`. If `F-` is empty, `SourPeak5_i = 0`. If a selected set is non-empty but patient exposure to all selected fibers is zero, the corresponding peak score is `0`.

This score is intentionally closer to the Nature Neuroscience weighted peak Fiber R score than to a target-level aggregate. It uses peak means rather than sums so that scores remain more comparable across fold-specific selected fiber sets while explicitly penalizing sour fiber engagement.

The previously discussed total fiber exposure score is not computed by the current executable analysis.

Final prediction model:

```text
Y_post_i = alpha
         + delta * NetFiberScore_i
         + beta  * Y_base_i
         + error_i
```

The prediction model is fit on the raw post-score scale. The primary validation statistic is LOOCV Spearman rho between held-out predictions and held-out raw outcomes.

## Validation And Sensitivity

- Primary validation is leave-one-patient-out cross-validation.
- In each fold, rebuild `F_candidate_tau`, fit `M_HF(l)`, select fold-specific `F+` and `F-`, compute training and held-out `SweetPeak5`, `SourPeak5`, and `NetFiberScore`, and fit the final prediction model using training patients only.
- Compare against the covariate-only baseline `Y_post ~ Y_base`.
- Primary metrics: LOOCV Spearman rho and plus-one permutation P value.
- Secondary metrics: LOOCV Pearson `r`, MAE, RMSE, and `Q2`.
- Formal Freedman-Lane permutation uses `B=10000`, seed `42`, and is restricted to the primary dTOR peak-E-field branch.
- Smoke permutation uses `B=1000`, seed `42`.
- Subject-level bootstrap uses `B=10000`, seed `42`, and is restricted to the primary dTOR peak-E-field branch.

Reference sensitivities:

```text
1500 V/m candidate threshold sensitivity with Coverage>=5
top 1% positive fibers for display
top 0.5% sour fibers for display
top1500 positive / top500 negative fiber-score sensitivity for PPMI, MGH, and dTOR
OSS-DBS all-candidate sensitivity for PPMI, MGH, and dTOR
jitter_level_1_selected_display for dTOR selected/display fibers
jitter_level_2_model_density for dTOR model-density robustness
plain_connected_streamline_control for PPMI, MGH, and dTOR
```

The Nature paper 5-fold/10-fold CV settings are documented in the reference checklist only. They are not generated for the current `n=16` execution; LOOCV is the executable validation design.

PPMI, MGH, and dTOR must all produce figure-grade observed outputs: full-sample maps, LOOCV predictions, score CSVs, selected sweet/sour fibers, density maps, candidate and coverage summaries, and label summaries. dTOR additionally carries formal `B=10000` permutation, `B=10000` bootstrap, and jitter QC.

## OSS-DBS Sensitivity

OSS-DBS is generated in the `ossdbsv2` Conda environment for all candidate fibers in PPMI, MGH, and dTOR.

The OSS branch replaces peak E-field exposure with pathway/axon activation:

```text
X_HF_OSS_i(l) = OSS-DBS activation value for fiber l under subject i HF stimulation
```

The OSS branch runs the same fiber-wise estimator, net sweet-minus-sour peak scoring, and LOOCV prediction workflow. It runs smoke permutation only:

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
plain_connected_streamline_control
```

Required observed outputs per branch:

```text
normative_HF_fiber_weights.csv
normative_HF_fiber_scores.csv
normative_HF_fiber_loocv_predictions.csv
normative_HF_fiber_mapping_qc.json
normative_HF_fiber_generation_manifest.json
normative_HF_fiber_display_top1_positive.tck
normative_HF_fiber_display_top1_positive.mat
normative_HF_fiber_display_top0p5_sour.tck
normative_HF_fiber_display_top0p5_sour.mat
normative_HF_fiber_density_map.nii.gz
normative_HF_fiber_endpoint_labels.csv
normative_HF_fiber_cortical_endpoint_summary.csv
normative_HF_fiber_subcortical_crossing_summary.csv
normative_HF_fiber_label_enrichment.csv
normative_HF_fiber_unthresholded_weighted_density.nii.gz
normative_HF_fiber_positive_weighted_density.nii.gz
normative_HF_fiber_negative_weighted_density.nii.gz
normative_HF_fiber_neglogp_density.nii.gz
normative_HF_fiber_qvalue_summary.csv
normative_HF_fiber_top_percentile_sweep_summary.csv
fdr_summary_by_scale.csv
fdr_thresholded_positive_density_q05.nii.gz
fdr_thresholded_negative_density_q05.nii.gz
fdr_thresholded_positive_density_q10.nii.gz
fdr_thresholded_negative_density_q10.nii.gz
```

Primary dTOR peak-E-field branch additionally writes:

```text
normative_HF_fiber_permutation_summary.csv
normative_HF_fiber_bootstrap_se.csv
normative_HF_fiber_bootstrap_selection_frequency.csv
normative_HF_fiber_bootstrap_sign_stability.csv
normative_HF_fiber_fold_selection_frequency.csv
normative_HF_fiber_fold_sign_stability.csv
normative_HF_fiber_stability_density_map.nii.gz
normative_HF_fiber_jitter_summary.csv
normative_HF_fiber_jitter_model_similarity.csv
normative_HF_fiber_jitter_selected_overlap.csv
normative_HF_fiber_jitter_density_correlation.csv
normative_HF_fiber_jitter_example_density_maps/
```

PPMI and MGH observed branches do not require formal permutation/bootstrap outputs. Their manifests record `resampling_status = observed_only_connectome_robustness`.

OSS branch additionally writes:

```text
normative_HF_fiber_oss_activation_matrix_summary.csv
normative_HF_fiber_oss_loocv_predictions.csv
normative_HF_fiber_oss_permutation_summary.csv
```

Plain connected-streamline control branch writes:

```text
normative_HF_plain_touched_fibers.tck
normative_HF_plain_touched_density_map.nii.gz
normative_HF_plain_touched_summary.csv
normative_HF_plain_connected_model_comparison.csv
```

Cross-connectome figure summaries are written at the HF normative connectome fiber summary root:

```text
connectome_scale_performance_summary.csv
connectome_scale_overlap_summary.csv
connectome_density_correlation_summary.csv
connectome_selected_label_summary.csv
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
is_top0p5_sour_display
is_top1500_positive
is_top500_negative
```

`fdr_summary_by_scale.csv` includes at least:

```text
scale
connectome
branch
n_q05_positive
n_q05_negative
n_q10_positive
n_q10_negative
top1_positive_overlap_q_ranked
top0p5_sour_overlap_q_ranked
```

`normative_HF_fiber_scores.csv` includes:

```text
subject_id
score_map_source
connectome
branch
SweetPeak5
SourPeak5
NetFiberScore
n_candidate_fibers
n_sweet_selected_fibers
n_sour_selected_fibers
n_sweet_peak_fibers
n_sour_peak_fibers
is_primary_score
```

`normative_HF_fiber_mapping_qc.json` records candidate counts, coverage distribution, degenerate fiber counts, empty-fold failures, FDR method, target-label summaries, chunking parameters, memory use summaries, and OSS-DBS status.

`normative_HF_fiber_endpoint_labels.csv` stores per-fiber endpoint and crossing labels from cortical, subcortical, and STN/SNr territory atlases. Endpoint labels support anatomical enrichment, cortical-origin summaries, and figure annotation only; they do not define the primary candidate universe or scoring set.

`normative_HF_fiber_label_enrichment.csv` compares selected sweet/sour fibers against the plain touched-streamline background, so outcome-filtered fibers can be interpreted against non-outcome-weighted stimulation-connectivity density.

### Plain Connected-Streamline Control

The plain control intentionally does not use clinical outcome, `rho_HF(l)`, `M_HF(l)`, or sweet/sour weights. It asks which normative streamlines are touched by HF stimulation before outcome filtering:

```text
Touched_i(l) = I[X_HF_i(l) > tau]
PlainCoverage(l) = sum_i Touched_i(l)
PlainDensityMap = streamline density of all touched fibers
```

Patient-level plain scores:

```text
PlainTouchedCount_i = sum_l Touched_i(l)
PlainExposureSum_i  = sum_l X_HF_i(l)
PlainExposureTop5_i = mean top 5% X_HF_i(l) among touched fibers
```

Model comparisons:

```text
Y_post ~ Y_base
Y_post ~ PlainExposureTop5 + Y_base
Y_post ~ NetFiberScore + Y_base
Y_post ~ NetFiberScore + PlainExposureTop5 + Y_base
```

The joint `NetFiberScore + PlainExposureTop5` model is QC only for this `n=16` cohort. It tests whether the outcome-filtered fiber profile adds information beyond stimulation burden, lead placement, and connectome density.

## Visualization

Target atlases are used after fiber modeling to label and summarize fibers, not to define primary predictors.

Display outputs:

- top 1% positive fibers by `M_HF(l)` for sweet streamline visualization;
- top 0.5% sour fibers by negative `M_HF(l)` for avoidance/sour visualization;
- streamline density maps for selected/display fibers;
- unthresholded weighted-density maps showing the full fiber landscape without percentile thresholding;
- `-log(P)` density maps and q-value summaries for statistical-certainty display;
- target-label, cortical endpoint, and subcortical crossing summary tables showing which atlas territories are traversed or contacted by selected fibers;
- plain touched-streamline density maps as non-outcome-weighted stimulation-connectivity controls;
- STN/SNr and STNSNrplus overlays as anatomical context only.

No display fiber subset is the primary statistical significance map. FDR q-values and q-thresholded density maps are generated for QC/display transparency, but they do not filter the primary model, define `F+`/`F-`, or enter `NetFiberScore`.

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

## Execution Efficiency

This section defines implementation-level rules to increase project-level computational efficiency for the HF normative connectome fiber analysis. These rules change only how computations are scheduled, cached, chunked, vectorized, and written to disk. They do not change the statistical estimands, validation design, output semantics, file naming, or interpretation of any `normative_HF_fiber_*` output.

The optimized implementation must preserve the logical full-process semantics described above. LOOCV training folds still define their own `F_candidate_tau`, fiber-wise maps, selected `F+`/`F-`, `SweetPeak5`, `SourPeak5`, `NetFiberScore`, and held-out predictions. Formal Freedman-Lane permutation and subject-level bootstrap still use `B=10000` and seed `42` for the primary dTOR peak-E-field branch. Smoke runs still use `B=1000`. The optimized implementation may reuse mathematically invariant cached subcomputations, but it must not use full-sample ranks, full-sample training masks, approximate ranks, adaptive early stopping, changed thresholds, changed estimators, changed selected-fiber percentages, or reduced formal resampling counts to gain speed.

### Equivalence Contract

The following quantities are part of the executable statistical definition and must remain unchanged:

```text
connectome order = PPMI observed figure-grade, MGH observed figure-grade, dTOR primary
canonical side = right
primary exposure = peak raw sim-efield along each normative fiber
tau_primary = 800 V/m
tau_sensitivity = 1500 V/m
Coverage>=5 counted over patient-level averaged right-canonical exposure rows
LOOCV patient split
primary estimator = baseline-adjusted partial Spearman
primary score = NetFiberScore
F+ = top 1% positive M_HF(l)
F- = top 0.5% most negative M_HF(l)
SweetPeak5/SourPeak5 = mean top 5% patient-specific weighted selected fibers
formal permutation B = 10000 for primary dTOR peak-E-field branch
formal bootstrap B = 10000 for primary dTOR peak-E-field branch
OSS-DBS permutation = smoke only, B = 1000
seed = 42
primary permutation statistic = LOOCV Spearman rho
```

Numerical reductions should use `float64` where feasible. Stored large exposure matrices may use `float32`; final CSV summaries must record the dtype used for each stage. Existing degenerate-fiber and NaN rules remain unchanged.

### Connectome Sidecar Cache

Formal runs must write memmap-friendly fiber-major sidecar files for Python postprocessing. PPMI and MGH may use single arrays when feasible:

```text
X_float32_fiber_major.npy       # shape = fiber x subject, averaged X_HF
S800_bool.npy                   # X_HF > 800 V/m
S1500_bool.npy                  # X_HF > 1500 V/m
fiber_id.npy
candidate_fiber_metadata.json
```

dTOR must use chunked sidecars. Loading the complete dTOR `fibers` matrix or all dTOR exposure values into memory is invalid:

```text
chunks/
  X_float32_fiber_major_chunk-000001.npy
  S800_bool_chunk-000001.npy
  S1500_bool_chunk-000001.npy
  fiber_id_chunk-000001.npy
fiber_chunk_manifest.json
candidate_fiber_metadata.json
```

The sidecar metadata must record subject order, fiber order, connectome slug, chunk size, dtype, array shape, memory layout, source connectome path, source hash when available, sidecar creation time, software version, and whether the branch uses peak E-field or OSS-DBS activation values.

### Coverage And Fold Candidate Cache

For each tau, precompute suprathreshold indicators and coverage by chunk:

```text
S_tau(l, i) = I[X_HF_i(l) > tau]
Coverage_tau_all(l) = sum_i S_tau(l, i)
```

For LOOCV fold `h`, derive training-fold coverage by subtraction:

```text
Coverage_tau_fold_h(l) =
  Coverage_tau_all(l) - S_tau(l, h)

F_candidate_tau_fold_h =
  {l : Coverage_tau_fold_h(l) >= 5}
```

The held-out patient therefore still does not contribute to the fold-specific candidate set, but the set is computed by chunked vectorized subtraction rather than rescanning streamlines or e-field images.

### Vectorized Fiber-Wise Partial Spearman

The primary fiber map must use a chunked vectorized rank-residual partial Spearman kernel.

For each training fold, ranks must be computed within the training set only. Full-sample ranks are prohibited for LOOCV map fitting, permutation map fitting, bootstrap maps, and OSS sensitivity. For each fiber chunk, compute residualized ranked exposure, residualized ranked outcome, and `rho_HF(l)` using vectorized reductions over subjects. Degenerate fibers with zero exposure variance, zero rank variance, or zero residualized exposure variance keep the existing NaN rule and are excluded from selected-fiber sets and scoring.

### NetFiberScore Computation

The direct voxel linear score operator must not be copied to this model. `NetFiberScore` contains patient-specific top-5% peak operations over selected `F+` and `F-`, so it is not a simple linear matrix product.

For observed maps and each permutation/bootstrap fold, the implementation may cache outcome-independent exposure chunks and coverage arrays, but it must recompute the outcome-dependent pieces:

```text
M_HF(l)
F+
F-
SweetWeighted_i(l)
SourWeighted_i(l)
SweetPeak5_i
SourPeak5_i
NetFiberScore_i
```

Peak selection should be implemented by streaming top-k reducers over selected fiber chunks. Formal runs must not materialize all selected dTOR fibers in memory when a streaming top-k reducer is sufficient.

### Permutation And Bootstrap Efficiency

Freedman-Lane permutation may reuse fold-specific exposure sidecars, `S_tau` arrays, coverage subtraction, subject order, baseline ranks, and chunk metadata. For each reconstructed `Y*`, it must refit the fiber-wise association, reselect `F+`/`F-`, recompute `NetFiberScore`, and rerun the LOOCV prediction statistic.

Subject-level bootstrap remains a full-process map stability analysis for the primary dTOR peak-E-field branch. For each bootstrap resample, represent sampled patients by subject counts:

```text
w_i = number of times subject i appears in the bootstrap sample

Coverage_tau_boot(l) =
  sum_i w_i * I[X_HF_i(l) > tau]
```

Ranks for `Y_post`, `Y_base`, and `X_HF(l)` must still be computed within the expanded bootstrap resample or an exactly equivalent weighted-resample representation. Full-sample ranks are prohibited. Bootstrap summaries should be accumulated with streaming finite-count updates and must not store `B=10000` complete fiber-weight tables.

### OSS-DBS Sensitivity Efficiency

OSS-DBS sensitivity uses the same sidecar and chunking rules, replacing peak E-field exposure with pathway/axon activation values. OSS activation matrices should be written as all-candidate, connectome-specific sidecars with chunk manifests. OSS runs generate LOOCV and smoke permutation only:

```text
B = 1000
seed = 42
```

Formal `B=10000` permutation/bootstrap remains restricted to the primary dTOR peak-E-field branch.

### Intermediate File Policy

Formal loops must not write per-fold, per-permutation, or per-bootstrap full fiber-weight tables unless a debug flag is explicitly enabled. dTOR display outputs should be limited to selected/display fibers and density maps:

```text
top 1% positive fibers
top 0.5% sour fibers
top1500 positive / top500 negative sensitivity fibers
downsampled representative unthresholded landscape fibers when explicitly requested
streamline density maps
plain touched-streamline density maps
FDR-thresholded density maps
target-label QC summaries
```

Workers must not concurrently append to shared CSV or JSON files. Workers should return structured block results to the main process, and the main process writes final CSV/JSON outputs atomically.

### Runtime Profile

`normative_HF_fiber_generation_manifest.json` should include a runtime profile:

```json
{
  "runtime_profile": {
    "connectome_slug": null,
    "branch": null,
    "preprocess_s": null,
    "sidecar_write_s": null,
    "load_sidecar_s": null,
    "observed_loocv_s": null,
    "permutation_s": null,
    "bootstrap_s": null,
    "oss_activation_s": null,
    "display_qc_s": null,
    "n_fibers_total": null,
    "n_fibers_candidate_tau800_mean": null,
    "n_fibers_candidate_tau800_min": null,
    "n_fibers_candidate_tau800_max": null,
    "coverage_tau800_summary": null,
    "coverage_tau1500_summary": null,
    "n_chunks": null,
    "chunk_size": null,
    "python_jobs": null,
    "blas_threads": null,
    "fiber_major_sidecars": [],
    "streaming_topk_enabled": null,
    "bootstrap_finite_count_summary": null
  }
}
```

### Equivalence And Regression Tests

Implementation should include a small deterministic equivalence test before formal runs.

For a small fiber subset and small resampling count:

```text
B_perm = 20
B_boot = 20
n_fiber_subset = 1000 to 10000
seed = 42
```

Compare brute-force and optimized implementations for:

```text
fold-specific F_candidate_tau
Coverage_tau
partial Spearman rho_HF(l)
benefit-oriented M_HF(l)
F+ and F-
SweetPeak5
SourPeak5
NetFiberScore
LOOCV held-out predictions
LOOCV Spearman rho
permutation null statistics
bootstrap finite-count summaries
```

Required tolerances:

```text
exact equality for subject IDs, fiber IDs, split indices, F+, and F-
near equality for float outputs under float64 reductions
same NaN/degenerate fiber locations
same plus-one p value for the deterministic small test
```

The final run manifest should record whether the optimized equivalence test passed.
