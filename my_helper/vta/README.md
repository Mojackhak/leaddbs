# Generic VTA/E-field Pipeline

The generic VTA pipeline consumes canonical stimulation records from a
`study_base.json` file and model parameters from a `vta_model.yaml` file.
Project-specific workbooks, target labels, component labels, HF/ULF roles, and
clinical endpoint definitions are outside the VTA execution contract.

## Implementation Status

| Scope | Status | Meaning |
| --- | --- | --- |
| Canonical YAML, study-base adapter, task DAG, CLI, path-based artifacts, and MATLAB task execution | `implementation_complete` | Provenance/hash reuse has been removed; same-subject frequency-group reuse, missing-path repair, force-to-Trash, and endpoint-independent execution are implemented. |
| Static and deterministic unit coverage | `unit_validated` | Python and MATLAB contract suites validate path state, donor reuse, failure isolation, voltage/current boundaries, output actions, and atomic publication. |
| Historical bilateral SNr003 single-voltage backend comparison | `historical_fem_validated` | Existing single-voltage evidence was re-compared with zero FEM solves; its original `Custom_Ewert_Zhang_Middlebrooks0.05` atlas identity is preserved and is not relabeled as current-atlas evidence. |
| Representative copied-subject delivery-aware gate | `copied_subject_acceptance_passed` | Fresh continuous and alternating tasks, group-peak derivation, equivalent-group reuse, repair, force-to-Trash, four-artifact leaves, and GM-mask head-model construction passed in an isolated SNr003 copy. |
| Fresh deterministic current gate | `current_fem_validated` | One fixed right-sided current case passed standard SimBio versus canonical comparison after exactly two FEM solves using `Custom_Ewert_Zhang_Middlebrooks`. |
| Production planning | `production_rebuild_ready` | Read-only planning resolves 16 subjects, 208 tasks, and 32 missing canonical hemisphere head models without writing outputs. |
| Real-cohort output rebuild | `production_rebuild_not_started` | Production subject trees and model outputs have not been rebuilt by this pipeline. |

The copied-subject representative FEM gate is separate from unit validation. Its
preparation helper creates an isolated minimal BIDS tree containing the source
`dataset_description.json` and only the selected
`derivatives/leaddbs/sub-$SUBJECT_ID` directory, then rewrites the validation
study base to that copied subject. Creating the copy does not run FEM or
establish end-to-end acceptance.

The representative gate does not run all 20 SNr003 tasks. It covers left and
right continuous solves, one two-source alternating group and its group peak,
one equivalent frequency-group copy represented by T2/T3 in the fixture, and a
minimal right-sided deterministic current acceptance with two FEM solves.
T2/T3 are fixture values only; implementation reuse is based on normalized
same-subject frequency-group content. Production all-subject execution remains
a separate operational goal.

The accepted delivery-aware run is
`/Volumes/VAL/STNSNr/validation/vta_pipeline_e2e_maskfix_20260713T172111Z`.
It contains 16 native/MNI leaves and exactly four scientific files per leaf,
with no provenance or QC sidecars. Head-model construction used the unified
patient-space GM mask surface. The fresh current numerical run is
`/Volumes/VAL/STNSNr/validation/vta_current_backend_equivalence_20260713_113545_719`;
it passed the native E-field, three native VTA, MNI transform, two-solve, and
production-tree safety gates.

The current acceptance runner also supports two bounded maintenance modes.
`compare_existing` recomputes metrics with zero FEM solves. `rerun_candidate`
is reserved for a failed fixed-contract gate: it reuses the existing standard
SimBio reference and copied headmodel, records the attempt, moves the old
candidate directory to Trash, and performs exactly one new canonical one-solve
FEM per attempt. Its summary keeps the accumulated solve count rather than
presenting recovery as a fresh gate.

## Canonical Backend Architecture

Canonical FEM execution has one production path:

```text
mh_vta_execute_canonical_task
  -> mh_vta_backend_simbio_onesolve_canonical
       -> mh_vta_assemble_boundary(control_mode)
       -> mh_vta_fem_apply_dbs
       -> mh_vta_fem_calc_gradient
       -> mh_vta_export_canonical_outputs
```

Voltage uses a Dirichlet boundary strategy. Current uses a current RHS plus
case/electrode return boundary strategy. Both modes share the same solver,
gradient calculation, electrode-removal geometry, native/MNI export, and
threshold pipeline. Canonical tasks never pass through the legacy registry
wrapper.

