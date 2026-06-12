# EasyReg normalization

Lead-DBS wraps FreeSurfer EasyReg to create ANTs-compatible deformation
fields for normalization. EasyReg's `--fwd_field` output is sampled on the
reference image grid and maps reference coordinates to floating coordinates.
Its `--bak_field` output is sampled on the floating image grid and maps
floating coordinates to reference coordinates.

Both fields should be requested directly from EasyReg and converted to ITK H5
before conversion to ANTs `.nii.gz` warps. The backward field must not be
created by numerically inverting the forward displacement field in Slicer,
because Slicer's iterative inverse can fail to converge for valid nonlinear
fields and may terminate the normalization workflow.

When converting an EasyReg field to ITK H5, the ITK grid metadata must come
from the NIfTI header of the field being converted. This keeps the forward warp
on the template grid and the inverse warp on the subject-native grid.
