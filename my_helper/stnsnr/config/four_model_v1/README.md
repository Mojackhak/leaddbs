# Direct-Voxel YAML Profiles

This directory contains the approved direct-voxel model profiles for the
dual-frequency four-model refactor.

## Profiles

- `direct_voxel_model.yaml` is the production scientific profile. It selects
  all 28 study-defined scales and uses the complete tau/Coverage grid and
  formal resampling counts.
- `direct_voxel_model_test.yaml` is a lightweight code-path smoke profile. It
  selects two scales, uses the smallest scan grid that still exercises the
  pre-specified source and two-neighbor resolver, and uses minimal resampling
  counts.

The test profile is not an inferential model. Its permutation p-values,
bootstrap summaries, jitter summaries, source classification, prediction
classification, and final-model classification must not be used as scientific
results. It exists only to verify that validation, planning, observed LOOCV,
source resolution, add-on branch realization, formal-loop dispatch,
sensitivity dispatch, and artifact writing execute successfully.

## Shared Contract

Both profiles:

- read scale definitions and observations from `study_base.json`;
- require every configured `scale_id` to match
  `study.scale_definitions[].scale_id` exactly;
- bind baseline `T0/program 0`, reference `T2/program 1`, and add-on
  `T3/program 2` explicitly;
- classify sources from frequency only;
- use continuous E-field values inside the selected Coverage/Omega support;
- retain reference-suprathreshold overlap exclusion for add-on exposure;
- apply the same hard-computability and DeltaReferenceScore support rules; and
- treat every configured scale as an equal engineering execution unit.

Fixed spatial aggregation, estimator, LOOCV, branch-role, fallback, reporting,
and smoke/equivalence behavior is defined by `direct_voxel_model_v1` and is not
configurable through these YAML files.

## Test Reductions

The test profile intentionally changes only workload-controlling public
parameters:

```text
scales:                    2 instead of 28
tau/Coverage scan cells:   6 instead of 60
permutation resamples:     5 instead of 10000
bootstrap resamples:       5 instead of 10000
jitter resamples:          2 instead of 1000
```

The test scan uses tau `[180, 200, 220]` and Coverage `[5, 6]`. The
pre-specified `tau=200/Coverage=5` cell remains in the grid and has enough
horizontal, vertical, and diagonal neighbors to exercise
`minimum_adjacent_passing_cells: 2`.

The existing `model.yaml`, `scales.yaml`, `study.yaml`, and `workflow.yaml`
belong to the predecessor multi-profile runtime. They are not modified by this
profile addition. The new direct-voxel profiles are configuration contracts for
the upcoming loader/runner refactor and do not imply that the current legacy
entrypoint already consumes them.
