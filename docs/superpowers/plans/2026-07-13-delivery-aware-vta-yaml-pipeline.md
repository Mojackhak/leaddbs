# Delivery-Aware VTA YAML Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a project-independent `vta-model` pipeline that reads canonical stimulation records from `study_base.json`, reads public FEM/output settings from `vta_model.yaml`, dispatches delivery-aware SimBio one-solve tasks, and writes deterministic native/MNI E-field and VTA artifacts under each Lead-DBS subject directory.

**Architecture:** A Python package validates inputs, resolves canonical stimulation records, creates a deterministic per-subject DAG, controls path-based reuse and force-to-Trash behavior, invokes MATLAB, and fills missing artifacts without overwriting existing files. A MATLAB adapter consumes one resolved task JSON at a time, builds a missing or reuses an existing canonical Lead-DBS head model, performs all production FEM calculations through `simbio_onesolve`, exports native common-grid E-fields, transforms continuous E-fields to MNI, and thresholds in each space. Existing STNSNr workbook adapters and legacy VTA entry points remain available but are not called by the new pipeline.

**Tech Stack:** Python 3 in Conda environment `leaddbs`, `argparse`, PyYAML, JSON Schema, pytest, MATLAB, Lead-DBS, SimBio, NIfTI, Git.

## Global Constraints

- Work on branch `stnvop`; do not push a remote branch.
- Before each implementation task, confirm `git status --short --branch` and do not modify code over unrelated uncommitted changes.
- Update the task's user-facing documentation before changing code.
- Code, identifiers, comments, docstrings, JSON keys, and YAML keys are English.
- `study_base.json` is the only project-data input; `vta_model.yaml` is the only public VTA-model input.
- `component_id`, source labels, STN/SNr, HF/ULF, and clinical endpoint roles do not control VTA task generation.
- Production FEM uses `simbio_onesolve` only. Backend selection, solve unit, mesh controls, tissue-surface controls, electrode removal, smoke settings, random seeds, and acceptance tolerances are not public YAML fields.
- `remove_electrode` remains the Lead-DBS internal default (`true`).
- `continuous` groups are solved jointly; `alternating` groups are solved once per source and derive a voxelwise maximum group E-field without duty-cycle or time averaging.
- A frequency group is homogeneous: every source is voltage-controlled or every source is current-controlled. Mixed groups are invalid.
- A continuous group cannot reuse the same electrode contact across sources. Case return may be shared.
- Native E-field is the authoritative FEM result. MNI E-field is transformed from native; MNI VTA is thresholded from transformed MNI E-field rather than warped from a binary native VTA.
- Public thresholds are `0.18`, `0.20`, and `0.22 V/mm`; NIfTI thresholding uses `180`, `200`, and `220 V/m`.
- Atlas name is exactly `Custom_Ewert_Zhang_Middlebrooks`.
- Do not write acceptance artifacts into the real subject tree. Use copied subjects below `/Volumes/VAL/STNSNr/validation`.
- Existing `/Volumes/VAL/STNSNr/derivatives/leaddbs/sub-*/stimulations` and `headmodel` directories have already been removed from the production tree; the new pipeline must rebuild all canonical head models and VTA outputs.
- Never permanently delete an untracked output. `--force` moves the previous leaf directory to the filesystem Trash before replacement.
- Recalculation is path based. Existing final artifacts are preserved; missing final artifacts are generated without provenance or hash checks.
- Reuse is resolved for complete same-subject `frequency_group` records. Runtime scans all groups represented by `study_base.json`, copies missing artifacts from an exactly equivalent existing donor, and computes only in selected paths when no donor exists. No phase or program value is recognized by implementation logic.
- The approved state-machine design is `docs/superpowers/specs/2026-07-13-path-based-vta-reuse-design.md`.

---

## Goal State Contract

The goal begins in this state:

```text
design_approved
path_only_runtime_implemented
python_and_matlab_unit_validated
representative_path_and_frequency_group_reuse_validated
fresh_continuous_and_current_fem_acceptance_pending
production_headmodels_absent
production_vta_outputs_absent
```

The current implementation scan of the example study base resolves 208 tasks
into 113 unique same-subject physical task records and 95 reusable tasks. These
counts are validation observations for that input file, not constants in the
planner. The generic implementation contains no branch keyed by those counts,
SNr003, or any T1/T2/T3 label.

The narrowed copied-subject run reused two existing continuous leaves, generated
two alternating source tasks plus one group-peak task, copied the physically
equivalent later group without MATLAB, and then skipped every completed path on
ordinary and `--resume` reruns. All 12 resulting E-fields were nonblank with
finite support and all 36 threshold outputs were binary across the two
equivalent phase paths. This is partial acceptance: a fresh continuous solve
and the separate current-control numerical comparison remain pending and are
not implied by the path/reuse result.

Progress is reported against these ordered milestones:

```text
1. public_contract_implemented
2. canonical_planner_implemented
3. voltage_current_backend_implemented
4. canonical_artifacts_implemented
5. copied_subject_acceptance_passed
6. production_rebuild_ready
```

The implementation goal is complete only when milestone 6 is documented and every item in the Final Acceptance Checklist passes. Production all-subject head-model/VTA execution is a separate operational goal and must not start as an implicit final step of this implementation plan.

## Artifact And Head-Model Contract

`$LEADDBS_SUBJECT_DIR` is read from each configured subject record. The generic
pipeline does not construct it from a project root or recognize a subject-name
pattern. The relative stimulation layout is:

```text
$LEADDBS_SUBJECT_DIR/stimulations/native/
  phase-$PHASE_ID/program-$PROGRAM_ID/electrode-$ELECTRODE_ID/frequency-group-$GROUP_ID/
    delivery-continuous/joint/
  phase-$PHASE_ID/program-$PROGRAM_ID/electrode-$ELECTRODE_ID/frequency-group-$GROUP_ID/
    delivery-alternating/sources/source-$SOURCE_ID/
    delivery-alternating/derived/group-peak/

$LEADDBS_SUBJECT_DIR/stimulations/MNI152NLin2009bAsym/
  phase-$PHASE_ID/program-$PROGRAM_ID/electrode-$ELECTRODE_ID/frequency-group-$GROUP_ID/
    delivery-continuous/joint/
  phase-$PHASE_ID/program-$PROGRAM_ID/electrode-$ELECTRODE_ID/frequency-group-$GROUP_ID/
    delivery-alternating/sources/source-$SOURCE_ID/
    delivery-alternating/derived/group-peak/
```

Every completed leaf contains exactly these scientific artifacts:

```text
efield.nii.gz
vta_threshold-0p18Vpermm.nii.gz
vta_threshold-0p20Vpermm.nii.gz
vta_threshold-0p22Vpermm.nii.gz
```

Canonical native head models use the existing Lead-DBS side convention and these exact paths:

```text
$LEADDBS_SUBJECT_DIR/headmodel/native/sub-SNr003_desc-headmodel1.mat  # right
$LEADDBS_SUBJECT_DIR/headmodel/native/sub-SNr003_desc-headmodel2.mat  # left
```

Head-model reuse is also path based. An existing canonical head-model MAT file is reused without provenance or implementation-hash comparison; a missing file is built. An existing unreadable or structurally invalid MAT file fails explicitly instead of being silently replaced.

## Locked File Structure

Create the Python package:

```text
my_helper/fiber/core/vta_pipeline/
  __init__.py
  errors.py
  records.py
  config.py
  study_base.py
  planner.py
  paths.py
  artifacts.py
  matlab_bridge.py
  service.py
  cli.py
  schemas/vta_model.schema.json
  tests/
    fixtures/study_base_minimal.json
    test_config.py
    test_study_base.py
    test_planner.py
    test_paths_and_artifacts.py
    test_matlab_bridge.py
    test_cli.py
```

Create the public command and project profile:

```text
my_helper/fiber/pipelines/vta-model
my_helper/stnsnr/config/vta_model.yaml
```

Create or modify the generic MATLAB layer:

```text
my_helper/fiber/core/stimulation/model/mh_vta_run_canonical_task.m
my_helper/fiber/core/stimulation/model/mh_vta_validate_canonical_task.m
my_helper/fiber/core/stimulation/model/mh_vta_prepare_canonical_headmodel.m
my_helper/fiber/core/stimulation/model/mh_vta_export_common_grid.m
my_helper/fiber/core/stimulation/model/mh_vta_transform_efield_to_mni.m
my_helper/fiber/core/stimulation/model/mh_vta_threshold_efield.m
my_helper/fiber/core/stimulation/model/mh_vta_compose_group_peak.m
my_helper/fiber/core/stimulation/model/fem/mh_vta_assemble_onesolve_boundary.m
my_helper/fiber/core/stimulation/model/backends/mh_vta_backend_simbio_onesolve.m
my_helper/fiber/core/stimulation/model/mh_vta_expand_delivery_group.m
```

Create or update tests and documentation:

```text
my_helper/fiber/tests/test_vta_canonical_task_contract.m
my_helper/fiber/tests/test_vta_onesolve_boundary_contract.m
my_helper/fiber/tests/test_vta_common_grid_export.m
my_helper/fiber/tests/test_vta_delivery_group_contract.m
my_helper/vta/test/run_single_current_backend_equivalence.m
my_helper/vta/test/test_run_single_current_backend_equivalence.m
my_helper/vta/test/README.md
my_helper/vta/README.md
```

Do not modify `study_base.json` or its importer in this implementation. The current `dual_frequency_study_v1` document is an input fixture, not a VTA-owned output.

### Task 1: Public Contract, YAML Profile, And Strict Schema

**Files:**
- Modify: `my_helper/vta/README.md`
- Create: `my_helper/stnsnr/config/vta_model.yaml`
- Create: `my_helper/fiber/core/vta_pipeline/__init__.py`
- Create: `my_helper/fiber/core/vta_pipeline/schemas/vta_model.schema.json`
- Create: `my_helper/fiber/core/vta_pipeline/config.py`
- Create: `my_helper/fiber/core/vta_pipeline/errors.py`
- Create: `my_helper/fiber/core/vta_pipeline/tests/test_config.py`

**Interfaces:**
- Produces: `VtaModelConfig`, `load_vta_model(path: Path) -> VtaModelConfig`, `ConfigError`.
- `VtaModelConfig.thresholds_v_per_m` returns the ordered unique tuple `(180.0, 200.0, 220.0)`.

- [ ] **Step 1: Document the public contract before code**

Add an English section to `my_helper/vta/README.md` containing this exact public profile and the statement that omitted execution/FEM controls use fixed Lead-DBS behavior:

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

- [ ] **Step 2: Write failing schema/config tests**

```python
def test_load_vta_model_converts_thresholds_to_v_per_m(tmp_path):
    path = write_profile(tmp_path, VALID_PROFILE)
    cfg = load_vta_model(path)
    assert cfg.atlas_set == "Custom_Ewert_Zhang_Middlebrooks"
    assert cfg.spaces == ("native", "MNI152NLin2009bAsym")
    assert cfg.thresholds_v_per_m == (180.0, 200.0, 220.0)


@pytest.mark.parametrize("forbidden", ["backend_policy", "solve_unit", "remove_electrode", "smoke"])
def test_schema_rejects_internal_fields(tmp_path, forbidden):
    profile = copy.deepcopy(VALID_PROFILE)
    profile[forbidden] = True
    with pytest.raises(ConfigError, match="Additional properties"):
        load_vta_model(write_profile(tmp_path, profile))
```

- [ ] **Step 3: Run the tests and confirm the expected failure**

Run:

```bash
conda run -n leaddbs python -m pytest my_helper/fiber/core/vta_pipeline/tests/test_config.py -q
```

Expected: collection fails because `vta_pipeline.config` does not exist.

- [ ] **Step 4: Implement the strict loader and immutable record**

Use a JSON Schema with `additionalProperties: false` at every object level. Implement:

```python
@dataclass(frozen=True)
class VtaModelConfig:
    gray_matter_s_per_m: float
    white_matter_s_per_m: float
    atlas_set: str
    spaces: tuple[str, ...]
    primary_threshold_v_per_mm: float
    sensitivity_thresholds_v_per_mm: tuple[float, ...]

    @property
    def thresholds_v_per_m(self) -> tuple[float, ...]:
        values = (*self.sensitivity_thresholds_v_per_mm, self.primary_threshold_v_per_mm)
        return tuple(sorted({value * 1000.0 for value in values}))


def load_vta_model(path: Path) -> VtaModelConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(_load_schema()).validate(raw)
    return _to_record(raw)
```

Validate finite positive conductivities, finite positive thresholds, exactly the two approved spaces, and the exact atlas string.

- [ ] **Step 5: Run tests and commit**

Run the Task 1 pytest command; expect all tests to pass. Then:

```bash
git add my_helper/vta/README.md my_helper/stnsnr/config/vta_model.yaml my_helper/fiber/core/vta_pipeline
git commit -m "feat: define strict VTA YAML contract"
```

### Task 2: Canonical Study-Base Adapter

**Files:**
- Create: `my_helper/fiber/core/vta_pipeline/records.py`
- Create: `my_helper/fiber/core/vta_pipeline/study_base.py`
- Create: `my_helper/fiber/core/vta_pipeline/tests/fixtures/study_base_minimal.json`
- Create: `my_helper/fiber/core/vta_pipeline/tests/test_study_base.py`
- Modify: `my_helper/vta/README.md`

**Interfaces:**
- Produces: `ContactRecord`, `SourceRecord`, `FrequencyGroupRecord`, `ElectrodeProgramRecord`, `SubjectRecord`, `StudyBase`, and `load_study_base(path: Path) -> StudyBase`.
- Contact records passed to MATLAB use side-local, one-based integer contacts or the string `case`.

- [ ] **Step 1: Document the consumed study-base fields**

Document that the adapter consumes `project.subjects[].subject_sources.leaddbs_subject_dir`, reconstruction path, contact numbering, electrodes, phases, programs, electrode programs, frequency groups, and source stimulation parameters. State explicitly that `component_id`, `source_label`, clinical observations, and HF/ULF roles are ignored by VTA execution.

- [ ] **Step 2: Write failing adapter tests**

