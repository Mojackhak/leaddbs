# Direct-Voxel Output Contract

## Status

```text
output_contract_documented
direct_voxel_design_frozen
publisher_implementation_not_started
current_legacy_outputs_unchanged
```

This document is the authoritative publication contract for the configured
`direct_voxel_model_v1` runner. It defines downstream artifacts, stable paths,
machine-readable status, and final-model references. It does not change the
reference or add-on model mathematics.

Existing outputs under `/Volumes/VAL/STNSNr/summary/direct_voxel/` remain
read-only legacy artifacts. They are not migrated or overwritten by this
contract.

## Scope

The contract covers:

- every configured clinical scale with identical engineering behavior;
- the frequency-1 reference direct-voxel model;
- both frequency-2 add-on branches;
- source resolution and unique final-model realization;
- final-linked formal resampling and sensitivity analyses; and
- model-only reports and display maps.

It excludes anatomical ROI assignment, atlas overlap, VTA-region intersection,
regional heatmaps, and GUI output. Those are future postprocessing layers.

## Canonical Naming

The configured implementation uses generic frequency-role names throughout its
internal modules, classes, functions, dataclasses, fields, status values,
artifact kinds, and published paths:

```text
reference
addon
no_delta_reference
delta_reference_adjusted
DeltaReferenceScore
```

`HF`, `ULF`, `no_delta_hf`, `delta_hf_adjusted`, and `DeltaHFScore` are legacy
STNSNr names. They are not canonical aliases inside the configured pipeline.
Implementation is incomplete until configured direct-voxel code and records
are renamed end to end. Temporary legacy entrypoints may remain only in an
explicitly isolated compatibility package; they cannot define internal state,
artifact identity, or publisher fields.

## Configured Output Root

The production profile declares:

```yaml
output:
  root: /Volumes/VAL/STNSNr/summary/spot
```

The smoke profile declares:

```yaml
output:
  root: /Volumes/VAL/STNSNr/validation/spot
```

`output.root` must be an absolute path. It changes storage location only and
must not change scientific configuration identity, source classification,
prediction classification, or final-model realization.

The publisher derives every lower path. YAML cannot override directory names
or artifact filenames:

```text
<output.root>/direct_voxel/<model_set_id>/<scale_id>/
```

The configured profile binds one baseline/reference/add-on phase-program tuple.
That binding is stored in `model_manifest.json`; it is not repeated as an
`endpoint` or `endpoint_pair` directory.

## Canonical Directory Tree

```text
<output.root>/direct_voxel/<model_set_id>/
|
|-- resolved_direct_voxel_model.yaml
|-- model_manifest.json
|-- scale_status.csv
|-- artifact_index.csv
|
|-- <scale_id>/
    |
    |-- scale_status.json
    |
    |-- reference/
    |   |-- observed/
    |   |-- resolver/
    |   |-- final_model.json
    |   |-- formal/
    |   |-- sensitivity/
    |   |-- report/
    |
    |-- addon/
    |   |-- branches/
    |   |   |-- no_delta_reference/
    |   |   |   |-- observed/
    |   |   |   |-- resolver/
    |   |   |
    |   |   |-- delta_reference_adjusted/
    |   |       |-- observed/
    |   |       |-- resolver/
    |   |
    |   |-- final_model.json
    |   |-- formal/
    |   |-- sensitivity/
    |   |-- report/
    |
    |-- report/
```

No directory may be created empty. A stage that was not requested has no
directory. A requested stage that cannot run writes only its required
`status.json` and any terminal classification record required below.

## Root Artifacts

### resolved_direct_voxel_model.yaml

This is the validated, fully resolved profile used for the publication. It
preserves `output.root` but scientific hashing must also compute a separate
hash that excludes storage-only fields.

### model_manifest.json

Required fields:

```text
schema_version = direct_voxel_model_manifest_v1
model_set_id
profile_type
study_id
study_base_path
study_base_sha256
resolved_model_path
resolved_model_sha256
scientific_config_sha256
output_root
endpoint_pair.baseline.phase_id
endpoint_pair.baseline.program_id
endpoint_pair.reference.phase_id
endpoint_pair.reference.program_id
endpoint_pair.addon.phase_id
endpoint_pair.addon.program_id
scale_ids
scale_count
code_provenance.git_available
code_provenance.git_commit
code_provenance.git_dirty
started_at_utc
finished_at_utc
final_status
```

