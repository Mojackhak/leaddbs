# Dual-Frequency Core Decoupling Implementation Plan

> **For agentic workers:** Subagents may be used for disjoint implementation or
> review tasks, but no local skill is required. Steps use checkbox (`- [ ]`)
> syntax for tracking.

**Goal:** Replace the STNSNr-oriented `four_model_v1` runtime adapters with a
strict, reusable `dual_frequency_v1` four-model core that can run from a
validated `study_base.json` without legacy or migration imports.

**Current goal contract set:**

- `my_helper/stnsnr/four_model_yaml_core_refactor_plan.md` for the umbrella
  four-model scientific, YAML, execution, and publication contract;
- this implementation plan for Task 17 shared computation, cache, resume,
  sensitivity, and resource acceptance; and
- `my_helper/stnsnr/postprocess_visualization_implementation_plan.md` for the
  canonical-publication-only visualization replay and acceptance.

**Approved architecture:**
`my_helper/stnsnr/dual_frequency_core_decoupling_design.md`.

**Performance refactor contract:**
`my_helper/stnsnr/four_model_shared_exposure_performance_refactor_plan.md`.
**Task 17 decision record:**
`my_helper/stnsnr/task17_design_decisions.md`.
**Three-plan acceptance evidence ledger:**
`my_helper/stnsnr/task17_three_plan_acceptance_audit.md`.
The generic core implementation below is complete, but the shared-exposure,
one-pass connectome, process-scheduler, direct-copy SHA cache, sensitivity
extension, and missing-parent rebuild work remains collectively
`implementation_in_progress`. Canonical main publication, final-in-sample
publication, and the public-only postprocess adapter are accepted. The
support-preserving v8 jitter computation is completed, the independent formal
OSS lineage is active, and combined execution, self-contained sensitivity
publication, full postprocess replay, and final resource/resume acceptance
remain open. The earlier instruction that deferred Task 17 sensitivity
execution no longer describes the authorized current phase.

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
- The historical plan-only production restriction was lifted by explicit user
  authorization for the completed v8 parent and its named Task 17 sensitivity
  children. Formal writes remain restricted to those immutable lineages and
  the canonical publication and postprocess roots defined below. Do not launch
  an unrelated production lineage or broaden the scientific scope implicitly.
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
  voxel range on the complete parent feature axis. Only
  `E < selected_reference_tau` is excluded, so exposure exactly at the selected
  reference tau remains active. A required subject with
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
  component suprathreshold fiber range on the complete parent axis. Only
  `E < selected_reference_tau` is excluded, so exposure exactly at the selected
  reference tau remains active. For each
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

**Executor-level three-gate correction, 2026-07-22.** A continuation audit
found that `RunStore.open(..., resume=True)` correctly enforced only JSON and
ordered YAML content, but `execute_plan` still rejected changed configuration,
scientific-configuration, and plan hashes before restoring completed task
documents. That second-stage comparison was an undocumented fourth resume
boundary and contradicted Decision 16. Remove all three executor comparisons;
retain the hashes in run and execution-segment provenance only. Add an
executor-level fixture whose stored audit hashes all differ from the newly
compiled plan while JSON and YAML inputs remain unchanged. The fixture must
restore the completed task without service invocation. Existing tests must
continue to prove that changed JSON or ordered YAML content is rejected and
that failed, skipped, running, missing, malformed, or incomplete task JSON is
rerun or re-evaluated.

The correction is implemented. `execute_plan` no longer compares the stored
configuration, scientific-configuration, or plan hashes with the newly
compiled plan. The extended exact-resume fixture crosses both `RunStore.open`
and `execute_plan` with changed audit-only hashes, code identity, parent ID,
and resolved snapshot and restores the completed result without invoking its
service. The complete executor suite passed 31 tests plus six subtests under
Conda `leaddbs`; focused JSON/YAML, malformed-result, incomplete-result, and
cache-first checks also passed. The active OSS process was already running
with a matching plan before this source edit and was not restarted.

The same full-suite run exposed one synthetic resource-fixture error during the
live OSS workload. The pPAM false-gate fixture labeled its terminal aggregate
with the generic service ID `aggregate`; the production ledger therefore
correctly treated it as the 48-GiB solver path instead of the 2-GiB
`aggregate_ppam_activation` path. The fixture must use the production service
identity so its admission contract is deterministic and tests the same DAG
role as the real run. This is a test-identity correction and does not change
runtime resource charges or the active OSS process.

Because the real pPAM observed workspace itself retains its required 48-GiB
charge, pure synthetic orchestration fixtures must freeze their host memory
state at 128 GiB total and available. Otherwise a concurrent formal solver can
make gate, resume, cleanup, bootstrap, permutation, or all-family synthetic
tests fail before invoking any in-memory service. Apply this isolation to the
complete `SyntheticEndToEndTest` class and the two focused executor pPAM
fixtures. Dedicated ledger tests continue to exercise the actual 48-GiB
charge, 64-GiB managed ceiling, reserve predicate, and cumulative admission
behavior; only orchestration fixtures isolate host availability.

The isolated synthetic end-to-end suite passed all seven scenarios while the
formal OSS solver remained active. The complete dual-frequency suite then ran
545 collected test items to exit status 0. This accepts the executor-level
three-gate correction and its deterministic test boundary; it does not mark
the still-running independent OSS lineage complete.

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
connectome-I/O slot. Enforce the 64-GiB normal managed ceiling over cumulative
active grants while retaining the strict
`projected_available_after_admission > reserve` predicate. With the public
worker ceiling at 12, admit at most five voxel producers or two fiber producers
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
historical boundary fixtures as migration evidence. Target fixtures include
exact tau and Coverage values in voxel and fiber support, retain the declared
overlap and support-QC policies, and keep exact `0.5` pPAM values inactive;
only enumerated boundary rows may differ from the historical result.

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

The retained configured-connectome parity authority is the completed v8 parent,
not a newly synthesized fixture. Its canonical PPMI reference physical cache
identity is
`6b2a5a428ad175daecc0360dc417ba24ae43afb9eb006af8df6b7c4fea0338d4`;
the complete 16 by 1700000 float32 exposure payload SHA is
`b872a1a4cd53f8d94abe0641311bbaf4f5c3dc277172bb76521d348d4e4e6a95`.
The retained Omega-max prepared reference artifact contains 16 by 10320 values
with SHA
`e49a092f0654797c64f7a81c568b4b8822e79da97fbf27dd5ea034519a09c7ea`.
The add-on PPMI physical cache identity is
`094e299fd50819936807e7089de7056a33cb4415796ba88e9ea23b7697a27155`;
its 13 by 10075 prepared artifact SHA is
`9acd6224af68f016e60a1be3b8cd65f6dc14ab272559d160094d3924c44ce9c9`.
These immutable cache and task artifacts remain available below the configured
VAL cache and completed parent. The post-OSS parity run must compute into a
separate acceptance cache, compare complete float32 bytes and selected axes,
and leave the retained authority untouched.

The complete nine physical fiber matrices, three physical direct-voxel
matrices, six prepared Omega-max artifacts, and two prepared direct-voxel
artifacts are frozen in
`config/four_model_v1/acceptance/task17_connectome_parity_fixture.json`.
A repository-owned verifier must validate every cache manifest and payload,
require a completed authority run manifest, resolve only terminal-completed
prepared task artifacts from that parent, reject duplicate or missing
model/connectome/role rows, and emit one immutable acceptance report.
The complete authority-only report is published at
`/Volumes/VAL/STNSNr/summary/spot/acceptance/`
`task17-physical-parity-authority-v3.json`; it contains no replay claim. The
earlier connectome v1 and v2 reports are retained as superseded fiber-only
evidence. V1 also omitted parent-manifest and task-terminal validation; v2
closed those checks but did not yet freeze direct voxel.
For scale-fanned task-local duplicates, validate terminal state and artifact
metadata for every task. Hash every retained fiber payload as before; for the
large direct-voxel duplicates, hash one representative payload per distinct
content identity after the complete physical cache payload has already passed
independent validation. Record both task count and payload-hash count so the
bounded authority audit does not reread approximately 28 GiB of duplicate
voxel bytes.
The verifier may inspect the retained authority before OSS completes, but the
new implementation replay and byte comparison remain ordered after the active
solver lineage to avoid competing for connectome and VAL bandwidth.

The post-refactor replay uses
`config/four_model_v1/workflow_task17_parity.yaml`, one explicit canonical
scale, all four model families, all three configured connectomes, and the
`observed` cutoff. It writes only to the dedicated
`dual_frequency_task17_parity_v1` cache and acceptance run root, retains every
completed cache entry, disables expensive producers, and starts with one
worker. The profile may be validated while OSS runs but must not execute until
the solver lineage releases VAL and connectome bandwidth. A second invocation
with the configured worker count must be cache-only and byte-identical; it is
not a second cold replay.

The frozen scientific fixture SHA-256 is
`7255126c155aa616faac1457103169597ecd9c8c9707976ecb26e71c617fba6c`.
The frozen replay-workflow SHA-256 is
`4ad144f4aa2c94a5d85ac89e84cf389474d8e82d31d4e642b8b5347d98cfb4cc`.
The fixture deliberately excludes execution paths and worker ceilings; those
remain owned by the workflow and the exact commands below. Before execution,
both digests must match, the workflow must still select all models and
connectomes through observed with one cold worker, and its cache and run roots
must remain the dedicated acceptance roots. Any drift blocks replay rather
than silently creating a different acceptance claim.

Read-only validation and planning passed on 2026-07-22 for scale `adl`. The
request resolves eight available endpoints, 46 dependency-complete tasks, the
expected study-base SHA, configuration hash
`b5be0e90bf1311f632988bbf9b6b156a5189356d5063db9433b717e524b55a12`,
and scientific configuration hash
`34d3014d5d4e16a4f49d8ded688981098b58460d6140fc339a30c101e86c0cd4`.
Neither the dedicated cache root nor the acceptance run root was created. This
accepts the replay request only; execution remains intentionally deferred.

The deferred replay has one frozen run identity and command sequence. After the
independent OSS child releases VAL and connectome bandwidth, execute the cold
one-worker pass:

```bash
env -u PYTHONPATH /opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/fiber/pipelines/run_dual_frequency_models.py run \
  --study-base /Volumes/VAL/STNSNr/summary/cohort/subj/study_base.json \
  --direct-voxel-model my_helper/stnsnr/config/four_model_v1/direct_voxel_model.yaml \
  --normative-fiber-model my_helper/stnsnr/config/four_model_v1/normative_fiber_model.yaml \
  --workflow-profile my_helper/stnsnr/config/four_model_v1/workflow_task17_parity.yaml \
  --scale adl \
  --through observed \
  --workers 1 \
  --run-id task17-parity-v1-post-refactor-20260722
```

Then invoke the identical run root with the production worker ceiling and exact
resume. This invocation must restore every completed task and must not produce
a second cold cache generation:

```bash
env -u PYTHONPATH /opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/fiber/pipelines/run_dual_frequency_models.py run \
  --study-base /Volumes/VAL/STNSNr/summary/cohort/subj/study_base.json \
  --direct-voxel-model my_helper/stnsnr/config/four_model_v1/direct_voxel_model.yaml \
  --normative-fiber-model my_helper/stnsnr/config/four_model_v1/normative_fiber_model.yaml \
  --workflow-profile my_helper/stnsnr/config/four_model_v1/workflow_task17_parity.yaml \
  --scale adl \
  --through observed \
  --workers 14 \
  --run-id task17-parity-v1-post-refactor-20260722 \
  --resume
```

After both invocations, publish the immutable replay report with the
repository-owned verifier:

```bash
env -u PYTHONPATH /opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/fiber/pipelines/validate_task17_connectome_parity_fixture.py \
  --fixture my_helper/stnsnr/config/four_model_v1/acceptance/task17_connectome_parity_fixture.json \
  --parent-run /Volumes/VAL/STNSNr/summary/spot/.runs/stnsnr_frequency_addon/task17-main-v8-tau-grid-formal-20260717 \
  --replay-cache-root /Volumes/VAL/STNSNr/cache/dual_frequency_task17_parity_v1 \
  --replay-run /Volumes/VAL/STNSNr/summary/spot/acceptance/.runs/stnsnr_frequency_addon/task17-parity-v1-post-refactor-20260722 \
  --output /Volumes/VAL/STNSNr/summary/spot/acceptance/task17-physical-parity-replay-v1.json
```

The first command is the only cold replay. The second command is a same-root
resume and the third command is read-only except for its atomic acceptance
report. None is permitted while the independent OSS solver lineage is active.

After execution, invoke the same verifier with explicit replay cache and replay
run roots. Replay mode must require a completed new run, resolve the exact
fixture semantic IDs from the dedicated cache, validate full payload bytes,
validate the one-scale prepared-task closure, and require the same three
frequency-role signatures in voxel and fiber. Its report binds both the frozen
fixture SHA and the replay run manifest SHA. Authority and replay reports remain
separate; replay mode never rewrites either run or cache.

The prepared-task verifier accepts the retained authority's concrete
`ArtifactRef` and the refactored replay's persisted `IndexedArrayView` as
distinct exact schemas. A replay view may reference only the explicit replay
run or replay cache roots. Its parent, optional row selector, and optional
column selector each pass URI containment, declared SHA, dtype, shape, axis,
and NPY-header validation. The logical shape and feature-axis SHA must match
the frozen fixture. To compare against the authority's final NPY SHA without
writing or allocating a complete subset, the verifier emits the deterministic
NumPy v1 header into the digest and streams logical rows in C order, gathering
only a bounded selector block at a time. A parent payload already verified
through the physical cache closure is not hashed a second time. Duplicate,
negative, out-of-range, non-`int64`, or axis-inconsistent selectors fail
closed. Focused replay fixtures must cover identity views, a reordered/subset
view, cache-root containment, logical-byte parity, corrupt selectors, and
forbidden paths.

The replay verifier now implements this dual representation. It reuses the
already validated physical-cache SHA for an identical view parent, validates
other parents and selectors once, and streams one logical row in bounded
column blocks into the deterministic NPY digest. The retained concrete
authority path remains unchanged. Seven focused parity-verifier tests pass,
including identity and reordered subset views beneath the explicit cache root,
logical SHA equality, duplicate-selector rejection, and outside-root
rejection. The complete dual-frequency regression passes 576 tests under
Conda `leaddbs`. This closes verifier compatibility only; the configured cold
replay remains ordered after independent OSS.

A bounded read-only check of the completed v8 authority opened all 224
terminal prepared-task documents and only the first eight bytes of each
declared exposure payload. All 224 are concrete NPY files with format version
1.0 and none is an indexed view. This confirms that the verifier's streamed
NumPy v1 header reproduces the frozen authority serialization contract rather
than merely matching a synthetic fixture. No complete scientific payload was
read during this header audit.

The corrected fiber-only v2 authority verifier was executed twice on
2026-07-22. Both runs
validated the completed parent manifest, all nine complete physical payloads,
the three distinct frequency-role cache signatures, all six prepared Omega-max
identities, and every one of the 168 terminal-completed scale-local prepared
task payload copies. The second invocation produced the same report bytes and
left its modification and change timestamps unchanged. The synthetic verifier
suite passes four tests covering complete closure, immutable report replay,
duplicate-role rejection, incomplete-parent rejection, and explicit replay-root
validation. Authority-mode output remained byte-identical after replay mode was
added. This freezes the
pre-refactor authority only; it does not yet accept the post-refactor replay.

The complete v3 physical authority verifier was then executed twice. It added
three full direct-voxel physical payloads, all 56 terminal-completed voxel
prepared-task metadata records, and representative payload hashes for the two
distinct prepared voxel identities. Fiber closure remained nine physical
payloads and 168 fully hashed task payloads. Voxel and fiber independently
resolved the same three frequency-role signatures. The second v3 invocation
left the 9709-byte report and both timestamps unchanged. This closes authority
freezing for all four model families; post-refactor replay parity remains open.

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

The complete cache contract suite was rerun under Conda `leaddbs` on
2026-07-22 and passed 38 tests plus 18 subtests. Coverage includes atomic
manifest-last publication, same-byte reuse, failed staging cleanup, complete
payload and shard validation, copied-cache portability, corruption rejection,
process-local verification reuse, and cross-instance producer-lease
serialization. This local evidence proves the cache implementation boundary;
the active real OSS and later combined lineage still provide the required
production reuse evidence.

**Prepared-artifact duplication audit, 2026-07-22.** The completed v8 parent
contains 224 prepared tasks and 1008 prepared artifact references. Their
task-local payloads total 71778637112 bytes, while one payload per distinct
content SHA totals 2495860510 bytes. The measured duplicate write footprint is
therefore 69282776602 bytes. The largest repeated families are the prepared
reference matrix, add-on-only matrix, raw add-on matrix, reference-condition
matrix, add-on reference-component matrix, overlap mask, and full voxel ID
axis. This contradicts the final single-write target even though the upstream
physical cache itself is shared.

The first correction is process-local artifact verification reuse.
`ArtifactStore` currently recomputes the complete payload SHA on every
materialization, including repeated references to an immutable cache or task
artifact in the same persistent worker. Cache the successful verification by
resolved path, declared SHA, device, inode, size, modification time, and change
time. Skip only the digest pass when every field is unchanged; continue to
validate declared dtype, shape, axes, units, space, and loaded NPY structure on
every call. A changed signature must force a new SHA pass and corruption must
still fail closed. This cache is process-local and never enters resume or
scientific identity. It reduces rereads but does not by itself close the
69282776602-byte publication duplication; prepared cache-backed artifacts or
indexed views remain required afterward.

Process-local artifact verification reuse is now implemented for both NPY and
JSON materialization. The store records only a successful SHA check and the
full local file signature. Repeated unchanged materialization performs one
digest pass, while rewriting the same path changes its signature, forces a
second digest pass, and rejects the stale ArtifactRef. Loaded dtype, shape,
axes, units, space, JSON schema, and read-only behavior remain checked on every
call. The focused cache suite passes 38 tests plus 18 subtests. Large prepared
artifact single-write publication remains open.

The complete `dual_frequency/tests` regression suite was rerun after this
change under Conda `leaddbs` on 2026-07-22 and passed 557 tests plus 310
subtests. This confirms that verification reuse preserves the broader runtime,
cache, resume, scheduling, sensitivity, and publication contracts covered by
the suite; it is not evidence that the separate prepared-artifact single-write
requirement is complete.

The next correction uses cache-backed prepared artifacts before introducing
logical indexed views. Every prepared array role receives a portable scientific
cache identity bound to the parent physical-exposure identity, exact ordered
subject and feature axes, preparation role, reference dependency where
applicable, canonical space, and an explicit preparation algorithm version.
Endpoint ID, scale name, run path, worker count, and task order remain excluded.
The first producer writes the final NPY directly into an atomic cache staging
generation and publishes its manifest last. A prepared task returns an
`ArtifactRef` to that validated cache payload instead of copying the payload to
its task-local output directory. Later tasks and resume processes resolve and
validate the same entry before reuse. Small task-specific readiness and input
hash documents remain task-local.

This cache-backed boundary must cover reference exposure, add-on-only exposure,
raw add-on exposure, reference-condition exposure, add-on reference-component
exposure, reference-overlap mask, and canonical feature IDs. Each key must be
known before cache publication so a hit avoids a second NPY write. When the
scientific cache is not configured, the existing run-scoped publisher remains
the explicit compatibility fallback. Tests must prove cross-endpoint reuse,
cache-root artifact materialization, changed-axis separation, corruption
rejection, and no large task-local NPY for the cache-enabled path. This closes
repeated final-payload publication but does not remove the temporary subject or
feature subset copy; `IndexedArrayView` remains the subsequent step for that
allocation boundary.

Cache-backed prepared publication is now implemented for every listed array
role. Physical matrices carry a portable scientific identity through exact
subject and ordered feature subsetting; derived add-on identities additionally
bind the reference-overlap state and selected reference threshold without
binding endpoint or scale names. Cache-enabled tasks return validated
cache-root `ArtifactRef` values and publish only the small readiness and input
hash documents beneath the task root. The atomic generated publisher writes,
flushes, synchronizes, hashes, and closes one final NPY before manifest-last
commit. The cache-disabled compatibility path continues to use the run-scoped
publisher.

Focused input-provider acceptance passes 29 tests plus 5 subtests. It proves
same-identity reuse across distinct task publishers, changed-axis identity
separation, cache-root materialization, new-process corruption rejection, one
physical producer, and absence of task-local NPY payloads in the cache-enabled
path. The complete dual-frequency regression suite passes 558 tests plus 310
subtests. Post-refactor configured-data parity replay and measured v8-sized
write reduction remain required before this boundary is accepted as complete;
temporary subset allocation and `IndexedArrayView` also remain open.

A follow-up identity audit found that the first implementation still included
the requested `AxisRef.axis_id` in the prepared cache key and manifest. Endpoint
subject-axis IDs contain the endpoint ID, so otherwise identical ordered
subjects would not reuse one payload across scales. The correction excludes
axis labels from the portable identity and binds only ordered axis count and
SHA. Cache manifests use deterministic neutral axis labels derived from the
dimension and axis SHA, while each returned task `ArtifactRef` retains the
caller's exact endpoint-local axes. NPY bytes do not encode axis labels, and
the artifact store continues to validate the exact task axes, dtype, shape,
units, space, and payload SHA. Tests must prove that two different axis labels
with the same count and SHA reuse one URI, while a changed axis SHA does not.

The portable-axis correction is now implemented. Prepared cache keys and cache
manifest axes exclude endpoint-local labels, while returned artifacts rebind
the validated payload to the caller's exact axes. The focused provider suite
passes 29 tests plus 5 subtests and explicitly proves different endpoint axis
labels reuse one URI, preserve their own returned axis refs, and separate when
the ordered axis SHA changes. The complete dual-frequency suite remains green
at 558 tests plus 310 subtests.

The prepared key must also bind the explicit physical model domain. Several
artifact roles are intentionally shared by direct voxel and normative fiber;
their normally different feature-axis SHAs are not a substitute for a domain
contract. Add `direct_voxel` or `normative_fiber` to the backend and scientific
parameter identity so no cross-domain payload can collide even under an
artificial axis-hash match.

Explicit domain binding is now implemented and the provider fixture proves
that identical axes, dependencies, role, and bytes produce distinct cache URIs
across direct voxel and normative fiber. The focused provider suite remains at
29 tests plus 5 subtests and the complete dual-frequency suite remains at 558
tests plus 310 subtests.

`IndexedArrayView` is implemented in two ordered phases. The first phase is the
preparation-kernel boundary: a cache-backed physical matrix retains its parent
NPY plus exact ordered row and column positions. Subject and Omega-max subset
operations compose positions without allocating a subset memmap. Omega-max
counting, reference-overlap preparation, add-on-only preparation, and the
final generated-cache writer consume bounded feature blocks from the view.
Cache hits must return before reading view payload blocks. The cache-disabled
compatibility path may retain its existing concrete subset artifacts.

The first phase still publishes a final cache-backed `ArtifactRef`; it does not
satisfy the complete persisted `IndexedArrayView` record contract by itself.
The later phase will expose typed logical views to downstream kernels where a
full prepared payload is not otherwise scientifically required. Acceptance of
this first phase requires identical arrays and semantic IDs, zero subject or
feature subset memmap allocation on the cache-enabled path, bounded block
reads, one final payload write on a miss, and zero payload reads or writes on a
hit.

The persisted second-phase contract is
`IndexedArrayView(schema_version, parent, row_positions, column_positions,
axis_refs)`. `schema_version` is fixed to
`dual_frequency_indexed_array_view_v1`. `parent` is one immutable two-dimensional
array `ArtifactRef`. `axis_refs` contains the exact ordered logical row and
column axes. Each optional positions artifact is an immutable one-dimensional
`int64` array on the corresponding logical output axis, uses `index` units, and
contains parent-axis positions. A missing positions artifact is permitted only
when that logical axis is identical to the corresponding parent axis. The view
inherits dtype, units, and space from its parent; it cannot override them.

Construction and JSON decoding enforce the closed structural contract. Verified
materialization additionally preserves selector order and requires every
positions array to contain no duplicate, have minimum position > -1, and have
maximum position < the corresponding parent-axis count. Selectors may reorder
parent rows or columns because the declared logical axis, not parent storage
order, is authoritative. This split keeps the immutable record path-independent
while still rejecting corrupt or dishonest index payloads before scientific
use. The codec treats the view as both an allowlisted root record and an
allowlisted nested value. Its transitive artifact closure is the parent followed
by row and column positions in field order, with normal content-identity
de-duplication.

The artifact store exposes a bounded logical-column iterator for this record.
It verifies and opens the parent read-only, verifies selectors once, then
gathers no more than the requested feature-block width per yield. It never
implements implicit `np.asarray(view)`. An explicit full materializer requires
a positive caller-provided byte budget and fails before allocation when logical
array bytes > that budget. Downstream request and prepared-record fields migrate
to an explicit `ArtifactRef | IndexedArrayView` scientific-array union only
after their kernels use this bounded interface or declare and meter an external
contiguous-array boundary. Document artifacts and one-dimensional identity axes
remain plain `ArtifactRef` values.

For long-lived fiber hot loops, `ArtifactStore.open_indexed_array_view` returns
one context-managed read-only reader over the verified parent mapping. The
reader supports only explicit two-dimensional indexing with an integer, a
contiguous unit-step slice, or a one-dimensional integer position vector on
each axis. It preserves normal scalar-axis removal, preserves declared selector
order, applies the Cartesian product when both axes use position vectors,
rejects boolean or multidimensional selectors, and rejects a requested block
before gathering when block bytes > the positive open-time budget.
Implicit NumPy conversion always raises. Closing the reader invalidates later
reads and closes the parent memmap; callers may not retain it beyond the
backend workspace lifetime.

The first persisted consumer migration covers the two-dimensional scientific
arrays in `PreparedExposureRecord`: `exposure`,
`reference_condition_exposure`, `addon_reference_component_exposure`,
`reference_overlap_mask`, and `total_exposure`. Each accepts exactly
`ArtifactRef | IndexedArrayView` while `feature_ids` and
`auxiliary_readiness` remain plain artifacts. The prepared-record codec decodes
this union by its exact closed field set rather than by a permissive tag or
heuristic. Existing artifact-only records remain byte-compatible and retain
their identifiers. A view-backed record closes over the view parent and
selector artifacts and therefore remains self-contained for resume and
publication validation.

`ObservedRequest.exposure` is the first downstream request field migrated to
the same union. Direct-voxel observed backends declare one explicit contiguous
materialization budget because their current solver requires the complete
matrix. Normative-fiber observed backends instead keep one bounded reader open
for the workspace lifetime and retain their existing feature-block traversal.
Coverage, held-out counts, weight construction, and signed-score selection may
inspect reader shape and dtype and request explicit blocks, but may not call
`np.asarray` on the complete reader. Outcome, baseline, nuisance, and feature-ID
inputs remain arrays or plain artifacts.

On a scientific-cache-enabled preparation, the first real producer use is the
reference endpoint's primary exposure. The physical shared-exposure cache entry
is represented as the view parent `ArtifactRef`. Endpoint subject selection and
fiber `Omega_max` selection are published as small cache-backed `int64`
positions artifacts only when the logical axis is not exactly the parent axis;
an axis-label-only difference uses an explicit identity selector so the
endpoint axis remains exact. The resulting `PreparedExposureRecord.exposure`
is the persisted view, and the former final prepared-reference exposure NPY is
not written. Cache-disabled preparation retains the artifact-only compatibility
path. Tests must prove exact value parity, cross-endpoint selector reuse,
artifact closure and codec resume, zero prepared-reference exposure NPY write,
bounded observed-backend reads, and unchanged source selection.

Sensitivity-base serialization and canonical publication must preserve the same
logical record. Portable checkpoint remapping recursively remaps the parent and
selector artifacts, and the base descriptor emits an explicit indexed-view
payload rather than pretending that the view has one URI or payload SHA.
Canonical publication verifies and explicitly materializes the view under the
same 16 GiB contiguous replay budget only at its existing voxel publication
boundary. Resume artifact closure continues to enumerate and verify the parent
and selectors separately.

Adjusted-bootstrap nuisance reconstruction does not materialize a complete
view. It resolves the locked final feature positions first, then gathers only
those columns through a reader budget equal to the selected output bytes.
Artifact-only parents use the same selected-column path, so voxel and fiber
bootstrap reconstruction retain one alignment rule and view-backed reference
preparation cannot increase its scientific working set.

`InSampleRequest.exposure` also accepts the view because its frozen contract
starts from the complete prepared parent axis before applying the selected
tau/Coverage. The in-sample backend scans coverage through bounded blocks,
gathers only the resulting full-sample candidate columns, and closes the reader
before returning or raising. It never converts the complete parent view to a
NumPy array. Its explicit candidate gather budget is 16 GiB, matching the
existing contiguous replay ceiling while retaining the exact full-parent
selection semantics.

Final selected-exposure publication follows the same bounded rule. Resolve and
validate the final feature positions against the complete parent ID axis before
opening the exposure. For an `IndexedArrayView`, open one bounded reader and
copy only the locked final columns into the existing final selected-exposure
temporary matrix in feature blocks. The reader budget is the byte size of one
subject-by-feature block and must be positive. Do not call the complete-view
materializer. An artifact-only prepared exposure retains its existing
read-only mapping path. Both paths publish the same selected axis, dtype,
units, space, and payload bytes. Acceptance must force complete-view
materialization to fail while view-backed selected publication still succeeds
and matches the artifact-backed result.

This final selected-exposure boundary is now implemented. View-backed
publication keeps one bounded reader open and gathers only locked final
columns; artifact-backed publication retains the existing read-only mapping.
The focused provider suite passes 31 tests and explicitly forces the complete
view materializer to raise while selected publication remains byte-identical.
The complete dual-frequency suite passes 550 tests.

The next add-on migration covers `PreparedExposureRecord.total_exposure`.
This role is the raw add-on physical matrix before overlap exclusion and is
therefore an exact row/column view of the shared physical cache rather than a
derived array. On a cache-enabled preparation, persist the indexed view and do
not write a second raw-add-on NPY. Keep the existing artifact publication only
for the cache-disabled compatibility path. Add-on exposure sensitivity gathers
only locked final columns through one bounded reader. Its collinearity
diagnostic computes the per-subject mean by ordered feature blocks without a
complete-view allocation. The derived add-on-only exposure and overlap mask
remain concrete artifacts. Acceptance requires exact raw-array parity, no
task-local total-exposure NPY, bounded sensitivity reads, and unchanged
artifact-backed behavior.

This raw add-on migration is now implemented. Cache-enabled add-on preparation
returns an indexed view for `total_exposure`; the sensitivity adapter gathers
only final columns and computes its row mean through verified blocks. Focused
tests force the complete view materializer to fail, reproduce selected values
exactly, and reproduce row means within the declared floating-point tolerance.
The complete dual-frequency suite passes 551 tests.

The remaining raw add-on auxiliaries are
`reference_condition_exposure` and
`addon_reference_component_exposure`. Both are exact row/column views of
shared physical matrices, so cache-enabled preparation must persist views and
must not write duplicate prepared NPY files. Delta-reference voxel and fiber
kernels must validate the complete logical axes and scan full-parent support
or finiteness in bounded feature blocks, while gathering only the locked
reference feature positions required by the scoring operator. Bootstrap
continues to gather only final positions through its existing bounded path.
Sensitivity collinearity computes both row means blockwise. Cache-disabled
preparation and bare NumPy backend inputs retain their current behavior.
Acceptance requires artifact/view score, support, and QC parity for direct
voxel and normative fiber; complete-view materialization must be forced to
fail in the view fixtures.

This auxiliary migration is now implemented. Cache-enabled preparation returns
indexed views for both raw reference-component roles. Direct-voxel and
normative-fiber DeltaReference kernels scan parent support and finiteness in
bounded blocks, retain only selected operator columns, and never call the
complete-view materializer. Sensitivity computes both collinearity means
blockwise, while bootstrap continues to use its selected-column reader.
Dedicated voxel and fiber fixtures prove byte-identical scores and support
rows with complete-view materialization forced to fail. The complete
prepared-record codec fixture also round-trips all three raw add-on views and
reconstructs their transitive artifact closure. The complete dual-frequency
suite passes 553 tests.

Portable sensitivity replay must cover the complete prepared-record closure,
not only its primary exposure. A cache-backed add-on fixture must remap the
primary, reference-condition, add-on reference-component, and total views to
portable cache URIs, retain every parent and selector, encode and decode the
prepared record, then resolve the copied tree beneath a distinct cache root.
Every resolved artifact must pass NPY header and payload-SHA validation.
Neither the original absolute root nor a run scratch path may survive the
portable record.

The complete add-on portability fixture is now implemented. It remaps and
codec-round-trips the four indexed views, copies the cache to a distinct root,
resolves every parent, selector, feature-ID, overlap, and readiness artifact,
and verifies every payload SHA without retaining the original root. The
focused checkpoint suite passes 11 tests and the complete dual-frequency suite
passes 555 tests.

The preparation-kernel phase is now implemented. `_TemporaryMatrix` carries
immutable optional row and column positions over one parent memmap, composes
ordered subject and feature selections, exposes bounded column reads, and
retains the derived semantic identity. Omega-max counts columns blockwise.
Direct-voxel and normative-fiber overlap preparation consume logical blocks and
write only their scientifically required derived outputs. The generated cache
writer writes a logical view blockwise into its one final NPY on a miss and
returns before any block read on a hit. Cache-disabled execution retains the
concrete compatibility path.

The focused provider suite passes 31 tests plus 5 subtests. It proves zero
subset-memmap allocator calls for cache-backed subject and feature views,
logical-value parity, direct-voxel add-on overlap parity, absence of task-local
large NPY payloads, and a cache hit that succeeds while every logical payload
read is forced to fail. A dedicated normative-fiber fixture also proves that
blockwise reference overlap remains inclusive at the exact tau boundary and
preserves the add-on-only values. The complete dual-frequency suite passes 559
tests plus 310 subtests. Persisted downstream `IndexedArrayView` records and
configured-data parity replay remain open and are not claimed by this phase.

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

**Frozen direct-voxel hot-loop boundary, 2026-07-22.** The current vectorized
voxel evaluator has no feature-range loop, but it still resolves paths,
transforms, hashes, and sampler handles inside the physical-subject enumeration.
Replace the fiber-specific sampler descriptor with one immutable bilateral
sampling plan shared by the voxel and fiber evaluators. Because direct voxel
has one vectorized call per row, build each physical-row plan once immediately
before that pure call and then release the row reference; do not pin every row's
samplers simultaneously. The pure voxel evaluator receives only the plan and
canonical coordinates; it performs no path, transform, hash, cache, or
NIfTI-open operation. Preserve bilateral side maxima, side averaging,
missing-group behavior, translations, float32 output bytes, and the independent
voxel threshold contract. Acceptance requires exact output parity plus call
evidence that plan construction occurs once per physical row and no plan
construction occurs inside the pure evaluator.

The direct-voxel path now uses the same immutable bilateral plan descriptor as
normative fiber. Its pure evaluator accepts only sampler handles, translations,
and canonical coordinates. Physical preparation builds and consumes one plan
per physical row, then endpoint subset requests reuse the single cached matrix.
The complete input-provider suite passes 28 tests plus five subtests; the
two-overlapping-subset fixture proves one physical producer, one plan and one
pure evaluator call per physical subject, and identical overlapping rows.
Configured full-matrix parity and production resource counters remain pending.

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

**Frozen geometry-cache implementation boundary, 2026-07-22.** A read-only
audit found that the current adapter still partitions by a fixed count of
65536 fibers and resolves paths and sampler handles inside the connectome range
loop. It preserves canonical IDs and never splits a fiber, but it does not yet
satisfy the point-byte-balanced or path-free hot-loop contract. The three
configured connectomes contain approximately 718 MiB, 4.43 GiB, and 11.54 GiB
of float32 coordinate rows, with offset arrays below 91 MiB. Every complete
geometry is therefore `< 16 GiB` and eligible for the shared-resident path under
the current 48-GiB solver boundary.

Implement one portable `connectome_geometry` cache generation per semantic
connectome source. Its scientific identity contains source content SHA,
geometry hash, ordered canonical-ID hash, adapter name/version, coordinate
dtype, and cache schema. The generation contains a read-only
`points.npy` float32 array with shape `n_points x 3`, a read-only
`point_offsets.npy` int64 array with shape `n_fibers + 1`, and an audit document
with logical point count, HDF5 raw-chunk geometry, bounded source reads, and
point-ID validation. Canonical fiber IDs remain implicit as the complete
one-based axis. Publication uses the existing lease, temporary sibling, atomic
rename, manifest-last, and direct-copy verification contracts. A producer
streams HDF5 ranges into the generation and validates the fourth row without
allocating a point-sized expected-ID vector.

