# Task 17 Three-Plan Acceptance Audit

## Purpose

This document is the evidence ledger for the complete acceptance of:

1. `four_model_yaml_core_refactor_plan.md`;
2. `dual_frequency_core_decoupling_implementation_plan.md`; and
3. `postprocess_visualization_implementation_plan.md`.

It does not replace or narrow those plans. A row is accepted only when the
named production artifact and its independent verifier prove the complete
requirement. Unit tests, design text, or an intermediate cache count cannot
close a production row by themselves.

Status vocabulary:

- `ACCEPTED` means current durable evidence proves the row;
- `ACTIVE` means an instrumented production operation is still running;
- `PENDING` means implementation may exist, but required production evidence
  is not terminal;
- `BLOCKED` is reserved for an external condition that prevents progress.

## Evidence Matrix

| Requirement | Status | Current authoritative evidence | Remaining acceptance action |
| --- | --- | --- | --- |
| Production YAML drives all four model families | ACCEPTED | `config/four_model_v1/workflow.yaml` references the production direct-voxel and normative-fiber profiles; configuration, CLI, in-sample, and cleanup fixtures pass. The historical `model.yaml` is explicitly outside the current loader and lineage. | Reconfirm resolved YAML digests during the final publication audit. |
| Frozen voxel and fiber source grids | ACCEPTED | Direct voxel uses tau 150, 180, 200, 220, 250, and 300 with pre-specified 200. Normative fiber uses tau 200, 350, 400, 450, 600, and 800 with pre-specified 400. Both use Coverage 5, 6, 7, 8, 10, and 12. | Compare the final published resolved profiles byte-for-byte with the completed parent manifests. |
| Boundary and computability policy | ACCEPTED | Current runtime and formal kernels use the frozen distinct voxel/fiber predicates, retain the 12-subject floor, and require at least one fold candidate fiber for every declared connectome. | Repeat the repository-owned final static audit after all production children terminate. |
| Main four-family formal run | ACCEPTED | Parent run `task17-main-v8-tau-grid-formal-20260717` is the completed immutable authority for 28 scales and 112 final endpoints. | Reopen its terminal manifest, task closure, final decisions, and artifact index during final audit. |
| Canonical main model-set publication | ACCEPTED | Completed direct-voxel and normative-fiber model-set publications are the only allowed public parents. Postprocess preflight resolves them without a run-store fallback. | Repeat model-manifest and indexed-payload verification after display-smoothing promotion. |
| Final in-sample inference and publication | ACCEPTED | Both model-set domains contain the canonical final-in-sample v2 extension. Formal postprocess resolves paired in-sample and LOOCV endpoint evidence from public paths. | Recheck exact 112-endpoint pairing and all declared statistics in the terminal postprocess output. |
| Shared physical preparation and configured-data parity | PENDING | Shared geometry, one-time physical exposure, inclusive fiber overlap, exact minimum-grid `Omega_max`, side-specific fiber peak reduction, cache-backed subject/feature views, copied-cache reuse, and bounded parity fixtures pass 104 focused tests. These fixtures prove the implementation boundary but do not compare the complete configured production matrices. | After independent OSS releases the formal connectome and VAL I/O path, run the repository-owned configured-data post-refactor replay. Record complete matrix parity, worker-count determinism, physical-row counters, logical-versus-physical write reduction, and absence of endpoint matrix copies or repeated full-connectome traversal. |
| Cold/warm performance and scheduler acceptance | PENDING | Persistent spawned scheduling, global CPU/memory/I/O/solver ledgers, parent-only state mutation, process-local cache verification, vectorized kernels, and deterministic RNG boundaries pass static tests. The repository-owned cumulative-CPU probe, five-second scheduler-window publication, exact 72-row matrix validator, source-evidence binding, deterministic report, worker/default decision, RSS/swap gates, and utilization-window gate are implemented. Every executed row binds the exact probe SHA; I/O classification is closed to compute-bound or storage-limited; and a non-default worker promotion requires matched compute-bound rows that are all faster than workers 3 while retaining both wall times in the report. All 28 counters derive from immutable task fragments, configured parity, artifact/static audit, terminal segment fields, and a SHA-bound source/scratch byte ledger; caller-entered counter values are rejected. Commit `f73d849d8` binds every scheduler sample to its contemporaneous managed-memory ceiling and validates the initial, minimum, maximum, and final segment closure. The benchmark harness validates the minimal operator request, accepted parent and independent OSS binding, exact source identities, maximum-burden scientific requests, measured/imported DAG task slices, protected-root separation, optional solver authorization, and the exact 72-row key closure. Its runner-readiness and measurement-start protocol binds the row, child PID, slice-plan SHA, imported task closures, byte-ledger path, and byte-ledger SHA before selected work may start. Stable row identities, immutable row contracts, monotonic attempt directories, terminal evidence SHAs, changed-contract rejection, and changed-evidence rejection are implemented. `prepare` writes the resolved plan, all 72 contracts, and only then the complete contract-SHA marker; read-only validation rejects missing, extra, changed, or path-aliased contract roots. The sole unauthorized real-cold solver branch publishes an immutable false-authorization preflight and terminal `not_run`; other rows cannot use that status. Every statistical slice includes its selected endpoint's base physical producer so a cold row can create the row-local shared-cache closure and a warm row can prove a cache hit without copying a selected-task result. Each resolved slice persists a closed executable plan with imported direct parents converted to checkpoint-only roots while preserving every selected task's original service, parameters, gates, and internal dependencies. pPAM injected, real-cache-hit, and real-solver rows have separate slice identities and all measure the OSS equivalence gate; the accepted OSS outcome is an injected/reference authority or cache seed, never a copied selected-task result. `prepare` decodes the exact two terminal OSS gate records, resolves only their referenced decision and final/Omega row entries from the configured shared cache, verifies stable scientific keys and final-axis probability parity, and binds every cache-manifest SHA plus a canonical closure SHA into the resolved plan. The benchmark-only injected toolchain reconstructs exact ten-sample activation counts from those accepted rows and rejects requests outside that closure. Ordinary and injected warm-seed production, child/probe launch, terminal row evidence, identical row resume, normalized numerical identity, scheduler-derived I/O classification, 72-row matrix publication, strict acceptance invocation, public `run`, and read-only terminal validation are implemented in the isolated worktree. Five candidate-parity tests and 35 harness tests pass. No production matrix has run. | After independent OSS terminates, merge the isolated implementation and run the complete regression. Then execute the workers 1, 3, 6, and 12 cold/warm matrix without substituting skipped or default-zero rows. Retain every terminal counter sidecar, exact-resume proof, deterministic matrix, and acceptance report. |
| Corruption, fail-once recovery, and deletion-rebuild acceptance | PENDING | Static cache, resume, checkpoint, and rebuild fixtures reject payload, shard, axis, and result corruption and selectively rerun affected descendants. The repository-owned marker-bound isolated harness implements complete parent/publication SHA closure, exact copied-cache marker closure, path-safe unique case IDs, absolute and relative command confinement, quarantine-and-restore corruption, immutable and task-bound pre-resume fail-once evidence, protected-artifact checks, distinct-lineage rebuild, unauthorized copied-cache replay, exact or NPY-tolerant one-shot comparison, contract-bound terminal case reuse, and read-only validation that cannot repair a changed report. Fifteen focused harness tests pass with warnings treated as errors. A later complete collect-only pass discovers 764 tests without import or collection failure; it is runner-readiness evidence and not a claim that all 764 tests executed. The production-scale sequence has not run. | Generate the production fault plan from the accepted parent and canonical publication. In its marked isolated root, execute all three corruption classes, fail-once recovery, missing-parent rebuild, copied-cache replay, and one-shot comparisons; retain the terminal deterministic report. |
| Independent spatial jitter computation | ACCEPTED | `task17-jitter-v8-support-preserving-formal-20260719` completed its support-preserving block and endpoint closure with no terminal failure. Jitter compilation, selective block resume, cache-first dispatch, and extension publication boundaries pass 25 focused tests with temporary fixtures. | Reopen the completed child manifest, block closure, endpoint closure, artifact index, and parent binding during final audit. |
| Canonical independent jitter-v2 publication | PENDING | The completed jitter child was replayed twice into self-contained v2 extensions in both public domains. The identical replay preserved both terminal publications and their source/parent bindings. | After independent OSS releases shared VAL bandwidth, run the frozen repository-owned publication validator across both roots and retain its atomic acceptance document. |
| Independent OSS axis equivalence and pPAM | ACTIVE | `task17-oss-v1-inclusive-formal-20260719` has a stable terminal reference group of 34 decisions and 68 rows, all pass, produced by Decision 39 cache-only promotion without a reference solver call. The add-on gate retains three validated pass decisions and six complete rows and reaches the solver only for missing work. At 2026-07-25T16:25:46Z, guarded `segment_0018` remained active with 393 completed tasks, one running add-on gate, and 196 dependency skips; the live solver was processing `sample_03`. VAL create/fsync/read/unlink passed at 10 Gb/s. Across 13692 guard samples, peak task-tree RSS was 45696860160 bytes, current RSS was about 7513522176 bytes, swap remained below the segment baseline, and no stop event occurred. Existing scientific payloads remain valid and preserved. | Require terminal add-on closure, execution of all dependency-derived downstream tasks, zero terminal failures, and complete reporting, artifact-index, identical-resume, and resource validation. |
| Canonical independent OSS-v2 publication | PENDING | Self-contained extension-v2 publisher and validator fixtures pass. The source OSS child is not terminal. | Publish twice without filters, validate the normative-fiber OSS-v2 root, and audit source/parent bindings plus forbidden paths. |
| Cache-first combined jitter and OSS replay | PENDING | Compiler, executor, physical jitter, and OSS decision fixtures prove cache-first behavior and fail before a producer call on a miss without authorization. | Start the frozen combined child without `--allow-expensive-producers`, attach the checked-in guard, and require complete cache reuse plus terminal DAG closure. |
| Canonical combined-v2 publication | PENDING | Publisher and validator fixtures cover both public domains. No terminal combined child exists. | Publish twice, validate both domain roots, and audit complete jitter plus normative-fiber OSS scope. |
| Resume and copied-cache implementation | ACCEPTED | Resume fixtures use input JSON/YAML identities and complete result JSON records, ignore repository code identity, selectively rerun missing blocks and consumers, and reuse a directly copied cache under a different path. | Recheck these fail-closed static contracts after the last implementation change. |
| Production identical resume acceptance | PENDING | The main and completed jitter lineages preserve resumable state, and the active OSS lineage has repeatedly restored its immutable plan and completed predecessors without invalidating scientific products after code-only changes. The complete terminal-child identical replay has not yet run. | After each production child becomes terminal, run its exact resume path, prove no accepted payload was rewritten, and retain the task-outcome and manifest evidence. |
| Resource scheduling and guard contract | ACTIVE | One persistent spawn pool, 14-worker ceiling, single solver token, 48-GiB authorized-producer admission charge, task-tree RSS `< 64 GiB`, and swap growth `< 1` byte are implemented and covered by static tests. The strict validator closes safe segment identity, initial/minimum/maximum/final managed-memory and reserve declarations, window-local managed-memory reservations, connectome-I/O/solver/BLAS ceilings, CPU/memory/I/O/solver/running-task peaks, exact admission maps, contained SHA-bound scheduler windows, exact UTC/elapsed/runnable/storage derivations, and a final zero-RSS guard terminal row. Segment 0016 proved that cache-only replay still inherited the producer grant and that a temporarily memory-blocked empty running set failed instead of waiting. Decision 40 implements a 512-MiB token-free cache-read grant, one-second production resampling for structurally admissible memory waits, and immediate failure only for structural impossibility or dependency deadlock. Focused and complete regressions pass. | Retain segment-wide guard evidence for the next resume. Build the repository-owned maximum-row measurement window from the terminal independent OSS closure and repeat strict acceptance for combined. |
| Display smoothing v2 publication | PENDING | `/private/tmp/task17-display-smoothing-v2-stage.zAofAX` contains 112 NIfTI replacements and 112 metadata records. All preserve exact raw finite support, all staged hashes and sizes match, and the repair-manifest SHA-256 is `dff3ab60616b2bd9d77075bc6781f6ef928db666f1052ac31d5f02f4088f6b5c`. Formal preflight now binds each smoothing sidecar and rejects the current mixed publication at its first remaining v1 derivative. | After OSS exits, validate, promote through the repository transaction into the canonical direct-voxel publication, archive replaced untracked files in the declared VAL Trash root, and validate again. |
| Formal paired-fit, voxel 2-D, and fiber 2-D output | PENDING | The durable request structurally resolves 28 scales, 112 endpoints, canonical public inputs, and all three batch components. The current v2 preflight intentionally blocks rendering until display-smoothing promotion. The 38-test visualization suite and 30-test publication suite pass with temporary fixtures. | After promotion, rerun preflight, render the formal output, repeat without force, verify no completed component rewrite, run `--validate-output` twice, and visually inspect representative outputs. |
| Interactive voxel and fiber 3-D implementation | ACCEPTED | The two PDQ-39 MATLAB examples resolve only canonical publications, request 0.5-mm inward voxel sampling, use signed `vik` mappings and independent colorbars, preserve grayscale anatomy, and create no export unless explicitly requested. Static and synthetic MATLAB scene contracts pass. | Retain both examples and their migrated export helpers unchanged through final publication work. |
| Final canonical 3-D scene review | PENDING | Earlier real and synthetic reviews established the intended rendering contract, but they predate the final canonical publication revalidation and full-goal closure. | After final public inputs validate, reopen both PDQ-39 examples, inspect voxel coverage, anatomy grayscale, voxel and fiber colorbars, RAS arrows, and interactive scene behavior, and record the review. |
| Cleanup policy and later sensitivity capability | ACCEPTED | Production `delete_run_cache_on_success` is false. Failed or partial runs are never cleanup-eligible, and shared scientific cache is outside the cleanup boundary. | Confirm no cleanup marker or missing cache entry before the no-expensive combined replay. |
| Final three-plan requirement audit | PENDING | This ledger names the production gates and authoritative evidence required for closure. | Reopen every named manifest, validator result, output root, and visual sample; update all rows to `ACCEPTED` only when direct evidence is terminal. |

