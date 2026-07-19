# Dual-Frequency Core Decoupling Implementation Plan

> **For agentic workers:** Subagents may be used for disjoint implementation or
> review tasks, but no local skill is required. Steps use checkbox (`- [ ]`)
> syntax for tracking.

**Goal:** Replace the STNSNr-oriented `four_model_v1` runtime adapters with a
strict, reusable `dual_frequency_v1` four-model core that can run from a
validated `study_base.json` without legacy or migration imports.

**Sole current `/goal`:**
`my_helper/stnsnr/four_model_yaml_core_refactor_plan.md`.

**Approved architecture:**
`my_helper/stnsnr/dual_frequency_core_decoupling_design.md`.

**Performance refactor contract:**
`my_helper/stnsnr/four_model_shared_exposure_performance_refactor_plan.md`.
**Task 17 decision record:**
`my_helper/stnsnr/task17_design_decisions.md`.
The generic core implementation below is complete, but the shared-exposure,
one-pass connectome, process-scheduler, direct-copy SHA cache, sensitivity
extension, and missing-parent rebuild work remains collectively
`implementation_in_progress`. Canonical main publication, final-in-sample
publication, and public-only postprocess are accepted. Jitter, OSS-DBS, and the
combined sensitivity extension remain outside the current execution phase by
explicit user instruction.

**Architecture:** Build a new `my_helper/fiber/core/dual_frequency` package next
to the predecessor package, migrate contracts and orchestration first, then
extract numerical backends one family at a time. Keep predecessor outputs
immutable, use bounded golden fixtures only for completed predecessor tasks, and
switch the production registry only after generic backends pass structural,
smoke, and applicable parity tests.

**Tech Stack:** Python 3.11, NumPy, SciPy, pandas, scikit-learn,
statsmodels, nibabel, PyYAML, jsonschema, unittest, Lead-DBS, and OSS-DBSv2.

## Global Constraints

- Work on the existing `stnvop` branch; do not create another worktree and do
  not push.
- Use the `leaddbs` Conda environment.
- Installing required packages into `leaddbs` is permitted. Add every new
  dependency to `my_helper/env/environment-leaddbs.yml` before installation,
  keep additions minimal, and record the resolved version in run provenance.
- Update relevant documentation before each code phase.
- Before Task 1, require the authoritative `/goal` status
  `goal_review_passed`, verify `git status --short` is empty, and do not begin
  from an uncommitted documentation baseline.
- Add focused tests with each implementation phase and run relevant regression
  tests before commit. Strict RED/GREEN ordering is not required.
- All code, identifiers, comments, docstrings, schemas, and generated field
  names are English.
- Runtime roles are `reference_component` and `addon_component`; generic code
  must not dispatch on STNSNr, HF, ULF, STN, STN+SNr, dTOR, or scale names.
- Generic CLI, service, workflow, backends, cache, and reporting must not import
  any module under `my_helper.fiber.projects.stnsnr`. The existing importer is
  an upstream `study_base.json` producer only.
- Scientific backends accept only typed requests, explicit arrays with declared
  axes, and `ArtifactRef` values. They must not accept untyped project paths,
  search directories, infer legacy filenames, or load raw project tables.
- Only config/study-base/artifact-store boundaries may receive explicitly
  supplied paths. No fixed STNSNr path is permitted.
- The core supports exactly reference-only and combined dual-frequency states;
  no add-on-only or N-frequency modeling.
- All configured scales are engineering-equivalent and no default scale exists.
- Every combined endpoint uses an explicit matched-reference binding; reference
  and combined phase IDs are not required to match.
- Normative-fiber `sensitive` connectomes emit `SensitiveRecord` only. Exactly
  one `formal` connectome is final-eligible; formal resampling, jitter, and
  endpoint OSS statistics derive from its realized final without a third
  connectome role. Raw OSS rows move before final realization only in Task 17's
  accepted `Omega_max` PASS branch; FAIL retains the final-linked producer.
- Direct voxel and normative fiber are the only model families.
- ROI/VTA postprocessing, regional heatmaps, GUI, HTTP, and upstream imaging/
  electrode reconstruction are out of scope.
- Preserve the existing mathematical estimators and the confirmed one-way
  fallback rule: accepted no-delta may replace failed intended adjusted after
  input, design, or source failure; adjusted never replaces failed intended
  no-delta; technical execution failure never triggers fallback.
- Formal, sensitivity, jitter, activation, and reporting cannot feed back into
  source, prediction, branch, or final-model classification.
- Public config never exposes direct-voxel candidate threshold or smoke counts.
- Expensive producer cache misses require explicit authorization; routine
  acceptance never implicitly authorizes them. Task 17's bounded real-OSS axis-
  equivalence decision matrix is a separate precondition, and each cold class
  may run only after its own explicit authorization.
- During the current implementation phase, production YAML may be validated
  and planned only. Do not execute its observed, formal, sensitivity, jitter,
  activation, or report tasks and do not write its configured output root.
  Runtime tests use deterministic synthetic fixtures or reviewed frozen
  read-only acceptance artifacts.
- Artifact-backed requests must match shape and exact ordered semantic axis IDs
  plus ordered ID files; formal requests declare a subject axis and activation
  requests inherit the realized final model's exact feature axis.
- Relative paths in `study_base.json` resolve against the JSON parent directory.
  Preserve and validate contact numbering/electrode order, contact ranges,
  uniqueness, and polarity-fraction closure without using component labels for
  frequency classification.
- Keep `configuration_id` for the complete effective run profile and a separate
  `scientific_profile_id` for task-content identity. Runtime locations,
  workers, resume/force, retries, and scheduling order must not alter
  scientific identity.
- `/Volumes/VAL/STNSNr/summary` and configured run
  `20260711T034644Z_d318f177f7f2ac7d` are immutable.
- Numerical parity covers only terminal completed, structurally readable scientific tasks
  from that run whose exact task IDs are in the reviewed frozen allowlist. Do
  not auto-enroll by status, resume the run, or compute unfinished paths for
  parity.
- Retain migration/acceptance tools after completion, but production modules and
  the default registry must not import them.

---

## Target File Map

```text
my_helper/fiber/core/dual_frequency/
  __init__.py
  contracts/
    __init__.py
    identity.py
    records.py
    requests.py
    study_base.py
  config/
    __init__.py
    loader.py
    models.py
    schemas/
      direct_voxel_model.schema.json
      normative_fiber_model.schema.json
      study_base.schema.json
      workflow.schema.json
  catalog/
    __init__.py
    builder.py
  workflow/
    __init__.py
    state.py
    planner.py
    executor.py
    run_store.py
    registry.py
  application/
    __init__.py
    service.py
    cli.py
  cache/
    __init__.py
    identity.py
    store.py
  backends/
    __init__.py
    protocols.py
    direct_voxel/
      kernel.py
      source_resolver.py
      reference.py
      addon.py
    normative_fiber/
      coverage.py
      scoring.py
      reference.py
      addon.py
    delta_reference/
      direct_voxel.py
      normative_fiber.py
    interaction/
      branch_resolver.py
      reference_overlap.py
    formal/
      direct_voxel.py
      normative_fiber.py
    sensitivity/
      tau_neighborhood.py
      spatial_jitter.py
      addon_exposure.py
      fiber_controls.py
    activation/
      canonical_mapping.py
      ppam.py
      ossdbs.py
  reporting/
    endpoint_summary.py
    artifact_index.py
    run_report.py
  tests/

my_helper/fiber/projects/stnsnr/
  __init__.py
  migration/
    __init__.py
    convert_four_model_v1.py
  acceptance/
    __init__.py
    build_bounded_fixture_manifest.py
    compare_bounded_fixtures.py
  legacy/

my_helper/fiber/pipelines/run_dual_frequency_models.py
my_helper/stnsnr/config/four_model_v1/
  direct_voxel_model.yaml
  direct_voxel_model_test.yaml
  normative_fiber_model.yaml
  normative_fiber_model_test.yaml
  workflow.yaml
```

The predecessor `my_helper/fiber/core/outcome_models` remains unchanged until
Task 15 switches the default entrypoint/registry and isolates legacy code.

## Numerical Extraction Map

The implementation extracts these verified predecessor functions into generic
array-in/record-out modules. Preserve formulas and tests; remove project I/O,
argument parsing, output discovery, and project naming.

| Generic target | Predecessor functions to extract |
|---|---|
| Reference direct source resolver | `row_passes_hard_filters`, `select_best_grid_cell`, `evaluate_grid_cell` from `stnsnr_hf_direct_voxel_posthoc_threshold_scan.py` |
| Reference fiber exposure/score/resolver | `reduce_point_values_to_fiber_peaks`, `normative_fiber_hard_computability_passes`, `resolve_normative_fiber_source`, `fixed_count_fiber_net_score`, `run_observed_loocv`, `evaluate_normative_fiber_grid_cell` from `stnsnr_hf_normative_fiber_smoke.py` |
| Add-on direct | `fit_baseline_with_covariates`, `delta_hf_scores_from_map`, `fit_hf_delta_full`, `fit_hf_delta_fold`, `compute_branch`, `evaluate_ulf_direct_grid_cell`, `resolve_ulf_direct_branch` from `stnsnr_ulf_direct_voxel_observed.py` |
| Add-on fiber | `apply_ulf_only_fiber_rule`, `delta_hf_fiber_scores_from_weights`, `fit_hf_delta_full`, `fit_hf_delta_fold`, `run_ulf_fiber_branch`, `evaluate_ulf_norm_fiber_grid_cell`, `resolve_ulf_norm_fiber_branch` from `stnsnr_ulf_normative_fiber_observed.py` |
| Direct formal | `build_fold_score_operators`, `direct_voxel_loocv_statistic`, `run_target_permutation`, `bootstrap_weights_for_sample`, `run_target_bootstrap` from the direct formal modules |
| Fiber formal | `prepare_candidate_union`, `build_fold_fiber_caches`, `normative_fiber_loocv_statistic`, `rank_columns_fast`, `residualize_complete`, `bootstrap_weights_for_sample`, `run_target_bootstrap` from the fiber formal modules |
| Jitter/neighborhood | `run_configured_neighborhood_sensitivity`, geometry/delta/branch fitter functions, and `run_configured_jitter` from the direct/fiber jitter modules |
| Add-on sensitivities | `compute_observed_sensitivity_branch`, `run_configured_additional_sensitivities`, `compute_observed_fiber_sensitivity_branch`, `run_configured_plain_burden_controls`, `run_configured_cheap_observed_sensitivity` |
| OSS fit | `_threshold_ppam`, `_estimable_oss_weight_mask`, `_build_oss_fold_caches`, `_loocv_oss`, `_full_sample_weights_scores` from `stnsnr_normative_fiber_oss_sensitivity.py` |

---

### Task 1: Freeze Bounded Acceptance Evidence And Retained Migration Tools

**Files:**
- Create: `my_helper/fiber/projects/__init__.py`
- Create: `my_helper/fiber/projects/stnsnr/__init__.py`
- Create: `my_helper/fiber/projects/stnsnr/acceptance/__init__.py`
- Create: `my_helper/fiber/projects/stnsnr/acceptance/tests/__init__.py`
- Create: `my_helper/fiber/projects/stnsnr/acceptance/build_bounded_fixture_manifest.py`
- Create: `my_helper/fiber/projects/stnsnr/acceptance/compare_bounded_fixtures.py`
- Create: `my_helper/fiber/projects/stnsnr/acceptance/approved_task_allowlist.json`
- Create: `my_helper/fiber/projects/stnsnr/acceptance/tests/test_bounded_fixture_manifest.py`
- Create: `my_helper/fiber/projects/stnsnr/migration/__init__.py`
- Create: `my_helper/fiber/projects/stnsnr/migration/tests/__init__.py`
- Create: `my_helper/fiber/projects/stnsnr/migration/four_model_v1_mapping.yaml`
- Create: `my_helper/fiber/projects/stnsnr/migration/convert_four_model_v1.py`
- Create: `my_helper/fiber/projects/stnsnr/migration/tests/test_convert_four_model_v1.py`
- Modify: `my_helper/stnsnr/four_model_execution_implementation_notes.md`

**Interfaces:**
- Produces: `build_fixture_manifest(run_root: Path, allowlist_path: Path, output_root: Path) -> Path`
- Produces: `compare_fixture(expected: Path, observed: Path) -> ComparisonResult`
- Produces: `convert_profiles(source_workflow: Path, mapping_path: Path, output_dir: Path) -> Path`
- Constraint: tools are manually invoked and never imported by runtime code.

- [x] **Step 1: Document the frozen task/artifact eligibility rule**

Add an implementation-note section naming the immutable run and stating:

```text
eligible when:
  task_id in approved_task_allowlist
  status in {completed}
  task has scientific artifacts
  every artifact exists and passes structural validation

excluded = task_id not in approved_task_allowlist
           or reports that only summarize failure
           or partial/failed/skipped/pending/unstarted tasks
```

- [x] **Step 2: Write failing fixture-manifest tests**

Create a temporary run with two completed scientific tasks, one completed
failure-report task, one failed task, and one missing artifact. Put only the
first completed scientific task in a temporary test allowlist, pass that
allowlist path explicitly, and assert no status-based auto-enrollment occurs:

```python
manifest = build_fixture_manifest(run_root, allowlist_path, output_root)
payload = json.loads(manifest.read_text(encoding="utf-8"))
self.assertEqual([row["task_id"] for row in payload["eligible_tasks"]], ["task_science"])
self.assertEqual(payload["source_run_id"], "frozen_run")
self.assertIn("task_completed_but_not_allowed", payload["excluded_tasks"])
self.assertIn("task_missing", payload["excluded_tasks"])
```

- [x] **Step 3: Run the failing tests**

Run:

```bash
conda run -n leaddbs env PYTHONPATH=my_helper/fiber \
  python -m unittest \
  projects.stnsnr.acceptance.tests.test_bounded_fixture_manifest -v
```

Expected: FAIL because the acceptance modules do not exist.

- [x] **Step 4: Implement deterministic manifest construction**

Read the static reviewed allowlist first, then `task_status.csv`; require the
immutable run identity from `run_manifest.json`, load only allowlisted task
manifests, validate every referenced artifact's existence/schema/shape/axes,
reject paths outside the run root, and write sorted JSON. Reject unknown,
duplicate, noncompleted, missing, or structurally invalid allowlist entries. Do
not discover additional tasks, run a producer, or repair missing files.

The result schema is:

```python
{
    "schema_version": "dual_frequency_bounded_fixture_v1",
    "source_run_id": run_id,
    "source_run_commit": commit,
    "configuration_hash": config_hash,
    "eligible_tasks": tuple(sorted(task_rows, key=lambda row: row["task_id"])),
    "excluded_tasks": excluded_reason_by_task,
}
```

- [x] **Step 5: Add the read-only comparison helper**

Implement exact comparisons for IDs/status/masks and `numpy.testing.assert_allclose`
for configured floating arrays. Return a structured result; never modify either
fixture.

- [x] **Step 6: Add old-YAML migration tests and implementation**

The converter uses an explicit project migration mapping. Python does not
hard-code predecessor period labels. Component roles, condition roles,
exposure bindings, and child subscale IDs are separate mapping sections:

```yaml
component_roles:
  <source-reference-component-key>: reference_component
  <source-addon-component-key>: addon_component
condition_roles:
  <source-reference-condition-key>: reference_only
  <source-combined-condition-key-a>: combined
  <source-combined-condition-key-b>: combined
exposure_bindings:
  <source-exposure-key>: {condition_role: combined, component_role: addon_component}
subscale_bindings:
  <source-endpoint-key>: {endpoint_binding_id: stable_child_id, condition_role: combined}
```

The converted study has one `reference_only` and one `combined` condition.
Distinct source-period labels become child subscale `endpoint_binding_id`
values under the same parent scale; they do not create additional core
conditions. Every combined child points to the same parent scale's reference
binding. Conflicting predecessor definitions for the shared combined
stimulation state fail conversion. Source labels may occur only as mapping-file
data and conversion-report evidence; target profiles contain no period field.

It writes draft `dual_frequency_v1` files plus a conversion report. Unknown
fields fail with `MigrationError`; the production loader is not imported.

- [x] **Step 7: Run focused tests and generate the frozen manifest**

Run the two test modules. Build and review
`approved_task_allowlist.json` from the immutable execution plan using only the
four completed scientific scopes named in the `/goal`; store exact task IDs,
expected stage, model family, endpoint, connectome role/ID, and artifact kinds.
Then generate a manifest from:

```text
/Volumes/VAL/STNSNr/configured_model_runs/stnsnr_frequency_addon/
20260711T034644Z_d318f177f7f2ac7d
```

Expected: only explicitly allowlisted, structurally valid completed scientific tasks are
eligible; every other terminal task has an exclusion reason; no process matching
`run_configured_outcome_models.py` starts.

- [x] **Step 8: Commit**

```bash
git add my_helper/fiber/projects my_helper/stnsnr/four_model_execution_implementation_notes.md
git commit -m "test: freeze bounded dual-frequency fixtures"
```

---

### Task 2: Add Generic Contracts And Strict Schemas

**Files:**
- Create: `my_helper/fiber/core/dual_frequency/__init__.py`
- Create: `my_helper/fiber/core/dual_frequency/contracts/__init__.py`
- Create: `my_helper/fiber/core/dual_frequency/contracts/identity.py`
- Create: `my_helper/fiber/core/dual_frequency/contracts/records.py`
- Create: `my_helper/fiber/core/dual_frequency/contracts/requests.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/__init__.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/protocols.py`
- Create: `my_helper/fiber/core/dual_frequency/config/__init__.py`
- Create: `my_helper/fiber/core/dual_frequency/config/models.py`
- Create: `my_helper/fiber/core/dual_frequency/config/loader.py`
- Create: `my_helper/fiber/core/dual_frequency/config/schemas/*.schema.json`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_config.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_records.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/__init__.py`

**Interfaces:**
- Produces: `load_workflow(path: Path, overrides: WorkflowOverrides) -> ResolvedWorkflow`
- Produces: immutable `EndpointKey`, `TaskKey`, `FinalModelKey`, `ArtifactRef`,
  `AxisRef`, `FeatureAxisRef`, `SourceRecord`, `ReferenceDependencyRecord`,
  `BranchRecord`, `FinalModelRecord`, `SensitiveRecord`,
  `DeltaReferenceBundle`, and `StudyBaseRecord`.
- Produces request/result contracts: `ObservedRequest`, `ObservedResult`,
  `FormalRequest`, `FormalResult`, explicit strategy-specific sensitivity
  requests, `SensitivityResult`, `ActivationRequest`, and `ActivationArtifact`.
- Produces narrow `ObservedBackend`, `FormalBackend`, `ActivationBackend`, and
  `ReportingBackend` protocols. Sensitivity strategies expose only their own
  typed `run(...)` contracts; there is no generic `SensitivityBackend` alias.

- [x] **Step 1: Write failing schema tests**

Tests must accept generic roles and reject:

```text
four_model_v1
frequency_1_reference
frequency_2_addon
candidate_threshold_v_per_m
smoke_permutations
unknown scale fields
missing --scale/all-available selection
```

- [x] **Step 2: Write failing immutable-record tests**

Use this interface:

```python
key = EndpointKey(
    study_id="synthetic",
    scale_id="scale_a",
    endpoint_binding_id="subscale_b",
    model_family="addon_fiber",
    connectome_id="connectome_x",
)
self.assertEqual(key.identifier, EndpointKey(**dataclasses.asdict(key)).identifier)
with self.assertRaises(dataclasses.FrozenInstanceError):
    key.scale_id = "changed"
```

Also assert an array `ArtifactRef` is rejected unless it declares `kind`,
`schema_version`, explicit `uri`, `dtype`, `shape`, ordered `axis_refs`, stable
semantic `axis_ids`, units/space where applicable, producer identity/version,
and terminal file status. Typed scientific requests must reject raw `Path`
fields and accept only arrays or artifact references for scientific inputs.

- [x] **Step 3: Run tests and verify RED**

```bash
conda run -n leaddbs env PYTHONPATH=my_helper/fiber/core \
  python -m unittest discover \
  -s my_helper/fiber/core/dual_frequency/tests \
  -p 'test_config.py' -v
```

Expected: import failure for `dual_frequency`.

- [x] **Step 4: Implement strict typed contracts**

Use frozen dataclasses and deterministic path-safe semantic identities. Generic
field names are mandatory:

```python
@dataclass(frozen=True)
class SourceRecord:
    endpoint: EndpointKey
    input_status: str
    source_status: str
    prediction_status: str
    selected_tau: float | None
    selected_coverage: int | None
    adjacent_support: int | None
    feature_axis: FeatureAxisRef | None
    artifacts: tuple[ArtifactRef, ...]
```

`ArtifactRef` is not a path alias. Its minimum contract is:

```python
@dataclass(frozen=True)
class ArtifactRef:
    kind: str
    schema_version: str
    uri: str
    dtype: str | None
    shape: tuple[int, ...] | None
    axis_refs: tuple[AxisRef, ...]
    axis_ids: tuple[str, ...]
    units: str | None
    space: str | None
    producer_id: str
    producer_version: str
    final_status: str
```

`ObservedRequest` and pre-final numerical kernels may contain typed records,
arrays, and `ArtifactRef` values. Final-linked `FormalRequest`, explicit
sensitivity-strategy requests, and `ActivationRequest` use immutable
identity-bearing artifacts where scientific order must be locked. No request
contains a raw project path, legacy filename, or unresolved YAML field. Define
backend protocols in the same task so planner, registry, and application code
cannot invent looser callable signatures before scientific extraction.

- [x] **Step 5: Implement three JSON Schemas and loader**

All schemas use `additionalProperties: false`. Cross-profile validation checks
scale order, endpoint pairs, frequency classes, connectome roles, minimum
subjects, model grids, output identity, and workflow selection. Derive:

```python
direct_candidate_threshold_v_per_m = min(direct_voxel.source.scan.tau_v_per_m)
```

Do not include the derived field in public serialized YAML.

- [x] **Step 6: Run focused and predecessor regression tests**

Run new config/record tests and the predecessor config/identity/record tests.
Expected: both suites pass; no predecessor file changes.

- [x] **Step 7: Commit**

```bash
git add my_helper/fiber/core/dual_frequency
git commit -m "feat: define dual-frequency contracts"
```

---

### Task 3: Implement Strict Study-Base Loading And Approved Profiles

**Files:**
- Create: `my_helper/fiber/core/dual_frequency/contracts/study_base.py`
- Create: `my_helper/fiber/core/dual_frequency/config/schemas/study_base.schema.json`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_study_base.py`
- Modify: `my_helper/stnsnr/config/four_model_v1/workflow.yaml`
- Modify: `my_helper/stnsnr/config/four_model_v1/README.md`

**Interfaces:**
- Produces: `load_study_base(path: Path) -> StudyBaseRecord`
- Produces: `validate_study_base(payload: Mapping[str, object]) -> None`
- Consumes the existing `dual_frequency_study_v1` JSON directly and never
  writes a transformed study artifact.

- [x] **Step 1: Write failing study-base loader tests**

Create minimal generic JSON fixtures with two subjects and two scales. Test
schema rejection, duplicate IDs, invalid directions, nonfinite observations,
invalid phase/program references, invalid source frequencies, and deterministic
subject/scale order. Assert the loader records the source path/schema version
and returns immutable records without writing another file.

- [x] **Step 2: Write failing cross-profile validation tests**

Assert direct-voxel and normative-fiber profiles have identical model-set ID,
output root, scale order, endpoint pair, frequency classes, minimum subjects,
and DeltaReferenceScore support thresholds. Every configured scale must exist
in the study base. Assert normative-fiber `formal` connectome count `> 0` and
`< 2`; the `sensitive` connectome list is optional.

- [x] **Step 3: Run tests and verify RED**

Run the study-base and config modules. Expected: missing generic study-base
loader and workflow schema support.

- [x] **Step 4: Implement read-only loading and semantic validation**

Validate schema, uniqueness, foreign keys, finite values, explicit order,
frequency-group closure, and scale directions. Load only the existing JSON;
do not create Parquet, a bundle directory, a study index, or a resolved study
manifest. The run manifest records the input path and schema version.

- [x] **Step 5: Finalize the three configured profiles**

Preserve the approved direct-voxel and normative-fiber scientific values.
Update `workflow.yaml` to reference those two profiles, expose no scale
defaults, and define execution/failure policy only. Keep MDS-UPDRS III and IV
as ordinary test selections in the test model profiles, not workflow defaults.

- [x] **Step 6: Run real read-only validation**

Validate `/Volumes/VAL/STNSNr/summary/cohort/subj/study_base.json` and both
production/test profile pairs without running a model or modifying source
files. Verify 16 subjects, 28 scales, and the configured endpoint pair.

- [x] **Step 7: Commit**

```bash
git add my_helper/fiber/core/dual_frequency/contracts \
  my_helper/fiber/core/dual_frequency/config/schemas \
  my_helper/fiber/core/dual_frequency/tests/test_study_base.py \
  my_helper/stnsnr/config/four_model_v1
git commit -m "feat: load canonical dual-frequency study base"
```

