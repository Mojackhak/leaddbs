"""Endpoint-local OSS sidecar preparation service tests."""

from __future__ import annotations

import tempfile
import json
import hashlib
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np

import outcome_models.services.oss_sidecar as oss_sidecar_module
from outcome_models.executor import (
    RunContext,
    TaskExecutionRecord,
    TaskResult,
    TaskStatus,
)
from outcome_models.identity import EndpointModelKey, TaskKey
from outcome_models.planner import (
    DependencyRequirement,
    DependencySpec,
    GatePredicate,
    TaskGate,
    TaskSpec,
)
from outcome_models.records import (
    ArtifactRef,
    FeatureAxisRef,
    FinalArtifactRecord,
    NuisancePlan,
    RecordError,
)
from outcome_models.services.oss_sidecar import (
    OSSSidecarInputsUnavailable,
    OSSSideInput,
    OSSSidecarPreparationRequest,
    OSSSidecarPreparationService,
    OSSGeneratedContent,
    _sha256_file,
    oss_compatibility_hash,
    run_configured_oss_sidecar_preparation,
    validate_oss_side_inputs,
)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _array_sha256(values: np.ndarray) -> str:
    array = np.ascontiguousarray(values)
    digest = hashlib.sha256()
    digest.update(array.dtype.str.encode("ascii"))
    digest.update(json.dumps(list(array.shape), separators=(",", ":")).encode("ascii"))
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


