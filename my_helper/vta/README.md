# Generic VTA/E-field Pipeline

The generic VTA pipeline consumes canonical stimulation records from a
`study_base.json` file and model parameters from a `vta_model.yaml` file.
Project-specific workbooks, target labels, component labels, HF/ULF roles, and
clinical endpoint definitions are outside the VTA execution contract.

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
