# MRtrix Seed-Wide Target-Coverage Tractography Goal

## Approved fixed-sampling whole-brain extension

This section takes precedence over the historical target-coverage contract
below for the newly approved Meige configuration. It does not authorize a
patient run, a Git commit, or changes to the existing atlas-builder work.

### Scientific contract

- Use the existing left/right STNplus and VOplus masks under
  `atlases/STNVOplus (Ewert 2017)` without further thresholding, dilation,
  subtraction, or merging. The expanded seeds overlap; report that overlap.
- Use all 166 existing binary AAL3 targets (78 left, 78 right, 10 midline)
  under `atlases/AAL3 (Rolls 2020)`. Their human atlas QC is approved.
- Four seeds per subject share the same target definitions. Subjects are
  Meige001--Meige021, Dys022, and Meige023, retaining their actual IDs.
- Fixed sampling selects 300000 valid mother streamlines per seed in
  50000-streamline chunks, with base random seed 42, iFOD2, cutoff 0.06,
  and lengths 10--250 mm. No target-conditioned seeding, stop-at-target,
  nearest-region compensation, ACT, or SIFT2 is added.
- `minimum_streamlines_per_target: 0` is allowed only with an explicit
  `seedwide_streamlines`. This opts into unrestricted whole-brain target
  reporting: retain target boundaries, allow zero hits, and distinguish
  unavailable native targets from valid targets with zero hits. Existing
  positive-coverage configurations retain seed subtraction and strict
  target validity. No schema version or new user-facing option is added.
- Source seeds and targets must still be finite, nonempty binary 3D images.
  They may have different grids in the same declared MNI space (the selected
  seeds are 0.5 mm and AAL3 is 1 mm). Resampling reads each image affine.
- A native target that disappears or has no intersection with the tracking
  mask is unavailable, with null count/fraction and a reason. Preserve its
  statistics row but do not fabricate a target TCK. Partial tracking-mask
  coverage is reported without silently clipping or dilating the target.
- Empty native seeds, bad transformations, corrupt input files, and failed
  mother generation remain errors. Missing target source files remain errors.
- Membership is segment-aware passage through a target voxel, with one hit
  per streamline per target. Multiple targets may contain the same streamline.
  Report count / actual mother count; fractions need not sum to one.
- Report seed/target overlap and target side relative to the seed. A primary
  comparison target must be available and nonoverlapping for every configured
  seed on that seed's side; keep excluded rows and their raw counts. This is
  a descriptive eligibility flag, not evidence of anatomical specificity.

### Component reuse and invalidation

The current shared preparation identity and target-dependent chunk RNG are
confirmed failure modes for this fixed-sampling use case. Separate their
dependencies without adding force/resume commands or versioned copies:

1. FOD preparation depends on DWI, gradients, brain mask, its actual algorithm
   and tool implementation, not targets or atlas-to-native transforms.
2. Each transformed ROI depends on that source mask, native reference,
   anatomical reference and selected transforms, not other ROIs or the FOD.
3. Fixed mother chunks depend on actual FOD/brain/response/tracking-mask
   artifacts, the current seed, generation settings and generator code.
   Target lists, target QC, coverage thresholds, and display settings must
   not change the fixed mother RNG or regenerate its chunks.
4. Classification depends on the mother chunks and effective target masks;
   changed targets reclassify existing chunks and rebuild target outputs.
5. The historical coverage-driven mode retains target-dependent generation
   identity because target counts determine its stopping condition.
6. Native publication reuse must compare current scientific input identity,
   not just filenames and artifact hashes. Display-only changes and YAML
   comments, formatting, key order, and unrelated subject entries must not
   regenerate native streamlines.
7. Preserve the actual generated-artifact hashes required after the prior
   stale-chunk incident. Commit IDs and broad repository hashes are provenance,
   not global rerun switches. Keep the existing transactional publication and
   ownership protections for untracked research files.
8. MATLAB identity uses the version/release line returned by the explicit
   query, not startup warnings. The local version query emits startup warnings
   before its version, which must not become scientific cache dependencies.

### Deliverables and execution gate

- Publish all configured target statistics, including availability, overlap,
  coverage, comparison eligibility, counts and fractions. Valid zero-hit
  targets have valid empty TCKs; unavailable targets have no TCK artifact.
  Keep the full records in the retained subject state and publish a flat
  `target_statistics.csv` alongside tractograms; unavailable numeric fields
  are empty CSV cells and JSON null. Include this report in the existing
  publication transaction and artifact verification.
