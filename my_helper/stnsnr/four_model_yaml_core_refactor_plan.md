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
> **Performance refactor contract.**
> `my_helper/stnsnr/four_model_shared_exposure_performance_refactor_plan.md`
> **Task 17 decision record.**
> `my_helper/stnsnr/task17_design_decisions.md`
> **Scientific model specifications.** `my_helper/stnsnr/model_summaries/`
> **Current branch.** `stnvop`
> **Target schema.** `dual_frequency_v1`
> **Status.** `design_approved`; `goal_review_passed`;
> `generic_core_implementation_complete`; `generic_runtime_active`;
> `predecessor_runtime_archived`; `bounded_numeric_evidence_verified`;
> `performance_refactor_design_documented`;
> `performance_refactor_implementation_not_started`;
> `canonical_main_publisher_implemented`;
> `postprocess_publication_adapter_implemented`;
> `configured_production_outputs_missing`; `production_rerun_required`.
> **Last updated.** 2026-07-19

---

Explicit user decisions are the model-contract authority. The approved design
controls target architecture and this document is the sole current `/goal` for
implementation scope and acceptance. `four_model_execution_plan.md`, existing
code, other `four_model_v1` documents, legacy scripts, and generated outputs are
predecessor evidence only. When they conflict with this target contract, do not
preserve the conflict as compatibility behavior.

The linked performance-refactor contract supersedes every earlier target rule
that requires endpoint-specific physical exposure or repeated within-process
payload hashing. The target cache is portable and deliberately small:
canonical semantic JSON, one `semantic_sha256`, one `payload_sha256` per file,
one `manifest.json`, same-parent atomic directory publication for local
producers, and direct-copy reuse after first-use verification in each process.
Device, inode, mtime, absolute path, scale, endpoint, run, and worker identity
never enter a portable cache key.

## Summary

Build a strict two-component, YAML-driven outcome-modeling system with four
model families:

```text
reference direct voxel
reference normative fiber
add-on direct voxel
add-on normative fiber
```

The STNSNr `study_base.json` preserves raw `target_stn` and `target_snr` component
identity. HF/ULF classes are derived exclusively from source frequency using
the configured model profile: HF is `frequency_hz > 100`, ULF is
`frequency_hz < 50`, and values satisfying neither predicate are unclassified;
50 and 100 satisfy neither predicate.
Target identity never changes the frequency class.

The `four_model_v1` catalog/DAG/executor is retained as predecessor evidence in
the project-level legacy namespace. The completed `dual_frequency_v1` runtime
uses reusable numerical backends, reads canonical `study_base.json` directly,
uses deterministic portable manifest caches, and imports no predecessor, migration,
acceptance, or STNSNr analysis module.

The predecessor real-data acceptance run did not finish. Numeric equivalence is
therefore bounded to its terminal completed scientific artifacts in the frozen
allowlist. Historical cache files require conversion to the portable entry
schema before reuse; converted and native portable entries may be copied
directly to their final semantic directory.
Unfinished paths require contract, synthetic, and lightweight smoke tests but
do not require comparison with nonexistent predecessor results.

The performance refactor explicitly reopens only the enumerated scientific
threshold boundaries. For direct voxel and normative fiber, E-field values
below tau are inactive and all other values are active; candidate counts below
Coverage are excluded and all other counts are included; reference-component
values below the selected tau are inactive and all other values enter overlap.
Support-QC retains its documented strict direction and pPAM uses
`p(A) > 0.5`. Equality is therefore included for E-field, Coverage, and
reference overlap, and derived artifacts bind `inclusive_threshold_v1`.
Artifacts from the earlier strict-boundary v6 lineages are historical only and
cannot authorize the corrected formal result.

## Goal And Success Criteria

The goal is complete only when one public library/CLI can:

1. validate `study_base.json`, both model profiles, and the workflow profile;
2. select arbitrary configured scales or all available scales without defaults;
3. resolve matched reference-only and combined endpoint rows by stable IDs;
4. compile the complete four-model dependency DAG for each endpoint;
5. execute observed grids and endpoint-specific source resolvers;
6. assign reference prediction status and the add-on intended branch;
7. realize exactly one primary/fallback final model or a closed terminal state;
8. attach endpoint formal, sensitivity, jitter-statistic, and activation-
   statistic tasks only to that final; Layer-1 physical jitter preparation and
   PASS-branch raw OSS preparation are reusable physical work, not final-
   attached statistics;
9. isolate endpoint-local failures while continuing independent tasks;
10. produce generic manifests, artifact indexes, statuses, and reports;
11. reuse portable exposure and activation entries only after the current
    process verifies their canonical manifest, requested `semantic_sha256`,
    payload SHA values, and structural metadata; and
12. run from validated project inputs without importing any predecessor,
    migration, acceptance, or STNSNr analysis module; and
13. create or rebuild an immutable main-run sensitivity checkpoint, then run
    selected jitter, OSS, or other final-linked sensitivity work in a separate
    process and lineage without mutating valid parent artifacts.

Implementation is not complete while any production path imports a
`legacy_*`, `stnsnr_*`, `run_stnsnr_*`, or
`my_helper.fiber.projects.stnsnr` module. The existing study-base importer is
an upstream producer only; the generic CLI, service, workflow, backends, cache,
and reporting packages never import it.

## Governing Invariants

### Strict dual-frequency scope

```text
reference_component
addon_component
```

Raw stimulation components and frequency classes are separate axes.
`study_base.json` stores raw components and source frequencies; each model YAML
stores the complete, non-overlapping frequency intervals. Runtime model inputs use HF
sources from the reference/combined conditions and ULF sources from the
combined condition. Unclassified sources remain in QC but enter neither model.

The modeled stimulation states are:

```text
reference_only = reference_component
combined       = reference_component + addon_component
```

There is exactly one configured `combined` stimulation condition. Each model
profile explicitly locks one baseline/reference/add-on endpoint pair by phase
and program. The runtime does not discover additional endpoint pairs or create
one-to-many endpoint fan-out.

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
ResolvedWorkflow, StudyBaseRecord, and typed configuration records
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

Only configuration loading, the strict study-base loader, and artifact-store
implementations may receive an explicitly supplied `Path` or URI. No project
path, condition name, component name, connectome name, scale name, or legacy
output filename is a code constant in the generic runtime.

