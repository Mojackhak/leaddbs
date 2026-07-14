# VTA Representative Paired Performance Gate Implementation Plan

**Status:** implementation_complete_solver_free_verified_real_fem_pending

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

The paired execution path was implemented on 2026-07-14 in the test-only
benchmark harness. The focused
benchmark tests pass 33 tests, and the combined Python VTA pipeline/benchmark
suite passes 187 tests. Live validation resolves 9 cases and 13 semantic tasks.
Three review passes closed failure accounting, atomic single-use root claiming,
protected-root ordering, immutable per-run working paths, and partial telemetry
coverage. Case-filtered preparation and explicit warm-donor validation are
implemented; restored snapshots revalidate all recorded donor/context hashes
before MATLAB starts. No MATLAB or production CLI file changed. The 16-FEM real
run has not started, so no performance result is claimed yet.

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

The first single-use root,
`vta_performance_benchmark_20260714T110925763267Z`, stopped after both
compatibility warm-up FEM solves because the newly emitted
`native_anchor_load` timing stage was missing from the allowed registry. The
root remains immutable failed evidence with `2` completed FEM solves and is not
reused.

After that registry-only repair, one new root may explicitly credit this failed
root as the compatibility warm-up only when its summary proves exactly two
`fem_pcg_solve` executions for the same case and path, no generated artifacts,
and failure identifier `mh_vta:InvalidTimingStage` naming
`native_anchor_load`. The recovery run skips only the compatibility warm-up,
runs the persistent warm-up and all three measured pairs, and therefore performs
at most 14 new FEM solves. The linked aggregate remains the original 16-FEM
bound. No other failure reason or partial solve can receive warm-up credit.

Credit eligibility must also prove identical frozen physical inputs. The failed
and replacement roots must match on the semantic case selector and task
definitions, study-base and VTA-model bytes, and the recorded head-model,
reconstruction, and patient-GM-mask hashes. The failed working root must resolve
exactly the two distinct expected source tasks, and its recorded artifact
inventory must equal the complete expected inventory derived from those source
tasks plus their group-peak dependency. A caller-supplied partial inventory or a
minimal fabricated summary is not eligible.

The failed execution's restored working root must independently match its own
frozen snapshot on the study/model bytes, recorded head-model, reconstruction,
patient-GM-mask hashes, and frozen artifact state. Merely locating the working
directory beneath the failed root is insufficient.

Each credited process observation must have a non-boolean integer return code
that is nonzero and be a protocol-incomplete
failure for one distinct expected source task, with zero generated/copied
artifacts and one task-scoped executed `fem_pcg_solve` timing carrying the same
task ID. The error identifier and message must exactly identify
`mh_vta:InvalidTimingStage` at `native_anchor_load`.

The replacement-root claim, external credit claim, and first
`paired_in_progress` publication form one failure-aware state transition. Once
the replacement root is claimed, a credit conflict or claim/publication error
must publish a terminal `paired_failed` summary with zero new FEM solves. It
must never leave a claimed root reporting the stale `prepared` state.
After the external credit claim is acquired, the harness must revalidate the
failed root and reject any change since pre-claim validation.

## Snapshot And Isolation Contract

The benchmark root is timestamped under the validation root. Before every path
execution, restore the same frozen case snapshot to a path-specific working
directory. The authoritative study and subject trees are read-only. Existing
conflicting validation paths are moved to Trash.

The warm head model is copied into the frozen snapshot. Every repetition starts
with missing selected output leaves and identical head-model bytes. Baseline
and candidate never share generated output leaves.

Preparation accepts an explicit fixture `--case` selector and freezes only the
selected case. This avoids requiring head models or artifacts from unrelated
fixture cases and does not change semantic task resolution. The prepared
fixture contains only the selected case; `run-paired` still verifies its exact
documented case ID.

If the authoritative subject tree does not contain the required warm head
model, preparation may receive one explicit `--warm-headmodel-donor`. The donor
is copied only into the frozen validation snapshot, never into the production
subject tree. It is accepted only when exactly one warm case is selected, its
canonical filename matches the selected hemisphere, and the donor subject
tree's reconstruction and configured patient GM mask hashes equal the current
source subject's files. The copied donor SHA-256 and context hashes are written
to the snapshot manifest. The canonical MATLAB unit validator remains the
authoritative pre-boundary guard when each benchmark path loads the model.

For the 2026-07-14 gate, the explicit donor is:

```text
/Volumes/VAL/STNSNr/validation/
  vta_pipeline_e2e_maskfix_20260713T172111Z/copied_dataset/
  derivatives/leaddbs/sub-SNr003/headmodel/native/
  sub-SNr003_desc-headmodel2.mat
```

It passed `mh_vta_validate_canonical_headmodel_units`. Its reconstruction hash
is `e9e1273e7e7c2ebb60088891ca0e1a5e1c76ced6e6de7352e693d05912ac01`
and its configured patient GM mask hash is
`f1481029d1dede9a29400eb422f5b890eea7a39bf7c28d2520376bc34f93fa75`;
both equal the current source subject files.

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
  --case snr003_t2_p2_l_alternating \
  --credited-compatibility-warmup-root <failed-root>
```

Prepare this gate with:

```bash
python my_helper/vta/test/run_vta_performance_benchmark.py prepare \
  --study-base <study-base.json> \
  --vta-model <vta_model.yaml> \
  --work-root <validation-root> \
  --case snr003_t2_p2_l_alternating \
  --warm-headmodel-donor <validated-headmodel2.mat>
```

`run-paired --case` is required and resolves exactly one declared fixture case.
This gate rejects other case IDs. `prepare --case` is repeatable in the general
harness, but the warm donor option requires exactly one selected warm case.
`--credited-compatibility-warmup-root` is optional and accepted only under the
exact failed-stage contract above; otherwise both warm-ups run normally.
Existing unfiltered `validate`, `prepare`, and `run-baseline` interfaces remain
available; `run-baseline` is historical and is not used for this gate.

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
