"""Target-space point-field and tractogram-structure tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
import time

import nibabel as nib
import numpy as np
import pytest
from scipy.io import savemat

from ..config import resolve_config
from ..identity import file_sha256
from ..publication import OWNER
from ..state import atomic_write_json, read_json
from ..errors import ValidationError
from ..tck import iter_tck, write_selected_tck
from .. import tractogram_space as space_module
from ..tractogram_space import (
    DISPLACEMENT_INTENT,
    DomainStats,
    apply_affine,
    apply_point_field,
    apply_point_field_with_paired_inverse,
    coordinate_implementation_hash,
    load_point_field,
    ordered_target_memberships,
    paired_field_inverse_implementation_hash,
    roundtrip_implementation_hash,
    transform_seedwide_and_targets,
)
from .helpers import minimal_document
from .test_publication import _resolved_subject


def _write_reference(path: Path, shape=(7, 8, 9), affine=None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(
        nib.Nifti1Image(
            np.zeros(shape, dtype=np.uint8),
            np.eye(4) if affine is None else affine,
        ),
        path,
    )
    return path


def _write_field(
    path: Path,
    vectors: np.ndarray,
    *,
    affine=None,
    intent: int = DISPLACEMENT_INTENT,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = nib.Nifti1Image(
        np.asarray(vectors, dtype=np.float32),
        np.eye(4) if affine is None else affine,
    )
    image.header["intent_code"] = intent
    nib.save(image, path)
    return path


def test_direct_affine_point_transform_is_exact() -> None:
    matrix = np.asarray(
        [[1, 0, 0, 3], [0, 2, 0, -4], [0, 0, -1, 5], [0, 0, 0, 1]],
        dtype=np.float64,
    )
    points = np.asarray([[1, 2, 3], [-2, 0, 7]], dtype=np.float64)
    assert np.allclose(
        apply_affine(points, matrix),
        [[4, 0, 2], [1, -4, -2]],
        atol=0,
        rtol=0,
    )


def test_scientific_code_identity_excludes_publication_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinate_before = coordinate_implementation_hash()
    paired_inverse_before = paired_field_inverse_implementation_hash()
    roundtrip_before = roundtrip_implementation_hash()

    def changed_cleanup(*_args: object, **_kwargs: object) -> bool:
        return False

    monkeypatch.setattr(
        space_module,
        "_recover_target_space_intent",
        changed_cleanup,
    )
    assert coordinate_implementation_hash() == coordinate_before
    assert roundtrip_implementation_hash() == roundtrip_before

    def changed_inverse_solver(*_args: object, **_kwargs: object):
        raise AssertionError("not called")

    monkeypatch.setattr(
        space_module,
        "_solve_paired_field_inverse",
        changed_inverse_solver,
    )
    assert coordinate_implementation_hash() == coordinate_before
    assert paired_field_inverse_implementation_hash() != paired_inverse_before

    def changed_apply_affine(points: np.ndarray, _matrix: np.ndarray) -> np.ndarray:
        return points

    monkeypatch.setattr(space_module, "apply_affine", changed_apply_affine)
    assert coordinate_implementation_hash() != coordinate_before


@pytest.mark.parametrize(
    ("shape", "intent", "message"),
    [
        ((7, 8, 9, 3), DISPLACEMENT_INTENT, "vector layout"),
        ((7, 8, 9, 1, 3), 0, "displacement intent"),
    ],
)
def test_point_field_rejects_invalid_layout_or_intent(
    tmp_path: Path, shape: tuple[int, ...], intent: int, message: str
) -> None:
    reference = _write_reference(tmp_path / "reference.nii.gz")
    field = _write_field(
        tmp_path / "field.nii.gz", np.zeros(shape, dtype=np.float32), intent=intent
    )
    with pytest.raises(ValidationError, match=message):
        load_point_field(field, reference_path=reference, label="production field")


def test_asymmetric_ras_displacement_is_added_without_lps_mirroring(
    tmp_path: Path,
) -> None:
    reference = _write_reference(tmp_path / "reference.nii.gz")
    vectors = np.zeros((7, 8, 9, 1, 3), dtype=np.float32)
    vectors[..., 0, :] = [8.0, -30.0, 31.0]
    field = load_point_field(
        _write_field(tmp_path / "field.nii.gz", vectors),
        reference_path=reference,
        label="production field",
    )
    source = np.asarray([[1.5, 2.5, 3.5]], dtype=np.float64)
    assert np.allclose(
        apply_point_field(source, field), [[9.5, -27.5, 34.5]], atol=1e-7
    )


def test_concurrent_point_field_transform_is_process_serialized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = _write_reference(tmp_path / "reference.nii.gz")
    vectors = np.zeros((7, 8, 9, 1, 3), dtype=np.float32)
    field = load_point_field(
        _write_field(tmp_path / "field.nii.gz", vectors),
        reference_path=reference,
        label="production field",
    )
    observer_lock = threading.Lock()
    active_calls = 0
    maximum_active_calls = 0

    def observed_map_coordinates(
        _values: np.ndarray,
        coordinates: np.ndarray,
        **_kwargs: object,
    ) -> np.ndarray:
        nonlocal active_calls, maximum_active_calls
        with observer_lock:
            active_calls += 1
            maximum_active_calls = max(maximum_active_calls, active_calls)
        time.sleep(0.005)
        with observer_lock:
            active_calls -= 1
        return np.zeros(coordinates.shape[1], dtype=np.float64)

    monkeypatch.setattr(
        space_module,
        "map_coordinates",
        observed_map_coordinates,
    )
    points = np.asarray([[1.5, 2.5, 3.5], [2.5, 3.5, 4.5]], dtype=np.float64)
    with ThreadPoolExecutor(max_workers=4) as executor:
        outputs = list(
            executor.map(
                lambda _index: apply_point_field(points, field),
                range(4),
            )
        )
    assert all(np.array_equal(output, points) for output in outputs)
    assert maximum_active_calls == 1


def test_oblique_field_domain_uses_inverse_full_affine(tmp_path: Path) -> None:
    angle = np.deg2rad(25)
    affine = np.asarray(
        [
            [np.cos(angle), -np.sin(angle), 0, 10],
            [np.sin(angle), np.cos(angle), 0, -5],
            [0, 0, 1.5, 2],
            [0, 0, 0, 1],
        ]
    )
    reference = _write_reference(tmp_path / "reference.nii.gz", affine=affine)
    vectors = np.zeros((7, 8, 9, 1, 3), dtype=np.float32)
    field = load_point_field(
        _write_field(tmp_path / "field.nii.gz", vectors, affine=affine),
        reference_path=reference,
        label="production field",
    )
    voxel_points = np.asarray([[0, 0, 0], [6.49, 7.49, 8.49]], dtype=np.float64)
    world = apply_affine(voxel_points, affine)
    stats = DomainStats()
    assert np.allclose(apply_point_field(world, field, stats=stats), world)
    assert stats.inside_domain_point_count == 2
    outside = apply_affine(np.asarray([[6.51, 7.49, 8.49]]), affine)
    with pytest.raises(ValidationError, match="point_transform_domain_failed"):
        apply_point_field(outside, field)


def test_outside_primary_point_uses_converged_paired_field_inverse(
    tmp_path: Path,
) -> None:
    production_reference = _write_reference(
        tmp_path / "production_reference.nii.gz",
        shape=(3, 3, 3),
    )
    production_vectors = np.zeros((3, 3, 3, 1, 3), dtype=np.float32)
    production_vectors[..., 0, :] = [1.0, 0.0, 0.0]
    production = load_point_field(
        _write_field(tmp_path / "production.nii.gz", production_vectors),
        reference_path=production_reference,
        label="production",
    )
    reverse_affine = np.eye(4, dtype=np.float64)
    reverse_affine[:3, 3] = [-3.0, -3.0, -3.0]
    reverse_reference = _write_reference(
        tmp_path / "reverse_reference.nii.gz",
        shape=(7, 7, 7),
        affine=reverse_affine,
    )
    reverse_vectors = np.zeros((7, 7, 7, 1, 3), dtype=np.float32)
    reverse_vectors[..., 0, :] = [-1.0, 0.0, 0.0]
    reverse = load_point_field(
        _write_field(
            tmp_path / "reverse.nii.gz",
            reverse_vectors,
            affine=reverse_affine,
        ),
        reference_path=reverse_reference,
        label="reverse",
    )
    points = np.asarray([[-1.0, 1.0, 1.0], [1.0, 1.0, 1.0]])
    stats = DomainStats()
    transformed = apply_point_field_with_paired_inverse(
        points,
        production,
        reverse,
        stats=stats,
    )
    assert np.allclose(transformed, [[0, 1, 1], [2, 1, 1]], atol=1e-10)
    assert stats.outside_domain_point_count == 1
    assert stats.paired_field_inverse_solved_point_count == 1
    assert stats.paired_field_inverse_nonconverged_point_count == 0
    assert stats.paired_field_inverse_max_residual_mm <= 1e-10
    assert stats.unresolved_domain_point_count == 0


def test_outside_primary_point_fails_when_paired_field_cannot_solve(
    tmp_path: Path,
) -> None:
    production_reference = _write_reference(
        tmp_path / "production_reference.nii.gz",
        shape=(3, 3, 3),
    )
    production_vectors = np.zeros((3, 3, 3, 1, 3), dtype=np.float32)
    production_vectors[..., 0, :] = [1.0, 0.0, 0.0]
    production = load_point_field(
        _write_field(tmp_path / "production.nii.gz", production_vectors),
        reference_path=production_reference,
        label="production",
    )
    reverse_affine = np.eye(4, dtype=np.float64)
    reverse_affine[:3, 3] = [10.0, 10.0, 10.0]
    reverse_reference = _write_reference(
        tmp_path / "reverse_reference.nii.gz",
        shape=(2, 2, 2),
        affine=reverse_affine,
    )
    reverse_vectors = np.zeros((2, 2, 2, 1, 3), dtype=np.float32)
    reverse = load_point_field(
        _write_field(
            tmp_path / "reverse.nii.gz",
            reverse_vectors,
            affine=reverse_affine,
        ),
        reference_path=reverse_reference,
        label="reverse",
    )
    stats = DomainStats()
    with pytest.raises(ValidationError, match="point_inverse_solver_failed"):
        apply_point_field_with_paired_inverse(
            np.asarray([[-1.0, 1.0, 1.0]]),
            production,
            reverse,
            stats=stats,
        )
    assert stats.paired_field_inverse_solved_point_count == 0
    assert stats.paired_field_inverse_nonconverged_point_count == 1
    assert stats.unresolved_domain_point_count == 1


def test_ordered_membership_and_single_seedwide_transform_preserve_structure(
    tmp_path: Path,
) -> None:
    streamlines = [
        np.asarray([[1 + i, 1, 1], [1 + i, 2, 2]], dtype=np.float32)
        for i in range(4)
    ]
    native_seedwide = tmp_path / "native" / "seedwide.tck"
    native_a = tmp_path / "native" / "a.tck"
    native_b = tmp_path / "native" / "b.tck"
    write_selected_tck(streamlines, np.ones(4, dtype=bool), native_seedwide)
    write_selected_tck(streamlines, np.asarray([True, False, True, False]), native_a)
    write_selected_tck(streamlines, np.asarray([False, True, True, True]), native_b)
    seed_count, memberships = ordered_target_memberships(
        native_seedwide, {"a": native_a, "b": native_b}
    )
    assert seed_count == 4
    assert memberships == {"a": (0, 2), "b": (1, 2, 3)}

    reference = _write_reference(tmp_path / "reference.nii.gz")
    vectors = np.zeros((7, 8, 9, 1, 3), dtype=np.float32)
    vectors[..., 0, :] = [0.25, -0.5, 1.0]
    field = load_point_field(
        _write_field(tmp_path / "field.nii.gz", vectors),
        reference_path=reference,
        label="production field",
    )
    transform = tmp_path / "b0_to_anchor44.mat"
    matrix = np.eye(4)
    matrix[:3, 3] = [0.5, 0.25, -0.25]
    savemat(transform, {"tmat": matrix})
    target_seedwide = tmp_path / "target" / "seedwide.tck"
    target_a = tmp_path / "target" / "a.tck"
    target_b = tmp_path / "target" / "b.tck"
    stats, realized = transform_seedwide_and_targets(
        native_seedwide=native_seedwide,
        native_targets={"a": native_a, "b": native_b},
        target_seedwide=target_seedwide,
        target_targets={"a": target_a, "b": target_b},
        b0_to_anchor_transform=transform,
        production_field=field,
        point_budget=5,
    )
    assert realized == memberships
    transformed = list(iter_tck(target_seedwide))
    expected_offset = np.asarray([0.75, -0.25, 0.75])
    assert len(transformed) == 4
    assert [item.shape[0] for item in transformed] == [2, 2, 2, 2]
    for source, result in zip(streamlines, transformed, strict=True):
        assert np.allclose(result, source + expected_offset, atol=1e-6)
    assert len(list(iter_tck(target_a))) == 2
    assert len(list(iter_tck(target_b))) == 3
    assert stats.total_point_count == 8
    assert stats.outside_domain_point_count == 0


def test_paired_point_fields_and_affines_round_trip(tmp_path: Path) -> None:
    reference = _write_reference(tmp_path / "reference.nii.gz")
    forward_vectors = np.zeros((7, 8, 9, 1, 3), dtype=np.float32)
    reverse_vectors = np.zeros_like(forward_vectors)
    forward_vectors[..., 0, :] = [0.2, -0.3, 0.4]
    reverse_vectors[..., 0, :] = [-0.2, 0.3, -0.4]
    forward = load_point_field(
        _write_field(tmp_path / "forward.nii.gz", forward_vectors),
        reference_path=reference,
        label="forward",
    )
    reverse = load_point_field(
        _write_field(tmp_path / "reverse.nii.gz", reverse_vectors),
        reference_path=reference,
        label="reverse",
    )
    source = np.asarray([[2, 3, 4], [4, 2, 1]], dtype=np.float64)
    target = apply_point_field(source, forward)
    restored = apply_point_field(target, reverse)
    assert np.allclose(restored, source, atol=1e-7)


def test_interrupted_target_side_publication_is_promoted_without_retransform(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = minimal_document(tmp_path)
    document["subjects"][0]["subject_dir"] = str(tmp_path / "sub-001")
    config = resolve_config(document, source_path=tmp_path / "config.yaml")
    subject = _resolved_subject(tmp_path / "sub-001")
    seed = config.atlas.seeds[0]
    root = subject.output_root / "tractograms" / config.atlas.space
    seedwide = root / "lh" / "Seed" / "seedwide.tck"
    target = root / "lh" / "Seed" / "targets" / "lh" / "Target.tck"
    streamlines = [np.asarray([[0, 0, 0], [1, 1, 1]], dtype=np.float32)]
    write_selected_tck(streamlines, np.asarray([True]), seedwide)
    write_selected_tck(streamlines, np.asarray([True]), target)
    records = [
        {
            "semantic_key": "lh/Seed/seedwide",
            "coordinate_space": config.atlas.space,
            "path": str(seedwide),
            "sha256": file_sha256(seedwide),
            "streamline_count": 1,
            "coordinate_fingerprint": "coordinate",
            "roundtrip_qc_fingerprint": "roundtrip",
            "domain_stats": {"total_point_count": 2},
            "roundtrip_qc": {"max_mm": 0.01},
        },
        {
            "semantic_key": "lh/Seed/target/lh/Target",
            "coordinate_space": config.atlas.space,
            "path": str(target),
            "sha256": file_sha256(target),
            "streamline_count": 1,
            "coordinate_fingerprint": "coordinate",
            "roundtrip_qc_fingerprint": "roundtrip",
            "domain_stats": {"total_point_count": 2},
            "roundtrip_qc": {"max_mm": 0.01},
        },
    ]
    state_path = subject.output_root / "work" / "state.json"
    state = {
        "owner": OWNER,
        "status": "target_space_transforming",
        "published_artifacts": [
            {
                "semantic_key": "lh/Seed/seedwide",
                "coordinate_space": "native",
                "path": "/native/seedwide.tck",
            }
        ],
        "target_space_intent": {
            "transaction_id": "a" * 32,
            "side": "lh",
            "artifacts": records,
        },
    }
    atomic_write_json(state_path, state)
    monkeypatch.setattr(space_module, "validate_tck", lambda *_args, **_kwargs: None)
    assert space_module._recover_target_space_intent(
        config=config,
        subject=subject,
        seed=seed,
        state=state,
        state_path=state_path,
        tckinfo=Path("/tmp/tckinfo"),
        coordinate_identity="coordinate",
        roundtrip_identity="roundtrip",
        final_side_root=root / "lh",
    )
    recovered = read_json(state_path)
    assert recovered["target_space_intent"] == {}
    assert len(recovered["published_artifacts"]) == 3
    assert recovered["target_space_sides"]["lh"]["roundtrip_qc"]["max_mm"] == 0.01
