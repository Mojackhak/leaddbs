# Canonical Head-Model Unit Contract Design

## Purpose

Prevent a canonical FEM task from silently interpreting a Lead-DBS head model
with inconsistent coordinate units. The gradient calculation is unit-sensitive:
the stored volume conductor must use meter coordinates while the exported mesh
must use millimeter coordinates.

## Scope

This change applies only to canonical head-model validation. It does not alter
meshing, FEM assembly, stimulation boundaries, E-field export, VTA thresholds,
or the path-based head-model reuse policy.

## Required Contract

A canonical head model is valid only when all of the following are true:

- `mesh.pnt` and `vol.pos` are real, finite numeric `N x 3` arrays;
- both arrays contain the same number of nodes;
- if `mesh.unit` exists, it equals `mm`, case-insensitively;
- `max(abs(double(vol.pos(:)))) < 2 m`; and
- after conversion to `double`, every node satisfies
  `double(mesh.pnt) / 1000 == double(vol.pos)` within an absolute tolerance of
  `1e-6 m`.

The tolerance accepts double- and single-precision serialization roundoff while
remaining far below a millimeter-versus-meter mismatch. It must not accept a
unit, axis, node-order, or geometry mismatch. The coarse range guard catches a
jointly mis-scaled pair that could otherwise satisfy the relationship check.

## Validation Points

The same reusable validator runs at the mandatory backend convergence point,
immediately after the backend loads the head model and before boundary assembly.
This covers both reused and newly built head models.

The head-model preparer also applies the validator when it already loads an
existing model for structural validation. The preparer does not add a second
load after a new build; the mandatory backend validation remains authoritative.
Validation therefore always occurs before FEM solving, gradient calculation,
or output publication.

## Failure Policy

Any contract violation fails the dependent task explicitly. Existing head
models are not overwritten, and newly built invalid models are not used.
Automatic coordinate conversion is prohibited because changing coordinate
arrays alone cannot establish that the stored FEM matrices were assembled with
the intended units.

The validator reports a stable error identifier and diagnostics describing the
failed field or maximum coordinate mismatch. The head-model preparer preserves
its existing distinction between invalid reused input and failed construction.

## Non-Goals

The validator does not require a nonempty suprathreshold VTA. A valid weak
stimulation may produce no voxels above a configured threshold, so that outcome
is not evidence of a coordinate-unit error.

## Verification

Automated MATLAB tests must cover:

- a valid millimeter/meter head model;
- a valid single-precision millimeter/meter head model;
- `vol.pos` incorrectly stored in millimeters;
- an absent `mesh.unit`, which remains valid;
- an incorrect `mesh.unit` when the field is present;
- a jointly mis-scaled coordinate pair outside the `2 m` bound;
- nonfinite coordinates;
- non-`N x 3` or node-count-mismatched coordinates; and
- propagation through existing-head-model preparation.
