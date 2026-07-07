# Four-Model Execution Implementation Notes

This note records executable implementation layers for `four_model_execution_plan.md`.

The full four-model program is intentionally gated. The current codebase now includes readiness, observed A/B/C/D branches, C/D source resolvers, consolidated status reporting, final-model worklist/readiness auditing, formal permutation/bootstrap/jitter layers for available final targets, final reporting/readiness summaries, and shared resolver utilities. Full fiber density/FDR/enrichment display outputs remain deferred until the required density and label caches exist.

## Pause Checkpoint

Execution has resumed through the 2026-07-07 status, formal-target, and
formal-readiness refresh. The latest observed branches and status files were
regenerated from the single retained worktree:

```text
/Users/mojackhu/Github/leaddbs
```

Current refreshed outputs:

```text
/Volumes/VAL/STNSNr/summary/four_model_execution/gate_status/four_model_gate_status.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/status/four_model_execution_status.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/status/four_model_execution_status.md
/Volumes/VAL/STNSNr/summary/four_model_execution/formal_worklist/four_model_formal_target_worklist.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/formal_worklist/four_model_formal_target_worklist.md
/Volumes/VAL/STNSNr/summary/four_model_execution/formal_readiness/four_model_formal_readiness.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/formal_readiness/four_model_formal_readiness.md
/Volumes/VAL/STNSNr/summary/four_model_execution/direct_voxel_formal_permutation/direct_voxel_formal_permutation_summary.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/direct_voxel_formal_bootstrap/direct_voxel_formal_bootstrap_summary.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/direct_voxel_formal_jitter/direct_voxel_formal_jitter_summary.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/normative_fiber_smoke_permutation/normative_fiber_smoke_permutation_summary.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/normative_fiber_formal_permutation/normative_fiber_formal_permutation_summary.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/normative_fiber_formal_bootstrap/normative_fiber_formal_bootstrap_summary.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/normative_fiber_sensitivity_readiness/normative_fiber_sensitivity_readiness_summary.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/final_reporting/four_model_final_report.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/final_reporting/four_model_figure_output_readiness.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/all_endpoint_reporting/four_model_all_endpoint_report.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/all_endpoint_reporting/four_model_all_endpoint_missing_work.csv
```

Current state:

```text
A direct voxel: SOURCE_ACCEPTED_ERROR_NONPREDICTIVE
B PPMI/MGH/dTOR normative fiber: SOURCE_ACCEPTED_ERROR_NONPREDICTIVE
C direct voxel: OBSERVED_COMPLETE_PRIMARY_ERROR_NONPREDICTIVE
D PPMI normative fiber: OBSERVED_COMPLETE_PRIMARY_ERROR_NONPREDICTIVE
D dTOR normative fiber: OBSERVED_COMPLETE_PRIMARY_ERROR_NONPREDICTIVE
formal target worklist: 4/7 READY_FOR_FORMAL_RESAMPLING; 3/7 OBSERVED_ROBUSTNESS_NO_FORMAL_RESAMPLING
formal readiness audit: 4/4 formal targets READY_FOR_FORMAL_DRIVER
ULF component e-fields: 64/64 available
direct-voxel formal permutation: A and C complete at B=10000, seed=42
direct-voxel formal bootstrap: A and C complete at B=10000, seed=42
direct-voxel formal jitter: A and C complete at B=1000, seed=42, FWHM=2 mm
dTOR normative-fiber smoke permutation: B_DTOR and D_DTOR complete at B=1000, seed=42
dTOR normative-fiber formal permutation: B_DTOR and D_DTOR complete at B=10000, seed=42
dTOR normative-fiber formal bootstrap: B_DTOR and D_DTOR complete at B=10000, seed=42
dTOR normative-fiber OSS/jitter sensitivity readiness: not_run_missing_inputs
final reporting/readiness: 7 rows; n=16 hypothesis-generating; A/C direct maps ready; fiber density/label caches missing
C gain/total-ULF observed sensitivity outputs: complete; resampling_status = not_run_observed_only
all-endpoint reporting: 61 rows; A all-endpoint source-resolver rows = 30; missing-work audit rows = 6, with 2 C observed sensitivity rows detected and 4 rows still not run
full fiber density/FDR/enrichment figure-grade outputs: not run
```

Current direct-voxel formal permutation results:

```text
A direct voxel:
  observed rho = -0.0265487881
  p_plus_one_two_sided = 0.9455054495
  B = 10000

C ULF direct voxel no_delta_hf final model:
  observed rho = 0.9189995239
  p_plus_one_two_sided = 0.2324767523
  B = 10000
```

Current dTOR normative-fiber smoke permutation results:

```text
B_DTOR HF normative fiber:
  observed rho = -0.1828916512
  p_plus_one_two_sided = 0.6343656344
  B = 1000

D_DTOR ULF normative fiber no_delta_hf final model:
  observed rho = 0.9410908586
  p_plus_one_two_sided = 0.0879120879
  B = 1000
```

No additional full fiber density/FDR/enrichment drivers should be started until
the required density and label caches are created or supplied. OSS-DBS
activation and fiber jitter sensitivity should remain explicit missing-input
statuses until their required sidecars exist.

The consolidated status manifest records git provenance for the worktree that
generated the status refresh, including branch, HEAD commit, and dirty files.
Each status CSV row also records whether its referenced `latest_manifest`
contains git or local-patch provenance. Existing branch manifests generated
before this policy may be marked `missing_git_or_patch_provenance`; that marker
means provenance is incomplete and does not by itself rerun or invalidate the
observed outputs.

