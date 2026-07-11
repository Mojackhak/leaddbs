# Dual-Frequency Core Decoupling Design

> **Purpose.** Replace the remaining STNSNr-specific numerical adapters in the
> configured four-model workflow with a reusable strict dual-frequency core.
> **Workspace.** `/Users/mojackhu/Github/leaddbs`
> **Parent goal.** `my_helper/stnsnr/four_model_yaml_core_refactor_plan.md`
> **Implementation plan.**
> `my_helper/stnsnr/dual_frequency_core_decoupling_implementation_plan.md`
> **Predecessor schema.** `four_model_v1`
> **Target schema.** `dual_frequency_v1`
> **Current branch.** `stnvop`
> **Status.** `design_approved`; `implementation_not_started`;
> `legacy_runtime_still_active`; `partial_numeric_baseline_available`.
> **Last updated.** 2026-07-11

---

Explicit user decisions are authoritative for this design. Existing Markdown,
code, and generated results are evidence, not independent authority. Stop for
clarification if a later implementation discovers a conflict that this design
does not resolve.

## Goal

Create a reusable strict dual-frequency modeling system that preserves the
current four-model mathematics and interaction state machine while removing
STNSNr, HF, ULF, STN, STN+SNr, and dTOR-specific semantics from the runtime
core.

The target runtime must support:

```text
reference component + add-on component
reference direct voxel model
reference normative fiber model
add-on direct voxel model
add-on normative fiber model
```

The default STNSNr profile remains high-frequency reference plus ultra-low-
frequency add-on. The core uses only `reference_component` and
`addon_component` roles. It does not assume that the reference component has a
higher numerical frequency than the add-on component. Frequency values may be
subject- and condition-specific and come from validated stimulation metadata.

## Confirmed Scope

### Strict two-component model

`dual_frequency_v1` supports exactly two modeled frequency components:

```text
reference_component
addon_component
```

N-frequency interaction models are outside this version.

### Stimulation states

The core requires only:

```text
reference_only = reference_component
combined       = reference_component + addon_component
```

`addon_only` is not required and is not modeled by the four-model core.
Combined conditions may expose any configured endpoint phases, including but
not limited to immediate and chronic phases. Phase names are data, not code
branches.

### Statistical model families

The core includes only:

```text
direct voxel
normative connectome fiber
```

ROI/VTA intersection, regional heatmaps, target-level models, anatomical
postprocessing, GUI, and HTTP services remain outside this refactor. A stable
application service is included so a later GUI can call the same API as the
CLI.

### Scale equality

Every configured scale is an equal engineering execution unit. The core has no
default scale, preferred scale, total-scale shortcut, axial-scale shortcut, or
scale-name dispatch. Reporting hierarchy cannot affect task planning, source
resolution, prediction classification, final-model realization, formal
inference, sensitivity, activation analysis, or artifact generation.

## Chosen Migration Strategy

Use incremental contract-driven replacement:

1. define the generic schema, study bundle, records, and backend protocols;
2. preserve existing numerical kernels long enough to build bounded golden
   fixtures;
3. extract one generic numerical backend at a time;
4. run structural tests, lightweight smoke tests, and available golden parity
   tests before switching the default registry;
5. prohibit legacy runtime fallback after each registry switch; and
6. remove all eight legacy adapters from the runtime registry after their
   replacements pass the applicable acceptance scope.

This is an architecture migration, not a model redesign. Scientific formulas,
source selection, prediction classification, and branch roles remain unchanged
except for the explicit 2026-07-11 clarification that intended adjusted
`absent_no_stable_grid` permits one-way accepted no-delta fallback. No other
final-model rule changes.

## Target Package Boundary

```text
my_helper/fiber/core/dual_frequency/
  contracts/
  config/
  catalog/
  workflow/
  backends/
    direct_voxel/
    normative_fiber/
    delta_reference/
    interaction/
    formal/
    sensitivity/
    activation/
  cache/
  reporting/
  application/
```

Responsibilities:

- `contracts`: immutable study, endpoint, feature-axis, source, final-model,
  request, result, and artifact records;
- `config`: strict `dual_frequency_v1` schema loading and typed resolved
  configuration;
