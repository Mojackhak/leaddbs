# Dual-Frequency Four-Model YAML Core Goal

> **Purpose.** Define the authoritative `/goal` contract for replacing the
> STNSNr-oriented `four_model_v1` runtime with a reusable strict dual-frequency
> four-model core.
> **Workspace.** `/Users/mojackhu/Github/leaddbs`
> **Authority.** This is the sole current implementation `/goal`.
> **Historical predecessor checkpoint.**
> `my_helper/stnsnr/four_model_execution_plan.md`
> **Approved design.**
> `my_helper/stnsnr/dual_frequency_core_decoupling_design.md`
> **Implementation plan.**
> `my_helper/stnsnr/dual_frequency_core_decoupling_implementation_plan.md`
> **Scientific model specifications.** `my_helper/stnsnr/model_summaries/`
> **Current branch.** `stnvop`
> **Target schema.** `dual_frequency_v1`
> **Status.** `design_approved`; `goal_review_passed`;
> `implementation_not_started`;
> `predecessor_implementation_paused`; `partial_numeric_evidence_frozen`;
> `legacy_runtime_still_active`.
> **Last updated.** 2026-07-11

---

Explicit user decisions are the model-contract authority. The approved design
controls target architecture and this document is the sole current `/goal` for
implementation scope and acceptance. `four_model_execution_plan.md`, existing
code, other `four_model_v1` documents, legacy scripts, and generated outputs are
predecessor evidence only. When they conflict with this target contract, do not
preserve the conflict as compatibility behavior.

## Summary

Build a strict two-component, YAML-driven outcome-modeling system with four
model families:

```text
reference direct voxel
reference normative fiber
add-on direct voxel
add-on normative fiber
```

The STNSNr study bundle preserves raw `target_stn` and `target_snr` component
identity. HF/ULF classes are derived exclusively from source frequency using
the configured model profile: HF is `frequency_hz > 100`, ULF is
`frequency_hz < 50`, and the inclusive interval `50..100` is unclassified.
Target identity never changes the frequency class.

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
`legacy_*`, `stnsnr_*`, `run_stnsnr_*`, or
`my_helper.fiber.projects.stnsnr` module. The project importer is a separate
pre-core producer; the generic CLI, service, workflow, backends, cache, and
reporting packages never import it.

## Governing Invariants

### Strict dual-frequency scope

```text
reference_component
addon_component
```

Raw stimulation components and frequency classes are separate axes. The study
bundle stores raw components and source frequencies; `spot_model.yaml` stores
the complete, non-overlapping frequency intervals. Runtime model inputs use HF
sources from the reference/combined conditions and ULF sources from the
combined condition. Unclassified sources remain in QC but enter neither model.

The modeled stimulation states are:

```text
reference_only = reference_component
combined       = reference_component + addon_component
```

There is exactly one core `combined` stimulation condition. Period-specific
clinical measurements are not separate stimulation conditions; they are
separate downstream subscale endpoint bindings under the same parent scale.
One reference binding may therefore fan out to any number of combined
subscale bindings. The reference endpoint/model is realized once and each
downstream binding reuses its exact `matched_reference_binding_id`.

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

Every final study input must provide a resolved better-outcome direction for
every scale: `lower` or `higher`. The STNSNr importer may emit `unknown` as a
pre-curation placeholder, but catalog construction must reject it. Current
STNSNr manual curation sets only `SE-ADL score (%)` to `higher`; all other
scales are `lower`. This direction metadata changes outcome orientation only
and never changes scale execution priority.

### Generic runtime interface boundary

Production generic modules accept only validated, structured inputs:

```text
ResolvedWorkflow and typed configuration records
DualFrequencyStudyBundle or StudyBundleRef
typed backend request/result records
explicit NumPy/table arrays with declared axes
ArtifactRef and FeatureAxisRef records
current-run task/final records
```

