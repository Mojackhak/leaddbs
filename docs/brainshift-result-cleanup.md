# Brainshift result cleanup

This operation removes only the user-approved brainshift results from one subject's
Lead-DBS derivatives directory. Move them to macOS Trash and retain their relative
paths so that the original files can be restored.

## Approved scope

- The two postoperative CT images with `rec-brainshift` and
  `rec-tonemappedbrainshift` under `coregistration/anat`.
- The corresponding two CT images under `normalization/anat`.
- The subject's `brainshift` directory, including its unapproved method log.

The approved subject has no brainshift transformation files and no saved
`desc-reconstruction.mat`. Its existing UI preference is `scrf.do = 0`, with
`reconmethod = 'Manual'`. Keep these preferences unchanged.

Preserve ordinary CT/MRI images, preprocessing results, ordinary coregistration
and normalization transforms, electrode fiducials, Slicer scenes, other processing
logs, and copies outside this subject directory. Use the explicit approved paths;
do not perform a dataset-wide cleanup.

## Computation boundaries

Removing these files makes only the four corrected-image results unavailable.
There is no SCRF reconstruction to remove or propagate in the approved subject.
Do not rerun preprocessing, coregistration, normalization, electrode reconstruction,
or any downstream analysis. No cache fingerprint, configuration, or source-code
change is required.

## Focused verification

Before moving files, record the approved paths and the subject's remaining file
inventory. Afterward, confirm that each approved path is absent from the subject,
its Trash copy exists with the original file size, and every retained subject file
has the same path, size, and modification time. Compare the UI preferences and
electrode/Slicer metadata directly to confirm that they were not rewritten.
Record the restore mapping and verification result outside the patient directory.

## Execution record

The approved cleanup moved four corrected CT images and the brainshift directory
containing its unapproved log to macOS Trash: five files totaling 255,210,272 bytes.
All 164 retained subject files kept their paths, sizes, and modification times.
UI preferences, electrode fiducials, and Slicer metadata were also compared directly
and remained unchanged. `scrf.do = 0` and `reconmethod = 'Manual'` were preserved.
The restore mapping and verification receipt were retained outside the subject.
No source code, configuration, cache fingerprint, or processing stage was changed
or rerun. Verification was limited to this cleanup and the retained subject files.
