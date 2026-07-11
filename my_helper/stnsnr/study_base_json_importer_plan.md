# STNSNr Study Base JSON Importer Goal

## Purpose

Define and implement the STNSNr-specific, read-only importer that converts the
current clinical workbook, stimulation workbook, and Lead-DBS electrode
reconstructions into one validated `study_base.json`. This JSON is the unique
data input for later VTA/E-field generation and dual-frequency sweet/sour spot
model execution. Scientific and workflow parameters remain outside this data
contract in `vta_model.yaml`, `spot_model.yaml`, and `workflow.yaml`.

## Workspace

```text
/Users/mojackhu/Github/leaddbs
```

## Parent Goal

```text
/Users/mojackhu/Github/leaddbs/my_helper/stnsnr/four_model_yaml_core_refactor_plan.md
```

## Authoritative Inputs

```text
clinical workbook:
  /Volumes/VAL/STNSNr/summary/cohort/subj/subject_effect_origin.xlsx

stimulation workbook:
  /Volumes/VAL/STNSNr/summary/cohort/subj/followup_stimulation.xlsx
  sheet: Contact Parameters

Lead-DBS subject root:
  /Volumes/VAL/STNSNr/derivatives/leaddbs

repository asset root:
  /Users/mojackhu/Github/leaddbs
```

## Output

```text
/Volumes/VAL/STNSNr/summary/cohort/subj/study_base.json
```

## Current Branch

```text
stnvop
```

## Baseline Commit

```text
61e14e1d8
```

## Status

```text
design_documented
implementation_not_started
study_base_json_not_generated
current_source_workbooks_read_only
current_model_outputs_unchanged
```

## Last Updated

```text
2026-07-11
```

## Goal And Success Criteria

The importer is complete only when it:

1. reads the two configured source workbooks without modifying them;
2. includes every clinical `Feature` as an independent, engineering-equivalent
   scale with `subscale_id = total`;
3. maps every clinical observation to an explicit subject/phase/program path;
4. emits explicit `not_assessed` observations for scale/program combinations
   that are absent from the immediate source conditions;
5. converts all stimulation rows into explicit component, frequency-group,
   source, contact, polarity, and fraction records;
6. extracts bilateral electrode model and contact count from each Lead-DBS
   reconstruction;
7. validates the bilateral contiguous zero-based contact convention;
8. records only source data needed by VTA and the four spot models;
9. excludes E-field/VTA paths and generated model artifacts;
10. writes one schema-valid JSON atomically whose data content, identifiers,
    ordering, and serialization are deterministic apart from the documented
    real-time `provenance.created_at` value; and
11. fails without replacing the previous output if any required source row is
    ambiguous, duplicated, invalid, or unmappable.

All 28 current clinical `Feature` values are equivalent for importer execution.
No production branch may recognize MDS-UPDRS total, axial, or any other scale
name.

## Scope Boundary

In scope:

```text
study JSON contract and JSON Schema
STNSNr workbook-to-study mapping
Lead-DBS reconstruction metadata extraction
program/component/source/contact conversion
explicit not_assessed materialization
input and output validation
atomic study_base.json generation
tests and a real-data acceptance audit
```

Out of scope:

```text
VTA/E-field calculation
direct-voxel or normative-fiber model execution
tau/Coverage or source resolver implementation
formal resampling, jitter, or OSS execution
GUI work
clinical date reconstruction
E-field/VTA file indexing
cross-run hash-based cache identity
modification of source workbooks or existing model outputs
```

## Data And Configuration Boundary

```text
study_base.json
  unique project data input

vta_model.yaml
  VTA/FEM scientific parameters

spot_model.yaml
  direct-voxel and normative-fiber scientific parameters

workflow.yaml
  selection, execution, resume, force, and worker policy
```

`study_base.json` must not contain model thresholds, resolver policy,
permutation/bootstrap counts, worker settings, or connectome role assignments.
The YAML profiles must not contain clinical values, patient programming rows,
or patient-specific reconstruction paths.

## Target JSON Contract

The following is documentation notation. The `#` comments are English field
descriptions and must not appear in the generated strict JSON.

