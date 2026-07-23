# Task 17 Design Decisions

## Status

```text
decision_record_active
task17_implementation_in_progress
partial_synthetic_acceptance_passed
oss_axis_gate_synthetic_acceptance_passed
production_configuration_validated
corrected_production_rerun_required
```

This record captures choices made while reconciling the Task 17 performance
plan, the later sensitivity-extension requirement, and deletion of the previous
run artifacts. It is subordinate to explicit user instructions but
authoritative when the implementation plans are silent or internally
inconsistent.

## Decision 1: Inclusive E-field and Coverage boundaries

The user's 2026-07-17 correction includes equality at the three reopened model
boundaries. E-field values below tau are inactive and all other values are
active. Candidate counts below Coverage are excluded and all other counts are
included. Reference-component values below the selected reference tau are
inactive and all other values enter overlap. Boundary fixtures must admit exact
tau, exact Coverage, and exact selected-reference-tau values.

This change does not reopen support-QC, pPAM, null-tail counting, input
validity, numerical tolerance, or array-bound predicates. pPAM retains
`p(A) > 0.5`. Derived support, overlap, candidate, and activation artifacts
bind `inclusive_threshold_v1`; raw continuous physical exposure remains
comparator-independent.

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
- exact inclusive-boundary `Omega_max` construction;
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

The implementation checkpoint above describes implemented components, not
closure of their complete performance contract. Decision 22 records the
current code-grounded gap audit and supersedes any broader reading of this
summary.

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
physical-row identity, task identity, then-current comparisons, and output values do
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

Legacy completed task JSON may still contain the superseded cross-connectome
fact. Gate resolution therefore uses the nearest dependency layer that
publishes the requested fact. A direct formal-final fact takes precedence over
a deeper sensitive-reference ancestor. Opposite values published at the same
nearest layer remain contradictory and fail closed.

## Decision 22: Separate Physical-Row Deduplication From One-Pass Preparation

The current production implementation deduplicates endpoint requests onto
scale-independent physical rows, but its cache-miss path still calls
`_compute_binding_matrix` once for each physical row. Each call traverses the
connectome geometry independently. This satisfies endpoint-to-physical-row
deduplication but does not satisfy the Task 17 requirement to keep a point
range resident and evaluate every required physical row before advancing to
the next range.

The v6 production lineage is therefore historical compatibility and checkpoint
evidence. It can prove its own strict-boundary resume behavior, cache reuse,
final realization, and later extension isolation, but cannot authorize the
corrected inclusive-boundary result. It also cannot by itself prove the
one-pass connectome acceptance gate or the target CPU-utilization matrix.

The remaining implementation work is explicit:

- compile the complete physical-row catalog before fiber production;
- acquire one producer authority for the ordered row batch;
- scan each connectome range once and evaluate all batch rows while resident;
- publish row-addressable final shards without merging a second monolith;
- prove raw geometry scan count `> 0` and `< 2` for each connectome and batch;
- prove the produced row values match the side-specific peak
  then bilateral-mean implementation within the existing tolerance.

The cache publication path also still copies a completed temporary NPY into a
same-parent staging directory while hashing it. This preserves atomicity and
direct-copy validation but does not satisfy single-write large-payload
publication. The batch producer must write final shard bytes directly into its
staging entry while calculating payload SHA, then publish the completed
manifest and atomically rename the directory.

The current sensitivity checkpoint validates copied cache entries, but a
production jitter cache hit still derives its key only after hashing source
paths and opening the feature-space source. Missing source files therefore
fail before cache lookup. Decision 19 remains the target; cache-first lookup
must use parent-recorded semantic identities and defer all physical source
access until an exact cache miss.

The executor currently owns one persistent pool for a fault-free invocation.
It does not yet provide hard-worker exit recovery, generation replacement,
heartbeat timeout handling, or periodic process-tree memory reconciliation.
Those gates remain open even though the fault-free single-generation test
passes.

No Task 17 completion statement may treat any of these open items as acceptance
evidence. Documentation status changes to complete only after the corresponding
code, focused regression tests, production or bounded acceptance evidence, and
full requirement audit all pass.

## Decision 23: Stop The Extension DAG At Completed Direct Parent Records

