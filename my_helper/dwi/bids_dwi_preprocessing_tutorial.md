# YAML-driven BIDS DWI Preprocessing Tutorial

## Scope

`run_bids_dwi_preprocessing` provides one project-independent workflow for DWI
data stored in a standard BIDS raw-data tree with Lead-DBS derivatives. It can:

1. discover or select subjects;
2. validate each DWI four-file set and anatomical input;
3. create an execution plan;
4. stage DWI data under Lead-DBS derivatives;
5. run Synb0-DISCO, topup, and eddy;
6. write corrected DWI, gradients, mean b0, optional QC, and a B0 target for
   Lead-DBS coregistration;
7. preserve an immutable record for each invocation.

This workflow starts from an existing BIDS DWI four-file set. If the source is
DICOM, first follow `my_helper/dwi/dicom_dwi_import.md`.

## Required Directory Layout

Each selected subject must have exactly one DWI NIfTI and matching sidecars:

```text
study_root_path/
|-- rawdata/
|   `-- sub-subjectID/
|       `-- ses-preop/
|           `-- dwi/
|               |-- sub-subjectID_ses-preop_acq-ax_dwi.nii.gz
|               |-- sub-subjectID_ses-preop_acq-ax_dwi.json
|               |-- sub-subjectID_ses-preop_acq-ax_dwi.bval
|               `-- sub-subjectID_ses-preop_acq-ax_dwi.bvec
`-- derivatives/
    `-- leaddbs/
        `-- sub-subjectID/
            `-- coregistration/
                `-- anat/
                    |-- ...space-anchorNative...T1w.nii
                    `-- ...space-anchorNative...T2w.nii
```

Rules:

- The DWI directory must contain exactly one `*_dwi.nii.gz` or `*_dwi.nii`.
- Its `.json`, `.bval`, and `.bvec` files must use the same basename.
- The DWI volume, bval, and bvec counts must match.
- At least one volume must have `bval < 10`.
- Synb0 requires an anchorNative T1w image.
- The configured coregistration anchor must exist. With a T2w anchor, both T1w
  and T2w are therefore required unless anchor fallback is enabled.
- Subject IDs in YAML or MATLAB must omit the `sub-` prefix.
- The session value must omit the `ses-` prefix.

## Create a Project YAML File

Create a project-owned configuration such as:

```text
project_config_path/dwi.yaml
```

Use this template:

```yaml
schema_version: 1

project:
  name: project_name
  study_root: study_root_path
  session: preop

subjects:
  mode: auto

dwi:
  distortion_correction: synb0
  phase_encoding_vector: [0, 1, 0]
  b0_reference:
    strategy: mean
    threshold: 10
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
  freesurfer_license: freesurfer_license_path
  synb0:
    container_engine: auto
    container_image: leonyichencai/synb0-disco:v3.1
    work_root: synb0_work_path
```

The loader rejects unknown fields. Do not add project notes or unsupported
keys inside this YAML file.

## YAML Fields

### Project

- `schema_version`: configuration schema; currently must be `1`.
- `project.name`: descriptive project name used in the resolved configuration.
- `project.study_root`: directory containing `rawdata` and `derivatives`.
- `project.session`: BIDS session label without `ses-`, such as `preop`.

### Subject selection

Use automatic discovery to include every subject with a DWI under the selected
session:

```yaml
subjects:
  mode: auto
```

Use an explicit list for a controlled subset:

```yaml
subjects:
  mode: explicit
  ids:
    - Subject001
    - Subject002
```

- `subjects.mode`: `auto` or `explicit`.
- `subjects.ids`: required and nonempty for `explicit`; forbidden for `auto`.
- IDs must not include `sub-`.

### DWI correction

- `dwi.distortion_correction`: `synb0` or `none`.
- `dwi.phase_encoding_vector`: three-element signed unit vector with exactly one
  nonzero axis, for example `[0, 1, 0]` or `[0, -1, 0]`.
- `dwi.b0_reference.strategy`: `mean` preserves the compatibility behavior;
  `last` selects the final volume satisfying the configured b0 threshold and
  moves it to the first eddy input position.
- `dwi.b0_reference.threshold`: positive b-value threshold used to identify b0
  volumes; the default is `10`.
- `dwi.total_readout_time.strategy`: `json_then_fallback` or `fixed`.
- `dwi.total_readout_time.seconds`: positive readout time in seconds.

With `json_then_fallback`, the workflow uses a valid `TotalReadoutTime` from the
DWI JSON and otherwise uses `seconds` as the fallback. With `fixed`, it always
uses the configured value.

