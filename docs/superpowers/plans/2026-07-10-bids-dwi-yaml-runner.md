# BIDS DWI YAML Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use test-driven development and execute each checkbox in order. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a project-agnostic YAML-driven BIDS/Lead-DBS DWI runner with strict validation, `validate`/`plan`/`run` modes, versioned run records, and thin project presets while preserving the existing Synb0/topup/eddy numerical backend.

**Architecture:** A strict YAML loader resolves configuration into one canonical MATLAB struct. The public runner resolves subjects and job specifications, validates every selected subject before dispatch, and then either reports the plan or calls the existing single-subject batch backend. A run-record helper owns immutable manifests and subject status snapshots; project wrappers only select a YAML preset and forward runtime overrides.

**Tech Stack:** MATLAB, bundled `readyaml`, SPM NIfTI inspection, existing Lead-DBS DWI helpers, YAML, JSON, CSV.

## Global Constraints

- Work on standard `<study_root>/rawdata/sub-<ID>/ses-<session>/dwi` and `<study_root>/derivatives/leaddbs` trees only.
- Raw BIDS files are read-only.
- Reuse `mh_fiber_process_imported_dwi_batch` and all existing Synb0/topup/eddy numerical code.
- Keep the fake-B0 tag, derivative naming, and `IntendedUse=coregistration_and_normalization` internal and unchanged.
- Reject unknown YAML fields, unsupported schema versions, ambiguous DWI candidates, invalid subject modes, prefixed subject IDs, invalid phase encoding, and invalid readout values.
- Validate all selected subjects before starting expensive image processing.
- Runtime name-value options override YAML; YAML overrides internal defaults.
- Use the Conda environment `leaddbs` for MATLAB verification.

---

### Task 1: Canonical Configuration Loader

**Files:**
- Create: `my_helper/fiber/core/dwi/mh_fiber_dwi_load_config.m`
- Create: `my_helper/dwi/test_bids_dwi_config.m`

**Interfaces:**
- Consumes: YAML path and a struct containing only explicitly supplied runtime overrides.
- Produces: `[config, source] = mh_fiber_dwi_load_config(configPath, overrides)`, where `config` is canonical and typed and `source.path` records the source YAML.

- [ ] Write tests covering the complete valid YAML, internal defaults, unknown fields, unsupported `schema_version`, subject-mode rules, `sub-` rejection, enum/type failures, and runtime override precedence.
- [ ] Run the test and confirm it fails because `mh_fiber_dwi_load_config` is undefined.
- [ ] Implement strict recursive field validation, typed normalization, defaults, and override application with bundled `readyaml`.
- [ ] Run the focused test and confirm every configuration case passes.
- [ ] Run `checkcode` on the loader and fix actionable diagnostics.

### Task 2: Session-Aware Job Resolution and Preflight

**Files:**
- Modify: `my_helper/fiber/core/dwi/mh_fiber_dwi_bids_jobspec.m`
- Create: `my_helper/fiber/core/dwi/mh_fiber_dwi_resolve_subjects.m`
- Create: `my_helper/fiber/core/dwi/mh_fiber_dwi_validate_jobspec.m`
- Modify: `my_helper/fiber/core/dwi/mh_fiber_process_imported_dwi.m`
- Create: `my_helper/dwi/test_bids_dwi_job_resolution.m`

**Interfaces:**
- Consumes: canonical config and optional runtime subject list.
- Produces: stable subject IDs, session-aware `jobSpec` structs, and geometry/gradient validation summaries.

- [ ] Write temporary-project tests for auto discovery, explicit selection, runtime override, non-`preop` sessions, acquisition-labeled sources, ambiguous DWI files, missing sidecars, gradient mismatch, absent b0, and missing anchors.
- [ ] Run the test and confirm failures identify the missing resolver/session/preflight behavior.
- [ ] Add `Session` to the job-spec builder and derive raw and formal paths from `ses-<session>`.
- [ ] Implement deterministic subject resolution and a shared preflight validator; call the validator from both the public runner and single-subject processor.
- [ ] Run focused and existing DWI job-spec/staging tests and confirm they pass.

### Task 3: Public Runner Modes

