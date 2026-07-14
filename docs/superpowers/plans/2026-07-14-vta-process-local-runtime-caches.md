# VTA Process-Local Runtime Cache Implementation Plan

**Status:** implementation_complete_solver_free_verified

**Parent design:**
`docs/superpowers/specs/2026-07-13-vta-performance-optimization-design.md`

**Optimization goal:**
`my_helper/fiber/vta_compute_performance_optimization_plan.md`

## Purpose

Use the persistent per-subject MATLAB process to reuse immutable subject,
head-model, anchor, and export-geometry data across canonical VTA tasks. This
slice removes repeated setup and geometry work without changing FEM equations,
stimulation boundaries, interpolation mathematics, artifact paths, or
path-existence-based resume behavior.

## Scope

This slice caches only:

1. lightweight native-to-MNI transform context resolved by `ea_getptopts`;
2. base subject/reconstruction context resolved by `ea_getptopts`,
   `ea_resolve_elspec`, and `ea_load_reconstruction`;
3. canonical head models after the existing coordinate-unit validator passes;
4. native anchor headers loaded by `ea_load_nii`;
5. field-independent export geometry: tetrahedron midpoint coordinates,
   brain-tissue selection indices, and electrode-removal-adjusted coordinates.

This slice does not cache FEM matrices, preconditioners, stimulation-dependent
boundaries, potentials, gradients, field values, `scatteredInterpolant`
objects, barycentric mappings, or generated artifacts. FEM system reuse remains
a separate later slice.

Implemented on 2026-07-14. The complete solver-free MATLAB fiber suite passes
121 tests, the Python VTA pipeline/benchmark suite passes 171 tests, and MATLAB
Code Analyzer reports zero findings in the canonical model directory and the
new cache tests. Review-driven regression coverage confirms that transform-only
repair does not load reconstruction geometry, replaced head-model files
invalidate memory entries, and direct export calls without an exact head-model
identity remain uncached. No real FEM run is claimed by this slice.

## Ownership And Lifetime

`mh_vta_run_canonical_subject_manifest` creates exactly one subject runtime
after manifest validation and passes it explicitly through canonical task,
backend, and export calls. The runtime owns process-local `containers.Map`
instances and is discarded when that subject process exits.

No global persistent variable is used. No cache is written to disk. The
compatibility single-task entry point creates a fresh empty runtime for each
invocation, so it preserves cold-task behavior.

Custom test callbacks retain their existing signatures and do not receive the
production runtime. Only the default canonical solve path uses these caches.

## Cache Keys

Keys are deterministic text encodings of explicit tuples. Paths are
canonicalized before encoding.

```text
subject_context_key:
  subject_dir + reconstruction_path + hemisphere + reconstruction_lead_id
  + electrode_model

headmodel_key:
  subject_context_key + canonical_headmodel_path + atlas_set
  + gray_matter_conductivity + white_matter_conductivity
  + canonical_meshing_version + canonical_headmodel_version
  + electrode_model + reconstruction_lead_id + trajectory_coordinates
  + patient_gm_mask_path + patient_gm_mask_size + patient_gm_mask_mtime_ns

transform_context_key:
  subject_dir + reconstruction_path

export_geometry_key:
  validated_headmodel_instance_key + reconstruction_path
  + reconstruction_lead_id
  + electrode_model + trajectory_coordinates + lead_diameter

validated_headmodel_instance_key:
  headmodel_key + current_headmodel_path + current_headmodel_size
  + current_headmodel_mtime

anchor_key:
  native_anchor_path + file_size + file_mtime_ns
```

Internal contract constants remain:

```text
canonical_meshing_version = canonical_mask_surface_v1
canonical_headmodel_version = simbio_onesolve_canonical_v1
```

The cache implementation may use MATLAB's available file timestamp precision;
the effective path, size, and timestamp values must be included in the key.
Changing any tuple member creates a miss rather than reusing an incompatible
entry.

## Subject Context Contract

The cached base context contains resolved `options`, side index, trajectory,
native anchor path, MNI reference, reconstruction model identity, and geometry
metadata needed to construct later cache keys. It must not contain a task's
stimulation amplitudes, contacts, polarities, control mode, or initialized `S`.

Each task constructs its own stimulation `S` from the cached base context.
Therefore tasks sharing reconstruction geometry can reuse context while still
producing distinct FEM boundary conditions.

