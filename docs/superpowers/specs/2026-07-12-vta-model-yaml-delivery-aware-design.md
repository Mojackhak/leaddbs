# Delivery-Aware VTA Model YAML Design

## Status

```text
design_approved_in_discussion
documentation_written
implementation_not_started
current_stimulations_backed_up
current_headmodels_moved_to_system_trash
rebuild_not_started
```

This specification defines a project-independent `vta_model.yaml`, its generic
CLI, and the delivery-aware VTA/E-field execution contract. It builds on the
canonical stimulation hierarchy in
`my_helper/fiber/vta_stimulation_contract_design.md`.

The design does not run FEM calculations or replace the existing STNSNr
entrypoints. Existing stimulation outputs and head models were moved as the
explicitly approved preparation recorded below. Rebuilding them requires a
separate implementation plan after this specification is reviewed.

## Current Migration State

On 2026-07-12 America/Los_Angeles:

- all 16 existing subject `stimulations` directories were moved to
  `/Users/mojackhu/Desktop/STNSNr_stimulations_backup_20260713T065630Z`;
- the backup contains 16 subject directories and 5,014 files with an apparent
  file size of approximately 3.950 GiB;
- all 16 existing subject `headmodel` directories were moved to the recoverable
  external-volume Trash location
  `/Volumes/VAL/.Trashes/501/STNSNr_headmodel_rebuild_20260713T070547Z`;
- the Trash backup contains all 16 subject head-model directories; and
- no new `stimulations` or `headmodel` directory has been generated.

## Goals

The implementation must:

- consume `study_base.json` as the only study-data input;
- consume one validated `vta_model.yaml` as the public physical/output model;
- contain no project, STNSNr, STN, SNr, HF, ULF, or scale-specific logic;
- derive all solve tasks from frequency-group delivery semantics;
- use `simbio_onesolve` for every production FEM solve;
- support homogeneous voltage-controlled and current-controlled groups;
- preserve independent alternating-source E-fields and VTAs;
- derive one alternating group-peak E-field and thresholded group VTA;
- write artifacts directly into each subject's Lead-DBS derivative tree; and
- provide deterministic paths, resume identity, and minimal provenance.

## Non-Goals

The first implementation does not:

- expose backend selection, solve unit, delivery merge policy, or duty cycle;
- allow voltage and current sources in the same frequency group;
- infer a time-averaged E-field for alternating stimulation;
- expose Lead-DBS meshing, tissue-surface, electrode-removal, smoothing, or
  tetrahedron-classification controls;
- introduce a project-specific importer or workbook parser;
- create an authoritative artifact index or resolved-stimulation manifest;
- run ROI/VTA postprocessing, fiber models, outcome models, or a GUI; or
- overwrite current real subject outputs during implementation acceptance.

## Authoritative Inputs

### Study Data

`study_base.json` is the only authoritative source for:

```text
subject
phase
program
electrode
frequency group
delivery mode
source
contact
control mode
amplitude
pulse width
frequency
Lead-DBS subject directory
```

The VTA core reads
`subject_sources.leaddbs_subject_dir` for each subject. It does not discover a
second project root or read clinical/programming workbooks.

### VTA Model

The public YAML contract is:

```yaml
schema_version: vta_model_v1
profile_type: vta_model

fem:
  conductivity_s_per_m:
    gray_matter: 0.33
    white_matter: 0.14

  atlas_set: Custom_Ewert_Zhang_Middlebrooks

outputs:
  spaces:
    - native
    - MNI152NLin2009bAsym

  binary_vta:
    primary_threshold_v_per_mm: 0.20
    sensitivity_thresholds_v_per_mm:
      - 0.18
      - 0.22
```

The conductivities are frozen model parameters, not implicit Lead-DBS defaults.
The schema uses `additionalProperties: false` at every object level.

Validation requires:

- finite positive gray- and white-matter conductivity values;
- a nonempty, duplicate-free output-space list;
- output spaces limited to `native` and `MNI152NLin2009bAsym` in v1;
- finite positive, duplicate-free VTA thresholds;
- sensitivity thresholds different from the primary threshold; and
- an atlas ID that resolves to a valid Lead-DBS atlas and gray-matter mask.

YAML thresholds are expressed in `V/mm`. Continuous E-field NIfTI values are
expressed in `V/m`, so thresholding uses the explicit conversion:

\[
\tau_{\mathrm{V/m}}=1000\,\tau_{\mathrm{V/mm}}
\]

The atlas ID resolves under the active Lead-DBS template root to:

```text
templates/space/MNI152NLin2009bAsym/atlases/
  Custom_Ewert_Zhang_Middlebrooks
```

The resolved atlas contains `gm_mask.nii.gz`. The YAML does not repeat that mask
path or expose `gray_matter_source`, `template_mask`, tissue-surface, meshing,
or electrode-removal fields. Electrode removal remains fixed to the current
Lead-DBS/helper value `true`.

The YAML also does not expose `backend`, `backend_policy`, `solve_unit`, smoke
settings, retry seeds, concurrency, resume, force, or subject selection.

## Architecture

```text
study_base.json + vta_model.yaml
  -> schema and cross-input validation
  -> canonical study records
  -> delivery-aware task resolver
  -> generic stimulation builder
  -> canonical head-model compatibility check or preparation
  -> simbio_onesolve native FEM
  -> native common-grid exporter
  -> optional alternating group composer
  -> native-to-MNI exporter
  -> thresholded VTA derivation
  -> hierarchical artifact store
```

The implementation is divided into these responsibilities:

1. `config` reads and validates `vta_model.yaml`.
2. `study_base_adapter` emits canonical study records without project meaning.
3. `planner` validates frequency groups, expands tasks, builds output paths, and
   resolves compute/resume/block actions.
4. `matlab_bridge` invokes MATLAB and reports process results without scientific
   dispatch rules.
5. `stimulation_builder` maps canonical sources and contacts into Lead-DBS `S`.
6. `headmodel_preparer` validates or builds the canonical per-hemisphere
   Lead-DBS head model without silently overwriting an incompatible model.
7. `simbio_onesolve_backend` solves homogeneous voltage or current states in
   native space.
8. `space_exporter` writes the native common grid and derives MNI outputs.
9. `alternating_composer` creates the native group-peak field only after every
   source parent is complete.
10. `artifact_store` owns paths, staging, atomic publication, Trash-on-force,
   minimal provenance, and resume checks.
11. `cli_service` is the single application API for CLI and a future GUI.

Dependencies flow in that order. A CLI or future GUI cannot implement a second
delivery resolver.

## Frequency-Group Invariants

Every frequency group must satisfy:

- all source frequencies are exactly equal, finite, and positive;
- all sources use exactly one shared `control_mode`;
- `continuous` contains at least one source;
- `alternating` contains at least two sources;
- every source independently satisfies the canonical contact contract; and
- different sources in one continuous group do not reuse an electrode contact.

The `case` return is not an electrode contact and may be shared by continuous
sources. Mixed voltage/current groups fail validation. Alternating sources may
reuse electrode contacts because they are not active simultaneously.

## Fixed Delivery-Aware Dispatch

Backend policy is not configurable. Production execution always uses
`simbio_onesolve`.

### Continuous

All sources in one continuous frequency group form one simultaneous physical
state and one joint FEM task:

```text
continuous + one source  -> one joint simbio_onesolve task
continuous + many sources -> one joint simbio_onesolve task
```

A continuous multi-source task does not generate source-specific
counterfactual E-fields. A continuous single-source task does not duplicate its
joint field under a second source artifact identity.

### Alternating

Every alternating source is an independent physical state:

```text
one source -> one independent simbio_onesolve task
```

Each source may contain multiple contacts. Those contacts are applied together
within that source's one solve. Source E-fields and VTAs remain separate.

After all alternating source tasks are complete, one dependent group-composer
task creates the group peak. No source is simultaneously active, no duty cycle
is inferred, and no time-weighted E-field is generated.

## Voltage And Current Boundary Conditions

### Voltage Control

Voltage-controlled groups use Dirichlet boundary conditions. A continuous group
applies all nonconflicting source contact potentials in one solve.

### Current Control

For source `s` and contact `k`:

\[
I_{s,k}=I_s f_{s,k}
\]

The implementation must:

- convert source amplitude from mA to A before constructing the FEM RHS;
- assign cathode and anode currents opposite signs;
- preserve separately normalized cathode and anode fractions;
- use the outer boundary as the return for case-return stimulation;
- use explicit anode contacts for electrode-return stimulation; and
- assemble every source in a continuous current group into one RHS.

