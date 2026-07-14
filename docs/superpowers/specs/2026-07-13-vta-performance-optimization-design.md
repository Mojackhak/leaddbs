# VTA Performance Optimization Design

## Status

```text
design_approved_for_execution
slice_1_telemetry_and_benchmark_harness_implemented
slice_2_bulk_threshold_generation_implemented
slice_3_bounded_native_interpolation_implemented
slice_4_context_headmodel_consolidation_implemented
slice_5_subject_manifest_state_machine_implemented
solver_free_verification_complete
real_fem_baseline_not_run
slices_6_to_9_not_started
current_outputs_unchanged
```

The implemented first slice includes framed event parsing, synchronized
process-tree RSS sampling, process-group-safe streaming MATLAB execution,
canonical task/stage event emission, and the frozen benchmark fixture and
harness. Solver-free Python and MATLAB acceptance suites pass, and live
benchmark validation resolves 9 cases and 13 semantic tasks.

Slice 2 adds one-load bulk threshold generation to both solve/export and
alternating group-peak paths while preserving per-artifact atomic publication.
Exact synthetic coverage includes threshold boundaries, nonfinite values,
metadata, resume, failure, compatibility, load count, and event ordering.

Slice 3 bounds native interpolation queries using all eight transformed
physical sample-box corners while retaining the full anchor-sized output.
Exact full-grid reference tests cover general affine geometry and internal,
boundary, partially external, and fully external support.

Slice 4 centralizes canonical headmodel load plus unit validation, returns the
validated structure from preparation, and reuses solve reconstruction/options
context through export. Repair-only paths continue to resolve only the context
required by their missing artifacts.

Slice 5 adds deterministic Python `vta_subject_manifest_v1` construction,
independent MATLAB envelope validation, static/runtime task-validator
separation, canonical path and headmodel-context guards, ordered same-subject
artifact reuse, and artifact-specific dependency resolution. It does not yet
replace the production per-task MATLAB bridge.

This status does not claim a measured runtime improvement. The real FEM
baseline, candidate comparison, and three-worker memory gate have not run.
The production CLI default remains one worker until that gate passes. Slices 6
through 9 remain implementation work.

## Purpose

Reduce canonical VTA/E-field clean-run and incremental-run wall time while
preserving the current scientific model, canonical artifacts, delivery-mode
semantics, path-based resume behavior, and numerical acceptance contracts.

This design resolves contradictions discovered during the current-state audit
of `my_helper/fiber/vta_compute_performance_optimization_plan.md`. The roadmap
remains the project-level goal; this specification defines the executable
architecture and state contracts.

## Non-Negotiable Contracts

- `simbio_onesolve` remains the only canonical production backend.
- Continuous groups are solved jointly; alternating sources are solved
  independently and retain source-level artifacts.
- Alternating group peak remains native source maximum, native thresholds,
  native-to-MNI transformation, then MNI thresholds.
- Native and MNI dimensions, affine, datatype, and artifact names do not change.
- File existence remains the persistent resume criterion.
- No subject, phase, program, timepoint, frequency group, electrode model, or
  study-specific HF/ULF label is hard-coded.
- No leaf provenance, artifact hash, or independent resolved manifest is added.
- CLI default concurrency changes to `--workers 3` and must pass the
  three-subject peak-memory acceptance gate.
- Documentation and RED/GREEN tests precede every production-code slice.

## Numerical Contracts

Two comparisons serve different purposes and must not share one tolerance:

1. Standard SimBio versus canonical backend equivalence retains the existing
   maximum absolute E-field tolerance of `0.05 V/m`.
2. Old-canonical versus optimized-canonical regression applies to every FEM
   E-field class, including continuous, alternating-source, voltage, and
   current. It requires exact dimensions and finite mask, maximum absolute
   E-field difference `<= 1e-3 V/m`, relative L2 error `<= 1e-5`, and Pearson
   correlation `>= 0.999999`.

