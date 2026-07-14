from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path

import pytest

from my_helper.fiber.core.vta_pipeline.config import load_vta_model
from my_helper.fiber.core.vta_pipeline.errors import SubjectManifestError
from my_helper.fiber.core.vta_pipeline.planner import (
    Selection,
    SubjectPlan,
    TaskKind,
    build_plan,
)
from my_helper.fiber.core.vta_pipeline.study_base import load_study_base
from my_helper.fiber.core.vta_pipeline.subject_manifest import (
    SCHEMA_VERSION,
    build_subject_manifest,
    validate_subject_manifest,
    write_subject_manifest,
)


REPO_ROOT = Path(__file__).resolve().parents[5]
FIXTURE = Path(__file__).with_name("fixtures") / "study_base_minimal.json"
MODEL_PATH = REPO_ROOT / "my_helper" / "stnsnr" / "config" / "vta_model.yaml"
RUN_ID = "20260714T120000Z"


@pytest.fixture
def study_path(tmp_path: Path) -> Path:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    subject_dir = tmp_path / "subject"
    reconstruction = (
        subject_dir / "reconstruction" / "sub-SNr003_desc-reconstruction.mat"
    )
    reconstruction.parent.mkdir(parents=True)
    reconstruction.write_bytes(b"fixture")
    path = tmp_path / "study_base.json"
    path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    return path


def make_plan(study_path: Path, selection: Selection | None = None) -> SubjectPlan:
    return build_plan(
        load_study_base(study_path),
        load_vta_model(MODEL_PATH),
        selection or Selection(subject_ids=("SNr003",)),
    )[0]


def add_equivalent_phase(study_path: Path, *, changed_amplitude: bool = False) -> None:
    raw = json.loads(study_path.read_text(encoding="utf-8"))
    subject = raw["study"]["subjects"][0]
    phase = deepcopy(subject["phases"][0])
    phase["phase_id"] = "followup"
    phase["phase_label"] = "Follow-up"
    program = phase["programs"][0]
    program["program_id"] = 77
    program["program_label"] = "Follow-up program"
    for electrode in program["electrode_programs"]:
        for group_index, group in enumerate(electrode["frequency_groups"]):
            group["frequency_group_id"] = f"followup-group-{group_index}"
            for source_index, source in enumerate(group["sources"]):
                source["source_id"] = f"followup-source-{source_index}"
    if changed_amplitude:
        program["electrode_programs"][0]["frequency_groups"][0]["sources"][0][
            "amplitude"
        ] += 0.25
    subject["phases"].append(phase)
    study_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")


def select_first_task(plan: SubjectPlan) -> SubjectPlan:
    task = plan.tasks[0]
    return replace(plan, tasks=(task,), reuse_candidates=plan.reuse_candidates)


def test_payload_is_deterministic_and_preserves_selected_task_order(
    study_path: Path,
) -> None:
    plan = make_plan(study_path)

    first = build_subject_manifest(plan, RUN_ID)
    second = build_subject_manifest(plan, RUN_ID)

    assert first == second
    assert first["schema_version"] == SCHEMA_VERSION
    assert [entry["task"]["task_id"] for entry in first["tasks"]] == [
        task.task_id for task in plan.tasks
    ]


def test_task_ids_beginning_with_digits_remain_array_values(
    study_path: Path,
) -> None:
    plan = select_first_task(make_plan(study_path))
    task = replace(plan.tasks[0], task_id="1digit-prefixed-task")
    plan = replace(plan, tasks=(task,), reuse_candidates=(task,))

    payload = build_subject_manifest(plan, RUN_ID)

    assert isinstance(payload["tasks"], list)
    assert payload["tasks"][0]["task"]["task_id"] == "1digit-prefixed-task"
    assert "1digit-prefixed-task" not in payload


def test_catalog_contains_selected_and_unselected_donors_in_planner_order(
    study_path: Path,
) -> None:
    add_equivalent_phase(study_path)
    plan = make_plan(
        study_path,
        Selection(subject_ids=("SNr003",), phase_ids=("T1",)),
    )

    payload = build_subject_manifest(plan, RUN_ID)

    assert [entry["donor_id"] for entry in payload["reuse_donors"]] == [
        task.task_id for task in plan.reuse_candidates
    ]
    assert {task.task_id for task in plan.tasks}.issubset(
        {entry["donor_id"] for entry in payload["reuse_donors"]}
    )
    assert len(payload["reuse_donors"]) > len(payload["tasks"])
    first_task = plan.tasks[0]
    first_entry = payload["tasks"][0]
    assert first_entry["reuse_candidate_ids"] == [
        donor.task_id
        for donor in plan.reuse_candidates
        if donor.task_id != first_task.task_id
        and donor.kind is first_task.kind
    ]