## Public Model Profile

The `vta_model_v1` public profile contains only tissue conductivity, atlas,
output-space, and binary-threshold settings:

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

Threshold values in this profile use `V/mm`. Continuous E-field NIfTI values
and threshold application use `V/m`, so the effective thresholds are 180, 200,
and 220 V/m.

## Fixed Internal Behavior

The public YAML does not expose backend selection, solve unit, mesh controls,
tissue-surface controls, electrode removal, smoke settings, random seeds, or
acceptance tolerances. Production calculations call the unified canonical
backend directly; that backend uses the SimBio one-solve FEM implementation
for both voltage and current control. The Lead-DBS internal default is
`remove_electrode=true`.

The fixed removal behavior solves FEM on the complete mesh. Before continuous
E-field interpolation, it reproduces the complete standard Horn export
geometry: remove contact/insulator tetrahedra, align samples to the electrode
axis, displace tissue samples radially to the lead surface, and remove samples
that cannot be mapped outside the lead. It is applied uniformly to
voltage/current and continuous/alternating tasks.

The configured atlas supplies a patient-space `gm_mask.nii.gz`. Canonical
head-model construction uses Lead-DBS `mask` geometry, which extracts one GM
surface at `max(mask)/2`; it does not sequentially resolve every tissue-type-1
ROI surface from `atlas_index.mat`. This fixed internal choice prevents
overlapping parent and subregion ROIs from causing combinatorial mesh growth
and is not exposed in YAML.

Continuous frequency-group sources are solved jointly. Alternating sources are
solved independently, and their group-level peak E-field is derived using a
voxelwise maximum. The pipeline does not infer duty cycle or generate a
time-weighted E-field.

## Study-Base Input Boundary

The VTA adapter reads only the stimulation and Lead-DBS location fields below:

```text
schema_version
study.subjects[].subject_id
study.subjects[].subject_label
study.subjects[].subject_sources.leaddbs_subject_dir
study.subjects[].subject_sources.electrode_reconstruction.path
study.subjects[].contact_numbering
study.subjects[].electrodes
study.subjects[].phases[].phase_id
study.subjects[].phases[].programs[].program_id
study.subjects[].phases[].programs[].electrode_programs[]
study.subjects[].phases[].programs[].electrode_programs[].frequency_groups[]
study.subjects[].phases[].programs[].electrode_programs[].frequency_groups[].sources[]
```

Source execution uses `frequency_hz`, `control_mode`, `amplitude`,
`pulse_width_us`, contacts, polarity, and fractions. The adapter ignores
`component_id`, `source_label`, Target, clinical observations, condition roles,
HF/ULF labels, and endpoint definitions.

The current study-base contact convention is bilateral contiguous zero-based.
The adapter validates each global contact against its electrode range and
converts it to a side-local one-based contact before creating MATLAB tasks.
`case` remains `case`.

Each frequency group must contain at least one source and use one control mode.
Cathode fractions and anode fractions are normalized independently within each
source. A continuous group cannot assign the same non-case electrode contact to
more than one source. The canonical adapter does not impose the legacy
four-source limit. Hierarchical execution identities must be unique: a subject
cannot repeat a phase ID, a phase cannot repeat a program ID, a program cannot
repeat an electrode ID, an electrode program cannot repeat a frequency-group
ID, and a group cannot repeat a source ID. The adapter rejects collisions
before any two physically different tasks can resolve to the same output leaf.

## Deterministic Task DAG

Each selected subject has one canonical head-model prerequisite. A continuous
frequency group creates one joint solve task containing every group source. An
alternating group creates one solve task per source and one derived group-peak
task that depends on every source task. Task IDs may remain deterministic
SHA-256 identifiers, but hashes do not control output reuse or recalculation.
Ignored study labels cannot change the numerical task definition.

Reuse is resolved only within one subject. Continuous joint and alternating
group-peak artifacts require equality of the complete normalized
`frequency_group`. An alternating source artifact requires equality of that
source's normalized physical record and execution context; a change to another
source in the same group therefore does not invalidate the unchanged source
leaf. Runtime scans every same-subject group represented by `study_base.json`
and copies a matching artifact into the selected hierarchical leaf. If no donor
exists, computation occurs only in the selected path. When multiple equivalent
tasks are selected together, the first task in deterministic order is their
in-run owner. A failed owner marks still-dependent recipients as
`skipped_dependency`; it is not silently replaced by another physical solve in
the same run. Equality is direct record comparison; no physical-stimulation
hash is generated. Phase names such as T2/T3 are fixture data and are never
recognized by generic planner or executor logic.

