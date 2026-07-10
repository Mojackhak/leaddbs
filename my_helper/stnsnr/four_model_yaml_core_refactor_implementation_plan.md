# Four-Model YAML Core Refactor Implementation Plan

> **For agentic workers:** Implement task-by-task with test-first red/green
> cycles. Subagents are permitted for bounded responsibilities with disjoint
> file ownership; the main thread reviews and integrates every change.

**Goal:** Implement `four_model_yaml_core_refactor_plan.md` end to end and pass
the named MDS-UPDRS III plus MDS-UPDRS IV acceptance.

**Architecture:** Add an isolated `my_helper/fiber/core/outcome_models/` package
for strict profiles, immutable identities, endpoint catalog, state machine, DAG,
run store, executor, service adapters, and reporting readers. Existing
`stnsnr_*` numerical kernels remain the computational base. Legacy wrappers
become compatibility adapters and stop owning configured-run identity/status.

**Tech Stack:** Python 3.11, dataclasses, argparse, unittest, PyYAML,
jsonschema Draft 2020-12, pandas/openpyxl, NumPy/SciPy, and Conda `leaddbs`.

## Global Constraints

- All configured scales use identical engineering paths. No production dispatch
  may branch on a scale label, total, axial, or the two acceptance scale IDs.
- Direct voxel uses the right-canonical brainmask; normative fiber uses the
  configured whole connectome. ROI, atlas, postprocessing, and GUI stay out.
- Public YAML/CLI rejects `candidate_threshold_v_per_m`, `smoke`,
  `smoke_iterations`, `primary_scale`, `first_pass_scale`, `axial_special`,
  `atlas`, `roi`, `postprocessing`, and per-scale scientific overrides.
- Direct `candidate_threshold_v_per_m` is `min(tau_grid_v_per_m)` and
  manifest-only.
- Formal/sensitivity outputs never modify model classification.
- Current `/Volumes/VAL/STNSNr/summary` outputs remain read-only. Configured runs
  use `<output_root>/configured_model_runs/<study_id>/<run_id>/`.
- Every production change requires a failing focused test first. All existing
  `stnsnr_*_selftest.py` tests must remain green.

## Planned File Layout

```text
my_helper/fiber/core/outcome_models/
  __init__.py
  config.py
  identity.py
  catalog.py
  state.py
  planner.py
  run_store.py
  executor.py
  cli.py
  schemas/{study_profile,scale_profile,model_profile,workflow}.schema.json
  services/{contracts,legacy_imports,observed,formal,sensitivity,reporting}.py
  tests/test_{config,identity,catalog,state,planner,run_store,executor_cli}.py
  tests/test_{observed_services,formal_sensitivity_services,two_scale_acceptance}.py
my_helper/fiber/config/stnsnr/four_model_v1/
  study_stnsnr.yaml
  scales_mds_updrs_iii_iv.yaml
  model_four_model_v1.yaml
  workflow_acceptance.yaml
my_helper/fiber/pipelines/run_configured_outcome_models.py
my_helper/fiber/stnsnr/run_stnsnr_configured_models_selftest.py
```

## Task 1: Strict Schemas And Typed Profiles

**Files:** Create `config.py`, schema files, package markers, config tests; modify
`my_helper/env/environment-leaddbs.yml` to declare `pyyaml` and `jsonschema`.

**Public interfaces:**

```python
@dataclass(frozen=True)
class WorkflowOverrides:
    scales: tuple[str, ...] = ()
    all_available: bool = False
    models: tuple[str, ...] = ()
    phases: tuple[str, ...] = ()
    connectomes: tuple[str, ...] = ()
    through: str | None = None

@dataclass(frozen=True)
class ResolvedWorkflow:
    study: StudyProfile
    scales: tuple[ScaleSpec, ...]
    model: ModelProfile
    workflow: WorkflowProfile
    configuration_hash: str
    source_paths: tuple[Path, ...]

def load_resolved_workflow(path: Path, overrides: WorkflowOverrides) -> ResolvedWorkflow: ...
```

