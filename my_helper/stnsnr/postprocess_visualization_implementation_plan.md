# Task 17 Postprocess Visualization Implementation Plan

## Status

Implemented on 2026-07-18. This document is the implementation contract for the
postprocess visualization layer that consumes completed dual-frequency final
model records without rerunning model fitting, permutation, bootstrap, jitter,
or OSS-DBS. Cohort-wide rendering from the formal Task 17 run has not started;
the next integration step is a run-store adapter that resolves the completed
artifacts into the explicit manifest described below.

## Goal

Add one reusable visualization package under
`my_helper/fiber/core/viz/` with two output families:

1. sweet/sour spatial visualization for direct-voxel and normative-fiber final
   models;
2. paired in-sample and LOOCV statistical-fit visualization with the final
   model parameters and inference statistics shown on the figure.

The package must preserve the distinction between voxel and fiber models.
Voxel model values live on a canonical voxel axis. Fiber model values live on
a canonical connectome fiber axis. A fiber result may be projected to a density
NIfTI for display, but that projection remains a visualization derivative and
does not become a voxel model.

## Source Implementations

The migration uses these local implementations as references:

- `/Users/mojackhu/Github/MyLFP/src/viz/surface/` for MATLAB surface rendering
  based on `ea_mnifigure()`;
- `/Users/mojackhu/Github/MyLFP/src/viz/visualdf.py` function
  `plot_triple_interaction_nifti` for MNI-space 2D section sampling and
  Boxsize-driven layout;
- `/Users/mojackhu/Github/MyLFP/src/viz/visualdf.py` functions
  `plot_triple_interaction_fit`, `plot_double_interaction_fit`, and
  `plot_single_effect_fit` for fit lines, confidence bands, faceting, style,
  and parameter annotations.

The migrated code must be self-contained in this repository. Runtime imports
from the MyLFP checkout are forbidden.

## Package Layout

```text
my_helper/fiber/core/viz/
  __init__.py
  layout.py
  spatial.py
  model_fit.py
  postprocess.py
  surface/
    batch/
    batch_helper/
    render/
  tests/
  mh_fiber_*.m
  mh_viz_*.m
```

The existing `my_helper/fiber/core/visualization/` MATLAB functions move into
`my_helper/fiber/core/viz/`. Their public function names remain unchanged, so
recursive MATLAB path users do not require call-site changes. The old directory
must be absent after the migration.

## Input Contract

### Endpoint identity

Every visualization request identifies one completed final endpoint through:

```text
endpoint_id
scale_id
model_family
final_model_id
selected_tau
selected_coverage
final_branch
```

These values are read from the final record. Plotting code must not substitute
the nominal primary tau or Coverage when a final endpoint selected a fallback
cell.

### Voxel spatial input

A direct-voxel visualization item contains:

```text
canonical reference NIfTI
canonical voxel IDs or a complete voxel-to-grid mapping
full-sample benefit-oriented weights
full-sample valid/support mask
sweet selection mask or IDs
sour selection mask or IDs
bootstrap positive/negative selection frequency when available
```

The postprocessor restores model vectors to the canonical NIfTI grid.
Non-covered and non-modelled voxels are written as `NaN`. Coverage maps and
binary masks may use zero outside their support.

The primary 3D voxel source is the restored signed full-sample weight NIfTI.
Its surface rendering uses the migrated MyLFP `default_nifti2patch_config` and
`default_plot_patch_config` contracts: mask geometry, inside-only scalar
sampling, the `vik` diverging colormap, symmetric color limits, gray missing
data, the reference texture-lighting profile, and a right-side colorbar at the
reference position. Sweet and sour binary NIfTIs remain optional selection-mask
overlays; they do not replace the signed heatmap or its colorbar.
The `vik` colormap applies only to the statistical voxel surface. Anatomy
slices are frozen as grayscale truecolor textures and therefore remain
independent of the statistical axes colormap and color limits.

### Fiber spatial input

A normative-fiber visualization item contains:

```text
connectome identity and declared geometry source
canonical fiber IDs
full-sample benefit-oriented weights
sweet selected fiber IDs
sour selected fiber IDs
bootstrap selection frequencies when available
```

The 3D renderer consumes geometry resolved from the declared connectome and
colors each fiber from its signed full-sample score. Its resolved MAT input
contains concatenated Lead-DBS `fibers`, one point-count entry in `idx` per
fiber, and one finite-or-NaN `scores` entry per fiber in exactly the same order.
Finite scores use `vik` with symmetric limits around zero, so positive sweet
and negative sour effects share one scale and zero maps to the neutral center.
The fiber colorbar reports that score scale. The 2D renderer consumes derived
sweet and sour fiber-density NIfTIs generated on an explicit reference grid.
The density NIfTIs must retain connectome identity, selected fiber ID hash,
reference-grid identity, and density normalization in their sidecar metadata.
They are display derivatives only.

