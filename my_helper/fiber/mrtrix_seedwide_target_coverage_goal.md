# MRtrix Seed-Wide Target-Coverage Tractography Goal

## Status

```text
design_approved
implementation_pending
formal_execution_blocked_by_test_gate
```

This document is the authoritative implementation and execution contract for
the standalone YAML-driven MRtrix seed-target tractography module. It
supersedes the pairwise target-conditioned design in
`docs/superpowers/specs/2026-07-13-mrtrix-seed-target-yaml-cli-design.md`.

## Objective

Build and run an independent Python CLI with an existing Lead-DBS MATLAB
preparation backend. For every configured subject and seed side, the module
must generate one seed-wide iFOD2 tractogram, classify each generated batch
against all targets in one pass, and stop only after every target has at least
the requested number of hit streamlines.

The implementation sequence is mandatory:

1. Commit this goal and its documentation-only supersession notice.
2. Implement the module without changing the behavior of the legacy MATLAB
   seed-target or normative-connectome pipelines.
3. Pass automated unit and integration tests in Conda `leaddbs`.
4. Validate and execute the two-subject real-data test YAML.
5. Verify its outputs, state, target coverage, and automatic reuse.
6. Only after all prior gates pass, validate and execute the 16-subject formal
   YAML.

The formal run must not start after a failed, interrupted, undercovered, or
ambiguous test run.

## Public Interfaces

Add the Python package:

```text
my_helper/fiber/core/mrtrix_seed_target/
```

Add the executable entry point:

```text
my_helper/fiber/pipelines/mrtrix-seed-target
```

The CLI exposes exactly:

```text
mrtrix-seed-target validate --config CONFIG
mrtrix-seed-target run --config CONFIG
mrtrix-seed-target status --config CONFIG
```

All scientific, subject, path, tracking, resource, and tool settings come from
YAML. There are no public `force`, `resume`, path-override, subject-override,
or tracking-override flags. Resume and reuse are automatic and identity based.
Each command writes one machine-readable JSON summary to standard output and
human progress messages to standard error. Configuration or run-integrity
failure returns nonzero.

The default Python environment is Conda `leaddbs`.

## YAML Contract

Schema version 1 has these required top-level objects:

```yaml
schema_version: 1
atlas: {}
subjects: []
tracking: {}
execution: {}
```

Unknown keys and duplicate YAML mapping keys are errors at every level.
Relative paths resolve against the YAML file directory. Subject IDs and
resolved subject directories must both be unique.

### Atlas Contract

`atlas` contains `name`, `space`, `root`, and `seeds`. Schema version 1 accepts
only `MNI152NLin2009bAsym`. Every seed is a separate side-specific item with
required `id`, `side`, `path`, and a nonempty nested `targets` list. Every
target has its own required `id`, `side`, and `path`; target side is explicit
and may differ from the parent seed side.

Supported sides are `lh`, `rh`, and `midline`. Canonical seed and target keys
are `<side>/<id>`. IDs must be safe single path components. Every resolved ROI
must be a finite, nonempty, three-dimensional NIfTI within the resolved atlas
root. Source masks are interpreted as binary by `value > 0`.

The approved formal atlas is:

```text
/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/atlases/STNSNrplus-connected regions
```

It defines left and right `STNSNrplus` seeds. Each seed owns these 18 same-side
targets in this exact order:

```text
VM_thalamus
VLA_thalamus
GPi
sPf_thalamus
GPe
PPN
VLP_thalamus
VA_thalamus
Pf_thalamus
preSMA
SMA
posterior_putamen
CM_thalamus
caudate
premotor
M1
DLPFC
RN
```

### Subject Contract