---

### Task 4: Implement Generic Identity And Endpoint Catalog

**Files:**
- Create: `my_helper/fiber/core/dual_frequency/catalog/__init__.py`
- Create: `my_helper/fiber/core/dual_frequency/catalog/builder.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_catalog.py`
- Modify: `my_helper/fiber/core/dual_frequency/contracts/identity.py`

**Interfaces:**
- Produces: `build_endpoint_catalog(config, study) -> tuple[EndpointRecord, ...]`
- Consumes: `ResolvedWorkflow`, `StudyBaseRecord`
- Every combined `EndpointRecord` contains exact
  `matched_reference_endpoint_id`; every normative-fiber record contains a
  validated connectome role.

- [x] **Step 1: Write failing catalog tests**

Cover all four model families, multiple connectome roles, multiple configured
scales, minimum subjects, unavailable rows, and scale equality. Assert the
synthetic profile has no project-frequency names in serialized catalog rows.
Include one explicit reference/add-on endpoint pair whose phases differ and
assert every configured scale uses that pair without automatic endpoint
discovery or fan-out. Assert sensitive connectomes declare `final_eligible`
false and the sole `formal` connectome declares `final_eligible` true.

- [x] **Step 2: Add the named III/IV structural fixture**

Assert MDS-UPDRS III and IV are both executable through the same configured
endpoint-pair factory, with no scale-name conditional in the builder.

- [x] **Step 3: Run tests and verify RED**

Expected: missing catalog module.

- [x] **Step 4: Implement study-base-driven catalog construction**

The builder filters canonical clinical rows by stable endpoint binding and
intersects explicit subject IDs. Combined dependencies resolve only through
`matched_reference_binding_id`; fiber dependencies also require exact
connectome ID. It never reads Excel or raw project paths.

```python
class CatalogStatus(str, Enum):
    DATA_AVAILABLE = "data_available"
    NOT_CONFIGURED = "not_configured"
    INSUFFICIENT_SUBJECTS = "insufficient_subjects"
```

- [x] **Step 5: Run focused tests and identity regression**

Expected: deterministic endpoint ordering and IDs under repeated builds;
reordering equivalent study-base rows does not change endpoint IDs.

- [x] **Step 6: Commit**

```bash
git add my_helper/fiber/core/dual_frequency/catalog \
  my_helper/fiber/core/dual_frequency/contracts/identity.py \
  my_helper/fiber/core/dual_frequency/tests/test_catalog.py
git commit -m "feat: build generic dual-frequency endpoint catalog"
```

---

### Task 5: Implement The Pure One-Way Fallback State Machine

**Files:**
- Create: `my_helper/fiber/core/dual_frequency/workflow/__init__.py`
- Create: `my_helper/fiber/core/dual_frequency/workflow/state.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_state.py`

**Interfaces:**
- Produces: `derive_branch_plan(reference: ReferenceDependencyRecord, delta_status: str) -> BranchPlan`
- Produces: `realize_final(branch_plan: BranchPlan, branches: Mapping[str, BranchRecord]) -> FinalDecision`

- [x] **Step 1: Write the exhaustive failing truth-table tests**

Include:

```text
matched reference binding missing -> dependency_failure, no branches
reference input/readiness failure -> dependency_failure, no branches
reference technical execution failure -> dependency_failure, no branches
reference input ready + absent_no_stable_grid -> no-delta only
reference predictive + Delta valid -> adjusted intended, both attempted
reference nonpredictive + Delta valid -> no-delta intended, both attempted
reference predictive + Delta invalid -> adjusted intended/input failure,
                                        no-delta attempted and fallback-eligible
reference nonpredictive + Delta invalid -> no-delta intended and attempted,
                                           adjusted not invoked
adjusted intended input/design/source failure + accepted no-delta -> fallback
no-delta intended failure + accepted adjusted -> no_final_model
intended technical failure + accepted alternate -> execution_failure
accepted intended + alternate technical failure -> intended remains final
```

- [x] **Step 2: Run tests and verify RED**

Expected: missing state module.

- [x] **Step 3: Implement pure state transitions**

Use no filesystem or NumPy dependency. `ReferenceDependencyRecord` separates
`dependency_status` (`ready`, `not_configured`, `input_failure`,
`design_failure`, `execution_failure`) from `source_status`. Only
Only `dependency_status` in `{"ready"}` can produce a branch plan. Accepted sources are
exactly:

```python
ACCEPTED = frozenset({"pre_specified_accepted", "scan_fallback_accepted"})
```

`dependency_status` in `{"ready"}` with `source_status` in
`{"absent_no_stable_grid"}` produces no-delta-only. Any nonready dependency
produces a terminal `dependency_failure` and no intended branch; it must never
be reinterpreted as source absence.

Fallback code must explicitly require:

```python
if (
    plan.intended_branch in {"delta_reference_adjusted"}
    and intended.status in {"input_failure", "design_failure", "absent_no_stable_grid"}
    and alternate.source_status in ACCEPTED
):
    return FinalDecision("no_delta_reference", "fallback_final", ...)
```

- [x] **Step 4: Run tests and mutation-style negative assertions**

Temporarily assert that adjusted would become fallback after failed intended
no-delta and confirm the assertion fails; restore the correct test.

- [x] **Step 5: Commit**

```bash
git add my_helper/fiber/core/dual_frequency/workflow/state.py \
  my_helper/fiber/core/dual_frequency/tests/test_state.py
git commit -m "feat: add dual-frequency final-model state machine"
```

---

### Task 6: Compile The Generic Round-Aware DAG

**Files:**
- Create: `my_helper/fiber/core/dual_frequency/workflow/planner.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_planner.py`

**Interfaces:**
- Produces: `compile_execution_plan(config, catalog) -> ExecutionPlan`
- Consumes: endpoint catalog and connectome roles.

- [x] **Step 1: Write failing DAG tests**

Assert:

- all four families are planned;
- add-on dependencies use explicit matched-reference endpoint IDs while the
  configured reference and add-on bindings remain distinct;
- normative-fiber add-on dependencies require exact connectome identity;
- sensitive connectomes stop at observed/formal-source-evaluation/report
  stages, emit `SensitiveRecord`, and have no final/formal/jitter/activation
  tasks;
- exactly one `formal` connectome is final-eligible;
- formal/activation tasks use connectome roles, not names;
- expensive activation producer tasks are statically visible;
- unavailable or insufficient rows at the fixed add-on binding produce
  terminal catalog/report tasks, not model tasks or endpoint substitution;
- no implicit additional-period or `Round 2b` task is generated; another
  assessment period requires another explicit endpoint-pair configuration;
- every scale receives the same task factory.

- [x] **Step 2: Run tests and verify RED**

Expected: missing planner module.

- [x] **Step 3: Implement typed tasks, gates, and topological ordering**

Use generic model families:

```text
reference_voxel
reference_fiber
addon_voxel
addon_fiber
```

Gates consume typed facts such as `source_accepted`, `delta_inputs_valid`,
`final_model_realized`, and `formal_complete`. False gates create explicit
terminal skipped records; they do not remove tasks from the plan.

Reference dependency failure creates an explicit add-on dependency-failure
record and closes all add-on branches. Ready reference input with
`absent_no_stable_grid` creates no-delta-only tasks. Connectome-role filtering
occurs before final realization so sensitive-connectome records cannot become
finals.

- [x] **Step 4: Compare the scientific task inventory with the `/goal` matrix**

Add a parameterized test asserting every non-deferred Round has
`task_stage_count > 0` and no optional future Round appears. Include add-on direct Round 9
display/final-manifest generation explicitly.

- [x] **Step 5: Commit**

```bash
git add my_helper/fiber/core/dual_frequency/workflow/planner.py \
  my_helper/fiber/core/dual_frequency/tests/test_planner.py
git commit -m "feat: compile dual-frequency workflow DAG"
```

---

### Task 7: Implement Scientific Cache, Run Store, And Executor

**Historical completion record.** The generic cache/executor was completed in
Task 7, but its endpoint-specific exposure, checksum, thread-pool, and wave-
barrier behavior is superseded and reopened by Task 17. Checked boxes in this
section do not mark the performance refactor complete.

**Files:**
- Create: `my_helper/fiber/core/dual_frequency/cache/__init__.py`
- Create: `my_helper/fiber/core/dual_frequency/cache/identity.py`
- Create: `my_helper/fiber/core/dual_frequency/cache/store.py`
- Create: `my_helper/fiber/core/dual_frequency/workflow/run_store.py`
- Create: `my_helper/fiber/core/dual_frequency/workflow/executor.py`
- Create: `my_helper/fiber/core/dual_frequency/workflow/registry.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_cache.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_executor.py`

**Historical interfaces:**
- Produces: `ScientificCacheKey`, `ContentAddressedCache`, `RunStore`,
  `ArtifactStore`, `ServiceRegistry`, and
  `execute_plan(plan, context) -> RunResult`.
- Task 17 replaces the target cache boundary with deterministic paths and
  existence/structural validation.

- [x] **Step 1: Write failing scientific-identity tests**

Assert scale, endpoint, run, workers, and retry changes do not alter an OSS row
key, while geometry, stimulation, component, transform, connectome, backend, or
scientific parameter changes do.

- [x] **Step 2: Write failing cache validation/reindex tests**

Exact IDs in different order may produce a view manifest after exact membership
validation. Changed/duplicate/missing IDs raise `CacheIdentityMismatch`.
Task 17 changes `ArtifactStore.materialize(ref)` to validate final-file
existence, dtype, shape, axes, units, space, and terminal status; a bare path
remains rejected.

- [x] **Step 3: Write failing executor tests**

Cover resume identity, endpoint isolation, false gates, required artifacts,
nonzero exit aggregation, and `ExpensiveProducerNotAuthorized` without invoking
a producer.

- [x] **Step 4: Historical atomic cache publication (superseded by Task 17)**

The historical implementation wrote a temporary sibling and atomically
published it with legacy integrity metadata. Task 17 retains portable payload
SHA, uses deterministic semantic paths plus one manifest, permits direct copy,
and verifies every used entry once per process.

- [x] **Step 5: Implement generic run store and executor**

Use the explicitly configured run root:

```text
<workflow.storage.run_root>/<study_id>/<run_id>/
```

Do not derive it from `model.output.root`; that separate path owns scientific
model artifacts and reports.

Before task execution, atomically write `configuration_resolved.yaml` containing
the canonical merged study/scale/model/workflow profiles and CLI overrides,
plus `configuration_sources.json` containing source URIs, semantic profile IDs,
and schema versions. Task 17 removes configuration checksums; the resolved
snapshot remains the run-local authority.

Validate every completed service result against declared artifact kinds and
keep all task outputs within run/cache roots.

- [x] **Step 6: Run focused and predecessor executor regressions**

Expected: generic tests pass; predecessor run store/executor tests still pass.

- [x] **Step 7: Commit**

```bash
git add my_helper/fiber/core/dual_frequency/cache \
  my_helper/fiber/core/dual_frequency/workflow \
  my_helper/fiber/core/dual_frequency/tests/test_cache.py \
  my_helper/fiber/core/dual_frequency/tests/test_executor.py
git commit -m "feat: execute cached dual-frequency workflows"
```

---

### Task 8: Add WorkflowService And Public CLI

**Files:**
- Create: `my_helper/fiber/core/dual_frequency/application/__init__.py`
- Create: `my_helper/fiber/core/dual_frequency/application/service.py`
- Create: `my_helper/fiber/core/dual_frequency/application/cli.py`
- Create: `my_helper/fiber/pipelines/run_dual_frequency_models.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_application_cli.py`

**Interfaces:**
- Produces: `WorkflowService.validate/plan/run/status/artifacts`
- Produces: CLI `main(argv: Sequence[str] | None = None) -> int`.
- `validate/plan/run` require `--study-base`, `--direct-voxel-model`,
  `--normative-fiber-model`, and `--workflow-profile`.
- `status/artifacts` require exact `--run-root`; no `latest` discovery.

- [x] **Step 1: Write failing service/CLI tests**

Test `--scale` repeatability, `--all-available` exclusivity, required selection,
dependency-complete `--through`, exact resume, force lineage, and explicit
`--allow-expensive-producers`. Execute the repository script in a subprocess
with `PYTHONPATH` removed and assert `--help` and explicit-profile `validate`
import successfully. Assert every missing study/model/workflow flag fails and
`status/artifacts` reject a nonexact or inferred run selector.

- [x] **Step 2: Run tests and verify RED**

Expected: missing application package and entrypoint.

- [x] **Step 3: Implement WorkflowService**

The service owns study-base/profile validation, catalog, planning, run-store
creation, registry construction, execution, and artifact lookup. CLI performs
argument parsing only.

- [x] **Step 4: Implement the thin entrypoint**

```python
#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


CORE_ROOT = Path(__file__).resolve().parents[1] / "core"
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from dual_frequency.application.cli import main

match __name__:
    case "__main__":
        raise SystemExit(main())
```

The bootstrap adds only the generic `core` directory. It must not add
`projects/stnsnr`, migration, acceptance, or legacy paths.

- [x] **Step 5: Run CLI smoke with an in-memory deterministic registry**

Execute `validate`, `plan`, and `run --through report` on a synthetic study base.
Run the public script directly with caller `PYTHONPATH` unset. Expected: generic
reports, no project/legacy imports, and no expensive process.

- [x] **Step 6: Commit**

```bash
git add my_helper/fiber/core/dual_frequency/application \
  my_helper/fiber/pipelines/run_dual_frequency_models.py \
  my_helper/fiber/core/dual_frequency/tests/test_application_cli.py
git commit -m "feat: expose dual-frequency workflow service"
```

---

### Task 9: Extract Reference Direct-Voxel Backend

**Current-phase execution boundary:** the production
`config/four_model_v1/direct_voxel_model.yaml` may be parsed, validated, and
planned, but it must not be executed in this task. Numerical verification is
restricted to deterministic synthetic arrays and explicitly frozen, bounded
reference-direct fixtures. The task must not launch production observed,
formal, sensitivity, jitter, OSS, or reporting work and must not write beneath
the production `output.root`.

**Files:**
- Modify: `my_helper/fiber/core/dual_frequency/backends/protocols.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/direct_voxel/kernel.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/direct_voxel/source_resolver.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/direct_voxel/reference.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_reference_direct_voxel.py`
- Test source: bounded completed reference-direct fixtures.

**Interfaces:**
- Produces: `ReferenceDirectVoxelBackend.run(ObservedRequest) -> ObservedResult`
- Produces pure LOOCV/grid/source functions with array inputs.
- `ObservedRequest` explicitly carries the endpoint outcome direction and the
  configured domain-appropriate hard-computability limits. Feature-count
  limits are optional at the shared request-contract level because voxel and
  fiber domains have different rules; the direct-voxel backend requires its
  full-sample and fold feature limits explicitly. No backend may infer these
  values from a scale name or replace YAML values with internal defaults.
- `ObservedRequest` also carries the expected exposure units and coordinate
  space. The reference direct-voxel backend requires continuous E-field
  magnitude in `V/m`, requires the exact declared feature-axis identity and
  coordinate space, and rejects any additional nuisance input: its only
  nuisance covariate is the separately declared baseline vector.
- Consumes scientific inputs only as request arrays or materialized
  `ArtifactRef` values through injected `ArtifactStore`; no path/glob argument.
- The backend receives an injected `ArtifactPublisher` that has already been
  scoped to the task output directory by the workflow service. Scientific
  backend public signatures do not receive raw output paths, and no backend
  discovers a project directory convention.
- Every published array/document has a persistent immutable metadata sidecar.
  Reuse requires byte identity and exact equality of kind, schema, ordered
  axes, units, space, producer ID, and producer version. Publication uses an
  exFAT-compatible same-directory exclusive publication lock followed by
  atomic rename. The implementation must not require hard links or
  platform-specific advisory locking. A same-name collision,
  orphaned lock, missing sidecar, or metadata mismatch is an error even when
  payload bytes are identical; stale state is never adopted automatically.
- The selected-source feature axis is the deterministic union of full-sample
  valid features and every fold-specific valid feature. Full and fold weights
  are projected onto that one axis with `NaN` where a feature is invalid for a
  particular fit. This preserves complete fold operators without using the
  full-sample outcome-derived validity mask to restrict any training fold.
- Fallback distance is Manhattan distance in declared grid-index steps, not a
  sum of values with incompatible tau and Coverage units. The complete order
  is grid-step distance, adjacent passing support, fold feature minimum,
  stricter Coverage, then higher tau.

- [x] **Step 1: Write failing synthetic kernel tests**

Cover hard computability, fold leakage, finite predictions, MAE/RMSE status, Q2/
rho report-only behavior, pre-specified acceptance, and scan fallback ordering.

- [x] **Step 2: Write failing bounded golden tests**

Load only the completed MDS-UPDRS III reference-direct task named in the frozen
bounded-fixture manifest. Validate the exact task ID and every consumed
artifact path/schema/shape/axis before reading it. Assert exact identity/source/tau/Coverage/
masks and allclose weights/scores/predictions. Direct reads from mutable legacy
summary paths do not count as bounded parity.

- [x] **Step 3: Run tests and verify RED**

Expected: backend missing.

- [x] **Step 4: Extract generic numerical functions**

Move mathematics out of
`stnsnr_hf_direct_voxel_posthoc_threshold_scan.py`; do not import that module.
Inputs include arrays, subject order, grid, model direction, and random settings.
Outputs are generic records and explicit artifacts.
Grid-cell records enforce internal invariants: hard-computability status equals
the conjunction of its declared hard checks, prediction status is applicable
only after hard computability passes, and finite/nonconstant flags cannot
contradict their underlying status fields.

- [x] **Step 5: Run focused, bounded parity, and predecessor selftests**

No ULF or MDS-UPDRS IV numeric parity is required in this task.
Any predecessor resolver fixture used here must contain adjacent passing-cell
count `> 1` to exercise the current stability rule;
a sparse fixture that cannot satisfy the stability rule is not a valid
selection-priority test.

- [x] **Step 6: Export the backend and commit**

The backend is exported from the generic backend package in this task. Its DAG
service adapter and production default-registry registration are completed in
Task 15, after the input-readiness and exposure-preparation services can build
an `ObservedRequest` entirely from typed dependency records. Do not register a
partial service that discovers inputs or YAML paths by itself.

```bash
git add my_helper/fiber/core/dual_frequency/backends \
  my_helper/fiber/core/dual_frequency/tests/test_reference_direct_voxel.py
git commit -m "feat: extract reference direct-voxel backend"
```

**Task 9 completion evidence (2026-07-15):**

- Generic dual-frequency suite: `115 passed, 57 subtests passed`.
- Focused records/cache/reference-direct suite: `44 passed, 13 subtests
  passed`.
- Frozen bounded parity task:
  `task_7a3ba9216fb910e53750` from run
  `20260711T034644Z_d318f177f7f2ac7d`; every consumed artifact's existence,
  structure, and axis identity were verified before read.
- Legacy reference-direct scan and shared resolver self-tests: PASS.
- `compileall`, `git diff --check`, generic hardcoding scan, and production
  output-root freshness check: PASS.
- No production YAML task was executed and no intermediate study bundle was
  created.

---

### Task 10: Extract Reference Normative-Fiber Backend And Shared Score

**Current-phase execution boundary:** production normative-fiber YAML may be
parsed, validated, and planned only. Task 10 uses deterministic synthetic
arrays and frozen structurally validated completed fixtures. It must not launch a
production observed grid, formal resampling, jitter, OSS, report task, or
expensive cache miss, must not write the production output root, and must not
create an intermediate study bundle.

**Files:**
- Create: `my_helper/fiber/core/dual_frequency/backends/statistics.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/source_resolver.py`
- Modify: `my_helper/fiber/core/dual_frequency/backends/direct_voxel/kernel.py`
- Modify: `my_helper/fiber/core/dual_frequency/backends/direct_voxel/source_resolver.py`
- Modify: `my_helper/fiber/core/dual_frequency/contracts/requests.py`
- Modify: `my_helper/fiber/core/dual_frequency/contracts/records.py`
- Modify: `my_helper/fiber/core/dual_frequency/cache/store.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/normative_fiber/coverage.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/normative_fiber/scoring.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/normative_fiber/reference.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_fiber_scoring.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_reference_fiber.py`
- Test source: completed dTOR/MGH/PPMI reference-fiber fixtures.

**Interfaces:**
- Produces: `ReferenceFiberBackend.run(ObservedRequest) -> ObservedResult`
- Produces:
  `score_signed_fibers(exposure, weights, fiber_ids, settings, candidate_mask=None) -> FiberScoreResult`.
  When supplied, `candidate_mask` is intersected with finite weights before
  signed selection. Omitting it is valid only when noncandidate weights are
  already `NaN` or the complete feature axis is intentionally eligible.
- Consumes explicit arrays/axes or validated `ArtifactRef` values only.
- `ObservedRequest` carries `connectome_role`, canonical `feature_ids`, and
  typed normative-fiber score settings. Direct-voxel requests require role
  `none` and no feature-ID/score payload; normative-fiber requests require role
  `formal` or `sensitive`, exact canonical fiber IDs, exposure units `V/m`, and
  the configured connectome-specific fold candidate minimum.
- `formal` `run` evaluates the complete observed grid, resolves the unique
  source, and returns a `SourceRecord`. `sensitive` `run` evaluates and
  publishes the complete observed grid but returns no source/final
  classification. Only a later
  `evaluate_sensitive_at_formal_source(request, formal_source)` call may emit a
  `SensitiveRecord`, using the exact numeric tau/Coverage selected by the
  matching formal endpoint. This preserves the already compiled DAG order.
- `SensitiveRecord` reports formal-source-cell computability and prediction
  evidence; it does not contain or assign a sensitive-connectome
  `source_status`, threshold source, branch role, or final-model status.
- Shared rank residualization, correlations, baseline/model prediction, and
  outcome-performance-independent tau/Coverage selection live in generic
  backend modules and are reused by direct voxel and normative fiber. Fallback
  distance is Manhattan distance in declared grid-index steps, followed by
  adjacent support, fold feature minimum, stricter Coverage, and higher tau.
- The realized formal fiber axis is the deterministic parent-order union of
  full-sample valid fibers and every fold-specific valid fiber. Full/fold
  weights project onto this exact axis with `NaN` where invalid. A full-sample
  finite-weight mask must never restrict a training fold.
- One-sided support is computable and remains QC-limited. Only
  `absent_no_valid_signed_fibers`, invalid baseline nuisance design,
  nonconstant-score failure, insufficient subjects/fold candidates, or
  nonfinite predictions fails hard computability.
- Artifact-backed exposure matrices are existence/axis/unit/space validated and
  opened read-only with memory mapping. Coverage, partial-Spearman weights, and
  selected-fiber scoring operate in bounded feature chunks; the backend must
  not materialize a complete dTOR exposure or candidate-by-subject weighted
  matrix in RAM.

- [x] **Step 1: Write failing score-policy tests**

Test finite-weight intersection, deterministic fiber-ID tie breaking,
`200/100/20`, one-sided status, full/fold recomputation, and held-out leakage
prevention.

- [x] **Step 2: Write failing source/resolver and connectome-role tests**

Use generic connectome IDs. Verify `sensitive` and `formal` behavior comes from
roles. Assert the sensitive observed-grid stage assigns no source, the later
formal-source evaluation emits `SensitiveRecord`, and sensitive connectomes
never emit `FinalModelRecord` or schedule formal/jitter/activation tasks.

- [x] **Step 3: Write bounded golden tests**

Load only exact completed tasks from the frozen bounded-fixture manifest and
verify every consumed path/schema/shape/axis before read. Compare completed dTOR full outputs and
MGH/PPMI observed/formal-source evaluation outputs only. Convert predecessor
MGH/PPMI final-like records to target sensitivity evidence; do not create
target finals, read mutable legacy summary paths directly, or invent formal/
OSS parity for sensitive connectomes.

The frozen Task 10 allowlist does not contain the complete parent canonical
fiber-ID axis required to reconstruct an `ObservedRequest`. Therefore bounded
golden acceptance must not follow the legacy selected manifest's indirect
`ids_path` or rerun the target backend from an unallowlisted input. It verifies
all consumed frozen artifacts' structural metadata, task and endpoint identities,
source/tau/Coverage/prediction semantics, selected score/prediction artifact
identity, and count/shape relationships that do not require the missing parent
ID axis. It must not claim parent-weight projection parity or instantiate a
target `SensitiveRecord` from a legacy full-sample-only selected axis. Complete
parent-axis, full/fold-valid-union, sensitive-record, and leakage behavior is
proven by deterministic synthetic tests.

The user's 2026-07-17 correction requires equality at tau to be active. Task 17
adds an explicit boundary-inclusion test. Bounded fixtures remain historical
semantic evidence. These are bounded-fixture limitations, not permission for
a transitive production read or a silent fallback to the superseded strict
rule.

- [x] **Step 4: Extract generic coverage, weights, resolver, and score kernels**

Do not import `stnsnr_hf_normative_fiber_smoke` or
`stnsnr_normative_fiber_score`.

