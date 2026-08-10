# Dual-Frequency Integrated Output Contract

## Status And Authority

This document is the canonical directory, publication, metadata, cache, and
resume contract for the dual-frequency direct-voxel, normative-fiber, and
individualized seed-target results.

The directory rules in this document supersede older directory trees,
standalone postprocess publication roots, root-level aggregate indexes,
artifact-hash lookup contracts, and model-set wrapper directories retained in
other design or implementation documents. Those documents remain authoritative
for scientific definitions and algorithms that are not changed here.

This document fixes the target contract. The direct-voxel and normative-fiber
publication reached its completion gate on 2026-07-30. The individualized
seed-target root extends that publication and is complete only when its own
root marker and all 56 endpoint results exist.

## Required Principles

1. The formal result root contains the reusable physical data, integrated
   direct-voxel, normative-fiber, and individualized seed-target results, plus
   one human-readable root README.
2. Visualization outputs are stored below the matching model, scale, and model
   role. There is no standalone formal `postprocess/` result tree.
3. Output, cache, and run directory names must not contain a version number
   unless the user explicitly authorizes one.
4. Canonical paths must not contain task names, dates, release wrappers, or
   model-set wrapper directories.
5. `endpoint_index.csv`, `artifact_index.csv`, `scale_status.csv`, a root
   manifest, and a root completion marker are not part of the target contract.
6. Each model root owns its model selection and statistics tables. Shared
   physical data are stored once at the sibling `shared/` root and are
   referenced with relative paths.
7. Resume uses deterministic paths and `complete.json` markers. Code identity,
   repository identity, file hashes, and directory hashes do not gate resume.
8. Binary-array and NIfTI metadata describe scientific interpretation only.
   Metadata checksums do not gate resume.
9. A directory that is not applicable or was not requested is not created.
   Empty placeholder directories are prohibited.
10. Historical results are migration inputs only. They are not renamed,
    overwritten, or removed until the corresponding new model root is complete.
11. Completed reusable physical data are formal data under `spot/shared/`, not
    cache entries. The cache contains only state and temporary work for an
    incomplete run.
12. The workflow YAML defines only `output.root`. The shared-data root, model
    roots, and hidden runtime cache are fixed paths derived from that one value.
13. Formal YAML inputs contain no `schema_version` or `model_set_id`. The
    loader chooses strict schemas from the workflow profile roles and checks
    compatibility from scientific fields that are actually shared.
14. Normative-fiber sensitivity excludes the former high-threshold candidate
    control and fixed-size sweet/sour outer-library control.

## Configured Root And Derived Paths

The workflow YAML contains the only configurable output-directory field:

```yaml
output:
  root: /Volumes/VAL/STNSNr/summary/spot
```

The direct-voxel, normative-fiber, and individualized seed-target model YAMLs
and the study profile do not define another publication, cache, or run root.
The implementation derives the following paths without additional
configuration:

| Purpose | Derived path |
|---|---|
| Reusable physical data | `{output.root}/shared` |
| Direct-voxel results | `{output.root}/direct_voxel` |
| Normative-fiber results | `{output.root}/normative_fiber` |
| Individualized seed-target results | `{output.root}/individualized_seed_target` |
| Incomplete runtime state | `{output.root}/.cache/runs` |

The completed configured output root contains:

```text
/Volumes/VAL/STNSNr/summary/spot/
├── README.md
├── shared/
├── direct_voxel/
├── normative_fiber/
└── individualized_seed_target/
```

An incomplete execution may additionally create `.cache/runs/`. The completed
publication excludes that hidden runtime directory when no incomplete state
remains. Neither the formal publication nor the hidden cache contains:

```text
postprocess/
.runs/
.staging/
releases/
endpoint_index.csv
artifact_index.csv
manifest.json
complete.json
```

The complete formal publication is present when all four paths exist:

```text
shared/complete.json
direct_voxel/complete.json
normative_fiber/complete.json
individualized_seed_target/complete.json
```

## Root README

`README.md` is the only file directly below the formal result root. It is a
human-readable entry point and explains:

- the `reference` and `addon` model roles;
- the difference between direct voxel and normative fiber;
- the scale-directory organization;
- the meaning of the primary statistical fields;
- the difference between scientific maps and display-smoothed maps;
- the reusable physical data stored below `shared/`;
- how to locate model-local summary tables; and
- that `.cache/` contains only incomplete runtime state and is not part of the
  formal publication.

`README.md` is not a resume marker and is not a program input.

## Shared Reusable Scientific Data

`shared/` contains the completed, portable physical data whose recomputation is
expensive and whose values are independent of a clinical scale or outcome. It
is part of the formal result set and is copied together with the three model
roots.

```text
/Volumes/VAL/STNSNr/summary/spot/shared/
├── complete.json                                      # Written after all requested shared physical data are complete
│
├── transformed_efields/
│   └── {physical_unit_id}/
│       ├── field.nii.gz                               # Spatially transformed E-field used by downstream preparation
│       ├── metadata.json                              # Subject, stimulation, side, frequency, affine, space, and units
│       └── complete.json                              # Terminal marker for this transformed E-field
│
├── connectome_geometry/
│   └── {connectome_id}/
│       ├── points.npy                                 # Canonically ordered streamline points in MNI coordinates
│       ├── point_offsets.npy                          # Start and stop offsets for every canonical fiber
│       ├── metadata.json                              # Connectome, point axis, fiber count, dtype, units, and space
│       └── complete.json                              # Terminal marker for this prepared connectome geometry
│
├── target_projections/
│   └── {connectome_id}/
│       ├── reference/
│       │   ├── fiber_ids.npy                          # Role-seed fibers in canonical connectome order
│       │   ├── target_membership.npz                  # Independent binary membership in the configured targets
│       │   ├── voxel_patterns.npz                     # Seed-voxel and target-pattern membership
│       │   ├── metadata.json                          # Connectome, seed, target order, grid, and intersection semantics
│       │   └── complete.json                          # Terminal marker for the reference projection
│       └── addon/
│           └── same files as reference                # Add-on role-seed projection
│
├── voxel_exposures/
│   └── {physical_unit_id}/
│       ├── exposure.npy                               # Continuous bilateral voxel exposure shared across scales
│       ├── metadata.json                              # Subject and voxel axes, physical condition, dtype, units, and space
│       └── complete.json                              # Terminal marker for this voxel exposure
│
├── fiber_exposures/
│   └── {connectome_id}/
│       └── {physical_unit_id}/
│           ├── exposure.npy                           # Continuous bilateral fiber exposure shared across scales
│           ├── fiber_ids.npy                          # Ordered canonical fiber IDs for the exposure columns
│           ├── metadata.json                          # Subject and fiber axes, physical condition, dtype, units, and space
│           └── complete.json                          # Terminal marker for this fiber exposure
│
├── individualized_target_exposures/
│   └── {subject_id}/
│       └── {condition}/
│           └── {side}/
│               └── {target_id}/
│                   ├── peak_e.npy                     # Streamline peak E in target-specific TCK order
│                   ├── metadata.json                  # Subject, condition, side, target, streamline count, units, and space
│                   └── complete.json                  # Terminal marker for this target exposure
│
├── jitter_exposures/
│   └── {model_family}/
│       └── {physical_unit_id}/
│           └── {block_id}/
│               ├── primary_exposure.npy               # Physical exposure for the deterministic replicate block
│               ├── feature_keys.npy                   # Ordered voxel or fiber feature identifiers
│               ├── replicate_indices.npy              # Replicate indices represented by the block
│               ├── replicate_seeds.npy                # Deterministic perturbation seeds
│               ├── metadata.json                      # Model family, physical condition, axes, perturbation, and units
│               └── complete.json                      # Terminal marker for this jitter block
│
│   # Individualized seed-target blocks use model_family
│   # individualized_seed_target and replace primary_exposure.npy with:
│   # patient_burdens.npy, patient_support.npy, and the applicable add-on
│   # reference-condition and reference-component burden/support arrays.
│   # Their leading axis is the deterministic jitter replicate axis; target
│   # burden arrays retain the configured tau, subject, and target axes.
│
└── oss_rows/
    └── {connectome_id}/
        └── {physical_unit_id}/
            ├── fiber_ids.npy                          # Ordered Omega-axis fiber IDs
            ├── probabilities.npy                      # OSS activation probability for every retained fiber
            ├── metadata.json                          # Physical condition, axis, activation semantics, dtype, and units
            └── complete.json                          # Terminal marker for this OSS row
```

An adjusted add-on jitter block also contains the applicable reference
condition exposure, add-on reference-component exposure, parent support counts,
and reference tau values. These files use the same block-level
`metadata.json` and `complete.json`; files that do not apply to a block are not
created.

Individualized seed-target spatial jitter uses fixed blocks of 25 replicate
indices. This block size is an internal execution constant, not a YAML setting.
The block producer never reruns an E-field solver. It reuses the precomputed
E-field volumes in `shared/` and resamples them at translated streamline
coordinates; only the derived peak exposure, burden, and support arrays vary by
replicate.

The generic `prepare_jitter_exposure_block` task is restricted to direct-voxel
and normative-fiber endpoints because its feature axis is a canonical voxel or
connectome-fiber axis. Individualized endpoints must not depend on that task or
receive its `jitter_block_group_id`. They use the existing individualized
target replicate provider, which creates the 25-replicate burden/support blocks
under `shared/jitter_exposures/individualized_seed_target/` and coordinates
same-group endpoint reuse with the block-local lock and completion marker.

