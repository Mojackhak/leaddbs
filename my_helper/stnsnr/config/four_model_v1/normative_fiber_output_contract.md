# Normative-Fiber Output Contract

## Status

```text
output_contract_documented
normative_fiber_design_frozen
publisher_implementation_not_started
current_legacy_outputs_unchanged
configured_production_outputs_missing
```

This document is the authoritative publication contract for the configured
`normative_fiber_model_v1` runner. It defines stable paths, connectome roles,
machine-readable status, selected-source artifacts, and unique final-model
references. Existing outputs under
`/Volumes/VAL/STNSNr/summary/normative_connectome_fiber/` remain read-only
legacy artifacts and are not migrated or overwritten.

## Scope

The contract covers:

- every configured clinical scale with identical engineering behavior;
- reference and add-on normative-fiber models;
- one `formal` connectome and zero or more `sensitive` connectomes;
- complete observed tau/Coverage grids for every configured connectome;
- formal-connectome source resolution and unique final realization;
- final-linked permutation, bootstrap, OSS, jitter, and controls; and
- numeric fiber statistics and density reports.

It excludes ROI assignment, anatomical enrichment, regional heatmaps, atlas
overlap, VTA-region postprocessing, GUI output, and HTTP services.

## Canonical Naming

Configured modules, records, paths, and artifacts use:

```text
reference
addon
no_delta_reference
delta_reference_adjusted
DeltaReferenceScore
formal
sensitive
```

Legacy HF/ULF names cannot define configured artifact identity. Temporary
legacy entrypoints may remain only in an isolated compatibility layer.

## Output Root

Production publishes below:

```text
/Volumes/VAL/STNSNr/summary/spot/normative_fiber/<model_set_id>/
```

The test profile publishes the same contract below:

```text
/Volumes/VAL/STNSNr/validation/spot/normative_fiber/<model_set_id>/
```

`output.root` is storage-only and must be absolute. The publisher derives all
lower paths; YAML cannot configure artifact filenames or subdirectory names.

## Canonical Directory Tree

```text
<output.root>/normative_fiber/<model_set_id>/
|
|-- resolved_normative_fiber_model.yaml
|-- model_manifest.json
|-- scale_status.csv
|-- artifact_index.csv
|
|-- <scale_id>/
    |
    |-- scale_status.json
    |
    |-- reference/
    |   |-- connectomes/
    |   |   |-- <formal_connectome_id>/
    |   |   |   |-- observed/
    |   |   |   |-- resolver/
    |   |   |
    |   |   |-- <sensitive_connectome_id>/
    |   |       |-- observed/
    |   |       |-- formal_source_evaluation/
    |   |
    |   |-- final_model.json
    |   |-- sensitivity_base.json
    |   |-- cross_connectome/
    |   |-- formal/
    |   |-- sensitivity/
    |   |   |-- high_threshold/
    |   |   |-- fixed_outer_library/
    |   |   |-- plain_burden/
    |   |   |-- oss/
    |   |   |-- jitter/
    |   |-- report/
    |
    |-- addon/
    |   |-- branches/
    |   |   |-- no_delta_reference/
    |   |   |   |-- connectomes/
    |   |   |   |   |-- <formal_connectome_id>/
    |   |   |   |   |   |-- observed/
    |   |   |   |   |   |-- resolver/
    |   |   |   |   |-- <sensitive_connectome_id>/
    |   |   |   |       |-- observed/
    |   |   |   |       |-- formal_source_evaluation/
    |   |   |
    |   |   |-- delta_reference_adjusted/
    |   |       |-- connectomes/
    |   |           |-- <formal_connectome_id>/
    |   |           |   |-- observed/
    |   |           |   |-- resolver/
    |   |           |-- <sensitive_connectome_id>/
    |   |               |-- observed/
    |   |               |-- formal_source_evaluation/
    |   |
    |   |-- final_model.json
    |   |-- sensitivity_base.json
    |   |-- cross_connectome/
    |   |-- formal/
    |   |-- sensitivity/
    |   |-- report/
    |
    |-- report/
```

Only a formal connectome creates `resolver/`. Only a sensitive connectome
creates `formal_source_evaluation/`. No directory may be empty. A stage that
was not requested has no directory. A requested stage that cannot run writes
only its required `status.json` and terminal classification record.