Pure numerical kernels are array-in/record-out. Scientific backend
orchestrators may materialize arrays only through an injected artifact store
using explicit `ArtifactRef` values. They cannot accept an untyped project path,
search a directory, infer an artifact from a filename, inspect a `latest`
folder, or read a raw project workbook.

Only config loading, bundle loading, artifact-store implementations, and the
standalone project importer may receive an explicitly supplied `Path` or URI.
Every STNSNr importer path comes from validated `ImportConfig`; no project path,
condition name, component name, connectome name, scale name, or legacy output
filename is a code constant in the generic runtime.

Dependency direction is one-way:

```text
project importer -> generic bundle contracts
generic CLI/service -> generic core
generic core -X-> projects/stnsnr
```

Reports consume current-run records and artifact references only. They do not
contain project compatibility aliases.

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

Only the standalone `importer` and validated project profiles participate
before the canonical bundle boundary. The importer may depend on generic bundle
contracts; no generic runtime package may depend on any
`projects/stnsnr` module. `migration`, `acceptance`, and `legacy` are retained
manual tools/evidence but are not production dependencies.

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

Every externally stored array is referenced by a structured `ArtifactRef` that
records at least:

```text
artifact kind and schema version
explicit URI supplied by bundle/config or produced by a task
SHA-256 content hash
dtype and shape
ordered axis references and axis hashes
units and coordinate space where applicable
producer/backend identity and version
```

The STNSNr importer may read explicitly configured current clinical/stimulation
workbooks and Lead-DBS derivatives, but it cannot contain fixed STNSNr paths or
infer inputs from legacy output names. It must emit this generic contract before
the model core runs.

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
exactly one reference-only and one combined condition ID
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

Each normative-fiber model profile resolves exactly one
`primary_formal` connectome. Zero or more `observed_robustness` connectomes may
run observed source/prediction resolution, controls, and reporting, but they
emit `RobustnessRecord` values and never produce a `FinalModelRecord`. The
`activation_sensitivity_enabled` role must be attached to the same
`primary_formal` connectome because activation consumes a realized final.

The runtime never tests for PPMI, MGH, or dTOR names.

### Scale profile

Each scale declares:

```text
scale_id
label
direction
minimum_subjects
one or more endpoint bindings with stable endpoint_binding_id
exactly one reference_only binding for dual_frequency_v1
zero or more combined bindings
matched_reference_binding_id on every combined binding
```

`scale_id` identifies the parent clinical scale. Each period-specific outcome
is a child subscale identified by its stable `endpoint_binding_id`. Multiple
combined child bindings may share the same `combined` condition and the same matched reference binding. Selecting a parent
scale selects all of its configured child bindings; no period receives special
engineering status.

Missing child subscale bindings become explicit `not_configured` catalog rows.
They are not copied from another scale. Matching is performed only through the
explicit binding relation; source-period labels are never equated or inferred.
The canonical runtime has no `phase_id` or `endpoint_phase` field.

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
parent-scale/subscale/model/connectome-role selection
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

The script uses the repository's established generic `core` path bootstrap and
then imports `dual_frequency.application.cli`. Direct invocation from the
workspace must work without a caller-supplied `PYTHONPATH`. The bootstrap may
locate only `my_helper/fiber/core`; it cannot add a project, migration,
acceptance, or legacy directory.

Subcommands:

```text
validate
plan
run
status
artifacts
```

Configuration inputs are explicit; the CLI never discovers a profile or bundle:

```text
validate/plan/run:
  --study-profile PATH
  --scales-profile PATH
  --model-profile PATH
  --workflow-profile PATH
  --study-bundle PATH

status/artifacts:
  --run-root PATH
```

All five `validate/plan/run` inputs are required. `status` and `artifacts`
require an exact run root and never search for `latest` or infer a run ID from a
directory name.

Selection and execution rules:

```text
--scale              repeatable
--all-available      mutually exclusive with --scale
--models             reference-voxel,reference-fiber,addon-voxel,addon-fiber,all
--subscale           repeatable child `endpoint_binding_id` selector
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
  study + parent scale + endpoint binding + model family + connectome role/ID

task identity =
  endpoint model identity + workflow stage + branch + parameter identity

final model identity =
  endpoint model identity + realized branch + selected source identity
```

Every combined endpoint catalog record stores an explicit
`matched_reference_endpoint_id` resolved from
`matched_reference_binding_id`. Reference and combined phase IDs may differ.
Multiple combined subscale endpoints may resolve to the same reference
endpoint ID, forming a one-to-many dependency fan-out without rerunning the
reference model.
Normative-fiber dependencies additionally require the same configured
`connectome_id`; no connectome is selected by name or nearest match.

Task and final IDs cannot be known by searching an output filename.

### Reference resolution

```text
input/readiness failure:
  endpoint = input_failure
  reference_input_status = unavailable
  source/prediction = not_applicable

ready input and stable source:
  reference_input_status = ready
  source = pre_specified_accepted | scan_fallback_accepted
  prediction = error_predictive | error_nonpredictive

ready input and no stable source:
  reference_input_status = ready
  source = absent_no_stable_grid
  prediction = not_applicable

technical execution failure:
  endpoint = execution_failure
  reference_input_status = indeterminate
  source/prediction = not_applicable
```

### Add-on branch permission

The branches are:

```text
no_delta_reference:
  Y_post ~ Y_reference

delta_reference_adjusted:
  Y_post ~ Y_reference + DeltaReferenceScore
```

Branch permission first evaluates the matched reference endpoint dependency:

```text
matched reference binding not configured:
  add-on endpoint = dependency_failure
  run no branches

matched reference input/readiness/design/technical execution failure:
  add-on endpoint = dependency_failure
  run no branches

matched reference input ready and source = absent_no_stable_grid:
  run no_delta_reference only
  use an infinite reference-overlap threshold

matched reference input ready and source accepted:
  evaluate DeltaReferenceScore input
```

The no-delta branch still requires valid `Y_reference`; source absence never
means reference clinical-input absence. If a reference source exists, build each
held-out DeltaReferenceScore using a reference model trained without that
subject.

DeltaReferenceScore support:

```text
adequate -> adjusted input valid
limited  -> adjusted input valid; limitation reported
invalid_extreme_out_of_support or invalid fold/input -> adjusted input failure
```

The no-delta branch is attempted whenever the matched reference clinical input
is ready, regardless of DeltaReferenceScore validity. When adjusted input is
valid, also run adjusted and resolve both branch sources independently. When
adjusted input is invalid, do not run its numerical backend; record its input
failure. If adjusted was intended, an accepted no-delta result may realize the
one-way fallback. If no-delta was intended, its normal realization is
unaffected.

### Intended branch

```text
reference input ready, source accepted, prediction = error_predictive:
  intended = delta_reference_adjusted

reference input ready and prediction = error_nonpredictive:
  intended = no_delta_reference

reference input ready and source = absent_no_stable_grid:
  intended = no_delta_reference

reference dependency failure:
  intended = none
  no branch is permitted
```

### Connectome role and final realization

For normative-fiber endpoints, source and prediction resolution run separately
for every configured connectome. Connectome role then controls output type:

```text
observed_robustness:
  emit source/prediction/control/RobustnessRecord outputs
  never emit FinalModelRecord
  never schedule formal, jitter, activation, or final-model sensitivity

primary_formal:
  apply intended-branch and one-way-fallback realization
  emit exactly one FinalModelRecord or a closed terminal state
```

Direct-voxel endpoints have no connectome role and proceed directly to final
realization. Final-model uniqueness is evaluated per clinical endpoint and
model family after connectome-role filtering, not once per robustness
connectome.

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