The consolidated status report also resolves final-model fields from the current
source/endpoint classifiers. HF rows record `hf_final_model_source`,
`hf_final_model_role`, and `hf_final_model_status`. ULF rows record
`ulf_final_model_branch`, `ulf_final_model_role`, and
`ulf_final_model_status`; formal, jitter, OSS, and display-layer work attach to
that final model rather than to a manually selected reporting branch.

The final reporting layer consumes the consolidated status, formal worklist,
formal readiness audit, formal summary CSVs, and fiber sensitivity-readiness
CSV. It writes:

```text
/Volumes/VAL/STNSNr/summary/four_model_execution/final_reporting/four_model_final_report.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/final_reporting/four_model_final_report.md
/Volumes/VAL/STNSNr/summary/four_model_execution/final_reporting/four_model_figure_output_readiness.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/final_reporting/four_model_final_reporting_manifest.json
```

This layer does not fit models, rerun resampling, or fabricate unavailable
fiber density/FDR/enrichment outputs. It records `ready_from_existing_maps` for
A/C direct-voxel display sources and `not_run_missing_density_label_cache` for
fiber figure-output readiness when the required caches are absent.

The all-endpoint reporting layer consumes the existing A all-scale
source-resolver scan, observed branch summary, final report, and discovered
branch manifests. It writes:

```text
/Volumes/VAL/STNSNr/summary/four_model_execution/all_endpoint_reporting/four_model_all_endpoint_report.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/all_endpoint_reporting/four_model_all_endpoint_report.md
/Volumes/VAL/STNSNr/summary/four_model_execution/all_endpoint_reporting/four_model_all_endpoint_missing_work.csv
/Volumes/VAL/STNSNr/summary/four_model_execution/all_endpoint_reporting/four_model_all_endpoint_reporting_manifest.json
```

This layer does not fit gain, same-day immediate, or total-ULF sensitivity
models. It records those absent C/D outputs as
`not_run_missing_observed_outputs` so downstream reporting can distinguish
"not run" from "failed model".

## Execution Root Availability

The canonical execution documents use `/Volumes/VAL/STNSNr` as the STNSNr VAL
root. During this resumed Codex run, `/Volumes/VAL` was initially unavailable,
so one M0 readiness check was run against the local mirror
`/Users/mojackhu/Research/STNSNr` and reported failures because that mirror does
not contain the complete external-drive project structure.

After the external drive was mounted, the canonical root was available again:

```text
/Volumes/VAL/STNSNr
```

Subsequent execution should use the canonical `/Volumes/VAL/STNSNr` defaults
unless the drive is unavailable again. The temporary local-root readiness output
is an environment diagnostic only and is not the authoritative four-model status.

## Backend / Workflow Separation

Implementation must distinguish reusable backend code from STN/SNr project
workflow code.

Reusable backend code belongs under:

```text
my_helper/fiber/core/
```

It should expose parameterized functions for statistics, feature matrices,
NIfTI/connectome IO, scoring, QC, and manifest writing. Backend code must not
make project paths, atlas selections, endpoint defaults, subject IDs, or
connectome choices part of the algorithm. Any convenience defaults must be
overridable by the caller.

Generic NIfTI writers must accept an explicit support mask. Continuous or
statistical maps write `NaN` outside support, not `0`; coverage/count maps and
binary masks are the only exception.

Project workflow code belongs under:

```text
my_helper/fiber/stnsnr/
```

Workflow scripts resolve STN/SNr-specific paths, endpoints, connectomes, atlas
registries, and branch names, then pass an explicit config into backend
functions. The `stnsnr/` directory remains an orchestration layer rather than a
helper-function directory.

## Implemented Layer

The M0 readiness entry point is:

```text
my_helper/fiber/stnsnr/run_stnsnr_four_model_m0_readiness.py
```

Reusable implementation lives in:

```text
my_helper/fiber/core/analysis/stnsnr_four_model_readiness.py
```

The pipeline script only resolves the repository path and calls the reusable core function. This preserves the rule that `my_helper/fiber/stnsnr` contains only orchestration scripts.

## M0 Scope

The readiness run verifies and records:

- Python execution environment, including the Conda `leaddbs` package versions needed for statistical post-processing.
- MATLAB executable availability and optional `ea_flip_lr_nonlinear` callability.
- `/Volumes/VAL/STNSNr` mount, `reference/`, `summary/`, and output-root writability.
- Raw clinical score workbook availability, required columns, subject count, default HF endpoint availability, ULF chronic delta/reconstructibility status, and immediate endpoint availability.
- `followup_stimulation.xlsx` `Contact Parameters` availability, required columns, subject count, target/frequency sanity, and expected MNI raw `sim-efield` path availability. Continuous stimulation uses the condition-level VTA folder. Alternating stimulation is discovered at subprogram/contact level with `alt_<side>_<target>_c<contact>_row*` folder names.
- Public connectome `data.mat` availability under the asset root.
- Connected-region atlas availability under the asset root.
- Scale direction table generation with `SE-ADL` marked higher-is-better and the current score scales marked lower-is-better.

Historical Codex worktrees may not contain gitignored heavy assets such as
`templates/` and `connectomes/`. The M0 tool therefore accepts an explicit
`--asset-root` and otherwise falls back to `/Users/mojackhu/Github/leaddbs`
when the current worktree lacks those assets.

