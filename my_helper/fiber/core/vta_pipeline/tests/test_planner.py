from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from my_helper.fiber.core.vta_pipeline.config import load_vta_model
from my_helper.fiber.core.vta_pipeline.errors import PlanningError
from my_helper.fiber.core.vta_pipeline.paths import leaf_directory
from my_helper.fiber.core.vta_pipeline.planner import (
    Selection,
    TaskKind,
    build_plan,
    equivalent_task_key,
    normalized_frequency_group,
)
from my_helper.fiber.core.vta_pipeline.study_base import load_study_base


REPO_ROOT = Path(__file__).resolve().parents[5]
FIXTURE = Path(__file__).with_name("fixtures") / "study_base_minimal.json"
MODEL_PATH = REPO_ROOT / "my_helper" / "stnsnr" / "config" / "vta_model.yaml"


@pytest.fixture
def study_path(tmp_path: Path) -> Path:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    reconstruction = (
        tmp_path
        / "subject"
        / "reconstruction"
        / "sub-SNr003_desc-reconstruction.mat"
    )
    reconstruction.parent.mkdir(parents=True)
    reconstruction.write_bytes(b"fixture")
    path = tmp_path / "study_base.json"
    path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    return path


def make_plan(study_path: Path):
    return build_plan(
        load_study_base(study_path),
        load_vta_model(MODEL_PATH),
        Selection(subject_ids=("SNr003",)),
    )


def add_equivalent_relabelled_phase(study_path: Path) -> None:
    raw = json.loads(study_path.read_text(encoding="utf-8"))
    subject = raw["study"]["subjects"][0]
    phase = deepcopy(subject["phases"][0])
    phase["phase_id"] = "arbitrary-followup"
    phase["phase_label"] = "Relabelled fixture phase"
    program = phase["programs"][0]
    program["program_id"] = 77
    program["program_label"] = "Relabelled fixture program"
    program["condition_role"] = "unrelated-display-role"
    for electrode in program["electrode_programs"]:
        for group_index, group in enumerate(electrode["frequency_groups"]):
            group["frequency_group_id"] = f"renamed-group-{group_index}"
            for source_index, source in enumerate(group["sources"]):
                source["source_id"] = f"renamed-source-{source_index}"
                source["source_label"] = "Relabelled source"
                source["component_id"] = "relabeled-component"
    subject["phases"].append(phase)
    study_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")


def test_continuous_group_creates_one_joint_task(study_path: Path) -> None:
    subject_plan = make_plan(study_path)[0]
    tasks = [
        task
        for task in subject_plan.tasks
        if task.frequency_group_id == "group-1"
    ]

    assert [task.kind for task in tasks] == [TaskKind.CONTINUOUS_JOINT]
    assert [source.source_id for source in tasks[0].sources] == ["source-1"]


def test_alternating_group_creates_source_tasks_then_peak(
    study_path: Path,
) -> None:
    subject_plan = make_plan(study_path)[0]
    tasks = [
        task
        for task in subject_plan.tasks
        if task.frequency_group_id == "group-2"
    ]

    assert [task.kind for task in tasks] == [
        TaskKind.ALTERNATING_SOURCE,
        TaskKind.ALTERNATING_SOURCE,
        TaskKind.ALTERNATING_GROUP_PEAK,
    ]
    assert tasks[-1].dependencies == tuple(task.task_id for task in tasks[:-1])


def test_leaf_path_is_hierarchical(study_path: Path) -> None:
    source_task = next(
        task
        for task in make_plan(study_path)[0].tasks
        if task.kind is TaskKind.ALTERNATING_SOURCE
    )

    assert leaf_directory(source_task, "native").parts[-8:] == (
        "native",
        "phase-T1",
        "program-1",
        "electrode-lead-R",
        "frequency-group-group-2",
        "delivery-alternating",
        "sources",
        "source-source-1",
    )


def test_plan_and_task_ids_are_deterministic(study_path: Path) -> None:
    first = make_plan(study_path)
    second = make_plan(study_path)

    assert first == second
    assert [task.task_id for task in first[0].tasks] == [
        task.task_id for task in second[0].tasks
    ]


