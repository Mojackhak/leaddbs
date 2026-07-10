# Normative-Fiber Minimum-Count Scoring Design

> **Purpose.** Record the user-confirmed implementation contract for HF, ULF,
> and OSS/pPAM normative-fiber scoring before code changes.
>
> **Workspace.** `/Users/mojackhu/Github/leaddbs`
>
> **Parent goal.** `my_helper/stnsnr/four_model_yaml_core_refactor_plan.md`
>
> **Status.** `design_confirmed_by_user`; implementation pending.
>
> **Authority boundary.** This document is an implementation record, not an
> independent authority. Explicit user decisions govern whenever code,
> historical documentation, or existing outputs disagree.

---

## Goal

Prevent a normative-fiber score from being determined by only a few fibers
without changing the tau/Coverage source resolver. The same engineering rule
applies to every configured endpoint/scale and to:

- HF normative fiber;
- the realized final ULF normative-fiber branch;
- OSS/pPAM sensitivity;
- full-sample final scores;
- every LOOCV training fold.

No clinical scale receives a different implementation path or parameter set.

## Valid Fiber Universe

For a selected source and one full-sample or training-fold fit, define:

\[
F_{\mathrm{coverage}}
=
\left\{
f:
\operatorname{Coverage}_{f}(E \ge \tau_{\mathrm{selected}})
\ge C_{\mathrm{selected}}
\right\},
\]

\[
F_{\mathrm{valid}}
=
F_{\mathrm{coverage}}
\cap
F_{\mathrm{finite\ weights}}.
\]

Coverage-insufficient fibers, non-finite-weight fibers, and fibers outside the
realized branch must never be used to satisfy a minimum count. For ULF,
candidate construction uses the realized final branch after HF-overlap
exclusion.

## Signed Outer Selection

Let:

\[
F_+=\{f\in F_{\mathrm{valid}}:w_f>0\},
\qquad
F_-=\{f\in F_{\mathrm{valid}}:w_f<0\},
\]

\[
N_+=|F_+|,
\qquad
N_-=|F_-|.
\]

The public model-profile parameters are:

```yaml
sweet_fraction: 0.01
sour_fraction: 0.005
weighted_peak_fraction: 0.05
sweet_selected_min_count: 200
sour_selected_min_count: 100
weighted_peak_min_count: 20
```

Requested percentage counts and actual selected counts are:

\[
P_+=\lceil 0.01N_+\rceil,
\qquad
K_+=\min\left[N_+,\max(P_+,200)\right],
\]

\[
P_-=\lceil 0.005N_-\rceil,
\qquad
K_-=\min\left[N_-,\max(P_-,100)\right].
\]

Sweet fibers are ordered by descending weight. Sour fibers are ordered by
ascending weight. Equal weights are resolved by ascending canonical fiber ID.
Selected IDs and their order must therefore be deterministic.

## Patient-Level Weighted Peak

For subject \(i\):

\[
Z^+_{i,f}=E_{i,f}w_f,
\qquad f\in F_{+,\mathrm{selected}},
\]

\[
Z^-_{i,f}=E_{i,f}(-w_f),
\qquad f\in F_{-,\mathrm{selected}}.
\]

The actual peak counts are:

\[
Q_+=\lceil0.05K_+\rceil,
\qquad
H_+=\min\left[K_+,\max(Q_+,20)\right],
\]

\[
Q_-=\lceil0.05K_-\rceil,
\qquad
H_-=\min\left[K_-,\max(Q_-,20)\right].
\]

Then:

\[
\operatorname{SweetPeak}_i
=
\frac{1}{H_+}
\sum_{f\in\operatorname{Top}_{H_+}(Z_i^+)} Z^+_{i,f},
\]

\[
\operatorname{SourPeak}_i
=
\frac{1}{H_-}
\sum_{f\in\operatorname{Top}_{H_-}(Z_i^-)} Z^-_{i,f},
\]

\[
\operatorname{NetFiberScore}_i
=
\operatorname{SweetPeak}_i-\operatorname{SourPeak}_i.
\]

If one signed set is empty, its peak is exactly zero and the result is marked
one-sided. If both signed sets are empty, the score support is absent.

## Minimum-Dominated Flags

A selected-set minimum flag is true when its percentage count is below the
configured minimum, even if the final actual count is capped by the available
signed-fiber count. For example, when \(N_+=50\), then \(K_+=50\) and
`sweet_minimum_count_dominated=true` because \(P_+<200\).

The same rule applies to peak minimum flags: compare the requested percentage
peak count against `weighted_peak_min_count` before applying the \(K\) cap.
Empty signed sets have actual counts of zero; their minimum-dominated flags are
false because no signed library exists to select or aggregate.

## Support Status

Every full-sample and fold fit receives exactly one support status:

```text
adequate_two_sign
limited_two_sign
limited_positive_only
limited_negative_only
absent_no_valid_signed_fibers
```

- `adequate_two_sign`: \(N_+\ge200\) and \(N_-\ge100\).
- `limited_two_sign`: both signs exist, but at least one side is below its
  selected-library minimum.
