# VTA Backend Acceptance Tests

This directory contains project-agnostic acceptance tests for the reusable VTA
engine. The tests consume a validated study-base JSON document and never parse
project workbooks or infer frequency roles from anatomical component labels.

## Paired Voltage And Current Backend Equivalence

`run_voltage_backend_equivalence` and `run_current_backend_equivalence` compare
the standard Lead-DBS SimBio reference with the same canonical production
backend in voltage and current mode, respectively. Voltage and current are
boundary strategies inside one backend; they do not have separate production
export implementations. The voltage runner uses one identical voltage source.
The historical voltage pilot is bounded to subject `SNr003`, phase `T1`,
program `1`, and both Medtronic 3387 hemispheres. The fresh current pilot uses
the same subject geometry but one fixed hypothetical right-sided current case.
Neither result establishes numerical equivalence for SceneRay electrodes or
multi-source clinical stimulation.

Historical voltage artifacts retain the atlas identity recorded in their own
manifest. Any new voltage or current acceptance run uses the canonical atlas
`Custom_Ewert_Zhang_Middlebrooks`; an earlier `0.05`-suffixed atlas directory
must not be silently treated as the current acceptance atlas.

Historical paired voltage outputs are refreshed with
`Mode='compare_existing'` and an explicit `ExistingRunRoot`. This mode starts
no FEM, copies no subject, and refreshes only comparison tables and summaries;
the replaced untracked files are moved to the filesystem Trash. It preserves
the historical manifest's atlas, code, and scope instead of relabeling those
outputs as a current-atlas run.

The historical voltage runner:

1. reads source, electrode, reconstruction, and subject paths from
   `study_base.json`;
2. copies the selected Lead-DBS subject into a private validation BIDS layout
   at `copied_subject/derivatives/leaddbs/sub-*`, together with the source
   dataset description required by `ea_getptopts`;
3. archives any copied head model and builds and hashes one fresh shared head
   model before the measured runs;
4. runs standard `simbio` and the unified canonical backend twice per
   hemisphere with the same explicit per-side RNG seed and distinct output
   labels, recording the actual Horn attempt seed used by every standard run;
5. compares native continuous E-fields;
6. derives and compares native 180, 200, and 220 V/m masks;
7. validates canonical native-to-MNI transformation and MNI thresholding
   independently of legacy direct-MNI interpolation; and
8. fails the MATLAB process when any per-side gate fails.

The source Lead-DBS subject tree is read-only. A validation root is never
automatically deleted. `ReusePreparedRoot=true` is accepted only for an
incomplete, output-free prepared root; a root containing backend outputs or an
acceptance summary is rejected to prevent stale-output reuse.
The official SNr003 pilot always requires a new root and rejects prepared-root
reuse. Any Horn retry also fails the matched-RNG acceptance gate because it
changes the actual attempt seed.

The historical voltage pilot scope is `SNr003`, `T1`, program `1`, with
bilateral Medtronic 3387 leads. Parameter overrides are retained for synthetic
contract tests and future pilots, but such runs are labeled as custom scope and
cannot be reported as that historical pilot.

The runner applies a process-scoped `MNI152NLin2009bAsym` Lead-DBS space
override so atlas lookup, patient-space atlas materialization, output folders,
and coordinate transforms do not depend on the user's persistent GUI space
preference. The previous environment value is restored when the runner exits.

## Acceptance Limits

Native continuous E-fields must have identical dimensions and finite masks,
affine maximum absolute difference at most `1e-12`, value maximum absolute
difference at most `0.05 V/m`, relative L2 error at most `1e-5`, and Pearson
correlation at least `0.999999`.

For each native threshold, binary masks must have Dice at least `0.999` and
relative volume difference at most `0.001`. Historical voltage backend repeat
runs must be voxel-identical. The minimal current gate runs each backend once
and therefore does not claim a current FEM repeatability result.

MNI is not compared to the legacy direct-MNI E-field. The canonical MNI field
must be transformed from canonical native continuous E-field with the patient
forward normalization, contain valid finite nonzero signal, be deterministic
under repeated transformation, and produce all three binary VTAs by
thresholding the transformed MNI continuous field.