`StudyRuntimeInputProvider` must resolve immutable sampler handles and all
hemisphere/group metadata before entering a geometry range. The hot function
then receives only points, offsets, sampler handles, translations, and output
views. It performs no path lookup, transform lock, NIfTI open, cache lease, or
artifact publication. Current configured connectomes use one shared read-only
geometry memmap. A deterministic fallback for future larger connectomes builds
the fewest consecutive ranges below an explicit point-byte budget, never
splits a fiber, and selects each stop from cumulative offsets while minimizing
distance to an HDF5 raw-chunk boundary. Logical point coverage must be exact;
raw chunk overlap and partial boundary count are separate audit fields.

Charge normative-fiber `prepare_exposure` at 32 GiB rather than the generic
16-GiB preparation charge. The 32-GiB grant covers the largest configured
geometry memmap, the bilateral transformed-NIfTI sampler working set, output
rows, offsets, and bounded point scratch while allowing only one such task
under the effective managed-memory ceiling. Direct-voxel preparation retains
its existing charge. Acceptance requires byte-identical bilateral exposure,
`Omega_max`, selected axes, and final statistics against the current adapter;
identical output across range budgets and worker counts; one cache producer
under concurrent misses; direct-copy resume; corruption rejection; exact
logical point coverage; no split fiber; and measured absence of path,
transform, and NIfTI work inside the geometry loop.

The first adapter slice now caches the complete immutable point-offset axis,
exposes the HDF5 raw point-chunk width, validates every fourth-row canonical ID
with fiber-sized minimum/maximum reductions instead of a point-sized expected-ID
array, and provides deterministic point-byte-balanced half-open fiber ranges.
The planner preserves the minimal greedy range count and, within that count,
prefers fiber boundaries closest to raw HDF5 point-chunk boundaries. Legacy
fixed-fiber `iter_chunks` behavior remains byte-compatible at the API boundary.
The connectome suite passes 11 tests plus six subtests, including exact point
coverage, no split fiber, invalid-budget rejection, corrupted-ID rejection, and
an explicit guard that forbids `numpy.repeat` during point-ID validation. The
shared geometry cache, frozen sampler plan, provider hot-loop switch, and
32-GiB fiber admission are implemented in the following slices. Real-data
parity, direct-copy resume, and corruption rejection remain pending.

The second slice adds the portable `connectome_geometry` cache generation and
process-local read-only opener. The key binds source SHA, geometry hash,
ordered canonical-ID hash, adapter name/version, coordinate layout, and cache
schema while excluding endpoint, scale, run, worker, and branch identity. One
lease-protected producer streams point-balanced HDF5 ranges into `points.npy`
and `point_offsets.npy`, writes a bounded geometry audit, then relies on the
existing manifest-last atomic cache publication. Concurrent callers share one
generation and receive non-writeable memmaps. The input-provider plus cache
regression passes 63 tests and 23 subtests, including a four-caller concurrent
miss with exactly one producer invocation and exact coordinate/offset replay.
The third slice switches normative-fiber preparation to the shared geometry
memmaps whenever the scientific cache is available. It constructs one frozen
sampler plan per physical subject before entering the geometry loop; the pure
range evaluator receives only immutable samplers, translations, points, and
offsets. Future uncached or larger sources use deterministic point-byte ranges,
while synthetic adapters retain the legacy iterator for test compatibility.
Normative-fiber preparation now receives a 32-GiB admission charge and
direct-voxel preparation remains at 16 GiB. Complete geometry is mapped only
when its coordinate-plus-offset size is `< 16 GiB`; larger sources use the
point-balanced HDF5 stream without producing a complete geometry cache. A
two-range provider assertion proves that plan construction occurs once per
physical subject while the pure evaluator occurs once per subject and range.
A real HDF5 adapter fixture produces byte-identical exposure through complete
shared geometry, uncached point-balanced input, and forced over-budget
streaming. The same fixture proves direct-copy cache reuse without a producer
and payload-corruption rejection. The complete dual-frequency suite passes 555
tests plus 310 subtests, and the complete seed-target connectivity suite passes
80 tests plus 29 subtests with one environment-dependent skip. Configured
connectome parity against retained formal artifacts remains pending. These
source changes are not loaded into the already-running independent OSS worker
and therefore do not alter that lineage.

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
`managed = min(64 GiB, max(0, currently_available - reserve))`. Charge expected
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

A focused resume replay on 2026-07-22 passed seven tests under Conda
`leaddbs`. It proves exact restoration of a complete result, selective rerun of
undecodable or incomplete completed results, selective rebuilding of missing
operator scratch, selective jitter-block and consumer replay, and selective
pPAM-block and aggregate replay. It also crosses both `RunStore.open` and the
executor while changing audit-only configuration hashes, scientific hashes,
plan hashes, code identity, parent identity, source URIs, and machine paths;
unchanged JSON and ordered YAML content still restores the completed result,
while changed JSON or YAML content is rejected. A direct audit of
`RunStore._validate_resume` confirms that these audit-only fields are recorded
as provenance and are not hidden resume gates. This accepts the three-gate
resume implementation boundary; the active independent OSS lineage still
requires terminal replay evidence after its two equivalence gates close.

A 2026-07-25 isolated pre-merge replay exposed one test-only resource
dependency. The historical accepted-OSS cache-only resume fixture created its
initial expensive gate under the host's live available-memory measurement.
While the production OSS process held memory, that synthetic first pass could
not admit its 48-GiB grant and reported a scheduler deadlock before reaching
the resume behavior under test. The fixture must pin `_ResourceLedger` to a
synthetic 128-GiB total and available-memory state around all three invocations.
This keeps the real 48-GiB solver charge and 64-GiB managed ceiling intact,
makes the unit test independent of concurrent host load, and changes no
production executor or resume gate. The fixture now pins that synthetic memory
state. All eight focused resume tests and all 41 executor tests pass under
Conda `leaddbs` with warnings treated as errors while the independent OSS
process remains active.

A current focused resource and determinism replay on 2026-07-22 passed 14 tests
plus four subtests under Conda `leaddbs`. It verifies one closed pool generation
in fault-free execution, cumulative jitter-memory admission, exclusive OSS-axis
ownership of the single solver token, separation of solver work from pPAM
blocks and aggregation, and refusal to bypass the managed-memory ceiling. The
same gate proves worker-order parity for formal permutation and bootstrap,
schedule-order provenance, deterministic prefixes, production dependency
boundaries, and runtime construction with project namespaces blocked. These
tests accept the local scheduler and deterministic-kernel boundary; they do not
replace the active segment's continuous `< 64 GiB` task-tree RSS, zero swap
growth, terminal gate, or full DAG evidence.

The final resource audit also requires durable scheduler evidence rather than
reconstructing admission behavior from task timestamps. Every newly created
execution segment must therefore append the following non-scientific counters
when it closes:

- restored, scheduled, and terminal task counts;
- peak running-task count and maximum dependency-ready queue depth;
- peak reserved CPU, memory, connectome-I/O, and external-solver tokens;
- distinct admission-blocked task counts by worker-slot, CPU, managed-memory,
  memory-reserve, connectome-I/O, and external-solver reason;
- accumulated admission-wait seconds by the same reasons; and
- maximum wall-clock admission wait for any one task.

Admission time begins only after all dependencies are terminal and the task is
otherwise runnable. Dependency waiting, false gates, dependency-derived skips,
service runtime, and result persistence do not enter this value. A task blocked
by several resource predicates contributes to every applicable reason but
contributes only once to the distinct task count for each reason. The segment
stores aggregate numbers only; no scientific payload, endpoint value, absolute
artifact path, or cache identity enters these counters. They are audit
provenance and never enter task identity, cache identity, or resume gates.

Focused executor tests must force both worker-capacity and resource-token
waiting, require positive bounded wait values, verify exact peak token
reservations, and prove that a fault-free dependency chain with no admission
pressure records zero blocked tasks. Continuous process-tree CPU, RSS, swap,
VAL availability, and effective-core windows remain external guard evidence;
the scheduler counters do not claim to measure operating-system utilization.
The already running independent OSS segment predates this instrumentation and
continues to use its one-second guard as authority. Combined execution and the
configured parity replay must retain the new execution-segment counters.

This scheduler provenance is now implemented. The parent ledger records peak
reservations at admission, while the executor tracks dependency-ready depth,
running width, distinct blocked tasks, overlapping wait intervals by reason,
and the longest task-level admission delay. Closing an execution segment
atomically appends those counters together with restored, scheduled, and
terminal task totals; task and cache identities remain unchanged. A
dependency-only two-task chain records no admission block. Independent
two-task fixtures force positive worker-slot waiting and positive
managed-memory plus external-solver waiting, and verify exact peak grants. The
focused executor suite passed 33 tests. The complete isolated-package
dual-frequency regression passed 558 tests under Conda `leaddbs`. The active
independent OSS process was already loaded before this commit, so its existing
external guard remains the authoritative resource record for that lineage.

The parent scheduler must additionally reconcile live memory while production
spawn workers are active. Waiting on a future therefore uses a one-second
bounded poll. At each poll the parent samples currently available RAM,
process-tree RSS, and swap, then reconstructs admission capacity by adding the
ledger's already reserved memory back to live available RAM before applying the
same reserve and 64-GiB managed ceilings. This avoids double-charging a running
task while ensuring unrelated memory pressure immediately pauses new
admission. It never revokes a grant or releases tokens while work is running.

Each production execution segment must retain resource sample count, peak
task-tree RSS, minimum live available RAM, and peak swap growth. These fields
complement the admission counters and the external guard. The in-process test
executor remains deterministic and does not inspect host process state. The
external guard remains responsible for terminating an already running process
tree at the hard RSS, swap, or VAL boundary; internal reconciliation only
prevents additional admission. Focused tests must prove that a reduced live
available value blocks a new grant without double-charging the existing
reservation and that later recovery makes the same grant admissible.

Live reconciliation is now implemented for production spawn execution. The
monitor samples at most once per second while futures are active, refreshes the
ledger from live available RAM, and persists resource sample count, peak
process-tree RSS, minimum available RAM, peak swap growth, and final managed
capacity. In-process tests remain host-independent. The reconciliation fixture
holds one 48-GiB solver reservation, lowers live available RAM until both
managed-memory and reserve predicates block a second grant, then restores RAM
and proves the same grant becomes admissible without releasing the first one.
A separate deterministic monitor fixture validates the persisted sample
fields. The focused executor suite passed 35 tests and the complete
dual-frequency regression passed 560 tests under Conda `leaddbs`.

Hard-exit and timeout recovery first require an explicit per-task execution
policy. `TaskSpec` therefore gains three internal fields:
`timeout_seconds`, `transient_safe`, and `max_transient_retries`. Their defaults
disable timeout and retry. A timeout, when present, must be finite and positive.
A retry limit must be a nonnegative integer, and any positive retry limit
requires `transient_safe`. Checkpoint-only roots cannot declare timeout or
retry because they never invoke a service.

These fields describe execution recovery only. They do not enter `TaskKey`,
task ID, scientific configuration, cache identity, RNG identity, or resume
gates. Changing only these values must preserve the task ID. No current
production task receives a generic retry merely because the capability exists;
producer-specific external subprocess timeouts remain unchanged. A later
supervisor slice may requeue only a task whose explicit transient-safe policy
retains retry budget. Every other timeout or hard worker exit fails closed.

The recovery policy contract is now implemented and defaults remain disabled
for every compiled production task. Validation rejects nonfinite or
nonpositive timeouts, nonboolean safety declarations, negative retry limits,
retry without transient safety, and any recovery policy on a checkpoint-only
root. A direct identity fixture changes all three policy fields while retaining
the exact task key and task ID. The focused planner suite passed 21 tests and
the complete dual-frequency regression passed 562 tests under Conda
`leaddbs`. This accepts policy declaration and identity isolation only;
timeout detection, pool termination, quarantine, generation replacement, and
bounded retry remain the next supervisor slice.

The spawn supervisor applies the recovery policy as follows. A bounded parent
poll detects the earliest declared task timeout and `BrokenProcessPool`.
Either event terminates every worker in the affected generation, waits for
their exit, quarantines every in-flight run-owned attempt directory, and only
then releases its ledger grants. Cache producer locks retain the worker PID;
the next lease atomically quarantines a lock whose owner is no longer alive.
Unique cache staging names prevent a replacement writer from reusing an
orphaned temporary path. Before releasing that dead-owner lock, the recovering
contender must first acquire a nonblocking exclusive kernel recovery claim on
the opened stale-lock inode. Every contender revalidates that the claimed inode
is still the current producer-lock path and that its recorded PID remains dead.
Only the claim owner may atomically move every exact-identity
`.<semantic_sha256>.tmp-*` sibling into a uniquely created
`.<semantic_sha256>.orphan-*` quarantine directory. The atomic move targets
that directory's previously absent `payload` child, so it never deletes or
overwrites an older orphan. Recovery never scans another cache identity and
never moves staging while the recorded owner remains alive. The still-present
stale lock excludes a new lease-based writer during this quarantine window;
only after the staging moves complete may one contender rename the stale lock
and compete for a fresh lease. A second contender that cannot acquire the
claim waits without scanning staging. Process exit releases the kernel claim
automatically, preserving crash recovery without a second persistent recovery
file or two recovery owners.

Every in-flight task is classified independently. A task is requeued only when
it declares `transient_safe` and its consumed retry count remains below
`max_transient_retries`; it retains the same task ID, dependencies, RNG
identity, semantic target, and output root but receives a new immutable attempt
directory. Other tasks fail closed. Pending tasks that never entered the broken
generation remain eligible. A replacement pool starts only after the prior
generation is fully terminated and only when runnable work remains.

The execution segment records actual `pool_generation_count`,
`task_timeout_count`, `broken_pool_count`, `transient_retry_count`, and
`quarantined_attempt_count`. The segment begins with one provisional pool
generation and may replace only that counter with a larger final value when it
closes; no other start-time setting is mutable. Fault-free execution retains
one generation and zero recovery counters. Focused injected-pool tests must
cover successful bounded retry after timeout, successful bounded retry after a
hard-exit signal, exhausted retry failure, non-transient fail-closed behavior,
attempt quarantine, token release after termination, and no overlapping pool
generation.

The spawn supervisor is now implemented. Production workers create their own
process session so terminating a generation also reaches worker-owned external
subprocesses. The parent detects declared deadlines and broken-pool futures,
terminates the old generation, waits for worker exit, moves each run-owned
attempt to a unique quarantine path, releases grants, writes a nonterminal
retry boundary, and creates a replacement only when eligible work remains.
Retry-budget exhaustion and non-transient work fail closed. The run store
allows only `pool_generation_count` to increase when an execution segment
closes; all other initial settings remain immutable.

Injected process-pool fixtures prove timeout recovery, broken-generation
recovery, generation termination before replacement, same-task successful
retry, retry exhaustion, non-transient failure, attempt quarantine, and exact
recovery counters. Fault-free execution retains one generation and zero
timeout, broken-pool, retry, and quarantine counts. The focused executor suite
passed 38 tests and the complete dual-frequency regression passed 565 tests
under Conda `leaddbs`. Current production tasks retain the default disabled
generic timeout and retry policies, while their existing external subprocess
timeouts remain the only production timeout boundary.

Stale cache-owner recovery uses the kernel recovery claim above. The claim
keeps multiple waiters from acting on one dead lock concurrently, and inode
revalidation prevents a waiter holding the old renamed inode from touching a
replacement producer's staging. The original producer lock remains present
until exact-identity orphan staging has been quarantined. Each payload lands at
an initially absent `payload` child, preserving interrupted bytes without
overwrite. A live producer or recovery owner leaves staging untouched, and an
unrelated cache identity is never selected. Acceptance must cover dead-owner
staging preservation, two-contender serialization, old-inode rejection,
live-owner noninterference, identity isolation, stale-lock quarantine, and
successful new lease acquisition. The focused cache suite passes 42 tests and
the complete dual-frequency regression passes 567 tests under Conda
`leaddbs`, including a forced two-contender overlap and a lock-path replacement
between inode claim and revalidation.

- [x] **Step 8: Vectorize grid, statistics, and fiber-scoring kernels**

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

Exact rational cutoff fixtures must account for binary floating-point
representation. A mathematically exact support ratio at a declared cutoff is
treated as the cutoff, even when its float64 subtraction lands infinitesimally
below it. Direct-voxel and normative-fiber classifiers therefore require both
the strict comparison and failure of an absolute boundary-proximity test with
tolerance `1e-12`; values farther below remain eligible.

Implementation slice on 2026-07-19: route the shared
`partial_spearman_weights` entry point through the existing complete-finite
multi-RHS kernel whenever outcome, exposure, and nuisance inputs are finite and
the ranked nuisance design is estimable. The optimized path performs one
outcome solve and one all-feature solve per block. Preserve the historical
columnwise implementation as the nonfinite and rank-deficient fallback. Freeze
direct parity for average ties, constants, nonfinite feature cells, and
rank-deficient nuisance designs, and count linear-solver calls so passing tests
cannot silently retain one solve per feature.

The normative-fiber endpoint workspace also retains one immutable Coverage
count vector per evaluated tau. Seed it with the minimum-tau vector already
required to construct the maximal weight cache, reuse each vector across every
Coverage value, and reuse the selected tau vector during final-cell
materialization. A complete grid therefore scans exposure once per distinct tau,
not once again for source publication.

Acceptance evidence on 2026-07-19: complete finite blocks use exactly two
linear solves and match the retained scalar implementation for average ties and
constant columns. Nonfinite feature cells and rank-deficient nuisance designs
take the scalar fallback with numerical parity. A three-tau normative-fiber
grid invokes Coverage counting exactly three times across maximal-cache
construction, grid evaluation, and selected-cell publication. The statistics
gate passed 78 tests and 26 subtests; the statistics-plus-fiber gate passed 42
tests and 14 subtests. The complete dual-frequency plus visualization
regression passed with 488 tests and 241 subtests. At that checkpoint, Step 8
remained open for
direct-voxel grid-operator reuse and one-time endpoint/fold baseline prediction
construction.

Next implementation slice: bind one direct-voxel grid workspace to the exact
exposure, outcome, nuisance plan, direction, and hard limits for an endpoint
branch. Cache the boolean threshold matrix and full Coverage counts once per
distinct tau. Fit the nuisance-only held-out baseline prediction once per fold
and reuse it across all tau/Coverage cells and selected-cell publication.
Cell-specific candidate masks, feature weights, scores, model predictions,
computability, and classification remain independently recomputed; the
workspace must not leak selected-cell or outcome-fitted feature state.

Acceptance evidence on 2026-07-19: both the reference and adjusted add-on
direct-voxel backends construct one threshold/Coverage operator per distinct
tau and one nuisance-only prediction per held-out fold across grid evaluation
and selected-cell publication. The selected cell still recomputes its
outcome-dependent masks, weights, scores, model predictions, computability,
and retained arrays. The focused direct-voxel gate passed 29 tests and 5
subtests; the complete dual-frequency plus visualization regression passed 490
tests and 241 subtests. After that checkpoint, Step 8 remained open for the normative-fiber one-time
baseline prediction and explicit prevalidated scoring-workspace contracts.

Next implementation slice: add a `PrevalidatedFiberScoreWorkspace` that owns
only one validated exposure/ordered-fiber axis, the configured feature chunk
size, and reusable top-k merge/retained scratch. Every score call must validate
its new weight and candidate-mask vectors and must independently rebuild finite
support, sign partitions, canonical-ID tie ordering, and selected libraries.
The normative-fiber endpoint workspace binds one nuisance-only held-out
prediction vector to the exact outcome and nuisance plan and reuses it for all
grid cells and selected-cell publication. Tests must count one exposure/axis
validation per workspace, one baseline prediction per fold, stable scratch
identity after initial capacity allocation, exact parity with the public scalar
entry point, and changed selections when weights or candidate masks change.
The formal normative-fiber permutation and final in-sample paths bind one such
workspace to their fixed exposure/fiber axis. Observed scoring requests the
complete result needed for publication; null replicates request a lightweight
result containing only net scores, signed-support status, and signed counts.
No replicate weight, mask, ordering, selected ID, score, or support object may
survive into the next call.
The pPAM activation fit uses the same rule while its binary activation matrix
and canonical fiber axis are fixed: full and observed-fold calls retain the
published support metadata, whereas permutation-fold calls request only the
lightweight score state.

Final acceptance on 2026-07-19: the normative-fiber endpoint computes one
nuisance-only prediction per held-out fold across its grid and selected-cell
publication. `PrevalidatedFiberScoreWorkspace` validates the exposure and
ordered fiber axis once, reuses bounded top-k scratch, and reproduces the
public scorer while changed weights and masks produce independently changed
selections. Formal permutation, final in-sample, and pPAM permutation bind the
workspace only to fixed exposure/fiber axes; null calls return lightweight
score state without selected-ID arrays or hashes. Direct-voxel and
normative-fiber support classifiers now treat mathematical equality at strict
cutoffs as nonpassing despite float64 representation drift. The workspace gate
passed 76 tests and 28 subtests, the support-boundary gate passed 22 tests and 3
subtests, and the complete dual-frequency plus visualization regression passed
493 tests and 244 subtests. Step 8 is complete.

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

First Step 9 implementation slice: introduce one internal formal replicate
block size of 250 without exposing a YAML field. The parent constructs the
complete historical permutation or bootstrap index schedule with the exact
existing `default_rng(seed)` method-call sequence and argument shapes. Fixed
half-open block descriptors only lend immutable schedule slices; workers never
reseed, jump, advance, or infer draw counts. Tests concatenate multiple block
partitions and require byte identity with the historical full schedule,
complete nonoverlapping coverage, and identical output when worker assignment
order changes. The same descriptor carries NumPy version, Generator and
BitGenerator class, schedule schema, seed, replicate count, subject count, and
full schedule digest for later task publication and cross-environment resume.

Acceptance evidence on 2026-07-19: permutation schedules match the historical
row-by-row `default_rng(seed).permutation` payload byte-for-byte, and bootstrap
schedules match the historical single `integers` call byte-for-byte. Fixed
half-open slices reassemble the same payload after shuffled worker assignment;
the descriptor records PCG64, NumPy/environment identity, axis sizes, seed, and
the full digest. Formal LOOCV, final in-sample, and pPAM now use this shared
schedule constructor. The focused gate passed 60 tests and 25 subtests; the
complete regression passed 495 tests and 244 subtests. Step 9 remains open for
durable block records, planner tasks, parallel aggregation, bootstrap merging,
and block-level resume.

Second Step 9 implementation slice: refactor direct-voxel and normative-fiber
permutation numerics into pure fixed-interval block computations plus one
strict ordered aggregator before changing the workflow DAG. A block receives
the immutable parent schedule and one matching half-open descriptor and returns
only its null-statistic interval with the full schedule digest. The aggregator
accepts blocks in arbitrary worker-completion order but rejects a changed
digest, total, missing interval, overlap, duplicate, or noncontiguous coverage;
it reconstructs the historical replicate order before calculating the plus-one
p value. Full serial entry points must execute through the same block contract,
and multi-block synthetic tests must match the retained unsplit calculation
before durable records and planner tasks are introduced.

Second-slice acceptance on 2026-07-19: both formal model families execute the
public full permutation entry point through the schedule-bound block contract;
three-block standalone results reassemble with exact null-statistic parity even
when supplied in reverse completion order. Aggregation rejects incomplete,
overlapping, noncontiguous, nonsequential, duplicate, wrong-total, or
wrong-schedule-digest blocks before calculating the plus-one p value. The
focused formal suite passes 40 tests and 15 subtests, and the complete
dual-frequency plus visualization regression passes 497 tests and 246
subtests. Step 9 remains open for durable schedule/block records, planner DAG
tasks, parent-managed shared operators, block-level resume, bootstrap merging,
and pPAM block execution.

Third Step 9 implementation slice: freeze durable records before exposing block
tasks in the execution DAG. `ResamplingScheduleRecord` binds one target, exact
resampling kind, subject and replicate axes, seed, replicate count, internal
block size, RNG schema/classes/version/environment fingerprint, complete
schedule digest, and immutable schedule artifact. `ResamplingBlockRecord` binds
one target and kind to that schedule digest, full replicate axis, exact
half-open block interval, block-local axis, technical completion status, and
immutable block artifacts. Both records use the closed JSON codec and reject
unknown fields, invalid digests, inconsistent axes/counts, noncanonical block
indices, or artifact-axis mismatches. The executor's existing completed task
JSON and artifact SHA verification then provide block-level resume without a
new resume gate. Planner migration remains disabled in this slice because a
spawned block task must not rebuild or pickle the complete fold operators; the
parent-managed read-only operator scratch contract is required first.

Third-slice acceptance on 2026-07-19: the two records are closed-codec roots
with canonical identifiers and exact artifact closures. The schedule record
requires the fixed internal block size, subject/replicate axes, dtype implied
by schedule kind, RNG provenance and two independent payload identities. The
permutation block v1 record requires the canonical 250-replicate interval and
derived local axis, one matching float64 null-statistic artifact, its parent
schedule ID/digest, and a terminal technical status. Malformed fields, axes,
artifacts, block sizes, and intervals fail before persistence. The focused
record/formal gate passes 60 tests and 37 subtests; the complete regression
passes 498 tests and 248 subtests. No planner stage changed, so shared operator
scratch and actual block-level execution/resume remain open.

Fourth Step 9 implementation slice: implement the run-scoped operator scratch
foundation without changing the planner. One predecessor workspace task will
own an exclusive generation directory beneath its task work directory and
atomically publish only `.npy` arrays plus a small immutable descriptor. Array
descriptors bind a unique logical name, safe generation-relative filename,
dtype, shape, C/Fortran memory order, and byte count. Spawned workers reopen every array with
`mmap_mode='r'`, verify the NPY header and descriptor before use, and receive no
operator payload through pickling. Direct-voxel fixed-shape fold fields are
stacked by fold. Normative-fiber fixed-shape fields are stacked, while each
fold's variable estimable-index and standardized-coefficient arrays use
separate contiguous NPY payloads. A padded 3D coefficient array is forbidden:
its strided fold view changes BLAS accumulation order and produced an observed
Pearson-rho difference of approximately `1.1e-16` in the parity gate.
Reconstructed views must reproduce the in-memory operator calculations
exactly. Publication uses a new exclusive generation instead of overwriting an
existing file. Cleanup may
unlink only descriptor-enumerated files in that generation and remove the
directory only when empty; failed or partial workflow execution retains the
generation for resume.
All functions that accept the task work-directory `Path` are private runtime
infrastructure. They must not widen the public scientific-backend signatures;
scientific block computation receives only typed records, arrays, and the
validated scratch descriptor.

Fourth-slice acceptance on 2026-07-19: direct and fiber in-memory fold
operators publish into exclusive generations and reopen as descriptor-verified,
nonwriteable memmaps. Both model families reproduce every observed metric with
zero numerical difference. The fiber parity failure from padded strided views
is eliminated by preserving each variable coefficient matrix as a separate
Fortran-order payload. A real macOS spawn worker receives only the descriptor
and reopens all arrays successfully. Cleanup rejects and preserves a generation
containing an untracked file, then removes only the enumerated files once the
directory is clean. The raw-Path public-API boundary passes. The focused gate
passes 42 tests and 13 subtests; the complete regression passes 500 tests and
248 subtests. Descriptor persistence, predecessor workspace tasks, and block
DAG execution remain open.

Fifth Step 9 implementation slice: persist the operator descriptor without
misclassifying scratch as a scientific artifact. `FormalOperatorScratchRecord`
binds the final target, model family, exact subject/feature axes, canonical
scientific input identity, operator schema, completed status, run-root-relative
generation path, ordered array-header records, and total payload bytes. It has
an empty artifact closure and may not contain an absolute path or parent
traversal. Runtime conversion resolves the generation only beneath the current
run's `work` directory and rebuilds the internal descriptor. During resume, a
completed workspace task is restored only when every listed NPY file still
reopens read-only with the declared dtype, shape, memory order, and byte count.
If validation fails, that workspace task becomes pending and reruns; unrelated
completed block outputs remain restorable. No repository code identity enters
this gate.

Fifth-slice acceptance on 2026-07-19: the scratch root round-trips through the
closed codec with an empty artifact closure and rejects absolute/traversing
paths, altered total bytes, malformed array paths, fields, or headers. Runtime
conversion resolves only beneath the current run's `work` directory and
reconstructs the original descriptor. Executor resume restores a completed
workspace task while its generation is structurally valid; after the same
generation is removed through descriptor-confined cleanup, resume reruns only
that workspace task. The focused record/executor/formal gate passes 76 tests
and 44 subtests; the complete regression passes 502 tests and 249 subtests.
Actual workspace services and block planner tasks remain open.

Sixth Step 9 implementation slice: implement and register the two predecessor
services before changing planner topology. The schedule service constructs one
exact `FormalRequest`, generates the complete historical permutation schedule,
publishes it once as `formal_resampling_schedule`, and returns the fully bound
`ResamplingScheduleRecord`. Its loader verifies target, axes, seed/count/kind,
artifact metadata, full schedule digest, and row semantics before lending any
slice. The operator-workspace service constructs the same request, materializes
only its declared artifacts, builds the direct or fiber fold operators once,
publishes one exclusive scratch generation, and returns the input-bound
`FormalOperatorScratchRecord`; any failure after generation creation performs
descriptor-confined cleanup. Focused service tests use the real typed provider
boundary for all four endpoint model families, including adjusted add-on
DeltaReference inputs, and require that neither service performs formal
permutation fits or publishes a `FormalResult`. The production planner remains
unchanged until both services pass independently.

Sixth-slice acceptance on 2026-07-19: the generic production registry now
contains `prepare_formal_permutation_schedule` and
`prepare_formal_operator_workspace` as registered but not yet planned
services. All four endpoint model families, including both adjusted add-on
paths, construct the locked permutation request through the typed provider
boundary. The first publishes and restores the complete
historical schedule with exact bytes and rejects a changed schedule digest.
The second materializes the fixed operator inputs once, publishes a
run-relative read-only generation, and returns an input-bound scratch record
without calling `run_formal` or producing a `FormalResult`. A forced failure
after generation publication initially removed only that new descriptor
generation; the Eighth-slice failed/partial retention rule below supersedes
that cleanup behavior.
The focused service, formal, codec, executor, registry, spawn, and dependency
boundary gate passes 89 tests and 48 subtests. The complete dual-frequency and
visualization regression passes 504 tests and 253 subtests. No production task
count or planner dependency changed in this slice; permutation block and
aggregate services remain open.

Seventh Step 9 implementation slice: register the permutation block and
aggregate consumers without changing planner topology. One block service takes
the canonical internal `block_index` task parameter, one matching
`ResamplingScheduleRecord`, and one input-bound
`FormalOperatorScratchRecord`. It restores the exact `FormalRequest`, validates
the complete schedule before lending the canonical interval, validates the
scratch target, model family, axes, input identity, and read-only NPY headers,
then reopens the existing direct or fiber fold operators without rebuilding
them. It publishes only one block-local null-statistic artifact and one
`ResamplingBlockRecord`; it does not compute observed metrics or publish a
`FormalResult`.

The aggregate service requires the schedule, scratch, and complete set of
canonical block records. It rejects a missing, duplicated, overlapping,
noncontiguous, changed-target, changed-axis, changed-schedule, or malformed
block before calculating a p value. It computes the observed statistic once
through the same reopened operators, reconstructs null values in historical
replicate order, and publishes the existing final `FormalResult` schema. The
final result references the exact upstream schedule artifact rather than
copying it into the aggregate task. This slice retains operator scratch after
success or failure so later resume and extensions remain possible. Focused
tests cover all four endpoint model families, reverse block completion order,
missing-block rejection, no operator rebuild, and equality with the retained
serial result. The production planner remains unchanged until both consumers
pass independently.

Seventh-slice acceptance on 2026-07-19: the production registry now contains
`run_formal_permutation_block` and `aggregate_formal_permutation` as unplanned
services. Reference voxel, reference fiber, adjusted add-on voxel, and adjusted
add-on fiber complete the typed single-block path while patched operator
builders remain unused. A 251-replicate direct and fiber fixture publishes the
canonical 250-replicate first block plus the one-replicate tail. Reverse record
order reconstructs null statistics with exact array equality to the retained
serial path and preserves identical observed metrics and formal p values.
Missing coverage, changed parent schedule identity, and changed scratch input
identity fail closed. Aggregate output references the upstream schedule
artifact, and scratch remains present until explicit descriptor-confined test
cleanup. The focused formal, service, codec, executor, spawn, and dependency
gate passes 90 tests and 50 subtests. The complete dual-frequency and
visualization regression passes 505 tests and 255 subtests. The production DAG
and task count remain unchanged; planner migration is the next open slice.

Eighth Step 9 implementation slice: migrate only formal permutation planner
topology for new execution plans. For each realized-final endpoint, replace the
single serial service with one `formal_permutation_schedule` task, one
`formal_operator_workspace` task, the YAML-derived number of canonical
`formal_permutation_block_NNNN` tasks, and one aggregate task. Block count is
the ceiling of the configured endpoint permutation count divided by the fixed
internal 250-replicate size. Each block carries only the immutable
`block_index` execution parameter. No YAML field or worker-count dependency is
added.

Schedule and workspace tasks receive the same endpoint input, prepared
exposure, optional DeltaReference bundle, and final selection used by the old
formal task. Every block directly receives that complete typed closure plus
both predecessor records so a spawned worker does not depend on transitive
record injection. The aggregate directly receives the typed closure,
predecessors, and every block record. It retains stage
`formal_permutation`, output type `FormalResult`, the final-realized gate, and
the existing downstream task identity. In-sample and sensitivity dependencies
therefore continue to point to the aggregate. The four family-specific serial
services remain registered only as historical compatibility entry points and
are absent from new plans. New schedule, workspace, block, and aggregate
stages use the existing formal resource class. Planner tests must prove exact
block count and indices, complete direct dependency closure, topological
ordering, generic-service registry closure, and absence of serial formal
services before full regression. A synthetic interrupted-run test marks one
completed block and its aggregate nonterminal, resumes the same plan, and
requires only that block plus aggregate to execute while schedule, workspace,
other blocks, observed, resolver, final, bootstrap, and in-sample remain
restored.

Because each task reconstructs the same selected exposure beneath its own work
directory, scratch input identity uses the selected payload content SHA,
schema, dtype, shape, ordered axes, units, and space rather than artifact URI,
task-local producer ID, or producer version. It still binds the realized final
identifier, resampling kind, outcome/baseline/Delta/feature-ID content,
subject/feature axes, direction, hard limits, connectome role, fiber scoring
settings, replicate count, and seed. Equal content published at different
task-local paths therefore reuses the workspace; any scientific-content or
metadata difference still fails closed.

Every actual task invocation writes beneath a new immutable attempt directory
inside `work/<task_id>/`. The task checkpoint references artifacts from the
successful attempt; resume creates another attempt and never overwrites,
deletes, or truncates an earlier completed, failed, or partial attempt. This
attempt isolation is execution provenance, not a scientific identity or resume
gate. Scratch validation resolves the run root from the enclosing `work`
directory so both historical task-root layouts and new attempt-root layouts
remain readable. The interrupted-run acceptance must also prove that the old
block and aggregate attempts remain byte-identical after the replacement block
and aggregate complete.

The workspace service applies the same failure rule internally: once an
operator generation exists beneath its attempt directory, a later descriptor
or publication failure must leave that generation in place. Production code
does not perform failure-path scratch cleanup. Descriptor-confined cleanup is
available only to explicit maintenance or test teardown and is never invoked
automatically for a failed or partial run.