## Outputs

Default output root:

```text
/Volumes/VAL/STNSNr/summary/four_model_execution/m0_readiness/
```

Each run writes a timestamped directory:

```text
run-YYYYMMDD-HHMMSS/
  four_model_m0_readiness_manifest.json
  four_model_m0_readiness_checks.csv
  four_model_m0_endpoint_availability.csv
  four_model_m0_efield_availability.csv
  scale_direction_table.csv
  environment/
    conda_leaddbs_explicit.txt
    pip_freeze.txt
```

The manifest records the overall status. Missing data are not silently ignored. The default run is report-only and exits `0`; `--strict` makes any `FAIL` check exit non-zero.

## M1 Shared Statistical Kernel

The first M1 code layer adds reusable statistical primitives only. It does not read real E-field matrices and does not write model outputs. The kernel is designed so the four model drivers can share the same exact baseline-adjusted partial Spearman, fold coverage, scoring, prediction, and permutation utilities.

Reusable implementation lives in:

```text
my_helper/fiber/core/analysis/stnsnr_four_model_stats.py
```

The smoke/equivalence self-test entry point is:

```text
my_helper/fiber/stnsnr/run_stnsnr_four_model_m1_selftest.py
```

The self-test verifies:

- vectorized partial Spearman matches a brute-force per-feature reference;
- LOOCV fold coverage by held-out subtraction matches a brute-force training-only coverage calculation;
- `HFScore_mean_main` style mean map scoring matches the manual formula;
- fiber `NetFiberScore = SweetPeak5 - SourPeak5` uses deterministic top-k selection and produces finite scores;
- Freedman-Lane permuted outcomes preserve the nuisance fitted component and are reproducible with seed `42`;
- plus-one two-sided permutation p values use the documented formula.

This layer is intentionally model-agnostic. It does not define HF/ULF paths, does not create sidecars, does not perform image/fiber sampling, and does not run formal `B=10000` loops.

## Shared Resolver Utilities

The shared resolver layer is:

```text
my_helper/fiber/core/analysis/stnsnr_four_model_resolver.py
```

It now contains reusable helpers for:

```text
pre-specified versus scan-fallback source resolution
adjacent-grid support counting
MAE/RMSE prediction-status classification
safe Pearson/Spearman reporting metrics
branch-specific nuisance design validation
```

Direct voxel and normative fiber ULF observed drivers import these helpers
instead of maintaining separate copies. Model-specific hard computability
predicates remain in the model drivers because voxel and fiber support
quantities differ.

Self-test:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/core/analysis/stnsnr_four_model_resolver_selftest.py
```

## ULF Dependency Identifiers

ULF readiness and status code use explicit HF dependency IDs from the current
status CSV:

```text
C direct voxel depends on A
D PPMI normative fiber depends on B_PPMI
D dTOR normative fiber depends on B_DTOR
```

There is no generic `B` status row. Additional D connectome variants must
bind to their matching `B_<connectome>` dependency explicitly.

## HF Direct Voxel Smoke Driver

This executable layer implements the primary HF direct voxel observed branch:

```text
model = HF direct voxel
scale = MDS-UPDRS III score (STN, 3 m) by default
branch = tau200 / partial_spearman
validation = observed LOOCV
resampling = not run
```

Entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_hf_direct_voxel_smoke.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_hf_direct_voxel_smoke.py
```

This driver reads existing raw `sim-efield` files. It does not create missing e-fields. Alternating same-side subprograms are max-combined in the common right-canonical sampled feature space, which also handles the real case where subprogram local e-field grids differ. Left-side subprogram e-fields are flipped with `ea_flip_lr_nonlinear` into the right canonical space before sampling. The driver samples both right e-fields and left-to-right flipped e-fields on the right MNI brainmask grid, averages them per subject, builds `Candidate` from `180 V/m`, and runs the `tau200 / Coverage>=5` partial-Spearman observed LOOCV branch.

Because `ea_flip_lr_nonlinear` uses interpolation, a flipped E-field magnitude image can contain very small negative interpolation artifacts. The smoke driver clamps negative sampled E-field values to `0` and records the count and minimum value in QC. This is a numeric data-integrity correction for an E-field magnitude image, not a modeling threshold.

Outputs are written under:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/<scale_slug>/
  preprocess/
  tau200/partial_spearman/
```

The smoke driver intentionally omits `direct_voxel_HF_permutation_summary.csv` and `direct_voxel_HF_bootstrap_se.nii.gz`; those belong to later gated formal/smoke resampling rounds.

## HF Normative Connectome Fiber Smoke Driver

This B-model executable layer targets the cheapest real public connectome first:

```text
model = HF normative connectome fiber
connectome = PPMI 85 (Ewert 2017) by default
scale = MDS-UPDRS III score (STN, 3 m) by default
legacy/current output branch = peak_efield_tau800_primary
revised spec branch = peak_efield_tau800_cov5_primary
validation = observed LOOCV
resampling = not run
```

Entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_hf_normative_fiber_smoke.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_hf_normative_fiber_smoke.py
```

This driver reads the full public connectome from MATLAB v7.3/HDF5 `data.mat` using chunked fiber blocks. It does not target-restrict streamlines. For each subject, right-sided raw `sim-efield` and left-sided `ea_flip_lr_nonlinear` flipped e-fields are sampled along the same right-canonical streamline coordinates. Alternating same-side subprograms are max-reduced in streamline point space before the bilateral average.

