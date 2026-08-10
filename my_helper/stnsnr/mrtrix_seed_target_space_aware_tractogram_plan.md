# MRtrix Seed-Target Space-Aware Tractogram Publication Plan

## Status and authority

This document defines the closed implementation contract and staged acceptance
plan for adding target-space tractogram publication to the existing
YAML-driven `mrtrix-seed-target` pipeline.

Status:

```text
coordinate_contract_closed
transform_direction_independently_verified
visualization_contract_closed
round_trip_tolerance_closed
implementation_complete
data_migration_completed
gate_e_passed
gate_f_passed
gate_g_pilot_artifacts_passed
gate_h_passed
anatomical_acceptance_contract_closed
paired_field_inverse_domain_resolution_approved
```

The implementation must remain part of the existing Python YAML CLI. MATLAB
continues to prepare atlas ROIs in patient space, MRtrix continues to generate
tractography in native DWI space, and Python publishes both native and
target-space TCK artifacts.

The authoritative runtime configuration is:

```text
/Volumes/VAL/STNSNr/config/spot/mrtrix_seed_target.yaml
```

The target-space name is read only from:

```yaml
atlas:
  space: <target_space>
```

The current configured value is `MNI152NLin2009bAsym`, but that value must not
be hard-coded in runtime path construction, transform discovery, state
records, or tests. The parsed source of truth is `config.atlas.space`.

## Review decisions and closure status

An independent review of this plan against the live repository and the real
`/Volumes/VAL/STNSNr` data produced the following decisions. Decisions marked
`approved` override any earlier wording in this document. The cross-method and
replacement-field canaries in Gate F have passed, so Decision D is closed.

| ID | Question | Decision | Status |
| --- | --- | --- | --- |
| A | Accepted `normalization` approval values | `{1, 0.5}`; the raw value is recorded in provenance and `0.5` is reported as a warning | approved |
| B | Configuration hashing | Remove `configuration_hash` only as a gate; per-artifact `sha256` and `source_roi_hashes` are retained unchanged | approved |
| C | `path_overrides` key rename | Rename directly; the key set is unused in the authoritative YAML, so no alias or compatibility layer is added | approved |
| D | Gate F round-trip tolerance | Retain the limits `median <= 0.05 mm`, `p95 <= 0.2 mm`, and `max <= 0.5 mm`. The former `ordinary_forward_point_exact_inverse` active pairs for `sub-SNr029` and `sub-SNr030` were replaced by pairs derived from one authoritative `PointExact` field: retain the `PointExact` anchor-native-to-legacy-MNI point map and generate the opposite direction only by numerical inversion. Both replacement pairs pass contact, ANTs-parity, brain-mask, and actual-tractography acceptance. | approved |
| E | Bulk point-transform backend | Use one in-process Nibabel backend in RAS world millimetres; use `antsApplyTransformsToPoints` only as an independent LPS reference | approved |
| F | Visualization colors | Read the colormap name and seed-wireframe color from the authoritative YAML; generate target colors deterministically from the current region count, with no target-specific color table in code | approved |
| G | Gate F anatomical dilation | Remove the former numerical MNI-mask hit threshold as a pass/fail gate because it is not resolution invariant. Retain the MNI seed and target masks, optional descriptive intersection fractions, independent ANTs point parity, exact count/order/membership preservation, and visual overlay. Native classification occurs on anisotropic DWI voxels, whereas the current atlas uses 0.5 mm isotropic voxels | approved |
| H | Production points outside the primary point-field grid | Preserve every native streamline and solve only those anchorNative points by numerically inverting the paired target-to-anchor point field. A clipped primary-field sample may initialize the solver but is never accepted as the output. Every resolved point must remain inside the paired field and converge to residual `<= 1e-5 mm`; otherwise publication stops. Identity mapping, boundary extrapolation, point deletion, streamline truncation, and native retracking are not permitted as domain repairs. | approved |

## Scope

The implementation will:

1. migrate the current published native TCK files into a `native` subdirectory;
2. change future native publication to use the new directory contract;
3. discover the direct approved native-DWI-to-anchor transform and the paired
   target-space normalization deformations, with image and point directions
   represented separately;
4. transform the existing native seed-wide tractograms into the configured
   target space;
5. reconstruct target-specific target-space TCK files without changing target
   membership;
6. generate one interactive target-space tractography scene per configured
   subject and side, with target-colored fibers, target surfaces, the seed
   wireframe, a saved MATLAB FIG, and fixed-view PNG/PDF exports;
7. integrate native reuse, target-space resume, visualization-only resume,
   validation, status, and cache
   cleanup into the existing CLI.

The implementation will not:

- rerun tractography merely because the publication directory changes;
- resample DWI data or FODs into target space;
- run individualized scoring, exposure sampling, jitter, statistics, or model
  publication;
- infer the target-space name from a transform filename;
- place display or color configuration in a separate visualization YAML;
- add a versioned directory, compatibility layer, or migration framework;
- commit or push changes without separate authorization.

The new public visualization values are part of the existing authoritative
tracking configuration, not a second configuration file:

```yaml
visualization:
  target_fiber_display_budget: 3000
  target_colormap: hsv
  seed_wireframe_color: "#D9D9D9"
```

For each subject-side scene, `3000` is the total number of rendered
target-membership instances. It is not a tractography-generation count and it
does not change any native or target-space TCK. Because target membership is
nonexclusive, the realized number of unique physical streamlines may be lower
than `3000`. The color fields affect display only.

## Confirmed current inventory

The current YAML declares:

```text
16 subjects
2 side-specific STNSNrplus seeds per subject
17 targets per side
1 seed-wide TCK plus 17 target TCKs per side
576 authoritative TCK files in total
```

The 576 currently configured source TCK files exist and occupy approximately
41.23 GiB. The seed-wide files account for approximately 12.16 GiB.

Historical state records still contain 18 targets per side, including
`preSMA`. The current YAML no longer declares `preSMA`. The migration therefore
treats the current YAML as authoritative, moves the historical `preSMA` files
to Trash with an audit record, and does not generate target-space `preSMA`
artifacts.

## Directory contract

For a parsed `target_space = config.atlas.space`, the only managed public
tractogram roots are:

```text
connectomics/dMRI/mrtrix_seed_target/tractograms/
├── native/
│   ├── lh/STNSNrplus/
│   │   ├── seedwide.tck
│   │   └── targets/lh/<target>.tck
│   └── rh/STNSNrplus/
│       ├── seedwide.tck
│       └── targets/rh/<target>.tck
└── <target_space>/
    ├── lh/STNSNrplus/
    │   ├── seedwide.tck
    │   └── targets/lh/<target>.tck
    └── rh/STNSNrplus/
        ├── seedwide.tck
        └── targets/rh/<target>.tck
```

For the current YAML, `<target_space>` resolves to
`MNI152NLin2009bAsym`. A different valid `atlas.space` value must produce a
directory with that exact name without requiring a code change.

Visualization products are stored beside, not inside, the authoritative
tractogram trees:

```text
connectomics/dMRI/mrtrix_seed_target/visualization/
└── <target_space>/
    ├── lh/STNSNrplus/
    │   ├── inputs/
    │   │   ├── display_geometry.mat
    │   │   └── display_membership.csv
    │   ├── figures/
    │   │   ├── <subject>_lh_STNSNrplus_target_fibers.fig
    │   │   ├── <subject>_lh_STNSNrplus_target_fibers_view01.png
    │   │   └── <subject>_lh_STNSNrplus_target_fibers_view01.pdf
    │   ├── sampling_manifest.json
    │   ├── scene_manifest.json
    │   └── complete.json
    └── rh/STNSNrplus/
        └── <same contract for the right side>
```

There are exactly `16 subjects x 2 sides = 32` final scenes for the current
configuration. The directory name still comes from `config.atlas.space`; the
literal current MNI space must not be hard-coded into output paths.

The configuration parser must validate `atlas.space` once at the YAML trust
boundary as a safe single path component. Empty values, `.`, `..`, path
separators, and absolute paths are invalid. Downstream code consumes the
validated string without repeating this validation.

## Coordinate contract

Published MRtrix TCK points are RAS+ world coordinates in millimetres on the
patient's native DWI/B0 physical space.

Image-resampling transform names and point-transform directions are opposite
for the paired ITK/ANTs displacement fields used here. The implementation must
therefore distinguish the filename's image direction from the runtime point
direction. It must not select a displacement field solely because its filename
appears to match the desired point direction.

The production chain is evaluated entirely in RAS world millimetres. For each
point:

\[
p_{\mathrm{anchor,RAS}}
=
T_{\mathrm{b0\to anchor}}\,p_{\mathrm{DWI,RAS}}
\]

\[
p_{\mathrm{field\ voxel}}
=
A_{\mathrm{field,RAS}}^{-1}
\begin{bmatrix}p_{\mathrm{anchor,RAS}}\\1\end{bmatrix}
\]

\[
u_{\mathrm{RAS}}
=
\operatorname{trilinear}
\left(D_{\mathrm{NIfTI}},p_{\mathrm{field\ voxel}}\right)
\]

\[
p_{\mathrm{target,RAS}}
=
p_{\mathrm{anchor,RAS}}+u_{\mathrm{RAS}}
\]

Here `A_field,RAS` is the full NIfTI affine of the anchor-grid production
field and `D_NIfTI` is its vector payload as returned by Nibabel. The full
affine, including any rotation, shear, or axis permutation, is always used.
The implementation must not require `aff2axcodes(...) == ('R', 'A', 'S')`.

The production chain in operational terms is:

```text
native DWI/B0 point in RAS+
-> direct approved b0-to-anchorNative 44.mat tmat
-> anchorNative point in RAS+
-> inverse production-field NIfTI affine
-> continuous production-field voxel coordinate
-> trilinear sample of the stored RAS world-mm displacement
-> direct RAS vector addition
-> published target-space TCK point in RAS+
```

The external reference chain uses the same transforms but converts points from
RAS to LPS before `antsApplyTransformsToPoints`, applies the field with
`[field,0]`, and converts the returned LPS points back to RAS. With
`C = diag(-1,-1,1,1)`, this reference-only chain is:

\[
p_{\mathrm{anchor,LPS}}=C\,p_{\mathrm{anchor,RAS}},\qquad
p_{\mathrm{target,RAS}}
=C\,D^{\mathrm{point}}_{\mathrm{anchor\to target}}
\left(p_{\mathrm{anchor,LPS}}\right)
\]

RAS-to-LPS conversion belongs only to this external reference helper. It is
not part of the bulk production backend.