```text
{
  "schema_version": "dual_frequency_study_v1", # Data contract version

  "study": {
    "study_id": "stnsnr_frequency_addon",      # Stable study identifier
    "study_label": "STNSNr frequency add-on",  # Human-readable study label
    "data_version": "1",                      # Importer contract version

    "frequency_components": [                   # Dual-frequency component definitions
      {
        "component_id": "frequency_1_reference", # Reference component identifier
        "label": "HF"                           # STNSNr display label
      },
      {
        "component_id": "frequency_2_addon",    # Add-on component identifier
        "label": "ULF"                          # STNSNr display label
      }
    ],

    "scale_definitions": [                      # Independent clinical scale definitions
      {
        "scale_id": null,                       # Deterministic ID derived from Feature
        "label": null,                          # Exact source Feature label
        "value_type": "integer",               # Current source values are integers
        "unit": "score",                       # Raw clinical score unit
        "direction": "unknown",                # No direction is inferred by the importer
        "subscales": [
          {
            "subscale_id": "total",            # Uniform child identifier for every Feature
            "label": "Total"                   # Uniform human-readable child label
          }
        ]
      }
    ],

    "spot_model_sources": {                     # Study-level sources shared by all four models
      "canonical_space": "MNI152NLin2009bAsym", # Canonical model space

      "hemisphere_mapping": {
        "canonical_hemisphere": "R",           # Right-canonical model representation
        "left_to_right_transform": {
          "path": "/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/fliplr/Composite.nii.gz" # Left-to-right transform
        }
      },

      "reference_images": [                    # Canonical multi-modal references
        {
          "image_id": "canonical_t1w",         # Stable reference image ID
          "modality": "T1w",                   # Imaging modality
          "label": "MNI152NLin2009bAsym T1w", # Human-readable image label
          "path": "/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/t1.nii" # Source NIfTI
        },
        {
          "image_id": "canonical_t2w",         # Stable reference image ID
          "modality": "T2w",                   # Imaging modality
          "label": "MNI152NLin2009bAsym T2w", # Human-readable image label
          "path": "/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/t2.nii" # Source NIfTI
        }
      ],

      "brainmask": {
        "brainmask_id": "mni152nlin2009basym_brainmask", # Stable mask ID
        "space": "MNI152NLin2009bAsym",       # Mask coordinate space
        "path": "/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/brainmask.nii.gz" # Source mask
      },

      "connectomes": [                         # Normative streamline sources
        {
          "connectome_id": null,               # Stable connectome ID
          "label": null,                       # Human-readable connectome name
          "space": "MNI152NLin2009bAsym",     # Connectome coordinate space
          "modality": "diffusion",            # Connectome modality
          "representation": "streamlines",    # Required representation
          "streamlines": {
            "format": "leaddbs_data_mat_v7_3", # Lead-DBS HDF5 MAT adapter
            "path": null                       # Connectome data.mat source
          },
          "metadata": {
            "path": null                       # Optional dataset_info.json source
          }
        }
      ]
    },

    "subjects": [                              # Imported study subjects
      {
        "subject_id": null,                    # Stable clinical subject ID
        "subject_label": null,                 # NameEn display label

        "subject_sources": {
          "leaddbs_subject_dir": null,          # Lead-DBS subject directory
          "electrode_reconstruction": {
            "path": null                       # desc-reconstruction.mat source
          }
        },

        "contact_numbering": {
          "convention": "bilateral_contiguous_zero_based", # Source contact convention
          "electrode_order": ["lead-L", "lead-R"] # Global contact order
        },

        "electrodes": [                        # Bilateral hardware definitions
          {
            "electrode_id": null,              # lead-L or lead-R
            "hemisphere": null,                # L or R
            "electrode_model": null,           # Reconstruction electrode model
            "contact_count": null,             # Reconstruction coordinate count
            "reconstruction_lead_id": null      # Lead-DBS side index: R=1, L=2
          }
        ],

        "phases": [                            # T0 through T3 study time groups
          {
            "phase_id": null,                  # Stable phase ID
            "phase_label": null,               # Human-readable phase label
            "date": {
              "window_start_date": null,       # Unknown current phase start date
              "window_end_date": null          # Unknown current phase end date
            },

            "programs": [                      # Assessment and stimulation conditions
              {
                "program_id": null,            # Phase-local numeric program ID
                "program_label": null,         # Human-readable program label
                "condition_role": null,        # none, reference_only, or combined
                "stimulation_state": null,     # none or active
                "assessment_order": null,      # Within-phase assessment order

                "exposure": {
                  "duration_label": null,       # preoperative, immediate, or 3m
                  "stimulation_start_date": null, # Unknown current start date
                  "assessment_date": null,     # Unknown current assessment date
                  "exposure_days": null         # Derived only when both dates exist
                },

                "clinical_observations": [     # Complete scale catalog for this program
                  {
                    "observation_id": null,     # Globally unique observation ID
                    "scale_id": null,           # Reference to scale_definitions
                    "subscale_id": "total",    # Uniform child identifier
                    "value": null,              # Raw score or null when unavailable
                    "status": null              # observed or not_assessed in current import
                  }
                ],

                "electrode_programs": [        # Per-electrode stimulation settings
                  {
                    "electrode_id": null,       # Reference to subject electrodes
                    "frequency_groups": [
                      {
                        "frequency_group_id": null, # Stable group within electrode/program
                        "frequency_hz": null,   # Group frequency in Hz
                        "delivery_mode": null,  # continuous or alternating
                        "sources": [
                          {
                            "source_id": null,  # Stable source within group
                            "source_label": null, # Source Target label
                            "component_id": null, # Reference or add-on component
                            "control_mode": "voltage", # Current workbook control mode
                            "amplitude": null,  # Voltage amplitude in V
                            "pulse_width_us": null, # Pulse width in microseconds
                            "contacts": [
                              {
                                "contact": null, # Global zero-based contact or case
                                "polarity": null, # cathode or anode
                                "fraction": 1.0   # Within-polarity allocation
                              }
                            ]
                          }
                        ]
                      }
                    ]
                  }
                ]
              }
            ]
          }
        ]
      }
    ],

    "provenance": {
      "created_at": null,                     # Real UTC import completion timestamp
      "importer": {
        "name": "build_stnsnr_study_base",    # Importer identity
        "version": "1",                       # Importer contract version
        "code_commit": null                    # Current repository commit
      },
      "source_files": [                       # Direct source files only
        {
          "role": null,                       # clinical or programming
          "path": null                        # Absolute source path
        }
      ],
      "notes": null                           # Optional import notes
    }
  }
}
```