The first executable branch writes a subject-by-fiber exposure sidecar, applies:

```text
tau = 800 V/m
coverage = Coverage>=5
Coverage_tau(l) = sum_i I[X_HF_i(l) > tau]
F_candidate_tau = Coverage_tau(l) >= 5
```

and then runs the partial-Spearman `NetFiberScore` observed LOOCV branch. Existing outputs use the legacy folder/branch name `peak_efield_tau800_primary`; documentation now maps that branch to revised `peak_efield_tau800_cov5_primary` until a future code/output migration renames directories. Formal `B=10000`, OSS-DBS, FDR/density/display, dTOR processing, and the revised `tau_coverage_source_resolver_scan` remain later gated stages.

The driver supports `--max-fibers` only for development self-tests and debugging. Production PPMI smoke runs should leave it unset so the candidate universe remains the full PPMI connectome.

## Four-Model Status Summary

The current status tool reads manifests/QC files and writes a compact execution table:

```text
my_helper/fiber/stnsnr/run_stnsnr_four_model_gate_status.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_four_model_gate_status.py
```

The tool does not run any model. Any older stop/go fields emitted by this code are historical execution metadata. Intended A direct-voxel dependency decisions must come from `hf_voxel_source_status` and `hf_voxel_prediction_status`; intended B normative-fiber decisions must come from `hf_norm_fiber_source_status` and `hf_norm_fiber_prediction_status`.

## ULF Component Readiness Gate

This executable layer audits whether the C and D ULF add-on models can start
without violating their component-separation requirements. It does not run ULF
voxel maps, ULF fiber maps, DeltaHFScore scoring, permutation, bootstrap, OSS,
or display outputs.

Entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_ulf_component_readiness.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_ulf_component_readiness.py
```

The readiness check verifies:

- chronic ULF endpoint reconstruction from `subject_effect_origin.xlsx` for the
  default total motor scale;
- same-day immediate endpoint availability, recorded as unavailable when the raw
  table has no immediate rows;
- frequency-component classification from `followup_stimulation.xlsx` with
  `HF >= 100 Hz` and `ULF <= 50 Hz`;
- component-specific `3m/STN+SNr` raw `sim-efield` availability for every
  subject, side, and frequency-classified component row;
- A/B dependency status from the current status CSV, while intended direct-voxel
  branch roles are refreshed from `hf_voxel_source_status` and
  `hf_voxel_prediction_status`.

The readiness check follows the same e-field path logic as the target-component VTA
distribution code:

- observed alternating components use observed subprogram e-fields under
  `stnsnr_vta_<ID>_<phase>_STNplusSNr_alt_<side>_<target>_c<contact>_row<index>`;
- observed single-target continuous components use the corresponding continuous
  condition e-field;
- mixed continuous STN+SNr components use the counterfactual target-component
  e-field under `stnsnr_target_component_<ID>_<phase>_STNplusSNr_<side>_<target>`.

The readiness check must not substitute the mixed `STN+SNr` condition-level e-field for
frequency-component HF or ULF e-fields. If the required observed subprogram or
target-component e-fields are missing, C/D remain not executable even when mixed
condition VTA outputs, thresholded VTA masks, or component stimulation-parameter
folders exist.

Outputs are written under:

```text
/Volumes/VAL/STNSNr/summary/four_model_execution/ulf_component_readiness/run-YYYYMMDD-HHMMSS/
  ulf_component_readiness_manifest.json
  ulf_component_readiness_checks.csv
  ulf_component_endpoint_reconstruction.csv
  ulf_component_efield_availability.csv
```

Expected current status is a hard input failure for C/D model execution if the
component folders contain only stimulation parameter files and no raw
`sim-efield` NIfTI files. This is still forward progress: it prevents an invalid
ULF analysis from being run with a mixed HF+ULF field while recording exactly
which component e-fields must be generated next.

## Commands

Run from the worktree:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_four_model_m0_readiness.py \
  --run-matlab-check
```

Use `--strict` when M0 is acting as a hard gate before starting model computation.

Run the M1 shared-kernel self-test:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_four_model_m1_selftest.py
```

Run the HF direct voxel observed smoke driver:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_hf_direct_voxel_smoke.py
```

Run the HF normative fiber observed smoke driver:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_hf_normative_fiber_smoke.py
```

Summarize legacy A/B status:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_four_model_gate_status.py
```

Run the ULF component readiness check:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_component_readiness.py
```

## Four-Model Execution Status Report

The current execution state is distributed across M0 readiness, A/B primary
status, and ULF component readiness outputs. The status report layer
collects those artifacts into one machine-readable and human-readable snapshot.
It does not run any model and does not change resolver/status fields. It should
also detect completed direct-voxel formal permutation summaries and mark A/C as
`FORMAL_PERMUTATION_COMPLETE_BOOTSTRAP_NOT_STARTED` when the final branch has a
complete `B=10000` permutation summary. Observed-robustness-only normative
connectome rows are marked `OBSERVED_ROBUSTNESS_NO_FORMAL_RESAMPLING` rather
than `NOT_STARTED_FORMAL_RESAMPLING`.

Entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_four_model_execution_status.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_four_model_execution_status.py
```

The report records, for each model:

- whether required primary observed outputs exist;
- current resolver/status decision and observed LOOCV metrics;
- whether downstream dependencies are locked or exploratory;
- whether missing inputs prevent execution;
- whether formal resampling is allowed, deferred by status, or not yet applicable.

