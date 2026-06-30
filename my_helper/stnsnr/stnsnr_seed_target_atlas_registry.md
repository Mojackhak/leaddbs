# STN/SNr Seed-Target Target-Atlas Registry

Date: 2026-07-01

## Purpose

This document is the authoritative registry for target ROI and atlas selection in STN/SNr seed-target fiber tracking. It fixes the primary atlas, sensitivity atlas, threshold, and interpretation boundary for each planned STN or SNr pathway.

The registry is documentation-only. It does not run tracking and does not change any MATLAB or Python implementation.

## General Rules

- Primary STN and SNr seed ROIs use `Custom_Ewert_Zhang_Middlebrooks0.05`.
- Cortical and whole-brain endpoint labels use `HCPex (Huang 2021)` when a suitable label exists.
- Thalamic subnuclei use `Julich-Brain Atlas v3.1` probabilistic maps.
- PPN uses `PPN_Atlas (Alho 2017)` as the primary atlas and `PPN (Snijders 2016)` as a sensitivity atlas.
- Superior colliculus uses `Allen Brain Atlas (Ding 2020)` `SC.nii.gz`.
- All ROIs are defined first in MNI152NLin2009bAsym space, then transformed to anchorNative and DWI/b0 space for tractography.

## Threshold Rules

| ROI source | Main threshold | Sensitivity threshold | Notes |
|---|---:|---:|---|
| `Custom_Ewert_Zhang_Middlebrooks0.05` STN/SNr/GPe/GPi | `relative_intensity > 0.05` | `relative_intensity > 0.5` | `0.05` is the atlas metadata threshold; `0.5` is a conservative high-confidence core ROI. |
| `HCPex (Huang 2021)` label masks | exact label ID membership | none by default | Side-specific label IDs should be recorded in implementation provenance. |
| `Julich-Brain Atlas v3.1` probabilistic maps | probability `>= 25%` | probability `> 0%` and `>= 50%` | Use the same threshold for left and right maps. |
| Single-mask atlases, including PPN and Allen SC | image value `> 0` | none by default | Binarize after spatial resampling. |
| Derived posterior putamen | HCPex Putamen posterior MNI-y half | posterior MNI-y third | Split is computed within each side-specific putamen mask. |

## Primary Seeds

| Seed | Primary atlas | Main ROI files | Sensitivity |
|---|---|---|---|
| STN | `Custom_Ewert_Zhang_Middlebrooks0.05` | `lh/STN.nii.gz`, `rh/STN.nii.gz` | high-confidence core with `> 0.5` |
| SNr | `Custom_Ewert_Zhang_Middlebrooks0.05` | `lh/SNr.nii.gz`, `rh/SNr.nii.gz` | high-confidence core with `> 0.5` |

## STN Target Registry

| Pathway | Primary target atlas | Primary ROI definition | Sensitivity / notes |
|---|---|---|---|
| `STN -> M1` | `HCPex (Huang 2021)` | `Primary_Motor_Cortex_L/R` | Optional sensitivity with Julich BA4a/BA4p or HMAT M1. |
| `STN -> SMA/pre-SMA` | `HCPex (Huang 2021)` | `Area_6m_anterior`, `Area_6mp`, `Supplementary_and_Cingulate_Eye_Field` | HMAT SMA/preSMA sensitivity. |
| `STN -> premotor cortex` | `HCPex (Huang 2021)` | `Area_6_anterior`, `Dorsal_area_6`, `Rostral_Area_6`, `Ventral_Area_6`, `Premotor_Eye_Field` | HMAT PMd sensitivity. |
| `STN -> GPe/GPi` | `HCPex (Huang 2021)` | `Globus_pallidus_externalis_L/R`, `Globus_pallidus_internalis_L/R` | Custom GPe/GPi `> 0.05`; Custom GPe/GPi `> 0.5` core sensitivity. |
| `STN -> DLPFC` | `HCPex (Huang 2021)` | `Area_46`, `Area_9-46d`, `Area_9_Middle`, `Area_9_anterior`, `Area_9_Posterior`, `Area_8Ad`, `Area_8Av`, `Area_8B_Lateral`, `Area_8C` | Exploratory target. |
| `STN -> ACC` | `HCPex (Huang 2021)` | `Dorsal_Area_24d`, `Ventral_Area_24d`, `Area_25`, `Area_33_prime`, `Area_p32`, `Area_p32_prime`, `Area_s32` | Optional target. |
| `STN -> OFC-vmPFC` | `HCPex (Huang 2021)` | `Posterior_OFC_Complex`, `Orbital_Frontal_Complex`, `Area_10r`, `Area_10v`, `Area_10d`, `Area_25`, `Area_s32` | Optional target. |

## SNr Target Registry

| Pathway | Primary target atlas | Primary ROI definition | Sensitivity / notes |
|---|---|---|---|
| `SNr -> VA/VL/VM thalamus` | `Julich-Brain Atlas v3.1` | `Thalamus-VA`, `Thalamus-VLA`, `Thalamus-VLP`, `Thalamus-VM` | HCPex VA/VLa/VLp as coarse comparator. |
| `SNr -> STN` | `Custom_Ewert_Zhang_Middlebrooks0.05` | `lh/STN.nii.gz`, `rh/STN.nii.gz`, `> 0.05` | Custom STN `> 0.5` core sensitivity. |
| `SNr -> posterior putamen` | `HCPex (Huang 2021)` | `Putamen_L/R`, posterior MNI-y half | Posterior MNI-y third sensitivity. |
| `SNr -> caudate` | `HCPex (Huang 2021)` | `Caudate_L/R` | Optional target. |
| `SNr -> PPN area` | `PPN_Atlas (Alho 2017)` | `lh/PPN.nii.gz`, `rh/PPN.nii.gz`, binarized `> 0` | `PPN (Snijders 2016)` sensitivity. |
| `SNr -> superior colliculus` | `Allen Brain Atlas (Ding 2020)` | `lh/SC.nii.gz`, `rh/SC.nii.gz`, binarized `> 0` | Keep separate from pretectal region. |
| `SNr -> MD / CM-Pf` | `Julich-Brain Atlas v3.1` | `Thalamus-MD`, `Thalamus-CM`, `Thalamus-Pf`, optional `Thalamus-sPf` | Optional target. |
| `SNr -> FEF` | `HCPex (Huang 2021)` | `Frontal_Eye_Fields_L/R` | Exploratory cortical target. |
| `SNr -> SMA / pre-SMA` | `HCPex (Huang 2021)` | `Area_6m_anterior`, `Area_6mp`, `Supplementary_and_Cingulate_Eye_Field` | Exploratory cortical target; HMAT sensitivity. |
| `SNr -> premotor cortex` | `HCPex (Huang 2021)` | `Area_6_anterior`, `Dorsal_area_6`, `Rostral_Area_6`, `Ventral_Area_6`, `Premotor_Eye_Field` | Exploratory cortical target. |
| `SNr -> M1` | `HCPex (Huang 2021)` | `Primary_Motor_Cortex_L/R` | Exploratory cortical target. |
| `SNr -> DLPFC` | `HCPex (Huang 2021)` | `Area_46`, `Area_9-46d`, Area 9 and Area 8 subdivisions | Exploratory cortical target. |

## Atlas Path Registry

| Atlas | Local path |
|---|---|
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