## Root Artifacts

### resolved_normative_fiber_model.yaml

The validated profile used for execution. Scientific hashing excludes
storage-only `output.root`.

### model_manifest.json

Required fields:

```text
schema_version = normative_fiber_model_manifest_v1
model_set_id
study_id
study_base_path
study_base_sha256
resolved_model_path
resolved_model_sha256
scientific_config_sha256
output_root
endpoint_pair
scale_ids
connectomes[].connectome_id
connectomes[].role
connectomes[].path
connectomes[].sha256
formal_connectome_id
code_provenance.git_available
code_provenance.git_commit
code_provenance.git_dirty
started_at_utc
finished_at_utc
final_status
```

`final_status` is `completed`, `completed_with_scale_failures`, or `failed`.

### scale_status.csv

One row per configured scale in YAML order:

```text
scale_id
scale_direction
formal_connectome_id
reference_input_status
reference_source_status
reference_prediction_status
reference_final_status
addon_intended_primary_branch
addon_final_branch
addon_final_role
addon_final_status
sensitive_connectome_status
overall_status
failure_reason
```

A scale failure never changes another scale's execution path.

### artifact_index.csv

One row per published artifact:

```text
scale_id
model_family
branch_id
connectome_id
connectome_role
stage
artifact_kind
relative_path
sha256
size_bytes
status
```

The index does not index itself and never creates a second copy of an artifact.

## Common Stage Status

Every created stage directory contains `status.json` with:

```text
schema_version = normative_fiber_stage_status_v1
scale_id
model_family = reference | addon
branch_id = null | no_delta_reference | delta_reference_adjusted
connectome_id
connectome_role = formal | sensitive
stage
status
reason
started_at_utc
finished_at_utc
artifact_relative_paths
```

Allowed stage values include:

```text
completed
failed
not_run_input_failure
not_run_no_formal_source
not_run_no_final_model
not_run_nonfinal
not_applicable_sensitive_connectome
```

Formal, OSS, jitter, control, FDR, or density failure cannot modify source,
prediction, branch-role, or final-model classification.

## Connectome Role Contract

`role` is restricted to `formal` or `sensitive`, and exactly one configured
connectome must be `formal`.

Every connectome runs the complete observed tau/Coverage grid. Only `formal`:

- assigns source and prediction status;
- applies add-on one-way fallback;
- creates `final_model.json`; and
- receives formal resampling, OSS, jitter, and final-linked sensitivity.

`Sensitive` connectomes retain cell-level metrics and evaluate the numeric
tau/Coverage selected by formal. They cannot become final when formal is absent
or failed. Fiber IDs are connectome-local and are never compared directly
across connectomes.

## Observed Grid

Every executable connectome/branch writes:

```text
observed/status.json
observed/source_scan.csv
```

`source_scan.csv` has one row per declared tau/Coverage cell:

```text
scale_id
model_family
branch_id
connectome_id
connectome_role
tau_v_per_m
coverage_subjects_min
n_subjects
n_candidate_fibers_full
fold_n_candidate_fibers_min
hard_computability_pass
adjacent_passing_cells
mae_model
mae_baseline
rmse_model
rmse_baseline
q2
loocv_spearman_rho
failure_reason
```

The publisher does not save full weight arrays for every grid cell.

## Formal Resolver Bundle

Each executable formal reference or formal add-on branch writes:

```text
resolver/status.json
resolver/source_selection.json
resolver/candidate_fiber_ids.npy
resolver/valid_fiber_ids.npy
resolver/full_weights.npy
resolver/fold_weights.npy
resolver/selected_sweet_fiber_ids.npy
resolver/selected_sour_fiber_ids.npy
resolver/scores.csv
resolver/loocv_predictions.csv
resolver/fiber_score_support.csv
```

`selected_sweet_fiber_ids.npy` and `selected_sour_fiber_ids.npy` are emitted
only for nonempty signed sides. A permitted one-sided score does not publish a
zero-length placeholder array; the missing side is represented by its support
status, selected count `0`, and deterministic empty-ID hash.

Array contracts:

```text
candidate_fiber_ids.npy: int64, shape [n_candidate_full]
valid_fiber_ids.npy: int64, shape [n_union], full/fold valid-feature union
full_weights.npy: float32, shape [n_union], NaN where full-sample-invalid
fold_weights.npy: float32, shape [n_subjects, n_union], NaN where fold-invalid
```

