# Dual-Frequency Core Decoupling Design

> **Purpose.** Replace the remaining STNSNr-specific numerical adapters in the
> configured four-model workflow with a reusable strict dual-frequency core.
> **Workspace.** `/Users/mojackhu/Github/leaddbs`
> **Parent goal.** `my_helper/stnsnr/four_model_yaml_core_refactor_plan.md`
> **Implementation plan.**
> `my_helper/stnsnr/dual_frequency_core_decoupling_implementation_plan.md`
> **Performance refactor contract.**
> `my_helper/stnsnr/four_model_shared_exposure_performance_refactor_plan.md`
> **Task 17 decision record.**
> `my_helper/stnsnr/task17_design_decisions.md`
> **Predecessor schema.** `four_model_v1`
> **Target schema.** `dual_frequency_v1`
> **Current branch.** `stnvop`
> **Status.** `design_approved`; `goal_review_passed`;
> `implementation_complete`; `generic_runtime_active`;
> `predecessor_runtime_archived`; `bounded_numeric_evidence_verified`;
> `performance_refactor_design_documented`;
> `performance_refactor_implementation_not_started`;
> `configured_production_outputs_missing`; `production_rerun_required`.
> **Last updated.** 2026-07-16

---

Explicit user decisions are authoritative for this design. Existing Markdown,
code, and generated results are evidence, not independent authority. Resolve a
later implementation conflict conservatively and record the choice in the Task
17 decision record.

The performance-refactor contract supersedes repeated within-process
payload-hash and local filesystem-signature cache rules in this design. The
target uses portable canonical semantic JSON, one semantic SHA, one payload SHA
per file, one manifest, same-parent atomic directory publication for local
producers, and direct-copy reuse after first-use verification in each process.

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
There is one configured `combined` stimulation condition. Each model profile
locks one explicit baseline/reference/add-on endpoint pair by phase and
program. The runtime does not discover additional endpoint pairs or create
one-to-many downstream branches.

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

1. define the generic schema, strict study-base loader, records, and backend protocols;
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

Task 17 separately reopens the enumerated threshold boundaries: direct voxel
and normative fiber use `X > tau`, `count > Coverage`, and
`reference > selected_tau`; support-QC retains its strict documented direction;
pPAM uses `p(A) > 0.5`. Boundary equality is excluded and derived artifacts
bind `strict_threshold_v1`; this target is not implemented in current code.

Execution is split into two layers. Scale-independent physical preparation
produces canonical E-fields, bilateral voxel/fiber exposure, minimum-grid
`Omega_max`, requested jittered exposure, and shared OSS/pPAM rows only for
allocator-relevant classes covered by exact axis-equivalence decisions. An
unproven or failed class retains the historical per-final-axis OSS producer in
the scale-dependent and final-linked layer.
That second layer consumes indexed subject/feature subsets and performs all
outcome-dependent fitting, classification, resampling, and reporting; the
explicit FAIL producer is its only retained physical producer. This
separation changes neither the direct-voxel bilateral formula nor the
normative-fiber rule of peaking each side before averaging the two peaks.

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
- `cache`: portable semantic SHA paths and manifest-backed artifacts;
- `reporting`: generic endpoint, artifact, and run reports;
- `application`: `WorkflowService`, shared by CLI, tests, and a future GUI.

The project boundary is separate:

```text
my_helper/fiber/projects/stnsnr/
  migration/
  acceptance/
  legacy/
```

The existing study-base importer is an upstream producer and is not part of the
model runtime. The default registry, production CLI, application service, DAG,
scientific backends, cache, and reports must not import any module under
`my_helper.fiber.projects.stnsnr`, including importer, migration, acceptance,
and legacy.

## Stable Interfaces

The target service contracts are conceptually:

```python
StudyBaseLoader.load(path) -> StudyBaseRecord
ObservedBackend.run(request) -> ObservedResult
SourceResolver.resolve(grid_results) -> SourceRecord
FinalModelResolver.realize(branch_records) -> FinalModelRecord
FormalBackend.run(final_record, request) -> FormalResult
SensitivityBackend.run(final_record, request) -> SensitivityResult
ActivationBackend.materialize(cache_request) -> ActivationArtifact
ReportingBackend.render(run_records) -> ReportArtifacts
```

