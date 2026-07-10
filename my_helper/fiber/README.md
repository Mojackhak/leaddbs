# Lead-DBS Fiber/VTA Visualization Helpers

This folder contains patient-level MATLAB helpers for reproducible Lead-DBS Fiber/VTA visualization.

The public entry points are:

- `mh_fiber_default_config(subjectDir, stimLabel)`: create a fixed configuration for one subject and one existing Lead-DBS stimulation label.
- `mh_fiber_run(cfg)`: run ROI generation, fiber filtering, VTA-hit detection, e-field peak extraction, native fiber back-projection by fiber ID, reports, and figures.
- `mh_fiber_open_scene(figPath)`: reopen a saved helper scene, make it visible, and open the Lead-DBS Anatomy Slices control window when possible.
- `pipelines/sub001/run_sub001_fiber_tracking_two_scheme_vis.m`: rerun sub-001 structural fiber tracking, then generate both the Lead-DBS two-source VTA approximation and the helper one-solve multi-voltage VTA outputs.
- `pipelines/sub001/run_sub001_fiber_vis.m`: command-line script for the current `sub-001` case.
- `stnsnr/run_stnsnr_build_active_contact_dataset.py`: build the 16-subject active-contact coordinate dataset.
- `stnsnr/run_stnsnr_generate_random_stimulation_table.py`: generate a reproducible random test stimulation table for the active contacts.
- `stnsnr/run_stnsnr_compare_roi_definitions.m`: compare HybraPD STN/SNr labels with the `Custom_Ewert_Zhang_Middlebrooks0.05` atlas.
- `stnsnr/run_stnsnr_dwi_import_stage.m`: re-import the 16-subject STN/SNr DWI four-file sets into BIDS rawdata, then stage DWI and b0 derivatives without running b0-to-T2 registration.
- `core/dwi/run_project_dwi_fake_b0_coreg.m`: run the project-agnostic Synb0/eddy fake-B0 UI-coreg staging workflow.
- `stnsnr/run_stnsnr_dwi_registration.m`: STNSNr wrapper for the project-agnostic Synb0/eddy fake-B0 UI-coreg workflow.
- `stnsnr/run_stnsnr_dwi_registration_method_pilot.m`: run the three-subject SPM and Hybrid SPM+ANTs b0-to-anchorNative T2 registration pilot.

## Folder Layout

The helper requires recursive MATLAB path setup, for example `addpath(genpath('/Users/mojackhu/Github/leaddbs'))`.

```text
my_helper/fiber/
  README.md
  core/
    coverage/       e-field grid sampling, atlas region partitioning, coverage summaries
    config/         configuration, validation, output folders, VTA paths
    dwi/            DWI staging, b0 extraction, b0-to-anchor registration, QC
    io/             FTR/TCK/VTK readers, writers, and reports
    roi/            atlas ROI definitions and mask generation
    connectomes/    public-connectome helper functions
    selection/      fiber-mask selection, subsets, and sampling
    stimulation/    stimulation specs, VTA facade/backends, scheme comparison
    tracking/       main runners, MRtrix, seed-target, SIFT2
    util/           shared filesystem, label, repository, and JSON helpers
    viz/            shared plotting styles and semantic chart helpers
    visualization/  scenes, figures, plots, electrode styling
    ui/             toolbar/object-control helpers
  pipelines/
    sub001/         patient/case pipeline scripts
  stnsnr/           STN/SNr pipeline scripts only
```

Core implementation functions live under `core/`. The `stnsnr/` folder must only contain pipeline scripts that call core functions; ROI specs, selectors, chunked connectome readers, and report writers belong under `core/`.

## Generic Seed-Target Connectivity Statistics

`core/seed_target_connectivity/` provides the project-independent Python
implementation for target-wise structural-connectivity statistics. Its public
API accepts exactly one target-atlas directory, one seed ROI NIfTI, one
stable-ID streamline connectome, and an algorithm configuration:

```python
from my_helper.fiber.core.seed_target_connectivity import compute_seed_target_statistics

result = compute_seed_target_statistics(
    target_atlas_root=target_atlas_root,
    seed_roi=seed_roi,
    connectome=connectome,
    config=config,
)
```

The command-line interface exposes four operations:

```bash
conda run -n leaddbs python my_helper/fiber/pipelines/seed-target-connectivity validate \
  --target-atlas-root /path/to/atlas \
  --seed-roi /path/to/seed.nii.gz \
  --connectome /path/to/connectome \
  --config /path/to/config.yaml

conda run -n leaddbs python my_helper/fiber/pipelines/seed-target-connectivity run \
  --target-atlas-root /path/to/atlas \
  --seed-roi /path/to/seed.nii.gz \
  --connectome /path/to/connectome \
  --config /path/to/config.yaml \
  --output-root /path/to/output

conda run -n leaddbs python my_helper/fiber/pipelines/seed-target-connectivity status \
  --run-dir /path/to/output/runs/<run-fingerprint>

conda run -n leaddbs python my_helper/fiber/pipelines/seed-target-connectivity artifacts \
  --run-dir /path/to/output/runs/<run-fingerprint>
```

`validate` resolves configuration, atlas targets, ROI masks, and connectome
metadata without traversing the complete connectome. `run` computes or reuses
independent seed/target membership caches and writes one immutable run
directory. `status` verifies an existing run, and `artifacts` lists its indexed
outputs. Unless `--cache-root` is supplied, reusable membership caches live at
`<output-root>/membership_cache`; immutable runs live at
`<output-root>/runs/<run-fingerprint>`. Commands write JSON to standard output.
Exit code `0` means success, `1` means a configuration/input/run integrity
failure, and argparse uses exit code `2` for invalid command syntax. All
repository invocations use the Conda `leaddbs` environment. The reusable core
has no STN/SNr, hemisphere, clinical, stimulation, or target-selection
defaults.

### Default Real-Data Acceptance

The repository acceptance fixture is explicit and remains outside reusable
core defaults:

```text
my_helper/fiber/core/seed_target_connectivity/tests/fixtures/dtor_stnsnr_acceptance.yaml
```

