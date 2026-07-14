# VTA Computation Performance Optimization Plan

## Document Status

```text
design_documented
phase_0_telemetry_and_baseline_harness_implemented
phase_1_bulk_threshold_generation_implemented
phase_1_bounded_native_interpolation_implemented
slice_4_context_and_headmodel_load_consolidation_implemented
slice_5_subject_manifest_and_state_machine_implemented
slice_6_persistent_subject_runner_implemented
slice_7_process_local_runtime_caches_implemented
representative_paired_performance_harness_implemented
solver_free_verification_complete
real_fem_numerical_gate_refreshed
real_fem_performance_baseline_complete
representative_pre_reuse_numerical_gate_complete
fem_system_reuse_implemented
current_factorization_real_fem_gate_complete
post_reuse_representative_gate_complete
three_worker_memory_gate_complete
public_cli_default_workers_3_authorized_not_implemented
documentation_updated_for_public_cli_default_workers_3
current_outputs_unchanged
```

As of 2026-07-14, the first implementation slice is complete. The repository
contains the framed telemetry parser, synchronized process-tree RSS monitor,
streaming MATLAB bridge, canonical MATLAB event emitter, stage timing, and the
frozen performance benchmark harness. The Python benchmark/pipeline suite and
the solver-free MATLAB fiber suite pass. Live benchmark validation resolves 9
cases and 13 semantic tasks from the current study configuration.

The representative real-FEM performance baseline and the corrected
three-worker memory-safety gate have been executed and passed. The public CLI
default remains one worker only until the authorized CLI/test update is
committed. Bulk threshold generation, bounded native
interpolation,
and context/headmodel load consolidation are implemented and solver-free
verified. The deterministic subject manifest and path-based artifact state
resolver are also implemented and solver-free verified. Production execution
now uses one persistent MATLAB process per active subject while preserving the
per-task compatibility runner. Process-local transform/subject context,
validated head-model, native-anchor, and export-geometry caches are implemented
and solver-free verified. The complete MATLAB fiber suite passes 130 tests, the
Python VTA pipeline/benchmark suite passes 193 tests, and Code Analyzer reports
zero findings. Guarded process-local FEM system/preconditioner reuse is
implemented. Its bounded real-current cache-hit gate, fresh post-reuse
representative gate, and corrected three-worker memory gate have passed.

The post-cache numerical gate has since been refreshed. Historical bilateral
voltage outputs passed zero-FEM re-comparison, and one fixed right-sided current
canonical candidate FEM passed against the retained standard SimBio reference:
maximum native difference `0.04443359375 V/m`, relative L2
`2.2273793323536e-6`, correlation `0.999999999996588`, and Dice `1.0` at all
three thresholds. The MNI contract and production-tree safety gate passed. The
retained standard-SimBio comparison remains the backend-equivalence gate;
optimization-regression comparisons use the independent `1e-3 V/m` maximum
error contract.

The first representative paired attempt completed two compatibility warm-up
FEM solves, then stopped at export because `native_anchor_load` was not in the
allowed timing-stage registry. This is an instrumentation registry defect, not
a numerical FEM failure. The failed root is retained. After the registry repair,
the linked recovery credits only those two verified warm-up solves and limits
the new root to 14 FEM, preserving the aggregate 16-FEM acceptance bound.

The linked recovery completed successfully at:

```text
/Volumes/VAL/STNSNr/validation/vta_performance_benchmark_20260714T113033575679Z
```

The replacement root completed `14/14` new FEM solves; together with the two
credited solves, the linked aggregate was exactly `16/16`. Across three measured
pairs, compatibility per-task median wall time was `73.42287808400579 s` and
persistent-subject median wall time was `44.65844920813106 s`, giving a ratio of
`0.6082361570876547` and a `39.18%` reduction. All three native/MNI comparisons
for both source fields and the alternating group peak were exactly equal:
maximum E-field difference `0 V/m`, relative L2 `0`, correlation `1`, affine
difference `0`, and Dice `1` at `180/200/220 V/m`. The largest observed
single-subject process-tree peak RSS was `9,166,995,456` bytes. This is a
single-subject representative baseline and does not satisfy the three-worker
memory gate.