- Preserve native and MNI mother/available-target TCKs, provenance, display
  outputs, and subject status. Update publication, conversion, visualization,
  status and cleanup to distinguish unavailable targets from missing artifacts.
  A seed with no evaluable targets has a seed-only scene. Display labels include
  hemisphere so bilateral AAL3 names remain distinguishable.
  Target-space conversion and replacement operate on each `side/seed`
  directory, not the whole hemisphere. Its identity includes only that seed's
  native artifacts and spatial transforms. Preserve prior MNI ownership records
  while replacing native outputs so downstream updates can replace them safely.
  Target-only updates reuse the verified MNI mother and extract new target
  subsets by native mother ordinal; they do not repeat coordinate deformation.
- Create the full-cohort YAML and a three-subject pilot YAML (Meige001,
  Meige008, Meige023), with the same scientific settings. Keep pilot caches;
  the full successful batch may clean only tool-owned work caches to Trash.
- Do not start tracking in this implementation request. Patient-specific
  native ROI/FOD QC and Meige023's normalization approval 0.5 remain separate
  from the approved AAL3 atlas QC.
- Preserve unrelated dirty atlas-builder files; do not commit or push.

### Focused acceptance tests

Test zero coverage with/without fixed sampling; mixed source grids; retained
target overlap; native target disappearance and tracking-mask coverage;
valid zero-hit versus unavailable rows and TCKs; classification and RNG reuse
after target changes; seed changes affecting only that seed; FOD reuse after
ROI changes; native request invalidation; conversion/display/cleanup with
unavailable targets; and semantic YAML equivalence. Run the MRtrix package
tests after focused checks because publication and preparation contracts
span its modules. Validate the real YAML without launching patient MATLAB,
FOD estimation, tckgen, or changing patient data.

### Implementation verification and retained boundaries

- Full configuration: `/Volumes/VAL/meige/config/mrtrix_seed_target.yaml`.
  Pilot configuration: `/Volumes/VAL/meige/config/mrtrix_seed_target_pilot.yaml`.
- The full configuration passed the existing read-only CLI validation for
  23 subjects, four seeds and 166 targets per seed. The pilot has the same
  atlas and scientific settings and selects Meige001, Meige008 and Meige023.
- All 23 reverse normalization field headers match the selected seed reference
  grid. Meige023 still has normalization approval 0.5; it was not changed.
- Synthetic tests cover native reclassification after cache cleanup, MNI
  mother reuse, two seeds in one hemisphere, zero versus unavailable targets,
  source/native mask provenance, independent ROI reuse and semantic YAML.
  MATLAB static analysis found no syntax errors; full patient tracking and
  real-data scene rendering have not been executed for this extension.
  The MRtrix package suite completed with 78 passed and one skipped test
  (the historical STNSNr `config/spot` YAML was not present).
- Historical fixed-sampling results used a target-dependent RNG identity.
  They are not relabeled as samples generated under the corrected identity;
  existing files are left untouched by this implementation. Running an old
  configuration later will use the corrected producer identity and the
  existing ownership/Trash publication rules, not a migration shim.
- Retain the existing whole-batch input validation before producers, as
  required by the batch contract. Retain artifact integrity verification,
  ownership checks and transactional publication because of the documented
  stale-chunk incident and untracked research-data protection. Broad code
  hashes remain provenance; they are not a global scientific rerun switch.

### Approved Meige execution recovery

The user approved Meige023 registration and the full 23-subject run. The
normalization approval value remains 0.5 in its source record and is retained
as a provenance warning, not rewritten as part of execution.

The first run completed ROI/FOD preparation for all subjects and generated
one 50000-streamline mother chunk for each of the 92 seeds. Target
classification then failed with `ModuleNotFoundError: No module named 'core'`.
The reproduced traceback reaches Numba's cached environment deserialization:
pytest's relative package imports compiled the shared traversal module under
`core.seed_target_connectivity`, while the public CLI imports it under
`my_helper.fiber.core.seed_target_connectivity`.

Recovery is limited to the demonstrated import mismatch:

- Import the shared classification models and traversal kernel by their
  canonical repository package name, as the public CLI and other consumers do.
  Do not add a runtime alias, retry, fallback, or new configuration option.
- Add a subprocess regression that warms the kernel through the pytest-style
  package path and then reads that cache through the canonical CLI path.
- Move only `traversal.*.nbi` and `traversal.*.nbc` compiled-cache files from
  the shared module's `__pycache__` to system Trash before rebuilding them.
  Preserve every patient preparation, mother chunk, and existing run log.
- The classification source edit invalidates classification and its dependent
  target outputs only. The mother generator, FOD and ROI identities and base
  random seed remain unchanged. Existing mother chunks must pass the current
  hash/count checks and be reused before further generation.
