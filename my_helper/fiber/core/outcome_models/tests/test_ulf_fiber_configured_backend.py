"""Executable contract for the configured ULF normative-fiber backend."""

from __future__ import annotations

import hashlib
import json
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from outcome_models.catalog import CatalogStatus, EndpointRecord
from outcome_models.config import ConnectomeSpec
from outcome_models.identity import EndpointModelKey
from outcome_models.records import ArtifactRef, DeltaHFBundle, FeatureAxisRef, HFSourceRecord, NuisancePlan, RecordError
from outcome_models.services import legacy_ulf_fiber
from outcome_models.services.legacy_ulf_fiber import (
    ULFNormativeFiberBackendInputs,
    _assess_hf_component_fiber_support,
    build_legacy_ulf_fiber_config,
    configured_ulf_fiber_delta_builder,
    run_configured_ulf_fiber_resolver,
)
from outcome_models.services.observed import ObservedServiceOutput
from outcome_models.services.ulf_observed import DeltaBuilderOutput, ULFObservedRequest
from stnsnr_four_model_stats import candidate_mask_from_coverage, coverage_from_suprathreshold, fiber_net_score
from stnsnr_hf_normative_fiber_smoke import sha256_array
from stnsnr_ulf_normative_fiber_observed import _array_sha256, _configured_delta_inputs
from stnsnr_ulf_normative_fiber_observed import ulf_fiber_artifact_names, ulf_fiber_branch_name