## Open Implementation-Step Mapping

The implementation plan deliberately leaves the following Step headings and
performance checklist rows unchecked until their production evidence closes.
This mapping prevents an open source-plan checkbox from disappearing behind a
broader ledger label.

| Source-plan item | Ledger coverage |
| --- | --- |
| Step 1, freeze parity fixtures and characterize every resource path | `Shared physical preparation and configured-data parity`; `Cold/warm performance and scheduler acceptance` |
| Step 2, directly copyable SHA cache and single-write publication | `Resume and copied-cache implementation`; `Cold/warm performance and scheduler acceptance`; `Corruption, fail-once recovery, and deletion-rebuild acceptance` |
| Step 3, distinct voxel sampling and shared physical rows | `Shared physical preparation and configured-data parity` |
| Step 4, point-balanced one-pass `Omega_max` fiber preparation | `Shared physical preparation and configured-data parity`; `Cold/warm performance and scheduler acceptance` |
| Step 5, Layer-1 jitter and shared OSS/pPAM gate | `Independent spatial jitter computation`; `Independent OSS axis equivalence and pPAM`; both canonical extension rows |
| Step 6, sensitivity checkpoints, extension runs, and missing-parent rebuild | `Production identical resume acceptance`; all canonical extension rows; `Corruption, fail-once recovery, and deletion-rebuild acceptance` |
| Step 7, persistent spawned scheduler and global resource ledger | `Resource scheduling and guard contract`; `Cold/warm performance and scheduler acceptance` |
| Step 9, deterministic formal, bootstrap, pPAM, jitter, and sensitivity shards | `Resume and copied-cache implementation`; `Production identical resume acceptance`; `Cold/warm performance and scheduler acceptance` |
| Step 10, numerical, reuse, resume, deletion-rebuild, and resource acceptance | Every `PENDING` or `ACTIVE` Task 17 execution, parity, performance, recovery, resume, cache-first, and resource row |
| Step 11, current status and final commit | `Final three-plan requirement audit` |
| Final performance checklist, physical preparation through exact boundaries | The parity, jitter, OSS, cache, performance, resume, resource, and boundary-policy rows collectively retain every checklist clause |

