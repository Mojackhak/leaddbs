# Lead-DBS Surface Rendering Helpers

This directory is migrated from `/Users/mojackhu/Github/MyLFP/src/viz/surface`
for repository-local use by the dual-frequency postprocess layer. Runtime code
must not import or add the MyLFP checkout to the MATLAB path.

The `render/` functions provide NIfTI-to-surface conversion, `ea_mnifigure`
rendering, camera capture/application, RAS orientation markers, transparent
export, and spin export. The `batch/` and `batch_helper/` functions retain the
generic batch renderer.

`../mh_viz_make_sweet_sour_scene.m` is the project-independent entry point for
combined sweet/sour voxel and fiber scenes. Recursive repository path setup is
required so the entry point can resolve this directory.