Dependency direction is one-way:

```text
upstream importer -> study_base.json
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

Execution has two explicit layers:

```text
scale-independent physical preparation
  -> canonical E-fields
  -> bilateral voxel exposure
  -> bilateral fiber peak exposure
  -> minimum-grid Omega_max
  -> requested jittered exposure
  -> [PASS only] requested shared OSS/pPAM on Omega_max

scale-dependent and final-linked execution
  -> endpoint subject/feature subset views
  -> observed weights/scores/predictions
  -> source/branch/final state
  -> [FAIL only] historical per-final-axis OSS/pPAM producer
  -> formal and sensitivity statistics
  -> reports
```

The physical layer never receives scale or outcome data. A shared OSS row enters
that layer only when an exact axis-equivalence decision covers its allocator-
relevant physical-row/axis/toolchain/RNG class; an unproven or failed class
keeps one explicit per-final-axis OSS physical producer in final-linked
execution. Apart from that
compatibility producer, statistical tasks must not rescan raw E-fields, full
connectome geometry, localization jitter, or OSS simulation. The detailed
cache, process-parallel, dynamic reserve/managed-RAM, and large-
range contracts are defined in the linked performance-refactor plan.

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
  migration/
  acceptance/
  legacy/
```

The existing project importer remains an upstream utility that creates the
canonical `study_base.json`; it is not part of the model runtime or this target
package. No generic runtime package may depend on any `projects/stnsnr` module.
`migration`, `acceptance`, and `legacy` are retained manual tools/evidence but
are not production dependencies.

`WorkflowService` is the single application API used by CLI, tests, and a
future GUI. The CLI cannot contain a second orchestration implementation.

### Confirmed terminal and reporting architecture

The scientific DAG executes endpoint-local observed, resolver, final, formal,
sensitivity, and activation work. Reporting is not an ordinary DAG task whose
dependency failure can hide another terminal state. After executor completion,
a post-executor aggregator receives the complete current-run task outcomes and
typed records, then writes endpoint summaries, the artifact index, and the run
report. It may describe failed, skipped, fallback, and no-final endpoints but
must not fabricate missing numerical artifacts.

`FinalDecisionRecord` is the typed terminal authority for every requested
endpoint/model family. It represents exactly one of:

```text
realized_primary
realized_fallback
no_final_model
dependency_failure
execution_failure
```

A realized decision references exactly one `FinalModelRecord`; a non-realized
decision cannot carry a final-model reference. Persisted service results must
restore these records through an explicit typed codec rather than untyped fact
dictionaries.

Every endpoint-local final-realization task first emits a typed
`FinalSelectionRecord`. A realized selection contains exactly one
`FinalModelRecord`; a closed selection instead records `no_final_model`,
dependency failure, or execution failure with deterministic reason codes. This
scientific selection is separate from the post-executor
`FinalDecisionRecord`, which incorporates the complete task outcome state for
reporting. A legitimate absence of a stable model is therefore not represented
as a runtime exception, while formal and sensitivity work remains strictly
gated on the one realized final model.

Implementation followed this fixed order: generic formal/sensitivity backends,
then the explicit runtime input provider, service adapters, and typed record
codec, followed by the production registry switch and post-executor report
aggregation. An empty registry remains test injection only.

## Canonical Study Base

The core consumes the existing validated `study_base.json` directly. It does
not create an intermediate bundle, Parquet copy, index document, or resolved
study manifest. Project-specific Excel layouts are outside the runtime.

Required guarantees:

- stable subject, endpoint, condition, component, and connectome IDs;
- explicit subject and feature order;
- units and coordinate-space identity;
- study-base schema validity and a stable explicit input path;
- no semantic inference from filenames;
- no silent clinical-row or scale substitution; and
- immutable study-base content during a run.

Every externally stored array is referenced by a structured `ArtifactRef` that
records these required fields:

```text
artifact kind and schema version
explicit URI supplied by study base/config or produced by a task
dtype and shape
ordered axis references and stable semantic axis IDs
units and coordinate space where applicable
producer/backend identity and version
terminal file status
```

The existing STNSNr importer may continue to create `study_base.json`, but the
model core neither invokes nor imports it. Full model execution starts from an
already generated study-base file.

### Runtime scientific-readiness boundary

`EndpointRecord.subject_ids` is the ordered clinical candidate cohort. It is
not automatically the fitted cohort. For every endpoint, the runtime provider
preserves that order while independently checking the exact configured program,
frequency-derived source class, required canonical group-level E-field leaf,
and model-specific input artifacts. It publishes candidate, included, and
reason-coded excluded subjects in `EndpointInputRecord` and reapplies the
minimum-subject rule to the included axis.

There are no subject-specific inclusion or exclusion lists. In particular,
subject IDs mentioned while checking the current project data are observations
about that snapshot, not configuration or runtime rules. A missing add-on-class
source excludes that subject only from the corresponding add-on endpoint; it
does not remove the subject from a valid reference endpoint.

The ordered add-on subject axis may therefore be a strict subset of the matched
reference subject axis. DeltaReferenceScore construction must join those axes by
stable `subject_id`; it must never require equal cohort cardinality or positional
identity. For each held-out add-on subject, use the matched reference fold that
excluded that same subject while retaining every other reference-ready subject,
including subjects that are not eligible for the add-on endpoint. Every add-on
subject must be present exactly once on the matched-reference axis. If any member
is absent or duplicated, the adjusted branch is an endpoint-level input failure;
the no-delta branch retains the unchanged add-on cohort. The runtime must not
silently create a third, smaller adjusted cohort or encode a subject-specific
exception.

The upstream VTA pipeline intentionally uses a path-existence completion
contract. The core therefore derives, rather than searches for, each exact
group-level input beneath the subject's configured Lead-DBS directory:

```text
stimulations/<canonical-space>/phase-<phase-id>/program-<program-id>/
  electrode-<electrode-id>/frequency-group-<group-id>/
    delivery-continuous/joint/efield.nii.gz

or

    delivery-alternating/derived/group-peak/efield.nii.gz
```

