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
final visual review remains part of full-cohort acceptance. The active
full-goal continuation now authorizes the all-scale batch after the ordered
Task 17 publication dependencies complete. The existing PDQ-39 and FoGQ fiber
roots remain refinement checkpoints and cannot substitute for that batch. This
document is the implementation contract
for a postprocess visualization layer that consumes formally published
dual-frequency final-model artifacts without rerunning model fitting,
permutation, bootstrap, jitter, or OSS-DBS. A run-store adapter is prohibited.

A read-only filesystem inventory on 2026-07-21 found 19 current checkpoint
roots below
`/Volumes/VAL/STNSNr/summary/spot/postprocess/dual_frequency_four_model_v1/`.
They comprise two PDQ-39 direct-voxel roots, 11 PDQ-39 normative-fiber roots,
and six FoGQ normative-fiber roots. Every root has a terminal `complete`
manifest with zero failed results. Each direct-voxel root contains six complete
render results; each normative-fiber root contains two. The newest checkpoints
are `task17-pdq39-voxel-spatial-v2-scale-label-20260721`,
`task17-pdq39-fiber-spatial-v11-target-raincloud-20260721`, and
`task17-fogq-fiber-spatial-v6-target-raincloud-20260721`.

This 19-root inventory does not constitute the current full 112-endpoint
postprocess deliverable. It covers only two scales, mixes successive visual
refinement versions, and has no durable full-cohort request manifest from which
the deleted historical batch can be reproduced or resumed as one formal job.
The earlier all-endpoint render remains historical implementation evidence
only. After explicit visual acceptance, the formal replay must derive a new
durable request from the canonical main and final-in-sample publications, write
one new immutable full-cohort output root, and repeat the identical request to
prove output-local resume. It must not treat a deleted root or any refinement
checkpoint as a completed full-cohort item.

The active full-goal continuation on 2026-07-22 authorizes that formal replay
after its required canonical Task 17 publication dependencies are terminal.
The durable request is stored at
`my_helper/stnsnr/config/four_model_v1/formal_postprocess.json` and targets the
new immutable root
`/Volumes/VAL/STNSNr/summary/spot/postprocess/dual_frequency_four_model_v1/`
`task17-formal-postprocess-v1-20260722`. It selects every canonical scale and
all three batch component families. It binds the canonical main and
final-in-sample v2 publications, the accepted 7-T display anatomy, the
right-sided STN and SNr outline masks, and the normative-fiber spatial
configuration. The request may be validated now, but rendering remains ordered
after independent OSS, combined execution, and the remaining canonical
extension replays so the full Task 17 publication audit precedes the final
postprocess acceptance. The independent jitter lineage already has accepted
self-contained v2 publications in both public domains: each contains 56
results, 170 relative artifact-index rows, complete parent binding, and an
unchanged manifest after identical replay. OSS-v2 and combined-v2 remain
pending and continue to gate the formal render.

A fresh read-only preflight on 2026-07-22 validated this durable request while
the independent OSS lineage remained active. It resolved 28 scales, 112 final
endpoints, four canonical main/final-in-sample publications, and the
`paired_fit`, `voxel_2d`, and `fiber_2d` component families. The accepted 7-T
anatomy, STN/SNr masks, formal PPMI85 connectome, fiber projection profile,
PDF tooling, and PNG/PDF formats all passed identity and availability checks.
The command used `--validate-only`; it did not create the formal output root or
read any run-store path. This accepts the current input preflight only. It does
not replace the ordered full render, terminal output verification, or
identical-request resume after the Task 17 sensitivity publications close.

A full selected-map derivative audit on 2026-07-23 found that the canonical
direct-voxel publication still mixes two display-smoothing generations. The
two PDQ-39 endpoint roles use the current
`masked_normalized_gaussian_original_roi_v2` contract and preserve the exact
finite support of their selected raw benefit maps. The other 54 endpoint roles
retain 108 indexed derivatives from `masked_normalized_gaussian_v1`, which
expands finite display support into neighboring voxels. Every file remains
structurally intact and digest-valid, and this difference is display-only, but
the mixed generation is not accepted as the input to the formal all-cohort
render. After the active OSS lineage releases VAL bandwidth, republish those
54 one-millimeter and two-millimeter derivative pairs from their canonical raw
maps with the current publisher, update their metadata and artifact-index
rows atomically, and verify exact raw-support preservation before starting the
formal postprocess job.

