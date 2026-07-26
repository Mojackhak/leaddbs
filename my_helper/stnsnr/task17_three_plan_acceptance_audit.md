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

The repository-owned plan-audit guard must retain exactly 24 uniquely named
Evidence Matrix rows, reject an unknown status or malformed table row, and
require the `Final three-plan requirement audit` row to remain non-accepted
while any other row is non-accepted. Only a completely accepted matrix may
mark that final row accepted.

## Evidence Matrix

| Requirement | Status | Current authoritative evidence | Remaining acceptance action |
| --- | --- | --- | --- |
| Production YAML drives all four model families | ACCEPTED | `config/four_model_v1/workflow.yaml` references the production direct-voxel and normative-fiber profiles; configuration, CLI, in-sample, and cleanup fixtures pass. The repository-owned production-source guard now binds all three exact source SHA-256 values plus model references, ordered grids, pre-specified cells, 12-subject floors, all three fold minima, and retained-cache policy; the complete configuration module passes 20 tests and 13 subtests. The historical `model.yaml` is explicitly outside the current loader and lineage. A fresh audit found that the current direct-voxel source YAML is byte-identical to the completed parent input, while the current normative-fiber source differs only in the corrected `p(A) > 0.5` comment and parses to the same document. The completed run scientific-configuration hash matches its resolved snapshot and both canonical model manifests. | Confirm that display-smoothing promotion restores the same completed model-manifest bytes and does not alter either resolved profile. |
| Frozen voxel and fiber source grids | ACCEPTED | Direct voxel uses tau 150, 180, 200, 220, 250, and 300 with pre-specified 200. Normative fiber uses tau 200, 350, 400, 450, 600, and 800 with pre-specified 400. Both use Coverage 5, 6, 7, 8, 10, and 12. The direct-voxel and normative-fiber sections of the completed parent `configuration_resolved.yaml` exactly match the parsed canonical `resolved_direct_voxel_model.yaml` and `resolved_normative_fiber_model.yaml`. Each published resolved file matches its own manifest SHA-256, and both published study snapshots are byte-identical to the parent input snapshot. The post-smoothing full-payload validator reopened both resolved files and study snapshots and reproduced all four declared SHA bindings. Raw source YAML and resolved publication YAML are intentionally different serializations and are not required to be byte-identical. | Reopen the retained validation report during final publication audit. |
| Boundary and computability policy | ACCEPTED | Current runtime and formal kernels include equality for both scientific boundaries: voxel and fiber exposure at tau is suprathreshold, and a feature with subject Coverage at the requested minimum is retained. The 12-subject floor remains active, and every declared connectome requires at least one fold candidate fiber. Four focused boundary and production-profile tests passed on 2026-07-25 with warnings treated as errors. | Repeat the repository-owned final static audit after all production children terminate. |
| Main four-family formal run | ACCEPTED | Parent run `task17-main-v8-tau-grid-formal-20260717` is terminal with `final_status` `completed`. All 1512 persisted task documents have unique task IDs and terminal `completed` status; no task is failed, skipped, or running. Both execution segments are terminal `finished` spawn-process segments with 14 workers. The run artifact index has 7468 unique artifact IDs and URIs. Its 11388 task-result artifact references reduce to the same 7468 unique URI/SHA-256 pairs, with no task artifact outside the index and no indexed artifact outside the task closure. The 224 unique final decisions split into 112 `realized_primary` records and 112 `no_final_model` sensitive-connectome records. Every realized decision maps to exactly one completed realization task, its decoded `FinalSelectionRecord`, its final-record ID, final-key ID, and exact causal-task closure. The realization closure contains 28 endpoints in each of reference voxel, add-on voxel, reference fiber, and add-on fiber. The no-final closure contains 56 reference and 56 add-on sensitive-connectome endpoints, has no model IDs or realization task, and maps exactly to the two sensitive-connectome evaluation services. The canonical publications contain 56 direct-voxel and 56 normative-fiber `final_model.json` records. Every public record is indexed as completed and matches the decoded parent final record in role, scale, branch, tau, Coverage, status, and final-record ID; all declared source, feature-axis, and artifact links exist and are indexed. Commit `dba11ec7d` adds the full run-artifact validator. Five focused tests pass; complete discovery passes 777 tests and 329 subtests. The production validator reread all 73406341913 payload bytes, matched all 7468 payload SHA-256 values, all 11388 task references, and all 1512 task documents. The indexed-payload closure SHA-256 is `792433fa43996dbd4c1015c79d77f663530599feee2eb8433ad563cc8850e6c8`; the task-document closure SHA-256 is `c38d0f12610fc1a2f4ae48e8427d352cf40f0ea90b4e8d12e14a30e19c478e50`. The atomic report SHA-256 is `e72b4b9b292faabf3e5c571b8950acf74fc9d521bc3784127890cb12c753863c`, and a second complete 73.4-GB invocation preserved its bytes and mtime. | Reopen the retained structural and full-payload reports during the final three-plan audit. |
| Canonical main model-set publication | ACCEPTED | Completed direct-voxel and normative-fiber model-set publications are the only allowed public parents, and postprocess preflight resolves them without a run-store fallback. Commit `3c45d57b7` adds the repository-owned full-payload validator. Five focused tests pass; complete dual-frequency discovery passes 772 tests and 329 subtests with warnings treated as errors. After display-smoothing promotion, the production validator hashed all 5690 indexed payloads and 1062720468 bytes, verified both terminal manifests, resolved profiles, study snapshots, root identities, 28-scale closures, and exactly 56 final models per domain. Direct-voxel and normative-fiber indexed-payload closure SHA-256 values are `cc48441d4109648c6e82c752f202763754c414460c6957ce689db932143a86db` and `a25d1936fc699ca4ea303ff87daa22bbe9775995fd350b330badd6acf901e3e6`. The atomic report SHA-256 is `8cf595681415820f5224fb7aeebe5023a702046cde3f0efefa485c3a559d782f`; a second full invocation preserved its bytes and mtime. | Reopen the retained report during final three-plan audit and require downstream publications to preserve these parent-manifest bindings. |
| Final in-sample inference and publication | ACCEPTED | Both model-set domains contain the canonical final-in-sample v2 extension. A fresh public-only closure audit found 56 direct-voxel and 56 normative-fiber results with 112 globally unique endpoint IDs. Every result has the complete paired in-sample and LOOCV statistic set, matching subject masks and finite counts, 10000 requested and finite permutations on both sides, and a final-model ID, selected tau, and selected Coverage matching its indexed canonical final-model record. Both parent-manifest bindings are current, all four publication manifests are terminal, all indexed rows are completed, and the paired metadata contains no run-store or runtime-work path. The audit found no mismatch. | Confirm that the terminal paired-fit plots consume this exact 112-endpoint closure without substituting a run-store source. |
| Shared physical preparation and configured-data parity | PENDING | Shared geometry, one-time physical exposure, inclusive fiber overlap, exact minimum-grid `Omega_max`, side-specific fiber peak reduction, cache-backed subject/feature views, copied-cache reuse, and bounded parity fixtures pass. A fresh provider/jitter/activation-universe/OSS-axis/toolchain replay passed 106 tests and 26 subtests with warnings treated as errors. These fixtures prove the implementation boundary but do not compare the complete configured production matrices. | After independent OSS releases the formal connectome and VAL I/O path, run the repository-owned configured-data post-refactor replay. Record complete matrix parity, worker-count determinism, physical-row counters, logical-versus-physical write reduction, and absence of endpoint matrix copies or repeated full-connectome traversal. |
| Cold/warm performance and scheduler acceptance | PENDING | Persistent spawned scheduling, global CPU/memory/I/O/solver ledgers, parent-only state mutation, process-local cache verification, vectorized kernels, and deterministic RNG boundaries pass static tests. The repository-owned cumulative-CPU probe, five-second scheduler-window publication, exact 72-row matrix validator, source-evidence binding, deterministic report, worker/default decision, RSS/swap gates, and utilization-window gate are implemented. Every executed row binds the exact probe SHA; I/O classification is closed to compute-bound or storage-limited; and a non-default worker promotion requires matched compute-bound rows that are all faster than workers 3 while retaining both wall times in the report. All 28 counters derive from immutable task fragments, configured parity, artifact/static audit, terminal segment fields, and a SHA-bound source/scratch byte ledger; caller-entered counter values are rejected. Commit `f73d849d8` binds every scheduler sample to its contemporaneous managed-memory ceiling and validates the initial, minimum, maximum, and final segment closure. The benchmark harness validates the minimal operator request, accepted parent and independent OSS binding, exact source identities, maximum-burden scientific requests, measured/imported DAG task slices, protected-root separation, optional solver authorization, and the exact 72-row key closure. Its runner-readiness and measurement-start protocol binds the row, child PID, slice-plan SHA, imported task closures, byte-ledger path, and byte-ledger SHA before selected work may start. Stable row identities, immutable row contracts, monotonic attempt directories, terminal evidence SHAs, changed-contract rejection, and changed-evidence rejection are implemented. `prepare` writes the resolved plan, all 72 contracts, and only then the complete contract-SHA marker; read-only validation rejects missing, extra, changed, or path-aliased contract roots. The sole unauthorized real-cold solver branch publishes an immutable false-authorization preflight and terminal `not_run`; other rows cannot use that status. Every statistical slice includes its selected endpoint's base physical producer so a cold row can create the row-local shared-cache closure and a warm row can prove a cache hit without copying a selected-task result. Each resolved slice persists a closed executable plan with imported direct parents converted to checkpoint-only roots while preserving every selected task's original service, parameters, gates, and internal dependencies. pPAM injected, real-cache-hit, and real-solver rows have separate slice identities and all measure the OSS equivalence gate; the accepted OSS outcome is an injected/reference authority or cache seed, never a copied selected-task result. `prepare` decodes the exact two terminal OSS gate records, resolves only their referenced decision and final/Omega row entries from the configured shared cache, verifies stable scientific keys and final-axis probability parity, and binds every cache-manifest SHA plus a canonical closure SHA into the resolved plan. The benchmark-only injected toolchain reconstructs exact ten-sample activation counts from those accepted rows and rejects requests outside that closure. Ordinary and injected warm-seed production, child/probe launch, terminal row evidence, identical row resume, normalized numerical identity, scheduler-derived I/O classification, 72-row matrix publication, strict acceptance invocation, public `run`, and read-only terminal validation are implemented in the isolated worktree. Five candidate-parity tests pass, and a fresh complete performance-harness replay passes 36 tests with warnings treated as errors. No production matrix has run. | After independent OSS terminates, merge the isolated implementation and run the complete regression. Then execute the workers 1, 3, 6, and 12 cold/warm matrix without substituting skipped or default-zero rows. Retain every terminal counter sidecar, exact-resume proof, deterministic matrix, and acceptance report. |
| Corruption, fail-once recovery, and deletion-rebuild acceptance | PENDING | Static cache, resume, checkpoint, and rebuild fixtures reject payload, shard, axis, and result corruption and selectively rerun affected descendants. The repository-owned marker-bound isolated harness implements complete parent/publication SHA closure, exact copied-cache marker closure, path-safe unique case IDs, absolute and relative command confinement, quarantine-and-restore corruption, immutable and task-bound pre-resume fail-once evidence, protected-artifact checks, distinct-lineage rebuild, unauthorized copied-cache replay, exact or NPY-tolerant one-shot comparison, contract-bound terminal case reuse, and read-only validation that cannot repair a changed report. Fifteen focused harness tests pass with warnings treated as errors. A later complete collect-only pass discovers 764 tests without import or collection failure; it is runner-readiness evidence and not a claim that all 764 tests executed. A 2026-07-26 scope review confirmed that the immutable plan plus harness `init`, `run`, and read-only `validate` operations are the approved repository-owned boundary; a second plan-builder entrypoint is not required. The production-scale sequence has not run. | After terminal OSS and combined authorities exist, prepare and review the exact six-case production plan. In its marked isolated root, execute all three corruption classes, fail-once recovery, missing-parent rebuild, copied-cache replay, and one-shot comparisons; retain and revalidate the terminal deterministic report. |
| Independent spatial jitter computation | ACCEPTED | `task17-jitter-v8-support-preserving-formal-20260719` completed its support-preserving block and endpoint closure with no terminal failure. Jitter compilation, selective block resume, cache-first dispatch, and extension publication boundaries pass 25 focused tests with temporary fixtures. | Reopen the completed child manifest, block closure, endpoint closure, artifact index, and parent binding during final audit. |
| Canonical independent jitter-v2 publication | ACCEPTED | Commit `f20b7754e` makes terminal extension-v2 artifact replay index each immutable metadata sidecar and adds an exact regular-file closure regression. Focused publication coverage passed 22 tests; the complete main dual-frequency suite passed 767 tests and 329 subtests with warnings treated as errors. The four invalid index/manifest commit files were archived with their original SHA-256 values under `/Volumes/VAL/.Trashes/501/task17-jitter-v8-extension-v2-index-repair-20260726`; no scientific payload or metadata sidecar moved. Unfiltered replay rebuilt each domain as 226 indexed files for 56 results. The direct-voxel and normative-fiber payload closures retained their pre-repair SHA-256 values `16c42c2d513b39205009732f56030c39784350caac75de4fb2ae4b829cae4e25` and `75a2f827004b7110b1f5ddc8187547c5a85e69188645142b3ce84bdd3d25d5d4`. A second replay preserved both index and manifest bytes and mtimes. The repository validator passed both roots twice and atomically retained report SHA-256 `f5491c15fd2d07b81a1f8b7910d345e63b45d61f59eb929ce597bf3073d95040`. | Reopen the two roots and the retained validator report during the final three-plan audit; do not modify the accepted jitter-v2 publication. |
| Independent OSS axis equivalence and pPAM | PENDING | `task17-oss-v1-inclusive-formal-20260719` has a stable terminal reference group of 34 decisions and 68 rows, all pass, produced by Decision 39 cache-only promotion without a reference solver call. Add-on work durably committed 12 pass decisions and 24 distinct complete row-cache entries; every committed decision had maximum probability difference, state mismatch count, and activation-count mismatch count of 0. The newest durable add-on decision committed at 2026-07-26T08:28:36Z. At 2026-07-26T10:00:16.144105Z, the checked-in guard recorded `val_unmounted_sigterm` and terminated the `segment_0018` process tree before the in-flight next row or decision was published. A post-event process audit found no remaining runner, persistent worker, solver, or guard. The persisted task ledger contains 393 completed tasks, one interrupted add-on gate marker, 196 dependency skips, and no terminal failed task. The user explicitly authorized continuation after VAL was remounted and verified writable at a 10000000000-bit/s USB link. `segment_0019` started at 2026-07-26T14:49:21.648100Z through `--resume` with 14 workers, one solver token, and a new checked-in guard. Startup reused the complete reference and add-on closures. At 2026-07-26T15:05:25.248089Z, the add-on solver was executing `sample_09`; task-tree RSS was 6198018048 bytes, the segment peak was 17354375168 bytes, swap had not grown, and the guard had no stop event. The 12-decision cache count remains progress evidence only; the terminal add-on gate record is the sole authority for its final `row_decision_ids` closure. | Allow guarded `segment_0019` to reach terminal add-on closure, execute all dependency-derived downstream tasks, and require zero terminal failures plus complete reporting, artifact-index, identical-resume, and resource validation. |
| Canonical independent OSS-v2 publication | PENDING | Self-contained extension-v2 publisher and validator fixtures pass. A fresh 2026-07-26 replay passed all 16 publication tests and all 6 independent validator tests with warnings treated as errors. The source OSS child is not terminal. | Publish twice without filters, validate the normative-fiber OSS-v2 root, and audit source/parent bindings plus forbidden paths. |
| Cache-first combined jitter and OSS replay | PENDING | Compiler, executor, physical jitter, OSS decision, and activation-provider fixtures prove cache-first behavior and fail before a producer call on a miss without authorization. A fresh 2026-07-26 replay passed ten focused tests with warnings treated as errors, including copied physical-jitter and OSS caches, historical accepted-OSS promotion, corrupt or missing rows, combined-plan compilation, and provider-level cache hit and unauthorized miss boundaries. | Start the frozen combined child without `--allow-expensive-producers`, attach the checked-in guard, and require complete cache reuse plus terminal DAG closure. |
| Canonical combined-v2 publication | PENDING | Publisher and validator fixtures cover both public domains. The fresh 2026-07-26 replay passed the same 22 publication and independent-validator tests. No terminal combined child exists. | Publish twice, validate both domain roots, and audit complete jitter plus normative-fiber OSS scope. |
| Resume and copied-cache implementation | ACCEPTED | Resume fixtures use input JSON/YAML identities and complete result JSON records, ignore repository code identity, selectively rerun missing blocks and consumers, and reuse a directly copied cache under a different path. A fresh cache/resume/cache-first audit passed 52 focused tests and 20 subtests; the complete executor file then passed 41 tests and 8 subtests with warnings treated as errors. The audit also removed host-memory dependence from the historical accepted-OSS cache-only resume fixture by freezing only its synthetic ledger state at 128 GiB. Production admission, cache identities, runtime code, and the active OSS process were unchanged. | Recheck these fail-closed static contracts after the last implementation change. |
| Production identical resume acceptance | PENDING | The main and completed jitter lineages preserve resumable state, and the active OSS lineage has repeatedly restored its immutable plan and completed predecessors without invalidating scientific products after code-only changes. The complete terminal-child identical replay has not yet run. | After each production child becomes terminal, run its exact resume path, prove no accepted payload was rewritten, and retain the task-outcome and manifest evidence. |
| Resource scheduling and guard contract | PENDING | One persistent spawn pool, 14-worker ceiling, single solver token, 48-GiB authorized-producer admission charge, task-tree RSS `< 64 GiB`, and swap growth `< 1` byte are implemented and covered by static tests. The strict validator closes safe segment identity, initial/minimum/maximum/final managed-memory and reserve declarations, window-local managed-memory reservations, connectome-I/O/solver/BLAS ceilings, CPU/memory/I/O/solver/running-task peaks, exact admission maps, contained SHA-bound scheduler windows, exact UTC/elapsed/runnable/storage derivations, and a final zero-RSS guard terminal row. Segment 0016 proved that cache-only replay still inherited the producer grant and that a temporarily memory-blocked empty running set failed instead of waiting. Decision 40 implements a 512-MiB token-free cache-read grant, one-second production resampling for structurally admissible memory waits, and immediate failure only for structural impossibility or dependency deadlock. A fresh 2026-07-26 replay passed all 44 guard, strict acceptance, and pre-instrumentation tests with warnings treated as errors. The `segment_0018` guard correctly detected the VAL unmount at 2026-07-26T10:00:16.144105Z and terminated the complete process tree before another publication commit. This is accepted fail-safe behavior but not terminal resource acceptance; the interrupted segment and its guard remain immutable evidence and cannot be combined with a later epoch. The explicitly authorized `segment_0019` resume has an independent checked-in guard and remained within its RSS and swap boundaries at the latest documented sample. | Retain the complete `segment_0019` evidence independently and validate only its terminal epoch. Build the repository-owned maximum-row measurement window from the terminal independent OSS closure and repeat strict acceptance for combined. |
| Display smoothing v2 publication | ACCEPTED | With the OSS process tree absent, the repository validator reopened `/private/tmp/task17-display-smoothing-v2-stage.zAofAX` against canonical raw support and accepted 112 targets, 108 changed NIfTIs, and repair-manifest SHA-256 `dff3ab60616b2bd9d77075bc6781f6ef928db666f1052ac31d5f02f4088f6b5c`. The repository promotion transaction archived every replaced v1 file under `/Volumes/VAL/.Trashes/501/task17-display-smoothing-v1-20260723`, installed all payload and metadata replacements atomically, restored the completed model manifest byte-identically, and committed candidate artifact-index SHA-256 `9ea5003edcd97242d79d3e6cfbf92b770ab157cd1c54c21fe7d963b897331f9c`. Post-promotion validation passed the canonical root. An identical second promotion preserved the index, model manifest, and transaction SHA-256 values; the transaction SHA-256 is `b718060bb832e5c28a1d002cbff80c7380099413c70390fbb8e6a9e9fae52ae8`. | Reopen the canonical root and Trash transaction during final audit, and require formal postprocess to consume these promoted v2 derivatives. |
| Formal paired-fit, voxel 2-D, and fiber 2-D output | PENDING | The durable request structurally resolves 28 scales, 112 endpoints, canonical public inputs, and all three batch components. Its repository-owned static guard binds the exact request SHA-256, four canonical publication aliases, manifests, `all_available` scope, ordered three-component closure, output root, resources, and absence of run-store paths without reading publication payloads. A nondefault-cell fixture proves that the endpoint resolver preserves voxel tau 180 with Coverage 8 and fiber tau 600 with Coverage 10 instead of using modality-wide defaults. After display-smoothing v2 promotion, the real public-only `--validate-only` preflight passed again with four publications, 28 scales, 112 endpoints, `paired_fit`, `voxel_2d`, and `fiber_2d`, the accepted anatomy and masks, the 1.7-million-fiber formal connectome, all 18 target definitions, and PDF/PNG tooling. It created no formal output root. The request and formal component suite pass all nine tests together. A fresh 2026-07-26 replay passes all 42 visualization tests and the exact 27-test publication closure with warnings treated as errors; the latter contains 16 general publisher tests, 6 extension validator tests, and 5 model-set validator tests. | After terminal OSS-v2 and combined-v2 publication, render the formal output, repeat without force, verify no completed component rewrite, run `--validate-output` twice, and visually inspect representative outputs. |
| Interactive voxel and fiber 3-D implementation | ACCEPTED | The two PDQ-39 MATLAB examples resolve only canonical publications, request 0.5-mm inward voxel sampling, use signed `vik` mappings and independent colorbars, preserve grayscale anatomy, and create no export unless explicitly requested. Their adapter rejects a run-store `study_base_path` or connectome geometry path before reading it. Both negative fixtures, both positive scene fixtures, and the complete 42-test visualization suite pass. | Retain both examples and their migrated export helpers unchanged through final publication work, then open both real canonical scenes for visual review. |
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
| Physical preparation occurs once before endpoint/scale fan-out | `Shared physical preparation and configured-data parity`; `Cold/warm performance and scheduler acceptance` |
| Direct voxel and normative fiber reuse bilateral exposure rows without formula drift | `Shared physical preparation and configured-data parity`; `Frozen voxel and fiber source grids` |
| Logical connectome points are covered once and minimum-grid `Omega_max` remains exact | `Shared physical preparation and configured-data parity`; `Cold/warm performance and scheduler acceptance` |
| Jitter schedules and exposure are Layer 1 while endpoint statistics remain Layer 2 | `Independent spatial jitter computation`; `Cache-first combined jitter and OSS replay` |
| OSS/pPAM uses formal-connectome `Omega_max` only after exact final-axis equivalence | `Independent OSS axis equivalence and pPAM`; `Canonical independent OSS-v2 publication` |
| Target-cache verification occurs once per entry and process without payload-hash rereads | `Resume and copied-cache implementation`; `Cold/warm performance and scheduler acceptance` |
| OSS row and decision identities are scientific, cache-first, and implementation-fingerprint independent | `Independent OSS axis equivalence and pPAM`; `Resume and copied-cache implementation`; `Production identical resume acceptance` |
| CPU-heavy work uses spawn, disjoint work, one persistent ready queue, and one worker ceiling | `Resource scheduling and guard contract`; `Cold/warm performance and scheduler acceptance` |
| Workers receive pure data and only the parent mutates durable run state | `Resource scheduling and guard contract`; `Cold/warm performance and scheduler acceptance` |
| Fiber hot loops avoid path, NIfTI, and transform locks and use point-byte partitions | `Shared physical preparation and configured-data parity`; `Cold/warm performance and scheduler acceptance` |
| Large payloads are written once and consumers use immutable views without axis duplication | `Shared physical preparation and configured-data parity`; `Cold/warm performance and scheduler acceptance` |
| Vectorized statistics and null fast paths preserve scalar parity without unused retained matrices | `Shared physical preparation and configured-data parity`; `Cold/warm performance and scheduler acceptance` |
| Formal, bootstrap, pPAM, and jitter RNG schedules are invariant to workers and scheduling | `Shared physical preparation and configured-data parity`; `Cold/warm performance and scheduler acceptance` |
| Resume re-evaluates dependency skips and accepts only provenance-safe overrides | `Resume and copied-cache implementation`; `Production identical resume acceptance`; `Corruption, fail-once recovery, and deletion-rebuild acceptance` |
| Managed RAM, solver admission, RSS, swap, local guard, and reporting cadence satisfy the resource contract | `Resource scheduling and guard contract`; `Cold/warm performance and scheduler acceptance` |
| Tau, Coverage, selected-reference overlap, support QC, and pPAM boundaries use their exact declared directions | `Boundary and computability policy`; `Frozen voxel and fiber source grids`; `Shared physical preparation and configured-data parity` |