Eighth-slice acceptance on 2026-07-19: all four endpoint families now plan the
generic schedule, workspace, fixed block, and aggregate topology. The block
count follows each model profile's actual permutation count, every spawned
consumer receives the complete typed dependency closure, and no new YAML or
worker-derived scientific parameter is present. Task-local selected-exposure
paths no longer change scratch identity; scientific payload SHA or metadata
changes still do. A full synthetic 251-replicate direct-voxel run produces the
canonical 250-replicate block and one-replicate tail. After one block and its
aggregate are marked nonterminal, resume invokes exactly one block service and
one aggregate service; schedule, workspace, the other block, observed,
resolver, final, bootstrap, and in-sample results are restored. Both earlier
attempt directories remain byte-identical while replacement artifacts are
published beneath new attempt directories. Focused planner, formal, service,
executor, codec, and synthetic coverage passes 110 tests. The complete matrix
passes 483 dual-frequency tests, eight separately invoked goal guards, and 14
visualization tests. No production, jitter, OSS-DBS, or combined extension was
started in this slice.

Ninth Step 9 implementation slice: decompose direct-voxel and normative-fiber
bootstrap numerics before adding durable tasks. One independent block consumes
only its immutable rows from the complete historical bootstrap schedule and
returns feature-aligned partial sums, squared sums, finite/candidate/sign and
optional sweet/sour counts, block-local replicate count/support vectors, and
replicate-indexed nuisance or non-estimability evidence. It does not publish a
final bootstrap result and does not retain a block-by-feature weight matrix.

The strict aggregate orders blocks by canonical replicate interval, rejects a
changed schedule digest, duplicate, overlap, gap, changed feature length,
changed selection mode, or malformed evidence, then combines integer counts
exactly and floating moments in canonical block order. Integer and categorical
mismatch count must be `< 1`; floating summaries must remain within the
existing serial tolerance. The public full bootstrap functions execute through
the same block and aggregate contract. Direct and fiber 251-replicate fixtures
must cover the canonical 250-replicate block and one-replicate tail, accept
reverse worker completion order, match the retained serial computation, and
reject incomplete coverage. Durable bootstrap records, planner migration, and
pPAM block execution remain outside this numerical slice.

Tenth-slice acceptance on 2026-07-19: the pPAM fit now creates one complete
historical schedule, executes schedule-bound null blocks against the fixed
in-task operators and scoring workspace, and reuses the shared strict ordered
aggregator for the plus-one result. A 251-replicate fixture produces the
250-replicate block and one-replicate tail, matches the retained
single-interval null exactly, accepts reverse completion order, and rejects
incomplete coverage or a changed schedule digest. Existing activation status,
publication, strict threshold, overlap, and authorization tests remain green.
The OSS/pPAM module passes 23 tests; the complete matrix passes 485
dual-frequency tests, eight separately invoked goal guards, and 14
visualization tests. The sensitivity DAG and durable artifact schemas remain
unchanged, and no production OSS process was invoked.

Eleventh Step 9 implementation slice: freeze durable bootstrap block output
before adding services or planner tasks. `BootstrapBlockRecord` binds the final
target, parent bootstrap schedule record and digest, feature axis, complete
replicate axis, canonical block axis and interval, selection mode, adjusted
nuisance-evidence mode, and terminal technical status. It carries only
feature-aligned weight sum, squared-weight sum, finite/candidate/positive/
negative counts, optional sweet/sour counts, block-local candidate/valid/support
vectors, and one strict evidence JSON document. It never carries per-replicate
feature weights.

Publication uses immutable run-scoped artifacts with complete dtype, shape,
axis, units, space, and SHA metadata. Restoration verifies every artifact and
evidence field against the parent schedule and record before constructing the
numerical block. Direct and fiber round trips must preserve exact arrays and
evidence, reject a changed parent, axis, kind, shape, digest, interval,
selection mode, or incomplete adjusted evidence, and remain compatible with
reverse-order numerical aggregation. Planner task count and production service
selection remain unchanged in this record-only slice.

Eleventh-slice acceptance on 2026-07-19: direct-voxel and normative-fiber
blocks publish and reopen with exact accumulator arrays and evidence. The
fiber closure contains sweet/sour counts while the voxel closure does not; both
exclude every replicate-by-feature artifact. Changed parent schedule, feature
axis, artifact kind, shape, payload SHA, selection closure, or incomplete
adjusted evidence fails closed. The focused codec and formal suites pass 57
tests. The complete matrix passes 487 dual-frequency tests, eight separately
invoked goal guards, and 14 visualization tests. Production planner topology
is unchanged, and no production or sensitivity run was started.

Twelfth Step 9 implementation slice: replace each planner-selected serial
formal-bootstrap task with one bootstrap schedule task, one fixed task per
canonical 250-replicate interval, and one strict aggregate task. The schedule
and every block retain the endpoint's complete typed scientific predecessor
closure. Adjusted add-on blocks additionally retain matched-reference input,
prepared exposure, reference dependency, and DeltaReference inputs so each
sample can rebuild its nuisance state independently. No permutation operator
workspace is shared with bootstrap because every bootstrap replicate must
refit the sampled model.

The block service reconstructs the same final-selected `FormalRequest`, opens
the complete immutable bootstrap schedule, computes only the requested
interval, and publishes one `BootstrapBlockRecord`. The aggregate requires all
canonical records, reopens and verifies every artifact, combines them in
replicate order, and publishes the unchanged final bootstrap result schema.
The legacy family-specific serial bootstrap handlers remain registered only
for historical compatibility and must be absent from newly compiled plans.
Resume acceptance uses 251 replicates: after one block and the aggregate become
nonterminal, exactly that block and the aggregate rerun; schedule, other block,
observed, resolver, final, permutation, and in-sample work remain restored, and
all prior attempt artifacts remain byte-identical.

Twelfth-slice acceptance on 2026-07-19: newly compiled plans select the
bootstrap schedule, canonical blocks, and aggregate for reference/add-on voxel
and fiber endpoints; none selects a historical family-specific serial
bootstrap service. Four-model 251-replicate service fixtures match the serial
final arrays within `1e-13` relative and absolute floating tolerance, and match
integer arrays, summaries, adjusted nuisance QC, attrition evidence, and
model-specific output closure exactly. Missing block coverage fails closed.
The end-to-end resume fixture reruns exactly one invalidated block and its
aggregate while every predecessor and the other block remain restored; both
old attempt generations remain byte-identical. The complete matrix passes 490
dual-frequency tests, eight separately invoked goal guards, and 14
visualization tests. No production, jitter, OSS-DBS, or combined extension was
started.

Thirteenth Step 9 implementation slice: freeze a pPAM-specific durable
permutation block record before splitting the activation task. The record binds
the final-model target, exact parent permutation schedule identifier and
digest, complete replicate axis, canonical block interval and axis, terminal
technical status, and one immutable block-local LOOCV Spearman artifact. It
does not contain activation probability, binary exposure, fold weights,
predictions, selected fibers, or physical OSS rows.

Publication and restoration reuse the same parent-pregenerated schedule and
canonical 250-replicate intervals as formal inference, but retain a distinct
pPAM artifact kind and units contract. Closed-codec and runtime tests must
round-trip exact null bytes and reject changed schedule target, identifier,
digest, interval, artifact kind, axis, shape, units, or payload SHA. The
activation service and sensitivity extension planner remain unchanged in this
record-only slice; the next slice must first freeze the observed pPAM workspace
needed to prevent every block task from repeating physical OSS preparation or
rebuilding retained observed output.

Thirteenth-slice acceptance on 2026-07-19: the closed record codec round-trips
the dedicated pPAM block, artifact discovery includes its only numerical
payload, and runtime publication restores the exact null bytes from a
read-only artifact store. Negative tests reject changed artifact kind, parent
schedule identity or digest, and corrupted payload SHA before returning
numerical state. The focused codec and OSS gate passed 35 tests and 39
subtests. The full dual-frequency gate passed 502 tests and 295 subtests
outside the restricted system-monitoring sandbox. No production or sensitivity
extension was started.

Fourteenth Step 9 implementation slice: extract one in-memory pPAM fit
workspace before introducing its durable run-scoped representation. Workspace
construction validates the inherited final axis, applies the reference-overlap
mask, builds the nuisance plan, fixed full and fold weight operators, and fiber
score workspace once, then computes the complete observed fit and technical
eligibility state once. A block function accepts only this prepared workspace,
the complete parent schedule, and one canonical interval. The ordered
aggregate accepts the same workspace and a complete set of non-overlapping
blocks, computes the plus-one two-sided tail, and returns the existing
`PPAMFitResult` without changing any `ActivationArtifact` field or serial
numerical output.

The retained `fit_ppam_activation` entry point becomes a compatibility wrapper
over workspace construction, fixed block execution, and ordered aggregation.
The existing public single-block helper may construct a workspace for bounded
parity tests, but the later production block service must receive a durable
workspace and must not invoke that compatibility path. Tests must prove that a
251-replicate two-block execution builds fixed operators and observed state
once, preserves exact schedule bytes and block results, and matches every
legacy result array, scalar, status, failure reason, support field, and plain
control within the existing floating tolerance. This slice changes no planner,
record codec, service registry, production output, or sensitivity execution.

Fourteenth-slice acceptance on 2026-07-19: the 251-replicate fixture constructs
one pPAM fit workspace, one complete historical schedule, a 250-replicate
block, and the one-replicate tail. The fixed-operator builder is invoked once
across observed fitting and both canonical blocks. Reverse block completion
matches the single-interval null bytes exactly, and explicit
workspace/block/aggregate execution matches every compatibility-wrapper
result field exactly. Missing coverage and changed parent schedule digest
continue to fail closed. The OSS gate passed 24 tests and 12 subtests; the full
dual-frequency gate passed 502 tests and 295 subtests outside the restricted
system-monitoring sandbox. No planner, record, production, jitter, OSS-DBS, or
combined extension was started.

Fifteenth Step 9 implementation slice: separate the retained observed pPAM
state from the in-memory numerical operators. The observed state contains only
the exact arrays, support evidence, performance metrics, technical reasons,
peak-score comparison, and plain-control outputs needed to construct the final
`PPAMFitResult`; it contains no permutation null and no operator object. Its
permutation-readiness decision is derived only from the retained technical
reasons. The workspace aggregate first projects the observed workspace into
this state, then calls one state-level ordered aggregate. A later durable
record can therefore restore the state and fixed-operator scratch separately
without reconstructing or rerunning the observed fit.

Tests must compare every state-derived final field with the existing workspace
and compatibility paths, require a complete parent schedule when the observed
state is permutation-ready, reject any supplied null block when it is not
permutation-ready, and preserve the current degenerate-status classification.
This slice changes no artifact schema, planner, service, or production path.

Fifteenth-slice acceptance on 2026-07-19: the compatibility and workspace
aggregates both delegate to the operator-free observed state and preserve every
final field exactly. A permutation-ready state fails before aggregation when
its parent schedule is absent. A retained degenerate state completes with the
historical activation-degenerate classification and all-NaN null axis only
when no schedule or block is supplied; any supplied null state fails closed.
The focused OSS gate passed 25 tests and 12 subtests, and the complete
dual-frequency gate passed 503 tests and 295 subtests outside the restricted
system-monitoring sandbox. No artifact schema, planner, production, jitter,
OSS-DBS, or combined extension changed or ran.

Sixteenth Step 9 implementation slice: define the durable observed-workspace
record before changing the sensitivity DAG. The record binds the exact final
model, reference or add-on fiber family, subject and final feature axes,
scientific input identity, activation request parameters, all named immutable
input artifacts, the observed-output artifact set, technical readiness, and
one optional run-relative fixed-operator generation. It never contains a null
block or physical OSS row.

Three terminal observed states are explicit. `permutation_ready` requires the
complete observed output set and fixed-operator scratch.
`observed_not_permutation_ready` retains the complete observed outputs and
scratch but permits no schedule or null block. `nuisance_not_estimable`
retains the continuous and binary activation inputs plus reason-coded state,
requires no scratch, and permits no schedule or null block. The record carries
named activation probability, binary exposure, outcome, baseline, peak final
score, final feature IDs, activation feature IDs, optional reference-overlap
mask, and optional nuisance inputs so a later process reconstructs the exact
typed `ActivationRequest` without calling the physical OSS producer or
republishing inputs.

The scratch contract uses immutable run-relative NPY generations and explicit
header descriptors for the nuisance plan and full/fold weight operators. A
restored record is reusable only when its input identity, final axes, request
parameters, named artifacts, observed-state document, and every scratch header
match. Missing or malformed scratch invalidates the observed task and all of
its descendants; it never falls back to rebuilding operators inside a null
block. This record-and-codec slice leaves the planner and activation service
unchanged.

Sixteenth-slice acceptance on 2026-07-19: the closed codec round-trips all
three terminal modes, a reference permutation-ready workspace, and an adjusted
add-on observed-only workspace. Artifact closure contains every immutable
named input and observed output but excludes run-scoped scratch files. Changed
branch semantics, an incomplete scratch descriptor set, scratch attached to a
nuisance failure, and malformed persisted scratch all fail closed. The focused
codec gate passed 12 tests and 28 subtests; the complete dual-frequency gate
passed 504 tests and 296 subtests outside the restricted system-monitoring
sandbox. The production planner and sensitivity extensions remain unchanged.

Seventeenth Step 9 implementation slice: make the fixed pPAM operator state
portable across spawned workers without yet changing the sensitivity planner.
The observed worker writes one immutable `ppam-generation-*` directory under
its task attempt. It contains the full and fold nuisance covariates, training
rows, ranked nuisance matrices, estimable masks, and standardized exposure
residual operators listed by the durable observed-workspace record. Compact
standardized residual columns occupy a deterministic prefix; the estimable
mask supplies the exact logical width. A zero-width logical operator retains
one zero-filled storage column so the NPY generation remains structurally
valid.

Publication uses temporary NPY siblings followed by atomic rename, read-only
permissions, and an exclusive generation directory. Reopen validates the exact
descriptor names, dtype, shape, order, byte count, and run-relative location
before constructing `PPAMPermutationWorkspace`. The reconstruction path may
instantiate scoring scratch from the immutable binary exposure and final fiber
IDs, but it must not call nuisance construction or `_weight_operators`.
Descriptor-confined cleanup rejects untracked files. A fresh macOS spawned
process must reproduce one null block from reopened state and release every
memmap cleanly. Missing, truncated, writable-metadata, or request-mismatched
scratch invalidates the parent observed task. This slice leaves observed-output
publication, block services, and planner topology unchanged.

Seventeenth-slice acceptance on 2026-07-19: one real pPAM permutation
workspace publishes the complete descriptor set, reopens every array as a
read-only memmap, and reproduces the retained null block byte-for-byte without
calling `_weight_operators`. A fresh macOS spawned interpreter repeats the
same reopen and numerical check through `ArtifactStore`. The zero-estimable
case retains one physical padding column and restores zero logical columns.
Changed request identity, an absent descriptor file, and untracked cleanup
content fail closed; descriptor-confined cleanup removes the remaining valid
generation. The joint formal and OSS gate passed 74 tests and 39 subtests, and
the complete dual-frequency gate passed 506 tests and 296 subtests outside the
restricted system-monitoring sandbox. No production or sensitivity process
was started.

Eighteenth Step 9 implementation slice: register the pPAM observed, schedule,
block, and aggregate services before planner migration. The observed service
is the only service allowed to request or materialize physical OSS rows. It
publishes the continuous activation artifact, masked binary exposure, complete
operator-free observed arrays and documents, fixed-operator generation when
available, and one `PPAMObservedWorkspaceRecord`. It emits the single runtime
fact `ppam_permutation_ready`.

The schedule and fixed 250-replicate block services depend directly on the
observed record and realized final selection. They reconstruct the typed
`ActivationRequest` exclusively from durable record fields and published
artifacts. A permutation-ready record requires one complete schedule and all
canonical blocks. For either non-permutation-ready terminal state, the schedule
and block tasks terminate through the `ppam_permutation_ready` gate without
creating schedule or null records. Their ordinary gate skip is not a dependency
failure.

The aggregate always runs after the observed, schedule, and block tasks become
terminal. It requires the exact complete schedule and blocks only for a
permutation-ready parent; otherwise it requires both to be absent. It restores
the operator-free observed state, publishes the unchanged public
`ActivationArtifact` contract, and never reopens fixed-operator scratch in the
non-permutation path. Every scalar and collection restored from the observed
state document is type checked before numerical reconstruction; missing,
non-numeric, non-finite, or structurally inconsistent fields fail closed. A
nuisance-design failure publishes only its reason-coded state, emits a false
permutation-ready fact, and aggregates without schedule, block, or scratch
records.

The historical serial activation service remains callable only for old plans
and checkpoints. Newly compiled plans must use the four decomposed services and
must not select the serial compatibility service. Direct service tests cover
permutation-ready, observed-degenerate, and nuisance-design-failure paths before
any new plan emits the decomposed services.

Planner migration contract: each formal fiber endpoint replaces its serial
activation task with one observed-workspace task, one schedule task, fixed
250-replicate block tasks covering the configured OSS permutation count, and one
aggregate retaining the historical `activation_sensitivity` stage. The observed
task keeps the cache-first expensive-producer flag and receives the activation
resource class with one connectome-I/O token, one solver token, and an 8-GiB
memory charge. Schedule, block, and aggregate tasks receive the bounded
resampling resource class without solver or connectome-I/O tokens. Schedule and
block tasks require `ppam_permutation_ready`; the aggregate requires final and
formal completion but deliberately does not require that pPAM fact. Resume
invalidating one block must rerun only that block and the aggregate, while the
observed workspace, physical OSS cache, schedule, and unrelated blocks remain
reusable.

An independent OSS sensitivity extension selects the complete decomposed pPAM
subgraph rather than only its final aggregate. Its observed workspace, schedule,
all fixed blocks, and aggregate remain new extension tasks; only their completed
non-formal parents become immutable checkpoint roots. Formal dependencies and
the `formal_complete` gate are removed from this child plan exactly as for the
historical single-task OSS extension, while `final_model_realized` and
`ppam_permutation_ready` retain their meanings. Jitter-only extension closure is
unchanged, and a combined child plan contains the union of both independently
closed subgraphs without duplicating checkpoint roots.

Eighteenth-slice acceptance on 2026-07-19: the production registry contains all
four decomposed pPAM services while the planner remains unchanged. The observed
service is the only tested caller of physical OSS materialization and creates
one reusable fixed-operator generation. A spawned block reopens that generation
without rebuilding operators; ready aggregation restores one complete null,
while degenerate and nuisance-failure aggregation requires no schedule or block.
Malformed finite counts, nonnumeric performance fields, contradictory failure
state, changed identities, and incomplete artifacts fail closed. The focused
service, OSS, codec, and dependency gate passed 54 tests and 43 subtests. The
complete dual-frequency and visualization gate passed 526 tests and 299
subtests outside the restricted system-monitoring sandbox. No planner task,
production run, jitter, OSS-DBS, or combined extension was started.

Nineteenth Step 9 implementation slice: migrate the two formal fiber planner
paths and independent sensitivity compiler to the decomposed pPAM services.
Reference and add-on fiber endpoints now plan one cache-first observed task,
one schedule, the configured number of fixed blocks, and one aggregate. The
resource ledger assigns solver and connectome-I/O tokens only to observed
preparation. New plans contain no serial activation service, while the registry
retains both legacy handlers for old checkpoint compatibility.

An OSS child plan recursively selects the exact pPAM sensitivity ancestors of
each aggregate before deriving checkpoint roots. The observed parent run,
formal tasks, and unrelated sensitivities remain absent from the child. A
restored completed pPAM observed record is accepted only after final-model,
input-identity, and scratch validation; an invalid completed parent prevents
restoration of its descendants. An explicitly interrupted block does not
invalidate scientifically independent completed consumers.

Nineteenth-slice acceptance on 2026-07-19: the decomposed ready service result
matches the retained serial backend artifact kinds and content digests. False
readiness skips schedule and blocks with the documented reason while aggregate
still completes. Fixed-resource, planner-closure, gate, one-block resume,
independent OSS extension, combined jitter/OSS extension, and synthetic full-run
tests pass. The focused planner, executor, and service gate passed 59 tests and
86 subtests. The complete dual-frequency and visualization gate passed 534
tests and 308 subtests outside the restricted system-monitoring sandbox. No
production, jitter, OSS-DBS, or combined extension was started.

Ninth-slice acceptance on 2026-07-19: the public direct-voxel and
normative-fiber bootstrap functions now execute through schedule-bound partial
accumulators and the strict ordered aggregate. A 251-replicate fixture for both
families produces the 250-replicate block and one-replicate tail, accepts
reverse completion order, matches the retained single-interval calculation
within `1e-13` relative and absolute floating tolerance, and matches every
integer, support, selection, attrition, and evidence field exactly. Incomplete
coverage, changed schedule digest, and untyped block state fail closed. The
formal module passes 44 tests; the complete matrix passes 484 dual-frequency
tests, eight separately invoked goal guards, and 14 visualization tests. The
production DAG and formal artifact schemas remain unchanged, and no production
or sensitivity run was started.

Tenth Step 9 implementation slice: decompose only pPAM permutation numerics.
The observed pPAM fit builds and retains its complete historical output, while
one fixed permutation workspace owns the immutable binary exposure, nuisance
plan, fold operators, scoring workspace, and observed LOOCV metrics. The parent
creates the complete historical permutation schedule once. Each numerical
block consumes only its schedule interval, refits every permuted outcome with
lightweight score metadata disabled, and returns only block-local LOOCV
Spearman values bound to the full schedule digest.

The ordered aggregate uses the shared strict permutation-block validator and
plus-one two-sided calculation. A 251-replicate fixture must match a retained
single-interval calculation exactly, accept reverse completion order, and
reject incomplete or changed-digest blocks. Activation admissibility,
`p(A) > 0.5`, final-axis locking, reference-overlap masking, status,
publication, and expensive OSS authorization remain unchanged. Durable pPAM
records, shared operator scratch, and sensitivity-planner migration remain
outside this numerical slice.

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

#### Repository-owned performance acceptance contract

Step 10 requires two repository-owned entrypoints rather than an ad hoc
spreadsheet assembled from terminal logs:

- `run_task17_performance_probe.py` records descendant aggregate CPU time,
  task-tree RSS, swap, and source/scratch byte counters at one-second cadence
  outside the guarded mount; and
- `validate_task17_performance_acceptance.py` joins those measurements to
  scheduler windows and validates the complete declared benchmark matrix.

**Production-harness gap found on 2026-07-25.** The probe, byte-ledger
initializer and builder, counter builder, static audits, and terminal matrix
validator are implemented, but no repository-owned entrypoint currently
orchestrates the configured 72-row matrix. In particular, no command derives a
row's benchmark class, connectome, cache state, solver mode, worker count, run
root, and execution segment from one immutable benchmark request before
launching the runner and probe. A manually assembled matrix can therefore bind
valid source files while assigning an unproved row label. That is not accepted
production evidence.

Before the configured matrix runs, add one repository-owned benchmark harness
and a versioned benchmark-plan schema. The harness must enumerate the exact
validator key closure, create a distinct immutable run and evidence directory
for every executed row, initialize the live byte ledger before the runner,
attach the probe immediately after the runner PID becomes available, build the
terminal byte ledger and all counter sidecars, and write the matrix manifest
from those verified outputs. The benchmark class and cache/solver state must be
derived from the frozen row request and checked against the resolved run plan
and terminal segment rather than copied from an operator-authored result row.
It must support exact resume of terminal rows, reject a partial or differently
configured row directory, and never convert an execution failure into a
`not_run` row. Only the explicitly unauthorized real-cold OSS solver rows may
be `not_run`, using their repository-owned preflight evidence. Focused tests
must prove complete key enumeration, row-label/run-plan mismatch rejection,
probe attachment, terminal evidence construction, identical resume, and
fail-closed partial-row recovery before the 72-row production matrix is
launched.

The benchmark plan must not let an operator choose an arbitrary favorable
endpoint. It derives one deterministic maximum-structural-burden request for
each class from the accepted parent and resolved configuration, with stable
semantic ID order as the final tie break:

- direct voxel uses the complete scale-neutral physical-row closure on the
  configured canonical voxel axis;
- each fiber-connectome row uses that connectome's complete scale-neutral
  physical-row closure on its configured parent fiber axis;
- formal permutation and bootstrap use the terminal final endpoint with the
  largest subject-by-feature operator burden for the requested class;
- spatial jitter uses the terminal endpoint with the largest physical support
  multiplied by its fixed replicate count; and
- pPAM uses the terminal normative-fiber endpoint with the largest accepted
  `Omega_max` axis multiplied by its fixed permutation count.

The frozen request records every candidate burden and the selected endpoint or
physical closure. A later parent or configuration change must produce a
different benchmark-plan identity rather than silently reusing the prior
selection. Cold and warm rows, every worker count, and injected versus real
cache-hit modes reuse the same selected scientific request for their class.
This makes row comparisons workload-matched while preventing one scale,
endpoint, or cache state from receiving a smaller convenient workload.

The repository entrypoint is
`my_helper/fiber/pipelines/run_task17_performance_matrix.py`. It exposes
`prepare`, `run`, and read-only `validate` operations over one
`dual_frequency_task17_performance_benchmark_plan_v1` request and one
plan-SHA-bound benchmark root. `prepare` validates the accepted parent,
resolved profiles, configured connectome closure, requested worker closure,
and output-root separation, derives the maximum-burden requests above, and
commits one immutable resolved plan before any measured row starts. `run`
executes missing rows sequentially and records every attempt; it never overlaps
two measured rows. `validate` reopens the resolved plan, every row transaction,
the complete matrix manifest, and the terminal acceptance report without
writing or repairing them.

The operator-authored request has exactly these fields:

```text
schema_version
plan_id
accepted_parent_root
accepted_independent_oss_root
study_base
direct_voxel_model
normative_fiber_model
workflow_profile
conda_environment
working_directory
maximum_task_tree_rss_bytes
real_cold_solver_authorization
```

`real_cold_solver_authorization` is null unless a separate authorization
document is supplied. The request contains no benchmark class, connectome,
scale, endpoint, task ID, cache-state, solver-mode, worker-count, burden, or
row-command field. `prepare` derives the configured connectomes, workers 1, 3,
6, and 12, every selected scientific request, every measured task slice, all
row commands, and the exact 72-row closure. Both accepted roots must be
terminal, configuration-compatible, and SHA-bound to the same scientific
parent. The four source files must match the parent's recorded input JSON and
YAML identities. The benchmark root is a separate CLI argument and must be
disjoint from the parent, independent OSS, canonical publication, configured
output, configured run, and shared production-cache roots.

The resolved plan retains the validated Conda environment token and canonical
working-directory path in an `execution_environment` object. They remain bound
by the original request SHA and plan identity. The harness parent derives every
child command from this object; a caller cannot replace either value on `run`
or `resume`, and the child rejects a current working directory or Conda prefix
that differs before it opens a row RunStore.

Cold and warm cache state is a harness-owned input condition rather than a
label added after execution:

- every measured cold row receives a new empty row-local cache root and must
  publish the required producer closure during that row;
- for each scientific request, one unmeasured preparation transaction creates
  a canonical warm-cache seed, verifies its exact manifest and payload closure,
  and never contributes timing or utilization evidence;
- every measured warm row receives a verified direct copy of that same
  canonical seed, so workers 1, 3, 6, and 12 begin from byte-identical cache
  content;
- a warm row that publishes a new required producer fails its cache-state
  contract instead of being relabeled cold;
- a cold row that resolves a pre-existing required entry fails before the
  runner starts; and
- the real pPAM cache-hit seed comes only from the independently accepted OSS
  closure, copied into a row-local root and fully verified before measurement.

An ordinary warm seed is generated only in a newly created, proven-empty,
benchmark-local scientific cache by one unmeasured execution of the same
selected slice. Because that isolated cache has no pre-existing entries, the
seed transaction may enumerate its terminal `shared_exposure_v2` descendants,
open every entry through `ContentAddressedCache.resolve_identity`, and freeze
their kind, scientific identity, manifest SHA, and complete seed-closure SHA.
Enumeration of the configured production shared cache remains forbidden.
Measured warm rows copy only that frozen seed closure; an empty seed, an
unexpected entry, or any manifest difference fails before readiness.

`prepare` resolves the accepted OSS gate records from the terminal independent
OSS lineage and records their exact group IDs, decision IDs, final/Omega row
identities, cache-entry manifest SHAs, and one canonical closure SHA in the
resolved benchmark plan. Every referenced entry must resolve under the
configured shared scientific-cache root and pass its ordinary cache, row, and
decision validators. Directory enumeration, newest-entry selection, and
unreferenced compatible rows are forbidden. The resolved plan records the
shared-cache source path only as a read-only accepted input; measured rows never
open that path after their row-local seed has been copied and verified.
Injected rows derive deterministic ten-sample states from the accepted
probability rows by activating the first `probability * 10` samples for each
fiber. The accepted pass decision must prove identical probabilities on the
final-axis subset before that derivation is accepted. This reconstruction is
benchmark-only and cannot publish into the production shared cache.

The harness records the empty-cache proof or warm-seed manifest SHA, copied
entry closure, and first producer/cache-resolution events in each row
transaction. It keeps source inputs read-only and moves any replaced
unversioned row-local state into a benchmark-local quarantine instead of
overwriting it. An interrupted preparation or measured row remains partial and
resumable but cannot enter the matrix manifest.

Every row compiles the ordinary production DAG and then applies one
repository-owned measured-task slice. Required ancestors outside that slice are
copied from the accepted parent as immutable row-local checkpoint inputs and
fully verified before the probe starts. They are not timed. A selected task
cannot be restored from the accepted parent or the warm-cache seed. A selected
task must execute in the measured segment, while its scale, endpoint,
connectome, schedule, feature-axis, and replicate identities remain those of
the ordinary compiled DAG. The row fails if the terminal executed-task closure
differs from its prepared slice.

The measured slices are:

- direct voxel: every `prepare_reference_voxel_exposure` and
  `prepare_addon_voxel_exposure` task in the selected complete physical-row
  closure;
- one fiber connectome: every `prepare_reference_fiber_sidecar` and
  `prepare_addon_fiber_sidecars` task in the selected complete physical-row
  closure for that connectome;
- formal permutation: the selected endpoint's model-family-specific
  `prepare_exposure` task,
  `prepare_formal_operator_workspace`,
  `prepare_formal_permutation_schedule`, every
  `run_formal_permutation_block`, and `aggregate_formal_permutation` task;
- bootstrap: the selected endpoint's model-family-specific `prepare_exposure`
  task, `prepare_formal_operator_workspace`,
  `prepare_formal_bootstrap_schedule`, every `run_formal_bootstrap_block`, and
  `aggregate_formal_bootstrap` task;
- spatial jitter: the selected endpoint's model-family-specific
  `prepare_exposure` task, every `prepare_jitter_exposure_block` task for the
  selected physical group, plus the selected endpoint's matching jitter
  consumer; and
- pPAM: the selected fiber endpoint's `prepare_exposure` task,
  `establish_oss_axis_equivalence`,
  `prepare_ppam_observed_workspace`,
  `prepare_ppam_permutation_schedule`, every `run_ppam_permutation_block`, and
  `aggregate_ppam_activation` task.

Cold and warm describe only the row-local shared scientific cache presented to
the measured slice. They never permit selected task checkpoints to be copied
from a prior measured run. Consequently warm formal, bootstrap, jitter, and
pPAM rows still execute their complete statistical work and differ from their
cold counterparts only in required shared-producer resolution. The terminal
row transaction records the prepared task IDs, imported ancestor IDs and SHAs,
executed task IDs, restored task IDs, and terminal scientific payload closure.
Any selected task in the restored set or any imported ancestor in the executed
set fails the row.

The included `prepare_exposure` task is the only allowed producer of the
selected endpoint's required base shared-cache closure. It executes in both
cold and warm rows: cold must publish the missing closure once, while warm must
resolve the verified seed without publishing a producer. Statistical tasks
cannot read a production-cache path directly or receive a copied selected-task
result.

pPAM has three separate slice identities even though their task service closure
is the same. Injected cold and warm rows execute the OSS gate against a
repository-owned deterministic toolchain whose probability rows and expected
decision are derived from the accepted independent OSS closure. Real-cache-hit
warm rows execute the gate against a verified row-local copy of the accepted
OSS row and decision cache. Authorized real-cold rows execute the same gate
against an empty row-local cache and the production toolchain. The accepted OSS
gate task outcome is never copied as a checkpoint-only selected result.
Injected warm seeds are created by one unmeasured injected gate execution;
real-cache-hit warm seeds are direct verified copies. Any solver call in a
real-cache-hit row or any production solver call in an injected row fails the
row.

Each measured row uses one harness parent, one isolated runner child, and one
probe process. The child creates its immutable RunStore, imports and validates
checkpoint-only ancestors, writes `runner_ready.json`, and waits without
executing a selected task. The parent then initializes the live byte-ledger
index, starts `run_task17_performance_probe.py` against the runner child PID,
and atomically publishes `measurement_start.json`. Only then may the child
enter `execute_plan`. The child terminates after finalizing its run manifest;
the probe must publish its sole `runner_exit` row and terminate before the
parent builds terminal evidence. A missing readiness boundary, runner exit
before probe attachment, selected-task event before the measurement token,
or surviving runner/probe descendant fails the row and leaves it partial.

Injected pPAM rows retain the ordinary persistent spawn pool. A versioned
benchmark-only fixture descriptor may therefore be carried in
`SpawnWorkerSpec`; its default is null, and every ordinary main, sensitivity,
OSS, combined, or postprocess worker must retain that null default. The
descriptor contains only a row-local read-only fixture-cache root, its accepted
closure SHA, and the exact permitted OSS row identities. The harness copies and
fully verifies that fixture before runner readiness. Worker initialization may
replace only `oss_producer_toolchain` with the deterministic injected
toolchain when this descriptor is present. The row-local scientific cache
remains separate: injected cold starts empty, while injected warm starts from
the separately prepared unmeasured injected seed. Importing the harness module
from the worker, reading the production shared cache after readiness, accepting
an unbound row identity, or changing any non-OSS provider method fails the row.

`prepare` also generates one configured-data candidate-parity plan from the
accepted parent's complete prepared-exposure closure and executes it outside
every measured row. Its report is immutable, plan-SHA-bound, and shared by all
counter builders; it is never generated from a benchmark result. The report
must cover direct voxel plus all configured connectomes, contain every full and
fold candidate comparison, and have no candidate mismatch before any measured
row starts. Resume revalidates its plan, report SHA, and candidate-row closure
without recomputation. An absent or partial parity report blocks `run` rather
than allowing zero-filled counter fields.

The configured-data plan binds each realized final source to its complete
parent exposure, ordered parent feature IDs, exact selected valid-union IDs,
selected tau, and selected Coverage. It computes full and leave-one-out
candidate IDs directly from the parent exposure and requires every such ID to
occur in the selected valid-union artifact. It does not materialize or publish
a redundant `N` by `F_selected` exposure copy because those values are an exact
parent-column view and are not a second scientific authority. Voxel
`selected_feature_indices` are converted once to ordered canonical parent IDs
in a benchmark-local SHA-bound artifact; fiber sources use their recorded
`normative_fiber_valid_union_ids` artifact directly. The plan covers all 224
configured prepared endpoints: 112 realized direct-voxel or formal-connectome
endpoints and 112 sensitive-connectome fiber evaluations at their bound formal
source. Repeated physical parent payloads remain referenced by SHA rather than
copied.

The executor retains scheduler samples in memory at five-second cadence and
publishes them once, atomically, when the execution segment closes. Each sample
contains UTC start and finish times, ready and running task counts,
`runnable_cpu_slots`, reserved CPU, memory, connectome-reader and solver slots,
and the active admission reasons. This adds no hot-loop path lookup, hash,
lock, or per-sample filesystem write. The terminal segment records the
scheduler-window payload SHA and row count.

The benchmark manifest uses schema
`dual_frequency_task17_performance_matrix_v1`. Its rows are keyed by:

```text
benchmark_class
connectome_id
cache_state
solver_mode
workers
```

The prepared-plan SHA plus those five key fields derive one stable
`row_<digest>` identity. Each row owns:

```text
rows/row_<digest>/
  row_contract.json
  attempts/
    attempt_0001/
      checkpoint_closure.json
      row_cache_state.json
      attempt_plan.json
      runner_ready.json
      measurement_start.json
      runner.stdout.log
      runner.stderr.log
      probe.csv
      probe.stdout.log
      probe.stderr.log
      attempt_result.json
  row_result.json
```

`row_contract.json` is immutable and binds the complete resolved-plan SHA,
slice ID, cache-seed identity, worker count, solver mode, resource ceiling, and
expected terminal-evidence paths. A terminal `row_result.json` is reused only
after its contract SHA and every evidence SHA revalidate. A partial row keeps
all prior attempts and creates the next monotonic attempt directory. A
differently configured existing row fails before execution; it is never
renamed or relabeled. Only a real cold solver row without authorization
publishes a terminal `not_run` result, and that result binds the immutable
authorization preflight. Runner, probe, evidence-builder, cache-state, or
scientific failures remain failed or partial attempts and never become
`not_run`.

