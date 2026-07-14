# VTA Three-Worker Memory Gate Plan

## Purpose

Prove that the production subject-level runner is memory-safe with three active
workers before changing the public `vta-model run --workers` default from one
to three. This is an isolated acceptance run, not a scientific rerun.

## Current State

```text
design_documented
implementation_complete
first_gate_instrumentation_failed
corrected_gate_passed
documentation_updated_for_public_cli_default_workers_3
public_cli_default_workers_3_implemented
full_python_vta_suite_210_passed
full_matlab_fiber_suite_130_passed
```

The post-reuse numerical/performance gate and bounded real-current cache-hit
gate are complete. Their retained roots are read-only and are not reused as
three-worker outputs.

## Acceptance Workload

The gate reads selectors from the versioned performance fixture rather than
embedding protocol phase, program, electrode, or frequency-group values in
code. The selected case IDs are:

```text
snr003_t2_p2_l_alternating
snr006_t2_p2_l_alternating
snr011_t2_p2_l_continuous
```

The harness must assert that these resolve to exactly three distinct subjects
and share one phase/program/electrode/frequency-group selector tuple. It copies
only those subjects into a new validation root, rewrites their study-base paths,
and omits copied `headmodel` and `stimulations` directories. Production subject
trees and completed validation roots remain unchanged.

The measured run therefore exercises three concurrent cold subject workers:

```text
two alternating source tasks plus one group peak for subject 1
two alternating source tasks plus one group peak for subject 2
one continuous task for subject 3
```

This is five FEM solves and seven realized tasks. Cold head-model construction
is intentionally included because the public default also applies when a
subject has not yet been prepared. The canonical atlas-mask geometry fix must
prevent the former overlapping-atlas Boolean explosion.

## Execution Contract

The harness uses the production components directly:

```text
prepare_plan
ProcessTreeMemoryMonitor(sample_interval_seconds=0.1)
MatlabBridge(memory_monitor=shared_monitor)
RunService.run(workers=3, resume=false, force=false)
```

Exactly one persistent MATLAB root process is allowed per selected subject.
The shared monitor registers all three roots, unions descendant PIDs at each
sample, counts each live PID once, and reports synchronized aggregate and
per-subject RSS. The run must demonstrate an interval in which all three
subject roots are simultaneously registered; merely requesting three workers
is insufficient evidence.

No MATLAB task-level parallel pool is enabled. External meshing or transform
children remain descendants of their owning subject process and are included
in the process-tree measurement.

## Acceptance Gates

- exactly three selected subject plans and seven tasks resolve;
- exactly five FEM solves are observed from timing events;
- all seven task outcomes complete without failed or dependency-skipped tasks;
- three subject MATLAB roots overlap in time;
- no process signal, nonzero exit, OOM evidence, or uncontrolled nested MATLAB
  roots occur;
- aggregate process-tree peak RSS is no greater than 75% of physical memory;
- each subject process-tree peak RSS is no greater than 50% of physical memory;
- memory sample interval is 100 ms and sample count is positive;
- swap start/end/peak and minimum available memory are reported; and
- every configured native/MNI E-field and VTA artifact exists when the run
  finishes.

The gate writes an immutable validation directory containing the copied study
input, copied model YAML, resolved selector/case inventory, run summary, memory
observation, task outcome inventory, and acceptance summary. A failed directory
is retained and never overwritten.

## CLI Default Change

Only after every gate above passes:

1. update the public CLI default from `1` to `3`;
2. update CLI/README/model documentation;
3. add parser and service tests proving omitted `--workers` resolves to three
   while an explicit positive value still overrides it; and
4. rerun the complete Python VTA suite, complete MATLAB fiber suite, Code
   Analyzer for touched MATLAB files, and `git diff --check`.

If the memory gate fails, the public default remains one. The measured failure
must be documented; workers may still be selected explicitly by the user.

## First Measured Attempt

The first measured attempt is retained at:

```text
/Volumes/VAL/STNSNr/validation/vta_three_worker_memory_gate_20260714T142745398955Z
```

The computational and memory gates passed:

```text
FEM solves: 5/5
task outcomes: 7/7 generated
three live roots sampled: passed
aggregate peak RSS: 19,592,151,040 bytes (14.255%)
maximum subject peak RSS: 10,228,760,576 bytes (7.442%)
swap start/end/peak: 7,468,810,240 bytes (no increase)
OOM/signal evidence: none
all artifacts complete: passed
```

The attempt was correctly retained as failed because the nested-MATLAB
classifier used a broad `startswith("matlab_")` rule. It counted each expected
`matlab_helper` child as a nested MATLAB interpreter, producing a false count of
three. The corrected classifier must match only known MATLAB interpreter
executable names and exclude helper/service processes. Because the first run did
not retain sampled child names, it cannot be retroactively relabeled as passed;
at that point, the corrected gate still had to run before changing the public
CLI default.

## Corrected Measured Attempt

The corrected gate passed at:

```text
/Volumes/VAL/STNSNr/validation/vta_three_worker_memory_gate_20260714T143046769646Z
```

The production three-worker runner completed the bounded cold-subject workload:

```text
FEM solves: 5/5
task outcomes: 7/7 generated
three live roots sampled: passed (maximum 3)
aggregate peak RSS: 18,002,034,688 bytes (13.098%)
maximum subject peak RSS: 9,692,545,024 bytes (7.052%)
minimum available memory: 63,403,884,544 bytes
swap start/end/peak: 7,468,810,240 bytes (no increase)
memory samples: 381 at 100 ms
nested MATLAB interpreters: 0
OOM/signal evidence: none
all artifacts complete: passed
wall time: 68.499 s
```

All acceptance gates passed. The corrected interpreter classifier observed
only exact MATLAB interpreter executable names and did not count
`matlab_helper` service processes. This result authorizes changing the public
CLI default to three workers. The separately documented CLI and parser-test
update is now committed, and the default is three.

## Non-Goals

- no production output migration or overwrite;
- no hard-coded clinical meaning for the selected fixture phases;
- no change to FEM physics, thresholds, artifact names, or resume semantics;
- no full-cohort execution; and
- no claim that three workers are safe on a host with less memory than the
  measured machine without applying the same percentage gates.
