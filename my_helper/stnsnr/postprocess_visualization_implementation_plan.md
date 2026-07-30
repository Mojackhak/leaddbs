# Task 17 Postprocess Visualization Implementation Plan

> **Output-layout authority.**
> `my_helper/stnsnr/dual_frequency_output_contract.md`
>
> Visualization algorithms and rendering behavior remain specified here.
> Their formal outputs are now integrated below the matching model, scale, and
> role. Any standalone postprocess result root, root aggregate index, or
> versioned output wrapper described later in this document is historical.

The cross-plan production evidence ledger is
`my_helper/stnsnr/task17_three_plan_acceptance_audit.md`. It records terminal
acceptance evidence without replacing this visualization contract.

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

Current status on 2026-07-26: the complete v2 display-smoothing repair is
promoted and accepted, and the real public-only preflight passes for four
canonical publications, 28 scales, 112 endpoints, and all three requested
component families. The formal output replay remains ordered after OSS-v2 and
combined-v2 publication.

Current minimal-resume contract on 2026-07-27: normal formal postprocess
admission parses the request JSON and checks its required consumed fields.
Resume does not compare request, source, style, repository, or code hashes.
Each completed component writes its own `complete.json` after its result and
outputs, and the formal root writes `complete.json` last after terminal
publication. A result path paired with its completion marker is skipped by
path; a missing pair reruns only that component. `--force` moves the existing
formal output root to the operating-system Trash and creates a fresh root.
Format-aware and scientific consistency checks remain available at the input
publication boundary and through explicit `--validate-only` and
`--validate-output`; they do not invalidate an already completed formal root.
The focused three-component and formal-orchestrator set passes 49 tests. After
the legacy-entry completion-marker change, the complete visualization suite
passes all 61 tests with warnings treated as errors.

The same path-and-marker rule applies to the repository-owned interactive 3-D
scene input preparation. Each scale and model family uses the fixed directory
`<scale-id>-<model-family>`, writes `manifest.json`, then writes
`complete.json` last. An existing pair is returned without reopening the
publication. A missing pair rebuilds only that scene input after moving an
incomplete directory to Trash. Explicit `force` validates the requested
publication input first, moves the prior directory to Trash, and creates a
fresh input. Source hashes remain publication-boundary evidence during an
actual build and never select a new resume directory.

The focused 3-D scene-input and MATLAB-wrapper set passes eight tests. These
tests prove fixed output naming, last-written marker publication, reuse without
reopening the publication, local incomplete-target replacement, explicit force
replacement, and validation before Trash mutation.

The still-public legacy `viz.postprocess` entry point follows the same minimal
resume rule. Admission parses the requested JSON and required fields. A root
`manifest.json` plus `complete.json` returns the terminal result without
reopening publications. Inside a nonterminal root, an endpoint
`manifest.json` plus endpoint-local `complete.json` skips only that endpoint.
Request hashes and output-file scans do not gate reuse. Explicit force
validates the publication catalog, moves the old output root to Trash, and
rebuilds the same path. This legacy entry point remains separate from the
formal 112-endpoint output contract.
Endpoint IDs are validated once as unique, nonempty single path components
because they name directories below `endpoints/`. The focused boundary fixture
rejects dot, parent, and nested path values; the complete visualization
directory remains at 61 passing tests.

The complete public visualization-entry test module passes 29 tests with
warnings treated as errors, including terminal reuse without reopening
publications, endpoint-local partial resume, force replacement, and
preservation of the existing root when force admission fails. The complete
visualization directory passes 61 tests with warnings treated as errors.

Formal postprocess admission applies the same split. Before a terminal root
return it validates only the JSON schema, requested component closure, nonempty
output path, and the object types of `publications`, `styles`, and `resources`.
It does not resolve those publications or resources until work is required.
Thus malformed required request fields remain visible while a valid terminal
resume performs no scientific or rendering I/O. The focused terminal-resume
fixture and the complete 61-test visualization directory pass with warnings
treated as errors.

The real public-only `--validate-only` preflight was repeated after Decisions
69 through 71 using the current uncommitted implementation. It again resolved
four canonical publications, 28 scales, 112 final endpoints, `paired_fit`,
`voxel_2d`, and `fiber_2d`. It verified both masks, the 8.69-GB 7-T background,
the 1.7-million-fiber formal connectome, all 18 fiber targets, PDF and PNG
formats, and `pdffonts`. The status was `valid`. The configured formal output
root was absent before and after the command, proving this replay remained
read-only.

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

The repository-owned static request guard parses `formal_postprocess.json`
once and binds the consumed semantic fields: the four canonical
main/final-in-sample publication aliases and manifest types, `all_available`,
the ordered `paired_fit`, `voxel_2d`, and `fiber_2d` component closure, the
formal output root, and all four shared resource paths. Every publication and
output path must remain outside `.runs`, `tasks`, `work`, and `runtime_work`.
Raw JSON byte identity is not a gate: whitespace, key ordering, line endings,
and equivalent serialization do not alter the request. This static guard reads
no publication payload and cannot replace the later 28-scale, 112-endpoint
canonical preflight or render.

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

A historical selected-map derivative audit on 2026-07-23 found that the canonical
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
This finding and the pre-promotion instructions below are retained as
transaction history. The promotion completed on 2026-07-26 as recorded later
in this section; only the formal render remains pending.

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

Formal postprocess preflight must fail until every selected one-millimeter and
two-millimeter direct-voxel display derivative has its canonical metadata
sidecar under the publication root. The sidecar must bind the indexed payload
path, SHA-256, byte count, selected raw benefit-map path, requested FWHM,
`masked_normalized_gaussian_original_roi_v2`, and
`original_finite_benefit_roi`; its input and output finite-voxel counts must be
positive and identical. The sidecar is deterministic provenance paired with
the already indexed NIfTI, not a run-store fallback. This gate prevents
`--validate-only` or the formal renderer from accepting the current mixed v1/v2
publication before the repair transaction commits.

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

The repository-owned repair command was implemented on 2026-07-23. Seven
transaction fixtures cover deterministic staging, read-only validation,
same-volume Trash promotion, identical repeated promotion, refusal to overwrite
an existing stage, source-index drift, invalid Trash placement, staged-payload
tampering, canonical metadata drift before manifest withdrawal, and resume
after an injected interruption with the model manifest withheld. All seven
pass. The affected publication, repair, and formal postprocess regression
passes 30 tests under Conda `leaddbs`; the visualization
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

The frozen promotion sequence is:

```bash
env -u PYTHONPATH /opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/fiber/pipelines/repair_task17_display_smoothing_publication.py validate \
  --publication-root /Volumes/VAL/STNSNr/summary/spot/direct_voxel/dual_frequency_four_model_v1 \
  --stage-root /private/tmp/task17-display-smoothing-v2-stage.zAofAX

env -u PYTHONPATH /opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/fiber/pipelines/repair_task17_display_smoothing_publication.py promote \
  --publication-root /Volumes/VAL/STNSNr/summary/spot/direct_voxel/dual_frequency_four_model_v1 \
  --stage-root /private/tmp/task17-display-smoothing-v2-stage.zAofAX \
  --trash-root /Volumes/VAL/.Trashes/501/task17-display-smoothing-v1-20260723

env -u PYTHONPATH /opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/fiber/pipelines/repair_task17_display_smoothing_publication.py validate \
  --publication-root /Volumes/VAL/STNSNr/summary/spot/direct_voxel/dual_frequency_four_model_v1 \
  --stage-root /private/tmp/task17-display-smoothing-v2-stage.zAofAX
```

Before promotion, the Trash target was absent, the retained stage was present,
and the canonical completed model manifest was present. Those preconditions
were checked after the then-active OSS segment exited. They are historical
transaction evidence and are superseded by the completed promotion below.

The frozen promotion sequence completed on 2026-07-26 after the guarded OSS
segment had terminated and a process audit found no runner or descendant.
Pre-promotion validation reopened all 112 staged targets against canonical raw
support, recorded 108 changed NIfTIs, and matched repair-manifest SHA-256
`dff3ab60616b2bd9d77075bc6781f6ef928db666f1052ac31d5f02f4088f6b5c`.
Promotion archived the replaced v1 files under
`/Volumes/VAL/.Trashes/501/task17-display-smoothing-v1-20260723`, atomically
installed all v2 payload and metadata pairs, restored model-manifest SHA-256
`6edb8266c05f39fae45aea0cc9a91d6354518e986f55c5e65262d2b127b07fd1`,
and installed artifact-index SHA-256
`9ea5003edcd97242d79d3e6cfbf92b770ab157cd1c54c21fe7d963b897331f9c`.
Post-promotion validation accepted the canonical root. A second identical
promotion preserved the index, model manifest, and Trash transaction bytes;
the transaction SHA-256 is
`b718060bb832e5c28a1d002cbff80c7380099413c70390fbb8e6a9e9fae52ae8`.
Formal postprocess may now pass its display-smoothing input gate.

The real public-only `--validate-only` preflight was repeated immediately
after promotion. It passed with status `valid`, resolving four completed
canonical publications, 28 scales, 112 endpoints, and the ordered
`paired_fit`, `voxel_2d`, and `fiber_2d` components. The accepted anatomy,
right-sided STN and SNr masks, 1.7-million-fiber formal connectome, all 18
fiber targets, PNG/PDF formats, and PDF font inspector also passed. The command
created no output root and read no run-store path. This closes the promoted
input gate but does not authorize the full render before OSS-v2 and combined-v2
become terminal.

