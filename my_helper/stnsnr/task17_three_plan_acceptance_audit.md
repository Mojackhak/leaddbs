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

The repository-owned plan-audit guard must retain exactly 25 uniquely named
Evidence Matrix rows, reject an unknown status or malformed table row, and
require the `Final three-plan requirement audit` row to remain non-accepted
while any other row is non-accepted. Only a completely accepted matrix may
mark that final row accepted.

## Evidence Matrix

| Requirement | Status | Current authoritative evidence | Remaining acceptance action |
| --- | --- | --- | --- |
| Production YAML drives all four model families | ACCEPTED | `config/four_model_v1/workflow.yaml` references the production direct-voxel and normative-fiber profiles. The repository-owned test parses all three YAML documents and asserts the model references, ordered grids, pre-specified cells, 12-subject floors, all three fold minima, and retained-cache policy. Run and scientific configuration identities derive from normalized typed values; a focused fixture proves typed-equivalent scalar serialization preserves both identities. Raw YAML SHA-256 is historical provenance only and is not an admission, cache, resume, publication, or rerun gate. A broader current-checkout replay passes 66 tests and 104 subtests across configuration, application CLI, catalog, planner, formal in-sample, run-cache cleanup, and goal acceptance. The historical `model.yaml` is explicitly outside the current loader and lineage. The current normative-fiber source differs from the completed parent input only in the corrected `p(A) > 0.5` comment and parses to the same document. The completed run scientific-configuration identity matches its resolved snapshot and both canonical model manifests. | Reopen the parsed production profiles and normalized identities during final audit. |
| Frozen voxel and fiber source grids | ACCEPTED | Direct voxel uses tau 150, 180, 200, 220, 250, and 300 with pre-specified 200. Normative fiber uses tau 200, 350, 400, 450, 600, and 800 with pre-specified 400. Both use Coverage 5, 6, 7, 8, 10, and 12. The direct-voxel and normative-fiber sections of the completed parent `configuration_resolved.yaml` exactly match the parsed canonical `resolved_direct_voxel_model.yaml` and `resolved_normative_fiber_model.yaml`. Each published resolved file matches its own manifest SHA-256, and both published study snapshots are byte-identical to the parent input snapshot. The post-smoothing full-payload validator reopened both resolved files and study snapshots and reproduced all four declared SHA bindings. Raw source YAML and resolved publication YAML are intentionally different serializations and are not required to be byte-identical. | Reopen the retained validation report during final publication audit. |
| Boundary and computability policy | ACCEPTED | Current runtime and formal kernels include equality for both scientific boundaries: voxel and fiber exposure at tau is suprathreshold, and a feature with subject Coverage at the requested minimum is retained. The 12-subject floor remains active, and every declared connectome requires at least one fold candidate fiber. A 2026-07-27 focused replay passed five tests with warnings treated as errors, covering direct-voxel boundary parity, normative-fiber boundary parity, inclusive fiber overlap, inclusive minimum-grid `Omega_max`, and the production profile. | Repeat the repository-owned final static audit after all production children terminate. |
| Main four-family formal run | ACCEPTED | Parent run `task17-main-v8-tau-grid-formal-20260717` is terminal with `final_status` `completed`. All 1512 persisted task documents have unique task IDs and terminal `completed` status; no task is failed, skipped, or running. Both execution segments are terminal `finished` spawn-process segments with 14 workers. The run artifact index has 7468 unique artifact IDs and URIs. Its 11388 task-result artifact references reduce to the same 7468 unique URI/SHA-256 pairs, with no task artifact outside the index and no indexed artifact outside the task closure. The 224 unique final decisions split into 112 `realized_primary` records and 112 `no_final_model` sensitive-connectome records. Every realized decision maps to exactly one completed realization task, its decoded `FinalSelectionRecord`, its final-record ID, final-key ID, and exact causal-task closure. The realization closure contains 28 endpoints in each of reference voxel, add-on voxel, reference fiber, and add-on fiber. The no-final closure contains 56 reference and 56 add-on sensitive-connectome endpoints, has no model IDs or realization task, and maps exactly to the two sensitive-connectome evaluation services. The canonical publications contain 56 direct-voxel and 56 normative-fiber `final_model.json` records. Every public record is indexed as completed and matches the decoded parent final record in role, scale, branch, tau, Coverage, status, and final-record ID; all declared source, feature-axis, and artifact links exist and are indexed. Commit `dba11ec7d` adds the full run-artifact validator. Five focused tests pass; complete discovery passes 777 tests and 329 subtests. The production validator reread all 73406341913 payload bytes, matched all 7468 payload SHA-256 values, all 11388 task references, and all 1512 task documents. The indexed-payload closure SHA-256 is `792433fa43996dbd4c1015c79d77f663530599feee2eb8433ad563cc8850e6c8`; the task-document closure SHA-256 is `c38d0f12610fc1a2f4ae48e8427d352cf40f0ea90b4e8d12e14a30e19c478e50`. The atomic report SHA-256 is `e72b4b9b292faabf3e5c571b8950acf74fc9d521bc3784127890cb12c753863c`, and a second complete 73.4-GB invocation preserved its bytes and mtime. | Reopen the retained structural and full-payload reports during the final three-plan audit. |
| Canonical main model-set publication | ACCEPTED | Completed direct-voxel and normative-fiber model-set publications are the only allowed public parents, and postprocess preflight resolves them without a run-store fallback. Commit `3c45d57b7` adds the repository-owned full-payload validator. Five focused tests pass; complete dual-frequency discovery passes 772 tests and 329 subtests with warnings treated as errors. After display-smoothing promotion, the production validator hashed all 5690 indexed payloads and 1062720468 bytes, verified both terminal manifests, resolved profiles, study snapshots, root identities, 28-scale closures, and exactly 56 final models per domain. Direct-voxel and normative-fiber indexed-payload closure SHA-256 values are `cc48441d4109648c6e82c752f202763754c414460c6957ce689db932143a86db` and `a25d1936fc699ca4ea303ff87daa22bbe9775995fd350b330badd6acf901e3e6`. The atomic report SHA-256 is `8cf595681415820f5224fb7aeebe5023a702046cde3f0efefa485c3a559d782f`; a second full invocation preserved its bytes and mtime. | Reopen the retained report during final three-plan audit and require downstream publications to preserve these parent-manifest bindings. |
| Final in-sample inference and publication | ACCEPTED | Both model-set domains contain the canonical final-in-sample v2 extension. A fresh public-only closure audit found 56 direct-voxel and 56 normative-fiber results with 112 globally unique endpoint IDs. Every result has the complete paired in-sample and LOOCV statistic set, matching subject masks and finite counts, 10000 requested and finite permutations on both sides, and a final-model ID, selected tau, and selected Coverage matching its indexed canonical final-model record. A second fresh replay validated all 112 canonical summaries against the complete 43-field contract: 56 summaries contain 16 finite subjects and 56 contain 13, all in-sample and LOOCV total and finite counts agree, all subject-mask and prediction-finiteness flags pass, all six optimism gaps satisfy the declared arithmetic contract, and no summary publishes `in_sample_adjusted_r2`. Both parent-manifest bindings are current, all four publication manifests are terminal, all indexed rows are completed, and the paired metadata contains no run-store or runtime-work path. The audit found no mismatch. | Confirm that the terminal paired-fit plots consume this exact 112-endpoint closure without substituting a run-store source. |
| Shared physical preparation and configured-data parity | ACCEPTED | Shared geometry, one-time physical exposure, inclusive fiber overlap, exact minimum-grid `Omega_max`, side-specific fiber peak reduction, cache-backed subject/feature views, copied-cache reuse, and bounded parity fixtures pass. A fresh provider/jitter/activation-universe/OSS-axis/toolchain replay passed 106 tests and 26 subtests with warnings treated as errors. The frozen configured-data replay started from absent dedicated cache and run roots as `task17-parity-v1-post-refactor-20260722`, used scale `adl`, all four model families, all three connectomes, the observed cutoff, one worker, no expensive-producer authorization, and the mount-only guard, and completed all 46 tasks with 46 task-local markers, zero failed tasks, a root completion marker, and a terminal manifest. A 14-worker identical resume returned successfully in about one second without starting scientific work. All 92 task documents and completion markers retained metadata-closure SHA-256 `9786228fc9eed7a43e95f29fb6eedb731aa386e83a9a7e08b0716cb50fd4ba46`; all 224 dedicated-cache files retained metadata-closure SHA-256 `cf6c77cd163c5c54fa4e2d473ec3bddaa74787c6b1e40e8db91f972196abe08a`. The deterministic report `task17-physical-parity-replay-v1.json` validates three physical voxel roles, nine physical fiber role/connectome rows, two prepared voxel exposures, and six prepared `Omega_max` exposures. A second validation preserved report bytes and nanosecond mtime at SHA-256 `83e822f31947567c0af06145ccd4d2f19bbf665b154e62de397f167d537d913f`. | Reopen the terminal run, dedicated-cache closure, identical-resume evidence, and deterministic parity report during the final three-plan audit. |
| Cold/warm performance and scheduler acceptance | PENDING | Persistent spawned scheduling, global CPU/I/O/solver ledgers, parent-only state mutation, process-local cache verification, vectorized kernels, and deterministic RNG boundaries pass static tests. The repository-owned cumulative-CPU probe, five-second scheduler-window publication, exact 72-row matrix validator, source-evidence binding, deterministic report, worker/default decision, observational RSS/swap reporting, and utilization-window gate are implemented. Every executed row binds the exact probe SHA; I/O classification is closed to compute-bound or storage-limited; and a non-default worker promotion requires matched compute-bound rows that are all faster than workers 3 while retaining both wall times in the report. All 28 counters derive from immutable task fragments, configured parity, artifact/static audit, terminal segment fields, and a SHA-bound source/scratch byte ledger; caller-entered counter values are rejected. Decision 45 supersedes the earlier managed-memory ceiling, reserve, task-tree RSS, and zero-swap-growth acceptance predicates. The benchmark harness validates the minimal operator request, accepted parent and independent OSS binding, exact parent input paths, normalized run/scientific configuration and task-plan identities, maximum-burden scientific requests, measured/imported DAG task slices, protected-root separation, optional solver authorization, and the exact 72-row key closure. Request formatting and raw YAML/JSON source bytes do not enter row identity. Its runner-readiness and measurement-start protocol binds the row, child PID, slice-plan identity, imported task closures, byte-ledger path, and byte-ledger SHA before selected work may start. Stable row identities, immutable row contracts, monotonic attempt directories, terminal evidence SHAs, changed-contract rejection, and changed-evidence rejection are implemented. `prepare` writes the resolved plan, all 72 contracts, and only then the complete contract marker; read-only validation rejects missing, extra, changed, or path-aliased contract roots. The sole unauthorized real-cold solver branch publishes an immutable false-authorization preflight and terminal `not_run`; other rows cannot use that status. Every statistical slice includes its selected endpoint's base physical producer so a cold row can create the row-local shared-cache closure and a warm row can prove a cache hit without copying a selected-task result. Each resolved slice persists a closed executable plan with imported direct parents converted to checkpoint-only roots while preserving every selected task's original service, parameters, gates, and internal dependencies. pPAM injected, real-cache-hit, and real-solver rows have separate slice identities and all measure the OSS Omega-only group; the accepted OSS outcome is an injected/reference authority or stable cache seed, never a copied selected-task result. `prepare` decodes the exact two terminal OSS group records, resolves their referenced Omega rows from the configured shared cache, verifies stable scientific keys and exact final-axis subsetting, and binds every cache-manifest SHA plus a canonical closure SHA into the resolved plan. The benchmark-only injected toolchain reconstructs exact ten-sample activation counts from those accepted rows and rejects requests outside that closure. Ordinary and injected warm-seed production, child/probe launch, terminal row evidence, identical row resume, normalized numerical identity, scheduler-derived I/O classification, 72-row matrix publication, strict acceptance invocation, public `run`, and read-only terminal validation are implemented. Five candidate-parity tests pass, and a fresh complete performance-harness replay passes 36 tests with warnings treated as errors. After synchronizing Decision 41 and the final OSS cache-promotion audit from main at merge `ac4e36b5c`, the combined performance, byte-ledger, counter, probe, resource-guard, and plan-audit set passes 91 tests with warnings treated as errors. Merge `b8cf39670` integrated the reviewed implementation and paired-fit postprocess closure. The current Decision 45 and minimal-resume worktree passes all 803 dual-frequency tests plus 326 subtests and all 55 visualization tests with warnings treated as errors. A later current-worktree replay of candidate parity, performance acceptance, byte ledger, counters, performance matrix, CPU probe, pre-instrumentation resources, terminal resource acceptance, mount guard, and the fault harness passes 147 tests plus 2 subtests with warnings treated as errors. The benchmark request now binds the replacement Omega-max-only OSS lineage and contains no RSS ceiling; it remains intentionally non-runnable until that lineage is terminal. No production matrix has run. | After independent OSS terminates, execute the workers 1, 3, 6, and 12 cold/warm matrix without substituting skipped or default-zero rows. Retain every terminal counter sidecar, exact-resume proof, deterministic matrix, and acceptance report. |
| Corruption, fail-once recovery, and deletion-rebuild acceptance | PENDING | Static cache, resume, checkpoint, and rebuild fixtures reject payload, shard, axis, and result corruption and selectively rerun affected descendants. The repository-owned marker-bound isolated harness implements complete parent/publication SHA closure, exact copied-cache marker closure, path-safe unique case IDs, absolute and relative command confinement, quarantine-and-restore corruption, immutable and task-bound pre-resume fail-once evidence, protected-artifact checks, distinct-lineage rebuild, unauthorized copied-cache replay, exact or NPY-tolerant one-shot comparison, contract-bound terminal case reuse, and read-only validation that cannot repair a changed report. Fifteen focused harness tests pass with warnings treated as errors. A current complete collect-only pass discovers 807 tests without import or collection failure; it is runner-readiness evidence and not a claim that all 807 tests executed. A 2026-07-26 scope review confirmed that the immutable plan plus harness `init`, `run`, and read-only `validate` operations are the approved repository-owned boundary; a second plan-builder entrypoint is not required. After Decisions 49 and 50, the combined cache, cleanup, jitter, OSS equivalence, fault harness, resource acceptance, and mount-guard replay passes 118 tests and 22 subtests with warnings treated as errors. The production-scale sequence has not run. | After terminal OSS and combined authorities exist, prepare and review the exact six-case production plan. In its marked isolated root, execute all three corruption classes, fail-once recovery, missing-parent rebuild, copied-cache replay, and one-shot comparisons; retain and revalidate the terminal deterministic report. |
| Independent spatial jitter computation | ACCEPTED | `task17-jitter-v8-support-preserving-formal-20260719` completed its support-preserving block and endpoint closure with no terminal failure. Jitter compilation, selective block resume, cache-first dispatch, and extension publication boundaries pass 25 focused tests with temporary fixtures. | Reopen the completed child manifest, block closure, endpoint closure, artifact index, and parent binding during final audit. |
| Canonical independent jitter-v2 publication | ACCEPTED | Commit `f20b7754e` makes terminal extension-v2 artifact replay index each immutable metadata sidecar and adds an exact regular-file closure regression. Focused publication coverage passed 22 tests; the complete main dual-frequency suite passed 767 tests and 329 subtests with warnings treated as errors. The four invalid index/manifest commit files were archived with their original SHA-256 values under `/Volumes/VAL/.Trashes/501/task17-jitter-v8-extension-v2-index-repair-20260726`; no scientific payload or metadata sidecar moved. Unfiltered replay rebuilt each domain as 226 indexed files for 56 results. The direct-voxel and normative-fiber payload closures retained their pre-repair SHA-256 values `16c42c2d513b39205009732f56030c39784350caac75de4fb2ae4b829cae4e25` and `75a2f827004b7110b1f5ddc8187547c5a85e69188645142b3ce84bdd3d25d5d4`. A second replay preserved both index and manifest bytes and mtimes. The repository validator passed both roots twice and atomically retained report SHA-256 `f5491c15fd2d07b81a1f8b7910d345e63b45d61f59eb929ce597bf3073d95040`. A fresh read-only replay on 2026-07-27 reopened the source child root marker and both canonical roots, validated 56 results and 226 relative artifact-index rows in each domain, matched parent manifests, and returned terminal `validated` status without writing a report. The current direct-voxel index and extension-manifest SHA-256 values are `9d582fdf3ff544ede10d308c5d332c3c0b37f13b7f1d6b688941cfeda24092c5` and `2da949fce0d5e57e92f1e274365582d75193ee48690f00447b879a77a4b95ba6`; the normative-fiber values are `a97868475fc35f7c62b4dae387ae2689ceb2e3538034d2887e44af00293c91df` and `2bd6b80c478d9f9e13075235f976f4202f5c63110beb6d93c0f328206e7b2852`. | Reopen the two roots and the retained validator report during the final three-plan audit; do not modify the accepted jitter-v2 publication. |
| Independent OSS Omega-max preparation and pPAM | ACCEPTED | The superseded paired lineage retained 34 reference and 11 add-on stable pass decisions before `segment_0021` was stopped. All 45 pairs have maximum probability difference `0`, state mismatch count `0`, and activation-count mismatch count `0`; they provide 45 validated stable `Omega_max` rows. Decision 43 implementation emits `OSSSharedOmegaGroupRecord`, produces only missing Omega-max rows, validates exact structural subsetting and stable closure, supports copied-cache resume and corruption rejection, and forces downstream pPAM cache-only. The replacement lineage `task17-oss-v2-omega-only-formal-20260726` is terminal. Its two completed `OSSSharedOmegaGroupRecord` tasks contain exactly 34 reference and 26 add-on Omega row IDs and 28 endpoints per group. All 590 planned tasks are completed with 590 task-local completion markers and no failed, skipped, or running task. The completed service closure contains 56 observed workspaces, 56 schedules, 224 permutation blocks, and 56 pPAM aggregates over 56 unique endpoints. The run manifest, root `complete.json`, extension results, and final decisions are terminal; the JSON and CSV artifact indexes each contain 2802 rows. `segment_0013` used 14 workers, one solver token, and the mount-only guard. The guard ended with `runner_exit`, recorded no stop event, and observed a maximum task-tree RSS of 46455406592 bytes; RAM and swap remained descriptive only. The immutable v8 parent predates the cleanup field, so the sensitivity child records its historical schema default; cleanup is not called by sensitivity or extension publication, failed or partial runs are never eligible, and shared cache remains outside that boundary. Current repository workflow policy is explicitly `false`, and checkpoint/cache/runtime work remains retained. Historical final rows and decisions remain immutable evidence only. The explicit marker migration found all 590 task markers and the root marker already present and created nothing. Exact resume without expensive authorization returned success before worker startup. Across migration and resume, all 17416 non-runtime files retained the same path, size, and nanosecond-mtime closure SHA-256 `0e0c7efd79d1790cd10dd710a9705f626b98563dba5a3c56ad4852bd85ea207c`. | Reopen the terminal manifests, group records, pPAM closure, guard CSV, and identical-resume evidence during final audit. |
| Canonical independent OSS-v2 publication | ACCEPTED | Self-contained extension-v2 publisher and validator fixtures pass. Decision 58 makes the source run-root `complete.json` path a required terminal publication and independent-validation gate without parsing or hashing the marker. The complete publisher and validator modules pass 24 focused tests with warnings treated as errors, including both missing-marker regressions. The terminal source child has 590 completed tasks, 56 terminal pPAM results, and a root completion marker. Two unfiltered production replays published the canonical normative-fiber extension `task17-oss-v2-omega-only-formal-20260726-v2`; direct voxel correctly has no OSS result. The publication contains 56 results, 2130 indexed artifacts, and 33523719 artifact bytes. Its artifact-index SHA-256 is `7a90643e1fd1af09a42bfa3658081dc8c0b891a82419faa072652cd4c8b3eca7`, its extension-manifest SHA-256 is `1823d4286801b5a3e68c004b98fc9541ae3265e6af6b5c25076f5daa6214ef4c`, and its parent publication manifest SHA-256 is `c03ee78f4d725423a98fa52ee2e6effbed4829cf350901a33e84286099228c7f`. The second replay preserved the complete 2132-file path, size, and nanosecond-mtime closure SHA-256 `c4e0b4305deb2d25787212b4a466aadda068cc6c5634c5eae2142d334a8b3264`. The independent validator returned `validated` after both replays and found no run-store path. | Reopen the source marker, canonical root, parent binding, and retained SHA values during final audit. |
| Cache-first combined jitter and OSS replay | ACCEPTED | Compiler, executor, physical jitter, OSS decision, and activation-provider fixtures prove cache-first behavior and fail before a producer call on a miss without authorization. A fresh 2026-07-26 replay passed ten focused tests with warnings treated as errors, including copied physical-jitter and OSS caches, historical accepted-OSS promotion, corrupt or missing rows, combined-plan compilation, and provider-level cache hit and unauthorized miss boundaries. After the minimal resume and RAM-control cleanup, 12 focused cache-first, copied-cache, corruption, historical-promotion, combined-compilation, and unauthorized-miss tests passed again. The production combined child `task17-combined-v1-inclusive-formal-20260719` started from an absent run root with analyses `jitter,oss`, 14 workers, no `--resume`, and no expensive-producer authorization. Its complete frozen plan contains 1194 tasks. All 1194 tasks completed with task-local markers, no failed or skipped task, a root completion marker, and a terminal completed manifest. The closure contains 240 physical jitter blocks, 112 jitter endpoints, two cache-reused Omega groups with exact 34-reference and 26-add-on row closures, 56 observed pPAM workspaces, 56 schedules, 224 permutation blocks, and 56 aggregates. It published 168 extension results and 112 final decisions without an expensive-producer authorization failure. | Reopen the terminal plan, both group records, complete service closure, root marker, and manifest during final audit. |
| Canonical combined-v2 publication | ACCEPTED | Publisher and validator fixtures cover both public domains. Two unfiltered production replays published `task17-combined-v1-inclusive-formal-20260719-v2` under both canonical domains. Direct voxel contains 56 jitter results, 226 indexed artifacts, and 92253150 artifact bytes; its artifact-index and manifest SHA-256 values are `91be210bedbfb459a8fdfd21a5de2df9751a00475739c68b3dc8ab2a4e601e33` and `8f4e8d7508709a9cf84c7353ee9389771fda62e37ce3253b94444b77bb5687ab`. Normative fiber contains 112 jitter-plus-OSS results, 2356 indexed artifacts, and 174185626 artifact bytes; its artifact-index and manifest SHA-256 values are `338339ec78d71d3a3f96b89153c50a1d8925cbbc5e39fadd587685fc9b451bd2` and `36bdae4e3e48684c90f565efc9aa399360121f10b81fcfd9a1254d65484a3779`. Both bind source-run manifest SHA-256 `0873acab460f60edada5b61be03d29895841c1acae2a7271de03fb8d1529beea` and the accepted parent manifests. The second replay preserved all 2586 publication files with path, size, and nanosecond-mtime closure SHA-256 `89251b59b5f559f79883b9b8a9136001c92dc4243952aa90e2a150a4fc1570b6`. The independent validator returned `validated` for both roots after both replays. | Reopen both roots, source and parent bindings, retained SHA values, and exact scope during final audit. |
| Resume and copied-cache implementation | ACCEPTED | Decision 44 separates admission from resume. Admission parses the declared study JSON and three YAML profiles and validates required fields before creating a run. Task restoration checks only the deterministic task-state path and `tasks/<task_id>/complete.json`; a present pair is restored, while an absent marker makes only that task eligible to run. The run-root `complete.json` is written only after successful finalization, repository and input hashes do not gate RunStore reuse, and malformed marked state is an explicit error. `--force` replaces the same requested path only after moving its prior untracked run root to the operating-system Trash; archival failure leaves the old root in place. Both public `run` and `sensitivity` commands expose that authority and reject combining it with `--resume`; sensitivity delegates to the shared RunStore path and adds no configuration field. Decision 46 removes the pre-RunStore sensitivity hashes and all resume-time metadata repair. The structural mapper now checks only portable URI syntax and root containment; it does not require artifact existence, compare repeated metadata, or read array headers before task restoration. Missing artifacts fail only an incomplete consumer task. Decision 49 makes an existing sensitivity child's persisted task graph authoritative for that exact child path, so resume does not reload parent sensitivity bases or require a later Omega descriptor merely to recover the graph. The fixed parent seed-task JSON contributes only the causal task-ID whitelist required by reporting. Run-root manifest admission uses one shared JSON-object parser. The workflow and performance harness share one typed task-plan decoder that enforces required fields and types while ignoring unrelated additional fields. Focused regressions prove selective main resume, malformed manifest rejection, exact sensitivity-child resume after historical metadata drift, unchanged checkpoint-root files, no input-bundle repair during resume, zero service calls when a completed child is restored after referenced parent runtime files are deleted, and exactly one service call after one incomplete child marker is removed while parent checkpoint loading is prohibited. A 2026-07-27 current-contract replay passed six focused tests covering run-marker finalization, missing task-marker rerun, restoration after scratch cleanup, terminal early return, missing parent artifact tolerance, and one-task sensitivity replay. The CLI, application service, executor, and synthetic extension replay passes 65 tests and 13 subtests after the sensitivity-force addition. The complete executor module, both CLI force cases, and plan audit pass 50 tests plus eight subtests after Decision 55. The latest relevant planner, application, checkpoint, synthetic end-to-end, performance-matrix, and plan-audit replay passes 95 tests and 90 subtests with warnings treated as errors; the prior complete dual-frequency suite passes 803 tests and 326 subtests. A consolidated replay of every modified dual-frequency test module passes 220 tests plus 25 subtests with warnings treated as errors, proving that the minimal-resume, Omega-only, RAM-removal, and acceptance changes coexist without test-order dependence. | Reopen the implementation and evidence during final audit; production identical-resume evidence remains tracked separately. |
| Production identical resume acceptance | ACCEPTED | Decision 48 repaired the analysis-local checkpoint boundary before production replay: pure jitter no longer requires an OSS-only `Omega_max` descriptor. Decision 49 additionally permits an exact sensitivity child to resume from its own persisted task graph without rewriting the parent. The checked-in migration created the formerly missing markers for the main and jitter lineages; later runs already contained their required markers. Exact resume returned success for main, jitter, independent OSS, and combined without starting a worker or rewriting non-runtime state. Main preserved 18983 files, jitter preserved 2651 files, and independent OSS preserved 17416 files with closure SHA-256 `0e0c7efd79d1790cd10dd710a9705f626b98563dba5a3c56ad4852bd85ea207c`. The terminal combined child returned success in about one second without expensive authorization and preserved all 18608 non-AppleDouble files with identical path, size, and nanosecond-mtime closure SHA-256 `e2dc942edbc4905c474747d3ed9dbbe5488cc69e6a1229ce505e4f23f8981183`. Decision 71 keeps completion markers append-only within a run root, and force replaces the whole root through Trash. | Reopen the four terminal roots and retained closure evidence during final audit. |
| Resource scheduling and guard contract | ACCEPTED | Decision 45 removes the 48-GiB authorized-producer admission charge, the additional reserve predicate, the task-tree RSS stop, and the zero-swap-growth stop. The live scheduler enforces only the 14-worker ceiling, connectome-I/O tokens, one solver token, dependencies, and cache or producer authorization. RAM and swap remain observational telemetry and cannot delay, fail, or terminate a task. The local guard retains runner-lifecycle and pinned VAL mount-generation checks only. Focused guard and strict-resource suites pass 39 tests, and broader executor and sensitivity suites cover high RSS, swap growth, unavailable telemetry, mount loss, same-path remount, continuity loss, and cache-only scheduling. The terminal independent OSS segment ran with 14 workers and one solver token; its guard recorded only samples plus `runner_exit`, no stop event, and peak task-tree RSS 46455406592 bytes. The terminal combined segment also ran with 14 workers and a mount-only guard; its 347 samples ended with one `runner_exit`, no stop event, peak task-tree RSS 9655926784 bytes, and peak sampled task-tree CPU 1360.7 percent. Neither run used RAM admission, RSS termination, or swap-growth termination. | Reopen both guard CSV files, terminal manifests, and scheduler settings during final audit. |
| OSS producer source identity | ACCEPTED | Decision 51 classifies the per-row before-and-after repository implementation hash as duplicate and speculative. The stable scientific key already excludes repository identity, while explicit input and output validations remain local to the row. The source-tree attestation call path is removed. A regression changes a repository file during fake row production and proves that the row still completes without an implementation attestation. The focused OSS toolchain, backend, cache, checkpoint, and synthetic suite passes 107 tests and 23 subtests with warnings treated as errors. The complete dual-frequency suite passes 806 tests and 326 subtests with warnings treated as errors. Production resume restored all 393 existing completion markers, reused all completed reference and add-on rows, and advanced the add-on stable Omega closure from 14 to 15 rows before the user-requested pause. The same lineage resumed again as `segment_0009` without recreating a child. | Reopen the implementation and production segment evidence during final audit; no source-identity gate remains. |
| Display smoothing v2 publication | ACCEPTED | With the OSS process tree absent, the repository validator reopened `/private/tmp/task17-display-smoothing-v2-stage.zAofAX` against canonical raw support and accepted 112 targets, 108 changed NIfTIs, and repair-manifest SHA-256 `dff3ab60616b2bd9d77075bc6781f6ef928db666f1052ac31d5f02f4088f6b5c`. The repository promotion transaction archived every replaced v1 file under `/Volumes/VAL/.Trashes/501/task17-display-smoothing-v1-20260723`, installed all payload and metadata replacements atomically, restored the completed model manifest byte-identically, and committed candidate artifact-index SHA-256 `9ea5003edcd97242d79d3e6cfbf92b770ab157cd1c54c21fe7d963b897331f9c`. Post-promotion validation passed the canonical root. An identical second promotion preserved the index, model manifest, and transaction SHA-256 values; the transaction SHA-256 is `b718060bb832e5c28a1d002cbff80c7380099413c70390fbb8e6a9e9fae52ae8`. | Reopen the canonical root and Trash transaction during final audit, and require formal postprocess to consume these promoted v2 derivatives. |
| Formal paired-fit, voxel 2-D, and fiber 2-D output | PENDING | The durable request structurally resolves 28 scales, 112 endpoints, canonical public inputs, and all three batch components. Its repository-owned static guard parses the request once and binds the consumed semantic fields: four canonical publication aliases and manifests, `all_available` scope, ordered three-component closure, output root, resources, and absence of run-store paths. Raw request bytes are not an acceptance or resume gate. A nondefault-cell fixture proves that the endpoint resolver preserves voxel tau 180 with Coverage 8 and fiber tau 600 with Coverage 10 instead of using modality-wide defaults. After display-smoothing v2 promotion, the real public-only `--validate-only` preflight passed again with four publications, 28 scales, 112 endpoints, `paired_fit`, `voxel_2d`, and `fiber_2d`, the accepted anatomy and masks, the 1.7-million-fiber formal connectome, all 18 target definitions, and PDF/PNG tooling. It created no formal output root. The same preflight was repeated after the minimal-resume and RAM-control cleanup and again returned `status: valid`, four publications, 28 scales, 112 endpoints, and the exact three-component closure. A fresh 2026-07-28 invocation returned the same closure from the current uncommitted checkout, independently reopened all four publications and spatial resources, and confirmed that the formal output root still does not exist after `--validate-only`. Paired-fit schema v2 fails before rendering unless all 43 paired metrics, both baseline-prediction columns, complete subject and permutation counts, and all six internally consistent optimism gaps are present. Table-to-summary recomputation is limited to metrics produced from the same prediction arrays: all in-sample metrics, LOOCV Spearman and nominal p, LOOCV standard R2, and LOOCV baseline errors. Secondary LOOCV Pearson, Q2, model RMSE, and model MAE remain required finite formal-permutation outputs but are not falsely required to be floating-point identical to the inherited main-model prediction table. Published values remain the output authority, and formal permutation or BH inference is not recomputed. A 2026-07-27 current-contract replay passed 15 focused tests and two subtests, covering invalid paired metrics, complete indexed metrics, missing fields and baseline predictions, read-only source validation, independent secondary LOOCV metrics, nondefault final cells, and direct-voxel plus normative-fiber full-axis paired inference. The complete current visualization directory passes 61 tests. Real canonical-publication preflights separately close all 112 paired-fit components and all 168 voxel spatial components with independent output validation, identical zero-rewrite resume, complete PNG/PDF format checks, and sampled visual review. The temporary voxel-only root also proves that the 56 inapplicable fiber endpoints retain an exact zero-component closure. | After terminal OSS-v2 and combined-v2 publication, render the formal output with the remaining fiber spatial component, repeat without force, verify no completed component rewrite, run `--validate-output` twice, and visually inspect representative outputs. |
| Interactive voxel and fiber 3-D implementation | ACCEPTED | The two PDQ-39 MATLAB examples resolve only canonical publications, request 0.5-mm inward voxel sampling, use signed `vik` mappings and independent colorbars, preserve grayscale anatomy, and create no export unless explicitly requested. Their adapter rejects a run-store `study_base_path` or connectome geometry path before reading it. A fresh 2026-07-26 source audit found all 27 repository-shared MyLFP MATLAB surface helpers byte-identical to their declared source files. The sole uncopied reference file is `demo/demo_render.m`, which hard-codes an unrelated historical research root, feature, atlas load, and video target; the repository-local PDQ-39 examples replace that project-specific demo. The audit also confirmed that the old `core/visualization/` tree is absent and found no production runtime import of the MyLFP checkout. The RAS colors remain `#F2000E`, `#0E6AAF`, and `#0CA228`; anatomy remains grayscale truecolor outside the `vik` axes mapping. A 2026-07-27 replay passed 11 focused Boxsize, signed-voxel, fiber-projection, canonical-scene, run-store-rejection, and migration tests with warnings treated as errors. Both negative fixtures, both positive scene fixtures, and the complete 55-test visualization suite pass. | Retain both examples and their migrated export helpers unchanged through final publication work, then open both real canonical scenes for visual review. |
| Final canonical 3-D scene review | PENDING | Decision 70 gives each scale and model family one fixed scene-input path, restores only a `manifest.json` plus `complete.json` pair, moves incomplete or explicitly forced targets to Trash after source validation, and removes source hashes from ordinary resume. The complete visualization directory now passes 61 tests. A fresh canonical PDQ-39 reference-voxel replay produced a valid temporary FIG, 450-dpi PNG, and one-page mixed PDF with embedded ArialMT. Visual and object-level inspection confirms signed vik surface mapping, one colorbar, three grayscale RGB anatomy slices, exact requested RAS colors, and 128 gray missing-data faces among 1,328 surface faces at the configured 0.5-mm inward sample depth. | After the active OSS releases the formal connectome, extract and review the canonical PDQ-39 reference-fiber scene, then reopen both interactive examples for the final paired scene review. |
| Cleanup policy and later sensitivity capability | ACCEPTED | Production `delete_run_cache_on_success` is false. The disabled branch returns before reading or mutating the run, and failed or partial runs are never cleanup-eligible when cleanup is enabled. Shared scientific cache is outside the cleanup boundary. The two focused false-policy and incomplete-run regressions passed again on 2026-07-27 with warnings treated as errors. | Confirm no cleanup marker or missing cache entry before the no-expensive combined replay. |
| Final three-plan requirement audit | PENDING | This ledger names the production gates and authoritative evidence required for closure. | Reopen every named manifest, validator result, output root, and visual sample; update all rows to `ACCEPTED` only when direct evidence is terminal. |

