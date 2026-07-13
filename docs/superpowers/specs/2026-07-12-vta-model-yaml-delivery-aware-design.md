# Delivery-Aware VTA Model YAML Design

## Status

```text
design_approved_in_discussion
documentation_written
implementation_complete
unit_and_copied_subject_acceptance_passed
production_rebuild_ready
current_stimulations_backed_up
current_headmodels_moved_to_system_trash
production_rebuild_not_started
```

This specification defines a project-independent `vta_model.yaml`, its generic
CLI, and the delivery-aware VTA/E-field execution contract. It builds on the
canonical stimulation hierarchy in
`my_helper/fiber/vta_stimulation_contract_design.md`.

The generic implementation and copied-subject acceptance are complete. Legacy
STNSNr entrypoints remain available but are not called by the new pipeline.
Existing stimulation outputs and head models were moved as the explicitly
approved preparation recorded below. Production rebuilding remains a separate
operational action and has not been started.

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
- no new production `stimulations` or `headmodel` directory has been generated;
  all implementation acceptance writes were confined to copied subjects below
  `/Volumes/VAL/STNSNr/validation`.

## Goals

The implementation:

- consume `study_base.json` as the only study-data input;
- consume one validated `vta_model.yaml` as the public physical/output model;
- contain no project, STNSNr, STN, SNr, HF, ULF, or scale-specific logic;
- derive all solve tasks from frequency-group delivery semantics;
- use `simbio_onesolve` for every production FEM solve;
- support homogeneous voltage-controlled and current-controlled groups;
- preserve independent alternating-source E-fields and VTAs;
- derive one alternating group-peak E-field and thresholded group VTA;
- write artifacts directly into each subject's Lead-DBS derivative tree; and
- provide deterministic paths and path-based incremental execution.

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

This fixed behavior does not remove the electrode from the FEM solve. Before
scattered interpolation of the continuous E-field, it reproduces the complete
standard Horn export geometry: remove contact/insulator tetrahedral samples
(`mesh.tissue > 2`), align samples to the electrode axis, displace tissue
samples radially to the lead surface, and remove samples that cannot be mapped
outside the lead. The rule applies to voltage and current tasks in both
delivery modes.

The YAML also does not expose `backend`, `backend_policy`, `solve_unit`, smoke
settings, retry seeds, concurrency, resume, force, or subject selection.

## Architecture

### Unified Canonical Backend

Canonical production execution has one backend and one export path:

```text
mh_vta_execute_canonical_task
  -> mh_vta_backend_simbio_onesolve_canonical
       -> mh_vta_assemble_boundary(control_mode)
       -> mh_vta_fem_apply_dbs
       -> mh_vta_fem_calc_gradient
       -> mh_vta_export_canonical_outputs
```

`mh_vta_execute_canonical_task` calls the canonical backend directly for every
FEM task. It does not dispatch canonical tasks through the legacy model
registry or the legacy `mh_vta_backend_simbio_onesolve` compatibility wrapper.
That wrapper may remain for non-canonical callers, but it is not a production
path for this pipeline.

Voltage and current are boundary strategies, not separate backends:

```text
voltage -> Dirichlet boundary values
current -> current RHS plus case/electrode return boundary
```

Both strategies use the same head model, linear solver, gradient calculation,
complete Horn electrode-removal geometry, native common-grid interpolation,
native thresholding, native-to-MNI continuous-field transformation, and MNI
thresholding. No control-mode-specific code may write E-field or VTA outputs.

`mh_vta_assemble_boundary` is the only canonical boundary assembler. The old
`mh_vta_assemble_onesolve_boundary` file and its tests have been removed,
preventing two implementations from drifting.

`mh_vta_export_canonical_outputs` owns the shared export pipeline and returns
the native/MNI artifact paths. The backend owns context preparation, head-model
reuse/build, active-contact lookup, boundary assembly, FEM solve, and gradient
calculation; it delegates all output generation to this shared exporter.

### Canonical Gray-Matter Geometry

