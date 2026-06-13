# Check-results workflow

The check-results pass may be run for subjects that only have preoperative
images. In that configuration `BIDSFetcher` sets `subj.postopModality` to
`'None'` and does not create `subj.brainshift`, because subcortical refinement
is only defined for postoperative anatomy.

Code paths that reopen check-registration figures must therefore treat
brainshift/SCRF data as optional. They may regenerate coregistration and
normalization check images without attempting to inspect or rerun SCRF unless
`subj.brainshift.anat.scrf` and the related transform fields are present.