Default outputs:

```text
/Volumes/VAL/STNSNr/summary/four_model_execution/status/
  four_model_execution_status.csv
  four_model_execution_status.md
  four_model_execution_status_manifest.json
```

Run the consolidated status report:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_four_model_execution_status.py
```

## Final-Model Formal Target Worklist

The formal target worklist is the first executable layer after final-model
classification. It does not run permutation, bootstrap, jitter, OSS-DBS, or
display generation. It reads the consolidated execution status and writes a
machine-readable list of final model branches/sources that should be consumed by
future formal resampling drivers.

Entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_four_model_formal_worklist.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_four_model_formal_worklist.py
```

Default outputs:

```text
/Volumes/VAL/STNSNr/summary/four_model_execution/formal_worklist/
  four_model_formal_target_worklist.csv
  four_model_formal_target_worklist.md
  four_model_formal_target_worklist_manifest.json
```

Rows with `final_model_error_predictive` or `final_model_error_nonpredictive`
are marked `READY_FOR_FORMAL_RESAMPLING` only if their model family defines a
formal inference target. Current formal targets are A, B_DTOR, C, and D_DTOR.
B_PPMI, B_MGH, and D_PPMI are retained as observed robustness outputs and are
marked `OBSERVED_ROBUSTNESS_NO_FORMAL_RESAMPLING`. Rows with no final model are
marked `NO_FINAL_MODEL`. This worklist is intentionally independent of manual
reporting-branch selection.

Run the worklist:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_four_model_formal_worklist.py
```

## Final-Model Formal Readiness Audit

The formal readiness audit is the next lightweight layer after the final-model
formal target worklist. It does not run formal permutation, bootstrap, spatial
jitter, OSS-DBS, or display generation. It reads the worklist and verifies that
each `READY_FOR_FORMAL_RESAMPLING` row points to an existing branch manifest and
to the branch-level QC, score, and LOOCV prediction files required by future
formal drivers.

Entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_four_model_formal_readiness.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_four_model_formal_readiness.py
```

Required branch files are inferred from the manifest filename:

```text
direct_voxel_HF_generation_manifest.json:
  direct_voxel_HF_mapping_qc.json
  direct_voxel_HF_scores.csv
  direct_voxel_HF_loocv_predictions.csv

normative_HF_fiber_generation_manifest.json:
  normative_HF_fiber_mapping_qc.json
  normative_HF_fiber_scores.csv
  normative_HF_fiber_loocv_predictions.csv

direct_voxel_ULF_only_generation_manifest.json:
  direct_voxel_ULF_only_mapping_qc.json
  direct_voxel_ULF_only_scores.csv
  direct_voxel_ULF_only_loocv_predictions.csv

normative_ULF_fiber_generation_manifest.json:
  normative_ULF_fiber_mapping_qc.json
  normative_ULF_fiber_scores.csv
  normative_ULF_fiber_loocv_predictions.csv
```

Default outputs:

```text
/Volumes/VAL/STNSNr/summary/four_model_execution/formal_readiness/
  four_model_formal_readiness.csv
  four_model_formal_readiness.md
  four_model_formal_readiness_manifest.json
```

Run the audit:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_four_model_formal_readiness.py
```

## Direct-Voxel Final-Model Formal Permutation

The direct-voxel formal permutation layer is the first expensive formal layer.
It covers the A and C final models only. B_DTOR and D_DTOR are normative-fiber
formal targets and require a separate chunked fiber implementation; B_PPMI,
B_MGH, and D_PPMI remain observed robustness outputs.

Entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_direct_voxel_formal_permutation.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_direct_voxel_formal_permutation.py
```

Default outputs are written into the final branch directories:

```text
A:
  direct_voxel_HF_permutation_summary.csv
  direct_voxel_HF_permutation_null_stats.npy

C:
  direct_voxel_ULF_only_permutation_summary.csv
  direct_voxel_ULF_only_permutation_null_stats.npy
```

The driver consumes the formal readiness CSV and processes only rows with
`formal_readiness_status = READY_FOR_FORMAL_DRIVER` and model IDs `A` or `C`.
Each permutation uses Freedman-Lane residual permutation with seed `42` and
reruns the direct-voxel LOOCV map, score, nuisance-only baseline, and held-out
prediction steps. It does not implement bootstrap, jitter, or fiber formal
permutation.

Run the formal A/C permutation:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_direct_voxel_formal_permutation.py \
  --n-permutations 10000
```

## dTOR Normative-Fiber Smoke Permutation

The dTOR normative-fiber smoke permutation layer covers B_DTOR and D_DTOR final
branches. It is exact for the selected dTOR peak-E-field model semantics: each
permuted outcome reruns fold-specific candidate selection, `rho`, `M`,
`F+`/`F-`, `NetFiberScore`, nuisance-only baseline, held-out prediction, and
LOOCV Spearman rho over the selected tau/Coverage candidate universe. It is not
formal `B=10000` inference and does not implement bootstrap, jitter, or OSS.

Entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_normative_fiber_smoke_permutation.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_normative_fiber_smoke_permutation.py
```

Default outputs:

```text
B_DTOR branch:
  normative_HF_fiber_smoke_permutation_summary.csv
  normative_HF_fiber_smoke_permutation_null_stats.npy

D_DTOR final branch:
  normative_ULF_fiber_smoke_permutation_summary.csv
  normative_ULF_fiber_smoke_permutation_null_stats.npy

Cross-target summary:
  /Volumes/VAL/STNSNr/summary/four_model_execution/normative_fiber_smoke_permutation/normative_fiber_smoke_permutation_summary.csv
```

