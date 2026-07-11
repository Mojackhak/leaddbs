# Dual-Frequency Core Decoupling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the STNSNr-oriented `four_model_v1` runtime adapters with a
strict, reusable `dual_frequency_v1` four-model core that can run from a
canonical study bundle without legacy or migration imports.

**Architecture:** Build a new `my_helper/fiber/core/dual_frequency` package next
to the predecessor package, migrate contracts and orchestration first, then
extract numerical backends one family at a time. Keep predecessor outputs
immutable, use bounded golden fixtures only for completed predecessor tasks, and
switch the production registry only after generic backends pass structural,
smoke, and applicable parity tests.

**Tech Stack:** Python 3.11, NumPy, SciPy, pandas, PyArrow, scikit-learn,
statsmodels, nibabel, PyYAML, jsonschema, unittest, Lead-DBS, and OSS-DBSv2.

## Global Constraints

- Work on the existing `stnvop` branch; do not create another worktree and do
  not push.
- Use the `leaddbs` Conda environment.
- Installing required packages into `leaddbs` is permitted. Add every new
  dependency to `my_helper/env/environment-leaddbs.yml` before installation,
  keep additions minimal, and record the resolved version in run provenance.
- Update relevant documentation before each code phase.
- Use test-driven development: failing test, minimal implementation, passing
  focused tests, regression tests, then commit.
- All code, identifiers, comments, docstrings, schemas, and generated field
  names are English.
- Runtime roles are `reference_component` and `addon_component`; generic code
  must not dispatch on STNSNr, HF, ULF, STN, STN+SNr, dTOR, or scale names.
- The core supports exactly reference-only and combined dual-frequency states;
  no add-on-only or N-frequency modeling.
- All configured scales are engineering-equivalent and no default scale exists.
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
- `/Volumes/VAL/STNSNr/summary` and configured run
  `20260711T034644Z_d318f177f7f2ac7d` are immutable.
- Numerical parity covers only terminal completed, hash-valid scientific tasks
  from that run. Do not resume it or compute unfinished paths for parity.
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
    study_bundle.py
  config/
    __init__.py
    loader.py
    models.py
    schemas/
      study_profile.schema.json
      scale_profile.schema.json
      model_profile.schema.json
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
  importer/
    __init__.py
    build_bundle.py
  migration/
    __init__.py
    convert_four_model_v1.py
  acceptance/
    __init__.py
    build_bounded_fixture_manifest.py
    compare_bounded_fixtures.py
  legacy/

my_helper/fiber/pipelines/run_dual_frequency_models.py
my_helper/stnsnr/config/dual_frequency_v1/
  study.yaml
  scales.yaml
  model.yaml
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
- Create: `my_helper/fiber/projects/stnsnr/acceptance/tests/test_bounded_fixture_manifest.py`
- Create: `my_helper/fiber/projects/stnsnr/migration/__init__.py`
- Create: `my_helper/fiber/projects/stnsnr/migration/tests/__init__.py`
- Create: `my_helper/fiber/projects/stnsnr/migration/convert_four_model_v1.py`
- Create: `my_helper/fiber/projects/stnsnr/migration/tests/test_convert_four_model_v1.py`
- Modify: `my_helper/stnsnr/four_model_execution_implementation_notes.md`

**Interfaces:**
- Produces: `build_fixture_manifest(run_root: Path, output_root: Path) -> Path`
- Produces: `compare_fixture(expected: Path, observed: Path) -> ComparisonResult`
- Produces: `convert_profiles(source_workflow: Path, output_dir: Path) -> Path`
- Constraint: tools are manually invoked and never imported by runtime code.

- [ ] **Step 1: Document the frozen task/artifact eligibility rule**

Add an implementation-note section naming the immutable run and stating:

```text
eligible = status == completed
           and task has scientific artifacts
           and every artifact hash validates

excluded = reports that only summarize failure
           or partial/failed/skipped/pending/unstarted tasks
```

- [ ] **Step 2: Write failing fixture-manifest tests**

Create a temporary run with one completed scientific task, one completed
failure-report task, one failed task, and one missing artifact. Assert only the
first enters `eligible_tasks`:

```python
manifest = build_fixture_manifest(run_root, output_root)
payload = json.loads(manifest.read_text(encoding="utf-8"))
self.assertEqual([row["task_id"] for row in payload["eligible_tasks"]], ["task_science"])
self.assertEqual(payload["source_run_id"], "frozen_run")
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

Read `task_status.csv`, require the immutable run identity from
`run_manifest.json`, load task manifests, hash every referenced artifact, reject
paths outside the run root, and write sorted JSON. Do not run a producer or
repair missing files.

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

The converter maps only explicit predecessor roles:

```python
ROLE_MAP = {
    "frequency_1_reference": "reference_component",
    "frequency_2_addon": "addon_component",
    "frequency_2_addon_chronic": "combined",
    "frequency_2_addon_immediate": "combined",
}
```

It writes draft `dual_frequency_v1` files plus a conversion report. Unknown
fields fail with `MigrationError`; the production loader is not imported.

- [ ] **Step 7: Run focused tests and generate the frozen manifest**

Run the two test modules, then manually generate a manifest from:

```text
/Volumes/VAL/STNSNr/configured_model_runs/stnsnr_frequency_addon/
20260711T034644Z_d318f177f7f2ac7d
```

Expected: only hash-valid completed scientific tasks are eligible; no process
matching `run_configured_outcome_models.py` starts.

- [ ] **Step 8: Commit**

```bash
git add my_helper/fiber/projects my_helper/stnsnr/four_model_execution_implementation_notes.md
git commit -m "test: freeze bounded dual-frequency fixtures"
```

---

### Task 2: Add Parquet Dependency, Generic Contracts, And Strict Schemas

**Files:**
- Modify: `my_helper/env/environment-leaddbs.yml`
- Create: `my_helper/fiber/core/dual_frequency/__init__.py`
- Create: `my_helper/fiber/core/dual_frequency/contracts/__init__.py`
- Create: `my_helper/fiber/core/dual_frequency/contracts/identity.py`
- Create: `my_helper/fiber/core/dual_frequency/contracts/records.py`
- Create: `my_helper/fiber/core/dual_frequency/contracts/requests.py`
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
  `FeatureAxisRef`, `SourceRecord`, `BranchRecord`, `FinalModelRecord`,
  `DeltaReferenceBundle`, and `StudyBundleRef`.
- Produces request/result contracts: `ObservedRequest`, `ObservedResult`,
  `FormalRequest`, `FormalResult`, `SensitivityRequest`, `SensitivityResult`,
  `ActivationRequest`, and `ActivationArtifact`.

- [ ] **Step 1: Add `pyarrow` to the environment definition**

Add `pyarrow` after `pandas` in `my_helper/env/environment-leaddbs.yml` and run:

```bash
conda env update -n leaddbs -f my_helper/env/environment-leaddbs.yml
conda run -n leaddbs python -c "import pyarrow; print(pyarrow.__version__)"
```

Expected: a finite version string; do not use `--prune`.

- [ ] **Step 2: Write failing schema tests**

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

- [ ] **Step 3: Write failing immutable-record tests**

Use this interface:

```python
key = EndpointKey(
    study_id="synthetic",
    scale_id="scale_a",
    phase_id="phase_b",
    model_family="addon_fiber",
    connectome_id="connectome_x",
)
self.assertEqual(key.identifier, EndpointKey(**dataclasses.asdict(key)).identifier)
with self.assertRaises(dataclasses.FrozenInstanceError):
    key.scale_id = "changed"
```

- [ ] **Step 4: Run tests and verify RED**

```bash
conda run -n leaddbs env PYTHONPATH=my_helper/fiber/core \
  python -m unittest discover \
  -s my_helper/fiber/core/dual_frequency/tests \
  -p 'test_config.py' -v
