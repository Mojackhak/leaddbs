# AAL3 1 mm adaptation to MNI152NLin2009bAsym

## Scope

Create a derived AAL3 atlas in the physical space of the installed Lead-DBS
MNI152NLin2009bAsym template. Preserve the downloaded AAL3 package, the existing
2 mm parcellation, STNVOplus, and all subject data. Do not run tractography.

## Inputs

- Labels: `/Users/mojackhu/Downloads/AAL3/AAL3v1_1mm.nii.gz`.
- Names: `/Users/mojackhu/Downloads/AAL3/AAL3v1_1mm.nii.txt`.
- Moving anatomy: Colin27 1998 `colin27_t1_tal_lin.nii`, distributed by MNI in
  `mni_colin27_1998_nifti.zip`.
- Fixed anatomy: `templates/space/MNI152NLin2009bAsym/t1.nii`.
- Fixed brain mask: `templates/space/MNI152NLin2009bAsym/brainmask.nii.gz`.

The WTCN Multi-Brain example explicitly pairs this AAL3 image and Colin27 T1:
<https://github.com/WTCN-computational-anatomy-group/mb#4-register-and-warp-atlas-to-mb-space>.
The MNI source archive is:
<https://packages.bic.mni.mcgill.ca/mni-models/colin27/mni_colin27_1998_nifti.zip>.

## Method

1. Check label IDs and NIfTI geometry; inspect AAL3 over its source T1.
2. Derive a 1 mm reference from the installed fixed T1 without changing its
   anatomical coordinate system or modifying the original file.
3. Register Colin27 T1 to that reference with the bundled ANTs: rigid, affine,
   and SyN. Record the command, binary version, reference geometry, and logs.
4. Apply the composed forward warp and affine to the original multi-label
   image once using nearest-neighbor interpolation. Do not smooth, dilate,
   reassign label IDs, or register individual masks separately.
5. Split the transformed labels into non-overlapping binary masks in
   `lh`, `rh`, and `midline`. Paired masks have matching base filenames.
6. Verify label preservation, output geometry, laterality, mask reconstruction,
   and anatomical overlays. Record quantitative results and any limitations.

The 1 mm grid preserves the fixed template's voxel-edge field of view:
197 x 233 x 189 voxels, RAS orientation, first voxel center at
(-97.75, -133.75, -71.75) mm. Linear interpolation is used for the reference
T1 and nearest-neighbor interpolation for its brain mask. Registration uses
both templates' supplied brain masks, MI for rigid/affine, and CC for SyN.
The SyN schedule is 100 x 70 x 50 x 20 iterations at 8/4/2/1 mm scales,
with SyN[0.1,3,0]. Four CPU threads and random seed 42 are recorded.

`adapt_aal3_to_mni2009b.py` provides separate `prepare`, `register`, and
`export` steps so that label export can be reviewed without rerunning the
anatomical registration. It reuses the existing whole-brain binary ROI
exporter rather than adding another mask writer. It is a task-specific
conversion utility, not a new configurable pipeline.
Direct script execution adds the repository root to the Python import path
before loading that exporter, preserving its existing package imports.

## Outputs and review

Retain source anatomy, transforms, and registration QC under
`templates/atlas_sources/AAL3 (Rolls 2020)/`.

The derived atlas destination is
`templates/space/MNI152NLin2009bAsym/atlases/AAL3 (Rolls 2020)/`, with
`labels.nii.gz`, label names, binary ROI folders, provenance, and a README.
Do not overwrite an existing destination. Do not replace the existing
`labeling/Automated Anatomical Labeling 3 (Rolls 2020).nii`.

Technical acceptance requires all 166 nonzero input labels to survive,
integer IDs without additions, identical ROI/reference geometry, and exact
reconstruction of the label image from the binary masks. Anatomy QC must
include cortex, ventricles, thalamus, midbrain, and cerebellum. A derived atlas
does not establish subject-specific accuracy for small nuclei. Human review
remains required before using it in a research analysis.

The official text table has 170 rows. The first column is the label ID;
unused IDs 35, 36, 81, and 82 omit the otherwise redundant third column.
Export only IDs actually present in the source NIfTI, retaining all 170 rows
unchanged in `labels_source.txt`.

## Dependency scope

This is a targeted atlas conversion, not a new cache or pipeline framework.
Registration depends on the two T1 images, registration masks, grid, and ANTs
parameters. Label transfer depends on the source labels and the saved spatial
transform. ROI naming depends on the label table. Documentation changes do not
invalidate registration. No existing patient results are invalidated.

## Completed conversion and focused checks

- ANTs 2.5.4.post19-g73e7590 completed successfully in 444.8 seconds. The final
  SyN level used its 20-iteration budget; this is not a claim that its numeric
  convergence threshold was reached.
- All 166 labels survived: 78 left, 78 right, and 10 midline.
- ROI geometry, qform/sform, integer labels, binary masks, disjointness, and
  exact reconstruction passed on the generated files.
- The 1 mm reference preserves the original 0.5 mm voxel-edge field of view.
- Brain-mask Dice changed from 0.961028 to 0.964784. T1 Pearson correlation
  within the same fixed brain mask changed from 0.739009 to 0.928898.
- Three existing resampling/export unit tests passed. No full test suite or
  patient pipeline was run. The original 2 mm AAL3 still byte-matches the
  downloaded original, and the archived 1 mm source matches its download.
- Source and transformed anatomical montages were visually inspected for
  gross alignment. Human anatomical QC for the exported 166-ROI AAL3 atlas
  was subsequently confirmed by the user on 2026-10-09 for the fixed-sampling
  whole-brain workflow. Subject-specific registration and native ROI QC
  remain separate requirements.

Small structures remain small: the transformed left/right thalamic reuniens
labels contain 8/6 voxels. Hemisphere assignment follows the source names,
not clipping at x=0. Some medial cortical labels already cross x=0 in the
source; for example ACC_sup_L changes from 15.70% to 17.82% across that plane.
This does not by itself establish a left-right flip. Retain the source
definitions and inspect the anatomy rather than silently cutting those ROIs.

The recorded QC reports live in `templates/atlas_sources/AAL3 (Rolls 2020)/qc/`.
No global invalidation, hashing scheme, cache, or retry policy was added.
