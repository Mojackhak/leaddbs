# HF-Adjusted ULF-Only Add-On Gain Normative Connectome Fiber Model

## Research Question

Which ULF-only normative connectome streamlines are associated with additional benefit after ULF stimulation is added to HF stimulation, after adjusting for HF clinical state and model-predicted change in HF fiber engagement?

This is a right-canonical, full-connectome, fiber-level model. Individual streamlines from the public structural connectome are the primary modeling units. Target atlases are retained only for endpoint labeling, anatomical enrichment, QC, and visualization.

Frequency definitions:

```text
HF  = high-frequency stimulation component, frequency_Hz >= 100
ULF = ultra-low-frequency stimulation component, frequency_Hz <= 50
```

## Endpoint

Two endpoint families are modeled separately:

```text
Chronic domain-specific endpoint:
  Y_HFplusULF_3m_domain = raw HF+ULF 3-month clinical score
  nuisance covariates = Y_HF3m_domain + DeltaHFScore_3m_domain

Immediate motor endpoint:
  Y_HFplusULF_immediate_motor = raw HF+ULF immediate motor score
  nuisance covariates = Y_HF3m_motor + DeltaHFScore_immediate_motor
```

The primary estimand is:

```text
HF-adjusted ULF-only add-on gain
```

Lower-is-better and higher-is-better scale directions are handled by the same built-in scale direction table used by the HF models.

## Inputs

- Public Lead-DBS structural connectomes: PPMI 85, MGH-USC HCP 32, and dTOR-985 Full.
- HF+ULF programming split into HF and ULF components.
- Raw `sim-efield` or accepted e-field-like exposure maps for the HF component and ULF component.
- Normative HF fiber-level model output from [`hf_3m_normative_connectome_fiber_model.md`](hf_3m_normative_connectome_fiber_model.md).
- Raw HF-only and HF+ULF clinical scores.
- Connected-region atlases for endpoint labels, anatomical enrichment, and STN/SNr contextual overlays.

The model-matched HF adjustment is computed from the normative HF fiber-level model:

```text
DeltaHFScore =
  S_HF_norm_fiber(E_HF_component,HF+ULF)
  - S_HF_norm_fiber(E_HF_only,HF-only)

S_HF_norm_fiber(E) = NetFiberScore(E)
```

`DeltaHFScore` is estimated inside each training fold. It may be z-scored inside that fold, but no fixed scaling coefficient is imposed before regression.

## Feature Construction

The executable feature space is a right-canonical streamline feature space. Left-sided stimulation is flipped into the right canonical space with `ea_flip_lr_nonlinear` and sampled along the same right-sided streamline features. Thus, bilateral e-field information is used, but the streamline feature set itself is one-sided/canonical rather than a true bilateral streamline set.

For each patient `i` and right-canonical streamline `l`, compute component-level peak exposure:

```text
E_HF_R_i(l)       = peak HF-component exposure along right-side fiber l
E_HF_L_to_R_i(l)  = peak left HF-component exposure after nonlinear L-to-R flip
E_ULF_R_i(l)      = peak ULF-component exposure along right-side fiber l
E_ULF_L_to_R_i(l) = peak left ULF-component exposure after nonlinear L-to-R flip

X_HF_component_i(l)  = (E_HF_R_i(l)  + E_HF_L_to_R_i(l))  / 2
X_ULF_component_i(l) = (E_ULF_R_i(l) + E_ULF_L_to_R_i(l)) / 2
```

Alternating ULF subprograms are combined within side by voxel-wise or streamline-wise maximum before bilateral averaging. Exposure is not scaled by frequency or pulse width in the peak E-field branch; those parameters are recorded in provenance.

ULF-only exposure is threshold-specific because HF-overlap streamlines are excluded from the ULF predictor:

```text
ULF_touched_i(l,tau) = X_ULF_component_i(l) > tau
HF_touched_i(l,tau)  = X_HF_component_i(l)  > tau

X_ULF_only_i(l,tau) =
  X_ULF_component_i(l), if ULF_touched_i(l,tau) and not HF_touched_i(l,tau)
  0,                   otherwise
```

If a streamline is activated by both HF and ULF components, it is attributed to the HF model and contributes to `DeltaHFScore` adjustment rather than to the ULF-only predictor.

Candidate fibers are defined to match the HF normative fiber model:

```text
tau_primary = 800 V/m
tau_sensitivity = 1500 V/m

Coverage_tau(l) = sum_i I[X_ULF_only_i(l,tau) > tau]
F_candidate_tau = {l: Coverage_tau(l) >= 5}
```

The candidate universe is the full public connectome, not target-restricted seed-target tracts.

## Statistical Model

The primary estimator is nuisance-adjusted partial Spearman at the fiber level:

```text
rho_ULF(l) =
  corr(
    resid(rank(Y_post_i)          ~ rank(Y_HF3m_i) + rank(DeltaHFScore_i)),
    resid(rank(X_ULF_only_i(l))   ~ rank(Y_HF3m_i) + rank(DeltaHFScore_i))
  )
```

Ties use average ranks. The same estimator is used for chronic and immediate endpoints with endpoint-matched `Y_post`, `Y_HF3m`, and `DeltaHFScore`.

Benefit-oriented fiber weights:

```text
M_ULF(l) = -rho_ULF(l)   for lower-is-better scales
M_ULF(l) =  rho_ULF(l)   for higher-is-better scales
```

Positive/sweet selected fibers:

```text
F+ = top 1% fibers with largest positive M_ULF(l)
```

Negative/sour selected fibers:

```text
F- = top 0.5% fibers with most negative M_ULF(l)
```

For each patient:

```text
SweetWeighted_i(l) = X_ULF_only_i(l) * M_ULF(l),      l in F+
SourWeighted_i(l)  = X_ULF_only_i(l) * [-M_ULF(l)],   l in F-

SweetPeak5_i = mean of top 5% largest SweetWeighted_i(l)
SourPeak5_i  = mean of top 5% largest SourWeighted_i(l)

NetULFFiberScore_i = SweetPeak5_i - SourPeak5_i
```

Selection and edge cases:

- `F+` and `F-` are selected within `F_candidate_tau`, excluding `NaN` or degenerate fibers.
- Percentile counts use `ceil(percent * n)` with at least one fiber when the corresponding positive or negative pool is non-empty.
- If `F+` is empty, `SweetPeak5_i = 0`.
- If `F-` is empty, `SourPeak5_i = 0`.
- If a selected set is non-empty but a patient has zero ULF-only exposure to all selected fibers, the corresponding peak score is `0`.

Prediction model:

```text
Y_post_i = alpha
         + delta * NetULFFiberScore_i
         + beta  * Y_HF3m_i
         + gamma * DeltaHFScore_i
         + error_i
```

Nuisance-only baseline:

```text
Y_post_i = alpha
         + beta  * Y_HF3m_i
         + gamma * DeltaHFScore_i
         + error_i
```

Optional supplemental estimator, not run in the current execution plan:

```text
OLS ANCOVA:
  Y_post_i ~ X_ULF_only_i(l) + Y_HF3m_i + DeltaHFScore_i
```

The optional ANCOVA branch is reserved for future sensitivity work and does not replace the primary partial Spearman estimator.

## Validation

Use fully nested leave-one-patient-out cross-validation.

For each connectome, scale, endpoint family, and outer fold:

```text
train = all patients except held-out patient h
test  = patient h
```

Within the training fold:

1. Recompute fold-specific `DeltaHFScore` from the HF normative fiber model.
2. Compute fold-specific `X_ULF_only_i(l,tau)` using only training patients for candidate definition.
3. Define `F_candidate_tau` from training-patient `Coverage_tau(l) >= 5`.
4. Fit `rho_ULF(l)` and `M_ULF(l)` using training patients only.
5. Select fold-specific `F+` and `F-`.
6. Compute `SweetPeak5`, `SourPeak5`, and `NetULFFiberScore` for training patients and the held-out patient.
7. Fit `Y_post ~ NetULFFiberScore + Y_HF3m + DeltaHFScore` in training patients.
8. Predict held-out `Y_post`.

Fold-level forbidden operations:

- No full-sample candidate mask for LOOCV scoring.
- No full-sample ranks.
- No full-sample `M_ULF`.
- No full-sample `F+` or `F-`.
- The held-out patient must not enter candidate definition, ULF map fitting, selected-fiber selection, or final prediction-model fitting.

Main validation metrics:

```text
LOOCV Spearman rho
LOOCV Pearson r
MAE
RMSE
Q2 relative to nuisance-only baseline
```

Freedman-Lane permutation is used for the dTOR primary branch:

```text
formal B = 10000
smoke B = 1000
seed = 42
primary statistic = LOOCV Spearman rho
p_plus_one = (1 + count(|stat_perm| >= |stat_obs|)) / (B + 1)
```

Each permutation must rerun the full LOOCV workflow, including candidate definition, `rho_ULF`, `M_ULF`, `F+`, `F-`, `NetULFFiberScore`, and held-out prediction.

Subject-level bootstrap for the dTOR primary branch:

```text
formal B = 10000
smoke B = 1000
seed = 42
```

PPMI and MGH are observed robustness branches. They require observed LOOCV, scores, maps, labels, and display outputs, but not formal `B=10000` permutation/bootstrap.

## Plain Connected-Streamline Control

The plain control tests whether the ULF result is merely stimulation burden, lead placement, or connectome density rather than outcome-filtered fiber specificity.

For each patient:

```text
Touched_ULF_only_i(l) = I[X_ULF_only_i(l,tau) > tau]

PlainTouchedCount_i = sum_l Touched_ULF_only_i(l)
PlainExposureSum_i  = sum_l X_ULF_only_i(l,tau)
PlainExposureTop5_i = mean top 5% X_ULF_only_i(l,tau) among touched candidate fibers
```

Compare:

```text
Y_post ~ Y_HF3m + DeltaHFScore
Y_post ~ PlainExposureTop5 + Y_HF3m + DeltaHFScore
Y_post ~ NetULFFiberScore + Y_HF3m + DeltaHFScore
Y_post ~ NetULFFiberScore + PlainExposureTop5 + Y_HF3m + DeltaHFScore
```

The joint model is QC only. With `n=16`, it must not be interpreted as a strong causal decomposition.

## Downstream Visualization

Output root:

```text
/Volumes/VAL/STNSNr/summary/normative_connectome_fiber/ulf/<connectome_slug>/<endpoint_slug>/<scale_slug>/<branch>/
```

Required numeric outputs per completed branch:

```text
normative_ULF_fiber_weights.csv
normative_ULF_fiber_scores.csv
normative_ULF_fiber_loocv_predictions.csv
normative_ULF_fiber_permutation_summary.csv
normative_ULF_fiber_mapping_qc.json
normative_ULF_fiber_generation_manifest.json
normative_ULF_fiber_HF_overlap_exclusion_summary.csv
```

Score outputs include:

```text
SweetPeak5
SourPeak5
NetULFFiberScore
DeltaHFScore
Y_HF3m
n_sweet_selected_fibers
n_sour_selected_fibers
n_sweet_peak_fibers
n_sour_peak_fibers
PlainExposureTop5
is_primary_score
```

Display and anatomical interpretation outputs:

```text
normative_ULF_fiber_display_top1_positive.tck
normative_ULF_fiber_display_top1_positive.mat
normative_ULF_fiber_display_top0p5_sour.tck
normative_ULF_fiber_display_top0p5_sour.mat
normative_ULF_fiber_density_map.nii.gz
normative_ULF_fiber_endpoint_labels.csv
normative_ULF_fiber_cortical_endpoint_summary.csv
normative_ULF_fiber_subcortical_crossing_summary.csv
normative_ULF_fiber_label_enrichment.csv
normative_ULF_fiber_unthresholded_weighted_density.nii.gz
normative_ULF_fiber_positive_weighted_density.nii.gz
normative_ULF_fiber_negative_weighted_density.nii.gz
normative_ULF_fiber_neglogp_density.nii.gz
normative_ULF_fiber_qvalue_summary.csv
fdr_summary_by_scale.csv
fdr_thresholded_positive_density_q05.nii.gz
fdr_thresholded_negative_density_q05.nii.gz
fdr_thresholded_positive_density_q10.nii.gz
fdr_thresholded_negative_density_q10.nii.gz
connectome_scale_performance_summary.csv
connectome_scale_overlap_summary.csv
connectome_density_correlation_summary.csv
connectome_selected_label_summary.csv
```

Plain-control outputs:

```text
normative_ULF_plain_touched_summary.csv
normative_ULF_plain_connected_model_comparison.csv
normative_ULF_plain_touched_fibers.tck
normative_ULF_plain_touched_density_map.nii.gz
```

FDR q-values, q-thresholded maps, endpoint labels, and display fibers are QC/display outputs only. They do not define `F+`, `F-`, `NetULFFiberScore`, or the primary model.

## Execution Efficiency

Efficiency rules follow the HF normative fiber model and must preserve exact equivalence.

Allowed caches:

```text
X_ULF_component_float32_fiber_major.npy
X_HF_component_float32_fiber_major.npy
X_ULF_only_tau800_float32_fiber_major.npy
X_ULF_only_tau1500_float32_fiber_major.npy
S800_ULF_only_bool.npy
S1500_ULF_only_bool.npy
fiber_id.npy
candidate_fiber_metadata.json
```

dTOR must be processed with chunked sidecars. Implementations must not load all dTOR streamlines into memory.

Outcome-independent caches may be reused across scales and endpoint families:

- raw component exposure sidecars
- ULF-only overlap-exclusion masks
- `Coverage_tau` caches
- candidate fiber metadata
- endpoint label lookup
- density lookup

Outcome-dependent objects must be recomputed inside each training fold:

- `DeltaHFScore`
- nuisance residuals
- `rho_ULF`
- `M_ULF`
- `F+`
- `F-`
- `SweetPeak5`
- `SourPeak5`
- `NetULFFiberScore`
- final prediction model

Disallowed shortcuts:

```text
reducing formal B=10000
adaptive permutation early stopping
full-sample ranks in fold-level estimation
approximate ranks
full-sample candidate mask replacing fold-specific candidate masks
fixed full-sample F+/F- used for LOOCV scoring
permutation score computed only from observed maps
outcome- or preliminary-rho-based fiber prefiltering
skipping sour fibers
using target-level aggregation as the primary model
```

Every optimized implementation must pass an exact-equivalence regression test against a small deterministic brute-force subset before formal execution.

## Execution Priority And Gatekeeping

Run this model as a gated sequence.

Current executable branches:

```text
primary:
  ulf_peak_efield_tau800_primary

sensitivity:
  ulf_peak_efield_tau1500_sensitivity
  ulf_top1500_top500_sensitivity

control:
  ulf_plain_connected_streamline_control
```

Current connectome roles:

```text
PPMI 85 (Ewert 2017)          observed figure-grade robustness
MGH-USC HCP 32 (Horn 2017)    observed figure-grade robustness
dTOR-985 Full (Elias 2024)    primary analysis
```

### Round 0: Version, Input, And Manifest Freeze

Run checks only:

```text
lock document version
lock endpoint list
lock scale list
lock connectome list
lock branch list
lock tau800 / tau1500 / Coverage>=5
lock seed = 42
check HF and ULF e-field manifests
check clinical ID join
check scale direction
check DeltaHFScore source
check PPMI / MGH / dTOR readability
check output root writability
```