Endpoint-local input/dependency/model/technical failure does not cancel
independent endpoints. The final process status is nonzero when the declared
failure policy contains a failed requested task. Closed `not_configured` states
are nonfailure; `dependency_failure`, `execution_failure`, and `no_final_model`
remain explicit requested-model terminal states with no fabricated outputs.

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
| 0 Readiness/reference lock | explicit matched-reference endpoint ID | Same scale, explicit binding, valid reference clinical input; phase IDs may differ. |
| 1 Sidecars/overlap/support | bundle, matched source | Branch-specific readiness and support. |
| 2 Observed/resolver/realization | model profile/state machine | Independent branch resolvers; one final or closed absence. |
| 2b Additional phase observed | endpoint binding | Same engineering status as every phase. |
| 3 Equivalence/smoke | internal-test | Technical qualification only. |
| 4 Formal permutation | realized final | Primary or permitted fallback final only. |
| 5 Formal bootstrap | realized final | Primary or permitted fallback final only. |
| 6 Spatial jitter | realized final | Rebuild geometry, overlap, and DeltaReferenceScore. |
| 7 Exposure neighborhood | selected source | Observed sensitivity only. |
| 8 Additional sensitivities/report | model/runtime | Comparison, gain, total exposure, support, collinearity. |
| 9 Display/final manifests | current-run records | Generic display artifacts, artifact index, and final manifests. |

### Reference normative fiber

| Round | Target source | Required behavior |
|---|---|---|
| 0 Input/manifest freeze | bundle/workflow | Immutable endpoint/connectome identity. |
| 1 Sidecar/equivalence | scientific cache/internal-test | Exact subject and feature identity. |
| 2 All-endpoint observed | catalog/connectome roles | Equal factory for every scale; robustness connectomes emit robustness records only. |
| 3 Plain control | model controls | Interpretation QC only. |
| 4 Primary-connectome smoke | internal-test | Technical qualification only. |
| 5 Cheap observed sensitivity | model/connectome roles | No hidden defaults or classification feedback. |
| 5.5 Source/prediction resolver | grid/hard filters | Endpoint/connectome source status; only primary-formal is final-eligible. |
| 6 Formal resampling | primary-formal role final | Selected source only. |
| 7 Activation sensitivity | activation-enabled role final | Cannot replace final model. |
| 8 Jitter | final | Robustness only. |
| 9 Numeric/report | reporting/runtime | Downstream numeric summaries and artifact index. |

### Add-on normative fiber