- [x] **Step 5: Run focused and bounded tests; commit**

```bash
git add my_helper/fiber/core/dual_frequency/backends \
  my_helper/fiber/core/dual_frequency/cache/store.py \
  my_helper/fiber/core/dual_frequency/contracts \
  my_helper/fiber/core/dual_frequency/tests/test_cache.py \
  my_helper/fiber/core/dual_frequency/tests/test_records.py \
  my_helper/fiber/core/dual_frequency/tests/test_reference_direct_voxel.py \
  my_helper/fiber/core/dual_frequency/tests/test_fiber_scoring.py \
  my_helper/fiber/core/dual_frequency/tests/test_reference_fiber.py \
  my_helper/stnsnr/config/four_model_v1/normative_fiber_output_contract.md \
  my_helper/stnsnr/dual_frequency_core_decoupling_implementation_plan.md \
  my_helper/stnsnr/model_summaries/hf_3m_normative_connectome_fiber_model.md \
  my_helper/stnsnr/model_summaries/ulf_addon_gain_normative_connectome_fiber_model.md
git commit -m "feat: extract reference normative-fiber backend"
```

**Task 10 completion evidence (2026-07-15):**

- Generic dual-frequency suite: `139 tests` passed.
- Focused records/cache/direct-reference/fiber-reference suite: `68 tests`
  passed; reference normative-fiber suite: `8 tests` passed.
- Legacy normative-fiber score suite: `16 tests` passed; legacy shared
  statistics self-test passed with partial-Spearman maximum difference `0.0`.
- Frozen bounded evidence used only the six allowlisted completed dTOR, MGH,
  and PPMI observed/resolver tasks. Every consumed artifact's existence,
  structure, and axis identity were verified before read; the documented
  missing-parent-axis and legacy strict-threshold
  limitations were preserved rather than bypassed.
- Historical synthetic tests covered the then-current equality-accepting tau
  rule, parent-order full/fold-valid union, fold-only fitting, formal/sensitive
  role separation, scan fallback, noncomputable sensitive evidence, one-sided
  support, and read-only memory mapping. Task 17 reopens the tau-boundary test.
- `compileall`, `git diff --check`, generic hardcoding scan, and production
  YAML diff check passed.
- No production YAML task was executed, no production output was written, and
  no intermediate study bundle was created.

---

### Task 11: Extract DeltaReferenceScore And Add-On Direct-Voxel Backend

**Files:**
- Create: `my_helper/fiber/core/dual_frequency/backends/delta_reference/direct_voxel.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/interaction/reference_overlap.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/interaction/branch_resolver.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/direct_voxel/addon.py`
- Modify: `my_helper/fiber/core/dual_frequency/backends/direct_voxel/kernel.py`
- Modify: `my_helper/fiber/core/dual_frequency/backends/direct_voxel/__init__.py`
- Modify: `my_helper/fiber/core/dual_frequency/contracts/records.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_delta_reference_direct.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_addon_direct_voxel.py`
- Modify: `my_helper/fiber/core/dual_frequency/tests/test_records.py`

**Interfaces:**
- Produces: `build_delta_reference_voxel(...) -> DeltaReferenceBundle`
- Produces: `AddonDirectVoxelBackend.run(ObservedRequest) -> ObservedResult`
- Consumes the catalog's explicit `matched_reference_endpoint_id`; no phase-
  equality or output-discovery fallback.
- `DeltaReferenceBundle` is an immutable typed dependency record. It does not
  create a bundle directory, a derived study file, or an intermediate study
  bundle. Its artifacts are published through the run-scoped injected
  publisher.
- DeltaReferenceScore construction consumes only the accepted matched
  reference `SourceRecord`, its existence/axis-validated selected-feature indices,
  full and fold weights, the reference-condition exposure, the add-on
  condition reference-component exposure, the shared subject/parent-feature
  axes, and the configured support thresholds. It accepts no project path,
  phase name, scale name, or output-discovery argument.
- The selected reference tau/Coverage is locked from `SourceRecord` for the
  full sample and every fold. Each fold uses that fold's own finite weight
  support; it does not rerun the source resolver and does not substitute the
  full-sample support.
- For full-sample or fold weights `w`, the score is the continuous-dose mean
  over the finite locked support:

  ```text
  DeltaReferenceScore_i =
      mean_u[(E_reference_component_addon_i(u)
              - E_reference_condition_i(u)) * w(u)]
  ```

  Tau defines the suprathreshold component-coverage QC only; continuous
  exposure values inside the locked finite map support enter the score.
- Support QC uses the add-on condition's reference-component suprathreshold
  voxel range on the complete parent feature axis and strict direct-voxel
  thresholding `E > selected_reference_tau`. A required subject with
  `suprathreshold_count < 1` is
  `invalid_no_reference_component_coverage`, never `adequate`.
- Historical Task 11 support classification is deterministic: `adequate`
  included a cohort median exactly at `0.20` and a subject fraction exactly at
  `25%`. Task 17 reopens those boundaries; its strict target requires median
  `< 0.20` and subject fraction `< 0.25`. `invalid_extreme_out_of_support` applies
  when cohort median is `> 0.50`, `subject_fraction > 0.25` for values
  `> 0.80`,
  or any required full/fold value is `> 0.95`; remaining cases with
  `suprathreshold_count > 0` are
  `limited`. Both `adequate` and `limited` are valid adjusted inputs.
- The immutable DeltaReference dependency record carries axis-bound full
  scores, fold-by-subject scores, numeric support rows, and a small support-QC
  document that names every support column and records the effective threshold
  rule and classification summary. Invalid support retains support rows/QC but
  publishes no usable full/fold score artifacts.
- Reference-overlap exclusion is a pure preparation function. An accepted
  reference source uses its exact selected tau; an absent source uses an
  infinite threshold, creates an all-false overlap mask, and leaves add-on
  exposure unchanged. Tau/Coverage source resolution remains downstream of
  this preparation.
- `ObservedRequest.baseline` is the matched reference clinical outcome. A
  `no_delta_reference` request has no nuisance inputs. A
  `delta_reference_adjusted` request carries exactly two axis-bound nuisance
  inputs in canonical order: the full-sample DeltaReferenceScore vector and
  the fold-by-subject DeltaReferenceScore matrix. Row `h` is generated by the
  reference model trained without subject `h`; element `[h, h]` is used for
  the held-out prediction after training-row-only standardization.
- The add-on numerical backend evaluates one executable branch only. It does
  not assign intended role, fallback role, or final status. The state-machine
  adapter wraps its result in `BranchRecord`; expected adjusted input/design
  failure skips that numerical branch while preserving the runnable no-delta
  branch.
- No-delta nuisance design is `[intercept, Y_reference]`. Adjusted nuisance
  design is `[intercept, Y_reference, z(DeltaReferenceScore)]`, with the mean
  and population standard deviation recomputed on each training fold. A
  constant/nonfinite DeltaReferenceScore or rank-deficient design is an
  adjusted-branch input/design failure, not an endpoint-wide failure.
- Each executable branch runs the complete declared add-on tau/Coverage grid
  and independently receives source/prediction status. The shared resolver
  remains independent of MAE, RMSE, Q2, and rho when choosing tau/Coverage;
  MAE and RMSE classify prediction only after hard computability passes.
- Direct-voxel observed mathematics is shared through a typed nuisance plan:
  one full-sample subject-by-covariate matrix plus one
  fold-by-subject-by-covariate matrix. The existing reference wrapper builds a
  plan whose fold matrices equal the full baseline covariate; the adjusted
  add-on wrapper supplies fold-specific standardized DeltaReferenceScore.
  Tau/Coverage, weight fitting, continuous scoring, LOOCV prediction, hard
  computability, and source resolution remain one implementation rather than
  copied reference/add-on kernels.
- Task 11 uses deterministic synthetic arrays only. The completed predecessor
  add-on direct tasks are unavailable, so this task must not claim numerical
  parity, start a legacy producer, execute production YAML, write the
  production output root, or create an intermediate study bundle.

- [x] **Step 1: Write failing DeltaReferenceScore tests**

Assert fold-specific reference training excludes held-out subjects, selected
reference tau/Coverage remains locked, adequate/limited are valid, extreme
out-of-support is invalid, and invalid adjusted input leaves no-delta runnable.
Separately assert missing/failed reference clinical input produces
`dependency_failure` with no branch, while ready reference input with
`absent_no_stable_grid` permits no-delta.

- [x] **Step 2: Write failing overlap/nuisance tests**

Reference absent means infinite overlap threshold and raw add-on exposure.
No-delta uses `Y_post ~ Y_reference`; adjusted adds DeltaReferenceScore.

- [x] **Step 3: Write state/backend integration tests**

Cover one-way source-failure fallback. The predecessor add-on direct tasks
failed, so tests are synthetic/smoke only and must not claim numeric parity.

- [x] **Step 4: Extract generic kernels without legacy imports**

Move reusable math from `legacy_ulf_direct.py` and
`stnsnr_ulf_direct_voxel_observed.py`. Keep project exposure discovery outside
the backend. Backend inputs are typed request records and arrays/artifact
references only.

- [x] **Step 5: Run focused smoke and commit**

```bash
git add my_helper/fiber/core/dual_frequency/backends/delta_reference \
  my_helper/fiber/core/dual_frequency/backends/interaction \
  my_helper/fiber/core/dual_frequency/backends/direct_voxel/__init__.py \
  my_helper/fiber/core/dual_frequency/backends/direct_voxel/kernel.py \
  my_helper/fiber/core/dual_frequency/backends/direct_voxel/addon.py \
  my_helper/fiber/core/dual_frequency/contracts/records.py \
  my_helper/fiber/core/dual_frequency/tests/test_records.py \
  my_helper/fiber/core/dual_frequency/tests/test_delta_reference_direct.py \
  my_helper/fiber/core/dual_frequency/tests/test_addon_direct_voxel.py \
  my_helper/stnsnr/dual_frequency_core_decoupling_implementation_plan.md
git commit -m "feat: extract add-on direct-voxel backend"
```

**Task 11 completion evidence (2026-07-15):**

- Generic dual-frequency suite: `155 tests` passed.
- Focused DeltaReference/add-on direct-voxel suite: `16 tests` passed.
- Reference and add-on direct-voxel kernels share one full/fold nuisance-plan
  implementation; the frozen reference-direct parity test remains passing.
- Synthetic tests cover accepted matched-endpoint identity, full/fold locked
  scoring, finite-weight support, adequate/limited/zero/extreme support,
  strict `> 0.95` behavior (`0.95` accepted, `0.96` invalid), absent-source
  overlap passthrough, adjusted scaling/design failures, branch independence,
  and one-way no-delta fallback.
- Legacy HF and ULF direct-voxel self-tests: PASS. No predecessor add-on task
  was promoted to bounded numerical parity because its completed output is not
  available.
- `compileall`, `git diff --check`, generic production-hardcoding scan, and
  production YAML diff check passed.
- No production YAML task was executed, no production output was written, and
  no intermediate study bundle was created.

---

### Task 12: Extract Add-On Normative-Fiber Backend

**Files:**
- Create: `my_helper/fiber/core/dual_frequency/backends/nuisance.py`
- Modify: `my_helper/fiber/core/dual_frequency/backends/direct_voxel/kernel.py`
- Modify: `my_helper/fiber/core/dual_frequency/backends/direct_voxel/addon.py`
- Modify: `my_helper/fiber/core/dual_frequency/backends/normative_fiber/reference.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/delta_reference/normative_fiber.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/normative_fiber/addon.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_delta_reference_fiber.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_addon_fiber.py`
- Test source: completed first combined-child dTOR add-on-fiber stages only.

**Interfaces:**
- Produces: `build_delta_reference_fiber(...) -> DeltaReferenceBundle`
- Produces: `AddonFiberBackend.run(ObservedRequest) -> ObservedResult`
- Consumes exact matched-reference endpoint/connectome IDs and explicit
  arrays/artifact references only.
- `DeltaReferenceBundle` remains an immutable run-scoped dependency record. It
  does not create a directory, derived study file, or intermediate study
  bundle.
- The formal add-on branch consumes the accepted formal reference
  `SourceRecord`. A sensitive add-on branch consumes only the computable local
  reference `SensitiveRecord` evaluated at the formal numeric tau/Coverage.
  The local matched-reference endpoint ID, connectome ID, parent fiber-axis
  semantic ID, and artifact axes must all agree; a sensitive connectome never borrows
  a formal-connectome fiber axis or fiber weights.
- The locked reference operator is reconstructed from the selected reference
  full/fold weights on the deterministic parent-order valid-feature union.
  For each full sample or fold, valid support is the selected-source
  Coverage-passing set intersected with finite weights. The full-sample finite
  set must not restrict any fold.
- Full and fold DeltaReferenceScore use the same signed-library and weighted-
  peak operator as the reference model:

  ```text
  DeltaReferenceScore_i =
      NetFiberScore(reference_component_addon_i; locked reference operator)
      - NetFiberScore(reference_condition_i; locked reference operator)
  ```

  Fiber ranking, sign, `K+`, `K-`, `H+`, and `H-` are recomputed from the
  corresponding full/fold weights with the configured `200/100/20` policy.
  Continuous exposure values enter the score after the locked valid support is
  established.
- DeltaReferenceScore support QC uses the add-on condition's reference-
  component suprathreshold fiber range on the complete parent axis and the
  strict normative-fiber rule `E > selected_reference_tau`. Equality at the
  selected reference tau is excluded. For each
  subject and each required full/fold operator:

  ```text
  out_support_fraction =
      count(suprathreshold fibers outside that operator's finite valid support)
      / count(all suprathreshold reference-component fibers)
  ```

  A `denominator_count < 1` is `invalid_no_reference_component_exposure`. Historical
  Task 12 classified median exactly `0.20` and subject fraction exactly `25%`
  as `adequate`; Task 17 reopens them with strict median `< 0.20` and fraction
  `< 0.25`. `invalid_extreme_out_of_support` applies when the
  cohort median is `> 0.50`, `subject_fraction > 0.25` for values `> 0.80`, or any
  required full/fold value is strictly `> 0.95`; all other cases with
  `denominator_count > 0` are
  `limited`. `adequate` and `limited` are valid adjusted inputs.
- Reference-active overlap is applied before add-on Coverage and candidate
  construction. An accepted local reference model uses its exact selected
  tau; an absent formal reference source uses `+Inf`, so the formal no-delta
  branch sees raw continuous add-on exposure and the adjusted branch is not
  attempted. For each fold, overlap and add-on Coverage are rebuilt from that
  fold's training inputs. No full-sample overlap or candidate mask is reused.
- Reference-overlap preparation operates in bounded fiber chunks. Synthetic
  tests may allocate a small in-memory destination; production preparation
  writes into caller-provided array/memmap destinations already owned by the
  run-scoped artifact layer and never materializes a complete dTOR copy or
  accepts a raw output path.
- The add-on source tau defines Coverage/candidate fibers only. Within the
  resulting candidate universe, continuous add-on peak E-field remains in the
  score except where reference-active overlap sets the patient-fiber value to
  zero.
- The direct-voxel and normative-fiber add-on backends share one generic
  full/fold nuisance-plan implementation. `no_delta_reference` uses
  `[Y_reference]`; `delta_reference_adjusted` uses
  `[Y_reference, z(DeltaReferenceScore)]`, with z-scaling learned independently
  inside every training fold. A DeltaReferenceScore failure invalidates only
  the adjusted branch.
- Formal connectomes evaluate the complete branch grid and may resolve a
  source. Sensitive connectomes evaluate the complete branch grid, then only
  evaluate the matching formal branch's numeric selected tau/Coverage; they
  emit sensitivity evidence only and cannot assign source, primary, fallback,
  or final status.
- The branch numerical backend never decides intended role or final role.
  Existing state-machine code applies the one-way no-delta fallback only after
  independent branch results exist; technical execution failure cannot trigger
  fallback.
- Production normative-fiber YAML remains parse/validate/plan-only in this
  task. Tests use deterministic arrays and structurally validated completed fixtures
  only; no production observed, formal, sensitivity, jitter, OSS, or report
  task may run or write beneath the production output root.

**Frozen bounded evidence for Task 12:**

- Acceptance run: `20260711T034644Z_d318f177f7f2ac7d`.
- Endpoint: `endpoint_0e489d4dae7d51a3fa0c`, MDS-UPDRS III score,
  chronic add-on, dTOR `formal`, 16 subjects.
- This endpoint is used only because it is the sole completed allowlisted
  add-on-fiber child. It has no engineering priority; every configured scale
  uses the same backend, resolver, classification, and artifact contract.
- The approved allowlist is exact. Relevant terminal tasks are
  `task_49c57915a31c57add0ee` (Delta/support sidecars),
  `task_294db6b85fcc19c9ff25` (no-delta observed resolver),
  `task_f2761adf6686800a83da` (final realization),
  `task_05fb8da14057db04bcd0` (controls),
  `task_4c0176441302daf11384` (formal summaries),
  `task_737a02e8a551e383ceb5` (cheap sensitivity), and
  `task_3791e85acf027faa4e68` (source neighborhood).
- The frozen Delta input is invalid-extreme (`tau=800`, `Coverage=5`); the
  adjusted task was gate-skipped. The completed no-delta source is a scan
  fallback at `tau=400`, `Coverage=5`, classified `error_predictive`, and is
  the realized final. Legacy filenames that contain `tau800` do not override
  the resolver metadata.
- Failed OSS, partial `388/1000` jitter, unstarted report, and completed but
  non-allowlisted tasks are excluded. The fixture has no fold weights or
  deterministic full/fold valid-feature union, so it cannot prove adjusted,
  sensitive-role, fold-operator, OSS, jitter, or full resampling parity.
  Those target contracts are tested synthetically; bounded parity is limited
  to structural artifact validation, completed status transitions, support QC, selected `400/5`
  no-delta evidence, and terminal summary artifacts.

- [x] **Step 1: Write failing support/overlap tests**

Cover matched reference feature identity, reference-component support,
overlap exclusion before add-on Coverage/candidate creation, branch-specific nuisance weights,
and the shared `200/100/20` score. Assert sensitive connectomes produce branch
resolver/sensitivity records but cannot realize a final or fallback final.

- [x] **Step 2: Write failing bounded parity tests**

Compare only completed first combined-child dTOR preprocessing, resolver, final, controls,
formal inputs, cheap sensitivity inputs, and neighborhood artifacts. Exclude
failed OSS and partial jitter.

- [x] **Step 3: Extract generic kernels**

Do not import `legacy_ulf_fiber.py` or
`stnsnr_ulf_normative_fiber_observed.py`. Use explicit connectome and artifact
references.

- [x] **Step 4: Run focused, bounded, and one-way fallback tests**

Expected: completed-scope parity passes; uncompleted paths run synthetic smoke
only.

- [x] **Step 5: Commit**

```bash
git add my_helper/fiber/core/dual_frequency/backends/delta_reference/normative_fiber.py \
  my_helper/fiber/core/dual_frequency/backends/normative_fiber/addon.py \
  my_helper/fiber/core/dual_frequency/tests/test_delta_reference_fiber.py \
  my_helper/fiber/core/dual_frequency/tests/test_addon_fiber.py
git commit -m "feat: extract add-on normative-fiber backend"
```

**Verification completed 2026-07-15:**

- Generic `dual_frequency` suite: `171 tests` passed.
- Focused add-on-fiber, DeltaReferenceScore, shared-nuisance, reference-fiber,
  scoring, record, and state suite: `69 tests` passed.
- Legacy HF/add-on normative-fiber observed, immediate, sensitive, shared
  statistics, and smoke self-tests all reported `PASS`.
- Python compilation and `git diff --check` passed; production YAML/JSON was
  unchanged, no task wrote beneath the production `summary/spot` root, and no
  intermediate study bundle was created.
- The frozen completed add-on-fiber fixture passed its exact task allowlist,
  manifest/artifact structure, invalid Delta-support, selected `400/5` no-delta,
  and realized-final assertions. Missing historical fold/operator evidence was
  covered only by deterministic synthetic tests, as required.

---

### Task 13: Extract Formal And Sensitivity Backends

**Files:**
- Create: `my_helper/fiber/core/dual_frequency/contracts/validation.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/formal/direct_voxel.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/formal/normative_fiber.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/sensitivity/tau_neighborhood.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/sensitivity/spatial_jitter.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/sensitivity/addon_exposure.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/sensitivity/fiber_controls.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_formal.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_sensitivity.py`

**Interfaces:**
- Produces: `FormalBackend.run(FinalModelRecord, FormalRequest) -> FormalResult`
- Produces: explicit sensitivity strategy implementations.
- Consumes only a formal-connectome/direct-voxel realized final plus typed
  arrays/artifact references; sensitive-connectome records are rejected.

**Formal sub-contract confirmed for implementation:**

- Every `FormalRequest` declares exactly one `resampling_kind`:
  `permutation` or `bootstrap`. Separate planner tasks remain separate and
  cannot silently execute the other resampling family.
- The request carries the realized `FinalModelRecord`, exposure, outcome,
  branch-specific baseline and optional full/fold DeltaReferenceScore inputs,
  exact subject and locked final feature axes, outcome direction, hard
  computability limits, resample counts, and seed. Normative-fiber requests
  additionally carry exact ordered fiber IDs and the signed score settings.
- Final-linked formal scientific inputs are immutable `ArtifactRef` values with
  exact ordered axis identities. Bare NumPy arrays remain permitted in
  pre-final observed numerical APIs and synthetic kernel tests only; they are
  not accepted by `FormalRequest` because shape alone cannot prove subject or
  feature order and a frozen dataclass does not freeze an array payload.
- Direct-voxel requests require connectome-role state `none`; normative-fiber
  formal requests require the unique connectome-role state `formal`. A sensitive-connectome
  record, non-realized final, mismatched axis, raw path, or filename is rejected
  before publication.
- Reference and no-delta requests have no additional nuisance inputs. Adjusted
  requests require one full subject vector and one fold-by-subject
  DeltaReferenceScore matrix. Formal permutation may reuse these fixed
  fold-local inputs because the stimulation/reference inputs are unchanged by
  outcome permutation.
- Adjusted subject bootstrap cannot resample the original full/fold
  DeltaReferenceScore values. It requires an injected
  `BootstrapNuisanceProvider` that rebuilds the matched reference score,
  support QC, and fold-local DeltaReferenceScore values for each sampled
  subject-multiplicity vector. The provider returns typed rebuilt-score evidence
  and structured support/provenance fields, not an arbitrary nuisance design.
  The formal backend itself standardizes those rebuilt scores and constructs the
  branch nuisance plan. A missing or identity-inconsistent provider result is an
  explicit input failure; no-delta/reference bootstrap does not require one.
  Rebuild provenance binds the exact ordered sample-index vector, not only its
  multiplicities. For a non-identity sample, unchanged original full/fold Delta
  payloads and direct sample/reindex views of the original full/fold Delta
  payloads are rejected as stale rather than accepted under self-attested new
  provenance. A provider must return scores from a newly fitted matched-
  reference bootstrap model; indexing or permuting the original scores is not a
  rebuild.
- All formal calculations stay on `final.valid_feature_axis`; no backend may
  rediscover a parent feature universe from paths. Fold-specific coverage,
  finite weights, signed fiber selection, and patient scores are recomputed
  within that locked axis.
- A normative-fiber request's ordered fiber IDs must be the exact immutable ID
  artifact carried by the selected final source/branch, not merely an array with
  the same length. Subject axes and ordered feature identities are compared by
  full scientific identity before any resampling starts.
- Freedman-Lane permutation uses the branch-specific nuisance-only model and
  the observed LOOCV Spearman rho as the two-sided plus-one test statistic.
  A null replicate contributes a statistic only when every held-out prediction
  is finite; partial finite-pair correlations remain `NaN` and cannot enter the
  null distribution. An inferential permutation p value is published only when
  every requested null replicate is finite. Any null attrition is reported with
  technical status and counts but has no inferential p value.
  Q2, Pearson correlation, MAE, and RMSE are emitted as report fields only and
  never alter source, prediction, branch-role, endpoint, or final status.
- Subject bootstrap emits finite replicate counts, candidate/support counts,
  weight mean/SE and applicable fiber sign/selection stability. It is a
  robustness output only. `FormalResult` contains final ID, resampling kind,
  technical status, and immutable artifacts; it exposes no classification
  mutation fields.

**Sensitivity sub-contract confirmed for implementation:**

- Final-linked tau-neighborhood, spatial-jitter, add-on exposure, and final
  fiber-control strategies accept only a realized `FinalModelRecord` and its
  exact locked feature axis. Their scientific inputs are immutable
  axis-bearing `ArtifactRef` values; bare mutable arrays are restricted to
  pre-final observed/kernel tests. They reject `SensitiveRecord`, non-final
  branches, sensitive connectomes, unresolved paths, and mismatched
  subject/feature IDs.
- Reference-fiber plain and cheap controls that execute before source
  resolution are a separate `ObservedFiberControlStrategy`. They consume typed
  observed inputs/results and emit diagnostic evidence only; they cannot be
  represented as, or promoted to, final-linked sensitivity.
