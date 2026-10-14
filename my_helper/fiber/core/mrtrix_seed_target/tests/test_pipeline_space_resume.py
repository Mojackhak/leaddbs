"""Native fast-path and target-space resume orchestration tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from pathlib import Path
import threading
import time
import sys
from types import SimpleNamespace

import pytest

from .. import pipeline
from ..config import resolve_config
from ..errors import ValidationError
from .helpers import minimal_document
from .test_publication import _resolved_subject, _seed_result


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


@pytest.mark.parametrize("native_only", [False, True])
def test_native_complete_fast_path_never_enters_native_producers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    native_only: bool,
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
    monkeypatch.setattr(pipeline, "preparation_identity", lambda *_args: ("fod", {}))
    monkeypatch.setattr(pipeline, "roi_transform_inputs", lambda *_args: {})
    monkeypatch.setattr(pipeline, "native_request_identity", lambda *_args: "native-request")
    monkeypatch.setattr(pipeline, "verify_native_publication", lambda *_args, **_kwargs: {
        "native_request_identity": "native-request", "status": "transform_domain_failed"})
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
    if native_only:
        monkeypatch.setattr(pipeline, "convert_subject_target_space", forbidden)
        monkeypatch.setattr(pipeline, "generate_subject_visualizations", forbidden)
    result = pipeline._process_subject(
        validation,
        subject,
        resources=SimpleNamespace(),
        repo_root=tmp_path,
        progress=lambda _message: None,
        native_only=native_only,
    )
    assert result == ({
        "status": "native_complete",
        "subject_id": subject.subject_id,
        "native_action": "reused",
        "downstream_status": "transform_domain_failed",
    } if native_only else {
        "status": "complete",
        "subject_id": "sub-001",
        "generated_scenes": 0,
        "reused_scenes": 2,
        "native_action": "reused",
    })


def test_native_generation_publishes_without_mni_or_visualization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = resolve_config(minimal_document(tmp_path), source_path=tmp_path / "config.yaml")
    subject = _resolved_subject(tmp_path / "sub-001")
    validation = SimpleNamespace(config=config, tools={
        "tckinfo": SimpleNamespace(executable=Path("/usr/local/bin/tckinfo")),
    }, tracking_code_hash="tracking")
    monkeypatch.setattr(pipeline, "preparation_identity", lambda *_: ("fod", {}))
    monkeypatch.setattr(pipeline, "roi_transform_inputs", lambda *_: {})
    monkeypatch.setattr(pipeline, "native_request_identity", lambda *_: "native-request")

    def no_publication(*args, **kwargs):
        raise ValidationError("native publication is absent")

    monkeypatch.setattr(pipeline, "verify_native_publication", no_publication)
    monkeypatch.setattr(pipeline, "prepare_subject", lambda *a, **kw: ({}, "reused"))
    result = {**_seed_result(tmp_path), "action": "generated"}
    monkeypatch.setattr(pipeline, "run_seedwide", lambda **kw: result)
    monkeypatch.setattr(pipeline, "_run_provenance", lambda *_: {})
    publications = []

    def publish(**kwargs):
        publications.append(kwargs)
        return {"status": "native_complete", "subject_id": subject.subject_id}

    def forbidden(**kwargs):
        raise AssertionError("deferred downstream stage was called")

    monkeypatch.setattr(pipeline, "publish_subject", publish)
    monkeypatch.setattr(pipeline, "convert_subject_target_space", forbidden)
    monkeypatch.setattr(pipeline, "generate_subject_visualizations", forbidden)
    resources = SimpleNamespace(reserve=lambda *a, **kw: nullcontext(
        SimpleNamespace(observe_memory_gb=lambda *_: None)))
    outcome = pipeline._process_subject(validation, subject, resources, tmp_path,
                                        lambda _: None, native_only=True)
    assert outcome["status"] == "native_complete"
    assert outcome["preparation_action"] == "reused"
    assert publications[0]["preparation"]["native_request_identity"] == "native-request"
    assert publications[0]["seed_results"]["lh/Seed"] is result


@pytest.mark.parametrize("failed_subjects", [0, 1])
@pytest.mark.parametrize("native_only", [False, True])
def test_batch_counts_scoped_success_and_gates_cache_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failed_subjects: int,
    native_only: bool,
) -> None:
    config = resolve_config(minimal_document(tmp_path, subject_count=2),
                            source_path=tmp_path / "config.yaml")
    subjects = [SimpleNamespace(subject_id=s.subject_id) for s in config.subjects]
    validation = SimpleNamespace(config=config, subjects=subjects, warnings=())
    requested_scope = native_only
    success_status = "native_complete" if native_only else "complete"
    def validate(path, *, native_only):
        assert native_only is requested_scope
        return validation

    def process(validation, subject, *args, native_only):
        assert native_only is requested_scope
        if failed_subjects and subject is subjects[1]:
            raise ValidationError("native test failure")
        return {"status": success_status, "subject_id": subject.subject_id}

    def forbidden(*args, **kwargs):
        raise AssertionError("work cache cleanup was called before full completion")

    monkeypatch.setattr(pipeline, "validate_config", validate)
    monkeypatch.setattr(pipeline, "_process_subject", process)
    monkeypatch.setattr(pipeline, "_run_provenance", lambda *_: {})
    if native_only or failed_subjects:
        monkeypatch.setattr(pipeline, "cleanup_batch_work_caches", forbidden)
    else:
        monkeypatch.setattr(pipeline, "cleanup_batch_work_caches", lambda *a, **kw: {
            "status": "complete", "warnings": [],
            "subjects": [{"subject_id": s.subject_id} for s in subjects]})
    result = pipeline.run_batch(tmp_path / "config.yaml", native_only=native_only, progress=lambda _: None)
    assert result["status"] == ("partial_failure" if failed_subjects else success_status)
    assert result["completed_subjects"] == 2 - failed_subjects
    assert result["failed_subjects"] == failed_subjects
    assert result["execution_scope"] == ("native" if native_only else "full")
    assert result["deferred_stages"] == (["target_space", "visualization"] if native_only else [])
    assert result["cache_cleanup"]["status"] == (
        "not_run_native_only" if native_only
        else "not_run_batch_incomplete" if failed_subjects else "complete")


def test_native_tool_resolution_does_not_probe_point_transform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from .. import tools

    document = minimal_document(tmp_path)
    document["execution"]["matlab_executable"] = sys.executable
    config = resolve_config(document, source_path=tmp_path / "config.yaml")
    monkeypatch.setattr(tools, "_resolve_executable", lambda *a: Path("/bin/true"))
    monkeypatch.setattr(tools, "_version", lambda *a: "test")

    def forbidden(*args, **kwargs):
        raise AssertionError("point-transform executable was probed")

    monkeypatch.setattr(tools.platform, "system", forbidden)
    identities = tools.resolve_tool_identities(config, include_point_transform=False)
    assert set(identities) == {*tools.MRTRIX_TOOLS, "matlab"}
