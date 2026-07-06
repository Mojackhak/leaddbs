# HF-Status-Resolved ULF-Only Add-On Gain Normative Connectome Fiber Model — Revised

Version: 2026-07-05 revised specification
Scope: ULF add-on normative connectome fiber-level model, aligned to `hf_3m_normative_connectome_fiber_model.md`.

---

## 1. Research Question

Which ULF-only normative connectome streamlines are associated with additional clinical benefit after ULF stimulation is added to HF stimulation, after adjusting for:

```text
1. the patient's pre-ULF HF clinical state, and
2. the matched HF normative fiber model's predicted change in HF-component engagement.
```

This is a right-canonical, full-connectome, fiber-level model. Individual streamlines from public structural connectomes are the primary modeling units. Target atlases are used only after modeling for endpoint labels, anatomical enrichment, QC, display grouping, and interpretation. They do not define the primary candidate universe or primary predictors.

Frequency definitions:

```text
HF  = high-frequency stimulation component, frequency_Hz >= 100
ULF = ultra-low-frequency stimulation component, frequency_Hz <= 50
```

The primary predictor represents streamlines uniquely recruited by the ULF component after HF-overlap streamlines are assigned to HF adjustment through `DeltaHFScore`.

---

## 2. Study Timeline And Endpoint Definitions

The clinical timeline is explicitly modeled as:

```text
T0:
  preoperative baseline assessment

T1:
  postoperative 1-month HF immediate activation assessment

T2:
  3 months after HF activation
  HF-only 3-month follow-up assessment
  same-day switch to HF+ULF
  same-day HF+ULF immediate assessment

T3:
  3 months after HF+ULF switch
  HF+ULF 3-month follow-up assessment
```

The immediate HF+ULF outcome and the HF-only 3-month clinical reference state are measured on the same day at `T2`. Therefore, the immediate endpoint is a valid same-day acute add-on endpoint, not a cross-day comparator.

Use endpoint-specific variable names:

```text
Y_HF_ref_T2_domain =
  raw HF-only 3-month score measured at T2 immediately before same-day HF+ULF switch

Y_HFplusULF_immediate_T2_domain =
  raw same-day HF+ULF immediate score after switching to HF+ULF at T2

Y_HFplusULF_3m_T3_domain =
  raw HF+ULF 3-month score measured at T3
```

Two endpoint families are modeled separately.

### 2.1 Chronic endpoint

```text
Y_post = Y_HFplusULF_3m_T3_domain
Y_HF_ref = Y_HF_ref_T2_domain
DeltaHFScore = DeltaHFScore_chronic_domain
```

Interpretation:

```text
sustained HF-state-adjusted ULF add-on association after 3 months of HF+ULF exposure
```

### 2.2 Immediate endpoint

```text
Y_post = Y_HFplusULF_immediate_T2_domain
Y_HF_ref = Y_HF_ref_T2_domain
DeltaHFScore = DeltaHFScore_immediate_domain
```

Interpretation:

```text
same-day HF-state-adjusted ULF acute add-on association
```

### 2.3 Endpoint hierarchy

Default first-pass endpoints:

```text
Primary formal endpoint:
  MDS-UPDRS III total chronic HF+ULF 3-month score

Key secondary endpoint:
  MDS-UPDRS III total same-day HF+ULF immediate score, if available
```

The immediate endpoint may be promoted to co-primary only by an explicit pre-run decision. If it is not promoted, it receives observed LOOCV and optional smoke resampling, but not default formal `B=10000` resampling.

### 2.4 Add-on gain sensitivity endpoints

Because the primary model is a raw post-score ANCOVA-style model, add-on gain should be reported as sensitivity.

For lower-is-better scales:

```text
Gain_immediate_i = Y_HF_ref_T2_i - Y_HFplusULF_immediate_T2_i
Gain_chronic_i   = Y_HF_ref_T2_i - Y_HFplusULF_3m_T3_i
```

For higher-is-better scales:

```text
Gain_immediate_i = Y_HFplusULF_immediate_T2_i - Y_HF_ref_T2_i
Gain_chronic_i   = Y_HFplusULF_3m_T3_i - Y_HF_ref_T2_i
```

In all gain definitions:

```text
positive Gain = improvement after adding ULF
```

Gain sensitivity model:

```text
Gain_i = alpha
       + delta * NetULFFiberScore_i
       + gamma * DeltaHFScore_i
       + error_i
```

This sensitivity checks whether the primary raw post-score model agrees with a direct within-subject add-on gain formulation.

---

## 3. Inputs

Required inputs:

```text
Public Lead-DBS structural connectomes:
  PPMI 85
  MGH-USC HCP 32
  dTOR-985 Full

HF+ULF programming split into HF and ULF components
Raw sim-efield or accepted e-field-like exposure maps for HF component and ULF component
HF-only reference e-fields from the pre-ULF HF-only phase
Raw HF-only and HF+ULF clinical scores
Normative HF fiber-level model outputs from hf_3m_normative_connectome_fiber_model.md
Connected-region atlases for endpoint labels, anatomical enrichment, and STN/SNr overlays
```

E-field rules:

```text
use raw sim-efield or explicitly accepted e-field-like exposure maps
record units as V/m
record frequency, pulse width, amplitude, contacts, side, phase, and component labels
missing or multiply matched e-fields fail the endpoint/run
subjects are not silently excluded
missing e-fields are not automatically created by this model
```

