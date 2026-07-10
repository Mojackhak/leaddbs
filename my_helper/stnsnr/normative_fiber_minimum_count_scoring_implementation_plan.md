# Normative-Fiber Minimum-Count Scoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use test-driven development and execute this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Bounded subagents are allowed for disjoint files or read-only audits, but the main agent owns integration and acceptance.

**Goal:** Implement one reusable, leakage-free `200/100/20` normative-fiber scoring contract across HF, realized-final ULF, DeltaHFScore, formal/sensitivity rounds, and binary pPAM OSS sensitivity without changing the tau/Coverage source resolver.

**Architecture:** Add a focused deterministic score kernel and keep `stnsnr_four_model_stats.fiber_net_score` as its compatibility entrypoint. Propagate one strict YAML score profile through every configured normative-fiber runner, persist full-sample and fold support provenance, and bind each normative-fiber final record to its realized `F_valid` fiber axis. OSS consumes that immutable axis, thresholds pPAM at `>= 0.5`, re-estimates weights and signed selections inside each training fold, and never derives tau/Coverage from pPAM.

**Tech Stack:** Python 3 in Conda `leaddbs`, NumPy, dataclasses, PyYAML, JSON Schema Draft 2020-12, `unittest`, existing configured four-model services and analysis modules.

## Global Constraints

- User decisions in the active task take precedence over any conflicting Markdown prose.
- All configured endpoint/scale rows use the same engineering execution and scoring rules. MDS-UPDRS III and IV are acceptance scales only.
- Do not change source-resolver tau/Coverage selection, prediction classification, or final-branch role rules.
- Retain the existing normative-fiber threshold comparator `E > tau`. Score construction consumes the resolver candidate mask and must not independently reinterpret the threshold.
- `F_valid = F_coverage & isfinite(weights)`; never backfill excluded fibers.
- ULF uses the realized branch candidate set after HF-overlap exclusion.
- Primary score parameters are exactly `0.01`, `0.005`, `0.05`, `200`, `100`, and `20` unless a valid public YAML profile supplies the same typed fields.
- One-sided signed scores are valid but limited. Only an empty valid signed set is `absent_no_valid_signed_fibers`.
- Support status is QC/reporting, not a new tau/Coverage hard gate. Existing score-nonconstant, finite-prediction, subject-count, candidate-count, and MAE/RMSE rules retain their documented effects.
- Every non-OSS held-out prediction recomputes coverage, weights, signs, selected IDs, and peak counts from the training fold only.
- OSS uses the immutable realized-final full-sample `F_valid` axis, binary `I[p(A)>=0.5]`, fold-local weights/selections, and no pPAM-derived coverage filter.
- Cross-endpoint OSS reuse is allowed only for exact source-input and ordered-candidate identity; reused artifacts must be rebound to destination-local final provenance.
- DeltaHF extreme out-of-support remains strict `out_support_fraction > 0.95`; equality at `0.95` is not failure.
- Code, identifiers, comments, and docstrings are English.
- Do not write to or migrate existing `/Volumes/VAL/STNSNr/summary` legacy outputs. Configured acceptance writes only under the configured run root.

---

## File Structure

- Create `my_helper/fiber/core/analysis/stnsnr_normative_fiber_score.py`: score policy, deterministic signed-fiber selection, weighted-peak aggregation, support classification, and QC serialization.
- Modify `my_helper/fiber/core/analysis/stnsnr_four_model_stats.py`: re-export the shared score API and remove the duplicate primary implementation.
- Create `my_helper/fiber/core/outcome_models/tests/test_normative_fiber_score.py`: focused unit tests for counts, ties, one-sided sets, hashes, and finite-weight intersection.
- Modify `my_helper/fiber/core/outcome_models/schemas/model_profile.schema.json`, `my_helper/stnsnr/config/four_model_v1/model.yaml`, and `my_helper/fiber/core/outcome_models/tests/test_config.py`: strict public score profile.
- Modify HF/ULF normative-fiber analysis modules and configured adapters: propagate policy, use the kernel in full/fold scoring, and emit required QC/artifacts.
- Modify `my_helper/fiber/core/outcome_models/records.py` and `services/record_io.py`: immutable realized-valid fiber axis for normative-fiber final records.
- Modify formal, sensitivity, and OSS analysis/adapters: consume the same score policy and immutable axis.
- Modify planner/default registry only where required to produce or exactly reuse an OSS sidecar before the OSS fit task.

---

### Task 1: Shared Deterministic Normative-Fiber Score Kernel

**Files:**
- Create: `my_helper/fiber/core/analysis/stnsnr_normative_fiber_score.py`
- Modify: `my_helper/fiber/core/analysis/stnsnr_four_model_stats.py:12-22,188-255`
- Create: `my_helper/fiber/core/outcome_models/tests/test_normative_fiber_score.py`
- Modify: `my_helper/fiber/core/analysis/stnsnr_four_model_stats_selftest.py`

**Interfaces:**
- Produces `NormativeFiberScoreConfig`, `FiberNetScoreResult`, `fiber_net_score`, and `score_support_fields`.
- `fiber_net_score(exposure, weights, candidate_mask, *, fiber_ids, score_config)` remains the common entrypoint used by all later tasks.

- [x] **Step 1: Write failing tests for count formulas, finite weights, ties, one-sided support, and hashes**

Use synthetic axes that assert:

```python
config = NormativeFiberScoreConfig(
    sweet_fraction=0.01,
    sour_fraction=0.005,
    weighted_peak_fraction=0.05,
    sweet_selected_min_count=200,
    sour_selected_min_count=100,
    weighted_peak_min_count=20,
)
result = fiber_net_score(exposure, weights, coverage_mask, fiber_ids=ids, score_config=config)
self.assertEqual(result.sweet_actual_selected_count, min(n_positive, max(math.ceil(0.01 * n_positive), 200)))
self.assertEqual(result.sour_actual_selected_count, min(n_negative, max(math.ceil(0.005 * n_negative), 100)))
self.assertEqual(result.sweet_actual_peak_count, min(result.sweet_actual_selected_count, max(math.ceil(0.05 * result.sweet_actual_selected_count), 20)))
```

