# MRtrix Seed-Target Seed-42 Rerun Integrity Design

## Status

```text
approved
implementation_in_progress
old_results_preserved_until_archive_validation
```

## Purpose

Repeat the 16-subject bilateral fixed-sampling MRtrix seed-target analysis with
`random_seed: 42` after creating a complete, recoverable archive of every
existing `mrtrix_seed_target` result. The rerun must start from empty active
result roots, must not reuse scientifically stale chunks, and must compare the
new 300,000-streamline target profiles with the archived current 300,000 and
historical 18-target 50,000 profiles.

The archive root is fixed as:

```text
/Volumes/VAL/STNSNr/backups/mrtrix_seed_target/pre_seed42_20260719
```

The operation is restricted to these subjects:

```text
sub-SNr003 sub-SNr006 sub-SNr007 sub-SNr011
sub-SNr012 sub-SNr014 sub-SNr015 sub-SNr016
sub-SNr017 sub-SNr018 sub-SNr020 sub-SNr022
sub-SNr024 sub-SNr026 sub-SNr029 sub-SNr030
```

No other tractography or connectomics directory is in scope.

## Pre-Rerun Archive Contract

Before any active directory moves, create and validate:

- one run inventory at `subject x side x seed-wide identity` grain;
- long target profiles for all valid states, including raw counts and hit
  fractions;
- separate 18-target 50,000 and 300,000 profile tables;
- an inventory of other historical mother totals and terminal states;
- copies of source YAML and resolved JSON configurations;
- file count, byte size, and SHA-256 for every non-AppleDouble file; and
- a manifest recording source and archive paths for all 16 subject roots.

Two-target 50,000 runs remain recoverable in the full archive but are not a
comparison cohort and do not receive a dedicated analysis.

Only after every manifest row validates may each complete active
`mrtrix_seed_target` directory be moved by same-volume atomic rename into
`full_data/<subject>/mrtrix_seed_target`. The move must preserve file count,
total bytes, and hashes. Failure leaves all not-yet-moved sources untouched and
is reported for manual recovery; no source is permanently deleted.

## Seed-Wide Scientific Identity Hardening

The seed-wide identity must bind the exact completed preparation artifacts
consumed by tracking, not only the preparation identity string. The canonical
identity document includes SHA-256 records for:

- `wm_fod.mif`;
- `brainmask.mif`;
- `response_wm.txt`; and
- the resolved tracking mask consumed by `tckgen`.

The chunk identity and verification record must bind the canonical preparation
artifact-set hash. A chunk generated from different bytes cannot be reused even
if an older preparation identity or directory name is unchanged.

## Post-Success Cache Cleanup Contract

The YAML execution object accepts:

```yaml
execution:
  cleanup_work_cache_after_success: true
```

The field is optional and defaults to `true`. It is operational provenance and
is written explicitly to every resolved configuration. It does not change the
scientific seed-wide identity.

Cleanup is a batch-level commit step. It runs only after all configured
subjects are complete and every public artifact passes hash and structural TCK
validation. Partial failure, coverage failure, interruption, publication
failure, or artifact verification failure preserves all caches.

The only eligible tool-owned cache directories are:

```text
work/preparations
work/seedwide
work/staging
work/rollback
```

The following are retained:

```text
tractograms
work/state.json
work/configs
work/run.lock
```

Because the seed-wide cache is eligible for removal, `work/state.json` must be
self-contained. Each published seed result retains its seed-wide identity,
preparation artifact-set hash, complete scientific identity document, ordered
target keys, target counts, and hit fractions. Later comparison and provenance
checks must not depend on a deleted `seed_state.json`.

Eligible cache directories are moved to platform Trash and never permanently
deleted. Each subject state records the request, terminal cleanup status,
selected paths, selected bytes, completed time, and any pending paths. Trash
failure produces a warning and pending state without invalidating already
verified scientific artifacts.

## Formal Seed-42 Configuration

The formal YAML is:

```text
/Volumes/VAL/STNSNr/config/mrtrix_seed_target_fixed300k_all_seed42.yaml
```

It contains all 16 subjects, both STNSNrplus seed sides, and the approved 18
same-side targets. Tracking is fixed to:

```yaml
tracking:
  seedwide_streamlines: 300000
  minimum_streamlines_per_target: 300
  fod_cutoff: 0.06
  min_length_mm: 10
  max_length_mm: 250
  random_seed: 42
```

Every one of the 32 subject-side units must contain exactly 300,000 mother
streamlines and at least 300 hits for every target. The active roots are empty
before launch, so no archived chunk can be reused.

## Post-Rerun Comparison

The comparison output root is:

```text
/Volumes/VAL/STNSNr/summary/individual_connectome_fiber/
  mrtrix_seed_target_seed42_comparison/run-<UTC timestamp>
```

Primary comparison uses the archived current fixed-300,000 result for each
subject-side. Historical 18-target 50,000 states form a separate descriptive
sensitivity analysis. Two-target states are excluded.

For each target report count, hit fraction, percentage-point difference,
ratio, and optional GPi-normalized fraction. For each subject-side report
Pearson, Spearman, Kendall, top-5/top-10/top-15 overlap, and the target with the
largest absolute hit-fraction change. Random-repeatability claims are allowed
only when preparation artifacts, ROI hashes, scientific parameters, code, and
mother total match and only the random seed differs.

## Acceptance Gates

1. No active writer or subject lock exists before archive creation.
2. The pre-rerun manifest covers exactly 16 active roots and verifies all
   non-AppleDouble files.
3. All 16 roots are recoverable under `full_data` and absent from the active
   namespace before rerun.
4. Automated configuration, identity, reuse, publication, cleanup, and status
   tests pass in Conda `leaddbs`.
5. The seed-42 YAML validates without warnings that affect execution.
6. All 32 new seed sides publish exactly 300,000 mother streamlines with all
   18 targets at or above 300.
7. Every published hash and TCK count validates before batch cache cleanup.
8. Cleanup runs only after the global success gate and leaves public
   tractograms, state, configs, and logs intact.
9. The seed-42 comparison report is reproducible from archived tables and new
   subject states.
