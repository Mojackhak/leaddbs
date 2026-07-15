# Dual-Frequency Core Decoupling Implementation Plan

> **For agentic workers:** Subagents may be used for disjoint implementation or
> review tasks, but no local skill is required. Steps use checkbox (`- [ ]`)
> syntax for tracking.

**Goal:** Replace the STNSNr-oriented `four_model_v1` runtime adapters with a
strict, reusable `dual_frequency_v1` four-model core that can run from a
validated `study_base.json` without legacy or migration imports.

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
  one `formal` connectome is final-eligible; formal resampling, OSS, and jitter
  derive from its realized final without a third connectome role.
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
- Expensive producer cache misses require explicit authorization; acceptance
  never authorizes them.
- During the current implementation phase, production YAML may be validated
  and planned only. Do not execute its observed, formal, sensitivity, jitter,
  activation, or report tasks and do not write its configured output root.
  Runtime tests use deterministic synthetic fixtures or reviewed frozen
  read-only acceptance artifacts.
- Artifact-backed requests must match both shape and exact ordered axis hashes;
  formal requests declare a subject axis and activation requests inherit the
  realized final model's exact feature axis.
- Relative paths in `study_base.json` resolve against the JSON parent directory.
  Preserve and validate contact numbering/electrode order, contact ranges,
  uniqueness, and polarity-fraction closure without using component labels for
  frequency classification.
- Keep `configuration_hash` for the complete effective run configuration and a
  separate `scientific_configuration_hash` for task-content identity. Runtime
  locations, workers, resume/force, retries, and scheduling order must not
  alter scientific identity.
- `/Volumes/VAL/STNSNr/summary` and configured run
  `20260711T034644Z_d318f177f7f2ac7d` are immutable.
- Numerical parity covers only terminal completed, hash-valid scientific tasks
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

- [ ] **Step 1: Document the frozen task/artifact eligibility rule**

Add an implementation-note section naming the immutable run and stating:

```text
eligible = task_id in approved_task_allowlist
           and status == completed
           and task has scientific artifacts
           and every artifact hash validates

excluded = task_id not in approved_task_allowlist
           or reports that only summarize failure
           or partial/failed/skipped/pending/unstarted tasks
```

- [ ] **Step 2: Write failing fixture-manifest tests**

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

- [ ] **Step 3: Run the failing tests**

Run:

```bash
conda run -n leaddbs env PYTHONPATH=my_helper/fiber \
  python -m unittest \
  projects.stnsnr.acceptance.tests.test_bounded_fixture_manifest -v
```

Expected: FAIL because the acceptance modules do not exist.

- [ ] **Step 4: Implement deterministic manifest construction**

Read the static reviewed allowlist first, then `task_status.csv`; require the
immutable run identity from `run_manifest.json`, load only allowlisted task
manifests, hash every referenced artifact, reject paths outside the run root,
and write sorted JSON. Reject unknown, duplicate, noncompleted, or hash-invalid
allowlist entries. Do not discover additional tasks, run a producer, or repair
missing files.

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

- [ ] **Step 5: Add the read-only comparison helper**

Implement exact comparisons for IDs/status/masks and `numpy.testing.assert_allclose`
for configured floating arrays. Return a structured result; never modify either
fixture.

- [ ] **Step 6: Add old-YAML migration tests and implementation**

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

- [ ] **Step 7: Run focused tests and generate the frozen manifest**

Run the two test modules. Build and review
`approved_task_allowlist.json` from the immutable execution plan using only the
four completed scientific scopes named in the `/goal`; store exact task IDs,
expected stage, model family, endpoint, connectome role/ID, and artifact kinds.
Then generate a manifest from:

```text
/Volumes/VAL/STNSNr/configured_model_runs/stnsnr_frequency_addon/
20260711T034644Z_d318f177f7f2ac7d
```

Expected: only explicitly allowlisted, hash-valid completed scientific tasks are
eligible; every other terminal task has an exclusion reason; no process matching
`run_configured_outcome_models.py` starts.

- [ ] **Step 8: Commit**

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
  `FormalRequest`, `FormalResult`, `SensitivityRequest`, `SensitivityResult`,
  `ActivationRequest`, and `ActivationArtifact`.
- Produces array/artifact-only `ObservedBackend`, `FormalBackend`,
  `SensitivityBackend`, `ActivationBackend`, and `ReportingBackend` protocols.