The repository-owned plan-audit guard must require a one-to-one row count for
every still-open source-plan checkbox, preserve the exact set of open Step
numbers, reject duplicate mapping labels, and reject a mapping reference that
does not name an Evidence Matrix requirement. The other two source plans
currently have no open checkbox; opening one without extending this ledger
must therefore fail the same guard.

`test_task17_plan_audit.py` implements this contract. Its five focused tests
pass with warnings treated as errors: the 26 open
dual-frequency items mapped to 26 unique ledger rows, the ten open Step
numbers matched exactly, both other plans had no open checkbox, and every
backticked mapping reference named an existing evidence row or an allowed
status token. They also enforce the 24-row status/final-closure contract and
the repository-path closure described below. The new guard and the existing
bounded goal-acceptance suite then passed all 13 tests together under Conda
`leaddbs`.

After the current main branch was merged into
`task17-perf-injected-worker`, the isolated performance-matrix suite and the
new plan-audit guard passed all 40 tests together with warnings treated as
errors. The parser selects the table by its `Source-plan item` header, so the
separate detailed checklist table below remains evidence rather than being
miscounted as a second source mapping. The named Git-ignored allowlist resolved
from the primary checkout, while every other current-worktree reference
retained the strict missing-path check.

A 2026-07-25 structural replay found 24 unique ledger rows: 10 accepted,
two active, 12 pending, and no blocked row. The YAML-core and postprocess source
plans contain no unchecked implementation item. The dual-frequency source plan
contains 26 deliberately open items: the 10 production Step headings listed
above and 16 final performance-checklist clauses covered by the last mapping
row. No source-plan checkbox is orphaned behind an absent ledger gate, and no
duplicate ledger name can make one production requirement appear closed twice.
This is structure-only evidence; every active or pending row still requires
the terminal production evidence named in the matrix.