The completed production checkpoint contains 1204 seed outcomes, 17888 artifact
references, and 4059 unique artifact paths. Eagerly rehydrating every seed
outcome would read about 151.5 GB before the extension plan is known. The same
checkpoint's combined jitter and OSS targets have only 308 distinct direct
parent tasks, and every one has a completed seed outcome.

The former recursive extension closure is too broad. For the combined request
it contains 476 observed-phase specifications and 112 sensitivity targets.
Twenty-eight of those observed specifications are intentionally skipped parent
branches and have no completed seed. Leaving them executable would violate the
rule that an extension invokes no observed, resolver, or final-model service.

The child-plan boundary is therefore:

- remove formal dependencies and the formal-complete gate from each requested
  sensitivity target;
- require every remaining direct parent task to have a completed seed outcome;
- include each completed direct parent as a dependency-free, gate-free child
  root and restore its result before execution;
- include only those roots and the requested sensitivity targets;
- never expand a restored parent into its historical ancestors;
- fail checkpoint loading or enter explicit rebuild mode when a required
  direct parent seed is absent.

Checkpoint loading is also two-stage. Metadata loading validates the completed
parent manifest, every selected `sensitivity_base.json`, the final-model
artifact set, and every declared shared-cache entry before the sensitivity DAG
starts. Identical final artifact paths are payload-hashed once in that parent
process. Only the direct seed roots selected by the compiled child plan are
then rehydrated. Unrelated historical seed outcomes are not read or hashed.
Artifacts outside the explicitly validated final set remain subject to exact
`ArtifactStore` validation when a selected sensitivity service first consumes
them.

Records restored at the checkpoint boundary retain their original causal task
IDs. Those IDs are immutable parent-run lineage and need not appear as child
tasks. Extension reporting must classify them as external parent provenance;
it must not enlarge the child DAG merely to satisfy a report-local closure
check. Every causal ID that is local to the extension must still belong to the
extension plan, while external IDs remain anchored by
`base_run_reference.json`, the parent manifest SHA, and the validated seed
bundle.

This boundary does not weaken the portable-cache contract. Every shared entry
still receives complete payload SHA and structural validation on first use in
each process, and corruption of a declared final artifact or shared-cache
payload still fails before any sensitivity service invocation.

## Decision 24: Parallel Jitter Uses Fixed Reduced-Axis Physical Blocks

The first production extension attempt exposed a structural scheduler failure.
Twelve endpoint tasks entered the same first jitter replicate. One worker held
the cache producer lease while eleven workers waited inside their services. No
jitter entry was published during the first two minutes, and the producer was
building a 16 by 8465824 voxel matrix for one replicate. Repeating that path for
1000 replicates would serialize physical production and would create endpoint-
local full-exposure copies. The interrupted extension is retained as resume and
performance evidence, but it is not an accepted production run.

Jitter production is therefore split into explicit physical block tasks before
endpoint statistics. Replicate ranges are fixed groups of 25 and do not depend
on worker count. The production checkpoint currently has three physical groups:
reference voxel, add-on voxel, and formal reference fiber. Each group has 40
ordered ranges for the 1000-replicate schedule. The final-axis union sizes are
386 reference voxels, 418 add-on voxels, and 10098 formal fibers, so physical
blocks use those reduced ordered axes instead of the complete brainmask or
connectome axis.

The first production exercise of this block design, retained as
`task17-jitter-v2-20260717`, exposed a second I/O boundary before any block was
published. Twelve independent workers remained CPU-busy for more than three
minutes because the producer traversed all subjects inside each replicate. The
per-worker sampler LRU has a 10-GiB production ceiling, but the complete
physical source set approached or exceeded that residency boundary, so later
replicates repeatedly decompressed the same NIfTI payloads. The accepted
producer traversal is component, then physical subject, then the fixed
replicate interval. This keeps each subject's small source set hot while all 25
translations are sampled and limits each block to one source load per physical
row. The interrupted v2 run is evidence only and is not resumed.

The next production exercise, retained as `task17-jitter-v3-20260717`, proved
that block admission also has to charge the real per-process working set.
Twelve reordered reference-voxel producers consumed roughly 40 GiB of child
RSS before the first block was published. The ledger charged only 2 GiB per
producer and checked each grant against the managed budget without enforcing
the cumulative managed ceiling. The run was stopped before cache publication;
swap did not grow, and v3 is evidence only rather than a resume source.

