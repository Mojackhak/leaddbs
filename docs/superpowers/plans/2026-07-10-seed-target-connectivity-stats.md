# Generic Seed-Target Connectivity Statistics Implementation Plan

> **For agentic workers:** Execute this plan task-by-task in the current session. Every production change requires a failing `unittest` first, and every command runs in `/opt/anaconda3/envs/leaddbs/bin/python`.

**Goal:** Build a project-independent Python API and CLI that computes deterministic seed-to-target streamline statistics, immutable caches, and provenance artifacts for arbitrary Lead-DBS target atlases and stable-ID connectomes.

**Architecture:** A typed orchestration layer resolves strict YAML configuration, atlas masks, and one connectome adapter. Independent seed and target membership identities feed a Numba-accelerated sparse-voxel traversal engine, while a deliberately slow reference kernel proves geometry on synthetic and sampled real fibers. A content-addressed atomic run store serializes statistics, caches, QC, and provenance without project-specific logic.

**Tech Stack:** Python 3 in Conda `leaddbs`, standard-library `unittest`/`argparse`/`dataclasses`, NumPy, SciPy sparse containers, h5py, nibabel, PyYAML, jsonschema, and Numba.

## Global Constraints

- The reusable core accepts exactly three scientific data inputs: one target-atlas directory, one seed NIfTI, and one stable-ID streamline connectome.
- Core code contains no project, anatomy, VTA, frequency, clinical-scale, outcome-model, hemisphere, or target-selection policy.
- All Python code, tests, comments, docstrings, identifiers, and CLI help are English.
- All commands run with `/opt/anaconda3/envs/leaddbs/bin/python`.
- Configuration rejects unknown fields and provides no project-specific defaults.
- Streamline traversal is bounded by `execution.fiber_chunk_size` and never loads the 11 GB dTOR connectome at once.
- Documentation is updated and committed before production code in each implementation phase.
- No remote repository mutation is authorized.

---

### Task 1: Strict Configuration And Typed Contracts

**Files:**
- Create: `my_helper/fiber/core/seed_target_connectivity/__init__.py`
- Create: `my_helper/fiber/core/seed_target_connectivity/errors.py`
- Create: `my_helper/fiber/core/seed_target_connectivity/models.py`
- Create: `my_helper/fiber/core/seed_target_connectivity/config.py`
- Create: `my_helper/fiber/core/seed_target_connectivity/schemas/config.schema.json`
- Create: `my_helper/fiber/core/seed_target_connectivity/tests/__init__.py`
- Create: `my_helper/fiber/core/seed_target_connectivity/tests/test_config.py`
- Modify: `my_helper/fiber/README.md`

**Interfaces:**
- Produces: `ConnectivityConfig`, `SeedConfig`, `TargetConfig`, `ExecutionConfig`, `RankingConfig`, `load_config(path)`, `resolve_config(mapping)`, and shared domain exceptions.
- Consumes: no earlier task interfaces.

- [ ] **Step 1: Document the public Python/CLI package boundary in the fiber README.**

Add the package path, the conceptual `compute_seed_target_statistics(...)` API,
the four CLI subcommands, and the Conda `leaddbs` invocation. Commit this
documentation before creating production Python modules.

- [ ] **Step 2: Write failing strict-configuration tests.**

```python
class ConfigTests(unittest.TestCase):
    def test_rejects_unknown_fields(self) -> None:
        with self.assertRaisesRegex(ConfigurationError, "Additional properties"):
            resolve_config({"schema_version": 1, "unknown": True})

    def test_requires_probability_thresholds_only_when_used(self) -> None:
        config = resolve_config({"schema_version": 1})
        self.assertIsNone(config.seed.probability_threshold)
        self.assertIsNone(config.targets.probability_threshold)

    def test_rejects_invalid_chunk_size_and_threshold(self) -> None:
        with self.assertRaises(ConfigurationError):
            resolve_config({"schema_version": 1, "execution": {"fiber_chunk_size": 0}})
        with self.assertRaises(ConfigurationError):
            resolve_config({"schema_version": 1, "seed": {"probability_threshold": 0.0}})
```

- [ ] **Step 3: Run RED.**

Run:

```bash
/opt/anaconda3/envs/leaddbs/bin/python -m unittest \
  my_helper.fiber.core.seed_target_connectivity.tests.test_config -v
```

Expected: `ModuleNotFoundError` for `seed_target_connectivity.config`.

