# HF-Status-Resolved ULF-Only Add-On Gain Direct Voxel-Level Model

## Research Question

Which ultra-low-frequency stimulation territory voxels have ULF-only exposure associated with additional clinical benefit after ULF stimulation is added to HF stimulation, after adjusting for the patient's same-day HF clinical state and model-predicted change in HF efficacy?

This is a direct local ULF-only add-on sweet-spot model. It does not define the main question as an anatomic SNr effect. The STN/SNr and peri-STN/SNr region is treated as one stimulation territory, with HF and ULF components separated by stimulation frequency and exposure overlap.

Frequency definitions:

```text
HF  = high-frequency stimulation component, frequency_Hz >= 100
ULF = ultra-low-frequency stimulation component, frequency_Hz <= 50
```

Voxels co-activated by HF and ULF are attributed to the HF adjustment model and are excluded from the primary ULF-only predictor. This is a modeling choice, not a biological claim that ULF cannot have an effect in HF-overlap territory.

## Follow-Up Timeline

The model assumes the following visit sequence:

```text
T0 = preoperative baseline assessment

T1 = postoperative 1-month HF immediate activation / opening assessment

T2 = HF-only 3-month follow-up
     same day, before adding ULF:
       raw HF-only 3-month clinical state is measured
     same day, after switching to HF+ULF:
       raw HF+ULF immediate clinical state is measured

T3 = HF+ULF 3-month follow-up
     approximately 3 months after T2:
       raw HF+ULF chronic 3-month clinical state is measured
```

The immediate HF+ULF endpoint and the HF-only 3-month clinical reference state are therefore same-day measurements. The immediate endpoint is not confounded by a different visit day relative to the HF-only 3-month reference. The chronic endpoint is a post-add-on follow-up endpoint, using the T2 HF-only 3-month state as the pre-ULF clinical reference.

## Endpoint Definitions

Two endpoint families are modeled separately.

### Primary Chronic Post-Add-On Endpoint

```text
Y_post_chronic = raw HF+ULF 3-month clinical score at T3
Y_HF_ref       = raw HF-only 3-month clinical score at T2, same scale/domain
DeltaHFScore_chronic = predicted change in HF efficacy between
                       HF+ULF chronic programming and HF-only T2 programming
```

Primary chronic estimand:

```text
HF-state-adjusted ULF-only chronic add-on association
```

This endpoint estimates whether ULF-only exposure explains the T3 HF+ULF outcome after accounting for the patient's T2 HF clinical state and the modeled change in HF-component efficacy.

### Key Same-Day Immediate Endpoint

```text
Y_post_immediate = raw HF+ULF immediate clinical score at T2, after switching to HF+ULF
Y_HF_ref         = raw HF-only 3-month clinical score at T2, before switching to HF+ULF
DeltaHFScore_immediate = predicted change in HF efficacy between
                         immediate HF+ULF programming and HF-only T2 programming
```

Immediate estimand:

```text
same-day HF-state-adjusted ULF-only acute add-on association
```

Because `Y_post_immediate` and `Y_HF_ref` are measured on the same day, this endpoint is a valid same-day add-on response endpoint. It is still modeled separately from the chronic endpoint. It may be treated as a key secondary endpoint by default, or promoted to co-primary only if explicitly declared before running formal resampling.

### Direction-Normalized Gain Sensitivity Endpoints

The primary model uses raw post-HF+ULF scores with HF-state adjustment. Direction-normalized gain endpoints are retained as sensitivity analyses.

For lower-is-better scales:

```text
Gain_immediate = Y_HF_ref - Y_post_immediate
Gain_chronic   = Y_HF_ref - Y_post_chronic
```

For higher-is-better scales:

```text
Gain_immediate = Y_post_immediate - Y_HF_ref
Gain_chronic   = Y_post_chronic - Y_HF_ref
```

Positive gain always means improvement after adding ULF. The immediate gain endpoint is the cleanest direct same-day add-on effect estimate. The chronic gain endpoint combines add-on response, time-on-stimulation, adaptation, medication/assessment variability, and disease-course effects.

Default first-pass endpoints:

```text
1. MDS-UPDRS III total chronic HF+ULF 3-month score at T3
2. MDS-UPDRS III total same-day immediate HF+ULF score at T2, if available
```

Raw scores come from the raw clinical table used by the HF direct voxel model:

```text
/Users/mojackhu/Research/STNSNr/summary/cohort/subj/subject_effect_origin.xlsx
```

Clinical rows are joined to imaging by `ID` (`SNr003`, `SNr006`, etc.). Improvement-rate tables are not used by the primary raw-score model. Scale direction is read from the same internal direction table as the HF direct voxel model. Unknown scales must provide an explicit higher-is-better or lower-is-better direction before the run starts.

## Inputs

- Stimulation parameter audit source:

  ```text
  /Users/mojackhu/Research/STNSNr/summary/cohort/subj/followup_stimulation.xlsx
  sheet = Contact Parameters
  ```

  This workbook is used to audit HF and ULF component identity, frequencies, pulse widths, amplitudes, sides, contacts, and phase labels. Existing e-fields are treated as accepted inputs after prior manual/clinical QC. The current ULF direct voxel analysis does not automatically create missing e-fields.

- HF-only reference E-field per side from the T2 HF-only 3-month phase, used to compute the reference HF score.

- HF component E-field and ULF component E-field per side from same-day T2 immediate HF+ULF programming, used for the immediate endpoint.

- HF component E-field and ULF component E-field per side from T3 chronic HF+ULF programming, used for the chronic endpoint. If the T3 stimulation settings are unchanged from T2 immediate HF+ULF programming, the manifest must explicitly record that the same component e-fields were reused.

- Direct voxel-level HF efficacy map trained from HF-only outcomes, matching the model type:

  ```text
  DeltaHFScore source = HF direct voxel model
  ```

  The ULF direct voxel model must not use a normative fiber HF score as the HF adjustment. Voxel-level ULF models adjust with voxel-level HF models.

- Canonical reference mask:

  ```text
  templates/space/MNI152NLin2009bAsym/brainmask.nii.gz > 0
  ```

  Candidate voxels are restricted to right-hemisphere voxel centers with MNI world coordinate `x > 0`.

- Anatomical overlay masks:

  ```text
  templates/space/MNI152NLin2009bAsym/atlases/STNSNr-connected regions/{rh,lh}/STNSNrplus.nii.gz
  ```

  `STNSNrplus` is used only for anatomical overlay, territory coverage, and QC background. It is not intersected with `Omega_ULF_tau` and is not the statistical candidate mask.

- Left/right homology transform:

  ```text
  helpers/ea_flip_lr_nonlinear.m
  templates/space/MNI152NLin2009bAsym/fliplr/{Composite,InverseComposite}.nii.gz
  ```

  All left/right flipping in this model uses `ea_flip_lr_nonlinear` with the Lead-DBS default interpolation behavior.