A later read-only replay on 2026-07-26 exposed one over-strict paired-fit
preflight rule. All 56 normative-fiber endpoints reproduce the published
in-sample metrics, LOOCV Spearman statistic and nominal p-value, LOOCV
standard R2, and LOOCV baseline errors from `predictions.csv`. The secondary
LOOCV Pearson, Q2, model RMSE, and model MAE fields come from the independent
formal-permutation observed calculation and therefore need not be
floating-point identical to the inherited main-model prediction table. The
largest observed absolute difference was 0.00261, while every primary LOOCV
Spearman statistic was identical. The preflight contract must therefore
compare only metrics produced from the same published prediction arrays.
Every summary metric remains required and finite, every prediction row remains
required and finite, and the primary LOOCV Spearman statistic remains an exact
table-to-summary invariant. This narrows a duplicated numeric check without
weakening the scientific statistic or publication boundary.
After implementation, the 21 focused formal-component tests and all 55
visualization tests passed with warnings treated as errors. The real
public-only preflight then passed again with four canonical publications,
28 scales, 112 endpoints, and all three requested component families.

A fresh repository-local static audit on 2026-07-26 confirmed that
`default_nifti2patch_config.m`, `default_plot_patch_config.m`,
`ea_nifti2patch.m`, `ea_plot_patch_leaddbs.m`, `ea_add_ras_triad.m`,
`ea_refresh_ras_triad.m`, and `ea_export_figure_transparent.m` remain
byte-identical to their declared MyLFP source files. The old
`my_helper/fiber/core/visualization/` directory is absent, and production code
does not import or add the MyLFP checkout at runtime. Both interactive examples
still resolve canonical publication inputs, the voxel example requests
0.5-millimeter inward sampling, the RAS colors remain `#F2000E`, `#0E6AAF`,
and `#0CA228`, and the signed voxel and fiber paths retain independent `vik`
colorbars with grayscale truecolor anatomy. The complete visualization suite
passed all 42 tests under Conda `leaddbs`. This is implementation evidence only;
the final real-scene review and full 112-endpoint render remain pending.

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

The primary 3D voxel source is the formally published display derivative
`report/display/benefit_map_smooth_fwhm1mm.nii.gz`. Here `1 mm` is Gaussian
FWHM display smoothing, not voxel resolution. The raw restored signed
full-sample weight NIfTI remains the scientific source, but the 3D renderer
must not recompute smoothing or substitute the raw or 2 mm display map. Its
surface rendering uses the migrated MyLFP `default_nifti2patch_config` and
`default_plot_patch_config` contracts: mask geometry, inside-only scalar
sampling at 1 mm depth, the `vik` diverging colormap, symmetric color
limits, gray missing data, the reference texture-lighting profile, and a
right-side colorbar at the reference position. Sweet and sour binary NIfTIs
remain optional selection-mask overlays; they do not replace the signed
heatmap or its colorbar.
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
renders the complete published candidate library rather than only the selected
libraries. Its resolved MAT input contains concatenated Lead-DBS `fibers`, one
point-count entry in `idx` per candidate fiber, one canonical `fiber_ids`
entry, one aligned full-sample `scores` entry, and one categorical
`fiber_roles` entry in exactly the same order. Role zero identifies an
unselected candidate, role one identifies a selected sweet fiber, and role
minus one identifies a selected sour fiber. The selected sweet and sour sets
must be disjoint subsets of the candidate axis.

The categorical 3D display does not map score magnitude to color. Unselected
candidate fibers use opaque RGB `#CCCCCC`; selected sweet fibers use opaque
`#F2000E`; selected sour fibers use opaque `#0E6AAF`.
Unselected candidates are rendered as a lightweight path layer, while selected
fibers remain the foreground layer. The formal renderer uses continuous path
lines for all three roles: 0.25-point candidate lines and 0.50-point selected
lines. It must not subsample path points or reduce a tube mesh in this mode.
The legacy tube representation remains an explicit interactive option rather
than the formal default. The renderer must display every candidate fiber and
must not silently apply the Lead-DBS 1,000-fiber sampling ceiling.
The aligned scores remain in the resolved input and export manifest for
scientific provenance, but the categorical figure uses a discrete three-item
legend instead of a continuous colorbar. Its symbols are horizontal lines and
its labels are white on the default black fiber-scene background.

The fiber-only default camera is a single orthographic view with azimuth zero,
elevation zero, camera view angle 3.8, up vector `[0 0 1]`, target
`[9.8538 -48.8761 9.6955]`, and position
`[1884.6 -48.8761 9.6955]`. The role-specific view container remains a
nonempty cell array so explicit callers can request multiple views. This
fiber-only default must not replace the two-view voxel camera contract.

Fiber scenes omit the RAS triad by default but retain the configurable
`AddRASTriad` capability. They use a black background and one opaque sagittal
anatomy slice at MNI `x=5 mm`, read from
`/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/backdrops/7T_100um_Edlow_2019.nii`.
The Lead-DBS slice transparency input is 100, corresponding to `FaceAlpha=1`.
The y- and z-planes remain disabled. Anatomy scalar values must be frozen to
truecolor RGB before any statistical colormap is applied.

The 2D renderer consumes derived
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
- applies the configurable `BackgroundColor` immediately after scene creation,
  with a white default and a transparent main axes so interactive display and
  exported output share the same background contract;
- loads the configurable atlas named by `AtlasName`, defaulting to
  `Custom_STNSNr`, from `ea_space([], 'atlases')/<AtlasName>/atlas_index.mat`;
  renders every atlas ROI as a wireframe using its published atlas color,
  `reducepatch(..., 0.5)`, no face fill, and edge alpha 0.15; the atlas can be
  disabled independently without changing the voxel heatmap;
- renders the signed voxel NIfTI through the migrated MyLFP heatmap pipeline
  with symmetric `vik` colors and the reference right-side colorbar; voxel and
  fiber score colorbars use the publication-resolved semantic label
  `Benefit-oriented partial Spearman ρ with {scale_display_name}`;
- may render voxel sweet/sour binary NIfTIs as separate optional overlays;
- renders every resolved candidate fiber, using opaque `#CCCCCC` for unselected
  candidates, opaque `#F2000E` for selected sweet fibers, and opaque `#0E6AAF`
  for selected sour fibers;
- renders formal categorical sweet and sour fibers as continuous 0.50-point
  vector-capable paths; the optional tube mode must not alter the formal
  default;
- sets candidate opacity to 1.0 and uses axes `childorder` rendering with the
  candidate layer behind the selected layers; sweet and sour must remain in
  the opaque foreground and may not be covered by candidate fibers;
- rejects any silent whole-fiber sampling and reports the candidate, sweet,
  sour, unselected, and rendered counts in scene metadata;
- shows a discrete Candidate/Sweet/Sour legend with realized counts, horizontal
  line samples, and white text when the scene is categorical fiber-only;
- adds an independent coefficient-colored fiber scene without replacing the
  categorical scene; this mode renders every candidate fiber as an unsampled
  continuous 0.25-point path, maps its aligned full-sample benefit-oriented
  coefficient through a 256-sample symmetric zero-centered `vik` range, omits
  the Candidate/Sweet/Sour count legend, and displays the publication-resolved
  coefficient colorbar on the right with white ticks and a white Arial label
  on the black fiber-scene background;
- derives each coefficient scene's color limit from the largest absolute
  finite candidate-fiber coefficient for that model, rejects missing,
  nonfinite, zero-only, or misaligned coefficient axes, and keeps the anatomy
  slice as grayscale truecolor rather than applying `vik` to anatomy;
- freezes the continuous-coefficient 3-D fiber visualization as an additive
  contract: all candidate fibers, unsampled geometry, opaque 0.25-point paths,
  model-specific symmetric zero-centered `vik`, black background, grayscale
  truecolor anatomy, white colorbar typography, the frozen fiber camera, and
  no Candidate/Sweet/Sour count legend; the separate categorical view remains
  frozen and must continue to be available;
- retains the configurable RAS orientation helper with arrow colors `#F2000E`,
  `#0E6AAF`, and `#0CA228`, but disables the entire triad by default for fiber
  scenes and their formal exports;
- uses one fiber-only orthographic default view while retaining the general
  multi-view export interface and leaving voxel camera defaults unchanged;
- renders the configured 7T anatomy backdrop only at MNI `x=5 mm`, with
  transparency input 100, and converts it to truecolor before applying
  statistical colors;
- retains Lead-DBS anatomy, camera, atlas, RAS orientation, transparent export,
  and spin-export helpers from the migrated MyLFP surface code;
- exports PNG and PDF through the repository-local migrated
  `ea_export_figure_transparent` module; categorical fiber PDF export uses that
  module's `mixed` mode to capture anatomy, atlas, and all fiber paths together
  from the same native MATLAB 3D axes; separate page-coordinate fiber
  projection is forbidden because it can shift fiber geometry relative to the
  anatomy plot box; the axes must retain `childorder` with candidate fibers
  behind foreground sweet and sour fibers; the aligned scene layer uses 600
  DPI, while the discrete legend lines and text remain vector objects;
  continuous line rendering must prevent the former streamtube tile artifact;
  Greek-symbol handling, base font, fallback fonts, colorbar font sizes, and
  text interpreters come from the migrated MyLFP
  `default_plot_patch_config` contract;
- assigns stable tags and user data so sweet, sour, voxel, fiber, and anatomy
  objects remain independently controllable;
- exports a `.fig` scene plus requested static views.

The configurable PDF export contract is model-role based rather than
anatomy-name based. `mh_viz_default_model_views()` retains the ordered
two-element `views.reference` and `views.addon` cell arrays used by voxel
export. `mh_viz_default_fiber_views()` returns the one-view fiber defaults
below. Callers may replace either cell array with one or more
Lead-DBS-compatible view structs before export.

| Role | View | az | el | camva | camup | camproj | camtarget | campos |
|---|---:|---:|---:|---:|---|---|---|---|
| reference | 1 | 0.8823 | 0.1224 | 0.3500 | `[0 0 1]` | orthographic | `[9.8725 -14.8273 -6.5437]` | `[-841.1497 -1612.5 481.0182]` |
| reference | 2 | -0.8227 | -0.1286 | 0.3500 | `[0 0 1]` | orthographic | `[8.5895 -16.9006 -8.6190]` | `[1046.8 1485.5 415.3169]` |
| addon | 1 | 0.8823 | 0.1224 | 0.5000 | `[0 0 1]` | orthographic | `[9.6266 -16.6089 -12.8113]` | `[-842.3468 -1613.8 474.5999]` |
| addon | 2 | -0.8227 | -0.1286 | 0.5000 | `[0 0 1]` | orthographic | `[9.1244 -16.2821 -12.1207]` | `[1047.3 1486.1 411.8152]` |

