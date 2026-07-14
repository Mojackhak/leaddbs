# Whole-Brain ROI Atlas Builder

This standalone Python package converts an integer whole-brain labeling into a deterministic Lead-DBS atlas and computes exact endpoint coverage for a Lead-DBS HDF5 connectome.

The repository configuration builds `HybraPD Whole Brain (Yu 2021)` from HybraPD anatomy and measures endpoint coverage using dTOR fibers. It uses strict endpoint-voxel assignment and does not use dTOR to define anatomical boundaries.

## Commands

Run from the repository root in Conda environment `leaddbs`:

```bash
conda run -n leaddbs python \
  my_helper/fiber/pipelines/whole-brain-roi-atlas validate \
  --config my_helper/fiber/configs/dtor_hybrapd_whole_brain.yaml
```

```bash
conda run -n leaddbs python \
  my_helper/fiber/pipelines/whole-brain-roi-atlas build \
  --config my_helper/fiber/configs/dtor_hybrapd_whole_brain.yaml
```

```bash
conda run -n leaddbs python \
  my_helper/fiber/pipelines/whole-brain-roi-atlas status \
  --atlas-root "templates/space/MNI152NLin2009bAsym/atlases/HybraPD Whole Brain (Yu 2021)"
```

## Outputs

The atlas root contains the exact 0.5 mm label image, resolved/source label tables, `lh`, `rh`, `midline`, and `mixed` Lead-DBS directories, complete CSV/JSON manifests, dTOR endpoint QC, provenance, and artifact hashes. White-matter masks are retained under `.qc/white_matter` and are not discovered as main connectivity targets.

The Python builder intentionally does not create `atlas_index.mat` or `gm_mask.nii.gz`. Lead-DBS creates them when the atlas is first opened in the UI.

The generated atlas `README.md` lists all 198 regions and their exact dTOR endpoint coverage.

## Superseded Repository Build

The repository configuration was built and independently verified on 2026-07-13,
before the label correction documented below:

- build fingerprint: `058ee47f5e80245655abbeb6870944eb4828fb6356de151c39d17940b1f686e1`;
- 198 integer labels and region-manifest rows;
- 150 main ROIs: 71 left, 71 right, 8 midline, and 0 mixed;
- 48 hidden white-matter QC ROIs;
- 42 spatial laterality corrections in white-matter display metadata;
- 11,820,000 fibers and 23,640,000 reconciled endpoints;
- 207 indexed artifacts with verified SHA-256 hashes;
- exact immutable reuse on a second build.

## HybraPD Label Correction

The original two-column label table distributed with the local whole-brain
labeling assigned incorrect anatomical names to 18 bilateral subcortical label
IDs. On 2026-07-14, the mapping was checked against
`PD_template_display_whole_anat_names.label`, the integer source image, spatial
laterality, and the Lead-DBS HybraPD probability ROIs.

The authoritative corrections are:

| Label IDs | Previous canonical name | Correct canonical name |
| --- | --- | --- |
| 307/308 | `Extended_amygdala` | `Ventral_pallidum` |
| 309/310 | `Ventral_pallidum` | `External_globus_pallidus` |
| 311/312 | `External_globus_pallidus` | `Internal_globus_pallidus` |
| 313/314 | `Internal_globus_pallidus` | `Pars_reticulata_of_substantia_nigra` |
| 315/316 | `Pars_reticulata_of_substantia_nigra` | `Pars_compacta_of_substantia_nigra` |
| 317/318 | `Pars_compacta_of_substantia_nigra` | `Red_nucleus` |
| 319/320 | `Red_nucleus` | `Subthalamic_nucleus` |
| 321/322 | `Subthalamic_nucleus` | `Habenular_nucleus` |
| 333/334 | `Thalamus` | `Dentate_nucleus` |

The integer source image and the resampled multi-label image are spatially
correct; the defect is limited to the ID-to-name association. Consequently,
existing connectivity results may be repaired without rescanning connectome
streamlines: target names and paths are migrated, while every spatial mask's
fiber-membership set and all per-mask fiber counts must remain identical. The
CSR segments may be reordered because the corrected target IDs change the
pipeline's deterministic lexical target order. Any migrated result must record
the source label-table hash, the previous run fingerprint, the correction
mapping, and regenerated artifact hashes in its provenance.

The ITK-SNAP source names are retained as provenance, while Lead-DBS outputs use
expanded English canonical names with `_L` and `_R` suffixes. White-matter
laterality continues to be resolved from MNI-space centroids rather than from
the historically inverted suffixes in the old two-column table.
