"""Native fast-path and target-space resume orchestration tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from .. import pipeline
from ..config import resolve_config
from .helpers import minimal_document
from .test_publication import _resolved_subject


def test_subject_visualization_stages_are_process_serialized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observer_lock = threading.Lock()
    active_calls = 0
    maximum_active_calls = 0

    def observed_visualization(**kwargs):
        nonlocal active_calls, maximum_active_calls
        with observer_lock:
            active_calls += 1
            maximum_active_calls = max(maximum_active_calls, active_calls)
        time.sleep(0.01)
        with observer_lock:
            active_calls -= 1
        return {"subject_id": kwargs["subject"].subject_id}

    monkeypatch.setattr(
        pipeline,
        "generate_subject_visualizations",
        observed_visualization,
    )

    def run(index: int):
        return pipeline._generate_subject_visualizations_serialized(
            subject=SimpleNamespace(subject_id=f"sub-{index:03d}")
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(run, range(4)))
    assert [result["subject_id"] for result in results] == [
        "sub-000",
        "sub-001",
        "sub-002",
        "sub-003",
    ]
    assert maximum_active_calls == 1


def test_native_complete_fast_path_never_enters_native_producers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = minimal_document(tmp_path)
    document["subjects"][0]["subject_dir"] = str(tmp_path / "sub-001")
    config = resolve_config(document, source_path=tmp_path / "config.yaml")
    subject = _resolved_subject(tmp_path / "sub-001")
    validation = SimpleNamespace(
        config=config,
        tools={
            "tckinfo": SimpleNamespace(executable=Path("/tmp/tckinfo")),
            "antsApplyTransformsToPoints": SimpleNamespace(
                executable=Path("/tmp/antsApplyTransformsToPoints"),
                version="test",
            ),
            "matlab": SimpleNamespace(
                executable=Path("/tmp/matlab"),
                version="test",
            ),
        },
        space_conversion_code_hash="space-code",
        visualization_code_hash="visualization-code",
    )
    monkeypatch.setattr(pipeline, "verify_native_publication", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        pipeline,
        "convert_subject_target_space",
        lambda **_kwargs: {
            "status": "target_space_complete",
            "subject_id": subject.subject_id,
        },
    )
    monkeypatch.setattr(
        pipeline,
        "generate_subject_visualizations",
        lambda **_kwargs: {
            "status": "complete",
            "subject_id": subject.subject_id,
            "generated_scenes": 0,
            "reused_scenes": 2,
        },
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("native producer or publication was called")

    monkeypatch.setattr(pipeline, "prepare_subject", forbidden)
    monkeypatch.setattr(pipeline, "run_seedwide", forbidden)
    monkeypatch.setattr(pipeline, "publish_subject", forbidden)
    result = pipeline._process_subject(
        validation,
        subject,
        resources=SimpleNamespace(),
        repo_root=tmp_path,
        progress=lambda _message: None,
    )
    assert result == {
        "status": "complete",
        "subject_id": "sub-001",
        "generated_scenes": 0,
        "reused_scenes": 2,
        "native_action": "reused",
    }
