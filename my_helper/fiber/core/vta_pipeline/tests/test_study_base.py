from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from my_helper.fiber.core import vta_pipeline
from my_helper.fiber.core.vta_pipeline.errors import StudyBaseError
from my_helper.fiber.core.vta_pipeline.study_base import load_study_base


FIXTURE = Path(__file__).with_name("fixtures") / "study_base_minimal.json"


def test_package_exports_study_loader() -> None:
    assert vta_pipeline.load_study_base is load_study_base


@pytest.fixture
def minimal_study_path(tmp_path: Path) -> Path:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    subject_dir = tmp_path / "subject"
    reconstruction = subject_dir / "reconstruction" / "sub-SNr003_desc-reconstruction.mat"
    reconstruction.parent.mkdir(parents=True)
    reconstruction.write_bytes(b"fixture")
    path = tmp_path / "study_base.json"
    path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    return path


def load_raw(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_raw(path: Path, raw: dict[str, object]) -> None:
    path.write_text(json.dumps(raw, indent=2), encoding="utf-8")


def right_group(raw: dict[str, object]) -> dict[str, object]:
    subject = raw["study"]["subjects"][0]
    program = subject["phases"][0]["programs"][0]
    return program["electrode_programs"][1]["frequency_groups"][0]


def test_right_contact_is_converted_to_side_local_one_based(
    minimal_study_path: Path,
) -> None:
    study = load_study_base(minimal_study_path)
    right = study.subjects[0].programs[0].electrodes[1]

    assert right.groups[0].sources[0].contacts[0].contact == 1
    assert right.groups[0].sources[1].contacts[0].contact == 2


def test_target_and_label_do_not_change_vta_semantic_payload(
    minimal_study_path: Path,
) -> None:
    original = load_study_base(minimal_study_path)
    raw = load_raw(minimal_study_path)
    source = right_group(raw)["sources"][0]
    source["component_id"] = "arbitrary-component"
    source["source_label"] = "arbitrary-label"
    save_raw(minimal_study_path, raw)

    changed = load_study_base(minimal_study_path)

    assert original.vta_semantic_payload() == changed.vta_semantic_payload()


def test_mixed_control_mode_group_is_rejected(minimal_study_path: Path) -> None:
    raw = load_raw(minimal_study_path)
    right_group(raw)["sources"][1]["control_mode"] = "voltage"
    save_raw(minimal_study_path, raw)

    with pytest.raises(StudyBaseError, match="homogeneous control_mode"):
        load_study_base(minimal_study_path)


def test_continuous_contact_reuse_is_rejected(minimal_study_path: Path) -> None:
    raw = load_raw(minimal_study_path)
    left_group = raw["study"]["subjects"][0]["phases"][0]["programs"][0][
        "electrode_programs"
    ][0]["frequency_groups"][0]
    duplicate = copy.deepcopy(left_group["sources"][0])
    duplicate["source_id"] = "source-2"
    left_group["sources"].append(duplicate)
    save_raw(minimal_study_path, raw)

    with pytest.raises(StudyBaseError, match="reuses contact"):
        load_study_base(minimal_study_path)


def test_source_fractions_must_sum_to_one_per_polarity(
    minimal_study_path: Path,
) -> None:
    raw = load_raw(minimal_study_path)
    right_group(raw)["sources"][0]["contacts"][0]["fraction"] = 0.8
    save_raw(minimal_study_path, raw)

    with pytest.raises(StudyBaseError, match="cathode fractions must sum to 1"):
        load_study_base(minimal_study_path)


def test_adapter_does_not_impose_four_source_limit(minimal_study_path: Path) -> None:
    raw = load_raw(minimal_study_path)
    group = right_group(raw)
    template = group["sources"][0]
    group["sources"] = []
    for index in range(5):
        source = copy.deepcopy(template)
        source["source_id"] = f"source-{index + 1}"
        source["contacts"][0]["contact"] = 4 + (index % 4)
        group["sources"].append(source)
    save_raw(minimal_study_path, raw)

    study = load_study_base(minimal_study_path)

    assert len(study.subjects[0].programs[0].electrodes[1].groups[0].sources) == 5


def test_missing_reconstruction_is_rejected(minimal_study_path: Path) -> None:
    raw = load_raw(minimal_study_path)
    raw["study"]["subjects"][0]["subject_sources"]["electrode_reconstruction"][
        "path"
    ] = "subject/reconstruction/missing.mat"
    save_raw(minimal_study_path, raw)

    with pytest.raises(StudyBaseError, match="reconstruction does not exist"):
        load_study_base(minimal_study_path)


def test_unsafe_identifier_is_rejected(minimal_study_path: Path) -> None:
    raw = load_raw(minimal_study_path)
    raw["study"]["subjects"][0]["phases"][0]["phase_id"] = "../T1"
    save_raw(minimal_study_path, raw)

    with pytest.raises(StudyBaseError, match="unsafe phase_id"):
        load_study_base(minimal_study_path)