Also assert a coverage-passing `NaN` weight is excluded, equal weights use ascending canonical fiber ID, duplicate canonical IDs are rejected, `N_positive=50` sets `sweet_minimum_count_dominated=True`, an empty sign sets its peak to zero and a limited one-sided status, and two identical selected ID arrays produce identical hashes.

- [x] **Step 2: Run the focused test and verify RED**

```bash
conda run -n leaddbs python -m unittest \
  my_helper.fiber.core.outcome_models.tests.test_normative_fiber_score -v
```

Expected: import or missing-field failures for the new score API.

- [x] **Step 3: Implement the score policy and result contract**

The production interface must be:

```python
@dataclass(frozen=True)
class NormativeFiberScoreConfig:
    sweet_fraction: float = 0.01
    sour_fraction: float = 0.005
    weighted_peak_fraction: float = 0.05
    sweet_selected_min_count: int = 200
    sour_selected_min_count: int = 100
    weighted_peak_min_count: int = 20

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "NormativeFiberScoreConfig":
        return cls(
            sweet_fraction=float(value["sweet_fraction"]),
            sour_fraction=float(value["sour_fraction"]),
            weighted_peak_fraction=float(value["weighted_peak_fraction"]),
            sweet_selected_min_count=int(value["sweet_selected_min_count"]),
            sour_selected_min_count=int(value["sour_selected_min_count"]),
            weighted_peak_min_count=int(value["weighted_peak_min_count"]),
        )


@dataclass(frozen=True)
class FiberNetScoreResult:
    sweet_peak5: np.ndarray
    sour_peak5: np.ndarray
    net_score: np.ndarray
    sweet_fiber_ids: np.ndarray
    sour_fiber_ids: np.ndarray
    n_positive_valid_fibers: int
    n_negative_valid_fibers: int
    sweet_percentage_count: int
    sour_percentage_count: int
    sweet_actual_selected_count: int
    sour_actual_selected_count: int
    sweet_actual_peak_count: int
    sour_actual_peak_count: int
    sweet_minimum_count_dominated: bool
    sour_minimum_count_dominated: bool
    sweet_peak_minimum_count_dominated: bool
    sour_peak_minimum_count_dominated: bool
    fiber_score_support_status: str
    sweet_selected_fiber_id_hash: str
    sour_selected_fiber_id_hash: str
```

Use `np.lexsort((canonical_ids, -positive_weights))` for sweet and `np.lexsort((canonical_ids, negative_weights))` for sour. Define percentage count as zero for an empty sign. A minimum-dominated flag is true only when that sign/selected set is nonempty and its percentage count is below the configured minimum.

- [x] **Step 4: Re-export the API from `stnsnr_four_model_stats`**

Delete its duplicate `FiberNetScoreResult`, `_top_mean_per_row`, and primary `fiber_net_score` implementation. Import/re-export the new symbols so existing analysis imports remain valid.

- [x] **Step 5: Run focused and legacy stats tests**

```bash
conda run -n leaddbs python -m unittest \
  my_helper.fiber.core.outcome_models.tests.test_normative_fiber_score -v
conda run -n leaddbs python my_helper/fiber/core/analysis/stnsnr_four_model_stats_selftest.py
```

Expected: all tests pass; the legacy selftest is updated for the approved minimum counts rather than the old percentage-only behavior.

- [x] **Step 6: Commit the kernel**

```bash
git add \
  my_helper/fiber/core/analysis/stnsnr_normative_fiber_score.py \
  my_helper/fiber/core/analysis/stnsnr_four_model_stats.py \
  my_helper/fiber/core/analysis/stnsnr_four_model_stats_selftest.py \
  my_helper/fiber/core/outcome_models/tests/test_normative_fiber_score.py
git commit -m "feat: add normative fiber minimum-count scoring"
```

### Task 2: Strict YAML Score Profile And Request Propagation

**Files:**
- Modify: `my_helper/fiber/core/outcome_models/schemas/model_profile.schema.json`
- Modify: `my_helper/stnsnr/config/four_model_v1/model.yaml`
- Modify: `my_helper/fiber/core/outcome_models/tests/test_config.py`
- Modify: `my_helper/fiber/core/outcome_models/services/legacy_hf_fiber.py`
- Modify: `my_helper/fiber/core/outcome_models/services/legacy_ulf_fiber.py`
- Modify: `my_helper/fiber/core/outcome_models/services/observed.py`
- Modify: `my_helper/fiber/core/outcome_models/tests/test_hf_fiber_configured_backend.py`
- Modify: `my_helper/fiber/core/outcome_models/tests/test_ulf_fiber_configured_backend.py`
- Modify: `my_helper/fiber/core/outcome_models/tests/test_observed_services.py`

**Interfaces:**
- Consumes `NormativeFiberScoreConfig.from_mapping`.
- Produces explicit six-field score policy on HF and ULF dependency-free analysis configs.

- [x] **Step 1: Add RED schema tests**

Assert that each of these missing or nonpositive fields fails validation and that unknown score fields fail because `additionalProperties` is false:

```yaml
sweet_selected_min_count: 200
sour_selected_min_count: 100
weighted_peak_min_count: 20
```

Retain rejection tests for public `candidate_threshold_v_per_m` and smoke controls.

- [x] **Step 2: Run config tests and verify RED**

```bash
conda run -n leaddbs python -m unittest \
  my_helper.fiber.core.outcome_models.tests.test_config -v
```

- [x] **Step 3: Extend the strict schema and committed profile**

The `normative_fiber.score` object must require exactly:

```json
{
  "sweet_fraction": {"type": "number", "exclusiveMinimum": 0, "maximum": 1},
  "sour_fraction": {"type": "number", "exclusiveMinimum": 0, "maximum": 1},
  "weighted_peak_fraction": {"type": "number", "exclusiveMinimum": 0, "maximum": 1},
  "sweet_selected_min_count": {"type": "integer", "minimum": 1},
  "sour_selected_min_count": {"type": "integer", "minimum": 1},
  "weighted_peak_min_count": {"type": "integer", "minimum": 1}
}
```