The first transform is selected from the approved B0 coregistration method in:

```text
coregistration/log/<subject>_desc-coregmethod.json
```

The implementation reads `method.B0` and requires `approval.B0`. It maps the
approved method through the existing method-token contract and selects the
direct matrix:

```text
coregistration/transformations/
<subject>_from-b0_to-anchorNative_desc-<method_token>44.mat
```

The implementation must not hard-code SPM and must not invert the
`anchorNative-to-b0` matrix at runtime. The exported `tmat` in the selected
direct `44.mat` maps moving B0 world millimetres directly to fixed
anchorNative world millimetres; no RAS/LPS conversion is inserted around this
linear step.

The production anchor-to-target **point** transform uses this image-resampling
deformation file:

```text
normalization/transformations/
<subject>_from-<target_space>_to-anchorNative_desc-ants.nii.gz
```

This file expresses target-to-anchor image resampling and is stored on the
anchorNative grid. With direct ANTs point semantics (`[field,0]`), it maps an
anchorNative LPS point to its target-space LPS point. The same file remains the
approved target-to-anchor image transform for native ROI preparation.

The paired deformation used for the reverse point leg of round-trip QC is:

```text
normalization/transformations/
<subject>_from-anchorNative_to-<target_space>_desc-ants.nii.gz
```

This file expresses anchor-to-target image resampling and is stored on the
target grid. With direct ANTs point semantics, it maps a target-space LPS point
back to anchorNative LPS. It must not be used as the production
anchor-to-target point transform.

The bulk production and reverse-QC point legs use the Nibabel RAS contract
above. The independent reference for both legs uses the direct field action
supported by `antsApplyTransformsToPoints --transform [<field>,0]`, with the
reference helper converting RAS points to LPS and the returned LPS points back
to RAS. The reverse point chain then applies the direct approved
`anchorNative-to-b0` `44.mat` tmat. Round-trip agreement verifies that the
paired fields are mutually consistent; it does not by itself establish their
direction. Direction is established from field-generation code, field grid
geometry, and the documented ANTs distinction between image and point
transforms. The upstream method is selected from the approved normalization
log; the `desc-ants.nii.gz` suffix identifies the exported ITK/ANTs
displacement format and must not be interpreted as proof that ANTs performed
the registration.

The direction contract is grounded in these implementation and format
authorities:

- `ea_spm_coreg.m` defines the exported forward `tmat` as moving-world-mm to
  fixed-world-mm and writes its explicit inverse separately;
- `ea_normalize_easyreg.m` assigns EasyReg forward and inverse outputs to the
  corresponding Lead-DBS image-transform filenames;
- `ext_libs/EasyReg/mri_easyreg` shows that the forward image field is sampled
  on the target/reference grid and stores source/floating coordinates, while
  the inverse image field is sampled on the source/floating grid and stores
  target/reference coordinates;