Scientific backends receive typed requests, explicit arrays with declared axes,
and explicit artifact references. Pure numerical kernels are array-in/record-
out. Backend orchestrators may load arrays only through an injected artifact
store using a validated `ArtifactRef`. They do not receive an untyped project
path or unresolved YAML, read raw project workbooks, infer meaning from
directory names, search a `latest` directory, or discover another task's
outputs implicitly.

An artifact-backed request must prove axis identity, not only array shape.
Outcome, baseline, nuisance, and exposure artifacts carry the exact declared
ordered subject-axis semantic ID and ordered ID file. Exposure artifacts also
carry the exact declared feature-axis semantic ID and ordered ID file. Formal
and activation requests declare their subject axis explicitly; activation also
inherits and must equal the realized final model's locked feature axis.
Same-shaped arrays with different ordered IDs are invalid inputs.

Only the config loader, strict study-base loader, and artifact store may
receive explicitly configured paths or URIs. Project paths and old output
filenames are never generic-runtime constants.

## Canonical Study Input

The model core reads an existing validated `study_base.json` directly. It does
not create an intermediate bundle, Parquet copy, index, or resolved study
manifest, and it does not read project workbooks.

The strict loader validates the repository study-base schema and converts the
document into immutable generic records with stable subject, scale, phase,
program, component, source, and observation IDs. It records the source path and
schema version in the run manifest. Every external array `ArtifactRef` records
kind/schema, explicit URI, dtype, shape, ordered axis references/IDs,
units/space, producer identity/version, and terminal file status.

Relative paths inside `study_base.json` are resolved against the directory
containing that JSON file, never against the process working directory. The
loader retains the declared contact-numbering convention and electrode order.
It validates that every electrode appears exactly once in that order and that
each stimulation source uses in-range, unique contacts with closed anode and
cathode fractions. These checks validate raw stimulation structure only;
component labels never participate in frequency classification.

The generic runtime schema preserves the canonical study-base field structure
but does not enumerate the current project's `T0`-`T3` phase IDs or
`target_stn`/`target_snr` component IDs. Those are valid data values in the
STNSNr instance, not generic code constants. The exact baseline, reference,
and add-on phase/program IDs are declared only by the two model profiles.

`source_id` is scoped to its frequency group and is not assumed to be globally
unique. The canonical stimulation-source identity is the ordered composite of
`subject_id`, `phase_id`, `program_id`, `electrode_id`,
`frequency_group_id`, and `source_id`; duplicate `source_id` values in
different groups or programs are therefore valid.

The existing STNSNr importer remains an upstream utility that may regenerate
`study_base.json`; the generic runtime neither invokes nor imports it. Another
project can provide the same study-base schema without modifying the core.

## YAML Profiles

The public configuration consists of three strict YAML profiles:

```text
direct_voxel_model.yaml
normative_fiber_model.yaml
workflow.yaml
```

`study_base.json` is a required CLI input, not a fourth YAML profile. Scale
definitions, clinical observations, phases, programs, stimulation components,
and source frequencies come only from that file. The model profiles may select
only scale IDs present in the study base; they cannot redefine scale metadata.

### Model profiles

The direct-voxel and normative-fiber profiles share:

```text
model-set ID and output root
ordered configured scale IDs
one explicit baseline/reference/add-on endpoint pair
reference/add-on frequency intervals
minimum-subject and DeltaReferenceScore support rules
```

Their domain-specific tau grids, formal-resampling counts, jitter settings, and
sensitivity parameters are validated independently and are not required to be
numerically equal.

The endpoint pair is fixed cohort-wide by exact `phase_id` and `program_id`.
There is no automatic endpoint discovery, period matching, substitution, or
one-to-many fan-out. A subject missing one member of the fixed pair is excluded
from that endpoint without changing the configured pair for other subjects.

The direct-voxel profile additionally contains its tau/Coverage resolver,
computability, formal-resampling, and selected-source sensitivity parameters.
The normative-fiber profile contains its connectomes, tau/Coverage resolver,
signed-fiber score, formal inference, sensitivity, and OSS parameters.

Connectome scheduling is role-based and limited to:

```text
formal
sensitive
```

Each normative-fiber model profile has `formal` connectome count `> 0` and
`< 2`; its `sensitive` connectome list is optional. Every connectome runs the complete observed
grid. Sensitive connectomes produce cell-level metrics and formal-source-cell
`SensitiveRecord` outputs but never a `FinalModelRecord`. OSS, jitter, and
formal inference are derived from a realized final on the formal connectome;
they do not require a third connectome role.