| Round | Target source | Required behavior |
|---|---|---|
| 0 Input/reference lock | explicit matched-reference/connectome record | Same scale and connectome, explicit binding, valid reference input; phase IDs may differ. |
| 1 Sidecar/support/equivalence | bundle/cache/internal-test | Branch-specific inputs and support. |
| 2 Observed/resolver/realization | model/state machine/connectome role | Robustness records for robustness connectomes; one primary/fallback final or closed absence for primary-formal. |
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
configuration_resolved.yaml
configuration_sources.json
study_bundle_ref.json
endpoint_catalog.csv
execution_plan.json
task_status.csv
run_manifest.json
artifact_index.csv
```

`configuration_resolved.yaml` is the canonical merged snapshot of the validated
study, scale, model, and workflow profiles after defaults and CLI overrides.
`configuration_sources.json` records every source profile URI and content hash.
The configuration hash is computed from the canonical resolved snapshot; a run
must not depend on source YAML remaining at its original location.

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
project-level legacy namespace outside the generic core namespace.

Manual migration/fixture conversion/parity tools remain available under the
project boundary for auditability. The generic runtime cannot import any module
under `my_helper.fiber.projects.stnsnr`, including importer, profiles,
migration, acceptance, and legacy. The standalone importer is invoked before
the generic runtime and writes a validated bundle reference.

## Acceptance Contract

### Structural acceptance for the full target

All target paths require:

- schema and StudyBundle validation tests;
- typed request, array-axis, `ArtifactRef`, and materialization-boundary tests;
- generic profile tests containing no STNSNr/HF/ULF/STN/dTOR names;
- all-scale catalog and DAG equality tests;
- explicit matched-reference binding tests with different phase IDs;
- reference/add-on state-machine and one-way fallback tests;
- reference-input-failure versus stable-source-absence truth-table tests;
- deterministic direct-voxel source fixtures for pre-specified acceptance,
  scan fallback, and absent-grid states on the complete production grid;
- deterministic predictive/nonpredictive LOOCV fixtures and branch-specific
  nuisance fixtures, including `invalid_delta_reference_scaling` versus
  `invalid_nuisance_design`;
- robustness-record versus primary-final connectome-role tests;
- backend contract and artifact validation tests;
- cache hit/miss/reindex and expensive-producer authorization tests;
- CLI and `WorkflowService` tests;
- AST dependency tests prohibiting generic imports from the complete
  `projects.stnsnr` namespace;
- fixed-path, project-name, connectome-name, and legacy-filename literal scans;
- direct CLI invocation without caller-supplied `PYTHONPATH`;
- a lightweight all-four-model end-to-end smoke through report while the
  complete project namespace is blocked; and
- documentation, compile, and diff checks.

MDS-UPDRS III score and MDS-UPDRS IV remain ordinary named real-data smoke
fixtures. The unconfigured second MDS-UPDRS IV child subscale remains explicit
`not_configured`; this is not a scale-specific code branch.

Direct-voxel acceptance is explicitly three-layered: the two-scale real-data
smoke checks end-to-end dispatch, pure state-machine tests cover every mutually
exclusive status transition, and fixed 16-subject/32-voxel NumPy fixtures run
the production resolver and LOOCV kernels. Real-data outcomes are never assumed
to exercise every status, and a silently skipped required smoke stage is not a
pass. Only one `4x4x2` synthetic NIfTI is required for input-adapter coverage.

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

Only task IDs in a reviewed, frozen allowlist may enter the golden fixture
manifest. Every allowlisted task must also be terminal `completed`, scientific,
complete, and hash-valid. Status-based discovery alone cannot enroll a task,
and later outputs cannot extend the allowlist implicitly. Completed numerical
evidence covers:

1. MDS-UPDRS III reference direct voxel through final, formal, complete jitter,
   neighborhood sensitivity, and report;
2. MDS-UPDRS III reference dTOR fiber through final, formal, OSS, complete
   jitter, and report;
3. MDS-UPDRS III reference MGH/PPMI fiber observed robustness through resolver
   and report; predecessor final-like records are converted to target
   `RobustnessRecord` evidence, never target `FinalModelRecord`; and
4. the first completed MDS-UPDRS III combined child add-on dTOR fiber through preprocessing, resolver,
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

The frozen fixture manifest records exact approved task IDs, artifact kinds,
source hashes, converter version, and an exclusion reason for every other
terminal task. Any allowlist change requires an explicit future documentation
decision.

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

Five documentation review passes completed on 2026-07-11:

| Pass | Result | Verified closure |
|---|---|---|
| 1. Target vs historical | PASS | `four_model_execution_plan.md` is historical only; this file is the sole current `/goal`; target status remains `implementation_not_started`. |
| 2. Scale equality and endpoint identity | PASS | No default/privileged scale; combined endpoints use explicit matched-reference bindings and may have different phase IDs. |
| 3. Dependency and fallback | PASS | Reference dependency failure is distinct from ready input with no source; invalid DeltaReferenceScore still runs no-delta; fallback remains one-way. |
| 4. Round, cache, activation, and interface | PASS | All nondeferred Rounds, including add-on direct Round 9, are mapped; robustness connectomes cannot become final; generic runtime accepts structured inputs and has no project reverse dependency. |
| 5. Numerical acceptance and wording | PASS | Frozen counts were verified; exact reviewed task allowlist is required; unfinished/failed/partial predecessor paths have no numerical parity requirement. |

The linked implementation plan maps every target requirement to a task. This
PASS record approves the documents for implementation; it does not claim that
schemas, Python modules, CLI, tests, caches, or model outputs already exist.