def test_missing_selected_tasks_are_appended_to_donor_catalog(
    study_path: Path,
) -> None:
    plan = make_plan(study_path)
    selected = plan.tasks[0]
    unrelated = plan.tasks[1]
    plan = replace(plan, tasks=(selected,), reuse_candidates=(unrelated,))

    payload = build_subject_manifest(plan, RUN_ID)

    assert [entry["donor_id"] for entry in payload["reuse_donors"]] == [
        unrelated.task_id,
        selected.task_id,
    ]


def test_reuse_candidates_are_equivalent_ordered_and_exclude_recipient(
    study_path: Path,
) -> None:
    add_equivalent_phase(study_path, changed_amplitude=True)
    plan = make_plan(
        study_path,
        Selection(subject_ids=("SNr003",), phase_ids=("T1",)),
    )
    payload = build_subject_manifest(plan, RUN_ID)
    first_task = plan.tasks[0]
    first_entry = payload["tasks"][0]

    assert first_task.task_id not in first_entry["reuse_candidate_ids"]
    assert first_entry["reuse_candidate_ids"] == [
        donor.task_id
        for donor in plan.reuse_candidates
        if donor.task_id != first_task.task_id
        and donor.kind is first_task.kind
        and donor.phase_id == "T1"
    ]


@pytest.mark.parametrize("run_id", ["", "   ", None])
def test_empty_or_non_string_run_id_is_rejected(
    study_path: Path, run_id: object
) -> None:
    with pytest.raises(SubjectManifestError, match="run_id"):
        build_subject_manifest(make_plan(study_path), run_id)  # type: ignore[arg-type]


def test_empty_subject_id_is_rejected(study_path: Path) -> None:
    plan = make_plan(study_path)
    with pytest.raises(SubjectManifestError, match="subject_id"):
        build_subject_manifest(replace(plan, subject_id=""), RUN_ID)


def test_duplicate_selected_task_id_is_rejected(study_path: Path) -> None:
    plan = make_plan(study_path)
    with pytest.raises(SubjectManifestError, match="Duplicate selected task ID"):
        build_subject_manifest(replace(plan, tasks=(plan.tasks[0], plan.tasks[0])), RUN_ID)


def test_duplicate_donor_id_is_rejected(study_path: Path) -> None:
    plan = make_plan(study_path)
    with pytest.raises(SubjectManifestError, match="Duplicate donor ID"):
        build_subject_manifest(
            replace(plan, reuse_candidates=(plan.tasks[0], plan.tasks[0])), RUN_ID
        )


@pytest.mark.parametrize("location", ["selected", "donor"])
def test_cross_subject_tasks_and_donors_are_rejected(
    study_path: Path, location: str
) -> None:
    plan = make_plan(study_path)
    foreign = replace(plan.tasks[0], subject_id="other-subject")
    if location == "selected":
        changed = replace(plan, tasks=(foreign,))
    else:
        changed = replace(plan, tasks=(plan.tasks[0],), reuse_candidates=(foreign,))

    with pytest.raises(SubjectManifestError, match="Cross-subject"):
        build_subject_manifest(changed, RUN_ID)


@pytest.mark.parametrize("location", ["selected", "donor"])
def test_tasks_and_donors_outside_subject_plan_tree_are_rejected(
    study_path: Path, tmp_path: Path, location: str
) -> None:
    plan = make_plan(study_path)
    foreign = replace(plan.tasks[0], subject_dir=tmp_path / "other-subject")
    if location == "selected":
        changed = replace(plan, tasks=(foreign,))
    else:
        changed = replace(plan, tasks=(plan.tasks[0],), reuse_candidates=(foreign,))

    with pytest.raises(SubjectManifestError, match="Cross-subject path"):
        build_subject_manifest(changed, RUN_ID)


