# Four-Model YAML Core Refactor Plan

> **Purpose.** This is the `/goal` sub-plan for replacing the current STNSNr
> scale-specific four-model orchestration with a YAML-driven, endpoint-aware
> core workflow.
> **Workspace.** `/Users/mojackhu/Github/leaddbs`
> **Parent goal.** `my_helper/stnsnr/four_model_execution_plan.md`
> **Authoritative model specs.** `my_helper/stnsnr/model_summaries/`
> **Detailed implementation plan.**
> `my_helper/stnsnr/four_model_yaml_core_refactor_implementation_plan.md`
> **Current branch.** `stnvop`
> **Status.** `design_documented`; `implementation_in_progress`;
> `current_outputs_unchanged`; `current_legacy_entrypoints_remain_active`.
> **Last updated.** 2026-07-09

---

## Summary

This document is the implementation contract for an active refactor. Strict
YAML schemas/loading, immutable identities, the endpoint catalog, the pure
HF-to-ULF final-model state machine, configured run store, Round-aware planner,
and generic executor/CLI now exist. The four scientific model services,
endpoint-aware final reporting adapters, and full model rerun are not yet
implemented. The current Python and MATLAB production drivers, legacy/current
output paths, and generated results remain unchanged.

The governing engineering invariant is:

```text
all configured scales are equal execution units
```

No scale, including MDS-UPDRS III total or axial, may receive special treatment
in endpoint discovery, model execution, source resolution, prediction-status
assignment, HF-to-ULF dependency resolution, final-model realization, formal
resampling, sensitivity analysis, or output generation. A clinical reporting
hierarchy may be applied after numeric outputs are complete, but it must not be
read by the core workflow compiler or any model resolver.

The core models do not require an anatomical ROI. Direct voxel models use the
right-canonical whole-brain mask as their statistical domain. Normative fiber
models use the configured whole connectome before stimulation tau/Coverage
filtering. VTA/ROI overlap, regional coverage, regional heatmaps, anatomical
postprocessing, GUI, and HTTP services are deferred and are not part of this
plan.

## Goal And Success Criteria

The future refactor is successful only when one public configuration and CLI
can:

1. select one or more arbitrary base clinical scales, or discover all available
   configured scales;
2. resolve matched HF/frequency-1 and ULF/frequency-2 endpoint rows by scale,
   phase, and stimulation condition;
3. build the complete A/B/C/D dependency graph for every executable endpoint;
4. run observed models and endpoint-specific source resolvers;
5. realize exactly one final model, or an explicit `no_final_model`, for every
   endpoint/model family;
6. attach formal resampling and sensitivity tasks only to the automatically
   realized final model where required by the authoritative model specs;
7. generate endpoint-aware status, manifests, artifacts, and final reports;
8. continue independent endpoint tasks after a local failure and return a
   nonzero process status when any requested executable task fails; and
9. produce the same task classes and output fields for every configured scale.

Success explicitly excludes adding a preferred scale list, first-pass scale,
primary engineering scale, total-scale shortcut, axial-only round, or any
scale-name-dependent dispatch rule.

## Named End-To-End Implementation Acceptance

Final code acceptance must include a real-data integration profile containing
both of these base scales:

```text
scale_id: mds_updrs_iii
current clinical row label: MDS-UPDRS III score
direction: lower
minimum_subjects: 12
frequency_1_reference binding: STN, 3m
frequency_2_addon_chronic binding: STN+SNr, 3m
frequency_2_addon_immediate binding: STN+SNr, immediate

scale_id: mds_updrs_iv
current clinical row label: MDS-UPDRS IV
direction: lower
minimum_subjects: 12
frequency_1_reference binding: STN, 3m
frequency_2_addon_chronic binding: STN+SNr, 3m
frequency_2_addon_immediate binding: omitted
```

In this acceptance profile, “MDS-UPDRS III” means the total-score row
`MDS-UPDRS III score`; it does not include `MDS-UPDRS III axial score`. The
axial row and every other configured scale remain ordinary extensible scales
and may be added through the same interface without production-code changes.

These are named acceptance fixtures, not production defaults, preferred scales,
or scale-specific dispatch keys. The production endpoint catalog, task factory,
resolver, and model services must receive them only through ordinary
`scale_profile` entries. Removing either scale from a study profile must not
require a code change, and adding another valid scale must use the same path.

The 2026-07-09 read-only audit of
`/Users/mojackhu/Research/STNSNr/summary/cohort/subj/subject_effect_origin.xlsx`
found:

| Scale row | STN 3m | STN immediate | STN+SNr 3m | STN+SNr immediate |
|---|---:|---:|---:|---:|
| `MDS-UPDRS III score` | 16 | 16 | 16 | 16 |
| `MDS-UPDRS IV` | 16 | 0 | 16 | 0 |

Each nonzero cell contains 16 unique subjects and all 16 rows have nonmissing
`Value` and `Baseline`. These counts are input-audit evidence, not model
results. Final acceptance must record a fresh input hash and endpoint catalog
rather than assuming the counts remain unchanged.

The acceptance workflow must validate, plan, and run both scale IDs together:

```text
models = all
scales = [mds_updrs_iii, mds_updrs_iv]
phases = [chronic, immediate]
through = report
```

The acceptance oracle is:

1. Both scales pass the same schema, endpoint-catalog, task-factory, resolver,
   final-model, provenance, and reporting code paths; no production source file
   contains a scale-name branch for either scale.
2. Chronic A/B/C/D tasks are planned independently for both scales, with all
   configured normative-fiber connectome roles represented.
3. MDS-UPDRS III immediate C/D tasks and their matched HF dependencies are
   planned through the same Round 2b rules used by any available immediate
   endpoint.
4. Because the audited MDS-UPDRS IV source has no immediate rows, its immediate
   endpoint terminates explicitly as `not_requested_or_not_configured`; it is
   not treated as a code failure and is never substituted with MDS-UPDRS III or
   another scale.
5. Every requested executable endpoint independently reaches an accepted final
   model or `no_final_model`. An observed nonpredictive or no-stable-source
   result is a scientific terminal result, not evidence that generic scale
   dispatch failed.
6. Formal and sensitivity tasks attach only to each endpoint's realized final
   model. Endpoints with `no_final_model` emit the specified skip/status
   artifacts and do not fabricate formal results.
7. The process exit code, task terminal states, artifact index, and manifest
   must agree. A scientifically valid `no_final_model` may make the workflow
   exit nonzero under the declared failure policy while the code acceptance
   assertion still passes by verifying that expected state explicitly.
8. At least one deterministic integration fixture using these two scale IDs
   must realize an accepted final source so formal and sensitivity execution is
   exercised independently of the real data's scientific outcome. Additional
   deterministic fixtures must cover `no_final_model` and adjusted-primary
   input failure with an accepted `no_delta_hf` fallback.

Code refactor acceptance therefore requires both the real-data two-scale run
and deterministic state-machine coverage. Passing only a hard-coded
MDS-UPDRS III or MDS-UPDRS IV driver is insufficient.

## Implementation Execution Policy

Subagents are explicitly permitted during implementation. They may perform
bounded codebase audits, implement independently testable components with
disjoint write scopes, or run focused verification tasks. Every delegated task
must name its exact responsibility and file ownership, and subagents must not
rewrite authoritative model rules, broaden scope into ROI/postprocessing/GUI,
or change another worker's files.

The main implementation thread remains responsible for dependency ordering,
reviewing every returned change, resolving integration issues, running the
complete test and acceptance matrix, preserving the documentation-first rule,
and performing the final requirement-by-requirement completion audit. A
subagent result, isolated passing test, or delegated review cannot by itself
establish completion of this `/goal`.

## Current Implementation Gap

The current implementation predates this design and remains the active
execution layer. Confirmed legacy/current gaps include:

- total/axial default scale constants in readiness and observed drivers;
- single-scale CLI defaults rather than an endpoint catalog and workflow-level
  scale selector;
- consolidated status and gate readers that use chronic total output paths or
  global A/B model rows;
- formal-target and reporting layers that are not keyed by a composite endpoint
  identity;
- HF direct voxel all-scale tau/Coverage scanning without an equivalent
  all-endpoint execution path for every downstream A/B/C/D stage; and
- reporting/audit layers that discover existing manifests but do not execute
  missing endpoint models.

Therefore, current outputs under `/Volumes/VAL/STNSNr/summary` are legacy/current
results. They are not outputs of a YAML-driven all-endpoint pipeline. This
document must not be cited as evidence that all scales have been rerun.

## Core Scope

### Frequency roles

The generic core names are:

```text
frequency_1_reference
frequency_2_addon
```

The current STNSNr aliases are:

```text
frequency_1_reference = HF
frequency_2_addon     = ULF
```

These aliases preserve current model/document terminology without hard-coding
HF or ULF as universal frequency values. Actual stimulation frequency,
component identity, phase, pulse width, and amplitude remain input metadata and
must be audited. OSS inputs additionally require exact modeled-frequency
validation as defined by the normative fiber model documents.

