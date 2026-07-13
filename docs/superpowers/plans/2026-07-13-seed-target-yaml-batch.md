# Seed-Target YAML Batch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace explicit seed-target path arguments and hash-named run directories with one schema-version-2 bilateral YAML batch, semantic per-side result directories, shared membership caches, and per-side provenance fingerprints.

**Architecture:** Preserve traversal, membership, and statistics as single-seed primitives. Add a strict batch configuration that resolves shared inputs and named seeds, stage every per-seed artifact set before publication, and commit semantic result directories with rollback and Trash preservation.

**Tech Stack:** Python 3.11, dataclasses, argparse, PyYAML, JSON Schema, NumPy, nibabel, h5py, send2trash, unittest, Conda environment `leaddbs`.

## Global Constraints

- Update the authoritative goal and package documentation before production code.
- Use test-first development and observe each focused test fail for the intended missing behavior.
- Use schema version 2 only for new validation and run interfaces.
- Remove the public `intersection` field while retaining fixed segment-aware traversal internally.
- Accept scientific inputs and publication paths only from YAML.
- Do not add `--resume` or `--force`.
- Publish `output_root/<seed_name>/<run_name>` and store fingerprints in `provenance.json`.
- Move replaced untracked results to platform Trash; never permanently delete them.
- Use Conda environment `leaddbs` and do not push remote changes.

---

### Task 1: Update the authoritative contract before code

**Files:**
- Modify: `my_helper/fiber/seed_target_connectivity_stats_goal.md`
- Modify: `my_helper/fiber/README.md`

**Interfaces:**
- Consumes: `docs/superpowers/specs/2026-07-13-seed-target-yaml-batch-design.md`.
- Produces: an authoritative schema-v2 contract and exact YAML-only commands used by later implementation tasks.

- [ ] **Step 1: Replace the goal's single-seed invocation and version-1 configuration sections**

Document the required top-level objects and the batch public APIs:

```python
validate_batch(config: BatchConnectivityConfig | Path | str) -> BatchValidationReport
compute_seed_target_batch(config: BatchConnectivityConfig | Path | str) -> BatchConnectivityResult
```

Document that `validate_inputs(...)` and `compute_seed_target_statistics(...)` remain internal single-seed primitives.

- [ ] **Step 2: Document the exact CLI and result layout**

Use only:

```bash
seed-target-connectivity validate --config CONFIG
seed-target-connectivity run --config CONFIG
```

Describe `results/lh/<run_name>` and `results/rh/<run_name>`, `provenance.json`, shared `.cache`, semantic replacement, and unchanged `status --run-dir` plus `artifacts --run-dir` inspection.

- [ ] **Step 3: Validate and commit documentation**

Run: `rg -n -- '--target-atlas-root|--seed-roi|--connectome|--output-root|--cache-root|schema_version: 1' my_helper/fiber/seed_target_connectivity_stats_goal.md my_helper/fiber/README.md`

Expected: no current public run example contains a removed flag or schema version 1.

Run: `git diff --check`

Expected: exit 0.

Commit: `docs: define YAML bilateral seed-target runs`

### Task 2: Implement schema version 2 and effective identities

**Files:**
- Modify: `my_helper/fiber/core/seed_target_connectivity/models.py`
- Modify: `my_helper/fiber/core/seed_target_connectivity/config.py`
- Modify: `my_helper/fiber/core/seed_target_connectivity/schemas/config.schema.json`
- Modify: `my_helper/fiber/core/seed_target_connectivity/tests/test_config.py`

**Interfaces:**
- Produces: `InputConfig`, `OutputConfig`, `BatchConnectivityConfig`, `EffectiveConnectivityConfig`, `load_config(path) -> BatchConnectivityConfig`, and `effective_config(batch, seed_name) -> EffectiveConnectivityConfig`.
- Preserves: `SeedConfig`, `TargetConfig`, `ExecutionConfig`, and `RankingConfig` for scientific primitives.

- [ ] **Step 1: Write failing schema-v2 tests**