Canonical fiber IDs are resolved to explicit tractogram streamline indices by
the caller before density generation. The rendering helper does not infer that
a canonical fiber ID is a zero-based or one-based tractogram row number.

### Statistical-fit input

The plotting API accepts one tidy subject table with these required columns:

```text
subject_id
outcome
in_sample_prediction
loocv_prediction
```

It accepts a separate endpoint summary mapping containing the final model key
and reported metrics. This separates plotting from the current run-store JSON
layout and permits future report schema changes without changing the rendering
primitive.

Required annotations include:

```text
selected tau
selected Coverage
final branch
finite subject count
Spearman rho
Spearman nominal p
formal permutation p
model-family BH q
all-endpoint BH q
Pearson r and nominal p
RMSE and MAE
in-sample standard R2
in-sample relative R2
LOOCV R2 and Q2
optimism gaps when finite
```

Adjusted R2 is not reported because the fitted spatial model has no single
stable degrees-of-freedom count.

## Rendering Contract

### Boxsize geometry

`boxsize` is the inner plotting area of each panel in millimetres. Figure size
is derived from panel count, Boxsize, absolute panel gaps, strip sizes, global
labels, legends, and colorbars. DPI changes raster density but must not change
the physical panel geometry.

The layout implementation is shared by 2D spatial plots and statistical-fit
plots. It validates positive finite Boxsize dimensions and exposes exact panel
positions for testing.

### 2D sweet/sour sections

The Python renderer:

- canonicalizes NIfTI images to RAS orientation;
- samples axial, coronal, and sagittal sections in MNI millimetres;
- uses nearest-neighbour sampling for binary masks and linear sampling for
  continuous maps;
- shows anatomy first, sweet/sour layers second, and optional atlas outlines
  last;
- uses one shared world-coordinate span and equal spatial aspect across panels;
- supports explicit slice coordinates and deterministic percent-of-support
  slices;
- uses stable sweet and sour colors with independent alpha;
- reports scale, plane, and MNI coordinate in panel strips;
- supports PNG, PDF, and SVG through Matplotlib.

### 3D sweet/sour scene

The MATLAB renderer:

- creates the base viewer with `ea_mnifigure()`;
- renders the signed voxel NIfTI through the migrated MyLFP heatmap pipeline
  with symmetric `vik` colors and the reference right-side colorbar;
- may render voxel sweet/sour binary NIfTIs as separate optional overlays;
- renders resolved fiber geometry with one full-sample score per fiber and maps
  those scores through a symmetric `vik` scale instead of fixed sweet/sour
  colors;
- shows a right-side fiber-score colorbar when the scene is fiber-only;
- colors the R, A, and S orientation arrows with `#F2000E`, `#0E6AAF`, and
  `#0CA228`, respectively, while all geometry, head size, line width, label,
  location, camera-following, and inset-axis settings come unchanged from the
  migrated MyLFP `default_plot_patch_config` and `ea_add_ras_triad` code;
- retains Lead-DBS anatomy, camera, atlas, RAS orientation, transparent export,
  and spin-export helpers from the migrated MyLFP surface code;
- exports PNG and PDF through the repository-local migrated
  `ea_export_figure_transparent` module; PDF uses that module's `mixed` mode so
  the 3D scene is rasterized without vector surface seams while the colorbar
  and its text remain vector objects; Greek-symbol handling, base font,
  fallback fonts, colorbar font sizes, and text interpreters come from the
  migrated MyLFP `default_plot_patch_config` contract;
- assigns stable tags and user data so sweet, sour, voxel, fiber, and anatomy
  objects remain independently controllable;
- exports a `.fig` scene plus requested static views.

### In-sample and LOOCV fit plot

The Python renderer creates paired panels with shared limits:

- observed outcome on the vertical axis;
- fitted in-sample or held-out LOOCV prediction on the horizontal axis;
- subject points;
- ordinary least-squares display line with a 95 percent confidence band when
  the input is estimable;
- optional identity line;
- one annotation block per panel containing the corresponding metrics;
- one figure-level block containing model family, scale, final tau, Coverage,
  final branch, and candidate-axis identity.

The fit line is descriptive. Formal inference remains the stored permutation
p and BH q; the renderer must not reinterpret the line's slope p as the model's
formal p.

## Output Contract