Production VTA modules cannot branch on concrete subject IDs, phase IDs,
program IDs, target/component labels, study names, HF/ULF roles, or
chronic/immediate labels. Concrete values such as SNr003 and T1/T2/T3 are
permitted only in isolated fixtures and copied-subject acceptance scripts. The
canonical execution path receives selected subjects through generic task input
and does not use the legacy `STNSNR_VTA_SUBJECT_IDS` environment variable.

Output directories are derived from canonical identifiers rather than a flat
stimulation label:

```text
$LEADDBS_SUBJECT_DIR/stimulations/$SPACE/
  phase-$PHASE_ID/
    program-$PROGRAM_ID/
      electrode-$ELECTRODE_ID/
        frequency-group-$FREQUENCY_GROUP_ID/
          delivery-continuous/joint/
          delivery-alternating/sources/source-$SOURCE_ID/
          delivery-alternating/derived/group-peak/
```

Subject, phase, program, electrode, and frequency-group filters are exact. An
unknown selector or a selection producing no solve tasks is an error rather
than a successful empty plan.

## Leaf Artifacts And Path State

Every completed native or MNI leaf contains:

```text
efield.nii.gz
vta_threshold-0p18Vpermm.nii.gz
vta_threshold-0p20Vpermm.nii.gz
vta_threshold-0p22Vpermm.nii.gz
```

No `provenance.json` is generated. Final-path existence is the only persistent
completion signal. A leaf is `complete` when all four paths exist and is
otherwise `missing`. Ordinary `run` and `run --resume` preserve every existing
final artifact and generate only missing paths.

Missing artifacts are repaired in dependency order: native E-field, native
thresholds, transformed MNI E-field, then MNI thresholds. An existing native
E-field can therefore repair downstream outputs without another FEM solve.
New artifacts and frequency-group copies use a temporary path in the destination
directory followed by atomic rename. `/Volumes/VAL` is ExFAT and does not
support hard links or filesystem clones, so equivalent frequency-group leaves are
materialized by copying only missing files.

Force replacement moves selected stimulation leaf directories to the
filesystem Trash before using the same missing-path state machine. If Trash
cannot be used, replacement aborts without permanently deleting data.

## Command-Line Interface

```text
vta-model validate --study-base PATH --vta-model PATH (--subject ID ... | --all-subjects) [selectors]
vta-model plan     --study-base PATH --vta-model PATH (--subject ID ... | --all-subjects) [selectors]
vta-model run      --study-base PATH --vta-model PATH (--subject ID ... | --all-subjects) [selectors] [--workers N] [--resume | --force]
vta-model status   --study-base PATH --vta-model PATH (--subject ID ... | --all-subjects) [selectors]
```

Selectors are repeatable `--phase`, `--program`, `--electrode`, and
`--frequency-group`. One of repeatable `--subject` or `--all-subjects` is
required, and the two forms are mutually exclusive. `--workers` is a positive
integer and parallelizes subjects only.

`validate` requires one unlabelled preoperative anchor T1w, the forward native
to MNI transform, the configured atlas index and template GM mask, and the
patient-space atlas `gm_mask.nii.gz`; a `label-Brain` mask cannot satisfy the
anchor requirement. `validate`, `plan`, and `status` are read-only. `plan` emits one JSON row per
task in stable subject/DAG order. Each row includes the task identifiers,
dependencies, native/MNI leaves, and the canonical hemisphere-specific head
model path with status `reuse_existing` or `build_required`. The head-model
status is path based and does not build or inspect FEM data. `status` reports
every planned native and MNI leaf as `missing` or `complete`. The runtime
summary may additionally report
`generated`, `copied`, `skipped_existing`, `failed`, and
`skipped_dependency`.

## MATLAB Task Contract

Python sends one resolved task JSON to `mh_vta_run_canonical_task`. Required
fields include task ID, task kind, subject and reconstruction paths,
phase/program/electrode/group IDs, hemisphere, delivery mode, canonical
sources, conductivities, atlas, output spaces, thresholds, output leaves,
and missing-artifact instructions. Input hashes, implementation hashes,
backend selection, and project labels are not part of the execution payload.