```python
def test_right_contact_is_converted_to_side_local_one_based(minimal_study_path):
    study = load_study_base(minimal_study_path)
    source = study.subjects[0].programs[0].electrodes[1].groups[0].sources[0]
    assert source.contacts[0].contact == 1


def test_target_and_label_do_not_change_task_input(minimal_study_path):
    original = load_study_base(minimal_study_path)
    mutate_source_labels_and_components(minimal_study_path)
    changed = load_study_base(minimal_study_path)
    assert original.vta_semantic_payload() == changed.vta_semantic_payload()


def test_mixed_control_mode_group_is_rejected(minimal_study_path):
    make_group_mixed_voltage_and_current(minimal_study_path)
    with pytest.raises(StudyBaseError, match="homogeneous control_mode"):
        load_study_base(minimal_study_path)
```

- [ ] **Step 3: Run the tests and confirm failure**

Run:

```bash
conda run -n leaddbs python -m pytest my_helper/fiber/core/vta_pipeline/tests/test_study_base.py -q
```

Expected: failure because canonical records and loader are absent.

- [ ] **Step 4: Implement immutable canonical records and conversion**

```python
@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    frequency_hz: float
    control_mode: Literal["voltage", "current"]
    amplitude: float
    pulse_width_us: float
    contacts: tuple[ContactRecord, ...]


def to_side_local_contact(global_contact: int, electrode: ElectrodeRecord,
                          electrode_order: tuple[str, ...],
                          contact_counts: Mapping[str, int]) -> int:
    offset = sum(contact_counts[item] for item in electrode_order[:electrode_order.index(electrode.electrode_id)])
    local_zero_based = global_contact - offset
    if not 0 <= local_zero_based < electrode.contact_count:
        raise StudyBaseError("contact is outside the electrode range")
    return local_zero_based + 1
```

Validate safe path identifiers (`[A-Za-z0-9][A-Za-z0-9._-]*`), existing subject/reconstruction paths, finite positive frequency/amplitude/pulse width, nonempty sources, normalized polarity fractions per sign, homogeneous group control mode, and no duplicate non-case contact across sources in a continuous group. Do not impose the legacy four-source limit.

- [ ] **Step 5: Run tests and commit**

Run Task 2 pytest; expect pass. Then:

```bash
git add my_helper/vta/README.md my_helper/fiber/core/vta_pipeline
git commit -m "feat: add canonical stimulation adapter"
```

### Task 3: Deterministic Delivery-Aware Planner And Paths

**Files:**
- Create: `my_helper/fiber/core/vta_pipeline/planner.py`
- Create: `my_helper/fiber/core/vta_pipeline/paths.py`
- Create: `my_helper/fiber/core/vta_pipeline/tests/test_planner.py`
- Modify: `my_helper/vta/README.md`

**Interfaces:**
- Produces: `TaskKind`, `VtaTask`, `SubjectPlan`, `Selection`, `build_plan(study, model, selection) -> tuple[SubjectPlan, ...]`, and `leaf_directory(task, space) -> Path`.
- Solve kinds are `continuous_joint` and `alternating_source`; derived kind is `alternating_group_peak`.

- [ ] **Step 1: Document the DAG and leaf hierarchy**

Document the exact hierarchy from the approved design and state that every subject has one head-model prerequisite, each continuous group has one joint solve, and each alternating group has one solve per source followed by one group-peak derivation.

- [ ] **Step 2: Write failing planner tests**

```python
def test_continuous_group_creates_one_joint_task(study, model):
    plan = build_plan(study, model, Selection(subject_ids=("subject-A",)))
    tasks = tasks_for_group(plan, "group-continuous")
    assert [task.kind for task in tasks] == [TaskKind.CONTINUOUS_JOINT]


def test_alternating_group_creates_source_tasks_then_peak(study, model):
    tasks = tasks_for_group(build_plan(study, model, Selection(all_subjects=True)), "group-alternating")
    assert [task.kind for task in tasks] == [
        TaskKind.ALTERNATING_SOURCE,
        TaskKind.ALTERNATING_SOURCE,
        TaskKind.ALTERNATING_GROUP_PEAK,
    ]
    assert tasks[-1].dependencies == tuple(task.task_id for task in tasks[:-1])


def test_leaf_path_is_hierarchical_not_flat(study, model):
    task = first_alternating_source_task(build_plan(study, model, Selection(all_subjects=True)))
    assert leaf_directory(task, "native").parts[-8:] == (
        "native", "phase-phase-alpha", "program-program-a", "electrode-lead-R",
        "frequency-group-group-b", "delivery-alternating", "sources", "source-source-1",
    )


def test_reuse_equivalence_is_group_based_and_phase_agnostic(study, model):
    first, second = equivalent_groups_with_different_labels(study)
    assert normalized_group_record(first) == normalized_group_record(second)
    assert first.phase_id != second.phase_id


def test_target_component_and_phase_labels_do_not_change_group_equivalence(study, model):
    original, relabeled = physically_identical_relabeling(study)
    assert normalized_group_record(original) == normalized_group_record(relabeled)
```

- [ ] **Step 3: Run tests and confirm failure**

```bash
conda run -n leaddbs python -m pytest my_helper/fiber/core/vta_pipeline/tests/test_planner.py -q
```

Expected: planner symbols are missing.

- [ ] **Step 4: Implement deterministic task records and path generation**

```python
class TaskKind(str, Enum):
    CONTINUOUS_JOINT = "continuous_joint"
    ALTERNATING_SOURCE = "alternating_source"
    ALTERNATING_GROUP_PEAK = "alternating_group_peak"


@dataclass(frozen=True)
class VtaTask:
    task_id: str
    kind: TaskKind
    subject_id: str
    subject_dir: Path
    reconstruction_path: Path
    phase_id: str
    program_id: int
    electrode_id: str
    hemisphere: Literal["L", "R"]
    frequency_group_id: str
    delivery_mode: Literal["continuous", "alternating"]
    sources: tuple[SourceRecord, ...]
    dependencies: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return canonical_task_payload(self)
```

Sort subjects, phases, programs, electrodes, groups, and source IDs deterministically. Task IDs may remain deterministic SHA-256 identifiers, but hashes never determine output reuse or recalculation. Build a normalized immutable record for each complete frequency group after excluding phase/program/group/source identifiers, target/component metadata, and display labels. The normalized group contains hemisphere, reconstruction/electrode identity, delivery and control modes, and the complete normalized source multiset. Alternating source artifacts are matched by normalized source record; group-peak artifacts are reusable only when the complete normalized group records are equal. Filters reject unknown values and must never silently produce an empty plan. No literal phase, program, subject, target, or frequency-class value may affect planning behavior.

- [ ] **Step 5: Run tests and commit**

```bash
conda run -n leaddbs python -m pytest my_helper/fiber/core/vta_pipeline/tests/test_planner.py -q
git add my_helper/vta/README.md my_helper/fiber/core/vta_pipeline
git commit -m "feat: plan delivery-aware VTA tasks"
```

### Task 4: Path-Based Artifacts, Force, And Status

**Files:**
- Create: `my_helper/fiber/core/vta_pipeline/artifacts.py`
- Create: `my_helper/fiber/core/vta_pipeline/tests/test_paths_and_artifacts.py`
- Remove: `my_helper/fiber/core/vta_pipeline/provenance.py`
- Remove: `my_helper/fiber/core/vta_pipeline/tests/test_paths_and_provenance.py`
- Modify: `my_helper/vta/README.md`

**Interfaces:**
- Produces: `expected_artifacts(...)`, `leaf_status(...)`, `missing_artifacts(...)`, `atomic_copy_missing(...)`, and `move_leaf_to_trash(...)`.