A fresh 2026-07-28 current-worktree replay passed the complete 61-test
visualization directory with warnings treated as errors: one formal-request
test, 22 formal-component tests, 33 visualization and fiber-projection tests,
and five default-contract tests.

Current uncommitted-contract update after Decisions 61 through 67:

- every current plan uses task-state path plus task-local `complete.json` as
  the restoration decision, and a terminal run resume performs no task-state
  reads;
- benchmark import requires source run and task completion-marker paths without
  parsing or hashing those markers;
- the performance harness, production registry, activation adapter, and
  executor use only `OSSSharedOmegaGroupRecord`,
  `prepare_oss_omega_max_rows`, and `oss_omega_max_` resource stages;
- historical paired final/Omega records and the standalone decoder remain
  read-only certification evidence and are not production services, cache
  authorities, or benchmark inputs; and
- preparation has no RAM admission charge; RSS, available RAM, and swap remain
  observational.

A focused 2026-07-27 executor regression now reproduces the active OSS recovery
boundary directly. Its first execution leaves an upstream task failed and its
dependent task skipped. Resume against the same run root restores neither
non-completed state because neither path has a task-local `complete.json`;
after the upstream service succeeds, both the upstream task and the previously
skipped dependent task execute and complete in dependency order. The single
focused test passes with warnings treated as errors. The complete executor
module passes 44 tests plus eight subtests under the same warning policy. This
current module result supersedes the earlier 42-test and 43-test checkpoints
retained in the matrix as chronological evidence. It proves the local resume
mechanism only. The production lineage has now proved the same boundary: the
196 dependency-skipped tasks were re-evaluated after the add-on Omega group
committed and all completed in dependency order.

