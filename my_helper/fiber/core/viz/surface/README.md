# Lead-DBS Surface Rendering Helpers

This directory is migrated from `/Users/mojackhu/Github/MyLFP/src/viz/surface`
for repository-local use by the dual-frequency postprocess layer. Runtime code
must not import or add the MyLFP checkout to the MATLAB path.

The `render/` functions provide NIfTI-to-surface conversion, `ea_mnifigure`
rendering, camera capture/application, RAS orientation markers, transparent
export, and spin export. The `batch/` and `batch_helper/` functions retain the
generic batch renderer.

The MyLFP `demo/demo_render.m` script is intentionally not copied because it
hard-codes a separate historical research root, feature name, atlas load, and
video target. The repository-local PDQ-39 examples below replace that
project-specific demo while reusing the byte-identical generic helpers.

`ea_export_figure_transparent.m` is retained byte-for-byte from the MyLFP
source. The project scene wrapper exposes its mixed PDF mode so 3D anatomy and
model objects are rasterized without vector seams while the colorbar and its
Arial text remain vector output. Statistical `vik` colormaps never apply to
the anatomy slices; voxel anatomy is frozen as grayscale truecolor, and the
fiber score colorbar uses a dedicated axes.

`../mh_viz_make_sweet_sour_scene.m` is the project-independent entry point for
combined sweet/sour voxel and fiber scenes. Recursive repository path setup is
required so the entry point can resolve this directory.

## Interactive PDQ-39 examples

Four MATLAB scripts under `../examples/` demonstrate the completed PDQ-39
reference and add-on final models from the Task 17 main run:

- `open_pdq39_reference_voxel_scene.m` opens the benefit-oriented direct-voxel
  1 mm FWHM display derivative with symmetric `vik` colors and grayscale
  anatomy slices. Before surface extraction, the finite-support crop is
  resampled to a retained isotropic 0.1 mm display NIfTI under
  `visualization/spatial_2d/maps/` by
  finite-mask-normalized interpolation with signed-distance support
  preservation. The crop retains one source voxel of background as a working
  halo for interpolation and boundary reconstruction; the halo never becomes
  the rendered finite support. The renderer keeps the migrated `insideOnly`
  color-sampling contract at a depth of 0.25 mm. The add-on voxel example and
  formal reference/add-on PDF exporter use the same retained display input and
  sampling depth. It also enables the configurable
  `Custom_STNSNr` atlas by default and draws only ROI 2, the STN, as a
  50%-reduced atlas-colored wireframe with edge alpha 0.15. The interactive figure applies
  the configurable scene background immediately after creation and defaults to
  white. Its colorbar uses `Benefit-oriented partial Spearman ρ with
  {scale_display_name}`, resolving the scale label from the formal publication.
- `open_pdq39_reference_fiber_scene.m` opens the selected sweet and sour PPMI
  fibers with one `vik` color per full-sample benefit-oriented weight and the
  same publication-resolved semantic colorbar label. It displays only
  `Custom_STNSNr` ROI 2, the STN.
- `open_pdq39_addon_voxel_scene.m` and
  `open_pdq39_addon_fiber_scene.m` provide the corresponding add-on models and
  display only `Custom_STNSNr` ROI 1, the SNr.

The reference scripts apply the first frozen STN camera view and the add-on
scripts apply the first frozen SNr camera view before the interactive window is
shown. Both camera families use an orthographic projection and an explicit
superior camera-up vector. Explicit scene views are applied identically to
voxel and fiber scenes.

All four scripts resolve the unique completed `FinalSelectionRecord` by scale and
model family. They do not hard-code a task identifier, tau, Coverage, artifact
producer, or selected feature axis. A repository-local Python preparation
helper reads the immutable final artifacts and creates one fixed display-input
directory per scale and model family under the system temporary directory.
`manifest.json` and the last-written `complete.json` are the resume pair; an
existing pair is reused by path without reopening the publication. The voxel
helper restores selected parent-axis positions to their canonical brainmask
voxels. The fiber helper resolves selected sweet and sour canonical IDs against
the model's valid-fiber axis and reads only those geometries from the formal
connectome. Every consumed final array is checked against its recorded
SHA-256 during an actual build. Explicit `Force` moves the previous input
directory to Trash after validating the requested source, then rebuilds it.