Component-specific proxy fields are allowed only if the manifest records the proxy status:

```text
component_field_type:
  true_component_separable
  interleaved_proxy
  synchronous_mixed_proxy
  ambiguous_component_assignment
```

If a majority of cases use proxy fields, interpretation must use:

```text
ULF-component proxy exposure association
```

rather than:

```text
direct ULF biophysical field association
```

---

## 4. Locked HF Adjustment Source

The ULF model may enter formal analysis only after the matched HF normative fiber model source for `DeltaHFScore` has been locked.

Locked HF source:

```text
model_family = hf_3m_normative_connectome_fiber_model
connectome = connectome-matched
branch = peak_efield_tau800_primary
tau = 800 V/m
coverage = Coverage>=5
estimator = partial_spearman
score = NetFiberScore
F+ = top 1% positive HF fibers
F- = top 0.5% sour HF fibers
SweetPeak5/SourPeak5 = mean top 5% patient-specific weighted selected fibers
map source in LOOCV = training-fold HF model
full-sample HF model = descriptive scores only
```

Connectome-matched rule:

```text
ULF/PPMI uses HF/PPMI DeltaHFScore
ULF/MGH  uses HF/MGH  DeltaHFScore
ULF/dTOR uses HF/dTOR DeltaHFScore
```

A shared dTOR-HF adjustment across all ULF connectomes may be reported only as a sensitivity:

```text
shared_dTOR_HF_adjustment_sensitivity
```

Do not assign the DeltaHF-adjusted ULF branch as the interpretive primary branch unless the matched HF normative branch has:

```text
observed LOOCV completed
non-empty candidate fibers in all relevant folds
NetFiberScore nonzero variance
finite LOOCV predictions
interpretable Q2 against Y_base-only baseline
no severe selected-fiber instability
no severe plain-control replacement
```

The ULF normative fiber implementation runs the DeltaHF-adjusted and no-DeltaHF branches as an equal-status core branch pair when inputs are available. The model report then records which branch is the interpretive primary branch using the locked HF result:

```text
if HF model is predictive_valid:
  ulf_primary_branch = delta_hf_adjusted
  delta_hfscore_role = primary nuisance adjustment
  no_delta_hf_role   = sensitivity

if HF model is stable_nonpredictive:
  ulf_primary_branch = no_delta_hf
  delta_hfscore_role = sensitivity / compatibility adjustment
  no_delta_hf_role   = primary

if HF model is unstable_or_failed:
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

If the matched HF branch fails or is technically degenerate, `DeltaHFScore` must be labeled as an unstable generated covariate and cannot define the primary ULF interpretation.

---

## 5. Feature Construction

The executable feature space is a right-canonical streamline feature space. Left-sided stimulation is flipped into the right canonical space with `ea_flip_lr_nonlinear` and sampled along the same right-sided streamline features.

For patient `i` and right-canonical streamline `l`:

```text
E_HF_R_i(l)       = peak HF-component exposure along right canonical fiber l
E_HF_L_to_R_i(l)  = peak left HF-component exposure after nonlinear L-to-R flip
E_ULF_R_i(l)      = peak ULF-component exposure along right canonical fiber l
E_ULF_L_to_R_i(l) = peak left ULF-component exposure after nonlinear L-to-R flip

X_HF_component_i(l)  = (E_HF_R_i(l)  + E_HF_L_to_R_i(l))  / 2
X_ULF_component_i(l) = (E_ULF_R_i(l) + E_ULF_L_to_R_i(l)) / 2
```

HF-only reference exposure for `DeltaHFScore`:

```text
E_HFonly_ref_R_i(l)      = peak HF-only reference exposure along right canonical fiber l
E_HFonly_ref_L_to_R_i(l) = peak left HF-only reference exposure after nonlinear L-to-R flip

X_HFonly_ref_i(l) =
  (E_HFonly_ref_R_i(l) + E_HFonly_ref_L_to_R_i(l)) / 2
```

Same-side same-frequency alternating subprograms:

```text
primary rule:
  combine same-side same-frequency subprogram e-fields by voxel-wise maximum
  before streamline sampling

allowed optimization:
  streamline-wise maximum only if exact-equivalence testing proves equality
  against voxel-wise maximum on a deterministic subset
```

Exposure is not scaled by frequency or pulse width in the peak E-field branch. Frequency classifies the component as HF or ULF; pulse width and frequency are recorded in provenance.

---

## 6. ULF-Only Exposure And Candidate Fibers

ULF-only exposure is tau-specific because tau defines both component activity and HF-overlap exclusion.

For each tau:

```text
tau_primary = 800 V/m
tau_sensitivity = 1500 V/m

ULF_touched_i(l,tau) = X_ULF_component_i(l) > tau
HF_touched_i(l,tau)  = X_HF_component_i(l)  > tau

X_ULF_only_i(l,tau) =
  X_ULF_component_i(l), if ULF_touched_i(l,tau) and not HF_touched_i(l,tau)
  0,                   otherwise