`git_commit` and `git_dirty` are nullable when Git is unavailable. Allowed
`final_status` values are:

```text
completed
completed_with_scale_failures
failed
```

### scale_status.csv

One row per configured scale, in YAML order:

```text
scale_id
scale_direction
reference_input_status
reference_source_status
reference_prediction_status
reference_final_status
addon_intended_primary_branch
addon_final_branch
addon_final_role
addon_final_status
overall_status
failure_reason
```

A failed scale never changes another scale's status or execution path.

### artifact_index.csv

One row per published artifact:

```text
scale_id
model_family
branch_id
stage
artifact_kind
relative_path
sha256
size_bytes
status
```

All paths are relative to the model-set root. The index does not create a
second copy of any artifact. It indexes resolved configuration, scale outputs,
and reports, but it does not index itself. Stage `status.json` files likewise
do not list themselves in `artifact_relative_paths`.

## Common Stage Status

Every created `observed/`, `resolver/`, `formal/`, `sensitivity/`, and `report/`
directory contains `status.json`.

Required fields:

```text
schema_version = direct_voxel_stage_status_v1
scale_id
model_family = reference | addon
branch_id = null | no_delta_reference | delta_reference_adjusted
stage
status
reason
started_at_utc
finished_at_utc
artifact_relative_paths
```

Allowed stage status values are:

```text
completed
failed
not_run_input_failure
not_run_no_final_model
not_run_nonfinal
```

Formal or sensitivity failure must not modify source status, prediction status,
branch role, or final-model identity.

## Observed Source Scan

Every executable reference model and add-on branch writes:

```text
observed/status.json
observed/source_scan.csv
observed/source_scan_qc.json
```

`source_scan.csv` contains one row per declared tau/Coverage cell:

```text
tau_v_per_m
coverage_subjects_min
n_subjects
n_voxels_full
fold_n_voxels_min
fold_n_voxels_median
fold_n_voxels_max
score_nonconstant_all_folds
all_predictions_finite
passes_hard_computability
adjacent_passing_cells
mae_model
mae_baseline
rmse_model
rmse_baseline
q2
loocv_spearman_rho
loocv_pearson_r
prediction_status
failure_reason
```

MAE/RMSE classify prediction only. Q2 and correlations are report-only. Source
selection must not use MAE, RMSE, Q2, correlation, or nominal p values.

Grid cells do not publish per-cell NIfTI maps. Full spatial artifacts are
published only for an accepted selected source and for the two declared
selected-source tau sensitivities.

## Resolver Artifacts

Every resolver writes:

```text
resolver/status.json
resolver/source_status.json
```

`source_status.json` requires:

```text
input_status
source_status
prediction_status
threshold_source
selected_tau_v_per_m
selected_coverage_subjects_min
selected_adjacent_passing_cells
source_failure_reasons
```

If the source is accepted, the resolver additionally writes:

```text
resolver/selected_source.json
resolver/coverage.nii.gz
resolver/coefficient.nii.gz
resolver/benefit_map.nii.gz
resolver/stability.nii.gz
resolver/scores.csv
resolver/loocv_predictions.csv
resolver/subject_order.csv
resolver/valid_voxel_indices.npy
resolver/full_weights.npy
resolver/fold_weights.npy
resolver/mapping_qc.json
```

`selected_source.json` records selected tau/Coverage, threshold source,
adjacent support, estimator identity, scale direction, subject-order hash,
voxel-axis hash, and relative paths to every selected-source artifact.

An absent or input-invalid source does not publish selected-source maps,
scores, predictions, or weight arrays.

## Selected-Source Array Contract

For `n` subjects and `v` voxels in the selected-source feature union:

```text
subject_order.csv          rows = n; columns = fold_index, subject_id
valid_voxel_indices.npy    dtype = int64;   shape = [v]
full_weights.npy           dtype = float32; shape = [v]
fold_weights.npy           dtype = float32; shape = [n, v]
```

Voxel IDs are zero-based NumPy C-order flat indices into the configured
right-canonical NIfTI grid. The feature union is the deterministic sorted union
of full-sample valid voxels and all fold-specific valid voxels. Every
weight-array column uses exactly this order. `full_weights.npy` is `NaN` for a
union voxel without a valid full-sample weight. Row `h` of `fold_weights.npy`
is estimated without subject `h` and is `NaN` for a union voxel invalid in that
fold. No full-sample weight, sign, support, or ranking may restrict or replace a
fold-specific value. This union representation therefore preserves the exact
leakage-safe fold operators while exposing one realized feature axis.

