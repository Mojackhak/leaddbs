"""Whole-brain fixed sampling, target availability and scoped reuse regressions."""

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import shutil

import nibabel as nib
import numpy as np
import pytest
from scipy.io import savemat
import yaml

from .. import preparation, roi, tracking, publication
from ..config import load_config, resolve_config
from ..errors import ConfigurationError, ValidationError
from ..identity import file_sha256
from ..models import ToolIdentity
from ..publication import available_target_config, publish_subject
from ..state import atomic_write_json, read_json
from ..tck import validate_tck, write_selected_tck
from ..validation import _validate_source_rois
from ..tractogram_space import verify_native_publication
from .helpers import minimal_document, write_nifti
from .test_tracking import _preparation_with_fod
from .test_publication import _resolved_subject, RUN_PROVENANCE


def fixed_document(root):
    document = minimal_document(root)
    document["tracking"].update(seedwide_streamlines=4, minimum_streamlines_per_target=0, random_seed=42)
    document["execution"].update(generation_chunk_streamlines=2, maximum_seedwide_streamlines=4)
    return document


def test_matlab_version_excludes_startup_warnings():
    from ..tools import _normalize_version
    expected = "MATLAB 24.2.0.2863752 (R2024b) Update 5 release 2024b"
    assert _normalize_version("Warning: old path\n" * 6 + expected) == expected
    assert _normalize_version("Warning: different path\n" + expected) == expected


def test_zero_minimum_requires_fixed_sampling_and_yaml_is_semantic(tmp_path):
    document = minimal_document(tmp_path)
    document["tracking"]["minimum_streamlines_per_target"] = 0
    with pytest.raises(ConfigurationError, match="requires fixed"):
        resolve_config(document, source_path=tmp_path / "config.yaml")
    document = fixed_document(tmp_path)
    first = tmp_path / "first.yaml"
    second = tmp_path / "second.yaml"
    first.write_text(yaml.safe_dump(document, sort_keys=False))
    second.write_text("# Comment only\n" + yaml.safe_dump(document, sort_keys=True))
    assert load_config(first).configuration_hash == load_config(second).configuration_hash


def test_source_rois_can_have_different_grids(tmp_path):
    config = resolve_config(fixed_document(tmp_path), source_path=tmp_path / "config.yaml")
    seed = config.atlas.seeds[0]
    write_nifti(seed.path, np.ones((4, 4, 4), dtype=np.uint8), np.diag([0.5, 0.5, 0.5, 1]))
    write_nifti(seed.targets[0].path, np.ones((2, 2, 2), dtype=np.uint8))
    assert len(_validate_source_rois(config)) == 2