The first cumulative-ledger exercise, retained as
`task17-jitter-v4-20260717`, admitted six reference-voxel producers at 8 GiB
each. After roughly 11 minutes, each producer had reached more than 8.5 GiB of
RSS and the summed child RSS had passed 51 GiB without publishing a block.
System memory pressure remained low and swap did not grow, but the measured
working set had crossed the declared managed boundary. The run was stopped
before cache publication and is evidence only rather than a resume source.

The accepted admission charge is therefore 12 GiB for every physical jitter
block, with one additional connectome-I/O slot for a fiber block. The normal
managed ceiling is 64 GiB, and cumulative active grants never go above
that ceiling. The projected available memory after admission must remain
`> reserve`. With 12 public workers, these charges permit at most five voxel
producers or two fiber producers at once; lower available memory can reduce
those counts. This worker reuse is intentional: each admitted process can
finish later blocks with already resident samplers instead of multiplying cold
source loads across twelve processes.

The v5 exercise proved that per-group endpoint dependencies were still too
weak for that reuse contract. All 80 voxel blocks completed, after which voxel
endpoint statistics became runnable while 40 reference-fiber blocks remained.
Those statistics expanded the persistent pool from four processes to twelve.
Although only two fiber producers held connectome-I/O grants, later fiber
ranges could be dispatched to newly idle processes without resident E-field
samplers. Hot fiber ranges took roughly 1.2 minutes, while two cold ranges took
roughly 13.7 minutes each. Short process samples placed both cold workers in
NIfTI gzip decompression. The 32 unique reference E-fields occupy roughly
8.27 GiB uncompressed, which fits below the 10-GiB sampler ceiling; the defect
was worker rotation rather than insufficient reference-source capacity.

The retained v5 evidence contains 80 voxel blocks, 23 reference-fiber blocks,
and all 56 voxel endpoint jitter results. It published 103 complete block cache
entries, left no producer lock, and did not grow swap. It is not resumed as the
accepted production run.

Every jitter endpoint task now depends on the complete ordered physical-block
task set, not only its own physical group. The persistent pool therefore stays
within the producer population until all 120 blocks finish. Only then may the
84 endpoint statistics expand the same pool to the public worker ceiling. The
barrier changes scheduling dependencies only; block identities, replicate
ranges, RNG order, cache keys, and endpoint scientific inputs remain unchanged.
When no physical-block capability exists, the legacy typed-provider path keeps
its original dependencies.

Each block identity binds:

- the ordered parent shared-exposure identities;
- model family and connectome role;
- the ordered union feature IDs and union-axis SHA;
- the physical subject axis;
- root seed, translation schedule, and replicate start and stop;
- the physical sampling rule and producer version.

The block contains the replicate axis, physical subject axis, union feature
axis, ordered feature IDs, ordered replicate seeds, and the required exposure
components. Reference blocks contain the primary component. Add-on blocks also
contain the reference-condition and add-on reference-component arrays required
to rebuild overlap and DeltaReferenceScore inputs.

Cache lookup occurs before source discovery. A complete copied block can be
used when the original E-field, transform, or connectome is unavailable. A
cache miss may produce the block only when the required physical sources are
available; otherwise it fails with `missing_sensitivity_source`. Source absence
never invalidates a complete block and never causes fabricated data or fallback
to an unperturbed exposure.

Block producers run as ordinary tasks in the one persistent workflow process
pool. They do not create a nested executor. Different ranges can occupy
different workers, while cache identities and RNG order remain invariant under
worker-count changes. Endpoint jitter tasks start only after their group's
blocks complete. They mmap each verified block once, select endpoint subject
rows and final features in memory, and write only compact replicate statistics
and small DeltaReferenceScore evidence. They do not publish endpoint-local full
jitter exposure arrays.

The extension compiler enables physical blocks only for the production runtime
or an explicitly injected provider that exposes the physical-block capability.
An injected replicate provider without that capability keeps its original typed
replicate path; the planner does not attach cache-block dependencies that the
provider cannot consume.

