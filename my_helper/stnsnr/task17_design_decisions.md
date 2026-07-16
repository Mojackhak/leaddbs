# Task 17 Design Decisions

## Status

```text
decision_record_active
task17_implementation_in_progress
synthetic_acceptance_passed
production_configuration_validated
production_outputs_missing
production_rerun_required
```

This record captures choices made while reconciling the Task 17 performance
plan, the later sensitivity-extension requirement, and deletion of the previous
run artifacts. It is subordinate to explicit user instructions but
authoritative when the implementation plans are silent or internally
inconsistent.

## Decision 1: Strict scientific thresholds

The latest Task 17 authority requires strict comparisons throughout the
reopened threshold set:

```text
E > tau
count > Coverage
reference > selected_tau
p(A) > 0.5
```

Values on any reopened boundary are excluded. Earlier draft text that admitted
the E-field or Coverage boundary is superseded. Historical fixtures remain
evidence of predecessor behavior, while target fixtures exercise and exclude
every boundary explicitly.

## Decision 2: Directly copyable portable cache

A cache entry may be copied directly to its final semantic directory. There is
no importer, incoming area, machine identity, cache-instance identity,
installation marker, or persistent verification database.

Every process fully verifies each entry on first use, then retains its
`semantic_sha256` in a process-local verified set. Later consumers in the same
process perform only requested structural checks. A new process, including a
resume or sensitivity-extension process, verifies the entry again.

Local producers still write final-format payloads into a same-parent staging
directory, calculate payload SHA while writing, write the manifest last, and
publish with an atomic directory rename. A directly copied partial or corrupt
entry fails closed but is neither deleted nor adopted automatically.

On the production external volume, macOS represents extended attributes as
AppleDouble `._*` sidecars. These sidecars are filesystem metadata rather than
cache payloads, so exact payload inventory ignores them. Every declared
scientific file remains mandatory and every other ordinary extra file still
fails validation.

## Decision 3: One manifest and bounded axis metadata

Each entry has one `manifest.json`, one `semantic_sha256`, and one
`payload_sha256` per payload or shard. The manifest contains structural array
metadata and strictly ordered shard intervals. It does not contain one JSON
record per fiber. An explicit `fiber_ids.npy` payload is used only when an
implicit range axis is insufficient.

There is no generation manifest, directory-combination digest, cache payload
sidecar, device/inode/mtime identity, or repeated RunStore hash of bytes just
published by the trusted in-process writer.

## Decision 4: Main run as a sensitivity checkpoint

A main run may stop after final-model realization. Every realized final emits a
durable `sensitivity_base.json` that references only durable run artifacts,
portable cache entries, and declared source inputs. Scratch paths are
forbidden.

A later process creates a separate sensitivity-extension run. It references an
immutable parent run and executes only requested jitter, OSS, or other
final-linked sensitivity tasks when the parent checkpoint is complete.

## Decision 5: Rebuild a missing parent chain

The previous run root, canonical model outputs, and study-base artifact have
been deleted. Task 17 therefore cannot assume that a parent checkpoint exists.

The sensitivity command accepts the same explicit study-base and profile inputs
as a main run. When the requested parent run or any required observed,
resolver, final-model, or sensitivity-base artifact is missing, an explicit
rebuild mode creates a new parent lineage, runs the missing main chain through
final realization, writes a new sensitivity checkpoint, and then starts the
extension run. It never repairs or mutates a partially deleted historical run.

If `study_base.json` is also missing, the project-owned upstream converter must
be run explicitly before the generic main run. The generic runtime never
imports or invokes project code implicitly.

## Decision 6: Extension output isolation

The extension has its own run ID, run manifest, task states, artifact index,
and resume lineage. Canonical extension publication lives below a unique
`extensions/<extension_id>/` directory under the existing model set. Existing
main-run artifacts are never overwritten.

