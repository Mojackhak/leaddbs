# Dual-Frequency Four-Model YAML Core Goal

> **Purpose.** Define the authoritative `/goal` contract for replacing the
> STNSNr-oriented `four_model_v1` runtime with a reusable strict dual-frequency
> four-model core.
> **Workspace.** `/Users/mojackhu/Github/leaddbs`
> **Parent goal.** `my_helper/stnsnr/four_model_execution_plan.md`
> **Approved design.**
> `my_helper/stnsnr/dual_frequency_core_decoupling_design.md`
> **Implementation plan.**
> `my_helper/stnsnr/dual_frequency_core_decoupling_implementation_plan.md`
> **Scientific model specifications.** `my_helper/stnsnr/model_summaries/`
> **Current branch.** `stnvop`
> **Target schema.** `dual_frequency_v1`
> **Status.** `design_approved`; `implementation_not_started`;
> `predecessor_implementation_paused`; `partial_numeric_evidence_frozen`;
> `legacy_runtime_still_active`.
> **Last updated.** 2026-07-11

---

Explicit user decisions are the model-contract authority. The approved design
controls target architecture and this document controls implementation scope and
acceptance. Existing code, `four_model_v1` documents, legacy scripts, and
generated outputs are predecessor evidence only. When they conflict with this
target contract, do not preserve the conflict as compatibility behavior.

## Summary

Build a strict two-component, YAML-driven outcome-modeling system with four
model families:

```text
reference direct voxel
reference normative fiber
add-on direct voxel
add-on normative fiber
```

The default STNSNr profile labels the reference component HF and the add-on
component ULF. Generic runtime code uses only `reference_component` and
`addon_component`; it does not infer role from numerical frequency, protocol
name, project name, scale name, or connectome name.

The implemented `four_model_v1` catalog/DAG/executor is a predecessor
foundation. It remains paused and its scientific services still use eight
STNSNr-oriented bridge modules. The target implementation extracts reusable
numerical backends, introduces a canonical `DualFrequencyStudyBundle`, moves
expensive artifacts into scientifically keyed caches, and removes all legacy
runtime imports.

The predecessor real-data acceptance run did not finish. Numeric equivalence is
therefore bounded to its terminal completed, hash-valid scientific artifacts.
Unfinished paths require contract, synthetic, and lightweight smoke tests but
do not require comparison with nonexistent predecessor results.

## Goal And Success Criteria

The goal is complete only when one public library/CLI can:

1. validate a `dual_frequency_v1` configuration and canonical study bundle;
2. select arbitrary configured scales or all available scales without defaults;
3. resolve matched reference-only and combined endpoint rows by stable IDs;
4. compile the complete four-model dependency DAG for each endpoint;
5. execute observed grids and endpoint-specific source resolvers;
6. assign reference prediction status and the add-on intended branch;
7. realize exactly one primary/fallback final model or a closed terminal state;
8. attach formal, sensitivity, jitter, and activation tasks only to that final;
9. isolate endpoint-local failures while continuing independent tasks;
10. produce generic manifests, artifact indexes, statuses, and reports;
11. reuse exact content-addressed exposure and activation artifacts across
    scales and runs; and
12. run from validated project inputs without importing any predecessor,
    migration, acceptance, or STNSNr analysis module.

Implementation is not complete while any production path imports a
`legacy_*`, `stnsnr_*`, or `run_stnsnr_*` numerical module.

## Governing Invariants

### Strict dual-frequency scope

```text
reference_component
addon_component
```

Roles are independent of frequency ordering. The default profile may be HF
reference plus ULF add-on; another profile may use different frequencies
without code changes.

The modeled stimulation states are:

```text
reference_only = reference_component
combined       = reference_component + addon_component
```

`addon_only` and N-frequency interaction models are outside
`dual_frequency_v1`.

### Scale equality

```text
all configured scales are equal execution units
```

There is no default, primary engineering, total, axial, or first-pass scale.
Clinical reporting hierarchy is downstream metadata and cannot affect the
catalog, DAG, resolver, branch role, final model, resampling, sensitivity,
activation, or output generation.

### Statistical domains

```text
direct voxel:
  configured right-canonical whole-brain mask

normative fiber:
  configured whole structural connectome before tau/Coverage filtering
```