- [ ] **Step 1: Write failing schema tests**

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

- [ ] **Step 2: Write failing immutable-record tests**

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
`schema_version`, explicit `uri`, `sha256`, `dtype`, `shape`, ordered
`axis_refs`, `axis_hashes`, units/space where applicable, and producer identity/
version. Typed scientific requests must reject raw `Path` fields and accept only
arrays or artifact references for scientific inputs.

- [ ] **Step 3: Run tests and verify RED**

```bash
conda run -n leaddbs env PYTHONPATH=my_helper/fiber/core \
  python -m unittest discover \
  -s my_helper/fiber/core/dual_frequency/tests \
  -p 'test_config.py' -v
```

Expected: import failure for `dual_frequency`.

- [ ] **Step 4: Implement strict typed contracts**

Use frozen dataclasses and canonical SHA-256 identities. Generic field names are
mandatory:

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
    sha256: str
    dtype: str | None
    shape: tuple[int, ...] | None
    axis_refs: tuple[AxisRef, ...]
    axis_hashes: tuple[str, ...]
    units: str | None
    space: str | None
    producer_id: str
    producer_version: str
```

`ObservedRequest`, `FormalRequest`, `SensitivityRequest`, and
`ActivationRequest` contain typed records, arrays, and `ArtifactRef` values;
they contain no raw project path, legacy filename, or unresolved YAML field.
Define backend protocols in the same task so planner, registry, and application
code cannot invent looser callable signatures before scientific extraction.

- [ ] **Step 5: Implement three JSON Schemas and loader**

All schemas use `additionalProperties: false`. Cross-profile validation checks
scale order, endpoint pairs, frequency classes, connectome roles, minimum
subjects, model grids, output identity, and workflow selection. Derive:

```python
direct_candidate_threshold_v_per_m = min(direct_voxel.source.scan.tau_v_per_m)
```

Do not include the derived field in public serialized YAML.

- [ ] **Step 6: Run focused and predecessor regression tests**

Run new config/record tests and the predecessor config/identity/record tests.
Expected: both suites pass; no predecessor file changes.

- [ ] **Step 7: Commit**

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

- [ ] **Step 1: Write failing study-base loader tests**

Create minimal generic JSON fixtures with two subjects and two scales. Test
schema rejection, duplicate IDs, invalid directions, nonfinite observations,
invalid phase/program references, invalid source frequencies, and deterministic
subject/scale order. Assert the loader records the source SHA-256 and returns
immutable records without writing another file.

- [ ] **Step 2: Write failing cross-profile validation tests**

Assert direct-voxel and normative-fiber profiles have identical model-set ID,
output root, scale order, endpoint pair, frequency classes, minimum subjects,
and DeltaReferenceScore support thresholds. Every configured scale must exist
in the study base. Assert exactly one normative-fiber `formal` connectome and
zero or more `sensitive` connectomes.

- [ ] **Step 3: Run tests and verify RED**

Run the study-base and config modules. Expected: missing generic study-base
loader and workflow schema support.

- [ ] **Step 4: Implement read-only loading and semantic validation**

Validate schema, uniqueness, foreign keys, finite values, explicit order,
frequency-group closure, and scale directions. Load only the existing JSON;
do not create Parquet, a bundle directory, a study index, or a resolved study
manifest. The run manifest records the input path and SHA-256.

- [ ] **Step 5: Finalize the three configured profiles**

Preserve the approved direct-voxel and normative-fiber scientific values.
Update `workflow.yaml` to reference those two profiles, expose no scale
defaults, and define execution/failure policy only. Keep MDS-UPDRS III and IV
as ordinary test selections in the test model profiles, not workflow defaults.

- [ ] **Step 6: Run real read-only validation**

Validate `/Volumes/VAL/STNSNr/summary/cohort/subj/study_base.json` and both
production/test profile pairs without running a model or modifying source
files. Verify 16 subjects, 28 scales, and the configured endpoint pair.

- [ ] **Step 7: Commit**

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

- [ ] **Step 1: Write failing catalog tests**

Cover all four model families, multiple connectome roles, multiple configured
scales, minimum subjects, unavailable rows, and scale equality. Assert the
synthetic profile has no project-frequency names in serialized catalog rows.
Include one explicit reference/add-on endpoint pair whose phases differ and
assert every configured scale uses that pair without automatic endpoint
discovery or fan-out. Assert
sensitive connectomes are `final_eligible = false` and the sole `formal`
connectome is `final_eligible = true`.

- [ ] **Step 2: Add the named III/IV structural fixture**

Assert MDS-UPDRS III and IV are both executable through the same configured
endpoint-pair factory, with no scale-name conditional in the builder.

- [ ] **Step 3: Run tests and verify RED**

Expected: missing catalog module.

- [ ] **Step 4: Implement study-base-driven catalog construction**

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

- [ ] **Step 5: Run focused tests and identity regression**

Expected: deterministic endpoint ordering and IDs under repeated builds;
reordering equivalent study-base rows does not change endpoint IDs.

- [ ] **Step 6: Commit**

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

- [ ] **Step 1: Write the exhaustive failing truth-table tests**

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

- [ ] **Step 2: Run tests and verify RED**

Expected: missing state module.

- [ ] **Step 3: Implement pure state transitions**

Use no filesystem or NumPy dependency. `ReferenceDependencyRecord` separates
`dependency_status` (`ready`, `not_configured`, `input_failure`,
`design_failure`, `execution_failure`) from `source_status`. Only
`dependency_status == "ready"` can produce a branch plan. Accepted sources are
exactly:

```python
ACCEPTED = frozenset({"pre_specified_accepted", "scan_fallback_accepted"})
```

`dependency_status == "ready"` with `source_status ==
"absent_no_stable_grid"` produces no-delta-only. Any nonready dependency
produces a terminal `dependency_failure` and no intended branch; it must never
be reinterpreted as source absence.

Fallback code must explicitly require:

```python
if (
    plan.intended_branch == "delta_reference_adjusted"
    and intended.status in {"input_failure", "design_failure", "absent_no_stable_grid"}
    and alternate.source_status in ACCEPTED
):
    return FinalDecision("no_delta_reference", "fallback_final", ...)