@pytest.mark.parametrize("location", ["selected", "donor"])
def test_inconsistent_reconstruction_is_rejected(
    study_path: Path, tmp_path: Path, location: str
) -> None:
    plan = make_plan(study_path)
    changed_task = replace(
        plan.tasks[1], reconstruction_path=tmp_path / "other-reconstruction.mat"
    )
    if location == "selected":
        changed = replace(plan, tasks=(plan.tasks[0], changed_task))
    else:
        changed = replace(
            plan, tasks=(plan.tasks[0],), reuse_candidates=(changed_task,)
        )

    with pytest.raises(SubjectManifestError, match="inconsistent reconstruction"):
        build_subject_manifest(changed, RUN_ID)


def test_unknown_dependency_is_rejected(study_path: Path) -> None:
    plan = select_first_task(make_plan(study_path))
    task = replace(plan.tasks[0], dependencies=("missing-task",))
    with pytest.raises(SubjectManifestError, match="Unknown dependency"):
        build_subject_manifest(replace(plan, tasks=(task,)), RUN_ID)


def test_forward_dependency_is_rejected(study_path: Path) -> None:
    plan = make_plan(study_path)
    first = replace(plan.tasks[0], dependencies=(plan.tasks[1].task_id,))
    with pytest.raises(SubjectManifestError, match="Forward dependency"):
        build_subject_manifest(replace(plan, tasks=(first, plan.tasks[1])), RUN_ID)


def test_duplicate_dependency_is_rejected(study_path: Path) -> None:
    plan = make_plan(study_path)
    dependency = plan.tasks[1].task_id
    task = replace(plan.tasks[2], dependencies=(dependency, dependency))
    with pytest.raises(SubjectManifestError, match="Duplicate dependency"):
        build_subject_manifest(replace(plan, tasks=plan.tasks[:2] + (task,)), RUN_ID)


def test_unknown_duplicate_and_self_reuse_references_are_rejected(
    study_path: Path,
) -> None:
    plan = make_plan(study_path)
    payload = build_subject_manifest(plan, RUN_ID)
    first_id = plan.tasks[0].task_id
    for candidate_ids in (["unknown"], [first_id, first_id], [first_id]):
        changed = deepcopy(payload)
        changed["tasks"][0]["reuse_candidate_ids"] = candidate_ids
        with pytest.raises(SubjectManifestError, match="reuse candidate|Reuse candidates"):
            validate_subject_manifest(changed, plan, RUN_ID)


def test_non_equivalent_reuse_reference_is_rejected(study_path: Path) -> None:
    plan = make_plan(study_path)
    payload = build_subject_manifest(plan, RUN_ID)
    non_equivalent = next(
        task
        for task in plan.tasks
        if task.kind is not plan.tasks[0].kind
    )
    changed = deepcopy(payload)
    changed["tasks"][0]["reuse_candidate_ids"] = [non_equivalent.task_id]

    with pytest.raises(SubjectManifestError, match="non-equivalent"):
        validate_subject_manifest(changed, plan, RUN_ID)


def test_noncanonical_selected_and_donor_leaves_are_rejected(
    study_path: Path,
) -> None:
    plan = make_plan(study_path)
    payload = build_subject_manifest(plan, RUN_ID)
    for collection in ("tasks", "reuse_donors"):
        changed = deepcopy(payload)
        changed[collection][0]["output_leaves"]["native"] = "/tmp/not-canonical"
        with pytest.raises(SubjectManifestError, match="Non-canonical"):
            validate_subject_manifest(changed, plan, RUN_ID)


def test_duplicate_writable_leaves_are_rejected(study_path: Path) -> None:
    plan = select_first_task(make_plan(study_path))
    duplicate = replace(plan.tasks[0], task_id="different-id")
    with pytest.raises(SubjectManifestError, match="Duplicate writable output leaf"):
        build_subject_manifest(replace(plan, tasks=(plan.tasks[0], duplicate)), RUN_ID)


def test_ancestor_descendant_writable_leaves_are_rejected(
    study_path: Path,
) -> None:
    plan = select_first_task(make_plan(study_path))
    parent = replace(
        plan.tasks[0],
        task_id="parent",
        frequency_group_id="base",
    )
    child = replace(
        plan.tasks[0],
        task_id="child",
        frequency_group_id="base/delivery-continuous/joint/descendant",
    )
    with pytest.raises(SubjectManifestError, match="ancestor/descendant"):
        build_subject_manifest(replace(plan, tasks=(parent, child)), RUN_ID)