This is a fixed artifact-path contract, not semantic filename discovery: every
path segment comes from the validated study/configuration record and delivery
mode, and directory scanning or `latest` selection is forbidden. The provider
validates the declared path, file type, dimensions, units, and finite content
needed by the consumer. No bundle,
standalone VTA resolved manifest, or `vta_model.yaml` input is added to the
downstream four-model interface; upstream FEM provenance remains outside this
core contract.

Exposure preparation publishes two typed records:

```text
EndpointInputRecord
  -> candidate/included/excluded subjects
  -> exact subject axis
  -> aligned baseline and outcome artifacts

PreparedExposureRecord
  -> exact subject and feature axes
  -> prepared primary exposure
  -> canonical feature IDs
  -> branch-specific reference/add-on auxiliary exposures and overlap mask
```

Direct voxel retains deterministic IDs for the configured right-canonical
brainmask voxels; normative fiber retains canonical connectome fiber IDs. A
numerical direct-voxel request may omit IDs that its kernel does not consume,
but the prepared record preserves them for exact map export, jitter, reporting,
and resume identity.

Add-on records also carry an explicit DeltaReferenceScore input-readiness
status and reason. Missing reference-condition or add-on reference-component
exposure invalidates only the adjusted branch; a shape-compatible zero-filled
auxiliary array cannot be treated as proof that the input was observed. The
no-delta branch remains eligible when its own clinical and add-on exposure
inputs are ready.

These records, rather than mutable provider-local filenames, are the resume and
downstream dependency authority.

Accordingly, final-linked formal, sensitivity, jitter, and activation tasks
declare the relevant endpoint-input and prepared-exposure records as direct
dependencies in addition to the final selection. They may derive the locked
selected-axis view from those immutable records, but they cannot rediscover
files or rebuild a different subject cohort.

## YAML Contract

The public configuration uses three strict inputs:

```text
direct_voxel_model.yaml
normative_fiber_model.yaml
workflow.yaml
```

The two model profiles declare:

```text
configured scale IDs
one explicit baseline/reference/add-on endpoint pair
reference/add-on frequency intervals
model-specific source, resolver, formal, sensitivity, and output parameters
normative-fiber connectomes and role sets
```

`workflow.yaml` declares model selection, execution phase, resume/force policy,
failure policy, scientific cache root, and run-store root. It does not contain
a default scale list or duplicate scientific model parameters.

Normative-fiber connectome roles are restricted to:

```text
formal
sensitive
```

Each normative-fiber model profile has `formal` connectome count `> 0` and
`< 2`; its `sensitive` connectome list is optional. Every connectome runs the complete
observed tau/Coverage grid. Only `formal` assigns source/prediction status,
realizes a final model, and schedules formal resampling, OSS, jitter, and
final-linked sensitivity. `Sensitive` connectomes evaluate the numeric
tau/Coverage selected by `formal`, emit cross-connectome sensitivity records,
and can never rescue or replace the formal final model.

The runtime never tests for PPMI, MGH, or dTOR names.

### Model profiles

Each model profile selects an ordered list of `scale_id` values. Every ID must
exist in `study_base.json`; label, direction, value type, unit, and observations
come only from that study base. Unknown, duplicate, or unavailable scale IDs
fail validation. No scale is inferred or substituted.

The profiles declare scientific parameters for:

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

The direct-voxel and normative-fiber profiles must agree exactly on
`model_set_id`, output root, configured scale order, endpoint pair, frequency
classes, minimum subjects, and DeltaReferenceScore support thresholds.

The direct-voxel candidate threshold is not public. It is derived as
`min(tau_grid_v_per_m)` and written only to technical provenance. Smoke and
equivalence counts are fixed internal-test parameters. Schema validation rejects
both fields if supplied through YAML or CLI.

### Workflow profile

Declares:

```text
model/connectome selection
through stage
resume/force policy
endpoint failure policy
runtime workers
expensive-producer policy
```

Workers and retry order do not enter scientific cache identity.

### Old configuration handling

The production runtime contract is `dual_frequency_v1` and accepts only the
approved direct-voxel, normative-fiber, and workflow profile schemas. A
retained manual migration tool may convert predecessor configuration for
review. It is never imported by the production config loader and no invalid
document is silently reinterpreted as old YAML.

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

Configuration inputs are explicit; the CLI never discovers a profile or study:

```text
validate/plan/run:
  --study-base PATH
  --direct-voxel-model PATH
  --normative-fiber-model PATH
  --workflow-profile PATH

status/artifacts:
  --run-root PATH
```

All four `validate/plan/run` inputs are required. `status` and `artifacts`
require an exact run root and never search for `latest` or infer a run ID from a
directory name.

Selection and execution rules:

```text
--scale              repeatable
--all-available      mutually exclusive with --scale
--models             reference-voxel,reference-fiber,addon-voxel,addon-fiber,all
--connectomes
--through            observed|formal|sensitivity|report
--resume --run-id
--force [--run-id]
--allow-expensive-producers
```

Omitting both `--scale` and `--all-available` is an error. Selecting an add-on
endpoint automatically adds its matched reference dependency. `--resume`
requires the same run ID, resolved profile IDs, study-base path, code version,
and scientific semantic identity.
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

Each configured model profile locks exactly one explicit baseline/reference/
add-on `endpoint_pair` by phase and program. Reference and add-on phase IDs may
differ. Every configured scale instantiates that same binding structure, but
the catalog does not automatically select another reference, discover an
additional add-on endpoint, or create one-to-many endpoint fan-out.
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

matched reference input ready with source state `absent_no_stable_grid`:
  run no_delta_reference only
  use an infinite reference-overlap threshold

matched reference input ready and source accepted:
  evaluate DeltaReferenceScore input
```

The no-delta branch still requires valid `Y_reference`; source absence never
means reference clinical-input absence. If a reference source exists, build each
held-out DeltaReferenceScore using a reference model trained without that
subject. The matched reference training cohort is not truncated to the add-on
cohort: reference-only subjects remain valid training observations. Full-sample
reference weights use the complete ready reference cohort; fold weights are
selected by stable subject identity for each add-on held-out row.

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
reference input ready, source accepted, prediction state `error_predictive`:
  intended = delta_reference_adjusted

reference input ready with prediction state `error_nonpredictive`:
  intended = no_delta_reference

reference input ready with source state `absent_no_stable_grid`:
  intended = no_delta_reference

reference dependency failure:
  intended = none
  no branch is permitted
```