```

- [ ] **Step 4: Run tests and mutation-style negative assertions**

Temporarily assert that adjusted would become fallback after failed intended
no-delta and confirm the assertion fails; restore the correct test.

- [ ] **Step 5: Commit**

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

- [ ] **Step 1: Write failing DAG tests**

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

- [ ] **Step 2: Run tests and verify RED**

Expected: missing planner module.

- [ ] **Step 3: Implement typed tasks, gates, and topological ordering**

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

- [ ] **Step 4: Compare the scientific task inventory with the `/goal` matrix**

Add a parameterized test asserting every non-deferred Round has at least one
task stage and no optional future Round appears. Include add-on direct Round 9
display/final-manifest generation explicitly.

- [ ] **Step 5: Commit**

```bash
git add my_helper/fiber/core/dual_frequency/workflow/planner.py \
  my_helper/fiber/core/dual_frequency/tests/test_planner.py
git commit -m "feat: compile dual-frequency workflow DAG"
```

---

### Task 7: Implement Scientific Cache, Run Store, And Executor

**Files:**
- Create: `my_helper/fiber/core/dual_frequency/cache/__init__.py`
- Create: `my_helper/fiber/core/dual_frequency/cache/identity.py`
- Create: `my_helper/fiber/core/dual_frequency/cache/store.py`
- Create: `my_helper/fiber/core/dual_frequency/workflow/run_store.py`
- Create: `my_helper/fiber/core/dual_frequency/workflow/executor.py`
- Create: `my_helper/fiber/core/dual_frequency/workflow/registry.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_cache.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_executor.py`

**Interfaces:**
- Produces: `ScientificCacheKey`, `ContentAddressedCache`, `RunStore`,
  `ArtifactStore`, `ServiceRegistry`, and
  `execute_plan(plan, context) -> RunResult`.

- [ ] **Step 1: Write failing scientific-identity tests**

Assert scale, endpoint, run, workers, and retry changes do not alter an OSS row
key, while geometry, stimulation, component, transform, connectome, backend, or
scientific parameter changes do.

- [ ] **Step 2: Write failing cache validation/reindex tests**

Exact IDs in different order may produce a view manifest after per-item hashes
validate. Changed/duplicate/missing IDs raise `CacheIdentityMismatch`. Assert
`ArtifactStore.materialize(ref)` validates hash, dtype, shape, axes, units, and
space before returning an array; a bare path is rejected.

- [ ] **Step 3: Write failing executor tests**

Cover resume identity, endpoint isolation, false gates, required artifacts,
nonzero exit aggregation, and `ExpensiveProducerNotAuthorized` without invoking
a producer.

- [ ] **Step 4: Implement atomic content-addressed cache publication**

Write to a temporary sibling, hash every file, then atomically publish. Cache
manifests include scientific identity and exclude runtime scheduler identity.

- [ ] **Step 5: Implement generic run store and executor**

Use the explicitly configured run root:

```text
<workflow.storage.run_root>/<study_id>/<run_id>/
```

Do not derive it from `model.output.root`; that separate path owns scientific
model artifacts and reports.

Before task execution, atomically write `configuration_resolved.yaml` containing
the canonical merged study/scale/model/workflow profiles and CLI overrides,
plus `configuration_sources.json` containing source URIs and hashes. Compute the
configuration hash from the resolved snapshot, not source file locations.

Validate every completed service result against declared artifact kinds and
keep all task outputs within run/cache roots.

- [ ] **Step 6: Run focused and predecessor executor regressions**

Expected: generic tests pass; predecessor run store/executor tests still pass.

- [ ] **Step 7: Commit**

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

- [ ] **Step 1: Write failing service/CLI tests**

Test `--scale` repeatability, `--all-available` exclusivity, required selection,
dependency-complete `--through`, exact resume, force lineage, and explicit
`--allow-expensive-producers`. Execute the repository script in a subprocess
with `PYTHONPATH` removed and assert `--help` and explicit-profile `validate`
import successfully. Assert every missing study/model/workflow flag fails and
`status/artifacts` reject a nonexact or inferred run selector.

- [ ] **Step 2: Run tests and verify RED**

Expected: missing application package and entrypoint.

- [ ] **Step 3: Implement WorkflowService**

The service owns study-base/profile validation, catalog, planning, run-store
creation, registry construction, execution, and artifact lookup. CLI performs
argument parsing only.

- [ ] **Step 4: Implement the thin entrypoint**

```python
#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