An anatomical ROI is not a core model input. ROI/VTA overlap, regional
heatmaps, target summaries, and other anatomical postprocessing remain deferred.

### Scientific classification

Each executable source resolver first decides whether a stable source exists:

```text
pre_specified_accepted
scan_fallback_accepted
absent_no_stable_grid
```

Prediction status is assigned only after a source exists:

```text
error_predictive:
  MAE_model < MAE_baseline
  and RMSE_model < RMSE_baseline

error_nonpredictive:
  a source exists but either error comparison fails

not_applicable:
  no source exists
```

Q2, LOOCV Spearman rho, nominal p values, bootstrap results, jitter, controls,
and activation results remain report/robustness evidence. They do not change
source, prediction, branch role, or final realization.

## Target Runtime Architecture

The reusable runtime package is:

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

The project boundary is separate:

```text
my_helper/fiber/projects/stnsnr/
  importer/
  profiles/
  migration/
  acceptance/
  legacy/
```

Only `importer` and validated project profiles participate before the canonical
bundle boundary. `migration`, `acceptance`, and `legacy` are retained manual
tools/evidence but are not production dependencies.

`WorkflowService` is the single application API used by CLI, tests, and a
future GUI. The CLI cannot contain a second orchestration implementation.

## Canonical Study Bundle

The core consumes a validated `DualFrequencyStudyBundle`, not project-specific
Excel layouts or Lead-DBS path conventions. The bundle contains at least:

```text
subjects.parquet
clinical_endpoints.parquet
stimulation_conditions.parquet
component_exposure_index.parquet
connectome_registry.json
spatial_manifest.json
bundle_manifest.json
```

Required guarantees:

- stable subject, endpoint, condition, component, and connectome IDs;
- explicit subject and feature order;
- units and coordinate-space identity;
- project importer version and input hashes;
- no semantic inference from filenames;
- no silent clinical-row or scale substitution; and
- immutable bundle content after validation.

The STNSNr importer may read the current clinical/stimulation workbooks and
Lead-DBS derivatives, but it must emit this generic contract before the model
core runs.

## YAML Contract

The public configuration uses four strict profiles:

```text
study.yaml
scales.yaml
model.yaml
workflow.yaml
```

All profiles use:

```yaml
schema_version: dual_frequency_v1
```

### Study profile

Declares:

```text
study ID and bundle/import inputs
reference/add-on component metadata sources
reference-only and combined condition IDs
canonical space, hemisphere, and transform
brainmask
connectomes and role sets
scientific cache root
run output root
```

Connectome roles are:

```text
observed_robustness
primary_formal
activation_sensitivity_enabled
```

The runtime never tests for PPMI, MGH, or dTOR names.

### Scale profile

Each scale declares:

```text
scale_id
label
direction
minimum_subjects
reference endpoint binding
zero or more combined endpoint bindings
```

Missing phases become explicit `not_configured` catalog rows. They are not
copied from another scale.

### Model profile

Declares shared scientific parameters for:

```text
direct-voxel pre-specified tau and scan grid
direct-voxel hard computability
normative-fiber tau/Coverage and scoring policy
DeltaReferenceScore support
formal permutation/bootstrap
selected-source tau neighborhood
spatial jitter
add-on exposure/support/collinearity sensitivities
normative-fiber controls and numeric reporting
activation sensitivity
```

The direct-voxel candidate threshold is not public. It is derived as
`min(tau_grid_v_per_m)` and written only to technical provenance. Smoke and
equivalence counts are fixed internal-test parameters. Schema validation rejects
both fields if supplied through YAML or CLI.

### Workflow profile

Declares:

```text
scale/model/phase/connectome-role selection
through stage
resume/force policy
endpoint failure policy
runtime workers
expensive-producer policy
```

Workers and retry order do not enter scientific cache identity.

### Old configuration handling

The production runtime accepts only `dual_frequency_v1`. A retained manual
migration tool may convert `four_model_v1` into a new profile for review. It is
never imported by the production config loader and no invalid new document is
silently reinterpreted as old YAML.

## CLI And Application Contract

The target entry point is:

```text
my_helper/fiber/pipelines/run_dual_frequency_models.py
```

Subcommands:

```text
validate
plan
run
status
artifacts
```

Selection and execution rules:

```text
--scale              repeatable
--all-available      mutually exclusive with --scale
--models             reference-voxel,reference-fiber,addon-voxel,addon-fiber,all
--phases
--connectomes
--through            observed|formal|sensitivity|report
--resume --run-id
--force [--run-id]
--allow-expensive-producers
```

Omitting both `--scale` and `--all-available` is an error. Selecting an add-on
endpoint automatically adds its matched reference dependency. `--resume`
requires exact resolved configuration, bundle, code, and scientific identity.
`--force` creates a new lineage and never edits an old task record.

`plan` reports exact cache hits/misses and blocked expensive producers. A cache
miss cannot start OSS or another declared expensive producer unless explicitly
authorized. Acceptance/smoke mode never authorizes an expensive miss.

`--through` is dependency-complete:

```text
observed:
  readiness, sidecars, observed grids, resolver prerequisites, final realization

formal:
  observed plus final-model formal permutation/bootstrap

sensitivity:
  formal plus selected-source neighborhood, jitter, controls, and activation

report:
  sensitivity plus endpoint/run summaries and artifact index
```

## Endpoint And Dependency State Machine

### Endpoint identity

```text
endpoint model identity =
  study + scale + endpoint phase + model family + connectome role/ID

task identity =
  endpoint model identity + workflow stage + branch + parameter identity

final model identity =
  endpoint model identity + realized branch + selected source identity
```

Task and final IDs cannot be known by searching an output filename.

### Reference resolution

```text
input/readiness failure:
  endpoint = input_failure
  source/prediction = not_applicable

stable source:
  source = pre_specified_accepted | scan_fallback_accepted
  prediction = error_predictive | error_nonpredictive

no stable source:
  source = absent_no_stable_grid
  prediction = not_applicable
```

### Add-on branch permission

The branches are:

```text
no_delta_reference:
  Y_post ~ Y_reference

delta_reference_adjusted:
  Y_post ~ Y_reference + DeltaReferenceScore
```

If the matched reference source is absent, run no-delta only and use an infinite
reference-overlap threshold. If a reference source exists, build each held-out
DeltaReferenceScore using a reference model trained without that subject.

DeltaReferenceScore support:

```text
adequate -> adjusted input valid
limited  -> adjusted input valid; limitation reported
invalid_extreme_out_of_support or invalid fold/input -> adjusted input failure
```

When adjusted input is valid, run both branches and resolve their sources
independently.

### Intended branch

```text
reference source exists and prediction = error_predictive:
  intended = delta_reference_adjusted

otherwise:
  intended = no_delta_reference
```

### One-way fallback realization

```text
intended branch has accepted source:
  final = intended
  role = primary

intended delta_reference_adjusted has input failure, design failure,
or absent_no_stable_grid, and no_delta_reference has accepted source:
  final = no_delta_reference
  role = fallback_final

intended no_delta_reference fails:
  adjusted comparison cannot be promoted
  final = none
  status = no_final_model

no permitted accepted branch:
  final = none
  status = no_final_model

technical backend execution failure:
  status = execution_failure
  do not auto-promote another branch
```

Prediction status of an accepted add-on branch is reported but does not change
its primary/fallback role. At most one final model enters downstream formal,
sensitivity, activation, and reporting tasks.

### Batch behavior

Endpoint-local input/model/technical failure does not cancel independent
endpoints. The final process status is nonzero when the declared failure policy
contains a failed requested task. Closed `not_configured` states are nonfailure;
`no_final_model` remains an explicit requested-model terminal state.

## Scientific Round Migration Matrix

This matrix inventories scientific functions that the generic implementation
must preserve. Round names retain model-document provenance; they do not define
legacy interfaces or project-specific dispatch.

Parameter classes:

```text
public YAML       versioned scientific/workflow parameter
internal-derived deterministic value from YAML or runtime inputs
internal-test    fixed qualification/smoke value
runtime output   resolver/status/artifact value, never a selector
```

### Reference direct voxel