Derived-only array operations require exact equality, including finite masks,
thresholded VTA arrays, and alternating group-peak NaN-union behavior.

All FEM comparisons retain affine tolerance `<= 1e-12`, VTA Dice `>= 0.999`,
and relative VTA volume difference `<= 0.1%`. Derived-only comparisons remain
exact.

## Approaches Considered

### A. Local Optimizations Only

Bulk thresholding and bounded interpolation are low risk, but process startup
would still occur once per unresolved task. This cannot satisfy the final
one-process-per-active-subject criterion and is insufficient as the complete
architecture.

### B. Persistent MATLAB Engine Pool

Python could retain current per-task control while keeping one MATLAB Engine
session per subject. This simplifies dynamic copy/retry decisions, but adds a
MATLAB Engine Python dependency, complicates environment deployment, and
creates a second interactive runtime path that differs from existing batch
acceptance.

### C. One Batch Subject Manifest Per Active Subject

This is the selected architecture. Python launches one `matlab -batch` process
per active subject. MATLAB initializes paths once, executes an ordered subject
manifest, re-resolves file state before every task, performs same-subject copy
reuse, retains process-local caches, and emits framed events to stdout. It
preserves the batch execution boundary without an Engine dependency.

## Target Data Flow

```text
Python planner
  -> selected SubjectPlan
  -> force-to-Trash when requested
  -> skip subjects whose selected leaves are already complete
  -> write one vta_subject_manifest_v1 JSON per active subject
  -> start one MATLAB batch process per active subject
       -> initialize Lead-DBS paths once
       -> validate manifest and task definitions
       -> for each task in topological order
            -> recheck artifact existence
            -> copy eligible same-subject donor artifacts atomically
            -> recompute missing_artifacts
            -> skip, solve, or derive
            -> emit timing and outcome events
       -> emit subject summary
  -> Python aggregates outcomes and peak process-tree RSS
  -> CLI emits one final JSON summary and returns nonzero if any task or
     subject process failed
```

Python continues to run subjects through a `ThreadPoolExecutor`. The default is
three subject workers. Tasks within one subject remain sequential.

## Subject Manifest Contract

The manifest is an execution envelope, not a second canonical task schema.
Task IDs are values inside arrays; they are never JSON object field names,
because a SHA-256 task ID may begin with a digit and MATLAB `jsondecode` may
rename such fields.

```json
{
  "schema_version": "vta_subject_manifest_v1",
  "run_id": "20260713T220000Z",
  "subject_id": "SNr003",
  "tasks": [
    {
      "task": {
        "task_id": "...",
        "kind": "continuous_joint",
        "...": "remaining existing canonical VtaTask fields"
      },
      "output_leaves": {
        "native": "...",
        "MNI152NLin2009bAsym": "..."
      },
      "reuse_candidate_ids": ["donor-1", "donor-2"]
    }
  ],
  "reuse_donors": [
    {
      "donor_id": "donor-1",
      "output_leaves": {
        "native": "...",
        "MNI152NLin2009bAsym": "..."
      }
    }
  ]
}
```

Python remains authoritative for physical equivalence. MATLAB does not recreate
`equivalent_task_key`; it only probes the ordered read-only donor candidates
supplied by Python. The donor catalog includes selected tasks and unselected
same-subject tasks that are physically equivalent. Unselected donors are never
made executable merely because they appear in the catalog.

Reuse candidates are not dependency edges. MATLAB never waits for a donor and
never propagates donor failure to a recipient. For each missing artifact it
probes candidate paths in manifest order, atomically copies the first existing
artifact, and computes the recipient if no donor artifact exists. All selected
tasks also appear as donor catalog entries. Because subject tasks execute in
manifest order, later equivalent tasks can reuse artifacts generated by an
earlier task; an earlier task simply ignores a not-yet-existing later artifact.
This deterministic probe algorithm cannot form a scheduling cycle.

