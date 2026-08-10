"""Deterministic Lead-DBS subject input discovery and validation."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Iterable

import nibabel as nib
import numpy as np
from scipy.io import loadmat

from .errors import DiscoveryError, ValidationError
from .models import ResolvedSubjectInputs, SubjectSpec


_METHOD_TOKENS = (
    (re.compile(r"^SPM\b", re.IGNORECASE), "spm"),
    (re.compile(r"^BRAINSFit\b", re.IGNORECASE), "brainsfit"),
    (re.compile(r"^ANTs\b", re.IGNORECASE), "ants"),
)


def _require_file(path: Path, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise DiscoveryError(f"{label} does not exist: {resolved}")
    return resolved


def _select_extension_variant(directory: Path, stem: str, label: str) -> Path:
    candidates = [directory / f"{stem}.nii", directory / f"{stem}.nii.gz"]
    existing = [candidate.resolve() for candidate in candidates if candidate.is_file()]
    if not existing:
        raise DiscoveryError(
            f"cannot discover {label}; expected {candidates[0]} or {candidates[1]}"
        )
    if len(existing) > 1:
        raise DiscoveryError(
            f"ambiguous {label}; both NIfTI variants exist: "
            + ", ".join(str(path) for path in existing)
        )
    return existing[0]


def _select_ordered_b0(directory: Path, subject_id: str) -> Path:
    stems = (
        f"{subject_id}_ses-preop_desc-preproc_dwi_b0",
        f"{subject_id}_ses-preop_desc-preproc_b0",
    )
    for stem in stems:
        matches = [
            candidate.resolve()
            for candidate in (directory / f"{stem}.nii", directory / f"{stem}.nii.gz")
            if candidate.is_file()
        ]
        if len(matches) > 1:
            raise DiscoveryError(
                f"ambiguous native preprocessed b0 for {subject_id}: "
                + ", ".join(str(path) for path in matches)
            )
        if matches:
            return matches[0]
    raise DiscoveryError(
        f"cannot discover native preprocessed b0 for {subject_id} in {directory}"
    )


def _select_anchor_reference(subject_dir: Path, subject_id: str) -> Path:
    directory = subject_dir / "coregistration" / "anat"
    candidates: list[Path] = []
    for pattern in (
        f"{subject_id}_ses-preop_space-anchorNative_desc-preproc_*T1w.nii",
        f"{subject_id}_ses-preop_space-anchorNative_desc-preproc_*T1w.nii.gz",
    ):
        for path in directory.glob(pattern):
            name = path.name.lower()
            if "label-" in name or "_mask" in name or name.startswith("._"):
                continue
            candidates.append(path.resolve())
    candidates = sorted(set(candidates))
    if len(candidates) != 1:
        detail = ", ".join(str(path) for path in candidates) or "none"
        raise DiscoveryError(
            f"expected exactly one anatomical anchorNative T1w reference for "
            f"{subject_id}; found {len(candidates)}: {detail}"
        )
    return candidates[0]


def _load_coregistration_method(path: Path) -> tuple[str, str, bool]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        method = str(document["method"]["B0"])
        approved_value = document["approval"]["B0"]
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise DiscoveryError(
            f"invalid B0 coregistration method log {path}: {exc}"
        ) from exc
    approved = bool(approved_value == 1 or approved_value is True)
    if not approved:
        raise DiscoveryError(f"B0 coregistration is not approved in {path}")
    for pattern, token in _METHOD_TOKENS:
        if pattern.search(method):
            return method, token, approved
    raise DiscoveryError(f"unsupported B0 coregistration method {method!r} in {path}")


def _load_normalization_method(path: Path) -> tuple[str, float]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        method_value = document["method"]
        approval_value = document["approval"]
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise DiscoveryError(
            f"invalid normalization method log {path}: {exc}"
        ) from exc
    if not isinstance(method_value, str) or not method_value.strip():
        raise DiscoveryError(f"normalization method is missing or invalid in {path}")
    if isinstance(approval_value, bool) or not isinstance(
        approval_value, (int, float)
    ):
        raise DiscoveryError(
            f"normalization approval must be one numeric scalar in {path}"
        )
    approval = float(approval_value)
    if approval not in {0.5, 1.0}:
        raise DiscoveryError(
            f"normalization is not approved in {path}: approval={approval_value!r}"
        )
    return method_value.strip(), approval


def _default_paths(subject: SubjectSpec, target_space: str) -> dict[str, Path]:
    subject_id = subject.subject_id
    root = subject.subject_dir
    dwi_dir = root / "preprocessing" / "dwi"
    coreg_log = (
        root
        / "coregistration"
        / "log"
        / f"{subject_id}_desc-coregmethod.json"
    )
    paths = {
        "dwi": _select_extension_variant(
            dwi_dir,
            f"{subject_id}_ses-preop_desc-preproc_dwi",
            "preprocessed DWI",
        ),
        "bvec": dwi_dir / f"{subject_id}_ses-preop_desc-preproc_dwi.bvec",
        "bval": dwi_dir / f"{subject_id}_ses-preop_desc-preproc_dwi.bval",
        "b0": _select_ordered_b0(dwi_dir, subject_id),
        "brain_mask": _select_extension_variant(dwi_dir, "brainmask", "DWI brain mask"),
        "tracking_mask": _select_extension_variant(
            dwi_dir, "trackingmask", "DWI tracking mask"
        ),
        "anchor_native_reference": _select_anchor_reference(root, subject_id),
        "target_to_anchor_image_deformation": (
            root
            / "normalization"
            / "transformations"
            / f"{subject_id}_from-{target_space}_to-anchorNative_desc-ants.nii.gz"
        ),
        "anchor_to_target_image_deformation": (
            root
            / "normalization"
            / "transformations"
            / f"{subject_id}_from-anchorNative_to-{target_space}_desc-ants.nii.gz"
        ),
        "coregistration_method_log": coreg_log,
        "normalization_method_log": (
            root
            / "normalization"
            / "log"
            / f"{subject_id}_desc-normmethod.json"
        ),
    }
    return paths


def discover_subject(subject: SubjectSpec, target_space: str) -> ResolvedSubjectInputs:
    """Resolve and validate the exact configured input set for one subject."""

    if not subject.subject_dir.is_dir():
        raise DiscoveryError(f"subject directory does not exist: {subject.subject_dir}")
    paths = _default_paths(subject, target_space)
    paths.update(subject.path_overrides)

    coregistration_method_log = _require_file(
        paths["coregistration_method_log"], "B0 coregistration method log"
    )
    method, method_token, approved = _load_coregistration_method(
        coregistration_method_log
    )
    normalization_method_log = _require_file(
        paths["normalization_method_log"], "normalization method log"
    )
    normalization_method, normalization_approval = _load_normalization_method(
        normalization_method_log
    )
    transform_root = subject.subject_dir / "coregistration" / "transformations"
    paths.setdefault(
        "b0_to_anchor_transform",
        transform_root
        / (
            f"{subject.subject_id}_from-b0_to-anchorNative_"
            f"desc-{method_token}44.mat"
        ),
    )
    paths.setdefault(
        "anchor_to_b0_transform",
        transform_root
        / (
            f"{subject.subject_id}_from-anchorNative_to-b0_"
            f"desc-{method_token}44.mat"
        ),
    )

    resolved = {
        key: _require_file(value, key.replace("_", " "))
        for key, value in paths.items()
    }
    result = ResolvedSubjectInputs(
        subject_id=subject.subject_id,
        subject_dir=subject.subject_dir.resolve(),
        dwi=resolved["dwi"],
        bvec=resolved["bvec"],
        bval=resolved["bval"],
        b0=resolved["b0"],
        brain_mask=resolved["brain_mask"],
        tracking_mask=resolved["tracking_mask"],
        anchor_native_reference=resolved["anchor_native_reference"],
        b0_to_anchor_transform=resolved["b0_to_anchor_transform"],
        anchor_to_b0_transform=resolved["anchor_to_b0_transform"],
        target_to_anchor_image_deformation=resolved[
            "target_to_anchor_image_deformation"
        ],
        anchor_to_target_image_deformation=resolved[
            "anchor_to_target_image_deformation"
        ],
        coregistration_method_log=coregistration_method_log,
        coregistration_method=method,
        coregistration_method_token=method_token,
        coregistration_approved=approved,
        normalization_method_log=normalization_method_log,
        normalization_method=normalization_method,
        normalization_approval=normalization_approval,
        target_space=target_space,
    )
    validate_subject_geometry(result)
    return result


def _load_nifti(path: Path, label: str) -> nib.spatialimages.SpatialImage:
    try:
        image = nib.load(path)
    except Exception as exc:
        raise ValidationError(f"cannot read {label} NIfTI {path}: {exc}") from exc
    if not np.all(np.isfinite(image.affine)) or np.linalg.det(image.affine[:3, :3]) == 0:
        raise ValidationError(f"{label} has an invalid affine: {path}")
    return image


def _read_gradient_count(path: Path, expected_axis: int | None = None) -> int:
    try:
        values = np.loadtxt(path, dtype=np.float64)
    except Exception as exc:
        raise ValidationError(f"cannot read gradient file {path}: {exc}") from exc
    if not np.all(np.isfinite(values)):
        raise ValidationError(f"gradient file contains nonfinite values: {path}")
    if expected_axis == 3:
        if values.ndim != 2 or 3 not in values.shape:
            raise ValidationError(f"bvec must contain a 3 x N or N x 3 matrix: {path}")
        return int(values.shape[1] if values.shape[0] == 3 else values.shape[0])
    return int(values.size)


def load_tmat(path: Path | str) -> np.ndarray:
    """Load and validate the direct world-coordinate `tmat` from a 44.mat file."""

    source = Path(path)
    try:
        document = loadmat(source)
        matrix = np.asarray(document["tmat"], dtype=np.float64)
    except Exception as exc:
        raise ValidationError(f"cannot load tmat from {source}: {exc}") from exc
    if matrix.shape != (4, 4) or not np.all(np.isfinite(matrix)):
        raise ValidationError(f"tmat must be one finite 4 x 4 matrix: {source}")
    if not np.allclose(matrix[3], [0.0, 0.0, 0.0, 1.0], atol=1e-8):
        raise ValidationError(f"tmat has an invalid homogeneous final row: {source}")
    if abs(np.linalg.det(matrix[:3, :3])) < 1e-8:
        raise ValidationError(f"tmat is singular: {source}")
    return matrix


def validate_subject_geometry(subject: ResolvedSubjectInputs) -> None:
    """Validate DWI volumes, gradients, masks, and the selected affine."""

    dwi = _load_nifti(subject.dwi, "DWI")
    b0 = _load_nifti(subject.b0, "native b0")
    brain = _load_nifti(subject.brain_mask, "brain mask")
    tracking = _load_nifti(subject.tracking_mask, "tracking mask")
    anchor = _load_nifti(subject.anchor_native_reference, "anchorNative reference")
    if len(dwi.shape) != 4 or dwi.shape[3] < 2:
        raise ValidationError(f"DWI must be four-dimensional: {subject.dwi}")
    if len(b0.shape) != 3:
        raise ValidationError(f"native b0 must be three-dimensional: {subject.b0}")
    if tuple(dwi.shape[:3]) != tuple(b0.shape):
        raise ValidationError(
            f"DWI and native b0 shapes differ for {subject.subject_id}: "
            f"{dwi.shape[:3]} versus {b0.shape}"
        )
    if not np.allclose(dwi.affine, b0.affine, atol=1e-4, rtol=1e-6):
        raise ValidationError(
            f"DWI and native b0 affines differ materially for {subject.subject_id}"
        )
    for label, image, path in (
        ("brain mask", brain, subject.brain_mask),
        ("tracking mask", tracking, subject.tracking_mask),
    ):
        if len(image.shape) != 3 or tuple(image.shape) != tuple(b0.shape):
            raise ValidationError(f"{label} is not on the native DWI shape: {path}")
        if not np.allclose(image.affine, b0.affine, atol=1e-4, rtol=1e-6):
            raise ValidationError(f"{label} is not on the native DWI affine: {path}")
        data = np.asanyarray(image.dataobj)
        if not np.all(np.isfinite(data)):
            raise ValidationError(f"{label} contains nonfinite values: {path}")
        unique = np.unique(data)
        if unique.size > 2 or not set(float(value) for value in unique).issubset(
            {0.0, 1.0}
        ):
            raise ValidationError(f"{label} must be binary with values 0 and 1: {path}")
        if not np.any(data):
            raise ValidationError(f"{label} is empty: {path}")
    if len(anchor.shape) != 3:
        raise ValidationError(
            f"anchorNative reference must be three-dimensional: {subject.anchor_native_reference}"
        )
    volume_count = int(dwi.shape[3])
    if _read_gradient_count(subject.bvec, expected_axis=3) != volume_count:
        raise ValidationError(
            f"bvec direction count does not match DWI volumes for {subject.subject_id}"
        )
    if _read_gradient_count(subject.bval) != volume_count:
        raise ValidationError(
            f"bval count does not match DWI volumes for {subject.subject_id}"
        )
    load_tmat(subject.b0_to_anchor_transform)
    load_tmat(subject.anchor_to_b0_transform)


def iter_all_roi_paths(seeds: Iterable) -> Iterable[Path]:
    """Yield unique ROI source paths in deterministic first-use order."""

    seen: set[Path] = set()
    for seed in seeds:
        for roi in (seed, *seed.targets):
            path = roi.path.resolve()
            if path not in seen:
                seen.add(path)
                yield path