The existing one-solve backend currently fixes `constvol=true` and rejects
current mode. Implementation must add a real current boundary assembler and
exercise the existing constant-current branch of the generic FEM solver. Merely
changing the backend capability flag is insufficient.

The production backend does not support mixed voltage/current groups because
the study contract forbids them.

## Canonical Head-Model Policy

The pipeline uses the standard Lead-DBS canonical paths under:

```text
<leaddbs_subject_dir>/headmodel/native/
```

Each hemisphere's existing `hmprotocol` must match the selected electrode
model/reconstruction, atlas set, gray- and white-matter conductivity, and
head-model implementation contract. A compatible canonical head model is
reused. A missing canonical head model is built before the first dependent FEM
task.

An incompatible canonical head model is never silently reused or overwritten.
Validation reports `incompatible_headmodel`. An explicit replacement action
must first move the incompatible untracked head-model files to a recoverable
backup or the system Trash and then rebuild the canonical path.

For the current STNSNr migration, the user approved discarding reuse of all 16
existing subject head models, including the three whose protocols already use
`Custom_Ewert_Zhang_Middlebrooks`. Every existing untracked `headmodel`
directory is moved to the recoverable system Trash, not permanently deleted.
The new pipeline later rebuilds all 16 canonical head models on demand with the
same YAML-selected atlas and conductivities. No model-scoped head-model cache is
introduced, and no rebuild is started before the new pipeline is implemented
and accepted.

## Computation And Export Spaces

FEM is computed once in patient native space. `MNI152NLin2009bAsym` is an
export space, not a second FEM computation space.

Each subject's preoperative anchor anatomy defines the native common grid:

- dimensions;
- affine;
- voxel size; and
- orientation.

Every native FEM field is interpolated to that geometry. Values outside the
valid head-model domain are `NaN`; true calculated zeros inside the valid
domain remain zero.

The corresponding patient deformation maps the native scalar E-field magnitude
to the fixed `MNI152NLin2009bAsym` reference geometry. This is a spatial
transformation/resampling of the native result, not a new MNI FEM solve. Binary
VTAs are not warped; thresholds are reapplied to the continuous E-field in each
export space.

## Alternating Group Peak

On the native common grid, for alternating group `G`:

\[
E_{\mathrm{group\_peak,native}}(v)
=
\max_{s\in G} E_{s,\mathrm{native}}(v)
\]

The group peak is computed only after all source-native E-fields are complete.
It is then transformed to MNI using the same patient deformation. The
implementation must not transform source fields first and then take their MNI
maximum.

For every configured threshold `tau`:

\[
V_{\tau}(v)=
\begin{cases}
1, & E(v)\ge\tau \\
0, & E(v)<\tau
\end{cases}
\]

The indicator value `1` means that the voxel belongs to the binary VTA. The
group VTA is therefore derived from the group-peak E-field. It is equivalent to
the same-threshold union of source VTAs on an identical grid, but is not a
simultaneous physical E-field.

## Artifact Path Contract

Artifacts are written directly under the subject directory declared by
`subject_sources.leaddbs_subject_dir`.

Identity is inferred from the complete directory path, not from a flattened
composite ID and not from an artifact index:

```text
<leaddbs_subject_dir>/
  stimulations/
    <space>/
      phase-<phase_id>/
        program-<program_id>/
          electrode-<electrode_id>/
            frequency-group-<frequency_group_id>/
              delivery-continuous/
                joint/
              delivery-alternating/
                sources/
                  source-<source_id>/
                derived/
                  group-peak/
```

All ID values used as path components must satisfy the study-base safe-ID
contract and must not contain path separators, `.`/`..` traversal components,
or platform-reserved names. Invalid IDs fail before any directory is created.

Every completed leaf contains:

```text
efield.nii.gz
vta_threshold-0p18Vpermm.nii.gz
vta_threshold-0p20Vpermm.nii.gz
vta_threshold-0p22Vpermm.nii.gz
provenance.json
```

The threshold filenames are generated from the configured values; the three
shown names are the v1 profile's concrete outputs.

## Minimal Leaf Provenance

`provenance.json` uses this exact minimal shape and field order:

```json
{
  "schema_version": "vta_leaf_provenance_v1",
  "run_id": "20260712T220000Z",
  "input_hash": "...",
  "study_base_sha256": "...",
  "vta_model_sha256": "...",
  "code_commit": "...",
  "efield_sha256": "...",
  "final_status": "completed"
}
```

`final_status` is the last field and allows only:

```text
completed
failed
```

`completed` requires a valid E-field, every configured VTA, successful basic
integrity checks, and a non-null `efield_sha256`. `failed` publishes no partial
scientific artifacts and stores `efield_sha256: null`. Partially generated
files remain in staging or diagnostic logs and are not formal leaf artifacts.

If Git is unavailable and no build-time commit is embedded, `code_commit` is
`null`. Execution must not invent an `unknown` commit or fail solely because
Git is absent. The task `input_hash` still includes a deterministic content
hash of the VTA implementation files so code changes invalidate resume identity.

The task `input_hash` covers:

```text
leaf relative-path identity
exact source/group stimulation records
head-model content
native anchor and grid
atlas GM mask
deformation and MNI reference for MNI leaves
effective model parameters
VTA implementation content
```

The leaf provenance does not duplicate effective-model objects, detailed QC,
artifact indexes, or hashes for derived VTAs. A VTA is validated by rebuilding
the mask from `efield.nii.gz` and the configured threshold.

## Publication, Resume, And Failure Rules

All files are written to a staging directory, validated, and atomically renamed
to the formal leaf. Failed tasks leave a minimal failed provenance record and
do not publish partial E-field/VTA files.

Resume may reuse a leaf only when:

- `final_status` is `completed`;
- `input_hash` matches the newly resolved task;
- every expected file exists and has a valid NIfTI header;
- dimensions and affine match the expected output grid; and
- the current E-field SHA-256 equals `efield_sha256`.

An incompatible existing leaf is an error by default. Explicit force first
moves the old untracked leaf to the system Trash and then computes a new leaf.
Force never permanently deletes an untracked directory.

One task failure does not delete successful independent tasks. Batch execution
continues across other subjects and groups and returns nonzero if any selected
task fails. An alternating group-peak task fails if any required source parent
is not complete. Native success does not make the MNI leaf successful when its
transform/export fails.

There is no fallback to the standard `simbio` backend and no delivery-semantic
fallback.

## CLI Contract

The generic public executable is `vta-model`.

### Validate

```bash
vta-model validate \
  --study-base /path/to/study_base.json \
  --model /path/to/vta_model.yaml
```

Validation checks JSON, YAML, subject directories, reconstruction, native
anchor, atlas, canonical head-model compatibility or build prerequisites, and
transforms without running FEM.

### Plan

```bash
vta-model plan \
  --study-base /path/to/study_base.json \
  --model /path/to/vta_model.yaml \
  --subject SNr003
```

Plan prints deterministic task rows with subject, phase, program, electrode,
frequency group, delivery mode, source/joint identity, control mode, output
directory, and `compute | resume_skip | blocked` action. It does not create a
new authoritative input file.

### Run

```bash
vta-model run \
  --study-base /path/to/study_base.json \
  --model /path/to/vta_model.yaml \
  --subject SNr003 \
  --resume
```

### Status

```bash
vta-model status \
  --study-base /path/to/study_base.json \
  --model /path/to/vta_model.yaml \
  --subject SNr003
```

Status replans the expected leaves and reads their minimal provenance. It does
not depend on an artifact index.

### Selection And Runtime Rules

- `--subject` is repeatable.
- Exactly one of repeatable `--subject` or `--all-subjects` is required.
- Repeatable `--phase`, `--program`, `--electrode`, and `--frequency-group`
  filters only narrow the selected study-base records.
- The output root cannot be overridden; it comes from `leaddbs_subject_dir`.
- `--workers N` parallelizes different subjects only. Tasks within one subject
  remain sequential to avoid shared head-model and transform races.
- `--resume` and `--force` are mutually exclusive.
- Validate, plan, and status do not start MATLAB FEM.
- Run uses the generic service and does not contain importer or project logic.
- No `artifacts` command is needed because paths are deterministic.

## Validation And Test Strategy

### Implementation Status