def test_roi_availability_overlap_and_individual_transform_reuse(tmp_path, monkeypatch):
    document = fixed_document(tmp_path)
    first = document["atlas"]["seeds"][0]
    first["targets"].append({"id": "Outside", "side": "rh", "path": str(tmp_path / "atlas/rh/Outside.nii.gz")})
    second = deepcopy(first)
    second["id"] = "OtherSeed"
    document["atlas"]["seeds"].append(second)
    config = resolve_config(document, source_path=tmp_path / "config.yaml")
    seed = config.atlas.seeds[0]
    data = np.zeros((6, 6, 6), dtype=np.uint8)
    data[2, 2, 2] = 1
    write_nifti(seed.path, data)
    target = data.copy()
    target[3, 2, 2] = 1
    write_nifti(seed.targets[0].path, target)
    affine = np.eye(4)
    affine[0, 3] = 100
    write_nifti(seed.targets[1].path, data, affine)
    mask = np.ones_like(data)
    mask[3, 2, 2] = 0
    b0 = write_nifti(tmp_path / "b0.nii.gz", data)
    tracking_mask = write_nifti(tmp_path / "mask.nii.gz", mask)
    transform = tmp_path / "transform.mat"
    savemat(transform, {"tmat": np.eye(4)})
    subject = replace(_resolved_subject(tmp_path / "sub-001"), b0=b0, tracking_mask=tracking_mask,
                      anchor_native_reference=b0, anchor_to_b0_transform=transform)
    calls = []

    def matlab_stub(command, *, log_path, **kwargs):
        manifest = read_json(log_path.parent / "matlab_roi_manifest.json")
        calls.append(len(manifest["rois"]))
        for item in manifest["rois"]:
            nib.save(nib.load(item["source"]), item["anchor_output"])
        atomic_write_json(Path(manifest["result_path"]), {"status": "complete"})

    monkeypatch.setattr(roi, "run_command", matlab_stub)
    kwargs = dict(config=config, subject=subject, preparation_dir=tmp_path / "work/preparations",
                  matlab=ToolIdentity("matlab", Path("/bin/true"), "test"), repo_root=tmp_path,
                  transform_inputs={})
    result = roi.prepare_rois(**kwargs)
    assert calls == [3]  # Two seed names share one source and transform.
    targets = result["seeds"][seed.key]["targets"]
    assert targets[0]["voxel_count"] == 2
    assert targets[0]["removed_seed_overlap_voxels"] == 0
    assert targets[0]["seed_overlap_voxels"] == 1
    assert targets[0]["partial_tracking_mask_coverage"]
    assert not targets[0]["comparison_eligible"]
    assert targets[1]["available"] is False
    assert targets[1]["unavailable_reason"] == "empty_native_roi"
    roi.prepare_rois(**kwargs)
    assert calls == [3]
    target[4, 2, 2] = 1
    write_nifti(seed.targets[0].path, target)
    roi.prepare_rois(**kwargs)
    assert calls == [3, 1]
    legacy = replace(config, tracking=replace(config.tracking, minimum_streamlines_per_target=1))
    with pytest.raises(ValidationError, match="unavailable"):
        roi.prepare_rois(**{**kwargs, "config": legacy})
    assert roi.target_qc(data.astype(bool), data.astype(bool), np.zeros_like(data, dtype=bool))["unavailable_reason"] == "outside_tracking_mask"


def tracking_fixture(tmp_path, monkeypatch):
    document = fixed_document(tmp_path)
    document["subjects"][0]["subject_dir"] = str(tmp_path / "sub-001")
    seed_spec = document["atlas"]["seeds"][0]
    seed_spec["targets"].extend([
        {"id": "Zero", "side": "rh", "path": str(tmp_path / "atlas/rh/Zero.nii.gz")},
        {"id": "MissingNative", "side": "midline", "path": str(tmp_path / "atlas/midline/MissingNative.nii.gz")},
    ])
    config = resolve_config(document, source_path=tmp_path / "config.yaml")
    seed = config.atlas.seeds[0]
    prep = _preparation_with_fod(tmp_path / "fod", b"fod")
    mask = write_nifti(Path(prep["identity_document"]["inputs"]["tracking_mask"]["path"]),
                       np.ones((6, 6, 6), dtype=np.uint8))
    prep["identity_document"]["inputs"]["tracking_mask"]["sha256"] = file_sha256(mask)
    for artifact in prep["artifacts"].values():
        artifact["size_bytes"] = Path(artifact["path"]).stat().st_size
    seed_data = np.zeros((6, 6, 6), dtype=np.uint8)
    seed_data[1, 2, 2] = 1
    write_nifti(seed.path, seed_data)
    targets = []
    for i, target in enumerate(seed.targets):
        data = np.zeros_like(seed_data)
        if i == 0:
            data[2, 2, 2] = 1
        elif i == 1:
            data[5, 5, 5] = 1
        write_nifti(target.path, data)
        targets.append({"id": target.roi_id, "side": target.side, "key": target.key,
                        "path": str(target.path), "hash": file_sha256(target.path),
                        "available": i != 2, "unavailable_reason": "empty_native_roi" if i == 2 else None})
    seed_record = {"path": str(seed.path), "hash": file_sha256(seed.path), "targets": targets}
    prep["rois"] = {"seeds": {seed.key: seed_record}}
    tools = {name: ToolIdentity(name, Path("/usr/local/bin") / name, "test")
             for name in ("tckgen", "tckinfo")}
    calls = []

    def tckgen_stub(command, **kwargs):
        count = int(command[command.index("-select") + 1])
        calls.append(kwargs["environment"]["MRTRIX_RNG_SEED"])
        lines = [np.array([[0, 2 + 0.01 * (len(calls) * count + i), 2],
                           [3, 2 + 0.01 * (len(calls) * count + i), 2]], dtype=np.float32)
                 for i in range(count)]
        write_selected_tck(lines, np.ones(count, dtype=bool), Path(command[2]))

    monkeypatch.setattr(tracking, "run_command", tckgen_stub)
    subject = _resolved_subject(tmp_path / "sub-001")
    kwargs = dict(config=config, subject_id=subject.subject_id, seed=seed, preparation=prep,
                  tools=tools, code_hash="provenance-only", work_root=subject.output_root / "work")
    return config, subject, prep, kwargs, calls


