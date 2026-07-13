# VTA Computation Performance Optimization Plan

## Document Status

```text
design_documented
implementation_not_started
current_outputs_unchanged
```

This document defines a performance optimization plan for the canonical
VTA/E-field pipeline. It does not authorize a scientific model change, an
artifact-contract change, or a model rerun.

## Goal

Reduce clean-run and incremental-run wall time while preserving:

- the canonical `simbio_onesolve` FEM backend;
- the existing voltage- and current-control boundary semantics;
- independent source-level outputs for alternating stimulation;
- native and MNI E-field/VTA outputs for every configured output leaf;
- native group-peak composition before MNI transformation;
- full native-anchor dimensions and affine;
- path-existence-based resume behavior; and
- numerical equivalence under the existing voltage/current acceptance gates.

The primary optimization target is repeated work across tasks. Increasing
`--workers` beyond the current subject-level default is not the primary
strategy.

## Current Baseline

The current canonical execution path is:

```text
Python CLI and planner
  -> subject-level ThreadPoolExecutor
  -> one MATLAB -batch process per unresolved task
  -> one canonical FEM or derived task
  -> native output
  -> MNI transformation
  -> thresholded VTA outputs
```

Current implementation characteristics:

- `matlab_bridge.py` starts one MATLAB process for each unresolved task.
- Every MATLAB invocation evaluates `addpath(genpath(repo_root))`.
- `service.py` runs subjects concurrently but executes each subject DAG
  sequentially.
- The current study configuration produces 208 planned task rows.
- Existing same-subject reuse reduces these rows to approximately 105 FEM
  solves and 8 group-peak derivations on a clean run.
- The current clean-run architecture can therefore start approximately 113
  MATLAB processes.
- Native E-field interpolation evaluates the complete native anchor grid,
  including voxels outside the FEM mesh support.
- Each requested threshold reloads the same compressed E-field.
- Existing head-model validation loads required MAT variables, after which the
  backend loads the same variables again.
- The canonical path does not yet emit structured stage-level timing.

The statement that FEM/head-model work and MATLAB startup dominate total wall
time is a working hypothesis. Stage timing must measure the actual proportions
before runtime-improvement claims are accepted.

## Global Constraints

- Do not hard-code subjects, phases, programs, clinical timepoints, HF/ULF
  labels, electrode models, or frequency-group identifiers.
- Derive every task from `study_base.json` and `vta_model.yaml`.
- Preserve the existing generic frequency-group and source task model.
- Keep reuse within the same subject and require an explicit physical
  equivalence definition.
- Continue to use file existence as the persistent resume criterion.
- Do not add artifact hashes, leaf provenance files, or an independent
  resolved manifest.
- Preserve every alternating source's native and MNI E-field and VTA outputs.
- Preserve the canonical alternating sequence:

```text
source-level native E-fields
  -> native voxelwise maximum
  -> native group-peak thresholds
  -> MNI transformation of the native group peak
  -> MNI group-peak thresholds
```

- Preserve complete native-anchor dimensions and affine.
- Do not silently omit configured output spaces or artifacts.
- Keep the default concurrency at three subject workers until measured memory
  and timing results justify another value.
- Do not combine subject-level process parallelism with source-level process
  parallelism in the first optimization implementation.
- A performance optimization must not relax the existing numerical acceptance
  tolerances.

## Target Architecture

```text
Python CLI and planner
  -> one ordered task manifest per active subject
  -> one persistent MATLAB process per active subject
       -> initialize Lead-DBS paths once
       -> cache subject and hemisphere context
       -> build or load each head model once
       -> execute FEM tasks in dependency order
       -> derive native group peaks
       -> transform required native E-fields to MNI
       -> generate all requested thresholds from one load per E-field
  -> Python validates output-leaf completeness
```

Three Python workers continue to execute different subjects concurrently.
Tasks within one subject initially remain sequential. This preserves simple DAG
ordering, limits FEM memory consumption, and maximizes reuse of process-local
state.

## Phase 0: Measurement Baseline

Add structured timing for these stages:

```text
MATLAB startup and path initialization
task decoding and validation
subject/reconstruction context loading
head-model build or load
active-contact and boundary assembly
boundary-conditioned matrix preparation
incomplete-Cholesky preconditioner construction
PCG solve
gradient calculation
electrode-removal export geometry
native-grid interpolation
NIfTI threshold generation
native-to-MNI transformation
artifact publication
```

