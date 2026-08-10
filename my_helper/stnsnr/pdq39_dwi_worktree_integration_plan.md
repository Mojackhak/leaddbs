# PDQ-39 Visualization and DWI Worktree Integration Plan

## Status and scope

This document freezes the contract for consolidating three historical worktree
lines into one integration branch based on the current `stnvop` branch.

The integration baseline is commit
`fa783f674cf345dc706faaa6ee6b939d0908b7dc`.

The source branches are:

- `codex/dwi-mosaic-correction`
- `codex/pdq39-3d-view-export-v1`
- `codex/pdq39-all-connectome-target-v2`

The target branch is `codex/pdq39-dwi-integration`.

The committed history of `codex/pdq39-all-connectome-target-v2` is already an
ancestor of `codex/pdq39-3d-view-export-v1`. It must therefore not be merged a
second time.

## Integration order

1. Merge `codex/dwi-mosaic-correction` into the frozen `stnvop` baseline.
2. Run the focused DWI Python and MATLAB tests.
3. Merge `codex/pdq39-3d-view-export-v1`.
4. Resolve visualization conflicts using the current `stnvop` publication and
   postprocessing contracts as the base.
5. Run focused visualization, publication, and MATLAB smoke tests.
6. Run the relevant combined regression set.
7. Remove the two redundant PDQ-39 linked worktrees only after the integrated
   branch is clean and verified.

## DWI contract

The DWI integration must preserve the source branch behavior for:

- corrected Siemens mosaic reconstruction and orientation handling;
- phase-encoding metadata transformation and candidate QC;
- explicit last-b0 motion and eddy reference handling;
- post-eddy source-order restoration;
- isolated coregistration candidate work roots;
- header-aware BRAINSFit candidate resampling;
- the associated YAML fields, documentation, launchers, and tests.

The DWI changes are independent of the four-model Task 17 scientific fitting
contract and must not change its model-selection, LOOCV, permutation, or
sensitivity semantics.

## PDQ-39 visualization contract

The integrated implementation must retain:

- the 3D camera and view presets;
- the reference lighting contract;
- PDF export and reference font settings;
- target inference derived from the formally published final model;
- raincloud statistical visualization;
- voxel and fiber score mapping through the `vik` colormap;
- anatomy slices rendered independently from the score colormap;
- the prescribed RAS arrow colors without changing the reference arrow style;
- the original, 1 mm FWHM, and 2 mm FWHM display artifacts as distinct
  publication products.

Formal postprocessing must read canonical publication data and must not depend
on `.runs` paths.

The current `stnvop` publication-v2, display-smoothing, portable artifact-index,
and resume contracts take precedence wherever the historical branches differ.

## Excluded uncommitted change

The uncommitted edit in
`codex/pdq39-all-connectome-target-v2` is not part of this integration. It
changes the reference-voxel example to `addon_voxel` while retaining a
reference-voxel filename and duplicates `shg` and `drawnow`.

The complete dirty worktree will be moved to Trash after verification so this
edit remains recoverable without entering the integrated history.

## Conflict policy

The expected PDQ-39 content conflicts are:

- `my_helper/fiber/core/viz/fiber_section_postprocess.py`
- `my_helper/fiber/core/viz/voxel_section_postprocess.py`
- `my_helper/fiber/core/viz/tests/test_fiber_projection.py`
- `my_helper/stnsnr/postprocess_visualization_implementation_plan.md`

Conflict resolution must preserve the current `stnvop` data and publication
contracts while adding the historical branch's missing rendering and export
features. A source-side conflict resolution must not be accepted without a
corresponding test or explicit contract check.

## Verification gates

The integration is complete only when all of the following hold:

- the integrated branch contains both source histories;
- the committed target-v2 history is present through the 3D branch ancestry;
- the worktree is clean;
- focused DWI Python tests pass;
- focused DWI MATLAB tests pass in the `leaddbs` environment;
- focused visualization and publication tests pass;
- the PDQ-39 voxel and fiber example scripts construct valid figure scenes;
- PDF export, fonts, lighting, RAS arrows, colorbars, and anatomy isolation are
  covered by tests or smoke evidence;
- canonical postprocessing remains publication-only;
- no Task 17 scientific model configuration is unintentionally changed.

## Integration regression finding

The first complete dual-frequency regression after the PDQ-39 merge established
that the canonical normative-fiber publication now contains 18 additional
artifacts. These are the nine publication-local target-inference basis
artifacts for each of the reference and add-on fiber roles. The synthetic
canonical-publication fixture must be regenerated to bind the expanded,
self-contained publication tree before the integrated branch can pass the
complete regression.

This fixture update records an intentional publication-contract expansion. It
does not change model fitting, final-model selection, LOOCV, permutation, or
sensitivity calculations.

## Final verification evidence

The integrated branch was verified on 2026-07-24 with the following evidence:

- all three source branches are ancestors of
  `codex/pdq39-dwi-integration`;
- the focused DWI Python suite passed with 2 tests;
- the last-b0 ordering, bottom-to-top mosaic reconstruction, and DWI
  orientation/content MATLAB tests passed;
- the focused visualization suite passed with 57 tests;
- the publication suite passed with 16 tests;
- the complete dual-frequency suite passed with 685 tests and 326 subtests;
- MATLAB Code Analyzer parsed all 51 visualization files; the reported
  findings were deprecation, style, or preallocation advisories rather than
  syntax failures;
- the formal-publication PDQ-39 reference voxel and reference fiber examples
  both constructed valid live figure scenes;
- the reference voxel scene exported both frozen PDF views successfully;
  both files were nonempty, single-page PDF 1.4 documents with embedded Arial
  text;
- the only changed model-adjacent YAML is
  `spatial_result_visualization.yaml`, which controls spatial-result projection,
  display smoothing, labels, and target visualization rather than Task 17
  model fitting.

The real-scene smoke tests required repository-local ignored Lead-DBS data.
The integration worktree reuses the main worktree's `t1.nii`, `segmask.nii`,
and `Custom_STNSNr` atlas without creating divergent copies.

## Worktree retirement

After every verification gate passes:

- move `/private/tmp/leaddbs-3d-view-export-v1` to Trash;
- move `/private/tmp/leaddbs-pdq39-target-v2` to Trash;
- remove their stale linked-worktree registrations;
- retain their Git branch references until the integrated branch has been
  reviewed and merged into `stnvop`.

The final active worktrees for this integration scope are the main `stnvop`
worktree and the stable `codex/pdq39-dwi-integration` worktree.