CORE_ROOT = Path(__file__).resolve().parents[1] / "core"
if str(CORE_ROOT) not in sys.path:
    sys.path.insert(0, str(CORE_ROOT))

from dual_frequency.application.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

The bootstrap adds only the generic `core` directory. It must not add
`projects/stnsnr`, migration, acceptance, or legacy paths.

- [ ] **Step 5: Run CLI smoke with an in-memory deterministic registry**

Execute `validate`, `plan`, and `run --through report` on a synthetic study base.
Run the public script directly with caller `PYTHONPATH` unset. Expected: generic
reports, no project/legacy imports, and no expensive process.

- [ ] **Step 6: Commit**

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
artifact hash before reading it. Assert exact identity/source/tau/Coverage/
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
Any predecessor resolver fixture used here must contain enough declared
neighbor cells to exercise the current minimum of two adjacent passing cells;
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
  `20260711T034644Z_d318f177f7f2ac7d`; every consumed artifact hash was
  verified before read.
- Legacy reference-direct scan and shared resolver self-tests: PASS.
- `compileall`, `git diff --check`, generic hardcoding scan, and production
  output-root freshness check: PASS.
- No production YAML task was executed and no intermediate study bundle was
  created.

---

### Task 10: Extract Reference Normative-Fiber Backend And Shared Score

**Current-phase execution boundary:** production normative-fiber YAML may be
parsed, validated, and planned only. Task 10 uses deterministic synthetic
arrays and frozen hash-validated completed fixtures. It must not launch a
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
- Artifact-backed exposure matrices are hash/axis/unit/space validated and
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
verify every consumed hash before read. Compare completed dTOR full outputs and
MGH/PPMI observed/formal-source evaluation outputs only. Convert predecessor
MGH/PPMI final-like records to target sensitivity evidence; do not create
target finals, read mutable legacy summary paths directly, or invent formal/
OSS parity for sensitive connectomes.

The frozen Task 10 allowlist does not contain the complete parent canonical
fiber-ID axis required to reconstruct an `ObservedRequest`. Therefore bounded
golden acceptance must not follow the legacy selected manifest's indirect
`ids_path` or rerun the target backend from an unallowlisted input. It verifies
all consumed frozen hashes, task and endpoint identities,
source/tau/Coverage/prediction semantics, selected score/prediction artifact
identity, and count/shape relationships that do not require the missing parent
ID axis. It must not claim parent-weight projection parity or instantiate a
target `SensitiveRecord` from a legacy full-sample-only selected axis. Complete
parent-axis, full/fold-valid-union, sensitive-record, and leakage behavior is
proven by deterministic synthetic tests.