An add-on final on the no-delta branch does not rebuild an unused
DeltaReferenceScore during jitter. Its support status is explicitly
not-applicable, while overlap exclusion is still rebuilt from the perturbed
add-on and reference-component arrays. An adjusted add-on final may use the
reduced block path only when the block also carries support-preserving evidence
for the complete parent universe. Until that evidence format is implemented,
an adjusted final stays on the existing full-parent replicate provider and is
not assigned to a reduced block group. This preserves the support definition
without blocking a scientifically valid extension. The current production
checkpoint contains 28 no-delta add-on voxel finals and no adjusted add-on
final, so its reduced add-on blocks preserve every input used by the realized
final branch.

Large block payloads use a generated-entry cache publication path. Final NPY
bytes are streamed into the cache staging generation while their payload SHA is
computed, then the completed manifest and directory are atomically published.
There is no work-memmap copy, endpoint exposure copy, or post-publication full
payload read by the producer.

## Decision 25: Correct Boundaries, Fold Gate, And Formal Connectome

The user's 2026-07-17 correction is one atomic scientific configuration
change:

- direct-voxel and normative-fiber exact tau values are active;
- exact Coverage counts are eligible;
- exact selected-reference-tau values enter overlap;
- every configured `fold_candidate_fibers_min` is one, so each LOOCV fold must
  retain at least one candidate fiber;
- `ppmi_85_ewert_2017` is the unique `formal` connectome, while
  `mgh_usc_hcp_32_horn_2017` and `dtor_985_full_elias_2024` are `sensitive`;
- `n_subjects_min: 12` remains unchanged for both model families.

The completed `task17-main-v6-20260716` and interrupted
`task17-jitter-v6-20260717` lineages used superseded strict boundaries and
nonzero fold minima. Neither may be resumed as the corrected formal result.
Comparator-independent continuous physical-exposure cache entries may be
reused after their normal portable SHA and structural validation, but derived
support, candidate, overlap, source, final, and inferential artifacts must be
rebuilt under `inclusive_threshold_v1` in a new run lineage.

After code, configuration, and tests pass, the next formal invocation runs the
main workflow through its configured formal outputs only. It does not compile
or execute jitter or OSS-DBS. Those extensions require a later explicit
authorization and must use the corrected parent lineage.

## Decision 26: Keep Degenerate Bootstrap Draws As Explicit Attrition

The corrected formal lineage
`task17-main-v7-inclusive-ppmi-formal-20260717` exposed a subject-bootstrap
boundary that is absent from the fixed observed and permutation fits. The
`eat_10` baseline has twelve zero values among sixteen subjects. Its sixth
deterministic draw contains fifteen zero values and one value of seven; the
LOOCV fold that removes the only nonzero value has a rank-deficient
intercept-plus-baseline nuisance design. The `dsfs` draw at replicate 8784 has
the same structure with fifteen values of two and one value of four. These are
valid with-replacement bootstrap draws, not malformed endpoint inputs.

A sample-specific nuisance design that becomes non-estimable after a valid
bootstrap draw is replicate attrition. It does not invalidate the endpoint,
the original nuisance design, or the complete bootstrap task. The backend must
retain the original deterministic draw schedule and replicate axis, must not
redraw or condition the bootstrap distribution on estimability, and must mark
only that replicate as non-estimable. Its candidate mask remains computable
from the sampled exposure, while its valid-weight count and support code remain
absent. Feature weights, signs, and signed-fiber selections receive no
contribution from that replicate.

The published summary records requested and finite replicate counts plus the
number of non-estimable nuisance draws. Nuisance QC records the exact replicate,
stable reason code, and diagnostic detail. The technical result is
`completed_with_nonfinite_replicates` when at least one requested draw has no
finite weight. A fixed original nuisance design that is non-estimable remains
a fatal endpoint-input error. Provider identity, stale adjusted-score, shape,
axis, and provenance failures also remain fatal; this decision does not turn
contract violations into bootstrap attrition.

After implementation and focused regression tests, the current main lineage
finishes its independent work and resumes only failed bootstrap tasks through
the existing three resume gates. No jitter or OSS-DBS task is authorized by
this repair.

## Decision 27: Refit The Matched Reference Inside Adjusted Bootstrap

An adjusted add-on subject bootstrap requires a task-scoped production
`BootstrapNuisanceProvider`. The provider is constructed only after the
formal request has selected `delta_reference_adjusted`; reference and
no-delta bootstrap remain provider-free. Its direct task closure contains the
add-on input, prepared exposure, observed DeltaReferenceScore bundle and final
selection, plus the matched reference input, prepared exposure, dependency
record and accepted locked source. The closure is validated by endpoint,
model-family, connectome, subject identity, parent feature axis, selected
feature axis, tau and Coverage before the first draw is evaluated.