Continuous groups resolve to one solve unit containing all sources. Alternating
groups resolve to one solve unit per source. Every production solve uses
`simbio_onesolve`; an alternating source can still contain multiple active and
return contacts within its independent solve.

The MATLAB entry point validates first and then dispatches by task kind.
`continuous_joint` and `alternating_source` tasks enter the canonical
one-solve executor. `alternating_group_peak` is a derived task: it reads the
completed source-level native E-fields, forms the native voxelwise maximum,
thresholds it, transforms the continuous maximum to MNI, and thresholds again.
The derived task never invokes FEM.

## Voltage And Current Boundary Values

Voltage boundaries use signed volts. Current boundaries convert public mA to A
using `1e-3`. Cathode values are negative and anode values are positive. Case
return uses the existing SimBio unipolar/current-return path; electrode-return
contacts remain explicit boundary groups. Multi-source current is assembled as
one signed FEM right-hand side, not as a maximum or sum of scalar E-field
magnitudes.

## Head Model And Output-Space Order

Each hemisphere uses a canonical native head model under:

```text
$LEADDBS_SUBJECT_DIR/headmodel/native/sub-$SUBJECT_ID_desc-headmodel1.mat  # right
$LEADDBS_SUBJECT_DIR/headmodel/native/sub-$SUBJECT_ID_desc-headmodel2.mat  # left
```

Head-model reuse is path based. A missing canonical head-model file is built; an
existing file is reused without provenance or hash comparison. A present but
unreadable or structurally invalid MAT file fails explicitly rather than being
silently replaced. `--force` applies to stimulation leaves and does not rebuild
an existing head model. To rebuild a head model, the operator must first move
its canonical file out of the way.

Every reused or newly built canonical head model must also satisfy the FEM
coordinate-unit contract before execution continues. `mesh.pnt` and `vol.pos`
must be finite real `N x 3` arrays with the same nodes. If `mesh.unit` exists,
it must be `mm`. After conversion to `double`, `mesh.pnt / 1000` must match
`vol.pos` within `1e-6 m` at every node, and all `vol.pos` coordinates must have
absolute magnitude below `2 m`. The canonical backend enforces this contract
immediately after loading the head model; existing-model preparation also uses
it for early failure. The pipeline never attempts an automatic conversion,
because coordinate-only repair cannot validate the units used to assemble the
stored FEM matrices. An empty suprathreshold VTA is not a unit-contract failure.

Canonical head-model preparation invokes the Horn meshing path in an internal
head-model-only mode. That call stops immediately after writing the volume
conductor and never writes a legacy dynamic-grid VTA; canonical E-field and VTA
artifacts are produced only by the fixed-grid executor below.

Horn atlas iteration maps each bilateral ROI cell back to its structure row
before reading `tissuetypes`; the metadata contains one tissue type per
structure, not one value per hemisphere cell. This is required for multi-entry
custom atlas sets such as `Custom_Ewert_Zhang_Middlebrooks`.

The authoritative order is:

1. solve FEM in native space;
2. sample continuous E-field onto the preoperative anchor NIfTI geometry;
3. threshold native E-field at 180, 200, and 220 V/m;
4. transform the continuous native E-field to `MNI152NLin2009bAsym`;
5. threshold the transformed MNI E-field at the same values.

Binary VTA files are never spatially warped from native to MNI.

For alternating groups, source-level native E-fields remain preserved. The
derived native field is:

```text
E_group_peak_native(v) = max_s E_s_native(v)
```

Native fixed-grid interpolation intentionally uses `NaN` outside each FEM
sample hull. Group peak therefore takes the maximum over finite source values
at each voxel and preserves `NaN` only where every source is non-finite.

The native peak is thresholded, transformed once to MNI, and thresholded again
in MNI. No additional FEM solve is performed for the derived task.

## Execution Policy

Tasks for one subject execute sequentially in DAG order. Different subjects may
execute concurrently up to `--workers`. A failed task skips only dependency
descendants; independent tasks for the same subject and tasks for other subjects
continue. The command returns nonzero when any selected task fails.

This path-only design intentionally favors compatibility over automatic
invalidation. Existing artifacts are reused even after code, YAML, atlas
content, or metadata changes. Operators must use `--force` for stimulation
outputs or move a canonical head-model file when intentional recalculation is
required. The complete approved state machine is documented in
`docs/superpowers/specs/2026-07-13-path-based-vta-reuse-design.md`.