A public-only deterministic staging replay completed on 2026-07-23 at
`/private/tmp/task17-display-smoothing-v2-stage.zAofAX` without changing the
canonical publication. Rebuilt PDQ-39 files were byte-identical to the four
accepted v2 files. The complete stage contains 112 v2 derivatives and metadata
records, all with exact raw finite-support preservation. Its candidate artifact
index retains all 2215 canonical relative paths and changes exactly the 108 old
v1 rows, limited to payload SHA-256 and byte count. The repair-manifest SHA-256
is
`dff3ab60616b2bd9d77075bc6781f6ef928db666f1052ac31d5f02f4088f6b5c`.
Promotion and the subsequent formal render remain ordered after the active OSS
solver releases VAL.

Promotion must use the repository-owned
`my_helper/fiber/pipelines/repair_task17_display_smoothing_publication.py`
command rather than an ad hoc file loop. Its `stage` mode reads only indexed
canonical selected raw maps, deterministically writes both v2 derivatives and
their metadata to a new caller-selected local directory, and writes a complete
repair manifest plus candidate artifact index. Its `validate` mode requires
the current canonical index to retain the manifest's frozen source SHA-256,
checks every staged byte and metadata record, proves exact finite-support
preservation, and permits index changes only to the target SHA-256 and byte
count fields.

Its `promote` mode is permitted only after the independent OSS process exits.
It requires an explicit same-volume destination below
`/Volumes/VAL/.Trashes/501`, copies each staged replacement to a temporary
sibling, verifies it, archives every replaced untracked canonical file in that
Trash tree, and uses same-parent atomic replacement. The completed
`model_manifest.json` is temporarily withdrawn while any target or index may
be mixed, so concurrent consumers fail closed. The original manifest is
restored byte-identically only after all replacement payloads, metadata, and
the candidate artifact index validate. Interrupted promotion remains
resumable from the repair manifest and archived files; an unknown destination
or changed source index fails closed. A final `validate` invocation must accept
the promoted root before formal postprocess starts.

The repository-owned repair command was implemented on 2026-07-23. Six
transaction fixtures cover deterministic staging, read-only validation,
same-volume Trash promotion, identical repeated promotion, refusal to overwrite
an existing stage, source-index drift, invalid Trash placement, staged-payload
tampering, and resume after an injected interruption with the model manifest
withheld. All six pass. The affected publication, repair, and formal
postprocess regression passes 29 tests under Conda `leaddbs`; the visualization
launcher preloads Numba before pytest adds test directories, preventing the
project `core/coverage` package from shadowing an absent third-party
`coverage` dependency during collection.

The command also rebuilt the full real stage into a second temporary directory.
Both stages contained the same 226-file closure and every relative file was
byte-identical; both repair manifests retained SHA-256
`dff3ab60616b2bd9d77075bc6781f6ef928db666f1052ac31d5f02f4088f6b5c`.
The redundant verification stage was moved intact to the user Trash. The
retained stage at
`/private/tmp/task17-display-smoothing-v2-stage.zAofAX` passes the command's
read-only `validate` mode with 112 targets and 108 changed NIfTIs. No canonical
VAL publication file has been promoted.

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
  formal_postprocess.py
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

An extension-v1 reporting mirror is not a canonical publication. In particular,
a completed manifest does not authorize postprocess when its artifact index
retains a `file://` URI below `.runs`, `tasks`, `work`, or `runtime_work`, or
when endpoint documents expose only run artifact IDs. The 2026-07-21 audit found
this condition in the completed support-preserving jitter mirrors. Jitter may
be used by a future visualization only after a self-contained extension-v2
replay publishes verified payloads and publication-relative index paths. Main
and final-in-sample v2 publications remain valid and are unaffected.

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
the PDQ-39 checkpoint; no other scale was rendered in that checkpoint.

## Output Contract

