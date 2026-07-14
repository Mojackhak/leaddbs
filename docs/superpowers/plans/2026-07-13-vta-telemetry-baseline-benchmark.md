# VTA Telemetry And Baseline Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reusable VTA event parsing, synchronized process-tree memory measurement, MATLAB stage timing, and a reproducible baseline benchmark without changing the scientific model or task scheduler.

**Architecture:** Keep the current one-MATLAB-process-per-task compatibility path for this slice, but make each process emit the same framed protocol that the future subject runner will use. Python parses the protocol and samples all registered MATLAB process trees on one clock. A frozen benchmark fixture restores copied inputs before each paired baseline/candidate measurement and never writes authoritative outputs.

**Tech Stack:** Python 3 in the `leaddbs` Conda environment, pytest, psutil 7.2, MATLAB function-based tests, Lead-DBS canonical VTA functions, JSON fixtures.

## Global Constraints

- The approved design is `docs/superpowers/specs/2026-07-13-vta-performance-optimization-design.md`.
- Write code, comments, identifiers, test names, and documentation examples in English.
- Use `/opt/anaconda3/envs/leaddbs/bin/python` for Python tests and the `leaddbs` Conda environment for MATLAB tests.
- Do not modify, stage, or commit the MRtrix design document.
- Do not change conductivities, atlas, thresholds, interpolation, output paths, source grouping, control-mode semantics, or artifact contents.
- Do not change the public CLI worker default in this slice; the benchmark passes `--workers 3` explicitly.
- Do not implement the persistent subject runner, donor catalog, or new state machine in this slice.
- Production telemetry is stdout-only. No provenance, hash, timing, or QC file is added to canonical output leaves.
- Benchmark files and temporary checksums are confined to a copied validation root.
- Every production-code change follows RED, GREEN, REFACTOR.

---

## File Map

- Create `my_helper/fiber/core/vta_pipeline/telemetry.py`: framed event types, parser, grammar validation, and process observation records.
- Create `my_helper/fiber/core/vta_pipeline/process_monitor.py`: synchronized unique-PID RSS sampling for registered MATLAB process trees.
- Create `my_helper/fiber/core/vta_pipeline/tests/test_telemetry.py`: event grammar and failure tests.
- Create `my_helper/fiber/core/vta_pipeline/tests/test_process_monitor.py`: deterministic RSS aggregation tests.
- Modify `my_helper/fiber/core/vta_pipeline/errors.py`: add protocol and MATLAB process errors.
- Modify `my_helper/fiber/core/vta_pipeline/matlab_bridge.py`: use `Popen`, parse framed events, forward diagnostics, and register process memory.
- Modify `my_helper/fiber/core/vta_pipeline/tests/test_matlab_bridge.py`: bridge protocol, diagnostics, process failure, and compatibility tests.
- Create `my_helper/fiber/core/stimulation/model/mh_vta_make_event_emitter.m`: contiguous `vta_event_v1` JSON event writer.
- Create `my_helper/fiber/core/stimulation/model/mh_vta_emit_stage_timing.m`: validated stage timing helper.
- Modify `my_helper/fiber/core/stimulation/model/mh_vta_run_canonical_task.m`: one-task compatibility event sequence.
- Modify `my_helper/fiber/core/stimulation/model/mh_vta_execute_canonical_task.m`: optional emitter propagation.
- Modify `my_helper/fiber/core/stimulation/model/backends/mh_vta_backend_simbio_onesolve_canonical.m`: context, headmodel, boundary, gradient, and export timing.
- Modify `my_helper/fiber/core/stimulation/model/fem/mh_vta_fem_apply_dbs.m`: matrix, preconditioner, and PCG timing.
- Modify `my_helper/fiber/core/stimulation/model/mh_vta_export_canonical_outputs.m`: export-stage timing.
- Modify `my_helper/fiber/core/stimulation/model/mh_vta_derive_canonical_group_peak.m`: derived-stage timing.
- Modify `my_helper/fiber/core/stimulation/model/mh_vta_publish_atomic.m`: optional publication timing without changing atomic behavior.
- Create `my_helper/fiber/tests/test_vta_event_protocol.m`: MATLAB event and call-order tests.
- Modify `my_helper/fiber/tests/test_vta_canonical_task_contract.m`: compatibility runner event assertions.
- Create `my_helper/vta/test/fixtures/vta_performance_benchmark_v1.json`: frozen semantic benchmark cases and expected counts.
- Create `my_helper/vta/test/run_vta_performance_benchmark.py`: fixture validation, snapshot restore, paired execution, and report generation.
- Create `my_helper/vta/test/test_run_vta_performance_benchmark.py`: solver-free benchmark harness tests.
- Modify `my_helper/vta/test/README.md`: document baseline-only execution and artifact location.