## Current YAML Preflight

The current repository workflow resolves only `direct_voxel_model.yaml` and
`normative_fiber_model.yaml`; no Python loader references the historical
`model.yaml`. The direct-voxel profile SHA-256 is
`0a8d9a6654dd13001ceed147fccc80b474740377b15ddd41e02447794080569f`,
the normative-fiber profile SHA-256 is
`439c59b3cc2052d6de47886bfc80010780bd3f9677c6b85c38f93930682af27b`,
and the workflow SHA-256 is
`a508b484e99280d9db43d0f25d9528f7fddc274b28e200b64a3609bea5d0336a`.
The profiles retain the frozen tau and Coverage grids, main-analysis cells,
three fiber fold minima of one, and retained-cache policy. The repository
default remains three workers; formal worker overrides remain CLI/runtime
inputs. On 2026-07-25, all 23 configuration and application-CLI tests plus 12
subtests passed under Conda `leaddbs` with warnings treated as errors.

The main model-set publication, reporting, artifact/static audit, and
extension-v2 publication suites were repeated at the same checkpoint. All 35
tests passed with warnings treated as errors. This validates the local output
and publication machinery but does not replace the remaining canonical OSS,
combined, smoothing, and postprocess executions.

The synthetic end-to-end suite was also repeated on the isolated branch. All
seven tests passed with warnings treated as errors, covering local YAML
validation, planning, execution, resume, main publication, and sensitivity
publication across their real module boundaries. Synthetic fixtures do not
replace configured-data or formal-run acceptance.