```text
postprocess/<postprocess-id>/
  request.json
  resolved_request.json
  README.md
  endpoint_index.csv
  manifest.json
  .cache/
    <scale-id>/<reference-or-addon>/fiber_projection_<projection-hash>.npz
  scales/
    <scale-id>/
      reference/
        voxel/
          in_sample_loocv_fit.png
          in_sample_loocv_fit.pdf
          in_sample_loocv_fit.json
          benefit_map_sections.png
          benefit_map_sections.pdf
          benefit_map_sections.json
          benefit_map_smooth_fwhm1mm_sections.png
          benefit_map_smooth_fwhm1mm_sections.pdf
          benefit_map_smooth_fwhm1mm_sections.json
          benefit_map_smooth_fwhm2mm_sections.png
          benefit_map_smooth_fwhm2mm_sections.pdf
          benefit_map_smooth_fwhm2mm_sections.json
        fiber/
          in_sample_loocv_fit.png
          in_sample_loocv_fit.pdf
          in_sample_loocv_fit.json
          fiber_spatial.json
          direct_streamline/
            maps/
            figures/
          target_conditioned/
            maps/
            tables/
            figures/
      addon/
        voxel/
          in_sample_loocv_fit.png
          in_sample_loocv_fit.pdf
          in_sample_loocv_fit.json
          benefit_map_sections.png
          benefit_map_sections.pdf
          benefit_map_sections.json
          benefit_map_smooth_fwhm1mm_sections.png
          benefit_map_smooth_fwhm1mm_sections.pdf
          benefit_map_smooth_fwhm1mm_sections.json
          benefit_map_smooth_fwhm2mm_sections.png
          benefit_map_smooth_fwhm2mm_sections.pdf
          benefit_map_smooth_fwhm2mm_sections.json
        fiber/
          in_sample_loocv_fit.png
          in_sample_loocv_fit.pdf
          in_sample_loocv_fit.json
          fiber_spatial.json
          direct_streamline/
            maps/
            figures/
          target_conditioned/
            maps/
            tables/
            figures/
```

The formal all-endpoint transaction is intentionally limited to paired-fit and
two-dimensional spatial outputs. The three-dimensional contract is fulfilled
by the two canonical-publication-backed PDQ-39 MATLAB examples, one direct
voxel and one normative fiber. They open interactive `ea_mnifigure` windows and
create no file unless the caller explicitly supplies an output path. They are
not silently expanded into 112 static scenes.

`request.json` is the immutable user-facing request copied into the output
root before rendering. It declares publication aliases, the requested output
families, all-available or explicit scale scope, the accepted visual-contract
identity, and the output root. It does not contain scientific values copied
from endpoint summaries. `resolved_request.json` is generated only from the
validated canonical model-set and final-in-sample publications. It enumerates
every selected endpoint with publication-relative final-model, summary,
prediction, voxel-map, or fiber-map references; final-model identity; realized
tau, Coverage, and branch; byte counts; and SHA-256 values. For the current
formal all-available publications it must contain 112 unique endpoint entries.

The renderer must not rely on an untracked file below `/private/tmp`, infer a
missing endpoint list from a deleted output, or silently narrow an
all-available request to the scales already present in refinement roots. The
root `manifest.json` becomes terminal only after the resolved request,
endpoint results, endpoint index, and every declared output pass validation.

`validate_formal_postprocess_output` is the independent terminal verifier. It
recomputes the immutable request and resolved-request hashes, requires a
terminal complete root manifest, proves exact endpoint count and unique IDs,
matches every endpoint-index row, checks every declared output as a contained
regular file, and scans public JSON and CSV metadata for run-store or runtime-
work paths. The verifier is read-only and must fail on a missing output,
nonterminal endpoint, count mismatch, hash mismatch, path escape, duplicate
endpoint, incomplete index, or forbidden source path. Formal acceptance runs
this verifier after the first render and again after the identical resume.

Every terminal endpoint row separately lists its scientific or figure outputs
and all component manifests that authorize those outputs. For the complete
three-family request, each voxel endpoint binds one paired-fit manifest plus
three voxel-figure manifests, while each fiber endpoint binds one paired-fit
manifest plus one fiber-spatial manifest. Root completion requires these exact
component rows; the terminal verifier opens every component manifest, requires
terminal complete status, and rejects a missing, duplicated, uncontained, or
unlisted component manifest even when all image files happen to exist.

