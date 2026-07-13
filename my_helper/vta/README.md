# Generic VTA/E-field Pipeline

The generic VTA pipeline consumes canonical stimulation records from a
`study_base.json` file and model parameters from a `vta_model.yaml` file.
Project-specific workbooks, target labels, component labels, HF/ULF roles, and
clinical endpoint definitions are outside the VTA execution contract.

## Public Model Profile

The `vta_model_v1` public profile contains only tissue conductivity, atlas,
output-space, and binary-threshold settings:

```yaml
schema_version: vta_model_v1
profile_type: vta_model

fem:
  conductivity_s_per_m:
    gray_matter: 0.33
    white_matter: 0.14
  atlas_set: Custom_Ewert_Zhang_Middlebrooks

outputs:
  spaces:
    - native
    - MNI152NLin2009bAsym
  binary_vta:
    primary_threshold_v_per_mm: 0.20
    sensitivity_thresholds_v_per_mm:
      - 0.18
      - 0.22
```

Threshold values in this profile use `V/mm`. Continuous E-field NIfTI values
and threshold application use `V/m`, so the effective thresholds are 180, 200,
and 220 V/m.

## Fixed Internal Behavior

The public YAML does not expose backend selection, solve unit, mesh controls,
tissue-surface controls, electrode removal, smoke settings, random seeds, or
acceptance tolerances. Production calculations use `simbio_onesolve` and the
Lead-DBS internal default `remove_electrode=true`.

Continuous frequency-group sources are solved jointly. Alternating sources are
solved independently, and their group-level peak E-field is derived using a
voxelwise maximum. The pipeline does not infer duty cycle or generate a
time-weighted E-field.