The task array is planner-provided topological order. The manifest validator
rejects duplicate task IDs, unknown dependencies, forward dependencies,
cross-subject tasks or donors, duplicate donor IDs, unknown reuse references,
and output leaves that do not match the canonical path contract. Python
verifies that every donor listed for a task has the same resolved physical
equivalence key before serialization.

Selected writable leaves must be pairwise distinct and may not be ancestor or
descendant directories of another selected writable leaf. A selected donor
leaf is writable only by its owning task and read-only when a recipient probes
it. An unselected donor leaf is globally read-only. A donor artifact maps only
to the same output space and same canonical relative filename as the recipient
(`efield.nii.gz` or one configured threshold filename). Partial donor leaves
are valid; each expected artifact is probed independently.

Static task validation is separated from runtime artifact validation:

- a static validator checks every canonical task definition when the manifest
  is loaded without requiring `missing_artifacts`;
- `missing_artifacts` is computed immediately before execution;
- a separate runtime-context validator is called only after a nonempty missing
  set has been attached; and
- complete or fully copied tasks never enter FEM/derived dispatch.

## Per-Task State Machine

```text
all expected artifacts already exist
  -> skipped_existing

otherwise
  -> atomically copy each missing artifact from ordered eligible donors
  -> recompute missing artifacts

no artifacts remain missing and at least one was copied
  -> copied

artifacts remain missing
  -> execute only required solve/transform/threshold actions
  -> validate all expected leaf artifacts
  -> generated

task exception
  -> failed
  -> block only downstream actions that still require a missing artifact
     produced by this task
  -> continue independent tasks
```

If copying satisfies only part of a task, the final status is `generated` and
the outcome records `copied_artifact_count`. `--force` retains the current
behavior: Python moves selected leaves to Trash before process launch, and
unselected same-subject donors may repopulate equivalent selected leaves.

Dependencies are resolved per required artifact, not per task outcome. For an
alternating group-peak task:

```text
missing native group-peak E-field
  -> requires every configured source native E-field

missing native group-peak threshold
  -> requires native group-peak E-field only

missing MNI group-peak E-field
  -> requires native group-peak E-field only

missing MNI group-peak threshold
  -> requires MNI group-peak E-field only
```

Therefore an existing group-peak E-field can support threshold or MNI repair
even when a source task failed in the same process. A task is
`skipped_dependency` only when a required upstream artifact is absent after
all eligible upstream execution and donor probes have finished.

Path-existence resume is always active. `--resume` remains a compatibility
alias for an ordinary run and does not change behavior; it remains mutually
exclusive with `--force`.

Force reset is transactional per subject. Python first preflights every
selected leaf and Trash destination, then records each successful move. If a
later move fails, it restores earlier moves to their original paths when
possible. An incomplete rollback yields `subject_process_failed = 1`, reports
the affected paths, does not start MATLAB for that subject, and allows other
subjects to continue.

If every selected task is complete before process launch, Python starts no
MATLAB process and synthesizes one `skipped_existing` outcome per selected
task so the summary still accounts for the complete selection.

## Framed Event Protocol

MATLAB writes machine-readable events as one compact JSON object per line with
the exact prefix:

```text
MH_VTA_EVENT {json}
```

All unprefixed MATLAB/Lead-DBS output remains diagnostic text and is forwarded
without being interpreted as protocol data. A malformed prefixed line is a
protocol failure.

Every event contains:

```text
schema_version = vta_event_v1
event_type
sequence
run_id
subject_id
```

Supported event types are:

- `subject_ready`: emitted after path initialization and manifest validation;
- `task_started`: includes the next `task_id` before runtime resolution;
- `stage_timing`: includes scope, optional `task_id`, `stage`,
  `stage_status`, optional `cache_status`, and `duration_seconds`;
- `task_outcome`: includes `task_id`, `status`, copied/generated artifact
  counts, and optional error identifier/message;
- `subject_summary`: includes all outcome counts and process success state.

The legal event grammar is:

```text
zero or more subject-scope initialization stage_timing events
subject_ready
for each task in manifest order:
  task_started
  zero or more task-scope stage_timing events
  task_outcome
subject_summary
```

No event may follow `subject_summary`. A task-scoped timing event must refer to
the currently started task.

Stage names are fixed:

```text
path_initialization
manifest_decode_validation
task_runtime_resolution
subject_reconstruction_context
headmodel_build_or_load
active_contact_boundary
fem_matrix_preparation
fem_preconditioner
fem_pcg_solve
gradient_calculation
electrode_removal_geometry
native_grid_interpolation
group_peak_composition
threshold_generation
native_to_mni_transform
artifact_publication
```

Python uses `subprocess.Popen`, combines stderr into the diagnostic stream,
parses only prefixed lines, and samples all live MATLAB process trees through
`psutil` on one synchronized 100 ms clock. At each tick it unions PIDs across
subject trees, sums each unique live PID's RSS once, and retains the maximum
simultaneous aggregate; it never sums independent historical peaks. Physical
memory is `psutil.virtual_memory().total`. The harness also records minimum
system-available memory, swap use at start/end/peak, process signals, and any
OOM evidence. The process-spawn-to-`subject_ready` interval is recorded as
MATLAB startup plus path/manifest initialization; MATLAB-emitted stage timings
retain the internal split.

Event sequences start at 1 and are strictly contiguous. A successful subject
process emits exactly one `subject_ready`, exactly one `task_started` followed
by exactly one `task_outcome` for every selected task, and exactly one final
`subject_summary`. Run and subject IDs must match the manifest, task IDs must
be known, task execution may not overlap, and summary counts must equal parsed
outcomes. Exit code zero with a missing or inconsistent event is a protocol
failure.

A caught task failure is an ordinary `task_outcome` and does not terminate the
subject process. A manifest-write, force-reset, process-launch, event-parser,
or fatal MATLAB failure increments the separate `subject_process_failed`
summary field. Python first terminates the MATLAB process tree when needed,
waits for it to exit, reaps it, and stops the RSS sampler. Only then does it
perform one final artifact reconciliation and synthesize unfinished task
outcomes:

```text
parsed successful task_outcome, expected artifacts complete
  -> preserve the parsed outcome

parsed successful task_outcome, expected artifact missing
  -> failed

started task without outcome, all artifacts now present
  -> recovered_complete

unstarted task, all artifacts already present
  -> recovered_complete

unfinished task with an absent required upstream artifact
  -> skipped_dependency

other unfinished task
  -> failed
```

The `recovered_complete` status means only that the artifact contract is
complete after a protocol failure; it does not claim whether execution, copy,
or prior file state produced it. The CLI returns nonzero whenever `failed > 0`,
`skipped_dependency > 0`, or `subject_process_failed > 0`, while other
subjects continue. Published artifacts are never rolled back.

Production telemetry remains stdout-only and non-authoritative. The benchmark
harness may write parsed timing JSON/CSV under a dedicated validation root,
never inside canonical output leaves.

## Phase 0 Measurement Design

Instrumentation is implemented before performance changes. The compatibility
per-task bridge remains available as a reference path, and the benchmark
harness records:

- wall time;
- MATLAB startup/process count;
- peak process-tree RSS;
- stage timings;
- task outcomes; and
- output artifact inventory.

The harness runs one warm-up and five measured repetitions. A fixed copied
validation root prevents writes to authoritative subject trees. Every
repetition starts from the same frozen prepared-input snapshot. Selected leaves
and every equivalent donor leaf are restored to the fixture's declared initial
state before each run; otherwise a warm-up would turn later repetitions into
resume or donor-copy runs. Cold-headmodel and warm-headmodel fixtures are
separate snapshots. Each fixture declares and asserts expected MATLAB startup,
FEM solve, derived-task, copy, and skip counts for baseline and candidate.

## Low-Risk Output Optimizations

### Bulk Threshold Generation

