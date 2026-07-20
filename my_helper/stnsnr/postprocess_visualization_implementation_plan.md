# Task 17 Postprocess Visualization Implementation Plan

## Status

Rendering primitives were implemented on 2026-07-18. The public-only adapter
was implemented and synthetically validated on 2026-07-19. Canonical main and
final-in-sample publication remain the scientific input boundary. The user
deleted the earlier 112-endpoint postprocess output after review, so that
historical render is evidence about the implementation but is not a current
published deliverable. The PDQ-39 paired in-sample and LOOCV fit checkpoint was
accepted on 2026-07-19. The next refinement checkpoint is the sweet/sour 2D
spatial figure. Its revised PDQ-39 direct-voxel implementation produced all six
contracted PNG/PDF/JSON result triplets with zero failures on 2026-07-20 and
reused all six results on an immediate second invocation. The revision fixes
the per-cell MNI field to 12 by 10 mm, preserves the raw finite ROI during
display smoothing, uses a 1 point mask boundary, and preserves opaque MyLFP
strip colors on the transparent canvas. Internal visual and PDF QA passed;
explicit user visual acceptance remains pending. No other scale
or fiber spatial batch is authorized. This document is the implementation contract
for a postprocess visualization layer that consumes formally published
dual-frequency final-model artifacts without rerunning model fitting,
permutation, bootstrap, jitter, or OSS-DBS. A run-store adapter is prohibited.

## Goal

Add one reusable visualization package under
`my_helper/fiber/core/viz/` with two output families:

1. sweet/sour spatial visualization for direct-voxel and normative-fiber final
   models;
2. paired in-sample and LOOCV statistical-fit visualization with only the
   requested Spearman and permutation inference statistics shown on the
   figure.

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
  paired_fit_postprocess.py
  postprocess.py
  plugin/
    __init__.py
    default/
      __init__.py
      viz_defaults.py
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

### Visualization plugin configuration

`my_helper/fiber/core/viz/plugin/default/viz_defaults.py` is the canonical
default visual-style configuration. It mirrors the configuration role of
`/Users/mojackhu/Github/MyLFP/plugin/default/viz_defaults.py` without importing
MyLFP at runtime. The module contains rendering choices only: physical panel
geometry, gaps, strip geometry, typography, palette, point and line styling,
ribbon styling, identity-line styling, export formats, DPI, and transparency.

The module must not contain endpoint IDs, scale IDs, tau, Coverage, branch
selection, sample size, statistical values, p-value thresholds, model-selection
rules, or scientific file paths. Those values remain publication data and are
read from the selected final model and final-in-sample summary. Callers obtain a
fresh configuration mapping so endpoint-specific display overrides cannot
mutate the process-wide default configuration.

## Input Contract

### Canonical publication boundary

The internal run store is not a postprocess API. The only accepted scientific
source is a completed canonical model-set publication or a completed canonical
extension publication. Configuration declares publication aliases whose roots
contain a terminal manifest and `artifact_index.csv`. Every scientific input
uses an object with:

```text
publication
relative_path
```

Before reading a scientific input, the adapter requires that the resolved path
remain below the declared publication root, that the artifact index contain one
matching row, that status is complete, and that byte count and SHA-256 match.
Paths below `.runs/`, `tasks/`, `work/`, or `runtime_work/` are invalid even if
their bytes match an indexed historical artifact. File URIs pointing back to a
run store are likewise invalid. There is no fallback to task records.

Postprocess is unaffected by workflow cache retention. It remains usable after
an eligible cache cleanup because every scientific input comes from canonical
publication. The configured production workflow currently retains cache so
later jitter, OSS-DBS, and combined extensions can reuse physical preparation.