### Statistical domains

```text
direct voxel:
  MNI152NLin2009bAsym right-canonical brainmask
  candidate support derived from stimulation exposure and tau/Coverage

normative fiber:
  configured public structural connectome
  candidate support derived from streamline exposure and tau/Coverage
```

An anatomical atlas or ROI must not be intersected with either core candidate
domain. Introducing an ROI-restricted statistical model would require a new
model-profile version and a separate model-document revision.

### Excluded scope

```text
VTA/ROI intersection and regional coverage
regional or anatomical heatmaps
fiber-atlas overlap and anatomical enrichment redesign
postprocessing workflow configuration
GUI or web frontend
HTTP service
new model estimators or revised classification rules
model reruns or migration of current output files
```

Existing normative-fiber FDR, labels, density, and enrichment outputs remain
part of the current model-document reporting rounds. The exclusion above means
this refactor does not add a new configurable VTA/ROI postprocessing subsystem.

## Configuration Profiles

The public configuration consists of four versioned YAML profiles validated by
JSON Schema with `additionalProperties: false`.

### `study_profile`

Required fields:

```text
schema_version
study_id
paths.clinical_table
paths.stimulation_table
paths.leaddbs_derivatives
paths.asset_root
paths.output_root
clinical_columns.subject_id
clinical_columns.scale
clinical_columns.protocol
clinical_columns.phase
clinical_columns.value
clinical_columns.baseline
space.name
space.reference_image
space.brainmask
space.canonical_hemisphere
space.left_to_right_transform
components.frequency_1_reference.alias
components.frequency_1_reference.frequency_metadata_binding
components.frequency_2_addon.alias
components.frequency_2_addon.frequency_metadata_binding
conditions.frequency_1_reference
conditions.frequency_2_addon_chronic
conditions.frequency_2_addon_immediate
efield_resolvers.frequency_1_reference
efield_resolvers.frequency_1_component_under_addon
efield_resolvers.frequency_2_component_under_addon
connectomes.<connectome_id>.path
connectomes.<connectome_id>.fiber_identity_source
```

Condition and E-field resolver fields identify data inputs. They do not define
an anatomical ROI. `space.brainmask` must resolve to the right-canonical
whole-brain mask required by the direct-voxel specifications; the schema does
not permit a scale-specific or ROI-restricted replacement. The connectome
catalog provides versioned assets, while `model_profile` assigns their observed,
robustness, or formal roles. Frequency metadata bindings may resolve per-row
values and must support the exact component-frequency audits required by OSS.

### `scale_profile`

Each scale entry requires:

```text
scale_id
label
direction = lower | higher
minimum_subjects
endpoint_bindings.frequency_1_reference
endpoint_bindings.frequency_2_addon_chronic, when available
endpoint_bindings.frequency_2_addon_immediate, when available
```

Unknown direction is a configuration/readiness failure. A scale entry may omit
an unavailable endpoint family, but the missing family must be represented in
the endpoint catalog as `not_requested_or_not_configured`, not silently mapped
to another scale. Per-scale overrides of tau grids, hard filters, branch rules,
or resampling counts are prohibited in `four_model_v1`. `minimum_subjects` is a
validated declaration of the shared readiness contract, not a per-scale model
override: every scale entry must equal the model profile's
`n_subjects_min = 12`, and configuration validation rejects any mismatch.

### `model_profile`

The versioned profile ID is:

```text
four_model_v1
```

It stores shared scientific and formal/sensitivity parameters for all scales:

```text
direct_voxel estimator and analysis domain
direct_voxel pre-specified tau/Coverage and scan grids
direct_voxel hard computability thresholds
normative_fiber exposure definition
normative_fiber pre-specified tau/Coverage and scan grids
connectome roles and connectome-specific hard computability thresholds
source-resolver neighborhood requirement
selected-source tau sensitivity multipliers
formal permutation/bootstrap parameters
formal jitter parameters
ULF branch-independent and branch-specific sensitivity switches
plain/burden control definitions
cheap normative-fiber tau/top-k/cross-connectome sensitivity definitions
OSS/pPAM sensitivity parameters
numeric display/FDR/stability reporting parameters already required by the
authoritative model specs
```

The profile may select a versioned scientific policy, but it must not contain
free-form formulas or executable code. LOOCV leakage prevention,
DeltaHFScore construction, source/prediction classification, HF-derived ULF
branch roles, and fallback-final realization remain code and model-document
contracts.

### `workflow`

Required selection and execution fields:

```text
study_profile
scale_profile
model_profile
selection.scales | selection.all_available
selection.phases
selection.models
selection.connectomes
execution.through = observed | formal | sensitivity | report
execution.resume
execution.force
execution.continue_on_endpoint_failure = true
```

`selection.scales` and `selection.all_available` are mutually exclusive. There
is no default scale. `selection.models = all` is the default model selection,
but selecting either ULF model automatically adds its matched HF dependency.
`selection.all_available` means every configured scale with a data-available
endpoint binding for the selected phase; it does not infer unconfigured
clinical columns or substitute a different scale for an unavailable binding.

## Hidden Internal Parameters

The public YAML schemas and CLI must reject:

```text
candidate_threshold_v_per_m
smoke
smoke_iterations
primary_scale
first_pass_scale
axial_special
per-scale model-parameter overrides
atlas
roi
postprocessing
```

For direct voxel preprocessing, the implementation derives:

```text
candidate_threshold_v_per_m = min(tau_grid_v_per_m)
```

This derived value is written to a technical manifest for reproducibility but
cannot be supplied or overridden by public configuration. This rule guarantees
that sparse preprocessing cannot exclude support required by the lowest
declared scan cell. Normative fiber has no global candidate-threshold setting;
each tau/Coverage cell and training fold defines its own candidate fibers.

Optimized-versus-brute-force equivalence and smoke permutation/bootstrap/jitter
are implementation qualification tests. Their fixed bounded parameters remain
inside test modules. A technical test manifest may record the executed values
and result, but no public YAML or CLI field exposes them. Smoke or equivalence
failure blocks the affected implementation path from formal execution; an
ordinary negative smoke statistic does not alter model classification.

## Round Coverage Matrix

Parameter classes:

```text
public YAML       versioned scientific/workflow parameter shared by all scales
internal-derived computed deterministically from public YAML or runtime inputs
internal-test    fixed implementation qualification parameter
runtime output   resolver/status/artifact value, never a user selector
```

### HF direct voxel

| Round | Planned source | Closed behavior |
|---|---|---|
| 0 Input readiness/environment | `study_profile`, `scale_profile`, workflow | One endpoint failure remains local; no default scale substitution. |
| 1 Sidecars/minimal QC | public YAML plus internal-derived candidate threshold | Candidate threshold equals the minimum direct-voxel tau grid. |
| 2 Observed LOOCV/resolver | `model_profile` grids/hard filters; runtime resolver output | Every endpoint independently receives source and prediction status. |
| 3 Equivalence/smoke | internal-test | Technical qualification only; no public smoke parameter. |
| 4 Formal permutation | public YAML formal profile plus runtime final source | Final accepted source only; results cannot redefine source/prediction status. |
| 5 Formal bootstrap | public YAML formal profile plus runtime final source | Final accepted source only. |
| 6 Formal spatial jitter | public YAML jitter profile plus runtime final source | Robustness only; cannot select a replacement source. |
| 7 Selected-source neighborhood | public YAML multipliers; runtime selected tau/Coverage | Observed `0.9x/1.1x` selected tau; never a fallback candidate. |
| 8 Summary/display/manifests | workflow and runtime artifacts | Endpoint-aware output; reporting hierarchy cannot alter execution. |
| 9 Optional future analyses | excluded | Not part of `four_model_v1`. |

### ULF direct voxel

| Round | Planned source | Closed behavior |
|---|---|---|
| 0 Readiness/HF lock | matched A runtime output plus profiles | C depends on matched scale/phase A, not global A status. |
| 1 Sidecars/overlap/support QC | profiles plus internal-derived candidate threshold | HF overlap uses matched selected HF tau; branch inputs remain separate. |
| 2 Observed/resolver/realization | model profile and branch state machine | Each executable branch gets its own source and prediction status. |
| 2b Immediate observed | scale endpoint binding | Same resolver as chronic; no engineering hierarchy. |
| 3 Equivalence/smoke | internal-test | Technical qualification only. |
| 4 Formal permutation | runtime realized final | Exactly one final or fallback-final branch only. |
| 5 Formal bootstrap | runtime realized final | Exactly one final or fallback-final branch only. |
| 6 Formal jitter | public YAML jitter profile plus runtime final | Rebuilds HF/ULF geometry and DeltaHFScore where applicable. |
| 7 Exposure-definition neighborhood | public YAML multipliers plus selected source | Observed sensitivity only. |
| 8 Additional sensitivities/summary | model profile | Non-selected branch, gain, total exposure, support, and collinearity sensitivity. |
| 9 Display/manifests | runtime artifacts | Cannot feed back into resolver or final model. |
| 10 Optional future analyses | excluded | Not part of `four_model_v1`. |

