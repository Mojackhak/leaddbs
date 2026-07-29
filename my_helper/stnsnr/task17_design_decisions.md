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

## Decision 34: Reduce OSS Execution Chunks After Add-On Resource Failure

The terminal reference gate accepted 34 decisions and 68 row caches, but the
first add-on `Omega_max` execution showed that the prior 3500-fiber bound was
not portable across the realized geometries. The external one-second guard
observed one solver ramp from 44519882752 bytes to 69068636160 bytes in about
31 seconds and emitted `rss_limit_sigterm`. This crossed the strict 64-GiB
task-tree ceiling without swap growth or a second solver. No add-on decision or
standard row cache published.

The accepted repair reduces the internal maximum to 2800 fibers. The add-on
7193-fiber `Omega_max` axis remains three execution chunks, now 2800, 2800,
and 1593 fibers. Chunking remains an unpublished execution detail; the exact
ordered full-axis product, scientific row identity, decision identity, and
resume contract do not change. Existing completed reference decisions remain
valid and the interrupted add-on task resumes from its first missing logical
row.

The stopped runner left one reparented persistent worker, which was explicitly
terminated after all descendants disappeared. Resume requires focused
chunk-order, full-axis concatenation, cache/resume, and termination regression,
then a new execution segment with a new one-second guard. The first real
maximum-size add-on chunk must complete with task-tree RSS `< 64 GiB`, swap
growth `< 1` byte, and no stop event before continued production is accepted.

Implementation sets the bound to 2800 and adds the exact add-on layout
fixture. The focused OSS, gate, cache, and executor suite passed 124 tests; the
complete package-scoped dual-frequency suite passed 610 tests. Production
acceptance still depends on the real guarded add-on chunk rather than these
synthetic results.

## Decision 35: Preserve V1 Sensitivity Plans Across Default Scheduler Fields

The first post-repair OSS resume regenerated the same 590-task scientific plan
but could not pass the byte-exact immutable-plan check. Every regenerated task
contained three scheduler fields introduced after the original lineage was
created: `timeout_seconds: null`, `transient_safe: false`, and
`max_transient_retries: 0`. The persisted v1 plan omitted those fields. A
complete structural comparison found no task, dependency, key, analysis,
scientific parameter, or other value difference; removing only these default
fields made the documents identical.

Resume compatibility for `sensitivity_plan.json` therefore treats an omitted
v1 scheduler field as its exact canonical default. This exception applies only
to the three fields above and only when the regenerated value is exactly the
default. A non-null timeout, enabled transient policy, positive retry count,
unknown missing field, scientific difference, task-order difference, or schema
difference still fails closed. The existing immutable file is compared but
never rewritten.

This compatibility rule does not change task identity, completed outcomes,
cache identity, or scientific results. Tests must prove default-field
compatibility, rejection of every non-default scheduler value, rejection of a
scientific task change, and byte preservation of the old plan before formal
resume. The implementation passed all four focused compatibility checks, the
real 590-task plan comparison while preserving the old file bytes, and the
complete 613-test package regression.

## Decision 36: Split The Real 2004-Fiber Add-On Row

Segment 0011 proved that the 2800-fiber maximum did not constrain every
resource-critical add-on row. The first retried row contained 2004 fibers, so
it ran as one execution. During sample 01, the token-free guard measured a
complete task-tree peak of 66341486592 bytes. This remained below 64 GiB, but
swap increased by 720896 bytes and the guard emitted
`swap_growth_sigterm`. The segment stopped with 197 completed tasks, the same
one incomplete add-on gate, and 392 dependency-derived skips. No standard
add-on row or equivalence decision published, and no runner, worker, solver, or
guard process remained after termination.

The OSS bootstrap already fixes NGSolve to one thread before entering its task
manager. The failure therefore cannot be repaired by reducing NGSolve
parallelism further. The execution maximum is reduced to 1800 fibers. The
observed 2004-fiber row becomes ordered chunks of 1800 and 204 fibers, while a
7193-fiber axis becomes 1800, 1800, 1800, and 1793 fibers. This remains an
execution-only partition; concatenation, scientific row identity, cache
identity, decision identity, and completed reference evidence remain
unchanged.

Before another formal resume, tests must cover the new exact layouts, complete
ordered-axis reconstruction, and unchanged process termination. The next
guarded segment must complete a real 1800-fiber chunk with task-tree RSS
`< 64 GiB`, swap growth `< 1` byte, and no stop event. A synthetic pass does
not close this production resource gate. The 1800-fiber implementation passed
125 focused OSS, equivalence, cache, and executor tests and the complete
614-test package regression.

## Decision 37: Reduce The Add-On Bound To 1500 Fibers

Segment 0012 executed a real 1800-fiber chunk for `sub-SNr020`, right side,
30 Hz. OSS retained 1334 axons inside the computational domain. During the
high-frequency field-copy sequence, the token-free guard measured
69279547392 bytes and emitted `rss_limit_sigterm`. This exceeded the strict
64-GiB task-tree limit while swap growth remained `< 1` byte. The task ledger
remained at 197 completed, one incomplete add-on gate, and 392
dependency-derived skips. No standard row or equivalence decision published,
and no runner, worker, solver, or guard process remained.

The 1800-fiber bound is superseded by 1500 fibers. The observed 2004-fiber row
becomes 1500 and 504 fibers. A 7193-fiber axis becomes 1500, 1500, 1500, 1500,
and 1193 fibers. This reduces the measured maximum execution by one sixth while
limiting the known largest axis to five solver chunks. Chunking remains an
unpublished execution partition and does not change the complete ordered row,
scientific identity, cache identity, decision identity, or accepted reference
evidence.

The next formal resume requires updated exact-layout and ordered-concatenation
tests plus the complete regression. A new one-second guard must then prove a
real 1500-fiber chunk completes with task-tree RSS `< 64 GiB`, swap growth
`< 1` byte, and no stop event.

The 1500-fiber implementation and exact-layout fixtures pass 125 focused OSS,
equivalence, cache, and executor tests and the complete 614-test package
regression. Only the guarded production resource gate remains open.

## Decision 38: Bound Time-Domain Reconstruction At 750 Fibers

Segment 0013 disproved the 1500-fiber production bound. The real add-on chunk
contained 1500 fibers for `sub-SNr015`, right side, 30 Hz. OSS retained 1046
axons inside the computational domain. The task tree remained near
56380178432 bytes through frequency-domain field copying, then reached
70575407104 bytes when time-domain reconstruction created the time-result
payload. The guard emitted `rss_limit_sigterm`; swap growth remained `< 1`
byte. No standard row or equivalence decision published, the task ledger
remained unchanged, and no process survived.

The 1500-fiber bound is superseded by 750 fibers. This halves the failing
chunk's axon-dependent time-result payload while retaining the measured fixed
field-solver cost. Applying the observed payload increment conservatively to a
fully retained 750-fiber chunk leaves more than 2 GiB below the strict 64-GiB
task-tree limit. The 2004-fiber row becomes 750, 750, and 504 fibers. A
7193-fiber axis becomes nine 750-fiber chunks plus 443. Chunking remains an
execution-only partition with exact ordered concatenation and unchanged
scientific, cache, row, and decision identities.

The implementation requires updated exact-layout fixtures, focused regression,
and complete package regression before segment 0014. Production acceptance
still requires a real guarded 750-fiber chunk with task-tree RSS `< 64 GiB`,
swap growth `< 1` byte, continuous VAL writability, and no guard stop event.

The 750-fiber implementation and exact-layout fixtures pass 125 focused OSS,
equivalence, cache, and executor tests and the complete 614-test package
regression. Only the guarded production resource gate remains open.

Segment 0014 has supplied the first durable production confirmation for this
bound. At least one complete 750-fiber add-on computation published its paired
final and Omega rows plus equivalence decision
`8c8614c12b2155a4b71232fd146feeb4657f1fdff71ed63bd8c6b9c699539991`.
The decision belongs to `oss_axis_group_eaf54b8ab53dc387916e`, has status
`pass`, maximum probability difference `0`, state mismatch count `0`, and
activation-count mismatch count `0`. The segment-wide task-tree RSS peak so
far is 46507081728 bytes, swap has not increased, VAL remains mounted, and the
guard has emitted no stop event.

This is positive intermediate evidence, not terminal acceptance. The add-on
gate is still running, its authoritative `row_decision_ids` closure is not yet
committed, and the 392 dependency-derived downstream tasks have not yet been
released. Raw cache-directory counts must not substitute for that closure.

## Decision 39: Separate OSS Scientific Identity From Execution Attestation

A read-only compatibility audit on 2026-07-24 found that Decisions 34, 36, 37,
and 38 state the intended contract but the current implementation does not
preserve it. The terminal reference closure contains 34 decisions and 68 rows,
all under implementation fingerprint
`definition-sha256-5cd672ef7e82fe9f273c40a6fe93eb1c58ace921a54a87ea574087cc507ce055`.
Rows durably published by the running add-on gate use
`definition-sha256-960551ea005f8f30f78fec1fa9c9ec9a479e98f36d9e4f6388810bf34362e8d2`,
while the current checkout resolves
`definition-sha256-2505d33c0e658849ac9ecd604a30a83db7f0dc4e962400f1a63a45c560532539`.
The reference group also contains 35 completed decision cache entries outside
its authoritative terminal closure, split across two intermediate
implementation fingerprints. They are not accepted group evidence, but they
demonstrate that execution-only source changes have already caused redundant
row identities.