```

If a streamline is touched by both HF and ULF components at the branch tau, it is assigned to HF adjustment and excluded from the primary ULF-only predictor.

Candidate rule:

```text
Coverage_ULF_tau(l) = sum_i I[X_ULF_only_i(l,tau) > tau]
F_candidate_ULF_tau = {l: Coverage_ULF_tau(l) >= 5}
```

The candidate universe is the full public connectome, not target-restricted seed-target tracts.

Important interpretation rule:

```text
For ULF, tau is part of the exposure definition.
It is not merely a candidate coverage threshold.
```

Therefore:

```text
ulf_peak_efield_tau1500_sensitivity
```

is a ULF-only exposure-definition sensitivity, not a simple threshold robustness check.

---

## 7. DeltaHFScore: Matched HF Normative Fiber Score Projection

`DeltaHFScore` is a generated nuisance covariate derived from the locked HF normative fiber model.

For each LOOCV training fold, define the training-fold HF score operator:

```text
O_HF_fold = {
  M_HF_fold(l),
  F+_HF_fold,
  F-_HF_fold,
  SweetPeak5 rule,
  SourPeak5 rule,
  NetFiberScore rule
}
```

For any HF exposure matrix `E`, define:

```text
S_HF_norm_fiber(E; O_HF_fold)_i = NetFiberScore_i obtained by applying
                                  the locked training-fold HF operator
                                  to exposure E for patient i
```

Explicitly:

```text
SweetWeighted_HF_i(l) = X_E_i(l) * M_HF_fold(l),       l in F+_HF_fold
SourWeighted_HF_i(l)  = X_E_i(l) * [-M_HF_fold(l)],    l in F-_HF_fold

SweetPeak5_HF_i = mean top 5% largest SweetWeighted_HF_i(l)
SourPeak5_HF_i  = mean top 5% largest SourWeighted_HF_i(l)

S_HF_norm_fiber(E; O_HF_fold)_i = SweetPeak5_HF_i - SourPeak5_HF_i
```

Then:

```text
DeltaHFScore_chronic_i =
  S_HF_norm_fiber(E_HF_component_T3_HFplusULF; O_HF_fold)_i
  - S_HF_norm_fiber(E_HFonly_ref_T2; O_HF_fold)_i

DeltaHFScore_immediate_i =
  S_HF_norm_fiber(E_HF_component_T2_HFplusULF_immediate; O_HF_fold)_i
  - S_HF_norm_fiber(E_HFonly_ref_T2; O_HF_fold)_i
```

Rules:

```text
Do not refit the HF model using HF+ULF outcomes.
Do not refit the HF model using HF+ULF exposure as the HF training exposure.
Do not use full-sample HF M_HF, F+, or F- to score held-out patients in LOOCV.
Do not replace the HF normative score with a direct voxel HF score.
Do not replace the connectome-matched HF score with another connectome unless running an explicitly labeled sensitivity.
```

`DeltaHFScore` may be z-scored inside each training fold for numerical stability. The z-scoring parameters are learned on training patients only and applied to the held-out patient. No fixed biological scaling coefficient is imposed before regression.

---

## 8. DeltaHFScore Support And Out-Of-Support HF Exposure

### 8.1 Support definitions

The locked HF 3-month model has a finite learned support.

For each HF training fold:

```text
F_HF_candidate_fold =
  candidate fibers satisfying HF tau800 Coverage>=5 in the HF training fold

F_HF_valid_fold =
  F_HF_candidate_fold intersect fibers with finite non-degenerate M_HF_fold(l)

F_HF_score_fold =
  F+_HF_fold union F-_HF_fold
```

`DeltaHFScore` is calculated only through the locked HF scoring operator:

```text
F_HF_score_fold = F+_HF_fold union F-_HF_fold
```

Fibers outside `F_HF_score_fold` do not contribute to `DeltaHFScore`.

This is not an imputation that the fiber has no biological HF effect. It only means:

```text
outside the locked HF NetFiberScore operator
```

### 8.2 If HF+ULF HF-component exposure touches fibers outside HF-3m coverage

If `E_HF_component` during HF+ULF touches fibers outside the HF-3m model's coverage or score support:

```text
Do not extrapolate M_HF to those fibers.
Do not smooth weights onto those fibers.
Do not assign nearest-neighbor HF weights.
Do not add those fibers into F+ or F-.
Do not retrain the HF model using HF+ULF exposure or outcome.
```

The primary `DeltaHFScore` remains:

```text
DeltaHFScore_in_support =
  S_HF_norm_fiber(E_HF_component; O_HF_fold)
  - S_HF_norm_fiber(E_HFonly_ref; O_HF_fold)
```

where `S_HF_norm_fiber` uses only `F_HF_score_fold`.

All HF-component exposure outside the learned HF support is reported as QC, not silently treated as fully controlled.

### 8.3 Required support QC metrics

For each subject, endpoint, connectome, branch, and LOOCV fold, compute:

```text
HF_component_total_touched_count_tau800
HF_component_total_exposure_sum_tau800
HF_component_total_exposure_top5_tau800

HF_component_in_HF_candidate_count_tau800
HF_component_in_HF_candidate_sum_tau800
HF_component_in_HF_candidate_top5_tau800

HF_component_in_HF_valid_count_tau800
HF_component_in_HF_valid_sum_tau800
HF_component_in_HF_valid_top5_tau800

HF_component_in_HF_selected_count_tau800
HF_component_in_HF_selected_sum_tau800
HF_component_in_HF_selected_top5_tau800

HF_component_out_HF_candidate_count_tau800
HF_component_out_HF_candidate_sum_tau800
HF_component_out_HF_candidate_top5_tau800

HF_component_out_HF_selected_count_tau800
HF_component_out_HF_selected_sum_tau800
HF_component_out_HF_selected_top5_tau800