- Tau-neighborhood uses the selected coverage and absolute tau values derived
  from `0.9 * selected_tau` and `1.1 * selected_tau`. It evaluates those cells
  without invoking the source resolver and omits source/prediction/final status
  from its output.
- Tau continues to define Coverage/Omega only. Historical Task 13 had
  inconsistent direct-voxel and normative-fiber boundary behavior. The
  2026-07-17 correction includes exact tau and Coverage values in both model
  families. For both families, all
  continuous E-field values inside the selected candidate support enter
  scoring. Add-on sensitivity may zero only the declared reference-overlap
  exposure; it must not zero add-on exposure merely because its value is below
  tau.
- Spatial jitter receives settings plus an injected typed replicate provider.
  Each replicate provider rebuilds perturbed exposure and, for add-on models,
  overlap exclusion, DeltaReferenceScore, support QC, and branch nuisance
  inputs before returning a complete typed observed request plus structured
  replicate evidence. The result must retain the exact subject axis and ordered
  feature identity of the final target. Adjusted replicates must prove a new
  DeltaReferenceScore/support rebuild for that replicate; a stale original
  adjusted input is rejected. Replicate provenance is content-bound to the
  perturbed exposure, rebuilt overlap mask, support status/QC, and applicable
  rebuilt DeltaReferenceScore payloads; copying unchanged original arrays under
  a new object or token is rejected. Outcome, baseline, branch, grid, limits,
  direction, units/space, score settings, and every nuisance input not declared
  rebuildable must remain scientifically identical to the final target. The
  numerical strategy never discovers geometry or files by name.
- Add-on analyses are independently identified and independently terminal:
  nonfinal-branch comparison, gain endpoint, total exposure, support, and
  collinearity. Failure or non-applicability of DeltaReferenceScore-dependent
  analyses cannot suppress an executable total-exposure or no-delta analysis.
- Nonfinal-branch and gain analyses use the same reference-overlap exclusion as
  the corresponding add-on model. Total-exposure sensitivity is the explicit
  exception and intentionally retains total exposure. Gain nuisance is
  branch-specific: no-delta gain uses an intercept only, while adjusted gain
  uses intercept plus rebuilt DeltaReferenceScore; neither gain branch includes
  the reference outcome as nuisance.
- A gain analysis requires an axis-bound artifact with the dedicated
  `direction_normalized_addon_gain` kind. An ordinary post-score outcome cannot
  be relabeled as gain merely by placing its `ObservedRequest` in a field named
  `gain_request`. Positive normalized gain always means benefit, so its request
  must use outcome-direction state `higher` regardless of the source scale direction.
- Only `nonfinal_request` may use the non-realized branch. Gain and total-
  exposure requests inherit the realized final branch and branch-specific
  nuisance inputs. Nonfinal and gain analyses reuse the target's exact
  overlap-excluded exposure artifact. Total-exposure sensitivity instead uses
  the same `PreparedExposureRecord`'s axis-identical
  `raw_addon_component_exposure` artifact and omits the target overlap mask;
  no other exposure substitution is permitted. Nonfinal and total-exposure
  requests retain the target outcome and baseline artifacts. Gain retains the
  target baseline and overlap-excluded exposure while replacing only outcome
  with the dedicated normalized-gain artifact.
- `ObservedRequest` accepts only the branch vocabulary of its model family:
  `reference` for reference models and exactly `no_delta_reference` or
  `delta_reference_adjusted` for add-on models. A nonfinal sensitivity request
  must use the one canonical add-on branch opposite the realized final; an
  arbitrary third branch is an input-contract failure, not a not-computable
  analysis result.
- Fiber controls report plain exposure/burden, signed-score increment, support,
  and collinearity diagnostics. Plain peak summaries aggregate continuous
  exposure across the locked candidate axis; tau is retained only for coverage
  and touched-count QC. Final-branch controls retain the branch's overlap-
  excluded exposure. A burden-dominated or one-sided result remains
  interpretation QC and cannot change the resolver or final decision.
- Every strategy returns only technical status, numeric metrics/QC, and
  immutable artifacts. Result construction rejects classification mutation
  keys, including source, prediction, branch-role, endpoint, or final-model
  status fields.
- Formal bootstrap support QC and all sensitivity payloads use one shared,
  recursive classification-feedback validator. Provider-supplied QC cannot
  publish classification keys or classification-status values through a nested
  evidence artifact.
- Remove the generic `SensitivityRequest` and `SensitivityBackend` API. Only
  the explicit typed strategy requests and their `run(...)` methods are public;
  a `SensitiveRecord` is never accepted by a final-linked strategy.

- [x] **Step 1: Write failing final-only and no-feedback tests**

Reject non-final branches, sensitive-connectome records, missing final axes, and outputs
that attempt to write classification fields.

- [x] **Step 2: Write bounded deterministic and frozen-evidence tests**

Run exactly ten deterministic synthetic permutations, ten deterministic
synthetic bootstraps, and five deterministic synthetic jitter replicates through
the extracted strategies. The frozen predecessor stores only completed
10,000-resample summaries, not the first ten numerical vectors; therefore do not
claim unavailable historical-prefix numerical replay. Validate the complete
predecessor formal summaries by schema/shape/numerical checks, and validate the
first five rows plus complete structure for each completed allowlisted jitter
artifact. Exclude the partial
add-on dTOR jitter.

- [x] **Step 3: Extract generic numerical code**

Move math from the relevant `stnsnr_*formal*`, `*jitter*`, and sensitivity
modules. Strategy selection is based on model-family capabilities, not module
name strings.

- [x] **Step 4: Run focused tests and completed-scope parity**

Expected: reference direct/fiber completed prefixes and completed add-on fiber
formal/cheap/neighborhood fixtures pass.

- [x] **Step 5: Commit**

```bash
git add my_helper/fiber/core/dual_frequency/backends/formal \
  my_helper/fiber/core/dual_frequency/backends/sensitivity \
  my_helper/fiber/core/dual_frequency/backends/__init__.py \
  my_helper/fiber/core/dual_frequency/backends/direct_voxel/kernel.py \
  my_helper/fiber/core/dual_frequency/backends/nuisance.py \
  my_helper/fiber/core/dual_frequency/backends/protocols.py \
  my_helper/fiber/core/dual_frequency/contracts/__init__.py \
  my_helper/fiber/core/dual_frequency/contracts/requests.py \
  my_helper/fiber/core/dual_frequency/contracts/validation.py \
  my_helper/fiber/core/dual_frequency/tests/test_formal.py \
  my_helper/fiber/core/dual_frequency/tests/test_records.py \
  my_helper/fiber/core/dual_frequency/tests/test_sensitivity.py \
  my_helper/stnsnr/dual_frequency_core_decoupling_implementation_plan.md
git commit -m "feat: extract generic formal and sensitivity backends"
```

**Verification completed 2026-07-15:**

- Formal backend suite: `24 tests` passed; sensitivity strategy suite:
  `33 tests` passed.
- Complete generic `dual_frequency` suite: `271 tests` passed.
- Deterministic synthetic tests covered ten permutations, ten bootstraps, five
  jitter replicates, direct strict and the then-current equality-accepting fiber
  tau boundary, exact
  final-axis identity, branch-specific nuisance, and classification-feedback
  rejection. Frozen predecessor evidence remained restricted to the allowlist.
- Independent review findings were closed with regression tests: normalized
  gain requires outcome-direction state `higher`; gain/total reuse the realized final
  branch and exact exposure/baseline/nuisance artifacts; nonfinal accepts only
  the canonical opposite branch; adjusted bootstrap rejects unchanged and
  directly reindexed stale DeltaReferenceScore values; formal support QC cannot
  publish classification fields.
- `compileall`, protocol type-hint resolution, `git diff --check`, obsolete API
  scan, and generic hardcoding scan passed. No production YAML, study data,
  output root, bundle, FEM, OSS, formal production run, or subject-specific
  runtime rule was created or modified.

---

### Task 14: Implement Shared Activation Universe And Generic OSS Backend

**Historical completion record, producer universe superseded.** The generic OSS
backend was completed on an endpoint-final axis. Task 17's PASS branch proposes
scale-independent OSS/pPAM rows on the formal connectome's exact minimum-grid
`Omega_max` axis and lets endpoint analysis select final columns; its FAIL
branch retains this completed endpoint-final producer. Task 17 reopens the
producer/planner/cache work; checked boxes below do not mark that conditional
migration complete.

**Files:**
- Modify: `my_helper/fiber/core/dual_frequency/contracts/requests.py`
- Modify: `my_helper/fiber/core/dual_frequency/backends/protocols.py`
- Modify: `my_helper/fiber/core/dual_frequency/config/schemas/normative_fiber_model.schema.json`
- Modify: `my_helper/fiber/core/dual_frequency/config/loader.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/activation/canonical_mapping.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/activation/ppam.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/activation/fitting.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/activation/ossdbs.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_activation_universe.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_oss_backend.py`

**Interfaces:**
- Produces: `OSSRowBackend.materialize(OSSRowBatchRequest) -> OSSRowBatchArtifact`.
- Produces: `ActivationBackend.run_activation(ActivationRequest) -> ActivationArtifact`.
- `ppam.py` owns only probability validation, canonical maximum union, and the
  binary threshold. The Task 14 implementation accepted equality at `0.5`;
  Task 17 reopens it for the strict target. `fitting.py` owns endpoint nuisance design,
  fold-local weights/scoring, Freedman-Lane smoke permutation, technical
  status, and run-scoped artifact publication.
- The PASS-only target producer fiber axis is the formal-connectome physical exposure
  family's exact `Omega_max` at minimum configured tau/Coverage. It is not the
  whole connectome and has no intermediate sidecar bundle. FAIL retains the
  historical endpoint-final axis.
- A PASS-branch producer deterministic path excludes scale, endpoint, final-model ID, run
  ID, worker count, and task order, but includes the exact ordered `Omega_max`
  semantic axis ID and canonical `feature_ids` file. Exact matching physical
  inputs reuse rows across endpoints; different axes cannot use nearest-key,
  superset guessing, or the same cache path. The FAIL path retains the
  historical final-axis identity.
- Consumes subject/component/condition/connectome/transform/solver inputs only as
  typed metadata and exact artifact references; solver paths come from validated
  backend configuration.
- The activation task has the realized final-model task as a direct dependency
  in addition to completed formal tasks. A transitive dependency is not a
  substitute for a typed direct final-record input.
- `expensive_producer` identifies a service that may produce expensive rows; it
  must not block service invocation before exact cache lookup. The activation
service probes all row keys first and checks expensive authorization only when
  `missing_valid_row_count > 0`.
- `ActivationRequest` explicitly carries outcome, branch-specific baseline,
  optional full/fold DeltaReferenceScore inputs, ordered subject/fiber axes,
  canonical fiber IDs, the matched final peak-E-field score, outcome direction,
  hard-computability limits, signed fiber-score settings, permutation count,
  and seed. The backend must not infer these inputs from filenames or hidden
  final-record artifacts.
- Adjusted activation nuisance inputs are exactly
  `delta_full_scores[subject]` and `delta_fold_scores[fold, subject]`, with
  axes `(subject_axis,)` and `(subject_axis, subject_axis)`. Other shapes or
  orders are branch-local input failures.
- In the PASS branch, `OSSRowBatchArtifact` exposes the prepared `Omega_max` canonical
  `feature_ids` artifact. Endpoint analysis creates an explicit ordered view:
  `ActivationRequest.feature_ids` carries the final-axis ID authority and
  `ActivationRequest.activation_feature_ids` carries the already-subset OSS
  matrix column-ID authority. Endpoint fitting requires those two int64 arrays
  to be exactly equal and bound to `final.valid_feature_axis`; IDs cannot be
  inferred, silently reordered, or selected by position without canonical-ID
  validation.
- In the PASS branch, `final.valid_feature_axis` must be an exact canonical-ID subset of the
  prepared `Omega_max` OSS axis. OSS never reapplies peak-E-field tau/Coverage
  in full-sample, LOOCV, or permutation fits. Within the selected final axis, full-sample and each
  training fold independently intersect finite OSS weights, reselect signed
  fibers, and recompute the configured weighted-peak score.
- Reference OSS uses an all-false overlap mask. Add-on physical OSS preparation
  stores raw activation; endpoint analysis additionally receives the realized
  branch's patient-by-feature reference-overlap mask on the selected ordered
  final axis. It applies that mask after strict pPAM thresholding and before
  weights, signed scoring, plain-activation QC, LOOCV, or permutation. The mask
  cannot change the final axis, and add-on OSS cannot reintroduce an HF-touched
  patient-fiber exposure.
- Endpoint fitting emits only sensitivity status and artifacts. The status is
  `failed_activation_degenerate` for `active_feature_count < 1`, non-estimable activation, or an
  absent/constant signed score, `failed_oss_design_or_prediction` for invalid
  nuisance/prediction/permutation execution, `passed_activation_consistent`
  for a technically valid score with positive correlation to the explicit
  final peak-E-field score, and `passed_activation_model_dependent` for any
  other finite technically valid correlation. A nonfinite or constant final
  peak-E-field score, or a nonfinite cross-model correlation, is
  `failed_oss_design_or_prediction`; it can never receive a passed status. None
  of these statuses may alter the source, prediction, branch-role, endpoint, or
  final-model record.
- Continuous pPAM rows must be exact `activated_count / 10` probabilities from
  the frozen ten-sample contract. The publication boundary rejects values that
  are outside `[0, 1]` or do not lie on the 0.1 probability lattice within
  floating-point tolerance.
- A smoke permutation P value is emitted only when all requested permutations
  complete with finite statistics. Incomplete null distributions retain the
  explicit failure/completion status and emit a null P value; they cannot use a
  reduced finite denominator.
- The backend materializes and validates every input, ordered ID binding,
  overlap mask, nuisance design, and fit result before publishing any immutable
  run-scoped artifact. A rejected request therefore leaves no partial artifact
  tree that could block an exact retry.
- The same task emits plain binary-activation count, sum, top-5% exposure, and
  nuisance-adjusted in-sample comparisons for nuisance-only, plain-top-5,
  OSS NetFiberScore, and their joint model. These are burden/placement QC only
  and cannot be interpreted as a causal decomposition or classification gate.

- [x] **Step 1: Write failing universe and identity tests**

Assert the analysis universe equals the realized final model's exact ordered
`valid_feature_axis` at selected tau/Coverage. Weights, signs, and selected
sweet/sour IDs do not restrict that endpoint subset. Scale/final identifiers do
not enter the producer path, while a changed ordered `Omega_max` axis ID does. Require the
unique configured `formal` connectome role without checking a connectome name.

- [x] **Step 2: Write failing mapping and threshold tests**

Assert elementwise-maximum L/R merging and the historical Task 14 binary rule,
which classified probability exactly `0.5` as active. Task 17 reopens only that
boundary and defines its strict replacement. Require exact canonical fiber IDs
and deterministic endpoint subsetting.
Freeze the public v1 OSS contract to `OSS-DBSv2`, `pPAM`, fiber diameters
`1.0..4.0` micrometers, exactly 10 equidistant samples, and the historical
equality-accepting fitting threshold `0.5`. Schema and semantic validation reject
any other values, and
the row publication boundary verifies that every probability equals an integer
activation count divided by ten.

- [x] **Step 3: Write bounded OSS acceptance tests**

Validate the completed allowlisted reference-fiber OSS matrix, fiber IDs,
metadata, and sensitivity-result structure. Replay exact ordered subsetting and
the historical boundary that treats `p(A)` exactly at `0.5` as active over 48
stratified fibers across three subjects. Because the reviewed frozen fixture contains only the already-merged
branch matrix and not raw left/right rows, test `max_probability_union` with a
deterministic synthetic L/R fixture. Exercise row scheduling with an injected
synthetic producer; do not launch OSS-DBS or generate any real row during this
acceptance task.

- [x] **Step 4: Implement generic OSS orchestration**

Remove dTOR name checks. Require a realized final on the unique `formal`
connectome, explicit OSS backend/version, exact subject-side frequency maps,
row checkpoints, three default row workers, and deterministic merge order.
Before scheduling, validate every requested row and exact scientific cache key.
Skip each already present structurally valid final row; never use nearest-key matching.
Map left stimulation geometry to right canonical space before OSS modeling,
require exact L/R rows for every final subject, merge by elementwise maximum,
cache continuous probability, and derive binary fitting exposure with
the historical equality-accepting `0.5` boundary. Refit weights, signed
selections, and the `200/100/20` score in
each training fold without changing source, prediction, branch-role, or final
classification. For add-on rows, apply the inherited patient-by-feature
HF-overlap mask before every fitting and QC calculation. Test adjusted
fold-specific DeltaReferenceScore with non-affine subject-specific fold changes
that cannot disappear under standardization. Reject incomplete permutation
P values, invalid final-score correlations, non-lattice pPAM rows, and any
request that would publish artifacts before all validation succeeds.

Update planner/executor wiring so activation directly receives the final record
and cache hits remain usable with expensive producers disabled. Preserve the
global pre-service expensive guard for services that cannot prove cache-first
behavior; activation explicitly declares cache-first authorization handling.

- [x] **Step 5: Verify expensive-miss blocking**

Delete only a temporary synthetic cache row and run acceptance mode with
expensive producers disabled. Expected: `missing_acceptance_fixture`; the
injected producer invocation count remains zero and no OSS process starts.

- [x] **Step 6: Commit**

```bash
git add my_helper/fiber/core/dual_frequency/contracts/requests.py \
  my_helper/fiber/core/dual_frequency/contracts/records.py \
  my_helper/fiber/core/dual_frequency/backends/protocols.py \
  my_helper/fiber/core/dual_frequency/config/schemas/normative_fiber_model.schema.json \
  my_helper/fiber/core/dual_frequency/config/loader.py \
  my_helper/fiber/core/dual_frequency/backends/activation \
  my_helper/fiber/core/dual_frequency/workflow/planner.py \
  my_helper/fiber/core/dual_frequency/workflow/executor.py \
  my_helper/fiber/core/dual_frequency/tests/test_activation_universe.py \
  my_helper/fiber/core/dual_frequency/tests/test_oss_backend.py \
  my_helper/fiber/core/dual_frequency/tests/test_executor.py \
  my_helper/fiber/core/dual_frequency/tests/test_planner.py
git commit -m "feat: add reusable dual-frequency activation backend"
```

**Task 14 verification, 2026-07-15:**

- Cache-first row materialization was committed as `d4d40b39b`; fixed-axis
  pPAM endpoint fitting was committed as `15d2461c2`. The acceptance hardening
  contract was documented first in `12c420fc9`.
- Focused request/universe/OSS coverage passed `46/46`; the complete generic
  dual-frequency suite passed `207/207` in the `leaddbs` Conda environment.
- Python compilation for every touched Task 14 module and `git diff --check`
  passed.
- The mounted allowlisted OSS fixture passed structural, ordered-axis, and the
  then-current equality-accepting threshold replay. Task 17 reopens the `0.5`
  boundary for strict comparison. Synthetic tests covered exact ordered-axis cache identity,
  three-worker deterministic production, cache-first blocked misses, ten-sample
  probability lattice enforcement, add-on overlap exclusion, fold-local
  nuisance inputs, incomplete permutation handling, and prepublication input
  rejection.
- A second read-only review reported no remaining P1/P2 findings across the
  seven targeted acceptance gaps.
- No production YAML, OSS-DBS, FEM, formal model, or project output was run or
  written, and no bundle authority was created.

---

### Task 15: Implement Generic Reporting, Switch Registry, And Isolate Legacy

**Files:**
- Create: `my_helper/fiber/core/dual_frequency/runtime/input_provider.py`
- Create: `my_helper/fiber/core/dual_frequency/runtime/record_codec.py`
- Create: `my_helper/fiber/core/dual_frequency/runtime/service_adapters.py`
- Create: `my_helper/fiber/core/dual_frequency/reporting/endpoint_summary.py`
- Create: `my_helper/fiber/core/dual_frequency/reporting/artifact_index.py`
- Create: `my_helper/fiber/core/dual_frequency/reporting/run_report.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_reporting.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_runtime_import_isolation.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_runtime_dependency_boundary.py`
- Modify: `my_helper/fiber/core/dual_frequency/workflow/registry.py`
- Modify: `my_helper/fiber/core/dual_frequency/application/service.py`
- Move: `my_helper/fiber/core/outcome_models/` to
  `my_helper/fiber/projects/stnsnr/legacy/outcome_models/`
- Move: `my_helper/fiber/pipelines/run_configured_outcome_models.py` to
  `my_helper/fiber/projects/stnsnr/legacy/run_configured_outcome_models.py`
- Create: `my_helper/fiber/projects/stnsnr/legacy/__init__.py`
- Preserve Git history for moved files.

**Interfaces:**
- Produces generic endpoint/run reports and the production-only generic registry.

**Historical clarification gate, resolved 2026-07-15:**

- At that checkpoint, the executor request did not carry validated
  study/configuration/catalog inputs, no production service-adapter layer
  existed, persisted
  `ServiceResult` values do not restore typed scientific records, and Task 13
  formal/sensitivity backends were not complete. Therefore a production default
  registry could not be switched by registering those kernels directly.
- Endpoint/run report orchestration, a typed realized/fallback/no-final decision
  record, and the ordering of Task 13 versus the input-provider/service-adapter
  phase require explicit confirmation before implementation.
- While those choices were open, only architecture-independent prerequisites
  could proceed: a pure artifact index over exact current-run `ArtifactRef` values,
  runtime import/dependency isolation tests, and read-only legacy move auditing.
  Do not implement an implicit input provider, retain an empty registry as a
  production default, move the predecessor package, or choose a report
  orchestration model before confirmation.

**Architecture-independent prerequisite verification, 2026-07-15:**

- `reporting/artifact_index.py` now builds a deterministic JSON-safe index only
  from one typed current-run `RunResult` and its exact `ArtifactRef` values. It
  performs no filename or directory discovery, groups repeated references to
  the same immutable artifact, and emits no artifact for failed or skipped
  tasks.
- A clean subprocess imported every non-test generic runtime module and
  constructed `WorkflowService` with an explicitly injected empty test
  registry while all STNSNr/legacy project namespace patterns were blocked.
  This does not make the empty registry a valid production default.
- An AST boundary test rejects project imports, fixed STNSNr or legacy output
  strings, and raw `Path` annotations in public scientific backend signatures.
- The seven focused artifact-index/isolation tests passed; the complete generic
  suite passed `214/214` in the `leaddbs` Conda environment. Python compilation
  for all five new modules and `git diff --check` also passed.
- At that checkpoint these prerequisites did not satisfy Steps 1, 3, or 4 below. Endpoint/run
  reporting, typed terminal decisions, input-provider/service adapters, record
  restoration, and the production registry remained clarification-gated. The
  predecessor package and entrypoint had not yet been moved.

**Architecture decisions confirmed, 2026-07-15:**

- Reporting uses a post-executor terminal aggregator over the complete
  current-run outcomes and typed records. Ordinary report DAG tasks will not be
  used to infer terminal states through dependency/skip propagation.
- Add `FinalDecisionRecord` as the typed authority for realized primary,
  realized fallback, `no_final_model`, dependency failure, and execution
  failure. Persisted records must round-trip through an explicit typed codec.
- Implementation order is Task 13 formal/sensitivity backends, then the
  `RuntimeInputProvider`, service adapters, and typed codec, followed by the
  production registry switch and post-executor reporting integration.
- These decisions released the architecture gate. They did not retroactively
  mark any Task 15 step complete; each implementation and acceptance gate below
  remained required until its own evidence was recorded.

**Runtime and terminal contract confirmed for implementation:**

- `RuntimeInputProvider` is constructed from the already validated
  `StudyBaseRecord`, `ResolvedWorkflow`, endpoint catalog, and current-run
  artifact/cache services. It resolves exact endpoint subjects, clinical
  vectors, frequency-class exposure artifacts, connectome inputs, and
  replicate inputs. It never performs source resolution, prediction
  classification, final selection, formal statistics, or reporting.
- Cohort readiness is endpoint-local and frequency-derived. A subject with a
  valid configured reference endpoint but no source in the configured add-on
  frequency interval remains in the reference cohort and is excluded only from
  the corresponding add-on design. Runtime code must not hard-code subject IDs,
  phase IDs, or program IDs; it follows the validated endpoint binding and
  frequency-class configuration.
- `EndpointRecord.subject_ids` remains the clinically complete candidate cohort.
  The provider derives a separate ordered scientific-ready subject axis after
  source-frequency and artifact readiness checks. Reports expose candidate,
  included, and reason-coded excluded counts; they must not describe the
  clinical candidate list as the fitted cohort.
- Scientific services receive no project paths or mutable project namespace.
  Explicit service adapters decode typed dependency records, ask the provider
  for the remaining scientific inputs, construct the backend's typed request,
  invoke exactly one backend/strategy, and encode exactly one typed result.
