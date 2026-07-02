# STN/SNr VTA Coverage Analysis Plan

## /goal Text

Compute and summarize VTA/e-field coverage for the 16-patient STN/SNr cohort using Lead-DBS SimBio/Horn FEM outputs.

Use `/Users/mojackhu/Research/STNSNr/summary/cohort/subj/followup_stimulation.xlsx`, sheet `Contact Parameters`, as the programming input. Analyze the four clinical conditions `immediate/STN`, `immediate/STN+SNr`, `3m/STN`, and `3m/STN+SNr`.

Use the already thresholded atlas `Custom_Ewert_Zhang_Middlebrooks0.05` as the anatomical boundary source:

```text
/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/atlases/Custom_Ewert_Zhang_Middlebrooks0.05/{lh,rh}/{STN,SNr}.nii.gz
```

Read STN/SNr masks as `img > 0`. For each thresholded VTA, classify voxels into four mutually exclusive compartments:

```text
STN_only = VTA & STN & ~SNr
SNr_only = VTA & SNr & ~STN
STN_SNr  = VTA & STN & SNr
Outside  = VTA & ~(STN | SNr)
```

Use e-field thresholds `0.20 V/mm` for the primary analysis and `0.18 V/mm`, `0.22 V/mm` for sensitivity analyses. Treat Lead-DBS e-field images as `V/m`, so these thresholds correspond to `200`, `180`, and `220 V/m`. During e-field generation, set the Horn export threshold to the lowest analysis threshold, `0.18 V/mm`, to avoid clipping the low-threshold bounding box; derive final masks by thresholding exported MNI-space e-field NIfTI files.

Use Lead-DBS SimBio/Horn FEM settings with gray-matter conductivity `0.33 S/m` and white-matter conductivity `0.14 S/m`.

Map contacts from the clinical/review table as global 0-based contacts with left-side contacts numbered first. For each subject, initialize Lead-DBS `S` and read `S.numContacts = n`. If `Side == L`, require raw contact in `[0, n-1]` and map to Lead-DBS local contact `raw_contact + 1`. If `Side == R`, require raw contact in `[n, 2*n-1]` and map to Lead-DBS local contact `raw_contact - n + 1`. Use the workbook `Side` field directly for `Ls*` or `Rs*`.

Handle alternating stimulation by computing each alternating subprogram separately, then using the union of subprogram VTAs as condition-level coverage and writing overlap masks/QC separately. Do not model alternating stimulation as simultaneous double-cathode stimulation.

Write per-subject outputs under:

```text
/Volumes/VAL/STNSNr/derivatives/leaddbs/sub-*/connectomics/stnsnr_vta_coverage
```

Write cohort summary outputs under:

```text
/Volumes/VAL/STNSNr/summary/vta
```

Required deliverables include per-subject long coverage tables, contact mapping QC tables, manifests, thresholded VTA masks, VTA category masks, QC figures, and cohort-level long/wide/condition/sensitivity summary tables and figures. Validate workbook row counts, contact mapping, non-empty ROI masks, mutually exclusive compartment masks, category-count sums, monotonic threshold volumes, alternating union/overlap logic, and `git diff --check`.

## Summary

This analysis computes Lead-DBS SimBio/Horn FEM e-field outputs for the 16-patient STN/SNr cohort and summarizes thresholded VTA coverage across four STN/SNr anatomical compartments.

Programming input:

```text
/Users/mojackhu/Research/STNSNr/summary/cohort/subj/followup_stimulation.xlsx
sheet: Contact Parameters
```

Subject root:

```text
/Volumes/VAL/STNSNr/derivatives/leaddbs
```

STN/SNr anatomical boundaries:

```text
/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/atlases/Custom_Ewert_Zhang_Middlebrooks0.05/{lh,rh}/{STN,SNr}.nii.gz
```

The atlas masks are read as binary masks using `img > 0`. The original continuous `Custom_Ewert_Zhang_Middlebrooks` atlas is not re-thresholded in this analysis.

## Analysis Conditions

The pipeline analyzes all rows in the `Contact Parameters` sheet for:

- `immediate / STN`
- `immediate / STN+SNr`
- `3m / STN`
- `3m / STN+SNr`

E-field thresholds:

| Role | V/mm | V/m |
|---|---:|---:|
| sensitivity low | 0.18 | 180 |
| main | 0.20 | 200 |
| sensitivity high | 0.22 | 220 |

Lead-DBS e-field images are treated as V/m. Thresholded VTA masks are derived directly from MNI-space e-field NIfTI files and are not taken from Lead-DBS default binary VTA files.

During e-field generation, the Lead-DBS Horn export threshold is set to the lowest analysis threshold, `0.18 V/mm`, so that the exported e-field bounding box is not clipped for the low-threshold sensitivity analysis. Final VTA masks are still generated only by thresholding the exported e-field images at `180`, `200`, and `220 V/m`.

The helper pipeline may retry a Lead-DBS Horn e-field generation call if it fails during the internal quiver/VTA display-index writing step before the MNI e-field NIfTI is written. Retry handling does not change the stimulation settings, conductivity values, atlas masks, or downstream VTA thresholds. A generated program is accepted only when the expected MNI e-field NIfTI exists.

## VTA Model Settings

The pipeline uses the Lead-DBS SimBio/Horn FEM model:

- gray-matter conductivity: `0.33 S/m`
- white-matter conductivity: `0.14 S/m`
- e-field thresholding in V/m after model generation

The conductivity values enter the FEM volume conductor during e-field generation. The STN/SNr atlas masks are used only for anatomical coverage classification after the e-field has been generated.

## Patient-Level Parallel Execution

