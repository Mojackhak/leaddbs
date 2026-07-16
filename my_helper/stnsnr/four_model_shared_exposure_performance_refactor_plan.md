# Four-Model Shared Exposure And Performance Refactor Plan

> **Purpose.** Remove scale-dependent physical-exposure recomputation and make
> configured all-scale execution use the available CPU, memory, and storage
> bandwidth efficiently without changing model classification.
> **Workspace.** `/Users/mojackhu/Github/leaddbs`
> **Parent goal.** `my_helper/stnsnr/four_model_yaml_core_refactor_plan.md`
> **Implementation plan.**
> `my_helper/stnsnr/dual_frequency_core_decoupling_implementation_plan.md`
> **Historical implementation plan.**
> `my_helper/stnsnr/four_model_yaml_core_refactor_implementation_plan.md`
> **Scientific specifications.** `my_helper/stnsnr/model_summaries/`
> **Current branch.** `stnvop`
> **Status.** `design_documented`; `implementation_not_started`;
> `current_outputs_unchanged`; `active_runs_not_modified`.
> **Last updated.** 2026-07-16

---

## Authority And Scope

This document is the current performance-refactor contract for the configured
four-model runtime. It overrides earlier cache and scheduling statements only
where they conflict with the explicit rules below. It does not change the
source resolver, prediction classifier, branch-role state machine, final-model
realization, or inferential definitions.

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

No currently running process is interrupted or migrated. Existing production
outputs remain read-only. This document does not claim that the target
implementation already exists.

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

1. `workflow/executor.py` uses `ThreadPoolExecutor`. Python/HDF5-heavy work does
   not achieve reliable multi-core execution, and h5py/HDF5 access can
   serialize threads inside one process.
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

## Two-Layer Target Architecture

### Layer 1: scale-independent physical preparation

The preparation layer is keyed by subject, phase/program binding, frequency
class, physical component grouping, coordinate-space rule, connectome, and
producer version. It never receives a scale, outcome, endpoint status, or final
model.

It produces:

```text
canonical side-specific E-field references
bilateral direct-voxel exposure rows
bilateral normative-fiber peak-exposure rows
minimum-grid maximal voxel/fiber support
shared localization-jitter schedules and jittered physical exposure rows
OSS/pPAM activation rows on the maximal eligible fiber support
ordered subject/voxel/fiber axes and row indexes
```

Expensive preparation is workflow-demanded: base exposure is required for
observed analysis; jitter preparation is included only when the requested
workflow reaches jitter sensitivity; OSS/pPAM preparation is included only
when activation sensitivity is requested. Once included, each producer remains
scale-independent and runs once per physical identity.

### Layer 2: scale-dependent statistical analysis

The analysis layer joins clinical rows and creates indexed views into prepared
resources. Direct voxel selects subject and voxel rows/columns. Normative fiber
selects subject and fiber rows/columns. No analysis task rescans E-field files,
connectome geometry, jittered geometry, or OSS simulation merely because a
scale changed.

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
  -> prepare requested OSS/pPAM rows on maximal support
  -> build endpoint row views
  -> run outcome-dependent observed models
  -> resolve source and final model
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
prepare_shared_oss_activation
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

For the current normative-fiber profile:

\[
\tau_{\min}=400\ \mathrm{V/m},
\qquad
C_{\min}=5.
\]

For a connectome and physical exposure family, define the maximal candidate
union over the maximal eligible physical subject cohort:

\[
\Omega_{\max}
=
\left\{
f:
\sum_i
\mathbf{1}\!\left[X_{i,f}\ge\tau_{\min}\right]
\ge C_{\min}
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
n_f(\tau)=\sum_i\mathbf{1}[X_{i,f}\ge\tau].
\]

For LOOCV held-out subject `h`, derive training Coverage by subtraction:

\[
n_{f,-h}(\tau)
=
n_f(\tau)
-
\mathbf{1}[X_{h,f}\ge\tau].
\]

All Coverage-grid masks follow from comparisons with configured Coverage
values. Fold-specific candidate support remains exact, but no fold reopens the
connectome or resamples an E-field.

## Scale-Independent Jitter And OSS Preparation

### Localization jitter

The physical jitter layer owns one deterministic perturbation schedule for each
configured subject/electrode/side/replicate identity. It generates perturbed
canonical side-specific E-fields and then derives both model-family exposure
forms without clinical input:

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

The previous rule that OSS rows are generated only after and only on
`final.valid_feature_axis` is superseded. For each formal connectome and
physical stimulation family, define:

\[
F_{\mathrm{OSS,prepare}}
=
\Omega_{\max},
\]

where `Omega_max` is the exact minimum-tau/minimum-Coverage maximal fiber union
defined above. OSS/pPAM is generated once per physical subject/program row on
this scale-independent axis. It is not generated over the complete normative
connectome.

For every realized endpoint final:

\[
F_{\mathrm{final}}
\subseteq
F_{\mathrm{OSS,prepare}}.
\]

The analysis layer selects the exact final columns by canonical fiber ID and
then performs fold-local weights, signed selection, scoring, nuisance fitting,
and OSS sensitivity statistics. A missing final fiber in the prepared OSS axis
is a preparation-contract failure.

For add-on models, OSS preparation stores raw add-on activation on
`F_OSS,prepare`. Reference-active overlap exclusion is applied later using the
endpoint's selected matched-reference source. This preserves branch-specific
semantics while allowing the expensive OSS simulation to remain scale-
independent.

The existing right-canonical OSS geometry rule, left-to-right transformation,
`max_probability_union`, ten-sample probability definition, and inclusive
`p(A) >= 0.5` threshold remain unchanged.

## Reusable Resource Inventory

### Required shared resources

| Resource | Reuse boundary | Required rule |
|---|---|---|
| Canonical right and transformed-left E-fields | subject/stimulation unit | Load once per process; use bounded LRU handles. |
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
| Jitter perturbation schedule | subject/electrode/side/replicate contract | Generate once without clinical input. |
| Jittered voxel/fiber exposure | physical jitter row plus model domain | Reuse across scales; endpoint statistics remain independent. |
| OSS/pPAM activation | formal connectome, physical stimulation row, and `Omega_max` | Generate once; endpoint finals select exact columns. |

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

## Exposure Cache Contract

### Existence-based reuse

No target cache or run artifact uses a cryptographic checksum as its reuse or
acceptance gate. The shared-exposure state machine is:

```text
required final file absent
  -> acquire one-producer lock
  -> recheck final file
  -> compute into a temporary sibling
  -> flush and close
  -> atomically rename to the final path

required final file present
  -> validate NPY header, dtype, dimensions, and finite declared axes
  -> reuse without rescanning source files or checksumming the payload
```

Temporary files never authorize reuse. A malformed final file fails closed and
requires explicit rebuild; it is not silently accepted.

The public `--force` control explicitly rebuilds the selected physical cache.
Because same-path input replacement is not detected automatically, users
must use `--force` or increment the cache schema/version when upstream E-fields,
connectome content, transforms, or scientific exposure definitions change.

### Deterministic path identity

The shared cache root is versioned:

```text
<cache_root>/shared_exposure_v2/
```

Paths are derived from stable study/configuration IDs, physical stimulation
binding, frequency class, canonical space, connectome ID where applicable, and
cache schema version. They do not contain scale, endpoint, outcome, run,
workers, or task order.

The cache uses atomic data files and compact axis/index files. It does not
require a checksum manifest or duplicate full matrices under endpoint task
directories.

### No-checksum boundary

Cryptographic checksums are removed from the complete target runtime contract,
including physical exposure, OSS rows, run artifacts, resume, provenance,
publication, and acceptance fixtures. These boundaries use deterministic
paths, stable semantic IDs, schema versions, file existence, structural
metadata, explicit status, and numerical comparison where applicable.

Historical runs may contain checksum fields because they were produced by an
older implementation. Those fields are inert historical data: the new runtime
does not regenerate, compare, or require them.

## Parallel Execution And Resource Scheduling

### Process-level parallelism

CPU/HDF5-heavy work must use processes, not a single-process thread pool.
`workers=12` is a global process-slot ceiling. It does not justify twelve
endpoint threads that serialize on one HDF5 handle.

On macOS, production workers use a `spawn` multiprocessing context. A parent
process sends only compact task descriptors and paths. It never pickles a
multi-gigabyte NumPy matrix or shares an open h5py handle with a child. Each
fiber-range worker opens the connectome once, reads only its assigned ranges,
and writes only its assigned temporary range.

Each worker must set numerical-library thread counts to one unless an explicitly
profiled task owns the whole machine:

```text
OMP_NUM_THREADS=1
MKL_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
VECLIB_MAXIMUM_THREADS=1
```

This prevents nested oversubscription.

The executor owns one global resource ledger:

```text
cpu_process_slots
memory_bytes
connectome_io_slots
external_solver_slots
```

A task starts only when all required resources are available. This avoids both
the current one-core serialization and the opposite failure mode of launching
twelve memory-heavy matrices or external solvers simultaneously.

### Stage-specific work units

```text
canonical E-field preparation:
  parallel by independent physical subject/stimulation unit

connectome exposure preparation:
  parallel by disjoint fiber ranges; each range evaluates all physical rows

jitter preparation:
  parallel by subject/electrode/replicate blocks; base E-fields and schedules
  are read-only shared inputs

OSS/pPAM preparation:
  parallel by independent subject/program/side rows with a separate external
  solver-slot limit

endpoint observed modeling:
  parallel by endpoint/model/connectome after shared exposure is ready

formal permutation/bootstrap:
  parallel by deterministic replicate blocks, then reduce in replicate order
```

Long monolithic tasks must be split into bounded units; otherwise a 12-worker
executor still uses one CPU core.

Initial stage ceilings for a 12-worker run are benchmarking defaults, not
public scientific parameters:

```text
lightweight endpoint analysis: up to 12 processes
dTOR fiber-range preparation: 6 to 8 processes
voxel/jitter exposure preparation: 4 to 8 processes
formal replicate blocks: up to 12 processes
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

Workers use work stealing across same-class ready items. Completion of one
fiber range, endpoint, or replicate block immediately frees its tokens and
admits the next item. Final reduction always sorts by canonical fiber ID,
endpoint ID, or replicate index so scheduling order cannot change results.

### Memory-aware admission

The scheduler combines the global worker ceiling with task memory estimates.
It must reserve at least the larger of 16 GiB or 20% of physical RAM, prevent
swap growth, and avoid allocating one full endpoint-specific fiber memmap per
worker. Shared matrices are read-only memmaps; endpoint inputs are indexed
views.

When runtime preflight confirms at least 64 GiB of currently available RAM, the
initial operating budget is:

```text
system and transient reserve: at least 16 GiB
shared resident/cache target: up to 32 GiB
active worker working sets: up to 16 GiB in aggregate
normal managed total: up to 48 GiB
```

The final 16 GiB remains uncommitted for the OS, filesystem cache fluctuations,
MATLAB/external solver peaks, and allocation variance. The scheduler may borrow
above the 48-GiB normal target only for one explicitly measured task and must
still preserve the reserve and zero-swap requirement.

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
Writers publish disjoint temporary ranges and perform one ordered merge.

Chunking is RAM-adaptive and deliberately coarse. Preflight calculates the
bytes required by connectome coordinates, lengths, offsets, IDs, physical
exposure rows, and worker scratch space:

```text
if complete connectome geometry fits the shared-resident budget:
  load geometry once into read-only shared memory/memmap
  let workers consume disjoint in-memory fiber ranges

otherwise:
  use large sequential ranges sized by actual point count and byte estimate
  align reads with HDF5 storage and canonical fiber boundaries
  process every physical exposure row while each range is resident
```

The default target for an out-of-core range is measured in hundreds of MiB to
several GiB, not tiny fixed fiber counts. The exact size is chosen from the
48-GiB managed budget, worker count, and connectome point density. A range may
be reduced only to preserve the 16-GiB system reserve or avoid swap.

Chunk count is minimized subject to those memory and concurrency constraints.
The scheduler chooses the fewest, largest safe ranges; it does not create tiny
ranges merely to match the worker count. While one range is resident, the
producer evaluates every configured physical exposure row, the minimum-grid
candidate indicators, and all scale-independent derivatives that require that
geometry. It then writes one contiguous range result before releasing the
geometry. Endpoint, scale, tau, Coverage, branch, and LOOCV-fold fan-out occurs
from the prepared arrays and may not trigger another raw-connectome read.

No resident range is reread for a different scale, tau, Coverage value, branch,
or LOOCV fold. The minimum-grid candidate union and all configured physical
rows are computed before releasing that range. Read-ahead and double buffering
may overlap loading the next large range with computation on the current one,
but must not create multiple full geometry copies.

Local-SSD staging is deferred until measurements show that storage, rather than
serialization or duplicate scans, is the remaining bottleneck.

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
change signed fiber scoring
change formal replicate counts
stage connectomes automatically onto local SSD
```

Jitter physical preparation and OSS/pPAM preparation are part of Layer 1.
Their endpoint-specific statistical analyses remain in Layer 2. Local-SSD
staging and a persistent trilinear connectome-point lookup remain optional
second-stage optimizations.

## Implementation Phases

### Phase 0: Characterization

1. Freeze deterministic small direct and fiber exposure fixtures.
2. Record current scan counts, wall time, CPU, RSS, I/O, and output arrays.
3. Add an instrumented counter for E-field loads and connectome range reads.

### Phase 1: Shared direct-voxel exposure

1. Resolve unique physical stimulation units before endpoint fan-out.
2. Produce one bilateral voxel row per physical unit.
3. Replace endpoint matrices with ordered row views.
4. Keep all direct-voxel numerical outputs equivalent.

### Phase 2: One-pass reduced fiber exposure

1. Introduce disjoint connectome-range iteration.
2. Evaluate all unique physical rows per range.
3. Apply exact minimum-grid `Omega_max` filtering.
4. Publish canonical reduced fiber IDs and continuous exposure rows once.
5. Prove no configured cell or fold loses a candidate.

### Phase 3: Shared jitter and OSS/pPAM preparation

1. Generate one deterministic localization-jitter schedule per physical input.
2. Materialize jittered voxel and fiber physical exposure without clinical
   input.
3. Generate OSS/pPAM rows on each formal connectome's `Omega_max` axis.
4. Replace final-axis OSS production with canonical-ID subsetting from the
   prepared maximal axis.
5. Apply endpoint-specific overlap, nuisance, fitting, and reporting only in
   Layer 2.

### Phase 4: Shared grid operators

1. Cache tau exceedance and Coverage tensors by exact subject axis.
2. Derive LOOCV fold counts by subtraction.
3. Compute endpoint/fold weights once on maximal support and mask by grid cell.
4. Reuse raw exposure ranks where exact axes match.

### Phase 5: Process scheduler

1. Replace CPU-heavy thread execution with process execution.
2. Add a dependency-aware persistent ready queue.
3. Add global process and memory admission control.
4. Shard formal replicate loops deterministically.

### Phase 6: Publication and cleanup

1. Stop copying shared exposure into endpoint task roots.
2. Remove cryptographic checksum generation and validation from cache, run,
   publication, provenance, resume, OSS, and acceptance paths.
3. Retain atomic publication, quick structural validation, and `--force`.
4. Delete no historical outputs; retire old cache producers only after parity.

## Planned Code Boundaries

Expected new modules:

```text
my_helper/fiber/core/dual_frequency/runtime/stimulation_units.py
my_helper/fiber/core/dual_frequency/runtime/shared_exposure.py
my_helper/fiber/core/dual_frequency/runtime/exposure_cache.py
my_helper/fiber/core/dual_frequency/workflow/resource_scheduler.py
my_helper/fiber/core/seed_target_connectivity/candidate_union.py
```

Expected modified modules:

```text
my_helper/fiber/core/dual_frequency/workflow/planner.py
my_helper/fiber/core/dual_frequency/workflow/executor.py
my_helper/fiber/core/dual_frequency/runtime/input_provider.py
my_helper/fiber/core/dual_frequency/runtime/service_adapters.py
my_helper/fiber/core/dual_frequency/cache/store.py
my_helper/fiber/core/seed_target_connectivity/connectome.py
my_helper/fiber/core/dual_frequency/backends/direct_voxel/kernel.py
my_helper/fiber/core/dual_frequency/backends/normative_fiber/reference.py
my_helper/fiber/core/dual_frequency/backends/normative_fiber/addon.py
my_helper/fiber/core/dual_frequency/backends/formal/
```

Names may be refined during implementation, but ownership boundaries and
behavioral contracts above must remain intact.

## Acceptance Contract

### Numerical equivalence

- Direct-voxel optimized exposure equals the existing bilateral voxel formula.
- Normative-fiber optimized exposure equals side-specific peak followed by
  arithmetic mean; the forbidden mean-before-peak formula is tested to ensure
  it is not substituted.
- Brute-force and reduced-connectome outputs match for all retained features.
- Every feature entering any production tau/Coverage cell appears in
  `Omega_max`; false negatives are forbidden.
- Full and every LOOCV fold candidate mask match brute force exactly.
- Observed weights, scores, predictions, source status, prediction status, and
  final realization match within existing numerical tolerances.
- Formal replicate ordering and statistics are invariant to worker count.
- Jitter perturbation schedules and physical exposure are identical across
  scales that use the same physical stimulation unit.
- Every endpoint OSS final axis is an exact canonical-ID subset of
  `F_OSS,prepare = Omega_max`.
- Subsetting prepared OSS rows reproduces the prior final-axis row values for
  the same fibers and physical stimulation inputs.

### Reuse behavior

- A 28-scale run creates one physical exposure producer set per unique
  stimulation/connectome identity.
- Requested jitter and OSS preparation each create one producer set per unique
  physical identity, not one set per scale.
- Changing only scale, endpoint outcome, run ID, worker count, or retry count
  produces a cache hit.
- Existing final cache files are reused without a payload checksum read.
- Missing files are produced once under a lock and atomically published.
- Partial temporary files are never accepted.
- `--force` rebuilds the selected cache explicitly.

### Performance behavior

- Instrumented complete-connectome range reads occur at most once in aggregate
  per connectome and cache version.
- Current-data physical row preparation decreases from 1540 endpoint-derived
  row scans per connectome to 42 unique physical rows evaluated during the
  shared pass.
- With `workers=12`, shared fiber preparation sustains at least six effective
  CPU cores for most compute-bound intervals unless measured storage throughput
  is the limiting resource.
- The performance report includes wall time, CPU utilization, peak RSS, swap,
  bytes read/written, cache hits/misses, connectome range reads, and physical
  rows evaluated.
- No test passes solely because more RAM was allocated; no run may enter swap
  due to duplicated endpoint matrices.

### State-machine closure

- Shared physical failure reaches every dependent endpoint deterministically.
- Independent endpoints continue.
- Outcome-dependent failures do not invalidate reusable physical exposure.
- No source/prediction/final status is changed by cache hit/miss or worker
  count.
- Formal and sensitivity remain attached only to the realized final model.

## Documentation Validation

Before implementation begins:

```bash
git diff --check
git diff --name-only -- '*.py' '*.m'
```

The second command must be empty for this documentation-only pass.

Contract searches:

```bash
rg -n "shared_exposure_v2|Omega_max|36.7|ThreadPoolExecutor|ProcessPoolExecutor|file existence|side-specific peak" \
  my_helper/stnsnr -g '*.md'

rg -n "File existence alone never authorizes reuse|content-addressed exposure|SHA-256|hash-valid" \
  my_helper/stnsnr/four_model_yaml_core_refactor_plan.md \
  my_helper/stnsnr/dual_frequency_core_decoupling_design.md \
  my_helper/stnsnr/dual_frequency_core_decoupling_implementation_plan.md
```

Any remaining old statement must be marked as historical/current
implementation and non-authoritative. No target cache, run, provenance,
resume, activation, or acceptance path is exempt from the no-SHA decision.

## Closed Decisions

```text
all scales reuse physical E-field exposure
direct voxel averages left/right voxel fields once
normative fiber peaks each side first and averages the two peaks second
minimum tau and Coverage define an exact maximal fiber candidate union
retained fiber values remain continuous
raw add-on exposure defines only an upper bound before overlap exclusion
cache reuse is final-file existence plus quick structural validation
no target cache, artifact, resume, provenance, OSS, or acceptance gate uses SHA
CPU-heavy preparation uses processes and disjoint work units
endpoint statistical results remain independent
jitter schedules and jittered physical exposure are prepared before scale analysis
OSS/pPAM is prepared on formal-connectome Omega_max before scale analysis
endpoint jitter and OSS statistics select subsets and remain outcome-dependent
```

There are no unresolved scientific choices in this performance-refactor
contract. Implementation details may change only when they preserve every
closed decision and acceptance gate above.