## Selected-Source NIfTI Contract

All NIfTI files use the configured right-canonical grid and affine.

```text
coverage.nii.gz     int16;   selected-tau subject count
coefficient.nii.gz  float32; raw partial-Spearman coefficient
benefit_map.nii.gz  float32; coefficient oriented by scale direction
stability.nii.gz    float32; LOOCV sign-direction stability fraction
```

Continuous/statistical images use `NaN` outside model support. Count and binary
images use `0` outside support. `benefit_map.nii.gz` is the only map used for
full-sample selected-source scoring; fold predictions use fold-specific arrays.
`stability.nii.gz` stores the fraction of finite LOOCV fold weights that are
the same sign as the nonzero full-sample `benefit_map` value. Folds where the
voxel is outside fold support are excluded from the denominator. A voxel with a
zero or non-finite full-sample weight has `NaN` stability because no reference
direction exists.

## Score And Prediction Tables

Reference `scores.csv` requires:

```text
subject_id
observed_outcome
baseline_outcome
reference_score
exposure_sum_valid_voxels
n_valid_score_voxels
score_map_source
source_status
prediction_status
```

Reference `loocv_predictions.csv` requires:

```text
fold_index
subject_id
observed_outcome
reference_score_loocv
prediction_model
prediction_baseline
residual_model
residual_baseline
```

Add-on tables add:

```text
branch_id
branch_role
intended_primary_branch
delta_reference_role
reference_outcome
addon_score
delta_reference_score
delta_reference_score_z
delta_reference_support_status
```

Delta fields are empty for `no_delta_reference`; they are never filled with
zeros to imply that adjustment was performed.

## Add-On Dependency Artifacts

Each add-on branch that completes overlap-input construction writes the
following artifacts, even if its later source resolver returns
`absent_no_stable_grid`:

```text
resolver/reference_overlap_coverage.nii.gz
resolver/reference_overlap_fraction.nii.gz
resolver/reference_overlap_subject_summary.csv
```

These artifacts describe model-defined reference-active overlap exclusion. They
are not anatomical ROI postprocessing.

Only `delta_reference_adjusted` writes the following artifacts. They are
published whenever DeltaReferenceScore construction completes, even if the
adjusted add-on source is later absent:

```text
resolver/delta_reference_scores.csv
resolver/delta_reference_fold_scores.npy
resolver/delta_reference_support_summary.csv
resolver/delta_reference_support_qc.json
```

For `n` subjects:

```text
delta_reference_scores.csv       rows = n
delta_reference_fold_scores.npy  dtype = float64; shape = [n, n]
```

Row `h` of the fold array is computed from the reference model trained without
subject `h`; column `i` is the resulting DeltaReferenceScore for subject `i`.
The held-out adjusted prediction uses element `[h, h]` after training-only
standardization. If DeltaReferenceScore construction fails before numerical
scores exist, the adjusted branch writes only stage/source status and the
available support QC; it does not fabricate score arrays.

## Final Model Record

`reference/final_model.json` and `addon/final_model.json` are immutable
selection records. They reference branch/resolver artifacts by relative path;
they never copy maps, scores, predictions, or weights.

Required common fields:

```text
schema_version = direct_voxel_final_model_v1
final_model_id
scale_id
model_family
intended_primary_branch
realized_final_branch
final_role
final_status
source_status
prediction_status
selected_tau_v_per_m
selected_coverage_subjects_min
selected_adjacent_passing_cells
source_record_relative_path
artifact_relative_paths
failure_reasons
```

Reference uses `reference` as its realized branch. Add-on uses
`no_delta_reference` or `delta_reference_adjusted`. Allowed `final_role` values
are:

```text
primary
fallback_final
no_final_model
```

When no final model exists, branch and selected-source fields are null,
artifact references are empty, and failure reasons are mandatory.

`final_model_id` is the SHA-256 of canonical JSON containing `model_set_id`,
`scale_id`, `model_family`, realized branch, selected-source record hash, and
scientific configuration hash. Storage paths and `output.root` are excluded.
When no final model is realized, `final_model_id` is null.

## Formal Outputs

Formal outputs are generated only for the accepted model referenced by
`final_model.json`:

```text
formal/status.json
formal/permutation_summary.csv
formal/permutation_null_statistics.npy
formal/bootstrap_summary.csv
formal/bootstrap_standard_error.nii.gz
```

`permutation_null_statistics.npy` is a compact `float64 [B]` array. No
permutation-specific maps or score tables are published. Bootstrap maps are
streamed; only the final standard-error map and summary are published.

Every formal artifact records `final_model_id`. It cannot become a new source
candidate or change final-model status.

## Sensitivity Outputs

Reference sensitivity output:

```text
sensitivity/status.json
sensitivity/tau_neighborhood/summary.csv
sensitivity/tau_neighborhood/tau-<value>/coverage.nii.gz
sensitivity/tau_neighborhood/tau-<value>/coefficient.nii.gz
sensitivity/tau_neighborhood/tau-<value>/benefit_map.nii.gz
sensitivity/tau_neighborhood/tau-<value>/scores.csv
sensitivity/tau_neighborhood/tau-<value>/loocv_predictions.csv
sensitivity/tau_neighborhood/tau-<value>/mapping_qc.json
sensitivity/spatial_jitter/summary.csv
sensitivity/spatial_jitter/model_similarity.csv
sensitivity/spatial_jitter/support_overlap.csv
sensitivity/spatial_jitter/standard_error.nii.gz
```

Add-on sensitivity additionally writes:

```text
sensitivity/branch_comparison.csv
sensitivity/gain_endpoint_summary.csv
sensitivity/total_addon_exposure_summary.csv
sensitivity/delta_reference_support_summary.csv
sensitivity/baseline_collinearity_summary.csv
```

Only valid/applicable analyses are materialized. Non-applicable analyses are
listed with explicit status and reason in `sensitivity/status.json`.
`tau-<value>` uses a normalized decimal V/m value with no exponent; a decimal
point is encoded as `p` (for example, `tau-198` or `tau-198p5`).

### Common sensitivity fields

Every sensitivity summary starts with:

```text
analysis_id
status
reason
scale_id
final_model_id
final_branch
selected_tau_v_per_m
selected_coverage_subjects_min
n_subjects
n_voxels_full
mae_model
mae_baseline
rmse_model
rmse_baseline
q2
loocv_spearman_rho
score_relative_path
prediction_relative_path
```

Missing metrics for a non-computable analysis are empty, not zero.

### branch_comparison.csv

This table reuses observed branch results and does not refit either branch. It
contains one row for each declared add-on branch and adds:

```text
branch_id
branch_input_status
source_status
prediction_status
threshold_source
adjacent_passing_cells
intended_primary_branch
final_role
delta_reference_role
```

### gain_endpoint_summary.csv

The sensitivity outcome is direction-normalized so positive gain always means
improvement:

```text
lower-is-better: gain = reference_outcome - addon_outcome
higher-is-better: gain = addon_outcome - reference_outcome
```

It locks the final branch exposure, selected tau/Coverage, estimator, and LOOCV
rules. For `delta_reference_adjusted`, the nuisance baseline contains
DeltaReferenceScore. For `no_delta_reference`, the nuisance baseline is
intercept-only because the reference outcome is already part of gain. Added
fields are:

```text
scale_direction
gain_definition
positive_gain_means_improvement
nuisance_design
gain_mean
gain_standard_deviation
```

This sensitivity cannot become a replacement outcome or final model.

### total_addon_exposure_summary.csv

This sensitivity replaces overlap-excluded add-on-only exposure with the total
add-on component exposure. It locks the final branch outcome, nuisance design,
selected tau/Coverage, estimator, and LOOCV policy, but rebuilds coverage and
Omega from total add-on exposure. Added fields are:

```text
exposure_definition = total_addon_component
overlap_exclusion_applied = false
primary_exposure_voxel_count
total_exposure_voxel_count
added_overlap_voxel_count
map_correlation_with_final
score_correlation_with_final
```

### delta_reference_support_summary.csv

This is diagnostic-only. It never excludes subjects, changes weights, refits a
model, or creates a replacement final model. It references the resolver support
artifacts and reports:

```text
support_status
cohort_median_out_support_fraction
subject_fraction_over_0p50
subject_fraction_over_0p80
maximum_required_out_support_fraction
zero_total_exposure_count
correlation_out_support_with_addon_score
correlation_out_support_with_absolute_loocv_residual
resolver_support_summary_relative_path
resolver_support_qc_relative_path
```