Every subject has required `id` and `subject_dir`. An optional `paths` object
may explicitly override only these discovery fields:

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
coregistration_method_log
```

Without overrides, discovery uses Lead-DBS subject structure below
`subject_dir`. It must resolve exactly one DWI, bvec, bval, native preprocessed
b0, brain mask, tracking mask, anatomical anchorNative reference, direct
MNI-to-anchorNative inverse deformation, B0 coregistration-method log, and
direct anchorNative-to-b0 affine.

The approved formal subjects, in scheduling order, are:

```text
sub-SNr003
sub-SNr007
sub-SNr006
sub-SNr011
sub-SNr012
sub-SNr014
sub-SNr016
sub-SNr018
sub-SNr020
sub-SNr022
sub-SNr026
sub-SNr024
sub-SNr029
sub-SNr030
sub-SNr017
sub-SNr015
```

### Tracking Contract

The approved tracking object is:

```yaml
tracking:
  minimum_streamlines_per_target: 300
  fod_cutoff: 0.06
  min_length_mm: 10
  max_length_mm: 250
  random_seed: 1
```

All fields are required. Counts and lengths are positive, the cutoff is finite
and positive, and `min_length_mm <= max_length_mm`.

The removed pairwise fields are invalid in this schema:

```text
requested_streamlines
max_seed_attempts
stop_at_target
```

### Execution Contract

The approved formal execution object is:

```yaml
execution:
  subject_workers: 2
  preparation_threads_per_subject: 4
  seedwide_workers_per_subject: 2
  mrtrix_threads_per_seedwide_job: 1
  cpu_budget: 16
  memory_budget_gb: 48
  memory_dispatch_fraction: 0.8
  preparation_memory_reservation_gb: 8
  seedwide_memory_reservation_gb: 2
  generation_chunk_streamlines: 50000
  maximum_seedwide_streamlines: 100000000
  matlab_executable: /Applications/MATLAB_R2024b.app/bin/matlab
  mrtrix_path_prefix: /usr/local/bin
```

The real-data test YAML differs by using two subjects, two targets per seed,
and `maximum_seedwide_streamlines: 50000`. Its one generated batch is therefore
an end-to-end test of preparation, generation, classification, extraction,
publication, status, and reuse rather than a reduced synthetic algorithm.

Every CPU and prospective memory reservation must fit its global budget.
`memory_budget_gb * memory_dispatch_fraction` is the soft dispatch capacity.
The scheduler charges each active process by the greater of its reservation
and sampled process-tree RSS, pauses new dispatch when capacity is exhausted,
and never kills a task merely for exceeding a reservation. Structural
concurrency limits that cannot be reached under CPU or memory budgets produce
warnings.

## Subject Input and Transform Contract

### Coregistration Selection

The B0 entry in each subject's
`coregistration/log/<subject>_desc-coregmethod.json` is authoritative. It must
be approved and must name the method used for anchorNative-to-b0 registration.
Discovery maps that method to the matching direct `44.mat` file:

```text
coregistration/transformations/<subject>_from-anchorNative_to-b0_desc-<method>44.mat
```

For example, SPM selects `desc-spm44.mat` and BRAINSFit selects
`desc-brainsfit44.mat`. The method-specific non-`44.mat` file is not the
default. A missing approval, unknown method, missing exact transform, or
ambiguous reference is an error.

The `44.mat` variable `tmat` is interpreted as a world-coordinate transform:

```text
x_b0_world = tmat * x_anchor_world
```

Let `A_anchor` and `A_b0` be the voxel-to-world NIfTI affines. To resample an
anchorNative ROI onto the native B0/DWI grid, the sampling relationship is:

```text
v_anchor = inverse(A_anchor) * inverse(tmat) * A_b0 * v_b0
```

Equivalently, the moved ROI affine is `tmat * A_anchor`. Both NIfTI header
affines are therefore part of the operation and its identity. Binary ROIs use
nearest-neighbor interpolation. The DWI/FOD remains on its native grid; it is
not upsampled to the approximately 0.7 mm anchorNative grid.

### MNI-to-DWI ROI Preparation

Each unique atlas ROI is transformed once per subject:

1. MNI to anchorNative uses the subject's direct inverse normalization through
   Lead-DBS MATLAB with label-preserving interpolation and the selected
   anatomical anchorNative reference.
2. AnchorNative to native B0/DWI applies the selected method-specific `tmat`
   and NIfTI affines with nearest-neighbor resampling.
3. Seed and target masks must exactly match the native B0 reference shape and
   affine and must remain nonempty.
4. For each seed, every target is cleaned on the final DWI grid as
   `clean_target = target AND NOT seed`.
5. An empty cleaned target is an error. The cleaned mask, not the uncleaned
   target, defines target hits and the final target-specific TCK.

The MATLAB process prepares one subject only, initializes Lead-DBS once, and
does not launch a parallel pool or `tckgen`. Python owns validation,
anchorNative-to-DWI affine resampling, MRtrix preparation/generation,
classification, scheduling, state, and publication.

### FOD Preparation

The subject DWI is converted with its bvec/bval gradient table. Brain and
tracking masks are converted to MRtrix format on the DWI grid. The fixed
response/FOD methods are:

```text
dwi2response tournier
dwi2fod csd
```

FOD preparation is reused only when DWI, gradients, masks, commands, tools,
code, and resolved geometry identities match.

## Seed-Wide Tracking and Coverage Algorithm

The independent execution unit is one `subject x seed side`. A unit is
sequential across its chunks because the next chunk is needed only when the
current cumulative coverage remains insufficient. Different seed sides and
subjects may run concurrently within configured limits.

For chunk index `k`, the command is equivalent to:

```text
tckgen WM_FOD CHUNK_TCK \
  -algorithm iFOD2 \
  -seed_image SEED_MASK \
  -mask TRACKING_MASK \
  -select GENERATION_CHUNK_STREAMLINES \
  -cutoff FOD_CUTOFF \
  -minlength MIN_LENGTH_MM \
  -maxlength MAX_LENGTH_MM \
  -nthreads MRTRIX_THREADS_PER_SEEDWIDE_JOB
