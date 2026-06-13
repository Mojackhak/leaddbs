# ANTs normalization

Lead-DBS may find existing ANTs transforms when a normalization is recomputed.
When the user chooses to refine an existing transform, the initial forward and
inverse transforms must each resolve to exactly one file path before building
the `antsRegistration --initial-moving-transform` command.

The transformation directory can contain both affine `.mat` files and nonlinear
`.nii.gz` displacement fields with the same BIDS transform direction. If both
are present, the nonlinear displacement field is the preferred initial
transform for a nonlinear refinement. Falling back to the affine `.mat` file is
valid only when no nonlinear displacement field is available.

When switching from another normalization method that writes ANTs-compatible
`desc-ants.nii.gz` files, choose "Start from scratch" in the existing-transform
prompt if the intended result should be a pure ANTs run rather than a refinement
of the previous transform.