The OSS root retained a preceding segment's failed manifest while its resumed
segment was nonterminal. `segment_0013` replaced the run manifest field with
`completed` and wrote the root `complete.json` last. A focused RunStore
regression proves this failed-to-completed transition and passes with warnings
treated as errors; the terminal production manifest now supplies the direct
evidence.

The current performance-matrix, structural plan-audit, and bounded
goal-acceptance suites pass 58 tests. The current service-adapter, executor,
sensitivity-checkpoint, and structural plan suites pass 82 tests plus 10
subtests. All were run with warnings treated as errors.

The historical per-row test counts above record the checkpoints at which each
contract was introduced. The current post-Decision-56 worktree supersedes
those checkpoints with one complete dual-frequency replay: 809 tests and 326
subtests passed in 133.47 seconds with warnings treated as errors.

A 2026-07-27 current-contract consistency audit removed the remaining
PASS/FAIL axis-gate wording from the umbrella OSS contract and the Task 17
status header. Current production has one Omega-max-only physical row per
deduplicated condition, no final-axis solver fallback, no equivalence-decision
gate, marker-only ordinary resume, and observational RAM/swap telemetry. The
dated paired-row, content-SHA, and memory-limit passages remain only inside
explicitly historical evidence sections. The repository-owned plan guard
passes all six tests after the later Decision 59 structural guard.

