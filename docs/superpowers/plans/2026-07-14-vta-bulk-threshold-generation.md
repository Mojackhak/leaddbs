# VTA Bulk Threshold Generation Implementation Plan

## Status

```text
implemented
solver_free_verification_complete
real_fem_not_required_for_this_slice
current_outputs_unchanged
```

Implemented on 2026-07-14. Native/MNI solve exports and alternating group-peak
exports now use one shared bulk helper. Seven focused bulk-threshold tests, the
complete 84-test solver-free MATLAB fiber suite, and all 115 Python VTA
pipeline/benchmark tests pass. MATLAB Code Analyzer reports no findings in the
touched files.

This slice does not establish a whole-pipeline speedup. No real FEM or
candidate performance benchmark was run.

## Goal

Generate every requested VTA threshold from one E-field NIfTI load per output
space while preserving the canonical artifact, threshold, telemetry, resume,
and atomic-publication contracts.

This is slice 2 of the approved VTA performance optimization design. It does
not change FEM computation, E-field values, interpolation, output paths,
configured thresholds, or CLI concurrency.

## Current Gap

`mh_vta_export_canonical_outputs` and
`mh_vta_derive_canonical_group_peak` currently loop over thresholds and call
`mh_vta_threshold_efield` once per missing output. Each call reloads the same
compressed E-field. With three configured thresholds, one output space can
therefore decompress the same E-field three times.

## Implementation Contract

Add a shared MATLAB helper:

```text
mh_vta_threshold_efields(
  efield_path,
  thresholds_v_per_m,
  output_paths,
  EventEmitter,
  TaskId)
```

The helper must:

1. validate one existing E-field path, finite nonnegative thresholds, and an
   equal-length ordered output-path collection;
2. return without loading the E-field when the requested collection is empty;
3. load the E-field exactly once when at least one requested output is missing;
4. preserve request order and skip output paths that already exist;
5. generate each mask as
   `uint8(isfinite(E) & E >= threshold)`;
6. preserve source dimensions and affine, set the existing uint8 datatype and
   scaling metadata, and retain the threshold-specific description;
7. publish each artifact independently through `mh_vta_publish_atomic`;
8. emit one `threshold_generation` event immediately before each corresponding
   `artifact_publication` event; and
9. leave no temporary output after a write or publication failure.

The source NIfTI load is included in the first generated threshold's timing.
Later thresholds measure only their own mask construction and temporary-file
write. This preserves one event per generated artifact while ensuring the sum
of threshold timings includes the single source load.

`mh_vta_threshold_efield` remains public compatibility surface and delegates
to the bulk helper with one threshold/output pair.

Atomic temporary paths must preserve the requested NIfTI suffix. A `.nii`
target uses a `.nii` temporary file and a `.nii.gz` target uses a `.nii.gz`
temporary file; compressed content must never be published under an
uncompressed filename.

Both canonical solve/export and alternating group-peak derivation must resolve
their requested threshold/output pairs first, then invoke the shared bulk
helper once per output space. No task, subject, phase, program, frequency
group, or threshold value may be hard-coded.

## Failure And Resume Semantics

- Existing outputs are not rewritten.
- Atomicity is per output artifact, matching current behavior; the batch is not
  a transaction.
- If one requested threshold fails, already published earlier thresholds remain
  valid and later thresholds are not attempted.
- A retry skips the existing outputs and regenerates only missing outputs from
  one E-field load.
- A missing E-field is an error only when at least one threshold output is
  requested and missing.

## Tests

Extend the focused MATLAB export tests to cover:

- below/equal/above values at 180, 200, and 220 V/m;
- `NaN`, positive infinity, and negative infinity;
- exact uint8 arrays, dimensions, affine, datatype, scaling, and descriptions;
- ordered partial requested sets;
- existing-output skip and all-complete no-load behavior;
- one source load for multiple requested thresholds using an instrumented
  `ea_load_nii` test double;
- compatibility-wrapper equivalence;
- threshold-generation/publication event ordering for solve and group-peak
  paths; and
- atomic failure cleanup with earlier completed artifacts retained.

Run the complete solver-free MATLAB fiber suite and the existing Python VTA
pipeline/benchmark suite. This derived-only slice requires exact array equality
and does not require a real FEM run.

## Acceptance

This slice is complete only when:

- solve and group-peak paths use the shared bulk helper;
- each E-field is loaded at most once for all missing thresholds in one output
  space;
- all derived arrays and metadata match the existing contract exactly;
- atomic resume/failure behavior is covered;
- all focused and regression tests pass; and
- the roadmap and design status record slice 2 as implemented without claiming
  a measured whole-pipeline speedup.