The fiber-only default for both roles is:

| Role | View | az | el | camva | camup | camproj | camtarget | campos |
|---|---:|---:|---:|---:|---|---|---|---|
| reference | 1 | 0 | 0 | 3.8000 | `[0 0 1]` | orthographic | `[9.8538 -48.8761 9.6955]` | `[1884.6 -48.8761 9.6955]` |
| addon | 1 | 0 | 0 | 3.8000 | `[0 0 1]` | orthographic | `[9.8538 -48.8761 9.6955]` | `[1884.6 -48.8761 9.6955]` |

`mh_viz_export_scene_views()` accepts a completed interactive scene, an output
directory, and the role `reference` or `addon`. It applies each ordered view,
refreshes the RAS triad only when the caller requires one, exports an opaque
mixed-content PDF with the requested background and reference Arial
typography, and restores the pre-export interactive camera.
The exporter reapplies the camera fields directly to the requested scene axes
after any Lead-DBS compatibility call and verifies the resulting projection,
view angle, up vector, target, and position before publishing each PDF. A
camera mismatch fails closed instead of exporting a plausible but incorrect
view. After every camera application, both role views use the same soft
camera-aligned three-light contract. `CamLight` is the key, `LeftLight` is the
camera-relative fill, and `CeilingLight` is a weak top light; `RightLight`
remains off. All three active lights are neutral white so the native Lead-DBS
blue, pink, and yellow light colors cannot bias the signed `vik` colormap.
They use Gouraud lighting, dominant ambient contribution, restrained diffuse
shading, and minimal specular reflection. This prevents the second oblique
view from becoming dark while retaining modest surface depth and without
changing voxel values or the `vik` colormap.

`mh_viz_export_pdq39_voxel_pdfs()` is the noninteractive publication entry
point for the four PDQ-39 voxel PDFs. It builds the reference and add-on scenes
with the same strict-headless contract as MyLFP
`recipes/stnsnr/viz/med/surface_med.m`: `FigureVisible='off'`,
`FigureBackend='matlab'`, and `StrictHeadless=true`. It therefore creates a
native hidden MATLAB figure instead of an Elvis viewer window, verifies that
every newly created figure remains hidden, exports the two frozen views for
each role, and closes every internal figure on success or failure. The
existing `open_pdq39_*_voxel_scene.m` examples remain interactive and are not
used by the silent exporter.

Strict headless applies to the complete scene-build and export interval, not
only to the final figure state. The root hidden-figure default must remain
active until all role views have been exported. Formal detached macOS jobs
must invoke MATLAB with `-nodisplay -batch`; `-batch` without `-nodisplay`
does not meet the publication requirement that no graphics window becomes
visible.

All-scale 3-D publication is parallel across scale IDs. The launcher starts
independent `MATLAB -nodisplay -batch` processes, assigns one scale to each
process, and keeps scale assignments disjoint. Its default concurrency is half
of the host logical CPU count, rounded down with a minimum of one process.
This execution default is derived locally and is not exposed as a model or
workflow parameter because it cannot change a scientific result. Each scale
retains deterministic output paths, so a resumed launch skips complete scale
components by path and reruns only a missing or explicitly replaced
component.

The frozen medium-contrast lighting preset uses Cam intensity `0.98`, Left
intensity `0.14`, Ceiling intensity `0.08`, ambient strength `0.78`, diffuse
strength `0.22`, specular strength `0.12`, specular exponent `24`, and
specular color reflectance `0.20`. The stronger key and narrower highlight
keep the surface defined while the high ambient term improves global
visibility and the lower diffuse term limits directional contrast.

The lighting helper must preserve the native Elvis lighting-control contract.
`ea_mnifigure()` publishes the `CamLight`, `RightLight`, `LeftLight`, and
`CeilingLight` handles as figure app data, and the native
`ea_set_lighting` toolbar app retains those handles. The scene lighting helper
must therefore reuse valid native light objects rather than delete them. The
frozen three-light presentation maps the key to `CamLight`, maps the fill to
`LeftLight`, enables the weak `CeilingLight`, and keeps `RightLight` valid but
hidden. Any unrelated light objects may be removed. Reapplying a camera or
exporting a view must update the same handles and refresh the figure app data
so opening the native lighting panel and changing each light toggle cannot
reference a deleted graphics object. This compatibility rule changes
presentation state only and does not alter the voxel, fiber, atlas, or
statistical data.

The native lighting panel must also display the active frozen material values.
When Elvis has no native `atlassurfs`, the unmodified app initializes its five
sliders from App Designer defaults rather than from the rendered voxel patch.
The scene therefore publishes a presentation-only lighting preset as figure
app data and replaces only its `Manually Set Lighting` callback with a
repository-local adapter. The adapter constructs the unchanged native
`ea_set_lighting` app, then synchronizes Ambient, Diffuse, Specular Strength,
Specular Exponent, and Specular Color Reflectance to the active scene values.
The native button and slider callbacks remain responsible for subsequent user
changes.

The displayed material values and the native slider mutation scope must be
identical before the panel opens. `ea_set_lighting` applies each material
slider to every patch and surface in the figure, including face-less atlas
wireframes and hidden anatomy slices. The scene preset must therefore
initialize that same complete object set. It must not skip `FaceColor=none`
patches or surfaces. This prevents the first slider callback from silently
changing an atlas wireframe from the MATLAB default ambient strength or
changing anatomy surfaces from their independent defaults. Applying material
properties does not alter the anatomy RGB `CData`, direct color mapping,
voxel values, or the `vik` colormap.

Elvis navigation controls must target the figure that owns the clicked
toolbar. Legacy `ea_defaultview` and `ea_defaultview_transition` discover a
figure by searching for `Electrode-Scene` in its title, which fails after a
postprocess example assigns a descriptive PDQ-39 title and can select the
wrong scene when several viewers are open. Both APIs must retain their legacy
signatures while accepting an explicit figure handle. The `ea_elvis` save,
display-default-view, initialization, and mouse double-click call sites must
pass their own figure handle. A descriptive title must not be part of the
functional navigation contract.

The compatibility repair was verified on 2026-07-25. A synthetic MATLAB
regression reused all four native handles, removed only an unrelated light,
and reapplied the preset twice without changing handle identity. A real
canonical-publication-backed PDQ-39 reference voxel scene then invoked both
the `Auto-adjust Lighting` and `Manually Set Lighting` toolbar callbacks and
toggled all four state buttons off and on without a deleted-object error. The
final regression confirmed that the panel opened from the toolbar with Cam,
Left, and Ceiling enabled, Right disabled, and slider values
`0.78/0.22/0.12/24/0.20`. The complete Python visualization suite passed with
57 tests.

The scope and navigation repairs were verified on 2026-07-26 against the
canonical-publication-backed PDQ-39 reference voxel example. The figure
contained two patches and three anatomy surfaces. Triggering each of the five
native material callbacks at its displayed value produced a maximum
before-versus-after property difference of zero across all five objects. The
same figure retained its descriptive title without `Electrode-Scene`; its
toolbar callbacks successfully saved the current view and displayed the
saved default view through the explicit figure binding. The preference file
was restored after the test. The complete Python visualization suite again
passed with 57 tests.

The `Custom_STNSNr` atlas has a frozen role mapping verified against its
`atlas_index.mat`: ROI 1 is `SNr.nii.gz` and ROI 2 is `STN.nii.gz`. Add-on
exports show only ROI 1; reference exports show only ROI 2. All other atlas
wireframes are hidden only for the export and their original visibility is
restored afterward. The four PDQ-39 interactive examples open reference models
with reference view 1 and ROI 2, and add-on models with add-on view 1 and ROI
1, rather than the generic MATLAB 3-D view. The scene constructor applies an
explicit `ViewStruct` for both voxel and fiber scenes; the voxel heatmap path
must not bypass the caller-supplied camera.

To match `surface_med.m` and prevent a slice plane from occluding the supplied
oblique cameras, PDF export hides anatomy slices by default and restores their
prior visibility afterward. `IncludeAnatomySlices=true` explicitly retains
them when required.
Default files are `<prefix>_<role>_view01.pdf` and
`<prefix>_<role>_view02.pdf`. Existing files are never replaced implicitly.
The export changes camera and presentation only; it does not mutate voxel,
fiber, atlas, color, or scientific input data.

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
figures. The heat colorbar label is
`Benefit-oriented partial Spearman ρ with {scale_display_name}`.
`scale_display_name` is resolved from the formal direct-voxel publication's
SHA-256-verified `study_base.json` using the same exact-label contract as the
normative-fiber figures.

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
composition and therefore uses explicitly different scoring and mapping fiber
universes. It publishes two target-score branches. The primary branch scores
targets from the complete coverage-qualified final resolver axis `C_r`; the
selected sweet-and-sour branch is retained as a visualization-only sensitivity
derivative from `S_r`.
Target membership `m_it` is one when any segment of fiber `i` intersects
target `t` and zero otherwise. Multiple intersections with one target remain
one hit, and overlapping targets are evaluated independently. The primary
target score for model role `r` is:

```text
T_coverage_rt = sum_(i in C_r)(m_it * q_i * s_ri) / sum_(i in C_r)(m_it * q_i)
```

`C_r` is exactly the published final resolver `valid_fiber_ids.npy` axis aligned
to `full_weights.npy`. It is not the full 1,700,000-streamline connectome. The
retained selected sweet-and-sour sensitivity target score is:

```text
T_selected_rt = sum_(i in S_r)(m_it * q_i * s_ri) / sum_(i in S_r)(m_it * q_i)
```

The seed-voxel composition instead uses every canonical streamline in the
formal connectome. Each target-score branch is applied independently to the
same cached whole-connectome composition. For whole-connectome streamline `j`,
let `A_brj` contain the targets that the streamline hits and for which branch
score `T_brt` is finite. Its derived target score is the equal-weight mean of
those finite target scores:

```text
A_brj = {t: m_jt = 1 and T_brt is finite}
U_brj = sum_(t in A_brj)(T_brt) / |A_brj|
G_brv = sum_j(I_jv * q_j * U_brj) / sum_j(I_jv * q_j)
```

Here `I_jv` is binary once-per-streamline incidence at seed voxel `v`. With
`a_brjt = m_jt / |A_brj|` for targets in `A_brj`, the same computation is
`H_brvt = sum_j(I_jv * q_j * a_brjt)` followed by
`G_brv = sum_t(H_brvt * T_brt) / sum_t(H_brvt)`. Each `G_brv` is evaluated only inside
the configured right-sided seed: STN for reference and SNr for add-on. A
streamline without any finite scored target is excluded from its branch `G_brv`, never
assigned a zero score, and published as unscored support. The current formal
connectome has no independent quantitative streamline weight, so both target
scoring and voxel composition use `q_i = q_j = 1`.

The explicit spatial catalog is
`my_helper/stnsnr/config/four_model_v1/fiber_spatial_projection.yaml`. It fixes
the full 7 T Edlow anatomy, one right-sided seed per role, the shared ordered
right-sided target catalog, segment-aware intersection, independent binary
target hits, coverage-qualified primary target scoring, selected-library
sensitivity target scoring, all-formal-connectome voxel composition, equal
finite-target averaging, uniform streamline weights, and the
exclude-and-report no-scored-target policy. Every seed and target must be binary, three-dimensional,
canonical RAS, and on the exact projection grid. Geometry disagreement is a
hard failure rather than an implicit resampling step. The 100 micrometre anatomy
is a lazy display resource only and never becomes the projection grid.

The target catalog contains 17 peer targets. `preSMA` is excluded because its
58,848 voxels are a strict subset of the 85,816-voxel `SMA` mask; retaining both
as peers would duplicate one hierarchical territory in per-streamline target
averaging. `SMA` remains the single parent target. This exclusion applies to
primary all-coverage scoring, selected sweet-and-sour sensitivity scoring,
whole-connectome composition, tables, rainclouds, and every raw or smoothed
target-conditioned map.

The accepted display family produces raw, 1 mm FWHM, and 2 mm FWHM versions of
the direct streamline derivative and both target-conditioned branches for each
model role. This gives eighteen independent spatial figures: three direct
streamline-score means, three primary all-coverage target-conditioned scores,
and three selected sweet-and-sour sensitivity target-conditioned scores for
reference, plus the same nine figures for add-on.

All eighteen figures reuse the accepted direct-voxel layout and aesthetics: three
rows for Ax, Cor, and Sag; 25, 50, and 75 percent seed positions; one fixed 12
by 10 mm field per cell; 0.1 mm display sampling; lazy 7 T anatomy; a solid,
fully opaque black 1 point seed boundary on the top layer; Arial typography;
opaque `#D7E3E0` top strips and `#E3DCCF` right strips; a signed `vik` scale
centered on zero; a single right colorbar; 600 DPI; transparent canvas; and PNG,
PDF, and JSON outputs. Each figure derives its own symmetric color range.

The direct-streamline colorbar uses the scale-aware semantic label
`Mean selected-fiber partial Spearman ρ with {scale_display_name}`. Both target-
conditioned branches use the colorbar label `Target-derived fiber partial
Spearman ρ with {scale_display_name}`; their unambiguous branch path and JSON
`target_score_fiber_scope` identify whether a figure is primary all-coverage or
selected sweet-and-sour sensitivity.
`scale_display_name` is the exact nonempty `label` from the requested
`scale_id` entry in the formal input `study_base.json` array
`study.scale_definitions`. The renderer must not guess, normalize, or maintain
a second display-name catalog. It resolves the publication-local
`study_base.json`, verifies it against `study_base_sha256` in the canonical
normative-fiber `model_manifest.json`, requires exactly one matching
`scale_id`, and records the input path, SHA-256, and resolved label in the
postprocess manifest. A rendered vertical label may contain a layout-only line
break to prevent clipping, while the provenance JSON retains the unbroken
semantic label.

The target-score distribution checkpoint adds one independent mirrored
raincloud figure for each model role. It replaces the earlier target-mean bar
without changing the target-score statistic. For each target, the left half
violin and its boxplot contain the selected sweet and sour fibers that intersect
the target. Their mean remains the formal selected-library target score `T_t`.
The right half violin and its boxplot contain every target-intersecting fiber on
the realized final resolver's `valid_fiber_ids.npy` axis, including the selected
fibers. This coverage-qualified universe is not the complete 1,700,000-fiber
connectome and is not a new selection rule.

The central jitter shows every target-intersecting coverage-qualified fiber.
Selected sweet points use `#F2000E`, selected sour points use `#0E6AAF`, and
coverage-qualified fibers outside both selected libraries use `#CCCCCC`.
Unselected points are drawn first and selected points are drawn above them. A
multi-target fiber is shown once under every target it intersects. These
repeated descriptive points are not independent subjects and must not receive
confidence intervals, hypothesis tests, or inferential error bars. The all-
coverage mean is the primary descriptive target score for the new target-
conditioned branch. The selected distribution and mean remain the
visualization-only sensitivity branch. Neither branch is an independent
hypothesis test and neither may replace model fitting or formal inference.

The aggregate CSV, provenance, and chart retain all 17 configured targets.
Targets with no selected-fiber hit remain in their fixed configured position
but receive no `NA` suffix or other missing-value annotation.
The absence of a left distribution indicates that no selected fiber intersects
the target; a right distribution and gray jitter may still be present when
unselected coverage-qualified fibers intersect it. Neither selected nor all-
coverage scores may reorder the chart. Reference and add-on use exactly the
same fixed target order and share one y-axis derived only from the finite
target-intersecting coverage-qualified fiber scores that are actually drawn as
jitter points across both roles. Target means, violins, boxes, and annotations
do not determine the limits. If `jitter_min` and `jitter_max` are the global
finite scatter bounds and `jitter_span = jitter_max - jitter_min`, the shared
limits are `jitter_min - 0.10 * jitter_span` and
`jitter_max + 0.15 * jitter_span`. A constant scatter uses a deterministic
nonzero fallback span based on its absolute value so that the axis remains
valid. The y-axis
label is `Target-derived fiber partial Spearman ρ with
{scale_display_name}`. The provenance JSON retains this exact unbroken semantic
label. The rendered vertical axis may insert layout-only line breaks after
`fiber` and before `with` so the label remains complete within the 25 mm chart
height without reducing the accepted 7 point font.

The fixed order and display labels are `GPe`, `GPi`, `Caudate`, `Posterior
putamen`, `VLP thalamus`, `VLA thalamus`, `RN`, `VA thalamus`, `VM thalamus`,
`PPN`, `SMA`, `M1`, `sPf thalamus`, `Premotor`, `CM thalamus`, `DLPFC`, and `Pf
thalamus`. Canonical IDs remain machine-readable and are not renamed by these
display labels.

The accepted chart geometry ports MyLFP `update_scalar_cfg` for one panel:
`boxsize_base = (8, 25)` mm and `boxsize = (8 * n_targets, 25)` mm. With all 17
configured targets, each accepted inner plotting box is exactly 136 by
25 mm; tick-label and global axis-label margins are additional and cannot
shrink the inner box. The chart uses Arial, no title or strips, 600 DPI,
transparent PNG/PDF export, 0.30 half-violin fill alpha, fully opaque matching
0.5 point violin outlines, central jitter width 0.20, jitter size 2 points,
jitter alpha 1, deterministic seed 42, and a dotted `#404040` zero line. All jitter points
are drawn at the lowest data z-order before violins, boxes, medians, means, and
whiskers so they cannot obscure distribution or summary marks. The left half
violin is value-signed rather than mean-signed: density below zero uses
`#0E6AAF`, and density at or above zero uses `#F2000E`. The split is evaluated
on one common KDE density so color does not create two independently normalized
distributions. The right half violin uses `#CCCCCC`. Each half violin is clipped
to its observed score range and uses deterministic Scott-rule Gaussian KDE. A
distribution with fewer than two distinct finite values omits the density body
while retaining its available box, median, mean, and jitter evidence.

Both half violins carry narrow black boxplots. Every box edge, whisker, cap,
median, and mean stroke is 0.5 point. The standard median is a solid black line
across the box width. The additional mean is a solid black line
whose length is 70% of the box width. Its endpoints are explicitly symmetric
about the box center; a dashed style is forbidden because dash-phase clipping
can make this short mark appear horizontally displaced. Whiskers use the
standard 1.5 IQR rule;
boxplot fliers are hidden because all observations already appear in the
central jitter. Within each unit target slot, central jitter occupies width
0.20, each box has width 0.20, each violin begins at offset 0.22, and its
maximum half-width is 0.24. The left and right box centers are offset by the
same 0.22, so each boxplot's vertical centerline exactly coincides with its
half violin's flat side line. The mean line remains explicitly drawn above the
box, has 70% of the box width, and is horizontally centered on that same
vertical centerline. Target labels replace underscores with spaces for display
and rotate 90 degrees without changing canonical `target_id` values. Every
rotated label is horizontally center-anchored so its rendered bounding-box
center coincides with the corresponding tick coordinate.

The target-score output adds `target_fiber_distributions.csv` beside the
aggregate `target_scores.csv`, plus `target_score_dual_raincloud.png`, PDF, and
JSON. The long table records role, target, canonical fiber ID, fiber score,
selected status, `sweet`, `sour`, or `unselected` class, selected-library target
mean, all-coverage target mean, selected count, and coverage-qualified count.
JSON records the exact order, shared asymmetric limits, scatter bounds and
padding fractions, Boxsize calculation, violin/KDE,
boxplot/mean, colors, jitter seed, source artifacts, study-label provenance,
and output SHA. Resume reuse requires the same valid fiber axis, full weights,
selected libraries, target membership, style contract, and completed outputs.

