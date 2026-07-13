# Seed-Target YAML Batch Design

## Purpose

Replace the seed-target connectivity CLI's separate scientific path arguments with one strict YAML configuration that defines a shared target atlas, a shared connectome, and a named collection of seed ROIs. One invocation validates or runs every configured seed while preserving the existing one-seed-per-result statistical contract.

The repository configuration uses two named seeds, `lh` and `rh`, and publishes human-readable current-result directories. SHA-256 fingerprints remain provenance values rather than directory names.

## Public Configuration

The change is a breaking schema upgrade to `schema_version: 2`. Version 2 requires the following structure:

```yaml
schema_version: 2

inputs:
  target_atlas_root: /Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/atlases/HybraPD Whole Brain (Yu 2021)
  seed_rois:
    lh: /Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/atlases/STNSNr-connected regions/lh/STNSNrplus.nii.gz
    rh: /Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/atlases/STNSNr-connected regions/rh/STNSNrplus.nii.gz
  connectome: /Users/mojackhu/Github/leaddbs/connectomes/dMRI/dTOR-985 Full (Elias 2024)

output:
  output_root: /Volumes/VAL/STNSNr/summary/individual_connectome_fiber/seed_target_connectivity/results
  run_name: dTOR__HybraPD__STNSNrplus
  cache_root: /Volumes/VAL/STNSNr/summary/individual_connectome_fiber/seed_target_connectivity/.cache

seed:
  probability_threshold: null

targets:
  probability_threshold: null
  roi_thresholds: {}

execution:
  fiber_chunk_size: 100000
  cache_membership: true

ranking:
  enabled: true
```

`inputs.target_atlas_root`, `inputs.seed_rois`, `inputs.connectome`, `output.output_root`, and `output.run_name` are required. `output.cache_root` is optional and defaults to `<output_root parent>/.cache`. Relative paths are resolved against the YAML file's directory. Seed keys and `run_name` are safe single path components containing only ASCII letters, digits, underscores, hyphens, or periods.

The public `intersection` object is removed. Segment-aware voxel traversal remains the only internal algorithm and continues to be recorded in provenance. Unknown fields, schema version 1, an empty seed mapping, unsafe names, duplicate YAML keys, and invalid paths are rejected.

## CLI Contract

Validation and execution accept only the YAML path:

```text
seed-target-connectivity validate --config CONFIG
seed-target-connectivity run --config CONFIG
```

The CLI does not accept `--target-atlas-root`, `--seed-roi`, `--connectome`, `--output-root`, or `--cache-root`. It does not add `--resume` or `--force`.

`status --run-dir RUN_DIR` and `artifacts --run-dir RUN_DIR` remain result-inspection interfaces. They do not select scientific inputs and therefore do not conflict with YAML-only run configuration.

## Batch Execution

The YAML describes one batch. The batch resolver opens the target atlas and connectome once and resolves every named seed using the same thresholds and execution parameters. Each seed is still evaluated independently against the shared target atlas, producing one `MembershipResult`, one target-statistics table, and one result directory.

Target fiber membership is independent of the seed and is shared through the configured cache. Seed membership remains keyed by the resolved seed mask. Changing one seed must not invalidate another seed's effective result identity or membership cache.

The `run` command returns a deterministic mapping keyed by seed name. For the repository configuration it reports separate `lh` and `rh` result paths, fingerprints, reuse states, target counts, and seed-fiber counts.

## Result Layout

Only the result tree receives seed-name hierarchy:

```text
seed_target_connectivity/
├── configs/
│   └── seed_target_dtor.yaml
├── .cache/
└── results/
    ├── lh/
    │   └── dTOR__HybraPD__STNSNrplus/
    └── rh/
        └── dTOR__HybraPD__STNSNrplus/
```

Each side directory contains:

```text
provenance.json
config_resolved.yaml
target_catalog.csv
target_connectivity.csv
target_ranking.csv
seed_connected_fiber_ids.npy
target_fiber_membership.npz
input_resolution_qc.csv
artifact_index.csv
```

`provenance.json` replaces `analysis_manifest.json`. The artifact index hashes every primary artifact plus `provenance.json` and excludes only its own self-referential hash.

## Identity and Provenance

Each seed result records three distinct identities:

- `batch_configuration_hash`: canonical hash of the fully resolved YAML, including all named seeds and publication settings;
- `effective_configuration_hash`: canonical hash of shared scientific parameters plus only the current named seed, excluding sibling seeds and publication paths;
- `run_fingerprint`: stable identity derived from the effective configuration, current seed source and resolved-mask hashes, target-atlas resolved-mask hash, connectome identity, fixed traversal algorithm/version, and code provenance.

The fingerprint is stored only in `provenance.json`. It is not part of the result path. Changing `lh` alone must not change the `rh` effective configuration hash or run fingerprint. The batch hash may change because it describes the complete YAML.

Provenance also records source paths and hashes, resolved-mask hashes, connectome geometry and ordered-fiber identities, traversal version, chunk size, Git commit, package hash, creation time, cache identities, and primary artifact hashes.

## Reuse and Replacement

For each semantic result directory:

- a matching fingerprint with a valid artifact index is reused;
- a missing directory is published as a new result;
- a different fingerprint is replaced only after every newly computed batch result passes validation.

The batch uses sibling staging directories on the same volume. Both side results are fully staged and verified before publication begins. Existing tool-owned result directories are renamed to rollback locations, staged results are renamed into their final paths, and all final artifacts are verified. If any publication step fails, newly published directories are removed from the final names and every prior directory is restored.

After a successful replacement, prior untracked result directories are moved to the platform Trash rather than permanently deleted. The cache resides outside the result tree and is not removed during replacement. The publisher refuses to replace a directory that lacks a valid seed-target provenance marker, preventing accidental replacement of unrelated user data.

## Compatibility

Schema version 1 YAML and the old scientific path flags are intentionally unsupported by the new CLI. Existing content-addressed result directories remain readable through `status` and `artifacts` if they contain `analysis_manifest.json`; new results use `provenance.json`. This read-only legacy support does not preserve the old run interface.

The existing Python statistical and traversal units remain single-seed primitives. A new batch orchestration layer resolves schema version 2 and invokes those units for each named seed. This keeps the scientific definitions unchanged while changing configuration, publication, and CLI behavior.

## Error Handling

Validation fails before traversal when any seed, target atlas, connectome, output location, name, or threshold is invalid. A failure while computing one seed prevents publication of all new batch results. Cache entries are accepted only when their recorded identities and hashes match the effective inputs. Corrupt cache entries are treated as misses and recomputed by the normal run; no explicit resume or force mode is exposed.

## Acceptance Criteria

- The CLI rejects all removed scientific and output path flags.
- One schema version 2 YAML validates both `lh` and `rh` seeds.
- One run produces `results/lh/<run_name>` and `results/rh/<run_name>`.
- Both results retain the existing per-target statistics and exact one-seed scientific meaning.
- Target membership is computed once or reused across both seeds.
- Each result contains `provenance.json` and no new `analysis_manifest.json`.
- Changing only one seed changes only that side's effective hash and fingerprint.
- Matching valid results are reused without rewriting.
- Different results replace semantic directories only after both sides stage successfully.
- Simulated publication failure restores both prior side directories.
- Previous untracked results are moved to Trash after successful replacement.
- No `--resume` or `--force` option exists.
- Repository tests, real dTOR validation, and deterministic artifact verification pass in Conda environment `leaddbs`.