- [ ] **Step 1: Document state semantics**

Document: final-path existence is the only persistent completion signal; a leaf is `complete` only when all four scientific artifacts exist and is otherwise `missing`; ordinary run and `--resume` fill only missing paths; `--force` moves selected leaves to Trash before using the same path-based state machine. No `provenance.json`, input hash, E-field hash, stale state, or persistent failed state is generated.

- [ ] **Step 2: Write failing path-state tests**

```python
def test_leaf_is_complete_only_when_all_expected_paths_exist(tmp_path):
    leaf = tmp_path / "leaf"
    write_expected_artifacts(leaf)
    assert leaf_status(leaf, THRESHOLDS) == "complete"
    (leaf / "vta_threshold-0p22Vpermm.nii.gz").unlink()
    assert leaf_status(leaf, THRESHOLDS) == "missing"


def test_atomic_copy_preserves_existing_destination(tmp_path):
    source = tmp_path / "source.nii.gz"
    destination = tmp_path / "leaf" / "efield.nii.gz"
    source.write_bytes(b"new")
    destination.parent.mkdir()
    destination.write_bytes(b"existing")
    assert atomic_copy_missing(source, destination) == "skipped_existing"
    assert destination.read_bytes() == b"existing"


def test_force_moves_existing_leaf_to_trash(tmp_path):
    leaf = tmp_path / "leaf"
    leaf.mkdir()
    (leaf / "old.txt").write_text("old")
    move_leaf_to_trash(leaf, trash_root=tmp_path / "Trash")
    assert not leaf.exists()
    assert list((tmp_path / "Trash").rglob("old.txt"))
```

- [ ] **Step 3: Run tests and confirm failure**

```bash
conda run -n leaddbs python -m pytest my_helper/fiber/core/vta_pipeline/tests/test_paths_and_artifacts.py -q
```

Expected: path-based artifact module is absent.

- [ ] **Step 4: Implement atomic path transitions**

Implement expected-path enumeration, complete/missing status, atomic temporary-copy promotion, and recoverable Trash moves. Existing final artifacts are immutable during ordinary execution. Failure removes or moves temporary files only and does not create a persistent failure marker.

- [ ] **Step 5: Run tests and commit**

```bash
conda run -n leaddbs python -m pytest my_helper/fiber/core/vta_pipeline/tests/test_paths_and_artifacts.py -q
git add my_helper/vta/README.md my_helper/fiber/core/vta_pipeline
git commit -m "feat: manage path-based VTA artifacts"
```

### Task 5: Read-Only CLI Surface

**Files:**
- Create: `my_helper/fiber/core/vta_pipeline/cli.py`
- Create: `my_helper/fiber/core/vta_pipeline/service.py`
- Create: `my_helper/fiber/core/vta_pipeline/tests/test_cli.py`
- Create: `my_helper/fiber/pipelines/vta-model`
- Modify: `my_helper/vta/README.md`

**Interfaces:**
- Produces: `main(argv: Sequence[str] | None = None) -> int` and executable `vta-model`.
- Public subcommands: `validate`, `plan`, `run`, `status`.

- [ ] **Step 1: Document exact command syntax**

```text
vta-model validate --study-base PATH --vta-model PATH (--subject ID ... | --all-subjects) [selectors]
vta-model plan     --study-base PATH --vta-model PATH (--subject ID ... | --all-subjects) [selectors]
vta-model run      --study-base PATH --vta-model PATH (--subject ID ... | --all-subjects) [selectors] [--workers N] [--resume | --force]
vta-model status   --study-base PATH --vta-model PATH (--subject ID ... | --all-subjects) [selectors]
```

Selectors are repeatable `--phase`, `--program`, `--electrode`, and `--frequency-group`. `--subject` and `--all-subjects` are mutually exclusive and one is required. `--workers` parallelizes subjects only.

- [ ] **Step 2: Write failing parser and read-only command tests**

```python
def test_subject_selection_is_required(capsys):
    assert main(["plan", "--study-base", STUDY, "--vta-model", MODEL]) == 2


def test_plan_is_deterministic_and_does_not_create_outputs(tmp_path, capsys):
    args = ["plan", "--study-base", STUDY, "--vta-model", MODEL, "--subject", "SNr003"]
    assert main(args) == 0
    first = capsys.readouterr().out
    assert main(args) == 0
    assert capsys.readouterr().out == first
    assert not list(tmp_path.rglob("stimulations"))


def test_resume_and_force_are_mutually_exclusive():
    assert main(RUN_ARGS + ["--resume", "--force"]) == 2
```

- [ ] **Step 3: Run tests and confirm failure**

```bash
conda run -n leaddbs python -m pytest my_helper/fiber/core/vta_pipeline/tests/test_cli.py -q
```

Expected: CLI module and executable are absent.

- [ ] **Step 4: Implement argparse and read-only services**

```python
def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except VtaPipelineError as exc:
        parser.error(str(exc))
        return 2
```

`validate` validates model, study base, selected records, reconstruction, preoperative anchor, normalization transform, and atlas availability. `plan` prints ordered task IDs and output paths. `status` prints one row per planned leaf with `missing` or `complete`, based only on the four expected artifact paths. The `run` handler must exist but return a clear `execution backend is not installed` error until Task 10 connects it.

- [ ] **Step 5: Run tests and commit**

```bash
conda run -n leaddbs python -m pytest my_helper/fiber/core/vta_pipeline/tests/test_cli.py -q
chmod +x my_helper/fiber/pipelines/vta-model
git add my_helper/vta/README.md my_helper/fiber/core/vta_pipeline my_helper/fiber/pipelines/vta-model
git commit -m "feat: add VTA model CLI"
```

### Task 6: MATLAB Canonical Task Contract And Delivery Expansion

**Files:**
- Create: `my_helper/fiber/core/stimulation/model/mh_vta_run_canonical_task.m`
- Create: `my_helper/fiber/core/stimulation/model/mh_vta_validate_canonical_task.m`
- Modify: `my_helper/fiber/core/stimulation/model/mh_vta_expand_delivery_group.m`
- Create: `my_helper/fiber/tests/test_vta_canonical_task_contract.m`
- Modify: `my_helper/fiber/tests/test_vta_delivery_group_contract.m`
- Modify: `my_helper/vta/README.md`

**Interfaces:**
- Produces: `status = mh_vta_run_canonical_task(taskJsonPath)` and `task = mh_vta_validate_canonical_task(task)`.
- Consumes the canonical task payload emitted by `VtaTask.to_payload()`.

- [ ] **Step 1: Document the MATLAB task JSON**

Document these required top-level fields: task ID, kind, subject/reconstruction paths, phase/program/electrode/group IDs, hemisphere, delivery mode, sources, conductivities, atlas, spaces, thresholds, output leaves, and missing-artifact instructions. State that backend, provenance hashes, and project labels are not part of the payload.

- [ ] **Step 2: Write failing MATLAB contract tests**

```matlab
function testContinuousSourcesRemainJoint(testCase)
task = fixture_task("continuous", [fixture_source("source-1"), fixture_source("source-2")]);
resolved = mh_vta_validate_canonical_task(task);
verifyEqual(testCase, string({resolved.solve_units{1}.source_id}), ["source-1", "source-2"]);
end

function testAlternatingSourcesRemainIndependent(testCase)
task = fixture_task("alternating", [fixture_source("source-1"), fixture_source("source-2")]);
resolved = mh_vta_validate_canonical_task(task);
ids = cellfun(@(unit) string(unit.source_id), resolved.solve_units);
verifyEqual(testCase, ids, ["source-1", "source-2"]);
end
```