- [ ] **Step 4: Implement frozen contracts and JSON-Schema validation.**

Use a duplicate-key-safe `yaml.SafeLoader`, Draft 2020-12 JSON Schema with
`additionalProperties: false` at every object level, and immutable dataclasses.
The only defaults are algorithmic: segment-aware traversal, chunk size 100000,
membership caching enabled, and ranking enabled. Thresholds remain absent unless
explicitly configured.

- [ ] **Step 5: Run GREEN and commit.**

Run the Task 1 module and expect all tests to pass, then commit documentation,
schema, contracts, loader, and tests together.

---

### Task 2: Atlas Discovery, ROI Resolution, And Mask Identity

**Files:**
- Create: `my_helper/fiber/core/seed_target_connectivity/identity.py`
- Create: `my_helper/fiber/core/seed_target_connectivity/atlas.py`
- Create: `my_helper/fiber/core/seed_target_connectivity/roi.py`
- Create: `my_helper/fiber/core/seed_target_connectivity/tests/helpers.py`
- Create: `my_helper/fiber/core/seed_target_connectivity/tests/test_atlas_roi.py`
- Modify: `my_helper/fiber/seed_target_connectivity_stats_goal.md`

**Interfaces:**
- Consumes: `ConnectivityConfig`, `ConfigurationError`.
- Produces: `TargetSource`, `ResolvedMask`, `ResolvedAtlas`, `discover_targets(root)`, `resolve_seed(path, config)`, `resolve_atlas(root, config)`, `sha256_file(path)`, and `canonical_hash(value)`.

- [ ] **Step 1: Update goal progress before ROI production code.**

Record Task 1 completion and Task 2 start without changing scientific scope.

- [ ] **Step 2: Write failing discovery and ROI tests.**

```python
def test_discovers_only_nonroot_visible_niftis(self) -> None:
    write_mask(self.root / "root_helper.nii.gz", np.ones((2, 2, 2)))
    write_mask(self.root / "group_a" / "region.nii.gz", np.ones((2, 2, 2)))
    write_mask(self.root / "group_b" / "region.nii", np.ones((2, 2, 2)))
    write_mask(self.root / ".hidden" / "secret.nii.gz", np.ones((2, 2, 2)))
    (self.root / "group_a" / "._copy.nii.gz").write_bytes(b"ignored")
    targets = discover_targets(self.root)
    self.assertEqual([item.target_id for item in targets], ["group_a/region", "group_b/region"])

def test_probabilistic_mask_requires_threshold_and_hashes_resolution(self) -> None:
    path = write_mask(self.root / "seed.nii.gz", np.array([[[0.0, 0.4, 0.8]]]))
    with self.assertRaises(ConfigurationError):
        resolve_seed(path, resolve_config({"schema_version": 1}))
    resolved = resolve_seed(path, resolve_config({"schema_version": 1, "seed": {"probability_threshold": 0.5}}))
    self.assertEqual(resolved.voxel_count, 1)
    self.assertEqual(resolved.threshold_source, "seed.probability_threshold")
```

Also cover nested directories, root-level NIfTI exclusion, AppleDouble (`._`)
exclusion, symlink cycles, malformed NIfTI failure,
nonfinite/out-of-range values, numeric tolerance for binary values, per-target
override precedence, target default precedence, physical volume, duplicate
basenames, empty-after-threshold status, and stable source/resolved hashes.

- [ ] **Step 3: Run RED.**

Expected: missing `atlas` and `roi` modules.

- [ ] **Step 4: Implement deterministic discovery and sparse resolved masks.**

Store sorted flat voxel indices rather than retaining every dense atlas image.
Normalize target IDs with POSIX relative paths and strip the full `.nii` or
`.nii.gz` suffix. Classify binary data when every finite nonzero value is within
`1e-6` absolute tolerance of one. Reject negative, greater-than-one, NaN, or
infinite probabilistic data. Record affine, shape, voxel volume, threshold
source, source hash, voxel count, physical volume, and resolved-mask hash.

- [ ] **Step 5: Run GREEN and commit.**

Run both Task 1 and Task 2 tests and expect all tests to pass.

---

### Task 3: Generic Connectome Adapter And Lead-DBS HDF5 Adapter

**Files:**
- Create: `my_helper/fiber/core/seed_target_connectivity/connectome.py`
- Create: `my_helper/fiber/core/seed_target_connectivity/tests/test_connectome.py`
- Modify: `my_helper/fiber/seed_target_connectivity_stats_goal.md`