Cover a complete document, relative-path resolution from the YAML parent, deterministic seed ordering, default cache root, safe path-component validation, duplicate keys, rejected schema version 1, missing required paths, unknown fields, and rejected `intersection`.

Use assertions equivalent to:

```python
batch = load_config(config_path)
self.assertEqual(tuple(batch.inputs.seed_rois), ("lh", "rh"))
self.assertEqual(batch.output.cache_root, batch.output.output_root.parent / ".cache")
self.assertNotIn("intersection", batch.resolved_mapping)
```

- [ ] **Step 2: Write the sibling-independence test**

Resolve `rh` from two batches that differ only in `inputs.seed_rois.lh` and assert:

```python
self.assertNotEqual(first.batch_configuration_hash, second.batch_configuration_hash)
self.assertEqual(
    effective_config(first, "rh").effective_configuration_hash,
    effective_config(second, "rh").effective_configuration_hash,
)
```

- [ ] **Step 3: Run tests and verify RED**

Run: `conda run -n leaddbs python -m unittest my_helper.fiber.core.seed_target_connectivity.tests.test_config -v`

Expected: failures because schema version 2 and batch/effective models do not exist.

- [ ] **Step 4: Implement strict parsing and models**

`BatchConnectivityConfig` contains shared paths/settings, a frozen deterministic seed mapping, `resolved_mapping`, and `batch_configuration_hash`. `EffectiveConnectivityConfig` contains the current seed name/path, shared scientific settings, an effective resolved mapping excluding sibling seeds and publication paths, and `effective_configuration_hash`; expose `configuration_hash` as a compatibility property returning the effective hash.

Resolve absolute paths directly and relative paths against `config_path.parent`. Reject unsafe names with `^[A-Za-z0-9_.-]+$` and reject `.` and `..`.

- [ ] **Step 5: Run focused tests and commit**

Run the command from Step 3.

Expected: all configuration tests pass.

Commit: `feat: add schema v2 seed-target batch config`

### Task 3: Add bilateral validation and YAML-only CLI

**Files:**
- Modify: `my_helper/fiber/core/seed_target_connectivity/models.py`
- Modify: `my_helper/fiber/core/seed_target_connectivity/pipeline.py`
- Modify: `my_helper/fiber/core/seed_target_connectivity/cli.py`
- Modify: `my_helper/fiber/core/seed_target_connectivity/__init__.py`
- Modify: `my_helper/fiber/core/seed_target_connectivity/tests/test_pipeline_cli.py`

**Interfaces:**
- Produces: `BatchValidationReport`, `validate_batch(config)`, and CLI JSON keyed by seed name.
- Consumes: `load_config`, `effective_config`, existing `resolve_seed`, `resolve_atlas`, and `open_connectome`.

- [ ] **Step 1: Write failing batch-validation tests**

Build a fixture YAML with two different seed masks and assert one call returns ordered `lh` and `rh` reports, identical target/connectome identities, and no connectome iteration during validation.

```python
report = validate_batch(config_path, connectome_override=adapter)
self.assertEqual(tuple(report.seeds), ("lh", "rh"))
self.assertEqual(adapter.iteration_count, 0)
```

The optional adapter override is test-only/programmatic and is not exposed by the CLI.

- [ ] **Step 2: Write failing CLI contract tests**

Assert `validate --config CONFIG` succeeds and removed path flags fail argparse parsing. Assert neither `--resume` nor `--force` appears in `run --help`.

- [ ] **Step 3: Run tests and verify RED**

Run: `conda run -n leaddbs python -m unittest my_helper.fiber.core.seed_target_connectivity.tests.test_pipeline_cli -v`

Expected: failures because the CLI still requires explicit path arguments and batch validation is absent.

- [ ] **Step 4: Implement batch validation and CLI parsing**

Keep the existing single-seed `validate_inputs(...)` helper but require an `EffectiveConnectivityConfig`. Implement `validate_batch(...)` by opening the shared connectome once, resolving the target atlas once through `ResolutionCache`, and resolving every named seed in sorted order.