- [x] **Step 4: Propagate all six fields into HF and ULF analysis configs**

Add the three integer fields to `HFNormativeFiberAnalysisConfig` and all six fields to `ULFNormativeFiberAnalysisConfig`. Preserve integer types in `HFNormativeFiberRequest.from_context` instead of coercing every score value to `float`. This task transports the policy without changing numerical scoring; Task 3 constructs `NormativeFiberScoreConfig` and applies it to every primary/resolver branch call.

- [x] **Step 5: Run config and configured-adapter tests**

```bash
conda run -n leaddbs python -m unittest \
  my_helper.fiber.core.outcome_models.tests.test_config \
  my_helper.fiber.core.outcome_models.tests.test_observed_services \
  my_helper.fiber.core.outcome_models.tests.test_hf_fiber_configured_backend \
  my_helper.fiber.core.outcome_models.tests.test_ulf_fiber_configured_backend -v
```

- [x] **Step 6: Commit profile plumbing**

```bash
git add \
  my_helper/fiber/core/outcome_models/schemas/model_profile.schema.json \
  my_helper/stnsnr/config/four_model_v1/model.yaml \
  my_helper/fiber/core/outcome_models/tests/test_config.py \
  my_helper/fiber/core/outcome_models/services/legacy_hf_fiber.py \
  my_helper/fiber/core/outcome_models/services/legacy_ulf_fiber.py \
  my_helper/fiber/core/outcome_models/services/observed.py \
  my_helper/fiber/core/outcome_models/tests/test_hf_fiber_configured_backend.py \
  my_helper/fiber/core/outcome_models/tests/test_ulf_fiber_configured_backend.py \
  my_helper/fiber/core/outcome_models/tests/test_observed_services.py
git commit -m "feat: configure normative fiber score minima"
```

### Task 3: HF Full-Sample And Fold-Local Integration

**Files:**
- Modify: `my_helper/fiber/core/analysis/stnsnr_hf_normative_fiber_smoke.py`
- Modify: `my_helper/fiber/core/analysis/stnsnr_hf_normative_fiber_smoke_selftest.py`
- Modify: `my_helper/fiber/core/outcome_models/tests/test_hf_fiber_configured_backend.py`

**Interfaces:**
- Consumes `NormativeFiberScoreConfig` and `FiberNetScoreResult`.
- Produces `selected_valid_fiber_ids`, full support QC, and all required per-fold support fields.

- [x] **Step 1: Add RED tests for HF leakage prevention and support fields**

Construct a fold where the held-out subject is the only subject lifting one fiber over Coverage. Assert that fiber is absent from that fold's selected ID hash but may appear in the full-sample hash. Assert one-sided folds remain computable unless score nonconstancy or another existing hard filter fails.

Include an exposure exactly equal to tau and assert it is not suprathreshold, preserving the confirmed `E > tau` resolver comparator.

- [x] **Step 2: Run HF focused tests and verify RED**

```bash
conda run -n leaddbs python my_helper/fiber/core/analysis/stnsnr_hf_normative_fiber_smoke_selftest.py
conda run -n leaddbs python -m unittest \
  my_helper.fiber.core.outcome_models.tests.test_hf_fiber_configured_backend -v
```

- [x] **Step 3: Replace primary selection with the shared kernel**

Construct one `NormativeFiberScoreConfig` from the six propagated analysis fields. In `run_observed_loocv`, use full `candidate_mask_from_coverage` plus full weights, and independently use each training-fold coverage plus fold weights. Do not reuse full-sample selected IDs, signs, or ranks in a fold.

- [x] **Step 4: Emit the complete support contract**

Add all required fields from `score_support_fields(result, config)` to full-sample QC and every fold row. Keep existing `n_sweet_selected_fibers` and `n_sour_selected_fibers` as compatibility aliases of actual selected counts.

- [x] **Step 5: Materialize immutable full-sample `F_valid` IDs**

Write `selected_valid_fiber_ids.npy` in canonical parent-axis order using:

```python
valid_mask = np.asarray(candidate, dtype=bool) & np.isfinite(weights)
selected_valid_ids = np.asarray(fiber_ids, dtype=np.int64)[valid_mask]
```

Publish it as artifact kind `selected_valid_fiber_ids`. Set `selected_fiber_pools_computable` when at least one valid signed fiber exists, not only when both signs exist.

- [x] **Step 6: Keep 1500/500 cheap sensitivity separate**

The fixed `sweet_top_count=1500` and `sour_top_count=500` branch remains a cheap observed sensitivity. It may share low-level weighted-peak helpers but must not replace or mutate the primary `200/100/20` policy.

- [x] **Step 7: Run HF tests and commit**

```bash
conda run -n leaddbs python my_helper/fiber/core/analysis/stnsnr_hf_normative_fiber_smoke_selftest.py
conda run -n leaddbs python -m unittest \
  my_helper.fiber.core.outcome_models.tests.test_hf_fiber_configured_backend -v
git add \
  my_helper/fiber/core/analysis/stnsnr_hf_normative_fiber_smoke.py \
  my_helper/fiber/core/analysis/stnsnr_hf_normative_fiber_smoke_selftest.py \
  my_helper/fiber/core/outcome_models/tests/test_hf_fiber_configured_backend.py
git commit -m "feat: apply fold-local HF fiber scoring"
```

### Task 4: ULF Branch And DeltaHFFiberScore Integration

**Files:**
- Modify: `my_helper/fiber/core/analysis/stnsnr_ulf_normative_fiber_observed.py`
- Modify: `my_helper/fiber/core/analysis/stnsnr_ulf_normative_fiber_observed_selftest.py`
- Modify: `my_helper/fiber/core/outcome_models/services/legacy_ulf_fiber.py`
- Modify: `my_helper/fiber/core/outcome_models/tests/test_ulf_fiber_configured_backend.py`
- Modify: `my_helper/fiber/core/outcome_models/tests/test_delta_hf.py`