| Scope | Status | Meaning |
| --- | --- | --- |
| Canonical YAML, study-base adapter, task DAG, CLI, provenance, and MATLAB task execution | `implemented` | The delivery-aware implementation exists in the repository. |
| Static and deterministic unit coverage | `unit_validated` | Automated Python and MATLAB unit suites validate their covered contracts. |
| Historical bilateral SNr003 single-voltage backend comparison | `fem_validated` | Existing numerical evidence covers only the documented single-voltage pilot. |
| Real-cohort output rebuild | `production_rebuild_not_started` | Production subject trees and model outputs have not been rebuilt by this pipeline. |

The copied-subject preparation helper is an isolation mechanism, not numerical
FEM evidence. It preserves the minimal valid BIDS hierarchy by copying the
dataset description and only the selected `derivatives/leaddbs/sub-*` tree.
The copied-subject end-to-end gate remains unverified until its separate
explicit run is completed. No production execution is implied by any status in
this table.

### Schema And Planner

Tests must cover:

- the exact accepted YAML profile;
- every prohibited or invalid YAML field/value;
- continuous one- and multi-source task expansion;
- alternating source and group-peak dependency expansion;
- homogeneous voltage and homogeneous current groups;
- mixed control mode, mixed frequency, and cross-source contact-duplication
  rejection;
- deterministic task ordering and hierarchical paths;
- canonical head-model reuse, missing-model preparation, and incompatible-model
  blocking/replacement;
- safe resume/force decisions; and
- absence of project/anatomical/frequency-role hardcoding in generic modules.

### MATLAB Units

Tests must cover:

- voltage and current contact boundary assembly;
- mA-to-A conversion, current sign, case return, and electrode return;
- continuous multi-current RHS algebraic summation;
- alternating source isolation;
- native common-grid interpolation;
- exact voxelwise group maximum;
- thresholded source/group VTA derivation; and
- native-composition-before-MNI transformation ordering.

### Numerical FEM Acceptance

The already completed SNr003 bilateral single-voltage
`simbio`-versus-`simbio_onesolve` pilot remains evidence for the voltage
single-source boundary.

A new copied-subject current suite uses SNr003 and Medtronic 3387 geometry. It
uses fixed seed `20260712` to generate hypothetical current parameters without
modifying `study_base.json`:

```text
control mode: current
amplitude range: 0.5-5.0 mA
pulse-width range: 30-120 us
hemispheres: left and right
```

The deterministic random suite includes:

1. one cathode with case return;
2. multiple cathodes with case return and normalized random fractions; and
3. electrode return with random cathode/anode contacts and separately
   normalized polarity fractions.

Every case runs the same contacts, polarities, fractions, amplitude, and pulse
width through standard `simbio` current mode and the new
`simbio_onesolve` current mode while sharing one frozen head model. Native and
MNI E-fields and 0.18/0.20/0.22 V/mm VTAs are compared separately for every
hemisphere and case.

At least one case repeats each backend twice for deterministic repeatability.
No average may hide a failed hemisphere or stimulation case. Acceptance gates
are:

```text
backend-internal repeated E-field: voxelwise identical
maximum absolute E-field difference: <= 1e-3 V/m
relative L2 error: <= 1e-5
Pearson correlation: >= 0.999999
VTA Dice at every threshold: >= 0.999
relative VTA volume difference: <= 0.1%
```

Continuous multi-current joint execution also requires an independent
RHS/vector-field superposition test; maximum or sum of scalar E-field
magnitudes is not an acceptable reference.

These tests validate the implemented current boundary path on copied SNr003
geometry. They do not claim cross-device real-clinical current validation until
appropriate observed current-controlled cases are available.

### End-To-End Pilot

The acceptance run uses a copied SNr003 derivative tree and a rewritten test
study base. It runs:

- one continuous single-source group;
- one alternating group;
- native and MNI exports;
- all three VTA thresholds;
- hierarchical path publication;
- minimal completed and failed provenance;
- resume; and
- force-to-Trash behavior.

Acceptance must not write or overwrite the real
`/Volumes/VAL/STNSNr/derivatives/leaddbs/sub-*` tree. A real cohort run requires
separate explicit approval after implementation acceptance.

## Implementation Boundary

Implementation follows the approved detailed plan. Relevant documentation is
updated before each code change, and repository tests and tooling use the Conda
environment `leaddbs`. Copied-subject and production FEM execution remain
separate, explicit acceptance operations.