For `validate` and `run`, argparse accepts only `--config`. Preserve `status --run-dir` and `artifacts --run-dir`.

- [ ] **Step 5: Run focused tests and commit**

Run the command from Step 3.

Expected: batch validation and CLI contract tests pass.

Commit: `feat: validate bilateral seed-target YAML batches`

### Task 4: Stage semantic artifacts with version-2 provenance

**Files:**
- Modify: `my_helper/fiber/core/seed_target_connectivity/artifacts.py`
- Modify: `my_helper/fiber/core/seed_target_connectivity/models.py`
- Modify: `my_helper/fiber/core/seed_target_connectivity/tests/test_artifacts.py`

**Interfaces:**
- Produces: `stage_run_artifacts(...) -> StagedRunArtifacts`, `verify_run_artifacts(run_dir)`, `publish_staged_batch(staged_runs, trash=send2trash) -> Mapping[str, RunArtifacts]`.
- Preserves: legacy `analysis_manifest.json` verification for `status` and `artifacts`.

- [ ] **Step 1: Write failing provenance and semantic-path tests**

Assert a staged side contains the exact nine-file version-2 set with `provenance.json`, no `analysis_manifest.json`, and provenance fields:

```python
self.assertEqual(provenance["batch_configuration_hash"], batch.batch_configuration_hash)
self.assertEqual(provenance["effective_configuration_hash"], effective.configuration_hash)
self.assertEqual(provenance["run_fingerprint"], staged.run_fingerprint)
```

Assert the final path is `output_root / seed_name / run_name` and does not include the fingerprint.

- [ ] **Step 2: Write failing reuse, refusal, rollback, and legacy tests**

Cover matching valid-result reuse, refusal to replace an unrelated directory without a provenance marker, legacy `analysis_manifest.json` inspection, both-side staging before replacement, rollback after an injected second-side rename failure, and injected Trash calls for replaced prior results.

- [ ] **Step 3: Run tests and verify RED**

Run: `conda run -n leaddbs python -m unittest my_helper.fiber.core.seed_target_connectivity.tests.test_artifacts -v`

Expected: failures because semantic staging, version-2 provenance, and batch publication do not exist.

- [ ] **Step 4: Separate staging from publication**

Refactor primary artifact writing without changing CSV/NPY/NPZ contents. Compute the per-side fingerprint from effective identity, write `provenance.json`, index every artifact except `artifact_index.csv`, and verify the staged directory before returning it.

Implement publication as two phases: rename existing tool-owned finals to sibling rollback names, rename all staged directories to finals, verify all finals, then call `send2trash` on rollback directories. On any failure, move newly published finals back to staging names and restore every rollback directory.

- [ ] **Step 5: Run focused tests and commit**

Run the command from Step 3.

Expected: all artifact and rollback tests pass, including legacy inspection.

Commit: `feat: publish semantic seed-target provenance`

### Task 5: Compute and publish one bilateral batch

**Files:**
- Modify: `my_helper/fiber/core/seed_target_connectivity/pipeline.py`
- Modify: `my_helper/fiber/core/seed_target_connectivity/cli.py`
- Modify: `my_helper/fiber/core/seed_target_connectivity/models.py`
- Modify: `my_helper/fiber/core/seed_target_connectivity/__init__.py`
- Modify: `my_helper/fiber/core/seed_target_connectivity/tests/test_pipeline_cli.py`
- Modify: `my_helper/fiber/core/seed_target_connectivity/acceptance.py`

**Interfaces:**
- Produces: `compute_seed_target_batch(config) -> BatchConnectivityResult`.
- Consumes: `validate_batch`, `compute_memberships`, `compute_statistics`, `stage_run_artifacts`, and `publish_staged_batch`.

- [ ] **Step 1: Write failing bilateral execution tests**

Assert one batch run returns ordered `lh` and `rh` results, writes both semantic directories, uses the target cache on the second seed, and a second identical batch reports both results as reused.

- [ ] **Step 2: Write the all-or-nothing computation test**

Inject a failure while computing the second seed and assert neither new semantic result directory is published.

