# Generic VTA/E-field Pipeline

The generic VTA pipeline consumes canonical stimulation records from a
`study_base.json` file and model parameters from a `vta_model.yaml` file.
Project-specific workbooks, target labels, component labels, HF/ULF roles, and
clinical endpoint definitions are outside the VTA execution contract.

## Implementation Status

| Scope | Status | Meaning |
| --- | --- | --- |
| Canonical YAML, study-base adapter, task DAG, CLI, provenance, and MATLAB task execution | `implemented` | The delivery-aware implementation exists in the repository. |
| Static and deterministic unit coverage | `unit_validated` | Automated Python and MATLAB unit suites validate their covered contracts. |
| Historical bilateral SNr003 single-voltage backend comparison | `fem_validated` | Existing numerical evidence covers only the documented single-voltage pilot. |
| Real-cohort output rebuild | `production_rebuild_not_started` | Production subject trees and model outputs have not been rebuilt by this pipeline. |

The copied-subject end-to-end FEM gate is separate from unit validation. Its
preparation helper creates an isolated validation study base and subject copy;
creating that copy does not run FEM or establish end-to-end acceptance.

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
task that depends on every source task. Task IDs are SHA-256 hashes of canonical
VTA-semantic task payloads; ignored study labels cannot change them.

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

## Leaf Artifacts And Provenance

Every completed native or MNI leaf contains:

```text
efield.nii.gz
vta_threshold-0p18Vpermm.nii.gz
vta_threshold-0p20Vpermm.nii.gz
vta_threshold-0p22Vpermm.nii.gz
provenance.json
```

`provenance.json` contains only `schema_version`, `run_id`, `input_hash`,
`study_base_sha256`, `vta_model_sha256`, `code_commit`, `efield_sha256`, and
`final_status`, in that order. `final_status` is last and accepts only
`completed` or `failed`. Git absence is represented by `code_commit: null`.

Resume reuses a leaf only when its status is `completed`, its input hash
matches the planned input, its E-field exists, and the current E-field SHA-256
matches provenance. Otherwise the leaf is stale and is not reused.

Force replacement moves the previous leaf directory to the filesystem Trash
before creating a new leaf. Failure cleanup also moves partial scientific
artifacts to Trash and then writes a failed provenance file with
`efield_sha256: null`. If Trash cannot be used, replacement or cleanup aborts
without permanently deleting data.

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
`missing`, `completed`, `failed`, or `stale`.

## MATLAB Task Contract

Python sends one resolved task JSON to `mh_vta_run_canonical_task`. Required
fields include task/run IDs, task kind, subject and reconstruction paths,
phase/program/electrode/group IDs, hemisphere, delivery mode, canonical
sources, conductivities, atlas, output spaces, thresholds, output leaves,
input hashes, `implementation_sha256`, and resume/force state. The
implementation hash is the same value used by resume identity and the embedded
head-model contract. Backend selection and project labels are not part of the
task payload.

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

The embedded `mh_vta_headmodel_contract` records subject, side, atlas,
conductivity, reconstruction, native-anchor, and implementation hashes. Missing
head models are rebuilt. A stale contract is rejected unless replacement was
explicitly authorized.

When `--force` explicitly authorizes an incompatible head-model replacement,
the old head model and matching Horn protocol are moved to the same-filesystem
Trash before rebuilding. If that move cannot be completed, execution aborts;
canonical execution never permanently deletes an existing head model.

Canonical head-model preparation invokes the Horn meshing path in an internal
head-model-only mode. That call stops immediately after writing the volume
conductor and never writes a legacy dynamic-grid VTA; canonical E-field and VTA
artifacts are produced only by the fixed-grid executor below.

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

The native peak is thresholded, transformed once to MNI, and thresholded again
in MNI. No additional FEM solve is performed for the derived task.

## Execution Policy

Tasks for one subject execute sequentially in DAG order. Different subjects may
execute concurrently up to `--workers`. A failed subject stops its dependent
tasks but does not cancel other subjects. The command returns nonzero when any
selected task fails.
