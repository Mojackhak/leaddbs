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
| Independent spatial jitter | ACCEPTED | `task17-jitter-v8-support-preserving-formal-20260719` completed and was replayed into self-contained canonical jitter-v2 extensions in both domains. Identical replay preserved the terminal publication. | Run the frozen independent publication validator after OSS releases shared VAL bandwidth. |
| Independent OSS axis equivalence and pPAM | ACTIVE | `task17-oss-v1-inclusive-formal-20260719` is running through guarded `segment_0014` with a 750-fiber execution bound. The first new add-on decision, `8c8614c12b2155a4b71232fd146feeb4657f1fdff71ed63bd8c6b9c699539991`, passed with zero probability, state, and activation-count mismatch. Peak task-tree RSS so far is 46507081728 bytes and swap has not increased. | Finish the authoritative add-on `row_decision_ids` closure, rerun all 392 dependency-derived downstream tasks, require zero terminal failures, and validate reporting, artifact index, and resources. |
| Canonical independent OSS-v2 publication | PENDING | Self-contained extension-v2 publisher and validator fixtures pass. The source OSS child is not terminal. | Publish twice without filters, validate the normative-fiber OSS-v2 root, and audit source/parent bindings plus forbidden paths. |
| Cache-first combined jitter and OSS replay | PENDING | Compiler, executor, physical jitter, and OSS decision fixtures prove cache-first behavior and fail before a producer call on a miss without authorization. | Start the frozen combined child without `--allow-expensive-producers`, attach the checked-in guard, and require complete cache reuse plus terminal DAG closure. |
| Canonical combined-v2 publication | PENDING | Publisher and validator fixtures cover both public domains. No terminal combined child exists. | Publish twice, validate both domain roots, and audit complete jitter plus normative-fiber OSS scope. |
| Resume and copied-cache portability | ACCEPTED | Resume fixtures use input JSON/YAML identities and complete result JSON records, ignore repository code identity, selectively rerun missing blocks and consumers, and reuse a directly copied cache under a different path. | Perform one production identical resume after terminal child completion and retain the resulting manifest evidence. |
| Resource scheduling and guard contract | ACTIVE | One persistent spawn pool, 14-worker ceiling, single solver token, 48-GiB admission charge, task-tree RSS `< 64 GiB`, and swap growth `< 1` byte are implemented and covered by static tests. Segment 0014 is currently guarded. | Build the repository-owned maximum-row measurement window from the terminal segment and pass the independent resource validator. Repeat strict acceptance for combined. |
| Display smoothing v2 publication | PENDING | `/private/tmp/task17-display-smoothing-v2-stage.zAofAX` contains 112 NIfTI replacements and 112 metadata records. All preserve exact raw finite support, all staged hashes and sizes match, and the repair-manifest SHA-256 is `dff3ab60616b2bd9d77075bc6781f6ef928db666f1052ac31d5f02f4088f6b5c`. | After OSS exits, validate, promote through the repository transaction into the canonical direct-voxel publication, archive replaced untracked files in the declared VAL Trash root, and validate again. |
| Formal paired-fit, voxel 2-D, and fiber 2-D output | PENDING | The durable request resolves 28 scales, 112 endpoints, canonical public inputs, and all three batch components in read-only preflight. The 37-test visualization suite and 30-test publication suite pass with temporary fixtures. | Render the formal output, repeat without force, verify no completed component rewrite, run `--validate-output` twice, and visually inspect representative outputs. |
| Interactive voxel and fiber 3-D scenes | ACCEPTED | The two PDQ-39 MATLAB examples resolve only canonical publications, request 0.5-mm inward voxel sampling, use signed `vik` mappings and independent colorbars, preserve grayscale anatomy, and create no export unless explicitly requested. | Reopen both examples after final publication validation for the final sampled visual review. |
| Cleanup policy and later sensitivity capability | ACCEPTED | Production `delete_run_cache_on_success` is false. Failed or partial runs are never cleanup-eligible, and shared scientific cache is outside the cleanup boundary. | Confirm no cleanup marker or missing cache entry before the no-expensive combined replay. |
| Final three-plan requirement audit | PENDING | This ledger names the production gates and authoritative evidence required for closure. | Reopen every named manifest, validator result, output root, and visual sample; update all rows to `ACCEPTED` only when direct evidence is terminal. |

## Final Closure Rule

The complete goal remains open while any row is `ACTIVE`, `PENDING`, or
`BLOCKED`. In particular, the following sequence cannot be skipped:

1. terminal independent OSS and downstream pPAM closure;
2. configured-data shared-preparation parity replay and independent OSS
   resource acceptance;
3. canonical OSS-v2 replay;
4. no-authorization combined execution and resource acceptance;
5. canonical combined-v2 replay;
6. display-smoothing promotion and canonical revalidation;
7. formal 112-endpoint postprocess, identical resume, independent validation,
   and sampled visual review; and
8. requirement-by-requirement reinspection of all three source plans.