The cause is exact and bounded. `oss_backend_version()` hashes every production
Python file below `my_helper/fiber/core/dual_frequency` plus the locked external
definitions. `StudyRuntimeInputProvider` places that value in
`OSSScientificSettings.backend_version`; the row key stores it directly and
also includes it indirectly through `OSSScientificSettings.parameter_hash`.
Changing the execution chunk maximum, scheduler, resource validator,
publication code, or another non-scientific module therefore changes the row
and decision identities even when every explicit OSS setting and scientific
payload is unchanged. The three-gate task resume contract preserves a completed
reference gate, but a fresh cache-only gate or combined child derives different
keys and can incorrectly report a miss.

The corrected contract has two identities:

1. The OSS scientific cache identity uses the stable internal semantic version
   `ossdbsv2-ppam-scientific-v1`, exact ordered fiber axis, geometry,
   stimulation, component frequency, transform, formal-connectome content, and
   all explicit `OSSScientificSettings` values. Worker count, execution chunk
   size, scheduler, memory limits, resource monitors, publication code, run ID,
   repository SHA, and complete implementation fingerprint are excluded.
2. Decision 51 later supersedes the complete current-producer attestation
   described in this Decision 39 checkpoint. The live producer performs no
   repository hash or before-and-after source comparison. Promoted historical
   fingerprints remain readable in `compatibility_source.json` only as
   immutable provenance and never control lookup, resume, direct-copy
   portability, or use of a previously completed scientific payload.

Changing a scientific definition requires an explicit new semantic version.
Changing only execution policy retains the existing version. This is the
enforceable boundary requested by the resume contract: code identity alone
does not make an unchanged result unusable, while a declared scientific
contract change cannot reuse the old key.

Legacy promotion is cache-first and never invokes OSS. On an exact stable-key
miss, the resolver may inspect completed legacy `oss_rows` entries only when:

- kind, backend name, geometry, stimulation, component frequency, transform,
  formal-connectome hash, and ordered-axis hash equal the current request;
- the legacy `oss_ppam_v1` hash equals the current explicit settings
  recomputed with that legacy `definition-sha256-*` value;
- full manifest and payload SHA verification succeeds and the stored fiber IDs
  exactly equal the requested ordered axis; and
- every compatible legacy candidate has identical fiber-ID and probability
  payload SHA values.

Zero candidates is a normal miss. Conflicting candidates fail closed. One
scientifically unique payload is atomically republished under the stable key
with compatibility provenance; the legacy entry remains immutable. A legacy
axis-equivalence decision is promoted only when its group, paired legacy rows,
status, tolerance, zero state mismatch, zero activation-count mismatch, and
maximum probability difference `< 1e-7` all validate against the corresponding
current requests. The stable final and Omega rows publish before the stable
decision, and the group manifest remains the final commit.

The code gate requires tests proving that:

- changing 750 to another execution-only chunk value does not change the stable
  row or decision identity;
- changing any scientific input or explicit OSS setting does change identity;
- copied legacy reference and add-on caches promote with expensive producers
  unavailable and reproduce byte-identical scientific arrays;
- one missing legacy row fails before toolchain construction or solver launch;
- corrupt, axis-mismatched, parameter-mismatched, ambiguous, and conflicting
  legacy candidates fail closed;
- a legacy pass decision promotes only after both paired rows validate; and
- Decision 51 replaces the former implementation-drift failure fixture with a
  regression proving that an on-disk repository change does not fail row
  production.

The active independent gate must finish under the implementation identity it
already resolved. No production source file may be changed while its external
solver is active. After terminal independent acceptance, the compatibility
repair and tests precede canonical OSS-v2 publication and the no-authorization
combined extension. Existing reference rows are retained and must not be
recomputed merely to obtain the stable identity.

A terminal accepted group recorded before this repair remains scientifically
valid, but ordinary resume would otherwise restore its completed task without
invoking the stable-key promotion path. Resume therefore validates only
completed `OSSAxisEquivalenceGroupRecord` values with
`gate_status=accepted_omega_max` against their referenced decision and row
caches. When every referenced row uses the stable scientific backend version,
the task is restored normally. When the accepted group still references
historical implementation-keyed rows, or one referenced accepted cache entry is
missing or invalid, resume replays that gate and its descendants. The replay is
forced cache-only even if the original invocation allowed expensive producers.
It may promote exact historical rows and pass decisions, but it must fail
before toolchain construction on any true miss, corruption, mismatch,
ambiguity, or conflict. This is output-reference completion validation, not a
repository SHA resume gate, and it never recomputes a historical scientific
payload merely to change its address.

## Decision 40: Separate Cache-Only Admission From Solver Admission

The first production replay after Decision 39 created `segment_0016` and
restored 196 terminal tasks without invoking the OSS toolchain or solver. It
then stopped before scheduling either ready equivalence gate. The scheduler
gave both gates the solver-capable 48-GiB memory, connectome-I/O, and solver
grant even though the terminal reference gate had been forced to cache-only
historical promotion. At that sample the dynamic managed-memory ceiling was
49758738842 bytes, which was `< 48 GiB`; both ready tasks were therefore
resource-blocked and the empty running set was incorrectly classified as a
dependency deadlock.

This is an execution-admission defect, not cache corruption or scientific
incompatibility. The terminal reference closure remains 34 pass decisions and
68 complete rows. The partial add-on closure remains three pass decisions and
six complete rows. No row or decision was written by `segment_0016`.

The corrected admission contract is:

1. A `cache_first_expensive` task that is not authorized to invoke its
   expensive producer receives a cache-read grant of 512 MiB, no connectome-I/O
   token, and no solver token. This includes a Decision 39 migration replay
   even when the enclosing command allows expensive producers.
2. The same task receives its declared 48-GiB, connectome-I/O, and single-solver
   grant only when a true miss is authorized to reach the producer.
3. If every dependency-ready task is blocked only by a dynamic memory
   predicate, the production scheduler keeps the tasks pending, samples live
   memory once per second, and retries admission after recovery. It does not
   misclassify temporary memory pressure as a dependency deadlock.
4. A grant that cannot fit below the structural worker, I/O, solver, physical
   memory, reserve, or 64-GiB limits still fails immediately. Dependency cycles
   and missing dependency outcomes also remain immediate errors.
5. The external guard remains the hard operational stop for VAL loss,
   task-tree RSS not `< 64 GiB`, or swap growth not `< 1` byte. Waiting for
   dynamic admission does not authorize a solver, mutate a cache, or add a
   scientific timeout.

Acceptance requires a cache-only equivalence gate to run with no solver grant,
a solver-capable task to remain pending across one low-memory sample and run
after a later admissible sample, and a structurally impossible grant to fail
without an unbounded wait. Production resume must then prove that reference
promotion performs no solver call and that the first solver work belongs only
to a missing add-on row.

The implementation now passes 157 focused tests plus 36 subtests and the
complete dual-frequency discovery passes 727 tests plus 326 subtests with
warnings treated as errors. The new fixtures prove the 512-MiB cache-only
grant, zero cache-only I/O and solver tokens, immediate structural rejection,
and recovery from a low-memory idle interval into an authorized 48-GiB solver
grant. Production evidence remains required.

Production `segment_0017` accepted the Decision 40 admission repair. It
promoted and committed the terminal reference group as 34 decisions and 68
rows without a reference solver call. The add-on gate retained its three pass
decisions and six complete historical rows, entered only its missing producer
work, and then failed when a later MATLAB preprocessing command returned code
1 with empty standard-output and standard-error logs. The segment closed with
393 completed tasks, one failed add-on gate, and 196 dependency-derived skips.
Its complete task-tree RSS peak was 20272988160 bytes, which was `< 64 GiB`;
swap growth was `< 1` byte and the guard emitted only `runner_exit`.

A bounded post-failure MATLAB batch printed `TASK17_BATCH_READY` and returned
success in about 14 seconds. This supports a transient MATLAB batch-start
classification rather than a cache, OSS numerical, or resource-contract
failure. The failed workspace and every published cache remain preserved.
Resume may retry the failed add-on gate in a new guarded segment without
replaying the now-stable reference group or any completed add-on cache.

## Decision 43: Produce Only Omega-Max OSS Rows

The user rejected per-physical-condition final-axis versus `Omega_max`
production as redundant after the completed production evidence showed exact
numerical containment. At the supersession boundary, 34 reference pairs and 11
add-on pairs had stable scientific cache identities. Every one of the 45
paired decisions passed with maximum probability difference `0`, sample-state
mismatch count `0`, and activation-count mismatch count `0`. The paired cache
therefore provides 45 directly reusable stable `Omega_max` rows. Fifteen
add-on physical conditions remain missing from the frozen 26-condition add-on
inventory.

This evidence changes the production architecture, not the pPAM scientific
definition:

1. A production physical condition creates or restores exactly one
   `Omega_max` OSS row. It never invokes the solver for the final feature axis.
2. A final feature row is a virtual canonical-ID indexed view of the
   `Omega_max` row. It is not a separately produced or published OSS cache
   entry.
3. The production DAG contains one group-level `Omega_max` preparation task
   before endpoint pPAM fan-out. It contains no per-condition equivalence
   decision task or decision cache.
4. Group completion records the exact ordered closure of stable `Omega_max`
   row identities. Resume fully validates that closure, reuses every valid
   row, and produces only a genuinely missing `Omega_max` row.
5. Historical final rows and equivalence decisions remain immutable evidence.
   They neither gate the new lineage nor authorize a missing `Omega_max` row.