After PDQ-39 visual acceptance, the same single-scale target-score checkpoint
is applied explicitly to `fogq_score` in a separate output root. Its display
label must resolve from the formal `study_base.json` as `FOGQ score`; it is not
hard-coded or rewritten as a second label variant. Both roles use their realized
final model and the same seed-target catalog, ranking, shared-axis, color,
Boxsize, and descriptive-jitter contracts. This explicit second-scale render is
not authorization for an all-scale batch.

Both score-map families use the same display-only smoothing contract as the
accepted direct-voxel maps. Each FWHM derivative is computed independently
from its raw score map, never recursively from another smoothed derivative. For
raw values `R`, original finite support `F`, and physical-axis Gaussian width
`sigma = FWHM / 2.354820045 / voxel_size`, the algorithm is:

```text
S = Gaussian(where(F, R, 0)) / Gaussian(F)
output[F] = S[F]
output[not F] = NaN
```

The algorithm identifier is `masked_normalized_gaussian_original_roi_v2` and
the support policy is `original_finite_support`. The finite masks of raw,
1 mm, and 2 mm maps must therefore be exactly identical. Smoothing never
expands streamline support or scored seed support. Support-count,
sweet/sour-count, scored/unscored-count, and assignment-fraction maps are not
smoothed. These derivatives are visualization-only and must not feed target
scoring, model fitting, model selection, LOOCV, permutation, bootstrap, or any
other inference.

The human-readable output contract is:

```text
scales/pdq39_score/<reference-or-addon>/fiber/
  direct_streamline/
    maps/
      streamline_score_mean.nii.gz
      streamline_score_mean_smooth_fwhm1mm.nii.gz
      streamline_score_mean_smooth_fwhm2mm.nii.gz
      streamline_support_count.nii.gz
      streamline_sweet_count.nii.gz
      streamline_sour_count.nii.gz
    figures/
      streamline_score_mean_sections.png
      streamline_score_mean_sections.pdf
      streamline_score_mean_sections.json
      streamline_score_mean_smooth_fwhm1mm_sections.png
      streamline_score_mean_smooth_fwhm1mm_sections.pdf
      streamline_score_mean_smooth_fwhm1mm_sections.json
      streamline_score_mean_smooth_fwhm2mm_sections.png
      streamline_score_mean_smooth_fwhm2mm_sections.pdf
      streamline_score_mean_smooth_fwhm2mm_sections.json
    projection_qc.json
  target_conditioned/
    all_coverage/
      maps/
        target_conditioned_score.nii.gz
        target_conditioned_score_smooth_fwhm1mm.nii.gz
        target_conditioned_score_smooth_fwhm2mm.nii.gz
        all_streamline_support_count.nii.gz
        target_scored_streamline_count.nii.gz
        target_unscored_streamline_count.nii.gz
        target_assignment_fraction.nii.gz
      tables/
        target_scores.csv
      figures/
        target_conditioned_score_sections.png
        target_conditioned_score_sections.pdf
        target_conditioned_score_sections.json
        target_conditioned_score_smooth_fwhm1mm_sections.png
        target_conditioned_score_smooth_fwhm1mm_sections.pdf
        target_conditioned_score_smooth_fwhm1mm_sections.json
        target_conditioned_score_smooth_fwhm2mm_sections.png
        target_conditioned_score_smooth_fwhm2mm_sections.pdf
        target_conditioned_score_smooth_fwhm2mm_sections.json
      target_score_qc.json
      voxel_composition_qc.json
    selected_sweet_sour/
      maps/
        target_conditioned_score.nii.gz
        target_conditioned_score_smooth_fwhm1mm.nii.gz
        target_conditioned_score_smooth_fwhm2mm.nii.gz
        all_streamline_support_count.nii.gz
        target_scored_streamline_count.nii.gz
        target_unscored_streamline_count.nii.gz
        target_assignment_fraction.nii.gz
      tables/
        target_scores.csv
        fiber_target_membership.csv
      figures/
        target_conditioned_score_sections.png
        target_conditioned_score_sections.pdf
        target_conditioned_score_sections.json
        target_conditioned_score_smooth_fwhm1mm_sections.png
        target_conditioned_score_smooth_fwhm1mm_sections.pdf
        target_conditioned_score_smooth_fwhm1mm_sections.json
        target_conditioned_score_smooth_fwhm2mm_sections.png
        target_conditioned_score_smooth_fwhm2mm_sections.pdf
        target_conditioned_score_smooth_fwhm2mm_sections.json
      target_score_qc.json
      voxel_composition_qc.json
    tables/
      target_fiber_distributions.csv
    figures/
      target_score_dual_raincloud.png
      target_score_dual_raincloud.pdf
      target_score_dual_raincloud.json
```

The shared physical cache stores one target-membership bit pattern per formal-
connectome streamline and sparse `(seed voxel, target pattern, streamline
count)` composition for both STN and SNr. It is independent of endpoint,
selected model scores, tau, Coverage, and clinical scale, so later endpoints
reuse it without rescanning HDF5. Endpoint-local cache stores selected
streamline geometry, selected target scores, and direct projection data. Cache
identity binds the formal connectome identity, seed and ordered target mask
identities, all-connectome universe, traversal contract, and projection grid.
Repository code identity is not a resume gate. Failed or partial work retains
both shared physical cache and completed role-local outputs.

Acceptance requires exact valid-axis, selected-ID, and score alignment; primary
target scores from every coverage-qualified valid-axis fiber; sensitivity
target scores from the selected sweet and sour library; raincloud comparison
distributions from the final coverage-qualified valid axis; voxel composition
from all canonical
formal-connectome streamlines; binary once-per-streamline target and voxel
incidence; segment-aware rather than vertex-only intersection; exact agreement
with a small brute-force two-universe reference; explicit total, scored, and
unscored support; finite `G_v` only where scored support is positive; `G_v`
within its contributing finite target-score range; physical-cache independence
from endpoint score identity; role-local failure isolation; verified
publication hashes; direct PNG and rendered-PDF inspection; Arial font
inspection; bounded lazy anatomy loading; and full reuse on an identical
second invocation. Smoothing acceptance additionally requires exact raw versus
smoothed finite-mask equality; `NaN` outside the original support; unchanged
shape, affine, orientation, and float32 dtype; nonrecursive raw-map inputs;
recorded physical FWHM and per-axis sigma; and unchanged support/QC maps.

The 2026-07-20 v1 implementation evidence is stored below
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

Scientific review on 2026-07-21 found that v1 incorrectly reused the selected
300-fiber library for seed-voxel composition. The v1 direct complete-path maps
and selected-library target scores remain valid, but its target-conditioned
maps, composition support maps, target-conditioned figures, and composition QC
are superseded and must not be used. Version 2 implements the two-universe
contract above and requires a new output lineage; it does not overwrite or
silently resume the v1 target-conditioned result.

Version 2 real-data acceptance completed on 2026-07-21 at
`task17-pdq39-fiber-spatial-v2-all-connectome-20260721/`. One shared physical
cache scanned all 1,700,000 canonical streamlines and served both model roles.
Reference had all 1,927 seed voxels supported and scored; add-on had 6,183 of
6,192 seed voxels with any streamline support and 6,102 with scored support.
For both roles, total support equalled scored plus unscored support with zero
maximum absolute error, every target-conditioned score stayed within the
finite target-score range, and all finite outputs stayed inside the configured
right-sided seed. All eight direct-map NIfTI SHA-256 values and all target-score
table values matched v1 exactly. Four PNG figures passed visual review, all four
PDFs embedded Arial and Arial Bold, 106 tests and 27 subtests passed with one
optional test skipped, and an identical invocation reused the physical cache
and both completed role results.

Version 3 adds only the confirmed 1 mm and 2 mm FWHM display derivatives under
a new output lineage. It must reuse the version 2 whole-connectome physical
cache and must not overwrite version 2 evidence. It does not change direct raw
maps, selected target scores, all-connectome composition, support maps, or any
scientific result.

Version 3 real-data acceptance completed on 2026-07-21 at
`task17-pdq39-fiber-spatial-v3-smoothed-20260721/`. The shared physical cache
was reused, both model roles completed, and an identical second invocation
reused both complete role results in approximately 12 seconds. All raw score,
support, and QC NIfTI SHA-256 values matched version 2 exactly, as did both
target-score tables. Reference direct, add-on direct, reference target-
conditioned, and add-on target-conditioned maps retained exactly 50,142,
50,571, 1,927, and 6,102 finite voxels, respectively, at raw, 1 mm, and 2 mm.
Every smoothed map remained float32 canonical RAS on the unchanged affine, had
only `NaN` outside its raw support, and recorded sigma values of approximately
0.849 and 1.699 voxels. All eight new PNG figures and all eight Poppler-rendered
PDF pages passed visual inspection; the PDFs embedded Arial and Arial Bold.
The combined visualization and seed-target suite passed 107 tests and 27
subtests with one optional test skipped.

The ranked target-score checkpoint completed on 2026-07-21 at
`task17-pdq39-fiber-spatial-v6-target-bars-20260721/`. Both model roles
completed with zero failures and an identical invocation reused both complete
role results. The aggregate outputs and both x-axes retain all 18 configured
targets without any `NA` tick suffix. Reference has 16 finite target means and
2 empty no-hit positions
(`Pf_thalamus` and `CM_thalamus`); add-on has 13 finite target means and 5
empty no-hit positions (`VM_thalamus`, `VLA_thalamus`, `sPf_thalamus`,
`Pf_thalamus`, and `RN`). Both inner Boxsizes remain 108 by 25 mm. The long descriptive
tables contain 780 reference and 565 add-on
fiber-target hit rows. Recomputed group means agree exactly with every finite
bar value. Both roles use the shared symmetric y-axis from approximately
-0.747 to 0.747.