Model summaries, final-model records, prediction tables, voxel maps, fiber
axes, fiber weights, density maps, and formal or in-sample inference summaries
are scientific inputs and must use indexed publication references. Anatomy,
atlas outlines, and declared connectome geometry are rendering resources; the
publication manifest must bind their identities, but the large immutable
source files need not be copied into every model-set directory.

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
For 2D sections, the same indexed signed `benefit_map.nii.gz` is supplied as
both spatial inputs with `sweet_value_mode: positive` and
`sour_value_mode: negative_magnitude`. These display-time sign projections do
not create, publish, threshold, or refit separate voxel models.
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
They are display derivatives only. The positive density retains positive
weight sums and the negative density retains negative weight sums; the 2D sour
layer therefore uses `negative_magnitude` display mode without altering the
published signed density.

A realized model may select only one sign. The canonical publisher still emits
both positive and negative density files so the postprocess schema remains
stable. The missing-sign file is zero over the union support of the selected
side and `NaN` outside that support; its provenance records zero selected fibers
and no selected-ID SHA. Postprocess renders the available sign and treats the
zero file as an empty layer. It does not create a replacement fiber or infer a
missing sign from the opposite library.

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

The figure annotation is intentionally restricted to:

```text
Spearman rho
formal permutation p
```

Selected tau, selected Coverage, final branch, finite counts, Pearson metrics,
Spearman nominal p, error metrics, fit metrics, optimism gaps, and BH-adjusted
values remain in the machine-readable endpoint result and are not drawn on the
figure. Adjusted R2 is not reported because the fitted spatial model has no
single stable degrees-of-freedom count.

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

The Python renderer creates paired calibration panels:

- observed outcome on the shared horizontal axis;
- fitted in-sample or held-out LOOCV prediction on the vertical axis;
- subject points;
- ordinary least-squares display line with a 95 percent confidence band when
  the input is estimable;
- no identity line;
- one upper-left annotation block per panel containing only Spearman rho and
  formal permutation p;
- no figure title or model-parameter text inside the graphic.

The fit line is descriptive. Formal inference remains the stored permutation
p and BH q; the renderer must not reinterpret the line's slope p as the model's
formal p.

### Accepted PDQ-39 fit-style checkpoint

The first postprocess checkpoint rendered only paired in-sample and LOOCV fit
figures for PDQ-39. The reference-fiber final model was the first visual QA
sentinel, followed by reference voxel, add-on voxel, and add-on fiber. The user
accepted this fit visualization on 2026-07-19. This acceptance freezes the
style described below for a future fit batch but does not authorize that batch
or a spatial batch.

The default fit style is a value-for-value port of the MyLFP `fit_cfg` and its
effective `plot_double_interaction_fit` defaults. It preserves the six-to-five
panel aspect with a 30 by 25 mm inner plotting box. Two panels are arranged in
one row with a 3 mm horizontal gap. The top strips use `#D7E3E0`, bold black
labels, 4.5 mm strip height, and 2 mm strip padding. Arial is used throughout.
Strip, axis-label, and optional title text use 7 point type; tick and annotation
text use 6 point type. Output DPI is 600 and the background is transparent.
Global axis labels use the MyLFP 5 mm offsets and measured text margins. Export
uses the same tight bounding-box behavior as the MyLFP `save_fig` helper. The
figure canvas outside the axes is transparent, while panel and strip axes stay
opaque so the `#D7E3E0` strip color survives both PNG and PDF export.

Each subject keeps one deterministic Viridis color across both panels. The
subject colors span the full MyLFP Viridis sampling interval. Points use the
MyLFP `fit_cfg` size of 2 and full opacity. The descriptive line is black with a
1 point stroke, and its 95 percent display ribbon uses 0.30 alpha. Grid lines
are absent. All four panel spines remain visible because `fit_cfg` does not
override the effective `plot_double_interaction_fit` default. Axis spines and
major ticks use a 1 point stroke, major ticks are 2 points long, and tick and
axis-label padding are 1 point. No identity line is drawn.