A shared helper loads one E-field NIfTI once and receives an ordered collection
of requested `(threshold, output_path)` pairs. It creates every mask using:

```matlab
uint8(isfinite(E) & E >= threshold)
```

Each output preserves dimensions and affine, uses `uint8`, writes the existing
threshold-specific description, and publishes atomically. Solve and group-peak
paths call the same helper. `mh_vta_threshold_efield` remains a compatibility
wrapper around the one-item bulk helper.

Exact synthetic tests cover values below, equal to, and above each threshold;
`NaN`, positive infinity, negative infinity; partial requested sets; output
metadata; and atomic failure behavior.

### Bounding-Box Native Interpolation

The optimized exporter still allocates the complete anchor-sized single array
initialized to `NaN` and writes the original dimensions and affine.

It computes the physical axis-aligned min/max bounds of finite FEM sample
points in millimeters, enumerates all eight physical corners, converts those
corners with the Lead-DBS one-based
`ea_mm2vox(points_mm, anchor.mat)` convention, expands by one voxel, and then
floors/ceils. The implementation intersects that integer range with
`[1, anchor_dimensions]`; it does not clamp two wholly out-of-range endpoints
onto one boundary voxel. If any axis has `lower > upper` after intersection,
the result is the full-size all-`NaN` grid. Only voxels inside a nonempty
intersection are sent to `scatteredInterpolant`.

Using all eight physical corners is mandatory for rotated or sheared affines.
An entirely out-of-image box produces an all-`NaN` grid. Reference full-grid
and optimized results must have exact finite-mask agreement and exact values at
all finite voxels for derived interpolation fixtures.

Tests cover identity, translated, rotated, sheared, reflected, and
negative-determinant affines; image-boundary contact; fully internal support;
partially and fully out-of-image support; and insufficient finite samples.

### Context And Head-Model Load Consolidation

Canonical head-model loading is centralized in one helper that loads required
variables and immediately applies the coordinate-unit validator. Preparation
returns the validated structure to the backend for both reused and newly built
models. The backend consumes that exact structure without a second load.

This preserves the mandatory unit guard at the backend convergence boundary:
the only load operation and its validator occur together before
`ea_getactiveidx`. Existing invalid files remain non-overwritable. The current
source-string test that requires a literal backend `load(...)` is replaced by
runtime tests proving that invalid reused and newly built head models fail with
the established error IDs before `ea_getactiveidx` and do not overwrite files.

The backend-resolved `options`, reconstruction, trajectory, anchor, and MNI
reference are passed through export functions. Export code must not call
`ea_getptopts` or reload reconstruction for each field.

## Process-Local Cache Contracts

All caches live only inside one subject MATLAB process and are cleared on exit.
No cache is serialized or used as a resume authority.

Keys are explicit tuples:

```text
subject_context_key:
  subject_dir + reconstruction_path

headmodel_key:
  subject_context_key + hemisphere + canonical_headmodel_path
  + atlas_set + gray_matter_conductivity + white_matter_conductivity
  + canonical_meshing_version + canonical_headmodel_version
  + electrode_model + reconstruction_lead_id + trajectory_coordinates
  + patient_gm_mask_path + patient_gm_mask_size + patient_gm_mask_mtime_ns

export_geometry_key:
  headmodel_key + reconstruction_path + reconstruction_lead_id
  + electrode_model + trajectory_coordinates + lead_diameter

interpolation_geometry_key:
  export_geometry_key + native_anchor_path + dimensions + affine
  + finite_sample_support_signature
```

Manifest validation rejects tasks that share a head-model path while declaring
different atlas, conductivity, meshing-version, headmodel-version, electrode
model, reconstruction lead, trajectory, or resolved patient GM geometry.
`canonical_meshing_version` is the internal constant
`canonical_mask_surface_v1`; `canonical_headmodel_version` is
`simbio_onesolve_canonical_v1`. They are code-contract versions, not public
YAML fields.