The MATLAB entry scripts intentionally leave `OutputFig`, `OutputImage`,
`OutputPdf`, and `OutputSpin` empty. Running either script creates one visible,
interactive `ea_mnifigure` window and leaves it open. It does not save a FIG,
PDF, image, or spin export. The returned scene remains available in the base
workspace as `pdq39VoxelScene` or `pdq39FiberScene`.

## Configurable model-role PDF views

`mh_viz_default_model_views()` provides two frozen camera views under each of
the fields `reference` and `addon` for voxel export. The names intentionally
describe model roles rather than the STN and SNr anatomy used to initialize
the cameras.

Export an existing scene with:

```matlab
views = mh_viz_default_model_views();
exports = mh_viz_export_scene_views(scene, outputDirectory, 'reference', ...
    'Views', views, 'FilePrefix', 'pdq39_voxel');
```

Generate all four PDQ-39 voxel PDFs without opening a visible figure:

```matlab
exports = mh_viz_export_pdq39_voxel_pdfs(outputDirectory);
```

The silent entry point creates the reference and add-on scenes with
the same strict-headless settings as MyLFP `surface_med.m`:
`FigureVisible='off'`, `FigureBackend='matlab'`, and
`StrictHeadless=true`. The hidden-figure default remains active for the full
scene-build and export operation so an implicit graphics call cannot create a
visible intermediate window. Formal detached batch export must also start
MATLAB with `-nodisplay`; `-batch` alone does not satisfy the no-window
operational contract on macOS. The entry point creates no Elvis viewer window,
verifies that each native MATLAB figure remains hidden, exports two views per
role, and closes every internal figure on success or failure. The
`open_pdq39_*_voxel_scene.m` examples remain intentionally interactive.

The corresponding PDQ-39 categorical fiber export uses every published
candidate fiber. Unselected candidates are drawn in opaque `#CCCCCC`,
selected sweet fibers in opaque `#F2000E`, and selected sour fibers in opaque
`#0E6AAF`. Full-sample scores remain provenance data and do not drive the
categorical colors. The export must not use the Lead-DBS 1,000-fiber display
ceiling. Its discrete legend uses colored horizontal line samples and white
text on the black fiber-scene background.

The formal categorical renderer draws all three fiber roles as continuous path
lines. Candidate lines use 0.25-point width and selected sweet/sour lines use
0.50-point width. Line mode does not subsample fiber points or reduce a tube
mesh, which preserves smooth trajectories at high zoom. The previous
`streamtube` representation remains available through the explicit
`SelectedFiberRenderMode='tube'` setting for interactive use, but it is not the
formal default. Candidate opacity is 1.0. Categorical fiber axes use
`SortMethod='childorder'`: the candidate layer is placed behind the selected
layers, while opaque sweet and sour layers are moved to the foreground so
candidate lines cannot cover either selected class.

```matlab
exports = mh_viz_export_pdq39_fiber_pdfs(outputDirectory);
```

An additional coefficient-colored PDQ-39 fiber view is available without
replacing the categorical view. It renders every published candidate fiber as
a continuous 0.25-point path and assigns its color from the aligned
full-sample benefit-oriented fiber coefficient. The mapping uses the 256-sample
`vik` colormap on an independent symmetric range centered on zero, with the
limit derived from the largest absolute candidate-fiber coefficient in that
model. This view performs no fiber or point sampling. It omits the
Candidate/Sweet/Sour count legend and instead displays the publication-resolved
right-side coefficient colorbar with white ticks and a white Arial label on
the black scene background. Anatomy remains grayscale truecolor and is not
affected by the fiber colormap. During PDF composition, a long vertical
colorbar label keeps its full semantic text and is reduced only as needed,
with a 12-point lower bound, so the label remains inside the page.