The authoritative target uses inclusive suprathreshold classification
`E >= tau`; the frozen predecessor used strict `E > tau`. Bounded fixtures are
therefore historical semantic evidence, not an exact proof of the revised
threshold-boundary implementation. Inclusive-boundary behavior is covered by
an explicit synthetic equality-at-tau test. These are bounded-fixture
limitations, not permission for a transitive production read or a silent
fallback to legacy rules.

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
  and PPMI observed/resolver tasks. Every consumed artifact hash was verified
  before read; the documented missing-parent-axis and legacy strict-threshold
  limitations were preserved rather than bypassed.
- Synthetic tests cover inclusive `E >= tau`, parent-order full/fold-valid
  union, fold-only fitting, formal/sensitive role separation, scan fallback,
  noncomputable sensitive evidence, one-sided support, and read-only memory
  mapping.
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
  reference `SourceRecord`, its hash/axis-validated selected-feature indices,
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
  thresholding `E > selected_reference_tau`. Total suprathreshold count zero
  for any required subject is
  `invalid_no_reference_component_coverage`, never `adequate`.
- Support classification is deterministic:
  `adequate` requires cohort median out-support fraction `<= 0.20` and no more
  than `25%` of subjects above `0.50`; `invalid_extreme_out_of_support` applies
  when cohort median is `> 0.50`, more than `25%` of subjects are above `0.80`,
  or any required full/fold value is `> 0.95`; all remaining nonzero cases are
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
  hash, and artifact axes must all agree; a sensitive connectome never borrows
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
  inclusive normative-fiber rule `E >= selected_reference_tau`. For each
  subject and each required full/fold operator:

  ```text
  out_support_fraction =
      count(suprathreshold fibers outside that operator's finite valid support)
      / count(all suprathreshold reference-component fibers)
  ```

  A zero denominator is `invalid_no_reference_component_exposure`. Support is
  `adequate` when the cohort median is `<= 0.20` and no more than `25%` of
  subjects exceed `0.50`; it is `invalid_extreme_out_of_support` when the
  cohort median is `> 0.50`, more than `25%` of subjects exceed `0.80`, or any
  required full/fold value is strictly `> 0.95`; all other nonzero cases are
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
  task. Tests use deterministic arrays and hash-validated completed fixtures
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
  to hashes, completed status transitions, support QC, selected `400/5`
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
  manifest/artifact hash, invalid Delta-support, selected `400/5` no-delta,
  and realized-final assertions. Missing historical fold/operator evidence was
  covered only by deterministic synthetic tests, as required.

---

### Task 13: Extract Formal And Sensitivity Backends

**Files:**
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

- [ ] **Step 1: Write failing final-only and no-feedback tests**

Reject non-final branches, sensitive-connectome records, missing final axes, and outputs
that attempt to write classification fields.

- [ ] **Step 2: Write bounded-prefix parity tests**

Replay exactly ten permutations, ten bootstraps, and five jitter replicates from
fixture prefixes. Validate full predecessor artifacts by hash only. Exclude the
partial add-on dTOR jitter.

- [ ] **Step 3: Extract generic numerical code**

Move math from the relevant `stnsnr_*formal*`, `*jitter*`, and sensitivity
modules. Strategy selection is based on model-family capabilities, not module
name strings.

- [ ] **Step 4: Run focused tests and completed-scope parity**

Expected: reference direct/fiber completed prefixes and completed add-on fiber
formal/cheap/neighborhood fixtures pass.

- [ ] **Step 5: Commit**

```bash
git add my_helper/fiber/core/dual_frequency/backends/formal \
  my_helper/fiber/core/dual_frequency/backends/sensitivity \
  my_helper/fiber/core/dual_frequency/tests/test_formal.py \
  my_helper/fiber/core/dual_frequency/tests/test_sensitivity.py
git commit -m "feat: extract generic formal and sensitivity backends"
```

---

### Task 14: Implement Shared Activation Universe And Generic OSS Backend