def test_fixed_mother_reused_for_target_change_and_unavailable_publication(tmp_path, monkeypatch):
    config, subject, prep, kwargs, calls = tracking_fixture(tmp_path, monkeypatch)
    first = tracking.run_seedwide(**kwargs)
    assert len(calls) == 2
    assert first["total_streamlines"] == 4
    assert [t["streamline_count"] for t in first["outputs"]["targets"]] == [4, 0, None]
    assert validate_tck(first["outputs"]["targets"][1]["path"], kwargs["tools"]["tckinfo"].executable) == 0
    assert first["outputs"]["targets"][2]["path"] is None
    identity = first["seedwide_identity"]
    seed_record = prep["rois"]["seeds"][kwargs["seed"].key]
    moved_record = {**seed_record, "path": str(tmp_path / "same-mask-different-cache-path.nii.gz")}
    assert tracking.seedwide_identity(config, subject.subject_id, prep, kwargs["seed"],
        moved_record, kwargs["tools"], "unrelated-code")[0] == identity
    original_rng = calls.copy()
    target = prep["rois"]["seeds"][kwargs["seed"].key]["targets"][0]
    data = np.zeros((6, 6, 6), dtype=np.uint8)
    data[4, 4, 4] = 1
    write_nifti(Path(target["path"]), data)
    target["hash"] = file_sha256(target["path"])
    second = tracking.run_seedwide(**kwargs)
    assert calls == original_rng
    assert second["seedwide_identity"] == identity
    assert second["outputs"]["targets"][0]["streamline_count"] == 0
    assert second["outputs"]["mother"]["sha256"] == first["outputs"]["mother"]["sha256"]
    publish_subject(config=config, subject=subject, preparation=prep,
                    seed_results={kwargs["seed"].key: second}, run_provenance=RUN_PROVENANCE)
    state = verify_native_publication(config, subject, tckinfo=kwargs["tools"]["tckinfo"].executable)
    assert len(state["published_artifacts"]) == 3
    assert len(available_target_config(config, state).atlas.seeds[0].targets) == 2
    assert state["seed_results"][kwargs["seed"].key]["targets"][2]["streamline_count"] is None
    shutil.rmtree(kwargs["work_root"] / "seedwide")
    data[2, 2, 2] = 1
    write_nifti(Path(target["path"]), data)
    target["hash"] = file_sha256(target["path"])
    third = tracking.run_seedwide(**kwargs)
    assert calls == original_rng
    assert third["outputs"]["targets"][0]["streamline_count"] == 4
    assert third["outputs"]["mother"]["sha256"] == first["outputs"]["mother"]["sha256"]
    changed = replace(config, tracking=replace(config.tracking, minimum_streamlines_per_target=1))
    assert tracking.seedwide_identity(changed, subject.subject_id, prep, kwargs["seed"],
        prep["rois"]["seeds"][kwargs["seed"].key], kwargs["tools"], "changed-code")[0] == identity