Minimum e-field checks: required paths must exist, subject/side/component/phase matches must be unique, files must be raw `sim-efield`, and units must be recorded as `V/m`. Missing or multiply matched e-fields fail the endpoint/run. Subjects are not silently excluded and missing e-fields are not automatically created.

## Locked HF Prerequisite

The ULF direct voxel model may enter formal analysis only after the HF direct voxel model source for `DeltaHFScore` has been locked.

Locked HF source:

```text
model_family = hf_3m_direct_voxel_model
scale        = matched scale/domain
branch       = tau200 / partial_spearman
coverage     = Coverage>=5
score        = HFScore_mean_main
map source   = training-fold map for LOOCV
full-sample map = descriptive and full-sample score output only
```

The ULF direct voxel implementation does not hard-code a single primary branch before HF results are reviewed. It runs the DeltaHF-adjusted and no-DeltaHF branches as an equal-status core branch pair when their inputs are available. The model report then records which branch is the interpretive primary branch using the locked HF result:

```text
if HF model is predictive_valid:
  ulf_primary_branch = delta_hf_adjusted
  delta_hfscore_role = primary nuisance adjustment
  no_delta_hf_role   = sensitivity

if HF model is stable_nonpredictive:
  ulf_primary_branch = no_delta_hf
  delta_hfscore_role = sensitivity / compatibility adjustment
  no_delta_hf_role   = primary

if HF model is failed_unstable:
  ulf_primary_branch = no_delta_hf when ULF inputs remain valid
  delta_hfscore_role = exploratory only, or not run if HF support is unavailable
  no_delta_hf_role   = primary exploratory branch
```

The branch-role decision must be written to the model manifest:

```text
hf_prediction_validity_status
hf_prediction_validity_source
ulf_primary_branch
ulf_core_branches_run
ulf_sensitivity_branches
delta_hfscore_role
branch_role_decision_reason
hf_model_support_status
```

If the locked HF branch fails QC, produces near-constant `HFScore_mean_main`, has empty fold scoring masks, or does not provide interpretable HF map support, `DeltaHFScore` must be labeled as an unstable generated covariate and cannot define the primary ULF interpretation.

Post-hoc HF threshold candidates follow the level system defined in `hf_3m_direct_voxel_model.md`. Level 0 and Level 1 candidates must not be propagated to ULF. Level 2 and Level 3 candidates may generate separate exploratory `DeltaHFScore` sensitivity branches only. Level 4 candidates, or the original `tau200/Coverage>=5` primary HF branch when it is `predictive_valid`, may define the primary DeltaHF-adjusted ULF interpretation. At most one selected post-hoc candidate per endpoint may generate a ULF branch; neighboring support cells are robustness evidence, not separate covariates.

## Feature Construction

Use the right-hemisphere MNI brainmask grid as the canonical statistical grid. Left-sided HF and ULF component fields are flipped into right space with `ea_flip_lr_nonlinear`. Right-sided fields are sampled on the same right canonical grid.

For each subject, side, and endpoint phase:

```text
E_HF_R_i(v, phase)       = right HF component e-field
E_HF_L_to_R_i(v, phase)  = left HF component e-field flipped to right canonical space
E_ULF_R_i(v, phase)      = right ULF component e-field
E_ULF_L_to_R_i(v, phase) = left ULF component e-field flipped to right canonical space
```

Same-side alternating subprograms are handled by component:

```text
E_HF_side_i(v, phase)  = voxel-wise maximum over same-side HF subprograms
E_ULF_side_i(v, phase) = voxel-wise maximum over same-side ULF subprograms
```

Interleaving is not modeled as simultaneous double-cathode stimulation. If a clinical condition contains synchronous mixed HF+ULF programming and component-specific fields are generated by turning on only the contacts assigned to one frequency component, the manifest must label those fields as component-specific proxies.

Patient-level bilateral component exposure:

```text
E_HF_component_i(v, phase) =
  (E_HF_R_i(v, phase) + E_HF_L_to_R_i(v, phase)) / 2

E_ULF_component_i(v, phase) =
  (E_ULF_R_i(v, phase) + E_ULF_L_to_R_i(v, phase)) / 2
```

Frequency only classifies the component as HF or ULF. Exposure is not scaled by frequency or pulse width in the primary direct voxel analysis.

### ULF Candidate Space

Sparse ULF candidate construction is phase-specific:

```text
candidate_threshold = 180 V/m
Candidate_ULF_phase(v) = any valid subject has E_ULF_component_i(v, phase) > 180 V/m
```

For each tau and endpoint phase:

```text
tau_primary = 200 V/m
tau_sensitivity = {180, 220} V/m

HF_active_i(v, phase)  = E_HF_component_i(v, phase)  > tau
ULF_active_i(v, phase) = E_ULF_component_i(v, phase) > tau

X_ULF_only_i(v, phase, tau) =
  E_ULF_component_i(v, phase), if ULF_active_i(v, phase) and not HF_active_i(v, phase)
  0,                         otherwise

Coverage_ULF_tau(v, phase) = sum_i I[X_ULF_only_i(v, phase, tau) > tau]
Omega_ULF_tau(phase) = {v in Candidate_ULF_phase : Coverage_ULF_tau(v, phase) >= 5}
```

For ULF, `tau` is part of the exposure definition. It defines component activity, HF-overlap exclusion, ULF-only zeroing, coverage, and QC. Therefore, `tau180/tau200/tau220` are not merely coverage sensitivities; they are exposure-definition sensitivities.

Continuous `X_ULF_only_i(v, phase, tau)` values are used for modeling inside `Omega_ULF_tau`. Voxels with both HF and ULF activation are excluded from the primary ULF-only predictor and represented by HF-overlap outputs.

### HF-Overlap Exclusion Outputs

HF-overlap is subject-specific, phase-specific, and tau-specific:

```text
HF_ULF_overlap_i(v, phase, tau) = HF_active_i(v, phase) and ULF_active_i(v, phase)
```

Do not store only one ambiguous binary overlap mask. Required overlap outputs are:

```text
direct_voxel_ULF_only_HF_overlap_coverage.nii.gz
direct_voxel_ULF_only_HF_overlap_fraction.nii.gz
direct_voxel_ULF_only_HF_overlap_subject_summary.csv
direct_voxel_ULF_only_HF_overlap_exclusion_mask_display.nii.gz
```

The display exclusion mask may be a full-sample `any-subject overlap` or `coverage>=1` mask, but its definition must be recorded explicitly in the manifest.

## DeltaHFScore

The model-matched HF adjustment comes from the locked HF direct voxel model.

For a given full-sample map or LOOCV training fold:

```text
V_HF_score = Omega_HF_tau200 intersect valid M_HF voxels
n_valid_HF_score_voxels = |V_HF_score|

S_HF_voxel(E)_i =
  sum_{u in V_HF_score} E_i(u) * M_HF(u)
  / n_valid_HF_score_voxels
```