Run the dTOR smoke permutation:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_normative_fiber_smoke_permutation.py \
  --n-permutations 1000
```

## ULF Component E-field Worklist

When the ULF readiness check reports missing component-specific e-fields, the
worklist layer converts the latest readiness CSV into an explicit queue. It
does not run MATLAB and does not generate e-fields; it only records which
components must be generated before any ULF voxel or fiber model can execute
without mixing HF and ULF fields.

Entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_ulf_component_efield_worklist.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_ulf_component_efield_worklist.py
```

Default outputs:

```text
/Volumes/VAL/STNSNr/summary/four_model_execution/ulf_component_efield_worklist/
  ulf_component_efield_worklist.csv
  ulf_component_efield_worklist_manifest.json
```

The current expected missing items are continuous mixed STN+SNr
counterfactual target-component e-fields. Existing observed alternating
subprogram e-fields are not included in the missing worklist.

Run the worklist generator:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_component_efield_worklist.py
```

## HF Direct Voxel Source Resolver

The executable resolver layer replaces the older candidate-level
classification with the direct-voxel source resolver from
`hf_3m_direct_voxel_model.md`. It reads the existing all-endpoint Round 2
tau/Coverage scan outputs and writes an automatic summary of which HF endpoints
have a stable source for downstream ULF `DeltaHFScore` construction.

The classifier is implemented inside the existing tau/Coverage scan module:

```text
my_helper/fiber/core/analysis/stnsnr_hf_direct_voxel_posthoc_threshold_scan.py
```

and exposed through the existing pipeline entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_hf_direct_voxel_posthoc_threshold_scan.py
```

Source-resolver refresh command without recomputing the 60-cell scans:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_hf_direct_voxel_posthoc_threshold_scan.py \
  --all-scales \
  --plot-only
```

Current resolver outputs:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/hf/posthoc_threshold_scan_all_scales/
  all_scales_posthoc_threshold_scan_long.csv
  all_scales_posthoc_threshold_scan_summary.csv
  all_scales_posthoc_threshold_scan_manifest.json
```

The intended resolver uses scan-table evidence only for computability and local
support: `n_subjects >= 12`, `n_voxels_full >= 20`, `fold_n_voxels_min >= 10`,
nonconstant `HFScore`, finite predictions, and adjacent passing grid cells on
the declared tau/Coverage grid. It first tests `tau200/Coverage>=5`; only if
that source is not accepted does it choose a fallback by distance to the
pre-specified grid, adjacent support count, `fold_n_voxels_min`, stricter
Coverage, and higher tau. MAE/RMSE define `hf_voxel_prediction_status`; `Q2`
and LOOCV Spearman rho are report metrics.

## ULF Direct Voxel Observed Driver

The C-model observed executable layer runs the core ULF direct voxel branches.
It is intentionally limited to LOOCV observed modeling; formal permutation,
bootstrap, and jitter are separate final-model drivers. Gain and total-ULF
sensitivity outputs are handled by the separate observed-only sensitivity
driver below. The same-day immediate endpoint family remains not implemented.

Entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_ulf_direct_voxel_observed.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_ulf_direct_voxel_observed.py
```

Lightweight implementation self-test:

```text
my_helper/fiber/core/analysis/stnsnr_ulf_direct_voxel_observed_selftest.py
```

Default endpoint:

```text
post scale = MDS-UPDRS III score (STN+SNr, 3 m)
HF reference scale = same base scale under STN, 3 m
tau = 200 V/m
Coverage>=5
estimator = baseline-adjusted partial Spearman
```

The driver reads the latest `ulf_component_efield_availability.csv`, samples
component-specific HF and ULF raw `sim-efield` files into the same right
canonical brainmask feature space used by the HF direct voxel driver, and
creates:

```text
E_HF_component_i(v)  = bilateral average of HF component e-fields
E_ULF_component_i(v) = bilateral average of ULF component e-fields
X_ULF_only_i(v)      = E_ULF_component_i(v) when ULF is active and HF is not active
```

Same-side same-frequency rows are max-combined before bilateral averaging.
Left-sided fields are flipped with `ea_flip_lr_nonlinear`. The driver does not
generate missing component e-fields.

Both core branches are executed when inputs allow:

```text
tau200/partial_spearman_no_delta_hf
tau200/partial_spearman_delta_hf_adjusted
```

Under the revised A resolver, both branches are run when a stable HF voxel source
exists. The DeltaHF-adjusted branch is primary only when
`hf_voxel_prediction_status = error_predictive`; otherwise no-DeltaHF is primary.
If the HF resolver returns `absent_no_stable_grid`, only no-DeltaHF should run for
that endpoint.

For the DeltaHF-adjusted branch, `DeltaHFScore` is computed fold-locally. In
each ULF LOOCV fold, the driver refits the matched HF direct voxel map from
training patients only, projects both the HF-only reference component and the
HF component under HF+ULF programming onto that training-fold map, and subtracts
the two scores. The held-out patient never contributes to the fold-specific HF
map, ULF map, ULF scoring set, or final prediction model.

Default outputs:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<scale_slug>/
  preprocess/
  tau200/partial_spearman_no_delta_hf/
  tau200/partial_spearman_delta_hf_adjusted/
```