Axis-limit content reproduces the effective MyLFP
`visualdf._plot_interaction_fit_grid` contract, with one explicit adaptation
for paired calibration plots. Horizontal and vertical limits are computed
independently rather than forcing a square numeric range. The shared horizontal
limit includes all finite observed outcomes and both display-curve grids. The
shared vertical limit uses the maximum joint range across both panels: its
lower endpoint is the minimum of every finite in-sample and LOOCV prediction,
fitted curve, and lower confidence-ribbon bound; its upper endpoint is the
maximum of the corresponding predictions, fitted curves, and upper
confidence-ribbon bounds. Both shared ranges receive 5 percent of their own
span as padding. The panels therefore share the observed horizontal axis and
the prediction vertical axis. No finite ribbon vertex may lie outside the
final shared vertical limit. The right panel suppresses duplicate vertical
tick labels.

The compact panel annotation contains only stored Spearman rho and formal
two-sided permutation p. Spearman rho is formatted as `rho = xxx` with the Greek
rho glyph. Permutation p is formatted to three decimals with `(n.s.)`, `(*)`,
or `(**)` for values outside, below 0.05, or below 0.01, respectively. Values
strictly below 0.001 are reported as `p < 0.001 (***)`. Spearman nominal p,
model-family BH q, finite subject count, and every other metric remain outside
the figure. The two-line block uses the 6 point tick-label size, upper-left
panel anchor, 5 percent inset on both axes, and a fully transparent annotation
box. The complete published
metrics remain in the human-readable result JSON; shrinking or hiding points
to fit the annotation is prohibited.

`paired_fit_postprocess.py` is the fit-only publication entry point. It accepts
one explicit scale ID and the four completed canonical publication roots,
validates each final model, final-in-sample summary, and paired prediction
table through the publication artifact indexes, and writes the semantic
`scales/<scale-id>/<reference-or-addon>/<voxel-or-fiber>/` tree. The PDQ-39
acceptance invocation passes only `pdq39_score`; it does not enumerate the
remaining scales.

Acceptance evidence comprises four completed PDQ-39 model-family figures with
zero rendering failures, direct PNG and Poppler-rendered PDF review, complete
confidence ribbons, embedded Arial PDF fonts, and 20 passing visualization
tests. An identical second invocation reused all four completed outputs with
zero failures. The acceptance figure shows observed outcome on the shared
horizontal axis, prediction on the shared maximum-joint-range vertical axis,
and upper-left Spearman rho plus formal permutation p annotations.

### Accepted PDQ-39 direct-voxel spatial checkpoint

The first 2D spatial checkpoint is restricted to the completed PDQ-39
direct-voxel reference and add-on final models. It does not authorize another
scale or a normative-fiber spatial batch. Scientific heatmaps are read only
from the completed canonical direct-voxel publication and never from `.runs/`.

The checkpoint produces six independent three-by-three figures: the original
right-sided benefit map, its one-millimetre FWHM display derivative, and its
two-millimetre FWHM display derivative for each of the reference and add-on
models. The indexed publication artifacts are `benefit_map.nii.gz`,
`benefit_map_smooth_fwhm1mm.nii.gz`, and
`benefit_map_smooth_fwhm2mm.nii.gz`. All three heatmaps remain right-sided;
this checkpoint does not create or render a bilateral derivative. Each figure derives its own symmetric
signed color limits from its sampled panels. No color range is shared between
figures. The heat colorbar label is `Benefit-oriented partial Spearman rho`,
rendered with the Greek rho glyph.

The implementation reproduces the effective configuration and rendering
contract of
`/Users/mojackhu/Github/MyLFP/recipes/stnsnr/viz/med/single_volume.py`,
`plugin/default/viz_defaults.py`, and
`src/viz/visualdf.py::plot_triple_interaction_nifti` without importing MyLFP at
runtime. Each row is one of Ax, Cor, and Sag. Columns use the 25, 50, and 75
percent positions of the finite signed heatmap support along the row's fixed
world axis. All panels use canonical RAS world coordinates, equal physical
spatial aspect, one shared fixed field of view, and the 30 by 25 mm inner
Boxsize. Sampling resolution is 0.1 mm. Continuous anatomy and heat use linear
world-space sampling; the binary mask uses nearest-neighbour sampling.
Every cell uses one fixed 12 by 10 mm MNI field of view centered on that
slice's finite heatmap support. This field preserves the 30 by 25 mm page
Boxsize ratio and one-to-one physical spatial scaling while providing more
anatomical context than the support-tight automatic range.