- [ ] RED: load one valid four-profile fixture; reject unknown nested fields,
  duplicate YAML keys, no scale selection, scales/all conflict, unknown
  direction, `minimum_subjects != 12`, and every hidden parameter.
- [ ] Run `PYTHONPATH=my_helper/fiber/core conda run -n leaddbs python -m unittest outcome_models.tests.test_config -v`; expect import failure.
- [ ] GREEN: implement duplicate-key-safe loading, Draft 2020-12 validation,
  relative profile references, frozen conversion, override checks, and canonical
  config hashing.
- [ ] Re-run focused/full tests and commit `feat: add strict four-model YAML profiles`.

## Task 2: Composite Identities

**Files:** Create `identity.py` and `test_identity.py`.

```python
@dataclass(frozen=True, order=True)
class EndpointModelKey:
    study_id: str
    scale_id: str
    endpoint_phase: str
    model_family: str
    connectome: str = "none"

@dataclass(frozen=True, order=True)
class TaskKey:
    endpoint_model_id: str
    execution_stage: str
    branch: str = "none"
    source_reference: str = "none"
    replicate: str = "none"
```

- [ ] RED: prove canonical hashes are key-order independent and phase,
  connectome, branch, or source changes produce distinct IDs; display labels do
  not participate.
- [ ] GREEN: implement canonical JSON hashing plus endpoint/task/final-model IDs.
- [ ] Commit `feat: add endpoint and task identities`.

## Task 3: Endpoint Catalog

**Files:** Create `catalog.py`, `test_catalog.py`, and synthetic fixture helpers.

```python
class CatalogStatus(str, Enum):
    DATA_AVAILABLE = "data_available"
    INPUT_FAILURE = "input_failure"
    NOT_CONFIGURED = "not_requested_or_not_configured"

def build_endpoint_catalog(config: ResolvedWorkflow) -> tuple[EndpointRecord, ...]: ...
```

- [ ] RED: test A/B/C/D expansion, chronic/immediate pairing, same-scale HF
  reference, connectomes, omitted binding, missing columns/values, minimum
  subjects, duplicate subject-condition rows, and no cross-scale substitution.
- [ ] GREEN: implement profile-driven CSV/XLSX loading, strict columns,
  duplicate rejection, finite filtering, pairing, deterministic ordering, and
  endpoint-local terminal rows.
- [ ] Add read-only real-data assertions for the fresh clinical hash and allowed
  MDS-UPDRS III/IV counts; commit `feat: build endpoint catalog`.

## Task 4: Pure Source/Branch/Final State Machine

**Files:** Create `state.py` and `test_state.py`.

```python
def intended_ulf_branches(hf: SourceResult) -> IntendedBranches: ...
def realize_ulf_final(hf: SourceResult, branches: Mapping[str, BranchResult]) -> FinalModelDecision: ...
```

- [ ] RED: table-test every HF source/prediction state, invalid DeltaHFScore,
  invalid nuisance design, no-HF no-delta-only, accepted no-delta fallback,
  unstable intended branch, both branches absent, and exactly one final or
  `no_final_model`.
- [ ] Assert input/design failure precedes `absent_no_stable_grid`; an ordinary
  comparison branch is never promoted after an evaluable unstable primary.
- [ ] GREEN: implement pure transitions and characterize existing resolver
  behavior; commit `feat: add endpoint final-model state machine`.

## Task 5: Round-Aware DAG

**Files:** Create `planner.py` and `test_planner.py`.

```python
class DependencyRequirement(str, Enum):
    TERMINAL = "terminal"
    SUCCESS = "success"
    ACCEPTED_FINAL = "accepted_final"
    FORMAL_COMPLETE = "formal_complete"

@dataclass(frozen=True)
class DependencySpec:
    task_id: str
    requirement: DependencyRequirement

@dataclass(frozen=True)
class TaskGate:
    predicate: str

@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    key: TaskKey
    endpoint: EndpointModelKey
    round_name: str
    workflow_phase: str
    dependencies: tuple[DependencySpec, ...]
    gate: TaskGate
    expected_artifact_kinds: tuple[str, ...]

def compile_execution_plan(config: ResolvedWorkflow, catalog: Sequence[EndpointRecord]) -> ExecutionPlan: ...
```