- [ ] **Step 3: Run tests and confirm failure**

```bash
matlab -batch "addpath(genpath('/Users/mojackhu/Github/leaddbs')); r=testsuite('my_helper/fiber/tests/test_vta_canonical_task_contract.m'); assertSuccess(run(r));"
```

Expected: missing canonical task functions.

- [ ] **Step 4: Implement strict task validation and expansion**

```matlab
function task = mh_vta_validate_canonical_task(task)
mustBeMember(task.kind, ["continuous_joint", "alternating_source", "alternating_group_peak"]);
mustBeMember(task.delivery_mode, ["continuous", "alternating"]);
modes = unique(string({task.sources.control_mode}));
if numel(modes) ~= 1
    error('mh_vta:MixedControlMode', 'A frequency group must use one control mode.');
end
task.solve_units = mh_vta_expand_delivery_group(task.delivery_mode, task.sources);
end
```

Remove standard-`simbio` selection from the delivery expander. Continuous resolves to one joint source collection; alternating resolves to one collection per source. Keep legacy wrappers working by adapting their inputs before this new contract rather than adding project fields to the canonical task.

- [ ] **Step 5: Run tests and commit**

```bash
matlab -batch "addpath(genpath('/Users/mojackhu/Github/leaddbs')); r=testsuite('my_helper/fiber/tests/test_vta_canonical_task_contract.m'); r=[r testsuite('my_helper/fiber/tests/test_vta_delivery_group_contract.m')]; assertSuccess(run(r));"
git add my_helper/vta/README.md my_helper/fiber/core/stimulation/model my_helper/fiber/tests
git commit -m "feat: define canonical VTA task contract"
```

### Task 7: Voltage And Current One-Solve Boundary Assembly

**Files:**
- Create: `my_helper/fiber/core/stimulation/model/fem/mh_vta_assemble_onesolve_boundary.m`
- Modify: `my_helper/fiber/core/stimulation/model/backends/mh_vta_backend_simbio_onesolve.m`
- Create: `my_helper/fiber/tests/test_vta_onesolve_boundary_contract.m`
- Modify: `my_helper/vta/README.md`

**Interfaces:**
- Produces: `boundary = mh_vta_assemble_onesolve_boundary(sources, activeidx, controlMode)` with `node_indices`, `values_and_groups`, `unipolar`, `constvol`, and `source_groups`.
- Current values passed to `mh_vta_fem_apply_dbs` are amperes; voltage values are volts.

- [ ] **Step 1: Document control-mode math**

Document that each source's cathode and anode fractions are normalized within sign, voltage uses signed volts, current uses signed milliamperes converted by `1e-3`, case return sets the existing SimBio unipolar/current-return path, and electrode-return contacts remain explicit boundary groups.

- [ ] **Step 2: Write failing boundary tests**

```matlab
function testCurrentIsConvertedFromMilliampereToAmpere(testCase)
source = fixture_current_source(2.5, cathode=1, anode="case");
b = mh_vta_assemble_onesolve_boundary(source, fixture_activeidx(), "current");
verifyFalse(testCase, b.constvol);
verifyEqual(testCase, min(b.values_and_groups(:,1)), -2.5e-3, AbsTol=1e-12);
end

function testMultipolarCurrentKeepsSignedFractions(testCase)
source = fixture_multipolar_current_source(4.0, [0.25 0.75], [0.4 0.6]);
b = mh_vta_assemble_onesolve_boundary(source, fixture_activeidx(), "current");
verifyEqual(testCase, sort(unique(b.values_and_groups(:,1))), ...
    sort([-3e-3 -1e-3 1.6e-3 2.4e-3])', AbsTol=1e-12);
end
```

- [ ] **Step 3: Run tests and confirm failure**

```bash
matlab -batch "addpath(genpath('/Users/mojackhu/Github/leaddbs')); r=testsuite('my_helper/fiber/tests/test_vta_onesolve_boundary_contract.m'); assertSuccess(run(r));"
```

Expected: boundary assembler is missing and the backend still rejects current mode.

- [ ] **Step 4: Implement the assembler and refactor one-solve**

```matlab
scale = 1;
constvol = controlMode == "voltage";
if controlMode == "current"
    scale = 1e-3;
end
signedValue = source.amplitude * scale * contact.fraction;
if contact.polarity == "cathode"
    signedValue = -signedValue;
end
```

Assign a deterministic group index per source/contact boundary, concatenate node indices, reject conflicting contact reuse, and call:

```matlab
potential = mh_vta_fem_apply_dbs(vol, boundary.node_indices, ...
    boundary.values_and_groups, boundary.unipolar, boundary.constvol, wmboundary);
```

Delete the fixed `for source = 1:4` extraction path from canonical execution. Legacy `S` remains available only for Lead-DBS geometry/head-model helpers.

- [ ] **Step 5: Run tests and commit**

```bash
matlab -batch "addpath(genpath('/Users/mojackhu/Github/leaddbs')); r=testsuite('my_helper/fiber/tests/test_vta_onesolve_boundary_contract.m'); assertSuccess(run(r));"
git add my_helper/vta/README.md my_helper/fiber/core/stimulation/model my_helper/fiber/tests
git commit -m "feat: support current one-solve boundaries"
```

### Task 8: Canonical Head Model, Native Common Grid, MNI Transform, And Thresholding

**Files:**
- Create: `my_helper/fiber/core/stimulation/model/mh_vta_prepare_canonical_headmodel.m`
- Create: `my_helper/fiber/core/stimulation/model/mh_vta_export_common_grid.m`
- Create: `my_helper/fiber/core/stimulation/model/mh_vta_transform_efield_to_mni.m`
- Create: `my_helper/fiber/core/stimulation/model/mh_vta_threshold_efield.m`
- Modify: `my_helper/fiber/core/stimulation/model/backends/mh_vta_backend_simbio_onesolve.m`
- Create: `my_helper/fiber/tests/test_vta_common_grid_export.m`
- Modify: `my_helper/vta/README.md`

**Interfaces:**
- Produces one canonical head model per subject/hemisphere under `$LEADDBS_SUBJECT_DIR/headmodel/native/` and fixed-grid continuous NIfTI files.
- `mh_vta_threshold_efield(efieldPath, thresholdVPerM, outputPath)` writes `uint8` binary data with `1` for `E >= threshold` and `0` otherwise.

- [ ] **Step 1: Document authoritative-space ordering**

Document the exact sequence: rebuild/reuse canonical native head model, solve native FEM, sample continuous E-field onto the preoperative anchor geometry, threshold native E-field, transform continuous E-field using the subject normalization, then threshold transformed MNI E-field.

- [ ] **Step 2: Write failing fixed-grid tests**

