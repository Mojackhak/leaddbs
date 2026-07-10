# Standard BIDS and Lead-DBS DWI Preprocessing Goal

## Status

Design approved. Directory and wrapper naming generalization are complete.
The YAML loader and runner modes described below remain implementation work.

## Goal

Provide one project-agnostic DWI preprocessing workflow for projects that use a
standard BIDS raw-data tree and Lead-DBS derivatives. Project differences must
be limited to the project root, session, patient selection, DWI acquisition
metadata, anatomical anchor, and execution parameters.

The workflow must reuse the existing single-subject Synb0/topup/eddy processing
backend and must not duplicate numerical processing in project wrappers.

## Supported Project Contract

```text
<study_root>/
|-- rawdata/
|   `-- sub-<ID>/
|       `-- ses-<session>/
|           `-- dwi/
|               |-- *_dwi.nii.gz or *_dwi.nii
|               |-- *_dwi.json
|               |-- *_dwi.bval
|               `-- *_dwi.bvec
`-- derivatives/
    `-- leaddbs/
        `-- sub-<ID>/
            |-- coregistration/anat/
            |-- preprocessing/dwi/
            `-- qc/
```

Each subject DWI directory must resolve to exactly one DWI four-file set. BIDS
entities such as `acq-ax`, `dir-AP`, or `run-1` may appear in the source name,
but the public configuration does not require an acquisition selector. Multiple
DWI candidates are an error rather than an invitation to choose one silently.

## Public YAML Configuration

```yaml
schema_version: 1

project:
  name: meige
  study_root: /Volumes/VAL/meige
  session: preop

dwi:
  distortion_correction: synb0
  phase_encoding_vector: [0, 1, 0]
  total_readout_time:
    strategy: json_then_fallback
    seconds: 0.05

anatomy:
  synb0_modality: T1w
  coregistration_anchor: T2w
  allow_anchor_fallback: false

lead_dbs:
  run_coregistration: false
  coregistration_method: SPM

processing:
  generate_optional_dwi_qc: true

execution:
  force: false
  parallel: false
  parallel_workers: 1
  max_concurrent_synb0: 1
  synb0_min_memory_gb: 12

runtime:
  freesurfer_license: /Applications/freesurfer/8.2.0/license.txt
  synb0:
    container_engine: auto
    container_image: leonyichencai/synb0-disco:v3.1
    work_root: /Users/mojackhu/Library/Caches/leaddbs/synb0_work
```

Patient IDs are not stored in the project YAML. They are supplied for a
specific run. If no IDs are supplied, the runner discovers subjects with a DWI
under the standard BIDS path.

Runtime options override YAML values, and YAML values override internal
defaults.

## Public Runner

The final public entry point is:

```matlab
result = run_bids_dwi_preprocessing( ...
    'Config', configPath, ...
    'Mode', 'validate', ...
    'SubjectIds', {'Subject001'});
```

Supported modes:

- `validate`: validate configuration and every resolved input without running
  image processing.
- `plan`: build and report resolved subject job specifications without writing
  image derivatives.
- `run`: execute the existing processing batch.

Until the YAML loader is implemented, the renamed wrapper may retain its current
name-value interface as a compatibility path. It must require `StudyRoot`, allow
an empty `SubjectIds` list for discovery, and contain no Meige cohort list.

## Processing Flow

```text
load and validate configuration
-> resolve explicit or discovered subjects
-> discover one DWI four-file set per subject
-> resolve anchorNative T1w and the selected coregistration anchor
-> build explicit jobSpec values
-> stage raw DWI in preprocessing/dwi
-> run Synb0-DISCO, topup, and eddy
-> write corrected DWI, bval, rotated bvec, and mean b0
-> generate optional FA, masks, and QC
-> stage corrected B0 in coregistration/anat
-> write a resolved manifest and subject status records
```

With `run_coregistration=false`, the corrected B0 remains pending for manual
Lead-DBS UI coregistration. `coregistration_method=SPM` becomes active only when
automatic coregistration is enabled.

## Internal Fixed Behavior

The following values are implementation contracts and are not public YAML
fields:

- the fake-B0 coregistration tag;
- the B0 `IntendedUse` metadata value;
- Lead-DBS derivative directory names;
- formal corrected DWI and B0 names;
- QC and status filename derivation.

Keeping these values internal prevents project configuration from breaking
Lead-DBS file discovery and UI integration.

## Existing Components to Reuse

- `mh_fiber_dwi_bids_jobspec`: resolve one standard BIDS/Lead-DBS job.
- `mh_fiber_process_imported_dwi_batch`: dispatch independent subject jobs.
- `mh_fiber_process_imported_dwi`: execute one resolved job specification.
- `mh_fiber_dwi_distortion_correction`: run Synb0/topup/eddy and write formal
  corrected outputs.
- `run_project_dwi_fake_b0_coreg`: compatibility preset for the current fake-B0
  workflow.

## Validation Rules

- Reject unsupported schema versions and unknown YAML fields.
- Reject subject IDs containing the `sub-` prefix.
- Require exactly one DWI NIfTI and matching JSON, bval, and bvec files.
- Require matching DWI volume, bval, and bvec counts and at least one b0.
- Require anchorNative T1w for Synb0.
- Require the configured coregistration anchor unless fallback is enabled.
- Require a three-element signed phase-encoding vector and a positive readout
  time.
- Validate all selected subjects before starting expensive computation.

## Run Records

Each execution should write a versioned run directory under the Lead-DBS import
logs rather than overwrite one cohort-level CSV:

```text
derivatives/leaddbs/import_logs/dwi_runs/<run_id>/
|-- config_source.yaml
|-- config_resolved.json
|-- job_manifest.csv
|-- status.csv
`-- subjects/<ID>_dwi_preprocessing_qc.json
```

## Implementation Phases

1. Complete: generalize the current directory, wrapper, test, and documentation names.
2. Add strict YAML loading and configuration validation.
3. Add `validate`, `plan`, and `run` modes to the public runner.
4. Add versioned run manifests and status outputs.
5. Replace Meige and STN/SNr project wrappers with thin YAML presets while
   preserving compatibility entry points where required.

## Test Plan

- Verify that a generic dry run accepts an explicit study root and subject list.
- Verify that an empty subject list is preserved for BIDS discovery.
- Verify that no Meige study root, pilot list, or cohort generator remains in the
  generic wrapper.
- Verify acquisition-labeled DWI discovery with one candidate.
- Verify that multiple DWI candidates fail with `AmbiguousRawDwi`.
- Verify strict YAML field, type, and enum validation.
- Compare resolved Meige job specifications from the old and new entry paths.
- Run one subject in a temporary project and verify corrected DWI, gradients,
  B0 geometry, metadata, and Lead-DBS UI visibility.

## Acceptance Criteria

- A new standard BIDS/Lead-DBS project requires configuration, not a new MATLAB
  wrapper.
- A runtime subject list processes only those subjects.
- Omitting the subject list discovers all valid BIDS DWI subjects.
- Raw BIDS data are never modified.
- Existing Synb0/topup/eddy numerical behavior and Lead-DBS B0 naming remain
  unchanged.
- No file or function under `my_helper/dwi` is named after Meige or STNVOP.