6. Structural checks remain mandatory: the final IDs must be ordered unique
   positive integers, the `Omega_max` IDs must be ordered unique positive
   integers, and every final ID must map exactly once into `Omega_max`.
7. Numerical subset invariance becomes a versioned certification test. The
   certification must cover representative reference and add-on conditions,
   both sides, component-frequency modes, small and large axes, and
   multi-chunk concatenation. It reruns when the OSS scientific backend
   version, explicit scientific settings, canonical fiber ordering, subset
   mapping, or external result adapter changes.

The new production record is `OSSSharedOmegaGroupRecord`. It binds the model
family, final and `Omega_max` axes, portable `Omega_max` descriptor, endpoint
closure, exact `omega_row_ids`, and one atomic group summary. The compiler
service is `prepare_oss_omega_max_rows`; old
`OSSAxisEquivalenceGroupRecord` values remain decodable for historical
lineages but are not emitted by a new plan.

The stopped dual-production lineage
`task17-oss-v1-inclusive-formal-20260719` remains resumable only as historical
evidence and must not restart. A new independent OSS lineage uses the same
completed main parent and shared scientific cache. Its reference preparation
must be cache-only across all 34 `Omega_max` rows; its add-on preparation must
reuse the 11 completed stable `Omega_max` rows and invoke the single solver
token only for the 15 missing rows. No final-row solver call or new axis
decision publication is permitted.

Acceptance requires a focused invariant-certification suite, cache-hit and
legacy-promotion fixtures, one-missing-row producer proof, copied-cache resume,
corrupt-row rejection, exact group-closure validation, downstream pPAM
subsetting parity, and the complete dual-frequency regression. Production
resume remains guarded by the pinned VAL mount generation, task-tree RSS
`< 64 GiB`, swap growth `< 1` byte, one solver token, and atomic cache
publication.

Implementation evidence at this boundary is complete. Documentation commit
`dc3dc6543` froze this decision before code changed, and implementation commit
`0d41b5e5d` added the new record, codec, compiler task, cache-first runtime,
resume validator, downstream cache-only pPAM boundary, and performance-harness
compatibility. The focused old/new OSS, codec, planner, executor, pPAM, cache,
and performance set passed 153 tests. The production-checkout dual-frequency
suite then passed 762 tests. After the previously reviewed performance and
paired-fit branch was integrated with the Omega-only closure, the integration
worktree passed 768 dual-frequency tests and 54 visualization tests with
warnings treated as errors. Merge commit `b8cf39670` then fast-forwarded that
reviewed integration closure into the production checkout. The production
checkout independently passed the same 768 dual-frequency tests and 54
visualization tests with warnings treated as errors. No expensive producer or
production output was used by these tests. Production acceptance remains open
until the replacement lineage closes.

## Decision 44: Minimal-Sufficient Admission and Path-Based Resume

This decision supersedes content-identity resume gates. Scientific input
validity is established before admission by parsing the declared JSON and YAML
documents and validating their required schema fields. Resume is an output
existence operation. It does not attempt to prove that an existing output was
created by the current repository, machine, scheduler, or implementation.

The admission and resume mechanisms are classified as follows.

| Class | Mechanism | Decision |
| --- | --- | --- |
| A | JSON and YAML parsing, required-field schema validation, path-safe run identifiers, and output-root containment | Retain at the untrusted input boundary. |
| B | Atomic file replacement, a task-local `complete.json` written after its task state, a run-root `complete.json` written after successful finalization, and the minimum result decoding needed to supply downstream dependencies | Retain as explicit workflow interfaces. |
| C | Rechecking input JSON and YAML content hashes during resume, decoding the same completed result through service-specific validators, and revalidating completed OSS cache closures during task restoration | Remove as duplicate validation. |
| D | Recursively hashing the repository for run identity, treating any restored-result exception as permission to rerun, and comparing an immutable sensitivity plan during resume | Remove because no current requirement or known failure requires these mechanisms. |
| E | Invalidating completed descendants because one ancestor is missing or fails an additional restoration check | Narrow to the task whose own completion marker is absent. |

The remaining broad exception boundaries are Class B only: the record codec
adds typed execution context to an arbitrary registered record failure, the
task runner converts an arbitrary worker failure into that task's terminal
failed outcome, and atomic report publication rolls back files already
replaced in the same transaction. None authorizes retry, fallback, cache
invalidation, or completed-task rerun.

The resulting contract is intentionally small:

1. Admission parses the study JSON and three YAML profiles once, rejects parser
   errors, validates their required schemas, and completes the existing
   cross-profile checks before creating a run root or starting workers. Initial
   run creation may separately copy these small files and record provenance
   digests. Resume does neither and does not recompute configuration-source
   hashes that the existing-run path ignores.
2. Every task retains its ordinary state document. A successful task then
   atomically writes `tasks/<task_id>/complete.json` as the final task-local
   operation. The completion marker is not a checksum.
3. Resume checks the deterministic task state path and the task-local
   `complete.json` path. When both files exist, the task is restored and
   skipped. When either file is absent, only that task is eligible to run.
4. A completion marker whose state document cannot be parsed is an explicit
   interface error. It is not silently converted into a rerun.
5. Successful run finalization writes the run-root `complete.json` last. A
   failed or interrupted run has no run-root completion marker.
6. `--force` is explicit overwrite authority. It replaces the requested run
   root at the same path and does not create a derived run identifier. The
   public `run` and `sensitivity` commands expose the same option, and both
   reject combining it with `--resume`. Sensitivity delegates replacement to
   the existing `RunStore.open` implementation; it does not add a second
   deletion path or a configuration field.
7. Resume does not compare code identity, repository state, input hashes,
   configuration hashes, plan hashes, parent-manifest hashes, file metadata, or
   payload hashes. These values may remain in historical records or scientific
   cache identities, but they do not decide whether a completed task is
   restored. The `RunIdentity` value supplies creation-time fields and current
   invocation provenance only; it is not a resume identity contract.
8. No generic retry, fallback, automatic compatibility migration, or
   catch-and-rerun branch is added. Existing bounded retries remain only where
   a documented external-process failure and an explicit task contract already
   require them.
9. The active OSS lineage predates task-local completion markers. The explicit
   operator-invoked
   `my_helper/fiber/pipelines/migrate_dual_frequency_completion_markers.py`
   command may create a missing marker only when the
   corresponding legacy `tasks/<task_id>.json` exists, names the same task, and
   declares `status: completed`. It may create the run-root marker only when
   `run_manifest.json` declares `final_status: completed`. The migration is
   idempotent, performs no hash or payload validation, is never called by
   ordinary resume, and should be run again after the legacy process exits
   before the first new-code resume.

This change deliberately accepts that an incorrectly copied or manually
modified file with the expected path can be treated as complete. Operators use
`--force` when an existing path must be replaced. Deep integrity validation is
a separate, explicitly invoked release operation and is not part of ordinary
admission or resume.
After adding the missing public sensitivity flag, the CLI, application
service, executor, and synthetic extension suites pass 65 tests and 13
subtests with warnings treated as errors. The regression proves CLI
propagation, mutual exclusion with resume, and reuse of the existing RunStore
replacement path.

## Decision 45: Remove RAM Admission and RAM-Triggered Termination

The operator explicitly removes both RAM control layers from Task 17. This
decision supersedes the 48-GiB task memory charge, the system-memory reserve
predicate, the 64-GiB task-tree RSS stop condition, and the zero-swap-growth
stop condition.

The remaining resource contract is:

1. `workers` remains the process-concurrency ceiling.
2. Connectome I/O and external-solver token limits remain because they control
   shared service concurrency rather than RAM.
3. RAM and swap may be sampled for observation and reporting, but neither value
   may block task admission or terminate a running task.
4. The local guard retains only runner-lifecycle and VAL mount-generation
   protection. A missing or replaced VAL mount still stops the writer because
   continuing after external-storage loss can redirect output to the local
   mount point. Failure to read optional swap telemetry records `-1` as
   unavailable and does not stop the runner or disable mount checking.
5. Existing completion markers, scientific cache entries, and resume behavior
   remain unchanged.

This removal accepts operating-system memory management, compression, swap,
and possible process-level allocation failure as runtime outcomes. No
replacement RAM threshold, retry, fallback, or hidden admission rule is added.
The former empty-running-set resource-resampling loop is also removed. It
existed only so an available-memory predicate could become admissible while no
task was running. After RAM admission is removed, worker, connectome-I/O, and
solver reservations cannot change without a task completion, so an empty
running set with pending work is a dependency or ledger error and fails
immediately. The observational monitor no longer receives the admission ledger
or a synthetic available-memory fallback.
The focused guard and strict-resource suites pass 39 tests. They prove that
high RSS, positive swap growth, and unavailable swap telemetry do not terminate
the runner, while VAL loss, replacement, or untrusted mount continuity still
does. The final complete dual-frequency suite passes 803 tests and 326
subtests in 131.06 seconds with warnings treated as errors, no failure, and no
skip. The executor file alone passes 42 tests and 8 subtests after the stale
resampling path is removed.

## Decision 46: Remove Sensitivity Checkpoint Hash Gates

A direct call-chain audit after Decision 44 found that `sensitivity --resume`
still loaded and hash-verified the parent sensitivity checkpoint before opening
the existing child run. The hidden checks covered each sensitivity-base JSON
file, the seed-task JSON bundle, final artifact payloads, shared-cache payloads,
and the parent scientific-configuration hash. They could reject an existing
child before its task-state paths and task-local completion markers were read.

The mechanisms are classified as follows.

