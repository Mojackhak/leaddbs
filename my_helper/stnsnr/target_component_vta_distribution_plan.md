# STN/SNr Target-Component VTA Distribution

## Purpose

This analysis compares VTA anatomical coverage for programming components
labelled as `STN` versus programming components labelled as `SNr`.

The clinical union VTA analysis remains authoritative for the actual delivered
stimulation condition:

```text
/Volumes/VAL/STNSNr/summary/vta/cohort_vta_coverage_long.csv
```

This target-component analysis is a secondary/proxy analysis. For continuous
`STN+SNr` stimulation, the STN-labelled and SNr-labelled contacts are split and
modeled as separate target-specific components. Those split results are not the
true synchronous combined field; they estimate target-specific component
coverage.

## Analysis Unit

The unit is:

```text
subject_id x phase x protocol x side x target
```

where `target` is `STN` or `SNr`. Multiple contacts with the same target in the
same subject, phase, protocol, and side are merged into one component.

Expected component count from the current contact QC table:

```text
STN target components: 126
SNr target components: 64
Total: 190
```

## Coverage Definition

VTA thresholds:

```text
0.18, 0.20, 0.22 V/mm
```

Anatomical masks:

```text
Custom_Ewert_Zhang_Middlebrooks0.05/{lh,rh}/{STN,SNr}.nii.gz
```

Each thresholded VTA voxel is assigned to exactly one category:

```text
STN_only = VTA & STN & ~SNr
SNr_only = VTA & SNr & ~STN
STN_SNr  = VTA & STN & SNr
Outside  = VTA & ~(STN | SNr)
```

## Component Origin Labels

- `observed_single_target`: the original side-level condition contains only one
  target and can be reused as-is.
- `observed_target_union`: multiple subprograms or contacts of the same target
  are represented as a union.
- `counterfactual_component_from_continuous_mixed`: continuous `STN+SNr`
  stimulation split into target-specific components.

## Outputs

Output root:

```text
/Volumes/VAL/STNSNr/summary/vta/target_component_distribution
```

Required outputs:

- `cohort_target_component_vta_coverage_long.csv`
- `cohort_target_component_vta_coverage_wide.csv`
- `cohort_target_component_distribution_summary.csv`
- `cohort_target_component_contact_qc.csv`
- `cohort_target_component_generation_manifest.json`
- `figures/target_component_stacked_bar_thr0p20.png`
- `figures/target_component_boxplot_thr0p20.png`
- `figures/target_component_threshold_sensitivity.png`

## Validation

- The input contact QC table has 194 rows.
- All `contact_side_rule_ok` values are true.
- Component counts are 126 STN, 64 SNr, and 190 total.
- Each component has four category rows per threshold.
- Category voxel counts sum to the total thresholded VTA voxel count.
- Thresholded total VTA volume is monotonic:
  `0.18 V/mm >= 0.20 V/mm >= 0.22 V/mm`.
- Target-component outputs do not overwrite the clinical union VTA outputs.