Decision 57 records the required A-through-E review of the complete current
diff. Necessary file-input and external-producer boundary checks and explicit
interface invariants remain; duplicate and speculative defenses are removed;
and every remaining failure scope is task-, cache-entry-, child-compilation-,
or postprocess-component-local. Immutable payload/publication digests and the
authorized external OSS environment lock remain only at their existing
scientific integrity boundaries. None controls ordinary resume or global
recomputation.

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
| Step 5, Layer-1 jitter and Omega-only OSS/pPAM preparation | `Independent spatial jitter computation`; `Independent OSS Omega-max preparation and pPAM`; both canonical extension rows |
| Step 6, sensitivity checkpoints, extension runs, and missing-parent rebuild | `Production identical resume acceptance`; all canonical extension rows; `Corruption, fail-once recovery, and deletion-rebuild acceptance` |
| Step 7, persistent spawned scheduler and global resource ledger | `Resource scheduling and guard contract`; `Cold/warm performance and scheduler acceptance` |
| Step 9, deterministic formal, bootstrap, pPAM, jitter, and sensitivity shards | `Resume and copied-cache implementation`; `Production identical resume acceptance`; `Cold/warm performance and scheduler acceptance` |
| Step 10, numerical, reuse, resume, deletion-rebuild, and resource acceptance | Every `PENDING` or `ACTIVE` Task 17 execution, parity, performance, recovery, resume, cache-first, and resource row |
| Step 11, current status and final audit without committing | `Final three-plan requirement audit` |
| Physical preparation occurs once before endpoint/scale fan-out | `Shared physical preparation and configured-data parity`; `Cold/warm performance and scheduler acceptance` |
| Direct voxel and normative fiber reuse bilateral exposure rows without formula drift | `Shared physical preparation and configured-data parity`; `Frozen voxel and fiber source grids` |
| Logical connectome points are covered once and minimum-grid `Omega_max` remains exact | `Shared physical preparation and configured-data parity`; `Cold/warm performance and scheduler acceptance` |
| Jitter schedules and exposure are Layer 1 while endpoint statistics remain Layer 2 | `Independent spatial jitter computation`; `Cache-first combined jitter and OSS replay` |
| OSS/pPAM uses formal-connectome `Omega_max` with versioned subset-invariance certification | `Independent OSS Omega-max preparation and pPAM`; `Canonical independent OSS-v2 publication` |
| Target-cache verification occurs once per entry and process without payload-hash rereads | `Resume and copied-cache implementation`; `Cold/warm performance and scheduler acceptance` |
| OSS row identities are scientific, cache-first, and implementation-fingerprint independent | `Independent OSS Omega-max preparation and pPAM`; `Resume and copied-cache implementation`; `Production identical resume acceptance` |
| CPU-heavy work uses spawn, disjoint work, one persistent ready queue, and one worker ceiling | `Resource scheduling and guard contract`; `Cold/warm performance and scheduler acceptance` |
| Workers receive pure data and only the parent mutates durable run state | `Resource scheduling and guard contract`; `Cold/warm performance and scheduler acceptance` |
| Fiber hot loops avoid path, NIfTI, and transform locks and use point-byte partitions | `Shared physical preparation and configured-data parity`; `Cold/warm performance and scheduler acceptance` |
| Large payloads are written once and consumers use immutable views without axis duplication | `Shared physical preparation and configured-data parity`; `Cold/warm performance and scheduler acceptance` |
| Vectorized statistics and null fast paths preserve scalar parity without unused retained matrices | `Shared physical preparation and configured-data parity`; `Cold/warm performance and scheduler acceptance` |
| Formal, bootstrap, pPAM, and jitter RNG schedules are invariant to workers and scheduling | `Shared physical preparation and configured-data parity`; `Cold/warm performance and scheduler acceptance` |
| Resume re-evaluates dependency skips and accepts only provenance-safe overrides | `Resume and copied-cache implementation`; `Production identical resume acceptance`; `Corruption, fail-once recovery, and deletion-rebuild acceptance` |
| Worker, connectome-I/O, solver-token, VAL mount-continuity, and reporting cadence satisfy the resource contract; RAM and swap remain observational | `Resource scheduling and guard contract`; `Cold/warm performance and scheduler acceptance` |
| Tau, Coverage, selected-reference overlap, support QC, and pPAM boundaries use their exact declared directions | `Boundary and computability policy`; `Frozen voxel and fiber source grids`; `Shared physical preparation and configured-data parity` |

