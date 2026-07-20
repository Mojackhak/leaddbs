# Four-Model Shared Exposure And Performance Refactor Plan

> **Purpose.** Remove scale-dependent physical-exposure recomputation and make
> configured all-scale execution use the available CPU, memory, and storage
> bandwidth efficiently without changing model classification.
> **Workspace.** `/Users/mojackhu/Github/leaddbs`
> **Parent goal.** `my_helper/stnsnr/four_model_yaml_core_refactor_plan.md`
> **Implementation plan.**
> `my_helper/stnsnr/dual_frequency_core_decoupling_implementation_plan.md`
> **Task 17 decision record.**
> `my_helper/stnsnr/task17_design_decisions.md`
> **Historical implementation plan.**
> `my_helper/stnsnr/four_model_yaml_core_refactor_implementation_plan.md`
> **Scientific specifications.** `my_helper/stnsnr/model_summaries/`
> **Current branch.** `stnvop`
> **Status.** `design_documented`; `code_audit_complete`;
> `literature_review_complete`; `threshold_policy_change_authorized`;
> `implementation_in_progress`; `synthetic_acceptance_passed`;
> `production_configuration_validated`;
> `corrected_production_main_completed`;
> `canonical_publication_and_postprocess_accepted`;
> `configured_production_outputs_published`;
> `sensitivity_extensions_deferred_by_user`.
> **Last updated.** 2026-07-19

---

## Authority And Scope

This document is the current performance-refactor contract for the configured
four-model runtime. It overrides earlier cache, scheduling, and the explicitly
reopened threshold-comparator statements where they conflict with the rules
below. Except for that comparator, it does not change the source resolver,
prediction classifier, branch-role state machine, final-model realization, or
inferential definitions.

The user's 2026-07-17 correction reopens three scientific boundaries.
Direct-voxel and normative-fiber E-field values below tau are inactive and all
other values are active. Candidate counts below Coverage are excluded and all
other counts are included. Reference-component values below the selected tau
are inactive and all other values enter overlap. Support-QC retains its
documented strict direction and pPAM activation uses `p(A) > 0.5`. Exact
E-field, Coverage, and reference-tau boundary values are included. Task 17
remains open until a corrected production rerun is complete.

This comparator policy is limited to the enumerated model-threshold comparators. It
does not alter formal null-tail counting, hard minimum sample/feature counts,
identity checks, array bounds, or numerical-tolerance validation.

The user's 2026-07-16 portability decision also replaces the earlier local-
filesystem-signature and checksum-free cache proposal. The target uses one
portable SHA-manifest format for locally produced and directly copied entries.
Each process verifies every used entry once before reuse. This simplification
changes cache identity and integrity mechanics but does not change scientific
arrays.

The semantic token `inclusive_threshold_v1` is recorded in scientific provenance
and every derived support, overlap, candidate, or binary-activation cache path.
Comparator-independent raw physical exposure may be reused, but an artifact
created under a different comparator policy cannot authorize a derived artifact
or resume segment.

The refactor covers:

```text
reference direct voxel
add-on direct voxel
reference normative fiber
add-on normative fiber
```

It separates the runtime into a scale-independent physical-preparation layer
and a scale-dependent statistical-analysis layer. Physical preparation includes
canonical E-fields, bilateral voxel exposure, bilateral fiber exposure,
localization-jitter exposure, and OSS/pPAM activation. Statistical analysis
includes clinical joins, weights, scores, source/final resolution, formal
resampling, sensitivity statistics, and reports.

Canonicalized left E-fields are themselves shared v2 physical-cache entries.
They are not worker-local durable state; their semantic identity binds source,
transform, interpolation, canonical space, and producer version so voxel and
fiber workers do not repeat the same MATLAB transform.

No currently running process is interrupted or migrated. Existing production
outputs remain read-only. Implementation status and remaining gates are stated
explicitly below.

### Document authority stack

Implementation must read the documents in this order:

1. `four_model_yaml_core_refactor_plan.md` is the sole current `/goal` and owns
   overall scope, success criteria, and completion status.
2. `dual_frequency_core_decoupling_design.md` owns the approved generic-core
   architecture, scientific state machine, and package boundaries.
3. This document owns the reopened shared-exposure, threshold-policy, cache,
   scheduling, memory, storage, and performance contract.
4. `dual_frequency_core_decoupling_implementation_plan.md`, specifically open
   Task 17, is the ordered code-and-acceptance checklist that implements this
   contract.
5. The four direct-voxel/normative-fiber files under `model_summaries/` are the
   scientific wording surface and are updated with code only after Task 17's
   parity and boundary fixtures pass.

`four_model_execution_plan.md`,
`four_model_yaml_core_refactor_implementation_plan.md`, and completed Tasks
1-16 are historical evidence where the current `/goal`, approved design, or
this performance contract supersedes them.

## Confirmed Scientific Invariants

### Scale equality

Every configured scale remains an equal engineering unit. Scale identity may
affect clinical rows and outcomes, but it must not cause the same stimulation
program or connectome geometry to be recomputed.

Physical exposure cache identity must exclude:

```text
scale ID
endpoint ID
outcome values
baseline values
branch role
final-model ID
run ID
worker count
retry count
task order
```

### Direct-voxel bilateral exposure

For subject `i` and right-canonical voxel `v`, direct voxel retains its current
definition:

\[
X^{\mathrm{voxel}}_{i}(v)
=
\frac{
E_{R,i}(v)+E_{L\rightarrow R,i}(v)
}{2}.
\]

The right field and nonlinearly transformed left field are sampled once on the
same canonical voxel grid. The bilateral voxel vector is then reused by every
scale and every downstream direct-voxel stage that references the same physical
stimulation unit.

### Normative-fiber bilateral exposure

Normative fiber also retains its current definition. The implementation must
first calculate the peak separately on each side and only then average the two
fiber-level values:

\[
E^{\mathrm{peak}}_{R,i,f}
=
\max_{u\in f} E_{R,i}(u),
\]

\[
E^{\mathrm{peak}}_{L\rightarrow R,i,f}
=
\max_{u\in f} E_{L\rightarrow R,i}(u),
\]

\[
X^{\mathrm{fiber}}_{i,f}
=
\frac{
E^{\mathrm{peak}}_{R,i,f}
+E^{\mathrm{peak}}_{L\rightarrow R,i,f}
}{2}.
\]

The following alternative is forbidden because maximum and averaging do not
commute:

\[
\max_{u\in f}
\frac{E_{R,i}(u)+E_{L\rightarrow R,i}(u)}{2}.
\]

The reusable object is therefore the bilateral **fiber exposure row obtained
after the two side-specific peaks have been averaged**, not a voxelwise
bilateral field sampled along the fiber.

### Continuous-dose rule

For direct voxel and normative fiber, tau defines Coverage and the candidate
support. Once a feature belongs to the selected support, the subject's
continuous E-field value enters scoring even when that individual value is
below tau. The optimization must retain continuous values for every retained
feature and must not replace them with binary threshold indicators.

Add-on reference-active overlap exclusion remains part of the add-on model.
The shared raw add-on exposure is an upper-bound input; exact overlap exclusion
is applied before the branch-specific add-on resolver and scoring.

## Current Implementation Diagnosis

The target runtime is scientifically functional, but its physical preparation
is still organized around endpoint tasks rather than reusable stimulation
units.

Observed implementation facts:

1. `workflow/executor.py` uses `ThreadPoolExecutor`. Python-bytecode-heavy and
   h5py-call-heavy work cannot rely on that pool for scalable multi-core
   execution; h5py serializes its API calls with the process-wide PHIL lock.
   Compiled kernels that release the GIL remain a separate measurable thread
   class rather than being assumed equivalent to h5py or Python loops.
2. `workflow/planner.py` creates a fiber sidecar task for every endpoint.
3. `runtime/input_provider.py::_matrix_for_binding()` allocates an
   endpoint-named matrix and traverses `endpoint -> subject -> connectome
   chunks`.
4. `connectome.py::iter_chunks()` reopens the HDF5 source and reconstructs or
   validates geometry during every endpoint scan.
5. NIfTI samplers are cleared after each subject, preventing bounded in-run
   reuse.
6. Large arrays are copied, written, and cryptographically checksummed
   repeatedly during publication, materialization, and run-artifact recording.
7. The executor waits for a complete runnable wave before releasing newly
   unblocked tasks.
8. Formal replicate loops are predominantly serial inside one long task.
9. Direct voxel recomputes support and feature weights across the full
   tau/Coverage grid even though several exposure-only operators are identical.
10. `workflow/executor.py` constructs a new executor for every runnable wave.
    The current two-scale test fixture has 81 tasks in 11 waves, so a direct
    replacement with a spawned pool per wave would add 11 interpreter and
    module-import cycles while preserving the barrier.
11. `ExecutionContext` contains `RLock`-holding registry/provider objects and
    each submission receives a complete outcome snapshot. This boundary is not
    spawn-serializable and transfers substantially more state than the direct
    dependency envelopes required by a task.
12. `workflow/run_store.py` performs synchronous state writes and repeatedly
    reads, validates, and rewrites the complete artifact index. Its `RLock` is
    process-local and therefore cannot protect a shared index from independent
    spawned writers.
13. The global `workers` value currently controls both outer workflow
    concurrency and nested activation work. `backends/activation/ossdbs.py`
    creates an internal executor, so the integer Python-work count can become
    `< W x W + 1` before external solver threads are counted.
14. The fiber sampling hot loop resolves transformed paths, consults samplers,
    and can repeat NIfTI validation for every connectome chunk. Subject-level
    global sampler clears can evict data still needed by another active task.
15. `connectome.py::iter_chunks()` reads all four HDF5 rows, constructs a
    point-sized expected-ID array, and revalidates canonical IDs on every scan,
    although exposure calculation consumes only the three coordinate rows.
16. Complete canonical fiber axes are repeatedly allocated and published as
    explicit `1..N` arrays. For dTOR, one int64 copy of that implicit axis is
    about 94.6 MB before endpoint and activation duplication.
17. `cache/store.py` and the prepared/selected-exposure publishers introduce
    full-payload copies, repeated flushes, and repeated reads. A prepared memmap
    is commonly written once as work data and again through `np.save()` before
    downstream final-axis views create further copies.
18. `backends/statistics.py` ranks, residualizes with `lstsq`, and correlates
    one feature at a time in Python. Fiber scoring repeatedly validates the full
    axis, sorts signed weights, and builds reporting hashes inside observed,
    formal, sensitivity, and pPAM loops.
19. Formal, pPAM, and jitter loops remain serial with production
    permutation/bootstrap replicate counts `< 10,001` and jitter replicate
    counts `< 1,001`. Their
    current retained arrays and fold operators would be multiplied by the
    process count if they were naively submitted to spawned workers.
20. OSS preparation rebuilds the same filtered connectome and mapping per
    physical row, repeats toolchain attestation, issues small per-fiber HDF5
    reads, and records O(number of fibers) Python/JSON cache items for a row.

For the current 28-scale STNSNr catalog, the repeated fiber preparation is
approximately:

```text
reference rows: 28 x 16 = 448
add-on rows:     28 x 13 x 3 matrices = 1092
total:           1540 subject-row connectome scans per connectome
```

The unique physical rows are only:

```text
reference-only component: 16
combined reference component: 13
combined add-on component: 13
total: 42
```

Therefore the current data contain a theoretical repeated-row reduction of:

\[
\frac{1540}{42}\approx36.7.
\]

This ratio is not a guaranteed wall-clock speedup. It identifies avoidable
physical work before candidate reduction, process parallelism, and storage
effects are considered.

### Measured storage layout relevant to the design

A read-only header inspection on 2026-07-16 established the actual layout of
the three configured connectomes. The values below are implementation inputs,
not general atlas assumptions:

| Connectome | File bytes | `fibers` shape | HDF5 chunk | Filter |
|---|---:|---:|---:|---|
| PPMI 85 | 686,332,653 | `4 x 62,728,157` | `4 x 4095` | gzip |
| MGH-USC HCP 32 | 4,291,383,620 | `4 x 396,595,508` | `4 x 4095` | gzip |
| dTOR-985 | 11,558,307,963 | `4 x 1,032,794,665` | `4 x 4095` | gzip |

For dTOR, one logical four-row scan represents about 16.5 GB of uncompressed
float32 values. Copying the three coordinate rows represents about 12.4 GB,
and constructing the current float32 expected point-ID vector across the scan
adds about 4.1 GB of cumulative allocation traffic. Because gzip operates per
HDF5 chunk, range design must follow the stored chunk boundaries and measured
point count; a fixed number of fibers is not an adequate work estimate.

The stored chunk spans all four rows, so selecting `fibers[0:3, ...]` can still
require HDF5 to read and decompress the complete `4 x 4095` chunk. The audited
three-row fast path therefore claims removal of application-level fourth-row
copies, expected-ID allocation, and repeated validation, not an unmeasured 25%
disk-I/O reduction. A coordinate-only repacked cache is considered only after
benchmarking and requires its own versioned producer/parity contract.

## Evidence Base And Engineering Interpretation

The plan uses primary publications and official implementation documentation.
These sources support design principles; they do not replace project-specific
numerical parity and benchmark evidence.