- `catalog`: scale/condition/phase endpoint discovery;
- `workflow`: dependency planning, state transitions, execution, resume, and
  endpoint failure isolation;
- `backends`: scientific array-in/record-out implementations;
- `cache`: scientific identities and content-addressed artifacts;
- `reporting`: generic endpoint, artifact, and run reports;
- `application`: `WorkflowService`, shared by CLI, tests, and a future GUI.

The project boundary is separate:

```text
my_helper/fiber/projects/stnsnr/
  importer/
  profiles/
  migration/
  acceptance/
  legacy/
```

`migration`, `acceptance`, and `legacy` are not runtime dependencies. The
default registry, production CLI, DAG, scientific backends, cache, and reports
must not import them.

## Stable Interfaces

The target service contracts are conceptually:

```python
StudyImporter.build_bundle(...) -> DualFrequencyStudyBundle
ObservedBackend.run(request) -> ObservedResult
SourceResolver.resolve(grid_results) -> SourceRecord
FinalModelResolver.realize(branch_records) -> FinalModelRecord
FormalBackend.run(final_record, request) -> FormalResult
SensitivityBackend.run(final_record, request) -> SensitivityResult
ActivationBackend.materialize(cache_request) -> ActivationArtifact
ReportingBackend.render(run_records) -> ReportArtifacts
```

Scientific backends receive typed requests and explicit artifact references.
They do not receive unresolved YAML, read raw project workbooks, infer meaning
from directory names, search a `latest` directory, or discover another task's
outputs implicitly.

## Canonical Study Input

Project-specific raw data first becomes a validated
`DualFrequencyStudyBundle`. The model core does not read project-specific Excel
layouts or Lead-DBS naming conventions directly.

The bundle contains at least:

```text
subjects.parquet
clinical_endpoints.parquet
stimulation_conditions.parquet
component_exposure_index.parquet
connectome_registry.json
spatial_manifest.json
bundle_manifest.json
```

All relations use stable IDs. The bundle manifest records schema version,
input hashes, subject order, units, spatial identity, importer version, and
provenance.

The STNSNr importer is project-specific by necessity, but it is a data-ingest
boundary rather than a scientific model adapter. Another project may implement
a different importer and produce the same bundle contract without modifying
the core.

## YAML Profiles

The public configuration remains split into:

```text
study.yaml
scales.yaml
model.yaml
workflow.yaml
```

### Study profile

The study profile defines component and condition roles, spatial resources,
connectomes, and external data assets. Labels are descriptive only:

```yaml
schema_version: dual_frequency_v1

components:
  reference_component:
    label: high_frequency
    frequency_source: stimulation_metadata
  addon_component:
    label: ultra_low_frequency
    frequency_source: stimulation_metadata

conditions:
  reference_only:
    components: [reference_component]
  combined:
    components: [reference_component, addon_component]
```

Connectome scheduling is role-based:

```text
observed_robustness
primary_formal
activation_sensitivity_enabled
```

The core never tests for PPMI, MGH, or dTOR names. The default STNSNr profile
may continue to assign PPMI/MGH to observed robustness and dTOR to primary
formal plus activation sensitivity.

### Scale profile

Each scale defines only:

```text
scale_id
label
direction
minimum subjects
reference endpoint binding
zero or more combined endpoint bindings
```

There is no default scale. Missing phase bindings produce explicit catalog
states and do not trigger substitution.

### Model profile

The model profile contains scientific parameters for:

- direct-voxel pre-specified tau, scan grid, computability, formal inference,
  and sensitivity;
- normative-fiber tau/Coverage, signed-fiber score, controls, formal inference,
  and sensitivity;
- DeltaReferenceScore support and branch realization;
- activation sensitivity and pPAM scoring.

The profile does not expose the direct-voxel candidate threshold. The runtime
derives it from the minimum formal tau grid value. Smoke/equivalence iteration
counts are internal tests, not study parameters. The schema rejects hidden test
fields and project-specific aliases.

### Workflow profile

The workflow selects scales, phases, model families, connectome roles, and the
execution cutoff. It also controls resume, force, endpoint failure policy,
workers, and expensive-producer authorization. Runtime scheduling parameters
do not alter scientific cache identity.

## Endpoint DAG

Each scale independently expands into:

```text
A = reference direct voxel
B = reference normative fiber x configured connectomes
C = add-on direct voxel x configured combined phases
D = add-on normative fiber x configured phases/connectomes
```

Each executable endpoint follows:

```text
input readiness
-> exposure/sidecar readiness
-> observed grid
-> source resolver
-> prediction classification
-> branch realization
-> unique final model
-> formal
-> sensitivity/activation
-> report
```

An endpoint failure remains local. The batch continues independent endpoints
and returns nonzero when the declared failure policy requires it.

## Preserved Interaction State Machine

The HF/ULF interaction state machine is preserved under generic role names,
including the confirmed one-way fallback clarification below.

### Reference model

Each reference endpoint independently receives:

```text
reference_source_status:
  pre_specified_accepted
  scan_fallback_accepted
  absent_no_stable_grid

reference_prediction_status:
  error_predictive
  error_nonpredictive
  not_applicable
```

`error_predictive` remains defined by both model MAE and model RMSE improving
over their baseline-only counterparts. Q2 and LOOCV Spearman rho remain report
metrics and do not become hard gates.

### Add-on model

If the matched reference source is absent:

```text
run no_delta_reference only
reference-overlap threshold = +infinity
add-on exposure remains unexcluded
```

If the matched reference source exists, use the same selected reference
tau/Coverage for all held-out subjects. Each held-out subject's
DeltaReferenceScore uses a reference model trained without that subject.

DeltaReferenceScore support statuses map as follows:

```text
adequate -> input valid
limited -> input valid, limitation reported
invalid_extreme_out_of_support -> adjusted branch input failure
```

When DeltaReferenceScore inputs are valid, run both:

```text
no_delta_reference
delta_reference_adjusted
```

Each branch independently runs the add-on tau/Coverage resolver.

Branch roles are:

```text
reference error_predictive    -> adjusted intended primary
reference error_nonpredictive -> no-delta intended primary
```

Fallback is intentionally one-way. When `delta_reference_adjusted` is the
intended primary and it has an input failure, design failure, or
`absent_no_stable_grid`, an accepted `no_delta_reference` branch becomes
`fallback_final`. When `no_delta_reference` is the intended primary, an
accepted adjusted comparison branch cannot be promoted after no-delta failure;
the endpoint records `no_final_model`. Technical execution failures never
trigger fallback. Formal, sensitivity, OSS, and reporting results never change
source, prediction, branch-role, or final-model status.

## Final States

Every endpoint/model family terminates in exactly one of:

```text
final_model_realized
fallback_final_realized
no_final_model
not_configured
input_failure
design_failure
```

At most one model is realized as final. Comparison branches and robustness
connectomes do not become additional final models unless the configured role
and state machine explicitly realize them.

## Normative-Fiber Score

The current signed-fiber minimum-count score remains unchanged. Valid fibers
are the intersection of selected tau/Coverage support and finite weights. The
score continues to use the configured sweet, sour, and weighted-peak fractions
with the `200/100/20` minimum-count policy. Full-sample and LOOCV folds must
recompute coverage, weights, signs, rankings, and selected IDs without using
held-out information.

The same score policy applies to reference fiber, realized add-on fiber, and
OSS/pPAM sensitivity.

## OSS / pPAM Activation Sensitivity

OSS participates only as activation sensitivity for a realized final
normative-fiber model whose connectome has the
`activation_sensitivity_enabled` role. It does not run for direct voxel, select
tau/Coverage, replace the observed final model, or feed back into classification.

### Activation universe

Do not run expensive OSS simulation for every fiber in the whole connectome.
Build a scale- and endpoint-independent universe from the most permissive
formal tau/Coverage boundary:

```text
F_OSS_universe = F_coverage(tau_min, coverage_min)
```

Endpoint final fibers must be a subset of this universe. Endpoint weights,
signed-fiber selection, and reference-overlap exclusion are not applied when
the universe is generated.

### Canonical representation

Cache continuous activation probability. Map left stimulation geometry to the
right canonical space before OSS modeling, then merge left-to-right and right
activation by maximum probability:

```text
p(A_i,f) = max(p(A_right_i,f), p(A_left_to_right_i,f))
```

The model sensitivity uses:

```text
X_OSS_i,f = 1[p(A_i,f) >= 0.5]
```

Each endpoint subsets the cached universe by its final valid feature axis and
refits training-fold weights and signed-fiber rankings. The final fit uses the
same normative-fiber scoring policy as the non-OSS model.

### Cache granularity

OSS scientific identity is based on subject, stimulation condition, component,
connectome/fiber identity, spatial transform, OSS parameters, backend version,
and input hashes. It does not include scale, endpoint, final branch, worker
count, run ID, or task order.

## Content-Addressed Cache

Expensive run-independent artifacts live outside endpoint run roots:

```text
cache/
  study_bundles/
  voxel_exposures/
  fiber_exposures/
  activation_universes/
  oss_rows/
```

A scientific cache key contains only values that can change numerical content:

```text
input geometry hash
stimulation settings hash
component/frequency metadata hash
spatial transform hash
connectome/fiber identity hash
backend name and version
scientific parameter hash
```

Scale IDs, endpoint IDs, run IDs, workers, retries, and scheduling order are
excluded. Exact identity matches are reused automatically. A cache artifact
with different scientific content is a `cache_identity_mismatch` and cannot be
used as an approximate substitute.

Different array order is not a scientific mismatch when unique subject/fiber
IDs and per-item hashes prove identical content. In that case, create a
deterministically reindexed view and record a new view manifest. Never infer
compatibility from array position.

Production may create a missing expensive cache only after explicit
`--allow-expensive-producers` authorization. Acceptance/smoke runs report
`missing_acceptance_fixture` instead of silently starting an expensive build.

## Application And CLI Contract

`WorkflowService` is the single application API for CLI, tests, and a future
GUI. GUI and HTTP transport remain deferred.

Public CLI subcommands are:

```text
validate
plan
run
status
artifacts
```

Rules:

- `--scale` is repeatable;
- `--scale` and `--all-available` are mutually exclusive;
- omitting both is an error;
- selecting an add-on endpoint automatically adds its matched reference
  dependency;
- `--through observed|formal|sensitivity|report` is dependency-complete;
- `--resume` requires identical configured and input identity;
- expensive cache misses require explicit authorization.

## Error Model

```text
configuration_error
bundle_validation_error
endpoint_input_failure
branch_input_failure
branch_design_failure
cache_identity_mismatch
expensive_producer_not_authorized
no_final_model
backend_execution_failure
```

Configuration and bundle errors reject the run. Endpoint and branch failures
remain local. `no_final_model` is a closed scientific state, not an unhandled
exception. Backend execution failures preserve checkpoints and provenance,
allow independent endpoints to continue, and contribute to the final process
status.

## Generic Reporting

The reporting backend reads only current-run generic records and outputs only
reference/add-on role fields. It does not emit HF/ULF compatibility aliases,
read legacy summaries, or infer model status from filenames.

Required report domains include:

```text
endpoint and task status
source and prediction status
selected tau/Coverage
DeltaReferenceScore support
intended and realized branch
unique final or no-final status
observed and LOOCV metrics
formal and sensitivity results
activation sensitivity results
artifact index and provenance
```

## Legacy Bridge Replacement

The eight current adapters are replaced as follows:

| Current adapter | Generic replacement |
|---|---|
| `legacy_hf_direct.py` | `direct_voxel/reference.py`, `kernel.py`, `source_resolver.py` |
| `legacy_hf_fiber.py` | `normative_fiber/reference.py`, `coverage.py`, `scoring.py` |
| `legacy_ulf_direct.py` | `direct_voxel/addon.py`, `delta_reference/direct_voxel.py`, `interaction/branch_resolver.py` |
| `legacy_ulf_fiber.py` | `normative_fiber/addon.py`, `delta_reference/normative_fiber.py`, `interaction/reference_overlap.py` |
| `legacy_formal.py` | `formal/direct_voxel.py`, `formal/normative_fiber.py` |
| `legacy_sensitivity.py` | explicit tau-neighborhood, spatial-jitter, add-on-exposure, and fiber-control strategies |
| `legacy_oss.py` | `activation/ossdbs.py`, `canonical_mapping.py`, `ppam.py` |
| `legacy_reporting.py` | generic endpoint summary, artifact index, and run report backends |