Internal RunStore JSON indexes remain supported during migration. Task 17 also
publishes the required CSV artifact-index snapshot so the documented extension
contract is satisfied without breaking existing readers.

## Decision 7: Source availability for later physical sensitivity

Base exposure alone cannot generate a new spatial jitter realization or a new
OSS row. A sensitivity extension may run when either the required physical
sources and toolchain remain available or the corresponding prepared jitter or
OSS cache entry is present.

Missing sources with a valid prepared cache permit statistical reuse. Missing
sources and missing prepared cache produce `missing_sensitivity_source`; no
fallback, substitution, or implicit expensive production is allowed.

## Decision 8: Resource and identity separation

`execution.workers`, CPU/BLAS/solver caps, memory admission, I/O admission,
timeouts, and scratch location are execution provenance. They do not enter
scientific cache identity after worker-count invariance is proven.

Scientific thresholds, ordered axes, seeds, source-content identity, producer
semantics, and schema versions remain immutable across resume and extension
runs.

## Decision 9: Verification timing and expected cost

Full payload SHA verification happens during the first cache lookup in each
process, before any dependent scientific task starts. Within-process repeat
verification count is `< 1`; full verification count per used entry and process
is `> 0` and `< 2`.

Manifest, header, and axis checks are small relative to payload hashing. Typical
shared exposure entries are expected to take seconds to tens of seconds on
first use; very large jitter or OSS entries may take minutes. This bounded
startup cost is accepted in exchange for direct-copy support and removal of
persistent trust state.

## Decision 10: Complete Task 17 scope

Task 17 remains one complete objective. Direct-copy cache, sensitivity
extensions, missing-parent rebuild, shared physical preparation, persistent
process scheduling, resource admission, resume correction, numerical parity,
and resource acceptance are all required before completion. Implementing only
the extension runner or only the cache contract cannot close Task 17.

## Implementation Checkpoint

The current implementation now provides:

- strict voxel, fiber, overlap, support-QC, and pPAM boundaries;
- scale-independent physical-subject exposure keys and endpoint row subsets;
- exact strict `Omega_max` construction;
- directly copyable v2 cache entries with complete first-use SHA and structural
  validation in every process;
- one cross-process producer lease per semantic entry;
- main-run sensitivity checkpoints, isolated jitter/OSS extension runs,
  extension resume, and missing-parent rebuild into a new lineage;
- one persistent event-driven pool, macOS spawn workers for production,
  numerical-library thread caps, parent-only RunStore updates, resource
  admission, and one execution-segment record per invocation;
- dependency-derived skip reevaluation on resume.

The generic suite passes, and production configuration validation reports 28
scales, 224 available endpoints, and 1288 tasks through final realization. The
remaining completion evidence is the production rerun plus measured resource,
worker-recovery, source-absent cache reuse, single-write payload, and authorized
OSS axis-equivalence gates.

## Decision 11: Share Canonicalized Left E-Fields

Production spawn smoke showed that a worker-local left-to-canonical directory
causes the same MATLAB transformation to be repeated by voxel and fiber workers.
Canonicalized left E-fields therefore use the same v2 semantic cache authority
as other physical inputs. Their identity binds source content SHA, transform
content SHA, interpolation, canonical space, and producer version while
excluding worker, run, scale, endpoint, and scratch paths.

The first producer holds the semantic producer lease, writes one transformed
NIfTI, validates it, and publishes it atomically. Other processes validate the
copied cache entry once and reuse the NIfTI directly. Worker scratch remains a
temporary producer location only and cannot be referenced by a completed task.

## Decision 12: Bound MATLAB Transform Stalls

The first production smoke produced no CPU activity or output for several
minutes inside one MATLAB transformation. The transformer therefore runs in a
dedicated process group with a bounded timeout. Timeout termination preserves
the semantic producer identity, leaves no published cache entry, and causes the
task to fail so a new lineage or eligible resume can retry it safely.