Endpoint-specific HF efficacy-change covariates:

```text
DeltaHFScore_immediate_i =
  S_HF_voxel(E_HF_component, T2 immediate HF+ULF programming)_i
  - S_HF_voxel(E_HF_only_reference, T2 HF-only 3m programming)_i

DeltaHFScore_chronic_i =
  S_HF_voxel(E_HF_component, T3 HF+ULF 3m programming)_i
  - S_HF_voxel(E_HF_only_reference, T2 HF-only 3m programming)_i
```

If the HF component settings in HF+ULF are identical to the T2 HF-only reference settings, `DeltaHFScore` should be near zero except for numerical interpolation and component-labeling differences. If the HF component changed, `DeltaHFScore` captures the model-predicted HF efficacy shift caused by HF-component reprogramming.

`DeltaHFScore` is not assigned a fixed biological scaling coefficient before modeling. It may be z-scored within training folds for numerical stability; its regression coefficient estimates its association with outcome. In LOOCV, `DeltaHFScore` for the held-out patient must be computed from the training-fold HF map, not a full-sample HF map.

### HF-Map Support And Out-Of-Support HF Exposure

`M_HF(u)` is defined only on `V_HF_score`. If an HF component field in the HF+ULF condition has suprathreshold exposure outside the HF 3-month model support, those voxels must not be extrapolated, smoothed into support, nearest-neighbor assigned, or added to the locked HF map post hoc.

Primary rule:

```text
DeltaHFScore uses in-support HF projection only.
```

That is:

```text
S_HF_voxel(E)_i =
  sum_{u in V_HF_score} E_i(u) * M_HF(u)
  / n_valid_HF_score_voxels
```

HF exposure outside `V_HF_score` contributes `0` to `DeltaHFScore` because the HF model has no learned coefficient there. This zero contribution means "unscored / outside learned support", not "biologically no HF effect".

Out-of-support burden must be quantified for every subject, endpoint phase, tau, and LOOCV fold:

```text
HF_in_support_sum_i = sum_{u in V_HF_score} E_HF_component_i(u)
HF_total_sum_i      = sum_{u in right_canonical_HF_grid} E_HF_component_i(u)
HF_out_support_sum_i = HF_total_sum_i - HF_in_support_sum_i

HF_out_support_fraction_i =
  HF_out_support_sum_i / max(HF_total_sum_i, epsilon)

HF_out_support_volume_tau_i =
  voxel_volume * count_v[ E_HF_component_i(v) > tau and v notin V_HF_score ]

HF_out_support_top5_i =
  mean top 5% E_HF_component_i(v) among voxels with E_HF_component_i(v) > tau and v notin V_HF_score
```

Required outputs:

```text
direct_voxel_ULF_only_delta_hf_support_summary.csv
direct_voxel_ULF_only_delta_hf_support_qc.json
```

Required fields include:

```text
subject_id
endpoint
phase
tau
score_map_source
n_hf_score_voxels
HF_in_support_sum
HF_out_support_sum
HF_out_support_fraction
HF_out_support_volume_tau
HF_out_support_top5
DeltaHFScore_in_support
DeltaHFScore_source_branch
fold_id if LOOCV
```

Default decision rules:

```text
Proceed without downgrading:
  cohort median HF_out_support_fraction <= 0.20
  and no more than 25% of subjects have HF_out_support_fraction > 0.50

Proceed but downgrade interpretation:
  cohort median HF_out_support_fraction > 0.20
  or more than 25% of subjects have HF_out_support_fraction > 0.50

Do not treat ULF model as confirmatory:
  HF_out_support_fraction is extreme enough that DeltaHFScore no longer represents the HF component change for many subjects,
  or the HF component was reprogrammed mainly into territory never covered by the locked HF model.
```

When downgraded, report:

```text
DeltaHFScore represents only the in-support projection of HF-component change.
Substantial HF-component exposure lay outside the learned HF 3-month map support.
```

Recommended sensitivity when out-of-support burden is nontrivial:

```text
Y_post ~ ULFScore_mean_main + Y_HF_ref + DeltaHFScore_in_support + HF_out_support_top5
```

or, if collinearity is severe:

```text
Y_post ~ ULFScore_mean_main + Y_HF_ref + DeltaHFScore_in_support
```

with `HF_out_support_*` reported descriptively instead of included as a fourth predictor.

Do not expand the primary HF support after seeing ULF results. A predeclared sensitivity may use the locked HF `tau180/partial_spearman` support if it was generated independently, but voxels never covered by any HF-only model remain unscored.

## Statistical Model

### Core Branch A: DeltaHF-Adjusted Partial Spearman

For each endpoint, phase, tau, and voxel `v`, use rank-residual partial Spearman with average ranks for ties:

```text
rho_ULF(v) =
  corr(
    resid(rank(Y_post_i)                  ~ rank(Y_HF_ref_i) + rank(DeltaHFScore_i)),
    resid(rank(X_ULF_only_i(v, phase,tau)) ~ rank(Y_HF_ref_i) + rank(DeltaHFScore_i))
  )
```

Degenerate voxels with zero ULF-only exposure variance, zero rank variance, or zero residualized exposure variance are assigned `rho_ULF(v)=NaN` and excluded from `ULFScore_mean_main`.

Benefit-oriented map:

```text
M_ULF(v) = -rho_ULF(v)   for lower-is-better scales
M_ULF(v) =  rho_ULF(v)   for higher-is-better scales
```

Positive `M_ULF(v)` consistently means ULF-only sweet or benefit-associated. Negative `M_ULF(v)` means ULF-only sour or worse-outcome-associated.

### Core Branch B: No-DeltaHF Partial Spearman

The no-DeltaHF estimator removes `DeltaHFScore` but keeps the same-day or pre-ULF HF clinical state:

```text
rho_ULF_noDeltaHF(v) =
  corr(
    resid(rank(Y_post_i)                  ~ rank(Y_HF_ref_i)),
    resid(rank(X_ULF_only_i(v, phase,tau)) ~ rank(Y_HF_ref_i))
  )
```

This branch is not intrinsically secondary. It is the interpretive primary branch when the matched HF model is stable but not predictive enough to justify using `DeltaHFScore` as the main nuisance adjustment. Otherwise, it reports how much the ULF map depends on the model-derived HF adjustment.

### Gain Endpoint Sensitivity Estimator

For direction-normalized gain endpoints:

```text
rho_ULF_gain(v) =
  corr(
    resid(rank(Gain_i)                    ~ rank(DeltaHFScore_i)),
    resid(rank(X_ULF_only_i(v, phase,tau)) ~ rank(DeltaHFScore_i))
  )
```

For the immediate endpoint, this is a same-day add-on gain sensitivity. For chronic endpoint, it is a post-add-on change sensitivity.

