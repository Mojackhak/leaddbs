# D99 limbic, frontal, and pallidal atlas

## Approved content

Create `D99 NAc_ALIC_HIP_AMY_GPi_GPe_mPFC` under
`templates/space/D99v2/atlases`. Each hemisphere contains 36 masks: 29
subregions, three exact merged masks, and four independent regions. The final
atlas therefore contains 72 binary NIfTI images. Do not replace existing atlases
or change patient data, registration, normalization, or software versions.

Sources are `D99_atlas_hemi_v2.0.nii`, `D99_hemi_v2.0_labels.txt`, and
`D99_hemi_Suppl_Table_1.xlsx` in `templates/space/D99v2/other_files`. The workbook
is read-only source data. Its `Combo_subcortical_corticalabels` sheet supplies
label number, hemisphere, abbreviation, and anatomical name. Match each chosen
ID to the text label list as well. The source labels and D99 T1 already share
the same 275 x 347 x 245 grid, 0.25 mm isotropic spacing, and affine.

## Region definitions

- NAc: left 3, right 525.
- GPi: left 5, right 527.
- GPe: left 4, right 526.
- ALIC: preserve the approved existing `D99 v2.0 NAc_ALIC/lh/ALIC.nii.gz` and
  `rh/ALIC.nii.gz` masks. Embed their cropped arrays on the D99 lattice with an
  integer voxel offset. Do not interpolate or treat all of labels 157/679 as
  ALIC. Record this as an existing derived delineation with unverified original
  boundary-authoring provenance, not an independently labeled D99 structure.
- AMY subregions: Ld, Lv, Bmc, Bi, Bpc, ABmc, ABpc, AAA, CE, COa, COp, PL, ME.
  Output `AMY_PL` corresponds to workbook abbreviation `PL_prime`. Exclude PAC,
  NLOT, and AHA. `AMY` is the exact union of these 13 masks on each side.
- HIP subregions: CA1, CA2, CA3, CA4, FD, Sub, proS, preS, paraS. FD refers to
  the atlas's fascia dentata granule-cell layer. `HIP` is the exact union of
  these nine masks and represents the agreed hippocampal formation definition.
- mPFC subregions: 9m, 10mc, 10mr, 14r, 14c, 25, 32. Output `mPFC_25` and
  `mPFC_32` correspond to `area 25` and `area 32` in the workbook. Exclude 8Bm.
  `mPFC` is the exact union of these seven masks. This composite is the agreed
  project definition rather than a single official D99 label.

Use names such as `AMY_Ld`, `HIP_CA1`, and `mPFC_25`, identical across `lh/`
and `rh/`. Merged names are `AMY`, `HIP`, and `mPFC`. The JSON specification
records explicit left and right IDs; do not infer a universal numeric offset.

## Construction and native display

Document the mapping before executing the builder. Use the `leaddbs` Conda
Python environment with NiBabel and NumPy for exact discrete-label extraction.
Reuse the project's label-union and provenance conventions, but do not route
this already-aligned atlas through the general builder's unconditional MRtrix
resampling step. Write full-reference-grid uint8 masks with values 0/1 and
preserve qform/sform and voxel sizes. Do not smooth, dilate, mirror, or run a
registration. Refuse an existing output directory rather than overwrite it.

Use the existing `ea_roi`, `ea_saveatlas`, and `ea_loadatlas` interfaces to build
and verify the Lead-DBS cache. The stock `ea_genatlastable` crops its input files
in place, so index objects are built from temporary cropped copies while the
72 public full-grid masks stay unchanged. Store final mask paths in the cached
ROI objects. Retain the native cache format already used by existing atlases;
do not introduce a new schema or project version. Do not create a lead-field
gray-matter mask by summing overlapping parent/child masks.

Use anatomical-family colors, native subgroups, and existing display presets:
`Merged regions` shows NAc, ALIC, GPi, GPe, AMY, HIP, and mPFC; `Subregions`
shows the four independent regions and 29 subregions. The merged view is the
default. Keep the parent/child hierarchy explicit in the manifest so downstream
analysis does not sum a parent together with its children.

## Outputs and focused checks

Deliver the binary masks, `atlas_index.mat`, JSON/CSV source manifests, QC
metrics, region definitions, and multiplane template overlays. Check:

1. Every requested label is present and agrees between workbook and text;
   source grid/affine matches the reference and all generated masks are binary,
   nonempty, finite, full-grid, and on the intended anatomical side.
2. Each direct mask equals its exact source label; each merged mask equals the
   OR of its children. Children within a family are disjoint. Parent/child
   overlap is intentional and is not an error.
3. Embedded ALIC masks preserve original support and world coordinates and
   remain subsets of source labels 157/679. Inspect their D99 anatomical overlay;
   this is spatial QA, not independent boundary ground truth.
4. Native cache contains 36 bilateral entries with matching ROI supports,
   geometry, names, hierarchy, and presets. Verify rendering through native ROI
   loading and inspect merged and subregion displays.
5. Confirm supplied source files and the existing ALIC atlas are unchanged and
   final changes contain no unrelated source edits, commits, remote operations,
   or version increments.

## Dependency boundary

The label map and each selected source label affect only their direct ROI,
its merged parent, relevant QC, and the new display cache. The existing ALIC
mask affects only its own side's ALIC output and associated QC/cache. Rendering
color/preset changes affect only the new display cache and previews. Spreadsheet
formatting or unused label changes do not alter extracted masks. The builder
is an explicit one-shot command, not an automatic global invalidation system.
No existing atlas, patient pipeline, normalization cache, or broad test suite
is invalidated or rerun.

## Commands and delivery checks

From the repository root, create a fresh atlas with:

```bash
/opt/anaconda3/envs/leaddbs/bin/python my_helper/atlas/build_d99_limbic_atlas.py
```

Then run `build_d99_limbic_atlas_index` from MATLAB with Lead-DBS and
`my_helper/atlas` on the path. Run the independent mask verification with:

```bash
/opt/anaconda3/envs/leaddbs/bin/python my_helper/atlas/verify_d99_limbic_atlas.py
```

The builder and display-index writer refuse existing destinations. These are
explicit creation commands, not automatic overwrite or cache-invalidation
commands. Native display objects contain cropped data for efficiency while
public masks retain the full D99 grid. Preview titles and panel labels must
remain separate and legible.

Source size/time records verify preservation during this construction only;
they are not cache keys and do not trigger recomputation. The completed build
passed 72 public-mask checks, six parent-union checks, and independent native
readback of all 72 supports against source labels and world coordinates.