The core never tests for PPMI, MGH, or dTOR names. The configured STNSNr
production profile assigns PPMI/MGH to `sensitive` and dTOR to `formal`.

The direct-voxel candidate threshold is not public configuration. The runtime
derives it from the minimum direct-voxel tau scan value. Script-level smoke and
equivalence controls remain internal tests and are rejected by public schemas.

### Workflow profile

The workflow references both model profiles and declares model/connectome
selection, execution cutoff, resume/force policy, endpoint failure policy,
cache/run roots, workers, and expensive-producer authorization. It contains no
default scale list and duplicates no scientific model parameter. CLI callers
must provide `--scale` argument count `> 0` or `--all-available`.
Runtime scheduling parameters do not alter scientific cache paths.

The resolved workflow exposes two stable semantic identifiers:

- `configuration_id` names the effective validated run profile, including
  selection, execution cutoff, failure policy, worker count, and storage roots.
  Invocation-only `resume` and `force` flags are recorded separately.
- `scientific_profile_id` names values that can change planned scientific task
  content. It excludes output/cache locations, worker count, retry/order
  controls, and invocation-only flags. Concrete study, transform, and
  connectome inputs are bound by explicit paths, semantic IDs, and versions.

CLI overrides are validated with the same strict types and enums as YAML;
coercion of strings to booleans, floats to integers, invalid phase cutoffs, or
duplicate selectors is forbidden.

## Endpoint DAG

Each scale independently expands into:

```text
A = reference direct voxel
B = reference normative fiber x configured connectomes
C = add-on direct voxel
D = add-on normative fiber x configured connectomes
```

Every combined endpoint record stores an explicit
`matched_reference_endpoint_id` resolved from the one configured endpoint
pair. Normative-fiber dependencies also require the same configured connectome
ID; no name or approximate matching is allowed.

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

Add-on branch permission first requires a matched reference endpoint with valid
clinical input. A missing binding or reference input/readiness/design/technical
failure produces add-on `dependency_failure` and runs no branch. This is
distinct from a valid reference model input whose source resolver finds no
stable spatial source.

If the matched reference input is valid but its source is absent:

```text
run no_delta_reference only
reference-overlap threshold = +infinity
add-on exposure remains unexcluded
```

The no-delta branch still requires valid `Y_reference`; source absence never
means reference clinical-input absence.

If the matched reference source exists, use the same selected reference
tau/Coverage for all held-out subjects. Each held-out subject's
DeltaReferenceScore uses a reference model trained without that subject.

DeltaReferenceScore support statuses map as follows:

```text
adequate -> input valid
limited -> input valid, limitation reported
invalid_extreme_out_of_support -> adjusted branch input failure
```

The no-delta branch is attempted whenever the matched reference clinical input
is ready. When DeltaReferenceScore inputs are valid, also run adjusted:

```text
no_delta_reference
delta_reference_adjusted
```

Each branch independently runs the add-on tau/Coverage resolver.

When DeltaReferenceScore input is invalid, do not invoke the adjusted numerical
backend; record adjusted input failure. If adjusted is intended, an accepted
no-delta branch may become the one-way fallback. If no-delta is intended, its
normal realization is unaffected.

Branch roles are:

```text
reference error_predictive    -> adjusted intended primary
reference error_nonpredictive -> no-delta intended primary
valid reference input with no stable source -> no-delta intended primary
```

Fallback is intentionally one-way. When `delta_reference_adjusted` is the
intended primary and it has an input failure, design failure, or
`absent_no_stable_grid`, an accepted `no_delta_reference` branch becomes
`fallback_final`. When `no_delta_reference` is the intended primary, an
accepted adjusted comparison branch cannot be promoted after no-delta failure;
the endpoint records `no_final_model`. Technical execution failures never
trigger fallback. Formal, sensitivity, OSS, and reporting results never change
source, prediction, branch-role, or final-model status.

For normative fiber, every configured connectome runs the complete observed
grid. Only the exactly one `formal` connectome assigns canonical
source/prediction status and applies final realization. Sensitive connectomes
terminate with `SensitiveRecord` and cannot schedule formal, jitter,
activation, or final-model sensitivity.