Timing records must be emitted to MATLAB standard output in a machine-readable
form and aggregated by Python. Timing must not create a new file in an output
leaf and must not become an authoritative input.

Measure at least these execution classes:

- missing head model plus FEM solve;
- existing head model plus FEM solve;
- continuous single-source solve;
- continuous multi-source solve;
- alternating source solve;
- alternating group-peak derivation;
- threshold-only repair; and
- fully complete resume.

## Phase 1: Low-Risk Local Optimizations

### 1. Bulk Threshold Generation

Replace the per-threshold E-field load with one bulk operation:

```text
load one E-field
  -> create every requested finite-inclusive threshold mask
  -> atomically publish each requested VTA
```

The helper must preserve:

- `uint8` output datatype;
- inclusive `E >= threshold` semantics;
- exclusion of nonfinite E-field values;
- source dimensions and affine;
- threshold-specific NIfTI descriptions; and
- current atomic-publication behavior.

The solve-output and group-peak paths must call the same bulk helper. The
single-threshold helper may remain as a compatibility wrapper.

### 2. Bounding-Box Native Interpolation

Continue to allocate the complete native-anchor array and initialize it with
`NaN`. Transform the finite FEM sample-point bounding box into anchor voxel
coordinates, add a one-voxel margin, clamp it to the anchor dimensions, and
query `scatteredInterpolant` only within that box.

Do not crop the written NIfTI. Voxels outside the query box must remain `NaN`.
This preserves the common-grid contract while avoiding point-location queries
that are guaranteed to be outside FEM support.

The implementation must handle rotated or sheared anchor affines by converting
all eight physical bounding-box corners into voxel coordinates. It must not
assume an axis-aligned identity affine.

### 3. Remove Duplicate Context and Head-Model Loads

- Existing-head-model validation should inspect the MAT inventory once.
- The backend should load the required variables once per subject/hemisphere
  process context.
- The already resolved Lead-DBS `options` structure should be passed to the MNI
  transformation path.
- The output path must not call `ea_getptopts` again for each E-field.

### 4. Cache Electrode-Removal Export Geometry

Cache the geometry that is invariant across fields for one exact
subject/hemisphere/head-model/electrode-model context:

```text
tetrahedron midpoint coordinates
tissue-selection indices
electrode-oriented sample coordinates
electrode-artifact exclusion mask
```

Only E-field values vary between compatible solves. A changed head model,
hemisphere, reconstruction, or electrode model must create a different cache
entry.

### 5. Initialize MATLAB Paths Once

The persistent subject worker performs Lead-DBS path initialization once. If a
per-task compatibility runner remains available, it should use a validated,
fixed path initializer rather than repeatedly traversing the complete repository
with `genpath`.

## Phase 2: Subject-Level Persistent MATLAB Worker

Introduce one subject-manifest MATLAB entry point. Its input contains an ordered
array of the existing canonical task payloads; it must not introduce a second
task schema.

The subject runner must:

- validate each canonical task using the existing validator;
- verify that every task belongs to the manifest subject;
- execute tasks in planner-provided topological order;
- retain existing source-to-group-peak dependency semantics;
- skip complete tasks before expensive context initialization;
- preserve per-artifact atomic publication;
- return task-level `generated`, `skipped_existing`, `failed`, and
  `skipped_dependency` outcomes;
- block only the failed task's dependents;
- continue independent tasks within the subject when possible;
- let other subject workers continue after one subject failure; and
- clear all process-local caches when the subject process exits.

Python changes from invoking `run_task()` repeatedly to invoking one
`run_subject_manifest()` per active subject. A subject whose selected leaves are
already complete must not start MATLAB.

## Phase 3: Process-Local Cache Contracts

Use explicit tuple keys rather than persistent artifact hashes:

```text
subject context key:
  subject directory + reconstruction path

head-model key:
  subject + hemisphere + canonical head-model path

export-geometry key:
  head-model key + electrode model

interpolation-geometry key:
  head-model key + native-anchor dimensions + native-anchor affine
```

Caches are valid only inside one subject MATLAB process. They are never written
to disk and never replace path-existence-based resume logic.

A later interpolation cache may precompute mesh-to-anchor interpolation
geometry or barycentric mappings. It requires a dedicated equivalence test and
is not part of the first implementation pass.