**Files:**
- Modify: `my_helper/dwi/run_bids_dwi_preprocessing.m`
- Modify: `my_helper/dwi/test_run_bids_dwi_preprocessing.m`

**Interfaces:**
- Consumes: `'Config'`, `'Mode'`, optional `'SubjectIds'`, and compatibility name-value parameters.
- Produces: a result struct containing mode, canonical config, subjects, job specs, preflight summaries, and batch output for `run`.

- [ ] Extend runner tests for `validate`, `plan`, `run` dispatch, no-write behavior in plan mode, runtime overrides, and legacy `DryRun` compatibility.
- [ ] Run tests and confirm they fail because the current runner lacks YAML and mode handling.
- [ ] Implement `Config`/`Mode`, explicit-argument detection, precedence resolution, all-subject preflight, and direct reuse of `mh_fiber_process_imported_dwi_batch`.
- [ ] Verify `validate` and `plan` never invoke image processing and `run` dispatches only after complete preflight.
- [ ] Run the full focused MATLAB suite.

### Task 4: Versioned Run Records

**Files:**
- Create: `my_helper/fiber/core/dwi/mh_fiber_dwi_run_records.m`
- Create: `my_helper/dwi/test_bids_dwi_run_records.m`
- Modify: `my_helper/dwi/run_bids_dwi_preprocessing.m`

**Interfaces:**
- Consumes: source config, resolved config, mode, job specs, and status rows.
- Produces: `derivatives/leaddbs/import_logs/dwi_runs/<run_id>/` with `config_source.yaml`, `config_resolved.json`, `job_manifest.csv`, `status.csv`, and per-subject JSON records.

- [ ] Write tests asserting unique run IDs, required files, manifest paths, status contents, and one subject record per selected ID.
- [ ] Run tests and confirm failure because the record helper is absent.
- [ ] Implement initialize/finalize actions with atomic file replacement where practical and no cohort-level CSV overwrite.
- [ ] Integrate records into all three modes after successful preflight.
- [ ] Run focused tests and inspect one temporary run directory.

### Task 5: Project YAML Presets and Compatibility Wrappers

**Files:**
- Create: `my_helper/stnvop/config/dwi.yaml`
- Create: `my_helper/stnsnr/config/dwi.yaml`
- Modify: `my_helper/fiber/stnsnr/run_stnsnr_dwi_registration.m`
- Create or modify focused wrapper tests beside each wrapper.

**Interfaces:**
- Consumes: project YAML plus optional mode, subjects, and runtime overrides.
- Produces: calls to `run_bids_dwi_preprocessing`; no project wrapper owns numerical processing or cohort generation.

- [ ] Write static and dry-run tests proving wrappers select presets, forward explicit subjects, and contain no duplicated project-processing logic.
- [ ] Run tests and confirm they fail against the current wrappers.
- [ ] Add the two presets and reduce wrappers to compatibility argument translation.
- [ ] Compare resolved Meige job specs from the compatibility and generic entry paths.
- [ ] Run wrapper and generic tests.

### Task 6: Acceptance Verification

**Files:**
- Modify: `my_helper/dwi/bids_leaddbs_dwi_goal.md`
- Modify: `my_helper/fiber/core/dwi/fake_b0_ui_coreg_tutorial.md`
- Modify: `my_helper/fiber/README.md`

**Interfaces:**
- Consumes: the implemented runner and its test evidence.
- Produces: current usage documentation and a requirement-by-requirement completion record.

- [ ] Run `test_bids_dwi_config`, `test_bids_dwi_job_resolution`, `test_run_bids_dwi_preprocessing`, `test_bids_dwi_run_records`, existing DWI regression tests, and wrapper tests in Conda `leaddbs`.
- [ ] Run `checkcode` for all changed MATLAB files and `git diff --check`.
- [ ] Run `validate` and `plan` against a temporary standard BIDS project and confirm no image derivatives are created.
- [ ] Run one temporary-project processing fixture with a lightweight injected batch path or existing fixture and verify corrected DWI, gradients, b0 geometry, metadata, and B0 target visibility without touching raw BIDS files.
- [ ] Search `my_helper/dwi` for Meige/STNVOP names and confirm only preset content, not file/function names, contains project identifiers.
- [ ] Update goal status and usage documentation only after every acceptance criterion has direct evidence.