### Connectome role and final realization

For normative-fiber endpoints, the complete observed grid runs separately for
every configured connectome. Connectome role controls selection and output:

```text
sensitive:
  emit cell-level computability/prediction metrics and formal-source-cell
  sensitivity outputs
  do not assign canonical source/prediction/final status
  never emit FinalModelRecord
  never schedule formal, jitter, activation, or final-model sensitivity

formal:
  assign source/prediction status
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
its primary/fallback role. The final-model count entering downstream formal,
sensitivity, and activation tasks is `< 2`.
Post-executor reporting receives the single typed final decision plus every
terminal task outcome; it does not select a model or feed classification back
into the DAG.

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
| 0 Input readiness/environment | study base, model profiles, workflow | Endpoint failure remains local; no scale substitution. |
| 1 Sidecars/minimal QC | YAML plus internal-derived candidate threshold | Candidate threshold equals minimum formal tau. |
| 2 Observed LOOCV/resolver | model grid/hard filters | Endpoint-specific source and prediction status. |
| 3 Equivalence/smoke | internal-test | Fixed test-suite qualification only; not an endpoint production task. |
| 4 Formal permutation | realized final | Cannot change classification. |
| 5 Formal bootstrap | realized final | Final source only. |
| 6 Spatial jitter | realized final | Robustness only. |
| 7 Selected-source neighborhood | selected tau/Coverage | `0.9x/1.1x` selected tau; not a source candidate. |
| 8 Report/manifests | runtime records | Generic endpoint output. |

### Add-on direct voxel

| Round | Target source | Required behavior |
|---|---|---|
| 0 Readiness/reference lock | explicit matched-reference endpoint ID | Same scale, explicit binding, valid reference clinical input; phase IDs may differ. |
| 1 Sidecars/overlap/support | study base, matched source | Branch-specific readiness and support. |
| 2 Observed/resolver/realization | model profile/state machine | Independent branch resolvers; one final or closed absence. |
| 3 Equivalence/smoke | internal-test | Fixed test-suite qualification only; not an endpoint production task. |
| 4 Formal permutation | realized final | Primary or permitted fallback final only. |
| 5 Formal bootstrap | realized final | Primary or permitted fallback final only. |
| 6 Spatial jitter | realized final | Rebuild geometry, overlap, and DeltaReferenceScore. |
| 7 Exposure neighborhood | selected source | Observed sensitivity only. |
| 8 Additional sensitivities/report | model/runtime | Comparison, gain, total exposure, support, collinearity. |
| 9 Display/final manifests | current-run records | Generic display artifacts, artifact index, and final manifests. |

### Reference normative fiber

| Round | Target source | Required behavior |
|---|---|---|
| 0 Input/manifest freeze | study base/workflow | Immutable endpoint/connectome identity. |
| 1 Sidecar/equivalence | scientific cache/internal-test | Exact subject and feature identity. |
| 2 All-endpoint observed | catalog/connectome roles | Equal factory for every scale; every connectome runs the complete observed grid. |
| 3 Plain control | model controls | Interpretation QC only. |
| 4 Formal-connectome internal smoke | internal-test | Fixed test-suite qualification only; not an endpoint production task and parameters are not public YAML. |
| 5 Cheap observed sensitivity | model/connectome roles | No hidden defaults or classification feedback. |
| 5.5 Source/prediction resolver | grid/hard filters | Only the formal connectome assigns status and is final-eligible. |
| 6 Formal resampling | formal role final | Every configured scale with a realized final; selected source only. |
| 7 Activation sensitivity | formal role final | Cannot replace final model. |
| 8 Jitter | final | Robustness only. |
| 9 Numeric/report | reporting/runtime | Downstream numeric summaries and artifact index. |

### Add-on normative fiber

| Round | Target source | Required behavior |
|---|---|---|
| 0 Input/reference lock | explicit matched-reference/connectome record | Same scale and connectome, explicit binding, valid reference input; phase IDs may differ. |
| 1 Sidecar/support/equivalence | study base/cache/internal-test | Branch-specific inputs and support. |
| 2 Observed/resolver/realization | model/state machine/connectome role | Full observed grids for all connectomes; one primary/fallback final or closed absence for formal. |
| 3 Plain/burden controls | model controls | Interpretation QC only. |
| 4 Formal-connectome internal smoke | internal-test | Fixed test-suite final-source qualification; not an endpoint production task. |
| 5 Cheap observed sensitivity | model profile | Comparison and exposure sensitivities. |
| 6 Selected-source neighborhood | selected source | Observed sensitivity only. |
| 7 Formal resampling | formal role final | Exactly one final per configured scale. |
| 8 Activation sensitivity | formal role final | Component/frequency identity required. |
| 9 Jitter | final | Rebuild exposure, overlap, DeltaReferenceScore, and model. |
| 10 Numeric/report | reporting/runtime | Cannot alter classification. |

Each resolved model profile contains exactly one explicit baseline/reference/
add-on endpoint pair. An additional assessment period is not an implicit
`Round 2b`, child endpoint, or `chronic`/`immediate` runtime class. It requires
another explicit endpoint-pair configuration and receives the same task factory
as every other configured scale/period row.

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

OSS/pPAM physical preparation becomes scale-independent for an allocator-
relevant class only after its bounded final-axis versus `Omega_max` equivalence
decision passes, and it runs only when the requested workflow includes
activation sensitivity. The bounded decision matrix must cover every distinct
class used by the run; an unproven or failed class retains the historical per-
final-axis producer in final-linked execution. Endpoint activation statistics
in either branch run only for a realized normative-fiber final on the unique
`formal` connectome. They do not participate in source resolution or final
realization.

In the PASS branch, the prepared activation universe is the exact minimum-grid
maximal candidate union for the corresponding physical exposure family:

```text
F_OSS_prepare = Omega_max at min(tau grid)/min(Coverage grid)
final.valid_feature_axis is an exact subset of F_OSS_prepare
```

PASS-branch OSS must not cover the complete connectome, rescan tau/Coverage per scale, add
fibers outside `Omega_max`, or restrict the prepared universe using activation.
Endpoint analysis selects final columns by canonical fiber ID. Add-on
reference-active overlap is applied after physical OSS preparation using the
endpoint's selected reference source. Endpoint weights, signs, and selected
sweet/sour fibers are re-estimated within each OSS training fold.

For the default OSS backend:

```text
left geometry -> right canonical space
p(A_i,f) = max(p(A_right_i,f), p(A_left_to_right_i,f))
X_OSS_i,f = 1[p(A_i,f) > 0.5]
```

The runtime derives OSS rows from frequency-group delivery semantics rather than
from endpoint names:

```text
continuous frequency group:
  model all simultaneously active sources as one OSS row

