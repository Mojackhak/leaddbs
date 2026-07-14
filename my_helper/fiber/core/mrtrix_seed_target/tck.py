"""Streaming TCK reading, writing, concatenation, and structural validation."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
from typing import Callable, Iterable, Iterator, Sequence

import nibabel as nib
from nibabel.streamlines import LazyTractogram
import numpy as np

from .errors import ToolError, ValidationError


def iter_tck(path: Path | str) -> Iterator[np.ndarray]:
    """Yield one TCK's streamlines in RAS+ world millimetres."""

    try:
        loaded = nib.streamlines.load(path, lazy_load=True)
        yield from loaded.tractogram.streamlines
    except Exception as exc:
        raise ValidationError(f"cannot read TCK {path}: {exc}") from exc


def load_tck_streamlines(path: Path | str) -> list[np.ndarray]:
    """Materialize one generated chunk for one-pass multi-target classification."""

    return [np.asarray(streamline, dtype=np.float32) for streamline in iter_tck(path)]


def _write_lazy_tck(
    output_path: Path,
    generator_factory: Callable[[], Iterable[np.ndarray]],
    expected_count: int,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tractogram = LazyTractogram(
        streamlines=generator_factory,
        affine_to_rasmm=np.eye(4, dtype=np.float64),
    )
    tractogram._nb_streamlines = int(expected_count)
    try:
        nib.streamlines.save(tractogram, output_path)
    except Exception as exc:
        raise ToolError(f"cannot write TCK {output_path}: {exc}") from exc


def write_selected_tck(
    streamlines: Sequence[np.ndarray],
    membership: np.ndarray,
    output_path: Path | str,
) -> int:
    """Write the selected subset of an in-memory chunk without changing coordinates."""

    selected = np.asarray(membership, dtype=bool)
    if selected.ndim != 1 or selected.size != len(streamlines):
        raise ValidationError("target membership length does not match TCK chunk")
    count = int(np.count_nonzero(selected))

    def generate() -> Iterator[np.ndarray]:
        for streamline, include in zip(streamlines, selected, strict=True):
            if include:
                yield streamline

    _write_lazy_tck(Path(output_path), generate, count)
    return count


def write_concatenated_tck(
    input_paths: Sequence[Path | str],
    output_path: Path | str,
    expected_count: int,
) -> None:
    """Stream-concatenate completed TCK chunks into one TCK."""

    resolved = tuple(Path(path) for path in input_paths)

    def generate() -> Iterator[np.ndarray]:
        for path in resolved:
            yield from iter_tck(path)

    _write_lazy_tck(Path(output_path), generate, expected_count)


def nibabel_tck_count(path: Path | str) -> int:
    """Count streamlines through a lazy Nibabel structural read."""

    count = 0
    for streamline in iter_tck(path):
        points = np.asarray(streamline)
        if points.ndim != 2 or points.shape[1] != 3 or points.shape[0] < 2:
            raise ValidationError(f"TCK contains an invalid streamline: {path}")
        if not np.all(np.isfinite(points)):
            raise ValidationError(f"TCK contains nonfinite coordinates: {path}")
        count += 1
    return count


def tckinfo_count(path: Path | str, executable: Path | str) -> int:
    """Require MRtrix to parse the TCK and report a nonnegative count."""

    try:
        result = subprocess.run(
            [str(executable), str(path), "-count"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ToolError(f"cannot validate TCK {path} with tckinfo: {exc}") from exc
    if result.returncode != 0:
        raise ToolError(
            f"tckinfo rejected {path} with exit {result.returncode}: {result.stdout.strip()}"
        )
    matches = re.findall(r"(?:^|\s)count\s*:\s*(\d+)", result.stdout, flags=re.IGNORECASE)
    if not matches:
        matches = re.findall(r"(?:^|\s)(\d+)\s*$", result.stdout, flags=re.MULTILINE)
    if not matches:
        raise ToolError(f"cannot parse streamline count from tckinfo output for {path}")
    return int(matches[-1])


def validate_tck(
    path: Path | str,
    executable: Path | str,
    *,
    expected_count: int | None = None,
    full_coordinate_check: bool = False,
) -> int:
    """Validate one TCK with MRtrix and optionally an independent full read."""

    source = Path(path)
    if not source.is_file() or source.stat().st_size <= 0:
        raise ValidationError(f"TCK is missing or empty on disk: {source}")
    count = tckinfo_count(source, executable)
    if count < 0:
        raise ValidationError(f"TCK has a negative count: {source}")
    if expected_count is not None and count != expected_count:
        raise ValidationError(
            f"TCK count mismatch for {source}: expected {expected_count}, found {count}"
        )
    if full_coordinate_check:
        independent = nibabel_tck_count(source)
        if independent != count:
            raise ValidationError(
                f"Nibabel and tckinfo counts differ for {source}: {independent} versus {count}"
            )
    return count