Direct PNG inspection confirmed descending finite targets followed by empty
no-hit positions without `NA` labels, complete 90-degree labels, unclipped three-line 7 point Arial
y-axis labels, descriptive jitter, and no title or strip. PNG alpha inspection
confirmed 0.30 bar fills and fully opaque same-color outlines and points, with
positive `#F2000E` and negative `#0E6AAF`. Both PDFs embed subset Arial
TrueType. All 37 tests in `my_helper/fiber/core/viz/tests` passed. This evidence
authorizes only the PDQ-39 checkpoint; it does not authorize batch rendering
of other scales.

The explicitly requested FoG-Q checkpoint completed on 2026-07-21 at
`task17-fogq-fiber-spatial-v1-target-bars-20260721/`. The formal study label
resolved as `FOGQ score`; both roles completed with zero failures and an
identical invocation reused both results. Reference has 15 finite target means,
3 empty no-hit positions (`VLP_thalamus`, `Pf_thalamus`, and `CM_thalamus`),
and 722 descriptive fiber-target rows. Add-on has 10 finite target means, 8
empty no-hit positions (`VM_thalamus`, `VLA_thalamus`, `sPf_thalamus`, `PPN`,
`VLP_thalamus`, `Pf_thalamus`, `CM_thalamus`, and `RN`), and 654 descriptive
rows. Both figures retain all 18 target names without `NA`, use 90-degree tick
labels and an exact 108 by 25 mm inner Boxsize, and share the symmetric y-axis
from approximately -0.886 to 0.886. Direct PNG review found no clipping, and
both PDFs embed subset Arial TrueType. This evidence authorizes FoG-Q as the
second explicit scale only; all-scale batch rendering remains unstarted.

The target-distribution acceptance completed on 2026-07-21 at
`task17-pdq39-fiber-spatial-v8-target-raincloud-20260721/` and
`task17-fogq-fiber-spatial-v3-target-raincloud-20260721/`. Both scales completed
reference and add-on with zero failures, reused the shared 1,700,000-streamline
physical cache, and reused both role results on an identical second invocation.
The PDQ-39 and FoG-Q models each expose 3,401 reference and 2,004 add-on valid
fibers before target intersection. Their long tables contain 7,332 reference
and 3,775 add-on target-hit rows. Reference has coverage-qualified hits for all
18 targets; add-on has hits for 16 targets. Every finite left mean agrees with
the published selected-library `T_t`, every right mean agrees with its grouped
coverage-qualified rows, and every target exactly partitions selected plus
unselected points into total coverage.

Direct inspection of all four PNG figures confirmed distinct left selected-
library and right all-coverage half violins, visible paired boxplots and shorter
dashed mean lines, complete central gray/red/blue jitter, unclipped 90-degree
target labels, shared role-wise symmetric axes, and no title. The PDQ-39 shared
range is approximately -0.747 to 0.747 and the FoG-Q range is approximately
-0.886 to 0.886. All four PDFs embed subset Arial TrueType. The final
visualization suite passed 38 tests. This acceptance replaces only the earlier
bar-plus-jitter figures for the already authorized PDQ-39 and FoG-Q scales; it
does not authorize an all-scale batch.

The refined target-distribution acceptance completed on 2026-07-21 at
`task17-pdq39-fiber-spatial-v9-target-raincloud-20260721/` and
`task17-fogq-fiber-spatial-v4-target-raincloud-20260721/`. These lineages
supersede version 8 and version 3, respectively, for the raincloud figure while
retaining the earlier outputs as provenance. Both scales completed reference
and add-on with zero failures; an identical second invocation reused both role
results and the shared 1,700,000-streamline physical cache. Each chart retains
all 18 targets and has an exact 72 by 25 mm inner Boxsize. The left selected
density is split from one common KDE at zero, with `#0E6AAF` below zero and
`#F2000E` at or above zero. The right all-coverage density remains `#CCCCCC`.
Each box is 0.30 target units wide and centered at the half violin's 0.22-unit
flat-edge offset; its explicit dashed mean line is 70% of the enlarged box
width. Jitter is rendered at z-order 0.5, below violins at 2 and boxes at 4.

Direct inspection of all four PNGs confirmed that the enlarged boxes and mean
lines remain readable, the box centerlines coincide with the violin flat
edges, and the low-layer jitter does not obscure density or summary marks.
The PDQ-39 and FoG-Q long tables retain 7,332 reference and 3,775 add-on rows;
recomputed all-coverage target means match the recorded means exactly. All four
PDFs embed subset Arial TrueType, and the final visualization suite passed 39
tests. This remains a two-scale checkpoint and does not authorize an all-scale
batch.

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

`request.json` is the user-facing request copied into the output root before
rendering. It declares publication aliases, the requested output
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
requires the root `complete.json` and a terminal complete manifest, proves
exact endpoint count and unique IDs, matches every endpoint-index row, checks
every declared output as a contained regular file, and scans public JSON and
CSV metadata for run-store or runtime-work paths. The verifier is read-only
and must fail on a missing output, nonterminal endpoint, count mismatch, path
escape, duplicate endpoint, incomplete index, or forbidden source path.
Request hashes are not recomputed. Formal acceptance runs this verifier after
the first render and again after the identical resume.

Every terminal endpoint row separately lists its scientific or figure outputs
and all component manifests that authorize those outputs. For the complete
three-family request, each voxel endpoint binds one paired-fit manifest plus
three voxel-figure manifests, while each fiber endpoint binds one paired-fit
manifest plus one fiber-spatial manifest. Root completion requires these exact
component rows; the terminal verifier opens every component manifest, requires
terminal complete status, and rejects a missing, duplicated, uncontained, or
unlisted component manifest even when all image files happen to exist.
For a deliberately partial component request, an endpoint whose model unit has
no applicable requested component has an exact expected component count of
zero. The verifier accepts that zero only for the inapplicable endpoint while
continuing to require the exact nonzero closure for every applicable endpoint.
This keeps voxel-only and fiber-only preflights independently verifiable
without weakening the complete three-family production contract.

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
component family. Component completion markers are:

- `completion/paired_fit/complete.json`;
- `completion/voxel_2d/<figure-stem>/complete.json`; and
- `completion/fiber_2d/complete.json`.

Resume checks only the component result path and its marker path. It does not
parse or hash the marker and never lets a later component replace an earlier
complete result.

This component boundary and the first formal orchestrator implementation were
completed on 2026-07-22. The paired-fit and direct-voxel renderers now expose
root-silent multi-scale component APIs. Normative-fiber rendering uses one
validated `FiberSectionContext`, so a formal process opens the connectome,
targets, anatomy metadata, and publication catalog once and writes
`fiber_spatial.json` per model leaf. `formal_postprocess.py` validates the four
canonical publications, resolves an all-available or explicit scale matrix,
writes request and resolved-request records, runs requested component
families with isolated spatial failures, writes one endpoint index and README,
and commits the root manifest as complete only when every resolved endpoint has
all required component rows. Existing single-scale CLIs retain their legacy
root contracts. The visualization suite passed 37 tests, including formal
two-scale coexistence across all three component families, component-local
resume that preserves a complete first scale while repairing a failed second
scale, no component root overwrite, the then-current immutable-request rule,
and refusal to mark missing component rows complete. Decision 69 supersedes
the request-identity resume rule but retains the component and terminal
closure requirements. Real canonical all-cohort execution remains pending
until the Task 17 extension publications required by the current goal are
terminal.

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
and intentionally create no FIG, PNG, PDF, or spin export. The voxel example
uses the publication-indexed 1 mm FWHM benefit-map derivative, 1 mm
inside-only sampling depth, and the default configurable `Custom_STNSNr`
wireframe atlas. The migrated export helpers remain available for an explicit
later export request but are not part of the cohort-wide endpoint batch
contract.

## Resume And Failure Boundaries

Postprocess resume is output-local and path based. A completed component is
reusable when its deterministic result path and component-local
`complete.json` both exist. The marker is not parsed or hashed. A missing pair
makes only that component eligible to render. Source, style, request,
repository, and code identities do not enter this resume decision.

The formal root writes its own `complete.json` only after every resolved
endpoint and requested component is terminal complete. When the root marker
and `manifest.json` exist, a normal invocation returns the stored terminal
manifest without resolving publications or reopening component results. A
stored manifest parse failure remains visible and does not trigger automatic
recomputation. Historical refinement roots and the deleted 2026-07-19 batch
never enter this resume decision.

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
explicit sweet/sour color distinction, 1 mm display sampling, 300 dpi output,
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
example explicitly requests 1 mm inward surface sampling. The scene defaults
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
path retains signed `vik`, the reference right-side colorbar, and 1 mm inward
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

A focused repository fixture must make this prohibition executable rather
than relying on current production values that happen to use the main-analysis
cells. It must publish one voxel endpoint at tau 180 and Coverage 8 and one
fiber endpoint at tau 600 and Coverage 10, pair each with a matching
final-in-sample summary, and require the formal endpoint resolver to retain
those exact values. A modality-wide 200/400 or Coverage-5 fallback must fail
that fixture.
The nondefault-cell fixture and the formal request/component suite passed all
nine tests together under Conda `leaddbs` with warnings treated as errors.

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

The formal paired-fit publisher must enforce this complete source contract
before rendering. A completed endpoint requires paired Spearman and Pearson
statistics, descriptive nominal p values, plus-one two-sided permutation p
values, model-family and all-endpoint BH values, standard R2,
relative-R2/Q2, model error, baseline error, finite subject and permutation
counts, matching subject masks, and all six declared optimism gaps. The
in-sample and LOOCV permutation requests must use the same positive count, and
both retained finite counts must cover their complete requests. The paired
prediction table must contain subject ID, outcome, in-sample prediction,
LOOCV prediction, in-sample baseline prediction, and LOOCV baseline prediction
with the same complete subject count. The unsupported
`in_sample_adjusted_r2` must not be published.

Each endpoint `result.json` and the root `endpoint_index.csv` must expose the
same complete paired metric set. The two fit panels retain compact annotations
for rho and the formal permutation p value; descriptive nominal p values and
the remaining diagnostics stay available in the indexed report without
overloading the figure. Missing, nonfinite, internally inconsistent, or
unpaired evidence must fail that endpoint before any figure is published.
This contract is published as paired-fit postprocess schema v2. An older v1
component has no current component completion marker and therefore is not
reused by the current path-and-marker contract.