With `last`, DWI volumes, b-values, and b-vectors are reordered together for
eddy. Corrected DWI volumes and rotated b-vectors are restored to source order
after eddy, and the formal corrected b0 is extracted from the selected source
volume rather than averaging all corrected b0 volumes. The reversible mapping
and selected-reference hash are stored in the run provenance.

Phase-encoding direction and readout time are acquisition-specific. Do not copy
them from another project without checking the DICOM or scanner metadata.

### Anatomy and coregistration

- `anatomy.synb0_modality`: currently must be `T1w`.
- `anatomy.coregistration_anchor`: `T1w` or `T2w`.
- `anatomy.allow_anchor_fallback`: when `true`, a missing T2w anchor may fall
  back to T1w; it does not bypass the T1w requirement for Synb0.
- `lead_dbs.run_coregistration`: when `false`, stage corrected B0 for later
  manual Lead-DBS UI coregistration; when `true`, run coregistration during the
  workflow.
- `lead_dbs.coregistration_method`: `SPM`, `ANTs`, `Hybrid SPM & ANTs`, or
  `FLIRT BBR`.

The conservative default is `run_coregistration: false`. It leaves the corrected
B0 in `coregistration/anat` for manual method selection and visual QC in the
Lead-DBS UI.

### Processing and execution

- `processing.generate_optional_dwi_qc`: attempt FA, masks, and image QC in
  addition to the required corrected DWI and b0 outputs.
- `execution.force`: allow replacement of existing workflow outputs. Keep
  `false` for initial runs and routine validation.
- `execution.parallel`: process subjects concurrently when `true`.
- `execution.parallel_workers`: maximum subject worker count.
- `execution.max_concurrent_synb0`: maximum simultaneous Synb0 jobs.
- `execution.synb0_min_memory_gb`: minimum available memory required for Synb0.

Start with serial execution. Synb0 jobs are memory-intensive, so increasing
`parallel_workers` without also limiting `max_concurrent_synb0` can exhaust
system or container memory.

### Runtime

- `runtime.freesurfer_license`: FreeSurfer license file used by Synb0.
- `runtime.synb0.container_engine`: container engine name or `auto`.
- `runtime.synb0.container_image`: Synb0 container image and tag.
- `runtime.synb0.work_root`: temporary Synb0 working directory. Use a location
  with sufficient free space.

## Start MATLAB

Use MATLAB with the Lead-DBS repository available. The default environment for
this repository is the Conda environment `leaddbs`.

```matlab
repoDir = 'leaddbs_repo_path';
configPath = 'project_config_path/dwi.yaml';

cd(repoDir);
addpath(genpath(repoDir));
```

## Recommended Execution Sequence

### 1. Validate all inputs

```matlab
result = run_bids_dwi_preprocessing( ...
    'Config', configPath, ...
    'Mode', 'validate');

disp(result.summary);
```

Validation resolves the subjects and verifies all raw DWI and anatomical
inputs before expensive processing begins. It does not create image
derivatives, but it does write an immutable validation record under:

```text
study_root_path/derivatives/leaddbs/import_logs/dwi_runs/<run_id>_validate/
```

Do not proceed until every row reports `validated` and `ok`.

### 2. Inspect the execution plan

```matlab
result = run_bids_dwi_preprocessing( ...
    'Config', configPath, ...
    'Mode', 'plan');

disp(result.jobManifest);
```

Review:

- `subject` and `session`;
- `raw_dwi`, `raw_json`, `raw_bval`, and `raw_bvec`;
- `anchor_anat` and `t1_anat`;
- `dwi_volumes` and `b0_count`;
- `staged_dwi` and `b0_coreg_target`.

Plan mode writes run metadata but does not create image derivatives.

### 3. Run one subject first

Runtime options override YAML values. Use `SubjectIds` to test one subject
without editing the project YAML:

```matlab
result = run_bids_dwi_preprocessing( ...
    'Config', configPath, ...
    'Mode', 'run', ...
    'SubjectIds', {'Subject001'});

disp(result.summary);
disp(result.runRecord.runDir);
```

Do not write `sub-Subject001` in `SubjectIds`.

Review the corrected DWI, b0, gradients, QC, and coregistration target before
starting the full cohort.

### 4. Run the configured cohort

```matlab
result = run_bids_dwi_preprocessing( ...
    'Config', configPath, ...
    'Mode', 'run');

disp(result.summary);
disp(result.runRecord.runDir);
```

With `subjects.mode: auto`, this processes every discovered subject. With
`subjects.mode: explicit`, it processes only the YAML list.

## Runtime Overrides

YAML is the reproducible project configuration. MATLAB name-value arguments can
temporarily override selected settings.