### Task 1: Implement The Framed Event Parser

**Files:**
- Create: `my_helper/fiber/core/vta_pipeline/telemetry.py`
- Create: `my_helper/fiber/core/vta_pipeline/tests/test_telemetry.py`
- Modify: `my_helper/fiber/core/vta_pipeline/errors.py`

**Interfaces:**
- Consumes: stdout lines, expected `run_id`, `subject_id`, and ordered task IDs.
- Produces: `EventStreamParser.feed_line(line)`, `EventStreamParser.finish(returncode)`, `ProcessObservation`, `StageTiming`, and `TaskOutcome`.

- [ ] **Step 1: Write failing parser tests**

Add tests that construct compact JSON lines with the exact `MH_VTA_EVENT `
prefix. Cover:

```python
def test_accepts_complete_one_task_protocol():
    parser = EventStreamParser("run", "SNr003", ("task-1",))
    for event in (
        event(1, "stage_timing", scope="subject",
              stage="manifest_decode_validation", stage_status="executed",
              duration_seconds=0.1),
        event(2, "subject_ready"),
        event(3, "task_started", task_id="task-1"),
        event(4, "task_outcome", task_id="task-1", status="generated",
              copied_artifact_count=0, generated_artifact_count=8),
        event(5, "subject_summary", generated=1, copied=0,
              skipped_existing=0, recovered_complete=0, failed=0,
              skipped_dependency=0, process_success=True),
    ):
        assert parser.feed_line(EVENT_PREFIX + json.dumps(event)) is None
    result = parser.finish(returncode=0)
    assert result.outcomes[0].status == "generated"
    assert result.protocol_complete
```

Add separate failing cases for malformed prefixed JSON, sequence gaps,
wrong run/subject/task IDs, timing after summary, task timing outside an active
task, outcome without start, two active tasks, summary count mismatch, missing
summary, and exit zero with incomplete protocol.

- [ ] **Step 2: Verify RED**

```bash
/opt/anaconda3/envs/leaddbs/bin/python -m pytest +  my_helper/fiber/core/vta_pipeline/tests/test_telemetry.py -q
```

Expected: collection fails because `telemetry.py` does not exist.

- [ ] **Step 3: Add focused exception types**

Add:

```python
class EventProtocolError(VtaPipelineError):
    """Raised when framed MATLAB telemetry violates vta_event_v1."""


class MatlabProcessError(VtaPipelineError):
    """Raised when a MATLAB process exits unsuccessfully."""
```

- [ ] **Step 4: Implement the parser**

Use immutable dataclasses. Keep raw diagnostic lines outside the protocol
records. The parser state is exactly:

```python
EVENT_PREFIX = "MH_VTA_EVENT "
TASK_OUTCOME_STATUSES = frozenset({
    "generated", "copied", "skipped_existing",
    "recovered_complete", "failed", "skipped_dependency",
})

@dataclass(frozen=True)
class StageTiming:
    scope: str
    task_id: str | None
    stage: str
    stage_status: str
    cache_status: str | None
    duration_seconds: float

@dataclass(frozen=True)
class TaskOutcome:
    task_id: str
    status: str
    copied_artifact_count: int
    generated_artifact_count: int
    error_identifier: str | None = None
    error_message: str | None = None

@dataclass(frozen=True)
class ProcessObservation:
    run_id: str
    subject_id: str
    outcomes: tuple[TaskOutcome, ...]
    timings: tuple[StageTiming, ...]
    protocol_complete: bool
    returncode: int
```