1. Blumofe and Leiserson analyze a randomized work-stealing scheduler for fully
   strict computations with dependencies; their bounds relate total work and
   critical-path length for that model. The result motivates removing global
   wave barriers, but it does not prove this project's central bounded,
   resource-aware queue. The project does not claim to implement their exact
   randomized-deque algorithm. [Blumofe and Leiserson, 1999](https://doi.org/10.1145/324133.324234)
2. Python documents that macOS uses `spawn`, that it starts a fresh interpreter,
   and that process arguments must be picklable. It also documents worker
   initializers and long-lived process pools. The project interpretation is one
   persistent pool, importable worker entry points, compact pure-data commands,
   and parent-owned mutable state. [Python multiprocessing](https://docs.python.org/3.11/library/multiprocessing.html#contexts-and-start-methods)
   and [ProcessPoolExecutor](https://docs.python.org/3.11/library/concurrent.futures.html#processpoolexecutor)
3. h5py advises independent file opens in each reader process and documents
   that its PHIL lock serializes h5py API calls inside one process. The HDF
   Group documents that filtered datasets read and decompress complete chunks
   and that chunk-cache effectiveness depends on the access pattern. The
   project interpretation is worker-local read-only handles, chunk-aware
   sequential ranges, bounded simultaneous readers, and locality within one
   connectome.
   [h5py parallel HDF5](https://docs.h5py.org/en/stable/mpi.html) and
   [h5py threading](https://docs.h5py.org/en/stable/threads.html) and
   [HDF5 chunking](https://support.hdfgroup.org/documentation/hdf5-docs/advanced_topics/chunking_in_hdf5.html)
4. Joblib's official documentation describes oversubscription when process
   workers invoke OpenMP/BLAS thread pools and exposes explicit inner-thread
   limits. The project interpretation is that `workers` is one global CPU
   budget and every Python, BLAS, and OSS child must consume tokens from it.
   [Joblib parallelism](https://joblib.readthedocs.io/en/stable/parallel.html#avoiding-over-subscription-of-cpu-resources)
5. NumPy documents reproducible parallel-stream construction through
   `SeedSequence`. This supports explicit stream identity, but it does not make
   a new stream scheme numerically equivalent to the existing runtime. The
   refactor therefore preserves the current jitter replicate-keyed identity and
   the current continuous formal/bootstrap/pPAM schedules; it never substitutes
   worker ID, completion order, or block assignment for scientific RNG state.
   NumPy's compatibility policy further requires the same BitGenerator, seed,
   call sequence and arguments, build, environment, and machine for strict
   stream compatibility; changing scalar/vector call shape is not presumed
   equivalent. [NumPy parallel random generation](https://numpy.org/doc/2.4/reference/random/parallel.html)
   and [NumPy compatibility policy](https://numpy.org/doc/2.4/reference/random/compatibility.html)

No cited source proves that 12 workers, a particular range size, or a 64-GiB
managed budget is optimal for this workload. Those remain benchmark hypotheses
and must pass the acceptance matrix below.

The implementation-environment snapshot verified during this review is Python
3.11.15, NumPy 2.4.6, h5py 3.16.0, and HDF5 1.14.6 in the `leaddbs` Conda
environment; both `joblib` and `threadpoolctl` are available. The implementation
must re-record these versions before benchmarking and may use the underlying
standard-library/thread-control mechanisms directly rather than introducing a
new scheduling dependency solely because its documentation is cited.

## Two-Layer Target Architecture

### Layer 1: scale-independent physical preparation

The core preparation layer is keyed by subject, phase/program binding, frequency
class, physical component grouping, coordinate-space rule, connectome, and
producer version. It never receives a scale, outcome, endpoint status, or final
model. A shared OSS row belongs here only after the axis-equivalence gate has
passed. If the gate fails, the historical per-final-axis OSS producer remains a
final-linked downstream task and is not relabeled as Layer 1.

It produces:

```text
canonical side-specific E-field references
bilateral direct-voxel exposure rows
bilateral normative-fiber peak-exposure rows
model-specific maximal support: direct-voxel support and fiber Omega_max
shared localization-jitter schedules and jittered physical exposure rows
PASS-only shared OSS/pPAM activation rows on the accepted maximal axis
ordered subject/voxel/fiber axes and row indexes
```

Expensive preparation is workflow-demanded: base exposure is required for
observed analysis; jitter preparation is included only when the requested
workflow reaches jitter sensitivity; OSS/pPAM preparation is included only
when activation sensitivity is requested. Base, jitter, and a PASS-branch OSS
producer remain scale-independent and run once per physical identity. A
FAIL-branch OSS producer deliberately remains final-axis-linked downstream.

### Layer 2: scale-dependent and final-linked execution

The analysis portion joins clinical rows and creates indexed views into prepared
resources. Direct voxel selects subject and voxel rows/columns. Normative fiber
selects subject and fiber rows/columns. In the PASS branch, no Layer-2 task
rescans physical inputs. In the FAIL branch, the explicitly retained
per-final-axis OSS producer is the only final-linked physical producer in this
layer; ordinary statistical tasks do not rescan E-field files, connectome
geometry, jittered geometry, or OSS simulation merely because a scale changed.

It computes:

```text
baseline/outcome nuisance designs
full/fold weights and signed feature selection
scores and held-out predictions
source and prediction status
branch role and unique final realization
formal permutation/bootstrap
jitter and OSS endpoint statistics
reports
```

### Target computation DAG

The physical and statistical layers must be separated:

```text
study/configuration
  -> resolve unique physical stimulation units
  -> prepare reusable bilateral voxel exposure rows
  -> prepare one shared reduced fiber exposure per connectome
  -> prepare requested jittered exposure rows
  -> [PASS only] prepare requested shared OSS/pPAM rows on Omega_max
  -> build endpoint row views
  -> run outcome-dependent observed models
  -> resolve source and final model
  -> [FAIL only] run the historical per-final-axis OSS/pPAM producer
  -> run final-linked formal/sensitivity/report tasks
```

The target reusable physical tasks are:

```text
resolve_stimulation_units
prepare_canonical_bilateral_voxel_exposure
prepare_connectome_maximal_candidate_union
prepare_shared_fiber_exposure
prepare_shared_jitter_schedule
prepare_shared_jitter_exposure
prepare_shared_oss_activation  [PASS branch only]
```

Endpoint tasks consume row references or indexed views:

```text
build_endpoint_row_view
run_observed_grid
resolve_source
realize_final
run_formal
run_sensitivity
run_report
```

No endpoint task may reopen and rescan the complete connectome merely because
the clinical scale changed.

### Distinct voxel and fiber execution contracts

Voxel and fiber reuse the same scheduler and physical-identity layer, but they
are different numerical models and must not be collapsed into one preparation
kernel:

| Property | Direct voxel | Normative fiber |
|---|---|---|
| Physical input | Right and canonicalized-left NIfTI E-fields | The same side-specific E-fields plus connectome point geometry |
| Required operation | Sample both fields on a canonical voxel grid, then average voxel values | Take each side's maximum along each fiber, then average the two side-specific maxima |
| Natural work unit | Physical row and exact-grid voxel tile | Connectome point-count/byte range containing complete fiber boundaries |
| Dominant reusable state | Decompressed float32 NIfTI, grid identity, affine/interpolation lookup | Point offsets, implicit canonical axis, chunk-aware geometry range, side-specific running peaks |
| Candidate reduction | Voxel support on the configured direct-voxel grid | Exact `Omega_max` derived from normative-fiber tau/Coverage grids |
| Threshold rule | Exact tau, Coverage, and reference-tau boundaries are included | Exact tau, Coverage, and reference-tau boundaries are included |
| Main I/O risk | Repeated `.nii.gz` decompression and full-volume validation | Repeated gzip HDF5 chunk decompression and geometry/ID validation |

The pre-Task-17 code baseline is intentionally recorded without treating the
two models as interchangeable:

| Path | Current implementation | Authorized target |
|---|---|---|
| Direct voxel | E-field exposure and Coverage currently exclude their exact boundaries | Include exact tau and exact Coverage boundaries |
| Normative fiber | E-field exposure and Coverage currently exclude their exact boundaries | Include exact tau and exact Coverage boundaries |
| Reference-active overlap | The shared interaction path currently excludes the exact selected tau | Include the exact selected reference tau |
| pPAM binary activation | The current implementation admits the probability boundary at `0.5` | `p(A) > 0.5` |

These current-state statements are migration evidence, not target operators.
Task 17 changes the three strict predecessor boundaries to inclusive behavior
and adds explicit boundary-inclusion fixtures for every predicate in the right
column.

The voxel path groups only E-fields with exactly matching shape and affine. It
may reuse base world-to-voxel coordinates and interpolation neighbors within
that grid identity, but different grids remain separate. The fiber path binds a
`SamplingPlan` before entering the connectome loop and performs the two
side-specific running maxima while a geometry range is resident.

The production threshold grids remain model-family specific. The direct-voxel
grid is 150, 180, 200, 220, 250, and 300 V/m, with 200 V/m evaluated first. The
normative-fiber grid is 200, 350, 400, 450, 600, and 800 V/m, with 400 V/m
evaluated first. The minimum configured Coverage remains five subjects for both
model families.

Exact-threshold values are scientific boundary fixtures. Both model families
include exact tau and Coverage values, and reference-active overlap includes
the exact selected reference tau. Strict `<` remains in use for the separately
defined inverse-direction support-QC threshold tests.

The corrected normative-fiber production profile assigns PPMI85 as the unique
`formal` connectome and MGH/dTOR as `sensitive`. Every configured
`fold_candidate_fibers_min` is one, so each LOOCV fold must retain at least one
candidate fiber. The independent `n_subjects_min: 12` requirement is retained unchanged.
The corrected formal invocation runs the main workflow only; jitter and
OSS-DBS are deferred to a separate user-authorized invocation.

The completed corrected formal lineage must publish one sensitivity base for
each realized primary or fallback final. On the current 28-scale catalog this
means 112 bases: 28 each for reference voxel, reference fiber on the unique
formal connectome, add-on voxel, and add-on fiber on the unique formal
connectome. The 112 sensitive-connectome endpoints intentionally have no final
and therefore publish no sensitivity base. Every published base must retain the
same ordered four-entry configuration-source identity tuple for the study JSON
and three YAML inputs. The publisher must materialize this tuple before the
per-endpoint loop; a one-shot iterator that is exhausted after the first base is
invalid. Acceptance requires 112 readable bases, 112 unique endpoint IDs,
exact agreement with realized-final decisions, four source identities in every
base, and resolvable final-artifact references. This is required so a later
jitter or OSS-DBS extension can validate and reuse the completed parent without
rerunning observed, resolver, or final-model work.

Production acceptance on 2026-07-17 used run
`task17-main-v7-inclusive-ppmi-formal-20260717`. Its final manifest is
`completed`. The plan contains 1512 tasks: 1428 completed and 84 expected
`not_run_delta_inputs_invalid` skips, with no failed task. The 224 final
decisions contain 105 primary finals, 7 fallback finals, and 112
sensitive-connectome endpoints with no final. The corrected checkpoint contains
112 bases and four ordered configuration-source identities in every base. The
112 base endpoint IDs exactly match all primary and fallback final decisions,
and all 1548 base final-artifact references resolve into the 6773-entry artifact
index. A completed-only resume created a third execution segment without
changing any completed-task timestamp, then republished the corrected
checkpoint. The complete 449-test dual-frequency suite passed. No jitter,
OSS-DBS, or combined-extension service ran in this lineage.

The subsequent threshold-grid rerun keeps all accepted Task 17 contracts and
changes only the two model-family tau grids and the normative-fiber
pre-specified tau. The direct-voxel pre-specified tau remains 200 V/m. The
normative-fiber pre-specified tau is 400 V/m. Coverage grids, score fractions,
selected-count minima, hard computability limits, formal resampling counts,
connectome roles, and threshold-boundary inclusion remain unchanged. The rerun
uses a new lineage, runs through formal outputs, and excludes jitter and
OSS-DBS. A later explicitly authorized sensitivity extension may reuse the
completed parent lineage.

## Shared Physical Stimulation Units

A physical stimulation unit is resolved from structured study/model inputs,
not from a scale or output filename. It includes the subject, configured
stimulation binding, frequency class, component grouping, canonical-space rule,
and E-field source paths needed to reproduce the existing bilateral exposure.

At minimum the runtime distinguishes:

```text
reference-only reference-frequency exposure
combined-condition reference-frequency exposure
combined-condition add-on-frequency exposure
```

Two clinical endpoints that point to the same stimulation sources and
parameters reuse the same physical row. A scale with missing clinical data uses
an indexed subset of the shared rows; it does not create a new exposure matrix.

Subject inclusion remains endpoint-specific. Reuse never adds a subject with
missing clinical inputs to an endpoint analysis.

## Exact Maximal Fiber Candidate Union

### Grid-derived upper bound

The runtime derives, rather than hard-codes:

\[
\tau_{\min}=\min(\mathrm{tau\ grid}),
\qquad
C_{\min}=\min(\mathrm{Coverage\ grid}).
\]

For the current normative-fiber profile only:

\[
\tau_{\min}=400\ \mathrm{V/m},
\qquad
C_{\min}=5.
\]

This profile accepts the configured Coverage boundary. Only counts below `5`
are excluded.

For a connectome and physical exposure family, define the maximal candidate
union over the maximal eligible physical subject cohort:

\[
\Omega_{\max}
=
\left\{
f:
\sum_i
\mathbf{1}\!\left[X_{i,f}\not<\tau_{\min}\right]
\not< C_{\min}
\right\}.
\]

Any fiber outside `Omega_max` cannot enter any configured tau/Coverage cell:
higher tau cannot increase its suprathreshold count, and higher Coverage cannot
relax the required count. Removing it is therefore an exact prefilter, not an
approximation.

For add-on, raw add-on exposure may define this upper bound because
reference-active overlap exclusion can only remove or zero exposure. It cannot
create a false-negative candidate outside the raw upper bound. Exact overlap
exclusion is still applied before endpoint- and branch-specific Coverage.

### One connectome pass

The first implementation does not require a persistent spatial index. It must:

1. iterate over each connectome in disjoint deterministic fiber ranges;
2. read each range once per cache schema version;
3. evaluate all unique physical exposure rows for that range;
4. calculate minimum-grid Coverage for each physical exposure family;
5. retain only fibers in its exact `Omega_max`;
6. write continuous row values and canonical fiber IDs for the retained range;
7. concatenate ranges in canonical fiber-ID order.

Across workers, disjoint ranges together constitute one complete connectome
scan. A worker must not reread the whole connectome for each endpoint or scale.

### Endpoint and fold masks without geometry rescans

An endpoint's exact subject cohort is an indexed view of the shared exposure.
For each tau, calculate full-cohort counts once:

\[
n_f(\tau)=\sum_i\mathbf{1}[X_{i,f}\not<\tau].
\]

For LOOCV held-out subject `h`, derive training Coverage by subtraction:

\[
n_{f,-h}(\tau)
=
n_f(\tau)
-
\mathbf{1}[X_{h,f}\not<\tau].
\]

All Coverage-grid masks include the exact configured count; only counts below
Coverage are excluded. Fold-specific candidate support remains exact, but no
fold reopens the connectome or resamples an E-field.

## Scale-Independent Jitter And OSS Preparation

### Localization jitter

The physical jitter layer preserves the current deterministic identity:
`binding_id + frequency_class + subject_id + hemisphere + replicate_index +
replicate_seed`. It keeps canonical side-specific E-fields fixed and applies
the deterministic coordinate translation while sampling. It then derives both
model-family exposure forms without clinical input:

```text
direct voxel:
  average right and transformed-left voxel fields

normative fiber:
  peak each side along each fiber, then average the two side-specific peaks
```

The same schedule and physical rows are reused by every scale. The later scale
analysis independently applies its realized final support, fits weights,
computes scores/predictions, and reports jitter stability. A jitter replicate
never reuses another scale's outcome-dependent map or selected signed features.

### OSS/pPAM preparation universe

The existing per-final-axis OSS producer remains authoritative for every
unproven allocator-relevant class until the bounded go/no-go decision matrix
defined below covers that class. The proposed shared branch defines:

\[
F_{\mathrm{OSS,prepare}}
=
\Omega_{\max},
\]

where `Omega_max` is the exact minimum-tau/minimum-Coverage maximal fiber union
defined above. Before migration, every distinct allocator-relevant class must
simulate the same physical row on its historical final axis and on `Omega_max`.
Each class must yield axon-state/count mismatch count `< 1` and probability
`absolute_difference < accepted_probability_tolerance` for all common fibers.

The gate has two accepted outcomes:

```text
PASS:
  generate OSS/pPAM once per physical row on Omega_max
  select endpoint final columns by canonical ID

FAIL:
  retain the existing per-final-axis request/cache/artifact contract
  record the axis-dependent allocator/RNG evidence
  do not claim scale-independent OSS simulation reuse
```

Each exact allocator-relevant equivalence class receives an immutable
`OSSAxisEquivalenceDecision`. Its identity binds allocator and solver/toolchain
versions, connectome and cache schema, the tested final/`Omega_max` axis pair,
physical-row identity, RNG contract, comparison fields, and accepted
probability tolerance. One decision authorizes only that exact class. Global
PASS scheduling requires a bounded decision matrix that covers every distinct
class used by the run; an absent, changed, or unproven class retains FAIL
behavior until its newly authorized proof passes.

Neither branch simulates the complete normative connectome. A future
fiber-keyed allocator may reopen a failed gate only through a separately
accepted change.

In the PASS branch, every realized endpoint final has no canonical ID missing
from the prepared axis:

\[
\left|
F_{\mathrm{final}}
\setminus
F_{\mathrm{OSS,prepare}}
\right| < 1.
\]

The analysis layer then selects the exact final columns by canonical fiber ID and
then performs fold-local weights, signed selection, scoring, nuisance fitting,
and OSS sensitivity statistics. A missing final fiber in the prepared OSS axis
is a preparation-contract failure.

For add-on models in the PASS branch, OSS preparation stores raw add-on
activation on `F_OSS,prepare`; in the fallback branch it stores the historical
per-final-axis row. Reference-active overlap exclusion is applied later using
the endpoint's selected matched-reference source in either branch. This
preserves branch-specific semantics without assuming the shared simulation gate
will pass.

The existing right-canonical OSS geometry rule, left-to-right transformation,
`max_probability_union` and the ten-sample probability definition remain
unchanged. The target binary activation rule is strict `p(A) > 0.5`; equality
at `0.5` is inactive.

## Reusable Resource Inventory

### Required shared resources

| Resource | Reuse boundary | Required rule |
|---|---|---|
| Canonical right and transformed-left E-fields | subject/stimulation unit | Load once per active cache residency/worker batch; reopen only after a recorded eviction. |
| Bilateral direct-voxel exposure | physical stimulation unit | Average voxel fields once and reuse across scales. |
| Bilateral normative-fiber exposure | connectome plus physical stimulation unit | Peak each side first, average peaks second, reuse across scales. |
| Connectome geometry | connectome | Read lengths, offsets, IDs, and point ranges once per producer shard. |
| Canonical feature axes | brainmask/connectome | Publish one ordered axis; endpoint views reference it. |
| Shared clinical vectors | scale plus locked endpoint binding | Load baseline/outcome once and reuse across voxel/connectome families. |
| Endpoint subject-index views | exact ordered subject set | Store indices, not copied exposure matrices. |
| Tau exceedance tensor | exposure family plus subject axis | Compute once for the complete tau grid. |
| Full/fold Coverage masks | exposure family plus subject axis | Derive folds by subtraction. |
| Raw exposure ranks | exposure family plus subject axis/fold | Reuse before scale-specific nuisance residualization. |
| LOOCV fold indices | ordered subject axis | Reuse across model families. |
| Permutation/bootstrap schedules | subject axis, seed, and replicate contract | Generate once; statistics still refit independently. |
| Add-on raw exposure and overlap inputs | physical add-on/reference inputs | Reuse between no-delta and adjusted branches. |
| DeltaReferenceScore | reference final plus model family | Calculate once and reuse by the matched add-on branch and its sensitivities. |
| Reporting axes/labels | feature-axis identity | Reuse IDs, affine/header, density lookup, and labels. |
| Jitter perturbation schedule | binding/frequency/subject/hemisphere/replicate-index/replicate-seed contract | Generate once without clinical input. |
| Jittered voxel/fiber exposure | physical jitter row plus model domain | Reuse across scales; endpoint statistics remain independent. |
| OSS/pPAM activation | go/no-go-selected axis contract | PASS reuses one `Omega_max` row; FAIL retains one row per historical final axis. |

### Optional second-stage resources

After the one-pass producer is correct, a persistent connectome sampling index
may store the trilinear neighbor voxel indices and weights for each fiber point.
This converts repeated interpolation into indexed gathers and weighted sums.
It is optional because it can be large and must be benchmarked against the
one-pass stream implementation.

If left-to-right deformation is performed inside this runtime rather than by
the upstream E-field producer, the deformation sampling coordinates may also be
cached once per canonical grid. They must not be recomputed per scale.

### Resources that must remain endpoint-specific

The following depend on clinical outcome or selected model state and cannot be
shared merely because exposure is identical:

```text
scale-specific nuisance residualization
outcome-dependent voxel/fiber weights
patient scores and held-out predictions
MAE/RMSE prediction classification
source and final-model records
DeltaReferenceScore across different model families
branch-specific inferential statistics
permutation/bootstrap refits and selected signed feature sets
```

Within one endpoint, optimized operators may still be reused when their exact
mathematical inputs match.

## Grid And Weight Computation Optimization

### Exposure-only operators

For each unique subject axis, calculate the full tau exceedance tensor and
Coverage masks once. Do not rebuild these for each scale, Coverage value, or
LOOCV fold.

### Outcome-dependent operators

For one endpoint and fold, feature weights are independent of Coverage once the
maximal candidate axis is fixed. The implementation should compute weights once
over the endpoint's maximal valid feature set, then apply the exact cell masks
for every tau/Coverage grid cell.

This optimization must be applied to direct voxel as well as normative fiber.
It must preserve:

```text
training-fold-only weights
training-fold-only candidate masks
finite/valid-weight intersection
deterministic feature order
cell-specific score and prediction calculation
```

No full-sample ranking, sign, weight, or selected-feature set may leak into a
held-out fold.

### Vectorized statistics contract

The shared partial-Spearman entry point dispatches complete finite blocks to a
rank-aware multi-RHS implementation. It ranks the outcome, all feature columns,
and nuisance columns with average ties, fits the outcome residual once, and
fits all feature residuals in one matrix solve. If any value is nonfinite or
the ranked nuisance design is not estimable, it uses the retained columnwise
finite-pair implementation. Tests must prove numerical parity and must verify
that a complete block uses two linear solves rather than one solve per feature.

`backends/statistics.py` must gain a finite-data fast path that operates on
feature blocks rather than calling Python and `np.linalg.lstsq` once per
feature. The safe implementation sequence is:

1. apply exact average-tie ranking down the subject axis for a feature block;
2. residualize all right-hand sides for one nuisance design in one rank-aware
   multi-RHS solve, using the same rank threshold as the current scalar path;
3. calculate centered dot products, norms, and correlations by block;
4. preserve the existing scalar path for nonfinite columns and explicit edge
   cases;
5. cache only fold-specific nuisance operators and invariant clinical-vector
   residuals whose exact design identity matches.

The implementation may not assume full-rank nuisance data, silently change tie
handling, or downcast a float64 statistical operator to float32. Tests cover
ties, constants, rank deficiency, nonfinite values, feature-block boundaries,
and multiple block sizes against the current scalar implementation.

### Direct and fiber grid workspaces

Direct voxel constructs threshold/support counts once per tau and derives fold
counts by subtracting the held-out row. Baseline-only LOOCV predictions are fit
once per endpoint/fold. Selected-cell publication consumes the scan workspace
for invariant threshold/Coverage operators and baseline predictions. Direct
voxel deliberately recomputes selected-cell ranking and weights; normative
fiber may reuse only its exact endpoint/fold maximal-support weight cache and
must reapply the selected cell's candidate and finite-weight masks.

The direct-voxel workspace is branch-local and binds the exact outcome and
nuisance plan. It may reuse only the tau threshold operator, full Coverage
counts, and nuisance-only held-out predictions. It must recompute each cell's
candidate mask, outcome-dependent weights, continuous score, model fit, and
classification. Selected-cell publication reuses the same operator and
baseline but retains arrays from a fresh selected-cell evaluation, so the grid
scan cannot leak a retained selected model.

Normative fiber represents tau exceedance and candidate membership as a
bit-packed or block-streamed tensor whose memory estimate participates in
admission. It does not scan the complete matrix for every tau/Coverage/fold.
Sensitive-connectome fixed-cell workspaces cover only requested cells rather
than building an unused full grid.

A `PrevalidatedFiberScoreWorkspace` owns only the ordered axis, invariant
exposure-finiteness validation, and preallocated top-k scratch. Candidate masks,
finite-weight masks, signed weights, and their ordering are outcome-, replicate-,
and fold-specific and must be recomputed for every statistical call; observed
state may not enter a null replicate or a held-out fold. Null-statistic calls return only scores, support flags, and
required counts; observed/final publication still produces complete selected
IDs and reporting metadata. Any partial selection must reproduce the current
boundary-tie rule based on weight and canonical fiber ID.

### Formal, pPAM, and sensitivity workspaces

Permutation, bootstrap, pPAM permutation, and spatial jitter use fixed replicate
blocks that do not depend on worker count. Jitter preserves its existing
replicate-keyed schedule. Formal, bootstrap, and pPAM preserve the existing
single continuous `default_rng(seed)` sequence: the parent either pregenerates
the historical schedule with the same method-call sequence and argument shapes
and lends immutable index slices, or saves BitGenerator states at exact
historical call boundaries. A generic draw-count split is invalid. An
`advance`/jump implementation is allowed only with the historical BitGenerator
and with NumPy version, BitGenerator class, build/environment/platform
fingerprint, and call-plan schema pinned in provenance, plus full-call-pattern
byte mismatch count `< 1`. A cross-environment resume reruns parity before it
may claim byte identity.
Replacing that sequence with new per-replicate `SeedSequence` streams is outside
this refactor.

Reduction follows canonical replicate index and a fixed tree independent of
worker assignment. Candidate-set, sign, selection/support-count,
exceedance-count, and p-value-numerator mismatch count is `< 1`. Floating moments use the fixed
tree and must satisfy `absolute_difference < existing_tolerance` against the
serial reference; if a
field requires bitwise historical equality, the parent retains the historical
one-replicate-at-a-time accumulation order for that field. Bootstrap still
refits every replicate; adjusted add-on inference still refits its matched
reference and must not reuse an observed `DeltaReferenceScore`.

Read-only fold operators are created once as parent-managed run-scoped scratch
memmaps and reopened by workers. They are not scientific artifacts, are not
pickled or rebuilt per replicate worker, and have crash-recoverable cleanup.
Bootstrap scratch is feature-blocked and admitted by measured bytes. A pPAM
`retain_arrays=false` path avoids creating `N x F` fold weights and `N x N`
retained matrices when a null replicate consumes only rho and attrition state.
The observed fit retains the complete historical output contract.

Sensitivity tasks use a task-scoped workspace for exposure, outcome, baseline,
feature axis, and nuisance operators. Overlap masking is applied by block or
view instead of a full-matrix `np.where` copy. Jitter blocks retain only the
active perturbed exposure; invariant clinical vectors and axes are loaded once.
Replicate-specific overlap, nuisance results, and `DeltaReferenceScore` are
never cached as invariants or reused across replicates.

## Sampling, Axis, And Publication Contracts

### Sampling hot-loop contract

Before a voxel tile or fiber range starts, the provider builds an immutable
`SamplingPlan` containing canonical E-field paths, sampler descriptors, shape,
affine/grid identity, translations, frequency-group maximum rules, and portable
source content SHA values from the validated source manifest. Device, inode,
mtime, and absolute path are runtime locators only and never enter scientific
identity. Source SHA is provided by the validated source manifest and verified
before local production; direct cache reuse compares the recorded content
identity without reopening the source. Inside the connectome range/chunk loop,
the following operations are forbidden:

```text
Path.resolve, stat, or payload hash
NIfTI open, full-volume validation, or decompression
left-transform cache lookup or producer lock
sampler construction or global sampler-cache clear
```

Each physical-row plan descriptor is built once. While one geometry range is
resident, a worker acquires sampler leases for only a byte-budgeted row batch,
evaluates it, and releases those leases before admitting the next batch. It may
not pin private ndarray samplers for all physical rows simultaneously. Compressed
NIfTI data may be canonicalized once to a versioned float32 NPY/raw memmap, then
reopened read-only so the OS page cache can serve multiple workers. A failed
single-flight preparation is delivered to all waiters and may be retried only
through the explicit producer state machine.

### Connectome fast-path and canonical axis

For each `(connectome semantic ID, source content SHA, cache schema)`, a cold
full-audit path validates `idx`,
the fourth fiber row, point boundaries, canonical IDs, dtype, chunk layout, and
compression. Audit state from one connectome cannot authorize another. After
that audit, the exposure hot path materializes only coordinate rows `0:3` into
application memory, uses precomputed point offsets, and does not allocate
point-sized expected-ID or redundant `arange` vectors. Raw compressed-chunk
reads/decompression remain separately measured because the stored chunks span
all four rows.

The complete parent axis `1..N` is represented by
`OneBasedRangeAxis(count=N)`. Selected canonical IDs use validated `id - 1`
positions. An explicit full ID array is published once only when a legacy
artifact boundary requires it; endpoint and OSS rows reference the shared axis
identity instead of copying it.

Ranges are balanced by cumulative point count and estimated uncompressed bytes.
They never split a fiber and choose boundaries that minimize, but cannot always
eliminate, partially shared `4095`-point HDF5 chunks. The performance record
separates logical fiber-point coverage from raw chunk reads/decompression,
includes bounded boundary overlap, median/max range bytes, and work skew. A cold
integrity test must still reject corrupted fourth-row IDs, `idx`, or fiber
boundaries.

### Single-write publication

Large-array producers write final-format files or range shards into one unique
same-parent staging directory. A hashing writer calculates each
`payload_sha256` while writing final bytes. After flush, close, and structural
validation, the producer writes one `manifest.json` and atomically renames the
complete directory to its semantic path. It does not write a work memmap and
pass it through a second `np.save()`/merge copy. A cache hit is decided before
allocating a full staging payload.

Endpoint/final selection is an immutable logical `IndexedArrayView` containing
a shared parent/shard path, axis identity, and ordered row/column indexes. It is
not an ordinary zero-copy NumPy fancy-index view and is not a copied
`selected_exposure.npy`: kernels gather only bounded column blocks into scratch
and may not call `np.asarray()` on the complete logical view. An external tool
that requires a contiguous file declares and accounts for an explicit
materialization boundary. Run artifacts and OSS rows otherwise share the view
and axis. The parent process is the only RunStore writer; it maintains an append
journal or in-memory index with periodic atomic snapshots instead of parsing
and rewriting the complete JSON index for every task.

Every process performs full manifest, semantic SHA, payload SHA,
presence/size, and structural-header validation on first use of an entry. A
process-local verified set suppresses repeat payload hashing for later tasks in
that process. Directly copied bytes and locally produced bytes follow the same
first-use rule.

## Portable Cache Contract

### One entry, one manifest

The complete cache state machine is:

```text
local miss
  -> acquire one-producer lock
  -> write final files into same-parent staging while calculating payload SHA
  -> write manifest last
  -> structurally validate
  -> atomically rename the complete directory

first lookup in a process
  -> validate semantic SHA and manifest
  -> validate every declared payload SHA
  -> validate file presence/size and structural headers
  -> add semantic SHA to the process-local verified set

later lookup in that process
  -> validate the requested structural contract
  -> reuse without repeating payload SHA

direct copy
  -> copy the complete entry to its final semantic directory
  -> rely on the same first-lookup validation
```

There is no device/inode/mtime identity, no separate generation ID, no
checksum-free mode, importer, incoming area, machine ID, installation marker,
or persistent verification database. One `manifest.json` describes the
complete entry. For shards, it lists strictly ordered,
nonoverlapping axis intervals with missing-range count `< 1`; duplicate,
reordered, overlapping, missing, or undeclared files fail closed. A crash leaves
only a producer staging directory, which resume ignores. A partial direct copy
fails validation but is not deleted or moved automatically.

### Portable identity and layout

```text
<cache_root>/shared_exposure_v2/<kind>/<semantic_sha256>/
  manifest.json
  data.npy or ordered shard files
```

Canonical JSON binds stable study/configuration IDs, physical-row identity,
frequency class, model domain, canonical grid/connectome content SHA, ordered
axis IDs, source content SHA values, producer/version, and scientific parameter
profile. Tau/Coverage support and `Omega_max` also bind the ordered cohort,
exact grids, and `inclusive_threshold_v1`. PASS OSS binds `Omega_max`; FAIL OSS
binds the historical final axis. Device, inode, mtime, absolute paths, scale,
endpoint, outcome, run, workers, and task order are excluded.

SHA-256 of that canonical JSON is `semantic_sha256`. The manifest stores the
canonical JSON and each relative file's byte count, `payload_sha256`, schema,
dtype, shape, ordered axes, units, space, producer version, and completed
status. Absolute source locations may appear only as provenance and cannot
change `semantic_sha256`.

The public `--force` control rebuilds into a new staging directory and replaces
only through the same atomic-install contract. Historical cache entries require
explicit schema conversion or producer rebuild before they may be copied into
the portable cache tree.

## Sensitivity Checkpoint And Extension Runs

Every realized final writes `sensitivity_base.json` before a main run may claim
checkpoint completion. The record binds the immutable parent run/model IDs,
scale, final branch and role, selected source, subject/outcome/nuisance axes,
shared base-exposure semantic ID, final artifacts, source-content identities,
`Omega_max` and OSS gate state when applicable, producer/schema versions, and
RNG schedule identity. No durable reference may point into scratch.

A new process may request jitter, OSS, or other final-linked sensitivity work
through an extension-only DAG. It creates a separate run lineage and publishes
below `<model_set_id>/extensions/<extension_id>/`; it never appends mutable task
state to a valid parent run. With a complete checkpoint, observed, resolver,
and final-model rerun count is `< 1`.

If the parent run or any required main-chain artifact is missing, explicit
rebuild mode accepts the complete normal-run inputs, creates a new parent
lineage, runs the missing chain through final realization, emits a new
`sensitivity_base.json`, and then starts the extension. It does not repair a
partially deleted lineage. A missing `study_base.json` is rebuilt by an
explicit project-owned converter command before the generic runtime starts.

Each extension process applies the normal first-use cache verification rule.
The parent checkpoint, final artifact, and used portable cache entries must all
validate before any sensitivity task starts. Missing physical source with no
prepared jitter or OSS cache produces `missing_sensitivity_source`. An exact
prepared cache may support statistics even when the original physical source
is unavailable.

Extension resume restores valid completed extension tasks, reruns
failed/running/missing tasks, and re-evaluates dependency-derived skips. It may
change only accepted resource provenance; parent scientific identity and
extension scientific parameters remain fixed.

## Parallel Execution And Resource Scheduling

### Process-level parallelism

Python-bytecode-heavy and h5py-call-heavy preparation must use processes, not
the current single-process thread pool. A compiled kernel that releases the GIL
may use a separately declared thread resource class only after measured parity,
utilization, and oversubscription acceptance under the same global ledger.
The public n_jobs-like control remains `execution.workers`. Its current
production value in `config/four_model_v1/workflow.yaml` is `3`; `workers=12`
is an acceptance scenario, not a new default. In the target runtime the value
is a global CPU-slot ceiling. It does not justify twelve endpoint threads that
serialize on one HDF5 handle, and it does not specify CPU affinity or physical
core IDs.

On macOS, production workers use a `spawn` multiprocessing context. A parent
process sends only compact task descriptors and paths. It never pickles a
multi-gigabyte NumPy matrix or shares an open h5py handle with a child. Each
fiber-range worker opens the connectome once, reads only its assigned ranges,
and writes only its assigned temporary range.

One persistent process-pool generation serves a fault-free run. The parent compiles
indegree/reverse-edge tables once and submits a pure-data `WorkerCommand` that
contains the task, direct dependency envelopes, resource allocation, paths,
and small configuration. A worker initializer reconstructs its registry,
provider, read-only cache handles, and bounded local sampler cache. Mutable
RunStore state, artifact-index state, gates, and retry decisions remain in the
parent.

Numerical-library limits must be applied before worker imports initialize BLAS
or OpenMP, then verified in each worker. Every Python process in the initial
pool remains at one numerical-library thread for its full lifetime:

```text
OMP_NUM_THREADS=1
MKL_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
VECLIB_MAXIMUM_THREADS=1
```

Together with worker-side thread-count verification and the global ledger,
these settings bound modeled numerical-library oversubscription. The initial implementation does not
dynamically raise an initialized Python worker's BLAS thread count. OSS/MATLAB
subprocesses receive their own explicit thread allocation and may not inherit an
unbounded host default. A future multithreaded native Python resource class
requires separate scoped-thread-control and restoration tests.

The executor owns one global resource ledger:

```text
cpu_process_slots
memory_bytes
connectome_io_slots
external_solver_slots
internal_parallelism
```

A task starts only when all required resources are available. This enables
bounded concurrency without launching an uncontrolled set of memory-heavy
matrices or external solvers. Only the benchmark matrix may establish whether
the target runtime escapes the current one-core serialization on each stage.

`cpu_process_slots` means total host CPU capacity, not only Python process
count. For all active tasks, the sum of granted Python baseline slots, extra
BLAS/OpenMP threads, and OSS/MATLAB solver threads must remain
`< execution.workers + 1`. `external_solver_slots` separately limits expensive
solver instances/licenses; it does not grant CPU outside the global ceiling.

Task resource declarations are scheduling metadata, not scientific
configuration. Effective stage concurrency is:

\[
\min(\mathrm{workers},\ \mathrm{stage\ cap},\ \mathrm{memory\ cap},\
\ \mathrm{I/O\ or\ solver\ cap}).
\]

No task may create a nested pool outside this ledger. A Python worker consumes
one CPU slot. A task that coordinates a multithreaded external solver holds the
solver's complete CPU grant, and those tokens remain unavailable to the outer
queue until every child thread/process exits.

### Stage-specific work units

```text
canonical E-field preparation:
  parallel by independent physical subject/stimulation unit

connectome exposure preparation:
  parallel by disjoint fiber ranges; each range evaluates all physical rows

jitter preparation:
  parallel by binding/frequency/subject/hemisphere/replicate blocks; base E-fields and schedules
  are read-only shared inputs

OSS/pPAM preparation:
  parallel by independent subject/program/side rows with a separate external
  solver-slot limit

endpoint observed modeling:
  parallel by endpoint/model/connectome after shared exposure is ready

formal permutation/bootstrap:
  parallel by deterministic replicate blocks, then reduce in replicate order
```

Subject bootstrap retains every deterministic with-replacement draw in the
requested replicate axis. If a valid draw makes its sample-specific nuisance
design non-estimable, that draw is explicit attrition rather than a task-level
failure: candidate membership remains measurable, but weights, signs,
selection, and support receive no contribution. The runtime must not redraw or
silently condition on estimability. It records the exact replicate and reason,
publishes finite and non-estimable replicate counts, and reports
`completed_with_nonfinite_replicates`. A non-estimable original nuisance design
or any input, identity, axis, provider, or provenance violation remains fatal.

Long monolithic tasks must be split into bounded units; otherwise a 12-worker
executor still uses one CPU core.

Initial stage ceilings for a 12-worker run are benchmarking defaults, not
public scientific parameters:

```text
lightweight endpoint analysis: process_count < 13
dTOR fiber-range preparation: process_count > 5 and process_count < 9
voxel/jitter exposure preparation: process_count > 3 and process_count < 9
formal replicate blocks: process_count < 13
OSS external rows: limited separately by measured solver RAM/CPU demand
```

The scheduler may reduce concurrency when memory or storage is limiting, but it
must record the reason. It may not silently reduce a compute-bound 12-worker run
to one active process.

### Persistent ready queue

The executor must submit a newly unblocked task as soon as capacity is
available. It must not wait for every task in the previous runnable wave to
finish. Endpoint failure remains isolated according to the existing state
machine.

The parent performs work-conserving dynamic dispatch across same-class ready
items. Completion of one fiber range, endpoint, or replicate block immediately
frees its tokens and admits the next item to an idle worker. Final reduction
always sorts by canonical fiber ID, endpoint ID, or replicate index so
scheduling order cannot change results.

The in-flight queue is bounded rather than pre-submitting an entire wave.
Priority favors short high-fan-out prerequisites and critical-path items, then
data locality: finish ready work for one resident connectome/grid before
interleaving another large source. Locality is subordinate to dependency and
resource correctness; it may not starve an independent endpoint.

A standard `ProcessPoolExecutor` cannot target a specific initialized worker.
Therefore initial locality claims are limited to global source grouping and
shared memmap/OS-page-cache reuse; worker-local sampler hits are best effort and
are measured, not assumed. Per-worker actor queues are introduced only if a
benchmark proves affinity is necessary and their failure/recovery semantics are
accepted separately.

### Persistence, cancellation, and resume

Workers return immutable results to a parent-only persistence path. Fail-fast
cancels work that has not started, releases its reservations, and records why
running work could not be cancelled. External/HDF5 task classes expose a
heartbeat and timeout. Automatic retry is limited to tasks explicitly declared
idempotent and transient-safe; the retry preserves seed, semantic identity,
and target path.

A timed-out or cancelled running producer does not release CPU/memory/I/O tokens
until the parent proves its worker/subprocess has terminated, revokes the
producer lease, and quarantines its temporary output. A hard timeout in
Python/h5py work recycles the complete process-pool generation and classifies
every in-flight lease before any replacement starts. A separately supervised
external solver subprocess may terminate without replacing an otherwise
healthy Python pool, but its coordinator retains tokens until child exit and
quarantine are proven. Stale locks and orphaned temporaries have an explicit
recovery test. A replacement producer may not overlap the old writer on the
same semantic target.

Hard worker termination or `BrokenProcessPool` ends that pool generation. A
supervisor may create a new persistent generation after invalidating every old
worker lease and classifying in-flight tasks as incomplete. Only declared
idempotent/transient-safe tasks are requeued with unchanged identity; all other
tasks fail closed. Fault injection verifies hard exit, generation restart, and
requeue behavior. The one-pool-creation performance gate applies to fault-free
benchmark runs.

Resume has exactly three gates. First, the current study-base JSON content SHA
must match the value recorded when the run root was created. Second, the ordered
content SHA values of the workflow, direct-voxel, and normative-fiber YAML files
must match; paths are ignored. Third, a task-state JSON is reusable only when it
exists, parses, declares `completed`, and contains a decodable `result` object.
Every failed, running, skipped, missing, malformed, or result-incomplete task is
executed again or has its gate re-evaluated.

Repository code SHA, derived configuration hashes, scientific-configuration
hash, plan hash, resolved-configuration text, service identity, producer
identity, artifact metadata, artifact location, and artifact payload hashing do
not reject resume. Code SHA remains provenance only. Cache and artifact readers
may still perform the validation needed when a new task actually consumes a
payload, but that validation is not a run-opening or completed-task restoration
gate.

After worker-count invariance is proven, CPU, memory, I/O, solver, and scratch
limits are execution provenance rather than scientific identity. A resume may
lower `execution.workers` or memory admission without changing the run's
scientific compatibility. Every execution segment records the effective
resource settings used.

The resource-only override whitelist is exactly:

```text
execution.workers
CPU/BLAS/solver stage caps within that global ceiling
managed memory and connectome-I/O admission limits
external solver instance limit
heartbeat/timeout values
storage.scratch_root
```

Each resume appends an execution-segment manifest containing the code and
resource provenance used by that segment. Those fields are audit records and
do not add a fourth resume gate.

The implemented contract passes 418 dual-frequency tests and 224 parameterized
subtests, including direct checks for all three gates and for audit-only code,
plan, path, and derived-configuration changes.

For add-on fiber DeltaReference, two distinct parents must remain explicit.
The augmented add-on prepared parent proves that every locked reference ID is
present in deterministic connectome order and supplies the aligned exposure
columns. The matched reference prepared parent reproduces the locked reference
selected-axis hash. Recomputing the reference selected-axis hash against the
augmented add-on parent is invalid because the two parent axes intentionally
have different identities. The DeltaReference DAG therefore carries both
prepared records to the builder.

This two-parent contract passes 419 dual-frequency tests and 224 parameterized
subtests.

No completed outcome or durable artifact reference may depend on a scratch URI.
When `storage.scratch_root` changes or prior scratch is missing, the parent
invalidates only incomplete scratch-dependent work and deterministically rebuilds
required fold/interpolation workspaces from durable artifacts before admitting
downstream tasks. Resume-with-new-scratch-root is an acceptance test.

### Memory-aware admission

The scheduler combines the global worker ceiling with task memory estimates.
Admission requires `projected_available_after_admission > required_reserve`,
reduces swap risk, and avoids allocating one full endpoint-specific fiber memmap
per worker. Shared matrices are read-only memmaps; endpoint inputs are indexed
views. Zero new swap remains an observed acceptance condition expressed as
`swap_delta_bytes < 1`, not a guarantee inferred from admission estimates.

At every runtime preflight, regardless of installed or currently available RAM,
the initial operating budget is calculated rather than assumed:

```text
required_reserve = max(16 GiB, 20% of physical RAM)
normal_managed_budget = min(64 GiB, max(0, currently_available - required_reserve))
shared resident/cache target = min(32 GiB, two thirds of normal_managed_budget)
active working-set budget = the remaining managed budget
```

The reserve is only for the OS, filesystem-cache fluctuation, and unmodeled
allocation variance. Expected MATLAB/OSS RSS, decompression buffers, and child-
process working sets are charged to task `memory_bytes`; they may not be hidden
in the reserve. Normal admission requires
`task_memory_bytes < normal_managed_budget`; otherwise the task remains pending
or runs alone under a separately measured explicit override that still
satisfies `projected_available_after_admission > required_reserve` and
`swap_delta_bytes < 1`.

Preflight estimates are not trusted for the full task lifetime. The parent
periodically reconciles measured process-tree RSS, currently available memory,
charged shared memory, external-solver RSS, and outstanding grants. New
admission pauses when measured headroom violates the strict reserve predicate;
the event and hysteresis state are recorded before admission resumes.

RAM is used to eliminate I/O and duplicate parsing, not to duplicate endpoint
matrices:

```text
keep canonical E-field samplers in a bounded shared/LRU cache
keep connectome lengths, offsets, canonical IDs, and active geometry ranges hot
keep interpolation lookup arrays and shared exposure memmaps read-only
use OS page-cache sharing or multiprocessing shared memory across spawned workers
represent tau exceedance and candidate masks compactly
pass row/column indexes instead of copied NumPy arrays
flush shared producer outputs once after ordered completion
```

Because macOS workers use `spawn`, Python object inheritance is not a sharing
mechanism. Large arrays must be reopened as read-only memmaps or attached by an
explicit shared-memory descriptor. Pickling a full exposure or connectome array
into each worker is a contract violation.

Jitter preparation is block-streamed. Its deterministic schedules, base
geometry, interpolation operators, and currently active replicate block may be
resident, but all configured replicates are not materialized in RAM at once.
Completed blocks are atomically published and their memory tokens are released
for the next block. OSS rows use the same bounded producer/consumer pattern.

Low RAM utilization alone is not a defect. The acceptance target is useful
concurrency without swapping or duplicating multi-gigabyte exposure matrices.

### Storage behavior

The first target is elimination of repeated reads, not unbounded concurrent
reads from the same external volume. Connectome workers read disjoint ranges.
Each worker writes a final range shard exactly once. The parent atomically
publishes a small ordered shard manifest; it does not copy shards into a second
monolithic payload. Downstream `IndexedArrayView` reads the logical concatenated
array. A contiguous NPY required by an external boundary is an explicit,
measured materialization rather than part of normal publication.

Each reader process opens its own read-only HDF5 handle. Preflight records
dataset dtype, shape, chunks, compression, raw chunk-cache settings, source
filesystem, and measured sequential throughput. The scheduler restricts
simultaneous readers when additional readers reduce aggregate throughput or
cause repeated decompression/cache eviction. Because every open dataset owns
its raw chunk cache, configured per-reader cache bytes are charged to memory
admission rather than treated as free filesystem cache.

Chunking is RAM-adaptive and deliberately coarse. Preflight calculates the
bytes required by connectome coordinates, lengths, offsets, IDs, physical
exposure rows, and worker scratch space:

```text
if geometry_bytes < shared_resident_budget:
  load geometry once into read-only shared memory/memmap
  let workers consume disjoint in-memory fiber ranges

otherwise:
  use large sequential ranges sized by actual point count and byte estimate
  never split fibers and minimize partially shared HDF5 boundary chunks
  process every physical exposure row while each range is resident
```

The default target for an out-of-core range is measured in hundreds of MiB to
several GiB, not tiny fixed fiber counts. The exact size is chosen from the
calculated `normal_managed_budget`, `required_reserve`, worker count, and
connectome point density. A range is reduced whenever required to preserve that
reserve and `swap_delta_bytes < 1`.

Chunk count is minimized subject to those memory and concurrency constraints.
The scheduler chooses the fewest, largest safe ranges; it does not create tiny
ranges merely to match the worker count. While one range is resident, the
producer evaluates every configured physical exposure row, the model-specific
candidate indicators, and all scale-independent derivatives that require that
geometry. It then writes one final range shard before releasing the
geometry. Endpoint, scale, tau, Coverage, branch, and LOOCV-fold fan-out occurs
from the prepared arrays and may not trigger another raw-connectome read.

No resident range is reread for a different scale, tau, Coverage value, branch,
or LOOCV fold. The model-specific maximal candidate union and all configured physical
rows are computed before releasing that range. Read-ahead and double buffering
may overlap loading the next large range with computation on the current one,
but must not create multiple full geometry copies.

Local-SSD staging is deferred until measurements show that storage, rather than
serialization or duplicate scans, is the remaining bottleneck.

An optional non-scientific `storage.scratch_root` may place decompressed NIfTI,
range workspaces, and OSS temporary work on a measured fast local volume. Final
publication still creates its temporary sibling on the destination filesystem
so atomic rename never depends on cross-filesystem behavior. Preflight checks
scratch capacity, records throughput, and provides crash-recoverable cleanup.

## Planner And Artifact Changes

The planner must move physical preparation above endpoint fan-out. A 28-scale
run should contain one producer set per physical exposure/connectome identity,
not 28 copies of the same producer.

Endpoint task artifacts reference:

```text
shared exposure path
ordered feature axis
ordered row-index view
endpoint clinical vectors
endpoint-specific derived results
```

They do not republish the complete exposure matrix. Run-local artifact indexes
may reference the shared file without copying it.

Jitter publication is block-oriented. One block stores a deterministic range of
replicate physical exposure and references invariant feature axes and base
exposure. It contains no clinical vectors. Layer-2 statistics load their
endpoint clinical workspace once and do not publish a complete feature-ID,
overlap, or selected-exposure payload for every replicate. A completed block is
durable before its memory reservation is released.

Block storage preserves the existing `JitterReplicateEvidence` contract through
per-replicate immutable views/references. Each replicate still identifies its
physical exposure, rebuilt overlap and support QC, and, for adjusted branches,
its replicate-specific `DeltaReferenceScore` rebuild. Layer-2 evidence is not
collapsed into a block aggregate and no replicate-specific Delta/overlap state
is cached as invariant.

OSS uses one `CanonicalFiberAxis` descriptor and one ordered-axis identity per
batch. A row cache stores the row probability payload plus the shared axis
identity; it does not create one Python/JSON cache item per fiber or duplicate
`fiber_ids.npy`. The filtered go/no-go-selected connectome and canonical-to-local
mapping are produced once per `(connectome, simulation axis, schema)` and reused
read-only by rows. The PASS branch uses `Omega_max`; the fallback uses each
historical final axis. Consecutive selected fibers are coalesced into point ranges instead of
issuing one HDF5 slice per fiber. If the external tool can mutate its input, the
runtime uses a read-only source plus copy-on-write clone rather than a writable
hard link.

OSS toolchain attestation is retained but calculated once per immutable
run-environment identity. Row tasks perform only a lightweight semantic-version
guard; they do not repeat source-tree scans, package inventories, MATLAB version
startup, or environment probing. Removing payload checksums must not remove
command, version, environment, and scientific-toolchain provenance.

Shared `Omega_max` simulation is conditional on a bounded go/no-go decision
matrix. For every distinct allocator-relevant equivalence class, the same
physical row and deterministic solver state on the historical final axis and
the proposed maximal axis must yield axon-state/count mismatch count `< 1` and
probability `absolute_difference < accepted_probability_tolerance` for every
fiber in the final subset. One durable decision authorizes only its exact
physical-row/axis/toolchain/RNG class. An absent or failed class keeps the per-
final-axis producer authoritative for that class until a fiber-keyed correction
passes its proof.

The existing final-model state machine remains unchanged:

```text
shared physical input failure
  -> fail only dependent endpoints

endpoint clinical/design failure
  -> fail that endpoint/branch only

no stable source
  -> no final model under existing rules

realized final
  -> formal/sensitivity/report consume the same shared exposure view
```

## Deferred Performance Work

The initial refactor does not:

```text
change tau/Coverage source resolution
change signed fiber scoring semantics or tie rules
change formal replicate counts
stage connectomes automatically onto local SSD
```

Jitter physical preparation is part of Layer 1. OSS/pPAM physical preparation
joins Layer 1 only in the accepted PASS branch; FAIL retains the historical
final-linked producer in Layer 2. Endpoint-specific statistical analyses remain
in Layer 2. Local-SSD
staging and a persistent trilinear connectome-point lookup remain optional
second-stage optimizations.

## Implementation Phases

### Phase 0: Characterization

1. Freeze deterministic small direct and fiber exposure fixtures.
2. Record current scan counts, wall time, CPU, RSS, I/O, and output arrays.
3. Add counters for pool creations, nested executors, E-field/NIfTI opens,
   sampler builds/evictions, hot-loop path/lock operations, connectome coordinate
   and fourth-row bytes, raw chunk overlap, range skew, full-payload read/write,
   inline SHA, first-use verification bytes, memmap flushes, selected-
   exposure copies, artifact-index rewrites, queue/resource waits, token
   occupancy, and worker idle fraction.
4. Profile statistics, scoring, formal, pPAM, jitter, sensitivity, and OSS
   separately so scheduler changes are not credited for kernel improvements.

### Phase 1: Shared direct-voxel exposure

1. Resolve unique physical stimulation units before endpoint fan-out.
2. Bind immutable sampling plans outside the hot loop and introduce a bounded
   lease/LRU or read-only decompressed NIfTI cache.
3. Produce one bilateral voxel row per physical unit through a direct final-NPY
   writer.
4. Replace endpoint matrices with ordered row views.
5. Include exact tau, Coverage, and selected-reference-tau values; fixtures
   admit every reopened boundary.
6. Keep all direct-voxel numerical outputs equivalent outside the authorized
   threshold-boundary change.

### Phase 2: One-pass reduced fiber exposure

1. Cold-audit each connectome semantic ID/source-content-SHA/cache-schema identity;
   construct reusable point offsets and an implicit one-based canonical axis.
2. Introduce disjoint ranges balanced by point bytes that never split fibers and
   minimize partially shared raw chunks.
3. Materialize only coordinate rows into application memory on the audited hot
   path and evaluate all unique physical rows per resident range.
4. Apply exact minimum-grid `Omega_max` filtering.
5. Include exact tau, Coverage, and selected-reference-tau values; fixtures
   admit every reopened boundary.
6. Publish canonical reduced fiber IDs and continuous exposure as final shards
   plus one portable SHA manifest through atomic directory rename.
7. Prove no configured cell or fold loses a candidate.

### Phase 3: Shared jitter and gated OSS/pPAM preparation

1. Preserve the existing binding/frequency/subject/hemisphere/replicate/seed
   jitter identity and coordinate-translation semantics.
2. Materialize block-oriented jittered voxel and fiber physical exposure
   without duplicating invariant axes or clinical input; retain per-replicate
   logical exposure/overlap/support/Delta evidence.
3. Prove final-axis versus `Omega_max` OSS ten-state/count/probability equivalence
   in an explicitly authorized bounded decision matrix covering every distinct
   allocator-relevant physical-row/axis/toolchain/RNG class used by the run.
4. Only after that proof, generate OSS/pPAM rows on each formal connectome's
   `Omega_max` axis; otherwise retain final-axis production.
5. On PASS, build one filtered connectome/mapping and one O(1)-manifest
   row-cache axis per connectome/`Omega_max` identity.
6. On PASS, replace final-axis OSS production with canonical-ID subsetting from
   the prepared maximal axis. On FAIL, retain the historical per-final-axis
   request/cache/artifact producer and record the failed gate evidence.
7. Apply strict `p(A) > 0.5` activation with equality excluded.
8. Apply endpoint-specific overlap, nuisance, fitting, and reporting only in
   Layer 2.

### Phase 4: Shared grid operators

1. Cache tau exceedance and Coverage tensors by exact subject axis.
2. Derive LOOCV fold counts by subtraction.
3. Add block-vectorized average-rank, multi-RHS residualization, and correlation
   with scalar nonfinite fallback.
4. Compute endpoint/fold weights once on maximal support and mask by grid cell.
5. Add prevalidated axis/finite-mask/scratch fiber-scoring and task-scoped
   sensitivity workspaces; never reuse observed signed ordering.
6. Add statistics-only pPAM/formal paths that do not retain unused `N x F`
   arrays; reuse observed workspaces without changing outputs.

### Phase 5: Process scheduler

1. Introduce a pure-data worker command and initializer; keep mutable RunStore
   and scheduler state in the parent.
2. Replace CPU-heavy thread execution with one persistent spawned process pool.
3. Add an event-driven dependency-ready queue with bounded in-flight work,
   cancellation, heartbeat/timeout, and connectome/grid locality.
4. Add global CPU, memory, connectome-I/O, solver, and internal-parallelism
   admission control; remove nested pools outside the ledger.
5. Apply and verify BLAS/OpenMP/OSS thread limits.
6. Shard formal, pPAM, bootstrap, and jitter loops by fixed replicate index while
   preserving historical RNG schedules and fixed reduction; share parent-owned
   run-scoped scratch fold operators.
7. Re-evaluate dependency-derived skips on resume and record resource-only
   resume overrides separately from scientific identity.

### Phase 6A: Cache, publication, and main-run resume

1. Stop copying shared exposure into endpoint task roots.
2. Add publisher-owned direct NPY/final-shard writers that calculate payload SHA
   inline, logical block-gathering indexed views, and a parent-only artifact
   index.
3. Add one canonical portable manifest, direct-copy lookup, and a process-local
   verified set.
4. Retain atomic local-producer publication, full first-use verification,
   explicit integrity audit, and `--force`.
5. Delete no historical outputs; retire old cache producers only after parity.

### Phase 6B: Sensitivity-ready checkpoint

1. Publish one durable `sensitivity_base.json` for every realized final.
2. Prohibit scratch references and preserve complete source/cache/axis identity.
3. Add missing-parent detection and explicit rebuild inputs.
4. Publish both JSON and CSV artifact-index views during migration.

### Phase 6C: Sensitivity extension runner

1. Add the `sensitivity` application command and extension-only planner.
2. Create an immutable child run with parent-manifest identity.
3. Execute only selected jitter, OSS, or other final-linked sensitivity tasks
   when the parent checkpoint is complete.
4. Rebuild a missing main chain into a new parent lineage before extension.
5. Publish canonical results below a unique `extensions/<extension_id>/` path.

### Phase 6D: Cross-process and deletion acceptance

1. Exit after main final realization, then launch jitter in a new process.
2. Launch OSS in a new process with cache-hit and authorized-miss cases.
3. Copy portable entries directly and verify them on first use.
4. Delete parent scientific artifacts and prove explicit rebuild reruns the
   required observed/resolver/final chain before sensitivity.
5. Resume a partial extension without rerunning valid parent work.

## Planned Code Boundaries

Expected new modules:

```text
my_helper/fiber/core/dual_frequency/runtime/stimulation_units.py
my_helper/fiber/core/dual_frequency/runtime/shared_exposure.py
my_helper/fiber/core/dual_frequency/runtime/exposure_cache.py
my_helper/fiber/core/dual_frequency/runtime/sampling_plan.py
my_helper/fiber/core/dual_frequency/runtime/array_views.py
my_helper/fiber/core/dual_frequency/workflow/resource_scheduler.py
my_helper/fiber/core/dual_frequency/workflow/worker_runtime.py
my_helper/fiber/core/seed_target_connectivity/candidate_union.py
```

Expected modified modules:

```text
my_helper/fiber/core/dual_frequency/workflow/planner.py
my_helper/fiber/core/dual_frequency/workflow/executor.py
my_helper/fiber/core/dual_frequency/workflow/run_store.py
my_helper/fiber/core/dual_frequency/runtime/input_provider.py
my_helper/fiber/core/dual_frequency/runtime/service_adapters.py
my_helper/fiber/core/dual_frequency/runtime/jitter_provider.py
my_helper/fiber/core/dual_frequency/runtime/connectome_subset.py
my_helper/fiber/core/dual_frequency/runtime/oss_toolchain.py
my_helper/fiber/core/dual_frequency/cache/store.py
my_helper/fiber/core/seed_target_connectivity/connectome.py
my_helper/fiber/core/dual_frequency/backends/statistics.py
my_helper/fiber/core/dual_frequency/backends/direct_voxel/kernel.py
my_helper/fiber/core/dual_frequency/backends/normative_fiber/reference.py
my_helper/fiber/core/dual_frequency/backends/normative_fiber/addon.py
my_helper/fiber/core/dual_frequency/backends/normative_fiber/scoring.py
my_helper/fiber/core/dual_frequency/backends/activation/fitting.py
my_helper/fiber/core/dual_frequency/backends/activation/ossdbs.py
my_helper/fiber/core/dual_frequency/backends/formal/
my_helper/fiber/core/dual_frequency/backends/sensitivity/
```

Names may be refined during implementation, but ownership boundaries and
behavioral contracts above must remain intact.

## Acceptance Contract

### Numerical equivalence

- Direct-voxel optimized exposure equals the existing bilateral voxel formula.
- Normative-fiber optimized exposure equals side-specific peak followed by
  arithmetic mean; the forbidden mean-before-peak formula is tested to ensure
  it is not substituted.
- Direct-voxel and normative-fiber exposure include exact tau values, candidate
  selection includes exact Coverage values, and overlap includes the exact
  selected reference tau. Support-QC uses its documented strict direction and
  pPAM uses `p(A) > 0.5`. Fixtures admit every reopened boundary. Formal null-tail tests,
  hard minimum counts, and tolerance checks retain their existing definitions.
- Historical parity is required everywhere except values exactly on a
  user-authorized changed comparator boundary. Brute-force references are updated
  to the target policy before optimized-kernel comparison; any production-output
  difference must be attributable to an enumerated strict-boundary case.
- Brute-force and reduced-connectome outputs match for all retained features.
- Every feature entering any production tau/Coverage cell appears in
  `Omega_max`; false negatives are forbidden.
- Full and every LOOCV fold candidate-mask mismatch count against brute force is
  `< 1`.
- Observed weights, scores, predictions, source status, prediction status, and
  final realization have discrete mismatch count `< 1` and numerical
  `absolute_difference < existing_tolerance` outside the explicitly authorized
  strict-boundary cases.
- Vectorized and scalar partial-Spearman paths have discrete mismatch count
  `< 1` and `absolute_difference < existing_tolerance` for ties, constant
  columns, rank-deficient nuisance matrices, nonfinite fallback, and every
  tested block size.
- Prevalidated and historical fiber scoring have discrete mismatch count `< 1`
  and `absolute_difference < existing_tolerance` for sweet/sour IDs and order,
  support status, weighted peaks, NetFiberScore, held-out predictions, and
  observed reporting identity for full and every fold.
- Statistics-only pPAM/formal paths have discrete mismatch count `< 1` and
  `absolute_difference < existing_tolerance` for null rho/statistic, attrition
  state, support counts, plus-one p value, and replicate order against the
  retained-array path.
- Formal replicate ordering and statistics are invariant to worker count.
- Jitter perturbation schedules have byte mismatch count `< 1`, and physical
  exposure has `absolute_difference < existing_tolerance`, across scales that
  use the same physical stimulation unit.
- Every jitter replicate retains immutable logical references to its physical
  exposure block and Layer-2 overlap/support evidence; adjusted replicates also
  retain their own Delta rebuild identity. Block storage removes copies, not
  per-replicate scientific evidence.
- In the PASS branch, every endpoint OSS final axis is an exact canonical-ID
  subset of `F_OSS,prepare = Omega_max` with missing-ID count `< 1`, and
  subsetting has `absolute_difference < accepted_probability_tolerance` against
  prior final-axis row values.
- In the FAIL branch, the existing per-final-axis request/cache/artifact contract
  remains authoritative and its values reproduce the historical producer.
- Before replacing final-axis OSS production for a class, the same physical row
  is run on its historical final axis and on `Omega_max`; all ten per-fiber
  diameter states/counts have mismatch count `< 1`, and every probability has
  `absolute_difference < accepted_probability_tolerance`, on the shared subset.
  The bounded decision matrix must cover every distinct allocator-relevant
  class used by the run. If axis size/order affects allocation or RNG,
  production remains per-final-axis for that class until a separately accepted
  fiber-keyed allocator fixes the dependency.

### Reuse behavior

- A 28-scale run creates one physical exposure producer set per unique
  stimulation/connectome identity.
- Requested jitter creates one producer set per physical identity. OSS does so
  only in the accepted `Omega_max` PASS branch; the FAIL branch intentionally
  retains per-final-axis producers.
- Canonical-left resolution, NIfTI load, and sampler construction occur once per
  unique active sampling identity/worker batch; each sampling-hot-loop path,
  NIfTI-open, full-validation, and transform-lock counter is `< 1`.
- A full canonical fiber axis is represented once by a range descriptor; no
  endpoint republishes the parent `1..N` payload.
- Selected/final exposures are shared indexed views and do not create a second
  full selected-exposure payload.
- A filtered OSS connectome/mapping is built once per selected simulation-axis
  identity (`Omega_max` on PASS, final axis on FAIL); an OSS row manifest remains
  O(1) in fiber count and does not contain duplicated axis payloads.
- Toolchain attestation runs once per immutable environment identity and retains
  equivalent provenance.
- Changing only scale, endpoint outcome, run ID, worker count, or retry count
  produces a raw-physical-exposure cache hit. PASS-branch OSS also hits when its
  exact simulation-axis identity is unchanged. FAIL-branch OSS hits only when
  its exact historical final-axis identity is unchanged.
- Every used entry verifies every declared payload SHA on first use in each
  process.
- Later tasks in the same process reuse its verified semantic ID without
  repeating payload SHA.
- Missing files are produced once under a lock and atomically installed.
- Complete entries may be copied directly to final semantic paths; partial or
  corrupt copies fail closed and remain untouched. Platform-generated
  AppleDouble `._*` sidecars are filesystem metadata and are excluded from the
  scientific inventory; ordinary undeclared files remain corruption.
- `--force` rebuilds the selected cache explicitly.
- A complete sensitivity checkpoint supports a later extension process without
  rerunning observed, resolver, or final-model work.
- A missing parent chain is rebuilt into a new lineage before sensitivity work.

### Performance behavior

- Logical fiber points are covered once in aggregate per connectome and cache
  generation. Raw HDF5 chunk reads/decompressions are counted separately and
  may overlap only at bounded adjacent-range boundary chunks.
- After the cold structural audit, exposure scans read only three coordinate
  rows and allocate no point-sized expected-ID vector. Ranges are balanced by
  point bytes and report bounded median/max skew.
- Current-data physical row preparation decreases from 1540 endpoint-derived
  row scans per connectome to 42 unique physical rows evaluated during the
  shared pass.
- For a `workers=12` run, `effective_cores = aggregate process CPU time / wall
  time`. Eligible five-second windows have `runnable_cpu_slots > 5` and no
  measured memory/I/O/solver admission block; require
  `fraction(effective_cores > 6 among eligible windows) > 0.80`.
  Storage-limited windows are classified from measured throughput/I/O wait
  rather than silently excluded.
- The performance report includes wall time, CPU utilization, peak RSS, swap,
  bytes read/written, cache hits/misses, connectome range reads, and physical
  rows evaluated.
- A fault-free workflow benchmark creates one persistent CPU-pool generation;
  `nested_executor_creation_count < 1` outside the resource scheduler. A fault
  test may create a recorded replacement generation only after old-process
  termination and lease invalidation. For each integer resource class, peak
  Python processes, BLAS threads, simultaneous HDF5 readers, and OSS solver
  threads satisfy `observed_count < granted_count + 1`.
- Large-array cache misses write one final payload or shard set while calculating
  payload SHA inline. Each used entry and process has full verification count
  `> 0` and `< 2`; within-process repeat verification count is `< 1`. No
  selected exposure is copied solely to rename its endpoint.
- The finite statistics fast path performs block-level multi-RHS solves rather
  than one `lstsq` call per feature. Null loops require
  `retained_null_N_by_F_output_count < 1`, and adding workers does not linearly
  duplicate shared fold operators.
- `left_transform_resolve_count`, `nifti_open_count`, sampler build/rebuild/
  eviction counts, hot-loop path/hash/lock counts, connectome row-4 audit passes,
  direct-copy verifications, filtered-connectome builds, toolchain versions,
  memmap flushes, artifact-index snapshots, payload read/write/hash
  bytes, ready-queue depth, dependency/resource wait by class, token occupancy,
  worker idle fraction, and cancellation/timeout/retry counts are included in
  acceptance evidence.
- No test passes solely because more RAM was allocated. macOS acceptance
  requires `swap_delta_bytes < 1`; pre-existing system swap is recorded but is
  not misreported as swap created by the run.

### Benchmark matrix and configuration decision

Cold-cache and warm-cache benchmarks run direct voxel, each fiber connectome,
formal permutation, bootstrap, jitter, and pPAM separately at
`execution.workers = 1, 3, 6, 12`. Every row records wall time, aggregate CPU
time, effective cores, peak RSS, swap delta, source and scratch bytes, reader/
solver concurrency, queue/resource waits, and numerical identity. A benchmark
that cannot run records explicit preflight evidence and a `not_run` reason; it
cannot support a performance or default-setting claim.

OSS acceptance respects the existing expensive-producer authorization boundary:

```text
injected/synthetic solver: complete 1/3/6/12 scheduler and resource matrix
real cache hits: warm reuse and materialization behavior only
real cold solver: separately authorized bounded go/no-go decisions per exact allocator-relevant class outside routine acceptance
```

Without explicit real-OSS authorization, the cold row is `not_run`; a cache-hit
test does not claim solver utilization.

The current default remains `3` until this matrix demonstrates a safer faster
value on representative production data. A value of `12` is accepted only when
compute-bound stages sustain the target utilization without swap or nested
oversubscription. I/O-bound stages may admit fewer processes when measured
throughput proves that additional readers do not help; the scheduler records
that cap rather than changing `execution.workers` or pretending all 12 slots
were useful.

The 2026-07-16 cold production trace found sixteen decoded canonical-left
E-fields occupying about 4.2 GiB and sixteen matching right fields raising the
full bilateral working set to about 8.4 GiB. Because that value is `> 2 GiB`
and `> 5 GiB`, both tested sampler budgets caused eviction and repeated gzip
decoding inside the fiber range loop. The immediate resource correction uses a
10 GiB sampler budget and a 13 GiB prepare-exposure grant, while validating
each unchanged NIfTI once per process. Acceptance requires sampler rebuild
count after initial population to remain `< 1` for the same thirty-two-path
working set and swap growth to remain `< 1` byte. A later shared decompressed-
memmap cache may reduce private worker RSS, but is not required to start the
scientifically unchanged replacement lineage.

The subsequent all-endpoint production lineage confirmed two additional
runtime boundaries. A 300-second MATLAB transformation limit was `<` valid cold
left-to-canonical work, so the bounded limit becomes 1800 seconds without
weakening process-group termination or cache-publication rules. Persistent
worker RSS reached about 14.1 GiB, which is `< 16 GiB`; prepare-exposure tasks
therefore receive a 16 GiB ledger charge while the connectome-I/O ceiling still
bounds concurrency.

The same lineage exposed a scientific-axis assembly defect rather than a
threshold defect. An add-on primary `Omega_max` can be narrower than the locked
reference valid union required by DeltaReference. The add-on prepared feature
axis must be the parent-ordered union of those two sets. The physical exposure
cache and primary `Omega_max` remain separately identified and directly
copyable; only the run-scoped prepared axis is augmented. Any locked reference
ID absent from the parent connectome axis remains a hard failure. No tau,
Coverage, resolver, or DeltaReference comparator is changed.

The implementation checkpoint passes 417 dual-frequency tests and 224
parameterized subtests, including the new add-on/reference union identity,
missing-parent-ID failure, MATLAB process-limit, and resource-ledger cases.

The 2026-07-19 statistics optimization checkpoint routes complete finite
partial-Spearman blocks through one outcome solve and one multi-feature solve,
while retaining the historical columnwise path for nonfinite or rank-deficient
inputs. Normative-fiber observed work now computes Coverage counts once per
distinct tau, including reuse of the minimum-tau weight-cache vector and the
selected-cell vector. Direct parity, fallback parity, solver-call count, and
tau-scan count tests pass. The complete current regression passes 488 tests and
241 parameterized subtests.

The subsequent direct-voxel checkpoint binds a branch-local grid workspace to
the exact exposure, outcome, nuisance plan, direction, and hard limits. Both
reference and adjusted add-on paths build one threshold/Coverage operator per
distinct tau and one nuisance-only prediction per held-out fold, then reuse
only those values for grid cells and selected-cell publication. Every
outcome-dependent selected-cell quantity is recomputed. The focused gate passes
29 tests and 5 subtests; the complete current regression passes 490 tests and
241 parameterized subtests. Normative-fiber baseline-prediction reuse and the
explicit prevalidated scoring workspace remain open before Step 8 closes.

The remaining normative-fiber slice introduces one branch-local
`PrevalidatedFiberScoreWorkspace`. It validates the exposure and ordered
canonical fiber axis once, then owns bounded top-k retained/merge scratch whose
capacity may grow but whose contents are reset for every call. It never caches
weights, candidate masks, finite masks, sign partitions, order, selected IDs,
or scores. The endpoint workspace also computes the nuisance-only held-out
prediction once per fold and reuses that vector across grid and selected-cell
evaluation. Full observed metadata remains unchanged; parity and state-change
tests are required before this optimization is accepted.

Formal normative-fiber permutation and final in-sample inference reuse the same
workspace only while exposure and ordered fiber axes remain fixed. Observed
calls return complete publication metadata. Null calls return a lightweight
net-score/support-state record and recompute all outcome-dependent selections;
they do not construct or retain selected-ID arrays or hashes.
The pPAM activation permutation loop follows the same fixed-axis workspace
boundary. Its published full and observed-fold results keep complete support
metadata; permutation folds use only lightweight score state.

Strict DeltaReference support cutoffs use an absolute `1e-12` boundary-
proximity guard in both direct-voxel and normative-fiber classifiers. This
prevents a mathematical ratio at `0.20` from being accepted merely because
float64 subtraction represents it infinitesimally below the declared cutoff;
ratios genuinely farther below retain the strict passing behavior.

Step 8 final acceptance on 2026-07-19 confirms one normative-fiber
nuisance-only prediction per held-out fold, one exposure/fiber-axis validation
per scoring workspace, reusable bounded top-k scratch, independent
weight/mask/sign/order reconstruction, and lightweight null score state across
formal permutation, final in-sample, and pPAM permutation. Exact direct and
fiber cutoff fixtures also confirm strict support behavior. The workspace gate
passes 76 tests and 28 subtests, the support-boundary gate passes 22 tests and 3
subtests, and the complete regression passes 493 tests and 244 parameterized
subtests.

The first Step 9 slice uses an internal 250-replicate formal block size and no
new YAML option. A parent creates the complete historical permutation or
bootstrap index schedule with the unchanged `default_rng(seed)` call pattern;
block descriptors lend immutable half-open slices. Blocks never reseed or use
generic draw-count jumps. The schedule contract records the NumPy, Generator,
BitGenerator, schema, seed, subject/replicate counts, and full payload digest,
and must reassemble byte-for-byte under different block and worker orders.

The 2026-07-19 RNG foundation gate confirms byte parity for historical
permutation and bootstrap schedules and shuffled block reassembly. Formal
LOOCV, final in-sample, and pPAM use the shared constructor. The focused gate
passes 60 tests and 25 subtests and the complete regression passes 495 tests
and 244 parameterized subtests. Durable planner block tasks, aggregation, and
block-level resume remain open.

The next Step 9 slice first decomposes direct and fiber permutation numerics
into pure schedule-bound block calculations and a strict ordered aggregator.
Worker completion order may vary, but schedule digest and complete contiguous
replicate coverage may not. The unsplit public entry points run through the
same block contract and require multi-block numerical parity before the DAG is
expanded with durable block records.

This numerical slice passed its 2026-07-19 acceptance: reverse-order
three-block assembly is exactly equal to the public full calculation for both
direct voxel and normative fiber, malformed or incomplete block sets fail
closed, the focused formal suite passes 40 tests and 15 subtests, and the full
regression passes 497 tests and 246 subtests. Durable publication, planner
tasks, shared operator scratch, and block-level resume remain required before
this performance step is complete.

The next slice introduces closed-codec `ResamplingScheduleRecord` and
`ResamplingBlockRecord` roots. Schedule identity includes exact subject and
replicate axes, RNG provenance, digest, and immutable schedule artifact; every
block carries one canonical half-open interval, block axis, parent digest,
status, and immutable outputs. Completed task JSON plus existing artifact SHA
verification is the only resume mechanism. The production planner does not
emit these block tasks until parent-created read-only fold-operator scratch can
be reopened by workers without rebuilding, copying, or multiplying its memory
footprint.

The durable-record slice passed acceptance on 2026-07-19: canonical schedule
and permutation-block roots round-trip through the closed codec, retain exact
artifact closure, and reject changed fixed block size, interval, local axis, or
array metadata. The focused gate passes 60 tests and 37 subtests and the full
regression passes 498 tests and 248 subtests. The production DAG remains on its
existing entry point pending shared operator scratch and worker reopen tests.

The following slice builds the shared operator scratch substrate before DAG
migration. One exclusive run-scoped generation stores stacked direct-voxel
fold fields. Normative-fiber fixed-shape fields are stacked, but every fold's
variable estimable-index and coefficient matrices remain separate contiguous
NPY arrays; padded strided coefficient views are disallowed after producing an
approximately `1.1e-16` Pearson-rho parity difference. Each descriptor retains
the original C/Fortran memory order. Workers receive only a
validated descriptor and reopen read-only
memmaps; no fold operator is rebuilt, copied, or pickled per block. Atomic
generation publication never overwrites an existing file. Cleanup is confined
to descriptor-listed generation files and is allowed only after successful
downstream completion; failed or partial execution retains scratch for resume.
Raw work-directory paths remain confined to private runtime publication
helpers and never enter a public scientific-backend signature.

The operator-scratch foundation passed acceptance on 2026-07-19. Direct and
fiber reconstructed operators use read-only memmaps and reproduce all metrics
exactly; separate Fortran-order fiber coefficient payloads remove the detected
padded-view drift. One actual spawn worker reopened the descriptor without an
operator payload. Cleanup preserved an untracked sentinel and removed only the
declared generation after the sentinel was explicitly cleared. The focused
gate passes 42 tests and 13 subtests and the full regression passes 500 tests
and 248 subtests. Planner integration and resume-aware descriptor persistence
remain open.

The next slice persists a `FormalOperatorScratchRecord` with no `ArtifactRef`
closure. It uses only a safe run-root-relative generation path, exact
subject/feature axes and scientific-input identity, ordered NPY header
descriptors, total bytes, and terminal status. Resume restores the completed
workspace task only after all files reopen read-only beneath the current run's
`work` directory. Missing or malformed scratch reruns that producer without
invalidating independent completed block outputs; repository code identity is
not a gate.

The resume-aware scratch record passed acceptance on 2026-07-19. Closed-codec
and path/header checks pass, descriptor conversion is confined to the current
run work root, valid scratch is restored without service invocation, and a
removed generation reruns only its workspace task. The focused gate passes 76
tests and 44 subtests and the full regression passes 502 tests and 249
subtests. Production workspace services and the block DAG remain open.

The next slice registers separate schedule and operator-workspace predecessor
services without yet emitting them from the production planner. The first
publishes one exact historical schedule artifact and typed record; the second
materializes the formal request once, builds fold operators once, and returns
one input-bound run-relative scratch record. Failures clean only the new
descriptor generation. Tests must prove both typed service boundaries before
the existing serial `formal_permutation` task is replaced. The focused matrix
must cover reference voxel, reference fiber, adjusted add-on voxel, and
adjusted add-on fiber so the DeltaReference full/fold inputs are exercised.

The two predecessor services passed acceptance on 2026-07-19. They are present
in the production registry but remain absent from the planner until block and
aggregate consumers are complete. Reference voxel, reference fiber, adjusted
add-on voxel, and adjusted add-on fiber pass through the typed provider
boundary, restore the published historical schedule byte for byte, reopen all
operator arrays as descriptor-validated read-only memmaps, and prove that
neither service calls a formal fit or returns a `FormalResult`. Changed
schedule identity fails validation, and a synthetic post-publication record
failure cleans only the newly created operator generation. The focused gate
passes 89 tests and 48 subtests; the complete
dual-frequency and visualization regression passes 504 tests and 253
subtests. The production DAG and its task count are unchanged.

The next slice adds registered but unplanned formal permutation block and
aggregate consumers. Each block receives only its canonical internal index,
the exact published schedule, the input-bound run-relative operator record,
and normal typed formal inputs. It validates and reopens shared operators,
computes only its null-statistic interval, and publishes one durable block
record. It never rebuilds fold operators and never computes observed metrics.
The aggregate validates complete historical interval coverage, computes the
observed statistic once with the same shared operators, combines blocks in
replicate order, and emits the existing final formal result while referencing
the original schedule artifact. Scratch remains available for resume and later
extension work. Four-family service parity and malformed-block rejection must
pass before planner migration.

The block and aggregate consumers passed acceptance on 2026-07-19. All four
endpoint model families use reopened scratch without invoking either fold
operator builder. Direct and fiber 251-replicate fixtures publish a canonical
250-replicate block and one-replicate tail; reverse completion order produces
the exact retained serial null array, observed metrics, and p value. Missing
coverage, changed schedule binding, and changed scratch input identity fail
closed. The aggregate retains the upstream schedule artifact and does not
delete scratch. The focused gate passes 90 tests and 50 subtests, and the
complete dual-frequency and visualization regression passes 505 tests and 255
subtests. The registered consumers remain absent from the production planner.

The next slice replaces only new-plan formal permutation topology. Each final
endpoint receives schedule and operator-workspace predecessors, then one
canonical block task per 250 configured permutations or partial tail, followed
by an aggregate that retains the public `formal_permutation` stage and
`FormalResult`. Every spawned block has direct typed clinical/final inputs plus
the two shared predecessor records; the aggregate also has every block record.
The internal block index is an immutable task parameter, independent of worker
count and unavailable in YAML. Existing downstream tasks continue to depend on
the aggregate. Historical family-specific serial services remain callable but
are not emitted by new plans. The scheduler charges all four new stage types to
the existing formal memory and CPU resource class.

Task-local selected-exposure copies are compared by immutable payload SHA and
scientific array metadata, not URI or producer labels. The scratch identity
continues to include the final model, all other formal input payloads and axes,
model settings, replicate count, and seed. This permits the schedule,
workspace, block, and aggregate tasks to reconstruct content-equivalent typed
requests without treating their distinct work directories as scientific
changes.

Resume acceptance changes one durable block and its aggregate to nonterminal
state after a complete synthetic run. The next execution must invoke exactly
one block consumer and one aggregate consumer; every other completed task and
the valid shared schedule/operator predecessors remain restored.

### Default final in-sample inference

Every realized final model in formal scope has a required in-sample inference
path. It is not a YAML option: the existing formal permutation count and
resolved endpoint seed control both LOOCV and in-sample inference. The two
paths share only outcome-independent inputs and a declared residual-permutation
schedule. They never share one fitted model. In-sample fits on the complete
subject axis; LOOCV independently refits every held-out fold.

The v1 in-sample test is conditional on the realized final model. It locks the
actual endpoint-specific tau, Coverage, branch, overlap exclusion, subject
axis, prepared physical exposure, and canonical candidate feature IDs. It
recomputes every outcome-dependent voxel/fiber weight, signed fiber library,
weighted-peak selection, spatial score, benefit orientation, and regression
coefficient for the observed outcome and every pseudo-outcome. The published
conditioning label is
`conditional_on_selected_tau_coverage_branch_and_candidate_axis`; it does not
claim correction for source search, fallback, branch choice, or resolver
selection.

The primary statistic is Spearman rho between outcome and the full-sample
fitted prediction. A paired report places in-sample and LOOCV Spearman,
Pearson, nominal p, formal permutation p, standard R2, nuisance-relative R2 or
Q2, RMSE, MAE, baseline error, and finite-result evidence on the same endpoint
row. Adjusted R2 is forbidden because the outcome-derived feature-fitting path
has no fixed interpretable effective degrees of freedom. Optimism gaps require
identical outcome transform, subject ordering, and finite-subject masks.

The report applies Benjamini-Hochberg correction to formal permutation p
values within each 28-scale model family and across all 112 final endpoints.
Nominal correlation p values remain descriptive. A small explicit residual-
permutation schedule artifact binds subject order, resolved seed, RNG identity,
contract version, and replicate count. A child of a historical run without
that artifact cannot infer subject-index rows from its null-statistic vector
alone and therefore reports an independent deterministic schedule. New runs
claim a shared explicit schedule only when both schedule payload SHA values
match.

Initial persistence mirrors the current LOOCV implementation: one endpoint
task publishes one complete null-statistic vector and resumes only at endpoint
granularity. No fixed 250-replicate block is introduced. Future Task 17 formal
sharding must shard LOOCV and in-sample together and independently refit both
paths; it cannot reuse one path's fitted weights or predictions.

The completed v8 formal lineage is not mutated. Its separately identified
`final_in_sample` extension restores immutable final-model checkpoints and
existing LOOCV evidence, computes only the in-sample path, and publishes the
paired report. New main lineages include in-sample inference automatically.

The first formal extension is complete at
`task17-final-in-sample-v1-20260718`. It restored 504 read-only parent
checkpoint tasks and completed 112 endpoint-level in-sample tasks, split into
28 reference voxel, 28 add-on voxel, 28 reference fiber, and 28 add-on fiber
results. All requested permutation statistics are finite; the paired report
contains all nominal and formal p values, both R2 definitions, Q2, error,
baseline error, and optimism gaps. Both model-family and all-endpoint BH layers
are complete. Historical v8 schedule status is correctly independent for all
endpoints. No fixed permutation block, jitter, OSS-DBS, observed, resolver,
final, LOOCV, or bootstrap computation ran in this child.

### State-machine closure

- Shared physical failure reaches every dependent endpoint deterministically.
- With `continue_on_endpoint_failure=true`, independent endpoints continue.
  With it false, queued work is cancelled and recorded as
  `not_run_batch_aborted`.
- Outcome-dependent failures do not invalidate reusable physical exposure.
- No source/prediction/final status is changed by cache hit/miss or worker
  count.
- Formal and sensitivity remain attached only to the realized final model.
- A fail-once dependency followed by resume reruns its previously
  dependency-skipped descendants; stable gate skips remain deterministic.
- Each task invocation uses a fresh immutable `work/<task_id>/<attempt>`
  directory. Resume retains every prior completed, failed, and partial attempt
  and publishes replacement artifacts only in the new attempt. Attempt paths
  are execution provenance and never become a scientific identity or resume
  gate.
- A workspace failure after operator generation retains that generation in its
  immutable attempt. Automatic failure-path cleanup is prohibited; explicit
  descriptor-confined cleanup remains a maintenance and test-teardown action.
- Fail-fast cancels queued work. A timeout releases tokens only after worker/
  subprocess termination, lease revocation, and temporary-output quarantine;
  retry is limited to declared idempotent/transient-safe tasks with unchanged
  identity.
- Resume may change only execution-resource limits after invariance acceptance;
  each segment records its effective settings without invalidating scientific
  outputs.

Planner-migration acceptance on 2026-07-19: production plans now replace each
serial formal-permutation task with one schedule task, one shared operator
workspace task, fixed internal 250-replicate blocks, and one ordered aggregate.
The configured permutation count determines only the number and tail length of
those blocks. A synthetic 251-replicate interruption reruns only the selected
block and aggregate, retains both earlier attempts byte-for-byte, and restores
all other scientific work. The complete validation matrix passes 483
dual-frequency tests, eight separately invoked goal guards, and 14
visualization tests. Production data and sensitivity extensions remain
untouched.

The next numerical slice splits bootstrap without expanding the production
DAG. Each fixed schedule block emits only mergeable O(F) moment/count state,
block-local O(B) replicate diagnostics, and ordered nuisance evidence; it never
emits a block-by-feature weight matrix. The aggregate requires complete
canonical coverage, combines integer state exactly, and reduces floating
moments in replicate-block order within the retained serial tolerance. Both
direct voxel and normative fiber must pass a 251-replicate reverse-completion
fixture before durable bootstrap publication, planner tasks, or pPAM sharding
begin.

Bootstrap numerical acceptance on 2026-07-19 confirms direct and fiber
251-replicate reverse-order aggregation without a block-by-feature retained
matrix. All integer and categorical fields are exact; floating summaries stay
within `1e-13` relative and absolute tolerance against the single-interval
calculation. Incomplete, changed-digest, and untyped blocks fail closed. The
complete validation matrix passes 484 dual-frequency tests, eight separately
invoked goal guards, and 14 visualization tests. Durable publication, planner
migration, and pPAM sharding remain open.

The following numerical slice routes the pPAM permutation null through the
same complete historical schedule and strict ordered block aggregator. One
fixed in-task workspace reuses binary exposure, nuisance operators, fold
operators, and scoring scratch; each block retains only its null Spearman
interval. A 251-replicate reverse-order fixture must match the retained
single-interval calculation exactly before durable pPAM records, operator
scratch, or sensitivity-planner tasks are introduced.

pPAM numerical acceptance on 2026-07-19 confirms exact 251-replicate null
parity between one interval and the 250-replicate plus one-replicate blocks.
Reverse completion order is deterministic; incomplete and changed-digest
blocks fail closed. The OSS/pPAM module passes 23 tests, and the complete
matrix passes 485 dual-frequency tests, eight separately invoked goal guards,
and 14 visualization tests. No durable pPAM record, planner mutation, or real
OSS execution was introduced.

The durable-bootstrap record slice publishes mergeable feature moments and
counts, block-local diagnostics, and strict evidence JSON against the exact
parent bootstrap schedule. It excludes every per-replicate feature-weight
matrix. Restoration verifies SHA, metadata, axes, interval, selection mode,
and adjusted evidence coverage before numerical aggregation. Production
planner and service topology remain unchanged until this record contract passes
direct and fiber round-trip tests independently.

Durable-bootstrap acceptance on 2026-07-19 confirms exact direct and fiber
round trips, correct model-specific artifact closure, and fail-closed rejection
of changed parent, axis, kind, shape, payload SHA, selection closure, or
adjusted evidence coverage. The focused codec and formal suites pass 57 tests;
the complete validation matrix passes 487 dual-frequency tests, eight
separately invoked goal guards, and 14 visualization tests. No production,
jitter, OSS-DBS, or combined extension process was started.

The following service/planner slice expands each formal bootstrap into one
complete schedule, fixed 250-replicate block tasks, and one ordered aggregate.
Blocks execute independently in the shared persistent worker pool but do not
share permutation operators or sampled-model fits. Adjusted add-on blocks keep
the full matched-reference dependency closure needed to rebuild sample-specific
nuisance values. Only O(F) mergeable feature state and O(B) diagnostics cross
the task boundary. A 251-replicate resume fixture must rerun one invalidated
block plus its aggregate while preserving all completed predecessors and prior
attempt bytes. Newly compiled plans must not select the historical serial
family-specific bootstrap services.

Bootstrap DAG acceptance on 2026-07-19 confirms four-model 251-replicate
service parity, strict missing-interval rejection, and block-level resume that
invokes only one invalidated block and its aggregate. Completed predecessors,
the other block, and both old immutable attempt generations remain unchanged.
The complete validation matrix passes 490 dual-frequency tests, eight
separately invoked goal guards, and 14 visualization tests. No production or
sensitivity process was started.

The next record-only pPAM slice introduces a dedicated immutable null-block
record bound to the complete parent schedule. Each record contains only its
LOOCV Spearman interval and never carries physical OSS rows, activation
matrices, fold weights, predictions, or selected fibers. Runtime restoration
validates the full parent and artifact contract before lending numerical state.
Sensitivity planner migration remains disabled until a separate observed pPAM
workspace can guarantee that physical OSS preparation and retained observed
output execute once per endpoint rather than once per null block.

The record-only runtime gate now round-trips exact block-local null bytes and
fails closed on changed parent schedule identity or digest, changed artifact
semantics, and payload SHA corruption. The focused codec and OSS regression
passed 35 tests and 39 subtests. The complete dual-frequency gate passed 502
tests and 295 subtests outside the restricted system-monitoring sandbox. No
planner, production, jitter, OSS-DBS, or combined extension was started by this
slice.

The next pPAM numerical slice creates one endpoint-local in-memory fit
workspace. It owns the immutable binary exposure, final feature IDs, nuisance
plan, fixed full and fold operators, reusable score workspace, observed fit,
and permutation eligibility. Canonical permutation blocks consume this object
without rebuilding those inputs, and the strict ordered aggregate combines the
complete parent axis into the unchanged final pPAM result. The serial public
entry point must delegate to the same workspace/block/aggregate path so parity
does not compare two independent implementations. Durable scratch, task
records, planner migration, and extension resume follow only after this
numerical boundary passes the two-block parity and one-construction tests.

The numerical workspace gate now passes. A 251-replicate fixture builds fixed
operators once, executes the 250-replicate block and one-replicate tail in
reverse completion order, reproduces the single-interval null bytes exactly,
and reproduces every existing pPAM result field through the compatibility
wrapper. The focused OSS gate passed 24 tests and 12 subtests; the complete
dual-frequency gate passed 502 tests and 295 subtests outside the restricted
system-monitoring sandbox. Planner and durable-workspace migration remain the
next boundary, and no sensitivity process was started.

Before persistence, observed pPAM outputs are projected into a separate
operator-free state. It retains every final observed array, support and
performance field, technical reason, peak-score comparison, and plain-control
result, but never the null axis or physical OSS rows. The ordered aggregate
consumes this state plus the complete parent schedule and durable null blocks.
This makes observed-state publication independent from the run-scoped
fixed-operator scratch and allows resume to invalidate only the missing layer.

The operator-free boundary now passes exact result parity. Ready observed state
requires the complete parent schedule, while degenerate observed state accepts
no null state and preserves the historical failure classification. The
focused OSS gate passed 25 tests and 12 subtests; the complete dual-frequency
gate passed 503 tests and 295 subtests outside the restricted
system-monitoring sandbox. No sensitivity process was started.

The durable pPAM workspace record has three explicit terminal modes:
permutation-ready observed state, complete observed state without permutation,
and nuisance-non-estimable state. It binds all typed fitting inputs and request
parameters, observed outputs, and an optional run-relative fixed-operator NPY
generation. Only the first mode may feed a schedule or null block. Null blocks
receive this restored state directly and may never invoke physical OSS
materialization, input republishing, or operator reconstruction. Missing
scratch invalidates the observed task for resume instead of shifting work into
its descendants.

The durable observed-workspace record and closed codec now pass acceptance for
all three terminal modes, reference and adjusted add-on branches, exact named
artifact closure, and run-relative scratch descriptors. Changed branch
semantics, incomplete scratch, scratch attached to a nuisance failure, and
malformed persisted scratch fail closed. The focused codec gate passed 12
tests and 28 subtests; the complete dual-frequency gate passed 504 tests and
296 subtests outside the restricted system-monitoring sandbox. Runtime scratch
publication, worker reopen, and sensitivity-planner migration remain the next
boundary.

The next runtime slice persists only fixed pPAM numerical state. One exclusive
run-relative generation stores nuisance designs and full/fold rank-residual
operators as descriptor-bound read-only NPY arrays. Variable logical widths
use deterministic prefix packing plus the recorded estimable masks; a logical
zero-width matrix keeps one physical storage column. Reopened blocks rebuild
only lightweight scoring scratch from already published activation and fiber-ID
artifacts. They may not rebuild nuisance designs, rank residuals, or physical
OSS rows. Exact descriptor validation, macOS spawn reopen, missing-file
invalidation, and descriptor-confined cleanup must pass before service or
planner migration.

The runtime scratch gate now passes. Fixed pPAM state reopens as read-only
memmaps in both the parent and a fresh macOS spawned process, reproduces one
null block byte-for-byte, and never invokes `_weight_operators`. Logical
zero-width operators survive the physical padding representation. Request
identity mismatch, missing payload, and untracked cleanup content fail closed.
The joint formal and OSS gate passed 74 tests and 39 subtests; the complete
dual-frequency gate passed 506 tests and 296 subtests outside the restricted
system-monitoring sandbox. Observed-output service publication and planner
migration remain open.

The next service slice registers four pPAM boundaries without changing the
planner. The observed service alone may materialize physical OSS rows and
publishes the durable observed workspace plus one permutation-readiness fact.
Schedule and block services reconstruct their request only from that record
and published artifacts. Their normal readiness gate emits no schedule or null
record for either non-permutation terminal state. The aggregate still runs
after those skipped tasks become terminal, requires schedule and blocks only
for a ready parent, and publishes the historical public activation result.
Ready and degenerate service paths must pass independently before planner
migration.

The service gate now passes. The four registered boundaries preserve the
historical activation artifact set and content digests, reopen one immutable
operator generation without rebuilding it, and distinguish permutation-ready,
observed-degenerate, and nuisance-design terminal states. Malformed numerical
state and incomplete scratch fail closed. The focused service, OSS, codec, and
dependency gate passed 54 tests and 43 subtests; the complete dual-frequency
and visualization gate passed 526 tests and 299 subtests outside the restricted
system-monitoring sandbox.

The planner migration replaces each formal fiber activation task with one
cache-first observed workspace, one deterministic schedule, fixed
250-replicate pPAM blocks, and one historical-stage aggregate. Only the observed
task holds connectome-I/O and solver tokens. Schedule and block tasks use the
single readiness gate; the aggregate runs for every realized final after those
tasks become terminal. Independent OSS extensions select this complete subgraph
and convert only its completed non-formal parents into checkpoint roots. One
invalidated block reruns with its aggregate while the observed workspace,
schedule, other blocks, and physical OSS cache remain reusable.

Planner-migration acceptance on 2026-07-19: no newly compiled task selects the
serial compatibility services. Ready output matches the retained serial backend
artifact-for-artifact, false readiness skips schedule and blocks while the
aggregate completes, and independent OSS plus combined jitter/OSS child plans
close without rerunning their observed parent. Resume validates a restored pPAM
workspace against its final model, scientific input identity, and scratch
headers. Invalid completed workspace state invalidates its descendants, whereas
an explicitly interrupted formal block retains independent valid consumers.
The planner, executor, service, and extension focused gate passed 59 tests and
86 subtests. The complete dual-frequency and visualization gate passed 534
tests and 308 subtests outside the restricted system-monitoring sandbox. No
production, jitter, OSS-DBS, or combined extension was started.

Before the first formal OSS child starts, add two explicit axis-equivalence
group tasks to the extension DAG. The current completed parent yields one
reference-fiber group and one add-on-fiber group. Each group is keyed by its
exact ordered final axis, exact ordered `Omega_max` cache identity, formal
connectome, allocator and solver toolchain identity, RNG contract, probability
tolerance, and ordered physical-row identities. Every observed pPAM workspace
in that group depends on the group decision. A missing, corrupt, or identity-
changed decision keeps the group on the historical final-axis path.

The parent checkpoint already names the portable shared-cache entries needed
to recover `Omega_max`. The loader must select the one
`normative_fiber_omega_max` entry whose stimulation identity matches the base's
primary shared exposure, validate its manifest and payload, and enrich the
in-memory checkpoint without editing the completed parent. Future checkpoints
publish this descriptor directly. Absolute paths, run identity, scale, and
endpoint identity do not enter the gate cache key.

The production row inventory is derived from the union of included subjects in
the 56 realized fiber finals. Sixteen reference subjects produce 34 logical
OSS rows and thirteen add-on subjects produce 26 logical rows. The decision
matrix therefore contains 60 row classes. A logical row uses one final-axis and
one `Omega_max` product, but each external product is partitioned into ordered
execution chunks containing `< 3501` fibers. Every chunk runs the same ten fixed
diameter samples. The sole external-solver token makes these sample executions
sequential. Per-row immutable decisions make an interrupted group task resume
from the first missing row rather than restart accepted rows.

For each row, the producer retains the ten sample-wise axon-state vectors long
enough to compare the final-axis vector with the canonical-ID subset of the
`Omega_max` vector. PASS requires state mismatch count `< 1`, activation-count
mismatch count `< 1`, and maximum probability absolute difference below the
internal accepted tolerance. Both standard row-cache entries are published
after structural validation regardless of PASS or FAIL. A group uses shared
`Omega_max` simulation only when every row decision passes; otherwise every
endpoint in that group uses its historical final axis. In both branches the
ordinary pPAM workspace and public activation artifacts remain on the exact
final model axis.

The row cache uses one O(1) manifest in fiber count, stores no per-fiber
`CacheItem` list, and writes each NPY payload once from its final byte buffer.
The group task attests the immutable toolchain once, records every per-row
decision cache identity, and publishes one group summary. Later observed tasks
validate that summary and the required row caches before reuse. The corrected
independent OSS plan contains 590 tasks: 196 immutable roots, two gate tasks,
and 392 endpoint pPAM tasks. The corrected combined plan contains 1194 tasks:
448 immutable roots, 240 jitter blocks, two OSS gate tasks, and 504 endpoint
statistics and pPAM tasks.

Implementation checkpoint on 2026-07-20: the production loader now recovers
and validates the portable `Omega_max` descriptor without changing the
completed parent. Live validation covered all 56 fiber endpoints and recovered
the two exact axis pairs, reference 3401 to 10320 fibers and add-on 2004 to
7193 fibers. The extension compiler emits the two group gates and the real
independent OSS dry plan contains 590 tasks. Each observed workspace depends
on one gate. The implemented gate persists one immutable decision per physical
row, retains all ten axon-state samples during comparison, publishes both
standard row caches with an O(1) manifest in fiber count, and selects back to
the locked final axis before endpoint fitting. Synthetic PASS, FAIL, resume,
codec, resource-token, exact-subset, and constant-manifest tests passed. The
complete dual-frequency regression passed 530 tests and 310 subtests outside
the restricted system-monitoring sandbox. Formal real solver decisions and the
independent OSS child remain open; no formal OSS child has started.

The first production child and its PATH-repaired resume then supplied the
missing real resource evidence. A 3401-fiber final row completed, whereas the
first 10320-fiber `Omega_max` sample exceeded 48 GiB and reached about 72.8 GiB
during termination. The main process exited before the separately sessioned
solver, so the orphan required direct termination. No row cache or equivalence
decision published and swap did not grow. Formal resume is prohibited until
the fixed `< 3501`-fiber chunk executor, 48-GiB solver charge, hard managed-grant
admission, and worker-to-child process-group termination pass automated tests
and a real reference-chunk acceptance with RSS `< 48 GiB`, total managed memory
`< 64 GiB`, and swap growth `< 1` byte.

The bounded-row and cascade-termination implementation passed 62 focused OSS/
executor tests. The complete dual-frequency regression passed 534 tests plus
310 subtests in the `leaddbs` environment. Formal OSS resume remains blocked on
the real reference-chunk RSS acceptance rather than on automated regression.

The first monitored exact 3500-fiber reference `Omega_max` execution measured
45,910,048,768 bytes of solver RSS and 46,284,881,920 bytes across the complete
descendant tree. Minimum available memory remained 77,078,921,216 bytes, swap
growth stayed `< 1` byte, and VAL remained mounted. The run was stopped because
that result exceeded the earlier 32-GiB charge. The evidence supports a 48-GiB
sole-solver charge under the unchanged 64-GiB cumulative ceiling and reserve;
it does not support restoring the historical unchunked 10320-fiber row. All ten
samples of one 3500-fiber chunk must still pass before the real gate closes.

The accepted v8 jitter exercise exposed one final-linked dependency-selection
defect after every physical block and every reference endpoint had completed.
An add-on endpoint closure intentionally contains both its own prepared exposure
and the matched-reference prepared exposure needed for physical reconstruction.
The endpoint adapter must therefore never require a type-only singleton
`PreparedExposureRecord`. It selects the one record whose endpoint identifier
matches the current task endpoint, fails closed when that endpoint-local record
is absent or duplicated, and leaves cross-endpoint records available only to
the explicitly matched-reference provider. The same endpoint-local selector is
required by spatial jitter and OSS activation so the later OSS extension cannot
repeat this defect.

This repair does not alter jitter blocks, RNG order, final axes, task identity,
or any completed artifact. Its regression gate supplies target and reference
prepared records to one add-on jitter task and one add-on activation task,
proves selection of the target record, proves reference behavior is unchanged,
and proves missing or duplicate endpoint-local records fail closed. Resume of
the v8 child must restore all completed roots, 240 physical blocks, and completed
endpoint results, rerun only its ten failed add-on endpoint tasks, and publish a
complete manifest only after all 800 tasks are terminal without failure.

Post-publication cleanup now has an executable fail-closed boundary. The main
canonical publisher alone may remove descriptor-listed formal or pPAM scratch
and run-owned `runtime_work` after complete run, artifact-index, model-manifest,
and configured-scale validation. Shared scientific cache and durable artifacts
remain outside that boundary. False policy, incomplete state, untracked scratch,
true-policy cleanup, and idempotent replay pass; the complete regression passes
539 tests and 308 subtests. The production policy remains false and no
production cache was deleted.

## Documentation Validation

Before implementation begins:

```bash
git diff --check
git diff --name-only -- '*.py' '*.m'
```

The second command must be empty for this documentation-only pass.

Contract searches:

```bash
rg -n "shared_exposure_v2|semantic_sha256|payload_sha256|Omega_max|ThreadPoolExecutor|ProcessPoolExecutor|side-specific peak" \
  my_helper/stnsnr -g '*.md'

rg -n "device, inode|mtime_ns|generation manifest|checksum-free|digest-free" \
  my_helper/stnsnr/four_model_yaml_core_refactor_plan.md \
  my_helper/stnsnr/dual_frequency_core_decoupling_design.md \
  my_helper/stnsnr/dual_frequency_core_decoupling_implementation_plan.md
```

Any remaining old statement must be marked as historical/current
implementation and non-authoritative. The target has only the portable
SHA-manifest contract above; every new process verifies each used entry once.

## Closed Decisions

```text
all scales reuse physical E-field exposure
direct voxel averages left/right voxel fields once
normative fiber peaks each side first and averages the two peaks second
minimum tau and Coverage define an exact maximal fiber candidate union
retained fiber values remain continuous
raw add-on exposure defines only an upper bound before overlap exclusion
cache identity uses portable canonical JSON and semantic SHA
each file records payload SHA calculated while writing or verified on first use
one manifest and one atomic directory rename authorize a cache entry
device inode mtime and absolute path never enter portable identity
complete cache entries may be copied directly to their final semantic paths
each process verifies a used entry once and memoizes that verification locally
every realized final emits a durable sensitivity checkpoint
later sensitivity runs use an immutable extension lineage
missing parent work is rebuilt into a new parent lineage before extension
CPU-heavy preparation uses processes and disjoint work units
execution.workers is the sole public n_jobs-like global CPU ceiling
voxel and fiber retain distinct sampling, partitioning, and candidate contracts
E/tau, Coverage, and overlap include their boundaries while support-QC and pPAM retain their documented strict comparisons
one persistent event-driven pool replaces per-wave and nested executors
the parent process alone owns scheduler and RunStore mutation
large producers write final-format payloads or shards once and endpoints consume logical indexed views
endpoint statistical results remain independent
jitter schedules and jittered physical exposure are prepared before scale analysis
OSS/pPAM uses formal-connectome Omega_max only for classes covered by final-axis equivalence decisions
parallel blocks preserve existing RNG schedules and never use worker identity
endpoint jitter and OSS statistics select subsets and remain outcome-dependent
```

There are no unresolved scientific choices in this performance-refactor
contract. Implementation details may change only when they preserve every
closed decision and acceptance gate above.