The first persistent-worker implementation caches subject context, validated
head models, anchor headers, tetrahedron midpoints, tissue-selection indices,
and electrode-removal geometry. It does not cache `scatteredInterpolant`,
barycentric mappings, or gradient basis terms until timing shows a remaining
bottleneck and dedicated equivalence tests exist.

## Persistent Subject Runner

`mh_vta_run_canonical_subject_manifest` owns subject-local scheduling. It uses
the existing canonical solve and group-peak dispatchers rather than duplicating
their mathematical logic. Context and caches are passed explicitly through a
subject runtime structure; global persistent state is avoided except where a
focused cache helper owns and clears it deterministically.

The compatibility `run_task` bridge remains for focused acceptance and
baseline comparison, but production CLI `run` calls `run_subject_manifest`.
Subjects whose selected outputs are already complete never start MATLAB.

The Python service remains responsible for initial plan validation,
force-to-Trash, constructing donor catalogs, launching subject workers, aggregating
events, and final exit status. MATLAB owns only runtime file-state resolution,
same-subject copy, task dispatch, and subject-process caches.

## FEM System And Preconditioner Reuse

FEM reuse is introduced only after persistent subject execution and timing
evidence. The cache key includes:

```text
headmodel_key
control_mode
unipolar_or_bipolar_return_design
exact sorted constrained Dirichlet/return boundary-node set
matrix_assembly_version
PCG tolerance and iteration limit
ichol options
```

For a matching key, the cache retains the original symmetric stiffness or
Dirichlet-coupling terms needed to rebuild the RHS, the conditioned sparse
matrix, and the `ichol` preconditioner. The exact sorted constrained-node set
is part of the matrix key. Current injection support and current values remain
per-solve RHS inputs rather than matrix-key fields. Amplitude/RHS changes do
not invalidate the matrix; any changed constrained-node set does.

The RHS is rebuilt for every solve. Voltage Dirichlet values and current source
centers/values are never cached as if they were matrix-invariant. PCG retains
the existing initial guess, tolerance, and iteration limit.

Voltage and current fixture tests must prove cache hit/miss behavior. Real
voltage and fixed hypothetical current acceptance must satisfy the separate
backend and optimization numerical contracts before this cache is enabled in
production.

## Benchmark And Acceptance Set

The first implementation slice creates
`my_helper/vta/test/fixtures/vta_performance_benchmark_v1.json` using schema
`vta_performance_benchmark_v1`. The file freezes the canonical selectors,
task kind, source IDs, current and synthetic source payloads, output spaces,
threshold profile, initial artifact inventory, and expected execution counts:

- SNr003 T1/program 1/lead-R/group-1, `continuous_joint`, source `source-1`:
  cold- and warm-headmodel continuous single source;
- SNr003 T2/program 2/lead-L/group-1, alternating sources `source-1` and
  `source-2` plus `alternating_group_peak`;
- the SNr003 T1/program 1/lead-R/group-1 continuous leaf with all native and
  MNI threshold files removed but both E-fields retained: threshold-only
  repair;
- the same SNr003 T1/program 1/lead-R/group-1 continuous leaf with every
  expected file present: complete resume;
- SNr006 T2/program 2/lead-L/group-1, alternating sources `source-1` and
  `source-2` plus group peak: SceneRay SR1200 coverage;
- SNr011 T2/program 2/lead-L/group-1, `continuous_joint`, source `source-1`:
  SceneRay SR1202 coverage;
- one deterministic synthetic continuous multi-source FEM fixture, because the
  current cohort contains no real continuous multi-source group; and
- the fixed SNr003 right-sided single-cathode/case-return current fixture from
  `run_current_backend_equivalence`, seed `20260712`, as the current-control
  performance and numerical case.

