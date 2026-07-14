# MRtrix Seed-Target YAML Batch CLI Design

## Status

```text
design_approved
implementation_not_started
existing_outputs_unchanged
```

## Purpose

Create an independent YAML-only command-line module for subject-specific DWI
seed-target tractography. Python owns strict configuration, validation,
identity, scheduling, state, and publication. A Lead-DBS MATLAB backend prepares
each subject's DWI/FOD inputs and transforms atlas ROIs into DWI space. Python
then schedules MRtrix `tckgen` processes globally across prepared subjects.

This module is separate from both:

- `core/seed_target_connectivity`, which measures intersections in an existing
  normative connectome such as dTOR; and
- the full Fiber/VTA workflow, which produces VTA, e-field, density, display,
  and reporting artifacts.

The only scientific result published by this module is the MRtrix `.tck`
tractogram for each explicitly configured seed-target pair.

## Scope

The implementation must provide:

- one strict YAML describing multiple Lead-DBS subjects;
- one shared atlas and shared tractography settings;
- separately listed left, right, or midline seed ROIs;
- a target list nested under each individual seed;
- an explicit side and explicit NIfTI path for every seed and target;
- subject input auto-discovery with optional explicit path overrides;
- bounded parallel subject preparation and globally scheduled MRtrix bundles;
- content-identified reuse without public `force` or `resume` modes;
- optional MRtrix `-stop`, disabled by default; and
- `validate`, `run`, and `status` commands.

The implementation must not produce density NIfTI files, CSV tables, VTK,
Lead-DBS display MAT files, figures, VTA intersection results, e-field results,
SIFT/SIFT2 results, or connectivity rankings.

ACT and whole-brain-then-filter tracking are outside this design. The fixed
tracking algorithm is pairwise target-conditioned MRtrix iFOD2.

## Selected Architecture

### Python Control Plane

Add a Python package under:

```text
my_helper/fiber/core/mrtrix_seed_target/
```

and an executable CLI under:

```text
my_helper/fiber/pipelines/mrtrix-seed-target
```

Python is responsible for:

- parsing YAML with duplicate-key detection and rejecting unknown fields;
- resolving paths relative to the YAML file;
- validating the shared atlas, nested seed-target definitions, subjects, and
  execution budget;
- discovering standard Lead-DBS subject inputs and applying explicit
  overrides;
- hashing scientific inputs, code, and tool versions;
- launching one preparation-only MATLAB process per active subject;
- reading the resolved preparation result from MATLAB;
- globally scheduling external MRtrix `tckgen` commands;
- validating staged TCK files;
- recording state under each subject's `work` directory; and
- transactionally publishing complete subject results.

The default Python environment is Conda `leaddbs`.

### MATLAB Preparation Backend

Add a standalone MATLAB entry point:

```text
mh_fiber_prepare_mrtrix_seed_target_subject.m
```

One MATLAB process prepares exactly one subject. It must:

- initialize Lead-DBS paths once;
- resolve or validate the subject's DWI inputs and transform chain;
- create or reuse `dwi.mif`, brain/tracking masks, response, and WM FOD;
- transform every unique referenced MNI ROI to the subject's DWI grid using
  label-preserving interpolation;
- deduplicate ROI preparation by resolved source path and source hash;
- reject an empty DWI-space seed or target mask; and
- write a machine-readable prepared-subject JSON for Python.

MATLAB does not launch `parpool` and does not run bundle-level `tckgen` jobs.
This avoids the memory and startup cost of nested MATLAB process and worker
pools. Existing MATLAB/Lead-DBS ROI transformation behavior remains the
scientific preparation backend.

The legacy `mh_fiber_run_seed_target.m` entry point remains supported and must
not change behavior as a side effect of this work. Shared helpers may be
extracted only when both entry points retain their tested contracts.

### Global MRtrix Scheduler

As soon as a subject has been prepared, Python makes its unresolved bundles
eligible for a single global work queue. Scheduling is dynamic rather than a
fixed worker allocation:

- `subject_workers` caps concurrently active subjects;
- `bundle_workers_per_subject` caps concurrent bundles reading one subject's
  FOD;
- `cpu_budget` is a hard global CPU-token ceiling;
- a preparation consumes `preparation_threads_per_subject` CPU tokens;
- a bundle consumes `mrtrix_threads_per_bundle` CPU tokens; and
- `memory_budget_gb` pauses new dispatch when sampled aggregate child-process
  RSS reaches 80 percent of the configured ceiling.

Running tasks are not killed merely because observed RSS crosses the memory
dispatch threshold. Their completion releases tokens. The final status reports
the observed aggregate peak RSS.

