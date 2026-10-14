# Mixed-model electrode localization within one subject

## Scope

One subject may contain three or more electrodes with independently selected
models. The supported workflow is electrode setup, Manual or Slicer (Manual)
initial localization, LeGUI import, manual refinement including manual directional
orientation, reconstruction save/load, native/SCRF/template coordinate propagation,
and single-subject display and coordinate export.

In mixed-model mode, directional leads support clockwise/counterclockwise manual
rotation and entry of an absolute native roll angle. DiODe detection is not used
by that mode's orientation controls; conventional bilateral controls retain their
existing detector behavior.

TRAC/CORE, Refined TRAC/CORE, and PaCER are unavailable for this mode. Both the GUI
workflow and processing entry points must reject these methods before running
them. VTA, stimulation parameter editing, and Lead Group are outside this update.
The existing algorithms remain available for conventional homogeneous bilateral
reconstructions.

## Configuration and electrode identity

- Reuse the subject's existing UI preferences file. `elmodels` is a cell array of
  model names indexed by electrode number and exists before the first reconstruction.
- `elnames` stores editable electrode names for named imports. LeGUI label prefixes
  match these names or existing reconstruction names, retaining non-contiguous
  indices in partial imports. Generic default names require a full first import,
  with sorted label prefixes mapped in electrode-index order; ambiguous partial
  imports are rejected instead of being assigned by position.
  Generic names are placeholders and do not replace an existing imported name
  when refinement is accepted.
- Reuse `reco.props(i).elmodel`, `elname`, `labels`, and `manually_corrected` in the
  saved reconstruction. Do not store `Multiple` as a physical electrode model.
- Electrode number is the stable array index shared by properties, markers,
  coordinate cells, and trajectory cells. Selecting a subset or changing display
  order does not renumber electrodes.
- `options.sides` selects electrode indices; `options.elside` selects the electrode
  currently being refined. A scalar `options.elmodel` describes the current
  single-electrode operation. Resolve geometry with the indexed model rather than
  applying that scalar to the whole subject.
- `ea_load_reconstruction` retains its existing six outputs and optionally returns
  the parsed reconstruction as its seventh output. Coordinate, metadata, and
  display consumers reuse that record rather than loading the MAT file again.
- The existing Custom button opens a configuration table with one row per
  electrode. The table persists each model and the selected processing subset.
  Selections above the existing numbered buttons are retained in preferences.

## Reconstruction menu updates

The subject controls support legacy popup menus and App Designer dropdowns exposed
through `UIControlPropertiesConverter`. Before reducing the reconstruction menu
from six methods to Manual, Slicer (Manual), and LeGUI, capture the selected method
name and set the existing menu's numeric `Value` to 1. Then replace `String` and
restore the selection by name. The converter immediately indexes the incoming
items with the current numeric value, so replacing the list while its value is
4, 5, or 6 raises an array-index error during subject loading or renaming.

Manual, Slicer (Manual), and LeGUI retain their selections across menu changes.
An automatic method becomes Manual when mixed-model restrictions apply. Returning
to homogeneous bilateral configuration restores all six methods and maps the
selection by name. Reloading preferences through `ea_getui` must also support the
full-list reset followed by the mixed-model restriction and saved selection.
These menu changes do not invalidate reconstruction, registration, normalization,
or cached computation.

The independent `Specified atlas not found` message means the saved atlas name
is absent from the current space's menu. For example, DISTAL Minimal (Ewert 2017)
is installed in MNI152NLin2009bAsym and is not a D99v2 atlas. Keep this diagnostic
and use an atlas belonging to the intended template space; loading electrode
preferences must not change the template space or substitute a different atlas.

## Geometry, import, and persistence

Resolve each electrode with the existing model specification and template. Its
contact count, spacing, fiducial geometry, diameter, and directional attributes
must come from that model. Slicer imports match `Head_i` and `Tail_i` labels to the
configured electrode index, independent of file row order or subset selection.
Validate the file's labels, coordinates, coordinate-system declaration, and
required pairs once at this parsing boundary.
When a model changes, obsolete contact labels on that electrode are cleared;
other electrodes' labels are preserved. Single-subject slice views use each
electrode's own contact count and coordinates rather than bilateral offsets.
Horizontal trajectories are valid. When the anterior reference frame is singular,
use an orthogonal horizontal reference rather than generating zero-length markers.

LeGUI import must preserve the original source files and contact labels, use the
configured or explicitly selected model, and produce the standard coordinate and
trajectory cell arrays. Match fiducials to the selected template's definitions;
do not assume that every model's tail is the fourth contact. Preserve imported
contact locations until a user explicitly refines or changes that electrode's
geometry. Use declared source coordinates and the existing Lead-DBS transforms;
never substitute native points for template coordinates or treat a projected
surface coordinate array as a brain-shift transform.

