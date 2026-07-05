# Four-Model Execution Plan (Codex + Subagent Orchestration)

> **Purpose.** This file is the `/goal` plan document — the north-star and engineering roadmap for the codex main orchestrator and its subagents to execute the four modeling tasks below.
> **Authoritative specs.** The four English `.md` files under `model_summaries/` are the single executable specification (`_zh` are mirrors; English wins on conflict). This plan only covers **cross-model orchestration, environment grounding, guardrails, and scheduling** — it does not restate each spec's internal detail.
> **Created:** 2026-07-04. **Workspace:** codex worktree `a409` (`/Users/mojackhu/.codex/worktrees/a409/leaddbs`). Chinese mirror: `four_model_execution_plan_zh.md`.

---

## 0. One-line goal (paste into `/goal`)

> On the n=16 STN/SNr DBS cohort, use MATLAB/Lead-DBS for image-domain preprocessing of E-field and fiber modeling and Python (conda `leaddbs`) for statistical post-processing, and deliver four stimulation–outcome association models (HF direct voxel, HF normative-connectome fiber, and the HF-adjusted ULF-only add-on gain voxel and fiber models) per the Round gating in each `model_summaries` spec. Every model follows the principle **"prove incremental LOOCV signal on the primary branch before investing in sensitivity/display layers,"** with seed fixed at 42, fully reproducible, manifest-backed, and obeying each spec's exact-equivalence (no-shortcut) contract. Because **n=16, results are hypothesis-generating.**

---

## 1. Scope: the four models

| ID | Spec file | Type | Primary tau | Primary predictor / score | Depends on |
|---|---|---|---|---|---|
| **A** | `hf_3m_direct_voxel_model.md` | Direct voxel sweet-spot | 200 V/m (180/220 sensitivity) | `HFScore_mean_main` (partial Spearman) | none (foundational) |
| **B** | `hf_3m_normative_connectome_fiber_model.md` | Normative connectome fiber filtering | 800 V/m (1500 sensitivity) | `NetFiberScore`; PPMI/MGH/dTOR; OSS-DBS sensitivity | none (foundational) |
| **C** | `ulf_addon_gain_direct_voxel_model.md` | ULF-only add-on gain, voxel | 200 V/m (180/220 = exposure-definition sensitivity) | `ULFScore_mean_main`, covariates include `DeltaHFScore` | **locked A** (voxel DeltaHFScore) |
| **D** | `ulf_addon_gain_normative_connectome_fiber_model.md` | ULF-only add-on gain, fiber | 800 V/m (1500 = exposure-definition sensitivity) | `NetULFFiberScore`, covariates include `DeltaHFScore` | **locked B** (fiber DeltaHFScore) |

**Out of scope (this round):** the two individualized-DWI seed-target models (`*_individualized_dwi_seed_target_model.md`); the `OLS ANCOVA` supplemental estimator (every spec marks it "documented only, not run"); 5/7/10-fold CV and other documented-only items. `Coverage>=6/8` remains out of the primary HF direct-voxel mainline, but the A-model post-hoc tau/coverage scan may evaluate it as an exploratory threshold-optimization branch.

---

## 2. Dependencies & execution order

```
        ┌──────────────┐        ┌──────────────┐
        │ A: HF voxel  │        │ B: HF fiber  │     ← run in parallel
        └──────┬───────┘        └──────┬───────┘
               │ lock (tau200/          │ lock (dTOR peak_efield_
               │ partial_spearman)      │ tau800_primary)
               ▼                        ▼
        ┌──────────────┐        ┌──────────────┐
        │ C: ULF voxel │        │ D: ULF fiber │     ← parallel once A/B locked
        │ uses A's     │        │ uses B's     │
        │ DeltaHFScore │        │ DeltaHFScore │
        └──────────────┘        └──────────────┘
```