### baseline_collinearity_summary.csv

This sensitivity adds the configured baseline outcome to the final branch
prediction design:

```text
no_delta_reference:
  addon_outcome ~ addon_score + reference_outcome + baseline_outcome

delta_reference_adjusted:
  addon_outcome ~ addon_score + reference_outcome
                  + DeltaReferenceScore + baseline_outcome
```

It adds:

```text
design_status
design_rank
design_column_count
condition_number
vif_addon_score
vif_reference_outcome
vif_delta_reference_score
vif_baseline_outcome
addon_score_coefficient
```

An unavailable baseline or invalid design is an explicit non-computable
sensitivity result. It does not change the final model.

## Report Outputs

Reference report:

```text
reference/report/status.json
reference/report/summary.json
reference/report/reference_report.html
reference/report/display/benefit_map_smooth_fwhm1mm.nii.gz
reference/report/display/benefit_map_smooth_fwhm2mm.nii.gz
reference/report/display/benefit_map_bilateral.nii.gz
reference/report/display/mapping_qc.pdf
```

Add-on report uses the same display family with `addon_report.html`. Scale-level
reporting writes:

```text
report/status.json
report/scale_summary.json
report/scale_report.html
```

Report output only summarizes or visualizes existing artifacts. Display maps
must not feed back into scoring, LOOCV, source resolution, formal resampling, or
sensitivity classification.

Display smoothing uses masked normalized Gaussian convolution in physical
millimeters:

```text
smoothed = Gaussian(value * finite_mask) / Gaussian(finite_mask)
```

Locations with zero smoothed-mask support remain `NaN`. The 1 mm and 2 mm FWHM
outputs never replace values in the unsmoothed selected-source bundle.

`benefit_map_bilateral.nii.gz` is derived from the unsmoothed right-canonical
final benefit map. The configured nonlinear left-right transform creates the
left homologous copy on the same canonical grid. Right and left finite values
are preserved; if interpolation produces a finite overlap voxel, the display
value is their arithmetic mean. This map is not a bilateral fitted model.

If a requested model-family report has no final model, it writes only
`status.json` and `summary.json`. It does not create HTML or display artifacts.
The scale-level report may still summarize the explicit no-final terminal
state.

No sweet/sour threshold masks or anatomical summaries are produced. Positive
and negative associations remain encoded by the sign of the continuous
`benefit_map`.

## Conditional Materialization

The publisher follows these rules:

```text
grid evaluated
  -> observed scan and resolver status always written

accepted selected source
  -> selected-source bundle written

absent or input-invalid source
  -> no selected-source bundle

final model realized
  -> final_model.json references one source bundle

no final model
  -> final_model.json records no_final_model with no artifact references

formal or sensitivity requested but no final model
  -> stage status only; no fabricated numerical artifacts
```

No candidate branch, source cell, or final model is silently substituted.

## Collision And Overwrite Rules

The model-set directory is immutable with respect to scientific identity.

- If the directory does not exist, the publisher may create it.
- If the directory exists with the same scientific configuration identity,
  execution may resume incomplete stages only after every prerequisite and
  existing artifact passes its recorded SHA-256 check.
- If the directory exists with a different scientific configuration identity,
  execution fails before writing artifacts.
- Changing only `output.root` does not change scientific identity.
- Existing files are never silently overwritten by a different artifact.
- File existence alone is never sufficient for resume or reuse.
- Each array or JSON document has an immutable adjacent metadata sidecar. The
  sidecar binds payload SHA-256, artifact kind and schema, ordered axis hashes,
  units, space, producer ID, and producer version.
- Same-byte reuse is allowed only when the metadata sidecar is present and
  exactly matches the requested artifact semantics. A missing sidecar or any
  metadata difference is a collision error.
- Payload and metadata publication use atomic create-if-absent operations; a
  concurrent writer cannot replace an artifact that appeared after the initial
  existence check.

Changing endpoint bindings or scientific model parameters requires a new
`model_set_id` or explicit archival of the old model-set directory outside this
contract.

## Test Profile

The test profile publishes the same directory and schema contract under:

```text
/Volumes/VAL/STNSNr/validation/spot/direct_voxel/
  dual_frequency_four_model_test_v1/
```

Reduced scales, grid size, and resampling counts change workload only. Missing
artifact classes or silently skipped required stages are test failures.