```text
postprocess/
  manifest.json
  endpoints/<endpoint_id>/
    spatial/
      voxel/
        sweet.nii.gz
        sour.nii.gz
        signed_weight.nii.gz
        stability.nii.gz
        sections.png
        sections.pdf
        scene.fig
        scene.png
        scene.pdf
      fiber/
        sweet_fibers.mat
        sour_fibers.mat
        sweet_density.nii.gz
        sour_density.nii.gz
        sections.png
        sections.pdf
        scene.fig
        scene.png
        scene.pdf
      spatial_manifest.json
    statistics/
      predictions.csv
      in_sample_loocv_fit.png
      in_sample_loocv_fit.pdf
      fit_manifest.json
```

Each manifest records source artifact URIs, source hashes already present in the
run, selected model key, plotting parameters, output paths, completion status,
and errors. Postprocessing never changes the parent run manifest or marks a
scientific task complete.

## Resume And Failure Boundaries

Postprocess resume is output-local. A completed item is reusable when its
manifest contains the same source artifact identities, endpoint final model
key, and rendering configuration, and all declared outputs exist. Repository
code identity is not a resume gate.

Failure to resolve fiber geometry must fail only the fiber spatial item. It must
not block voxel plots or statistical-fit plots. A missing optional anatomy or
atlas overlay produces a warning and remains explicit in the manifest.

## Validation

Automated validation must cover:

- exact Boxsize panel geometry within floating-point tolerance;
- deterministic slice selection and canonical RAS orientation;
- correct sweet/sour layer order and colors;
- no conversion of fiber statistical units into voxel statistical units;
- paired in-sample and LOOCV panels from one subject table;
- annotation values copied from the endpoint summary without recomputation;
- finite-data filtering and degenerate-fit behavior;
- unchanged public MATLAB function discovery after moving
  `core/visualization/` into `core/viz/`;
- Python imports without MATLAB or Lead-DBS initialization;
- a synthetic NIfTI smoke export in the Conda `leaddbs` environment;
- MATLAB syntax checks and a noninteractive synthetic scene smoke test when a
  licensed MATLAB runtime is available.

Real-data acceptance will use one completed direct-voxel endpoint and one
completed normative-fiber endpoint before cohort-wide postprocessing.

## Invocation

The endpoint renderer accepts a JSON manifest. Relative paths are resolved from
the manifest directory. One minimal item is:

```json
{
  "schema_version": "dual_frequency_postprocess_v1",
  "output_root": "postprocess",
  "defaults": {
    "formats": ["png", "pdf"],
    "dpi": 300,
    "spatial_boxsize": [36.0, 32.0],
    "fit_boxsize": [48.0, 42.0]
  },
  "endpoints": [
    {
      "endpoint_id": "example_endpoint",
      "summary_json": "inputs/example_endpoint_summary.json",
      "spatial_2d": {
        "model_unit": "voxel",
        "sweet_image": "inputs/sweet.nii.gz",
        "sour_image": "inputs/sour.nii.gz",
        "background_image": "inputs/anatomy.nii.gz"
      },
      "statistics": {
        "subject_table": "inputs/predictions.csv"
      }
    }
  ]
}
```

Run it in the repository environment:

```bash
conda run -n leaddbs python -m my_helper.fiber.core.viz.postprocess \
  --config /absolute/path/to/postprocess.json
```

For MATLAB, remove a previously saved legacy folder from the MATLAB path before
adding the repository recursively:

```matlab
rmpath('/Users/mojackhu/Github/leaddbs/my_helper/fiber/core/visualization');
addpath(genpath('/Users/mojackhu/Github/leaddbs'));
```

Calling `savepath` afterward is an optional user-level MATLAB configuration
change and is not performed by this repository migration.

## Implementation Validation

Validation completed on 2026-07-18:

- the combined dual-frequency and visualization test suite passed with 466
  Python tests and 239 subtests;
- the visualization package passed Python byte-code compilation and CLI import
  checks in Conda `leaddbs`;
- MATLAB R2024b found both the migrated legacy entry points and the new
  `mh_viz_make_sweet_sour_scene` entry point under `core/viz`;
- MATLAB Code Analyzer reported no issue for the new scene wrapper;
- noninteractive synthetic voxel and fiber scenes exported successfully;
- synthetic signed-voxel validation confirmed a symmetric `vik` scale, the
  reference right-side colorbar, grayscale truecolor anatomy slices, and the
  requested R/A/S colors without changing reference arrow style parameters;
- synthetic scored-fiber validation confirmed one `scores` value per fiber,
  symmetric `vik` mapping, true score ticks, and an independent right-side
  colorbar that does not recolor anatomy slices;
- PNG and mixed-mode PDF exports were visually reviewed after rendering the PDF
  pages with Poppler; the PDFs contain embedded Arial text and no vector surface
  seams;
- synthetic Boxsize-driven 2D sections and paired in-sample/LOOCV plots were
  exported and visually reviewed.