```

No target `-include` and no `-stop` option is permitted. The mother
tractogram is seed-wide. The per-chunk MRtrix RNG seed is deterministically
derived from the base seed, resolved run identity, subject ID, seed key, and
chunk index, so distinct chunks never reuse the same random stream.

After each successful chunk, Python reads all streamlines once and performs
segment-aware voxel traversal against all cleaned target masks simultaneously.
For target `t`, a streamline contributes one hit if any of its segments
intersects any voxel in `t`. Multiple crossings of the same target still count
once. A streamline may hit multiple targets and is then included in every
corresponding target-specific TCK.

Let `n_t` be the cumulative number of mother streamlines that hit target `t`.
Generation stops successfully only when:

```text
min(n_t for every configured target) >= minimum_streamlines_per_target
```

The mother streamline total is the sum of structurally validated completed
chunk counts. It is not forced to a fixed value. The target hit fraction is:

```text
n_t / n_seedwide_total
```

Raw target counts must not be compared across subjects without this
denominator because the rarest target determines the mother total.

If the maximum seed-wide total is reached before all targets meet the minimum,
the unit becomes `coverage_failed`. The report lists every deficient target,
its actual hit count, the required count, and the mother total. A
`coverage_failed` unit is not published as complete. If a final chunk would
cross the maximum, its requested size is reduced to the exact remaining
budget.

A zero-streamline chunk or repeated failure to increase the mother count is a
terminal generation error, not an infinite retry condition. An underfilled
exit-zero chunk is accepted by its actual validated count and may be followed
by another chunk while budget remains.

## Output Contract

Every subject writes directly below its Lead-DBS directory:

```text
<subject_dir>/connectomics/dMRI/mrtrix_seed_target/
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
│   ├── chunks/
│   ├── membership/
│   ├── logs/
│   ├── staging/
│   └── rollback/
└── tractograms/
    └── <seed_side>/
        └── <seed_id>/
            ├── seedwide.tck
            └── targets/
                └── <target_side>/
                    └── <target_id>.tck