The schema-v2 implementation was completed in the isolated integration
worktree on 2026-07-26. It validates all 43 declared paired metrics, the six
required prediction-table columns, complete subject and permutation counts,
probability and correlation domains, nonnegative error metrics, and the
arithmetic identity of all six optimism gaps before rendering. The same metric
mapping is retained in each component result, each formal endpoint result, and
the root endpoint index. Terminal validation independently rechecks the
component, endpoint, and CSV copies. Formal `--validate-only` must apply the
same metric and prediction-table contract while resolving canonical endpoints,
so an invalid source fails during read-only preflight rather than after the
render transaction begins. As a consistency gate only, validation must
recalculate the deterministic Spearman, Pearson, standard and relative fit,
model-error, and baseline-error summaries from the paired prediction table and
compare them with the published values. Figures and result indexes continue to
use the published values; the recalculated values are never substituted, and
formal permutation or BH inference is never recomputed. Forty-four focused
paired-fit and component tests, the complete 54-test visualization package,
and the complete dual-frequency plus visualization regression with 846 tests
and 329 subtests pass with warnings treated as errors.

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
  byte-count, and SHA-256 validation before rendering;
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
on 2026-07-22 and passed all 22 focused tests. That historical evidence covers
self-contained extension inputs, rejection of technical-failure OSS payloads,
component-local resume, the then-current immutable-request rule, and refusal
to commit a terminal root without complete component closure. Decision 69
supersedes only the request-identity resume rule. These temporary-fixture tests
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

Display-smoothing preflight closure on 2026-07-24:

- each formal direct-voxel endpoint now binds the one-millimeter and
  two-millimeter v2 metadata sidecars into `resolved_request.json` with their
  SHA-256 and byte counts;
- preflight rejects a missing sidecar, a payload/path/size/FWHM mismatch, a
  non-v2 algorithm, a changed support policy, or unequal finite-support counts;
- a fresh 2026-07-26 replay of the complete visualization suite passes all 42
  tests with warnings treated as errors, including explicit rejection of a v1
  sidecar; and
- a read-only invocation of the durable formal request now stops at the first
  remaining v1 derivative,
  `adl/reference/report/display/benefit_map_smooth_fwhm1mm.nii.gz`, before
  creating the formal output root.

This is the required pre-promotion behavior. The same request must become valid
only after the staged 112-derivative repair is promoted and the canonical
publication is revalidated.

## 2026-07-29 Full PDQ39 And DWI Worktree Integration Scope

The user replaced the previous acceptance-oriented continuation with a
result-only delivery sequence. The first implementation step is to integrate
the complete clean worktree
`/Users/mojackhu/Github/leaddbs-pdq39-dwi-integration` into the current
`/Users/mojackhu/Github/leaddbs` working tree.

This integration includes both complete source-worktree domains:

- DWI mosaic correction, last-b0 handling, phase-encoding QC, motion QC, and
  related MATLAB and Python entry points; and
- PDQ-39 voxel and fiber visualization, categorical and coefficient-colored
  fiber scenes, target inference, raincloud figures, lighting controls, and
  PDF export.

The integration must preserve the current uncommitted Task 17 changes in the
target working tree. It must not merge any other Task 17 temporary worktree and
must not create a commit or push a remote branch. Files changed by both trees
require a semantic three-way merge; the source-worktree version must not
overwrite newer completion-marker, resume, OSS, combined-publication, or
formal-postprocess behavior in the target.

After the complete source delta is present in the target working tree and the
source worktree is clean, its Git worktree registration must be removed and
the source directory must be moved to the macOS Trash. This step performs no
scientific recomputation, performance acceptance, fault acceptance, output
audit, or final rendering. Final result regeneration is a later step that
consumes the existing completed publication versions.

### Verified overlap resolution

- Fiber postprocess resume remains governed only by the result path and its
  `complete.json`. A reused role must be excluded from both preparation and
  rendering loops.
- Scene-example resume and replacement remain governed by paths,
  `complete.json`, and explicit `force`. Publication or study JSON SHA values
  do not gate reuse.
- The PDQ-39 reference and add-on voxel examples use the repository default
  `VoxelSampleDepthMm` value of `1.0`.

Additional visualization-specific acceptance evidence was collected on
2026-07-21 as part of the historical PDQ-39 rendering line.

The scale-aware target-conditioned fiber label acceptance completed on
2026-07-21. The v4 PDQ-39 request resolved the exact `PDQ39 score` label from
the SHA-256-verified publication-local `study_base.json`, completed both model
roles with zero failures, and rendered the semantic label as `PDQ39 score
target-connectivity-derived fiber model score`. The vertical figure label used
one layout-only line break and remained unclipped on visual inspection. All 26
non-metadata NIfTI files and both target-score tables were byte-identical to the
accepted v3 lineage. Target PDFs embedded Arial and Arial Bold. The focused and
complete visualization suites passed with 108 tests, 27 subtests, and one
expected skip; a repeated request reused both role results.

The statistic-explicit label acceptance completed later on 2026-07-21. The
voxel v2 and fiber v5 PDQ-39 lineages rendered the exact semantic labels
`Benefit-oriented partial Spearman ρ of PDQ39 score`, `Mean selected-fiber
partial Spearman ρ of PDQ39 score`, and `Target-derived fiber partial
Spearman ρ of PDQ39 score`. All labels used the same publication-local,
SHA-256-verified `study_base.json` resolver and retained an unbroken semantic
value in JSON; vertical figures used a layout-only line break before `of`.
Visual inspection found no clipping, and all sampled PDFs embedded Arial and
Arial Bold. All 26 fiber NIfTI files and both target-score tables were
byte-identical to the prior accepted lineage. The complete visualization suite
passed with 108 tests, 27 subtests, and one expected skip. Repeated requests
reused all six voxel figures and both fiber role results.

The 2026-07-22 label revision supersedes that historical `of` wording with
`with` for every partial-Spearman association label. This applies to the 3D
voxel and fiber colorbars, the 2D voxel and fiber colorbars, and the target
raincloud y-axis. Existing rendered v2/v5 artifacts retain their historical
text until the postprocess is rerun; no scientific array or statistic changes.

The wide target-raincloud acceptance completed on 2026-07-21 at
`task17-pdq39-fiber-spatial-v11-target-raincloud-20260721/` and
`task17-fogq-fiber-spatial-v6-target-raincloud-20260721/`. The intermediate
v10 and v5 lineages are retained but rejected because dash-phase clipping made
their short dashed mean marks appear horizontally displaced. The accepted
figures use a 10 by 25 mm per-target Boxsize, producing an exact 180 by 25 mm
inner plotting box for 18 targets. Boxes are 0.20 target units wide. Violin
outlines and every box, whisker, cap, median, and mean stroke are 0.5 point.
The mean is a centered solid line spanning 70% of its box width, and automated
geometry validation confirms that both mean-line endpoint pairs are symmetric
about their corresponding box centers.

Direct review of all four PNGs confirmed centered mean marks, readable paired
distributions, complete 90-degree target labels, and low-layer jitter that does
not obscure violin or box summaries. Both scales completed two roles with zero
failures; identical second invocations reused both role results and the shared
physical cache. JSON records the exact 180 by 25 mm Boxsize and all accepted
stroke widths, sampled PDFs embed subset Arial TrueType, and the visualization
suite passed all 39 tests.

The final compact-width acceptance completed on 2026-07-21 at
`task17-pdq39-fiber-spatial-v12-target-raincloud-20260721/` and
`task17-fogq-fiber-spatial-v7-target-raincloud-20260721/`. These lineages
supersede v11 and v6 for the target-raincloud display only. The per-target
Boxsize is 8 by 25 mm, producing an exact 144 by 25 mm inner plotting box for
all 18 targets. Direct review of all four PNGs confirmed that the tighter width
does not introduce overlap or clipping. Box width remains 0.20 target units;
all violin and boxplot strokes remain 0.5 point; mean marks remain centered;
and jitter remains below density and summary layers. Both scales completed two
roles with zero failures, and identical second invocations reused both role
results and the shared physical cache. The visualization suite passed all 39
tests.

The centered-target-label acceptance completed on 2026-07-21 at
`task17-pdq39-fiber-spatial-v13-target-raincloud-20260721/` and
`task17-fogq-fiber-spatial-v8-target-raincloud-20260721/`. These lineages
supersede v12 and v7 for the target-raincloud display only. The prior explicit
right alignment anchored the right edge of each 90-degree rotated label to its
tick and displaced the rendered label body to the left. The accepted style uses
center alignment. A renderer-level test now verifies that every label bounding-
box center coincides with its tick display coordinate within 0.5 pixel. Direct
review of all four PNGs confirmed centered labels without overlap or clipping.
Both scales completed two roles with zero failures, and identical second
invocations reused both role results and the shared physical cache. The
visualization suite passed all 39 tests.

The all-coverage-primary target-conditioned acceptance completed on 2026-07-21
at `task17-pdq39-fiber-spatial-v14-all-coverage-primary-20260721/`. The primary
branch scored targets from 3,401 coverage-qualified reference fibers and 2,004
coverage-qualified add-on fibers, while the visualization-only sensitivity
branch retained the 300 selected sweet and sour fibers in each role. The
primary branch produced 18 finite reference target scores and 16 finite add-on
target scores; the selected sensitivity branch retained 16 and 13. The primary
maps contained 1,927 finite reference seed voxels and 6,103 finite add-on seed
voxels. The selected sensitivity maps contained 1,927 and 6,102.

For both branches and roles, raw, 1 mm FWHM, and 2 mm FWHM maps had exactly
identical finite support within their own branch. Every primary target score
matched the independently recorded all-coverage raincloud mean with zero
numeric difference. The retained selected target scores and raw maps matched
the v13 accepted lineage with zero numeric difference. Primary and selected
maps remained scientifically distinct: their maximum absolute voxel
differences were approximately 0.387 for reference and 0.469 for add-on. All
declared outputs existed, both roles completed with zero failures, and an
identical second invocation reused both role results plus the shared
1,700,000-streamline physical cache. The visualization suite passed all 39
tests.