alternating frequency group:
  model each source independently and merge source probabilities by elementwise max
```

For both delivery modes in the PASS branch, left stimulation/electrode geometry is first mapped to
the configured right-canonical space and OSS is then evaluated on
`F_OSS_prepare`. The runtime must not model a left native row and map only its
activation values afterward.

Exact cache lookup may derive the canonical-geometry identity from the source
reconstruction, reconstruction lead, stimulation parameters, mapping method,
and configured transform without executing the transform. An authorized cache
miss must materialize the identified right-canonical geometry before OSS starts.
This distinction preserves cache-first execution without weakening the mapping
contract.

In the PASS branch, cache continuous probability on `F_OSS_prepare` and derive the binary analysis
matrix. Endpoint fits select the exact final valid feature-axis columns and
refit training-fold weights/ranks.

In the PASS branch, the exact ordered `Omega_max` semantic ID and canonical fiber-ID file
participate in the producer-row deterministic path, but scale, endpoint,
branch role, final-model ID, run identity, and worker count do not. This permits
reuse across all scales without expanding OSS to a whole-connectome universe.
A different prepared axis uses a different path and cannot be served by
nearest-key matching. The FAIL branch retains the historical final-axis path,
request, cache, and artifact identity.
The filtered Lead-DBS connectome renumbers this exact axis locally as `1..K`,
writes `idx` for those `K` fibers, and sets `origNum = K`. The parent connectome
count is retained only in the local-to-canonical prepared-axis mapping metadata;
it must not be
used as the OSS denominator for the filtered candidate universe. Standard
Lead-DBS `4xN`/`5xN` and transposed `Nx4`/`Nx5` point layouts are both accepted;
neither orientation may reorder the prepared `Omega_max` axis.
The filtered artifact is always one flattened internal pathway even when the
parent connectome's human-readable label contains `Multi-Tract`; the parent
label remains provenance and must not select a different allocator parser.
Filtered HDF5 creation uses an exclusive no-overwrite open rather than a
check-then-truncate sequence.
This filesystem materialization belongs to runtime producer infrastructure,
not to the scientific activation backend API; backend call signatures remain
typed-record/artifact based and do not accept raw filesystem paths.

Activation tasks exchange typed records and artifact references directly. They
must not create a `DualFrequencyStudyBundle`, `OSSSidecarBundle`, or another
intermediate bundle authority.

Each activation task directly consumes its immutable realized final record and
completed formal dependencies. Cache lookup remains available when expensive
producers are disabled, and a complete exact cache hit does not require producer
authorization. On an exact cache miss, acceptance mode or a run without
`--allow-expensive-producers` fails closed as `missing_acceptance_fixture` before
any OSS process starts. An explicitly authorized production miss resolves the
official Lead-DBS `OSS-DBSv2` environment internally and may invoke the declared
producer. OSS executable or environment paths are internal runtime dependencies;
they are not public model-YAML fields.

The default producer rebuilds its row exclusively from verified run-scoped
geometry/source locator artifacts and the configured formal connectome. A
continuous frequency group is accepted as one simultaneous row only when its
sources share reconstruction lead, frequency, control mode, and pulse width and
do not reuse an active contact identity; its contact boundary is then summed
before OSS. The v1 waveform is rectangular with zero relative phase. A
continuous voltage group must use one consistent return topology; mixing
case-return and electrode-return sources is rejected because the MAT converter
cannot preserve that boundary exactly. Every active voltage contact has
`fraction = 1.0`; current fractions close independently within each polarity;
`case`, when present, is the sole anode in both modes. Alternating rows remain
one source each. The configured `Composite.nii.gz` remains the forward image
transform. For left point geometry, the provider deterministically requires its
sibling `InverseComposite.nii.gz`; MATLAB receives that exact path,
mirrors RAS x, converts the points to LPS, applies the already selected inverse
field directly through the locked platform `antsApplyTransformsToPoints`
binary with no additional inversion, converts the result back to RAS, and
thereby matches `ea_flip_lr_nonlinear` without an SPM/NIfTI affine round trip.
In the PASS branch, the ten pPAM samples are restricted to the selected
`Omega_max` simulation axis; in the current/FAIL branch they remain restricted
to the immutable final fiber axis. Both return activated counts divided by ten.
No subject, phase, program, target, or scale allowlist is permitted in this
producer path.

The MATLAB producer bridge loads the exact reconstruction MAT supplied by the
typed row request and rejects reconstruction-lead, electrode-model, and contact-
count mismatches. It also retains the standard Lead-DBS rejection of a
directional lead implanted perfectly along the x axis. It must not initialize
patient options or scientific settings through `ea_getptopts`, mutable GUI
preferences, or subject-directory discovery.

The v1 producer also freezes the previously effective internal OSS scientific
defaults instead of inheriting mutable Lead-DBS GUI preferences:

```text
template tissue segmentation = MNI152NLin2009bAsym/segmask.nii
conductivity model = ColeCole4 isotropic
patient DTI conductivity = disabled
axon model = McNeal1976
axon length = 10 mm
```

The v7.3 MAT serializes disabled DTI as the pinned converter's supported
`no dti` sentinel. The converter must normalize that value to an empty
`DTIPath` with `DiffusionTensorActive = false`; a MATLAB empty character array
is not an equivalent serialized representation.

The template segmentation bytes, fixed settings, OSS environment definition,
producer/bridge code, reconstruction, configured transform, stimulation
parameters, formal connectome, and exact ordered simulation axis all
participate in the deterministic cache path and declared version. PASS uses the
selected `Omega_max` axis; current/FAIL uses the final fiber axis. A cache hit
remains possible without an
installed OSS environment, but an authorized miss must resolve and validate the
official environment before starting an external process.

The producer re-derives the complete semantic row path from the verified
documents and fixed settings before execution. Nested paths must stay
inside validated study subject roots or the repository root, and captured input
paths and structural metadata must remain unchanged through publication. Subject roots are keyed
by subject ID, so one subject's locator cannot resolve through another subject's
root. The target computes the complete implementation attestation once per
immutable run-environment identity and binds it to the backend version in the
cache path; each row uses a lightweight semantic/version guard. `OSS-DBSv2.yml`
pins the accepted upstream commit, declared versions for
installed OSS/Lead-DBS-interface package resources (including HOC/MOD
scientific assets), normalized entrypoints, the Conda/Python environment
inventory, and exact MATLAB runtime identity. The local
implementation attestation includes the transitive Lead-DBS/MATLAB bridge and
coordinate helpers as well as the top-level producer, and the platform ANTs
point-transform binary is part of that attestation. Authorized misses reuse the
attested immutable-environment record and validate only the lightweight row
guard; a changed environment identity requires a new complete attestation.
Only executable paths may be cached.
The converted OSS
JSON must explicitly confirm the exact segmentation, `ColeCole4`, inactive DTI,
rectangular zero-phase waveform, requested control/frequency/pulse width, and
active pathway calculation. The pinned converter itself is the final electrode-
model compatibility authority; a broader Lead-DBS GUI/model registry cannot
pre-approve a model that the converter does not implement.
All OSS console scripts are launched through the validated
`environment_root/bin/python`; executable shebang text cannot select a second,
unvalidated interpreter.

Every external producer stage streams stdout/stderr to its work-directory log,
records its new process-group ID immediately after `Popen`, uses a fixed
internal deadline, and terminates the entire process group with a
bounded TERM-to-KILL sequence on timeout. The original process-group ID is kept
and receives SIGKILL after the grace period even if the group leader exits
after SIGTERM, so resistant descendants cannot escape. These lifecycle values
are internal producer safeguards and remain absent from public YAML and CLI.

The generic producer checkpoint on 2026-07-15 passed the complete
`dual_frequency` Python suite (`387 tests`, `224 subtests`), all 15 MATLAB OSS
bridge/mapping/boundary/converter tests, and installed `ossdbsv2` lock
resolution twice consecutively. Regression coverage includes non-Python OSS
package resources, complete core Python producer-module attestation, pre/post-
row environment validation, validated-environment entrypoint binding, and a
SIGTERM-resistant descendant whose group leader exits first. The converter
test runs only the bounded MAT-to-JSON conversion;
no FEM, OSS simulation, formal model, or production YAML workflow was launched,
and the overall `/goal` remains in progress.

## Spatial-Jitter Contract

Spatial-jitter **statistics** are final-linked robustness evidence and cannot
alter source, prediction, branch-role, endpoint, or final-model status.
Scale-independent jitter geometry and physical exposure are prepared before
endpoint fan-out whenever the requested workflow includes jitter. The public
model profile supplies `replicates`, `seed`, and `translation_fwhm_mm`; the
runtime derives the Gaussian standard deviation as:

```text
translation_sigma_mm = translation_fwhm_mm / 2.354820045
```

For each replicate, the provider derives one deterministic translation vector
per `(replicate, condition/component, subject_id, hemisphere)`. Every leaf in
the same stimulation group and hemisphere receives that same vector. Exposure
is sampled on the existing canonical grid with linear interpolation and
out-of-domain values set to zero. Direct-voxel and normative-fiber aggregation,
bilateral mapping, and frequency-group semantics remain identical to the
observed model. These vectors and physical exposure rows exclude scale,
outcome, endpoint status, and final-model identity and are reused by all scales.

Physical direct-voxel jitter uses the canonical voxel domain; physical
normative-fiber jitter uses the same `Omega_max` prepared fiber axis as the
base exposure. After a final is realized, endpoint analysis selects its exact
feature-axis subset from those prepared rows and must not invoke the source
resolver. Reference jitter refits the selected model. Add-on jitter also rebuilds the
add-on reference component, reference-overlap exclusion, support QC, and, for an
adjusted final, the matched-reference operator and full/fold DeltaReferenceScore
using the subject-ID cohort join above. Replicate resources are task-scoped and
released after each task; temporary arrays or mappings may not accumulate across
endpoints.

Support readiness remains branch-specific during jitter. An invalid rebuilt
DeltaReferenceScore support state makes an adjusted replicate not computable,
but it does not suppress a no-delta replicate. A no-delta final remains
evaluable when matched-reference support is invalid or not applicable; the
support state is retained as QC only.

## Portable SHA-Manifest Cache Contract

Run-independent expensive artifacts are stored under versioned deterministic
paths built from one portable canonical descriptor:

```text
voxel exposures
fiber exposures
jitter exposures
OSS rows
```

The descriptor includes:

```text
study and physical stimulation-unit IDs
component/frequency class and delivery-mode IDs
spatial transform content SHA and version
connectome content SHA and ordered feature-axis IDs
backend and scientific-version IDs
scientific parameter profile ID
```

Canonical JSON SHA-256 produces `semantic_sha256`; the cache path is
`<cache_root>/shared_exposure_v2/<kind>/<semantic_sha256>/`. It excludes device,
inode, mtime, absolute paths, scale, endpoint, branch role, run ID, worker count,
retry count, and completion order. Every source content SHA is portable across
machines.

One `manifest.json` stores the complete canonical descriptor plus each relative
file path, byte count, `payload_sha256`, schema, dtype, shape, ordered axes,
units, space, producer version, and completed status. The producer calculates
`payload_sha256` while writing final bytes. A complete entry may be copied
directly into its final semantic directory. On first use in every process, the
runtime recomputes the semantic SHA, verifies every declared payload SHA, and
validates file presence/size plus structural headers before adding the entry to
a process-local verified set. Later consumers in that process do not repeat
payload hashing; a new process, including resume or sensitivity extension,
verifies the entry again.

Temporary, partial, corrupt, or structurally invalid directories never
authorize reuse and are not deleted automatically. Identical ordered IDs may
be reused across machines; a different order may produce a deterministic
reindex view only after exact ID membership and uniqueness validation.

## Sensitivity Checkpoint And Extension Contract

Main-run completion is an immutable checkpoint, not the end of future
sensitivity work. Every realized direct-voxel or normative-fiber final writes a
durable `sensitivity_base.json` containing:

```text
base run and model-set IDs
scale, model family, final branch, and final role
selected tau and Coverage
subject, voxel, and fiber axis references as applicable
outcome and nuisance artifact references
base exposure semantic SHA
final-model artifact references
source E-field, transform, and connectome content identities
Omega_max reference and OSS axis-gate status as applicable
producer/schema versions and RNG schedule identity
```

Every reference is durable. Scratch URIs are forbidden.

A later process may execute:

```text
run_dual_frequency_models.py sensitivity
  --base-run PATH
  --analyses jitter,oss
  --run-id ID
  --workers N