An individualized jitter block stores `patient_support.npy`, so its physical
cache identity includes both `activated_fiber_count_min` and
`activated_fiber_fraction_min`. Changing either support threshold invalidates
only the matching individualized jitter blocks and their downstream sensitivity
results. It does not invalidate source E-field volumes or the unperturbed
target-level `peak_e.npy` cache.
Within one block, each configured target tractogram is streamed once and all
25 deterministic translations are evaluated while its geometry is resident.
The resulting burden and support arrays are shared by every scale with the
same physical role, cohort, perturbation settings, and, for add-on exclusion,
locked reference tau. Endpoint tasks consume read-only replicate views from
these arrays. Endpoint IDs, outcome values, and scale IDs are not part of the
physical block identity.

`physical_unit_id` is a stable, human-readable identifier for one physical
stimulation condition. It does not contain a version number, date, task name,
file hash, repository identity, or machine-specific path.

The shared root stores all eight expensive reusable categories:

1. spatially transformed E-fields;
2. prepared connectome geometry;
3. target and seed-voxel projection patterns;
4. continuous voxel exposures;
5. continuous fiber exposures;
6. individualized target streamline peak-E exposures;
7. physical jitter exposure blocks; and
8. OSS activation-probability rows.

The current migration inventory is approximately:

| Category | Current amount | Reason to retain |
|---|---:|---|
| Spatially transformed E-fields | 1.2 GB across 45 entries | Avoid repeated spatial transformation and NIfTI decompression |
| Prepared connectome geometry | 17 GB | Avoid repeated HDF5 decompression and geometry preparation |
| Continuous voxel exposures | 1.5 GB across 3 entries | Avoid repeated voxel sampling and bilateral assembly |
| Continuous fiber exposures | 3.0 GB across 27 entries | Avoid repeated full-connectome reads and fiber sampling |
| Physical jitter exposure blocks | 3.6 GB across 360 blocks | Reuse perturbation physics when replaying or extending jitter analyses |
| OSS activation-probability rows | 658 MB across 249 rows | Avoid repeated OSS-DBS solver execution |

These amounts describe the current migration source and are not required counts
or size limits in the publication contract.

Scale-specific weights, predictions, nuisance operators, threshold masks,
permutation or bootstrap schedules, visualization intermediates, and
equivalence-check records are not stored below `shared/`. Final schedules and
statistics that are part of scientific reporting remain in their model and
scale result directories.

The individualized target leaf is independent of tau, Coverage, clinical
scale, and outcome. `condition` is one of `reference`, `addon`, or
`addon_reference_component`. An add-on endpoint reads the add-on and
add-on-reference-component leaves for the same subject, side, target, and
streamline order when applying the reference-inactive numerator rule. It also
reads the reference-condition leaf when constructing the matched
DeltaReferenceScore input.

Every shared leaf is installed as complete files before its `complete.json` is
written. A consumer uses the leaf only when that marker exists. Shared metadata
contains only the semantic fields required to interpret the payload and does
not contain a payload, code, repository, or directory checksum.

## Model-Root Metadata

All three model roots use the same small metadata contract:

```text
{model_root}/
├── resolved_model.yaml
├── model_manifest.json
├── final_model_selection.csv
├── final_statistics.csv
├── complete.json
└── {scale_id}/
```

### `resolved_model.yaml`

This file stores the resolved scientific configuration used by the model. It
contains only values that affect the scientific interpretation or numerical
result, including:

- tau candidates and the primary tau;
- Coverage candidates and the primary Coverage;
- fallback rules;
- formal permutation and bootstrap counts;
- fiber-selection parameters where applicable;
- enabled sensitivity analyses;
- scale definitions consumed by the model; and
- semantic input references.

It does not contain worker counts, RAM limits, timeouts, code identity,
repository identity, cache identity, an output path, or a version number.

### `model_manifest.json`

This file describes one model-local publication and its relative reference to
the shared physical-data root. Its minimum content is:

```text
model_family
shared_root
resolved_model_path
scale_ids
scale_count
roles
final_model_selection_path
final_statistics_path
status
started_at
finished_at
```

All paths are relative to the model root. `shared_root` is `../shared`. The
manifest does not contain file hashes, code hashes, repository hashes, legacy
run names, or version fields.

The manifest is descriptive. Ordinary resume is controlled by
`complete.json`, not by reparsing or comparing this manifest.

### `final_model_selection.csv`

This is the only model-level table for final model selection. One row
represents one scale and model role.

Common fields are:

```text
scale_id
model_family
role
computability_status
selected_tau_v_per_m
selected_coverage_subjects_min
fallback_used
finite_subjects
candidate_feature_count
selected_feature_count
failure_reason
```

Normative-fiber rows may also include:

```text
formal_connectome_id
candidate_fiber_count
sweet_fiber_count
sour_fiber_count
weighted_peak_fiber_count
```

The selected tau and Coverage are the values actually used by the final model,
including any fallback result. They are not replaced by a hard-coded primary
threshold. `fallback_used` is derived from the realized source selection: it is
true when the selected source has `scan_fallback_accepted` status and false when
the pre-specified cell was accepted. The final-realization wrapper status does
not determine this field.

### `final_statistics.csv`

This is the only model-level table for final statistical results. One row
represents one scale and model role.

It contains the paired in-sample and LOOCV fields, including:

```text
scale_id
model_family
role
in_sample_finite_subjects
in_sample_finite_permutations
loocv_finite_predictions
loocv_finite_permutations
in_sample_spearman_rho
in_sample_spearman_nominal_p
in_sample_permutation_p_plus_one_two_sided
loocv_spearman_rho
loocv_spearman_nominal_p
loocv_permutation_p_plus_one_two_sided
in_sample_pearson_r
in_sample_pearson_nominal_p
loocv_pearson_r
loocv_pearson_nominal_p
in_sample_r2
in_sample_relative_r2
loocv_q2
in_sample_rmse
in_sample_mae
loocv_rmse_model
loocv_mae_model
in_sample_rmse_baseline
in_sample_mae_baseline
loocv_rmse_baseline
loocv_mae_baseline
spearman_optimism_gap
pearson_optimism_gap
r2_q2_gap
rmse_optimism_gap
mae_optimism_gap
```

An adjusted in-sample R-squared field is not published because the final model
does not have one stable, unambiguous model degree of freedom.
`r2_q2_gap` is `in_sample_relative_r2` minus `loocv_q2`, so the comparison uses
the same nuisance-only baseline. Standard `in_sample_r2` remains a descriptive
field and is not subtracted from `loocv_q2`.

### Model-Root `complete.json`

The model-root marker is written last, after every requested scale, model-local
summary table, and model manifest have been published.

Ordinary resume checks only for the expected model root and this marker. The
marker is not a file-integrity index.

## Direct-Voxel Result Tree

In both result trees, text after `#` is a descriptive comment and is not part
of the directory or file name.