**Interfaces:**
- Consumes: `sha256_file`, `canonical_hash`, shared exceptions.
- Produces: `FiberChunk`, `ConnectomeMetadata`, `ConnectomeAdapter` protocol, `LeadDBSHDF5Connectome`, and `open_connectome(path)`.

- [ ] **Step 1: Record the adapter phase in the goal document.**

- [ ] **Step 2: Write failing synthetic HDF5 adapter tests.**

```python
def test_hdf5_adapter_preserves_canonical_ids_across_chunks(self) -> None:
    path = write_hdf5_connectome(
        self.root / "data.mat",
        [line((0, 0, 0), (1, 0, 0)), line((0, 1, 0), (1, 1, 0)), line((0, 2, 0), (1, 2, 0))],
    )
    adapter = LeadDBSHDF5Connectome(path)
    chunks = list(adapter.iter_chunks(2))
    self.assertEqual(chunks[0].fiber_ids.tolist(), [1, 2])
    self.assertEqual(chunks[1].fiber_ids.tolist(), [3])
    self.assertEqual(adapter.metadata.n_valid_fibers, 3)

def test_hdf5_adapter_rejects_mismatched_fourth_row_ids(self) -> None:
    path = write_hdf5_connectome(self.root / "bad.mat", [line((0, 0, 0), (1, 0, 0))])
    mutate_fourth_row(path, value=99)
    with self.assertRaisesRegex(ConnectomeError, "canonical fiber ID"):
        list(LeadDBSHDF5Connectome(path).iter_chunks(1))
```

Cover duplicate/reordered IDs, nonfinite coordinates, `idx`/point-count
mismatch, fibers shorter than two points, deterministic metadata, source-file
SHA-256, geometry identity, and ordered-ID hash.

- [ ] **Step 3: Run RED.**

Expected: missing `connectome` module.

- [ ] **Step 4: Implement the protocol and HDF5 adapter.**

Load the 11.8M `idx` lengths as one bounded int64 vector, derive cumulative
point offsets, and slice only one fiber block from `fibers` at a time. The
adapter explicitly establishes one-based `idx` position as canonical ID and
validates `fibers[3, :]` for every yielded point. Invalid streamlines fail
validation rather than silently changing `N_all`.

- [ ] **Step 5: Run GREEN and commit.**

---

### Task 4: Reference And Numba Segment-Aware Voxel Traversal

**Files:**
- Create: `my_helper/fiber/core/seed_target_connectivity/traversal.py`
- Create: `my_helper/fiber/core/seed_target_connectivity/tests/test_traversal.py`
- Modify: `my_helper/fiber/seed_target_connectivity_stats_goal.md`

**Interfaces:**
- Consumes: `FiberChunk`, `ResolvedMask`.
- Produces: `SparseVoxelLookup`, `build_sparse_lookup(masks)`, `reference_membership(streamlines, masks)`, and `optimized_membership(chunk, lookup)`.

- [ ] **Step 1: Document the half-open voxel-cell boundary convention.**

Define voxel `i` as the half-open cell `[i - 0.5, i + 0.5)` in each dimension,
with the segment endpoint included. This removes grid-plane ambiguity and is
used identically by the reference and optimized kernels.

- [ ] **Step 2: Write failing geometry tests.**

```python
def test_detects_crossing_when_vertices_are_outside(self) -> None:
    mask = resolved_mask(voxels=[(1, 1, 1)], shape=(3, 3, 3))
    fiber = np.array([[-1.0, 1.0, 1.0], [3.0, 1.0, 1.0]])
    self.assertTrue(reference_membership([fiber], [mask])[0, 0])
    self.assertTrue(optimized_membership(chunk([fiber]), build_sparse_lookup([mask]))[0, 0])

def test_rejects_near_miss(self) -> None:
    mask = resolved_mask(voxels=[(1, 1, 1)], shape=(3, 3, 3))
    fiber = np.array([[-1.0, 1.51, 1.0], [3.0, 1.51, 1.0]])
    self.assertFalse(reference_membership([fiber], [mask])[0, 0])

def test_overlapping_targets_are_independent(self) -> None:
    first = resolved_mask(voxels=[(1, 1, 1)], shape=(3, 3, 3), target_id="a")
    second = resolved_mask(voxels=[(1, 1, 1)], shape=(3, 3, 3), target_id="b")
    result = optimized_membership(chunk([crossing_fiber()]), build_sparse_lookup([first, second]))
    self.assertEqual(result.tolist(), [[True, True]])
```