### HF normative fiber

| Round | Planned source | Closed behavior |
|---|---|---|
| 0 Version/input/manifest freeze | profiles and workflow | Endpoint and connectome identities are immutable for the run. |
| 1 Sidecar/equivalence | public cache profile plus internal-test equivalence | Exposure sidecars may be shared only when subject/input identity matches. |
| 2 All-endpoint observed LOOCV | scale catalog and connectome roles | All configured HF endpoint rows follow the same execution factory. |
| 3 Plain connected control | model profile controls | Interpretation QC only; cannot alter source/prediction status. |
| 4 dTOR smoke resampling | internal-test | Technical qualification only; no public smoke parameter. |
| 5 Cheap observed sensitivity | model profile | High-tau, top-k, and cross-connectome observed sensitivity. |
| 5.5 Source/predictive resolver | model profile grids/hard filters; runtime output | Endpoint-wise selected source and prediction status. |
| 6 dTOR formal resampling | public formal profile plus runtime selected source | Final selected dTOR source only. |
| 7 OSS activation sensitivity | OSS profile plus final candidate universe | dTOR final branch only; OSS cannot rescan candidates or replace final model. |
| 8 dTOR jitter QC | jitter profile plus final branch | Sensitivity only; no classification feedback. |
| 9 Numeric/display summaries | reporting profile and runtime artifacts | FDR/density/labels/cross-connectome outputs remain downstream of numeric model. |

### ULF normative fiber

| Round | Planned source | Closed behavior |
|---|---|---|
| 0 Input/HF lock | profiles plus matched B runtime output | D depends on matched scale/phase/connectome B. |
| 1 Sidecar/support/equivalence | profiles plus internal-test equivalence | Branch-specific inputs and HF support are explicit. |
| 2 Chronic observed/resolver/realization | model profile and branch state machine | Exactly one realized final model or explicit absence. |
| 2b Immediate observed | scale endpoint binding | Same engineering status as other endpoint rows. |
| 3 Plain/burden controls | model profile controls | Interpretation QC only. |
| 4 dTOR smoke resampling | internal-test | Technical qualification of realized final source. |
| 5 Cheap observed sensitivity | model profile | Non-selected branch, high-tau/top-k, total exposure, gain, and HF-neighbor sensitivity. |
| 6 Selected-source neighborhood | public multipliers plus runtime source | Observed sensitivity only. |
| 7 dTOR formal resampling | public formal profile plus realized final | Exactly one final or fallback-final branch only. |
| 8 ULF OSS activation | OSS profile plus final candidate universe | Sensitivity only; component/frequency validation required. |
| 9 ULF jitter QC | jitter profile plus final branch | Rebuilds component exposure, overlap, DeltaHFScore, and model. |
| 10 Numeric/display summaries | reporting profile and runtime artifacts | Cannot alter source, prediction, endpoint, or final-model status. |

## CLI Contract

The stable entry point is planned as:

```text
my_helper/fiber/pipelines/run_configured_outcome_models.py
```

Public subcommands:

```bash
python my_helper/fiber/pipelines/run_configured_outcome_models.py validate --config workflow.yaml
python my_helper/fiber/pipelines/run_configured_outcome_models.py plan --config workflow.yaml
python my_helper/fiber/pipelines/run_configured_outcome_models.py run --config workflow.yaml
python my_helper/fiber/pipelines/run_configured_outcome_models.py status --run-id RUN_ID
python my_helper/fiber/pipelines/run_configured_outcome_models.py artifacts --run-id RUN_ID
```

Selection and execution overrides:

```text
--scale              repeatable base-scale selector
--all-available      mutually exclusive with --scale
--models             hf-voxel,hf-fiber,ulf-voxel,ulf-fiber or all
--phases             chronic,immediate
--connectomes
--through            observed | formal | sensitivity | report
--dry-run
--resume
--force
--run-id
```

Run lookup and lineage are explicit:

```text
run --resume --run-id RUN_ID:
  reopen the identity-compatible configured run and reuse completed tasks

run --force [--run-id SUPERSEDED_RUN_ID]:
  create a new run; when an old ID is supplied, record supersession lineage

status|artifacts --output-root ROOT --run-id RUN_ID:
  search ROOT/configured_model_runs/*/RUN_ID and require exactly one study match
```

`--resume` and `--force` are mutually exclusive. `--resume` without `--run-id`
is a configuration/argument error. A resumed run never accepts a changed
configuration, input hash, or code provenance.