The bounded real-current factorization gate completed successfully at:

```text
/Volumes/VAL/STNSNr/validation/vta_current_factorization_cache_20260714_070153_462
```

It executed exactly two canonical current FEM solves in one copied-subject
runtime. Matrix preparation and preconditioner status were `miss` then `hit`,
and the runtime retained exactly one factorization entry. Native and MNI
E-fields were voxel-identical (`0 V/m` maximum difference, relative L2 `0`,
correlation `1`); all 180/200/220 V/m VTA comparisons had Dice `1` and zero
volume difference. The two output leaves were independent. This proves a real
cache hit without expanding the acceptance to the historical multi-case FEM
suite.

The fresh post-reuse representative gate completed successfully at:

```text
/Volumes/VAL/STNSNr/validation/vta_performance_benchmark_20260714T140401688999Z
```

It completed the full bounded `16/16` FEM contract. Compatibility per-task
median wall time was `77.99708383297548 s`; persistent-subject median wall time
was `44.61829545791261 s`, for a ratio of `0.5720508160722921` and a `42.79%`
reduction. Every source/group-peak native and MNI comparison across all three
measured pairs was exact: maximum E-field difference `0 V/m`, relative L2 `0`,
correlation `1`, affine difference `0`, Dice `1`, and relative VTA volume
difference `0` at 180/200/220 V/m. Peak single-subject process-tree RSS was
`9,205,678,080` bytes.

The representative alternating voltage sources use different constrained-node
sets, so their factorization cache status remains miss/miss by design. Relative
to the pre-reuse gate, median `fem_matrix_preparation` time increased from
`0.054461 s` to `0.064422 s` in compatibility mode and from `0.049960 s` to
`0.059627 s` in persistent mode. These `18.29%` and `19.35%` relative changes
are about `10 ms` absolute and are the expected bounded miss-path cost of exact
cache-key validation, lookup, and one-entry publication. Persistent
`electrode_removal_geometry` changed from `0.014517 s` to `0.016216 s`
(`11.70%`, about `1.7 ms`); that stage was not changed by the factorization
slice and the absolute variation is timing noise. Persistent total median wall
time improved slightly from `44.65844920813106 s` to `44.61829545791261 s`.
No scientific or output regression was observed.

This document defines a performance optimization plan for the canonical
VTA/E-field pipeline. It does not authorize a scientific model change, an
artifact-contract change, or a model rerun.

The executable architecture and resolved audit decisions are defined in:

```text
docs/superpowers/specs/2026-07-13-vta-performance-optimization-design.md
```

The slice 6 persistent-subject-runner implementation contract is:

```text
docs/superpowers/plans/2026-07-14-vta-persistent-subject-runner.md
```

The slice 7 process-local runtime-cache implementation contract is:

```text
docs/superpowers/plans/2026-07-14-vta-process-local-runtime-caches.md
```

The representative paired real-FEM gate contract is:

```text
docs/superpowers/plans/2026-07-14-vta-representative-paired-performance-gate.md
```

The three-worker memory gate contract is:

```text
docs/superpowers/plans/2026-07-14-vta-three-worker-memory-gate.md
```

The first three-worker attempt completed all five FEM solves and seven tasks
with aggregate peak RSS `19,592,151,040` bytes (`14.255%` of physical memory)
and maximum subject RSS `10,228,760,576` bytes (`7.442%`). It remains a failed
instrumentation attempt because `matlab_helper` children were overclassified as
nested MATLAB interpreters. At that point, the corrected gate still had to run
before changing the public default.

The corrected three-worker gate passed at:

```text
/Volumes/VAL/STNSNr/validation/vta_three_worker_memory_gate_20260714T143046769646Z
```

It completed `5/5` FEM solves and generated all `7/7` tasks while sampling
three simultaneous MATLAB subject roots. Aggregate peak RSS was
`18,002,034,688` bytes (`13.098%` of physical memory); maximum subject-tree RSS
was `9,692,545,024` bytes (`7.052%`). The 381 synchronized 100 ms samples showed
no swap increase, nested MATLAB interpreter, OOM/signal evidence, failed task,
or missing artifact. All memory and execution gates passed. This authorizes the
separate public CLI default update from one to three workers.

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

