# STN/SNr Seed-Target Target-Atlas Registry

Date: 2026-07-01

## Purpose

This document is the authoritative registry for target ROI and atlas selection in STN/SNr seed-target fiber tracking and for ROI interpretation in the STN/SNr normative connectome models. It fixes the preferred ROI directory, upstream atlas source, sensitivity atlas, threshold, and interpretation boundary for each planned STN or SNr pathway.

The registry is documentation-only. It does not run tracking and does not change any MATLAB or Python implementation.

## General Rules

- Model-level STN ROI and endpoint grouping should use `STN-connected regions` first.
- Model-level SNr ROI and endpoint grouping should use `SNr-connected regions` first.
- The connected-region atlases are prebuilt binary ROI directories with side-specific masks, `roi_manifest.csv`, and `roi_qc.csv`.
- `Custom_Ewert_Zhang_Middlebrooks0.05` remains the upstream source for STN/SNr masks and is retained as a sensitivity or fallback source for standalone STN/SNr masks.
- Cortical and whole-brain endpoint labels use connected-region ROI masks first; their upstream cortical definitions use `HCPex (Huang 2021)` when a suitable label exists.
- Thalamic subnuclei use `Julich-Brain Atlas v3.1` probabilistic maps.
- PPN uses `PPN_Atlas (Alho 2017)` as the primary atlas and `PPN (Snijders 2016)` as a sensitivity atlas.
- Superior colliculus uses `Allen Brain Atlas (Ding 2020)` `SC.nii.gz`.
- All ROIs are defined first in MNI152NLin2009bAsym space, then transformed to anchorNative and DWI/b0 space for tractography.

## Threshold Rules

| ROI source | Main threshold | Sensitivity threshold | Notes |
|---|---:|---:|---|
| `STN-connected regions` | follow `roi_manifest.csv` | sensitivity masks in the same atlas directory | Preferred ROI directory for STN model gating, STN candidate fibers, and STN endpoint grouping. |
| `SNr-connected regions` | follow `roi_manifest.csv` | sensitivity masks in the same atlas directory | Preferred ROI directory for SNr model gating, SNr candidate fibers, and SNr endpoint grouping. |
| `Custom_Ewert_Zhang_Middlebrooks0.05` STN/SNr/GPe/GPi | `relative_intensity > 0.05` | `relative_intensity > 0.5` | `0.05` is the atlas metadata threshold; `0.5` is a conservative high-confidence core ROI. |
| `HCPex (Huang 2021)` label masks | exact label ID membership | none by default | Side-specific label IDs should be recorded in implementation provenance. |
| `Julich-Brain Atlas v3.1` probabilistic maps | probability `>= 25%` | probability `> 0%` and `>= 50%` | Use the same threshold for left and right maps. |
| Single-mask atlases, including PPN and Allen SC | image value `> 0` | none by default | Binarize after spatial resampling. |
| Derived posterior putamen | HCPex Putamen posterior MNI-y half | posterior MNI-y third | Split is computed within each side-specific putamen mask. |

## Primary Seeds

| Seed | Primary atlas | Main ROI files | Sensitivity |
|---|---|---|---|
| STN | `STN-connected regions` | `lh/STN.nii.gz`, `rh/STN.nii.gz` | `STN_thr025` and `STN_thr05` sensitivity masks in the same atlas directory. |
| SNr | `SNr-connected regions` | `lh/SNr.nii.gz`, `rh/SNr.nii.gz` | `SNr_thr025` and `SNr_thr05` sensitivity masks in the same atlas directory. |

## STN Target Registry

| Pathway | Primary target atlas | Primary ROI definition | Sensitivity / notes |
|---|---|---|---|
| `STN -> M1` | `STN-connected regions` | `lh/M1.nii.gz`, `rh/M1.nii.gz` | Upstream source: HCPex `Primary_Motor_Cortex`; optional sensitivity with Julich BA4a/BA4p or HMAT M1. |
| `STN -> SMA/pre-SMA` | `STN-connected regions` | `lh/SMA.nii.gz`, `rh/SMA.nii.gz`, `lh/preSMA.nii.gz`, `rh/preSMA.nii.gz` | Upstream source: HCPex Area 6/SCEF labels; HMAT SMA/preSMA sensitivity. |
| `STN -> premotor cortex` | `STN-connected regions` | `lh/premotor.nii.gz`, `rh/premotor.nii.gz` | Upstream source: HCPex premotor Area 6 labels; HMAT PMd sensitivity. |
| `STN -> GPe/GPi` | `STN-connected regions` | `lh/GPe.nii.gz`, `rh/GPe.nii.gz`, `lh/GPi.nii.gz`, `rh/GPi.nii.gz` | Upstream source: DISTAL `>0.25`; `GPe_thr005`, `GPe_thr05`, `GPi_thr005`, and `GPi_thr05` sensitivity masks. |
| `STN -> DLPFC` | `STN-connected regions` | `lh/DLPFC.nii.gz`, `rh/DLPFC.nii.gz` | Exploratory target; upstream source: HCPex Area 46, 9/46, 9, and 8 labels. |
| `STN -> ACC` | `STN-connected regions` | `lh/ACC.nii.gz`, `rh/ACC.nii.gz` | Optional target; upstream source: HCPex cingulate labels. |
| `STN -> OFC-vmPFC` | `STN-connected regions` | `lh/OFC.nii.gz`, `rh/OFC.nii.gz`, `lh/vmPFC.nii.gz`, `rh/vmPFC.nii.gz` | Optional target; upstream source: HCPex OFC/medial prefrontal labels. |