The background is fixed to
`/Volumes/VAL/STNSNr/config/atlas/7T_100um_Edlow_2019_cropped.nii.gz` and uses
the reference grayscale zero-to-one-hundred percentile contrast with gamma
one. The large compressed anatomy must not be converted into one full
floating-point array. The renderer reads only the required spatial crop or
slice data while preserving the reference pixels. Anatomy is always rendered
before the mask and heatmap and never receives the `vik` colormap.

The reference figure uses
`/Volumes/VAL/STNSNr/config/atlas/STN_rh_mask.nii.gz`; the add-on figure uses
`/Volumes/VAL/STNSNr/config/atlas/SNr_rh_mask.nii.gz`. The mask threshold is
0.05. Masks are
not filled: their boundaries are drawn after the voxel heatmap with a solid,
fully opaque black 1 point stroke, so the boundary remains visible over every
heat color.

Both smoothed heatmaps are constrained to the exact finite support of their
selected unsmoothed `benefit_map.nii.gz`. Smoothing remains masked-normalized
within that support, but no Gaussian halo becomes a finite output voxel. The
raw, 1 mm FWHM, and 2 mm FWHM NIfTIs therefore share one finite ROI for each
model role.

The remaining style is frozen to the MyLFP reference values: a three-by-three
panel grid, 3 mm horizontal and vertical panel gaps, Arial typography, 7 point
strip and axis text, 600 DPI, no title, no axis tick labels, `#D7E3E0` top
strips, `#E3DCCF` right strips, the `vik` signed colormap, a single global
right-side colorbar, a black 2 mm global scale bar, and a transparent figure
canvas. The output formats are PNG, PDF, and one machine-readable JSON record
per figure.

Every ordinary text artist uses Arial, matching the MyLFP defaults. A fallback
font is permitted only for a special character that Arial cannot render; it
must not replace Arial for surrounding ordinary text. The top and right strip
patches remain fully opaque even though the surrounding figure canvas is
transparent. Their rendered backgrounds are respectively the solid MyLFP
colors `#D7E3E0` and `#E3DCCF`, and export QA checks the output pixels rather
than relying only on in-memory Matplotlib properties.

The accepted output root is
`/Volumes/VAL/STNSNr/summary/spot/postprocess/dual_frequency_four_model_v1/task17-pdq39-voxel-spatial-v1-20260719`.
The human-readable relative output contract is:

```text
scales/pdq39_score/reference/voxel/
  benefit_map_sections.png
  benefit_map_sections.pdf
  benefit_map_sections.json
  benefit_map_smooth_fwhm1mm_sections.png
  benefit_map_smooth_fwhm1mm_sections.pdf
  benefit_map_smooth_fwhm1mm_sections.json
  benefit_map_smooth_fwhm2mm_sections.png
  benefit_map_smooth_fwhm2mm_sections.pdf
  benefit_map_smooth_fwhm2mm_sections.json
scales/pdq39_score/addon/voxel/
  benefit_map_sections.png
  benefit_map_sections.pdf
  benefit_map_sections.json
  benefit_map_smooth_fwhm1mm_sections.png
  benefit_map_smooth_fwhm1mm_sections.pdf
  benefit_map_smooth_fwhm1mm_sections.json
  benefit_map_smooth_fwhm2mm_sections.png
  benefit_map_smooth_fwhm2mm_sections.pdf
  benefit_map_smooth_fwhm2mm_sections.json
```

