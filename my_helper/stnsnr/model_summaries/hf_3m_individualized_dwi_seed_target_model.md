# HF-Only 3-Month Individualized DWI Seed-Target Model

## Status And Scope

This document is the authoritative scientific definition of the reference-role
individualized seed-target model. The model uses each subject's own MRtrix
tractography and estimates target-level rather than fiber-level associations.

The implementation runs all 28 scales declared by
`individualized_seed_target_model.yaml`. Each scale is an independent
engineering endpoint with the same model definition.

## Endpoint

The outcome is the raw reference-phase clinical score:

```text
baseline  = T0, program 0
reference = T2, program 1
```

The nuisance-only baseline model contains the matching raw preoperative score.
Lower scores indicate benefit except for scales whose study definition
explicitly declares a higher-is-better direction.

## Individualized Tractography

Subject-specific tractography is read from:

```text
/Volumes/VAL/STNSNr/derivatives/leaddbs/
└── sub-{subject_id}/connectomics/dMRI/mrtrix_seed_target/
    └── tractograms/
        └── <atlas.space>/
            ├── lh/STNSNrplus/
            └── rh/STNSNrplus/
```

`<atlas.space>` is not a fixed name in the individualized model. It is read
once from `tractography.tracking_config` at configuration load time, using the
`atlas.space` value in the authoritative MRtrix seed-target YAML. The resolved
space is part of the individualized scientific configuration and selects the
tractogram directory used by exposure preparation. A change to that semantic
value invalidates individualized exposure preparation and its downstream
statistics; formatting-only changes to the tracking YAML do not.

The selected tractogram space must be the same canonical space as the E-field
samplers used by the model. Native-DWI tractograms must never be substituted
for target-space tractograms through a legacy path or compatibility symlink.
The tracking YAML is therefore included in run-local configuration provenance
and in the portable input bundle. The bundled individualized profile points to
that bundled tracking YAML. The filesystem path itself is operational
provenance rather than scientific identity; the parsed `atlas.space` value is
the stage input that can invalidate individualized exposure and downstream
results.

Each side has one 300,000-streamline `seedwide.tck` and target-specific TCK
subsets derived from that fixed seedwide set. The scientific target catalog has
17 targets on each side:

```text
GPe
GPi
caudate
posterior_putamen
VLP_thalamus
VLA_thalamus
RN
VA_thalamus
VM_thalamus
PPN
SMA
M1
sPf_thalamus
premotor
CM_thalamus
DLPFC
Pf_thalamus
```

`preSMA` is not generated or analyzed. Target membership is independent
binary membership: one streamline may belong to more than one target, and it
is counted once within each target to which it belongs.

## Target Activation Burden

For subject `i`, side `h`, target `k`, and source threshold `tau`, let:

```text
N_total
  number of valid subject-specific fibers assigned to target k

N_activated
  number of those fibers whose streamline peak E is at least tau

activated_fiber_fraction
  N_activated divided by N_total

activated_mean_peak_E
  mean streamline peak E among activated fibers
```

The continuous target exposure is the thresholded mean peak E over the full
target fiber denominator:

```text
target_activation_burden
  activated_fiber_fraction multiplied by activated_mean_peak_E
```

Equivalently:

```text
B(i,h,k) =
  sum of peak E over fibers with peak E at least tau
  divided by N_total
```

When `N_total` is positive and no fiber is activated, burden is zero. When
`N_total` is zero, burden is missing; missing tractography is not interpreted
as zero activation.

## Subject Support And Bilateral Exposure

A side supports a target when both conditions hold:

```text
N_activated at least 20
activated_fiber_fraction at least 0.01
```

The 0.01 fraction threshold is shared by the reference and add-on models. The
absolute count threshold and patient Coverage threshold remain independent
requirements, so lowering the within-target fraction threshold does not remove
the minimum streamline or cohort-support constraints.

A subject supports a target when either side supports it. The continuous
patient feature nevertheless uses both actual side burdens:

```text
B_bilateral(i,k) = mean of B(i,lh,k) and B(i,rh,k)
```

The burden from a side below the support threshold remains in that mean and may
be small or zero. A patient-target row is missing when either side has no valid
target fibers, because there is no actual bilateral burden to average.

Target Coverage is the number of patients who support the target and have a
finite bilateral burden. The main source uses `tau` 400 V/m and Coverage 5.
The complete source grid is:

```text
tau:      200, 350, 400, 450, 600, 800 V/m
Coverage: 5, 6, 7, 8, 10, 12 patients
```