Parallel execution is supported only at the patient level. Each worker is an independent MATLAB batch process that handles one subject or a group of subjects. Within each subject, conditions, sides, and alternating subprograms are still processed sequentially to avoid file races inside the same Lead-DBS subject directory.

Worker rules:

- Workers call the same core analysis function with a subject subset.
- Workers write only per-subject outputs under `sub-*/connectomics/stnsnr_vta_coverage`.
- Workers do not write cohort summary files.
- Workers use subject-level lock directories to prevent two workers from processing the same subject simultaneously.
- Completed subject outputs can be skipped when rerunning a worker batch.

Launcher and aggregation rules:

- `run_stnsnr_vta_coverage_parallel.m` launches `N` independent MATLAB batch workers.
- `run_stnsnr_vta_coverage_worker.m` runs one worker subject subset.
- `run_stnsnr_vta_coverage_cohort_aggregate.m` reads all per-subject outputs after workers finish and writes the cohort summary tables/figures.
- Recommended initial worker count is `2` because SimBio/Horn itself can use multiple CPU threads and each MATLAB process can be memory intensive.
- Set `STNSNR_VTA_DRY_RUN=true` when running the launcher to write the planned job table without starting MATLAB workers.

The current single-process runner remains available for serial execution. A running serial process should not be overlapped with newly launched parallel workers unless it is stopped first, because the serial process was started before subject lock files existed.

## Contact Mapping

`Contact Parameters.Contact` is a clinical/review-table global 0-based contact number. The review table numbers left-side contacts first. For each subject, the pipeline initializes Lead-DBS stimulation structure `S` and reads `S.numContacts = n`.

The required mapping is:

```text
if Side == L:
    require raw_contact in [0, n-1]
    lead_contact_index = raw_contact + 1

if Side == R:
    require raw_contact in [n, 2*n-1]
    lead_contact_index = raw_contact - n + 1
```

The Lead-DBS stimulation side is taken directly from the workbook `Side` field:

```text
L -> Ls*
R -> Rs*
```

The pipeline does not infer side from Lead-DBS contact display labels because Lead-DBS internally uses `side 1 = R` and `side 2 = L`, while display labels can reflect electrode-specific conventions.

The contact mapping QC table must include subject ID, subject folder, phase, protocol, target, side, raw contact, mapped Lead-DBS contact, voltage, pulse width, frequency, stimulation pattern, and alternating group.

## Alternating Stimulation

Continuous stimulation:

- Same subject, phase, protocol, and continuous rows are combined into one condition.

Alternating stimulation:

- Rows are split by `AlternatingGroup`.
- Each alternating row/subprogram is computed as its own Lead-DBS stimulation.
- The main condition-level VTA is the union of subprogram VTA masks.
- The alternating overlap mask is written as QC.
- Alternating stimulation is not modeled as simultaneous double-cathode stimulation.

## Coverage Compartments

For each thresholded VTA mask, the pipeline classifies voxels into four mutually exclusive compartments:

```text
STN_only = VTA & STN & ~SNr
SNr_only = VTA & SNr & ~STN
STN_SNr  = VTA & STN & SNr
Outside  = VTA & ~(STN | SNr)
```

Each row of the long coverage table records voxel count, volume in mm3, percent of total VTA, and percent of the anatomical compartment covered.

## Outputs

Per-subject output root:

```text
/Volumes/VAL/STNSNr/derivatives/leaddbs/sub-*/connectomics/stnsnr_vta_coverage
```

Required per-subject outputs:

- `reports/sub-*_vta_coverage_long.csv`
- `reports/sub-*_contact_mapping_qc.csv`
- `reports/sub-*_vta_coverage_summary.md`
- `manifest/sub-*_vta_coverage_manifest.json`
- `masks/<condition>/*_desc-vta_thr-*.nii`
- `masks/<condition>/*_desc-vtaCategory_thr-*.nii`
- `figures/<condition>/*_desc-vtaCoverage_thr-*.png`

Cohort output root:

```text
/Volumes/VAL/STNSNr/summary/vta
```

Required cohort outputs:

- `cohort_vta_coverage_long.csv`
- `cohort_vta_coverage_wide.csv`
- `cohort_vta_coverage_by_condition.csv`
- `cohort_vta_threshold_sensitivity.csv`
- `cohort_contact_mapping_qc.csv`
- `cohort_vta_generation_manifest.json`
- `figures/coverage_stacked_bar_thr0p20.png`
- `figures/coverage_boxplot_by_condition_thr0p20.png`
- `figures/coverage_threshold_sensitivity.png`

## Validation

Workbook QC:

- 16 unique subjects.
- 194 contact rows.
- No missing voltage, pulse width, or frequency values.

Contact mapping QC:

- All raw contacts follow the left-first numbering rule.
- All mapped Lead-DBS contacts are in `1:S.numContacts`.
- Cohort aggregation normalizes per-subject contact QC columns to snake_case
  names before validation, because the per-subject contact files preserve the
  workbook-derived column names.

ROI QC:

- `Custom_Ewert_Zhang_Middlebrooks0.05` STN/SNr masks are non-empty after reslicing to each e-field grid.

Category QC:

- The four category masks are mutually exclusive.
- Category voxel counts sum to the total thresholded VTA voxel count.

Threshold QC:

- VTA volume is monotonic across thresholds: `0.18 V/mm >= 0.20 V/mm >= 0.22 V/mm`.

Alternating QC:

- Union volume is greater than or equal to each subprogram volume.
- Overlap volume is less than or equal to union volume.

Output QC:

- Each subject has per-subject reports, masks, figures, and manifest.
- Cohort summary tables and figures exist.
- `git diff --check` passes.