Resume/force flags and the referenced prior run ID are lineage controls. They
do not modify the resolved scientific/workflow configuration hash; resume
compares that unchanged hash and force records lineage in `run_manifest.json`.

CLI overrides may change workflow selection/execution fields. They must not
inject formulas, hidden internal parameters, per-scale scientific overrides,
or an anatomical ROI. `plan` and `--dry-run` emit the resolved endpoint catalog,
dependency DAG, expected outputs, and input failures without running models.

`--through` selects a dependency-complete execution stage rather than a literal
numeric-Round cutoff:

```text
observed:
  readiness, sidecars, observed models, and every resolver prerequisite

formal:
  observed plus final-model formal permutation/bootstrap tasks

sensitivity:
  formal plus post-final jitter, selected-source neighborhood, OSS,
  and the other sensitivity tasks declared by the selected model families

report:
  sensitivity plus numeric summaries, manifests, and artifact indexing
```

This logical stage order does not renumber the authoritative model documents.
For example, an observed cheap sensitivity that is required by a source
resolver remains an `observed` prerequisite even when its document Round number
precedes formal resampling.

## Endpoint And Dependency State Machine

### Endpoint identity

The stable endpoint-model identity is:

```text
study_id
scale_id
endpoint_phase
model_family
connectome_or_none
```

Display labels are metadata and are not identifiers. No endpoint is looked up
solely by `A`, `B`, `C`, `D`, total score, or axial score.

Task and final-model identities extend, but never mutate, that stable identity:

```text
endpoint_model_id = hash(study_id, scale_id, endpoint_phase,
                         model_family, connectome_or_none)

task_id = hash(endpoint_model_id, execution_stage, declared_branch,
               candidate_cell_or_selected_source_reference, replicate_or_none)

final_model_id = hash(endpoint_model_id, realized_final_branch,
                      selected_tau, selected_coverage, estimator)
```

Fields that do not apply use a canonical `none` value. The observed resolver
task exists before source selection and therefore uses declared candidate-cell
identities; selected source is its runtime output. Downstream tasks refer to the
immutable resolver task and selected-source record rather than renaming the
observed task.

`execution_stage` is operation-specific, for example
`formal_permutation`, `formal_bootstrap`, `oss_sensitivity`, or
`endpoint_report`; the broader `workflow_phase` is separately recorded as
`observed`, `formal`, `sensitivity`, or `report`. This prevents two operations
in the same logical phase from receiving the same task identity.

### Static DAG and runtime gates

The planner compiles all conditionally possible tasks before HF source and ULF
final-model results exist. A task therefore records typed dependencies and a
runtime gate rather than only a tuple of prerequisite task IDs:

Each task also embeds its immutable `EndpointModelKey` fields in the execution
plan. The hash remains the identifier, while the explicit study/scale/phase/
family/connectome fields make dependency and artifact audits possible without
reverse-decoding the hash.

```text
dependency requirement:
  terminal         prerequisite may complete, fail, or skip; its result is inspectable
  success          prerequisite must complete successfully
  accepted_final   final-realization prerequisite must expose one accepted final model
  formal_complete  selected-final formal prerequisite must complete successfully

runtime gate:
  always
  endpoint_data_available
  hf_source_available
  delta_hfscore_inputs_valid
  branch_intended_or_comparison
  final_model_realized
```

The executor evaluates gates only after their typed dependencies reach the
required state. A false gate creates an explicit terminal skipped task; it does
not remove or rename a statically planned task. In particular:

```text
matched HF resolver -> ULF branch realization:
  terminal dependency, because absent/failed HF still releases no_delta_hf

DeltaHFScore-adjusted branch:
  requires hf_source_available and delta_hfscore_inputs_valid

formal tasks:
  require accepted_final

OSS and jitter:
  require formal_complete and attach to either a primary or fallback final

reports:
  wait for relevant tasks to be terminal so failures/skips remain reportable
```

Immediate and chronic endpoint rows are independent peers. Round 2b records
the immediate document provenance but creates no chronic-to-immediate
scientific dependency. ULF direct-voxel Round 8 sensitivity operations and the
Round 8 endpoint summary are separate tasks with different workflow phases.

### HF resolution

For each configured endpoint:

```text
input/readiness failure:
  endpoint task = input_failure
  no source or prediction status is fabricated

hard-computable stable source:
  source_status = pre_specified_accepted | scan_fallback_accepted
  prediction_status = error_predictive | error_nonpredictive

no stable source:
  source_status = absent_no_stable_grid
  prediction_status = not_applicable
```

Formal and sensitivity statistics cannot change these statuses.