The final performance checklist expands to the following non-overlapping
evidence map:

| Final checklist clause | Required ledger evidence |
| --- | --- |
| One physical preparation before endpoint and scale fan-out | `Shared physical preparation and configured-data parity`; `Cold/warm performance and scheduler acceptance` |
| Distinct voxel and fiber bilateral formulas reused across scales | `Shared physical preparation and configured-data parity` |
| One logical connectome traversal with measured raw-boundary overlap and exact `Omega_max` | `Shared physical preparation and configured-data parity`; `Cold/warm performance and scheduler acceptance` |
| Layer-1 jitter schedule and exposure with Layer-2 endpoint statistics | `Independent spatial jitter computation`; `Cold/warm performance and scheduler acceptance` |
| Exact final-axis OSS equivalence before pPAM | `Independent OSS axis equivalence and pPAM` |
| Once-per-process target-cache verification without checksum rereads | `Cold/warm performance and scheduler acceptance`; `Resume and copied-cache implementation` |
| Stable OSS scientific identities and cache-first historical promotion | `Independent OSS axis equivalence and pPAM`; `Production identical resume acceptance` |
| Spawned CPU work, disjoint units, persistent ready queue, and one public worker ceiling | `Resource scheduling and guard contract`; `Cold/warm performance and scheduler acceptance` |
| Pure-data spawned commands, read-only shared artifacts, and parent-only mutation | `Resource scheduling and guard contract`; `Cold/warm performance and scheduler acceptance` |
| Path-free fiber hot loops and point-byte-balanced whole-fiber partitions | `Shared physical preparation and configured-data parity`; `Cold/warm performance and scheduler acceptance` |
| Single-write large payloads and immutable indexed views | `Shared physical preparation and configured-data parity`; `Cold/warm performance and scheduler acceptance` |
| Vectorized numerical parity without duplicate operators or unused retained matrices | `Shared physical preparation and configured-data parity`; `Cold/warm performance and scheduler acceptance` |
| Historical RNG schedules and worker-count invariance | `Shared physical preparation and configured-data parity`; `Cold/warm performance and scheduler acceptance`; `Production identical resume acceptance` |
| Dependency-skip reevaluation and scientific-identity-safe resource overrides | `Production identical resume acceptance`; `Independent OSS axis equivalence and pPAM`; `Cache-first combined jitter and OSS replay` |
| Managed-memory, task-tree RSS, swap, solver, local guard, and two-hour Codex boundaries | `Resource scheduling and guard contract`; `Cold/warm performance and scheduler acceptance` |
| Exact tau and Coverage boundaries, reference overlap, strict support QC, and pPAM `p(A) > 0.5` | `Boundary and computability policy`; `Shared physical preparation and configured-data parity`; `Independent OSS axis equivalence and pPAM` |

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

