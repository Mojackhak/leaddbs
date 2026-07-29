# SNr017 and SNr022 DWI Mosaic Correction Plan

## Purpose

Correct the Siemens SaveBySlc mosaic reconstruction used for SNr017 and
SNr022, then regenerate all DWI-derived outputs from the corrected raw DWI.
The implementation must remain subject-agnostic: subject identifiers and
source paths belong in configuration or job input, not in core functions.

This workflow does not modify the anatomical normalization. It invalidates
the old raw DWI import and every derivative that depends on the DWI grid or
diffusion directions.

## Confirmed source interpretation

The source is a 9 x 9 mosaic. Each tile is 108 x 105 voxels, 78 tiles contain
real slices, and three tiles are padding. Direct comparison of DICOM pixels
with the dcm2niix mosaic NIfTI established the following traversal for the
dcm2niix array:

1. traverse mosaic rows from bottom to top;
2. traverse columns from left to right within each row;
3. retain the 78 real tiles and exclude the three padding tiles;
4. preserve the resulting inferior-to-superior slice order.

The corrected 3D volume then requires a 180-degree in-plane rotation about
the slice axis. The same `rotZ180` signed-axis transform must be applied to the
source b-vectors and any signed phase-encoding direction before diffusion
preprocessing:

```text
image: flip voxel dimensions 1 and 2
bvec:  diag([-1, -1, 1]) * source_bvec
PE:    j becomes j-; j- becomes j
```

No slice-axis reversal is part of the corrected reconstruction.

## Difference from the previous reconstruction

The previous formal reconstruction used a top-to-bottom, right-to-left tile
traversal followed by an incremental `rotX180 -> flipY` correction. The net
b-vector transform of that chain was `flipZ`. Relative to the confirmed
source interpretation, the previous reconstruction:

- omitted three true inferior slices;
- appended three zero-valued superior slices;
- paired the image content with a diffusion-direction convention that did not
  match the corrected in-plane orientation;
- applied the orientation correction after eddy without regenerating
  Synb0/topup/eddy outputs.

The new workflow starts from the original mosaic and original b-vectors. It
must not reuse the previous post-processing correction chain.

## Configuration contract

The reusable source-preparation configuration is:

```yaml
mosaic:
  tile_order: bottom_to_top_left_to_right
  slice_count: 78
  skip_padding_tiles: true

orientation:
  image_content_transform: rotZ180
  bvec_transform: rotZ180
  apply_before_preprocessing: true

b0_reference:
  strategy: last
  apply_to_synb0: true
  apply_to_eddy_reference: true
  apply_to_formal_b0: true
```

The low-level MATLAB API keeps existing tile-order values for backward
compatibility and adds `bottom_to_top_left_to_right`. Padding exclusion is an
explicit option. If enabled, tile selection must be derived from the tile
content across all DWI volumes and must produce exactly `slice_count`
non-padding tiles. Ambiguous or inconsistent padding detection is an error.

Image and b-vector transforms are configured separately so their provenance
is explicit, but DWI preparation requires them to be identical. A mismatch is
an error. `apply_before_preprocessing` must be `true` for this workflow.

When the source JSON contains a signed BIDS `PhaseEncodingDirection`, the
same-grid content transform must update it in lockstep with the image. When
only `PhaseEncodingAxis` is available, the sign remains unresolved and the
preprocessing configuration must supply and validate it explicitly.

The corrected SNr017 and SNr022 series each contain two b0 volumes at
one-based volume indices 1 and 2. Manual review identified substantial motion
in the first b0 relative to the subsequent acquisition. The last b0 volume,
volume 2 for both subjects, is therefore the explicit reference. The raw b0
volumes must not be averaged before motion correction. The selected reference
must be recorded by source volume index and content hash and must be used for
the Synb0 input, the eddy reference ordering, and the formal corrected b0 used
for anatomical coregistration.