| Class | Mechanism | Decision |
| --- | --- | --- |
| A | Parse the parent manifest, checkpoint index, sensitivity-base JSON files, seed-task JSON bundle, and the four declared JSON/YAML inputs; require their schemas and necessary fields | Retain at the input boundary. |
| B | Require path containment, the parent terminal status, unique endpoint and task identifiers, required artifact paths, and the minimum typed result decoding needed by an incomplete child task | Retain as interface invariants. |
| C | Recompute hashes for sensitivity-base JSON and seed-task JSON after those files were already parsed and structurally validated | Remove as duplicate validation. |
| D | Recompute final-artifact and shared-cache payload hashes before opening an existing child, and compare the parent scientific-configuration hash during ordinary resume | Remove because neither check decides whether a child task has its own completion marker. |
| E | Reject or invalidate the entire child because an already completed parent or cache payload fails a new pre-resume integrity pass | Narrow to the incomplete task that actually attempts to consume a missing or unreadable dependency. |

`load_sensitivity_checkpoint` therefore becomes a structural loader. Historical
SHA fields remain readable for compatibility and provenance, but the loader
does not recompute or compare them. A persisted Omega-max descriptor supplies
the structural fields needed to compile the child plan without reopening and
hashing the shared cache. Ordinary task restoration remains governed only by
the deterministic state path and `tasks/<task_id>/complete.json`.

The structural loader validates portable URI syntax and root containment but
does not require the referenced artifact to exist, compare repeated artifact
metadata, or read an array header. Those checks belong to the incomplete task
that actually materializes the artifact. A missing or unreadable parent payload
therefore cannot invalidate completed child tasks before marker restoration.

Application setup writes the child annotation, base reference, sensitivity
plan, and imported checkpoint-root task states only while creating a new child.
It does not repair or rewrite any of them during resume. An existing child's
task files are read by the executor; any separate compatibility conversion
requires an explicit operator action.

The same rule applies to a main run's portable input bundle. Initial creation
writes `inputs/input_bundle.json` and its four copied inputs. Partial resume
does not recreate a deleted bundle or copy inputs again; it only restores or
runs tasks. A missing bundle remains visible and prevents a later sensitivity
child from treating that parent as portable until the operator explicitly
rebuilds a parent lineage. The focused main-resume, application-service, and
checkpoint suites pass 21 tests and 3 subtests. The complete dual-frequency
suite was superseded by the final complete replay reported below.

Main and sensitivity resume both bypass creation-only configuration-source
hashing. Focused regressions replace that hash collector with a failing stub.
The completed main resume returns without calling it, reaggregating reports,
rewriting accepted decisions, or finalizing the run again. The selective
sensitivity resume likewise runs only the markerless child task without
recomputing configuration-source or parent-checkpoint hashes. The
application-service file passes 8 tests and 3 subtests after this change.

This change does not weaken explicit publication validation. A separately
invoked release validator may still perform full payload hashing because that
operation verifies a publication contract rather than deciding ordinary
workflow resume.

The implementation removes the checkpoint JSON, seed JSON, final-artifact, and
shared-cache payload hash reads from the structural loader; removes the parent
scientific-configuration hash comparison; and writes imported child metadata
and checkpoint roots only during initial child creation. The exact-child
regression changes the parent manifest scientific hash, every indexed
sensitivity-base hash, the seed-bundle hash and JSON bytes, and persisted final
artifact SHA fields. Resume still executes only the one task whose marker was
removed, while every completed checkpoint-root state and marker preserves both
bytes and modification time. The final mapper accepts portable URI syntax and
root containment without checking artifact existence or reading array headers.
A completed-child regression deletes a referenced parent artifact and proves
that resume restores every completed task without any service call. The final
checkpoint-focused set passes 14 tests, and the complete dual-frequency suite
passes 803 tests and 326 subtests in 131.06 seconds with warnings treated as
errors, no failure, and no skip.

## Decision 47: Narrow Executor Future Inspection

The minimal-sufficient-correctness review classifies the remaining broad
exception boundaries as follows:

| Class | Boundary | Decision |
| --- | --- | --- |
| B | Typed-record codec adapters | Retain because external codec implementations may raise different exception types and this layer adds the rejected record context. |
| B | Backend task execution | Retain because this is the task isolation boundary that converts an arbitrary backend failure into one terminal failed task. |
| B | Atomic reporting transaction | Retain because every failure after partial replacement must enter the same rollback path. |
| D | The preliminary call to `Future.exception()` before `_finish_future` | Remove the catch-all because completed task exceptions are returned by the Future, and `_finish_future` already owns task failure localization. |

The executor now calls `Future.exception()` directly only to detect the one
recoverable `BrokenProcessPool` condition. An unexpected Future API failure,
including cancellation outside the declared scheduler path, propagates instead
of being silently reclassified as a worker exception. No retry, fallback, or
new exception wrapper is added. The executor file passes 42 tests and 8
subtests with warnings treated as errors after this narrowing. A complete
package replay remains required before the next process starts under the
updated executor.

## Decision 48: Scope Omega-Max Checkpoint Requirements to OSS

The first production identical-resume attempt for the completed jitter v8
child stopped before opening its RunStore because the structural parent loader
unconditionally required an `Omega_max` descriptor from every fiber
sensitivity base. That descriptor was added after the completed parent was
created and is needed only to compile OSS or combined OSS tasks. Pure jitter
does not consume it.

The requirement is narrowed to the analysis that uses it:

1. a request containing `oss` requires a complete structural `Omega_max`
   descriptor for every applicable fiber base;
2. a request containing only `jitter` or `final_in_sample` does not require or
   validate that descriptor;
3. a combined `jitter,oss` request retains the OSS requirement;
4. the performance-matrix loader explicitly requests the descriptor because
   its pPAM slices depend on the accepted OSS closure; and
5. no missing descriptor is synthesized, repaired, or written during resume.

This is a local dependency rule, not a compatibility fallback. The loader
continues to parse the common parent JSON and required base fields, while an
OSS-only field can fail only an OSS consumer. Focused regression must remove
the descriptor from a fiber base, prove that jitter compilation and resume
still succeed, and prove that OSS compilation rejects the same base.

The completed jitter v8 run also predates Decision 44 completion markers. Its
800 task documents are completed, but task-local and run-root `complete.json`
files are absent. The checked-in
`my_helper/fiber/pipelines/migrate_dual_frequency_completion_markers.py`
command will create only those markers after the focused code regression
passes. Ordinary resume must never invoke this migration automatically.
Production identical-resume acceptance then compares the path, size, and
modification time of every non-runtime run file before and after the exact
resume and requires no change.

The implementation adds one explicit `require_omega_max` loader argument. The
application sets it only when the requested analysis set contains `oss`, and
the performance matrix sets it because its pPAM slices consume OSS. The
checkpoint and performance-matrix suites pass 51 tests, and the complete
synthetic end-to-end file passes eight tests with warnings treated as errors.

The explicit migration then created 800 task markers and one run-root marker
for jitter v8, and 1512 task markers plus one run-root marker for the completed
main lineage. Exact resume returned success for both. Jitter preserved all 2651
non-runtime files, and main preserved all 18983 non-runtime files, with no
path, size, or modification-time change. Neither resume started a worker or
rewrote a task, marker, report, manifest, or scientific payload.

## Decision 49: Resume an Existing Sensitivity Child from Its Persisted Plan

An incomplete sensitivity child already contains the exact task graph that
created its task-state files in `sensitivity_plan.json`. Recompiling that graph
from the parent checkpoint before opening the child is unnecessary and can
prevent a valid resume when a later code version introduces a parent-only
descriptor that was not present when the child was created.

The minimal resume contract is:

1. Initial child creation continues to validate the parent input bundle, load
   the parent sensitivity checkpoint, compile the selected analyses, and write
   the resulting child-local plan before executing tasks.
2. When `--resume` addresses an existing child path, the child-local
   `sensitivity_plan.json` is the task-plan authority. The application parses
   its required JSON fields into the existing typed task and plan records.
   The same decoder is reused by the performance harness instead of maintaining
   a second task-plan parser. Required fields and their types are enforced;
   unrelated additional JSON fields are ignored and cannot invalidate an
   existing run.
3. Existing task paths and task-local `complete.json` files determine which
   tasks are skipped. The run-root `complete.json` determines whether the
   entire child returns immediately.
4. Resume does not reload parent sensitivity bases merely to reconstruct the
   already persisted graph, does not compare a plan hash, does not scan or hash
   scientific cache payloads, and does not synthesize or repair a missing
   parent descriptor.
5. The exact parent run manifest and the fixed
   `sensitivity_bases/seed_task_states.json` task-ID list remain available for
   reporting and causal parent binding. Only an incomplete child that must
   republish reporting reads that task-ID list; a child with run-root
   `complete.json` returns before the read. Resume reads no parent sensitivity
   base, artifact payload, cache entry, or SHA for this purpose. Current YAML
   and JSON inputs still pass ordinary application admission before the child
   is opened.
6. A missing, unreadable, or structurally incomplete child-local plan fails at
   that child. There is no fallback to parent recompilation because such a
   fallback would silently change the graph associated with the existing task
   files.

This rule is local to an already existing sensitivity child. It does not allow
a new OSS child to be created without the required Omega-max parent
descriptor, and it does not change any scientific task identity or cached
result.