Each JSON record binds the publication artifact identity and hash, final-model
identity and selected tau and Coverage, anatomy and mask identities, slice
coordinates, sampled ranges, color limits, rendering parameters, and PNG/PDF
outputs. A completed reusable result requires both visual files and the matching
JSON record. The six-figure checkpoint must pass direct PNG review, rendered-PDF
review, font inspection, output-structure validation, publication-hash
validation, and proof that the anatomy was not loaded as one full floating-point
volume before any broader spatial batch can be proposed.

Acceptance evidence for the right-sided contract comprises six completed
figures with zero failures, 36 passing focused publication and visualization
tests, direct review of reference and add-on PNG/PDF renderings, and embedded
Arial plus Arial Bold PDF fonts. Source inspection found zero finite voxels at
negative MNI x in all six selected raw or smoothed NIfTIs. A second invocation
reused all six completed results with zero failures. Superseded outputs were
moved out of the formal result tree and into the VAL Trash.

Implementation evidence on 2026-07-20 comprises six complete results, zero
failed results, and six reused results on the second invocation. The reference
raw, 1 mm, and 2 mm maps each contain 638 finite voxels; the add-on maps each
contain 577. Every recorded panel range is exactly 12 by 10 mm. Pixel-level PNG
inspection found fully opaque `#D7E3E0` top-strip and `#E3DCCF` right-strip
backgrounds in all six figures while the surrounding canvas remained
transparent. All six PDFs embed only subset Arial and Arial Bold TrueType
fonts. Poppler-rendered PDF review found complete strips, panel labels,
colorbars, global scale bars, anatomy, signed heatmaps, and top-layer black mask
boundaries without clipping. Every result records a symmetric heat range and
`background_full_float_loaded: false`. This evidence establishes implementation
readiness but does not replace explicit user acceptance of the visual
appearance.

### PDQ-39 normative-fiber two-dimensional spatial checkpoint

The next spatial checkpoint is restricted to the completed PDQ-39 normative-
fiber reference and add-on final models. It consumes only the final model,
resolver artifacts, and formal connectome geometry declared by the completed
canonical normative-fiber publication. It never reads `.runs/`, and it does
not authorize another endpoint or a cohort-wide fiber batch.

The checkpoint publishes two distinct fiber-axis display derivatives for each
model role. Neither derivative is a direct-voxel model, a new fitted model, or
an inferential statistic.

The direct streamline-score projection uses the complete selected streamline
paths. For selected fiber `i`, signed full-model score `s_i`, independent
quantitative streamline weight `q_i`, and binary once-per-fiber voxel incidence
`I_iv`, the projected score is:

```text
M_v = sum_i(I_iv * q_i * s_i) / sum_i(I_iv * q_i)
```

The current formal PPMI connectome has no independent quantitative streamline
weight, so `q_i` is exactly one. Model-score magnitude must never be reused as
`q_i`. The direct projection writes `NaN` where no selected sweet or sour fiber
is present and publishes separate total, sweet, and sour support maps. Complete
streamline paths are retained in the NIfTI derivative, while the accepted
three-by-three figure remains centered on the right-sided role seed.

The target-conditioned projection separates target scoring from local target
composition. Target membership `m_it` is one when any segment of selected
fiber `i` intersects target `t` and zero otherwise. Multiple intersections with
one target remain one hit, and overlapping targets are evaluated independently.
The target score is:

```text
T_t = sum_i(m_it * q_i * s_i) / sum_i(m_it * q_i)
```

For `k_i = sum_t(m_it)`, fractional membership is used only for composition:

```text
a_it = m_it / k_i
H_vt = sum_i(I_iv * q_i * a_it)
G_v = sum_t(H_vt * T_t) / sum_t(H_vt)
```

`H_vt` and `G_v` are evaluated only inside the configured right-sided seed:
STN for reference and SNr for add-on. Every target-hit fiber therefore
contributes total composition mass `q_i` at each traversed seed voxel regardless
of how many targets it hits. A fiber with `k_i` equal to zero is excluded from
`G_v`, but its seed-voxel mass is published separately. The contract therefore
claims mass conservation only within the target-hit subset and also publishes
target-assignment coverage so unassigned mass is never hidden.

