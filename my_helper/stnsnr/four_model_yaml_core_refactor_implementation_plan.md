# Four-Model YAML Core Refactor Implementation Plan

> **Historical predecessor only.** The authoritative implementation plan is
> `my_helper/stnsnr/dual_frequency_core_decoupling_implementation_plan.md` and
> the current performance contract is
> `my_helper/stnsnr/four_model_shared_exposure_performance_refactor_plan.md`.
> Every checksum/content-addressed cache, endpoint-specific physical exposure,
> thread-pool scheduling, final-axis-only OSS, or model-specific jitter rule in
> this file is superseded. Do not implement or validate the current target from
> this historical plan.

## Study-Base Frequency Migration Addendum

The configured runner must use `study_base.json` as its only project data
input. Raw source components are `target_stn` and `target_snr`; HF/ULF is
derived only from source-level `frequency_hz` and the strict intervals in
`spot_model.yaml`. The workflow no longer loads project clinical or stimulation
workbooks through `study.yaml`. Runtime writes source-level frequency QC inside
the run directory and summary counts into the existing run manifest; no
independent resolved manifest is created.

> **For agentic workers:** Implement task-by-task with test-first red/green
> cycles. Subagents are permitted for bounded responsibilities with disjoint
> file ownership; the main thread reviews and integrates every change.

**Goal:** Implement `four_model_yaml_core_refactor_plan.md` end to end and pass
the named MDS-UPDRS III plus MDS-UPDRS IV acceptance.

**User-confirmed normative-fiber scoring design:**
`normative_fiber_minimum_count_scoring_design.md`. Explicit user decisions
govern; this and other Markdown files are implementation records rather than
independent authorities.

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
- The configured run root is an internal execution store, not the stable
  downstream interface. Direct-voxel publication must follow
  `config/four_model_v1/direct_voxel_output_contract.md` and materialize under
  `<direct_voxel_model.output.root>/direct_voxel/<model_set_id>/<scale_id>/`.
- Normative-fiber publication must follow
  `config/four_model_v1/normative_fiber_output_contract.md` and materialize
  under
  `<normative_fiber_model.output.root>/normative_fiber/<model_set_id>/<scale_id>/`.
- Direct-voxel publication stores selected-source and candidate-branch
  artifacts once. `final_model.json` references the realized model and never
  duplicates its maps, scores, predictions, or weights.
- Configured direct-voxel and normative-fiber internals must be renamed end to end from legacy
  HF/ULF terminology to `reference`, `addon`, `no_delta_reference`,
  `delta_reference_adjusted`, and `DeltaReferenceScore`. This applies to module
  names, classes, functions, dataclasses, fields, status records, artifact
  kinds, tests, and publisher paths. Boundary-only translation is prohibited.
  Temporary legacy entrypoints may survive only in an isolated compatibility
  package and cannot define configured internal state.
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
- [ ] Resume restores every completed task's non-manifest `TaskArtifact` from
  the run-local artifact index with exact path and SHA-256 validation. This is
  required when a later task executes after an interrupted run and consumes a
  completed sidecar. Missing or hash-drifted producer artifacts invalidate
  reuse and cause that producer task to run again; resume must never reconstruct
  a completed result with facts but an empty artifact tuple.
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
  `B=1000`, seed 42, fiber percentages, public normative-fiber cheap sensitivity
  (`tau=1500`, `Coverage>=5`, sweet top 1500, sour top 500), controls, OSS, and
  reporting policy.
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

Every configured service stage must also satisfy the planner artifact contract
for that exact Round. Analysis-native filenames are not executor artifact
kinds. The adapter must write or translate them into the declared kinds, such
as `sidecar_index` plus `qc`, `observed_metrics` plus
`loocv_predictions`, or `source_status` plus `selected_source`, inside the
task-local output root. A service must not return `completed` for readiness,
sidecar, control, sensitivity, resolver, or reporting work when any declared
artifact is absent. This requirement is tested through `execute_plan`, not only
through isolated runner tests.

- [ ] RED: endpoint, phase, brainmask, connectome, grid, output root, and force/
  resume are explicit; names reflect actual selected tau/Coverage; no default
  scale/connectome is read inside services.
- [ ] Characterize A exposure/resolver arrays and B fiber IDs/order/scoring.
- [ ] GREEN: retain numerical kernels, add typed A/B requests, phase-aware B
  stimulation selection, dynamic names, and task-local configured outputs.
- [ ] Add executor-level A/B integration tests proving that each executable
  observed Round emits every `TaskSpec.expected_artifact_kinds` entry and that
  all returned paths are files below the configured run root.
- [ ] Preserve legacy wrappers through `LegacyArtifactStore`; run exact
  equivalence and commit `refactor: parameterize HF observed services`.

## Task 10: Parameterize C/D With Explicit HF Records

**Files:** Extend observed services/tests; modify C/D modules behind tests.