```

The extension process validates the parent checkpoint and every used cache
entry, compiles only requested final-linked sensitivity tasks, and writes a new
run lineage. A complete parent causes observed, resolver, and final-model rerun
count `< 1`.

When the parent run or any required observed, resolver, final-model, or
sensitivity-base artifact is missing, explicit rebuild mode uses supplied
study-base and model/workflow profiles to create a new parent run through final
realization before starting the extension. It does not repair or mutate the
deleted or partial lineage. If `study_base.json` is missing, the project-owned
upstream converter runs explicitly before the generic runtime; generic core
code never imports that converter.

Base exposure alone cannot create a new physical jitter realization or OSS row.
The required E-field/transform/connectome/toolchain sources or corresponding
prepared sensitivity cache must remain available. Missing sources with no
prepared cache produce `missing_sensitivity_source`.

Extension run root:

```text
<workflow.storage.run_root>/<study_id>/<extension_run_id>/
  run_manifest.json
  base_run_reference.json
  configuration_resolved.yaml
  sensitivity_plan.json
  artifact_index.json
  artifact_index.csv
  tasks/
  work/
  sensitivity_results/
```

Canonical extension publication is isolated below:

```text
<model.output.root>/<model_type>/<model_set_id>/extensions/<extension_id>/
```

No extension overwrites a main-run artifact. Extension resume restores valid
completed sensitivity tasks, reruns failed/running/missing tasks, and
re-evaluates dependency-derived skips.

## Artifact And Provenance Contract

The internal execution run store and canonical downstream publication are
separate boundaries. Task-local artifacts continue to use the run root below.
Configured direct-voxel publication must materialize the stable, scale-equal
layout defined by
`config/four_model_v1/direct_voxel_output_contract.md` under:

```text
<direct_voxel_model.output.root>/direct_voxel/<model_set_id>/<scale_id>/
```

Configured normative-fiber publication follows
`config/four_model_v1/normative_fiber_output_contract.md` under:

```text
<normative_fiber_model.output.root>/normative_fiber/<model_set_id>/<scale_id>/
```

The canonical publication is the only scientific-input boundary for
postprocessing. The internal run store may be read by the publisher, but no
postprocess adapter, renderer, example, or resume check may inspect `.runs/`,
`tasks/`, `work/`, `runtime_work/`, or a task-local artifact URI. A postprocess
request must start from a completed model-set or extension manifest, resolve
every scientific input through that publication's `artifact_index.csv`, and
verify the recorded payload SHA-256 before rendering. Missing canonical
publication is a blocking input state; it never permits run-store fallback.

The direct-voxel publisher owns the unsmoothed selected-source NIfTI and the
1 mm and 2 mm FWHM display-only NIfTI derivatives defined by the direct-voxel
output contract. Postprocess consumes those published NIfTI files and cannot
reconstruct a substitute from task-local arrays. Normative-fiber visualization
likewise begins from published selected fiber axes, weights, density maps, and
declared connectome geometry identity.

Workflow storage policy exposes `delete_run_cache_on_success`. The configured
production value is `false`, so completed shared physical preparation remains
available for later jitter, OSS-DBS, combined extensions, and resume. Cache
cleanup is eligible only after the requested workflow and canonical
publication both reach an unqualified completed terminal state. Failed,
partial, interrupted, completed-with-failures, or incompletely published runs
must never remove cache content. This is an unconditional recovery invariant:
enabling successful-run cleanup cannot override it. Publication and run
artifacts are never cache cleanup targets.

Canonical publication uses replayable temporary-sibling writes followed by
atomic rename and a single payload integrity read. The verified SHA-256 and
byte count are reused when recording the artifact index. Per-artifact
synchronous filesystem flushes are not part of the portable publication
contract: completion is instead guarded by commit-last root manifests, and any
interrupted fragment remains available for verified same-byte replay from the
immutable source run.

The writer resolves the publication root once, rejects absolute or
parent-traversing relative paths, and resolves each unique destination parent
once before first use. It verifies each distinct immutable source artifact and
its declared SHA-256 once per publisher process. Reuse of that verification is
allowed only for another reference to the same canonical path and digest.

The normative-fiber profile is `normative_fiber_model.yaml`; its lightweight
acceptance profile is `normative_fiber_model_test.yaml`. Both enforce `formal`
connectome count `> 0` and `< 2`; their `sensitive` connectome lists are
optional.

The publication path contains no `endpoint`, `endpoint_pair`, or run-ID
directory. Endpoint binding remains explicit in the resolved model profile and
`model_manifest.json`. Publication never copies a selected branch into a second
final-model directory; `final_model.json` is an immutable relative-path
reference.

The configured direct-voxel and normative-fiber implementations use
reference/add-on terminology internally, not only at publication. Legacy HF/ULF names must be removed from
configured modules, typed records, state fields, artifact kinds, tests, and
task identities. Compatibility-only legacy entrypoints are quarantined outside
the canonical configured API.

Run root:

```text
<workflow.storage.run_root>/<study_id>/<run_id>/
```

`model.output.root` remains the scientific artifact/report root. The workflow
run store is independently rooted at the explicit `storage.run_root`; neither
path is inferred from the other.

Required run artifacts:

```text
configuration_resolved.yaml
configuration_sources.json
endpoint_catalog.csv
execution_plan.json
task_status.csv
run_manifest.json
artifact_index.csv
```

`configuration_resolved.yaml` is the canonical merged snapshot of the validated
study, scale, model, and workflow profiles after defaults and CLI overrides.
`configuration_sources.json` records every source profile URI, semantic profile
ID, and declared schema version. The resolved snapshot is copied into the run
directory; a run must not depend on source YAML remaining at its original
location.

Every task records endpoint/task/final identities, dependencies, study-base and
configuration paths/versions, subject/feature order, selected source, statuses,
random parameters, code/environment provenance, cache references, outputs, and
terminal status.

Resume reuses only the same run/task identity and present structurally valid
terminal artifacts. Force creates a new lineage. No run modifies the
predecessor configured run or
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
under `my_helper.fiber.projects.stnsnr`, including importer, migration,
acceptance, and legacy. The model runtime receives an existing validated
`study_base.json`; it never invokes the importer.

## Acceptance Contract

### Structural acceptance for the full target

All target paths require:

- schema and study-base validation tests;
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
- sensitive-record versus formal-final connectome-role tests;
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
fixtures. Both traverse the same configured endpoint-pair factory; neither is
a default or scale-specific code branch.

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
planned_tasks: 205
terminal_tasks: 73
completed_tasks: 50
```