The explicit spatial catalog is
`my_helper/stnsnr/config/four_model_v1/fiber_spatial_projection.yaml`. It fixes
the full 7 T Edlow anatomy, one right-sided seed per role, the shared ordered
right-sided target catalog, segment-aware intersection, independent binary
target hits, fractional composition, uniform `q_i`, and the exclude-and-report
no-target policy. Every seed and target must be binary, three-dimensional,
canonical RAS, and on the exact projection grid. Geometry disagreement is a
hard failure rather than an implicit resampling step. The 100 micrometre anatomy
is a lazy display resource only and never becomes the projection grid.

The first checkpoint produces four independent figures:

1. reference direct streamline-score mean;
2. add-on direct streamline-score mean;
3. reference target-conditioned score;
4. add-on target-conditioned score.

All four figures reuse the accepted direct-voxel layout and aesthetics: three
rows for Ax, Cor, and Sag; 25, 50, and 75 percent seed positions; one fixed 12
by 10 mm field per cell; 0.1 mm display sampling; lazy 7 T anatomy; a solid,
fully opaque black 1 point seed boundary on the top layer; Arial typography;
opaque `#D7E3E0` top strips and `#E3DCCF` right strips; a signed `vik` scale
centered on zero; a single right colorbar; 600 DPI; transparent canvas; and PNG,
PDF, and JSON outputs. Each figure derives its own symmetric color range. The
first checkpoint publishes raw projections only and performs no Gaussian
smoothing.

The human-readable output contract is:

```text
scales/pdq39_score/<reference-or-addon>/fiber/
  direct_streamline/
    maps/
      streamline_score_mean.nii.gz
      streamline_support_count.nii.gz
      streamline_sweet_count.nii.gz
      streamline_sour_count.nii.gz
    figures/
      streamline_score_mean_sections.png
      streamline_score_mean_sections.pdf
      streamline_score_mean_sections.json
    projection_qc.json
  target_conditioned/
    maps/
      target_conditioned_score.nii.gz
      target_assigned_mass.nii.gz
      target_unassigned_mass.nii.gz
      target_assignment_fraction.nii.gz
    tables/
      target_scores.csv
      fiber_target_membership.csv
    figures/
      target_conditioned_score_sections.png
      target_conditioned_score_sections.pdf
      target_conditioned_score_sections.json
    target_membership_qc.json
```

The output-local cache stores resolved selected streamline geometry, binary
target membership, once-per-fiber voxel incidence, and sparse seed target mass.
Cache identity binds the canonical publication artifacts, formal connectome
identity, spatial-catalog identity, traversal contract, and projection grid.
Repository code identity is not a resume gate. Failed or partial work retains
the cache and completed role-local outputs.

Acceptance requires exact selected-ID and score alignment; binary once-per-
fiber target and voxel incidence; segment-aware rather than vertex-only
intersection; target-hit composition conservation; explicit unassigned mass;
finite `G_v` only where assigned mass is positive; `G_v` within the local
finite target-score range; role-local failure isolation; verified publication
hashes; direct PNG and rendered-PDF inspection; Arial font inspection; bounded
lazy anatomy loading; and full reuse on an identical second invocation.

Implementation evidence on 2026-07-20 is stored below
`/Volumes/VAL/STNSNr/summary/spot/postprocess/dual_frequency_four_model_v1/`
`task17-pdq39-fiber-spatial-v1-20260720/`. Both role-local results completed,
and an identical second invocation reused both complete results. Reference and
add-on each used 300 selected fibers, comprising 200 sweet and 100 sour fibers,
at their realized final tau of 400 V/m and Coverage of 5. The direct maps
contain 50,142 and 50,571 finite voxels, respectively. The target-conditioned
maps contain 878 finite reference seed voxels and 2,183 finite add-on seed
voxels. Maximum target-composition mass errors are
`1.4210854715202004e-14` and `7.105427357601002e-15`, and no target-conditioned
score exceeds its contributing target-score range.