For every ordered bootstrap sample, add-on subject IDs map to the matching
reference rows and retain their exact multiplicity and order. The provider
then refits the reference full-sample weights and every LOOCV fold weight on
that sampled reference cohort. Direct voxel uses the same inclusive
tau/Coverage candidate rule, partial-Spearman weights and benefit orientation
as its observed kernel. Normative fiber uses the same inclusive candidate
rule, partial-Spearman weights, benefit orientation, locked valid-union fiber
IDs and signed score settings as its observed backend. Neither model may add
features outside the accepted reference source axis.

The newly fitted full and fold operators score the sampled difference between
the add-on reference-component exposure and its matched reference-condition
exposure. DeltaReferenceScore support is recomputed from the complete parent
feature axis with the configured support profile. The provider returns only
the raw full/fold score arrays, support evidence and identity-bound rebuild
provenance; it does not publish ten thousand per-replicate artifacts. Reusing,
indexing or permuting the original DeltaReferenceScore remains a fatal stale-
input violation.

Provider identity, dependency, shape, axis and provenance violations remain
fatal. Once those contracts have passed, sample-specific matched-reference
rank loss, absence of a finite full or fold operator, invalid sampled support,
or rank/scaling loss during construction of the adjusted nuisance plan is
replicate attrition under Decision 26. It preserves the requested replicate
axis and does not trigger a replacement draw.

Adjusted nuisance QC contains rebuild support and provenance for every finite
provider result, and the non-estimable table contains every attrited replicate
with its exact index and reason. These two disjoint sets must jointly cover the
complete requested replicate axis. A reference or no-delta bootstrap has no
provider evidence and therefore records only any non-estimable rows.

The adjusted bootstrap tasks gain these direct dependencies without changing
their `TaskKey`, whose identity is endpoint, stage, branch and configuration.
Therefore the corrected provider can resume the current v7 lineage while
retaining every already completed task outcome. Only failed or unfinished
tasks execute again. Jitter and OSS-DBS remain outside this run.

## Decision 28: Replace Only The Two Tau Grids For The New Formal Lineage

The authorized rerun changes only the direct-voxel and normative-fiber tau
configuration. The direct-voxel grid is 150, 180, 200, 220, 250, and 300 V/m,
with 200 V/m as the pre-specified source. The normative-fiber grid is 200, 350,
400, 450, 600, and 800 V/m, with 400 V/m as the pre-specified source.

The Coverage grids, inclusive threshold policy, minimum adjacent support,
hard-computability limits, connectome roles, score fractions, selected-count
minima, resampling counts, and add-on support policy remain unchanged. The new
lineage runs through formal outputs with fourteen workers. Jitter and OSS-DBS
are not requested and must not appear in its plan. The completed formal parent
remains eligible for a later separately authorized sensitivity extension.

## Decision 29: Align Adjusted Fiber Bootstrap Across Two Parent Axes

The v8 formal lineage exposed four fail-fast errors in the adjusted add-on
fiber bootstrap for FSS, KPPS, ODQ, and PDQ39. The matched reference prepared
exposure and the add-on prepared exposure intentionally use different parent
fiber axes. The former is the canonical matched-reference parent, while the
latter is the add-on reference union that defines the two add-on
reference-component exposure matrices. Parent-axis identity is therefore not
a valid fiber bootstrap requirement.

The accepted matched-reference valid-union fiber IDs remain the single locked
scientific feature axis for every bootstrap refit. The provider must locate
that ordered ID vector independently in the matched-reference parent and the
add-on parent. The matched-reference exposure is sliced with the first position
vector. The add-on reference-condition exposure and add-on reference-component
exposure are sliced with the second position vector. All three resulting
matrices must present the locked fiber IDs in their original accepted order
before any full-sample or LOOCV operator is fitted or scored.

Both parent ID arrays and the locked selected ID array must contain unique
integers. Every locked selected ID must occur in both parents, and its ordered
position vector must preserve each parent's deterministic order. A missing ID,
duplicate ID, order violation, malformed array, or incompatible exposure shape
remains a fatal provider error. The implementation must not form an
intersection, drop a fiber, reorder the locked selected axis, or substitute the
add-on final feature axis for the accepted matched-reference source axis.