SNr020 and SNr026 also contain two b0 volumes at one-based indices 1 and 2,
and their completed two-volume QC confirms measurable motion between the b0
volumes. They are therefore included with SNr017 and SNr022 in the formal
last-b0-reference preprocessing scope. The mosaic and orientation repair
remains specific to SNr017 and SNr022; SNr020 and SNr026 enter preprocessing
from their existing approved raw DWI series.

The implementation must remain subject-agnostic. `strategy: last` selects the
last volume satisfying the configured b0 threshold and fails if no b0 exists.
It must not assume that the last b0 is volume 2 for other datasets.

## Implementation sequence

### 1. Generic mosaic and orientation support

- Add bottom-to-top, left-to-right tile traversal to the mosaic reconstructor,
  converter, and batch wrappers.
- Add explicit padding-tile exclusion and record selected and excluded tile
  coordinates in JSON QC metadata.
- Add `rotZ180` to same-grid NIfTI content transforms, b-vector transforms,
  correction composition, and provenance.
- Transform signed BIDS phase-encoding metadata with the same incremental
  content transform and mark missing signs as unresolved.
- Preserve all existing behavior for existing option values.

### 2. Automated validation

Use synthetic 9 x 9 mosaics with 78 labelled tiles and three padding tiles to
verify:

- exact inferior-to-superior output order;
- exclusion of the three padding tiles;
- no missing or duplicated real slice;
- failure when the number of detected real tiles differs from 78;
- `rotZ180` image and b-vector synchronization;
- `rotZ180` conversion of `PhaseEncodingDirection: j` to `j-`;
- unchanged volume, b-value, and b-vector counts;
- unchanged NIfTI affine during same-grid content rotation.

A real-data regression check must compare the staged corrected data with the
previous formal import and confirm the already observed 3-slice offset without
using patient identifiers in core code.

### 3. Staged raw-data preparation

Generate corrected four-file DWI sets for SNr017 and SNr022 in a new staging
directory. Do not overwrite formal BIDS rawdata at this stage. Record source
and output SHA-256 hashes, geometry, tile coordinates, transform matrices, and
gradient counts.

Pause for manual review of:

- inferior-to-superior slice order;
- axial orientation after `rotZ180`;
- b0 anatomy and absence of padding slices;
- the proposed phase-encoding direction for each subject.

### 4. Full DWI preprocessing

After raw-data approval, rerun the complete chain from the corrected DWI:

1. denoising and Gibbs-ringing correction;
2. Synb0-DISCO;
3. topup and eddy;
4. rotated-b-vector validation and `dwigradcheck`;
5. corrected b0 generation.

Before Synb0, generate separate QC for every b0 volume and select the final b0
in acquisition order as the reference for SNr017, SNr020, SNr022, and SNr026.
For all four subjects, reorder the selected reference to the first eddy input
position while preserving a reversible source-to-eddy volume mapping and
reordering b-values and b-vectors in lockstep. Retain the displaced first b0
unless post-eddy QC demonstrates intra-volume corruption, signal dropout, or
failure to align to the selected reference. Any later exclusion is a separate
reviewed decision and must regenerate all dependent artifacts.

After eddy, restore the corrected DWI volumes and rotated b-vectors to source
acquisition order before writing the formal staged outputs. The formal b-values
therefore retain their source order. Generate the formal corrected b0 from the
restored volume corresponding to the selected source reference, rather than
averaging the corrected b0 volumes.

The b0 motion-QC package must contain, for each of the four subjects:

- separate axial montages for every raw b0;
- a rigid first-b0-to-reference transform and registered overlay;
- a difference image and quantitative similarity metrics;
- the selected reference index and hash;
- post-eddy b0 comparison when preprocessing is authorized.

The formal preprocessing scope now includes all four subjects. Every subject
must complete the pre-eddy QC package, reference-first volume reordering,
Synb0/topup/eddy, post-eddy b0 comparison, gradient validation, and staging
validation before any formal publication is considered.