Fiber IDs use the connectome's validated `data.mat:idx` identity. Full-sample
and fold-specific selection use deterministic weight ordering with canonical
fiber ID ascending as the tie-breaker. `n_union` is the deterministic
parent-axis-order union of the full-sample valid set and every fold-specific
valid set. This representation preserves every leakage-safe fold operator;
full-sample finite weights never restrict a training-fold candidate or signed
pool.

`source_selection.json` records:

```text
source_status
prediction_status
threshold_source
selected_tau_v_per_m
selected_coverage_subjects_min
selected_adjacent_passing_cells
selected_grid_distance
final_valid_feature_axis_relative_path
```

## Fiber Score Support

Full sample and every LOOCV fold record:

```text
n_positive_valid_fibers
n_negative_valid_fibers
sweet_fraction_requested
sour_fraction_requested
weighted_peak_fraction_requested
sweet_selected_k_min
sour_selected_k_min
weighted_peak_k_min
sweet_percentage_count
sour_percentage_count
sweet_actual_selected_count
sour_actual_selected_count
sweet_actual_peak_count
sour_actual_peak_count
sweet_minimum_count_dominated
sour_minimum_count_dominated
sweet_peak_minimum_count_dominated
sour_peak_minimum_count_dominated
fiber_score_support_status
sweet_selected_fiber_id_hash
sour_selected_fiber_id_hash
```

Allowed support states are:

```text
adequate_two_sign
limited_two_sign
limited_positive_only
limited_negative_only
absent_no_valid_signed_fibers
```

Support labels do not create a new tau/Coverage gate and do not change the
MAE/RMSE prediction classifier.

## Sensitive Formal-Source Evaluation

If formal resolves a source, every input-valid sensitive connectome evaluates
that same numeric tau/Coverage and writes:

```text
formal_source_evaluation/status.json
formal_source_evaluation/formal_source_cell.json
formal_source_evaluation/candidate_fiber_ids.npy
formal_source_evaluation/valid_fiber_ids.npy
formal_source_evaluation/full_weights.npy
formal_source_evaluation/fold_weights.npy
formal_source_evaluation/scores.csv
formal_source_evaluation/loocv_predictions.csv
formal_source_evaluation/fiber_score_support.csv
```

For a computable formal-source cell, the array contracts match the formal
resolver artifact set: `candidate_fiber_ids.npy` is the full-sample candidate axis,
`valid_fiber_ids.npy` is the parent-order full/fold-valid union,
`full_weights.npy` has shape `[n_union]`, and `fold_weights.npy` has shape
`[n_subjects, n_union]`; invalid full/fold positions are `NaN`. A
noncomputable cell may omit weight/score arrays but must retain status, cell
metrics, failure reasons, and any support diagnostics that were computable.

The run-scoped `SensitiveRecord` contains `input_status`,
`cell_computability_status`, `prediction_status`, evaluated numeric
tau/Coverage, and the optional valid feature axis. It has no `source_status`,
threshold source, branch role, fallback role, or final-model status. These
artifacts are sensitivity evidence only. If formal has no source, the
directory contains status only with `not_run_no_formal_source` and no
`SensitiveRecord` is emitted.

## Continuous Exposure And Add-On Overlap

Reference and add-on tau both define Coverage and candidate fibers only.
Continuous peak E-field remains in the score after a fiber enters the
candidate universe. Add-on additionally zeros patient-fiber exposure where the
reference component reaches or exceeds the selected reference tau.

For each fold, candidate Coverage and overlap are rebuilt from training inputs.
No full-sample candidate mask, overlap mask, fiber ranking, sign, or selected
ID set may be reused for held-out prediction.

The adjusted add-on branch additionally writes:

```text
delta_reference_scores.csv
delta_reference_fold_scores.npy
delta_reference_support_summary.csv
delta_reference_support_status.json
```

`delta_reference_fold_scores.npy` is float64 with shape
`[n_subjects, n_subjects]`; row `h` stores the fold-`h` score operator applied
to the ordered cohort, and `[h,h]` is the held-out score.