Each replacement is switched independently after its applicable tests pass.
After a switch, no legacy fallback is permitted. When all replacements pass,
remove the eight adapters from the default runtime registry and move the old
STNSNr analysis entrypoints to the project-level legacy namespace outside the
production Python path.

## Migration And Acceptance Tools

Retain, but do not register, explicit tools for:

```text
old YAML -> dual_frequency_v1 migration
legacy result -> canonical acceptance fixture conversion
numeric parity audit
```

These tools remain available after migration for auditability. They are manual
commands, not product modules. Core code, CLI, DAG, backends, cache, and
reporting cannot import them. New input validation never silently falls back to
legacy interpretation.

The fixture converter is read-only with respect to old results. It writes a new
fixture manifest containing converter version, source paths, source hashes,
output hashes, and conversion rules.

## Bounded Numerical Acceptance

The predecessor `/goal` did not finish its planned real MDS-UPDRS III/IV run.
This decoupling design does not require completing that expensive run solely to
create a broader parity oracle.

### Frozen evidence source

The only real-run numerical baseline is the immutable paused run:

```text
run_id: 20260711T034644Z_d318f177f7f2ac7d
run_commit: e3606e9ba57e83b61a18883b571ebe184029ebc0
configuration_hash: e686212ba6658b2f4b8abf3a94305817555ec334ee9ba07262fbca9190f5f338
planned_tasks: 205
terminal_tasks: 73
completed_tasks: 50
```

Only terminal `completed` scientific tasks with complete, hash-valid artifacts
are eligible for numerical golden parity. A completed reporting task that only
summarizes an upstream failure is structural evidence, not a numerical model
oracle.

### Included real-data numerical scope

The completed evidence currently covers:

1. MDS-UPDRS III HF direct voxel through source/final realization, formal
   permutation/bootstrap, full spatial jitter, selected-source neighborhood,
   and reporting.
2. MDS-UPDRS III HF normative fiber dTOR through sidecars, observed analysis,
   controls, source/final realization, candidate smoke, formal inference,
   complete OSS/pPAM sensitivity, 1,000-replicate spatial jitter, and reporting.
3. MDS-UPDRS III HF normative fiber MGH and PPMI through sidecars, observed
   analysis, controls, source/final realization, and reporting.
4. MDS-UPDRS III chronic add-on normative fiber dTOR through matched-reference
   lock, preprocessing, branch resolver, final realization, plain/burden
   controls, candidate smoke, formal inference, cheap observed sensitivity,
   and selected-source neighborhood.

The fixture manifest must enumerate exact task IDs and artifact hashes. It must
not infer coverage from this prose alone.

### Explicit numerical exclusions

No real-data numerical parity is required for:

- any task that was pending or unstarted when the predecessor run stopped;
- the chronic add-on dTOR jitter checkpoint at `388/1000`;
- failed add-on direct-voxel tasks;
- failed add-on normative-fiber OSS preparation;
- skipped dependency or skipped gate tasks;
- MDS-UPDRS IV model paths not completed by the paused run;
- any other model/phase/connectome path without a terminal completed scientific
  artifact in the frozen run.

The original run is not resumed, repaired in place, or completed merely to
expand numerical acceptance. Later results may be added only by an explicit
future decision and a new immutable fixture manifest.

### What still must be tested outside numerical parity

Every generic backend and state-machine path still requires:

- contract and unit tests;
- deterministic synthetic tests;
- lightweight end-to-end smoke execution;
- import-isolation tests;
- artifact/provenance validation; and
- failure/fallback closure tests.

For a path without completed predecessor evidence, these tests prove that the
new implementation is coherent and executable; they do not claim numerical
equivalence to a result that never existed.

### Numeric tolerances

Where a completed golden artifact exists:

- endpoint identity, source status, selected tau/Coverage, feature IDs, branch
  role, final status, masks, binary pPAM, and selected fiber IDs must match
  exactly;
- weights, scores, and LOOCV predictions use `rtol=1e-8`, `atol=1e-10`;
- continuous OSS activation spot checks use `rtol=1e-6`, `atol=1e-8`;
- bounded permutation/bootstrap/jitter replay uses the same seed and the same
  prefix of the predecessor sampling order.