The previous Synb0/topup/eddy products are not reusable. The phase-encoding
checks remain mandatory: validate whether the SNr017 AP series is a genuine
reverse-PE reference, compare isolated positive/negative phase-encoding
assumptions where the sign is unresolved, and validate the effective signed
phase-encoding direction for every subject before formal publication.

Positive and negative phase-encoding comparison runs for the same subject must
use distinct project staging roots and distinct external Synb0 work roots.
Subject-level cache paths must never be shared across the comparison variants,
because the acquisition-parameter identity differs even when the DWI and T1w
inputs are otherwise identical.

The SNr017 DICOM metadata confirms that the original main DWI is `j` and the
independent AP reference is `j-`. After `rotZ180`, these become `j-` and `j`,
respectively, and remain a valid reverse-PE pair. SNr022 reports only
`PhaseEncodingAxis: j`; its sign cannot be recovered from that field alone and
must remain behind the phase-encoding review gate.

### 5. Coregistration candidates and manual gate

Before generating coregistration candidates, complete a separate post-eddy QC
stage in the isolated reprocessing root. This stage must:

- compare the two corrected b0 volumes after restoring source acquisition
  order, using the final corrected b0 as the fixed reference;
- report rigid residual translation, rotation, correlation, normalized error,
  and mutual information without modifying the corrected DWI;
- run `dwigradcheck` against the corrected DWI, formal b-values, rotated
  b-vectors, and generated brain mask, and save the suggested gradient table
  and complete command log as QC artifacts;
- compare the isolated SNr022 positive- and negative-j outputs on their common
  grid, including corrected-DWI difference, selected corrected-b0 difference,
  similarity to the corresponding Synb0 undistorted b0, and visual montages;
- preserve both SNr022 candidates until the phase-encoding direction is
  selected by manual review.

The post-eddy QC stage is read-only with respect to preprocessing outputs. Its
artifacts are written under `post_eddy_qc/` in the versioned staging root.

Generate independent anchorNative-to-corrected-b0 candidates with:

- SPM44;
- BRAINSFit44.

The isolated candidate generator must receive an explicit machine-readable
configuration containing the corrected b0 path, unchanged anchorNative T1
path, subject/candidate label, and staging output directory. It must never
discover or write the formal subject `coregistration/` directory. For each
method it preserves the native method transform, exports forward and inverse
world-coordinate `tmat` 4-by-4 matrices, resamples b0 onto anchorNative and
anchorNative onto b0, and records input and artifact hashes. Registration
montages are generated from these staged images for manual review. Review-only
resampling from a 4-by-4 `tmat` must combine that world transform with both
NIfTI voxel-to-world affines; it must not apply the matrix directly to voxel
indices.

Stop after generating their QC material. Do not choose a transform
automatically and do not start tractography until the user selects the
registration method for each subject.

### 6. Downstream regeneration

After registration selection, regenerate the DWI-space ROIs, masks, response,
FOD, seed-wide tractograms, and target-specific tractograms. The existing
MNI-to-anchorNative normalization may be reused only when its input and output
hashes are unchanged.

## Publication and preservation rules

- All computation is written to staging first.
- Formal files are replaced only after the staged raw DWI, preprocessing, and
  registration outputs pass validation.
- Existing untracked formal outputs are moved to the external-volume Trash;
  they are never permanently deleted or overwritten in place.
- A publication failure must leave the previous formal dataset intact.
- The run record must identify every reused, regenerated, staged, published,
  and trashed artifact.

## Stop conditions

The workflow must stop rather than publish when any of the following occurs:

- padding detection does not resolve exactly 78 real tiles;
- image and b-vector transforms differ;
- b-value, b-vector, or DWI volume counts differ;
- a reconstructed slice is empty unexpectedly;
- phase-encoding validation is unresolved;
- Synb0/topup/eddy or gradient QC fails;
- either SPM44 or BRAINSFit44 candidate is missing;
- the user has not selected the registration candidate.