- `ServiceResult` persistence uses an explicit allowlisted typed codec. The
  declared `output_record_type`, decoded dataclass type, and `record_id` must
  agree during initial execution and resume. Generic untyped JSON cannot stand
  in for `SourceRecord`, `BranchRecord`, `FinalModelRecord`, `FormalResult`,
  `SensitivityResult`, or `ActivationArtifact`.
- The planner no longer creates ordinary endpoint report tasks. The `report`
  cutoff means all selected scientific phases run first and the post-executor
  aggregator then writes endpoint/run reports. Lower cutoffs still write the
  technical terminal-decision and artifact-index documents for the stages that
  actually ran, but do not fabricate unrequested numerical report artifacts.
- The post-executor aggregator consumes the complete `ExecutionPlan`, endpoint
  catalog, `RunResult`, and codec-restored typed records. It performs no path or
  filename discovery and cannot invoke a scientific backend.
- Every requested endpoint receives exactly one `FinalDecisionRecord` using
  this precedence: a decoded realized final records primary or fallback;
  otherwise an endpoint-local failed task records `execution_failure`;
  otherwise a matched/cross-endpoint dependency failure records
  `dependency_failure`; otherwise the endpoint records `no_final_model` with a
  typed reason. A sensitive connectome deterministically uses
  `no_final_model` with reason `not_final_eligible_sensitive_connectome` and is
  reported as sensitivity evidence without a final ID.
- `FinalDecisionRecord` is a frozen generic contract with this minimum shape:

  ```python
  @dataclass(frozen=True)
  class FinalDecisionRecord:
      endpoint: EndpointKey
      decision_status: str
      final_model: FinalModelRecord | None
      reason_code: str
      causal_task_ids: tuple[str, ...]
  ```

  `decision_status` is exactly one of `realized_primary`,
  `realized_fallback`, `no_final_model`, `dependency_failure`, or
  `execution_failure`. Realized decisions require a same-endpoint
  `FinalModelRecord` whose own status and realization role agree; non-realized
  decisions forbid one. `reason_code` is always nonempty and causal task IDs are
  unique, deterministic, and refer only to the current plan. The record's
  identifier is a deterministic path-safe semantic ID from its typed identity
  fields.
- Final, formal, sensitivity, jitter, activation, and reporting artifacts never
  revise a previously decoded source, prediction, branch-role, or final
  decision. Aggregator failure changes the run's technical final status to
  failed but does not rewrite scientific classifications.
- Executor task completion is collected before run finalization. The service
  then builds decisions, endpoint summaries, run report, and current-run
  artifact index atomically; only after those steps succeed does `RunStore`
  publish the run's final `completed` or `failed` status. Resume reuses typed
  completed task records and deterministically rebuilds the aggregate files.

**Task 15 implementation refinement, 2026-07-15:**

- The three subject IDs discussed during data verification are not model
  configuration and must never appear in generic runtime logic. Candidate
  subjects always come from `EndpointRecord.subject_ids`; scientific inclusion
  is recalculated per endpoint from the configured binding, frequency class,
  required group-level E-field leaves, and minimum-subject rule. Missing add-on
  input excludes only that subject from that add-on endpoint and does not alter
  an otherwise valid reference endpoint.
- Existing canonical E-fields use the separately approved path-existence
  contract. The provider derives each exact leaf from the validated study
  record and binding; it does not scan directories and does not require a
  bundle, a VTA provenance sidecar, or `vta_model.yaml` as a downstream model
  input. It validates each declared file's existence and required structural
  properties while publishing typed run/cache artifacts; it does not generate
  or compare a cryptographic checksum.
- The provider reuses the generic Lead-DBS HDF5 connectome adapter. Its package
  entrypoint must expose existing public symbols lazily so importing the narrow
  connectome module does not eagerly import unrelated traversal/pipeline or
  optional JIT dependencies. This is an import-boundary change only; the
  connectome adapter and the package's public API remain unchanged.
- A continuous group consumes
  `delivery-continuous/joint/efield.nii.gz`; an alternating group consumes
  `delivery-alternating/derived/group-peak/efield.nii.gz`. All matching groups
  in the requested frequency class are included. `component_id`, target label,
  subject ID, phase label, and assessment-period names never classify a source.
- Add `PreparedExposureRecord` rather than overloading a single `ArtifactRef`.
  It carries the endpoint and exact subject/feature axes, the primary prepared
  exposure, canonical feature IDs, and the add-on-only auxiliary
  arrays required by DeltaReferenceScore, overlap exclusion, gain/total-
  exposure sensitivity, formal inference, jitter, and activation. Its artifact
  closure is complete and resume-safe. Direct voxel uses deterministic
  canonical-brainmask voxel IDs; normative fiber uses canonical connectome
  fiber IDs. Backend requests may omit direct-voxel IDs when the numerical
  kernel does not consume them, but the prepared record must retain them for
  map export, jitter, reporting, and exact resume identity.
- Add-on prepared exposure records carry an explicit DeltaReferenceScore input
  readiness status and reason. Missing reference-condition or add-on reference-
  component exposure invalidates only the adjusted branch; it does not remove
  an otherwise ready subject from the no-delta branch. Shape-preserving
  auxiliary arrays cannot be interpreted as proof that those inputs were
  observed.
- Add `EndpointInputRecord` with the clinical candidate IDs, scientifically
  included IDs, reason-coded per-subject exclusions, exact subject axis,
  baseline/outcome artifacts, and readiness status. A separate
  `SubjectExclusionRecord` uses generic reason codes only. The minimum-subject
  rule is applied to the included axis, not the catalog candidate count.
- `ReferenceDependencyRecord.reference_record` accepts the exact matched
  `SourceRecord` for final-eligible endpoints or `SensitiveRecord` for a
  sensitive-connectome endpoint. A noncomputable sensitive reference cell is
  treated like locally absent reference evidence: the no-delta branch remains
  eligible, while DeltaReferenceScore and the adjusted branch are unavailable.
  No sensitive endpoint can realize a final model.
- Remove both ordinary report tasks and synthetic catalog-terminal tasks from
  the DAG. Catalog-unavailable requested endpoints have no scientific tasks and
  receive their sole terminal decision from the post-executor aggregator.
  `through=report` still includes every selected scientific phase before the
  aggregator runs.
- Add the input-readiness record as an explicit dependency of observed and
  branch services. Add the reference dependency and Delta task state as direct
  dependencies of add-on final realization so `derive_branch_plan` can be
  evaluated from typed direct dependencies rather than implicit ancestor facts.
- Add `FinalSelectionRecord` as the typed output of every final-realization
  task. It is distinct from the aggregate-only `FinalDecisionRecord`:
  `FinalSelectionRecord` records the endpoint-local scientific state-machine
  result and therefore may contain either one realized `FinalModelRecord` or a
  closed `no_final_model`/dependency/execution state with deterministic reason
  codes. This avoids misclassifying a legitimate absence of a stable source as
  a task execution failure. Formal, sensitivity, jitter, and activation tasks
  consume only `FinalSelectionRecord.final_model` when the selection status is
  realized. The post-executor aggregator combines this selection with all
  endpoint task outcomes to produce the terminal `FinalDecisionRecord`.
- The v1 record codec root allowlist is exact:
  `EndpointInputRecord`, `PreparedExposureRecord`, `ArtifactRef`,
  `ObservedResult`, `SourceRecord`, `ReferenceDependencyRecord`,
  `DeltaReferenceBundle`, `BranchRecord`, `FinalModelRecord`,
  `FinalSelectionRecord`, `SensitiveRecord`, `FormalResult`,
  `SensitivityResult`, and `ActivationArtifact`.
  `FinalDecisionRecord` is aggregate-only. Endpoint/final/axis records are
  nested-only. Unknown roots, extra/missing fields, type-name mismatch,
  identifier mismatch, incomplete artifact closure, and malformed nested axes
  fail closed during initial execution and resume.
- Service adapters receive codec-restored direct dependencies, use the provider
  only for endpoint-scoped scientific inputs, call exactly one generic backend
  or pure state transition, and return `ServiceResult.from_record(...)`.
  Runtime facts are derived from the returned typed record; callers cannot
  supply contradictory type, identifier, payload, or artifact lists.
- Every downstream numerical task declares the typed input records it actually
  consumes as direct dependencies. A final-selection record alone is not an
  exposure or clinical-input container: formal, sensitivity, jitter, and
  activation adapters also receive the exact `EndpointInputRecord` and
  `PreparedExposureRecord`, plus the Delta bundle when an adjusted add-on final
  is possible. Adapters may slice the locked selected feature axis from these
  records but may not rediscover files or silently rebuild a second endpoint
  cohort.
- `execute_plan` returns task outcomes without finalizing the run. The
  application layer writes `final_decisions.json`, `endpoint_summary.json`,
  `run_report.json`, and `artifact_index.json` through a staged reporting
  directory and publishes them before the one final `RunStore.finalize` call.
  Aggregation is deterministic and is rebuilt on resume.

**Task 15 provider audit closure requirements, 2026-07-15:**

- A missing add-on-condition reference-component group or E-field is auxiliary
  DeltaReferenceScore unavailability only. It must not remove a subject whose
  clinical outcome and add-on-frequency exposure are otherwise ready from the
  no-delta add-on cohort.
- Add-on and matched-reference cohorts are joined by stable subject identity,
  not by positional equality. The add-on subject axis may be a strict subset of
  the ready reference axis. For each add-on held-out subject, select the matched
  reference LOOCV operator that excluded that same subject while retaining all
  other reference-ready training subjects, including reference-only subjects.
  Missing identity membership invalidates only the affected adjusted input; no
  subject ID may appear as a code or configuration exception.
- Normative-fiber bilateral exposure is computed as the arithmetic mean of the
  two hemisphere-specific fiber peaks after left-to-canonical mapping. Pointwise
  hemisphere averaging before the per-fiber peak is forbidden because the two
  homologous peak locations need not be the same point along a fiber.
- Full-connectome preparation must be bounded-memory. Production fiber matrices
  are written through temporary memory maps or an equivalent chunked
  publisher-owned destination; preparation must not retain all reference,
  add-on, auxiliary, and overlap matrices as independent in-memory arrays.
- Every add-on preparation validates the exact add-on endpoint, configured
  matched-reference endpoint ID, connectome, and ready dependency state before
  using reference evidence. Formal and final-linked requests likewise require
  exact endpoint, subject-axis, parent-feature-axis, and selected-axis identity.
- Direct selected indices and fiber IDs must retain their declared integer
  dtype, be ordered, unique, and in bounds. The selected feature axis is
  recomputed from the canonical parent axis, ordered selected positions or IDs,
  branch, selected tau, and selected Coverage; count equality alone is not
  sufficient.
- Adjusted observed/formal requests require both a valid
  `DeltaReferenceBundle` and a `PreparedExposureRecord` whose
  `delta_reference_input_status` state is `ready`. A valid bundle
  cannot override auxiliary-readiness failure.
- The configured left-to-canonical transform must be the transform actually
  consumed by the mapping operation. MATLAB may not silently choose another
  active-space transform. Every consumed left/right E-field, brainmask,
  connectome, and transform uses the explicit validated path; cached transformed
  output is published atomically under an interprocess lock and structurally
  verified before reuse.
- Provider acceptance tests cover asymmetric bilateral fiber peaks, missing
  Delta-only auxiliaries, dependency/endpoint mismatch, adjusted readiness,
  formal slicing, malformed selected axes, bounded preparation, transform
  selection, and concurrent cache reuse. Production-runtime import isolation
  is tested with the actual default registry, not only an injected empty test
  registry.
- Equivalence and smoke qualification are fixed internal test-suite gates, not
  endpoint-scoped production DAG tasks. Their parameters remain absent from
  public YAML/CLI, and production reports must not contain a completed
  `SensitivityResult` whose numerical work was actually `not_run`.
- Add-on normative-fiber plain/burden controls consume the realized final model
  and use the shared `FinalFiberControlStrategy`. Its separate cheap/exposure
  sensitivity stage uses the shared add-on comparison, direction-normalized
  gain, raw total-exposure, support, and collinearity strategy. These stages
  may not be replaced by typed placeholder documents.
- Adjusted add-on spatial jitter always perturbs and rebuilds the matched
  reference exposure/operator as well as the add-on reference component,
  overlap mask, support QC, and full/fold DeltaReferenceScore. It applies the
  same subject-ID cohort join described above; reusing original reference fold
  weights or restricting reference training to the add-on cohort is forbidden.
- Spatial-jitter settings include `translation_fwhm_mm`; runtime sampling derives
  `translation_sigma_mm = translation_fwhm_mm / 2.354820045`. A deterministic
  vector is keyed by replicate, condition/component, subject ID, and hemisphere,
  and shared by every leaf in the same stimulation group and side. Replicates
  use linear interpolation with zero outside the source grid, start from the
  realized final's selected axis, and release task-scoped temporary resources.
  Invalid or not-applicable DeltaReferenceScore support blocks only an adjusted
  replicate; no-delta jitter still executes and records that support state as QC.
- The generic OSS producer treats a continuous frequency group as one jointly
  modeled simultaneous row and treats an alternating frequency group as
  independently modeled source rows merged by elementwise maximum probability.
  In Task 17's PASS branch, left stimulation/electrode geometry is mapped to
  right-canonical space before physical OSS is evaluated once on the
  scale-independent `Omega_max` axis, and endpoint analysis selects the locked
  final-axis view by canonical ID. FAIL retains the completed per-final-axis
  producer.
  Cache hits require no toolchain; an authorized miss resolves the official
  Lead-DBS `OSS-DBSv2` environment internally, while public YAML remains free
  of executable/environment paths.
- Cache lookup does not need to materialize transformed electrode geometry. Its
  canonical-geometry identity is derived from the exact reconstruction bytes,
  reconstruction lead, source parameters, declared canonicalization method,
  and configured transform bytes. On an authorized miss, the producer must
  materialize that declared mapping before invoking OSS; modeling native-left
  geometry and mapping only the resulting activation values is forbidden.
- The production activation adapter performs one closed sequence: build the
  typed final-linked row request, resolve or produce every exact row through the
  scientific cache, construct one `ActivationRequest` from the materialized
  probability matrix and the same endpoint inputs, and invoke pPAM fitting.
  A row-materialization artifact is not itself a completed endpoint sensitivity.

The following default authorized-miss producer steps describe the proposed
PASS branch. They replace the historical final-axis preparation only after the
Task 17 gate passes; FAIL retains the completed producer contract. The producer
is project-neutral and consumes only the typed row request plus internally
resolved Lead-DBS/OSS dependencies. It must:

1. restore every geometry, stimulation-parameter, and locator document from its
   verified `ArtifactRef`;
2. require all sources in one continuous group to share reconstruction,
   electrode lead, frequency, control mode, and pulse width, and reject
   overlapping active contact identities instead of silently changing the
   simultaneous boundary;
3. construct one summed simultaneous contact boundary for a continuous group,
   or one single-source boundary for each alternating row; use the fixed
   rectangular, zero-relative-phase waveform and reject a continuous voltage
   group that mixes case-return and electrode-return sources because the MAT
   converter cannot preserve that boundary exactly; every active voltage
   contact has `fraction = 1.0`, current fractions sum to one independently
   within each polarity, and `case` is the sole anode in either control mode;
4. map left reconstruction/contact geometry with the exact transform declared
   by `study_base.json`; the declared `Composite.nii.gz` remains the forward
   image transform, while the provider deterministically requires and uses its
   sibling `InverseComposite.nii.gz` as the exact point-coordinate
   transform after x reflection, matching `ea_flip_lr_nonlinear`; MATLAB must
   convert mirrored RAS coordinates to LPS, call the locked platform
   `antsApplyTransformsToPoints` binary directly with the already selected
   inverse field and no additional inversion, and convert the mapped
   coordinates back to RAS. It may not rediscover another transform or
   introduce an SPM/NIfTI affine round trip into this template-to-template
   mapping;
   the MATLAB bridge must load the exact request-supplied reconstruction MAT
   directly and reject reconstruction-lead, electrode-model, or contact-count
   mismatches, and must reject a directional lead implanted perfectly along the
   x axis using the same geometry guard as the standard Lead-DBS OSS path; it
   must not initialize patient options or scientific settings from
   `ea_getptopts`, mutable GUI preferences, or directory discovery;
5. prepare the configured formal connectome, restrict its local axon allocation
   to the exact ordered scale-independent `Omega_max` axis, and preserve an
   explicit local-axon-to-canonical-fiber mapping; the filtered Lead-DBS file
   uses contiguous
   local IDs `1..K`, writes `idx` for those `K` fibers, and sets `origNum = K`
   so OSS percentages use the prepared maximal candidate universe rather than the
   parent connectome size; the parent fiber count remains mapping metadata only;
   both standard Lead-DBS point layouts (`4xN`/`5xN` and `Nx4`/`Nx5`) are
   accepted without changing the requested `Omega_max` axis order; regardless of the
   parent connectome label, this flattened filtered artifact is presented to
   the OSS axon allocator as one internal pathway and must not trigger a
   multi-tract parser;
   creation of the filtered HDF5 file is exclusive at the filesystem open
   operation, so a concurrent file cannot be truncated or overwritten; this
   path-based materialization is runtime producer infrastructure and must not
   widen the typed scientific-backend API to accept raw filesystem paths;
6. run the fixed ten equidistant 1--4 micrometer pPAM samples with the internally
   resolved official `OSS-DBSv2` environment, aggregate activated counts as
   `count / 10`, and return one `OSSRowProduct` on the requested fiber axis; and
7. use an isolated scientific-identity work directory and atomically publish
   only through the deterministic existence-based cache.

Before any external process starts, the producer validates every per-source
geometry, stimulation, frequency, and transform path/semantic ID from the
verified source documents, re-derives the aggregate deterministic row path from
the exact scientific settings, and rejects any mismatch. Embedded subject,
reconstruction, transform, and segmentation paths are confined to the
validated study subject roots or repository root as appropriate. Source-file
paths, sizes, and structural metadata are captured before execution and
rechecked before publication so a concurrent replacement is not accepted
during the same producer call.
Subject roots are keyed by `subject_id`; a locator for one subject cannot use a
different configured subject's directory. The producer also recomputes its
complete implementation
attestation immediately before external execution and again before returning;
that attestation must equal `settings.backend_version` used by the cache path.

The producer must not inherit scientific values from mutable Lead-DBS GUI
preferences. It freezes the currently verified template-space contract:

```text
template tissue segmentation = MNI152NLin2009bAsym/segmask.nii
conductivity model = ColeCole4 isotropic
patient DTI conductivity = disabled
axon model = McNeal1976
axon length = 10 mm
```

The serialized v7.3 MAT uses the converter-supported literal `no dti`; the
pinned converter normalizes that sentinel to an empty `DTIPath` and
`DiffusionTensorActive = false`. A MATLAB empty char array is forbidden because
the converter can decode its zero dimensions as nonempty NUL characters.

In the PASS branch, encode the template-segmentation ID, fixed-settings version, environment ID,
producer/bridge version, reconstruction ID, configured transform ID,
stimulation-unit ID, formal-connectome ID, and exact ordered `Omega_max` axis ID
in the deterministic scientific path. Cache lookup itself remains environment-free;
the FAIL branch retains the historical final-axis path identity.
only an authorized miss resolves and validates the installed OSS toolchain.
`OSS-DBSv2.yml` pins the upstream release/commit identifier and records the
declared installed-file inventory for `ossdbs` and `leaddbsinterface`, including
Python, HOC, MOD, session, and other packaged scientific resources. It also
records normalized entrypoints, Conda package inventory, Python distribution
inventory, and exact MATLAB version/release/architecture. The local producer attestation
includes the complete executed Python producer modules and the transitive
Lead-DBS/MATLAB coordinate, electrode-specification, and bridge helpers rather
than only the top-level bridge. The consumed platform-specific ANTs
point-transform executable is included as well. The pinned definition
participates in the cache identity; an authorized miss verifies every installed
lock and the MATLAB runtime immediately before and after every produced row.
Cached command paths may be reused, but cached validation results may not. The
converted JSON is also checked for template-space
segmentation, `ColeCole4`, inactive diffusion tensors, rectangular zero-phase
stimulation, requested frequency/pulse width/control mode, and active pathway
modeling before OSS starts. Electrode support is accepted only when the pinned
installed converter successfully resolves the exact reconstruction model; a
separate broader Lead-DBS model list is not treated as converter authority.
Every OSS console entrypoint is invoked explicitly through the validated
`environment_root/bin/python`; its mutable script shebang is never allowed to
select an unvalidated interpreter.

External producer stages write stdout/stderr directly to bounded work-directory
logs instead of retaining process output in memory. Each internal stage records
its new process-group ID immediately after `Popen` and has a fixed non-public
deadline; timeout uses that preserved ID, sends
TERM to that complete group, waits a bounded grace interval, and then sends
KILL to the same group even if the group leader has already exited. These
operational limits are not exposed through model YAML or CLI and do not alter a
successful scientific result.

Neither the toolchain nor its tests may contain a subject, phase, program,
scale, target, or endpoint allowlist. Endpoint membership is already closed by
`EndpointInputRecord.included_subject_ids`; Target/component labels remain
irrelevant to frequency classification and scientific cache identity.

**Generic OSS producer checkpoint, 2026-07-15:**

- The provider, deterministic existence-based row materializer, runtime connectome subset
  writer, installed-toolchain verifier, MATLAB canonical-row bridge, boundary
  assembler, and explicit inverse-coordinate mapper are implemented without a
  project subject/phase/program allowlist.
- The complete generic Python suite passed `387 tests` and `224 subtests` in
  the `leaddbs` Conda environment. The runtime dependency guard confirms that
  path-based filtered-connectome materialization remains outside the public
  scientific backend API. Regression coverage includes non-Python OSS package
  resources, all core Python producer modules, pre/post-row environment
  validation, validated-environment entrypoint binding, and a SIGTERM-resistant
  descendant whose group leader exits before cleanup.
- MATLAB contract tests passed `15 tests`: ten voltage/current boundary cases,
  one exact-transform unit test, two parameter-preparation cases including the
  directional x-axis rejection, one real asymmetric-coordinate integration
  comparison against `ea_flip_lr_nonlinear` using the explicit
  `InverseComposite.nii.gz` field, and one real pinned-converter MAT-to-JSON
  smoke proving DTI is disabled and waveform settings are preserved.
- The pinned installed environment resolved and validated
  `prepareaxonmodel`, `leaddbs2ossdbs`, `ossdbs`, and
  `run_pathway_activation` under `/opt/anaconda3/envs/ossdbsv2`. Converter JSON
  validation tests cover both voltage and current modes and reject DTI or
  control-mode drift before an external solver can start. Two consecutive live
  validations passed, demonstrating that executable paths are reused without
  caching the lock-validation result.
- This checkpoint did not run FEM, OSS-DBSv2 simulation, formal resampling, a
  production YAML workflow, or a scientific model rerun.

- [x] **Step 1: Write failing runtime-provider, codec, and generic-report tests**

Reports must contain reference/add-on fields and reject HF/ULF compatibility
aliases, filename discovery, and old summary roots. Sensitive connectomes emit
explicit sensitivity rows without final IDs; only formal-connectome/direct-
voxel realized finals appear in final-model reports.

Codec tests must reject an unknown record type, a type/name mismatch, a record
ID mismatch, and malformed nested `ArtifactRef`/axis identities. Provider and
adapter tests must prove that endpoint subjects and binding identities come
from the validated catalog/configuration and that scientific backends receive
typed arrays/artifacts only.

- [x] **Step 2: Write failing runtime import-isolation test**

Install an import blocker for names matching:

```text
legacy_*
stnsnr_*
run_stnsnr_*
projects.stnsnr
my_helper.fiber.projects.stnsnr
```

With the blocker active and relevant entries removed from `sys.modules`, import
and construct production `WorkflowService`, then run the project-neutral four-
model synthetic workflow through report using a fake activation provider.
Expected behavior after implementation is success, proving lazy task dispatch
does not import project code.

Add an AST dependency test over all non-test generic runtime modules. Reject any
`Import`/`ImportFrom` edge into the project namespace and any production string
literal containing fixed STNSNr roots, known legacy summary roots, or legacy
output filename templates. Also reject scientific backend public signatures
whose annotated fields include raw `Path` rather than typed request/artifact
contracts.

- [x] **Step 3: Implement runtime provider, service adapters, and typed codec**

Thread one explicit provider through `ExecutionContext` and
`TaskExecutionRequest`. Restore typed dependency records before adapter
dispatch, construct backend requests without filename discovery, and preserve
the same codec contract during resume. The provider must publish
`EndpointInputRecord` and `PreparedExposureRecord` values and must use only the
validated binding/frequency/path rules above; no subject-specific exception is
permitted.

- [x] **Step 4: Implement record-driven terminal aggregation and reporting**

Generate endpoint summary, artifact index, and run report only from exact
current-run records/artifact references. Report failure, skip, fallback, and
no-final states without fabricating numerical outputs. Emit exactly one
`FinalDecisionRecord` for every requested endpoint before finalizing the run.

- [x] **Step 5: Build the generic default registry**

Register every generic backend explicitly. Remove dynamic import dispatch. An
empty registry remains test injection only.

