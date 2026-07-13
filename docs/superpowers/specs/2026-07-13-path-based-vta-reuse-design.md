# Path-Based VTA Reuse Design

**Status:** approved

**Parent plan:** `docs/superpowers/plans/2026-07-13-delivery-aware-vta-yaml-pipeline.md`

## Purpose

Simplify VTA execution state so existing outputs remain compatible across code,
configuration, and metadata revisions. Recalculation is determined only by the
presence or absence of expected artifact paths. The pipeline does not create a
leaf-level provenance file and does not use hashes to decide whether to reuse an
E-field, VTA, or head model.

## Path-Only Completion Contract

Each native or MNI leaf has four expected artifacts:

```text
efield.nii.gz
vta_threshold-0p18Vpermm.nii.gz
vta_threshold-0p20Vpermm.nii.gz
vta_threshold-0p22Vpermm.nii.gz
```

An artifact whose final path exists is complete and must not be overwritten by
an ordinary run. An artifact whose final path does not exist is missing and may
be generated. A leaf is `complete` only when all four paths exist; otherwise it
is `missing`. No persistent `failed` or `stale` state exists.

New artifacts are written to a temporary path in the destination directory and
renamed to the final path only after the producing operation succeeds. This
ensures that path existence remains a usable completion signal after an
interrupted process. A failed operation removes or moves only its temporary
files; it never deletes an existing final artifact.

## Incremental Generation Order

The executor fills only missing artifacts and follows this dependency order:

1. If native `efield.nii.gz` is missing, run the native FEM solve.
2. Generate each missing native threshold from the native E-field.
3. If MNI `efield.nii.gz` is missing, transform the native continuous E-field.
4. Generate each missing MNI threshold from the MNI E-field.

An existing native E-field can therefore repair missing native thresholds or a
missing MNI leaf without another FEM solve. Existing final artifacts are never
rewritten during this repair.

## Head-Model Reuse

Each hemisphere has one fixed Lead-DBS head-model path. If that path exists, the
pipeline reuses it without checking embedded provenance or implementation
hashes. If it is absent, the pipeline builds it. A present but unreadable or
structurally invalid MAT file causes the task to fail; it is not silently
replaced.

`--force` applies to selected stimulation outputs, not to an existing head
model. Rebuilding a head model requires the operator to move the corresponding
head-model file out of its canonical path before running.

## Frequency-Group Reuse

Reuse is resolved at the complete `frequency_group` level and is restricted to
the same subject. Phase, program, frequency-group, source IDs, and display
labels identify output locations but do not change physical E-field
calculation. Two groups are physically equivalent when their normalized group
records compare exactly after removing those identifiers. The comparison
includes:

```text
subject and reconstruction path
hemisphere and reconstruction lead
electrode model
delivery mode and task kind
control mode
frequency, amplitude, and pulse width
contact numbers, polarity, and fractions
atlas, conductivities, spaces, and thresholds
the complete normalized source multiset for the group
```

The implementation must not contain phase names such as `T2` or `T3`, protocol
roles, or project-specific assumptions. Equality is evaluated directly on
normalized immutable group records; no physical-stimulation hash is generated.
For alternating groups, source-level artifacts are matched by their normalized
source records and group-peak artifacts are matched only after the complete
group records are equal.

For each selected group, the runtime scans all frequency groups for the same
subject that are represented in `study_base.json`. It checks their expected
output paths in deterministic study order and uses the first physically
equivalent group with an existing matching artifact as the donor. It does not
write to an unselected donor path.

Reuse handling is path based:

1. If every selected-group artifact exists, skip it.
2. If a selected-group artifact is missing and an equivalent donor artifact
   exists, copy only that missing artifact.
3. If no equivalent donor artifact exists, generate the missing artifact in
   the selected group's own path.
4. If one run selects multiple equivalent groups with no existing donor, the
   first selected group in deterministic order is generated and becomes the
   in-run donor for the others.
5. If generation fails, mark only dependent derivations and selected reuse
   recipients as `skipped_dependency` for the current run.

The output hierarchy remains phase/program specific. `/Volumes/VAL` is ExFAT,
so hard links and filesystem clones are unavailable; reuse materialization uses
an atomic temporary copy followed by rename.

## Task And Failure State Machine

Persistent status is derived only from paths:

```text
complete
missing
```

The current run may additionally report:

```text
generated
copied
skipped_existing
failed
skipped_dependency
```

A task failure blocks only tasks that depend on it. Independent tasks for the
same subject and tasks for other subjects continue. Alternating group-peak tasks
depend on all source tasks for that group. A selected reuse recipient depends
on its current donor only for artifacts that still need to be copied.

## CLI Semantics

Ordinary `run` and `run --resume` both fill missing paths and preserve existing
paths. `--resume` remains accepted for command compatibility but does not enable
a separate hash-aware mode.

`--force` first moves selected stimulation leaf directories to the appropriate
filesystem Trash. Their paths are then missing, so execution proceeds through
the same state machine. `--force` never permanently deletes untracked output.

`status` is read-only and reports `complete` or `missing` for each planned leaf.
It does not inspect content hashes and does not require `provenance.json`.

## Acceptance Scope

Copied-subject acceptance does not rerun all 20 SNr003 tasks. It covers the
minimum set of execution semantics:

```text
one left continuous joint task
one right continuous joint task
one two-source alternating group on one hemisphere
one derived group-peak task
one equivalent frequency-group reuse path represented by T2/T3 in the SNr003 fixture
deterministic synthetic current-control numerical acceptance
```

Acceptance verifies nonblank native/MNI E-fields, three thresholds per space,
path-only skip behavior, partial-artifact repair, frequency-group copying, dependency
failure isolation, and force-to-Trash behavior. Production all-subject execution
remains a separate operational goal.

The T2/T3 labels above describe only the current SNr003 acceptance fixture.
They are not recognized by the planner or executor and are not part of the
generic reuse contract.

## Project-Hardcoding Boundary

Production modules under the generic VTA pipeline and its MATLAB execution
entrypoints must not contain behavior keyed by a concrete subject ID, phase ID,
program ID, target/component label, study name, or HF/ULF role. In particular,
the following literals cannot control production behavior:

```text
SNr003
STNSNr
T1 / T2 / T3
STN / SNr
HF / ULF
chronic / immediate
```

Concrete identifiers may appear in isolated test fixtures, copied-subject
acceptance commands, and documentation examples only. Tests must verify that
arbitrary relabeling leaves normalized frequency-group equality unchanged. The
legacy `STNSNR_VTA_SUBJECT_IDS` environment-variable name in the generic MATLAB
worker launcher must be removed from the canonical execution path; the new
pipeline passes selected subjects through generic task input rather than a
project-named environment variable.

## Explicit Trade-Off

This design prioritizes compatibility and operational simplicity. Existing
files are reused even when code, YAML, atlas contents, source metadata, or
software versions have changed. Operators must use `--force` or move an existing
head model when they intentionally require recalculation.