```python
@dataclass(frozen=True)
class ArtifactRef:
    task_id: str
    kind: str
    relative_path: str
    sha256: str
    shape: tuple[int, ...] = ()

@dataclass(frozen=True)
class HFSourceRecord:
    resolver_task_id: str
    endpoint_model_id: str
    source_status: str
    prediction_status: str
    selected_tau: float | None
    selected_coverage: int | None
    subject_order: tuple[str, ...]
    feature_axis: FeatureAxisRef | None
    artifacts: tuple[ArtifactRef, ...]
    record_hash: str

@dataclass(frozen=True)
class DeltaHFBundle:
    input_status: str
    support_status: str
    selected_hf_tau: float | None
    selected_hf_coverage: int | None
    full_scores: ArtifactRef | None
    fold_scores: ArtifactRef | None
    support_rows: ArtifactRef | None
```

`DeltaHFBundle.input_status` is successful for both `adequate` and `limited`
support, with the limitation retained in `support_status`; extreme
out-of-support or missing/full/fold artifacts are invalid. Adjusted nuisance
always consumes both the full-score vector and fold-by-subject score matrix.
The shared support classifier uses the authoritative thresholds: cohort median
out-of-support fraction `> 0.50`, more than 25% of subjects `> 0.80`, or any
required subject/LOOCV fold `> 0.95` is
`invalid_extreme_out_of_support`. Zero required suprathreshold HF-component
coverage/exposure is invalid and can never be classified `adequate`.

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

```python
@dataclass(frozen=True)
class FormalRequest:
    task: TaskSpec
    final: FinalArtifactRecord
    output_root: Path
    permutations: int
    bootstraps: int
    seed: int
```

The request's `final.nuisance` is authoritative. `delta_hf_adjusted` always
loads both full and fold-specific DeltaHFScore artifacts identified by the
matching `DeltaHFBundle`; `no_delta_hf` never discovers or injects Delta by
filename. Formal output facts may report inference status but cannot emit new
source/prediction/final classification fields.

- [ ] RED: targets use immutable final records, selected tau/Coverage, final
  branch manifest, and branch-specific nuisance columns including DeltaHFScore.
- [ ] Assert one formal target per configured scale, PPMI/MGH `sensitive`
  connectomes never become final, local failures, and no classification
  feedback.
- [ ] GREEN: parameterize target factories and reuse per-target permutation/
  bootstrap kernels after exact equivalence; commit
  `refactor: make formal targets endpoint aware`.

## Task 12: Sensitivity And Reporting Services

**Files:** Create `services/sensitivity.py`, `services/reporting.py`, and tests;
modify jitter/OSS/reporting only behind failing tests.

```python
@dataclass(frozen=True)
class SensitivityRequest:
    task: TaskSpec
    final: FinalArtifactRecord
    delta_hf: DeltaHFBundle | None
    output_root: Path
    selected_tau_multipliers: tuple[float, float]
    jitter_resamples: int
    seed: int
    enabled_ulf_analyses: tuple[str, ...]
    component_exposures: tuple[ArtifactRef, ...]
    jitter_input_manifest: ArtifactRef | None
    matched_hf_final: FinalArtifactRecord | None
    y_base: ArtifactRef | None
    hf_overlap_tau: float | None
    rebuild_geometry: bool
    rebuild_delta_hf: bool
    rebuild_support_qc: bool
    rebuild_nuisance: bool

@dataclass(frozen=True)
class FinalLinkedArtifact:
    final_model_id: str
    final_record_hash: str
    artifact: ArtifactRef
```

Every reporting, OSS, jitter, FDR, density, and label artifact must carry the
same `final_model_id` and final-record hash as its request. Recursive filename
matches, branch substrings, and global model IDs are invalid provenance.

`jitter_resamples`, `jitter_translation_fwhm_mm`, and `seed` come from each
public model profile. The enabled
ULF analysis tuple is derived from the public sensitivity switches. Artifact
references and matched records are immutable runtime inputs with validated
hashes. `jitter_input_manifest` is mandatory for jitter; ULF jitter also
requires the matched HF final record and branch-specific `Y_base`. The selected
HF-overlap tau is carried explicitly whenever ULF exposure must be rebuilt.
Voxel and normative-fiber jitter remain independent executions. They may use
the same numeric seed, resample count, and FWHM, but the implementation does
not create a shared cross-domain perturbation schedule or exposure cache.
Within each model family, scale-independent source geometry and checkpoint
state may still be reused when scientific identity and subject order match.

The run-local jitter manifest uses one of two strict geometry schemas. Direct
voxel tasks declare `builder = direct_efield_resample_v1`, the final candidate
XYZ artifact, and endpoint-ordered hashed sampling rows. ULF direct tasks also
declare HF- and ULF-component rows; finite HF overlap additionally declares the
matched HF candidate XYZ, the full right-brainmask support XYZ, the matched-HF
candidate indices in that support, and HF-reference rows. Normative-fiber tasks
declare `builder = normative_fiber_efield_resample_v1`, the configured
connectome `data.mat`, and the corresponding endpoint-ordered HF-reference or
HF/ULF-component sampling rows. Every referenced file carries an exact path and
SHA-256 digest. The registry derives these entries only from immutable endpoint
task records and the configured study profile; it never selects a latest legacy
output.

