# VTA Context And Headmodel Consolidation Implementation Plan

## Status

```text
implemented
solver_free_verification_complete
real_fem_not_required_for_solver_free_contract_tests
current_outputs_unchanged
```

Implemented on 2026-07-14. Canonical headmodels now have one load-and-unit-guard
path, preparation returns the validated structure, and the backend consumes it
without reloading. Solve context reuses one reconstruction load and passes its
trajectory and resolved options through export. All 91 solver-free MATLAB
fiber tests and 115 Python VTA pipeline/benchmark tests pass. MATLAB Code
Analyzer reports no findings in the touched files.

This slice does not establish a whole-pipeline speedup. No real FEM or
candidate performance benchmark was run.

## Goal

Remove duplicate reconstruction, Lead-DBS context, and canonical headmodel
loads within one task while preserving the mandatory unit guard, error IDs,
solve inputs, export geometry, transform semantics, and output artifacts.

This is slice 4 of the approved VTA performance optimization design. It does
not yet add cross-task process-local caching or a persistent subject runner.

## Current Gap

For a native solve, the canonical backend currently:

1. builds `options` and directly loads reconstruction metadata to verify the
   electrode model;
2. asks headmodel preparation to load and validate an existing headmodel;
3. loads and validates that same headmodel again in the backend;
4. asks export to call `ea_load_reconstruction` again for trajectory; and
5. asks the MNI transform path to call `ea_getptopts` again.

These operations are task-local duplicates. They are separate from the later
subject-process cache work.

## Headmodel Contract

Add one canonical loader that:

```text
load required FEM variables
  -> validate vol/mesh coordinate-unit contract immediately
  -> return the validated headmodel structure
```

The required variables remain:

```text
vol
mesh
centroids
wmboundary
elfv
meshregions
```

`mh_vta_prepare_canonical_headmodel` returns `(path, state, headmodel)`:

- reused path: load and validate once; preserve
  `mh_vta_prepare_canonical_headmodel:InvalidExistingHeadmodel` wrapping and do
  not overwrite the file;
- built path: build, then load and validate once; preserve the direct
  `mh_vta:InvalidCanonicalHeadmodelUnits` failure for an invalid new model;
- successful backend: consume the returned validated structure without a
  second `load` or second unit validation.

The load and unit guard are indivisible and must occur before
`ea_getactiveidx`. Existing two-output callers remain compatible.

## Reconstruction And Export Context Contract

The solve context builder calls `ea_load_reconstruction(options)` once and
uses its returned electrode model for the current lead check. It also returns
the trajectory needed by electrode-removal export.

The solve/export path passes this trajectory and the already resolved
`options` structure into `mh_vta_export_canonical_outputs`:

- electrode-removal geometry uses the supplied trajectory;
- MNI transformation reuses the supplied `options` and only resolves the MNI
  reference from that context;
- no additional `ea_getptopts` or `ea_load_reconstruction` call occurs after a
  solve context has been built.

For transform-only repair, where no solve context exists, export may build one
minimal transform context from the task. Threshold-only repair must not build a
Lead-DBS context.

Alternating group-peak derivation has no solve context. It continues to build
one transform context only when its MNI E-field is missing; threshold-only
group-peak repair builds none.

## Tests

Extend focused MATLAB tests to prove:

- valid reused and newly built headmodels are returned as complete validated
  structures;
- invalid reused headmodels retain the wrapped error and file hash;
- invalid newly built headmodels retain the direct unit error and stop before
  `ea_getactiveidx`;
- the backend source contains no direct headmodel `load` and consumes the
  preparation return value before active-index calculation;
- a solve plus native/MNI export calls `ea_load_reconstruction` once and
  `ea_getptopts` once;
- transform-only repair calls `ea_getptopts` once;
- threshold-only repair calls neither context loader;
- supplied trajectory reaches electrode-removal export unchanged; and
- existing task status, timing stages, and artifact arrays remain unchanged.

Run MATLAB Code Analyzer, the complete solver-free MATLAB fiber suite, and the
Python VTA pipeline/benchmark suite. A later real FEM numerical gate still
applies before final release, but this consolidation slice does not require a
fresh real FEM solve for its solver-free contract tests.

## Acceptance

This slice is complete only when:

- each canonical headmodel is loaded and unit-validated once per task;
- solve reconstruction/context data is reused through export;
- repair-only paths create only the context they require;
- established error and non-overwrite behavior is preserved;
- all focused and regression tests pass; and
- no whole-pipeline speedup is claimed before the fixed benchmark runs.