The cache, run-cache cleanup, and sensitivity-checkpoint suites were repeated
at the same checkpoint. All 58 tests and 20 subtests passed with warnings
treated as errors. They cover content-addressed cache validation, portable
checkpoint closure, copied-root reuse, corruption rejection, and the rule that
failed or partial runs retain recovery state. Production identical resume and
deletion-rebuild acceptance remain separate pending gates.

The complete isolated fault harness and local resource-guard modules were
replayed again on 2026-07-25. All 15 fault cases and all 11 guard cases passed.
For harness tests that launch nested `conda run`, warnings-as-errors belongs on
the outer interpreter through `python -W error`; the launcher must clear the
inherited `PYTHONWARNINGS` environment variable. Exporting that variable causes
the base Conda interpreter to terminate on its own deprecation warning before
the declared synthetic fault command starts, which changes the observed exit
code and is a launcher failure rather than a harness rejection. This invocation
boundary changes no production command or warning policy.

## Repository Entrypoint Preflight

The following repository-owned entrypoints parse successfully in Conda
`leaddbs` with caller `PYTHONPATH` removed:

- `run_dual_frequency_models.py`;
- `validate_task17_connectome_parity_fixture.py`;
- `build_task17_preinstrumentation_windows.py`;
- `validate_task17_preinstrumentation_resources.py`;
- `validate_task17_resource_acceptance.py`;
- `init_task17_performance_byte_ledger_index.py`;
- `run_task17_performance_probe.py`;
- `build_task17_performance_byte_ledger.py`;
- `build_task17_performance_counters.py`;
- `run_task17_performance_matrix.py` for `prepare`, internal resumable matrix
  execution, terminal publication, and read-only `validate`;
- `run_task17_fault_acceptance.py` for isolated `init`, resumable `run`, and
  read-only `validate`;
- `validate_task17_performance_acceptance.py`;
- `validate_task17_extension_publication.py`;
- `repair_task17_display_smoothing_publication.py`; and
- `my_helper.fiber.core.viz.formal_postprocess`.