Native-to-MNI-only repair uses the separate lightweight transform context. It
must not call `ea_resolve_elspec`, load reconstruction geometry, validate an
electrode model, or require a native anchor. This preserves repairability when
the native E-field exists but FEM-only inputs are unavailable.

## Head-Model Contract

On a miss, the existing canonical preparation path builds or reads the exact
head-model path and immediately validates its coordinate-unit contract. Only
the successfully validated loaded structure is inserted into the runtime.

On a hit, the cache compares the current head-model path/size/available-mtime
signature with the signature captured after validation. An exact match returns
the already validated MATLAB structure without another MAT-file inventory,
load, or validation pass. A changed, removed, or replaced file invalidates the
entry and returns to the normal load/build-and-validate path. A cache hit never
authorizes resume and never substitutes for an expected output artifact.

The head-model function returns a validated-instance key that includes the
post-validation backing-file signature. Export geometry uses this instance key,
so replacing a head model with a different valid mesh also invalidates geometry
derived from the prior mesh.

Manifest validation rejects tasks that declare one canonical head-model path
with incompatible head-model key inputs. This fails before any task executes.

## Export Geometry Contract

The export-geometry cache stores:

```text
tetrahedron_midpoints_mm
tissue_keep_indices
electrode_adjusted_points_mm
final_field_value_indices
```

The geometry is computed without stimulation-dependent field values. Every
task applies `final_field_value_indices` to its newly computed gradient
magnitude, preserving the existing point/value alignment exactly. Empty or
invalid geometry continues to raise the existing export-sample errors.

The cache does not store field values or interpolation objects.

## Anchor Contract

`mh_vta_export_common_grid` accepts an optional preloaded anchor structure.
Production subject execution obtains it from the runtime anchor cache; direct
callers may omit it and retain the existing load behavior. Dimensions, affine,
datatype metadata, and output header behavior remain unchanged.

## Telemetry

Cacheable stages emit their existing timing event with one of:

```text
cache_status = hit
cache_status = miss
```

The required stages are:

```text
subject_reconstruction_context
headmodel_build_or_load
electrode_removal_geometry
native_anchor_load
```

Lookup duration is included in the stage duration. Non-cacheable stages retain
an empty cache status.

## Failure And Resume Semantics

- Cache creation or lookup failure fails only the current endpoint task under
  the existing subject-runner outcome rules.
- Failed values are never inserted.
- A later task may retry a prior miss after a failure.
- Existing artifacts remain governed only by the manifest resolver and file
  existence.
- `--force`, donor copy, atomic publication, dependency failure, and final
  process exit semantics do not change.

## Implementation Steps

1. Add a process-local runtime constructor and focused cache get/put helpers.
2. Split base context resolution from task-specific stimulation construction.
3. Add a lightweight transform-only context that does not load FEM geometry.
4. Thread runtime through the default subject-runner solve path while
   preserving custom callback compatibility.
5. Add keyed validated head-model reuse with backing-file invalidation.
6. Split field-independent export geometry from field-value application and
   add keyed reuse.
7. Allow common-grid export to consume a cached native anchor header.
8. Add cache hit/miss telemetry and manifest cross-task compatibility checks.
9. Update the parent specification and optimization goal status only after all
   solver-free tests pass.

## Verification

Required solver-free evidence:

1. Runtime cache unit tests prove independent names, hit/miss behavior, exact
   key matching, and process-local lifetime.
2. Context tests prove amplitudes and contacts are not cached.
3. Head-model tests prove a validated structure is loaded once per matching
   key and incompatible key inputs do not hit.
4. Export tests prove cached and uncached geometry produce identical points,
   selected field values, native E-field arrays, and thresholded VTA arrays.
5. Runtime integration tests prove two matching operations report miss then hit
   and changed context, geometry, path, or backing-file inputs do not hit.
6. Existing Python VTA pipeline tests, MATLAB solver-free fiber tests, and
   MATLAB Code Analyzer checks remain green.

No claim of real-FEM numerical or performance acceptance is made by this
slice. Those gates remain mandatory before the overall optimization goal can
complete.

## Completion Criteria

This slice is complete only when:

- the production per-subject runner owns and passes one explicit runtime;
- all five scoped cache categories are active and keyed as documented;
- no disk-persistent cache or artifact-hash resume logic is introduced;
- compatibility task execution remains valid;
- cache telemetry distinguishes hits and misses;
- all solver-free verification passes; and
- the parent documents accurately report implementation status.