```

The public `tractograms` tree contains only TCK files. The visible `work`
directory contains preparation artifacts, logs, hashes, cumulative coverage,
chunk completion records, and extraction membership needed for deterministic
reuse and audit. No density NIfTI, CSV, VTK, FTR, MAT display file, figure,
VTA/e-field result, SIFT/SIFT2 result, or normative connectivity ranking is
produced.

On external filesystems where macOS creates AppleDouble `._*` metadata files,
the publisher must treat those sidecars as post-publication cleanup artifacts.
It must move them to the platform Trash rather than permanently delete them.
An AppleDouble cleanup failure is reported as `cleanup_pending`; it never
silently weakens the requirement that the public `tractograms` tree contain
only the declared TCK artifacts.

Each target TCK contains exactly the subset of the published mother TCK that
hit the corresponding cleaned target under the recorded classifier. Its
streamline count must equal `n_t`. The mother count and all target counts are
recorded in state and returned by `status`.

## Identity, Completion, and Automatic Resume

Identity is layered:

- preparation identity covers input imaging, gradients, masks, transform log,
  exact transform contents, NIfTI affines, preparation parameters, tools, and
  code;
- ROI identity covers source mask content, transforms, references, resampling,
  seed subtraction, and cleaned-mask content;
- seed-wide identity covers subject, FOD, seed, all ordered targets, tracking
  parameters, chunk size, maximum size, RNG derivation, MRtrix identity,
  classifier identity, and code;
- chunk identity additionally covers chunk index, requested chunk size, and
  derived RNG seed;
- published artifact identity covers content hash, canonical path, producer
  completion record, and structural TCK count.

Code identity is layered by dependency rather than represented by one global
invalidation switch. Preparation identity hashes only preparation/discovery,
transform, ROI, FOD, and directly used shared code. Seed-wide identity hashes
only tracking, TCK, classifier, RNG, and directly used shared scientific code.
Publication/scheduler/CLI code has its own provenance hash but must not
invalidate unchanged FODs, ROIs, chunks, or tractograms merely because a
non-scientific publication behavior changes.

Although chunk and maximum sizes appear under `execution`, they affect the
sampled scientific result and therefore enter seed-wide identity.

Every external producer writes to an inflight path. A file is reusable only
after its process exits zero, structural validation succeeds, its hash and
count are recorded, and it is atomically renamed to a completed path. A
readable `tckinfo` header alone never proves completion. Inflight files and
files without a matching exit-zero record are never promoted.

Matching completed preparation, ROI, chunk, membership, mother, and target
artifacts are reused automatically. Missing, changed, corrupt, or incomplete
tool-owned artifacts are regenerated. There are no public `force` or `resume`
switches.

Unknown files are never overwritten, moved, or deleted. Replacement is
allowed only when state records the exact canonical path and the current file
still matches the recorded tool-owned hash. Displaced tool-owned files are
kept in rollback until successful validation, then moved to the platform Trash
rather than permanently deleted. Trash failure leaves `cleanup_pending`
without invalidating a successfully published result.

Publication is transactional per subject: both configured seed sides and all
their targets must reach valid staged completion before any changed public TCK
for that subject is replaced. A failed rename restores prior tool-owned files.
Independent subjects may complete or fail independently.

## Scheduler Contract

Python maintains one global scheduler:

- `subject_workers` caps concurrently active subjects from preparation through
  publication or terminal failure;
- `preparation_threads_per_subject` and its memory reservation are charged to
  each preparation process;
- `seedwide_workers_per_subject` caps active seed-side units for one subject;
- `mrtrix_threads_per_seedwide_job` and its memory reservation are charged to
  each active seed-wide chunk job;
- aggregate CPU tokens never exceed `cpu_budget`;
- prospective memory admission never exceeds the soft dispatch capacity.

Scheduling is deterministic and fair-backfilled. Subjects enter in YAML order.
Preparation has priority for admitted unprepared subjects when resources fit.
Each prepared active subject receives one admissible seed-side dispatch
opportunity per round before another subject receives surplus work. Remaining
capacity is completion-biased toward the earliest active subject, with later
admissible work backfilled when the preferred task cannot fit.

SIGINT or SIGTERM stops new dispatch, terminates active child process trees,
preserves only completion-recorded artifacts as reusable, and leaves prior
public results unchanged.

## Tool and Code Identity

Validation resolves and normalizes versions for MATLAB, `mrconvert`,
`dwi2response`, `dwi2fod`, `tckgen`, `tckinfo`, and any TCK writer/validator
used by the implementation. It records the Lead-DBS Git commit and a content
hash of all relevant Python and MATLAB implementation files; the content hash
is authoritative in a dirty worktree. Timestamps, terminal formatting, and
absolute executable paths do not enter normalized semantic version identity.

## Test Plan

### Automated Python Tests

- duplicate-key YAML detection, strict unknown-field rejection, schema
  version, safe IDs, path containment, duplicate subject IDs/directories, and
  removed pairwise fields;
- exact formal and test YAML structural counts and ordering;
- subject discovery for SPM and BRAINSFit logs, approval enforcement, exact
  `44.mat` selection, anchor-reference ambiguity, and explicit overrides;
- `tmat` plus NIfTI affine resampling on synthetic grids, nearest-neighbor
  binary preservation, grid equality, and seed subtraction;
- FOD and chunk command construction, proving absence of `-include`, `-stop`,
  and removed pairwise options;
- deterministic but distinct RNG seeds across subjects, sides, and chunks;
- one-pass segment-aware multi-target classification, same-target deduplication,
  multi-target membership, cumulative counts, hit fractions, and exact target
  extraction;
- stopping at global minimum coverage, exact final remaining-budget request,
  maximum-budget coverage failure, zero/underfilled chunks, and interruption;
- strict producer exit-zero plus structural-validation completion semantics;
- automatic reuse and invalidation layers;
- CPU, memory, per-subject concurrency, deterministic fair-backfill, and
  over-reservation reporting;
- transactional subject publication, rollback restoration, non-tool-owned
  collision refusal, and Trash cleanup failure;
- CLI JSON, exit codes, validate read-only behavior, run, and status;
- unchanged legacy MATLAB seed-target behavior.

### Fake-Tool Integration Tests

Fake MATLAB and MRtrix executables exercise complete orchestration without real
imaging cost. They must cover successful preparation/generation, failed
producer processes, misleading readable partial TCKs, classification,
coverage failure, reuse, and publication rollback.

### Real Two-Subject Gate

The real test configuration is:

```text
/Volumes/VAL/STNSNr/config/mrtrix_seed_target_test.yaml
```

It contains subjects `sub-SNr003` and `sub-SNr007`, bilateral `STNSNrplus`
seeds, and same-side `GPi` and `PPN` targets. It uses one 50,000-streamline
maximum batch per subject and side.

The gate passes only when:

1. `validate` succeeds without writing subject artifacts.
2. `run` completes all four subject-side units with both targets at least 300.
3. Four mother TCKs and eight target TCKs pass structural validation.
4. Every target TCK count equals recorded membership and is no greater than
   its mother count.
5. Counts satisfy `GPi >= 300`, `PPN >= 300`, and the recorded denominator is
   the actual mother count.
6. Transformed seeds and cleaned targets are binary, nonempty, native-B0-grid
   masks; cleaned seed-target overlap is zero.
7. `status` reports complete and no unknown collision, incomplete producer,
   rollback, or cleanup error.
8. A second unchanged `run` reuses all preparation, chunks, membership, and
   public TCKs without changing their hashes or modification times.

Any unmet item blocks formal execution and must be reported explicitly.

## Formal Execution Gate

The formal configuration is:

```text
/Volumes/VAL/STNSNr/config/mrtrix_seed_target.yaml
```

### Implementation and Real-Test Gate Record (2026-07-14)

The standalone implementation is present under
`my_helper/fiber/core/mrtrix_seed_target/`, with the public executable at
`my_helper/fiber/pipelines/mrtrix-seed-target` and the isolated Lead-DBS
MATLAB preparation helper at
`my_helper/fiber/core/tracking/mh_fiber_prepare_mrtrix_seed_target_subject.m`.

The final pre-formal gate used code identity
`e3fd2b06f5b282360617decf873dfdfcb830dc38cc1c2460344f94af11a857b7`
and explicitly recorded both the current Lead-DBS Git HEAD and the layered
content hashes. The content hashes remain authoritative when the worktree is
dirty.
Its automated results were:

- 23 focused Python tests passed;
- 77 existing normative-connectivity tests passed, one was skipped, and 27
  subtests passed;
- Python compilation and `git diff --check` passed.

The final real-data test run completed all four subject-side units:

| Subject | Seed | Mother | GPi | PPN | Minimum |
|---|---|---:|---:|---:|---:|
| `sub-SNr003` | `lh/STNSNrplus` | 50,000 | 13,658 | 5,387 | 5,387 |
| `sub-SNr003` | `rh/STNSNrplus` | 50,000 | 14,294 | 2,926 | 2,926 |
| `sub-SNr007` | `lh/STNSNrplus` | 50,000 | 12,873 | 5,922 | 5,922 |
| `sub-SNr007` | `rh/STNSNrplus` | 50,000 | 17,226 | 8,175 | 8,175 |

All twelve public files were structurally valid TCKs whose counts and hashes
matched state. Every transformed seed and cleaned target was binary, nonempty,
on the exact native-B0 grid, and had zero cleaned seed-target overlap. No
cleanup remained pending and no process exceeded its configured memory
reservation. A second unchanged run reported both preparations, all four
seed-wide units, and all twelve public artifacts as reused; it generated zero
public artifacts and left every public SHA-256, byte size, and nanosecond mtime
unchanged. Therefore the real-test gate is passed and formal validation is
authorized as the next step.

After all automated and real-data test gates pass, execute:

```bash
conda run -n leaddbs python \
  /Users/mojackhu/Github/leaddbs/my_helper/fiber/pipelines/mrtrix-seed-target \
  validate \
  --config /Volumes/VAL/STNSNr/config/mrtrix_seed_target.yaml