- **A ∥ B** proceed in parallel (different preprocessing, different tau, shared statistical kernel).
- **C only after A is locked**; **D only after B is locked.** If the depended-upon HF model fails QC / is degenerate, the corresponding ULF model is exploratory only, and its `DeltaHFScore` is labeled an *unstable generated covariate* (see each ULF spec's "Locked HF Prerequisite").
- **Connectome-matched (D):** `ULF/PPMI` uses `HF/PPMI` DeltaHFScore, `ULF/MGH` uses `HF/MGH`, `ULF/dTOR` uses `HF/dTOR`. A shared dTOR-HF adjustment across connectomes may be reported only as `shared_dTOR_HF_adjustment_sensitivity`.
- **Status reporting for B:** gate/status summaries must report the HF normative fiber observed branches for `PPMI`, `MGH`, and `dTOR` separately; a PPMI-only status row is not sufficient evidence that Model B has completed its observed connectome sequence.

---

## 3. Confirmed decisions

1. **Goal horizon = full program with a first-batch gate.** The `/goal` covers all Rounds of all four models, but the *first practical run* is limited to the first batch **M0–M3 (smoke)** per each spec's "Recommended First Batch." Only after the first batch passes do we release the expensive **B=10000** formal permutation/bootstrap and the display layer. "Done" = A/B locked with their primary branches fully completed, C/D primary branches completed after their dependencies lock, and four traceable manifests.
2. **ULF `immediate` endpoint = key secondary.** For C/D, the **chronic 3-month** endpoint is the sole formal primary endpoint. The same-day `immediate` endpoint gets observed LOOCV plus optional smoke resampling only — **no default B=10000.** Formal resampling is restricted to the chronic `tau200/partial_spearman` branch (C) and the dTOR `ulf_peak_efield_tau800_primary` chronic branch (D). `immediate` is not promoted to co-primary unless an explicit pre-registered decision is made later.

---

## 4. Environment & data (verified)

**Compute environment**
- conda base: `/opt/anaconda3` (note: `conda` is **not** on the PATH of non-interactive shells). Before running specs, `source /opt/anaconda3/etc/profile.d/conda.sh`, or use the absolute path `/opt/anaconda3/bin/conda run -n leaddbs ...`.
- `leaddbs` env ✓: Python statistical post-processing (LOOCV / permutation / bootstrap / jitter / NIfTI output).
- `ossdbsv2` env ✓: used only by the OSS-DBS activation sensitivity branch of B and D.
- MATLAB + Lead-DBS: image-domain preprocessing (**Round 0 must verify version and that `ea_flip_lr_nonlinear` is callable**).
- Pin BLAS threads: on the Python side export `OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1` *before* importing numpy/scipy; use worker-level parallelism.
- Default resources: MATLAB workers 8; Python jobs 14; random seed 42. The MATLAB phase and Python phase run **serially, in separate phases** to avoid CPU oversubscription.

**Data (verified to exist)**
- Raw clinical scores: `/Users/mojackhu/Research/STNSNr/summary/cohort/subj/subject_effect_origin.xlsx` ✓ (joined by `ID`, e.g. `SNr003`).
- Stimulation parameter audit: same dir, `followup_stimulation.xlsx` (sheet `Contact Parameters`) ✓.
- `/Volumes/VAL` mounted ✓, contains `reference/` (methodology PDFs) and `summary/` (existing `cohort/ stats/ table/ vta/`).
- Output roots `/Volumes/VAL/STNSNr/summary/direct_voxel/` and `.../normative_connectome_fiber/` **not yet created** (greenfield).
- **No existing `.py`/`.m` implementation under stnsnr:** the executable pipeline is greenfield; the `.md` files are specs only.

**External-volume risk:** `/Volumes/VAL` and the clinical dir are an unmountable/permission-restricted volume; re-verify mount and read/write at every Round 0.

---

## 5. Two-phase architecture (shared by all models)

**Phase 1 — MATLAB/Lead-DBS preprocessing (image domain)**
- Discover and availability-check required E-fields (raw `sim-efield`, **not** `sim-efieldgauss`, units V/m; unique match on subject × side × condition/phase/component).
- Combine same-side alternating subprograms by voxel-wise maximum; do all left/right flips with `ea_flip_lr_nonlinear`; sample onto the right-hemisphere canonical grid (voxel) or right-canonical streamline features (fiber).
- Write a MAT v7 design matrix plus memmap-friendly sidecars (voxel-major / fiber-major `.npy`, `S{tau}_bool`, candidate ijk/xyz, metadata, flip audit). dTOR **must** be chunked; **never** load the whole fibers matrix.

**Phase 2 — Python statistical post-processing (conda `leaddbs`)**
- Read sidecars → rebuild coverage/candidate within each fold → build the partial-Spearman map → scores → LOOCV → permutation/bootstrap/jitter → CSV/JSON/NIfTI/PDF.
- Orchestrate from a single long-running Python entry point; avoid repeated `conda run` inside tau/fold/perm/boot/jitter loops.

**Phase OSS — (conda `ossdbsv2`, B/D only)**
- Compute activation **after** the peak-E-field candidate set is locked; must not redefine/add/remove candidate fibers; write the parameter set as `primary_locked` in the manifest first.

---

## 6. Shared statistical kernel: build once, reuse ×4

All four models share one statistical skeleton — **build it once, parameterize, and reuse.** This is the project's biggest effort-saver and consistency guarantee:

- Sidecar schema and memmap loader (voxel-major / fiber-major; dTOR chunk manifest).
- Fold coverage by **subtraction**: `Coverage_fold_h = Coverage_all - S_tau(·,h)`, so the held-out subject never enters the fold's candidate set.
- Vectorized rank-residual **partial Spearman kernel** (ranks within the training fold; full-sample ranks prohibited).
- **Fold-level score operator** (permutation reuses the outcome-independent parts: `A_h`, `Z_h`).
- **Freedman-Lane permutation** harness (permute nuisance residuals, plus-one two-sided p, statistic = LOOCV Spearman rho).
- **Streaming Welford bootstrap** (never store 10000 maps; accumulate mean/M2/finite_count).
- **Spatial jitter** (FWHM 2 mm, sigma 0.849; translation-only linear resampling; rebuild the full chain).
- **Exact-equivalence regression-test** framework (brute-force vs optimized, small subset + B_perm/B_boot=20, seed 42).
- Manifest/QC writer (provenance, env snapshot `conda list --explicit` + `pip freeze`, hashes, `runtime_profile`).
- Display layer: display smoothing FWHM 1/2 mm, bilateral homologous display maps, top-x + stability display masks, PDF QC — **display only, never fed back into statistics.**

**Per-model differences to parameterize:** prediction unit (voxel grid ↔ streamline, dTOR chunking); tau (200 ↔ 800, and for ULF tau is part of the exposure definition); score definition (`HFScore_mean_main` / `NetFiberScore` / `ULFScore_mean_main` / `NetULFFiberScore`, incl. F+/F- top-k fiber selection); nuisance covariates (A/B: `Y_base`; C/D: `Y_HF_ref` + `DeltaHFScore`); ULF's HF-overlap exclusion and in-support `DeltaHFScore` projection; B/D's OSS branch and FDR/label/density display.

---

## 7. Codex + subagent orchestration

**Main orchestrator (codex main):** holds the dependency graph, gating, and schedule; releases C/D after A/B lock; enforces cross-model consistency (seed, sidecar schema, manifest conventions).

**Suggested subagent decomposition (bounded, parallelizable, dependency-aware):**

| Subagent | Responsibility | Depends on | Parallel with |
|---|---|---|---|
| **S0** env/data readiness + scaffolding | verify conda/MATLAB/VAL/clinical, create output roots, repo skeleton + scale-direction table | — | start |
| **S1** shared statistical kernel (Python/leaddbs) | implement §6 kernel + equivalence-test framework | S0 | S2a, S2b |
| **S2a** MATLAB voxel preprocessing | E-field sampling + sidecars serving A, C | S0 | S1, S2b |
| **S2b** MATLAB fiber preprocessing | serve B, D; dTOR chunking; OSS sidecar scaffolding | S0 | S1, S2a |
| **S3** Model A driver | assemble A's Round 0→lock, run primary branch | S1, S2a | S4 |
| **S4** Model B driver | assemble B's Round 0→lock (PPMI/MGH/dTOR, OSS) | S1, S2b | S3 |
| **S5** Model C driver | ULF voxel, consumes **locked A** DeltaHFScore | S3(lock), S2a | S6 |
| **S6** Model D driver | ULF fiber, consumes **locked B** DeltaHFScore | S4(lock), S2b | S5 |

**Subagent discipline (bake into each subagent task):**
1. Single model / single phase boundary; return structured results to the main process, which atomically writes the final CSV/JSON.
2. **Never** run MATLAB and Python concurrently (CPU oversubscription); **always** pass the equivalence test before any formal resampling.
3. Strictly obey §9 guardrails; write a manifest and QC for every branch; record `not_run_nonprimary` + reason for any branch not run.
4. Reuse the shared kernel — do not reinvent it; pass tau/score/covariate differences via configuration.

**Parallelism:** S1 ∥ S2a ∥ S2b; A ∥ B; C ∥ D (each after its HF lock). OSS (ossdbsv2) and the main statistics (leaddbs) are separate phases and never overlap the MATLAB phase.

---

## 8. Milestone roadmap (compressed from each spec's Round 0–10)

Each model walks the milestones below independently. **Gating philosophy:** the primary branch must first show interpretable incremental LOOCV signal beyond the covariate-only baseline before investing in sensitivity / formal resampling / display; when the primary branch fails, do **not** go to tau180/tau220 to "search for signal."

| Milestone | Content | A | B | C | D |
|---|---|---|---|---|---|
| **M0** readiness & freeze | clinical join, E-field uniqueness, scale direction, flip callable, env manifest, seed 42 | R0 | R0 | R0 (+lock A) | R0 (+lock B) |
| **M1** sidecars + equivalence | preprocessing sidecars, coverage cache, brute-force vs optimized equivalence | R1 | R1 | R1 | R1 |
| **M2** primary observed LOOCV | primary tau/scale, write numeric core outputs, defer display | R2 | R2–3 | R2 (+2b immediate) | R2–3 |
| **M3** smoke resampling | equivalence + smoke perm/boot B=1000 + jitter B=100 | R3 | R5 | R3 | R5 |
| **M4** formal permutation | Freedman-Lane B=10000 (primary branch / dTOR only) | R4 | R7 | R4 | R7 |
| **M5** formal bootstrap | subject-level B=10000, streaming SE | R5 | R7 | R5 | R7 |
| **M6** formal jitter | FWHM 2 mm B=1000 | R6 | R9 | R6 | R8 |
| **M7** sensitivity/controls | tau sensitivity, plain control, no-DeltaHF, total-ULF, OSS, etc. | R7 | R4/6/8 | R7–8 | R4/6 |
| **M8** secondary scale/endpoint | axial; C/D immediate endpoint (key secondary) | R8 | R3 | R2b | R3 |
| **M9** display & final manifests | smoothing, display masks, FDR/label/density, PDF QC, cross-connectome summaries | R9 | R10 | R9 | R9 |

**First batch (strongly do only this segment first, then reassess):** each model's **M0 + M1 + M2 + M3 (smoke)**. Concrete scope per each spec's "Recommended First Batch": primary scale (MDS-UPDRS III total), primary tau, `Coverage>=5`, primary score, LOOCV, covariate-only comparison, equivalence test, smoke perm/boot (B=1000), smoke jitter (B=100), basic QC/manifest. **Only after the first batch passes** do we enter B=10000 formal permutation/bootstrap.

---

## 9. Guardrails (exact-equivalence / no-shortcut contract)

**General (all four models)**
- Prohibited: shrinking formal B, adaptive permutation early stopping, full-sample ranks inside LOOCV/perm/boot, approximate ranks, full-sample candidate/F+/F- replacing fold-specific ones, using anatomical overlay masks as the analysis mask, dropping requested jitter QC, using compressed NPZ as the random-access formal-loop input.
- Within folds: each fold builds its own coverage/candidate (held-out subtraction), each fold/perm/boot re-selects F+/F-, ranks are computed within the fold.
- Reproducibility: seed 42 derives deterministic child seeds; every branch's manifest records env (`conda list --explicit` + `pip freeze`), code version, input hashes, `runtime_profile`; completion markers + force-rerun.
- Formal loops do not write per-perm/per-boot intermediate maps (unless debug is explicitly enabled); workers do not concurrently append to shared CSV/JSON.

**Fiber (B/D)**
- dTOR **must** be chunked/memmap; never load whole fibers or all exposure into memory; two-pass streaming top-k; deterministic top-k tie-break `(-M, fiber_id)`.
- OSS: lock candidate first, then compute activation; activation must not redefine candidates.

**ULF (C/D)**
- tau is **part of the exposure definition** (defines ULF-active, HF-active, overlap exclusion, ULF-only zeroing, coverage); a tau-independent `X_ULF_only` is prohibited.
- The primary predictor **hard-excludes HF-overlap** voxels/fibers; total-ULF is sensitivity only.
- `DeltaHFScore` uses only the **in-support projection** of the locked HF model; no extrapolation/smoothing/nearest-neighbor of HF weights outside support; no expanding HF support after seeing ULF results; in LOOCV the held-out DeltaHFScore must use the **training-fold** HF map (not full-sample).
- Out-of-support burden must be quantified and interpretation downgraded per the gating rules.

---

## 10. Definition of Done

**Per model:** the primary branch completes M0–M6 producing all required outputs listed in the spec; every branch has a complete manifest/QC (incl. `corr(score, covariate)`, coefficient signs, collinearity diagnostics, flip audit, env provenance, `runtime_profile`); the equivalence test passes and is recorded; negative results are honestly labeled exploratory/negative with a minimal report per spec.

**Overall:** A and B locked with their primary branches complete; C and D complete their primary branches after their dependencies lock; the four manifests trace back to the same seed and a consistent sidecar schema; the interpretation boundary states **n=16 → hypothesis-generating**; cross-connectome / cross-scale summaries (B/D) are produced.

---

## 11. Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| n=16 small sample | LOOCV may be non-significant; single high-leverage subject can dominate | influence diagnostics (Cook/DFBETA), honestly label hypothesis-generating, interpret permutation p jointly with rho/Q2 |
| conda not on PATH | scripts calling `conda` directly fail | standardize on `/opt/anaconda3/bin/conda run -n leaddbs` or source the profile first |
| `/Volumes/VAL` external volume | mid-run unmount/permission → IO failure | verify mount + read/write at every Round 0; use local NVMe scratch for formal loops, atomically promote after validation |
| scale-direction table | undefined scale polarity → wrong M-map sign | Round 0 forces higher/lower-is-better definition, written to the internal direction table |
| dTOR scale | memory/compute blow-up | chunk-size autotune (peak mem < budget × 0.7), two-pass streaming, resumable-block checkpoints |
| OSS params unlocked | sensitivity not reproducible | write full params as `oss_model_set=primary_locked` in the manifest before running |
| ULF same-day T2 pairing | immediate endpoint validity depends on same-day measurement | Round 0 audits that T2 HF-only and HF+ULF immediate are same-day/same-session |
| C/D depend on A/B quality | degenerate HF → unstable DeltaHFScore | dependency lock gating; if HF fails, ULF is exploratory only and labeled unstable covariate |

---

### Appendix: authoritative document index
- Specs (executable): `model_summaries/{hf_3m_direct_voxel_model, hf_3m_normative_connectome_fiber_model, ulf_addon_gain_direct_voxel_model, ulf_addon_gain_normative_connectome_fiber_model}.md` (+ `_zh` mirrors)
- Master plan: `endpoint_specific_sweetspot_plan.md` (Implementation Outline / Statistical Plan / Acceptance Checks)
- Technical details: `normative_connectome_sweet_sour_technical_details.md`, `dwi_registration_technical_details.md`, `stnsnr_seed_target_atlas_registry.md`