`finish()` requires contiguous sequence numbers starting at 1, exactly one
ready and summary event, one ordered started/outcome pair per expected task,
matching summary counts, and no event after summary. A nonzero return code
raises `MatlabProcessError` after parser validation; malformed protocol raises
`EventProtocolError`.

- [ ] **Step 5: Verify GREEN and commit**

Run the Step 2 command. Expected: all tests pass.

```bash
git add +  my_helper/fiber/core/vta_pipeline/errors.py +  my_helper/fiber/core/vta_pipeline/telemetry.py +  my_helper/fiber/core/vta_pipeline/tests/test_telemetry.py
git commit -m "feat: parse framed VTA telemetry"
```

### Task 2: Add Synchronized Process-Tree Memory Sampling

**Files:**
- Create: `my_helper/fiber/core/vta_pipeline/process_monitor.py`
- Create: `my_helper/fiber/core/vta_pipeline/tests/test_process_monitor.py`

**Interfaces:**
- Produces: `ProcessTreeMemoryMonitor(sample_interval_seconds=0.1)`,
  `register(subject_id, pid)`, `unregister(subject_id, pid)`,
  `sample_once()`, and `finish()`.
- Returns: `MemoryObservation` with aggregate peak, per-subject peaks,
  physical memory, minimum available memory, swap start/end/peak, and sample
  count.

- [ ] **Step 1: Write failing deterministic monitor tests**

Inject a fake process provider and fake virtual/swap memory providers. Prove
that overlapping descendant PIDs are counted once:

```python
def test_sample_sums_unique_live_pids_once():
    provider = FakeProvider({
        10: tree(10, rss=100, children=(11,)),
        20: tree(20, rss=200, children=(11, 21)),
        11: tree(11, rss=50),
        21: tree(21, rss=25),
    })
    monitor = ProcessTreeMemoryMonitor(
        process_provider=provider.process,
        virtual_memory_provider=lambda: memory(total=1000, available=400),
        swap_memory_provider=lambda: swap(used=10),
        start_thread=False,
    )
    monitor.register("SNr003", 10)
    monitor.register("SNr006", 20)
    monitor.sample_once()
    result = monitor.finish()
    assert result.aggregate_peak_rss_bytes == 375
    assert result.subject_peak_rss_bytes == {"SNr003": 150, "SNr006": 275}
```

Also test vanished processes, unregister, zero samples, minimum available
memory, swap peak, and idempotent shutdown.

- [ ] **Step 2: Verify RED**

```bash
/opt/anaconda3/envs/leaddbs/bin/python -m pytest +  my_helper/fiber/core/vta_pipeline/tests/test_process_monitor.py -q
```

Expected: import failure.

- [ ] **Step 3: Implement the monitor**

Use one daemon thread and one lock. At each 100 ms tick:

```python
roots = dict(self._roots)
unique_processes: dict[int, psutil.Process] = {}
subject_pids: dict[str, set[int]] = {}
for subject_id, root_pid in roots.items():
    processes = [psutil.Process(root_pid)]
    processes.extend(processes[0].children(recursive=True))
    subject_pids[subject_id] = {process.pid for process in processes}
    unique_processes.update({process.pid: process for process in processes})
rss_by_pid = {
    pid: process.memory_info().rss
    for pid, process in unique_processes.items()
    if process.is_running()
}
```

Catch only `NoSuchProcess`, `ZombieProcess`, and `AccessDenied` per PID.
Aggregate RSS is the same-tick sum of `rss_by_pid`; per-subject RSS uses that
subject's PID set. Never sum historical per-subject peaks.

- [ ] **Step 4: Verify GREEN and commit**

Run the Step 2 command. Expected: all tests pass.