- Resume the same YAML in the detached session, appending to the original log.
  Verify reused preparation and the first successful classification plus
  subsequent chunk generation before reporting that execution has resumed.

Retain the existing whole-batch input validation and artifact integrity checks
because the batch execution contract and prior stale-chunk incident require
them. Do not introduce broader validation or global cache invalidation.

Recovery verification: the import/cache subprocess regression reproduced the
namespace mismatch before the edit and passed afterward. The 27 focused
tracking, whole-brain and traversal tests passed. Meige001's retained first
50000-streamline left STNplus chunk passed its recorded SHA-256 check and
classified successfully against all 164 available native targets (two of the
166 configured targets were unavailable). All 92 recorded mother-generation
code identities still match the unchanged generator. The 31 affected Numba
cache files were preserved in system Trash; patient caches were not removed.
The resumed batch reused Meige001/Meige002 preparation and their original
left STNplus/VOplus first chunks, completed classification for those chunks,
and entered generation of chunk 000001 without the import error. Completion
of the full cohort still requires the normal publication and status checks.

### Meige MNI domain failure: investigation and execution boundary

The resumed Meige001 run published all four native mothers at 300000
streamlines per seed. Its left STNplus MNI conversion then failed with
`point_inverse_solver_failed`. The first 499888-point conversion buffer
contains 3185 points outside the primary field; the paired-field inverse
resolved 1208 and could not resolve 1977. These are buffer-level counts,
not a census of the complete mother tractogram.

Read-only diagnostics found that increasing the inverse iteration limit
from 64 to 256 and 1024 leaves the same 1977 points unresolved: their
estimates leave the reverse field's domain. Bounded inverse fitting of five
high-residual points reaches the inferior MNI field boundary at approximately
Z = -72.25 mm with residuals of 5.40--6.06 mm. This supports a genuine
field-coverage limitation for those points, not merely an iteration limit.
Only the sampled EasyReg normalization fields were found; no original
full-domain normalization components were found in the subject directory.
Synb0 registration components belong to a different transformation and
must not be substituted.

Preserve the native publications, mother chunks, preparation artifacts,
and original fields. Do not silently extrapolate the deformation, clip
points, relax the inverse tolerance, discard streamlines, or mark an
incomplete MNI result complete. The user must choose between continuing
native processing with MNI deferred, explicitly permitting complete-fiber
MNI exclusion with an audit, or supplying a wider valid normalization
transform. No source-code or scientific-parameter change is made merely
to suppress this failure.

Space-conversion-only changes must remain downstream of native publication:
they must not invalidate FOD preparation or mother generation. Retain the
existing stage-specific identities, artifact verification, and publication
ownership checks. Software failures with a demonstrated repair may be
fixed and resumed under the user's execution authorization; changes to
anatomical registration, scientific sampling, or fiber inclusion still
require an explicit decision.

### Approved Meige001 coverage-limited MNI display pilot

The user approved a Meige001-only display derivative before any cohort
rollout. Native mother/target TCKs, target statistics, published provenance,
work state, and all caches remain unchanged. This is not complete MNI
publication and must not change the full pipeline's fail-closed converter.

Implement a separate `limited_display` module that reads the existing YAML
and native publication. Reuse the current point-field interpolation and
paired-field inverse solver, with the existing tolerance and iteration
limit. Points inside the primary field use its direct mapping; outside
points are displayable only when the paired inverse converges. Also require
the mapped point to lie inside the MNI reference field of view. A failed
point is missing, never clipped, extrapolated, or left in native coordinates.
No brain-mask exclusion is introduced: the template brain mask touches its
inferior image boundary, so image coverage is not an anatomical exclusion.

Split each mother streamline into maximal contiguous runs of valid original
vertices. Retain runs of at least two vertices; record isolated valid points
as not drawable. Do not join across a missing vertex or add synthetic boundary
points. Preserve each vertex's native point ordinal. The source fiber ID is
the subject, seed key, and zero-based ordinal in the unchanged mother TCK;
TCK has no embedded source IDs. A sidecar maps every output fragment ordinal
to that source ID and its half-open original point interval. A second table
has one row for every source fiber, including intact, truncated/split, and
not-displayed cases, with reasons and counts. Fragment counts are not fiber
counts or connectivity estimates.

Write only to a new subject-local `display_limited_mni` directory, never the
formal tractogram/visualization publication paths. Refuse an existing output
directory rather than overwriting untracked artifacts. Process all four
Meige001 mothers, but no other subject and no target reclassification.
Produce a clearly labeled sampled anatomical preview, retain all eligible
fragments in TCK, and record preview sampling separately from domain loss.
Use deterministic source-ordinal sampling, not a new tracking random seed.