## SNr Target Registry

| Pathway | Primary target atlas | Primary ROI definition | Sensitivity / notes |
|---|---|---|---|
| `SNr -> VA/VL/VM thalamus` | `SNr-connected regions` | `lh/VA_thalamus.nii.gz`, `rh/VA_thalamus.nii.gz`, `lh/VLA_thalamus.nii.gz`, `rh/VLA_thalamus.nii.gz`, `lh/VLP_thalamus.nii.gz`, `rh/VLP_thalamus.nii.gz`, `lh/VM_thalamus.nii.gz`, `rh/VM_thalamus.nii.gz` | Upstream source: Julich-Brain v3.1 `>=25%`; threshold sensitivity masks in the same atlas directory. |
| `SNr -> STN` | `SNr-connected regions` | `lh/STN.nii.gz`, `rh/STN.nii.gz` | `STN_thr025` and `STN_thr05` sensitivity masks in the same atlas directory. |
| `SNr -> posterior putamen` | `SNr-connected regions` | `lh/posterior_putamen.nii.gz`, `rh/posterior_putamen.nii.gz` | `posterior_putamen_third` sensitivity masks. |
| `SNr -> caudate` | `SNr-connected regions` | `lh/caudate.nii.gz`, `rh/caudate.nii.gz` | Optional target; upstream source: HCPex caudate labels. |
| `SNr -> PPN area` | `SNr-connected regions` | `lh/PPN.nii.gz`, `rh/PPN.nii.gz` | `PPN_snijders2016` sensitivity masks. |
| `SNr -> superior colliculus` | `SNr-connected regions` | `lh/superior_colliculus.nii.gz`, `rh/superior_colliculus.nii.gz` | Upstream source: Allen Brain Atlas `SC.nii.gz`; keep separate from pretectal region. |
| `SNr -> MD / CM-Pf` | `SNr-connected regions` | `lh/MD_thalamus.nii.gz`, `rh/MD_thalamus.nii.gz`, `lh/CM_thalamus.nii.gz`, `rh/CM_thalamus.nii.gz`, `lh/Pf_thalamus.nii.gz`, `rh/Pf_thalamus.nii.gz`, `lh/sPf_thalamus.nii.gz`, `rh/sPf_thalamus.nii.gz` | Optional target; threshold sensitivity masks in the same atlas directory. |
| `SNr -> FEF` | `SNr-connected regions` | `lh/FEF.nii.gz`, `rh/FEF.nii.gz` | Exploratory cortical target. |
| `SNr -> SMA / pre-SMA` | `SNr-connected regions` | `lh/SMA.nii.gz`, `rh/SMA.nii.gz`, `lh/preSMA.nii.gz`, `rh/preSMA.nii.gz` | Exploratory cortical target; HMAT sensitivity. |
| `SNr -> premotor cortex` | `SNr-connected regions` | `lh/premotor.nii.gz`, `rh/premotor.nii.gz` | Exploratory cortical target. |
| `SNr -> M1` | `SNr-connected regions` | `lh/M1.nii.gz`, `rh/M1.nii.gz` | Exploratory cortical target. |
| `SNr -> DLPFC` | `SNr-connected regions` | `lh/DLPFC.nii.gz`, `rh/DLPFC.nii.gz` | Exploratory cortical target. |

## Atlas Path Registry

| Atlas | Local path |
|---|---|
| `STN-connected regions` | `/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/atlases/STN-connected regions` |
| `SNr-connected regions` | `/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/atlases/SNr-connected regions` |
| `Custom_Ewert_Zhang_Middlebrooks0.05` | `/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/atlases/Custom_Ewert_Zhang_Middlebrooks0.05` |
| `HCPex (Huang 2021)` | `/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/labeling/HCPex (Huang 2021).nii` |
| `Julich-Brain Atlas v3.1` | `/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/labeling/Julich-Brain Atlas-v3.1/probabilistic-maps_PMs_207-areas` |
| `PPN_Atlas (Alho 2017)` | `/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/atlases/PPN_Atlas (Alho 2017)` |
| `PPN (Snijders 2016)` | `/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/atlases/PPN (Snijders 2016)` |
| `Allen Brain Atlas (Ding 2020)` | `/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/atlases/Allen Brain Atlas (Ding 2020)` |
| `HMAT (Mayka 2005)` | `/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/labeling/HMAT (Mayka 2005).nii` |
| `Julich BA4 sensitivity labels` | `/Users/mojackhu/Github/leaddbs/templates/space/MNI152NLin2009bAsym/labeling/Juelich-gm-thr25-2mm (Eickhoff 2005).nii` |

## Interpretation Boundaries

- These target ROIs define seed-target tractography endpoints and anatomical grouping, not causal pathway activation by themselves.
- STN and SNr ROIs are not used to crop VTA or truncate streamlines.
- For stimulation-linked analyses, report both the full seed-target bundle and the stimulation-covered subset, such as `VTA_seed_hit`.
- Small brainstem and thalamic targets should be interpreted cautiously because DWI resolution and registration error can dominate ROI-level tractography results.
- Atlas sensitivity analyses are required before interpreting a pathway as target-specific when the target is small, probabilistic, or derived.