Enter Round 1 only if all inputs are uniquely resolved and the worktree manifests record the locked parameter set.

### Round 1: Sidecar Cache And Equivalence Test

Build PPMI/MGH sidecars and dTOR chunked sidecars for HF component exposure, ULF component exposure, and tau-specific ULF-only exposure. Run a deterministic small-subset equivalence test for candidate definition, partial Spearman, selected fibers, `NetULFFiberScore`, LOOCV prediction, smoke permutation, and bootstrap summaries.

Enter Round 2 only if optimized and brute-force outputs match within the predefined tolerance and dTOR chunked IO has no memory error.

### Round 2: Primary Observed Chronic Endpoint

Run:

```text
endpoint = chronic 3-month HF+ULF add-on
branch = ulf_peak_efield_tau800_primary
connectome order = PPMI observed -> MGH observed -> dTOR observed
```

Enter Round 3 only if dTOR observed LOOCV completes, fold-specific candidates are non-empty, `NetULFFiberScore` has nonzero variance, and validation metrics are finite.

### Round 3: Primary Observed Immediate Endpoint

Run:

```text
endpoint = immediate HF+ULF motor add-on
branch = ulf_peak_efield_tau800_primary
connectome order = PPMI observed -> MGH observed -> dTOR observed
```

Enter Round 4 only if the immediate endpoint joins correctly, candidate masks are non-empty, `NetULFFiberScore` is non-constant, and LOOCV prediction is fit.

### Round 4: Plain Connected-Streamline Control

Run `ulf_plain_connected_streamline_control` for endpoints/connectomes that passed observed gates. Compare nuisance-only, plain exposure, ULF net score, and joint QC models.

Enter Round 5 only if `PlainExposureTop5` is computable, the joint QC model is not singular, and `NetULFFiberScore` is not perfectly collinear with `PlainExposureTop5`.

### Round 5: dTOR Primary Smoke Resampling

Run only dTOR primary branches that passed observed gates:

```text
Freedman-Lane smoke permutation B=1000
subject-level smoke bootstrap B=1000
seed = 42
```

Enter Round 6 only if smoke permutation/bootstrap complete, plus-one p-values are computable, bootstrap finite counts are interpretable, and runtime profile suggests formal `B=10000` is feasible.

### Round 6: Cheap Observed Sensitivity

Run observed-only sensitivity:

```text
ulf_peak_efield_tau1500_sensitivity
ulf_top1500_top500_sensitivity
PPMI -> MGH -> dTOR
```

Do not run formal permutation/bootstrap for these branches. Enter Round 7 only if sensitivity outputs are finite or explicitly record candidate-empty / threshold-too-strict status.

### Round 7: dTOR Primary Formal Resampling

Run only:

```text
connectome = dTOR
branch = ulf_peak_efield_tau800_primary
formal permutation B=10000
formal bootstrap B=10000
seed = 42
```

Enter Round 8 only if formal resampling completes and manifests record `resampling_status = formal_complete`.

### Round 8: Display, FDR, Labels, Density, And Cross-Connectome Summaries

Generate display and interpretation outputs only after numeric branches are locked. Display, FDR, label, density, and cross-connectome outputs must derive from finalized numeric outputs and must not alter the primary model.

## Interpretation Boundary

This model estimates HF-adjusted ULF-only add-on association using public normative connectomes. It is not an anatomical SNr gain model. It does not claim that ULF effects are restricted to SNr or to predefined seed-target pathways. The primary predictor represents streamlines uniquely recruited by ULF after HF-overlap streamlines are assigned to HF adjustment through `DeltaHFScore`.

Because `n=16`, all ULF fiber-level results are hypothesis-generating. Negative or unstable LOOCV results should not be interpreted as proof that ULF has no biological effect; they may reflect limited sample size, endpoint noise, stimulation-field uncertainty, or connectome limitations.