Verification covers synthetic gaps, all-invalid and isolated points, paired
inverse recovery, reference-FOV exclusion, ID/point-interval reconstruction,
output TCK structure, count reconciliation, and unchanged native metadata
and statistics. For the real pilot, also compare sampled retained vertices
to their exact native source intervals and the current mapping, check ANTs
point parity, and report paired-field round-trip errors without relaxing
the existing complete-conversion QC thresholds. This is a geometry audit,
not an additional filter or a replacement for anatomical registration QC.
No repeated cohort-wide content hashing is required: use
the previously verified publication receipts, a streaming source-count
check, before/after file size and mtime inventory, and hashes of small
state/statistics/provenance files. Record current transform and display-code
hashes for this derivative. Only display input/transform/method changes
require regenerating this derivative; no cache invalidation or native
execution is introduced. Preview style changes affect only previews.

Pilot result: all four Meige001 mothers were read at 300000 fibers each.
Intact/truncated/not-displayed source counts were 272622/27378/0 (lh STNplus),
282666/17334/0 (lh VOplus), 277757/22243/0 (rh STNplus), and
286160/13840/0 (rh VOplus). The 1200543 display fragments retain the source
IDs of all 1200000 native fibers; 375445 unresolved vertices and 230 isolated
valid vertices are not drawn. Native publication metadata, state, YAML,
transforms, and target-statistics preservation checks passed. The 22 focused
display/point-conversion tests passed, and both preview images were inspected.

Real-data geometry audit: 960 source fibers / 963 fragments matched their
original point intervals and mapped float32 coordinates exactly. ANTs point
parity passed. The original 200-midpoint-per-seed round-trip sampling passes
all existing thresholds. An expanded sample of 105663 retained vertices
contains 14 direct-field points with round-trip errors above 0.5 mm (maximum
0.593997514 mm). These are interior, not inferior truncation endpoints, and
their direct mappings agree with ANTs. Preserve this local paired-field
inverse-consistency warning in the pilot review; do not change tolerance,
filter those points, claim full MNI publication, or roll out to other
subjects without the user's review. `review.json` links the display scope,
RAS units, count summary, preservation evidence, and geometry warning.

### Approved coverage-limited display cohort rollout

The user reviewed the Meige001 pilot and approved the remaining 22 subjects.
Keep the existing pilot unchanged. Extend the same display-only entry point
with explicit subject selection and a separate cohort summary directory;
do not call native or full-pipeline execution. Refuse existing subject display
directories. A failed subject must not invalidate other subjects or any native
artifact. No tracking, ROI, FOD, target classification, or cache cleanup runs.

Reuse the pilot mapping, contiguous-vertex rule, source IDs, exhaustive audit
tables, and preview sampling unchanged. Generalize the pilot geometry audit:
200 midpoint-stratified source fibers plus the first 40 truncated fibers per
seed, with all retained vertices checked against the original source and
serialized fragments. Compare direct mapping and recovered points with ANTs,
check the stored forward/inverse coregistration matrices, and retain the
existing 0.05/0.2/0.5 mm round-trip median/p95/maximum thresholds. Record
outlier source IDs and vertices, missing sampled midpoints, and QC warnings;
warnings are not an additional display filter or permission to relax a
threshold. Preserve the known Meige023 normalization approval warning.

Each subject receives geometry QC, a review receipt, and the two anatomical
projection previews. The cohort summary reconciles source fibers, fragments,
truncation, non-display, and warnings, with links to individual previews.
Overview previews are samples, not connectivity measurements. Use common
coordinates and scales in the cohort preview. Completion refers only to this
coverage-limited display derivative, never full MNI publication.

Native receipts and small scientific-summary hashes are checked against the
existing publication. Before/after metadata covers native published files,
configuration, state, and transformations; small files are hashed. Do not
repeat cohort-wide native TCK hashing. Display inputs affect only the selected
subject's display derivative; preview rendering affects only its preview.
No automatic invalidation or overwrite is introduced. Test explicit subject
selection, unchanged QC thresholds, missing/empty samples, warning retention,
and source-ID verification before real cohort execution.

The cohort execution was interrupted after 14 completed subjects, during the
first seed of Meige016. Recovery reads the existing cohort receipt and skips
every completed subject. First confirm that no exporter remains active. Move
only the interrupted, uncompleted subject display directory to the user's
Trash before rerunning that display; retain its original preservation receipt
and compare native metadata before recovery. The completed subject directories
and all native files are untouched. Append the same batch log and continue
updating the existing cohort receipt. This incident does not justify a native
rerun, cohort-wide display rerun, or general cache invalidation mechanism.