```text
/Volumes/VAL/STNSNr/summary/spot/direct_voxel/
├── resolved_model.yaml                         # Resolved scientific configuration used by this model
├── model_manifest.json                        # Model publication contents, roles, scales, and terminal status
├── final_model_selection.csv                  # Selected tau, Coverage, fallback, and feature counts by scale and role
├── final_statistics.csv                       # Paired in-sample and LOOCV statistics by scale and role
├── complete.json                              # Terminal completion marker for the direct-voxel model root
│
└── {scale_id}/
    ├── complete.json                          # Terminal marker for all requested outputs of this scale
    │
    ├── reference/
    │   ├── observed/
    │   │   ├── source_scan.csv                # Evaluated tau and Coverage cells, support counts, and computability state
    │   │   ├── source_scan_qc.json            # Selected cell, evaluated-cell counts, fallback state, and scan diagnostics
    │   │   └── status.json                    # Terminal status of observed-input preparation
    │   │
    │   ├── resolver/
    │   │   ├── benefit_map.nii.gz             # Unsmoothed voxelwise benefit-oriented scientific map
    │   │   ├── benefit_map.nii.gz.metadata.json   # Shape, affine, units, space, and value semantics
    │   │   ├── coefficient.nii.gz             # Unsmoothed voxelwise fitted model coefficients
    │   │   ├── coefficient.nii.gz.metadata.json   # Shape, affine, units, space, and coefficient semantics
    │   │   ├── coverage.nii.gz                # Number of contributing subjects at each voxel
    │   │   ├── coverage.nii.gz.metadata.json      # Shape, affine, space, and coverage-count semantics
    │   │   ├── stability.nii.gz               # Voxelwise stability measure used for interpretation
    │   │   ├── stability.nii.gz.metadata.json     # Shape, affine, space, and stability-value semantics
    │   │   ├── valid_voxel_indices.npy        # Flattened voxel indices retained by the final resolver
    │   │   ├── valid_voxel_indices.npy.metadata.json # Index axis, dtype, image shape, and ordering
    │   │   ├── full_weights.npy               # Full-sample model weight for each retained voxel
    │   │   ├── full_weights.npy.metadata.json     # Feature axis, dtype, units, and sign convention
    │   │   ├── fold_weights.npy               # LOOCV fold-specific voxel weights
    │   │   ├── fold_weights.npy.metadata.json     # Fold and feature axes, dtype, units, and ordering
    │   │   ├── fold_valid_masks.npy           # Valid-feature mask for each LOOCV fold
    │   │   ├── fold_valid_masks.npy.metadata.json # Fold and feature axes, dtype, and mask semantics
    │   │   ├── subject_order.csv              # Canonical subject order shared by arrays and predictions
    │   │   ├── scores.csv                     # Subject-level voxel-model scores and observed outcomes
    │   │   ├── loocv_predictions.csv          # Held-out model and baseline predictions by subject
    │   │   ├── selected_source.json           # Selected tau, Coverage, fallback, and source identity
    │   │   ├── source_status.json             # Computability and terminal state of each candidate source
    │   │   ├── mapping_qc.json                # Subject, image-grid, and feature-axis mapping checks
    │   │   └── status.json                    # Terminal status of resolver publication
    │   │
    │   ├── final_model.json                   # Final selected source, thresholds, fit, and model identity
    │   ├── sensitivity_base.json              # Immutable base-model references consumed by extensions
    │   │
    │   ├── formal/
    │   │   ├── permutation_null_statistics.npy    # Formal LOOCV null statistic for each permutation
    │   │   ├── permutation_null_statistics.npy.metadata.json # Permutation axis, dtype, statistic, and tail convention
    │   │   ├── permutation_summary.csv         # Observed statistic, nominal p, and permutation p
    │   │   ├── bootstrap_standard_error.nii.gz    # Voxelwise bootstrap standard error of the fitted map
    │   │   ├── bootstrap_standard_error.nii.gz.metadata.json # Shape, affine, space, units, and bootstrap semantics
    │   │   ├── bootstrap_summary.csv           # Bootstrap replicate counts and aggregate diagnostics
    │   │   └── status.json                     # Terminal status of formal inference
    │   │
    │   ├── in_sample/
    │   │   ├── model_predictions.npy           # Full-sample fitted predictions in canonical subject order
    │   │   ├── model_predictions.npy.metadata.json # Subject axis, dtype, outcome units, and prediction meaning
    │   │   ├── baseline_predictions.npy        # Full-sample nuisance-only baseline predictions
    │   │   ├── baseline_predictions.npy.metadata.json # Subject axis, dtype, outcome units, and baseline meaning
    │   │   ├── predictions.csv                 # Subject IDs, outcomes, model fits, and baseline fits
    │   │   ├── observed_scores.npy             # Observed subject-level feature-derived model scores
    │   │   ├── observed_scores.npy.metadata.json  # Subject axis, dtype, units, and score convention
    │   │   ├── observed_weights.npy            # Full-sample weights used for the observed statistic
    │   │   ├── observed_weights.npy.metadata.json # Feature axis, dtype, units, and ordering
    │   │   ├── candidate_feature_ids.npy       # Voxel feature IDs entering in-sample inference
    │   │   ├── candidate_feature_ids.npy.metadata.json # Feature axis, dtype, image shape, and ID convention
    │   │   ├── candidate_parent_indices.npy    # Mapping from candidate features to the parent voxel axis
    │   │   ├── candidate_parent_indices.npy.metadata.json # Feature axis, dtype, and parent-axis ordering
    │   │   ├── permutation_schedule.npy        # Subject-label permutation schedule
    │   │   ├── permutation_schedule.npy.metadata.json # Replicate and subject axes, RNG contract, and ordering
    │   │   ├── permutation_null_statistics.npy    # In-sample null statistic for each permutation
    │   │   ├── permutation_null_statistics.npy.metadata.json # Permutation axis, dtype, statistic, and tail convention
    │   │   ├── summary.json                    # Reader-facing in-sample metrics and permutation result
    │   │   ├── technical_summary.json          # Detailed counts, baseline metrics, and execution diagnostics
    │   │   ├── technical_summary.json.metadata.json # Field definitions, units, and array references
    │   │   └── status.json                     # Terminal status of in-sample inference
    │   │
    │   ├── sensitivity/
    │   │   └── spatial_jitter/
    │   │       ├── spatial_jitter_metrics.json # Endpoint metrics across spatial perturbation replicates
    │   │       ├── spatial_jitter_metrics.json.metadata.json # Metric definitions, replicate count, and perturbation units
    │   │       ├── result.json                 # Reader-facing spatial-jitter sensitivity result
    │   │       └── status.json                 # Terminal status of spatial-jitter analysis
    │   │
    │   ├── visualization/
    │   │   ├── paired_fit/
    │   │   │   ├── in_sample_loocv_fit.png    # Raster paired in-sample and LOOCV fit figure
    │   │   │   ├── in_sample_loocv_fit.pdf    # Publication-ready vector fit figure
    │   │   │   └── result.json                # Plotted values, statistics, labels, and style provenance
    │   │   │
    │   │   ├── spatial_2d/
    │   │   │   ├── maps/
    │   │   │   │   └── display.nii.gz           # Single 1 mm FWHM, 0.1 mm display-only spatial map
    │   │   │   └── figures/
    │   │   │       ├── display.png               # Raster 2D sections rendered from display.nii.gz
    │   │   │       ├── display.pdf               # Publication-ready 2D sections rendered from display.nii.gz
    │   │   │       └── result.json               # Source map, display transform, slices, limits, and style
    │   │   │
    │   │   └── spatial_3d/
    │   │       ├── figures/
    │   │       │   ├── {scale_id}_voxel_reference_view01.pdf # First configured 3D reference-voxel camera view
    │   │       │   └── {scale_id}_voxel_reference_view02.pdf # Second configured 3D reference-voxel camera view
    │   │       └── export_manifest.json           # Exported views, camera settings, fonts, and source maps
    │   │
    │   └── report/
    │       └── summary.json                       # Reader-facing endpoint summary and artifact references
    │
    └── addon/
        ├── branches/
        │   ├── no_delta_reference/
        │   │   ├── observed/                      # Add-on inputs without delta-reference adjustment
        │   │   └── resolver/                      # Resolved model for the unadjusted branch
        │   └── delta_reference_adjusted/
        │       ├── observed/                      # Add-on inputs after delta-reference adjustment
        │       └── resolver/                      # Resolved model for the adjusted branch
        ├── final_model.json                       # Selected add-on branch, thresholds, fit, and identity
        ├── sensitivity_base.json                  # Base references consumed by add-on extensions
        ├── formal/                                # Same formal-inference file contract as reference
        ├── in_sample/                             # Same in-sample file contract as reference
        ├── sensitivity/                           # Add-on sensitivity results
        │   └── spatial_jitter/                    # Same jitter file contract as reference
        ├── visualization/                         # Figures derived from the selected add-on model
        │   ├── paired_fit/                        # Same paired-fit file contract as reference
        │   ├── spatial_2d/                        # Same 2D map and figure contract as reference
        │   └── spatial_3d/
        │       ├── figures/
        │       │   ├── {scale_id}_voxel_addon_view01.pdf # First configured 3D add-on voxel camera view
        │       │   └── {scale_id}_voxel_addon_view02.pdf # Second configured 3D add-on voxel camera view
        │       └── export_manifest.json           # Exported views, camera settings, fonts, and source maps
        └── report/
            └── summary.json                       # Reader-facing add-on summary and artifact references
```

The add-on branch `observed/` and `resolver/` directories use the same artifact
contract as the reference directories. `final_model.json` records which branch
was selected. The selected branch is not copied into a second top-level
resolver directory.

The unsmoothed scientific `benefit_map.nii.gz` remains in `resolver/`.
Visualization publishes one display-only derivative named `display.nii.gz`.
It is generated directly from the selected scientific map and does not consume
the former report-level 1 mm or 2 mm smoothed maps.

Display generation applies a 1 mm FWHM masked-normalized Gaussian to the
scientific values and finite-support weights, interpolates the numerator and
continuous weight to an isotropic 0.1 mm grid, divides numerator by weight, and
retains values where the interpolated Gaussian weight is greater than 0.5.
Values outside that display support are NaN. These parameters are read from
`spatial_result_visualization.yaml`; the output name `display.nii.gz` is fixed.

Two-dimensional and three-dimensional rendering reuse the same
`display.nii.gz`. The anatomy layer is not recolored by the heat-map renderer.
The display derivative cannot be used for model selection, prediction,
permutation, bootstrap, spatial jitter, or OSS-pPAM.

Two-dimensional STN and SNr outlines remain display-only atlas derivatives.
When a role defines an optional continuous `outline_path`, rendering samples
that atlas linearly on the same 0.1 mm panel grid as the display map and draws
its configured 0.05 isovalue. The fiber seed remains the source of projection
membership, slice positions, and panel geometry. When `outline_path` is absent,
rendering thresholds the native binary seed, crops its positive-voxel bounding
box with one native-voxel background halo, computes a physical signed-distance
field inside that local ROI, and draws its 0 mm isovalue. Neither path applies
Gaussian shape smoothing or changes an atlas used by a scientific stage. The
local signed-distance fallback is an in-memory rendering intermediate and is
not a published or shared-cache artifact.

The surface mesh is extracted from the finite support of `display.nii.gz`, and
colors are sampled 0.25 mm inward. Neither smoothing, resampling, nor sampling
depth alters the scientific map, model selection, predictions, or inference.

## Normative-Fiber Result Tree