### Scale-independent localization jitter

When jitter sensitivity is requested, the physical layer generates one
deterministic perturbation schedule and perturbed exposure set per physical
subject/stimulation/side/replicate identity. Direct voxel derives bilateral
voxel exposure; normative fiber preserves side-specific peak followed by the
mean of the two peaks. These physical resources exclude scale and outcome.

After final realization, each endpoint selects its final feature subset and
independently refits jitter weights, scores, predictions, and robustness
statistics. No outcome-dependent map, signed feature set, or classification is
shared across scales.

## Final States

Every endpoint/model family terminates in exactly one of:

```text
final_model_realized
fallback_final_realized
no_final_model
not_configured
input_failure
dependency_failure
design_failure
execution_failure
robustness_complete
```

The realized final-model count is `< 2`. Comparison branches and robustness
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

OSS endpoint statistics participate only as activation sensitivity for a
realized normative-fiber final on the unique `formal` connectome. When the
workflow requests activation sensitivity, OSS/pPAM physical rows are prepared
before endpoint analysis only for allocator-relevant classes covered by exact
axis-equivalence PASS decisions; an unproven or failed class retains the
historical per-final-axis producer after realization.
OSS does not run for direct voxel,
select tau/Coverage, replace the observed final model, or feed back into
classification.

### Activation universe

Do not run expensive OSS simulation for every fiber in the whole connectome.
In the PASS branch, use the minimum-grid maximal candidate union for the
corresponding formal-connectome physical exposure family:

```text
F_OSS_prepare = Omega_max at min(tau grid)/min(Coverage grid)
final.valid_feature_axis is an exact subset of F_OSS_prepare
```

OSS does not rescan tau/Coverage by scale or add fibers outside `Omega_max`.
Endpoint analysis selects final columns by canonical fiber ID. Endpoint
weights, signs, and selected sweet/sour IDs are re-estimated in each OSS
training fold. Add-on reference-active overlap is applied after raw activation
preparation using the endpoint's selected reference source.

In the PASS branch, the exact ordered `Omega_max` semantic ID and canonical fiber-ID file are part
of every producer-row deterministic path. Scale, endpoint, branch role,
final-model ID, run ID, worker count, and task order are not. Consequently, all
scales using the same physical input reuse completed rows and later select
their exact final-axis subset. Different prepared axes require different paths.
Approximate, nearest-axis, or whole-connectome substitution is forbidden. FAIL
retains the historical final-axis request, cache, artifact, and path identity.

The runtime passes typed row records and artifacts directly between tasks. It
does not create an `OSSSidecarBundle`, `DualFrequencyStudyBundle`, or another
intermediate study/bundle authority.

### Canonical representation

Cache continuous activation probability. Map left stimulation geometry to the
right canonical space before OSS modeling, then merge left-to-right and right
activation by maximum probability:

```text
p(A_i,f) = max(p(A_right_i,f), p(A_left_to_right_i,f))
```

The model sensitivity uses:

```text
X_OSS_i,f = 1[p(A_i,f) > 0.5]
```

For `normative_fiber_model_v1`, the public OSS settings are fixed and validated:

```text
model = OSS-DBSv2
activation model = pPAM
fiber diameter = 1.0..4.0 micrometers
samples = 10, equidistant
fitting threshold predicate: p(A) > 0.5; boundary inactive
```

Different values require a future schema version rather than a silent v1
parameter override.

Each endpoint uses the exact final valid feature axis and refits training-fold
weights and signed-fiber rankings. The final fit uses the same normative-fiber
scoring policy as the non-OSS model.

All exact row identities are validated before an expensive producer may start.
When expensive producers are disabled, any missing row yields
`missing_acceptance_fixture` before the first external process is launched.
Acceptance uses reviewed completed artifacts plus deterministic synthetic row
and L/R-union fixtures; it never fills a cache miss by starting OSS-DBS.

The activation workflow task depends directly on the immutable realized final
record as well as its formal-completion tasks. The executor must permit this
cache-first service to inspect exact rows even when expensive production is not
authorized. Authorization is checked inside the activation service only after
all cache probes complete and before scheduling the first missing row. Other
expensive services retain the executor-level guard unless they implement the
same explicit cache-first contract.

### Cache granularity

