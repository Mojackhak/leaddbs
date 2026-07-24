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
| Cold/warm performance and scheduler acceptance | PENDING | Persistent spawned scheduling, global CPU/memory/I/O/solver ledgers, parent-only state mutation, process-local cache verification, vectorized kernels, and deterministic RNG boundaries pass static tests. The repository-owned cumulative-CPU probe, five-second in-memory scheduler-window publication, exact 72-row matrix validator, source-evidence binding, deterministic report, worker/default decision, RSS/swap gates, and utilization-window gate are implemented. The 44 focused tests and complete 613-test discovery pass. No configured benchmark matrix has run. | Run cold and warm configured benchmarks at workers 1, 3, 6, and 12 for voxel, every connectome, formal, bootstrap, jitter, and pPAM. Record wall and CPU time, effective cores, runnable/admission windows, queue and token occupancy, I/O classification, cache verification counts, pool generations, nested pools, hot-loop metadata work, copies, bytes, RSS, and swap. Apply every quantitative Step 10 gate without substituting skipped rows. |
| Corruption, fail-once recovery, and deletion-rebuild acceptance | PENDING | Static cache, resume, checkpoint, and rebuild fixtures reject payload, shard, axis, and result corruption and selectively rerun affected descendants. Step 10 now freezes a repository-owned, marker-bound, isolated-root harness that treats the accepted parent, canonical publication, and shared production cache as read-only and quarantines every replaced isolated file. The harness and required production-scale sequence have not completed. | Implement and test the frozen fault-plan/report schemas and safety checks. In a marked isolated acceptance root, inject each declared corruption, prove failure before scientific consumption, run fail-once recovery so dependency-derived descendants execute, and prove a missing required parent artifact invokes rebuild into a new main lineage without mutating the accepted parent. Compare rebuilt extension outputs with one-shot outputs under the frozen tolerances. |
| Independent spatial jitter computation | ACCEPTED | `task17-jitter-v8-support-preserving-formal-20260719` completed its support-preserving block and endpoint closure with no terminal failure. Jitter compilation, selective block resume, cache-first dispatch, and extension publication boundaries pass 25 focused tests with temporary fixtures. | Reopen the completed child manifest, block closure, endpoint closure, artifact index, and parent binding during final audit. |
| Canonical independent jitter-v2 publication | PENDING | The completed jitter child was replayed twice into self-contained v2 extensions in both public domains. The identical replay preserved both terminal publications and their source/parent bindings. | After independent OSS releases shared VAL bandwidth, run the frozen repository-owned publication validator across both roots and retain its atomic acceptance document. |
| Independent OSS axis equivalence and pPAM | ACTIVE | `task17-oss-v1-inclusive-formal-20260719` is running through guarded `segment_0014` with a 750-fiber execution bound. The first new add-on decision, `8c8614c12b2155a4b71232fd146feeb4657f1fdff71ed63bd8c6b9c699539991`, passed with zero probability, state, and activation-count mismatch. Peak task-tree RSS so far is 46507081728 bytes and swap has not increased. | Finish the authoritative add-on `row_decision_ids` closure, rerun all 392 dependency-derived downstream tasks, require zero terminal failures, and validate reporting, artifact index, and resources. |
| Canonical independent OSS-v2 publication | PENDING | Self-contained extension-v2 publisher and validator fixtures pass. The source OSS child is not terminal. | Publish twice without filters, validate the normative-fiber OSS-v2 root, and audit source/parent bindings plus forbidden paths. |
| Cache-first combined jitter and OSS replay | PENDING | Compiler, executor, physical jitter, and OSS decision fixtures prove cache-first behavior and fail before a producer call on a miss without authorization. | Start the frozen combined child without `--allow-expensive-producers`, attach the checked-in guard, and require complete cache reuse plus terminal DAG closure. |
| Canonical combined-v2 publication | PENDING | Publisher and validator fixtures cover both public domains. No terminal combined child exists. | Publish twice, validate both domain roots, and audit complete jitter plus normative-fiber OSS scope. |
| Resume and copied-cache implementation | ACCEPTED | Resume fixtures use input JSON/YAML identities and complete result JSON records, ignore repository code identity, selectively rerun missing blocks and consumers, and reuse a directly copied cache under a different path. | Recheck these fail-closed static contracts after the last implementation change. |
| Production identical resume acceptance | PENDING | The main and completed jitter lineages preserve resumable state, and the active OSS lineage has repeatedly restored its immutable plan and completed predecessors without invalidating scientific products after code-only changes. The complete terminal-child identical replay has not yet run. | After each production child becomes terminal, run its exact resume path, prove no accepted payload was rewritten, and retain the task-outcome and manifest evidence. |
| Resource scheduling and guard contract | ACTIVE | One persistent spawn pool, 14-worker ceiling, single solver token, 48-GiB admission charge, task-tree RSS `< 64 GiB`, and swap growth `< 1` byte are implemented and covered by static tests. Segment 0014 is currently guarded. | Build the repository-owned maximum-row measurement window from the terminal segment and pass the independent resource validator. Repeat strict acceptance for combined. |
| Display smoothing v2 publication | PENDING | `/private/tmp/task17-display-smoothing-v2-stage.zAofAX` contains 112 NIfTI replacements and 112 metadata records. All preserve exact raw finite support, all staged hashes and sizes match, and the repair-manifest SHA-256 is `dff3ab60616b2bd9d77075bc6781f6ef928db666f1052ac31d5f02f4088f6b5c`. | After OSS exits, validate, promote through the repository transaction into the canonical direct-voxel publication, archive replaced untracked files in the declared VAL Trash root, and validate again. |
| Formal paired-fit, voxel 2-D, and fiber 2-D output | PENDING | The durable request resolves 28 scales, 112 endpoints, canonical public inputs, and all three batch components in read-only preflight. The 37-test visualization suite and 30-test publication suite pass with temporary fixtures. | Render the formal output, repeat without force, verify no completed component rewrite, run `--validate-output` twice, and visually inspect representative outputs. |
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

## Repository Entrypoint Preflight

The following repository-owned entrypoints parse successfully in Conda
`leaddbs` with caller `PYTHONPATH` removed:

- `run_dual_frequency_models.py`;
- `validate_task17_connectome_parity_fixture.py`;
- `build_task17_preinstrumentation_windows.py`;
- `validate_task17_preinstrumentation_resources.py`;
- `validate_task17_resource_acceptance.py`;
- `validate_task17_extension_publication.py`;
- `repair_task17_display_smoothing_publication.py`; and
- `my_helper.fiber.core.viz.formal_postprocess`.

The generic runner exposes the required `run`, `sensitivity --resume`, and
`sensitivity --rebuild --rebuild-run-id` operations. However, no dedicated
repository entrypoint now aggregates and validates the complete
workers-1/3/6/12 cold/warm performance matrix, but that configured matrix has
not run. No dedicated production fault harness yet owns the isolated
corruption plus deletion-rebuild sequence. Those execution and implementation
gaps remain part of their `PENDING` ledger rows. The existence of generic
runner flags or lower-level telemetry cannot close them.

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