Run it in Conda `leaddbs` with an output directory outside the source tree:

```bash
conda run -n leaddbs python -m \
  my_helper.fiber.core.seed_target_connectivity.acceptance \
  --fixture my_helper/fiber/core/seed_target_connectivity/tests/fixtures/dtor_stnsnr_acceptance.yaml \
  --repo-root /Users/mojackhu/Github/leaddbs \
  --output-root /tmp/seed-target-connectivity-dtor-acceptance
```

The fixture invokes the same public API twice, once per declared seed. It
requires complete optimized dTOR traversal, target-cache reuse, deterministic
artifact hashes on unchanged reruns, and exact reference/optimized membership
agreement for deterministic sampled real fibers. It does not union seeds or
infer hemisphere/anatomical meaning from fixture labels.

Within one process, the acceptance runner may reuse a read-only resolution
cache for the unchanged atlas and seed NIfTIs. This avoids decompressing the
same 106 high-resolution target files on every public-API invocation; cache
identity includes source path, file size, modification time, and configuration
hash. Membership identities and immutable artifacts remain unchanged.

## VTA Computation Modules

VTA generation now uses `core/stimulation/model/mh_vta_compute.m` as the
single facade. Existing public helpers such as `mh_fiber_ensure_vta` and
`mh_fiber_ensure_vta_onesolve` remain compatibility wrappers around the facade.
Model selection is resolved through `mh_vta_model_registry`, while Horn
conductivity, threshold, atlas, and electrode-removal settings are centralized
in `mh_vta_settings`.
The generic omitted-model fallback is centralized in
`mh_vta_default_model_key`.
Generic VTA config and request output-space defaults are centralized in
`mh_vta_default_config_space` and `mh_vta_output_spaces_from_config`.
The generic fallback gray-matter atlas for `mh_fiber_default_config` is
centralized in `mh_vta_default_gm_atlas`; project analyzers should still inject
their own atlas choices explicitly.
Task-runner parser defaults for VTA request fields are centralized in
`mh_vta_task_request_defaults`.
Backend request-field and force fallbacks are centralized in
`mh_vta_request_field` and `mh_vta_config_force`.
Execution config reads optional `cfg.vta` fields through
`mh_vta_config_field`.
Deferred real FEM/process/parpool checks should be run through
`mh_fiber_run_stnsnr_vta_subset_validation`, which copies selected STN/SNr
subjects into a fresh validation root before invoking the shared VTA coverage
entry point.
Standard VTA path lookups use `mh_fiber_vta_paths` and
`mh_fiber_vta_efield_path`.
VTA MAT volume reads use `mh_vta_read_vat_volume`.
Coverage thresholding samples e-field lists with
`mh_coverage_sample_efields_to_grid` and classifies one threshold with
`mh_coverage_threshold_sampled_efields`.
Coverage composition figures are written through
`mh_coverage_write_composition_figure`.
Coverage summary statistics use `mh_coverage_iqr` for NaN-robust interquartile
range values.
Total VTA summary tables use `mh_coverage_total_vta_summary`.
Category summary tables use `mh_coverage_category_summary_table`.
Stacked coverage-share figure matrices use `mh_coverage_category_matrix`.
Threshold-sensitivity trend tables use `mh_coverage_threshold_trend_table`.
Long-to-wide category coverage tables use `mh_coverage_category_wide_table`.
Coverage output file checks use `mh_coverage_require_output_files`.
Threshold-series validation uses `mh_coverage_validate_threshold_series`.
Category-total validation uses `mh_coverage_validate_category_totals`.
Required table-variable checks use `mh_util_require_table_vars` when callers
need first-missing-column error behavior.
Cell-row table construction uses `mh_util_cell_rows_to_table` when callers own
the output schema and string-variable list.
Horn backend calls use `mh_vta_run_horn_with_retry` for deterministic retry and
post-write success handling.

STN/SNr VTA generation uses explicit atomic compute tasks.
`mh_vta_make_compute_task` records the standard paths and request metadata for
one stimulation label and side; `mh_vta_run_compute_task` executes that task
through the facade. `mh_vta_run_compute_tasks` keeps sequential execution as
the default and selects task-level `parpool` or `process` execution when
`cfg.vta.executionMode` requests those modes.
Generated stimulation labels use `mh_util_sanitize_label` through
`mh_fiber_make_stim_label`.
`mh_vta_run_stim_spec_tasks` owns cfg/stimSpec normalization and stimulation
building so project analyzers only need to prepare project-specific stimulation
specs. It delegates built stimulation dispatch to
`mh_vta_run_built_stimulation_tasks`, which owns shared side-task construction
and task-harness execution for both analyzer-generated and manually customized
Lead-DBS stimulation structures.
STN/SNr analyzers share `mh_fiber_stnsnr_stimspec_from_table` for converting
workbook-style and normalized contact rows into Layer 1 stimulation specs.
STN/SNr stimulation-pattern report labels use
`mh_fiber_stnsnr_stimulation_pattern_label`.
STN/SNr observed VTA program labels use
`mh_fiber_stnsnr_vta_program_label`.
STN/SNr condition and target directory keys use
`mh_fiber_stnsnr_condition_key`.
STN/SNr VTA coverage artifact basenames use
`mh_fiber_stnsnr_vta_artifact_base`.
STN/SNr target-component identifiers and generated target-component VTA labels
use `mh_fiber_stnsnr_target_component_id` and
`mh_fiber_stnsnr_target_component_vta_label`.
STN/SNr VTA manifest fields, including conductivity defaults from
`mh_vta_settings`, are populated through
`mh_fiber_stnsnr_add_vta_manifest_fields`.
The STN/SNr default VTA gray-matter atlas is centralized in
`mh_fiber_stnsnr_default_vta_gm_atlas`; project scripts still accept
`STNSNR_VTA_GM_ATLAS` overrides.
The STN/SNr default VTA model key is centralized in
`mh_fiber_stnsnr_default_vta_model_key`; project scripts still accept
`STNSNR_VTA_MODEL_KEY` overrides.