The repository-owned plan-audit guard must require a one-to-one row count for
every still-open source-plan checkbox, preserve the exact set of open Step
numbers, reject duplicate mapping labels, and reject a mapping reference that
does not name an Evidence Matrix requirement. The other two source plans
currently have no open checkbox; opening one without extending this ledger
must therefore fail the same guard.

`test_task17_plan_audit.py` implements this contract. Its six focused tests
pass with warnings treated as errors: the 26 open
dual-frequency items mapped to 26 unique ledger rows, the ten open Step
numbers matched exactly, both other plans had no open checkbox, and every
backticked mapping reference named an existing evidence row or an allowed
status token. They also enforce the 25-row status/final-closure contract and
the repository-path closure described below. The new guard and the existing
bounded goal-acceptance suite now pass all 14 tests together under Conda
`leaddbs`.

The sixth structural case records Decision 59 and rejects any benchmark-row
call to the deleted recursive repository code-identity helper. The complete
performance-matrix module plus plan-audit replay passes 46 tests with warnings
treated as errors.

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

The current live matrix contains 25 unique rows: 14 accepted, no active row,
11 pending rows, and no blocked row. The independent Omega-only OSS computation
and its identical-resume proof are accepted. The plan-audit guard continues to
reject final acceptance while any row remains active or pending.

The 2026-07-27 production continuation retains the same Omega-only lineage.
`segment_0011` ended when its Codex-owned persistent terminal session was
reclaimed; its mount guard ended on an ordinary sample and recorded no VAL
loss or scientific-task failure. `segment_0012` resumed the same run root in a
detached screen session with 14 workers, one solver token, and the mount-only
guard. At that resume boundary, 393 tasks were complete, the add-on group task
was running, 196 downstream tasks remained dependency-skipped, the reference
Omega closure was 34 rows, and the raw stable add-on cache inventory contained
20 candidate rows. These values are historical recovery evidence only. The
later terminal group records, all 56 pPAM endpoints, root `complete.json`, zero
current failures, and separate identical-resume proof close those requirements.

`segment_0013` then resumed the same run root after the mount interruption. It
resolved exactly 19 of the frozen 26 physical requests from complete cache
entries. The earlier raw count of 20 included one cache entry outside this
request closure and was not a valid completion numerator. The segment then
atomically published rows under scientific identities
`eea42907094f6c4de81e4525eed201548c8aaa261bf6a4863dbbab7d9cbd56d0`
at 2026-07-27 23:19:03 PDT and
`86fc8fe1673451d7766c5e01b7ea641857929e10f441fea215c14a94ce1523ac`
at 2026-07-28 01:05:43 PDT. At 2026-07-28 02:46:16 PDT it atomically
published two more rows under scientific
identities
`93b0e38338df3babbb974a56f8e2f0ea05b10a0254d22150df6329988615de0e`
and
`1532eb7b4c9a2e0d0526601f0b1c890f949c2ce3e75e8775fce33923f45148f8`.
Both manifests are complete and independently bind the expected 7,193-fiber
Omega axis, while their stimulation and geometry hashes differ. The stable
add-on request closure was therefore 23 of 26 at that boundary. At
2026-07-28 04:29:24 PDT, the same segment atomically published one additional
complete 7,193-fiber Omega row under scientific identity
`48cd0540bc81d7e2d5848f06b5cd1b7f22a1ede4c114eb7841bb14fa7c26d63e`.
Its feature axis has SHA-256
`af4392251bb3eaddfd914548e55ae619246c863771d7f75f3d8fad1f9c900bf3`.
This advanced the request closure to 24 of 26. At
2026-07-28 06:13:18 PDT, the segment published scientific identity
`3fbe430a042db815e3f622eab2fa98862c5630c61d706bfbb39c85db311d1ed3`,
advancing the exact closure to 25 of 26. The sole remaining request was
`sub-SNr014`, right-side, 30 Hz, 60 microseconds. Each request uses its own
internally chunked solver sequence; cache-directory counts and producer-chunk
counts are not completion numerators. At 2026-07-28 07:52:01 PDT, the final
row and add-on group committed. The two terminal group records contain exactly
34 reference and 26 add-on row IDs. Direct parsing of the 590 authoritative
task-state JSON files confirms that all tasks are completed with 590 local
completion markers. The formerly skipped closure completed as exactly 28
observed pPAM workspaces, 28 permutation schedules, 112 permutation blocks, and
28 aggregates, complementing the same 28-task closure already completed for
reference endpoints. The final result contains 56 unique pPAM endpoints, 56
final decisions, 56 extension results, and 2802 artifact-index rows in both
JSON and CSV. The run manifest and root completion marker are terminal and no
task is failed, skipped, or running.

The terminal `segment_0013` guard CSV contains 36,408 one-second observations
from 2026-07-28T04:22:03Z through 14:52:51Z. Its observed peak task-tree RSS is
46,455,406,592 bytes and maximum sampled task-tree CPU is 1,415.5 percent.
Swap never exceeds the 20,925,844,029-byte epoch baseline and ends lower at
19,155,449,283 bytes. Events consist only of `sample` and the terminal
`runner_exit`; no guard stop event is present. RAM and swap are descriptive
observations only.

The final performance checklist expands to the following non-overlapping
evidence map:

| Final checklist clause | Required ledger evidence |
| --- | --- |
| One physical preparation before endpoint and scale fan-out | `Shared physical preparation and configured-data parity`; `Cold/warm performance and scheduler acceptance` |
| Distinct voxel and fiber bilateral formulas reused across scales | `Shared physical preparation and configured-data parity` |
| One logical connectome traversal with measured raw-boundary overlap and exact `Omega_max` | `Shared physical preparation and configured-data parity`; `Cold/warm performance and scheduler acceptance` |
| Layer-1 jitter schedule and exposure with Layer-2 endpoint statistics | `Independent spatial jitter computation`; `Cold/warm performance and scheduler acceptance` |
| Exact canonical-ID final-axis subsetting from the shared `Omega_max` row before pPAM | `Independent OSS Omega-max preparation and pPAM` |
| Once-per-process target-cache verification without checksum rereads | `Cold/warm performance and scheduler acceptance`; `Resume and copied-cache implementation` |
| Stable OSS scientific identities and cache-first historical promotion | `Independent OSS Omega-max preparation and pPAM`; `Production identical resume acceptance` |
| Spawned CPU work, disjoint units, persistent ready queue, and one public worker ceiling | `Resource scheduling and guard contract`; `Cold/warm performance and scheduler acceptance` |
| Pure-data spawned commands, read-only shared artifacts, and parent-only mutation | `Resource scheduling and guard contract`; `Cold/warm performance and scheduler acceptance` |
| Path-free fiber hot loops and point-byte-balanced whole-fiber partitions | `Shared physical preparation and configured-data parity`; `Cold/warm performance and scheduler acceptance` |
| Single-write large payloads and immutable indexed views | `Shared physical preparation and configured-data parity`; `Cold/warm performance and scheduler acceptance` |
| Vectorized numerical parity without duplicate operators or unused retained matrices | `Shared physical preparation and configured-data parity`; `Cold/warm performance and scheduler acceptance` |
| Historical RNG schedules and worker-count invariance | `Shared physical preparation and configured-data parity`; `Cold/warm performance and scheduler acceptance`; `Production identical resume acceptance` |
| Dependency-skip reevaluation and scientific-identity-safe resource overrides | `Production identical resume acceptance`; `Independent OSS Omega-max preparation and pPAM`; `Cache-first combined jitter and OSS replay` |
| Worker and solver limits, mount-only local guard, observational RAM/swap telemetry, and two-hour Codex boundaries | `Resource scheduling and guard contract`; `Cold/warm performance and scheduler acceptance` |
| Exact tau and Coverage boundaries, reference overlap, strict support QC, and pPAM `p(A) > 0.5` | `Boundary and computability policy`; `Shared physical preparation and configured-data parity`; `Independent OSS Omega-max preparation and pPAM` |