The direct-voxel provider retains its existing shared-parent-axis contract and
single selected-index vector. Reference bootstrap, no-delta bootstrap,
observed models, final realization, formal permutation, jitter, and OSS-DBS do
not use this repaired fiber bootstrap alignment path.

After focused regression and dual-frequency test suites pass, the existing
`task17-main-v8-tau-grid-formal-20260717` lineage resumes through the three
established resume gates. The 1508 completed task outcomes must be restored
without execution, while only the four failed adjusted add-on fiber bootstrap
tasks return to pending work. Acceptance requires all 1512 tasks completed,
no failed task, unchanged completed-task payload digests, and completed formal
bootstrap results for the four named endpoints. The repair does not authorize
jitter, OSS-DBS, or combined sensitivity execution.

The completed repair met this acceptance contract. Five focused dual-parent
alignment regressions and seventy-three directly related formal, adapter,
DeltaReferenceScore, and input-provider tests passed. The complete
dual-frequency suite passed 452 of 454 tests; its two remaining failures are
the previously stale configuration expectations for the authorized v8 tau
grid and do not enter the bootstrap provider path. Compilation and diff checks
passed.

Resume execution segment `segment_0002` used fourteen spawn workers, finished
without swap growth, restored the original 1508 completed task payloads with
an unchanged aggregate digest, and executed only the four failed bootstrap
tasks. KPPS retained 7907 finite draws and 2093 explicit nuisance-attrition
draws. ODQ retained 7906 and 2094. FSS retained 7903 and 2097. PDQ39 retained
7906 and 2094. Every pair covers the complete 10000-draw deterministic axis.
The run manifest is completed with 1512 completed tasks, 224 final decisions,
112 sensitivity bases, and 7468 indexed artifacts. No jitter, OSS-DBS, or
combined extension task was planned or executed.

## Decision 30: Add Default Final In-Sample Inference And Paired Reporting

Every realized final model now requires an in-sample inference result whenever
formal permutation inference is in scope. This behavior is part of the formal
workflow contract and has no separate YAML enable switch. It inherits the
endpoint's existing formal permutation count and resolved seed. The public
configuration therefore remains unchanged.

The in-sample path and the LOOCV path may share the subject ordering, prepared
physical exposure, nuisance inputs, candidate definition, and a deterministic
residual-permutation schedule. They must not share an outcome-dependent fit.
For each observed or pseudo-outcome, in-sample inference fits once on the full
subject axis, while LOOCV fits independently inside every held-out fold.

The test is explicitly conditional on the realized final model. It locks the
actual selected tau, Coverage, final branch, overlap exclusion, complete
subject axis, prepared exposure, and outcome-independent candidate voxel or
fiber IDs. It does not lock observed voxel weights, fiber weights, benefit
orientation, sweet IDs, sour IDs, weighted-peak IDs, spatial scores, or final
regression coefficients. Those values are recomputed under every
pseudo-outcome. The result does not adjust for tau/Coverage search, fallback,
branch selection, or source resolution and must carry the conditioning label
`conditional_on_selected_tau_coverage_branch_and_candidate_axis`.

The primary in-sample statistic is Spearman rho between the outcome and the
full-sample fitted prediction. The report mirrors the existing LOOCV Spearman,
Pearson, nominal-p, formal permutation-p, RMSE, MAE, baseline-error, and finite-
result fields. It additionally reports standard in-sample and LOOCV R2 values
against the outcome total sum of squares, and pairs the in-sample nuisance-
relative R2 with the existing LOOCV Q2. No adjusted R2 is reported because the
outcome-derived voxel/fiber fitting path has no fixed interpretable effective
degrees of freedom. Paired optimism gaps are emitted only when both paths use
the same transformed outcome, subject ordering, and finite-subject mask.

Formal raw permutation p values receive two Benjamini-Hochberg corrections:
one across the 28 scales in each model family and one across all 112 final
endpoints. Nominal correlation p values remain descriptive and are not used in
the primary multiplicity correction. A correction layer is published only
when its complete predeclared raw-p family is available.