All four PNG files and Poppler-rendered PDF pages passed visual inspection for
the accepted anatomy, signed heatmap, panel geometry, opaque strips, top-layer
seed outline, colorbar, scale bar, and absence of clipping. Each PDF embeds
only subset Arial and Arial Bold TrueType fonts. The combined visualization and
seed-target traversal suite passed 106 tests and 27 subtests, with one optional
real-data acceptance test skipped. The formal output passed NIfTI grid,
support-decomposition, assignment-fraction, finite-support, output-presence,
figure-metadata, and mass-conservation checks. This evidence authorizes only
the PDQ-39 checkpoint; no other scale was rendered.

## Output Contract

```text
postprocess/<postprocess-id>/
  README.md
  endpoint_index.csv
  manifest.json
  scales/
    <scale-id>/
      reference/
        voxel/
          in_sample_loocv_fit.png
          in_sample_loocv_fit.pdf
          result.json
        fiber/
          in_sample_loocv_fit.png
          in_sample_loocv_fit.pdf
          result.json
      addon/
        voxel/
          in_sample_loocv_fit.png
          in_sample_loocv_fit.pdf
          result.json
        fiber/
          in_sample_loocv_fit.png
          in_sample_loocv_fit.pdf
          result.json
```

Opaque endpoint IDs remain manifest fields for resume and provenance; they are
not user-facing directory names. During the active checkpoint, the tree
contains only `scales/pdq39_score/`. Spatial output will be added only after its
separate visual contract is accepted.

Each manifest records canonical publication IDs, indexed relative source paths,
source hashes, selected model key, plotting parameters, output paths,
completion status, and errors. Postprocessing never changes a model-set or
extension manifest and never marks a scientific task complete.

The endpoint batch renderer does not duplicate published NIfTI, MAT, or
prediction-table scientific inputs into its output tree. Their canonical
publication aliases, relative paths, byte counts, and SHA-256 values are stored
in the endpoint manifest. This preserves one scientific source of truth and
keeps output-local resume independent of the internal run store.

The two PDQ-39 MATLAB examples are the separate interactive 3D acceptance
surface requested for voxel and fiber models. They verify and prepare inputs
from the same canonical publications, open a correctly rendered figure window,
and intentionally create no FIG, PNG, PDF, or spin export. The migrated export
helpers remain available for an explicit later export request but are not part
of the cohort-wide endpoint batch contract.

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

### Formal production request

The 2026-07-19 production acceptance request uses the completed
`dual_frequency_four_model_v1` direct-voxel and normative-fiber model-set
publications plus their canonical
`task17-final-in-sample-v2-20260719` extensions. It contains all 112 unique
final endpoints. Every endpoint receives one paired in-sample/LOOCV fit plot.
The 56 direct-voxel endpoints use the realized final benefit map as both the
sweet and sour source with positive and negative-magnitude display modes. The
56 normative-fiber endpoints use the published positive and negative weighted
density maps; these remain display derivatives of fiber-axis results.

Spatial panels use the repository MNI152NLin2009bAsym T1 image as anatomy and
right-hemisphere STN and SNr masks from the configured 0.05 custom atlas as
outline-only rendering resources. The request retains Boxsize layout, the
explicit sweet/sour color distinction, 0.5 mm display sampling, 300 dpi output,
and both PNG and PDF formats. It writes only below:

```text
/Volumes/VAL/STNSNr/summary/spot/postprocess/
  dual_frequency_four_model_v1/
    task17-final-in-sample-v2-20260719/
```

Acceptance first renders reference-voxel and reference-fiber PDQ-39 smoke
items for visual review, then executes all 112 endpoints. A second identical
execution must reuse all completed endpoint manifests and outputs without
rerendering. Any failed or partial endpoint remains in place for output-local
resume; postprocess never cleans the run store, canonical publications,
extensions, or shared cache.

