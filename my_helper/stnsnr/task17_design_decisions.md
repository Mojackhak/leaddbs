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

Worker-local NIfTI samplers use a byte-bounded least-recently-used cache. The
durable transformed entry remains shared, while decoded arrays are evicted
before sequential subjects multiply one worker's resident memory without
bound.

## Decision 12: Bound MATLAB Transform Stalls

The first production smoke produced no CPU activity or output for several
minutes inside one MATLAB transformation. The transformer therefore runs in a
dedicated process group with a bounded timeout. Timeout termination preserves
the semantic producer identity, leaves no published cache entry, and causes the
task to fail so a new lineage or eligible resume can retry it safely.

## Decision 13: Do Not Time Out a Live Semantic Producer

The first all-scale run showed that a valid cold physical producer can exceed
the former fixed lease wait. A waiter now refreshes its wait deadline whenever
the lock still names a live producer PID. A dead PID is quarantined immediately;
an unreadable lock still has a bounded timeout. Producer-specific MATLAB and
external-tool timeouts remain responsible for terminating stalled children.

## Decision 14: Fit the Bilateral Decoded E-Field Working Set Before Fiber Resume

The corrected production rerun measured sixteen canonical-left float32
E-fields at about 4.2 GiB. Fiber sampling also needs sixteen right fields, so
the complete bilateral decoded working set is about 8.4 GiB. That value is
`> 2 GiB` and `> 5 GiB`; both tested worker-local LRU limits repeatedly evicted
and decompressed unchanged NIfTI files while traversing successive fiber
chunks. Each affected lineage reached 364 completed tasks with no failure
before it was safely interrupted.

The worker sampler budget is raised to 10 GiB, which is `> 8.4 GiB`, and one
unchanged NIfTI path is structurally validated only once per process. The
prepare-exposure resource grant is raised to 13 GiB so the parent ledger
charges the decoded samplers, bounded output memmap, process baseline, and
connectome chunk rather than hiding them in the reserve. The existing
connectome-I/O ceiling still bounds simultaneous cold producers.

This change affects execution resources only. Scientific cache identity,
physical-row identity, task identity, strict comparisons, and output values do
not change. Code SHA is retained as audit provenance and does not gate resume.

## Decision 15: Close Full-Cohort Transform and Add-On Fiber-Axis Failures

The full-cohort, all-scale production lineage showed that 300 seconds was `<`
valid cold MATLAB left-to-canonical transformation time. The transformer keeps
its dedicated process group and bounded termination contract, but the limit is
raised to 1800 seconds. Timeout still publishes no cache entry, terminates the
whole child process group, quarantines temporary output, and releases the
producer lease. This is a runtime correction and does not change transform
identity or interpolation.

The same lineage proved that an add-on fiber axis derived only from its primary
`Omega_max` can omit IDs needed by the matched reference valid union. Relaxing
the DeltaReference membership check would silently alter the scientific
contrast, so that check remains strict. Instead, an accepted add-on dependency
uses a run-scoped parent-ordered union of its primary `Omega_max` and the exact
locked reference valid-union IDs. The augmented axis identity binds the parent
axis, primary `Omega_max`, locked reference axis, and ordered union positions.
An ID absent from the parent connectome axis remains a hard error. The durable
physical exposure and pure primary `Omega_max` caches are unchanged.

Persistent workers reached about 14.1 GiB RSS after large bilateral fiber
preparation. Since 14.1 GiB is `< 16 GiB`, the parent ledger now charges 16 GiB
for preparation. The I/O ceiling still permits fewer than 3 simultaneous cold
connectome producers, keeping managed memory within the documented production
budget.

The correction passes 417 dual-frequency tests and 224 parameterized subtests.
These tests retain strict DeltaReference membership failure while proving that
the prepared add-on axis contains the required locked reference IDs in parent
connectome order.

## Decision 16: Reduce Resume to Three Gates

The final authorized resume contract has exactly three gates:

1. The current study-base JSON content SHA matches the run's recorded JSON SHA.
2. The ordered content SHA values of the workflow, direct-voxel, and normative-
   fiber YAML files match the recorded values; source paths are ignored.
3. A task-state JSON exists, parses, declares `completed`, and contains a
   decodable result object.