**Files:**
- Modify: `my_helper/fiber/core/dual_frequency/contracts/requests.py`
- Modify: `my_helper/fiber/core/dual_frequency/backends/protocols.py`
- Modify: `my_helper/fiber/core/dual_frequency/config/schemas/normative_fiber_model.schema.json`
- Modify: `my_helper/fiber/core/dual_frequency/config/loader.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/activation/canonical_mapping.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/activation/ppam.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/activation/ossdbs.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_activation_universe.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_oss_backend.py`

**Interfaces:**
- Produces: `OSSRowBackend.materialize(OSSRowBatchRequest) -> OSSRowBatchArtifact`.
- Produces: `ActivationBackend.run_activation(ActivationRequest) -> ActivationArtifact`.
- The requested producer fiber axis is exactly
  `final.valid_feature_axis`; there is no whole-connectome or minimum-tau
  producer universe and no intermediate sidecar bundle.
- A producer cache key excludes scale, endpoint, final-model ID, run ID, worker
  count, and task order, but includes the exact ordered requested fiber-axis
  hash. Exact matching axes can therefore reuse rows across endpoints; different
  axes cannot use nearest-key or superset guessing.
- Consumes subject/component/condition/connectome/transform/solver inputs only as
  typed metadata and exact artifact references; solver paths come from validated
  backend configuration.
- The activation task has the realized final-model task as a direct dependency
  in addition to completed formal tasks. A transitive dependency is not a
  substitute for a typed direct final-record input.
- `expensive_producer` identifies a service that may produce expensive rows; it
  must not block service invocation before exact cache lookup. The activation
  service probes all row keys first and checks expensive authorization only when
  at least one valid row is absent.
- `ActivationRequest` explicitly carries outcome, branch-specific baseline,
  optional full/fold DeltaReferenceScore inputs, ordered subject/fiber axes,
  canonical fiber IDs, the matched final peak-E-field score, outcome direction,
  hard-computability limits, signed fiber-score settings, permutation count,
  and seed. The backend must not infer these inputs from filenames or hidden
  final-record artifacts.
- `final.valid_feature_axis` is the complete OSS candidate universe for the
  endpoint. OSS never reapplies peak-E-field tau/Coverage in full-sample,
  LOOCV, or permutation fits. Within that locked axis, full-sample and each
  training fold independently intersect finite OSS weights, reselect signed
  fibers, and recompute the configured weighted-peak score.
- Endpoint fitting emits only sensitivity status and artifacts. The status is
  `failed_activation_degenerate` for all-zero/non-estimable activation or an
  absent/constant signed score, `failed_oss_design_or_prediction` for invalid
  nuisance/prediction/permutation execution, `passed_activation_consistent`
  for a technically valid score with positive correlation to the explicit
  final peak-E-field score, and `passed_activation_model_dependent` for any
  other technically valid correlation. None of these statuses may alter the
  source, prediction, branch-role, endpoint, or final-model record.

- [x] **Step 1: Write failing universe and identity tests**

Assert the analysis universe equals the realized final model's exact ordered
`valid_feature_axis` at selected tau/Coverage. Weights, signs, and selected
sweet/sour IDs do not restrict that axis. Scale/final identifiers do not enter
the producer key, while a changed ordered fiber-axis hash does. Require the
unique configured `formal` connectome role without checking a connectome name.

- [x] **Step 2: Write failing mapping and threshold tests**

Assert:

```python
merged = np.maximum(probability_right, probability_left_to_right)
binary = (merged >= 0.5).astype(np.float32)
```

Require exact canonical fiber IDs and deterministic endpoint subsetting.
Freeze the public v1 OSS contract to `OSS-DBSv2`, `pPAM`, fiber diameters
`1.0..4.0` micrometers, exactly 10 equidistant samples, and inclusive fitting
threshold `0.5`. Schema and semantic validation reject any other values.

- [x] **Step 3: Write bounded OSS acceptance tests**

Validate the completed allowlisted reference-fiber OSS matrix, fiber IDs,
metadata, and sensitivity-result hashes. Replay exact ordered subsetting and
the inclusive `p(A) >= 0.5` threshold over 48 stratified fibers across three
subjects. Because the reviewed frozen fixture contains only the already-merged
branch matrix and not raw left/right rows, test `max_probability_union` with a
deterministic synthetic L/R fixture. Exercise row scheduling with an injected
synthetic producer; do not launch OSS-DBS or generate any real row during this
acceptance task.