Meige023 stopped before display creation because the existing ANTs B0/anchor
matrix pair has a maximum identity-product error of 2.9648774579893455e-6,
above the unchanged 1e-8 threshold. Both source ANTs transforms contain
float32 parameters; the stored 44.mat matrices and Python loader use float64.
The stored SPM pair is a different registration and must not be substituted.
Retain the strict gate pending explicit user direction. Report 21 of 22 new
subjects as completed, with Meige023 explicitly not exported; partial cohort
summaries and preview sheets must not claim cohort completion. Do not modify
either matrix, normalization approval, native data, or connectivity statistics.

The user subsequently explicitly authorized continuing Meige023 display with
this matrix-QC failure retained as a warning. Add an explicit subject-scoped
execution opt-in, `--matrix-qc-warning-subjects sub-Meige023`. The 1e-8 threshold
and both matrix values remain unchanged; the result must record a failed QC,
not a pass. Without the named opt-in the existing gate still raises. This
authorization applies only to the limited display; the full converter and
native pipeline remain unchanged. Record the measured error, threshold,
authorization, and warning in the subject provenance and cohort receipt.
Continue the existing batch after the 21 completed subjects without repeating
them. Preserve the partial summary/preview artifacts in Trash before replacing
them with the completed 22-subject summaries at the same unversioned paths.

Final cohort display result: all 22 additional subjects / 88 seeds completed,
reading 26400000 unchanged native mother fibers. There are 26181991 intact
fibers, 218009 truncated fibers (0.825791667%), zero wholly undisplayed fibers,
and 26403221 retained fragments. Exhaustive fragment/ID/count checks and each
subject's native/statistics preservation checks passed. The 2081522 sampled
retained vertices matched their source intervals exactly; all ANTs parity
samples passed. Retain 1803 sampled round-trip points above 0.5 mm (maximum
1.721216971 mm), the subject-specific QC warnings, and Meige023's explicitly
authorized matrix-QC failure and normalization approval 0.5 warning.

The 28 focused display/conversion tests passed; the display-only tests also
passed after confirming subject-scoped warning authorization. No native/FOD/
ROI/tracking/classification cache is invalidated. Exhaustive validation is
limited to new display TCK/ID tables because complete source-ID accounting is
required; no cohort-wide native rehash or broad test suite was run. Cohort
contact sheets show one consistently sampled left-STN sagittal panel per
subject; individual previews retain all four seeds and both projections.
Contact sheets use only the required rows, and layout changes affect preview
files only. This is limited-display completion, not full MNI publication.

### Approved native-first continuation

The user selected completion of native tracking while deferring the MNI
coverage problem. Add `run-native --config <yaml>` to the existing YAML-only
CLI and a `native_only=False` keyword to `run_batch`. This is an execution
stage selection, not a new scientific configuration or schema version.
The normal `run`, `validate`, and full-pipeline `status` commands retain
their existing meanings.

- `run-native` uses the same configuration, resource pool, native input
  identities, producers, and publication transaction as `run`. Verify and
  reuse existing native publications; otherwise resume verified mother
  chunks. Do not invoke MNI conversion or visualization in this command.
- A successful native-only batch returns `status: native_complete`, with
  `execution_scope: native` and deferred MNI/visualization stages. This is
  successful completion of the requested stage, not full-pipeline completion.
  Newly published subject states retain the existing `native_complete`
  status. Reused subject states keep their recorded MNI failure or partial
  conversion diagnostics; do not relabel those records as full success.
- Preserve all work caches, even when every native subject succeeds and the
  YAML requests cleanup after success. Cleanup remains gated on successful
  completion of the full pipeline. Full-pipeline `status` remains incomplete
  while MNI outputs or visualization are missing.
- Keep whole-batch input validation required by the existing batch contract,
  but do not probe `antsApplyTransformsToPoints` in native-only execution:
  that external tool is used only by the deferred coordinate conversion.
- The command selection and orchestration edit are not native identity
  inputs. They invalidate no FOD, ROI, mother, or classification output.
  YAML bytes and semantic values remain unchanged. Existing native artifact
  integrity and ownership checks remain required by the stale-cache incident
  and untracked-data protection policy.
- Verify native fast-path reuse without any producer or MNI call, generation
  followed by native-only publication, native-only batch success/failure
  accounting, deferred cleanup, CLI exit codes, and unchanged full-run
  behavior before resuming the real batch in the existing detached session.
  Append to the original log and update the ten-minute monitor to accept
  native-stage completion while retaining MNI as pending work.