The implementation now branches after ordinary YAML and JSON admission but
before parent checkpoint loading. A new child retains the original parent
compilation path. An existing child resume decodes its persisted plan through
the shared workflow decoder, reads only the fixed parent seed-task ID list for
reporting, and lets the existing RunStore completion markers drive restoration.
Run-root manifest parsing is shared by exact-root admission and sensitivity
report binding; malformed JSON or a non-object manifest fails at that input
boundary with no retry.
The previous duplicate performance-harness task-plan decoder has been replaced
by the same shared decoder. A regression makes the parent checkpoint loader
raise if called during partial-child resume, mutates the historical parent
metadata, removes one child marker, and proves that exactly that one
sensitivity task runs. The relevant planner, application, checkpoint,
synthetic end-to-end, performance-matrix, and plan-audit suites pass 94 tests
and 90 subtests with warnings treated as errors. After consolidating run
manifest parsing and adding malformed-object coverage, the same set passes 95
tests and 90 subtests.

## Decision 50: Derive a Missing Historical Omega Descriptor Only for New Children

The immutable v8 parent predates the portable `omega_max` field in fiber
sensitivity bases. Its declared shared-exposure identities and the stable
Omega-max cache remain sufficient to create the descriptor, and the active
independent OSS child already proves that the physical cache exists. A new
combined child would otherwise fail before it can reuse that cache.

The bounded creation rule is:

1. It applies only while creating a new child whose requested analyses include
   `oss`. Existing-child resume follows Decision 49 and never enters this path.
2. If a fiber base already contains a complete descriptor, it is used
   unchanged.
3. If the descriptor is absent, the loader resolves the base's already
   declared shared-cache manifest identities and derives the descriptor in
   memory from the one matching `normative_fiber_omega_max` entry. It reads
   only `manifest.json` and does not open or hash the cached array payload.
   Entries whose declared kind cannot contain the fiber Omega artifact are
   ignored before any manifest read. A missing or unreadable unrelated
   manifest is also ignored while scanning; only a readable manifest whose
   cache key exactly matches both `normative_fiber_omega_max` and the base's
   shared physical identity is an Omega candidate. Creation still fails when
   that scan yields zero or more than one exact candidate.
4. The parent checkpoint and cache are never rewritten. The derived descriptor
   is persisted only as part of the new child's ordinary
   `sensitivity_plan.json`.
5. A missing, ambiguous, or invalid exact Omega cache entry fails that new child
   locally. Failure of any unrelated entry remains local to that entry. No
   fallback, solver authorization, retry, or parent repair is added.
6. The combined launch continues to omit `--allow-expensive-producers`.
   Therefore execution can reuse the accepted cache but cannot silently
   regenerate a missing physical row.

This is task-input derivation for a known historical parent, not a resume
compatibility gate.

The focused loader regression publishes one synthetic Omega cache, removes the
descriptor from its parent base, and proves that new-child loading derives the
same axis and payload identity without writing the base. The end-to-end
regression removes the field from every synthetic fiber base, completes
independent OSS, then completes a combined child with expensive production
disabled while preserving every modified parent-base byte. The application,
checkpoint, synthetic end-to-end, performance-matrix, and plan-audit replay
passes 75 tests and 3 subtests with warnings treated as errors.
The narrowed manifest scan adds one missing prepared-artifact identity and one
missing fiber-exposure identity ahead of the valid Omega entry. Checkpoint,
application CLI, synthetic end-to-end, and OSS tests pass 37 tests and 2
subtests with warnings treated as errors, while the parent base remains
byte-unchanged.

## Decision 51: Remove the OSS Producer Source-Identity Gate

The replacement Omega-only OSS run exposed one remaining code-identity gate.
Task `task_2ae8cbacf8f39dbd921f` failed with
`producer implementation changed during row production` after the repository
was edited while the external producer was active. The row had no scientific
input failure. This is not a cache or resume compatibility problem: the stable
OSS row key already excludes repository state and implementation fingerprints.

The mechanisms are classified as follows:

| Class | Mechanism | Decision |
|---|---|---|
| A | Validate declared stimulation, reconstruction, transform, connectome, and fiber-axis inputs at the producer boundary | Retain |
| B | Require the returned ordered fiber axis, probability lattice, shape, and finite values to satisfy the row contract | Retain |
| C | Hash the complete local producer tree both before and after every row in addition to explicit scientific-input checks | Remove |
| D | Fail a completed external calculation because repository files on disk changed while the already-loaded producer process was running | Remove |
| E | Invalidate the whole row for a source-identity observation unrelated to its scientific inputs or returned payload | Replace with no failure path |

The current contract is minimal:

1. Repository files and the complete implementation tree are not hashed by the
   live OSS producer.
2. Source identity is not a cache key, resume gate, preflight gate, publication
   gate, or post-execution acceptance gate.
3. A successful real producer row leaves
   `producer_implementation_attestation` absent. The optional field remains
   readable only because completed historical and benchmark rows already carry
   it; it does not control reuse.
4. Explicit scientific inputs and the returned scientific payload retain their
   existing local validations.
5. No retry, fallback, compatibility scan, or replacement invalidation rule is
   introduced.

The failed task has no task-local `complete.json`, so ordinary `--resume`
re-executes only that missing task and its dependency-skipped descendants.
Completed reference and add-on rows retain their existing paths and completion
markers.

The focused OSS toolchain, backend, cache, checkpoint, and synthetic suite
passes 107 tests and 23 subtests with warnings treated as errors. The complete
dual-frequency suite passes 806 tests and 326 subtests with warnings treated as
errors. The repository-change regression mutates a source file during fake row
production and confirms that the row completes with no implementation
attestation.

## Decision 52: Validate the Formal Postprocess Request Semantically

The formal postprocess request test duplicated its complete parsed-field
contract with a raw SHA-256 assertion over
`config/four_model_v1/formal_postprocess.json`. The digest added no scientific
or interface coverage: the same test already asserts every consumed top-level
field, publication binding, ordered component, resource path, and forbidden
run-store path. It also rejected whitespace, key-order, line-ending, and
equivalent-serialization changes that do not alter the parsed request.

The minimal contract is:

1. Parse the JSON once at the file-input boundary.
2. Assert the required schema version, output root, publication descriptors,
   scale selector, ordered component list, and resource descriptors.
3. Require configured publication and output paths to remain absolute and
   outside `.runs`, `tasks`, `work`, and `runtime_work`.
4. Do not hash the complete request file and do not use byte identity as a
   cache, resume, rendering, or acceptance gate.

This removes a duplicated byte-level guard. It does not weaken the public-only
publication boundary or endpoint-level output-local resume contract.

## Decision 53: Keep Production YAML Admission Semantic

The production configuration loader already parses YAML before constructing
its run and scientific configuration identities. Its tests reopen the checked-in
workflow and both model profiles, assert the consumed grids and policies, and
prove that typed-equivalent values such as `150` and `150.0` produce the same
identities. Resume does not compare either identity.

Two plan documents nevertheless described the raw SHA-256 values of all three
YAML files as a mandatory production-source guard. That documentation was
stricter than the implementation and conflicted with the semantic configuration
contract.

The accepted boundary is:

1. YAML syntax, duplicate keys, required fields, field types, and cross-profile
   invariants are validated once during admission.
2. Run and scientific configuration identities derive from normalized parsed
   values consumed by their respective stages.
3. Comments, whitespace, line endings, key ordering, and equivalent scalar
   serialization do not change either identity.
4. Raw source-file SHA-256 values may be recorded as historical provenance but
   are not admission, cache, resume, publication, or rerun gates.

No loader change is required because the implementation and focused
configuration tests already enforce this semantic boundary.

## Decision 54: Make Performance-Benchmark Input Identity Semantic

The pending 72-row performance harness retained two byte-level gates after
Decision 53:

- it hashed the complete operator request JSON and used that digest in every
  row identity; and
- it required the four parent input files to retain the SHA-256 values recorded
  by the historical input bundle before recompiling the workflow.

Both checks duplicated stronger semantic evidence. `prepare` and every child
already compile the ordinary workflow and compare its normalized configuration
and task-plan identities.

The mechanisms are classified as follows:

| Class | Mechanism | Decision |
|---|---|---|
| A | Parse the request JSON and the four declared parent inputs | Retain |
| B | Require the declared paths to match the accepted parent's input-bundle paths and require normalized run configuration, scientific configuration, and task plan identities to match | Retain |
| C | Compare each input file's raw SHA before performing the normalized comparisons | Remove |
| D | Change all 72 row identities for request whitespace, key-order, line-ending, or equivalent-serialization changes | Remove |
| E | Reject the complete benchmark because one semantically unchanged source file has different bytes | Replace with the local normalized identity comparison |

The request identity is now the canonical hash of the parsed request object.
Path fields use their resolved absolute paths, and path-safe token fields use
their normalized values before that identity is calculated. Equivalent path
spellings therefore do not create a different benchmark.
The resolved input descriptors retain paths only. Raw source-file SHA values
remain historical fields in the accepted parent's immutable input bundle but
are neither required nor read by the performance harness and do not enter the
benchmark plan, row keys, or child admission. Cache payload, row evidence,
publication artifact, and executable authorization digests are unaffected
because those files are not configuration serializations.

The complete performance-harness module and the structural plan-audit module
pass 45 focused tests with warnings treated as errors. The regressions prove
that request formatting and source-file byte changes do not change benchmark
admission while parsed request values, bound paths, normalized configuration
identity, scientific configuration identity, and task-plan identity remain
enforced.

## Decision 55: Archive a Forced Run Root Instead of Deleting It

The `--force` implementation previously called `shutil.rmtree` on the existing
run root. A run root is not protected by Git, so permanent recursive deletion
conflicts with the repository's explicit destructive-operation boundary.