- [x] **Step 6: Move the complete predecessor runtime outside the core path**

After generic regression passes, use `git mv` to move the complete predecessor
`outcome_models` package and its tests into
`projects/stnsnr/legacy/outcome_models`. Move its public pipeline entrypoint into
the same legacy boundary and update that manual entrypoint's path bootstrap.
Do not move unrelated DWI/VTA scripts. No production module may import the moved
namespace. The move is archival isolation outside the generic core namespace;
the legacy package remains auditable but is never registered by production.

The moved manual entrypoint adds only its own `legacy` directory and the
existing generic `fiber/core/analysis` directory needed by predecessor adapters.
It does not recreate an `outcome_models` wrapper, symlink, or compatibility
package under `fiber/core`. The moved `cli.py` derives the repository root from
its new project path for legacy provenance. Historical tests move with the
package and may be run only with an explicit legacy `PYTHONPATH`; they are not
part of generic production discovery. Ignored `.DS_Store` and `__pycache__`
files are neither staged nor deleted as part of the tracked Git move.

- [x] **Step 7: Run import-isolation and full generic tests**

Expected: all generic tests pass with project migration/acceptance/legacy paths
blocked; predecessor historical tests may be archived rather than required by
the production package.

Completion evidence, 2026-07-15:

- `fiber/core/outcome_models` is absent and the complete tracked predecessor
  package, tests, and manual entrypoint retain Git history under
  `fiber/projects/stnsnr/legacy`.
- The generic suite passed all 387 tests with an explicit `PYTHONPATH` limited
  to generic `fiber/core` and `fiber` roots. The public generic entrypoint and
  the relocated manual legacy entrypoint both returned `--help` successfully
  without an inherited `PYTHONPATH`.
- The archived predecessor suite was also audited with an explicit legacy
  `PYTHONPATH`: 331 of 334 tests passed. The only three errors are the archived
  `test_two_scale_acceptance` cases reading the current generic workflow YAML
  through the predecessor schema, which intentionally does not accept the new
  `model_profiles`/`storage` contract. They are not production discovery or
  generic acceptance failures.
- Production code/config scans contain no fixed subject IDs or project-specific
  subject allowlist. Subject inclusion remains data-, configuration-, and
  readiness-driven.

- [x] **Step 8: Commit**

```bash
git add my_helper/fiber/core/dual_frequency \
  my_helper/fiber/projects/stnsnr/legacy \
  my_helper/fiber/pipelines
git commit -m "feat: switch to generic dual-frequency runtime"
```

The archival-isolation checkpoint was committed as `71cfa52ec` with the more
specific message `feat: isolate legacy outcome model runtime`. No remote push
was performed.

---

### Task 16: Run Final Structural, Smoke, Bounded-Parity, And Documentation Acceptance

**Files:**
- Create: `my_helper/fiber/core/dual_frequency/tests/test_synthetic_end_to_end.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_two_scale_smoke.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_goal_acceptance.py`
- Modify: `my_helper/stnsnr/four_model_yaml_core_refactor_plan.md`
- Modify: `my_helper/stnsnr/dual_frequency_core_decoupling_design.md`
- Modify: `my_helper/stnsnr/dual_frequency_core_decoupling_implementation_plan.md`
- Modify: `my_helper/stnsnr/four_model_execution_implementation_notes.md`

**Interfaces:**
- Produces final requirement-by-requirement evidence and completion status.

- [x] **Step 1: Add a project-neutral synthetic end-to-end test**

Use component/condition/connectome IDs that contain none of the forbidden
project terms. Run all four families through report with deterministic arrays
and a fake activation backend while the entire `projects.stnsnr` namespace is
blocked. Assert sensitive connectomes have no finals and each direct/formal
endpoint has one final or closed state.

Synthetic RED evidence, 2026-07-15: the first complete executor pass exposed a
generic add-on sensitivity adapter defect. The realized branch was correctly
restricted to `final.valid_feature_axis`, but the independently constructed
non-final comparison branch retained the full prepared feature axis. The
strategy therefore rejected the comparison before fitting. The repair must
reuse the realized branch's selected exposure/feature identity for the
non-final branch while preserving that branch's own nuisance design. It must
not rerun the source resolver, change branch role, or promote the non-final
branch. Three additional RED outcomes were synthetic-fixture contract errors:
jitter artifacts outside the configured output/cache roots and parent fiber IDs
without `fiber_id` units. Those fixture errors are corrected only in the
project-neutral test provider.

The next RED pass exposed a second generic adapter defect in the same add-on
sensitivity task: `total_exposure_request` reused the realized overlap-excluded
exposure even though its declared analysis requires the raw add-on component.
The repair selects `PreparedExposureRecord.total_exposure` on the already
realized final feature indices, preserves the raw artifact kind/units/space,
and changes no source or final identity. The synthetic parent fiber-ID fixture
also follows the production provider contract by using no units metadata;
`fiber_id` is an artifact kind/axis identity here, not a physical unit.

GREEN evidence: the project-neutral workflow executes all four families through
report in one temporary run with the project namespace blocked. It produces one
terminal final decision per catalog endpoint, gives sensitive connectomes no
final, makes exactly two fake activation calls for the two formal fiber finals,
and completes with exit code zero. The test contains no real subject, phase, or
program identifiers.

- [x] **Step 2: Add the named III/IV lightweight smoke**

Use the new STNSNr input/profile and existing exact caches. MDS-UPDRS III and
IV traverse the same ordinary endpoint-pair catalog/DAG path.
Use only internal-test permutation/bootstrap/jitter counts and block expensive
misses. Start `WorkflowService` directly from the existing `study_base.json`
while the project namespace is blocked, proving the runtime does not invoke the
importer.

GREEN evidence: the read-only smoke validates the current STNSNr
`study_base.json`, MDS-UPDRS III/IV test profiles, ordinary catalog, complete
report-through DAG, and endpoint readiness with project imports and expensive
cache misses blocked. A separate public-CLI `validate`/`plan` audit using the
production profiles reports 16 available endpoints and 136 tasks: each named
scale receives the same 68-task distribution (`reference_voxel=9`,
`reference_fiber=19`, `addon_voxel=12`, `addon_fiber=28`). The two named scales
are acceptance inputs only; no subject ID is fixed or special-cased.

- [x] **Step 3: Run the bounded numerical fixture suite**

Compare only the manifest allowlist. Assert the test suite fails if any excluded
task is added to numerical parity or if a missing fixture tries to start a
producer.

Pre-implementation read-only audit, 2026-07-15: the frozen reviewed manifest
contains 32 eligible tasks and 137 task/artifact files. Every file exists and
passes its recorded structural/schema/axis checks. The retained 12-test acceptance-tool suite also
passes without starting a producer. This evidence does not complete Step 3
until the generic goal-acceptance test enforces the same boundary.

GREEN evidence: the new eight-test goal acceptance enforces exact allowlist
membership, rejects excluded-task expansion, proves an unauthorized miss calls
no producer, revalidates every task/artifact path/schema/shape/axis, blocks project
imports, and detects literal subject allowlists. The retained 12-test bounded
tool suite also passes. No numerical parity scope was added.

Final-matrix RED evidence, 2026-07-15: after adding the goal-level guard, the
retained tool suite correctly rejected its module-level import of
`projects.stnsnr.acceptance` from the generic test tree. Production runtime was
already isolated, but the stricter retained-tool contract applies to every
Python file under `fiber/core`, including tests. The repair invokes the
read-only comparator in an isolated subprocess by explicit script path; no
generic module imports or registers the project tool, and the comparator remains
outside the runtime Python path.

GREEN evidence: the isolated comparator path passes all eight goal-acceptance
tests and all 12 retained-tool tests. The final complete generic rerun passes
397/397 in 27.929 seconds.

- [x] **Step 4: Run the complete test matrix**

```bash
conda run -n leaddbs env PYTHONPATH=my_helper/fiber/core:my_helper/fiber \
  python -m unittest discover \
  -s my_helper/fiber/core/dual_frequency/tests -p 'test_*.py' -v

conda run -n leaddbs python -m compileall -q \
  my_helper/fiber/core/dual_frequency \
  my_helper/fiber/projects/stnsnr \
  my_helper/fiber/pipelines/run_dual_frequency_models.py

git diff --check
```

Then run:

```bash
env -u PYTHONPATH conda run -n leaddbs \
  python my_helper/fiber/pipelines/run_dual_frequency_models.py --help

env PYTHONPATH=my_helper/fiber/core:my_helper/fiber \
  conda run -n leaddbs python -m unittest \
  dual_frequency.tests.test_application_cli.ApplicationCliTest -v
```

The second test creates temporary explicit study/model/workflow inputs and launches
the public script's `validate` subcommand. Expected: all tests pass, direct CLI
import succeeds, compile succeeds, and diff check is empty.

GREEN evidence, 2026-07-15: the final complete generic suite passes 397/397 in
27.929 seconds. The four direct application-CLI tests pass independently, the
public script displays `validate/plan/run/status/artifacts` with caller
`PYTHONPATH` unset, `compileall` succeeds, and `git diff --check` is empty.

- [x] **Step 5: Run runtime isolation scans**

```bash
rg -n "projects\\.stnsnr|my_helper\\.fiber\\.projects\\.stnsnr|legacy_|stnsnr_|run_stnsnr|frequency_1_reference|frequency_2_addon|/Volumes/VAL/STNSNr|/Users/mojackhu/Research/STNSNr|four_model_execution|\\bHF\\b|\\bULF\\b|\\bSTN\\b|\\bSNr\\b|\\bdTOR\\b" \
  my_helper/fiber/core/dual_frequency \
  my_helper/fiber/pipelines/run_dual_frequency_models.py \
  --glob '!**/tests/**'
```

Expected: no production hits. Test fixtures may mention forbidden names only in
negative assertions or isolated predecessor-acceptance modules. Run
`test_runtime_dependency_boundary.py` and the full import-blocked synthetic
workflow in addition to this text scan; text scanning alone is not acceptance.

GREEN evidence, 2026-07-15: the production-only text scan has zero hits. The
runtime import-isolation test and complete project-namespace-blocked synthetic
workflow pass. A separate scan for the three real subject IDs discussed during
data verification also has zero production-code/profile hits. Those IDs remain
data observations only; no real subject ID is an inclusion, exclusion, or test
allowlist constant.

- [x] **Step 6: Audit artifacts and process state**

Confirm every smoke task has a terminal record, every realized final has
`final_id_count < 2`, no sensitivity record has a final ID, `configuration_resolved.yaml`
and `configuration_sources.json` reproduce the configuration IDs and source paths,
report/index/manifests agree, old output trees are unchanged, and no Lead-DBS/
OSS/model process remains active.

GREEN evidence, 2026-07-15: the project-neutral temporary run records every
task as `completed`, one terminal decision per endpoint, no final ID for any
sensitive connectome, and exactly two activation calls for the two formal fiber
finals. The test reloads the profiles, reproduces both configuration IDs,
revalidates all four source paths, and checks agreement among the
run manifest, resolved configuration, task states, final decisions, report, and
artifact index. The bounded fixture audit revalidates all 137 files structurally.
Only temporary output roots were written; existing STNSNr outputs were not
modified, and the final process scan found no model, OSS, or MATLAB task.

- [x] **Step 7: Update documentation status with exact evidence**

Mark tasks complete only with test counts, run IDs, fixture identities, and artifact
paths. Keep any nonpassing requirement open; do not use partial evidence to mark
the `/goal` complete.

The completion evidence is recorded in this implementation plan, the sole
`/goal`, the approved design, and the implementation notes. The synthetic run
ID is `project-neutral-synthetic-e2e` inside a disposable temporary root. The
read-only real-data audit plans 136 tasks across 16 available endpoints. The
tracked bounded manifest is identified by its reviewed path, schema version,
exact task allowlist, and terminal file inventory.

- [x] **Step 8: Commit final acceptance documentation**

```bash
git add my_helper/stnsnr my_helper/fiber/core/dual_frequency/tests
git commit -m "docs: record dual-frequency core acceptance"
```

The complete implementation, acceptance tests, and final documentation evidence
were committed on `stnvop` as `a2c6ab37d` (`fix: close dual-frequency
acceptance gaps`). No remote push was performed.

---

### Task 17: Implement Two-Layer Shared Physical Preparation And Parallel Runtime

**Status:** `design_documented`; `code_audit_complete`;
`literature_review_complete`; `threshold_policy_change_authorized`;
`implementation_in_progress`; `partial_synthetic_acceptance_passed`;
`production_configuration_validated`; `corrected_production_main_completed`;
`canonical_publication_and_postprocess_accepted`;
`sensitivity_extensions_deferred_by_user`; `completion_gap_audited`.

**Authority:**
`my_helper/stnsnr/four_model_shared_exposure_performance_refactor_plan.md`.

This task supersedes the endpoint-specific exposure, payload-checksum cache,
thread-pool wave scheduler, and model-specific jitter preparation implemented
in Tasks 7-15. It reopens the final-axis-only OSS producer but replaces it only
if the bounded axis-equivalence gate passes. It does not reopen the scientific
resolver, classifier, fallback, or continuous-dose scoring definitions. It does
reopen the user-authorized threshold comparator: voxel/fiber exact tau values
are active, exact Coverage counts are eligible, and exact selected-reference-tau
values enter overlap. Support-QC retains its documented strict direction and
pPAM uses `p(A) > 0.5`. Formal
null-tail counting, hard minimum sample/feature
counts, identity checks, bounds, and numerical tolerances are not reopened.

**Historical implementation checkpoint, 2026-07-16.** The v2 directly copyable cache,
per-process verification set, strict array/shard metadata, cross-process
producer lease, global physical-subject exposure axes, exact
`Omega_max`, distinct voxel/fiber bilateral rules, sensitivity checkpoint and
extension command, missing-parent rebuild, completed-only resume restoration,
persistent event-driven spawn scheduler, parent-only persistence, resource
ledger, execution-segment manifests, and the then-authorized strict threshold boundaries are
implemented. The complete generic test suite passes. Production validation
resolves 28 scales, 224 available endpoints, and 1288 tasks through final
realization. The production rerun, measured resource matrix, hard-worker
recovery, source-absent sensitivity-cache reuse, single-write large-payload
conversion, and authorized OSS axis-equivalence decisions remain open.

**Scientific correction checkpoint, 2026-07-17.** The earlier v6 main and
jitter lineages used strict tau/Coverage/overlap boundaries and nonzero fold
candidate minima. They are historical execution evidence only and cannot be
resumed as the corrected formal result. The corrected profile retains
`n_subjects_min: 12`, sets every configured fold candidate minimum to one,
assigns `ppmi_85_ewert_2017` as the unique formal connectome, and requires a
new main lineage. Jitter and OSS-DBS are intentionally outside this corrected
main-run invocation.

**Bootstrap non-estimability checkpoint, 2026-07-17.** The corrected v7 main
lineage proved that valid subject draws can make a sample-specific baseline
nuisance design rank deficient even though the fixed endpoint design is valid.
`eat_10` first reaches this boundary at replicate 5 and held-out index 6;
`dsfs` reaches it at replicate 8784 and held-out index 11. Decision 26 treats
only these sample-specific cases as explicit replicate attrition. The draw
schedule and requested replicate axis remain unchanged, no replacement draw is
allowed, and the result records finite and non-estimable counts plus exact
nuisance-QC reasons. Original-design failure and provider/input/provenance
violations remain fatal. The repair applies to both direct-voxel and
normative-fiber bootstrap loops, followed by focused regression tests and a
resume of failed formal tasks only.

**Adjusted-bootstrap production-provider checkpoint, 2026-07-17.** The same
lineage exposed that the formal contracts rejected stale adjusted scores but
the production runtime did not yet construct the required task-scoped
`BootstrapNuisanceProvider`. Decision 27 closes that execution gap. Adjusted
bootstrap tasks directly receive both add-on and matched-reference input and
prepared records, the dependency and accepted locked source, the observed
DeltaReferenceScore bundle and the realized final. For each ordered subject
draw, the provider preserves multiplicity, refits the locked reference full
and all fold operators with the observed model's inclusive tau/Coverage,
partial-Spearman and benefit-orientation rules, and rebuilds raw full/fold
DeltaReferenceScore plus support and provenance. Direct voxel stays on its
locked selected voxel axis; normative fiber stays on its locked valid-union
fiber IDs and signed score settings. No per-replicate scientific artifact is
published. Dependency, identity, shape, axis, provenance and stale-score
violations remain fatal. Sample-specific matched-reference rank loss, absent
finite full or fold operators, invalid sampled support, and adjusted nuisance
rank or scaling loss are replicate attrition after the provider's static
contracts pass. Adding direct dependencies does not change the formal task IDs,
so the v7 run resumes completed work and reruns only failed or unfinished
tasks.

For adjusted bootstrap, successful rebuild-evidence rows and explicit
non-estimable rows are disjoint and jointly cover the requested replicate
axis. Reference and no-delta bootstrap remain provider-free and may contain
only the non-estimable table. This prevents a valid mixture of rebuilt and
attrited adjusted draws from being rejected by the result container.

**Corrected-formal checkpoint audit, 2026-07-17.** The v7 lineage completed all
1512 planned tasks with 1428 completed outcomes, 84 expected
`not_run_delta_inputs_invalid` skips, no failed outcome, 224 final decisions,
and 6773 indexed artifacts. The 84 skips are the two add-on-fiber branch tasks
for each of 28 scales on the two sensitive connectomes; they are not formal
failures. Formal execution created 112 realized primary or fallback finals and
112 sensitivity bases, split equally across the four model families. Jitter,
OSS-DBS, and combined-extension services were absent from the run.

The final audit found one extension-provenance defect before Task 17 closure.
`publish_sensitivity_checkpoints` received configuration-source identities as a
one-shot generator. The first base retained the ordered study-JSON plus three-
YAML identity rows, while the remaining 111 bases received an empty sequence.
Decision 28 requires the caller or publisher to materialize the identities as a
reusable tuple before endpoint fan-out. The repair does not alter scientific
arrays, task IDs, final decisions, or formal statistics. Acceptance reruns the
completed lineage through the three-gate resume path and requires exactly 112
readable unique bases, exact agreement with all realized-final endpoints, four
ordered source identities per base, and resolvable final-artifact references.
Only after this audit passes may the parent be accepted for a later independent
jitter or OSS-DBS extension.

Decision 28 is implemented by materializing the ordered source identities as a
tuple before checkpoint publication. A multi-base synthetic regression requires
every base to retain all four identities, and the complete 449-test
dual-frequency suite passes. A completed-only third execution segment then
republished the production checkpoint without rerunning scientific tasks: the
latest completed-task timestamp remains before the end of segment two. The
corrected production index contains 112 readable unique bases, every base has
four ordered source identities, the base endpoints exactly match 105 primary
and 7 fallback finals, and all 1548 base final-artifact references resolve into
the 6773-entry artifact index. The final run manifest is `completed`; all 1512
tasks are terminal with 1428 completed and 84 expected skips. This parent is
accepted for a later separately authorized jitter or OSS-DBS extension without
rerunning observed, resolver, or final-model work.

**Production resource checkpoint, 2026-07-16.** The first corrected all-scale
lineage reached 364 completed tasks with no failure before the initial shared
fiber exposure exposed a decoded-field working-set error. Sixteen canonical-
left float32 E-fields occupy about 4.2 GiB, which is `> 2 GiB`; the matching
sixteen right fields raise the full bilateral working set to about 8.4 GiB.
Both the original 2 GiB limit and the first 5 GiB correction are `< 8.4 GiB`,
so both repeatedly evict and decompress unchanged NIfTI files inside successive
connectome chunks. The affected lineages were interrupted without discarding
their completed task states. Before the replacement run, the target is a 10
GiB sampler budget, which is `> 8.4 GiB`, one structural NIfTI validation per
unchanged path and process, and a 13 GiB preparation grant that accounts for
samplers, the output memmap, process baseline, and bounded connectome chunks.
This is an execution-resource correction only; cache keys, task IDs,
thresholds, axes, and scientific outputs remain unchanged. Runtime code SHA is
recorded for provenance but does not invalidate completed task output.

**Full-cohort failure-closure checkpoint, 2026-07-16.** The next production
lineage used every available endpoint across all 28 scales. Reference endpoints
used all 16 study subjects; add-on endpoints used their 13 eligible subjects.
The lineage reached 876 completed tasks, 36 failed tasks, 106 dependency skips,
and 2 tasks left nonterminal before its parent process exited. It is preserved
as failed production evidence and is not an authoritative result.

Six failures showed that the bounded MATLAB left-to-canonical transform limit
of 300 seconds was `<` valid cold-production duration. The replacement limit
is 1800 seconds, while process-group termination, temporary-output quarantine,
and producer-lease cleanup remain mandatory. Thirty failures showed that an
add-on fiber preparation axis derived only from add-on `Omega_max` can omit a
fiber required by the locked reference valid union. For an accepted add-on
fiber dependency, the prepared axis is therefore the parent-ordered union of
the add-on primary `Omega_max` and the exact locked reference valid-union IDs.
The pure physical `Omega_max` cache remains unchanged. Missing parent IDs still
fail closed, and tau, Coverage, resolver, DeltaReference, and final-model rules
do not change. Finally, the measured persistent-worker peak of about 14.1 GiB
is `< 16 GiB`; the prepare-exposure resource grant is raised to 16 GiB while
the existing I/O ceiling continues to bound simultaneous cold producers.

These corrections change runtime code and the run-scoped add-on prepared axis.
The code SHA itself does not control resume. The replacement v6 lineage was
stopped after 202 completed tasks and 12 running tasks so the three-gate resume
contract could be implemented before further computation. v6 is the selected
resume root because its completed outputs were produced after the axis fix.

**Three-gate resume decision, 2026-07-17.** Resume accepts a run using only the
study-base JSON content SHA, the ordered content SHA values of the three input
YAML files, and each task-state JSON's completed result. It ignores code SHA,
derived configuration/scientific hashes, plan hash, resolved configuration,
paths, service or producer identity, and artifact revalidation as resume gates.
Non-completed or unusable task JSON is simply executed again. Code and resource
details remain execution-segment audit fields.

The three-gate implementation passes 418 dual-frequency tests and 224
parameterized subtests. Dedicated cases prove that changed code, plan,
derived-configuration, path, study-label, parent, and service audit fields do
not block reuse; changed study JSON or YAML content does block it; malformed or
incomplete completed-result JSON is rerun rather than aborting the lineage.

**Reference-parent-axis closure, 2026-07-17.** The resumed v6 lineage reached
844 completed tasks before two add-on fiber DeltaReference tasks exposed a
second axis-contract defect. Membership in the augmented add-on prepared axis
passed, but the locked reference selected-axis hash was incorrectly recomputed
against that augmented add-on parent. A reference selected axis is defined
against the matched reference prepared parent, not the add-on prepared parent.
The corrected DeltaReference task therefore receives both prepared records:
the add-on parent supplies ordered membership and exposure columns, while the
matched reference parent supplies the SHA used to reproduce the locked selected
axis. Neither comparator nor numerical operator changes. The interrupted v6
segment is retained and will continue through the same three resume gates.

The correction passes 419 dual-frequency tests and 224 parameterized subtests.
The added regression uses intentionally different reference and augmented
add-on parent identities while preserving the same locked valid-union IDs.

**Sensitivity-extension closure audit, 2026-07-17.** The implemented extension
command, checkpoint loader, isolated output tree, and rebuild mode are present,
but current target closure still inherits formal-permutation and formal-
bootstrap dependencies from the one-shot DAG. This violates the required
final-linked extension boundary and would expand a production jitter or OSS run
by high-resample formal work. Decision 18 therefore requires an extension-only
dependency rewrite that retains seeded parent prerequisites while executing no
observed, resolver, final-realization, or formal task. Decisions 19-20 also keep
source-absent prepared-cache reuse and the twelve extension acceptance scenarios
open. Production sensitivity execution remains blocked until those code and
test gates pass.

The audit also found that immutable extension-manifest annotation rejected a
workers-only resume. The corrected contract retains first-invocation resources
at the lineage level and records later effective resources in execution
segments, so worker changes do not become a fourth resume gate.
The persisted sensitivity DAG likewise omits the execution-configuration hash
while retaining its scientific hash and complete stable task graph.
Exact extension retries also preserve enriched artifact-index rows and compare
only their immutable identity fields.

The resumed production run exposed two sensitive add-on tasks where a realized
formal final and a noncomputable sensitive-reference evaluation published
opposite values under the same `formal_source_available` name. Decision 21
removes that cross-connectome alias: the sensitive evaluation publishes only
its own reference-acceptance fact, while the formal-final lineage remains the
sole authority for formal availability.
Because the three resume gates deliberately retain old completed results, the
executor also resolves facts from the nearest publishing dependency layer.
This preserves old numerical artifacts without allowing a deeper legacy fact
to override the task's direct scientific owner.