- [ ] RED: map all executable Rounds from four summaries; enforce C-to-matched-A
  and D-to-matched-B/connectome; add HF dependencies automatically; reject
  cycles/missing edges; make `through` dependency-complete.
- [ ] Assert III immediate uses Round 2b and IV immediate creates no executable
  task. Use operation-specific `TaskKey.execution_stage` values so permutation,
  bootstrap, smoke, OSS, jitter, and report tasks cannot collide.
- [ ] RED: distinguish terminal, success, accepted-final, and formal-complete
  dependency requirements; compile conditional ULF branch/final tasks with
  explicit runtime gates. A failed or absent HF result must release no-delta,
  while adjusted requires valid DeltaHFScore inputs.
- [ ] Split ULF direct-voxel Round 8 sensitivity and endpoint-summary tasks;
  create no chronic-to-immediate edge. Attach OSS/jitter to either a primary or
  fallback realized final after formal completion.
- [ ] GREEN with deterministic standard-library topological sorting. Static
  skipped tasks retain immutable IDs and terminal skip records.
- [ ] Embed the immutable `EndpointModelKey` in each task record so plan/status
  artifacts remain directly auditable by study, scale, phase, family, and
  connectome without reverse-decoding a hash ID.
- [ ] Commit `feat: compile endpoint-aware four-model DAG`.

## Task 6: Run Store And Provenance

**Files:** Create `run_store.py` and `test_run_store.py`.

- [ ] RED: test UTC/hash run IDs, six required run artifacts, atomic writes,
  config/input/code hashes, subject/feature order, artifact indexing,
  interrupted tasks, identity-compatible resume, hash mismatch, force lineage,
  and read-only legacy roots.
- [ ] Require `workflow_resolved.yaml`, `endpoint_catalog.csv`,
  `execution_plan.json`, `task_status.csv`, `run_manifest.json`, and
  `artifact_index.csv` in every created run root.
- [ ] GREEN: implement atomic YAML/JSON/CSV writes, SHA-256 helpers, task/run
  manifests, indexes, and superseded-run links.
- [ ] Commit `feat: add configured run store`.

## Task 7: Executor And CLI

**Files:** Create `executor.py`, `cli.py`, `test_executor_cli.py`, and the thin
pipeline entry point.

```python
class ModelService(Protocol):
    def execute(self, task: TaskSpec, context: RunContext) -> TaskResult: ...

def execute_plan(plan: ExecutionPlan, context: RunContext, services: ServiceRegistry) -> RunResult: ...
```

- [ ] RED with deterministic in-process services: endpoint-local continuation,
  dependency skips, resume/force, one terminal state per task, and aggregate
  exits `0` success, `2` config, `3` planned input failure, `4` execution/no-final,
  `5` run lookup.
- [ ] Test `validate/plan/run/status/artifacts`, repeatable `--scale`, exclusive
  `--all-available`, no default scale, automatic HF dependencies, explicit
  `--output-root` for run lookup, `--models`, `--phases`, `--connectomes`,
  dependency-complete `--through`, and forbidden overrides.
- [ ] Define `run --resume --run-id RUN_ID`; define `run --force --run-id OLD`
  as a new run with supersession lineage. `status/artifacts` must resolve exactly
  one `<output-root>/configured_model_runs/*/<run-id>` match.
- [ ] Keep resume/force and prior-run IDs outside the configuration hash; they
  are lineage controls recorded by the run store.
- [ ] GREEN and commit `feat: add configured workflow CLI and executor`.

## Task 8: Committed v1 And Acceptance Profiles

**Files:** Create the four YAML profiles, `test_two_scale_acceptance.py`, and the
aggregate configured-model selftest wrapper.

