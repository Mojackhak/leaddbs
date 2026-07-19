"""Run-scoped read-only memmap generations for formal fold operators."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import uuid
from collections.abc import Mapping

import numpy as np


OPERATOR_SCRATCH_SCHEMA = "dual_frequency_formal_operator_scratch_v1"
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


class OperatorScratchError(RuntimeError):
    """Raised when an operator generation is unsafe, missing, or inconsistent."""


@dataclass(frozen=True, slots=True)
class ScratchArrayDescriptor:
    """Structural identity for one NPY payload in an operator generation."""

    name: str
    filename: str
    dtype: str
    shape: tuple[int, ...]
    fortran_order: bool
    nbytes: int

    def __post_init__(self) -> None:
        name = str(self.name).strip().lower()
        if _NAME.fullmatch(name) is None:
            raise OperatorScratchError("scratch array name is not canonical")
        filename = str(self.filename).strip()
        path = Path(filename)
        if (
            not filename
            or path.name != filename
            or path.suffix != ".npy"
            or path.is_absolute()
        ):
            raise OperatorScratchError("scratch array filename is unsafe")
        try:
            dtype = np.dtype(self.dtype)
        except TypeError as error:
            raise OperatorScratchError("scratch array dtype is invalid") from error
        shape = tuple(self.shape)
        if not shape or any(type(value) is not int or value < 1 for value in shape):
            raise OperatorScratchError("scratch array shape is invalid")
        expected_nbytes = int(np.prod(shape, dtype=np.int64)) * dtype.itemsize
        if type(self.fortran_order) is not bool:
            raise OperatorScratchError("scratch array order flag is invalid")
        if type(self.nbytes) is not int or self.nbytes != expected_nbytes:
            raise OperatorScratchError("scratch array byte count is inconsistent")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "filename", filename)
        object.__setattr__(self, "dtype", dtype.name)
        object.__setattr__(self, "shape", shape)


@dataclass(frozen=True, slots=True)
class FormalOperatorScratchDescriptor:
    """Small picklable descriptor for one exclusive read-only generation."""

    schema_version: str
    model_family: str
    root: Path
    arrays: tuple[ScratchArrayDescriptor, ...]

    def __post_init__(self) -> None:
        if self.schema_version != OPERATOR_SCRATCH_SCHEMA:
            raise OperatorScratchError("operator scratch schema is unsupported")
        family = str(self.model_family).strip().lower()
        if family not in {"direct_voxel", "normative_fiber"}:
            raise OperatorScratchError("operator scratch model family is unsupported")
        root = Path(self.root).expanduser().resolve()
        arrays = tuple(self.arrays)
        if not arrays or not all(
            isinstance(item, ScratchArrayDescriptor) for item in arrays
        ):
            raise OperatorScratchError("operator scratch arrays are invalid")
        if len({item.name for item in arrays}) != len(arrays):
            raise OperatorScratchError("operator scratch array names are duplicated")
        if len({item.filename for item in arrays}) != len(arrays):
            raise OperatorScratchError("operator scratch filenames are duplicated")
        object.__setattr__(self, "model_family", family)
        object.__setattr__(self, "root", root)
        object.__setattr__(self, "arrays", arrays)


def _close_memmap(array: np.ndarray) -> None:
    mapping = getattr(array, "_mmap", None)
    if mapping is not None:
        mapping.close()


def _publish_operator_scratch(
    parent: Path,
    model_family: str,
    arrays: Mapping[str, np.ndarray],
) -> FormalOperatorScratchDescriptor:
    """Atomically publish one exclusive generation without replacing files."""

    parent = Path(parent).expanduser().resolve()
    parent.mkdir(parents=True, exist_ok=True)
    generation = parent / f"operator-generation-{uuid.uuid4().hex}"
    generation.mkdir(exist_ok=False)
    descriptors: list[ScratchArrayDescriptor] = []
    created: list[Path] = []
    temporary: list[Path] = []
    try:
        for index, (raw_name, raw_value) in enumerate(sorted(arrays.items())):
            name = str(raw_name).strip().lower()
            if _NAME.fullmatch(name) is None:
                raise OperatorScratchError("scratch array name is not canonical")
            value = np.asarray(raw_value)
            if value.dtype == object or value.ndim < 1 or any(
                dimension < 1 for dimension in value.shape
            ):
                raise OperatorScratchError("scratch array payload is invalid")
            filename = f"{index:02d}_{name}.npy"
            final_path = generation / filename
            temporary_path = generation / f".{filename}.{uuid.uuid4().hex}.tmp.npy"
            temporary.append(temporary_path)
            fortran_order = bool(
                value.flags.f_contiguous and not value.flags.c_contiguous
            )
            output = np.lib.format.open_memmap(
                temporary_path,
                mode="w+",
                dtype=value.dtype,
                shape=value.shape,
                fortran_order=fortran_order,
            )
            try:
                output[...] = value
                output.flush()
            finally:
                _close_memmap(output)
            if final_path.exists():
                raise OperatorScratchError("operator scratch publication would overwrite")
            os.replace(temporary_path, final_path)
            temporary.remove(temporary_path)
            created.append(final_path)
            final_path.chmod(0o444)
            descriptors.append(
                ScratchArrayDescriptor(
                    name=name,
                    filename=filename,
                    dtype=value.dtype.name,
                    shape=tuple(int(item) for item in value.shape),
                    fortran_order=fortran_order,
                    nbytes=int(value.nbytes),
                )
            )
        return FormalOperatorScratchDescriptor(
            schema_version=OPERATOR_SCRATCH_SCHEMA,
            model_family=model_family,
            root=generation,
            arrays=tuple(descriptors),
        )
    except Exception:
        for path in (*temporary, *created):
            path.unlink(missing_ok=True)
        try:
            generation.rmdir()
        except OSError:
            pass
        raise


def open_operator_scratch(
    descriptor: FormalOperatorScratchDescriptor,
) -> dict[str, np.memmap]:
    """Validate and reopen a complete generation as read-only NPY memmaps."""

    if not isinstance(descriptor, FormalOperatorScratchDescriptor):
        raise OperatorScratchError("operator scratch descriptor is invalid")
    root = descriptor.root.resolve()
    if not root.is_dir():
        raise OperatorScratchError("operator scratch generation is missing")
    output: dict[str, np.memmap] = {}
    try:
        for item in descriptor.arrays:
            path = (root / item.filename).resolve()
            if path.parent != root or not path.is_file():
                raise OperatorScratchError("operator scratch array is missing or unsafe")
            try:
                value = np.load(path, mmap_mode="r", allow_pickle=False)
            except (OSError, ValueError) as error:
                raise OperatorScratchError(
                    "operator scratch array cannot be reopened"
                ) from error
            if not isinstance(value, np.memmap):
                raise OperatorScratchError("operator scratch array is not memory mapped")
            if (
                value.dtype.name != item.dtype
                or value.shape != item.shape
                or int(value.nbytes) != item.nbytes
                or bool(value.flags.f_contiguous and not value.flags.c_contiguous)
                != item.fortran_order
                or value.flags.writeable
            ):
                _close_memmap(value)
                raise OperatorScratchError(
                    "operator scratch array does not match its descriptor"
                )
            output[item.name] = value
        return output
    except Exception:
        close_operator_scratch(output)
        raise


def close_operator_scratch(arrays: Mapping[str, np.ndarray]) -> None:
    """Close every distinct memmap owned by one reopened generation."""

    seen: set[int] = set()
    for value in arrays.values():
        mapping = getattr(value, "_mmap", None)
        if mapping is None or id(mapping) in seen:
            continue
        seen.add(id(mapping))
        mapping.close()


def cleanup_operator_scratch(
    descriptor: FormalOperatorScratchDescriptor,
) -> None:
    """Remove only descriptor-listed files and one otherwise-empty generation."""

    if not isinstance(descriptor, FormalOperatorScratchDescriptor):
        raise OperatorScratchError("operator scratch descriptor is invalid")
    root = descriptor.root.resolve()
    if not root.is_dir():
        return
    paths = tuple((root / item.filename).resolve() for item in descriptor.arrays)
    if any(path.parent != root for path in paths):
        raise OperatorScratchError("operator scratch cleanup path is unsafe")
    expected_names = {path.name for path in paths}
    actual_names = {path.name for path in root.iterdir()}
    unexpected = actual_names - expected_names
    if unexpected:
        raise OperatorScratchError(
            "operator scratch generation contains untracked files"
        )
    for path in paths:
        path.unlink(missing_ok=True)
    root.rmdir()


__all__ = [
    "FormalOperatorScratchDescriptor",
    "OPERATOR_SCRATCH_SCHEMA",
    "OperatorScratchError",
    "ScratchArrayDescriptor",
    "cleanup_operator_scratch",
    "close_operator_scratch",
    "open_operator_scratch",
]