### HF-to-ULF dependency

```text
C ULF direct voxel:
  depends on matched A with the same scale and HF reference endpoint

D ULF normative fiber:
  depends on matched B with the same scale, HF reference endpoint,
  and connectome
```

Dependency resolution never falls back to a different scale or global status
row.

### ULF intended branch

```text
HF source unavailable:
  matched HF source_status = absent_no_stable_grid, or the matched HF task
  terminates before producing an accepted source
  run no_delta_hf when its own inputs are valid
  do not run delta_hf_adjusted
  intended primary = no_delta_hf

HF source exists and HF prediction = error_predictive:
  intended primary = delta_hf_adjusted
  also run no_delta_hf

HF source exists and HF prediction = error_nonpredictive:
  intended primary = no_delta_hf
  run delta_hf_adjusted only when DeltaHFScore inputs are valid
```

DeltaHFScore input failure fails only `delta_hf_adjusted`. It does not prevent
`no_delta_hf` from running. An upstream HF failure reason remains recorded on
the ULF task even when the independently ready `no_delta_hf` branch can run.

### ULF branch resolver and final realization

Each executable ULF branch independently receives source and prediction status.
Then:

```text
intended primary executable with accepted source:
  final_model = intended primary
  final_role = primary

intended primary input/design failure and no_delta_hf executable with accepted source:
  final_model = no_delta_hf
  final_role = fallback_final
  primary failure remains recorded

delta_hf_adjusted cannot be a fallback when the matched HF source is absent or
DeltaHFScore input/support is invalid

intended primary has no stable source, or no accepted permitted fallback exists:
  endpoint_model_status = no_final_model
  formal tasks = not_run_no_final_model
```

An accepted comparison branch is not automatically promoted when the intended
primary branch is evaluable but has `absent_no_stable_grid`. The only permitted
`four_model_v1` fallback is an accepted `no_delta_hf` branch after intended
`delta_hf_adjusted` input/design failure, as defined by the authoritative ULF
model summaries.

Exactly one realized final model may enter formal resampling. Non-selected core
branches remain observed sensitivities. Formal, OSS, jitter, and display results
cannot replace the realized final model or modify source, prediction, branch-role,
or endpoint status.

### Batch completion

An endpoint-level input, technical, or model failure does not stop independent
endpoint tasks. The run is complete after every requested task reaches a terminal
state. The CLI returns nonzero if any requested executable task ends in failure,
while unavailable/non-requested endpoint families remain explicit nonfailure
terminal states. `no_final_model` is a terminal model-absence failure for a
requested executable endpoint and therefore contributes to the nonzero batch
exit status; it does not cancel other endpoint tasks.

## Artifact And Provenance Contract

The future run root is namespaced and must not overwrite current outputs:

```text
<output_root>/configured_model_runs/<study_id>/<run_id>/
```

The run identity is auditable and collision-resistant; its hash component is
reproducible from the recorded inputs:

```text
run_id = <UTC-start-time>_<short-hash(resolved configuration, input catalog,
                                      code provenance)>
```

Resume addresses the same run ID. A forced run receives a new run ID and links
the superseded run in provenance rather than overwriting it.

Required run-level artifacts:

```text
workflow_resolved.yaml
endpoint_catalog.csv
execution_plan.json
task_status.csv
run_manifest.json
artifact_index.csv
```

Every task manifest records:

```text
composite task ID and dependency IDs
study/scale/phase/model/connectome identity
resolved profile versions and configuration hash
clinical/stimulation/e-field input hashes
right-canonical brainmask or connectome identity
subject order and feature/fiber order
derived direct-voxel candidate threshold when applicable
selected tau/Coverage and source
source/prediction/endpoint/final-model statuses
random seed and formal/sensitivity parameters when applicable
code commit, dirty status, environment, and package provenance
outputs and terminal task status
```

Resume may reuse an artifact only when all relevant identities and hashes match.
`force` creates refreshed task artifacts under the configured run policy; it
must not silently overwrite incompatible legacy/current outputs.

## Planned Implementation Phases

This section is future work and is not executed by documenting this plan.
File ownership, test-first steps, commands, commits, and completion evidence are
specified in `four_model_yaml_core_refactor_implementation_plan.md`.

1. Implement JSON Schemas, YAML loaders, and typed profile objects.
2. Implement the endpoint catalog and scale/phase pairing rules.
3. Parameterize A/B/C/D model services and remove scale/path hard-coding.
4. Implement the workflow compiler and dependency DAG.
5. Convert status, formal target, resampling, sensitivity, and reporting layers
   to endpoint-aware manifests.