The canonical backend uses the configured atlas to materialize a patient-space
`gm_mask.nii.gz`, but it must not merge the atlas ROI surfaces from
`atlas_index.mat`. Parent ROIs and overlapping subregions can cause repeated
surface Boolean resolution to split triangles combinatorially. The observed
SNr003 right-sided failure produced approximately 29.6 million faces and a
999 MB Boolean input before FEM began.

Canonical context configuration therefore fixes:

```matlab
options.prefs.vat.gm = 'mask';
options.prefs.machine.vatsettings.horn_useatlas = 1;
options.prefs.machine.vatsettings.horn_atlasset = task.model.atlas_set;
```

In native space, `ea_fem_getmask` ensures that the configured atlas is warped
for the patient, reads its `gm_mask.nii.gz`, smooths according to the existing
Lead-DBS default, and extracts one isosurface at `max(mask)/2`. Disconnected GM
components may remain disconnected within that single surface object; they are
not resolved sequentially as separate atlas ROIs. This changes geometry input
construction only. Voltage/current boundaries, FEM, export, and thresholding
remain unchanged. Legacy non-canonical VTA entry points retain their existing
user-selected GM source behavior.

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
   and path-based completion checks.
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

The canonical one-solve backend now uses a real current boundary assembler and
the existing constant-current branch of the generic FEM solver. Current support
is implemented as a boundary strategy, not as a capability-flag change.

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

Compatibility includes a strict coordinate-unit contract. `mesh.pnt` and
`vol.pos` must be finite real `N x 3` arrays with identical node counts. If
`mesh.unit` exists, it must be `mm`. After conversion to `double`,
`mesh.pnt / 1000` must match `vol.pos` node by node within `1e-6 m`, and
`max(abs(vol.pos(:)))` must remain below `2 m`. The mandatory check runs after
the canonical backend loads either a reused or newly built head model and
before FEM boundary assembly or gradient calculation. Existing-model
preparation also applies the same check as an early failure. A violation fails
explicitly; the pipeline neither repairs units nor silently replaces the file.
The detailed contract is defined in
`2026-07-13-canonical-headmodel-unit-contract-design.md`.

An incompatible canonical head model is never silently reused or overwritten.
Validation reports `incompatible_headmodel`. An explicit replacement action
must first move the incompatible untracked head-model files to a recoverable
backup or the system Trash and then rebuild the canonical path.