## Phase 4: FEM Linear-System Reuse

The current FEM path reconstructs the boundary-conditioned sparse system and
its `ichol` preconditioner for each solve. Reuse is allowed only when all of the
following are identical:

```text
canonical head model
control mode
unipolar/bipolar return design
exact Dirichlet/current boundary-node set
matrix assembly behavior
solver tolerances and preconditioner options
```

Amplitude or RHS changes alone may reuse a compatible matrix and
preconditioner. A changed active-node set must produce a different cache entry.

Current-controlled unipolar case-return tasks are expected to offer the clearest
reuse opportunity because the outer boundary-node set is stable. Voltage tasks
may reuse a factorization only when their exact constrained-node sets match.

This phase must be implemented after persistent subject execution and must pass
separate voltage and current numerical acceptance tests.

## Optional Versioned Physical E-field Reuse

The current quasistatic FEM solver validates but does not consume
`frequency_hz` or `pulse_width_us`. A future versioned
`physical_efield_signature_v1` may therefore allow reuse when those two fields
differ but every physical FEM input is identical.

The signature must include:

```text
subject and hemisphere
reconstruction lead
electrode model
control mode
amplitude
contact identifiers
contact polarity and fractions
return design
delivery/solve semantics
gray- and white-matter conductivity
atlas/head-model context
backend and physical-signature version
configured output spaces and thresholds
```

Frequency and pulse width remain in `study_base.json`, task metadata, and output
paths. This signature affects same-subject copy reuse only; it does not change
the path-existence resume rule. It must not be enabled for a future backend that
uses frequency or pulse width without defining a new signature version.

## Explicitly Deferred Changes

The following are not part of the initial optimization:

- cropping native NIfTI dimensions or changing the native affine;
- omitting per-source MNI outputs;
- moving threshold or group-peak production to Python;
- subject-internal FEM process parallelism;
- combining subject-level and source-level process parallelism;
- transforming multiple E-fields as one 4-D ANTs input;
- reusing a FEM factorization across different boundary-node sets; and
- changing scientific thresholds, conductivities, interpolation semantics, or
  the canonical backend.

Moving derived array operations to Python may be reconsidered for a future
threshold-only repair tool. It would first require exact tests for NIfTI
metadata, affine, datatype, atomic publication, and group-peak NaN-union
semantics.

## Failure And Resume Semantics

- Complete leaves are skipped before MATLAB startup.
- Partial leaves request only their missing artifacts.
- Threshold-only repair must not rerun FEM when the E-field exists.
- Missing MNI output may reuse an existing native E-field.
- A failed source blocks only group-peak tasks that depend on that source.
- A failed task must not publish a partially written final artifact.
- Python returns a nonzero final status when any selected task fails.
- Existing successful outputs remain usable after another task fails.
- `--force` behavior remains governed by the existing Trash-based leaf reset.

## Numerical Acceptance

Every optimized path must preserve:

- exact native and MNI dimensions;
- affine maximum absolute difference no greater than `1e-12`;
- exact finite-mask agreement;
- exact thresholded VTA arrays for derived-only optimizations;
- exact alternating group-peak NaN-union semantics;
- continuous E-field maximum absolute difference no greater than `1e-3 V/m`;
- continuous E-field relative L2 error no greater than `1e-5`;
- Pearson correlation at least `0.999999`;
- VTA Dice at least `0.999`; and
- relative VTA volume difference no greater than `0.1%`.

Backend-internal repeated runs must remain deterministic under the existing
acceptance contract. Run both voltage and current acceptance paths:

```text
my_helper/vta/test/run_voltage_backend_equivalence.m
my_helper/vta/test/run_current_backend_equivalence.m
```

Bulk threshold and group-peak tests must use synthetic NIfTI fixtures covering:

- finite values below, equal to, and above every threshold;
- `NaN`, positive infinity, and negative infinity;
- one-sided finite group-peak support;
- overlapping finite support;
- dimensions and affine mismatch failures; and
- partial requested-threshold sets.

Bounding-box interpolation tests must compare the optimized implementation with
the full-grid reference on:

- identity and nonidentity affines;
- mesh support touching an image boundary;
- mesh support completely inside the image;
- out-of-image mesh corners; and
- finite-mask and value equality inside the reference convex hull.

