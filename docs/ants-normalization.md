# ANTs normalization

Lead-DBS may find existing transforms when a normalization is recomputed. This
decision is handled by the shared cross-method refinement layer documented in
`docs/normalization-refine.md`. ANTs runs launched from the normalization entry
point do not show their legacy method-local existing-transform prompt.

When ANTs is invoked directly outside the shared normalization entry point and
chooses to refine an existing transform, the initial forward and inverse
transforms must each resolve to exactly one file path before building the
`antsRegistration --initial-moving-transform` command.

The transformation directory can contain both affine `.mat` files and nonlinear
`.nii.gz` displacement fields with the same BIDS transform direction. If both
are present, the nonlinear displacement field is the preferred initial
transform for a nonlinear refinement. Falling back to the affine `.mat` file is
valid only when no nonlinear displacement field is available.

When switching from another normalization method, choose `Start from scratch` in
the shared normalization refinement prompt if the intended result should be a
pure ANTs run rather than a refinement of the previous transform.

ANTs presets are present in two parameter schemas. Legacy Lead-DBS presets
define top-level metric and convergence fields, while ANTs-default presets
define stage-specific `rigid`, `affine`, and `syn` structures. Normalization
code must accept both schemas. If a stage-specific preset does not define a
separate subcortical-refinement stage, the SyN stage parameters are reused for
that refinement.