Process-isolated launches are now routed through
`mh_vta_launch_process_workers`, which centralizes subject chunking, dry-run job
tables, Conda-aware MATLAB batch command construction, and PID/log metadata for
the STN/SNr process worker entry point.
Shell command quoting uses the shared `mh_fiber_shell_quote` helper.

Task-level process execution uses the same execution-harness family:
`mh_vta_run_compute_tasks` keeps sequential execution as the default, while
`cfg.vta.executionMode = 'process'` dispatches serialized program-side VTA tasks
to isolated MATLAB workers for cases where Lead-DBS global state should not be
shared inside one MATLAB process. Process-mode configuration lives under
`cfg.vta.matlabExe`, `cfg.vta.condaEnv`, `cfg.vta.processWorkDir`,
`cfg.vta.processDryRun`, `cfg.vta.processPollSeconds`, and
`cfg.vta.processTimeoutSeconds`. Default execution values are centralized in
`mh_vta_default_execution_options`.

STN/SNr cohort coverage exposes the same controls as
`VtaModelKey`, `VtaExecutionMode`, `VtaParallelWorkers`, `VtaMatlabExe`,
`VtaCondaEnv`, `VtaProcessWorkDir`, `VtaProcessDryRun`,
`VtaProcessPollSeconds`, and `VtaProcessTimeoutSeconds`. The subject-level
launcher forwards matching
`STNSNR_VTA_MODEL_KEY`, `STNSNR_VTA_EXECUTION_MODE`,
`STNSNR_VTA_PARALLEL_WORKERS`, `STNSNR_VTA_TASK_MATLAB_EXE`,
`STNSNR_VTA_TASK_CONDA_ENV`, `STNSNR_VTA_PROCESS_WORK_DIR`,
`STNSNR_VTA_PROCESS_DRY_RUN`, `STNSNR_VTA_PROCESS_POLL_SECONDS`, and
`STNSNR_VTA_PROCESS_TIMEOUT_SECONDS` environment variables to worker processes.
`STNSNR_VTA_MODEL_KEY` defaults to `simbio`.
Subject ID chunks are written and forwarded as semicolon-separated lists, which
are parsed by `mh_fiber_split_env_list`. The launcher writes full shell command
lines to per-worker command files and stores those command file paths in
`parallel_jobs.csv`, keeping the CSV readable by MATLAB `readtable` when
`Delimiter` is set to `','`.

The non-parallel STN/SNr cohort script reads the same execution environment
variables before calling `mh_fiber_run_stnsnr_vta_coverage`, so execution mode
selection does not require editing the script.

The STN/SNr target-component VTA distribution runner uses the same
`STNSNR_VTA_*` execution environment variables for counterfactual component VTA
generation.
The project VTA gray-matter restriction atlas is selected with `VtaGmAtlas` or
the `STNSNR_VTA_GM_ATLAS` environment variable, defaulting to
`DISTAL Minimal (Ewert 2017)`.
The cohort aggregation script reads the same subject-root, workbook,
cohort-output, and gray-matter-atlas environment overrides as the launcher.

Coverage analysis is separate from VTA generation. `core/coverage/` builds the
reference grid, samples e-field and atlas masks, and classifies VTA voxels with
a generic membership-partition region specification. STN/SNr analyses inject
their own STN and SNr atlas paths at the project layer; the coverage engine does
not hard-code those region names or paths. The shared STN/SNr project region
specification is built by `mh_fiber_stnsnr_region_spec`.
Standard VTA/category/overlap mask outputs are written through
`mh_coverage_write_standard_masks`.
Coverage threshold values are formatted for filenames with
`mh_coverage_threshold_label`.
STN/SNr contact mapping tables are normalized through
`mh_fiber_stnsnr_normalize_contact_table`, which accepts both workbook-style
headers and normalized per-subject contact QC CSV headers.
Shared table string-column conversion uses `mh_util_force_string_vars`.
Shared struct field access/removal uses `mh_util_get_field` and
`mh_util_rmfield_safe`.
Semicolon-joined report fields use `mh_util_join_values`.
General labels are sanitized through `mh_util_sanitize_label`; explicit
stimulation labels preserve plus signs for backward-compatible folder names.

Composition figures use `core/viz/` semantic plotting helpers: part-whole VTA
category summaries are drawn as donut charts or 100 percent stacked share bars,
with readable percentage labels on visible composition segments, while
distribution and threshold-sensitivity outputs remain box plots and line plots
with shared styling.

## STN/SNr Cohort Test Datasets

The active-contact dataset pipeline reads the source clinical coordinate table,
the reconstructed contact table, the subject electrode configuration, and the
programming definition. It then writes:

```text
/Users/mojackhu/Research/STNSNr/summary/cohort/lead/contact_activation_dataset/active_contacts.csv
/Users/mojackhu/Research/STNSNr/summary/cohort/lead/contact_activation_dataset/active_contacts_info.json
```

In `active_contacts.csv`, `Region` remains the anatomical atlas/reconstruction
label. The added `region_programming` field stores the programming region from
`/Users/mojackhu/Research/STNSNr/summary/cohort/subj/programming.json`.

Run it with the Lead-DBS Conda environment:

```bash
/opt/anaconda3/envs/leaddbs/bin/python \
  /Users/mojackhu/Github/leaddbs/my_helper/fiber/stnsnr/run_stnsnr_build_active_contact_dataset.py
```

The random stimulation table pipeline uses `active_contacts.csv` as input and
writes:

```text
/Users/mojackhu/Research/STNSNr/summary/cohort/lead/contact_activation_dataset/random_stimulation_parameters.csv
/Users/mojackhu/Research/STNSNr/summary/cohort/lead/contact_activation_dataset/random_stimulation_parameters_info.json
```

Default test ranges are:

- voltage: uniform random values from `2.0` to `4.0 V`, rounded to `0.1 V`;
- pulse width: uniform random integers from `50` to `90 us`;
- SNr frequency: uniform random integers from `15` to `40 Hz`;
- STN frequency: uniform random integers from `120` to `180 Hz`.

