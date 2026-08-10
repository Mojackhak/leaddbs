# HF-Adjusted ULF Add-On Individualized DWI Seed-Target Model

## Status And Scope

This document is the authoritative scientific definition of the add-on-role
individualized seed-target model. It uses the same subject-specific 17-target
MRtrix geometry as the matching reference model and estimates ULF-only
target-level burden after excluding fibers already active under the reference
HF component.

The implementation runs all 28 scales declared by
`individualized_seed_target_model.yaml`.

## Endpoint And Branches

The configured endpoints are:

```text
baseline  = T0, program 0
reference = T2, program 1
addon     = T3, program 2
```

The adjusted add-on branch models the raw add-on-phase outcome with:

```text
matching reference-phase clinical score
matching individualized reference target-score change
ULF-only individualized target score
```

The no-delta branch omits the reference target-score-change covariate. Branch
realization and support status use the same one-way rules as the direct-voxel
and normative-fiber add-on models.

## Individualized Tractography And Targets

The model reads left and right `STNSNrplus` tractography from:

```text
/Volumes/VAL/STNSNr/derivatives/leaddbs/
└── sub-{subject_id}/connectomics/dMRI/mrtrix_seed_target/
```

It uses the same 17 target IDs as the reference individualized model.
`preSMA` is excluded. Target membership is independent binary membership and
one fiber is counted once within each target it hits.

## ULF-Only Target Activation Burden

For each subject, side, target, and source threshold, compute HF-component and
ULF-component streamline peak E on the same target-specific fibers.

The denominator is always:

```text
N_total
  all valid individualized fibers assigned to the target
```

The ULF-only numerator contains fibers that satisfy both conditions:

```text
ULF peak E is at least tau
HF peak E is below tau
```

The continuous add-on target burden is:

```text
B_ULF_only(i,h,k) =
  sum of ULF peak E over ULF-active and HF-inactive fibers
  divided by all valid target fibers
```

HF-overlap fibers contribute zero to the numerator but remain in the
anatomical target denominator. This prevents ULF-only burden from being
inflated when HF already activates a large fraction of the target tract.
The locked HF threshold is read from the ready matched-reference record:
`selected_tau` for a formal source and `evaluated_tau` for an explicitly
evaluated sensitivity source. Add-on preparation does not reselect or
independently infer the reference threshold.

When `N_total` is positive and no ULF-only fiber is activated, burden is zero.
When `N_total` is zero, burden is missing.

## Subject Support And Bilateral Exposure

For each side:

```text
N_activated
  number of ULF-active and HF-inactive target fibers

activated_fiber_fraction
  N_activated divided by N_total
```

The side supports the target when:

```text
N_activated at least 20
activated_fiber_fraction at least 0.01
```

The 0.01 fraction threshold is shared by the reference and add-on models. The
absolute count threshold and patient Coverage threshold remain independent
requirements, so lowering the within-target fraction threshold does not remove
the minimum streamline or cohort-support constraints.

The subject supports the target when either side supports it. The patient
feature remains the average of both actual side burdens:

```text
B_ULF_only_bilateral(i,k) =
  mean of left and right ULF-only target burdens
```

A side below the support threshold still contributes its actual burden. A
patient-target row is missing when either side has no valid target fibers.

The main source uses `tau` 400 V/m and Coverage 5. The complete source grid is:

```text
tau:      200, 350, 400, 450, 600, 800 V/m
Coverage: 5, 6, 7, 8, 10, 12 patients
```

Threshold boundaries are inclusive.

## Target Coefficients And Score

For each target, compute the partial Spearman coefficient between bilateral
ULF-only burden and add-on outcome while controlling for the branch-specific
nuisance design. Convert the coefficient to the benefit-oriented direction.

All targets that pass Coverage and have finite coefficients enter the score.
There is no fixed number of sweet or sour targets. Target-level FDR q values
use the same finite-row partial-correlation t approximation and
Benjamini-Hochberg family as the reference individualized model. The family is
the finite target tests within this scale, role, and selected tau/Coverage
cell. Nominal p and FDR q values are reported but do not gate target inclusion,
source selection, or score construction.

Training-fold standardization and score construction are identical to the
reference individualized model:

```text
sum of standardized bilateral burden multiplied by target weight
divided by the sum of absolute target weights
```

Target support, coefficients, scaling, and score construction are learned
inside every LOOCV training fold.

## Delta Reference Score

The adjusted branch uses the matching individualized reference target model:

```text
DeltaReferenceScore =
  reference target score of the HF component in the combined program
  minus reference target score of the HF-only reference program
```

For strict LOOCV, the matching reference target model is trained inside the
same outer training fold. The held-out patient's delta score uses only that
fold's target set, scaling parameters, and weights.

The full-sample delta score uses the reference model's stored full-sample
target means, standard deviations, and weights. Each fold delta score uses the
matching reference training fold's stored means, standard deviations, target
mask, and weights. The reference-component support check counts targets that
meet the configured per-patient target support rule at the selected reference
tau; it reports the fraction of those targets outside the corresponding
full-sample or fold reference target set.

The no-delta branch remains independently executable. No implicit fallback
copies a score from another model family or clinical scale.

## Source Resolution And Computability

The pre-specified source and fallback grid use the same deterministic resolver
as the reference individualized model. At least two adjacent passing cells are
required.

Hard limits are:

```text
at least 12 complete subjects
at least 1 full-sample candidate target
at least 1 candidate target in every realized LOOCV fold
```

## Inference

Every realized final branch runs:

```text
10,000 formal permutations
10,000 subject-level bootstrap replicates
1,000 spatial-jitter replicates
```

The root random seed is 42. Spatial jitter uses 2 mm translation FWHM and
recomputes HF and ULF component peak exposure on the fixed individualized
tractography. It does not rerun tractography or solve either E-field again.
Every replicate reuses the precomputed HF and ULF E-field volumes in `shared/`
and resamples them at translated streamline coordinates; nominal per-fiber
peak-E values cannot be reused because the fiber-to-field spatial relationship
has changed. Physical preparation uses fixed blocks of 25 replicate indices.
Blocks are shared across add-on endpoints with the same cohort, perturbation
settings, and locked reference tau. Each target tractogram is streamed once per
block and evaluated at all block translations before its geometry is released.
Endpoint evaluation uses read-only replicate views from the shared burden and
support arrays; replicate ordering may be rotated for execution, but the seed
assigned to every replicate index remains fixed.

Formal outputs report paired in-sample and LOOCV statistics, target bootstrap
intervals, sign stability, fold selection frequency, target Coverage,
HF-overlap exclusion counts, and target-level FDR q values. OSS-DBS and pPAM
are not part of this model.

## Visualization

The final benefit-oriented target coefficients are projected through PPMI 85
normative geometry for standard-space visualization:

```text
17 target coefficients
→ right SNr seed-connected PPMI fibers
→ target-derived fiber coefficients
→ coefficient-colored 3-D fibers
→ all-coverage seed-voxel composition
→ display.nii.gz
→ 2-D figures
```

Patient-specific tractography is not pooled into the final group spatial map.
The PPMI projection is display-only and cannot affect scientific computation.

The endpoint also publishes the paired in-sample/LOOCV fit and the target
coefficient stability figure. Figures are PNG or PDF only, rendering is
headless, and surface colors are sampled 0.25 mm inward.

## Interpretation Boundary

The model estimates target-level association for the ULF-active fraction of
individualized fibers not already active under HF. Its burden denominator is a
tractography streamline sample and does not estimate biological axon count.
Results remain conditional on DWI reconstruction, registration, field
component separation, overlap classification, and sample size.