- [ ] **Step 4: Implement generic OSS orchestration**

Remove dTOR name checks. Require a realized final on the unique `formal`
connectome, explicit OSS backend/version, exact subject-side frequency maps,
row checkpoints, three default row workers, and deterministic merge order.
Before scheduling, validate every requested row and exact scientific cache key.
Skip each already completed hash-valid row; never use nearest-key matching.
Map left stimulation geometry to right canonical space before OSS modeling,
require exact L/R rows for every final subject, merge by elementwise maximum,
cache continuous probability, and derive binary fitting exposure with
`p(A) >= 0.5`. Refit weights, signed selections, and the `200/100/20` score in
each training fold without changing source, prediction, branch-role, or final
classification.

Update planner/executor wiring so activation directly receives the final record
and cache hits remain usable with expensive producers disabled. Preserve the
global pre-service expensive guard for services that cannot prove cache-first
behavior; activation explicitly declares cache-first authorization handling.

- [x] **Step 5: Verify expensive-miss blocking**

Delete only a temporary synthetic cache row and run acceptance mode with
expensive producers disabled. Expected: `missing_acceptance_fixture`; the
injected producer invocation count remains zero and no OSS process starts.

- [ ] **Step 6: Commit**

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

---

### Task 15: Implement Generic Reporting, Switch Registry, And Isolate Legacy

**Files:**
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

- [ ] **Step 1: Write failing generic-report tests**

Reports must contain reference/add-on fields and reject HF/ULF compatibility
aliases, filename discovery, and old summary roots. Sensitive connectomes emit
explicit sensitivity rows without final IDs; only formal-connectome/direct-
voxel realized finals appear in final-model reports.

- [ ] **Step 2: Write failing runtime import-isolation test**

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

- [ ] **Step 3: Implement record-driven reporting**

Generate endpoint summary, artifact index, and run report only from exact
current-run records/artifact references. Report failure, skip, fallback, and
no-final states without fabricating numerical outputs.

- [ ] **Step 4: Build the generic default registry**

Register every generic backend explicitly. Remove dynamic import dispatch. An
empty registry remains test injection only.

- [ ] **Step 5: Move the complete predecessor runtime outside the core path**

After generic regression passes, use `git mv` to move the complete predecessor
`outcome_models` package and its tests into
`projects/stnsnr/legacy/outcome_models`. Move its public pipeline entrypoint into
the same legacy boundary and update that manual entrypoint's path bootstrap.
Do not move unrelated DWI/VTA scripts. No production module may import the moved
namespace. The move is archival isolation outside the generic core namespace;
the legacy package remains auditable but is never registered by production.

- [ ] **Step 6: Run import-isolation and full generic tests**

Expected: all generic tests pass with project migration/acceptance/legacy paths
blocked; predecessor historical tests may be archived rather than required by
the production package.

- [ ] **Step 7: Commit**

```bash
git add my_helper/fiber/core/dual_frequency \
  my_helper/fiber/projects/stnsnr/legacy \
  my_helper/fiber/pipelines
git commit -m "feat: switch to generic dual-frequency runtime"
```

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

- [ ] **Step 1: Add a project-neutral synthetic end-to-end test**

Use component/condition/connectome IDs that contain none of the forbidden
project terms. Run all four families through report with deterministic arrays
and a fake activation backend while the entire `projects.stnsnr` namespace is
blocked. Assert sensitive connectomes have no finals and each direct/formal
endpoint has one final or closed state.

- [ ] **Step 2: Add the named III/IV lightweight smoke**

Use the new STNSNr input/profile and existing exact caches. MDS-UPDRS III and
IV traverse the same ordinary endpoint-pair catalog/DAG path.
Use only internal-test permutation/bootstrap/jitter counts and block expensive
misses. Start `WorkflowService` directly from the existing `study_base.json`
while the project namespace is blocked, proving the runtime does not invoke the
importer.

- [ ] **Step 3: Run the bounded numerical fixture suite**

Compare only the manifest allowlist. Assert the test suite fails if any excluded
task is added to numerical parity or if a missing fixture tries to start a
producer.

- [ ] **Step 4: Run the complete test matrix**

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

env -u PYTHONPATH conda run -n leaddbs \
  python -m unittest \
  my_helper.fiber.core.dual_frequency.tests.test_application_cli.DirectEntrypointTests -v