Only task IDs in a reviewed, frozen allowlist may enter the golden fixture
manifest. Every allowlisted task must also be terminal `completed`, scientific,
complete, and structurally readable. Status-based discovery alone cannot enroll a task,
and later outputs cannot extend the allowlist implicitly. Completed numerical
evidence covers:

1. MDS-UPDRS III reference direct voxel through final, formal, complete jitter,
   neighborhood sensitivity, and report;
2. MDS-UPDRS III reference dTOR fiber through final, formal, OSS, complete
   jitter, and report;
3. MDS-UPDRS III reference MGH/PPMI predecessor sensitivity evidence through resolver
   and report; predecessor final-like records are converted to target
   `SensitiveRecord` evidence, never target `FinalModelRecord`; and
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

Complete predecessor formal/jitter/OSS products receive schema, status, axis,
shape, and numerical validation. New backends replay only fixed internal-test slices, such as ten
permutations, ten bootstraps, five jitter replicates, and OSS 48-fiber samples
across three representative subjects. These are test constants, not scientific
outputs. Missing acceptance fixtures never trigger expensive generation.

The frozen fixture manifest records exact approved task IDs, artifact kinds,
source paths, schema/converter versions, and an exclusion reason for every other
terminal task. Any allowlist change requires an explicit future documentation
decision.