OSS path identity is based on subject, stimulation condition, component,
connectome/fiber semantic identity, spatial transform ID, OSS parameters, and
backend version. It does not include scale, endpoint, final branch, worker
count, run ID, or task order.

## Portable SHA-Manifest Cache

Expensive run-independent artifacts live outside endpoint run roots:

```text
cache/
  voxel_exposures/
  fiber_exposures/
  jitter_exposures/
  oss_rows/
```

A deterministic cache path contains only stable semantic values that can change
numerical content:

```text
input geometry and stimulation-unit IDs
stimulation settings profile ID
component/frequency metadata IDs
spatial transform ID and version
connectome/fiber-axis IDs
backend name and version
scientific parameter profile ID
```

Scale IDs, endpoint IDs, run IDs, workers, retries, scheduling order, device,
inode, mtime, and absolute paths are excluded. Canonical JSON SHA-256 produces
one `semantic_sha256` and selects
`<cache_root>/shared_exposure_v2/<kind>/<semantic_sha256>/`. Different semantic
content uses a different path and cannot be an approximate substitute.

Different array order may create a deterministic reindexed view only when
unique subject/fiber IDs prove exact membership. Never infer compatibility from
array position.

One `manifest.json` stores the canonical descriptor and each relative file's
byte count, `payload_sha256`, structural metadata, producer version, and
completed status. Source content SHA values, not local filesystem metadata,
bind portable input identity. Producer hashes final bytes while writing and
publishes through a same-parent atomic directory rename. A complete portable
entry may also be copied directly to the final semantic path. Every process
verifies semantic identity, all payload SHA values, file presence/size, and
structural headers on first use, then memoizes the verified semantic ID for the
remainder of that process.

Production may create a missing expensive cache only after explicit
`--allow-expensive-producers` authorization. Acceptance/smoke runs report
`missing_acceptance_fixture` instead of silently starting an expensive build.

## Sensitivity Extension Boundary

Each realized final publishes a small durable `sensitivity_base.json`. It binds
the parent run/model identity, final branch and role, selected source,
subject/outcome/nuisance axes, shared exposure cache identity, final artifact
references, source-content identities, `Omega_max` and OSS axis-gate state when
applicable, producer/schema versions, and RNG schedule identity. It contains no
scratch path.

A separate `sensitivity` application command validates that checkpoint and
builds an extension-only DAG for requested jitter, OSS, or other final-linked
sensitivity work. The extension receives a new run ID and immutable parent
reference. It never mutates valid parent files.

When the parent checkpoint is absent or incomplete, explicit rebuild mode
accepts the complete normal-run inputs and creates a new parent lineage through
final realization before compiling the extension DAG. It does not repair a
partially deleted historical run. A missing upstream `study_base.json` is
rebuilt only by the explicitly invoked project converter; the generic runtime
does not import that converter.

Extension artifacts live in their own run root and publish below
`<model_set_id>/extensions/<extension_id>/`. A complete parent has observed,
resolver, and final-model rerun count `< 1`. A rebuilt parent runs only the
main-chain work required to create a valid checkpoint.

Physical jitter generation requires its E-field and transform sources unless a
prepared jitter cache exists. OSS generation requires connectome/toolchain
sources unless the requested OSS cache exists. Missing source and missing
prepared cache fail as `missing_sensitivity_source`.

## Accepted Implementation Execution Boundary

The generic runtime implementation is accepted. Acceptance loaded and validated
the production profiles and compiled their endpoint catalog and DAG as a
read-only structural check. It did not execute production-YAML observed,
formal, sensitivity, jitter, activation, or report tasks and did not write the
configured production run root. Numerical evidence remains limited to
deterministic unit fixtures, project-neutral synthetic integration fixtures,
and explicitly frozen read-only acceptance artifacts.

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

`validate`, `plan`, and `run` require an explicit study-base path, direct-voxel
model profile, normative-fiber model profile, and workflow profile. `status`
and `artifacts` require an exact run root. No command searches for a default
profile, `latest` run, or inferred study input.