All cases use spaces `native` and `MNI152NLin2009bAsym` and thresholds 180,
200, and 220 V/m. The synthetic and current payloads are serialized in the
benchmark manifest; production code contains no study-row special case.
The fixture stores stable semantic selector IDs. Because canonical task IDs
include absolute copied paths, the harness resolves and records exact task IDs
after materializing each frozen snapshot instead of hard-coding a production
root into the fixture.
Old-canonical versus optimized-canonical comparison uses a dedicated
`optimization_regression` comparator mode with the `1e-3 V/m` contract. The
existing standard-SimBio comparator retains its `0.05 V/m` backend gate.
Comparator unit tests include a finite-mask-matched difference strictly between
`1e-3` and `0.05 V/m`: the standard backend mode passes it and the optimization
regression mode must fail it.

Baseline and candidate both run with `--workers 3`. Each receives its own
warm-up. The five measured pairs use the fixed order baseline/candidate,
candidate/baseline, baseline/candidate, candidate/baseline,
baseline/candidate; every member is restored from the same frozen snapshot and
the report stratifies timing by run order. Temporary benchmark checksums are
allowed only under the validation root. Repeated derived arrays are exactly
equal, and repeated same-backend FEM arrays satisfy the existing exact
repeatability contract.

The performance metric is the median total wall time of the complete fixed
warm-headmodel suite across five measured repetitions after one warm-up for
each path. The candidate must satisfy:

```text
candidate median <= 0.75 * baseline median
```

Task execution class is the fixed tuple `(headmodel_state, task_kind,
control_mode, source_count_class, resolved_action)`. Subject-scope stages are
aggregated separately. For each repetition, stage durations are summed by
class and stage; the candidate median is compared with the baseline median for
that same class and stage. A cache hit emits its lookup duration and
`cache_status=hit`; a stage excluded by the resolved action is
`not_applicable`; an absent event for an expected stage is a protocol failure.
Process spawn to `subject_ready` is reported once as `startup_total` and is not
added to MATLAB's internal initialization stages.
No individual execution class or measured stage may regress by more than 10%
without a documented, evidence-backed justification. One fast case cannot hide
a regression in another class.

Additional gates:

- MATLAB startup count `<=` active subject count;
- fully complete resume starts zero MATLAB processes;
- threshold-only repair performs zero FEM solves;
- each E-field is loaded at most once per output space for all thresholds;
- interpolation queries stay inside the nonempty intersected sample bounding
  box;
- default `--workers 3` completes SNr003/SNr006/SNr011 without OOM or nested
  process parallelism;
- aggregate three-worker process-tree peak RSS is no greater than 75% of
  physical memory, and no one subject process tree exceeds 50% of physical
  memory; and
- all numerical, resume, copy, dependency, and atomic-publication tests pass.

The benchmark writes under a timestamped copied validation root. It never
overwrites authoritative `/Volumes/VAL/STNSNr` outputs.

## Implementation Slices

Each slice receives its own implementation plan, RED/GREEN cycle, review, and
commit:

1. Framed timing/outcome protocol and benchmark harness.
2. Bulk threshold generation.
3. Bounding-box native interpolation.
4. Centralized context/head-model loading.
5. Subject-manifest validation and runtime state machine.
6. Persistent MATLAB subject runner and Python bridge integration.
7. Process-local context/export-geometry caches.
8. FEM system/preconditioner reuse.
9. Numerical and performance acceptance plus documentation finalization.

Failure of a numerical gate blocks the next slice. Performance measurements may
change the priority of later caches but cannot weaken completion criteria.

## Deferred Work

- Disk-persistent caches or artifact hashes.
- Python-side VTA/group-peak array production.
- Source-level process parallelism.
- 4-D ANTs transform batching.
- Interpolant/barycentric or gradient-basis caching without new evidence.
- Versioned physical E-field reuse across differing frequency/pulse width.
- Changing thresholds, conductivities, atlas, output spaces, or backend.

## Completion Criteria

The optimization is complete only when all nine slices are implemented and
reviewed, every artifact and numerical contract passes, the fixed suite reaches
the 25% median improvement, default three-worker execution is memory-safe, and
the public documentation reports measured current behavior rather than planned
intent.