Add randomized affine/segment fixtures comparing every bit from the brute-force
segment/AABB reference kernel with the optimized DDA kernel, including zero-
length segments, negative voxel coordinates, endpoints on boundaries, multiple
grid geometries, and chunk splits.

- [ ] **Step 3: Run RED.**

Expected: missing traversal functions.

- [ ] **Step 4: Implement independent kernels.**

The reference kernel tests a segment against occupied voxel boxes using the slab
method. The optimized kernel transforms points with inverse affine, applies a
Numba 3D DDA, binary-searches sorted occupied flat voxel keys, and ORs packed
uint64 target words. Group masks by exact shape/affine identity so differing
valid grids remain supported. Reject ROI dilation and original-vertex-only
shortcuts.

- [ ] **Step 5: Run GREEN, benchmark a synthetic million-segment fixture, and commit.**

The benchmark is diagnostic, not a timing assertion; it must demonstrate
bounded memory and Numba compilation before real acceptance.

---

### Task 5: Membership Engine, Independent Cache Reuse, Statistics, And Ranking

**Files:**
- Create: `my_helper/fiber/core/seed_target_connectivity/cache.py`
- Create: `my_helper/fiber/core/seed_target_connectivity/statistics.py`
- Create: `my_helper/fiber/core/seed_target_connectivity/engine.py`
- Create: `my_helper/fiber/core/seed_target_connectivity/tests/test_engine_statistics.py`
- Modify: `my_helper/fiber/seed_target_connectivity_stats_goal.md`

**Interfaces:**
- Consumes: adapter chunks, seed/target lookups, config, canonical identities.
- Produces: `MembershipResult`, `TargetStatistic`, `compute_memberships(...)`, `compute_statistics(...)`, `rank_statistics(...)`, and cache load/write functions.

- [ ] **Step 1: Update the goal with the cache/statistics phase.**

- [ ] **Step 2: Write failing hand-calculated statistics tests.**

```python
def test_five_statistics_match_hand_calculation(self) -> None:
    seed = np.array([True, True, False, False])
    targets = np.array([[True, False], [True, True], [False, True], [False, False]])
    rows = compute_statistics(seed, targets, target_records("a", "b"))
    self.assertEqual(rows[0].raw_fiber_count, 2)
    self.assertEqual(rows[0].seed_normalized_fraction, 1.0)
    self.assertEqual(rows[0].target_background_prevalence, 0.5)
    self.assertEqual(rows[0].connectivity_lift, 2.0)
    self.assertEqual(rows[0].connectivity_pmi, 1.0)

def test_zero_semantics_are_explicit(self) -> None:
    with self.assertRaisesRegex(StatisticsError, "seed"):
        compute_statistics(np.zeros(3, dtype=bool), np.zeros((3, 1), dtype=bool), target_records("a"))
    no_background = compute_statistics(np.array([True, False]), np.zeros((2, 1), dtype=bool), target_records("a"))[0]
    self.assertEqual(no_background.target_status, "no_connectome_support")
    self.assertIsNone(no_background.connectivity_lift)
```

Also test zero joint membership (`lift == 0`, PMI status `negative_infinity` but
no nonfinite serialized number), empty-after-threshold exclusion, exact ranking
tie breakers, non-estimable rows last, overlapping target fractions not summing
to one, identical results across chunk sizes, duplicate IDs, and cache identity
reuse for changed seed versus changed atlas.

- [ ] **Step 3: Run RED.**

- [ ] **Step 4: Implement membership and cache storage.**

Persist seed IDs as sorted int64 NPY. Persist target membership as compressed
CSR-style NPZ fields `target_ids`, `indptr`, and `fiber_ids`, preserving
canonical IDs without a dense 11.8M-by-106 matrix. Seed cache identity binds
connectome geometry, ordered IDs, seed mask, method, and algorithm version;
target cache identity substitutes the resolved atlas identity. When both caches
are absent, traverse chunks once per required grid lookup and accumulate bounded
per-target ID arrays.

- [ ] **Step 5: Implement exact statistics/ranking and run GREEN.**

Use integer counts for all denominators and Python floats only at serialization.
Represent non-estimable and negative-infinity semantics with status fields and
empty numeric CSV cells/JSON null, never NaN or Infinity.

