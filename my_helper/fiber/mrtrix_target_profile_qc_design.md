# MRtrix Target-Profile QC Design

## Purpose

Provide a standalone, YAML-only quality-control workflow for comparing the
target-hit profiles produced by the MRtrix seed-wide tractography pipeline.
The workflow identifies technical failures and statistical outlier candidates
without automatically excluding subjects.

## Public interface

The command-line entry point is:

```text
my_helper/fiber/pipelines/mrtrix-target-profile-qc
```

It exposes exactly three commands:

```text
validate --config <yaml>
run      --config <yaml>
status   --config <yaml>
```

All scientific inputs are inherited from the referenced tracking YAML. The QC
YAML deliberately exposes only the source tracking configuration, a versioned
QC preset, and the output location:

```yaml
schema_version: 1

inputs:
  tracking_config: /path/to/mrtrix_seed_target.yaml

qc:
  preset: robust_target_profile_v1

output:
  root: /path/to/qc
  run_name: fixed300k_all_subjects
```

Unknown or duplicate YAML keys are errors. Paths may be absolute or relative
to the QC YAML.

## Input identity

The QC workflow must never select a result by modification time. It validates
the referenced tracking configuration, computes the exact preparation
identity for every subject, and then computes the exact seed-wide identity for
every configured seed. The corresponding `seed_state.json` is selected by
content identity.

This rule permits inspection of both `staged_complete` and `coverage_failed`
states while preventing an older published result from being mistaken for the
current run. A missing or ambiguous identity is a validation error.

## Preset: `robust_target_profile_v1`

The versioned preset resolves to the following analysis contract:

- Inspect every subject, seed, and target in the tracking YAML.
- Verify preparation and seed-wide state integrity.
- Treat missing targets, empty ROIs, zero target hits, and coverage failures as
  technical failures.
- Use target hit fraction (`target hits / seed-wide total`) without normalizing
  target fractions to sum to one, because one streamline may hit more than one
  target.
- Apply an empirical logit with a 0.5 pseudocount.
- Analyze seed sides separately and also create a side-standardized combined
  subject profile.
- Compute pairwise Spearman, Pearson, and cosine similarities.
- Compare each subject with a leave-one-out median reference.
- Use median/MAD robust scaling and a PCA-whitened multivariate distance with
  at most five components and an 85% explained-variance target.
- Compute homologous-target laterality asymmetry.
- Flag low similarity or high distance at three MADs, target extremes at an
  absolute robust z-score of 3.5, and a single-target review at 5.0.
- Require at least three extreme targets for the target-extreme criterion and
  at least two independent statistical criteria for a statistical-outlier
  candidate.
- Never exclude a subject automatically.

All resolved preset values are written to `config_resolved.yaml` and included
in the run fingerprint.

## Outputs

The run publishes to `<output.root>/<output.run_name>/`:

```text
config_resolved.yaml
provenance.json
manifest.json
input_inventory.csv
target_profiles_long.csv
roi_qc.csv
technical_qc.csv
subject_qc_metrics.csv
subject_similarity_lh.csv
subject_similarity_rh.csv
subject_similarity_combined.csv
target_similarity_lh.csv
target_similarity_rh.csv
target_robust_zscores.csv
laterality_asymmetry.csv
qc_flags.csv
inclusion_recommendation.csv
report.md
figures/*.png
```

The scientific CSV and JSON outputs are required. Figures are best-effort
diagnostic artifacts and use deterministic subject/target ordering.

## Publication and reuse

The fingerprint includes the resolved QC configuration, tracking configuration
hash, exact preparation and seed-wide identities, selected state hashes, ROI
hashes, and QC implementation hash.

Filesystem metadata sidecars such as macOS AppleDouble `._*` files are not QC
artifacts and are excluded from manifests and status verification.

- A complete output with a matching fingerprint is verified and reused.
- A changed fingerprint is built in a sibling staging directory and verified
  before replacement.
- Existing output is preserved in a timestamped sibling backup if atomic
  replacement is required; no untracked data is deleted irreversibly.
- `status` is read-only and verifies the manifest and artifact hashes.

## Decision semantics

Each subject receives one recommendation:

- `include`: no technical failure and no statistical outlier candidate.
- `review_required`: a statistical criterion requires manual review.
- `technical_failure`: an identity, state, ROI, coverage, or zero-hit failure.

Statistical deviation alone is not evidence of preprocessing failure or a
reason for automatic exclusion. Manual image, ROI, FOD, and tractogram review
remains required before changing an analysis cohort.