**Interfaces:**
- Consumes the shared score policy for both ULF branches and matched-HF Delta scores.
- Produces branch-local `selected_valid_fiber_ids` after HF-overlap exclusion.

- [x] **Step 1: Add RED tests for realized-branch candidates and Delta consistency**

Test both `no_delta_hf` and `delta_hf_adjusted`. Assert `selected_valid_fiber_ids` is derived after HF-overlap exclusion, a nonfinal branch cannot provide the final axis, and DeltaHFFiberScore uses the matched HF source's exact score policy for full sample and each held-out fold.

- [x] **Step 2: Run ULF/Delta tests and verify RED**

```bash
conda run -n leaddbs python my_helper/fiber/core/analysis/stnsnr_ulf_normative_fiber_observed_selftest.py
conda run -n leaddbs python -m unittest \
  my_helper.fiber.core.outcome_models.tests.test_ulf_fiber_configured_backend \
  my_helper.fiber.core.outcome_models.tests.test_delta_hf -v
```

- [x] **Step 3: Apply the shared policy in each ULF branch**

Pass `score_config` into full and fold scoring. Preserve branch-specific nuisance design:

```text
no_delta_hf:       Y_post ~ Y_HF_ref + NetULFFiberScore
delta_hf_adjusted: Y_post ~ Y_HF_ref + DeltaHFScore + NetULFFiberScore
```

The ULF source resolver remains branch-specific and unchanged.

- [x] **Step 4: Apply the same policy to DeltaHFFiberScore**

For full and fold matched-HF scores, use identical selected tau/Coverage, training-fold weights, and `NormativeFiberScoreConfig`. Continue to classify support using the existing strict out-of-support contract; do not alter `adequate`, `limited`, or invalid thresholds.

- [x] **Step 5: Emit branch-local support fields and valid IDs**

Write `selected_valid_fiber_ids.npy` for every accepted ULF branch. Only the realized final branch is later promoted into the final record. One-sided support remains runnable and is labeled limited.

- [x] **Step 6: Run ULF/Delta tests and commit**

```bash
conda run -n leaddbs python my_helper/fiber/core/analysis/stnsnr_ulf_normative_fiber_observed_selftest.py
conda run -n leaddbs python -m unittest \
  my_helper.fiber.core.outcome_models.tests.test_ulf_fiber_configured_backend \
  my_helper.fiber.core.outcome_models.tests.test_delta_hf -v
git add \
  my_helper/fiber/core/analysis/stnsnr_ulf_normative_fiber_observed.py \
  my_helper/fiber/core/analysis/stnsnr_ulf_normative_fiber_observed_selftest.py \
  my_helper/fiber/core/outcome_models/services/legacy_ulf_fiber.py \
  my_helper/fiber/core/outcome_models/tests/test_ulf_fiber_configured_backend.py \
  my_helper/fiber/core/outcome_models/tests/test_delta_hf.py
git commit -m "feat: apply branch-local ULF fiber scoring"
```

### Task 5: Immutable Realized-Valid Fiber Axis

**Files:**
- Modify: `my_helper/fiber/core/outcome_models/records.py`
- Modify: `my_helper/fiber/core/outcome_models/services/record_io.py`
- Modify: `my_helper/fiber/core/outcome_models/services/ulf_observed.py`
- Modify: `my_helper/fiber/core/outcome_models/tests/test_records.py`
- Modify: `my_helper/fiber/core/outcome_models/tests/test_record_io.py`
- Modify: `my_helper/fiber/core/outcome_models/tests/test_qualification_service.py`

**Interfaces:**
- Produces `FinalArtifactRecord.full_weights: ArtifactRef | None` and `FinalArtifactRecord.valid_feature_axis: FeatureAxisRef | None`.
- Normative-fiber finals require both; direct-voxel finals keep both as `None`.

- [x] **Step 1: Add RED record tests**

Assert that an HF/ULF normative-fiber final cannot be created without parent-axis full weights and a nonempty valid feature axis, both artifact hashes participate in `record_hash`, an axis-order or weight-artifact change invalidates deserialization, and a direct-voxel final remains valid with both fields set to `None`.

- [x] **Step 2: Run record tests and verify RED**

```bash
conda run -n leaddbs python -m unittest \
  my_helper.fiber.core.outcome_models.tests.test_records \
  my_helper.fiber.core.outcome_models.tests.test_record_io -v
```

- [x] **Step 3: Extend the final record**

Add:

```python
full_weights: ArtifactRef | None
valid_feature_axis: FeatureAxisRef | None
```

to create/serialize/deserialize/hash logic. Enforce both when `estimator` identifies `peak_efield_partial_spearman`; verify the weight shape equals the parent feature count and the valid axis is the exact ordered subset selected by `coverage_mask & isfinite(full_weights)` during persistence.

- [x] **Step 4: Bind HF and realized-final ULF artifacts**

Require artifact kinds `selected_valid_fiber_ids` and `selected_full_weights` for accepted normative-fiber outputs. Construct `valid_feature_axis` from the selected IDs artifact using the connectome's canonical identity source. Never take the axis from a nonfinal ULF branch.

- [x] **Step 5: Run record/qualification tests and commit**

```bash
conda run -n leaddbs python -m unittest \
  my_helper.fiber.core.outcome_models.tests.test_records \
  my_helper.fiber.core.outcome_models.tests.test_record_io \
  my_helper.fiber.core.outcome_models.tests.test_qualification_service -v
git add \
  my_helper/fiber/core/outcome_models/records.py \
  my_helper/fiber/core/outcome_models/services/record_io.py \
  my_helper/fiber/core/outcome_models/services/ulf_observed.py \
  my_helper/fiber/core/outcome_models/tests/test_records.py \
  my_helper/fiber/core/outcome_models/tests/test_record_io.py \
  my_helper/fiber/core/outcome_models/tests/test_qualification_service.py
git commit -m "feat: bind final fiber models to valid axes"
```