```matlab
function testThresholdUsesIndicatorFunction(testCase)
input = write_test_nifti(single([179 180 220 221]));
output = tempname + ".nii";
mh_vta_threshold_efield(input, 180, output);
nii = ea_load_nii(output);
verifyEqual(testCase, uint8(nii.img), uint8([0 1 1 1]));
end

function testExportMatchesAnchorGeometry(testCase)
[meshPoints, field, anchor] = fixture_mesh_and_anchor();
output = tempname + ".nii";
mh_vta_export_common_grid(meshPoints, field, anchor, output);
verifyEqual(testCase, ea_load_nii(output).mat, ea_load_nii(anchor).mat, AbsTol=1e-12);
verifyEqual(testCase, size(ea_load_nii(output).img), size(ea_load_nii(anchor).img));
end
```

- [ ] **Step 3: Run tests and confirm failure**

```bash
matlab -batch "addpath(genpath('/Users/mojackhu/Github/leaddbs')); r=testsuite('my_helper/fiber/tests/test_vta_common_grid_export.m'); assertSuccess(run(r));"
```

Expected: common-grid and threshold helpers are missing.

- [ ] **Step 4: Implement canonical output generation**

Use the preoperative anchor NIfTI as the native reference geometry. Use the existing Lead-DBS normalization transform for continuous interpolation into `MNI152NLin2009bAsym`; pass the canonical MNI T1 reference explicitly. Do not call `ea_write_vta_nii` for canonical artifacts because its dynamic local extent is not the approved common grid.

```matlab
thresholds = double(task.thresholds_v_per_m);
for threshold = thresholds
    name = sprintf('vta_threshold-%sVpermm.nii.gz', threshold_token(threshold / 1000));
    mh_vta_threshold_efield(nativeEfield, threshold, fullfile(nativeLeaf, name));
    mh_vta_threshold_efield(mniEfield, threshold, fullfile(mniLeaf, name));
end
```

Build a missing head model in `$LEADDBS_SUBJECT_DIR/headmodel/native/`. If the canonical head-model path exists, reuse it without provenance or hash comparison. Loading an existing unreadable or structurally invalid MAT file fails explicitly and does not silently replace it. `--force` applies only to selected stimulation leaves; rebuilding a head model requires the operator to move its canonical file out of the way.

- [ ] **Step 5: Run tests and commit**

```bash
matlab -batch "addpath(genpath('/Users/mojackhu/Github/leaddbs')); r=testsuite('my_helper/fiber/tests/test_vta_common_grid_export.m'); assertSuccess(run(r));"
git add my_helper/vta/README.md my_helper/fiber/core/stimulation/model my_helper/fiber/tests
git commit -m "feat: export canonical VTA grids"
```

### Task 9: Alternating Group-Peak Derivation

**Files:**
- Create: `my_helper/fiber/core/stimulation/model/mh_vta_compose_group_peak.m`
- Modify: `my_helper/fiber/core/stimulation/model/mh_vta_run_canonical_task.m`
- Modify: `my_helper/fiber/tests/test_vta_canonical_task_contract.m`
- Modify: `my_helper/vta/README.md`

**Interfaces:**
- Produces native and MNI `group-peak` leaves from completed alternating source leaves.
- Native peak is `max_s E_s(v)` on identical native grids; MNI peak is transformed from native peak and thresholded in MNI.

- [ ] **Step 1: Document group-peak semantics**

Document:

```text
E_group_peak_native(v) = max_s E_s_native(v)
group_vta_tau(v) = 1 when E_group_peak(v) >= tau, otherwise 0
```

State that source-level NIfTI files remain unchanged and no temporal weighting is produced.

- [ ] **Step 2: Write failing derivation tests**

```matlab
function testPeakUsesVoxelwiseMaximum(testCase)
left = write_test_nifti(single([10 30 20]));
right = write_test_nifti(single([20 15 40]));
output = tempname + ".nii";
mh_vta_compose_group_peak([left right], output);
verifyEqual(testCase, ea_load_nii(output).img, single([20 30 40]));
end

function testPeakRejectsGridMismatch(testCase)
verifyError(testCase, @() mh_vta_compose_group_peak(mismatched_niftis(), tempname), ...
    'mh_vta:GridMismatch');
end
```

- [ ] **Step 3: Run tests and confirm failure**

Run the canonical task MATLAB test file; expect missing `mh_vta_compose_group_peak`.

- [ ] **Step 4: Implement peak, transform, and threshold sequence**

```matlab
peak = -inf(referenceSize, 'single');
for path = sourceEfields
    nii = ea_load_nii(path);
    assert_same_grid(referenceNii, nii);
    peak = max(peak, single(nii.img));
end
write_like_reference(referenceNii, peak, nativePeakPath);
```

Threshold native peak, transform native continuous peak once, and threshold the MNI peak. Do not recompute a FEM solve for the derived task.

- [ ] **Step 5: Run tests and commit**

```bash
matlab -batch "addpath(genpath('/Users/mojackhu/Github/leaddbs')); r=testsuite('my_helper/fiber/tests/test_vta_canonical_task_contract.m'); assertSuccess(run(r));"
git add my_helper/vta/README.md my_helper/fiber/core/stimulation/model my_helper/fiber/tests
git commit -m "feat: derive alternating group peak VTA"
```

### Task 10: Python-To-MATLAB Execution And Subject-Level Parallelism

**Files:**
- Create: `my_helper/fiber/core/vta_pipeline/matlab_bridge.py`
- Modify: `my_helper/fiber/core/vta_pipeline/service.py`
- Modify: `my_helper/fiber/core/vta_pipeline/cli.py`
- Create: `my_helper/fiber/core/vta_pipeline/tests/test_matlab_bridge.py`
- Modify: `my_helper/fiber/core/vta_pipeline/tests/test_cli.py`
- Modify: `my_helper/fiber/core/stimulation/model/mh_vta_launch_process_workers.m`
- Create: `my_helper/fiber/core/vta_pipeline/tests/test_no_project_hardcoding.py`
- Modify: `my_helper/vta/README.md`

**Interfaces:**
- Produces: `MatlabBridge.run_task(task, context) -> None` and `RunService.run(plan, workers, resume, force) -> RunSummary` with `generated`, `copied`, `skipped_existing`, `failed`, and `skipped_dependency` counts.

- [ ] **Step 1: Document execution and failure policy**

Document that tasks within one subject are sequential, subjects may run concurrently, a failed task skips only its dependency descendants, independent tasks for the same subject continue, and the final CLI exit code is nonzero if any selected task fails. For each selected group, runtime scans all same-subject frequency groups represented by `study_base.json` for exactly equivalent existing artifacts. Donor failure skips only selected recipients that still depend on that donor; complete donors atomically copy only missing artifacts.

- [ ] **Step 2: Write failing bridge/executor tests**

```python
def test_bridge_writes_canonical_json_and_invokes_one_entrypoint(tmp_path, fake_runner):
    bridge = MatlabBridge(repo_root=REPO, runner=fake_runner)
    bridge.run_task(TASK, CONTEXT)
    payload = json.loads(fake_runner.task_json.read_text())
    assert payload["task_id"] == TASK.task_id
    assert "backend" not in payload
    assert "component_id" not in json.dumps(payload)
    assert "mh_vta_run_canonical_task" in fake_runner.command


def test_workers_never_overlap_tasks_from_same_subject(fake_bridge):
    summary = RunService(fake_bridge).run(TWO_SUBJECT_PLAN, workers=3, resume=False, force=False)
    assert summary.failed == 0
    assert fake_bridge.maximum_inflight_per_subject == 1
    assert fake_bridge.maximum_subjects_inflight == 2


def test_failed_task_does_not_stop_independent_sibling(fake_bridge):
    summary = RunService(fake_bridge).run(PLAN_WITH_FAILED_OWNER_AND_SIBLING, workers=1)
    assert summary.failed == 1
    assert summary.skipped_dependency == 1
    assert summary.generated == 1


def test_generic_production_modules_contain_no_project_control_literals():
    assert forbidden_control_literals_in_generic_modules() == []
```