- [ ] **Step 6: Commit.**

---

### Task 6: Atomic Immutable Run Store And Provenance Artifacts

**Files:**
- Create: `my_helper/fiber/core/seed_target_connectivity/artifacts.py`
- Create: `my_helper/fiber/core/seed_target_connectivity/tests/test_artifacts.py`
- Modify: `my_helper/fiber/seed_target_connectivity_stats_goal.md`

**Interfaces:**
- Consumes: resolved config/atlas/seed/connectome metadata, memberships, statistics.
- Produces: `RunArtifacts`, `write_run_atomic(...)`, `inspect_status(run_dir)`, and `list_artifacts(run_dir)`.

- [ ] **Step 1: Record the artifact phase in the goal.**

- [ ] **Step 2: Write failing artifact-contract tests.**

```python
def test_writes_exact_required_artifacts_and_valid_hashes(self) -> None:
    run = write_synthetic_run(self.root)
    self.assertEqual(
        {path.name for path in run.run_dir.iterdir()},
        {
            "config_resolved.yaml", "target_catalog.csv", "target_connectivity.csv",
            "target_ranking.csv", "seed_connected_fiber_ids.npy",
            "target_fiber_membership.npz", "input_resolution_qc.csv",
            "analysis_manifest.json", "artifact_index.csv",
        },
    )
    verify_artifact_index(run.run_dir)

def test_unchanged_rerun_is_content_identical_and_not_rewritten(self) -> None:
    first = write_synthetic_run(self.root, now=fixed_time())
    hashes = artifact_hashes(first.run_dir)
    mtimes = artifact_mtimes(first.run_dir)
    second = write_synthetic_run(self.root, now=later_time())
    self.assertEqual(second.run_dir, first.run_dir)
    self.assertEqual(artifact_hashes(second.run_dir), hashes)
    self.assertEqual(artifact_mtimes(second.run_dir), mtimes)
```

Cover atomic staging, immutable collision rejection, deterministic CSV row and
column order, `allow_nan=False`, target-connectivity required columns, source
hashes, resolved hashes, config hash, connectome identity, ordered-ID hash,
algorithm version, chunk size, code provenance, UTC timestamps, and no writes
outside output/cache roots.

- [ ] **Step 3: Run RED.**

- [ ] **Step 4: Implement content-addressed run storage.**

Derive the run fingerprint solely from stable configuration/input/algorithm
identity. Build all files in a sibling temporary directory, fsync, verify, then
atomically rename to `runs/<fingerprint>`. An existing complete matching run is
returned read-only; an incomplete or mismatched collision raises an error.
Timestamps are captured on first creation and preserved on unchanged reruns.

- [ ] **Step 5: Run GREEN and commit.**

---

### Task 7: Reusable API, CLI, Validation, Status, And Artifact Inspection

**Files:**
- Create: `my_helper/fiber/core/seed_target_connectivity/pipeline.py`
- Create: `my_helper/fiber/core/seed_target_connectivity/cli.py`
- Create: `my_helper/fiber/core/seed_target_connectivity/__main__.py`
- Create: `my_helper/fiber/pipelines/seed-target-connectivity`
- Create: `my_helper/fiber/core/seed_target_connectivity/tests/test_pipeline_cli.py`
- Modify: `my_helper/fiber/README.md`
- Modify: `my_helper/fiber/seed_target_connectivity_stats_goal.md`

**Interfaces:**
- Consumes: all prior task interfaces.
- Produces: `compute_seed_target_statistics(...)`, `validate_inputs(...)`, and CLI commands `validate`, `run`, `status`, `artifacts`.

- [ ] **Step 1: Update public documentation before API/CLI code.**

Document exact positional/options syntax, exit codes, immutable output layout,
cache location, and examples using the three scientific inputs explicitly.

- [ ] **Step 2: Write failing API/CLI integration tests.**

```python
def test_validate_resolves_inputs_without_traversing_connectome(self) -> None:
    adapter = RecordingAdapter(self.synthetic_fibers)
    report = validate_inputs(self.atlas_root, self.seed, adapter, self.config)
    self.assertEqual(report.n_targets, 2)
    self.assertEqual(adapter.iteration_count, 0)

def test_cli_exposes_four_commands(self) -> None:
    for command in ("validate", "run", "status", "artifacts"):
        completed = run_cli(command, fixture=self.fixture)
        self.assertEqual(completed.returncode, 0, completed.stderr)
```

