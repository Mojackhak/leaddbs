# Four-Model YAML Profiles

This directory contains the approved direct-voxel and normative-fiber model
profiles for the dual-frequency four-model refactor.

## Profiles

- `direct_voxel_model.yaml` is the production scientific profile. It selects
  all 28 study-defined scales and uses the complete tau/Coverage grid and
  formal resampling counts.
- `direct_voxel_model_test.yaml` is a lightweight code-path smoke profile. It
  selects two scales, uses the smallest scan grid that still exercises the
  pre-specified source and two-neighbor resolver, and uses minimal resampling
  counts.
- `normative_fiber_model.yaml` is the production reference/add-on
  normative-fiber profile. It uses PPMI85 as the unique `formal` connectome and
  MGH/dTOR as `sensitive` connectomes. Every configured fold candidate minimum
  is one, so each LOOCV fold must retain at least one candidate fiber.
- `normative_fiber_model_test.yaml` is a lightweight normative-fiber code-path
  profile. It uses PPMI as `formal`, MGH as `sensitive`, two scales, a reduced
  grid, and minimal resampling counts.

The test profile is not an inferential model. Its permutation p-values,
bootstrap summaries, jitter summaries, source classification, prediction
classification, and final-model classification must not be used as scientific
results. It exists only to verify that validation, planning, observed LOOCV,
source resolution, add-on branch realization, formal-loop dispatch,
sensitivity dispatch, and artifact writing execute successfully.

Both production profiles retain the hard requirement for at least 12 complete
subjects after branch-specific exclusion.

## Shared Contract

All four profiles:

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

The normative-fiber profiles additionally require exactly one `formal`
connectome. Every configured connectome runs the complete observed grid, but
only `formal` assigns source/prediction status, realizes a final model, and
receives formal resampling, OSS, and jitter. Reference and add-on tau define
Coverage/candidate fibers only; continuous peak E-field remains in the score.
Add-on exposure retains reference-active overlap exclusion.

Fixed spatial aggregation, estimator, LOOCV, branch-role, fallback, reporting,
and smoke/equivalence behavior is defined by the corresponding
`direct_voxel_model_v1` or `normative_fiber_model_v1` schema and is not
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

The normative-fiber test scan uses tau `[600, 800, 1000]` and Coverage
`[5, 6]`, with `minimum_adjacent_passing_cells: 1`. It preserves production
exposure, scoring, branch-role, fallback, and connectome-role semantics.

`workflow.yaml` is the execution-policy profile for the new runtime. It
references `direct_voxel_model.yaml` and `normative_fiber_model.yaml`, but does
not declare default scales, endpoint phases, or connectome names. The model
profiles remain the scientific source of configured scales, the locked
endpoint pair, and connectome roles. CLI selection may narrow the configured
scales or model families, but it cannot add values absent from the model
profiles.

The runtime reads the existing `study_base.json` supplied through the CLI. It
does not create or consume an intermediate study bundle, copied clinical
table, study index, or resolved-study manifest. This configuration contract is
being implemented incrementally; current legacy outputs remain unchanged until
the new runner passes its stated acceptance checks.

## Output Contract

The authoritative configured-run publication layout and artifact schemas are
defined in `direct_voxel_output_contract.md` and
`normative_fiber_output_contract.md`.

Production publishes below:

```text
/Volumes/VAL/STNSNr/summary/spot/direct_voxel/<model_set_id>/<scale_id>/
/Volumes/VAL/STNSNr/summary/spot/normative_fiber/<model_set_id>/<scale_id>/
```

The smoke profile publishes the identical artifact contract below:

```text
/Volumes/VAL/STNSNr/validation/spot/direct_voxel/<model_set_id>/<scale_id>/
/Volumes/VAL/STNSNr/validation/spot/normative_fiber/<model_set_id>/<scale_id>/
```

Reference and add-on selected-source artifacts are stored once. A
`final_model.json` record references the realized source or add-on branch; it
does not duplicate maps, scores, predictions, or weights. ROI and atlas
postprocessing are excluded from this output contract.

## Three-Layer Test Strategy

The smoke profile is one of three complementary test layers. It cannot provide
complete branch coverage because source, prediction, branch, fallback, and
terminal statuses are data-dependent and mutually exclusive.

1. The real-data end-to-end smoke uses `direct_voxel_model_test.yaml`. It checks
   catalog construction, both configured scales, observed execution, resolver
   dispatch, final-model realization, formal/sensitivity dispatch, and artifact
   writing. A required downstream stage that is silently skipped does not count
   as a passing success-path smoke.
2. Pure state-machine unit tests provide deterministic truth-table coverage for
   source status, prediction status, branch permission, one-way fallback, and
   `no_final_model`. They do not run LOOCV or resampling.
3. Small deterministic exposure/outcome integration fixtures execute the real
   statistical kernels, fold-local scoring, resolver, prediction classifier,
   and branch-specific nuisance checks.

The integration fixture uses fixed `float64` arrays with 16 subjects, 32
voxels, 24 signal voxels, 8 background voxels, and the complete production
tau/Coverage grid. It does not draw random numbers at test time. Define
`z = linspace(-1.5, 1.5, 16)`, signal loadings from `0.8` through `1.2`, and
deterministic sinusoidal voxel variation. Background exposure remains below the
lowest production tau.

The locked source fixtures are:

```text
pre-specified: b=260, s=20 -> tau200/Coverage5 accepted with >=2 neighbors
scan fallback: b=190, s=4  -> tau200 fails; tau180/Coverage5 selected
absent:        all exposure <100 V/m -> no stable grid
```

Predictive and nonpredictive outcomes are fixed arrays whose expected MAE/RMSE
relations are verified through the production LOOCV implementation. Resolver
selection must not inspect MAE, RMSE, Q2, or rho. A single `4x4x2` synthetic
NIfTI checks the array-input adapter; state fixtures remain NumPy-only.

The adjusted nuisance covariate is always standardized. Full-sample descriptive
fitting uses the full-sample mean and population standard deviation. Every
LOOCV fit uses only that training fold's mean and population standard deviation
and applies those locked values to its held-out subject. Fold-scaling tests must
prove that changing a held-out value cannot change training-row standardized
values.

For the adjusted add-on branch, a constant or otherwise non-scalable
DeltaReferenceScore has:

```text
branch_nuisance_design_status = invalid_delta_reference_scaling
```

General full-sample or fold-specific rank deficiency has:

```text
branch_nuisance_design_status = invalid_nuisance_design
```

Either status fails only the adjusted branch. The no-delta branch remains
independently executable.