HF_out_candidate_fraction_tau800 =
  HF_component_out_HF_candidate_sum_tau800
  / max(HF_component_total_exposure_sum_tau800, epsilon)

HF_out_selected_fraction_tau800 =
  HF_component_out_HF_selected_sum_tau800
  / max(HF_component_total_exposure_sum_tau800, epsilon)
```

Write these outputs:

```text
normative_ULF_fiber_delta_hf_support_summary.csv
normative_ULF_fiber_delta_hf_support_qc.json
```

Interpret `HF_out_candidate_fraction_tau800` as the main support failure indicator.

Interpret `HF_out_selected_fraction_tau800` more cautiously, because NetFiberScore intentionally uses only selected sweet/sour HF fibers. High out-selected exposure is expected when stimulation touches many nonscoring fibers; high out-candidate exposure is more concerning.

### 8.4 Gatekeeping rules for out-of-support exposure

Default gates:

```text
Proceed without downgrading:
  cohort median HF_out_candidate_fraction_tau800 <= 0.20
  and no more than 25% of subjects have HF_out_candidate_fraction_tau800 > 0.50

Proceed but downgrade interpretation:
  cohort median HF_out_candidate_fraction_tau800 > 0.20
  or more than 25% of subjects have HF_out_candidate_fraction_tau800 > 0.50

Do not present the ULF branch as formally HF-adjusted:
  HF_out_candidate_fraction_tau800 is extreme enough that DeltaHFScore no longer represents the HF-component change for many subjects
  or HF component programming moved mainly into territory never covered by the locked HF model
```

If out-of-support exposure is substantial, add a QC-only or secondary sensitivity model:

```text
Y_post ~ NetULFFiberScore
       + Y_HF_ref
       + DeltaHFScore_in_support
       + PlainHFOutSupportTop5
```

where:

```text
PlainHFOutSupportTop5 =
  mean top 5% X_HF_component_i(l)
  among HF-component-touched fibers outside F_HF_candidate_fold
```

Do not force this variable into the main model if it is highly collinear with `NetULFFiberScore`, `DeltaHFScore`, or `Y_HF_ref`. With `n=16`, it is primarily a diagnostic.

### 8.5 Fibers inside HF candidate support but outside HF selected score support

If a fiber is inside `F_HF_candidate_fold` or `F_HF_valid_fold` but not in `F_HF_score_fold`, it is within the learned HF model universe but outside the HF NetFiberScore operator. It does not contribute to `DeltaHFScore` because the locked HF scoring model did not select it.

This is not a technical failure. Report it as:

```text
in-candidate / non-selected HF-component exposure
```

not as out-of-coverage exposure.

### 8.6 Fibers absent from the public connectome

If an anatomical pathway is not represented by the public connectome, it cannot be scored in either HF or ULF normative models. This is a connectome limitation, not evidence that the pathway is irrelevant.

Report as:

```text
not represented in the normative connectome feature space
```

No imputation is allowed.

---

## 9. Core Statistical Models

### 9.0 Core Branch A: DeltaHF-Adjusted Partial Spearman

The DeltaHF-adjusted fiber-level estimator is nuisance-adjusted partial Spearman.

For each endpoint and candidate fiber `l`:

```text
rho_ULF(l) =
  corr(
    resid(rank(Y_post_i)             ~ rank(Y_HF_ref_i) + rank(DeltaHFScore_i)),
    resid(rank(X_ULF_only_i(l,tau))  ~ rank(Y_HF_ref_i) + rank(DeltaHFScore_i))
  )
```

Ties use average ranks. Degenerate fibers with zero ULF-only exposure variance, zero rank variance, or zero residualized exposure variance are assigned:

```text
rho_ULF(l) = NaN
```

and excluded from selected-fiber sets and scoring.

Benefit-oriented fiber weight:

```text
M_ULF(l) = -rho_ULF(l)   for lower-is-better scales
M_ULF(l) =  rho_ULF(l)   for higher-is-better scales
```

Interpretation:

```text
M_ULF(l) > 0:
  ULF-only exposure to this streamline is benefit-associated

M_ULF(l) < 0:
  ULF-only exposure to this streamline is worse-outcome-associated
```

### 9.1 Patient-level NetULFFiberScore

Within each full-sample map or LOOCV training fold:

```text
F+_ULF = top 1% fibers with largest positive M_ULF(l)
F-_ULF = top 0.5% fibers with most negative M_ULF(l)
```

For each patient:

```text
SweetWeighted_ULF_i(l) = X_ULF_only_i(l,tau) * M_ULF(l),      l in F+_ULF
SourWeighted_ULF_i(l)  = X_ULF_only_i(l,tau) * [-M_ULF(l)],   l in F-_ULF

SweetPeak5_ULF_i = mean top 5% largest SweetWeighted_ULF_i(l)
SourPeak5_ULF_i  = mean top 5% largest SourWeighted_ULF_i(l)

NetULFFiberScore_i = SweetPeak5_ULF_i - SourPeak5_ULF_i
```

Selection and edge cases:

```text
F+ and F- are selected within F_candidate_ULF_tau
NaN or degenerate fibers are excluded
percentile counts use ceil(percent * n)
minimum count is 1 when the corresponding positive or negative pool is non-empty
empty F+ gives SweetPeak5 = 0
empty F- gives SourPeak5 = 0
if a selected set is non-empty but a patient has zero exposure to all selected fibers, that peak component is 0
```

### 9.2 Final prediction model

DeltaHF-adjusted prediction model:

```text
Y_post_i = alpha
         + delta * NetULFFiberScore_i
         + beta  * Y_HF_ref_i
         + gamma * DeltaHFScore_i
         + error_i