The default is one MRtrix thread per bundle. This maximizes bundle-level
parallelism and gives the strongest repeatability when `MRTRIX_RNG_SEED` is
fixed. A configured value greater than one is permitted but validation must
warn that regenerated probabilistic streamlines may not be byte-reproducible.

## YAML Contract

The public schema is version 1:

```yaml
schema_version: 1

atlas:
  name: STNSNr-connected regions
  space: MNI152NLin2009bAsym
  root: /path/to/STNSNr-connected regions

  seeds:
    - id: STNSNrplus
      side: lh
      path: /path/to/STNSNr-connected regions/lh/STNSNrplus.nii.gz
      targets:
        - id: GPi
          side: lh
          path: /path/to/STNSNr-connected regions/lh/GPi.nii.gz
        - id: PPN
          side: lh
          path: /path/to/STNSNr-connected regions/lh/PPN.nii.gz
        - id: GPi
          side: rh
          path: /path/to/STNSNr-connected regions/rh/GPi.nii.gz

    - id: STNSNrplus
      side: rh
      path: /path/to/STNSNr-connected regions/rh/STNSNrplus.nii.gz
      targets:
        - id: GPi
          side: rh
          path: /path/to/STNSNr-connected regions/rh/GPi.nii.gz
        - id: PPN
          side: rh
          path: /path/to/STNSNr-connected regions/rh/PPN.nii.gz

subjects:
  - id: sub-001
    subject_dir: /path/to/derivatives/leaddbs/sub-001

  - id: sub-002
    subject_dir: /path/to/derivatives/leaddbs/sub-002
    paths:
      dwi: /optional/override/dwi.nii.gz
      bvec: /optional/override/dwi.bvec
      bval: /optional/override/dwi.bval

tracking:
  requested_streamlines: 5000
  max_seed_attempts: 500000
  fod_cutoff: 0.06
  min_length_mm: 10
  max_length_mm: 250
  stop_at_target: false
  random_seed: 1

execution:
  subject_workers: 2
  preparation_threads_per_subject: 4
  bundle_workers_per_subject: 8
  mrtrix_threads_per_bundle: 1
  cpu_budget: 16
  memory_budget_gb: 48
  matlab_executable: matlab
  mrtrix_path_prefix: /usr/local/bin
```

The required top-level fields are `schema_version`, `atlas`, `subjects`,
`tracking`, and `execution`. Unknown fields at every level are rejected.
Relative filesystem paths resolve against the YAML file's directory.

All atlas, seed, target, subject `id`, `subject_dir`, `side`, and ROI `path`
fields shown above are required. A subject `paths` object is optional.

Tracking fields may be omitted individually. Their defaults are
`requested_streamlines=5000`, `max_seed_attempts=500000`,
`fod_cutoff=0.06`, `min_length_mm=10`, `max_length_mm=250`,
`stop_at_target=false`, and `random_seed=1`. The complete resolved values are
always written to each subject's `resolved_config.json`.

The resource fields `subject_workers`, `preparation_threads_per_subject`,
`bundle_workers_per_subject`, `cpu_budget`, and `memory_budget_gb` are required
positive values. `mrtrix_threads_per_bundle` defaults to `1`.
`matlab_executable` defaults to `matlab`; `mrtrix_path_prefix` defaults to an
empty string and then relies on `PATH`. Validation requires every single task's
CPU-token request to fit within `cpu_budget`; the global scheduler enforces the
aggregate ceiling dynamically.

### Atlas and Pair Rules

- `atlas.space` must be `MNI152NLin2009bAsym` in schema version 1.
- Every resolved seed and target path must be inside the resolved
  `atlas.root`.
- Seeds are listed separately by side. Their canonical identity is
  `<side>/<id>`.
- Every seed owns its own nonempty `targets` list. There is no global target
  list and no implicit Cartesian expansion.
- Every target explicitly declares `side`; it never inherits side implicitly.
- Supported side values are `lh`, `rh`, and `midline`.
- A target nested under a seed is one exact tracking pair. A cross-side target
  is expressed directly by its explicit side and needs no separate exception
  object.
- Seed and target IDs must be safe single path components. A canonical seed
  must be unique, and a canonical target must be unique within its parent seed.
- ROI files must be finite, nonempty, three-dimensional binary NIfTI images.
- Resolved symlink targets, not merely lexical input paths, are used for the
  common-root check.

### Subject Discovery and Overrides

Every subject has a unique `id` and a Lead-DBS `subject_dir`. Standard discovery
uses the existing Lead-DBS/BIDS conventions for:

- DWI NIfTI;
- bvec and bval;
- b0 reference;
- DWI brain mask;
- DWI tracking mask;
- anchorNative reference;
- MNI-to-anchorNative normalization; and
- anchorNative-to-DWI transform.

The optional `paths` object supports the exact keys:

```text
dwi
bvec
bval
b0
brain_mask
tracking_mask
anchor_native_reference
mni_to_anchor_transform
anchor_to_dwi_transform
```

An override replaces discovery only for that named input. All resolved files
are validated before subject preparation begins.

### Tracking Semantics

For every configured pair, the command contract is equivalent to:

```text
tckgen WM_FOD OUTPUT \
  -algorithm iFOD2 \
  -seed_image SEED_MASK \
  -include TARGET_MASK \
  -mask TRACKING_MASK \
  -select REQUESTED_STREAMLINES \
  -seeds MAX_SEED_ATTEMPTS \
  -cutoff FOD_CUTOFF \
  -minlength MIN_LENGTH_MM \
  -maxlength MAX_LENGTH_MM \
  -nthreads MRTRIX_THREADS_PER_BUNDLE
```

`-stop` is appended only when `tracking.stop_at_target` is `true`. Its default
is `false`. Without `-stop`, an accepted streamline must traverse the target
but may continue beyond it. With `-stop`, propagation is stopped after all
include regions have been traversed. Neither behavior proves biological axon
termination or synaptic connectivity.

The source response and FOD methods remain `dwi2response tournier` and
`dwi2fod csd`, matching the current pairwise backend.

`tracking.random_seed` is a positive base integer. The per-bundle MRtrix seed is
derived deterministically as:

```text
1 + ((base_random_seed + first_64_bits(SHA256(bundle_identity))) mod (2^31 - 1))
```

and is supplied through the `MRTRIX_RNG_SEED` environment variable.

## CLI Contract

The executable exposes exactly these commands:

```text
mrtrix-seed-target validate --config CONFIG
mrtrix-seed-target run --config CONFIG
mrtrix-seed-target status --config CONFIG
```

All scientific and execution parameters come from YAML. The CLI does not offer
ROI, subject, tracking, output, `force`, or `resume` overrides.

- `validate` is read-only. It performs strict Python validation and a bounded
  MATLAB preflight for Lead-DBS transform resolution. It does not generate FOD
  or tractograms.
- `run` validates the complete batch before starting subject preparation,
  prepares unresolved subjects, globally schedules unresolved bundles, and
  publishes complete subject transactions.
- `status` reads subject state and invokes `tckinfo` for existing final TCK
  files. It does not start MATLAB.

Configuration errors return a distinct nonzero exit status before execution.
Execution continues across independent subjects and reports a nonzero final
status if any subject fails.

## Subject Directory Contract

Each subject writes under:

```text
derivatives/leaddbs/sub-xxx/connectomics/dMRI/mrtrix_seed_target/
├── work/
│   ├── resolved_config.json
│   ├── prepared_subject.json
│   ├── state.json
│   ├── dwi.mif
│   ├── brainmask.mif
│   ├── trackingmask.mif
│   ├── response_wm.txt
│   ├── wm_fod.mif
│   ├── rois/
│   ├── logs/
│   ├── staging/
│   └── rollback/
└── tractograms/
    └── <seed_side>/
        └── <seed_id>/
            └── <target_side>/
                └── <target_id>.tck
```

The `work` directory is intentionally visible and contains reproducibility,
cache, logging, and transaction data. The `tractograms` tree contains only
`.tck` files.

## Identity and Reuse

Identity is layered so changes invalidate only dependent work:

- FOD identity includes DWI, bvec, bval, brain/tracking masks, response/FOD
  settings, and relevant tool versions.
- DWI-space ROI identity includes source ROI content, subject transform chain,
  DWI reference geometry, and label interpolation contract.
- Bundle identity includes subject, resolved FOD, seed ROI, target ROI,
  tracking settings, `stop_at_target`, derived RNG seed, MRtrix version, and
  execution code identity.

Hashes and resolved identities are stored only in `work/state.json`; they do
not appear in result path names.

Automatic behavior replaces public `force` and `resume` modes:

- matching identity plus a valid final TCK is reused;
- missing, corrupt, or incomplete output is regenerated;
- changed identity is regenerated into `work/staging`; and
- matching valid staged output from an interrupted run is reused.

Changing one target invalidates only bundles that reference that target.
Changing a seed invalidates all targets nested under that seed. Changing FOD
inputs invalidates every bundle for that subject.

## Validation and Publication

A staged TCK is valid when `tckinfo` reads its header and reports a
nonnegative streamline count. A successful zero-streamline TCK is a valid
scientific result. An empty transformed seed or target mask is an error and no
tracking task is launched for it.