### Total ULF Exposure Sensitivity

The primary predictor excludes HF-overlap voxels. A predeclared sensitivity keeps total ULF component exposure:

```text
X_ULF_total_i(v, phase) = E_ULF_component_i(v, phase)
```

The total-ULF branch uses the same covariates, estimator, score definition, LOOCV logic, and output family, but it is explicitly labeled:

```text
branch = total_ulf_exposure_sensitivity
```

This branch tests whether ULF-associated signal is lost when the primary model hard-excludes HF-overlap territory.

### Optional Supplemental Estimator: OLS ANCOVA

OLS ANCOVA is retained as an optional future supplemental estimator. It is not run in the current executable analysis and does not generate output files in this run.

```text
Y_post_i = alpha_v
         + theta_ULF(v) * X_ULF_only_i(v)
         + beta_v      * Y_HF_ref_i
         + gamma_v     * DeltaHFScore_i
         + error_i,v
```

If enabled in a future run, the OLS estimator should generate the same output family under an `ols_ancova/` estimator directory. Its `direct_voxel_ULF_only_coef.nii.gz` would store `theta_ULF(v)`, whereas the current `partial_spearman/` coefficient file stores `rho_ULF(v)`.

### Patient-Level Score

Primary patient-level ULF-only sweet-spot score:

```text
V_score = Omega_ULF_tau intersect valid M_ULF voxels
n_valid_score_voxels = |V_score|

ULFScore_mean_main_i =
  sum_{v in V_score} X_ULF_only_i(v, phase,tau) * M_ULF(v)
  / n_valid_score_voxels
```

This is the primary ULF-only prediction score. It is a voxel-count-normalized, voxel-correlation-weighted mean ULF-only exposure over the fixed scoring voxel set for the corresponding full-sample map or LOOCV training fold. It is not divided by `sum(X)` and is not multiplied by voxel volume. If `V_score` is empty, the branch/fold fails QC instead of producing a score. If a subject/fold has no ULF-only exposure in a non-empty valid scoring voxel set, `ULFScore_mean_main_i` is recorded as `0`.

DeltaHF-adjusted prediction model:

```text
Y_post_i = alpha
         + delta * ULFScore_mean_main_i
         + beta  * Y_HF_ref_i
         + gamma * DeltaHFScore_i
         + error_i
```

DeltaHF-adjusted covariate-only baseline:

```text
Y_post_i = alpha
         + beta  * Y_HF_ref_i
         + gamma * DeltaHFScore_i
         + error_i
```

No-DeltaHF prediction model:

```text
Y_post_i = alpha
         + delta * ULFScore_mean_main_i
         + beta  * Y_HF_ref_i
         + error_i
```

No-DeltaHF covariate-only baseline:

```text
Y_post_i = alpha
         + beta * Y_HF_ref_i
         + error_i
```

Both core branch prediction models are fit on the raw post-score scale. The primary validation statistic remains rank-based LOOCV Spearman rho. The branch-role resolver determines which branch's LOOCV statistic is reported as the primary statistic.

Missing-data rule: missing `Y_post`, missing `Y_HF_ref`, or failed e-field availability fails the endpoint/run after QC. Missing or invalid `DeltaHFScore` fails only the DeltaHF-adjusted branch; the no-DeltaHF branch may still run and must record why the adjusted branch was unavailable. For configurable future endpoints, the endpoint is skipped if the valid sample size falls below 12.

## Validation

- Model chronic T3 and same-day immediate T2 endpoints separately.
- Use leave-one-patient-out cross-validation with no inner hyperparameter tuning.
- In each outer fold, rebuild the branch-specific nuisance inputs, rebuild `Omega_ULF_tau`, fit the ULF-only voxel map, compute training and held-out `ULFScore_mean_main`, and fit the final prediction model using only training patients.
- For the DeltaHF-adjusted branch, rebuild the HF direct voxel map needed for `DeltaHFScore`, compute fold-specific `DeltaHFScore`, compute fold-specific HF out-of-support burden, and compare against `Y_post ~ Y_HF_ref + DeltaHFScore`.
- For the no-DeltaHF branch, omit `DeltaHFScore` from map estimation, scoring, prediction, permutation nuisance models, and baseline comparison; compare against `Y_post ~ Y_HF_ref`.
- Run both core branches at the observed LOOCV stage when inputs permit. The branch-role resolver records which one is interpreted as primary after the HF result is classified.
- Report the gain endpoint sensitivity when endpoint data are complete.
- Primary validation statistic: LOOCV Spearman rho between held-out predictions and held-out raw outcomes.
- Secondary metrics: LOOCV Pearson `r`, MAE, RMSE, and `Q2` on the original raw outcome scale.
- Define `Q2` relative to the covariate-only baseline:

  ```text
  Q2 = 1 - SSE_ULFScore_model / SSE_covariate_only
  ```

- Patient-level Freedman-Lane permutation uses `B=10000` and random seed `42` for the branch recorded as primary by the branch-role resolver. Smoke/exploratory runs use `B=1000`. Formal permutation is run only for the selected primary `tau200/partial_spearman` chronic endpoint branch unless the immediate endpoint is explicitly promoted to co-primary.
- For each permutation, fit the branch-specific nuisance model, permute nuisance residuals, reconstruct `Y*`, and rerun the full LOOCV pipeline including branch-specific nuisance inputs, ULF coverage, ULF map, `ULFScore_mean_main`, and prediction. The primary permutation statistic is LOOCV Spearman rho.
- Permutation p value is plus-one two-sided:

  ```text
  p = (1 + count(|stat_perm| >= |stat_obs|)) / (B + 1)
  ```

- Subject-level bootstrap uses `B=10000` and seed `42` for the branch recorded as primary by the branch-role resolver. Smoke/exploratory runs use `B=1000`. Each bootstrap resample reruns the full branch-specific map-building process, including `DeltaHFScore` and HF support QC only for the DeltaHF-adjusted branch, `Omega_ULF_tau`, and `direct_voxel_ULF_only_bootstrap_se.nii.gz` stores voxel-wise standard deviation of the estimator map.

For non-primary executed branches (`tau180/partial_spearman`, `tau220/partial_spearman`, the non-selected core branch, gain endpoint sensitivity, total-ULF sensitivity, and immediate endpoints unless co-primary), LOOCV is still run, but formal permutation/bootstrap outputs are not generated. Their manifests and QC JSON files must record:

```text
resampling_status = not_run_nonprimary
resampling_reason = formal resampling restricted to primary tau200/partial_spearman chronic branch unless endpoint promoted to co-primary
```

## Execution Structure

The later code implementation should keep image preprocessing and statistical postprocessing separated.

MATLAB/Lead-DBS preprocessing:

- discover and availability-check required HF-only reference, HF-component, and ULF-component e-fields;
- classify components by frequency (`HF >= 100 Hz`, `ULF <= 50 Hz`);
- combine same-side same-frequency alternating subprograms by voxel-wise maximum;
- call `ea_flip_lr_nonlinear` for all left/right flips;
- compute left/right flip deformation audit metrics and record warnings without automatic exclusion;
- sample HF and ULF component exposure into right-hemisphere MNI grids required for ULF modeling and HF-score projection;
- write a MAT v7 design matrix and optional compressed NPZ mirror.

Required design matrix schema:

- `E_ULF_component_phase(subject x ulf_candidate_voxel)` continuous ULF component exposure;
- `E_HF_component_phase_on_ulf_grid(subject x ulf_candidate_voxel)` continuous HF component exposure used for HF-overlap exclusion;
- `X_ULF_only_tau180_phase(subject x ulf_candidate_voxel)` tau-specific ULF-only exposure;
- `X_ULF_only_tau200_phase(subject x ulf_candidate_voxel)` tau-specific ULF-only exposure;
- `X_ULF_only_tau220_phase(subject x ulf_candidate_voxel)` tau-specific ULF-only exposure;
- `E_HF_component_phase_on_hf_score_grid(subject x hf_score_voxel)` continuous HF component exposure used for `DeltaHFScore`;
- `E_HF_only_reference_on_hf_score_grid(subject x hf_score_voxel)` continuous HF-only reference exposure used for `DeltaHFScore`;
- ULF candidate voxel `ijk` and MNI `xyz_mm`;
- HF score-support voxel `ijk` and MNI `xyz_mm`;
- NIfTI affine/header references;
- `subject_id`, source e-field paths, side metadata, component labels, frequency labels, visit labels, and clinical raw values;
- tau/candidate metadata, HF-overlap exclusion metadata, HF-support metadata, flip metadata, and jitter metadata placeholders.

The implementation must not store a single tau-independent `X_ULF_only` as the formal input. `X_ULF_only` is tau-specific because tau defines ULF activity, HF activity, and overlap exclusion.

Python postprocessing in the `leaddbs` Conda environment:

- read the MAT v7 design matrix or optional NPZ mirror;
- construct `Omega_ULF_tau` inside each fold;
- compute fold-specific HF direct voxel maps and `DeltaHFScore`;
- compute HF out-of-support burden for `DeltaHFScore`;
- run partial Spearman map fitting, LOOCV, permutation, bootstrap, and display output generation;
- write CSV, JSON, NIfTI maps, and figures.

Default parallelism follows the HF direct voxel model:

```text
MATLAB preprocessing workers: 8
Python jobs: 14
seed: 42
```

## Downstream Visualization And Outputs

Output root:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/<tau_slug>/<branch_slug>/
```

Core branches:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau200/partial_spearman_delta_hf_adjusted/
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau200/partial_spearman_no_delta_hf/
```