Within a new attempt, the harness first validates and records the imported
checkpoint closure, then prepares and records the row cache state, and commits
`attempt_plan.json` last. That final marker binds the row contract SHA, attempt
number, executable slice-plan hash, selected and imported task IDs, checkpoint
closure SHA, and cache-state SHA. A runner child accepts only that marker and
revalidates both referenced documents before creating its RunStore.

`prepare` writes the resolved plan first, then all 72 immutable row contracts,
and commits `benchmark_root.json` last with the complete row-ID and contract-SHA
closure. The marker is absent while any contract is missing. Read-only
`validate` recomputes the plan, checks the marker, and reopens every contract;
it never creates a missing row or repairs a changed file.

The required classes are direct voxel, each configured fiber connectome,
formal permutation, bootstrap, spatial jitter, and pPAM. Workers are exactly
1, 3, 6, and 12. Every non-pPAM class has cold and warm rows. pPAM has injected
solver cold and warm rows plus real cache-hit warm rows. A real cold solver row
is accepted only with a separate authorization document; otherwise it is an
explicit `not_run` row and cannot support a default or utilization claim.
Duplicate, missing, silently skipped, or extra keys fail validation.

Every executed row binds one immutable run root, one finished execution
segment, one performance-probe CSV plus its SHA-256, one scheduler-window
payload, one numerical-identity digest, the exact resolved configuration digest, and one
run-published counter sidecar plus its SHA. Counter values cannot be entered
directly in the matrix manifest. The sidecar reports source and scratch bytes,
cache verification counts, physical producer counts, pool generations, nested
executors, metadata work, copies, bytes, reader and solver peaks, queue and
admission waits, cancellation, timeout and retry counts. The validator derives
wall and aggregate CPU time, effective cores, peak RSS, and swap delta from the
probe; requires source and scratch bytes to agree between the probe and terminal
counter sidecar; and rejects a row when any required counter is absent. Zero is
data, but an omitted value is not.

`io_classification` is exactly `compute_bound` or `storage_limited`. The
prespecified safe default remains three workers without a performance
promotion claim. Selecting any other default requires at least one matched
candidate-versus-three comparison in which both rows are `compute_bound`, and
the candidate must have shorter wall time in every such eligible comparison.
The acceptance document records the matched row keys and both wall times rather
than retaining only the selected integer.

For the 12-worker rows, the validator aligns probe and scheduler samples into
five-second windows. A window is eligible only when
`runnable_cpu_slots > 5`, every non-worker admission-reason count is below 1,
and the window is not storage-limited. Effective cores are the descendant
aggregate CPU-time increase divided by elapsed wall time. The row passes the
compute-utilization gate only when the fraction of eligible windows with
`effective_cores > 6` is `> 0.80`. An executed 12-worker compute-bound row
without eligible windows fails rather than becoming `not_run`.

Performance acceptance independently validates the complete scheduler sidecar;
it does not assume that a separate resource-acceptance invocation already
accepted the benchmark. The scheduler document and every row must have the
exact repository-owned field closure. Window timestamps are UTC, positive, and
contiguous. Ready, running, runnable, CPU, managed-memory, reserved-memory,
connectome-I/O, solver, admission-reason, and storage-limited values are typed
and bounded by the selected segment's worker and resource declarations.
`runnable_cpu_slots` is the bounded sum of ready and running tasks, and
`storage_limited` is true exactly when the connectome-I/O admission count is
positive. A valid SHA over structurally incomplete or resource-inconsistent
scheduler rows must fail the performance matrix before utilization is
calculated.

The validator writes one atomic
`dual_frequency_task17_performance_acceptance_v1` document containing the
input manifest SHA, every source-evidence SHA including the exact probe CSV
SHA, per-row verdicts, aggregate
matrix closure, utilization-window results, and the chosen-default decision.
Running the validator twice over unchanged evidence must produce the same
scientific and acceptance payload except for no timestamp field, because the
acceptance document contains no wall-clock generation timestamp.

Every probe row must have a timezone-aware strictly increasing UTC timestamp
and strictly increasing monotonic elapsed time. Aggregate CPU time,
`source_bytes`, and `scratch_bytes` must never decrease. Every row before the
last is a `sample` with at least one live process; the last row is the sole
`runner_exit` row with zero live processes and zero task-tree RSS. Unknown
event labels, an early exit marker, a live-process sample after exit, or a
counter reset fails the matrix row. Scheduler-window interpolation is
therefore performed only over an ordered, continuous probe envelope.
Each executed matrix row names a safe single-component `segment_*` identity.
The segment file and the segment-declared scheduler-window relative path must
both resolve inside that row's run root; absolute scheduler paths and
path-traversal segment identities are rejected before any source SHA is
accepted.

##### Counter provenance and aggregation

The terminal counter sidecar is not a bag of caller-supplied integers. Every
field carries one source class and is aggregated only from the following
repository-owned evidence:

| Counter | Authoritative event or evidence |
|---|---|
| `candidate_false_negative_count` | configured-data brute-force parity report |
| `physical_producer_count_min`, `physical_producer_count_max` | new physical cache publication events keyed by scientific cache identity |
| `hot_loop_metadata_work_count` | path/hash/lock instrumentation events emitted while a provider range-loop guard is active |
| `cache_full_verification_count_min`, `cache_full_verification_count_max` | actual payload-SHA verification events keyed by process identity and cache identity |
| `cache_repeat_verification_count_max` | full payload-SHA verification after the first verified event for the same process/cache identity |
| `endpoint_payload_copy_count` | prepared-exposure publication event whose source and destination differ only by endpoint naming |
| `nested_executor_creation_count` | executor-construction audit outside the single parent scheduler |
| `retained_null_n_by_f_output_count` | artifact-index audit for a retained null payload with both permutation and feature axes |
| `left_transform_resolve_count` | canonical-left resolution event, separated from a real transform producer event |
| `nifti_open_count`, `sampler_build_count`, `sampler_rebuild_count`, `sampler_eviction_count` | process-local sampler lifecycle events keyed by unchanged path signature |
| `connectome_row4_audit_pass_count` | configured connectome row-4 parity audit |
| `direct_copy_verification_count` | portable identity-only cache resolution followed by full payload verification |
| `filtered_connectome_build_count` | new filtered-connectome publication event keyed by source connectome and final feature axis |
| `memmap_flush_count` | explicit managed-memmap flush event |
| `artifact_index_snapshot_count` | parent-owned artifact-index atomic publication event |
| `payload_read_bytes`, `payload_write_bytes`, `payload_hash_bytes` | byte counts at cache/artifact read, write, and SHA loops; one operation can contribute to more than one category |
| `source_bytes`, `scratch_bytes` | benchmark-scoped source-read and scratch-write byte ledger |
| `cancellation_count`, `timeout_count`, `retry_count` | terminal execution-segment scheduler counters |

Worker events are process-local in memory. At each task boundary the worker
writes one immutable delta fragment below that task attempt. The parent alone
validates and aggregates fragments after workers stop, joins the configured
parity and artifact audits, derives the terminal scheduler counters, and
atomically publishes
`dual_frequency_performance_counters_v1` beside the execution segment.
Fragments include process creation identity, task ID, event keys, and counts;
an unknown counter, negative delta, duplicate fragment identity, missing task
fragment, or source-evidence SHA mismatch fails sidecar publication.

Minima and maxima are calculated over the exact identity closure declared by
the benchmark class, not over identities that happened to emit an event.
Consequently a missing producer or verification contributes zero and fails the
required gate instead of disappearing from the denominator. Cold and warm
rows use the same identity closure. Cold rows require one physical producer
per required identity; warm rows require no new producer. Full verification is
keyed by process and cache identity and must occur once; structural manifest
reads do not count as full payload verification.

Two non-exported support events define those denominators without accepting a
caller-entered integer. `physical_cache_use` is emitted after every successful
shared voxel, fiber, or physical-jitter cache resolution and defines the
physical scientific-identity closure. `cache_resolve` is emitted after every
successful cache entry resolution and, together with the fragment process
identity, defines the process/cache verification closure. The sidecar derives
producer minima and maxima over the first closure and full-verification minima,
maxima, and repeats over the second closure. A support event without its
required producer or verification evidence contributes zero; a producer or
verification identity outside the support closure fails publication.

The sidecar publisher consumes one
`dual_frequency_performance_counter_inputs_v1` document. It binds the run and
segment IDs plus the SHA-256 of the terminal segment, raw event report,
benchmark byte ledger, configured-data candidate-parity report, and
artifact/static audit. It also declares the benchmark class and cold or warm
cache state, but it contains no counter values. The publisher verifies every
bound source, rejects incomplete worker fragments and nonterminal segments,
derives all 28 counters, and writes one deterministic
`performance_counters_<segment_id>.json` document. The second identical
invocation must byte-match the first. The event report is not selected by
basename: its segment-declared relative path must resolve inside the run root
and must be the exact SHA-bound document supplied to the builder.

The benchmark byte ledger has one repository-owned live index and one
terminal document. The live
`dual_frequency_performance_byte_ledger_index_v1` document binds exactly one
run root. On every probe sample, the probe discovers only atomically published
`work/task_*/attempt-*/performance_counter_fragment.json` files. The presence
of such a fragment is the terminal-attempt boundary; incomplete attempts have
no visible fragment. The probe validates the task/attempt path, fragment
schema, task and process identities, and scalar closure, then sums its
`source_bytes` and `scratch_bytes` deltas. This deliberately includes bytes
spent by a terminal failed or retried attempt. Callers do not enter either
byte total. A duplicate, malformed, path-mismatched, or counter-incomplete
fragment fails the sample instead of contributing zero. The live index is
static during the run; the probe CSV records the monotonically increasing
derived totals. A repository-owned initializer creates this index from one
validated run root and refuses source/scratch values or an output path inside
that run. The benchmark harness must use the initializer rather than authoring
the index JSON directly.

The one-second probe must not reread and rehash the full fragment population
on every sample. Its process-local reader validates the static index once,
discovers atomically visible fragment paths, and reads each newly observed
immutable fragment once. Intermediate samples reuse the accumulated totals.
On `runner_exit`, it performs one complete independent rescan and validation
and requires the terminal totals and fragment closure to match the incremental
state. This preserves fail-closed terminal evidence without turning the probe
itself into a benchmark-scale random-I/O workload.

After the run and selected execution segment are terminal, the repository
ledger builder repeats the same aggregation over the event report's exact
fragment closure and writes
`dual_frequency_performance_byte_ledger_v1`. The terminal ledger binds the
run ID, segment ID, terminal segment SHA, event-report SHA, every fragment path
and SHA, and the final source/scratch totals. The final probe sample must match
this ledger byte for byte at the counter level before performance acceptance.
The counter-sidecar builder independently reopens every event-report and
ledger fragment. Their task, process, exact run-relative path, SHA, and byte
deltas must form the same closure; an external same-byte copy or a
caller-authored summary cannot substitute for a run-owned attempt fragment.
Because the live ledger observes worker attempt fragments, parent-process
`source_bytes` and `scratch_bytes` must both remain below 1. Parent scheduling,
state, and index publication events remain in the parent event section, but
moving scientific source or scratch I/O into the parent requires a versioned
live-ledger extension before such a run can be accepted.
`source_bytes` counts bytes read from original configured scientific inputs;
cache payload reads and run-owned artifacts remain under
`payload_read_bytes`. `scratch_bytes` counts bytes newly written to temporary
matrices, cache staging generations, and run-scoped artifact staging files;
an atomic rename contributes no additional bytes. Flush calls are tracked
separately and do not multiply the logical scratch allocation. These
categories may overlap the payload read/write/hash counters because they
answer different provenance questions, but a single source read or scratch
write contributes only once to its own category.

Source accounting is defined at repository-controlled read boundaries rather
than inferred from device telemetry. A full configured-input SHA pass
contributes the file size once; loading an original NIfTI contributes the
compressed file size once for that load; and each HDF5 connectome chunk
contributes the logical bytes of the point, offset, and fiber-ID arrays
returned to the workflow. Cache, parent-run, and current-run roots are excluded
from `source_bytes`. This makes the ledger deterministic across filesystems
without pretending that filesystem readahead, compression, or operating-system
page-cache traffic is portable. Scratch accounting records each cache payload
and cache manifest staged, each run-scoped artifact payload and metadata
sidecar staged, and each temporary memmap's logical file allocation once.

`run_task17_artifact_static_audit.py` produces the required
`dual_frequency_artifact_static_audit_v1` source. It binds the terminal event
report and artifact index, restricts task inspection to the event report's
fragment task closure, and checks every retained artifact against the indexed
publication. The segment, event report, artifact index, and task-state paths
must resolve inside the declared run root. A terminal completed run whose
event-report fragment closure contains any failed or noncompleted task fails
the audit; failed tasks cannot be skipped to obtain an apparently clean
artifact result. It reports retained null artifacts only when one artifact has
both a permutation axis and a voxel/fiber/feature axis. Its AST audit scans the
scientific `runtime`, `backends`, and `cache` packages for process- or
thread-pool construction; the single parent scheduler in `workflow/executor.py`
and the publication-only file-copy pool are outside that nested-scientific
scope. The audit records every scanned source SHA and every detected call site,
so a source change requires a new audit rather than reusing a zero count.

`run_task17_candidate_parity.py` consumes a
`dual_frequency_candidate_parity_plan_v1` document whose configured rows bind
the model family, selected tau and Coverage, parent exposure and feature-ID
artifacts, and reduced/optimized exposure and feature-ID artifacts by SHA-256,
dtype, shape, and axis. Direct-voxel rows bind the same full parent and
optimized axis; normative-fiber rows bind the complete connectome exposure as
the parent and `Omega_max` as the optimized axis. For the full sample and every
held-out subject, the tool computes a scalar brute-force candidate mask from
the parent, computes the production vectorized mask on the optimized axis, and
reports both optimized-mask mismatches and parent candidates missing from the
optimized axis. The deterministic
`dual_frequency_candidate_parity_v1` report binds the plan SHA and every
artifact SHA. The counter sidecar rejects nonzero full or fold mask mismatches
and uses the summed missing-parent count as
`candidate_false_negative_count`.

Counters that require configured parity or artifact-index audits remain
unavailable until those source documents are present. The sidecar publisher
must fail; it cannot synthesize zero, infer success from missing events, or
accept a matrix-entered fallback.

#### Repository-owned isolated fault acceptance contract

`run_task17_fault_acceptance.py` owns the Step 10 corruption, fail-once,
selective-resume, and deletion-rebuild sequence. It refuses to run unless the
caller-selected acceptance root:

1. lies outside the accepted parent run and canonical publication roots;
2. contains a marker created by the tool for the same plan SHA;
3. contains only harness-created copied runs, copied cache entries,
   quarantined originals, command logs, and evidence; and
4. names a distinct rebuilt main-run ID before any parent artifact is made
   unavailable inside the isolated copy.

The accepted parent run, canonical publication, and shared production cache
are read-only inputs. The harness never corrupts, renames, deletes, or
overwrites them. It copies only the declared artifact closure into the isolated
root, verifies every copy before fault injection, and moves each replaced or
withheld isolated file into a per-case quarantine directory. No original is
permanently deleted.

The fault plan uses schema `dual_frequency_task17_fault_plan_v1`. It declares
the accepted-parent manifest SHA, isolated cache root, copied artifact closure,
payload, shard and axis corruption cases, one deterministic fail-once task,
the descendants expected to be dependency-skipped before recovery, the
required-parent artifact to withhold, the rebuilt main-run ID, the extension
commands, and the one-shot comparison roots. Commands are argument arrays,
not shell strings. Their working directory and Conda environment are explicit,
stdout and stderr are retained, and a command cannot escape the marked
acceptance root through any output or run ID.

The terminal
`dual_frequency_task17_fault_acceptance_v1` report must prove:

- each corruption is rejected before scientific materialization or extension
  startup;
- the fail-once task fails exactly once, its descendants are skipped for that
  failed attempt, resume completes the task, and those descendants then run;
- scientific artifacts completed before the injected failure retain their
  SHA and byte size;
- withholding a required artifact from the isolated parent copy causes plain
  extension startup to fail closed;
- rebuild mode creates the declared distinct main lineage before sensitivity,
  while the accepted parent and canonical publication remain byte-identical;
- copied-cache replay works with expensive authorization disabled; and
- rebuilt and one-shot extension outputs match under the frozen numerical
  tolerances.

The harness is resumable by case. A completed case is reused only after its
input copy hashes, command arguments, expected failure class, output closure,
and quarantine inventory revalidate. Partial or failed cases are retained and
never trigger cleanup of the acceptance root.
The marker has an exact field closure and must retain the complete copied-input
closure derived from the current plan; deleting a marker row cannot suppress
input revalidation. Every terminal case stores a deterministic hash of its
current case object. Reuse requires that hash, the exact terminal result schema,
and the immutable attempt inventory to match. It then reruns the case-specific
read-only postconditions: corruption targets equal their declared isolated
copies, fail-once task and descendants remain completed while protected files
retain their hashes, the rebuilt lineage and one-shot comparisons still pass,
and copied-cache outputs retain their expected hashes. A `status: validated`
string or unchanged log inventory alone is not sufficient reuse evidence.
The three corruption IDs plus fail-once, rebuild, and cache-replay IDs are
nonempty path-safe tokens and form one unique six-case closure. A separator,
dot traversal token, duplicate ID, or case path outside the marked acceptance
root fails while the plan is loaded, before any case directory is created.
The `validate` operation is read-only. It evaluates marker, case, attempt,
command, output, comparison, and read-only-root evidence without publishing or
repairing any file, then compares the recomputed report with the existing
`fault_acceptance.json`. A missing or changed report fails; validation must not
call a path that rewrites the report before comparison.

The production invocation is frozen to one plan document and one disjoint
acceptance root. Generate the plan only after canonical OSS-v2 and combined-v2
are terminal, because its read-only closure must bind their actual manifests,
indexes, payload hashes, accepted parent, and copied scientific-cache entries.
The plan path is
`/Volumes/VAL/STNSNr/summary/spot/acceptance/task17-fault-plan-v1.json`;
the harness root is
`/Volumes/VAL/STNSNr/summary/spot/acceptance/task17-fault-v1`.
The plan remains outside the marked harness root so initialization can prove
that the root is absent or contains only a matching resumable transaction.
After an independent review of the generated plan and its six-case closure,
run:

```bash
env -u PYTHONPATH /opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/fiber/pipelines/run_task17_fault_acceptance.py \
  --plan /Volumes/VAL/STNSNr/summary/spot/acceptance/task17-fault-plan-v1.json \
  --acceptance-root /Volumes/VAL/STNSNr/summary/spot/acceptance/task17-fault-v1 \
  init

env -u PYTHONPATH /opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/fiber/pipelines/run_task17_fault_acceptance.py \
  --plan /Volumes/VAL/STNSNr/summary/spot/acceptance/task17-fault-plan-v1.json \
  --acceptance-root /Volumes/VAL/STNSNr/summary/spot/acceptance/task17-fault-v1 \
  run

env -u PYTHONPATH /opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/fiber/pipelines/run_task17_fault_acceptance.py \
  --plan /Volumes/VAL/STNSNr/summary/spot/acceptance/task17-fault-plan-v1.json \
  --acceptance-root /Volumes/VAL/STNSNr/summary/spot/acceptance/task17-fault-v1 \
  validate
```

Repeat `run` once after terminal success and then repeat `validate`. The second
run must reuse all six completed cases only after revalidating their immutable
inputs, quarantines, commands, outputs, comparisons, and read-only roots.
Neither invocation may alter the accepted parent, canonical publications, or
shared production cache.

Performance instrumentation implementation checkpoint on 2026-07-24:

- the executor retains five-second scheduler windows in memory and publishes
  one SHA-bound sidecar only when the segment closes;
- the external performance probe preserves cumulative CPU time for descendant
  processes after they exit and distinguishes PID reuse by process creation
  time;
- the matrix validator requires the exact 72-row closure for three configured
  connectomes, workers 1, 3, 6, and 12, cold and warm non-pPAM rows, injected
  pPAM rows, real warm cache-hit rows, and explicit unauthorized real-cold
  rows;
- resolved worker configuration, segment, probe, scheduler-window,
  numerical-identity, RSS, swap, and 12-worker utilization gates are checked
  from their source evidence;
- counter values are accepted only from a SHA-bound terminal sidecar, never
  directly from a matrix row; and
- 44 focused tests and the complete 613-test discovery pass.

This checkpoint closes the missing probe, scheduler-trace, and validator
implementation. It does not close Step 10 because the configured benchmark
matrix has not run. The isolated fault harness was the remaining implementation
gap at that checkpoint and is closed by the subsequent checkpoint below.

Probe-identity closure checkpoint on 2026-07-24:

- every executed matrix row now declares `probe_sha256`;
- the validator verifies that digest before parsing any probe measurement and
  retains it in the per-row acceptance evidence; and
- I/O classification is closed to the declared two-value vocabulary, while a
  non-default worker promotion requires and records matched compute-bound
  comparisons against three workers; and
- the 35-test performance-byte, ledger, probe, counter, matrix, and artifact
  audit suite passes, including probe-substitution, classification, and
  non-default-selection rejection tests.

This closes the remaining mutable-probe evidence gap. It does not substitute
for running the configured 72-row production benchmark matrix.

Isolated fault-harness implementation checkpoint on 2026-07-24:

- `run_task17_fault_acceptance.py` provides separate `init`, `run`, and
  validation-only operations over a plan-SHA-bound acceptance root;
- the marker requires complete SHA enumeration of the accepted-parent and
  canonical-publication file trees, while production cache inputs are copied
  only through an explicit verified closure;
- subprocess arguments can address only the isolated root or the declared
  working directory; no test command receives the accepted parent,
  publication, or shared production cache as a writable path;
- payload, shard, and axis cases move the isolated original into quarantine,
  publish deterministic corruption, require pre-consumption rejection, and
  restore the original through rename;
- fail-once recovery proves failed and dependency-skipped states before
  resume, completed states after resume, and unchanged prior scientific
  artifacts;
- missing-parent extension startup must fail before rebuild, rebuild must
  create a distinct completed main lineage, copied-cache replay must omit the
  expensive-producer authorization argument, and rebuilt outputs must match
  declared one-shot outputs exactly or under declared NPY tolerances; and
- completed cases are reused only after their input marker and complete
  attempt/log/quarantine inventory revalidate.

The five fault-harness tests, 49 combined executor/performance/fault tests, and
complete 618-test discovery pass. This closes the missing harness
implementation, not the production-scale fault acceptance sequence.

Terminal fault-reuse closure was completed later on 2026-07-24. The marker now
has an exact plan-derived copied-input closure; all six case IDs are path-safe
and unique; relative traversal arguments fail; and every terminal result binds
its exact case contract, command/log evidence, attempt inventory, and
case-specific current postconditions. Fail-once retains immutable failed and
dependency-skipped task snapshots before resume. Rebuild and copied-cache
outputs are revalidated on every reuse. Validation recomputes the complete
report without writing and rejects a changed report byte-for-byte. Fifteen
focused harness tests cover the complete replay plus marker deletion, absolute
and relative path escape, unsafe and duplicate case IDs, attempt tampering,
case-contract tampering, fail-once task drift and snapshot-identity swapping,
rebuilt-output drift,
copied-cache-output drift, and read-only report validation. Complete
dual-frequency discovery passes 690 tests with warnings treated as errors.
The production-scale fault plan and sequence remain pending.

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

Historical downstream acceptance evidence on 2026-07-19: the production request
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
That batch was subsequently deleted and cannot satisfy current formal output
acceptance. The configured 2026-07-22 output root remains absent. Its durable
112-endpoint replay, identical resume, independent validation, and sampled
visual review remain open until the active OSS and combined publication
sequence completes.

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

The executable cleanup boundary is deliberately narrower than the shared
scientific cache. Run-owned cache means only descriptor-enumerated formal and
pPAM operator generations plus the run's own `runtime_work` directory. It never
includes shared `cache_root` entries, task artifacts, task-state JSON, reporting
documents, portable sensitivity bases, or canonical output. The canonical main
publisher is the sole trigger: before touching scratch it verifies the completed
run manifest, absence of failed or nonterminal task outcomes, both completed
model manifests, both artifact indexes, and completed coverage of every
configured scale. It validates all scratch descriptors in a first pass, removes
them only in a second pass, and writes one atomic idempotence marker after full
success. A false policy returns without inspection or mutation beyond the
already completed publication.

Cleanup acceptance on 2026-07-19: false policy returns before reading missing
publication state and preserves all scratch. True policy rejects failed run
state and untracked scratch before deletion. A complete synthetic run with real
formal operator generations completes canonical publication, removes only those
generations and run-owned `runtime_work`, preserves task NPY artifacts and a
sentinel in shared `cache_root`, writes the atomic marker, and republishes
successfully through the idempotent marker path. The cleanup, publication, and
configuration gate passed 34 tests and 10 subtests; the complete dual-frequency
and visualization gate passed 539 tests and 308 subtests outside the restricted
system-monitoring sandbox. The production policy remains false, so no production
cache was deleted.

A current cleanup-boundary replay on 2026-07-22 passed all four focused tests.
The false policy returned before publication inspection and preserved
`runtime_work`; an incomplete run failed before any scratch mutation; a fully
completed publication removed only descriptor-declared run-owned scratch while
preserving task artifacts and shared cache, then reused the atomic marker on an
identical replay; and unexpected untracked scratch failed preflight before any
deletion. This replay directly verifies that failed or partial execution retains
the checkpoint, shared cache, and runtime state required for resume. The current
formal profile still sets `delete_run_cache_on_success` to false.

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

### Corrected v8 production sensitivity execution contract

Production sensitivity execution on 2026-07-19 uses only the completed parent
`task17-main-v8-tau-grid-formal-20260717`. Its completed manifest SHA-256 is
`25d48876aa955b2df514102523dcee7deb9bf8a8a8bd0c8151d141c1b3809347`, its
study SHA-256 is
`3aa0d58a7373e186896b2fbfb5c0342d8425046bf9a5b07517b416d6a7def925`, and
its scientific configuration SHA-256 is
`6d23bc0e9f30e697806d0847f238c1c8b09170673dc1ff0c29253808a5c401d5`.
The current resolved configuration reproduces that scientific identity. Its
different complete configuration SHA-256 reflects only the retained-cache
execution policy and other nonscientific runtime state.

The parent checkpoint contains 112 endpoint bases and 1512 completed seed task
states. The preflight validates the parent manifest, every selected final
artifact, declared shared-cache entry, scientific identity, endpoint identity,
and required direct seed before creating a child. Historical jitter lineages
from v1 through v6 used superseded scientific boundaries and remain immutable
evidence only. They must not seed, resume, or publish the corrected result.

The active child lineages are:

- `task17-jitter-v8-support-preserving-formal-20260719` for independent
  jitter;
- `task17-oss-v1-inclusive-formal-20260719` for independent OSS and pPAM;
- `task17-combined-v1-inclusive-formal-20260719` for the joint cache-reuse and
  closure check.

The initial combined launch occurs only after the independent OSS child is
terminal, both equivalence groups pass, all downstream pPAM tasks complete, and
its reporting and artifact index validate. Its acceptance command is:

```bash
conda run --no-capture-output -n leaddbs \
  python my_helper/fiber/pipelines/run_dual_frequency_models.py sensitivity \
  --base-run /Volumes/VAL/STNSNr/summary/spot/.runs/stnsnr_frequency_addon/task17-main-v8-tau-grid-formal-20260717 \
  --analyses jitter,oss \
  --run-id task17-combined-v1-inclusive-formal-20260719 \
  --workers 14
```

The initial command deliberately omits `--allow-expensive-producers`. Every
physical jitter block, OSS row, and equivalence decision must reuse an already
verified independent-child cache entry. An unexpected cache miss therefore
fails closed instead of silently launching another solver or physical jitter
producer. If an identity-matching combined root already exists after an
interruption, audit its parent, scientific configuration, requested analyses,
and terminal task documents before adding `--resume`; never create a replacement
lineage to bypass a partial reusable root.

A read-only prelaunch audit on 2026-07-22 confirmed that the frozen combined
run root does not exist and that neither domain contains a combined-v2
publication. The first combined invocation must therefore use the command
above without `--resume`; only a later interruption may activate exact-root
resume after its three input-identity gates pass. VAL reported approximately
821 GiB available during this audit. This capacity check does not waive the
independent OSS terminal gate or authorize any expensive producer.

A 2026-07-21 read-only code audit found one prerequisite for that acceptance
command. The executor correctly allows `cache_first_expensive` tasks to enter
without blanket expensive-producer authorization, but
`establish_oss_axis_equivalence` currently rejects the request before checking
whether every immutable row decision is already present. After the independent
OSS process exits and before combined launch, move this authorization check to
the first genuinely missing or invalid row. A fully cached gate with expensive
authorization disabled must validate and reuse every decision without invoking
the toolchain. A single missing decision with authorization disabled must fail
before any solver call. Authorization enabled must produce only the missing
row. Focused tests must prove all three paths before the no-authorization
combined command above is permitted.

The same audit found that physical jitter block tasks are not currently marked
`expensive_producer` and do not receive a reuse-only authorization boundary.
`prepare_jitter_exposure_block` resolves the semantic cache correctly, but an
absent entry proceeds directly to physical production. Before combined launch,
compile jitter blocks as `cache_first_expensive` tasks and require expensive
authorization only inside the cache-miss branch, before taking a producer lease
or building any physical array. A complete cache with authorization disabled
must reuse every block. A single missing block with authorization disabled must
fail before physical provider invocation. Authorization enabled must produce
only the missing block. Existing completed v8 block identities and payloads
remain reusable because the execution-policy flag does not enter the task or
scientific cache identity. Focused planner, executor, provider, and combined-
plan tests must close this boundary before the combined command is launched.

The implementation map is intentionally narrow. In
`runtime/oss_axis_equivalence.py`, retain descriptor validation, immutable
`Omega_max` loading, runtime-request construction, physical-row pairing, and
`_load_decision` ahead of authorization. Remove the group-wide early rejection
and check `allow_expensive_producers` only inside `if decision is None`, before
the first `produce_with_evidence` call. This preserves validation of cached
decisions while guaranteeing that an unauthorized miss cannot reach MATLAB or
OSS-DBS. The focused test must first populate all decisions, repeat with
authorization disabled and a toolchain that raises if called, then remove one
decision entry and prove failure with zero toolchain calls.

In `application/sensitivity.py`, each generated
`prepare_jitter_exposure_block` `TaskSpec` receives both
`expensive_producer=True` and `cache_first_expensive=True`. In
`runtime/jitter_blocks.py`, retain all deterministic key construction and the
initial `cache.resolve(key)` ahead of authorization; if that resolve is empty,
reject an unauthorized request before `producer_lease` and before either
`build_jitter_physical_block` provider method. The focused test must populate a
block, repeat with authorization disabled and a provider that raises if called,
then remove the entry and prove failure with zero provider calls. A separate
planner assertion must prove both task-policy flags without changing the task
ID or cache digest relative to the completed v8 identity contract.

Local implementation evidence on 2026-07-22 closes this prerequisite.
`runtime/oss_axis_equivalence.py` now performs authorization only after a
decision lookup proves a real miss. The focused fixture proves fully cached
reuse with authorization disabled and no new toolchain call, an unauthorized
single-decision miss with zero toolchain calls, and authorized repair of only
that missing decision. A cached decision is reusable only while both its final
and `Omega_max` standard row entries still resolve and pass their complete
three-file validation. The focused fixture must also remove one referenced row
while retaining the decision and prove fail-closed behavior with zero new
toolchain calls. A separate fixture must corrupt one referenced row payload
while retaining its directory, manifest, and decision and prove the same
pre-toolchain failure. A complete shared-cache tree copied byte-for-byte to a
new root must also restore the entire gate with authorization disabled and zero
toolchain calls, proving that no path, inode, machine, or cache-instance
identity entered the closure. `application/sensitivity.py` now enables both expensive
and cache-first policy flags on every physical jitter-block task, while the
planner fixture proves that toggling those execution-policy fields leaves the
task identity unchanged. `runtime/jitter_blocks.py` now rejects an
unauthorized miss before the producer lease and physical provider call; the
provider fixture proves authorized initial production, copied-cache reuse with
authorization disabled, corruption rejection, and an unauthorized miss with
zero provider calls. The complete dual-frequency suite passed 538 tests plus
310 subtests in the `leaddbs` environment. No live combined execution was
attempted because VAL was offline; the no-authorization combined command and
real cache-reuse evidence remain the next external acceptance gate.

The strengthened OSS closure suite passed six tests on 2026-07-22. In
addition to dynamic decision-count, reuse, blocked-miss, and mismatch paths, it
now retains a cached decision while deleting one referenced standard row and
proves that the gate fails before any new toolchain call. This closes the
decision-to-two-row missing-entry fixture. A separate fresh cache-process
fixture corrupts a referenced `probabilities.npy` while leaving its decision
and manifest intact; first-process verified-set reuse remains unchanged, while
the new process rehashes the entry, rejects the corruption, and makes no new
toolchain call. A complete shared-cache tree then copies to a distinct root and
restores the identical accepted closure with authorization disabled and zero
toolchain calls. The copy proves that absolute path, inode, machine, and cache
instance are not reuse gates. None of these fixtures changes production
behavior.

A final adapter-level cache-first correction is required before combined
execution. The group function may not require a usable
`produce_with_evidence` method until `_load_decision` returns a genuine miss,
and the service adapter may not instantiate the project OSS toolchain merely
to validate a fully cached gate. Pass a lazy toolchain proxy from the adapter;
resolve the real project toolchain only on the first authorized producer call.
A fully cached gate must therefore succeed with an unusable toolchain object
and with a factory that raises if invoked. An unauthorized miss must fail
before factory resolution, while an authorized miss resolves the factory once
and produces only missing evidence. This closes source-independent combined
reuse rather than only the lower-level decision-cache lookup.

The adapter-level correction is now implemented. Cached group restoration no
longer requires a usable producer object, and the service adapter passes a
proxy that instantiates the project toolchain only on the first evidence
request. The strengthened gate fixture restores with an unusable toolchain,
blocks an unauthorized missing decision before producer access, and repairs
the miss after authorization. The proxy fixture proves zero eager factory
calls and one factory resolution across repeated producer calls. The complete
dual-frequency suite passes 554 tests.

The combined compiler also requires one direct plan-level fixture rather than
only separate jitter and OSS fixtures. Starting from one fiber endpoint that
contains both terminal services, compile `jitter,oss` together and require
fixed jitter blocks, one OSS equivalence gate, the gate dependency on the
observed pPAM workspace, and every expensive task to carry
`cache_first_expensive`. The compiled child must contain no expensive task that
would be rejected before its cache probe when the combined command omits
expensive authorization.

The combined compiler fixture is now implemented. One normative-fiber endpoint
compiled with both analyses produces two fixed jitter blocks, one OSS
equivalence gate, the gate dependency on its pPAM observed workspace, and only
cache-first expensive tasks. The focused checkpoint suite passes 12 tests and
the complete dual-frequency suite passes 556 tests. Live reuse remains
unclaimed until the independent OSS child is terminal and the real combined
command completes without expensive authorization.

The three focused cache-first suites were rerun during formal OSS segment
`segment_0010` on 2026-07-22 and now pass 22 tests plus two subtests after the
decision-to-two-row closure fixtures were added. This current
check covers OSS decision reuse and blocked misses, jitter provider reuse and
blocked physical misses, and sensitivity checkpoint planning. It does not
replace the required live no-authorization combined execution after independent
OSS reaches terminal closure.

A current-worktree prelaunch replay on 2026-07-23 repeated the eight decisive
cache-first boundaries without reading the active formal cache. The executor
admitted cache-first expensive probes without global producer authorization
and retained one OSS solver token. The OSS gate rejected an unauthorized miss
before the toolchain, restored a directly copied complete cache without the
toolchain, and rejected a cached decision whose standard row closure was
missing. The physical jitter block matched the historical producer, restored
from a directly copied cache with authorization disabled, rejected corruption,
and rejected a true miss before the physical provider. The combined compiler
again marked every expensive task cache-first, while the jitter-only compiler
retained fixed shared block ranges. All eight targeted tests passed under
Conda `leaddbs`. The first seven passed in one isolated invocation; the jitter
integration module initially lacked the separately packaged
`seed_target_connectivity` import in that temporary test path, then passed
after the package was added to the same isolation root. This was an import-path
setup error rather than a product failure. Formal combined execution remains
gated on terminal independent OSS evidence.

