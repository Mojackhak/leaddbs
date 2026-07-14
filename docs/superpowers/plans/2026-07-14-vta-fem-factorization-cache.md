# VTA FEM Factorization Cache Implementation Plan

## Purpose

Implement Phase 4 of the canonical VTA performance plan without changing the
scientific model, output contract, solver tolerances, or path-based resume
semantics. Reuse is process-local to one persistent subject worker.

## Current State

```text
design_documented
implementation_complete
post_reuse_acceptance_complete
pre_reuse_representative_gate_complete
real_current_cache_hit_gate_complete
post_reuse_representative_gate_complete
three_worker_memory_gate_not_run
public_cli_default_workers_1
```

The pre-reuse paired gate completed at
`/Volumes/VAL/STNSNr/validation/vta_performance_benchmark_20260714T113033575679Z`.
Its compatibility and persistent medians were `73.42287808400579 s` and
`44.65844920813106 s`, and all paired native/MNI arrays were exactly equal.

## Reuse Boundary

Cache one conditioned FEM system and its incomplete-Cholesky preconditioner only
when this complete key is identical:

```text
cache schema/version
canonical head-model cache key
control mode: voltage or current
return design: unipolar or bipolar
exact sorted unique constrained-node set
matrix dimensions
matrix assembly version
PCG tolerance and maximum iterations
ichol default/fallback options
```

Amplitude, signed boundary values, current-injection nodes, and RHS values are
not key fields because they are rebuilt for every solve. Voltage tasks therefore
reuse only when their exact electrode-plus-return constrained-node set matches.
Current tasks may reuse when their return constrained-node set matches, while
their current injection remains solve-specific.

No factorization cache is allowed without a nonempty validated canonical
head-model key and an explicit subject runtime. Different runtimes never share
entries.

## Memory Bound

Each subject runtime holds at most one factorization entry. A key miss replaces
the prior entry instead of accumulating large sparse matrices. The entry stores:

```text
symmetric unconditioned stiffness needed for solve-specific RHS conditioning
conditioned sparse system matrix
ichol preconditioner
exact cache key
```

The validated head model remains owned by the existing head-model cache. No
factorization or E-field is persisted to disk.

## Execution And Telemetry

Extend `mh_vta_fem_apply_dbs` with optional `SubjectRuntime`, `HeadmodelKey`, and
`ControlMode` arguments. The canonical backend passes the existing subject
runtime and validated head-model key.

On a miss:

1. Build the solve-specific RHS and Dirichlet values.
2. Assemble the symmetric and conditioned matrices exactly as before.
3. Build `ichol` with the existing default-then-ICT fallback.
4. Replace the process-local factorization entry.
5. Run PCG with the unchanged `1e-9` tolerance, `5000` iterations, and initial
   vector equal to the RHS.

On a hit:

1. Rebuild the solve-specific RHS and Dirichlet values.
2. Recondition the RHS using the cached symmetric stiffness.
3. Reuse the exact conditioned matrix and preconditioner.
4. Run the unchanged PCG solve.

`fem_matrix_preparation` and `fem_preconditioner` emit `cache_status=miss` or
`hit` when an exact cache identity is available. Direct uncached calls retain an
empty cache status. `fem_pcg_solve` always remains `executed`.

## File Scope

```text
my_helper/fiber/core/stimulation/model/mh_vta_create_subject_runtime.m
my_helper/fiber/core/stimulation/model/fem/mh_vta_fem_apply_dbs.m
my_helper/fiber/core/stimulation/model/backends/mh_vta_backend_simbio_onesolve_canonical.m
my_helper/fiber/tests/test_vta_fem_factorization_cache.m
my_helper/fiber/tests/test_vta_common_grid_export.m
```

No Python orchestration, YAML, output filename, scientific threshold, or public
CLI default changes in this slice.

## Solver-Free And Synthetic Acceptance

Tests must prove:

- same voltage constrained-node set with changed amplitude yields matrix and
  preconditioner hits while rebuilding the RHS;
- changed voltage constrained-node set misses and replaces the sole entry;
- current unipolar solves with changed injection contacts reuse only the stable
  return-conditioned matrix and remain numerically equal to uncached solves;
