# MRtrix Seed-Target YAML Batch CLI Design

## Status

```text
design_revision_pending_review
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
- preparation and bundle tasks reserve their configured memory estimates
  before process launch.

The soft memory dispatch capacity is:

```text
memory_budget_gb * memory_dispatch_fraction
```

For every active task, the scheduler charges the greater of its declared
reservation and its latest sampled process-tree RSS. A new task is admitted
only when its reservation fits alongside all current charges. Validation
rejects a preparation or bundle reservation that cannot fit by itself. This
prospective reservation prevents a burst of newly launched processes from
crossing the dispatch threshold before RSS sampling reacts.

`memory_budget_gb` is a soft dispatch budget, not a hard operating-system
memory limit. A task may grow beyond its reservation after launch, so observed
RSS may exceed the configured value. Crossing the threshold stops new dispatch
but does not kill running tasks. The final status reports declared
reservations, aggregate peak RSS, and every task whose observed RSS exceeded
its reservation.

Scheduling order is deterministic and completion-biased:

1. Subjects enter the active set in YAML order, up to `subject_workers`. A
   subject remains active from preparation dispatch through publication or
   terminal failure.
2. Preparation for an active unprepared subject has priority over dispatching
   an additional bundle, provided its CPU and memory reservation fits.
3. Bundle order within a subject follows the nested seed and target order in
   the YAML.
4. At the start of each scheduling round, every prepared active subject with
   pending work is offered one admissible bundle in YAML order before any
   subject receives a second newly dispatched bundle.
5. Remaining capacity is assigned to the earliest active YAML-order subject,
   up to `bundle_workers_per_subject`, so one subject reaches its transactional
   publish point promptly. That subject remains the focus until it publishes or
   fails terminally.
6. If the next preferred task cannot fit, the scheduler scans later eligible
   tasks and backfills the first one that fits. No admissible task is left idle
   merely because an earlier task is temporarily blocked.

This defines `fair backfill` operationally: every prepared active subject gets
one dispatch opportunity per round, while surplus capacity is
completion-biased. A newly admitted subject cannot have preparation starved by
bundles from an already prepared peer.

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
  memory_dispatch_fraction: 0.8
  preparation_memory_reservation_gb: 8
  bundle_memory_reservation_gb: 2
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
`bundle_workers_per_subject`, `cpu_budget`, `memory_budget_gb`,
`preparation_memory_reservation_gb`, and `bundle_memory_reservation_gb` are
required positive values. `mrtrix_threads_per_bundle` defaults to `1` and
`memory_dispatch_fraction` defaults to `0.8`, with an allowed interval of
`(0, 1]`. `matlab_executable` defaults to `matlab`; `mrtrix_path_prefix`
defaults to an empty string and then relies on `PATH`.

Validation requires every task's CPU request to fit within `cpu_budget` and
every task's memory reservation to fit within
`memory_budget_gb * memory_dispatch_fraction`. The scheduler enforces both
aggregate admission ceilings dynamically. Validation also emits structural
concurrency warnings when any requested cap is unreachable, including:

```text
subject_workers * preparation_threads_per_subject > cpu_budget
bundle_workers_per_subject * mrtrix_threads_per_bundle > cpu_budget
subject_workers * bundle_workers_per_subject * mrtrix_threads_per_bundle
  > cpu_budget
