# DICOM Series To NIfTI Conversion

This helper converts a single-folder DICOM series into a NIfTI image when the
DICOM files are missing reliable per-slice geometry fields such as
`InstanceNumber`, `SliceLocation`, `SliceThickness`, or
`SpacingBetweenSlices`.

The script is intended for simple single-frame CT/MR image series where the
file names encode the slice order. It does not modify the source DICOM files.

## Requirements

Run the script from the `LFP` Conda environment:

```bash
conda run -n LFP python /Users/mojackhu/Github/leaddbs/my_helper/convert_dicom_series_to_nifti.py --help
```

The environment must provide:

- `pydicom`
- `nibabel`
- `numpy`

## Default Behavior

By default, the script:

- reads `*.dcm` files from the input folder;
- sorts files by numeric file stem, for example `00.dcm`, `01.dcm`, ...;
- validates that all files belong to one series and share image geometry;
- uses the DICOM in-plane pixel spacing;
- uses a synthetic slice thickness of `0.625 mm`;
- stacks slices in the `+Z` direction;
- writes a compressed `.nii.gz` image;
- writes a JSON conversion record next to the NIfTI file.

If the requested output directory already exists and is not empty, the script
creates a timestamped sibling directory instead of overwriting existing files.

## Example

```bash
conda run -n LFP python /Users/mojackhu/Github/leaddbs/my_helper/convert_dicom_series_to_nifti.py \
  /Users/mojackhu/Desktop/2026.6.13/115068/头/115068_20260613 \
  --output-dir /Users/mojackhu/Desktop/2026.6.13/115068/头/115068_20260613_nifti \
  --output-name 115068_20260613_head
```

Expected outputs:

- `115068_20260613_head.nii.gz`
- `115068_20260613_head_conversion.json`

## Important Geometry Assumption

This helper should only be used when the missing DICOM geometry has been
reviewed and the intended slice spacing and slice direction are known. For the
example dataset above, the selected assumptions are:

- slice thickness: `0.625 mm`
- slice direction: `+Z`
- slice order: numeric file name order

To override these values:

```bash
conda run -n LFP python /Users/mojackhu/Github/leaddbs/my_helper/convert_dicom_series_to_nifti.py \
  /path/to/dicom_folder \
  --slice-thickness 0.625 \
  --slice-direction +z
```

Use `--slice-direction -z` if the numeric file order runs in the opposite
patient-space Z direction.

## Validation

After conversion, verify the output with:

```bash
conda run -n LFP python - <<'PY'
import nibabel as nib

nii = nib.load('/path/to/output.nii.gz')
print('shape:', nii.shape)
print('zooms:', nii.header.get_zooms()[:3])
print('affine:')
print(nii.affine)
PY
```

For the example dataset, the expected shape is `512 x 512 x 169`, and the voxel
size should be approximately `0.357422 x 0.357422 x 0.625 mm`.