class OSSSidecarPreparationServiceTests(unittest.TestCase):
    def _task(self) -> TaskSpec:
        endpoint = EndpointModelKey(
            study_id="study",
            scale_id="scale",
            endpoint_phase="reference",
            model_family="hf_fiber",
            connectome="dtor",
        )
        key = TaskKey(
            endpoint_model_id=endpoint.identifier,
            execution_stage="oss_sidecar_preparation",
            source_reference="final_model_record",
        )
        return TaskSpec(
            task_id=key.identifier,
            key=key,
            endpoint=endpoint,
            round_name="Round 7",
            workflow_phase="sensitivity",
            dependencies=(),
            gate=TaskGate(GatePredicate.FINAL_MODEL_REALIZED),
            expected_artifact_kinds=(
                "task_manifest",
                "oss_activation_probabilities",
                "oss_fiber_ids",
                "oss_parameter_manifest",
                "oss_activation_metadata",
            ),
        )

    def _final(self, task: TaskSpec) -> FinalArtifactRecord:
        artifact = lambda kind, name, shape=(): ArtifactRef(
            "producer",
            kind,
            f"producer/{name}",
            "a" * 64,
            shape,
        )
        return FinalArtifactRecord.create(
            final_model_id="final-hf-fiber",
            endpoint_model_id=task.endpoint.identifier,
            final_branch="hf_source",
            final_role="realized_final",
            selected_tau=800,
            selected_coverage=5,
            estimator="peak_efield_partial_spearman",
            scale_direction="lower",
            subject_order=("sub-01", "sub-02"),
            nuisance=NuisancePlan.for_branch("hf_source", None),
            manifest=artifact("selected_manifest", "manifest.json"),
            exposure=artifact("exposure_matrix", "exposure.npy", (2, 4)),
            scores=artifact("selected_scores", "scores.csv", (2,)),
            feature_axis=FeatureAxisRef(
                Path("producer/fiber_ids.npy"),
                4,
                "b" * 64,
                "data.mat:idx",
            ),
            full_weights=artifact("selected_full_weights", "weights.npy", (4,)),
            valid_feature_axis=FeatureAxisRef(
                Path("producer/valid_fiber_ids.npy"),
                3,
                "c" * 64,
                "data.mat:idx",
            ),
        )

    def _cache_request(self, root: Path, token: str) -> OSSSidecarPreparationRequest:
        endpoint = EndpointModelKey(
            study_id="study",
            scale_id=token,
            endpoint_phase="reference",
            model_family="hf_fiber",
            connectome="dtor",
        )
        key = TaskKey(
            endpoint_model_id=endpoint.identifier,
            execution_stage="oss_sidecar_preparation",
            source_reference="final_model_record",
        )
        task = TaskSpec(
            task_id=key.identifier,
            key=key,
            endpoint=endpoint,
            round_name="Round 7",
            workflow_phase="sensitivity",
            dependencies=(),
            gate=TaskGate(GatePredicate.FINAL_MODEL_REALIZED),
            expected_artifact_kinds=("task_manifest",),
        )
        producer = root / "models" / endpoint.identifier / "producer"
        producer.mkdir(parents=True, exist_ok=True)
        parent_ids = np.asarray([101, 103, 107, 109], dtype=np.int64)
        valid_ids = np.asarray([101, 107, 109], dtype=np.int64)
        paths = {
            "parent": producer / "fiber_ids.npy",
            "valid": producer / "valid_fiber_ids.npy",
            "exposure": producer / "exposure.npy",
            "weights": producer / "weights.npy",
            "scores": producer / "scores.csv",
            "manifest": producer / "manifest.json",
        }
        np.save(paths["parent"], parent_ids)
        np.save(paths["valid"], valid_ids)
        np.save(paths["exposure"], np.ones((2, 4), dtype=np.float32))
        np.save(paths["weights"], np.asarray([1.0, np.nan, -1.0, 0.5], dtype=np.float32))
        paths["scores"].write_text("subject_id,Y_post,Y_base\nsub-01,1,2\nsub-02,2,3\n", encoding="utf-8")
        paths["manifest"].write_text("{}\n", encoding="utf-8")

        def artifact(kind: str, name: str, shape=()):
            path = paths[name]
            return ArtifactRef(
                "producer",
                kind,
                path.relative_to(root).as_posix(),
                _file_sha256(path),
                shape,
            )

        final = FinalArtifactRecord.create(
            final_model_id=f"final-{token}",
            endpoint_model_id=endpoint.identifier,
            final_branch="hf_source",
            final_role="realized_final",
            selected_tau=800,
            selected_coverage=5,
            estimator="peak_efield_partial_spearman",
            scale_direction="lower",
            subject_order=("sub-01", "sub-02"),
            nuisance=NuisancePlan.for_branch("hf_source", None),
            manifest=artifact("selected_manifest", "manifest"),
            exposure=artifact("exposure_matrix", "exposure", (2, 4)),
            scores=artifact("selected_scores", "scores", (2,)),
            feature_axis=FeatureAxisRef(
                paths["parent"],
                4,
                _array_sha256(parent_ids),
                "data.mat:idx",
            ),
            full_weights=artifact("selected_full_weights", "weights", (4,)),
            valid_feature_axis=FeatureAxisRef(
                paths["valid"],
                3,
                _array_sha256(valid_ids),
                "data.mat:idx",
            ),
        )
        payload = {
            "source_stimulation_input_hashes": {
                "sub-01:R:0": {
                    "efield_sha256": "a" * 64,
                    "stimulation_parameter_sha256": "f" * 64,
                }
            },
            "subject_order": ["sub-01", "sub-02"],
            "requested_frequencies_hz": {"sub-01:R": 130.0},
            "modeled_frequencies_hz": {"sub-01:R": 130.0},
            "canonical_hemisphere": "right",
            "left_to_right_mapping": {
                "method": "ea_flip_lr_nonlinear",
                "code_sha256": "d" * 64,
                "transform_sha256": "e" * 64,
            },
            "hemisphere_merge_rule": "max_probability_union",
            "component_identity": "HF_only_reference",
            "hf_overlap_definition": "not_applicable",
            "ordered_valid_fiber_ids": valid_ids.tolist(),
            "valid_fiber_axis_sha256": _array_sha256(valid_ids),
            "parent_feature_axis_sha256": _array_sha256(parent_ids),
            "connectome_input_sha256": "1" * 64,
            "generator_identity_sha256": "2" * 64,
            "oss_toolchain_sha256": {
                "matlab": "3" * 64,
                "leaddbs2ossdbs": "4" * 64,
                "prepareaxonmodel": "5" * 64,
                "ossdbs": "6" * 64,
                "run_pathway_activation": "7" * 64,
            },
            "oss_environment_sha256": "c" * 64,
            "oss_model": "OSS-DBSv2",
            "ppam_sample_count": 10,
            "ppam_sampling": {
                "probabilistic_parameter": "Fiber Diameter",
                "parameter_limits_um": [1.0, 4.0],
                "sampling_distribution": "Equidistant",
            },
        }
        return OSSSidecarPreparationRequest(
            task=task,
            final=final,
            output_root=root / "models" / endpoint.identifier / "tasks" / task.task_id,
            compatibility_hash=oss_compatibility_hash(payload),
            compatibility_payload=payload,
        )
    def test_compatibility_hash_is_canonical_and_changes_on_exact_identity_fields(self) -> None:
        payload = {
            "source_stimulation_input_hashes": {
                "sub-01:R": {
                    "efield_sha256": "a" * 64,
                    "stimulation_parameter_sha256": "f" * 64,
                }
            },
            "subject_order": ["sub-01"],
            "requested_frequencies_hz": {"sub-01:R": 130.0},
            "modeled_frequencies_hz": {"sub-01:R": 130.0},
            "canonical_hemisphere": "right",
            "left_to_right_mapping": {
                "method": "ea_flip_lr_nonlinear",
                "code_sha256": "d" * 64,
                "transform_sha256": "e" * 64,
            },
            "hemisphere_merge_rule": "max_probability_union",
            "component_identity": "HF_only_reference",
            "hf_overlap_definition": "not_applicable",
            "ordered_valid_fiber_ids": [101, 107, 109],
            "valid_fiber_axis_sha256": "b" * 64,
            "parent_feature_axis_sha256": "1" * 64,
            "connectome_input_sha256": "2" * 64,
            "generator_identity_sha256": "3" * 64,
            "oss_toolchain_sha256": {
                "matlab": "4" * 64,
                "leaddbs2ossdbs": "5" * 64,
                "prepareaxonmodel": "6" * 64,
                "ossdbs": "7" * 64,
                "run_pathway_activation": "8" * 64,
            },
            "oss_environment_sha256": "c" * 64,
            "oss_model": "OSS-DBSv2",
            "ppam_sample_count": 10,
            "ppam_sampling": {
                "probabilistic_parameter": "Fiber Diameter",
                "parameter_limits_um": [1.0, 4.0],
                "sampling_distribution": "Equidistant",
            },
        }
        reordered = dict(reversed(list(payload.items())))

        self.assertEqual(
            oss_compatibility_hash(payload),
            oss_compatibility_hash(reordered),
        )
        changed = {
            **payload,
            "component_identity": "ULF_addon_component",
            "hf_overlap_definition": "matched_hf_peak_efield_selected_tau",
        }
        self.assertNotEqual(
            oss_compatibility_hash(payload),
            oss_compatibility_hash(changed),
        )
        changed_parameter = json.loads(json.dumps(payload))
        changed_parameter["source_stimulation_input_hashes"]["sub-01:R"][
            "stimulation_parameter_sha256"
        ] = "0" * 64
        self.assertNotEqual(
            oss_compatibility_hash(payload),
            oss_compatibility_hash(changed_parameter),
        )
        changed_overlap = {
            **changed,
            "hf_overlap_definition": "hf_source_absent_all_false",
        }
        self.assertNotEqual(
            oss_compatibility_hash(changed),
            oss_compatibility_hash(changed_overlap),
        )
        invalid_source_identity = json.loads(json.dumps(payload))
        invalid_source_identity["source_stimulation_input_hashes"]["sub-01:R"] = {
            "efield_sha256": "a" * 64
        }
        with self.assertRaisesRegex(RecordError, "source input identity"):
            oss_compatibility_hash(invalid_source_identity)
        with self.assertRaisesRegex(RecordError, "pPAM sample count"):
            oss_compatibility_hash({**payload, "ppam_sample_count": 0})
        with self.assertRaisesRegex(RecordError, "pPAM sampling"):
            oss_compatibility_hash(
                {
                    **payload,
                    "ppam_sampling": {
                        **payload["ppam_sampling"],
                        "parameter_limits_um": [2.0, 4.0],
                    },
                }
            )
        changed_connectome = {**payload, "connectome_input_sha256": "9" * 64}
        self.assertNotEqual(
            oss_compatibility_hash(payload),
            oss_compatibility_hash(changed_connectome),
        )
        with self.assertRaisesRegex(RecordError, "missing"):
            oss_compatibility_hash(
                {key: value for key, value in payload.items() if key != "oss_model"}
            )

    def test_file_hash_reflects_content_changes_within_one_process(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mutable-input.mat"
            path.write_bytes(b"first")
            first = _sha256_file(path)
            path.write_bytes(b"second")
            second = _sha256_file(path)

        self.assertNotEqual(first, second)

    def test_generator_identity_changes_when_a_matlab_dependency_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            python_source = root / "generator.py"
            matlab_source = root / "ea_prepare_fibers.m"
            python_source.write_text("generator = 1\n", encoding="utf-8")
            matlab_source.write_text("function x = f(); x = 1; end\n", encoding="utf-8")
            first = oss_sidecar_module._generator_identity_sha256(
                {"python": python_source, "matlab": matlab_source}
            )
            matlab_source.write_text("function x = f(); x = 2; end\n", encoding="utf-8")
            second = oss_sidecar_module._generator_identity_sha256(
                {"python": python_source, "matlab": matlab_source}
            )

        self.assertNotEqual(first, second)

    def test_final_axes_are_hash_checked_ordered_subsets_inside_the_run_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run"
            request = self._cache_request(run_root, "scale-one")
            context = SimpleNamespace(store=SimpleNamespace(run_root=run_root))

            parent, valid = oss_sidecar_module._validated_final_axes(
                request.final,
                context,
            )
            np.testing.assert_array_equal(parent, np.asarray([101, 103, 107, 109]))
            np.testing.assert_array_equal(valid, np.asarray([101, 107, 109]))

            np.save(
                request.final.valid_feature_axis.ids_path,
                np.asarray([101, 107, 999], dtype=np.int64),
            )
            with self.assertRaisesRegex(RecordError, "SHA-256"):
                oss_sidecar_module._validated_final_axes(request.final, context)

            outside = Path(tmp) / "outside.npy"
            np.save(outside, np.asarray([101], dtype=np.int64))
            outside_axis = FeatureAxisRef(
                outside,
                1,
                _array_sha256(np.asarray([101], dtype=np.int64)),
                "data.mat:idx",
            )
            with self.assertRaisesRegex(RecordError, "outside"):
                oss_sidecar_module._validated_axis_path(
                    outside_axis,
                    run_root,
                    "valid",
                )

    def test_ulf_overlap_definition_is_derived_from_the_locked_hf_source_status(self) -> None:
        self.assertEqual(
            oss_sidecar_module._hf_overlap_definition(
                "hf_fiber",
                {},
            ),
            "not_applicable",
        )
        self.assertEqual(
            oss_sidecar_module._hf_overlap_definition(
                "ulf_fiber",
                {"hf_source_status": "pre_specified_accepted"},
            ),
            "matched_hf_peak_efield_selected_tau",
        )
        self.assertEqual(
            oss_sidecar_module._hf_overlap_definition(
                "ulf_fiber",
                {"hf_source_status": "absent_no_stable_grid"},
            ),
            "hf_source_absent_all_false",
        )
        with self.assertRaisesRegex(OSSSidecarInputsUnavailable, "HF source status"):
            oss_sidecar_module._hf_overlap_definition("ulf_fiber", {})

    def test_formal_dependency_must_match_the_exact_final_record(self) -> None:
        producer = self._task()
        final = self._final(producer)
        formal_key = TaskKey(
            endpoint_model_id=producer.endpoint.identifier,
            execution_stage="formal_permutation_bootstrap",
            source_reference="final_model_record",
        )
        formal_task = TaskSpec(
            task_id=formal_key.identifier,
            key=formal_key,
            endpoint=producer.endpoint,
            round_name="Round 6",
            workflow_phase="formal",
            dependencies=(),
            gate=TaskGate(GatePredicate.FINAL_MODEL_REALIZED),
            expected_artifact_kinds=("task_manifest",),
        )
        producer = replace(
            producer,
            dependencies=(
                DependencySpec(
                    formal_task.task_id,
                    DependencyRequirement.FORMAL_COMPLETE,
                ),
            ),
        )
        context = RunContext(store=SimpleNamespace(run_root=Path("/tmp/run")), catalog=())
        context.results[formal_task.task_id] = TaskExecutionRecord(
            formal_task,
            TaskResult(
                TaskStatus.COMPLETED,
                facts={
                    "formal_complete": True,
                    "final_model_id": final.final_model_id,
                    "final_artifact_record_hash": "0" * 64,
                },
            ),
        )

        with self.assertRaisesRegex(OSSSidecarInputsUnavailable, "final-record"):
            oss_sidecar_module._validate_formal_dependency(producer, context, final)

        context.results[formal_task.task_id] = TaskExecutionRecord(
            formal_task,
            TaskResult(
                TaskStatus.COMPLETED,
                facts={
                    "formal_complete": True,
                    "final_model_id": final.final_model_id,
                    "final_artifact_record_hash": final.record_hash,
                },
            ),
        )
        oss_sidecar_module._validate_formal_dependency(producer, context, final)

    def test_service_passes_final_locked_request_and_preserves_runner_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            task = self._task()
            final = self._final(task)
            context = RunContext(
                store=SimpleNamespace(run_root=root),
                catalog=(),
            )
            captured = []

            def request_factory(observed_task, observed_context, observed_final):
                request = OSSSidecarPreparationRequest(
                    task=observed_task,
                    final=observed_final,
                    output_root=root / "task",
                    compatibility_hash="d" * 64,
                )
                captured.append((observed_context, request))
                return request

            expected = TaskResult(
                TaskStatus.COMPLETED,
                "prepared",
                facts={
                    "oss_sidecar_bundle": {
                        "final_model_id": final.final_model_id,
                        "final_record_hash": final.record_hash,
                    }
                },
            )
            service = OSSSidecarPreparationService(
                request_factory=request_factory,
                runner=lambda request: expected,
                final_loader=lambda _task, _context: final,
            )

            result = service.execute(task, context)

        self.assertIs(result, expected)
        self.assertEqual(captured[0][1].final.record_hash, final.record_hash)
        self.assertEqual(captured[0][1].compatibility_hash, "d" * 64)

    def test_side_inputs_require_exactly_one_left_and_right_row_per_subject(self) -> None:
        rows = (
            OSSSideInput("sub-01", "L", (Path("left.mat"),), ("a" * 64,), 130.0, 130.0),
            OSSSideInput("sub-01", "R", (Path("right.mat"),), ("b" * 64,), 130.0, 130.0),
            OSSSideInput("sub-02", "L", (Path("left2.mat"),), ("c" * 64,), 130.0, 130.0),
            OSSSideInput("sub-02", "R", (Path("right2.mat"),), ("d" * 64,), 130.0, 130.0),
        )

        ordered = validate_oss_side_inputs(("sub-01", "sub-02"), rows)

        self.assertEqual([(row.subject_id, row.side) for row in ordered], [
            ("sub-01", "L"),
            ("sub-01", "R"),
            ("sub-02", "L"),
            ("sub-02", "R"),
        ])
        with self.assertRaisesRegex(OSSSidecarInputsUnavailable, "exact"):
            validate_oss_side_inputs(("sub-01", "sub-02"), rows[:-1])
        with self.assertRaisesRegex(OSSSidecarInputsUnavailable, "duplicate"):
            validate_oss_side_inputs(("sub-01", "sub-02"), rows + (rows[0],))

    def test_missing_side_inputs_are_endpoint_local_input_failure(self) -> None:
        task = self._task()
        final = self._final(task)
        context = RunContext(store=SimpleNamespace(run_root=Path("/tmp/run")), catalog=())
        request = OSSSidecarPreparationRequest(
            task=task,
            final=final,
            output_root=Path("/tmp/run/task"),
            compatibility_hash="e" * 64,
        )
        service = OSSSidecarPreparationService(
            request_factory=lambda *_: request,
            runner=lambda _request: (_ for _ in ()).throw(
                OSSSidecarInputsUnavailable("missing executable")
            ),
            final_loader=lambda _task, _context: final,
        )

        result = service.execute(task, context)

        self.assertEqual(result.status, TaskStatus.INPUT_FAILURE)
        self.assertIn("missing executable", result.detail)
        self.assertEqual(result.facts["final_model_id"], final.final_model_id)
        self.assertFalse(result.facts["oss_sidecar_preparation_complete"])

    def test_exact_compatibility_reuses_content_but_rewrites_destination_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = self._cache_request(root, "scale-one")
            second = self._cache_request(root, "scale-two")
            calls = 0

            def generator(request, cache_root):
                nonlocal calls
                calls += 1
                cache_root.mkdir(parents=True, exist_ok=True)
                probabilities = cache_root / "probabilities.npy"
                fiber_ids = cache_root / "fiber_ids.npy"
                np.save(
                    probabilities,
                    np.asarray([[0.1, 0.5, 0.9], [0.2, 0.6, 0.8]], dtype=np.float32),
                )
                np.save(fiber_ids, np.asarray([101, 107, 109], dtype=np.int64))
                return OSSGeneratedContent(probabilities, fiber_ids)

            first_result = run_configured_oss_sidecar_preparation(first, generator=generator)
            second_result = run_configured_oss_sidecar_preparation(second, generator=generator)
            first_manifest = json.loads(
                first_result.artifacts[2].path.read_text(encoding="utf-8")
            )
            second_manifest = json.loads(
                second_result.artifacts[2].path.read_text(encoding="utf-8")
            )
            second_metadata = json.loads(
                second_result.artifacts[3].path.read_text(encoding="utf-8")
            )

        self.assertEqual(calls, 1)
        self.assertFalse(first_result.facts["oss_content_reused"])
        self.assertTrue(second_result.facts["oss_content_reused"])
        first_bundle = first_result.facts["oss_sidecar_bundle"]
        second_bundle = second_result.facts["oss_sidecar_bundle"]
        self.assertNotEqual(first_bundle["final_model_id"], second_bundle["final_model_id"])
        self.assertEqual(first_manifest["final_model_id"], first.final.final_model_id)
        self.assertEqual(second_manifest["final_model_id"], second.final.final_model_id)
        self.assertEqual(
            first_manifest["compatibility_hash"],
            second_manifest["compatibility_hash"],
        )
        self.assertEqual(second_manifest["ppam_sample_count"], 10)
        self.assertEqual(
            second_manifest["parent_feature_axis_sha256"],
            second.final.feature_axis.sha256,
        )
        self.assertEqual(
            second_manifest["connectome_input_sha256"],
            second.compatibility_payload["connectome_input_sha256"],
        )
        self.assertEqual(
            second_manifest["oss_toolchain_sha256"],
            second.compatibility_payload["oss_toolchain_sha256"],
        )
        self.assertEqual(second_metadata["ppam_sample_count"], 10)
        self.assertEqual(
            second_metadata["generator_identity_sha256"],
            second.compatibility_payload["generator_identity_sha256"],
        )

    def test_cache_payload_drift_forces_regeneration_even_when_digest_string_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = self._cache_request(root, "scale-one")
            calls = 0

            def generator(_request, cache_root):
                nonlocal calls
                calls += 1
                cache_root.mkdir(parents=True, exist_ok=True)
                probabilities = cache_root / f"probabilities-{calls}.npy"
                fiber_ids = cache_root / f"fiber-ids-{calls}.npy"
                np.save(
                    probabilities,
                    np.asarray(
                        [[0.1, 0.5, 0.9], [0.2, 0.6, 0.8]],
                        dtype=np.float32,
                    ),
                )
                np.save(fiber_ids, np.asarray([101, 107, 109], dtype=np.int64))
                return OSSGeneratedContent(probabilities, fiber_ids)

            run_configured_oss_sidecar_preparation(request, generator=generator)
            cache_manifest = (
                root
                / "oss_content_cache"
                / request.compatibility_hash
                / "content_manifest.json"
            )
            manifest = json.loads(cache_manifest.read_text(encoding="utf-8"))
            manifest["compatibility_payload"]["component_identity"] = "tampered"
            cache_manifest.write_text(json.dumps(manifest), encoding="utf-8")

            result = run_configured_oss_sidecar_preparation(request, generator=generator)

        self.assertEqual(calls, 2)
        self.assertFalse(result.facts["oss_content_reused"])

    def test_hash_consistent_but_semantically_invalid_cache_is_regenerated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = self._cache_request(root, "scale-one")
            calls = 0

            def generator(_request, cache_root):
                nonlocal calls
                calls += 1
                cache_root.mkdir(parents=True, exist_ok=True)
                probabilities = cache_root / f"probabilities-{calls}.npy"
                fiber_ids = cache_root / f"fiber-ids-{calls}.npy"
                np.save(
                    probabilities,
                    np.asarray(
                        [[0.1, 0.5, 0.9], [0.2, 0.6, 0.8]],
                        dtype=np.float32,
                    ),
                )
                np.save(fiber_ids, np.asarray([101, 107, 109], dtype=np.int64))
                return OSSGeneratedContent(probabilities, fiber_ids)

            run_configured_oss_sidecar_preparation(request, generator=generator)
            cache_root = root / "oss_content_cache" / request.compatibility_hash
            probability_path = cache_root / "X_oss_float32_fiber_major.npy"
            np.save(probability_path, np.zeros((2, 2), dtype=np.float32))
            manifest_path = cache_root / "content_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["activation_probabilities_file_sha256"] = _file_sha256(
                probability_path
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            result = run_configured_oss_sidecar_preparation(request, generator=generator)

        self.assertEqual(calls, 2)
        self.assertFalse(result.facts["oss_content_reused"])

    def test_producer_rejects_near_but_not_exact_ten_sample_probabilities(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = self._cache_request(root, "scale-one")

            def generator(_request, cache_root):
                cache_root.mkdir(parents=True, exist_ok=True)
                probabilities = cache_root / "probabilities.npy"
                fiber_ids = cache_root / "fiber-ids.npy"
                values = np.asarray(
                    [[0.1, 0.5, 0.9], [0.2, 0.6, 0.8]],
                    dtype=np.float32,
                )
                values[0, 0] = np.float32(0.10000005)
                np.save(probabilities, values)
                np.save(fiber_ids, np.asarray([101, 107, 109], dtype=np.int64))
                return OSSGeneratedContent(probabilities, fiber_ids)

            with self.assertRaisesRegex(RecordError, "ten-sample lattice"):
                run_configured_oss_sidecar_preparation(request, generator=generator)

    def test_endpoint_generator_runs_every_source_and_max_unions_sources_and_sides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._cache_request(root, "scale-one")
            source_specs = {
                ("sub-01", "L"): ("s01-l-a", "s01-l-b"),
                ("sub-01", "R"): ("s01-r",),
                ("sub-02", "L"): ("s02-l",),
                ("sub-02", "R"): ("s02-r",),
            }
            side_inputs = []
            for (subject_id, side), names in source_specs.items():
                source_paths = []
                stimulation_paths = []
                for name in names:
                    source = root / f"{name}.nii.gz"
                    stimulation = root / f"{name}.mat"
                    source.write_bytes(name.encode("ascii"))
                    stimulation.write_bytes((name + "-stim").encode("ascii"))
                    source_paths.append(source)
                    stimulation_paths.append(stimulation)
                side_inputs.append(
                    OSSSideInput(
                        subject_id,
                        side,
                        tuple(source_paths),
                        tuple(_file_sha256(path) for path in source_paths),
                        130.0,
                        130.0,
                        tuple(stimulation_paths),
                        tuple(_file_sha256(path) for path in stimulation_paths),
                    )
                )
            request = replace(
                base,
                side_inputs=tuple(side_inputs),
                toolchain={
                    "matlab": Path("/mock/matlab"),
                    "leaddbs2ossdbs": Path("/mock/leaddbs2ossdbs"),
                    "prepareaxonmodel": Path("/mock/prepareaxonmodel"),
                    "ossdbs": Path("/mock/ossdbs"),
                    "run_pathway_activation": Path("/mock/run_pathway_activation"),
                },
            )
            values = {
                "s01-l-a": [0.2, 0.6, 0.1],
                "s01-l-b": [0.4, 0.3, 0.7],
                "s01-r": [0.1, 0.9, 0.3],
                "s02-l": [0.8, 0.1, 0.4],
                "s02-r": [0.2, 0.5, 0.6],
            }
            observed_rows = []

            def preflight_runner(**kwargs):
                row = dict(kwargs["row"])
                observed_rows.append(row)
                source = Path(row["source_paths"])
                return {
                    **row,
                    "source_path_used": str(source),
                    "source_frequency_hz": "130.0",
                    "parameter_file": str(source.with_suffix(".parameter.mat")),
                    "converter_json": str(source.with_suffix(".json")),
                    "sample_parameter_manifest": str(source.with_suffix(".samples.json")),
                    "preflight_status": "parameter_preflight_passed",
                }

            def activation_runner(**kwargs):
                row = dict(kwargs["row"])
                name = Path(row["source_path_used"]).name.removesuffix(".nii.gz")
                probability_path = root / f"{name}-probability.npy"
                np.save(probability_path, np.asarray(values[name], dtype=np.float32))
                return {
                    **row,
                    "row_status": "probabilistic_activation_complete",
                    "right_canonical_probability_path": str(probability_path),
                    "right_canonical_candidate_fiber_ids_path": str(
                        base.final.valid_feature_axis.ids_path
                    ),
                }

            content = oss_sidecar_module.generate_configured_oss_content(
                request,
                root / "cache",
                preflight_runner=preflight_runner,
                activation_runner=activation_runner,
            )

            matrix = np.load(content.activation_probabilities)
            fiber_ids = np.load(content.fiber_ids)

        self.assertEqual(len(observed_rows), 5)
        self.assertTrue(all(";" not in row["source_paths"] for row in observed_rows))
        self.assertEqual(
            {(row["side"], row["canonicalization_mode"]) for row in observed_rows},
            {("L", "left_geometry_to_right"), ("R", "native_right")},
        )
        np.testing.assert_allclose(
            matrix,
            np.asarray(
                [
                    [0.4, 0.9, 0.7],
                    [0.8, 0.5, 0.6],
                ],
                dtype=np.float32,
            ),
        )
        np.testing.assert_array_equal(fiber_ids, np.asarray([101, 107, 109]))


if __name__ == "__main__":
    unittest.main()