The random stimulation table assigns frequency by `region_programming`, not by
the anatomical `Region` label. All active contacts must map to exactly one of
`programming.json[ID]["SNr"]` or `programming.json[ID]["STN"]`; otherwise the
pipeline raises an error instead of silently assigning a frequency.

Run the random stimulation generator with:

```bash
/opt/anaconda3/envs/leaddbs/bin/python \
  /Users/mojackhu/Github/leaddbs/my_helper/fiber/stnsnr/run_stnsnr_generate_random_stimulation_table.py
```

## Default Behavior

The default workflow uses:

- MNI-space fibers from `connectomics/dMRI/FTR_normalized.mat`.
- Native-space fibers from `connectomics/dMRI/FTR_anat.mat` when available.
- MNI VTA/e-field files generated by Lead-DBS under `stimulations/MNI152NLin2009bAsym/<stimLabel>`.
- Native VTA/e-field files generated by Lead-DBS under `stimulations/native/<stimLabel>`.
- ROI masks generated from `templates/space/MNI152NLin2009bAsym/labeling/HybraPD Whole Brain (Yu 2021).nii`.

Default HybraPD Whole Brain labels:

- `ALIC_R = 217`
- `ALIC_L = 218`
- `NAc_L = 305`
- `NAc_R = 306`

The default activation proxy is defined as fiber/VTA intersection. For every VTA-hit fiber, the helper records peak e-field sampled from the Lead-DBS e-field NIfTI and flags `peak >= 200 V/m`.

## Sub-001 Two-Scheme Stimulation Workflow

The current sub-001 rerun uses a global 0-15 clinical contact convention:

- Global left contacts `0-7` map to Lead-DBS contacts `L1-L8`.
- Global right contacts `8-15` map to Lead-DBS contacts `R1-R8`.
- Global `1` and `9` therefore map to `L2` and `R2`, stimulated at `3.0 V / 130 Hz / 120 us`.
- Global `4,5,6,7` and `12,13,14,15` map to `L5-L8` and `R5-R8`, stimulated at `5.0 V / 130 Hz / 120 us`.

Two VTA schemes are produced from the same regenerated patient-specific fibers:

- `clinical_twosource_L2R2_3V_L5to8R5to8_5V`: Lead-DBS-native SimBio scheme. Each side uses two Lead-DBS sources because each source has only one amplitude: contact 2 is a 3 V cathodic source, and contacts 5-8 are a 5 V cathodic source with `perc=100` for every active contact. In voltage mode `perc` is an on/off participation marker and does not split voltage.
- `clinical_onesolve_L2R2_3V_L5to8R5to8_5V`: helper multi-voltage scheme. The helper reuses the Lead-DBS headmodel and VTA writer but solves one FEM problem per side with contact 2 set to -3 V and contacts 5-8 set to -5 V. This avoids Lead-DBS' per-source maximum-field merge for the mixed-amplitude contacts.

The two schemes write separate stimulation folders and separate `connectomics/fiber_vis/<stimLabel>` outputs. Their VTA volumes, Dice overlap, e-field peaks, and VTA-hit fiber counts are summarized in `connectomics/fiber_vis/two_scheme_comparison`.

The rerun script builds the Lead-Connectome `options.lc` structure directly instead of opening the Lead Connectome GUI initializer, so it can run from `matlab -batch`.

The rerun requires Lead-DBS to recognize numbered ANTs affine filenames such as `_ants1.mat` when applying b0/T1 transforms. The helper workflow relies on that compatibility because Lead-DBS itself writes numbered ANTs transforms during DWI/T1 and tracking-mask registration.

Fiber normalization must stay on the same registration chain that was visually approved:

- b0/DWI native space: `preprocessing/dwi/sub-001_ses-preop_acq-iso_dwi_b0.nii`.
- anatomical native space: `coregistration/anat/sub-001_ses-preop_space-anchorNative_desc-preproc_acq-iso_T2w.nii`.
- b0 to anatomical transform: `coregistration/dwi_t2/sub-001_ses-preop_acq-iso_dwi_b02sub-001_ses-preop_space-anchorNative_desc-preproc_acq-iso_T2w_ants1.mat`.
- anatomical to MNI transform: `normalization/transformations/sub-001_from-anchorNative_to-MNI152NLin2009bAsym_desc-ants.nii.gz`.

The b0 image must inherit the affine/header of the 4D DWI from which FA was computed. Do not recenter only the b0 header independently of the 4D DWI/FA header, because that makes b0 and FA disagree before any DWI-to-T1 transform is applied. For sub-001, the accepted repair is:

- rebuild `preprocessing/dwi/sub-001_ses-preop_acq-iso_dwi_b0.nii` from frame 1 of `preprocessing/dwi/sub-001_ses-preop_acq-iso_dwi.nii`;
- re-estimate the b0-to-anchorNative T2 ANTs affine from the rebuilt b0;
- use the same b0-to-anchorNative T2 affine to resample native FA for QC;
- apply `sub-001_from-anchorNative_to-MNI152NLin2009bAsym_desc-ants.nii.gz` to the anchorNative b0/FA QC files for MNI inspection.

## STN/SNr DWI Registration

The STN/SNr DWI registration batch is documented in:

```text
/Users/mojackhu/Github/leaddbs/my_helper/stnsnr/dwi_registration_technical_details.md
```

Lead-DBS DWI import/staging now recreates the staged b0 image automatically from the imported 4D DWI and gradient sidecars. Existing staged b0 files are overwritten during import/staging. The b0 extraction helper uses `bval < 10`, averages multiple b0 volumes, and preserves the original DWI affine/header without independently recentering the b0 image.

When a staged b0 exists under `preprocessing/dwi/`, the Lead-DBS Coregister UI exposes it as a pseudo-preop modality named `B0`. `B0` reuses the existing MR coregistration methods and writes formal UI outputs under:

```text
coregistration/anat/sub-<Subject>_ses-preop_space-anchorNative_desc-preproc_B0.nii
coregistration/transformations/sub-<Subject>_from-b0_to-anchorNative_desc-<method>.mat
coregistration/transformations/sub-<Subject>_from-anchorNative_to-b0_desc-<method>.mat
```

The `B0` item is not an anatomical MRI and is appended after true preop anatomical modalities, so it is available for b0-to-anchorNative QC without becoming the default anchor.

The 16-subject raw DWI re-import and staging-only entry point is:

```bash
matlab -batch "cd('/Users/mojackhu/Github/leaddbs'); addpath(genpath(pwd)); run('/Users/mojackhu/Github/leaddbs/my_helper/fiber/stnsnr/run_stnsnr_dwi_import_stage.m')"
```

The project-agnostic YAML entry point is:

```matlab
run_bids_dwi_preprocessing( ...
    'Config', '/path/to/project/dwi.yaml', ...
    'Mode', 'run', ...
    'SubjectIds', {'SubA', 'SubB'})
```

Use `Mode='validate'` to validate every selected input without image
processing, and `Mode='plan'` to return and record the resolved job manifest.
Each mode writes a unique audit directory under
`derivatives/leaddbs/import_logs/dwi_runs/<run_id>/`.

The STNSNr wrapper is:

```bash
matlab -batch "cd('/Users/mojackhu/Github/leaddbs'); addpath(genpath(pwd)); run('/Users/mojackhu/Github/leaddbs/my_helper/fiber/stnsnr/run_stnsnr_dwi_registration.m')"
```

The wrapper selects `my_helper/stnsnr/config/dwi.yaml`, then calls the generic
runner. The fake-B0 workflow writes:

```text
preprocessing/dwi/sub-<Subject>_ses-preop_desc-preproc_dwi.nii
preprocessing/dwi/sub-<Subject>_ses-preop_desc-preproc_b0.nii
coregistration/anat/sub-<Subject>_ses-preop_space-anchorNative_desc-preproc_B0.nii
```

The script is resumable and reuses existing outputs unless `Force` is enabled.
It does not run scripted b0-to-T2 registration in fake-B0 mode. Instead, the
corrected b0 is exposed to the Lead-DBS `Coregister Volumes` UI as pseudo `B0`.
SPM is usually tried first, but the accepted method should be chosen from manual
QC of the coregistration result.

The three-subject method pilot compares SPM and Hybrid SPM+ANTs against the existing ANTs T2 results for `ChenMeiJu`, `ZhangXiaoHong`, and `ZhangMing`:

```bash
matlab -batch "cd('/Users/mojackhu/Github/leaddbs'); addpath(genpath(pwd)); run('/Users/mojackhu/Github/leaddbs/my_helper/fiber/stnsnr/run_stnsnr_dwi_registration_method_pilot.m')"
```

The pilot writes branch-specific outputs and does not promote any transform into `coregistration/transformations/`:

```text
coregistration/dwi_t2_spm/sub-<Subject>_from-b0_to-anchorNative_desc-spm.mat
coregistration/dwi_t2_spm/sub-<Subject>_from-anchorNative_to-b0_desc-spm.mat
coregistration/dwi_t2_hybrid_spm_ants/sub-<Subject>_from-b0_to-anchorNative_desc-ants.mat
coregistration/dwi_t2_hybrid_spm_ants/sub-<Subject>_from-anchorNative_to-b0_desc-ants.mat
```

For the Hybrid branch, the `desc-ants` files are the ANTs refinement after a saved `desc-spm-init` initialization; they are not standalone complete transforms for promotion.
Legacy SPM/ANTs intermediate filenames are confined to each branch `work/` subfolder.

The helper intentionally does not call `ea_perform_lc` for the normalization step. `ea_perform_lc` refreshes `ea_getptopts` before `ea_normalize_fibers`, which can reset `prefs.prenii_unnormalized` to the default preprocessing T1 and make `ea_normalize_fibers` pick a newly generated `_ants2.mat` tracking-mask transform. That chain can place normalized fibers too inferiorly in MNI space.

For BIDS ANTs normalization, native-to-MNI fiber coordinates should be mapped with the Lead-DBS `forward` transform (`from-anchorNative_to-MNI152NLin2009bAsym`) and `useinverse=0`. The helper verifies this direction because `ea_gettransformfiles.inverse` is the MNI-to-anchorNative deformation in the current BIDS naming scheme.

Native visualization and native TRK export should use the same accepted anchorNative reference as `FTR_anat.mat`: `coregistration/anat/<subject>_ses-preop_space-anchorNative_desc-preproc_acq-iso_T1w.nii`. The helper resolves this anchorNative image before any preprocessing T1 fallback, so native ROI masks, native fibers, native VTA, and the native scene share the same patient-space reference.

## Output Layout

Each stimulation label writes to:

```text
connectomics/fiber_vis/<stimLabel>/rois
connectomics/fiber_vis/<stimLabel>/fibers_mni
connectomics/fiber_vis/<stimLabel>/fibers_native
connectomics/fiber_vis/<stimLabel>/activation
connectomics/fiber_vis/<stimLabel>/seed_target
connectomics/fiber_vis/<stimLabel>/figures
connectomics/fiber_vis/<stimLabel>/reports
```

The `activation` output is a VTA-overlap and e-field-threshold proxy by default. It should be described as VTA-hit fibers or peak e-field thresholded fibers, not as full OSS-DBS/PAM axon activation.

## MRtrix3 Seed-Target Tractography

The helper can optionally run native DWI-space MRtrix3 iFOD2 tractography after the existing Lead-DBS FTR exact filtering step. This adds `NAc_seed_target` and `ALIC_seed_target` outputs without changing the strict `NAc_exact` and `ALIC_exact` definitions.

Strict exact definitions are unchanged:

- `NAc_exact`: an existing patient-specific Lead-DBS FTR streamline has at least one sampled point inside the NAc mask.
- `ALIC_exact`: an existing patient-specific Lead-DBS FTR streamline has at least one sampled point inside the ALIC mask.