The complete affected regression, including the executor suite, then passed 53
tests plus eight subtests. This adds parent-owned admission, dependency
re-evaluation, exact resume, and cache-first dispatch coverage to the three
provider and planning suites without polling or restarting the formal OSS run.

A broader current-worktree replay on 2026-07-22 combined the complete cache,
executor, jitter-provider, OSS-axis-equivalence, run-cache-cleanup, and
sensitivity-checkpoint suites. It passed 93 tests plus 26 subtests under Conda
`leaddbs`. This single gate covers atomic and copied portable cache entries,
process-local verification, exact resume and dependency-skip re-evaluation,
both cache-first authorization boundaries, decision-to-two-row closure,
success-only cleanup, and retained sensitivity checkpoints. It used only
temporary injected producers and caches, so the independent real OSS closure
and no-authorization real combined lineage remain required.

Before that live launch, the synthetic independent-extension acceptance must
exercise the same authorization boundary. It first completes standalone jitter
and standalone OSS with the expensive authorization required for their cold
misses, then launches the combined child with
`allow_expensive_producers=False`. The combined child must complete using only
the populated physical caches and preserve the union of requested terminal
analyses. Endpoint pPAM aggregation remains outcome-specific and must execute;
its invocation is not a physical OSS producer call. The focused provider and
toolchain fixtures, rather than the synthetic aggregate counter, prove zero
physical producer calls on complete cache hits. This strengthens the preflight
but does not substitute for the formal real-cache combined lineage.

This exact synthetic acceptance was replayed on 2026-07-22 and passed. The
fixture created an observed parent checkpoint, completed independent jitter,
completed independent OSS with expensive authorization, and then completed the
combined child with expensive authorization disabled. The combined service
closure was the union of the independent jitter and OSS closures, the parent
manifest digest did not change, and restored parent task documents remained
byte-identical. This accepts the end-to-end local authorization and parent
immutability boundary. Rerunning the scenario together with the OSS hit/miss
and copied-jitter-cache fixtures passed four focused tests; the miss fixtures
still prove failure before their respective physical producer calls. The real
combined lineage remains pending until the independent formal OSS child reaches
terminal acceptance.

A current executor-coverage audit on 2026-07-22 confirmed that a second
micro-fixture containing only two cache-first tasks would not add an uncovered
boundary. The synthetic acceptance above runs through `WorkflowService`, the
compiled sensitivity plan, the production executor, the production jitter
block service, and the production OSS axis-gate service. It therefore proves
more than the generic executor probe: both cache-first domains enter with
expensive authorization disabled, their populated caches are consumed, their
dependent endpoint services complete, and the parent checkpoint remains
byte-identical. The separate jitter-provider and OSS-axis miss fixtures retain
the complementary proof that a true cache miss stops before the respective
physical producer. No duplicate executor test or production behavior change
was added.

A separate 2026-07-22 end-to-end replay passed all three lineage-control
fixtures under Conda `leaddbs`: a missing parent creates a new main lineage
before extension execution, jitter and OSS execute as independent children of
one completed parent, and extension resume invokes only the noncompleted
sensitivity task. These fixtures mutate temporary synthetic roots only and do
not substitute for the active real OSS, combined, or publication acceptance.

The earlier `task17-jitter-v7-inclusive-formal-20260719` lineage is retained as
partial runtime evidence only. It stopped before endpoint statistics and cannot
publish or resume as the formal jitter result.

All children use fourteen workers. The production cache-cleanup policy remains
false, so successful children retain shared cache and run-owned resume state.
Failed or partial children are never cleanup-eligible. A VAL unmount stops new
writes and forbids automatic restart until the mount is verified again.

The successor independent jitter plan contains 800 tasks. Of these, 448 are
immutable checkpoint roots, 240 are fixed physical blocks covering six
physical groups with forty blocks per group, and 112 are endpoint statistics.
The six groups are reference voxel, no-delta add-on voxel, adjusted add-on
voxel, reference fiber, no-delta add-on fiber, and adjusted add-on fiber. Each
endpoint consumes the complete physical-block barrier and retains its own
statistical refit.

The realized branch inventory contains 22 no-delta add-on voxel endpoints,
six adjusted add-on voxel endpoints, 24 no-delta add-on fiber endpoints, and
four adjusted add-on fiber endpoints. The 46 no-delta add-on endpoints retain
the version-one reduced physical groups. The ten adjusted add-on endpoints use
the version-two support-preserving groups below and must not invoke Decision
24's endpoint-local full-parent artifact path.

Adjusted-branch Layer-1 closure uses a versioned support-preserving block, not
the endpoint-local full-parent artifact path. The compiler adds separate
adjusted add-on voxel and adjusted add-on fiber physical groups. Their reduced
union contains every realized add-on final feature plus every matched-reference
selected source feature required by full and fold DeltaReferenceScore weights.
The producer streams the complete parent geometry once for each physical
component, subject, and replicate range. It retains union-axis exposures and a
compact all-parent suprathreshold-count tensor for every realized matched-
reference tau. It must not retain or publish a complete parent exposure matrix.

The adjusted consumer reconstructs the final selected exposure and reference
overlap from union-axis views. It reconstructs full and fold DeltaReferenceScore
values from the matched-reference selected source view. In-support counts use
the exact finite full and fold reference-weight masks; the compact all-parent
count supplies the denominator required by the existing inclusive reference-
tau support rule. The reconstructed support rows, support status, score arrays,
overlap, rebuilt observed request, and final jitter metrics must match the
retained full-parent provider before the adjusted endpoint switches paths.

The completed parent dependency records fix the production support-threshold
vector without introducing a configured default. The six adjusted add-on voxel
endpoints use their matched-reference selections at tau 200 and Coverage 5:
ESS, MDS-UPDRS I, MDS-UPDRS IV, ODQ, SCOPA-AUT, and SDQ. The four adjusted
add-on fiber endpoints use their matched-reference selections at tau 400 and
Coverage 5: FSS, KPPS, ODQ, and PDQ-39. The v2 descriptor must derive these
values from each `ReferenceDependencyRecord`; it must not infer them from model
family or the configured main-analysis preference. A future endpoint with a
different realized reference choice therefore creates the corresponding
ordered threshold entry instead of reusing either observed production value.

The new cache identity binds the complete parent axis, ordered union keys,
ordered matched-reference tau vector, physical source identities, replicate
schedule, support-count algorithm version, and producer version. The block
keeps the 12-GiB admission charge, existing connectome-I/O limit, one persistent
spawn pool, single-write publication, and no nested executor. Existing block
version one entries remain valid for their original reference and no-delta
scope but cannot satisfy adjusted support. Migration acceptance covers a small
exact scalar fixture, direct-voxel and normative-fiber full-provider parity,
worker-order invariance, cache corruption, one-block resume, and the ten
realized production adjusted endpoints. Only after those gates pass may the
adjusted endpoints join the reduced-axis production lineage and close the open
Layer-1 requirement.

The corrected independent OSS plan contains 590 tasks. Of these, 196 are
immutable checkpoint roots, two are axis-equivalence group tasks, and 392 are
new endpoint pPAM tasks. Every one of the 56 fiber endpoints receives one
observed workspace, one deterministic schedule, four fixed permutation blocks,
and one aggregate. Each observed workspace depends on exactly one group gate.
Only a gate task or an observed-workspace task on the retained FAIL path may
materialize a missing physical OSS generation. Both receive the sole external-
solver token and require explicit expensive-producer authorization. Schedules,
permutation blocks, and aggregates cannot launch the solver.

The two current gate groups use the reference and add-on ordered final-axis and
`Omega_max` pairs. The completed parent exposes the relevant `Omega_max` cache
entries through its portable shared-exposure identities, so the loader enriches
the in-memory checkpoint without mutating parent files. Physical-row closure is
derived from the canonical runtime requests and is not frozen from a pre-run
count estimate. Each row has an immutable decision cache; group resume reuses
accepted rows and continues only missing or invalid rows. Formal acceptance
uses the terminal `row_decision_ids` closure returned by both gate records,
requires every referenced decision and its two row manifests to validate, and
then requires every planned downstream task to reach a nonfailed terminal
state. A row execution contains ten fixed sample-level OSS solver invocations;
the final cold-execution bound is reported from the terminal group closures
rather than from a provisional 34/26 partition.

For each row, compare all ten sample-wise axon states after selecting the final
canonical IDs from the `Omega_max` result. PASS requires state mismatch count
`< 1`, activation-count mismatch count `< 1`, and probability absolute
difference below the internal tolerance for every final-axis fiber. A group
switches to `Omega_max` only when all row decisions pass. Any FAIL or unproven
row retains the complete historical final-axis path for that group. Both paths
publish final-axis endpoint matrices and statistics, so the gate cannot change
the fitted feature axis.

The successor combined plan contains 1194 tasks. Of these, 448 are immutable
checkpoint roots and 746 are new tasks forming the exact union of 240 jitter
blocks, two OSS gate tasks, and 504 endpoint statistics and pPAM tasks. It
follows the two independent children so valid physical exposure, gate-decision,
and OSS row-cache entries are warm. Acceptance requires cache validation and
reuse without duplicate physical production, no observed, resolver, final,
formal permutation, bootstrap, or in-sample recomputation, and no mutation of
the parent lineage.

The 2026-07-20 implementation checkpoint closes the code-side gate boundary.
The real completed parent validated 56 recovered fiber descriptors, with the
reference axis expanding from 3401 to 10320 fibers and the add-on axis from
2004 to 7193 fibers. The real independent OSS dry plan contains 590 tasks and
two group gates. The row-decision cache, ten-state comparison, O(1) row
manifest, final-axis subset publication, solver-token admission, and resume
reuse passed synthetic acceptance. The complete dual-frequency regression
passed 530 tests and 310 subtests outside the restricted system-monitoring
sandbox. This evidence does not close the scientific gate: the 60 real row
classes still require formal solver execution before the OSS child may use
`Omega_max`.

Each child must finish with no failed or nonterminal task, a completed run
manifest, complete reporting documents, a valid artifact index, unchanged
parent-manifest binding, and publication below the canonical model-set
extension roots. Resume acceptance interrupts or invalidates one bounded child
task and verifies that only its required descendants rerun. Resource evidence
records effective worker admission, CPU, RSS, swap, connectome-I/O tokens, and
the external-solver token. Performance windows overlapping unrelated VAL-heavy
work remain correctness evidence but cannot support an uncontended throughput
claim.

Intermediate v7 runtime evidence on 2026-07-19: startup restored all 448
checkpoint roots before launching four physical producers. The first four
reference-voxel ranges took 756.62, 756.66, 757.12, and 758.68 seconds while
their workers populated the source sampler. The remaining 36 ranges took from
0.74 through 0.96 seconds, with a median of 0.79 seconds. All forty block
references recorded a false reuse field, so this acceleration is persistent
worker sampler reuse followed by new cache publication, not a pre-existing
cache hit. Four workers reached an aggregate RSS near 34 GiB after the first
group and later near 40 GiB while groups overlapped. The largest sampled worker
RSS remained near 10.1 GiB and `< 12 GiB`, its declared charge. Swap remained
at its 0.75-MiB startup value and VAL remained mounted through a 10-Gb/s USB
link.
This is partial runtime evidence only. It does not establish child completion,
endpoint completion, adjusted-branch performance, uncontended throughput, or
the final Step 10 acceptance result.

The v7 endpoint-boundary audit found that the retained adjusted fallback cannot
be allowed to enter production endpoint execution. Each adjusted replicate
publishes complete parent prepared-exposure arrays beneath the endpoint task,
including multiple parent-sized add-on voxel components, while the scheduler
charges the entire `spatial_jitter` task only 2 GiB. After the global block
barrier, the ten adjusted tasks could therefore run beside reduced-axis
consumers, exceed the declared memory accounting, and consume the remaining
844 GiB volume capacity with endpoint-local parent copies. The run is stopped
before any endpoint statistic starts. Its eighty completed reference-voxel and
reference-fiber blocks remain valid v1 cache evidence; four in-flight add-on
voxel blocks had not published and create no resumable result. A successor
lineage may reuse the eighty completed v1 entries, but adjusted endpoints must
first move to the support-preserving v2 block path described above. The partial
v7 lineage cannot publish a formal jitter extension.

Support-preserving v2 implementation acceptance on 2026-07-19: the extension
compiler now creates separate adjusted voxel and fiber groups, uses producer
version two, restores the matched-reference prepared parent as a direct block
and endpoint checkpoint, and excludes generated block tasks from the immutable
parent-root audit. The physical producer retains only union-axis component
exposures, deterministic replicate seeds, ordered matched-reference taus, and
complete-parent suprathreshold counts. The consumer rebuilds final exposure,
reference overlap, full and fold DeltaReferenceScore values, support rows,
support status, and replicate-local nuisance inputs in a task-local arena.

Direct-voxel and normative-fiber scalar parity tests compare the compact path
against the existing full-parent implementation. Synthetic production-path
integration tests additionally cover both adjusted model families, copied
block consumption, the add-on subset within a larger reference cohort, locked
reference parent identity, deterministic seed schedules, and exact exposure
and score arrays. The focused checkpoint, input-provider, jitter-provider, and
DeltaReferenceScore matrix passes 65 tests and 10 subtests. Static compilation
also passes. The complete dual-frequency matrix passes 522 tests and 308
subtests when macOS system monitoring, spawn, and process-group inspection are
available. The restricted monitoring sandbox separately passes 491 tests; its
34 failures are all environment-denied executor, spawn, or process-group
checks. This closes the local implementation and numerical fixture gate; the
800-task successor run, production resource evidence, cache resume, and
published jitter result were still open at this historical checkpoint. Later
evidence below closes the support-preserving jitter run, its cache/resume
boundary, and its canonical v2 publications; it does not close independent OSS
or combined execution.

The production-parent read-only preflight compiles exactly 800 successor tasks:
448 immutable checkpoint roots, 240 physical blocks, and 112 endpoint
statistics. The physical set contains 160 version-one blocks and 80
version-two blocks. Each of the six model-family and branch groups contributes
forty ranges. This confirms that the production DAG matches the frozen
support-preserving contract before any successor run directory is created.

The first independent OSS production attempt on 2026-07-20 restored all 196
parent roots and admitted only one external solver worker, but both group gates
failed on their first physical row. OSS-DBSv2 completed the FEM stage and
created the time-domain result; `run_pathway_activation` then failed while
compiling the NEURON mechanism because `nrnivmodl` was absent from the child
process `PATH`. The executable is present under the locked `ossdbsv2`
environment. This is an execution-environment propagation defect, not a
scientific input, final-axis, or `Omega_max` decision failure.

The corrective boundary follows the already frozen row-runner contract in
`normative_fiber_oss_ppam_generation_plan.md`: every external OSS command must
receive an explicit child environment whose leading `PATH` component is the
parent directory of the attested environment Python executable. The inherited
remainder of `PATH` stays intact. A focused subprocess test must prove that a
nested executable placed beside that Python is discoverable, and existing
timeout, process-group termination, logging, and command-identity tests must
remain unchanged. After the focused and complete dual-frequency suites pass,
the failed child may resume in place. Resume must restore the 196 completed
roots, rerun only the two failed gates and their dependency-derived skipped
descendants, and retain both failed runtime workspaces as diagnostic evidence.

The corrective implementation now supplies that explicit child environment.
A real probe launched through the locked environment Python resolved
`nrnivmodl` to the locked environment `bin` directory. The focused toolchain
suite passed 29 tests, the complete pytest regression passed 531 tests and 310
subtests, the package-aware unittest regression passed 520 tests, static
compilation passed, and the diff whitespace check passed. These tests close the
execution-path repair only; the original failed child remains the formal resume
target and the real two-group scientific gate remains open until its resumed
solver execution finishes.

That resume exposed a second, independent production boundary before any row
decision published. The first reference final-axis row completed all ten
samples. On the matching 10320-fiber `Omega_max` row, the first OSS sample grew
beyond the 48-GiB managed-memory ceiling and reached about 72.8 GiB during the
stop sequence. Main-process termination also left the separately sessioned
solver alive until it was explicitly terminated. VAL stayed mounted, swap did
not grow, no immutable decision or row cache published, and the 196 restored
parent roots remain valid.

Formal resume is now gated on two implementation repairs. External execution
must split a logical row into deterministic ordered chunks containing `< 3501`
fibers, run the same ten fixed samples for every chunk, concatenate exact states
and probabilities on the unchanged full canonical axis, and publish only the
existing full-row cache identity. The chunk limit is an internal execution
constant rather than YAML or scientific model configuration. Solver-capable
tasks charge 48 GiB, and the resource ledger cannot admit any grant above its
managed ceiling. The 48-GiB value is a conservative admission charge that
prevents a second solver from entering the 64-GiB managed pool; it is not a
post-admission hard RSS limit for the single admitted solver. A real reference
`Omega_max` chunk must demonstrate complete task-tree RSS `< 64 GiB`, swap
growth `< 1` byte, and an intact system reserve under one-second sampling before
the formal child may resume. Per-role solver RSS remains recorded as diagnostic
resource provenance.

The worker must also forward termination to the active external process group
using the existing bounded TERM-to-KILL path before it exits. Acceptance sends
a termination signal while a worker owns a live descendant and proves that no
process-group member survives. Focused chunk-order, state-concatenation,
resource-admission, and termination tests plus the complete regression precede
the real single-row resource gate. The interrupted task JSON and runtime work
remain diagnostic and resumable evidence; they are not cleaned or declared
complete.

The implementation repair passed 62 focused OSS/executor tests and the complete
dual-frequency regression passed 534 tests plus 310 subtests in the `leaddbs`
environment. The real reference-chunk RSS gate remains open and formal OSS
resume is still prohibited until that measured gate passes.

The first monitored segment after that repair executed an exact 3500-fiber
reference `Omega_max` chunk. One-second sampling measured solver RSS at
45,910,048,768 bytes and complete descendant RSS at 46,284,881,920 bytes. The
minimum available memory remained 77,078,921,216 bytes, swap growth stayed
`< 1` byte, and VAL remained mounted. The segment was stopped because this
crossed the earlier 32-GiB task charge, not because it crossed the 64-GiB
managed ceiling. The measured contract therefore charges the sole solver task
48 GiB while preserving the 64-GiB cumulative ceiling and the existing reserve.
Formal continuation then completed all ten samples of one exact 3500-fiber
`Omega_max` chunk. One-second sampling measured a segment-0004 solver peak of
42,068,082,688 bytes and a complete-descendant peak of 42,447,421,440 bytes;
minimum available memory remained 78,255,472,640 bytes, swap growth stayed
`< 1` byte, and VAL remained mounted. Removal of the completed chunk workspace
and creation of the next ordered 3500-fiber chunk prove that the full logical
chunk returned successfully. This closes the real resource gate and permits the
independent OSS child to continue under the conservative 48-GiB sole-solver
admission charge and 64-GiB cumulative hard ceiling.

Later segment-0005 coverage showed why the admission charge and runtime hard
ceiling must remain distinct. During the `sub-SNr012` right-side 105-Hz
final-axis and `Omega_max` rows, one-second sampling measured peak solver RSS at
61,986,045,952 bytes and peak complete descendant RSS at 62,497,554,432 bytes.
The latter remained `< 64 GiB`, minimum available memory across these windows
remained 63,444,467,712 bytes, swap growth stayed `< 1` byte, VAL remained
mounted, and no second solver was admitted. This observation supersedes the
earlier solver-RSS `< 48 GiB` acceptance wording without changing the 48-GiB
ledger charge, the one-solver token, or the 64-GiB task-tree hard ceiling.

The same segment later exposed an independent macOS NGSolve exit defect during
the `sub-SNr012` right-side 105-Hz tail row. Sample 04 completed FEM and
time-domain reconstruction, wrote a 5.7-GB `oss_time_result_PAM.h5`, and logged
the terminal volume-conductor timings, but the OSS process remained near one
CPU core for more than eight minutes without writing `success_rh.txt` or
removing `fail_rh.txt`. A five-second process sample placed every main-thread
observation in `ngcore::ExitTaskManager` and
`ngcore::TaskManager::StopWorkers`, while the TaskManager worker threads were
asleep. This is an external-runtime termination defect, not a completed sample
or a numerical failure. The active resume must stop through the existing
TERM-to-KILL process-group contract and retain its checkpoint, cache, and
runtime work.

Formal continuation now requires a repository-owned OSS CLI bootstrap that
calls `ngsolve.SetNumThreads(1)` before delegating to `ossdbs.main.main()`. The
thread count is an internal execution constant and must not enter scientific
YAML identity. Command provenance must identify the bootstrap and the fixed
thread count. Acceptance requires a focused command-construction test, a real
TaskManager smoke process that exits normally, preservation of timeout and
process-group termination tests, and replay of the exact interrupted sample.
That replay must produce the standard success marker, remove the fail marker,
exit with code zero, and preserve validated field/state output. Post-terminal
log exit latency must stay `< 60` seconds; the existing six-hour solver timeout
remains only a final safety backstop and cannot by itself close this defect.

The repository bootstrap and command boundary were implemented before the
formal replay. The focused OSS toolchain suite passed 33 tests, including fixed
thread ordering, the real bootstrap command, TaskManager smoke behavior,
timeouts, and process-group termination. The locked `ossdbsv2` environment also
ran the real bootstrap smoke and exited with code zero. The correctly packaged
dual-frequency discovery suite then passed all 525 tests. The bootstrap source,
including `NGSOLVE_THREADS` set to one, participates in the producer definition
digest, while the external command invokes the repository bootstrap through the
validated environment Python. These results close the static and local-runtime
gates; only the exact interrupted formal sample replay and its `< 60`-second
post-terminal exit gate remain open.

Segment 0006 then resumed the same independent OSS lineage and reclaimed the
stale running equivalence task without rewriting its identity. Process-table
evidence showed the locked environment Python invoking the repository
`ossdbs_bootstrap.py` for sample 04 of an earlier replayed row. Its OSS log
reached `Process Completed`, `success_rh.txt` appeared, `fail_rh.txt` was absent,
and pathway activation began in the same filesystem timestamp interval. The
next process-table observation found the bootstrap process absent, bounding
post-terminal exit latency `< 10` seconds for that structurally equivalent
sample. A subsequent uninterrupted 180-second window sampled the complete task
tree every second: peak task-tree RSS was 42,198,908,928 bytes, peak solver RSS
was 41,467,838,464 bytes, peak downstream pathway utilization was above twelve
CPU cores, and swap growth stayed `< 1` byte. VAL remained online throughout.
This closes the bootstrap path and resource gates. The exact interrupted-sample
gate was then observed directly in the same segment for sample 04 of the
3320-fiber tail covering canonical fiber IDs 1141982 through 1699401. The
process table recorded the locked `ossdbsv2` Python invoking the repository
`ossdbs_bootstrap.py` with that exact sample's parameter JSON. Its OSS log
reached `Process Completed`; `success_rh.txt` appeared, `fail_rh.txt` was
removed, the bootstrap disappeared at the next one-second observation, and the
post-terminal exit latency was one second, therefore `< 60` seconds. Pathway
activation then completed and published both `Axon_state_default_4.mat` and
`Pathway_status_default_4.json`. During this exact observation, peak complete
task-tree RSS was 22,176,432,128 bytes, therefore `< 64 GiB`, and reported used
swap remained 2358.44 MiB from the first through the final sample with no
observable growth. These artifacts close the exact interrupted-sample replay
gate; the independent lineage must still finish every remaining row and pass
its equivalence, manifest, artifact-index, and reporting audits before OSS is
accepted as complete.

Completion of that tail atomically published its paired final-axis and
`Omega_max` rows. The shared cache advanced from 36 to 38 complete row
manifests and from 18 to 19 equivalence decisions. The new decision has status
`pass`, maximum probability difference 0, state mismatch count 0, and
activation-count mismatch count 0. The worker then entered the next group,
showing that the repaired exact boundary returned control to the persistent
executor rather than merely leaving valid-looking sample files behind.

**Historical provisional-denominator warning.** The chronological progress
records immediately below used an early estimate of 120 row manifests, 60
decisions, 34 reference decisions, and 26 add-on decisions. Production later
created a 35th reference decision and disproved every one of those denominators
and derived remaining-work counts. In those paragraphs, only each completed
numerator, immutable decision identity, numerical comparison, and measured
resource observation remains evidence. Current acceptance uses only the exact
ordered `row_decision_ids` closure committed by each terminal group gate.

The following paired comparison also completed without intervention. It
processed three 3500-fiber chunks and one 3320-fiber tail, each through all ten
parameter samples, and advanced the shared cache to 40 complete row manifests
and 20 complete equivalence decisions. The new decision has status `pass`, maximum
probability difference 0, state mismatch count 0, and activation-count mismatch
count 0. Peak complete task-tree RSS across the directly monitored chunk
windows was 39,160,446,976 bytes, therefore `< 64 GiB`; reported used swap
remained 2358.44 MiB with no observable growth. The worker then entered the
next comparison under the same lineage and resource contract.

The next comparison completed one 3401-fiber final-axis row and an
`Omega_max` row split into two 3500-fiber chunks plus one 3320-fiber tail, with
all ten parameter samples completed in every chunk. Atomic publication advanced
the shared cache to 42 complete row manifests and 21 complete equivalence decisions.
The new decision has status `pass`, maximum probability difference 0, state
mismatch count 0, and activation-count mismatch count 0. Peak complete
task-tree RSS in the directly monitored windows was 55,246,766,080 bytes,
therefore `< 64 GiB`; reported used swap fell from 2358.44 MiB to 2155.06 MiB
instead of growing. The persistent worker then entered the next comparison.

The subsequent comparison completed another 3401-fiber final-axis row and an
`Omega_max` row split into two 3500-fiber chunks plus one 3320-fiber tail, with
all ten parameter samples completed in every chunk. Atomic publication advanced
the shared cache to 44 complete row manifests and 22 complete equivalence decisions.
Decision `c107dd649571c22f2d54a69fd6c327b0e5ebca0adc73f338510d8214441d59b3`
has status `pass`, maximum probability difference 0, state mismatch count 0,
and activation-count mismatch count 0. Peak complete task-tree RSS across the
directly monitored windows was 33,954,332,672 bytes, therefore `< 64 GiB`;
reported used swap fell from 2155.06 MiB to 2139.06 MiB instead of growing.
The persistent worker then continued the remaining independent OSS rows.

The next comparison completed one 3401-fiber final-axis row and an
`Omega_max` row split into two 3500-fiber chunks plus one 3320-fiber tail, with
all ten parameter samples completed in every chunk. Atomic publication advanced
the shared cache to 46 complete row manifests and 23 complete equivalence decisions.
Decision `c7959b2302255df4381bafbe519d5f9493ebfc76cbfabbad959a2db073b35d82`
has status `pass`, maximum probability difference 0, state mismatch count 0,
and activation-count mismatch count 0. Peak complete task-tree RSS across the
directly monitored windows was 47,340,732,416 bytes, therefore `< 64 GiB`;
reported used swap remained 2139.06 MiB with no observable growth. The
persistent worker then continued the remaining independent OSS rows.

The following comparison completed one 3401-fiber final-axis row and an
`Omega_max` row split into two 3500-fiber chunks plus one 3320-fiber tail, with
all ten parameter samples completed in every chunk. Atomic publication advanced
the shared cache to 48 complete row manifests and 24 complete equivalence decisions.
Decision `a720c3fa3d67f5c9d93ce6ce5f43ef8ce0a25799abe12ab37c85d5e066ebcba3`
has status `pass`, maximum probability difference 0, state mismatch count 0,
and activation-count mismatch count 0. Peak complete task-tree RSS across the
directly monitored windows was 62,838,358,016 bytes, therefore `< 64 GiB`;
reported used swap fell from 2139.06 MiB to 2123.06 MiB and then remained
unchanged. The persistent worker then continued the next independent OSS
comparison.

The next comparison completed one 3401-fiber final-axis row and an
`Omega_max` row split into two 3500-fiber chunks plus one 3320-fiber tail, with
all ten parameter samples completed in every chunk. Atomic publication advanced
the shared cache to 50 complete row manifests and 25 complete equivalence decisions.
Decision `1c8af8b9cbef090f5cc8fbee126d0fcbc9d436001a1a1d56ebd20e6b2f3e1ecd`
has status `pass`, maximum probability difference 0, state mismatch count 0,
and activation-count mismatch count 0. Peak complete task-tree RSS across the
directly monitored windows was 44,041,093,120 bytes, therefore `< 64 GiB`;
reported used swap remained 2123.06 MiB with no observable growth. The
persistent worker then continued the next independent OSS comparison.

The following comparison completed one 3401-fiber final-axis row and an
`Omega_max` row split into two 3500-fiber chunks plus one 3320-fiber tail, with
all ten parameter samples completed in every chunk. Atomic publication advanced
the shared cache to 52 complete row manifests and 26 complete equivalence decisions.
Decision `f540516225c37b9ac5b40300350b6f776d836e345d5902fafc1ab6d59b266eec`
has status `pass`, maximum probability difference 0, state mismatch count 0,
and activation-count mismatch count 0. Peak complete task-tree RSS across the
directly monitored windows was 45,620,887,552 bytes, therefore `< 64 GiB`;
reported used swap fell from 2123.06 MiB to 2115.06 MiB instead of growing. The
persistent worker then continued the next independent OSS comparison.

The next comparison completed one 3401-fiber final-axis row and an
`Omega_max` row split into two 3500-fiber chunks plus one 3320-fiber tail, with
all ten parameter samples completed in every chunk. Atomic publication advanced
the shared cache to 54 complete row manifests and 27 complete equivalence decisions.
Decision `3a5727f5ff3ae976f251afd0b953681b34bf4bf385e12dd464d5ffaeea16920d`
has status `pass`, maximum probability difference 0, state mismatch count 0,
and activation-count mismatch count 0. Peak complete task-tree RSS across the
continuously monitored comparison was 44,909,838,336 bytes, therefore
`< 64 GiB`; reported used swap remained 2115.06 MiB with no observable growth.
The persistent worker then continued the next independent OSS comparison.

The following comparison completed one 3401-fiber final-axis row and an
`Omega_max` row split into two 3500-fiber chunks plus one 3320-fiber tail, with
all ten parameter samples completed in every chunk. Atomic publication advanced
the shared cache to 56 complete row manifests and 28 complete equivalence decisions.
Decision `d34a5ec2d330373d38ccdb9b7bb674285f34204ba38fa3ce7811d2add554d675`
has status `pass`, maximum probability difference 0, state mismatch count 0,
and activation-count mismatch count 0. Peak complete task-tree RSS across the
continuously monitored comparison was 35,174,645,760 bytes, therefore
`< 64 GiB`; reported used swap remained 2115.06 MiB with no observable growth.
The persistent worker then continued the next independent OSS comparison.

The next reference-fiber comparison completed one 3401-fiber final-axis row and an
`Omega_max` row split into two 3500-fiber chunks plus one 3320-fiber tail, with
all ten parameter samples completed in every chunk. Atomic publication advanced
the shared cache to 58 complete row manifests and 29 complete equivalence decisions.
Decision `79aee2c2c650f9cbd14c66fcc2863fb8501d9793cc8d39be547be3275da5509d`
has status `pass`, maximum probability difference 0, state mismatch count 0,
and activation-count mismatch count 0. Peak complete task-tree RSS across the
continuously monitored comparison was 46,838,235,136 bytes, therefore
`< 64 GiB`; reported used swap fell from 2115.06 MiB to 2099.06 MiB instead of
growing. The lineage still required terminal group closure, successful
dependency re-evaluation, all downstream pPAM
tasks, completed manifest and publication, artifact-index and reporting audits
before the independent OSS extension is accepted as complete.

The following reference-fiber comparison completed one 3401-fiber final-axis
row and an `Omega_max` row split into two 3500-fiber chunks plus one 3320-fiber
tail, with all ten parameter samples completed in every chunk. Atomic
publication advanced the shared cache to 60 complete row manifests and 30
complete equivalence decisions. Decision
`021b003c94d21399dac014a6fe10d91e7b433bac95adf20807fd899c96a8b9ba`
has status `pass`, maximum probability difference 0, state mismatch count 0,
and activation-count mismatch count 0. Peak complete task-tree RSS across the
continuously monitored comparison was 43,884,167,168 bytes, therefore
`< 64 GiB`; reported used swap fell from 2099.06 MiB to 2091.06 MiB instead of
growing. The group gate remained nonterminal.

The next reference-fiber comparison completed one 3401-fiber final-axis row
and the `Omega_max` row split into two 3500-fiber chunks plus one 3320-fiber
tail, with all ten parameter samples completed in every chunk. Atomic
publication advanced the shared cache to 62 complete row manifests and 31
complete equivalence decisions. Decision
`162257a4eba6e8f158a3ff99fbb7e6b2d54b8bf6ef6c986c3fa1901be0b1a48c`
has status `pass`, maximum probability difference 0, state mismatch count 0,
and activation-count mismatch count 0. The continuously sampled final 728
seconds of this comparison reached a complete task-tree RSS peak of
49,164,075,008 bytes, therefore `< 64 GiB`; reported used swap fell from
2075.06 MiB to 2059.06 MiB instead of growing. The group gate remained
nonterminal.

The following reference-fiber comparison completed one 3401-fiber final-axis
row and the `Omega_max` row split into two 3500-fiber chunks plus one 3320-fiber
tail, with all ten parameter samples completed in every chunk. Atomic
publication advanced the shared cache to 64 complete row manifests and 32
complete equivalence decisions. Decision
`c912d46a2bbadb043882506a4d1e709a25dcaee6b0c92fe99a609617130d7758`
has status `pass`, maximum probability difference 0, state mismatch count 0,
and activation-count mismatch count 0. Its final row identity is
`339097730c3db93cd469afc2852fe6d2098bef2b0268e9ee8bc5fb6e3205cade`
and its `Omega_max` row identity is
`48744f2726fcf8ce41528e89f57acd9778a84d59470538535dc33b5a389d65c9`.
Continuous one-second sampling across 4174 seconds reached a complete task-tree
RSS peak of 61,318,348,800 bytes, therefore `< 64 GiB`; reported used swap fell
from 2059.06 MiB to 2011.06 MiB instead of growing. The group gate remained
nonterminal, and the persistent worker entered the next comparison without
intervention.

The next reference-fiber comparison then advanced the shared cache to 66
complete row manifests and 33 complete equivalence decisions. Decision
`77de1bcd93c82ebc679d47cbd26afe79a6a9ac77957668813c5afee7f543926f`
has status `pass`, maximum probability difference 0, state mismatch count 0,
and activation-count mismatch count 0. Its final row identity is
`8bee1a8e2b1563c2ba760a2b8d53187a561283fff149a94275becb7bdf984b36`
and its `Omega_max` row identity is
`3bd87dc185ade797102f7a458219ce30ffea8a8cb925598157d99e1a40520f2f`.
Continuous one-second sampling across this 178-second completion window
reached a complete task-tree RSS peak of 13,449,019,392 bytes, therefore
`< 64 GiB`; reported used swap remained at 2011.06 MiB. The group gate remained
nonterminal, and the persistent worker continued without intervention.

The final reference-fiber comparison then completed its one 3401-fiber final
row and all three `Omega_max` chunks for the 10,320-fiber axis. Atomic
publication advanced the shared cache to 68 row manifests and 34
equivalence decisions. At that checkpoint all published decisions belonged to
the reference group, but the running gate had not yet committed its terminal
group record; this checkpoint therefore did not prove reference-group closure.
Decision
`a7c56f99d0230737c64e1c2e006f253c04ac178ff03ae2cc971bb426119c2978`
has status `pass`, maximum probability difference 0, state mismatch count 0,
and activation-count mismatch count 0. Its final row identity is
`659f876096e3caeab60db5af1ca180a9a30326db1104ba3cc6546dc0dad84d6d`
and its `Omega_max` row identity is
`505d2983ef38fe0fd2d39baa882abb77dc8bbc709437d714d478fe0aeea2a363`.
Continuous one-second sampling across 3271 seconds reached a complete
task-tree RSS peak of 41,371,369,472 bytes, therefore `< 64 GiB`; reported used
swap fell from 1995.06 MiB to 1963.06 MiB. All 34 decisions belonged to
`oss_axis_group_078d3c2f2b8ac612a268` and passed. Later resume evidence below
showed that treating this nonterminal count as the complete reference closure
was incorrect.

