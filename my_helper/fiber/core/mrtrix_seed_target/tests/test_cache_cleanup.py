"""Batch-level verified work-cache cleanup tests."""

from __future__ import annotations

from pathlib import Path
import shutil
from types import SimpleNamespace

import numpy as np
import pytest

from .. import cache_cleanup as cleanup_module
from ..cache_cleanup import CACHE_DIRECTORY_NAMES, cleanup_batch_work_caches
from ..errors import PublicationError
from ..identity import file_sha256
from ..publication import OWNER
from ..state import atomic_write_json, read_json
from ..tck import write_selected_tck


def _validation(tmp_path: Path, *, cleanup: bool = True):
    output_root = tmp_path / "mrtrix_seed_target"
    work_root = output_root / "work"
    public = output_root / "tractograms" / "lh" / "Seed" / "seedwide.tck"
    write_selected_tck(
        [np.asarray([[0, 0, 0], [1, 1, 1]], dtype=np.float32)],
        np.asarray([True]),
        public,
    )
    for name in CACHE_DIRECTORY_NAMES:
        directory = work_root / name
        directory.mkdir(parents=True)
        (directory / "cache.bin").write_bytes(name.encode("ascii"))
    configs = work_root / "configs"
    configs.mkdir(parents=True)
    (configs / "resolved.json").write_text("{}\n", encoding="utf-8")
    (work_root / "run.lock").write_text("", encoding="utf-8")
    state = {
        "owner": OWNER,
        "status": "complete",
        "configuration_hash": "configuration",
        "published_artifacts": [
            {
                "path": str(public),
                "sha256": file_sha256(public),
                "streamline_count": 1,
            }
        ],
    }
    atomic_write_json(work_root / "state.json", state)
    subject = SimpleNamespace(subject_id="sub-001", output_root=output_root)
    config = SimpleNamespace(
        configuration_hash="configuration",
        execution=SimpleNamespace(cleanup_work_cache_after_success=cleanup),
    )
    return SimpleNamespace(
        subjects=(subject,),
        config=config,
        tools={
            "tckinfo": SimpleNamespace(executable=Path("/usr/local/bin/tckinfo"))
        },
    )


def test_successful_batch_cleanup_preserves_public_state_and_configs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    validation = _validation(tmp_path)

    def fake_trash(path: str) -> None:
        shutil.rmtree(path)

    monkeypatch.setattr(cleanup_module, "send2trash", fake_trash)
    result = cleanup_batch_work_caches(validation, progress=lambda _message: None)
    work_root = validation.subjects[0].output_root / "work"
    assert result["status"] == "complete"
    assert all(not (work_root / name).exists() for name in CACHE_DIRECTORY_NAMES)
    assert (validation.subjects[0].output_root / "tractograms").is_dir()
    assert (work_root / "state.json").is_file()
    assert (work_root / "configs" / "resolved.json").is_file()
    assert (work_root / "run.lock").is_file()
    state = read_json(work_root / "state.json")
    assert state["status"] == "complete"
    assert state["cache_cleanup"]["status"] == "complete"
    assert len(state["cache_cleanup"]["removed_paths"]) == 4


def test_disabled_cleanup_records_state_without_removing_cache(tmp_path: Path) -> None:
    validation = _validation(tmp_path, cleanup=False)
    result = cleanup_batch_work_caches(validation, progress=lambda _message: None)
    work_root = validation.subjects[0].output_root / "work"
    assert result["status"] == "complete"
    assert all((work_root / name).is_dir() for name in CACHE_DIRECTORY_NAMES)
    assert read_json(work_root / "state.json")["cache_cleanup"]["status"] == "disabled"


def test_incomplete_publication_blocks_cleanup_before_any_move(tmp_path: Path) -> None:
    validation = _validation(tmp_path)
    state_path = validation.subjects[0].output_root / "work" / "state.json"
    state = read_json(state_path)
    state["status"] = "coverage_failed"
    atomic_write_json(state_path, state)
    with pytest.raises(PublicationError, match="incomplete state"):
        cleanup_batch_work_caches(validation, progress=lambda _message: None)
    work_root = state_path.parent
    assert all((work_root / name).is_dir() for name in CACHE_DIRECTORY_NAMES)


def test_trash_failure_is_reported_without_invalidating_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    validation = _validation(tmp_path)

    def fail_trash(_path: str) -> None:
        raise OSError("injected Trash failure")

    monkeypatch.setattr(cleanup_module, "send2trash", fail_trash)
    result = cleanup_batch_work_caches(validation, progress=lambda _message: None)
    state_path = validation.subjects[0].output_root / "work" / "state.json"
    state = read_json(state_path)
    assert result["status"] == "warning"
    assert state["status"] == "complete"
    assert state["cache_cleanup"]["status"] == "warning"
    assert len(state["cache_cleanup"]["pending_paths"]) == 4
