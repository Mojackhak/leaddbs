# VTA Persistent Subject Runner Implementation Plan

## Status

```text
design_aligned
implementation_complete
solver_free_verification_complete
subject_manifest_contract_available
production_subject_runner_active
compatibility_per_task_runner_available
current_outputs_unchanged
```

## Goal

Connect the validated `vta_subject_manifest_v1` contract to one persistent
MATLAB batch process per active subject. Preserve the canonical task schema,
artifact paths, numerical model, path-existence resume rule, subject-level
parallelism, and the per-task compatibility runner.

This is slice 6 of the approved VTA performance optimization design. It removes
repeated MATLAB startup within one subject but does not yet introduce
process-local geometry or FEM matrix caches.

As implemented on 2026-07-14, production `run` orchestration launches at most
one MATLAB batch process for each active subject and launches none for a fully
complete subject. Python retains manifest construction, transactional force
reset, process lifecycle, partial telemetry snapshots, fatal-process artifact
reconciliation, and final exit status. MATLAB owns ordered runtime resolution,
donor copies, dispatch, and task events. The complete Python VTA pipeline and
benchmark suite passes 159 tests, the complete solver-free MATLAB fiber suite
passes 114 tests, and Code Analyzer reports no findings in the new MATLAB
runner or its tests. No real FEM performance claim is made by this slice.

## MATLAB Subject Runner

Add `mh_vta_run_canonical_subject_manifest` as the only new production subject
entry point. It must:

1. decode and validate one manifest before execution;
2. create one event emitter for the manifest run and subject;
3. emit `subject_ready` once;
4. process every selected task in manifest order;
5. emit one `task_started` and one `task_outcome` for every task;
6. call `mh_vta_resolve_manifest_task` immediately before each task;
7. return `skipped_existing`, `copied`, or `skipped_dependency` without FEM;
8. execute only `ready` tasks through `mh_vta_execute_canonical_task`;
9. recompute all expected artifacts after execution;
10. report `generated` when execution returns and the task is complete;
11. report `failed` for every caught task exception, including an exception
    raised after artifacts were published;
12. reserve `recovered_complete` for Python fatal-process reconciliation;
13. catch task-level failures and continue later independent tasks; and
14. emit one summary whose counts and `process_success` match the event
    protocol.

`process_success` is false when any task is `failed` or
`skipped_dependency`, matching the current Python parser contract. A caught
task failure does not terminate MATLAB and does not prevent independent later
tasks from running. Manifest decode/validation failure remains a fatal nonzero
process failure and may occur before an emitter can be created.

The runner emits `task_runtime_resolution` timing around path recheck and donor
copy resolution. Existing backend stage timings continue to use the same
emitter. No project-specific subject, phase, program, frequency, target, or
electrode value may appear in production code.

## Python Bridge

Extend `MatlabBridge` with `run_subject_manifest(subject, run_id)`:

- build and atomically write the deterministic manifest in a temporary
  directory;
- launch exactly one `matlab -batch` process invoking
  `mh_vta_run_canonical_subject_manifest`;
- bootstrap only the canonical model runner directory, then let the subject
  runner time one full repository path initialization before manifest
  validation and `subject_ready`;
- parse the complete ordered task ID sequence with one `EventStreamParser`;
- retain a partial parser snapshot when a process, stream, or protocol failure
  occurs after one or more complete task outcomes;
- register and unregister exactly one subject process tree with the shared RSS
  monitor;
- terminate and reap the process group on parser or stream failure; and
- remove the temporary manifest after process exit.

Keep `run_task` and `mh_vta_run_canonical_task` as compatibility interfaces.
Shared process launch/stream/reap behavior should be factored rather than
duplicated, but compatibility behavior and event validation must remain
unchanged.

## Run Service State Machine

Replace Python's per-task execution loop with one subject process call:

```text
force requested
  -> transactionally move every existing selected leaf to Trash
  -> rollback prior moves if a later move fails

all selected tasks complete after force handling
  -> do not start MATLAB
  -> synthesize skipped_existing for every selected task

otherwise
  -> launch one subject manifest process
  -> aggregate parsed task outcomes
```

Add these explicit `RunSummary` fields:

```text
generated
copied
skipped_existing
recovered_complete
failed
skipped_dependency
subject_process_failed
```

If process launch, manifest I/O, event parsing, or fatal MATLAB execution
fails, increment `subject_process_failed` and perform one final path-based
reconciliation after the process has been reaped:

- a parsed successful task whose artifact set remains complete preserves its
  parsed status;
- a parsed successful task whose artifact set is incomplete becomes `failed`;
- a parsed `failed` or `skipped_dependency` outcome preserves that status;
- an unfinished task whose full artifact set exists becomes
  `recovered_complete`;
- an unfinished alternating group peak whose currently required source native
  E-field is absent becomes `skipped_dependency`;
- any other unfinished task becomes `failed`.

Other subjects continue. The overall CLI remains nonzero when `failed`,
`skipped_dependency`, or `subject_process_failed` is nonzero. `--resume`
remains a no-op compatibility alias for ordinary path-based resume.

Force reset is transactional per subject. Preflight rejects duplicate or
overlapping selected leaves and unavailable Trash destinations. Every
successful move records source and destination. If a later move fails, restore
earlier moves in reverse order. An incomplete rollback increments
`subject_process_failed`, reports the failure, and does not launch MATLAB for
that subject.

## Tests

### MATLAB

Add solver-free subject-runner tests for:

- one process handling multiple ordered tasks;
- complete and fully copied tasks avoiding dispatch;
- partial-copy tasks dispatching only remaining artifacts;
- task failure followed by an independent successful task;
- artifact-specific group-peak dependency skip;
- generated and recovered-complete classification;
- exact event order, counts, generated/copied counts, and summary state; and
- fatal malformed manifest behavior.

### Python

Add bridge and service tests for:

- one MATLAB launch per active subject and no launch for complete subjects;
- deterministic manifest creation and cleanup;
- multi-task event parsing and RSS monitor lifecycle;
- partial parser snapshots that preserve completed outcomes;
- process termination/reaping on protocol failure;
- aggregation of every task outcome status;
- fatal-process artifact reconciliation;
- independent subjects continuing after one process failure;
- transactional force success, rollback, and rollback-failure accounting; and
- preservation of the per-task compatibility bridge.

Run the complete Python VTA pipeline/benchmark suite, complete solver-free
MATLAB fiber suite, MATLAB Code Analyzer on touched files, `git diff --check`,
and the no-project-hardcoding scan. No real FEM run is required for this
process-architecture slice.

## Acceptance

This slice is complete only when:

- one active subject creates at most one MATLAB process;
- tasks remain sequential and topologically ordered inside that process;
- all task outcomes and process failures are fully accounted for;
- path-based resume and donor reuse remain artifact-specific;
- complete subjects launch no process;
- force reset cannot silently leave a partially reset subject;
- the compatibility task runner still passes its tests; and
- documentation records that process-local caches, FEM reuse, real FEM timing,
  and the three-worker memory gate remain pending.