At 2026-07-21 19:55 PDT, `/Volumes/VAL` became unmounted while the first
add-on decision was producing its `Omega_max` row. The one-second guard stopped
runner PID 1050 immediately and the worker tree exited; no automatic remount or
resume was attempted. The active window had reached a complete task-tree RSS
peak of 45,861,519,360 bytes, therefore `< 64 GiB`. The last guard sample also
reported used swap at 12,032 MiB after a 1963.06 MiB window baseline, so the
interrupted segment cannot satisfy the zero-swap-growth acceptance contract.
The external device remained enumerated as `/dev/disk4s2` but was not mounted.
All 68 complete row manifests, 34 complete decisions, checkpoints, and partial
runtime work remain the resume boundary. Resume requires explicit remount and
writability verification; the interrupted add-on decision must restart from
its last complete immutable row or decision and must not treat temporary
producer state as complete.

The user explicitly authorized resume after macOS remounted the volume. The
pre-resume audit verified a real create, flush, read-size, and cleanup probe on
`/Volumes/VAL`; 68 complete row manifests and 34 complete decisions; no active
Task 17 process; and a Samsung T7 `UsbLinkSpeed` of 10,000,000,000 bits per
second. System memory had more than 4,900,000 free 16 KiB pages. Existing used
swap was 8278.00 MiB, but a 20-second admission window showed no growth.
Authorized resume created `segment_0007` in the same lineage with runner PID
36802 and persistent worker PID 37038. Its one-second guard began at the lower
8270.00 MiB used-swap reading and must stop on any subsequent increase, while
the complete task-tree RSS remains `< 64 GiB`. The worker restarted the next
unpublished physical row from its immutable input boundary; the lineage still
contained 68 complete rows and 34 complete decisions and no replacement run
was created.

Segment 0007 then atomically published two additional row manifests and
decision `bc89a4bc83751b07c5df5880c4a32846c141b0fd5122cc9db7414310e03650e7`,
advancing the durable boundary to 70 row manifests and 35 decisions. The
decision belongs to reference group
`oss_axis_group_078d3c2f2b8ac612a268`; its final row identity is
`615145f0786fb28801b6ef50a135ed821742bb31869da8857520c0be4befed9a`
on 3401 fibers and its `Omega_max` row identity is
`b552be2ea9b02b2dffae7accdc8b864b83372b0ed027d915c1242f2b8ccfd6a3`
on 10,320 fibers. Status is `pass`; maximum probability difference, state
mismatch count, and activation-count mismatch count are all 0. Continuous
one-second sampling across 3919 seconds reached a complete task-tree RSS peak
of 46,496,251,904 bytes, therefore `< 64 GiB`; used swap fell from 8270 MiB to
7710 MiB. This proves that the former 34-reference-row estimate was not the
terminal closure. The gate continues, and its committed group record remains
the authority for the final count.

At the 2026-07-22 07:28 PDT follow-up, `/Volumes/VAL` was no longer mounted and
`diskutil list external physical` returned no external physical device. Runner
PID 36802, persistent worker PID 37038, and all OSS child processes had exited,
so no Task 17 writer remained active. The last boundary verified while the
volume was online remains 70 row manifests and 35 decisions; the offline state
cannot establish whether any later atomic boundary reached the device before
disconnect. No automatic remount or resume is permitted. The same lineage,
checkpoint, cache, and `runtime_work` must be inspected after reconnection and
may resume only after renewed mount, link, write, process, and stable-swap
admission checks plus explicit user authorization.

The user then explicitly authorized another resume. A renewed write probe and
10,000,000,000-bit-per-second USB link check passed, no old writer remained,
and `segment_0008` started in the same lineage with 14 workers and one solver
token. Its used-swap baseline was 6791.88 MiB. The reference gate recomputed
one unpublished final-axis and `Omega_max` pair through all ten parameter
samples for each row while the observed task-tree RSS remained `< 64 GiB` and
used swap fell below the segment baseline. Before either row could publish,
the row-level toolchain identity check launched MATLAB in batch mode. The
MATLAB process stopped making progress, reached the existing 180-second
timeout, and became a zombie while MathWorks ServiceHost members remained in
the same external process group. The timeout cleanup then raised
`cannot signal the live external OSS process group`, so the reference gate
became terminal failed without publishing either row. The persistent worker
reclaimed the historical add-on gate and immediately entered the same MATLAB
identity probe. Continuing would repeat the technical failure rather than
advance the scientific closure, so the runner, worker, MATLAB process group,
and resource tracker were terminated safely. VAL remained mounted; the 70
row manifests, 35 decisions, cache, checkpoints, and both diagnostic workspaces
were retained.

This incident freezes an additional acceptance boundary before the next
resume. Toolchain identity must be resolved once per persistent producer
process or from one separately validated immutable process-local record, not
rerun after every expensive row. MATLAB version, release, update, and computer
identity must be read from the installed `VersionInfo.xml` plus the resolved
architecture directory and matched to the locked YAML values; identity
validation must not launch a second MATLAB batch process. A timed-out probe
must terminate and reap its
owned batch process without treating GUI ServiceHost helpers or zombies as a
live scientific solver. Focused tests must cover a normal identity probe, a
probe timeout with a zombie leader, surviving unrelated helper processes, no
orphaned owned process, stable cached identity reuse across two rows, and zero
solver calls when identity validation fails. A real read-only identity probe
must pass before the same OSS lineage resumes. No row or decision from
`segment_0008` may be counted as complete.

The frozen repair was implemented and accepted locally before another formal
resume. `SubprocessOSSRowExecutor` now validates the complete toolchain once,
commits the verified command set only after all checks pass, and reuses that
process-local record before and after later rows. MATLAB identity is parsed
from the installed `VersionInfo.xml` and architecture directory, so no identity
batch process or ServiceHost tree is created. Timeout cleanup now reaps an
exited managed leader when the initial group signal is denied, while leaving
an unrelated helper outside the scientific boundary untouched. The focused
OSS toolchain suite passed 37 tests plus eight subtests. A real installation
probe matched the locked OSS environment in 0.761 seconds; immediate reuse
took about three microseconds, and the count of MATLAB identity processes
remained zero before and after both calls. The complete dual-frequency suite
then passed 545 tests plus 310 subtests. These checks accept the local repair;
the same lineage must still resume, reproduce the unpublished pair, and reach
terminal gate closure before formal OSS acceptance.

The next authorized resume created `segment_0009`, but it did not accept the
formal OSS gate. Static toolchain identity validation completed without
launching MATLAB, confirming that the identity-probe repair remained active.
The retained reference and add-on gate attempts then each invoked the real
`mh_oss_prepare_canonical_row` MATLAB producer and returned code 1 before an
OSS solver call or any new atomic row publication. Both MATLAB preflight logs
were empty. The segment ended normally with 196 completed tasks, two failed
`establish_oss_axis_equivalence` tasks, and 392 dependency-skipped tasks; the
durable scientific boundary remained 70 row manifests and 35 equivalence
decisions. No Task 17 runner or worker remains active, and automatic resume is
forbidden at this boundary.

Read-only MATLAB diagnosis after `segment_0009` found that even a bounded
simple batch startup could not reach command execution. MathWorks ServiceHost
client logs for the failed startup window report an invalid identity token,
authentication error 428, `Email to be reverified`, and failed identity-token
validation. This is an external MATLAB account or licensing readiness failure,
not evidence of an OSS scientific-computation defect. The user's long-lived
MATLAB GUI and its process group must not be terminated automatically. Before
formal resume, the account email must be reverified and MATLAB must be signed
in again by the user if requested. Acceptance then requires one bounded simple
batch command and one retained-request `mh_oss_prepare_canonical_row` dry run
to succeed with no publication mutation. A fresh explicit resume authorization
is required after those checks; otherwise the cache, checkpoint, and
`runtime_work` remain preserved with `cleanup_on_success` false.

The user then instructed the goal to continue. A fresh bounded MATLAB batch
returned `TASK17_BATCH_READY` with code 0. A publication-isolated copy of the
retained reference request was replayed below `/private/tmp`; MATLAB completed
`mh_oss_prepare_canonical_row` in 11.846 seconds, wrote the required manifest,
and produced all ten declared parameter files without invoking the OSS solver
or modifying the formal lineage. VAL passed a create, flush, read, and cleanup
probe; the Samsung T7 reported a 10,000,000,000-bit-per-second link; used swap
remained unchanged at 6575.88 MiB over 20 seconds; and no prior Task 17 writer
was active. These checks satisfy the frozen restart boundary.

The same independent OSS lineage resumed as `segment_0010` with 14 workers,
one solver token, and `--allow-expensive-producers`. Runner PID 15265 and
persistent worker PID 15357 entered the retained reference equivalence gate.
The formal MATLAB preparation succeeded and the first real OSS sample began;
the segment must still satisfy complete task-tree RSS `< 64 GiB`, swap growth
`< 1 byte`, terminal gate closure, and the full 590-task outcome contract
before independent OSS can be accepted.

A 2026-07-22 resolved-configuration audit confirmed that this lineage recorded
14 workers, expensive-producer authorization for the independent OSS miss, and
`delete_run_cache_on_success` false. The checked-in workflow keeps its generic
default at three workers and expensive producers disabled; the later combined
lineage must therefore pass only the 14-worker resource override and must omit
the expensive-producer flag. The same audit found historical `segment_0008`
still carrying its pre-termination `running` field because the external stop
prevented its `finally` completion write. No process from that segment remains,
later segments exist in the same append-only lineage, and no scientific row
from that attempt is accepted. Final audit must classify it as interrupted
historical provenance, not as the active writer or a terminal acceptance
segment. At that dated snapshot, `segment_0010` was the sole execution segment;
later segment records below supersede that operational status.

A 2026-07-22 operational audit later found that `segment_0010` retained only
intermittent process-tree snapshots and no surviving one-second resource guard.
Those snapshots are useful diagnostics but cannot establish the segment-wide
RSS maximum or the swap invariant. A replacement guard therefore samples the
exact runner descendant tree once per second, records its maximum RSS and the
segment guard swap baseline outside VAL, and sends `SIGTERM` to the runner if
VAL disappears, task-tree RSS reaches 64 GiB, or reported used swap rises above
that baseline. Starting this observer does not restart the lineage, change any
scientific or execution identity, or authorize an expensive producer.
The persistent replacement guard started as PID 31147 with its audit stream at
`/private/tmp/task17-oss-segment_0010-resource-guard.csv`. Its swap baseline is
6844978299 bytes. Through the first surviving samples its task-tree RSS peak was
18602819584 bytes, reported swap did not rise, VAL stayed mounted, and no stop
condition fired.
The first continuity audit covered 2184 persistent-guard samples over about 38
minutes with a maximum adjacent-sample gap of 1.219103 seconds. Every event was
an ordinary sample, observed swap minimum and maximum both matched the
6844978299-byte baseline, and the captured task-tree RSS peak had risen safely
to 48970170368 bytes, still `< 64 GiB`.

The user subsequently required model-driven checks and reports to use a
two-hour interval. At that intermediate point the one-second stop guard and the
temporary ten-second interactive poll were stopped. Before termination, the
guard had accumulated more than 3200 continuous samples, retained the same
48970170368-byte RSS peak, observed swap growth `< 1` byte, and fired no stop
event. This temporary absence of a continuous guard was immediately superseded
by the local-observation decision below and is not the final resource policy.

The user then distinguished local observation from Codex activity. A local
one-second Python guard consumes no model token and is reauthorized; ten-second
Codex polling remains disabled because tool-driven interactive polling consumes
tokens. The two-hour Codex heartbeat remains the only model-driven progress
check and user-facing reporting interval. The restarted local guard uses the
same runner tree, VAL-unmount stop rule, RSS `< 64 GiB` boundary, fresh swap
baseline, and append-only CSV. It changes no scientific, cache, task, or resume
identity.
A detached restart briefly wrote two ordinary samples but did not survive the
tool session. It fired no stop event and did not affect the runner. The guard
was therefore relaunched as persistent local execution session 98901 with PID
95498. Its first persisted samples use a fresh swap baseline of 6794646651
bytes and retain ordinary `sample` status. Earlier guard epochs remain in the
same CSV with their own baselines and peaks; final audit must group rows by
restart epoch rather than compare swap values across baselines.

The temporary guard source is not a reproducible launch boundary for successor
segments. Before combined execution, preserve the same operational contract in
the repository as `run_task17_resource_guard.py`. Its required arguments are
the runner PID, local append-only CSV path, and guarded mount; the RSS ceiling
defaults to 64 GiB and the sample interval defaults to one second. The output
must retain the exact seven-column CSV schema already consumed by both resource
validators. An existing nonempty output is append-only and must have the exact
header before a new epoch may begin. The output path must remain outside the
guarded mount so an unmount cannot erase its evidence.

Every sample resolves the complete runner descendant tree, records aggregate
RSS and CPU, and compares current swap against the epoch startup baseline. A
runner closes cleanly with `runner_exit` only after an independent PID probe
confirms that the declared runner no longer exists. If the process-table
snapshot omits a runner whose PID is still live, the guard treats the snapshot
as untrustworthy and fails closed instead of leaving an unguarded process. A
missing guarded mount, RSS at or above the ceiling, or any positive swap growth
records the corresponding stop event, flushes the row, and sends `SIGTERM` to
the descendant tree and runner. The command returns a nonzero status after a
guard-triggered stop. Malformed process, swap, mount, PID, or output evidence
must fail closed instead of silently continuing. Focused tests must cover
ordinary sampling, independently confirmed clean runner exit, a live PID
missing from one process snapshot, every stop condition, append-header
rejection, and tree termination without signaling an unrelated process. The
active independent OSS process continues under its already-running temporary
guard; only successor launches use the checked-in command, so this
implementation change cannot alter the current segment.

The checked-in guard is now implemented with the frozen CLI and CSV contract.
Eleven focused guard tests cover ordinary descendant-tree aggregation,
independently confirmed clean runner exit, compatibility with both terminal
validators, unmount, RSS, and swap stops, malformed-header rejection, output
placement outside the guarded mount, fail-closed process-evidence handling, a
live runner omitted from one process snapshot, PID absence versus permission
denial, and descendant-only termination. The joint guard and two
resource-validator replay passed 33 tests under Conda `leaddbs`. These tests
use temporary process snapshots and do not replace the active independent OSS
guard or its production evidence. The checked-in guard becomes the required
external observer for combined execution.

After this PID-evidence correction, the complete isolated-package
dual-frequency test directory passed 609 tests in 72.466 seconds under Conda
`leaddbs`. The authoritative invocation included both the repository root and
the isolated `dual_frequency` package root so package-relative tests and the
repository-owned guard module shared the same test process. Two earlier
discovery attempts produced only import-path errors before this corrected
invocation; they are not product-test failures and are not acceptance
evidence.

Terminal resource acceptance uses a repository-owned read-only validator rather
than a hand-copied peak. `validate_task17_resource_acceptance.py` receives one
completed sensitivity run, its accepted execution segment, the append-only
external guard CSV, the expected worker ceiling, and the RSS ceiling. The
finished segment's internal one-second monitor is the full-span authority: it
must report positive sample count, task-tree RSS below the ceiling, both peak
and final swap growth `< 1 byte`, one spawn pool lineage unless a recorded
recovery explains a larger generation count, one external-solver slot, and
reserved CPU `< workers + 1`. Its terminal task count must match the plan and
every plan task document must be completed without a retained dependency skip
or failure.

The strict validator accepts only a single-component `segment_[0-9]+` identity.
It verifies the segment's deterministic connectome-I/O ceiling, one solver
slot, one BLAS thread per worker, positive managed-memory and reserve settings,
and every CPU, memory, connectome-I/O, solver, and running-task peak against the
corresponding declared ceiling. Admission-count and admission-wait maps must
have the exact repository-owned reason closure with finite nonnegative values.
Because live available memory can change during one segment, the writer records
the initial, minimum, maximum, and final managed-memory ceilings and includes
the contemporaneous ceiling in every scheduler window. The validator requires
the four segment values to form a valid closure below the formal RSS ceiling
and checks each sampled reserved-memory value against its own window ceiling;
it must not compare the whole segment only with its startup value.
The strict resource validator uses the writer's same exact timestamp, elapsed,
runnable-slot, admission-reason, and storage-limited derivations as performance
acceptance. A non-string UTC field, Boolean elapsed value, or runnable slot
count different from the bounded ready-plus-running count fails before peak
resource evidence is accepted.
The segment-declared scheduler-window path must be relative and contained by
the run root; its SHA, segment identity, row count, timestamp order, reservation
ceilings, admission-reason closure, and storage-limited derivation must all
validate.

The external guard is supplemental stop evidence. The validator parses every
row, requires monotonic timestamps and self-consistent running RSS peaks,
starts a new epoch when `swap_baseline_bytes` changes or the declared running
peak resets, and requires RSS below the same ceiling and swap growth
`< 1 byte` in every epoch. A normal sample or
runner-exit marker is permitted; any unmount, RSS, swap, or explicit stop event
fails acceptance. The guard may start after the segment because the internal
monitor covers the complete segment, but its actual start, finish, maximum
sample gap, epoch count, and SHA-256 remain visible in the report. The report
also binds the run manifest, plan, selected segment, and every terminal task
document and uses atomic same-byte publication. Focused fixtures cover a valid
multi-epoch guard, RSS rejection, swap rejection, terminal-task mismatch, and
stop-event rejection. A runner-exit, runner-exited, or completed event is
terminal and may occur only in the final row; no sample may follow it.
Independent OSS and combined execution require separate reports.

The resource validator is implemented. Five focused fixtures pass with Python
resource warnings promoted to errors, and the complete dual-frequency
regression passes 581 tests under Conda `leaddbs`.

It cannot be applied dishonestly to `segment_0010`. That process started at
2026-07-22 09:00 PDT. Scheduler-admission metrics, the internal one-second
resource monitor, and timeout/recovery segment fields were committed between
21:59 and 22:17 PDT while the Python process was already running. A running
process does not hot-load those changes, so its eventual segment document
cannot contain the validator's required full-span fields. The strict validator
must reject that pre-instrumentation segment. Independent OSS scientific
closure remains valid when its tasks and manifests complete, but its resource
acceptance must separately combine the surviving external guard epochs, the
terminal exact row inventory, the maximum-row structural memory bound, and
the prior measured max-size row windows. This evidence remains pending until
the gate closes; no full-span internal metric may be invented.

The pre-instrumentation path is a distinct acceptance schema, not a relaxed
mode of the strict validator. Its terminal evidence bundle must contain:

1. the completed run-manifest and exact task closure;
2. both completed OSS gate records and their complete, unique
   `row_decision_ids`;
3. every referenced passing decision and its two valid row manifests;
4. the row-level `n_fibers` inventory, proving which terminal row or tied rows
   have the maximum structural size;
5. one or more already captured guard windows that explicitly bind a maximum
   structural row identity to UTC start and finish times, guard epoch, observed
   RSS peak, and swap baseline; and
6. all surviving external-guard epochs, with no stop event, RSS `< 64 GiB`,
   swap growth `< 1 byte`, and a cryptographic digest of the original CSV.

The validator must recompute the gate, decision, row, and maximum-size closure
from terminal files. It may verify a measured window only when every sample in
the declared UTC interval belongs to one guard epoch and the declared peak is
the maximum observed peak in that interval. The selected maximum-row cache
manifest and its owning decision cache manifest must also have been committed
within the same declared interval. Their local filesystem commit times are
recorded in the acceptance report, but remain machine-specific resource
provenance: they never enter scientific identity, cache validity, task
identity, publication identity, or resume gates. A copied cache cannot inherit
this machine-specific resource verdict without new execution evidence.

A human-authored row label without matching commit times, an unbounded
snapshot, a window that cannot be tied to a terminal maximum row, or an
inferred full-span internal metric must fail closed. The report must state
`external_guard_with_maximum_row_windows`, expose uncovered elapsed intervals,
and describe the result as pre-instrumentation resource evidence rather than
continuous full-span monitoring. Scientific completion and this resource
acceptance remain separate verdicts.

`validate_task17_preinstrumentation_resources.py` implements this separate
schema. It requires a terminal completed run and exactly two accepted OSS gate
records, verifies every decision and row payload against its cache manifest,
derives the unique maximum-`n_fibers` row set, and accepts only measurement
windows that select one guard epoch and bind a terminal maximum row to the
observed interval peak, selected-row manifest commit, and owning-decision
manifest commit. It rejects instrumented segments so they cannot bypass the
stricter validator, preserves the incomplete full-span verdict, reports the
pre-guard and post-guard uncovered intervals, and publishes its report
atomically. Focused fixtures cover valid multi-epoch evidence,
non-maximum-row binding, peak mismatch, stale row or decision commit time,
corrupt decision payload, and incorrect use on an instrumented segment. The
real report remains blocked on terminal OSS gate closure and a frozen
measured-window input assembled only from the already captured runtime
observations.

The commit-time binding is now implemented. The validator derives UTC commit
times from the local selected-row and owning-decision cache manifests, requires
both times inside the declared one-epoch guard window, and records them in the
accepted window report. A new fixture moves each manifest outside the window
independently and proves rejection. The pre-instrumentation, strict-resource,
and checked-in guard suites pass 28 tests under Conda `leaddbs`. This closes
the form-only row-label loophole without changing cache content, scientific
identity, or resume.

The frozen measurement-window input must also be derived reproducibly rather
than assembled by copying IDs and timestamps by hand. A repository command
therefore loads the completed task and two-gate closure, derives the maximum
row set, reads the selected row and decision manifest commit times, and groups
the original guard samples into restart epochs. It selects the latest
deterministic maximum-row candidate whose row and decision commits both fall
inside one epoch and emits that complete epoch as the single bounded window.
The output uses atomic same-byte publication. If no such candidate exists, the
builder fails and the resource verdict remains open; it may not widen a guard
epoch, alter a cache timestamp, choose a nonmaximum row, or synthesize a
sample. The independent validator must still reopen and verify the generated
document rather than trusting the builder.

`build_task17_preinstrumentation_windows.py` now implements this derivation and
supports both direct-file and Python-module CLI invocation. The valid fixture
derives the expected maximum row and complete guard epoch, then passes the
independent validator; moving the only maximum-row commit outside every epoch
makes the builder fail. The pre-instrumentation suite now passes 14 tests, and
the builder, guard, and both resource validators pass 30 focused tests
together. The production command remains gated on terminal independent OSS
closure.

After the source child is terminal, inspect its actual terminal segment document
before choosing a resource validator. Never copy a historical segment ID into
the command. If the terminal segment declares `resource_sample_count > 0` and
the complete strict scheduler/resource fields, validate it with its matching
guard CSV:

```bash
env -u PYTHONPATH /opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/fiber/pipelines/validate_task17_resource_acceptance.py \
  --run-root /Volumes/VAL/STNSNr/summary/spot/.runs/stnsnr_frequency_addon/task17-oss-v1-inclusive-formal-20260719 \
  --segment-id <terminal-instrumented-segment-id> \
  --guard-csv <matching-terminal-segment-guard-csv> \
  --workers 14 \
  --max-rss-bytes 68719476736 \
  --output /Volumes/VAL/STNSNr/summary/spot/acceptance/task17-oss-v1-resource-acceptance-v1.json
```

Do not invoke the pre-instrumentation validator for such a segment. If the
terminal segment lacks the strict instrumentation fields, identify the guard
CSV whose single epoch contains the terminal maximum-row and owning-decision
commits, then generate and validate the bounded pre-instrumentation evidence
with these commands:

```bash
env -u PYTHONPATH /opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/fiber/pipelines/build_task17_preinstrumentation_windows.py \
  --run-root /Volumes/VAL/STNSNr/summary/spot/.runs/stnsnr_frequency_addon/task17-oss-v1-inclusive-formal-20260719 \
  --cache-root /Volumes/VAL/STNSNr/cache/dual_frequency \
  --guard-csv <guard-csv-containing-terminal-maximum-row> \
  --output /Volumes/VAL/STNSNr/summary/spot/acceptance/task17-oss-v1-preinstrumentation-windows-v1.json

env -u PYTHONPATH /opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/fiber/pipelines/validate_task17_preinstrumentation_resources.py \
  --run-root /Volumes/VAL/STNSNr/summary/spot/.runs/stnsnr_frequency_addon/task17-oss-v1-inclusive-formal-20260719 \
  --segment-id <terminal-pre-instrumentation-segment-id> \
  --cache-root /Volumes/VAL/STNSNr/cache/dual_frequency \
  --guard-csv <guard-csv-containing-terminal-maximum-row> \
  --measurement-windows /Volumes/VAL/STNSNr/summary/spot/acceptance/task17-oss-v1-preinstrumentation-windows-v1.json \
  --workers 14 \
  --max-rss-bytes 68719476736 \
  --output /Volumes/VAL/STNSNr/summary/spot/acceptance/task17-oss-v1-preinstrumentation-resource-acceptance-v1.json
```

The selected guard CSV must belong to the declared segment and contain the
required commit envelope; a guard from another segment is invalid even when its
peak appears numerically safe. All validator and builder commands remain
read-only with respect to the run and cache. Their only writes are the named
acceptance documents, each installed atomically and reused only when its bytes
are identical.

The first combined launch must attach the checked-in guard immediately after
the runner PID is known:

```bash
env -u PYTHONPATH /opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/fiber/pipelines/run_task17_resource_guard.py \
  --runner-pid <combined-runner-pid> \
  --output /private/tmp/task17-combined-segment_0001-resource-guard.csv \
  --mount /Volumes/VAL
```

The launch preflight must confirm that the combined root is still absent, so
its first instrumented segment is `segment_0001`. After terminal completion,
run the strict resource acceptance command:

```bash
env -u PYTHONPATH /opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/fiber/pipelines/validate_task17_resource_acceptance.py \
  --run-root /Volumes/VAL/STNSNr/summary/spot/.runs/stnsnr_frequency_addon/task17-combined-v1-inclusive-formal-20260719 \
  --segment-id segment_0001 \
  --guard-csv /private/tmp/task17-combined-segment_0001-resource-guard.csv \
  --workers 14 \
  --output /Volumes/VAL/STNSNr/summary/spot/acceptance/task17-combined-v1-resource-acceptance-v1.json
```

If preflight finds an existing exact combined root, do not assume
`segment_0001`: validate the existing lineage and select only its newly
finished instrumented resume segment. The guard and report names must use that
actual segment ID.

The complete repository-local dual-frequency test directory was then rerun
with the isolated `dual_frequency` and `seed_target_connectivity` package
links and low CPU scheduling priority. All 604 tests passed in 73.104 seconds.
This current-worktree replay includes the new guard and commit-time resource
binding together with every existing cache, resume, jitter, OSS, pPAM,
publication, executor, reporting, and inference test. It used temporary
fixtures and did not inspect the formal run or shared cache.

The first production-plan dry read exposed one serialization boundary in that
validator before it was used for acceptance: persisted
`sensitivity_plan.json` task entries contain the complete `TaskKey` under
`key`, not a redundant top-level `task_id`. The validator must derive
`task_<first-20-hex-of-canonical-key-SHA256>` from that exact key and compare it
with the corresponding task document. A fixture that uses only synthetic
top-level task IDs is insufficient. Focused coverage now uses the production
plan shape and rejects a task document whose derived identity differs. A
read-only audit of the active production plan derived 590 unique IDs and found
590 task documents with no missing or mismatched identity.
The same serialized-plan rule applies to
`validate_task17_resource_acceptance.py`; the later instrumented combined
lineage cannot be accepted by a fixture-only top-level identity convention.
Both resource validators must share the exact canonical `TaskKey` derivation
and production-shaped mismatch coverage before combined execution begins.
They now do: the strict and pre-instrumentation focused suites pass 12 tests,
including an identity-mismatch rejection for each validator.

An older immutable `sensitivity_plan.json` may omit the later scheduler-only
task fields `timeout_seconds`, `transient_safe`, and
`max_transient_retries`. Resume comparison interprets those omissions only as
the exact defaults `null`, `false`, and `0`. This is a narrow v1 compatibility
normalization: the persisted file is not rewritten, and any non-default
scheduler value or any remaining structural or scientific difference still
rejects resume. The production OSS plan comparison covers all 590 tasks and is
identical after removing only those omitted defaults. The compatibility tests
and complete 613-test package regression pass, and the production plan file is
byte-identical before and after the compatibility check.

The later combined lineage starts under the instrumented code and must use the
strict validator with its own terminal segment and guard CSV, the same limits,
and a distinct acceptance report. A running or pre-instrumentation segment
cannot pass.

The first atomic scientific boundary published by `segment_0010` increased the
shared cache from 70 to 72 OSS row manifests and from 35 to 36 equivalence
decisions. Decision
`708a2add852860f390cb6e5a581dbfbfe2af15d6b3b7258a20da37547568c550`
belongs to reference group `oss_axis_group_078d3c2f2b8ac612a268` and passed
with maximum probability difference 0, state mismatch count 0, and activation
count mismatch count 0. The runner then started the next retained row pair, so
36 decisions are a durable progress boundary rather than terminal reference
gate closure. At this boundary VAL remained writable, used swap was below the
segment baseline, and the observed process tree remained within the frozen
resource limits.

The next atomic boundary increased the cache to 74 OSS row manifests and 37
equivalence decisions. Decision
`bb1a194270afce27209b47b9e7fb0aa194d7cbdc2e48ff4788182f129d968013`
belongs to the same reference group and passed with maximum probability
difference 0, state mismatch count 0, and activation count mismatch count 0.
Its final and Omega row identities are
`6243614a27b94af71e53cc0135db3c23f0f7bf80920927908da3dbce09066a38`
and `73b76a4e99733607db184a32030e280001a5a820a7801e4729e68e853f4a3a16`.
The runner immediately entered the next missing physical pair; therefore 37
decisions remain a durable progress boundary, not reference gate closure.
Used swap remained below the segment baseline.

The retained 590-task DAG gives an exact downstream acceptance census. The
196 immutable parent tasks comprise 28 reference input, preparation, and final
triplets plus 28 add-on input, preparation, delta-reference, and final
quartets. The two equivalence gates control the remaining 392 tasks: 56
observed pPAM workspaces, 56 deterministic permutation schedules, 224
permutation blocks with four blocks per endpoint, and 56 terminal activation
aggregates. After both gates complete, resume must replace every one of these
392 historical dependency-skips with terminal execution outcomes. Independent
OSS acceptance therefore checks these service-level counts in addition to the
590-task total; a completed manifest with any retained dependency-skip is not
acceptable.

A fresh task-store census during `segment_0010` on 2026-07-22 reconfirmed this
exact blocked baseline. All 392 skipped tasks belong to the four downstream
services and no other service is skipped: 56 observed workspaces, 56 schedules,
224 fixed permutation blocks, and 56 aggregates. Exactly 28 observed
workspaces cite the reference gate as their direct failed dependency and 28
cite the add-on gate; every later skip cites its endpoint-local workspace,
schedule, blocks, or aggregate dependency chain. This gives resume an exact
before-state. Terminal independent-OSS acceptance must re-evaluate all 392 and
must find no retained historical dependency-failure skip.

A concurrent canonical-publication audit at this checkpoint confirmed that the
support-preserving jitter execution is terminal `completed` in both the
direct-voxel and normative-fiber extension-v1 mirrors, with 56 endpoint rows in
each domain. A deeper artifact-index audit showed that these v1 mirrors are not
yet canonical scientific publications: their artifact rows retain
`file://.../.runs/.../work/...` URIs and their endpoint documents carry artifact
IDs rather than publication-local payload paths. They therefore fail the
public-only postprocess boundary and cannot count as completed canonical jitter
publication. The final-in-sample v2 replay publisher is self-contained, but its
current implementation is specialized to final-in-sample artifacts.

Task 17 must generalize the replay publisher to completed jitter, OSS, and
combined lineages after formal execution. The v2 publication must copy or
transactionally replay every declared scientific payload below the extension
root, write publication-relative artifact-index rows with verified byte counts
and SHA-256 values, bind the completed child and immutable parent manifests,
reject every `.runs`, `tasks`, `work`, or `runtime_work` URI as a public input,
and commit the completed extension manifest last. Repeating an identical replay
must be idempotent. The independent OSS extension is also not yet a usable
publication: no direct-voxel OSS extension exists, while the normative-fiber
OSS v1 mirror retains the historical `failed` status and a header-only artifact
index from the interrupted lineage. Resume must publish neither domain until
both axis-equivalence groups, all downstream pPAM tasks, reporting, and the run
manifest reach an unqualified completed state.

A compact payload-level audit on 2026-07-21 checked all 112 completed jitter
endpoint tasks before implementing that generalized replay. The four service
families each contributed 28 artifacts, and the complete 221.65-MiB payload set
had no missing file or SHA-256 mismatch. Every artifact retained all 1000
ordered replicate records. Its `completed_replicates` value matched the number
of replicate rows carrying technical status `complete`; non-computable rows
remained explicit records with their reason and support status rather than
being dropped. All 56 reference endpoints retained 1000 complete replicates.
The six adjusted add-on voxel endpoints each retained 119 complete and 881
non-computable replicates, while the four adjusted add-on fiber endpoints each
retained 867 complete and 133 non-computable replicates. The other 46 add-on
endpoints retained 1000 complete replicates.

A no-payload-reread combined preflight on 2026-07-22 validated all 240
completed physical-block task references from jitter v8. They resolve to 240
unique `jitter_exposures` semantic identities, split into six physical groups
with forty fixed blocks each. Every small reference document matched its
recorded SHA-256 value; every cache manifest was completed, matched its
semantic directory, and had exact declared non-AppleDouble file closure and
byte counts. The large payload SHA values were deliberately not reread while
independent OSS was active. The new combined process must perform the normal
first-use full cache verification before reuse, which supplies the authoritative
payload-SHA acceptance without competing I/O in this preflight.

The same audit resolved every jitter `target_id` against the 112 canonical
published `final_model.json` documents and found no target, service family,
selected tau, Coverage, model-role, or realized-branch mismatch. This v8
realization contains 28 reference and 28 add-on endpoints in each modality,
with 22 no-delta and six adjusted add-on voxel branches plus 24 no-delta and
four adjusted add-on fiber branches. The final-model documents happen to
resolve every voxel endpoint to tau 200 and Coverage 5 and every fiber endpoint
to tau 400 and Coverage 5. These values are replayed from each final-model
identity and must never become publisher defaults or modality-wide hard-coded
assumptions. This audit establishes that the retained jitter payloads are
complete inputs for a self-contained v2 replay; it does not turn the current v1
mirrors into canonical publications.

The generalized extension-v2 replay uses the following stable public layout.
It projects only terminal endpoint-level scientific records. Jitter block
payloads, pPAM schedules, pPAM block nulls, operator scratch, leases, and other
execution-only intermediates remain in the run or shared cache and are never
public inputs.

```text
<model-set-root>/extensions/<extension-id>/
  <scale-id>/<reference-or-addon>/sensitivity/
    spatial_jitter/
      spatial_jitter_metrics.json
      result.json
      status.json
    oss_ppam/
      <artifact-kind>.<source-extension>
      <artifact-kind>.<source-extension>.metadata.json
      result.json
      status.json
  spatial_jitter_results.json
  spatial_jitter_results.csv
  oss_ppam_results.json
  oss_ppam_results.csv
  artifact_index.csv
  extension_manifest.json
```

Each endpoint `result.json` lists publication-relative payload paths, SHA-256,
byte count, schema, axis, units, space, final-model identity, actual selected
tau and Coverage, realized branch, source child run, and immutable parent run.
The published payload name is derived from the validated artifact kind and the
source file extension; no task ID, attempt ID, source basename, or run-store URI
enters the public name. The root JSON and CSV files contain one compact row per
terminal endpoint and analysis. They do not duplicate replicate vectors or
arrays.

Spatial jitter publishes the one terminal `SensitivityResult` payload for each
of all 112 endpoints. OSS publishes the transitive public payload closure of
each terminal `ActivationArtifact`: activation probability, binary exposure,
public observed arrays, support and comparison documents, final permutation
null and summary, and terminal OSS status. Internal workspace and block records
are excluded. Independent OSS is normative-fiber-only and therefore creates no
empty direct-voxel extension. A combined child publishes spatial jitter in both
domains and OSS only in the normative-fiber domain. The manifest records the
analyses and result count actually present in each domain.