### Task 6: Formal, Bootstrap, Jitter, And Observed Sensitivity Consistency

**Files:**
- Modify: `my_helper/fiber/core/analysis/stnsnr_normative_fiber_smoke_permutation.py`
- Modify: `my_helper/fiber/core/analysis/stnsnr_normative_fiber_formal_bootstrap.py`
- Modify: `my_helper/fiber/core/analysis/stnsnr_ulf_normative_fiber_sensitivity_observed.py`
- Modify: `my_helper/fiber/core/analysis/stnsnr_normative_fiber_formal_jitter.py`
- Modify: `my_helper/fiber/core/analysis/stnsnr_ulf_normative_fiber_observed.py`
- Modify: `my_helper/fiber/core/outcome_models/services/formal.py`
- Modify: `my_helper/fiber/core/outcome_models/services/legacy_formal.py`
- Modify: `my_helper/fiber/core/outcome_models/services/sensitivity.py`
- Modify: `my_helper/fiber/core/outcome_models/services/legacy_sensitivity.py`
- Modify: `my_helper/fiber/core/outcome_models/services/legacy_oss.py`
- Modify: `my_helper/fiber/core/outcome_models/tests/test_configured_formal_backend.py`
- Modify: `my_helper/fiber/core/outcome_models/tests/test_configured_sensitivity_backend.py`
- Modify: `my_helper/fiber/core/outcome_models/tests/test_configured_jitter_spatial_qc.py`

**Interfaces:**
- Consumes the final record and public score profile.
- Produces resampling results without classification feedback.

- [x] **Step 1: Add RED tests proving profile propagation**

Use deliberately small test minima such as `4/3/2` in fixture-only profiles and assert permutation, bootstrap, selected-tau sensitivity, nonfinal ULF sensitivity, and jitter use those values. Assert results do not mutate source, prediction, branch-role, or final-model records.

- [x] **Step 2: Run configured formal/sensitivity tests and verify RED**

```bash
conda run -n leaddbs python -m unittest \
  my_helper.fiber.core.outcome_models.tests.test_configured_formal_backend \
  my_helper.fiber.core.outcome_models.tests.test_configured_sensitivity_backend \
  my_helper.fiber.core.outcome_models.tests.test_configured_jitter_spatial_qc -v
```

- [x] **Step 3: Thread `NormativeFiberScoreConfig` through every numerical target**

Do not rely on module defaults in configured execution. Each formal/sensitivity request must derive its policy from `context.config.model.normative_fiber["score"]` and record the six values in its manifest.

- [x] **Step 4: Preserve fold-local and replicate-local fitting**

Permutation outcomes, bootstrap samples, and jittered exposures re-estimate weights before calling the shared kernel. They may not reuse observed selected IDs or signs. The immutable final axis limits the feature universe but does not freeze resampled weights. Bump the normative-fiber jitter checkpoint method/version identity so checkpoints from the percentage-only scorer cannot resume under the new score contract.

Formal, sensitivity, and the existing OSS adapter must validate `data.mat:idx` axes with the canonical logical-array hash rather than the raw `.npy` file hash.

- [x] **Step 5: Run tests and commit**

```bash
conda run -n leaddbs python -m unittest \
  my_helper.fiber.core.outcome_models.tests.test_configured_formal_backend \
  my_helper.fiber.core.outcome_models.tests.test_configured_sensitivity_backend \
  my_helper.fiber.core.outcome_models.tests.test_configured_jitter_spatial_qc -v
git add \
  my_helper/fiber/core/analysis/stnsnr_normative_fiber_smoke_permutation.py \
  my_helper/fiber/core/analysis/stnsnr_normative_fiber_formal_bootstrap.py \
  my_helper/fiber/core/analysis/stnsnr_ulf_normative_fiber_sensitivity_observed.py \
  my_helper/fiber/core/analysis/stnsnr_normative_fiber_formal_jitter.py \
  my_helper/fiber/core/outcome_models/services/legacy_formal.py \
  my_helper/fiber/core/outcome_models/services/legacy_sensitivity.py \
  my_helper/fiber/core/outcome_models/tests/test_configured_formal_backend.py \
  my_helper/fiber/core/outcome_models/tests/test_configured_sensitivity_backend.py \
  my_helper/fiber/core/outcome_models/tests/test_configured_jitter_spatial_qc.py
git commit -m "fix: align fiber resampling score policy"
```

### Task 7: OSS Candidate Axis, Binary pPAM Scoring, And Exact Reuse

**Files:**
- Create: `my_helper/fiber/core/outcome_models/services/oss_sidecar.py`
- Modify: `my_helper/fiber/core/outcome_models/services/legacy_oss.py`
- Modify: `my_helper/fiber/core/outcome_models/services/oss.py`
- Modify: `my_helper/fiber/core/analysis/stnsnr_normative_fiber_oss_sidecar_worklist.py`
- Modify: `my_helper/fiber/core/analysis/stnsnr_normative_fiber_oss_parameter_preflight.py`
- Modify: `my_helper/fiber/core/analysis/stnsnr_normative_fiber_oss_activation_rows.py`
- Modify: `my_helper/fiber/core/analysis/stnsnr_normative_fiber_oss_sidecar_merge.py`
- Modify: `my_helper/fiber/core/analysis/stnsnr_normative_fiber_oss_sensitivity.py`
- Modify: `my_helper/fiber/core/outcome_models/services/default_registry.py`
- Modify: `my_helper/fiber/core/outcome_models/planner.py`
- Modify: `my_helper/fiber/core/outcome_models/tests/test_configured_oss_backend.py`
- Create: `my_helper/fiber/core/outcome_models/tests/test_oss_sidecar_service.py`
- Modify: `my_helper/fiber/core/outcome_models/tests/test_default_registry.py`
- Modify: `my_helper/fiber/core/outcome_models/tests/test_planner.py`