Native-stage verification: 20 focused tests passed and one historical-input
test was skipped. The MRtrix package suite passed 88 tests with the same one
skip. All 92 retained mother identities still match the current generation
implementation and retain random seed 42 and fixed sampling of 300000.
The semantic YAML hash remains unchanged. No repository-wide tests, global
cache invalidation, registration changes, or existing TCK replacement were
required by this orchestration change.

## Status

```text
design_approved
implementation_complete
real_data_test_gate_passed
formal_execution_resumed_seven_subject_batch_running
fixed_seedwide_sampling_approved_for_all_subject_rerun
fixed_seedwide_sampling_implementation_complete
seed42_rerun_integrity_hardening_in_progress
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

The approved seed-42 rerun, pre-rerun archival gate, exact preparation-artifact
identity binding, and post-success cache cleanup contract are specified in
`docs/superpowers/specs/2026-07-19-mrtrix-seed42-rerun-integrity-design.md`.

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

The original coverage-driven tracking object is:

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

An optional fixed-sampling field is supported:

```yaml
tracking:
  seedwide_streamlines: 300000
  minimum_streamlines_per_target: 300
  fod_cutoff: 0.06
  min_length_mm: 10
  max_length_mm: 250
  random_seed: 1
```

When `seedwide_streamlines` is absent, the historical coverage-driven stopping
rule remains in force for backward compatibility. When it is present, every
subject and seed side generates exactly that many structurally validated
mother streamlines. `minimum_streamlines_per_target` then becomes a completion
QC threshold rather than a sampling stop trigger. A fixed-sampling unit whose
mother total is complete but whose least-covered target remains below the
threshold becomes `coverage_failed`; it must not silently generate a larger
primary tractogram because doing so would make the sampling denominator depend
on the observed target distribution.

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
  cleanup_work_cache_after_success: true
  matlab_executable: /Applications/MATLAB_R2024b.app/bin/matlab
  mrtrix_path_prefix: /usr/local/bin
```

`cleanup_work_cache_after_success` is optional and defaults to `true`. It is
written explicitly to resolved configuration but is operational rather than
scientific identity. Cleanup occurs only after the entire configured batch is
complete and all public artifacts have passed hash and structural validation.
Partial failure, coverage failure, interruption, or verification failure
preserves all preparation, seed-wide, staging, and rollback caches. Successful
cleanup moves only these tool-owned cache directories to platform Trash:

```text
work/preparations
work/seedwide
work/staging
work/rollback
```

Public tractograms plus `work/state.json`, `work/configs`, and `work/run.lock`
remain in place. Cleanup status and any pending paths are recorded in state.
The retained state is self-contained: each seed result stores the complete
seed-wide scientific identity document, preparation artifact-set hash, ordered
target keys, target counts, and hit fractions so provenance and comparisons do
not depend on cache-resident seed state.

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

The subject DWI is converted with its bvec/bval gradient table. The brain mask
is converted to MRtrix format for response/FOD estimation. The resolved source
tracking-mask NIfTI must be binary, nonempty, and on the exact native-DWI
grid; `tckgen -mask` consumes that validated NIfTI directly. A redundant
second MIF conversion is not used. The fixed response/FOD methods are:

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
In legacy coverage-driven mode, generation stops successfully only when:

```text
min(n_t for every configured target) >= minimum_streamlines_per_target
```

In fixed-sampling mode, generation stops after exactly
`seedwide_streamlines` structurally validated mother streamlines. The final
chunk request is reduced when needed so that the configured total is not
crossed. Target coverage is assessed only after the fixed total is reached;
insufficient coverage fails QC without extending the primary tractogram.

The mother streamline total is always the sum of structurally validated
completed chunk counts. The target hit fraction is:

```text
n_t / n_seedwide_total
```

Raw target counts must not be compared across subjects without this
denominator. Fixed sampling is preferred for cross-subject modelling because
every subject-side unit has the same denominator and the rarest observed
target does not determine when sampling stops.

If the maximum seed-wide total is reached before all targets meet the minimum,
the unit becomes `coverage_failed`. The report lists every deficient target,
its actual hit count, the required count, and the mother total. A
`coverage_failed` unit is not published as complete. If a final chunk would
cross the maximum, its requested size is reduced to the exact remaining
budget.

In fixed-sampling mode, `seedwide_streamlines` must not exceed
`maximum_seedwide_streamlines`. The fixed total is the effective generation
limit; `maximum_seedwide_streamlines` remains an outer configuration safety
bound and does not cause sampling beyond the fixed total.

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

The FOD reference in seed-wide identity is content-bound. The identity document
must include the completed preparation artifact hashes for `wm_fod.mif`,
`brainmask.mif`, `response_wm.txt`, and the tracking mask consumed by `tckgen`.
Chunk identity and reuse verification bind the canonical hash of this artifact
set. A path or preparation identity string alone is insufficient for reuse.

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