```text
/Volumes/VAL/STNSNr/summary/spot/normative_fiber/
├── resolved_model.yaml                         # Resolved scientific configuration used by this model
├── model_manifest.json                        # Model publication contents, roles, scales, and terminal status
├── final_model_selection.csv                  # Selected tau, Coverage, fallback, connectome, and fiber counts
├── final_statistics.csv                       # Paired in-sample and LOOCV statistics by scale and role
├── complete.json                              # Terminal completion marker for the normative-fiber model root
│
└── {scale_id}/
    ├── complete.json                          # Terminal marker for all requested outputs of this scale
    │
    ├── reference/
    │   ├── connectomes/
    │   │   ├── {formal_connectome_id}/
    │   │   │   ├── observed/
    │   │   │   │   ├── source_scan.csv        # Discovered subject-level inputs for the formal connectome
    │   │   │   │   └── status.json            # Terminal status of formal-connectome input preparation
    │   │   │   └── resolver/
    │   │   │       ├── candidate_fiber_ids.npy                 # Fiber IDs remaining after candidate construction
    │   │   │       ├── candidate_fiber_ids.npy.metadata.json   # Feature axis, dtype, connectome, and ID convention
    │   │   │       ├── valid_fiber_ids.npy                     # Candidate fibers computable for the selected source
    │   │   │       ├── valid_fiber_ids.npy.metadata.json       # Feature axis, dtype, connectome, and ordering
    │   │   │       ├── selected_sweet_fiber_ids.npy            # Positive fibers retained by sweet selection
    │   │   │       ├── selected_sweet_fiber_ids.npy.metadata.json # Feature axis, dtype, selection rule, and ordering
    │   │   │       ├── selected_sour_fiber_ids.npy             # Negative fibers retained by sour selection
    │   │   │       ├── selected_sour_fiber_ids.npy.metadata.json # Feature axis, dtype, selection rule, and ordering
    │   │   │       ├── full_weights.npy                         # Full-sample weight for each retained fiber
    │   │   │       ├── full_weights.npy.metadata.json           # Feature axis, dtype, units, and sign convention
    │   │   │       ├── fold_weights.npy                         # LOOCV fold-specific fiber weights
    │   │   │       ├── fold_weights.npy.metadata.json           # Fold and feature axes, dtype, units, and ordering
    │   │   │       ├── fold_valid_masks.npy                     # Valid-feature mask for each LOOCV fold
    │   │   │       ├── fold_valid_masks.npy.metadata.json       # Fold and feature axes, dtype, and mask semantics
    │   │   │       ├── fiber_score_support.csv                  # Fiber support, sign, rank, and selection membership
    │   │   │       ├── scores.csv                               # Subject-level fiber-model scores and outcomes
    │   │   │       ├── loocv_predictions.csv                    # Held-out model and baseline predictions by subject
    │   │   │       ├── subject_order.csv                        # Canonical subject order shared by arrays and predictions
    │   │   │       ├── source_selection.json                    # Selected tau, Coverage, fallback, and connectome source
    │   │   │       └── status.json                              # Terminal status of formal-connectome resolution
    │   │   │
    │   │   └── {sensitive_connectome_id}/
    │   │       ├── observed/
    │   │       │   ├── source_scan.csv                          # Inputs discovered for this sensitive connectome
    │   │       │   └── status.json                              # Terminal status of sensitive-connectome preparation
    │   │       └── formal_source_evaluation/
    │   │           ├── candidate_fiber_ids.npy                  # Sensitive-connectome candidate fiber IDs
    │   │           ├── candidate_fiber_ids.npy.metadata.json    # Feature axis, dtype, connectome, and ID convention
    │   │           ├── valid_fiber_ids.npy                      # Sensitive-connectome fibers valid for evaluation
    │   │           ├── valid_fiber_ids.npy.metadata.json        # Feature axis, dtype, connectome, and ordering
    │   │           ├── full_weights.npy                         # Full-sample weights evaluated on this connectome
    │   │           ├── full_weights.npy.metadata.json           # Feature axis, dtype, units, and sign convention
    │   │           ├── fold_weights.npy                         # LOOCV fold weights evaluated on this connectome
    │   │           ├── fold_weights.npy.metadata.json           # Fold and feature axes, dtype, units, and ordering
    │   │           ├── fold_valid_masks.npy                     # Valid-feature mask for each evaluation fold
    │   │           ├── fold_valid_masks.npy.metadata.json       # Fold and feature axes, dtype, and mask semantics
    │   │           ├── fiber_score_support.csv                  # Fiber support and score information for evaluation
    │   │           ├── scores.csv                               # Subject-level sensitive-connectome scores
    │   │           ├── loocv_predictions.csv                    # Held-out predictions on the sensitive connectome
    │   │           ├── formal_source_cell.json                  # Evaluation result bound to the formal source model
    │   │           ├── formal_source_cell.json.metadata.json    # Field definitions and source-axis references
    │   │           └── status.json                              # Terminal status of formal-source evaluation
    │   │
    │   ├── final_model.json                                    # Final connectome, thresholds, fit, and model identity
    │   ├── sensitivity_base.json                               # Immutable base-model references used by extensions
    │   ├── formal/
    │   │   ├── permutation_null.npy                            # Formal LOOCV null statistic for each permutation
    │   │   ├── permutation_null.npy.metadata.json              # Permutation axis, dtype, statistic, and tail convention
    │   │   ├── permutation_summary.csv                         # Observed statistic, nominal p, and permutation p
    │   │   ├── bootstrap_selection_frequency.npy               # Fiber selection frequency across bootstrap replicates
    │   │   ├── bootstrap_selection_frequency.npy.metadata.json # Feature axis, replicate count, and frequency semantics
    │   │   ├── bootstrap_sign_stability.npy                    # Fiber sign consistency across bootstrap replicates
    │   │   ├── bootstrap_sign_stability.npy.metadata.json      # Feature axis, replicate count, and stability semantics
    │   │   ├── bootstrap_summary.csv                           # Bootstrap replicate counts and aggregate diagnostics
    │   │   └── status.json                                     # Terminal status of formal inference
    │   │
    │   ├── in_sample/
    │   │   ├── model_predictions.npy                           # Full-sample fitted predictions in subject order
    │   │   ├── model_predictions.npy.metadata.json             # Subject axis, dtype, outcome units, and prediction meaning
    │   │   ├── baseline_predictions.npy                        # Full-sample nuisance-only baseline predictions
    │   │   ├── baseline_predictions.npy.metadata.json          # Subject axis, dtype, outcome units, and baseline meaning
    │   │   ├── predictions.csv                                 # Subject IDs, outcomes, model fits, and baseline fits
    │   │   ├── observed_scores.npy                             # Observed subject-level fiber-model scores
    │   │   ├── observed_scores.npy.metadata.json               # Subject axis, dtype, units, and score convention
    │   │   ├── observed_weights.npy                            # Full-sample fiber weights for the observed statistic
    │   │   ├── observed_weights.npy.metadata.json              # Feature axis, dtype, units, and ordering
    │   │   ├── candidate_feature_ids.npy                       # Fiber IDs entering in-sample inference
    │   │   ├── candidate_feature_ids.npy.metadata.json         # Feature axis, dtype, connectome, and ID convention
    │   │   ├── candidate_parent_indices.npy                    # Candidate-to-parent Omega or connectome-axis mapping
    │   │   ├── candidate_parent_indices.npy.metadata.json      # Feature axis, dtype, and parent-axis ordering
    │   │   ├── permutation_schedule.npy                        # Subject-label permutation schedule
    │   │   ├── permutation_schedule.npy.metadata.json          # Replicate and subject axes, RNG contract, and ordering
    │   │   ├── permutation_null_statistics.npy                 # In-sample null statistic for each permutation
    │   │   ├── permutation_null_statistics.npy.metadata.json   # Permutation axis, dtype, statistic, and tail convention
    │   │   ├── summary.json                                    # Reader-facing in-sample metrics and permutation result
    │   │   ├── technical_summary.json                          # Detailed counts, baseline metrics, and diagnostics
    │   │   ├── technical_summary.json.metadata.json            # Field definitions, units, and array references
    │   │   └── status.json                                     # Terminal status of in-sample inference
    │   │
    │   ├── sensitivity/
    │   │   ├── spatial_jitter/
    │   │   │   ├── spatial_jitter_metrics.json                 # Metrics across spatial perturbation replicates
    │   │   │   ├── spatial_jitter_metrics.json.metadata.json   # Metric definitions, replicate count, and jitter units
    │   │   │   ├── result.json                                 # Reader-facing spatial-jitter sensitivity result
    │   │   │   └── status.json                                 # Terminal status of spatial-jitter analysis
    │   │   └── oss_ppam/
    │   │       ├── oss_fiber_ids.npy                            # Ordered final fiber IDs extracted from the Omega axis
    │   │       ├── oss_activation_probability.npy              # Subject-by-fiber OSS activation probabilities
    │   │       ├── oss_binary_activation.npy                   # Thresholded subject-by-fiber activation states
    │   │       ├── oss_benefit_oriented_fiber_weights.npy      # Benefit-oriented weights applied to OSS activation
    │   │       ├── oss_full_net_fiber_scores.npy               # Subject-level net pPAM scores from the full model
    │   │       ├── oss_loocv_model_predictions.npy             # Held-out pPAM model predictions
    │   │       ├── oss_loocv_baseline_predictions.npy          # Held-out nuisance-only baseline predictions
    │   │       ├── oss_permutation_null_statistics.npy         # pPAM null statistic for each permutation
    │   │       ├── oss_permutation_summary.json                 # Observed pPAM statistic and permutation p-value
    │   │       ├── oss_plain_activation_model_comparison.json  # Weighted pPAM versus plain-activation comparison
    │   │       ├── result.json                                 # Reader-facing OSS-pPAM sensitivity result
    │   │       └── status.json                                 # Terminal status of OSS-pPAM analysis
    │   │
    │   ├── visualization/
    │   │   ├── paired_fit/
    │   │   │   ├── in_sample_loocv_fit.png                     # Raster paired in-sample and LOOCV fit figure
    │   │   │   ├── in_sample_loocv_fit.pdf                     # Publication-ready vector fit figure
    │   │   │   └── result.json                                 # Plotted values, statistics, labels, and style provenance
    │   │   ├── spatial_2d/
    │   │   │   ├── direct_streamline/
    │   │   │   │   ├── maps/
    │   │   │   │   │   └── display.nii.gz                                  # Single 1 mm FWHM, 0.1 mm direct-streamline display map
    │   │   │   │   ├── figures/
    │   │   │   │   │   ├── display.png                                       # Raster direct-streamline display
    │   │   │   │   │   ├── display.pdf                                       # Publication-ready direct-streamline display
    │   │   │   │   │   └── result.json                                       # Projection source, display transform, slices, and style
    │   │   │   │   └── projection_qc.json                                  # Streamline-to-voxel projection coverage checks
    │   │   │   └── target_conditioned/
    │   │   │       ├── all_coverage/
    │   │   │       │   ├── maps/
    │   │   │       │   │   └── display.nii.gz                                  # Single target-conditioned all-coverage display map
    │   │   │       │   ├── figures/
    │   │   │       │   │   ├── display.png                                       # Raster all-coverage target-conditioned display
    │   │   │       │   │   ├── display.pdf                                       # Publication-ready all-coverage display
    │   │   │       │   │   └── result.json                                       # Source, display transform, slices, and style
    │   │   │       │   ├── tables/
    │   │   │       │   │   └── target_scores.csv                            # Target-level score and support summary
    │   │   │       │   ├── target_score_qc.json                             # Target score completeness and range checks
    │   │   │       │   └── voxel_composition_qc.json                        # Scored and unscored voxel composition checks
    │   │   │       ├── selected_sweet_sour/
    │   │   │       │   ├── maps/
    │   │   │       │   │   └── display.nii.gz                                  # Single selected-fiber target-conditioned display map
    │   │   │       │   ├── figures/
    │   │   │       │   │   ├── display.png                                       # Raster selected-fiber target-conditioned display
    │   │   │       │   │   ├── display.pdf                                       # Publication-ready selected-fiber display
    │   │   │       │   │   └── result.json                                       # Source, display transform, slices, and style
    │   │   │       │   ├── tables/
    │   │   │       │   │   ├── target_scores.csv                            # Scores for targets reached by selected fibers
    │   │   │       │   │   └── fiber_target_membership.csv                  # Selected-fiber membership by target
    │   │   │       │   ├── target_score_qc.json                             # Selected-target score checks
    │   │   │       │   └── voxel_composition_qc.json                        # Selected-fiber voxel composition checks
    │   │   │       ├── figures/
    │   │   │       │   ├── target_score_dual_raincloud.png                  # Raster sweet-versus-sour target distribution
    │   │   │       │   ├── target_score_dual_raincloud.pdf                  # Vector sweet-versus-sour target distribution
    │   │   │       │   └── target_score_dual_raincloud.json                 # Values, labels, limits, and style provenance
    │   │   │       └── tables/
    │   │   │           └── target_fiber_distributions.csv                   # Target-level sweet and sour fiber distributions
    │   │   └── spatial_3d/
    │   │       ├── categorical/
    │   │       │   ├── figures/
    │   │       │   │   └── {scale_id}_fiber_reference_view01.pdf            # Categorical sweet/sour 3D fiber view
    │   │       │   └── export_manifest.json                                 # Camera, category colors, fonts, and sources
    │   │       └── coefficient/
    │   │           ├── figures/
    │   │           │   └── {scale_id}_fiber_coefficient_reference_view01.pdf # Coefficient-colored 3D fiber view
    │   │           └── export_manifest.json                                 # Camera, vik mapping, fonts, and sources
    │   └── report/
    │       └── summary.json                                                  # Reader-facing endpoint summary and references
    │
    └── addon/
        ├── branches/
        │   ├── no_delta_reference/
        │   │   └── connectomes/
        │   │       ├── {formal_connectome_id}/
        │   │       │   ├── observed/                     # Unadjusted formal-connectome inputs
        │   │       │   └── resolver/                     # Unadjusted formal-connectome model
        │   │       └── {sensitive_connectome_id}/
        │   │           ├── observed/                     # Unadjusted sensitive-connectome inputs
        │   │           └── formal_source_evaluation/     # Unadjusted formal-source evaluation
        │   └── delta_reference_adjusted/
        │       └── connectomes/
        │           ├── {formal_connectome_id}/
        │           │   ├── observed/                     # Delta-adjusted formal-connectome inputs
        │           │   └── resolver/                     # Delta-adjusted formal-connectome model
        │           └── {sensitive_connectome_id}/
        │               ├── observed/                     # Delta-adjusted sensitive-connectome inputs
        │               └── formal_source_evaluation/     # Delta-adjusted formal-source evaluation
        ├── final_model.json                              # Selected add-on branch, connectome, thresholds, and fit
        ├── sensitivity_base.json                         # Base references consumed by add-on extensions
        ├── formal/                                       # Same formal-inference file contract as reference
        ├── in_sample/                                    # Same in-sample file contract as reference
        ├── sensitivity/                                  # Add-on sensitivity results
        │   ├── spatial_jitter/                           # Same jitter file contract as reference
        │   └── oss_ppam/                                 # Same OSS-pPAM file contract as reference
        ├── visualization/                                # Figures derived from the selected add-on model
        │   ├── paired_fit/                               # Same paired-fit file contract as reference
        │   ├── spatial_2d/                               # Add-on 2D spatial outputs
        │   │   ├── direct_streamline/                    # Same direct-streamline contract as reference
        │   │   └── target_conditioned/                   # Same target-conditioned contract as reference
        │   └── spatial_3d/                               # Add-on 3D spatial outputs
        │       ├── categorical/                          # Sweet/sour categorical fiber rendering
        │       └── coefficient/                          # Coefficient-colored fiber rendering
        └── report/
            └── summary.json                              # Reader-facing add-on summary and references
```