The generic runner exposes the required `run`, `sensitivity --resume`, and
`sensitivity --rebuild --rebuild-run-id` operations. Repository entrypoints
now collect cumulative CPU/resource evidence, derive the terminal byte ledger
and all counter sidecars, and validate the exact workers-1/3/6/12 cold/warm
matrix. The repository-owned benchmark harness prepares and revalidates the
immutable request, maximum-burden workload selection, DAG slices, and 72-row
closure. Its internal orchestration now prepares ordinary warm seeds, runs and
probes measured rows, resumes only complete terminal transactions, builds
counter evidence, and publishes the terminal matrix plus acceptance report.
The injected spawned-worker fixture and public `run` operation are implemented
in the isolated worktree, but no production matrix manifest exists. Merge,
complete regression, and production execution therefore remain open. The
dedicated
isolated fault harness is implemented, but its production plan and sequence
have not run. Those gaps remain part of their `PENDING` ledger rows. The
existence of implementation tests or lower-level telemetry cannot close them.

On 2026-07-25, the documented isolated module-path launcher was repeated under
Conda `leaddbs` with warnings treated as errors. The complete visualization
suite plus the extension-publication and display-smoothing suites passed all 51
selected tests. This revalidates the offline implementation boundary but does
not replace canonical publication, the 112-endpoint render, identical resume,
or visual review.

The isolated launcher must expose the worktree root plus a package-only
`dual_frequency` link. It must not add the whole `my_helper/fiber/core`
directory as a top-level module root: that directory contains an unrelated
MATLAB `coverage/` folder, which can shadow Numba's optional third-party
`coverage` import during pytest collection. With the package-only bridge and
the outer `python -W error` policy, the current complete visualization suite
passes all 38 tests. This is test-path isolation evidence; the installed
production package and visualization implementation require no change.

A broader 2026-07-25 pre-merge replay ran the isolated dual-frequency suite
without the two tests that resolve the mounted production study base. It
completed 736 tests, skipped four optional cases, and passed 314 subtests.
Eleven cases initially failed only at isolated-worktree boundaries: two
spawned children could not re-import pytest's temporary `core...` module name,
four activation fixtures could not see the main worktree's local 69-MB
template segmentation, and five frozen-acceptance cases could not see local
fixture or mounted artifact paths. Replaying the two spawn cases through the
importable `dual_frequency.tests...` package and the four activation cases
against the same main-worktree template made all six pass without a code
change. The visualization suite was then replayed separately and all 38 tests
passed. The five frozen-artifact cases remain intentionally deferred until a
permitted production inspection window and the post-merge main-worktree
regression; no VAL path was read to manufacture pre-merge closure.

The frozen formal postprocess request was also audited read-only. Its SHA-256 is
`144ad7a1e775c1bf01f5d99df285a87b31bae7075aa3692d714201f1953e6ab0`.
It names exactly the canonical direct-voxel and normative-fiber main and
final-in-sample publications, contains no `.runs` path, selects all available
scales, and requests paired-fit, voxel 2-D, and fiber 2-D components. The
configured output root remains absent until its production execution gate.

A static 3-D scene audit on 2026-07-25 confirmed that both PDQ-39 examples
resolve only canonical publication roots and retain an interactive figure
without writing FIG, image, PDF, or spin outputs. The voxel example requests a
0.5-mm inward sample depth. The shared renderer uses vik for signed voxel and
score-mapped fiber color, freezes anatomy slices as independent grayscale
truecolor, and sets RAS colors to `#F2000E`, `#0E6AAF`, and `#0CA228` without
changing the reference arrow-style parameters. Real canonical scene execution
and visual review remain required after the publication gates close.

The local display-smoothing stage was revalidated without opening the canonical
publication on 2026-07-25. Its 226-file closure contains 112 NIfTI payloads and
112 matching metadata documents; 108 payloads changed bytes and all 112 retain
their original finite support. Every payload size, payload SHA, metadata SHA,
relative path, algorithm, support policy, and input/output finite-voxel count
matches the repair manifest. The repair-manifest SHA-256 remains
`dff3ab60616b2bd9d77075bc6781f6ef928db666f1052ac31d5f02f4088f6b5c`,
and the staged artifact-index SHA-256 is
`9ea5003edcd97242d79d3e6cfbf92b770ab157cd1c54c21fe7d963b897331f9c`.
Direct NIfTI loading further confirms 56 one-millimeter and 56 two-millimeter
3-D payloads. Every actual finite-voxel count matches both metadata counts; the
aggregate finite-voxel count across the 112 payloads is 68040.
Canonical source-state comparison and promotion remain pending.

The same isolated checkpoint repeated the fault-acceptance, resource-guard,
strict and pre-instrumentation resource-validation, artifact/static audit,
performance-acceptance, byte-ledger, counter, and probe suites. All 99 tests and
two subtests passed with warnings treated as errors. These tests validate the
repository-owned evidence machinery; the production fault sequence and terminal
OSS/combined resource documents remain required.

