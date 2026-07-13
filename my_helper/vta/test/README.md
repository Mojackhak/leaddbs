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

Historical voltage artifacts retain the atlas identity recorded in their own
manifest. Any new voltage or current acceptance run uses the canonical atlas
`Custom_Ewert_Zhang_Middlebrooks`; an earlier `0.05`-suffixed atlas directory
must not be silently treated as the current acceptance atlas.

The runner:

1. reads source, electrode, reconstruction, and subject paths from
   `study_base.json`;
2. copies the selected Lead-DBS subject into a private validation BIDS layout
   at `copied_subject/derivatives/leaddbs/sub-*`, together with the source
   dataset description required by `ea_getptopts`;
3. archives any copied head model and builds and hashes one fresh shared head
   model before the measured runs;
4. runs `simbio` and `simbio_onesolve` twice per hemisphere with the same
   explicit per-side RNG seed and distinct stimulation labels, recording the
   actual Horn attempt seed used by every run;
5. compares native and MNI continuous E-fields;
6. derives 180, 200, and 220 V/m masks from each continuous E-field; and
7. fails the MATLAB process when any per-side gate fails.

The source Lead-DBS subject tree is read-only. A validation root is never
automatically deleted. `ReusePreparedRoot=true` is accepted only for an
incomplete, output-free prepared root; a root containing backend outputs or an
acceptance summary is rejected to prevent stale-output reuse.
The official SNr003 pilot always requires a new root and rejects prepared-root
reuse. Any Horn retry also fails the matched-RNG acceptance gate because it
changes the actual attempt seed.

The official pilot scope is `SNr003`, `T1`, program `1`, with bilateral
Medtronic 3387 leads. Parameter overrides are retained for synthetic contract
tests and future pilots, but such runs are labeled as custom scope and cannot
be reported as the official SNr003 pilot.

The runner applies a process-scoped `MNI152NLin2009bAsym` Lead-DBS space
override so atlas lookup, patient-space atlas materialization, output folders,
and coordinate transforms do not depend on the user's persistent GUI space
preference. The previous environment value is restored when the runner exits.

## Acceptance Limits

Continuous E-fields must have identical dimensions and finite masks, affine
maximum absolute difference at most `1e-12`, value maximum absolute difference
at most `1e-3 V/m`, relative L2 error at most `1e-5`, and Pearson correlation
at least `0.999999`.

For each threshold, binary masks must have Dice at least `0.999`, relative
volume difference at most `0.001`, and every discordant voxel must be within
`1e-3 V/m` of the threshold in both input E-fields. Backend repeat runs must be
voxel-identical.

An equivalence pass also requires each input image to contain finite,
nonzero E-field signal and at least one suprathreshold voxel at every requested
threshold. Identical all-NaN, all-zero, or empty-VTA outputs are invalid and
cannot pass by numerical identity alone.

## Entry Point

```matlab
run_single_source_backend_equivalence( ...
    'StudyBase', '/path/to/study_base.json', ...
    'WorkRoot', '/path/to/validation');
```

The default selection is `SNr003`, `T1`, program `1`. The generated validation
directory contains manifests, case inventories, head-model hashes, comparison
tables, summaries, copied inputs, and backend outputs.

## Deterministic Current Acceptance

`run_single_current_backend_equivalence` is the current-controlled companion to
the historical voltage pilot. The two suites remain separate evidence: the
voltage suite reuses the existing SNr003 bilateral single-source outputs,
while the current suite generates one deterministic hypothetical right-sided
current program and compares the standard SimBio current path with
the canonical `simbio_onesolve` current path. A voltage pass is not treated as
current evidence, and synthetic current tests are not reported as completed
real-FEM acceptance.

The current fixture seed is fixed at `20260712`. Generated amplitudes are in
the inclusive range `0.5-5.0 mA`, pulse widths are in the inclusive range
`30-120 us`, and every fixture uses the atlas
`Custom_Ewert_Zhang_Middlebrooks`. The real FEM inventory contains exactly one
right-sided cathode with case return. Its amplitude and pulse width are selected
deterministically from those ranges.

Fixture ordering, selected contacts, amplitudes, pulse widths, and fractions
must be byte-stable for the same seed. The runner refuses a `WorkRoot` that is
the production Lead-DBS derivatives tree, lies inside it, or contains it. Real
acceptance always operates on a copied subject below a new validation root and
never writes the source SNr003 subject tree.

The current FEM gate runs the standard `simbio` path once and the
`simbio_onesolve` path once, for exactly two FEM solves. It uses the same
native/MNI continuous E-field and 180/200/220 V/m gates listed above. Bilateral
single-voltage metrics are recomputed from existing paired outputs without new
voltage FEM. Multiple-cathode, electrode-return, repeatability, and vector
superposition remain solver-free unit fixtures; the vector fixture verifies
that neither scalar maximum nor scalar sum can replace signed vector
superposition.

The reference solve uses the standard Lead-DBS `simbio` current path. The
candidate solve uses the canonical task `simbio_onesolve` implementation, which
supports current-controlled boundaries and reuses the same fixed native
headmodel in the copied subject. The older registry wrapper whose one-solve
contract is voltage-only is not used for the current candidate solve.

Numerical comparison uses the standard `simbio` local E-field grid as the
fixed comparison grid. For a valid fresh acceptance run, the canonical raw
tetrahedral E-field is interpolated directly to the standard native reference
grid during candidate export; it must not first be reduced to the 0.7 mm
production native grid. MNI comparison still uses world-coordinate linear
resampling to the standard MNI reference grid, and thresholds are applied only
after alignment. Re-comparison of existing NIfTI outputs starts no FEM, but it
cannot recover raw tetrahedral detail that was previously exported only on the
coarser production grid.

When candidate and reference dimensions and affine already match, alignment is
an identity operation. The comparison helper skips interpolation in that case
to preserve the original finite support at image boundaries.

The lightweight test entry point exercises fixture generation, safety guards,
inventory validation, and the independent vector-superposition fixture. The
existing synthetic NIfTI comparison test separately verifies the shared strict
E-field/VTA gates. Neither test invokes meshing or FEM:

```matlab
r = testsuite('my_helper/vta/test/test_run_single_current_backend_equivalence.m');
assertSuccess(run(r));
```

The copied-subject FEM acceptance is deliberately separate and must be started
explicitly:

```matlab
run_single_current_backend_equivalence( ...
    'StudyBase', '/Volumes/VAL/STNSNr/summary/cohort/subj/study_base.json', ...
    'WorkRoot', '/Volumes/VAL/STNSNr/validation', ...
    'SubjectId', 'SNr003');
```

An existing current FEM pair can be compared again without copying a subject,
meshing, or solving:

```matlab
run_single_current_backend_equivalence( ...
    'Mode', 'compare_existing', ...
    'ExistingRunRoot', '/path/to/vta_single_current_backend_equivalence_RUN');
```

This mode requires the recorded single right-sided case and both backend
E-fields. It refreshes only the comparison CSV files and acceptance summary.
Existing versions of those untracked files are moved to the filesystem Trash
before replacement. The refreshed overall result also preserves the original
`production_subject_tree_unchanged` safety gate.

This command is not part of the lightweight test suite and is not run while the
current harness itself is being implemented.