- [ ] **Step 3: Run tests and confirm failure**

```bash
conda run -n leaddbs python -m pytest my_helper/fiber/core/vta_pipeline/tests/test_matlab_bridge.py my_helper/fiber/core/vta_pipeline/tests/test_cli.py -q
```

Expected: execution bridge is absent and `run` still reports unavailable.

- [ ] **Step 4: Implement the bridge and executor**

```python
command = [
    matlab_executable,
    "-batch",
    f"addpath(genpath('{matlab_quote(repo_root)}')); "
    f"mh_vta_run_canonical_task('{matlab_quote(task_json)}');",
]
subprocess.run(command, check=True, text=True, capture_output=False)
```

Serialize task JSON atomically in the task working directory. Use one `ThreadPoolExecutor(max_workers=workers)` future per subject and run that subject's topological task list in one worker. Before MATLAB invocation, determine which native/MNI artifacts are missing. For each missing artifact, scan deterministic same-subject equivalent-group paths and copy the first existing match. Pass only still-missing generation instructions to MATLAB. If multiple equivalent selected groups remain missing, generate the first selected group and use it as the in-run donor without writing to any unselected path. Track task outcomes in memory so only dependency descendants are skipped. Default workers to `1`; require a positive integer. Remove the legacy `STNSNR_VTA_SUBJECT_IDS` project-named environment-variable dependency from canonical execution. Generic production modules cannot branch on concrete subject, phase, program, target, study, HF/ULF, chronic, or immediate literals; fixture-only tests and acceptance scripts are explicitly outside this static production-module check.

- [ ] **Step 5: Run Python tests and commit**

```bash
conda run -n leaddbs python -m pytest my_helper/fiber/core/vta_pipeline/tests -q
git add my_helper/vta/README.md my_helper/fiber/core/vta_pipeline my_helper/fiber/pipelines/vta-model
git commit -m "feat: execute VTA tasks by subject"
```

### Task 11: Voltage And Current Numerical Acceptance

**Files:**
- Modify: `my_helper/vta/test/README.md`
- Create: `my_helper/vta/test/run_single_current_backend_equivalence.m`
- Create: `my_helper/vta/test/test_run_single_current_backend_equivalence.m`
- Modify: `my_helper/vta/test/run_single_source_backend_equivalence.m`
- Modify: `my_helper/vta/test/test_run_single_source_backend_equivalence.m`

**Interfaces:**
- Produces repeatable copied-subject acceptance artifacts below `/Volumes/VAL/STNSNr/validation`.
- Does not write `/Volumes/VAL/STNSNr/derivatives/leaddbs/sub-SNr003`.

- [ ] **Step 1: Document historical and new evidence separately**

Record the existing SNr003 bilateral single-voltage `simbio` versus `simbio_onesolve` pilot as historical evidence. Define the new deterministic current suite with RNG seed `20260712`, atlas `Custom_Ewert_Zhang_Middlebrooks`, amplitudes `0.5-5.0 mA`, pulse widths `30-120 us`, both hemispheres, case-return and electrode-return configurations.

- [ ] **Step 2: Write failing fixture-generation and safety tests**

```matlab
function testGeneratedCurrentCasesAreDeterministic(testCase)
a = generate_cases(20260712);
b = generate_cases(20260712);
verifyEqual(testCase, a, b);
verifyTrue(testCase, any([a.has_case_return]));
verifyTrue(testCase, any([a.has_electrode_return]));
verifyTrue(testCase, all([a.amplitude_mA] >= 0.5 & [a.amplitude_mA] <= 5.0));
end

function testWorkRootCannotBeProductionSubjectTree(testCase)
verifyError(testCase, @() run_single_current_backend_equivalence( ...
    'WorkRoot','/Volumes/VAL/STNSNr/derivatives/leaddbs'), ...
    'mh_vta_acceptance:UnsafeWorkRoot');
end
```

- [ ] **Step 3: Run lightweight tests and confirm failure**

```bash
matlab -batch "addpath(genpath('/Users/mojackhu/Github/leaddbs')); r=testsuite('my_helper/vta/test/test_run_single_current_backend_equivalence.m'); assertSuccess(run(r));"
```

Expected: current acceptance functions are missing.

- [ ] **Step 4: Implement the deterministic copied-subject suite**

Generate: one cathode plus case return; multiple cathodes plus case with random normalized fractions; and electrode return with separately normalized random cathode/anode fractions. Compare standard SimBio current as reference against new one-solve current for native and MNI continuous E-field plus all three thresholds. Repeat at least one case for each path.

Use these exact gates independently for every case and hemisphere:

```text
repeat E-field: voxelwise exact
repeat binary VTA: voxelwise exact
maximum absolute E-field difference <= 1e-3 V/m
relative L2 error <= 1e-5
Pearson correlation >= 0.999999
VTA Dice >= 0.999
relative VTA volume difference <= 0.1%
```

Add an independent multi-current RHS/vector-field superposition fixture that verifies signed linear superposition and explicitly rejects scalar maximum or scalar sum of field magnitudes.

- [ ] **Step 5: Run lightweight tests, then real acceptance**

First run the Task 11 test command. Then run:

```bash
matlab -batch "addpath(genpath('/Users/mojackhu/Github/leaddbs')); run_single_current_backend_equivalence('StudyBase','/Volumes/VAL/STNSNr/summary/cohort/subj/study_base.json','WorkRoot','/Volumes/VAL/STNSNr/validation','SubjectId','SNr003');"
```

Expected: all bilateral voltage/current gates pass and the production subject tree path/size inventory is unchanged.

- [ ] **Step 6: Commit acceptance code and documentation**

```bash
git add my_helper/vta/test
git commit -m "test: validate voltage and current one-solve FEM"
```

### Task 12: Copied-Subject End-To-End Gate And Production Rebuild Readiness

**Files:**
- Modify: `my_helper/fiber/core/vta_pipeline/tests/test_cli.py`
- Create: `my_helper/vta/test/prepare_copied_vta_validation.py`
- Create: `my_helper/vta/test/test_prepare_copied_vta_validation.py`
- Modify: `my_helper/vta/README.md`
- Modify: `docs/superpowers/specs/2026-07-12-vta-model-yaml-delivery-aware-design.md`

**Interfaces:**
- Representative acceptance of `validate`, `plan`, `run`, `status`, path-only skip/repair, force-to-Trash, same-subject frequency-group reuse, head-model reuse, and voltage/current execution for copied SNr003.
- The acceptance run must not execute all 20 SNr003 tasks.

- [ ] **Step 1: Update documentation status before the end-to-end run**

Keep the implementation-status table at `migration_in_progress` until the
path-only state machine and representative end-to-end gate both pass. Preserve
the narrower `unit_validated` and historical `fem_validated` evidence labels,
and keep `production_rebuild_not_started`. Do not describe the migration or
production rebuild as complete.

- [ ] **Step 2: Run all static/unit suites**