**Interfaces:**
- Consumes `FinalArtifactRecord.valid_feature_axis` and a destination-local `OSSSidecarBundle`.
- Produces `OSSSidecarPreparationRequest`, an endpoint-local `oss_sidecar_preparation` task, a hash-locked `OSSSidecarBundle`, binary pPAM formal sensitivity artifacts, and an exact sidecar compatibility/reuse key.

- [x] **Step 1: Review and supersede the existing OSS TDD patch**

Inspect the saved WIP only after Tasks 1-6 are integrated:

```bash
git stash show -p stash@{0}
```

Do not apply its coverage-only candidate derivation. Port only still-valid test intent against the new final-record contract: the expected sidecar axis is exactly `final.valid_feature_axis`. Keep the stash until Task 7 passes and is committed, then drop it explicitly.

- [x] **Step 2: Add RED candidate-axis tests**

Create a parent axis with four coverage-passing fibers and make one final weight nonfinite. Assert the immutable valid axis and OSS sidecar contain only the other three in parent order. Reject missing, extra, reordered, or hash-drifted IDs.

- [x] **Step 3: Add RED pPAM and fold-selection tests**

At the isolated threshold-function boundary, assert `0.49 -> 0`, `0.50 -> 1`, and `0.90 -> 1`. Persisted 10-sample pPAM sidecars must separately reject off-lattice values and use only `0.0, 0.1, ..., 1.0`. Assert each OSS training fold re-estimates weights and signed `K/H` selections on the fixed sidecar axis, while no function calls tau/Coverage on the binary matrix.

- [x] **Step 4: Implement exact cross-endpoint compatibility identity**

Create a canonical compatibility payload containing:

```text
source E-field hashes and the corresponding resolved stimulation-parameter MAT hashes
subject order
requested and modeled frequencies
canonical hemisphere and left-to-right mapping
max_probability_union merge rule
HF or ULF component identity
ordered valid fiber IDs and logical hash
OSS-DBSv2 environment/model identity

The identity also records the fixed pPAM sample count and requires a complete sample set for every subject/side/source. A cache entry is reusable only when its stored canonical payload is exactly equal to the current request payload; matching a digest string without payload equality is insufficient.
```

The compatibility identity additionally binds the parent selected-source axis, dTOR connectome input hash, OSS generator implementation hash, and actual MATLAB/OSS tool executable hashes. With ten fixed Bernoulli samples, every persisted probability must lie on the `0.0, 0.1, ..., 1.0` lattice; arbitrary continuous values are invalid even when finite and inside `[0, 1]`.

The configured left-side pathway is fixed as follows: transform the left stimulation/electrode geometry into right-canonical space with `ea_flip_lr_nonlinear`, run OSS against the same ordered `final.valid_feature_axis` used for the right side, and combine the resulting right-canonical probabilities with `max_probability_union`. Do not assume that equal left/right local fiber IDs encode tract homology. The compatibility payload and manifests must record the transform name plus an exact transform/code identity hash.

For ULF, the compatibility payload and destination manifest must also preserve the realized overlap mode. Use `matched_hf_peak_efield_selected_tau` when an accepted matched HF source supplied the exclusion threshold, and `hf_source_absent_all_false` when no HF source existed and the exclusion mask was therefore all false. HF uses `not_applicable`. The producer must never hard-code the finite-threshold mode for every ULF final.

Reuse is allowed only when the canonical hash matches exactly. The reused probability matrix may be content-addressed, but the destination bundle and manifest must carry the destination endpoint ID, final model ID, and final record hash.

- [x] **Step 5: Close the configured OSS producer/consumer DAG**

Add exactly one endpoint-local `oss_sidecar_preparation` task after the selected final's formal completion and before `oss_sensitivity`. The preparation service must expose:

```python
@dataclass(frozen=True)
class OSSSidecarPreparationRequest:
    task: TaskSpec
    final: FinalArtifactRecord
    output_root: Path
    compatibility_hash: str


class OSSSidecarPreparationService:
    def __init__(
        self,
        request_factory: Callable[
            [TaskSpec, RunContext, FinalArtifactRecord],
            OSSSidecarPreparationRequest,
        ],
        runner: Callable[[OSSSidecarPreparationRequest], TaskResult],
    ) -> None:
        self._request_factory = request_factory
        self._runner = runner

    def execute(self, task: TaskSpec, context: RunContext) -> TaskResult:
        final = load_final_record(task, context)
        request = self._request_factory(task, context, final)
        return self._runner(request)
```

Refactor the existing worklist, parameter-preflight, activation-row, and merge modules to accept immutable request objects rather than fixed `B_DTOR`/`D_DTOR` discovery. The service transforms left stimulation geometry with `ea_flip_lr_nonlinear`, runs the established `prepareaxonmodel -> leaddbs2ossdbs -> ossdbs -> run_pathway_activation` chain for both right-canonical side inputs on the exact realized valid axis, combines left-transformed/right probabilities with `max_probability_union`, and publishes `oss_sidecar_bundle` in task facts. The `oss_sensitivity` task has a typed successful dependency on this producer. Missing executables, incomplete subjects, transform failure, or merge failure are endpoint-local input/execution failures, never a hidden manual prerequisite.

Before generation, the producer validates that its formal dependency records the same `final_model_id` and final-record hash, and validates both parent and valid axes against their recorded ordered-array hashes. The consumer depends on the successful producer rather than carrying a redundant second formal edge. Corrupt or semantically invalid cache content is treated as a cache miss and regenerated; it is not accepted and does not permanently poison other compatible endpoints.

For an exact compatibility-hash hit, reuse the content-addressed probability matrix and ordered ID axis, then rewrite destination-local parameter/activation manifests and construct new `ArtifactRef`s bound to the destination final model and record hash.

- [x] **Step 6: Apply the shared score policy to OSS**

Pass the public six-field policy into `_loocv_oss` and `_full_sample_weights_scores`. Keep the sidecar axis fixed; fold-local nonconstant/finite weight checks only determine fold-valid weights and signed selections. Record all full/fold support fields.