Explicitly excluded keys:

```text
artifact_index
sha256
size_bytes
shape
dtype
anatomical_images
subject transform chains
E-field paths
VTA paths
generated fiber_ids.npy paths
model thresholds or connectome roles
```

## Clinical Mapping Contract

The source workbook is a complete long table with columns:

```text
ID
Feature
Condition
Value
Group
```

Current audited source facts:

```text
subjects: 16
distinct Features: 28
source observation rows: 1408
duplicate ID/Feature/Condition keys: 0
missing source cells: 0
```

Every exact source `Feature` becomes one independent scale:

```text
scale_id = deterministic sanitized Feature
label = exact source Feature
subscale_id = total
value_type = integer
unit = score
direction = unknown
```

Sanitization lowercases the NFKC-normalized label, replaces non-alphanumeric
runs with `_`, trims `_`, and rejects collisions. The importer does not repair
source spelling, merge related Features, or recognize special scale names.

Condition mapping is fixed and explicit:

| Source Group | Source Condition | Phase | Program | Role | Exposure |
|---|---|---|---:|---|---|
| A | `Pre-op` | T0 | 0 | `none` | `preoperative` |
| B | `STN (immediate)` | T1 | 1 | `reference_only` | `immediate` |
| D | `STN (3 m)` | T2 | 1 | `reference_only` | `3m` |
| C | `STN+SNr (immediate)` | T2 | 2 | `combined` | `immediate` |
| E | `STN+SNr (3 m)` | T3 | 2 | `combined` | `3m` |

The `Group` column is validation evidence only. It is not emitted as model
semantics. Any Condition/Group mismatch is fatal.

Every program emits all 28 scales in the same deterministic scale order:

```text
source row exists:
  status = observed
  value = source integer

source row absent for that condition:
  status = not_assessed
  value = null
```

Expected output counts:

```text
program-observation slots per subject: 5 * 28 = 140
total program-observation slots: 16 * 140 = 2240
observed: 1408
explicit not_assessed: 832
```

The immediate conditions currently contain only MDS-UPDRS III total and axial
Feature rows. This source fact does not grant those scales a different importer
or model status.

## Programming Mapping Contract

Required source columns:

```text
ID
NameEn
Phase
Protocol
Contact
Target
Side
Voltage
PulseWidth
Frequency
StimulationPattern
AlternatingGroup
```

Source phase/protocol mapping:

| Source Phase | Source Protocol | Target Phase | Program |
|---|---|---|---:|
| `immediate` | `STN` | T1 | 1 |
| `3m` | `STN` | T2 | 1 |
| `immediate` | `STN+SNr` | T2 | 2 |
| `3m` | `STN+SNr` | T3 | 2 |

Component mapping is STNSNr importer behavior only:

```text
Target = STN -> component_id = frequency_1_reference
Target = SNr -> component_id = frequency_2_addon
```

Program role validation:

```text
none:
  stimulation_state = none
  electrode_programs = []

reference_only:
  stimulation_state = active
  every source component_id = frequency_1_reference

combined:
  stimulation_state = active
  at least one frequency_1_reference source
  at least one frequency_2_addon source
```

Contact conversion preserves the workbook convention exactly:

```text
bilateral contiguous
left electrode first
zero-based
case represented as the string "case"
```

Each workbook stimulation row becomes one source with:

```text
control_mode = voltage
amplitude = Voltage
pulse_width_us = PulseWidth
one cathode contact with fraction 1.0
one case anode with fraction 1.0
source_label = Target
```

Frequency grouping:

```text
alternating rows:
  AlternatingGroup is required
  rows sharing subject/phase/program/side/AlternatingGroup form one group
  all rows in the group must share Frequency

continuous rows:
  rows sharing subject/phase/program/side/Frequency form one group

source ordering:
  ascending global Contact, then exact source row order
```

Every one of the current 194 source stimulation rows must appear exactly once
in the generated program tree.

## Electrode Reconstruction Contract

For each clinical subject ID:

```text
subject directory:
  <leaddbs_root>/sub-<ID>

reconstruction:
  <subject_dir>/reconstruction/sub-<ID>_desc-reconstruction.mat
```

The Python importer reads MATLAB v5 reconstruction structures with
`scipy.io.loadmat(..., simplify_cells=True)`.

Lead-DBS side identity is fixed:

```text
reconstruction side index 1 = R
reconstruction side index 2 = L
JSON electrode_order = [lead-L, lead-R]
```

For each side:

```text
electrode_model = reco.props[side].elmodel
contact_count = row count of reco.mni.coords_mm[side]
```

The model and count are both required. Current expected model/count pairs are:

```text
Medtronic 3387: 4
SceneRay SR1200: 4
SceneRay SR1202: 8
```

The importer must reject missing reconstructions, missing bilateral coordinates,
different coordinate counts across native/MNI representations, unsupported
contact ranges, or programming contacts inconsistent with the extracted count.

## Study-Level Source Contract

The generated JSON records these current repository inputs directly:

```text
canonical space:
  MNI152NLin2009bAsym

T1w:
  /Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/t1.nii

T2w:
  /Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/t2.nii

brainmask:
  /Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/brainmask.nii.gz

left-to-right transform:
  /Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/fliplr/Composite.nii.gz

PPMI:
  /Users/mojackhu/Github/leaddbs/connectomes/dMRI/PPMI 85 (Ewert 2017)/data.mat

MGH:
  /Users/mojackhu/Github/leaddbs/connectomes/dMRI/MGH-USC HCP 32 (Horn 2017)/data.mat

dTOR:
  /Users/mojackhu/Github/leaddbs/connectomes/dMRI/dTOR-985 Full (Elias 2024)/data.mat
```

Connectome fiber identity remains an adapter rule, not input JSON:

```text
/fibers = streamline coordinate storage
/idx = fiber lengths and order
derived fiber ID = 1..n_fibers
```

## Planned File Layout

Documentation and schema:

```text
my_helper/stnsnr/study_base_json_importer_plan.md
my_helper/stnsnr/study_base.schema.json
```

Requested project-specific executable:

```text
my_helper/stnsnr/build_stnsnr_study_base.py
```

Reusable STNSNr importer implementation and tests remain outside the generic
runtime core:

```text
my_helper/fiber/projects/stnsnr/importer/__init__.py
my_helper/fiber/projects/stnsnr/importer/study_base.py
my_helper/fiber/projects/stnsnr/importer/tests/__init__.py
my_helper/fiber/projects/stnsnr/importer/tests/test_study_base.py
```

No module under the future generic dual-frequency core may import this STNSNr
project package.

## CLI Contract

```bash
conda run -n leaddbs python \
  my_helper/stnsnr/build_stnsnr_study_base.py \
  --clinical-workbook /Volumes/VAL/STNSNr/summary/cohort/subj/subject_effect_origin.xlsx \
  --stimulation-workbook /Volumes/VAL/STNSNr/summary/cohort/subj/followup_stimulation.xlsx \
  --stimulation-sheet "Contact Parameters" \
  --leaddbs-root /Volumes/VAL/STNSNr/derivatives/leaddbs \
  --asset-root /Users/mojackhu/Github/leaddbs \
  --output /Volumes/VAL/STNSNr/summary/cohort/subj/study_base.json
```

All paths have these STNSNr defaults but remain overrideable. Additional CLI
flags:

```text
--schema <path>       explicit JSON Schema override
--validate-only       build and validate in memory without writing output
--force               replace an existing output only after full validation
```

Without `--force`, an existing output is not overwritten. The final write uses
a same-directory temporary file followed by atomic replacement.

## Validation And Failure Policy

Fatal input failures include:

```text
missing required workbook columns
clinical/stimulation subject-set mismatch
duplicate clinical ID/Feature/Condition keys
unknown clinical Condition or Group mismatch
non-finite or non-integer current clinical Value
scale-ID sanitization collision
missing or duplicate subject reconstruction
missing bilateral reconstruction props or MNI coordinates
electrode model/contact-count inconsistency
program contact outside the electrode global range
unknown Target, Side, Protocol, Phase, or StimulationPattern
alternating row without AlternatingGroup
mixed frequencies inside one alternating group
reference_only program containing an add-on component
combined program missing either component
missing study-level source file
schema validation failure
```

Any fatal error prevents output replacement. Errors are reported with subject,
source file, sheet, and source-row context.

## Implementation Sequence

### Stage 0: Clean Baseline

1. Require branch `stnvop` and a clean worktree.
2. Record the starting commit.
3. Confirm all authoritative input paths are readable.
4. Do not edit or normalize either workbook.

### Stage 1: Contract And Schema

1. Add `study_base.schema.json` with English `description` fields.
2. Encode all required keys, enums, ID uniqueness checks possible in JSON
   Schema, and structural `if/then` role constraints.
3. Keep cross-record semantic checks in Python where JSON Schema cannot express
   them reliably.
4. Add schema fixtures for a minimal no-stimulation program, a reference-only
   program, and a combined program.

### Stage 2: Importer Unit Implementation

1. Write failing tests for clinical condition mapping and 28-scale equality.
2. Implement deterministic scale catalog creation.
3. Write failing tests for explicit immediate `not_assessed` materialization.
4. Implement the complete 5-program observation grid.
5. Write failing tests for 4-contact and 8-contact reconstruction extraction.
6. Implement bilateral model/count extraction and contact validation.
7. Write failing tests for continuous and alternating programming groups.
8. Implement source/component/contact conversion.
9. Write failing tests for all role closure and failure paths.
10. Implement semantic validation and deterministic ordering.
11. Inject the UTC clock used for `provenance.created_at` so tests can use a
    fixed instant and assert byte-for-byte deterministic serialization.

### Stage 3: CLI And Atomic Output