def _artifact(root: Path, kind: str, name: str, shape: tuple[int, ...]) -> ArtifactRef:
    path = root / "tasks" / "hf-sidecars" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".npy":
        np.save(path, np.zeros(shape, dtype=np.float64))
    else:
        path.write_text("subject_id,status\nsub-01,adequate\n", encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return ArtifactRef(
        task_id="hf-sidecars",
        kind=kind,
        relative_path=str(path.relative_to(root)),
        sha256=digest,
        shape=shape,
    )


def _endpoint(connectome: str = "ppmi", phase: str = "chronic") -> EndpointRecord:
    outcome_phase = "3m" if phase == "chronic" else "immediate"
    return EndpointRecord(
        key=EndpointModelKey("study", "scale", phase, "ulf_fiber", connectome),
        endpoint_model_id=f"endpoint-{connectome}-{phase}",
        scale_label="Configured Scale",
        direction="lower",
        outcome_protocol="CUSTOM_ADDON",
        outcome_phase=outcome_phase,
        hf_reference_protocol="CUSTOM_REFERENCE",
        hf_reference_phase="9m",
        n_subjects=2,
        subject_ids=("sub-02", "sub-01"),
        status=CatalogStatus.DATA_AVAILABLE,
        failure_reasons=(),
    )


def _source(root: Path, *, accepted: bool = True) -> HFSourceRecord:
    ids = root / "hf_fiber_ids.npy"
    np.save(ids, np.array([11, 12, 13], dtype=np.int64))
    axis = FeatureAxisRef(ids, 3, "b" * 64, "data.mat:idx")
    manifest = root / "hf_source.json"
    manifest.write_text("{}\n", encoding="utf-8")
    artifact = ArtifactRef("hf-resolver", "source_manifest", "hf_source.json", "c" * 64, ())
    return HFSourceRecord.create(
        resolver_task_id="hf-resolver",
        endpoint_model_id="hf-endpoint",
        input_status="valid" if accepted else "unavailable",
        source_status="scan_fallback_accepted" if accepted else "absent_no_stable_grid",
        prediction_status="error_predictive" if accepted else "not_applicable",
        threshold_source="scan_fallback" if accepted else "none",
        selected_tau=675.0 if accepted else None,
        selected_coverage=7 if accepted else None,
        subject_order=("sub-02", "sub-01"),
        feature_axis=axis if accepted else None,
        artifacts=(artifact,) if accepted else (),
    )


def _delta(root: Path, *, valid: bool = True) -> DeltaHFBundle:
    return DeltaHFBundle(
        input_status="valid" if valid else "invalid",
        support_status="limited" if valid else "invalid_extreme_out_of_support",
        selected_hf_tau=675.0 if valid else None,
        selected_hf_coverage=7 if valid else None,
        full_scores=_artifact(root, "delta_hf_full_scores", "delta_full.npy", (2,)) if valid else None,
        fold_scores=_artifact(root, "delta_hf_fold_scores", "delta_folds.npy", (2, 2)) if valid else None,
        support_rows=_artifact(root, "delta_hf_support_rows", "delta_support.csv", (2,)) if valid else None,
        failure_stage="" if valid else "support_qc",
        failure_detail="" if valid else "extreme out of support",
    )


def _request(
    root: Path,
    *,
    endpoint: EndpointRecord,
    branch: str,
    source: HFSourceRecord,
    delta: DeltaHFBundle | None,
) -> ULFObservedRequest:
    return ULFObservedRequest(
        endpoint=endpoint,
        branch=branch,
        hf_source=source,
        delta_hf=delta,
        nuisance=NuisancePlan.for_branch(branch, delta),
        model_root=root / "models" / endpoint.endpoint_model_id,
        output_root=root / "models" / endpoint.endpoint_model_id / "tasks" / f"resolver-{branch}",
        tau_grid=(350.0, 800.0, 1250.0),
        coverage_grid=(3, 5, 9),
        primary_tau=800.0,
        primary_coverage=5,
        hf_overlap_tau=float(source.selected_tau) if source.accepted else math.inf,
        hf_overlap_coverage=int(source.selected_coverage) if source.accepted else None,
    )


def _inputs(root: Path, connectome: str = "ppmi") -> ULFNormativeFiberBackendInputs:
    return ULFNormativeFiberBackendInputs(
        connectome=ConnectomeSpec(
            connectome_id=connectome,
            label=f"Configured {connectome}",
            path=root / f"{connectome}.mat",
            fiber_identity_source="data.mat:idx",
        ),
        clinical_table=root / "clinical.xlsx",
        stimulation_table=root / "stimulation.xlsx",
        readiness_csv=root / "component_readiness.csv",
        derivatives_root=root / "derivatives",
        asset_root=root / "assets",
        matlab_bin=root / "matlab",
        run_root=root,
        clinical_columns={
            "subject_id": "ID",
            "scale": "Scale",
            "protocol": "Protocol",
            "phase": "Phase",
            "value": "Value",
            "baseline": "Baseline",
        },
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _endpoint_with_subjects(subject_ids: tuple[str, ...], connectome: str = "ppmi") -> EndpointRecord:
    endpoint = _endpoint(connectome)
    return EndpointRecord(
        **{
            **endpoint.__dict__,
            "n_subjects": len(subject_ids),
            "subject_ids": subject_ids,
        }
    )


def _immutable_hf_source(
    root: Path,
    *,
    subject_ids: tuple[str, ...],
    reference_exposure: np.ndarray,
    full_weights: np.ndarray,
    fold_weights: np.ndarray,
    tau: float = 1.0,
    coverage: int = 2,
) -> HFSourceRecord:
    source_root = root / "models" / "hf-endpoint" / "tasks" / "hf-resolver"
    source_root.mkdir(parents=True, exist_ok=True)
    fiber_ids = np.arange(1, reference_exposure.shape[1] + 1, dtype=np.int64)
    paths = {
        "exposure_matrix": source_root / "reference_exposure.npy",
        "selected_full_weights": source_root / "full_weights.npy",
        "selected_fold_weights": source_root / "fold_weights.npy",
        "selected_manifest": source_root / "selected_manifest.json",
    }
    np.save(paths["exposure_matrix"], reference_exposure)
    np.save(paths["selected_full_weights"], full_weights)
    np.save(paths["selected_fold_weights"], fold_weights)
    ids_path = source_root / "fiber_ids.npy"
    np.save(ids_path, fiber_ids)
    axis = FeatureAxisRef(ids_path, fiber_ids.size, _array_sha256(fiber_ids), "data.mat:idx")
    paths["selected_manifest"].write_text(
        json.dumps(
            {
                "status": "complete",
                "selected_tau_v_per_m": tau,
                "selected_coverage": coverage,
                "subject_order": list(subject_ids),
                "feature_axis": axis.as_dict(),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    artifacts = tuple(
        ArtifactRef(
            "hf-resolver",
            kind,
            path.relative_to(root).as_posix(),
            _sha256(path),
            tuple(np.load(path, mmap_mode="r").shape) if path.suffix == ".npy" else (),
        )
        for kind, path in paths.items()
    )
    return HFSourceRecord.create(
        resolver_task_id="hf-resolver",
        endpoint_model_id="hf-endpoint",
        input_status="valid",
        source_status="scan_fallback_accepted",
        prediction_status="error_predictive",
        threshold_source="scan_fallback",
        selected_tau=tau,
        selected_coverage=coverage,
        subject_order=subject_ids,
        feature_axis=axis,
        artifacts=artifacts,
    )


class ConfiguredULFFiberBackendTests(unittest.TestCase):
    def test_adjusted_config_preserves_endpoint_connectome_grid_and_delta_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            endpoint = _endpoint("mgh", "immediate")
            source = _source(root)
            delta = _delta(root)
            request = _request(root, endpoint=endpoint, branch="delta_hf_adjusted", source=source, delta=delta)
            inputs = _inputs(root, "mgh")
            config = build_legacy_ulf_fiber_config(request, inputs)

        self.assertEqual(config.endpoint_protocol, "CUSTOM_ADDON")
        self.assertEqual(config.endpoint_phase, "immediate")
        self.assertEqual(config.hf_reference_protocol, "CUSTOM_REFERENCE")
        self.assertEqual(config.hf_reference_phase, "9m")
        self.assertEqual(config.subject_order, ("sub-02", "sub-01"))
        self.assertEqual(config.connectome_id, "mgh")
        self.assertEqual(config.connectome_path, inputs.connectome.path)
        self.assertEqual(config.tau_grid, request.tau_grid)
        self.assertEqual(config.coverage_grid, request.coverage_grid)
        self.assertEqual((config.hf_overlap_tau, config.hf_overlap_coverage), (675.0, 7))
        self.assertEqual(config.nuisance_columns, ("Y_HF_ref", "DeltaHFScore"))
        self.assertEqual(config.delta_full_scores_path.name, "delta_full.npy")
        self.assertEqual(config.delta_fold_scores_path.name, "delta_folds.npy")
        self.assertEqual(config.delta_fold_scores_shape, (2, 2))
        self.assertEqual(config.delta_support_rows_path.name, "delta_support.csv")
        self.assertTrue(config.dynamic_names)

    def test_absent_hf_runs_no_delta_with_infinite_overlap_and_never_adjusted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            endpoint = _endpoint()
            source = _source(root, accepted=False)
            no_delta = _request(root, endpoint=endpoint, branch="no_delta_hf", source=source, delta=None)
            config = build_legacy_ulf_fiber_config(no_delta, _inputs(root))
            fabricated_adjusted = ULFObservedRequest(
                **{**no_delta.__dict__, "branch": "delta_hf_adjusted", "nuisance": no_delta.nuisance}
            )
            with self.assertRaises(RecordError):
                build_legacy_ulf_fiber_config(fabricated_adjusted, _inputs(root))

        self.assertTrue(math.isinf(config.hf_overlap_tau))
        self.assertIsNone(config.hf_overlap_coverage)
        self.assertEqual(config.nuisance_columns, ("Y_HF_ref",))
        self.assertIsNone(config.delta_full_scores_path)
        self.assertIsNone(config.delta_fold_scores_path)

    def test_invalid_delta_fails_adjusted_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            endpoint = _endpoint()
            source = _source(root)
            invalid = _delta(root, valid=False)
            no_delta = _request(root, endpoint=endpoint, branch="no_delta_hf", source=source, delta=invalid)
            no_delta_config = build_legacy_ulf_fiber_config(no_delta, _inputs(root))
            fabricated_adjusted = ULFObservedRequest(
                **{
                    **no_delta.__dict__,
                    "branch": "delta_hf_adjusted",
                    "nuisance": SimpleNamespace(columns=("Y_HF_ref", "DeltaHFScore")),
                }
            )
            with self.assertRaises(RecordError):
                build_legacy_ulf_fiber_config(fabricated_adjusted, _inputs(root))

        self.assertEqual(no_delta_config.branch, "no_delta_hf")

    def test_runner_returns_typed_output_and_rejects_feature_axis_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            endpoint = _endpoint("dtor")
            source = _source(root)
            request = _request(root, endpoint=endpoint, branch="delta_hf_adjusted", source=source, delta=_delta(root))
            inputs = _inputs(root, "dtor")
            ids_path = root / "fiber_ids.npy"
            ids_path.write_text("axis\n", encoding="utf-8")
            selected = root / "selected_source.json"
            status = root / "source_status.json"
            selected.write_text("{}\n", encoding="utf-8")
            status.write_text("{}\n", encoding="utf-8")
            hf_component = request.model_root / "cache" / "hf_component.npy"
            ulf_component = request.model_root / "cache" / "ulf_component.npy"
            y_base = request.model_root / "cache" / "y_base.npy"
            hf_component.parent.mkdir(parents=True, exist_ok=True)
            np.save(hf_component, np.ones((2, 3), dtype=np.float32))
            np.save(ulf_component, np.ones((2, 3), dtype=np.float32))
            np.save(y_base, np.ones(2, dtype=np.float64))

            def payload(axis_sha: str) -> dict[str, object]:
                return {
                    "branch": "delta_hf_adjusted",
                    "source_status": "pre_specified_accepted",
                    "prediction_status": "error_predictive",
                    "threshold_source": "pre_specified",
                    "selected_tau": 800.0,
                    "selected_coverage": 5,
                    "adjacent_support": 3,
                    "subject_order": list(endpoint.subject_ids),
                    "feature_axis": {
                        "ids_path": str(ids_path),
                        "count": 3,
                        "sha256": axis_sha,
                        "identity_source": "data.mat:idx",
                    },
                    "artifacts": {
                        "source_status": str(status),
                        "selected_source": str(selected),
                        "hf_component_exposure": str(hf_component),
                        "ulf_component_exposure": str(ulf_component),
                        "y_base": str(y_base),
                    },
                }

            fake = SimpleNamespace(run_ulf_normative_fiber_configured=lambda config: payload("b" * 64))
            with patch.object(legacy_ulf_fiber, "_load_legacy_analysis", return_value=fake):
                output = run_configured_ulf_fiber_resolver(request, inputs)
            bad = SimpleNamespace(run_ulf_normative_fiber_configured=lambda config: payload("d" * 64))
            with patch.object(legacy_ulf_fiber, "_load_legacy_analysis", return_value=bad):
                with self.assertRaisesRegex(RuntimeError, "feature axis"):
                    run_configured_ulf_fiber_resolver(request, inputs)
            fabricated = SimpleNamespace(
                run_ulf_normative_fiber_configured=lambda config: {
                    **payload("b" * 64),
                    "branch": "no_delta_hf",
                }
            )
            with patch.object(legacy_ulf_fiber, "_load_legacy_analysis", return_value=fabricated):
                with self.assertRaisesRegex(RuntimeError, "exact requested branch"):
                    run_configured_ulf_fiber_resolver(request, inputs)

        self.assertIsInstance(output, ObservedServiceOutput)
        self.assertEqual(output.source_status, "pre_specified_accepted")
        self.assertEqual(
            {artifact.kind for artifact in output.artifacts},
            {
                "source_status",
                "selected_source",
                "hf_component_exposure",
                "ulf_component_exposure",
                "y_base",
            },
        )

    def test_dynamic_names_and_all_connectome_identities_are_preserved(self) -> None:
        self.assertEqual(
            ulf_fiber_branch_name(1250.5, 9, "delta_hf_adjusted"),
            "ulf_peak_efield_tau1250p5_cov9_delta_hf_adjusted",
        )
        names = ulf_fiber_artifact_names(1250.5, 9, "delta_hf_adjusted", dynamic=True)
        self.assertIn("tau1250p5_cov9_delta_hf_adjusted", names["resolver_manifest"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for connectome in ("ppmi", "mgh", "dtor"):
                endpoint = _endpoint(connectome)
                request = _request(
                    root,
                    endpoint=endpoint,
                    branch="no_delta_hf",
                    source=_source(root, accepted=False),
                    delta=None,
                )
                config = build_legacy_ulf_fiber_config(request, _inputs(root, connectome))
                self.assertEqual(config.connectome_id, connectome)
                self.assertEqual(config.connectome_path, root / f"{connectome}.mat")

    def test_feature_axis_hash_matches_the_hf_normative_fiber_contract(self) -> None:
        fiber_ids = np.array([9, 2, 17], dtype=np.int64)
        self.assertEqual(_array_sha256(fiber_ids), sha256_array(fiber_ids))

    def test_adjusted_fold_provider_uses_the_heldout_specific_delta_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            endpoint = _endpoint()
            source = _source(root)
            request = _request(root, endpoint=endpoint, branch="delta_hf_adjusted", source=source, delta=_delta(root))
            config = build_legacy_ulf_fiber_config(request, _inputs(root))
            np.save(config.delta_full_scores_path, np.array([10.0, 20.0]))
            np.save(config.delta_fold_scores_path, np.array([[1.0, 2.0], [3.0, 4.0]]))
            full, provider, _ = _configured_delta_inputs(config, list(endpoint.subject_ids))

        np.testing.assert_array_equal(full, np.array([10.0, 20.0]))
        np.testing.assert_array_equal(provider(0)["delta"], np.array([1.0, 2.0]))
        np.testing.assert_array_equal(provider(1)["delta"], np.array([3.0, 4.0]))


class DeltaHFSupportTests(unittest.TestCase):
    def test_adequate_and_limited_use_suprathreshold_out_candidate_exposure(self) -> None:
        component = np.full((4, 5), 2.0, dtype=float)
        component[:, 4] = 100.0
        adequate, adequate_rows, _ = _assess_hf_component_fiber_support(
            component_exposure=component,
            full_candidate=np.array([True, True, True, True, False]),
            fold_candidates=np.tile(
                np.array([True, True, True, True, False]),
                (4, 1),
            ),
            selected_tau=1.0,
            subject_ids=("s1", "s2", "s3", "s4"),
        )
        limited, limited_rows, _ = _assess_hf_component_fiber_support(
            component_exposure=component,
            full_candidate=np.array([True, True, True, False, False]),
            fold_candidates=np.tile(
                np.array([True, True, True, False, False]),
                (4, 1),
            ),
            selected_tau=1.0,
            subject_ids=("s1", "s2", "s3", "s4"),
        )

        self.assertEqual(adequate.status, "adequate")
        self.assertTrue(adequate.valid)
        self.assertEqual([row["subject_id"] for row in adequate_rows], ["s1", "s2", "s3", "s4"])
        self.assertTrue(all(math.isclose(row["subject_out_candidate_fraction"], 0.2) for row in adequate_rows))
        self.assertEqual(limited.status, "limited")
        self.assertTrue(limited.valid)
        self.assertTrue(all(math.isclose(row["subject_out_candidate_fraction"], 0.4) for row in limited_rows))

    def test_any_fold_over_point_95_is_extreme_even_when_full_support_is_adequate(self) -> None:
        component = np.full((4, 5), 2.0, dtype=float)
        fold_candidates = np.ones((4, 5), dtype=bool)
        fold_candidates[2] = False
        assessment, rows, qc = _assess_hf_component_fiber_support(
            component_exposure=component,
            full_candidate=np.ones(5, dtype=bool),
            fold_candidates=fold_candidates,
            selected_tau=1.0,
            subject_ids=("s1", "s2", "s3", "s4"),
        )

        self.assertEqual(assessment.status, "invalid_extreme_out_of_support")
        self.assertFalse(assessment.valid)
        self.assertEqual(assessment.maximum_required_fraction, 1.0)
        self.assertTrue(all(row["maximum_fold_out_candidate_fraction"] == 1.0 for row in rows))
        self.assertEqual(qc["n_required_fold_subject_pairs"], 16)

    def test_zero_touched_or_nonpositive_total_is_invalid_no_hfcomponent_exposure(self) -> None:
        component = np.full((4, 5), 2.0, dtype=float)
        component[1] = 0.5
        assessment, rows, qc = _assess_hf_component_fiber_support(
            component_exposure=component,
            full_candidate=np.ones(5, dtype=bool),
            fold_candidates=np.ones((4, 5), dtype=bool),
            selected_tau=1.0,
            subject_ids=("s1", "s2", "s3", "s4"),
        )

        self.assertEqual(assessment.status, "invalid_no_hfcomponent_exposure")
        self.assertFalse(assessment.valid)
        self.assertEqual(rows[1]["suprathreshold_touched_count"], 0)
        self.assertEqual(rows[1]["total_suprathreshold_exposure"], 0.0)
        self.assertTrue(qc["any_zero_touched_or_nonpositive_total"])


class DeltaHFBuilderTests(unittest.TestCase):
    def test_builder_uses_immutable_full_and_fold_weights_and_writes_atomic_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subject_ids = ("s1", "s2", "s3", "s4")
            endpoint = _endpoint_with_subjects(subject_ids)
            reference = np.array(
                [
                    [2.0, 2.0, 2.0, 2.0],
                    [2.5, 2.0, 2.0, 2.0],
                    [2.0, 2.5, 2.0, 2.0],
                    [2.0, 2.0, 2.5, 2.0],
                ]
            )
            component = np.array(
                [
                    [3.0, 2.0, 2.0, 2.0],
                    [2.0, 3.0, 2.0, 2.0],
                    [2.0, 2.0, 3.0, 2.0],
                    [2.0, 2.0, 2.0, 3.0],
                ]
            )
            full_weights = np.array([2.0, -1.0, 1.0, -2.0])
            fold_weights = np.array(
                [
                    [2.0, -1.0, 1.0, -2.0],
                    [1.0, -2.0, 2.0, -1.0],
                    [3.0, -1.0, 1.0, -2.0],
                    [2.0, -3.0, 1.0, -1.0],
                ]
            )
            source = _immutable_hf_source(
                root,
                subject_ids=subject_ids,
                reference_exposure=reference,
                full_weights=full_weights,
                fold_weights=fold_weights,
            )
            task = SimpleNamespace(
                task_id="ulf-sidecars",
                endpoint=endpoint.key,
                key=SimpleNamespace(execution_stage="preprocessing_sidecars"),
            )
            context = SimpleNamespace(
                store=SimpleNamespace(run_root=root),
                config=SimpleNamespace(workflow=SimpleNamespace(execution=SimpleNamespace(force=False))),
            )
            inputs = _inputs(root)

            def component_payload(config, *, include_hashes: bool):
                config.output_dir.mkdir(parents=True, exist_ok=True)
                exposure_path = config.output_dir / "hf_component_exposure.npy"
                ids_path = config.output_dir / "fiber_ids.npy"
                np.save(exposure_path, component)
                np.save(ids_path, np.arange(1, 5, dtype=np.int64))
                payload = {
                    "exposure_matrix": str(exposure_path),
                    "fiber_ids": str(ids_path),
                    "subject_order": list(subject_ids),
                    "feature_axis_sha256": _array_sha256(np.arange(1, 5, dtype=np.int64)),
                }
                if include_hashes:
                    payload["exposure_sha256"] = _sha256(exposure_path)
                    payload["fiber_ids_file_sha256"] = _sha256(ids_path)
                return payload

            missing_hash_builder = configured_ulf_fiber_delta_builder(
                inputs=inputs,
                component_runner=lambda config: component_payload(config, include_hashes=False),
            )
            with self.assertRaisesRegex(RecordError, "component exposure hash"):
                missing_hash_builder(endpoint, source, task, context)

            builder = configured_ulf_fiber_delta_builder(
                inputs=inputs,
                component_runner=lambda config: component_payload(config, include_hashes=True),
            )
            output = builder(endpoint, source, task, context)
            task_root = root / "models" / endpoint.endpoint_model_id / "tasks" / task.task_id
            full = np.load(task_root / "full.npy")
            folds = np.load(task_root / "folds.npy")
            support_rows = (task_root / "support.csv").read_text(encoding="utf-8").splitlines()
            support_qc = json.loads((task_root / "support_qc.json").read_text(encoding="utf-8"))

            active = reference > source.selected_tau
            full_candidate = candidate_mask_from_coverage(
                coverage_from_suprathreshold(active),
                source.selected_coverage,
            )
            expected_full = (
                fiber_net_score(component, full_weights, full_candidate, fiber_ids=np.arange(1, 5)).net_score
                - fiber_net_score(reference, full_weights, full_candidate, fiber_ids=np.arange(1, 5)).net_score
            )
            fold_candidate = candidate_mask_from_coverage(
                coverage_from_suprathreshold(active) - active[1].astype(np.int32),
                source.selected_coverage,
            )
            expected_fold_1 = (
                fiber_net_score(component, fold_weights[1], fold_candidate, fiber_ids=np.arange(1, 5)).net_score
                - fiber_net_score(reference, fold_weights[1], fold_candidate, fiber_ids=np.arange(1, 5)).net_score
            )

            self.assertIsInstance(output, DeltaBuilderOutput)
            self.assertTrue(output.bundle.valid)
            self.assertEqual(output.bundle.support_status, "adequate")
            np.testing.assert_allclose(full, expected_full)
            np.testing.assert_allclose(folds[1], expected_fold_1)
            self.assertEqual(folds.shape, (4, 4))
            self.assertEqual(output.bundle.full_scores.shape, (4,))
            self.assertEqual(output.bundle.fold_scores.shape, (4, 4))
            self.assertEqual(output.bundle.support_rows.shape, (4,))
            self.assertEqual([line.split(",", 1)[0] for line in support_rows[1:]], list(subject_ids))
            self.assertEqual(support_qc["support_status"], "adequate")
            self.assertEqual(
                {artifact.kind for artifact in output.artifacts},
                {"delta_hf_full_scores", "delta_hf_fold_scores", "delta_hf_support_rows", "delta_hf_support_qc"},
            )
            for reference_artifact in (
                output.bundle.full_scores,
                output.bundle.fold_scores,
                output.bundle.support_rows,
            ):
                artifact_path = root / reference_artifact.relative_path
                self.assertEqual(reference_artifact.sha256, _sha256(artifact_path))
            self.assertFalse(list(task_root.glob(".*.tmp-*")))


if __name__ == "__main__":
    unittest.main()