For DeltaHFScore support rebuilt during jitter, the extreme subject/fold rule
is strictly `out_support_fraction > 0.95`. Equality at `0.95` does not trigger
`invalid_extreme_out_of_support` unless another invalid-support criterion is
met.

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
- [ ] Add one production `build_default_service_registry` factory used by the
  generic CLI. It binds A/B/C/D observed, qualification, formal, sensitivity,
  OSS, and reporting services from the resolved run context; an empty registry
  is permitted only when tests inject it explicitly.
- [ ] Generate ULF component availability as a hash-validated run-local shared
  sidecar from the configured stimulation table and Lead-DBS derivatives. Both
  ULF model families reuse that exact artifact. Production configured execution
  must not discover the latest legacy readiness CSV under a summary directory.
- [ ] Convert wrappers to typed requests. Generic CLI exposes no scale default or
  candidate threshold; compatibility-only legacy flags remain explicitly labeled.
- [ ] Run optimized-versus-brute-force and old-versus-new deterministic
  equivalence for A/B/C/D/formal kernels plus every old selftest.
- [ ] Commit `refactor: route legacy wrappers through model services`.

## Task 14: Final Acceptance

### Acceptance Run Ledger

- `20260710T052812Z_f502386305c1044c`: stopped during observed execution and
  retained as failed audit evidence. HF direct Round 1 exposed an adapter
  contract error: the production registry passed the five-argument MATLAB flip
  implementation where the configured HF direct backend requires a callback
  accepting only `side_paths`, `preprocess_dir`, and `force`. This run is not an
  acceptance result and must not be resumed. The registry adapter must bind the
  configured `asset_root` and `matlab_bin`, pass a contract test, and then start
  a fresh run ID.
- `20260710T053236Z_bd038a13c80b9c1c`: stopped during the first HF direct
  MATLAB flip after an independent pre-acceptance audit found unresolved
  sensitivity/control correctness defects. No terminal scientific result from
  this run is accepted, and the run must not be resumed.

### Pre-Acceptance Correctness Audit

The following findings must be closed before the next real run:

1. Validate direct feature axes by file hash and normative-fiber axes by their
   declared logical array-identity hash; do not compare incompatible hash
   definitions.
2. Jitter DeltaHFScore support must evaluate the complete
   `n_folds x n_subjects` out-of-support matrix. The strict `> 0.95` rule applies
   to every required pair, not only the held-out diagonal. A value exactly equal
   to `0.95` remains within the accepted boundary and does not trigger the
   extreme out-of-support failure.
3. A realized `no_delta_hf` final may still run the non-final adjusted
   sensitivity when the endpoint-local DeltaHFScore bundle is valid. The bundle
   must be loaded through the exact ULF sidecar/lock provenance, not inferred
   from the final nuisance plan.
4. Direct and normative-fiber jitter must report spatial robustness, including
   map correlation, support overlap, sign consistency, and map-variability
   summaries, in addition to LOOCV metrics.
5. ULF normative-fiber plain/burden controls must implement the documented
   touched-candidate plain exposure, branch-specific nuisance comparisons, and
   HF out-of-support burden; descriptive raw-axis summaries alone are not a
   completed control task.
6. Support sensitivity parsing must accept the typed direct and fiber support
   row schemas and include fold maxima.
7. ULF sensitivity must resolve the exact matched HF source through the
   endpoint's `input_hf_lock` record and verify source hash, tau/Coverage,
   subject order, feature axis, and connectome before using HF-derived inputs.
8. Fiber jitter sampling provenance requires exactly one R and one L row for
   every subject, including intentionally empty sides; duplicate empty rows are
   invalid.
9. Resume must validate files referenced inside strict jitter manifests, not
   only the outer manifest hash. Long jitter execution must use atomic,
   final-hash/seed/method-keyed replicate progress so an interrupted task can
   resume without accepting partial or stale results. The checkpoint identity
   must include the immutable final-record hash, seed, FWHM, requested replicate
   count, method version, and strict jitter-input-manifest hash. It atomically
   stores completed replicate rows plus streaming spatial state; recovery may
   continue only from an exact identity match and must regenerate the final
   summary/artifacts rather than treating the checkpoint itself as completion.
10. Configured OSS must use the realized final selected-source candidate fiber
   axis, not the full parent dTOR exposure axis. Candidate IDs are derived from
   the immutable final exposure with its selected tau/Coverage, and
   `oss_fiber_ids.npy` must equal that ordered subset exactly. The OSS matrix
   shape is therefore `n_subjects x n_selected_candidate_fibers`; the parent
   feature axis remains provenance only. A full-parent-axis equality check is a
   contract violation and must be rejected by tests.

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