```

Expected: import failure for `dual_frequency`.

- [ ] **Step 5: Implement strict typed contracts**

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

- [ ] **Step 6: Implement four JSON Schemas and loader**

All schemas use `additionalProperties: false`. Cross-profile validation checks
component roles, condition membership, scale bindings, connectome roles,
minimum subjects, model grids, and required scale selection. Derive:

```python
direct_candidate_threshold_v_per_m = min(model.direct_voxel.tau_grid_v_per_m)
```

Do not include the derived field in public serialized YAML.

- [ ] **Step 7: Run focused and predecessor regression tests**

Run new config/record tests and the predecessor config/identity/record tests.
Expected: both suites pass; no predecessor file changes.

- [ ] **Step 8: Commit**

```bash
git add my_helper/env/environment-leaddbs.yml my_helper/fiber/core/dual_frequency
git commit -m "feat: define dual-frequency contracts"
```

---

### Task 3: Implement Canonical StudyBundle And STNSNr Importer

**Files:**
- Create: `my_helper/fiber/core/dual_frequency/contracts/study_bundle.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_study_bundle.py`
- Create: `my_helper/fiber/projects/stnsnr/importer/__init__.py`
- Create: `my_helper/fiber/projects/stnsnr/importer/tests/__init__.py`
- Create: `my_helper/fiber/projects/stnsnr/importer/build_bundle.py`
- Create: `my_helper/fiber/projects/stnsnr/importer/tests/test_build_bundle.py`
- Create: `my_helper/stnsnr/config/dual_frequency_v1/study.yaml`
- Create: `my_helper/stnsnr/config/dual_frequency_v1/scales.yaml`
- Create: `my_helper/stnsnr/config/dual_frequency_v1/model.yaml`
- Create: `my_helper/stnsnr/config/dual_frequency_v1/workflow.yaml`

**Interfaces:**
- Produces: `write_bundle(bundle: DualFrequencyStudyBundle, root: Path) -> StudyBundleRef`
- Produces: `load_bundle(root: Path) -> DualFrequencyStudyBundle`
- Produces: `build_stnsnr_bundle(config: ImportConfig, output_root: Path) -> StudyBundleRef`

- [ ] **Step 1: Write failing bundle round-trip tests**

Create two subjects, two scales, one reference-only condition, and one combined
condition. Write/load all required Parquet/JSON files and assert stable hashes,
orders, units, and role IDs.

- [ ] **Step 2: Write failing importer tests with synthetic Excel files**

The test workbook columns are exactly:

```text
ID, Scale, Protocol, Phase, Value, Baseline
```

Assert the importer maps project labels through configuration and emits only
generic role IDs. A missing immediate MDS-UPDRS IV row must remain absent rather
than copied from another scale.

- [ ] **Step 3: Run tests and verify RED**

Run the two new test modules. Expected: missing bundle/importer modules.

- [ ] **Step 4: Implement bundle validation and atomic writes**

Validate uniqueness, foreign keys, finite clinical values, explicit orders,
units, space, and artifact hashes before publishing `bundle_manifest.json`.
Write to a temporary sibling directory and atomically rename only after every
file validates.

- [ ] **Step 5: Implement the STNSNr importer**

The importer may know STNSNr workbook/path labels. It must output canonical
tables with these role columns:

```text
component_role: reference_component | addon_component
condition_role: reference_only | combined
```

Do not import any outcome-model service.

- [ ] **Step 6: Author the four STNSNr `dual_frequency_v1` profiles**

Preserve current scientific grids and parameters. Assign current connectomes by
roles rather than runtime name checks. Keep MDS-UPDRS III score and IV as normal
workflow selections, not defaults.

- [ ] **Step 7: Run tests and real read-only import validation**

Build a bundle into a new namespaced temporary output. Verify current input
hashes and endpoint counts without running a model or modifying source files.

- [ ] **Step 8: Commit**

```bash
git add my_helper/fiber/core/dual_frequency/contracts \
  my_helper/fiber/projects/stnsnr/importer \
  my_helper/stnsnr/config/dual_frequency_v1
git commit -m "feat: add canonical dual-frequency study bundle"
```

---

### Task 4: Implement Generic Identity And Endpoint Catalog

**Files:**
- Create: `my_helper/fiber/core/dual_frequency/catalog/__init__.py`
- Create: `my_helper/fiber/core/dual_frequency/catalog/builder.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_catalog.py`
- Modify: `my_helper/fiber/core/dual_frequency/contracts/identity.py`

**Interfaces:**
- Produces: `build_endpoint_catalog(config, bundle) -> tuple[EndpointRecord, ...]`
- Consumes: `ResolvedWorkflow`, `DualFrequencyStudyBundle`

- [ ] **Step 1: Write failing catalog tests**

Cover all four model families, multiple connectome roles, multiple phases,
minimum subjects, unavailable rows, and scale equality. Assert the synthetic
profile has no project-frequency names in serialized catalog rows.

- [ ] **Step 2: Add the named III/IV structural fixture**

Assert MDS-UPDRS III immediate is executable and MDS-UPDRS IV immediate is
`not_configured`, with no scale-name conditional in the builder.

- [ ] **Step 3: Run tests and verify RED**

Expected: missing catalog module.

- [ ] **Step 4: Implement bundle-driven catalog construction**

The builder filters canonical clinical rows by stable endpoint binding and
intersects explicit subject IDs. It never reads Excel or raw project paths.

```python
class CatalogStatus(str, Enum):
    DATA_AVAILABLE = "data_available"
    NOT_CONFIGURED = "not_configured"
    INSUFFICIENT_SUBJECTS = "insufficient_subjects"