Each branch writes observed scores, LOOCV predictions, NIfTI maps, QC JSON, and
a generation manifest. The branch manifests record `ulf_primary_branch`,
`delta_hfscore_role`, `hf_voxel_source_status`, `hf_voxel_prediction_status`,
`ulf_voxel_source_status`, `ulf_voxel_prediction_status`,
`ulf_endpoint_model_status`, `ulf_branch_input_status`,
`branch_nuisance_design_status`, and `resampling_status=not_run_observed_only`.

The ULF branch resolver mirrors the HF direct-voxel split between source
stability and prediction error. Its hard computability filter is
`n_subjects >= 12`, `n_voxels_full >= 20`, `fold_n_voxels_min >= 10`,
nonconstant `ULFScore_mean_main`, valid branch-specific nuisance design, and
finite held-out predictions. The nuisance design is branch-specific:
`intercept + Y_HF_ref` for no-DeltaHF and
`intercept + Y_HF_ref + DeltaHFScore` for DeltaHF-adjusted. MAE/RMSE are
compared against that branch's nuisance-only baseline to assign
`ulf_voxel_prediction_status`. ULF statuses qualify the selected branch as
stable/error-predictive or not; they do not change the branch role assigned from
the matched HF resolver.

Current C source-resolver output:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/mds_updrs_iii_score_stn_snr_3_m/tau_coverage_source_resolver_scan/
  direct_voxel_ULF_only_tau_coverage_source_resolver_scan.csv
  direct_voxel_ULF_only_tau_coverage_source_resolver_manifest.json

no_delta_hf:        pre_specified_accepted + error_nonpredictive at tau200/Coverage>=5
delta_hf_adjusted:  pre_specified_accepted + error_predictive at tau200/Coverage>=5
endpoint status:    primary_branch_error_nonpredictive
```

The consolidated execution status reporter treats C as
`OBSERVED_COMPLETE_PRIMARY_ERROR_NONPREDICTIVE` because the matched A source is
accepted but `error_nonpredictive`, so the HF-derived intended primary branch is
no-DeltaHF.

Run the C source resolver:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_direct_voxel_observed.py \
  --source-resolver-scan
```

## ULF Direct Voxel Gain / Total-ULF Sensitivity Driver

The C-model gain/total-ULF sensitivity layer is observed-only and
chronic-endpoint-only. It reuses the existing C observed output and
preprocessing products when available, and writes:

```text
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau200/partial_spearman_gain_endpoint/
/Volumes/VAL/STNSNr/summary/direct_voxel/ulf/<endpoint_slug>/tau200/partial_spearman_total_ulf_exposure/
```

The gain endpoint replaces `Y_post` with direction-normalized `Gain_chronic`.
The total-ULF sensitivity keeps the chronic raw post-score endpoint but uses
total ULF component exposure instead of HF-overlap-excluded ULF-only exposure.
Both outputs are sensitivity branches only:

```text
resampling_status = not_run_observed_only
formal permutation/bootstrap/jitter = not run
same-day immediate endpoint family = not included
```

Current observed-only sensitivity summary:

```text
partial_spearman_gain_endpoint: rho = 0.4762799998; Q2 = 0.1980823112
partial_spearman_total_ulf_exposure: rho = 0.9278360578; Q2 = -0.0371760912
summary CSV = /Volumes/VAL/STNSNr/summary/direct_voxel/ulf/mds_updrs_iii_score_stn_snr_3_m/tau200/direct_voxel_ULF_only_sensitivity_summary.csv
```

Entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_ulf_direct_voxel_sensitivity_observed.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_ulf_direct_voxel_sensitivity_observed.py
```

## ULF Normative Fiber Observed Driver

The D-model observed executable layer runs the observed-only ULF normative
connectome fiber branches. It is intentionally limited to LOOCV observed
modeling; formal permutation, bootstrap, jitter, OSS-DBS, endpoint enrichment,
and figure-grade density outputs are separate downstream layers.

Entry point:

```text
my_helper/fiber/stnsnr/run_stnsnr_ulf_normative_fiber_observed.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_ulf_normative_fiber_observed.py
```

Lightweight implementation self-test:

```text
my_helper/fiber/core/analysis/stnsnr_ulf_normative_fiber_observed_selftest.py
```

Default observed endpoint and connectome:

```text
post scale = MDS-UPDRS III score (STN+SNr, 3 m)
HF reference scale = same base scale under STN, 3 m
connectome = PPMI 85
tau = 800 V/m
Coverage>=5
estimator = baseline-adjusted partial Spearman
```

The driver reads the latest `ulf_component_efield_availability.csv`, samples
component-specific HF and ULF raw `sim-efield` files along the right-canonical
public connectome streamlines, and creates:

```text
X_HF_component_i(l)  = bilateral average peak HF component exposure
X_ULF_component_i(l) = bilateral average peak ULF component exposure
X_ULF_only_i(l)      = X_ULF_component_i(l) when ULF is active and HF is not active
```

The matched HF reference exposure is reused from the existing HF normative fiber
sidecar for the same connectome and scale whenever available. This keeps the
`DeltaHFFiberScore` support aligned to the already observed B branch.

Both D core branches are executed when inputs allow:

```text
default observed output: ulf_peak_efield_tau800_no_delta_hf
revised default spec:    ulf_peak_efield_tau800_cov5_no_delta_hf

default observed output: ulf_peak_efield_tau800_delta_hf_adjusted
revised default spec:    ulf_peak_efield_tau800_cov5_delta_hf_adjusted