The external `ea_import_LeGUI` entry point imports electrode coordinates into an
existing Lead-DBS subject; it does not replace that subject's images or transforms.
Its `space` argument selects unprojected `ElecXYZRaw` (native) or `ElecXYZMNIRaw`
(the declared current template space). Internal LeGUI conversion uses native
coordinates. Explicit configured models take precedence over model guessing;
unconfigured imports request a model selection in interactive MATLAB and require
models in noninteractive execution.

Save by merging the selected electrodes into the existing reconstruction. Preserve
other electrodes, labels, correction flags, and orientation metadata. Refinement
completion must not broadcast one model or correction flag to the other
electrodes. Reopening and recalculating must retain every indexed model.
Manual edits are saved in native space while refinement is open. Finish propagates
the electrodes whose geometry changed in one call, preserving unchanged electrodes
and avoiding a template-space mapping on every key press.

## Coordinate propagation and display

Reuse the existing native-to-SCRF and native-to-template transforms. Apply them to
the selected electrodes' coordinates and fiducials, and rebuild trajectory and
orientation marker geometry with each electrode's own specification. Preserve
unselected entries in every coordinate space.

Single-subject rendering uses the indexed model, actual contact count, and labels
for each electrode. Changing the selected electrode refreshes its model, contact
graphics, and directional controls. Render imported contacts using their stored
locations until explicitly edited. Export contact coordinates with electrode and
contact identity preserved.

## Recalculation boundaries

- Changing a model or fiducials affects that electrode's geometry, propagated
  coordinates, and dependent display/export results.
- Geometry comparisons read only head, tail, x, and y coordinates plus the model;
  unrelated marker metadata does not trigger geometry generation. Angle updates
  are limited to changed electrodes, or the selected coordinate-propagation scope.
- Existing St. Jude-to-Abbott model-name normalization is applied per electrode.
  Equivalent model names and row/column serialization of configuration vectors
  do not constitute a geometry change.
- Changing a label or processing selection does not recalculate geometry.
- Configuration formatting and serialization changes do not invalidate results.
  There is no configuration-file hash or global recomputation switch.
- Changing a shared registration or normalization transform affects all electrode
  coordinates that use it, because those coordinates share that transform.
- Electrode changes do not rerun image preprocessing, registration, normalization,
  or unrelated reconstructions.

## Focused validation

Use synthetic reconstructions and existing model templates to verify:

1. Three different models with different contact counts and a directional model.
2. Configuration persistence before initial reconstruction and after reopening,
   including a selection above the existing numbered buttons.
3. Slicer label matching with shuffled rows and a non-contiguous electrode subset.
4. LeGUI contact/model/label preservation and the standard trajectory cell type.
5. Single-electrode refinement and save preserving every unselected electrode.
6. Native/SCRF/template propagation with known transforms and individual diameters.
7. Single-subject rendering and coordinate export retaining model/contact identity.
8. Rejection of unsupported automatic methods in this mode.
9. Existing homogeneous bilateral localization and display regressions.
10. App Designer reconstruction-menu restriction, selection preservation, expansion,
    and repeated preference reloads, including an unavailable-atlas diagnostic.

Record executed checks and their limits below after implementation. Synthetic
transform checks do not constitute clinical image-registration validation.

## Operation

1. Select one existing Lead-DBS subject and open Custom. Set the electrode count,
   indexed names, individual models, and processing selection, then Apply. Image
   preparation, coregistration, and normalization must already be available when
   running the complete coordinate-propagation workflow.
2. Choose Manual or Slicer (Manual) for initial localization. Slicer pairs retain
   their `Head_i` and `Tail_i` labels even when only a subset is processed.
3. For LeGUI import, use names matching the channel-label prefixes (for example,
   `A` for `A1` through `A12`). The imported contact count must match its selected
   model. External imports declare native or the subject's current template space
   and retain the subject's existing images and transforms.
4. Open manual refinement, use the next/previous controls or Space to accept and
   advance, and use `m` to edit the current electrode's head/tail coordinates.
   Directional controls adjust the current lead's native roll angle.
5. Finish saves the edited native geometry and propagates only changed electrodes.
   Reopen the subject to display individual models or export contact coordinates.

## Validation record

- MATLAB R2024b under Conda `leaddbs`: all 30 runtime tests in
  `tests/test_mixed_model_localization.m` passed. This includes real model templates,
  the Custom table with 16 indexed entries, Manual initial localization, shuffled
  Slicer/LPS pairs, native and template LeGUI import, refinement and manual
  directional controls, save/reopen, scoped angle updates, synthetic SCRF/template
  propagation, homogeneous bilateral behavior, equivalent configuration values,
  three-model rendering, and 36 third-electrode slice images.
- The three existing Python tests in
  `tests/test_manual_reconstruction_display_refresh.py` passed in Conda `leaddbs`.