Also test malformed target failure, missing threshold failure, zero-seed-support
run failure, peer target isolation, exact API output, JSON status, artifact
listing, safe paths, and CLI nonzero exit codes.

- [ ] **Step 3: Run RED.**

- [ ] **Step 4: Implement orchestration and CLI.**

`validate` may read connectome metadata and hashes but must never call
`iter_chunks`. `run` resolves all inputs, uses caches, computes statistics, and
writes one immutable run. `status` verifies the manifest/index before reporting
completion. `artifacts` emits deterministic artifact records.

- [ ] **Step 5: Run GREEN, run all package tests, and commit.**

Run:

```bash
/opt/anaconda3/envs/leaddbs/bin/python -m unittest discover \
  -s my_helper/fiber/core/seed_target_connectivity/tests -v
```

Expected: every unit/integration test passes with no warnings or errors.

---

### Task 8: Default dTOR Real-Data Acceptance And Completion Audit

**Files:**
- Create: `my_helper/fiber/core/seed_target_connectivity/acceptance.py`
- Create: `my_helper/fiber/core/seed_target_connectivity/tests/test_real_data_acceptance.py`
- Create: `my_helper/fiber/core/seed_target_connectivity/tests/fixtures/dtor_stnsnr_acceptance.yaml`
- Modify: `my_helper/fiber/README.md`
- Modify: `my_helper/fiber/seed_target_connectivity_stats_goal.md`
- Modify: `.planning/seed-target-connectivity-stats/task_plan.md` (ignored working log)
- Modify: `.planning/seed-target-connectivity-stats/progress.md` (ignored working log)

**Interfaces:**
- Consumes: the exact generic public API and all immutable artifacts.
- Produces: a repository acceptance command and evidence for both independent seeds.

- [ ] **Step 1: Document the real-data acceptance command and evidence directory.**

The fixture supplies explicit repository-relative paths for the 106-target
atlas, left seed, right seed, and dTOR data.mat. No core default or anatomical
branch is added.

- [ ] **Step 2: Write a guarded failing acceptance test.**

```python
@unittest.skipUnless(os.environ.get("RUN_DTOR_ACCEPTANCE") == "1", "full dTOR acceptance is opt-in")
def test_default_dtor_fixture(self) -> None:
    report = run_default_acceptance(self.repo_root, self.output_root)
    self.assertEqual(report.target_count, 106)
    self.assertGreater(report.left.n_seed_fibers, 0)
    self.assertGreater(report.right.n_seed_fibers, 0)
    self.assertTrue(report.sampled_kernel_equivalence)
    self.assertTrue(report.identical_rerun_hashes)
```

Expected RED before acceptance orchestration exists.

- [ ] **Step 3: Implement acceptance orchestration through the public API.**

Run left and right STNSNrplus independently. Reuse the target-membership cache
between runs. Select deterministic sampled real fibers containing seed-connected
and background IDs, load only those HDF5 ranges, and require bit-for-bit target
membership agreement between reference and optimized kernels. Assert 106 output
rows, valid finite metrics, deterministic ranks, unchanged rerun hashes, and no
source-tree/legacy-output mutation.

- [ ] **Step 4: Run the complete synthetic suite.**

Run package discovery plus `git diff --check`; expect all tests and whitespace
checks to pass.

- [ ] **Step 5: Run full real-data acceptance.**

```bash
RUN_DTOR_ACCEPTANCE=1 /opt/anaconda3/envs/leaddbs/bin/python -m unittest \
  my_helper.fiber.core.seed_target_connectivity.tests.test_real_data_acceptance -v
```

Expected: both complete dTOR runs pass. Record elapsed time, peak-memory evidence,
run directories, target count, seed counts, kernel sample size, and artifact
hash verification in the goal and progress log.

- [ ] **Step 6: Perform the requirement-by-requirement completion audit.**

Map every goal input, algorithm, metric, artifact, failure state, cache-reuse
rule, synthetic test, and real-data acceptance requirement to current code and
command evidence. Any missing or indirect evidence keeps the goal active.

- [ ] **Step 7: Mark implemented only after complete proof and commit.**

Change goal metadata to `Status: implemented` and
`Implementation status: verified_complete`, link the acceptance run evidence,
run the full test suite one final time, and create the final local commit. Do
not push.