| Round | Target source | Required behavior |
|---|---|---|
| 0 Input readiness/environment | bundle, scale, workflow | Endpoint failure remains local; no scale substitution. |
| 1 Sidecars/minimal QC | YAML plus internal-derived candidate threshold | Candidate threshold equals minimum formal tau. |
| 2 Observed LOOCV/resolver | model grid/hard filters | Endpoint-specific source and prediction status. |
| 3 Equivalence/smoke | internal-test | Technical qualification only. |
| 4 Formal permutation | realized final | Cannot change classification. |
| 5 Formal bootstrap | realized final | Final source only. |
| 6 Spatial jitter | realized final | Robustness only. |
| 7 Selected-source neighborhood | selected tau/Coverage | `0.9x/1.1x` selected tau; not a source candidate. |
| 8 Report/manifests | runtime records | Generic endpoint output. |

### Add-on direct voxel

| Round | Target source | Required behavior |
|---|---|---|
| 0 Readiness/reference lock | matched reference record | Same scale/phase identity; no global status. |
| 1 Sidecars/overlap/support | bundle, matched source | Branch-specific readiness and support. |
| 2 Observed/resolver/realization | model profile/state machine | Independent branch resolvers; one final or closed absence. |
| 2b Additional phase observed | endpoint binding | Same engineering status as every phase. |
| 3 Equivalence/smoke | internal-test | Technical qualification only. |
| 4 Formal permutation | realized final | Primary or permitted fallback final only. |
| 5 Formal bootstrap | realized final | Primary or permitted fallback final only. |
| 6 Spatial jitter | realized final | Rebuild geometry, overlap, and DeltaReferenceScore. |
| 7 Exposure neighborhood | selected source | Observed sensitivity only. |
| 8 Additional sensitivities/report | model/runtime | Comparison, gain, total exposure, support, collinearity. |

### Reference normative fiber

| Round | Target source | Required behavior |
|---|---|---|
| 0 Input/manifest freeze | bundle/workflow | Immutable endpoint/connectome identity. |
| 1 Sidecar/equivalence | scientific cache/internal-test | Exact subject and feature identity. |
| 2 All-endpoint observed | catalog/connectome roles | Equal factory for every scale. |
| 3 Plain control | model controls | Interpretation QC only. |
| 4 Primary-connectome smoke | internal-test | Technical qualification only. |
| 5 Cheap observed sensitivity | model/connectome roles | No hidden defaults or classification feedback. |
| 5.5 Source/prediction resolver | grid/hard filters | Endpoint-specific final source. |
| 6 Formal resampling | primary-formal role final | Selected source only. |
| 7 Activation sensitivity | activation-enabled role final | Cannot replace final model. |
| 8 Jitter | final | Robustness only. |
| 9 Numeric/report | reporting/runtime | Downstream numeric summaries and artifact index. |

### Add-on normative fiber

| Round | Target source | Required behavior |
|---|---|---|
| 0 Input/reference lock | matched reference/connectome record | Same scale, phase family, and connectome identity. |
| 1 Sidecar/support/equivalence | bundle/cache/internal-test | Branch-specific inputs and support. |
| 2 Observed/resolver/realization | model/state machine | One primary/fallback final or closed absence. |
| 2b Additional phase observed | endpoint binding | No phase hierarchy in engineering. |
| 3 Plain/burden controls | model controls | Interpretation QC only. |
| 4 Primary-connectome smoke | internal-test | Final-source qualification. |
| 5 Cheap observed sensitivity | model profile | Comparison and exposure sensitivities. |
| 6 Selected-source neighborhood | selected source | Observed sensitivity only. |
| 7 Formal resampling | primary-formal role final | Exactly one final. |
| 8 Activation sensitivity | activation-enabled role final | Component/frequency identity required. |
| 9 Jitter | final | Rebuild exposure, overlap, DeltaReferenceScore, and model. |
| 10 Numeric/report | reporting/runtime | Cannot alter classification. |

## Normative-Fiber Scoring Contract

Valid fibers remain:

```text
F_valid = F_coverage intersect F_finite_weights
```

The existing signed-fiber score policy remains shared by reference, realized
add-on, and activation sensitivity:

```text
sweet_fraction = 0.01
sour_fraction = 0.005
weighted_peak_fraction = 0.05
sweet_selected_min_count = 200
sour_selected_min_count = 100
weighted_peak_min_count = 20
```