Only the formal connectome creates `resolver/`. A sensitive connectome creates
`formal_source_evaluation/`. Zero or more sensitive-connectome directories may
exist. The add-on branch subtrees use the same connectome-specific artifact
contracts as the reference subtree.

Each published NPY or NIfTI file has an adjacent
`{filename}.metadata.json` when axis, shape, dtype, unit, or coordinate-space
information is required to interpret the payload. The sidecar does not contain
or require a checksum.

Unicode target-ID arrays record their NumPy dtype in a directly parseable form,
such as `<U17`; numeric arrays retain their existing canonical dtype names.

## Individualized Seed-Target Result Tree

The individualized model publishes one target-level reference result and one
target-level add-on result for every configured scale:

Selecting `addon_individualized` for execution also selects its completed
`reference_individualized` dependency for publication. The selection list in
the resolved run configuration is therefore an execution request, not
permission to omit the reference role from the two-role individualized
publication. Publication must close both roles before visualization begins.

```text
/Volumes/VAL/STNSNr/summary/spot/individualized_seed_target/
├── resolved_model.yaml                         # Resolved target model configuration used by all scales
├── model_manifest.json                         # Model roles, scale IDs and display labels, publication contents, and terminal status
├── final_model_selection.csv                   # Selected tau, Coverage, fallback, and target counts
├── final_statistics.csv                        # Paired in-sample and LOOCV statistics by scale and role
├── complete.json                               # Terminal marker for all individualized results
│
└── {scale_id}/
    ├── complete.json                           # Terminal marker for both roles of this scale
    │
    ├── reference/
    │   ├── observed/
    │   │   ├── source_scan.csv                 # Subject, side, target, tau, burden, and support rows
    │   │   ├── source_scan_qc.json             # DWI, tractography, E-field, and target availability summary
    │   │   └── status.json                     # Terminal observed-input status
    │   ├── resolver/
    │   │   ├── target_ids.npy                  # Ordered 17-target axis used by all resolver arrays
    │   │   ├── target_ids.npy.metadata.json    # Target names, ordering, dtype, and membership semantics
    │   │   ├── full_weights.npy                # Full-sample benefit-oriented target coefficients
    │   │   ├── full_weights.npy.metadata.json  # Target axis, coefficient definition, and sign convention
    │   │   ├── full_centers.npy                # Full-sample target-burden means used for score scaling
    │   │   ├── full_scales.npy                 # Full-sample target-burden standard deviations
    │   │   ├── fold_weights.npy                # LOOCV training-fold target coefficients
    │   │   ├── fold_weights.npy.metadata.json  # Fold and target axes
    │   │   ├── fold_centers.npy                # Training-fold target-burden means
    │   │   ├── fold_scales.npy                 # Training-fold target-burden standard deviations
    │   │   ├── fold_valid_masks.npy            # Fold-local target stability and finite-coefficient masks
    │   │   ├── fold_valid_masks.npy.metadata.json # Fold and target mask semantics
    │   │   ├── target_activation_support.csv   # Full and fold target counts, fractions, and Coverage
    │   │   ├── target_stability.csv            # Coverage, coefficient, rank, fold frequency, nominal p, and FDR q
    │   │   ├── subject_order.csv               # Canonical subject order for arrays and predictions
    │   │   ├── scores.csv                      # Bilateral burdens, target-model scores, and outcomes
    │   │   ├── loocv_predictions.csv           # Held-out model and nuisance-only predictions
    │   │   ├── source_selection.json            # Selected tau, Coverage, fallback, and support counts
    │   │   └── status.json                     # Terminal resolver status
    │   ├── final_model.json                    # Final source, target set, fit, and model identity
    │   ├── formal/
    │   │   ├── permutation_null.npy            # Formal LOOCV null statistic
    │   │   ├── permutation_null.npy.metadata.json # Permutation axis and statistic definition
    │   │   ├── permutation_summary.csv         # Observed statistic, nominal p, and permutation p
    │   │   ├── bootstrap_target_coefficients.npy # Target coefficient by bootstrap replicate
    │   │   ├── bootstrap_target_coefficients.npy.metadata.json # Replicate and target axes
    │   │   ├── bootstrap_summary.csv           # Percentile interval, sign stability, and finite counts
    │   │   └── status.json                     # Terminal formal-inference status
    │   ├── in_sample/
    │   │   ├── model_predictions.npy           # Full-sample fitted predictions
    │   │   ├── model_predictions.npy.metadata.json # Subject axis and outcome units
    │   │   ├── baseline_predictions.npy        # Nuisance-only full-sample predictions
    │   │   ├── baseline_predictions.npy.metadata.json # Subject axis and outcome units
    │   │   ├── predictions.csv                 # Outcomes, scores, model fits, and baseline fits
    │   │   ├── summary.json                    # Reader-facing in-sample statistics and permutation result
    │   │   ├── technical_summary.json          # Counts, baseline metrics, and paired LOOCV references
    │   │   └── status.json                     # Terminal in-sample status
    │   ├── sensitivity/
    │   │   └── spatial_jitter/
    │   │       ├── observed_statistic.json     # Selected final-model statistic and perturbation contract
    │   │       ├── null_statistics.npy         # Statistic for every completed jitter replicate
    │   │       ├── null_statistics.npy.metadata.json # Replicate axis and statistic definition
    │   │       ├── summary.json                # Jitter p value and finite-replicate counts
    │   │       └── status.json                 # Terminal jitter status
    │   ├── visualization/
    │   │   ├── paired_fit/
    │   │   │   ├── in_sample_loocv_fit.png     # Paired fitted-versus-observed panel
    │   │   │   ├── in_sample_loocv_fit.pdf     # Vector publication form of the same panel
    │   │   │   ├── result.json                 # Metrics, labels, and source references
    │   │   │   └── complete.json               # Terminal paired-fit component marker
    │   │   ├── spatial_2d/
    │   │   │   └── target_conditioned/
    │   │   │       └── all_coverage/
    │   │   │           ├── maps/
    │   │   │           │   └── display.nii.gz  # Display-only target-derived PPMI voxel map
    │   │   │           ├── figures/
    │   │   │           │   ├── display.png     # Boxsize axial, coronal, and sagittal panel
    │   │   │           │   ├── display.pdf     # Vector publication form of the panel
    │   │   │           │   └── result.json     # Color limits, slice positions, and source references
    │   │   │           ├── tables/
    │   │   │           │   └── target_scores.csv # Target coefficients used for PPMI projection
    │   │   │           ├── target_score_qc.json # Scored and excluded PPMI fiber counts
    │   │   │           ├── voxel_composition_qc.json # Seed-voxel support and target-pattern counts
    │   │   │           └── complete.json       # Terminal all-coverage component marker
    │   │   ├── spatial_3d/
    │   │   │   └── coefficient/
    │   │   │       ├── figures/
    │   │   │       │   └── {scale_id}_fiber_coefficient_reference_view01.pdf
    │   │   │       ├── export_manifest.json    # Relative PDF, camera, font, and color-limit record
    │   │   │       └── complete.json           # Terminal 3-D component marker
    │   │   └── target_coefficient_stability/
    │   │       ├── target_coefficient_stability.png # Target coefficient and stability panel
    │   │       ├── target_coefficient_stability.pdf # Vector publication form
    │   │       ├── target_statistics.csv       # Full, fold, bootstrap, Coverage, and FDR statistics
    │   │       ├── result.json                 # Figure labels and source references
    │   │       └── complete.json               # Terminal target-figure marker
    │   └── report/
    │       └── summary.json                    # Reader-facing reference result
    │
    └── addon/
        └── same contract as reference          # Add-on burden also reports HF-overlap exclusion
```

