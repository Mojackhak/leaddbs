# WarpSlicer Helpers

Utilities in this folder build auditable Slicer/Lead-DBS warp corrections from
landmark pairs. The initial use case is a legacy-contact compatibility warp:
current Lead-DBS MNI contact coordinates are treated as moving landmarks and
historical cohort MNI contact coordinates are treated as fixed landmarks.

The workflow is intentionally non-destructive by default. It writes candidate
residual and composite transforms to a subject-local output folder, validates
contact-level residuals, and leaves the active Lead-DBS normalization transforms
unchanged until a validated candidate is explicitly installed.
Existing run outputs, including logs, are moved to a timestamped `backups`
folder before a new run writes replacements.

## ZhangMing Example

Run from the Lead-DBS repository root:

```bash
/opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/warpslicer/examples/zhangming_legacy_contact_compat.py
```

The example reads:

- current reconstruction:
  `/Volumes/VAL/STNSNr/derivatives/leaddbs/sub-ZhangMing/reconstruction/sub-ZhangMing_desc-reconstruction.mat`
- legacy cohort table:
  `/Volumes/VAL/STNSNr/summary/cohort/lead/contact_reco_space_locs.pkl`
- current ANTs transforms under:
  `/Volumes/VAL/STNSNr/derivatives/leaddbs/sub-ZhangMing/normalization/transformations`

It writes candidate outputs under:

`/Volumes/VAL/STNSNr/derivatives/leaddbs/sub-ZhangMing/warpdrive/legacy_contact_compat`

At the end of a run, the example prints the ordinary Slicer-composed inverse
validation and the `PointExact` inverse validation. The grid validation is the
highest-precision check of the written displacement field; the ANTs validation
reports what Lead-DBS/ANTs point-transform tooling reads back from the same
file.

## ZhangMing Install

After the compatibility candidates have been generated and validated, install
the candidate transforms and legacy-compatible MNI reconstruction with:

```bash
/opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/warpslicer/examples/zhangming_install_legacy_contact_compat.py
```

The installer is intentionally strict. It stops before changing official files
unless the validated candidate forward transform, the `PointExact` inverse
transform, the original transforms, and the reconstruction file all exist. It
also requires `validation_summary.json` to report a rounded-exact
`PointExact` grid validation with maximum error below `1e-6` mm.

Original official files are copied to same-folder `-bak` files before
replacement:

- `sub-ZhangMing_from-anchorNative_to-MNI152NLin2009bAsym_desc-ants-bak.nii.gz`
- `sub-ZhangMing_from-MNI152NLin2009bAsym_to-anchorNative_desc-ants-bak.nii.gz`
- `sub-ZhangMing_desc-reconstruction-bak.mat`

If any of those backups already exists, installation aborts to avoid replacing
the first backup. Recovery is a manual copy from the `-bak` files back to their
original names.

The installed forward transform is the ordinary Slicer-composed candidate. The
installed inverse transform is the `PointExact` inverse candidate. The
reconstruction update only changes `reco.mni` contacts, markers, trajectories,
and angles; `reco.native` and `reco.scrf` remain unchanged.

## Precision

For `Sub-ZhangMing`, the legacy cohort `MNI_x`, `MNI_y`, and `MNI_z` values
round-trip exactly at up to seven decimal places. Validation reports both full
floating-point residuals and rounded agreement at the requested decimal places.

## Notes

This helper uses SlicerForLeadDBS command-line modules directly:

- `FiducialRegistrationVariableRBF`
- `CompositeToGridTransform`

This avoids depending on an interactive Slicer session and matches the same
core transform composition used by WarpDrive hardening.

The RBF residual is written as an ITK displacement field with `.nrrd` suffix.
The final candidate forward and inverse transforms are written as
Lead-DBS-compatible ANTs `.nii.gz` grid transforms.

For Lead-DBS contact coordinates, validation must use the BIDS inverse transform
file (`from-MNI...to-anchorNative`) because ANTs point transforms are applied in
the opposite direction from image resampling. The helper therefore validates the
candidate inverse transform against the legacy contact coordinates.

If a first candidate leaves sub-voxel residuals, `CompatPaths` may point
`legacy_target_override_csv` to a CSV file with columns
`contact,target_mni_x,target_mni_y,target_mni_z`. This override is used only as
the RBF fitting target. Final validation and the `PointExact` inverse still use
the original legacy cohort coordinates as the expected coordinates.

For contact-level numerical matching, the helper can also write a
`PointExact` candidate inverse transform. This is a local grid correction on
top of the Slicer-composed inverse transform: it solves the trilinear grid
weights around each native contact point so that the displacement field samples
to the requested legacy MNI coordinate at those points. The Slicer-composed
forward and inverse candidates remain available as auditable global transforms;
the point-exact inverse is the contact-coordinate compatibility artifact.
