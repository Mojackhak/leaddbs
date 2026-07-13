# HybraPD Atlas Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the anatomical atlas from `dTOR-HybraPD Whole Brain (Yu 2021)` to `HybraPD Whole Brain (Yu 2021)` while retaining dTOR names only for endpoint-QC provenance.

**Architecture:** Keep the generic builder and the dTOR-specific configuration filename unchanged. Change the configured publication root and generated atlas title, then produce a new immutable build at the corrected path; preserve the prior untracked output in macOS Trash after the replacement passes all acceptance checks.

**Tech Stack:** Python 3.11, unittest, PyYAML, NIfTI artifacts, Git, Conda environment `leaddbs`.

## Global Constraints

- Use Conda environment `leaddbs`.
- Update user-facing documentation before production code or tests.
- Use test-first development for the configured atlas name and generated README title.
- Keep `dtor_endpoint_qc.csv` and `dtor_hybrapd_whole_brain.yaml` because they identify endpoint-census provenance.
- Do not overwrite or permanently delete the existing untracked atlas directory.
- Do not push remote changes.

---

### Task 1: Align tracked documentation with the atlas identity

**Files:**
- Modify: `docs/superpowers/plans/2026-07-13-dtor-hybrapd-whole-brain-atlas.md`
- Modify: `my_helper/fiber/README.md`
- Modify: `my_helper/fiber/core/whole_brain_roi_atlas/README.md`

**Interfaces:**
- Consumes: naming boundary defined in `docs/superpowers/specs/2026-07-13-hybrapd-whole-brain-atlas-design.md`.
- Produces: user instructions that point to `templates/space/MNI152NLin2009bAsym/atlases/HybraPD Whole Brain (Yu 2021)` and describe dTOR only as the endpoint-QC source.

- [ ] **Step 1: Update the original implementation plan terminology**

Rename its title to `HybraPD Whole-Brain ROI Atlas Implementation Plan` and describe the tracked YAML as a dTOR endpoint-census configuration rather than part of the atlas identity.

- [ ] **Step 2: Update package documentation**

Use the heading `HybraPD Whole-Brain ROI Atlas` and the exact status command:

```bash
conda run -n leaddbs python \
  my_helper/fiber/pipelines/whole-brain-roi-atlas status \
  --atlas-root "templates/space/MNI152NLin2009bAsym/atlases/HybraPD Whole Brain (Yu 2021)"
```

- [ ] **Step 3: Validate and commit documentation**

Run: `rg -n 'dTOR-HybraPD Whole Brain \(Yu 2021\)' docs my_helper/fiber --glob '*.md'`

Expected: no atlas-facing use of the old name.

Run: `git diff --check`

Expected: exit 0.

Commit: `docs: rename HybraPD anatomical atlas`

### Task 2: Lock and implement the corrected configured name

**Files:**
- Modify: `my_helper/fiber/core/whole_brain_roi_atlas/tests/test_repository_config.py`
- Modify: `my_helper/fiber/core/whole_brain_roi_atlas/tests/test_pipeline_cli.py`
- Modify: `my_helper/fiber/configs/dtor_hybrapd_whole_brain.yaml`
- Modify: `my_helper/fiber/core/whole_brain_roi_atlas/artifacts.py`

**Interfaces:**
- Consumes: `load_atlas_config(path) -> AtlasBuildConfig` and `build_whole_brain_roi_atlas(config) -> AtlasBuildResult`.
- Produces: a configured root named `HybraPD Whole Brain (Yu 2021)` and generated README title `# HybraPD Whole-Brain ROI Atlas`.

- [ ] **Step 1: Write failing naming assertions**

Add these behavioral assertions:

```python
self.assertEqual(config.atlas_root.name, "HybraPD Whole Brain (Yu 2021)")
self.assertTrue(readme.startswith("# HybraPD Whole-Brain ROI Atlas\n"))
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
conda run -n leaddbs python -m unittest \
  my_helper.fiber.core.whole_brain_roi_atlas.tests.test_repository_config \
  my_helper.fiber.core.whole_brain_roi_atlas.tests.test_pipeline_cli
```

Expected: failures showing the old configured directory and old generated title.

- [ ] **Step 3: Apply the minimal production changes**

Set the YAML output to:

```yaml
output:
  atlas_root: ../../../templates/space/MNI152NLin2009bAsym/atlases/HybraPD Whole Brain (Yu 2021)
```

Set the generated README title to:

```python
"# HybraPD Whole-Brain ROI Atlas",
```

- [ ] **Step 4: Run focused and full tests**

Run the focused command from Step 2 and then:

```bash
conda run -n leaddbs python -m unittest discover \
  -s my_helper/fiber/core/whole_brain_roi_atlas/tests -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit the green change**

Commit: `fix: name atlas independently of dTOR`

### Task 3: Publish and verify the corrected real atlas

**Files:**
- Create through the builder: `templates/space/MNI152NLin2009bAsym/atlases/HybraPD Whole Brain (Yu 2021)/`
- Preserve in Trash: prior `templates/space/MNI152NLin2009bAsym/atlases/dTOR-HybraPD Whole Brain (Yu 2021)/`

**Interfaces:**
- Consumes: `my_helper/fiber/configs/dtor_hybrapd_whole_brain.yaml`.
- Produces: a complete immutable 198-label atlas under the corrected name.

- [ ] **Step 1: Validate the real configuration**

```bash
conda run -n leaddbs python \
  my_helper/fiber/pipelines/whole-brain-roi-atlas validate \
  --config my_helper/fiber/configs/dtor_hybrapd_whole_brain.yaml
```

Expected: validation succeeds with 198 labels and the corrected atlas root.

- [ ] **Step 2: Build at the corrected root**

```bash
conda run -n leaddbs python \
  my_helper/fiber/pipelines/whole-brain-roi-atlas build \
  --config my_helper/fiber/configs/dtor_hybrapd_whole_brain.yaml
```

Expected: status `complete`, 198 labels, 150 main ROIs, 48 white-matter QC ROIs, 11,820,000 fibers, and 23,640,000 endpoints.

- [ ] **Step 3: Verify deterministic reuse and artifact integrity**

Run the same build command again and the CLI `status` command against the corrected root.

Expected: the second build reports reuse and all indexed SHA-256 hashes validate.

- [ ] **Step 4: Preserve the old untracked directory in Trash**

After the corrected build passes, move the complete old directory to a uniquely named location under `~/.Trash` without overwriting any existing item.

- [ ] **Step 5: Run final acceptance checks**

Verify 71 `lh`, 71 `rh`, 8 `midline`, 0 `mixed`, and 48 recursively stored white-matter masks. Confirm `dtor_endpoint_qc.csv` sums to 23,640,000 endpoints, `README.md` begins with the corrected title, the old atlas path is absent, `git diff --check` passes, and the Git working tree is clean.