## Pre-Optimization Baseline

Before the persistent subject runner, the canonical execution path was:

```text
Python CLI and planner
  -> subject-level ThreadPoolExecutor
  -> one MATLAB -batch process per unresolved task
  -> one canonical FEM or derived task
  -> native output
  -> MNI transformation
  -> thresholded VTA outputs
```

Recorded baseline characteristics were:

- `matlab_bridge.py` started one MATLAB process for each unresolved task.
- Every MATLAB invocation evaluates `addpath(genpath(repo_root))`.
- `service.py` runs subjects concurrently but executes each subject DAG
  sequentially.
- The current CLI default is one subject worker. The optimized CLI contract
  changes this default to three only after the required memory-safety gate.
- The current study configuration produces 208 planned task rows.
- Existing same-subject reuse reduces these rows to approximately 105 FEM
  solves and 8 group-peak derivations on a clean run.
- The baseline clean-run architecture could therefore start approximately 113
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
- Change the final CLI default to three subject workers. Three-subject
  memory-safety acceptance is mandatory; failure blocks release rather than
  silently restoring a one-worker default.
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

Three Python workers execute different subjects concurrently by default.
Tasks within one subject initially remain sequential. This preserves simple DAG
ordering, limits FEM memory consumption, and maximizes reuse of process-local
state.

Before each task, the MATLAB subject runner rechecks artifact existence,
attempts ordered same-subject copy reuse supplied by Python, recomputes
`missing_artifacts`, and only then selects skip, solve, or derived execution.
This prevents stale manifest state when an earlier task creates a later donor.

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
alternating group-peak composition
NIfTI threshold generation
native-to-MNI transformation
artifact publication
```

Timing records must be emitted to MATLAB standard output in a machine-readable
form and aggregated by Python. Timing must not create a new file in an output
leaf and must not become an authoritative input.

Every machine-readable line uses the exact prefix `MH_VTA_EVENT ` followed by
one compact `vta_event_v1` JSON object. Supported records are `subject_ready`,
`task_started`, `stage_timing`, `task_outcome`, and `subject_summary`.
Unprefixed output remains diagnostic text. Python samples all live MATLAB
process trees on one synchronized 100 ms clock, counting each PID once per
tick, and treats a malformed prefixed line as a protocol failure.

Sequences begin at 1 and are contiguous. A successful process emits exactly
one ready event, one started/outcome pair per selected task, and one summary
whose counts match the outcomes. Exit zero with a missing or inconsistent
protocol event is still a process failure.

The legal order is subject-scope initialization timings, `subject_ready`, then
one ordered `task_started` / task-scope timings / `task_outcome` block per
task, followed by `subject_summary`. No event follows the summary.
Each stage event declares scope, stage status, duration, and cache status when
applicable.

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
coordinates, add a one-voxel margin, intersect it with the anchor dimensions,
and query `scatteredInterpolant` only within a nonempty intersection.

Do not crop the written NIfTI. Voxels outside the query box must remain `NaN`.
This preserves the common-grid contract while avoiding point-location queries
that are guaranteed to be outside FEM support.

The implementation accepts FEM sample points in millimeters and handles
rotated, sheared, reflected, or negative-determinant anchor affines by
converting all eight physical bounding-box corners with one-based
`ea_mm2vox(points_mm, anchor.mat)` semantics. It intersects the integer query
range with `[1, dimensions]`; if any axis is empty, it returns the full-size
all-`NaN` grid rather than clamping onto a boundary voxel.

### 3. Remove Duplicate Context and Head-Model Loads

- Centralize canonical MAT loading and coordinate-unit validation in one helper.
- Preparation returns the validated head-model structure for reused and newly
  built paths; the backend consumes that exact structure without a second load.
- The load and mandatory unit guard remain one indivisible operation before
  active-index calculation.
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

The envelope is `vta_subject_manifest_v1`. Its `tasks` field is an array of
objects containing one existing canonical task payload, that task's
`output_leaves`, and ordered `reuse_candidate_ids`. Its separate
`reuse_donors` array contains selected and unselected same-subject donor
paths. Task IDs are never JSON object field names.

Python remains authoritative for physical equivalence; MATLAB does not
recreate the equivalence key. Donor candidates are read-only path probes, not
dependency edges. A missing or failed donor never blocks a recipient: MATLAB
tries the next donor and computes the recipient when none exists. Unselected
donors are not executable tasks.

Selected writable leaves must be distinct and may not overlap by
ancestor/descendant path. A selected donor is writable only by its owning task
and read-only to recipients; an unselected donor is globally read-only. Donor
copies map only the same output space and same canonical relative artifact
filename; partial donor leaves are probed artifact-by-artifact.

The subject runner must:

- validate each canonical task with a static definition validator that does
  not require `missing_artifacts`;
- validate runtime context separately after a nonempty missing-artifact set is
  resolved;
- verify that every task belongs to the manifest subject;
- execute tasks in planner-provided topological order;
- recheck artifact existence and recompute `missing_artifacts` immediately
  before every task;
- perform eligible same-subject artifact copies atomically inside the subject
  process;
- resolve source-to-group-peak requirements per missing artifact rather than
  blocking the whole task after any source outcome failure;
- skip complete tasks before expensive context initialization;
- preserve per-artifact atomic publication;
- return task-level `generated`, `copied`, `skipped_existing`,
  `recovered_complete`, `failed`, and `skipped_dependency` outcomes;
- mark a downstream task `skipped_dependency` only when its currently
  required upstream artifact remains absent;
- continue independent tasks within the subject when possible;
- let other subject workers continue after one subject failure; and
- clear all process-local caches when the subject process exits.

Python changes from invoking `run_task()` repeatedly to invoking one
`run_subject_manifest()` per active subject. A subject whose selected leaves are
already complete must not start MATLAB.

When every selected task is complete, Python synthesizes one
`skipped_existing` outcome per task without starting MATLAB.

For group peak, source native E-fields are required only when the native
group-peak E-field is missing. Native thresholds require the native group-peak
E-field; MNI E-field requires the native group-peak E-field; MNI thresholds
require the MNI E-field. Existing downstream E-fields therefore remain
repairable after an unrelated source failure.

## Phase 3: Process-Local Cache Contracts

Use explicit tuple keys rather than persistent artifact hashes:

```text
subject context key:
  subject directory + reconstruction path