- [ ] **Step 3: Run tests and verify RED**

Run: `conda run -n leaddbs python -m unittest my_helper.fiber.core.seed_target_connectivity.tests.test_pipeline_cli -v`

Expected: failures because `compute_seed_target_batch` and batch run JSON are absent.

- [ ] **Step 4: Implement batch computation**

Validate shared inputs once, compute every seed's membership/statistics before publishing, stage changed results, preserve matching valid results as reuse candidates, then publish all staged results together. Return one `BatchConnectivityResult` mapping seed names to the existing per-seed `ConnectivityRunResult` shape.

Update the acceptance runner to construct effective single-seed configurations from its explicit fixture without reintroducing version-1 public CLI behavior.

- [ ] **Step 5: Run focused and full suites, then commit**

Run:

```bash
conda run -n leaddbs python -m unittest \
  my_helper.fiber.core.seed_target_connectivity.tests.test_pipeline_cli \
  my_helper.fiber.core.seed_target_connectivity.tests.test_engine_statistics \
  my_helper.fiber.core.seed_target_connectivity.tests.test_artifacts -v
```

Then run:

```bash
conda run -n leaddbs python -m unittest discover \
  -s my_helper/fiber/core/seed_target_connectivity/tests -v
```

Expected: all non-opt-in tests pass and the real-data acceptance test remains skipped unless explicitly enabled.

Commit: `feat: run bilateral seed-target YAML batches`

### Task 6: Install the real configuration and verify end to end

**Files:**
- Create or move outside Git: `/Volumes/VAL/STNSNr/summary/individual_connectome_fiber/seed_target_connectivity/configs/seed_target_dtor.yaml`
- Generate outside Git: `/Volumes/VAL/STNSNr/summary/individual_connectome_fiber/seed_target_connectivity/results/lh/dTOR__HybraPD__STNSNrplus/`
- Generate outside Git: `/Volumes/VAL/STNSNr/summary/individual_connectome_fiber/seed_target_connectivity/results/rh/dTOR__HybraPD__STNSNrplus/`
- Modify: `my_helper/fiber/seed_target_connectivity_stats_goal.md`
- Modify: `my_helper/fiber/README.md`

**Interfaces:**
- Consumes: the schema-v2 CLI and the existing dTOR/HybraPD/STNSNrplus inputs.
- Produces: one validated real bilateral configuration and current semantic result directories.

- [ ] **Step 1: Move the existing external YAML into `configs` and replace its contents**

Preserve the existing untracked file by moving it, then write the exact schema-v2 configuration from the approved design. Do not retain the old root-level config file.

- [ ] **Step 2: Validate without full traversal**

Run:

```bash
conda run -n leaddbs python \
  my_helper/fiber/pipelines/seed-target-connectivity validate \
  --config /Volumes/VAL/STNSNr/summary/individual_connectome_fiber/seed_target_connectivity/configs/seed_target_dtor.yaml
```

Expected: both `lh` and `rh` validate against 150 HybraPD targets and the dTOR connectome without iterating fibers.

- [ ] **Step 3: Run the bilateral real analysis**

Run the same CLI with `run`, monitor the full traversal, and require both semantic result directories to pass artifact verification before treating the run as complete.

- [ ] **Step 4: Preserve obsolete legacy output**

After both new results verify, move the old external `dtor_stnsnrplus` legacy tree to Trash. Do not remove it before successful publication.

- [ ] **Step 5: Record verified evidence and run final checks**

Update documentation with actual result paths, per-side fingerprints, target counts, seed-fiber counts, target-cache reuse, and artifact counts.

Run:

```bash
conda run -n leaddbs python -m compileall -q my_helper/fiber/core/seed_target_connectivity
conda run -n leaddbs python -m unittest discover -s my_helper/fiber/core/seed_target_connectivity/tests -v
git diff --check
git status --short --branch
```

Expected: compilation and tests pass, documentation matches real outputs, and the worktree is clean after the final commit.

Commit: `docs: record bilateral seed-target acceptance`