The complete repository `test_task17_*` selection was then run as one closure
under the same environment. All 161 tests and two subtests passed with warnings
treated as errors. This combined replay confirms compatibility among the
benchmark, parity, publication, smoothing, fault, resource, and telemetry
fixtures; it remains lower-level evidence rather than a production acceptance
substitute.

The benchmark cache-seed layer now converts the accepted OSS closure into an
exact deduplicated entry list, requires an empty and disjoint row-local cache,
copies only the bound row and decision identities, and reopens every copied
entry through the ordinary full cache validator before returning one canonical
seed SHA. Reuse of a nonempty destination fails instead of merging state. The
focused performance-harness suite now has 30 passing tests. It covers the
required reference/add-on gate-family closure as well as extending the accepted
cache-closure fixture with seed-copy assertions.

The injected fixture preparation now copies only accepted `oss_rows` entries
into its separate row-local read-only cache, excludes every production decision
entry, and binds the permitted row identities, accepted closure SHA, copied
seed SHA, and fixture SHA. This is preparation support only; the spawn-worker
descriptor and measured execution remain pending until the active independent
OSS process has terminated.

The future row runner can now reopen one row identity exactly once, resolve its
single bound slice, strict-decode the persisted execution plan, and rederive
the selected non-checkpoint task closure plus plan hash. Missing, duplicated,
or changed row/slice bindings fail before any runner child is launched.
It can also open the marker-complete benchmark root without repair, bind the
original minimal request SHA and plan ID, rederive the resolved-plan SHA, and
revalidate all 72 immutable row contracts before selecting work.
Checkpoint-root loading now requires the exact persisted parent/OSS task IDs,
completed result envelopes, planned output-record types, source-file SHAs, and
full slice closure; overlap with any selected task fails before import.
Row-local installation removes the source-only task ID field before using the
RunStore API, then reads every state back and requires exact equality with the
validated source envelope before readiness can be published.
The prepared plan now persists a path-safe Conda environment token and
canonical existing working directory as its immutable child execution
environment; neither can be supplied again by a later `run` invocation.
The child-side validator requires both the canonical working directory and the
active Conda environment or prefix name to match before a row RunStore opens.
Cold-cache preparation now emits a canonical zero-entry proof. Unmeasured
ordinary warm seeds may enumerate only their initially empty benchmark-local
cache, fully validate each resulting entry, publish a slice-bound nonempty
entry closure, and direct-copy that exact closure into an empty measured-row
cache. Changed slice IDs, manifests, or entry sets fail before measurement.
The row-cache dispatcher now materializes each frozen condition explicitly:
ordinary and real-solver cold use a proven-empty cache; ordinary and injected
warm use the slice-bound unmeasured seed; injected rows also receive their
separate accepted-row fixture; and real-cache-hit warm receives the verified
independent OSS row/decision closure. Invalid cold real-cache-hit combinations
fail before runner startup.
Attempt preparation now validates the immutable row contract and exact slice,
loads the accepted checkpoint states, commits `checkpoint_closure.json`, then
commits `row_cache_state.json`, and writes `attempt_plan.json` last. That marker
binds the contract, monotonic attempt number, plan hash, selected/imported task
closures, and both input-document SHAs; a terminal row cannot create another
attempt.
Child preflight now reopens the attempt marker, contract, slice, checkpoint
states, result record types, cache-state document, actual row-cache entries,
and any injected fixture closure. It rejects path aliases, changed document
SHAs, selected/imported drift, nonempty cold caches, injected fixtures on
ordinary rows, and injected row identities outside the accepted closure before
creating a RunStore.
The child can now reopen all four bound source files, verify their SHAs,
reconstruct the parent resolved selection, compile the ordinary production DAG,
and require both the scientific-configuration hash and full-plan hash to match
the immutable benchmark plan before using its selected slice.
The hidden row-child executor is now implemented for ordinary, real-cache-hit,
and authorized real-solver slices. It creates an isolated RunStore and
row-local scientific cache, installs only validated checkpoint roots, retains
the production registry/provider and persistent spawn pool, publishes
`runner_ready.json`, waits for the parent measurement token, executes the exact
slice, finalizes the run, rejects restored selected tasks, and publishes a
SHA-bound child result. The isolated implementation now supplies injected rows
with the frozen spawn-worker fixture descriptor while leaving every ordinary
production descriptor null.

The corresponding parent row transaction is also implemented. It launches the
bound child and external probe in separate harness-owned process groups,
requires readiness before creating the live byte-ledger index, requires one
probe sample before releasing the child with `measurement_start.json`, and
waits for both processes to terminate. It then validates exactly one finished
segment and one terminal `runner_exit`, builds the byte ledger, requires the
probe and ledger byte totals to match, runs the artifact/static audit and
counter builder, and publishes a SHA-closed terminal row only after all
evidence succeeds. Failures retain a partial monotonic attempt and terminate
only the two harness-owned process groups. Injected spawned-worker support,
matrix-level manifest/acceptance, and public `run` are implemented in the
isolated worktree; production execution remains pending.