For the current STNSNr migration, the user approved discarding reuse of all 16
existing subject head models, including the three whose protocols already use
`Custom_Ewert_Zhang_Middlebrooks`. Every existing untracked `headmodel`
directory is moved to the recoverable system Trash, not permanently deleted.
The new pipeline is ready to rebuild the canonical hemisphere head models on
demand with the same YAML-selected atlas and conductivities. No model-scoped
head-model cache is introduced. Production rebuilding was not started during
implementation acceptance.

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
```

The threshold filenames are generated from the configured values; the three
shown names are the v1 profile's concrete outputs.

## Path-Based Publication And Reuse

No `provenance.json` is generated. Final-path existence is the only persistent
completion signal. A leaf is `complete` only when all four scientific artifact
paths exist and is otherwise `missing`. Existing final artifacts are preserved
without content, hash, code-version, or configuration comparison.

New artifacts are produced at temporary paths in the destination directory and
atomically renamed after successful generation. Ordinary run and
`run --resume` fill only missing paths in this order: native E-field, native
thresholds, transformed MNI E-field, and MNI thresholds. Explicit force moves
selected stimulation leaves to Trash, making their paths missing before the
same state machine runs.

Reuse is resolved from the complete normalized `frequency_group` record and is
restricted to the same subject. For each selected group, runtime scans all
same-subject groups represented by `study_base.json` for physically equivalent
existing artifacts. Missing artifacts are copied from the first deterministic
donor; if no donor exists, they are generated only in the selected path. When
multiple equivalent groups are selected together, the first selected group is
generated and becomes the in-run donor. Equality is direct record comparison,
not a hash, and implementation logic cannot recognize project phase names.
`/Volumes/VAL` is ExFAT, so reuse publication uses atomic copy rather than hard
links or filesystem clones.

Head models are also path based: existing canonical MAT files are reused and
missing files are built. An unreadable existing head model fails explicitly.
`--force` does not implicitly rebuild it.

One task failure does not delete successful independent tasks. Batch execution
continues across independent tasks for the same subject and across other
subjects, and returns nonzero if any selected task fails. Alternating group peak
and reuse recipients are skipped only when their required donor generation
fails. The complete
approved state machine is defined in
`docs/superpowers/specs/2026-07-13-path-based-vta-reuse-design.md`.

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

Plan prints deterministic JSON task rows with subject, phase, program,
electrode, frequency group, delivery mode, task kind, dependencies, and native
and MNI output leaves. Every row also reports the canonical hemisphere-specific
head-model path and path-derived status: `reuse_existing` when that MAT file is
present, otherwise `build_required`. Planning does not inspect FEM contents,
build a head model, resolve a runtime donor, or create a new authoritative
input file.

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

Status replans the expected leaves and derives `complete` or `missing` directly
from the four expected scientific artifact paths. It does not depend on an
artifact index or provenance file.

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
| Canonical YAML, study-base adapter, task DAG, CLI, path-based artifacts, and MATLAB task execution | `implementation_complete` | The path-only state machine, same-subject frequency-group reuse, missing-path repair, force-to-Trash, and MATLAB execution are implemented. |
| Static and deterministic unit coverage | `unit_validated` | Automated Python and MATLAB unit suites validate their covered contracts. |
| Historical bilateral SNr003 single-voltage backend comparison | `historical_fem_validated` | Existing numerical evidence was refreshed with zero FEM and retains its recorded `Custom_Ewert_Zhang_Middlebrooks0.05` atlas identity. |
| Representative copied-subject delivery-aware gate | `copied_subject_acceptance_passed` | Fresh continuous and alternating execution, group peak, equivalent-group copy, repair, force, and four-artifact leaves passed in the isolated SNr003 tree. |
| Fresh deterministic current gate | `current_fem_validated` | One fixed right-sided current case passed after exactly two FEM solves with the current canonical atlas. |
| Production planning | `production_rebuild_ready` | Read-only planning resolves 16 subjects, 208 tasks, and 32 missing canonical hemisphere head models. |
| Real-cohort output rebuild | `production_rebuild_not_started` | Production subject trees and model outputs have not been rebuilt by this pipeline. |

The copied-subject preparation helper is an isolation mechanism, not numerical
FEM evidence. It preserves the minimal valid BIDS hierarchy by copying the
dataset description and only the selected `derivatives/leaddbs/sub-*` tree.
Its `run_id` is one safe path component matching
`[A-Za-z0-9][A-Za-z0-9._-]*`; separators, traversal, and absolute paths are
rejected before the destination is constructed.
The accepted copied-subject root is
`/Volumes/VAL/STNSNr/validation/vta_pipeline_e2e_maskfix_20260713T172111Z`.
It contains 16 native/MNI leaf directories and 64 scientific artifacts, exactly
four per leaf, with no `provenance.json` or `qc.json`. It also verifies fresh
continuous solves, independent alternating sources, native group peak,
equivalent frequency-group reuse, missing-artifact repair, force-to-Trash, and
single-mask GM head-model construction. No production execution is implied by
any status in this table.

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

Voltage and current use paired acceptance entrypoints:

```text
run_voltage_backend_equivalence
run_current_backend_equivalence

