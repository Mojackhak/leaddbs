# STNSNr Normative Fiber FDR And Enrichment Cache Definition

> **Purpose.** Canonical statistical definition for normative fiber FDR and enrichment caches.
> **Scope.** HF and ULF normative connectome fiber models only.
> **Status.** Documentation definition; this file does not indicate that caches have been generated.

---

## Role

FDR and enrichment caches are post-model QC, display, and interpretation layers.
They do not change:

```text
tau/Coverage source resolver
HF/ULF source status
HF/ULF prediction status
endpoint model status
final branch selection
NetFiberScore or NetULFFiberScore
DeltaHFScore source or role
OSS sensitivity status
jitter status
```

The FDR cache answers:

```text
Which individual tested fibers show endpoint association after nuisance adjustment
and multiple-comparison correction?
```

The enrichment cache answers:

```text
Are selected associated fibers over-represented in specific anatomical,
endpoint, or pathway labels?
```

---

## FDR Cache

### Tested Universe

For each model, endpoint, connectome, branch, and selected source, the tested
fiber universe is:

```text
all selected-source tau/Coverage candidate fibers tested in the selected final branch
```

This is the same model-level candidate universe used by the selected peak-E-field
branch. It is not the whole connectome atlas and not a parent raw `fiber_ids.npy`
when that file stores the full exposure id universe. Cache manifests must record
the tested candidate fiber id hash. When OSS sidecars are generated for the same
final branch, their `oss_fiber_ids.npy` must match this selected candidate id
order or explicitly document an equivalent manifest-recorded order.

Do not pool HF and ULF families for FDR correction. Do not pool different
endpoints, connectomes, branches, or tested fiber universes.

### Null Hypothesis

For fiber `j`:

```text
H0_j:
  fiber j exposure has no association with the endpoint after branch-specific
  nuisance adjustment
```

### Statistic

Use full-sample branch-specific partial Spearman:

```text
T_j = partial_spearman(Y, X_j | Z)
```

where:

```text
Y   = endpoint
X_j = exposure of fiber j
Z   = branch-specific nuisance covariates
```

HF nuisance model:

```text
Y_post ~ Y_base
```

ULF no-DeltaHF nuisance model:

```text
Y_post ~ Y_HF_ref
```

ULF DeltaHF-adjusted nuisance model:

```text
Y_post ~ Y_HF_ref + DeltaHFScore
```

`T_j` is used for FDR/QC/display. It is not a replacement for LOOCV prediction
or model-level formal permutation/bootstrap.

### Permutation

Use patient-level Freedman-Lane permutation with the branch-specific nuisance
model:

```text
B = 10000
seed = 42
```

For permutation `b`, recompute the same partial Spearman statistic `T_bj`.
The raw two-sided plus-one p value is:

```text
p_j = (1 + count(abs(T_bj) >= abs(T_j))) / (B + 1)
```

### Multiple-Comparison Correction

Apply Benjamini-Hochberg FDR correction to `p_j` within the exact cache family:

```text
model x endpoint x connectome x branch x tested_fiber_universe
```

The resulting q value is `q_bh_fdr`.

Bootstrap standard error or selection frequency must not be reported as FDR
p/q. Bootstrap outputs are stability summaries, not null-hypothesis
multiple-comparison correction.

### Required Outputs

HF outputs:

```text
normative_HF_fiber_fdr_cache.csv
normative_HF_fiber_fdr_cache_manifest.json
```

ULF outputs:

```text
normative_ULF_fiber_fdr_cache.csv
normative_ULF_fiber_fdr_cache_manifest.json
```

Required CSV fields:

```text
model_id
endpoint_slug
connectome
branch
fiber_id
selected_tau
selected_coverage
nuisance_model
rho_observed
p_raw_two_sided
q_bh_fdr
n_permutations
seed
tested_fiber_universe_hash
source_manifest_hash
```

Required manifest fields:

```text
model_id
endpoint_slug
connectome
branch
selected_tau
selected_coverage
n_subjects
n_tested_fibers
n_permutations
seed
nuisance_model
permutation_method
p_value_method
fdr_method
tested_fiber_universe_hash
input_manifest_hashes
created_at
```

---

## Enrichment Cache

### Unit And Background

The enrichment unit is the fiber, not the voxel.

For each model, endpoint, connectome, and branch, the background set is:

```text
B = all selected-source tau/Coverage candidate fibers tested in the selected final branch
```

Do not use voxel volume as the enrichment denominator. Plain touched-streamline
summaries may be reported as separate burden/display controls, but they are not
the canonical enrichment background.

### Foreground Sets

Confirmatory foreground:

```text
F_confirmatory_sweet = fibers with q_bh_fdr <= 0.05 and benefit-oriented effect > 0
F_confirmatory_sour  = fibers with q_bh_fdr <= 0.05 and benefit-oriented effect < 0
```

Display-only foreground:

```text
F_display_sweet = top percentile or top-k sweet fibers
F_display_sour  = top percentile or top-k sour fibers
```

If no FDR-significant fibers exist, display foregrounds may still be written but
must be marked:

```text
display_only_not_confirmatory
```

### Label Membership

For each fiber `j` and region/pathway label `r`:

```text
A_jr = 1 if fiber j has valid intersection with label r
A_jr = 0 otherwise
```

Label membership must be computed against the same tested fiber IDs used by the
selected final branch. Aggregate label summaries are not a substitute for the
fiber-level membership table.

### Enrichment Test

For each foreground family and label, build a 2x2 fiber-count table:

```text
foreground_in_region
foreground_outside_region
background_nonforeground_in_region
background_nonforeground_outside_region
```

Use a one-sided Fisher exact or equivalent hypergeometric over-representation
test:

```text
p_fisher_greater = P(foreground is over-represented in region r)
```

Apply Benjamini-Hochberg FDR across labels within:

```text
model x endpoint x connectome x branch x foreground_family
```

### Required Outputs

HF outputs:

```text
normative_HF_fiber_enrichment_cache.csv
normative_HF_fiber_enrichment_cache_manifest.json
```

ULF outputs:

```text
normative_ULF_fiber_enrichment_cache.csv
normative_ULF_fiber_enrichment_cache_manifest.json
```

Required CSV fields:

```text
model_id
endpoint_slug
connectome
branch
foreground_family
foreground_definition
background_definition
region_label
n_foreground
n_background
foreground_in_region
foreground_outside_region
background_nonforeground_in_region
background_nonforeground_outside_region
odds_ratio
enrichment_ratio
p_fisher_greater
q_bh_fdr
label_cache_hash
fdr_cache_hash
```

Required manifest fields:

```text
model_id
endpoint_slug
connectome
branch
foreground_families
background_definition
n_background
label_source
label_cache_hash
fdr_cache_hash
fdr_threshold
test_method
fdr_method
created_at
```

---

## Readiness Status

Cache definitions being documented is not the same as cache generation.

Before cache generation:

```text
fiber_fdr_cache_status = definition_documented_cache_not_generated
fiber_enrichment_cache_status = definition_documented_cache_not_generated
```

After successful generation:

```text
fiber_fdr_cache_status = complete
fiber_enrichment_cache_status = complete
```

A branch with valid density and label caches but missing FDR/enrichment caches
is still blocked from full figure-grade fiber outputs by:

```text
fdr_cache
enrichment_cache
```

These blockers are display/interpretation blockers only. They do not invalidate
completed source resolution, LOOCV, formal permutation/bootstrap, or the
independently recorded OSS and jitter readiness statuses.