Declared-output validation is format-aware. PNG files must decode through
Pillow with positive dimensions; PDFs must have a valid PDF envelope, parse
through Poppler `pdffonts`, and contain an Arial-family embedded font; SVG must
parse as an SVG document; JSON and CSV must parse structurally; and NIfTI files
must open with a valid nonempty image shape. Other declared files must be
nonempty. These checks complement, but do not replace, the required sampled
visual inspection of rendered PNG and PDF pages.

The terminal verifier is implemented in `formal_postprocess.py` and exposed by
`--validate-output`. Its focused fixture accepts a complete eight-endpoint,
two-scale output after identical resume, rejects a component manifest whose
terminal status is changed to running, rejects a duplicated root component row
that is not in one-to-one endpoint closure, rejects an unrequested component
family, and then rejects the same root after one declared figure is removed. A
PDF-focused fixture also proves that a successful Poppler parse without an
Arial-family font is rejected. These checks are included in the current
37-test visualization suite.

The durable real request resolves PNG and PDF output and passed its tooling
preflight with `/opt/homebrew/bin/pdffonts`. A missing Poppler font inspector
now fails before the formal output root is created or rendering begins.

`formal_postprocess.py` owns the full-cohort root transaction. The existing
paired-fit, direct-voxel section, and normative-fiber section entry points are
single-scale checkpoint runners; each currently writes root-level
`manifest.json`, README, and index files. The formal orchestrator must not call
those root-writing wrappers repeatedly into one directory because a later
scale or component would overwrite earlier root state. Refactor their rendering
work into reusable component functions that write only below the selected
`scales/<scale-id>/` subtree plus component-specific child manifests. The
formal orchestrator alone writes `request.json`, `resolved_request.json`, the
root README and endpoint index, and the terminal root `manifest.json`.

The full orchestrator validates shared publications and rendering resources
once per process. It opens the formal connectome once, reuses the validated
whole-connectome seed/target-pattern cache across all normative-fiber scales,
and never reloads the 7-T anatomy as one full floating-point array. Existing
single-scale public CLIs remain available for explicit checkpoints and retain
their current output contract. Focused tests must prove that two scales and all
three component families coexist without root-file overwrite, that a partial
second scale preserves a complete first scale for resume, and that the root
manifest cannot become terminal while any resolved endpoint or component is
missing.

The implementation boundary is a component API rather than nested checkpoint
CLIs. `render_paired_fit_components`, `render_voxel_section_components`, and
`render_fiber_section_components` receive an already validated publication
catalog, an explicit ordered scale list, the final output root, resolved shared
resources, style, and force policy. They may write only endpoint or component
results below `scales/<scale-id>/...` and return manifest rows; they must not
write root request, index, README, or manifest files. Each historical
single-scale runner delegates its rendering work to the matching component API
and then writes its legacy root contract. `formal_postprocess.py` constructs
the shared catalog and resources once, calls all requested component APIs, and
is the sole writer of the formal root transaction. This separation is required
before a new all-cohort request is executed.

Formal component manifests must not collide inside one model leaf. Paired-fit
state is written as `in_sample_loocv_fit.json`; direct-voxel figures retain one
JSON beside each figure stem; normative-fiber spatial state is written as
`fiber_spatial.json`. Historical single-scale checkpoint CLIs may retain their
legacy `result.json` name because each checkpoint root contains only one
component family. Formal resume keys each component by its own manifest and
never lets a later component replace an earlier complete result.

This component boundary and the first formal orchestrator implementation were
completed on 2026-07-22. The paired-fit and direct-voxel renderers now expose
root-silent multi-scale component APIs. Normative-fiber rendering uses one
validated `FiberSectionContext`, so a formal process opens the connectome,
targets, anatomy metadata, and publication catalog once and writes
`fiber_spatial.json` per model leaf. `formal_postprocess.py` validates the four
canonical publications, resolves an all-available or explicit scale matrix,
writes immutable request and resolved-request records, runs requested component
families with isolated spatial failures, writes one endpoint index and README,
and commits the root manifest as complete only when every resolved endpoint has
all required component rows. Existing single-scale CLIs retain their legacy
root contracts. The visualization suite passed 37 tests, including formal
two-scale coexistence across all three component families, component-local
resume that preserves a complete first scale while repairing a failed second
scale, no component root overwrite, immutable-request rejection, and refusal
to mark missing component rows complete. Real canonical all-cohort execution
remains pending until the Task 17 extension publications required by the
current goal are terminal.