- the ANTs documentation on
  [forward and inverse warps for images and point sets](https://github.com/ANTsX/ANTs/wiki/Forward-and-inverse-warps-for-warping-images%2C-pointsets-and-Jacobians)
  documents the opposite image-resampling and point-set transform directions.

The current MATLAB display helper
`my_helper/fiber/core/tracking/mh_fiber_tck_to_display_ftr.m` is not the
authority for this conversion. Its current direct use of the
anchor-to-target image deformation for forward point mapping must not be
copied into the YAML pipeline.

The same defect exists at a second site. `connectomics/ea_normalize_fibers.m`
carries an uncommitted local modification that selects
`transformfiles.forward`, the anchor-to-target image deformation, with
`useinverse = 0` for native-to-target point mapping, together with a comment
asserting that this is correct. Both sites are wrong in the same way and
neither is authoritative for this plan. Whether to repair
`ea_normalize_fibers.m` is a separate decision outside this scope; it is
recorded here so the defect is not treated as a precedent.

### Displacement-field component storage convention

ITK flips the first two vector components when it writes an LPS displacement
field to NIfTI. Consequently, Nibabel exposes both the NIfTI affine and the raw
vector payload in RAS convention. The only production interpretation is
therefore:

```text
point convention: RAS world millimetres
voxel lookup: inverse of the full NIfTI affine
sampled vector convention: RAS world millimetres
point update: target_RAS = anchor_RAS + sampled_vector_RAS
```

The bulk implementation must not negate x or y, convert a production point to
LPS, or expose a selectable coordinate-convention backend. Converting both the
point and vector into LPS is mathematically equivalent, but it is not a second
authorized production path. RAS-to-LPS conversion is confined to the external
ANTs reference helper.

Each production and reverse-QC field is validated once when it is parsed. The
current contract requires:

```text
NIfTI intent code: 1006 (displacement vector)
vector layout: (X, Y, Z, 1, 3)
affine: finite and invertible
production field grid: expected anchorNative grid
reverse-QC field grid: expected configured target-space grid
```

Grid agreement means both the three spatial dimensions and the full affine
match the expected reference image; vector dimensions and intent are checked
separately. Validation occurs at this file-parsing trust boundary and is not
repeated inside point chunks.

All 16 current production fields satisfy the intent and vector-layout
contract. Their current voxel-axis codes happen to be RAS, but that observation
is not a runtime requirement because voxel-axis labels do not replace the full
affine calculation.

This failure mode is specifically dangerous because the z component is correct
under either reading, so the error appears only in x and y and presents as an
apparent left-right reflection rather than as an obvious failure. Measured on
the `sub-SNr017` probe point below:

```text
raw sampled vector              [  8.0296, -30.2542,  31.4817]
added as LPS (wrong)     RAS    [ -6.3441,   5.7801, -43.3824]   62.6 mm error
added directly in RAS           [  9.7150, -54.7284, -43.3824]   exact
antsApplyTransformsToPoints     [  9.7150, -54.7284, -43.3824]
```

The mandated comparison against the bundled `antsApplyTransformsToPoints`
detects this defect, but the contract is stated here so the defect is avoided
rather than merely caught.

### Direction generality across normalization methods

The direction argument is derived from EasyReg field generation, but the cohort
is not uniformly EasyReg. The configured subjects use approved EasyReg, ANTs,
and SynthMorph normalization. The contract generalizes because the production
field is always written on the anchorNative grid and the reverse-QC field is
always written on the target grid, independent of method. Measured:

```text
sub-SNr017  EasyReg      anchor grid 256x345x300  production field 256x345x300
sub-SNr018  ANTs         anchor grid 338x338x233  production field 338x338x233
sub-SNr007  SynthMorph   anchor grid 347x347x233  production field 347x347x233
sub-SNr015  EasyReg      anchor grid 221x272x233  production field 221x272x233
reverse-QC field on the target grid, 394x466x378, for all of the above
```

Implementation validation must assert this grid relationship per subject rather
than assume it, because it is the structural property that makes the direction
contract method-independent.

### Verified representative chain: `sub-SNr017`

The current approved B0 method for `sub-SNr017` is read from
`coregistration/log/sub-SNr017_desc-coregmethod.json` as approved SPM. The
direct linear input is:

```text
coregistration/transformations/
sub-SNr017_from-b0_to-anchorNative_desc-spm44.mat
```

Its direct `tmat` is:

```text
[[ 0.999973234054,  0.002593476140, -0.006848968193, -1.306492150846],
 [-0.002464209802,  0.999819906354,  0.018817237949,  0.566095074143],
 [ 0.006896534955, -0.018799863538,  0.999799513363,  1.252620003733],
 [ 0.000000000000,  0.000000000000,  0.000000000000,  1.000000000000]]
```

The direct reverse linear input is:

```text
coregistration/transformations/
sub-SNr017_from-anchorNative_to-b0_desc-spm44.mat
```

Its paired `anchorNative-to-b0` matrix is an inverse to a maximum absolute
matrix-product error of approximately `2.44e-14`.

The production nonlinear point field is:

```text
normalization/transformations/
sub-SNr017_from-MNI152NLin2009bAsym_to-anchorNative_desc-ants.nii.gz
```

It is defined on the anchorNative grid with shape `256 x 345 x 300` and
approximately `0.66 mm` sampling. The paired reverse-QC point field is the
anchor-to-MNI image deformation on the MNI grid with shape
`394 x 466 x 378` and `0.5 mm` sampling. All `179349` nonzero tracking-mask
voxel centres tested for this subject are inside its actual oblique voxel
domain. A real first TCK point followed this measured chain:

```text
DWI RAS:     [ 2.528601, -23.596975, -76.593170]
anchor RAS:  [ 1.685428, -24.474134, -74.864136]
target RAS:  [ 9.714990, -54.728400, -43.382400]
```

Applying the paired reverse point field and direct anchor-to-B0 matrix returned
the point with approximately `0.0165 mm` Euclidean error. Four deterministic
probe points produced nonlinear round-trip errors from approximately
`0.0035 mm` to `0.0184 mm`. These measurements are acceptance evidence for the
current files, not hard-coded runtime constants; implementation validation
must recompute them from the selected subject inputs.

The chain was subsequently reproduced independently against the bundled
`antsApplyTransformsToPoints` executable and against a complete real target
tractogram:

```text
external ANTs reference applied the production field with [field,0]
to the anchorNative LPS point
  reproduces the recorded target RAS point to 0.000 mm

reverse-QC field applied to an anchorNative point instead of a target point
  returns the input unchanged, because the point is outside the target-grid
  domain and ANTs silently identity-maps out-of-domain points

sub-SNr017 lh M1 target tractogram, 13,703 streamlines, 2,150,810 points
  production point-field domain inclusion: 2,150,810 / 2,150,810 inside
  anchor -> target -> anchor round trip on 200 deterministic real TCK points
    median 0.0040 mm, p95 0.0172 mm, max 0.0342 mm
  points silently identity-mapped by the production field: 0 / 200
```

The observation that ANTs silently returns out-of-domain points unchanged is
the reason the production point-field domain gate below is mandatory rather
than advisory. An out-of-domain point does not raise an error; it produces a
plausible coordinate that is simply wrong.

## Implementation order

### 1. Documentation before mutation

This plan and the related DWI technical documentation must describe the final
layout and coordinate contract before either the migration script or runtime
code is written.

### 2. One-time temporary layout migration

A temporary repository-external script will be created at:

```text
/private/tmp/migrate_mrtrix_seed_target_layout.py
```

The script will call the existing configuration loader and read
`config.atlas.space`. It will not implement a second YAML parser and will not
infer space from filenames.

The script defaults to a read-only dry run. Its apply mode performs, per
subject:

1. acquire the existing subject run lock and reject an active writer;
2. enumerate only the native artifacts declared by the current YAML;
3. verify the current TCK hashes and streamline counts against tool-owned state;
4. verify that the tracking settings, seed identities, current target
   identities, DWI preparation identity, and transform identities are
   semantically compatible with reuse;
5. reject any destination collision before moving a file;
6. move historical `preSMA` TCK files to Trash and record their prior hashes,
   before any rename, so their paths are still the ones recorded in state;
7. move `tractograms/lh` to `tractograms/native/lh` with a same-filesystem
   atomic rename;
8. move `tractograms/rh` to `tractograms/native/rh` with a same-filesystem
   atomic rename;
9. create the empty `tractograms/<target_space>` directory;
10. move the original untracked `work/state.json` to Trash before installing a
    migrated state file;
11. update artifact paths, add `coordinate_space: native`, retain the original
    scientific hashes, downgrade the subject `status` from `complete` to
    `native_complete`, and record the migration provenance;
12. write an atomic migration audit under the subject work directory.

Step 6 is deliberately ordered before the renames. The historical `preSMA`
files live inside the trees moved in steps 7 and 8, so trashing them first
avoids recomputing their paths and keeps the audit record aligned with the
paths stored in the pre-migration state.

Step 11 must downgrade `status`. Every current subject state already records
`status: "complete"`, which under the pre-existing contract meant only that
native publication finished. Under the new contract `complete` means native,
target-space, and visualization are all finished. Leaving the value untouched
would make `status` report a finished pipeline before any target-space or
visualization work exists.

The migration changes paths only. It must not change TCK bytes, mtimes,
streamline order, streamline counts, or scientific identities. The script must
be idempotent: a second apply run reports `already_migrated` and performs no
mutation.

If any subject fails migration validation, the script stops before modifying
that subject. A partially completed subject is not accepted. No old CLI command
may run during the controlled interval between layout migration and the
corresponding runtime-code update.

The temporary script remains available until migration acceptance is complete
and is then moved to Trash. It is not added to the repository.

### 3. Native publication path update

The native publication root changes from:

```text
tractograms/<side>/<seed>/...
```

to:

```text
tractograms/native/<side>/<seed>/...
```

The transactional publication code retains its ownership checks, staging,
rollback, hash verification, and Trash behavior. Native stale-path discovery
is scoped to `tractograms/native`; target-space TCK files must never be treated
as unknown native files.

On the VAL exFAT volume, macOS may create and concurrently remove `._*`
AppleDouble sidecars while a published staging tree is being retired. A
verified target-space publication must not be invalidated by failure to remove
that already-obsolete work directory. The implementation therefore moves the
owned transaction root to Trash after state promotion. If that cleanup alone
fails, it records the exact path and reason under `cleanup_pending` and leaves
the verified target-space artifacts and side completion valid for resume.

The state owner identifier and existing version identifiers are not changed.
The path-only migration does not invalidate tracking.

### 4. Target-space input discovery

The resolved subject input contract gains:

```text
b0_to_anchor_transform
anchor_to_b0_transform
target_to_anchor_image_deformation
anchor_to_target_image_deformation
target_space
```

These names preserve the files' image-resampling directions. Their point roles
are deliberately recorded separately:

```text
target_to_anchor_image_deformation
  -> anchor_to_target_point_field for production conversion

anchor_to_target_image_deformation
  -> target_to_anchor_point_field for reverse round-trip QC
```

The native ROI preparation path continues to use the
`target_to_anchor_image_deformation` as an image transform and the existing
approved anchor-to-DWI transform. Names in code must include either `image` or
`point` where direction could otherwise be ambiguous. Transform discovery uses
`config.atlas.space` for both deformation filenames. It also reads:

```text
normalization/log/<subject>_desc-normmethod.json
```

The selected normalization method must be approved. For example,
`sub-SNr017` currently uses approved EasyReg even though the paired exported
fields use the `desc-ants.nii.gz` format suffix.

#### Normalization approval semantics

Normalization approval is **not** shaped like coregistration approval and must
not reuse its accessor. Coregistration approval is a per-modality mapping read
as `approval.B0` and is binary in this cohort. Normalization approval is a
**scalar** `approval` field with three meaningful values.

Per decision A, the accepted set is `{1, 0.5}`:

```text
1     approved; all preoperative coregistrations were already approved
0.5   approved, but approved before all preoperative coregistrations were
      approved, or downgraded when a coregistration was approved afterwards
0     or missing: not approved, and rejected
```

`0.5` is written by `ea_checkreg.m` in two places. In both, the user did
approve the normalization; the value records approval **ordering**, not
registration quality. Its stated consequence is that Lead-DBS would redo the
normalization only when a **multispectral** method is used.

Accepting `0.5` is justified for this cohort by three verified facts:

- `ea_normalize_easyreg.m` and `ea_normalize_synthmorph.m` both declare
  `varargout{4} = 0; % is multispectral`, and both normalize using only
  `options.subj.coreg.anat.preop.(options.subj.AnchorModality)`. The anchor
  image needs no coregistration by definition, so the approval state of any
  secondary modality cannot influence the deformation field. Every affected
  subject uses one of these two non-multispectral methods.
- All four affected subjects now have every coregistration approved, so the
  condition that produced `0.5` no longer holds. There is no automatic path
  from `0.5` back to `1`, which is why the marker persists.
- `helpers/ea_reglocked.m` returns the raw scalar for normalization, so `0.5`
  is truthy and Lead-DBS's own approval gate already treats it as approved.

The affected subjects are:

```text
sub-SNr007   SynthMorph   approval 0.5
sub-SNr014   EasyReg      approval 0.5
sub-SNr029   EasyReg      approval 0.5   also a Gate F pilot subject
sub-SNr030   EasyReg      approval 0.5
```

The implementation records the raw approval value in provenance and emits a
warning for every subject whose normalization approval is not exactly `1`. A
rejection of `0.5` would exclude four of sixteen subjects, including a pilot
subject, on the basis of a marker that is structurally inapplicable to the
methods actually used.

#### Discovery interface changes

`discover_subject` currently accepts only a `SubjectSpec` and hard-codes the
literal current space when constructing the normalization deformation path. It
must instead receive the parsed `target_space`, and every caller must be
updated. The hard-coded space literal is removed.

The existing resolved-input field names are renamed so that direction is
unambiguous:

```text
mni_to_anchor_transform  ->  target_to_anchor_image_deformation
anchor_to_dwi_transform  ->  anchor_to_b0_transform
```

The same two names also appear as public `path_overrides` keys in the
configuration schema. Per decision C they are renamed directly with no alias
and no compatibility layer, because the authoritative YAML contains no
`path_overrides` block and the key set is therefore unused in production.

The schema currently constrains the space with
`"space": {"const": "MNI152NLin2009bAsym"}`. That constant is replaced by a
pattern that admits exactly one safe path component. Relaxing the constant is a
real loosening, so it is paired with the rule in section 6.3: a space other
than the currently accepted one requires an explicitly approved reference image
and view preset, and must not silently reuse the current backdrop or camera.

### 5. Target-space tractogram conversion

A focused module will own coordinate transformation, structural preservation,
and target-space staging. It should use a space-neutral name such as:

```text
my_helper/fiber/core/mrtrix_seed_target/tractogram_space.py
```

The conversion proceeds independently for each subject and side:

1. validate the native seed-wide TCK;
2. build an exact ordered streamline membership map between the seed-wide TCK
   and each configured target TCK;
3. reject unknown, duplicated, missing, or out-of-order membership;
4. stream seed-wide points in bounded chunks;
5. apply the direct B0-to-anchor 4x4 matrix;
6. load the configured target-to-anchor **image** deformation as the production
   anchor-to-target **point** field and validate its displacement intent,
   vector layout, affine, and anchorNative grid once;
7. map anchorNative RAS points to continuous field voxel coordinates with the
   inverse of the full NIfTI affine;
8. trilinearly sample the stored RAS world-mm displacement vectors and add them
   directly to the anchorNative RAS points;
9. compare deterministic samples against the independent
   `antsApplyTransformsToPoints` LPS reference;
10. write the transformed seed-wide streamlines and all target subsets without
   changing streamline or point ordering;
11. validate every staged TCK;
12. atomically publish the complete side only after all 18 files pass.

The target TCKs are expected to be strict ordered subsets of their same-side
seed-wide TCK. Preliminary validation for `sub-SNr015/lh` found all 17 current
targets to be ordered subsets with zero missing streamlines and no duplicate
seed-wide streamline digests. All 32 subject-side seed-wide sets must pass this
contract before production conversion.

The nonlinear transform is therefore applied once to each of the 32 seed-wide
TCK files rather than redundantly to all 576 files. The target-space output
still contains the complete 576-file authoritative set.

The measured scale of that work sets the implementation constraints. A single
seed-wide TCK holds `300,000` streamlines and about `44.2` million points in
roughly `534 MB`, so the 32 seed-wide files together carry on the order of
`9.6` million streamlines and `1.4` billion points. Bulk conversion must
therefore be an in-process vectorized point transform over bounded chunks. The
`antsApplyTransformsToPoints` executable is a CSV-based reference used only for
deterministic sample verification; it is not viable as the bulk production
path at this scale.

The installed SciPy build has a confirmed process-local concurrency failure in
the nonlinear point-field stage containing `scipy.ndimage.map_coordinates`.
Three complete subject-side conversions run serially produced zero domain
violations. Running the same three conversions through three Python threads
produced random false domain violations whose subject and count changed between
repetitions. Native TCK reads, the direct B0-to-anchor affine, the field-affine
voxel lookup, and fixed-batch interpolation each matched their serial hashes
independently. Serializing only each `map_coordinates` call passed once but
failed on repetition, so that narrower boundary is not sufficient.

The production module must therefore use one process-local lock around the
complete nonlinear point-field operation: field-voxel lookup, domain
accounting, trilinear displacement sampling, and displacement addition. Three
successive full three-subject concurrent repetitions under that boundary
produced zero domain violations and exact full-output hash agreement with all
three serial baselines. Native TCK reading, direct B0-to-anchor affine
conversion, target reconstruction, validation, and subject scheduling remain
concurrent. This is a required recovery for a reproduced failure, not a general
retry or speculative global serialization. The lock is part of the coordinate
implementation identity, so changing or removing it invalidates target-space
coordinate outputs but does not invalidate native tracking.

Streamline membership uses a deterministic digest of point count plus the
exact little-endian float32 point bytes. A duplicated digest is treated as an
ambiguous input and stops the side; there is no silent fallback.

The single bulk production point-field implementation must be independently
compared with the bundled `antsApplyTransformsToPoints` executable on
deterministic samples, using the same target-to-anchor image deformation with
direct point semantics. The production side remains all-RAS; only the external
reference helper performs RAS-to-LPS and LPS-to-RAS conversion. Only an
implementation that reproduces the reference transform within the acceptance
tolerance may be used for production conversion.

### 6. Target-space tractography visualization

#### 6.1 Configuration ownership

The display budget is read from the same authoritative configuration used for
tracking:

```text
/Volumes/VAL/STNSNr/config/spot/mrtrix_seed_target.yaml
```

The strict schema, immutable model, normalized semantic mapping, and focused
configuration tests must first be extended to accept exactly:

```yaml
visualization:
  target_fiber_display_budget: 3000
  target_colormap: hsv
  seed_wireframe_color: "#D9D9D9"
```

`target_fiber_display_budget` is a required positive integer once the
visualization stage is enabled. `target_colormap` is a required Matplotlib
colormap name and is resolved through `matplotlib.colormaps` at the Python
configuration boundary. `seed_wireframe_color` is a required six-digit RGB hex
string and is normalized to an RGB triplet at the same boundary. Invalid
colormap names and malformed colors stop configuration parsing. Downstream
rendering receives only the validated colormap and normalized color.
Matplotlib is already present in the `leaddbs` environment, so this contract
does not add `glasbey`, `colorcet`, or another palette dependency.

The current strict parser rejects unknown keys, so the external YAML must not
be edited before parser/schema support is installed and tested. Because that
YAML is external and untracked, its original must be moved to Trash before the
corrected file is installed. No separate visualization YAML is created.

The remaining appearance settings are fixed repository contracts. Target and
seed colors are configuration values because they are display choices; they do
not become scientific tracking inputs.

#### 6.2 Sampling with real nonexclusive membership

For one configured subject and side, let `n_k` be the number of streamlines in
the target-space TCK for target `k`, using only the 17 targets declared under
that side's seed in the current YAML. Since one seed-wide streamline may
belong to several targets, the denominator is the sum of target memberships,
not the seed-wide count:

\[
N = \sum_k n_k, \qquad p_k = \frac{n_k}{N}.
\]

For display budget `B = 3000`, the ideal target quota is:

\[
a_k = B p_k.
\]

Integer quotas use the largest-remainder method. Floor every `a_k`, then
assign remaining instances by descending fractional remainder; exact ties are
resolved by the target order in the authoritative YAML. The quotas must sum
to exactly `3000` when at least 3000 memberships are available. If fewer than
`B` memberships exist, all available memberships are rendered and the lower
realized total is recorded; no streamline is synthesized or duplicated to
fill the budget.

Within target `k`, select `q_k` rows deterministically and uniformly across the
ordered target TCK using midpoint-stratified ordinal indices. For zero-based
selection ordinal `j = 0, ..., q_k - 1`, the source row is:

\[
r_{k,j} = \left\lfloor
\frac{(j + 0.5)n_k}{q_k}
\right\rfloor.
\]

The selected streamline retains every original point. There is no point
decimation and no random sampling state.

Membership remains nonexclusive. A physical seed-wide streamline that belongs
to multiple targets remains eligible in every corresponding colored target
layer. Cross-target instances are not deduplicated, merged, assigned to one
exclusive target, or recolored as neutral. Consequently, `3000` means 3000
target-membership render instances, while the manifest separately reports the
number of unique physical streamlines and cross-target duplicate instances.
This sampling is display-only and never changes the complete target TCKs.

#### 6.3 Scene contents and style

Each of the 32 subject-side scenes contains exactly:

```text
17 target-specific fiber layers
17 matching target surface layers
1 configured STNSNrplus seed wireframe
```

The seed, targets, and fibers must all come from the same configured side and
`config.atlas.space`. Historical `preSMA` is not displayed. There is no
target-specific RGB table in Python or MATLAB. For the `N` targets declared for
the side, Python resolves `visualization.target_colormap` from
`matplotlib.colormaps` and samples it at:

\[
t_j=\frac{j}{N},\qquad j=0,\ldots,N-1
\]

The half-open interval `[0, 1)` prevents duplicate endpoints for a cyclic
colormap. The configured `hsv` colormap is recommended here because it spans
the complete hue circle and gives equal hue spacing for unordered categorical
regions. Sequential maps such as `viridis` or `turbo` remain valid selectable
configuration values, but they are not recommended for this scene because
adjacent samples intentionally look related.

The `N` sampled colors are assigned deterministically in authoritative YAML
target order. The same resolved mapping is reused across subjects and sides
whose ordered target-ID lists match. If the target count or ordered target list
changes, the complete mapping is regenerated and recorded; no historical color
is silently retained. Fibers, target surfaces, toolbar controls, legends, and
manifests all consume that one resolved mapping.

The display-input boundary requires an `N x 3` finite RGB array in `[0, 1]`
with `N` distinct rows. A configured colormap that cannot produce `N` distinct
sampled colors is rejected before MATLAB rendering. No fallback palette is
substituted.

Fiber appearance follows the normative fiber 3D scene contract:

```text
continuous target-colored lines
line width: 0.25
alpha: 1.0
no geometry reduction after streamline selection
```

Each target mask is rendered as a filled surface with its target's fiber color:

```text
FaceAlpha: 0.15
EdgeColor: none
```

The actual side-specific `STNSNrplus` mask declared by the YAML is rendered in
the normalized `visualization.seed_wireframe_color`, following the normative
atlas-wireframe style:

```text
FaceColor: none
EdgeAlpha: 0.15
surface reduction factor: 0.5
```

Target surfaces are drawn behind fibers and the seed wireframe remains visible
above the surfaces. The scene uses the normative black background, no RAS
triad, and the same configured-space anatomy backdrop used by the normative
fiber 3D renderer. For the currently approved space, the backdrop authority is
`mh_viz_default_fiber_scene_spec.m`, which resolves to:

```text
/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/backdrops/7T_100um_Edlow_2019.nii
```

The current display is specifically accepted for
`MNI152NLin2009bAsym`. Path construction remains dynamic, but a different
`atlas.space` must have an explicitly approved reference image and view preset;
the implementation must not silently reuse the current MNI backdrop or camera
for an unapproved space.

#### 6.4 Camera, controls, and exports

The initial FIG camera and static view use the existing normative helper
`mh_viz_default_fiber_views.m`, currently:

```text
azimuth: 0
elevation: 0
camera view angle: 3.8000
camera up vector: [0 0 1]
projection: orthographic
camera target: [9.8538 -48.8761 9.6955]
camera position: [1884.6 -48.8761 9.6955]
```

The implementation reuses the existing camera helper rather than copying
these numeric values into a second runtime definition.

The interactive navigation toolbar contains, with all layers initially on:

```text
one control per target fiber layer
one control per target surface layer
one seed-wireframe control
one global All fibers control
one global All targets control
```

Labels identify the target, side, and for fiber layers the displayed/available
count. Controls use the corresponding target color and must remain functional
after saving, closing, and reopening the FIG. Existing scene-control and
right-click bindings are reused.

Static PNG/PDF views include a compact two-column categorical legend in the
authoritative YAML target order. Target IDs are rendered literally with no TeX
or LaTeX interpretation, so underscores and other identifier characters remain
unchanged and readable. There is no continuous colorbar. The legend is
export-only so it does not replace or duplicate the interactive controls in the
saved FIG.

Every scene writes exactly:

```text
one interactive .fig
one view01.png at 600 dpi
one view01.pdf
```

SVG output is prohibited. The reusable generator remains repository-owned and
is not copied into every subject directory. Each scene manifest records the
generator paths and hashes so the exact code that created the FIG and static
views is recoverable.

#### 6.5 Headless MATLAB contract

Every MATLAB subprocess launched by this YAML pipeline is a silent background
operation. Both ROI preparation and scene rendering must be launched with
`-noFigureWindows`, `-nosplash`, and `-batch`. The scene generator must also
keep the root default figure visibility and every created or reopened figure
set to `off` for the complete render, verification, and export lifecycle. No
MATLAB desktop, splash screen, scene figure, control figure, or transient
export figure may be shown while the YAML CLI is running.

`-noFigureWindows` is the authoritative process-level guarantee. Setting only
MATLAB graphics objects to `Visible='off'` is insufficient because a helper may
briefly create a visible figure before the caller can hide it. The saved FIG
must remain interactive when a user explicitly opens it after generation; the
headless production requirement does not remove its controls.

#### 6.6 Render concurrency and memory

The five-subject pilot reproduced a render-dispatch failure that was not
visible during the single-subject canary. Four simultaneous MATLAB scene
exports reached a summed process-tree RSS of approximately `83.7 GB`, above the
configured `48 GB` execution budget. The operating system did not throttle and
the atomic scene outputs remained valid, but that scheduling is not accepted
for cohort execution.

The current implementation must admit at most one subject visualization stage
at a time within one CLI process. One process-local orchestration lock covers
both side-specific scenes for that subject. Target-space conversion for other
subjects may continue while the renderer is active, and already complete scenes
remain cache hits. This scheduling lock does not enter sampling, color, style,
camera, or artifact fingerprints because it cannot change scene content. No
new YAML resource estimate is introduced: the measured failure is closed by
the smallest sufficient concurrency boundary under the current configuration.

### 7. Pipeline, resume, status, and cleanup integration

The public CLI remains:

```text
validate
run
status
```

The normal `run` command implements these subject-level paths:

```text
valid existing native artifacts
→ skip preparation, MATLAB ROI work, FOD, and tckgen
→ generate or resume target-space artifacts
→ generate or resume visualization artifacts
```

```text
missing or invalid native artifacts
→ run the existing native preparation and tracking path
→ publish native artifacts
→ generate target-space artifacts
→ generate visualization artifacts
```

```text
native complete and target-space interrupted
→ preserve native artifacts
→ resume only target-space work
```

```text
native and target-space complete but visualization interrupted
→ preserve every TCK artifact
→ resume only visualization preparation or rendering
```

The native fast path must validate exact semantic compatibility and artifact
identity. It must not use the raw YAML byte hash as a rerun switch.

The native fast path must also not re-enter the transactional publication code.
Batch work caches were already cleaned on 2026-07-19, so `work/preparations`,
`work/seedwide`, and `work/staging` no longer exist and every
`published_artifacts[].source_path` points at a deleted staging file. Any call
into `publish_subject` for an already-published subject therefore fails its
staged-source hash verification. The fast path validates the **published**
artifacts in place — path, `sha256`, and streamline count — and never restages
them.

Subject state progresses through:

```text
native_complete
target_space_transforming
target_space_complete
visualization_preparing
visualization_rendering
complete
```

Target-space failure preserves the native publication and records the exact
failure reason. Visualization failure preserves both native and target-space
publications and records the exact visualization failure reason. Neither case
rolls back or retracks native results. Batch work cache cleanup remains blocked
until all subjects are `complete` in native space, configured target space,
and the 32-scene visualization set.

### Removal of the whole-configuration hash gate

Per decision B, `configuration_hash` is removed as a gate. It is currently a
single canonical hash over the entire resolved configuration mapping, and cache
cleanup rejects any subject whose recorded value differs from the current one.
Adding the `visualization` block changes that hash for every subject at once,
which would both block cache cleanup and contradict this plan's own rule that
the display budget must not invalidate any scientific stage.

The whole-configuration comparison in cache cleanup is deleted. It is replaced
by per-stage semantic fingerprints:

```text
native tracking fingerprint
target-space coordinate fingerprint
reverse-QC fingerprint
visualization sampling fingerprint
visualization styling and camera fingerprint
```

Each stage compares only its own fingerprint, so a change confined to one stage
cannot invalidate another. This is the mechanism that makes the incremental
invalidation table below implementable rather than aspirational.

The scene resume reader treats a missing `complete.json` as an ordinary cache
miss. This is the expected state on the first render and after display-input
preparation has completed but MATLAB has not yet produced a scene. It must not
dereference the absent document as a mapping; rendering proceeds from the
already verified sampling inputs.

Concurrent scene rendering must never ask `ea_load_nii` to decompress a shared
atlas `.nii.gz` beside its authoritative source. The five-subject pilot exposed
a real race in which two MATLAB processes used the same temporary `.nii`; one
process removed it while the other was reading it, producing `File too small`.
Each scene therefore copies compressed seed and target masks into its own
scene-local scratch directory before calling `ea_load_nii`. The scratch copy
and any uncompressed derivative are display-only work files and are removed
after rendering. This change invalidates only visualization generation.

Within `tractogram_space.py`, the coordinate and round-trip identities hash the
source of only the callables and constants actually consumed by that
scientific component. Transaction retirement, rollback bookkeeping, state
promotion, and AppleDouble cleanup are publication mechanics and are excluded
from the coordinate-byte fingerprint. A change limited to those mechanics may
resume or repair publication but must not regenerate an already verified TCK.

Decision B removes **only** this gate. Every other integrity hash is retained
unchanged:

```text
per-artifact sha256        retained  file identity and publication ownership
source_roi_hashes          retained  ROI content change detection
seedwide_identity          retained  tracking identity
stage code fingerprints    retained  resume and local invalidation
```

Per-artifact `sha256` is retained specifically because it is the only
implementation of publication ownership. It is what distinguishes a
tool-published file from an unrelated file occupying the same path, what makes
`reused` versus `replaced` decidable without rewriting 42 GB, and what supplies
the Gate C evidence that migration changed paths and not bytes. Verifying the
complete 576-file native set costs approximately 76 seconds at the measured
throughput of roughly 550 MB/s on the data volume.

## State and provenance contract

The state retains one `published_artifacts` list. Every artifact records:

```text
semantic_key
coordinate_space
path
sha256
streamline_count
```

Target-space artifacts additionally record:

```text
source_native_sha256
b0_to_anchor_transform_path
b0_to_anchor_transform_sha256
target_to_anchor_image_deformation_path
target_to_anchor_image_deformation_sha256
anchor_to_target_image_deformation_path
anchor_to_target_image_deformation_sha256
production_point_direction: anchor_to_target
bulk_point_backend: nibabel_trilinear_ras
bulk_input_point_convention: RAS_world_mm
field_voxel_lookup: inverse_nifti_affine
displacement_nifti_intent: 1006
displacement_vector_layout: X_Y_Z_1_3
displacement_storage_convention: RAS_world_mm
external_reference_backend: antsApplyTransformsToPoints
external_reference_point_convention: LPS_world_mm
space_conversion_code_hash
```

The configured space string, artifact `coordinate_space`, transform filename,
and public directory name must agree exactly. The production coordinate bytes
depend on the target-to-anchor image deformation. The paired
anchor-to-target image deformation is recorded because successful round-trip
QC is required for final target-space completion.

Each subject-side visualization records, without adding these display products
to the scientific TCK artifact list:

```text
target_fiber_display_budget
realized_membership_instance_count
unique_displayed_streamline_count
cross_target_duplicate_instance_count
target_colormap_name and equally spaced sample positions
ordered_target_ids
target_id and resolved RGB color
configured and normalized seed_wireframe_color
source_target_tck_path, sha256, and streamline_count
membership_count, membership_share, ideal_quota, and integer_quota
selected source-row ordinals and deterministic streamline digests
seed and target mask paths and sha256 values
target_space and reference-image identity
camera/view preset identity and exact realized camera state
fiber, target-surface, and seed-wireframe styles
FIG, PNG, and PDF paths and sha256 values
generator paths, code hashes, and MATLAB release
```

The repository-owned generator surface is expected to consist of one focused
Python display-input and colormap builder plus focused MATLAB scene and batch
export functions. MATLAB consumes the resolved RGB values from the display
input and contains no target-specific color table. It reuses
`mh_viz_default_fiber_views`,
`mh_fiber_add_toggle`, and the existing scene reopen/rebind helpers instead of
duplicating those contracts.

Output paths are publication metadata, not scientific identities. Moving an
unchanged native artifact from the old layout into `tractograms/native` does
not invalidate preparation, tracking, or target membership.

## Production point-field domain gate

Every displacement field has a finite voxel domain. The domain check must be
performed against the field that actually receives the production input
points: the target-to-anchor **image** deformation on the anchorNative grid,
used directly as the anchor-to-target **point** field. Domain inclusion must be
calculated in the field's full voxel geometry, including its affine and
obliquity; an axis-aligned world-coordinate bounding box is insufficient as
the acceptance test.

The earlier preliminary result claiming that `641/10000` points from
`sub-SNr017/lh` were outside the forward field is retracted. It tested
anchorNative input points against the target-grid domain of the wrong
deformation. It is not evidence that the deformation omits part of the brain.
Against the correct production point field, all `179349` tested nonzero
tracking-mask voxel centres for `sub-SNr017` are inside-domain.

Production conversion must still verify every actual TCK point, because mask
coverage is supporting evidence rather than a substitute for checking the
published source. Before writing final target-space files, each side records:

```text
total point count
inside-domain point count
outside-domain point count
outside-domain streamline count
maximum physical distance beyond the field domain
coordinate ranges of outside-domain points
paired-field inverse solved point count
paired-field inverse nonconverged point count
maximum paired-field inverse residual
unresolved point count
```

The authoritative full-cohort run identified one real finite-domain case in
`sub-SNr022`. Both sides crossed only the inferior edge of the primary
anchor-grid field:

```text
side   total points   primary outside   fraction      outside streamlines
lh      43,252,041          9,209        0.0213%              3,071
rh      44,246,890         10,929        0.0247%              3,563
```

These are valid native DWI tractography points and must not be deleted. For a
point `a` outside the primary anchor-to-target point field, production instead
solves the paired-field equation

```text
m + d_target_to_anchor(m) = a
```

for the target-space point `m`. The initial estimate is `a` plus the primary
displacement sampled at the nearest in-domain voxel. That clipped sample is
initialization only: the published coordinate is the converged numerical
solution. The solver uses damped fixed-point iteration, requires every iterate
sample to remain inside the paired target-grid field, and accepts a point only
when the Euclidean residual is `<= 1e-5 mm`. Representative `sub-SNr022`
points converged 20/20 with residuals at or below approximately `1e-8 mm`.

If any outside-primary point cannot be solved under this contract, the subject
remains `native_complete`, the target-space stage records the exact unresolved
count and residual, and no target-space `complete` state is written. Identity
mapping, nearest-boundary extrapolation as a final value, streamline
truncation, point deletion, and native retracking remain prohibited.

## Incremental invalidation contract

| Semantic change | Invalidated component |
| --- | --- |
| Publication directory layout only | No scientific component |
| One native target TCK | Corresponding target-space target TCK only |
| One native seed-wide TCK | That side's target-space seed-wide and 17 targets |
| Direct B0-to-anchor matrix | All target-space TCKs for that subject |
| Target-to-anchor image deformation, which is read by native ROI preparation and reused as the production anchor-to-target point field | Affected native ROI preparation and tracking, plus all target-space coordinate outputs downstream of the changed native or point transform for that subject |
| Anchor-to-target image deformation used as the reverse QC point field | Round-trip QC for every subject; additionally, target-space coordinate bytes for any side that recorded paired-field inverse solved points |
| Space-conversion coordinate code | Target-space TCKs only |
| Nibabel RAS point-field application code | Target-space TCKs only |
| External ANTs reference-helper code | Reference parity QC and target-space completion only; already converted coordinate bytes remain reusable if the production backend and inputs are unchanged |
| Anchor-to-B0 matrix | Native ROI preparation, affected tracking, and downstream target-space TCKs |
| Seed ROI content | Affected native side and its downstream target-space TCKs; every scene that renders that seed wireframe is also invalidated even if regenerated TCK bytes happen to be unchanged |
| One target ROI content | That target's native classification and downstream target-space TCK; every scene that renders that target surface is also invalidated even if regenerated TCK bytes happen to be unchanged |
| Removal of `preSMA` | No seed-wide or remaining-target invalidation |
| Parsed `visualization.target_fiber_display_budget` | Sampling manifest, display inputs, FIG, PNG, and PDF for each affected subject-side; no TCK invalidation |
| Parsed `visualization.target_colormap` | Resolved color mapping, display inputs, FIG, PNG, and PDF only; sampling selections and all TCKs remain reusable |
| Parsed `visualization.seed_wireframe_color` | Display inputs, FIG, PNG, and PDF only; sampling selections and all TCKs remain reusable |
| Ordered configured target-ID list or target count | Existing scientific target membership follows its own target-list invalidation; the complete resolved display color mapping is regenerated for every affected side |
| One target-space target TCK | The complete subject-side display sampling and scene, because membership proportions and all integer quotas share one denominator |
| Target-surface style | FIG, PNG, and PDF only; display selection and all TCKs remain reusable |
| Seed-wireframe style | FIG, PNG, and PDF only |
| Normative view preset or backdrop | FIG initial camera and PNG/PDF views only; display selection and TCKs remain reusable |
| Toolbar/control implementation | FIG only, plus static views only if visible scene contents change |
| Visualization generator code | Only the display substage whose semantic code fingerprint changed |
| YAML comments, whitespace, ordering, or equivalent serialization | No invalidation |

`atlas.space` is a semantic declaration, transform selector, and output-space
identifier. A changed value selects a different target-space directory and
transform set. It must not merely rename an existing target-space result.

The target-space coordinate stage fingerprint includes only the native source
TCK identity, direct B0-to-anchor matrix, production target-to-anchor image
deformation, parsed `atlas.space`, and coordinate-conversion code semantics.
The deformation identity covers its complete file bytes, including the intent,
vector layout, affine, and payload that are validated at the field input
boundary. These header semantics are not separately exposed as configuration
and do not create a second invalidation switch.
The reverse-QC fingerprint additionally includes the paired anchor-to-target
image deformation. The native tracking fingerprint includes the
target-to-anchor image deformation only because native ROI preparation already
reads that file. It does not gain the paired reverse-QC field or target-space
publication code as new native-tracking dependencies.

The visualization configuration fingerprint consumes the normalized positive
integer budget, validated Matplotlib colormap name, normalized seed RGB value,
and ordered target-ID list, not the raw YAML bytes. The display-surface
fingerprint additionally consumes the SHA-256 of the configured seed mask and
every ordered target mask because MATLAB reads those NIfTI payloads directly
when it renders the wireframe and translucent surfaces. A change to any of these
display values does not invalidate ROI preparation, FOD, native tracking,
target membership, or target-space coordinate transformation. Styling and
camera fingerprints are separate from sampling so a visual-only change does
not reread or rewrite TCK coordinates.

This table is only implementable because the whole-configuration hash gate is
removed. While a single `configuration_hash` covered the entire resolved
mapping, adding or changing the `visualization` block changed the one hash
shared by every stage and every subject, so no row of this table could be
honoured. The
per-stage fingerprints defined above replace it.

## Acceptance plan

### Gate A: documentation review

Before migration or implementation:

- this document is present and marked `implementation_not_started`;
- the DWI technical documentation agrees with the coordinate directions;
- image-resampling direction and point-transform direction are named
  separately throughout the planned interfaces;
- current YAML is confirmed as the only target-list and target-space authority;
- the same current YAML is confirmed as the only visualization-budget
  and color authority, with the planned values
  `target_fiber_display_budget: 3000`, `target_colormap: hsv`, and
  `seed_wireframe_color: "#D9D9D9"` under `visualization`;
- the migration treatment of historical `preSMA` is explicit;
- approved decisions A, B, C, E, and F are reflected in every affected
  section, while decision D is explicitly provisional pending Gate F;
- no runtime or external data has been changed.

### Gate B: migration dry run

The temporary script must report:

- 16 configured subjects;
- 576 authoritative current TCK files;
- zero missing current files;
- all expected existing hashes and streamline counts;
- the exact set of historical `preSMA` files to be moved to Trash;
- zero destination collisions;
- no active subject writer;
- sufficient same-volume path availability for atomic renames;
- no planned scientific recomputation.

Any discrepancy stops before mutation.

### Gate C: migration acceptance

After apply mode:

- all 16 subjects are migrated;
- `tractograms/native` contains 576/576 authoritative TCK files;
- `tractograms/<target_space>` exists and is initially empty;
- legacy root-level `tractograms/lh` and `tractograms/rh` are absent;
- every migrated TCK has an unchanged SHA-256;
- every migrated TCK has an unchanged mtime;
- every migrated TCK has an unchanged streamline count;
- historical `preSMA` files are recoverable in Trash and recorded in the audit;
- state artifact paths resolve under `tractograms/native`;
- state artifacts carry `coordinate_space: native`;
- a second script run performs no mutation;
- no tracking, FOD generation, MATLAB ROI preparation, or target-space
  conversion has occurred.

### Gate D: focused implementation tests

Run the smallest relevant test set in the `leaddbs` Conda environment. Tests
must cover:

1. safe parsing of `atlas.space` as one directory component;
2. two synthetic target-space names producing different dynamic directories;
3. target-space transform discovery derived from `config.atlas.space`;
4. approved SPM, BRAINSFit, and ANTs B0 method-token selection;
5. direct B0-to-anchor selection with no runtime inversion;
6. direct anchor-to-B0 selection for reverse QC with no runtime inversion;
7. production point mapping selecting the
   `from-<target_space>_to-anchorNative` image deformation;
8. rejection of the `from-anchorNative_to-<target_space>` image deformation as
   the production anchor-to-target point field;
9. native publication under `tractograms/native`;
10. target-space files not being treated as unknown native files;
11. migration dry run, apply, idempotence, and collision stop behavior;
12. native artifact reuse preserving hashes and mtimes;
13. a native-complete fast path that does not call `prepare_subject`, MATLAB
    ROI preparation, `run_seedwide`, or `tckgen`;
14. exact affine point transformation;
15. RAS/LPS conversion confined to the external ANTs reference helper, with no
    LPS conversion in the Nibabel production backend;
16. deterministic all-RAS production point-field agreement with ANTs;
17. correct production-field voxel-domain inclusion using the full field
   affine, including oblique geometry;
18. exact paired-field numerical inversion for outside-primary points,
    including convergence, residual provenance, and fail-closed behavior;
19. ordered target-subset reconstruction;
20. preservation of streamline count, order, and per-streamline point counts;
21. paired reverse point mapping and complete DWI-to-target-to-DWI round-trip;
22. target-space interruption and target-space-only resume;
23. an all-sides-reused target-space resume returning the recorded per-side
    coordinate and round-trip fingerprints without depending on variables
    assigned only by a conversion branch;
24. target-space failure preserving valid native artifacts;
25. concurrent full-chunk point-field sampling matching serial output hashes
    when the process-local nonlinear point-field lock is active;
26. concurrent subject completion admitting no more than one MATLAB
    visualization stage at a time while preserving target-space concurrency;
27. both MATLAB ROI preparation and visualization launching with
    `-noFigureWindows`, `-nosplash`, and `-batch`, with all render and
    verification figures remaining invisible;
28. `status` validating both spaces and every expected visualization artifact;
29. cache cleanup being blocked until both spaces and visualization are
    complete;
30. separate coordinate and round-trip-QC fingerprints;
31. semantic local invalidation without raw whole-YAML invalidation;
32. strict schema/model parsing of the positive-integer display budget,
    registered Matplotlib colormap name, and six-digit seed RGB hex color, with
    rejection of invalid values and unknown visualization keys;
33. normalized display and color values affecting only the appropriate
    visualization fingerprints;
34. largest-remainder quotas summing to 3000, with deterministic YAML-order
    tie breaking and correct behavior when fewer memberships are available;
35. midpoint-stratified row selection being deterministic, unique within a
    target, and retaining every point of each selected streamline;
36. real multi-target membership being retained, including one physical
    streamline appearing in more than one colored target layer;
37. no cross-target exclusivity, neutral recoloring, or deduplication;
38. exactly one scene per configured subject and side;
39. exactly 17 target fiber layers, 17 target surfaces, and one seed wireframe
    per current scene, with no `preSMA` layer;
40. exactly `N` distinct target colors generated by sampling the configured
    colormap at `j/N` on `[0, 1)`, with deterministic YAML-order assignment and
    identical resolved RGB values in fibers, surfaces, controls, legends, and
    manifests across subjects and matching sides, plus rejection of a colormap
    that yields duplicate sampled rows;
41. target `FaceAlpha = 0.15`, seed `FaceColor = none` and
    `EdgeAlpha = 0.15`, and fiber line width `0.25` with alpha `1.0`;
42. exact reuse of the normative view helper, black background, approved
    backdrop, orthographic projection, and no RAS triad;
43. expected per-layer and global controls surviving FIG save, close, reopen,
    and control rebinding;
44. nonempty 600-dpi PNG and PDF exports with the categorical legend and no
    SVG artifact;
45. visualization-only interruption and resume causing zero native or
    target-space TCK rewrites;
46. normalization approval accepting `1` and `0.5`, rejecting `0` and a missing
    field, reading the **scalar** `approval` rather than a per-modality
    mapping, recording the raw value, and emitting a warning when the value is
    not exactly `1`;
47. production and reverse-QC field input validation accepting only NIfTI
    displacement intent `1006`, vector layout `(X, Y, Z, 1, 3)`, a finite
    invertible affine, and the expected anchorNative or target-space grid, while
    rejecting each violated contract;
48. an asymmetric displacement regression in which direct all-RAS addition
    matches ANTs, naive raw-vector addition to an LPS point fails in x and y,
    and checking the z component alone would miss the failure;
49. absence of any whole-configuration hash gate, with cases proving that
    adding or changing the visualization budget, colormap, or seed color
    neither blocks cache cleanup nor invalidates any scientific stage;
50. retention of per-artifact `sha256` for publication ownership, including
    rejection of a foreign file occupying a managed path;
51. migration downgrading a pre-existing `status: complete` to
    `native_complete`;
52. the native fast path validating published artifacts in place and never
    calling into transactional publication when staging directories are absent;
53. the production point field being on the anchorNative grid and the
    reverse-QC field being on the target grid, asserted per subject across
    EasyReg, ANTs, and SynthMorph normalization.

The complete unrelated repository test suite is not required unless focused
failures demonstrate a broader shared-interface impact.

### Gate E: `sub-SNr017` transform-chain canary

Before the conversion pilot, the implementation must reproduce the currently
verified `sub-SNr017` chain from the live selected inputs rather than from
hard-coded expected coordinates:

- the normalization method log is approved, using the scalar `approval` field
  and the accepted set `{1, 0.5}` from decision A, with the raw value recorded;
- the B0 method log is approved and selects the direct method-specific
  B0-to-anchor `44.mat`;
- the paired direct B0-to-anchor and anchor-to-B0 matrices multiply to identity
  within floating-point tolerance;
- the production point field is the file named
  `from-MNI152NLin2009bAsym_to-anchorNative` for the current configured space;
- the reverse-QC point field is the file named
  `from-anchorNative_to-MNI152NLin2009bAsym`;
- both selected fields pass the NIfTI displacement intent, vector-layout,
  finite-affine, invertibility, and expected-grid boundary contract;
- the measured raw displacement
  `[8.0296, -30.2542, 31.4817]` is added directly to its anchorNative RAS point
  and reproduces target RAS `[9.7150, -54.7284, -43.3824]`;
- the same point agrees with the external ANTs LPS reference within
  `1e-4 mm`, while the intentionally naive LPS interpretation reproduces the
  known incorrect result `[-6.3441, 5.7801, -43.3824]` and is rejected;
- all tested tracking-mask voxel centres are inside the production point-field
  domain when evaluated in field voxel coordinates;
- the recorded real TCK point transforms to a finite target coordinate and
  returns to native DWI with Euclidean error below `0.05 mm`;
- the old `641/10000` wrong-field domain result is absent from runtime status,
  provenance, and acceptance output.

The literal space name in this canary identifies the current verified input
pair only. Runtime discovery and all general tests continue to derive the
space from `config.atlas.space`.

### Gate F: five-subject cross-method pilot

The first conversion pilot uses:

```text
sub-SNr003  EasyReg
sub-SNr015  EasyReg
sub-SNr029  EasyReg
sub-SNr007  SynthMorph
sub-SNr018  ANTs
```

This produces up to:

```text
5 subjects × 2 sides × (1 seed-wide + 17 targets) = 180 target-space TCK files
```

Every pilot file must satisfy:

- source and output streamline counts are exactly equal;
- independent Nibabel and `tckinfo` counts agree;
- source and output total point counts are exactly equal;
- the per-streamline point-count sequence is exactly equal;
- streamline order is exactly equal;
- target membership is exactly equal;
- all output coordinates are finite;
- native source SHA-256 and mtime remain unchanged;
- no temporary file is accepted as final;
- no point outside the production point-field domain is silently
  identity-mapped.

For deterministic samples inside the production point-field domain, the bulk
implementation and bundled `antsApplyTransformsToPoints` output must differ by
no more than:

```text
maximum Euclidean error <= 1e-4 mm
```

For points in the common valid domains of the production and reverse-QC point
fields, the provisional round-trip QC limits from decision D are:

```text
median error <= 0.05 mm
95th percentile error <= 0.2 mm
maximum error <= 0.5 mm
```

The completed 16-subject, 32-side read-only audit found 28 sides below all
three limits. The only failures were both sides of `sub-SNr029` and
`sub-SNr030`; both use EasyReg field pairs with normalization approval `0.5`.
Their 200-point metrics were:

```text
subject-side     median mm    p95 mm    max mm
sub-SNr029 lh      0.1790      0.7627    0.9085
sub-SNr029 rh      0.1293      0.4540    0.7960
sub-SNr030 lh      0.1323      0.4531    1.0949
sub-SNr030 rh      0.3708      0.9944    1.1402
```

The next-highest cohort p95 was `0.0199 mm`. For `sub-SNr029`, both the
production and reverse-QC point mappings independently matched the bundled ANTs
point executable within `7.71e-5 mm`, while a 1,000-point repeat reproduced the
paired-field inconsistency. This isolates the failure to the supplied field
pair rather than the RAS/LPS convention, field direction, Python interpolation,
or TCK sampling. Decision D must not be closed by loosening the limits across
the cohort.

Subsequent read-only provenance inspection found that these two cases are not
ordinary failed EasyReg outputs. Their historical
`warpdrive/legacy_contact_compat/install_legacy_contact_compat.json` records
show that the normalization transforms were replaced under the
`ordinary_forward_point_exact_inverse` policy so regenerated anchor-native
contacts reproduce historical cohort MNI coordinates exactly. That policy is
now superseded: the `PointExact` field is authoritative and the opposite field
must be generated only by numerical inversion of it. The ordinary composed
forward may be used only as the numerical solver's initial estimate. The
pre-install EasyReg field pairs remain preserved under each subject's `bak/`
directory and are not modified.

A 200-point-per-side comparison using the same production point semantics and
the same native seed-wide TCK sampling found that both preserved pairs pass the
unchanged plan thresholds:

```text
subject-side       median mm    p95 mm    max mm
sub-SNr029 lh        0.0366      0.1589    0.3057
sub-SNr029 rh        0.0410      0.1273    0.3087
sub-SNr030 lh        0.0306      0.0943    0.1801
sub-SNr030 rh        0.0200      0.0740    0.1423
```

The comparison artifact is:

```text
/private/tmp/mrtrix-seed-target-candidate-field-pair-audit.json
```

The approved closure retained the contact-compatible `PointExact` direction
and replaced its companion with a numerical inverse derived from that same
authoritative field. The independently fitted reverse RBF and the ordinary
composed forward are not production companions; the ordinary composed forward
is retained only as the numerical solver's initial estimate. Newton is the
primary solver. Candidate grid points that do not converge under Newton are
restarted from the same estimate and solved by damped fixed-point iteration
against the authoritative field, preventing isolated zero-displacement holes
without falling back to ordinary-field values. The replacement fields passed the
unchanged Gate F limits on contacts, 10,000 deterministic anchor-brain-mask
samples, and 1,000 actual seed-wide tractography midpoint samples per side,
with independent ANTs point parity.

Post-install round-trip acceptance metrics were:

```text
support                               median mm    p95 mm    max mm
sub-SNr029 contacts, anchor domain       0.0064     0.0277    0.0296
sub-SNr029 contacts, MNI domain          0.0076     0.0321    0.0371
sub-SNr029 anchor brain mask             0.0099     0.0336    0.1426
sub-SNr029 tractography lh               0.0024     0.0103    0.0405
sub-SNr029 tractography rh               0.0023     0.0122    0.0573
sub-SNr030 contacts, anchor domain       0.0083     0.0248    0.0275
sub-SNr030 contacts, MNI domain          0.0084     0.0314    0.0319
sub-SNr030 anchor brain mask             0.0088     0.0312    0.1491
sub-SNr030 tractography lh               0.0019     0.0083    0.0345
sub-SNr030 tractography rh               0.0017     0.0069    0.0351
```

The installed active-field hashes match the validated candidates, both NIfTI
headers use displacement-vector intent, and the maximum in-process-versus-ANTs
contact difference was `8.57e-5 mm`. The prior active fields and superseded
validation/provenance files were moved to:

```text
/Users/mojackhu/.Trash/legacy_contact_compat_pair_replacement_20260805T062048Z
```

The active replacement pair was then exercised by the production YAML pipeline
on every point in both `sub-SNr029` seed-wide TCKs. All points were inside the
production field domain, all 36 configured target-space artifacts were written,
and the side-level 200-point round-trip metrics were:

```text
subject-side     median mm    p95 mm    max mm    ANTs parity max mm
sub-SNr029 lh      0.0019      0.0100    0.0238       0.0000690
sub-SNr029 rh      0.0024      0.0098    0.0214       0.0000599
```

This production result closes the former two-field-pair blocker without
loosening any threshold and without regenerating native tractography.

The completed structural acceptance audit covered the canary `sub-SNr017` and
the four conversion-pilot subjects that passed round-trip QC
(`sub-SNr003`, `sub-SNr007`, `sub-SNr015`, and `sub-SNr018`). Across ten
subject-sides, every seed-wide TCK retained exactly 300,000 streamlines, the
complete per-streamline point-count sequence, finite target-space coordinates,
and the exact ordered membership of all 17 currently configured targets.
Native SHA-256 values and mtimes remained equal to the migration audit. The
read-only evidence is recorded in:

```text
/private/tmp/mrtrix-seed-target-structural-acceptance.json
```

Measured on 200 deterministic real TCK points from
`sub-SNr017 lh M1`, the observed errors were `median 0.0040 mm`,
`p95 0.0172 mm`, and `max 0.0342 mm`, so the tightened limits still retain
headroom for that EasyReg example. The same limits become binding only if the
EasyReg, ANTs, and SynthMorph pilot subjects all pass. A cross-method failure
triggers investigation of transform semantics or method-specific numerical
behaviour; it does not automatically loosen the thresholds.

Anatomical pilot acceptance requires:

- exact preservation of the segment-aware membership already established on
  the native DWI grid, including streamline identity, count, and order;
- optional descriptive target-space seed/target intersection fractions, which
  must not be converted into a pass/fail threshold or used to rewrite
  membership;
- no left/right reflection, assessed through the independent point-transform
  parity and seed/target visual overlay, never through the coordinate sign of
  complete streamlines;
- visual overlay on the reference image for `config.atlas.space` for both
  sides of all five pilot subjects;
- PNG or PDF QC only, with no SVG output.

The former requirement of at least 95% intersection after one target-space
voxel of dilation is removed as a pass/fail gate. It was dimensionally
inconsistent with the data. For example, `sub-SNr003` native B0 voxels are approximately
`1.75 x 1.75 x 5.0 mm`, while the configured MNI atlas voxels are
`0.5 x 0.5 x 0.5 mm`. The native classifier accepts a whole anisotropic DWI
voxel when a streamline segment traverses it, so a single 0.5 mm atlas-voxel
dilation cannot reproduce the original spatial support.

A read-only sensitivity audit of 170 target TCKs from the five available
subject-sides found that one 6-connected atlas-voxel dilation passed 43 files
and one 26-connected atlas-voxel dilation passed 105 files at the former 95%
threshold. The minimum target-hit fractions were 0.589 and 0.658,
respectively. This confirms that neighborhood connectivity alone cannot close
the gate. The audit artifacts are:

```text
/private/tmp/mrtrix-seed-target-anatomical-acceptance.json
/private/tmp/mrtrix-seed-target-anatomical-acceptance-connectivity-3.json
```

The native-ROI reconstruction for `sub-SNr003 lh PPN` provides a direct
counterexample to treating target-space mask intersection as a preservation
test. The cleaned native PPN mask contains only four DWI voxels and has SHA-256
`532de3bd10d7af619579b9c6ffe20a092ea303cf7a790ba9f5f1b1c540f2cdfc`,
identical to the historical classification state. All `32,409/32,409`
published native PPN streamlines satisfy the exact segment-aware native
membership test. The source atlas PPN contains 528 voxels at 0.5 mm isotropic
resolution, whereas the native B0 grid is approximately
`1.75 x 1.75 x 5.0 mm`. Mapping a streamline centreline back to the fine atlas
therefore does not reconstruct the full physical footprint of the coarse
native voxel that made the original membership decision.

Consequently, a numerical target-space hit fraction would test a new
resolution-dependent property rather than preservation of the existing target
membership. The approved closure deletes that redundant numeric pass/fail
threshold rather than choosing a larger dilation radius. The MNI masks remain
authoritative inputs and descriptive intersection fractions remain permitted.
Direction and content correctness remain independently covered by ANTs point
parity, exact streamline/count/order preservation, exact native membership
preservation, and the target-space visual overlay.

The reflection test must not assume that a side's streamlines stay within that
hemisphere. Target TCK files contain complete, untruncated streamlines, so a
streamline that legitimately intersects a left-hemisphere target may continue
across the midline. Measured on `sub-SNr017 lh M1`, the converted target-space
points span `x` from `-63.0` to `+49.7`. A sign-based reflection check would
report a false positive on correct data; a seed/target intersection check would
not.

Any domain, direction, reflection, count, or membership failure stops before
full-cohort conversion.

### Gate G: visualization pilot

After `sub-SNr017` passes the transform canary and both target-space sides are
complete, it is the first visualization pilot because its real data already
demonstrate substantial nonexclusive target membership. The pilot must show,
for both `lh` and `rh`:

- only the current 17 configured targets are included;
- the available target counts are read from the final target-space target
  TCKs;
- target shares use `sum(n_k)` as the denominator;
- largest-remainder quotas sum to exactly `3000`;
- every selected target row is an exact, all-point-preserving member of its
  source target TCK;
- the manifest reports both 3000 membership instances and the realized unique
  streamline count;
- at least one observed multi-target fiber can remain represented in multiple
  colored layers without being forced into an exclusive target;
- target fibers, target surfaces, toolbar controls, and the static legend use
  the same target-ID colors;
- target surfaces are visibly translucent at alpha `0.15` and do not obscure
  the fibers;
- the configured side-specific `STNSNrplus` seed is visibly rendered as a
  wireframe;
- the realized camera state exactly matches the normative helper;
- the FIG closes and reopens with all controls functional;
- one PNG and one PDF view are produced for each side, with no SVG;
- native and target-space TCK hashes and mtimes are unchanged.

After this canary, the five conversion-pilot subjects produce ten additional
scenes under the same contract. Visual inspection checks target/side identity,
colormap consistency, seed/target overlay, fiber continuity, anatomy backdrop,
legend readability, and absence of left/right reflection before rendering the
remaining cohort.

The two `sub-SNr017` canary scenes and the eight scenes from the four
round-trip-passing conversion subjects (`sub-SNr003`, `sub-SNr007`,
`sub-SNr015`, and `sub-SNr018`) have been generated and visually inspected.
All ten show consistent side orientation, target-color correspondence, the
configured seed wireframe, target surfaces, continuous fibers, the anatomical
backdrop, and a readable legend. Colors span the configured cyclic colormap
without a target-specific RGB table.

After the replacement-field Gate F pass, both `sub-SNr029` scenes were also
generated in a real background canary with MATLAB launched using
`-noFigureWindows -nosplash -batch`. No MATLAB desktop or figure-window process
was started. Visual inspection found correct orientation and scene content. It
also identified that MATLAB's default TeX interpretation altered target IDs
containing underscores. The legend now uses `Interpreter='none'`; a subsequent
left-side background canary confirmed that all YAML target IDs are displayed
literally. The final cohort run regenerates every scene under this corrected
visualization fingerprint.

A complete read-only manifest and geometry audit of these ten scenes passed.
For every scene, the current YAML target order determined the dynamic target
count and the `hsv` positions `j/N`; there was no target-name-to-RGB table.
Largest-remainder quotas summed to 3,000, every membership CSV ordinal and
digest matched the selected source TCK streamline, and every geometry-array
point sequence matched exactly. Each scene contained `N` fiber layers, `N`
target surfaces, one seed wireframe, and `2*N+3` controls (37 for the current
17 targets), plus exactly one FIG, PNG, and PDF and no SVG. Live seed, target,
TCK, geometry, scene, and artifact hashes all matched their manifests. The
audit is recorded in:

```text
/private/tmp/mrtrix-seed-target-scene-acceptance.json
```

The display-surface fingerprint now includes the live seed-mask hash and all
ordered target-mask hashes. The ten pilot scenes were regenerated after this
dependency was added; ROI content changes can no longer reuse a stale surface
scene, while sampling, native TCKs, and target-space TCKs remain reusable.

### Gate H: full-cohort conversion and visualization acceptance

Full conversion starts only after all pilot gates pass. Terminal acceptance
requires:

- EasyReg, ANTs, and SynthMorph canaries all passing the production/reference
  parity and round-trip limits, thereby closing provisional decision D;
- 576/576 native TCK files;
- 576/576 configured target-space TCK files;
- 1,152 authoritative managed TCK files in total;
- 32/32 interactive FIG scenes;
- 32/32 fixed-view PNG files;
- 32/32 fixed-view PDF files;
- zero SVG files;
- 32/32 sampling manifests, scene manifests, and visualization completion
  records;
- 16/16 subjects in state `complete`;
- zero missing, failed, or unexpected current artifacts;
- no managed `preSMA` artifact;
- native and target-space streamline counts matching for every artifact;
- native and target-space per-streamline point-count sequences matching for
  every artifact;
- all 32 side-level ordered-subset contracts passing;
- all target-space artifact space labels matching `config.atlas.space`;
- all target-space output directories matching `config.atlas.space` exactly;
- every production point-field provenance entry naming the selected
  target-to-anchor image deformation;
- every reverse-QC provenance entry naming the paired anchor-to-target image
  deformation;
- all transformation paths and recorded space labels agreeing;
- every scene containing 17 target fiber controls, 17 target-surface controls,
  one seed-wireframe control, and the two global target/fiber controls;
- every scene reporting a realized membership budget of 3000 unless its source
  contains fewer than 3000 total memberships;
- every target quota, selected row, target color, and unique-streamline count
  reproducible from the authoritative YAML and target-space TCKs;
- every FIG and static view matching the approved normative camera and
  configured-space backdrop;
- every reopened FIG retaining functional controls;
- native hashes and mtimes unchanged from the accepted migration inventory;
- no accepted staging or partial files;
- `mrtrix-seed-target status` returning `complete`;
- cache cleanup running only after the preceding checks pass;
- no individualized scoring, exposure, jitter, statistics, or model
  publication output created or changed;
- no Git commit or push.

Gate H passed on the authoritative 16-subject cohort. The final read-only CLI
status returned `complete` with configuration hash
`942f0f86e43d2a305e105aefa3059e9579c53df68d4fdfd2831a45730d208691`,
16 complete subjects, and zero artifact errors. The accepted inventory,
excluding exFAT `._*` AppleDouble sidecars, contains 576 native TCK files, 576
configured-space TCK files, 32 FIG files, 32 PNG files, 32 PDF files, and zero
SVG files. All 32 sampling manifests, scene manifests, and visualization
completion records are present, and no managed `preSMA` file is present.

The full structural acceptance audit passed all 32 subject-sides with zero
failures. It verified native-to-target streamline counts, finite coordinates,
per-streamline point-count sequences, ordered target membership, accepted
native hashes and mtimes, configured-space labels, and the absence of staging
or partial artifacts. The independent round-trip audit passed all 32 sides:
30 sides used the primary in-process point-field backend and the two
`sub-SNr022` sides used the approved paired-field numerical inverse only for
points outside the primary field domain. For `sub-SNr022`, all 9,209 left-side
and 10,929 right-side outside-domain points converged, no point remained
unresolved, and the maximum inverse residuals were
`9.999156674749473e-6 mm` and `9.99990104515475e-6 mm`, respectively. Its
round-trip maxima were `0.02895351140470927 mm` and
`0.027077149280454273 mm`, and its ANTs-parity maxima were
`0.00006533225623226033 mm` and `0.00006298900106605636 mm`.

The scene acceptance audit passed all 32 scenes with zero failures. Every
scene contains the current 17 target layers and surfaces, 3,000 membership
instances, 37 controls, deterministic YAML-derived colors, exact source-TCK
membership, and FIG/PNG/PDF artifacts. Representative left and right
`sub-SNr022` static views were visually inspected after the numerical inverse
resolution and showed consistent orientation, continuous fibers, target
overlays, seed wireframes, anatomy backdrops, and literal target labels.
Every production render command used
`MATLAB_maca64 -noFigureWindows -nosplash -batch`; no MATLAB desktop or figure
window was started, and existing user MATLAB processes were not accessed.
The ROI-preparation command now uses the same three process flags; its focused
command-contract test confirms that future native preparation is also
windowless.

The final focused test run passed all 69 tests under
`my_helper/fiber/core/mrtrix_seed_target/tests`. The machine-readable Gate H
records are:

```text
/private/tmp/mrtrix-seed-target-final-status.json
/private/tmp/mrtrix-seed-target-structural-acceptance.json
/private/tmp/mrtrix-seed-target-gate-h-roundtrip.json
/private/tmp/mrtrix-seed-target-scene-acceptance.json
```

## Planned change surface

`preparation.py` and `roi.py` are included because they consume the two renamed
transform fields: `preparation.py` forwards the target-to-anchor image
deformation to MATLAB, and `roi.py` uses the anchor-to-B0 matrix.
`tests/helpers.py` is included because it hard-codes the current space literal.

The implementation is expected to make localized changes to:

```text
my_helper/fiber/core/mrtrix_seed_target/config.py
my_helper/fiber/core/mrtrix_seed_target/models.py
my_helper/fiber/core/mrtrix_seed_target/schemas/config.schema.json
my_helper/fiber/core/mrtrix_seed_target/discovery.py
my_helper/fiber/core/mrtrix_seed_target/validation.py
my_helper/fiber/core/mrtrix_seed_target/publication.py
my_helper/fiber/core/mrtrix_seed_target/pipeline.py
my_helper/fiber/core/mrtrix_seed_target/preparation.py
my_helper/fiber/core/mrtrix_seed_target/roi.py
my_helper/fiber/core/mrtrix_seed_target/cache_cleanup.py
my_helper/fiber/core/mrtrix_seed_target/tractogram_space.py
my_helper/fiber/core/mrtrix_seed_target/visualization.py
my_helper/fiber/core/mrtrix_seed_target/tests/
my_helper/fiber/core/mrtrix_seed_target/tests/helpers.py
my_helper/fiber/core/viz/mh_viz_make_mrtrix_seed_target_scene.m
my_helper/fiber/core/viz/mh_viz_export_mrtrix_seed_target_scenes.m
my_helper/fiber/core/viz/examples/open_mrtrix_seed_target_scene.m
```

After strict parser support passes focused tests, the external authoritative
configuration is updated in place by first moving the untracked original to
Trash and then installing the corrected YAML containing:

```yaml
visualization:
  target_fiber_display_budget: 3000
  target_colormap: hsv
  seed_wireframe_color: "#D9D9D9"
```

No second visualization configuration, unrelated dual-frequency model, or
statistical file belongs to this change.