If either exact count is zero, the report keeps it as zero. The seed-target workflow is a separate probabilistic tractography analysis and must not be described as exact passage through NAc or ALIC.

The MRtrix3 backend uses:

- DWI image: `preprocessing/dwi/<subject>_ses-preop_acq-iso_dwi.nii`
- Gradients: matching `.bvec` and `.bval`
- b0 reference: `preprocessing/dwi/<subject>_ses-preop_acq-iso_dwi_b0.nii`
- Brain mask: `preprocessing/dwi/brainmask.nii`
- Tracking mask: `preprocessing/dwi/trackingmask.nii`
- Algorithm: `tckgen -algorithm iFOD2`
- Response/FOD: single-shell response with `dwi2response tournier`, then single-shell CSD with `dwi2fod csd`

Seed-target tractography is parallelized at the bundle level. The ROI conversion,
DWI/FOD preparation, and stimulation VTA/e-field resampling are still performed
once in a serial setup step, then each seed-target query is dispatched as an
independent task. This avoids multiple workers writing the same intermediate
ROI masks while allowing independent `tckgen` calls to run concurrently.

Default parallel settings:

- `cfg.seedTarget.parallel = true`
- `cfg.seedTarget.parallelWorkers = 16`
- `cfg.seedTarget.threads = 1`

For sub-001, this uses all 16 available CPU cores as independent single-thread
MRtrix workers. If the workstation must remain responsive for other heavy
programs, reduce `parallelWorkers` to 8-10 before starting the run.

With the default full network there can be up to 128 `.tck` tasks:

```text
2 sides x 2 seeds x 2 seed variants x 8 non-self targets x
2 tract types (seed-target and VTA_seed_hit)
```

The formal default tractography budget is:

- `cfg.seedTarget.select = 5000`
- `cfg.seedTarget.seeds = 500000`

`select` is the requested number of accepted streamlines per task. `seeds` is
the maximum number of seeding attempts. Difficult seed-target pairs can take
much longer than easy pairs and may still return fewer than `select` streamlines
or zero streamlines after exhausting the seed budget.

The seed-target runner is resumable by default:

- `cfg.seedTarget.force = false`
- `cfg.seedTarget.resume = true`

A bundle is skipped only when the main `.tck`, native/MNI display `.mat`, the
`VTA_seed_hit` `.tck`, and its native/MNI display `.mat` are all present and
readable. Interrupted partial files are not treated as complete results and are
rerun.

For fast QC, reduce the budget before running:

```matlab
cfg.seedTarget.select = 200;
cfg.seedTarget.seeds = 50000;
cfg.seedTarget.writeDensity = false;
cfg.seedTarget.writeVtk = false;
```

For sub-001 and similar Lead-DBS outputs, `preprocessing/dwi/brainmask.nii` may be a high-resolution anatomical tissue-class image rather than a DWI-grid mask. The helper checks the spatial dimensions against the DWI image. If the brain mask does not match the DWI grid, it uses the DWI-grid `trackingmask.nii` as the MRtrix response/FOD mask and records that fallback in the command log.

Seed-target spatial QC should distinguish the tractography result from display exports:

- The native MRtrix `.tck` files and `tckmap` density NIfTI files are in DWI/b0 space and should be checked against the DWI b0 or FA image.
- The native display `.mat`, native display `.trk`, helper `.vtk`, and native scene `.fig` are derived display exports and should be checked against the anchorNative T1/FA image.
- If density maps align with DWI but display fibers appear outside the brain, the problem is in the display coordinate transform, not in the completed iFOD2 tractography itself.

For display conversion, DWI-space TCK points must be mapped into anchorNative space with the approved b0-to-anchorNative transform:

```text
coregistration/dwi_t2/<subject>_ses-preop_acq-iso_dwi_b02<subject>_ses-preop_space-anchorNative_desc-preproc_acq-iso_T2w_ants1.mat
```

Do not use the anchorNative-to-b0 transform for this direction. Doing so shifts seed-target display fibers away from the anchorNative anatomy while the original `.tck` and density maps remain valid in DWI space.

The helper `.vtk` files are anchorNative display files for Slicer. They are written from the corrected native display `.mat` coordinates, not directly from raw MRtrix `tckconvert`, because raw `.tck` coordinates remain in DWI/b0 space.

Seed variants are written separately:

- `seed-exact`: the atlas ROI inverse-normalized into DWI space and restricted to the DWI brain mask.
- `seed-interface`: the DWI-space ROI is dilated by `cfg.seedTarget.interfaceDilatePasses` and restricted to the DWI tracking mask. This is a tractography seed definition only; it is not an exact anatomical-passage definition.

Default seed ROIs:

- `NAc_R` and `NAc_L`
- `ALIC_R` and `ALIC_L`

Default ipsilateral targets:

- `NAc`
- `ALIC`
- `mPFC`
- `OFC`
- `ACC`
- `amygdala`
- `hippocampus`
- `thalamus`
- `VTA`

The default ROI sources are deterministic atlas label masks:

- HybraPD Whole Brain for NAc: `Nucleus_accumbens_L=305`, `Nucleus_accumbens_R=306`.
- HybraPD Whole Brain for ALIC: `Anterior_limb_of_internal_capsule_R=217`, `Anterior_limb_of_internal_capsule_L=218`.
- HybraPD Whole Brain for mPFC: `Frontal_Sup_Medial`, `Frontal_Med_Orb`, and `Rectus` labels for the matching side.
- HybraPD Whole Brain for OFC: `OFCmed`, `OFCant`, `OFCpost`, and `OFClat` labels for the matching side.
- HybraPD Whole Brain for amygdala, hippocampus, and thalamus: the corresponding single left/right labels.
- Hammers n30r95 for ACC when HybraPD does not provide a clear anterior cingulate label and the local AAL3 NIfTI has empty anterior cingulate labels: `CG_anterior_cingulate_gyrus_L=24`, `CG_anterior_cingulate_gyrus_R=25`.
- AAL3 for VTA: `VTA_L=159`, `VTA_R=160`.

