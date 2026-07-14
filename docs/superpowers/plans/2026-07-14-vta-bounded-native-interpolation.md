# VTA Bounded Native Interpolation Implementation Plan

## Status

```text
design_aligned
implementation_not_started
real_fem_not_required_for_this_slice
current_outputs_unchanged
```

## Goal

Avoid native-anchor interpolation queries that are provably outside the finite
FEM sample support while preserving the full canonical NIfTI grid and exact
derived output values.

This is slice 3 of the approved VTA performance optimization design. It does
not change FEM samples, interpolation method, extrapolation behavior, output
dimensions, affine, datatype, description, paths, or CLI behavior.

## Current Gap

`mh_vta_export_common_grid` allocates the required full-size single-precision
array and queries `scatteredInterpolant` for every anchor voxel. Voxels outside
the physical axis-aligned bounding box of all finite FEM samples cannot lie
inside their convex hull and therefore must remain `NaN`; querying them adds
point-location work without changing the result.

## Implementation Contract

After current finite-sample validation, the exporter must:

1. construct the physical min/max bounding box of finite FEM sample points in
   millimeters;
2. enumerate all eight physical corners of that box;
3. convert all corners with Lead-DBS one-based
   `ea_mm2vox(corners_mm, anchor.mat)` semantics;
4. derive a voxel-axis bounding box by expanding the transformed extrema by
   one voxel, then applying `floor` to lower bounds and `ceil` to upper bounds;
5. intersect that integer box with `[1, anchor.dim(1:3)]` without clamping an
   entirely external box onto an image boundary;
6. retain the full anchor-sized `single` array initialized to `NaN`;
7. query the existing linear/no-extrapolation `scatteredInterpolant` only for
   voxels in a nonempty intersection; and
8. leave the complete output array as `NaN` when any intersected axis is empty.

All eight physical corners are mandatory. Transforming only physical min/max
endpoints is invalid for rotated, sheared, reflected, or negative-determinant
affines.

The bounded voxel set must still be processed in chunks of at most 250,000
linear box indices. The implementation must not allocate all full-grid query
coordinates at once and must not crop the written NIfTI.

## Numerical Contract

The reference is the pre-optimization full-grid algorithm using the same
finite points, values, anchor affine, and `scatteredInterpolant` options.

For every synthetic fixture:

- dimensions and affine are unchanged;
- finite masks are exactly equal;
- every finite voxel value is exactly equal after the existing single cast;
- every voxel outside the reference finite mask remains `NaN`; and
- NIfTI datatype, scaling metadata, and description are unchanged.

This is a derived-only optimization and requires exact equality. It does not
use the looser FEM numerical tolerance.

## Tests

Extend the focused common-grid tests with a local full-grid reference covering:

- identity affine;
- translated affine;
- rotated affine;
- sheared affine;
- reflected affine;
- negative-determinant affine;
- support touching an image boundary;
- support fully internal to the image;
- support partially outside the image;
- support fully outside the image, producing a full-size all-`NaN` result;
- nonfinite sample exclusion; and
- fewer than four finite samples retaining the established error.

At least one fixture must use a large anchor with a small internal FEM support
to prove that the bounded query count is smaller than the full voxel count.
This may use an optional test-only query observer that does not alter the
public production API or written artifacts.

Run the complete solver-free MATLAB fiber suite, MATLAB Code Analyzer on all
touched files, and the Python VTA pipeline/benchmark suite. No real FEM run is
required for this slice.

## Acceptance

This slice is complete only when:

- only the intersected bounded voxel set is queried;
- all reference arrays and metadata match exactly;
- all affine and out-of-image cases pass;
- full-grid dimensions and affine remain unchanged;
- all focused and regression tests pass; and
- roadmap/design status is updated without claiming a whole-pipeline speedup.