test_run_voltage_backend_equivalence
test_run_current_backend_equivalence
```

The completed SNr003 bilateral single-voltage `simbio`-versus-canonical outputs
are historical evidence. Their zero-FEM refresh preserves the manifest's
`Custom_Ewert_Zhang_Middlebrooks0.05` atlas identity and does not relabel them
as current-atlas results. New voltage acceptance, when required, must use the
current atlas and a new copied-subject root.

A new copied-subject current suite uses SNr003 and Medtronic 3387 geometry. It
uses fixed seed `20260712` to generate hypothetical current parameters without
modifying `study_base.json`:

```text
control mode: current
amplitude range: 0.5-5.0 mA
pulse-width range: 30-120 us
hemisphere: right only
case design: one cathode with case return
```

The real current FEM gate contains exactly one deterministic hypothetical case.
The same right-sided contacts, polarity, amplitude, pulse width, and frequency
run once through standard `simbio` current mode and once through
the canonical current strategy while sharing one frozen head model. A fresh
gate therefore starts exactly two current FEM solves. Backend numerical
equivalence is evaluated only on native E-field and native
0.18/0.20/0.22 V/mm VTAs; no averaging or backend-repeat run is part of this
minimal gate. Native acceptance gates are:

```text
maximum absolute E-field difference: <= 0.05 V/m
relative L2 error: <= 1e-5
Pearson correlation: >= 0.999999
VTA Dice at every threshold: >= 0.999
relative VTA volume difference: <= 0.1%
```

The accepted current evidence from copied SNr003 is:

```text
native maximum absolute difference: 0.04443359375 V/m
native relative L2 error: 2.2273793323536e-6
native correlation: 0.999999999996588
native VTA Dice at 180/200/220 V/m: 1.0 / 1.0 / 1.0
native relative VTA volume difference: 0 / 0 / 0
```

MNI is a transformation-contract acceptance, not a legacy backend-equivalence
gate. The canonical MNI continuous field must be produced from the canonical
native continuous field using the patient's forward normalization; dimensions,
affine, finite support, and nonzero signal must be valid; repeated transforms
must be deterministic; and MNI binary VTAs must be recreated from that MNI
continuous field at 180/200/220 V/m. Legacy SimBio maps FEM sample points into
MNI before interpolation, so its direct-MNI field is intentionally not the
numerical reference for the canonical native-to-MNI architecture.

The standard Lead-DBS `simbio` current path is the reference implementation.
The candidate implementation is the shared canonical backend in current mode.
The legacy registry one-solve wrapper remains outside canonical execution and
is not an execution path for either paired gate. Both accepted paths must use
the same fixed native headmodel under the copied subject tree.

For native numerical comparison only, the standard `simbio` local E-field grid
is the authoritative comparison grid. In a fresh gate the canonical raw
tetrahedral field is exported directly to the standard native reference grid,
bypassing the coarser 0.7 mm production-native export. No binary image is
resampled.
Existing paired NIfTI outputs may be re-compared without another solve, but a
coarse previous export cannot reconstruct discarded tetrahedral detail.
If dimensions and affine already match the reference within the acceptance
tolerance, alignment is a no-op and must not interpolate the candidate again.
Re-comparison moves any replaced metrics or summary file to the filesystem
Trash first. It cannot upgrade the overall result unless the original run also
recorded that the production subject tree remained unchanged.

If a completed two-solve gate identifies a candidate-only implementation
defect, recovery may reuse the existing standard SimBio reference, copied
subject, fixed headmodel, and deterministic fixture. Each attempt is recorded
before the old candidate output directory is moved to Trash and only the
canonical candidate is solved again. The recovery result records the latest
one-solve attempt and the actual accumulated solve count for that run lineage;
it is not represented as a fresh two-solve gate.

Multiple-cathode, electrode-return, repeatability, and continuous multi-current
behavior remain covered by deterministic solver-free unit fixtures. The
independent RHS/vector-field superposition fixture requires signed vector
superposition; maximum or sum of scalar E-field magnitudes is not an acceptable
reference.

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
- path-only skip and partial-artifact repair;
- one equivalent frequency-group copy, represented by T2/T3 only in the SNr003 fixture;
- dependency failure isolation;
- resume-compatible path reuse; and
- force-to-Trash behavior.

The representative pilot does not run all 20 SNr003 tasks. It executes two
continuous joint solves, one hemisphere's two alternating source solves and
group-peak derivation, plus the logical frequency-group reuse path and
deterministic current suite. T2/T3 are fixture labels only and are never
hard-coded by the generic planner or executor.

Acceptance must not write or overwrite the real
`/Volumes/VAL/STNSNr/derivatives/leaddbs/sub-*` tree. A real cohort run requires
separate explicit approval after implementation acceptance.

## Implementation Boundary

Implementation follows the approved detailed plan. Relevant documentation is
updated before each code change, and repository tests and tooling use the Conda
environment `leaddbs`. Copied-subject and production FEM execution remain
separate, explicit acceptance operations.