Sensitivity branches:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau180/partial_spearman_delta_hf_adjusted/
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau180/partial_spearman_no_delta_hf/
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau220/partial_spearman_delta_hf_adjusted/
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau220/partial_spearman_no_delta_hf/
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau200/partial_spearman_gain_endpoint/
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau200/partial_spearman_total_ulf_exposure/
```

Required outputs:

```text
direct_voxel_ULF_only_coverage.nii.gz
direct_voxel_ULF_only_coef.nii.gz
direct_voxel_ULF_only_sweet_sour.nii.gz
direct_voxel_ULF_only_stability.nii.gz
direct_voxel_ULF_only_bootstrap_se.nii.gz
direct_voxel_ULF_only_scores.csv
direct_voxel_ULF_only_loocv_predictions.csv
direct_voxel_ULF_only_permutation_summary.csv
direct_voxel_ULF_only_HF_overlap_coverage.nii.gz
direct_voxel_ULF_only_HF_overlap_fraction.nii.gz
direct_voxel_ULF_only_HF_overlap_subject_summary.csv
direct_voxel_ULF_only_HF_overlap_exclusion_mask_display.nii.gz
direct_voxel_ULF_only_delta_hf_support_summary.csv
direct_voxel_ULF_only_delta_hf_support_qc.json
direct_voxel_ULF_only_mapping_qc.json
direct_voxel_ULF_only_generation_manifest.json
```

`direct_voxel_ULF_only_bootstrap_se.nii.gz` and `direct_voxel_ULF_only_permutation_summary.csv` are generated only for the primary branch. Non-primary branches omit these files and record `not_run_nonprimary` in their manifest and QC JSON.

For continuous/statistical NIfTI outputs, voxels outside the model support are written as `NaN`, not `0`. This applies to coefficient, sweet/sour, stability, bootstrap SE, HF-overlap fraction, smoothed-display, and homologous-display statistical maps outside `Omega_ULF_tau` or outside the right-canonical candidate grid. `0` is reserved for true zero-valued estimates inside support. Integer coverage/count maps and binary/exclusion display masks remain `0` outside support because their data type and semantics are count/false rather than continuous effect.

Output semantics:

- `direct_voxel_ULF_only_coverage.nii.gz` stores `Coverage_ULF_tau(v)=sum_i I[X_ULF_only_i(v, phase,tau)>tau]`. Use `int16`.
- `direct_voxel_ULF_only_coef.nii.gz` stores `rho_ULF(v)` for the executed `partial_spearman/` estimator. Optional future OLS outputs would store `theta_ULF(v)`.
- `direct_voxel_ULF_only_sweet_sour.nii.gz` stores benefit-oriented `M_ULF(v)`. Positive values indicate ULF-only benefit-associated voxels.
- `direct_voxel_ULF_only_stability.nii.gz` stores LOOCV training-fold direction stability of `M_ULF(v)>0` or `M_ULF(v)<0`, depending on display class. It is not a p value.
- `direct_voxel_ULF_only_bootstrap_se.nii.gz` stores full-process bootstrap standard deviation of the estimator map for the primary branch only.
- `direct_voxel_ULF_only_scores.csv` stores patient-level scores, including `branch`, `branch_role`, `delta_hfscore_role`, `ULFScore_mean_main`, `DeltaHFScore` when applicable, `Y_HF_ref`, `HF_out_support_fraction`, `score_map_source`, `n_valid_score_voxels`, and `is_primary_score`.
- `direct_voxel_ULF_only_loocv_predictions.csv` stores held-out predictions, observed raw outcome, branch-specific nuisance-only prediction, `ULFScore_mean_main`, `DeltaHFScore` when applicable, HF support burden fields, and residuals.
- `direct_voxel_ULF_only_permutation_summary.csv` stores Freedman-Lane permutation summary for the primary branch only.
- HF-overlap files store subject-level and cohort-level voxels excluded from the ULF-only predictor because both HF and ULF are active at the branch tau.
- DeltaHFScore support files store the in-support and out-of-support HF component exposure used to determine whether `DeltaHFScore` is within the learned HF model support.
- `direct_voxel_ULF_only_mapping_qc.json` stores endpoint/tau/estimator QC, including patient inclusion, candidate mask size, coverage distribution, `Omega_ULF_tau` voxel count, HF-overlap exclusion volume, HF out-of-support burden, degenerate voxels, NaN handling, zero-exposure score counts, `corr(ULFScore_mean_main, Y_HF_ref)`, `corr(ULFScore_mean_main, DeltaHFScore)`, `corr(Y_HF_ref, DeltaHFScore)`, coefficient signs, VIF or equivalent collinearity diagnostics, flip deformation audit metrics, and design-matrix dimensions.
- `direct_voxel_ULF_only_generation_manifest.json` stores provenance, parameters, code version, conda environment, package state, random seeds, visit labels, same-day immediate reference confirmation, component-proxy labels, and runtime profile.

Primary statistical maps are unsmoothed. Display smoothing is generated only after coefficient estimation and must not be used for ULFScore, LOOCV, permutation, bootstrap, or jitter:

```text
display_smooth_fwhm1mm/
display_smooth_fwhm2mm/
```

Display maps should overlay:

```text
ULF-only sweet/sour map
HF-overlap exclusion coverage/fraction map
HF out-of-support burden summaries
STN/SNr anatomical outlines
STNSNrplus territory background
```

## Left/Right Flip Deformation Audit

`ea_flip_lr_nonlinear` remains the only supported left/right flip method. The audit records warnings but does not automatically exclude subjects unless there is an input integrity failure.

QC metrics:

```text
input/output grid and affine
finite voxel count
nonzero voxel count
max, p95, p99, sum
suprathreshold volume at 180 / 200 / 220 V/m
intensity-weighted centroid
L-to-R output overlap with right canonical brainmask
component label, phase label, and side metadata
```

Empty images, all-NaN images, non-finite values, missing paths, and obvious path/component mismatches are hard failures. Ordinary deformation differences are warnings.

## Spatial Jitter QC Sensitivity

Spatial jitter is a robustness stress test applied to accepted e-field inputs. It is not an automatic localization/normalization QC procedure and is not an input-validity gate. It is run only for the selected primary ULF branch unless an endpoint is explicitly promoted to co-primary.

```text
formal jitter resamples: B = 1000
smoke jitter resamples:  B = 100
seed: 42
FWHM: 2 mm
sigma: 2 / 2.355 = 0.849 mm
```

For each jitter iteration, draw an independent 3D translation vector for each subject-side HF and ULF component e-field. Apply translation-only e-field resampling with linear interpolation and outside fill value `0`. Then rebuild ULF-only exposure, HF-overlap exclusion, `Omega_ULF_tau`, `DeltaHFScore`, HF out-of-support support QC, full-sample map, ULF scores, and LOOCV validation metrics.

Do not save every jittered NIfTI map. Save a summary table, map correlation/stability summary, and voxel-wise jitter standard deviation map.

## Reference-Parameter Coverage

The ULF direct voxel model covers the same direct voxel parameter family as the HF direct voxel model where applicable:

```text
raw sim-efield, not sim-efieldgauss
right canonical voxel grid
ea_flip_lr_nonlinear left/right flip
tau = 180 / 200 / 220 V/m
Coverage>=5
covariate-adjusted partial Spearman
LOOCV
Freedman-Lane permutation for the primary branch
subject-level bootstrap for the primary branch
2 mm FWHM spatial jitter QC
display smoothing FWHM 1 mm and 2 mm, display only
```

Documented-only items for the current ULF direct voxel execution:

```text
Coverage>=6 optional sensitivity: documented only; no current ULF direct voxel outputs
Coverage>=8 / 50% E-field rule: documented only; primary rule remains Coverage>=5
5/7/10-fold CV: documented only; LOOCV is executable
optional OLS supplemental estimator: documented only; not run in the current execution
OSS-DBS: not part of direct voxel; belongs to normative fiber / activation sensitivity
paper-like spatial similarity score sensitivity: not included; ULFScore_mean_main is the primary score
automatic localization / electrode reconstruction QC: not included; prior manual QC is assumed
```

## Interpretation Boundary

This model estimates HF-state-adjusted ULF-only add-on association. It is not an anatomic SNr gain model. Voxels co-activated by HF and ULF are treated as HF-dominant for the primary analysis, so the ULF map represents regions uniquely recruited by ULF stimulation after accounting for HF clinical state and model-predicted HF efficacy changes.

Because the immediate HF+ULF endpoint and the HF-only 3-month clinical reference are measured on the same day, the immediate model can be interpreted as a same-day acute add-on association. The chronic model remains a post-add-on follow-up association.

Because the cohort has `n=16`, the result is hypothesis-generating. A non-significant LOOCV result should not be interpreted as proof that no biological ULF add-on sweet spot exists. The QC report must include the association between `ULFScore_mean_main`, `Y_HF_ref`, and `DeltaHFScore`, the support coverage of `DeltaHFScore`, plus a basic collinearity diagnostic for the final prediction model.

Interpret as:

```text
After accounting for same-day or pre-ULF HF state and modeled HF efficacy changes,
additional ULF-only exposure in this territory is associated with better or worse
post-HF+ULF outcome.
```

Do not interpret as:

```text
The displayed voxels prove an anatomic SNr-specific causal effect.
HF-overlap voxels have no ULF biological effect.
HF-component exposure outside the learned HF map has no biological effect.
DeltaHFScore fully removes all HF contribution when out-of-support burden is large.
```

## Execution Efficiency

The optimized implementation must preserve the logical full-process semantics described above. In particular, LOOCV training folds still define their own HF adjustment map, `DeltaHFScore`, HF support QC, `Omega_ULF_tau`, ULF voxel map, ULF scores, and held-out predictions. Formal Freedman-Lane permutation and subject-level bootstrap still use `B=10000` and seed `42` for the primary branch. Smoke runs use `B=1000` for permutation/bootstrap and `B=100` for jitter.

### Equivalence Contract

Optimization may reuse mathematically invariant cached subcomputations, but it must not use full-sample ranks, full-sample training masks, approximate ranks, adaptive early stopping, changed tau thresholds, changed estimators, changed HF support rules, or reduced formal resampling counts to gain speed.

Numerical reductions should use `float64` where feasible. Final NIfTI outputs use `float32` for coefficient, sweet/sour, stability, and bootstrap SE maps, and `int16` for coverage and binary/exclusion masks.

### Preprocessing Sidecar Cache

Preferred formal-loop input:

```text
E_ULF_component_<phase>_float32_voxel_major.npy
E_HF_component_<phase>_on_ulf_grid_float32_voxel_major.npy
E_HF_component_<phase>_on_hf_score_grid_float32_voxel_major.npy
E_HF_only_reference_on_hf_score_grid_float32_voxel_major.npy
X_ULF_only_tau180_<phase>_float32_voxel_major.npy
X_ULF_only_tau200_<phase>_float32_voxel_major.npy
X_ULF_only_tau220_<phase>_float32_voxel_major.npy
S180_ULF_only_<phase>_bool.npy
S200_ULF_only_<phase>_bool.npy
S220_ULF_only_<phase>_bool.npy
HF_overlap_tau180_<phase>_bool.npy
HF_overlap_tau200_<phase>_bool.npy
HF_overlap_tau220_<phase>_bool.npy
ulf_candidate_ijk.npy
ulf_candidate_xyz_mm.npy
hf_score_support_ijk.npy
hf_score_support_xyz_mm.npy
candidate_mask_metadata.json
hf_support_metadata.json
```

Voxel-major layout is preferred because voxel chunks are contiguous on disk. MAT and compressed NPZ files may be retained for archival, compatibility, and debugging. Compressed NPZ must not be the primary random-access input inside formal permutation, bootstrap, or jitter loops.

### Coverage And Fold Mask Cache

For each tau and phase, precompute:

```text
S_tau(v, i, phase) = I[X_ULF_only_i(v, phase,tau) > tau]
Coverage_tau_all(v, phase) = sum_i S_tau(v, i, phase)
Coverage_tau_fold_h(v, phase) = Coverage_tau_all(v, phase) - S_tau(v, h, phase)
Omega_ULF_tau_fold_h(phase) = {v : Coverage_tau_fold_h(v, phase) >= 5}
```

`HF_overlap_tau*_bool` can be cached because it depends only on accepted HF/ULF component exposures and tau, not on outcome.

### Vectorized Partial Spearman Kernel

For every training fold, ranks are computed within the training set only. Full-sample ranks are prohibited for LOOCV map fitting, permutation map fitting, bootstrap maps, and jitter resamples.

The DeltaHF-adjusted core branch residualizes both outcome and exposure against:

```text
rank(Y_HF_ref_train)
rank(DeltaHFScore_train)
```

The no-DeltaHF core branch residualizes against:

```text
rank(Y_HF_ref_train)
```

### Fold-Level Score Operator For Permutation

Formal Freedman-Lane permutation for the primary branch may use a fold-level score operator, but it must remain logically equivalent to recomputing the full ULF map and `ULFScore_mean_main` for every permuted outcome.

Each permutation must have its own:

```text
DeltaHFScore if recomputed under the fold/HF map semantics
rho_ULF(v)
M_ULF(v)
V_score
ULFScore_mean_main
held-out prediction
LOOCV statistic
```

### Bootstrap Efficiency

Subject-level bootstrap remains a full-process map stability analysis for the primary branch. It must rebuild bootstrap `DeltaHFScore`, HF support QC, `Omega_ULF_tau`, `rho_ULF`, and `M_ULF`. Bootstrap SE is accumulated by streaming Welford updates. The implementation must not store 10000 bootstrap maps.

### Spatial Jitter Efficiency

Jitter changes e-field geometry. Primary `X`-derived caches are invalid under jitter and must not be reused as if exposure were unchanged. Each jitter iteration must rebuild HF component exposure, ULF component exposure, HF-overlap exclusion, ULF-only exposure, candidate mask, `Omega_ULF_tau`, `DeltaHFScore`, HF support QC, map, scores, and LOOCV metrics.

### Prohibited Speed Shortcuts

Formal runs prohibit:

```text
adaptive permutation early stopping
reduced formal B
changed tau thresholds
changed Coverage>=5 rule
changed estimator
full-sample ranks inside LOOCV/permutation/bootstrap
approximate ranks
using anatomical overlay masks as the analysis mask
dropping requested jitter QC
using a tau-independent X_ULF_only matrix
using total ULF exposure in place of ULF-only exposure for the primary branch
including HF-overlap voxels in the primary ULF predictor
expanding the locked HF score support after seeing ULF results
imputing or smoothing HF map coefficients outside V_HF_score
using compressed NPZ as the random-access formal-loop input
```

### Runtime Profile

`direct_voxel_ULF_only_generation_manifest.json` should include:

```json
{
  "runtime_profile": {
    "preprocess_s": null,
    "sidecar_write_s": null,
    "load_design_s": null,
    "observed_loocv_s": null,
    "permutation_s": null,
    "bootstrap_s": null,
    "jitter_s": null,
    "display_qc_s": null,
    "n_voxels_candidate": null,
    "n_voxels_tau200_mean": null,
    "n_voxels_tau200_min": null,
    "n_voxels_tau200_max": null,
    "n_hf_overlap_tau200_mean": null,
    "hf_out_support_fraction_summary": null,
    "python_jobs": null,
    "blas_threads": null,
    "memmap_sidecars": [],
    "bootstrap_finite_count_summary": null
  }
}
```

### Equivalence And Regression Tests

Before formal runs, compare brute-force and optimized implementations on a deterministic subset:

```text
B_perm = 20
B_boot = 20
n_voxel_subset = 100 to 1000
seed = 42
```

Compare:

```text
fold-specific DeltaHFScore
fold-specific HF out-of-support burden
fold-specific Omega_ULF_tau
HF-overlap exclusion masks
partial Spearman rho map
benefit-oriented M_ULF map
ULFScore_mean_main
LOOCV held-out predictions
LOOCV Spearman rho
permutation null statistics
bootstrap SE for finite voxels
```

Required tolerances:

```text
exact equality for masks, subject IDs, voxel IDs, and split indices
near equality for float outputs under float64 reductions
same NaN/degenerate voxel locations
same plus-one p value for the deterministic small test
```

## Execution Priority And Gatekeeping

Run the ULF direct voxel analysis as a gatekeeping sequence. Do not run all sensitivity analyses at once.

### Round 0: Input Readiness

Run:

```text
clinical table audit:
  Y_HF_ref exists at T2 HF-only 3-month same-day reference
  Y_post_immediate exists at T2 HF+ULF same-day immediate endpoint, if modeled
  Y_post_chronic exists at T3 HF+ULF 3-month endpoint, if modeled
  DeltaHFScore inputs exist
  ID joins to imaging subject
  scale direction is defined