The completed parent's deterministic `configuration_resolved.yaml` sections
were serialized with the publication writer's exact sorted-YAML contract and
compared directly with both canonical resolved profiles. The direct-voxel
bytes matched at SHA-256
`d4f6cc2c99d01dcd56c85c5123dee02e655b22f127b26562bf05602c2d17ae03`;
the normative-fiber bytes matched at SHA-256
`06866f2dea707a97686e081442a37d9f61ec7e9d1708d88524c236f73910d228`.
Both artifact indexes contain those exact profile hashes and the common
study-base SHA-256
`3aa0d58a7373e186896b2fbfb5c0342d8425046bf9a5b07517b416d6a7def925`.
The current raw normative-fiber YAML differs from the parent copy only in the
OSS fitting-threshold comment, and the current workflow adds the nonscientific
retained-cache policy. Loading the current profiles still yields scientific
configuration SHA-256
`6d23bc0e9f30e697806d0847f238c1c8b09170673dc1ff0c29253808a5c401d5`,
which matches the completed parent and both model-set manifests.

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

The current resume implementation was re-inspected directly. `RunIdentity`
still records `code_identity`, configuration hashes, and the plan hash as
provenance, but `_validate_resume` does not use any of them as a reuse gate. It
requires the study JSON digest and the ordered source digests for the three
YAML inputs. The executor then restores only a task JSON whose status is
completed and whose full typed result decodes and validates; malformed,
incomplete, or missing results rerun with their affected descendants. Nine
focused resume and copied-cache cases plus four cleanup-policy cases passed.
One fixture changes the synthetic code identity while preserving JSON and YAML
inputs and proves that the completed result is restored without service
invocation. Failed or partial runs remain ineligible for cleanup, and the
production false cleanup policy returns before inspection or mutation.

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
A static three-plan path audit extracted 121 unique backticked repository-file
references with an implementation, configuration, test, or documentation
extension. All 120 references intended to remain at their stated paths exist.
The sole absent source path is
`my_helper/fiber/pipelines/run_configured_outcome_models.py`, which Task 15
explicitly requires moving out of the production pipeline. Its destination,
`my_helper/fiber/projects/stnsnr/legacy/run_configured_outcome_models.py`,
exists, the old production path is absent, and `git log --follow` reaches both
the legacy-isolation commit and the original configured-workflow commit.
The repository-owned plan-audit guard must repeat this extraction, reject any
additional missing path, require the legacy destination, and continue to
require the moved production entrypoint to remain absent. Its focused replay
found the exact 121-reference closure, the expected sole missing source, and
the existing legacy destination.
In a linked Git worktree, the explicitly Git-ignored frozen
`approved_task_allowlist.json` may resolve from the primary checkout; this
exception applies only to that named local acceptance fixture and cannot hide
any other missing source-plan path.