A small explicit residual-permutation index artifact records the schedule,
subject-axis identity, resolved seed, bit-generator identity, RNG-contract
version, and requested count. The current v8 parent did not publish such an
artifact, and its null-statistic vector does not independently reveal the
underlying subject-index rows. The child therefore uses an independent
deterministic schedule and reports `independent_deterministic_schedule`; it
does not claim replicate-level pairing with the parent LOOCV null. New main
lineages report `shared_explicit_schedule` only when both explicit schedule
payload SHA values match.

The first implementation deliberately matches current formal-permutation
persistence: one endpoint task computes and atomically publishes its complete
null vector. There is no public or internal fixed 250-replicate block contract.
An interrupted endpoint reruns as a whole, while valid completed endpoint task
JSON is reused. Task 17's future shared formal-sharding work may shard both
LOOCV and in-sample paths together only after its historical-RNG parity and
resume gates pass; this in-sample addition does not introduce one-sided
sharding ahead of that work.

The completed v8 parent remains immutable. A `final_in_sample` child extension
rehydrates its final-model, endpoint-input, prepared-exposure, DeltaReference,
and formal-permutation checkpoint roots, computes only the in-sample path, and
builds a paired report from the inherited LOOCV evidence. Future main lineages
schedule the same in-sample task automatically beside formal permutation and
bootstrap.

The implementation and formal v8 child are accepted. The complete generic
dual-frequency suite passed 459 tests and 239 subtests. The first child startup
restored all parent checkpoints but failed before numerical work on one shared
production-record field lookup; the typed-key repair has a dedicated
production-provider regression. Endpoint-level resume then restored the same
504 checkpoint roots and completed all 112 new endpoint tasks with fourteen
workers. Every endpoint produced 10000 finite in-sample permutation statistics,
paired metrics, an explicit schedule, and a summary. Both 28-scale family BH
layers and both 112-endpoint BH layers completed. The child contains no jitter,
OSS-DBS, bootstrap, observed-grid, source-resolver, or final-realization
execution.

## Decision 31: Gate Shared OSS Rows Before Endpoint pPAM

The formal OSS extension adds two cache-first group tasks ahead of endpoint
pPAM: one for reference fiber and one for add-on fiber. Group identity binds the
ordered final axis, ordered `Omega_max`, formal connectome, physical rows,
toolchain, RNG contract, and comparison tolerance. The completed v8 parent is
not rewritten. Its already declared shared-cache identities let the loader
recover and validate the exact `Omega_max` descriptor in memory.

The original planner estimate was 34 reference and 26 add-on row classes, but
production created a 35th reference decision and therefore invalidated those
counts as an acceptance denominator. Each group gate must enumerate its actual
physical row classes and commit their exact ordered `row_decision_ids` closure.
For every committed class, the gate compares ten sample-wise axon-state vectors
from a final-axis run and an `Omega_max` run after exact canonical-ID
subsetting. PASS requires state mismatch count `< 1`, activation-count mismatch
count `< 1`, and maximum probability difference below the fixed internal
tolerance. Every per-row decision is immutable and independently resumable;
only the two terminal gate closures define the authoritative count.

Only complete PASS coverage moves that group to shared `Omega_max` simulation.
Any unproven, corrupt, or failed row keeps the whole group on the historical
final-axis path. Both row products remain valid standard caches, while public
activation matrices and endpoint fitting remain locked to the final feature
axis. The row cache stores no per-fiber manifest item list and writes each
payload once. The corrected independent OSS plan has 590 tasks; the combined
plan has 1194 tasks.

## Decision 32: Resolve Final-Linked Prepared Exposure By Endpoint

The v8 jitter child completed all 240 physical blocks and both reference model
families, then ten add-on endpoint tasks failed because their dependency
closures contained more than one `PreparedExposureRecord`. This multiplicity
is expected: an add-on closure carries its own prepared exposure and the
matched-reference prepared exposure required to rebuild physical contrast.

Every final-linked adapter now resolves the target prepared exposure by the
current task endpoint identifier rather than by record type alone. Exactly one
endpoint-local match is required. Missing or duplicate endpoint-local matches
fail closed, while a distinct matched-reference record remains available to the
typed jitter provider. Spatial jitter and OSS activation share this rule.