visit chronology audit:
  T0 preoperative baseline exists when available
  T1 1-month HF immediate opening visit exists when available
  T2 HF-only 3-month and HF+ULF immediate are same-day or same-session
  T3 HF+ULF 3-month follow-up phase is labeled

e-field availability check:
  HF-only T2 reference e-fields exist
  HF+ULF immediate HF-component e-fields exist when immediate endpoint is modeled
  HF+ULF immediate ULF-component e-fields exist when immediate endpoint is modeled
  HF+ULF chronic HF-component e-fields exist when chronic endpoint is modeled
  HF+ULF chronic ULF-component e-fields exist when chronic endpoint is modeled
  all matches are unique
  raw sim-efield is used

component audit:
  HF frequency >= 100 Hz
  ULF frequency <= 50 Hz
  mixed or proxy component fields are labeled

locked HF model audit:
  hf_3m_direct_voxel_model tau200/partial_spearman source exists
  HFScore_mean_main and M_HF support are valid
  fold-specific map generation is available for LOOCV DeltaHFScore
  hf_prediction_validity_status is recorded
```

Enter Round 1 only if all primary endpoint subjects have complete clinical and e-field inputs, same-day immediate reference is confirmed when immediate endpoint is run, and valid sample size is at least 12.

### Round 1: Preprocessing, Overlap QC, And HF Support QC

Run preprocessing sidecars and flip audit. Confirm:

```text
ULF component matrix is non-empty
X_ULF_only_tau200 matrix is non-empty
HF_overlap outputs are valid even if overlap is zero
tau200 Coverage>=5 Omega_ULF is non-empty
each subject has nonzero HF component exposure
each subject has nonzero or explicitly absent ULF-only exposure
DeltaHFScore support summary is generated
HF_out_support_fraction is not extreme enough to invalidate HF adjustment
```

If ULF-only exposure is empty for most subjects, stop and report that the primary ULF-only predictor is not modelable. If HF out-of-support burden is large, continue only as exploratory or add the predeclared HF-out-of-support sensitivity.

### Round 2: Core Chronic Observed LOOCV

Run first unless immediate endpoint has been explicitly promoted:

```text
endpoint = MDS-UPDRS III total chronic HF+ULF 3-month score
core branches =
  tau200 / partial_spearman / delta_hf_adjusted
  tau200 / partial_spearman / no_delta_hf