Threshold boundaries are inclusive.

## Target Coefficients And Score

For each target, compute a partial Spearman coefficient between bilateral
target activation burden and outcome while controlling for the matching
baseline score. Convert the coefficient to the benefit-oriented direction:

```text
lower-is-better scale: weight is negative partial Spearman rho
higher-is-better scale: weight is positive partial Spearman rho
```

A target enters a score when it passes the source Coverage rule and has a
finite coefficient. There is no fixed sweet-target or sour-target count.
For each target, ranks and nuisance residuals are computed from that target's
finite patient rows. The two-sided nominal p value uses the standard
partial-correlation t approximation with degrees of freedom equal to the
finite row count minus the rank of the nuisance design including its intercept
minus one. Benjamini-Hochberg q values are computed across the finite target
tests within this scale, role, and selected tau/Coverage cell. Nominal p and
FDR q values are reported but do not gate target inclusion, source selection,
or score construction.

Within each training set, target burdens are standardized from training rows
only. The patient score is:

```text
sum over valid targets of standardized burden multiplied by target weight
divided by the sum of absolute target weights
```

The held-out subject uses the training-fold means, standard deviations, target
set, and target weights.

## Source Resolution And Computability

The pre-specified source is evaluated first. If it is not accepted, the
configured tau/Coverage grid is evaluated with the same deterministic resolver
used by the other dual-frequency models. At least two adjacent passing cells
are required.

Hard limits are:

```text
at least 12 complete subjects
at least 1 full-sample candidate target
at least 1 candidate target in every realized LOOCV fold
```

All target support, scaling, coefficients, and score construction are repeated
inside each LOOCV training fold.

## Inference

Every realized final endpoint in the main formal run executes:

```text
10,000 formal permutations
10,000 subject-level bootstrap replicates
```

The main formal publication is complete without spatial jitter. It contains
the observed model, final source, LOOCV predictions, formal permutation,
bootstrap, paired in-sample inference, target-coefficient summaries, and all
display-only visualization derived from those formal coefficients. Main
selection, statistics, reports, visualization, and completion markers never
depend on a sensitivity result.

Spatial jitter is a later, explicitly requested sensitivity extension:

```text
1,000 spatial-jitter replicates
```

The root random seed is 42. Spatial jitter uses 2 mm translation FWHM and
recomputes target burdens on fixed individualized tractography. It does not
rerun tractography or solve an E-field again. Every replicate reuses the
precomputed E-field volume in `shared/` and resamples that volume at translated
streamline coordinates; the nominal per-fiber peak-E values cannot be reused
because the fiber-to-field spatial relationship has changed. Physical
preparation uses fixed blocks of 25 replicate indices shared across all
reference endpoints. Each target tractogram is streamed once per block and
evaluated at all block translations before its geometry is released. Endpoint
evaluation uses read-only replicate views from the shared burden and support
arrays; replicate ordering may be rotated for execution, but the seed assigned
to every replicate index remains fixed.

Formal reporting includes paired in-sample and LOOCV statistics, target
bootstrap intervals, sign stability, fold selection frequency, target
Coverage, and FDR-adjusted target q values. A later jitter extension is linked
to the immutable main formal publication and cannot rewrite its model,
statistics, reports, figures, or completion markers. OSS-DBS and pPAM are not
part of this model.

## Visualization

Patient tractography supplies scientific target burdens but is not pooled into
the final group spatial figure. Final full-sample benefit-oriented target
coefficients are projected through the PPMI 85 normative fiber geometry:

```text
17 target coefficients
→ right STN seed-connected PPMI fibers
→ equal mean over finite coefficients of targets hit by each fiber
→ coefficient-colored 3-D fibers
→ all-coverage seed-voxel composition
→ display.nii.gz
→ 2-D figures
```

The projection is display-only and cannot affect source selection, fitting,
LOOCV, permutation, bootstrap, or jitter.

The endpoint also publishes the paired in-sample/LOOCV fit and the target
coefficient stability figure. Figures are PNG or PDF only. Three-dimensional
rendering is headless. Surface colors are sampled 0.25 mm inward.

## Interpretation Boundary

`target_activation_burden` combines the proportion and intensity of activated
tractography streamlines. The fiber fraction is a relative proportion of the
tractography sample, not an estimate of the biological proportion of activated
axons. Results remain conditional on individual DWI quality, registration,
tractography, stimulation-field reconstruction, and the available sample size.