The correction passes 417 dual-frequency tests and 224 parameterized
subtests. The new cases verify parent-ordered axis union, reference-axis identity
binding, strict failure for a locked ID outside the parent connectome, artifact
materialization, the 1800-second process limit, and the 16 GiB scheduler charge.
The broader package-root collection remains outside this task because unrelated
packages currently fail import under the installed Numba and coverage versions;
no dual-frequency test failure is hidden by that environment issue.

**Completion-gap audit, 2026-07-17.** The running v6 lineage uses physical-row
cache identities and avoids endpoint-specific recomputation, but the cold
fiber producer still scans one connectome separately for each physical row.
It is not yet the required range-resident all-row pass. `ContentAddressedCache`
still copies a completed large temporary payload into staging while hashing it,
so single-write final-shard publication also remains open. Production jitter
still hashes and opens physical sources before resolving a prepared cache key,
which means source-absent cache reuse is not yet implemented. The persistent
executor has a fault-free single-generation path but no hard-exit generation
replacement, heartbeat timeout recovery, or periodic live-memory
reconciliation. The v6 run remains valuable compatibility and checkpoint
evidence, but it cannot close those performance and recovery gates. Decision 22
in `task17_design_decisions.md` records the required implementation boundary.

**Production extension-closure audit, 2026-07-17.** The completed v6
checkpoint contains 1204 completed seed outcomes. The existing combined jitter
and OSS compiler selects 588 tasks: 476 observed-phase specifications and 112
sensitivity targets. The targets require only 308 distinct direct parent
records, all of which have completed seeds. Recursive ancestry expansion also
selects 28 intentionally skipped observed branches without completed seeds and
would make them executable in the child run. Decision 23 replaces that closure
with completed direct-parent roots. It also requires two-stage checkpoint
loading so final artifacts and shared entries are validated before execution
while unrelated historical seed outcomes are never rehydrated or payload-
hashed. Restored records keep their parent-run causal IDs; reporting treats
those nonlocal IDs as parent provenance instead of reintroducing historical
tasks into the executable extension DAG.

**Compact extension checkpoint implementation evidence, 2026-07-17.** The
loader now validates the parent manifest, all 84 realized bases, the declared
final artifacts, and shared-cache entries before parsing seed records into a
metadata-only index. The production combined plan contains 420 child tasks:
308 dependency-free checkpoint roots and 112 jitter or OSS targets. It contains
no executable observed task and no formal task. Only those 308 completed parent
outcomes are rehydrated. Checkpoint-only roots fail before pool creation when a
completed state is absent, and extension reporting preserves historical causal
IDs as validated parent lineage. The focused extension tests and the complete
427-test dual-frequency suite pass.

**Jitter production audit and revised implementation boundary, 2026-07-17.**
The first 12-worker production jitter extension restored 308 checkpoint roots
and submitted 12 reference-voxel endpoint tasks. All 12 reached the same first
replicate cache key. One worker used one CPU core as producer while the other 11
waited inside the cache lease, and the producer began a 16 by 8465824 full-grid
matrix. The run was safely stopped before a jitter entry was published. Decision
24 replaces endpoint-led production with fixed 25-replicate physical block
tasks on reduced union axes. The production union counts are 386 reference
voxels, 418 add-on voxels, and 10098 formal fibers. Cache-first block lookup,
source-absent reuse, generated-entry single-write publication, and endpoint
in-memory selection are required before the production extension is resumed.
The reduced add-on block path is branch-aware. No-delta finals rebuild overlap
but do not rebuild unused DeltaReferenceScore evidence. Adjusted finals require
complete-parent support evidence in addition to the reduced selected axes;
until that evidence format exists, they remain on the full-parent provider. The
current production checkpoint contains only no-delta add-on voxel finals.

The next block exercise, retained as `task17-jitter-v2-20260717`, showed that
loop order is also part of the resource contract. Traversing all subjects once
per replicate defeated the 10-GiB production sampler LRU and repeatedly
decompressed identical NIfTI payloads. Twelve workers remained CPU-busy for
more than three minutes without publishing a block. A block producer must
traverse component and physical subject first, then sample the complete fixed
replicate interval while that subject's source samplers are resident. This
preserves replicate-keyed RNG identity while bounding each block to one source
load per physical row. The v2 run was safely stopped before cache publication.

The reordered v3 exercise then exposed admission undercharging. Twelve
reference-voxel producers reached roughly 40 GiB of child RSS before the first
block was published. The scheduler had charged 2 GiB per producer even though
the runtime permits a 10-GiB sampler cache, and its managed-memory predicate
limited an individual grant without limiting the cumulative active grants.
The v3 run was safely stopped before cache publication and did not grow swap.

The cumulative-ledger v4 exercise admitted six reference-voxel producers at
8 GiB each. After roughly 11 minutes, per-worker RSS had passed 8.5 GiB and the
summed child RSS had passed 51 GiB without publishing a block. Memory pressure
remained low and swap did not grow, but the declared 48-GiB managed boundary
was no longer conservative. The v4 run was safely stopped before cache
publication.

Charge every physical jitter block 12 GiB and give a fiber block one additional
connectome-I/O slot. Enforce the 48-GiB normal managed ceiling over cumulative
active grants while retaining the strict
`projected_available_after_admission > reserve` predicate. With the public
worker ceiling at 12, admit at most four voxel producers or two fiber producers
concurrently; current available memory may lower those counts. Later ranges
remain eligible for the same persistent workers so their resident samplers can
be reused.

The v5 production exercise exposed a remaining scheduling boundary. After all
80 voxel blocks completed, their 56 endpoint statistics became runnable while
40 reference-fiber blocks remained. The endpoint work expanded the pool from
four processes to twelve, so later fiber ranges could rotate onto cold idle
workers despite the two-slot connectome-I/O limit. Hot fiber blocks took about
1.2 minutes, while two cold blocks took about 13.7 minutes and sampled inside
NIfTI gzip decompression. The 32 reference E-fields occupy about 8.27 GiB
uncompressed and fit below the 10-GiB sampler ceiling, so increasing that
ceiling is not the accepted fix. v5 was stopped with 80 voxel blocks, 23 fiber
blocks, all 56 voxel endpoint results, 103 complete block cache entries, no
producer lock, and no swap growth.

Compile a global physical-block barrier whenever reduced-axis block production
is active. Every jitter endpoint target depends on the complete ordered set of
physical-block task IDs. The one persistent pool remains at the producer
population until all 120 blocks complete; the 84 endpoint statistics may then
use the full public worker ceiling. Preserve every block key, fixed range, RNG
identity, cache descriptor, and endpoint numerical input. Providers without
physical-block capability retain the legacy typed-provider dependency path.

- [ ] **Step 1: Freeze parity fixtures and characterize every resource path**

Preserve deterministic brute-force direct-voxel, normative-fiber, jitter, OSS,
formal, pPAM, and sensitivity fixtures before implementation. Profile each stage
at `execution.workers = 1` and the current configured value `3`. Preserve the
historical equality-accepting fixtures as migration evidence and add target
fixtures in which exact tau, Coverage, overlap, support-QC, and `0.5` pPAM
values are excluded; only enumerated
boundary rows may differ from the historical result.

Record wall time, aggregate CPU time, effective cores, peak RSS, swap, source
and scratch bytes, E-field/NIfTI opens, sampler builds/rebuilds/evictions,
hot-loop path/stat/hash/lock calls, connectome coordinate/fourth-row bytes,
point-range skew, pool and nested-executor creations, full-payload read/write/
checksum-reread bytes, inline semantic-digest input bytes, memmap flushes,
selected-exposure copies, artifact-index rewrites, ready-queue depth,
dependency/CPU/memory/I/O/solver wait, token occupancy, worker idle fraction,
cancel/timeout/retry counts,
formal-operator bytes, null `N x F` allocations, filtered-connectome builds,
toolchain attestations, and active solver threads.

- [ ] **Step 2: Establish directly copyable SHA cache and single-write publication**

Implement `<cache_root>/shared_exposure_v2/<kind>/<semantic_sha256>/` with one
canonical `manifest.json`, one payload SHA per final file or shard, strict
structural metadata, and a process-local verified set. Complete entries may be
copied directly into their final semantic directory. There is no importer,
incoming area, installation marker, machine identity, cache-instance identity,
generation ID, or persistent verification database.

At first lookup in every process, reconstruct and validate semantic SHA,
manifest schema/completed state, exact file set, every payload SHA, byte count,
dtype, shape, ordered axes, units, space, and ordered shard intervals. Add the
semantic ID to the process-local verified set only after every check passes.
Later consumers in that process do not repeat payload hashing. A new main,
resume, or sensitivity-extension process verifies each used entry again.
Partial or corrupt direct copies fail closed but are not deleted, moved, or
adopted automatically.

Add publisher-owned final-format NPY writers or final range shards so a producer
writes, flushes, and closes each large byte once. The parent publishes an
ordered shard manifest rather than merging into a second monolith. Cache hits
are resolved before full staging allocation. Add logical
`IndexedArrayView(parent, rows, columns)` records whose kernels gather bounded
blocks; full `np.asarray()` and implicit fancy-index copies are forbidden. A
contiguous external-tool boundary must be explicit and metered. Use a parent-
only artifact journal/snapshot writer; endpoint/final tasks may not copy a
payload merely to give it a new task-local name.

One manifest describes the complete shard set. It requires every listed shard
to exist and requires strictly ordered, nonoverlapping intervals with
missing-range count `< 1` over the declared logical axis. Duplicate,
reordered, overlapping, missing, and undeclared shards fail closed. Orphan
producer staging directories are ignored; add one corruption fixture per
invariant plus crash-before-manifest and partial-direct-copy acceptance.

Bind cache identity per artifact. Raw physical exposure includes the ordered
physical-row identity, model domain, canonical grid/connectome content SHA,
source content SHA values, and producer version. Tau/Coverage support and `Omega_max`
also include the exact ordered eligible cohort, exact ordered tau and Coverage
grids, and `inclusive_threshold_v1`. PASS-branch OSS includes the selected
`Omega_max` axis and solver/toolchain producer identity; FAIL retains the
historical final-axis identity. Canonical JSON SHA selects the path; payload SHA
and structural checks validate copied bytes. Device, inode, mtime, and absolute
path are runtime locators or provenance only and never enter identity.

- [ ] **Step 3: Implement distinct voxel sampling and shared physical rows**

Resolve unique physical subject/program/frequency-component units before
endpoint fan-out. Bind an immutable `SamplingPlan` before the voxel/fiber hot
loop. Canonical paths, left transforms, shape/affine, sampler descriptor/cache
key, translation, frequency grouping, and source content SHA values are resolved
once. Workers validate structural source requirements once on open and the
parent validates final payloads before publication. Replace global sampler clears
with byte-bounded row-batch leases; never pin private samplers for every physical
row simultaneously. Optionally canonicalize compressed NIfTI to a versioned
read-only float32 memmap.

Produce one bilateral direct-voxel row per physical unit and group only exact
grid identities. Direct-voxel thresholding includes exact tau, Coverage, and
selected-reference-tau values. Preserve the voxel sampling rule independently from the fiber
sampling rule.
Endpoint inputs are ordered row/column views; scale, outcome, worker count, and
run identity do not enter physical paths.

- [ ] **Step 4: Implement audited, point-balanced one-pass `Omega_max` fiber preparation**

Cold-audit each `(semantic connectome ID, source content SHA, cache schema)`
once, including `idx`, fourth-row IDs, point
boundaries, dtype, chunks, and compression. Construct point offsets once
and represent the complete `1..N` axis implicitly. The audited hot path reads
the compressed source as required but materializes only coordinate rows into
application memory, allocates no point-sized expected-ID vector, and performs no
NIfTI/path/transform-lock operation inside the range loop. Raw chunk reads and
decompression are measured separately.

Derive normative-fiber minimum tau/Coverage from its profile; these values do
not define the voxel model. Load geometry into shared read-only storage when
`geometry_bytes < shared_resident_budget`; otherwise use the fewest safe sequential ranges balanced by cumulative
point bytes. Ranges never split a fiber and minimize partially shared HDF5
boundary chunks; logical point coverage and raw chunk overlap are measured
separately. While a range is
resident, evaluate every physical row using side-specific maxima followed by
their mean. Normative-fiber thresholding also includes exact tau, Coverage, and
selected-reference-tau values.
Retain exact
`Omega_max`, publish continuous values once, and prove
that no full/fold cell loses a candidate. Endpoint, scale, branch, grid, and fold
work may not reopen raw geometry.

- [ ] **Step 5: Move jitter into Layer 1 and gate shared OSS/pPAM preparation**

Generate one scale-independent jitter schedule per physical identity while
preserving the current exact key: `binding_id + frequency_class + subject_id +
hemisphere + replicate_index + replicate_seed`. Worker and completion order do
not enter it. Publish bounded physical-exposure blocks that reference invariant
axes and base exposure but contain no clinical data. Downstream Layer-2 tasks
load their endpoint clinical workspace once. Every replicate retains immutable
logical exposure/overlap/support evidence and, when adjusted, its own Delta
rebuild identity; block storage removes copies but not scientific evidence.

Before replacing the historical final-axis solver, run an explicitly authorized
bounded decision matrix. For every distinct allocator-relevant equivalence
class used by the run, final-axis and `Omega_max` inputs for the same physical
row must produce ten-sample axon-state/count mismatch count `< 1` and
probability `absolute_difference < accepted_probability_tolerance` for every
shared fiber. If allocator/RNG behavior depends on axis size/order, retain the
per-final-axis producer for that class until a separately accepted fiber-keyed
correction passes. Every real-OSS miss requires explicit expensive-producer
authorization.

Persist one immutable `OSSAxisEquivalenceDecision` per exact class, keyed by
allocator and solver/toolchain versions, connectome and cache schema, tested
final/`Omega_max` axis pair, physical-row identity, RNG contract, comparison
fields, and accepted probability tolerance. One decision authorizes only its
exact class. Global PASS scheduling requires durable decisions covering every
distinct class used by the run. An absent or changed identity returns that
class to unproven and retains FAIL behavior until its newly authorized proof
passes.

On PASS, prepare OSS/pPAM rows on formal-connectome `Omega_max`, build one
filtered connectome/mapping per `(connectome, axis, schema)`, and let endpoints
select final columns by canonical ID. On FAIL, keep the existing per-final-axis
request/cache/artifact producer and record why shared simulation is unsafe. In
both branches, coalesce consecutive selected fibers into HDF5 point ranges, use
one `CanonicalFiberAxis` descriptor per batch, keep row manifests O(1) in fiber
count, and avoid repeated `fiber_ids.npy` or per-fiber cache items. Attest the
immutable toolchain once, retain semantic provenance, and use a lightweight row
guard. Endpoint analysis applies add-on overlap at the existing boundary and
refits all outcome-dependent statistics. Binary pPAM activation uses strict
`p(A) > 0.5`; equality at `0.5` is inactive.

- [ ] **Step 6: Implement sensitivity checkpoints, extension runs, and missing-parent rebuild**

Publish one durable `sensitivity_base.json` for every realized final. It binds
the parent run/model identity, scale, final branch/role, selected source,
subject/outcome/nuisance axes, shared exposure semantic ID, final artifact
references, E-field/transform/connectome source-content identity, `Omega_max`
and OSS gate state when applicable, producer/schema versions, and RNG schedule
identity. Reject every scratch URI.

Add an application command with explicit `--base-run`, `--analyses`, `--run-id`,
and resource controls. With a complete parent checkpoint, compile only requested
jitter, OSS, or other final-linked sensitivity tasks and write a separate child
run. Publish canonical extension results below a unique
`extensions/<extension_id>/` path. Observed, resolver, and final-model rerun
count for this path is `< 1`.

Add explicit rebuild mode with complete normal-run study-base and profile
inputs. If the parent run or any required observed, resolver, final-model, or
sensitivity-base artifact is absent, create a new parent lineage, execute the
missing main chain through final realization, publish a new checkpoint, and
then start the extension. Never repair or mutate a partially deleted lineage.
If `study_base.json` is missing, require the explicit project-owned upstream
converter command before the generic runtime; do not import project code.

Permit statistics from an exact prepared jitter or OSS cache when physical
sources are absent. Require source E-fields/transforms/connectome/toolchain for
new physical production. Missing source and missing prepared cache fail as
`missing_sensitivity_source`. Extension resume restores only valid completed
extension tasks and re-evaluates dependency-derived skips.

- [ ] **Step 7: Implement one persistent spawned scheduler and global resource ledger**

Introduce an importable worker entry point and pure-data `WorkerCommand` with
only direct dependency envelopes, paths, small configuration, and granted
resources. Reconstruct worker-local providers/registries in an initializer;
keep scheduler, gates, retries, RunStore, and artifact-index mutation in the
parent. Large arrays are reopened as read-only memmaps/shared resources and are
never passed through pickle.

Replace per-wave threads with one persistent macOS `spawn` pool generation in a
fault-free run. Compile
indegree/reverse edges once; use a bounded event-driven ready queue that admits
newly unlocked work immediately and favors critical prerequisites plus current
connectome/grid grouping. With a standard process pool, affinity relies only on
shared memmap/page cache and worker-local hits are best effort; actor queues
require separate acceptance. Fail-fast cancels queued work. Add heartbeat/
timeout and retry only for declared idempotent transient-safe tasks. A timed-out
producer releases tokens only after worker/subprocess termination, lease
revocation, and temporary-output quarantine; test stale-lock/orphan recovery.
For Python/h5py hard timeouts, recycle the complete pool generation and classify
every in-flight lease. Only a separately supervised external subprocess may be
terminated without necessarily replacing a healthy Python pool.
Hard exit or `BrokenProcessPool` ends the generation; after invalidating old
leases, a supervisor may create a recorded replacement and requeue only declared
idempotent/transient-safe work. Add hard-exit/generation-restart acceptance.

Keep `execution.workers` as the sole public n_jobs-like CPU ceiling. Its current
default remains `3`; `12` is a benchmark scenario, not a default and not a list
of CPU core IDs. Give every task CPU, memory, connectome-I/O, external-solver,
and internal-parallelism requirements. Remove nested executors outside this
ledger. Set numerical-library limits before worker imports, verify actual BLAS/
OpenMP threads, and keep every Python worker at one numerical-library thread for
its lifetime. Give OSS/MATLAB subprocesses explicit tokens and thread
limits. The sum of Python baseline, extra BLAS/OpenMP, and solver CPU tokens must
remain `< execution.workers + 1`; solver-instance slots grant no extra CPU.
A compiled GIL-releasing kernel may use a separately declared thread resource
class only after measured parity, utilization, and oversubscription acceptance;
h5py-call-heavy and Python-bytecode-heavy preparation stays process-based.
Define `reserve = max(16 GiB, 20% physical RAM)` and
`managed = min(48 GiB, max(0, currently_available - reserve))`. Charge expected
MATLAB/OSS RSS and per-reader HDF5 raw chunk caches to task memory rather than
the reserve. Normal admission requires `task_memory_bytes < managed` and
`projected_available_after_admission > reserve`. Otherwise the task remains
pending or runs alone under an explicit measured override that still preserves
the reserve and `swap_delta_bytes < 1`. Periodically reconcile live process-tree
RSS, available memory, shared-memory charges, child RSS, and outstanding grants,
pausing new admission when the strict reserve predicate fails.

Resume uses only three gates: study-base JSON content SHA, ordered content SHA
values for the three input YAML files, and a parseable completed task JSON with
a decodable result. Failed, running, skipped, missing, malformed, and
result-incomplete task JSON is rerun. Append code and resource provenance to a
separate execution-segment manifest without using either as a resume gate.

- [ ] **Step 8: Vectorize grid, statistics, and fiber-scoring kernels**

Cache compact/block-streamed tau exceedance and Coverage operators by exact
axis and derive training-fold counts by held-out subtraction. Fit baseline-only
LOOCV once per endpoint/fold. Apply exact cell masks to endpoint/fold weights on
maximal valid support; sensitive fixed-cell work computes only requested cells.

Add a finite-data partial-Spearman fast path with exact average-tie ranking,
rank-aware multi-RHS residualization, and block correlation, while retaining
the scalar nonfinite fallback. Add a prevalidated fiber-score workspace that
reuses only ordered axes, invariant exposure-finiteness validation, and top-k
scratch. Candidate masks,
finite-weight masks, and signed weights/order are recomputed for every outcome,
replicate, and fold; observed state may not leak into null or held-out work. Observed results
retain complete IDs/metadata; null calls return only required scores and support
state. Preserve fold-only fitting, tie order, continuous values, signed
selection, and finite-weight intersection.

Update support-QC classification to strict cutoffs only, including cohort
median `< 0.20` and subject fraction `< 0.25` for `adequate`; add exact-cutoff
fixtures so equality is not silently included in either class.

- [ ] **Step 9: Shard formal, bootstrap, pPAM, jitter, and sensitivity safely**

Shard direct/fiber permutation and bootstrap, pPAM permutation, and spatial
jitter by fixed replicate-index blocks independent of worker count. Jitter keeps
its existing keyed streams. Formal/bootstrap/pPAM preserve the historical single
continuous `default_rng(seed)` stream by reproducing the historical method-call
sequence and argument shapes, then lending parent-pregenerated slices or saving
BitGenerator state at exact historical call boundaries. A generic draw-count
split is invalid. Advance/jump is allowed only with the historical BitGenerator
and with NumPy version, BitGenerator class, build/environment/platform
fingerprint, and call-plan schema pinned in provenance, plus full-call-pattern
byte mismatch count `< 1`. A cross-environment resume reruns parity before
claiming byte identity; new
per-replicate streams are not allowed. Candidate/sign/selection/exceedance
mismatch count is `< 1`. Float moments use a fixed reduction tree independent
of assignment and satisfy `absolute_difference < existing_serial_tolerance`;
any field requiring bitwise history retains serial replicate
accumulation order. Bootstrap still refits each replicate, and adjusted add-on
inference refits its matched reference.

Create read-only fold operators once as parent-managed run-scoped scratch
memmaps, not permanent scientific artifacts. Account for their bytes and block
scratch in admission, reopen them by descriptor, and provide crash-recoverable
cleanup so worker count does not multiply them.

Add statistics-only null paths that do not allocate retained `N x F` outputs.
Use task-scoped sensitivity workspaces for exposure, outcomes, baseline, axes,
and nuisance operators; apply overlap in chunks/views and release each jitter
block after durable publication. Do not cache replicate-specific overlap,
nuisance, support, or Delta state as invariant.

- [x] **Step 9A: Add default final in-sample inference and paired formal reporting**

Add one `formal_in_sample` task for every realized final endpoint whenever
formal permutation is planned. This is a required formal stage with no new
YAML enable flag, block-size field, selection-scope field, or RNG field. It
inherits the existing endpoint permutation count and resolved seed. Future
main plans include the task automatically; the completed v8 parent is handled
through the existing extension command with analysis name `final_in_sample`.

Introduce a typed in-sample request that carries the full prepared exposure
and canonical parent feature IDs rather than `final.valid_feature_axis`, which
may contain an outcome-derived valid union. Reconstruct the outcome-independent
candidate voxel or fiber mask from the actual selected tau, Coverage, branch,
overlap rule, and prepared exposure. Publish and identity-bind the resulting
candidate IDs. Fail closed if the source/final key, parent axis, candidate IDs,
subject axis, or DeltaReference input does not match the inherited final model.

Implement independent direct-voxel and normative-fiber full-sample kernels.
For the observed outcome and every Freedman-Lane pseudo-outcome, refit weights,
benefit orientation, full-sample score, and outcome regression. Fiber also
reselects sweet, sour, and weighted-peak IDs every time. Do not call the LOOCV
fit as a shortcut and do not reuse observed or fold-specific fitted state. The
primary null statistic is Spearman rho between each pseudo-outcome and its
own full-sample fitted prediction.

Publish a compact residual-permutation index schedule with subject-axis ID,
resolved seed, BitGenerator identity, RNG-contract version, requested count,
and schedule digest. New main runs give both formal paths the same schedule but
retain separate fits, and claim sharing only when both schedule payload SHA
values match. The historical v8 parent has no schedule artifact, and its null
statistics do not identify the subject-index rows. Its child therefore reports
`independent_deterministic_schedule` without paired-replicate claims.

The first implementation uses one endpoint task and one complete null array,
matching current LOOCV persistence. It adds no 250-replicate block and no
block-level resume. Valid completed endpoint JSON is reusable; failed,
interrupted, malformed, or incomplete endpoints rerun in full. Later Step 9
sharding may refactor both formal paths together only after the historical RNG
and worker-invariance gates pass.

Mirror the LOOCV report with in-sample Spearman rho and nominal p, Pearson r
and nominal p, plus-one two-sided permutation p, standard R2, nuisance-relative
R2, model and baseline RMSE/MAE, finite-subject evidence, finite-prediction
evidence, and finite-permutation counts. Derive `loocv_r2` from inherited
held-out predictions without refitting. Do not report adjusted R2. Emit
Spearman, Pearson, standard-R2, nuisance-relative-R2/Q2, RMSE, and MAE optimism
gaps only when both sides use the same transformed outcome, subject order, and
finite mask.