Every LOOCV fold recomputes coverage, weights, signs, ranks, selected IDs, and
peak aggregation from training subjects only.

## Activation And OSS Contract

Activation sensitivity runs only for a realized normative-fiber final whose
connectome has `activation_sensitivity_enabled`. It does not participate in
source resolution or final realization.

The shared activation universe is scale- and endpoint-independent:

```text
F_activation = F_coverage(tau_min, coverage_min)
```

Do not apply endpoint weights, signed-fiber selection, or reference-overlap
exclusion while constructing this universe. Endpoint final axes are subsets.

For the default OSS backend:

```text
left geometry -> right canonical space
p(A_i,f) = max(p(A_right_i,f), p(A_left_to_right_i,f))
X_OSS_i,f = 1[p(A_i,f) >= 0.5]
```

Cache continuous probability and derive the binary analysis matrix. Endpoint
fits use the final valid feature axis and refit training-fold weights/ranks.

## Content-Addressed Cache Contract

Run-independent expensive artifacts are stored under scientific identities:

```text
study bundles
voxel exposures
fiber exposures
activation universes
OSS rows
```

Scientific identity includes:

```text
input geometry and stimulation hashes
component/frequency metadata hash
spatial transform hash
connectome/fiber identity hash
backend and scientific-version hash
scientific parameter hash
```

It excludes scale, endpoint, branch role, run ID, worker count, retry count, and
completion order. Exact content is reusable across scales and runs. Different
scientific content is `cache_identity_mismatch` and cannot be approximately
reused. Identical IDs in a different order may produce a deterministic reindex
view only after unique IDs and per-item hashes validate.

Every cache artifact records schema/backend version, full inputs, orders, units,
space, environment, code provenance, row statuses, and content hashes.

## Artifact And Provenance Contract

Run root:

```text
<output_root>/dual_frequency_runs/<study_id>/<run_id>/
```

Required run artifacts:

```text
workflow_resolved.yaml
study_bundle_ref.json
endpoint_catalog.csv
execution_plan.json
task_status.csv
run_manifest.json
artifact_index.csv
```

Every task records endpoint/task/final identities, dependencies, bundle/config
hashes, subject/feature order, selected source, statuses, random parameters,
code/environment provenance, cache references, outputs, and terminal status.

Resume reuses only exact task identity and hash-valid artifacts. Force creates a
new lineage. No run modifies the predecessor configured run or
`/Volumes/VAL/STNSNr/summary`.

Generic reports contain only reference/add-on fields. They do not emit HF/ULF
compatibility aliases or discover predecessor output names.

## Legacy Bridge Removal Contract

The target default registry must not import:

```text
legacy_hf_direct.py
legacy_hf_fiber.py
legacy_ulf_direct.py
legacy_ulf_fiber.py
legacy_formal.py
legacy_sensitivity.py
legacy_oss.py
legacy_reporting.py
```

Their generic replacements are defined in the approved design and detailed
implementation plan. After each replacement passes its applicable tests, switch
the registry and prohibit fallback. Move retained old entrypoints to the
project-level legacy namespace outside the production Python path.

Manual migration/fixture conversion/parity tools remain available under the
project boundary for auditability. Production code cannot import them.

## Acceptance Contract

### Structural acceptance for the full target

All target paths require:

- schema and StudyBundle validation tests;
- generic profile tests containing no STNSNr/HF/ULF/STN/dTOR names;
- all-scale catalog and DAG equality tests;
- reference/add-on state-machine and one-way fallback tests;
- backend contract and artifact validation tests;
- cache hit/miss/reindex and expensive-producer authorization tests;
- CLI and `WorkflowService` tests;
- runtime import blockers for legacy/migration/acceptance modules;
- lightweight end-to-end smoke through report; and
- documentation, compile, and diff checks.

MDS-UPDRS III score and MDS-UPDRS IV remain ordinary named real-data smoke
fixtures. MDS-UPDRS IV immediate remains explicit `not_configured`; this is not
a scale-specific code branch.

### Bounded numerical acceptance

The only predecessor numerical source is:

```text
run_id: 20260711T034644Z_d318f177f7f2ac7d
run_commit: e3606e9ba57e83b61a18883b571ebe184029ebc0
configuration_hash: e686212ba6658b2f4b8abf3a94305817555ec334ee9ba07262fbca9190f5f338
planned_tasks: 205
terminal_tasks: 73
completed_tasks: 50
```