```bash
git add +  my_helper/fiber/core/vta_pipeline/process_monitor.py +  my_helper/fiber/core/vta_pipeline/tests/test_process_monitor.py
git commit -m "feat: sample VTA process memory"
```

### Task 3: Emit The One-Task MATLAB Protocol

**Files:**
- Create: `my_helper/fiber/core/stimulation/model/mh_vta_make_event_emitter.m`
- Create: `my_helper/fiber/core/stimulation/model/mh_vta_emit_stage_timing.m`
- Create: `my_helper/fiber/tests/test_vta_event_protocol.m`
- Modify: `my_helper/fiber/core/stimulation/model/mh_vta_run_canonical_task.m`
- Modify: `my_helper/fiber/core/stimulation/model/mh_vta_execute_canonical_task.m`
- Modify: `my_helper/fiber/tests/test_vta_canonical_task_contract.m`

**Interfaces:**
- `emit = mh_vta_make_event_emitter(runId, subjectId)`
- `emit(eventType, fieldsStruct)`
- `mh_vta_emit_stage_timing(emit, scope, taskId, stage, status, duration, cacheStatus)`

- [ ] **Step 1: Write failing MATLAB event tests**

Use `evalc` to capture stdout. Assert every framed line decodes, sequence is
`1:N`, and success emits:

```text
stage_timing(manifest_decode_validation)
subject_ready
task_started
task_outcome(generated)
subject_summary(process_success=true)
```

A throwing solve stub must emit `failed` outcome and a failure summary before
rethrowing the original error. Invalid JSON may exit without events because
run and subject IDs are unavailable.

- [ ] **Step 2: Verify RED**

```bash
conda run -n leaddbs matlab -batch +  "addpath(genpath('/Users/mojackhu/Github/leaddbs')); +   r=testsuite('my_helper/fiber/tests/test_vta_event_protocol.m'); +   assertSuccess(run(r));"
```

Expected: undefined emitter failure.

- [ ] **Step 3: Implement the emitter**

`mh_vta_make_event_emitter` owns a nested sequence counter. It writes exactly:

```matlab
fprintf('MH_VTA_EVENT %s\n', jsonencode(payload));
```

Every payload contains `schema_version='vta_event_v1'`, event type, sequence,
run ID, and subject ID. Reject non-scalar text IDs and unsupported event types.

- [ ] **Step 4: Instrument the compatibility runner**

Time JSON decode plus canonical validation. After validation, create the
emitter, emit the completed initialization timing and `subject_ready`, then
`task_started`. Pass `EventEmitter` to
`mh_vta_execute_canonical_task`. On success emit generated counts from
`task.missing_artifacts`, then the matching summary. On failure emit a failed
outcome with `ME.identifier` and `ME.message`, emit a failure summary, then
rethrow.

Custom test solve/derived callbacks retain their one-argument signature.
`mh_vta_execute_canonical_task` passes the emitter only to the default
canonical backend or default group-peak function.

- [ ] **Step 5: Verify GREEN and commit**

Run the new suite plus the existing task contract:

```bash
conda run -n leaddbs matlab -batch +  "addpath(genpath('/Users/mojackhu/Github/leaddbs')); +   r=[testsuite('my_helper/fiber/tests/test_vta_event_protocol.m'), +      testsuite('my_helper/fiber/tests/test_vta_canonical_task_contract.m')]; +   assertSuccess(run(r));"
```

```bash
git add +  my_helper/fiber/core/stimulation/model/mh_vta_make_event_emitter.m +  my_helper/fiber/core/stimulation/model/mh_vta_emit_stage_timing.m +  my_helper/fiber/core/stimulation/model/mh_vta_run_canonical_task.m +  my_helper/fiber/core/stimulation/model/mh_vta_execute_canonical_task.m +  my_helper/fiber/tests/test_vta_event_protocol.m +  my_helper/fiber/tests/test_vta_canonical_task_contract.m
git commit -m "feat: emit canonical VTA task events"
```