A fresh production-only scan of all 93 Python files below the generic
`dual_frequency` package found no project-name dispatch token and no import of
STNSNr, legacy, migration, or acceptance code. The import-isolation,
runtime-dependency-boundary, and generic goal-acceptance suites then passed all
12 tests under Conda `leaddbs` with warnings treated as errors. This confirms
both the static and executable boundary; references retained only in test
fixtures do not enter production imports.

The YAML, application CLI, production service, and run-cache cleanup suites
were also repeated through the repository's documented module-path launcher:
Numba was imported before the complete `my_helper/fiber/core` root was
prepended, matching the production CLI dependency boundary while preventing
the project `coverage` package from shadowing the third-party package during
test collection. All 35 tests and 15 subtests passed with warnings treated as
errors, including construction of the production default registry. A
dual-frequency-only bridge is not accepted for this suite because it omits the
sibling `seed_target_connectivity` package that the production CLI exposes
through the complete core root.

The injected spawned-worker fixture and public `run` operation are implemented
in the isolated worktree, but no production matrix manifest exists. Merge,
post-merge complete regression, and production execution therefore remain
open. The
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
passed. During the next permitted production inspection window, the isolated
package was exercised through the main checkout's exact frozen fixture files.
All five previously deferred reference-fiber, add-on-fiber, OSS, jitter, and
formal-summary cases passed, including 12 subtests, against their mounted
allowlisted artifacts. The two real study-base compatibility and drift tests
and the two-scale catalog/DAG smoke also passed. This closes every previously
identified environment-path case without copying or replacing its data.
The post-merge main-worktree complete regression remains mandatory.