No code SHA, derived configuration hash, scientific-configuration hash, plan
hash, resolved-configuration comparison, service/producer identity, artifact
metadata, artifact path, or artifact payload rehash is a resume gate. Failed,
running, skipped, missing, malformed, and incomplete task JSON is rerun. Code
and effective resource settings remain execution-segment provenance only. The
interrupted v6 lineage, with 202 completed tasks produced after the add-on axis
fix, is the selected resume root.

The implementation passes 418 dual-frequency tests and 224 parameterized
subtests. A completed result with malformed or incomplete JSON is treated as
unfinished and rerun; it does not introduce another resume rejection gate.

## Decision 17: Validate the Locked Reference Axis Against Its Reference Parent

The resumed v6 run reached 844 completed tasks before two DeltaReference tasks
showed that membership and selected-axis identity require different parent
axes. The augmented add-on prepared parent is the authority for membership and
column order. The matched reference prepared parent is the authority used to
recompute the locked reference selected-axis SHA. The builder now receives both
records explicitly. It keeps strict missing-ID and order failures and does not
change tau, Coverage, weights, folds, scoring, or the three resume gates.

The correction passes 419 dual-frequency tests and 224 parameterized subtests.

## Decision 18: Keep Extension DAGs Final-Linked And Formal-Free

The post-checkpoint extension is a new analysis lineage, not a delayed formal
run. Its compiled prerequisite closure may contain completed parent records
needed to reconstruct the final-linked request, but it may not execute observed,
resolver, final-realization, formal-permutation, or formal-bootstrap services.

The generic one-shot plan keeps its historical phase ordering. The extension
compiler removes formal task dependencies and the formal-complete gate only
from copied jitter and OSS target specifications. Task IDs remain stable because
they identify endpoint, stage, branch, and scientific parameter identity rather
than dependency layout. Parent observed and final records are seeded as
completed records in the child RunStore; they are not invoked again.

Acceptance must inspect actual service invocations, not only successful output.
Separate jitter, OSS, and combined extension cases must report observed,
resolver, final-realization, formal-permutation, and formal-bootstrap invocation
counts `< 1`.

## Decision 19: Distinguish Missing Sensitivity Sources From Invalid Checkpoints

A copied, valid jitter or OSS cache entry remains reusable when its original
physical source files are unavailable. The checkpoint supplies the recorded
source-content identity needed to reconstruct the same semantic lookup. A cache
miss may consult physical sources only after lookup. If both the exact prepared
entry and a required physical source are absent, the task fails with the stable
reason `missing_sensitivity_source` before any substitute computation.

Checkpoint corruption, payload SHA failure, array-header failure, axis mismatch,
and incomplete direct copies remain validation failures. They are not reported
as missing sources and never fall back to a producer.

## Decision 20: Close Sensitivity Acceptance Before Production Extension

The production main run may continue with the already loaded runtime while the
extension boundary is audited. No production jitter or OSS extension starts
until tests cover jitter-only, OSS-only, combined selection, no main or formal
service reinvocation, one-shot parity, copied-cache startup, pre-task corruption
failure, source-absent cache reuse, explicit missing-source failure,
worker-count invariance, and missing-task-only extension resume.

The extension run manifest retains the resource settings from the first
invocation as lineage provenance. Every new invocation records its effective
workers and resource limits in a new execution segment. Resume may therefore
change workers without rewriting the immutable lineage annotation.

The immutable `sensitivity_plan.json` stores the selected analyses, scientific
configuration identity, stable task IDs, dependencies, gates, and services. It
does not store the execution-configuration hash because that hash includes
workers and other invocation settings. The full effective hash remains in the
run and execution-segment audit records.

Artifact resume compares the immutable core identity only: artifact ID, kind,
URI, and payload SHA. Reporting may add task references and descriptive
metadata to the same index row. Those additions are preserved and do not turn
an exact task retry into an identifier collision.

## Decision 21: Keep Runtime Facts Scoped To Their Scientific Owner

`formal_source_available` is owned by the matched formal source or formal final
selection. A sensitive-connectome reference evaluation publishes only its own
`reference_source_accepted` fact. Re-publishing the formal fact from the
sensitive result conflates two connectome roles and can create a false
contradiction when the formal final exists but the sensitive evaluation is not
computable.

The sensitive add-on formal-cell gate therefore reads formal availability from
the formal-final lineage and sensitive-reference acceptance from its separate
reference-dependency lineage. Neither state overrides the other.