- [x] **Step 7: Run OSS/planner/registry tests and commit**

Verified on `stnvop` before the Task 7 commit: 68 focused OSS/planner/registry tests and 298 complete `outcome_models` tests passed; `py_compile` and `git diff --check` also passed. No real OSS workload was launched during this unit/regression stage.

```bash
PYTHONPATH=my_helper/fiber/core:my_helper/fiber/core/analysis \
  conda run -n leaddbs python -m unittest \
  outcome_models.tests.test_configured_oss_backend \
  outcome_models.tests.test_configured_oss_scoring \
  outcome_models.tests.test_oss_ppam_generation \
  outcome_models.tests.test_oss_left_to_right_geometry \
  outcome_models.tests.test_oss_sidecar_merge_contract \
  outcome_models.tests.test_oss_sidecar_service \
  outcome_models.tests.test_default_registry \
  outcome_models.tests.test_planner -v
PYTHONPATH=my_helper/fiber/core:my_helper/fiber/core/analysis \
  conda run -n leaddbs python -m unittest discover \
  -s my_helper/fiber/core/outcome_models/tests -p 'test_*.py'
git add \
  my_helper/fiber/core/outcome_models/services/oss_sidecar.py \
  my_helper/fiber/core/outcome_models/services/legacy_oss.py \
  my_helper/fiber/core/outcome_models/services/oss.py \
  my_helper/fiber/core/analysis/stnsnr_normative_fiber_oss_sidecar_worklist.py \
  my_helper/fiber/core/analysis/stnsnr_normative_fiber_oss_parameter_preflight.py \
  my_helper/fiber/core/analysis/stnsnr_normative_fiber_oss_activation_rows.py \
  my_helper/fiber/core/analysis/stnsnr_normative_fiber_oss_sidecar_merge.py \
  my_helper/fiber/core/analysis/stnsnr_normative_fiber_oss_sensitivity.py \
  my_helper/fiber/core/outcome_models/services/default_registry.py \
  my_helper/fiber/core/outcome_models/planner.py \
  my_helper/fiber/core/outcome_models/tests/test_configured_oss_backend.py \
  my_helper/fiber/core/outcome_models/tests/test_oss_sidecar_service.py \
  my_helper/fiber/core/outcome_models/tests/test_default_registry.py \
  my_helper/fiber/core/outcome_models/tests/test_planner.py
git commit -m "feat: bind OSS to realized fiber axes"
```

### Task 8: Reporting, Documentation, Regression, And Two-Scale Acceptance

**Files:**
- Modify: `my_helper/fiber/core/outcome_models/services/legacy_reporting.py`
- Modify: `my_helper/fiber/core/outcome_models/tests/test_configured_reporting_backend.py`
- Modify: `my_helper/stnsnr/model_summaries/hf_3m_normative_connectome_fiber_model.md`
- Modify: `my_helper/stnsnr/model_summaries/ulf_addon_gain_normative_connectome_fiber_model.md`
- Modify: `my_helper/stnsnr/four_model_execution_implementation_notes.md`
- Modify: `my_helper/stnsnr/four_model_yaml_core_refactor_plan.md`
- Modify: `.planning/four-model-yaml-implementation/progress.md` locally only; do not stage `.planning`.

**Interfaces:**
- Consumes all score/support artifacts.
- Produces endpoint-aware report artifacts and final acceptance evidence.

- [x] **Step 1: Add RED reporting tests**

Assert reports expose full-sample and fold summaries for all required support fields, label limited/one-sided scores, retain the unique final model identity, and do not promote support status into source/prediction classification.

- [x] **Step 2: Implement numeric reporting and manifests**

Add the six score parameters, support-status counts, min-dominated proportions, and selected-ID hashes. Keep endpoint rows independent and engineering-equal.

- [x] **Step 3: Synchronize model and implementation documentation**

Describe implemented behavior and current test evidence only after code is green. Remove stale percentage-only score wording. Keep the explicit statement that user decisions take precedence over conflicting documentation.

- [x] **Step 4: Run the configured-core regression**

```bash
PYTHONPATH=my_helper/fiber/core:my_helper/fiber/core/analysis \
  conda run -n leaddbs python -m unittest discover \
  -s my_helper/fiber/core/outcome_models/tests \
  -p 'test_*.py' -v
```

Expected: all configured-core tests pass.

Verified before real-data acceptance: all 300 configured-core tests pass.

- [x] **Step 5: Run related legacy selftests and static checks**

```bash
conda run -n leaddbs python my_helper/fiber/core/analysis/stnsnr_four_model_stats_selftest.py
conda run -n leaddbs python my_helper/fiber/core/analysis/stnsnr_hf_normative_fiber_smoke_selftest.py
conda run -n leaddbs python my_helper/fiber/core/analysis/stnsnr_ulf_normative_fiber_observed_selftest.py
conda run -n leaddbs python -m compileall -q \
  my_helper/fiber/core/analysis \
  my_helper/fiber/core/outcome_models
git diff --check
```

Verified before real-data acceptance: all three named selftests report `PASS`;
Python compilation and `git diff --check` pass.

- [x] **Step 6: Validate the real MDS-UPDRS III/IV DAG before execution**

```bash
conda run -n leaddbs python my_helper/fiber/pipelines/run_configured_outcome_models.py \
  validate --config my_helper/stnsnr/config/four_model_v1/workflow.yaml
conda run -n leaddbs python my_helper/fiber/pipelines/run_configured_outcome_models.py \
  plan --config my_helper/stnsnr/config/four_model_v1/workflow.yaml \
  --scale mds_updrs_iii_score --scale mds_updrs_iv --through report
```

Verify all A/B/C/D endpoint tasks are present for both scales, every normative-fiber final has at most one OSS sidecar producer and one OSS fit, and there is no total/axial special task type.

Verified: configuration validation reports 24 catalog rows and zero input
failures. The report-through plan contains 205 tasks. All five dTOR
normative-fiber endpoint rows have exactly one OSS sidecar producer and one OSS
fit, no execution-stage name contains total/axial specialization, and the
omitted MDS-UPDRS IV immediate bindings are explicit nonfailure catalog rows.