- [ ] RED: validate profiles and assert real dry-run planning produces chronic
  A/B/C/D for both scales, immediate C/D only for III, and configured PPMI/MGH/
  dTOR roles without a scale-name production branch.
- [ ] GREEN: record current paths, brainmask, flip resolver, frequencies,
  E-field resolvers, connectomes, direct/fiber grids, hard filters, selected
  `0.9/1.1` sensitivity, formal `B=10000`, internal smoke `B=1000`, direct jitter
  `B=1000`, seed 42, fiber percentages, controls, OSS, and reporting policy.
- [ ] Commit `config: add STNSNr four-model v1 profiles`.

## Task 9: Parameterize A/B Observed Services

**Files:** Create service contracts/import adapter/observed service tests; modify
A/B modules only after characterization tests fail for the required interface.

```python
@dataclass(frozen=True)
class HFDirectVoxelRequest:
    endpoint: EndpointRecord
    clinical_table: Path
    stimulation_table: Path
    derivatives_root: Path
    brainmask: Path
    model_root: Path
    output_root: Path  # <model_root>/tasks/<task_id>
    tau_grid: tuple[float, ...]
    coverage_grid: tuple[int, ...]
    primary_tau: float
    primary_coverage: int
    candidate_threshold: float
    force: bool

@dataclass(frozen=True)
class HFNormativeFiberRequest:
    endpoint: EndpointRecord
    connectome: ConnectomeSpec
    clinical_table: Path
    stimulation_table: Path
    derivatives_root: Path
    model_root: Path
    output_root: Path  # <model_root>/tasks/<task_id>
    tau_grid: tuple[float, ...]
    coverage_grid: tuple[int, ...]
    primary_tau: float
    primary_coverage: int
    force: bool

@dataclass(frozen=True)
class FeatureAxisRef:
    ids_path: Path
    count: int
    sha256: str
    identity_source: str
```

Configured services write only below
`<run_root>/models/<endpoint_model_id>/`. Each stage writes to
`tasks/<task_id>/`; reusable sidecars live under a hash-keyed `cache/` directory
and require the atomic provenance checks below. Legacy wrappers retain their
current layout through a separate compatibility artifact store. Request
construction must not inspect a scale-name default, infer a connectome, or
derive a model parameter from output folder names.
Subject order may be embedded because the cohort is small. Voxel/fiber order
must use `FeatureAxisRef`; task JSON must not embed millions of feature IDs.
Sidecar reuse requires an atomic completion manifest matching subject order,
feature-axis hash, connectome/input fingerprint, matrix shape, and development
cap. File existence alone never authorizes reuse.

- [ ] RED: endpoint, phase, brainmask, connectome, grid, output root, and force/
  resume are explicit; names reflect actual selected tau/Coverage; no default
  scale/connectome is read inside services.
- [ ] Characterize A exposure/resolver arrays and B fiber IDs/order/scoring.
- [ ] GREEN: retain numerical kernels, add typed A/B requests, phase-aware B
  stimulation selection, dynamic names, and task-local configured outputs.
- [ ] Preserve legacy wrappers through `LegacyArtifactStore`; run exact
  equivalence and commit `refactor: parameterize HF observed services`.

## Task 10: Parameterize C/D With Explicit HF Records

**Files:** Extend observed services/tests; modify C/D modules behind tests.

- [ ] RED: C/D consume immutable matched `HFSourceRecord`, never global status;
  overlap and DeltaHFScore share selected HF tau; absent HF runs no-delta only;
  DeltaHF failure affects adjusted only; D never writes a mislabeled adjusted
  branch; configured immediate roles include MGH when selected.
- [ ] GREEN: classify branch input/design before source resolution, route final
  realization through `state.py`, preserve branch-specific nuisance/support QC,
  and write composite branch/final records.
- [ ] Run regression/equivalence and commit `refactor: parameterize ULF observed services`.

## Task 11: Endpoint-Aware Formal Services