The frozen formal postprocess request was also audited read-only. Its SHA-256 is
`144ad7a1e775c1bf01f5d99df285a87b31bae7075aa3692d714201f1953e6ab0`.
It names exactly the canonical direct-voxel and normative-fiber main and
final-in-sample publications, contains no `.runs` path, selects all available
scales, and requests paired-fit, voxel 2-D, and fiber 2-D components. The
configured output root remains absent until its production execution gate.

A production-code scan at the same checkpoint confirms that formal
postprocess, paired-fit, voxel-section, fiber-section, and 3-D example-input
resolution all read the actual selected tau and Coverage from each canonical
`final_model.json` and cross-check the paired summary. They contain no
modality-wide voxel-200, fiber-400, or Coverage-5 fallback. Those literals occur
only in synthetic test fixtures; the unrelated production literal 200 defines
a fit-curve grid or an electrode display length, not a scientific threshold.
Endpoints that reached a different fallback cell therefore retain their own
published parameters in every visual and statistical output.

The paired-inference contract was also replayed locally. Three backend tests
and six parameterized fit/publication cases passed with warnings treated as
errors. Each endpoint summary retains paired in-sample and LOOCV Spearman,
Pearson, nominal p, plus-one two-sided permutation p, finite-subject,
finite-prediction, finite-permutation, model-error, and baseline-error fields.
It reports standard `in_sample_r2` with `loocv_r2`, and the common-baseline
pair `in_sample_relative_r2` with `loocv_q2`. The unsupported
`in_sample_adjusted_r2` remains absent. Spearman, Pearson, standard-R2,
relative-R2/Q2, RMSE, and MAE optimism gaps are emitted only for matching
subject masks. Visualization reads these stored values rather than recomputing
or relabeling inference.

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