The mechanisms are classified as follows:

| Class | Mechanism | Decision |
|---|---|---|
| A | Reject simultaneous `--resume` and `--force` | Retain |
| B | Preserve the displaced run root in the operating-system Trash before creating the replacement | Add |
| C | A second sensitivity-specific deletion path | Do not add |
| D | Retry, fallback deletion, or automatic recovery when Trash archival fails | Do not add |
| E | Permanent recursive deletion of the complete existing run root | Replace with one Trash operation |

`--force` keeps the same requested path and run ID. Before the new staging root
is created, the old root is moved with the operating system's `/usr/bin/trash`
command. Failure is reported as `RunStoreError`; the old root remains in place
and no replacement starts. Temporary staging directories created by the same
failed `RunStore.open` call remain eligible for local cleanup because they are
not prior user results.

The complete executor module, both CLI force-boundary tests, and the structural
plan audit pass 50 tests and eight subtests with warnings treated as errors.
The focused cases prove that successful force preserves the displaced root,
failure preserves it in place, and resume/force mutual exclusion is unchanged.
A 2026-07-27 replay of the four direct force and CLI boundary cases passed
again with warnings treated as errors.

## Decision 56: Remove the Empty Resume Cache-Replay State

Decision 44 removed resume-time cache validation and invalid-completion
reclassification. The executor nevertheless retained the former
`cache_only_replays` return value and an expensive-producer authorization
condition keyed by that value. The restored value is now always empty.

This is class C duplicate state rather than a current interface invariant. The
restore helper returns only restored outcomes, and task admission reads
`allow_expensive_producers` directly from the execution context. No cache
validation, retry, fallback, or new branch replaces the removed state.

The complete executor module and structural plan audit pass 48 tests and eight
subtests with warnings treated as errors. No `cache_only_replays` reference
remains in production or pipeline code.

After Decisions 52 through 56, the complete dual-frequency suite passes 809
tests and 326 subtests in 133.47 seconds with warnings treated as errors.

## Decision 57: Final Minimal-Sufficient Diff Audit

The complete current uncommitted diff was reviewed after Decisions 44 through
56. Every added validation, digest, retry, fallback, invalidation condition,
and exception branch was classified against the repository policy.

| Class | Current mechanism | Decision |
|---|---|---|
| A | Parse declared JSON/YAML, validate public CLI combinations, constrain supplied file URIs to their declared roots, and validate an authorized external OSS request at the producer boundary | Retain |
| B | Require task state plus task-local `complete.json`, write the run marker last, preserve exact ordered scientific axes, enforce returned payload structure, and protect the active VAL mount generation | Retain |
| C | Resume identity comparisons, duplicate task-plan parsing, repeated checkpoint payload validation, source-tree attestation, raw request/source SHA guards, and empty cache-replay state | Removed by Decisions 44, 46, 51, 52, 54, and 56 |
| D | RAM admission, RSS/swap termination, automatic marker migration, parent repair, repository-change failure, retry/fallback deletion, and semantically irrelevant configuration invalidation | Removed or explicitly absent |
| E | A missing task marker, invalid cache entry, historical-parent Omega descriptor gap, or postprocess component failure affecting a broader run | Scoped to that task, cache entry, new-child compilation, or output component and its real downstream dependents |

No added production branch catches `Exception` or `BaseException`. Existing
pool recovery remains restricted to explicit transient-safe tasks and confirmed
timeout or broken-process-pool failure modes; no current production task
receives a generic retry merely because recovery infrastructure exists. The
scientific one-way no-delta fallback remains because it is an explicit model
contract, not an execution fallback.

The remaining digest use is local:

1. immutable cache payloads, artifacts, axis files, and publication indexes
   retain SHA-256 for their existing integrity and provenance contracts;
2. the installed OSS environment lock is checked only before an explicitly
   authorized real cache miss invokes the external scientific solver; cache
   hits and resume do not execute that check; and
3. performance, fault, and resource evidence digests are read only by their
   explicit acceptance commands and do not affect normal computation.

No whole-file configuration digest, repository digest, environment snapshot,
or complete-run digest controls ordinary resume or global recomputation.
Configuration invalidation is semantic at initial compilation; task resume is
path-and-marker based; scientific cache invalidation is entry-local; and
postprocess reuse is component-local.

Current focused evidence includes 68 configuration/CLI/executor tests plus 20
subtests, 22 checkpoint/end-to-end tests, 108 OSS/pPAM tests plus 34 subtests,
146 performance/fault tests plus two subtests, 97 cache/parity tests plus 27
subtests, 133 model/formal tests plus 47 subtests, 66
service/publication/reporting tests plus 118 subtests, 142 remaining structural
tests plus 78 subtests, and all 55 visualization tests. All passed with warnings
treated as errors. These grouped invocations supplement, rather than replace,
the complete 809-test plus 326-subtest replay recorded above.

## Decision 58: Require the Run Completion Marker at Publication Boundaries

Successful run finalization writes `run_manifest.json` before writing the
run-root `complete.json`. A process interruption between those two writes can
therefore leave a manifest whose `final_status` is `completed` without the
terminal commit marker required by the run interface. Canonical replay and its
independent validator previously checked only the manifest field.

This is a class B interface gap. The minimal publication contract is:

1. Canonical main and extension replay require the source run's root-level
   `complete.json` path to exist before reading terminal scientific results.
2. Independent extension-v2 validation requires the same source marker.
3. Both boundaries continue to require `run_manifest.json` with
   `final_status` set to `completed`.
4. Neither boundary parses or hashes the completion marker. Task-level resume
   remains based on each task state path and its task-local marker.
5. No retry, fallback, migration, cache, configuration field, or broader
   invalidation rule is added.

The check is source-run local. A missing marker blocks only publication or
validation of that source run and does not invalidate completed task results,
shared caches, the parent run, or another extension.

The complete canonical-publication module and independent extension validator
pass 24 focused tests with warnings treated as errors. The two new regressions
prove that a completed manifest without the run completion marker cannot be
published or independently validated and that no extension manifest is
committed by the rejected replay.

## Decision 59: Remove the Deleted Code-Identity Call from Benchmark Rows

Decision 44 removed recursive repository hashing and the private
`WorkflowService._code_identity` helper. A final diff review found two
performance-matrix row-creation paths that still called that deleted helper.
Those calls would fail before a warm-seed or measured row could open its local
RunStore.

This is a class C stale duplicate, not a new benchmark identity requirement.
Both paths now use the same fixed `not_recorded` creation-provenance value as
ordinary main and sensitivity runs. The value does not enter row identity,
scientific cache identity, resume, publication, or invalidation. No replacement
hash, repository scan, compatibility branch, retry, fallback, or configuration
field is added.

The complete performance-matrix test module and structural plan audit pass
46 tests with warnings treated as errors after the removal. The structural
guard rejects reintroduction of either the deleted helper or a benchmark call
to it.

## Decision 60: Make the Open Step 5 Contract Omega-Only

The open Step 5 text still described the superseded paired final-axis and
`Omega_max` equivalence gate as a current implementation requirement. Decision
43, the current compiler, and the active replacement lineage instead require
one cache-first `Omega_max` row per physical condition and exact endpoint
subsetting by ordered canonical fiber ID.

The implementation plan now states that current contract directly. New plans
contain no final-axis OSS producer, equivalence-decision task, or fallback
branch. Historical paired decisions remain immutable numerical evidence only.
The adjacent checkpoint text now requires the structural `Omega_max`
descriptor rather than an OSS gate state. This is a documentation correction;
it changes no task, cache, scientific input, running process, or publication.

The plan-audit and bounded goal-acceptance suites pass 14 tests with warnings
treated as errors after the correction.

## Decision 62: Remove Superseded RAM Admission from the Open Geometry Step

The open Step 4 still required 32-GiB normative-fiber and 16-GiB direct-voxel
RAM admission charges even though Decision 45 removed every task RAM charge,
available-memory reserve, managed-memory ceiling, RSS stop, and swap-growth
stop. That requirement contradicted both the current executor and the final
resource checklist.

Step 4 now states the implemented contract: preparation admission uses worker
and connectome-I/O tokens, while RAM, RSS, and swap are observational
execution-segment evidence only. The point-range path is described as the
ordinary path for a source outside the declared shared-resident geometry
budget, rather than as a speculative future fallback. The chronological third
slice remains as historical evidence but explicitly records that Decision 45
superseded its RAM charges.

This is a documentation-only correction. It changes no task, resource grant,
cache key, geometry payload, running process, scientific input, or
publication.

The plan-audit and bounded goal-acceptance suites pass 14 tests with warnings
treated as errors after the correction.

## Decision 63: Make the Performance Harness Omega-Only

The formal benchmark request binds only the replacement independent
Omega-only OSS lineage. Retaining support for historical
`OSSAxisEquivalenceGroupRecord` values inside the not-yet-run performance
harness is therefore an unneeded compatibility branch. It also keeps obsolete
final-axis rows and equivalence decisions in the accepted cache closure even
though current pPAM consumes an ordered endpoint subset of one shared
`Omega_max` row.

The benchmark contract now accepts exactly two terminal
`OSSSharedOmegaGroupRecord` values produced by
`prepare_oss_omega_max_rows`, one for each fiber family. Its accepted cache
closure contains only the ordered Omega rows referenced by those records.
Measured pPAM slices select Omega-only preparation, and injected fixtures derive
their deterministic activation states directly from the accepted Omega
probabilities. No final-axis OSS row, equivalence decision, legacy gate service,
or compatibility decoder remains in the performance-harness path.