A current read-only production plan replay resolves 28 scales, 224 endpoints,
and all four model families. Through `formal`, the block-level DAG contains
10,920 tasks: 1,288 observed tasks and 9,632 formal tasks, including 4,480
fixed 250-replicate permutation blocks and 4,480 matching bootstrap blocks.
Through `report`, it contains 11,648 tasks after adding 728 sensitivity and
reporting tasks. The accepted v8 parent contains 1,512 monolithic tasks because
it predates this decomposition. Both requests retain the same scientific
configuration identity. These counts are structural evidence only; numerical
equivalence remains pending in the configured-data parity row.

The accepted jitter-v2 evidence was reopened without running the full
payload-hashing validator while the OSS solver is active. Both extension
manifests remain terminal `completed`, complete-scope, 56-result,
jitter-only publications. Their current manifest and artifact-index SHA-256
values match the retained validation report exactly. The retained report
remains `validated` for two publications and its SHA-256 remains
`f5491c15fd2d07b81a1f8b7910d345e63b45d61f59eb929ce597bf3073d95040`.
This confirms the small terminal evidence is unchanged without contending for
VAL bandwidth; complete payload revalidation remains ordered after independent
OSS.

Both canonical final-in-sample publications were also reopened through their
small terminal metadata. Each manifest remains `completed`, contains 56
results, binds the accepted v8 parent and scientific configuration, and
declares only `final_in_sample`. Each artifact index has 674 completed rows:
672 endpoint artifacts spanning 28 scales and both reference and add-on roles,
plus the two aggregate result tables. Neither publication metadata tree
contains a run-store, task, work, or runtime-work path. The real 112-endpoint
formal preflight independently decoded the paired metric closure; no large
permutation payload was reread during this lightweight audit.

The accepted v8 parent and canonical main publications were likewise reopened
through terminal metadata only. The parent run manifest and run marker remain
`completed`; all 1,512 task states and all 1,512 task markers are present and
completed. The direct-voxel and normative-fiber model manifests remain
terminal, retain 28 scales, bind the same v8 source run and scientific
configuration, and keep their accepted manifest and artifact-index SHA-256
values. No 73.4-GB payload rehash was performed while the independent OSS
solver was active.

## Current YAML Preflight

The current repository workflow resolves only `direct_voxel_model.yaml` and
`normative_fiber_model.yaml`; no Python loader references the historical
`model.yaml`. The profiles retain the frozen tau and Coverage grids,
main-analysis cells, three fiber fold minima of one, and retained-cache policy.
Raw source-file SHA values are not gates. The loader constructs normalized
typed identities after parsing, so comments, whitespace, key order, line
endings, and equivalent scalar serialization do not invalidate computation.
The repository default remains three workers; formal worker overrides remain
CLI/runtime inputs. After the minimal-resume and RAM-control cleanup, all 24
configuration and application-CLI tests plus 12 subtests passed under Conda
`leaddbs` with warnings treated as errors.

The current admission command was repeated on 2026-07-27 after the append-only
marker cleanup against the retained formal study input and the three current
repository YAML files. It parsed and validated all four model families, all 28
scales, and all 224 available endpoints without creating a run, reading a
result cache, or starting a worker. It returned configuration hash
`1e382f02c20c90571c4c3c02e3c20845b1e91bf1cca67091a5d6ce75def7017d`
and scientific-configuration hash
`6d23bc0e9f30e697806d0847f238c1c8b09170673dc1ff0c29253808a5c401d5`.
The latter remains identical to the completed parent.

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
combined, and postprocess executions.

The synthetic end-to-end suite was also repeated on the isolated branch. All
seven tests passed with warnings treated as errors, covering local YAML
validation, planning, execution, resume, main publication, and sensitivity
publication across their real module boundaries. Synthetic fixtures do not
replace configured-data or formal-run acceptance.

After the minimal-resume changes entered the current production checkout, the
expanded end-to-end suite passed all eight tests with warnings treated as
errors. It additionally proves that a sensitivity resume bypasses
creation-only configuration-source hashing while restoring completed tasks by
their local completion markers.

The cache, run-cache cleanup, and sensitivity-checkpoint suites were repeated
at the same checkpoint. All 58 tests and 20 subtests passed with warnings
treated as errors. They cover content-addressed cache validation, portable
checkpoint closure, copied-root reuse, corruption rejection, and the rule that
failed or partial runs retain recovery state. Production identical resume and
deletion-rebuild acceptance remain separate pending gates.

After the minimal-resume and RAM-control cleanup, the complete focused fault,
performance-matrix, byte-ledger, counter, process-probe, pre-instrumentation,
strict-resource, and mount-guard set was replayed in one invocation. All 142
tests and two subtests passed with warnings treated as errors. This proves the
current tooling boundary; the production 72-row matrix and marked six-case
fault sequence remain pending until the independent OSS authority is terminal.

The current resume implementation was re-inspected directly after Decision 44.
`RunIdentity` no longer compares repository, configuration, plan, or input
hashes when RunStore opens an existing root. The executor restores a task when
the deterministic task state file and task-local `complete.json` both exist; a
missing marker makes only that task eligible to run, while an unreadable marked
state is an explicit interface error rather than permission to rerun. A
successful run writes the run-root `complete.json` last. The one-time explicit
`my_helper/fiber/pipelines/migrate_dual_frequency_completion_markers.py`
command creates markers only for legacy task states already marked completed
and is never invoked by ordinary resume. Failed or partial runs remain
ineligible for cleanup, and the production false cleanup policy returns before
inspection or mutation. A fresh focused replay of the explicit migration
fixture passes with warnings treated as errors and proves both first-pass
marker creation and second-pass zero-create idempotence; the public wrapper
also exposes only the required `--run-root` argument. The paired terminal-run
resume fixture passes again and proves that an intact root marker returns
without configuration-source hashing, DAG compilation, task-state reads,
report aggregation, finalization, or final-decision rewrites.

That review was initially incomplete at the application boundary. Decision 46
removed the remaining parent-checkpoint, seed, artifact, shared-cache, and
parent scientific-configuration hash gates before child restoration. The
focused exact-child regression changes their historical SHA fields and JSON
bytes, removes one task marker, and proves that only that task executes while
completed checkpoint roots are not rewritten.

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
- `repair_task17_display_smoothing_publication.py`;
- `migrate_dual_frequency_completion_markers.py`; and
- `my_helper.fiber.core.viz.formal_postprocess`.

A 2026-07-27 current-worktree replay invoked `--help` for all 15 script
entrypoints and the formal-postprocess module with caller `PYTHONPATH`
removed. All 16 parsed and imported successfully without reading a production
run or starting a worker.

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

The injected spawned-worker fixture and public `run` operation were integrated
by merge `b8cf39670`, and the fast-forwarded production checkout passed the
complete 768-test dual-frequency and 54-test visualization regression with
warnings treated as errors. No production matrix manifest exists, so
production execution remains open. The
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

The formal postprocess request was also audited read-only from its parsed JSON
document. It names exactly the canonical direct-voxel and normative-fiber main
and final-in-sample publications, contains no `.runs` path, selects all
available scales, and requests paired-fit, voxel 2-D, and fiber 2-D components.
Raw request-file SHA-256 is intentionally not an acceptance or resume gate;
semantically equivalent serialization does not invalidate the request. The
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
matrix-level manifest/acceptance, and public `run` were integrated by merge
`b8cf39670`; production execution remains pending.

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
Five candidate-parity tests and 36 performance-harness tests pass. Merge
`b8cf39670` integrated the reviewed implementation after the superseded OSS
runner released the production checkout. The fast-forwarded production
checkout then passed 768 dual-frequency tests and 54 visualization tests with
warnings treated as errors.

The isolated handoff was rooted in two ordered commits on top of main baseline
`f08658f0d`: implementation commit `186b36d6f` and request commit
`ae0b60486`. Merge `b8cf39670` preserved the complete reviewed range rather
than selecting only the two foundational commits. The historical frozen
request SHA-256 was
`c9f4bca02361f7004adc383e95df69a40a5dbd31ca30e0acf64286073948e839`.
Decision 54 supersedes that byte-level gate: benchmark `prepare` validates the
canonical parsed request identity and normalized workflow identities.
Production execution remains blocked while the replacement independent OSS
lineage is active.

The production checkout now contains the reviewed implementation and later
Omega-only compatibility changes. The 768-test dual-frequency and 54-test
visualization regressions passed after the production fast-forward; no
additional branch merge is required before benchmark preparation.

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

At that historical pre-merge checkpoint, the request was frozen at
`config/four_model_v1/acceptance/task17_performance_benchmark_request.json`.
It references only the parent-run input copies, declares the 64-GiB ceiling,
and leaves real-cold solver authorization null. The configured benchmark root
is separate under `summary/spot/acceptance`. Preparing or executing it remains
pending until independent OSS is terminal and the isolated implementation has
passed complete regression in the production checkout.

The production performance acceptance became active on 2026-07-28 after the
independent Omega-only OSS lineage completed. The prepared benchmark root is
`/Volumes/VAL/STNSNr/summary/spot/acceptance/task17-performance-matrix-v1-20260725`.
It contains exactly 72 immutable row contracts and a terminal benchmark-root
marker. Its 224-row configured candidate-parity report has zero candidate
false negatives, zero full-candidate mismatches, and zero fold-candidate
mismatches. The formal matrix runner is active in detached screen session
`task17_performance_matrix`, with the VAL mount-continuity guard in
`task17_performance_guard`. Final acceptance remains pending until all row
results, deterministic reporting, exact resume, and read-only validation
complete.
The first production warm-seed attempt then completed all 46 tasks but failed
after scientific completion because exFAT AppleDouble metadata was treated as
a cache-kind entry. The local fix excludes only `._*` filesystem metadata and
adds recovery from an attempt that already has both its root completion marker
and seed-attempt result. Forty-two focused performance-harness tests pass. The
next `run` reused `attempt_0001`, published a 22-entry `warm_seed.json`, and
created no `attempt_0002`, proving that the completed scientific seed was not
recomputed. The same matrix root is continuing with subsequent warm seeds.

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
zero-skip repeat passed all 828 tests and 329 subtests in 133.20 seconds,
including the endpoint-specific tau/Coverage resolver fixture, both run-store
scene-provenance rejections, cross-endpoint physical pPAM sharing, and
outcome-specific observed-workspace identity. The run used temporary fixtures,
did not authorize an expensive producer, and did not write any production run
or publication root. This is complete static and synthetic regression
evidence; it does not replace the remaining production executions and
validators.

