# VTA Backend Acceptance Tests

This directory contains project-agnostic acceptance tests for the reusable VTA
engine. The tests consume a validated study-base JSON document and never parse
project workbooks or infer frequency roles from anatomical component labels.

## Single-Source Backend Equivalence

`run_single_source_backend_equivalence` compares the standard Lead-DBS SimBio
backend with the helper one-solve backend for one identical voltage source.
The current real-data pilot is deliberately bounded to subject `SNr003`, phase
`T1`, program `1`, and both Medtronic 3387 hemispheres. Passing this pilot does
not establish numerical equivalence for SceneRay electrodes or multi-source
stimulation.

The runner:

1. reads source, electrode, reconstruction, and subject paths from
   `study_base.json`;
2. copies the selected Lead-DBS subject into a new validation root;
3. archives any copied head model and builds one fresh shared head model;
4. runs `simbio` and `simbio_onesolve` twice per hemisphere with fixed RNG
   seeds and distinct stimulation labels;
5. compares native and MNI continuous E-fields;
6. derives 180, 200, and 220 V/m masks from each continuous E-field; and
7. fails the MATLAB process when any per-side gate fails.

The source Lead-DBS subject tree is read-only. A validation root is never
overwritten or automatically deleted.

## Acceptance Limits

Continuous E-fields must have identical dimensions and finite masks, affine
maximum absolute difference at most `1e-12`, value maximum absolute difference
at most `1e-3 V/m`, relative L2 error at most `1e-5`, and Pearson correlation
at least `0.999999`.

For each threshold, binary masks must have Dice at least `0.999`, relative
volume difference at most `0.001`, and every discordant voxel must be within
`1e-3 V/m` of the threshold in both input E-fields. Backend repeat runs must be
voxel-identical.

## Entry Point

```matlab
run_single_source_backend_equivalence( ...
    'StudyBase', '/path/to/study_base.json', ...
    'WorkRoot', '/path/to/validation');
```

The default selection is `SNr003`, `T1`, program `1`. The generated validation
directory contains manifests, case inventories, head-model hashes, comparison
tables, summaries, copied inputs, and backend outputs.