All atlas masks are first generated in MNI space, then inverse-normalized into anchorNative T1 space, then coregistered into DWI/b0 space using the approved anchorNative-to-b0 ANTs affine. The tractography calculation itself is performed in DWI space. For visualization, the helper exports downsampled display fibers in anchorNative and MNI coordinates by applying the approved DWI-to-anchorNative and anchorNative-to-MNI transforms.

Each seed-target tract records:

- requested seed side, seed ROI, seed variant, and target ROI;
- atlas label IDs and ROI voxel counts;
- selected streamline count and length summary from `tckstats`;
- density map in DWI space from `tckmap`;
- `VTA_exact_hit` count against the current Lead-DBS stimulation binary VTA resampled into DWI space, defined as any streamline point entering the binary VTA mask;
- `VTA_seed_hit` count, defined by rerunning the same seed-target query with `seed ∩ stimulation VTA` as the seed mask and the same target/waypoint;
- peak e-field per VTA-hit streamline, with the same `peak >= 200 V/m` threshold flag used by the exact FTR pipeline.

Seed-target outputs are written under:

```text
connectomics/fiber_vis/<stimLabel>/seed_target/native
connectomics/fiber_vis/<stimLabel>/seed_target/mni
connectomics/fiber_vis/<stimLabel>/seed_target/rois
connectomics/fiber_vis/<stimLabel>/seed_target/qc
connectomics/fiber_vis/<stimLabel>/seed_target/reports
connectomics/fiber_vis/<stimLabel>/seed_target/work
```

The native calculation files remain MRtrix `.tck` files in DWI space. The helper also writes VTK display files and Lead-DBS-compatible `.mat` files for figure display.

## MRtrix3 SIFT2 Seed-VTA-Target Analysis

The helper can additionally run a SIFT2-weighted visualization analysis focused on stimulation-covered seed tissue. This is separate from the exact FTR filtering and from the pairwise seed-target iFOD2 runs above.

The SIFT2 analysis uses:

- Seeds: `NAc ∩ stimulation VTA` and `ALIC ∩ stimulation VTA`, split by hemisphere.
- Anatomical seed ROIs for display: the full HybraPD NAc and ALIC masks.
- Targets: the existing ipsilateral target system except `NAc` and `ALIC`: `mPFC`, `OFC`, `ACC`, `amygdala`, `hippocampus`, `thalamus`, and anatomical `VTA`.
- Stimulation VTA: the Lead-DBS SimBio binary VTA. This is always named `stimulation VTA` in reports to distinguish it from the anatomical AAL3 VTA target.

The default whole-brain tractogram and display budgets are:

- `cfg.seedVtaSift2.wholebrainSelect = 5000000`
- `cfg.seedVtaSift2.displayBudget = 8000`
- `cfg.seedVtaSift2.displayBudgetMode = 'global'`

When rerunning after a small quality-control tractogram, increase `cfg.seedVtaSift2.wholebrainSelect` and set `cfg.seedVtaSift2.forceDownstream = true`. This reuses an already generated whole-brain `.tck` and SIFT2 weight file when present, but forces seed-VTA extraction, target classification, density maps, display tracts, display `.mat/.trk/.vtk` files, figures, and reports to be regenerated for the selected tractogram scale. This prevents small-sample display fibers from being reused with a larger summary table.

The workflow generates an ACT whole-brain iFOD2 tractogram, estimates SIFT2 weights, extracts streamlines intersecting each `seed ∩ stimulation VTA` mask, and then classifies those streamlines by target masks. Target assignment is exclusive:

- streamlines intersecting exactly one configured target are assigned to that target;
- streamlines intersecting more than one target are reported as `ambiguous`;
- streamlines intersecting no configured target are reported as `no_target`.

The main quantitative metric is SIFT2 weight sum. Raw streamline count is written only as QC. Target fractions are computed from exclusive target SIFT2 weight sums:

```text
P_target = W_target / sum(W_all_exclusive_targets)
```

SIFT2-weighted density maps are written for each non-empty target and should be interpreted as tractography-derived weighted streamline density, not true axon density. The 3D scene uses proportional display subsampling only. With the default `displayBudgetMode = 'global'`, the whole figure has one fixed display budget. Streamlines are allocated across all `side x seed x target` pathways according to their SIFT2 weight fraction in the full VTA-covered pathway system, then sampled within each target using SIFT2 weights. The older `displayBudgetMode = 'per_seed'` keeps one display budget per `side x seed` group and is intended only for inspecting target distributions within each seed group.

Global display allocation uses largest-remainder rounding:

```text
N_pathway = displayBudget * W_pathway / sum(W_all_exclusive_pathways)
```

The integer display counts are then rounded so that the total displayed streamline count is exactly `displayBudget`, subject to the available streamline count in each pathway.

Seed-VTA-SIFT2 outputs are written under:

```text
connectomics/fiber_vis/<stimLabel>/seed_vta_sift2/tracks
connectomics/fiber_vis/<stimLabel>/seed_vta_sift2/density
connectomics/fiber_vis/<stimLabel>/seed_vta_sift2/display
connectomics/fiber_vis/<stimLabel>/seed_vta_sift2/reports
connectomics/fiber_vis/<stimLabel>/seed_vta_sift2/work
```

## Interactive Figure Controls

The helper generates separate MNI-space and native-space Lead-DBS/MATLAB scene files:

- MNI scene: `figures/<subject>_<stimLabel>_mni_scene.fig`, using `FTR_normalized.mat`, MNI VTA/e-field, and MNI HybraPD ROI masks.
- Native scene: `figures/<subject>_<stimLabel>_native_scene.fig`, using `FTR_anat.mat` or `FTR.mat`, native VTA/e-field, and HybraPD ROI masks inverse-normalized into anchorNative space.

The seed-VTA-SIFT2 scene also writes separate native and MNI figures:

- Native scene: `seed_vta_sift2/figures/<subject>_<stimLabel>_seed_vta_sift2_native_scene.fig`.
- MNI scene: `seed_vta_sift2/figures/<subject>_<stimLabel>_seed_vta_sift2_mni_scene.fig`.