- [ ] **Step 7: Execute the real two-scale workflow**

```bash
conda run -n leaddbs python my_helper/fiber/pipelines/run_configured_outcome_models.py \
  run --config my_helper/stnsnr/config/four_model_v1/workflow.yaml \
  --scale mds_updrs_iii_score --scale mds_updrs_iv --through report
```

The command prints `run_id` and `run_root`; record both in `.planning/four-model-yaml-implementation/progress.md`. If execution is interrupted, resume that exact run with:

```bash
RUN_ROOT=$(ls -td /Volumes/VAL/STNSNr/configured_model_runs/stnsnr_frequency_addon/* | head -n 1)
RUN_ID=${RUN_ROOT##*/}
conda run -n leaddbs python my_helper/fiber/pipelines/run_configured_outcome_models.py \
  run --config my_helper/stnsnr/config/four_model_v1/workflow.yaml \
  --scale mds_updrs_iii_score --scale mds_updrs_iv --through report \
  --resume --run-id "$RUN_ID"
```

Do not claim completion if OSS inputs cannot be generated, if any selected final lacks formal/sensitivity/report artifacts, or if the command exits nonzero. Record endpoint-local failures and continue other endpoints according to workflow policy.

First acceptance attempt
`20260710T143933Z_6b8054589fd9e59b` was intentionally interrupted after it
exposed a real direct-voxel qualification contract defect: the generic
equivalence reader expected normative-fiber `scores_csv`, while
`DirectVoxelTarget` exposes `subjects_csv`. The run had already proved
endpoint-local continuation and reached dTOR HF-fiber formal/jitter work, but it
cannot be acceptance evidence because the HF-voxel formal path was skipped.
Fix this mismatch with a RED test that uses the direct target field contract,
rerun the 300-test regression, commit the repair, and start a new clean-
provenance run. Do not resume the old run under changed code provenance.

Repair verification: the RED test reproduced the exact `scores_csv` attribute
error. The reader now accepts `subjects_csv` for direct targets and
`scores_csv` for fiber targets, while rejecting conflicting dual paths. All 301
configured-core tests, the direct formal-permutation selftest, compilation, and
`git diff --check` pass.

Second acceptance attempt
`20260710T151202Z_8d4e5419ee4ba1c2` proved the direct repair through complete
observed, formal permutation/bootstrap, jitter, sensitivity, and report tasks.
It then exposed an OSS producer provenance mismatch: `_source_rows` called the
legacy `manifest["outputs"]["mapping_qc_json"]` contract on a configured selected
manifest. Configured source rows instead belong to the exact endpoint-local
`sidecar_equivalence` QC artifact (or ULF `preprocessing_sidecars` QC artifact),
which is already indexed and hash locked. Repair the producer to resolve that
single completed task artifact by endpoint and stage, require its artifact-index
path/hash to match, and parse source rows from the QC payload. Add HF and ULF
contract tests plus tamper rejection before another clean run.

Repair verification: configured HF now reads ordered source rows from the
single completed `sidecar_equivalence` QC artifact; configured ULF reads them
from the single completed `preprocessing_sidecars` QC artifact. Both require an
exact endpoint/stage match and artifact-index path/SHA-256 match. HF, ULF, and
hash-drift tests pass, as do all 304 configured-core tests, Python compilation,
and `git diff --check`.

- [ ] **Step 8: Audit final artifacts and state closure**

```bash
RUN_ROOT=$(ls -td /Volumes/VAL/STNSNr/configured_model_runs/stnsnr_frequency_addon/* | head -n 1)
RUN_ID=${RUN_ROOT##*/}
conda run -n leaddbs python my_helper/fiber/pipelines/run_configured_outcome_models.py \
  status --output-root /Volumes/VAL/STNSNr --run-id "$RUN_ID"
conda run -n leaddbs python my_helper/fiber/pipelines/run_configured_outcome_models.py \
  artifacts --output-root /Volumes/VAL/STNSNr --run-id "$RUN_ID"
```

For each acceptance endpoint/model family, require one realized final or explicit `no_final_model`; formal and sensitivity must reference only the realized final/fallback; every normative-fiber support artifact must contain the approved parameters and support fields.

- [ ] **Step 9: Commit completion evidence without pushing**

```bash
git add \
  my_helper/fiber/core/outcome_models/services/legacy_reporting.py \
  my_helper/fiber/core/outcome_models/tests/test_configured_reporting_backend.py \
  my_helper/stnsnr/model_summaries/hf_3m_normative_connectome_fiber_model.md \
  my_helper/stnsnr/model_summaries/ulf_addon_gain_normative_connectome_fiber_model.md \
  my_helper/stnsnr/four_model_execution_implementation_notes.md \
  my_helper/stnsnr/four_model_yaml_core_refactor_plan.md
git commit -m "docs: record fiber scoring acceptance"
```

---

## Completion Criteria

Implementation is complete only when all conditions hold:

1. The six public score fields validate strictly and reach every normative-fiber executable Round.
2. HF, ULF, DeltaHFScore, formal, bootstrap, jitter, and OSS all call the same deterministic score kernel.
3. Full sample and every held-out fold emit all required count, dominated, status, and selected-ID hash fields.
4. One-sided support is labeled limited and remains runnable; no-valid-signed-fiber is explicit.
5. No full-sample signed ranking or selected IDs leak into non-OSS LOOCV folds.
6. Each normative-fiber final record is bound to its ordered realized `F_valid` axis.
7. OSS uses exactly that axis, binary `p(A)>=0.5`, fold-local weights/selections, and an exact reuse key with destination-local provenance.
8. Source/prediction/final classification is unchanged by support QC or later formal/sensitivity results.
9. All configured-core and related legacy tests pass.
10. The MDS-UPDRS III/IV workflow reaches report with complete artifacts or records explicit endpoint-local terminal failures; no silent manual OSS dependency remains.