```

DeltaHF-adjusted nuisance-only baseline:

```text
Y_post_i = alpha
         + beta  * Y_HF_ref_i
         + gamma * DeltaHFScore_i
         + error_i
```

No-DeltaHF prediction model:

```text
Y_post_i = alpha
         + delta * NetULFFiberScore_noDeltaHF_i
         + beta  * Y_HF_ref_i
         + error_i
```

No-DeltaHF nuisance-only baseline:

```text
Y_post_i = alpha
         + beta * Y_HF_ref_i
         + error_i
```

Primary validation statistic for the branch selected by the branch-role resolver:

```text
LOOCV Spearman rho between held-out predicted Y_post and held-out observed Y_post
```

Secondary metrics:

```text
LOOCV Pearson r
MAE
RMSE
Q2 relative to branch-specific nuisance-only baseline
```

```text
Q2 = 1 - SSE_ULFScore_model / SSE_branch_specific_nuisance_only_baseline
```

---

## 10. Sensitivity Models

### 10.1 Non-selected core branch comparison

Purpose: compare the core branch not selected as primary against the selected primary branch. When the matched HF model is `stable_nonpredictive`, the no-DeltaHF branch is primary and the DeltaHF-adjusted branch becomes the comparison branch. When the matched HF model is `predictive_valid`, the DeltaHF-adjusted branch is primary and the no-DeltaHF branch becomes the comparison branch.

Fiber estimator:

```text
rho_ULF_noDeltaHF(l) =
  corr(
    resid(rank(Y_post_i)            ~ rank(Y_HF_ref_i)),
    resid(rank(X_ULF_only_i(l,tau)) ~ rank(Y_HF_ref_i))
  )
```

Prediction:

```text
Y_post_i = alpha
         + delta * NetULFFiberScore_noDeltaHF_i
         + beta  * Y_HF_ref_i
         + error_i
```

No-DeltaHF branch name:

```text
ulf_peak_efield_tau800_no_delta_hf
```

This branch is not automatically secondary. Its role is assigned by the branch-role resolver. The non-selected core branch receives observed LOOCV outputs but does not receive formal `B=10000` resampling unless explicitly promoted.

### 10.2 Total ULF exposure sensitivity

Purpose: test whether hard HF-overlap exclusion removes biologically relevant ULF effects.

Exposure:

```text
X_ULF_total_i(l) = X_ULF_component_i(l)
```

No HF-overlap exclusion is applied. The model still adjusts for `Y_HF_ref` and `DeltaHFScore`.

Branch name:

```text
ulf_total_exposure_tau800_sensitivity
```

This branch is not primary. If total ULF exposure is positive but ULF-only exposure is negative or null, interpretation should state that the primary hard-exclusion definition may have removed co-modulated ULF effects.

### 10.3 Tau1500 ULF-only exposure-definition sensitivity

Branch:

```text
ulf_peak_efield_tau1500_sensitivity
```

This is not merely a high-threshold robustness check. It changes ULF touched status, HF touched status, HF-overlap exclusion, `X_ULF_only`, candidate fibers, and patient scores.

### 10.4 Top1500/top500 selected-fiber sensitivity

Branch:

```text
ulf_top1500_top500_sensitivity
```

Use fixed selected-fiber counts:

```text
top 1500 positive fibers
top 500 negative/sour fibers
```

This checks dependence on the percentile selected-fiber rule.

### 10.5 Optional OLS ANCOVA

Documented only, not run by default:

```text
Y_post_i ~ X_ULF_only_i(l,tau) + Y_HF_ref_i + DeltaHFScore_i
```

This does not replace the primary partial Spearman estimator.

### 10.6 Future ULF OSS-DBS activation sensitivity

Not part of the current executable mainline unless explicitly enabled.

If enabled, the OSS branch should inherit the ULF peak-E-field candidate universe and replace `X_ULF_only` with modeled ULF activation after candidate definition. OSS activation must not redefine candidate fibers.

---

## 11. Validation

Use fully nested leave-one-patient-out cross-validation.

For each connectome, endpoint, scale, branch, and held-out patient `h`:

```text
train = all patients except h
test  = patient h
```

Within each training fold:

```text
1. Fit or retrieve the matched training-fold HF normative fiber model.
2. Compute fold-specific DeltaHFScore for training patients and the held-out patient.
3. Compute fold-specific X_ULF_only_i(l,tau).
4. Define F_candidate_ULF_tau using training-patient Coverage_ULF_tau(l) >= 5.
5. Estimate rho_ULF(l) and M_ULF(l) using training patients only.
6. Select fold-specific F+_ULF and F-_ULF.
7. Compute NetULFFiberScore for training patients and the held-out patient.
8. Fit the branch-specific prediction model on training patients.
9. Predict held-out Y_post.
```

Forbidden fold-level operations:

```text
no full-sample ULF candidate mask for LOOCV scoring
no full-sample ranks
no full-sample M_ULF
no full-sample F+_ULF or F-_ULF
no held-out patient in candidate definition
no held-out patient in ULF map fitting
no held-out patient in selected-fiber selection
no held-out patient in final prediction-model fitting
no full-sample HF model for held-out DeltaHFScore
```

---

## 12. Permutation And Bootstrap

### 12.1 Freedman-Lane permutation

Formal permutation is restricted to the dTOR branch recorded as primary by the branch-role resolver unless another endpoint is explicitly promoted.

```text
connectome = dTOR
branch = ulf_peak_efield_tau800_primary_by_hf_status
formal B = 10000
smoke B = 1000
seed = 42
primary statistic = LOOCV Spearman rho
p_plus_one = (1 + count(|stat_perm| >= |stat_obs|)) / (B + 1)
```

Branch-specific nuisance model:

```text
delta_hf_adjusted: Y_post ~ Y_HF_ref + DeltaHFScore
no_delta_hf:       Y_post ~ Y_HF_ref
```

Permutation workflow:

```text
1. Fit nuisance model.
2. Permute nuisance residuals.
3. Reconstruct permuted Y*.
4. Rerun full ULF LOOCV workflow:
   - candidate definition
   - rho_ULF
   - M_ULF
   - F+_ULF / F-_ULF
   - NetULFFiberScore
   - held-out prediction
   - LOOCV statistic