head-model key:
  subject + hemisphere + canonical head-model path + atlas set
  + gray/white conductivity + canonical meshing/model versions
  + electrode model + reconstruction lead + trajectory coordinates
  + patient GM mask path/size/mtime

export-geometry key:
  head-model key + reconstruction path + reconstruction lead
  + electrode model + trajectory coordinates + lead diameter

interpolation-geometry key:
  export-geometry key + native-anchor path + dimensions + affine
  + finite-sample-support signature
```

Caches are valid only inside one subject MATLAB process. They are never written
to disk and never replace path-existence-based resume logic.

A later interpolation cache may precompute mesh-to-anchor interpolation
geometry or barycentric mappings. It requires a dedicated equivalence test and
is not part of the first implementation pass.

Tasks sharing a head-model path must declare the same atlas, conductivity,
meshing-version, headmodel-version, electrode model, reconstruction lead,
trajectory, and resolved patient GM geometry or manifest validation fails.
Internal constants are `canonical_mask_surface_v1` and
`simbio_onesolve_canonical_v1`; they are not public YAML fields.

## Phase 4: FEM Linear-System Reuse

The current FEM path reconstructs the boundary-conditioned sparse system and
its `ichol` preconditioner for each solve. Reuse is allowed only when all of the
following are identical:

```text
canonical head model
control mode
unipolar/bipolar return design
exact constrained Dirichlet/return boundary-node set
matrix assembly behavior
solver tolerances and preconditioner options
```

The cache retains the original symmetric stiffness or Dirichlet-coupling terms
needed to rebuild the RHS, the conditioned matrix, and the `ichol`
preconditioner. Current injection support and values remain per-solve RHS
inputs, not matrix-key fields. Amplitude or RHS changes alone may reuse a
compatible matrix and preconditioner. A changed constrained-node set must
produce a different cache entry.

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
- A failed source blocks group-peak work only when a currently missing
  group-peak artifact requires that source's missing native E-field.
- Reuse donors never block recipients and never become hard dependencies.
- A failed task must not publish a partially written final artifact.
- Before synthesizing outcomes after process failure, Python terminates and
  reaps the MATLAB process tree, stops RSS sampling, then performs one final
  artifact reconciliation and preserves completed work.
- Manifest-write, force-reset, process-launch, parser, and fatal MATLAB
  failures increment `subject_process_failed`; other subjects continue.
- Parsed successful outcomes are retained only after all expected files are
  revalidated. A complete task with no final outcome after protocol failure is
  `recovered_complete`, which does not claim whether execution, copy, or prior
  state produced it.
- Python returns a nonzero final status when any selected task fails, any task
  is `skipped_dependency`, or any subject process fails.
- Existing successful outputs remain usable after another task fails.
- Path-existence resume is always enabled; `--resume` is a compatibility alias
  for ordinary run behavior.
- `--force` preflights Trash moves and restores prior moves on a later reset
  failure when possible; incomplete rollback is reported explicitly.

## Numerical Acceptance

Every optimized path must preserve:

- exact native and MNI dimensions;
- affine maximum absolute difference no greater than `1e-12`;
- exact finite-mask agreement;
- exact thresholded VTA arrays for derived-only optimizations;
- exact alternating group-peak NaN-union semantics;
- old-canonical versus optimized-canonical FEM E-fields of every continuous,
  alternating-source, voltage, and current class have exact dimensions and
  finite masks and maximum absolute difference no greater than `1e-3 V/m`;
- every such FEM E-field has relative L2 error no greater than `1e-5`;
- Pearson correlation at least `0.999999`;
- VTA Dice at least `0.999`; and
- relative VTA volume difference no greater than `0.1%`.

Backend-internal repeated runs must remain deterministic under the existing
acceptance contract. Run both voltage and current acceptance paths:

```text
my_helper/vta/test/run_voltage_backend_equivalence.m
my_helper/vta/test/run_current_backend_equivalence.m
```

Standard SimBio versus canonical backend equivalence retains its separate
maximum absolute E-field tolerance of `0.05 V/m`. Derived-only threshold,
group-peak, and interpolation operations require exact array and finite-mask
agreement.

Old-canonical versus optimized-canonical acceptance uses a dedicated
`optimization_regression` comparator mode with the `1e-3 V/m` maximum-error
gate. It must not reuse or silently change the standard-SimBio comparator's
`0.05 V/m` contract.

A negative comparator test uses a difference strictly between `1e-3` and
`0.05 V/m`: standard backend mode passes and optimization mode fails.

Bulk threshold and group-peak tests must use synthetic NIfTI fixtures covering:

- finite values below, equal to, and above every threshold;
- `NaN`, positive infinity, and negative infinity;
- one-sided finite group-peak support;
- overlapping finite support;
- dimensions and affine mismatch failures; and
- partial requested-threshold sets.

Bounding-box interpolation tests must compare the optimized implementation with
the full-grid reference on:

- identity, translated, rotated, sheared, reflected, and
  negative-determinant affines;
- mesh support touching an image boundary;
- mesh support completely inside the image;
- out-of-image mesh corners; and
- finite-mask and value equality inside the reference convex hull.

All bounding conversion uses Lead-DBS one-based
`ea_mm2vox(points, anchor.mat)` semantics.

The centralized head-model loader replaces the current source-string assertion
that expects a literal backend `load(...)`. Runtime tests must prove that
invalid reused and newly built models fail with the established error IDs
before `ea_getactiveidx` and do not overwrite existing files.

## Performance Acceptance

The first implementation slice creates the suite declaration at
`my_helper/vta/test/fixtures/vta_performance_benchmark_v1.json`, schema
`vta_performance_benchmark_v1`:

```text
SNr003 T1/program 1/lead-R/group-1 continuous_joint source-1, cold and warm
SNr003 T2/program 2/lead-L/group-1 alternating source-1/source-2 plus group peak
SNr003 T1/program 1/lead-R/group-1 native/MNI threshold-only repair with both E-fields retained
SNr003 T1/program 1/lead-R/group-1 fully complete resume
SNr006 T2/program 2/lead-L/group-1 alternating source-1/source-2 plus group peak
SNr011 T2/program 2/lead-L/group-1 continuous_joint source-1
deterministic synthetic continuous multi-source fixture
SNr003 right-sided single-cathode/case-return current fixture, seed 20260712
```

The current cohort has no real continuous multi-source group, so that execution
class is a deterministic synthetic FEM fixture rather than a hard-coded study
row. The manifest freezes all canonical selectors, task kinds, source IDs,
synthetic/current payloads, spaces (`native`, `MNI152NLin2009bAsym`), thresholds
(180/200/220 V/m), initial artifact inventory, and expected counts.

The nine-case declaration remains the solver-free contract and broad execution
inventory. Real-FEM pre-reuse timing uses only the representative
`snr003_t2_p2_l_alternating` warm-headmodel case. The compatibility per-task
and persistent subject paths receive separate warm-ups followed by three
measured pairs in fixed order: baseline/candidate, candidate/baseline,
baseline/candidate. This performs at most 16 FEM solves. Every member restores
the same frozen case snapshot into a disjoint path. Expected process, solve,
derived, copy, and skip counts are asserted. Temporary validation-root
checksums enforce exact derived and same-backend repeatability without adding
production provenance.

The representative median is a pre-reuse performance gate, not the median of
the complete nine-case suite. The separate three-worker memory gate has passed
and authorizes changing the public CLI default after its documentation and
parser/service tests are updated.

The fixture stores stable semantic selector IDs. Canonical task IDs include
absolute copied paths, so the harness resolves and records exact task IDs after
each frozen snapshot is materialized rather than embedding production-root
task IDs in the fixture.

The representative path passes its performance target when:

- MATLAB startup count is no greater than the number of active subjects;
- a fully complete resume starts zero MATLAB processes;
- threshold-only repair performs zero FEM solves;
- each E-field is loaded at most once per output space for all requested
  thresholds;
- interpolation queries are restricted to the nonempty intersected mesh
  bounding box;
- default three-worker execution completes without out-of-memory failure or
  uncontrolled nested process parallelism;
- aggregate three-worker process-tree peak RSS is no greater than 75% of
  physical memory and no single subject process tree exceeds 50%;
- the candidate representative-case median wall time is no greater than 75%
  of the baseline representative-case median; and
- no measured stage regresses by more than 10% without an explicit documented
  justification.

Performance results must report wall time, process count, MATLAB startup count,
peak resident memory, and stage timings. One unusually fast task must not be
used to hide a regression in another execution class.

RSS uses one synchronized 100 ms sampler: at each tick it unions PIDs across
subject process trees, sums each live PID once, and takes the maximum over
time. Physical memory comes from `psutil.virtual_memory().total`; minimum
available memory, swap start/end/peak, signals, and OOM evidence are recorded.

Task execution class is `(headmodel_state, task_kind, control_mode,
source_count_class, resolved_action)`; subject-scope stages are separate. Stage
durations are summed by class/stage for each repetition, then compared by
baseline/candidate medians. Cache hits emit lookup duration with
`cache_status=hit`; action-excluded stages are `not_applicable`; missing
expected telemetry is a protocol failure. Spawn-to-`subject_ready` is a
separate `startup_total` metric and is not added to internal initialization
stages.

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
my_helper/vta/test/fixtures/vta_performance_benchmark_v1.json
my_helper/vta/test/mh_compare_vta_optimization_outputs.m
my_helper/vta/test/test_compare_vta_optimization_outputs.m
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
- CLI default `--workers 3` execution remains memory-safe; and
- documentation describes the measured implementation rather than planned
  behavior.