A later isolated replay collected and executed all 15
`test_task17_fault_acceptance.py` cases under Conda `leaddbs` with warnings
treated as errors. All 15 passed in 50.89 seconds. This confirms the frozen
fault-harness implementation before production planning; it does not replace
the marked production corruption, fail-once, copied-cache, or rebuild cases.

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
The focused CLI contract must invoke `main()` for `run`, prove that the exact
request and benchmark-root paths reach the resumable orchestrator, and verify
the successful JSON result rather than checking parser choices alone.
Five candidate-parity tests and 36 performance-harness tests pass in the
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

The latest read-only scope audit at reviewed head `8d2168dfe` again confirms
that baseline `f08658f0d` remains an ancestor. The closed range contains 43
commits and the same eight changed paths: the performance runner, its two
workflow integration files, two focused test files, the frozen benchmark
request, the implementation plan, and this acceptance ledger. The two commits
after `a368278a6` are documentation-only closure for the benchmark merge and
the frozen production fault-acceptance invocation. The request SHA-256 remains
`c9f4bca02361f7004adc383e95df69a40a5dbd31ca30e0acf64286073948e839`.
Both worktrees were clean. This is current merge-readiness evidence only; the
same ancestry, path, and digest closure must still be recomputed after the OSS
writer exits immediately before the fast-forward-only merge.

A subsequent read-only scope audit at reviewed head `eaaec7d8b` again confirms
that main head `f08658f0d` is an ancestor. The closed range contains 46 commits
and the same eight changed paths: two focused test files, two workflow files,
the performance runner, the frozen benchmark request, the implementation plan,
and this acceptance ledger. Both worktrees were clean, and the benchmark
request SHA-256 remained
`c9f4bca02361f7004adc383e95df69a40a5dbd31ca30e0acf64286073948e839`.
This is another pre-merge checkpoint only; the terminal audit after the OSS
writer exits remains authoritative.

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