```bash
conda run -n leaddbs python -m pytest my_helper/fiber/core/vta_pipeline/tests -q
matlab -batch "addpath(genpath('/Users/mojackhu/Github/leaddbs')); files={'test_vta_canonical_task_contract.m','test_vta_onesolve_boundary_contract.m','test_vta_common_grid_export.m','test_vta_delivery_group_contract.m'}; r=matlab.unittest.Test.empty; for i=1:numel(files), r=[r testsuite(fullfile('my_helper','fiber','tests',files{i}))]; end; assertSuccess(run(r));"
git diff --check
```

Expected: all suites pass and no whitespace errors are reported.

- [ ] **Step 3: Write and test the copied-subject preparation helper**

Implement this exact public interface:

```python
def prepare_validation_copy(
    study_base_path: Path,
    subject_id: str,
    work_root: Path,
    run_id: str,
) -> Path:
    """Return the rewritten validation study-base path."""
```

The helper creates `$WORK_ROOT/vta_pipeline_e2e_$RUN_ID`, copies only the selected Lead-DBS subject directory, rewrites that subject's `leaddbs_subject_dir` and reconstruction path in a study-base copy, removes all other subjects, and refuses a work root within `/Volumes/VAL/STNSNr/derivatives/leaddbs`.

Its executable block parses `--study-base`, `--subject`, `--work-root`, and `--run-id`, calls `prepare_validation_copy`, and prints only the absolute output study-base path to stdout so shell command substitution is deterministic.

```python
def test_prepare_validation_copy_never_points_to_production(tmp_path):
    output = prepare_validation_copy(STUDY, "SNr003", tmp_path, "test-run")
    raw = json.loads(output.read_text())
    subject = raw["project"]["subjects"][0]
    assert subject["subject_id"] == "SNr003"
    assert str(tmp_path) in subject["subject_sources"]["leaddbs_subject_dir"]
    assert "/derivatives/leaddbs/sub-SNr003" not in str(output.parent)
```

Run:

```bash
conda run -n leaddbs python -m pytest my_helper/vta/test/test_prepare_copied_vta_validation.py -q
```

Expected: pass after implementation.

- [ ] **Step 4: Create a copied SNr003 study base and execute representative tasks**

Run:

```bash
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
VALIDATION_STUDY="$(conda run -n leaddbs python my_helper/vta/test/prepare_copied_vta_validation.py --study-base /Volumes/VAL/STNSNr/summary/cohort/subj/study_base.json --subject SNr003 --work-root /Volumes/VAL/STNSNr/validation --run-id "$RUN_ID")"
conda run -n leaddbs my_helper/fiber/pipelines/vta-model validate --study-base "$VALIDATION_STUDY" --vta-model my_helper/stnsnr/config/vta_model.yaml --subject SNr003
conda run -n leaddbs my_helper/fiber/pipelines/vta-model run --study-base "$VALIDATION_STUDY" --vta-model my_helper/stnsnr/config/vta_model.yaml --subject SNr003 --phase T1 --program 1 --workers 1
conda run -n leaddbs my_helper/fiber/pipelines/vta-model run --study-base "$VALIDATION_STUDY" --vta-model my_helper/stnsnr/config/vta_model.yaml --subject SNr003 --phase T2 --program 2 --electrode lead-L --workers 1
conda run -n leaddbs my_helper/fiber/pipelines/vta-model run --study-base "$VALIDATION_STUDY" --vta-model my_helper/stnsnr/config/vta_model.yaml --subject SNr003 --phase T3 --program 2 --electrode lead-L --workers 1
conda run -n leaddbs my_helper/fiber/pipelines/vta-model status --study-base "$VALIDATION_STUDY" --vta-model my_helper/stnsnr/config/vta_model.yaml --subject SNr003
```

The representative commands execute exactly two continuous joint tasks and the
two alternating source solves plus group-peak derivation for one hemisphere.
In this fixture only, T2 and T3 contain physically identical frequency groups,
so the later command must reuse the existing same-subject group artifacts and
perform no additional physical solve or derivation. T2/T3 values are acceptance
data, not implementation branches. The current-control numerical suite remains
a separate deterministic acceptance command. Expected: every selected
native/MNI leaf reports `complete` and contains one E-field plus three VTA
files; no `provenance.json` is created.

- [ ] **Step 5: Verify path-only repair, alias copy, and force semantics**

Run the representative command again with and without `--resume`; expect zero FEM invocations because every expected path exists. Remove one copied-subject threshold by moving it to Trash, rerun, and expect only that missing threshold to be recreated from an existing equivalent-group artifact or the selected group's existing E-field. Verify with synthetic arbitrary phase/program labels that same-subject equivalent groups copy missing artifacts, while equal groups in different subjects do not. Run one filtered stimulation leaf with `--force`; expect the old leaf in Trash and regenerated artifacts while the existing head model remains untouched. Confirm no production subject path changed.

- [ ] **Step 6: Validate production rebuild plan without running it**

```bash
conda run -n leaddbs my_helper/fiber/pipelines/vta-model plan --study-base /Volumes/VAL/STNSNr/summary/cohort/subj/study_base.json --vta-model my_helper/stnsnr/config/vta_model.yaml --all-subjects
```

Expected: 16 subjects are selected; each required hemisphere reports
`reuse_existing` when its canonical head-model path exists or `build_required`
when it does not; and no output is created. Production execution requires a
separate explicit user instruction after this plan is implemented and
accepted.

- [ ] **Step 7: Final documentation commit**

```bash
git add my_helper/vta/README.md my_helper/vta/test/prepare_copied_vta_validation.py my_helper/vta/test/test_prepare_copied_vta_validation.py docs/superpowers/specs/2026-07-12-vta-model-yaml-delivery-aware-design.md my_helper/fiber/core/vta_pipeline/tests/test_cli.py
git commit -m "docs: record VTA pipeline acceptance"
```

## Final Acceptance Checklist

- [ ] Public YAML contains only the approved conductivities, atlas, spaces, and VTA thresholds.
- [ ] Changing target/component, phase, program, or subject display labels does not alter normalized physical-group equality.
- [ ] Continuous groups use one joint `simbio_onesolve` task.
- [ ] Alternating groups use independent `simbio_onesolve` source tasks and a derived maximum E-field.
- [ ] Voltage and current groups pass strict unit and numerical gates.
- [ ] No legacy four-source cap affects canonical input.
- [ ] Native E-field uses the preoperative common grid.
- [ ] MNI E-field is transformed from native continuous E-field.
- [ ] All binary VTAs are thresholded in their own space at 180/200/220 V/m.
- [ ] Artifact hierarchy is deterministic and hierarchical.
- [ ] Leaves contain only one E-field and three threshold artifacts; no `provenance.json` is generated.
- [ ] `--workers` parallelizes subjects only.
- [ ] Ordinary run and `--resume` preserve existing paths and fill only missing artifacts.
- [ ] Same-subject equivalent frequency groups reuse existing artifacts without hashes; no phase/program/subject literal controls behavior.
- [ ] A failed task skips only dependency descendants; independent tasks continue.
- [ ] Force uses Trash and does not implicitly rebuild an existing head model.
- [ ] Representative copied SNr003 acceptance passes without running all 20 tasks or modifying production subjects.
- [ ] Production all-subject planning selects 16 subjects and performs no writes.
- [ ] Production rebuild remains unstarted until separately authorized.