The helper can also summarize the SIFT2 results as a two-panel global contribution bar plot. The plot uses each exclusive `side x seed x target` pathway weight divided by the SIFT2 weight sum across all exclusive pathways, so all bars across both hemispheres sum to 100%. This is distinct from the seed-normalized `target_fraction` column in `seed_vta_sift2_summary.csv`. The default bar plot uses separate left/right panels, a Lead-DBS manuscript-style top strip, and seed colors `NAc=#82D143` and `ALIC=#3070B7`; the plot legend labels are `NAc` and `ALIC`, while the methods text clarifies that these refer to stimulation-VTA-intersecting seed pathways.

Each scene includes toolbar toggle buttons for every requested visualization object:

- HybraPD anatomical ROI buttons: `NAc R`, `NAc L`, `ALIC R`, and `ALIC L`.
- Lead-DBS visualization atlas buttons from `NAc_ALIC (Yu 2021 and Ewert 2017)` by default.
- VTA buttons: `VTA R` and `VTA L`.
- Fiber buttons for all five filtering stages on each side: `NAc_only`, `ALIC_only`, `NAc_ALIC_intersection`, `VTA_hit`, and `NAc_ALIC_VTA_hit`.
- Lead buttons generated by Lead-DBS for each electrode side.

All buttons are enabled by default. Clicking a button hides its object; clicking it again shows the object. Empty fiber bundles keep a toolbar button labeled with `0 fibers`; clicking it is a no-op so the empty set is explicitly visible in the interface. HybraPD ROI buttons are bound to persistent helper ROI patch handles generated from the ROI NIfTI masks, so `NAc R/L` and `ALIC R/L` continue to toggle correctly after reopening the `.fig`. Right-clicking helper-managed ROI, VTA, fiber, or lead buttons opens a lightweight display-control window for visibility, color, edge color, and alpha when those properties are available.

In seed-VTA-SIFT2 scenes, the `NAc∩stimulation VTA` and `ALIC∩stimulation VTA` intersection ROI objects are created but hidden by default. Their toolbar buttons remain available and can be turned on for inspection. This keeps the default scene focused on anatomical seed ROIs, stimulation VTA, target ROIs, and proportional pathway fibers.

Default helper-scene appearance is intentionally fixed for reproducible figure export:

- Anatomical NAc ROIs are green (`#82D143`).
- Anatomical ALIC ROIs are blue (`#3070B7`).
- ROI alpha defaults to `0.20`.
- Fiber alpha defaults to `0.10`.
- Electrode contacts are displayed in black.
- Electrode insulation and the helper-only electrode extension are displayed in light gray-white.
- When `cfg.figure.electrodeDisplayLengthMm = 200`, the helper adds a 200 mm visual extension along each electrode axis for figure display only. This does not change electrode coordinates, stimulation contacts, VTA, e-field, or fiber calculations.

Set `cfg.figure.sceneFileSuffix` to write these styled figures as additional files instead of replacing existing `.fig` and `.png` scene files.

Scene text annotations drawn by ROI, atlas, or electrode-label objects are hidden by default in the saved figure. The helper re-hides these text annotations after toolbar toggles and after reopening a saved `.fig`, and it excludes MATLAB `text` handles from atlas and lead toggle targets when region labels are disabled. Object names remain available through toolbar tooltips and right-click control windows.

The helper keeps the visualization control logic close to `ea_mnifigure`: the scene is still created by `ea_elvis`, Lead-DBS creates the lead toolbar buttons, and helper code rebinds the saved `.fig` callbacks so they remain functional after reopening.

When writing the `.fig`, the helper stores the main scene objects and toolbar callbacks but does not serialize transient Anatomy Slices or Atlas Control windows. The scene is created with Lead-DBS atlas-control auto-open suppressed to avoid MATLAB/Java tree serialization warnings. These windows can be recreated after reopening the scene through `mh_fiber_open_scene(figPath)` or the native Lead-DBS toolbar buttons.

Before exporting the `.png`, the helper enforces a minimum scene figure size and briefly makes the scene visible so hidden batch figures do not export as tiny placeholder images or blank OpenGL captures.

The helper scene also opens the native Lead-DBS Anatomy Slices control window by default. Use that window to switch the backdrop between available MNI templates, patient Pre-OP/Post-OP images, or `Choose...` for a custom `.nii` file. The X/Y/Z slice controls and transparency fields are the standard Lead-DBS controls. Helper scenes lock the 3D slice planes against direct mouse dragging and disable the main-scene `Slide Slices` toolbar mode, so slice position changes should be made through the Anatomy Slices window while mouse dragging in the main scene remains reserved for camera navigation.

For non-interactive batch runs, disable the figure windows before calling `mh_fiber_run`:

```matlab
cfg.figure.openAfterRun = false;
cfg.figure.openAnatomyControl = false;
cfg.figure.closeAfterSave = true;
```

## Example

```matlab
cd('/Users/mojackhu/Github/leaddbs');
addpath(genpath(pwd));

cfg = mh_fiber_default_config( ...
    '/Users/mojackhu/Desktop/ASD/derivatives/leaddbs/sub-001', ...
    'clinical_L4R4_5V_L2R2_3V');
result = mh_fiber_run(cfg);
```

To reopen an existing scene with the Anatomy Slices control window:

```matlab
figPath = '/Users/mojackhu/Desktop/ASD/derivatives/leaddbs/sub-001/connectomics/fiber_vis/clinical_L4R4_5V_L2R2_3V/figures/sub-001_clinical_L4R4_5V_L2R2_3V_mni_scene.fig';
h = mh_fiber_open_scene(figPath);
```

Or run the case script:

```bash
matlab -batch "cd('/Users/mojackhu/Github/leaddbs'); addpath(genpath(pwd)); run('/Users/mojackhu/Github/leaddbs/my_helper/fiber/pipelines/sub001/run_sub001_fiber_vis.m')"
```