The formal request binds an approximately 8.7-GB 7-T anatomy. Validation now
creates one process-local anatomy identity record and passes it to both voxel
and fiber components; the fiber context rejects a path mismatch and does not
rehash the same anatomy. This prevents a duplicate full-file read during both
validation and rendering while preserving the same SHA-256 and NIfTI geometry
checks.

A publication-only lightweight preflight of the durable request completed on
2026-07-22 without reading the large anatomy. It validated four canonical
publications, 28 identical direct-voxel and normative-fiber scale IDs, and 112
unique core endpoints split into 56 voxel and 56 fiber models. Every endpoint
resolved and verified its final model, final-in-sample summary, and paired
prediction table. The preflight also preserved the existing canonical contract
that a final-model ID is compared only when the domain-specific main final
record provides one; otherwise the completed summary supplies the publication
identity. The full spatial-artifact and shared-resource preflight remains
deferred until the active OSS workload no longer competes for VAL I/O.

The publication-only preflight was then expanded to every requested spatial
source without reading the anatomy. All 112 endpoints passed. The resolved
closure contains 392 direct-voxel source references and 448 normative-fiber
source references, totaling 233,349,261 referenced bytes before deduplication.
This validates the selected raw and smoothed voxel maps, report summaries,
fiber axes, full weights, selected sweet and sour IDs, source selections,
final models, in-sample summaries, and paired prediction tables. Only the
large shared anatomy and external mask/connectome resource identities remain
for the deferred full preflight.

A separate publication-pair audit on 2026-07-22 compared all 112 final-in-
sample summaries with their domain-specific canonical main final records. The
realized tau, Coverage, and branch matched for every endpoint. All 56 direct-
voxel final-model IDs also matched. The normative-fiber main publication uses
its own `normative_fiber_final_model_v1` schema: it stores the branch as
`final_branch` and does not expose `final_model_id`, so the completed in-sample
summary remains the publication identity source for those 56 endpoints, as
already required by the resolver contract. The apparent cross-domain field-
name difference is therefore not a scientific mismatch. The realized
distribution contains 56 direct-voxel rows at tau 200 and Coverage 5 and 56
normative-fiber rows at tau 400 and Coverage 5; branch binding still varies by
endpoint and is never inferred from those profile-first values.

Opaque endpoint IDs remain manifest fields for resume and provenance; they are
not user-facing directory names. Every refinement root contains only its
requested scale. The current roots contain PDQ-39 or FoGQ checkpoints; the
future formal full-cohort root must contain every requested canonical scale.
Spatial output for the remaining scales will be added only after its separate
visual contract is accepted.

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

Formal resume first compares the immutable `request.json` and generated
`resolved_request.json` identities, then validates each endpoint `result.json`
and its declared outputs. A matching complete endpoint is reused. A missing,
failed, partial, changed-source, changed-style, or missing-output endpoint is
rerun without deleting independent complete endpoints. A terminal root
manifest is reusable only when every endpoint in the resolved request is
complete. Historical refinement roots and the deleted 2026-07-19 batch never
enter this resume decision.

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

### Current formal invocation

After the independent OSS, combined execution, and all canonical extension-v2
replays pass their terminal audits, execute the durable full-cohort request in
Conda `leaddbs` with caller `PYTHONPATH` removed:

```bash
env -u PYTHONPATH /opt/anaconda3/envs/leaddbs/bin/python -m \
  my_helper.fiber.core.viz.formal_postprocess \
  --config my_helper/stnsnr/config/four_model_v1/formal_postprocess.json

env -u PYTHONPATH /opt/anaconda3/envs/leaddbs/bin/python -m \
  my_helper.fiber.core.viz.formal_postprocess \
  --validate-output /Volumes/VAL/STNSNr/summary/spot/postprocess/dual_frequency_four_model_v1/task17-formal-postprocess-v1-20260722
```