**Files:** Create `services/formal.py` and formal service tests; modify target
discovery/readiness and kernels only where characterized hard-coding fails.

- [ ] RED: targets use immutable final records, selected tau/Coverage, final
  branch manifest, and branch-specific nuisance columns including DeltaHFScore.
- [ ] Assert one formal target per endpoint, PPMI/MGH robustness-only, local
  failures, and no classification feedback.
- [ ] GREEN: parameterize target factories and reuse per-target permutation/
  bootstrap kernels after exact equivalence; commit
  `refactor: make formal targets endpoint aware`.

## Task 12: Sensitivity And Reporting Services

**Files:** Create `services/sensitivity.py`, `services/reporting.py`, and tests;
modify jitter/OSS/reporting only behind failing tests.

- [ ] RED: ULF jitter rebuilds geometry, overlap, DeltaHFScore, support, and
  nuisance per jitter; selected source remains fixed.
- [ ] Test selected-source neighborhood, non-final branch, gain, total exposure,
  support, collinearity, plain/burden controls, top-k, cross-connectome, OSS
  frequency/candidate/order locks, FDR/density reporting, and non-feedback.
- [ ] GREEN: reporting reads catalog/task/final/artifact records only; OSS row
  failures propagate and locked frequency provenance is mandatory.
- [ ] Commit `refactor: add endpoint-aware sensitivity reporting`.

## Task 13: Legacy Wrapper Migration And Equivalence

- [ ] RED: characterize every legacy wrapper argument/output contract.
- [ ] Convert wrappers to typed requests. Generic CLI exposes no scale default or
  candidate threshold; compatibility-only legacy flags remain explicitly labeled.
- [ ] Run optimized-versus-brute-force and old-versus-new deterministic
  equivalence for A/B/C/D/formal kernels plus every old selftest.
- [ ] Commit `refactor: route legacy wrappers through model services`.

## Task 14: Final Acceptance

- [ ] Run deterministic accepted-final, `no_final_model`, and adjusted-input-
  failure/no-delta-fallback fixtures.
- [ ] Run two-scale `validate`, `plan`, then real `run --through report` in the
  configured namespace. Scientific no-final states are allowed only when exit,
  task status, manifest, and artifact index agree.
- [ ] Verify all six run artifacts, hashes, subject/fiber order, unique final,
  formal/sensitivity attachment, independent failure continuation, and
  read-only legacy outputs.
- [ ] Run all old/new tests, `git diff --check`, schema/forbidden-field/scale-
  hardcoding searches, and a requirement-by-requirement `/goal` audit.
- [ ] Move `.planning` files to Trash, commit without pushing, and mark the goal
  complete only after every evidence item passes.

## Standard Test Commands

```bash
PYTHONPATH=my_helper/fiber/core \
  /opt/anaconda3/bin/conda run -n leaddbs \
  python -m unittest discover \
  -s my_helper/fiber/core/outcome_models/tests -p 'test_*.py' -v

/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_configured_models_selftest.py

for test_file in my_helper/fiber/core/analysis/stnsnr_*_selftest.py; do
  /opt/anaconda3/bin/conda run -n leaddbs python "$test_file" || exit 1
done
```

## Completion Evidence

| Requirement | Evidence |
|---|---|
| Arbitrary/all scales, no privilege | Schema/CLI/catalog tests, source search, two-scale run |
| Four profiles and hidden fields | Draft 2020-12 tests and committed v1 profiles |
| Complete Round coverage | Planner tests against four Round matrices |
| HF-to-ULF matching/fallback | State/DAG tests and endpoint records |
| Unique final/formal attachment | Final records, DAG edges, formal manifests |
| Resume/force/provenance | Hash/supersession tests and run manifests |
| Current outputs unchanged | Namespace and filesystem audit |
| Full A/B/C/D execution | Two-scale task status and artifact index |
| Formal/sensitivity/report | Final-linked artifacts and non-feedback tests |
| MDS-UPDRS III/IV acceptance | Fresh hash, catalog, DAG, run status, reports |