Apply Benjamini-Hochberg correction to complete formal raw permutation p values
within each model family's 28 predeclared scales and across all 112 endpoints.
Do not multiplicity-adjust nominal correlation p values in the primary report.
If a predeclared correction family is incomplete, withhold that correction
layer and report the missing endpoint IDs.

Extend `SensitivityExtensionRequest`, extension-plan compilation, canonical
extension publication, artifact indexing, and resume tests for
`final_in_sample`. The extension rehydrates only immutable parent endpoint,
prepared-exposure, final-model, DeltaReference, and formal-permutation roots;
it does not rerun observed grids, resolver, final realization, LOOCV,
bootstrap, jitter, OSS-DBS, or combined extensions. Record the conditioning
label `conditional_on_selected_tau_coverage_branch_and_candidate_axis` in every
endpoint summary and aggregate report.

The first formal v8 child startup restored all 504 immutable checkpoint roots
and then failed all 112 new targets before numerical work because the production
provider read model family directly from `EndpointRecord` instead of its typed
`EndpointKey`. The repair changes only that record-field lookup to
`endpoint.key.model_family`. Resume must retain all restored checkpoints and
rerun only the 112 failed in-sample endpoint tasks.

The corrected resume completed the formal child
`task17-final-in-sample-v1-20260718`. All 616 child-plan tasks are completed:
504 immutable parent checkpoints were restored and 112 in-sample endpoint
tasks completed, with 28 endpoints in each of the four model families. Every
endpoint retained all 10000 requested permutation statistics. All subject
masks match their paired LOOCV results, and all required correlation, nominal
p, formal p, standard R2, relative R2 or Q2, error, baseline-error, and optimism
fields are finite. Both predeclared Benjamini-Hochberg layers completed for
in-sample and LOOCV raw permutation p values. The historical parent lacks an
explicit schedule, so all 112 results correctly report
`independent_deterministic_schedule`.

The child publishes `sensitivity_results/final_in_sample_results.json` with
112 rows and `sensitivity_results/final_in_sample_results.csv` with one header
plus 112 rows. Its artifact index contains 112 endpoint summaries, 112 explicit
schedule arrays, and 112 in-sample null arrays. The extension manifest is
completed with no failed endpoint. The recorded parent-manifest SHA still
matches the current parent manifest after execution.

- [ ] **Step 10: Run numerical, reuse, resume, deletion-rebuild, and resource acceptance**

Run cold/warm benchmarks for voxel, every connectome, formal, bootstrap, jitter,
and pPAM at `workers = 1, 3, 6, 12`. A skipped row records preflight evidence
and cannot support a performance/default claim. Run the complete OSS matrix with
an injected solver and real cache-hit reuse separately. Incorporate Step 5's
separately authorized bounded real-OSS decisions for every exact class used by
the run; do not let the routine acceptance suite launch a cold solver miss.
Require the
authority document's complete acceptance contract: brute-force and optimized
numerical equivalence, worker-count determinism, candidate false-negative count
`< 1`, producer count per physical identity `> 0` and `< 2`, hot-loop metadata
work count `< 1`, full cache-verification count per used entry and process
`> 0` and `< 2`, within-process repeat verification count `< 1`,
endpoint-selected payload-copy count `< 1`, fault-free pool-generation count
`> 0` and `< 2`, untracked nested
pool count `< 1`, bounded HDF5/solver/BLAS concurrency, parent-only persistence,
and `swap_delta_bytes < 1`. Exact-threshold fixtures must exclude voxel/fiber
E-field/tau, Coverage, reference overlap, support-QC, and pPAM boundaries.

On current 28-scale data, reduce 1540 endpoint-derived row evaluations per
connectome to 42 physical rows in the shared pass. For the 12-worker benchmark,
define `effective_cores = aggregate process CPU time / wall time` in five-second
windows. Eligible windows have `runnable_cpu_slots > 5` and no measured
admission block; require
`fraction(effective_cores > 6 among eligible windows) > 0.80`. Storage-limited
windows retain their measured I/O classification. Require
`swap_delta_bytes < 1`. Test
fail-once resume so formerly dependency-skipped descendants run after recovery,
and verify that resource-only resume overrides preserve scientific artifacts.
Run main-through-final followed by new-process jitter, OSS, and combined
extensions. Delete required parent artifacts and prove rebuild mode creates a
new main lineage before sensitivity. Direct-copy portable entries and inject
payload, shard, and axis corruption before extension startup. Compare extension
outputs with one-shot outputs under the existing numerical tolerances.

- [ ] **Step 11: Update current status and commit**

Only after all acceptance gates pass, mark the performance refactor complete in
the goal/design/plan, update every current threshold/output-contract/model-
summary statement to the strict rule, record the complete benchmark matrix and
chosen defaults, and commit without modifying, migrating, or deleting existing
scientific output trees.

---

### Task 18: Implement Canonical Main Publication And Public-Only Postprocess

Task 18 closes the gap between the internal run store and the stable output
contracts. It is required before the authoritative `/goal` can be complete.

- [x] **Step 1: Freeze publication-only fixtures and path rejection tests**

Create synthetic completed direct-voxel and normative-fiber run stores plus
their expected canonical model-set trees. Freeze tests proving that every
published payload is indexed with a relative path, SHA-256, byte count, stage,
model family, branch, and terminal status. Add negative fixtures for partial
manifests, missing payloads, SHA mismatch, path escape, task-local URI, and any
postprocess input below `.runs/`, `tasks/`, `work/`, or `runtime_work/`.

Closure plan on 2026-07-19: reuse the existing project-neutral one-scale
end-to-end run inside its current test instead of executing a second scientific
fixture. Replay that completed run through `CanonicalPublisher` and compare the
entire direct-voxel and normative-fiber relative file trees plus artifact-index
schema/counts against one checked-in versioned JSON fixture. Extend negative
coverage for a missing source payload and parameterize public-only input-root
rejection across `.runs`, `tasks`, `work`, and `runtime_work`. Existing tests
already cover noncompleted manifests, failed task states, SHA mismatch,
immutable collision, URI removal, and symlink escape.

The frozen normative-fiber fixture must also exercise a scientifically valid
single-sign selection. A realized source may contain sweet selected IDs without
sour selected IDs, or the converse. Publication still requires the canonical
valid-fiber axis and its complete benefit-oriented weights, publishes the signed
density from the selected side, and publishes a zero-valued density for the
missing side over the same selected-fiber support. Its provenance records a
selected count of `0` and a null selected-ID SHA for that side. It must not
invent a fiber, expand the support, or change model scores.

Acceptance evidence on 2026-07-19: the project-neutral one-scale four-model
test now runs the completed scientific workflow and replays the same run
through `CanonicalPublisher` while the project namespace remains blocked. The
checked-in `canonical_publication_tree_v1.json` freezes the direct-voxel tree
at 118 files and 82 indexed artifacts, the normative-fiber tree at 146 files
and 100 indexed artifacts, both complete sorted relative-tree SHA-256 values,
and the domain-specific artifact-index fields. The add-on fiber fixture selects
only sweet fibers; its published negative density is exactly zero on finite
support, with zero sour count and null sour selected-ID SHA in provenance.
Missing source payload rejection and all four prohibited postprocess root names
are covered. The focused gate passed 26 tests, and the complete dual-frequency
plus visualization suite passed 485 tests and 239 subtests.

- [x] **Step 2: Implement the canonical main publisher**

Implement publication-only projection from a completed run into the exact
direct-voxel and normative-fiber output contracts. The publisher may consume
the internal run store, but it must publish immutable payloads and relative
references below each model-set root. It writes the resolved profile,
`model_manifest.json`, `scale_status.csv`, `artifact_index.csv`, all required
per-scale stage status, selected-source bundles, final-model references,
formal outputs, sensitivity checkpoints, and reports. It must support replay
from an already completed scientific run without refitting a model.

Implementation evidence on 2026-07-19: the public `publish` and
`publish-extension` commands replay completed run stores into immutable
direct-voxel and normative-fiber model-set roots. Main publication now covers
both add-on branches, all configured connectome observed grids, sensitive
formal-source evaluations, selected source arrays and NIfTI files, formal
permutation/bootstrap results, final-model references, report derivatives,
root indexes, and commit-last manifests. A one-scale real PDQ-39 replay
published and verified 82 direct-voxel plus 127 normative-fiber indexed
artifacts without refitting.

Publication replay loads independent completed task-state JSON documents with
a bounded metadata thread pool. This boundary is limited to small immutable
JSON reads and record decoding; scientific arrays, HDF5 connectomes, NIfTI
generation, and publication writes remain explicitly ordered. The bound must
avoid serial exFAT open latency without multiplying large scientific payloads.
On the completed 1,512-task v8 parent, the bounded loader decoded all 1,512
states from VAL in about 187 seconds; the preceding serial attempt had not
finished after 12 minutes and was stopped before any scale directory existed.

Canonical publication is replayable from the retained immutable run store.
Each new payload is written to a temporary sibling, closed, verified once by
SHA-256 when its bytes did not originate in memory, and installed by atomic
rename. The writer retains that verified digest and byte count for the
artifact-index row instead of reading the installed payload again. It does not
issue one synchronous filesystem flush for every artifact on portable external
filesystems. Root manifests remain commit-last, so an interruption cannot
advertise a partial publication as complete; a later replay verifies and reuses
already installed same-byte payloads. Failed or partial replay never removes
the publication fragment, source run, checkpoint, or shared cache.

The publication root is resolved once. Relative artifact names reject absolute
paths and parent traversal lexically; each unique destination parent is then
created and resolved once before first use, so an existing symlink cannot
escape the publication root. The publisher also verifies each distinct source
artifact path and SHA-256 once per process and reuses that result only when a
later reference declares the same digest. This preserves fail-closed path and
content validation while avoiding repeated external-filesystem metadata walks
and repeated reads of the same immutable run-store payload.

Recovery and performance evidence on 2026-07-19: a real PDQ-39 replay was
intentionally allowed to retain its partial publication after an implementation
failure in the bootstrap standard-error NIfTI step. After correcting that
helper, replay resumed into the same output root without deleting or replacing
the fragment. The completed replay published 82 indexed direct-voxel artifacts
and 127 indexed normative-fiber artifacts; the public-only catalog rechecked
every indexed path, byte count, and SHA-256 successfully. Targeted publication
and configuration regression passed with 29 tests and 10 subtests. The complete
dual-frequency and visualization regression then passed with 481 tests and 239
subtests after the USB 3 link was restored.

- [x] **Step 3: Publish direct-voxel display NIfTI derivatives**

For every realized reference or add-on direct-voxel final, publish the
unsmoothed selected-source map and the masked normalized Gaussian display
derivatives with 1 mm and 2 mm FWHM. These derivatives remain report-only and
must not feed scoring, source selection, LOOCV, permutation, bootstrap,
sensitivity, or final-model identity. Verify NIfTI shape, affine, units,
finite-support behavior, payload SHA-256, and artifact-index rows.

Implementation evidence on 2026-07-19: the real PDQ-39 replay published the
unsmoothed selected benefit map, 1 mm and 2 mm masked-normalized Gaussian
display maps, canonical bootstrap standard-error NIfTI, and a bilateral map
derived with the configured nonlinear ANTs displacement. Bilateral
transformation applies the same field to a zero-filled value image and its
finite-support mask before normalized resampling back to the right-canonical
grid. Reference and add-on shapes and affines matched the canonical brainmask;
their indexed payloads passed byte-count and SHA-256 verification.

- [x] **Step 4: Replace run-store visualization inputs with publication inputs**

Postprocess configuration names one or more completed canonical publication
roots. Every scientific input is an artifact reference containing a
publication alias and an indexed relative path. The adapter verifies the
publication manifest, artifact index, path containment, payload size, and
SHA-256 before reading. Inline scientific summaries and arbitrary scientific
file paths are rejected. External anatomy and atlas overlays remain declared
rendering resources and cannot replace a scientific result artifact.

Interactive scene examples use the same publication resolver. They read
published `final_model.json` and its relative artifact references; they never
scan run tasks or reconstruct a display map from `.runs` arrays. Absence of a
completed canonical publication fails before MATLAB opens a figure.

Implementation evidence on 2026-07-19: postprocess schema v2 accepts only
indexed publication artifact references, verifies path containment, byte count,
and SHA-256, and rejects a `.runs` publication root. Inline scientific
summaries are rejected. Both PDQ-39 MATLAB examples now name canonical
direct-voxel or normative-fiber model-set roots. Synthetic canonical
direct-voxel and normative-fiber publications prepare the signed voxel NIfTI
and scored-fiber MAT inputs successfully. The complete dual-frequency and
visualization regression passed with 470 tests and 239 subtests; MATLAB Code
Analyzer reported no issue in the changed helper and example scripts. Real-data
scene execution remains correctly blocked until Steps 2 and 3 publish the
canonical model-set tree.

- [x] **Step 5: Run publication-only replay and downstream acceptance**

Replay the completed formal parent and completed final-in-sample extension into
new canonical model-set publications without rerunning observed grids,
resolvers, final realization, LOOCV, permutation, bootstrap, jitter, or OSS.
Validate all configured scales, both physical domains, reference/add-on final
states, root manifests, artifact indexes, 1 mm and 2 mm voxel display NIfTI
files, extension linkage, public-only postprocess input preparation, and
output-local postprocess resume.

Partial acceptance evidence on 2026-07-19: one real PDQ-39 parent replay and
one final-in-sample child replay completed below `/private/tmp`. Published
reference-voxel and reference-fiber artifacts prepared the interactive scene
inputs, and one statistics postprocess completed then reused its output-local
resume result. All 82 direct and 127 fiber main artifacts passed the public
catalog path, byte-count, and SHA checks. The full 28-scale production replay,
cohort-wide postprocess, and final extension audit remained open at this
checkpoint and are closed by the later evidence below. The complete
dual-frequency plus visualization regression passed with 475 tests and 239
subtests outside the restricted system-monitoring sandbox.

Formal-parent acceptance evidence on 2026-07-19: after the external volume was
restored to a verified 10 Gbps USB 3 link, publication replay resumed the
retained partial canonical tree and completed all 28 configured scales without
rerunning scientific tasks. The completed direct-voxel model set contains
2,215 indexed artifacts and the normative-fiber model set contains 3,475.
The public-only catalog independently resolved all 5,690 relative paths and
verified completed row status, byte count, and SHA-256. Semantic acceptance
confirmed 28 completed scale-status rows, 56 realized reference/add-on final
models per physical domain, 280 direct-voxel spatial files, and 168
normative-fiber density files. The direct-voxel check covered each realized
model's unsmoothed selected benefit map, bootstrap standard-error map,
bilateral map, and 1 mm plus 2 mm FWHM display derivatives. The fiber check
covered signed, positive, and negative density maps. All checked NIfTI files
had compatible shape, affine, spatial units, and nonempty finite support. The
final-in-sample extension and cohort-wide public-only postprocess remained open
at this checkpoint and are closed by the later evidence below.

Extension migration decision on 2026-07-19: the pre-existing
`task17-final-in-sample-v1-20260718` extension directories are retained as
legacy evidence but are not valid public-only inputs. Their v1 artifact indexes
lack the canonical relative-path, byte-count, and terminal-status columns and
are rejected by `PublicationCatalog`. The completed child run remains the
immutable source of 112 final-in-sample results. Replay therefore publishes a
new `task17-final-in-sample-v2-20260719` extension beside v1, using the current
v2 manifest and canonical artifact-index contracts. It must not overwrite,
delete, or treat the v1 directories as resumable canonical output.

Extension acceptance evidence on 2026-07-19: the v2 replay completed with 56
direct-voxel and 56 normative-fiber final-in-sample rows. Its two canonical
indexes contain 674 artifacts each; the public-only catalog verified all 1,348
relative paths, completed statuses, byte counts, and SHA-256 values. Semantic
acceptance confirmed all 112 unique endpoints against their canonical parent
final-model identifier, realized branch, selected tau, selected coverage, and
subject axis. Every paired in-sample and LOOCV result used 10,000 requested and
finite permutations. Spearman rho, descriptive nominal p values, formal
permutation p values, Pearson statistics, standard and relative R2, LOOCV R2
and Q2, model and baseline errors, and all declared optimism gaps were present
and internally consistent. The patient-level prediction tables paired outcome,
in-sample prediction, LOOCV prediction, and both nuisance-only baselines with
finite values. No adjusted R2 was published.

Real-data postprocess smoke evidence on 2026-07-19: canonical PDQ-39
reference-voxel and reference-fiber inputs each rendered one 2D spatial figure
and one paired in-sample/LOOCV fit figure in PNG and PDF formats with zero
failed items. Visual QA identified and corrected repeated axis-label and legend
collisions before cohort-wide execution. The corrected renderer preserves
exact Boxsize panels, shows ticks only at the outer grid edges, uses one
plane-specific bottom axis label, and reserves a separate legend band. PNG and
Poppler-rendered PDF review passed, Arial was embedded, 11 focused visualization
tests passed, and the complete suite passed with 481 tests and 239 subtests.
At this smoke checkpoint, the 112-endpoint production postprocess and its
output-local resume audit remained open; the full acceptance immediately below
supersedes that checkpoint.

Full downstream acceptance evidence on 2026-07-19: the production request
consumed only the four completed canonical main/extension publications and
completed all 112 endpoints with zero failures. Each endpoint produced one 2D
spatial PNG/PDF pair and one paired in-sample/LOOCV PNG/PDF pair. All 112
endpoint manifests were complete; all 448 outputs existed with nontrivial byte
counts; 224 PNG files decoded successfully; and all 224 PDF files had valid PDF
headers and terminal EOF records. Model coverage was exactly 28 rows for each
of reference voxel, add-on voxel, reference fiber, and add-on fiber. Reference
and add-on examples from both domains passed visual review. An identical second
request reused all 112 completed endpoint manifests, reported zero failures,
and changed neither byte size nor nanosecond modification time for any output.

Add the workflow storage policy `delete_run_cache_on_success`. Its production
value is `false`. When false, successful runs retain cache content. When true,
cleanup is permitted only after the requested workflow, reporting, canonical
publication, root artifact index, and every required scale reach an
unqualified completed state. Failed, partial, interrupted,
completed-with-failures, or publication-incomplete runs never clean cache.
This recovery rule is unconditional and cannot be overridden by the cleanup
setting. A cleanup attempt must fail closed before touching cache whenever the
run or publication state is not fully complete.
Cleanup cannot remove the run store, canonical model-set publication,
extensions, sensitivity checkpoints, or cache entries not owned by the
completed run.

- [x] **Step 6: Update status and commit**

Only after the publisher, publication replay, and public-only postprocess gates
pass may the goal remove `canonical_main_publisher_not_started`,
`postprocess_publication_adapter_not_started`, and
`configured_production_outputs_missing`.

Status evidence on 2026-07-19: all three gates passed. The authoritative goal
now records accepted canonical main publication, accepted final-in-sample
publication, accepted public-only postprocess, and published configured
production outputs. The three obsolete blockers above are absent. The commit
containing this record freezes the publisher boundary, fixture, negative tests,
single-sign fiber behavior, and final acceptance evidence. This completes Task
18 only; Task 17 sensitivity-extension work remains deferred by explicit user
instruction and therefore the authoritative `/goal` remains active.

---

## Plan Self-Review Record

Five generic-core review passes were completed on 2026-07-15. A sixth
performance-contract review was added on 2026-07-16:

| Pass | Result | Implementation mapping |
|---|---|---|
| 1. Authority/current state | PASS | Global prerequisite requires the sole `/goal`, passed review status, clean branch, and no new worktree. |
| 2. Scale/endpoint identity | PASS | Tasks 3-6 implement equal factories, stable binding IDs, explicit matched-reference endpoint IDs, and cross-phase matching. |
| 3. Dependency/fallback | PASS | Task 5 defines the exhaustive readiness/source/Delta/fallback truth table; Tasks 11-12 integrate it without bidirectional fallback. |
| 4. Round/interface/provenance | PASS | Tasks 2, 6-8, and 13-16 cover every Round, typed requests/arrays/artifacts, project import isolation, standalone CLI, connectome roles, and resolved configuration artifacts. |
| 5. Bounded acceptance | PASS | Task 1 requires an exact reviewed task allowlist; Tasks 9-14 use only applicable completed fixtures; Task 16 blocks expensive misses and parity expansion. |
| 6. Shared physical preparation and resources | DESIGN PASS / IMPLEMENTATION OPEN | Code audit plus primary literature/official runtime guidance now map Task 17 to the authorized mixed threshold policy, distinct voxel/fiber preparation, exact `Omega_max`, single-write no-payload-reread caches, bounded semantic identity, a persistent spawn-safe resource scheduler, parity-preserving RNG blocks, vectorized kernels, resume correctness, and measured performance gates. |

This record validates closure of the generic-core implementation and design
closure of the performance refactor. Task 17 remains open; no current status or
test count implies that the new execution architecture is implemented.

---

## Generic-Core Historical Acceptance And Current Target Checklist

- [x] `dual_frequency_v1` is the only production schema.
- [x] `four_model_yaml_core_refactor_plan.md` is the sole current `/goal`; the
  predecessor execution plan is historical only.
- [x] Production starts directly from a validated `study_base.json` and creates
  no intermediate study bundle.
- [x] Generic runtime imports no `projects.stnsnr` module and scientific
  backends accept only typed requests, arrays, and artifact references.
- [x] All scales use identical task factories and status fields.
- [x] Combined endpoints use explicit matched-reference IDs; cross-phase binding
  never depends on source-period equality.
- [x] Reference dependency failure is distinct from ready input with no stable
  source.
- [x] Four model families and all non-deferred Rounds are represented.
- [x] One-way fallback truth table passes exactly.
- [x] Generic runtime has no predecessor/migration/acceptance imports.
- [x] Connectome behavior is role-based.
- [x] Sensitive connectomes emit no final; exactly one `formal` connectome is
  final-eligible.
- [x] Historical scientific caches exclude scale/run/scheduler identity.
- [ ] Physical preparation occurs once before endpoint/scale fan-out.
- [ ] Direct voxel and normative fiber reuse their respective bilateral
  exposure rows across all scales without changing either bilateral formula.
- [ ] Logical connectome points are covered once per preparation generation;
  bounded raw-chunk boundary overlap is measured separately, and filtering uses
  exact minimum-grid `Omega_max`.
- [ ] Jitter schedules and physical exposure are scale-independent Layer-1
  resources; endpoint jitter statistics remain Layer 2.
- [ ] OSS/pPAM moves to formal-connectome `Omega_max` only after exact final-axis
  ten-state/count/probability equivalence; every endpoint final axis is an exact
  canonical-ID subset.
- [ ] Target cache verifies each used entry once per process and performs no
  within-process payload checksum reread; bounded semantic/axis/toolchain digests remain
  permitted under the authority contract.
- [ ] CPU-heavy work uses spawned processes, large disjoint work units, and a
  persistent event-driven ready queue; `execution.workers` is the one public
  global CPU ceiling and nested pools cannot bypass it.
- [ ] Spawned workers receive pure-data commands and read-only shared artifacts;
  only the parent mutates RunStore, gates, retries, and artifact indexes.
- [ ] Fiber hot loops perform no path/NIfTI/transform-lock work, materialize only
  audited coordinate rows, and partition by point bytes without splitting a
  fiber while minimizing raw-chunk overlap.
- [ ] Large payloads are written once and endpoint/final consumers use immutable
  row/column views; complete one-based fiber axes are not duplicated.
- [ ] Vectorized statistics/scoring and null fast paths pass scalar parity and
  do not duplicate fold operators or allocate unused retained `N x F` arrays.
- [ ] Parallel formal/bootstrap/pPAM preserve their historical continuous RNG
  schedules; jitter preserves its existing replicate-keyed identity, and all are
  invariant to worker count and scheduling order.
- [ ] Resume re-evaluates dependency-derived skips and permits only accepted
  resource-provenance overrides without changing scientific identity.
- [ ] Managed RAM is the smaller of 48 GiB and available RAM after the larger of
  a 16-GiB or 20%-physical reserve; expected solver RSS is charged and swap
  satisfies `swap_delta_bytes < 1`.
- [ ] Voxel/fiber thresholds include exact tau and Coverage values, and overlap
  includes the exact selected reference tau; support-QC uses its documented
  strict direction and pPAM uses `p(A) > 0.5`. Every reopened boundary fixture
  is admitted.
- [x] Formal/sensitivity/activation consume only one realized final.
- [x] Generic reports contain no HF/ULF compatibility aliases.
- [x] Bounded parity includes only exact IDs in the reviewed allowlist that are
  also frozen completed, structurally valid scientific tasks.
- [x] No unfinished predecessor task is assigned numerical parity.
- [x] No expensive producer starts during acceptance without authorization.
- [x] Old outputs and the paused run remain immutable.
- [x] Resolved study-base/model/workflow configuration IDs, source paths, and
  schema versions are persisted and reproduce the run inputs.
- [x] Public CLI runs directly with caller `PYTHONPATH` unset and never discovers
  a default profile, study input, run, or legacy output.
- [x] Synthetic, two-scale smoke, bounded parity, import isolation, compile, and
  documentation checks all pass.
