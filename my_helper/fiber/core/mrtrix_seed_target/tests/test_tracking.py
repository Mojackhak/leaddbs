"""Multi-target classification, TCK, RNG, and global stopping tests."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from ..classification import build_target_lookup, classify_streamlines
from ..config import resolve_config
from ..tck import validate_tck, write_concatenated_tck, write_selected_tck
from ..tracking import (
    build_tckgen_command,
    coverage_complete,
    derive_chunk_rng_seed,
    generation_complete,
    next_chunk_request,
    source_tracking_mask_path,
)
from .helpers import minimal_document, write_nifti


def test_one_pass_classification_deduplicates_and_allows_multi_target_hits(
    tmp_path: Path,
) -> None:
    first = np.zeros((6, 6, 6), dtype=np.uint8)
    second = np.zeros_like(first)
    first[2, 2, 2] = 1
    second[3, 2, 2] = 1
    first_path = write_nifti(tmp_path / "first.nii.gz", first)
    second_path = write_nifti(tmp_path / "second.nii.gz", second)
    lookup = build_target_lookup(["first", "second"], [first_path, second_path])
    streamlines = [
        np.asarray([[0.0, 2.0, 2.0], [4.0, 2.0, 2.0], [0.0, 2.0, 2.0]]),
        np.asarray([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]),
    ]
    membership = classify_streamlines(streamlines, lookup)
    assert membership.tolist() == [[True, True], [False, False]]
    assert membership.sum(axis=0).tolist() == [1, 1]


def test_tck_subset_empty_and_concatenation_are_structurally_valid(tmp_path: Path) -> None:
    streamlines = [
        np.asarray([[0, 0, 0], [1, 1, 1]], dtype=np.float32),
        np.asarray([[1, 0, 0], [2, 1, 1]], dtype=np.float32),
    ]
    one = tmp_path / "one.tck"
    empty = tmp_path / "empty.tck"
    assert write_selected_tck(streamlines, np.asarray([True, False]), one) == 1
    assert write_selected_tck(streamlines, np.asarray([False, False]), empty) == 0
    tckinfo = Path("/usr/local/bin/tckinfo")
    assert validate_tck(one, tckinfo, expected_count=1, full_coordinate_check=True) == 1
    assert validate_tck(empty, tckinfo, expected_count=0) == 0
    concatenated = tmp_path / "concatenated.tck"
    write_concatenated_tck([one, one], concatenated, 2)
    assert validate_tck(
        concatenated, tckinfo, expected_count=2, full_coordinate_check=True
    ) == 2


def test_command_is_seedwide_and_rng_is_chunk_distinct(tmp_path: Path) -> None:
    config = resolve_config(
        minimal_document(tmp_path), source_path=tmp_path / "config.yaml"
    )
    command = build_tckgen_command(
        Path("/usr/local/bin/tckgen"),
        tmp_path / "fod.mif",
        tmp_path / "out.tck",
        tmp_path / "seed.nii.gz",
        tmp_path / "mask.mif",
        config,
        50_000,
    )
    assert "-include" not in command
    assert "-stop" not in command
    assert "-seeds" not in command
    assert command[command.index("-select") + 1] == "50000"
    seeds = {
        derive_chunk_rng_seed(1, "identity", "sub-001", "lh/Seed", index)
        for index in range(10)
    }
    assert len(seeds) == 10
    assert all(1 <= value <= 2_147_483_646 for value in seeds)


def test_global_coverage_and_exact_final_chunk_request() -> None:
    assert not coverage_complete([12_450, 299, 537], 300)
    assert coverage_complete([12_450, 300, 537], 300)
    assert next_chunk_request(0, 50_000, 100_000_000) == 50_000
    assert next_chunk_request(99_980_000, 50_000, 100_000_000) == 20_000
    assert next_chunk_request(100_000_000, 50_000, 100_000_000) == 0


def test_fixed_sampling_ignores_early_coverage_and_stops_at_exact_total() -> None:
    assert not generation_complete(50_000, [2_000, 1_000], 300, 300_000)
    assert generation_complete(300_000, [2_000, 1_000], 300, 300_000)
    assert generation_complete(300_000, [2_000, 299], 300, 300_000)
    assert not generation_complete(50_000, [2_000, 299], 300, None)
    assert generation_complete(50_000, [2_000, 300], 300, None)
    assert next_chunk_request(250_000, 50_000, 300_000) == 50_000
    assert next_chunk_request(300_000, 50_000, 300_000) == 0


def test_tracking_uses_validated_source_nifti_instead_of_redundant_mif(
    tmp_path: Path,
) -> None:
    source = tmp_path / "trackingmask.nii"
    source.write_bytes(b"mask")
    preparation = {
        "identity_document": {
            "inputs": {
                "tracking_mask": {
                    "path": str(source),
                    "sha256": hashlib.sha256(b"mask").hexdigest(),
                }
            }
        }
    }
    assert source_tracking_mask_path(preparation) == source