The repository script bootstraps only `my_helper/fiber/core` and imports
`dual_frequency.application.cli`. It must run directly from the workspace
without caller-supplied `PYTHONPATH` and cannot add any project, migration,
acceptance, or legacy directory.

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
study_base_validation_error
endpoint_input_failure
branch_input_failure
branch_design_failure
cache_identity_mismatch
expensive_producer_not_authorized
no_final_model
backend_execution_failure
```

Configuration and study-base errors reject the run. Endpoint and branch failures
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

## Completed Legacy Bridge Replacement

The eight current adapters are replaced as follows:

| Predecessor adapter | Generic replacement |
|---|---|
| `legacy_hf_direct.py` | `direct_voxel/reference.py`, `kernel.py`, `source_resolver.py` |
| `legacy_hf_fiber.py` | `normative_fiber/reference.py`, `coverage.py`, `scoring.py` |
| `legacy_ulf_direct.py` | `direct_voxel/addon.py`, `delta_reference/direct_voxel.py`, `interaction/branch_resolver.py` |
| `legacy_ulf_fiber.py` | `normative_fiber/addon.py`, `delta_reference/normative_fiber.py`, `interaction/reference_overlap.py` |
| `legacy_formal.py` | `formal/direct_voxel.py`, `formal/normative_fiber.py` |
| `legacy_sensitivity.py` | explicit tau-neighborhood, spatial-jitter, add-on-exposure, and fiber-control strategies |
| `legacy_oss.py` | `activation/ossdbs.py`, `canonical_mapping.py`, `ppam.py` |
| `legacy_reporting.py` | generic endpoint summary, artifact index, and run report backends |

All replacements passed their applicable tests and are registered in the
generic production runtime. No legacy fallback is permitted. The complete
predecessor package and old STNSNr analysis entrypoint now live under the
project-level legacy namespace outside the production Python path.

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
fixture manifest containing converter version, source paths, output paths,
schema/axis metadata, terminal status, and conversion rules.

## Bounded Numerical Acceptance

The predecessor `/goal` did not finish its planned real MDS-UPDRS III/IV run.
This decoupling design does not require completing that expensive run solely to
create a broader parity oracle.

### Frozen evidence source

The only real-run numerical baseline is the immutable paused run:

```text
run_id: 20260711T034644Z_d318f177f7f2ac7d
planned_tasks: 205
terminal_tasks: 73
completed_tasks: 50
```

Only exact task IDs in a reviewed frozen allowlist are eligible for numerical
golden parity. Every allowlisted task must also be terminal `completed`,
scientific, complete, and structurally readable. Status-based discovery cannot enroll a
task automatically, and a later output cannot extend the allowlist implicitly.
A completed reporting task that only summarizes an upstream failure is
structural evidence, not a numerical model oracle.

### Included real-data numerical scope

The completed evidence currently covers:

1. MDS-UPDRS III HF direct voxel through source/final realization, formal
   permutation/bootstrap, full spatial jitter, selected-source neighborhood,
   and reporting.
2. MDS-UPDRS III HF normative fiber dTOR through sidecars, observed analysis,
   controls, source/final realization, candidate smoke, formal inference,
   complete OSS/pPAM sensitivity, 1,000-replicate spatial jitter, and reporting.
3. MDS-UPDRS III HF normative fiber MGH and PPMI through sidecars, observed
   analysis, controls, resolver, and reporting. Their predecessor final-like
   records become target robustness evidence, not target final models.
4. the first completed MDS-UPDRS III combined child add-on normative fiber dTOR through matched-reference
   lock, preprocessing, branch resolver, final realization, plain/burden
   controls, candidate smoke, formal inference, cheap observed sensitivity,
   and selected-source neighborhood.

The fixture manifest must enumerate exact task IDs, artifact paths, schemas,
shapes, axes, and terminal statuses. It must
not infer coverage from this prose alone.

### Explicit numerical exclusions

No real-data numerical parity is required for:

- any task that was pending or unstarted when the predecessor run stopped;
- the first combined-child add-on dTOR jitter checkpoint at `388/1000`;
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
The fixture converter records paths, schema/axis metadata, and provenance for complete predecessor
outputs and extracts deterministic bounded slices needed by smoke parity. The
new backend replays only fixed internal-test prefixes, for example ten
permutations, ten bootstrap samples, and five jitter replicates, and compares
them with the corresponding frozen slices. These counts are acceptance-test
constants, not public model parameters or reportable scientific results.

OSS acceptance additionally performs full lightweight metadata/mapping/union/
threshold/subset replay and a deterministic stratified numerical sample of 48
fibers across three representative subjects. One minimal subject/component OSS
solver smoke proves execution without regenerating the full real OSS result set.

## Test Matrix

1. schema, study-base, identity, catalog, planner, state, cache, and report unit
   tests;
2. a synthetic profile with no STNSNr/HF/ULF/STN/dTOR names;
3. all-scale equality and missing-phase catalog tests;
4. explicit cross-phase matched-reference, reference-input-failure, stable-
   source-absence, DeltaReferenceScore, two-branch, fallback, and no-final
   fixtures;
5. typed request/array/ArtifactRef boundary tests plus AST and runtime blockers
   for the complete `projects.stnsnr` namespace;
6. bounded golden replay for the completed scope above;
7. lightweight two-scale smoke using MDS-UPDRS III and IV without expensive
   cache generation;
8. OSS cache, canonical mapping, threshold, subset, and sampled numerical tests;
9. CLI `validate/plan/run/status/artifacts` tests; and
10. direct CLI execution without caller-supplied `PYTHONPATH`, fixed-path/name
    scans, documentation, schema, compile, and diff checks.

## Full-Rerun Independence Criterion

A production full rerun from validated project inputs must follow:

```text
validated study_base.json
plus direct-voxel/normative-fiber/workflow YAML
-> dual_frequency_v1 validation
-> generic catalog and DAG
-> generic numerical backends
-> generic formal/sensitivity/activation
-> generic reporting
```

It must succeed with the migration, acceptance, and legacy directories removed
from the Python path. It cannot import `run_stnsnr_*`, `legacy_*`, or
`stnsnr_*` analysis modules, cannot import the project namespace, and cannot
read old output trees. Lead-DBS,
OSS-DBS, NIfTI, and connectome libraries remain external scientific engines,
accessed through generic provider/backend contracts.

The model-core full rerun begins from standardized clinical/stimulation inputs
and Lead-DBS derivatives. Electrode reconstruction and raw-image-to-E-field
processing remain upstream external production stages.

## Migration Stages

1. freeze existing completed artifacts and write the bounded fixture manifest;
2. implement `dual_frequency_v1` schemas and typed contracts;
3. implement the strict study-base loader and approved model/workflow profiles;
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

All ten migration stages completed on 2026-07-15. This completion concerns the
generic implementation and bounded acceptance only; no production scientific
rerun or output migration was performed.

## Success Criteria

The design is implemented only when:

1. the production runtime accepts only the approved `dual_frequency_v1`
   runtime contract and a validated `study_base.json`;
2. no generic runtime module imports `projects.stnsnr` or contains STNSNr, HF,
   ULF, STN, STN+SNr, dTOR, fixed-project-path, legacy-filename, or scale-name
   dispatch semantics;
3. the original interaction state machine and four model families remain
   intact;
4. all configured scales receive equal DAG and output treatment;
5. connectome scheduling is role-based;
6. scale-independent physical exposure and jitter resources, plus PASS-branch
   shared activation resources, are prepared before endpoint fan-out, use one
   portable SHA manifest per cache entry, and are reused only under matching
   semantic identity across machines/scales/runs; FAIL retains the historical
   final-linked activation producer;
7. PASS-branch OSS physical preparation uses the formal-connectome minimum-grid
   `Omega_max`, and each endpoint selects its realized final valid feature axis
   as an exact canonical-ID subset; FAIL preserves per-final-axis production;
8. sensitive connectomes emit no final model, while exactly one final model or
   an explicit closed terminal state exists per endpoint/model family after
   `formal` role filtering;
9. migration/acceptance tools remain non-runtime dependencies;
10. bounded numerical parity passes for every eligible completed predecessor
    artifact and is not claimed for unfinished predecessor paths; and
11. synthetic, smoke, import-isolation, cache, provenance, and report tests pass.

The 397-test generic suite, project-namespace-blocked synthetic report-through
run, equal III/IV read-only 136-task plan, 32-task/137-file bounded fixture
audit, public CLI/compile/diff checks, and zero-hit production
coupling/hardcoding scans satisfy the generic-core criteria. They do not
satisfy the revised Criteria 6-7. Full design completion now additionally
requires Task 17's numerical, reuse, I/O, process-concurrency, and RAM-budget
acceptance; that implementation has not started.
Real subject IDs used to inspect project data are not runtime or configuration
constants; model participation remains data- and readiness-driven.

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