Exact fields include endpoint/source/final identities, tau/Coverage, feature
IDs, masks, binary pPAM, branch roles, and selected fibers. Floating weights,
scores, and predictions use `rtol=1e-8`, `atol=1e-10`; sampled continuous OSS
probability uses `rtol=1e-6`, `atol=1e-8`.

## Implementation Record

The completed implementation record is:

```text
my_helper/stnsnr/dual_frequency_core_decoupling_implementation_plan.md
```

The predecessor
`four_model_yaml_core_refactor_implementation_plan.md` is historical evidence of
the implemented foundation. It is not an instruction source for new runtime
interfaces.

Subagents were permitted for bounded, disjoint tasks. The main implementation
thread retained dependency ordering, integration review, complete tests,
acceptance, documentation-first updates, and the final requirement audit.

## Historical Four-Model V1 Checkpoint

The predecessor state is retained only for provenance:

```text
schema: four_model_v1
archived package: my_helper/fiber/projects/stnsnr/legacy/outcome_models
archived entrypoint: my_helper/fiber/projects/stnsnr/legacy/run_configured_outcome_models.py
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

## Completion Evidence

Implementation acceptance completed on 2026-07-15 without running production
models or modifying existing output trees:

- the complete generic suite passes 397/397 tests;
- the project-neutral synthetic workflow executes all four model families
  through report with the project namespace blocked and all tasks terminal;
- MDS-UPDRS III and IV traverse the same read-only real-data catalog and DAG,
  producing 16 available endpoints and 136 planned tasks, 68 per scale;
- the reviewed bounded manifest contains 32 eligible tasks and 137 terminal,
  structurally readable task/artifact files;
- resolved configuration, all four source paths, run manifest, final decisions,
  task states, report, and artifact index agree in the synthetic acceptance;
- the public CLI, compilation, diff validation, runtime import isolation, and
  production hardcoding scans pass; and
- no production source/profile contains the real subject IDs used during data
  verification. Subject inclusion is derived only from configured endpoint data,
  classified source availability, branch readiness, and minimum-subject rules.

This completes the generic core implementation contract. It does not claim a
new scientific result, a full expensive all-scale rerun, or migration of any
existing STNSNr output.

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

Five documentation review passes were repeated after generic-core acceptance
on 2026-07-15. A sixth performance-contract pass was added on 2026-07-16:

| Pass | Result | Verified closure |
|---|---|---|
| 1. Target vs historical | PASS | `four_model_execution_plan.md` is historical only; this file is the sole current `/goal`; generic implementation is complete while production rerun remains deferred. |
| 2. Scale equality and endpoint identity | PASS | No default/privileged scale; combined endpoints use explicit matched-reference bindings and may have different phase IDs. |
| 3. Dependency and fallback | PASS | Reference dependency failure is distinct from ready input with no source; invalid DeltaReferenceScore still runs no-delta; fallback remains one-way. |
| 4. Round, cache, activation, and interface | PASS | All nondeferred Rounds, including add-on direct Round 9, are mapped; sensitive connectomes cannot become final; generic runtime accepts structured inputs and has no project reverse dependency. |
| 5. Numerical acceptance and wording | PASS | Frozen counts were verified; exact reviewed task allowlist is required; unfinished/failed/partial predecessor paths have no numerical parity requirement. |
| 6. Shared physical preparation and resources | DESIGN PASS / IMPLEMENTATION OPEN | Scale-independent base/jitter preparation, conditional PASS-branch OSS reuse on exact `Omega_max`, FAIL-branch final-axis retention, portable SHA manifests, coarse RAM-adaptive ranges, and process scheduling are specified by the linked performance contract and Task 17. |

The linked implementation plan maps the accepted generic-core requirements to
completed code and evidence. Task 17 maps the new performance requirements to
unchecked implementation and acceptance steps. This record therefore confirms
generic-core completion and performance-design closure only; it does not claim
that shared physical preparation is implemented or that production model
outputs were regenerated.