Acceptance does not rerun full formal resampling or 1,000-replicate jitter.
The fixture converter records hashes and provenance for complete predecessor
outputs and extracts deterministic bounded slices needed by smoke parity. The
new backend replays only fixed internal-test prefixes, for example ten
permutations, ten bootstrap samples, and five jitter replicates, and compares
them with the corresponding frozen slices. These counts are acceptance-test
constants, not public model parameters or reportable scientific results.

OSS acceptance additionally performs full lightweight metadata/mapping/union/
threshold/subset replay and a deterministic stratified numerical sample of 48
fibers across three representative subjects. One minimal subject/component OSS
solver smoke proves execution without regenerating the full activation universe.

## Test Matrix

1. schema, bundle, identity, catalog, planner, state, cache, and report unit
   tests;
2. a synthetic profile with no STNSNr/HF/ULF/STN/dTOR names;
3. all-scale equality and missing-phase catalog tests;
4. matched-reference, DeltaReferenceScore, two-branch, fallback, and no-final
   fixtures;
5. legacy import blockers with migration tools removed from `PYTHONPATH`;
6. bounded golden replay for the completed scope above;
7. lightweight two-scale smoke using MDS-UPDRS III and IV without expensive
   cache generation;
8. OSS cache, canonical mapping, threshold, subset, and sampled numerical tests;
9. CLI `validate/plan/run/status/artifacts` tests; and
10. documentation, schema, compile, and diff checks.

## Full-Rerun Independence Criterion

A production full rerun from validated project inputs must follow:

```text
raw project inputs
-> new project importer
-> DualFrequencyStudyBundle
-> dual_frequency_v1 validation
-> generic catalog and DAG
-> generic numerical backends
-> generic formal/sensitivity/activation
-> generic reporting
```

It must succeed with the migration, acceptance, and legacy directories removed
from the Python path. It cannot import `run_stnsnr_*`, `legacy_*`, or
`stnsnr_*` analysis modules and cannot read old output trees. Lead-DBS,
OSS-DBS, NIfTI, and connectome libraries remain external scientific engines,
accessed through generic provider/backend contracts.

The model-core full rerun begins from standardized clinical/stimulation inputs
and Lead-DBS derivatives. Electrode reconstruction and raw-image-to-E-field
processing remain upstream external production stages.

## Migration Phases

1. freeze existing completed artifacts and write the bounded fixture manifest;
2. implement `dual_frequency_v1` schemas and typed contracts;
3. implement the STNSNr importer and canonical StudyBundle;
4. move orchestration into the new generic package;
5. replace reference direct-voxel and normative-fiber backends;
6. replace DeltaReferenceScore and add-on backends;
7. replace formal, sensitivity, and reporting backends;
8. implement activation-universe cache and replace OSS;
9. remove legacy default registration and run import-isolation tests; and
10. complete bounded parity, synthetic, smoke, provenance, and documentation
    acceptance.

Each phase is test-first and independently committed. A parity failure stops
that backend migration. No phase overwrites `/Volumes/VAL/STNSNr/summary` or
the immutable configured run.

## Success Criteria

The design is implemented only when:

1. the production runtime accepts only `dual_frequency_v1` and validated study
   bundles;
2. no generic runtime module contains STNSNr, HF, ULF, STN, STN+SNr, dTOR, or
   scale-name dispatch semantics;
3. the original interaction state machine and four model families remain
   intact;
4. all configured scales receive equal DAG and output treatment;
5. connectome scheduling is role-based;
6. expensive caches are scientifically keyed and reusable across scales/runs;
7. OSS uses the shared activation universe and final-axis subset;
8. exactly one final model or an explicit closed terminal state exists per
   endpoint/model family;
9. migration/acceptance tools remain non-runtime dependencies;
10. bounded numerical parity passes for every eligible completed predecessor
    artifact and is not claimed for unfinished predecessor paths; and
11. synthetic, smoke, import-isolation, cache, provenance, and report tests pass.

## Deferred Work

```text
N-frequency interaction models
addon-only clinical models
ROI/VTA postprocessing and regional heatmaps
target-level model families
GUI and HTTP transport
raw imaging and electrode reconstruction workflow
completion of the paused predecessor real-data run solely for parity expansion
```