selected-source output after current PPMI scan fallback:
  ulf_peak_efield_tau600_no_delta_hf
  ulf_peak_efield_tau600_delta_hf_adjusted
```

The revised normative-fiber resolver reads the matched B dependency before
assigning the interpretive primary branch: accepted B source plus
`hf_norm_fiber_prediction_status = error_predictive` makes
`delta_hf_adjusted` intended primary; accepted B source plus
`error_nonpredictive` makes `no_delta_hf` intended primary;
`absent_no_stable_grid` runs no-DeltaHF only.

Default outputs:

```text
/Volumes/VAL/STNSNr/summary/normative_connectome_fiber/ulf/<connectome_slug>/<scale_slug>/peak_efield_tau800_observed/
  preprocess/
  ulf_peak_efield_tau800_no_delta_hf/
  ulf_peak_efield_tau800_delta_hf_adjusted/
  tau_coverage_source_resolver_scan/
```

Selected-source fallback outputs use the selected tau in the observed output
root and branch names. The current PPMI fallback is:

```text
/Volumes/VAL/STNSNr/summary/normative_connectome_fiber/ulf/ppmi_85_ewert_2017/mds_updrs_iii_score_stn_snr_3_m/peak_efield_tau600_observed/
  ulf_peak_efield_tau600_no_delta_hf/
  ulf_peak_efield_tau600_delta_hf_adjusted/
```

Each branch writes observed scores, LOOCV predictions, fiber weights, QC JSON,
and a generation manifest. The branch manifests record `ulf_primary_branch`,
`delta_hfscore_role`, the relevant `hf_norm_fiber_*` source-status fields,
`ulf_norm_fiber_source_status`, `ulf_norm_fiber_prediction_status`,
`ulf_norm_fiber_endpoint_model_status`, selected tau/Coverage fields, and
`resampling_status=not_run_observed_only`.

Current PPMI source resolver and selected-source observed run:

```text
source resolver root = /Volumes/VAL/STNSNr/summary/normative_connectome_fiber/ulf/ppmi_85_ewert_2017/mds_updrs_iii_score_stn_snr_3_m/peak_efield_tau800_observed/tau_coverage_source_resolver_scan/
selected output root = /Volumes/VAL/STNSNr/summary/normative_connectome_fiber/ulf/ppmi_85_ewert_2017/mds_updrs_iii_score_stn_snr_3_m/peak_efield_tau600_observed
no_delta_hf:        scan_fallback_accepted + error_nonpredictive; LOOCV Spearman rho = 0.916054, Q2 = 0.0718562
delta_hf_adjusted:  scan_fallback_accepted + error_nonpredictive; LOOCV Spearman rho = 0.908690, Q2 = -0.0597838
endpoint status:    primary_branch_error_nonpredictive
```

The D PPMI observed output is now included in the consolidated status report as
`OBSERVED_COMPLETE_PRIMARY_ERROR_NONPREDICTIVE`. Formal resampling,
OSS-DBS activation, density maps, endpoint enrichment, and dTOR-scale
figure-grade outputs remain deferred.

Current dTOR source resolver and selected-source observed run:

```text
source resolver root = /Volumes/VAL/STNSNr/summary/normative_connectome_fiber/ulf/dtor_985_full_elias_2024/mds_updrs_iii_score_stn_snr_3_m/peak_efield_tau800_observed/tau_coverage_source_resolver_scan/
selected output root = /Volumes/VAL/STNSNr/summary/normative_connectome_fiber/ulf/dtor_985_full_elias_2024/mds_updrs_iii_score_stn_snr_3_m/peak_efield_tau400_observed
no_delta_hf:        scan_fallback_accepted + error_nonpredictive; LOOCV Spearman rho = 0.941091, Q2 = -0.0849500
delta_hf_adjusted:  scan_fallback_accepted + error_predictive; LOOCV Spearman rho = 0.946982, Q2 = 0.216921
endpoint status:    primary_branch_error_nonpredictive
```

The D dTOR observed output is included in the consolidated status report as
`OBSERVED_COMPLETE_PRIMARY_ERROR_NONPREDICTIVE`. The matched B_DTOR source is
accepted but `error_nonpredictive`, so the HF-derived intended primary branch is
no-DeltaHF. The D_DTOR ULF tau/Coverage source resolver scan selects
tau400/Coverage>=5 as scan fallback; endpoint realization remains
primary-branch error-nonpredictive because no-DeltaHF is the HF-derived primary.
For D rows, the consolidated status `branch` field must be generated from the
selected-source tau recorded by the source resolver, not from the default
tau800 scan root. Current selected-source rows therefore report
`peak_efield_tau600` for PPMI and `peak_efield_tau400` for dTOR.

Run the D PPMI source resolver:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_normative_fiber_observed.py \
  --connectome ppmi \
  --source-resolver-scan
```

Run the current D PPMI selected-source observed branch:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_normative_fiber_observed.py \
  --connectome ppmi \
  --tau 600 \
  --min-coverage 5
```

Run the D dTOR observed branch:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_normative_fiber_observed.py \
  --connectome dtor
```

Run the D dTOR source resolver:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_normative_fiber_observed.py \
  --connectome dtor \
  --source-resolver-scan
```

Run the current D dTOR selected-source observed branch:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_ulf_normative_fiber_observed.py \
  --connectome dtor \
  --tau 400 \
  --min-coverage 5
```