The same correction removes obsolete managed-memory and reserved-memory fields
from the scheduler-window prose. Benchmark resource evidence binds worker,
CPU, connectome-I/O, and solver-token state; RAM, RSS, and swap remain
observations rather than predicates.

This change is local to the pending performance harness and its focused tests.
It does not alter the active OSS lineage, the shared scientific rows, endpoint
pPAM numerics, ordinary resume, or publication.

The performance-matrix, structural plan-audit, and bounded goal-acceptance
suites pass 55 tests with warnings treated as errors. A structural guard
rejects reintroduction of the historical paired-record type, gate service, or
cache kind into the performance harness.

## Decision 64: Use Marker-Only Resume in Every Current Plan

The current extension contract in the four-model plan and the current
`formal_in_sample` Step 9A text still described completed-task payload
validation as part of ordinary resume. That contradicted Decisions 44, 46, and
61 and could reintroduce broad or stage-specific resume gates.

Both plans now state one rule: a deterministic task-state path together with
the task-local `complete.json` restores that task. A missing pair makes only
that task eligible to run. Payload parsing occurs only when a downstream
consumer actually reads the restored result; a local parse failure remains
visible and does not trigger automatic recomputation, fallback, or broader
invalidation.

This is a documentation-only correction. It changes no task marker, running
process, cache entry, scientific result, or publication.

The structural plan-audit and bounded goal-acceptance suites pass 16 tests with
warnings treated as errors after the correction.

## Decision 65: Remove the Historical Equivalence Gate from Production Services

Current plans produce `OSSSharedOmegaGroupRecord` values through
`prepare_oss_omega_max_rows`. The production service registry and activation
adapter still exposed the superseded `establish_oss_axis_equivalence` path and
accepted `OSSAxisEquivalenceGroupRecord` as an alternative physical-row
authority. No current plan, accepted lineage, benchmark request, combined
extension, or publication requires that branch.

The production registry now exposes only Omega-only group preparation.
Activation accepts a shared Omega group when one is present and otherwise
retains the ordinary main-plan path; it no longer decodes a paired final/Omega
gate record. The executor assigns solver and connectome-I/O tokens only to the
current `oss_omega_max_` group stage. Focused structural tests reject
reintroduction of the historical service or record into these production
paths.

The standalone historical equivalence module and record codec remain
read-only numerical-evidence tooling. They are not registered, planned,
restored, or consumed by current production execution. Retaining that isolated
decoder is required only to inspect immutable historical certification
artifacts and does not add a current fallback or cache path.

This change does not alter the active Omega-only OSS process, its task plan,
cache rows, endpoint pPAM numerics, or publication.

The service-adapter, executor, sensitivity-checkpoint, and structural plan
suites pass 82 tests plus 10 subtests with warnings treated as errors. The
performance-matrix, structural plan, and bounded goal suites pass 58 tests.

## Decision 66: Require Completion Markers at Benchmark Import Boundaries

The performance harness accepted a parent run from its completed manifest and
classified imported task states from completed JSON alone. That was weaker
than the repository-wide completion contract and could import a run or task
interrupted before its final marker was written.

Benchmark preparation now requires the accepted parent and independent OSS
roots to contain root-level `complete.json`. An imported task is classified as
completed only when both its deterministic task-state path and task-local
`complete.json` exist. Markers are checked only for path existence; they are
not parsed, hashed, or used to validate payloads. A missing marker blocks only
the pending benchmark preparation and does not invalidate, delete, repair, or
rerun the source run.

This is a class B interface invariant at the benchmark import boundary. It
adds no ordinary-resume gate, retry, fallback, migration, cache entry, or
broader invalidation.

The performance-matrix, structural plan-audit, and bounded goal-acceptance
suites pass 58 tests with warnings treated as errors, including direct missing
run-marker and missing task-marker regressions.

## Decision 67: Do Not Reparse Tasks after the Run Completion Marker

The main and sensitivity resume paths correctly returned early when the
run-root `complete.json` existed, but the return helper still reopened every
task state and decoded every `TaskOutcome`. Those reads could reject or delay a
run after the terminal marker had already established the interface state.
They also duplicated the explicit `status`, reporting, and validation commands.

A completed-run resume now returns a successful `RunResult` with no reconstructed
task outcomes and performs no task-state read. The run ID comes from the opened
RunStore, and the run marker remains the sole terminal-resume decision. This
does not erase persisted tasks or reports; it only keeps ordinary resume from
revalidating them.

This removes a class C duplicate validation. It adds no fallback, cache,
migration, retry, or invalidation rule.

The focused application and synthetic completed-resume set passes seven tests
plus three subtests with warnings treated as errors. The main-run regression
forces any task-state read to fail, proving the terminal early return is
marker-only.

## Decision 61: State Marker-Only Extension Resume and the No-Commit Closeout

The open Step 6 text still described resume as restoring “valid” completed
tasks. That wording could imply checkpoint payload revalidation even though
the implemented contract is intentionally narrower. The plan now states the
actual rule: a deterministic task-state path together with that task's local
`complete.json` restores the task; a missing pair affects only that task.
Dependency-derived skips are then re-evaluated from the restored task states.
No SHA, payload inspection, configuration identity comparison, retry, fallback,
or broader invalidation is introduced.

The acceptance mapping also described Step 11 as a final commit even though the
Step 11 contract and the user's explicit instruction require this worktree to
remain uncommitted. The mapping now names the final audit without committing.
This is a documentation-only correction and does not change the active OSS
process, task state, cache, scientific input, or publication.

The plan-audit and bounded goal-acceptance suites pass 14 tests with warnings
treated as errors after the correction.

## Decision 68: Final Minimal-Sufficient-Correctness Diff Review

The current uncommitted diff was reviewed again after Decisions 61 through 67.
The review classified every added validation, hash, fallback, retry, cache
condition, and exception branch against the repository's A through E policy.
It found no remaining class C duplicate, class D speculative defense, or class
E global failure mechanism in the changed production paths.

The retained class A boundaries are limited to parsing YAML and JSON at their
input boundaries, checking required consumed fields, resolving publication
inputs, and checking the external OSS environment only before an authorized
real solver cache miss. The retained class B invariants are deterministic task
state paths paired with task-local `complete.json`, the run-root
`complete.json` required by publication import, explicit `--force` replacement
through Trash, and VAL mount-generation continuity while an external writer is
active.

The review confirms the following removals already present in the diff:

1. repository, code, source-file, configuration-file, and audit SHA values do
   not gate ordinary resume;
2. terminal resume does not reopen or decode completed task states;
3. RAM admission, RSS termination, and swap-growth termination are absent;
4. the historical paired OSS equivalence service is absent from production
   planning, execution, and the pending performance harness; and
5. no automatic retry, fallback, compatibility migration, or global cache
   invalidation was added.

Remaining scientific artifact and cache SHA values retain their established
entry-local integrity and provenance roles. They are not ordinary-resume
predicates and cannot trigger a whole-run rerun. Missing task state or a
missing task marker affects only that task. A cache miss affects only that
scientific cache entry and its direct consumers. Explicit publication,
performance, fault, and output validators remain separate commands and do not
run as global startup preflight.

This final diff review requires no additional code change. The worktree remains
uncommitted as requested.

## Decision 69: Make Formal Postprocess Resume Path-and-Marker Only

The broader three-plan audit found one remaining ordinary-resume exception
outside the workflow diff reviewed by Decision 68. Formal paired-fit, voxel,
and fiber postprocess components compared source-and-style request hashes
before reuse, while the formal root compared request and resolved-request
hashes. Those checks could rerender completed figures after a metadata or
configuration change even though the latest explicit resume contract requires
path-based reuse.

The formal postprocess contract is now:

1. normal admission parses the request JSON and checks the required fields
   consumed by the selected execution path;
2. each component writes a deterministic result file and then a
   component-local `complete.json`;
3. ordinary component resume skips when both paths exist and does not parse or
   hash the marker;
4. the formal root writes `complete.json` last and returns its stored manifest
   immediately on ordinary terminal resume;
5. a missing result or marker affects only that component;
6. `--force` moves the existing formal output root to the operating-system
   Trash before a fresh render; and
7. explicit `--validate-only` and `--validate-output` retain publication,
   scientific, structural, and format checks without becoming ordinary-resume
   predicates.

This removes the remaining class C request-identity duplication and converts
the class E component invalidation rule to the smallest persisted component
boundary. Scientific source validation remains class A at the canonical
publication input boundary. Terminal endpoint closure and the last-written
root marker remain class B output contracts. No retry, fallback, migration
layer, compatibility shim, new configuration option, or global cache
invalidation is introduced.

The paired-fit, voxel-section, fiber-section, and formal-orchestrator focused
set passes 49 tests. The complete visualization suite passes all 55 tests with
warnings treated as errors. The tests prove component marker publication,
path-and-marker reuse, root-marker terminal resume without rewriting the
manifest, explicit force replacement through Trash, missing-root-marker
validation failure, and complete paired, voxel, and fiber output closure.

## Decision 70: Make Interactive 3-D Scene Inputs Path-and-Marker Only

The PDQ-39 scene-input helper still selected its output directory from a hash
of publication, source, and geometry records. It had no completion marker and
no explicit force operation. A source metadata change therefore selected a new
directory even when the prior scene input was already complete. This was the
same class E broad invalidation pattern removed from formal postprocess by
Decision 69.