```

The second test creates temporary explicit study/model/workflow inputs and launches
the public script's `validate` subcommand. Expected: all tests pass, direct CLI
import succeeds, compile succeeds, and diff check is empty.

- [ ] **Step 5: Run runtime isolation scans**

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

- [ ] **Step 6: Audit artifacts and process state**

Confirm every smoke task has a terminal record, every realized final has at most
one final ID, no sensitivity record has a final ID, `configuration_resolved.yaml`
and `configuration_sources.json` reproduce the configuration hash,
report/index/manifests agree, old output trees are unchanged, and no Lead-DBS/
OSS/model process remains active.

- [ ] **Step 7: Update documentation status with exact evidence**

Mark tasks complete only with test counts, run IDs, fixture hashes, and artifact
paths. Keep any nonpassing requirement open; do not use partial evidence to mark
the `/goal` complete.

- [ ] **Step 8: Commit final acceptance documentation**

```bash
git add my_helper/stnsnr my_helper/fiber/core/dual_frequency/tests
git commit -m "docs: record dual-frequency core acceptance"
```

---

## Plan Self-Review Record

Five plan review passes completed on 2026-07-11:

| Pass | Result | Implementation mapping |
|---|---|---|
| 1. Authority/current state | PASS | Global prerequisite requires the sole `/goal`, passed review status, clean branch, and no new worktree. |
| 2. Scale/endpoint identity | PASS | Tasks 3-6 implement equal factories, stable binding IDs, explicit matched-reference endpoint IDs, and cross-phase matching. |
| 3. Dependency/fallback | PASS | Task 5 defines the exhaustive readiness/source/Delta/fallback truth table; Tasks 11-12 integrate it without bidirectional fallback. |
| 4. Round/interface/provenance | PASS | Tasks 2, 6-8, and 13-16 cover every Round, typed requests/arrays/artifacts, project import isolation, standalone CLI, connectome roles, and resolved configuration artifacts. |
| 5. Bounded acceptance | PASS | Task 1 requires an exact reviewed task allowlist; Tasks 9-14 use only applicable completed fixtures; Task 16 blocks expensive misses and parity expansion. |

This record validates plan completeness only. All task checkboxes remain open
until implementation evidence exists.

---

## Final Acceptance Checklist

- [ ] `dual_frequency_v1` is the only production schema.
- [ ] `four_model_yaml_core_refactor_plan.md` is the sole current `/goal`; the
  predecessor execution plan is historical only.
- [ ] Production starts directly from a validated `study_base.json` and creates
  no intermediate study bundle.
- [ ] Generic runtime imports no `projects.stnsnr` module and scientific
  backends accept only typed requests, arrays, and artifact references.
- [ ] All scales use identical task factories and status fields.
- [ ] Combined endpoints use explicit matched-reference IDs; cross-phase binding
  never depends on source-period equality.
- [ ] Reference dependency failure is distinct from ready input with no stable
  source.
- [ ] Four model families and all non-deferred Rounds are represented.
- [ ] One-way fallback truth table passes exactly.
- [ ] Generic runtime has no predecessor/migration/acceptance imports.
- [ ] Connectome behavior is role-based.
- [ ] Sensitive connectomes emit no final; exactly one `formal` connectome is
  final-eligible.
- [ ] Scientific caches exclude scale/run/scheduler identity.
- [ ] OSS inherits the realized final model's exact `valid_feature_axis`, does
  not rescan tau/Coverage, and does not add noncandidate fibers.
- [ ] Formal/sensitivity/activation consume only one realized final.
- [ ] Generic reports contain no HF/ULF compatibility aliases.
- [ ] Bounded parity includes only exact IDs in the reviewed allowlist that are
  also frozen completed, hash-valid scientific tasks.
- [ ] No unfinished predecessor task is assigned numerical parity.
- [ ] No expensive producer starts during acceptance without authorization.
- [ ] Old outputs and the paused run remain immutable.
- [ ] Resolved study-base/model/workflow configuration and source hashes are
  persisted and reproduce the configuration hash.
- [ ] Public CLI runs directly with caller `PYTHONPATH` unset and never discovers
  a default profile, study input, run, or legacy output.
- [ ] Synthetic, two-scale smoke, bounded parity, import isolation, compile, and
  documentation checks all pass.