```

Then execute:

```bash
conda run -n leaddbs python \
  /Users/mojackhu/Github/leaddbs/my_helper/fiber/pipelines/mrtrix-seed-target \
  run \
  --config /Volumes/VAL/STNSNr/config/mrtrix_seed_target.yaml
```

During the long formal execution, inspect scheduler/run state no more often
than once every 10 minutes unless a process exits or an error event occurs.
The CLI must continue automatically until all subjects finish, fail, or the
user interrupts it. A 100,000,000-streamline cap applies independently to each
subject and seed side.

## Final Acceptance Criteria

- The repository implementation and documentation are committed locally; no
  remote push is performed.
- The CLI accepts only YAML scientific input and exposes only `validate`,
  `run`, and `status`.
- Real subject transform discovery follows each B0 coregistration log and uses
  the corresponding approved method-specific `44.mat` by default.
- ROI resampling explicitly incorporates source affine, world `tmat`, and B0
  affine and keeps DWI/FOD on the native grid.
- Every target is cleaned by the relevant seed on the final grid.
- Each subject-side unit runs seed-wide iFOD2 without target conditioning and
  classifies every batch against all targets in one pass.
- Every published target has at least 300 hit streamlines; otherwise the unit
  is `coverage_failed` and is not published as complete.
- Mother totals, target counts, and target hit fractions are auditable and
  target TCK counts exactly match recorded membership.
- Valid work resumes automatically; partial or identity-mismatched work is not
  trusted.
- Unknown files are never overwritten or deleted, and tool-owned replacement
  is transactional.
- The two-subject real-data gate passes before the formal command starts.
- The formal run reports every subject and seed side as either complete or an
  explicit terminal failure; it never silently treats undercoverage as
  success.
