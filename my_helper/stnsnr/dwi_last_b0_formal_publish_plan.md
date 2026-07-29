# Last-B0 DWI Formal Publication Plan

## Scope

Publish the completed last-b0 preprocessing candidates for the following subjects:

| Subject | Candidate root | Phase encoding | B0 reference |
| --- | --- | --- | --- |
| SNr017 | `snr017_jminus` | `j-` | last acquired b0, source index 2 |
| SNr020 | `snr020_026_jplus` | `j` | last acquired b0, source index 2 |
| SNr022 | `snr022_jminus` | `j-` | last acquired b0, source index 2 |
| SNr026 | `snr020_026_jplus` | `j` | last acquired b0, source index 2 |

The candidate roots are under:

```text
/Volumes/VAL/STNSNr/derivatives/leaddbs/import_logs/
  dwi_last_b0_reprocessing_20260715_221834/
```

All four candidates completed Synb0/topup/eddy successfully and have the
`pending_ui_coregistration` status.

## Publication Rules

1. Replace each subject's complete `rawdata/sub-*/ses-preop/dwi` directory.
2. Replace each subject's complete `derivatives/leaddbs/sub-*/preprocessing/dwi`
   directory, including the Synb0/eddy work records.
3. In `coregistration/anat`, replace only the pseudo-B0 NIfTI and JSON sidecar.
   Preserve CT, T1w, T2w, FLAIR, SWI, QSM, and all other anatomical files.
4. Invalidate only stale B0 registration state:
   - B0-to-anchorNative and anchorNative-to-B0 transform files;
   - the B0 check-registration PNG;
   - the `B0` entries in `desc-coregmethod.json`.
5. Preserve all non-B0 registration transforms and approval records.
6. Move every replaced untracked artifact to the external-disk Trash before
   publication. Do not permanently delete it.
7. Stage and validate replacements before changing formal paths. Restore the
   previous data if publication fails.
8. Do not modify connectomics, FOD, ROI, or tractography products during this
   publication. Those products remain stale until manual B0 registration and
   downstream regeneration are complete.

## SNr022 Phase-Encoding Resolution

The original SNr022 DICOM series contains 66 instances. All 66 instances store
`A->P` in private tag `(0065,1005)`. The corrected NIfTI positive `j` axis points
predominantly anteriorly, so the physical `A->P` direction maps to `j-` on the
corrected grid. The formal raw JSON must therefore explicitly contain
`"PhaseEncodingDirection": "j-"` before publication.

## Required Post-Publication State

- The formal raw and preprocessing files match their selected candidates.
- The formal pseudo-B0 matches the candidate corrected b0.
- No old B0 registration transform or B0 check-registration PNG remains in the
  active subject directory.
- Non-B0 anatomical and registration artifacts remain unchanged.
- Lead-DBS is ready for manual B0 coregistration in the UI.
