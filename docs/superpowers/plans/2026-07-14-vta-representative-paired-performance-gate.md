# VTA Representative Paired Performance Gate Implementation Plan

**Status:** implementation_not_started

**Parent design:**
`docs/superpowers/specs/2026-07-13-vta-performance-optimization-design.md`

**Optimization goal:**
`my_helper/fiber/vta_compute_performance_optimization_plan.md`

## Purpose

Measure the real-FEM performance effect of the persistent subject runner and
process-local caches without replaying the complete nine-case declaration for
every measured pair. The gate compares the preserved compatibility per-task
path with the production persistent-subject path on one representative warm
alternating group.

This is the pre-FEM-reuse performance baseline. It does not prove three-worker
memory safety, complete execution-class performance, or the final 25% goal for
the entire declared benchmark suite.

## Selected Case

Use only:

```text
case_id: snr003_t2_p2_l_alternating
subject: SNr003
phase: T2
program: 2
electrode: lead-L
frequency_group: group-1
headmodel_state: warm
tasks:
  alternating_source source-1
  alternating_source source-2
  alternating_group_peak source-1/source-2
```

This case exercises two sequential FEM solves, a dependent derived group-peak
task, repeated subject geometry, native/MNI export, and all configured VTA
thresholds. No production implementation may branch on these project IDs. The
test harness selects the declared fixture case by `case_id`, then resolves it
through the normal semantic planner.

## Compared Paths

`compatibility_per_task` executes the selected subject DAG in planner order
through `MatlabBridge.run_task`. Every executable task starts its own MATLAB
process with a fresh empty runtime. Dependency, existing-file, donor-copy,
failure, and artifact-validation semantics must match the compatibility
service immediately before the persistent-subject migration.

`persistent_subject` executes the same DAG through the production `RunService`
and `MatlabBridge.run_subject_manifest`. Exactly one MATLAB process owns the
subject and reuses its explicit process-local runtime.

These are test-harness execution paths. They must not add a production mode,
change the public CLI, or change the current one-worker default.

## Run Schedule And FEM Bound

Each path receives one unmeasured warm-up. Three measured pairs run in fixed
order:

```text
pair 1: compatibility_per_task, persistent_subject
pair 2: persistent_subject, compatibility_per_task
pair 3: compatibility_per_task, persistent_subject
```

Each path execution performs two FEM solves:

```text
warm-up: 2 paths * 2 FEM = 4 FEM
measured: 3 pairs * 2 paths * 2 FEM = 12 FEM
total maximum = 16 FEM
```

The harness aborts if observed completed FEM count exceeds this bound. A failed
or interrupted attempt is recorded from telemetry and is not silently retried.

## Snapshot And Isolation Contract

The benchmark root is timestamped under the validation root. Before every path
execution, restore the same frozen case snapshot to a path-specific working
directory. The authoritative study and subject trees are read-only. Existing
conflicting validation paths are moved to Trash.

The warm head model is copied into the frozen snapshot. Every repetition starts
with missing selected output leaves and identical head-model bytes. Baseline
and candidate never share generated output leaves.

## Measurements And Expected Counts

For every execution record wall time, process and FEM counts, derived/copy/skip
counts, process-tree peak RSS, system minimum available memory, swap
start/end/peak, stage timings and cache status, and artifact inventory.

```text
compatibility_per_task:
  matlab_process_count = 3
  fem_solve_count = 2
  derived_task_count = 1

persistent_subject:
  matlab_process_count = 1
  fem_solve_count = 2
  derived_task_count = 1
```

## Numerical And Artifact Gate

For every pair, compare corresponding native/MNI E-fields and thresholded VTA
artifacts. Derived group-peak arrays must be exactly equal. FEM outputs use:

```text
finite masks identical
affine maximum absolute difference <= 1e-12
E-field maximum absolute difference <= 1e-3 V/m
relative L2 error <= 1e-5
Pearson correlation >= 0.999999
VTA Dice >= 0.999 at 180/200/220 V/m
relative VTA volume difference <= 0.1%
discordant voxels confined to threshold +/- 1e-3 V/m
```

Missing artifacts, unexpected counts, malformed telemetry, or a nonzero case
process fails the gate.

## Performance Interpretation

Report the three-execution median for each path and:

```text
persistent_subject_median / compatibility_per_task_median
```

The representative-case target is:

```text
persistent_subject median <= 0.75 * compatibility_per_task median
```

Failure is retained as a performance result and informs the FEM-reuse slice; it
does not invalidate numerical correctness. This result must never be described
as the median of the complete nine-case suite.

## Test-Harness CLI

Add:

```bash
python my_helper/vta/test/run_vta_performance_benchmark.py run-paired \
  --benchmark-root <prepared-root> \
  --case snr003_t2_p2_l_alternating
```

`--case` is required and resolves exactly one declared fixture case. This gate
rejects other case IDs. Existing `validate`, `prepare`, and `run-baseline`
interfaces remain available; `run-baseline` is historical and is not used for
this gate.

## Solver-Free Verification

Tests must prove fixed order, exact process counts through fake bridges,
dependency blocking, disjoint snapshot restoration, the 16-FEM cap, artifact
pairing by task identity/space, failure on malformed results, and unchanged
production CLI/default workers. Run benchmark tests and the full Python VTA
pipeline suite in the `leaddbs` environment. MATLAB tests are required only if
MATLAB code changes; this slice is expected to change Python test infrastructure
only.

## Completion Evidence

This slice is complete only when solver-free tests pass, one isolated real-FEM
paired benchmark finishes within 16 FEM, all numerical gates pass, measurement
artifacts are written, both parent documents record the exact validation root,
and neither production outputs nor the MRtrix design document changed.

