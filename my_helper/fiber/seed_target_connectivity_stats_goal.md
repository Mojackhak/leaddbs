# Generic Seed-Target Connectome Statistics `/goal`

## Goal Metadata

```text
Purpose: Compute target-wise structural-connectivity statistics for one seed ROI over one streamline connectome
Workspace: /Users/mojackhu/Github/leaddbs
Parent goal: none; standalone reusable fiber-core module
Authoritative specification: this document
Current branch: stnvop
Status: implemented
Implementation status: verified_complete
Current outputs: /private/tmp/seed-target-connectivity-dtor-acceptance-20260710
Implementation language: Python
Default execution environment: Conda leaddbs
Last updated: 2026-07-10
```

## Goal And Success Criteria

Implement one project-independent module with exactly three scientific data
inputs:

1. a Lead-DBS-style target-atlas directory;
2. one seed ROI NIfTI;
3. one streamline connectome with stable canonical fiber identifiers.

For every discovered target ROI, the module must identify streamlines that
intersect both the seed and target using segment-aware voxel traversal and must
report:

```text
raw_fiber_count
seed_normalized_fraction
target_background_prevalence
connectivity_lift
connectivity_pmi
```

The implementation is complete only when the generic interface, deterministic
atlas discovery, chunked streamline traversal, exact statistic definitions,
cache/provenance contract, synthetic tests, and the default real-data
acceptance fixture all pass. No project name, anatomical structure name, VTA,
stimulation frequency, clinical scale, or outcome-model rule may be encoded in
the core implementation.

## Scope

### In scope

- Recursive discovery of target ROI NIfTIs below a target-atlas root.
- Binary and probabilistic seed/target masks.
- Per-ROI probability-threshold resolution.
- Segment-aware streamline-to-voxel intersection.
- Overlapping target ROIs with independent fiber membership.
- Chunked connectome processing.
- Target-wise descriptive connectivity statistics.
- Deterministic fiber-membership caches and provenance manifests.
- A command-line entry point and a reusable Python API.

### Out of scope

- VTA or E-field generation and sampling.
- HF/ULF or other frequency-specific logic.
- Clinical endpoints, prediction, sweet/sour weights, or outcome regression.
- Target-selection policy, hierarchical atlas workflows, or parent-child
  refinement.
- Afferent/efferent or upstream/downstream direction inference.
- Target-overlap reports.
- Spatial normalization or repair of inputs.
- Individual-subject DWI preprocessing or tractography generation.
- GUI or HTTP-service implementation.

The caller is responsible for selecting scientifically valid inputs and for
ensuring that seed, target atlas, and connectome are already expressed in the
same world-coordinate space.

## Core Data Contract

### Target atlas

The target atlas is a directory, not a single integer-label image. The loader
must recursively include every valid `.nii` or `.nii.gz` file that is located
at least one directory level below the atlas root.

It must not include NIfTI files located directly in the atlas root. This avoids
classifying atlas-level auxiliary images such as `gm_mask.nii.gz` as targets.

The loader must also ignore:

```text
hidden directories
AppleDouble files whose names begin with ._
non-NIfTI files
directory symlink cycles
```

Each target receives a stable identifier derived from its normalized relative
path with the full `.nii` or `.nii.gz` suffix removed:

```text
<atlas_root>/group_a/region_1.nii.gz -> group_a/region_1
<atlas_root>/group_b/region_1.nii    -> group_b/region_1
```

Directory names are grouping information only. The core must not infer an
anatomical role or hemisphere from names such as `lh`, `rh`, `cortex`, or
`thalamus`.

Target ROIs may overlap. A fiber may independently belong to any number of
targets. The implementation must not use winner-takes-all assignment, subtract
overlapping masks, force fractions to sum to one, or generate an overlap
report.

### Seed ROI

The seed input is one `.nii` or `.nii.gz` image. It may be binary or
probabilistic. The module operates on exactly one resolved seed mask per run.

### Connectome

The connectome adapter must provide, in a deterministic order:

```text
canonical fiber ID
ordered world-coordinate streamline points
connectome identity and source hash
```

Canonical fiber IDs must be unique and stable across chunk boundaries. The core
must not assume that streamline row number is a permanent identifier unless the
adapter explicitly establishes that contract.

## ROI Resolution

An image is binary when all finite nonzero values are equal to one within a
documented numeric tolerance. Its resolved mask is:

\[
M(u)=\mathbf{1}[x(u)>0].
\]

An image is probabilistic when its finite values lie in `[0, 1]` and at least
one value lies strictly between zero and one. Its resolved mask is:

\[
M_t(u)=\mathbf{1}[p(u)\ge t], \qquad 0<t\le1.
\]

A probabilistic image must have an explicit threshold. Threshold resolution is:

```text
target-specific override
then atlas-level target default
otherwise configuration error
```

The seed probability threshold is configured separately. Thresholds are
algorithm parameters, not additional scientific data inputs.

The resolved manifest must record source type, threshold value and source,
source hash, resolved voxel count, resolved physical volume, and resolved-mask
hash for the seed and every target.

## Segment-Aware Intersection

A streamline is an ordered point sequence:

\[
f=(p_1,p_2,\ldots,p_n).
\]

For every consecutive segment \(L_k=[p_k,p_{k+1}]\), the production algorithm
must transform the segment into the ROI voxel coordinate system and enumerate
every voxel crossed by that segment using deterministic 3D voxel traversal.

For deterministic grid-plane behavior, voxel index `i` owns the half-open cell
`[i - 0.5, i + 0.5)` on each voxel axis. The segment's final endpoint is also
evaluated explicitly. Both the reference and optimized kernels must implement
this same convention.

The intersection indicator is:

\[
I_R(f)=\mathbf{1}[f\cap R\ne\varnothing].
\]

A fiber therefore intersects an ROI even when neither original streamline
vertex lies inside the ROI but the connecting segment crosses it. ROI dilation
must not be used as a substitute for segment-aware traversal.

The implementation must process the connectome in bounded chunks. It must
accumulate whole-connectome target membership for the background denominator
and seed-plus-target membership for conditional connectivity. An optimized
implementation may use a combined target voxel lookup, provided it preserves
independent membership for overlapping targets.

## Statistics Contract

For all valid connectome fibers \(F\), seed \(S\), and target \(T\), define:

\[
F_S=\{f\in F:f\cap S\ne\varnothing\},
\]

\[
F_T=\{f\in F:f\cap T\ne\varnothing\},
\]

\[
F_{S,T}=F_S\cap F_T.
\]

Let:

\[
N_{\mathrm{all}}=|F|,\quad
N_S=|F_S|,\quad
N_T=|F_T|,\quad
N_{S,T}=|F_{S,T}|.
\]

Every target row must report the following five statistics.

### Raw fiber count

\[
\mathrm{RawCount}_{S,T}=N_{S,T}.
\]

### Seed-normalized fraction

\[
P(T\mid S)=\frac{N_{S,T}}{N_S}.
\]

### Target background prevalence

\[
P(T)=\frac{N_T}{N_{\mathrm{all}}}.
\]

### Connectivity lift

\[
\mathrm{Lift}_{S,T}=\frac{P(T\mid S)}{P(T)}.
\]

### Pointwise mutual information

\[
\mathrm{PMI}_{S,T}=\log_2\left(\mathrm{Lift}_{S,T}\right).
\]

These are streamline-sampling statistics, not estimates of biological axon
count, physiological strength, or connection direction.

If `N_S == 0`, the run is invalid. If `N_T == 0`, lift and PMI are not
estimable. If `N_T > 0` and `N_{S,T} == 0`, lift is zero and PMI is negative
infinity; serialized outputs must use an explicit status rather than an invalid
non-finite JSON number.

## Ranking

The module may provide a deterministic convenience rank, but it must not select
or reject scientific targets. Ranking order is:

```text
connectivity_lift descending
seed_normalized_fraction descending
raw_fiber_count descending
target_id ascending
```

Rows with non-estimable lift sort after estimable rows. Target selection remains
the responsibility of the caller.

## Public Interface

The reusable API is conceptually:

```python
compute_seed_target_statistics(
    target_atlas_root=target_atlas_root,
    seed_roi=seed_roi,
    connectome=connectome,
    config=config,
)
```

The CLI contract is:

```text
seed-target-connectivity validate
seed-target-connectivity run
seed-target-connectivity status
seed-target-connectivity artifacts
```

`validate` resolves the atlas and configuration without traversing the full
connectome. `run` computes the statistics. `status` and `artifacts` inspect
an existing immutable run directory.

## Configuration Contract

An illustrative configuration is:

```yaml
schema_version: 1

seed:
  probability_threshold: 0.25

targets:
  probability_threshold: 0.25
  roi_thresholds:
    group_a/region_1: 0.50

intersection:
  method: segment_aware_voxel_traversal

execution:
  fiber_chunk_size: 100000
  cache_membership: true

ranking:
  enabled: true
```

Unknown fields must be rejected. No project-specific defaults are permitted in
the reusable module.

## Artifact And Provenance Contract

Every run writes an immutable run directory containing:

```text
config_resolved.yaml
target_catalog.csv
target_connectivity.csv
target_ranking.csv
seed_connected_fiber_ids.npy
target_fiber_membership.npz
input_resolution_qc.csv
analysis_manifest.json
artifact_index.csv
```

`target_connectivity.csv` must include:

```text
target_id
target_group
relative_path
source_value_type
probability_threshold
threshold_source
target_status
n_all_fibers
n_seed_fibers
n_target_fibers
n_seed_target_fibers
raw_fiber_count
seed_normalized_fraction
target_background_prevalence
connectivity_lift
connectivity_pmi
rank
```

The manifest and artifact index must record configuration hashes, source-file
hashes, connectome identity, ordered fiber-ID hash, algorithm version, chunk
size, resolved-mask hashes, artifact hashes, code provenance, and timestamps.

Membership-cache identity must include:

```text
connectome geometry identity
ordered canonical fiber-ID identity
seed resolved-mask identity
target-atlas resolved-mask identity
intersection algorithm and version
```

A changed seed may reuse target membership only when connectome and target
identities are exact. A changed target atlas may reuse seed membership only when
connectome and seed identities are exact.

## Failure And Isolation Rules

- An invalid seed or a seed with no connectome support fails the run.
- A malformed target NIfTI or unresolved probabilistic threshold fails
  validation rather than being silently skipped.
- A valid target that becomes empty after thresholding is recorded as
  `empty_after_threshold` and does not enter traversal or ranking.
- A target with no connectome support is recorded as
  `no_connectome_support`; other targets continue.
- Processing order and output rows must be deterministic across chunk sizes and
  repeated runs.

## Implementation Plan

1. Add strict typed configuration and Lead-DBS atlas-directory discovery.
2. Add binary/probabilistic ROI resolution with deterministic target IDs.
3. Add connectome adapter interfaces and stable fiber-ID validation.
4. Implement a brute-force reference segment-intersection kernel for tests.
5. Implement optimized chunked 3D segment-aware voxel traversal.
6. Add independent seed/target membership caches and statistic aggregation.
7. Add atomic run storage, artifact indexing, CLI commands, and provenance.
8. Add synthetic equivalence tests and the default real-data acceptance run.

Current implementation progress:

- strict typed configuration: complete;
- deterministic atlas discovery and ROI resolution: complete;
- stable-ID connectome adapter: complete;
- reference and optimized segment-aware traversal: complete;
- independent membership caches, statistics, and ranking: complete;
- atomic immutable artifacts and provenance: complete;
- reusable API and four-command CLI: complete;
- default real-data acceptance and completion audit: in progress.

Acceptance performance note:

- when both seed and target memberships are absent, the engine traverses one
  combined ordered mask lookup and then splits the independent cache outputs;
- repeated API calls may reuse an exact read-only ROI resolution cache, but
  membership-cache identities remain independently bound to seed or atlas;
- the first dTOR attempt was interrupted before artifact publication after it
  exposed redundant traversal/resolution work; no partial run was accepted.

Documentation must be updated before each later implementation phase changes
production code.

## Test Plan

### Atlas discovery and ROI resolution

- Include `.nii` and `.nii.gz` files from every non-hidden subdirectory depth.
- Exclude root-level NIfTIs, including atlas helper files such as
  `gm_mask.nii.gz`.
- Exclude AppleDouble and hidden-directory files.
- Preserve duplicate basenames in different directories as different target
  IDs.
- Resolve binary masks with `> 0` and probabilistic masks with `>= threshold`.
- Reject probabilistic masks without an explicit threshold.
- Record thresholded-empty targets without aborting valid peer targets.

### Geometry and statistics

- Detect a segment crossing an ROI when both source vertices are outside it.
- Reject a segment that approaches but does not cross an ROI.
- Assign one fiber independently to multiple overlapping targets.
- Produce identical membership and statistics from brute-force and optimized
  kernels.
- Produce identical output across multiple chunk sizes.
- Verify all five statistics against hand-calculated synthetic fixtures.
- Verify exact zero-background, zero-seed-target, and zero-seed semantics.

### Default real-data acceptance fixture

The reusable module has no project-specific defaults. Its repository acceptance
fixture is nevertheless fixed to the following available data:

```text
target atlas: STNSNr-connected regions
seed ROI: lh/STNSNrplus and rh/STNSNrplus as two independent runs
connectome: dTOR-985 Full (Elias 2024)
```

The fixture must run the same generic public interface used by any other atlas,
seed, and connectome. It must not invoke a project wrapper or branch on these
names. The two seed files are tested separately because the generic API consumes
exactly one seed NIfTI per run; the core must not union them or infer hemisphere
semantics from their paths.

Acceptance requires:

- deterministic discovery of all eligible subdirectory `.nii`/`.nii.gz`
  targets while excluding root-level NIfTIs;
- nonzero seed-connected dTOR fiber support;
- one complete statistics row per valid target;
- exact agreement of sampled real fibers between reference and optimized
  segment-intersection kernels;
