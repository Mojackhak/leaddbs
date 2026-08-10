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

## SNr030 / ZhangMing Example

Run from the Lead-DBS repository root:

```bash
/opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/warpslicer/examples/zhangming_legacy_contact_compat.py
```

The example reads:

- preserved pre-compatibility reconstruction:
  `/Volumes/VAL/STNSNr/derivatives/leaddbs/sub-SNr030/bak/sub-SNr030_desc-reconstruction-bak.mat`
- legacy cohort table:
  `/Volumes/VAL/STNSNr/summary/cohort/lead/contact_reco_space_locs.pkl`
- preserved pre-compatibility ANTs transforms under:
  `/Volumes/VAL/STNSNr/derivatives/leaddbs/sub-SNr030/bak`

It writes candidate outputs under:

`/Volumes/VAL/STNSNr/derivatives/leaddbs/sub-SNr030/warpdrive/legacy_contact_compat`

At the end of a run, the example prints the ordinary Slicer-composed inverse
validation, the `PointExact` authoritative-field validation, and the validation
of the numerically derived companion field. The grid validation is the
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
unless the validated numerically derived forward transform, the `PointExact`
authoritative inverse transform, the original transforms, and the
reconstruction file all exist. It also requires `validation_summary.json` to
report a rounded-exact `PointExact` grid validation with maximum error below
`1e-6` mm and a successful numerical-inversion validation.

Original official files are moved into the subject-level `bak` folder before
replacement. The installer creates this folder when needed:

`/Volumes/VAL/STNSNr/derivatives/leaddbs/sub-SNr030/bak`

- `sub-SNr030_from-anchorNative_to-MNI152NLin2009bAsym_desc-ants-bak.nii.gz`
- `sub-SNr030_from-MNI152NLin2009bAsym_to-anchorNative_desc-ants-bak.nii.gz`
- `sub-SNr030_desc-reconstruction-bak.mat`

If any of those backups already exists, installation aborts to avoid replacing
the first backup. Recovery is a manual copy from the `bak` folder back to the
original formal-file locations.

The installed inverse transform is the `PointExact` candidate. The installed
forward transform is its numerical inverse; the ordinary Slicer-composed
forward is retained only as the numerical solver's initial estimate and as an
auditable intermediate. The reconstruction update only changes `reco.mni`
contacts, markers, trajectories, and angles; `reco.native` and `reco.scrf`
remain unchanged.

## SNr029 / HuangDan Build And Install

`Sub-HuangDan` uses the same legacy-contact compatibility strategy as
`Sub-ZhangMing`: current Lead-DBS MNI contacts are the moving landmarks and the
legacy cohort `MNI_x`, `MNI_y`, and `MNI_z` values are the fixed landmarks.
Candidate rebuilding reads the preserved pre-compatibility reconstruction and
EasyReg fields under `sub-SNr029/bak`; it must not fit residuals from the
already legacy-compatible active reconstruction.

Run from the Lead-DBS repository root:

```bash
/opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/warpslicer/examples/huangdan_build_and_install_legacy_contact_compat.py
```

The script first builds candidates under:

`/Volumes/VAL/STNSNr/derivatives/leaddbs/sub-SNr029/warpdrive/legacy_contact_compat`

It installs the candidates only after the `PointExact` inverse grid validation
is rounded-exact at seven decimal places and the maximum grid error is below
`1e-6` mm. The installed inverse transform is the `PointExact` candidate, and
the installed forward transform is derived by numerical inversion of that
same field.

Original official files are moved into:

`/Volumes/VAL/STNSNr/derivatives/leaddbs/sub-SNr029/bak`

- `sub-SNr029_from-anchorNative_to-MNI152NLin2009bAsym_desc-ants-bak.nii.gz`
- `sub-SNr029_from-MNI152NLin2009bAsym_to-anchorNative_desc-ants-bak.nii.gz`
- `sub-SNr029_desc-reconstruction-bak.mat`

If any of those backups already exists, installation aborts. Recovery is a
manual copy from the `bak` folder back to the original formal-file locations.
The reconstruction update only changes `reco.mni`; `reco.native` and
`reco.scrf` remain unchanged.

## Precision

For `Sub-ZhangMing` / `sub-SNr030`, the legacy cohort `MNI_x`, `MNI_y`, and `MNI_z` values
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

For contact-level numerical matching, the helper writes a `PointExact`
candidate inverse transform. This is a local grid correction on
top of the Slicer-composed inverse transform: it solves the trilinear grid
weights around each native contact point so that the displacement field samples
to the requested legacy MNI coordinate at those points. The Slicer-composed
forward and inverse candidates remain available as auditable intermediates.
The point-exact inverse is the authoritative contact-coordinate compatibility
field. The final companion field is generated only by numerically inverting
this authoritative field on the template grid; the independently fitted
reverse RBF is never installed as its inverse.

## Authoritative Direction And Numerical Inversion

Lead-DBS transform filenames describe image-resampling direction. For point
transforms, the file named `from-MNI...to-anchorNative` maps anchor-native RAS
points to MNI RAS points. The legacy-contact compatibility contract therefore
uses that `PointExact` field as the authoritative point map:

```text
anchor-native point -> legacy-compatible MNI point
```

The file named `from-anchorNative...to-MNI` is generated as the numerical
inverse point map:

```text
legacy-compatible MNI point -> anchor-native point
```

The solver starts from the ordinary composed forward field and applies
chunked Newton updates against the authoritative `PointExact` displacement
field. If Newton does not converge at a candidate grid point, the solver
restarts that point from the same initial estimate and applies a damped
fixed-point iteration against the authoritative field. This second solver
closes isolated Newton overshoot holes without installing values from the
ordinary field. The ordinary field is only an initial estimate. Voxels whose
initial estimate lies outside the authoritative field domain, or for which
neither numerical solver finds a preimage, remain identity because the
authoritative inverse is undefined there; no ordinary-field fallback is
written into the final companion field.

The output NIfTI stores displacement components in RAS order and uses NIfTI
intent code 1006 (`displacement vector`). This is required because a raw
SimpleITK vector NIfTI stores the x/y components with ITK's LPS convention;
using those components as RAS would create an apparent left-right mirror.

Acceptance requires all of the following:

- the authoritative field reproduces all legacy contacts with maximum grid
  error at or below `1e-6` mm;
- the derived field maps the legacy contacts back to anchor-native contacts;
- the pair passes round-trip limits of median `0.05` mm, 95th percentile
  `0.2` mm, and maximum `0.5` mm on the validated spatial support;
- in-process RAS sampling and `antsApplyTransformsToPoints` agree for both
  fields;
- numerical inversion reports no unconverged point inside the validated
  support.