The first real PDQ-39 smoke render exposed a layout defect before cohort-wide
execution: every bottom-row panel repeated a long generic horizontal-axis
label, adjacent tick labels collided, and the legend occupied the same lower
margin. The renderer must retain exact Boxsize panels while showing horizontal
tick labels only on the bottom row, vertical tick labels only in the first
column, one plane-specific horizontal-axis label on the center bottom panel,
and a separately reserved legend band. This is a rendering-only correction;
it does not change slice selection, spatial sampling, source values, colors,
atlas geometry, or statistical results.

After the correction, 11 focused visualization tests passed. The regenerated
PDQ-39 reference-voxel and reference-fiber smoke requests completed with zero
failed items. PNG review confirmed grayscale anatomy, distinct sweet and sour
overlays, readable STN/SNr outlines, noncolliding labels, and a complete legend.
Poppler-rendered PDF review confirmed the same layout without clipping; the
PDFs embed Arial text. The complete dual-frequency and visualization regression
then passed with 481 tests and 239 subtests in the system-monitoring-capable
test environment.

The endpoint renderer accepts a JSON manifest. Relative paths are resolved from
the manifest directory. One minimal item is:

```json
{
  "schema_version": "dual_frequency_postprocess_v2",
  "output_root": "postprocess",
  "publications": {
    "direct_voxel_main": {
      "root": "/absolute/path/to/direct_voxel/model_set",
      "manifest": "model_manifest.json"
    },
    "direct_voxel_in_sample": {
      "root": "/absolute/path/to/direct_voxel/model_set/extensions/final_in_sample",
      "manifest": "extension_manifest.json"
    }
  },
  "defaults": {
    "formats": ["png", "pdf"],
    "dpi": 300,
    "spatial_boxsize": [36.0, 32.0],
    "fit_boxsize": [48.0, 42.0]
  },
  "endpoints": [
    {
      "endpoint_id": "example_endpoint",
      "summary_json": {
        "publication": "direct_voxel_in_sample",
        "relative_path": "example_endpoint/summary.json"
      },
      "spatial_2d": {
        "model_unit": "voxel",
        "sweet_image": {
          "publication": "direct_voxel_main",
          "relative_path": "example_endpoint/resolver/benefit_map.nii.gz"
        },
        "sour_image": {
          "publication": "direct_voxel_main",
          "relative_path": "example_endpoint/resolver/benefit_map.nii.gz"
        },
        "sweet_value_mode": "positive",
        "sour_value_mode": "negative_magnitude",
        "background_image": "inputs/anatomy.nii.gz"
      },
      "statistics": {
        "subject_table": {
          "publication": "direct_voxel_in_sample",
          "relative_path": "example_endpoint/predictions.csv"
        }
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

Public-only integration validation completed on 2026-07-19:

- postprocess schema v2 rejected inline scientific summaries and required
  publication aliases plus indexed relative paths;
- every scientific input passed publication-root containment, completed-row,
  byte-count, and SHA-256 validation before rendering or resume reuse;
- a publication root below `.runs` was rejected without creating output;
- the PDQ-39 scene adapter consumed synthetic canonical direct-voxel and
  normative-fiber publications and no longer scanned task JSON or run work;
- 10 focused visualization tests passed;
- the complete dual-frequency and visualization suite passed with 470 tests
  and 239 subtests under Conda `leaddbs`; and
- MATLAB Code Analyzer reported no issue for the changed helper and examples.

Real-data production acceptance completed on 2026-07-19. The formal request
resolved four completed canonical publications, rendered all 112 final
endpoints with zero failures, and produced 448 PNG/PDF outputs. All endpoint
manifests and files passed structural validation; 224 PNG files decoded, and
224 PDF files passed file-level integrity checks. Reference and add-on examples
from both physical domains passed visual review. Repeating the identical
request reused all 112 endpoint outputs without changing their byte counts or
nanosecond modification times. No run-store fallback was used.