The change is orchestration-only. It preserves completed blocks, seeds, feature
axes, task IDs, result schemas, and scientific cache identities. Resume restores
the 790 completed v8 tasks and reruns only the ten failed add-on endpoints. Tests
must cover target-plus-reference inputs for jitter and activation, the unchanged
reference path, and both endpoint-local failure cases before formal resume.

## Decision 33: Bound OSS Omega Rows And Cascade External Termination

The first repaired independent OSS resume established the complete final-axis
ten-sample result for one reference physical row, then entered the corresponding
10320-fiber `Omega_max` row. Its first sample passed the FEM stages but the OSS
process RSS grew beyond 48 GiB and later reached about 72.8 GiB while the main
process was being stopped. This violates the formal managed-memory boundary.
The main process exited before its separately sessioned OSS subprocess, leaving
that solver temporarily orphaned until it received a direct termination signal.
No row decision or standard row cache had published, and swap did not grow.

The accepted repair partitions only the external execution axis into ordered,
contiguous chunks containing `< 3501` fibers. Chunk boundaries and identities
derive deterministically from the full row identity and ordered feature IDs.
Every chunk repeats the same ten fixed diameter samples and unchanged
stimulation, geometry, material, waveform, and connectome-source contracts.
Chunk state matrices concatenate in the original canonical order. Only the
complete logical row product receives the existing standard cache identity;
chunks are runtime implementation details and never become public axes, cache
items, endpoint features, or independent statistical replicates.

The group gate and any solver-capable observed activation task charge 48 GiB.
The resource ledger must reject a grant above its managed boundary even when no
other task is running. This is a conservative admission charge that prevents a
second solver from entering the 64-GiB managed pool; it is not a post-admission
hard RSS limit for the sole admitted solver. Production resume remains
prohibited until a real reference `Omega_max` chunk keeps complete task-tree RSS
`< 64 GiB`, swap growth `< 1` byte, and the configured system reserve intact.
If that evidence fails, the fixed chunk bound must decrease before another
formal resume.

Every external command remains in its own process group. While waiting for that
command, the worker must intercept termination, terminate the complete external
process group with the existing bounded TERM-to-KILL policy, and then exit. A
process-level regression must terminate a worker during an active child command
and prove that no live descendant remains. The interrupted formal child retains
its 196 completed parent roots, failed and interrupted runtime workspaces, and
all valid immutable caches; resume re-evaluates the incomplete gate only after
these two repairs pass focused and complete regression.

The implementation repair passed 62 focused OSS/executor tests and the complete
dual-frequency regression passed 534 tests plus 310 subtests in the `leaddbs`
environment. These synthetic and process-level results close the code gate but
do not replace the still-required real reference-chunk RSS acceptance.

The next monitored segment reached an exact 3500-fiber reference `Omega_max`
chunk. One-second sampling measured solver RSS at 45,910,048,768 bytes and the
complete descendant tree at 46,284,881,920 bytes. Available memory stayed above
77,078,921,215 bytes, swap growth stayed `< 1` byte, and VAL remained mounted.
The segment was stopped under the earlier 32-GiB task charge. That charge is
replaced by a measured 48-GiB solver grant while the cumulative managed ceiling
remains 64 GiB and the sole-solver token remains unchanged. This avoids
duplicating FEM and OSS work through smaller execution chunks without admitting
the historical unchunked row that reached about 72.8 GiB.

Segment 0004 completed all ten samples of one exact 3500-fiber `Omega_max`
chunk. One-second sampling measured a solver peak of 42,068,082,688 bytes and a
complete-descendant peak of 42,447,421,440 bytes. Minimum available memory
remained 78,255,472,640 bytes, swap growth stayed `< 1` byte, and VAL remained
mounted. The completed chunk workspace was removed and the next ordered
3500-fiber chunk began, proving successful return rather than mere process
termination. The real resource gate is therefore closed for formal continuation
under the 48-GiB sole-solver charge and 64-GiB cumulative ceiling.

Later one-second formal sampling measured 61,986,045,952 bytes of solver RSS
and 62,497,554,432 bytes across the complete task tree. The task tree remained
`< 64 GiB`, swap growth remained `< 1` byte, the system reserve remained
intact, and no second solver entered. This evidence supersedes the earlier
solver-RSS `< 48 GiB` wording while preserving the 48-GiB admission charge,
single-solver token, and 64-GiB task-tree hard ceiling.