def test_fod_identity_ignores_targets_and_transforms(tmp_path):
    config = resolve_config(fixed_document(tmp_path), source_path=tmp_path / "config.yaml")
    subject = _resolved_subject(tmp_path / "sub-001")
    subject.dwi.parent.mkdir(parents=True)
    subject.dwi.write_bytes(b"input")
    validation = SimpleNamespace(config=config, tools={})
    first = preparation.preparation_identity(validation, subject)[0]
    changed = replace(config, atlas=replace(config.atlas, seeds=()))
    assert preparation.preparation_identity(SimpleNamespace(config=changed, tools={}),
        replace(subject, anchor_to_b0_transform=tmp_path / "other.mat"))[0] == first
    subject.dwi.write_bytes(b"changed")
    assert preparation.preparation_identity(validation, subject)[0] != first


def test_two_seeds_on_one_side_convert_and_replace_independently(tmp_path, monkeypatch):
    from .. import tractogram_space as space
    from .test_tractogram_space import _write_field

    config, subject, prep, kwargs, calls = tracking_fixture(tmp_path, monkeypatch)
    result = tracking.run_seedwide(**kwargs)
    seed = config.atlas.seeds[0]
    second_seed = replace(seed, roi_id="OtherSeed")
    config = replace(config, atlas=replace(config.atlas, seeds=(seed, second_seed)))
    matrix = tmp_path / "identity.mat"
    savemat(matrix, {"tmat": np.eye(4)})
    field = _write_field(tmp_path / "field.nii.gz", np.zeros((6, 6, 6, 1, 3), dtype=np.float32))
    subject = replace(subject, b0_to_anchor_transform=matrix, anchor_to_b0_transform=matrix,
                      anchor_native_reference=seed.path, target_to_anchor_image_deformation=field,
                      anchor_to_target_image_deformation=field)
    results = {seed.key: result, second_seed.key: deepcopy(result)}
    monkeypatch.setattr(space, "ants_reference_transform", lambda points, **kwargs: points.copy())
    monkeypatch.setattr(space, "send2trash", lambda path: shutil.rmtree(path))
    monkeypatch.setattr(publication, "send2trash", lambda path: Path(path).unlink())
    publish_subject(config=config, subject=subject, preparation=prep,
                    seed_results=results, run_provenance=RUN_PROVENANCE)
    convert_kwargs = dict(config=config, subject=subject, tckinfo=kwargs["tools"]["tckinfo"].executable,
                          ants=ToolIdentity("ants", Path("/bin/true"), "test"), code_hash="display-provenance")
    converted = space.convert_subject_target_space(**convert_kwargs)
    assert converted["completed_sides"] == [seed.key, second_seed.key]
    second_mother = subject.output_root / "tractograms" / config.atlas.space / second_seed.key / "seedwide.tck"
    mtime = second_mother.stat().st_mtime_ns
    first_target = result["outputs"]["targets"][0]
    zero = tmp_path / "zero.tck"
    write_selected_tck([], np.zeros(0, dtype=bool), zero)
    first_target.update(path=str(zero), sha256=file_sha256(zero), streamline_count=0, hit_fraction=0.0)
    publish_subject(config=config, subject=subject, preparation=prep,
                    seed_results=results, run_provenance=RUN_PROVENANCE)
    space.convert_subject_target_space(**convert_kwargs)
    assert second_mother.stat().st_mtime_ns == mtime
    state = read_json(subject.output_root / "work/state.json")
    assert len(state["published_artifacts"]) == 12  # Two mothers and four available targets, both spaces.
    first_mni_target = subject.output_root / "tractograms" / config.atlas.space / seed.key / "targets/lh/Target.tck"
    assert validate_tck(first_mni_target, kwargs["tools"]["tckinfo"].executable) == 0


