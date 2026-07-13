# dTOR-HybraPD Whole-Brain ROI Atlas Design

## Purpose

Create a deterministic, standalone Python workflow that maps the existing HybraPD Whole Brain labeling into the Lead-DBS MNI152NLin2009bAsym 0.5 mm grid and measures its exact coverage of dTOR streamline endpoints. HybraPD remains the sole anatomical source; dTOR supplies streamlines, not anatomy.

## Inputs

- HybraPD integer labeling NIfTI and its integer-to-name text table.
- Lead-DBS `MNI152NLin2009bAsym/t1.nii` as the target grid.
- Lead-DBS dTOR HDF5 connectome with `fibers` and `idx` datasets.
- A strict YAML config that identifies input/output paths, the expected label count, category ID sets, and execution chunk size.

All input files are hashed. Unknown config fields, missing labels, duplicate IDs, invalid category coverage, inconsistent HDF5 dimensions, and a non-integer source image are fatal validation errors.

## Atlas Construction

The source integer image is resampled to the reference shape and affine with nearest-neighbor interpolation and an integer output type. The resulting `labels.nii.gz` remains mutually exclusive: a voxel contains one original label ID or zero.

The 198 labels are classified as follows:

- 90 bilateral cortical and limbic labels;
- 18 bilateral cerebellar-hemisphere labels;
- 8 midline vermis labels;
- 34 bilateral subcortical labels;
- 48 white-matter labels retained for QC only.

The main Lead-DBS atlas contains 150 binary regions in `lh`, `rh`, `midline`, and `mixed`. Bilateral counterparts use the same filename in `lh` and `rh`. The expected distribution is 71 left, 71 right, 8 midline, and 0 mixed. White-matter masks are written under `.qc/white_matter`, which is ignored by Lead-DBS atlas indexing and by the existing Python target discovery.

## Laterality Resolution

Non-white-matter labels retain their source names and declared laterality. Their centroids and contralateral voxel fractions are reported.

The HybraPD white-matter text metadata reverses spatial laterality for 42 unilateral labels. The workflow determines their resolved side from the MNI-space centroid, changes only the display/output suffix, and preserves the source label ID and source name. For example, source label 217 is resolved as left ALIC and source label 218 as right ALIC. Every correction is marked in the manifest.

## dTOR Endpoint Census

The connectome is read sequentially in fiber chunks. Only the first and last point of each fiber are assigned. World coordinates are converted to the resampled label grid; an endpoint receives the integer value of its containing voxel or zero for `unassigned`. No distance tolerance, dilation, or nearest-region fallback is applied.

The census reports per label:

- endpoint count and fraction of all endpoints;
- unique fiber count with at least one endpoint in the label and fraction of all fibers;
- anatomical category, tissue class, side, and inclusion policy.

The summary must account exactly for 11,820,000 fibers and 23,640,000 endpoints.

## Outputs and Publication

The default atlas directory is `templates/space/MNI152NLin2009bAsym/atlases/dTOR-HybraPD Whole Brain (Yu 2021)` and contains:

- `labels.nii.gz`, `labels.txt`, and `labels_source.txt`;
- `lh`, `rh`, `midline`, and `mixed` main ROI directories;
- `.qc/white_matter` binary masks;
- `region_manifest.csv`, `region_manifest.json`, and `dtor_endpoint_qc.csv`;
- `build_manifest.json`, `artifact_index.csv`, `config_resolved.yaml`, and `README.md`.

README lists all 198 labels grouped by category. `atlas_index.mat` and `gm_mask.nii.gz` are intentionally absent from Python publication and are generated when the user first opens the atlas in Lead-DBS.

Publication uses a sibling staging directory followed by an atomic rename. An existing output with the same fingerprint and valid hashes is reused. Any mismatch fails without overwriting or deleting the existing directory.

## Interfaces

Public Python API:

```python
build_whole_brain_roi_atlas(config: AtlasBuildConfig) -> AtlasBuildResult
```

CLI commands:

```text
whole-brain-roi-atlas validate --config CONFIG
whole-brain-roi-atlas build --config CONFIG
whole-brain-roi-atlas status --atlas-root ATLAS_ROOT
```

The implementation is generic; the tracked dTOR-HybraPD YAML config supplies dataset-specific paths and label category sets.

## Acceptance Criteria

- Exactly 198 labels survive resampling and every mask is nonempty.
- Exactly 150 main masks and 48 white-matter QC masks are published.
- Main masks are mutually exclusive and reconstruct the non-white-matter portion of `labels.nii.gz` exactly.
- All masks match the reference shape, affine, qform, and sform.
- All endpoint totals reconcile exactly and all artifacts pass SHA-256 verification.
- Rebuilding from identical inputs is deterministic and reuses the immutable output.