The no-preSMA fixed-order acceptance completed on 2026-07-21 at
`task17-pdq39-fiber-spatial-v15-no-presma-fixed-order-20260721/`. It supersedes
v14 for the PDQ-39 target catalog, target scores, target-conditioned maps, and
rainclouds. `preSMA` is absent from the 17-target catalog. The new physical
cache was rebuilt from all 1,700,000 formal-connectome streamlines because the
target bit-pattern identity changed; an identical second invocation reused the
new cache and both completed role results.

The primary all-coverage branch produced 17 finite reference target scores and
15 finite add-on target scores. The selected sweet-and-sour sensitivity branch
produced 15 and 12. Primary target-conditioned maps retained 1,927 finite
reference seed voxels and 6,103 finite add-on seed voxels; sensitivity maps
retained 1,927 and 6,102. Every retained target score matched v14 exactly after
excluding `preSMA`. Removing the nested target changed the primary voxel scores
by at most approximately 0.013 for reference and 0.031 for add-on.

Both rainclouds used the exact configured 17-target order and display labels,
independent of selected or all-coverage score magnitude. Their inner plotting
box was exactly 136 by 25 mm. Direct visual review confirmed the requested
order, centered 90-degree labels, complete labels without `preSMA`, and no new
overlap or clipping. Raw, 1 mm FWHM, and 2 mm FWHM maps retained identical
finite support within every branch; all declared outputs existed; both roles
completed with zero failures; and the visualization suite passed all 41 tests.

The same 17-target contract was accepted for FoG-Q on 2026-07-21 at
`task17-fogq-fiber-spatial-v9-no-presma-fixed-order-20260721/`. It supersedes
v8 for the FoG-Q target catalog, target scores, target-conditioned maps, and
rainclouds. The shared 17-target physical cache was reused. The primary all-
coverage branch produced 17 finite reference target scores and 15 finite add-
on target scores; the selected sweet-and-sour sensitivity branch produced 14
and 9. Primary target-conditioned maps retained 1,927 finite reference seed
voxels and 6,103 finite add-on seed voxels; sensitivity maps retained 1,927 and
6,085. Raw, 1 mm FWHM, and 2 mm FWHM maps retained identical finite support
within every branch, and every declared output existed.

Both FoG-Q rainclouds used the exact configured 17-target order, the 136 by 25
mm inner plotting box, and the requested display labels without `preSMA`.
Direct PDF review confirmed centered 90-degree labels without overlap or
clipping. Both roles completed with zero failures, and an identical second
invocation reused the physical cache and both role results.

## Conditional signed target inference contract

The next fiber postprocess revision adds patient-level inference only to the
primary `all_coverage` target distribution. The selected sweet-and-sour
distribution remains descriptive. The implementation name is
`conditional_signed_target_inference_v1`; its inference is explicitly
conditional on the published final-model identity, selected tau, selected
coverage threshold, selected branch, and final valid-fiber axis. It does not
adjust for the upstream resolver or fallback search. Role-local result and
figure manifests use `dual_frequency_fiber_section_postprocess_v12`; the
axes-internal raw-p star annotation and scatter-range axis policy use
raincloud style v10.

For target `t`, the inferential fiber set is the intersection of the final
resolver valid-fiber axis, the target membership, and the fibers whose exposure
is finite for every subject on the endpoint-wide complete-case axis and whose
ranked nuisance-adjusted exposure has nonzero norm. Pairwise patient deletion
is forbidden. A multi-target fiber enters every target that it intersects but
enters a given target only once. Empty inferential target sets produce `NA` and
do not enter the multiplicity family.

The observed signed statistic is the equal-weight mean benefit-oriented
partial Spearman coefficient over the inferential target fiber set. It tests
net benefit-versus-harm direction; it is not a generic association-magnitude
test. The first implementation does not add an absolute-correlation statistic.
The observed per-fiber coefficients must reproduce the published
`full_weights.npy`, subject to its stored dtype, and each observed target mean
must reproduce the existing primary all-coverage `target_scores.csv` value.

The null uses patient-level Freedman-Lane residual permutation in the exact
rank-transformed linear-model space used by the observed partial Spearman
calculation. The published ranked nuisance design includes the intercept and
retains the resolver's exact covariate construction, column order, missingness
rule, and average-rank tie method. A pseudo-outcome is not ranked again. Its
nuisance-adjusted residual is normalized separately in every replicate. One
permutation order is shared by all fibers and targets on the same subject and
exchangeability axes. Reference and add-on may reuse a plan only when both axis
identities and exchangeability identities match. Restricted exchangeability is
mandatory when declared by the study input.

The signed target kernel is the equal-weight mean of unit-norm
nuisance-adjusted ranked exposure vectors. Matrix multiplication against the
unit-norm pseudo-outcome residual provides the replicate target statistics.
Float64 brute-force and kernel results must differ by less than `1e-12` for the
observed statistic and representative permutations, including tied exposures,
multi-target fibers, reference, add-on, and empty targets.

The permutation count and seed continue to come only from the existing formal
model configuration. The primary targetwise result uses the plus-one two-sided
Monte Carlo p value. The formal figure displays significance stars derived
from this unadjusted `p_net_targetwise` value; the figure does not claim that
the stars control family-wise error. Publication also retains the Holm-adjusted
value and a single-step complete-null max-absolute-statistic value. The maxT
result is named `p_net_max_t_single_step`; it is not described as strong-FWER
evidence. Each target also publishes its null mean, standard deviation, and
2.5 and 97.5 percentiles.

The parent normative-fiber publication adds the endpoint-local patient and
fiber inference basis under `resolver/target_inference/`:

```text
valid_fiber_exposure.npy
ranked_valid_fiber_exposure.npy
valid_fiber_ids.npy
outcome.npy
ranked_outcome.npy
ranked_nuisance_design.npy
subject_order.csv
exchangeability_blocks.csv
inference_input.json
```

The parent publisher must not import the independent visualization target
catalog or rescan connectome geometry. After reading only the canonical parent
publication and the declared spatial target configuration, postprocess writes
the target-specific inference inputs into its own formal output:

```text
target_conditioned/inference/input/
├── valid_fiber_target_membership.npz
├── target_ids.csv
└── inference_input.json
```

Target membership is a sparse boolean fiber-by-target matrix aligned to the
parent valid-fiber axis and the postprocess target axis. Its manifest binds all
parent inference-basis hashes, the target-catalog hash, and the physical
membership-cache hash. Postprocess may consume only these publication-local
files and other indexed canonical publication artifacts; it must reject
`.runs` paths. The code commit is provenance only and is not a resume gate.

The postprocess inference output is:

```text
target_conditioned/inference/
├── target_group_observed.csv
├── target_group_permutation_null.npy
├── target_group_permutation_summary.csv
├── permutation_plan.npy
└── target_group_permutation_manifest.json
```

The deterministic permutation plan is split into internal atomic blocks whose
size is not exposed in YAML. Blocks live under a request-identity directory, so
inputs with the same replicate count cannot reuse one another. Resume
recomputes only missing blocks; invalid blocks are retained under a quarantine
name and recomputed. Worker-count changes cannot alter the plan or final
results. Partial and failed runs retain blocks and checkpoints. The terminal
inference manifest is written only after every requested replicate and summary
artifact is complete.

Raincloud annotation stays inside the existing axes and leaves the accepted
17-target, 8-by-25-mm-per-target, 136-by-25-mm inner plotting box and y limits
unchanged. At axes-relative height `y = 0.90`, centered above each target's
jitter, it displays only a 7-point significance star: `*` for
`p_net_targetwise < 0.05`, `**` for `p_net_targetwise < 0.01`, and `***` for
`p_net_targetwise < 0.001`. The thresholds are strict and evaluated from most
stringent to least stringent. Values greater than or equal to 0.05 and empty
targets receive no annotation. Exact targetwise, Holm, and maxT values remain
in tables and JSON.

Implementation proceeds through publication-input tests, observed parity,
brute-force-versus-kernel equivalence, deterministic resampling, interrupted
resume, worker-count invariance, empty-target handling, and public-only source
validation. PDQ-39 reference and add-on are the first runtime acceptance;
FoG-Q follows only after PDQ-39 numerical and visual acceptance. Adding
inference must not change the accepted v15 and v9 target scores, maps, finite
support, or descriptive distributions.

### Pre-publication PDQ-39 smoke evidence

A read-only replay of the completed formal parent run confirmed one
`PreparedExposureRecord` and one `EndpointInputRecord` for each PDQ-39 formal
fiber endpoint, plus one valid `DeltaReferenceBundle` for the realized add-on
adjusted branch. The reference basis contained 16 subjects and 3,401 final
valid fibers; its ranked nuisance design had rank 2 and 14 residual degrees of
freedom. The add-on basis contained 13 subjects and 2,004 final valid fibers;
its ranked nuisance design had rank 3 and 10 residual degrees of freedom.
Recomputed observed weights differed from the stored weights by at most
approximately `2.97e-8` for reference and `2.95e-8` for add-on.

A separate noncanonical 10,000-replicate smoke combined those replayed bases
with the accepted v15 17-target membership. It completed 40 atomic blocks per
role, reproduced the accepted target means within approximately `3.33e-9` for
reference and `5.09e-9` for add-on, and retained all 17 reference targets and
15 add-on targets in the multiplicity families. Every Holm-adjusted value was
1.0. The smallest unadjusted value was approximately 0.0902 for reference and
0.1424 for add-on, so the accepted star rule draws no stars on either real-data
smoke figure. The two empty add-on targets were `sPf_thalamus` and
`Pf_thalamus`. These numbers validate the implementation but are not canonical
results because the parent inference basis has not yet been replayed into a
completed indexed publication and the postprocess did not consume that basis
from the canonical publication boundary.