```

- [ ] **Step 5: Run focused tests and identity regression**

Expected: deterministic endpoint ordering and IDs under repeated builds;
reordering bundle rows does not change endpoint IDs.

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
- Produces: `derive_branch_plan(reference: SourceRecord, delta_status: str) -> BranchPlan`
- Produces: `realize_final(branch_plan: BranchPlan, branches: Mapping[str, BranchRecord]) -> FinalDecision`

- [ ] **Step 1: Write the exhaustive failing truth-table tests**

Include:

```text
reference absent -> no-delta only
reference predictive + Delta valid -> adjusted intended, both attempted
reference nonpredictive + Delta valid -> no-delta intended, both attempted
adjusted intended input/design/source failure + accepted no-delta -> fallback
no-delta intended failure + accepted adjusted -> no_final_model
intended technical failure + accepted alternate -> execution_failure
accepted intended + alternate technical failure -> intended remains final
```

- [ ] **Step 2: Run tests and verify RED**

Expected: missing state module.

- [ ] **Step 3: Implement pure state transitions**

Use no filesystem or NumPy dependency. Accepted sources are exactly:

```python
ACCEPTED = frozenset({"pre_specified_accepted", "scan_fallback_accepted"})
```

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
- add-on dependencies match scale/phase/connectome reference identities;
- robustness connectomes stop at configured observed/report stages;
- formal/activation tasks use connectome roles, not names;
- expensive activation producer tasks are statically visible;
- missing endpoint phases produce terminal catalog/report tasks, not models;
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

- [ ] **Step 4: Compare the scientific task inventory with the `/goal` matrix**

Add a parameterized test asserting every non-deferred Round has at least one
task stage and no optional future Round appears.

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
  `ServiceRegistry`, and `execute_plan(plan, context) -> RunResult`.

- [ ] **Step 1: Write failing scientific-identity tests**

Assert scale, endpoint, run, workers, and retry changes do not alter an OSS row
key, while geometry, stimulation, component, transform, connectome, backend, or
scientific parameter changes do.

- [ ] **Step 2: Write failing cache validation/reindex tests**

Exact IDs in different order may produce a view manifest after per-item hashes
validate. Changed/duplicate/missing IDs raise `CacheIdentityMismatch`.

- [ ] **Step 3: Write failing executor tests**

Cover resume identity, endpoint isolation, false gates, required artifacts,
nonzero exit aggregation, and `ExpensiveProducerNotAuthorized` without invoking
a producer.

- [ ] **Step 4: Implement atomic content-addressed cache publication**

Write to a temporary sibling, hash every file, then atomically publish. Cache
manifests include scientific identity and exclude runtime scheduler identity.

- [ ] **Step 5: Implement generic run store and executor**

Use run root:

```text
<output_root>/dual_frequency_runs/<study_id>/<run_id>/
```

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

- [ ] **Step 1: Write failing service/CLI tests**

Test `--scale` repeatability, `--all-available` exclusivity, required selection,
dependency-complete `--through`, exact resume, force lineage, and explicit
`--allow-expensive-producers`.

- [ ] **Step 2: Run tests and verify RED**

Expected: missing application package and entrypoint.

- [ ] **Step 3: Implement WorkflowService**

The service owns loading, bundle validation, catalog, planning, run-store
creation, registry construction, execution, and artifact lookup. CLI performs
argument parsing only.

- [ ] **Step 4: Implement the thin entrypoint**

```python
#!/usr/bin/env python3
from dual_frequency.application.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run CLI smoke with an in-memory deterministic registry**

