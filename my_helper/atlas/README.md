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

## Current Threshold Policy

- STN/SNr: `Custom_Ewert_Zhang_Middlebrooks > 0.05`.
- STNSNr: side-specific union of STN and SNr at `> 0.05`.
- STNSNrplus: STNSNr with 2 mm dilation on the 0.5 mm MNI reference grid.
- GPe/GPi: `DISTAL (Ewert 2017) > 0.25`.
- Julich thalamic nuclei: `>= 25%`.
- HCPex labels: exact label membership.
- PPN and Allen superior colliculus masks: `> 0`.

See `seed_target_binary_atlas_builder_plan.md` for details and rationale.