A 2026-07-25 offline command-drift audit invoked `--help` through the locked
Conda `leaddbs` interpreter for the strict resource validator, extension-v2
validator, display-smoothing repair transaction, performance matrix harness,
fault-acceptance harness, unfiltered extension publisher, and formal
postprocess entry point. All seven entry points returned zero. Their current
interfaces retain the frozen run, segment, guard, RSS, source publication,
stage, Trash, benchmark, fault-root, and formal-output arguments plus the
required `publish-extension`, `stage`, `validate`, `promote`, `prepare`, `run`,
and `init` operations. This proves that the documented post-OSS command
sequence has not drifted at the CLI boundary; it does not substitute for
executing that sequence against terminal production artifacts.

The complete isolated dual-frequency test tree was collected read-only on
2026-07-25 through package-only Python-path links. The bridge exposes exactly
`dual_frequency` and `seed_target_connectivity` from the isolated worktree,
while the worktree root exposes `my_helper`; it does not expose the entire
`my_helper/fiber/core` directory. All 764 tests were discovered without an
import or collection error. The same bridge passes all seven synthetic
end-to-end tests, including four-family main execution, selective resume,
independent jitter and OSS extensions, missing-parent rebuild, and guarded
cleanup.

The complete isolated tree was later executed natively in one invocation with
warnings treated as errors after the interrupted OSS segment had released its
process tree. The three Git-ignored local fixtures were materialized through
same-device hard links to the authoritative primary-checkout allowlist, frozen
manifest, and MNI template segmask. This preserves the isolated worktree paths
without copying payload bytes or changing tracked content. The invocation
passed 773 tests and 329 subtests with no failure or skip, and both worktrees
remained clean. This replaces the earlier split-path result as the authoritative
pre-merge regression. It still does not substitute for the required single
all-green post-merge regression after the independent OSS lineage is terminal.

A read-only scope audit after that regression confirmed that main head
`f08658f0d` remains an ancestor of the isolated branch. Before this
documentation checkpoint, the closed range contained 48 commits; after this
checkpoint commit it contains 49. The range still changes exactly eight paths:
two focused tests, two workflow files, the performance runner, the frozen
benchmark request, the implementation plan, and this acceptance ledger. The
benchmark request SHA-256 remains
`c9f4bca02361f7004adc383e95df69a40a5dbd31ca30e0acf64286073948e839`,
and both worktrees were clean. The terminal pre-merge audit must still
recompute all four facts after the OSS writer exits.

The subsequent no-run-store scene repair adds only
`viz/scene_example_inputs.py` and its visualization test module to that
prospective merge closure. After committing the repair and this checkpoint,
the range contains 50 commits and changes ten paths. This scope increase
enforces an existing public-only contract and does not alter a scientific
model, published result, cache identity, resume identity, or active OSS
execution. The terminal audit must use this ten-path closure as its expected
upper bound unless a later documented repair is required.

A later documentation-only merge synchronized main-head commits
`af87efdc5` and `2d98bb58f` into the isolated branch without merging isolated
implementation into the production checkout. The synchronization merge head
was `f2fd325d7`; main head `2d98bb58f` is an ancestor of that merge and the
subsequent documentation checkpoint, so the required eventual main-checkout
operation remains fast-forward-only. The post-merge range contained 51 commits
before this checkpoint and contains 52 commits after it, with the same ten
changed paths. The benchmark request
SHA-256 remains
`c9f4bca02361f7004adc383e95df69a40a5dbd31ca30e0acf64286073948e839`.
Both worktrees were clean after the merge. This is a pre-terminal checkpoint;
all ancestry, count, path, digest, and cleanliness evidence must still be
recomputed after the OSS process exits.

A second documentation-only synchronization incorporated main commit
`42815ad93`, which replaces the prematurely hard-coded resource command with
terminal-segment-driven selection between the strict and pre-instrumentation
validators. Main is again an ancestor of the isolated branch. The range
contains 53 commits before this checkpoint and 54 after it, while retaining
the same ten changed paths and benchmark-request SHA-256. No isolated
implementation has entered the production checkout.

A current read-only scope audit after synchronizing main
`c1d63094cfe7ab385d8a13091faecd56bf3edbb0` confirms that it remains an
ancestor of reviewed branch head
`fc0202bb4effb0c348e7143ca127ff6aec28c601`. Before this documentation
checkpoint, the branch has 71 commits not present on main and changes exactly
nine paths: the performance-matrix test, two worker integration files, the
performance runner, two visualization input/test files, the frozen benchmark
request, the implementation plan, and this ledger. The earlier
`test_executor.py` path is no longer branch-unique because its isolated-memory
fixture is already present on current main. The request SHA-256 remains
`c9f4bca02361f7004adc383e95df69a40a5dbd31ca30e0acf64286073948e839`,
and both worktrees are clean. The terminal pre-merge audit must still repeat
the ancestry, exact changed-path closure, request digest, and cleanliness after
the OSS writer exits.

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

The complete current main-worktree dual-frequency and visualization regression
was repeated on 2026-07-26 under Conda `leaddbs` with warnings treated as
errors. Numba was preloaded before adding the complete core root, so the project
`coverage` package could not shadow the third-party package. The accepted
zero-skip repeat passed all 809 tests and 329 subtests in 136.67 seconds,
including the endpoint-specific tau/Coverage resolver fixture, both run-store
scene-provenance rejections, cross-endpoint physical pPAM sharing, and
outcome-specific observed-workspace identity. The run used temporary fixtures,
did not authorize an expensive producer, and did not write any production run
or publication root. This is complete static and synthetic regression
evidence; it does not replace the remaining production executions and
validators.

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
