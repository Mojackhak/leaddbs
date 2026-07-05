# Four-Model Execution Implementation Notes

This note records the first executable implementation layer for `four_model_execution_plan.md`.

The full four-model program is intentionally gated. The first code layer only implements M0 readiness checks and manifest generation. It does not run voxel or fiber statistics, does not compute E-field sidecars, and does not start formal permutation, bootstrap, jitter, OSS-DBS, or display stages.

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

The a409 worktree may not contain gitignored heavy assets such as `templates/` and `connectomes/`. The M0 tool therefore accepts an explicit `--asset-root` and otherwise falls back to `/Users/mojackhu/Github/leaddbs` when the current worktree lacks those assets.

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

## HF Direct Voxel Smoke Driver

The next executable layer implements the primary HF direct voxel observed branch only:

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

The next B-model executable layer targets the cheapest real public connectome first:

```text
model = HF normative connectome fiber
connectome = PPMI 85 (Ewert 2017) by default
scale = MDS-UPDRS III score (STN, 3 m) by default
branch = peak_efield_tau800_primary
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
Coverage_tau(l) = sum_i I[X_HF_i(l) > tau]
F_candidate_tau = Coverage_tau(l) >= 5
```

and then runs the partial-Spearman `NetFiberScore` observed LOOCV branch. Formal `B=10000`, OSS-DBS, FDR/density/display, and dTOR processing remain later gated stages.

The driver supports `--max-fibers` only for development self-tests and debugging. Production PPMI smoke runs should leave it unset so the candidate universe remains the full PPMI connectome.

## Four-Model Gate Status Summary

After foundational smoke branches run, the gate status tool reads current manifests/QC files and writes a compact decision table:

```text
my_helper/fiber/stnsnr/run_stnsnr_four_model_gate_status.py
```

Reusable implementation:

```text
my_helper/fiber/core/analysis/stnsnr_four_model_gate_status.py
```

The tool does not run any model. It classifies each available primary smoke branch as:

```text
PASS_TO_NEXT_ROUND
STOP_FORMAL_REMAIN_EXPLORATORY
MISSING_OUTPUT
ERROR
```

For the current gate, a branch enters the next expensive round only if all executable QC files exist, LOOCV predictions are finite, the primary LOOCV Spearman rho is positive, and Q2 is not negative. This intentionally prevents formal permutation/bootstrap from starting when the primary observed branch does not show incremental signal beyond baseline.

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

Summarize gate status:

```bash
/opt/anaconda3/bin/conda run -n leaddbs \
  python my_helper/fiber/stnsnr/run_stnsnr_four_model_gate_status.py
```