### Task 4: Integrate Popen, Protocol Parsing, And RSS

**Files:**
- Modify: `my_helper/fiber/core/vta_pipeline/matlab_bridge.py`
- Modify: `my_helper/fiber/core/vta_pipeline/tests/test_matlab_bridge.py`

**Interfaces:**
- `MatlabBridge.run_task(task, context) -> ProcessObservation`
- Constructor accepts `popen_factory`, optional shared
  `ProcessTreeMemoryMonitor`, and optional diagnostic sink.

- [ ] **Step 1: Replace runner mocks with a fake Popen and write RED tests**

The fake exposes `pid`, iterable `stdout`, `wait()`, `poll()`,
`terminate()`, and `kill()`. Test:

- valid events return one generated outcome;
- unprefixed lines reach the diagnostic sink only;
- malformed prefixed lines terminate/reap the process and raise
  `EventProtocolError`;
- nonzero exit raises `MatlabProcessError`;
- monitor registration precedes stdout consumption and unregister follows
  process reaping;
- task JSON is deleted after completion;
- the MATLAB batch command still calls `mh_vta_run_canonical_task`.

- [ ] **Step 2: Verify RED**

```bash
/opt/anaconda3/envs/leaddbs/bin/python -m pytest +  my_helper/fiber/core/vta_pipeline/tests/test_matlab_bridge.py -q
```

Expected: failures because the bridge still uses `subprocess.run`.

- [ ] **Step 3: Implement the streaming bridge**

Start:

```python
process = self._popen_factory(
    [self.matlab_executable, "-batch", batch],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
    start_new_session=True,
)
```

Register the root PID, stream lines through `EventStreamParser`, and forward
only unprefixed lines to the diagnostic sink. On parser failure, terminate,
wait with a bounded timeout, kill if still alive, reap, unregister, then
reraise. On POSIX, termination targets the process group created for the
MATLAB launch so child processes do not survive the failed root process. The
original protocol/process exception remains primary if cleanup also reports an
error. RSS unregister occurs only after successful process reaping. On normal
EOF, wait, unregister, and call `finish(returncode)`.

- [ ] **Step 4: Verify GREEN and commit**

Run the Step 2 command plus all VTA pipeline Python tests:

```bash
/opt/anaconda3/envs/leaddbs/bin/python -m pytest +  my_helper/fiber/core/vta_pipeline/tests -q
```

```bash
git add +  my_helper/fiber/core/vta_pipeline/matlab_bridge.py +  my_helper/fiber/core/vta_pipeline/tests/test_matlab_bridge.py
git commit -m "feat: observe MATLAB VTA processes"
```

### Task 5: Add Stage-Level Timing Without Changing Results

**Files:**
- Modify the backend, FEM, export, group-peak, and atomic-publication files
  listed in the File Map.
- Modify: `my_helper/fiber/tests/test_vta_event_protocol.m`
- Modify: `my_helper/fiber/tests/test_vta_common_grid_export.m`

**Interfaces:**
- Every modified MATLAB function accepts optional `EventEmitter` and
  `TaskId` name/value arguments or receives them from its caller.
- Empty emitters are no-ops and preserve existing direct callers.

- [ ] **Step 1: Add RED timing tests with injected stubs**

Use stub functions and a collecting emitter to assert stage names and nesting:

```text
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

Threshold timing may repeat and is summed by the benchmark. A skipped stage is
omitted in production and classified `not_applicable` by the resolved action
matrix. No stage may publish an event after task outcome.

- [ ] **Step 2: Verify RED**

Run:

```bash
conda run -n leaddbs matlab -batch +  "addpath(genpath('/Users/mojackhu/Github/leaddbs')); +   r=[testsuite('my_helper/fiber/tests/test_vta_event_protocol.m'), +      testsuite('my_helper/fiber/tests/test_vta_common_grid_export.m')]; +   assertSuccess(run(r));"
```

Expected: missing stage events.

- [ ] **Step 3: Instrument exact operation boundaries**

- Time context around `build_context`.
- Time headmodel preparation plus validated load as
  `headmodel_build_or_load`, with `cache_status=hit` only for a reused model.
- Time `ea_getactiveidx` plus `mh_vta_assemble_boundary` as
  `active_contact_boundary`.
- Split `mh_vta_fem_apply_dbs` timing around `dbs_matrix`, `ichol`, and
  `pcg`; do not change matrices, tolerances, initial guess, or return values.
- Time gradient calculation.
- Time electrode sample removal separately from common-grid interpolation.
- Time each threshold producer, MNI transform, and final atomic rename.
- Time group-peak composition as `group_peak_composition` with
  `stage_status='executed'`; do not change its NaN-union algorithm.

- [ ] **Step 4: Verify numerical noninterference**

Run all focused MATLAB VTA tests:

```bash
conda run -n leaddbs matlab -batch +  "addpath(genpath('/Users/mojackhu/Github/leaddbs')); +   r=testsuite('my_helper/fiber/tests','IncludeSubfolders',false); +   assertSuccess(run(r));"
```

Expected: all existing and new tests pass without FEM.

- [ ] **Step 5: Commit**

Stage only the explicit MATLAB files from this task and commit:

```bash
git commit -m "feat: time canonical VTA stages"
```

### Task 6: Create The Frozen Benchmark Fixture And Harness

**Files:**
- Create: `my_helper/vta/test/fixtures/vta_performance_benchmark_v1.json`
- Create: `my_helper/vta/test/run_vta_performance_benchmark.py`
- Create: `my_helper/vta/test/test_run_vta_performance_benchmark.py`
- Modify: `my_helper/vta/test/README.md`

**Interfaces:**
- CLI modes: `validate`, `prepare`, and `run-baseline`.
- Required arguments for modes that touch files:
  `--study-base`, `--vta-model`, `--work-root`.
- Benchmark command construction always uses three workers. Candidate binding
  remains deferred until the persistent subject runner exists.

- [ ] **Step 1: Write RED harness tests**

Use temporary fake subject trees and fake command runners. Prove:

- fixture schema and every selector resolve uniquely;
- current payload is exactly:

```json
{
  "case_id": "R_single_cathode_case_return",
  "hemisphere": "R",
  "design": "single_cathode_case_return",
  "control_mode": "current",
  "unit": "mA",
  "amplitude_mA": 4.7761121690289734,
  "pulse_width_us": 90,
  "frequency_hz": 130,
  "contacts": [
    {"contact": 4, "polarity": "cathode", "fraction": 1.0},
    {"contact": "case", "polarity": "anode", "fraction": 1.0}
  ]
}
```

- synthetic continuous multi-source payload uses two voltage sources at
  130 Hz, 2.0 V, 60 us, with contacts 1 and 2 as separate cathodes and case
  return;
- threshold repair removes only all 180/200/220 V/m native and MNI masks for
  SNr003 T1/program 1/lead-R/group-1 and retains both E-fields;
- complete resume retains every expected artifact;
- selected and donor leaves reset before every measured run;
- the reusable future paired-order schedule is B/C, C/B, B/C, C/B, B/C after
  one warm-up per path;
- expected process/solve/derive/copy/skip counts are asserted;
- any path under the authoritative derivatives root is rejected;
- replaced untracked benchmark outputs move to Trash rather than being
  overwritten.

- [ ] **Step 2: Verify RED**

```bash
/opt/anaconda3/envs/leaddbs/bin/python -m pytest +  my_helper/vta/test/test_run_vta_performance_benchmark.py -q
```

Expected: harness import failure.

- [ ] **Step 3: Write the exact fixture**

Use schema `vta_performance_benchmark_v1`. Store semantic selector IDs rather
than absolute-path-dependent canonical task IDs. The harness materializes the
frozen snapshot, resolves canonical IDs, records them in validation output, and
fails unless each selector resolves exactly once. Include both spaces and
thresholds `[180, 200, 220]`.

- [ ] **Step 4: Implement safe snapshot and paired-run behavior**

The harness creates:

```text
vta_performance_benchmark_<timestamp>/
  fixture.json
  frozen_input/
  working/baseline/
  working/candidate/
  runs/
  benchmark_summary.json
