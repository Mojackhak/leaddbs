# Generic VTA/E-field Pipeline

The generic VTA pipeline consumes canonical stimulation records from a
`study_base.json` file and model parameters from a `vta_model.yaml` file.
Project-specific workbooks, target labels, component labels, HF/ULF roles, and
clinical endpoint definitions are outside the VTA execution contract.

## Implementation Status

| Scope | Status | Meaning |
| --- | --- | --- |
| Canonical YAML, study-base adapter, task DAG, CLI, path-based artifacts, and MATLAB task execution | `path_only_runtime_implemented` | Provenance/hash reuse has been removed; same-subject frequency-group reuse and missing-path repair are implemented. |
| Static and deterministic unit coverage | `unit_validated` | Python and MATLAB contract suites validate path state, donor reuse, failure isolation, voltage/current boundaries, output actions, and atomic publication. |
| Historical bilateral SNr003 single-voltage backend comparison | `fem_validated` | Existing numerical evidence covers only the documented single-voltage pilot. |
| Representative copied-subject delivery-aware gate | `path_reuse_partially_validated` | Existing continuous leaves were skipped by path, two alternating source solves and one group peak were generated, and an equivalent same-subject group copied with no FEM. Those historical leaves predate removal of `provenance.json`, so they do not satisfy the final leaf-content gate. A fresh continuous solve and the corrected current numerical gate remain pending. |
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
Production all-subject execution remains a separate operational goal.

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
acceptance tolerances. Production calculations use `simbio_onesolve` and the
Lead-DBS internal default `remove_electrode=true`.

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
four-source limit.

## Deterministic Task DAG

Each selected subject has one canonical head-model prerequisite. A continuous
frequency group creates one joint solve task containing every group source. An
alternating group creates one solve task per source and one derived group-peak
task that depends on every source task. Task IDs may remain deterministic
SHA-256 identifiers, but hashes do not control output reuse or recalculation.
Ignored study labels cannot change the numerical task definition.

Reuse is resolved at the complete `frequency_group` level and only within the
same subject. For each selected group, runtime scans all same-subject groups
represented by `study_base.json`. If a normalized group record is exactly equal
and a matching artifact already exists, that artifact is copied into the
selected hierarchical leaf. If no donor exists, computation occurs only in the
selected path. When multiple equivalent groups are selected together, the
first selected group in deterministic order is generated and becomes the
in-run donor. Equality is direct record comparison; no physical-stimulation
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

`validate`, `plan`, and `status` are read-only. `plan` emits tasks in stable
subject/DAG order. `status` reports every planned native and MNI leaf as
`missing` or `complete`. The runtime summary may additionally report
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