Execute `validate`, `plan`, and `run --through report` on a synthetic bundle.
Expected: generic reports, no legacy imports, and no expensive process.

- [ ] **Step 6: Commit**

```bash
git add my_helper/fiber/core/dual_frequency/application \
  my_helper/fiber/pipelines/run_dual_frequency_models.py \
  my_helper/fiber/core/dual_frequency/tests/test_application_cli.py
git commit -m "feat: expose dual-frequency workflow service"
```

---

### Task 9: Extract Reference Direct-Voxel Backend

**Files:**
- Create: `my_helper/fiber/core/dual_frequency/backends/protocols.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/direct_voxel/kernel.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/direct_voxel/source_resolver.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/direct_voxel/reference.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_reference_direct_voxel.py`
- Test source: bounded completed reference-direct fixtures.

**Interfaces:**
- Produces: `ReferenceDirectVoxelBackend.run(ObservedRequest) -> ObservedResult`
- Produces pure LOOCV/grid/source functions with array inputs.

- [ ] **Step 1: Write failing synthetic kernel tests**

Cover hard computability, fold leakage, finite predictions, MAE/RMSE status, Q2/
rho report-only behavior, pre-specified acceptance, and scan fallback ordering.

- [ ] **Step 2: Write failing bounded golden tests**

Load only the completed MDS-UPDRS III reference-direct fixture. Assert exact
identity/source/tau/Coverage/masks and allclose weights/scores/predictions.

- [ ] **Step 3: Run tests and verify RED**

Expected: backend missing.

- [ ] **Step 4: Extract generic numerical functions**

Move mathematics out of
`stnsnr_hf_direct_voxel_posthoc_threshold_scan.py`; do not import that module.
Inputs include arrays, subject order, grid, model direction, and random settings.
Outputs are generic records and explicit artifacts.

- [ ] **Step 5: Run focused, bounded parity, and predecessor selftests**

No ULF or MDS-UPDRS IV numeric parity is required in this task.

- [ ] **Step 6: Register the backend in the generic registry and commit**

```bash
git add my_helper/fiber/core/dual_frequency/backends \
  my_helper/fiber/core/dual_frequency/tests/test_reference_direct_voxel.py
git commit -m "feat: extract reference direct-voxel backend"
```

---

### Task 10: Extract Reference Normative-Fiber Backend And Shared Score

**Files:**
- Create: `my_helper/fiber/core/dual_frequency/backends/normative_fiber/coverage.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/normative_fiber/scoring.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/normative_fiber/reference.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_fiber_scoring.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_reference_fiber.py`
- Test source: completed dTOR/MGH/PPMI reference-fiber fixtures.

**Interfaces:**
- Produces: `ReferenceFiberBackend.run(ObservedRequest) -> ObservedResult`
- Produces: `score_signed_fibers(exposure, weights, fiber_ids, settings) -> FiberScoreResult`

- [ ] **Step 1: Write failing score-policy tests**

Test finite-weight intersection, deterministic fiber-ID tie breaking,
`200/100/20`, one-sided status, full/fold recomputation, and held-out leakage
prevention.

- [ ] **Step 2: Write failing source/resolver and connectome-role tests**

Use generic connectome IDs. Verify robustness and primary-formal behavior comes
from roles.

- [ ] **Step 3: Write bounded golden tests**

Compare completed dTOR full outputs and MGH/PPMI observed/final outputs only.
Do not invent formal/OSS parity for robustness connectomes.

- [ ] **Step 4: Extract generic coverage, weights, resolver, and score kernels**

Do not import `stnsnr_hf_normative_fiber_smoke` or
`stnsnr_normative_fiber_score`.

- [ ] **Step 5: Run focused and bounded tests; commit**

```bash
git add my_helper/fiber/core/dual_frequency/backends/normative_fiber \
  my_helper/fiber/core/dual_frequency/tests/test_fiber_scoring.py \
  my_helper/fiber/core/dual_frequency/tests/test_reference_fiber.py
git commit -m "feat: extract reference normative-fiber backend"
```

---

### Task 11: Extract DeltaReferenceScore And Add-On Direct-Voxel Backend

**Files:**
- Create: `my_helper/fiber/core/dual_frequency/backends/delta_reference/direct_voxel.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/interaction/reference_overlap.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/interaction/branch_resolver.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/direct_voxel/addon.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_delta_reference_direct.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_addon_direct_voxel.py`