Configured candidate-parity generation is no longer an implementation gap.
The harness now requires the exact 224 prepared-endpoint closure and pairs it
with 112 realized finals plus 112 sensitive-connectome evaluations. It derives
voxel selected IDs from SHA-verified source indices and canonical parent IDs,
reuses fiber valid-union ID artifacts directly, executes the shared full/fold
parity report, and binds both plan and report into the marker committed last.
The v2 parity plan omits redundant selected-exposure copies and caches repeated
physical parent candidate closures; v1 remains readable. Five candidate-parity
tests and 27 harness tests pass. A read-only derivation against the configured
parent produced 224 rows, all four model families, 8 unique physical parent
exposures, and 8 unique selected-ID payloads. The production-scale report scan
has not run because the independent OSS process still owns the active VAL
workload; parity acceptance therefore remains pending.

The configured-data replay request is frozen across two versioned inputs.
`config/four_model_v1/acceptance/task17_connectome_parity_fixture.json` has
SHA-256
`7255126c155aa616faac1457103169597ecd9c8c9707976ecb26e71c617fba6c`
and contains only the retained scientific authority: the completed v8 parent
identity plus complete physical and prepared payload, feature-axis, shape, and
role closures. `config/four_model_v1/workflow_task17_parity.yaml` has SHA-256
`4ad144f4aa2c94a5d85ac89e84cf389474d8e82d31d4e642b8b5347d98cfb4cc`
and owns the execution boundary: observed cutoff, all model families and
connectomes, one cold worker, expensive producers disabled, retained successful
cache, dedicated cache
`/Volumes/VAL/STNSNr/cache/dual_frequency_task17_parity_v1`, and dedicated run
root `/Volumes/VAL/STNSNr/summary/spot/acceptance/.runs`. The plan binds the
first invocation to run
`task17-parity-v1-post-refactor-20260722` with one worker, then binds a
14-worker exact resume to that same run root. The verifier alone binds the
retained parent, replay cache, replay run, and immutable output
`/Volumes/VAL/STNSNr/summary/spot/acceptance/task17-physical-parity-replay-v1.json`.
Keeping runtime paths and worker ceilings out of the scientific fixture
prevents execution policy from changing the authority SHA. These inputs are
frozen and internally consistent, but execution remains pending until
independent OSS releases VAL.

The ordinary unmeasured warm-seed executor is implemented. It derives 7
ordinary seed slices plus one injected slice, runs each ordinary slice once
against a proven-empty isolated cache, binds its exact imported checkpoints,
rejects restored selected tasks, fully verifies the resulting cache, and
publishes the seed manifest last. Existing seeds must remain below their own
transaction root and revalidate byte-for-byte. Real-cache-hit pPAM continues
to use the independent OSS closure directly. The isolated injected-worker
implementation now enables the eighth injected seed without changing ordinary
seed execution.

Internal matrix resume and terminal publication are implemented. The harness
serially resumes the exact 72 rows, reuses only SHA-complete terminal
transactions, creates monotonic attempts for partial rows, derives storage
classification from scheduler windows, derives worker/cache-comparable
numerical identity from normalized selected-task results, and permits
`not_run` only for unauthorized real-cold pPAM. A complete closure publishes
the matrix, runs the existing strict validator, and commits its acceptance
report. This intermediate closure passed five candidate-parity tests and 30
performance-harness tests before injected-worker support was added.

The implemented injected-worker contract uses an optional
`BenchmarkOSSInjectedFixtureSpec` on `SpawnWorkerSpec`. Its null default leaves
all production paths unchanged. When present, worker initialization must retain
an actual `StudyRuntimeInputProvider`, validate the versioned row-local fixture
root, and replace only `oss_producer_toolchain` with the deterministic
ten-sample benchmark implementation. The pre-spawn child validates the full
fixture closure once, while each worker fully reopens only a requested
permitted row. Both warm-seed and measured-row contexts derive this descriptor
from their prevalidated fixture document; callers cannot supply a separate
cache root or row list.

A 2026-07-25 static construction audit found exactly four runtime
`SpawnWorkerSpec` call sites. The ordinary main and sensitivity service call
sites omit the fixture field and retain its null default. Only the benchmark
warm-seed and measured-row call sites populate it, and both use
`_benchmark_oss_fixture_spec` over their already validated fixture document.
No other production or extension path references the injection field.

The CLI now exposes the existing internal `run` orchestrator. Its read-only
`validate` path additionally distinguishes a prepared root from a terminal
root, rejects one-sided matrix/report publication, recomputes repository
acceptance for a terminal matrix, and requires exact document equality with
the stored deterministic report without repairing it.
Five candidate-parity tests and 35 performance-harness tests pass in the
isolated worktree. Merge and complete regression remain intentionally deferred
until independent OSS releases the production checkout and its memory
reservation.

