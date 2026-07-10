# Generic Seed-Target Connectome Statistics `/goal`

## Goal Metadata

```text
Purpose: Compute target-wise structural-connectivity statistics for one seed ROI over one streamline connectome
Workspace: /Users/mojackhu/Github/leaddbs
Parent goal: none; standalone reusable fiber-core module
Authoritative specification: this document
Current branch: stnvop
Status: design_approved
Implementation status: task_3_connectome_adapter_in_progress
Current outputs: unchanged
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
- stable-ID connectome adapter: in progress;
- traversal, statistics, artifacts, CLI, and acceptance: pending.

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

## Deferred Work

- Clinical or model-weighted target analysis.
- Target-selection and multiple-comparison workflows.
- Individual-subject DWI seed-target quantification.
- Directional connectivity interpretation.
- Target-overlap reporting.
- GUI and service layers.