**Interfaces:**
- Produces: `build_delta_reference_voxel(...) -> DeltaReferenceBundle`
- Produces: `AddonDirectVoxelBackend.run(ObservedRequest) -> ObservedResult`

- [ ] **Step 1: Write failing DeltaReferenceScore tests**

Assert fold-specific reference training excludes held-out subjects, selected
reference tau/Coverage remains locked, adequate/limited are valid, extreme
out-of-support is invalid, and invalid adjusted input leaves no-delta runnable.

- [ ] **Step 2: Write failing overlap/nuisance tests**

Reference absent means infinite overlap threshold and raw add-on exposure.
No-delta uses `Y_post ~ Y_reference`; adjusted adds DeltaReferenceScore.

- [ ] **Step 3: Write state/backend integration tests**

Cover one-way source-failure fallback. The predecessor add-on direct tasks
failed, so tests are synthetic/smoke only and must not claim numeric parity.

- [ ] **Step 4: Extract generic kernels without legacy imports**

Move reusable math from `legacy_ulf_direct.py` and
`stnsnr_ulf_direct_voxel_observed.py`. Keep project exposure discovery outside
the backend.

- [ ] **Step 5: Run focused smoke and commit**

```bash
git add my_helper/fiber/core/dual_frequency/backends/delta_reference \
  my_helper/fiber/core/dual_frequency/backends/interaction \
  my_helper/fiber/core/dual_frequency/backends/direct_voxel/addon.py \
  my_helper/fiber/core/dual_frequency/tests/test_delta_reference_direct.py \
  my_helper/fiber/core/dual_frequency/tests/test_addon_direct_voxel.py
git commit -m "feat: extract add-on direct-voxel backend"
```

---

### Task 12: Extract Add-On Normative-Fiber Backend

**Files:**
- Create: `my_helper/fiber/core/dual_frequency/backends/delta_reference/normative_fiber.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/normative_fiber/addon.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_delta_reference_fiber.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_addon_fiber.py`
- Test source: completed chronic dTOR add-on-fiber stages only.

**Interfaces:**
- Produces: `build_delta_reference_fiber(...) -> DeltaReferenceBundle`
- Produces: `AddonFiberBackend.run(ObservedRequest) -> ObservedResult`

- [ ] **Step 1: Write failing support/overlap tests**

Cover matched reference feature identity, HF-component support, reference-
overlap exclusion after candidate creation, branch-specific nuisance weights,
and the shared `200/100/20` score.

- [ ] **Step 2: Write failing bounded parity tests**

Compare only completed chronic dTOR preprocessing, resolver, final, controls,
formal inputs, cheap sensitivity inputs, and neighborhood artifacts. Exclude
failed OSS and partial jitter.

- [ ] **Step 3: Extract generic kernels**

Do not import `legacy_ulf_fiber.py` or
`stnsnr_ulf_normative_fiber_observed.py`. Use explicit connectome and artifact
references.

- [ ] **Step 4: Run focused, bounded, and one-way fallback tests**

Expected: completed-scope parity passes; uncompleted paths run synthetic smoke
only.

- [ ] **Step 5: Commit**

```bash
git add my_helper/fiber/core/dual_frequency/backends/delta_reference/normative_fiber.py \
  my_helper/fiber/core/dual_frequency/backends/normative_fiber/addon.py \
  my_helper/fiber/core/dual_frequency/tests/test_delta_reference_fiber.py \
  my_helper/fiber/core/dual_frequency/tests/test_addon_fiber.py
git commit -m "feat: extract add-on normative-fiber backend"
```

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

- [ ] **Step 1: Write failing final-only and no-feedback tests**

Reject non-final branches, missing final axes, and outputs that attempt to write
classification fields.

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
- Create: `my_helper/fiber/core/dual_frequency/backends/activation/canonical_mapping.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/activation/ppam.py`
- Create: `my_helper/fiber/core/dual_frequency/backends/activation/ossdbs.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_activation_universe.py`
- Create: `my_helper/fiber/core/dual_frequency/tests/test_oss_backend.py`

**Interfaces:**
- Produces: `ActivationBackend.materialize(ActivationRequest) -> ActivationArtifact`
- Produces: reusable canonical pPAM cache independent of scale/endpoint/final.