The continuous scientific predictor is target activation burden. A side burden
is the sum of suprathreshold streamline peak E values divided by all valid
fibers assigned to that target. A patient supports a target when either side
passes the configured count and fraction thresholds, while the score uses the
mean of the two actual side burdens. A missing target denominator is missing
data, not zero activation.

For the add-on model, all valid target fibers remain in the denominator and
only add-on-active, reference-inactive fibers contribute to the numerator.

Target-level nominal p values are two-sided partial-correlation t
approximations. Each target is ranked and residualized on its own finite
patient rows. Degrees of freedom equal the finite row count minus the rank of
the ranked nuisance design including its intercept minus one.
Benjamini-Hochberg q values use the finite target tests within one scale, one
role, and the selected tau/Coverage cell as the correction family. Nominal p
and FDR q values are report-only and never change target inclusion, resolver
selection, or patient scores. The target coefficient stability panel marks a
target with `*` only when its finite FDR q value is < 0.05.

Patient tractography is not pooled into the final group spatial map. The final
17 target coefficients are projected through the shared PPMI 85
`target_projections` leaf. That physical projection is independent of scale,
outcome, and model weights. It is computed once and reused by all
individualized endpoints.

The PPMI fiber scope is `role_seed_connected_with_target_hit`, not the
normative-fiber final resolver axis. A fiber that hits multiple targets receives
the equal mean of all finite coefficients for those targets. A fiber with no
finite scored target is excluded and reported. Each scale and role selects its
own zero-centered symmetric color limits; the corresponding 2-D and 3-D views
reuse that one range.

## Visualization Placement

Visualization is a consumer of scientific files in the same scale and model
role. It never supplies inputs to model selection, prediction, formal
resampling, spatial jitter, or OSS-pPAM.

For `individualized_seed_target/`, the scientific publisher writes all
scientific payloads and the completed `model_manifest.json`, but it does not
write the scale-level or model-root `complete.json` markers. The visualization
consumer writes a scale marker only after both role visualizations are
complete, and writes the model-root marker only after every configured scale
is complete. Therefore no terminal marker can cause resume to skip missing
visualization files.

Spatial visualization reads one configuration file:
`my_helper/stnsnr/config/four_model_v1/spatial_result_visualization.yaml`.
The corresponding production copy is
`/Volumes/VAL/STNSNr/config/spot/spatial_result_visualization.yaml`. The file
contains no schema or model-set version. Shared `display_map` parameters apply
to voxel and fiber display derivatives; modality-specific masks, labels,
projection rules, seeds, and targets remain under separate `voxel` and `fiber`
sections. The individualized fiber section identifies both the PPMI 85
connectome ID and its explicit `data.mat` path; the postprocess does not infer
that path from a run directory or from a different model publication. The
output filename `display.nii.gz` is fixed and is not configurable. The PPMI
projection and scale-role color-limit fields are validated only when the
`individualized_seed_target` section is present; they are not prerequisites
for direct-streamline normative-fiber visualization.

The direct-streamline fiber view projects the complete paths of all selected
sweet and sour fibers. Intersection with the configured anatomical role seed
is recorded as visualization coverage information, not used as an additional
fiber-eligibility gate. A selected fiber outside that display seed therefore
remains in the direct projection and does not invalidate the endpoint.

Visualization figures are published only as PNG and PDF files. SVG output is
not part of the formal result contract.

For mixed 3-D PDF export, anatomy, fibers, atlas wireframes, and the RAS triad
are raster composition layers. The coefficient colorbar, all five symmetric
tick labels, and its full semantic label are drawn after every raster layer so
that no overlay can obscure or clip them. Rendered-page acceptance requires a
complete color strip and legible signed tick labels inside the page boundary.

The main-publication dependency direction is:

```text
observed/resolver/final_model/formal/in_sample
→ visualization
```

It never runs in the reverse direction.

For `individualized_seed_target`, spatial jitter is an independent extension
of a completed main publication. It reads the main final model and portable
sensitivity checkpoint, publishes below the individualized extension domain,
and never becomes a prerequisite for main visualization or main completion.
When an add-on final uses `delta_reference_adjusted`, the sensitivity planner
must select the matched reference input and prepared exposure from the same
scientific family: `addon_voxel` pairs with `reference_voxel`, `addon_fiber`
pairs with `reference_fiber`, and `addon_individualized` pairs with
`reference_individualized`. A matched reference from another family is not an
allowed substitute.

The parent input bundle contains both the individualized model YAML and its
MRtrix tracking YAML. The bundled individualized profile resolves the bundled
tracking file relative to itself. A tracking-file path change alone is not a
scientific change; the parsed tracking values actually consumed by the model,
including `atlas.space`, define scientific invalidation.

Three-dimensional PDF names use:

```text
{scale_id}_{unit}_{role}_view{index}.pdf
```

Coefficient-colored fiber PDFs use:

```text
{scale_id}_fiber_coefficient_{role}_view{index}.pdf
```

The view index identifies a configured camera view and is not a version
identifier.