Repeat the first command without `--force`. The identical request must reuse
every complete endpoint and must not rewrite a completed figure or component
manifest. Then repeat the independent `--validate-output` command. Acceptance
requires both terminal validations to pass, exact 112-endpoint closure, all
three requested component families, format-aware output checks, sampled visual
inspection, and no run-store path in public metadata.

The read-only production preflight passed on 2026-07-22 with the exact request
above and `--validate-only`. It resolved four completed canonical publications,
28 scales, 112 endpoints, and the `paired_fit`, `voxel_2d`, and `fiber_2d`
component families. It also verified the anatomy image, both anatomical masks,
the 1.7-million-fiber formal connectome, all 18 target definitions, and the PDF
font inspection tool. The preflight status was `valid`; no figure or output
root was created. Formal rendering remains intentionally gated on completion
and publication of the independent OSS and combined sensitivity lineages.

### Historical formal production request

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

The request and output described in this subsection were executed in 2026-07-19
and were later deleted by the user. They are retained here as historical
acceptance evidence, not as a current invocation source or current deliverable.
The next formal invocation requires a newly persisted request manifest and a
new immutable output root as specified in the Status section.

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

A read-only source re-audit on 2026-07-21 reconfirmed the interactive 3D
contract without launching MATLAB during the formal OSS run. Both PDQ-39
examples resolve their scientific inputs through canonical publication roots,
create no FIG, image, PDF, or spin output, and never inspect `.runs`. The voxel
example explicitly requests 0.5 mm inward surface sampling. The scene defaults
retain the reference arrow geometry while applying R, A, and S colors
`#F2000E`, `#0E6AAF`, and `#0CA228`. Voxel surfaces and scored fibers use
separate symmetric `vik` mappings and right-side colorbars; anatomy surfaces
are converted to grayscale truecolor before either statistical colormap is
installed. The PDF export path retains the reference font configuration and
its embedded-font checks. The migrated legacy public entry points remain under
`core/viz`, and `core/visualization` is absent.

The same visual contract was re-audited on the current worktree on 2026-07-22.
The RAS color matrix is exactly `[242, 0, 14; 14, 106, 175; 12, 162, 40] / 255`,
while location, axes padding, line width 5, head size 1, font size 27, and Arial
font are loaded from the byte-matching migrated MyLFP plot defaults. The voxel
path retains signed `vik`, the reference right-side colorbar, and 0.5 mm inward
sampling; the fiber path colors every streamline from its score on an
independent symmetric `vik` scale. Anatomy CData is frozen as grayscale RGB
truecolor before either statistical colormap is installed. Both PDQ-39 scripts
still resolve only canonical publication inputs and leave every output path
empty. The complete visualization suite passed all 37 tests under Conda
`leaddbs`.

A separate read-only paired-fit input audit on 2026-07-21 traversed all 112
canonical final-in-sample v2 summaries and their published final-model records.
The inventory contains 56 reference finals, 46 no-delta add-on finals, and ten
delta-reference-adjusted add-on finals. Every summary contains the required
paired Spearman, Pearson, formal permutation, error, baseline, standard and
relative fit, and optimism-gap fields. Both in-sample and LOOCV schedules
request and retain 10000 finite permutations, all subject masks and predictions
are complete, and every prediction table has the paired outcome, in-sample,
LOOCV, and baseline columns with the declared subject count. Selected tau,
Coverage, branch, final identity, scale, and model family match the corresponding
domain-specific canonical `final_model.json` for every endpoint. No hard-coded
main-analysis tau or Coverage was used in this verification.

The paired inference and publication suites were replayed on the current
worktree on 2026-07-22 and passed 18 tests plus two subtests. A fresh public-only
audit then verified all 112 canonical endpoint summaries and all 112 sibling
prediction tables. Every summary is technically completed, uses matching
in-sample and LOOCV subject masks, retains 10000 requested and finite
permutations for each analysis, and reports finite Spearman, Pearson, nominal
p, formal permutation p, standard and relative fit, model and baseline error,
and optimism fields. Standard `in_sample_r2`, `in_sample_relative_r2`,
`loocv_r2`, and `loocv_q2` are present; the deliberately unsupported
`in_sample_adjusted_r2` is absent. Every table has the exact subject, outcome,
in-sample prediction, LOOCV prediction, and both baseline-prediction columns,
with no empty cell and a row count matching its endpoint summary.

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

