# dTOR-HybraPD Whole-Brain ROI Atlas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic Python package and CLI that exports a Lead-DBS-compatible HybraPD whole-brain ROI atlas and exact dTOR endpoint coverage.

**Architecture:** A generic core loads strict YAML into immutable models, parses and classifies integer labels, resamples the label volume, exports binary masks, streams endpoint counts from a Lead-DBS HDF5 connectome, and atomically publishes immutable artifacts. A tracked dTOR-HybraPD config supplies project-specific paths and category IDs.

**Tech Stack:** Python 3.11, NumPy, SciPy, nibabel, h5py, PyYAML, jsonschema, unittest.

## Global Constraints

- Use Conda environment `leaddbs`.
- Write documentation before production code.
- Write tests before each production behavior and observe the expected failure.
- Keep all code, identifiers, comments, docstrings, and code documentation in English.
- Do not overwrite mismatched existing atlas outputs and do not push remote changes.

---

### Task 1: Strict configuration and label metadata

**Files:** create the package models/config/labels modules, JSON schema, tracked dTOR-HybraPD YAML config, and focused tests.

**Interfaces:** `load_atlas_config(path) -> AtlasBuildConfig`; `parse_label_table(path) -> tuple[AtlasLabel, ...]`; `resolve_labels(config, source_image) -> tuple[ResolvedLabel, ...]`.

- [ ] Write tests for duplicate YAML keys, unknown fields, missing/surplus label IDs, category partitioning, hemisphere parsing, repeated white-matter names, and centroid-based white-matter laterality correction.
- [ ] Run the focused tests and confirm failure because the package does not exist.
- [ ] Implement only the validated immutable models, schema loader, label parser, classification, filename pairing, and source/resolved names.
- [ ] Run focused tests, then commit the green task.

### Task 2: Integer resampling and ROI export

**Files:** create resampling/export modules and synthetic NIfTI tests.

**Interfaces:** `resample_integer_labels(source, reference) -> nib.Nifti1Image`; `export_binary_rois(image, labels, staging_root) -> tuple[RoiArtifact, ...]`.

- [ ] Write tests proving nearest-neighbor label preservation, reference header/grid equality, 71/71/8/0 main directory counts for a category-complete fixture, white-matter isolation under `.qc`, paired filenames, mask disjointness, and exact reconstruction.
- [ ] Run tests and confirm the new APIs fail as missing.
- [ ] Implement memory-bounded order-zero affine resampling and one-mask-at-a-time compressed NIfTI export.
- [ ] Run focused tests and the existing seed-target atlas discovery tests; commit the green task.

### Task 3: Exact HDF5 endpoint census

**Files:** create endpoint census module and a tiny real HDF5 fixture test.

**Interfaces:** `compute_endpoint_census(connectome_path, label_image, labels, chunk_size) -> EndpointCensus`.

- [ ] Write tests for first/last endpoint extraction, outside-grid assignment, background assignment, same-label double endpoints, per-label unique-fiber counts, malformed `idx`, and total reconciliation.
- [ ] Run tests and confirm failure for the missing API.
- [ ] Implement sequential fiber-chunk reads and vectorized world-to-voxel lookup without distance fallback.
- [ ] Run focused tests and commit the green task.

### Task 4: Immutable artifacts, public API, and CLI

**Files:** create artifacts/pipeline/cli modules, executable pipeline wrapper, README update, and integration tests.

**Interfaces:** `build_whole_brain_roi_atlas(config) -> AtlasBuildResult`; CLI `validate`, `build`, and `status`.

- [ ] Write integration tests for validation output, atomic build, complete artifact set, README complete label inventory, hash verification, identical rerun reuse, mismatched output refusal, and status output.
- [ ] Run tests and confirm failures for missing pipeline/CLI behavior.
- [ ] Implement staged publication, fingerprinting, manifests, complete English README generation, API, and CLI.
- [ ] Run the complete new suite plus the existing seed-target connectivity suite; commit the green task.

### Task 5: Real-data acceptance and documentation

**Files:** update package and fiber documentation with exact run commands and verified output summary.

- [ ] Validate the tracked real config in Conda `leaddbs`.
- [ ] Build the real atlas and monitor the full 11,820,000-fiber endpoint scan.
- [ ] Verify label/mask counts, 23,640,000 endpoint reconciliation, spatial/header invariants, artifact hashes, and deterministic reuse.
- [ ] Confirm `atlas_index.mat` and `gm_mask.nii.gz` are absent and document that Lead-DBS UI creates them on first use.
- [ ] Run `compileall`, all package tests, existing seed-target tests, and `git diff --check`.
- [ ] Commit final documentation and acceptance evidence, leaving a clean worktree without pushing.