- changed control mode or return design misses;
- constrained-node ordering does not change identity;
- different runtimes do not share entries;
- missing head-model identity disables caching;
- cached and uncached potentials agree within `1e-12` on deterministic fixtures;
- matrix/preconditioner/PCG event order remains unchanged and cache statuses are
  correct; and
- the runtime factorization cache count never exceeds one.

Run the complete MATLAB fiber suite, Python VTA suite, Code Analyzer, and
`git diff --check` before committing.

## Real-FEM Acceptance

After implementation, prepare a fresh isolated representative root and repeat
the paired numerical/performance gate without modifying the completed pre-reuse
root. Because the representative alternating voltage sources use different
constrained-node sets, no factorization hit is assumed for that case; lack of a
speedup there is not hidden or relabeled.

Also run one bounded current-control repeated-return case that demonstrates a
real factorization hit. Pre- and post-reuse voltage/current outputs must satisfy
the existing numerical gates. Only after these pass may the separate
three-worker memory gate run. The public CLI default remains one worker until
that gate independently passes.

The real current cache-hit gate is intentionally bounded to two FEM solves. It
uses one copied subject, one validated head model, one process-local subject
runtime, and two output-isolated canonical tasks with the same deterministic
current source and return design. The first task must report matrix and
preconditioner `miss`; the second must report `hit`. Their native and MNI
E-fields and all 180/200/220 V/m masks must pass the dedicated
`optimization_regression` comparator. Exact task identity is repeated here so
the output comparison proves that reuse changes neither the physical input nor
the result; changed-injection and changed-amplitude correctness remain covered
by the synthetic FEM cache suite. The gate must also prove that the runtime
contains at most one factorization entry and that both output leaves are
independent.

The post-reuse voltage/performance gate uses a fresh isolated representative
root and the existing bounded paired harness. Its completed pre-reuse root is
read-only numerical evidence; it is never modified or relabeled. The
representative alternating sources have distinct constrained-node sets, so
their expected cache sequence is miss/miss. This gate validates the optimized
production path and performance contract but is not presented as a
factorization-hit case.

## Measured Current Cache-Hit Evidence

The bounded gate passed at:

```text
/Volumes/VAL/STNSNr/validation/vta_current_factorization_cache_20260714_070153_462
```

Measured evidence:

```text
planned/actual FEM solves: 2/2
matrix cache sequence: miss -> hit
preconditioner cache sequence: miss -> hit
factorization entries after both solves: 1
native maximum E-field difference: 0 V/m
MNI maximum E-field difference: 0 V/m
native/MNI relative L2: 0
native/MNI correlation: 1
VTA Dice at 180/200/220 V/m: 1
relative VTA volume difference: 0
independent output leaves: passed
```

The failed setup-only root ending in `070049_790` contains no FEM result and is
not acceptance evidence. It is retained rather than overwritten or deleted.

## Measured Post-Reuse Representative Evidence

The fresh bounded paired gate passed at:

```text
/Volumes/VAL/STNSNr/validation/vta_performance_benchmark_20260714T140401688999Z
```

Measured evidence:

```text
completed FEM solves: 16/16
compatibility median: 77.99708383297548 s
persistent median: 44.61829545791261 s
persistent/compatibility ratio: 0.5720508160722921
25 percent target: passed
maximum E-field difference: 0 V/m
maximum relative L2: 0
minimum correlation: 1
maximum affine difference: 0
minimum VTA Dice: 1
maximum relative VTA volume difference: 0
peak single-subject process-tree RSS: 9,205,678,080 bytes
```

The alternating voltage tasks have different constrained-node sets and
therefore correctly report factorization misses. Median matrix-preparation time
rose by about `10 ms` (`18.29%` compatibility, `19.35%` persistent) because the
miss path now validates and publishes the exact bounded cache identity. The
only other stage above the 10% relative-review threshold was persistent
electrode removal (`+1.7 ms`, `11.70%`); that stage was untouched and the
absolute change is measurement noise. Persistent total median changed from
`44.65844920813106 s` pre-reuse to `44.61829545791261 s` post-reuse.