The isolated handoff is rooted in two ordered commits on top of main baseline
`f08658f0d`: implementation commit `186b36d6f` and request commit
`ae0b60486`. Documentation and regression closure continue on the same branch.
The terminal merge must therefore preserve the complete contiguous range after
`f08658f0d` through the reviewed branch head, rather than selecting only the two
foundational commits. The frozen request SHA-256 is
`c9f4bca02361f7004adc383e95df69a40a5dbd31ca30e0acf64286073948e839`.
The terminal merge sequence must revalidate the request digest before `prepare`;
no commit in this range authorizes benchmark execution while the independent
OSS lineage remains active.

If main remains an ancestor of `task17-perf-injected-worker`, the required merge
is a Git fast-forward-only merge of that branch after the OSS writer exits.
Selecting individual commits is prohibited because later tests and acceptance
documentation are part of the same reviewed range. If fast-forward is no longer
possible, stop and re-audit the divergence in a clean worktree before any merge
or benchmark preparation.

A 2026-07-25 pre-merge scope audit confirms that baseline `f08658f0d` remains
an ancestor of reviewed head `910b05fc0`. That closed range contains 24 commits
and exactly seven changed paths: the performance harness, spawned-worker
implementation and export, its focused test, the frozen benchmark request,
this acceptance ledger, and the Task 17 implementation plan. It contains no
formal workflow YAML, model policy, publication implementation, visualization
implementation, or unrelated repository path. This proves review scope only;
the ancestry and changed-path closure must be recomputed immediately before the
eventual fast-forward merge.

A later 2026-07-25 scope audit at reviewed head `bfdcd0165` confirms that
baseline `f08658f0d` remains an ancestor. That closed range contains 31 commits
and exactly eight changed paths. The only path added to the earlier seven-path
closure is `tests/test_executor.py`, where the synthetic historical-OSS resume
fixture now supplies an isolated memory state so its 48-GiB admission grant
cannot depend on live production memory pressure. The remaining seven paths
are unchanged in scope. Both worktrees were clean during this audit. The final
ancestry, commit count, path list, and request digest still must be recomputed
after the independent OSS writer exits and immediately before the
fast-forward-only merge.

A matching semantic audit confirms that the added fixture descriptor defaults
to null, ordinary main and sensitivity worker construction never populate it,
and only benchmark warm-seed and measured-row construction derives it from the
prevalidated fixture document. Worker initialization retains the ordinary
provider class and changes only its OSS toolchain when that explicit descriptor
is present. Four focused tests covering descriptor validation, injected
toolchain isolation, ordinary production initialization, and accepted-row
closure passed under Conda `leaddbs` with warnings treated as errors. This
closes the pre-merge production-path isolation review; it does not replace the
post-merge complete regression.

The complete isolated dual-frequency test tree was collected read-only on
2026-07-25 through package-only Python-path links. The bridge exposes exactly
`dual_frequency` and `seed_target_connectivity` from the isolated worktree,
while the worktree root exposes `my_helper`; it does not expose the entire
`my_helper/fiber/core` directory. All 764 tests were discovered without an
import or collection error. The same bridge now passes all seven synthetic
end-to-end tests, including four-family main execution, selective resume,
independent jitter and OSS extensions, missing-parent rebuild, and guarded
cleanup. This is runner-readiness evidence only: it does not claim that the
complete regression executed, and the post-merge full run remains mandatory
after the active OSS resource reservation ends.

The formal request is frozen at
`config/four_model_v1/acceptance/task17_performance_benchmark_request.json`.
It references only the parent-run input copies, declares the 64-GiB ceiling,
and leaves real-cold solver authorization null. The configured benchmark root
is separate under `summary/spot/acceptance`. Preparing or executing it remains
pending until independent OSS is terminal and the isolated implementation has
passed complete regression in the production checkout.

The six combined-preflight cache-first boundary tests were repeated on
2026-07-25. They prove authorized OSS publication followed by unauthorized
decision reuse, rejection of an OSS miss before toolchain entry, copied-cache
OSS reuse without a solver, copied-cache jitter reuse without a physical
producer, rejection of a jitter miss before producer entry, and executor
admission only for tasks explicitly marked cache-first expensive. All six
passed with warnings treated as errors. Production combined execution remains
the required full-DAG proof.

## Final Closure Rule

The complete goal remains open while any row is `ACTIVE`, `PENDING`, or
`BLOCKED`. In particular, the following sequence cannot be skipped:

1. terminal independent OSS and downstream pPAM closure;
2. completed-jitter identical resume and repository-owned canonical jitter-v2
   validation;
3. configured-data shared-preparation parity replay and independent OSS
   exact resume plus resource acceptance;
4. canonical OSS-v2 replay;
5. no-authorization combined execution, exact resume, and resource acceptance;
6. canonical combined-v2 replay;
7. complete cold/warm scheduler benchmark, corruption, fail-once recovery, and
   isolated deletion-rebuild acceptance;
8. display-smoothing promotion and canonical revalidation;
9. formal 112-endpoint postprocess, identical resume, independent validation,
   and sampled 2-D/statistical visual review;
10. final canonical voxel and fiber 3-D scene review; and
11. requirement-by-requirement reinspection of all three source plans.