def test_target_only_change_after_cleanup_does_not_prepare_fod(tmp_path, monkeypatch):
    config, subject, prep, kwargs, calls = tracking_fixture(tmp_path, monkeypatch)
    result = tracking.run_seedwide(**kwargs)
    fod = {key: value for key, value in prep.items() if key != "rois"}
    prep["fod_preparation"] = fod
    publish_subject(config=config, subject=subject, preparation=prep,
                    seed_results={kwargs["seed"].key: result}, run_provenance=RUN_PROVENANCE)
    for artifact in fod["artifacts"].values():
        Path(artifact["path"]).unlink()
    monkeypatch.setattr(preparation, "prepare_rois", lambda *args, **kw: prep["rois"])
    def forbidden(*args, **kw):
        raise AssertionError("FOD preparation should not run for reclassification")
    monkeypatch.setattr(preparation, "_prepare_fod", forbidden)
    subject = replace(subject, tracking_mask=Path(prep["identity_document"]["inputs"]["tracking_mask"]["path"]))
    validation = SimpleNamespace(config=config, source_roi_hashes={}, tracking_code_hash="ignored",
                                 tools={**kwargs["tools"], "matlab": ToolIdentity("matlab", Path("/bin/true"), "test")})
    composed, action = preparation.prepare_subject(validation, subject, tmp_path,
        identity_record=(prep["preparation_identity"], prep["identity_document"]), roi_inputs={})
    assert action == "reused_published_mothers"
    assert kwargs["seed"].key in composed["reusable_published_seeds"]


def test_native_request_ignores_display_and_other_subjects(tmp_path):
    config = resolve_config(fixed_document(tmp_path), source_path=tmp_path / "config.yaml")
    subject = _resolved_subject(tmp_path / "sub-001")
    subject.dwi.parent.mkdir(parents=True)
    subject.dwi.write_bytes(b"mask")
    validation = SimpleNamespace(config=config, source_roi_hashes={"target": "hash"},
                                 tools={name: ToolIdentity(name, Path("/bin/true"), "test")
                                        for name in ("tckgen", "matlab")})
    first = preparation.native_request_identity(validation, subject, "fod", {"transform": "identity"})
    config = replace(config, subjects=(), visualization=replace(config.visualization,
                     target_fiber_display_budget=50), configuration_hash="different batch")
    validation.config = config
    assert preparation.native_request_identity(validation, subject, "fod", {"transform": "identity"}) == first
    validation.source_roi_hashes = {"target": "changed"}
    assert preparation.native_request_identity(validation, subject, "fod", {"transform": "identity"}) != first


def test_display_input_omits_unavailable_targets_and_supports_seed_only_scene(tmp_path, monkeypatch):
    from ..visualization import prepare_display_input
    config, subject, prep, kwargs, _ = tracking_fixture(tmp_path, monkeypatch)
    result = tracking.run_seedwide(**kwargs)
    publish_subject(config=config, subject=subject, preparation=prep,
                    seed_results={kwargs["seed"].key: result}, run_provenance=RUN_PROVENANCE)
    state = read_json(subject.output_root / "work/state.json")
    for record in list(state["published_artifacts"]):
        state["published_artifacts"].append({**record, "coordinate_space": config.atlas.space})
    selected = available_target_config(config, state)
    display = prepare_display_input(config=selected, subject=subject, seed=selected.atlas.seeds[0],
                                    state=state, code_hash="test")
    assert display["ordered_target_ids"] == ["Target", "Zero"]
    rows = state["seed_results"][kwargs["seed"].key]["targets"]
    for row in rows:
        row.update(available=False, unavailable_reason="outside_tracking_mask",
                   streamline_count=None, hit_fraction=None)
    selected = available_target_config(config, state)
    display = prepare_display_input(config=selected, subject=subject, seed=selected.atlas.seeds[0],
                                    state=state, code_hash="test")
    assert display["ordered_target_ids"] == []
    assert display["realized_membership_instance_count"] == 0