def test_conflicting_selected_and_donor_definitions_are_rejected(
    study_path: Path,
) -> None:
    plan = select_first_task(make_plan(study_path))
    conflicting = replace(plan.tasks[0], phase_id="other-phase")
    with pytest.raises(SubjectManifestError, match="conflicts with donor"):
        build_subject_manifest(replace(plan, reuse_candidates=(conflicting,)), RUN_ID)


def test_shared_headmodel_context_conflict_is_rejected(study_path: Path) -> None:
    plan = make_plan(study_path)
    first = plan.tasks[0]
    conflicting = replace(
        first,
        task_id="same-headmodel-conflict",
        phase_id="different-phase",
        electrode_model="Different electrode",
    )
    changed = replace(
        plan,
        tasks=(first, conflicting),
        reuse_candidates=(first, conflicting),
    )

    with pytest.raises(SubjectManifestError, match="sharing headmodel"):
        build_subject_manifest(changed, RUN_ID)


def test_threshold_filename_collision_is_rejected(study_path: Path) -> None:
    plan = select_first_task(make_plan(study_path))
    task = plan.tasks[0]
    colliding_model = replace(
        task.model,
        primary_threshold_v_per_mm=0.180001,
        sensitivity_thresholds_v_per_mm=(0.180002,),
    )
    changed_task = replace(task, model=colliding_model)
    changed = replace(
        plan,
        tasks=(changed_task,),
        reuse_candidates=(changed_task,),
    )

    with pytest.raises(SubjectManifestError, match="colliding artifact"):
        build_subject_manifest(changed, RUN_ID)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload.update(schema_version="wrong"), "schema_version"),
        (lambda payload: payload.update(run_id="different-run"), "run_id"),
        (lambda payload: payload.update(subject_id="other"), "subject_id"),
        (lambda payload: payload.update(tasks={}), "tasks must be an array"),
        (lambda payload: payload.update(extra=True), "unsupported or missing"),
    ],
)
def test_malformed_manifest_envelope_is_rejected(
    study_path: Path, mutation, message: str
) -> None:
    plan = make_plan(study_path)
    payload = build_subject_manifest(plan, RUN_ID)
    mutation(payload)
    with pytest.raises(SubjectManifestError, match=message):
        validate_subject_manifest(payload, plan, RUN_ID)


def test_task_and_donor_order_changes_are_rejected(study_path: Path) -> None:
    plan = make_plan(study_path)
    payload = build_subject_manifest(plan, RUN_ID)
    for key in ("tasks", "reuse_donors"):
        changed = deepcopy(payload)
        changed[key][0], changed[key][1] = changed[key][1], changed[key][0]
        with pytest.raises(SubjectManifestError):
            validate_subject_manifest(changed, plan, RUN_ID)


def test_atomic_writer_produces_identical_utf8_json_bytes(
    study_path: Path, tmp_path: Path
) -> None:
    plan = make_plan(study_path)
    first = write_subject_manifest(tmp_path / "a" / "manifest.json", plan, RUN_ID)
    second = write_subject_manifest(tmp_path / "b" / "manifest.json", plan, RUN_ID)

    assert first.read_bytes() == second.read_bytes()
    assert first.read_bytes().endswith(b"\n")
    assert json.loads(first.read_text(encoding="utf-8")) == build_subject_manifest(
        plan, RUN_ID
    )
    assert not list(first.parent.glob(".*.tmp"))


def test_atomic_writer_replaces_destination_and_cleans_failed_temporary_file(
    study_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = make_plan(study_path)
    destination = tmp_path / "manifest.json"
    destination.write_bytes(b"old")
    real_replace = os.replace
    write_subject_manifest(destination, plan, RUN_ID)
    assert destination.read_bytes() != b"old"

    destination.write_bytes(b"preserved")

    def fail_replace(source: Path, target: Path) -> None:
        del source, target
        raise OSError("synthetic replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="synthetic replace failure"):
        write_subject_manifest(destination, plan, RUN_ID)
    monkeypatch.setattr(os, "replace", real_replace)

    assert destination.read_bytes() == b"preserved"
    assert not list(tmp_path.glob(".manifest.json.*.tmp"))