Only terminal completed scientific tasks with complete, hash-valid artifacts
enter the golden fixture manifest. Completed numerical evidence covers:

1. MDS-UPDRS III reference direct voxel through final, formal, complete jitter,
   neighborhood sensitivity, and report;
2. MDS-UPDRS III reference dTOR fiber through final, formal, OSS, complete
   jitter, and report;
3. MDS-UPDRS III reference MGH/PPMI fiber observed robustness through final and
   report; and
4. MDS-UPDRS III chronic add-on dTOR fiber through preprocessing, resolver,
   final, controls, formal, cheap sensitivity, and neighborhood sensitivity.

Explicit numerical exclusions:

```text
partial add-on dTOR jitter at 388/1000
failed add-on direct-voxel tasks
failed add-on fiber OSS preparation
skipped, pending, and unstarted tasks
uncompleted MDS-UPDRS IV model paths
every path without a terminal completed scientific artifact
```

Do not resume or complete the predecessor run merely to enlarge the oracle.
Excluded paths receive structural/synthetic/smoke acceptance, not numerical
equivalence claims.

Complete predecessor formal/jitter/OSS products receive hash/provenance
validation. New backends replay only fixed internal-test slices, such as ten
permutations, ten bootstraps, five jitter replicates, and OSS 48-fiber samples
across three representative subjects. These are test constants, not scientific
outputs. Missing acceptance fixtures never trigger expensive generation.

Exact fields include endpoint/source/final identities, tau/Coverage, feature
IDs, masks, binary pPAM, branch roles, and selected fibers. Floating weights,
scores, and predictions use `rtol=1e-8`, `atol=1e-10`; sampled continuous OSS
probability uses `rtol=1e-6`, `atol=1e-8`.

## Implementation Entry

The executable next-stage plan is:

```text
my_helper/stnsnr/dual_frequency_core_decoupling_implementation_plan.md
```

The predecessor
`four_model_yaml_core_refactor_implementation_plan.md` is historical evidence of
the implemented foundation. It is not an instruction source for new runtime
interfaces.

Subagents are permitted for bounded, disjoint tasks. The main implementation
thread owns dependency ordering, integration review, complete tests, acceptance,
documentation-first updates, and final requirement audit.

## Historical Four-Model V1 Checkpoint

The predecessor state is retained only for provenance:

```text
schema: four_model_v1
package: my_helper/fiber/core/outcome_models
entrypoint: my_helper/fiber/pipelines/run_configured_outcome_models.py
status: implementation_paused
legacy bridge modules: 8
configured acceptance run: partial
current legacy output trees: read-only
```

Implemented predecessor foundations include strict YAML loading, endpoint
catalog, planner, executor, run store, records, configured services, formal/
sensitivity dispatch, OSS row resume/cache work, and endpoint reporting.

The paused run discovered and preserved three historical execution failures:
two add-on direct adapter-signature failures and one add-on fiber OSS source-
wiring failure. Later commits repaired those code paths, but the immutable old
run was not edited and no new complete acceptance lineage was created.

All detailed `four_model_v1` field names, HF/ULF branch records, prior CLI
examples, and old run commands belong to Git history and the predecessor
implementation notes. They are not duplicated as target requirements here.

## Deferred Work

```text
completion of the predecessor run solely to expand parity
full expensive all-scale scientific rerun
old output migration or overwrite
addon-only and N-frequency models
ROI/VTA postprocessing and regional heatmaps
target-level model families
GUI and HTTP transport
raw imaging, electrode reconstruction, and upstream E-field generation
new estimators or revised classification rules
```

## Documentation Review Record

Five review passes are required before implementation begins:

1. target-vs-historical separation;
2. scale equality and generic role naming;
3. dependency and one-way fallback closure;
4. Round/cache/activation/interface coverage; and
5. bounded numerical acceptance and current-vs-target wording.

This `/goal` is complete as a design contract only when each pass is recorded
as passed, the implementation plan maps every target requirement to a task, no
runtime requirement depends on a legacy/migration module, and no unfinished
predecessor path is assigned numerical parity.