An unfiltered replay may commit terminal status `completed` only after every
expected endpoint for every requested analysis is present, copied, indexed,
and verified. A scale-filtered smoke replay records a partial publication scope
and cannot be accepted by public-only postprocess. The writer installs payloads
and metadata first, root aggregates next, `artifact_index.csv` after all rows,
and `extension_manifest.json` last. Repeating the same replay verifies and
reuses identical bytes. Any collision, missing result, failed task, digest
mismatch, parent mismatch, unsupported record type, or path escape leaves the
fragment nonterminal and preserves the source run and caches.

Implementation acceptance for this replay requires focused fixtures for a
complete jitter endpoint, a complete OSS `ActivationArtifact`, an OSS technical
failure, a combined child, and a final-in-sample regression. The tests must
prove deterministic public names, complete artifact closure, domain-specific
analysis presence, exact parent/final-model binding, partial-scope rejection by
postprocess, idempotent same-byte resume, immutable-collision rejection,
missing-payload rejection, failed-task rejection, digest rejection, and absence
of every run-store path in payload metadata, endpoint documents, indexes, and
manifests. A real replay of the completed v8 jitter child must then publish 56
direct-voxel and 56 normative-fiber results, verify all 112 endpoint payloads
and their 1000 retained replicate rows, and reproduce the branch and
complete-versus-non-computable counts recorded above without rerunning a
physical block or endpoint statistic.

Local implementation evidence on 2026-07-22 adds the generalized terminal
extension replay to `CanonicalPublisher.publish_extension`. A child without a
final-in-sample aggregate now dispatches to a v2 jitter/OSS replay that requires
a completed run and aggregate, exact parent identity, completed terminal tasks,
matching endpoint/final-model identities, and valid source digests. Jitter
copies the terminal `SensitivityResult` closure. OSS copies activation
probability, binary exposure, and the complete `ActivationArtifact` closure and
rejects a technical-failure status. Public filenames derive only from validated
artifact kinds and source extensions. Endpoint documents, root aggregates,
relative artifact indexes, and domain-specific manifests contain no source
URI; an independent OSS child creates no empty direct-voxel extension. A
selected-scale replay commits `completed_partial`, while only an unfiltered
replay may commit `completed`.

Synthetic fixtures now cover self-contained jitter replay, same-byte
idempotence, domain-specific combined replay, normative-fiber-only OSS,
technical-failure rejection, and absence of run-store paths. The complete
dual-frequency suite passed 541 tests plus 310 subtests. A read-only real-data
smoke used the completed v8 jitter child and a temporary parent publication
under `/private/tmp/task17-extension-v2-smoke2.QDHdBq`. It published both
reference and add-on PDQ-39 endpoints in each modality, four terminal results
in total, with every payload retaining 1000 replicate rows. Repeating the
identical replay reused every byte. The direct-voxel and normative-fiber
manifests both correctly recorded `completed_partial`; scans found no
`file://`, `.runs`, `tasks`, `work`, or `runtime_work` path in any public JSON
or CSV. This proves the isolated replay path but does not replace the required
unfiltered 112-endpoint canonical jitter publication or later OSS/combined
production publications.

The required unfiltered read-only replay was then completed under
`/private/tmp/task17-jitter-v8-full-v2.Fo5fqs`. It published 56 direct-voxel
and 56 normative-fiber terminal endpoints. Each domain contains 170 indexed
artifacts, and every indexed path, byte count, and SHA-256 digest passed
verification. All 112 metrics payloads retain exactly 1000 replicate rows.
The direct-voxel closure contains 28 complete reference endpoints, 22 complete
no-delta add-on endpoints, and six adjusted add-on endpoints with 119 complete
and 881 non-computable replicates each. The normative-fiber closure contains
28 complete reference endpoints, 24 complete no-delta add-on endpoints, and
four adjusted add-on endpoints with 867 complete and 133 non-computable
replicates each. Both manifests record `completed` with complete publication
scope. A recursive public JSON and CSV scan found no run-store or runtime-work
path. This accepts the implementation and real-data replay boundary; the
temporary replay is not the formal canonical publication, which remains
blocked on completion of the independent OSS and combined lineages.

The focused publication suite was rerun on 2026-07-22 and passed all 15 tests.
This current regression evidence preserves the generalized v2 replay contract
while the independent OSS lineage remains active; it is not evidence that the
pending canonical OSS or combined publications already exist.

A later joint replay on the same date passed 22 publication and formal
postprocess component tests. It reconfirmed self-contained and idempotent
terminal extension replay, domain-specific combined analysis presence,
normative-fiber-only OSS publication, technical-failure rejection, component
resume, immutable requests, and terminal output closure. The replay used only
temporary local fixtures and did not read, mutate, or substitute for the active
formal OSS lineage.

The canonical replay target IDs are frozen before the live lineages finish.
The completed jitter child publishes as
`task17-jitter-v8-support-preserving-formal-20260719-v2` in both domain model
sets. The independent OSS child publishes as
`task17-oss-v1-inclusive-formal-20260719-v2` only in the normative-fiber model
set. The combined child publishes as
`task17-combined-v1-inclusive-formal-20260719-v2` in both model sets, with
jitter in both domains and OSS only in normative fiber. These names follow the
terminal-sensitivity publisher default of appending `-v2` to the source child
run ID. Existing same-run directories without `-v2` are automatic v1 mirrors;
the current OSS mirror is terminal `failed`. The jitter v2 target is now a
self-contained canonical publication. The OSS and combined v2 targets remain
pending, may not be replaced by their automatic v1 mirrors, and must not
satisfy the canonical extension or public-only postprocess gate.

Run each unfiltered canonical replay only after its own source lineage is
terminal and independently validated, using the locked repository environment:

```bash
env -u PYTHONPATH /opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/fiber/pipelines/run_dual_frequency_models.py publish-extension \
  --run-root /Volumes/VAL/STNSNr/summary/spot/.runs/stnsnr_frequency_addon/task17-jitter-v8-support-preserving-formal-20260719

env -u PYTHONPATH /opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/fiber/pipelines/run_dual_frequency_models.py publish-extension \
  --run-root /Volumes/VAL/STNSNr/summary/spot/.runs/stnsnr_frequency_addon/task17-oss-v1-inclusive-formal-20260719

env -u PYTHONPATH /opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/fiber/pipelines/run_dual_frequency_models.py publish-extension \
  --run-root /Volumes/VAL/STNSNr/summary/spot/.runs/stnsnr_frequency_addon/task17-combined-v1-inclusive-formal-20260719
```

Do not pass `--scale`, `--extension-id`, or `--output-root` for these formal
replays. Omitting `--scale` requires complete plan closure; omitting
`--extension-id` selects the frozen child ID with the `-v2` suffix; omitting
`--output-root` binds the completed parent model-set roots from the resolved
configuration. Each command must be repeated once after its first successful
publication to prove same-byte idempotent resume, followed by a complete
manifest, artifact-index, payload SHA-256, parent-binding, and forbidden-path
audit before postprocess may consume the extension.

The audit is repository-owned and repeatable rather than an ad hoc shell
inspection. `validate_task17_extension_publication.py` accepts one completed
source child plus one or more extension-v2 roots and performs no writes unless
an explicit report path is provided. For every root it requires a terminal
`completed` v2 manifest, complete publication scope, an extension ID matching
the directory name, and a completed parent model manifest whose bytes match
the declared SHA-256. The source child manifest must be terminal, match the
declared source run and SHA-256, and carry the same parent run and scientific-
configuration identities as the extension. The CSV index must contain unique
safe relative paths, terminal rows, valid byte counts and SHA-256 values, and
exact closure over every regular publication file except the index and manifest
themselves and filesystem-generated AppleDouble or `.DS_Store` sidecars. The
validator hashes every indexed payload, checks aggregate result counts and
analysis families against the manifest, and rejects `file://`, `.runs`,
`tasks`, `work`, or `runtime_work` text in public JSON and CSV metadata. It
emits one deterministic JSON summary per root; an explicit report uses atomic
same-byte publication and refuses a changed collision. Focused fixtures cover
a valid extension, payload corruption, an unindexed file, parent-manifest
drift, source-child drift, and a forbidden run-store path. The accepted
jitter-v2, later OSS-v2, and later combined-v2 roots must all pass this same
command.

The validator is implemented with six focused fixtures. They cover a valid
complete extension, atomic same-byte report reuse and changed-report
rejection, payload corruption, an unindexed payload, parent-manifest drift,
source-child drift, and forbidden run-store text after otherwise valid
reindexing. The complete dual-frequency regression passes 573 tests under
Conda `leaddbs`. Real jitter-v2 validation is intentionally ordered after the
active independent OSS solver releases VAL bandwidth; the validator itself
does not weaken the requirement to hash every indexed byte.

The frozen jitter-v2 invocation is:

```bash
env -u PYTHONPATH /opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/fiber/pipelines/validate_task17_extension_publication.py \
  --source-run /Volumes/VAL/STNSNr/summary/spot/.runs/stnsnr_frequency_addon/task17-jitter-v8-support-preserving-formal-20260719 \
  --extension-root /Volumes/VAL/STNSNr/summary/spot/direct_voxel/dual_frequency_four_model_v1/extensions/task17-jitter-v8-support-preserving-formal-20260719-v2 \
  --extension-root /Volumes/VAL/STNSNr/summary/spot/normative_fiber/dual_frequency_four_model_v1/extensions/task17-jitter-v8-support-preserving-formal-20260719-v2 \
  --output /Volumes/VAL/STNSNr/summary/spot/acceptance/task17-jitter-v8-extension-v2-validation-v1.json
```

After each source child has been published twice with its frozen unfiltered
`publish-extension` command, validate OSS-v2 and combined-v2 with:

```bash
env -u PYTHONPATH /opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/fiber/pipelines/validate_task17_extension_publication.py \
  --source-run /Volumes/VAL/STNSNr/summary/spot/.runs/stnsnr_frequency_addon/task17-oss-v1-inclusive-formal-20260719 \
  --extension-root /Volumes/VAL/STNSNr/summary/spot/normative_fiber/dual_frequency_four_model_v1/extensions/task17-oss-v1-inclusive-formal-20260719-v2 \
  --output /Volumes/VAL/STNSNr/summary/spot/acceptance/task17-oss-v1-extension-v2-validation-v1.json

env -u PYTHONPATH /opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/fiber/pipelines/validate_task17_extension_publication.py \
  --source-run /Volumes/VAL/STNSNr/summary/spot/.runs/stnsnr_frequency_addon/task17-combined-v1-inclusive-formal-20260719 \
  --extension-root /Volumes/VAL/STNSNr/summary/spot/direct_voxel/dual_frequency_four_model_v1/extensions/task17-combined-v1-inclusive-formal-20260719-v2 \
  --extension-root /Volumes/VAL/STNSNr/summary/spot/normative_fiber/dual_frequency_four_model_v1/extensions/task17-combined-v1-inclusive-formal-20260719-v2 \
  --output /Volumes/VAL/STNSNr/summary/spot/acceptance/task17-combined-v1-extension-v2-validation-v1.json
```

Independent OSS passes only its normative-fiber root; combined passes both
domain roots.

The completed jitter lineage was replayed on 2026-07-22 with the first command
above. It created
`direct_voxel/dual_frequency_four_model_v1/extensions/`
`task17-jitter-v8-support-preserving-formal-20260719-v2` and the matching
`normative_fiber` extension. Each domain manifest is terminal `completed`,
binds parent run `task17-main-v8-tau-grid-formal-20260717`, records complete
publication scope, and contains 56 results. Each artifact index contains 170
relative rows with no absolute path, parent traversal, or `.runs` reference.
The identical replay returned the same 56 plus 56 result closure while both
manifest modification times and byte sizes remained unchanged. This accepts
the self-contained and idempotent canonical jitter-v2 publication. A separate
digest audit recomputed the source child `run_manifest.json` SHA-256 and the
domain-specific parent `model_manifest.json` SHA-256; all four comparisons
matched the identities recorded by the two extension manifests. Independent
OSS execution, OSS-v2 publication, combined execution, and combined-v2
publication remain open.

A read-only threshold audit during the same running segment confirmed that the
formal resolved YAML contains the requested voxel tau grid of 150, 180, 200,
220, 250, and 300 with pre-specified tau 200, and the requested fiber tau grid
of 200, 350, 400, 450, 600, and 800 with pre-specified tau 400. Both use the
configured Coverage grid beginning at 5, every normative connectome records a
fold candidate minimum of 1, and the runtime uses inclusive tau, Coverage, and
reference-overlap predicates. The active pPAM runtime remains correct:
`binary_activation` applies strict `p(A) > 0.5`, so probability exactly 0.5 is
inactive. One source-YAML comment and two add-on overlap test expectations still
describe the superseded inclusive pPAM boundary. They do not enter the resolved
scientific payload or the running calculation, but they must be corrected and
the complete test gate rerun after formal execution, before final acceptance.

The stale source comments and fixtures were corrected on 2026-07-22 without
changing runtime scientific code. Both production and test normative-fiber
YAML now state the strict `I[p(A) > 0.5]` rule, both add-on overlap fixtures use
the strict boundary, and the synthetic activation helper follows the same
contract. The three direct semantic tests for the exact half-threshold and the
two overlap paths passed. A later full-suite audit showed that synthetic
orchestration tests were inheriting live host availability while the formal
solver held memory. Those pure in-memory fixtures now freeze a 128-GiB test
memory state, while dedicated ledger tests retain the production 48-GiB charge,
64-GiB ceiling, and reserve predicates. The complete 545-item dual-frequency
suite then passed while formal OSS remained active; no production admission
rule was relaxed.

A later all-path threshold scan found one residual diagnostic mismatch in the
cheap plain-fiber control: candidate construction already included tau, but
its per-subject touched count excluded values exactly at tau. The implementation
now excludes only values below tau, matching the main model, bootstrap, jitter,
DeltaReferenceScore support, and Coverage contracts. The direct-voxel and
normative-fiber support-QC documentation was corrected to the same inclusive
boundary. Four focused fiber-control boundary tests passed, including an exact
tau fixture. This diagnostic fix does not alter the active independent OSS
calculation or any parent final-model identity.

The consolidated inclusive-boundary gate then passed eight exact fixtures
across direct voxel, normative fiber, formal permutation, continuous-dose
support, plain touched counts, add-on reference overlap, and both
DeltaReferenceScore support paths. Coverage and overlap scans found no
remaining strict comparison against their configured minimum. This acceptance
uses boundary-valued synthetic inputs rather than inferring semantics from a
production result that may contain no exact-threshold value.

The current-worktree boundary replay was broadened on 2026-07-22 and passed 11
tests plus three subtests. It directly covers direct-voxel and normative-fiber
tau and Coverage equality, add-on reference-overlap equality, the exact
inclusive minimum-grid `Omega_max` union, both DeltaReferenceScore support
directions, continuous-dose support, strict adequate-support cutoffs, and
strict pPAM activation at `p(A) > 0.5`. This confirms that equality is included
only for the three configured exposure/coverage/overlap minima and remains
excluded for support-QC and pPAM rules. No production YAML or running
scientific identity changed during this replay.

Formal OSS progress evidence on 2026-07-22 reached 76 immutable row entries
and 38 equivalence decisions in the reference group. Decision
`4afb7c51694354cff528d04e8835ba1061d7d7551476f45ad7e0700ad6d87589`
passed with zero maximum probability difference, zero state mismatch, and zero
activation-count mismatch. Its final-axis row contains 3401 canonical fibers
and its `Omega_max` row contains 10320 canonical fibers. Both referenced row
manifests contain exactly `fiber_ids.npy`, `probabilities.npy`, and
`row_metadata.json`; all six files matched their declared byte counts and
SHA-256 values. This is an intermediate durable boundary rather than terminal
gate acceptance. The reference gate remains active, the add-on gate and all
dependency-skipped downstream pPAM tasks remain open, and no fixed expected
decision count may replace the gate's final `row_decision_ids` closure.

The next atomic boundary raised the cache to 78 row entries and 39 decisions.
Decision
`647399afb5cde4c9d84ff8ce73bd7df0e40fbffbed0baaf9f2de385f01f69dd5`
also belongs to the reference group and passed with zero maximum probability
difference, zero state mismatch, and zero activation-count mismatch. Its final
and `Omega_max` row identities are
`8ed8e424cd624431e80bc79982b041bf64d96e92d21a8a2f9c69a37d7657fbc3`
and `a591aad308040f4f4d8b89e8cf3ef94a94e84808f12996bdc68a21b0f5a3b06c`.
Each manifest contains the same exact three-file closure, and all six payloads
matched their declared SHA-256 values and byte counts. The worker then entered
the next physical row, so this remains intermediate rather than terminal gate
evidence.

The following atomic boundary raised the cache to 80 row entries and 40
decisions. Decision
`176ced1f6e17c0eb60d077c2cb67e981af30a54c3775360c289a38210091eb42`
belongs to the same reference group and passed with zero maximum probability
difference, zero state mismatch, and zero activation-count mismatch. Its final
row identity is
`cf9e986decf8156fa724b62e80effa1582a143e4d9119d9e553f145e7e1a9fca`;
its `Omega_max` row identity is
`ff88c4a32a776fee94a797c46b079684cac6ab40ef42cd3789a14eb472d33515`.
The production `ContentAddressedCache.resolve_identity` path reread and
validated the decision plus both row entries. Each row contains exactly
`fiber_ids.npy`, `probabilities.npy`, and `row_metadata.json`; manifest
identity, complete descendant closure, file size, array structure, and every
payload SHA-256 passed. This remains an intermediate boundary until the
reference gate commits its authoritative `row_decision_ids` closure.

The next complete multi-chunk row pair raised the cache to 82 row entries and
41 decisions. Decision
`4a527104355d834071663daff1bfb0bd86aba7eea14d91c069579ec7254967dc`
belongs to the same reference group and passed. Its final row identity is
`0bddc501d323f8bcae91d24fc178191cbd0cbcdcc8977bbda2f227d388cd8bc0`
with 3401 fibers; its `Omega_max` row identity is
`1c4c904c045d87f18f86b80d4d418bda6d3459f12e3a0fadbfb6bb22699f1c22`
with 10320 fibers. Production `resolve_identity` validation passed the decision
and both row entries, exact three-file row closure, every byte count and
SHA-256, NPY dtype and shape metadata, ordered unique fiber IDs, finite
probabilities within the closed unit interval, and row metadata identity. An
independent final-to-`Omega_max` ID mapping recomputed maximum probability
difference 0 and strict `p(A) > 0.5` state mismatch count 0. The one-second
segment guard observed a task-tree RSS peak of 48970170368 bytes, therefore
`< 64 GiB`, while swap stayed at its 6844978299-byte guard baseline. The worker
then entered the next physical row, so terminal gate closure remains open.

The next durable boundary raised the cache to 84 row entries and 42 decisions.
Decision
`d56e76a44e9171c4580052bf6e186be0a8fb7bf3e1c7d8661f1408ade14dea15`
belongs to the reference group and passed with zero maximum probability
difference, zero state mismatch, and zero activation-count mismatch. Its final
row identity is
`a8b1a110f20ae2ca16b9a1d51d60ddf9adc1afd0a3b99f63bc54144e907de366`;
its `Omega_max` row identity is
`0343af9f828bff3d877f78bac31d5e4a9709c246ab4e4b57b8d2e1659a517e35`.
The persisted decision status is `pass`. This is still intermediate evidence:
the authoritative count and closure come only from the terminal reference gate
and later add-on gate, not from a predicted decision total.

The next durable boundary raised the cache to 86 row entries and 43 decisions.
Decision
`8070064e4442c8252efd70de0cc65b1aa43c1885f7ac3a1b7249d42d726141d9`
belongs to the same reference group and passed with zero maximum probability
difference, zero state mismatch, and zero activation-count mismatch. Its final
row identity is
`a0df680339a905aea7557a55465201ef063fac603ba2dcce7497358627a20daa`
with 3401 fibers; its `Omega_max` row identity is
`f47b8669550f77d0e56b62a56799fe8a994536046ef920344289818439b9c137`
with 10320 fibers. A fresh byte-level audit verified the exact three-file
closure of each row, every stored size and SHA-256, matching one-dimensional
array shapes, and finite probability values. The segment guard peak remains
48970170368 bytes, therefore `< 64 GiB`, and its current-epoch swap value has
not grown. The reference gate remains running, so this evidence does not infer
or replace its terminal ordered closure.

A current-input audit of the running reference attempt found 34 unique
materialized source-parameter, geometry, and source-locator triplets. This is
not the gate decision denominator. Production constructs final-axis and
`Omega_max` producer requests for every endpoint, verifies that their physical
keys match, and then deduplicates them by `_physical_row_key`; only the
terminal `OSSAxisEquivalenceGroupRecord.row_decision_ids` records that ordered
closure. The shared cache also retains valid decisions from earlier attempts
and toolchain/request identities, so its cumulative decision-directory count
can exceed or differ from the current closure. Monitoring and completion must
therefore continue to use the terminal group record plus its two-row decision
closure, never the cumulative cache count or the 34 materialized triplets as a
predicted total.

At the scheduled 2026-07-22 21:26 PDT checkpoint, the active reference group
had durably published 48 pass decisions and 96 corresponding standard row
manifests. The newest decision retained zero state mismatch, zero
activation-count mismatch, and zero maximum probability difference. The
runner and one solver remained live. Task-tree RSS was 38257524736 bytes with
a segment peak of 46511964160 bytes, both below the 64-GiB ceiling. Swap was
5169280451 bytes against the 6794646651-byte segment baseline and therefore
had not grown. The task ledger remained at 196 completed, one running
reference gate, one historical failed add-on gate, and 392 dependency-derived
skips. This is progress evidence only; the reference group still lacks its
terminal authoritative closure.

A process-only audit at 2026-07-22 21:44 PDT confirmed that the formal runner,
its persistent worker, one OSS-DBS solver child, and the local one-second
resource guard were all live. This audit did not traverse the shared cache or
advance the scheduled two-hour durable-progress poll. The guard remains a
local process safeguard rather than a model-driven monitoring turn.

At the scheduled 2026-07-22 23:26 PDT checkpoint, the active reference group
had durably published 50 pass decisions and 100 corresponding row manifests.
The newest decision is
`8e231e4c5b32942b45963bfcec597f289dc4580d57f1057cc7c56b21fd32ac90`;
its final and `Omega_max` row identities are
`c5283d6064d450982f1b274636be86367ceab5863793ee92528f28403d98588a`
and
`97beab6dcc45bb7a3c45a31214dd001f6513bf86a76747bd09084cbea304fd3f`.
It passed with maximum probability difference 0, state mismatch count 0, and
activation-count mismatch count 0. All 50 cumulative decisions still belong
to `oss_axis_group_078d3c2f2b8ac612a268`; the reference gate remains running
and has not published its authoritative closure. The 590-task ledger remains
196 completed, one running reference gate, one historical failed add-on gate,
and 392 dependency-derived skips. Runner PID 15265, persistent worker PID
15357, and one solver child were live. A one-second process sample measured
100.2 percent task-tree CPU and 2607742976 bytes RSS. The current external
guard epoch contains 27076 samples, observed a 46511964160-byte peak
`< 64 GiB`, and swap growth `< 1` byte. The write probe passed. This is
intermediate progress only.

At the scheduled 2026-07-23 01:26 PDT checkpoint, the reference cache had
advanced to 52 passing decisions and 104 corresponding row manifests. The
newest decision is
`274860a37f3f8be9eb4467124a8500d31ffa2dad562e325c55c7de7f69ebbbe2`;
its final and `Omega_max` row identities are
`eae532a17f837266f1842f867242c8e92abf9709a4f63ac4bc98c28469437c2e`
and
`fdeda5113449db405c55d1ed6a549b183585cf9e6f7e1e48af0124cbde68efa5`.
Every cumulative decision still belongs to
`oss_axis_group_078d3c2f2b8ac612a268` and has pass status, zero state mismatch,
zero activation-count mismatch, and zero maximum probability difference. The
reference gate remains running; the add-on gate retains its historical failed
state; and the ledger remains 196 completed, one running, one failed, and 392
dependency-derived skips.

The VAL write probe passed. The process tree was live at 98.7 percent aggregate
CPU and 14787035136 bytes RSS; no `run_pathway_activation` child happened to
exist in that one snapshot, which is not interpreted as a stopped gate. The
append-only guard contained 37524 samples across four detected epochs, current
RSS 14787035136 bytes, peak RSS 55017013248 bytes, current swap 5152503235 bytes
against the 6794646651-byte current baseline, and an ordinary final `sample`
event. The global stream's largest adjacent timestamp gap was approximately
814.41 seconds. That value may span a guard restart boundary and does not by
itself invalidate a later single-epoch window, but it exposes a missing
window-level continuity gate.

At the scheduled 2026-07-23 03:26 PDT checkpoint, collected at 03:32 PDT after
the quiet monitoring boundary, the same reference cache had advanced to 54
passing decisions and 108 corresponding row manifests. The newest decision is
`370b60b653eee199771b85b16bb2fd8f8a31a8c08d9af3a6172e0a25684646c1`;
its final and `Omega_max` row identities are
`31b28e0484f913e56fb43d87e51e250b1f304597efae896e4c019bf0b3d3f051`
and
`ec2eab4207984a58bf3615e27b73a99bc21a682295ec3aebbc49a88fde4111a4`.
The final row contains 3401 fibers and the `Omega_max` row contains 10320
fibers. Fresh validation passed each cache manifest, exact file closure, byte
count, SHA-256 value, NPY dtype and shape, ordered unique positive fiber IDs,
finite probability range, and the exact final-to-`Omega_max` ID subset. An
independent probability and strict `p(A) > 0.5` replay found maximum
probability difference 0 and state mismatch count 0, agreeing with the
persisted pass decision and its zero activation-count mismatch.

All 54 cumulative decisions still belong to
`oss_axis_group_078d3c2f2b8ac612a268` and have pass status. The authoritative
reference closure remains unavailable because its gate is still running; the
historical add-on gate remains failed until resume reaches it. The 590-task
ledger therefore remains 196 completed, one running, one historical failed,
and 392 dependency-derived skips. VAL remained mounted and writable. Runner
PID 15265, persistent worker PID 15357, the guard, and one solver child were
live. A bounded snapshot measured 33418461184 bytes of task-tree RSS. The
append-only guard's recorded peak remained 55017013248 bytes, therefore
`< 64 GiB`, and neither detected baseline epoch had positive swap growth. The
guard stream contains ordinary sample events only. Its two startup regions
contain isolated approximately 63.81-second and 69.81-second adjacent gaps;
these cannot support an accepted maximum-row window, while the existing
window-local `< 5`-second validator remains the authority for final resource
acceptance. This checkpoint proves forward progress but not gate completion.

At the next scheduled boundary, collected at 2026-07-23 05:45 PDT, the
reference cache had advanced again to 56 passing decisions and 112
corresponding row manifests. The newest decision is
`0b5859facf29add5241ab82d014184bee168329fd619525843334b947e34a786`;
its final and `Omega_max` row identities are
`0e49a200327dacf6050a0d149f3b87b65a6ceb081df47fc9384ed447c91d7684`
and
`cd87d0884e43c1aa5a9274c9bb727a56ea4e2c4bfbff6eb817c14ef361294f5a`.
Fresh byte-level validation passed both row manifests and the decision
manifest, exact file closure, byte count, SHA-256, NPY dtype and shape, ordered
unique positive fiber IDs, finite probability range, and exact canonical-ID
subset mapping. The final row contains 3401 fibers and the `Omega_max` row
contains 10320 fibers. Independent replay found maximum probability difference
0 and strict `p(A) > 0.5` state mismatch count 0, agreeing with the persisted
pass decision and its zero activation-count mismatch.

All 56 cumulative decisions remain passing members of
`oss_axis_group_078d3c2f2b8ac612a268`. The reference gate is still running and
has not committed its authoritative closure, so the task ledger remains 196
completed, one running, one historical failed, and 392 dependency-derived
skips. VAL remained mounted and writable. Runner PID 15265, persistent worker
PID 15357, the guard, and an active `run_pathway_activation` child were live.
The bounded process snapshot measured 2821275648 bytes RSS and 82 percent
aggregate CPU. The guard contained more than 52000 samples, recorded a new
task-tree peak of 62493573120 bytes that remains `< 64 GiB`, and retained
positive swap growth `< 1` byte in both detected baseline epochs. This is
continued intermediate progress only.

At the following scheduled boundary, collected at 2026-07-23 08:08 PDT, the
reference cache had advanced to 58 passing decisions and 116 corresponding row
manifests. The newest decision is
`c2738d1d543088383e0aa04ab7edd31b0dbf0a6299f1eee16516ac6e4e10158d`;
its final and `Omega_max` row identities are
`235a3388fc7c55355442eefeda947bacfc9e4711045ce2b80b5e08cfbeba4107`
and
`2724e4922d882f87fe081131a839465111a68d8fd550173e64fc339d44f25473`.
Fresh validation again passed the decision and both row manifests, exact file
closure, byte count, SHA-256, array dtype and shape, ordered unique positive
fiber IDs, finite probability range, and the exact final-to-`Omega_max`
canonical-ID subset. The final row contains 3401 fibers and the `Omega_max` row
contains 10320 fibers. Independent replay found maximum probability difference
0 and strict `p(A) > 0.5` state mismatch count 0, agreeing with the persisted
pass status and zero activation-count mismatch.

All 58 cumulative decisions remain passing members of the reference group.
The reference gate still has not committed its terminal `row_decision_ids`
closure, so the 590-task ledger remains 196 completed, one running, one
historical failed, and 392 dependency-derived skips. VAL remained mounted and
writable. Runner PID 15265, persistent worker PID 15357, the guard, and one
active OSS solver child were live. The bounded snapshot measured 20999716864
bytes of task-tree RSS and 6.3 percent aggregate CPU during an
`ossdbs_bootstrap.py` phase. The append-only guard exceeded 60000 samples; its
recorded peak remained 62493573120 bytes, therefore `< 64 GiB`, and swap growth
remained `< 1` byte in both detected baseline epochs. This remains
intermediate, nonterminal evidence.

At the 2026-07-23 10:12 PDT checkpoint, the reference cache had advanced to 60
passing decisions and 120 corresponding row manifests. The newest decision is
`82daa7b6af4588ae1f87eb348a51076f30773ca9ac3d9f8e7efe7d6c388a06f3`;
its final and `Omega_max` row identities are
`7a79660624f4d19205b5b45ba8fa4dadb0e6d338fb2bba7a13d9d02b90388db6`
and
`5d8f24483d353823c9124ca12c50fbc61b7dafe829ad2a5319c515668ab7636a`.
Fresh validation passed the decision and both row manifests, exact file
closure, byte count, SHA-256, NPY dtype and shape, ordered unique positive
fiber IDs, finite probability range, and the exact final-to-`Omega_max`
canonical-ID subset. The final row contains 3401 fibers and the `Omega_max` row
contains 10320 fibers. Independent replay again found maximum probability
difference 0 and strict `p(A) > 0.5` state mismatch count 0, agreeing with the
persisted pass status and zero activation-count mismatch.

All 60 cumulative decisions remain passing members of the reference group.
This cumulative count is not a terminal denominator: the reference gate was
still running an active solver child and had not committed its authoritative
`row_decision_ids` closure. The 590-task ledger therefore remains 196
completed, one running, one historical failed, and 392 dependency-derived
skips. VAL remained mounted and writable. Runner PID 15265, persistent worker
PID 15357, the guard, and one active `run_pathway_activation` child were live;
the solver's internal pool used eight CPU workers during the snapshot. The
bounded task-tree snapshot measured 10424090624 bytes RSS and 796.5 percent
aggregate CPU. The guard exceeded 67000 samples; its recorded peak remained
62493573120 bytes, therefore `< 64 GiB`, and swap growth remained `< 1` byte
in both detected baseline epochs. This remains intermediate, nonterminal
evidence.

At the 2026-07-23 12:18 PDT checkpoint, the reference cache had advanced to 63
passing decisions and 126 corresponding row manifests. The newest decision is
`79bf18b86e0da3a2134e1877774f9361765d5b2979f79bb0ceddfbfd23dd7883`;
its final and `Omega_max` row identities are
`9cd749fa7dfb821a5ba0146ad2951f707ecbdfc67a02d1c3dd853f77b904dec6`
and
`cd139fd00adbf1cb47c2c9963b606f1c500fd1542f29adef8f81f2bbb7f96e22`.
Production cache resolution validated the decision and both row entries,
manifest identity, declared payload closure, byte count, SHA-256, NPY dtype
and shape, ordered unique positive fiber IDs, and finite probabilities within
the closed unit interval. Independent replay confirmed that the 3401-fiber
final axis is an exact canonical-ID subset of the 10320-fiber `Omega_max`
axis. The maximum probability difference, strict `p(A) > 0.5` state mismatch
count, and activation-count mismatch count were all 0, matching the persisted
pass decision.

All 63 cumulative decisions belong to the reference group and pass. The
reference gate remains running and has not committed its terminal
`row_decision_ids` closure, so this cumulative count is still not an
acceptance denominator. The 590-task ledger remains 196 completed, one
running, one historical failed, and 392 dependency-derived skips. VAL remained
mounted; the live runner, persistent worker, guard, and one OSS bootstrap child
were present. The bounded task-tree snapshot contained four processes at 98.1
percent aggregate CPU and 1860419584 bytes RSS. The append-only guard exceeded
74500 samples, retained its 62493573120-byte peak below 64 GiB, and reported
swap use below the active epoch baseline. This remains intermediate,
nonterminal evidence.

At the user-requested 2026-07-23 13:45 PDT inspection, the reference cache had
advanced again to 64 passing decisions and 128 row manifests. The eight most
recent decisions were committed at approximately 48-to-64-minute intervals.
All 64 decisions still belong to the reference group and pass; no new task
failure appeared. The active reference gate remains the only running task.

The single failed ledger row is the retained add-on equivalence gate
`task_7894935452035f4bf4b8`. It started at 2026-07-22T15:46:04Z and stopped
68 seconds later because an external MATLAB invocation returned code 1. This
is historical resume state rather than evidence that the currently executing
reference gate is failing. The resumed run preserves that record until the
single solver token is released and the add-on task can be retried. Formal OSS
acceptance still requires that retry to complete and cannot ignore or relabel
the retained failure.

No exact remaining-time denominator may be inferred from the 64 cumulative
reference decisions. The group function discovers and deduplicates its full
physical-row set before execution but publishes the authoritative count only
in its terminal `row_decision_ids` closure. The observed production rate can
therefore estimate time per remaining row but cannot prove how many reference
or add-on rows remain. Current operational planning uses a broad one-to-three
day range for independent OSS and a three-to-five day range for the full
remaining Task 17, combined, publication, and postprocess sequence, provided
there is no new external-tool or VAL interruption. These are scheduling
estimates, not acceptance evidence.

At the scheduled 2026-07-23 15:45 PDT boundary, the reference cache had
advanced to 66 passing decisions and 132 row manifests. The newest decision is
`7326853482974209ebb94cea781ceefe41164e939243010aec2dcb2034a3a432`;
its final and `Omega_max` rows are
`4d809f2c630b4e38f18832c580485654c197a409455b574cba1afbf3f9bc829d`
and
`8d062dc9674fb0848a51d531f99058a75fd0e6edbcff481ecaebe6100ed602de`.
Production cache resolution accepted all three entries, including exact
declared row payload closure, byte count, SHA-256, NPY dtype and shape,
ordered unique positive IDs, and finite closed-unit-interval probabilities.
Independent canonical-ID replay again proved that the 3401-fiber final axis is
an exact subset of the 10320-fiber `Omega_max` axis, with maximum probability
difference 0 and strict `p(A) > 0.5` state mismatch count 0. The persisted
activation-count mismatch is also 0.

The reference gate remained the sole running task; the historical add-on
failure and 392 dependency-derived skips were unchanged. The live runner,
persistent worker, external guard, and one solver process with eight internal
workers were present. The snapshot contained 14 processes, approximately
355.8 percent aggregate CPU, and 3532636160 bytes task-tree RSS. The guard
contained more than 86300 samples, retained its 62493573120-byte peak below
64 GiB, and reported no positive swap growth above the active baseline. VAL
remained mounted and writable. This remains nonterminal evidence because the
reference gate has not committed its authoritative closure.