The matched reference operator is connectome-local. Formal add-on uses the
accepted formal reference source; sensitive add-on uses the same sensitive
connectome's computable reference evidence evaluated at the formal numeric
tau/Coverage. Endpoint ID, connectome ID, parent fiber-axis hash, and artifact
axes must all match. Fiber IDs and weights are never borrowed across
connectomes.

For each full-sample or fold operator, DeltaReferenceScore support is the
selected-source Coverage-passing set intersected with finite reference
weights. The full-sample finite set does not restrict a fold. DeltaReferenceScore
reapplies the configured signed-library and weighted-peak policy to each
operator and is defined as:

```text
NetFiberScore(add-on-condition reference component; locked operator)
- NetFiberScore(reference-condition exposure; locked operator)
```

Support QC uses the strict normative-fiber threshold
`reference_component_exposure > selected_reference_tau` on the complete
parent fiber axis. For every subject and required full/fold operator:

```text
out_support_fraction =
  n_suprathreshold_fibers_outside_finite_valid_support
  / n_suprathreshold_fibers_total
```

A zero denominator is `invalid_no_reference_component_exposure`. `adequate`
requires cohort median `< 0.20` and subject fraction `< 0.25` above `0.50`.
`invalid_extreme_out_of_support` applies when cohort median is `> 0.50`, more
than `25%` of subjects are above `0.80`, or any required full/fold value is
strictly `> 0.95`. All remaining nonzero cases are `limited`. Both `adequate`
and `limited` remain valid adjusted-branch inputs.

## Final Model Reference

Reference and add-on each create exactly one `final_model.json` terminal
record. It references artifacts and never copies them.

Required fields:

```text
schema_version = normative_fiber_final_model_v1
scale_id
model_family
formal_connectome_id
final_branch
final_role = primary | fallback_final | no_final_model
final_status
source_status
prediction_status
selected_tau_v_per_m
selected_coverage_subjects_min
resolver_relative_path
valid_feature_axis_relative_path
scientific_config_sha256
final_record_sha256
```

Only a formal-connectome final enters downstream formal or sensitivity stages.

## Formal Resampling

Every configured scale with a realized final writes:

```text
formal/status.json
formal/permutation_summary.csv
formal/permutation_null.npy
formal/bootstrap_summary.csv
formal/bootstrap_selection_frequency.npy
formal/bootstrap_sign_stability.npy
```

Permutation and bootstrap counts are 10000 in production. Null/statistic arrays
are compact float64 vectors; no per-resample full fiber-weight tables are
published.

## Final-Linked Sensitivity

Reference sensitivity contains high-threshold, fixed-outer-library,
plain-burden, OSS, and jitter stages. Add-on additionally contains branch
comparison, total add-on exposure, gain endpoint, DeltaReferenceScore support,
and collinearity diagnostics.

OSS writes:

```text
status.json
oss_parameter_summary.json
activation_probability_summary.csv
scores.csv
loocv_predictions.csv
permutation_summary.csv
permutation_null.npy
```

OSS inherits `final.valid_feature_axis`, does not rescan tau/Coverage, and uses
`I[p(A) > 0.5]` for fitting. Continuous p(A) remains a sidecar/QC value. OSS
uses the same 200/100/20 score rules and fold-local refitting.

The activation request receives the matched final peak-E-field score as an
explicit subject-axis input. It is used only for the report-only
activation-consistency correlation; the backend must not discover that score
through a filename, directory, or hidden final-record artifact.

The request also carries two explicit ordered ID inputs on the same feature
axis: final-model `feature_ids` and OSS-row `activation_feature_ids`. They must
be elementwise equal int64 arrays. Shape/axis metadata alone is insufficient;
any value or order mismatch fails before endpoint fitting.

Jitter writes:

```text
status.json
jitter_summary.csv
model_similarity.csv
selected_fiber_overlap.csv
density_correlation.csv
```

Voxel and normative-fiber jitter are independent. This contract does not
create a shared cross-domain jitter schedule or cache.

## Cross-Connectome Comparison

Reference and each input-valid add-on branch may write:

```text
cross_connectome/status.json
cross_connectome/performance_comparison.csv
cross_connectome/formal_source_computability.csv
cross_connectome/score_direction_comparison.csv
cross_connectome/density_similarity.csv
```

Cross-connectome comparison uses performance, score direction, and spatial
density metrics. It never compares raw fiber IDs or promotes sensitive results.

## Reports

A realized final may write:

```text
report/status.json
report/summary.json
report/model_report.html
report/fiber_qvalue_summary.csv
report/unthresholded_weighted_density.nii.gz
report/positive_weighted_density.nii.gz
report/negative_weighted_density.nii.gz
```

Continuous/statistical density maps use NaN outside modeled density support;
zero denotes a true zero contribution inside support. FDR and density outputs
are reporting evidence only. ROI labels, enrichment, and regional heatmaps are
not part of this contract.

If there is no final model, report contains status and summary only; HTML and
density outputs are not generated.

## Sensitivity Checkpoint And Extensions

Every realized reference or add-on final writes `sensitivity_base.json` next to
`final_model.json`. It binds parent run/model identity, selected source,
subject/fiber axes, shared exposure semantic SHA, final artifacts, E-field,
transform, connectome, `Omega_max`, and OSS gate identities, producer/schema
versions, and RNG schedule identity. It contains no scratch URI.

A later process may publish jitter, OSS, or other final-linked fiber sensitivity
below:

```text
<output.root>/normative_fiber/<model_set_id>/extensions/<extension_id>/
├── extension_manifest.json
├── artifact_index.csv
└── <scale_id>/
    ├── reference/sensitivity/
    └── addon/sensitivity/
```

With a complete checkpoint, observed, resolver, and final-model rerun count is
`< 1`. Missing parent artifacts trigger explicit rebuild into a new parent
lineage before extension. An exact prepared OSS or jitter cache may support
statistics without original sources; new physical production requires its
declared sources and toolchain. Extension files never overwrite main-run files.

## Reuse And Collision Rules

Artifact reuse requires exact scientific identity, subject order, connectome
hash, selected source, branch, feature-axis hash, and recorded artifact SHA-256.
File existence alone is insufficient. A path collision with a different
scientific identity fails without overwrite.

Outcome-independent exposure/candidate sidecars may be reused across scales
with identical subjects and source inputs. Outcome-dependent weights, signed
fiber selections, scores, predictions, permutation, bootstrap, and reports are
recomputed per scale. dTOR exposure and formal scoring remain chunked; loading
the entire connectome exposure matrix is invalid.

## Test Profile

`normative_fiber_model_test.yaml` uses the identical artifact contract under
the validation root. It uses two scales, PPMI as `formal`, MGH as `sensitive`,
a reduced tau/Coverage grid, and minimal resampling counts. It is a code-path
test and must not be interpreted scientifically.

Deterministic state-machine and synthetic exposure/outcome fixtures cover
pre-specified acceptance, scan fallback, absent source, predictive and
nonpredictive status, adjusted-input failure, one-way fallback, continuous
add-on exposure, formal/sensitive role boundaries, and OSS candidate-axis
inheritance. Real smoke results are not expected to realize every mutually
exclusive state.

## Documentation Review Record

Five read-only contract review passes completed on 2026-07-14:

| Pass | Result | Verified closure |
|---|---|---|
| 1. Scale equality and endpoint identity | PASS | Production direct-voxel and normative-fiber profiles contain the same 28 ordered scales; both test profiles contain MDS-UPDRS III and IV; every configured scale exists in `study_base.json`; endpoint and frequency bindings match exactly. |
| 2. Reference-to-add-on dependency and fallback | PASS | The reference formal result alone determines intended add-on branch role; adjusted-input or stable-source absence permits only the declared one-way no-delta fallback; technical failure cannot trigger fallback. |
| 3. Round and parameter coverage | PASS | The full observed grid, formal resolver, selected-source neighborhood, formal resampling, score support, OSS, jitter, controls, and reporting each have a public value, fixed schema rule, or runtime-derived record. |
| 4. YAML, path, and manifest consistency | PASS | Production/test model-set IDs, roots, support thresholds, resampling seeds, and shared direct/fiber dependency fields align; every profile has exactly one `formal` connectome and uses only `formal`/`sensitive` roles. |
| 5. Current versus planned implementation | PASS | The files are approved design contracts; the configured normative-fiber loader, publisher, code-path smoke, and scientific rerun remain unimplemented, and current legacy outputs remain unchanged. |

The review also confirms that reference and add-on both retain continuous
peak E-field after tau/Coverage defines the candidate universe, add-on retains
reference-active overlap exclusion, and voxel/fiber jitter is not shared.