- Visually inspected the configuration table, refinement view, three-model scene,
  and synthetic slice output. `git diff --check` passed.
- Tests use synthetic subjects/MRI volumes, controlled SPM point-selection inputs,
  and a stand-in for nonlinear image mapping with a known affine transform. They
  verify indexing, geometry, preservation, propagation, and rendered output;
  they do not validate clinical registration accuracy or a live 3D Slicer session.
- The initial synthetic localization validation did not modify a patient dataset.
  No VTA or Lead Group functionality was added.
- Whole-subject propagation remains available through the explicit Recalculate
  command and when a shared transform changes, since those operations intentionally
  affect every electrode using that transform. Normal edits remain electrode scoped.

Run the focused checks from the repository root:

```sh
conda run --no-capture-output -n leaddbs matlab -batch "results=runtests('tests/test_electrode_model_menu.m'); assertSuccess(results);"
conda run --no-capture-output -n leaddbs matlab -batch "results=runtests('tests/test_mixed_model_localization.m'); assertSuccess(results);"
conda run --no-capture-output -n leaddbs python -m unittest discover -s tests -p 'test_manual_reconstruction_display_refresh.py'
```

The four tests in `tests/test_electrode_model_menu.m` reproduced the reported
`UicontrolConversionUtils.convertString` array-index error before the fix and
passed after the index reset in MATLAB R2024b Update 5 under Conda `leaddbs`.
They use real App Designer dropdown converters and synthetic UI preferences to
verify all six starting selections, mixed-model and three-electrode restrictions,
homogeneous-menu restoration, repeated preference reloads, and the independent
unavailable-atlas diagnostic. The existing 30-test localization suite was not
rerun for this menu-only fix. Whitespace checks passed for the changed files.

After an occurrence of this exception, reopen Lead-DBS before loading the subject
again: the converter has already changed its underlying legacy control's `String`
when it throws, which can leave the existing window's selection out of range.
The fix prevents this intermediate state on subsequent loads with fresh controls.

## Reconstruction preference serialization and rename verification

`reconmethod` represents one selected method name, not the dropdown's item list.
At the UI-preference boundary, a scalar cell or string name is equivalent to a
character-vector name. A list containing multiple names has no recorded selection;
report that malformed value and retain the current valid UI selection rather
than comparing it element by element with the menu. A user-confirmed field
correction can restore the intended single name without changing other preferences.

When collecting UI options, extract the selected name into the output only after
indexing succeeds. If the existing optional-control handling skips an unavailable
or invalid selection, it must not leave the complete menu assigned to `reconmethod`.
Full patient loading must preserve the restored method across the modality-menu
update when that method remains available. Explicit MR/CT changes retain the
existing modality-default behavior.

The live rename verification uses the native `ea_rename_pts` and `ea_load_pts`
path, preserves original overwritten metadata in Trash, and verifies the renamed
subject across derivatives, rawdata, sourcedata, raw-image references, the selected
UI row, and the saved scalar reconstruction method. The confirmed correction for
this request is Manual. Renaming updates identifiers and paths only; it does not
invalidate or rerun image preprocessing, coregistration, normalization, or electrode
geometry. The existing rename routine scans the BIDS dataset to locate files with
the exact old subject prefix; this search remains necessary for its dataset-wide
identifier contract and is not a computation or cache-invalidation operation.

### Executed preference and live rename checks

- All eight focused menu/preference tests passed in MATLAB R2024b Update 5 through
  the installed MATLAB Engine API under Conda `leaddbs`. The three added failure
  checks reproduced the original size mismatch, partial menu-list serialization,
  and unwanted modality-default reset before their fixes.
- A user-requested existing subject was renamed with native `ea_rename_pts` and
  loaded twice with native `ea_load_pts` in the real Lead-DBS App Designer app.
  Both loads completed without errors, the selected UI row matched the final ID,
  and the selected and saved reconstruction method was Manual. The exported app
  image was inspected for the patient ID, selected method, and atlas/space controls.
- All 168 subject files were accounted for across derivatives, rawdata, and
  sourcedata. The 166 files outside the two intentionally changed metadata files
  retained their sizes. The old subject folders were absent, and raw-image index
  values differed only by the requested subject-prefix replacement.
- MATLAB semantic comparison confirmed that every original UI preference except
  the user-confirmed `reconmethod` correction was preserved. Original UI preferences
  and the raw-image index were moved to Trash before working copies were changed.
  Lead-DBS application preferences and recent-list writes for the test were isolated
  in a temporary directory.
- No image preprocessing, registration, normalization, electrode reconstruction,
  or global cache invalidation was run. The original dataset-wide filename search
  remains solely to find the exact old subject prefix during a native BIDS rename.
  Focused whitespace checks passed; the broader localization suite was not rerun.