```

`DeltaHFScore` in ULF permutation:

```text
DeltaHFScore is fold-dependent and HF-model-dependent.
It is not dependent on the permuted ULF outcome.
```

Therefore, within a fixed outer fold and fixed HF model cache, `DeltaHFScore` may be reused across ULF outcome permutations. This is an allowed exact optimization. Bootstrap must recompute `DeltaHFScore` because bootstrap subject multiplicity changes the HF model fitting sample.

### 12.2 Subject-level bootstrap

Formal bootstrap is restricted to the dTOR branch recorded as primary by the branch-role resolver unless another endpoint is explicitly promoted.

```text
formal B = 10000
smoke B = 1000
seed = 42
```

Each bootstrap resample must rerun:

```text
matched HF model fitting / DeltaHFScore
ULF-only exposure and coverage
F_candidate_ULF_tau
rho_ULF
M_ULF
F+_ULF / F-_ULF
NetULFFiberScore
bootstrap stability summaries
```

Do not store full `B=10000` fiber-weight tables. Use streaming finite-count, selection-frequency, and sign-stability summaries.

---

## 13. Plain Controls And Burden QC

### 13.1 ULF-only plain connected-streamline control

For each patient:

```text
Touched_ULF_only_i(l) = I[X_ULF_only_i(l,tau) > tau]

PlainULFOnlyTouchedCount_i = sum_l Touched_ULF_only_i(l)
PlainULFOnlyExposureSum_i  = sum_l X_ULF_only_i(l,tau)
PlainULFOnlyExposureTop5_i = mean top 5% X_ULF_only_i(l,tau) among touched candidate fibers
```

Compare:

```text
Y_post ~ Y_HF_ref + DeltaHFScore
Y_post ~ PlainULFOnlyExposureTop5 + Y_HF_ref + DeltaHFScore
Y_post ~ NetULFFiberScore + Y_HF_ref + DeltaHFScore
Y_post ~ NetULFFiberScore + PlainULFOnlyExposureTop5 + Y_HF_ref + DeltaHFScore
```

The joint model is QC only. With `n=16`, it must not be interpreted as strong causal decomposition.

### 13.2 Additional burden QC variables

Compute but do not force into the primary model:

```text
PlainULFTotalExposureTop5
PlainHFComponentExposureTop5
PlainHFOverlapExposureTop5
PlainHFOutSupportTop5
HFOverlapFraction
ULFOnlyToTotalULFFraction
```

Required correlations / diagnostics:

```text
corr(NetULFFiberScore, Y_HF_ref)
corr(NetULFFiberScore, DeltaHFScore)
corr(Y_HF_ref, DeltaHFScore)
corr(NetULFFiberScore, PlainULFOnlyExposureTop5)
corr(NetULFFiberScore, PlainULFTotalExposureTop5)
corr(NetULFFiberScore, PlainHFOverlapExposureTop5)
corr(NetULFFiberScore, PlainHFOutSupportTop5)
VIF / condition number for final model
leave-one-subject-out coefficient sign stability
Cook's distance / DFBETA for final model
```

Collinearity flags:

```text
|corr| < 0.85: acceptable
0.85 <= |corr| < 0.95: high collinearity warning
|corr| >= 0.95: severe collinearity warning
```

---

## 14. Outputs

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
normative_ULF_fiber_bootstrap_summary.csv
normative_ULF_fiber_mapping_qc.json
normative_ULF_fiber_generation_manifest.json
normative_ULF_fiber_HF_overlap_exclusion_summary.csv
normative_ULF_fiber_delta_hf_support_summary.csv
normative_ULF_fiber_delta_hf_support_qc.json
```

`normative_ULF_fiber_weights.csv` fields:

```text
connectome
endpoint_slug
scale_slug
branch
branch_role
delta_hfscore_role
fiber_id
tau_v_per_m
coverage_ULF_only
rho_ULF
p_uncorrected
q_fdr
M_ULF
direction_class
is_top1_positive
is_top0p5_sour
is_top1500_positive
is_top500_negative
HF_overlap_coverage
ULF_only_to_total_ULF_exposure_fraction
target_labels_for_qc
```

`normative_ULF_fiber_scores.csv` fields:

```text
subject_id
connectome
endpoint_slug
scale_slug
branch
branch_role
delta_hfscore_role
score_map_source
Y_post
Y_HF_ref
DeltaHFScore
DeltaHFScore_in_support
NetULFFiberScore
SweetPeak5_ULF
SourPeak5_ULF
PlainULFOnlyExposureTop5
PlainULFTotalExposureTop5
PlainHFComponentExposureTop5
PlainHFOverlapExposureTop5
PlainHFOutSupportTop5
HF_out_candidate_fraction_tau800
HF_out_selected_fraction_tau800
n_candidate_fibers
n_sweet_selected_fibers
n_sour_selected_fibers
n_sweet_peak_fibers
n_sour_peak_fibers
is_primary_score
```

LOOCV prediction file:

```text
normative_ULF_fiber_loocv_predictions.csv
```

Required fields:

```text
subject_id
fold_id
endpoint_slug
scale_slug
connectome
branch
Y_post_observed
Y_post_predicted_ULF_model
Y_post_predicted_nuisance_only
NetULFFiberScore_LOOCV
Y_HF_ref
DeltaHFScore_LOOCV
DeltaHFScore_z_LOOCV
HF_out_candidate_fraction_tau800_LOOCV
residual_ULF_model
residual_nuisance_only
```

Display and anatomical outputs:

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

FDR q-values, q-thresholded maps, endpoint labels, and display fibers are QC/display outputs only. They do not define `F+`, `F-`, `NetULFFiberScore`, or the primary model.

---

## 15. Execution Efficiency

Efficiency rules follow the HF normative fiber model and must preserve exact equivalence.

### 15.1 Required sidecars

PPMI/MGH may use single sidecars. dTOR must use chunked sidecars.

```text
X_ULF_component_float32_fiber_major.npy
X_HF_component_float32_fiber_major.npy
X_HFonly_ref_float32_fiber_major.npy
X_ULF_only_tau800_float32_fiber_major.npy
X_ULF_only_tau1500_float32_fiber_major.npy
S800_ULF_only_bool.npy
S1500_ULF_only_bool.npy
S800_HF_component_bool.npy
S1500_HF_component_bool.npy
S800_ULF_total_bool.npy
S1500_ULF_total_bool.npy
HF_overlap_tau800_bool.npy
HF_overlap_tau1500_bool.npy
fiber_id.npy
candidate_fiber_metadata.json
```

For dTOR:

```text
chunks/
  X_ULF_component_float32_fiber_major_chunk-*.npy
  X_HF_component_float32_fiber_major_chunk-*.npy
  X_HFonly_ref_float32_fiber_major_chunk-*.npy
  X_ULF_only_tau800_float32_fiber_major_chunk-*.npy
  X_ULF_only_tau1500_float32_fiber_major_chunk-*.npy
  S800_ULF_only_bool_chunk-*.npy
  S1500_ULF_only_bool_chunk-*.npy
  S800_HF_component_bool_chunk-*.npy
  S1500_HF_component_bool_chunk-*.npy
  HF_overlap_tau800_bool_chunk-*.npy
  HF_overlap_tau1500_bool_chunk-*.npy
  fiber_id_chunk-*.npy
fiber_chunk_manifest.json
candidate_fiber_metadata.json
```

Loading all dTOR streamlines or all dTOR exposure values into memory is invalid.

### 15.2 Outcome-independent caches

May be reused across scales and endpoint families when cache keys match:

```text
raw component exposure sidecars
HF-only reference exposure sidecars
ULF-only overlap-exclusion masks
Coverage_ULF_tau caches
candidate fiber metadata
endpoint label lookup
density lookup
HF support lookup for locked HF model
```

### 15.3 Outcome-dependent objects

Must be recomputed inside each training fold:

```text
DeltaHFScore
DeltaHFScore z-scoring parameters
nuisance residuals
rho_ULF
M_ULF
F+_ULF
F-_ULF
SweetPeak5_ULF
SourPeak5_ULF
NetULFFiberScore
final prediction model
```

### 15.4 Disallowed shortcuts

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
using total ULF exposure in place of ULF-only exposure for the primary model
using full-sample HF model to compute held-out DeltaHFScore
extrapolating HF weights to out-of-support fibers
```

Every optimized implementation must pass exact-equivalence regression testing against a small deterministic brute-force subset before formal execution.

---

## 16. Execution Priority And Gatekeeping

Run the model as a gated sequence.

Executable branches:

```text
primary:
  ulf_peak_efield_tau800_delta_hf_adjusted
  ulf_peak_efield_tau800_no_delta_hf

sensitivity:
  ulf_peak_efield_tau1500_sensitivity
  ulf_top1500_top500_sensitivity
  non-selected core branch comparison
  ulf_total_exposure_tau800_sensitivity
  ulf_gain_endpoint_sensitivity

control:
  ulf_plain_connected_streamline_control
  ulf_hf_out_support_burden_control