An equivalence pass also requires each input image to contain finite,
nonzero E-field signal and at least one suprathreshold voxel at every requested
threshold. Identical all-NaN, all-zero, or empty-VTA outputs are invalid and
cannot pass by numerical identity alone.

## Entry Point

```matlab
run_voltage_backend_equivalence( ...
    'StudyBase', '/path/to/study_base.json', ...
    'WorkRoot', '/path/to/validation');
```

The default selection is `SNr003`, `T1`, program `1`. The generated validation
directory contains manifests, case inventories, head-model hashes, comparison
tables, summaries, copied inputs, and backend outputs.

## Deterministic Current Acceptance

`run_current_backend_equivalence` is the current-controlled companion to
the historical voltage pilot. The two suites remain separate evidence: the
voltage suite reuses the existing SNr003 bilateral single-source outputs,
while the current suite generates one deterministic hypothetical right-sided
current program and compares the standard SimBio current path with
the unified canonical current path. A voltage pass is not treated as
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

The current FEM gate runs the standard `simbio` path once and the shared
canonical backend once, for exactly two FEM solves. It uses the same native
continuous E-field and 180/200/220 V/m gates listed above. Bilateral
single-voltage metrics are recomputed from existing paired outputs without new
voltage FEM. Multiple-cathode, electrode-return, repeatability, and vector
superposition remain solver-free unit fixtures; the vector fixture verifies
that neither scalar maximum nor scalar sum can replace signed vector
superposition.

The reference solve uses the standard Lead-DBS `simbio` current path. The
candidate solve uses the unified canonical backend in current mode and reuses
the same fixed native headmodel in the copied subject. The older registry
wrapper is not used for either canonical candidate.

Numerical comparison uses the standard `simbio` local E-field grid as the
fixed comparison grid. For a valid fresh acceptance run, the canonical raw
tetrahedral E-field is interpolated directly to the standard native reference
grid during candidate export; it must not first be reduced to the 0.7 mm
production native grid. MNI acceptance validates the canonical native-to-MNI
transformation and applies thresholds in MNI space without using legacy MNI as
the numerical reference. Re-comparison of existing NIfTI outputs starts no FEM, but it
cannot recover raw tetrahedral detail that was previously exported only on the
coarser production grid.

When candidate and reference dimensions and affine already match, alignment is
an identity operation. The comparison helper skips interpolation in that case
to preserve the original finite support at image boundaries. A current
acceptance candidate whose native dimensions or affine do not already match the
standard SimBio reference grid fails; the runner does not resample it into a
passing result.

The lightweight test entry point exercises fixture generation, safety guards,
inventory validation, and the independent vector-superposition fixture. The
existing synthetic NIfTI comparison test separately verifies the shared strict
E-field/VTA gates. Neither test invokes meshing or FEM:

```matlab
test_run_voltage_backend_equivalence;
r = testsuite('my_helper/vta/test/test_run_current_backend_equivalence.m');
assertSuccess(run(r));
```

The copied-subject FEM acceptance is deliberately separate and must be started
explicitly:

```matlab
run_current_backend_equivalence( ...
    'StudyBase', '/Volumes/VAL/STNSNr/summary/cohort/subj/study_base.json', ...
    'WorkRoot', '/Volumes/VAL/STNSNr/validation', ...
    'SubjectId', 'SNr003');
```

An existing current FEM pair can be compared again without copying a subject,
meshing, or solving:

```matlab
run_current_backend_equivalence( ...
    'Mode', 'compare_existing', ...
    'ExistingRunRoot', '/path/to/vta_single_current_backend_equivalence_RUN');
```

This mode requires the recorded single right-sided case and both backend
E-fields. It refreshes only the comparison CSV files and acceptance summary.
Existing versions of those untracked files are moved to the filesystem Trash
before replacement. The refreshed overall result also preserves the original
`production_subject_tree_unchanged` safety gate.

To validate a changed canonical backend while reusing the fixed standard
SimBio reference, use `Mode='rerun_candidate'`. This performs exactly one FEM
solve and records an explicit `RecoveryReason`; the default reason is
`canonical_backend_post_runtime_cache_validation`. The reason is provenance
only and does not alter the numerical gate.

Candidate recovery is self-contained in the frozen copied subject. It records
whether the production subject tree has changed since the original acceptance,
but historical drift does not block recovery. The mandatory safety gate is
that the production tree hash immediately before and after the recovery is
identical; recovery must not mutate the current production tree.