Historical real-data production evidence was collected on 2026-07-19. That
request resolved four completed canonical publications, rendered all 112 final
endpoints with zero failures, and produced 448 PNG/PDF outputs. All endpoint
manifests and files passed structural validation; 224 PNG files decoded, and
224 PDF files passed file-level integrity checks. Reference and add-on examples
from both physical domains passed visual review. Repeating the identical
request reused all 112 endpoint outputs without changing their byte counts or
nanosecond modification times. No run-store fallback was used. That historical
batch was subsequently deleted and is not current formal acceptance evidence.
The configured 2026-07-22 formal output root is absent, so the current durable
112-endpoint render, identical resume, independent output validation, and
sampled visual review remain open until the active OSS and combined sensitivity
publication sequence has completed. Canonical jitter-v2 publication is already
complete in both public domains.

The visualization unit suite was repeated under Conda `leaddbs` on 2026-07-22
after the formal component-manifest closure changes and passed all 37 tests.
The test launcher must not expose the whole `my_helper/fiber/core` directory as
a top-level Python path: that directory contains the project namespace
`coverage`, which can shadow the unrelated third-party module expected by
Numba. The reproducible launcher places only a temporary `dual_frequency`
package link on `PYTHONPATH`; project imports continue to resolve from the
repository root. This is test-path isolation and does not modify production
imports or scientific code.

The publication and formal-postprocess component boundary was replayed again
on 2026-07-22 and passed all 22 focused tests. The current evidence covers
self-contained extension inputs, rejection of technical-failure OSS payloads,
component-local resume, immutable request enforcement, and refusal to commit a
terminal root without complete component closure. These temporary-fixture tests
do not replace the still-pending all-cohort render from the canonical formal
publications.

A current 3-D contract audit on 2026-07-22 confirmed that both PDQ-39 example
scripts resolve their inputs from the canonical model-set publications and
create visible interactive windows without requesting FIG, image, PDF, or spin
output. The voxel example explicitly uses a 0.5-mm inward sampling depth and
the signed vik surface with its right-side colorbar. The fiber renderer maps
each displayed fiber score through the same symmetric vik colormap and creates
an independent fiber colorbar. Anatomy surfaces are converted to grayscale RGB
truecolor before any scientific colormap is applied. The migrated RAS-triad
implementation, default style, transparent PDF exporter, and both spin
exporters are byte-identical to the MyLFP reference files; the configured RAS
colors remain the requested red, blue, and green values while line width, head
size, font size, and Arial font remain unchanged from the reference.

A fresh real-publication paired-fit smoke on 2026-07-22 consumed only the four
canonical main and final-in-sample publications and rendered all four PDQ-39
model families below `/private/tmp/task17-pdq39-paired-fit.ApYPm7`. It completed
four endpoints with zero failures and produced one PNG and one PDF per endpoint.
Visual inspection confirmed complete in-sample and LOOCV panels, preserved
Boxsize geometry, finite subject points, fitted curves and confidence ribbons,
unclipped labels, and readable Spearman and formal permutation annotations.
Each PNG decoded at 1781 by 1037 pixels. Each PDF contains one page at the same
physical layout and embeds subset Arial and Arial Bold TrueType fonts. An
identical request reported all four endpoints as reused. Every endpoint PNG,
PDF, and result JSON retained its modification time, byte count, and SHA-256;
only the root README, endpoint index, and aggregate manifest were refreshed to
record the replay, with README and index bytes unchanged. This accepts the
real-data component and resume behavior but remains a temporary single-scale
smoke, not the pending 112-endpoint formal output root.

The publication and visualization regression was rerun on 2026-07-22 after
prepared scientific arrays migrated to persisted indexed views. All 42 focused
tests passed. This proves that self-contained extension replay, public-only
input validation, visualization defaults, scene contracts, and fit-plot
contracts still accept the updated publication boundary. It does not replace
the pending canonical all-endpoint postprocess run after OSS and combined
publication complete.