Validate one subject with a different anchor:

```matlab
result = run_bids_dwi_preprocessing( ...
    'Config', configPath, ...
    'Mode', 'validate', ...
    'SubjectIds', {'Subject001'}, ...
    'AnchorModality', 'T1w');
```

Run with a fixed readout time:

```matlab
result = run_bids_dwi_preprocessing( ...
    'Config', configPath, ...
    'Mode', 'run', ...
    'SubjectIds', {'Subject001'}, ...
    'TotalReadoutTime', 0.05);
```

Run a small controlled parallel batch:

```matlab
result = run_bids_dwi_preprocessing( ...
    'Config', configPath, ...
    'Mode', 'run', ...
    'SubjectIds', {'Subject001', 'Subject002'}, ...
    'Parallel', true, ...
    'ParallelWorkers', 2, ...
    'MaxConcurrentSynb0', 1);
```

Prefer editing and versioning the YAML when a value should become a permanent
project setting.

## Outputs

Subject-level outputs are written under:

```text
study_root_path/derivatives/leaddbs/sub-subjectID/
|-- preprocessing/dwi/
|   |-- sub-subjectID_ses-preop_dwi.nii
|   |-- sub-subjectID_ses-preop_dwi.json
|   |-- sub-subjectID_ses-preop_dwi.bval
|   |-- sub-subjectID_ses-preop_dwi.bvec
|   |-- sub-subjectID_ses-preop_dwi_b0.nii
|   `-- optional FA and masks
|-- coregistration/anat/
|   `-- sub-subjectID_ses-preop_space-anchorNative_desc-preproc_B0.nii
`-- qc/
    `-- dwi_registration_synb0_fakeb0/
```

Exact corrected DWI results and correction QC are produced by the existing
Synb0/topup/eddy backend. The staged B0 includes metadata identifying it for
coregistration and normalization.

## Run Records

Every `validate`, `plan`, and `run` invocation writes a unique record:

```text
study_root_path/derivatives/leaddbs/import_logs/dwi_runs/<run_id>/
|-- config_source.yaml
|-- config_resolved.json
|-- job_manifest.csv
|-- status.csv
`-- subjects/
    `-- subjectID_dwi_preprocessing_qc.json
```

- `config_source.yaml`: exact source YAML used for the invocation.
- `config_resolved.json`: YAML plus runtime overrides and defaults.
- `job_manifest.csv`: resolved input and output paths before processing.
- `status.csv`: final subject status and compact error messages.
- `subjects/*.json`: one machine-readable status record per subject.

Use `result.runRecord.runDir` to locate the record created by the current call.

## Lead-DBS UI Follow-up

When `lead_dbs.run_coregistration` is `false`, a successful processing status
can remain `pending_ui_coregistration`. This is expected.

In Lead-DBS:

1. open the subject;
2. run or review coregistration for the staged B0;
3. select an appropriate registration method;
4. inspect alignment against the anchorNative anatomy;
5. approve only after visual QC.

Manual UI QC remains a separate operator step and is not automated by this
workflow.

## Safety Rules

- Keep `execution.force: false` until existing outputs have been reviewed.
- Run `validate`, then `plan`, then one-subject `run` before a cohort run.
- Do not replace raw DWI after preprocessing without invalidating dependent
  corrected DWI, B0, coregistration, and QC outputs.
- Do not assume phase-encoding direction or readout time from another scanner
  protocol.
- Do not run multiple Synb0 containers concurrently without sufficient memory
  and disk space.
- Preserve the run record for every production execution.

## Common Errors

### No subjects discovered

Check that each subject has a DWI NIfTI under:

```text
study_root_path/rawdata/sub-subjectID/ses-<session>/dwi/
```

Also verify that `project.session` omits `ses-`.

### Ambiguous raw DWI

The subject DWI directory contains more than one `*_dwi.nii` or
`*_dwi.nii.gz`. The public workflow intentionally refuses to choose silently.
Keep one intended DWI four-file set in that directory.

### Missing sidecar or gradient mismatch

Ensure the NIfTI, JSON, bval, and bvec use the same basename and that gradient
counts match the fourth NIfTI dimension.

### Missing T1w or anchor

Synb0 requires anchorNative T1w. The configured T1w or T2w coregistration anchor
must also be present under the subject Lead-DBS `coregistration/anat` directory.

### Invalid subject or session label

Use `Subject001`, not `sub-Subject001`, and `preop`, not `ses-preop`.

### Existing output

The workflow stops when protected outputs exist and `force` is false. Determine
whether the existing run is complete before considering replacement. Do not
enable `force` merely to bypass an unexplained conflict.