```

Each run restores from `frozen_input` before starting. It never deletes an
untracked prior root; conflicting roots or files move to Trash. Validation and
unit tests invoke no MATLAB. `run-baseline` is explicit and may start the
fixed FEM suite only when the user runs that command.

- [ ] **Step 5: Verify GREEN and commit**

```bash
/opt/anaconda3/envs/leaddbs/bin/python -m pytest +  my_helper/vta/test/test_run_vta_performance_benchmark.py +  my_helper/fiber/core/vta_pipeline/tests -q
```

```bash
git add +  my_helper/vta/test/fixtures/vta_performance_benchmark_v1.json +  my_helper/vta/test/run_vta_performance_benchmark.py +  my_helper/vta/test/test_run_vta_performance_benchmark.py +  my_helper/vta/test/README.md
git commit -m "test: add reproducible VTA performance benchmark"
```

### Task 7: Close The First Slice

**Files:**
- Modify: `my_helper/fiber/vta_compute_performance_optimization_plan.md`
- Modify: `docs/superpowers/specs/2026-07-13-vta-performance-optimization-design.md`
- Modify: `.planning/vta-performance-optimization/progress.md` when present

- [ ] **Step 1: Run the solver-free acceptance suite**

```bash
/opt/anaconda3/envs/leaddbs/bin/python -m pytest +  my_helper/fiber/core/vta_pipeline/tests +  my_helper/vta/test/test_run_vta_performance_benchmark.py -q
```

```bash
conda run -n leaddbs matlab -batch +  "addpath(genpath('/Users/mojackhu/Github/leaddbs')); +   r=[testsuite('my_helper/fiber/tests/test_vta_event_protocol.m'), +      testsuite('my_helper/fiber/tests/test_vta_canonical_task_contract.m'), +      testsuite('my_helper/fiber/tests/test_vta_common_grid_export.m')]; +   assertSuccess(run(r));"
```

- [ ] **Step 2: Validate the benchmark fixture without FEM**

```bash
/opt/anaconda3/envs/leaddbs/bin/python +  my_helper/vta/test/run_vta_performance_benchmark.py validate +  --study-base /Volumes/VAL/STNSNr/summary/cohort/subj/study_base.json +  --vta-model /Volumes/VAL/STNSNr/config/spot/vta_model.yaml
```

Expected: all semantic selectors resolve once and no file is written.

- [ ] **Step 3: Run repository checks**

```bash
git diff --check
git status --short --branch
git diff --name-only -- docs/superpowers/specs/2026-07-13-mrtrix-seed-target-yaml-cli-design.md
```

Expected: the MRtrix diff command prints nothing.

- [ ] **Step 4: Update status wording**

Mark only telemetry and baseline harness as implemented. Keep persistent
subject execution, local output optimizations, caches, FEM reuse, the 25%
performance gate, and the default-worker change as pending.

- [ ] **Step 5: Commit the slice documentation**

Stage only the two VTA performance documents and the ignored local progress
file if it is intentionally tracked. Commit:

```bash
git commit -m "docs: record VTA telemetry baseline"
```

## Self-Review

- Spec coverage: event framing, parser grammar, task outcomes, synchronized
  memory, stage timing, frozen reset, paired repetitions, current fixture,
  no-authoritative-write safety, and solver-free validation are assigned.
- Deferred correctly: persistent subject runner, donor/state-machine behavior,
  bulk thresholds, bounded interpolation, duplicate-load removal, caches, FEM
  reuse, final three-worker default, and full FEM benchmark execution.
- Type consistency: `ProcessObservation`, `StageTiming`, `TaskOutcome`,
  and `MemoryObservation` have one definition and are reused by the bridge and
  benchmark.
- No production MRtrix file is in the file map or any staging command.