def test_ignored_labels_do_not_change_task_ids(study_path: Path) -> None:
    first = make_plan(study_path)
    raw = json.loads(study_path.read_text(encoding="utf-8"))
    source = raw["study"]["subjects"][0]["phases"][0]["programs"][0][
        "electrode_programs"
    ][1]["frequency_groups"][0]["sources"][0]
    source["source_label"] = "changed"
    source["component_id"] = "changed"
    study_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    second = make_plan(study_path)

    assert [task.task_id for task in first[0].tasks] == [
        task.task_id for task in second[0].tasks
    ]


def test_selected_plan_keeps_all_same_subject_groups_as_reuse_candidates(
    study_path: Path,
) -> None:
    add_equivalent_relabelled_phase(study_path)
    subject_plan = build_plan(
        load_study_base(study_path),
        load_vta_model(MODEL_PATH),
        Selection(subject_ids=("SNr003",), phase_ids=("T1",)),
    )[0]

    assert len(subject_plan.tasks) == 4
    assert len(subject_plan.reuse_candidates) == 8
    assert {task.phase_id for task in subject_plan.tasks} == {"T1"}
    assert {task.phase_id for task in subject_plan.reuse_candidates} == {
        "T1",
        "arbitrary-followup",
    }


def test_frequency_group_equivalence_ignores_all_project_identifiers(
    study_path: Path,
) -> None:
    add_equivalent_relabelled_phase(study_path)
    plan = make_plan(study_path)[0]
    original = next(
        task
        for task in plan.reuse_candidates
        if task.phase_id == "T1" and task.kind is TaskKind.CONTINUOUS_JOINT
    )
    relabelled = next(
        task
        for task in plan.reuse_candidates
        if task.phase_id == "arbitrary-followup"
        and task.kind is TaskKind.CONTINUOUS_JOINT
    )

    assert normalized_frequency_group(original) == normalized_frequency_group(
        relabelled
    )
    assert equivalent_task_key(original) == equivalent_task_key(relabelled)


def test_frequency_group_equivalence_changes_with_physical_parameters(
    study_path: Path,
) -> None:
    add_equivalent_relabelled_phase(study_path)
    raw = json.loads(study_path.read_text(encoding="utf-8"))
    duplicate_source = raw["study"]["subjects"][0]["phases"][1]["programs"][0][
        "electrode_programs"
    ][0]["frequency_groups"][0]["sources"][0]
    duplicate_source["amplitude"] += 0.25
    study_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    plan = make_plan(study_path)[0]
    original = next(
        task
        for task in plan.reuse_candidates
        if task.phase_id == "T1" and task.kind is TaskKind.CONTINUOUS_JOINT
    )
    changed = next(
        task
        for task in plan.reuse_candidates
        if task.phase_id == "arbitrary-followup"
        and task.kind is TaskKind.CONTINUOUS_JOINT
    )

    assert normalized_frequency_group(original) != normalized_frequency_group(changed)
    assert equivalent_task_key(original) != equivalent_task_key(changed)


def test_filter_selects_exact_frequency_group(study_path: Path) -> None:
    plan = build_plan(
        load_study_base(study_path),
        load_vta_model(MODEL_PATH),
        Selection(
            subject_ids=("SNr003",),
            frequency_group_ids=("group-1",),
        ),
    )

    assert {task.frequency_group_id for task in plan[0].tasks} == {"group-1"}


def test_unknown_selector_is_rejected(study_path: Path) -> None:
    with pytest.raises(PlanningError, match="Unknown phase selector"):
        build_plan(
            load_study_base(study_path),
            load_vta_model(MODEL_PATH),
            Selection(subject_ids=("SNr003",), phase_ids=("T9",)),
        )


def test_subject_selection_is_required(study_path: Path) -> None:
    with pytest.raises(PlanningError, match="exactly one subject selection mode"):
        build_plan(
            load_study_base(study_path),
            load_vta_model(MODEL_PATH),
            Selection(),
        )
