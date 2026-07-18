# Lead-DBS Surface Rendering Helpers

This directory is migrated from `/Users/mojackhu/Github/MyLFP/src/viz/surface`
for repository-local use by the dual-frequency postprocess layer. Runtime code
must not import or add the MyLFP checkout to the MATLAB path.

The `render/` functions provide NIfTI-to-surface conversion, `ea_mnifigure`
rendering, camera capture/application, RAS orientation markers, transparent
export, and spin export. The `batch/` and `batch_helper/` functions retain the
generic batch renderer.

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

Two MATLAB scripts under `../examples/` demonstrate the completed PDQ-39
reference final models from the Task 17 main run:

- `open_pdq39_reference_voxel_scene.m` opens the benefit-oriented direct-voxel
  surface with symmetric `vik` colors and grayscale anatomy slices.
- `open_pdq39_reference_fiber_scene.m` opens the selected sweet and sour PPMI
  fibers with one `vik` color per full-sample benefit-oriented weight.

Both scripts resolve the unique completed `FinalSelectionRecord` by scale and
model family. They do not hard-code a task identifier, tau, Coverage, artifact
producer, or selected feature axis. A repository-local Python preparation
helper reads the immutable final artifacts and creates request-addressed
display inputs under the system temporary directory. The voxel helper restores
selected parent-axis positions to their canonical brainmask voxels. The fiber
helper resolves selected sweet and sour canonical IDs against the model's
valid-fiber axis and reads only those geometries from the formal connectome.
Every consumed final array is checked against its recorded SHA-256 before use;
the temporary-cache request also includes the local brainmask or connectome
file signature so changed geometry cannot reuse a stale display input.

The MATLAB entry scripts intentionally leave `OutputFig`, `OutputImage`,
`OutputPdf`, and `OutputSpin` empty. Running either script creates one visible,
interactive `ea_mnifigure` window and leaves it open. It does not save a FIG,
PDF, image, or spin export. The returned scene remains available in the base
workspace as `pdq39VoxelScene` or `pdq39FiberScene`.