## Performance Acceptance

Benchmark a fixed representative suite:

```text
existing-headmodel continuous single-source
existing-headmodel continuous multi-source
alternating multi-source plus group peak
one missing-headmodel build case
partial leaf with only thresholds missing
fully complete resume case
```

The optimized pipeline passes performance acceptance when:

- MATLAB startup count is no greater than the number of active subjects;
- a fully complete resume starts zero MATLAB processes;
- threshold-only repair performs zero FEM solves;
- each E-field is loaded at most once per output space for all requested
  thresholds;
- interpolation queries are restricted to the clamped mesh bounding box;
- default three-worker execution completes without out-of-memory failure or
  uncontrolled nested process parallelism;
- the warm-headmodel benchmark median wall time improves by at least 25%; and
- no measured stage regresses by more than 10% without an explicit documented
  justification.

Performance results must report wall time, process count, MATLAB startup count,
peak resident memory, and stage timings. One unusually fast task must not be
used to hide a regression in another execution class.

## Planned File Changes

Documentation first:

```text
my_helper/fiber/vta_compute_performance_optimization_plan.md
my_helper/vta/README.md
my_helper/vta/test/README.md
```

Python orchestration:

```text
my_helper/fiber/core/vta_pipeline/matlab_bridge.py
my_helper/fiber/core/vta_pipeline/service.py
my_helper/fiber/core/vta_pipeline/planner.py
my_helper/fiber/core/vta_pipeline/tests/test_matlab_bridge.py
my_helper/fiber/core/vta_pipeline/tests/test_service.py
my_helper/fiber/core/vta_pipeline/tests/test_planner.py
```

MATLAB execution and output:

```text
my_helper/fiber/core/stimulation/model/mh_vta_run_canonical_subject_manifest.m
my_helper/fiber/core/stimulation/model/mh_vta_export_common_grid.m
my_helper/fiber/core/stimulation/model/mh_vta_export_canonical_outputs.m
my_helper/fiber/core/stimulation/model/mh_vta_derive_canonical_group_peak.m
my_helper/fiber/core/stimulation/model/mh_vta_threshold_efield.m
my_helper/fiber/core/stimulation/model/backends/mh_vta_backend_simbio_onesolve_canonical.m
my_helper/fiber/core/stimulation/model/fem/mh_vta_fem_apply_dbs.m
my_helper/fiber/core/stimulation/model/mh_vta_prepare_canonical_headmodel.m
```

MATLAB tests:

```text
my_helper/fiber/tests/test_vta_common_grid_export.m
my_helper/fiber/tests/test_vta_canonical_outputs.m
my_helper/fiber/tests/test_vta_canonical_subject_manifest.m
my_helper/fiber/tests/test_vta_fem_factorization_cache.m
my_helper/vta/test/test_run_voltage_backend_equivalence.m
my_helper/vta/test/test_run_current_backend_equivalence.m
```

Exact test filenames may be reduced by extending an existing focused test file,
but responsibilities must remain separated between orchestration, output
generation, and FEM numerical behavior.

## Implementation Sequence

```text
1. Record the baseline and add stage-level timing.
2. Implement bulk threshold generation with failing tests first.
3. Implement bounding-box interpolation with full-grid equivalence tests.
4. Remove duplicate context and head-model loads.
5. Add the subject task manifest contract and Python bridge tests.
6. Add the persistent MATLAB subject runner.
7. Add process-local context and export-geometry caches.
8. Run voltage/current numerical acceptance and performance benchmarks.
9. Add guarded FEM matrix/preconditioner reuse.
10. Repeat numerical and performance acceptance.
11. Evaluate, but do not automatically enable, versioned physical E-field reuse.
```

Each implementation step must begin with documentation alignment, use a failing
test before production-code changes, and end in an independently reviewable
commit. A failed numerical gate blocks progression to the next optimization
phase.

## Completion Criteria

The optimization project is complete only when:

- one MATLAB process handles each active subject DAG;
- all configured canonical artifacts remain available;
- all voltage/current numerical gates pass;
- all resume and dependency-failure tests pass;
- no subject, phase, program, frequency group, or electrode model is hard-coded;
- the representative warm-headmodel benchmark improves by at least 25%;
- default three-worker execution remains memory-safe; and
- documentation describes the measured implementation rather than planned
  behavior.