1. Add the requested `my_helper/stnsnr` executable.
2. Implement explicit path arguments and STNSNr defaults.
3. Implement `--validate-only` and `--force`.
4. Validate before writing.
5. Write formatted UTF-8 JSON with deterministic key and list ordering. The
   only production-run volatile field is the real UTC
   `provenance.created_at`; fixed-clock tests must be byte deterministic.
6. Use atomic output replacement.

### Stage 4: Real-Data Acceptance

1. Run `--validate-only` against the actual source data.
2. Verify 16 subjects, 28 scales, 2240 observation slots, 1408 observed, 832
   not assessed, and 194 stimulation sources.
3. Verify all source clinical and stimulation rows map exactly once.
4. Verify expected 4-contact and 8-contact electrode models.
5. Verify every referenced study-level and subject-level path exists.
6. Scan the JSON for forbidden E-field/VTA/generated-output keys.
7. Generate `study_base.json` only after every check passes.
8. Re-read and revalidate the written JSON.

### Stage 5: VTA Handoff Readiness

1. Build a read-only adapter test that converts one reference-only and one
   combined program into the existing MATLAB stimulation-spec boundary.
2. Verify global zero-based contacts convert to Lead-DBS local one-based
   contacts only at the adapter boundary.
3. Verify component-specific source selection can request reference and add-on
   VTA tasks without using STN/SNr labels.
4. Do not run VTA or spot models in this importer goal.

## Test Plan

Unit tests run in the `leaddbs` Conda environment:

```bash
env PYTHONPATH=/Users/mojackhu/Github/leaddbs/my_helper/fiber \
  /opt/anaconda3/envs/leaddbs/bin/python -m unittest discover \
  -s my_helper/fiber/projects/stnsnr/importer/tests \
  -p 'test_*.py' -v
```

Contract and real-data checks:

```bash
conda run -n leaddbs python \
  my_helper/stnsnr/build_stnsnr_study_base.py --validate-only

conda run -n leaddbs python \
  my_helper/stnsnr/build_stnsnr_study_base.py --force

python -m json.tool \
  /Volumes/VAL/STNSNr/summary/cohort/subj/study_base.json >/dev/null

rg -n 'efield|e-field|binary_vta|"vta"|fiber_ids\.npy|sha256|size_bytes|artifact_index' \
  /Volumes/VAL/STNSNr/summary/cohort/subj/study_base.json

git diff --check
```

The forbidden-key scan must return no output. No VTA generation, model runner,
formal resampling, OSS, or output refresh runs as part of this goal.

## Acceptance Contract

Implementation is accepted only when:

```text
the two source workbooks remain unchanged
study_base.json is the only structured project data input
all 16 source subjects are present exactly once
all 28 Features are independent, equivalent scales
all five condition streams are represented for every scale
not_assessed rows are explicit rather than inferred downstream
all 1408 source clinical rows map exactly once
all 194 source stimulation rows map exactly once
electrode models and contact counts come from reconstruction data
all contacts preserve bilateral contiguous zero-based source numbering
program and source roles are explicit and name-independent downstream
no E-field/VTA or generated fiber-ID path appears in the input JSON
schema and semantic validation pass
all data content, identifiers, list/key ordering, and serialization are
deterministic; only the real UTC provenance.created_at varies between
production imports
fixed-clock tests produce byte-for-byte identical output
output replacement is atomic
```

## Deferred Work

```text
generic study-bundle loader
Python-to-MATLAB VTA execution adapter
VTA/E-field generation from study_base.json
spot_model.yaml implementation
four-model DAG execution from the generated study data
GUI authoring and validation
real date population and exposure_days calculation
content hashing and cross-run cache identity
```

## Assumptions

1. The current 16-subject clinical and stimulation ID sets remain identical.
2. `subject_effect_origin.xlsx` remains authoritative for clinical values.
3. `followup_stimulation.xlsx` `Contact Parameters` remains authoritative for
   programming rows.
4. Reconstruction side order follows Lead-DBS `R=1`, `L=2`.
5. Current source control mode is voltage with case anode.
6. Dates remain null until a separate authoritative date source is approved.
7. Scale direction remains `unknown`; the importer does not infer clinical
   improvement direction.
8. Existing E-field/VTA and model outputs remain read-only and are not imported.
