# Atlas Helpers

This folder contains reusable atlas-building helpers for Lead-DBS seed-target tractography.

The current builder converts declarative JSON ROI specifications into binary MNI-space Lead-DBS atlas folders. Each generated atlas includes side-specific ROI masks, a provenance manifest, and a QC table.

## Build STN/SNr Connected-Region Atlases

Run from MATLAB:

```matlab
addpath(genpath('/Users/mojackhu/Github/leaddbs/my_helper/atlas'));
build_stn_connected_regions_atlas();
build_snr_connected_regions_atlas();
build_stnsnr_connected_regions_atlas();
```

Generated outputs:

```text
/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/atlases/STN-connected regions
/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/atlases/SNr-connected regions
/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/atlases/STNSNr-connected regions
```

The generated atlas directories live under the Lead-DBS template tree and are ignored by Git. The source code, plan, and JSON specs live in this folder.

## ROI Specification

Specs are stored in:

```text
my_helper/atlas/specs/stn_connected_regions.json
my_helper/atlas/specs/snr_connected_regions.json
my_helper/atlas/specs/stnsnr_connected_regions.json
```

Supported operations:

- `threshold`: threshold a continuous or probabilistic source image.
- `copy_binary`: binarize a mask using `> 0`.
- `label_union`: extract one or more labels from a discrete label atlas.
- `posterior_split`: extract the posterior half or third of a source mask by MNI y coordinate.
- `union`, `intersect`, and `subtract`: define composite ROI masks from source masks.
- `dilate_mm`: dilate a source mask by a millimeter radius on the reference grid.
- `probability_sum_threshold`: add aligned source probability images before
  thresholding, preserving their different cropped extents.

## STNVOplus Atlas

`specs/stnvo_plus.json` defines the approved bilateral STNplus and VOplus masks
from `DISTAL STN_Vop_main (Ewert 2017)`. Both use an absolute `>= 0.05`
threshold followed by nearest-neighbor resampling and 2 mm Euclidean dilation
on the 0.5 mm reference grid. VO is thresholded after adding Voa and Vop, not
after binarizing them separately. The source Voa is already restricted to its
main component at approximately 0.5 probability; this build does not restore
its removed periphery. Overlap between the expanded seeds is retained.

Use `build_stnvo_plus_atlas()` to create a new output directory, record overlap,
and preserve reference qform/sform metadata. It refuses an existing destination
and does not modify source atlases or start tractography.

## D99 Limbic, Frontal, and Pallidal Atlas

`build_d99_limbic_atlas.py` creates the approved D99 atlas with 36 bilateral
entries: independent NAc/ALIC/GPi/GPe, 29 retained subregions, and exact AMY,
HIP, and mPFC unions. Masks remain on the original 0.25 mm D99 grid without
resampling. Existing derived ALIC masks are embedded on that same lattice.
`build_d99_limbic_atlas_index.m` uses the native ROI interfaces to generate a
display cache with merged and subregion presets. See
[`d99_limbic_atlas.md`](d99_limbic_atlas.md) for definitions, commands, and QC;
the explicit source map is `specs/d99_limbic_regions.json`.

## Current Threshold Policy

- STN/SNr: `Custom_Ewert_Zhang_Middlebrooks > 0.05`.
- STNSNr: side-specific union of STN and SNr at `> 0.05`.
- STNSNrplus: STNSNr with 2 mm dilation on the 0.5 mm MNI reference grid.
- GPe/GPi: `DISTAL (Ewert 2017) > 0.25`.
- Julich thalamic nuclei: `>= 25%`.
- HCPex labels: exact label membership.
- PPN and Allen superior colliculus masks: `> 0`.

See `seed_target_binary_atlas_builder_plan.md` for details and rationale.

## Custom SNr Left-To-Right Flip QA

Run this atlas QA script from MATLAB to verify how Lead-DBS nonlinear
left-to-right flipping maps the continuous Custom left SNr atlas onto the
native right SNr atlas:

```bash
/Applications/MATLAB_R2024b.app/bin/matlab -batch "run('/Users/mojackhu/Github/leaddbs/my_helper/atlas/run_custom_snr_lr_flip_test.m')"
```

The script uses `ea_flip_lr_nonlinear` only; it does not use a manual x-axis
mirror. It writes outputs to:

```text
/Volumes/VAL/STNSNr/summary/atlas_qc/lr_flip/Custom_Ewert_Zhang_Middlebrooks_SNr/
```

Main outputs:

- `lh_SNr_flipped_to_right.nii.gz`
- `lh_SNr_flipped_to_right_on_rh_grid.nii.gz`
- `lh_SNr_flip_vs_rh_continuous_diff.nii.gz`
- `lh_SNr_flip_vs_rh_metrics.csv`
- `lh_SNr_flip_vs_rh_manifest.json`

The metrics CSV reports continuous-image difference metrics and thresholded
Dice/Jaccard/volume metrics at `0.001`, `0.01`, `0.05`, `0.25`, and `0.5`.
Do not use `> 0` as the main overlap threshold: Lead-DBS' default B-spline
interpolation can create tiny nonzero values and small negative or above-one
values around mask boundaries. The `> 0.05` threshold is the primary threshold
for the Custom STN/SNr atlas definitions used in this project.

This script is an atlas flip QA utility, not a fiber tracking pipeline. Keep it
under `my_helper/atlas` rather than `my_helper/fiber/stnsnr`.
