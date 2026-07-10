"""Tests for immutable-final-record formal backend adapters."""

from __future__ import annotations

import csv
from dataclasses import replace
import hashlib
import importlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from outcome_models.identity import EndpointModelKey, TaskKey
from outcome_models.planner import GatePredicate, TaskGate, TaskSpec
from outcome_models.records import (
    ArtifactRef,
    DeltaHFBundle,
    FeatureAxisRef,
    FinalArtifactRecord,
    NuisancePlan,
    RecordError,
)
from outcome_models.services.formal import FormalRequest
from outcome_models.services.legacy_formal import (
    build_configured_formal_target,
    run_configured_formal,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ConfiguredFormalBackendTests(unittest.TestCase):
    def _task(self, model_family: str, stage: str) -> TaskSpec:
        endpoint = EndpointModelKey(
            study_id="synthetic",
            scale_id="scale_one",
            endpoint_phase="chronic" if model_family.startswith("ulf_") else "reference",
            model_family=model_family,
            connectome="dtor" if model_family.endswith("fiber") else "none",
        )
        key = TaskKey(
            endpoint_model_id=endpoint.identifier,
            execution_stage=stage,
            branch="realized_final" if model_family.startswith("ulf_") else "none",
            source_reference="final_model_record",
        )
        kinds = (
            ("task_manifest", "permutation_results", "bootstrap_results")
            if stage == "formal_permutation_bootstrap"
            else ("task_manifest", "permutation_results" if stage == "formal_permutation" else "bootstrap_results")
        )
        return TaskSpec(
            task_id=key.identifier,
            key=key,
            endpoint=endpoint,
            round_name="Round 7" if model_family.startswith("ulf_") else "Round 6",
            workflow_phase="formal",
            dependencies=(),
            gate=TaskGate(GatePredicate.FINAL_MODEL_REALIZED),
            expected_artifact_kinds=kinds,
        )

    def _artifact(self, root: Path, path: Path, kind: str, shape=()) -> ArtifactRef:
        return ArtifactRef(
            task_id="task_final",
            kind=kind,
            relative_path=path.relative_to(root).as_posix(),
            sha256=_sha256(path),
            shape=shape,
        )

    def _request(
        self,
        root: Path,
        *,
        model_family: str,
        stage: str,
        branch: str,
        nuisance: NuisancePlan,
        tau: float,
        coverage: int,
    ) -> FormalRequest:
        task = self._task(model_family, stage)
        artifact_root = root / "artifacts"
        artifact_root.mkdir(parents=True, exist_ok=True)
        exposure = artifact_root / "exposure.npy"
        feature_ids = artifact_root / "feature_ids.npy"
        scores = artifact_root / "scores.csv"
        manifest = artifact_root / "final_manifest.json"
        np.save(exposure, np.arange(48, dtype=np.float32).reshape(12, 4))
        np.save(feature_ids, np.arange(4, dtype=np.int64))
        nuisance_name = "Y_base" if branch == "hf_source" else "Y_HF_ref"
        with scores.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["subject_id", "Y_post", nuisance_name])
            writer.writeheader()
            for index in range(12):
                writer.writerow(
                    {
                        "subject_id": f"sub-{index + 1:02d}",
                        "Y_post": 30 - index,
                        nuisance_name: 40 - index,
                    }
                )
        manifest.write_text(
            json.dumps(
                {
                    "scale_direction": "lower",
                    "subject_order": [f"sub-{index + 1:02d}" for index in range(12)],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        final = FinalArtifactRecord.create(
            final_model_id="final_selected",
            endpoint_model_id=task.endpoint.identifier,
            final_branch=branch,
            final_role="primary",
            selected_tau=tau,
            selected_coverage=coverage,
            estimator="partial_spearman",
            scale_direction="lower",
            subject_order=tuple(f"sub-{index + 1:02d}" for index in range(12)),
            nuisance=nuisance,
            manifest=self._artifact(root, manifest, "final_manifest"),
            exposure=self._artifact(root, exposure, "exposure", (12, 4)),
            scores=self._artifact(root, scores, "scores", (12,)),
            feature_axis=FeatureAxisRef(
                ids_path=feature_ids,
                count=4,
                sha256=_sha256(feature_ids),
                identity_source=("data.mat:idx" if model_family.endswith("fiber") else "candidate_flat_indices"),
            ),
        )
        return FormalRequest(
            task=task,
            final=final,
            output_root=root / "models" / task.endpoint.identifier / "tasks" / task.task_id,
            permutations=17,
            bootstraps=19,
            seed=23,
        )

    def test_direct_no_delta_target_uses_only_final_record_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = self._request(
                root,
                model_family="ulf_voxel",
                stage="formal_permutation",
                branch="no_delta_hf",
                nuisance=NuisancePlan.for_branch("no_delta_hf", None),
                tau=250,
                coverage=6,
            )
            rogue_delta = request.output_root.parent / "DeltaHFScore.npy"
            rogue_delta.parent.mkdir(parents=True, exist_ok=True)
            np.save(rogue_delta, np.ones(12))
            target = build_configured_formal_target(request)

        self.assertEqual(target.model_id, request.final.final_model_id)
        self.assertEqual(target.branch_dir, request.output_root)
        self.assertEqual(target.x_path, (root / request.final.exposure.relative_path).resolve())
        self.assertEqual(target.subjects_csv, (root / request.final.scores.relative_path).resolve())
        self.assertEqual(target.nuisance_columns, ("Y_HF_ref",))
        self.assertEqual((target.tau, target.min_coverage), (250.0, 6))
        self.assertEqual(target.subject_order[0], "sub-01")
        self.assertFalse(hasattr(target, "delta_hf_path"))

    def test_feature_axis_must_remain_inside_configured_run_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            root = Path(tmp)
            request = self._request(
                root,
                model_family="hf_voxel",
                stage="formal_permutation",
                branch="hf_source",
                nuisance=NuisancePlan.for_branch("hf_source", None),
                tau=200,
                coverage=5,
            )
            outside_axis = Path(outside) / "feature_ids.npy"
            np.save(outside_axis, np.arange(4, dtype=np.int64))
            request = replace(
                request,
                final=replace(
                    request.final,
                    feature_axis=FeatureAxisRef(
                        ids_path=outside_axis,
                        count=4,
                        sha256=_sha256(outside_axis),
                        identity_source="candidate_flat_indices",
                    ),
                ),
            )

            with self.assertRaisesRegex(RecordError, "outside.*run root"):
                build_configured_formal_target(request)

    def test_fiber_combined_runner_returns_exact_standard_artifact_kinds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = self._request(
                root,
                model_family="hf_fiber",
                stage="formal_permutation_bootstrap",
                branch="hf_source",
                nuisance=NuisancePlan.for_branch("hf_source", None),
                tau=1000,
                coverage=7,
            )
            calls: list[tuple[str, int, int, float, int]] = []

            def permutation(target, *, n_permutations, seed, tier):
                calls.append((tier, n_permutations, seed, target.tau, target.min_coverage))
                path = target.branch_dir / f"{target.output_prefix}_permutation_summary.csv"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("result\n", encoding="utf-8")
                return {"summary_csv": str(path)}

            def bootstrap(target, *, n_bootstraps, seed):
                calls.append(("bootstrap", n_bootstraps, seed, target.tau, target.min_coverage))
                path = target.branch_dir / f"{target.output_prefix}_bootstrap_summary.csv"
                path.write_text("result\n", encoding="utf-8")
                return {"summary_csv": str(path)}

            output = run_configured_formal(
                request,
                fiber_permutation_runner=permutation,
                fiber_bootstrap_runner=bootstrap,
            )

        self.assertEqual([artifact.kind for artifact in output.artifacts], ["permutation_results", "bootstrap_results"])
        self.assertEqual(
            calls,
            [
                ("formal", 17, 23, 1000.0, 7),
                ("bootstrap", 19, 23, 1000.0, 7),
            ],
        )

    def test_direct_runner_dispatches_only_requested_operation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = self._request(
                root,
                model_family="hf_voxel",
                stage="formal_bootstrap",
                branch="hf_source",
                nuisance=NuisancePlan.for_branch("hf_source", None),
                tau=180,
                coverage=5,
            )
            calls: list[tuple[int, int]] = []

            def bootstrap(target, *, n_bootstraps, seed):
                calls.append((n_bootstraps, seed))
                path = target.branch_dir / f"{target.output_prefix}_bootstrap_summary.csv"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("result\n", encoding="utf-8")
                return {"summary_csv": str(path)}

            output = run_configured_formal(request, direct_bootstrap_runner=bootstrap)

        self.assertEqual(calls, [(19, 23)])
        self.assertEqual([artifact.kind for artifact in output.artifacts], ["bootstrap_results"])

    def test_direct_default_bootstrap_reports_missing_spatial_reference_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = self._request(
                Path(tmp),
                model_family="hf_voxel",
                stage="formal_bootstrap",
                branch="hf_source",
                nuisance=NuisancePlan.for_branch("hf_source", None),
                tau=200,
                coverage=5,
            )
            with self.assertRaisesRegex(
                RecordError,
                "FinalArtifactRecord must carry a spatial_reference ArtifactRef",
            ):
                run_configured_formal(request)

    def test_adjusted_branch_uses_full_and_fold_delta_artifact_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            delta_root = root / "delta"
            delta_root.mkdir()
            full = delta_root / "full.npy"
            folds = delta_root / "folds.npy"
            support = delta_root / "support.csv"
            np.save(full, np.ones(12))
            np.save(folds, np.ones((12, 12)))
            support.write_text("subject_id\n", encoding="utf-8")
            bundle = DeltaHFBundle(
                input_status="valid",
                support_status="adequate",
                selected_hf_tau=200,
                selected_hf_coverage=5,
                full_scores=self._artifact(root, full, "delta_hf_full_scores", (12,)),
                fold_scores=self._artifact(root, folds, "delta_hf_fold_scores", (12, 12)),
                support_rows=self._artifact(root, support, "delta_hf_support_rows", (12,)),
            )
            request = self._request(
                root,
                model_family="ulf_voxel",
                stage="formal_permutation",
                branch="delta_hf_adjusted",
                nuisance=NuisancePlan.for_branch("delta_hf_adjusted", bundle),
                tau=200,
                coverage=5,
            )

            target = build_configured_formal_target(request)

        self.assertEqual(target.delta_hf_full_path, full.resolve())
        self.assertEqual(target.delta_hf_fold_path, folds.resolve())

    def test_adapter_rejects_tampered_final_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = self._request(
                root,
                model_family="hf_voxel",
                stage="formal_permutation",
                branch="hf_source",
                nuisance=NuisancePlan.for_branch("hf_source", None),
                tau=200,
                coverage=5,
            )
            (root / request.final.scores.relative_path).write_text("tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(RecordError, "artifact SHA-256 mismatch"):
                build_configured_formal_target(request)

    def test_direct_numerical_backend_uses_fold_specific_delta_design(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = self._request(
                root,
                model_family="ulf_voxel",
                stage="formal_permutation",
                branch="no_delta_hf",
                nuisance=NuisancePlan.for_branch("no_delta_hf", None),
                tau=0.5,
                coverage=5,
            )
            target = build_configured_formal_target(request)
            module = importlib.import_module("stnsnr_direct_voxel_formal_permutation")
            full = root / "delta_full.npy"
            folds = root / "delta_folds.npy"
            np.save(full, np.linspace(0.1, 1.2, 12))
            fold_values = np.arange(144, dtype=float).reshape(12, 12) / 10.0
            np.save(folds, fold_values)
            target = module.DirectVoxelTarget(
                **{
                    **target.__dict__,
                    "delta_hf_full_path": full,
                    "delta_hf_fold_path": folds,
                }
            )
            table = module.load_subject_table(target.subjects_csv)
            full_nuisance, fold_nuisance = module.load_target_nuisance(target, table)
            x = np.random.default_rng(7).normal(2.0, 0.5, size=(12, 10))
            operators = module.build_fold_score_operators(
                x=x,
                nuisance=full_nuisance,
                fold_nuisance=fold_nuisance,
                scale_direction="lower",
                tau=0.5,
                min_coverage=5,
            )

        self.assertEqual(full_nuisance.shape, (12, 2))
        self.assertEqual(fold_nuisance.shape, (12, 12, 2))
        self.assertEqual(operators[3].nuisance_test[0, 1], fold_values[3, 3])

    def test_fiber_numerical_backend_uses_fold_specific_delta_design(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request = self._request(
                root,
                model_family="ulf_fiber",
                stage="formal_permutation_bootstrap",
                branch="no_delta_hf",
                nuisance=NuisancePlan.for_branch("no_delta_hf", None),
                tau=0.5,
                coverage=5,
            )
            target = build_configured_formal_target(request)
            module = importlib.import_module("stnsnr_normative_fiber_smoke_permutation")
            full = root / "delta_full.npy"
            folds = root / "delta_folds.npy"
            np.save(full, np.linspace(0.1, 1.2, 12))
            fold_values = np.arange(144, dtype=float).reshape(12, 12) / 10.0
            np.save(folds, fold_values)
            target = module.NormativeFiberTarget(
                **{
                    **target.__dict__,
                    "delta_hf_full_path": full,
                    "delta_hf_fold_path": folds,
                }
            )
            columns = module._load_score_columns(target.scores_csv)
            full_nuisance, fold_nuisance = module.load_target_nuisance(target, columns)
            x = np.random.default_rng(9).normal(2.0, 0.5, size=(12, 10)).astype(np.float32)
            reduced = module.prepare_candidate_union(
                x=x,
                fiber_ids=np.arange(10),
                tau=0.5,
                min_coverage=5,
            )
            caches = module.build_fold_fiber_caches(reduced, full_nuisance, fold_nuisance)

        self.assertEqual(full_nuisance.shape, (12, 2))
        self.assertEqual(fold_nuisance.shape, (12, 12, 2))
        self.assertEqual(caches[4].nuisance_test[0, 1], fold_values[4, 4])


if __name__ == "__main__":
    unittest.main()