6. Add resumable execution and artifact/provenance indexing.
7. Convert old entry points to explicit-parameter compatibility wrappers.
8. Run numerical-equivalence tests before any all-scale model rerun.
9. Run the named MDS-UPDRS III plus MDS-UPDRS IV real-data acceptance workflow
   and deterministic terminal-state fixtures defined above.

## Deferred Work

```text
Python/YAML schema implementation
legacy wrapper replacement
model rerun or current-output migration
VTA/ROI postprocessing and regional heatmaps
GUI or HTTP service
ROI-restricted model variants
new estimators and optional future analyses
```

## Documentation Review Contract

Before this design document is accepted, run five review passes:

1. **Scale equality and endpoint identity.** Verify that no configured scale
   receives a default, priority, or special execution path.
2. **HF-to-ULF dependency and fallback closure.** Verify every HF source state,
   DeltaHFScore input state, ULF branch state, and final/fallback state has one
   terminal outcome.
3. **Round-to-parameter coverage.** Verify every executable round in all four
   authoritative model summaries appears in the Round Coverage Matrix.
4. **CLI/YAML/manifest consistency.** Verify public inputs, internal-derived
   parameters, internal tests, runtime outputs, and forbidden fields do not
   conflict.
5. **Current-versus-planned wording.** Verify that planned interfaces are never
   described as implemented and current outputs are never described as YAML
   pipeline outputs.

### Completed Review Record

Five documentation-only review passes were completed on 2026-07-09 before
commit:

1. **Scale equality and endpoint identity: passed after correction.** Restricted
   `scale_profile.minimum_subjects` to a validated mirror of the shared
   `four_model_v1` hard filter, so every endpoint uses `n_subjects >= 12` and no
   scale can override it. Defined `--all-available` as configured,
   data-available endpoint discovery without implicit clinical-column or scale
   substitution.
2. **HF-to-ULF dependency and fallback closure: passed after correction.**
   Added a terminal `HF source unavailable` path, kept DeltaHFScore failure local
   to `delta_hf_adjusted`, and restricted fallback promotion to accepted
   `no_delta_hf` after intended adjusted-branch input/design failure. An
   evaluable intended branch with no stable source resolves to `no_final_model`.
3. **Round-to-parameter coverage: passed.** Matched every Round heading in the
   four authoritative model summaries, including both Round 2b entries and HF
   fiber Round 5.5, to a public-YAML, internal-derived, internal-test, runtime,
   or explicitly excluded source in the coverage matrix.
4. **CLI/YAML/manifest consistency: passed after correction.** Replaced the
   ambiguous analysis-mask field with the required right-canonical brainmask,
   added connectome asset and frequency-metadata bindings, defined dependency-
   complete `--through` stages, and separated endpoint-model, task, final-model,
   and run identities so runtime source selection cannot mutate an existing ID.
5. **Current-versus-planned wording: passed at the documentation checkpoint.**
   The interface was then labeled `implementation_not_started`. Active status is
   now `implementation_in_progress`, while current outputs remain read-only
   legacy/current outputs and completed claims name only implemented foundation
   layers.

The named-acceptance addendum was reviewed separately on 2026-07-09. The two
scale IDs are confined to test configuration, their current endpoint
availability was checked directly against the clinical source, missing
MDS-UPDRS IV immediate rows have an explicit terminal state, and code acceptance
is independent of whether the real-data models are predictive or realize a
stable final source.

No unresolved state, implicit default scale, unmatched dependency, or claim of
completed YAML implementation remains in this plan.

## Historical Documentation-Only Acceptance Criteria

The initial documentation phase was completed when:

- this `/goal` sub-plan is linked from the parent execution plan;
- implementation notes identify the current code gaps and planned parameter
  boundaries without claiming implementation completion;
- each model summary links to this plan and classifies the future interface as
  `public YAML`, `internal-derived`, `internal-test`, or `runtime output`;
- all four summaries continue to state that available endpoint rows are
  engineering-equivalent;
- no Python, MATLAB, schema, model output, or external data file changes exist;
- all five review passes are recorded as complete; and
- the documentation is committed separately without pushing.

## Current Execution Checkpoint

```text
design_documented
implementation_in_progress
current_outputs_unchanged
current_legacy_entrypoints_remain_active
```

No CLI example in this document is a claim that the generic executor is already
complete. Current refactor status is tracked here, in the detailed
implementation plan, and in the implementation notes. Legacy executable status
continues to come from `four_model_execution_plan.md` until configured model
services are implemented, validated, and explicitly promoted.