The recovery candidate executes through the production canonical task
validator and therefore writes first to the copied subject's canonical output
leaf. After successful publication, the complete native and MNI leaves are
copied to the acceptance run's `outputs/canonical/<case>/` index for comparison.
The harness never weakens canonical-path validation to accommodate acceptance
paths.

Recovery attempt count and completed FEM solve count are separate. A failure
before the canonical solve returns does not increment the completed solve
count. A missing candidate directory after an interrupted attempt is a
recoverable state: the next attempt rebuilds it from the frozen copied subject
and retained standard reference.

Historical voltage outputs can likewise be re-compared without FEM:

```matlab
run_voltage_backend_equivalence( ...
    'Mode', 'compare_existing', ...
    'ExistingRunRoot', '/path/to/vta_single_source_backend_equivalence_RUN');
```

This command remains an explicit maintenance action outside the lightweight
test suite.

## Frozen VTA Performance Baseline

`run_vta_performance_benchmark.py` validates and materializes the frozen
`vta_performance_benchmark_v1` fixture. Validation and preparation are
solver-free. The only mode that may start MATLAB is the explicit baseline
command:

```bash
/opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/vta/test/run_vta_performance_benchmark.py validate \
  --study-base /path/to/study_base.json \
  --vta-model /path/to/vta_model.yaml

/opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/vta/test/run_vta_performance_benchmark.py prepare \
  --study-base /path/to/study_base.json \
  --vta-model /path/to/vta_model.yaml \
  --work-root /path/to/copied-validation

/opt/anaconda3/envs/leaddbs/bin/python \
  my_helper/vta/test/run_vta_performance_benchmark.py run-baseline \
  --study-base /path/to/study_base.json \
  --vta-model /path/to/vta_model.yaml \
  --work-root /path/to/copied-validation
```

The baseline command always requests three workers from the VTA pipeline, but
each frozen case currently selects one subject. The first-slice report therefore
labels three-subject concurrency as unmeasured. Candidate binding remains
deferred until the persistent subject runner exists; five baseline repetitions
are recorded without synthetic pair positions. The frozen B/C schedule is
retained only as an unexecuted future contract.

Each preparation creates
`vta_performance_benchmark_<timestamp>/` below the copied validation root. It
contains the resolved fixture, `frozen_input/`, independent baseline and future
candidate working trees, per-run records under `runs/`, and
`benchmark_summary.json`. Existing untracked benchmark paths are moved to the
filesystem Trash instead of being overwritten. The harness rejects the
authoritative Lead-DBS derivatives root and every path below it.
Runtime process/solve/derived/copy/skip counts must be emitted by the executed
case; the harness never derives them from expected fixture ordering. Snapshot
manifests record selected and equivalent-donor artifact states, and every
restore verifies those states before execution.

## Accepted Evidence

The historical bilateral voltage outputs were refreshed without FEM at:

```text
/Volumes/VAL/STNSNr/validation/
  vta_single_source_backend_equivalence_20260712_214218_510
```

That run retains its original `Custom_Ewert_Zhang_Middlebrooks0.05` atlas
identity. The refresh passed and recorded zero comparison FEM solves.

The fresh current-controlled gate completed at:

```text
/Volumes/VAL/STNSNr/validation/
  vta_current_backend_equivalence_20260713_113545_719
```

It used `Custom_Ewert_Zhang_Middlebrooks`, executed exactly two FEM solves, and
passed. Native maximum absolute difference was `0.04443359375 V/m`, relative L2
error was `2.2273793323536e-6`, and correlation was
`0.999999999996588`. Dice was `1.0` at 180, 200, and 220 V/m. The MNI transform
contract passed and the production subject-tree hash was unchanged.

After process-local runtime caches were implemented, the canonical current
candidate was refreshed in the same frozen run on 2026-07-14. It reused the
standard SimBio reference and executed exactly one additional FEM solve. The
same native metrics and perfect three-threshold Dice passed, the MNI contract
passed, and the current production subject tree was unchanged during recovery.
The run now records three completed FEM solves in total and two recovery
attempts; the first recovery attempt stopped during task validation before FEM
and is not counted as a completed solve.