Publication is transactional per subject:

1. Every changed bundle is staged and validated.
2. Any bundle failure prevents publication of all changed bundles for that
   subject; unchanged final outputs remain untouched.
3. Before replacement, each tool-owned old TCK is renamed into the subject's
   `work/rollback` directory on the same filesystem.
4. Staged TCK files are renamed to final paths.
5. A failed rename restores all rollback files.
6. After successful final validation, replaced untracked TCK files are moved
   to the platform Trash rather than permanently deleted.

The publisher refuses to overwrite an existing TCK that is not recorded as a
tool-owned artifact in `state.json`. Independent subjects publish
independently.

## Failure and Interruption Semantics

- Complete-batch static validation precedes all writes.
- A subject preparation failure does not cancel other subjects.
- A bundle failure does not stop other queued bundles, but it prevents that
  subject's transaction from publishing.
- Successful staged bundles remain reusable after a sibling bundle fails.
- On interruption, Python stops dispatching new work, terminates child
  processes, preserves staging, and leaves prior final outputs unchanged.
- The final CLI summary distinguishes generated, reused, zero-streamline,
  failed, and not-run tasks.

## Efficiency Contracts

- DWI conversion, response estimation, and FOD generation occur at most once
  per valid FOD identity and subject.
- Each unique ROI source is transformed at most once per subject and ROI
  identity, even when multiple seeds reference it.
- Shared atlas source hashes are computed once per batch.
- Existing valid outputs never enter MATLAB or MRtrix execution queues.
- Global scheduling backfills released CPU tokens across subjects while
  preserving per-subject caps.
- MRtrix commands read one cached FOD per subject, allowing the operating
  system page cache to serve concurrent bundles.
- The design does not substitute one seed-wide tractogram followed by
  `tckedit` filtering because that would change target-conditioned sampling and
  the per-target `requested_streamlines` meaning.

## Testing Strategy

Implementation follows documentation-first TDD.

### Python Unit Tests

- strict schema, duplicate YAML keys, unknown fields, and schema version;
- required explicit seed and target sides;
- nested per-seed target ownership and canonical identity;
- safe IDs, common atlas root, binary/nonempty ROI validation;
- subject discovery and every supported path override;
- deterministic task expansion and RNG seed derivation;
- FOD, ROI, and bundle invalidation boundaries;
- CPU tokens, per-subject caps, memory dispatch threshold, and fair backfill;
- state recovery, staged reuse, and status classification; and
- transactional publication, rollback, Trash, and refusal to replace unknown
  files.

### MATLAB Unit Tests

- resolved subject JSON validation;
- Lead-DBS input and transform discovery;
- explicit transform override handling;
- one-time DWI/FOD preparation;
- ROI transformation deduplication;
- binary label-preserving resampling; and
- empty transformed-mask rejection.

### Integration and Acceptance Tests

- fake MATLAB/MRtrix executables test CLI process orchestration and failures;
- scheduler tests prove hard CPU and per-subject concurrency limits;
- command tests prove `-stop` is absent by default and present when enabled;
- interruption tests preserve prior outputs and reusable staging;
- simulated publish failure restores every prior subject TCK;
- the result tree contains only `.tck` files;
- the legacy MATLAB seed-target runner retains its current behavior; and
- a small real MRtrix acceptance run in Conda `leaddbs` validates discovery,
  preparation, TCK generation, automatic reuse, and `status`.

## Acceptance Criteria

- One YAML validates and runs multiple subjects.
- Every seed side is a separate entry and owns its exact target list.
- Every target has an explicit side and explicit path.
- All ROIs belong to the configured atlas root.
- The CLI exposes only `validate`, `run`, and `status` with YAML scientific
  input.
- Python launches no more than the configured active-subject limit.
- MATLAB starts no more than once per unresolved subject and launches no
  `parpool`.
- The global scheduler never exceeds configured CPU-token or per-subject
  bundle limits.
- Each subject prepares one reusable FOD and one copy of each unique DWI-space
  ROI.
- `stop_at_target: false` omits `-stop`; `true` appends it.
- Final result directories contain only valid TCK files at the documented
  semantic paths.
- Matching results are reused without rewriting.
- Changed results stage completely and publish transactionally per subject.
- Old untracked tool-owned outputs are moved to Trash after replacement.
- Failure in one subject does not cancel independent subjects.
- No VTA, e-field, display, density, CSV, ranking, SIFT, or connectome-statistic
  artifacts are produced.
- Existing normative-connectome and legacy MATLAB seed-target workflows remain
  unchanged.
