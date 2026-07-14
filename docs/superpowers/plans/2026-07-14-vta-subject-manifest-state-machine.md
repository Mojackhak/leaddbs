# VTA Subject Manifest And Runtime State Machine Implementation Plan

## Status

```text
design_aligned
implementation_complete
solver_free_verification_complete
persistent_subject_process_not_yet_connected
current_outputs_unchanged
```

## Goal

Implement the validated `vta_subject_manifest_v1` envelope and the deterministic
per-task artifact state resolver required by the future one-process-per-subject
runner.

This is slice 5 of the approved VTA performance optimization design. It creates
and validates the subject execution contract but does not yet replace the
production per-task MATLAB bridge. Existing outputs remain unchanged.

As implemented on 2026-07-14, Python builds and atomically writes deterministic
subject manifests, while MATLAB independently validates the envelope and
resolves each task to `skipped_existing`, `copied`, `ready`, or
`skipped_dependency`. The compatibility task validator now composes separate
static-definition and runtime-artifact validators. The complete solver-free
MATLAB suite passes 106 tests, the Python VTA pipeline and benchmark suite
passes 151 tests, and MATLAB Code Analyzer reports no findings in the touched
files. No real FEM was run for this contract-only slice.

## Python Manifest Contract

Add a dedicated `subject_manifest.py` module that builds one immutable payload
from a selected `SubjectPlan` and `run_id`:

```json
{
  "schema_version": "vta_subject_manifest_v1",
  "run_id": "...",
  "subject_id": "...",
  "tasks": [
    {
      "task": {"task_id": "...", "kind": "..."},
      "output_leaves": {"native": "...", "MNI152NLin2009bAsym": "..."},
      "reuse_candidate_ids": ["..."]
    }
  ],
  "reuse_donors": [
    {
      "donor_id": "...",
      "output_leaves": {"native": "...", "MNI152NLin2009bAsym": "..."}
    }
  ]
}
```

The builder must:

- preserve planner-provided task order;
- keep task IDs as array values, never JSON object field names;
- include every selected task and every unique same-subject reuse candidate in
  the donor catalog;
- exclude the recipient itself from its ordered reuse candidate list;
- include only candidates with the same `equivalent_task_key`;
- verify physical equivalence before serialization;
- derive every leaf with `leaf_directory`, never from labels or hard-coded
  phases/programs;
- reject empty run/subject IDs, duplicate task/donor IDs, cross-subject tasks or
  donors, unknown or forward dependencies, unknown reuse references, duplicate
  writable leaves, and writable leaves with ancestor/descendant overlap;
- reject output leaves that differ from the canonical path contract;
- reject configured thresholds whose canonical two-decimal V/mm filenames
  collide; and
- atomically write deterministic UTF-8 JSON when requested.

Every `donor_id` is the originating candidate task's `task_id`; this identity
defines ownership without an additional owner field. Unselected donor entries
are read-only. Selected donor entries remain writable only by their owning
task. Donor order follows the deterministic planner order. Donor candidates
are path probes, not dependency edges.

Tasks resolving to one canonical headmodel path must have identical headmodel
inputs: subject/reconstruction, hemisphere/lead, electrode model, atlas, and
gray/white conductivities. A conflicting shared path is rejected before any
execution.

## MATLAB Validation Contract

Split the current validator into:

```text
mh_vta_validate_canonical_task_definition
  -> task fields, sources, model, kind/delivery, solve units

mh_vta_validate_canonical_task_runtime
  -> run_id, canonical output leaves, nonempty missing_artifacts

mh_vta_validate_canonical_task
  -> compatibility wrapper that applies both
```

Add `mh_vta_validate_subject_manifest` that validates the envelope, attaches
the manifest `run_id` and entry `output_leaves` to each task, and invokes only
the static definition validator during initial manifest loading.

The manifest validator must independently reject:

- unsupported schema/version or malformed scalar/array fields;
- duplicate selected task IDs or donor IDs;
- task subject mismatch;
- unknown, duplicate, or forward task dependencies;
- unknown or duplicate reuse candidate IDs;
- donor paths outside the manifest subject stimulation tree;
- selected leaf collisions or ancestor/descendant overlap; and
- any selected output leaf that differs from the MATLAB canonical path
  reconstruction for the task and space.

Path comparison resolves `.`/`..` and symlink aliases before containment or
overlap checks. Platform case semantics are respected rather than relying on a
raw string prefix.

MATLAB does not reconstruct physical equivalence. That remains Python's
authoritative responsibility.

## Runtime Artifact Resolver

Add solver-free MATLAB helpers that operate on one validated manifest entry:

1. enumerate canonical artifact names from configured thresholds;
2. recheck every output path immediately before the task;
3. if complete, return `skipped_existing` without context initialization;
4. for each missing `(space, relative_name)`, probe ordered donor candidates
   and atomically copy the first existing matching artifact;
5. recompute missing artifacts from the filesystem;
6. if copying completed the task, return `copied`;
7. attach the nonempty missing set and run the runtime task validator;
8. evaluate only artifact-specific upstream requirements; and
9. return `ready` or `skipped_dependency` plus copied count and resolved task.

Atomic copy is per artifact, never overwrites an existing destination, removes
temporary files after failure, preserves the source, and maps only the same
space and canonical relative filename.

For `alternating_group_peak`, missing source native E-fields block execution
only when the native group-peak E-field itself is missing. Existing native
group-peak E-fields remain sufficient for native threshold or MNI repair even
if a source task failed. A missing/failed donor never blocks a recipient.

Partial copy followed by computation returns `ready` with a nonzero copied
count; the future runner will emit final status `generated`. No runtime helper
may initialize Lead-DBS context or execute FEM.

## Tests

Python tests must cover:

- deterministic payload and atomic JSON bytes;
- selected and unselected donor catalog construction;
- physical-equivalence filtering and recipient exclusion;
- all duplicate, cross-subject, dependency-order, unknown-reference, canonical
  path, writable-path-overlap, headmodel-context conflict, and
  threshold-filename collision rejections; and
- task IDs beginning with digits remaining array values.

MATLAB tests must cover:

- static/runtime validator separation and compatibility wrapper behavior;
- complete static contact validation, including contact identifier, polarity,
  positive finite fraction, duplicate contact/polarity pairs, and per-polarity
  fraction normalization;
- one-task and multi-task manifest decoding;
- every manifest rejection listed above;
- complete, copied, partial-copy-ready, ready-without-donor, and
  skipped-dependency states;
- artifact-specific group-peak dependency behavior;
- ordered fallback across partial/missing donors;
- atomic no-overwrite and cleanup behavior; and
- no project-specific subject, phase, program, frequency, or electrode values
  in production implementation.

Run MATLAB Code Analyzer, the complete solver-free MATLAB fiber suite, and all
Python VTA pipeline/benchmark tests. No real FEM run is required for this
contract slice.

## Acceptance

This slice is complete only when:

- Python and MATLAB independently validate the manifest structure and paths;
- static task validation no longer requires runtime artifacts;
- runtime resolution is fully path-based and artifact-specific;
- all state branches are covered and deterministic;
- the existing per-task runner remains compatible; and
- documentation records that persistent subject-process integration remains
  pending.