- `limited_positive_only`: positive valid fibers exist and negative valid
  fibers do not.
- `limited_negative_only`: negative valid fibers exist and positive valid
  fibers do not.
- `absent_no_valid_signed_fibers`: neither signed set exists.

These statuses do not alter tau/Coverage source selection and are not a new
resolver hard gate. Existing computability and MAE/RMSE prediction rules remain
unchanged. Support limitation and one-sidedness are QC/reporting facts. If an
absent score independently violates an existing nonconstant-score requirement,
that existing requirement retains its normal effect.

## LOOCV Contract

For every held-out subject, using training data only:

1. recompute training-fold coverage at the selected tau;
2. rebuild the fold candidate mask at the selected Coverage;
3. estimate fold weights using training subjects only;
4. intersect fold coverage with finite fold weights;
5. recompute signed counts, percentage counts, selected counts, and selected
   fiber IDs;
6. calculate held-out SweetPeak, SourPeak, and NetFiberScore using fold-local
   selected IDs and weights.

Full-sample rankings, signs, and selected IDs must not enter a held-out fold.

## OSS/pPAM Contract

The OSS axis is the realized final model's full-sample \(F_{\mathrm{valid}}\),
in canonical fiber-ID order inherited from the final parent axis. OSS does not
rerun the tau/Coverage resolver and does not recompute coverage from binary
pPAM exposure.

OSS exposure is:

\[
X^{\mathrm{OSS}}_{i,f}
=
\mathbf{1}\left[p(A_{i,f})\ge0.5\right].
\]

Within that fixed axis, each OSS training fold re-estimates weights, intersects
with fold-finite weights, reselects signed fibers, and applies the same
`200/100/20` rules. The fixed OSS axis may not be expanded with parent-atlas
fibers or reduced using a new pPAM coverage scan.

For ULF OSS, the fixed axis is the realized ULF final branch after HF-overlap
exclusion. An OSS/pPAM sidecar may be reused across endpoints only when all of
the following are exactly equal:

- subject order;
- source stimulation inputs and hashes;
- requested and modeled frequencies;
- canonical hemisphere and left-to-right mapping;
- hemisphere merge rule;
- exposure component;
- ordered candidate fiber IDs and hash.

Reuse creates endpoint-local provenance bound to the destination final-model ID
and final-record hash. It must not claim that the source endpoint's final record
is the destination final record.

## Required QC Fields

Full-sample and every fold must record:

```text
n_positive_valid_fibers
n_negative_valid_fibers
sweet_fraction_requested
sour_fraction_requested
weighted_peak_fraction_requested
sweet_selected_k_min
sour_selected_k_min
weighted_peak_k_min
sweet_percentage_count
sour_percentage_count
sweet_actual_selected_count
sour_actual_selected_count
sweet_actual_peak_count
sour_actual_peak_count
sweet_minimum_count_dominated
sour_minimum_count_dominated
sweet_peak_minimum_count_dominated
sour_peak_minimum_count_dominated
fiber_score_support_status
sweet_selected_fiber_id_hash
sour_selected_fiber_id_hash
```

The ID hashes use the ordered canonical integer IDs after deterministic
selection. Empty selections use the shared canonical empty-ID hash rather than
an empty string.

## Reusable Architecture

One shared, endpoint-independent scoring kernel must own:

- valid-mask construction from coverage and finite weights;
- deterministic signed outer selection;
- support-status assignment;
- patient-level weighted-peak aggregation;
- QC-field construction and selected-ID hashing.

HF, ULF, and OSS adapters provide exposure, coverage, weights, canonical fiber
IDs, and score parameters. They must not independently reimplement count or
tie-breaking rules. Full-sample and fold callers use the same kernel.

## Error Handling

- Misaligned exposure, weight, coverage, or fiber-ID axes are execution errors.
- Non-finite exposure values are execution errors before scoring.
- Non-finite weights are excluded through \(F_{\mathrm{finite\ weights}}\).
- Duplicate canonical fiber IDs are execution errors because tie-breaking and
  selected-ID hashes would be ambiguous.
- A one-sided score is valid but limited and must remain visible in QC.
- An empty two-sided library yields zero peaks and
  `absent_no_valid_signed_fibers`; it is never silently backfilled.

## Verification

Tests must cover:

- exact `200/100/20` boundaries and smaller signed universes;
- large universes where percentage counts exceed minima;
- deterministic canonical-ID tie-breaking;
- exclusion of coverage-failing and non-finite-weight fibers;
- positive-only, negative-only, two-sign limited, adequate, and absent states;
- full-sample/fold parity of the kernel with fold-local inputs;
- proof that held-out labels do not change fold-selected IDs;
- ULF post-overlap candidate input;
- fixed OSS candidate axis and binary pPAM threshold at `>=0.5`;
- exact cross-endpoint sidecar reuse acceptance and every identity mismatch;
- required full/fold QC fields in manifests, score tables, and reports;
- all configured endpoint rows receiving the same parameters and execution
  path.