All-scale 3-D export is scheduled at scale granularity. Independent
`MATLAB -nodisplay -batch` processes receive disjoint scale IDs, and the
default process count is half of the host logical CPU count, rounded down with
a minimum of one. This is an execution-only default and is not stored in the
scientific YAML or JSON. Existing complete deterministic component paths are
reused, so interruption or a worker-local failure does not invalidate or
rebuild other scales.

## Runtime And Cache Tree

```text
/Volumes/VAL/STNSNr/summary/spot/.cache/
└── runs/
    ├── main/
    │   ├── request.json
    │   ├── tasks/
    │   │   └── {task_id}/
    │   │       ├── task.json
    │   │       └── complete.json
    │   └── runtime_work/
    ├── spatial_jitter/
    │   └── same incomplete-run structure as main
    └── oss_ppam/
        └── same incomplete-run structure as main
```

`runs/` stores only task state and temporary work for an incomplete run.
In-sample inference is part of `main`; combined execution does not create an
independent result or run directory; visualization writes its requested formal
files directly and has no persistent cache.

When a stage has published all of its requested files and the corresponding
formal `complete.json`, its run directory is no longer required for resume.
It is then cleanup-eligible without a YAML cleanup option. Failed or partial
work is never cleaned, so its task markers and `runtime_work/` remain
available.

The cache contains no completed E-field, connectome, voxel, fiber, jitter, OSS,
or visualization result. Completed reusable physical data live only below
`spot/shared/`.

## Resume Contract

Resume resolves existing data in this order:

1. completed formal results below `direct_voxel/`, `normative_fiber/`, or
   `individualized_seed_target/`;
2. completed reusable physical leaves below `shared/`; and
3. unfinished task state below `.cache/runs/`.

A higher-priority completed destination is authoritative and does not require
the lower-priority runtime state to exist.

### Task Resume

A task is restored when both paths exist:

```text
.cache/runs/{stage}/tasks/{task_id}/task.json
.cache/runs/{stage}/tasks/{task_id}/complete.json
```

A missing task marker makes only that task eligible to run. It does not
invalidate unrelated tasks.

### Shared Physical Resume

A shared physical leaf is restored when its expected payload files and sibling
`complete.json` exist below:

```text
/Volumes/VAL/STNSNr/summary/spot/shared/
```

A missing leaf marker makes only that E-field, connectome, voxel exposure,
fiber exposure, jitter block, or OSS row eligible to run. It does not
invalidate another shared physical unit.

### Published-Result Resume

A completed model, scale, role, or sensitivity destination is reused directly.
A later sensitivity run may load the published `final_model.json` and its
scientific payloads without the parent run directory. Existing published
statistics and figures are not regenerated merely because `.cache/` is absent.

### Incomplete-Run Resume

Run directories exist only for incomplete work. Completion is recognized from
the destination `complete.json` below `spot/shared/`, the matching scale, or
the matching model root. A completed destination returns without reopening its
run directory.

### Scale Resume

A scale publication is complete when:

```text
{model_root}/{scale_id}/complete.json
```

exists. A missing scale marker makes only that scale eligible for re-output.

### Model Resume

A model publication is complete when:

```text
{model_root}/complete.json
```

exists. A completed model is not reopened while publishing the other model.

### Cross-Machine Reuse

Copying the following directories preserves every completed result and allows
new downstream sensitivity or visualization work to reuse them:

```text
spot/shared/
spot/direct_voxel/
spot/normative_fiber/
spot/individualized_seed_target/
```

Copying `spot/.cache/` is optional. It is needed only to continue a task that
was interrupted before publishing its destination. Omitting it never
invalidates completed shared or formal results.

### Force

Force applies only to the explicitly selected shared leaf, task, run, scale, or
model root. An existing untracked target is moved to the operating-system Trash
before replacement. Force does not clear unrelated shared data or model
outputs.

## Runtime And Shared-Data Dependence

Completed shared physical data are formal reusable inputs, not caches. Runtime
state affects only recovery from incomplete work. Visualization has no
persistent intermediate cache.

| State | Required action |
|---|---|
| Result path and `complete.json` exist | Reuse the result |
| Published final model exists and a new sensitivity is requested | Load the published model and continue from that dependency |
| Task is incomplete and its shared physical leaf is complete | Reuse the shared data and continue downstream |
| One shared physical leaf is missing | Recompute only that physical unit and its dependents |
| `.cache/` is absent but required published and shared data are complete | Continue without reconstructing the old run directory |
| One visualization output is missing | Rebuild only that visualization file or component |
| A run is failed or partial | Preserve its task markers and temporary work |

## Invalidation Scope

| Changed input | Invalidated scope |
|---|---|
| One source E-field or its spatial transform parameters | The matching transformed E-field, its voxel, fiber, or individualized target exposures, applicable jitter blocks or OSS rows, and only their downstream model results |
| One connectome input | The matching prepared connectome geometry, fiber exposures, fiber jitter blocks, OSS rows, and only their downstream normative-fiber results |
| One scale's outcome, nuisance, or other endpoint-specific input | That scale and role below the applicable model root; no shared physical data |
| Tau or Coverage settings | The affected scale and role from thresholding onward; continuous transformed E-fields and unperturbed target peak-E arrays remain reusable |
| Individualized activated-fiber count or fraction support threshold | The affected individualized model results and matching jitter blocks because those blocks store threshold-derived support; source E-fields and unperturbed target peak-E arrays remain reusable |
| One add-on branch input | That branch, its selected final model when applicable, and its downstream results |
| Spatial-jitter settings | The matching jitter blocks and their endpoint sensitivity results only |
| OSS physical settings | The matching OSS rows and their downstream pPAM results only |
| One visualization style | The matching visualization figures only |
| One FWHM display setting | The matching smoothed NIfTI and section figures only |
| Worker count, RAM telemetry, or timeout | No scientific result |
| YAML comments, whitespace, ordering, or equivalent serialization | No scientific result |

No whole-repository, whole-configuration-file, or whole-output-tree hash may
trigger global invalidation.

Normal resume does not inspect content identity to discover these changes. It
reuses an existing path with `complete.json`. When a scientific input is
intentionally changed, the caller uses force only for the affected shared
leaves or result branch listed above and their direct dependents.

## Publication Order

Shared physical data are published first:

```text
complete shared leaf payloads
→ shared leaf complete.json
→ all requested shared leaves
→ shared/complete.json
```

Each model is then published:

```text
scientific scale payloads
→ in-sample and sensitivity payloads
→ visualization payloads
→ scale complete.json
→ final_model_selection.csv
→ final_statistics.csv
→ model_manifest.json
→ model complete.json
```

The main formal result set is complete after the shared root and all selected
model-root completion markers exist. An individualized spatial-jitter
extension has its own terminal marker and is not part of the main formal gate.

## Migration Rule

Migration reuses the already completed scientific publications and sensitivity
results. It does not rerun main modeling, in-sample permutation, spatial
jitter, or OSS-pPAM merely to change paths.

The migration copies all six completed reusable categories into the fixed
`spot/shared/` tree:

```text
spatially transformed E-fields
prepared connectome geometry
continuous voxel exposures
continuous fiber exposures
physical jitter exposure blocks
OSS activation-probability rows
```

Prepared-artifact staging copies, axis-equivalence records, visualization
intermediates, and completed run wrappers are not migrated as shared scientific
data. Missing or incomplete source entries are not promoted and remain
eligible for local recomputation at their destination leaf.

Historical result directories, standalone postprocess directories, obsolete
indexes, and old cache layouts remain untouched until the applicable shared and
model-root completion markers exist. Untracked historical directories are then
moved to the operating-system Trash rather than permanently deleted.
Only an actively incomplete run that still needs subtask-level recovery may be
copied into `spot/.cache/runs/`; completed run wrappers are not migrated.

## Final Closeout Execution

This section records the frozen implementation and publication work for the
integrated contract. The direct-voxel and normative-fiber closeout reused
completed scientific results. The individualized extension computes its new
scientific results and then publishes them into the same root. Performance
benchmarking, fault-injection acceptance, and plan-by-plan audits remain
outside the closeout scope.

### Final Scope

The closeout publishes 28 scale IDs. Each scale has `reference` and `addon`
roles in all three model families, giving 168 model-role endpoints:

```text
28 scales
× 2 roles
× 3 model families
= 168 endpoints
```

Every applicable endpoint receives its completed main result, formal
inference, in-sample result, visualization outputs, and reader-facing summary.
The individualized main publication does not require or contain a
spatial-jitter result; that result is published only by a later sensitivity
extension. OSS-pPAM is published only for normative-fiber endpoints. The
previously completed combined run does not define another
scientific result and therefore does not create a separate result subtree.

Visualization is generated from the newly published formal data, never from a
historical run directory. The published figure formats are PNG and PDF only.
JSON files beside figures contain plotted values and rendering provenance; they
are not figure formats. No SVG file is generated.

### Authoritative Migration Sources

The following historical locations were the one-time migration inputs. They
were moved to the operating-system Trash after the historical shared,
direct-voxel, and normative-fiber completion markers were written and
validated:

| Destination content | Existing source |
|---|---|
| Direct-voxel main results | `/Volumes/VAL/STNSNr/summary/spot/direct_voxel/dual_frequency_four_model_v1` |
| Normative-fiber main results | `/Volumes/VAL/STNSNr/summary/spot/normative_fiber/dual_frequency_four_model_v1` |
| Direct-voxel and normative-fiber in-sample results | The completed `task17-final-in-sample-v2-20260719` extension below each historical model root |
| Direct-voxel and normative-fiber spatial-jitter results | The completed `task17-jitter-v8-support-preserving-formal-20260719-v2` extension below each historical model root |
| Normative-fiber OSS-pPAM results | The completed `task17-oss-v2-omega-only-formal-20260726-v2` extension below the historical normative-fiber root |
| Transformed E-fields, voxel exposures, fiber exposures, jitter blocks, and OSS rows | `/Volumes/VAL/STNSNr/cache/dual_frequency/shared_exposure_v2` |
| Prepared connectome geometry | `/Volumes/VAL/STNSNr/cache/dual_frequency_task17_parity_v1/shared_exposure_v2/connectome_geometry` |

The names above identify historical sources only. Their task names, dates,
wrapper names, and version labels are not copied into destination paths or
destination metadata. The combined extension is not copied because its
scientific payloads are already represented by the independent jitter and OSS
sources. Performance warm-seed directories and prepared-artifact staging
directories are not migration sources.

### Source Promotion Boundary

Migration validates an input once when parsing the source JSON or YAML and when
opening the payload files required for that source kind. A source shared leaf
is eligible for promotion only when its required payload set is present:

| Shared category | Required source payload |
|---|---|
| Transformed E-field | transformed NIfTI and its source manifest |
| Connectome geometry | point array, point-offset array, and source manifest |
| Voxel exposure | exposure array and source manifest |
| Fiber exposure | exposure array, ordered fiber-ID array, and source manifest |
| Jitter block | the block-kind-specific exposure arrays, feature keys, replicate indices, replicate seeds, and source manifest |
| OSS row | ordered fiber-ID array, probability array, and source metadata |

Partial source leaves are not promoted. They remain missing at the destination
and may be recomputed only if a requested final result depends on them.

The publisher derives each human-readable destination identifier from parsed
semantic fields such as subject, side, frequency, stimulation condition, model
family, and connectome. It does not use the historical hash directory name as
the destination identifier. Destination `metadata.json` contains only the
scientific fields needed to interpret the payload and uses relative references
within the formal result tree.

Each destination payload is copied to a same-directory temporary sibling and
atomically installed. This local atomic write is retained because physical VAL
disconnects occurred during prior production runs. It prevents a partial file
from occupying the final path without introducing a staging tree, checksum, or
retry mechanism. After every required payload is present, the publisher writes
the leaf marker last with the minimal content:

```json
{"status":"complete"}
```

No source-file hash, repository hash, code identity, directory hash, or
machine-specific path is written or checked.

### Result Publication

Main scientific arrays, NIfTI files, predictions, and inference tables are
copied without numerical transformation. JSON and YAML documents are rewritten
only where required to:

- use the integrated destination paths;
- replace absolute and historical-run references with relative formal paths;
- remove legacy task, wrapper, hash, repository, and machine identity fields;
- expose the selected tau and Coverage actually used after fallback;
- pair in-sample and LOOCV statistics in `final_statistics.csv`; and
- describe binary axes, units, spaces, and value semantics in adjacent
  metadata.

In-sample and sensitivity results are placed directly below the matching model,
scale, and role. The model-local `final_model_selection.csv` and
`final_statistics.csv` are regenerated from those published endpoint results.
They are presentation summaries, not resume inputs.

The existing visualization implementation is adapted to read only the
integrated formal paths. It generates paired-fit, spatial 2D, configured
spatial 3D, and fiber target-summary artifacts exactly where this contract
lists them. It does not create a standalone postprocess root, persistent
visualization cache, empty directory, SVG output, or duplicate unsmoothed
scientific map.

### Resume And Force During Closeout

Resume follows two levels:

1. If the expected unit-level `complete.json` exists, the whole shared leaf,
   scale, or model is skipped.
2. If the marker is absent, the publisher examines only the deterministic
   expected paths for that unit. Existing files are skipped by path and file
   name; only missing files are generated or copied. The marker is written
   after the expected file set is present.

This allows an interrupted migration or visualization pass to continue without
reopening completed scientific computations. A normal resume performs no
content hash comparison.

Main-run sensitivity checkpoint assembly must consume the completed typed task
records restored by resume. Voxel and normative-fiber endpoints use
`PreparedExposureRecord`; individualized seed-target endpoints use
`PreparedTargetExposureRecord`. For the individualized record, the portable
shared exposure descriptor is `patient_burdens`, with its target axis and
metadata. Checkpoint assembly must not reject a completed individualized final
merely because its preparation record is not the voxel/fiber record class.

Force is explicitly scoped to one selected shared leaf, visualization
component, role, scale, or model root. It does not clear sibling results or the
whole output root. Existing untracked destination files inside that selected
scope are moved to the operating-system Trash before replacement.

### Resumed-Run Provenance

Run-local configuration snapshots and manifest identities are publication
provenance, not task-completion gates. Before a resumed run is published, they
must describe the parsed configuration used by its terminal execution plan.
If a run-local snapshot is stale after an explicitly approved semantic
configuration change, it is corrected only after the runner and workers have
exited. The existing untracked snapshot is moved to the operating-system Trash
before its corrected replacement is written.

This metadata correction does not invalidate completed task paths,
`complete.json` markers, shared physical data, or scientific payloads. A file
SHA may be recorded for provenance after correction, but it must not trigger a
rerun. Scientific invalidation remains limited to task identities and shared
leaves whose parsed inputs changed.

### Implementation Sequence

The closeout was performed in this order:

1. Treat this document as the only output and resume contract.
2. Change workflow path resolution so `output.root` is the only configurable
   output path and all five derived roots are fixed.
3. Add the seven-category shared-data promoter and shared-data resolver.
4. Change main, in-sample, jitter, and OSS publishers to write the integrated
   model trees and relative metadata defined here.
5. Change formal postprocessing to read the integrated model trees and publish
   visualization beneath each endpoint.
6. Run the publisher on the existing completed sources. Resume the same
   publication if interrupted; do not create another destination wrapper.
7. Write scale markers, model summary tables, model manifests, model markers,
   and finally `shared/complete.json` as their dependencies become complete.
8. After all four publication root markers exist, move historical wrapper directories,
   completed run directories, standalone postprocess outputs, obsolete indexes,
   and old cache layouts to the operating-system Trash.

Steps 2 through 5 change paths and publication only. They must not invoke main
model fitting, bootstrap, in-sample permutation, spatial jitter, or OSS solver
work when the corresponding completed source payload is present.

### Focused Verification

Only the smallest checks needed for the new publication path are retained:

- parsing one workflow YAML with `output.root`;
- deriving the fixed shared, model, and hidden runtime paths;
- promoting one complete and one incomplete fixture for each shared category;
- resuming an incomplete destination without rewriting existing files;
- applying force only to the selected local scope;
- publishing one direct-voxel, one normative-fiber, and one individualized
  seed-target endpoint fixture;
- confirming that visualization reads the integrated destination and produces
  only the declared PNG, PDF, JSON, NIfTI, CSV, and NPY files; and
- checking the completed real publication for the 28 configured scales, both
  roles, all three model roots, and the four publication root completion
  markers.

No cold/warm performance matrix, resource-performance acceptance, injected
failure matrix, deletion-rebuild exercise, or three-plan audit is run.

### Final Completion Gate

Closeout is complete when:

1. all required shared leaves used by the published results have their local
   completion markers;
2. all 168 model-role endpoints have their applicable main scientific,
   in-sample, visualization, and report payloads; sensitivity payloads are
   required only by a separately requested extension;
3. every configured scale has `{model_root}/{scale_id}/complete.json`;
4. each model has its resolved configuration, model manifest, final model
   selection table, final statistics table, and model-root marker;
5. `shared/complete.json`, `direct_voxel/complete.json`,
   `normative_fiber/complete.json`, and
   `individualized_seed_target/complete.json` all exist; and
6. the completed publication contains none of the prohibited wrapper,
   versioned destination, standalone postprocess, index, SVG, or hash-gated
   resume structures.

The hidden runtime cache is not part of this completion gate. Once the four
root markers exist, the final scientific publication remains usable and
portable without `.cache/`.

### Existing Two-Domain Completion Evidence

Before the individualized root was added to the target contract, the
direct-voxel and normative-fiber publication satisfied its two-domain gate with
the following destination-only evidence. This evidence does not prove the
individualized extension complete:

- the result root contained `README.md`, `shared/`, `direct_voxel/`, and
  `normative_fiber/`;
- the shared root and both model roots contain the exact minimal
  `{"status":"complete"}` marker;
- both model roots contain all 28 configured scales, for 112 model-role
  endpoints in total;
- the declared scientific closure contains 12214 files with no missing path;
- all 112 reader-facing endpoint summaries and all 56 scale completion markers
  are present;
- all-scale 3-D rendering used eight disjoint-scale headless MATLAB workers on
  the 16-logical-core host and completed 224 single-page Arial PDFs;
- the formal 3-D publication contains those 224 PDFs plus 168 relative,
  sanitized export manifests;
- visualization and final publication validation found no missing file,
  prohibited metadata field, AppleDouble sidecar, SVG file, versioned
  destination, historical wrapper, standalone postprocess root, or prohibited
  index; and
- after historical sources and caches were moved to Trash, an identical
  finalizer resume wrote no file, and all 20372 formal file paths, sizes, and
  modification times remained unchanged.