- [ ] **Step 1: Write failing universe and identity tests**

Assert the universe is derived from minimum formal tau/Coverage before weights,
signs, final-axis subset, or reference-overlap exclusion. Scale/final changes do
not alter the producer key.

- [ ] **Step 2: Write failing mapping and threshold tests**

Assert:

```python
merged = np.maximum(probability_right, probability_left_to_right)
binary = (merged >= 0.5).astype(np.float32)
```

Require exact canonical fiber IDs and deterministic endpoint subsetting.

- [ ] **Step 3: Write bounded OSS acceptance tests**

Validate all completed HF dTOR cache metadata/hashes, replay mapping/union/
threshold/subset, compare 48 stratified fibers across three subjects, and run
one minimal subject/component solver smoke. Never generate the full universe.

- [ ] **Step 4: Implement generic OSS orchestration**

Remove dTOR name checks. Require the `activation_sensitivity_enabled` role,
explicit OSS backend/version, exact subject-side frequency maps, row checkpoints,
three default row workers, and deterministic merge order.

- [ ] **Step 5: Verify expensive-miss blocking**

Delete only a temporary synthetic cache row and run acceptance mode. Expected:
`missing_acceptance_fixture`; no OSS process starts.

- [ ] **Step 6: Commit**

```bash
git add my_helper/fiber/core/dual_frequency/backends/activation \
  my_helper/fiber/core/dual_frequency/tests/test_activation_universe.py \
  my_helper/fiber/core/dual_frequency/tests/test_oss_backend.py
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
aliases, filename discovery, and old summary roots.

- [ ] **Step 2: Write failing runtime import-isolation test**

Install an import blocker for names matching:

```text
legacy_*
stnsnr_*
run_stnsnr_*
my_helper.fiber.projects.stnsnr.migration
my_helper.fiber.projects.stnsnr.acceptance
```

Import and construct the production `WorkflowService`; expected behavior after
implementation is success.

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
namespace.

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
and a fake activation backend. Assert one final/closed state per endpoint.

- [ ] **Step 2: Add the named III/IV lightweight smoke**

Use the new STNSNr bundle/profile and existing exact caches. MDS-UPDRS III and
IV traverse ordinary catalog/DAG paths; IV immediate is `not_configured`.
Use only internal-test permutation/bootstrap/jitter counts and block expensive
misses.

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

Expected: all tests pass, compile succeeds, and diff check is empty.

- [ ] **Step 5: Run runtime isolation scans**

```bash
rg -n "legacy_|stnsnr_|run_stnsnr|frequency_1_reference|frequency_2_addon|\bHF\b|\bULF\b|\bdTOR\b" \
  my_helper/fiber/core/dual_frequency \
  my_helper/fiber/pipelines/run_dual_frequency_models.py \
  --glob '!tests/**'
```

Expected: no production hits. Test fixtures may mention forbidden names only in
negative assertions.

- [ ] **Step 6: Audit artifacts and process state**

Confirm every smoke task has a terminal record, every realized final has at most
one final ID, report/index/manifests agree, old output trees are unchanged, and
no Lead-DBS/OSS/model process remains active.

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

## Final Acceptance Checklist

- [ ] `dual_frequency_v1` is the only production schema.
- [ ] Production starts from a validated `DualFrequencyStudyBundle`.
- [ ] All scales use identical task factories and status fields.
- [ ] Four model families and all non-deferred Rounds are represented.
- [ ] One-way fallback truth table passes exactly.
- [ ] Generic runtime has no predecessor/migration/acceptance imports.
- [ ] Connectome behavior is role-based.
- [ ] Scientific caches exclude scale/run/scheduler identity.
- [ ] OSS activation universe is shared and endpoint-independent.
- [ ] Formal/sensitivity/activation consume only one realized final.
- [ ] Generic reports contain no HF/ULF compatibility aliases.
- [ ] Bounded parity includes only frozen completed scientific tasks.
- [ ] No unfinished predecessor task is assigned numerical parity.
- [ ] No expensive producer starts during acceptance without authorization.
- [ ] Old outputs and the paused run remain immutable.
- [ ] Synthetic, two-scale smoke, bounded parity, import isolation, compile, and
  documentation checks all pass.