score = ULFScore_mean_main
covariates =
  delta_hf_adjusted: Y_HF_ref + DeltaHFScore
  no_delta_hf:       Y_HF_ref
validation = LOOCV
```

After both core branches finish, use the locked HF result to record:

```text
ulf_primary_branch
delta_hfscore_role
branch_role_decision_reason
```

Enter Round 3 only if the branch selected as primary has all folds complete, `ULFScore_mean_main` is not constant, held-out predictions are finite, LOOCV rho is positive, `Q2 > 0`, and the ULFScore model improves over its branch-specific nuisance-only baseline.

Stop if both core chronic branches are negative, near-constant, unsupported by required inputs, or dominated by one high-leverage subject. Do not run `tau180/tau220` to search for a better threshold after core-branch failure.

### Round 2b: Same-Day Immediate Observed LOOCV

Run as key secondary, or as co-primary only if explicitly declared:

```text
endpoint = MDS-UPDRS III total same-day immediate HF+ULF score
core branches =
  tau200 / partial_spearman / delta_hf_adjusted
  tau200 / partial_spearman / no_delta_hf
score = ULFScore_mean_main
covariates =
  delta_hf_adjusted: Y_HF_ref + DeltaHFScore_immediate
  no_delta_hf:       Y_HF_ref
validation = LOOCV
```

Also run the same-day gain sensitivity if complete:

```text
endpoint = Gain_immediate
branch = tau200 / partial_spearman_gain_endpoint
```

The immediate endpoint may enter smoke resampling if it passes the same criteria as chronic observed LOOCV.

### Round 3: Equivalence And Smoke Resampling

Run:

```text
deterministic equivalence test
smoke permutation B=1000
smoke bootstrap B=1000
smoke jitter B=100
```

Enter Round 4 only if optimized and brute-force paths match, smoke resampling runs without artifacts, bootstrap finite-count distribution is acceptable, and jitter does not reverse the signal direction.

### Round 4: Formal Permutation

Run only for the branch recorded as primary by the branch-role resolver:

```text
tau200 / partial_spearman
branch_role = ulf_primary_branch
B = 10000
seed = 42
statistic = LOOCV Spearman rho
```

Proceed to bootstrap if the permutation completes, p value is finite, and the observed signal remains positive. If `p_perm > 0.10` and `Q2 <= 0`, stop heavy analyses and produce a minimal exploratory report.

### Round 5: Formal Bootstrap

Run:

```text
tau200 / partial_spearman
branch_role = ulf_primary_branch
B = 10000
seed = 42
```

Proceed only if bootstrap finite counts are acceptable, core sign stability is interpretable, and most bootstrap maps are not empty.

### Round 6: Formal Spatial Jitter

Run:

```text
tau200 / partial_spearman
branch_role = ulf_primary_branch
B = 1000
FWHM = 2 mm
```

If jitter map correlation is near zero or the signal direction reverses, downgrade conclusions to spatially fragile exploratory association.

### Round 7: Tau Sensitivity

Run observed LOOCV only:

```text
tau180 / partial_spearman
tau220 / partial_spearman
run for both delta_hf_adjusted and no_delta_hf core roles when inputs allow
```

Do not run formal permutation/bootstrap for tau sensitivity. Interpret tau180/tau220 as exposure-definition robustness checks, not threshold search.

### Round 8: Additional Sensitivities

Run only after the primary branch is interpretable:

```text
non-selected core branch comparison
gain endpoint sensitivity
total ULF exposure sensitivity
HF-out-of-support covariate sensitivity when support burden is nontrivial
Y_base-added collinearity sensitivity if baseline data are complete
```

The `Y_base`-added sensitivity is:

```text
delta_hf_adjusted:
  Y_post ~ ULFScore_mean_main + Y_HF_ref + DeltaHFScore + Y_base

no_delta_hf:
  Y_post ~ ULFScore_mean_main + Y_HF_ref + Y_base
```

It is a collinearity/stability check, not a replacement primary model.

### Round 9: Display And Final Manifests

Generate display smoothing, bilateral homologous display maps, HF-overlap exclusion overlays, HF support burden summaries, STN/SNr outlines, PDF QC, and final manifests only after statistical branches complete. Display outputs must not feed back into ULFScore, LOOCV, permutation, bootstrap, or jitter.

### Round 10: Optional Future Analyses

Not part of the current executable mainline:

```text
OLS ANCOVA
Coverage>=6
Coverage>=8 / 50% rule
5/7/10-fold CV
OSS-DBS direct voxel analysis
paper-like spatial similarity score
automatic localization / electrode reconstruction QC
```

### Recommended First Batch

The first practical run should cover only:

```text
Round 0
Round 1
Round 2 chronic observed LOOCV
Round 2b immediate observed LOOCV, if same-day immediate data are complete
Round 3 smoke only
```

Concrete first-batch scope:

```text
MDS-UPDRS III total chronic endpoint
MDS-UPDRS III total same-day immediate endpoint, if complete
tau200
partial_spearman
Coverage>=5
ULF-only exposure
HF-overlap exclusion
DeltaHFScore-adjusted model
HF out-of-support support QC
ULFScore_mean_main
LOOCV
covariate-only comparison
equivalence test
smoke permutation B=1000
smoke bootstrap B=1000
smoke jitter B=100
basic QC JSON + manifest
```