```matlab
exports = mh_viz_export_pdq39_fiber_coefficient_pdfs(outputDirectory);
```

The visible interactive entry points are
`open_pdq39_reference_fiber_coefficient_scene.m` and
`open_pdq39_addon_fiber_coefficient_scene.m`. The original categorical
examples and exporter remain unchanged and available.

This coefficient-colored scene is the frozen continuous-coefficient 3-D fiber
visualization contract. Future changes must preserve the complete candidate
axis, unsampled path geometry, 0.25-point opaque lines, model-specific
symmetric zero-centered `vik` limits, grayscale truecolor anatomy, black
background, white colorbar typography, the single frozen fiber camera, and the
absence of a Candidate/Sweet/Sour count legend. The categorical visualization
remains a separate frozen view and must not be replaced by this contract.

`mh_viz_default_fiber_views()` supplies one default camera view for each model
role:

```text
az        0
el        0
camva     3.8
camup     [0 0 1]
camproj   orthographic
camtarget [9.8538 -48.8761 9.6955]
campos    [1884.6 -48.8761 9.6955]
```

This entry point uses the same strict-headless contract as the voxel exporter,
closes all internal figures, and writes one default view for each model role.
The general view exporter still accepts any nonempty role-specific cell array,
so callers can explicitly request multiple fiber views. The interactive
`open_pdq39_*_fiber_scene.m` examples use the same categorical layers and
single default view but remain intentionally visible.

Fiber scenes use a black background and omit the RAS orientation triad by
default. `AddRASTriad=true` remains supported for an explicit interactive or
export request. The default fiber anatomy backdrop is
`/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/backdrops/7T_100um_Edlow_2019.nii`.
Only the sagittal x-plane at MNI `x=5 mm` is shown, with the Lead-DBS
transparency setting at 100, equivalent to an opaque slice. The scalar anatomy
is converted to RGB before statistical colors are applied.

The general exporter refuses implicit replacement and preserves the current
scene after export. Before each export it reapplies every native MATLAB camera
property and verifies the projection, view angle, up vector, target, and
position. A reference export requires and displays only `Custom_STNSNr` ROI 2;
an add-on export requires and displays only ROI 1. Missing role-specific
anatomy or a camera mismatch aborts the export. Every requested view receives
the frozen camera-aligned three-light preset
after the camera is applied: Cam is the 0.98 key, Left is the 0.14 fill,
Ceiling is the 0.08 top light, and Right remains off. All three active lights
are neutral white. Gouraud lighting uses ambient strength 0.78, diffuse
strength 0.22, specular strength 0.12, specular exponent 24, and specular
color reflectance 0.20. The preset is applied to the same complete patch and
surface set controlled by the native lighting panel, so the first slider
interaction cannot cause an implicit material jump. Anatomy RGB `CData`,
direct color mapping, voxel values, fiber scores, and the statistical `vik`
colormap remain unchanged. The voxel exporter continues to hide anatomy slices
and use a white background. The fiber exporter explicitly includes its x-plane
anatomy slice and uses an opaque black background. Custom views use the same
structure and may replace either role cell array.

For categorical fiber PDFs, mixed export captures anatomy, atlas, and all fiber
paths together from the original MATLAB 3D axes. The exporter must not project
fiber vertices into a separate page-coordinate overlay because that breaks the
native plot-box transform and can displace fibers relative to anatomy. The
single aligned scene layer is rasterized at 600 DPI after the formal camera is
reapplied. Before capture, the axes remains in `childorder` mode with candidate
fibers behind sweet and sour fibers. Continuous path rendering avoids the
previous streamtube tiling artifact, while the 600 DPI scene layer preserves
sharp trajectories. The discrete legend is hidden during scene capture and
redrawn as vector horizontal lines and white Arial labels in its original
layout slot.