```

Connectome roles:

```text
PPMI 85                 observed figure-grade robustness
MGH-USC HCP 32          observed figure-grade robustness
dTOR-985 Full           primary formal analysis
```

### Round 0: Version, input, and manifest freeze

Run checks only:

```text
lock document version
lock endpoint list
lock timeline labels T0/T1/T2/T3
lock scale list
lock connectome list
lock branch list
lock tau800 / tau1500 / Coverage>=5
lock seed = 42
check HF and ULF e-field manifests
check HF-only reference e-field manifest
check component labels and proxy status
check clinical ID join
check same-day T2 immediate/HF reference pairing
check scale direction
check locked HF normative model source
check hf_prediction_validity_status
check HF support output availability
check PPMI / MGH / dTOR readability
check output root writability
```

Enter Round 1 only if all inputs are uniquely resolved and the manifest records the locked parameter set.

### Round 1: Sidecar cache, HF support cache, and equivalence test

Build PPMI/MGH sidecars and dTOR chunked sidecars for:

```text
HF component exposure
ULF component exposure
HF-only reference exposure
tau-specific ULF-only exposure
HF-overlap masks
HF support masks
out-of-support QC summaries
```

Run deterministic small-subset equivalence testing for:

```text
candidate definition
HF support classification
DeltaHFScore
partial Spearman
selected fibers
NetULFFiberScore
LOOCV prediction
smoke permutation
bootstrap summaries
```

Enter Round 2 only if optimized and brute-force outputs match within tolerance and dTOR chunked IO has no memory error.

### Round 2: Core observed chronic endpoint

Run:

```text
endpoint = chronic 3-month HF+ULF add-on
scale = MDS-UPDRS III total
core branches =
  ulf_peak_efield_tau800_delta_hf_adjusted
  ulf_peak_efield_tau800_no_delta_hf
connectome order = PPMI observed -> MGH observed -> dTOR observed
```

Enter Round 3 only if:

```text
dTOR observed LOOCV completes
fold-specific ULF candidates are non-empty
NetULFFiberScore has nonzero variance
the branch selected as primary has finite branch-specific nuisance inputs
HF_out_candidate_fraction gates are not extreme
validation metrics are finite
Q2 is interpretable against branch-specific nuisance-only baseline
ulf_primary_branch is recorded in the manifest
```

### Round 3: Same-day immediate endpoint

Run:

```text
endpoint = same-day HF+ULF immediate add-on
scale = MDS-UPDRS III total or motor domain as configured
core branches =
  ulf_peak_efield_tau800_delta_hf_adjusted
  ulf_peak_efield_tau800_no_delta_hf
connectome order = PPMI observed -> MGH observed -> dTOR observed
```

Enter Round 4 only if the same-day endpoint joins correctly, candidate masks are non-empty, `NetULFFiberScore` is non-constant, `DeltaHFScore_immediate` is computable, and LOOCV prediction is fit.

### Round 4: Plain controls and burden diagnostics

Run:

```text
ulf_plain_connected_streamline_control
ulf_hf_out_support_burden_control
```

Enter Round 5 only if `PlainULFOnlyExposureTop5` is computable, joint QC models are not singular, and `NetULFFiberScore` is not perfectly collinear with the plain exposure or out-of-support burden metrics.

### Round 5: dTOR primary smoke resampling

Run for dTOR primary branches that passed observed gates:

```text
Freedman-Lane smoke permutation B=1000
subject-level smoke bootstrap B=1000
seed = 42
```

Enter Round 6 only if smoke permutation/bootstrap complete, plus-one p values are computable, bootstrap finite counts are interpretable, and runtime profile suggests formal `B=10000` is feasible.

### Round 6: Cheap observed sensitivity

Run observed-only sensitivity:

```text
ulf_peak_efield_tau1500_sensitivity
ulf_top1500_top500_sensitivity
non-selected core branch comparison
ulf_total_exposure_tau800_sensitivity
ulf_gain_endpoint_sensitivity
PPMI -> MGH -> dTOR
```

Do not run formal permutation/bootstrap for these branches unless explicitly promoted.

### Round 7: dTOR primary formal resampling

Run only:

```text
connectome = dTOR
branch = ulf_peak_efield_tau800_primary
endpoint = chronic 3-month HF+ULF add-on unless immediate endpoint is promoted
formal permutation B=10000
formal bootstrap B=10000
seed = 42
```

Enter Round 8 only if formal resampling completes and manifests record:

```text
resampling_status = formal_complete
```

### Round 8: ULF jitter QC

Run only for dTOR branches with completed formal primary results.

Jitter changes HF and ULF component geometry, so each jitter iteration must rebuild:

```text
HF component exposure
ULF component exposure
HF-only reference exposure if jitter is applied to reference phase
HF-overlap exclusion
ULF-only exposure
DeltaHFScore
ULF candidate masks
M_ULF
NetULFFiberScore
LOOCV prediction
```

If jitter is unstable, report the result as spatially fragile.

### Round 9: Display, FDR, labels, density, and cross-connectome summaries

Generate display outputs only after numeric branches are locked. Display, FDR, labels, density, and cross-connectome outputs must derive from finalized numeric outputs and must not alter the primary model.

---

## 17. Interpretation Boundary

Interpret as:

```text
After accounting for the patient's same-day/pre-ULF HF clinical state and the matched HF normative fiber model's in-support predicted change in HF-component engagement, ULF-only engagement of this outcome-filtered normative streamline profile is associated with post-HF+ULF clinical outcome.
```

Do not interpret as:

```text
ULF causal tract has been validated.
HF contribution has been fully removed.
HF-overlap streamlines have no ULF biological role.
HF out-of-support exposure has no effect.
Every selected streamline is patient-specific.
The result proves an anatomical SNr gain mechanism.
```

Because `n=16`, all ULF fiber-level results are hypothesis-generating. Negative or unstable LOOCV results should not be interpreted as proof that ULF has no biological effect; they may reflect limited sample size, endpoint noise, stimulation-field uncertainty, HF adjustment instability, out-of-support HF-component exposure, or connectome limitations.