An offline integration preflight then merged isolated performance head
`2afd3e50e` into main head `2f2e2bd97` on the separate
`task17-perf-merge-preflight` branch. Git resolved the seven-path closure
without a conflict. After the same ignored frozen allowlist, frozen manifest,
and MNI template segmask used by the main checkout were materialized at the
integration-worktree paths, the complete dual-frequency and visualization
regression passed all 834 tests and 329 subtests in 132.78 seconds with no
failure or skip. The production checkout and active OSS process were not
modified, and the preflight read no production payload. This evidence closes
merge compatibility before terminal OSS, but the production checkout must
still merge the reviewed implementation and repeat the complete regression
after the OSS writer exits.

The same isolated integration branch now enforces the complete paired-fit
publication contract before any formal visualization is rendered. Paired-fit
schema v2 requires all 43 declared in-sample, LOOCV, completeness, and optimism
fields; the six-column subject table including both baseline predictions; full
finite subject and permutation closure; valid probability, correlation, and
error domains; and the declared arithmetic direction for every optimism gap.
It rejects adjusted R2, incomplete masks, missing or nonfinite evidence,
inconsistent gaps, and stale v1 resume. Each endpoint component, formal
endpoint, and root endpoint index retains the same metric set, while terminal
validation compares all three copies. Formal read-only preflight now enforces
the same source contract and rejects a prediction-table metric mismatch without
substituting recalculated values. Forty-four focused tests and all 54
visualization tests passed. A fresh complete dual-frequency and visualization
regression then passed 846 tests and 329 subtests in 132.83 seconds with
warnings treated as errors, no failure, and no skip. This remains isolated
merge-readiness evidence; the active OSS process and production checkout were
not modified.

A current merge-scope audit at isolated head `428d18104` confirms that
production head `2f2e2bd97` remains its ancestor. Before this documentation
checkpoint the range contains 114 commits and exactly 12 changed paths: the
performance worker test, two worker integration files, the performance runner,
four paired/formal visualization implementation and test files, the frozen
benchmark request, both implementation plans changed by the isolated work, and
this acceptance ledger. The benchmark request SHA-256 remains
`c9f4bca02361f7004adc383e95df69a40a5dbd31ca30e0acf64286073948e839`.
Both worktrees are clean. The terminal audit must repeat ancestry, path closure,
request digest, and cleanliness after the OSS writer exits; this checkpoint
does not authorize an early merge.

The current production checkout supersedes those pre-merge checkpoints. The
reviewed implementation is present, and the uncommitted Decision 43 through 45
worktree passes 801 dual-frequency tests plus 326 subtests and 55 visualization
tests. The benchmark request now binds
`task17-oss-v2-omega-only-formal-20260726`, contains no RSS ceiling, and has
SHA-256
`1440883c8053f6c0ca02436caec5554b5ae26dc12fffb099f419dcada969b180`.
This current request remains pending until its OSS authority is
terminal-completed.

Decision 69 aligns the pending formal postprocess with the repository-wide
minimal resume contract. Paired-fit, voxel, and fiber components now publish a
component-local `complete.json` after their deterministic result and outputs.
The formal root publishes `complete.json` last. Ordinary resume checks only
the result and marker paths, while a completed root returns its stored
manifest before reopening publications or components. Request, resolved-
request, source, style, repository, and code hashes no longer gate formal
resume. Explicit force moves the existing formal root to Trash before a fresh
render. Explicit input and terminal-output validators retain their scientific,
structural, and format checks outside ordinary resume. The focused
three-component set passes 49 tests, the complete visualization suite passes
55 tests, and the combined visualization plus plan-audit set passes 63 tests
with warnings treated as errors. Production 112-endpoint execution remains
pending and is not claimed by these fixture tests.

Decision 70 applies the same minimal resume boundary to interactive 3-D scene
inputs. The output path is fixed by scale and model family; `manifest.json`
plus `complete.json` restores that scene input without reopening its
publication. Missing markers affect only that scene input, and explicit force
validates the source before moving an existing target to Trash. The focused
scene-input set passes eight tests, the complete visualization suite passes 58
tests, and the combined visualization plus plan-audit set passes 66 tests with
warnings treated as errors. The production 3-D visual review remains pending.

The current real formal-postprocess preflight was repeated after Decisions 69
through 71. It returned `valid` for four canonical publications, 28 scales,
112 endpoints, all three requested components, both masks, the 8.69-GB anatomy
background, the 1.7-million-fiber connectome, 18 target definitions, and the
required PDF and PNG tooling. The configured formal output root was absent
before and after validation. This proves current input readiness without
claiming the still-gated production render.

All raw benchmark-request digest statements in the preceding dated pre-merge
checkpoints are retained only as historical provenance. Decision 54 supersedes
them as current admission, row-identity, cache, resume, or rerun requirements.
The current contract uses the canonical parsed request identity, exact accepted
input paths, normalized configuration identities, and the task-plan identity.

The current uncommitted production diff received a final minimal-sufficient-
correctness pattern review while the independent OSS writer remained active.
No added production line contains a catch-all exception, automatic retry,
backoff, fallback execution path, repository-wide identity gate, or whole-file
configuration hash used as a resume or rerun switch. Category A and B checks
remain only at JSON/YAML parsing, explicit public interfaces, scientific cache
descriptors, publication indexes, and toolchain inputs actually consumed by
the selected operation. No duplicate or speculative Category C or D branch
was found, and previously broad Category E RAM admission, RSS termination,
swap-growth termination, repository identity, source identity, and input/audit
hash resume gates remain absent. Available RAM, RSS, and swap are observational
telemetry only. A focused current-worktree replay passed 18 tests covering
normalized configuration identity, marker-only resume, missing-marker local
rerun, absence of input and audit hash comparison, no checkpoint payload
hashing, no task memory budget or memory-delayed dispatch, observational RSS
and swap, semantic benchmark request identity, and absence of repository or
source identity gates. This review changed no production code.

A real canonical-publication scene-input preflight now covers all 28 scales
for both reference and add-on voxel without opening the still-active formal
connectome. All 56 v2 scene inputs resolved the published final model and
benefit map only from the canonical direct-voxel model set and retained the
publication-local 0.5-mm NIfTI rather than copying it. These realized final
models all select tau 200 and Coverage 5. Every image has finite nonzero data;
the per-image count ranges from 577 to 638 voxels. The PDQ-39 reference image
has shape 394 by 466 by 378, 638 finite nonzero voxels, and finite values from
-0.7178884744644165 to 0.6422083973884583. Each temporary output contains only
`manifest.json` and `complete.json`. A second invocation of the complete
56-scene closure preserved all 112 files' bytes, SHA-256 values, sizes, and
mtimes, proving the real path-and-marker resume boundary across both voxel
families. These outputs remain a temporary preflight; canonical voxel
rendering, fiber extraction, and visual review remain pending until the
independent OSS workload releases the formal connectome I/O path.

A separate real-publication preflight rendered the full 28-scale, 112-endpoint
paired-fit closure without loading anatomy or connectome data. It resolved
reference and add-on voxel and fiber endpoints from the four canonical main
and final-in-sample publications and produced 112 PNG files, 112 PDFs, 112
component manifests, and a terminal paired-only formal root with no failure.
Independent output validation found 112 endpoint manifests, 224 declared
rendered files, and 229 metadata files. An identical root invocation preserved
every file's bytes, SHA-256 value, size, and mtime. Visual inspection covered
all four PDQ-39 models and the largest-width FSS and ODQ examples; every
inspected plot had complete uncropped panels, shared In-sample and LOOCV axes,
readable points, regression curves, confidence bands, and the declared
Spearman and permutation annotations. The sampled numerical extremes also
render correctly: EAT-10 reference fiber has the lowest LOOCV Spearman rho and
largest optimism gap, tremor add-on voxel has the highest LOOCV rho, and ADL
add-on voxel represents the 13-subject minimum. Every PNG has height 1037
pixels at 600 dpi; tight bounding boxes produce 106 widths of 1781 pixels, two
widths of 1808 pixels, and four widths of 1790 pixels without clipping. Every
PDF is one page with the corresponding tight-bounding-box width, and all 112
embed only subsetted ArialMT and Arial-BoldMT. This temporary paired-only
transaction proves the complete real paired-fit rendering, output-validation,
and marker-only resume boundaries. Formal acceptance still requires the
canonical transaction that also contains voxel and fiber spatial components.
An independent metric audit over the same 112 endpoint manifests found every
required paired Spearman, Pearson, nominal-p, permutation-p, fit, error,
baseline-error, completeness, and optimism field finite and present. It found
no adjusted-R2 field and no optimism-direction mismatch. All endpoints declare
10000 requested in-sample and 10000 requested LOOCV permutations; 56 endpoints
have 16 finite subjects and 56 have 13.

A fresh 112-endpoint publication scan confirms that paired-fit consumes each
final model's selected fields rather than a visualization constant. Every
direct-voxel final model records tau 200 and Coverage 5, and every normative-
fiber final model records tau 400 and Coverage 5; all 112 records have
`pre_specified_accepted` source status. The uniformity is therefore an observed
property of this accepted run, not hard-coded postprocess behavior. Every
final-in-sample summary matches its own final model's selected tau and
Coverage. Reference branches contain 28 voxel and 28 fiber records. Add-on
voxel contains 22 no-delta-reference and six delta-reference-adjusted finals;
add-on fiber contains 24 and four respectively.