- finite fraction, prevalence, and lift wherever their denominators are valid;
- deterministic ranks and identical artifact hashes on an unchanged rerun;
- no source-tree or legacy-output mutation.

## Completion Audit

Before changing status to `implemented`, audit every explicit input, algorithm,
metric, artifact, failure state, test, and acceptance requirement in this
document against current code and generated evidence. Passing narrow unit tests
does not prove completion of the real-data fixture or artifact/provenance
contract.

### Verified completion evidence

The completion audit passed on 2026-07-10 against package code provenance:

```text
git commit: 840665d1602b3aa2b4b0b8869bedce952c03655e
package SHA-256: 9b8fa462dd134185ac6d9783978d34e64913a5339b3d78ecb89591601bdf0289
Conda environment: leaddbs
synthetic/integration suite: 64 passed; 1 opt-in real test skipped
opt-in dTOR acceptance: 1 passed in 187.692 seconds
successful acceptance peak RSS: 3,125,428,224 bytes
successful acceptance swap count: 0
```

The successful acceptance reused exact content-addressed target and left-seed
membership caches produced by the immediately preceding full dTOR traversal.
That first traversal ran for 628.98 seconds and had already atomically published
the left run and both membership caches before it was interrupted during the
next seed stage. The successful acceptance then verified those cache hashes,
completed the right seed, reran both public API calls, and performed sampled
reference/optimized equivalence.

Real-data evidence:

```text
acceptance report:
/private/tmp/seed-target-connectivity-dtor-acceptance-20260710/acceptance_report.json

left run:
/private/tmp/seed-target-connectivity-dtor-acceptance-20260710/runs/8e9731dd9875f7080987eb1b8d800ab607b68b8c8a2d348456356cea23ded543

right run:
/private/tmp/seed-target-connectivity-dtor-acceptance-20260710/runs/8bf62ccc72dfc667b0bb8f406ea37faa699f588ec0bfcffedb8c268abfbe483f
```

| Requirement group | Authoritative evidence | Audit result |
|---|---|---|
| Exactly three scientific inputs and generic API | `pipeline.py`, `test_pipeline_cli.py`; both fixture seeds call `compute_seed_target_statistics` independently | passed |
| Strict configuration and unknown-field rejection | `config.py`, `config.schema.json`, `test_config.py` | passed |
| Recursive deterministic atlas discovery and exclusions | `atlas.py`, `test_atlas_roi.py`; real fixture discovered 106 eligible targets | passed |
| Binary/probabilistic resolution, threshold precedence, empty targets, hashes, and physical volume | `roi.py`, `test_atlas_roi.py`, both `input_resolution_qc.csv` files | passed |
| Stable canonical IDs and bounded HDF5 chunks | `connectome.py`, `test_connectome.py`; real metadata records 11,820,000 fibers and 1,032,794,665 points | passed |
| Segment-aware reference and optimized traversal | `traversal.py`, `test_traversal.py`; 24 sampled real fibers agreed exactly across all 106 targets | passed |
| Overlapping target independence and no winner-takes-all policy | multi-target bitset tests, including 70-target multiword coverage | passed |
| Five exact statistics and failure semantics | `statistics.py`, `test_engine_statistics.py`; hand calculations, zero joint, zero background, and zero seed are covered | passed |
| Deterministic ranking without scientific selection | ranking tests and `deterministic_ranks=true` in the acceptance report | passed |
| Independent seed/target cache reuse and identity | `cache.py`, cache-reuse/tamper tests; right run reused target membership and both unchanged reruns reused exact caches | passed |
| Nine immutable artifacts, atomic publication, hashes, timestamps, and code provenance | `artifacts.py`, `test_artifacts.py`; both real run directories contain and verify all nine required files | passed |
| Four-command CLI | `cli.py`, executable `pipelines/seed-target-connectivity`, subprocess integration tests | passed |
| Real left/right dTOR support | left seed: 251,376 fibers; right seed: 327,966 fibers | passed |
| Complete real target rows and valid denominators | 106 rows per seed; 103 estimable lift rows, 2 empty targets, and 1 no-support target per run | passed |
| Unchanged rerun hashes and source isolation | `identical_rerun_hashes=true`, `source_state_unchanged=true`; output root is outside the repository | passed |
| No project/anatomy/clinical logic in reusable core | production-core coupling scan; project names occur only in the explicit acceptance fixture/test | passed |

Both real run manifests and artifact indexes were reverified after acceptance.
The worktree was clean, `git diff --check` passed, and no remote mutation was
performed.

## Deferred Work

- Clinical or model-weighted target analysis.
- Target-selection and multiple-comparison workflows.
- Individual-subject DWI seed-target quantification.
- Directional connectivity interpretation.
- Target-overlap reporting.
- GUI and service layers.