At the scheduled 2026-07-23 17:45 PDT boundary, the reference gate became
terminal. Task `task_e4439d7c662faaf447fa` completed at
2026-07-24T00:42:07Z and committed the authoritative reference closure:
34 unique decision identities, 68 unique row-cache identities, gate status
`accepted_omega_max`, and artifact SHA-256
`f64d647a93305a648c713da8e1400a9b8c2eaa0a1cc07002a5ad2676ca2c50eb`.
The cumulative cache contained 69 reference-group decisions at the inspection
instant, but only the terminal 34-item `row_decision_ids` list is the accepted
reference inventory.

An independent full-closure replay resolved all 34 decision entries and all 68
row entries through the production cache validator. Every decision belongs to
the committed reference group and has status `pass`; every row passed
manifest identity, file SHA-256 and byte count, array dtype and shape, ordered
unique positive ID, and finite probability-range validation. All 34 final axes
were exact canonical-ID subsets of their paired `Omega_max` axes. The maximum
probability difference across the closure was 0, and aggregate strict
`p(A) > 0.5` state and activation-count mismatch counts were both 0. No
closure error was found.

The executor then restored the historical add-on gate
`task_7894935452035f4bf4b8` from failed to running without changing its task
identity. The ledger consequently became 197 completed, one running, zero
failed, and 392 dependency-derived skips. This is direct production evidence
that resume preserves a failed record until it can be retried, then reopens
only that failed task after the single solver token is released. The add-on
gate was actively producing its first unresolved row at the inspection
boundary; its authoritative closure remains pending.

VAL remained mounted and writable. The task-tree snapshot contained four
processes, approximately 7.9 percent aggregate CPU during an OSS bootstrap
phase, and 31934611456 bytes RSS. The external guard contained more than 93100
samples, retained its 62493573120-byte peak below 64 GiB, and recorded no
positive swap growth above the active baseline. Independent OSS remains
nonterminal until the add-on gate and all downstream tasks complete.

The first add-on `Omega_max` execution after reference closure disproved the
3500-fiber chunk bound for the add-on geometry. The one-second external guard
recorded a continuous single-solver RSS ramp from 44519882752 bytes to
69068636160 bytes between 2026-07-24T00:56:53Z and
2026-07-24T00:57:24Z. The final sample emitted `rss_limit_sigterm` because the
task tree no longer satisfied the strict 64-GiB ceiling. Swap remained below
the active epoch baseline, no second solver was present, no add-on decision or
row cache was published, and the retained workspace identifies the failing
execution chunk as a 3500-fiber add-on `Omega_max` chunk for `sub-SNr015`.

The guard terminated the runner and its active external child. Persistent
worker PID 15357 became reparented after runner exit and was then terminated
explicitly; a process-tree audit found no remaining runner, worker, solver, or
guard. All checkpoint, cache, failed workspace, and diagnostic logs remain
intact. Automatic restart is prohibited.

Before the next resume, reduce the internal execution bound from 3500 to 2800
fibers. This keeps the 7193-fiber add-on `Omega_max` row in three ordered
chunks while reducing the largest chunk by 20 percent. The observed
approximately linear memory ramp projects a peak near 55 GiB, leaving a
meaningful margin below 64 GiB. This is an execution-only partition: chunk
identities remain derived from the complete logical row identity and ordered
fiber IDs, chunks remain unpublished, concatenation restores the exact full
axis, and the standard row-cache and decision identities remain unchanged.
Existing complete reference decisions therefore remain reusable.

The code gate requires a boundary test for 2800-fiber chunks, a real
7193-fiber three-chunk layout test, focused OSS and cache/resume regression,
and a clean process-tree termination test. The next formal resume must use a
new execution segment and a new one-second guard from runner birth. Acceptance
requires the first real add-on maximum-size chunk to complete with task-tree
RSS `< 64 GiB`, swap growth `< 1` byte, and no stop event before the remaining
add-on gate may continue.

The 2800-fiber implementation and regression gate completed on 2026-07-24.
The chunk constant is now 2800, the generic concatenation fixture derives its
input size from that constant, and a dedicated 7193-fiber fixture requires the
exact 2800, 2800, and 1593 layout plus complete ordered-axis reconstruction
and unique chunk identities. The focused toolchain, axis-equivalence, cache,
and executor suite passed 124 tests. The correctly package-scoped complete
dual-frequency discovery then passed 610 tests in 72.843 seconds. An earlier
discovery invocation reported two import-loader errors because it omitted the
package top-level; neither loaded a test body, and the corrected full run
contains both modules and passes. Formal resume remains gated on the new
segment and real add-on resource measurement.

Segment 0011 then showed that the first unresolved add-on row contained 2004
fibers and therefore bypassed the 2800-fiber partition. Its sample-01
task-tree RSS peaked at 66341486592 bytes and remained below 64 GiB, but swap
grew by 720896 bytes. The one-second guard emitted
`swap_growth_sigterm`, terminated the runner, and left the add-on gate
incomplete without publishing a standard row or equivalence decision. No
process remained after termination. The NGSolve bootstrap was already fixed at
one thread, so no further NGSolve concurrency reduction is available.

The superseding execution bound is 1800 fibers. It splits the observed row
into 1800 and 204 fibers and splits the known 7193-fiber axis into 1800, 1800,
1800, and 1793 fibers. Tests must prove both layouts, exact ordered
concatenation, unique chunk identities, and termination behavior. The next
formal segment remains prohibited until those tests pass. Its production gate
requires a real 1800-fiber chunk to complete with task-tree RSS `< 64 GiB`,
swap growth `< 1` byte, and no guard stop event. The code gate is now closed:
125 focused OSS, equivalence, cache, and executor tests pass, followed by the
complete 614-test package regression. Only the real guarded resource gate
remains open.

Segment 0012 disproved the 1800-fiber production bound. A real
`sub-SNr020` right-side 30-Hz chunk contained 1800 fibers and retained 1334
axons inside the computational domain. During high-frequency field copying,
the complete task tree reached 69279547392 bytes and triggered
`rss_limit_sigterm`; swap growth remained `< 1` byte. No standard add-on row
or equivalence decision published, the task ledger was unchanged, and all
processes terminated.

The superseding execution bound is 1500 fibers. It partitions a 2004-fiber row
as 1500 and 504 and partitions a 7193-fiber axis as four 1500-fiber chunks
plus 1193. This execution-only change retains the complete row and all
scientific/cache identities. Before segment 0013, focused fixtures must assert
both exact layouts and ordered concatenation, and the complete package
regression must pass. Production acceptance still requires a real
1500-fiber chunk under task-tree RSS `< 64 GiB`, swap growth `< 1` byte, and
an uninterrupted guard.

The 1500-fiber implementation and exact-layout fixtures pass 125 focused OSS,
equivalence, cache, and executor tests and the complete 614-test package
regression. Segment 0013 is therefore permitted to test the remaining
production resource gate.

Segment 0013 disproved that bound. A real `sub-SNr015` right-side 30-Hz chunk
contained 1500 fibers and retained 1046 axons inside the computational domain.
The complete task tree remained near 56380178432 bytes through frequency-field
copying, then reached 70575407104 bytes when time-domain reconstruction
created the time-result payload. The guard emitted `rss_limit_sigterm`; swap
growth remained `< 1` byte. No standard row or decision published, the ledger
was unchanged, and all processes terminated.

The superseding execution bound is 750 fibers. It partitions a 2004-fiber row
as 750, 750, and 504 and partitions a 7193-fiber axis as nine 750-fiber chunks
plus 443. This halves the failed chunk's axon-dependent reconstruction payload
and conservatively leaves more than 2 GiB below the strict 64-GiB task-tree
limit even if all 750 fibers remain inside the domain. Scientific, cache, row,
and decision identities remain unchanged. Focused and complete regression must
pass before segment 0014 tests the real guarded boundary.

The 750-fiber implementation and exact-layout fixtures pass 125 focused OSS,
equivalence, cache, and executor tests and the complete 614-test package
regression. Segment 0014 is therefore permitted to test the remaining
production resource gate.

Segment 0014 has now completed and published at least one real 750-fiber
add-on decision. Decision
`8c8614c12b2155a4b71232fd146feeb4657f1fdff71ed63bd8c6b9c699539991`
belongs to `oss_axis_group_eaf54b8ab53dc387916e`; its maximum probability
difference, state mismatch count, and activation-count mismatch count are all
`0`, and its status is `pass`. Its paired final and Omega row manifests were
committed before the next workspace began. The segment-wide task-tree RSS peak
so far is 46507081728 bytes, swap has not increased, VAL remains mounted, and
the guard has emitted no stop event.

The segment and add-on gate remain active. The authoritative
`row_decision_ids` closure is therefore unavailable, the 392
dependency-derived downstream tasks remain skipped, and cumulative cache
directory counts are not a valid terminal denominator.

An accepted maximum-row measurement window must contain at least two guard
samples. Both the selected-row and owning-decision manifest commit times must
fall inside the first-to-last actual sample envelope, not merely inside
human-declared bounds. Every adjacent sample interval inside the selected
window must be `< 5` seconds. The accepted report records the maximum
window-local gap. A restart gap outside the selected epoch remains reported in
the global guard summary; a gap at or above five seconds inside the selected
window fails resource acceptance. This preserves the approximately one-second
guard contract without treating an unrelated restart gap as a scientific
failure.

The window-local continuity gate is implemented in both the builder and
independent validator. A boundary fixture places two samples exactly five
seconds apart: direct validation rejects the window and the builder refuses to
select that epoch. Valid one-second-scale fixtures continue to pass. The
pre-instrumentation suite now passes 15 tests, and the joint guard plus both
resource-validator suite passes 31 tests under Conda `leaddbs`.

The complete dual-frequency test directory was rerun after the continuity
change with low CPU priority and isolated package links. All 607 tests passed
in 73.400 seconds. The replay used temporary fixtures and did not read the
formal run, guard, or shared cache.

### Unified static regression checkpoint, 2026-07-23

The complete repository-local dual-frequency test directory was rerun under
Conda `leaddbs` with only the isolated package link on `PYTHONPATH` and a low
CPU scheduling priority while the independent OSS lineage remained active.
All 604 tests and 321 subtests passed in 75.17 seconds. The run covered the
typed record codecs, JSON/YAML configuration, four-family planning, persistent
spawn executor, direct-copy cache, bounded indexed views, distinct voxel and
fiber preparation, formal and in-sample inference, jitter blocks, OSS
toolchain and axis equivalence, pPAM, reporting, canonical publication,
extension-v2 validation, resource acceptance, and goal-level guards. It used
temporary fixtures and did not inspect or substitute for the formal run or
shared cache. This closes the current-worktree static regression boundary only;
the production OSS gate, downstream pPAM, combined child, canonical replay,
formal postprocess, and final resource audit remain required.

The terminal-resource preflight on the same date found one evidence-vocabulary
boundary before the active guard closes. The external segment-0010 guard writes
`runner_exit` after a normal runner disappearance, while the repository
pre-instrumentation validator accepted only the equivalent spellings
`runner_exited` and `completed`. The running guard cannot hot-load a source
change, and rejecting its actual terminal spelling would discard otherwise
valid one-second RSS and swap evidence. The validator must therefore accept
`runner_exit` as a clean terminal event without accepting any stop, limit, or
unmount event. A focused fixture must prove that the exact current spelling is
accepted and that unsupported guard events remain rejected. This compatibility
repair changes no scientific input, cache identity, task outcome, resource
ceiling, or running process.

The same clean-terminal spelling must be accepted by the strict instrumented
resource validator used for successor segments. It may receive a guard produced
from the same external template even when the execution segment also contains
internal resource samples. Both validators therefore accept `runner_exit`,
`runner_exited`, and `completed` as clean terminal vocabulary while continuing
to reject every limit, unmount, or termination event.

The same preflight found that the resource validator required
`max_probability_difference` to be exactly zero even though the scientific
gate accepts any finite value strictly below the fixed internal tolerance of
`1e-7`. The terminal validator must match the gate contract: the persisted
`probability_tolerance` must equal the fixed runtime tolerance, state and
activation-count mismatches must remain zero, and the maximum probability
difference must be `< 1e-7`. A nonzero value below the tolerance must pass,
while a value at the boundary or a changed persisted tolerance must fail.
This aligns acceptance with the immutable scientific decision rather than
weakening it or relying on the zero differences observed so far.

The active independent OSS runner also predates the in-process resource and
scheduler instrumentation. A source-history replay of the executor boundary
loaded by that lineage confirms that its segment opens with the stable
`dual_frequency_execution_segment_v1` identity, `spawn_process` pool mode,
worker and token settings, and a running status; normal closure adds
`finished_at` and `swap_delta_bytes` before atomically changing the status to
`finished`. It does not claim `resource_sample_count`, task-tree RSS, or
scheduler admission counters. The pre-instrumentation validator intentionally
accepts exactly this smaller segment and derives the missing continuous
resource evidence from the retained one-second external guard.

Successor execution segments use the current instrumented executor and must be
accepted only by the strict resource validator. The current writer and
validator agree on the finished status, spawn pool mode, worker ceiling,
single solver token, BLAS thread boundary, internal resource sample count,
task-tree RSS and swap fields, restored and scheduled task counts, terminal
task closure, pool generations, recovery counters, and scheduler admission
metrics. Recovery-path inspection confirms that every rescheduled invocation
increments `transient_retry_count`, including timeout and broken-pool
recovery, so the validator's scheduled-versus-terminal closure remains valid.
The independent OSS segment must never be upgraded by inference to this
instrumented schema, and the combined segment must never fall back to the
pre-instrumentation validator.

Strict resource-closure checkpoint on 2026-07-24:

- the validator now rejects unsafe segment identities, missing or escaped
  scheduler sidecars, SHA or row-closure mismatches, unknown admission reasons,
  and inconsistent storage classification;
- declared managed-memory, reserve, connectome-I/O, solver, BLAS, CPU, memory,
  running-task, queue, and admission boundaries are validated against both
  segment aggregates and scheduler-window samples;
- a guard terminal marker is accepted only as the final zero-RSS row, so no
  later sample can be silently accepted; and
- the checked-in guard plus pre-instrumentation and strict resource validators
  pass 40 focused tests.

This closes the strict-validator implementation gap for the future combined
segment. It does not reinterpret the active independent OSS segment, which
continues to require its separate pre-instrumentation acceptance.

Dynamic managed-memory closure was then completed on 2026-07-24. The resource
ledger is the sole owner of the initial, minimum, maximum, and final admission
ceilings; the live monitor owns only observed process-tree RSS, available
memory, and swap evidence. Every persisted scheduler window now carries its
contemporaneous managed-memory ceiling. Both the strict resource validator and
the performance-matrix validator reject a window whose ceiling falls outside
the segment closure or whose reserved memory exceeds that window ceiling.
The focused executor, resource, and performance set passed 65 tests; the joint
Task 17 byte, counter, probe, guard, pre-instrumentation, strict-resource, and
performance set passed 71 tests; and the complete dual-frequency discovery
passed 670 tests with warnings treated as errors. These tests establish the
writer and validator schema boundary only. The future combined production
segment must still supply the corresponding live evidence.

Independent performance-scheduler closure was completed on 2026-07-24. The
performance validator now requires the exact scheduler document and row field
sets, UTC-positive contiguous windows, the declared worker, managed-memory,
reserve, connectome-I/O, solver, and BLAS boundaries, exact admission-reason
closure, bounded running/runnable/reservation values, the writer-owned runnable
derivation, and the writer-owned storage-limited classification before it
calculates effective cores. Five new negative fixtures reject an added field,
a UTC gap, a solver reservation above its ceiling, a false runnable value, and
a false storage classification; a sixth rejects a Boolean elapsed value. The
seventh rejects a segment schema mismatch. The performance module passes 19
tests. The strict resource validator now rejects a Boolean elapsed value, a
non-string UTC value, and a false runnable derivation through three additional
fixtures. The joint executor and Task 17 evidence set passes 119 tests, and
complete dual-frequency discovery passes 680 tests with warnings treated as
errors.
The configured 72-row production matrix remains pending.

OSS identity-compatibility checkpoint on 2026-07-24:

The intended execution-only chunk contract is not yet met by the cache-key
implementation. The terminal reference closure has 34 decisions and 68 rows
under one historical `definition-sha256-*` fingerprint, the running add-on
rows use a later fingerprint, and the current checkout computes a third value.
This occurs because the complete `dual_frequency` production source tree is
hashed into `OSSScientificSettings.backend_version`, which enters each row key
both directly and through the settings parameter hash. The scientific arrays
remain valid, ordered-axis concatenation remains exact, and the accepted
reference closure remains authoritative; the incompatibility is lookup
identity, not numerical meaning.

Decision 39 in `task17_design_decisions.md` freezes the repair. OSS cache
identity must use a stable internal scientific contract version and explicit
scientific inputs. The complete implementation fingerprint remains a
before-and-after execution attestation for authorized misses but cannot
invalidate, hide, or force recomputation of an unchanged completed row. A
cache-first legacy resolver may atomically promote a fully verified
scientifically unique old payload and pass decision under the stable identity.
It must reject missing, corrupt, mismatched, ambiguous, or conflicting
candidates before any external toolchain starts.

No producer source is changed while the active independent solver is running.
After the independent gate becomes terminal, the compatibility implementation,
focused tests, and complete regression are required before OSS-v2 publication
or the cache-only combined child. The combined command remains forbidden from
carrying `--allow-expensive-producers`; its successful replay is the production
proof that both terminal reference and add-on rows remain usable after
execution-only code changes.

Implementation checkpoint on 2026-07-24:

The compatibility repair is isolated in
`/private/tmp/leaddbs-task17-oss-cache-compat` while the formal add-on solver
continues from the unchanged main checkout. The worktree now contains the
stable scientific backend version, cache-first legacy row and decision
promotion, promotion provenance, and before/after implementation attestation.
Newly executed rows persist the accepted attestation in
`row_metadata.json`; promoted rows retain the verified historical fingerprints
in `compatibility_source.json`. Neither provenance field participates in the
stable scientific identity. Production APIs use the project-neutral term
`historical`; the recognized historical backend string remains the exact
portable `definition-sha256-*` format.

The final isolated implementation test pass covers stable-key independence
from execution chunk size, exact historical row and pass-decision promotion,
promotion provenance, parameter and ordered-axis mismatch, missing and corrupt
rows, conflicting row payloads, conflicting decision evidence, cache-only
failure before toolchain invocation, and in-flight implementation drift.
Eighty-four focused OSS tests pass, the production dependency-boundary set
passes, and complete `dual_frequency` discovery passes 702 tests with four
expected skips and warnings treated as errors. Because the worktree does not
contain Git-ignored repository data, the complete run used read-only paths to
the main checkout's exact template segmentation and frozen acceptance
fixtures. The repair remains intentionally unmerged until the active formal
solver is terminal.

Resume migration boundary:

Completed accepted OSS-axis groups require referenced decision and row cache
closure during restore. A group whose rows already use
`ossdbsv2-ppam-scientific-v1` restores unchanged. A completed accepted group
that still references `definition-sha256-*` rows is replayed together with its
descendants, with expensive producer authorization forced off for the gate
regardless of the original run flag. Exact historical rows and pass decisions
therefore promote automatically on the first post-repair resume, while a real
miss or invalid cache fails before OSS. Rejected historical groups retain their
existing completed scientific decision because the frozen promotion contract
allows only validated pass decisions. This behavior is driven by the completed
result's referenced cache closure and does not inspect repository SHA.
The executor and OSS focused set passes 127 tests, including stable restore,
historical gate replay, descendant replay, forced no-expensive task
authorization, and an end-to-end executor resume fixture that promotes a real
historical row-and-decision cache closure without invoking the toolchain.

The compatibility commits were then merged after the interrupted writer had
fully exited. Parent-run ID, parent manifest SHA, scientific configuration
hash, plan hash, and OSS-only analysis scope all validated before resume, and
the main checkout passed 155 focused tests plus 36 subtests. The first true
resume created `segment_0016`, restored 196 tasks, scheduled zero tasks, invoked
no solver, and wrote no row or decision. Its two ready equivalence gates were
both charged as 48-GiB solver tasks while the live managed-memory ceiling was
49758738842 bytes, which was `< 48 GiB`; the executor then incorrectly raised a
dependency or resource-admission deadlock.

Decision 40 freezes the repair before another production attempt. A
cache-first task without expensive authorization receives only the bounded
cache-read grant and owns no solver or connectome-I/O token. A structurally
admissible task blocked only by current memory pressure remains pending while
the production monitor resamples once per second. Structural impossibility and
dependency deadlock continue to fail immediately. This changes only scheduler
admission: it does not change task identity, stable OSS identity, historical
promotion criteria, row content, decision content, or any scientific result.
Production `segment_0017` must prove cache-only reference promotion and reuse
of the three completed add-on decisions before the first missing add-on row
reaches the solver.

The Decision 40 implementation is complete. Focused executor and OSS coverage
passes 157 tests plus 36 subtests. Complete dual-frequency discovery passes 727
tests plus 326 subtests with warnings treated as errors. The new production
resume is therefore authorized, but its cache-reuse and first-solver-call
evidence remain open until the guarded segment runs.

Guarded `segment_0017` supplied the first production evidence. Reference
historical promotion reached a terminal accepted group with 34 decisions and
68 rows and no reference solver call. The add-on gate reused its completed
cache and reached only missing producer work. A later MATLAB preprocessing
launch returned code 1 with empty logs, so the segment finished with 393
completed tasks, one failed add-on gate, and 196 dependency skips. The guard
recorded a 20272988160-byte task-tree RSS peak, swap growth `< 1` byte, and no
stop event other than normal runner exit.

The same MATLAB batch executable passed a bounded readiness command immediately
after diagnosis. No code, scientific identity, cache identity, or resource
setting changes are justified by this isolated external startup failure.
Resume the same lineage under a fresh segment and guard. It must restore the
stable reference gate, reuse every complete add-on cache, and retry only the
failed add-on gate and its dependency-derived descendants.

The authorized `segment_0018` resume remained active at
2026-07-25T16:25:46Z. VAL was mounted, a real create/fsync/read/unlink probe
passed, and the Samsung T7 reported `UsbLinkSpeed` 10000000000 bits/s. The
590-task ledger contained 393 completed, one running add-on equivalence gate,
and 196 dependency skips. The stable reference gate still contained 34
accepted decisions; the add-on producer was executing `sample_03` for a
genuinely missing row. The one-second guard contained 13692 samples, only
`sample` events, peak task-tree RSS 45696860160 bytes, current task-tree RSS
about 7513522176 bytes, swap baseline 3579188347 bytes, and current swap
3366851707 bytes. Thus RSS remained `< 64 GiB` and swap growth remained `< 1`
byte. No automatic restart or code hot-load occurred.

The benchmark parent transaction is now implemented without exposing the
public `run` operation prematurely. For each prepared ordinary,
real-cache-hit, or authorized real-solver row, the parent launches the bound
child in a new process group, requires the exact readiness PID and slice-plan
SHA, initializes the live byte-ledger index, launches the external probe, and
waits for its first live process sample before publishing the immutable
measurement token. After child and probe exit, it requires one terminal
`runner_exit` sample, strictly increasing timezone-aware timestamps and elapsed
times, monotonic CPU and byte counters, one completed run manifest, and exactly
one finished execution segment. It then builds the terminal byte ledger,
requires its source and scratch totals to match the probe, runs the
artifact/static audit and counter builder, and commits `row_result.json` only
after every evidence file has a row-local SHA reference. Any exception stops
only the harness-owned runner and probe process groups and leaves the attempt
partial. The hidden child CLI is available solely for this parent transaction.
The public `run` gate remains closed until configured-data candidate parity,
ordinary unmeasured warm-seed execution, injected spawn-worker support, and
matrix-level terminal validation are complete. The focused harness suite now
passes 26 tests, including exact terminal-segment and probe-envelope rejection
fixtures.

Configured candidate-parity preparation is now implemented. It strict-decodes
the accepted parent's task-status table and completed task states, requires
224 unique prepared endpoints and 224 matching final or sensitive selections,
and derives every row without an operator-supplied endpoint or threshold.
Voxel rows convert their exact source-selected indices to benchmark-local
ordered canonical IDs through an immutable atomic NPY transaction. Fiber rows
bind the existing `normative_fiber_valid_union_ids` artifact directly. The
marker is committed only after the 224-row v2 plan runs, reports no full or
fold false negative, and reopens with the same plan/report SHA closure. The v2
parity runner caches each unique parent-exposure, parent-axis, tau, and
Coverage candidate closure, so repeated scales do not rescan the same physical
matrix. The historical v1 plan remains supported. Synthetic v1/v2 and
performance-harness coverage passes 32 tests. A read-only configured parent
derivation produced 224 rows across all four model families, 8 unique physical
parent exposures, and 8 unique selected-ID payloads. The full configured
parent scan was deliberately not started while independent OSS was using VAL;
its terminal report remains production evidence to be generated by the later
benchmark `prepare`.

Ordinary unmeasured warm-seed execution is now implemented. The harness derives
exactly 8 seed slices from the 72-row matrix: 7 ordinary slices and one
injected pPAM slice. For each ordinary slice it creates a monotonic
benchmark-local attempt, proves the scientific cache is empty, binds the exact
accepted parent and OSS checkpoint closure, executes the selected production
slice with one persistent spawned-worker pool, rejects any restored selected
task, finalizes the isolated run, fully reopens every resulting cache entry,
and commits `warm_seed.json` last. Resume revalidates that the seed cache lies
beneath its own warm-seed transaction and that the complete entry closure
still matches. Real-cache-hit pPAM is excluded because it copies the accepted
OSS closure directly; real-cold pPAM has no warm row. Injected pPAM remains
fail-closed until its spawned-worker fixture descriptor can be implemented
after independent OSS terminates. The candidate-parity plus harness suite now
passes 33 tests.

Matrix-level resume and terminal publication are now implemented internally.
The runner reopens the marker and candidate report, prepares every missing
seed, visits all 72 stable rows sequentially, reuses only a terminal row whose
contract and complete evidence SHA closure still validate, and creates a new
monotonic attempt for every partial row. Only the four unauthorized real-cold
pPAM rows may publish `not_run`; every other execution error remains partial.
Each executed row derives `io_classification` from its run-owned scheduler
windows and derives one normalized numerical identity from the exact selected
task-result closure after removing only run-local artifact URIs and scratch
generation paths. It then binds the actual resolved worker snapshot, finished
segment, probe, counter sidecar, and numerical identity into the matrix row.
After all rows are terminal, the harness atomically publishes the exact
72-row matrix, invokes the repository validator, and publishes its immutable
acceptance report. At that intermediate checkpoint the public `run` operation
remained closed because injected spawned-worker execution was fail-closed.
Candidate-parity plus harness coverage then passed 35 tests.

The injected-worker implementation boundary was frozen before code changes.
`SpawnWorkerSpec` receives one optional immutable
`BenchmarkOSSInjectedFixtureSpec`; the default remains null. The descriptor
contains the version, resolved fixture-cache root, accepted closure SHA, and
sorted permitted row identities. A worker with a descriptor reconstructs the
ordinary `StudyRuntimeInputProvider`, validates the descriptor and fixture
root, and overrides only `oss_producer_toolchain` with the deterministic
ten-sample benchmark toolchain. The pre-spawn child validates the complete
fixture closure once; workers fully reopen only a requested permitted row,
avoiding a closure-wide rehash in every process. The provider must remain a
`StudyRuntimeInputProvider` instance because the OSS gate enforces that
capability boundary. Warm-seed and measured-row parents derive the descriptor
only from their already validated fixture document. Ordinary rows continue to
construct the unchanged null descriptor. Null-default compatibility must execute
`initialize_worker` without a fixture and prove that it constructs the ordinary
provider with its production OSS toolchain unchanged; inspecting only the
dataclass default is insufficient. Focused tests must also prove
invalid-descriptor rejection, permitted-row reconstruction, forbidden-row
rejection, and injected warm/row context construction before the public `run`
operation opens. At the current isolated checkpoint, all five candidate-parity
tests and 35 performance-harness tests pass.

The public boundary then exposes only the already implemented `_run_matrix`
orchestration as `run`. Read-only `validate` must keep its prepared-plan checks
and, when either terminal file exists, require both `performance_matrix.json`
and `performance_acceptance.json`, recompute strict acceptance without writing,
and require exact equality with the stored report. A matrix without acceptance,
acceptance without a matrix, or changed terminal report is partial and fails.

This isolated implementation now passes five candidate-parity tests and 34
performance-harness tests. It adds the null-default spawn descriptor, the
worker-local injected provider, injected warm-seed and measured-row context
construction, public `run`, and read-only terminal validation. The complete
suite remains deferred until independent OSS exits because the active
production memory reservation makes the system-derived executor admission test
fail in both the unchanged main checkout and this isolated worktree; ignored
template and frozen-acceptance data are also absent from the worktree.

The formal configured benchmark request is frozen at
`config/four_model_v1/acceptance/task17_performance_benchmark_request.json`.
It binds the completed v8 parent, the independent OSS lineage, the exact four
input copies retained by the parent run, Conda `leaddbs`, the repository
working directory, a 64-GiB RSS ceiling, and no real-cold solver
authorization. Its separate benchmark root is
`/Volumes/VAL/STNSNr/summary/spot/acceptance/task17-performance-matrix-v1-20260725`.
Only after independent OSS is terminal, the isolated implementation is merged,
and the complete regression passes, execute:

```bash
env -u PYTHONPATH /opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/fiber/pipelines/run_task17_performance_matrix.py prepare \
  --request my_helper/stnsnr/config/four_model_v1/acceptance/task17_performance_benchmark_request.json \
  --benchmark-root /Volumes/VAL/STNSNr/summary/spot/acceptance/task17-performance-matrix-v1-20260725

env -u PYTHONPATH /opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/fiber/pipelines/run_task17_performance_matrix.py run \
  --request my_helper/stnsnr/config/four_model_v1/acceptance/task17_performance_benchmark_request.json \
  --benchmark-root /Volumes/VAL/STNSNr/summary/spot/acceptance/task17-performance-matrix-v1-20260725

env -u PYTHONPATH /opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/fiber/pipelines/run_task17_performance_matrix.py validate \
  --request my_helper/stnsnr/config/four_model_v1/acceptance/task17_performance_benchmark_request.json \
  --benchmark-root /Volumes/VAL/STNSNr/summary/spot/acceptance/task17-performance-matrix-v1-20260725
```

`prepare` is forbidden while the OSS source is nonterminal. `run` resumes only
the immutable prepared root, and `validate` performs no repair.

### Current remaining-acceptance matrix, 2026-07-22

This matrix separates implemented code from evidence that can exist only after
the active production lineage advances. The unchecked Task 17 steps remain
unchecked until both columns are complete.

| Step | Current implementation evidence | Remaining authoritative evidence |
|---|---|---|
| 1 | Reviewed parity allowlist, axis authority, voxel/fiber separation, and replay verifier are implemented and covered by the current regression. | Run the configured-data post-refactor replay after the independent OSS process releases the shared connectome and VAL I/O path. |
| 2 | Direct-copy SHA cache, process-local verification reuse, persisted indexed views for reference and all raw add-on matrices, bounded consumers, copied-root checkpoint replay, and corruption tests pass. | Measure configured-data parity and production-scale logical-versus-physical write reduction from the post-refactor replay. |
| 3 | Shared bilateral sampling plans, scale-neutral physical rows, endpoint row/column views, and direct-voxel parity fixtures pass. | Record configured full-matrix parity and production physical-row counters. |
| 4 | Point-balanced HDF5 traversal, exact inclusive minimum-grid `Omega_max`, shared geometry, bounded fallback, and real-HDF5 path fixtures pass. | Record configured connectome parity and production chunk/resource counters. |
| 5 | Jitter v8 is complete; physical blocks are cache-first; the OSS decision gate, O(1) rows, exact subset mapping, and lazy toolchain boundary pass local tests. The current whole-tree implementation fingerprint incorrectly changes row lookup identity after execution-only edits; Decision 39 freezes the stable semantic identity and legacy-promotion repair. | Finish both production OSS groups, prove every decision passes, implement and test cache-only promotion of their terminal reference and add-on rows, rerun the 392 dependency-derived downstream tasks, and accept independent OSS reporting and publication. |
| 6 | Portable sensitivity bases, exact resume, extension-v2 replay, missing-parent checks, and self-contained publication fixtures pass. | Publish canonical independent OSS and combined extension-v2 trees from terminal children. |
| 7 | Persistent spawn scheduling, pure-data commands, parent-owned state mutation, resource ledger, timeout/retry boundaries, one solver token, and 64-GiB guard fixtures pass. | Retain terminal live RSS, CPU, swap, worker, resume, and generation evidence across independent OSS and combined execution. |
| 9 | Formal and bootstrap schedules, scratch, durable blocks, ordered aggregation, pPAM blocks, jitter blocks, fixed historical RNG, and selective resume pass local regression. | Accept the production downstream pPAM block closure and combined cache-only replay. |
| 10 | Numerical, cache-copy, corruption, resume, cleanup, publication, and visualization component suites pass. | Run the configured parity replay, no-authorization combined child, canonical publication, full public-only postprocess, identical resume, and sampled visual review. |
| 11 | All implementation and checkpoint changes are recorded in focused commits and the worktree is clean. | Complete the requirement-by-requirement three-plan audit, update final statuses, and commit only after every production artifact and verifier passes. |

---

## Plan Self-Review Record

Five generic-core review passes were completed on 2026-07-15. A sixth
performance-contract review was added on 2026-07-16:

| Pass | Result | Implementation mapping |
|---|---|---|
| 1. Authority/current state | PASS | The umbrella YAML goal and its linked dual-frequency and postprocess plans jointly define current acceptance; the predecessor plan is historical, and the existing uncommitted implementation worktree remains preserved until final acceptance rather than being represented as clean. |
| 2. Scale/endpoint identity | PASS | Tasks 3-6 implement equal factories, stable binding IDs, explicit matched-reference endpoint IDs, and cross-phase matching. |
| 3. Dependency/fallback | PASS | Task 5 defines the exhaustive readiness/source/Delta/fallback truth table; Tasks 11-12 integrate it without bidirectional fallback. |
| 4. Round/interface/provenance | PASS | Tasks 2, 6-8, and 13-16 cover every Round, typed requests/arrays/artifacts, project import isolation, standalone CLI, connectome roles, and resolved configuration artifacts. |
| 5. Bounded acceptance | PASS | Task 1 requires an exact reviewed task allowlist; Tasks 9-14 use only applicable completed fixtures; Task 16 blocks expensive misses and parity expansion. |
| 6. Shared physical preparation and resources | DESIGN PASS / PARTIAL IMPLEMENTATION | Code audit plus primary literature/official runtime guidance map Task 17 to the authorized mixed threshold policy, distinct voxel/fiber preparation, exact `Omega_max`, single-write no-payload-reread caches, bounded semantic identity, a persistent spawn-safe resource scheduler, parity-preserving RNG blocks, vectorized kernels, resume correctness, and measured performance gates. The OSS axis gate, exact subset path, row-decision resume, and O(1) row manifest are implemented and synthetically accepted; formal real OSS decisions and the remaining full Task 17 audit remain open. |

This record validates closure of the generic-core implementation and design
closure of the performance refactor. Task 17 remains open. The OSS axis-gate
subsystem is implemented, but no test count implies completion of the remaining
formal real OSS execution, combined extension, publication, or full resource
audit.

---

## Generic-Core Historical Acceptance And Current Target Checklist

- [x] `dual_frequency_v1` is the only production schema.
- [x] The umbrella YAML goal, this implementation plan, and the postprocess
  visualization plan jointly define current acceptance; the predecessor
  execution plan is historical only.
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
- [ ] OSS row and decision cache identities use the stable scientific contract
  rather than the complete repository implementation fingerprint; verified
  historical rows and pass decisions promote cache-first without an expensive
  producer, while implementation drift is retained only as execution
  attestation. The isolated implementation and complete regression pass; merge
  and production cache-only promotion remain pending until the active solver is
  terminal.
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
- [ ] Managed RAM is the smaller of 64 GiB and available RAM after the larger of
  a 16-GiB or 20%-physical reserve; one solver receives a conservative 48-GiB
  admission charge, complete task-tree RSS stays `< 64 GiB`, and swap satisfies
  `swap_delta_bytes < 1`. A token-free local guard samples mount state, runner
  liveness, task-tree RSS, and swap at approximately one-second intervals and
  terminates the runner on a contract violation. Codex progress inspection and
  user-facing reporting remain limited to the user-selected two-hour interval;
  they do not replace the local safety guard.
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