```

The warning reports the maximum concurrency actually attainable under the
configured CPU tokens. Equivalent warnings are emitted when declared memory
reservations make the requested preparation or per-subject bundle concurrency
unreachable.

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

Every subject has a unique `id` and a Lead-DBS `subject_dir`. Duplicate subject
IDs and duplicate resolved subject directories are hard validation errors. The
output root is always created below the resolved `subject_dir`; `id` is the
logical identifier used in status, identity, and RNG derivation. `id` need not
equal the declared directory basename, but a mismatch emits a validation
warning and both values are recorded. Changing `id` changes bundle identity
even when `subject_dir` is unchanged.

Standard discovery uses the existing Lead-DBS/BIDS conventions for:

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

The transform direction is intentionally narrower than the legacy
Fiber/VTA runner because this module publishes no native/MNI display export.
MNI atlas masks are mapped to DWI in exactly two label-preserving stages:

1. MNI to anchorNative uses the subject's inverse normalization, matching
   `ea_apply_normalization_tofile(..., 1, 'GenericLabel', anchor_reference)`.
   An explicit `mni_to_anchor_transform` must therefore be a direct
   MNI-to-anchorNative deformation, not the forward anchorNative-to-MNI warp.
2. anchorNative to DWI uses the direct anchorNative-to-b0 ANTs transform,
   matching `ea_ants_apply_transforms(..., useinverse=0, b0_reference,
   anchor_to_dwi_transform, 'GenericLabel')`.

The standard Lead-DBS transform candidates are:

```text
normalization/transformations/<subject>_from-MNI152NLin2009bAsym_to-anchorNative_desc-ants.nii.gz
coregistration/dwi/<subject>_ses-preop_space-anchorNative_desc-preproc_acq-iso_T1w2<subject>_ses-preop_acq-iso_dwi_b0_ants1.mat
coregistration/anat/<subject>_ses-preop_space-anchorNative_desc-preproc_acq-iso_T1w2<subject>_ses-preop_acq-iso_dwi_b0_ants1.mat
```

The first path is the direct inverse normalization. The latter two are ordered
location candidates for the same direct anchorNative-to-DWI affine; discovery
selects the first existing file and records which candidate was used.

Discovery must not copy the legacy runner's requirements for
DWI-to-anchorNative or anchorNative-to-MNI transforms; those directions are
needed for display export, not for MNI ROI to DWI preparation. Preflight
records the exact selected transform paths, directions, inversion flags, and
reference images.

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

### Tool and Code Version Identity

Version identity is captured before cache resolution because it directly
controls invalidation:

- Python executes `mrconvert -version`, `dwi2response -version`,
  `dwi2fod -version`, `tckgen -version`, and `tckinfo -version` from the
  resolved MRtrix path.
- The MATLAB preflight returns `version` and `version('-release')`.
- Python records the Lead-DBS Git commit when available and a SHA-256 content
  hash of the relevant Python and MATLAB implementation files. The content hash
  remains authoritative when the worktree is dirty.

Each command's output is normalized into a JSON object containing the tool
name, semantic/release version, and build identifier. Timestamps, terminal
color codes, and absolute executable paths do not enter the normalized value.
A missing command or unparsable version response is a validation error.

FOD identity uses the preparation-command, MATLAB, and Lead-DBS identities.
Bundle identity additionally uses the `tckgen` identity. TCK structural
validation records the `tckinfo` identity without making a different
`tckinfo` patch version alone invalidate a scientifically complete bundle.

## CLI Contract

The executable exposes exactly these commands:

```text
mrtrix-seed-target validate --config CONFIG
mrtrix-seed-target run --config CONFIG
mrtrix-seed-target status --config CONFIG
```

All scientific and execution parameters come from YAML. The CLI does not offer
ROI, subject, tracking, output, `force`, or `resume` overrides.

- `validate` is read-only. It completes all Python checks first, then launches
  at most one MATLAB preflight process per unique configured subject. Total
  MATLAB startups are therefore no greater than the number of subjects, and
  concurrent preflights are bounded by `subject_workers`, CPU admission, and
  memory admission. The preflight resolves Lead-DBS transforms and versions but
  creates no subject directories, FODs, ROI derivatives, or tractograms.
- `run` validates the complete batch before starting subject preparation,
  prepares unresolved subjects, globally schedules unresolved bundles, and
  publishes complete subject transactions.
- `status` reads subject state and invokes `tckinfo` for existing final TCK
  files. For subjects in the current YAML it also reports removed-pair orphans,
  incomplete attempts, and `cleanup_pending` rollback files. It does not start
  MATLAB.

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
│   │   ├── inflight/
│   │   └── complete/
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
- a matching staged output is reused only when `state.json` contains its
  successful producer-completion record and the completed staged TCK passes
  structural validation.

Changing one target invalidates only bundles that reference that target.
Changing a seed invalidates all targets nested under that seed. Changing FOD
inputs invalidates every bundle for that subject.

Removing a seed or target from a later YAML does not delete its prior output.
For subjects still listed in the current YAML, `status` compares the current
task set with tool-owned records and reports removed-pair TCK files as
`orphaned_from_current_config`. `run` leaves these files untouched. If an
entire subject is removed from the YAML, its directory is not inspected and
all existing outputs remain out of scope. No cleanup command is added in schema
version 1.

## Validation and Publication

`tckinfo` alone is not a producer-completion signal. A killed `tckgen` process
may leave a readable header with a misleading zero count. Every bundle
therefore uses this state machine:

1. Before launch, `state.json` records the matching bundle identity as
   `running`.
2. `tckgen` writes only to
   `work/staging/inflight/<bundle>.partial.tck`; the filename still ends in
   `.tck` so MRtrix selects the correct format.
3. A nonzero, signaled, or missing process exit status marks the attempt
   incomplete. Its partial file is never reusable.
4. Only after `tckgen` exits zero does Python run `tckinfo`, require a readable
   header, and require a nonnegative actual streamline count.
5. The validated inflight file is atomically renamed to
   `work/staging/complete/<bundle>.tck`, and an atomically written state record
   stores producer exit zero, bundle identity, actual count, TCK hash, and the
   completed staged path.

Reuse requires both the completed path and its matching successful state
record. A crash between file rename and state update therefore causes safe
regeneration rather than inferred success. Inflight files and completed files
that retain only their pre-launch `running` ownership record are incomplete
tool-owned attempts and are moved to Trash before regeneration; they are never
promoted based on `tckinfo` alone. A file with no ownership record is
non-tool-owned and is never touched.

A successful zero-streamline or underfilled TCK is a valid scientific result
when this full completion contract passes. An empty transformed seed or target
mask is an error and no tracking task is launched for it. State and CLI output
record `requested_streamlines`, `actual_streamlines`, and two independent
status axes:

```text
action: generated | reused | failed | not_run
yield_status: full | underfilled | zero | unknown
```

`underfilled` means `0 < actual_streamlines < requested_streamlines`, normally
after the maximum seed-attempt budget is exhausted. `full` means equality,
`zero` means `actual_streamlines == 0`, and a reported count greater than the
requested count is a structural validation error rather than a fourth yield
class.

Publication is transactional per subject:

Before expensive execution, every occupied final path is checked against
`state.json`; a non-tool-owned collision fails that subject without touching
the file. After this preflight:

1. Every changed bundle completes the producer and staging contract above.
2. Any bundle failure prevents publication of all changed bundles for that
   subject; unchanged final outputs remain untouched.
3. Before replacement, each tool-owned old TCK is renamed into the subject's
   `work/rollback` directory on the same filesystem.
4. Staged TCK files are renamed to final paths.
5. A failed rename restores all rollback files.
6. After successful final validation, the displaced old tool-owned TCK files
   in `work/rollback` are moved to the platform Trash rather than permanently
   deleted.

`tool-owned` means that `state.json` records the exact canonical path and prior
published artifact identity and that the current file still matches the
recorded artifact hash. Git tracking status is irrelevant. A path-only state
record or a content mismatch is treated as a non-tool-owned collision. The
publisher only replaces tool-owned outputs. A non-tool-owned file is never
overwritten, moved, or deleted.

Rollback renames are atomic because `work` and `tractograms` share the subject
filesystem. Moving rollback files to platform Trash is a post-publication
cleanup operation and is not assumed atomic: on another volume it may become a
slow copy-plus-delete. If Trash transfer fails, the newly published result
remains valid, the old file remains safely in `work/rollback` with
`cleanup_pending`, and the CLI returns a nonzero cleanup status so a later run
can retry. Independent subjects publish independently.

## Failure and Interruption Semantics

- Complete-batch static validation precedes all writes.
- A subject preparation failure does not cancel other subjects.
- A bundle failure does not stop other queued bundles, but it prevents that
  subject's transaction from publishing.
- Successful staged bundles remain reusable after a sibling bundle fails.
- On interruption, Python stops dispatching new work, terminates child
  processes, preserves only completion-recorded staging as reusable, and
  leaves prior final outputs unchanged.
- A Trash cleanup failure is reported separately from scientific publication;
  published results remain valid while rollback files stay `cleanup_pending`.
- The final CLI summary reports action and yield status separately, including
  full, underfilled, and zero-streamline bundles plus requested and actual
  aggregate streamline counts.

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
- duplicate subject-ID and duplicate resolved-subject-directory rejection;
- subject ID/directory mismatch warning and output-root resolution;
- subject discovery and every supported path override;
- deterministic task expansion and RNG seed derivation;
- normalized MRtrix, MATLAB, and Lead-DBS version/code identity;
- FOD, ROI, and bundle invalidation boundaries;
- single-task CPU/memory feasibility, structural cap warnings, prospective
  memory reservations, RSS over-reservation, and soft dispatch threshold;
- deterministic preparation priority, one-per-subject fairness rounds,
  completion-biased focus, and admissible-task backfill;
- producer exit-status gating, partial-file rejection, state recovery, staged
  reuse, orphan classification, and action/yield status classification; and
- transactional publication, rollback, Trash, and refusal to replace unknown
  files.

### MATLAB Unit Tests

- resolved subject JSON validation;
- Lead-DBS input and transform discovery;
- exact MNI-to-anchorNative-to-DWI direction, interpolation, and explicit
  transform override handling;
- one-time DWI/FOD preparation;
- ROI transformation deduplication;
- binary label-preserving resampling; and
- empty transformed-mask rejection.

### Integration and Acceptance Tests

- fake MATLAB/MRtrix executables test CLI process orchestration and failures;
- `validate` starts no more than one read-only MATLAB preflight per subject and
  obeys configured concurrency and admission limits;
- scheduler tests prove hard CPU and per-subject concurrency limits and exact
  deterministic dispatch order;
- command tests prove `-stop` is absent by default and present when enabled;
- interruption tests leave `.partial.tck` non-reusable even when fake
  `tckinfo` reports count zero;
- exit-zero underfilled and zero-streamline fixtures remain valid and report
  requested versus actual counts;
- simulated publish failure restores every prior subject TCK;
- Trash failure preserves published output and records `cleanup_pending`;
- removed targets are preserved and reported as orphans for configured
  subjects;
- the result tree contains only `.tck` files;
- the legacy MATLAB seed-target runner retains its current behavior; and
- a small real MRtrix acceptance run in Conda `leaddbs` validates discovery,
  preparation, TCK generation, automatic reuse, and `status`.

## Acceptance Criteria

- One YAML validates and runs multiple subjects.
- Duplicate subject IDs and duplicate resolved subject directories are
  rejected.
- Every seed side is a separate entry and owns its exact target list.
- Every target has an explicit side and explicit path.
- All ROIs belong to the configured atlas root.
- The CLI exposes only `validate`, `run`, and `status` with YAML scientific
  input.
- `validate` starts at most one read-only MATLAB preflight per configured
  subject and obeys the same CPU/memory admission limits.
- Tool identity uses normalized MRtrix/MATLAB versions plus Lead-DBS source
  identity and drives the documented invalidation layers.
- ROI preparation uses only the direct MNI-to-anchorNative and
  anchorNative-to-DWI chain; display-only inverse directions are not required.
- Python launches no more than the configured active-subject limit.
- MATLAB starts no more than once per unresolved subject and launches no
  `parpool`.
- The global scheduler never exceeds configured CPU-token or per-subject
  bundle limits.
- Every dispatched task fits prospectively reserved memory capacity; actual
  memory over-reservation pauses further dispatch and is reported.
- Scheduler tests prove preparation priority, one opportunity per prepared
  subject per round, completion-biased focus, and admissible backfill.
- Each subject prepares one reusable FOD and one copy of each unique DWI-space
  ROI.
- `stop_at_target: false` omits `-stop`; `true` appends it.
- Final result directories contain only valid TCK files at the documented
  semantic paths.
- No staged or final TCK is accepted without a matching producer exit-zero
  completion record and structural validation.
- Full, underfilled, and zero-streamline results report requested and actual
  streamline counts separately from generated/reused action status.
- Matching results are reused without rewriting.
- Changed results stage completely and publish transactionally per subject.
- Displaced old tool-owned outputs are moved from rollback to Trash after
  replacement; non-tool-owned files are never touched.
- A failed Trash transfer leaves the displaced file in rollback as
  `cleanup_pending` without invalidating the newly published TCK.
- Removing a configured pair preserves its prior TCK and reports it as an
  orphan when that subject remains in the YAML.
- Failure in one subject does not cancel independent subjects.
- No VTA, e-field, display, density, CSV, ranking, SIFT, or connectome-statistic
  artifacts are produced.
- Existing normative-connectome and legacy MATLAB seed-target workflows remain
  unchanged.