The scene-input contract now uses the fixed directory
`<scale-id>-<model-family>`. A normal call returns `manifest.json` when that
path and the sibling `complete.json` exist. It does not parse the marker or
reopen the publication. A missing pair makes only that one scene input eligible
to build. Any incomplete prior target is moved to Trash after the requested
publication and required source fields pass validation. Explicit force follows
the same validation-first ordering, moves the prior target to Trash, and then
builds a fresh target. The MATLAB wrapper exposes the same explicit `Force`
flag.

Scientific source and geometry hashes remain class A publication-boundary
evidence during a real build. They are retained in the manifest for
provenance, but no hash selects the target path, controls resume, or
invalidates another model family. No retry, fallback, compatibility branch,
additional cache, or configuration field is added.

The focused scene-input and MATLAB-wrapper set passes eight tests. The complete
visualization suite passes all 58 tests with warnings treated as errors. The
tests prove fixed output naming, marker publication, path-and-marker reuse
without reopening the publication, local incomplete-target replacement,
explicit force replacement, and validation before Trash mutation.

## Decision 71: Keep Completion Markers Append-Only Within a Run Root

The marker implementation still contained two deletion branches. Writing a
noncompleted state after a task marker existed removed that task marker, and
finalizing a run as failed after its run marker existed removed the run marker.
Neither transition belongs to the workflow lifecycle: an existing marker makes
the task or run terminal, ordinary resume restores it, and explicit force moves
the complete run root to Trash before creating a new root. The old run-store
test reached the deletion branch only by calling completed finalization and
then failed finalization on the same root.

Those two deletion branches are removed. Successful task and run publication
still writes its marker last. A failed or partial task or run never creates a
marker and never deletes an earlier marker. Explicit marker migration remains
add-only. Explicit force remains the sole replacement operation and acts on the
whole run root through Trash. The focused test now uses separate successful and
failed roots, matching the real lifecycle. No new validation, recovery branch,
retry, fallback, compatibility layer, cache, or configuration field is added.

The three focused marker, migration, and hash-free resume cases pass. The
complete executor suite passes 43 tests and eight subtests with warnings
treated as errors. The smallest cross-entry RunStore replay across CLI,
application service, synthetic end-to-end, publication, and executor passes 83
tests and 13 subtests with warnings treated as errors.

## Decision 72: Check Terminal Completion Before DAG Compilation

Decision 67 stopped terminal resume from reopening task states, but the main
and sensitivity entrypoints still compiled the ordinary parent DAG before they
checked the run-root `complete.json`. That compilation cannot change a terminal
resume decision and is not part of the required JSON or YAML admission
boundary.

The minimal startup order is therefore:

1. parse the declared study JSON and YAML profiles once and validate their
   required consumed fields;
2. derive the deterministic requested run root;
3. if ordinary resume finds the run-root `complete.json`, return success
   immediately without compiling a DAG, loading a persisted sensitivity plan,
   or reading the parent seed-task whitelist;
4. if a main run is incomplete, compile the current main plan and restore only
   task states paired with task-local markers; and
5. if a sensitivity child is incomplete, load that child's persisted plan
   directly and do not compile the parent plan merely to resume it.

Sensitivity still resolves the explicitly supplied base-run directory and
parses its run manifest once as an untrusted JSON input boundary. That required
admission check is not duplicate resume validation.

This removes duplicate terminal-resume work without changing task IDs,
scientific configuration, cache identity, force semantics, or the
path-and-marker invalidation boundary. It adds no hash, retry, fallback,
compatibility branch, cache, or configuration field. The change is confined to
future application entrypoint calls; it does not alter the already loaded
executor, worker, provider, OSS cache, or scientific operation of the active
independent OSS process.

The implementation now parses and validates the declared inputs, derives the
requested root, and returns from a terminal marker before compiling either
ordinary DAG. An incomplete sensitivity child loads its persisted plan without
compiling the parent DAG. The two direct terminal-resume regressions pass, and
the existing one-task incomplete sensitivity replay now explicitly rejects
parent DAG compilation. The complete application-service, synthetic
end-to-end, and public CLI modules pass 23 tests and five subtests with warnings
treated as errors.

Moving the terminal check to the deterministic run-root boundary also leaves
`RunStore.is_complete()` without a production caller. Keeping a second method
that only restates `root / complete.json` would duplicate the accepted marker
contract. The unused method is therefore removed, and the finalize regression
checks the marker path directly. This is a class C duplicate removal and does
not change completion semantics. The focused finalization and plan-audit
replay passes nine tests with warnings treated as errors.

## Decision 73: Use Completion Markers in the Legacy Visualization Entry Point

The still-public `my_helper.fiber.core.viz.postprocess` entry point retained an
older resume rule that recomputed a semantic request hash, parsed the endpoint
manifest, and scanned every declared output before reusing an endpoint. That
rule is inconsistent with the accepted minimal path-and-marker contract and is
not required by its interface.

The entry point now parses and validates the requested JSON fields once. A
normal invocation returns an existing root when `manifest.json` and
`complete.json` are present. Within an incomplete root, an endpoint is reused
when its fixed `manifest.json` and endpoint-local `complete.json` are present.
Neither marker is parsed or hashed. A missing pair reruns only that endpoint.
The request hash and output scan are removed from resume. Source artifact
records remain publication evidence only when an endpoint is actually built.

Explicit force validates the requested publication catalog before moving the
existing output root to the operating-system Trash and rebuilding the same
path. A failed or partial run never writes the root marker. This change adds no
configuration field, compatibility fallback, retry, cache, or broad
invalidation.

The complete public visualization-entry test module passes 29 tests with
warnings treated as errors. It covers root and endpoint markers, partial-root
endpoint reuse, formatting-independent terminal reuse without reopening a
publication, force replacement, and preservation of the old root when force
input validation fails. The complete visualization directory passes 61 tests
with warnings treated as errors.
The endpoint loop reuses the IDs parsed at the input boundary rather than
reading and normalizing them a second time.
Because each endpoint ID is used directly as one output-directory name, the
same boundary requires it to be one safe path component. This is an untrusted
path-construction check; it does not inspect the filesystem or add an
invalidation rule. The focused boundary fixture covers dot, parent, and nested
path values, and the complete 61-test visualization directory passes.

## Decision 74: Validate Formal Request Shape Before Terminal Resume

The formal postprocess entry point already returns from a root
`manifest.json` plus `complete.json` before reopening publications or rendering
resources. Its terminal path nevertheless returned before checking that
`output_root`, `publications`, `styles`, and `resources` retained their required
JSON field types.

These inexpensive request-shape checks move to the JSON admission boundary
before the terminal marker decision. They do not resolve a publication, inspect
an artifact, open anatomy or connectome data, validate rendering tooling, or
compare any hash. A valid terminal request still returns without those
operations. This is the smallest change that satisfies required-field
admission while preserving marker-only resume.

The focused terminal-resume fixture passes and the complete visualization
directory remains at 61 passing tests with warnings treated as errors. The
fixture covers invalid output path, publication object, style object, and
resource object fields while proving that a valid terminal request does not
invoke the publication loader.

The final current-worktree validation now includes the complete
dual-frequency test directory: 816 tests and 326 subtests pass. Warnings are
treated as errors through pytest's `-W error` option. An earlier invocation
incorrectly exported `PYTHONWARNINGS=error` into the fault-harness child
processes, causing `conda` itself to stop on a Python 3.12 deprecation warning
before any fixture command ran; rerunning with the pytest-local warning policy
closed all eight environment-induced failures.

## Decision 75: Validate Run IDs Before Constructing Run Paths

Decision 72 moved the main terminal-marker check before `RunIdentity`
construction. The application entry point already rejected slash-separated run
IDs, but it still accepted `.` and `..`. Those values are path components with
navigation meaning, so they could select the study directory or its parent
before the later identity object was created. The sensitivity request had the
same incomplete path-component rule for its child and optional rebuilt-parent
IDs.

Run IDs are untrusted input used directly as directory names. The application
boundary will therefore parse each run ID once and require one nonempty path
component that is neither `.` nor `..` and contains no forward or backward
separator. Main, sensitivity-child, and rebuilt-parent IDs share that single
helper before any run path is constructed.

This is class A input validation and class B output-root containment. It does
not inspect an existing run, hash an input, add a retry or fallback, or change
resume and invalidation behavior. A rejected ID creates or reuses no path. A
valid ID retains the existing path-plus-`complete.json` contract.

The focused public-application module passes six tests and seven subtests. The
complete dual-frequency directory passes 817 tests and 331 subtests with
warnings treated as errors. The final diff retains one shared run-ID parser,
adds no cache or invalidation state, and leaves scientific and ordinary resume
behavior unchanged.

## Decision 76: Validate Extension IDs Before Constructing Publication Paths

The run-ID audit exposed the same incomplete rule in canonical extension
publication. Both final-in-sample and terminal jitter or OSS replay rejected
forward and backward separators, but still accepted `.` and `..` before
joining the extension ID beneath `<model-set>/extensions`.

An extension ID is another untrusted directory-name input. Canonical
publication will parse it once through one local helper and require one
nonempty component that is neither `.` nor `..` and contains no separator.
Both extension publication paths reuse that helper before creating a writer.

This is class A input validation and class B publication-root containment. It
adds no hash, retry, fallback, compatibility path, cache, or invalidation
state. Invalid input cannot create or reuse a publication path; valid
publication and idempotent replay behavior are unchanged.

The complete publication module passes 18 tests. The complete dual-frequency
directory passes 818 tests and 331 subtests with warnings treated as errors.