A real PDQ-39 voxel-only 2-D preflight exposed and resolved one narrow terminal
verification defect. The partial request correctly kept all four model
endpoints in its resolved cohort, rendered three spatial component manifests
for each applicable voxel endpoint, and recorded zero component manifests for
the two inapplicable fiber endpoints. The independent verifier already derived
those exact expected counts but then redundantly rejected every empty list.
That unconditional rejection was removed; exact per-unit expected-count,
closure, containment, completion-marker, and declared-output checks remain.
The focused regression proves that a voxel-only request accepts three voxel
manifests and zero fiber manifests, while the existing complete-root and
three-family tests remain passing.

The corrected real preflight is terminal and independently valid for four
PDQ-39 endpoints, six component manifests, and 12 declared PNG or PDF outputs.
It renders the raw, 1-mm FWHM, and 2-mm FWHM canonical publication maps for
both reference and add-on voxel. The anatomy loader read one bounded crop of
2,461,968 bytes for reference and 1,990,676 bytes for add-on from the
1971-by-2331-by-1891 uint8 background; it did not materialize a full floating
anatomy volume. The first render completed in 12.16 seconds with a maximum
reported resident set of 1,580,531,712 bytes. An identical invocation reused
the terminal root and preserved every file's bytes, SHA-256 value, size, and
mtime. Both sampled raw-map PNGs are 3045 by 2335 pixels at 600 dpi and show
complete uncropped 3-by-3 panels, anatomical outlines, vik benefit mapping,
row and column strips, the scale bar, and the shared colorbar. Both PDFs are
one page and embed only subsetted ArialMT and Arial-BoldMT. This remains a
temporary preflight; formal acceptance still requires the final 112-endpoint
transaction after the sensitivity publications are terminal.

The same voxel-only request was then expanded to the complete 28-scale,
112-endpoint cohort. It completed with no failure and produced 168 spatial
component manifests, 168 PNG files, 168 PDF files, and 168 component completion
markers for the 56 applicable voxel endpoints; all 56 fiber endpoints retained
the exact zero-component inapplicable closure. Independent terminal validation
accepted all 336 declared outputs, all 168 component manifests, and 341 public
JSON or CSV metadata files. The identical invocation reused the complete root
and preserved every file's bytes, SHA-256 value, size, and mtime.

All 168 PNG files are 3045 by 2335 pixels at 600 dpi. All 168 PDFs contain one
page and embed only subsetted ArialMT and Arial-BoldMT. Every raw-map component
uses `bounded_union_lazy`, `finite_heatmap` support, and reports that no full
floating anatomy volume was loaded. The bounded anatomy crop is 1,990,676
bytes for add-on and 2,461,968 bytes for reference. Visual review covered the
minimum raw heat limit at CCCS reference, the maximum raw heat limit at HAMD
add-on, and the 2-mm FWHM delta-reference-adjusted ODQ add-on branch. Each
sample has complete uncropped 3-by-3 panels, anatomical outlines, vik benefit
mapping, row and column strips, the shared colorbar, and the 2-mm scale bar.
The temporary full voxel-only closure therefore proves the real spatial
rendering and resume contracts without opening the normative fiber connectome;
the final canonical combined transaction remains pending. The complete current
visualization test directory passed 59 tests after the partial-component
terminal-verifier correction.

A fresh headless MATLAB replay of the canonical PDQ-39 reference-voxel scene
completed from the publication-backed scene input with tau 200, Coverage 5,
and 0.5-mm inward surface sampling. It produced a temporary 44,874,802-byte
FIG, 8314-by-5456 PNG at 450 dpi, and one-page mixed-mode PDF with embedded
ArialMT text. The rendered PDF shows grayscale anatomy, the signed vik voxel
surface, one right-side colorbar, and the RAS triad. Direct FIG inspection found
1,328 voxel surface faces: 1,200 scalar-colored faces and 128 gray missing-data
faces, for a missing-face fraction of 0.0963855421687. All three anatomy
surfaces were RGB truecolor with identical channels, so the statistical
colormap did not recolor anatomy. The FIG contains one RAS triad and one
colorbar. Its R, A, and S label colors are exactly the configured red, blue,
and green values. The default full-brain camera makes the small STN surface
occupy little of the static export, while the FIG remains interactive and
zoomable. The final 3-D row remains pending until the canonical reference-fiber
scene is extracted and reviewed from the now-terminal OSS authority.

A fresh minimal-sufficient-correctness review of the current uncommitted
production diff classified every added validation, hash, retry, fallback,
cache-invalidating branch, and exception handler. Required input-boundary
checks remain limited to parsing declared JSON or YAML objects, publication
artifacts, and explicit benchmark or acceptance inputs. Required interface
invariants remain limited to deterministic result paths, task-local and
run-local `complete.json` markers, explicit force replacement through Trash,
and exact output closure. The historical-parent Omega descriptor derivation is
retained only because the immutable accepted parent predates that required OSS
field; it reads the exact declared cache manifests and is scoped to creation of
the new OSS-containing child. No generic retry, catch-all exception handler,
repository-source identity gate, raw configuration hash resume gate, or global
cache invalidation was added. Ordinary resume remains path-and-marker only.

Decision 72 identified one startup-only duplication before its implementation:
terminal main and sensitivity resume compiled the ordinary DAG before checking
the run-root marker. The accepted minimal order is input JSON and YAML parsing,
deterministic root resolution, then terminal marker return before DAG or parent
task-state work. Exact base-run resolution and its run-manifest parse remain the
required sensitivity input boundary. Incomplete main resume may compile its
schedulable plan; incomplete sensitivity resume must load its own persisted
plan. The change is confined to future entrypoint calls and does not alter the
loaded active OSS executor or worker. Both direct terminal-resume regressions
pass, and the incomplete one-task sensitivity replay explicitly rejects parent
DAG compilation. The complete application-service, synthetic end-to-end, and
public CLI modules pass 23 tests and five subtests with warnings treated as
errors, accepting this startup-only item.
The follow-up call-site audit found `RunStore.is_complete()` had no production
caller after this change and was exercised only by its own test. It is removed
as a class C duplicate; the finalization test reads the required run-root
marker directly, so the public completion contract and invalidation boundary
remain unchanged. The focused finalization and plan-audit replay passes nine
tests with warnings treated as errors.

Decision 73 closes the one remaining public visualization resume exception.
The legacy manifest-driven entry point no longer computes a request hash or
scans outputs to decide reuse. Root and endpoint-local `complete.json` markers
now provide the same fixed-path boundary as the formal renderer, and explicit
force replaces the root through Trash after input validation. The complete
public visualization-entry test module passes 29 tests with warnings treated
as errors. It proves path-and-marker root reuse, endpoint-local partial resume,
force replacement, and no Trash mutation when force input validation fails.
The complete visualization directory passes 61 tests with warnings treated as
errors.

Decision 74 places the formal request's required lightweight JSON field checks
before root-marker restoration. A valid terminal request still returns before
publication, anatomy, connectome, or tooling resolution. The focused
terminal-resume fixture and the complete 61-test visualization directory pass
with warnings treated as errors.

Decision 75 retains one additional A-category boundary: run IDs are parsed
before they are joined to a run root and must be one nonempty component other
than `.` or `..`. Main, sensitivity-child, and optional rebuilt-parent IDs use
the same helper. This prevents output-root escape without inspecting the
filesystem or adding any resume, hash, or invalidation state. The focused
public-application module passes six tests and seven subtests.

Decision 76 gives canonical extension IDs the same publication-root boundary.
Final-in-sample and terminal jitter or OSS replay share one parser before
writer creation. The complete publication module passes 18 tests; no invalid
ID creates an extension manifest. A fresh current-worktree replay also passes
all five Task 17 model-set publication tests with warnings treated as errors,
covering the canonical four-model publication closure independently of the
still-running OSS extension. The seven focused Task 17 extension-publication
tests also pass, covering terminal source admission, self-contained payload
replay, relative indexing, parent binding, and deterministic publication
replacement before the production OSS-v2 replay is eligible to run. A live
target preflight confirms that the automatic same-run OSS v1 mirror exists,
while the canonical `task17-oss-v2-omega-only-formal-20260726-v2` directory
and its acceptance report are both absent; the eventual unfiltered replay
therefore has no premature v2 collision. The same live target scan reconfirms
that the frozen combined run root and both combined-v2 domain targets are
absent. Its first invocation must therefore remain the documented cache-only
command without `--resume` or `--allow-expensive-producers`.

A production-source identity scan after Decision 76 found no comparison of
repository code identity, configuration hash, scientific-configuration hash,
plan hash, or OSS source identity in ordinary task or run resume. Those values
remain creation-time provenance, reporting fields, or stage-local scientific
cache identity only. The canonical extension contract intentionally commits
`extension_manifest.json` last; task and run execution use `complete.json`.
Adding a second extension marker would duplicate the documented publication
terminal state and is not required.

The complete current-worktree dual-frequency directory also passes 818 tests
and 331 subtests. The accepted run uses pytest-local `-W error`; it does not
export `PYTHONWARNINGS=error` into the fault harness's nested Conda processes.
The latter test-launch mistake had produced eight environment-induced failures
inside Conda before any fault fixture command ran and is not retained as
product evidence.
The public visualization entry point also reuses endpoint IDs parsed at the
JSON boundary instead of normalizing them again inside the rendering loop.
Those IDs are restricted to one safe path component because they directly name
output directories; this is retained as an A-category untrusted path boundary.
The focused boundary fixture and complete 61-test visualization directory pass.

The current Decisions 72 through 76 diff has the following minimal-sufficient
classification:

- A: one-time JSON and YAML parsing, required-field type checks, and safe
  single-component run and extension identifiers at public run, sensitivity,
  formal-postprocess, and legacy-postprocess boundaries;
- B: deterministic result paths, result-plus-`complete.json` restoration, and
  validation-before-Trash force replacement;
- C: removed `RunStore.is_complete()`, endpoint-ID reparsing, request-hash
  resume, output scans, and terminal DAG compilation;
- D: no new retry, fallback, compatibility shim, repository identity check,
  source identity gate, memory admission, or speculative exception branch; and
- E: missing completion pairs affect only their task, endpoint, or component,
  while an intact terminal root returns without reopening downstream state.

The paired-fit, voxel, fiber, formal-root, legacy-root, and 3-D scene paths all
use this marker boundary. Fiber projection and publication hashes remain only
inside new-build cache identity or explicit scientific-source verification;
they do not invalidate ordinary resume.

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