When a new valid configuration no longer desires a previously published
tool-owned TCK, that stale artifact is retired within the same subject
transaction. Its current hash must still match the prior ownership record; it
is first moved to rollback, restored on any transaction failure, and sent to
the platform Trash only after all desired artifacts validate. Unknown or
ownership-mismatched files are never treated as stale tool-owned artifacts.

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
`0cc923d01ec7308b79bd0e7257c21d67836d331284b81c467f0eecc223ffe873`
and explicitly recorded both the current Lead-DBS Git HEAD and the layered
content hashes. The content hashes remain authoritative when the worktree is
dirty.
Its automated results were:

- 29 focused Python tests passed;
- 77 existing normative-connectivity tests passed, one was skipped, and 27
  subtests passed;
- Python compilation and `git diff --check` passed.

The final real-data test run completed all four subject-side units:

| Subject | Seed | Mother | GPi | PPN | Minimum |
|---|---|---:|---:|---:|---:|
| `sub-SNr003` | `lh/STNSNrplus` | 50,000 | 13,583 | 5,438 | 5,438 |
| `sub-SNr003` | `rh/STNSNrplus` | 50,000 | 14,096 | 2,890 | 2,890 |
| `sub-SNr007` | `lh/STNSNrplus` | 50,000 | 12,884 | 5,974 | 5,974 |
| `sub-SNr007` | `rh/STNSNrplus` | 50,000 | 17,161 | 8,078 | 8,078 |

All twelve public files were structurally valid TCKs whose counts and hashes
matched state. Every transformed seed and cleaned target was binary, nonempty,
on the exact native-B0 grid, and had zero cleaned seed-target overlap. No
cleanup remained pending and no process exceeded its configured memory
reservation. A second unchanged run reported both preparations, all four
seed-wide units, and all twelve public artifacts as reused; it generated zero
public artifacts and left every public SHA-256, byte size, and nanosecond mtime
unchanged. Therefore the real-test gate is passed and formal validation is
authorized as the next step.

The first formal attempt exposed an external-volume conversion failure in
which nonempty binary `trackingmask.nii` inputs for `sub-SNr012` and
`sub-SNr014` produced all-zero redundant `trackingmask.mif` files, while the
same source data and the corresponding `brainmask.mif` remained nonempty.
That attempt was safely interrupted after four complete subjects. The fix is
the source-NIfTI tracking-mask contract above plus explicit binary/nonempty
input validation. Automated and real-data gates were repeated successfully
under the new preparation/tracking content identity before formal execution
was authorized to resume.
The subsequent reduced test configuration also exposed stale tool-owned
formal target TCKs that were not part of the reduced desired set. Publication
must therefore apply the transactional stale-artifact retirement rule above;
the gate additionally requires the public file set to equal the current
state's desired paths exactly. The 64 files left by the pre-fix attempt were
each matched uniquely by path and SHA-256 to a completed seed-state output,
then moved to the platform Trash. The repaired reduced test published exactly
six TCKs per subject and its second unchanged run preserved every hash, byte
size, and nanosecond mtime.

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
than once every 30 minutes unless a process exits or an error event occurs.
The CLI must continue automatically until all subjects finish, fail, or the
user interrupts it. A 100,000,000-streamline cap applies independently to each
subject and seed side.

### Controlled Seven-Subject Resume Record (2026-07-15)

At the user's request, the first 16-subject formal process, PID `91324`, was
terminated with `SIGTERM` so that its active work could be rescheduled without
discarding valid chunks. The process exited normally within four seconds, all
four active `tckgen` process groups exited, and the `sub-SNr020` and
`sub-SNr026` subject locks were released. The final committed resume
boundaries were:

| Subject | Seed | Complete chunks | Mother streamlines | Next chunk index |
|---|---|---:|---:|---:|
| `sub-SNr020` | `lh/STNSNrplus` | 465 | 23,250,000 | 465 |
| `sub-SNr020` | `rh/STNSNrplus` | 400 | 20,000,000 | 400 |
| `sub-SNr026` | `lh/STNSNrplus` | 392 | 19,600,000 | 392 |
| `sub-SNr026` | `rh/STNSNrplus` | 409 | 20,450,000 | 409 |

Incomplete files below each `inflight/` directory are not members of the
committed chunk list and are not eligible for reuse. A resumed unit must verify
every committed TCK, membership artifact, target chunk, identity, and hash
before continuing at the recorded next chunk index.

The authorized resume configuration is:

```text
/Volumes/VAL/STNSNr/config/mrtrix_seed_target_remaining7.yaml
```

It contains these subjects in exact scheduling order:

```text
sub-SNr020
sub-SNr026
sub-SNr024
sub-SNr029
sub-SNr030
sub-SNr017
sub-SNr015
```

The resume configuration changes only the batch subject list, its ordering,
and `execution.subject_workers`, which is set to `4`. Atlas, ROI, subject
inputs, tracking parameters, generation chunk size, per-side maximum,
MRtrix thread count, and tool paths remain identical to the formal
configuration. The stored and current preparation and tracking implementation
hashes matched before rescheduling. Consequently, `sub-SNr020` and
`sub-SNr026` retain their preparation and seed-wide scientific identities even
though the batch-level configuration hash changes.

After all seven subjects reach explicit terminal states, the complete
16-subject formal YAML must be run again. That reconciliation run must reuse
valid completed subjects and chunks, finish any incomplete units, update the
full-batch provenance, and produce the authoritative final status report.

The seven-subject configuration passed structural comparison against the
formal YAML and full CLI validation without warnings. Its batch configuration
hash is
`7fd139107c0904e49b9c69071b28b2be1001f191f52ec72e28ad61aacfc80bb0`.
The managed run started at `2026-07-15 01:31:41 -0700` under PID `31264`; its
append-only log is:

```text
/Volumes/VAL/STNSNr/config/run_logs/mrtrix_seed_target_remaining7_20260715T013141-0700.log
```

Startup verification confirmed that the first four subject locks belonged to
`sub-SNr020`, `sub-SNr026`, `sub-SNr024`, and `sub-SNr029`. The latter two
completed both seed sides with one 50,000-streamline chunk, were published,
and released their slots; `sub-SNr030` then completed in the same way and the
remaining subjects entered in configured order. Most importantly, the four
interrupted units resumed at their exact committed boundaries:

```text
sub-SNr020 lh: chunk 465
sub-SNr020 rh: chunk 400
sub-SNr026 lh: chunk 392
sub-SNr026 rh: chunk 409
```

No interrupted unit restarted at chunk zero. Monitoring is attached to the
active run at the approved 30-minute interval.

### All-Subject Fixed-Sampling Rerun With Corrected Subjects First (2026-07-17)

After corrected DWI preprocessing and newly approved SPM44 B0 registrations,
`sub-SNr017`, `sub-SNr020`, `sub-SNr022`, and `sub-SNr026` require new
preparation identities and new tractograms. Their prior FOD, DWI-space ROI,
chunk, membership, and published TCK artifacts are not valid scientific inputs
for the rerun. The same fixed-sampling tracking identity is applied to all 16
subjects so every subject-side primary tractogram has the same denominator.

The subject scheduling order is:

```text
sub-SNr017
sub-SNr020
sub-SNr022
sub-SNr026
sub-SNr003
sub-SNr007
sub-SNr006
sub-SNr011
sub-SNr012
sub-SNr014
sub-SNr016
sub-SNr018
sub-SNr024
sub-SNr029
sub-SNr030
sub-SNr015
```

With `subject_workers: 4`, the four corrected subjects occupy the first four
subject slots. Later subjects are admitted in the listed order as slots are
released.

The dTOR normative connectome contains 11,820,000 fibers. Strict STNSNrplus
membership contains 251,376 fibers for the left seed and 327,966 for the right
seed; their mean is 289,671 fibers per side. The approved rounded fixed sample
is therefore 300,000 accepted seed-wide iFOD2 streamlines per subject and seed
side. This is a Monte Carlo sampling count, not an estimate of the biological
axon count.

The formal rerun configuration is:

```text
/Volumes/VAL/STNSNr/config/mrtrix_seed_target_fixed300k_017_020_022_026.yaml
```

The historical filename is retained to avoid creating a second competing
formal configuration, although its subject list now contains all 16 subjects.

It uses 50,000-streamline chunks, a fixed 300,000-streamline mother total per
side, a 300-hit completion QC threshold for every one of the 18 targets, and a
2,000,000-streamline outer safety bound. The expected primary total is 600,000
mother streamlines per subject and 9,600,000 across the 16-subject batch.
Any target below 300 after its fixed 300,000-streamline mother tractogram is
reported as `coverage_failed` rather than triggering subject-specific primary
oversampling.

The implementation added the optional strict YAML field, exact fixed-total
chunk scheduling, fixed-total coverage failure semantics, and scientific
identity coverage. All 32 focused package tests passed. Read-only validation
resolved all 16 subjects, confirmed the required first-four ordering and
method-specific SPM44 transforms, reported no warnings, and produced
configuration hash
`e485d31d3890db8f9ffd731fe1bbc264fffd9e19a39563fad6e5b0047f891735`.

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
