# Whole-Brain ROI Atlas Builder

This standalone Python package converts an integer whole-brain labeling into a deterministic Lead-DBS atlas and computes exact endpoint coverage for a Lead-DBS HDF5 connectome.

The repository configuration builds `dTOR-HybraPD Whole Brain (Yu 2021)` from HybraPD anatomy and dTOR fibers. It uses strict endpoint-voxel assignment and does not use dTOR to define anatomical boundaries.

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
  --atlas-root "templates/space/MNI152NLin2009bAsym/atlases/dTOR-HybraPD Whole Brain (Yu 2021)"
```

## Outputs

The atlas root contains the exact 0.5 mm label image, resolved/source label tables, `lh`, `rh`, `midline`, and `mixed` Lead-DBS directories, complete CSV/JSON manifests, dTOR endpoint QC, provenance, and artifact hashes. White-matter masks are retained under `.qc/white_matter` and are not discovered as main connectivity targets.

The Python builder intentionally does not create `atlas_index.mat` or `gm_mask.nii.gz`. Lead-DBS creates them when the atlas is first opened in the UI.

The generated atlas `README.md` lists all 198 regions and their exact dTOR endpoint coverage.
