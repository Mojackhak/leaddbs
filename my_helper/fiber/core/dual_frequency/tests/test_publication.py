"""Canonical publication transaction and replay boundary tests."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import yaml

import dual_frequency.application.publication as publication_module
from dual_frequency.application.publication import (
    CanonicalPublisher,
    PublicationError,
    _PublicationWriter,
    _masked_normalized_gaussian_original_roi,
)
from dual_frequency.contracts import (
    ActivationArtifact,
    ArtifactRef,
    AxisRef,
    EndpointInputRecord,
    EndpointKey,
    FeatureAxisRef,
    FinalModelKey,
    FinalModelRecord,
    FinalSelectionRecord,
    IndexedArrayView,
    SensitivityResult,
    SourceRecord,
)
from dual_frequency.workflow import ServiceResult, TaskOutcome


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact(path: Path) -> ArtifactRef:
    axis = AxisRef("axis-test", 3, "a" * 64)
    return ArtifactRef(
        kind="test_array",
        schema_version="dual_frequency_array_v1",
        uri=path.resolve().as_uri(),
        sha256=_sha256(path),
        dtype="float32",
        shape=(3,),
        axis_refs=(axis,),
        axis_hashes=(axis.sha256,),
        units="coefficient",
        space="MNI152NLin2009bAsym",
        producer_id="task-test",
        producer_version="1",
    )


def test_masked_normalized_gaussian_preserves_original_finite_roi() -> None:
    values = np.zeros((9, 9, 9), dtype=np.float32)
    finite_mask = np.zeros(values.shape, dtype=np.float32)
    finite_mask[4, 4, 3:6] = 1.0
    values[4, 4, 3:6] = np.asarray([-1.0, 0.5, 2.0], dtype=np.float32)

    smoothed = _masked_normalized_gaussian_original_roi(
        values,
        finite_mask,
        np.asarray([1.0, 1.0, 1.0], dtype=float),
    )

    original_roi = finite_mask.astype(bool)
    assert np.array_equal(np.isfinite(smoothed), original_roi)
    assert np.all(np.isnan(smoothed[~original_roi]))
    assert not np.allclose(smoothed[original_roi], values[original_roi])


def test_canonical_publisher_materializes_verified_indexed_view(
    tmp_path: Path,
) -> None:
    parent_axis = AxisRef("parent-rows", 3, "1" * 64)
    feature_axis = AxisRef("parent-columns", 4, "2" * 64)
    selected_axis = AxisRef("selected-columns", 2, "3" * 64)
    parent_values = np.arange(12, dtype=np.float32).reshape(3, 4)
    parent_path = tmp_path / "parent.npy"
    positions_path = tmp_path / "positions.npy"
    np.save(parent_path, parent_values, allow_pickle=False)
    np.save(
        positions_path,
        np.asarray([3, 1], dtype=np.int64),
        allow_pickle=False,
    )

    def artifact(
        path: Path,
        *,
        kind: str,
        dtype: str,
        axes: tuple[AxisRef, ...],
        units: str | None,
        space: str | None,
    ) -> ArtifactRef:
        return ArtifactRef(
            kind=kind,
            schema_version="dual_frequency_array_v1",
            uri=path.as_uri(),
            sha256=_sha256(path),
            dtype=dtype,
            shape=tuple(axis.count for axis in axes),
            axis_refs=axes,
            axis_hashes=tuple(axis.sha256 for axis in axes),
            units=units,
            space=space,
            producer_id="publication_test",
            producer_version="1",
        )

    parent = artifact(
        parent_path,
        kind="shared_physical_exposure",
        dtype="float32",
        axes=(parent_axis, feature_axis),
        units="V/m",
        space="synthetic",
    )
    positions = artifact(
        positions_path,
        kind="indexed_array_column_positions",
        dtype="int64",
        axes=(selected_axis,),
        units="index",
        space=None,
    )
    view = IndexedArrayView(
        parent=parent,
        row_positions=None,
        column_positions=positions,
        axis_refs=(parent_axis, selected_axis),
    )
    output = CanonicalPublisher()._materialize_scientific_array(view)
    np.testing.assert_array_equal(output, parent_values[:, [3, 1]])
    assert not output.flags.writeable


def test_writer_copies_verified_payload_without_persisting_run_uri(tmp_path: Path) -> None:
    source = tmp_path / ".runs" / "work" / "source.npy"
    source.parent.mkdir(parents=True)
    np.save(source, np.asarray([1.0, 2.0, 3.0], dtype=np.float32))
    publication = tmp_path / "publication"
    writer = _PublicationWriter(publication, domain="direct_voxel")
    reference = _artifact(source)
    context = {
        "scale_id": "scale_a",
        "model_family": "reference",
        "stage": "resolver",
    }

    writer.artifact(
        "scale_a/reference/resolver/full_weights.npy",
        reference,
        artifact_kind="full_weights",
        context=context,
    )
    writer.artifact(
        "scale_a/reference/resolver/full_weights.npy",
        reference,
        artifact_kind="full_weights",
        context=context,
    )
    writer.write_index()

    target = publication / "scale_a/reference/resolver/full_weights.npy"
    metadata_path = Path(f"{target}.metadata.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    with (publication / "artifact_index.csv").open(
        "r", encoding="utf-8", newline=""
    ) as handle:
        rows = list(csv.DictReader(handle))

    assert target.read_bytes() == source.read_bytes()
    assert "uri" not in metadata["source_artifact"]
    assert ".runs" not in metadata_path.read_text(encoding="utf-8")
    assert rows[0]["relative_path"] == "scale_a/reference/resolver/full_weights.npy"
    assert rows[0]["sha256"] == _sha256(target)
    assert int(rows[0]["size_bytes"]) == target.stat().st_size
    assert rows[0]["status"] == "completed"


def test_writer_rejects_immutable_collision(tmp_path: Path) -> None:
    publication = tmp_path / "publication"
    writer = _PublicationWriter(publication, domain="direct_voxel")
    context = {"stage": "configuration"}
    writer.bytes(
        "resolved.yaml",
        b"first\n",
        artifact_kind="resolved_model_profile",
        context=context,
    )

    with pytest.raises(PublicationError, match="immutable publication collision"):
        writer.bytes(
            "resolved.yaml",
            b"second\n",
            artifact_kind="resolved_model_profile",
            context=context,
        )


def test_new_in_memory_payload_reuses_digest_without_fsync_or_reread(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publication = tmp_path / "publication"
    writer = _PublicationWriter(publication, domain="direct_voxel")

    def reject_fsync(_descriptor: int) -> None:
        raise AssertionError("publication must not issue a per-artifact fsync")

    def reject_reread(_path: Path) -> str:
        raise AssertionError("new in-memory payload must reuse its verified digest")

    monkeypatch.setattr(publication_module.os, "fsync", reject_fsync)
    monkeypatch.setattr(publication_module, "_sha256_file", reject_reread)
    writer.bytes(
        "resolved.yaml",
        b"payload\n",
        artifact_kind="resolved_model_profile",
        context={"stage": "configuration"},
    )

    expected = hashlib.sha256(b"payload\n").hexdigest()
    assert writer.rows["resolved.yaml"]["sha256"] == expected
    assert writer.rows["resolved.yaml"]["size_bytes"] == len(b"payload\n")


def test_copied_payload_hashes_temporary_once_and_reuses_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.npy"
    np.save(source, np.asarray([1.0, 2.0, 3.0], dtype=np.float32))
    reference = _artifact(source)
    publication = tmp_path / "publication"
    writer = _PublicationWriter(publication, domain="direct_voxel")
    original_sha256_file = publication_module._sha256_file
    checked_paths: list[Path] = []

    def track_sha256(path: Path) -> str:
        checked_paths.append(Path(path))
        return original_sha256_file(path)

    monkeypatch.setattr(publication_module, "_sha256_file", track_sha256)
    writer.artifact(
        "scale_a/reference/resolver/full_weights.npy",
        reference,
        artifact_kind="full_weights",
        context={"scale_id": "scale_a", "stage": "resolver"},
    )

    target = publication / "scale_a/reference/resolver/full_weights.npy"
    assert checked_paths[0] == source
    assert len(checked_paths) == 2
    assert checked_paths[1].parent == target.parent
    assert checked_paths[1] != target
    assert target not in checked_paths
    assert writer.rows[
        "scale_a/reference/resolver/full_weights.npy"
    ]["sha256"] == reference.sha256


def test_publisher_verifies_each_source_path_once_per_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.npy"
    np.save(source, np.asarray([1.0, 2.0, 3.0], dtype=np.float32))
    reference = _artifact(source)
    publisher = CanonicalPublisher()
    original_sha256_file = publication_module._sha256_file
    original_artifact_location = publication_module._artifact_location
    checked_paths: list[Path] = []
    resolved_uris: list[str] = []

    def track_sha256(path: Path) -> str:
        checked_paths.append(Path(path))
        return original_sha256_file(path)

    def track_artifact_location(artifact: ArtifactRef) -> Path:
        resolved_uris.append(artifact.uri)
        return original_artifact_location(artifact)

    monkeypatch.setattr(publication_module, "_sha256_file", track_sha256)
    monkeypatch.setattr(
        publication_module, "_artifact_location", track_artifact_location
    )
    assert publisher._artifact_path(reference) == source.resolve()
    assert publisher._artifact_path(reference) == source.resolve()

    assert checked_paths == [source.resolve()]
    assert resolved_uris == [reference.uri]


def test_publisher_rejects_missing_source_payload(tmp_path: Path) -> None:
    source = tmp_path / "source.npy"
    np.save(source, np.asarray([1.0, 2.0, 3.0], dtype=np.float32))
    reference = _artifact(source)
    source.unlink()

    with pytest.raises(PublicationError, match="source artifact is missing"):
        CanonicalPublisher()._artifact_path(reference)


def test_publisher_rejects_changed_digest_without_rereading_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.npy"
    np.save(source, np.asarray([1.0, 2.0, 3.0], dtype=np.float32))
    reference = _artifact(source)
    publisher = CanonicalPublisher()
    original_sha256_file = publication_module._sha256_file
    checks = 0

    def track_sha256(path: Path) -> str:
        nonlocal checks
        checks += 1
        return original_sha256_file(path)

    monkeypatch.setattr(publication_module, "_sha256_file", track_sha256)
    publisher._artifact_path(reference)
    changed = ArtifactRef(
        kind=reference.kind,
        schema_version=reference.schema_version,
        uri=reference.uri,
        sha256="b" * 64,
        dtype=reference.dtype,
        shape=reference.shape,
        axis_refs=reference.axis_refs,
        axis_hashes=reference.axis_hashes,
        units=reference.units,
        space=reference.space,
        producer_id=reference.producer_id,
        producer_version=reference.producer_version,
    )

    with pytest.raises(PublicationError, match="SHA-256 mismatch"):
        publisher._artifact_path(changed)

    assert checks == 1


def test_writer_resolves_each_destination_parent_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publication = tmp_path / "publication"
    writer = _PublicationWriter(publication, domain="direct_voxel")
    original_resolve = Path.resolve
    resolved_paths: list[Path] = []

    def track_resolve(path: Path, *args: object, **kwargs: object) -> Path:
        resolved_paths.append(path)
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", track_resolve)
    writer.bytes(
        "scale_a/reference/first.json",
        b"first\n",
        artifact_kind="first",
        context={"scale_id": "scale_a"},
    )
    writer.bytes(
        "scale_a/reference/second.json",
        b"second\n",
        artifact_kind="second",
        context={"scale_id": "scale_a"},
    )

    assert resolved_paths == [publication / "scale_a/reference"]


def test_writer_rejects_destination_parent_symlink_escape(tmp_path: Path) -> None:
    publication = tmp_path / "publication"
    outside = tmp_path / "outside"
    outside.mkdir()
    publication.mkdir()
    (publication / "escape").symlink_to(outside, target_is_directory=True)
    writer = _PublicationWriter(publication, domain="direct_voxel")

    with pytest.raises(PublicationError, match="escapes model root"):
        writer.bytes(
            "escape/payload.json",
            b"payload\n",
            artifact_kind="payload",
            context={"stage": "configuration"},
        )

    assert not (outside / "payload.json").exists()


def test_replay_rejects_noncompleted_manifest_without_writing(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    recovery_cache = run_root / "recovery-cache"
    recovery_cache.mkdir()
    checkpoint = recovery_cache / "checkpoint.bin"
    checkpoint.write_bytes(b"recoverable partial state")
    (run_root / "run_manifest.json").write_text(
        json.dumps({"final_status": "failed"}), encoding="utf-8"
    )

    with pytest.raises(PublicationError, match="completed run manifest"):
        CanonicalPublisher().publish(run_root)

    assert tuple(tmp_path.glob("**/model_manifest.json")) == ()
    assert checkpoint.read_bytes() == b"recoverable partial state"


def test_outcome_loader_rejects_failed_tasks_and_preserves_task_file(
    tmp_path: Path,
) -> None:
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    task = tasks / "task_failed.json"
    task.write_text(
        json.dumps(
            {
                "task_id": "task_failed",
                "endpoint_id": "endpoint_failed",
                "service_id": "service_failed",
                "status": "failed",
                "reason": "injected_failure",
                "started_at": None,
                "finished_at": None,
                "result": None,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(PublicationError, match="retains failed tasks"):
        CanonicalPublisher._outcomes(tmp_path)

    assert task.is_file()
    assert json.loads(task.read_text(encoding="utf-8"))["status"] == "failed"


def _extension_artifact(
    path: Path,
    kind: str,
    *,
    axes: tuple[AxisRef, ...] = (),
    dtype: str | None = None,
    shape: tuple[int, ...] | None = None,
    units: str | None = None,
    space: str | None = None,
) -> ArtifactRef:
    return ArtifactRef(
        kind=kind,
        schema_version=(
            "dual_frequency_document_v1" if dtype is None else "dual_frequency_array_v1"
        ),
        uri=path.resolve().as_uri(),
        sha256=_sha256(path),
        dtype=dtype,
        shape=shape,
        axis_refs=axes,
        axis_hashes=tuple(axis.sha256 for axis in axes),
        units=units,
        space=space,
        producer_id="task-payload",
        producer_version="1",
    )


def _write_task(run_root: Path, task_id: str, endpoint_id: str, record: object) -> None:
    outcome = TaskOutcome(
        task_id=task_id,
        endpoint_id=endpoint_id,
        service_id=f"service-{task_id}",
        status="completed",
        reason="none",
        result=ServiceResult.from_record(record),
        started_at="2026-07-22T00:00:00Z",
        finished_at="2026-07-22T00:00:01Z",
    )
    payload = {"task_id": task_id, **outcome.as_dict()}
    destination = run_root / "tasks" / f"{task_id}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload), encoding="utf-8")


def _extension_fixture(
    tmp_path: Path,
    entries: tuple[tuple[str, str], ...],
    *,
    technical_failure: bool = False,
) -> tuple[Path, Path]:
    run_root = tmp_path / ".runs" / "extension-run"
    work = run_root / "work"
    work.mkdir(parents=True)
    output_root = tmp_path / "published"
    parent_run_id = "parent-run"
    model_set_id = "model-set"
    fixture_analyses = list(dict.fromkeys(analysis for _, analysis in entries))
    for domain in ("direct_voxel", "normative_fiber"):
        parent = output_root / domain / model_set_id
        parent.mkdir(parents=True)
        (parent / "model_manifest.json").write_text(
            json.dumps(
                {
                    "final_status": "completed",
                    "source_run_id": parent_run_id,
                }
            ),
            encoding="utf-8",
        )
        (parent / "artifact_index.csv").write_text(
            "relative_path,sha256,size_bytes,status\n",
            encoding="utf-8",
        )
    (run_root / "run_manifest.json").write_text(
        json.dumps(
            {
                "final_status": "completed",
                "run_id": "extension-run",
                "parent_run_id": parent_run_id,
                "scientific_configuration_hash": "s" * 64,
                "selected_sensitivity_analyses": fixture_analyses,
            }
        ),
        encoding="utf-8",
    )
    (run_root / "complete.json").write_text("{}\n", encoding="utf-8")
    (run_root / "base_run_reference.json").write_text(
        json.dumps(
            {
                "base_run_id": parent_run_id,
                "scientific_configuration_hash": "s" * 64,
            }
        ),
        encoding="utf-8",
    )
    (run_root / "configuration_resolved.yaml").write_text(
        yaml.safe_dump(
            {
                "direct_voxel": {
                    "model_set_id": model_set_id,
                    "output": {"root": str(output_root)},
                },
                "normative_fiber": {
                    "model_set_id": model_set_id,
                    "output": {"root": str(output_root)},
                },
            }
        ),
        encoding="utf-8",
    )

    aggregate_rows: list[dict[str, object]] = []
    analyses: list[str] = []
    plan_tasks: list[dict[str, object]] = []
    for index, (model_family, analysis) in enumerate(entries):
        role = "reference" if model_family.startswith("reference_") else "addon"
        connectome_id = "formal-connectome" if model_family.endswith("fiber") else "none"
        endpoint = EndpointKey(
            "study",
            f"scale-{index}",
            role,
            model_family,
            connectome_id,
        )
        endpoint_id = endpoint.identifier
        subject_axis = AxisRef(f"{endpoint_id}:subjects", 1, f"{index + 1}" * 64)
        feature_axis = AxisRef(f"{endpoint_id}:features", 2, f"{index + 3}" * 64)
        endpoint_work = work / endpoint_id
        endpoint_work.mkdir()
        baseline_path = endpoint_work / "baseline.npy"
        outcome_path = endpoint_work / "outcome.npy"
        feature_ids_path = endpoint_work / "feature_ids.npy"
        np.save(baseline_path, np.asarray([0.0], dtype=np.float64))
        np.save(outcome_path, np.asarray([1.0], dtype=np.float64))
        np.save(feature_ids_path, np.asarray([11, 12], dtype=np.int64))
        baseline = _extension_artifact(
            baseline_path,
            "endpoint_baseline",
            axes=(subject_axis,),
            dtype="float64",
            shape=(1,),
            units="score",
        )
        outcome = _extension_artifact(
            outcome_path,
            "endpoint_outcome",
            axes=(subject_axis,),
            dtype="float64",
            shape=(1,),
            units="score",
        )
        feature_ids = _extension_artifact(
            feature_ids_path,
            "selected_feature_ids",
            axes=(feature_axis,),
            dtype="int64",
            shape=(2,),
            units="fiber_id" if model_family.endswith("fiber") else "voxel_index",
            space="right_canonical",
        )
        endpoint_input = EndpointInputRecord(
            endpoint=endpoint,
            readiness_status="ready",
            candidate_subject_ids=("subject-1",),
            included_subject_ids=("subject-1",),
            exclusions=(),
            minimum_subjects=1,
            subject_axis=subject_axis,
            baseline=baseline,
            outcome=outcome,
        )
        source = SourceRecord(
            endpoint=endpoint,
            input_status="valid",
            source_status="pre_specified_accepted",
            prediction_status="error_nonpredictive",
            threshold_source="pre_specified",
            selected_tau=400.0 if model_family.endswith("fiber") else 200.0,
            selected_coverage=5,
            adjacent_support=2,
            feature_axis=FeatureAxisRef(feature_axis, "selected_feature_ids"),
            artifacts=(feature_ids,),
        )
        final_model = FinalModelRecord(
            endpoint=endpoint,
            final_status="final_model_realized",
            realization_role="primary",
            final_key=FinalModelKey(
                endpoint_id,
                "reference",
                source.selected_tau,
                source.selected_coverage,
                "weighted_peak",
            ),
            selected_source=source,
            selected_branch=None,
        )
        selection = FinalSelectionRecord(
            endpoint=endpoint,
            selection_status="final_model_realized",
            final_model=final_model,
            reason_codes=("primary_realized",),
            causal_task_ids=(f"task-source-{index}",),
        )
        _write_task(run_root, f"task_input_{index}", endpoint_id, endpoint_input)
        _write_task(run_root, f"task_final_{index}", endpoint_id, selection)

        if analysis == "jitter":
            metrics_path = endpoint_work / "spatial_jitter_metrics.json"
            metrics_path.write_text(
                json.dumps({"replicates": [{"replicate_index": 0}]}),
                encoding="utf-8",
            )
            record = SensitivityResult(
                target_id=final_model.identifier,
                sensitivity_kind="spatial_jitter",
                artifacts=(
                    _extension_artifact(
                        metrics_path,
                        "spatial_jitter_metrics",
                    ),
                ),
            )
        else:
            probability_path = endpoint_work / "probability.npy"
            binary_path = endpoint_work / "binary.npy"
            status_path = endpoint_work / "oss_status.json"
            np.save(probability_path, np.asarray([[0.1, 0.9]], dtype=np.float32))
            np.save(binary_path, np.asarray([[0, 1]], dtype=np.uint8))
            status_path.write_text(
                json.dumps(
                    {
                        "status": (
                            "completed_with_technical_failure"
                            if technical_failure
                            else "completed"
                        )
                    }
                ),
                encoding="utf-8",
            )
            probability = _extension_artifact(
                probability_path,
                "oss_activation_probability",
                axes=(subject_axis, feature_axis),
                dtype="float32",
                shape=(1, 2),
                units="probability",
                space="right_canonical",
            )
            binary = _extension_artifact(
                binary_path,
                "oss_binary_exposure",
                axes=(subject_axis, feature_axis),
                dtype="uint8",
                shape=(1, 2),
                units="binary",
                space="right_canonical",
            )
            status = _extension_artifact(status_path, "oss_sensitivity_status")
            record = ActivationArtifact(
                final_model_id=final_model.identifier,
                feature_axis=feature_axis,
                activation_probability=probability,
                binary_exposure=binary,
                artifacts=(status,),
            )
        terminal_task_id = f"task_terminal_{index}"
        _write_task(run_root, terminal_task_id, endpoint_id, record)
        plan_tasks.append(
            {
                "endpoint_id": endpoint_id,
                "stage": (
                    "spatial_jitter" if analysis == "jitter" else "activation_sensitivity"
                ),
            }
        )
        aggregate_rows.append(
            {
                "task_id": terminal_task_id,
                "endpoint_id": endpoint_id,
                "scale_id": endpoint.scale_id,
                "model_family": model_family,
                "model_role": role,
                "analysis": analysis,
                "status": "completed",
                "reason": "none",
                "record_id": ServiceResult.from_record(record).record_id,
                "artifact_ids": [artifact.identifier for artifact in record.artifacts],
            }
        )
        if analysis not in analyses:
            analyses.append(analysis)
    sensitivity = run_root / "sensitivity_results"
    sensitivity.mkdir()
    (run_root / "sensitivity_plan.json").write_text(
        json.dumps({"plan": {"tasks": plan_tasks}}),
        encoding="utf-8",
    )
    (sensitivity / "extension_results.json").write_text(
        json.dumps(
            {
                "schema_version": "dual_frequency_extension_results_v1",
                "extension_id": "extension-run",
                "parent_run_id": parent_run_id,
                "analyses": analyses,
                "status": "completed",
                "results": aggregate_rows,
            }
        ),
        encoding="utf-8",
    )
    return run_root, output_root


def test_terminal_jitter_replay_is_self_contained_and_idempotent(
    tmp_path: Path,
) -> None:
    run_root, output_root = _extension_fixture(
        tmp_path,
        (("reference_voxel", "jitter"), ("reference_fiber", "jitter")),
    )
    publisher = CanonicalPublisher()
    first = publisher.publish_extension(run_root)
    second = CanonicalPublisher().publish_extension(run_root)

    assert first == second
    assert first.direct_voxel_result_count == 1
    assert first.normative_fiber_result_count == 1
    for extension_root in (first.direct_voxel_root, first.normative_fiber_root):
        assert extension_root is not None
        manifest = json.loads((extension_root / "extension_manifest.json").read_text())
        assert manifest["status"] == "completed"
        assert manifest["publication_scope"] == "complete"
        with (extension_root / "artifact_index.csv").open(
            "r",
            encoding="utf-8",
            newline="",
        ) as handle:
            indexed_paths = {
                row["relative_path"]
                for row in csv.DictReader(handle)
            }
        actual_paths = {
            path.relative_to(extension_root).as_posix()
            for path in extension_root.rglob("*")
            if path.is_file()
            and path.name
            not in {"artifact_index.csv", "extension_manifest.json", ".DS_Store"}
            and not path.name.startswith("._")
        }
        metadata_paths = {
            relative
            for relative in actual_paths
            if relative.endswith(".metadata.json")
        }
        assert metadata_paths
        assert indexed_paths == actual_paths
        assert metadata_paths.issubset(indexed_paths)
        text = "\n".join(
            path.read_text(errors="ignore")
            for path in extension_root.rglob("*")
            if path.is_file() and path.suffix in {".json", ".csv"}
        )
        assert "file://" not in text
        assert ".runs/" not in text
        assert "runtime_work" not in text
    assert output_root in first.direct_voxel_root.parents


def test_combined_replay_keeps_domain_specific_analysis_presence(
    tmp_path: Path,
) -> None:
    run_root, _ = _extension_fixture(
        tmp_path,
        (("reference_voxel", "jitter"), ("reference_fiber", "oss")),
    )
    result = CanonicalPublisher().publish_extension(run_root)

    assert result.direct_voxel_root is not None
    assert result.normative_fiber_root is not None
    assert (result.direct_voxel_root / "spatial_jitter_results.json").is_file()
    assert not (result.direct_voxel_root / "oss_ppam_results.json").exists()
    assert (result.normative_fiber_root / "oss_ppam_results.json").is_file()
    assert not (result.normative_fiber_root / "spatial_jitter_results.json").exists()


def test_extension_replay_requires_run_completion_marker(tmp_path: Path) -> None:
    run_root, output_root = _extension_fixture(
        tmp_path,
        (("reference_fiber", "oss"),),
    )
    (run_root / "complete.json").unlink()

    with pytest.raises(PublicationError, match="run completion marker"):
        CanonicalPublisher().publish_extension(run_root)

    extension_root = (
        output_root
        / "normative_fiber"
        / "model-set"
        / "extensions"
        / "extension-run-v2"
    )
    assert not (extension_root / "extension_manifest.json").exists()


def test_extension_id_must_be_one_safe_path_component(tmp_path: Path) -> None:
    run_root, output_root = _extension_fixture(
        tmp_path,
        (("reference_fiber", "oss"),),
    )

    for extension_id in (".", "..", "../escape", "nested/escape", "nested\\escape"):
        with pytest.raises(PublicationError, match="path-safe token"):
            CanonicalPublisher().publish_extension(
                run_root,
                extension_id=extension_id,
            )

    assert not tuple(output_root.rglob("extension_manifest.json"))


def test_oss_replay_omits_empty_voxel_domain_and_rejects_technical_failure(
    tmp_path: Path,
) -> None:
    complete_run, _ = _extension_fixture(
        tmp_path / "complete",
        (("reference_fiber", "oss"),),
    )
    result = CanonicalPublisher().publish_extension(complete_run)
    assert result.direct_voxel_root is None
    assert result.direct_voxel_result_count == 0
    assert result.normative_fiber_root is not None
    assert (result.normative_fiber_root / "oss_ppam_results.json").is_file()

    failed_run, output_root = _extension_fixture(
        tmp_path / "failed",
        (("reference_fiber", "oss"),),
        technical_failure=True,
    )
    with pytest.raises(PublicationError, match="technical failure"):
        CanonicalPublisher().publish_extension(failed_run)
    extension_root = (
        output_root
        / "normative_fiber"
        / "model-set"
        / "extensions"
        / "extension-run-v2"
    )
    assert not (extension_root / "extension_manifest.json").exists()
